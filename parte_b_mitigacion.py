"""Implementación reproducible de la Parte B de la Unidad 3.

El módulo consume únicamente los artefactos de la Parte A y escribe los
artefactos que necesita la Parte C. No contiene ninguna operación de GCP.
"""

from __future__ import annotations

import argparse
import copy
import json
import pickle
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)
from fairlearn.postprocessing import ThresholdOptimizer
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.utils.class_weight import compute_sample_weight


SEEDS = (42, 7, 123, 2024, 99)
LAMBDA = 1.0
EPOCHS = 50
LEARNING_RATE = 0.001


def _set_seed(seed: int) -> None:
    """Fija todas las semillas usadas por esta implementación."""

    random.seed(seed)
    np.random.seed(seed)

    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _as_aligned_series(values: Any, index: pd.Index, name: str) -> pd.Series:
    """Convierte una serie/array al índice del split sin reordenar sus filas."""

    return pd.Series(np.asarray(values), index=index, name=name).astype(int)


def load_artifacts(artifacts_dir: str | Path = "artifacts") -> dict[str, Any]:
    """Carga y valida el contrato producido por la Parte A."""

    directory = Path(artifacts_dir)
    required = (
        "X_train.pkl",
        "X_test.pkl",
        "y_train.pkl",
        "y_test.pkl",
        "gender_train.pkl",
        "gender_test.pkl",
        "modelo_base.pkl",
        "baseline_metrics.json",
    )
    missing = [name for name in required if not (directory / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Faltan artefactos de Parte A: " + ", ".join(missing)
        )

    try:
        X_train = pd.read_pickle(directory / "X_train.pkl")
        X_test = pd.read_pickle(directory / "X_test.pkl")
        y_train_raw = pd.read_pickle(directory / "y_train.pkl")
        y_test_raw = pd.read_pickle(directory / "y_test.pkl")
        gender_train_raw = pd.read_pickle(directory / "gender_train.pkl")
        gender_test_raw = pd.read_pickle(directory / "gender_test.pkl")
        with (directory / "modelo_base.pkl").open("rb") as handle:
            modelo_base = pickle.load(handle)
    except (ImportError, ModuleNotFoundError, TypeError, AttributeError) as exc:
        raise RuntimeError(
            "No se pudieron cargar los pickles. Ejecuta esta module en el "
            "mismo entorno de Python/pandas/numpy que generó los artefactos."
        ) from exc

    y_train = _as_aligned_series(y_train_raw, X_train.index, "Churn")
    y_test = _as_aligned_series(y_test_raw, X_test.index, "Churn")
    gender_train = _as_aligned_series(
        gender_train_raw, X_train.index, "gender_Male"
    )
    gender_test = _as_aligned_series(
        gender_test_raw, X_test.index, "gender_Male"
    )

    if not X_train.index.equals(y_train.index) or not X_train.index.equals(
        gender_train.index
    ):
        raise ValueError("El split de entrenamiento no está alineado.")
    if not X_test.index.equals(y_test.index) or not X_test.index.equals(
        gender_test.index
    ):
        raise ValueError("El split de prueba no está alineado.")
    if not X_train.columns.equals(X_test.columns):
        raise ValueError("X_train y X_test no tienen las mismas columnas.")
    if set(gender_train.unique()) != {0, 1} or set(gender_test.unique()) != {
        0,
        1,
    }:
        raise ValueError("gender debe estar codificado como 0/1.")

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "gender_train": gender_train,
        "gender_test": gender_test,
        "modelo_base": modelo_base,
    }


def _xgb_model(seed: int = 42) -> xgb.XGBClassifier:
    """Crea el XGBoost con los hiperparámetros fijados por el plan."""

    return xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=seed,
        eval_metric="logloss",
        n_jobs=1,
    )


