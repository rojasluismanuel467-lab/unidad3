"""Consulta BigQuery — resultados y cuarentena que carga el DAG.

En el proyecto compartido de la clase el usuario NO tiene
`serviceusage.services.use`, asi que el SDK Python de google-cloud-bigquery
falla al inicializar el cliente. El CLI `bq` usa gcloud auth y no pasa por
ese check, por lo que se usa `bq head --format=json` via subprocess.

Las agregaciones (COUNT, GROUP BY) se hacen en pandas despues de traer las
filas — mucho mas simple y sin necesidad de `bigquery.jobs.create`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st


st.set_page_config(layout="wide")
st.markdown("""<style>
.block-container {padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1100px;}
h1 {font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.25rem;}
h2 {font-weight: 600; letter-spacing: -0.01em; margin-top: 2rem;}
h3 {font-weight: 600; margin-top: 1.5rem;}
[data-testid="stMetricLabel"] {font-size: 0.8rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em;}
[data-testid="stMetricValue"] {font-size: 1.8rem; font-weight: 600;}
footer, [data-testid="stDecoration"] {display: none;}
</style>""", unsafe_allow_html=True)

st.title("Consulta BigQuery")
st.caption(
    "Tablas `resultados` y `cuarentena` cargadas por el DAG "
    "`pipeline_mlops_churn`. Cada corrida deja un `run_id` unico."
)

PROJECT = os.getenv("BQ_PROJECT", "computacionnube20262")
DATASET = os.getenv("BQ_DATASET", "u6_g02_data_20260919")

with st.sidebar:
    st.text_input("BQ Project", value=PROJECT, key="bq_project")
    st.text_input("BQ Dataset", value=DATASET, key="bq_dataset")
    max_rows = st.number_input(
        "Filas a traer (max por tabla)", min_value=100, max_value=10000,
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
        ["bq", "head", f"--format=json", f"-n{n}", fq],
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
col_status_1, col_status_2 = st.columns(2)

with st.spinner("Trayendo `resultados` desde BigQuery..."):
    try:
        df_res = _bq_head("resultados", max_rows)
        col_status_1.metric("Filas en `resultados`", f"{len(df_res):,}")
    except Exception as e:
        col_status_1.error(f"No se pudo leer `resultados`: {e}")
        df_res = pd.DataFrame()

with st.spinner("Trayendo `cuarentena` desde BigQuery..."):
    try:
        df_cur = _bq_head("cuarentena", max_rows)
        col_status_2.metric("Filas en `cuarentena`", f"{len(df_cur):,}")
    except Exception as e:
        col_status_2.error(f"No se pudo leer `cuarentena`: {e}")
        df_cur = pd.DataFrame()

if df_res.empty and df_cur.empty:
    st.stop()

# ---------------------------------------------------------------------------
# Metricas por corrida
# ---------------------------------------------------------------------------
st.subheader("Corridas del DAG")

if not df_res.empty:
    df_res["customer_risk_score"] = pd.to_numeric(
        df_res["customer_risk_score"], errors="coerce"
    )
    df_res["predicted_churn"] = df_res["predicted_churn"].astype(str).str.lower() == "true"
    agg_res = (
        df_res.groupby(["run_id", "archivo"], as_index=False)
        .agg(
            n_ok=("customer_id", "count"),
            avg_risk=("customer_risk_score", "mean"),
            n_marca_churn=("predicted_churn", "sum"),
        )
    )
else:
    agg_res = pd.DataFrame(columns=["run_id", "archivo", "n_ok", "avg_risk", "n_marca_churn"])

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
    agg_cur = pd.DataFrame(columns=["run_id", "archivo", "n_cuarentena",
                                     "n_api_reject", "n_parse", "n_network"])

cruce = agg_res.merge(agg_cur, on=["run_id", "archivo"], how="outer").fillna(0)
for c in ["n_ok", "n_cuarentena", "n_marca_churn", "n_api_reject", "n_parse", "n_network"]:
    if c in cruce.columns:
        cruce[c] = cruce[c].astype(int)
cruce["n_total"] = cruce["n_ok"] + cruce["n_cuarentena"]
cruce["tasa_rechazo_%"] = (
    cruce["n_cuarentena"] / cruce["n_total"].replace(0, 1) * 100
).round(2)
cruce = cruce.sort_values("run_id", ascending=False)

st.dataframe(
    cruce[["run_id", "archivo", "n_total", "n_ok", "n_cuarentena",
           "tasa_rechazo_%", "avg_risk", "n_marca_churn"]],
    use_container_width=True, hide_index=True,
    column_config={
        "avg_risk": st.column_config.NumberColumn(format="%.3f"),
        "tasa_rechazo_%": st.column_config.NumberColumn(format="%.1f %%"),
    },
)

# ---------------------------------------------------------------------------
# Detalle de errores
# ---------------------------------------------------------------------------
if not df_cur.empty:
    st.subheader("Distribucion de errores en cuarentena")
    df_cur["http_status"] = pd.to_numeric(df_cur["http_status"], errors="coerce")
    err = (
        df_cur.groupby(["error_type", "http_status"], dropna=False, as_index=False)
        .agg(n=("customer_id", "count"))
        .sort_values("n", ascending=False)
    )
    st.dataframe(err, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Muestra cruda (util para depurar)
# ---------------------------------------------------------------------------
with st.expander("Muestra cruda de `resultados` (primeras 100 filas)"):
    st.dataframe(df_res.head(100), use_container_width=True, hide_index=True)

with st.expander("Muestra cruda de `cuarentena` (primeras 100 filas)"):
    st.dataframe(df_cur.head(100), use_container_width=True, hide_index=True)

st.caption(
    f"Fuente: `{project}.{dataset}.{{resultados,cuarentena}}`. "
    f"Lectura via `bq head --format=json` (evita serviceusage.services.use "
    "que el proyecto compartido no otorga)."
)
