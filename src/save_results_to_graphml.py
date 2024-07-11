import osmnx as ox
import geopandas as gpd
import rasterio
import numpy as np
import os
import shutil
import time
import warnings
import pandas as pd
import logging

def sample_raster_values(gdf, raster_path, attribute_name):
    if not os.path.exists(raster_path):
        raise FileNotFoundError(f"{raster_path} not found.")
    with rasterio.open(raster_path) as src:
        gdf[attribute_name] = np.nan  # Initialize column with NaN values
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=pd.errors.PerformanceWarning)
            for idx, row in gdf.iterrows():
                coords = list(row.geometry.coords)
                raster_values = []
                for x, y in coords:
                    try:
                        row, col = src.index(x, y)
                        raster_values.append(src.read(1)[row, col])
                    except IndexError:
                        continue
                gdf.loc[idx, attribute_name] = np.mean(raster_values) if raster_values else np.nan

def save_results_to_graphml(city_name, graph_path_with_capacity, omniscape_output_path, radius,
                            block_size, threads, pixel_size, region, edge_buffer, edge_buffer_value,
                            conductance_raster_edge_buffer, case_folder):
    total_start_time = time.time()

    logging.info("Loading the graph from the GraphML file...")
    G = ox.load_graphml(graph_path_with_capacity)
    nodes, edges = ox.graph_to_gdfs(G, nodes=True, edges=True)

    logging.info("Converting graph to GeoDataFrames and reprojecting...")
    nodes = nodes.to_crs(epsg=3310)
    edges = edges.to_crs(epsg=3310)

    region_str = "full" if region is None else f"{region[0]}_{region[1]}"

    raster_files = {
        "cum_currmap.tif": "cum_flow",
        "flow_potential.tif": "flow_pot",
        "normalized_cum_currmap.tif": "norm_flow"
    }

    for raster_filename, attr_name in raster_files.items():
        raster_path = os.path.join(omniscape_output_path, raster_filename)
        logging.info(f"Sampling raster values for {raster_filename}...")
        sample_raster_values(nodes, raster_path, attr_name)
        sample_raster_values(edges, raster_path, attr_name)

    nodes = nodes.to_crs(epsg=4326)
    edges = edges.to_crs(epsg=4326)

    output_path = os.path.join(case_folder,
                               f"{city_name}_network_r{radius}_bs{block_size}_t{threads}_ps{pixel_size}_region{region_str}.gpkg")
    edges.to_file(output_path, layer='edges', driver='GPKG')
    nodes.to_file(output_path, layer='nodes', driver='GPKG')

    updated_graph = ox.graph_from_gdfs(nodes, edges)
    graphml_output_path = os.path.join(case_folder,
                                       f"{city_name}_network_r{radius}_bs{block_size}_t{threads}_ps{pixel_size}_region{region_str}.graphml")
    ox.save_graphml(updated_graph, graphml_output_path)

    for raster_filename in raster_files.keys():
        original_path = os.path.join(omniscape_output_path, raster_filename)
        new_filename = f"{os.path.splitext(raster_filename)[0]}_r{radius}_bs{block_size}_t{threads}_ps{pixel_size}_region{region_str}.tif"
        new_path = os.path.join(case_folder, new_filename)
        if os.path.exists(original_path):
            shutil.copy(original_path, new_path)

    shutil.copy(os.path.join(omniscape_output_path, "config.ini"), case_folder)

    logging.info(f"Processes completed, outputs are in: {case_folder}")

    total_elapsed_time = time.time() - total_start_time
    logging.info(f"Total time for saving results to GraphML: {total_elapsed_time:.2f} seconds")

    return case_folder