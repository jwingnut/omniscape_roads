import os
import rasterio
import numpy as np
import glob


def generate_condition_raster(city_name, pixel_size, edge_buffer, case_folder):
    output_raster_path = os.path.join(case_folder, f"{city_name}_condition_{pixel_size}m_buffer{edge_buffer}.tif")

    if not os.path.exists(output_raster_path):
        # Use the source raster (population or vehicle) to get the dimensions
        source_raster_path = os.path.join(case_folder, f"{city_name}_*_{pixel_size}m_buffer{edge_buffer}.tif")
        source_raster_path = glob.glob(source_raster_path)[0]  # Get the first match

        with rasterio.open(source_raster_path) as src:
            source_raster = src.read(1)
            transform = src.transform
            crs = src.crs

        condition_raster = np.ones_like(source_raster, dtype=np.int8)

        buffer_pixels = int(edge_buffer / pixel_size)
        condition_raster[:buffer_pixels, :] = 2
        condition_raster[-buffer_pixels:, :] = 2
        condition_raster[:, :buffer_pixels] = 2
        condition_raster[:, -buffer_pixels:] = 2

        with rasterio.open(output_raster_path, 'w', driver='GTiff', height=condition_raster.shape[0],
                           width=condition_raster.shape[1], count=1, dtype='int8', crs=crs, transform=transform) as dst:
            dst.write(condition_raster, 1)

    return output_raster_path