# -------------------------------------------------------------
# PROJET GREEN AI - Est-ce rentable d'installer des panneaux ?
# Version France / adresse postale / OSMnx 2.x / NASA POWER
# -------------------------------------------------------------

import osmnx as ox
from osmnx import features, projection
import requests
from shapely.geometry import Point
import math

# -------------------------------------------------------------
# 1) CONSTANTES GLOBALES
# -------------------------------------------------------------

# API NASA POWER (irradiance journalière)
NASA_API_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Hypothèses économiques (à adapter dans ton rapport)
COST_PER_KW = 1600          # €/kWc installé (ordre de grandeur France)
ELECTRICITY_PRICE = 0.20    # €/kWh TTC (tarif réglementé ~0.20 € en 2025)
SYSTEM_LIFETIME = 20        # années de durée de vie
COVERAGE_RATIO = 0.6        # part de la surface de toit réellement couverte
PANEL_EFFICIENCY = 0.18     # rendement panneaux
PERFORMANCE_RATIO = 0.75    # pertes système (câbles, onduleur…)


# -------------------------------------------------------------
# 2) GÉOCODAGE ADRESSE → (LAT, LON)
# -------------------------------------------------------------

def geocode_address(address: str):
    """
    Utilise OSM pour convertir une adresse en coordonnées (lat, lon)
    Retourne toujours un point → jamais d'erreur.
    """
    try:
        lat, lon = ox.geocode(address + ", France")
        return lat, lon
    except Exception as e:
        raise RuntimeError(f"Impossible de géocoder l'adresse : {address}\n{e}")



# -------------------------------------------------------------
# 3) RÉCUPÉRER BÂTIMENTS OSM AUTOUR DU POINT
# -------------------------------------------------------------

def get_buildings_around(lat: float, lon: float, dist: float = 80):
    """
    Récupère les bâtiments OSM dans un rayon `dist` (m) autour du point.
    Retourne un GeoDataFrame (peut être vide).
    """
    center = (lat, lon)
    # features_from_point(center_point, tags, dist)
    b = features.features_from_point(
        center,
        {"building": True},
        dist
    )
    # Garder uniquement Polygons / MultiPolygons
    b = b[b.geometry.type.isin(["Polygon", "MultiPolygon"])]
    return b


# -------------------------------------------------------------
# 4) SÉLECTIONNER LE TOIT LE PLUS PROCHE + PROJECTION
# -------------------------------------------------------------

def select_roof_and_project(buildings_gdf, lat: float, lon: float):
    """
    - projette tous les bâtiments en EPSG:2154 (Lambert 93, France)
    - trouve le bâtiment le plus proche du point (lat, lon)
    Retourne (roof_gdf_1row, buildings_proj).
    """
    if buildings_gdf.empty:
        raise ValueError("Aucun bâtiment trouvé à proximité de l'adresse.")

    # Projection métrique France
    buildings_proj = projection.project_gdf(buildings_gdf, to_crs="EPSG:2154")

    user_pt = Point(lon, lat)
    user_pt_proj, _ = projection.project_geometry(
        user_pt, crs="EPSG:4326", to_crs="EPSG:2154"
    )

    distances = buildings_proj.geometry.distance(user_pt_proj)
    idx_min = distances.idxmin()
    roof = buildings_proj.loc[[idx_min]]  # GeoDataFrame 1 ligne

    return roof, buildings_proj


# -------------------------------------------------------------
# 5) FACTEUR D'OMBRE (DENSITÉ BÂTIE AUTOUR DU TOIT)
# -------------------------------------------------------------

def compute_shade_factor(buildings_proj, roof, buffer_m: float = 40.0):
    """
    Approxime l'ombre à partir de la densité de bâtiments dans un buffer autour du toit.
    Renvoie un facteur entre ~0.6 (très ombragé) et 1.0 (peu d'obstacles).
    """
    roof_geom = roof.geometry.iloc[0]
    buf = roof_geom.buffer(buffer_m)

    neighbors = buildings_proj[buildings_proj.geometry.intersects(buf)]
    built_area = neighbors.geometry.area.sum() - roof_geom.area
    built_area = max(built_area, 0.0)
    ratio = built_area / buf.area  # densité bâtie

    if ratio < 0.1:
        return 1.0    # campagne, peu de masques
    elif ratio < 0.25:
        return 0.9
    elif ratio < 0.4:
        return 0.8
    else:
        return 0.65   # environnement très dense


# -------------------------------------------------------------
# 6) IRRADIANCE NASA POWER (rayonnement + nuages)
# -------------------------------------------------------------

def get_solar_irradiance(lat: float, lon: float,
                         start_year: int = 2013,
                         end_year: int = 2023) -> float:
    """
    Récupère l'irradiance solaire ALLSKY_SFC_SW_DWN (kWh/m²/jour)
    moyenne sur plusieurs années via l'API DAILY de NASA POWER.
    """
    start = f"{start_year}0101"
    end = f"{end_year}1231"

    params = {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": start,
        "end": end,
        "format": "JSON"
    }

    r = requests.get(NASA_API_DAILY, params=params, timeout=30)
    data = r.json()

    try:
        series = data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        values = list(series.values())
        if not values:
            raise ValueError("Liste vide de valeurs NASA.")
        avg_daily = sum(values) / len(values)
        return avg_daily  # kWh/m²/jour
    except Exception as e:
        print("⚠️ Problème avec l'API NASA POWER:", e)
        print("   Utilisation d'une valeur moyenne France ≈ 3.8 kWh/m²/jour")
        return 3.8


