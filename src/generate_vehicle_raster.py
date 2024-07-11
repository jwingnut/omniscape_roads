import os
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
import requests
from shapely.geometry import box
import pandas as pd
import osmnx as ox
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fetch_acs_block_group_data(api_key, state, county):
    url = "https://api.census.gov/data/2020/acs/acs5"
    params = {
        'get': 'B25044_001E,B25044_002E,B25044_003E,B25044_004E,B25044_005E,B25044_006E,B25044_007E',
        'for': f'block group:*',
        'in': f'state:{state} county:{county}',
        'key': api_key
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        logging.error(f"API request failed with status code {response.status_code}")
        logging.error(f"Response content: {response.text}")
        raise Exception("Failed to fetch ACS data")
    data = response.json()

    columns = data[0]
    df = pd.DataFrame(data[1:], columns=columns)

    for col in columns[:-4]:  # Convert all but the last 4 columns (state, county, tract, block group) to numeric
        df[col] = pd.to_numeric(df[col], errors='coerce')

    logging.info(f"Fetched ACS data: {len(df)} rows")
    return df

def fetch_block_group_geometries(state, county):
    url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/8/query"
    params = {
        'where': f"STATE='{state}' AND COUNTY='{county}'",
        'outFields': '*',
        'returnGeometry': 'true',
        'f': 'geojson',
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        logging.error(f"Block group geometries API request failed with status code {response.status_code}")
        logging.error(f"Response content: {response.text}")
        raise Exception("Failed to fetch block group geometries")

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        logging.error("Failed to decode JSON from response")
        logging.error(f"Raw response content: {response.text[:1000]}...")  # Print first 1000 characters
        raise Exception("Invalid JSON response from Census API")

    if 'features' in data:
        gdf = gpd.GeoDataFrame.from_features(data['features'], crs='EPSG:4326')
        if 'geometry' in gdf.columns:
            gdf = gdf.set_geometry('geometry')
        logging.info(f"Fetched block groups: {len(gdf)} features")
        return gdf
    else:
        logging.warning("No features found in block group response")
        logging.warning(f"Response keys: {data.keys()}")
        return gpd.GeoDataFrame(columns=['geometry'], crs='EPSG:4326')

def generate_vehicle_raster(city_name, pixel_size, vehicle_edge_buffer, vehicle_edge_buffer_value,
                            region, case_type, case_folder, h, w, api_key):
    try:
        total_start_time = time.time()

        region_str = "full" if region is None else f"{region[0]}_{region[1]}"
        output_raster_path = os.path.join(case_folder,
                                          f"{city_name}_vehicles_{pixel_size}m_border{vehicle_edge_buffer}_value{vehicle_edge_buffer_value}_region{region_str}.tif")
        output_shapefile_path = os.path.join(case_folder,
                                             f"{city_name}_block_groups_vehicles_{region_str}.shp")

        logging.info(f"Generating vehicle raster for {city_name}, {case_type}, region: {region_str}")

        if not os.path.exists(output_raster_path):
            logging.info("Raster file doesn't exist. Generating new raster.")

            graph_path = f"/mnt/p/python_geoserver_scripts/new_omniscape/{city_name}_road_network.graphml"
            G = ox.load_graphml(graph_path)
            nodes, edges = ox.graph_to_gdfs(G)

            original_bounds = edges.total_bounds
            geo_polygon = gpd.GeoSeries([box(*original_bounds)], crs='EPSG:4326')
            geo_polygon = geo_polygon.to_crs('EPSG:3310')
            projected_bounds = geo_polygon.total_bounds

            state = "06"  # California
            county = "007"  # Butte County

            logging.info("Fetching ACS data...")
            df = fetch_acs_block_group_data(api_key, state, county)

            logging.info("Fetching block group geometries...")
            gdf_geometries = fetch_block_group_geometries(state, county)

            logging.info("Merging data with geometries...")
            df['GEOID'] = df['state'] + df['county'] + df['tract'] + df['block group']
            gdf_geometries['GEOID'] = gdf_geometries['GEOID'].astype(str)

            gdf = gdf_geometries.merge(df, on='GEOID', how='inner')

            gdf['no_vehicle'] = gdf['B25044_002E']
            gdf['one_vehicle'] = gdf['B25044_003E']
            gdf['two_vehicles'] = gdf['B25044_004E']
            gdf['three_vehicles'] = gdf['B25044_005E']
            gdf['four_vehicles'] = gdf['B25044_006E']
            gdf['five_plus_vehicles'] = gdf['B25044_007E']

            gdf['total_vehicles'] = (
                    (gdf['one_vehicle'] * 1) +
                    (gdf['two_vehicles'] * 2) +
                    (gdf['three_vehicles'] * 3) +
                    (gdf['four_vehicles'] * 4) +
                    (gdf['five_plus_vehicles'] * 5)
            )

            gdf['area_m2'] = gdf.to_crs('EPSG:3310').area
            pixel_area = pixel_size * pixel_size
            gdf['vehicles_per_pixel'] = gdf['total_vehicles'].div(gdf['area_m2']) * pixel_area

            logging.info(
                f"Vehicles per pixel stats: min={gdf['vehicles_per_pixel'].min()}, max={gdf['vehicles_per_pixel'].max()}, mean={gdf['vehicles_per_pixel'].mean()}")

            # Save the block groups with total vehicle counts as a shapefile
            gdf[['geometry', 'GEOID', 'total_vehicles']].to_file(output_shapefile_path)
            logging.info(f"Saved block groups shapefile to: {output_shapefile_path}")

            gdf = gdf.to_crs('EPSG:3310')
            x_min, y_min, x_max, y_max = projected_bounds
            width = max(int((x_max - x_min) / pixel_size), 1)
            height = max(int((y_max - y_min) / pixel_size), 1)
            transform = from_origin(x_min, y_max, pixel_size, pixel_size)

            shapes_and_values = [(geom, value) for geom, value in
                                 zip(gdf.geometry, gdf['vehicles_per_pixel']) if geom.is_valid]

            if not shapes_and_values:
                raise ValueError("No valid geometry objects found for rasterization")

            raster = rasterize(shapes_and_values, out_shape=(height, width), transform=transform, fill=0,
                               dtype='float32')

            if case_type == "base_case_no_border":
                final_raster = raster
                final_transform = transform
            elif case_type == "base_case_with_border":
                border_height, border_width = height + 2 * vehicle_edge_buffer, width + 2 * vehicle_edge_buffer
                border_transform = from_origin(x_min - vehicle_edge_buffer * pixel_size,
                                               y_max + vehicle_edge_buffer * pixel_size, pixel_size, pixel_size)
                final_raster = np.pad(raster, (
                    (vehicle_edge_buffer, vehicle_edge_buffer), (vehicle_edge_buffer, vehicle_edge_buffer)),
                                      mode='constant', constant_values=vehicle_edge_buffer_value)
                final_transform = border_transform
            else:  # edge_region case
                border_height, border_width = height + 2 * vehicle_edge_buffer, width + 2 * vehicle_edge_buffer
                border_transform = from_origin(x_min - vehicle_edge_buffer * pixel_size,
                                               y_max + vehicle_edge_buffer * pixel_size, pixel_size, pixel_size)
                border_raster = np.pad(raster, (
                    (vehicle_edge_buffer, vehicle_edge_buffer), (vehicle_edge_buffer, vehicle_edge_buffer)),
                                       mode='constant', constant_values=vehicle_edge_buffer_value)

                i, j = region
                vert_slice = slice(i * border_height // h, (i + 1) * border_height // h)
                horz_slice = slice(j * border_width // w, (j + 1) * border_width // w)

                if i == 0:  # Top edge
                    border_raster[vert_slice.start:vert_slice.start + vehicle_edge_buffer, horz_slice] = 0
                if i == h - 1:  # Bottom edge
                    border_raster[vert_slice.stop - vehicle_edge_buffer:vert_slice.stop, horz_slice] = 0
                if j == 0:  # Left edge
                    border_raster[vert_slice, horz_slice.start:horz_slice.start + vehicle_edge_buffer] = 0
                if j == w - 1:  # Right edge
                    border_raster[vert_slice, horz_slice.stop - vehicle_edge_buffer:horz_slice.stop] = 0

                final_raster = border_raster
                final_transform = border_transform

            with rasterio.open(output_raster_path, 'w', driver='GTiff', height=final_raster.shape[0],
                               width=final_raster.shape[1], count=1, dtype='float32', crs='EPSG:3310',
                               transform=final_transform) as dst:
                dst.write(final_raster, 1)

            logging.info(f"Generated raster with shape: {final_raster.shape}")
        else:
            logging.info(f"Vehicle raster for {city_name} already exists. Skipping generation.")

        total_elapsed_time = time.time() - total_start_time
        logging.info(f"Total time for generating vehicle raster: {total_elapsed_time:.2f} seconds")

        return output_raster_path

    except Exception as e:
        logging.error(f"Error in generate_vehicle_raster: {str(e)}")
        logging.exception("Full traceback:")
        raise

def get_regions_to_process(h, w, exit_nodes_path=None):
    all_regions = [(i, j) for i in range(h) for j in range(w) if i == 0 or i == h - 1 or j == 0 or j == w - 1]

    if exit_nodes_path:
        try:
            exit_nodes = gpd.read_file(exit_nodes_path)
            exit_nodes = exit_nodes.to_crs('EPSG:3310')

            total_bounds = exit_nodes.total_bounds
            width = total_bounds[2] - total_bounds[0]
            height = total_bounds[3] - total_bounds[1]

            regions_with_nodes = set()
            for _, node in exit_nodes.iterrows():
                i = int(h * (node.geometry.y - total_bounds[1]) / height)
                j = int(w * (node.geometry.x - total_bounds[0]) / width)
                if (i, j) in all_regions:
                    regions_with_nodes.add((i, j))

            return list(regions_with_nodes)
        except Exception as e:
            logging.error(f"Error processing exit nodes file: {e}")
            return all_regions
    else:
        return all_regions