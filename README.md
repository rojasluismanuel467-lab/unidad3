# Unidad 3 — IA en la Nube

Laboratorio de análisis de sesgo en un modelo de churn (Telco), con **`gender` como única variable protegida**.

> Nota: por instrucción del profesor, `SeniorCitizen` fue removido por completo del modelo (ni como protegida ni como feature).

## Alcance
- Ampliación justificada de features del dataset crudo.
- Reentrenamiento de XGBoost.
- Aplicación de técnicas de mitigación de sesgo: **reweighting**, **adversarial training**,
  **threshold adjustment**, y su combinación.
- Tabla comparativa de métricas (recall, precision, AUC, DPD, EOD) para las 5 configuraciones.
- Respuesta al PM con evidencia numérica.

## Archivos
- `u3_telco_churn_bias_analysis.ipynb` — notebook principal.
- `parte_b_mitigacion.py` — implementación reproducible de las técnicas de la Parte B.
- `artifacts/` — datos/modelo de la Parte A y salidas serializadas para la Parte C.

## Ejecutar la Parte B

Desde este directorio, usando el mismo entorno de Python que generó los
artefactos de la Parte A:

```bash
python parte_b_mitigacion.py
```

La ejecución aplica reweighting, adversarial training con cinco semillas y
threshold adjustment, y guarda los resultados en `artifacts/`. La exportación
a BigQuery del notebook está desactivada por defecto.
