"""Contrato de entrada/salida del servicio churn-api (U5).

Refleja las 10 features seleccionadas y justificadas en la Tarea 1 (U3).
Los enums cierran el dominio de los categoricos -> FastAPI devuelve 422
automaticamente cuando un valor cae fuera del dominio esperado.

Grupo 2 - Gabriel Ernesto Escobar A00399291, David Artunduaga Penagos A00396342, Luis Manuel Rojas A00399289.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums (dominios cerrados)
# ---------------------------------------------------------------------------
class Gender(str, Enum):
    male = "Male"
    female = "Female"


class Contract(str, Enum):
    month_to_month = "Month-to-month"
    one_year = "One year"
    two_year = "Two year"


class PaymentMethod(str, Enum):
    bank_transfer = "Bank transfer (automatic)"
    credit_card = "Credit card (automatic)"
    electronic_check = "Electronic check"
    mailed_check = "Mailed check"


class InternetService(str, Enum):
    dsl = "DSL"
    fiber_optic = "Fiber optic"
    no = "No"


class YesNoNoInternet(str, Enum):
    """OnlineSecurity y TechSupport comparten este dominio."""
    yes = "Yes"
    no = "No"
    no_internet_service = "No internet service"


# ---------------------------------------------------------------------------
# Input - refleja las 10 features del modelo ganador (U4)
# ---------------------------------------------------------------------------
class ClienteInput(BaseModel):
    """Input del endpoint /predict.

    Todas las features son las mismas que se justificaron en U3:
      - Del set base: gender, Partner, Dependents, tenure, Contract,
        PaymentMethod, MonthlyCharges
      - Ampliadas (justificadas por EDA + proxy test): InternetService,
        OnlineSecurity, TechSupport

    SeniorCitizen NO forma parte del contrato (removido por instruccion
    del profesor en U3).
    """

    customer_id: str = Field(
        ..., min_length=1, max_length=64,
        description="Identificador del cliente. Se propaga al output para trazabilidad."
    )

    gender: Gender = Field(..., description="Male | Female")
    partner: bool = Field(..., description="True si el cliente tiene pareja")
    dependents: bool = Field(..., description="True si el cliente tiene dependientes")
    tenure: int = Field(
        ..., ge=0, le=200,
        description=(
            "Meses de antiguedad como cliente. Rango original 0-100 se amplio "
            "a 0-200 en U6 tras detectar cliente RET-0548 con tenure=130 "
            "rechazado erroneamente (10.8 anios es plausible en telecom)."
        ),
    )

    contract: Contract = Field(..., description="Month-to-month | One year | Two year")
    payment_method: PaymentMethod = Field(
        ...,
        description="Bank transfer | Credit card | Electronic check | Mailed check"
    )
    monthly_charges: float = Field(
        ..., gt=0.0, le=200.0,
        description="Cargo mensual en USD"
    )

    internet_service: InternetService = Field(
        ..., description="DSL | Fiber optic | No"
    )
    online_security: YesNoNoInternet = Field(
        ..., description="Yes | No | 'No internet service' (si internet_service=No)"
    )
    tech_support: YesNoNoInternet = Field(
        ..., description="Yes | No | 'No internet service' (si internet_service=No)"
    )

    # NOTA: la coherencia (online_security requires internet_service) es LOGICA DE NEGOCIO,
    # se valida en main.py (_validar_coherencia_negocio). Pydantic aqui solo valida tipos
    # y dominios cerrados. Si el modelo se re-entrena con otra logica, no toca este schema.

    model_config = {
        "json_schema_extra": {
            "example": {
                "customer_id": "TEST-001",
                "gender": "Female",
                "partner": True,
                "dependents": False,
                "tenure": 12,
                "contract": "Month-to-month",
                "payment_method": "Electronic check",
                "monthly_charges": 70.5,
                "internet_service": "Fiber optic",
                "online_security": "No",
                "tech_support": "No",
            }
        }
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
class PrediccionOutput(BaseModel):
    """Output del endpoint /predict."""

    customer_id: str
    customer_risk_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Probabilidad de churn (calibrada) en [0, 1]"
    )
    predicted_churn: bool = Field(
        ...,
        description="True si customer_risk_score >= threshold_used"
    )
    threshold_used: float = Field(
        ..., ge=0.0, le=1.0,
        description="Threshold optimo aprendido en Fase 1 (minimiza costo negocio)"
    )
    model_version: str = Field(..., description="Version registrada del modelo (Model Registry)")
    predicted_at: datetime = Field(..., description="Timestamp UTC de la prediccion")
    requested_by: str = Field(..., description="Identidad IAM del solicitante (Cloud Run)")
    source: Literal["api_single", "api_batch"] = Field(
        ..., description="Origen de la peticion"
    )
    input_file: Optional[str] = Field(
        default=None,
        description="Nombre del archivo si source='api_batch'"
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthOutput(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    model_loaded: bool
    model_version: Optional[str] = None
