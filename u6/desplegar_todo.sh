#!/bin/bash
# ============================================================================
# desplegar_todo.sh
#
# Script one-shot para desplegar el Trabajo Final U6 del Grupo 2 desde cero.
#
# Que hace:
#   1. Verifica prerequisitos (gcloud, bq, docker, python3)
#   2. Clona el repo si no existe
#   3. Crea Service Account, Artifact Registry, GCS Bucket, BigQuery dataset
#   4. Sube el CSV al bucket
#   5. Build + push + deploy de U5 (API)
#   6. Smoke test contra U5
#   7. Instala Airflow + corre el DAG
#   8. Build + push + deploy de U6 (Streamlit) con CLOUD_RUN_URL autodetectado
#   9. Imprime URLs finales
#
# Uso:
#   bash desplegar_todo.sh                # con defaults
#   FECHA=20260921 bash desplegar_todo.sh # sobreescribir fecha
#   SKIP_DAG=1 bash desplegar_todo.sh     # brincar el DAG
#
# Prerequisitos:
#   - Estar logueado en gcloud (Cloud Shell ya lo esta)
#   - Tener acceso al proyecto computacionnube20262 (o cambiar $PROJECT)
#
# Autor: Grupo 2 - Universidad Icesi - Computacion en la Nube para IA
# ============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Config (se puede sobreescribir con env vars)
# ---------------------------------------------------------------------------
PROJECT="${PROJECT:-computacionnube20262}"
REGION="${REGION:-us-central1}"
GNN="${GNN:-g02}"
FECHA="${FECHA:-20260919}"        # fecha en los nombres de recursos
REPO_URL="${REPO_URL:-https://github.com/rojasluismanuel467-lab/unidad3.git}"
REPO_DIR="${REPO_DIR:-$HOME/unidad3}"
REPO_USE_LOCAL="${REPO_USE_LOCAL:-0}"
SKIP_DAG="${SKIP_DAG:-0}"

# Derivados (no tocar)
SA="u5-${GNN}-sa-${FECHA}"
SA_EMAIL="${SA}@${PROJECT}.iam.gserviceaccount.com"
AR_REPO="u5-${GNN}-repo-${FECHA}"
BUCKET="u6-${GNN}-bucket-${FECHA}"
DATASET="u6_${GNN}_data_${FECHA}"
U5_SERVICE="u5-${GNN}-cr-${FECHA}"
U6_SERVICE="u6-${GNN}-cr-${FECHA}"
MODEL_BUCKET="${MODEL_BUCKET:-u4-${GNN}-mdl-20260917}"
MODEL_OBJECT="${MODEL_OBJECT:-u4_g02_mdl_20260914/model.joblib}"
MODEL_FILE="${MODEL_FILE:-$REPO_DIR/artifacts/u4/u4_g02_mdl_20260914_ganador.joblib}"
MODEL_VERSION="${MODEL_VERSION:-u4_g02_mdl_20260914}"
MODEL_GCS_URI="gs://${MODEL_BUCKET}/${MODEL_OBJECT}"
IMAGE_U5="us-central1-docker.pkg.dev/${PROJECT}/${AR_REPO}/u5-${GNN}-api:v1"
IMAGE_U6="us-central1-docker.pkg.dev/${PROJECT}/${AR_REPO}/u6-${GNN}-streamlit:v1"

# Colores
G="\033[0;32m"; Y="\033[1;33m"; R="\033[0;31m"; B="\033[1;34m"; N="\033[0m"

log()   { echo -e "${B}[$(date +%H:%M:%S)]${N} $*"; }
ok()    { echo -e "${G}✓${N} $*"; }
warn()  { echo -e "${Y}⚠${N} $*"; }
fail()  { echo -e "${R}✗${N} $*" >&2; exit 1; }
paso()  { echo -e "\n${B}================================================================${N}"; echo -e "${B}$*${N}"; echo -e "${B}================================================================${N}"; }

# ---------------------------------------------------------------------------
# 0. Confirmar plan
# ---------------------------------------------------------------------------
cat <<INFO

${B}Plan de despliegue${N}

Proyecto GCP:        $PROJECT
Region:              $REGION
Grupo:               $GNN
Fecha (nombres):     $FECHA
Repo:                $REPO_URL
Directorio local:    $REPO_DIR

Recursos que se crearan/reutilizaran:
  Service Account:   $SA_EMAIL
  Artifact Registry: $AR_REPO
  GCS Bucket:        gs://$BUCKET
  Model bucket:      gs://$MODEL_BUCKET
  BigQuery dataset:  $PROJECT:$DATASET
  Cloud Run U5:      $U5_SERVICE
  Cloud Run U6:      $U6_SERVICE

