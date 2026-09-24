# Guía de despliegue — Servicio churn-api (U5)

**Grupo 2** · Curso: Computación en la Nube para IA · Profesora: Diana Jaimes

Basada en `Guia_Lab_Unidad5.md` de la profesora, con nombres del grupo y comandos
listos para copiar. Toda la secuencia se ejecuta desde **Cloud Shell** del
proyecto `computacionnube20262`.

---

## Prerrequisitos

1. Modelo ganador entrenado y `artifacts/u4/u4_g02_mdl_20260914_ganador.joblib`
   ya subido al bucket de U4 (`gs://u4-g02-mdl-20260917/`). El runner-up se registra
   como respaldo, pero solamente el ganador se despliega en U5.
2. Estar autenticado en `gcloud` con la misma cuenta del proyecto.
3. Repo clonado en Cloud Shell:
   ```bash
   git clone https://github.com/rojasluismanuel467-lab/unidad3.git
   cd unidad3/service
   ```

Antes de ejecutar comandos, fija explícitamente el proyecto para no usar por error
otro proyecto configurado en la máquina:

```bash
gcloud config set project computacionnube20262
```

---

## Paso 1 — Verificar la estructura

```bash
ls -la
ls -la app/
```

Debe verse:
```
Dockerfile
requirements.txt
app/
  __init__.py
  main.py
  schemas.py
```

---

## Paso 2 — Crear repositorio Artifact Registry (una sola vez)

```bash
gcloud artifacts repositories create u5-g02-repo-20260917 \
  --repository-format=docker \
  --location=us-central1 \
  --description="Repo de imagenes para churn-api del Grupo 2"
```

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

---

## Paso 3 — Construir la imagen

Antes de correr, guarda el project id:

```bash
export PROJECT_ID=computacionnube20262
```

```bash
docker build --platform linux/amd64 -t us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260917/u5-g02-img-20260917:v1 .
```

---

## Paso 4 — Subir la imagen

```bash
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260917/u5-g02-img-20260917:v1
```

Si falla con `connection refused`, reintenta el mismo comando. Si persiste:

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
docker push us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260917/u5-g02-img-20260917:v1
```

---

## Paso 5 — Crear service account dedicada + permisos (una sola vez)

```bash
gcloud iam service-accounts create u5-g02-sa-20260917 \
  --display-name="Service account para churn-api Grupo 2"
```

Dale permiso de LECTURA sobre el bucket con el `.joblib` del modelo:

```bash
gcloud storage buckets add-iam-policy-binding gs://u4-g02-mdl-20260917 \
  --member="serviceAccount:u5-g02-sa-20260917@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

---

## Paso 6 — Desplegar a Cloud Run

```bash
gcloud run deploy u5-g02-cr-20260917 \
  --image=us-central1-docker.pkg.dev/${PROJECT_ID}/u5-g02-repo-20260917/u5-g02-img-20260917:v1 \
  --region=us-central1 \
  --no-allow-unauthenticated \
  --service-account=u5-g02-sa-20260917@${PROJECT_ID}.iam.gserviceaccount.com \
  --min-instances=0 \
  --max-instances=1 \
  --memory=512Mi \
  --port=8080 \
  --set-env-vars="MODEL_GCS_URI=gs://u4-g02-mdl-20260917/u4_g02_mdl_20260914/model.joblib,MODEL_VERSION=u4_g02_mdl_20260914"
```

**Guarda la `Service URL`** que devuelve — la vas a necesitar en todos los pasos siguientes.

Como el servicio es privado, autoriza al usuario que hará las pruebas:

```bash
CALLER=$(gcloud auth list --filter=status:ACTIVE --format='value(account)')
gcloud run services add-iam-policy-binding u5-g02-cr-20260917 \
  --region=us-central1 \
  --member="user:${CALLER}" \
  --role=roles/run.invoker
```

---

## Paso 7 — Guardar la URL del servicio

```bash
export SERVICE_URL=$(gcloud run services describe u5-g02-cr-20260917 \
  --region=us-central1 --format='value(status.url)')
echo $SERVICE_URL
```

---

## Paso 8 — Verificar que el servicio está activo

```bash
gcloud run services list --project=computacionnube20262 --region=us-central1
```

**Captura este output** — es una de las evidencias del entregable.

---

