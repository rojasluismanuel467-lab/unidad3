"""DAG del pipeline batch de churn — Unidad 6, Grupo 2.

Alineado con el patron de la guia de clase (Airflow 3.3.2):

    apache-airflow dags test pipeline_mlops_churn \
        --conf '{"archivo": "lotes_retencion_u6.csv"}'

Flujo:
    leer_de_bucket -> validar_schema -> llamar_api (con quarantine) ->
        cargar_a_bq (resultados + cuarentena) -> reporte_metricas

Diferencia con el ejemplo de clase (defendible):
    El servicio de U5 del Grupo 2 (u5-g02-cr-20260919) tiene 10 features
    (removimos SeniorCitizen en U3 por instruccion del profesor, agregamos
    InternetService/OnlineSecurity/TechSupport en U4). Este DAG mapea el
    CSV de 22 columnas del cliente al schema de 11 campos de nuestra API.

Grupo 2 - Gabriel Ernesto Escobar A00399291, David Artunduaga Penagos A00396342, Luis Manuel Rojas A00399289.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException

# Configuracion via env vars (Cloud Shell / Workbench)
API_URL = os.getenv("API_URL", "https://TU_SERVICE_URL/predict")
GCS_BUCKET = os.getenv("GCS_BUCKET", "u6-g02-bucket-20260919")
BQ_DATASET = os.getenv("BQ_DATASET", "u6_g02_data_20260919")
BQ_PROJECT = os.getenv("BQ_PROJECT", "computacionnube20262")
UMBRAL_CUARENTENA_PCT = float(os.getenv("UMBRAL_CUARENTENA_PCT", "2.5"))
UMBRAL_DRIFT_QUALITY_GATE_PCT = float(os.getenv("UMBRAL_DRIFT_QUALITY_GATE_PCT", "50.0"))


# ---------------------------------------------------------------------------
# Helpers (import diferidos para evitar romper el parseo del DAG)
# ---------------------------------------------------------------------------
def _fetch_id_token(audience: str) -> str:
    """ID token via gcloud CLI (evita ADC + serviceusage.services.use).

    En proyectos academicos compartidos el usuario NO tiene
    serviceusage.services.use, por lo que el SDK Python de google-cloud-*
    falla al llamar cualquier API. gcloud CLI usa un flujo diferente
    (metadata server / stored creds) que no requiere ese permiso.
    """
    result = subprocess.run(
        ["gcloud", "auth", "print-identity-token", f"--audiences={audience}"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()

    # Las cuentas de usuario no admiten --audiences en gcloud. El token
    # estándar sí puede invocar el servicio privado cuando el usuario tiene
    # roles/run.invoker; el runtime de Cloud Run usa el token con audience.
    fallback = subprocess.run(
        ["gcloud", "auth", "print-identity-token"],
        check=True, capture_output=True, text=True,
    )
    return fallback.stdout.strip()


def _yn(v):
    return str(v).strip().lower() == "yes"


def _to_payload(row: dict) -> dict[str, Any]:
    """Del CSV crudo (22 cols) al payload de NUESTRA API U5 (11 campos).

    Ignora: customerID_lookalike, SeniorCitizen, PhoneService, MultipleLines,
    OnlineBackup, DeviceProtection, StreamingTV, StreamingMovies,
    PaperlessBilling, TotalCharges, BancoPago (esta ultima analizada aparte
    porque el modelo no la conoce).

    Rechaza explicitamente NaN/None para que caigan como client_side_parse
    (json.dumps se rompe con NaN y confundiria el error como network).
    """
    import math

    def _int(v, name):
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{name} no parseable: {v!r}")
        if math.isnan(n):
            raise ValueError(f"{name} es NaN")
        return int(n)

    def _float(v, name):
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{name} no parseable: {v!r}")
        if math.isnan(n):
            raise ValueError(f"{name} es NaN")
        return n

    return {
        "customer_id": str(row["customerID"]),
        "gender": row["gender"],
        "partner": _yn(row.get("Partner")),
        "dependents": _yn(row.get("Dependents")),
        "tenure": _int(row["tenure"], "tenure"),
        "contract": row["Contract"],
        "payment_method": row["PaymentMethod"],
        "monthly_charges": _float(row["MonthlyCharges"], "monthly_charges"),
        "internet_service": row["InternetService"],
        "online_security": row["OnlineSecurity"],
        "tech_support": row["TechSupport"],
    }


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
@dag(
    dag_id="pipeline_mlops_churn",
    description="U6 Grupo 2 — batch scoring desde GCS a BigQuery via Cloud Run",
    schedule=None,  # se dispara con --conf, como pide la guia
    start_date=datetime(2026, 9, 19, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["u6", "g02", "grupo2", "churn", "mlops"],
    default_args={
        "owner": "grupo2",
        "retries": 2,
        "retry_delay": timedelta(minutes=3),
    },
    doc_md=__doc__,
)
def pipeline_mlops_churn():

    @task
    def leer_de_bucket(**context) -> dict:
        """Lee el CSV desde gs://{GCS_BUCKET}/input/{archivo} via gcloud CLI.

        Usa `gcloud storage cp` (subprocess) en vez del SDK Python para
        esquivar la exigencia de serviceusage.services.use, que en el
        proyecto compartido del curso solo tiene el owner (profesora).
        """
        import pandas as pd

        archivo = context["dag_run"].conf.get("archivo", "")
        if not archivo:
            raise ValueError(
                "Falta --conf '{\"archivo\": \"...\"}'. "
                "Ej: apache-airflow dags test pipeline_mlops_churn "
                "--conf '{\"archivo\": \"lotes_retencion_u6.csv\"}'"
            )

        tmp = f"/tmp/{archivo}"
        subprocess.run(
            ["gcloud", "storage", "cp",
             f"gs://{GCS_BUCKET}/input/{archivo}", tmp],
            check=True, capture_output=True, text=True,
        )
        df = pd.read_csv(tmp)

        run_id = f"{context['ts_nodash']}-{archivo.replace('.csv', '')}"
        print(f"[leer_de_bucket] {archivo}: {len(df)} filas, run_id={run_id}")
        return {"run_id": run_id, "archivo": archivo, "n_filas": int(len(df)), "path": tmp}

    @task
    def validar_schema(payload: dict) -> dict:
        """Chequeo minimo: columnas obligatorias presentes."""
        import pandas as pd
        df = pd.read_csv(payload["path"])
        req = {"customerID", "gender", "tenure", "Contract", "PaymentMethod",
               "MonthlyCharges", "InternetService", "OnlineSecurity", "TechSupport"}
        missing = req - set(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas obligatorias: {missing}")
        return payload

    @task
    def llamar_api(payload: dict) -> dict:
        """Envia cada fila al servicio Cloud Run; separa 422 en cuarentena."""
        import pandas as pd
        import requests

        df = pd.read_csv(payload["path"])
        token = _fetch_id_token(API_URL.rsplit("/", 1)[0])
        session = requests.Session()

        resultados: list[dict] = []
        cuarentena: list[dict] = []

        for _, row in df.iterrows():
            row_d = row.to_dict()
            try:
                body = _to_payload(row_d)
            except Exception as e:
                cuarentena.append({
                    "customer_id": str(row_d.get("customerID", "")),
                    "fecha_lote": row_d.get("fecha_lote"),
                    "http_status": None,
                    "error_type": "client_side_parse",
                    "error_detail": json.dumps({"error": str(e)}),
                    "raw": json.dumps({k: str(v) for k, v in row_d.items()}),
                })
                continue

            try:
                r = session.post(
                    API_URL, json=body, timeout=15,
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                )
            except Exception as e:
                cuarentena.append({
                    "customer_id": body["customer_id"],
                    "fecha_lote": row_d.get("fecha_lote"),
                    "http_status": None,
                    "error_type": "network",
                    "error_detail": json.dumps({"error": str(e)}),
                    "raw": json.dumps(body),
                })
                continue

            if r.status_code == 200:
                data = r.json()
                data["fecha_lote"] = row_d.get("fecha_lote")
                resultados.append(data)
            else:
                cuarentena.append({
                    "customer_id": body["customer_id"],
                    "fecha_lote": row_d.get("fecha_lote"),
                    "http_status": r.status_code,
                    "error_type": "api_reject",
                    "error_detail": r.text[:1000],
                    "raw": json.dumps(body),
                })

        # Escribe a disco temporal — la task siguiente sube a BQ
        Path("/tmp/u6_out").mkdir(exist_ok=True)
        with open(f"/tmp/u6_out/{payload['run_id']}_res.jsonl", "w") as f:
            for r in resultados:
                f.write(json.dumps(r) + "\n")
        with open(f"/tmp/u6_out/{payload['run_id']}_cur.jsonl", "w") as f:
            for r in cuarentena:
                f.write(json.dumps(r) + "\n")

        tasa = round(len(cuarentena) / max(payload["n_filas"], 1) * 100, 2)
        print(f"[llamar_api] OK={len(resultados)}  Cuarentena={len(cuarentena)}  Tasa={tasa}%")
        return {**payload, "n_ok": len(resultados), "n_cuarentena": len(cuarentena),
                "tasa_rechazo_pct": tasa}

    @task
    def cargar_a_bq(scored: dict) -> dict:
        """Carga resultados y cuarentena con jobs de carga de BigQuery.

        La cuenta de ejecución ya tiene permiso para crear jobs. Usamos
        `bq load` (load job) en vez de `bq insert` (streaming workaround),
        de modo que la corrida quede trazable en el historial de BigQuery y
        la carga sea más adecuada para un lote batch.
        """
        from datetime import datetime as _dt, timezone as _tz

        loaded_at = _dt.now(_tz.utc).isoformat()

        # Schema exacto de las tablas (ver u6-g02-sql-20260919.sql).
        # Filtramos el payload de la API para no enviar campos extra
        # (`source`, `input_file`) que la tabla `resultados` no tiene.
        RES_COLS = {
            "run_id", "archivo", "customer_id", "fecha_lote",
            "customer_risk_score", "predicted_churn", "threshold_used",
            "model_version", "predicted_at", "requested_by", "loaded_at",
        }
        CUR_COLS = {
            "run_id", "archivo", "customer_id", "fecha_lote",
            "http_status", "error_type", "error_detail", "raw",
            "quarantined_at",
        }

        def _preparar_ndjson(path_in: str, extra: dict, cols: set[str]) -> str | None:
            if not os.path.exists(path_in) or os.path.getsize(path_in) == 0:
                return None

            def _as_json_value(value: Any) -> Any:
                if value is None or isinstance(value, (dict, list, int, float, bool)):
                    return value
                try:
                    return json.loads(value)
                except (TypeError, json.JSONDecodeError):
                    return {"value": str(value)}

            path_out = path_in.replace(".jsonl", "_bq.jsonl")
            with open(path_in) as f_in, open(path_out, "w") as f_out:
                for line in f_in:
                    obj = json.loads(line)
                    obj.update(extra)
                    obj = {k: v for k, v in obj.items() if k in cols}
                    for json_col in ("error_detail", "raw"):
                        if json_col in obj:
                            obj[json_col] = _as_json_value(obj[json_col])
                    f_out.write(json.dumps(obj, default=str) + "\n")
            return path_out

        def _bq_load(tabla: str, ndjson_path: str) -> None:
            fq = f"{BQ_PROJECT}:{BQ_DATASET}.{tabla}"
            result = subprocess.run(
                [
                    "bq", "load",
                    f"--project_id={BQ_PROJECT}",
                    "--location=us-central1",
                    "--source_format=NEWLINE_DELIMITED_JSON",
                    "--replace=false",
                    fq,
                    ndjson_path,
                ],
                check=False, capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise ValueError(
                    f"[bq load] tabla={tabla} rc={result.returncode}\n"
                    f"stderr={result.stderr[:1000]}\nstdout={result.stdout[:500]}"
                )

        # ---- resultados ----
        res_extra = {"run_id": scored["run_id"], "archivo": scored["archivo"],
                     "loaded_at": loaded_at}
        res_path = _preparar_ndjson(
            f"/tmp/u6_out/{scored['run_id']}_res.jsonl", res_extra, RES_COLS
        )
        if res_path:
            # Sin schema en la línea de comandos: el load job usa el schema
            # ya definido en la tabla y conserva sus modos REQUIRED/NULLABLE.
            _bq_load("resultados", res_path)
            n_res = sum(1 for _ in open(res_path))
            print(f"[cargar_a_bq] resultados: {n_res} filas via BigQuery load job")

        # ---- cuarentena ----
        cur_extra = {"run_id": scored["run_id"], "archivo": scored["archivo"],
                     "quarantined_at": loaded_at}
        cur_path = _preparar_ndjson(
            f"/tmp/u6_out/{scored['run_id']}_cur.jsonl", cur_extra, CUR_COLS
        )
        if cur_path:
            _bq_load("cuarentena", cur_path)
            n_cur = sum(1 for _ in open(cur_path))
            print(f"[cargar_a_bq] cuarentena: {n_cur} filas via BigQuery load job")

        return scored

    @task
    def quality_gate(scored: dict) -> dict:
        """Si tasa_rechazo > umbral_drift, marca el DAG como FAILED (como en la guia)."""
        tasa = scored["tasa_rechazo_pct"]
        if tasa > UMBRAL_DRIFT_QUALITY_GATE_PCT:
            raise ValueError(
                f"[FAILED] tasa_rechazo={tasa}% > umbral_drift={UMBRAL_DRIFT_QUALITY_GATE_PCT}%. "
                "Escenario drift: se paraliza la corrida."
            )
        if tasa > UMBRAL_CUARENTENA_PCT:
            print(f"[WARN] tasa_rechazo={tasa}% > umbral_cuarentena={UMBRAL_CUARENTENA_PCT}%. "
                  "Se registra pero no se pausa.")
        return scored

    @task
    def reporte_metricas(scored: dict) -> None:
        """Print de las metricas finales del run — visible en el log de Airflow."""
        print(
            f"{scored['archivo']}"
            f"   {scored['n_filas']:3d} total"
            f"   {scored['n_ok']:3d} OK"
            f"   {scored['n_cuarentena']:3d} rechazados"
            f"   {scored['tasa_rechazo_pct']:5.1f}%"
            f"   run_id={scored['run_id']}"
        )

    # Wiring
    p1 = leer_de_bucket()
    p2 = validar_schema(p1)
    p3 = llamar_api(p2)
    p4 = cargar_a_bq(p3)
    p5 = quality_gate(p4)
    reporte_metricas(p5)


dag = pipeline_mlops_churn()
