"""Home del monitor U6 — Grupo 2."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from _shared import (
    apply_page_config, sidebar_branding, page_header, kpi_row, footer,
)

apply_page_config(page_title="Monitor pipeline retencion")
sidebar_branding()

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
page_header(
    "Monitor del pipeline de retencion",
    "Escobar A00399291 · Artunduaga A00396342 · Rojas A00399289 · "
    "Curso Computacion en la Nube para IA · Prof. Diana Jaimes",
)

# ---------------------------------------------------------------------------
# Cargar hallazgos precalculados
# ---------------------------------------------------------------------------
try:
    with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
        H = json.load(f)
except FileNotFoundError:
    st.error(
        "No se encontro `analysis/hallazgos_u6.json`.  \n"
        "**Que hacer:** corre `python u6/analysis/run_analysis.py` para regenerar."
    )
    st.stop()

# ---------------------------------------------------------------------------
# KPIs — lo primero que ve la Direccion de Retencion
# ---------------------------------------------------------------------------
kpi_row([
    ("Semanas analizadas", str(H["meta"]["n_semanas"]),
     "Ventana del CSV entregado por el cliente"),
    ("Clientes en el lote", f"{H['meta']['csv_filas']:,}",
     "Total de filas del CSV lotes_retencion_u6.csv"),
    ("Tasa de rechazo", f"{H['D1_agregado']['tasa_rechazo_pct']:.1f}%",
     "Fraccion rechazada por el API en el batch completo"),
    ("Features con drift material",
     str(H.get("D3_drift", {}).get("n_features_drift", "—")),
     "Features con PSI > 0.25 vs training set (Siddiqi 2006)"),
])

# ---------------------------------------------------------------------------
# Titular ejecutivo
# ---------------------------------------------------------------------------
st.markdown(
    "El pipeline detecto la degradacion antes de que impactara mas campanas. "
    "**El modelo no se rompio — la poblacion cambio.**  \n"
    "Los detalles y el plan de respuesta estan en las vistas laterales."
)

# ---------------------------------------------------------------------------
# Catalogo de vistas
# ---------------------------------------------------------------------------
st.header("Vistas del monitor")

vistas = [
    ("Cuarentena", "Que se rechazo y por que. Distribucion por semana y tipo de error.", "D1+D2"),
    ("Drift", "PSI y KS-test por feature. Cambio de poblacion vs training.", "D3+D4"),
    ("BancoPago", "Columna nueva no conocida por el modelo. Analisis de impacto.", "D5"),
    ("Respuesta Cliente", "Timeline SRE + accion recomendada.", "D6"),
    ("Prediccion Individual", "Consultar el modelo desplegado en Cloud Run.", "—"),
    ("Consulta BQ", "Tablas `resultados` y `cuarentena` cargadas por el DAG.", "—"),
]

izq, der = st.columns(2, gap="large")
for i, (titulo, descripcion, tag) in enumerate(vistas):
    col = izq if i % 2 == 0 else der
    with col:
        st.markdown(
            f"**{titulo}**  \n"
            f"<span style='color:#6b7280;font-size:0.85rem'>{descripcion}</span>  \n"
            f"<span style='font-size:0.72rem;color:#6b7280;letter-spacing:0.06em;"
            f"text-transform:uppercase'>{tag}</span>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Fuentes / footer tecnico
# ---------------------------------------------------------------------------
st.header("Fuentes")
st.markdown(
    f"""
- **CSV en produccion**: `lotes_retencion_u6.csv` ({H['meta']['csv_filas']} filas, {H['meta']['n_semanas']} semanas)
- **Modelo**: `u4_g02_mdl_20260914` — XGBoost calibrado, desplegado como `u5-g02-cr-20260914`
- **Baseline drift**: X_train de U4 ({H.get('meta', {}).get('baseline_filas', 'N/A')} filas)
- **DAG**: `pipeline_mlops_churn` (Airflow 3.3.2) carga a `computacionnube20262.u6_g02_data_20260919`
"""
)

footer(fuentes=["lotes_retencion_u6.csv", "hallazgos_u6.json"])
