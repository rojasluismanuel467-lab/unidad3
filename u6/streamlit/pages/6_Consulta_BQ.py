"""Consulta BigQuery — resultados y cuarentena escritos por el DAG.

Alineado con el patron de la guia de clase: el DAG carga a
`u6_g02_data_20260919.resultados` y `u6_g02_data_20260919.cuarentena`.
Esta pagina las lee y muestra las metricas por run.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

st.title(":cloud: Consulta BigQuery — resultados del pipeline")

st.markdown(
    """
Esta pagina lee de BigQuery las tablas que el DAG `pipeline_mlops_churn`
carga cuando procesa un archivo del bucket. Es la evidencia "en la nube"
que la profesora pidio dejar activa hasta el viernes 25.

**Prerequisito**: haber corrido al menos una vez el DAG con
`apache-airflow dags test pipeline_mlops_churn --conf '{"archivo": "..."}'`.
"""
)

PROJECT = os.getenv("BQ_PROJECT", "computacionnube20262")
DATASET = os.getenv("BQ_DATASET", "u6_g02_data_20260919")

with st.sidebar:
    st.text_input("BQ Project", value=PROJECT, key="bq_project")
    st.text_input("BQ Dataset", value=DATASET, key="bq_dataset")

project = st.session_state.get("bq_project", PROJECT)
dataset = st.session_state.get("bq_dataset", DATASET)

try:
    from google.cloud import bigquery
except ImportError:
    st.error("Falta `google-cloud-bigquery` en requirements.txt. Instalar y re-desplegar.")
    st.stop()

try:
    client = bigquery.Client(project=project)
except Exception as e:
    st.error(f"No pude construir el cliente BQ: {e}")
    st.caption("Asegura que la SA del Streamlit tenga `roles/bigquery.dataViewer` "
               "sobre el dataset.")
    st.stop()

# ---------------------------------------------------------------------------
# Vista: metricas por run
# ---------------------------------------------------------------------------
st.header(":bar_chart: Metricas por corrida del DAG")
try:
    q = f"""
    SELECT
      run_id, archivo,
      MIN(loaded_at) AS iniciado_en,
      COUNT(*) AS n_ok,
      AVG(customer_risk_score) AS avg_risk,
      COUNTIF(predicted_churn) AS n_marca_churn
    FROM `{project}.{dataset}.resultados`
    GROUP BY run_id, archivo
    ORDER BY iniciado_en DESC
    LIMIT 20
    """
    df_r = client.query(q).to_dataframe()
    st.dataframe(df_r, use_container_width=True, hide_index=True)
except Exception as e:
    st.warning(f"No pude consultar resultados: {e}")
    df_r = pd.DataFrame()

st.header(":triangular_flag_on_post: Cuarentena por corrida")
try:
    q = f"""
    SELECT
      run_id, archivo,
      COUNT(*) AS n_cuarentena,
      COUNTIF(error_type = 'api_reject') AS n_api_reject,
      COUNTIF(error_type = 'client_side_parse') AS n_parse_fail,
      COUNTIF(error_type = 'network') AS n_network
    FROM `{project}.{dataset}.cuarentena`
    GROUP BY run_id, archivo
    ORDER BY MIN(quarantined_at) DESC
    LIMIT 20
    """
    df_c = client.query(q).to_dataframe()
    st.dataframe(df_c, use_container_width=True, hide_index=True)
except Exception as e:
    st.warning(f"No pude consultar cuarentena: {e}")
    df_c = pd.DataFrame()

# ---------------------------------------------------------------------------
# Cruce: tasa de rechazo por run
# ---------------------------------------------------------------------------
if not df_r.empty and not df_c.empty:
    st.header(":chart_with_upwards_trend: Tasa de rechazo por corrida")
    cruce = df_r.merge(
        df_c[["run_id", "archivo", "n_cuarentena"]],
        on=["run_id", "archivo"], how="outer",
    ).fillna(0)
    cruce["n_total"] = cruce["n_ok"] + cruce["n_cuarentena"]
    cruce["tasa_rechazo_pct"] = (
        cruce["n_cuarentena"] / cruce["n_total"].replace(0, 1) * 100
    ).round(2)
    st.dataframe(
        cruce[["run_id", "archivo", "n_total", "n_ok", "n_cuarentena",
               "tasa_rechazo_pct", "avg_risk"]],
        use_container_width=True, hide_index=True,
    )

st.markdown("---")
st.subheader(":mag: Detalle de errores en la cuarentena")
try:
    q = f"""
    SELECT error_type, http_status, COUNT(*) AS n
    FROM `{project}.{dataset}.cuarentena`
    GROUP BY error_type, http_status
    ORDER BY n DESC
    """
    df_e = client.query(q).to_dataframe()
    st.dataframe(df_e, use_container_width=True, hide_index=True)
except Exception as e:
    st.warning(f"No pude consultar errores: {e}")
