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

import requests
import streamlit as st


st.set_page_config(layout="wide")
st.markdown("""<style>
.block-container {padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1100px;}
h1 {font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0.25rem;}
h2 {font-weight: 600; letter-spacing: -0.01em; margin-top: 2rem;}
h3 {font-weight: 600; margin-top: 1.5rem;}
[data-testid="stMetricLabel"] {font-size: 0.8rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em;}
[data-testid="stMetricValue"] {font-size: 1.8rem; font-weight: 600;}
footer, [data-testid="stDecoration"] {display: none;}
</style>""", unsafe_allow_html=True)

st.title("Prediccion individual")
st.caption(
    "Formulario que invoca el servicio U5 (`u5-g02-cr-20260914`) con un "
    "identity token firmado. Cloud Run corre con `--no-allow-unauthenticated`."
)

CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL", "")


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


with st.sidebar:
    st.text_input(
        "Cloud Run URL", value=CLOUD_RUN_URL, key="url_input",
        help="URL base del servicio U5 (sin /predict).",
    )

url = st.session_state.get("url_input", CLOUD_RUN_URL)

st.subheader("Datos del cliente")

with st.form("prediccion"):
    c1, c2, c3 = st.columns(3)
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

    submitted = st.form_submit_button("Predecir", type="primary")

if submitted:
    if not url:
        st.error("Falta configurar `CLOUD_RUN_URL` (var de entorno o campo lateral).")
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
            r = requests.post(
                f"{url.rstrip('/')}/predict",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
    except Exception as e:
        st.error(f"Fallo la peticion: {type(e).__name__}: {e}")
        st.stop()

    st.subheader("Respuesta del servicio")
    try:
        data = r.json()
    except Exception:
        st.error(f"Respuesta no JSON: HTTP {r.status_code}\n\n{r.text[:1000]}")
        st.stop()

    if r.status_code == 200:
        c1, c2, c3 = st.columns(3)
        c1.metric("Risk score", f"{data['customer_risk_score']:.4f}")
        c2.metric("Threshold", f"{data['threshold_used']:.4f}")
        c3.metric("Prediccion", "Churn" if data["predicted_churn"] else "No churn")
        with st.expander("Payload completo"):
            st.json(data)
    else:
        st.warning(f"HTTP {r.status_code} — la peticion fue rechazada.")
        st.json(data)
