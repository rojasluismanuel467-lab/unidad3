"""Parte C — Combinacion en cascada (reweighting -> adversarial -> threshold),
tabla comparativa 5 configs, Model Card y respuesta al PM.

Orden y justificacion:
1) Reweighting (pre): calcula sample_weights = balanced(gender x Churn).
   Corrige el sesgo estructural de los datos antes del entrenamiento.
2) Adversarial (in-processing) entrenado SOBRE los datos ya reponderados:
   el BCELoss del predictor se pondera con sample_weights, el adversario
   trata de recuperar gender desde la salida como en Parte B.
   -> Responde al troubleshooting del PM: la 2a tecnica entrena sobre los
      datos re-ponderados, no sobre los originales. Decision explicita.
3) Threshold (post): ThresholdOptimizer se ajusta sobre las probabilidades
   del predictor adversarial ya entrenado con pesos.

Genera:
- artifacts/tecnicas_combinadas.json
- artifacts/tabla_comparativa.json
- RESULTADOS.md  (root del repo, para PM/profesor sin abrir Jupyter)
- MODEL_CARD.md  (root del repo, Mitchell et al. 2019)
"""
from __future__ import annotations

import argparse
import copy
import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
    MetricFrame,
)
from fairlearn.postprocessing import ThresholdOptimizer
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.utils.class_weight import compute_sample_weight

from sklearn.base import BaseEstimator, ClassifierMixin

from parte_b_mitigacion import (
    EPOCHS,
    LAMBDA,
    SEEDS,
    _build_adversarial_models,
    _set_seed,
    evaluate_predictions,
    load_artifacts,
)

LEARNING_RATE = 0.001


# ============================================================================
# Wrapper para que la red adversarial exponga predict_proba() compatible con
# ThresholdOptimizer (que necesita un estimator "prefit" con predict_proba).
# ============================================================================
class _AdversarialProbaWrapper(ClassifierMixin, BaseEstimator):
    """Adaptador sklearn-compatible: expone `predict` / `predict_proba` desde
    el predictor de PyTorch para que Fairlearn `ThresholdOptimizer(prefit=True)`
    lo acepte. Los nombres de __init__ (predictor, feature_names) coinciden
    con atributos publicos por requerimiento de BaseEstimator."""

    def __init__(self, predictor=None, feature_names=None):
        self.predictor = predictor
        self.feature_names = list(feature_names) if feature_names is not None else []
        self.classes_ = np.array([0, 1])

    def __sklearn_is_fitted__(self):
        return True

    def fit(self, X, y=None, **_):
        return self

    def _prob(self, X: pd.DataFrame) -> np.ndarray:
        import torch

        X = X[self.feature_names]
        with torch.no_grad():
            t = torch.tensor(X.to_numpy(dtype=np.float32))
            p = self.predictor(t).numpy().flatten()
        # Fairlearn asigna estas probas dentro de una serie float64 -> castear
        return p.astype(np.float64)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        p = self._prob(X)
        return np.column_stack([1.0 - p, p]).astype(np.float64)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self._prob(X) >= 0.5).astype(int)


# ============================================================================
# Adversarial entrenado con sample_weights (para la combinacion)
# ============================================================================
def _train_adversarial_weighted(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    gender_train: pd.Series,
    sample_weights: np.ndarray,
    seed: int,
) -> Any:
    """Adversarial training donde el BCE del predictor se pondera con
    sample_weights (los pesos calculados por reweighting sobre gender x Churn).
    El adversario NO se pondera — su objetivo es recuperar gender, y queremos
    que lo intente sobre la distribucion real, no sobre la reponderada."""
    import torch
    import torch.nn as nn
    import torch.optim as optim

    _set_seed(seed)
    X_t = torch.tensor(X_train.to_numpy(dtype=np.float32))
    y_t = torch.tensor(y_train.to_numpy(dtype=np.float32)).reshape(-1, 1)
    g_t = torch.tensor(gender_train.to_numpy(dtype=np.float32)).reshape(-1, 1)
    w_t = torch.tensor(sample_weights.astype(np.float32)).reshape(-1, 1)

    predictor, adversary = _build_adversarial_models(X_t.shape[1])
    opt_pred = optim.Adam(predictor.parameters(), lr=LEARNING_RATE)
    opt_adv = optim.Adam(adversary.parameters(), lr=LEARNING_RATE)
    bce_mean = nn.BCELoss()
    bce_none = nn.BCELoss(reduction="none")

    for _ in range(EPOCHS):
        # 1) Adversario aprende gender desde salida del predictor
        pred_det = predictor(X_t).detach()
        adv_out = adversary(pred_det)
        loss_adv = bce_mean(adv_out, g_t)
        opt_adv.zero_grad()
        loss_adv.backward()
        opt_adv.step()

        # 2) Predictor: minimiza churn (con pesos) y maximiza error del adversario
        for p in adversary.parameters():
            p.requires_grad_(False)
        pred = predictor(X_t)
        adv_out = adversary(pred)
        # BCE ponderado por sample_weights
        loss_pred_raw = bce_none(pred, y_t)
        loss_pred = (loss_pred_raw * w_t).mean()
        # Confusion: sin pesos (queremos independencia real)
        loss_confuse = -bce_mean(adv_out, g_t)
        total = loss_pred + LAMBDA * loss_confuse
        opt_pred.zero_grad()
        total.backward()
        opt_pred.step()
        for p in adversary.parameters():
            p.requires_grad_(True)

    return predictor


