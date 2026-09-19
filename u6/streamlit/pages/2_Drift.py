"""D3 + D4 — Drift analysis con PSI + KS-test + Chi2."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, footer

apply_page_config(page_title="Drift · Monitor U6")
sidebar_branding()

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)

drift = H["D3_D4_drift"]

page_header(
    "Analisis de drift",
    "Que tanto cambio la poblacion respecto al training set y respecto a "
    "las primeras semanas del CSV.",
    directriz="D3 + D4",
)

st.markdown(
    "Se comparan las 10 semanas contra dos referencias: **X_train de U4** "
    "(¿los datos de hoy se parecen a los que el modelo aprendio?) y las "
    "**primeras 4 semanas del CSV** (¿esta semana se parece a las primeras?). "
    "Metodo: PSI (Population Stability Index) — umbral 0.25 marca drift "
    "material, siguiendo Siddiqi (2006, *Credit Risk Scorecards*)."
)

with st.expander("Umbrales de referencia (¿que valor de PSI es 'malo'?)"):
    u = drift["umbrales_referencia"]
    st.markdown(
        """
- **PSI < 0.10** — poblacion estable
- **0.10 ≤ PSI ≤ 0.25** — drift leve, monitorear
- **PSI > 0.25** — drift material, requiere retraining
- **KS p-value < 0.05** — distribuciones estadisticamente distintas
"""
    )
    st.caption(u["justificacion_psi_material_0.25"])

# ---------------------------------------------------------------------------
# (a) vs Training U4
# ---------------------------------------------------------------------------
st.header("Drift vs X_train de U4")
st.caption("¿Los datos de hoy se parecen a los que el modelo aprendio?")

for feat in drift["features_numericas"]:
    st.subheader(f"`{feat}`")
    resultados = drift["vs_training_U4"][feat]
    df_feat = pd.DataFrame(resultados)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**PSI por semana**")
        st.bar_chart(df_feat.set_index("semana")["psi"], height=220)
    with col2:
        st.markdown("**KS statistic por semana**")
        st.line_chart(df_feat.set_index("semana")["ks_stat"], height=220)
    with st.expander("Tabla numerica"):
        st.dataframe(
            df_feat, use_container_width=True, hide_index=True,
            column_config={
                "psi": st.column_config.NumberColumn(format="%.3f"),
                "ks_stat": st.column_config.NumberColumn(format="%.3f"),
                "ks_pvalue": st.column_config.NumberColumn(format="%.4f"),
            },
        )

# ---------------------------------------------------------------------------
# (b) vs Baseline 4 semanas
# ---------------------------------------------------------------------------
st.header("Drift vs primeras 4 semanas del CSV")
st.caption("¿Esta semana se parece a las primeras del archivo?")

for feat in drift["features_numericas"]:
    st.subheader(f"`{feat}`")
    resultados = drift["vs_baseline_4_semanas"][feat]
    df_feat = pd.DataFrame(resultados)
    st.bar_chart(df_feat.set_index("semana")["psi"], height=220)
    with st.expander("Tabla numerica"):
        st.dataframe(
            df_feat, use_container_width=True, hide_index=True,
            column_config={
                "psi": st.column_config.NumberColumn(format="%.3f"),
            },
        )

# ---------------------------------------------------------------------------
# Categoricas
# ---------------------------------------------------------------------------
st.header("`Contract` vs training (chi²)")
st.caption("¿La distribucion de Contract cambio?")

chi2_data = pd.DataFrame(drift["chi2_contract_vs_training"])
col1, col2 = st.columns(2)
with col1:
    st.markdown("**chi² por semana**")
    st.line_chart(chi2_data.set_index("semana")["chi2"], height=220)
with col2:
    st.markdown("**Delta maximo por bucket**")
    st.line_chart(chi2_data.set_index("semana")["max_delta_pct"], height=220)
with st.expander("Tabla numerica chi²"):
    st.dataframe(chi2_data, use_container_width=True, hide_index=True)

st.markdown(
    "Contract fluctua pero **no crece monotonamente** — es relativamente "
    "estable. No todas las features driftan: cambiaron `tenure` y "
    "`MonthlyCharges`, no `Contract`. Es un shift dirigido, no ruido general."
)

# ---------------------------------------------------------------------------
# Hallazgo principal
# ---------------------------------------------------------------------------
st.header("Hallazgo principal")
st.markdown(f"> {drift['hallazgo_principal']}")

footer(fuentes=["hallazgos_u6.json"])
