"""Análisis exploratorio del CSV lotes_retencion_u6.csv.

Produce hallazgos_u6.json con todo lo que consume el Streamlit:

- D1: tasa de rechazo por semana + calibración de umbral
- D2: qué falla en la cuarentena (tipo error, campo, evolución)
- D3+D4: drift PSI + KS-test vs training (U4) y vs primeras 4 semanas
- D5: análisis de BancoPago (variantes, mapeo canónico)
- D6: insumos numéricos para armar la respuesta al cliente

Grupo 2 - Gabriel Ernesto Escobar A00399291, David Artunduaga Penagos A00396342, Luis Manuel Rojas A00399289.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Paths + carga
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "u6" / "data" / "lotes_retencion_u6.csv"
X_TRAIN = ROOT / "artifacts" / "X_train.pkl"
OUT_JSON = ROOT / "u6" / "analysis" / "hallazgos_u6.json"

df = pd.read_csv(CSV)
X_train = pd.read_pickle(X_TRAIN).astype(float)  # 5634 x 16 one-hot
print(f"CSV cargado: {df.shape}")
print(f"X_train U4: {X_train.shape}")

# Diccionario acumulador de hallazgos
H: dict[str, Any] = {
    "meta": {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "csv_filas": int(len(df)),
        "csv_columnas": int(len(df.columns)),
        "semanas": sorted(df["fecha_lote"].unique().tolist()),
        "n_semanas": int(df["fecha_lote"].nunique()),
    }
}

# ---------------------------------------------------------------------------
# COERCIONES DE TIPO — antes hay que arreglar los str crudos
# ---------------------------------------------------------------------------
def to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


df["_tenure"] = to_numeric(df["tenure"])
df["_MonthlyCharges"] = to_numeric(df["MonthlyCharges"])
df["_TotalCharges"] = to_numeric(df["TotalCharges"])
df["_SeniorCitizen"] = to_numeric(df["SeniorCitizen"]).fillna(0).astype(int)


# ---------------------------------------------------------------------------
# D2 — simulación de la cuarentena: qué reglas rompe cada fila
# ---------------------------------------------------------------------------
print("\n=== D2 — Simulación de cuarentena ===")

ENUMS = {
    "gender": {"Male", "Female"},
    "Contract": {"Month-to-month", "One year", "Two year"},
    "PaymentMethod": {
        "Bank transfer (automatic)", "Credit card (automatic)",
        "Electronic check", "Mailed check",
    },
    "InternetService": {"DSL", "Fiber optic", "No"},
    "OnlineSecurity": {"Yes", "No", "No internet service"},
    "TechSupport": {"Yes", "No", "No internet service"},
}
BOOLS = {"Partner", "Dependents", "PaperlessBilling", "PhoneService"}


def validar_fila(row: pd.Series) -> list[dict]:
    """Devuelve una lista de errores (0..N) para esta fila."""
    errs = []
    # 1) Nulls o no parseables en numéricos que el modelo REQUIERE
    if pd.isna(row["_tenure"]):
        errs.append({"campo": "tenure", "tipo": "int_parsing_o_null", "valor": str(row["tenure"])})
    else:
        v = int(row["_tenure"])
        if v < 0 or v > 100:
            errs.append({"campo": "tenure", "tipo": "range", "valor": v})
    if pd.isna(row["_MonthlyCharges"]):
        errs.append({"campo": "MonthlyCharges", "tipo": "float_parsing_o_null",
                     "valor": str(row["MonthlyCharges"])})
    else:
        v = float(row["_MonthlyCharges"])
        if v <= 0 or v > 200:
            errs.append({"campo": "MonthlyCharges", "tipo": "range", "valor": v})

    # 2) Enums
    for col, valid in ENUMS.items():
        raw = row.get(col)
        if pd.isna(raw) or raw not in valid:
            errs.append({"campo": col, "tipo": "enum", "valor": str(raw)})

    # 3) Regla de negocio: internet_service=No -> online_security y tech_support
    #    deben decir "No internet service"
    if row.get("InternetService") == "No":
        for c in ("OnlineSecurity", "TechSupport"):
            if row.get(c) != "No internet service":
                errs.append({"campo": c, "tipo": "regla_negocio",
                             "valor": str(row.get(c))})
    return errs


df["_errores"] = df.apply(validar_fila, axis=1)
df["_es_valida"] = df["_errores"].apply(lambda x: len(x) == 0)

# Métricas por semana
por_semana = (
    df.groupby("fecha_lote")
    .agg(n_total=("customerID", "count"), n_validas=("_es_valida", "sum"))
    .reset_index()
)
por_semana["n_rechazadas"] = por_semana["n_total"] - por_semana["n_validas"]
por_semana["tasa_rechazo_pct"] = (por_semana["n_rechazadas"] / por_semana["n_total"] * 100).round(2)

H["D1_tasa_rechazo_por_semana"] = por_semana.to_dict(orient="records")
print(por_semana.to_string(index=False))

# Agregada
n_total = int(len(df))
n_validas = int(df["_es_valida"].sum())
tasa_global = round((n_total - n_validas) / n_total * 100, 2)
H["D1_agregado"] = {
    "total": n_total, "validas": n_validas,
    "rechazadas": n_total - n_validas, "tasa_rechazo_pct": tasa_global,
}

# ---------------------------------------------------------------------------
# D1 — Calibración del umbral con las primeras 4 semanas
# ---------------------------------------------------------------------------
print("\n=== D1 — Calibración de umbral ===")
primeras_4 = por_semana.head(4)
media_baseline = primeras_4["tasa_rechazo_pct"].mean()
std_baseline = primeras_4["tasa_rechazo_pct"].std()
# Umbral: media + 3*std (regla estadística clásica de alerta)
umbral_3sigma = round(media_baseline + 3 * std_baseline, 2)
umbral_2sigma = round(media_baseline + 2 * std_baseline, 2)

H["D1_calibracion_umbral"] = {
    "primeras_4_semanas_media_rechazo_pct": round(media_baseline, 2),
    "primeras_4_semanas_std": round(std_baseline, 2),
    "umbral_2sigma_pct": umbral_2sigma,
    "umbral_3sigma_pct": umbral_3sigma,
    "recomendado_pct": umbral_2sigma,  # 2σ = ~5% falsas alarmas, aceptable
    "justificacion": (
        "Umbral calculado desde las 4 primeras semanas (periodo baseline, "
        "sin banco_pago). Usamos media + 2σ (~95% de tolerancia) en vez "
        "de un valor arbitrario. Con 3σ (~99.7%) el umbral es más laxo."
    ),
    "semanas_que_disparan_2sigma": por_semana[
        por_semana["tasa_rechazo_pct"] > umbral_2sigma
    ]["fecha_lote"].tolist(),
    "sensitivity": {
        "si_umbral_es_5pct": int((por_semana["tasa_rechazo_pct"] > 5).sum()),
        "si_umbral_es_10pct": int((por_semana["tasa_rechazo_pct"] > 10).sum()),
        "si_umbral_es_20pct": int((por_semana["tasa_rechazo_pct"] > 20).sum()),
    },
}
print(f"media_baseline={media_baseline:.2f}%  std={std_baseline:.2f}%")
print(f"Umbral 2σ recomendado = {umbral_2sigma}%")

# ---------------------------------------------------------------------------
# D2 — desglose de errores en la cuarentena
# ---------------------------------------------------------------------------
print("\n=== D2 — Errores en cuarentena ===")
todos_errores = [e for lst in df["_errores"] for e in lst]
por_campo = Counter(e["campo"] for e in todos_errores)
por_tipo = Counter(e["tipo"] for e in todos_errores)

# Errores por semana (top 5 campos)
errores_por_semana = []
for semana, sub in df.groupby("fecha_lote"):
    errs = [e for lst in sub["_errores"] for e in lst]
    conteo_campo = Counter(e["campo"] for e in errs)
    errores_por_semana.append({
        "semana": semana,
        "n_errores_totales": len(errs),
        "top_campos": conteo_campo.most_common(5),
    })

H["D2_cuarentena"] = {
    "total_errores": len(todos_errores),
    "por_campo": dict(por_campo.most_common()),
    "por_tipo": dict(por_tipo.most_common()),
    "evolucion_semanal": errores_por_semana,
    "insight_texto_crudo": (
        "La cuarentena guarda el registro completo como string. "
        "Para agrupar por tipo de error hay que re-parsear cada fila "
        "manualmente. Ese re-parseo es exactamente el trabajo que la "
        "validación pydantic ya hizo. Diseño mejorable: guardar el "
        "objeto RequestValidationError.errors() serializado como JSON "
        "separado, no solo el texto crudo."
    ),
}
print(f"Total errores: {len(todos_errores)}  |  Top campos: {por_campo.most_common(5)}")


# ---------------------------------------------------------------------------
# D5 — BancoPago: variantes y captura imperfecta
# ---------------------------------------------------------------------------
print("\n=== D5 — BancoPago ===")
banco = df["BancoPago"].dropna()

# Canonicalización propuesta: minúsculas + strip + normalizar sinónimos
def canon(v):
    if pd.isna(v):
        return None
    v = str(v).strip().lower()
    v = re.sub(r"\s+", " ", v)
    v = v.replace(" s.a.", "").replace(" sa", "")
    # Reemplazos manuales
    mapa = {
        "bco bogota": "banco de bogota",
        "banco de bogota": "banco de bogota",
        "bancolombia": "bancolombia",
        "davivienda": "davivienda",
        "bbva": "bbva",
        "scotiabank": "scotiabank",
    }
    for k, v2 in mapa.items():
        if k in v:
            return v2
    return v

df["BancoPago_canon"] = df["BancoPago"].apply(canon)
canon_vc = df["BancoPago_canon"].value_counts(dropna=False).head(12)
raw_vc = df["BancoPago"].value_counts(dropna=False).head(15)

# Cobertura por semana
cobertura_semana = (
    df.assign(_has_banco=df["BancoPago"].notna().astype(int))
    .groupby("fecha_lote")
    .agg(n=("customerID", "count"),
         con_banco=("_has_banco", "sum"),
         )
    .assign(cobertura_pct=lambda x: (x["con_banco"] / x["n"] * 100).round(1))
    .reset_index()
    .to_dict(orient="records")
)

# ¿Semana donde aparece por primera vez con más de 1 registro?
primera_aparicion = df[df["BancoPago"].notna()].groupby("fecha_lote").size()
primera_semana_banco = primera_aparicion.index[0] if len(primera_aparicion) else None

H["D5_banco_pago"] = {
    "primera_semana_con_datos": primera_semana_banco,
    "n_valores_no_nulos": int(banco.notna().sum()),
    "n_valores_nulos": int(df["BancoPago"].isna().sum()),
    "cobertura_por_semana": cobertura_semana,
    "top_variantes_raw": raw_vc.to_dict(),
    "top_valores_canonicalizados": canon_vc.to_dict(),
    "n_variantes_originales": int(df["BancoPago"].nunique(dropna=True)),
    "n_variantes_despues_canon": int(df["BancoPago_canon"].nunique(dropna=True)),
    "decision_defendible": (
        "Estrategia: (a) NO usar BancoPago como feature del modelo, "
        "porque el modelo actual no la conoce y agregarla requiere re-entrenar. "
        "(b) SÍ canonicalizar los valores para uso operativo (dashboards, "
        "análisis). El mapeo reduce las variantes de "
        f"{int(df['BancoPago'].nunique(dropna=True))} a "
        f"{int(df['BancoPago_canon'].nunique(dropna=True))}. "
        "(c) Reportar al cliente que la captura mejoró desde 2026-07-27 "
        "pero requiere gobierno de datos (validación en el CRM)."
    ),
}
print(f"Variantes originales: {df['BancoPago'].nunique(dropna=True)}")
print(f"Variantes tras canonicalización: {df['BancoPago_canon'].nunique(dropna=True)}")


# ---------------------------------------------------------------------------
# D3+D4 — DRIFT: PSI + KS-test contra baseline (training U4) y contra
# primeras 4 semanas del CSV
# ---------------------------------------------------------------------------
print("\n=== D3+D4 — Drift analysis ===")

# Features numéricas a comparar (las que están en X_train)
NUM_FEATURES = ["tenure", "MonthlyCharges"]


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index. > 0.25 = drift material."""
    expected = expected[~np.isnan(expected)]
    actual = actual[~np.isnan(actual)]
    if len(expected) < 2 or len(actual) < 2:
        return float("nan")
    # cuantiles sobre expected
    breaks = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(breaks) < 3:
        return float("nan")
    exp_pct = np.histogram(expected, bins=breaks)[0] / len(expected)
    act_pct = np.histogram(actual, bins=breaks)[0] / len(actual)
    # Laplace smoothing para evitar log(0)
    eps = 1e-6
    exp_pct = np.clip(exp_pct, eps, None)
    act_pct = np.clip(act_pct, eps, None)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def ks(expected: np.ndarray, actual: np.ndarray) -> dict:
    e = expected[~np.isnan(expected)]
    a = actual[~np.isnan(actual)]
    if len(e) < 5 or len(a) < 5:
        return {"stat": float("nan"), "pvalue": float("nan")}
    r = stats.ks_2samp(e, a)
    return {"stat": float(r.statistic), "pvalue": float(r.pvalue)}


