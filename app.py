import streamlit as st
from streamlit_folium import st_folium
# Assure-toi que les imports sont corrects selon tes noms de fichiers
from solar_roi_france import evaluate_address, create_folium_map

# --- Configuration de la page (doit être au tout début) ---
st.set_page_config(page_title="Solar AI Project", layout="centered")

st.title("🌞 Estimation Solaire – Projet Green IA")

# --- Initialisation du Session State ---
if "results" not in st.session_state:
    st.session_state["results"] = None
if "error_message" not in st.session_state:
    st.session_state["error_message"] = None

# --- Interface utilisateur ---
address = st.text_input("Entrez une adresse en France :", "12 Rue Victor Hugo, Lyon")

# --- Logique du bouton Analyser ---
if st.button("Analyser 🚀", type="primary"):
    # 1. Nettoyage de l'état précédent
    st.session_state["results"] = None
    st.session_state["error_message"] = None
    
    with st.spinner('🔍 Recherche de l\'adresse et analyse des données OSM...'):
        try:
            # 2. Analyse
            analysis_results = evaluate_address(address)
            st.session_state["results"] = analysis_results
            
        except Exception as e:
            # 3. Gestion d'erreur
            st.session_state["error_message"] = f"Oups ! Analyse impossible pour cette adresse. \n\nDétails : {e}"


# --- Affichage des résultats OU de l'erreur ---

if st.session_state["error_message"]:
    st.error(st.session_state["error_message"], icon="❌")

elif st.session_state["results"]:
    results = st.session_state["results"]
    st.success("Analyse terminée avec succès !", icon="✅")

    st.subheader("🛰️ Vue satellite et contour OSM détecté")
    st.info("Note : Le contour rouge provient des données OpenStreetMap. Sa précision dépend de la qualité des contributions locales.", icon="ℹ️")

    # Affichage de la carte
    try:
        folium_map = create_folium_map(
            results["roof"],
            results["lat"],
            results["lon"],
        )
        st_folium(folium_map, width=700, height=450, key="result_map")
    except Exception as e:
         st.warning(f"Impossible d'afficher la carte : {e}")


    # --- Affichage des Métriques (Colonnes) ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏠 Toit détecté (OSM)")
        st.metric("Surface au sol", f"{results['area_m2']:.0f} m²")
        st.metric("Surface exploitable (est. 50%)", f"{results['exploitable_m2']:.0f} m²")
        st.metric("Puissance recommandée", f"{results['kwp']:.1f} kWc")

    with col2:
        st.subheader("⚡ Potentiel estimé")
        st.metric("Production annuelle", f"{results['annual_energy_kwh']:.0f} kWh/an")
        st.metric("Économie CO₂", f"{results['co2_tonnes']:.2f} t/an", delta="Positif pour la planète")
        st.metric("Économie financière (brute)", f"{results['annual_savings_eur']:.0f} €/an", delta="Gain potentiel")

    # --- NOUVELLE SECTION : DÉTAILS DES CALCULS ---
    st.markdown("---")
    
    with st.expander("ℹ️ Comprendre ces résultats (Détails des calculs & Hypothèses)"):
        st.markdown("### 1. Hypothèses standard")
        st.markdown("""
        Pour ces estimations, nous utilisons des moyennes standards du marché français :
        * **Ratio de couverture :** Nous estimons que seulement **50%** de la surface du toit est exploitable.
        * **Efficacité des panneaux :** **18%** (panneaux standards actuels).
        * **Ratio de performance (PR) :** **0.75** (pertes système).
        * **Prix de l'électricité :** **0.20 €/kWh**.
        """)

        st.markdown("### 2. Le calcul pas à pas pour votre toit")
        
        # Récupération des variables pour l'affichage
        area = results['area_m2']
        exploitable = results['exploitable_m2']
        irr = results['irr_annual']
        energy = results['annual_energy_kwh']
        savings = results['annual_savings_eur']
        
        # A. Surface exploitable
        st.markdown("**A. Surface exploitable**")
        st.caption("On ne couvre jamais 100% d'un toit (cheminées, bords, ombres).")
        # st.latex force l'affichage mathématique propre
        # Note : On utilise des doubles accolades {{ }} pour que Python comprenne que c'est du LaTeX
        st.latex(f"{area:.0f} \\text{{ m}}^2 \\times 0.50 = \\mathbf{{{exploitable:.0f} \\text{{ m}}^2}}")
        
        # B. Ensoleillement
        st.markdown("**B. Ensoleillement local (Données NASA)**")
        st.write(f"Pour vos coordonnées ({results['lat']:.3f}, {results['lon']:.3f}), l'irradiation solaire moyenne est de :")
        st.latex(f"\\approx \\mathbf{{{irr:.0f} \\text{{ kWh}}/\\text{{m}}^2/\\text{{an}}}}")
        
        # C. Production
        st.markdown("**C. Production électrique estimée**")
        st.caption("Formule : Surface × Ensoleillement × Efficacité × Performance")
        st.latex(f"{exploitable:.0f} \\times {irr:.0f} \\times 0.18 \\times 0.75 \\approx \\mathbf{{{energy:.0f} \\text{{ kWh/an}}}}")
        
        # D. Économies
        st.markdown("**D. Économies financières**")
        st.latex(f"{energy:.0f} \\text{{ kWh}} \\times 0.20 \\text{{ €}} \\approx \\mathbf{{{savings:.0f} \\text{{ €/an}}}}")

        st.info("💡 **Note :** Ce calcul est une approximation linéaire. Une étude réelle prendrait en compte l'inclinaison exacte du toit et les ombres portées.")