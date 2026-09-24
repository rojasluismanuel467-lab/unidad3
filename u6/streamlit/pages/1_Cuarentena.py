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
    "Cuarentena y calibración del umbral",
    "Qué umbral usa el DAG para disparar la alarma y qué hay en las filas "
    "que quedan por fuera.",
    directriz="D1 + D2",
)

# ---------------------------------------------------------------------------
# D1 — Calibracion del umbral
# ---------------------------------------------------------------------------
st.header("Umbral del DAG")

cal = H["D1_calibracion_umbral"]

kpi_row([
    ("Media de rechazo (semanas 1–4)",
     f"{cal['primeras_4_semanas_media_rechazo_pct']}%",
     "Baseline pre-drift usado como referencia"),
    ("Desviación estándar",
     f"{cal['primeras_4_semanas_std']}%",
     "Volatilidad natural del rechazo"),
    ("Umbral recomendado (2σ)",
     f"{cal['recomendado_pct']}%",
     "Regla de 2 sigmas ≈ 95% de tolerancia a la fluctuación normal"),
    ("Umbral 3σ (más laxo)",
     f"{cal['umbral_3sigma_pct']}%",
     None),
])

st.markdown(
    "El DAG dispara una alerta cuando la tasa de rechazo supera un umbral. "
    "Con 10 semanas de historia calibramos el número con evidencia."
)

with st.expander("Justificacion tecnica del umbral 2σ", expanded=False):
    st.markdown(cal["justificacion"])

st.subheader("Tasa de rechazo por semana")
por_sem = pd.DataFrame(H["D1_tasa_rechazo_por_semana"])
st.bar_chart(por_sem.set_index("fecha_lote")["tasa_rechazo_pct"], height=280)

st.subheader("Sensibilidad — cuántas semanas dispararían alarma según el umbral")
sens = cal["sensitivity"]
sens_df = pd.DataFrame({
    "Umbral": ["Recomendado (2σ)", "5%", "10%", "20%"],
    "Semanas que disparan la alarma": [
        len(cal["semanas_que_disparan_2sigma"]),
        sens["si_umbral_es_5pct"],
        sens["si_umbral_es_10pct"],
        sens["si_umbral_es_20pct"],
    ],
})
st.dataframe(
    sens_df, use_container_width=True, hide_index=True,
    column_config={
        "Semanas que disparan la alarma": st.column_config.NumberColumn(format="%d"),
    },
)
st.caption(
    f"Con un umbral fijado a dedo del 20% no se alertaría en las dos últimas "
    f"semanas ({por_sem.iloc[-2]['tasa_rechazo_pct']:.2f}% y "
    f"{por_sem.iloc[-1]['tasa_rechazo_pct']:.2f}%). Con 2σ la primera alerta "
    f"aparece en {cal['semanas_que_disparan_2sigma'][0]} en este histórico."
)

# ---------------------------------------------------------------------------
# D2 — Contenido de la cuarentena
# ---------------------------------------------------------------------------
st.header("Contenido de la cuarentena")

q = H["D2_cuarentena"]

kpi_row([
    ("Errores detectados", f"{q['total_errores']:,}",
     "Errores de campo acumulados en las filas rechazadas"),
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

st.subheader("Evolución semanal")
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
    "**Hallazgo sobre el diseño de la cuarentena.** " + q["insight_texto_crudo"]
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
        "**Diagnóstico.** Los valores son legítimos: el CRM los envía porque "
        "son medios de pago reales que la empresa ahora acepta. El esquema del "
        "contrato en `service/app/schemas.py` (U5) está desactualizado.  \n"
        "**Corrección inmediata.** Ampliar el enum `PaymentMethod` para incluir PSE, "
        "PayPal, Digital wallet, Corporate billing, Credit card (manual)."
    )

footer(fuentes=["hallazgos_u6.json", "lotes_retencion_u6.csv"])