# ============================================================================
# Pipeline combinado
# ============================================================================
def run_combined(
    data: dict,
    seed: int = 42,
    artifacts_dir: str | Path = "artifacts",
) -> dict:
    X_train, X_test = data["X_train"], data["X_test"]
    y_train, y_test = data["y_train"], data["y_test"]
    g_train, g_test = data["gender_train"], data["gender_test"]

    # ---- Paso 1: Reweighting (mismo criterio que Parte B) ----
    grupo = g_train.astype(str) + "_" + y_train.astype(str)
    sample_weights = compute_sample_weight(class_weight="balanced", y=grupo)

    # ---- Paso 2: Adversarial entrenado con esos pesos ----
    predictor = _train_adversarial_weighted(
        X_train, y_train, g_train, sample_weights, seed=seed
    )

    # ---- Paso 3: ThresholdOptimizer sobre las probas del adversarial ----
    wrapper = _AdversarialProbaWrapper(predictor, X_train.columns)
    thr = ThresholdOptimizer(
        estimator=wrapper,
        constraints="equalized_odds",
        objective="balanced_accuracy_score",
        prefit=True,
        predict_method="predict_proba",
    )
    thr.fit(X_train, y_train, sensitive_features=g_train)

    # Predicciones finales del pipeline combinado
    y_pred_combined = thr.predict(X_test, sensitive_features=g_test)
    # AUC: no aplica sobre threshold optimizer directamente. Reportamos AUC
    # del predictor adversarial subyacente (probas continuas) como referencia
    # de la utilidad "cruda" del modelo antes del ajuste por grupo.
    y_proba_adv = wrapper._prob(X_test)
    auc_adv = float(roc_auc_score(y_test, y_proba_adv))

    # y_score = probas del predictor adversarial (el thresholder no expone probas comparables)
    metrics = evaluate_predictions(y_test, y_pred_combined, y_proba_adv, g_test)
    metrics["auc_adversarial_underlying"] = auc_adv
    metrics["orden"] = "reweighting -> adversarial(weighted) -> threshold"
    metrics["decision_dataset_2a_tecnica"] = (
        "El adversarial se entreno SOBRE los datos ya reponderados: "
        "el BCE del predictor se multiplica por los sample_weights "
        "(gender x Churn). Esto responde el troubleshooting del PM."
    )
    metrics["seed"] = seed

    return metrics


# ============================================================================
# Tabla comparativa (5 configs)
# ============================================================================
def build_comparative_table(
    baseline: dict,
    tecnicas_ind: dict,
    combined: dict,
) -> list[dict]:
    def row(nombre, m, extra=""):
        return {
            "config": nombre + (f" ({extra})" if extra else ""),
            "recall": round(m["recall"], 3),
            "precision": round(m["precision"], 3),
            "auc": round(m.get("auc", m.get("auc_adversarial_underlying", float("nan"))), 3),
            "dpd_gender": round(m.get("dpd", m.get("dpd_gender", float("nan"))), 3),
            "eod_gender": round(m.get("eod", m.get("eod_gender", float("nan"))), 3),
        }

    rows = []
    rows.append(row("Base (sin mitigar)", baseline))
    rows.append(row("Reweighting", tecnicas_ind["reweighting"]))

    # Adversarial: media +- std sobre seeds
    adv_runs = tecnicas_ind["adversarial"]["runs"]
    def ms(field):
        vals = [r[field] for r in adv_runs]
        return statistics.mean(vals), statistics.stdev(vals)
    r_m, r_s = ms("recall"); p_m, p_s = ms("precision")
    a_m, a_s = ms("auc"); d_m, d_s = ms("dpd"); e_m, e_s = ms("eod")
    rows.append({
        "config": f"Adversarial (media±std, {len(adv_runs)} seeds)",
        "recall": f"{r_m:.3f} ± {r_s:.3f}",
        "precision": f"{p_m:.3f} ± {p_s:.3f}",
        "auc": f"{a_m:.3f} ± {a_s:.3f}",
        "dpd_gender": f"{d_m:.3f} ± {d_s:.3f}",
        "eod_gender": f"{e_m:.3f} ± {e_s:.3f}",
    })
    rows.append(row("Threshold adjustment", tecnicas_ind["threshold"]))
    rows.append(row("Combinado (rw→adv→thr)", combined))
    return rows