## Paso 9 — Probar `/health` (caso 200)

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  ${SERVICE_URL}/health
```

Esperado (JSON con `status: ok`):

```json
{"status":"ok","model_loaded":true,"model_version":"u4_g02_mdl_20260914"}
```

**Captura el comando + respuesta** — evidencia entregable.

---

## Paso 10 — Probar `/predict` con los 4 casos requeridos

### Caso 1 — VÁLIDO (200 con predicción)

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "TEST-VALID-001",
    "gender": "Female",
    "partner": true,
    "dependents": false,
    "tenure": 12,
    "contract": "Month-to-month",
    "payment_method": "Electronic check",
    "monthly_charges": 89.5,
    "internet_service": "Fiber optic",
    "online_security": "No",
    "tech_support": "No"
  }' \
  ${SERVICE_URL}/predict
```

Esperado: 200 con `customer_risk_score` entre 0 y 1.

### Caso 2 — 422 por TIPO incorrecto (`tenure` como string)

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "TEST-422-TYPE",
    "gender": "Female",
    "partner": true,
    "dependents": false,
    "tenure": "veinte",
    "contract": "Month-to-month",
    "payment_method": "Electronic check",
    "monthly_charges": 89.5,
    "internet_service": "Fiber optic",
    "online_security": "No",
    "tech_support": "No"
  }' \
  ${SERVICE_URL}/predict
```

Esperado: 422 con `type_error.integer` o similar en `detail`.

### Caso 3 — 422 por VALOR fuera de dominio (`contract` inválido)

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "TEST-422-ENUM",
    "gender": "Female",
    "partner": true,
    "dependents": false,
    "tenure": 12,
    "contract": "Perpetuo",
    "payment_method": "Electronic check",
    "monthly_charges": 89.5,
    "internet_service": "Fiber optic",
    "online_security": "No",
    "tech_support": "No"
  }' \
  ${SERVICE_URL}/predict
```

Esperado: 422 diciendo que `contract` debe ser uno de `{Month-to-month, One year, Two year}`.

### Caso 4 — 422 por CAMPO faltante (`monthly_charges` omitido)

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "TEST-422-MISSING",
    "gender": "Female",
    "partner": true,
    "dependents": false,
    "tenure": 12,
    "contract": "Month-to-month",
    "payment_method": "Electronic check",
    "internet_service": "Fiber optic",
    "online_security": "No",
    "tech_support": "No"
  }' \
  ${SERVICE_URL}/predict
```

Esperado: 422 con `field_required` para `monthly_charges`.

**Captura las 4 respuestas completas** — evidencia entregable.

---

## Paso 11 — Verificar el logging estructurado en Cloud Logging

Consola GCP → Logging → Explorador de registros → filtro:

```
resource.type="cloud_run_revision"
resource.labels.service_name="u5-g02-cr-20260917"
jsonPayload.message="predict_ok"
```

Debes ver los logs de las predicciones válidas con `input` y `output` completos como campos buscables. Y con filtro `jsonPayload.message="predict_422"` los rechazos por schema.

---

## Paso 12 — Limpieza (al terminar de capturar evidencia)

```bash
gcloud run services delete u5-g02-cr-20260917 \
  --region=us-central1 --quiet
```

**NO borres** (según indicación de la profesora):
- El bucket `gs://u4-g02-mdl-20260917`
- El Model Registry
- El repositorio Artifact Registry (puede reutilizarse en futuras iteraciones)

---

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `403` en `/predict` | Falta el identity-token en el header | Agregar `-H "Authorization: Bearer $(gcloud auth print-identity-token)"` |
| `422` inesperado en caso válido | Alguna feature con nombre/valor distinto al enum | Revisa `service/app/schemas.py` — los strings deben ser EXACTOS |
| `503` en `/health` | El modelo no cargó — bucket o path mal | Verifica `MODEL_GCS_URI` en el deploy y que la SA tenga `roles/storage.objectViewer` |
| `docker push` falla con `connection refused` | Red temporal | Reintentar |
| `PERMISSION_DENIED: artifactregistry.repositories.create` | Falta rol `roles/artifactregistry.admin` | Pedir el rol a la profesora |

---

## Evidencia a subir a INTU

1. `service/app/schemas.py` y `service/app/main.py`
2. Screenshot de `gcloud run services list` mostrando `u5-g02-cr-20260917` activo (Paso 8)
3. Screenshot de `curl /health` con respuesta 200 (Paso 9)
4. Screenshots de los 4 `curl /predict`:
   - Caso 1 válido con 200 + score
   - Caso 2 422 por tipo
   - Caso 3 422 por valor
   - Caso 4 422 por campo faltante
5. (Opcional) Screenshot del Cloud Logging mostrando un `predict_ok` con input+output
