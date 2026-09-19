"""Prediccion individual — invoca el servicio Cloud Run de U5.

Usa `gcloud auth print-identity-token` (subprocess) para obtener el token
en vez del SDK Python `google.oauth2.id_token`, que en el proyecto
compartido de la clase falla porque el usuario no tiene
`serviceusage.services.use`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import apply_page_config, sidebar_branding, page_header, kpi_row, footer

apply_page_config(page_title="Prediccion · Monitor U6")
sidebar_branding()

page_header(
    "Prediccion individual",
    "Formulario que invoca el servicio U5 (`u5-g02-cr-20260914`) con un "
    "identity token firmado. Cloud Run corre con `--no-allow-unauthenticated`.",
    directriz="Herramienta",
)

U5_SERVICE_NAME = os.getenv("U5_SERVICE_NAME", "u5-g02-cr-20260914")
U5_REGION = os.getenv("U5_REGION", "us-central1")


def _fetch_id_token(audience: str) -> str:
    """Identity token via gcloud CLI (evita ADC + serviceusage)."""
    if not shutil.which("gcloud"):
        raise RuntimeError(
            "El CLI `gcloud` no esta disponible. Instalar google-cloud-sdk."
        )
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
        tenure = st.number_input("tenure (meses)", 0, 100, 12)
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
            "**Que hacer:** exportar la variable de entorno antes de arrancar "
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
        with st.spinner("Firmando peticion y llamando al servicio..."):
            token = _fetch_id_token(url)
            resp = requests.post(
                f"{url.rstrip('/')}/predict",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
    except Exception as e:
        st.error(
            f"Fallo la peticion: `{type(e).__name__}: {e}`  \n"
            "**Diagnostico habitual:**\n"
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
            ("Prediccion",
             "Churn" if data["predicted_churn"] else "No churn",
             None),
        ])
        with st.expander("Payload completo de la respuesta"):
            st.json(data)
    else:
        st.warning(f"HTTP {resp.status_code} — la peticion fue rechazada por el servicio.")
        st.json(data)

footer(fuentes=["Cloud Run u5-g02-cr-20260914"])