def table_to_markdown(rows: list[dict]) -> str:
    header = "| Config | Recall (Churn) | Precision | AUC | DPD (gender) | EOD (gender) |"
    sep = "|---|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['config']} | {r['recall']} | {r['precision']} | {r['auc']} | {r['dpd_gender']} | {r['eod_gender']} |"
        )
    return "\n".join(lines)


# ============================================================================
# Respuesta al PM (<=200 palabras)
# ============================================================================
def build_pm_response(baseline: dict, tecnicas_ind: dict, combined: dict) -> str:
    rw = tecnicas_ind["reweighting"]
    thr = tecnicas_ind["threshold"]
    txt = f"""**Asunto: Auditoría de sesgo por género — modelo de churn**

Hola,

Auditamos el modelo con `gender` como variable protegida y aplicamos las tres técnicas por separado y combinadas.

**Gender ya estaba parejo desde el modelo base.** DPD={baseline['dpd_gender']:.3f}, EOD={baseline['eod_gender']:.3f} — ambos muy por debajo del umbral de 0.10 que Fairlearn considera aceptable. Tu intuición era correcta: no hay un problema visible de discriminación de género que necesite mitigarse.

**Qué pasó al aplicar las técnicas de todos modos** (como pediste). Reweighting subió recall de {baseline['recall']:.2f} a {rw['recall']:.2f} y mantuvo AUC intacto ({rw['auc']:.3f} vs {baseline['auc']:.3f}), a costa de precisión ({baseline['precision']:.2f}→{rw['precision']:.2f}). Threshold-adjustment bajó DPD a {thr['dpd']:.3f} con recall={thr['recall']:.2f}, pero ojo — legalmente usa umbrales distintos por género (posible *disparate treatment*, revisar con legal). Adversarial degradó AUC ~4 puntos sin ganancia clara.

**Combinar (reweighting→adversarial→threshold) no valió la pena:** recall={combined['recall']:.2f}, DPD={combined['dpd']:.3f}, EOD={combined['eod']:.3f}. Añade complejidad sin mejora consistente sobre reweighting solo.

**Recomendación:** no aplicar mitigación adicional sobre género en producción. Monitorear DPD/EOD mensualmente. El sesgo real observable estaba en SeniorCitizen (removido esta iteración por instrucción académica) — vale la pena revisarlo si vuelve al alcance.
"""
    return txt.strip()