def evaluate_predictions(
    y_true: pd.Series,
    y_pred: np.ndarray | pd.Series,
    y_score: np.ndarray | pd.Series | None,
    sensitive_features: pd.Series,
) -> dict[str, Any]:
    """Calcula utilidad, fairness y métricas desagregadas por género."""

    y_true = pd.Series(np.asarray(y_true)).reset_index(drop=True)
    y_pred = pd.Series(np.asarray(y_pred)).reset_index(drop=True)
    sensitive = pd.Series(np.asarray(sensitive_features)).reset_index(drop=True)

    metrics: dict[str, Any] = {
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "dpd": float(
            demographic_parity_difference(
                y_true, y_pred, sensitive_features=sensitive
            )
        ),
        "eod": float(
            equalized_odds_difference(
                y_true, y_pred, sensitive_features=sensitive
            )
        ),
    }
    if y_score is not None:
        metrics["auc"] = float(roc_auc_score(y_true, np.asarray(y_score)))
    else:
        metrics["auc"] = None

    for value, label in ((0, "female"), (1, "male")):
        mask = sensitive == value
        metrics[f"recall_{label}"] = float(
            recall_score(y_true[mask], y_pred[mask], zero_division=0)
        )
        metrics[f"precision_{label}"] = float(
            precision_score(y_true[mask], y_pred[mask], zero_division=0)
        )
    return metrics


def run_reweighting(
    data: dict[str, Any], artifacts_dir: str | Path = "artifacts", verbose: bool = True
) -> tuple[xgb.XGBClassifier, dict[str, Any], pd.DataFrame]:
    """Entrena reweighting usando las cuatro celdas gender x Churn."""

    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]
    gender_train = data["gender_train"]
    gender_test = data["gender_test"]

    # El peso se calcula sobre gender x Churn, no únicamente sobre Churn.
    intersection = gender_train.astype(str) + "_" + y_train.astype(str)
    sample_weights = compute_sample_weight(
        class_weight="balanced", y=intersection
    )
    weight_table = (
        pd.DataFrame({"grupo": intersection, "peso": sample_weights})
        .groupby("grupo", as_index=False)
        .agg(peso=("peso", "first"), n=("peso", "size"))
        .sort_values("grupo")
    )
    if len(weight_table) != 4 or weight_table["peso"].nunique() != 4:
        raise ValueError(
            "Reweighting no produjo cuatro pesos distintos para gender x Churn."
        )

    modelo_rw = _xgb_model(seed=42)
    modelo_rw.fit(X_train, y_train, sample_weight=sample_weights)
    y_pred = modelo_rw.predict(X_test)
    y_proba = modelo_rw.predict_proba(X_test)[:, 1]
    metrics = evaluate_predictions(y_test, y_pred, y_proba, gender_test)
    metrics["weights_by_group"] = [
        {"grupo": str(row.grupo), "peso": float(row.peso), "n": int(row.n)}
        for row in weight_table.itertuples(index=False)
    ]

    output_dir = Path(artifacts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "modelo_reweighting.pkl").open("wb") as handle:
        pickle.dump(modelo_rw, handle)

    if verbose:
        print("=== REWEIGHTING: pesos por gender x Churn ===")
        print(weight_table.to_string(index=False))
        print("=== REWEIGHTING: métricas ===")
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return modelo_rw, metrics, weight_table


def _threshold_value(operation: Any) -> float | None:
    """Obtiene el umbral de una ThresholdOperation entre versiones de Fairlearn."""

    for attribute in ("threshold", "_threshold"):
        value = getattr(operation, attribute, None)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def extract_thresholds(threshold_model: ThresholdOptimizer) -> dict[str, Any]:
    """Extrae las reglas/umbrales aprendidos por grupo para hacerlos auditables."""

    thresholder = getattr(threshold_model, "interpolated_thresholder_", None)
    interpolation = getattr(thresholder, "interpolation_dict", {}) or {}
    result: dict[str, Any] = {}
    for group, rule in interpolation.items():
        operations: list[dict[str, Any]] = []
        if isinstance(rule, dict):
            for name in ("operation0", "operation1"):
                operation = rule.get(name)
                if operation is not None:
                    operations.append(
                        {
                            "operation": name,
                            "threshold": _threshold_value(operation),
                            "description": repr(operation),
                        }
                    )
        result[str(group)] = {
            "p0": float(rule["p0"]) if isinstance(rule, dict) and "p0" in rule else None,
            "p1": float(rule["p1"]) if isinstance(rule, dict) and "p1" in rule else None,
            "operations": operations,
            "raw": repr(rule),
        }
    return result


