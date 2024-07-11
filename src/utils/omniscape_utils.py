import os

def create_ini_file(case_folder, city_name, source_raster_path, conductance_raster_path, condition_raster_path,
                    threads, radius, block_size, pixel_size, edge_buffer, edge_buffer_value, conductance_raster_edge_buffer):
    ini_content = f"""
[Options]
project_name = {city_name}_pix{pixel_size}_eb{edge_buffer}_ebv{edge_buffer_value}_ceb{conductance_raster_edge_buffer}_r{radius}_bs{block_size}_t{threads}
resistance_file = {conductance_raster_path}
source_file = {source_raster_path}
condition1_file = {condition_raster_path}
radius = {radius}
block_size = {block_size}
calc_flow_potential = true
calc_normalized_current = true
parallelize = true
solver = cholmod
resistance_is_conductance = true
write_raw_currmap = true
write_as_tif = true

[Conditional Connectivity Options]
conditional = true
n_conditions = 1
comparison1 = equal
    """
    ini_path = os.path.join(case_folder, "omniscape_config.ini")
    with open(ini_path, "w") as f:
        f.write(ini_content)
    return ini_path