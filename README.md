# Omniscape Outward Flow

This project uses Omniscape to model outward traffic flow from a city to its surrounding areas.

## Setup

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the main script for population-based analysis:
   ```
   python src/main.py --city_name "YourCity" --expand_distance 1000 --pixel_size 30 --edge_buffer 500 --threads 4 --radius 1000 --block_size 5
   ```
   Or for vehicle-based analysis:
   ```
   python src/main_vehicle.py --city_name "YourCity" --expand_distance 1000 --pixel_size 30 --edge_buffer 500 --threads 4 --radius 1000 --block_size 5 --census_api_key "your_api_key_here"
   ```

## Directory Structure

- `src/`: Contains the main Python scripts
- `data/`: Input and output data
- `config/`: Configuration files
- `tests/`: Unit tests

## License

[Your chosen license]
