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
- `u3_telco_churn_bias_analysis.ipynb` — notebook principal (54 celdas, ejecutable end-to-end).
- `parte_b_mitigacion.py` — implementación reproducible de las 3 técnicas individuales (Parte B).
- `parte_c_combinacion.py` — combinación en cascada + tabla comparativa + PM response + Model Card (Parte C).
- `artifacts/` — pickles y JSON compartidos entre las 3 partes.
- `RESULTADOS.md` — tabla comparativa + respuesta al PM (para consumir sin abrir Jupyter).
- `MODEL_CARD.md` — Model Card estilo Mitchell et al. 2019.
- `PLAN_IMPLEMENTACION.md` — plan dividido en 3 partes A/B/C.

## Ejecutar end-to-end

```bash
# 1. Genera artifacts de Parte A (splits + baseline)
#    -> hacerlo desde el notebook (Sección 4C) o correr solo esa parte
# 2. Ejecuta las 3 técnicas individuales
python parte_b_mitigacion.py
# 3. Ejecuta la combinación + genera tabla, Model Card y respuesta al PM
python parte_c_combinacion.py
```

La exportación a BigQuery al final del notebook está desactivada por defecto (`RUN_GCP_EXPORT = False`).
