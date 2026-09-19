#!/bin/bash
# ============================================================================
# auditar_cuenta_actual.sh
# Audita todos los recursos GCP visibles bajo la cuenta gcloud activa.
# No modifica nada; solo lista.
#
# Uso:
#   bash auditar_cuenta_actual.sh
# ============================================================================

REGIONES=(us-central1 us-east1 us-west1 europe-west1 southamerica-east1)

G="\033[0;32m"; Y="\033[1;33m"; B="\033[1;34m"; N="\033[0m"
ok()   { echo -e "  ${G}OK${N} $*"; }
paso() { echo -e "\n${B}==============================================================${N}"; echo -e "${B}$*${N}"; echo -e "${B}==============================================================${N}"; }

CUENTA=$(gcloud config get-value account 2>/dev/null)
[[ -z "$CUENTA" ]] && { echo "No hay cuenta gcloud activa. Corre 'gcloud auth login' primero."; exit 1; }

paso "NIVEL 0 - Cuenta activa"
echo "  $CUENTA"

paso "NIVEL 1 - Proyectos accesibles"
gcloud projects list --format='table(projectId,name,lifecycleState)' 2>/dev/null

echo
echo "-- Facturacion por proyecto --"
for p in $(gcloud projects list --format='value(projectId)' 2>/dev/null); do
  info=$(gcloud billing projects describe "$p" --format='value(billingEnabled,billingAccountName)' 2>/dev/null)
  echo "  $p -> $info"
done

paso "NIVEL 3 - Cuentas de facturacion asociadas"
gcloud billing accounts list 2>/dev/null || echo "  (sin permisos o vacio)"

paso "NIVEL 2 - Recursos por proyecto"

for PROJECT_ID in $(gcloud projects list --format='value(projectId)' 2>/dev/null); do
  echo
  echo "-----------------------------------------------------------"
  echo "PROYECTO: $PROJECT_ID"
  echo "-----------------------------------------------------------"

  echo "  [1] Cloud Run (todas las regiones):"
  found=0
  for region in "${REGIONES[@]}"; do
    services=$(gcloud run services list --project=$PROJECT_ID --region=$region --format='value(SERVICE)' 2>/dev/null)
    if [[ -n "$services" ]]; then
      echo "      [$region] $services"
      found=1
    fi
  done
  [[ $found -eq 0 ]] && echo "      (ninguno)"

  echo "  [2] Compute Engine VMs:"
  vms=$(gcloud compute instances list --project=$PROJECT_ID --format='value(name,zone,status)' 2>/dev/null)
  [[ -n "$vms" ]] && echo "$vms" | sed 's/^/      /' || echo "      (ninguna)"

  echo "  [3] GKE clusters:"
  gke=$(gcloud container clusters list --project=$PROJECT_ID --format='value(name,location)' 2>/dev/null)
  [[ -n "$gke" ]] && echo "$gke" | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [4] Cloud SQL instances:"
  sql=$(gcloud sql instances list --project=$PROJECT_ID --format='value(name,region)' 2>/dev/null)
  [[ -n "$sql" ]] && echo "$sql" | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [5] GCS buckets:"
  buckets=$(gcloud storage buckets list --project=$PROJECT_ID --format='value(name)' 2>/dev/null)
  [[ -n "$buckets" ]] && echo "$buckets" | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [6] BigQuery datasets:"
  bq_out=$(bq ls --project_id=$PROJECT_ID 2>/dev/null | tail -n +3)
  [[ -n "$bq_out" ]] && echo "$bq_out" | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [7] Artifact Registry:"
  ar=$(gcloud artifacts repositories list --project=$PROJECT_ID --format='value(name,format,location)' 2>/dev/null)
  [[ -n "$ar" ]] && echo "$ar" | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [8] Cloud Functions:"
  fn=$(gcloud functions list --project=$PROJECT_ID --regions=- --format='value(name,region)' 2>/dev/null)
  [[ -n "$fn" ]] && echo "$fn" | sed 's/^/      /' || echo "      (ninguna)"

  echo "  [9] IPs estaticas:"
  ips=$(gcloud compute addresses list --project=$PROJECT_ID --format='value(name,region,status)' 2>/dev/null)
  [[ -n "$ips" ]] && echo "$ips" | sed 's/^/      /' || echo "      (ninguna)"

  echo "  [10] Discos persistentes:"
  disks=$(gcloud compute disks list --project=$PROJECT_ID --format='value(name,zone,sizeGb)' 2>/dev/null)
  [[ -n "$disks" ]] && echo "$disks" | head -10 | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [11] Service Accounts custom:"
  sas=$(gcloud iam service-accounts list --project=$PROJECT_ID --format='value(email,displayName)' 2>/dev/null | grep -vE "@developer.gserviceaccount|compute@|appspot")
  [[ -n "$sas" ]] && echo "$sas" | sed 's/^/      /' || echo "      (solo por defecto)"

  echo "  [12] Cloud Scheduler jobs:"
  sched=$(gcloud scheduler jobs list --project=$PROJECT_ID --format='value(name)' 2>/dev/null)
  [[ -n "$sched" ]] && echo "$sched" | sed 's/^/      /' || echo "      (ninguno)"

  echo "  [13] Pub/Sub topics:"
  ps=$(gcloud pubsub topics list --project=$PROJECT_ID --format='value(name)' 2>/dev/null)
  [[ -n "$ps" ]] && echo "$ps" | head -10 | sed 's/^/      /' || echo "      (ninguno)"
done

paso "LOCAL - Cloud Shell"

echo "-- ADC local --"
[[ -f ~/.config/gcloud/application_default_credentials.json ]] && echo "  EXISTE" || echo "  no existe"

echo "-- Airflow local --"
[[ -d ~/airflow ]] && du -sh ~/airflow 2>/dev/null || echo "  no existe"

echo "-- Repo unidad3 --"
[[ -d ~/unidad3 ]] && du -sh ~/unidad3 2>/dev/null || echo "  no existe"

echo "-- Docker images cached --"
if command -v docker >/dev/null 2>&1; then
  docker images --format='{{.Repository}}:{{.Tag}}  {{.Size}}' 2>/dev/null | head -20
else
  echo "  docker no accesible"
fi

paso "AUDITORIA COMPLETA"
echo "  Cuenta activa: $CUENTA"