# -------------------------------------------------------------
# 7) PRODUCTION ANNUELLE ESTIMÉE
# -------------------------------------------------------------

def estimate_yearly_production(area_m2: float,
                               irr_daily: float,
                               shade_factor: float,
                               orientation_factor: float = 0.9) -> float:
    """
    Estime la production annuelle (kWh/an) d'une installation PV
    sur le toit considéré.
    """
    annual_irradiance = irr_daily * 365.0  # kWh/m²/an

    panel_area = area_m2 * COVERAGE_RATIO

    effective_irradiance = annual_irradiance * shade_factor * orientation_factor

    energy_kwh = (
        panel_area *
        effective_irradiance *
        PANEL_EFFICIENCY *
        PERFORMANCE_RATIO
    )
    return energy_kwh


# -------------------------------------------------------------
# 8) ANALYSE ÉCONOMIQUE
# -------------------------------------------------------------

def economic_analysis(annual_energy_kwh: float, area_m2: float):
    """
    Retourne (investissement estimé, temps de retour, label).
    On utilise la surface pour estimer la puissance installée,
    au lieu de relier directement le coût à l'énergie annuelle.
    """

    if annual_energy_kwh <= 0 or area_m2 <= 0:
        return None, None, "Non viable"

    # Surface réellement couverte par des panneaux
    panel_area = area_m2 * COVERAGE_RATIO  # ex: 60% du toit

    # Approximation : 1 kWc ≈ 5.5 m² de panneaux (rendement ~18%)
    M2_PER_KW = 5.5
    kwp_installed = panel_area / M2_PER_KW

    # Coût d'installation
    investment = kwp_installed * COST_PER_KW

    # Économies annuelles
    annual_savings = annual_energy_kwh * ELECTRICITY_PRICE
    if annual_savings <= 0:
        payback = None
    else:
        payback = investment / annual_savings

    # Classification
    if payback is None or payback > SYSTEM_LIFETIME:
        label = "Peu intéressant financièrement"
    elif payback < 8:
        label = "Très intéressant"
    elif payback <= 12:
        label = "Intéressant"
    elif payback <= 20:
        label = "Acceptable"
    else:
        label = "Peu intéressant financièrement"

    return investment, payback, label



# -------------------------------------------------------------
# 9) FONCTION COMPLÈTE : ADRESSE → DIAGNOSTIC
# -------------------------------------------------------------

def evaluate_address(address: str):
    """
    Pipeline complet :
    - géocode l'adresse
    - trouve le toit le plus proche
    - calcule surface, ombre
    - récupère irradiance NASA
    - estime production & rentabilité
    Retourne un dict de résultats.
    """
    print(f"\n🔎 Évaluation pour l'adresse : {address}")

    # 1) Géocodage
    lat, lon = geocode_address(address)
    print(f"   → Coordonnées : lat={lat:.5f}, lon={lon:.5f}")

    # 2) Bâtiments
    buildings = get_buildings_around(lat, lon, dist=80)
    if buildings.empty:
        raise RuntimeError("Aucun bâtiment trouvé à proximité. Essaie avec une autre adresse.")

    roof, buildings_proj = select_roof_and_project(buildings, lat, lon)
    area_m2 = roof.geometry.area.iloc[0]
    print(f"   → Surface de toit estimée : {area_m2:.1f} m²")

    # 3) Ombre
    shade = compute_shade_factor(buildings_proj, roof, buffer_m=40)
    print(f"   → Facteur d'ombre ≈ {shade:.2f}")

    # 4) Irradiance
    irr_daily = get_solar_irradiance(lat, lon)
    print(f"   → Irradiance moyenne (NASA) : {irr_daily:.2f} kWh/m²/jour")

    # 5) Production annuelle
    annual_energy = estimate_yearly_production(area_m2, irr_daily, shade)
    print(f"   → Production annuelle estimée : {annual_energy:.0f} kWh/an")

    # 6) Économie et rentabilité
    investment, payback, label = economic_analysis(annual_energy, area_m2)

    print("\n📊 Résumé économique :")
    if investment is not None:
        print(f"   - Investissement estimé : {investment:,.0f} €")
    if payback is not None:
        print(f"   - Temps de retour : {payback:.1f} ans")
    print(f"   - Conclusion : {label}")

    return {
        "lat": lat,
        "lon": lon,
        "area_m2": area_m2,
        "shade_factor": shade,
        "irradiance_daily_kwh_m2": irr_daily,
        "annual_energy_kwh": annual_energy,
        "investment_eur": investment,
        "payback_years": payback,
        "decision": label,
    }


# -------------------------------------------------------------
# 10) MAIN : TEST INTERACTIF
# -------------------------------------------------------------

if __name__ == "__main__":
    print("=== Évaluation solaire (France) ===")
    addr = input("Entrez une adresse (ex: '10 Rue de Rivoli, Paris') : ")
    try:
        result = evaluate_address(addr)
    except Exception as e:
        print("\n❌ Erreur pendant l'évaluation :", e)
