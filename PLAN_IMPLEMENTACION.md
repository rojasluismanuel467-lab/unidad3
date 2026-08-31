# Plan de Implementación — Unidad 3, Auditoría de Sesgo por `gender`

**Repo**: `rojasluismanuel467-lab/unidad3` (privado)
**Notebook base**: `u3_telco_churn_bias_analysis.ipynb`
**Objetivo**: responder la solicitud del PM del proyecto de retención con evidencia numérica.

---

## Contexto del entregable

El PM pidió que el modelo de churn se audite y mitigue **para género** (adicional a `SeniorCitizen`, no reemplazo), amplíe features del dataset crudo con criterio, aplique reweighting + adversarial + threshold por separado y combinadas, y que le respondamos con números si mejoró la equidad, cuánto costó en AUC/recall, y si combinar valió la pena.

## Requisitos mínimos para aprobar la unidad

Del enunciado, ponderación 100%:

| # | Item | % |
|---|---|---|
| 1 | Selección de features (≥3 justificadas) | 20 |
| 2 | Entrenar XGBoost con ajustes para gender | 10 |
| 3 | Aplicar reweighting + adversarial + threshold **por separado** | 20 |
| 4 | Combinar las 3 técnicas (orden justificado) | 20 |
| 5 | Tabla comparativa (recall, precision, AUC, DPD, EOD) × 5 configs | 20 |
| 6 | Respuesta al PM ≤200 palabras | 10 |

**Constraints obligatorios (no negociables):**
- No agregar todas las columnas "porque sí" — cada feature con justificación.
- Mantener `train_test_split(stratify=y, random_state=42)` para comparabilidad.
- `gender` es variable protegida **adicional** a `SeniorCitizen`.

**Troubleshooting explícito del enunciado:**
- `compute_sample_weight` debe cruzar `gender × Churn`, no `SeniorCitizen × Churn`.
- Encoding numérico de `gender` antes de Fairlearn / red adversaria.
- Explicitar sobre qué datos entrena la 2ª técnica de la combinación.

## Extras exigidos por la investigación (Géron, Chollet, NIST, Fairlearn, Barocas & Selbst, Zhang et al., Pleiss et al.)

Estos NO valen puntos extra por sí solos, pero blindan la respuesta al PM y evitan hallazgos negativos si legal audita:

1. **Fairness baseline sobre `gender` ANTES de mitigar** (Fairlearn User Guide) — nunca mitigar sin medir primero.
2. **Test de proxy leakage** para cada feature candidata: entrenar clasificador auxiliar `feature → gender` y reportar AUC. Si AUC>0.7 la feature es proxy y hay que decidir con criterio (Barocas & Selbst 2016).
3. **Adversarial multi-seed** (≥5 seeds), reportar media±std, no cherry-pick (Zhang et al. 2018).
4. **Declarar métrica prima antes de mitigar** — proponemos **EOD** (Equal Opportunity Difference). Racional: en retención, el daño principal es *quality-of-service* (mujeres realmente en riesgo no reciben oferta); EOD mide exactamente paridad de TPR. Kleinberg/Chouldechova demuestran que DPD y EOD no bajan a cero simultáneamente si las tasas base difieren.
5. **Model Card** breve al final del notebook (Mitchell et al. 2019, exigido implícitamente por EU AI Act Art. 11).
6. **Documentar limitación**: `gender` viene binario Male/Female en este dataset; no hay categoría "no declarado".

## Estado actual del notebook (baseline heredado, sobre `SeniorCitizen`)

| Config | AUC | Recall (Churn) | Precision | DPD | EOD |
|---|---|---|---|---|---|
| Base | 0.829 | 0.520 | 0.630 | 0.273 | 0.309 |
| Reweighting | 0.823 | 0.770 | 0.510 | 0.135 | 0.081 |
| Adversarial | 0.789 | 0.599 | 0.580 | 0.070 | 0.040 |

Estos números son sobre `SeniorCitizen`. **Todos deben recalcularse sobre `gender`** con features ampliadas.

---

# Reparto en 3 partes

Diseñado para maximizar paralelismo. **Un solo checkpoint duro** entre A y (B, C).

## Parte A — Datos, Features y Modelo Base ampliado (Compañero 1)

**Ponderación cubierta**: 30% (Item 1 + Item 2)
**Duración estimada**: 40% del esfuerzo total. Es la parte más de EDA/pensamiento.
**Dependencias**: ninguna — arranca primero.

