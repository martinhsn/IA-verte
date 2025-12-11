import streamlit as st
from streamlit_folium import st_folium
from solar_roi_france import evaluate_address, create_folium_map


CO2_PER_KWH = 0.0217
ELECTRICITY_PRICE = 0.1952


st.set_page_config(page_title="Solar AI Project", layout="centered")
st.markdown(
    """
    <style>
    section[data-testid="stHeading"] a {
        display: none !important;
    }
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <h1 style='text-align: center;'>
        Solar Potential Estimation
    </h1>
    <h3 style='text-align: center;'>
        Green AI Project
    </h3>
    """,
    unsafe_allow_html=True,
)


st.markdown(
    """
    <style>
    div[data-testid="stRadio"] {
        background-color: #fff3cd;
        padding: 0.75rem 1rem 0.25rem 1rem;
        border-radius: 0.25rem;
    }
    div[data-testid="stRadio"] > label {
        margin-bottom: 0.1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


house_answer = st.radio("Do you live in a house?", ["Yes", "No"])


if house_answer == "No":
    st.warning("Sorry, this service currently works only for houses.")
    st.stop()


if "results" not in st.session_state:
    st.session_state["results"] = None
if "error_message" not in st.session_state:
    st.session_state["error_message"] = None


address = st.text_input("Enter an address in France:", "13 rue des Peupliers, Paris")


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


if st.session_state["error_message"]:
    st.error(st.session_state["error_message"])

elif st.session_state["results"]:
    results = st.session_state["results"]
    st.success("Analysis completed successfully!")

    st.subheader("Satellite View & Detected OSM Building Outline")
    st.info(
        "Note: The red outline comes from OpenStreetMap data. Accuracy depends on local contributions."
    )

    try:
        folium_map = create_folium_map(results["roof"], results["lat"], results["lon"])
        st_folium(folium_map, width=700, height=450, key="result_map")
    except Exception as e:
        st.warning(f"Unable to display the map: {e}")

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
    irr = results["irr_annual"]

    energy = kwp * irr * 0.75

    co2_tonnes = energy * CO2_PER_KWH / 1000
    co2_kg = co2_tonnes * 1000
    savings = energy * ELECTRICITY_PRICE

    cost_avg = exploitable * 575

    if savings > 0:
        payback_years = cost_avg / savings
    else:
        payback_years = None

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Detected Roof (OSM)")

        st.metric("Approximate roof size", f"{results['area_m2']:,.0f} m2")
        st.metric("Detected Coverage Ratio", f"{results['coverage_ratio'] * 100:.0f}%")
        st.metric("Coverage Ratio Used", f"{effective_coverage_percent:.0f}%")
        st.metric("Usable Area", f"{exploitable:,.0f} m2")
        st.metric("Recommended System Size", f"{kwp:.1f} kWp")

    with col2:
        st.subheader("Estimated Potential (Estimation Only)")
        st.metric("Annual Production", f"{energy:,.0f} kWh/year")
        st.metric(
            "CO₂ Savings",
            f"{co2_kg:,.0f} kgCO₂/year",
            delta="Positive for the planet",
        )
        st.metric(
            "Estimated Financial Savings",
            f"{savings:,.0f} EUR/year",
            delta="Potential gain",
        )
        st.metric(
            "Estimated Installation Cost (avg)",
            f"{cost_avg:,.0f} EUR",
            help="Based on an average cost of 575 €/m² for solar installation in France (incl. maintenance)",
        )

    if payback_years is not None:
        st.markdown(
            f"""
<div style='text-align:center; margin-top: 1.5rem; margin-bottom: 1rem;'>
  <h3>Simple Payback Time (rough estimate)</h3>
  <p style='font-size:1.1rem; margin-top:0.5rem;'>
    The simple payback time is:<br>
    <strong>≈ {payback_years:.1f} years.</strong>
  </p>
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='text-align:center;'><em>Simple payback time cannot be estimated with the current assumptions.</em></div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    with st.expander("Understand These Results (Details & Assumptions)"):

        area = results["area_m2"]

        st.markdown("<h3>1. Standard Assumptions</h3>", unsafe_allow_html=True)
        st.markdown(
            f"""
These estimates rely on a few standard assumptions:

- **Dynamic coverage ratio detected:** {results['coverage_ratio'] * 100:.0f}%
- **Panel coverage slider applied:** {coverage_slider}%
- **Performance ratio (losses, wiring, inverter, etc.):** 0.75
- **Surface required per kWp (norm):** 5 m²/kWp
- **Electricity price (Dec 2025 TRV Tarif Bleu):** 0.1952 €/kWh
- **Installation cost:** 575 €/m²
"""
        )

        st.markdown(
            """
**Detected coverage ratio** (for example 50%) is an average share of the roof
that is realistically usable: we exclude non-south-facing parts and zones blocked
by chimneys, windows, obstacles or safety distances.

**Coverage ratio used** is the final share of the whole roof that enters the
calculation. It combines this detected limit and your slider
**“Panel coverage applied to the usable roof area”**.  
If you set the slider to 60%, we only keep 60% of the usable part.
"""
        )

        st.markdown("<h3>2. Effective usable surface area</h3>", unsafe_allow_html=True)
        st.markdown(
            "The effective usable surface area depends on the detected roof shape "
            "and the percentage you chose with the coverage slider."
        )

        st.latex(
            rf"""
{area:.0f}\ \text{{m}}^2 \times {effective_coverage_ratio:.2f}
\simeq {exploitable:.0f}\ \text{{m}}^2
"""
        )

        st.markdown(
            "This result is the **approximate roof surface actually used** for panels, "
            "after taking into account both physical roof constraints and your slider choice."
        )

        st.markdown("<h3>3. Recommended System Size (kWp)</h3>", unsafe_allow_html=True)
        st.markdown(
            f"""
From this effective usable surface area, we estimate the system size using a
common market rule of thumb:

- **Effective usable area:** {exploitable:.0f} m²  
- **Surface required per kWp (norm):** 5 m²/kWp  

This “5 m² per kWp” value is a standard approximation used in the sector:
it already includes typical panel efficiencies and layout constraints.
"""
        )

        st.latex(
            rf"""
\text{{System Size}} \simeq
\frac{{{exploitable:.0f}\ \text{{m}}^2}}{{5\ \text{{m}}^2/\text{{kWp}}}}
\simeq {kwp:.1f}\ \text{{kWp}}
"""
        )

        st.markdown("<h3>4. Local Solar Irradiance (NASA data)</h3>", unsafe_allow_html=True)

        st.markdown(
            """
For this address, we query the NASA POWER API using its exact GPS coordinates.
The value below is the **annual average solar irradiance** on a horizontal surface
for this location.
"""
        )

        st.latex(
            rf"""
\text{{Irradiance}} \simeq {irr:.0f}\ \text{{kWh/m}}^2/\text{{yr}}
"""
        )

        st.markdown("<h3>5. Estimated Electricity Production</h3>", unsafe_allow_html=True)
        st.markdown(
            """
Once we know:

- the **recommended system size** in kWp,  
- the **local annual irradiance** in kWh/m²/year, and
- the **performance ratio (losses, wiring, inverter, etc.)**,

we use a very simple proportional model: the yearly electricity production is
approximated as the system size multiplied by the local irradiance mulitplied and then by the performance ratio.
All the detailed assumptions (roof layout, losses, etc.) are already embedded in
the energy value shown above.
"""
        )

        st.latex(
            rf"""
E \simeq {kwp:.1f}\ \text{{kWp}} \times {irr:.0f}\ \text{{kWh/m}}^2/\text{{yr}} \times 0.75
\simeq {energy:,.0f}\ \text{{kWh/year}}
"""
        )

        st.markdown("<h3>6. CO₂ Savings</h3>", unsafe_allow_html=True)
        st.markdown(
            """
The **CO₂ savings** shown in the metrics above represent the emissions that would
have been produced if the same amount of electricity had come from the average
French electricity mix.

We use a simplified emission factor:

- **Emission factor:** 0.0217 kg CO₂ per kWh

With this factor, yearly CO₂ savings are computed as:
"""
        )
        st.latex(
            rf"""
\text{{CO}}_2\ \text{{savings}}
\simeq {energy:,.0f}\ \text{{kWh}} \times 0.0217\ \text{{kg CO}}_2/\text{{kWh}}
\simeq {co2_kg:,.0f}\ \text{{kg CO}}_2/\text{{year}}
"""
        )

        st.markdown("<h3>7. Financial Savings</h3>", unsafe_allow_html=True)
        st.markdown(
            """
Based on the regulated electricity tariff (TRV – Tarif Bleu EDF),
**December 2025 price: 0.1952 €/kWh**.
"""
        )
        st.latex(
            rf"""
E_{{\text{{savings}}}} \simeq {energy:,.0f}\ \text{{kWh}} \times 0.1952\ \text{{EUR/kWh}}
\simeq {savings:,.0f}\ \text{{EUR/year}}
"""
        )

        st.markdown("<h3>8. Installation Cost (Average France Value)</h3>", unsafe_allow_html=True)
        st.markdown(
            """
Average turnkey solar installation cost in France is **575 €/m²**,
including equipment, installation, administrative fees, and maintenance.
"""
        )
        st.latex(
            rf"""
{exploitable:.0f}\ \text{{m}}^2
\times 575\ \text{{EUR/m}}^2
\simeq {cost_avg:,.0f}\ \text{{EUR}}
"""
        )

        st.markdown("<h3>9. Simple Payback Time</h3>", unsafe_allow_html=True)
        if payback_years is not None:
            st.markdown(
                """
The simple payback time tells you how many years of electricity savings are
needed to cover the initial installation cost (ignoring future price changes,
maintenance, subsidies, or financing).
"""
            )
            st.latex(
                rf"""
T_{{\text{{payback}}}} \simeq
\frac{{{cost_avg:,.0f}\ \text{{EUR}}}}{{{savings:,.0f}\ \text{{EUR/year}}}}
\simeq {payback_years:.1f}\ \text{{years}}
"""
            )
            st.markdown(
                f"After roughly **year {int(payback_years) + 1}**, the system is paid back and the following years correspond to net savings."
            )
        else:
            st.markdown(
                "With the current assumptions, yearly savings are not positive, so a payback time cannot be computed."
            )

        st.info(
            "Note: This model does not yet account for roof orientation, tilt, or shading. "
            "A real assessment would refine these estimates."
        )