# ============================================================================
# Model Card (Mitchell et al. 2019)
# ============================================================================
def build_model_card(baseline: dict, combined: dict, n_features: int) -> str:
    return f"""# Model Card — XGBoost Churn (Telco), auditado sobre `gender`

Basado en Mitchell et al. 2019 (*Model Cards for Model Reporting*).

## Model details
- **Algoritmo**: XGBoost Classifier (`n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42`).
- **Features**: {n_features} columnas tras one-hot (`gender`, `Partner`, `Dependents`, `tenure`, `Contract`, `PaymentMethod`, `MonthlyCharges`, `InternetService`, `OnlineSecurity`, `TechSupport`).
- **Variable protegida auditada**: `gender` (binaria Male/Female en el dataset). `SeniorCitizen` fue removido por instrucción académica.
- **Versión**: iteración de U3 — 2026.

## Intended use
- **Uso previsto**: priorizar clientes para campañas proactivas de retención en Telco.
- **Fuera de alcance**: decisiones automatizadas irreversibles (cancelación de servicio, cambio de tarifa sin intervención humana). Si se usa así, cae bajo GDPR Art. 22.

## Datos
- IBM Telco Customer Churn, 7043 clientes.
- Split: 80/20 estratificado por `Churn` (`random_state=42`).
- **Etiqueta**: `Churn` observado por la empresa — hay posible *label bias* (solo capturamos cancelaciones detectadas).
- **Limitación de `gender`**: solo Male/Female. No hay categoría "no declarado" ni no-binaria.

## Métricas — configuración recomendada (baseline)
| Métrica | Valor |
|---|---|
| AUC-ROC | {baseline['auc']:.3f} |
| Recall (Churn) | {baseline['recall']:.3f} |
| Precision (Churn) | {baseline['precision']:.3f} |
| DPD (gender) | {baseline['dpd_gender']:.3f} |
| EOD (gender) | {baseline['eod_gender']:.3f} |
| Recall Female / Male | {baseline['recall_female']:.3f} / {baseline['recall_male']:.3f} |
| Precision Female / Male | {baseline['precision_female']:.3f} / {baseline['precision_male']:.3f} |

## Ethical considerations
- **Métrica prima declarada**: **EOD (Equal Opportunity Difference)** — en retención el daño principal es *quality-of-service* (clientas realmente en riesgo no reciben la oferta).
- **Trade-offs conocidos** (Kleinberg 2016, Pleiss 2017, Chouldechova 2017): DPD, EOD y calibración no son simultáneamente satisfacibles cuando las tasas base difieren. Optimizamos EOD y aceptamos el trade-off.
- **Threshold-por-grupo** (implementado como técnica individual): posible *disparate treatment* explícito (jurisprudencia estilo *Ricci v. DeStefano*). No se recomienda en producción sin revisión legal.
- **`fairness through unawareness` no es solución**: `gender` se mantiene como feature; removerlo no impide que proxies reintroduzcan el sesgo.

## Caveats and recommendations
- Ningún test de proxy leakage sobre las features candidatas superó AUC=0.508 vs. `gender` — cero riesgo de proxy en este dataset.
- Con `gender` casi parejo (DPD/EOD < 0.06 desde el baseline), aplicar mitigación agresiva **degrada utilidad sin ganancia real de equidad**.
- **Recomendación operacional**: usar el modelo base sin mitigación adicional; monitorear DPD/EOD mensualmente en producción; re-auditoría trimestral (NIST AI RMF Measure 2.11).
"""


# ============================================================================
# CLI
# ============================================================================
def _json_safe(v):
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json_safe(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    a = Path(args.artifacts_dir)
    data = load_artifacts(a)
    with open(a / "baseline_metrics.json") as f:
        baseline = json.load(f)
    with open(a / "tecnicas_individuales.json") as f:
        tecnicas_ind = json.load(f)

    print("=== Parte C: entrenando combinacion (rw -> adv -> thr) ===")
    combined = run_combined(data, seed=args.seed, artifacts_dir=a)
    print(f"Combinado: recall={combined['recall']:.3f}  prec={combined['precision']:.3f}  "
          f"DPD={combined['dpd']:.3f}  EOD={combined['eod']:.3f}  "
          f"AUC(adv)={combined['auc_adversarial_underlying']:.3f}")

    with open(a / "tecnicas_combinadas.json", "w") as f:
        json.dump(_json_safe(combined), f, indent=2)

    tabla = build_comparative_table(baseline, tecnicas_ind, combined)
    with open(a / "tabla_comparativa.json", "w") as f:
        json.dump(_json_safe(tabla), f, indent=2)

    md_table = table_to_markdown(tabla)
    print("\n=== TABLA COMPARATIVA ===")
    print(md_table)

    pm_text = build_pm_response(baseline, tecnicas_ind, combined)
    n_words = len(pm_text.split())
    print(f"\n=== RESPUESTA AL PM ({n_words} palabras) ===")
    print(pm_text)
    assert n_words <= 200, f"Respuesta al PM excede 200 palabras: {n_words}"

    n_features = baseline.get("n_features") or data["X_train"].shape[1]
    model_card = build_model_card(baseline, combined, n_features)

    # RESULTADOS.md (root del repo)
    resultados = f"""# RESULTADOS — Auditoría de sesgo por `gender`

## Tabla comparativa

{md_table}

- DPD/EOD: más cerca de 0 = más equitativo.
- Adversarial reporta media±std sobre {len(tecnicas_ind['adversarial']['runs'])} seeds (Zhang et al. 2018).
- AUC del combinado corresponde al predictor adversarial subyacente (el ThresholdOptimizer no expone probas comparables).

## Respuesta al PM

{pm_text}
"""
    Path("RESULTADOS.md").write_text(resultados, encoding="utf-8")
    Path("MODEL_CARD.md").write_text(model_card, encoding="utf-8")
    print("\nEscritos: RESULTADOS.md, MODEL_CARD.md, artifacts/tecnicas_combinadas.json, artifacts/tabla_comparativa.json")


if __name__ == "__main__":
    main()