### Tareas

1. **EDA de las 11 columnas descartadas** (`PhoneService`, `MultipleLines`, `InternetService`, `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`, `PaperlessBilling`).
   Para cada una:
   - Cardinalidad y distribución (`value_counts`)
   - % nulls / valores "No internet service" / "No phone service"
   - Tasa de churn por categoría (`df.groupby(col)['Churn'].mean()`)
   - Correlación con `MonthlyCharges` y `tenure` (posible redundancia)

2. **Test de proxy leakage vs `gender`** — para cada feature candidata:
   ```python
   from sklearn.linear_model import LogisticRegression
   from sklearn.metrics import roc_auc_score
   # gender codificado 0/1
   # X = solo esa feature (one-hot si aplica)
   # target = gender
   auc = roc_auc_score(gender, LogReg().fit(X, gender).predict_proba(X)[:,1])
   ```
   Descartar si AUC > 0.7. Reportar tabla `feature → AUC(→gender)`.

3. **Selección justificada de ≥3 features** — combinar 3 criterios:
   - **Negocio**: hipótesis explícita ("cliente sin `TechSupport` → mayor fricción → churn").
   - **EDA cuantitativo**: la tasa de churn del subgrupo debe diferir claramente de la global.
   - **No proxy de género**: AUC del test anterior < 0.7.

   Candidatas prioritarias (sujetas a validación por EDA):
   - `InternetService` (Fiber optic vs DSL vs None segmenta churn fuertemente en la literatura Telco)
   - `TechSupport` (mencionada explícitamente por el PM)
   - `OnlineSecurity` (servicio de valor agregado, retiene)
   - Opcional 4ta: `PaperlessBilling` si EDA lo respalda

4. **Actualizar `columnas_hoy`** en la celda de selección, mantener `TotalCharges` fuera (decisión heredada, documentar el trade-off en 2 líneas).

5. **Reentrenar modelo base** con features ampliadas: mismo `XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42)`. Mismo `train_test_split(test_size=0.2, random_state=42, stratify=y)`.

6. **Fairness baseline sobre `gender`** — calcular DPD, EOD y métricas desagregadas (recall, precision por Male/Female) del modelo base ampliado, ANTES de cualquier mitigación. Comparar contra el baseline heredado (features viejas + SeniorCitizen) para saber cuánta señal aportan las nuevas features.

### Entregables (contrato para B y C)

Guardar en el repo, en `artifacts/`:
- `artifacts/X_train.pkl`, `X_test.pkl`, `y_train.pkl`, `y_test.pkl`, `gender_train.pkl`, `gender_test.pkl` (Serie cruda Male/Female y one-hot numérico 0/1).
- `artifacts/modelo_base.pkl` (el XGBoost entrenado).
- `artifacts/baseline_metrics.json` con: `{recall, precision, auc, dpd_gender, eod_gender, recall_male, recall_female, ...}`.
- Sección de notebook con celdas markdown que expliquen la selección (evidencia visible para el profesor).

### Criterios de "hecho"
- Tabla EDA con las 11 features y sus 4 columnas de análisis.
- Tabla proxy-AUC.
- Justificación escrita de las features seleccionadas (2-3 líneas cada una).
- Baseline numérico visible en el notebook.

---

## Parte B — Técnicas Individuales de Mitigación sobre `gender` (Compañero 2)

**Ponderación cubierta**: 20% (Item 3)
**Duración estimada**: 30% del esfuerzo.
**Dependencias**: Parte A completada (necesita los pickles y el modelo base).

### Tareas

1. **Técnica 1 — Reweighting** (pre-processing, Kamiran & Calders 2012):
   ```python
   from sklearn.utils.class_weight import compute_sample_weight
   grupo_interseccion = gender_train.astype(str) + "_" + y_train.astype(str)
   sample_weights = compute_sample_weight(class_weight='balanced', y=grupo_interseccion)
   modelo_rw = xgb.XGBClassifier(...).fit(X_train, y_train, sample_weight=sample_weights)
   ```
   **Chequeo obligatorio**: imprimir los pesos únicos y verificar que las 4 celdas (Male/Female × Churn/No-Churn) reciben pesos distintos.

