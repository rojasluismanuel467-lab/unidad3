"""D6 — Respuesta al cliente: que paso, que significa, que recomendamos."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)
r = H["D6_respuesta_cliente"]


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

st.title("Respuesta al cliente")
st.caption(
    "D6 · Correo de vuelta a la Direccion de Retencion, con los tres "
    "puntos que planteo: que paso, que significa, que recomendamos."
)

st.subheader("1. Que paso")
st.info(r["que_paso"]["titular"])

with st.expander("Evidencia 1 — Valores nuevos de PaymentMethod (49% de los rechazos)", expanded=True):
    st.markdown(r["que_paso"]["evidencia_1_valores_nuevos_paymentmethod"])
    detalle = r["que_paso"]["evidencia_1_detalle_por_semana"]
    if detalle:
        st.dataframe(
            pd.DataFrame([{"semana:valor": k, "n": v} for k, v in detalle.items()]),
            use_container_width=True, hide_index=True,
        )

with st.expander("Evidencia 2 — Drift material en `tenure`", expanded=True):
    st.markdown(r["que_paso"]["evidencia_2_drift_material_tenure"])

with st.expander("Evidencia 3 — Drift material en `MonthlyCharges`", expanded=True):
    st.markdown(r["que_paso"]["evidencia_3_drift_material_monthlycharges"])

with st.expander("Evidencia 4 — `Contract` estable (no todo cambio)"):
    st.markdown(r["que_paso"]["evidencia_4_contract_estable"])

with st.expander("Evidencia 5 — La tasa de rechazo confirma el patron"):
    st.markdown(r["que_paso"]["evidencia_5_tasa_rechazo"])

st.subheader("PSI promedio por feature vs training")
psi_prom = r["que_paso"]["psi_promedio_por_feature_vs_training"]
if psi_prom:
    st.dataframe(
        pd.DataFrame(psi_prom.items(), columns=["feature", "psi_promedio_vs_training"]),
        use_container_width=True, hide_index=True,
    )

st.markdown("---")
st.subheader("2. Que significa")
st.info(r["que_significa"]["titular"])

st.subheader("Hipotesis 1 — Medios de pago expandidos")
st.markdown(r["que_significa"]["hipotesis_1_medios_pago_expandidos"])

st.subheader("Hipotesis 2 — Campana de adquisicion nueva")
st.markdown(r["que_significa"]["hipotesis_2_campana_nueva"])

st.subheader("Hipotesis 3 — El CRM cambio su criterio de alerta")
st.markdown(r["que_significa"]["hipotesis_3_criterio_alerta_crm_cambió"])

st.markdown("---")
st.subheader("3. Que recomendamos")

st.error("**Inmediato (hoy mismo):** " + r["que_recomendamos"]["inmediato_hoy_mismo"])
st.warning("**Corto plazo (esta semana):** " + r["que_recomendamos"]["corto_plazo_esta_semana"])
st.info("**Mediano plazo (este mes):** " + r["que_recomendamos"]["mediano_plazo_mes"])
st.success("**Largo plazo (infra):** " + r["que_recomendamos"]["largo_plazo"])

st.markdown("---")
st.subheader("Timeline SRE — cronologia del incidente")
st.caption(
    "Formato Google SRE Workbook (cap. Postmortem Culture). "
    "Estructura los eventos con dueno y fecha."
)
timeline = r.get("timeline_sre", [])
if timeline:
    df_t = pd.DataFrame(timeline)
    color_map = {
        "verde": "OK",
        "amarillo": "warn",
        "rojo": "FAIL",
        "azul": "info",
        "planificado": "planificado",
    }
    for e in timeline:
        icono = color_map.get(e["estado"], "")
        st.markdown(f"{icono} **{e['fecha']}** — {e['evento']}")
        st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;{e['detalle']}")

st.markdown("---")
st.subheader("Action items con owner y due date")
st.caption(
    "Cada recomendacion se traduce en accion concreta. Priorizadas por "
    "impacto en la calidad del score."
)
items = r.get("action_items", [])
if items:
    df_i = pd.DataFrame(items)
    st.dataframe(df_i, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("Limites reconocidos de este analisis")
st.caption(
    "Ser explicito sobre lo que NO cubrimos evita conclusiones sobredimensionadas. "
    "Basado en Gama 2014 (concept drift survey), Nixon 2019 (calibration), "
    "Rabanser 2019 (MMD multivariado), Efron 1979 (bootstrap)."
)
limites = r.get("limites_reconocidos_del_analisis", [])
for lim in limites:
    st.warning(lim)

st.markdown("---")
st.subheader("Conclusion para la reunion")
st.markdown(f"> {r['conclusion_para_la_reunion']}")
