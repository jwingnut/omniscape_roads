import osmnx as ox
import networkx as nx
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
import time
import os

def download_and_merge_road_networks(places, expand_distance=100):
    start_time = time.time()
    G_list = []

    for place in places:
        start_time_place = time.time()
        G = ox.graph_from_place(place, network_type='drive')
        elapsed_time_place = time.time() - start_time_place
        print(f"Downloaded graph for {place} in {elapsed_time_place:.2f} seconds")
        G_list.append(G)

    elapsed_time_merge = time.time() - start_time
    print(f"Merged all graphs in {elapsed_time_merge:.2f} seconds")

    start_time_compose = time.time()
    G_merged = nx.compose_all(G_list)
    elapsed_time_compose = time.time() - start_time_compose
    print(f"Composed all graphs in {elapsed_time_compose:.2f} seconds")

    start_time_convert = time.time()
    nodes, edges = ox.graph_to_gdfs(G_merged)
    unified_gdf = gpd.GeoDataFrame(pd.concat([edges], ignore_index=True), crs=edges.crs)
    elapsed_time_convert = time.time() - start_time_convert
    print(f"Converted graph to GeoDataFrame in {elapsed_time_convert:.2f} seconds")

    start_time_bbox = time.time()
    bbox_gdf = gpd.GeoDataFrame({'geometry': [box(*unified_gdf.total_bounds)]}, crs=edges.crs)
    bbox_gdf_proj = bbox_gdf.to_crs(epsg=3310)
    expanded_bbox = bbox_gdf_proj.buffer(expand_distance).envelope
    expanded_bbox_gdf = gpd.GeoDataFrame(geometry=expanded_bbox, crs=bbox_gdf_proj.crs)
    expanded_bbox_gdf = expanded_bbox_gdf.to_crs(edges.crs)
    minx_exp, miny_exp, maxx_exp, maxy_exp = expanded_bbox_gdf.total_bounds
    bbox_tuple = (maxy_exp, miny_exp, maxx_exp, minx_exp) # North, South, East, West
    elapsed_time_bbox = time.time() - start_time_bbox
    print(f"Calculated expanded bounding box in {elapsed_time_bbox:.2f} seconds")

    start_time_retrieve = time.time()
    G_retrieved = ox.graph_from_bbox(bbox=bbox_tuple, network_type='drive', simplify=True)
    elapsed_time_retrieve = time.time() - start_time_retrieve
    print(f"Retrieved graph from expanded bounding box in {elapsed_time_retrieve:.2f} seconds")

    return G_retrieved

def download_graph(city_names, expand_distance):
    start_time = time.time()
    cities = city_names.split('_')
    city_key = '_'.join(cities)
    graph_path = f"/mnt/p/python_geoserver_scripts/new_omniscape/graphml/{city_key}/{city_key}_expand{expand_distance}_road_network.graphml"

    if not os.path.exists(graph_path):
        print(f"Initiating download for {city_key} with an expand distance of {expand_distance} meters...")

        places = [f"{city}, California, USA" for city in cities]

        start_time_download = time.time()
        G_road_network = download_and_merge_road_networks(places, expand_distance)
        elapsed_time_download = time.time() - start_time_download
        print(f"Downloaded and merged road networks in {elapsed_time_download:.2f} seconds")

        start_time_save = time.time()
        os.makedirs(os.path.dirname(graph_path), exist_ok=True)
        ox.save_graphml(G_road_network, graph_path)
        elapsed_time_save = time.time() - start_time_save
        print(f"Saved GraphML file in {elapsed_time_save:.2f} seconds")

        elapsed_time = time.time() - start_time
        print(f"Total process for {city_key} completed in {elapsed_time:.2f} seconds")

    else:
        print(f"GraphML file for {city_key} with expand distance {expand_distance} already exists. Skipping download.")

    return graph_path