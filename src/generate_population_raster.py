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

def fetch_census_blocks(bbox):
    url = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/12/query"
    params = {
        'where': '1=1',
        'outFields': '*',
        'geometry': f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        'geometryType': 'esriGeometryEnvelope',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnGeometry': 'true',
        'f': 'geojson',
    }
    response = requests.get(url, params=params)
    data = response.json()
    return gpd.GeoDataFrame.from_features(data['features'],
                                          crs='EPSG:4326') if 'features' in data else gpd.GeoDataFrame([],
                                                                                                       crs='EPSG:4326')

def generate_population_raster(city_name, pixel_size, population_edge_buffer, population_edge_buffer_value,
                               region, case_type, case_folder, h, w):
    try:
        total_start_time = time.time()

        region_str = "full" if region is None else f"{region[0]}_{region[1]}"
        output_raster_path = os.path.join(case_folder,
                                          f"{city_name}_population_{pixel_size}m_border{population_edge_buffer}_value{population_edge_buffer_value}_region{region_str}.tif")

        logging.info(f"Generating population raster for {city_name}, {case_type}, region: {region_str}")

        if not os.path.exists(output_raster_path):
            logging.info("Raster file doesn't exist. Generating new raster.")

            graph_path = f"/mnt/p/python_geoserver_scripts/new_omniscape/{city_name}_road_network.graphml"
            G = ox.load_graphml(graph_path)
            nodes, edges = ox.graph_to_gdfs(G)

            original_bounds = edges.total_bounds
            geo_polygon = gpd.GeoSeries([box(*original_bounds)], crs='EPSG:4326')
            geo_polygon = geo_polygon.to_crs('EPSG:3310')
            projected_bounds = geo_polygon.total_bounds

            census_blocks = fetch_census_blocks(geo_polygon.to_crs('EPSG:4326').total_bounds)
            if census_blocks.empty:
                raise ValueError("No census blocks fetched; check API call and bounding box.")
            census_blocks = census_blocks.to_crs('EPSG:3310')
            census_blocks['area_m2'] = census_blocks.geometry.area
            pixel_area = pixel_size * pixel_size
            census_blocks['pop_per_pixel'] = census_blocks['POP100'].div(census_blocks['area_m2']) * pixel_area

            x_min, y_min, x_max, y_max = projected_bounds
            width = max(int((x_max - x_min) / pixel_size), 1)
            height = max(int((y_max - y_min) / pixel_size), 1)
            transform = from_origin(x_min, y_max, pixel_size, pixel_size)
            shapes_and_values = [(geom, value) for geom, value in
                                 zip(census_blocks.geometry, census_blocks['pop_per_pixel'])]
            raster = rasterize(shapes_and_values, out_shape=(height, width), transform=transform, fill=0,
                               dtype='float32')

            if case_type == "base_case_no_border":
                final_raster = raster
                final_transform = transform
            elif case_type == "base_case_with_border":
                border_height, border_width = height + 2 * population_edge_buffer, width + 2 * population_edge_buffer
                border_transform = from_origin(x_min - population_edge_buffer * pixel_size,
                                               y_max + population_edge_buffer * pixel_size, pixel_size, pixel_size)
                final_raster = np.pad(raster, (
                    (population_edge_buffer, population_edge_buffer), (population_edge_buffer, population_edge_buffer)),
                                      mode='constant', constant_values=population_edge_buffer_value)
                final_transform = border_transform
            else:  # edge_region case
                border_height, border_width = height + 2 * population_edge_buffer, width + 2 * population_edge_buffer
                border_transform = from_origin(x_min - population_edge_buffer * pixel_size,
                                               y_max + population_edge_buffer * pixel_size, pixel_size, pixel_size)
                border_raster = np.pad(raster, (
                    (population_edge_buffer, population_edge_buffer), (population_edge_buffer, population_edge_buffer)),
                                       mode='constant', constant_values=population_edge_buffer_value)

                i, j = region
                vert_slice = slice(i * border_height // h, (i + 1) * border_height // h)
                horz_slice = slice(j * border_width // w, (j + 1) * border_width // w)

                if i == 0:  # Top edge
                    border_raster[vert_slice.start:vert_slice.start + population_edge_buffer, horz_slice] = 0
                if i == h - 1:  # Bottom edge
                    border_raster[vert_slice.stop - population_edge_buffer:vert_slice.stop, horz_slice] = 0
                if j == 0:  # Left edge
                    border_raster[vert_slice, horz_slice.start:horz_slice.start + population_edge_buffer] = 0
                if j == w - 1:  # Right edge
                    border_raster[vert_slice, horz_slice.stop - population_edge_buffer:horz_slice.stop] = 0

                final_raster = border_raster
                final_transform = border_transform

            with rasterio.open(output_raster_path, 'w', driver='GTiff', height=final_raster.shape[0],
                               width=final_raster.shape[1], count=1, dtype='float32', crs='EPSG:3310',
                               transform=final_transform) as dst:
                dst.write(final_raster, 1)
        else:
            logging.info(f"Population raster for {city_name} already exists. Skipping generation.")

        total_elapsed_time = time.time() - total_start_time
        logging.info(f"Total time for generating population raster: {total_elapsed_time:.2f} seconds")

        return output_raster_path

    except Exception as e:
        logging.error(f"Error in generate_population_raster: {e}")
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