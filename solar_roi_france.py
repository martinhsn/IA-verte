import osmnx as ox
from osmnx import features
import geopandas as gpd
from shapely.geometry import Point, mapping
import folium
import requests

# Constantes ( inchangées)
COVERAGE_RATIO = 0.5
PANEL_EFFICIENCY = 0.18
PERFORMANCE_RATIO = 0.75
M2_PER_KW = 5
CO2_PER_KWH = 0.08
ELECTRICITY_PRICE = 0.20
NASA_API = "https://power.larc.nasa.gov/api/temporal/daily/point"


def geocode_address(address: str):
    """Tente de géocoder l'adresse. Lève une erreur explicite si échec."""
    try:
        # On ajoute France pour aider le géocodeur
        search_query = address if "France" in address else address + ", France"
        lat, lon = ox.geocode(search_query)
        return lat, lon
    except Exception:
        # Si OSMnx ne trouve pas, on lève une ValueError avec un message clair
        raise ValueError(f"L'adresse '{address}' n'a pas pu être localisée précisément par OpenStreetMap.")


def get_buildings(lat: float, lon: float, dist: int = 60):
    """Récupère les bâtiments autour du point. Rayon réduit à 60m."""
    try:
        # On utilise tags={"building": True} qui est plus robuste
        b = features.features_from_point((lat, lon), tags={"building": True}, dist=dist)
        # On ne garde que les polygones (pas les points ou lignes)
        buildings_poly = b[b.geometry.type.isin(["Polygon", "MultiPolygon"])]
        
        if buildings_poly.empty:
             # Si la requête marche mais ne retourne aucun polygone
             return gpd.GeoDataFrame()
             
        return buildings_poly
    except Exception:
        # Si la requête OSM échoue complètement (ex: timeout, zone vide)
        return gpd.GeoDataFrame()


def select_roof(buildings: gpd.GeoDataFrame, lat: float, lon: float):
    """Sélectionne le bâtiment le plus proche du point central."""
    
    # VÉRIFICATION CRITIQUE : Si aucun bâtiment n'a été trouvé
    if buildings.empty:
        raise ValueError("Aucune donnée de bâtiment (polygone) trouvée dans OpenStreetMap à proximité immédiate de cette adresse.")

    # Projection métrique (Lambert 93 France) pour des calculs de distance précis
    buildings_l93 = buildings.to_crs(2154)
    
    # Création du point central et projection en L93
    pt_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs=4326)
    pt_l93 = pt_wgs84.to_crs(2154).iloc[0]

    # Trouver l'index du bâtiment le plus proche du point
    distances = buildings_l93.geometry.distance(pt_l93)
    idx_nearest = distances.idxmin()
    
    # Vérification de sécurité : si le bâtiment "le plus proche" est trop loin (> 50m)
    # Cela évite de sélectionner la maison du voisin si la nôtre n'est pas dans OSM.
    if distances[idx_nearest] > 50:
         raise ValueError("Un bâtiment a été trouvé, mais il est trop éloigné du point d'adresse exact (>50m). Il est probable que votre bâtiment ne soit pas cartographié dans OSM.")

    # On retourne le GeoDataFrame contenant uniquement le bâtiment sélectionné
    return buildings_l93.loc[[idx_nearest]]


def get_irradiance(lat: float, lon: float) -> float:
    """Récupère les données NASA avec un timeout pour ne pas bloquer l'app."""
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
        # Ajout d'un timeout de 8 secondes pour ne pas faire attendre l'utilisateur
        r = requests.get(NASA_API, params=params, timeout=8)
        r.raise_for_status() # Lève une erreur si le code HTTP n'est pas 200 OK
        
        data = r.json()
        vals = list(data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"].values())
        # Nettoyage des valeurs manquantes (parfois -999 chez la NASA)
        clean_vals = [v for v in vals if v > 0]
        
        if not clean_vals: raise Exception("Pas de données valides NASA")
        
        daily_avg = sum(clean_vals) / len(clean_vals)
        
    except Exception as e:
        print(f"Warning NASA API: {e}. Utilisation de la valeur par défaut.")
        daily_avg = 3.8 # Valeur moyenne par défaut en France si l'API échoue

    return daily_avg * 365  # kWh/m²/an


def create_folium_map(roof_l93: gpd.GeoDataFrame, lat: float, lon: float) -> folium.Map:
    # Zoom initial fort pour bien voir la maison
    m = folium.Map(location=[lat, lon], zoom_start=19, tiles=None)

    # Fond de carte satellite ESRI (souvent plus joli que Google)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satellite",
        max_zoom=21
    ).add_to(m)

    # IMPORTANT : Reprojeter le toit de L93 (métrique) vers WGS84 (GPS) pour Folium
    roof_wgs84 = roof_l93.to_crs(4326)

    folium.GeoJson(
        mapping(roof_wgs84.geometry.iloc[0]),
        style_function=lambda x: {
            "color": "#FF0000",   # Rouge vif pour le contour
            "weight": 3, 
            "fillColor": "#FF0000", 
            "fillOpacity": 0.3    # Remplissage léger
        },
        tooltip="Contour du bâtiment (Données OpenStreetMap)"
    ).add_to(m)
    
    # Ajouter un marqueur sur le point d'adresse exact
    folium.Marker(
        [lat, lon],
        tooltip="Point d'adresse exact géocodé",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)

    return m


def evaluate_address(address: str) -> dict:
    """Fonction principale orchestrant le processus."""
    
    # 1. Géocodage (peut lever une erreur)
    lat, lon = geocode_address(address)
    
    # 2. Récupération des bâtiments (peut retourner vide)
    buildings = get_buildings(lat, lon)
    
    # 3. Sélection du toit (peut lever une erreur si buildings est vide ou trop loin)
    roof_l93 = select_roof(buildings, lat, lon)

    # --- Calculs ---
    # roof_l93 est en EPSG:2154, l'aire est donc en mètres carrés réels
    area = roof_l93.geometry.area.iloc[0]
    
    # Si la surface est ridiculement petite (ex: < 10m²), c'est probablement une erreur de donnée OSM (ex: un abri de jardin)
    if area < 15:
         raise ValueError(f"Le bâtiment trouvé est trop petit ({area:.0f}m²) pour une installation solaire viable selon les données OSM.")

    exploitable = area * COVERAGE_RATIO
    kwp = exploitable / M2_PER_KW

    irr_annual = get_irradiance(lat, lon)
    annual_energy = exploitable * irr_annual * PANEL_EFFICIENCY * PERFORMANCE_RATIO

    co2_tonnes = (annual_energy * CO2_PER_KWH) / 1000
    savings = annual_energy * ELECTRICITY_PRICE

    # On renvoie les données brutes. PAS de folium map ici pour éviter les soucis de SessionState.
    return {
        "lat": lat,
        "lon": lon,
        "roof": roof_l93, # On garde le GeoDataFrame en L93
        "area_m2": area,
        "exploitable_m2": exploitable,
        "kwp": kwp,
        "irr_annual": irr_annual,
        "annual_energy_kwh": annual_energy,
        "co2_tonnes": co2_tonnes,
        "annual_savings_eur": savings,
    }