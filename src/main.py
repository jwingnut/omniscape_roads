import argparse
import itertools
from multiprocessing import Pool
import os
import logging
import sys
from datetime import datetime
from functools import partial
from prepare_city_group import prepare_city_group
from generate_population_raster import generate_population_raster, get_regions_to_process
from generate_conductance_raster import generate_conductance_raster
from generate_condition_raster import generate_condition_raster
from run_omniscape import run_omniscape
from save_results_to_graphml import save_results_to_graphml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def create_run_folder(base_path, city_group, parameters):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    folder_name = f"{timestamp}_{city_group}_{'_'.join(f'{k}{v}' for k, v in parameters.items())}"
    run_folder = os.path.join(base_path, folder_name)
    os.makedirs(run_folder, exist_ok=True)
    return run_folder

def process_single_case(run_folder, args):
    city_group, expand_distance, pixel_size, conductance_raster_edge_buffer, population_pair, threads, radius, block_size, case_type, region, h, w = args
    population_edge_buffer, population_edge_buffer_value = population_pair

    region_str = '_'.join(map(str, region)) if region else 'full'
    case_folder = os.path.join(run_folder, f"{case_type}_{region_str}")
    os.makedirs(case_folder, exist_ok=True)

    logging.info(f"Processing: {city_group}, {case_type}, region: {region_str}")
    logging.info(f"Case folder: {case_folder}")

    try:
        graph_path_with_capacity = prepare_city_group(city_group, expand_distance)

        population_raster_path = generate_population_raster(
            city_group, pixel_size, population_edge_buffer,
            population_edge_buffer_value, region, case_type, case_folder, h, w
        )
        logging.info(f"Population raster generated: {population_raster_path}")

        conductance_raster_path = generate_conductance_raster(
            city_group, graph_path_with_capacity,
            conductance_raster_edge_buffer, pixel_size,
            population_raster_path, case_folder
        )
        logging.info(f"Conductance raster generated: {conductance_raster_path}")

        condition_raster_path = generate_condition_raster(
            city_group, pixel_size, population_edge_buffer, case_folder
        )
        logging.info(f"Condition raster generated: {condition_raster_path}")

        omniscape_output_path = run_omniscape(
            city_group, population_raster_path, conductance_raster_path, condition_raster_path,
            threads, radius, block_size, pixel_size, population_edge_buffer,
            population_edge_buffer_value, conductance_raster_edge_buffer, case_folder
        )

        if omniscape_output_path:
            logging.info(f"Successfully ran Omniscape for {case_type}, region: {region_str}")
            logging.info(f"Omniscape output path: {omniscape_output_path}")
            save_results_to_graphml(
                city_group, graph_path_with_capacity, omniscape_output_path,
                radius, block_size, threads, pixel_size, region,
                population_edge_buffer, population_edge_buffer_value, conductance_raster_edge_buffer,
                case_folder
            )
            return case_folder
        else:
            logging.error(f"Omniscape failed to generate output for {case_type}, region: {region_str}")
            return None
    except Exception as e:
        logging.error(f"Error processing {case_type}, region: {region_str} for {city_group}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Omniscape Analysis")
    parser.add_argument("--city_groups", type=str, nargs="+", required=True)
    parser.add_argument("--expand_distances", type=int, nargs="+", required=True)
    parser.add_argument("--pixel_sizes", type=int, nargs="+", required=True)
    parser.add_argument("--conductance_raster_edge_buffers", type=int, nargs="+", required=True)
    parser.add_argument("--population_edge_buffers", type=int, nargs="+", required=True)
    parser.add_argument("--population_edge_buffer_values", type=float, nargs="+", required=True)
    parser.add_argument("--threads", type=int, nargs="+", required=True)
    parser.add_argument("--radii", type=int, nargs="+", required=True)
    parser.add_argument("--block_sizes", type=int, nargs="+", required=True)
    parser.add_argument("--regions", type=int, nargs=2, required=True,
                        help="Number of horizontal and vertical divisions")
    parser.add_argument("--exit_nodes", type=str, help="Path to the exit_nodes.shp file")
    args = parser.parse_args()

    base_output_path = "/mnt/p/python_geoserver_scripts/new_omniscape/outputs"

    population_pairs = list(itertools.product(args.population_edge_buffers, args.population_edge_buffer_values))

    for params in itertools.product(
            args.city_groups,
            args.expand_distances,
            args.pixel_sizes,
            args.conductance_raster_edge_buffers,
            population_pairs,
            args.threads,
            args.radii,
            args.block_sizes
    ):
        city_group, expand_distance, pixel_size, conductance_raster_edge_buffer, population_pair, threads, radius, block_size = params

        run_parameters = {
            "pix": pixel_size,
            "ceb": conductance_raster_edge_buffer,
            "peb": population_pair[0],
            "pebv": population_pair[1],
            "r": radius,
            "bs": block_size,
            "t": threads
        }

        run_folder = create_run_folder(base_output_path, city_group, run_parameters)

        h, w = args.regions
        all_cases = [
            (city_group, expand_distance, pixel_size, conductance_raster_edge_buffer, population_pair, threads, radius,
             block_size, "base_case_no_border", None, h, w),
            (city_group, expand_distance, pixel_size, conductance_raster_edge_buffer, population_pair, threads, radius,
             block_size, "base_case_with_border", None, h, w)
        ]

        regions = get_regions_to_process(h, w, args.exit_nodes)
        for region in regions:
            all_cases.append((city_group, expand_distance, pixel_size, conductance_raster_edge_buffer, population_pair,
                              threads, radius, block_size, "edge_region", region, h, w))

        logging.info(f"Processing run with {len(all_cases)} cases")

        process_func = partial(process_single_case, run_folder)

        with Pool() as pool:
            results = pool.map(process_func, all_cases)

        successful_cases = [r for r in results if r is not None]
        logging.info(f"Completed {len(successful_cases)} out of {len(all_cases)} cases successfully")

if __name__ == "__main__":
    main()