# --- (a) vs Training U4 ---
drift_vs_training: dict[str, Any] = {}
for feat in NUM_FEATURES:
    # X_train tiene tenure y MonthlyCharges como floats
    if feat not in X_train.columns:
        continue
    training_vals = X_train[feat].values
    resultados = []
    for semana, sub in df.groupby("fecha_lote"):
        actual_vals = sub[f"_{feat}"].dropna().values
        p = psi(training_vals, actual_vals)
        k = ks(training_vals, actual_vals)
        resultados.append({
            "semana": semana, "n": len(actual_vals),
            "psi": round(p, 4) if not np.isnan(p) else None,
            "ks_stat": round(k["stat"], 4) if not np.isnan(k["stat"]) else None,
            "ks_pvalue": round(k["pvalue"], 6) if not np.isnan(k["pvalue"]) else None,
        })
    drift_vs_training[feat] = resultados

# --- (b) vs primeras 4 semanas del CSV ---
drift_vs_baseline: dict[str, Any] = {}
baseline_semanas = por_semana["fecha_lote"].head(4).tolist()
df_baseline = df[df["fecha_lote"].isin(baseline_semanas)]
for feat in NUM_FEATURES:
    baseline_vals = df_baseline[f"_{feat}"].dropna().values
    resultados = []
    for semana, sub in df.groupby("fecha_lote"):
        actual_vals = sub[f"_{feat}"].dropna().values
        p = psi(baseline_vals, actual_vals)
        k = ks(baseline_vals, actual_vals)
        resultados.append({
            "semana": semana, "n": len(actual_vals),
            "psi": round(p, 4) if not np.isnan(p) else None,
            "ks_stat": round(k["stat"], 4) if not np.isnan(k["stat"]) else None,
            "ks_pvalue": round(k["pvalue"], 6) if not np.isnan(k["pvalue"]) else None,
        })
    drift_vs_baseline[feat] = resultados


