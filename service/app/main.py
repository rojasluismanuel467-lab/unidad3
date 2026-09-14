"""FastAPI service para predecir churn — Cloud Run deployment (U5).

Diseno con mejoras metodologicas:
  - Lifespan async (patron moderno desde FastAPI 0.104, on_event deprecado)
  - Probes separadas /startup, /live, /ready (Kubernetes/Cloud Run convention)
  - Logging estructurado desde el diseno (json_fields para Cloud Logging)
  - Threshold optimo cargado desde el bundle del modelo (no hardcoded 0.5)
  - Validacion de dominio en pydantic; coherencia semantica en main (separacion
    de responsabilidades: schema = transporte, main = negocio)

Grupo 2 - Gabriel Escobar, David Artunduaga, Luis Rojas.
"""
from __future__ import annotations

import logging
import os
import pickle
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import (
    ClienteInput,
    HealthOutput,
    InternetService,
    PrediccionOutput,
    YesNoNoInternet,
)


# ---------------------------------------------------------------------------
# Configuracion via env vars (Cloud Run los inyecta al desplegar)
# ---------------------------------------------------------------------------
MODEL_PATH_LOCAL = os.getenv("MODEL_PATH_LOCAL", "/tmp/model.joblib")
MODEL_GCS_URI = os.getenv("MODEL_GCS_URI", "")
MODEL_VERSION = os.getenv("MODEL_VERSION", "u4_g02_mdl_20260914")


# ---------------------------------------------------------------------------
# Logging estructurado (Cloud Logging convention)
# ---------------------------------------------------------------------------
class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json as _json
        payload = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if hasattr(record, "json_fields"):
            payload.update(record.json_fields)
        return _json.dumps(payload, default=str)


def _init_logger() -> logging.Logger:
    logger = logging.getLogger("churn-api")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    logger.handlers = [handler]
    logger.propagate = False
    return logger


logger = _init_logger()


# ---------------------------------------------------------------------------
# Estado del modelo (compartido via app.state)
# ---------------------------------------------------------------------------
class ModelState:
    """Contenedor del bundle cargado (estimator calibrado + threshold + features)."""

    def __init__(self) -> None:
        self.bundle: Optional[dict] = None
        self.error: Optional[str] = None
        self.loaded_at: Optional[datetime] = None

    def is_ready(self) -> bool:
        return self.bundle is not None and self.error is None


def _load_model_from_gcs(gcs_uri: str, dest: str) -> str:
    if Path(dest).exists():
        return dest
    from google.cloud import storage

    assert gcs_uri.startswith("gs://"), f"MODEL_GCS_URI mal formado: {gcs_uri}"
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_path = rest.partition("/")
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(dest)
    return dest


def _load_bundle() -> dict:
    """Carga y valida el bundle del modelo (contract del pkl).

    Soporta tanto joblib (formato preferido, mas robusto entre versiones de
    Python/sklearn) como pickle plano (compat con bundles antiguos).
    """
    path = MODEL_PATH_LOCAL
    if MODEL_GCS_URI:
        path = _load_model_from_gcs(MODEL_GCS_URI, MODEL_PATH_LOCAL)

    try:
        # Formato preferido: joblib maneja mejor arrays numpy grandes y es
        # el standard de sklearn/xgboost/lightgbm.
        bundle = joblib.load(path)
    except Exception:
        # Fallback a pickle plano para bundles antiguos.
        with open(path, "rb") as f:
            bundle = pickle.load(f)

    # Contract check: el bundle DEBE traer al menos estas llaves
    required = {"estimator", "threshold_optimo", "features", "arquitectura"}
    missing = required - set(bundle.keys())
    if missing:
        raise ValueError(f"Bundle mal formado, faltan keys: {missing}")

    return bundle


