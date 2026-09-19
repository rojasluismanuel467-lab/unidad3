"""D6 — Respuesta al cliente: que paso, que significa, que recomendamos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, footer

apply_page_config(page_title="Respuesta cliente · Monitor U6")
sidebar_branding()

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)
r = H["D6_respuesta_cliente"]

page_header(
    "Respuesta al cliente",
    "Correo de vuelta a la Direccion de Retencion, con los tres puntos que "
    "plantearon: que paso, que significa, que recomendamos.",
    directriz="D6",
)

# ---------------------------------------------------------------------------
# 1. Que paso
# ---------------------------------------------------------------------------
st.header("1. Que paso")
st.markdown(f"> {r['que_paso']['titular']}")

with st.expander("Evidencia 1 — Valores nuevos de PaymentMethod (49 % de los rechazos)",
                 expanded=True):
    st.markdown(r["que_paso"]["evidencia_1_valores_nuevos_paymentmethod"])
    detalle = r["que_paso"]["evidencia_1_detalle_por_semana"]
    if detalle:
        st.dataframe(
            pd.DataFrame([{"semana:valor": k, "n": v} for k, v in detalle.items()]),
            use_container_width=True, hide_index=True,
            column_config={"n": st.column_config.NumberColumn(format="%d")},
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
        pd.DataFrame(psi_prom.items(), columns=["feature", "PSI promedio vs training"]),
        use_container_width=True, hide_index=True,
        column_config={
            "PSI promedio vs training": st.column_config.NumberColumn(format="%.3f"),
        },
    )

# ---------------------------------------------------------------------------
# 2. Que significa
# ---------------------------------------------------------------------------
st.header("2. Que significa")
st.markdown(f"> {r['que_significa']['titular']}")

st.subheader("Hipotesis 1 — Medios de pago expandidos")
st.markdown(r["que_significa"]["hipotesis_1_medios_pago_expandidos"])

st.subheader("Hipotesis 2 — Campana de adquisicion nueva")
st.markdown(r["que_significa"]["hipotesis_2_campana_nueva"])

st.subheader("Hipotesis 3 — El CRM cambio su criterio de alerta")
st.markdown(r["que_significa"]["hipotesis_3_criterio_alerta_crm_cambió"])

# ---------------------------------------------------------------------------
# 3. Que recomendamos — semaforo semantico (unico lugar donde el color aporta)
# ---------------------------------------------------------------------------
st.header("3. Que recomendamos")

recs = [
    ("Inmediato (hoy mismo)", r["que_recomendamos"]["inmediato_hoy_mismo"], "fail"),
    ("Corto plazo (esta semana)", r["que_recomendamos"]["corto_plazo_esta_semana"], "warn"),
    ("Mediano plazo (este mes)", r["que_recomendamos"]["mediano_plazo_mes"], "info"),
    ("Largo plazo (infra)", r["que_recomendamos"]["largo_plazo"], "ok"),
]
_color = {
    "fail": "#991b1b", "warn": "#92400e", "info": "#1e40af", "ok": "#065f46",
}
_bg = {
    "fail": "#fee2e2", "warn": "#fef3c7", "info": "#dbeafe", "ok": "#d1fae5",
}
for label, texto, tono in recs:
    st.markdown(
        f"""<div style="border-left: 3px solid {_color[tono]};
                     background: {_bg[tono]}20;
                     padding: 0.6rem 0.9rem;
                     margin: 0.5rem 0;
                     border-radius: 4px;">
        <div style="font-size:0.72rem;color:{_color[tono]};font-weight:600;
                    letter-spacing:0.05em;text-transform:uppercase;">{label}</div>
        <div style="color:#111827;margin-top:0.25rem;">{texto}</div>
        </div>""",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Timeline SRE
# ---------------------------------------------------------------------------
st.header("Timeline del incidente")
st.caption(
    "Formato Google SRE Workbook (cap. Postmortem Culture). Estructura los "
    "eventos con dueno y fecha."
)

timeline = r.get("timeline_sre", [])
_estado_glyph = {
    "verde": ("●", "#065f46"),
    "amarillo": ("●", "#92400e"),
    "rojo": ("●", "#991b1b"),
    "azul": ("●", "#1e40af"),
    "planificado": ("○", "#6b7280"),
}
for e in timeline:
    glyph, color = _estado_glyph.get(e["estado"], ("●", "#6b7280"))
    st.markdown(
        f"""<div style="padding: 0.35rem 0; border-bottom: 1px solid #f3f4f6;">
        <span style="color:{color};font-size:1.1rem;">{glyph}</span>
        <b style="margin-left:0.5rem;">{e['fecha']}</b> — {e['evento']}
        <div style="color:#6b7280;font-size:0.85rem;margin-left:1.6rem;">
        {e['detalle']}</div></div>""",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Action items
# ---------------------------------------------------------------------------
st.header("Action items")
st.caption(
    "Cada recomendacion se traduce en accion concreta con owner y due date, "
    "priorizadas por impacto en la calidad del score."
)

items = r.get("action_items", [])
if items:
    df_i = pd.DataFrame(items)
    st.dataframe(df_i, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Limites
# ---------------------------------------------------------------------------
st.header("Limites reconocidos del analisis")
st.caption(
    "Explicito sobre lo que este analisis NO cubre — evita conclusiones "
    "sobredimensionadas. Basado en Gama 2014 (concept drift survey), Nixon "
    "2019 (calibration), Rabanser 2019 (MMD multivariado), Efron 1979 "
    "(bootstrap)."
)
for lim in r.get("limites_reconocidos_del_analisis", []):
    st.markdown(f"- {lim}")

# ---------------------------------------------------------------------------
# Conclusion
# ---------------------------------------------------------------------------
st.header("Conclusion para la reunion")
st.markdown(f"> {r['conclusion_para_la_reunion']}")

footer(fuentes=["hallazgos_u6.json"])