Duracion estimada:   8-12 minutos.

INFO

read -p "¿Continuar? (escribe SI para arrancar): " conf
[[ "$conf" != "SI" ]] && { echo "Cancelado."; exit 1; }

# ---------------------------------------------------------------------------
# 1. Prerequisitos
# ---------------------------------------------------------------------------
paso "1/9 · Verificando prerequisitos"

for cmd in gcloud bq docker python3 git; do
  command -v $cmd >/dev/null 2>&1 && ok "$cmd instalado" || fail "Falta $cmd"
done

CUENTA=$(gcloud config get-value account 2>/dev/null || echo "")
[[ -z "$CUENTA" ]] && fail "No hay cuenta gcloud activa. Corre 'gcloud auth login' primero."
ok "Cuenta activa: $CUENTA"

gcloud config set project "$PROJECT" >/dev/null 2>&1
ok "Proyecto activo: $PROJECT"

# ---------------------------------------------------------------------------
# 2. Repo
# ---------------------------------------------------------------------------
paso "2/9 · Clonando repo si hace falta"

if [[ ! -d "$REPO_DIR" ]]; then
  git clone "$REPO_URL" "$REPO_DIR"
  ok "Repo clonado en $REPO_DIR"
elif [[ "$REPO_USE_LOCAL" == "1" ]]; then
  ok "Usando repo local sin hacer pull: $REPO_DIR"
else
  cd "$REPO_DIR" && git pull --ff-only origin main 2>&1 | tail -1
  ok "Repo actualizado en $REPO_DIR"
fi
cd "$REPO_DIR"

# ---------------------------------------------------------------------------
# 3. Service Account
# ---------------------------------------------------------------------------
paso "3/9 · Service Account"

if gcloud iam service-accounts describe "$SA_EMAIL" --project=$PROJECT >/dev/null 2>&1; then
  ok "SA ya existe: $SA_EMAIL"
else
  gcloud iam service-accounts create "$SA" \
    --project="$PROJECT" \
    --display-name="U5 API scoring - Grupo 2" >/dev/null
  ok "SA creada: $SA_EMAIL"
fi

# ---------------------------------------------------------------------------
# 4. Artifact Registry
# ---------------------------------------------------------------------------
paso "4/9 · Artifact Registry"

if gcloud artifacts repositories describe "$AR_REPO" \
     --project=$PROJECT --location=$REGION >/dev/null 2>&1; then
  ok "AR repo ya existe: $AR_REPO"
else
  gcloud artifacts repositories create "$AR_REPO" \
    --project=$PROJECT --location=$REGION \
    --repository-format=docker \
    --description="Repo Docker Grupo 2 - U5 API + U6 Streamlit" >/dev/null
  ok "AR repo creado: $AR_REPO"
fi

gcloud auth configure-docker "us-central1-docker.pkg.dev" --quiet >/dev/null 2>&1
ok "Docker configurado para Artifact Registry"

# ---------------------------------------------------------------------------
# 5. GCS Bucket + CSV
# ---------------------------------------------------------------------------
paso "5/9 · GCS Bucket + CSV"

if gcloud storage buckets describe "gs://$BUCKET" --project=$PROJECT >/dev/null 2>&1; then
  ok "Bucket ya existe: gs://$BUCKET"
else
  gcloud storage buckets create "gs://$BUCKET" \
    --project=$PROJECT --location=$REGION >/dev/null
  ok "Bucket creado: gs://$BUCKET"
fi

if gcloud storage ls "gs://$BUCKET/input/lotes_retencion_u6.csv" >/dev/null 2>&1; then
  ok "CSV ya subido"
else
  gcloud storage cp "$REPO_DIR/u6/data/lotes_retencion_u6.csv" \
    "gs://$BUCKET/input/lotes_retencion_u6.csv" 2>&1 | tail -1
  ok "CSV subido a gs://$BUCKET/input/"
fi

if [[ ! -f "$MODEL_FILE" ]]; then
  fail "No existe el bundle ganador: $MODEL_FILE"
fi
if gcloud storage buckets describe "gs://$MODEL_BUCKET" --project=$PROJECT >/dev/null 2>&1; then
  ok "Bucket del modelo ya existe: gs://$MODEL_BUCKET"
else
  gcloud storage buckets create "gs://$MODEL_BUCKET" \
    --project="$PROJECT" --location="$REGION" \
    --uniform-bucket-level-access >/dev/null
  ok "Bucket del modelo creado: gs://$MODEL_BUCKET"
fi
if gcloud storage ls "gs://$MODEL_BUCKET/$MODEL_OBJECT" >/dev/null 2>&1; then
  ok "Bundle del modelo ya subido"
