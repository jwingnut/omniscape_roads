import requests
import geopandas as gpd
import pandas as pd

def fetch_acs_block_group_data(api_key, state, county):
    url = f"https://api.census.gov/data/2019/acs/acs5"
    params = {
        'get': 'B25044_001E,B25044_002E,B25044_003E,B25044_004E,B25044_005E,B25044_006E,B25044_007E,B01003_001E',
        'for': f'block group:*',
        'in': f'state:{state} county:{county}',
        'key': api_key
    }
    response = requests.get(url, params=params)
    data = response.json()

    columns = data[0]
    df = pd.DataFrame(data[1:], columns=columns)

    return df

def fetch_block_group_geometries(state, county):
    url = f"https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/8/query"
    params = {
        'where': f"STATE='{state}' AND COUNTY='{county}'",
        'outFields': '*',
        'returnGeometry': 'true',
        'f': 'geojson',
    }
    response = requests.get(url, params=params)
    data = response.json()

    gdf = gpd.GeoDataFrame.from_features(data['features'], crs='EPSG:4326')
    return gdf