def _predict_threshold_compatible(
    threshold_model: ThresholdOptimizer,
    X_test: pd.DataFrame,
    sensitive_features: pd.Series,
    random_state: int = 42,
) -> np.ndarray:
    """Predice con Fairlearn y aplica un fallback para pandas 3.x.

    Fairlearn 0.14 construye internamente una Series y, en pandas 3.x, la
    asignación de las probabilidades interpoladas puede fallar por upcasting.
    El fallback usa las mismas operaciones y reglas ya aprendidas por
    ``ThresholdOptimizer``; no cambia el criterio ni vuelve a entrenar nada.
    """

    try:
        return np.asarray(
            threshold_model.predict(
                X_test,
                sensitive_features=np.asarray(sensitive_features),
                random_state=random_state,
            ),
            dtype=int,
        )
    except TypeError as exc:
        if "dtype" not in str(exc) and "upcast" not in str(exc):
            raise

    interpolated_thresholder = threshold_model.interpolated_thresholder_
    base_scores = np.asarray(
        threshold_model.estimator_.predict_proba(X_test)[:, 1], dtype=float
    )
    sensitive = np.asarray(sensitive_features)
    positive_probs = np.zeros(len(base_scores), dtype=float)

    for group, rule in interpolated_thresholder.interpolation_dict.items():
        get = rule.get if isinstance(rule, dict) else lambda key: getattr(rule, key)
        interpolated = (
            float(get("p0")) * get("operation0")(base_scores)
            + float(get("p1")) * get("operation1")(base_scores)
        )
        if "p_ignore" in rule:
            interpolated = float(get("p_ignore")) * float(
                get("prediction_constant")
            ) + (1 - float(get("p_ignore"))) * interpolated
        mask = sensitive == group
        positive_probs[mask] = np.asarray(interpolated)[mask]

    rng = np.random.RandomState(random_state)
    return (positive_probs >= rng.rand(len(positive_probs))).astype(int)


def run_threshold_adjustment(
    data: dict[str, Any], artifacts_dir: str | Path = "artifacts", verbose: bool = True
) -> tuple[ThresholdOptimizer, dict[str, Any]]:
    """Ajusta umbrales por grupo sobre el modelo base ya entrenado."""

    modelo_base = data["modelo_base"]
    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]
    gender_train = data["gender_train"]
    gender_test = data["gender_test"]

    threshold_model = ThresholdOptimizer(
        estimator=modelo_base,
        constraints="equalized_odds",
        objective="balanced_accuracy_score",
        prefit=True,
        predict_method="predict_proba",
    )
    threshold_model.fit(
        X_train, y_train, sensitive_features=gender_train.to_numpy()
    )
    y_pred = _predict_threshold_compatible(
        threshold_model, X_test, gender_test, random_state=42
    )
    # ThresholdOptimizer no entrega probabilidades ROC comparables; por contrato,
    # usamos el AUC de las probabilidades del modelo base.
    y_base_proba = modelo_base.predict_proba(X_test)[:, 1]
    metrics = evaluate_predictions(y_test, y_pred, y_base_proba, gender_test)
    metrics["auc_note"] = "AUC de las probabilidades del modelo base"
    metrics["thresholds_by_group"] = extract_thresholds(threshold_model)

    output_dir = Path(artifacts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "threshold_optimizer.pkl").open("wb") as handle:
        pickle.dump(threshold_model, handle)

    if verbose:
        print("=== THRESHOLD ADJUSTMENT: reglas por grupo ===")
        for group, details in metrics["thresholds_by_group"].items():
            print(f"Grupo {group}: {details}")
        print("=== THRESHOLD ADJUSTMENT: métricas ===")
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return threshold_model, metrics


