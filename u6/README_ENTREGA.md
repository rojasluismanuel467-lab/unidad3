# Trabajo Final Unidad 6 — Grupo 2

**Curso:** Computación en la Nube para IA — Universidad Icesi
**Profesora:** Diana Jaimes
**Fecha:** 2026-09-19

## Integrantes

| Nombre | Código |
|---|---|
| Gabriel Ernesto Escobar | A00399291 |
| David Artunduaga Penagos | A00396342 |
| Luis Manuel Rojas | A00399289 |

---

## Recursos desplegados

### Cloud Run
| Servicio | URL | Revisión |
|---|---|---|
| U5 API (churn scoring) | `https://u5-g02-cr-20260914-978302928352.us-central1.run.app` | `00002-rfl` (v2, tenure fix) |
| U6 Streamlit (monitor) | `https://u6-g02-cr-20260919-978302928352.us-central1.run.app` | `00009-bgf` (v5) |

Ambos con `--no-allow-unauthenticated`, min-instances 0, max-instances 1, SA `u5-g02-sa-20260914@computacionnube20262.iam.gserviceaccount.com`.

### Google Cloud Storage
- **Bucket:** `u6-g02-bucket-20260919` (us-central1)
- **Archivo:** `input/lotes_retencion_u6.csv` (703 filas, 10 semanas)

### BigQuery
- **Dataset:** `computacionnube20262.u6_g02_data_20260919`
- **Tablas:** `resultados` (1,320 filas), `cuarentena` (789 filas)
- **Vista:** `v_metricas_por_run`

### Artifact Registry
- **Repo:** `us-central1-docker.pkg.dev/computacionnube20262/u5-g02-repo-20260914`
- **Imágenes:** `u5-g02-api:v2`, `u6-g02-streamlit:v5`

### GitHub
- **Repo:** https://github.com/rojasluismanuel467-lab/unidad3
- **Último commit al momento de entrega:** `d99713c`
- **Estructura U6:** `u6/dag/` (DAG + DDL SQL) · `u6/analysis/` (script + `hallazgos_u6.json`) · `u6/streamlit/` (7 páginas + Dockerfile) · `u6/scripts/run_batch.py`

---

## Hallazgo principal

**El pipeline detectó la degradación antes de que impactara más campañas de retención. El modelo no se rompió — la población cambió.**

### Evidencia numérica (corrida `20260919T213731-lotes_retencion_u6`)

- **703 clientes procesados** en 10 semanas
- **5.12% de rechazo global** (36 filas en cuarentena)
- **Drift concentrado en las últimas 2 semanas**:
  - 2026-08-24: **18.7%** rechazo (17 filas)
  - 2026-08-31: **43.9%** rechazo (29 filas)
- **PSI vs training**: `tenure` = 1.7 → 5.0 → 8.2 (drift material extremo, umbral 0.25 según Siddiqi 2006)
- **80% de los rechazos son valores nuevos de PaymentMethod** (PSE, PayPal, Digital wallet, Corporate billing) que el enum de U5 no contempla

### 3 tipos de problema detectados (validando el cierre del loop MLOps)

1. **Fallo operacional** — corrida `20260919T202148` con URL mal configurado: 703 filas en cuarentena como `network`. Prueba de que el pipeline captura fallos de infraestructura, no solo semánticos.
2. **Drift semántico** — PSE / PayPal / Digital wallet: 26 filas en `api_reject`. Fix: ampliar enum en `service/app/schemas.py`.
3. **Bug del contrato** — `tenure ≤ 100` en `schemas.py` rechazaba clientes legítimos con 10+ años de antigüedad. **Detectado con el pipeline, no con EDA**. Fix aplicado, recuperó 14 clientes (de 50 → 36 cuarentena).

---

## Directrices D1-D6

Cada directriz tiene una página del dashboard con evidencia numérica. Ver screenshots adjuntos.