2. **Técnica 2 — Adversarial Training** (in-processing):
   Adaptar el bloque PyTorch existente. Cambiar `s_train_t` de `SeniorCitizen` a `gender_Male` (0/1). Predictor + Adversario con la misma arquitectura.
   **Extra crítico (research-based)**: correr **5 seeds** (42, 7, 123, 2024, 99), guardar la mejor por EOD y reportar media±std de las 5 en (AUC, recall, EOD). Sin esto no es reproducible (Zhang et al.).
   Hiperparámetros: `LAMBDA=1.0`, `EPOCHS=50`, `lr=0.001` (mantener consistencia con lo aprendido en clase).

3. **Técnica 3 — Threshold Adjustment** (post-processing, Hardt et al. 2016):
   Usar `fairlearn.postprocessing.ThresholdOptimizer`:
   ```python
   from fairlearn.postprocessing import ThresholdOptimizer
   thr_model = ThresholdOptimizer(
       estimator=modelo_base,
       constraints='equalized_odds',
       objective='balanced_accuracy_score',
       prefit=True,
       predict_method='predict_proba'
   )
   thr_model.fit(X_train, y_train, sensitive_features=gender_train)
   y_pred_thr = thr_model.predict(X_test, sensitive_features=gender_test)
   ```
   **Documentar**: el ThresholdOptimizer aplica umbrales distintos por grupo. En la respuesta al PM hay que mencionar el riesgo de *disparate treatment* (Ricci v. DeStefano) — decisión legal, no técnica.

4. **Métricas por técnica**: para cada una calcular recall, precision, AUC (donde aplique — ThresholdOptimizer no da probas comparables, usar AUC del modelo base), DPD y EOD sobre `gender`.

### Entregables (contrato para C)

- `artifacts/tecnicas_individuales.json` con la estructura:
  ```json
  {
    "reweighting":  {"recall":..., "precision":..., "auc":..., "dpd":..., "eod":...},
    "adversarial":  {"recall_mean":..., "recall_std":..., "eod_mean":..., "eod_std":..., ...},
    "threshold":    {"recall":..., "precision":..., "auc":..., "dpd":..., "eod":...}
  }
  ```
- `artifacts/modelo_reweighting.pkl`, `modelo_adversarial_bestseed.pt`, `threshold_optimizer.pkl`.
- Celdas de notebook con la lógica documentada (comentarios inline explicando cada línea crítica).

### Criterios de "hecho"
- Las 3 técnicas corren end-to-end en el notebook.
- Adversarial reporta ≥5 seeds, no un solo run.
- Reweighting muestra los 4 pesos únicos.
- ThresholdOptimizer imprime los umbrales por grupo.

---

## Parte C — Combinación, Tabla, Model Card y Respuesta al PM (Compañero 3)

**Ponderación cubierta**: 50% (Item 4 + 5 + 6)
**Duración estimada**: 30% del esfuerzo.
**Dependencias**: Parte B completada. **Puede empezar en paralelo con B** en el setup (funciones de métricas, plantilla de tabla, borrador de Model Card).

### Tareas

1. **Combinación en cascada** (Item 4, 20%) — orden propuesto y justificación:

   > **Orden: Reweighting → Adversarial → Threshold**
   >
   > **Justificación**:
   > (a) Reweighting primero porque es pre-processing: modifica la distribución de entrenamiento y da una base más limpia a lo que sigue.
   > (b) Adversarial segundo, **entrenado sobre los datos ya reponderados** (los `sample_weights` de la etapa anterior se pasan como pesos por muestra en el loss del predictor; el adversario ve las mismas muestras). Racional: la red debe aprender a "confundir" al adversario sobre la distribución que sí queremos que vea en producción, no sobre la sesgada original.
   > (c) Threshold al final porque es post-processing puro: solo ajusta el umbral de decisión sobre las probas del modelo ya doblemente mitigado.

   **Decisión explícita del troubleshooting del PM**: la 2ª técnica (adversarial) entrena sobre **datos re-ponderados**, no originales. Se comenta en el notebook.

2. **Tabla comparativa** (Item 5, 20%):

   | Config | Recall (Churn) | Precision | AUC-ROC | DPD (gender) | EOD (gender) |
   |---|---|---|---|---|---|
   | Base | | | | | |
   | Reweighting | | | | | |
   | Adversarial (media±std) | | | | | |
   | Threshold | | | | | |
   | **Combinado** | | | | | |

   Debe estar en el notebook como celda de código (imprime tabla desde el JSON de B + resultado de la combinación) **y** también como celda markdown formateada.