def _build_adversarial_models(n_features: int):
    import torch.nn as nn

    class Predictor(nn.Module):
        def __init__(self, features: int):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(features, 32),
                nn.ReLU(),
                nn.Linear(32, 16),
                nn.ReLU(),
                nn.Linear(16, 1),
                nn.Sigmoid(),
            )

        def forward(self, x):
            return self.net(x)

    class Adversario(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(1, 8),
                nn.ReLU(),
                nn.Linear(8, 1),
                nn.Sigmoid(),
            )

        def forward(self, prediction):
            return self.net(prediction)

    return Predictor(n_features), Adversario()


def _train_adversarial_once(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    gender_train: pd.Series,
    seed: int,
) -> tuple[Any, Any]:
    import torch
    import torch.nn as nn
    import torch.optim as optim

    _set_seed(seed)
    X_train_t = torch.tensor(X_train.to_numpy(dtype=np.float32))
    y_train_t = torch.tensor(
        y_train.to_numpy(dtype=np.float32)
    ).reshape(-1, 1)
    # La variable sensible de la red es gender_Male, no SeniorCitizen.
    gender_train_t = torch.tensor(
        gender_train.to_numpy(dtype=np.float32)
    ).reshape(-1, 1)

    predictor, adversary = _build_adversarial_models(X_train_t.shape[1])
    opt_pred = optim.Adam(predictor.parameters(), lr=LEARNING_RATE)
    opt_adv = optim.Adam(adversary.parameters(), lr=LEARNING_RATE)
    criterion = nn.BCELoss()

    for _epoch in range(EPOCHS):
        # Paso 1: el adversario aprende a predecir gender desde la salida.
        prediction_detached = predictor(X_train_t).detach()
        adversary_output = adversary(prediction_detached)
        adversary_loss = criterion(adversary_output, gender_train_t)
        opt_adv.zero_grad()
        adversary_loss.backward()
        opt_adv.step()

        # Paso 2: el predictor minimiza churn y maximiza el error del adversario.
        for parameter in adversary.parameters():
            parameter.requires_grad_(False)
        prediction = predictor(X_train_t)
        adversary_output = adversary(prediction)
        prediction_loss = criterion(prediction, y_train_t)
        confuse_loss = -criterion(adversary_output, gender_train_t)
        total_loss = prediction_loss + LAMBDA * confuse_loss
        opt_pred.zero_grad()
        total_loss.backward()
        opt_pred.step()
        for parameter in adversary.parameters():
            parameter.requires_grad_(True)

    return predictor, adversary


