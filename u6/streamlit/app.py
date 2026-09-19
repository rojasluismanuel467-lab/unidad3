"""Home del monitor U6 — Grupo 2."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Monitor pipeline retencion — Grupo 2",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS para look mas sobrio: tipografia system, spacing generoso, tarjetas neutras
st.markdown(
    """
    <style>
    .block-container {padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1100px;}
    h1 {font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.25rem;}
    h2 {font-weight: 600; letter-spacing: -0.01em; margin-top: 2rem; padding-top: 0.5rem;
        border-top: 1px solid #e5e7eb;}
    h3 {font-weight: 600; margin-top: 1.5rem;}
    [data-testid="stMetricLabel"] {font-size: 0.8rem; color: #6b7280; text-transform: uppercase;
        letter-spacing: 0.04em;}
    [data-testid="stMetricValue"] {font-size: 2rem; font-weight: 600;}
    [data-testid="stSidebarNav"] a {font-size: 0.9rem;}
    footer, [data-testid="stDecoration"] {display: none;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Monitor del pipeline de retencion")
st.caption(
    "Grupo 2 · Escobar A00399291 · Artunduaga A00396342 · Rojas A00399289 · "
    "Curso Computacion en la Nube para IA · Prof. Diana Jaimes"
)

# ---------------------------------------------------------------------------
# Resumen ejecutivo — lo primero que ve la Direccion de Retencion
# ---------------------------------------------------------------------------
try:
    with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
        H = json.load(f)
except FileNotFoundError:
    st.error(
        "Falta `analysis/hallazgos_u6.json`. Corre `python u6/analysis/run_analysis.py` "
        "para regenerar los hallazgos."
    )
    st.stop()

st.subheader("Resumen ejecutivo")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Semanas analizadas", H["meta"]["n_semanas"])
c2.metric("Clientes en el lote", f"{H['meta']['csv_filas']:,}")
c3.metric("Tasa de rechazo", f"{H['D1_agregado']['tasa_rechazo_pct']:.1f}%")
c4.metric("Features con drift material", H.get("D3_drift", {}).get("n_features_drift", "—"))

st.markdown(
    "El pipeline detecto la degradacion antes de que impactara mas campanas. "
    "**El modelo no se rompio — la poblacion cambio.** Los detalles y el plan de "
    "respuesta estan en las vistas laterales."
)

# ---------------------------------------------------------------------------
# Como leer este dashboard
# ---------------------------------------------------------------------------
st.subheader("Vistas disponibles")

vistas = [
    ("Cuarentena", "Que se rechazo y por que. Distribucion por semana y tipo de error."),
    ("Drift", "PSI y KS-test por feature. Que cambio en la poblacion desde el training set."),
    ("BancoPago", "La columna nueva que el modelo no conoce. Analisis de impacto."),
    ("Respuesta Cliente", "Timeline SRE + accion recomendada para la Direccion de Retencion."),
    ("Prediccion Individual", "Consultar el modelo desplegado en Cloud Run con un caso ad-hoc."),
    ("Consulta BQ", "Ver las tablas `resultados` y `cuarentena` que el DAG carga en BigQuery."),
]

col_izq, col_der = st.columns(2)
for i, (titulo, descripcion) in enumerate(vistas):
    (col_izq if i % 2 == 0 else col_der).markdown(f"**{titulo}** — {descripcion}")

# ---------------------------------------------------------------------------
# Fuentes / footer tecnico
# ---------------------------------------------------------------------------
st.subheader("Fuentes")
st.markdown(
    f"""
- **CSV en produccion**: `lotes_retencion_u6.csv` ({H['meta']['csv_filas']} filas, {H['meta']['n_semanas']} semanas)
- **Modelo**: `u4_g02_mdl_20260914` (XGBoost calibrado, U4) desplegado en Cloud Run como `u5-g02-cr-20260914`
- **Baseline drift**: X_train de U4 (Telco Churn extendido, {H.get('meta', {}).get('baseline_filas', 'N/A')} filas)
- **DAG**: `pipeline_mlops_churn` (Airflow 3.3.2) — carga a `computacionnube20262.u6_g02_data_20260919`
"""
)
