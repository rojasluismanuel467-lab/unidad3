# Guia para David y Gabriel — U6 Trabajo Final

**Para**: Gabriel Escobar (A00399291), David Artunduaga (A00396342)
**De**: Luis Rojas (A00399289)
**Fecha**: 2026-09-19

Este documento tiene dos partes:

1. **[Parte A](#parte-a-subir-a-intu)** — Como subir el trabajo a INTU (lo minimo para entregar).
2. **[Parte B](#parte-b-repetir-el-proceso-con-tu-ia)** — Como replicar el proceso desde cero usando tu chat de IA (Claude, ChatGPT, etc.), por si quieren practicar antes de sustentar o reproducir el flujo con sus propias cuentas.

---

## Parte A — Subir a INTU

### Que subir

**Un envio por grupo** (uno solo, alguno de los tres). En el cuadro de texto de INTU (o adjuntar como comentario / PDF corto):

```
Grupo 2 — Trabajo Final Unidad 6
Curso: Computacion en la Nube para IA
Profesora: Diana Jaimes

Integrantes:
- Gabriel Ernesto Escobar A00399291
- David Artunduaga Penagos A00396342
- Luis Manuel Rojas A00399289

Aplicacion Streamlit (monitor del pipeline):
https://u6-g02-cr-20260919-978302928352.us-central1.run.app

Servicio API U5 (churn scoring) que consume el monitor:
https://u5-g02-cr-20260919-978302928352.us-central1.run.app

Ambos con --no-allow-unauthenticated. Para acceso interactivo:
gcloud run services proxy u6-g02-cr-20260919 --region=us-central1

Repo GitHub:
https://github.com/rojasluismanuel467-lab/unidad3

Ubicacion del trabajo en el repo:
- u6/dag/            (DAG Airflow + DDL SQL)
- u6/analysis/       (script + hallazgos_u6.json)
- u6/streamlit/      (7 paginas del dashboard + Dockerfile)
- u6/scripts/        (run_batch.py standalone)
- u6/README_ENTREGA.md    (informacion detallada)
- u6/COMPANEROS.md   (esta guia)
```

### Que NO hay que subir

- No hay que subir el codigo (esta en GitHub y en Cloud Run).
- No hay que subir screenshots (la rubrica dice que se evalua por los servicios en GCP + reunion).
- No hay que subir un informe largo — la profesora quiere ver el pipeline funcionando, no un PDF.

### Antes de subir, confirma que todo esta arriba

```bash
# Cloud Run U5 (API)
gcloud run services describe u5-g02-cr-20260919 --region=us-central1 --format='value(status.url)'

# Cloud Run U6 (Streamlit)
gcloud run services describe u6-g02-cr-20260919 --region=us-central1 --format='value(status.url)'

# BigQuery dataset
bq ls u6_g02_data_20260919

# Bucket GCS
gcloud storage ls gs://u6-g02-bucket-20260919/input/
```

Si alguno falla, avisa antes de la sustentacion.

### Fecha limite

- **Entrega en INTU**: sabado 3 de octubre a las 00:00
- **Servicios arriba hasta**: viernes 25 de septiembre a medianoche
- **Sustentacion**: entre lunes 21 y miercoles 30 de septiembre (agendar por correo)

---

## Parte B — Repetir el proceso con tu IA

### Objetivo

Si quieren correr todo el flujo desde cero (por ejemplo, para practicar antes de sustentar, o para reproducirlo con sus propias cuentas GCP), esta seccion los guia.

### Prerequisitos

1. **Cuenta de GCP** con un proyecto y facturacion habilitada (o el proyecto compartido del curso).
2. **Cloud Shell** habilitado en la consola de GCP (o local con `gcloud`, `docker`, `python3.11+`).
3. **Chat con IA** — Claude (claude.ai), ChatGPT (chat.openai.com), o similar.
4. **Repo del Grupo 2** clonado:
   ```bash
   git clone https://github.com/rojasluismanuel467-lab/unidad3.git
   cd unidad3
   ```

### Prompt inicial para tu IA

Copia y pega este prompt al inicio del chat con tu IA. Ajusta lo que este entre `<>`:

```
Estoy trabajando en el Trabajo Final de la Unidad 6 del curso Computacion en la Nube para IA de la Universidad Icesi. Ya tengo el codigo base en el repositorio github.com/rojasluismanuel467-lab/unidad3 (soy compaiiero de grupo del autor original).

Contexto:
- El trabajo pide desplegar un pipeline MLOps completo en GCP:
  - API de scoring (Cloud Run) que ya existe en la carpeta service/
  - DAG Airflow que consume el CSV lotes_retencion_u6.csv, invoca la API,
    y carga resultados a BigQuery
  - Dashboard Streamlit multipagina que analiza D1-D6 (directrices)
- Mi rol: replicar el deploy en <mi cuenta GCP / mi region>
- El CSV a procesar tiene 703 clientes en 10 semanas y viene con drift
  (nuevos PaymentMethod: PSE, PayPal, Digital wallet)
- El DAG usa el CLI solo para GCS e identity tokens en Cloud Shell; las cargas
  a BigQuery usan `bq load` y el dashboard usa el SDK Python para ejecutar
  jobs de consulta reales.

Ayudame a:
1. Verificar que tengo los prerequisitos (gcloud, bq, docker instalados)
2. Configurar mi proyecto y crear los recursos (bucket, dataset, SA)
3. Correr el DAG contra el CSV
4. Levantar el Streamlit (localmente primero, luego Cloud Run)
5. Preparar mi respuesta para las 6 directrices D1-D6

Empezamos por el paso 1: verificacion de entorno.
```

### Pasos del flujo (guia rapida)

Cada paso lo puedes discutir con tu IA en detalle. Este es el skeleton.

#### Paso 1: Verificacion de entorno

```bash
# Verificar herramientas
gcloud version
bq version
docker version
python3 --version   # >= 3.11
```

Si algo falta, tu IA te guia con el install (Cloud Shell trae todo por defecto — recomendado).

#### Paso 2: Config del proyecto GCP

```bash
export PROJECT_ID=<tu_proyecto>
export REGION=us-central1
export FECHA=$(date +%Y%m%d)   # o pon la fecha del entregable

gcloud config set project $PROJECT_ID
gcloud auth application-default login   # solo si no estas en Cloud Shell
```

#### Paso 3: Crear recursos (nomenclatura del curso: `uN-gNN-<tipo>-YYYYMMDD`)

```bash
# Ajusta GNN al numero de tu grupo
GNN=g02

# Bucket
gcloud storage buckets create gs://u6-${GNN}-bucket-${FECHA} --location=$REGION

# Subir el CSV
gcloud storage cp u6/data/lotes_retencion_u6.csv \
  gs://u6-${GNN}-bucket-${FECHA}/input/

# Service Account
gcloud iam service-accounts create u5-${GNN}-sa-${FECHA} \
  --display-name="U5 API scoring SA"

# Artifact Registry
gcloud artifacts repositories create u5-${GNN}-repo-${FECHA} \
  --repository-format=docker --location=$REGION

# BigQuery dataset + tablas (usa el DDL del repo)
bq mk --location=$REGION u6_${GNN}_data_${FECHA}
bq mk --table u6_${GNN}_data_${FECHA}.resultados \
  u6/dag/schema_resultados.json    # si no existe, genera con tu IA
bq mk --table u6_${GNN}_data_${FECHA}.cuarentena \
  u6/dag/schema_cuarentena.json
```

#### Paso 4: Deploy U5 (API de scoring)

```bash
cd service
docker build -t us-central1-docker.pkg.dev/$PROJECT_ID/u5-${GNN}-repo-${FECHA}/u5-${GNN}-api:v1 .
docker push us-central1-docker.pkg.dev/$PROJECT_ID/u5-${GNN}-repo-${FECHA}/u5-${GNN}-api:v1

gcloud run deploy u5-${GNN}-cr-${FECHA} \
  --image us-central1-docker.pkg.dev/$PROJECT_ID/u5-${GNN}-repo-${FECHA}/u5-${GNN}-api:v1 \
  --region=$REGION --no-allow-unauthenticated \
  --service-account=u5-${GNN}-sa-${FECHA}@$PROJECT_ID.iam.gserviceaccount.com \
  --min-instances=0 --max-instances=1
```

Verifica con:
```bash
export API_URL=$(gcloud run services describe u5-${GNN}-cr-${FECHA} \
  --region=$REGION --format='value(status.url)')/predict
TOKEN=$(gcloud auth print-identity-token --audiences=${API_URL%/predict})
curl -sS -X POST "$API_URL" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":"TEST","gender":"Female","partner":true,"dependents":false,"tenure":12,"contract":"Month-to-month","payment_method":"Electronic check","monthly_charges":70.5,"internet_service":"Fiber optic","online_security":"No","tech_support":"No"}'
```

Debe devolver un JSON con `customer_risk_score` y `predicted_churn`.

#### Paso 5: Correr el DAG

```bash
# Instalar Airflow 3.3.2 (Cloud Shell)
pip install --user apache-airflow==3.3.2
export AIRFLOW_HOME=$HOME/airflow
export PATH="$HOME/.local/bin:$PATH"
apache-airflow db migrate

# Copiar el DAG
mkdir -p $AIRFLOW_HOME/dags
cp u6/dag/dag_pipeline_churn.py $AIRFLOW_HOME/dags/

# Env vars que el DAG necesita
export GCS_BUCKET="u6-${GNN}-bucket-${FECHA}"
export BQ_DATASET="u6_${GNN}_data_${FECHA}"
export BQ_PROJECT="$PROJECT_ID"

# Correr
apache-airflow dags test pipeline_mlops_churn \
  --conf '{"archivo": "lotes_retencion_u6.csv"}'
```

Deberias ver algo como:
```
lotes_retencion_u6.csv   703 total   667 OK    36 rechazados     5.1%
```

#### Paso 6: Levantar Streamlit

**Local (recomendado para probar)**:
```bash
cd u6/streamlit
pip install -r requirements.txt
export BQ_PROJECT=$PROJECT_ID
export BQ_DATASET=u6_${GNN}_data_${FECHA}
streamlit run app.py --server.port=8080 --server.address=0.0.0.0 \
  --server.enableCORS=false --server.enableXsrfProtection=false
```

Abrir Web Preview en Cloud Shell (icono de monitor arriba a la derecha) puerto 8080.

**Cloud Run (para dejar arriba hasta la sustentacion)**:
```bash
cd u6
docker build -t us-central1-docker.pkg.dev/$PROJECT_ID/u5-${GNN}-repo-${FECHA}/u6-${GNN}-streamlit:v1 -f streamlit/Dockerfile .
docker push us-central1-docker.pkg.dev/$PROJECT_ID/u5-${GNN}-repo-${FECHA}/u6-${GNN}-streamlit:v1

gcloud run deploy u6-${GNN}-cr-${FECHA} \
  --image us-central1-docker.pkg.dev/$PROJECT_ID/u5-${GNN}-repo-${FECHA}/u6-${GNN}-streamlit:v1 \
  --region=$REGION --no-allow-unauthenticated \
  --service-account=u5-${GNN}-sa-${FECHA}@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars="BQ_PROJECT=$PROJECT_ID,BQ_DATASET=u6_${GNN}_data_${FECHA},CLOUD_RUN_URL=$(gcloud run services describe u5-${GNN}-cr-${FECHA} --region=$REGION --format='value(status.url)')"
```

### Preguntas tipicas de sustentacion (preparar las 3)

La profesora hace **2 preguntas por grupo**, escoge al azar quien responde cada una. Cualquiera de los 3 debe poder responder cualquiera.

**Q1 — "Muestren el umbral y por que lo cambiarian"**
Abrir pagina **Cuarentena** → tabla sensitivity → respuesta:
"Calibramos con 2σ = 2.5 % usando las 4 primeras semanas (baseline pre-drift). Con umbral a dedo de 20 % habriamos perdido las alarmas de 2026-08-24 (13.19 %) y 2026-08-31 (30.30 %); con nuestro umbral detectamos ambas."

**Q2 — "¿La poblacion cambio o el modelo se rompio?"**
Abrir pagina **Drift** → PSI de tenure → respuesta:
"La poblacion cambio, el modelo esta funcionando. Evidencia: PSI de tenure vs training pasa de 1.7 a 8.2 (umbral 0.25 segun Siddiqi 2006 → drift material 30x el umbral). MonthlyCharges tambien drifta pero Contract se mantiene estable → es un shift dirigido, no ruido general. Ademas, 27 errores de campo corresponden a valores nuevos de PaymentMethod (PSE, PayPal) — no data mala, sino medios de pago que la empresa ahora acepta y que el enum del contrato no contempla."

**Q3 — "¿Que hacen con BancoPago?"**
Abrir pagina **BancoPago** → 4 alternativas → respuesta:
"Elegimos la opcion D: ignorar como feature + canonicalizar para uso operativo. No agregamos al modelo porque (1) el modelo actual no la conoce, (2) la captura es sucia (mismo banco con 3 variantes: 'Bancolombia', 'Bancolombia S.A.', 'bancolombia'), y (3) los primeros 259 clientes tienen null porque la columna no existia. Descartamos imputar (metria sesgo), descartar filas (perderiamos 37 % del batch), y agregarla al modelo ya (requiere retraining con captura sucia)."

**Q4 — "¿Que le dirian al cliente?"**
Abrir pagina **Respuesta Cliente** → recorrer las 3 secciones → respuesta:
"El modelo no se rompio, la poblacion cambio. Recomendacion inmediata: ampliar enum de PaymentMethod para aceptar los nuevos medios y redesplegar U5. Corto plazo (esta semana): pedir al CRM la lista completa de nuevos medios de pago y el racional de la campana de adquisicion nueva. Mediano plazo: retraining con datos de las ultimas 2 semanas incluidos. Largo plazo: monitoreo automatico de PSI + calibracion mensual (Nixon 2019). Timeline SRE completo y action items con owner y due date en la pagina."

**Q5 — "Muestrenme el pipeline funcionando"**
Abrir **Consulta BQ** → 3 corridas visibles → respuesta:
"El pipeline capturo 3 tipos de problema:
- `network` (700+ filas): corrida de las 20:21 con URL mal configurado — prueba de que capturamos fallos operacionales.
- `api_reject` (66 filas): drift semantico + bug del contrato tenure≤100 que descubrimos con los datos reales.
- `client_side_parse` (30 filas): NaN y 'sin dato' en el CSV — falla de captura upstream.
Entre corrida 2 y 3 la cuarentena bajo de 50 a 36 filas gracias al fix del schema tenure — ejemplo del ciclo completo detectar-arreglar-verificar."

### Regla de oro para la sustentacion

**Si no saben algo, no inventen.** Digan "eso lo hizo <compaiiero> pero puedo recorrer la evidencia contigo en el dashboard" y abren la pagina relevante. La profesora quiere ver que dominan el flujo, no que memorizaron cada detalle.

---

## Troubleshooting comun

| Sintoma | Causa | Fix |
|---|---|---|
| `serviceusage.services.use denied` | Credencial local sin ese permiso | Ejecutar el DAG en Cloud Shell o corregir IAM antes de usar SDKs |
| `bigquery.jobs.create denied` | Cuenta de ejecución sin permiso | Conceder `roles/bigquery.jobUser` a la cuenta de servicio del monitor |
| `Setting IAM policy failed` en deploy | Org policy bloquea allUsers | Aceptar el warning, usar proxy para acceso interno |
| WebSocket rechazado en Web Preview | CORS/XSRF activo | `--server.enableCORS=false --server.enableXsrfProtection=false` |
| DAG dice "unrunnable tasks" | Alguna tarea fallo con retry | Ver el traceback en `airflow.log`, corregir y re-correr |

---

## Contacto

Si algo se rompe antes de la sustentacion, escribanme (Luis) por WhatsApp/correo. El repo tiene todo el historial en git — cualquier cambio se puede revertir con `git revert`.

Suerte con la sustentacion.
