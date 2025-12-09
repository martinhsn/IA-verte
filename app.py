import streamlit as st
from streamlit_folium import st_folium
from solar_roi_france import evaluate_address, create_folium_map

# --- Page config ---
st.set_page_config(page_title="Solar AI Project", layout="centered")

st.title("🌞 Solar Potential Estimation – Green AI Project")

# --- Session State ---
if "results" not in st.session_state:
    st.session_state["results"] = None
if "error_message" not in st.session_state:
    st.session_state["error_message"] = None

# --- User Input ---
address = st.text_input("Enter an address in France:", "12 Rue Victor Hugo, Lyon")

# --- Analysis Button ---
if st.button("Analyze 🚀", type="primary"):
    st.session_state["results"] = None
    st.session_state["error_message"] = None
    
    with st.spinner("🔍 Searching address and analyzing OSM data..."):
        try:
            analysis_results = evaluate_address(address)
            st.session_state["results"] = analysis_results
        except Exception as e:
            st.session_state["error_message"] = (
                f"Oops! Analysis failed for this address.\n\nDetails: {e}"
            )

# --- Display Results or Error ---
if st.session_state["error_message"]:
    st.error(st.session_state["error_message"], icon="❌")

elif st.session_state["results"]:
    results = st.session_state["results"]
    st.success("Analysis completed successfully!", icon="✅")

    st.subheader("🛰️ Satellite View & Detected OSM Building Outline")
    st.info(
        "Note: The red outline comes from OpenStreetMap data. Accuracy depends on local contributions.",
        icon="ℹ️"
    )

    # Display Map
    try:
        folium_map = create_folium_map(results["roof"], results["lat"], results["lon"])
        st_folium(folium_map, width=700, height=450, key="result_map")
    except Exception as e:
        st.warning(f"Unable to display the map: {e}")

    # --- Metrics ---
    col1, col2 = st.columns(2)

    # LEFT COLUMN
    with col1:
        st.subheader("🏠 Detected Roof (OSM)")

        # Footprint
        st.metric("Footprint Area", f"{results['area_m2']:,.0f} m²")

        # Coverage Ratio %
        coverage_percent = results["coverage_ratio"] * 100
        st.metric("Coverage Ratio Used", f"{coverage_percent:.0f}%")

        # Clear explanatory sentence
        

        # Usable area and system size
        st.metric("Usable Area", f"{results['exploitable_m2']:,.0f} m²")
        st.metric("Recommended System Size", f"{results['kwp']:.1f} kWp")

    # RIGHT COLUMN
    with col2:
        st.subheader("⚡ Estimated Potential *(Estimation Only)*")
        st.metric("Annual Production", f"{results['annual_energy_kwh']:,.0f} kWh/year")
        st.metric(
            "CO₂ Savings",
            f"{results['co2_tonnes']:.2f} tCO₂/year",
            delta="Positive for the planet"
        )
        st.metric(
            "Estimated Financial Savings",
            f"{results['annual_savings_eur']:,.0f} €/year",
            delta="Potential gain"
        )

    # --- Explanation Section ---
    st.markdown("---")

    with st.expander("ℹ️ Understand These Results (Details & Assumptions)"):
        st.markdown("### 1. Standard Assumptions")
        st.markdown(
            f"""
            These estimates use standard photovoltaic assumptions:

            * **Dynamic coverage ratio detected:** **{coverage_percent:.0f}%**
            * **Panel efficiency:** 18%
            * **Performance ratio:** 0.75
            * **Electricity price:** 0.20 €/kWh
            """
        )

        st.markdown("### 2. Step-by-Step Calculations")

        area = results['area_m2']
        exploitable = results['exploitable_m2']
        irr = results['irr_annual']
        energy = results['annual_energy_kwh']
        savings = results['annual_savings_eur']

        # A. Surface
        st.markdown("**A. Usable Surface Area**")
        st.caption("The dynamic coverage ratio depends on roof shape and complexity.")
        st.latex(
            f"{area:.0f} \\text{{ m}}^2 \\times {results['coverage_ratio']:.2f} = "
            f"\\mathbf{{{exploitable:.0f} \\text{{ m}}^2}}"
        )

        # B. Irradiance
        st.markdown("**B. Local Solar Irradiance (NASA Data)**")
        st.write(
            f"For coordinates ({results['lat']:.3f}, {results['lon']:.3f}), "
            "the annual irradiance is:"
        )
        st.latex(
            f"\\approx \\mathbf{{{irr:.0f} \\text{{ kWh}}/\\text{{m}}^2/\\text{{yr}}}}"
        )

        # C. Production
        st.markdown("**C. Estimated Electricity Production**")
        st.caption("Formula: Surface × Irradiance × Efficiency × Performance")
        st.latex(
            f"{exploitable:.0f} \\times {irr:.0f} \\times 0.18 \\times 0.75 "
            f"\\approx \\mathbf{{{energy:,.0f} \\text{{ kWh/yr}}}}"
        )

        # D. Financial Savings
        st.markdown("**D. Estimated Financial Benefit**")
        st.latex(
            f"{energy:,.0f} \\text{{ kWh}} \\times 0.20 \\text{{ €}} "
            f"\\approx \\mathbf{{{savings:,.0f} \\text{{ €/yr}}}}"
        )

        st.info(
            "💡 **Note:** This is a simplified model. A real assessment also considers "
            "roof orientation, tilt, shading, and installation constraints."
        )