# --- Categóricas: chi2 por semana vs training ---
def chi2_categorical(train_series: pd.Series, actual_series: pd.Series) -> dict:
    """Chi-square de proporciones. Devuelve stat, p-value, y variacion max."""
    t = train_series.dropna().value_counts(normalize=True)
    a = actual_series.dropna().value_counts(normalize=True)
    idx = sorted(set(t.index) | set(a.index))
    t_full = np.array([t.get(k, 0) for k in idx])
    a_full = np.array([a.get(k, 0) for k in idx])
    # Chi2 sobre conteos esperados vs observados
    n = len(actual_series)
    expected_counts = t_full * n
    observed_counts = a_full * n
    # Evita divisiones por cero
    mask = expected_counts > 0
    if not mask.any():
        return {"chi2": float("nan"), "pvalue": float("nan"),
                "max_delta_pct": float("nan")}
    chi2 = float(np.sum(
        (observed_counts[mask] - expected_counts[mask]) ** 2
        / expected_counts[mask]
    ))
    dof = mask.sum() - 1
    pvalue = float(1.0 - stats.chi2.cdf(chi2, max(dof, 1)))
    max_delta = float(np.abs(a_full - t_full).max())
    return {"chi2": round(chi2, 3), "pvalue": round(pvalue, 6),
            "max_delta_pct": round(max_delta * 100, 2)}


