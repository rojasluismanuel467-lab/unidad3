"""Consulta BigQuery — resultados y cuarentena que carga el DAG.

En el proyecto compartido de la clase el usuario NO tiene
`serviceusage.services.use`, asi que el SDK Python de google-cloud-bigquery
falla al inicializar el cliente. El CLI `bq` usa gcloud auth y no pasa por
ese check, por lo que se usa `bq head --format=json` via subprocess.

Las agregaciones (COUNT, GROUP BY) se hacen en pandas despues de traer las
filas — mas simple y sin necesidad de `bigquery.jobs.create`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, kpi_row, footer

apply_page_config(page_title="Consulta BQ · Monitor U6")
sidebar_branding()

page_header(
    "Consulta BigQuery",
    "Tablas `resultados` y `cuarentena` que carga el DAG `pipeline_mlops_churn`. "
    "Cada corrida deja un `run_id` unico.",
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


def _bq_head(tabla: str, n: int) -> pd.DataFrame:
    """Devuelve las primeras N filas de una tabla via `bq head --format=json`.

    Alternativa al SDK Python cuando el proyecto no otorga serviceusage.use.
    """
    if not shutil.which("bq"):
        raise RuntimeError(
            "El CLI `bq` no esta disponible en este container. "
            "Instalar `google-cloud-sdk` o correr esta app desde Cloud Shell."
        )
    fq = f"{project}:{dataset}.{tabla}"
    result = subprocess.run(
        ["bq", "head", "--format=json", f"-n{n}", fq],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`bq head` fallo (rc={result.returncode}): {result.stderr.strip()[:500]}"
        )
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
error_res = error_cur = None

with st.spinner("Trayendo `resultados`..."):
    try:
        df_res = _bq_head("resultados", max_rows)
    except Exception as e:
        df_res = pd.DataFrame()
        error_res = str(e)

with st.spinner("Trayendo `cuarentena`..."):
    try:
        df_cur = _bq_head("cuarentena", max_rows)
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
    st.error(f"No se pudo leer `resultados`.  \n`{error_res}`")
if error_cur:
    st.error(f"No se pudo leer `cuarentena`.  \n`{error_cur}`")

if df_res.empty and df_cur.empty:
    st.stop()

# ---------------------------------------------------------------------------
# Corridas del DAG
# ---------------------------------------------------------------------------
st.header("Corridas del DAG")
st.caption("Una fila por `run_id`. Ordenadas por corrida mas reciente primero.")

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
    st.header("Distribucion de errores en cuarentena")
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
