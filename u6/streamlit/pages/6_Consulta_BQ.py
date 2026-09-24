"""Consulta BigQuery — resultados y cuarentena que carga el DAG.

La cuenta de servicio del monitor tiene acceso de lectura al dataset y
permiso para crear jobs de consulta. Se usa el cliente oficial de BigQuery
para ejecutar consultas reales y traer el lote más reciente de cada tabla.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, kpi_row, footer

apply_page_config(page_title="Consulta BQ · Monitor U6")
sidebar_branding()

page_header(
    "Consulta BigQuery",
    "Tablas `resultados` y `cuarentena` que carga el DAG `pipeline_mlops_churn`. "
    "Cada corrida deja un `run_id` único.",
    directriz="Datos en la nube",
)

PROJECT = os.getenv("BQ_PROJECT", "computacionnube20262")
DATASET = os.getenv("BQ_DATASET", "u6_g02_data_20260919")

with st.sidebar:
    st.text_input("BQ Project", value=PROJECT, key="bq_project")
    st.text_input("BQ Dataset", value=DATASET, key="bq_dataset")
    max_rows = st.number_input(
        "Filas por tabla", min_value=100, max_value=10000,
        value=2000, step=500,
    )

project = st.session_state.get("bq_project", PROJECT)
dataset = st.session_state.get("bq_dataset", DATASET)


@st.cache_data(ttl=60, show_spinner=False)
def _query_rows(project_id: str, dataset_id: str, tabla: str, order_col: str, n: int) -> pd.DataFrame:
    """Ejecuta un query job y devuelve las filas más recientes de una tabla."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
        raise ValueError("BQ Project contiene caracteres no permitidos")
    if not re.fullmatch(r"[A-Za-z0-9_]+", dataset_id):
        raise ValueError("BQ Dataset contiene caracteres no permitidos")
    if tabla not in {"resultados", "cuarentena"}:
        raise ValueError("Tabla no permitida")
    if order_col not in {"loaded_at", "quarantined_at"}:
        raise ValueError("Columna de orden no permitida")

    client = bigquery.Client(project=project_id)
    query = (
        f"SELECT * FROM `{project_id}.{dataset_id}.{tabla}` "
        f"ORDER BY {order_col} DESC LIMIT @limit"
    )
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("limit", "INT64", int(n))]
    )
    job = client.query(query, job_config=config, location=os.getenv("BQ_LOCATION", "us-central1"))
    return job.result().to_dataframe()


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
error_res = error_cur = None

with st.spinner("Trayendo `resultados`..."):
    try:
        df_res = _query_rows(project, dataset, "resultados", "loaded_at", max_rows)
    except Exception as e:
        df_res = pd.DataFrame()
        error_res = str(e)

with st.spinner("Trayendo `cuarentena`..."):
    try:
        df_cur = _query_rows(project, dataset, "cuarentena", "quarantined_at", max_rows)
    except Exception as e:
        df_cur = pd.DataFrame()
        error_cur = str(e)

kpi_row([
    ("Filas en resultados", f"{len(df_res):,}",
     "Predicciones OK cargadas en BQ (limite: N filas del sidebar)"),
    ("Filas en cuarentena", f"{len(df_cur):,}",
     "Rechazos por 422/network/parse cargados en BQ"),
    ("Proyecto", project, None),
    ("Dataset", dataset, None),
])

if error_res:
    st.error(f"No se pudieron leer los `resultados`.  \n`{error_res}`")
if error_cur:
    st.error(f"No se pudo leer la `cuarentena`.  \n`{error_cur}`")

if df_res.empty and df_cur.empty:
    st.stop()

# ---------------------------------------------------------------------------
# Corridas del DAG
# ---------------------------------------------------------------------------
st.header("Corridas del DAG")
st.caption("Una fila por `run_id`, ordenadas por la corrida más reciente.")

if not df_res.empty:
    df_res["customer_risk_score"] = pd.to_numeric(
        df_res["customer_risk_score"], errors="coerce"
    )
    df_res["predicted_churn"] = (
        df_res["predicted_churn"].astype(str).str.lower() == "true"
    )
    agg_res = (
        df_res.groupby(["run_id", "archivo"], as_index=False)
        .agg(
            n_ok=("customer_id", "count"),
            avg_risk=("customer_risk_score", "mean"),
            n_marca_churn=("predicted_churn", "sum"),
        )
    )
else:
    agg_res = pd.DataFrame(
        columns=["run_id", "archivo", "n_ok", "avg_risk", "n_marca_churn"]
    )

if not df_cur.empty:
    agg_cur = (
        df_cur.groupby(["run_id", "archivo"], as_index=False)
        .agg(
            n_cuarentena=("customer_id", "count"),
            n_api_reject=("error_type", lambda s: (s == "api_reject").sum()),
            n_parse=("error_type", lambda s: (s == "client_side_parse").sum()),
            n_network=("error_type", lambda s: (s == "network").sum()),
        )
    )
else:
    agg_cur = pd.DataFrame(
        columns=["run_id", "archivo", "n_cuarentena",
                 "n_api_reject", "n_parse", "n_network"]
    )

cruce = agg_res.merge(agg_cur, on=["run_id", "archivo"], how="outer").fillna(0)
for c in ["n_ok", "n_cuarentena", "n_marca_churn",
          "n_api_reject", "n_parse", "n_network"]:
    if c in cruce.columns:
        cruce[c] = cruce[c].astype(int)
cruce["n_total"] = cruce["n_ok"] + cruce["n_cuarentena"]
cruce["tasa_rechazo_pct"] = (
    cruce["n_cuarentena"] / cruce["n_total"].replace(0, 1) * 100
).round(2)
cruce = cruce.sort_values("run_id", ascending=False)

st.dataframe(
    cruce[["run_id", "archivo", "n_total", "n_ok", "n_cuarentena",
           "tasa_rechazo_pct", "avg_risk", "n_marca_churn"]],
    use_container_width=True, hide_index=True,
    column_config={
        "n_total": st.column_config.NumberColumn("N total", format="%d"),
        "n_ok": st.column_config.NumberColumn("N OK", format="%d"),
        "n_cuarentena": st.column_config.NumberColumn("N cuarentena", format="%d"),
        "avg_risk": st.column_config.NumberColumn("Risk promedio", format="%.3f"),
        "tasa_rechazo_pct": st.column_config.NumberColumn(
            "Rechazo", format="%.1f %%"),
        "n_marca_churn": st.column_config.NumberColumn(
            "N marca churn", format="%d"),
    },
)

# ---------------------------------------------------------------------------
# Detalle de errores
# ---------------------------------------------------------------------------
if not df_cur.empty:
    st.header("Distribución de errores en cuarentena")
    df_cur["http_status"] = pd.to_numeric(df_cur["http_status"], errors="coerce")
    err = (
        df_cur.groupby(["error_type", "http_status"], dropna=False, as_index=False)
        .agg(n=("customer_id", "count"))
        .sort_values("n", ascending=False)
    )
    st.dataframe(
        err, use_container_width=True, hide_index=True,
        column_config={"n": st.column_config.NumberColumn("N", format="%d")},
    )

# ---------------------------------------------------------------------------
# Muestra cruda
# ---------------------------------------------------------------------------
with st.expander("Muestra cruda — `resultados` (100 filas)"):
    st.dataframe(df_res.head(100), use_container_width=True, hide_index=True)

with st.expander("Muestra cruda — `cuarentena` (100 filas)"):
    st.dataframe(df_cur.head(100), use_container_width=True, hide_index=True)

footer(fuentes=[f"{project}.{dataset}.resultados", f"{project}.{dataset}.cuarentena"])