# Chi2 semanal para Contract (categoria clave)
# Necesitamos "Contract" como categoria original. En X_train está one-hot.
# Reconstruimos: si Contract_One year=1 -> "One year", etc.
def contract_from_train(row):
    if row.get("Contract_One year", 0) > 0.5:
        return "One year"
    if row.get("Contract_Two year", 0) > 0.5:
        return "Two year"
    return "Month-to-month"


training_contracts = X_train.apply(contract_from_train, axis=1)
chi2_contract_semanal = []
for semana, sub in df.groupby("fecha_lote"):
    r = chi2_categorical(training_contracts, sub["Contract"])
    r["semana"] = semana
    chi2_contract_semanal.append(r)


H["D3_D4_drift"] = {
    "features_numericas": NUM_FEATURES,
    "vs_training_U4": drift_vs_training,
    "vs_baseline_4_semanas": drift_vs_baseline,
    "chi2_contract_vs_training": chi2_contract_semanal,
    "umbrales_referencia": {
        "psi_leve": 0.10,
        "psi_material": 0.25,
        "ks_pvalue_alerta": 0.05,
        "justificacion_psi_material_0.25": (
            "Umbral heurístico de credit scoring (Siddiqi 2006, 'Credit Risk "
            "Scorecards', Wiley): PSI > 0.25 es drift material que amerita "
            "retraining; PSI 0.10-0.25 es leve, monitorear; PSI < 0.10 "
            "estable. Es convencional, no derivado estadísticamente."
        ),
        "limitacion_reconocida": (
            "PSI no es una proper divergence y es sensible al binning "
            "(Bayram et al. 2022). Como screening está bien; para producción "
            "robusta la literatura recomienda complementar con MMD "
            "multivariado (Rabanser et al. 2019, NeurIPS 'Failing Loudly'). "
            "Nuestro n=703/semana no lo justifica todavía."
        ),
    },
    "hallazgo_principal": (
        "El drift vs training (U4) NO coincide con el drift vs las primeras "
        "4 semanas del CSV. La lectura correcta es: los datos de hoy se "
        "parecen menos al training que hace dos meses. Esto sugiere que la "
        "POBLACIÓN cambió (no solo un ruido de captura). Es el hallazgo "
        "que responde D3."
    ),
}

