# Repo del curso — Grupo 2

Contiene los entregables de las Unidades 3, 4 y 5 del curso *Computación en la Nube para IA* (Profesora Diana Jaimes). Reutiliza los mismos artifacts entre unidades.

**Integrantes**: Gabriel Ernesto Escobar A00399291 · David Artunduaga Penagos A00396342 · Luis Manuel Rojas A00399289

## Unidades

- **U3 — Auditoría de sesgo** (`u3-g02-nb-20260905.ipynb` + `parte_b_mitigacion.py` + `parte_c_combinacion.py`): EDA, selección de features, mitigación por reweighting/adversarial/threshold, tabla comparativa, respuesta al PM.
- **U4 — Selección de arquitectura ganadora** (`u4-g02-nb-20260914.ipynb`): 4-way leaderboard XGB/LGBM/LogReg/MLP con Optuna optimizando business_cost, calibración isotonic, threshold tuning, y registro en Model Registry.
- **U5 — Servicio de inferencia** (`service/`): FastAPI + Docker + Cloud Run. Ver `GUIA_DESPLIEGUE_U5.md` para el paso a paso de deploy.

Laboratorio de análisis de sesgo en un modelo de churn (Telco), con **`gender` como única variable protegida**.

> Nota: por instrucción del profesor, `SeniorCitizen` fue removido por completo del modelo (ni como protegida ni como feature).

## Las 5 garantías del servicio (U5) — mapeadas a nuestro código

Basado en la presentación teórica de U5 (Diana Jaimes), el servicio de producción debe garantizar 5 cosas. Aquí cómo las cumplimos:

| # | Garantía | Cómo la cumplimos |
|---|---|---|
| 1 | **Datos validados** | `service/app/schemas.py` con Enums cerrados (Contract, PaymentMethod, InternetService, YesNoNoInternet, Gender) + `Field(ge=..., le=...)` en numéricos + reglas de coherencia (`_validar_coherencia_negocio` en `main.py`). Input mal escrito → **422** con el campo exacto, no un 200 silencioso. |
| 2 | **Transformación correcta** | `_preparar_features()` en `main.py` replica el mismo `pd.get_dummies(drop_first=True)` del notebook U3/U4. El listado `features` viene serializado en el bundle → si cambia el entrenamiento, cambia el bundle, y el servicio se alinea automáticamente. |
| 3 | **Mismo entorno del entrenamiento** | `service/Dockerfile` con `python:3.11-slim` + `service/requirements.txt` con versiones pinneadas (fastapi, uvicorn, pydantic, xgboost, lightgbm, scikit-learn, joblib, google-cloud-storage). |
| 4 | **Servicio seguro y con costo controlado** | Deploy con `--no-allow-unauthenticated` + service account dedicada (por ejemplo, `u5-g02-sa-20260917`) con solo `roles/storage.objectViewer` + `--min-instances=0` (paga solo por segundo activo) + `--max-instances=1` (techo de costo). |
| 5 | **Cada predicción deja rastro** | Logging estructurado desde el diseño (no como parche): `StructuredFormatter` en `main.py` con `json_fields` — cada request emite `predict_ok` con `input + output` completos, y cada 422 emite `predict_422` con la lista de errores. Buscable en Cloud Logging con filtros sobre `jsonPayload.message`. |

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