| # | Directriz | Página del monitor | Hallazgo clave |
|---|---|---|---|
| D1 | Umbral del DAG calibrado | `Cuarentena` | 2σ = 8.9% con 10 semanas de historia (baseline vs 20% a dedo) |
| D2 | Contenido de la cuarentena | `Cuarentena` | 49% son valores nuevos de PaymentMethod, no data mala |
| D3 | Drift PSI vs training | `Drift` | `tenure` y `MonthlyCharges` con drift material; `Contract` estable |
| D4 | Método comparable entre features | `Drift` | PSI + KS-test para numéricas; chi² para categóricas |
| D5 | Columna nueva BancoPago | `BancoPago` | Decisión: ignorar como feature + canonicalizar. 3 alternativas descartadas |
| D6 | Respuesta al cliente | `Respuesta Cliente` | 4 recomendaciones (inmediato/corto/mediano/largo) + timeline SRE + 9 action items |

---

## Cómo correr localmente

### Correr el DAG

```bash
export API_URL="$(gcloud run services describe u5-g02-cr-20260914 --region=us-central1 --format='value(status.url)')/predict"
export GCS_BUCKET="u6-g02-bucket-20260919"
export BQ_DATASET="u6_g02_data_20260919"
export BQ_PROJECT="computacionnube20262"
export AIRFLOW_HOME="$HOME/airflow"
export PATH="$HOME/.local/bin:$PATH"

cp u6/dag/dag_pipeline_churn.py ~/airflow/dags/
apache-airflow dags test pipeline_mlops_churn \
  --conf '{"archivo": "lotes_retencion_u6.csv"}'
```

### Correr el Streamlit

```bash
cd u6/streamlit
pip install -r requirements.txt
streamlit run app.py --server.port=8080 \
  --server.enableCORS=false --server.enableXsrfProtection=false
```

En Cloud Shell: abrir Web Preview en puerto 8080.

### Ver el Streamlit desplegado en Cloud Run

```bash
gcloud run services proxy u6-g02-cr-20260919 --region=us-central1
```
Y abrir `http://localhost:8080` en el navegador (requiere `roles/run.invoker`).

---

## Notas técnicas importantes

### Bypass de `serviceusage.services.use`

En el proyecto compartido `computacionnube20262` los usuarios estudiantes no tienen `serviceusage.services.use`, lo que hace que los SDK Python de `google-cloud-*` fallen al inicializar cualquier cliente. La solución fue reescribir las tres integraciones críticas usando el CLI de gcloud (subprocess), que usa un flujo de auth diferente y no pasa por ese check:

- `leer_de_bucket` (DAG): `gcloud storage cp` en vez de `storage.Client()`
- `llamar_api` (DAG): `gcloud auth print-identity-token` en vez de `id_token.fetch_id_token()`
- `cargar_a_bq` (DAG): `bq insert` (streaming) en vez de `bigquery.Client().insert_rows_json()`
- `6_Consulta_BQ.py` (Streamlit): `bq head --format=json` en vez de `bigquery.Client().query()`
- `5_Prediccion_Individual.py` (Streamlit): `gcloud run services describe` para autodetectar URL de U5

### Nomenclatura por Pautas GCP del curso

- Recursos con `-` (guion medio): `u6-g02-cr-20260919`, `u6-g02-bucket-20260919`, `u5-g02-repo-20260914`
- Datasets/tablas BigQuery con `_` (guion bajo): `u6_g02_data_20260919`
- Formato: `uN-gNN-<tipo>-YYYYMMDD`

---

## Screenshots

_Los PNGs de las 7 páginas del monitor van en la carpeta `screenshots/` de esta entrega._

1. `01_home.png` — Home con 4 KPIs y catálogo de vistas
2. `02_cuarentena.png` — Umbral 2σ + gráfico semanal + casos concretos
3. `03_drift.png` — PSI + KS + chi² + sesgo de selección
4. `04_bancopago.png` — Cobertura + variantes + 4 alternativas descartadas
5. `05_respuesta_cliente.png` — Semáforo + timeline SRE + action items
6. `06_prediccion_individual.png` — Predicción en vivo con respuesta del API
7. `07_consulta_bq.png` — 3 corridas del DAG con distribución de errores

---

## Anexos

- `u6/dag/u6-g02-sql-20260919.sql` — DDL de las tablas + vista de métricas
- `u6/dag/dag_pipeline_churn.py` — DAG Airflow 3.3.2
- `u6/analysis/hallazgos_u6.json` — Datos precalculados que consume el dashboard
- `u6/analysis/run_analysis.py` — Script que regenera los hallazgos
