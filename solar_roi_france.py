import osmnx as ox
from osmnx import features, projection
import requests
from shapely.geometry import Point
import math

# API NASA POWER (pour obtenir l'irradiance journalière)
NASA_API_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Variables économiques (à mettre à jour régulièrement)
PANEL_EFFICIENCY = 0.18     # rendement panneaux
PERFORMANCE_RATIO = 0.75    # pertes système (câbles, onduleur…)

# Utilise OSM pour retourner le point coordonnées d'une adresse (lat, lon)
def geocode_address(address: str):
    try:
        lat, lon = ox.geocode(address + ", France")
        return lat, lon
    except Exception as e:
        raise RuntimeError(f"Impossible de géocoder l'adresse : {address}\n{e}")

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

def economic_analysis(area_m2: float):
    # En moyenne besoin de 1000kWh par m2 par an
    tot_kwh_needed = area_m2 * 1000
    # En moyenne 1kWc produit 1200kWh par an
    tot_kwc_needed = tot_kwh_needed / 1200

    print(f"   → Production annuelle nécessaire estimée : {tot_kwh_needed:.0f} kWh/an")
    print(f"   → Besoin : {tot_kwc_needed:.0f} kWc")

    # Coût d'installation du kWc (€/kWc adapté approximativement selon la quantité de kWc installés)
    COST_PER_KWC = 1200 + (3/tot_kwc_needed) * 1800
    investment = tot_kwc_needed * COST_PER_KWC

    print(f"   → Prix du kWc : {COST_PER_KWC:.0f} €")

    # Économies annuelles
    annual_savings = tot_kwh_needed * 0.21  # Prix électricité (~0.21 €/kWh TTC en 2025)
    if annual_savings <= 0:
        payback = None
    else:
        payback = investment / annual_savings

    # Classification
    if payback is None or payback > 25:  # durée de vie de 25 ans en moyenne
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


def evaluate_address(address: str):
    print(f"\n🔎 Évaluation pour l'adresse : {address}")

    # 1) Géocodage
    lat, lon = geocode_address(address)
    print(f"   → Coordonnées : lat={lat:.5f}, lon={lon:.5f}")

    # 2) Bâtiments
    buildings = get_buildings_around(lat, lon, dist=80)
    if buildings.empty:
        raise RuntimeError("Aucun bâtiment trouvé à proximité. Essaie avec une autre adresse.")
    roof, buildings_proj = select_roof_and_project(buildings, lat, lon)
    area_m2 = roof.geometry.area.iloc[0]  # Toit le plus proche du point d'adresse (soit l'adresse visée)
    '''
    Dans un idéal proche de l'impossible il faudrait connaître la surface intérieure exacte,
    alors pour faire une approximation on pourrait commencer par connaître le nombre d'étage(s)
    (maison ~= 2 ou appartement ~= 1)
    Idée : déterminer la localistaion en fonction du nombre de voisins, s'il est < 30 -> campagne
    -> maison -> 2 étages, sinon ça veut dire que c'est dense -> ville -> appartement -> 1 étage
    (théorie approuvée avec des tests, forcément des exceptions, mais elles impacteront moins négativement
    l'estimation que l'approximation du nombre d'étages)
    '''
    # Seuil arbitraire : moins de 30 bâtiments alentour = campagne
    if len(buildings_proj) < 30:
        area_m2 *= 2
    print(f"   → {len(buildings_proj)} bâtiments détectés dans les 80m")
    print(f"   → Surface estimée : {area_m2:.1f} m²")

    # 3) Ombre
    shade = compute_shade_factor(buildings_proj, roof, buffer_m=40)
    print(f"   → Facteur d'ombre ≈ {shade:.2f}")

    # 4) Irradiance
    irr_daily = get_solar_irradiance(lat, lon)
    print(f"   → Irradiance moyenne (NASA) : {irr_daily:.2f} kWh/m²/jour")

    # 5) Économie et rentabilité
    investment, payback, label = economic_analysis(area_m2)

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
        # "annual_energy_kwh": annual_energy, (à mettre à jour avec nouveau calcul)
        "investment_eur": investment,
        "payback_years": payback,
        "decision": label,
    }

if __name__ == "__main__":
    print("=== Évaluation solaire (France) ===")
    addr = input("Entrez une adresse (ex: '10 Rue de Rivoli, Paris') : ")
    try:
        result = evaluate_address(addr)
    except Exception as e:
        print("\n❌ Erreur pendant l'évaluation :", e)
