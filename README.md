# Unidad 3 — IA en la Nube

Laboratorio de análisis de sesgo en un modelo de churn (Telco), con variable protegida **gender**
(adicional a `SeniorCitizen`, no la reemplaza).

## Alcance
- Ampliación justificada de features del dataset crudo.
- Reentrenamiento de XGBoost.
- Aplicación de técnicas de mitigación de sesgo: **reweighting**, **adversarial training**,
  **threshold adjustment**, y su combinación.
- Tabla comparativa de métricas (recall, precision, AUC, DPD, EOD) para las 5 configuraciones.
- Respuesta al PM con evidencia numérica.

## Archivos
- `u3_telco_churn_bias_analysis.ipynb` — notebook principal.
