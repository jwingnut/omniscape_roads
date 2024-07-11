import os
from utils.download_graph import download_graph
from utils.add_capacity import add_capacity
import logging

def prepare_city_group(city_group, expand_distance):
    logging.info(f"Preparing city group: {city_group}")
    graph_path = download_graph(city_group, expand_distance)
    graph_path_with_capacity = add_capacity(graph_path)
    logging.info(f"Preparation completed for city group: {city_group}")
    return graph_path_with_capacity