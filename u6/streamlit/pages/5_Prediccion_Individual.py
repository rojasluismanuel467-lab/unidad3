"""Predicción individual — invoca el servicio Cloud Run de U5.

En Cloud Run el token se obtiene desde el metadata server con el SDK oficial.
El fallback a `gcloud` queda únicamente para ejecutar Streamlit localmente.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests
import streamlit as st
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, kpi_row, footer

apply_page_config(page_title="Predicción · Monitor U6")
sidebar_branding()

page_header(
    "Predicción individual",
    "Formulario que invoca el servicio U5 (`u5-g02-cr-20260919`) con un "
    "identity token firmado. Cloud Run funciona con `--no-allow-unauthenticated`.",
    directriz="Herramienta",
)

U5_SERVICE_NAME = os.getenv("U5_SERVICE_NAME", "u5-g02-cr-20260919")
U5_REGION = os.getenv("U5_REGION", "us-central1")
# U5 conserva min-instances=0 por requerimiento del curso, así que la primera
# petición después de un periodo inactivo debe tolerar el arranque en frío.
U5_CONNECT_TIMEOUT_SECONDS = float(
    os.getenv("U5_CONNECT_TIMEOUT_SECONDS", "10")
)
U5_READ_TIMEOUT_SECONDS = float(
    os.getenv("U5_READ_TIMEOUT_SECONDS", "120")
)


def _fetch_id_token(audience: str) -> str:
    """Obtiene un identity token desde Cloud Run o desde gcloud local."""
    try:
        return id_token.fetch_id_token(google_requests.Request(), audience)
    except Exception as metadata_error:
        # En desarrollo local no existe el metadata server; allí se usa la
        # credencial de la sesión gcloud como fallback explícito.
        if not shutil.which("gcloud"):
            raise RuntimeError(
                "No fue posible obtener un identity token desde Cloud Run "
                f"ni se encontró gcloud localmente: {metadata_error}"
            ) from metadata_error
    result = subprocess.run(
        ["gcloud", "auth", "print-identity-token", f"--audiences={audience}"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gcloud fallo: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


@st.cache_data(ttl=300, show_spinner=False)
def _detectar_url_u5() -> str:
    """Autodetecta el URL del servicio U5 via `gcloud run services describe`.

    Orden de prioridad:
      1. Env var CLOUD_RUN_URL (override manual).
      2. `gcloud run services describe <U5_SERVICE_NAME> --region=<U5_REGION>`
         — usa el nombre por defecto del Grupo 2 pero se puede reescribir
         con env vars.
    """
    url = os.getenv("CLOUD_RUN_URL", "").strip()
    if url:
        return url
    if not shutil.which("gcloud"):
        return ""
    try:
        result = subprocess.run(
            ["gcloud", "run", "services", "describe", U5_SERVICE_NAME,
             f"--region={U5_REGION}", "--format=value(status.url)"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


url_detectado = _detectar_url_u5()

with st.sidebar:
    st.text_input(
        "Cloud Run URL", value=url_detectado, key="url_input",
        help=(
            "Autodetectado via `gcloud run services describe "
            f"{U5_SERVICE_NAME}`. Se puede sobreescribir aqui o con la "
            "env var `CLOUD_RUN_URL`."
        ),
    )
    if url_detectado:
        st.caption(f"URL autodetectado para `{U5_SERVICE_NAME}`.")

url = st.session_state.get("url_input", url_detectado)

st.subheader("Datos del cliente")

with st.form("prediccion"):
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        customer_id = st.text_input("customer_id", "TEST-001")
        gender = st.selectbox("gender", ["Female", "Male"])
        partner = st.checkbox("partner", value=True)
        dependents = st.checkbox("dependents", value=False)
    with c2:
        tenure = st.number_input("tenure (meses)", 0, 200, 12)
        contract = st.selectbox("contract", ["Month-to-month", "One year", "Two year"])
        payment_method = st.selectbox(
            "payment_method",
            ["Bank transfer (automatic)", "Credit card (automatic)",
             "Electronic check", "Mailed check"],
        )
    with c3:
        monthly_charges = st.number_input("monthly_charges", 0.0, 200.0, 89.5, step=0.5)
        internet_service = st.selectbox("internet_service", ["DSL", "Fiber optic", "No"])
        online_security = st.selectbox("online_security", ["Yes", "No", "No internet service"])
        tech_support = st.selectbox("tech_support", ["Yes", "No", "No internet service"])

    submitted = st.form_submit_button("Predecir", type="primary", use_container_width=False)

if submitted:
    if not url:
        st.error(
            "Falta configurar `CLOUD_RUN_URL`.  \n"
            "**Qué hacer:** exporta la variable de entorno antes de iniciar "
            "Streamlit, o pegar la URL en el campo del sidebar."
        )
        st.stop()

    payload = {
        "customer_id": customer_id, "gender": gender,
        "partner": partner, "dependents": dependents,
        "tenure": int(tenure),
        "contract": contract, "payment_method": payment_method,
        "monthly_charges": float(monthly_charges),
        "internet_service": internet_service,
        "online_security": online_security,
        "tech_support": tech_support,
    }

    try:
        with st.spinner("Firmando la petición y llamando al servicio..."):
            token = _fetch_id_token(url)
            resp = requests.post(
                f"{url.rstrip('/')}/predict",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=(
                    U5_CONNECT_TIMEOUT_SECONDS,
                    U5_READ_TIMEOUT_SECONDS,
                ),
            )
    except requests.ReadTimeout:
        st.error(
            "El API no respondió antes del límite de "
            f"{U5_READ_TIMEOUT_SECONDS:g} segundos. Como U5 usa "
            "`min-instances=0`, su primera llamada puede incluir el arranque "
            "en frío. Intenta nuevamente; si persiste, revisa los logs de U5."
        )
        st.stop()
    except Exception as e:
        st.error(
            f"Falló la petición: `{type(e).__name__}: {e}`  \n"
            "**Diagnóstico habitual:**\n"
            "- Sin `gcloud auth print-identity-token`: reautenticar con "
            "`gcloud auth login`.\n"
            "- Cloud Run responde 403: la cuenta activa no tiene "
            "`roles/run.invoker`."
        )
        st.stop()

    st.subheader("Respuesta del servicio")
    try:
        data = resp.json()
    except Exception:
        st.error(f"Respuesta no JSON: HTTP {resp.status_code}\n\n{resp.text[:1000]}")
        st.stop()

    if resp.status_code == 200:
        kpi_row([
            ("Risk score", f"{data['customer_risk_score']:.4f}",
             "Probabilidad de churn (calibrada)"),
            ("Threshold usado", f"{data['threshold_used']:.4f}",
             "Punto de corte optimo aprendido en Fase 1"),
            ("Predicción",
             "Churn" if data["predicted_churn"] else "No churn",
             None),
        ])
        with st.expander("Payload completo de la respuesta"):
            st.json(data)
    else:
        st.warning(f"HTTP {resp.status_code} — la petición fue rechazada por el servicio.")
        st.json(data)

footer(fuentes=["Cloud Run u5-g02-cr-20260919"])
