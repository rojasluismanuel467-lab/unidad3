# Unidad 6 — Monitoreo del pipeline de retención en producción

**Grupo 2** · Curso: *Computación en la Nube para IA* · Profesora: Diana Jaimes

**Integrantes:** Gabriel Escobar · David Artunduaga · Luis Rojas

## Estructura

```
u6/
├── data/
│   └── lotes_retencion_u6.csv         # CSV entregado por el cliente (10 semanas, 703 filas)
├── analysis/
│   ├── run_analysis.py                # análisis exploratorio + drift + calibración umbral
│   └── hallazgos_u6.json              # salida consumida por el Streamlit
├── scripts/
│   └── run_batch.py                   # script batch: lee CSV, valida, invoca Cloud Run, cuarentena 422
├── dag/
│   └── churn_nightly.py               # DAG Airflow (TaskFlow) que envuelve run_batch.py
└── streamlit/
    ├── app.py                         # home con nombres del grupo
    ├── pages/
    │   ├── 1_Cuarentena.py            # D1 + D2
    │   ├── 2_Drift.py                 # D3 + D4
    │   ├── 3_BancoPago.py             # D5
    │   ├── 4_Respuesta_Cliente.py     # D6
    │   └── 5_Prediccion_Individual.py # invoca Cloud Run U5 con identity token
    ├── requirements.txt
    └── Dockerfile
```

## Correr el análisis (produce hallazgos_u6.json)

```bash
cd u6/analysis
python run_analysis.py
```

Consume `../data/lotes_retencion_u6.csv` y `../../artifacts/X_train.pkl` (baseline de U4).

## Correr el Streamlit localmente

```bash
cd u6/streamlit
pip install -r requirements.txt
export CLOUD_RUN_URL="https://u5-g02-cr-20260914-xxxxx.a.run.app"
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json
streamlit run app.py
```

Abre `http://localhost:8501`.

## Deploy del Streamlit a Cloud Run

```bash
cd u6
export PROJECT_ID=computacionnube20262

# Build (context = u6/ para copiar analysis/ y data/ reales, no symlinks)
docker build -t us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260914/u6-g02-streamlit-20260919:v1 -f streamlit/Dockerfile .

# Push
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260914/u6-g02-streamlit-20260919:v1

# Deploy (usa el mismo SA de U5 que ya tiene run.invoker)
gcloud run deploy u6-g02-streamlit-20260919 \
  --image=us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260914/u6-g02-streamlit-20260919:v1 \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --service-account=u5-g02-sa-20260914@${PROJECT_ID}.iam.gserviceaccount.com \
  --min-instances=0 \
  --max-instances=1 \
  --memory=512Mi \
  --port=8501 \
  --set-env-vars="CLOUD_RUN_URL=https://u5-g02-cr-20260914-XXXXX.a.run.app"
```

## Correr run_batch.py directamente

```bash
python u6/scripts/run_batch.py \
  --csv u6/data/lotes_retencion_u6.csv \
  --url https://u5-g02-cr-20260914-xxxxx.a.run.app \
  --out-dir u6/data/outputs \
  --umbral-cuarentena-pct 2.5
```

Exit code 2 si la tasa de rechazo supera el umbral calibrado (para uso desde el DAG).

## Ejecutar el DAG local con Airflow standalone

```bash
pip install "apache-airflow==2.10.*" "apache-airflow-providers-google"
export AIRFLOW_HOME=$PWD/airflow_home
export AIRFLOW__CORE__DAGS_FOLDER=$PWD/u6/dag
export CLOUD_RUN_URL="https://u5-g02-cr-20260914-xxxxx.a.run.app"
export CSV_INPUT_PATH="$PWD/u6/data/lotes_retencion_u6.csv"
export OUT_DIR="$PWD/u6/data/outputs"

airflow standalone
```

Abre `http://localhost:8080`, activa el DAG `u6_g02_churn_nightly_20260919`.

## Resumen de las 6 directrices

| # | Directriz | Ubicación en el entregable |
|---|---|---|
| D1 | Umbral del DAG calibrado | Streamlit → **Cuarentena** (2.5% calculado desde 2σ de las 4 primeras semanas) |
| D2 | Contenido de la cuarentena | Streamlit → **Cuarentena** (breakdown por campo, tipo de error, evolución) |
| D3 | Drift en lo que no está en cuarentena | Streamlit → **Drift** (vs X_train de U4 + vs primeras 4 semanas) |
| D4 | Método comparable en escala | PSI + KS + Chi2 (todos escalados, umbral 0.25 calibrado por Verbraken 2013) |
| D5 | Qué hacer con BancoPago | Streamlit → **BancoPago** (decisión: canonicalizar, no usar como feature) |
| D6 | Respuesta al cliente | Streamlit → **Respuesta al Cliente** (qué pasó / qué significa / qué recomendamos) |

## Hallazgo principal

El modelo NO se rompió — la población cambió. El CRM empezó a enviar valores nuevos
de `PaymentMethod` desde la semana 2026-08-24 (PSE, PayPal, Digital wallet, etc.),
y en las últimas 2 semanas el PSI de `tenure` pasa de 1.7 a 8.2 (drift material extremo,
30x sobre el umbral). El pipeline lo detectó. Las campañas están usando un score
que fue entrenado sobre una población que ya no existe.
