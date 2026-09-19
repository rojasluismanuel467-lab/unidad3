"""D3 + D4 — Drift analysis con PSI + KS-test + Chi2."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)


st.set_page_config(layout="wide")
st.markdown("""<style>
.block-container {padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1100px;}
h1 {font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.25rem;}
h2 {font-weight: 600; letter-spacing: -0.01em; margin-top: 2rem;}
h3 {font-weight: 600; margin-top: 1.5rem;}
[data-testid="stMetricLabel"] {font-size: 0.8rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em;}
[data-testid="stMetricValue"] {font-size: 1.8rem; font-weight: 600;}
footer, [data-testid="stDecoration"] {display: none;}
</style>""", unsafe_allow_html=True)

st.title("Analisis de drift")
st.caption(
    "D3 + D4 · Que tanto cambio la poblacion respecto al training set, "
    "y respecto a las primeras semanas del CSV."
)

st.markdown(
    "Se comparan las 10 semanas contra dos referencias: X_train de U4 "
    "(¿los datos de hoy se parecen a los que el modelo aprendio?) y las "
    "primeras 4 semanas del CSV (¿esta semana se parece a las primeras?). "
    "Metodo: **PSI** (Population Stability Index) — umbral 0.25 marca "
    "drift material, siguiendo Siddiqi (2006, *Credit Risk Scorecards*)."
)

drift = H["D3_D4_drift"]

# ------------------------- Umbrales -------------------------
with st.expander(":books: Umbrales de referencia (¿que valor de PSI es 'malo'?)"):
    u = drift["umbrales_referencia"]
    st.markdown(f"""
    - **PSI < 0.10** — poblacion estable, sin cambios significativos
    - **0.10 ≤ PSI ≤ 0.25** — drift leve, monitorear
    - **PSI > 0.25** — drift material, requiere retraining
    - **KS p-value < 0.05** — distribuciones estadisticamente distintas

    {u['justificacion_psi_material_0.25']}
    """)

st.markdown("---")

# ------------------------- (a) vs Training U4 -------------------------
st.header("(a) Drift vs X_train de U4")
st.caption("¿Los datos de hoy se parecen a los que el modelo aprendio?")

for feat in drift["features_numericas"]:
    st.subheader(f"Feature: `{feat}`")
    resultados = drift["vs_training_U4"][feat]
    df_feat = pd.DataFrame(resultados)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PSI por semana**")
        st.bar_chart(df_feat.set_index("semana")["psi"])
    with col2:
        st.markdown("**KS statistic por semana**")
        st.line_chart(df_feat.set_index("semana")["ks_stat"])
    with st.expander("Tabla numerica"):
        st.dataframe(df_feat, use_container_width=True, hide_index=True)

st.markdown("---")

# ------------------------- (b) vs Baseline 4 semanas -------------------------
st.header("(b) Drift vs primeras 4 semanas del CSV")
st.caption("¿Esta semana se parece a las primeras del archivo?")

for feat in drift["features_numericas"]:
    st.subheader(f"Feature: `{feat}`")
    resultados = drift["vs_baseline_4_semanas"][feat]
    df_feat = pd.DataFrame(resultados)
    st.bar_chart(df_feat.set_index("semana")["psi"])
    with st.expander("Tabla numerica"):
        st.dataframe(df_feat, use_container_width=True, hide_index=True)

st.markdown("---")

# ------------------------- Categoricas -------------------------
st.header("Contract vs training (chi2)")
st.caption("¿La distribucion de Contract cambio?")

chi2_data = pd.DataFrame(drift["chi2_contract_vs_training"])
col1, col2 = st.columns(2)
with col1:
    st.line_chart(chi2_data.set_index("semana")["chi2"])
with col2:
    st.line_chart(chi2_data.set_index("semana")["max_delta_pct"])
with st.expander("Tabla numerica chi2"):
    st.dataframe(chi2_data, use_container_width=True, hide_index=True)

st.info(
    "Contract fluctua pero NO crece monotonamente — la distribucion de tipo "
    "de contrato es relativamente estable. **No todas las features driftan**: "
    "cambiaron `tenure` y `MonthlyCharges`, no `Contract`. Es un shift "
    "dirigido, no ruido general."
)

st.markdown("---")

# ------------------------- Hallazgo principal -------------------------
st.header(":bulb: Hallazgo principal")
st.error(drift["hallazgo_principal"])
