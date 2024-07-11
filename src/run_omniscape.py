import os
import time
import logging
import subprocess
import glob
from omniscape_utils import create_ini_file

def run_omniscape(city_name, source_raster_path, conductance_raster_path, condition_raster_path,
                  threads, radius, block_size, pixel_size, edge_buffer, edge_buffer_value,
                  conductance_raster_edge_buffer, case_folder):
    total_start_time = time.time()

    ini_path = create_ini_file(case_folder, city_name, source_raster_path, conductance_raster_path,
                               condition_raster_path, threads, radius, block_size, pixel_size, edge_buffer,
                               edge_buffer_value, conductance_raster_edge_buffer)

    logging.info(f"Created INI file at: {ini_path}")
    with open(ini_path, 'r') as f:
        logging.info(f"INI file contents:\n{f.read()}")

    logging.info(f"Running Omniscape for {city_name} in {case_folder}")

    julia_command = f"using Omniscape; run_omniscape(\"{ini_path}\")"
    logging.info(f"Executing Julia command: {julia_command}")

    env = os.environ.copy()
    env["JULIA_NUM_THREADS"] = str(threads)

    subprocess.run(["julia", "-e", julia_command], cwd=case_folder, env=env)

    project_name = f"{city_name}_pix{pixel_size}_eb{edge_buffer}_ebv{edge_buffer_value}_ceb{conductance_raster_edge_buffer}_r{radius}_bs{block_size}_t{threads}"

    # Look for the most recently created directory that matches the pattern
    matching_dirs = glob.glob(os.path.join(case_folder, f"{project_name}*"))
    if matching_dirs:
        output_dir = max(matching_dirs, key=os.path.getctime)
        logging.info(f"Found Omniscape output directory: {output_dir}")
        required_files = ['cum_currmap.tif', 'flow_potential.tif', 'normalized_cum_currmap.tif']
        missing_files = [f for f in required_files if not os.path.exists(os.path.join(output_dir, f))]
        if missing_files:
            logging.error(f"Missing files in output directory: {', '.join(missing_files)}")
            logging.error(f"Contents of output directory: {os.listdir(output_dir)}")
        else:
            logging.info(f"All required Omniscape output files are present in: {output_dir}")
            return output_dir
    else:
        logging.error(f"No matching output directory found in: {case_folder}")
        logging.error(f"Contents of case folder: {os.listdir(case_folder)}")

    logging.error("Failed to locate or create the Omniscape output directory.")
    return None