else
  gcloud storage cp "$MODEL_FILE" "gs://$MODEL_BUCKET/$MODEL_OBJECT" >/dev/null
  ok "Bundle del modelo subido: $MODEL_GCS_URI"
fi

# La API U5 descarga el bundle al arrancar; el acceso queda limitado a su SA.
gcloud storage buckets add-iam-policy-binding "gs://$MODEL_BUCKET" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer" --quiet >/dev/null
ok "Acceso de lectura al bucket del modelo configurado"

# El dashboard lee el CSV de entrada para contextualizar los lotes.
if gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/storage.objectViewer" --quiet >/dev/null 2>&1; then
  ok "Acceso de lectura al bucket de datos configurado"
else
  warn "No se pudo configurar objectViewer en el bucket de datos"
fi

# ---------------------------------------------------------------------------
# 6. BigQuery dataset + tablas
# ---------------------------------------------------------------------------
paso "6/9 · BigQuery dataset + tablas"

if bq ls "$PROJECT:$DATASET" >/dev/null 2>&1; then
  ok "Dataset ya existe: $DATASET"
else
  bq mk --location=$REGION --dataset "$PROJECT:$DATASET" >/dev/null
  ok "Dataset creado: $DATASET"
fi

# Tablas + vista: el DDL es la única fuente de verdad del esquema.
# `bq query` crea un job real y evita que el script diverja del DAG.
sed "s/u6_g02_data_20260919/${DATASET}/g" \
  "$REPO_DIR/u6/dag/u6-g02-sql-20260919.sql" \
  | bq query --project_id="$PROJECT" --location="$REGION" \
      --use_legacy_sql=false >/dev/null
ok "Dataset, tablas y vista BigQuery creados/verificados mediante query job"

# El dashboard corre con esta identidad: necesita leer el dataset y crear
# query jobs para consultar las tablas desde Cloud Run.
if gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/bigquery.jobUser" \
    --quiet >/dev/null 2>&1; then
  if bq add-iam-policy-binding \
      --member="serviceAccount:${SA_EMAIL}" \
      --role="roles/bigquery.dataViewer" \
      --dataset "$PROJECT:$DATASET" >/dev/null 2>&1; then
    ok "Permisos BigQuery configurados para la cuenta de servicio"
  else
    warn "No se pudo configurar dataViewer en el dataset; la administradora debe habilitarlo"
  fi
else
  warn "No se pudo configurar roles/bigquery.jobUser; la administradora debe otorgarlo a ${SA_EMAIL}"
fi

# ---------------------------------------------------------------------------
# 7. Build + push + deploy U5
# ---------------------------------------------------------------------------
paso "7/9 · Deploy U5 (API scoring)"

log "Building imagen U5..."
docker build --platform linux/amd64 --quiet -t "$IMAGE_U5" -f "$REPO_DIR/service/Dockerfile" "$REPO_DIR/service/" >/dev/null
ok "Imagen U5 construida"

log "Pushing a Artifact Registry..."
docker push "$IMAGE_U5" >/dev/null 2>&1
ok "Imagen U5 pusheada"

log "Desplegando a Cloud Run..."
gcloud run deploy "$U5_SERVICE" \
  --image "$IMAGE_U5" \
  --region=$REGION --project=$PROJECT \
  --no-allow-unauthenticated \
  --min-instances=0 --max-instances=1 \
  --service-account="$SA_EMAIL" \
  --set-env-vars="MODEL_GCS_URI=${MODEL_GCS_URI},MODEL_VERSION=${MODEL_VERSION}" \
  --quiet 2>&1 | tail -2

U5_URL=$(gcloud run services describe "$U5_SERVICE" \
  --region=$REGION --project=$PROJECT --format='value(status.url)')
ok "U5 desplegado: $U5_URL"

# U6 usa la misma cuenta de servicio para invocar el API privado de U5.
if gcloud run services add-iam-policy-binding "$U5_SERVICE" \
    --region="$REGION" --project="$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.invoker" --quiet >/dev/null 2>&1; then
  ok "Invocación privada U5 habilitada para la cuenta de servicio del grupo"
else
  warn "No se pudo otorgar run.invoker a la cuenta de servicio; la administradora debe habilitarlo"
fi

# Smoke test
log "Smoke test contra U5..."
if TOKEN=$(gcloud auth print-identity-token --audiences="$U5_URL" 2>/dev/null); then
  RESP=$(curl -sS -o /tmp/u5_smoke.json -w "%{http_code}" \
    -X POST "$U5_URL/predict" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"SMOKE","gender":"Female","partner":true,"dependents":false,"tenure":12,"contract":"Month-to-month","payment_method":"Electronic check","monthly_charges":70.5,"internet_service":"Fiber optic","online_security":"No","tech_support":"No"}')

  if [[ "$RESP" == "200" ]]; then
    ok "U5 responde HTTP 200"
  else
    warn "U5 smoke test devolvio HTTP $RESP — revisa /tmp/u5_smoke.json"
    cat /tmp/u5_smoke.json
  fi
