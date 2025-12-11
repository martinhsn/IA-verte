import osmnx as ox
from osmnx import features
import geopandas as gpd
from shapely.geometry import Point, mapping
import folium
import requests

M2_PER_KW = 5
NASA_API = "https://power.larc.nasa.gov/api/temporal/daily/point"


def compute_dynamic_coverage(roof_l93):
    """
    Compute a dynamic coverage ratio based on building compactness.
    compactness = area / perimeter^2
    """
    area = roof_l93.geometry.area.iloc[0]
    perimeter = roof_l93.geometry.length.iloc[0]

    compacity = area / (perimeter ** 2)

    if compacity > 0.05:
        return 0.65
    elif compacity > 0.03:
        return 0.50
    else:
        return 0.35


def geocode_address(address: str):
    """Convert a French address to lat/lon using OpenStreetMap."""
    try:
        search_query = address if "France" in address else address + ", France"
        lat, lon = ox.geocode(search_query)
        return lat, lon
    except Exception:
        raise ValueError(
            f"The address '{address}' could not be precisely located by OpenStreetMap."
        )


def get_buildings(lat: float, lon: float, dist: int = 60):
    """Retrieve OSM buildings near the coordinates."""
    try:
        b = features.features_from_point((lat, lon), tags={"building": True}, dist=dist)
        buildings_poly = b[b.geometry.type.isin(["Polygon", "MultiPolygon"])]

        if buildings_poly.empty:
            return gpd.GeoDataFrame()

        return buildings_poly
    except Exception:
        return gpd.GeoDataFrame()


def select_roof(buildings: gpd.GeoDataFrame, lat: float, lon: float):
    """Select the nearest building footprint from OSM data."""
    if buildings.empty:
        raise ValueError(
            "No building detected in OSM in the immediate vicinity of this address."
        )

    buildings_l93 = buildings.to_crs(2154)

    pt_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs=4326)
    pt_l93 = pt_wgs84.to_crs(2154).iloc[0]

    distances = buildings_l93.geometry.distance(pt_l93)
    idx_nearest = distances.idxmin()

    if distances[idx_nearest] > 50:
        raise ValueError(
            "The building found is too far away (>50m). Your roof is probably not in OSM."
        )

    return buildings_l93.loc[[idx_nearest]]


def get_irradiance(lat: float, lon: float) -> float:
    """Fetch annual solar irradiance from NASA POWER API."""
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": "20130101",
        "end": "20231231",
        "format": "JSON",
    }
    try:
        r = requests.get(NASA_API, params=params, timeout=8)
        r.raise_for_status()

        data = r.json()
        vals = list(data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"].values())
        clean_vals = [v for v in vals if v > 0]

        if not clean_vals:
            raise Exception("Invalid NASA data")

        daily_avg = sum(clean_vals) / len(clean_vals)

    except Exception:
        print("Warning NASA API: issue fetching data, using fallback 3.8 kWh/m²/day.")
        daily_avg = 3.8

    return daily_avg * 365  # annual irradiance (kWh/m²/year)


def create_folium_map(roof_l93: gpd.GeoDataFrame, lat: float, lon: float) -> folium.Map:
    """Create a Folium map centered on the location with roof outline."""
    def style_roof(_):
        return {
            "color": "#FF0000",
            "weight": 3,
            "fillColor": "#FF0000",
            "fillOpacity": 0.3,
        }

    m = folium.Map(location=[lat, lon], zoom_start=19, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        max_zoom=21,
    ).add_to(m)

    roof_wgs84 = roof_l93.to_crs(4326)

    folium.GeoJson(
        mapping(roof_wgs84.geometry.iloc[0]),
        style_function=style_roof,
        tooltip="Building outline (OSM)",
    ).add_to(m)

    folium.Marker(
        [lat, lon],
        tooltip="Geocoded address",
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(m)

    return m


def evaluate_address(address: str) -> dict:
    """Main function: geocode → find roof → compute basic metrics."""
    lat, lon = geocode_address(address)
    buildings = get_buildings(lat, lon)
    roof_l93 = select_roof(buildings, lat, lon)

    area = roof_l93.geometry.area.iloc[0]
    if area < 15:
        raise ValueError(f"The building found is too small ({area:.0f} m²).")

    coverage_ratio = compute_dynamic_coverage(roof_l93)
    exploitable = area * coverage_ratio

    kwp = exploitable / M2_PER_KW
    irr_annual = get_irradiance(lat, lon)

    return {
        "lat": lat,
        "lon": lon,
        "roof": roof_l93,
        "area_m2": area,
        "coverage_ratio": coverage_ratio,
        "exploitable_m2": exploitable,
        "kwp": kwp,
        "irr_annual": irr_annual,
    }
