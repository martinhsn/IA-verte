import streamlit as st
from streamlit_folium import st_folium
from solar_roi_france import evaluate_address, create_folium_map


# --- Page config ---
st.set_page_config(page_title="Solar AI Project", layout="centered")
st.title("Solar Potential Estimation - Green AI Project")


# --- Session State ---
if "results" not in st.session_state:
    st.session_state["results"] = None
if "error_message" not in st.session_state:
    st.session_state["error_message"] = None


# --- User Input ---
address = st.text_input("Enter an address in France:", "12 Rue Victor Hugo, Lyon")


# --- Analysis Button ---
if st.button("Analyze", type="primary"):
    st.session_state["results"] = None
    st.session_state["error_message"] = None

    with st.spinner("Searching address and analyzing OSM data..."):
        try:
            analysis_results = evaluate_address(address)
            st.session_state["results"] = analysis_results
        except Exception as e:
            st.session_state["error_message"] = (
                f"Oops! Analysis failed for this address.\n\nDetails: {e}"
            )


# --- Display Results or Error ---
if st.session_state["error_message"]:
    st.error(st.session_state["error_message"])

elif st.session_state["results"]:
    results = st.session_state["results"]
    st.success("Analysis completed successfully!")

    st.subheader("Satellite View & Detected OSM Building Outline")
    st.info(
        "Note: The red outline comes from OpenStreetMap data. Accuracy depends on local contributions."
    )

    # Display Map
    try:
        folium_map = create_folium_map(results["roof"], results["lat"], results["lon"])
        st_folium(folium_map, width=700, height=450, key="result_map")
    except Exception as e:
        st.warning(f"Unable to display the map: {e}")

    # --- User-adjustable panel coverage ---
    st.markdown("### Adjust panel coverage on usable roof area")
    coverage_slider = st.slider(
        "Panel coverage applied to the usable roof area",
        min_value=0,
        max_value=100,
        value=100,
        step=5,
        format="%d%%",
        help="Set how much of the usable roof area you plan to cover with panels.",
    )
    panel_fraction = coverage_slider / 100

    effective_coverage_ratio = results["coverage_ratio"] * panel_fraction
    effective_coverage_percent = effective_coverage_ratio * 100

    exploitable = results["exploitable_m2"] * panel_fraction
    kwp = results["kwp"] * panel_fraction
    energy = results["annual_energy_kwh"] * panel_fraction
    co2 = results["co2_tonnes"] * panel_fraction
    savings = results["annual_savings_eur"] * panel_fraction

    # --- Metrics ---
    col1, col2 = st.columns(2)

    # LEFT COLUMN
    with col1:
        st.subheader("Detected Roof (OSM)")

        st.metric("Footprint Area", f"{results['area_m2']:,.0f} m2")
        st.metric("Detected Coverage Ratio", f"{results['coverage_ratio'] * 100:.0f}%")
        st.metric("Coverage Ratio Used", f"{effective_coverage_percent:.0f}%")
        st.metric("Usable Area", f"{exploitable:,.0f} m2")
        st.metric("Recommended System Size", f"{kwp:.1f} kWp")

    # RIGHT COLUMN
    with col2:
        st.subheader("Estimated Potential (Estimation Only)")
        st.metric("Annual Production", f"{energy:,.0f} kWh/year")
        st.metric(
            "CO2 Savings",
            f"{co2:.2f} kCO2/year",
            delta="Positive for the planet",
        )
        st.metric(
            "Estimated Financial Savings",
            f"{savings:,.0f} EUR/year",
            delta="Potential gain",
        )
        cost_low = exploitable * 400
        cost_high = exploitable * 1000
        st.metric(
            "Estimated System Cost Range",
            f"{cost_low:,.0f} - {cost_high:,.0f} EUR",
            help="Based on 400 to 1000 EUR per m2 of panels."
        )

    # --- Explanation Section ---
    st.markdown("---")

    with st.expander("Understand These Results (Details & Assumptions)"):
        st.markdown("### 1. Standard Assumptions")
        st.markdown(
            f"""
            These estimates use standard photovoltaic assumptions:

            * **Dynamic coverage ratio detected:** **{results['coverage_ratio'] * 100:.0f}%**
            * **Panel coverage slider applied:** **{coverage_slider}%** (on the usable area)
            * **Panel efficiency:** 18%
            * **Performance ratio:** 0.75
            * **Electricity price:** 0.20 EUR/kWh
            * **Cost assumption:** 400–1000 EUR per m² of installed panels
            """
        )

        st.markdown("### 2. Step-by-Step Calculations")

        area = results["area_m2"]
        irr = results["irr_annual"]

        # A. Surface
        st.markdown("**A. Usable Surface Area**")
        st.caption("The dynamic coverage ratio depends on roof shape and complexity.")
        st.latex(
            f"{area:.0f} \\text{{ m}}^2 \\times {effective_coverage_ratio:.2f} = "
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
        st.caption("Formula: Surface x Irradiance x Efficiency x Performance")
        st.latex(
            f"{exploitable:.0f} \\times {irr:.0f} \\times 0.18 \\times 0.75 "
            f"\\approx \\mathbf{{{energy:,.0f} \\text{{ kWh/yr}}}}"
        )

        # D. Financial Savings
        st.markdown("**D. Estimated Financial Benefit**")
        st.latex(
            f"{energy:,.0f} \\text{{ kWh}} \\times 0.20 \\text{{ EUR}} "
            f"\\approx \\mathbf{{{savings:,.0f} \\text{{ EUR/yr}}}}"
        )

        st.info(
            "Note: This is a simplified model. A real assessment also considers "
            "roof orientation, tilt, shading, and installation constraints."
        )
