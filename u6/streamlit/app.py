"""U6 — Monitoreo de un pipeline de retencion en produccion.

Streamlit app del Grupo 2 para el trabajo final de la Unidad 6.
Incluye las 5 directrices (D1-D6) mas prediccion individual contra el
servicio Cloud Run de U5.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT  # analysis/ y data/ son symlinks a los mismos directorios en u6/

st.set_page_config(
    page_title="U6 Grupo 2 — Monitoreo pipeline churn",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
)

# ---------- Home ----------
st.title(":chart_with_upwards_trend: Unidad 6 — Monitoreo del pipeline de retencion en produccion")

st.markdown(
    """
**Grupo 2** — Curso: *Computacion en la Nube para IA* · Profesora: **Diana Jaimes**

**Integrantes:**
- Gabriel Ernesto Escobar A00399291
- David Artunduaga Penagos A00396342
- Luis Manuel Rojas A00399289

---

## Contexto

La Direccion de Retencion nos entrego el consolidado de las ultimas 10 semanas
del CRM (703 clientes marcados como "en riesgo") y nos pidio investigar por que
las campanas de retencion han venido funcionando peor. **No nos pidieron un
pipeline** — nos pidieron una **explicacion**.

Este app organiza los hallazgos por directriz. Use el menu lateral para navegar.
"""
)

col1, col2, col3 = st.columns(3)
try:
    with open(REPO_ROOT / "analysis" / "hallazgos_u6.json") as f:
        H = json.load(f)
    col1.metric("Semanas analizadas", H["meta"]["n_semanas"])
    col2.metric("Clientes procesados", H["meta"]["csv_filas"])
    col3.metric(
        "Tasa de rechazo global",
        f"{H['D1_agregado']['tasa_rechazo_pct']:.1f}%",
    )
    st.info(
        "**Hallazgo principal:** El pipeline detecto correctamente el problema. "
        "El modelo NO se rompio — la poblacion cambio. Ver la pestana "
        "**Respuesta al cliente** para la explicacion completa."
    )
except FileNotFoundError:
    st.error("No se encontro `u6/analysis/hallazgos_u6.json`. Corra primero `python u6/analysis/run_analysis.py`.")

st.markdown("---")
st.caption(
    "Este servicio consume el modelo desplegado en Cloud Run (U5). "
    "Fuentes de datos: CSV `lotes_retencion_u6.csv` provisto por el cliente + "
    "X_train de U4 como baseline para el analisis de drift."
)
