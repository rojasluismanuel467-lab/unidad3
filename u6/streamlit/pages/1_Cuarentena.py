"""D1 + D2 — Umbral del DAG y contenido de la cuarentena."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)

st.title(":triangular_flag_on_post: D1 + D2 — Cuarentena y umbral del DAG")

# ------------------------- D1 -------------------------
st.header("D1 — El umbral del DAG (calibrado con evidencia)")

st.markdown(
    """
El DAG de U6 dispara la alarma cuando la tasa de rechazo supera un umbral.
En clase pusimos un numero a dedo. Ahora tenemos 10 semanas de historia:
podemos calcularlo.
"""
)

col1, col2 = st.columns(2)
cal = H["D1_calibracion_umbral"]
with col1:
    st.metric("Media rechazo primeras 4 semanas", f"{cal['primeras_4_semanas_media_rechazo_pct']}%")
    st.metric("Desviacion estandar", f"{cal['primeras_4_semanas_std']}%")
with col2:
    st.metric("Umbral recomendado (media + 2σ)", f"{cal['recomendado_pct']}%",
              help="Regla de 2σ = ~95% de tolerancia a fluctuacion normal")
    st.metric("Umbral 3σ (mas laxo)", f"{cal['umbral_3sigma_pct']}%")

st.info(cal["justificacion"])

st.subheader("Tasa de rechazo semana a semana")
por_sem = pd.DataFrame(H["D1_tasa_rechazo_por_semana"])
st.bar_chart(por_sem.set_index("fecha_lote")["tasa_rechazo_pct"])

st.subheader("Sensitivity — ¿cuantas semanas disparan la alarma segun el umbral?")
sens = cal["sensitivity"]
sens_df = pd.DataFrame({
    "umbral": ["Recomendado (2σ)", "5%", "10%", "20%"],
    "semanas_que_disparan_alarma": [
        len(cal["semanas_que_disparan_2sigma"]),
        sens["si_umbral_es_5pct"],
        sens["si_umbral_es_10pct"],
        sens["si_umbral_es_20pct"],
    ],
})
st.dataframe(sens_df, use_container_width=True, hide_index=True)
st.caption(
    "Con un umbral a dedo del 20% habriamos perdido la alarma temprana de la "
    "semana 2026-08-24 (18.7% de rechazo). Con 5% o 2σ, la alarma habria "
    "saltado y habriamos tenido 1 semana adicional para reaccionar."
)

st.markdown("---")

# ------------------------- D2 -------------------------
st.header("D2 — Que hay dentro de la cuarentena")

q = H["D2_cuarentena"]
st.metric("Total de errores detectados", q["total_errores"])

col1, col2 = st.columns(2)
with col1:
    st.subheader("Por CAMPO")
    st.dataframe(
        pd.DataFrame(q["por_campo"].items(), columns=["campo", "n_errores"])
        .sort_values("n_errores", ascending=False),
        hide_index=True,
    )

with col2:
    st.subheader("Por TIPO de error")
    st.dataframe(
        pd.DataFrame(q["por_tipo"].items(), columns=["tipo", "n_errores"])
        .sort_values("n_errores", ascending=False),
        hide_index=True,
    )

st.subheader("Evolucion semanal de los errores")
evol_rows = []
for w in q["evolucion_semanal"]:
    for campo, n in w["top_campos"]:
        evol_rows.append({"semana": w["semana"], "campo": campo, "n_errores": n})
evol_df = pd.DataFrame(evol_rows)
if not evol_df.empty:
    piv = evol_df.pivot_table(
        index="semana", columns="campo", values="n_errores", fill_value=0
    )
    st.bar_chart(piv)
    st.dataframe(piv, use_container_width=True)

st.warning(
    "**Hallazgo sobre el diseno de la cuarentena:** " + q["insight_texto_crudo"]
)

st.markdown("---")
st.subheader("Casos concretos del CSV: por que fallaron")

# Carga el CSV completo para ejemplos
df = pd.read_csv(ROOT / "data" / "lotes_retencion_u6.csv")

st.markdown("### PaymentMethod: valores nuevos no reconocidos")
enum_valid = {
    "Bank transfer (automatic)", "Credit card (automatic)",
    "Electronic check", "Mailed check",
}
nuevos = df[
    (~df["PaymentMethod"].isin(enum_valid)) & df["PaymentMethod"].notna()
]
st.metric("Filas rechazadas por PaymentMethod nuevo", len(nuevos))
if len(nuevos):
    valores_nuevos_x_semana = (
        nuevos.groupby(["fecha_lote", "PaymentMethod"])
        .size()
        .reset_index(name="n")
    )
    st.dataframe(valores_nuevos_x_semana, use_container_width=True)
    st.error(
        "**Estos valores son legitimos — el CRM los envia porque son medios "
        "de pago reales que la empresa ahora acepta. El schema del contrato "
        "(U5 schemas.py) esta desactualizado. Fix inmediato: ampliar el "
        "enum de PaymentMethod para incluir PSE, PayPal, Digital wallet, "
        "Corporate billing, Credit card (manual).**"
    )
