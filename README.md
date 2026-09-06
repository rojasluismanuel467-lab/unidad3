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
- `u3-g02-nb-20260905.ipynb` — notebook principal (54 celdas, ejecutable end-to-end).
- `parte_b_mitigacion.py` — implementación reproducible de las 3 técnicas individuales.
- `parte_c_combinacion.py` — combinación en cascada, tabla comparativa, correo al PM y Model Card.
- `artifacts/` — pickles y JSON compartidos entre las 3 partes.
- `RESULTADOS.md` — tabla comparativa + respuesta al PM (para consumir sin abrir Jupyter).
- `MODEL_CARD.md` — Model Card estilo Mitchell et al. 2019.
- `PLAN_IMPLEMENTACION.md` — plan dividido en 3 partes A/B/C.

## Ejecutar end-to-end

```bash
# 1. Genera artifacts del modelo base (splits + baseline)
#    -> hacerlo desde el notebook (Sección 4C) o correr solo esa parte
# 2. Ejecuta las 3 técnicas individuales
python parte_b_mitigacion.py
# 3. Ejecuta la combinación + genera tabla, Model Card y respuesta al PM
python parte_c_combinacion.py
```

La exportación a BigQuery al final del notebook está desactivada por defecto (`RUN_GCP_EXPORT = False`).

## Auto-generación de documentación

`RESULTADOS.md` y `MODEL_CARD.md` se re-renderizan automáticamente desde
`artifacts/*.json` mediante un pre-commit hook. Nunca quedan desincronizados
con las métricas actuales.

**Setup una sola vez** (cada miembro del equipo, tras clonar):

```bash
pip install pre-commit
pre-commit install
```

De ahí en adelante, cada `git commit` que toque `artifacts/*.json`,
`parte_c_combinacion.py` o `regenerate_docs.py` re-renderiza los docs.
Si cambian, el commit se aborta y pide agregarlos:

```bash
git add RESULTADOS.md MODEL_CARD.md && git commit
```

**Regenerar manualmente**:

```bash
python regenerate_docs.py
```

El script solo re-renderiza (no reentrena). Si faltan JSONs porque nunca se
corrió las técnicas de mitigación, avisa y sale sin bloquear.
