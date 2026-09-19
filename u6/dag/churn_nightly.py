"""DAG nocturno de batch scoring — consume el servicio Cloud Run de U5.

Estructura (TaskFlow API):

    extract_csv -> validate -> score_via_api (con quarantine) -> load_to_bq
                                                  \\-> emit_metrics
                                                  \\-> drift_check (quality gate)

Grupo 2 - Gabriel Escobar, David Artunduaga, Luis Rojas.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.decorators import dag, task, task_group
from airflow.exceptions import AirflowSkipException

# Add scripts/ al path para reusar run_batch.py sin instalar como paquete
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# ----- Configuracion via Variables de Airflow / env -----
CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL", "")
CSV_INPUT_PATH = os.getenv("CSV_INPUT_PATH", "/opt/airflow/data/lotes_retencion_u6.csv")
OUT_DIR = os.getenv("OUT_DIR", "/opt/airflow/data/outputs")
UMBRAL_CUARENTENA_PCT = float(os.getenv("UMBRAL_CUARENTENA_PCT", "2.5"))
UMBRAL_PSI_ALERTA = float(os.getenv("UMBRAL_PSI_ALERTA", "0.25"))


@dag(
    dag_id="u6_g02_churn_nightly_20260919",
    description="Batch scoring nocturno consumiendo el servicio Cloud Run U5",
    schedule="0 2 * * *",
    start_date=datetime(2026, 9, 19, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["u6", "g02", "churn", "batch-scoring", "grupo2"],
    default_args={
        "owner": "grupo2",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "email_on_failure": False,
    },
    doc_md=__doc__,
)
def churn_nightly():

    @task
    def extract_csv() -> str:
        """Lee el CSV crudo del lote a scorear."""
        import pandas as pd
        df = pd.read_csv(CSV_INPUT_PATH)
        out = f"{OUT_DIR}/_extracted.csv"
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        return out

    @task
    def validate_schema(extracted_path: str) -> str:
        """Chequea que las columnas requeridas esten presentes."""
        import pandas as pd
        df = pd.read_csv(extracted_path)
        required = {"customerID", "gender", "tenure", "Contract", "PaymentMethod",
                    "MonthlyCharges", "InternetService", "OnlineSecurity",
                    "TechSupport"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas: {missing}")
        return extracted_path

    @task_group(group_id="score")
    def score_group(validated_path: str):

        @task
        def score_via_api(path: str) -> dict:
            """Invoca /predict fila a fila; separa 422 en cuarentena."""
            import pandas as pd
            from run_batch import score_batch  # type: ignore
            df = pd.read_csv(path)
            predicciones, cuarentena, resumen = score_batch(df, CLOUD_RUN_URL)

            out = Path(OUT_DIR)
            out.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(predicciones).to_csv(out / "predicciones.csv", index=False)
            with open(out / "cuarentena.jsonl", "w") as f:
                for r in cuarentena:
                    f.write(json.dumps(r, default=str) + "\n")
            with open(out / "resumen.json", "w") as f:
                json.dump(resumen, f, indent=2)
            return resumen

        @task
        def emit_metrics(resumen: dict) -> dict:
            """Publica metricas al log de Airflow y (opcional) a BQ."""
            print(f"METRICS batch_id={resumen['batch_id']} "
                  f"n_total={resumen['n_total']} "
                  f"tasa_rechazo={resumen['tasa_rechazo']}")
            return resumen

        @task
        def quality_gate_cuarentena(resumen: dict) -> dict:
            """Quality gate: si tasa_rechazo > umbral, skipea downstream."""
            if resumen["tasa_rechazo"] > UMBRAL_CUARENTENA_PCT:
                print(f"ALARMA: tasa_rechazo={resumen['tasa_rechazo']}% > "
                      f"umbral={UMBRAL_CUARENTENA_PCT}%. Se pausa el load a BQ.")
                raise AirflowSkipException("Cuarentena arriba del umbral")
            return resumen

        r = score_via_api(validated_path)
        emit_metrics(r)
        return quality_gate_cuarentena(r)

    @task
    def drift_check(resumen: dict) -> dict:
        """Ejecuta el analisis de drift (PSI vs X_train de U4)."""
        # Se apoya en el JSON de hallazgos ya generado por run_analysis.py
        hallazgos = Path("/opt/airflow/analysis/hallazgos_u6.json")
        if not hallazgos.exists():
            print("Sin hallazgos precalculados, omito drift_check.")
            return resumen
        with open(hallazgos) as f:
            H = json.load(f)
        psi_prom = H.get("D6_respuesta_cliente", {}).get(
            "que_paso", {}
        ).get("psi_promedio_por_feature_vs_training", {})
        alertas = [f for f, v in psi_prom.items() if v > UMBRAL_PSI_ALERTA]
        if alertas:
            print(f"DRIFT MATERIAL detectado en features: {alertas}")
        return resumen

    @task
    def load_to_bq(resumen: dict) -> None:
        """Placeholder — en Workbench se activa el BigQueryInsertJobOperator con MERGE."""
        print(f"[dry-run] cargaria predicciones a BQ. Resumen: {resumen}")

    e = extract_csv()
    v = validate_schema(e)
    scored = score_group(v)
    drifted = drift_check(scored)
    load_to_bq(drifted)


dag = churn_nightly()
