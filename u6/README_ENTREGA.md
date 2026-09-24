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

> **Estado de auditoría 2026-09-23:** los recursos de U6 del grupo 02 no
> están activos actualmente en `computacionnube20262`; las tablas, URLs e
> imágenes descritas abajo son los identificadores objetivo del despliegue.
> La verificación en GCP mostró únicamente el servicio `u5-g01-api`, que no
> pertenece a este grupo. Para volver a levantar el entorno se debe ejecutar
> `u6/desplegar_todo.sh` con el proyecto indicado.

### Cloud Run
| Servicio | URL | Revisión |
|---|---|---|
| U5 API (churn scoring) | `https://u5-g02-cr-20260919-978302928352.us-central1.run.app` | `00001` (deploy reproducible) |
| U6 Streamlit (monitor) | `https://u6-g02-cr-20260919-978302928352.us-central1.run.app` | `00009-bgf` (v5) |

Ambos con `--no-allow-unauthenticated`, min-instances 0, max-instances 1, SA `u5-g02-sa-20260919@computacionnube20262.iam.gserviceaccount.com`.

### Google Cloud Storage
- **Bucket:** `u6-g02-bucket-20260919` (us-central1)
- **Archivo:** `input/lotes_retencion_u6.csv` (703 filas, 10 semanas)

### BigQuery
- **Dataset:** `computacionnube20262.u6_g02_data_20260919`
- **Tablas esperadas en la corrida corregida:** `resultados` (667 filas), `cuarentena` (36 filas)
- **Vista:** `v_metricas_por_run`

### Artifact Registry
- **Repo:** `us-central1-docker.pkg.dev/computacionnube20262/u5-g02-repo-20260919`
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
  - 2026-08-24: **13.19%** rechazo (12 filas)
  - 2026-08-31: **30.30%** rechazo (20 filas)
- **PSI vs training**: `tenure` = 1.7 → 5.0 → 8.2 (drift material extremo, umbral 0.25 según Siddiqi 2006)
- **73% de los errores de campo son valores nuevos de PaymentMethod** (27 de 37; PSE, PayPal, Digital wallet, Corporate billing) que el enum de U5 no contempla

### 3 tipos de problema detectados (validando el cierre del loop MLOps)

1. **Fallo operacional** — corrida `20260919T202148` con URL mal configurado: 703 filas en cuarentena como `network`. Prueba de que el pipeline captura fallos de infraestructura, no solo semánticos.
2. **Drift semántico** — PSE / PayPal / Digital wallet: 27 errores de campo. Fix recomendado: ampliar enum en `service/app/schemas.py` y evaluar la población fuera de dominio.
3. **Bug del contrato** — `tenure ≤ 100` en `schemas.py` rechazaba clientes legítimos con 10+ años de antigüedad. **Detectado con el pipeline, no con EDA**. Fix aplicado, recuperó 14 clientes (de 50 → 36 cuarentena).

---

## Directrices D1-D6

Cada directriz tiene una página del dashboard con evidencia numérica. Ver screenshots adjuntos.

| # | Directriz | Página del monitor | Hallazgo clave |
|---|---|---|---|
| D1 | Umbral del DAG calibrado | `Cuarentena` | 2σ = 2.5% calculado con las primeras 4 semanas (baseline vs 20% a dedo) |
| D2 | Contenido de la cuarentena | `Cuarentena` | 73% de los errores de campo son valores nuevos de PaymentMethod, no data mala |
| D3 | Drift PSI vs training | `Drift` | `tenure` y `MonthlyCharges` con drift material; `Contract` estable |
| D4 | Método comparable entre features | `Drift` | PSI + KS-test para numéricas; chi² para categóricas |
| D5 | Columna nueva BancoPago | `BancoPago` | Decisión: ignorar como feature + canonicalizar. 3 alternativas descartadas |
| D6 | Respuesta al cliente | `Respuesta Cliente` | 4 recomendaciones (inmediato/corto/mediano/largo) + timeline SRE + 9 action items |

---

## Cómo correr localmente

### Correr el DAG

```bash
export API_URL="$(gcloud run services describe u5-g02-cr-20260919 --region=us-central1 --format='value(status.url)')/predict"
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

### Integración con BigQuery y autenticación

La cuenta de ejecución tiene permiso para crear jobs en el proyecto
`computacionnube20262`. Por eso el DAG usa `bq load` para cargas batch y el
dashboard usa `google-cloud-bigquery` para sus consultas; ambas operaciones
quedan trazables como jobs reales de BigQuery. El script de despliegue concede
`roles/bigquery.jobUser` a la cuenta de servicio y `roles/bigquery.dataViewer`
solo sobre el dataset del grupo.

El CLI se conserva únicamente donde resulta práctico en Cloud Shell: copiar el
CSV desde GCS, obtener el identity token del DAG y autodetectar servicios en
desarrollo local. Dentro de Cloud Run, la predicción individual obtiene el
token desde el metadata server y no depende de que exista `gcloud` en la
imagen.

### Nomenclatura por Pautas GCP del curso

- Recursos con `-` (guion medio): `u6-g02-cr-20260919`, `u6-g02-bucket-20260919`, `u5-g02-repo-20260919`
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
