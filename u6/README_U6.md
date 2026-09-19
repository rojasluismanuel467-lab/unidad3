# Unidad 6 — Monitoreo del pipeline de retención en producción

**Grupo 2** · Curso: *Computación en la Nube para IA* · Profesora: Diana Jaimes

**Integrantes:** Gabriel Escobar · David Artunduaga · Luis Rojas

Alineado con la guía `UNIDAD6_Lab_Paso_a_Paso.md` que la profesora entregó
en clase (patrón GCS → API → BigQuery `resultados` + `cuarentena`).

## Estructura

```
u6/
├── data/
│   └── lotes_retencion_u6.csv         # CSV del cliente: 10 semanas, 703 filas
├── analysis/
│   ├── run_analysis.py                # análisis exploratorio + PSI + calibración umbral
│   └── hallazgos_u6.json              # salida consumida por el Streamlit
├── dag/
│   ├── dag_pipeline_churn.py          # DAG Airflow 3.3.2 (patrón de la clase)
│   └── bigquery_ddl.sql               # DDL de dataset u6_g02_mlops_churn
├── scripts/
│   └── run_batch.py                   # script batch alternativo (sin Airflow)
└── streamlit/
    ├── app.py                         # home con nombres del grupo
    ├── pages/
    │   ├── 1_Cuarentena.py            # D1 + D2
    │   ├── 2_Drift.py                 # D3 + D4 (PSI + KS + Chi2)
    │   ├── 3_BancoPago.py             # D5
    │   ├── 4_Respuesta_Cliente.py     # D6 con timeline SRE + action items
    │   ├── 5_Prediccion_Individual.py # invoca Cloud Run U5
    │   └── 6_Consulta_BQ.py           # lee tablas resultados/cuarentena de BQ
    ├── requirements.txt
    └── Dockerfile
```

## Puesta a punto en Cloud Shell (paso a paso alineado con la guía)

### 1. Confirmar proyecto activo

```bash
gcloud config get-value project
# Debe responder: computacionnube20262
```

### 2. Verificar que la API de U5 sigue viva

```bash
gcloud run services describe u5-g02-cr-20260914 \
  --region=us-central1 \
  --format="value(status.url, status.latestReadyRevisionName)"
```

Guardar la URL:

```bash
export API_URL=$(gcloud run services describe u5-g02-cr-20260914 \
  --region=us-central1 --format='value(status.url)')/predict
echo $API_URL
```

### 3. Probar `/predict` a mano (schema de 11 campos — el nuestro, no el de la guía)

```bash
curl -s -X POST "$API_URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id":"SMOKE-001",
    "gender":"Female",
    "partner":true, "dependents":false,
    "tenure":12,
    "contract":"Month-to-month",
    "payment_method":"Electronic check",
    "monthly_charges":89.5,
    "internet_service":"Fiber optic",
    "online_security":"No",
    "tech_support":"No"
  }'
```

> Nota importante: **nuestra API tiene 11 campos**, no los 8 del ejemplo de
> la guía. En U3 removimos `SeniorCitizen` por instrucción del profesor, y en
> U4 agregamos `InternetService`, `OnlineSecurity` y `TechSupport`. El DAG
> extrae del CSV solo los campos que nuestro modelo necesita.

### 4. Crear bucket y subir el CSV del cliente

```bash
gcloud storage buckets create gs://computacionnube20262-u6-g02-batches-20260919 \
  --location=us-central1 --uniform-bucket-level-access

gcloud storage cp u6/data/lotes_retencion_u6.csv \
  gs://computacionnube20262-u6-g02-batches-20260919/input/
```

### 5. Crear dataset y tablas en BigQuery

```bash
bq query --use_legacy_sql=false --location=us-central1 \
  < u6/dag/bigquery_ddl.sql

bq ls u6_g02_mlops_churn
# Deben aparecer: resultados, cuarentena, v_metricas_por_run
```

### 6. Instalar Airflow 3.3.2

```bash
pip install "apache-airflow==3.3.2" --break-system-packages
```

⚠️ El ejecutable se llama **`apache-airflow`**, no `airflow`.

```bash
apache-airflow version
```

### 7. Inicializar Airflow

```bash
export AIRFLOW_HOME=~/airflow
export AIRFLOW__CORE__LOAD_EXAMPLES=False
apache-airflow db migrate
```

### 8. Instalar el DAG

