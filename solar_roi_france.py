import osmnx as ox
from osmnx import features
import geopandas as gpd
from shapely.geometry import Point, mapping
import folium
import requests

# Constantes (inchangées)
PANEL_EFFICIENCY = 0.18
PERFORMANCE_RATIO = 0.75
M2_PER_KW = 5
CO2_PER_KWH = 0.08
ELECTRICITY_PRICE = 0.20
NASA_API = "https://power.larc.nasa.gov/api/temporal/daily/point"


# ---------------------------
# 1. COVERAGE RATIO DYNAMIQUE
# ---------------------------
def compute_dynamic_coverage(roof_l93):
    """
    Calcule un ratio de couverture dynamique basé sur la compacité du bâtiment.
    compacité = aire / périmètre²
    """
    area = roof_l93.geometry.area.iloc[0]
    perimeter = roof_l93.geometry.length.iloc[0]

    compacity = area / (perimeter ** 2)

    if compacity > 0.05:
        return 0.65   # toit simple / compact
    elif compacity > 0.03:
        return 0.50   # cas standard
    else:
        return 0.35   # forme complexe (L, T, découpes)


# ---------------------------
# 2. GÉOCODAGE
# ---------------------------
def geocode_address(address: str):
    try:
        search_query = address if "France" in address else address + ", France"
        lat, lon = ox.geocode(search_query)
        return lat, lon
    except Exception:
        raise ValueError(f"L'adresse '{address}' n'a pas pu être localisée précisément par OpenStreetMap.")


# ---------------------------
# 3. RÉCUPÉRATION DES BÂTIMENTS
# ---------------------------
def get_buildings(lat: float, lon: float, dist: int = 60):
    try:
        b = features.features_from_point((lat, lon), tags={"building": True}, dist=dist)
        buildings_poly = b[b.geometry.type.isin(["Polygon", "MultiPolygon"])]
        
        if buildings_poly.empty:
            return gpd.GeoDataFrame()
             
        return buildings_poly
    except Exception:
        return gpd.GeoDataFrame()


# ---------------------------
# 4. SÉLECTION DU TOIT
# ---------------------------
def select_roof(buildings: gpd.GeoDataFrame, lat: float, lon: float):
    if buildings.empty:
        raise ValueError("Aucun bâtiment détecté dans OSM à proximité immédiate de cette adresse.")

    buildings_l93 = buildings.to_crs(2154)

    pt_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs=4326)
    pt_l93 = pt_wgs84.to_crs(2154).iloc[0]

    distances = buildings_l93.geometry.distance(pt_l93)
    idx_nearest = distances.idxmin()
    
    if distances[idx_nearest] > 50:
        raise ValueError("Le bâtiment trouvé est trop éloigné (>50m). Il est probable que votre toit ne soit pas dans OSM.")

    return buildings_l93.loc[[idx_nearest]]


# ---------------------------
# 5. IRRADIANCE NASA
# ---------------------------
def get_irradiance(lat: float, lon: float) -> float:
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
            raise Exception("Données NASA invalides")
        
        daily_avg = sum(clean_vals) / len(clean_vals)
        
    except Exception as e:
        print(f"Warning NASA API: {e}. Utilisation d'une valeur par défaut.")
        daily_avg = 3.8

    return daily_avg * 365  # kWh/m²/an


# ---------------------------
# 6. CARTE FOLIUM
# ---------------------------
def create_folium_map(roof_l93: gpd.GeoDataFrame, lat: float, lon: float) -> folium.Map:

    def style_roof(feature):
        return {
            "color": "#FF0000",
            "weight": 3,
            "fillColor": "#FF0000",
            "fillOpacity": 0.3
        }

    m = folium.Map(location=[lat, lon], zoom_start=19, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        max_zoom=21
    ).add_to(m)

    roof_wgs84 = roof_l93.to_crs(4326)

    folium.GeoJson(
        mapping(roof_wgs84.geometry.iloc[0]),
        style_function=style_roof,
        tooltip="Building outline (OSM)"
    ).add_to(m)

    folium.Marker(
        [lat, lon],
        tooltip="Geocoded address",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)

    return m


# ---------------------------
# 7. CALCUL GLOBAL
# ---------------------------
def evaluate_address(address: str) -> dict:
    
    # 1. Géocodage
    lat, lon = geocode_address(address)
    
    # 2. Bâtiments OSM
    buildings = get_buildings(lat, lon)
    
    # 3. Sélection du bon toit
    roof_l93 = select_roof(buildings, lat, lon)

    # --- Aire du toit ---
    area = roof_l93.geometry.area.iloc[0]

    if area < 15:
        raise ValueError(f"Le bâtiment trouvé est trop petit ({area:.0f} m²).")

    # --- COVERAGE DYNAMIQUE ---
    coverage_ratio = compute_dynamic_coverage(roof_l93)
    exploitable = area * coverage_ratio

    # Puissance (kWp)
    kwp = exploitable / M2_PER_KW

    # Irradiance NASA
    irr_annual = get_irradiance(lat, lon)

    # Production annuelle
    annual_energy = exploitable * irr_annual * PANEL_EFFICIENCY * PERFORMANCE_RATIO

    # CO₂ & économies
    co2_tonnes = (annual_energy * CO2_PER_KWH) / 1000
    savings = annual_energy * ELECTRICITY_PRICE

    return {
        "lat": lat,
        "lon": lon,
        "roof": roof_l93,
        "area_m2": area,
        "coverage_ratio": coverage_ratio,
        "exploitable_m2": exploitable,
        "kwp": kwp,
        "irr_annual": irr_annual,
        "annual_energy_kwh": annual_energy,
        "co2_tonnes": co2_tonnes,
        "annual_savings_eur": savings,
    }