3. **Model Card** breve (Mitchell et al. 2019) — celda markdown al final:
   - Modelo, uso previsto, out-of-scope uses
   - Data: dataset, población, sesgo de etiqueta declarado
   - Métricas: la tabla comparativa + qué métrica se optimizó y por qué
   - Consideraciones éticas: `gender` binario, riesgo *disparate treatment* del threshold
   - Recomendación operacional al equipo de U4/U5

4. **Respuesta al PM** (Item 6, 10%) — ≤200 palabras, redactada como email:
   Debe responder las 4 preguntas literales del PM:
   - ¿Mejoró la equidad para gender?
   - ¿Cuánto costó en AUC/recall?
   - ¿Combinar las técnicas valió la pena?
   - ¿Gender ya tenía poca disparidad desde el modelo base?

   Formato sugerido: dos párrafos + tabla resumen de 3 filas.

5. **Commit y push final** al repo `unidad3`, con mensaje: `feat: mitigación de sesgo por gender - notebook completo`.

### Entregables

- Notebook `u3_telco_churn_bias_analysis.ipynb` completo y ejecutable end-to-end.
- Sección "Model Card" y sección "Respuesta al PM" visibles.
- Repo actualizado en GitHub.
- `RESULTADOS.md` en el root del repo con la tabla + respuesta al PM (fuera del notebook, para que legal/PM pueda leer sin abrir Jupyter).

### Criterios de "hecho"
- Notebook corre de principio a fin sin errores.
- Tabla comparativa 5 filas × 5 métricas completa.
- Respuesta al PM ≤200 palabras (contadas).
- Model Card cubre las 5 secciones del template Mitchell 2019.

---

# Orquestación entre las 3 partes

```
Tiempo →

Parte A ██████████████████████
                              ↓ (checkpoint: pickles + baseline)
Parte B                       ██████████████████
                              ↓ (checkpoint: JSON con métricas)
Parte C            ████████████████████████████████
                   ↑ (arranca en paralelo: setup, plantilla, Model Card)
```

**Sync points:**
1. **Fin de A → inicio de B**: A entrega los `.pkl` en `artifacts/`.
2. **Fin de B → cierre de C**: B entrega `tecnicas_individuales.json` para la tabla final.
3. **C hace el commit final** con integración de todo.

**Convención de ramas Git** (opcional pero recomendada):
- `main`: solo commits integrados y funcionales.
- `feat/parte-a-features`, `feat/parte-b-mitigacion`, `feat/parte-c-integracion`: ramas de trabajo.
- Merge a `main` cuando cada compañero valida su entregable.

---

# Riesgos y cómo mitigarlos

| Riesgo | Mitigación |
|---|---|
| A elige features que son proxy de gender sin querer | Test de proxy leakage es obligatorio, no opcional |
| Adversarial reporta un buen seed por suerte | Multi-seed con reporte de std |
| Combinación no mejora vs. sola-reweighting | Documentar honestamente en la respuesta al PM — "no forcemos una solución a un problema que no existe" (palabras del PM) |
| Threshold por grupo es cuestionable legalmente | Declarar explícitamente en Model Card y respuesta al PM |
| Runs no reproducibles | Fijar todas las semillas (numpy, torch, xgboost, random) al inicio |
| Gender ya está razonablemente parejo en el base | Si el baseline arroja DPD/EOD < 0.05, la respuesta al PM debe decirlo sin mitigar por mitigar |

---

# Definition of Done — checklist final antes de entregar

- [ ] Notebook corre end-to-end sin excepciones desde una VM limpia
- [ ] `train_test_split(stratify=y, random_state=42)` es idéntico en las 5 configs
- [ ] `gender` es adicional a `SeniorCitizen` (no reemplazo) — ambos siguen como features
- [ ] `compute_sample_weight` usa `gender × Churn`, verificado imprimiendo los 4 pesos únicos
- [ ] Encoding numérico de `gender` (0/1) confirmado antes de pasar a NN
- [ ] Documentado explícitamente qué datos entrena cada técnica en la combinación
- [ ] Tabla comparativa 5 filas × 5 métricas presente
- [ ] Respuesta al PM ≤200 palabras (contar con `len(respuesta.split())`)
- [ ] Model Card presente
- [ ] Repo pusheado a `main`
- [ ] `RESULTADOS.md` generado en el root
