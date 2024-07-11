import numpy as np
import rasterio
from rasterio.features import rasterize
import osmnx as ox
import time
import os
import logging

def generate_conductance_raster(city_name, graph_path_with_capacity, conductance_raster_edge_buffer, pixel_size,
                                source_raster_path, case_folder):
    output_raster_path = os.path.join(case_folder, f"{city_name}_conductance_{pixel_size}m_buffer{conductance_raster_edge_buffer}.tif")

    total_start_time = time.time()

    if not os.path.exists(output_raster_path):
        logging.info("Generating new conductance raster...")
        G = ox.load_graphml(graph_path_with_capacity)
        edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)

        edges_gdf = edges_gdf.to_crs(epsg=3310)  # California Albers
        edges_gdf['buffered_geometry'] = edges_gdf.geometry.buffer(conductance_raster_edge_buffer)
        edges_gdf['capacity'] = edges_gdf['capacity'].astype(float)

        with rasterio.open(source_raster_path) as src:
            height, width = src.shape
            transform = src.transform
            crs = src.crs

        conductance_raster = rasterize(
            [(geom, value) for geom, value in zip(edges_gdf['buffered_geometry'], edges_gdf['capacity'])],
            out_shape=(height, width),
            transform=transform,
            fill=np.nan,  # Use NaN for areas outside the network
            dtype='float32'
        )

        with rasterio.open(output_raster_path, 'w', driver='GTiff', height=height, width=width, count=1,
                           dtype='float32', crs=crs, transform=transform, nodata=np.nan) as dest:
            dest.write(conductance_raster, 1)

        logging.info(f"Generated conductance raster with shape: {conductance_raster.shape}")
        logging.info(
            f"Conductance raster min value: {np.nanmin(conductance_raster)}, max value: {np.nanmax(conductance_raster)}")
    else:
        logging.info(f"Conductance raster for {city_name} already exists. Skipping generation.")

    total_elapsed_time = time.time() - total_start_time
    logging.info(f"Total time for generating conductance raster: {total_elapsed_time:.2f} seconds")

    return output_raster_path