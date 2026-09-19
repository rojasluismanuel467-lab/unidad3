"""D1 + D2 — Umbral del DAG y contenido de la cuarentena."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, kpi_row, footer

apply_page_config(page_title="Cuarentena · Monitor U6")
sidebar_branding()

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)

page_header(
    "Cuarentena y calibracion del umbral",
    "Que umbral usa el DAG para disparar la alarma, y que hay en las filas "
    "que quedan por fuera.",
    directriz="D1 + D2",
)

# ---------------------------------------------------------------------------
# D1 — Calibracion del umbral
# ---------------------------------------------------------------------------
st.header("Umbral del DAG")

cal = H["D1_calibracion_umbral"]

kpi_row([
    ("Media rechazo (semanas 1-4)",
     f"{cal['primeras_4_semanas_media_rechazo_pct']}%",
     "Baseline pre-drift usado como referencia"),
    ("Desviacion estandar",
     f"{cal['primeras_4_semanas_std']}%",
     "Volatilidad natural del rechazo"),
    ("Umbral recomendado (2σ)",
     f"{cal['recomendado_pct']}%",
     "Regla de 2 sigmas ≈ 95% de tolerancia a fluctuacion normal"),
    ("Umbral 3σ (mas laxo)",
     f"{cal['umbral_3sigma_pct']}%",
     None),
])

st.markdown(
    "El DAG dispara alerta cuando la tasa de rechazo supera un umbral. "
    "Con 10 semanas de historia calibramos el numero con evidencia."
)

with st.expander("Justificacion tecnica del umbral 2σ", expanded=False):
    st.markdown(cal["justificacion"])

st.subheader("Tasa de rechazo por semana")
por_sem = pd.DataFrame(H["D1_tasa_rechazo_por_semana"])
st.bar_chart(por_sem.set_index("fecha_lote")["tasa_rechazo_pct"], height=280)

st.subheader("Sensitivity — cuantas semanas dispararian alarma segun el umbral")
sens = cal["sensitivity"]
sens_df = pd.DataFrame({
    "Umbral": ["Recomendado (2σ)", "5%", "10%", "20%"],
    "Semanas que disparan alarma": [
        len(cal["semanas_que_disparan_2sigma"]),
        sens["si_umbral_es_5pct"],
        sens["si_umbral_es_10pct"],
        sens["si_umbral_es_20pct"],
    ],
})
st.dataframe(
    sens_df, use_container_width=True, hide_index=True,
    column_config={
        "Semanas que disparan alarma": st.column_config.NumberColumn(format="%d"),
    },
)
st.caption(
    "Con un umbral fijado a dedo del 20% habriamos perdido la alarma temprana "
    "de la semana 2026-08-24 (18.7% rechazo). Con 2σ la alarma habria saltado "
    "una semana antes."
)

# ---------------------------------------------------------------------------
# D2 — Contenido de la cuarentena
# ---------------------------------------------------------------------------
st.header("Contenido de la cuarentena")

q = H["D2_cuarentena"]

kpi_row([
    ("Errores detectados", f"{q['total_errores']:,}",
     "Filas rechazadas en las 10 semanas"),
    ("Campos distintos con error", str(len(q["por_campo"])), None),
    ("Tipos de error", str(len(q["por_tipo"])), None),
])

col1, col2 = st.columns(2, gap="large")
with col1:
    st.subheader("Por campo")
    st.dataframe(
        pd.DataFrame(q["por_campo"].items(), columns=["Campo", "N errores"])
        .sort_values("N errores", ascending=False),
        hide_index=True, use_container_width=True,
        column_config={"N errores": st.column_config.NumberColumn(format="%d")},
    )

with col2:
    st.subheader("Por tipo")
    st.dataframe(
        pd.DataFrame(q["por_tipo"].items(), columns=["Tipo", "N errores"])
        .sort_values("N errores", ascending=False),
        hide_index=True, use_container_width=True,
        column_config={"N errores": st.column_config.NumberColumn(format="%d")},
    )

st.subheader("Evolucion semanal")
evol_rows = []
for w in q["evolucion_semanal"]:
    for campo, n in w["top_campos"]:
        evol_rows.append({"semana": w["semana"], "campo": campo, "n_errores": n})
evol_df = pd.DataFrame(evol_rows)
if not evol_df.empty:
    piv = evol_df.pivot_table(
        index="semana", columns="campo", values="n_errores", fill_value=0
    )
    st.bar_chart(piv, height=280)
    with st.expander("Ver matriz completa"):
        st.dataframe(piv, use_container_width=True)

st.caption(
    "**Insight sobre el diseno de la cuarentena.** " + q["insight_texto_crudo"]
)

# ---------------------------------------------------------------------------
# Casos concretos
# ---------------------------------------------------------------------------
st.header("Casos concretos del CSV")

df = pd.read_csv(ROOT / "data" / "lotes_retencion_u6.csv")

st.subheader("PaymentMethod: valores nuevos no reconocidos")
enum_valid = {
    "Bank transfer (automatic)", "Credit card (automatic)",
    "Electronic check", "Mailed check",
}
nuevos = df[
    (~df["PaymentMethod"].isin(enum_valid)) & df["PaymentMethod"].notna()
]

kpi_row([
    ("Filas rechazadas por PaymentMethod nuevo", f"{len(nuevos):,}", None),
    ("Valores distintos nuevos",
     f"{nuevos['PaymentMethod'].nunique()}" if len(nuevos) else "0", None),
])

if len(nuevos):
    valores_nuevos_x_semana = (
        nuevos.groupby(["fecha_lote", "PaymentMethod"])
        .size()
        .reset_index(name="n")
    )
    st.dataframe(
        valores_nuevos_x_semana,
        use_container_width=True, hide_index=True,
        column_config={"n": st.column_config.NumberColumn(format="%d")},
    )

    st.markdown(
        "**Diagnostico.** Los valores son legitimos: el CRM los envia porque "
        "son medios de pago reales que la empresa ahora acepta. El schema del "
        "contrato en `service/app/schemas.py` (U5) esta desactualizado.  \n"
        "**Fix inmediato.** Ampliar el enum `PaymentMethod` para incluir PSE, "
        "PayPal, Digital wallet, Corporate billing, Credit card (manual)."
    )

footer(fuentes=["hallazgos_u6.json", "lotes_retencion_u6.csv"])
