# Evidencias de despliegue U5 — Servicio de churn

**Grupo:** 02  
**Integrantes:** Gabriel Escobar Bravo · David Artunduaga Penagos · Luis Manuel Rojas  
**Proyecto GCP:** `computacionnube20262`  
**Servicio Cloud Run:** `u5-g02-cr-20260917`  
**Región:** `us-central1`

## 1. Servicio activo en Cloud Run

La salida de `gcloud run services list` confirma que el servicio del grupo 02 fue desplegado correctamente en el proyecto indicado y aparece activo en la región `us-central1`.

![Evidencia de Cloud Run](evidencias_u5/01-cloud-run.png)

## 2. Endpoint `/health`

La respuesta HTTP `200` confirma que el servicio responde correctamente y que la aplicación está disponible para recibir solicitudes.

![Respuesta del endpoint health](evidencias_u5/02-health.png)

## 3. Predicción válida en `/predict`

La respuesta HTTP `200` demuestra que el contrato de entrada fue aceptado y que el modelo devolvió un puntaje de riesgo, una predicción de churn, el threshold utilizado y la versión del modelo.

![Predicción válida](evidencias_u5/03-predict-valido.png)

## 4. Validación de entrada con respuesta `422`

La respuesta HTTP `422` se genera porque `tenure` recibió el texto `veinte` en lugar de un entero. Esto demuestra que el contrato protege el servicio frente a tipos de datos inválidos.

![Error de validación 422](evidencias_u5/04-predict-422.png)

## Resumen

Las evidencias confirman el despliegue del servicio, la disponibilidad del endpoint de salud, una predicción válida y el rechazo de una solicitud que no cumple el esquema de entrada. El modelo utilizado corresponde a `u4_g02_mdl_20260914`.