def run_adversarial_multiseed(
    data: dict[str, Any], artifacts_dir: str | Path = "artifacts", verbose: bool = True
) -> dict[str, Any]:
    """Entrena cinco semillas, elige la menor EOD y reporta media +/- std."""

    import torch

    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]
    gender_train = data["gender_train"]
    gender_test = data["gender_test"]
    X_test_t = torch.tensor(X_test.to_numpy(dtype=np.float32))

    runs: list[dict[str, Any]] = []
    trained_models: dict[int, tuple[Any, Any]] = {}
    for seed in SEEDS:
        predictor, adversary = _train_adversarial_once(
            X_train, y_train, gender_train, seed
        )
        predictor.eval()
        with torch.no_grad():
            y_proba = predictor(X_test_t).cpu().numpy().ravel()
        y_pred = (y_proba >= 0.5).astype(int)
        metrics = evaluate_predictions(y_test, y_pred, y_proba, gender_test)
        run = {"seed": int(seed), **metrics}
        runs.append(run)
        trained_models[seed] = (predictor, adversary)
        if verbose:
            print(
                f"Seed {seed}: AUC={metrics['auc']:.4f}, "
                f"recall={metrics['recall']:.4f}, EOD={metrics['eod']:.4f}"
            )

    best_run = min(runs, key=lambda run: run["eod"])
    best_predictor, best_adversary = trained_models[int(best_run["seed"])]
    output_dir = Path(artifacts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "predictor_state_dict": copy.deepcopy(best_predictor.state_dict()),
            "adversary_state_dict": copy.deepcopy(best_adversary.state_dict()),
            "best_seed": int(best_run["seed"]),
            "n_features": int(X_train.shape[1]),
            "feature_names": list(X_train.columns),
            "hyperparameters": {
                "lambda": LAMBDA,
                "epochs": EPOCHS,
                "learning_rate": LEARNING_RATE,
                "seeds": list(SEEDS),
            },
        },
        output_dir / "modelo_adversarial_bestseed.pt",
    )

    summary: dict[str, Any] = {
        "seeds": list(SEEDS),
        "runs": runs,
        "best_seed": int(best_run["seed"]),
        "best": best_run,
    }
    for metric in ("recall", "precision", "auc", "dpd", "eod"):
        values = np.array([run[metric] for run in runs], dtype=float)
        summary[f"{metric}_mean"] = float(values.mean())
        summary[f"{metric}_std"] = float(values.std(ddof=1))

    if verbose:
        print(
            "Adversarial summary: "
            + json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "best_seed",
                        "auc_mean",
                        "auc_std",
                        "recall_mean",
                        "recall_std",
                        "eod_mean",
                        "eod_std",
                    )
                },
                indent=2,
            )
        )
    return summary


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def save_part_b_results(
    reweighting_metrics: dict[str, Any],
    adversarial_metrics: dict[str, Any],
    threshold_metrics: dict[str, Any],
    artifacts_dir: str | Path = "artifacts",
    verbose: bool = True,
) -> dict[str, Any]:
    """Guarda el JSON que consume la Parte C sin volver a entrenar modelos."""

    output = {
        "reweighting": reweighting_metrics,
        "adversarial": adversarial_metrics,
        "threshold": threshold_metrics,
        "metadata": {
            "protected_attribute": "gender",
            "gender_encoding": {"0": "Female", "1": "Male"},
            "adversarial_seeds": list(SEEDS),
            "lambda": LAMBDA,
            "epochs": EPOCHS,
            "learning_rate": LEARNING_RATE,
        },
    }
    output_path = Path(artifacts_dir) / "tecnicas_individuales.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(output), handle, indent=2, ensure_ascii=False)

    if verbose:
        print(f"Artefactos de Parte B guardados en {output_path}")
    return output


def run_part_b(
    artifacts_dir: str | Path = "artifacts", verbose: bool = True
) -> dict[str, Any]:
    """Ejecuta las tres técnicas y persiste el contrato completo para C."""

    data = load_artifacts(artifacts_dir)
    _, reweighting_metrics, _ = run_reweighting(
        data, artifacts_dir=artifacts_dir, verbose=verbose
    )
    adversarial_metrics = run_adversarial_multiseed(
        data, artifacts_dir=artifacts_dir, verbose=verbose
    )
    _, threshold_metrics = run_threshold_adjustment(
        data, artifacts_dir=artifacts_dir, verbose=verbose
    )

    return save_part_b_results(
        reweighting_metrics,
        adversarial_metrics,
        threshold_metrics,
        artifacts_dir=artifacts_dir,
        verbose=verbose,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts-dir", default="artifacts", help="Directorio de artefactos"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="No imprimir métricas durante la ejecución"
    )
    args = parser.parse_args()
    run_part_b(args.artifacts_dir, verbose=not args.quiet)


if __name__ == "__main__":
    main()
