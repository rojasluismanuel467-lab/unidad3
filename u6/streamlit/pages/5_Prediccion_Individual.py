"""Prediccion individual — invoca el servicio Cloud Run de U5 con identity token."""
from __future__ import annotations

import os
from pathlib import Path

import requests
import streamlit as st

st.title(":target: Prediccion individual — Cloud Run (U5)")

st.markdown(
    """
Este formulario invoca el servicio de U5 (`u5-g02-cr-20260914`) con un
identity token firmado (Cloud Run tiene `--no-allow-unauthenticated`).

**Requisito:** la variable de entorno `CLOUD_RUN_URL` debe apuntar al
servicio, y el proceso donde corre Streamlit necesita credenciales
de un SA con `roles/run.invoker`.
"""
)

CLOUD_RUN_URL = os.getenv("CLOUD_RUN_URL", "")


def _fetch_id_token(audience: str) -> str:
    """Obtiene un identity token para el audience dado (Cloud Run URL)."""
    import google.auth.transport.requests
    from google.oauth2 import id_token

    auth_req = google.auth.transport.requests.Request()
    return id_token.fetch_id_token(auth_req, audience)


with st.sidebar:
    st.text_input("Cloud Run URL", value=CLOUD_RUN_URL, key="url_input",
                  help="URL del servicio Cloud Run desplegado en U5.")

url = st.session_state.get("url_input", CLOUD_RUN_URL)

with st.form("prediccion"):
    st.subheader("Datos del cliente")
    c1, c2, c3 = st.columns(3)
    with c1:
        customer_id = st.text_input("customer_id", "TEST-001")
        gender = st.selectbox("gender", ["Female", "Male"])
        partner = st.checkbox("partner", value=True)
        dependents = st.checkbox("dependents", value=False)
    with c2:
        tenure = st.number_input("tenure (meses)", min_value=0, max_value=100, value=12)
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

    submitted = st.form_submit_button(":rocket: Predecir")

if submitted:
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

    if not url:
        st.error("Falta configurar `CLOUD_RUN_URL` (variable de entorno o campo lateral).")
    else:
        try:
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
            st.code(f"HTTP {r.status_code}")
            data = r.json()
            if r.status_code == 200:
                col1, col2, col3 = st.columns(3)
                col1.metric("Risk score", f"{data['customer_risk_score']:.4f}")
                col2.metric("Threshold usado", f"{data['threshold_used']:.4f}")
                col3.metric("Predicted churn",
                            ":red_circle: SI" if data["predicted_churn"] else ":green_circle: NO")
                st.json(data)
            else:
                st.warning(f"Respuesta {r.status_code} — la peticion fue rechazada.")
                st.json(data)
        except Exception as e:
            st.error(f"Fallo la peticion: {type(e).__name__}: {e}")
            st.caption(
                "Diagnostico habitual: `default credentials not found` = falta "
                "`GOOGLE_APPLICATION_CREDENTIALS` apuntando a un SA JSON."
            )
