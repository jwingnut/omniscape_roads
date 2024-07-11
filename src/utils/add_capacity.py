import osmnx as ox
import networkx as nx
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import math
import re
import time
import os


def extract_numeric(value):
    if isinstance(value, str):
        match = re.search(r'(\d+(\.\d+)?)', value)
        if match:
            return float(match.group(1))
    elif isinstance(value, (int, float)):
        return float(value)
    return np.nan


def convert_lists_to_strings(value):
    if isinstance(value, list):
        return ', '.join(value)
    return value


def correct_speed_lanes_highway(arcs_parameters):
    # Ensuring no SettingWithCopyWarnings
    arcs_parameters = arcs_parameters.copy()
    arcs_parameters['maxspeed'] = arcs_parameters['maxspeed'].fillna('0 mph')
    arcs_parameters['lanes'] = arcs_parameters['lanes'].fillna(0)

    arcs_parameters['maxspeed'] = arcs_parameters['maxspeed'].apply(extract_numeric)
    arcs_parameters['lanes'] = pd.to_numeric(arcs_parameters['lanes'], errors='coerce', downcast='float')

    # Apply the custom function to the entire column
    arcs_parameters["highway"] = arcs_parameters["highway"].apply(convert_lists_to_strings)
    condition = (arcs_parameters['highway'] == 'unclassified')
    arcs_parameters.loc[condition, 'highway'] = 'residential'

    condition = (arcs_parameters['highway'] == 'residential, unclassified')
    arcs_parameters.loc[condition, 'highway'] = 'residential'

    condition = (arcs_parameters['highway'] == 'unclassified, residential')
    arcs_parameters.loc[condition, 'highway'] = 'residential'

    condition = (arcs_parameters['highway'] == 'residential, tertiary')
    arcs_parameters.loc[condition, 'highway'] = 'residential'

    condition = (arcs_parameters['highway'] == 'tertiary, residential')
    arcs_parameters.loc[condition, 'highway'] = 'residential'

    arcs_parameters = arcs_parameters[['highway', 'length', 'maxspeed', 'lanes', 'geometry']]

    # Define the conditions and corresponding speeds
    conditions = [
        (arcs_parameters['highway'] == 'motorway'),
        (arcs_parameters['highway'] == 'motorway link'),
        (arcs_parameters['highway'] == 'trunk'),
        (arcs_parameters['highway'] == 'trunk link'),
        (arcs_parameters['highway'] == 'primary'),
        (arcs_parameters['highway'] == 'primary link'),
        (arcs_parameters['highway'] == 'secondary'),
        (arcs_parameters['highway'] == 'tertiary'),
        (arcs_parameters['highway'] == 'minor'),
        (arcs_parameters['highway'] == 'unclassified'),
        (arcs_parameters['highway'] == 'residential'),
        (arcs_parameters['highway'] == 'living street'),
        (arcs_parameters['highway'] == 'Phantom')
    ]

    speeds = [100, 60, 50, 50, 50, 50, 50, 30, 30, 30, 30, 15, 1000]  # Corresponding speeds for the conditions km/h
    average_speed = [1.2, 1.2, 0.5, 0.5, 0.5, 0.5, 0.5, 0.8, 0.8, 0.8, 0.6, 1.0,
                     1.0]  # Corresponding speeds for the conditions
    capacity = [2000, 1500, 1000, 1000, 1000, 1000, 1000, 600, 600, 600, 600, 300, 100000]  # veh/h
    number_lanes = [2, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1000]

    # Create the 'speed' column based on the conditions
    arcs_parameters['speed'] = np.select(conditions, speeds, default=0)  # Default speed is 0 for unmatched conditions
    arcs_parameters['average_speed'] = np.select(conditions, average_speed,
                                                 default=0)  # Default speed is 0 for unmatched conditions
    arcs_parameters['capacity'] = np.select(conditions, capacity,
                                            default=0)  # Default speed is 0 for unmatched conditions
    arcs_parameters['number_lanes'] = np.select(conditions, number_lanes,
                                                default=0)  # Default speed is 0 for unmatched conditions

    arcs_parameters['max_lanes'] = arcs_parameters[['lanes', 'number_lanes']].max(axis=1)
    arcs_parameters['capacity'] = arcs_parameters['capacity'] * arcs_parameters['max_lanes']
    arcs_parameters['resistance'] = 1 / arcs_parameters['capacity'] * arcs_parameters['capacity'].max()

    return arcs_parameters


def add_capacity(graph_path):
    total_start_time = time.time()

    print("Loading graph...")
    start_time = time.time()

    graph_path_with_capacity = graph_path.replace(".graphml", "_with_capacity.graphml")

    if not os.path.exists(graph_path_with_capacity):
        G_road_network = ox.load_graphml(graph_path)
        elapsed_time = time.time() - start_time
        print(f"Loaded graph in {elapsed_time:.2f} seconds")

        print("Converting graph to GeoDataFrame...")
        start_time = time.time()
        nodes, edges = ox.graph_to_gdfs(G_road_network, nodes=True, edges=True)
        elapsed_time = time.time() - start_time
        print(f"Converted graph to GeoDataFrame in {elapsed_time:.2f} seconds")

        print("Applying capacity corrections...")
        start_time = time.time()
        edges = correct_speed_lanes_highway(edges)
        elapsed_time = time.time() - start_time
        print(f"Applied capacity corrections in {elapsed_time:.2f} seconds")

        print("Updating graph with new edge attributes...")
        start_time = time.time()
        G_road_network = ox.graph_from_gdfs(nodes, edges)
        elapsed_time = time.time() - start_time
        print(f"Updated graph in {elapsed_time:.2f} seconds")

        print("Saving updated graph...")
        start_time = time.time()
        graph_path_with_capacity = graph_path.replace(".graphml", "_with_capacity.graphml")
        ox.save_graphml(G_road_network, graph_path_with_capacity)
        elapsed_time = time.time() - start_time
        print(f"Saved updated graph in {elapsed_time:.2f} seconds")
    else:
        print(f"GraphML file with capacity for {graph_path} already exists. Skipping capacity addition.")

    total_elapsed_time = time.time() - total_start_time
    print(f"Total time for adding capacity: {total_elapsed_time:.2f} seconds")

    return graph_path_with_capacity