# ---------------------------------------------------------------------------
# Lifespan async — carga el modelo UNA VEZ al arrancar el container
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Se ejecuta al arrancar (antes de aceptar requests) y al apagar."""
    state = ModelState()
    app.state.model = state
    try:
        bundle = _load_bundle()
        state.bundle = bundle
        state.loaded_at = datetime.now(timezone.utc)
        logger.info(
            "startup_model_loaded",
            extra={"json_fields": {
                "arquitectura": bundle.get("arquitectura"),
                "threshold_optimo": bundle.get("threshold_optimo"),
                "n_features": len(bundle.get("features", [])),
                "version": MODEL_VERSION,
            }},
        )
    except Exception as e:
        state.error = str(e)
        logger.error(
            "startup_model_load_failed",
            extra={"json_fields": {"error": str(e), "gcs_uri": MODEL_GCS_URI}},
        )
    yield
    # Shutdown: liberar memoria por si algo se aferra
    app.state.model = None


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Churn API - Grupo 2",
    version="2.0.0",
    description=(
        "Servicio de prediccion de churn. Modelo ganador de U4 seleccionado con "
        "Optuna optimizando costo de negocio + calibracion isotonic + threshold "
        "tuning. Contrato validado con pydantic; probes separadas para orquestacion."
    ),
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Coherencia de negocio (fuera de pydantic — es logica de dominio, no de transporte)
# ---------------------------------------------------------------------------
def _validar_coherencia_negocio(cliente: ClienteInput) -> None:
    """Reglas de negocio que dependen del modelo entrenado.

    Se pueden aflojar si el modelo se re-entrena con otra logica, sin tocar el
    schema. Se mantienen en main para separar transporte (pydantic) de negocio.
    """
    sin_internet = cliente.internet_service == InternetService.no
    servicios = [
        ("online_security", cliente.online_security),
        ("tech_support", cliente.tech_support),
    ]
    for nombre, valor in servicios:
        if sin_internet and valor != YesNoNoInternet.no_internet_service:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "type": "business_rule",
                    "loc": ["body", nombre],
                    "msg": f"{nombre} debe ser 'No internet service' cuando internet_service='No'",
                    "input": valor.value,
                }],
            )
        if (not sin_internet) and valor == YesNoNoInternet.no_internet_service:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "type": "business_rule",
                    "loc": ["body", nombre],
                    "msg": (
                        f"{nombre} no puede ser 'No internet service' cuando "
                        f"internet_service='{cliente.internet_service.value}'"
                    ),
                    "input": valor.value,
                }],
            )


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def _preparar_features(cliente: ClienteInput, feature_cols: list) -> pd.DataFrame:
    raw = {
        "gender": cliente.gender.value,
        "Partner": cliente.partner,
        "Dependents": cliente.dependents,
        "tenure": cliente.tenure,
        "Contract": cliente.contract.value,
        "PaymentMethod": cliente.payment_method.value,
        "MonthlyCharges": cliente.monthly_charges,
        "InternetService": cliente.internet_service.value,
        "OnlineSecurity": cliente.online_security.value,
        "TechSupport": cliente.tech_support.value,
    }
    df_raw = pd.DataFrame([raw])
    categoricas = [
        "gender", "Partner", "Dependents", "Contract", "PaymentMethod",
        "InternetService", "OnlineSecurity", "TechSupport",
    ]
    df_ohe = pd.get_dummies(df_raw, columns=categoricas, drop_first=True)
    for col in feature_cols:
        if col not in df_ohe.columns:
            df_ohe[col] = False
    return df_ohe[feature_cols].astype(float)


# ---------------------------------------------------------------------------
# Probes separadas (Kubernetes / Cloud Run convention)
# ---------------------------------------------------------------------------
@app.get("/live", tags=["probes"])
def live() -> dict:
    """Liveness: solo confirma que el proceso responde. Nunca toca el modelo."""
    return {"status": "alive"}


@app.get("/startup", tags=["probes"])
def startup(request: Request) -> dict:
    """Startup: 200 solo cuando el modelo cargo (o error si fallo la carga)."""
    state: ModelState = request.app.state.model
    if state is None or not state.is_ready():
        raise HTTPException(
            status_code=503,
            detail=f"Modelo aun no cargado: {state.error if state else 'state=None'}",
        )
    return {"status": "started", "loaded_at": state.loaded_at.isoformat()}


@app.get("/ready", tags=["probes"])
def ready(request: Request) -> dict:
    """Readiness: 200 si el servicio esta listo para tomar trafico."""
    state: ModelState = request.app.state.model
    if state is None or not state.is_ready():
        raise HTTPException(status_code=503, detail="No listo")
    return {"status": "ready", "model_version": MODEL_VERSION}


@app.get("/health", response_model=HealthOutput, tags=["probes"])
def health(request: Request) -> HealthOutput:
    """Alias legacy de /ready — mantiene compatibilidad con la guia del curso."""
    state: ModelState = request.app.state.model
    if state is None or not state.is_ready():
        raise HTTPException(status_code=503, detail="Modelo no cargado")
    return HealthOutput(status="ok", model_loaded=True, model_version=MODEL_VERSION)


# ---------------------------------------------------------------------------
# Predict
# ---------------------------------------------------------------------------
@app.post("/predict", response_model=PrediccionOutput, tags=["prediction"])
def predict(cliente: ClienteInput, request: Request) -> PrediccionOutput:
    """Prediccion single-record.

    Contract:
      200: prediccion con customer_risk_score en [0, 1] y flag `predicted_churn`
      422: input no cumple schema pydantic o regla de negocio
      503: modelo no disponible
    """
    state: ModelState = request.app.state.model
    if state is None or not state.is_ready():
        logger.error("predict_model_unavailable", extra={"json_fields": {"error": state.error if state else "state=None"}})
        raise HTTPException(status_code=503, detail="Modelo no disponible")

    # Regla de negocio (fuera del schema)
    _validar_coherencia_negocio(cliente)

    bundle = state.bundle
    estimator = bundle["estimator"]
    threshold = float(bundle["threshold_optimo"])

    X = _preparar_features(cliente, bundle["features"])
    proba = float(estimator.predict_proba(X)[0, 1])
    predicted_churn = bool(proba >= threshold)

    requested_by = (
        request.headers.get("x-goog-authenticated-user-email")
        or "unknown"
    )

    resultado = PrediccionOutput(
        customer_id=cliente.customer_id,
        customer_risk_score=round(proba, 4),
        predicted_churn=predicted_churn,
        threshold_used=round(threshold, 4),
        model_version=MODEL_VERSION,
        predicted_at=datetime.now(timezone.utc),
        requested_by=requested_by,
        source="api_single",
        input_file=None,
    )

    logger.info(
        "predict_ok",
        extra={"json_fields": {
            "input": cliente.model_dump(),
            "output": resultado.model_dump(mode="json"),
        }},
    )
    return resultado


# ---------------------------------------------------------------------------
# 422 handler con log estructurado (util para monitoreo de drift de esquema)
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def _log_422(request: Request, exc: RequestValidationError):
    logger.warning(
        "predict_422",
        extra={"json_fields": {
            "errors": exc.errors(),
            "path": request.url.path,
        }},
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
