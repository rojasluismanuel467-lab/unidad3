"""D5 — Que hacer con la columna nueva BancoPago."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, kpi_row, footer

apply_page_config(page_title="BancoPago · Monitor U6")
sidebar_branding()

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)
b = H["D5_banco_pago"]

page_header(
    "Columna nueva: BancoPago",
    "Que hacer con un campo que llega en el CSV pero el modelo no conoce, "
    "y que ademas viene con captura parcial.",
    directriz="D5",
)

st.markdown(
    "> Desde hace unas semanas empezamos a capturar el banco desde el cual "
    "nos pagan. Es un campo nuevo, asi que en los primeros envios viene vacio "
    "y aparece a partir de cierta fecha. Sabemos que la captura no ha sido "
    "perfecta.\n\n— Direccion de Retencion, correo del 2026-09-14"
)

kpi_row([
    ("Primera semana con datos", b["primera_semana_con_datos"], None),
    ("Filas con BancoPago", f"{b['n_valores_no_nulos']:,}", None),
    ("Filas sin BancoPago", f"{b['n_valores_nulos']:,}",
     "Nulls en las primeras semanas antes de que existiera la columna"),
])

# ---------------------------------------------------------------------------
# Cobertura semanal
# ---------------------------------------------------------------------------
st.header("Cobertura semana a semana")

cov = pd.DataFrame(b["cobertura_por_semana"])
col1, col2 = st.columns([2, 1], gap="large")
with col1:
    st.bar_chart(cov.set_index("fecha_lote")["cobertura_pct"], height=280)
with col2:
    st.dataframe(
        cov, use_container_width=True, hide_index=True,
        column_config={
            "cobertura_pct": st.column_config.NumberColumn(format="%.1f %%"),
        },
    )

st.caption(
    "La cobertura salta de 0 % a 94 % entre 2026-07-20 y 2026-07-27 (arranque "
    "de captura). Despues se estabiliza entre 92-98 %."
)

# ---------------------------------------------------------------------------
# Variantes / canonicalizacion
# ---------------------------------------------------------------------------
st.header("Captura inconsistente")

kpi_row([
    ("Variantes originales", str(b["n_variantes_originales"]),
     "Strings distintos en el CSV crudo"),
    ("Despues de canonicalizar", str(b["n_variantes_despues_canon"]),
     "Aplicando strip + lowercase + mapping de sinonimos"),
    ("Reduccion",
     f"{100 * (1 - b['n_variantes_despues_canon'] / max(b['n_variantes_originales'], 1)):.0f}%",
     None),
])

col1, col2 = st.columns(2, gap="large")
with col1:
    st.subheader("Top valores raw")
    st.dataframe(
        pd.DataFrame(b["top_variantes_raw"].items(), columns=["Valor raw", "N"]),
        use_container_width=True, hide_index=True,
        column_config={"N": st.column_config.NumberColumn(format="%d")},
    )

with col2:
    st.subheader("Top valores canonicalizados")
    st.dataframe(
        pd.DataFrame(b["top_valores_canonicalizados"].items(),
                     columns=["Banco canon", "N"]),
        use_container_width=True, hide_index=True,
        column_config={"N": st.column_config.NumberColumn(format="%d")},
    )

st.markdown(
    "El mismo banco aparece hasta con 3 variantes:  \n"
    "- **Bancolombia** — `Bancolombia S.A.`, `bancolombia`  \n"
    "- **Banco de Bogota** — `BCO BOGOTA`  \n"
    "- **Davivienda** — `davivienda`"
)

# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------
st.header("Decision")
st.markdown(f"**{b['decision_defendible']}**")

st.subheader("Alternativas descartadas")

with st.expander("A — Imputar los nulos con el banco mas frecuente"):
    st.markdown(
        "Meteria sesgo sistematico: el cliente sin BancoPago no es aleatorio. "
        "Ademas las primeras 4 semanas son 100 % nulls porque la columna no "
        "existia, e imputarlas contaminaria el baseline de drift."
    )

with st.expander("B — Descartar todas las filas sin BancoPago"):
    st.markdown(
        "Perderiamos 259 clientes (37 % del CSV), casi todos de las primeras "
        "4 semanas. Rompe la promesa del pipeline de scorear todo lo que pasa "
        "el contrato."
    )

with st.expander("C — Agregar BancoPago como feature del modelo ya"):
    st.markdown(
        "El modelo actual no la conoce (features cerradas en U3/U4). Agregarla "
        "requiere re-entrenar con nueva feature engineering. Ademas con la "
        "captura tan sucia, el modelo aprenderia los typos como categorias "
        "distintas."
    )

with st.expander("D — Ignorar como feature + canonicalizar para uso operativo (elegida)",
                 expanded=True):
    st.markdown(
        "- No rompe el contrato del modelo.  \n"
        "- Permite dashboards y analisis operativo.  \n"
        "- Deja documentado el problema de captura al cliente sin dependencia "
        "  tecnica del pipeline de scoring."
    )

footer(fuentes=["hallazgos_u6.json"])