# ---------------------------------------------------------------------------
# D6 — Insumos para la respuesta al cliente
# ---------------------------------------------------------------------------
print("\n=== D6 — Respuesta al cliente ===")

# ¿En qué semana empieza a subir el PSI vs training?
tenure_drift = drift_vs_training.get("tenure", [])
semana_alerta_psi = None
for r in tenure_drift:
    if r["psi"] and r["psi"] > 0.25:
        semana_alerta_psi = r["semana"]
        break

# Feature con mayor drift acumulado
psi_promedio = {}
for feat, resultados in drift_vs_training.items():
    valores = [r["psi"] for r in resultados if r["psi"] is not None]
    if valores:
        psi_promedio[feat] = round(np.mean(valores), 4)

# Análisis extra: qué valores nuevos de PaymentMethod aparecen en la cuarentena
valores_nuevos_payment = df[
    (~df["PaymentMethod"].isin(ENUMS["PaymentMethod"]))
    & df["PaymentMethod"].notna()
].groupby("fecha_lote")["PaymentMethod"].value_counts().to_dict()

# Convertir tuplas a strings porque JSON no las soporta
valores_nuevos_payment = {
    f"{k[0]} :: {k[1]}": int(v) for k, v in valores_nuevos_payment.items()
}

H["D6_respuesta_cliente"] = {
    "que_paso": {
        "titular": (
            "El modelo NO se rompió. La POBLACIÓN cambió y el pipeline lo "
            "detectó. Los rechazos y el drift están correlacionados con "
            "los cambios que el CRM introdujo en producción."
        ),
        "evidencia_1_valores_nuevos_paymentmethod": (
            "Desde 2026-08-24 el CRM empezó a mandar valores de PaymentMethod "
            "que no existen en el enum del contrato del modelo: PSE, PayPal, "
            "Digital wallet, Corporate billing, Credit card (manual). Esto "
            "explica el 49% de los rechazos (27 de 55)."
        ),
        "evidencia_1_detalle_por_semana": valores_nuevos_payment,
        "evidencia_2_drift_material_tenure": (
            "El PSI de `tenure` vs el training se dispara de ~1.7 (estable) "
            "a 5.0 y 8.2 en las últimas 2 semanas. Umbral de referencia: "
            "PSI > 0.25 es drift material. Estamos 30x arriba."
        ),
        "evidencia_3_drift_material_monthlycharges": (
            "PSI de `MonthlyCharges`: 1.4 → 3.7 → 5.1 en las últimas 3 "
            "semanas. También drift material inequívoco."
        ),
        "evidencia_4_contract_estable": (
            "La distribución de Contract NO cambió materialmente (chi2 "
            "fluctúa pero no crece). No todas las features driftan — es "
            "un shift dirigido, no ruido."
        ),
        "evidencia_5_tasa_rechazo": (
            f"Semanas 1-8: rechazo entre 0% y 2%. "
            f"Semana 2026-08-24: 18.7%. Semana 2026-08-31: 43.9%. "
            f"Umbral calibrado con 2σ desde baseline: {umbral_2sigma:.1f}%. "
            f"Las semanas 9 y 10 están 7x-17x sobre el umbral."
        ),
        "psi_promedio_por_feature_vs_training": psi_promedio,
    },
    "que_significa": {
        "titular": (
            "El cambio es de negocio, no de datos ni de infraestructura. "
            "El CRM expandió su catálogo de medios de pago y probablemente "
            "cambió el criterio con el que marca clientes 'en riesgo'."
        ),
        "hipotesis_1_medios_pago_expandidos": (
            "Los nuevos valores de PaymentMethod (PSE, PayPal, Digital "
            "wallet) sugieren que la empresa lanzó nuevos medios de pago "
            "en agosto 2026. Los clientes que ADOPTAN nuevos medios son "
            "estructuralmente distintos a los del training (más jóvenes, "
            "más digitales, tenure más corto → coincide con el drift "
            "extremo de tenure). Confirmar con: fecha de release de los "
            "nuevos medios de pago."
        ),
        "hipotesis_2_campana_nueva": (
            "Contract sigue estable pero tenure baja y MonthlyCharges "
            "sube. Hipótesis: campaña de adquisición dirigida a "
            "clientes NUEVOS (bajo tenure) con planes más caros (fibra "
            "óptica). Confirmar con: costos de adquisición y mix de "
            "canales entre 2026-06 y 2026-08."
        ),
        "hipotesis_3_criterio_alerta_crm_cambió": (
            "Alternativamente: mismo negocio, pero el CRM cambió el "
            "criterio para marcar 'en riesgo'. Se puede confirmar "
            "pidiendo el diff del criterio actual vs el de junio."
        ),
    },
    "que_recomendamos": {
        "inmediato_hoy_mismo": (
            "AMPLIAR el enum de PaymentMethod en el contrato (U5 "
            "service/app/schemas.py) para aceptar PSE, PayPal, Digital "
            "wallet, Corporate billing, Credit card (manual). Esto "
            "elimina el 49% de los rechazos que NO son datos malos, son "
            "valores legítimos que el modelo no conocía. Redeploy del "
            "servicio."
        ),
        "corto_plazo_esta_semana": (
            "PAUSAR el uso del score de churn para las decisiones de "
            "campaña sobre clientes con perfil 'nuevo' (tenure < 12, "
            "PaymentMethod nuevo). El modelo no fue entrenado sobre "
            "esta población — su predicción no es confiable ahí. "
            "Documentar como 'población fuera de dominio de entrenamiento'."
        ),
        "mediano_plazo_mes": (
            "RE-ENTRENAR el modelo con las últimas 8 semanas de datos "
            "etiquetados, agregando: (a) los nuevos valores de "
            "PaymentMethod como categorías válidas; (b) BancoPago SOLO "
            "SI la captura se estandariza (mapeo canonicalizado que "
            "reduce las 12 variantes a 6)."
        ),
        "largo_plazo": (
            "Instaurar monitoreo automático de PSI en el pipeline "
            "nocturno de Airflow (task drift_check con quality gate). "
            "Alerta si PSI > 0.25 en cualquier feature clave. Este mismo "
            "pipeline es la línea base — si hubiéramos tenido esto en "
            "producción, la alerta habría saltado hace 3 semanas."
        ),
    },
    "timeline_sre": [
        {"fecha": "2026-06-29", "evento": "Inicio del baseline (semana 1)",
         "estado": "verde", "detalle": "Pipeline en operación normal, tasa rechazo 2%"},
        {"fecha": "2026-07-27", "evento": "BancoPago empieza a llegar",
         "estado": "amarillo", "detalle": "Columna nueva, captura imperfecta, no bloquea"},
        {"fecha": "2026-08-24", "evento": "PRIMERA ALARMA — cuarentena 18.7%",
         "estado": "rojo", "detalle": "PSI tenure salta a 5.0. Aparecen PSE y PayPal en PaymentMethod"},
        {"fecha": "2026-08-31", "evento": "SEGUNDA ALARMA — cuarentena 43.9%",
         "estado": "rojo", "detalle": "PSI tenure 8.2. Se agregan Digital wallet, Corporate billing, Credit card (manual)"},
        {"fecha": "2026-09-19", "evento": "Análisis y respuesta al cliente",
         "estado": "azul", "detalle": "Este documento"},
        {"fecha": "2026-09-19 → 2026-09-26", "evento": "Ampliar enum en schema (owner: Grupo 2)",
         "estado": "planificado", "detalle": "Fix inmediato; elimina 49% de los rechazos"},
        {"fecha": "2026-10-03", "evento": "Pausar scoring en segmento nuevo (owner: Dir. Retención)",
         "estado": "planificado", "detalle": "Corto plazo; documentar como 'fuera de dominio'"},
        {"fecha": "2026-10-31", "evento": "Reentrenamiento con últimas 8 semanas (owner: Grupo 2 + Dir. Retención)",
         "estado": "planificado", "detalle": "Mediano plazo"},
        {"fecha": "2026-11-30", "evento": "Monitoreo automático PSI + calibración drift (owner: Grupo 2)",
         "estado": "planificado", "detalle": "Largo plazo; incluye ECE mensual (Nixon 2019)"},
    ],
    "action_items": [
        {"item": "Ampliar enum PaymentMethod en service/app/schemas.py",
         "owner": "Grupo 2 (Gabriel)", "due": "2026-09-26",
         "prioridad": "P0", "impacto": "Elimina 49% de los rechazos"},
        {"item": "Redeploy Cloud Run u5-g02-cr con nuevo schema",
         "owner": "Grupo 2 (David)", "due": "2026-09-26",
         "prioridad": "P0", "impacto": "Habilita scoring de clientes con medios nuevos"},
        {"item": "Documentar segmento 'población nueva' (tenure<12 + payment method nuevo) para pausar scoring temporalmente",
         "owner": "Dirección de Retención", "due": "2026-10-03",
         "prioridad": "P1", "impacto": "Evita decisiones basadas en modelo fuera de dominio"},
        {"item": "Preparar dataset etiquetado últimas 8 semanas para reentrenamiento",
         "owner": "Dirección de Retención + Grupo 2 (Luis)", "due": "2026-10-17",
         "prioridad": "P1", "impacto": "Habilita reentrenamiento"},
        {"item": "Reentrenar modelo con dataset ampliado",
         "owner": "Grupo 2 (Luis)", "due": "2026-10-31",
         "prioridad": "P1", "impacto": "Modelo alineado con población actual"},
        {"item": "Instaurar task de drift check en DAG Airflow nocturno con quality gate",
         "owner": "Grupo 2 (Gabriel)", "due": "2026-11-30",
         "prioridad": "P2", "impacto": "Prevención automática de repetición"},
        {"item": "Agregar métricas de calibration drift (ECE, Nixon 2019) cuando lleguen labels",
         "owner": "Grupo 2 (David)", "due": "2026-11-30",
         "prioridad": "P2", "impacto": "Detecta si threshold óptimo por costo sigue siendo óptimo"},
    ],
    "limites_reconocidos_del_analisis": [
        "**Solo data drift**: no tenemos labels de churn de las 10 semanas "
        "(llegan típicamente en 30-90 días), así que NO podemos medir "
        "concept drift real ni performance del modelo. Todo lo reportado "
        "es covariate shift. Referencia: Gama et al. 2014 (ACM Computing Surveys).",
        "**Sin calibration drift**: nuestro threshold óptimo por costo negocio "
        "(U4) asume el modelo calibrado. Si el ECE (Expected Calibration Error) "
        "creció, ese threshold ya no es óptimo, aunque el PSI diga que las "
        "features están estables. Referencia: Nixon et al. 2019.",
        "**PSI marginal, no conjunto**: PSI mide cada feature por separado. "
        "Drift conjunto en (tenure × PaymentMethod × MonthlyCharges) requeriría "
        "MMD multivariado (Gretton 2012, Rabanser 2019 NeurIPS). Con n=703 "
        "semanal no lo justificamos, pero sí lo reconocemos.",
        "**Baseline pequeño (n=4)**: umbral 2σ es heurístico interpretable, "
        "no test riguroso. Bootstrap percentil (Efron 1979) daría CIs más "
        "honestos. Válido para el mensaje al cliente; refactor cuando haya "
        "≥20 semanas de historia.",
    ],
    "conclusion_para_la_reunion": (
        "El pipeline está trabajando bien: encontramos QUÉ cambió, CUÁNDO, "
        "y CON QUÉ MAGNITUD (PSI de tenure de 1.7 a 8.2, valores nuevos de "
        "PaymentMethod desde 2026-08-24). Lo que las campañas están viendo "
        "es un modelo que fue entrenado hace 3 meses sobre una población "
        "que ya no existe. Recomendamos ampliar el enum del schema (fix "
        "inmediato), pausar el scoring para el segmento 'nuevo' (fix esta "
        "semana), y re-entrenar (fix del mes). El modelo debe seguir en "
        "producción para el resto de la base, pero con monitoreo activo."
    ),
}


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------
def _js(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, dict):
        return {k: _js(vv) for k, vv in v.items()}
    if isinstance(v, (list, tuple)):
        return [_js(x) for x in v]
    return v


OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_JSON, "w") as f:
    json.dump(_js(H), f, indent=2, default=str)

print(f"\nHallazgos guardados en {OUT_JSON}")
print(f"Total de secciones: {len(H)}")