```bash
mkdir -p ~/airflow/dags
cp u6/dag/dag_pipeline_churn.py ~/airflow/dags/

# Exporta las variables que el DAG necesita
export API_URL="<tu URL de la API U5>/predict"
export GCS_BUCKET="computacionnube20262-u6-g02-batches-20260919"
export BQ_PROJECT="computacionnube20262"
export BQ_DATASET="u6_g02_mlops_churn"

apache-airflow dags reserialize
apache-airflow dags list
# Debe aparecer: pipeline_mlops_churn
```

Si no aparece:

```bash
apache-airflow dags list-import-errors
```

### 9. Correr el pipeline sobre el CSV del cliente

```bash
apache-airflow dags test pipeline_mlops_churn \
  --conf '{"archivo": "lotes_retencion_u6.csv"}'
```

El DAG:
1. Lee `gs://<bucket>/input/lotes_retencion_u6.csv`
2. Valida el schema mínimo (columnas obligatorias)
3. Envía cada fila a `$API_URL/predict` con identity token
4. Separa 422 en cuarentena
5. Carga `resultados` y `cuarentena` a BQ
6. **Quality gate**: si `tasa_rechazo > 50%` marca FAILED (escenario drift)

### 10. Streamlit local

```bash
cd u6/streamlit
pip install -r requirements.txt
export CLOUD_RUN_URL="$API_URL"  # sin /predict
export BQ_PROJECT="computacionnube20262"
export BQ_DATASET="u6_g02_mlops_churn"
streamlit run app.py --server.port 8501 --server.enableCORS=false \
  --server.enableXsrfProtection=false
```

### 11. Streamlit desplegado a Cloud Run (recomendado)

```bash
cd u6
export PROJECT_ID=computacionnube20262

# Build (context = u6/ para copiar analysis/ y data/ sin symlinks)
docker build \
  -t us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260914/u6-g02-streamlit-20260919:v1 \
  -f streamlit/Dockerfile .

docker push us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260914/u6-g02-streamlit-20260919:v1

gcloud run deploy u6-g02-streamlit-20260919 \
  --image=us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260914/u6-g02-streamlit-20260919:v1 \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --service-account=u5-g02-sa-20260914@${PROJECT_ID}.iam.gserviceaccount.com \
  --min-instances=0 --max-instances=1 --memory=512Mi --port=8501 \
  --set-env-vars="CLOUD_RUN_URL=${API_URL%/predict},BQ_PROJECT=${PROJECT_ID},BQ_DATASET=u6_g02_mlops_churn"
```

Recuerda darle a la SA (`u5-g02-sa-20260914`) el rol `roles/bigquery.dataViewer`
sobre el dataset `u6_g02_mlops_churn` para que el Streamlit pueda leer las
tablas.

### 12. Limpieza (solo cuando cierre el ciclo, viernes 25)

```bash
gcloud run services delete u6-g02-streamlit-20260919 --region=us-central1 --quiet
```

**NO borrar** (según la guía y las Pautas):
- `u5-g02-cr-20260914` (servicio de U5)
- El bucket del modelo (`computacionnube20262-u4-class-mdl-20260914`)
- El Model Registry
- Las imágenes de Artifact Registry
- El bucket de U6 y el dataset (opcional: borrar al cierre del curso)

## Las 6 directrices — dónde encontrarlas

| # | Directriz | Ubicación |
|---|---|---|
| D1 | Umbral del DAG calibrado | Streamlit → **Cuarentena** (2.5% desde 2σ de las 4 primeras semanas) |
| D2 | Contenido de la cuarentena | Streamlit → **Cuarentena** (breakdown por campo, tipo, evolución) |
| D3 | Drift en lo que no está en cuarentena | Streamlit → **Drift** (vs training + vs primeras 4 semanas) |
| D4 | Método comparable en escala | PSI + KS + Chi² con umbral Siddiqi 2006 (Credit Risk Scorecards) |
| D5 | Qué hacer con BancoPago | Streamlit → **BancoPago** (canonicalizar, no usar como feature) |
| D6 | Respuesta al cliente | Streamlit → **Respuesta al Cliente** (qué / significa / recomiendan + timeline SRE + action items) |

## Hallazgo central para la sustentación

El modelo **NO se rompió** — la población cambió. El CRM empezó a enviar valores nuevos
de `PaymentMethod` desde 2026-08-24 (PSE, PayPal, Digital wallet, Corporate billing,
Credit card manual). PSI de `tenure` salta de 1.7 a 8.2. El pipeline lo detectó, pero
el modelo estaba scoreando población fuera de dominio. Fix inmediato: ampliar el enum
del schema; mediano plazo: reentrenar.