else
  warn "Smoke test omitido: la cuenta activa no permite generar un token de audiencia para un servicio privado"
fi

# ---------------------------------------------------------------------------
# 8. DAG Airflow (opcional)
# ---------------------------------------------------------------------------
if [[ "$SKIP_DAG" == "1" ]]; then
  paso "8/9 · DAG Airflow (SKIPPED por env SKIP_DAG=1)"
else
  paso "8/9 · DAG Airflow"

  if ! command -v apache-airflow >/dev/null 2>&1; then
    log "Instalando Airflow 3.3.2..."
    pip install --user --quiet apache-airflow==3.3.2 2>&1 | tail -3
    export PATH="$HOME/.local/bin:$PATH"
    export AIRFLOW_HOME="$HOME/airflow"
    apache-airflow db migrate 2>&1 | tail -2
    ok "Airflow instalado"
  else
    ok "Airflow ya instalado"
    export PATH="$HOME/.local/bin:$PATH"
    export AIRFLOW_HOME="$HOME/airflow"
  fi

  mkdir -p "$AIRFLOW_HOME/dags"
  cp "$REPO_DIR/u6/dag/dag_pipeline_churn.py" "$AIRFLOW_HOME/dags/"
  ok "DAG copiado"

  # Env vars que el DAG necesita
  export API_URL="$U5_URL/predict"
  export GCS_BUCKET="$BUCKET"
  export BQ_DATASET="$DATASET"
  export BQ_PROJECT="$PROJECT"

  log "Corriendo DAG (703 llamadas HTTP, ~2 min)..."
  apache-airflow dags test pipeline_mlops_churn \
    --conf '{"archivo": "lotes_retencion_u6.csv"}' 2>&1 \
    | grep -E "reporte_metricas|DagRun Finished|lotes_retencion_u6.csv" | tail -5

  ok "DAG corrio (revisa BQ para ver resultados)"
fi

# ---------------------------------------------------------------------------
# 9. Build + push + deploy U6
# ---------------------------------------------------------------------------
paso "9/9 · Deploy U6 (Streamlit dashboard)"

log "Building imagen U6..."
docker build --platform linux/amd64 --quiet -t "$IMAGE_U6" -f "$REPO_DIR/u6/streamlit/Dockerfile" "$REPO_DIR/u6/" >/dev/null
ok "Imagen U6 construida"

log "Pushing a Artifact Registry..."
docker push "$IMAGE_U6" >/dev/null 2>&1
ok "Imagen U6 pusheada"

log "Desplegando a Cloud Run..."
gcloud run deploy "$U6_SERVICE" \
  --image "$IMAGE_U6" \
  --region=$REGION --project=$PROJECT \
  --no-allow-unauthenticated \
  --min-instances=0 --max-instances=1 --memory=512Mi \
  --service-account="$SA_EMAIL" \
  --set-env-vars="BQ_PROJECT=${PROJECT},BQ_DATASET=${DATASET},GCS_BUCKET=${BUCKET},CLOUD_RUN_URL=${U5_URL}" \
  --quiet 2>&1 | tail -2

U6_URL=$(gcloud run services describe "$U6_SERVICE" \
  --region=$REGION --project=$PROJECT --format='value(status.url)')
ok "U6 desplegado: $U6_URL"

# ---------------------------------------------------------------------------
# Fin
# ---------------------------------------------------------------------------
paso "DESPLIEGUE COMPLETO"

cat <<RESUMEN

${G}Todo listo.${N}

URLs:
  U5 API:       $U5_URL
  U6 Streamlit: $U6_URL

Ver el dashboard:
  gcloud run services proxy $U6_SERVICE --region=$REGION

Y abrir Web Preview en Cloud Shell (puerto 8080).

Recursos creados (para limpiar despues):
  gcloud run services delete $U5_SERVICE $U6_SERVICE --region=$REGION --quiet
  gcloud storage rm --recursive gs://$BUCKET --quiet
  bq rm -r -f --dataset $PROJECT:$DATASET
  gcloud artifacts repositories delete $AR_REPO --location=$REGION --quiet
  gcloud iam service-accounts delete $SA_EMAIL --quiet
  # El bucket del modelo pertenece a U4 y se conserva para reutilizarlo.

Suerte con la sustentacion.
RESUMEN
