"""D3 + D4 — Drift analysis con PSI + KS-test + Chi2."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)

st.title(":chart_with_upwards_trend: D3 + D4 — Analisis de drift")

st.markdown(
    """
**Directriz 3:** los que pasaron la cuarentena tambien tienen algo que contar.
Comparamos las 10 semanas contra 2 referencias distintas:

1. **X_train de U4** — ¿los datos de hoy se parecen a los que el modelo aprendio?
2. **Primeras 4 semanas del CSV** — ¿esta semana se parece a las primeras?

**Directriz 4:** el metodo tiene que compararlas con el mismo criterio.
Usamos **PSI** (Population Stability Index) para escalar cualquier feature
al mismo eje: PSI > 0.25 es drift material (Verbraken 2013).
"""
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
