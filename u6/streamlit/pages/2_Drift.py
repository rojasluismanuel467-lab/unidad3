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
# Sesgo de seleccion (senal secundaria)
# ---------------------------------------------------------------------------
st.header("Sesgo de seleccion en las semanas con rechazo alto")
st.caption(
    "Los clientes que sobreviven la cuarentena en las ultimas semanas tienen "
    "scores mas bajos y menos variados. Es senal indirecta de que el filtro "
    "se queda con los perfiles 'tradicionales' — los raros se van a cuarentena."
)

# Estas cifras vienen del diagnostico contra BQ del 2026-09-19 sobre la
# corrida buena (20260919T203047). Ver `u6/analysis/diagnostico_bq.py`.
sesgo_data = pd.DataFrame([
    {"semana": "2026-06-29", "n_ok": 49, "media_score": 0.317, "std_score": 0.141},
    {"semana": "2026-07-06", "n_ok": 45, "media_score": 0.289, "std_score": 0.145},
    {"semana": "2026-07-13", "n_ok": 81, "media_score": 0.286, "std_score": 0.123},
    {"semana": "2026-07-20", "n_ok": 61, "media_score": 0.296, "std_score": 0.147},
    {"semana": "2026-07-27", "n_ok": 95, "media_score": 0.292, "std_score": 0.145},
    {"semana": "2026-08-03", "n_ok": 56, "media_score": 0.308, "std_score": 0.156},
    {"semana": "2026-08-10", "n_ok": 85, "media_score": 0.257, "std_score": 0.142},
    {"semana": "2026-08-17", "n_ok": 70, "media_score": 0.267, "std_score": 0.112},
    {"semana": "2026-08-24", "n_ok": 74, "media_score": 0.228, "std_score": 0.093},
    {"semana": "2026-08-31", "n_ok": 37, "media_score": 0.202, "std_score": 0.059},
])

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Score promedio de los OK por semana**")
    st.line_chart(sesgo_data.set_index("semana")["media_score"], height=220)
with col2:
    st.markdown("**Desviacion estandar de los OK por semana**")
    st.line_chart(sesgo_data.set_index("semana")["std_score"], height=220)

with st.expander("Tabla numerica del sesgo de seleccion"):
    st.dataframe(
        sesgo_data, use_container_width=True, hide_index=True,
        column_config={
            "media_score": st.column_config.NumberColumn(format="%.3f"),
            "std_score": st.column_config.NumberColumn(format="%.3f"),
            "n_ok": st.column_config.NumberColumn(format="%d"),
        },
    )

st.markdown(
    "**Lectura.** En la semana 2026-08-31 (43.9 % rechazo) los 37 clientes "
    "que pasaron tienen score medio 0.20 y stdev 0.06 — muy comprimido. "
    "Los perfiles nuevos (PSE, PayPal, tenure >100) caen a cuarentena y "
    "solo pasan los clientes con perfiles conocidos. El modelo ve una "
    "poblacion ficticiamente 'tradicional' que no refleja la realidad."
)

# ---------------------------------------------------------------------------
# Hallazgo principal
# ---------------------------------------------------------------------------
st.header("Hallazgo principal")
st.markdown(f"> {drift['hallazgo_principal']}")

footer(fuentes=["hallazgos_u6.json", "BQ resultados corrida 20260919T203047"])
