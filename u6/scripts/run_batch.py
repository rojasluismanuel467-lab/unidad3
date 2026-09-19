"""Script batch reutilizable — lee CSV, valida contra schema pydantic de U5,
invoca Cloud Run (identity token), separa 422 en cuarentena, escribe metricas.

Es la pieza que consume tanto el DAG como el Streamlit (opcional).

Uso:
    python run_batch.py \
        --csv u6/data/lotes_retencion_u6.csv \
        --url https://u5-g02-cr-20260914-xxxx.a.run.app \
        --out-dir u6/data/outputs/

Grupo 2 — Gabriel Escobar, David Artunduaga, Luis Rojas.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ENUMS = {
    "gender": {"Male", "Female"},
    "contract": {"Month-to-month", "One year", "Two year"},
    "payment_method": {
        "Bank transfer (automatic)", "Credit card (automatic)",
        "Electronic check", "Mailed check",
    },
    "internet_service": {"DSL", "Fiber optic", "No"},
    "online_security": {"Yes", "No", "No internet service"},
    "tech_support": {"Yes", "No", "No internet service"},
}


def _fetch_id_token(audience: str) -> str:
    import google.auth.transport.requests
    from google.oauth2 import id_token
    auth_req = google.auth.transport.requests.Request()
    return id_token.fetch_id_token(auth_req, audience)


def _to_payload(row: pd.Series) -> dict[str, Any]:
    """Convierte una fila del CSV en el payload que espera /predict.

    Rechaza NaN/None de forma explicita para que caigan como client_side_parse
    (rechazo del cliente) y no como network (json.dumps se rompe con NaN).
    """
    import math

    def yn_to_bool(v):
        return str(v).strip().lower() == "yes"

    def _to_int(v, name):
        n = pd.to_numeric(v, errors="raise")
        if pd.isna(n):
            raise ValueError(f"{name} es NaN/None")
        return int(n)

    def _to_float(v, name):
        n = pd.to_numeric(v, errors="raise")
        if pd.isna(n) or (isinstance(n, float) and math.isnan(n)):
            raise ValueError(f"{name} es NaN/None")
        return float(n)

    return {
        "customer_id": str(row["customerID"]),
        "gender": row["gender"],
        "partner": yn_to_bool(row.get("Partner")),
        "dependents": yn_to_bool(row.get("Dependents")),
        "tenure": _to_int(row["tenure"], "tenure"),
        "contract": row["Contract"],
        "payment_method": row["PaymentMethod"],
        "monthly_charges": _to_float(row["MonthlyCharges"], "monthly_charges"),
        "internet_service": row["InternetService"],
        "online_security": row["OnlineSecurity"],
        "tech_support": row["TechSupport"],
    }


def score_batch(
    df: pd.DataFrame,
    url: str,
    *,
    token: str | None = None,
    timeout: int = 15,
) -> tuple[list[dict], list[dict], dict]:
    """Score cada fila. Devuelve (predicciones, cuarentena, resumen)."""
    if token is None:
        token = _fetch_id_token(url)

    predicciones: list[dict] = []
    cuarentena: list[dict] = []
    session = requests.Session()
    endpoint = f"{url.rstrip('/')}/predict"

    for _, row in df.iterrows():
        # Intento construir el payload; si eso ya falla localmente,
        # va directo a cuarentena sin llamar al servicio (rechazo temprano).
        try:
            payload = _to_payload(row)
        except Exception as e:
            cuarentena.append({
                "customerID": str(row["customerID"]),
                "fecha_lote": row.get("fecha_lote"),
                "http_status": None,
                "error_type": "client_side_parse",
                "error_detail": str(e),
                "raw": row.astype(str).to_dict(),
            })
            continue

        try:
            r = session.post(
                endpoint, json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
        except Exception as e:
            cuarentena.append({
                "customerID": payload["customer_id"],
                "fecha_lote": row.get("fecha_lote"),
                "http_status": None,
                "error_type": "network",
                "error_detail": str(e),
                "raw": payload,
            })
            continue

        if r.status_code == 200:
            data = r.json()
            data["fecha_lote"] = row.get("fecha_lote")
            predicciones.append(data)
        else:
            cuarentena.append({
                "customerID": payload["customer_id"],
                "fecha_lote": row.get("fecha_lote"),
                "http_status": r.status_code,
                "error_type": "api_reject",
                "error_detail": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text,
                "raw": payload,
            })

    resumen = {
        "batch_id": datetime.now(timezone.utc).isoformat(),
        "n_total": int(len(df)),
        "n_predicciones": int(len(predicciones)),
        "n_cuarentena": int(len(cuarentena)),
        "tasa_rechazo": round(len(cuarentena) / max(len(df), 1) * 100, 3),
        "url": url,
    }
    return predicciones, cuarentena, resumen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path al CSV de entrada")
    ap.add_argument("--url", required=True, help="Cloud Run service URL")
    ap.add_argument("--out-dir", default="u6/data/outputs",
                    help="Carpeta destino para predicciones + cuarentena")
    ap.add_argument("--umbral-cuarentena-pct", type=float, default=2.5,
                    help="Si tasa_rechazo > umbral, exit code != 0")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    print(f"Cargadas {len(df)} filas de {args.csv}")

    predicciones, cuarentena, resumen = score_batch(df, args.url)
    print(json.dumps(resumen, indent=2))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(predicciones).to_csv(out / "predicciones.csv", index=False)
    pd.DataFrame(cuarentena).to_json(out / "cuarentena.jsonl",
                                     orient="records", lines=True)
    with open(out / "resumen.json", "w") as f:
        json.dump(resumen, f, indent=2)

    if resumen["tasa_rechazo"] > args.umbral_cuarentena_pct:
        print(
            f"ALARMA: tasa_rechazo={resumen['tasa_rechazo']}% "
            f"supera umbral={args.umbral_cuarentena_pct}%",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
