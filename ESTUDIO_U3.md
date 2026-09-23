# Guía de estudio — Unidad 3

**Auditoría de sesgo por `gender` en un modelo de churn**

---

## Contexto y objetivo del cliente

Ustedes trabajan en el equipo de Ciencia de Datos de una telco. Ya hay un modelo de churn en producción (churn = cliente que cancela el servicio). El **PM del proyecto de retención** llegó con esta pregunta:

> *"El modelo predice bien, pero ¿está siendo justo con hombres y mujeres por igual? ¿Vale la pena aplicar técnicas de fairness?"*

Y les puso **6 tareas ponderadas**:

| # | Tarea | Puntos |
|---|---|---|
| 1 | Selección de features (≥3 justificadas) | 20 |
| 2 | Entrenar XGBoost baseline con ajustes para gender | 10 |
| 3 | Aplicar reweighting + adversarial + threshold por separado | 20 |
| 4 | Combinar las 3 técnicas en cascada (orden justificado) | 20 |
| 5 | Tabla comparativa (5 configs × 5 métricas) | 20 |
| 6 | Respuesta al PM (≤ 200 palabras) | 10 |

Con dos **constraints no negociables**:
- `SeniorCitizen` se remueve **completamente** del modelo (ni como feature ni como protegida) — instrucción del profesor
- `gender` (Male/Female) es la **única** variable protegida auditada
- Mantener `train_test_split(stratify=y, random_state=42)` para comparabilidad entre técnicas

---

## Marco conceptual: fairness en ML

Un modelo puede tener **excelente precisión pero ser injusto**. Ejemplo: si el modelo captura 90% de mujeres que iban a churnear pero solo 60% de hombres, se están yendo hombres sin que los llamemos.

Usamos 2 métricas de fairness (ambas de la librería **Fairlearn**):

- **DPD (Demographic Parity Difference)**: diferencia entre la tasa de "predicho positivo" entre grupos. Ideal = 0. Mide **paridad demográfica**.
- **EOD (Equalized Odds Difference)** = max{|TPR_A − TPR_B|, |FPR_A − FPR_B|}. Mide **paridad de oportunidad**. Ideal = 0.

Criterio del profesor: **DPD ≤ 0.20** y **EOD ≤ 0.20**.

**Métrica prima elegida**: EOD. Razón: en retención el daño principal es **quality-of-service** — mujeres que realmente iban a churnear y no reciben oferta. EOD mide exactamente paridad de recall entre grupos. Además, **Kleinberg/Chouldechova** demostraron que DPD y EOD no bajan a cero simultáneamente si las tasas base difieren, así que hay que elegir cuál priorizar.

---

# TAREA 1 — Selección de features (20 puntos)

## Qué pedía

Elegir al menos 3 features del dataset crudo y justificar por qué. **No** agregar "porque sí".

## Universo de análisis

El notebook base ya tenía 7 features. Había **10 columnas descartadas** como candidatas:
```
PhoneService, MultipleLines, InternetService, OnlineSecurity,
OnlineBackup, DeviceProtection, TechSupport, StreamingTV,
StreamingMovies, PaperlessBilling
```

## Los 3 criterios que combinamos

Cada feature candidata pasó por **3 filtros**. Solo si superaba los 3, entraba al modelo.

### Criterio 1 — Análisis descriptivo (pandas)

Para cada columna candidata:

**a) Cardinalidad y distribución**
```python
df[col].value_counts(dropna=False)
```
Por qué: si una feature tiene 90% valores iguales, no ayuda a discriminar.

**b) % nulls y valores estructuralmente distintos**
```python
df[col].isna().mean()
(df[col] == "No internet service").mean()
(df[col] == "No phone service").mean()
```
Por qué: "No internet service" no es un "No" real — significa que la feature ni siquiera aplica. Hay que decidir si tratarlo como categoría aparte.

**c) Tasa de churn por categoría (el más importante)**
```python
df.groupby(col)['Churn'].mean()
```
Ejemplo del output para `Contract`:
```
Month-to-month    0.43   ← 43% churnea
One year          0.11
Two year          0.03
```
Por qué: si la tasa por categoría **difiere claramente de la global** (~26%), la feature **segmenta** el churn → útil.

**d) Correlación con features ya seleccionadas**
```python
df[[col, 'tenure', 'MonthlyCharges']].corr()
```
Por qué: si está muy correlacionada con `tenure` o `MonthlyCharges` (ya adentro), es **redundante**.

### Criterio 2 — Test de proxy leakage (sklearn)

**Referencia**: Barocas & Selbst 2016, *"Big Data's Disparate Impact"*.

**La idea**: una feature puede **no ser género**, pero **codificarlo indirectamente**. Ejemplo hipotético: `TipoDePlan="Familiar"` podría correlacionarse con `Partner=True`, que a su vez con `gender=Female`. Si dejas entrar features proxy, el modelo aprende sesgos por la puerta trasera.

**Cómo se prueba**:
```python
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

# X = solo la feature candidata (one-hot si es categórica)
# y = gender codificado 0/1

modelo_aux = LogisticRegression().fit(X_solo_esa_feature, gender)
prob_gender = modelo_aux.predict_proba(X_solo_esa_feature)[:, 1]
auc = roc_auc_score(gender, prob_gender)

print(f"{feature} → AUC(gender) = {auc:.3f}")
```

**Regla de decisión**:
- **AUC < 0.7** → no es proxy de género → OK
- **AUC ≥ 0.7** → es proxy → descartar

**Por qué LogisticRegression y no XGBoost**: queremos capturar señal linear directa. XGBoost podría sobreajustar pequeñas señales no lineales y darnos falsos positivos.

**Por qué el umbral 0.7**: convención razonable (Barocas & Selbst 2016). `AUC=0.5` es azar, `AUC=1.0` es perfecto. `0.7` marca donde la señal empieza a ser "sustancial". Lo importante es **declararlo antes** del análisis, no ajustarlo después.

### Criterio 3 — Hipótesis de negocio explícita

No basta con estadística. Cada feature necesita una **historia de negocio** que explique **por qué** debería predecir churn.

## Features elegidas (3 nuevas + 7 base = 10 en total)

### Las 3 nuevas

**`InternetService`** (DSL / Fiber optic / No)
> Hipótesis: Fibra óptica es servicio premium; pagan más → posibles dos efectos contradictorios: (a) más propensos a churnear si no valoran el servicio; (b) el servicio retiene por calidad. El EDA nos dirá cuál gana.

Resultado del EDA: Fiber tiene mayor tasa de churn que DSL (el precio pesa más que la calidad).

**`TechSupport`** (Yes / No / No internet service)
> Hipótesis: Clientes sin soporte técnico tienen fricción cuando algo falla → mayor probabilidad de churn.

Resultado: quienes **no** contratan TechSupport churnean 41.7% vs 15.1% de los que sí. Claro.

**`OnlineSecurity`** (Yes / No / No internet service)
> Hipótesis: Add-on de seguridad. Si el cliente lo contrata, muestra compromiso con la marca → menos churn.

Resultado: quienes contrataron OnlineSecurity churnean menos.

### Las 7 base
`gender, Partner, Dependents, tenure, Contract, PaymentMethod, MonthlyCharges`

### Removida por instrucción del profesor
`SeniorCitizen` — introducía sesgo indirecto por edad correlacionada con gender.

## Features descartadas (justificación)

Las 7 que **NO** entraron pasaron al menos uno de estos criterios negativos:
- `PhoneService` — casi todos tienen (90% "Yes") → cardinalidad efectiva ~0
- `MultipleLines` — muy correlacionada con `PhoneService`
- `OnlineBackup`, `DeviceProtection`, `StreamingTV`, `StreamingMovies` — muy correlacionadas entre sí y con `InternetService`
- `PaperlessBilling` — no pasó el filtro de negocio (no hay hipótesis clara)
- `TotalCharges` — redundante con `tenure × MonthlyCharges`, colinealidad

## Entregables de esta tarea

- Sección de EDA en el notebook `u3-g02-nb-20260905.ipynb`
- Tabla proxy-AUC de todas las candidatas
- Actualización de `columnas_hoy` en el notebook

---

# TAREA 2 — XGBoost baseline (10 puntos)

## Qué pedía

Entrenar un XGBoost sobre las 10 features seleccionadas, **sin mitigación**. Es el punto de referencia.

## Por qué XGBoost (y no otro)

1. **El enunciado lo pedía explícitamente**
2. **Estándar de la industria para churn** — el Telco Churn Challenge en Kaggle lo ganó XGBoost
3. **Boosting sobre gradient descent** maneja bien el desbalance de clases y la mezcla de tipos categóricos/numéricos

## Los hiperparámetros exactos

En `parte_b_mitigacion.py:132-141`:

```python
xgb.XGBClassifier(
    n_estimators=100,      # 100 árboles
    max_depth=4,           # profundidad máxima 4 niveles
    learning_rate=0.1,     # cada árbol contribuye 10%
    random_state=42,       # reproducibilidad
    eval_metric="logloss", # BCE probabilística
    n_jobs=1,              # reproducibilidad numérica
)
```

## De dónde vienen los hiperparámetros

**Respuesta honesta**: NO los optimizamos con Grid Search / Optuna. Vienen del notebook base del profesor.

**Los defaults reales de XGBoost son distintos**:
| Parámetro | Default oficial | El que usamos |
|---|---|---|
| `n_estimators` | 100 | 100 ✓ |
| `max_depth` | **6** | 4 |
| `learning_rate` | **0.3** | 0.1 |

**Por qué está bien defenderlo así**:
- El objetivo de U3 era **auditar fairness**, no maximizar AUC
- Si hubiéramos optimizado en U3, cada configuración de mitigación tendría que reoptimizar también → 5 búsquedas separadas → ruido experimental → imposible aislar el efecto de fairness
- En **U4** sí optimizamos con Optuna (100 trials, CV interno), y los óptimos cayeron cerca de los defaults de U3 → validación a posteriori

**Referencias de convenciones**:
- XGBoost Parameter Docs: [xgboost.readthedocs.io/en/stable/parameter.html](https://xgboost.readthedocs.io/en/stable/parameter.html)
- Aarshay Jain (Analytics Vidhya 2016) — "Complete Guide to Parameter Tuning in XGBoost"
- Aurélien Géron — *Hands-On Machine Learning*, cap. 7
- Chen & Guestrin 2016 — el paper original de XGBoost (KDD 2016)

## El pipeline exacto

### 1. Cargar y limpiar
```python
df = pd.read_csv("WA_Fn-UseC_-Telco-Customer-Churn.csv")
df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
df["Churn"] = (df["Churn"] == "Yes").astype(int)
gender = df["gender"].copy()  # Male/Female como string
```

### 2. Seleccionar features
```python
columnas_hoy = [
    "gender", "Partner", "Dependents", "tenure", "Contract",
    "PaymentMethod", "MonthlyCharges", "InternetService",
    "OnlineSecurity", "TechSupport",
]
X = df[columnas_hoy]
y = df["Churn"]
```

### 3. Encoding categórico
```python
X = pd.get_dummies(X, drop_first=True)
```

**`drop_first=True`** evita colinealidad perfecta. Ejemplo: `Contract` (3 valores) queda como 2 columnas dummies (`Contract_One year`, `Contract_Two year`). Si ambas son 0 → Month-to-month (referencia).

**Importante**: exactamente este mismo encoding se replica en el servicio U5 — si cambian el encoding, el servicio se rompe.

### 4. Train/Test split
```python
X_train, X_test, y_train, y_test, gender_train, gender_test = train_test_split(
    X, y, gender,
    test_size=0.20,
    random_state=42,
    stratify=y,       # ← crítico
)
```

**Por qué `stratify=y`**: si el dataset tiene 26% churners, tanto train como test tendrán ~26%. Sin esto, el split aleatorio podría dar 20% o 32% → AUC/recall serían incomparables entre técnicas.

### 5. Entrenar
```python
modelo_base = _xgb_model(seed=42)
modelo_base.fit(X_train, y_train)  # sin sample_weight
```

### 6. Predecir y evaluar
```python
y_pred = modelo_base.predict(X_test)
y_proba = modelo_base.predict_proba(X_test)[:, 1]

# Utilidad
recall_score(y_test, y_pred)
precision_score(y_test, y_pred)
roc_auc_score(y_test, y_proba)

# Fairness (Fairlearn)
demographic_parity_difference(y_test, y_pred, sensitive_features=gender_test)
equalized_odds_difference(y_test, y_pred, sensitive_features=gender_test)
```

### 7. Guardar artifacts (contrato con B y C)
```
artifacts/X_train.pkl, X_test.pkl
artifacts/y_train.pkl, y_test.pkl
artifacts/gender_train.pkl, gender_test.pkl
artifacts/modelo_base.pkl
artifacts/baseline_metrics.json
```

## Resultado del baseline

```
Recall (Churn):  0.519    ← capturamos ~52% de los que iban a churnear
Precision:       0.664    ← 66% de los marcados como churn lo eran
AUC:             0.840    ← buena discriminación
DPD (gender):    0.010    ← disparidad demográfica casi nula
EOD (gender):    0.052    ← disparidad de oportunidad muy baja
```

## Insight clave

**El baseline YA cumple el criterio de fairness** sin mitigar. Esto no era esperado a priori. Razones posibles:

1. `gender` no está fuertemente correlacionado con las demás features en este dataset
2. `Churn` tampoco depende fuertemente de gender — hombres y mujeres churnean a tasas parecidas
3. Al remover `SeniorCitizen` (que sí sesgaba), el problema se resolvió solo

Este resultado es la base del argumento para **no mitigar** en la respuesta al PM.

---

# TAREA 3 — Las 3 técnicas por separado (20 puntos)

## Qué pedía

Aplicar **reweighting, adversarial, threshold** cada una de forma independiente, medir su impacto, comparar contra el baseline.

## Marco mental

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│  Pre-process   │ →   │  In-process    │ →   │  Post-process  │
│  (datos)       │     │  (algoritmo)   │     │  (predicción)  │
│                │     │                │     │                │
│  Reweighting   │     │  Adversarial   │     │  Threshold     │
│  Kamiran &     │     │  Zhang et al.  │     │  Hardt et al.  │
│  Calders 2012  │     │  2018          │     │  2016          │
└────────────────┘     └────────────────┘     └────────────────┘
```

Cada técnica interviene en un **momento distinto** del pipeline.

## Técnica 1 — Reweighting (pre-processing)

**Idea**: ajustar los pesos de las muestras del training set para que las combinaciones subrepresentadas pesen más al entrenar.

**Referencia**: Kamiran & Calders 2012.

### Implementación
```python
# Cruzar gender × Churn (la intersección crítica)
intersection = gender_train.astype(str) + "_" + y_train.astype(str)
# Ejemplo: "Male_0", "Male_1", "Female_0", "Female_1"

# sklearn calcula pesos que balancean las 4 celdas
sample_weights = compute_sample_weight(
    class_weight="balanced",
    y=intersection,
)

# Entrenar pasando los pesos
modelo_rw = _xgb_model(seed=42)
modelo_rw.fit(X_train, y_train, sample_weight=sample_weights)
```

### Detalle crítico: `gender × Churn`, no solo `Churn`

El enunciado exigía cruzar. Por qué:
- Si solo pesamos por `y` (Churn), balanceamos churn/no-churn pero **sin fijar el sesgo por género**
- Al cruzar `gender × Churn`, las 4 celdas de la matriz tienen influencia equivalente en el entrenamiento

### Chequeo obligatorio (defensivo)

```python
if len(weight_table) != 4 or weight_table["peso"].nunique() != 4:
    raise ValueError("Reweighting no produjo cuatro pesos distintos.")
```

Si el chequeo falla, sabemos que la implementación está mal.

### Resultado
```
Recall:     0.794    ← subió mucho (era 0.519)
Precision:  0.514    ← bajó (era 0.664)
AUC:        0.839
DPD:        0.014
EOD:        0.035    ← mejoró
```

### Trade-off
Sube recall porque el modelo se vuelve "sobre-sensible" a churn. Baja precisión por la misma razón. Es el clásico trade-off recall ↔ precision.

## Técnica 2 — Adversarial Training (in-processing)

**Idea**: entrenar dos redes en paralelo — un **predictor** que predice churn, y un **adversario** que trata de predecir gender desde las salidas del predictor. El predictor se penaliza si el adversario acierta.

**Referencia**: Zhang, Lemoine, Mitchell 2018 — *"Mitigating Unwanted Biases with Adversarial Learning"* (AAAI/ACM).

### Diagrama

```
X ──▶ Predictor ──▶ y_hat_churn ──▶ BCE(y_hat_churn, y_churn)
                       │                     │
                       ▼                     │
                    Adversario               │  loss del predictor
                       │                     │
                       ▼                     ▼
                   y_hat_gender ──▶ BCE(y_hat_gender, y_gender)
                                            │
                                            │  loss del adversario,
                                            ▼  MULTIPLICADA POR -λ
```

La **loss combinada del predictor**:
```
L_predictor = BCE(y_hat_churn, y_churn) − λ · BCE(y_hat_gender, y_gender)
```

El signo `−` es clave. Si el adversario **acierta** (BCE alto pero con signo positivo desde la perspectiva del adversario), el predictor lo resta → penalización → el predictor aprende a **no leakear gender**.

En el equilibrio, el adversario está al 50% (azar) → el predictor es "gender-blind".

### Implementación (PyTorch, `parte_b_mitigacion.py`)

```python
LAMBDA = 1.0
EPOCHS = 50
LEARNING_RATE = 0.001
SEEDS = (42, 7, 123, 2024, 99)

for seed in SEEDS:
    _set_seed(seed)
    predictor, adversary = _build_adversarial_models(input_dim=X_train.shape[1])

    for epoch in range(EPOCHS):
        # Forward
        y_hat_churn = predictor(X_train)
        y_hat_gender = adversary(y_hat_churn)

        # Losses
        loss_pred = BCE(y_hat_churn, y_churn) - LAMBDA * BCE(y_hat_gender, y_gender)
        loss_adv = BCE(y_hat_gender, y_gender)

        # Backward alternado
        optimizer_pred.zero_grad()
        loss_pred.backward(retain_graph=True)
        optimizer_pred.step()

        optimizer_adv.zero_grad()
        loss_adv.backward()
        optimizer_adv.step()
```

### Extra crítico: 5 seeds

Adversarial es **notoriamente inestable**. Zhang et al. 2018 recomienda mínimo 5 seeds. Sin multi-seed, un solo run "afortunado" puede engañar.

### Resultado (media ± std sobre 5 seeds)
```
Recall:     0.530 ± 0.025
Precision:  0.609 ± 0.034
AUC:        0.806 ± 0.006    ← bajó de 0.84
DPD:        0.048 ± 0.019
EOD:        0.042 ± 0.019
```

### Trade-off
Baja AUC (perdemos poder predictivo) porque el modelo se vuelve gender-blind por construcción. Además es **inestable** (varianza entre seeds visible en las `± std`).

## Técnica 3 — Threshold Adjustment (post-processing)

**Idea**: dejar el modelo **intacto** y ajustar el **umbral de decisión** distinto para cada grupo protegido.

**Referencia**: Hardt, Price, Srebro 2016 — *"Equality of Opportunity in Supervised Learning"* (NeurIPS).

### Ejemplo intuitivo

Si el modelo baseline usa umbral 0.5 para todos:
- Umbral para hombres: **0.42** → más generoso, más hombres predichos como churn
- Umbral para mujeres: **0.38** → aún más generoso para mujeres

Al bajar el umbral para el grupo con menor recall, se **iguala el TPR** entre grupos → `EOD ≈ 0`.

### Implementación (Fairlearn)

```python
from fairlearn.postprocessing import ThresholdOptimizer

thr_model = ThresholdOptimizer(
    estimator=modelo_base,                # el XGBoost base ya entrenado
    constraints="equalized_odds",         # forzar EOD → 0
    objective="balanced_accuracy_score",  # maximizar balanced accuracy
    prefit=True,                          # NO reentrenar el estimator
    predict_method="predict_proba",
)

# Aprende los umbrales por grupo
thr_model.fit(X_train, y_train, sensitive_features=gender_train)

# Al predecir, hay que pasar el gender otra vez
y_pred = thr_model.predict(X_test, sensitive_features=gender_test)
```

### Extraer los umbrales aprendidos (auditoría)

Fairlearn no expone directamente los umbrales, pero es importante hacerlos **auditables**. En `parte_b_mitigacion.py:251-276`:

```python
def extract_thresholds(threshold_model: ThresholdOptimizer) -> dict[str, Any]:
    thresholder = getattr(threshold_model, "interpolated_thresholder_", None)
    interpolation = getattr(thresholder, "interpolation_dict", {}) or {}
    ...
```

Los umbrales se guardan en `artifacts/tecnicas_individuales.json`.

### Resultado
```
Recall:     0.799   ← subió mucho
Precision:  0.525
AUC:        0.840   ← intacto (el modelo no se reentrenó)
DPD:        0.003   ← el más bajo de todos
EOD:        0.035
```

### Trade-off
Rapidísimo, preserva AUC. **Pero**: requiere conocer el `gender` en **tiempo de inferencia**. Además, puede constituir *disparate treatment* (Ricci v. DeStefano 2009). En algunas jurisdicciones tratar diferente a grupos protegidos es ilegal — decisión legal, no técnica.

## Tabla comparativa de las 3

| Técnica | Momento | ¿Retrena? | ¿Necesita gender en inferencia? | Recall | AUC | EOD |
|---|---|---|---|---|---|---|
| Base | — | — | No | 0.519 | 0.840 | 0.052 |
| Reweighting | Pre | Sí | No | **0.794** | 0.839 | 0.035 |
| Adversarial | In | Sí | No | 0.530 | 0.806 | 0.042 |
| Threshold | Post | No | **Sí** | **0.799** | 0.840 | 0.035 |

Todas cumplen el criterio (EOD < 0.20). Cada una tiene trade-offs distintos.

---

# TAREA 4 — Combinación en cascada (20 puntos)

## Qué pedía

Combinar reweighting + adversarial + threshold en un solo pipeline, con **orden justificado**.

## Orden elegido

```
Reweighting → Adversarial → Threshold
   (pre)      (in-processing)    (post)
```

## Justificación del orden

Esto lo puede preguntar la profesora — memorízalo bien.

**1. Reweighting va primero** porque corrige el **sesgo estructural de los datos** antes del entrenamiento. Es lógico limpiar los datos antes de entrenar el modelo.

**2. Adversarial va segundo, entrenando sobre los datos ya reponderados** — esto es explícito en el "troubleshooting del PM": *"declarar sobre qué datos entrena la segunda técnica"*. El BCELoss del predictor se pondera con `sample_weights` del paso 1, y el adversario intenta recuperar gender.

**3. Threshold va al final** porque es post-processing puro — se aplica sobre las probabilidades del predictor adversarial ya entrenado con pesos.

## Implementación (`parte_c_combinacion.py`)

```python
# Paso 1: pesos del reweighting
sample_weights = compute_sample_weight(class_weight="balanced", y=intersection)

# Paso 2: adversarial sobre datos reponderados
for seed in SEEDS:
    _set_seed(seed)
    predictor, adversary = _build_adversarial_models(...)
    for epoch in range(EPOCHS):
        # loss_pred multiplicada por sample_weights
        loss_pred = (BCE(y_hat_churn, y_churn) * sample_weights).mean() \
                    - LAMBDA * BCE(y_hat_gender, y_gender)
        ...

# Paso 3: wrapper para que la red adversarial exponga predict_proba
class _AdversarialWrapper(BaseEstimator, ClassifierMixin):
    def predict_proba(self, X):
        return np.column_stack([1 - probas, probas])

# ThresholdOptimizer sobre el wrapper
thr_model = ThresholdOptimizer(
    estimator=_AdversarialWrapper(mejor_predictor),
    constraints="equalized_odds",
    prefit=True,
)
thr_model.fit(X_train, y_train, sensitive_features=gender_train)
```

## Resultado combinado
```
Recall:     0.730
Precision:  0.465
AUC:        0.815
DPD:        0.020
EOD:        0.095   ← SUBIÓ vs ~0.035 de las técnicas por separado
```

## Sorpresa negativa: combinar empeora

Este es el **hallazgo más importante** de la Tarea 4:

- EOD subió de ~0.035 a 0.095
- AUC bajó de 0.84 a 0.815
- Precision cayó a 0.465

**Lección**: **las técnicas de fairness no son aditivas**. Cada una interviene sobre un aspecto distinto del pipeline y a veces se anulan o se pelean entre sí.

- Reweighting balancea las 4 celdas → el modelo aprende una distribución "ficticia"
- Adversarial sobre esa distribución ficticia → intenta remover gender info de una señal ya distorsionada
- Threshold sobre el resultado → intenta corregir lo que las dos anteriores dejaron

Cada técnica introduce **ruido en la señal** que la siguiente tiene que digerir. Al final, EOD sube porque el modelo ya no distingue bien churn de no-churn, y las "correcciones" cruzadas empeoran.

## Conclusión para el PM

Combinar NO valió la pena en este caso. La técnica ganadora individualmente (threshold) es mejor que la combinación.

---

# TAREA 5 — Tabla comparativa (20 puntos)

## Qué pedía

Una tabla con las **5 configuraciones × 5 métricas** para que el PM pudiera comparar de un vistazo.

## Tabla entregada

| Config | Recall | Precision | AUC | DPD | EOD | Cumple ≤ 0.20 |
|---|---|---|---|---|---|---|
| **Base** | 0.519 | 0.664 | 0.84 | 0.010 | 0.052 | ✅ |
| Reweighting | 0.794 | 0.514 | 0.839 | 0.014 | 0.035 | ✅ |
| Adversarial (±std) | 0.530 ± 0.025 | 0.609 ± 0.034 | 0.806 ± 0.006 | 0.048 ± 0.019 | 0.042 ± 0.019 | ✅ |
| Threshold | **0.799** | 0.525 | 0.840 | **0.003** | 0.035 | ✅ |
| Combinado | 0.730 | 0.465 | 0.815 | 0.020 | 0.095 | ✅ |

## Interpretación por columna

- **Recall**: threshold y reweighting ganan (~0.79-0.80)
- **Precision**: base gana (0.664); todas las mitigaciones la reducen
- **AUC**: threshold preserva 0.84; adversarial cae a 0.81
- **DPD**: threshold es el mejor (0.003)
- **EOD**: reweighting y threshold empatan (0.035)

**Ninguna configuración es mejor en todas las columnas**. Hay que elegir según el objetivo de negocio.

## Auto-generación de la tabla

`RESULTADOS.md` se re-renderiza automáticamente desde `artifacts/tabla_comparativa.json` mediante un pre-commit hook. Nunca queda desincronizada.

---

# TAREA 6 — Respuesta al PM (10 puntos, ≤ 200 palabras)

## Qué pedía

Un correo al PM con la recomendación final: concreto, con números, ≤ 200 palabras.

## Correo entregado

> **Asunto: Resultados de la auditoría de género — modelo de churn**
>
> Terminamos la auditoría del modelo de churn usando `gender` como único atributo protegido. Primero medimos el modelo actual y luego probamos reweighting, entrenamiento adversarial, ajuste de decisión y su combinación.
>
> `gender` ya presentaba poca disparidad en el modelo actual (DPD=0.010; EOD=0.052). Reweighting redujo EOD a 0.035, mantuvo AUC en 0.839 y elevó recall de 0.519 a 0.794. El ajuste de decisión logró DPD=0.003, EOD=0.035 y recall=0.799.
>
> Adversarial redujo EOD a 0.042, pero AUC cayó de 0.840 a 0.806 y recall quedó en 0.530. Combinar técnicas no valió la pena: EOD subió a 0.095 y AUC fue 0.815.
>
> **Recomendamos conservar el modelo actual y monitorearlo mensualmente.** Si el negocio prioriza captar más clientes en riesgo y puede asumir más contactos innecesarios, el **ajuste de decisión** es la alternativa a evaluar. Para auditoría conservamos versión, datos, errores por género y comparación de modelos.

## El "twist" de la recomendación

El enunciado te pedía probar 4 técnicas de mitigación, pero la **respuesta correcta era NO mitigar**. ¿Por qué?

1. El baseline **ya cumple** el criterio (DPD=0.01, EOD=0.052 < 0.20)
2. Las técnicas que mejoran EOD **destruyen la precisión** (0.66 → 0.51)
3. Adversarial **baja AUC**
4. Combinar **empeora todo**

Lección crucial para la sustentación: **no aplicar una técnica solo porque el enunciado la pidió**. Hay que justificar con datos si vale la pena o no. La profesora quiere ver que **piensas críticamente**, no que ejecutas órdenes.

---

# Extras exigidos por investigación

Aunque no valían puntos separados, dan robustez académica:

## 1. Fairness baseline antes de mitigar (Fairlearn User Guide)

Nunca mitigar sin medir primero — de otra manera no sabes contra qué comparas.

## 2. Proxy leakage test para cada feature nueva (Barocas & Selbst 2016)

Ya explicado en Tarea 1.

## 3. Adversarial multi-seed con media ± std (Zhang et al. 2018)

Ya explicado en Tarea 3. Sin esto, adversarial no es reproducible.

## 4. Declarar métrica prima antes de mitigar

Elegimos **EOD** porque en retención el daño es no llamar a alguien que iba a churnear. **Kleinberg/Chouldechova** demostraron que DPD y EOD no pueden bajar a cero simultáneamente si las tasas base difieren.

## 5. Model Card estilo Mitchell et al. 2019

Al final del notebook. Obligatorio implícitamente por **EU AI Act Art. 11** (Documentación técnica para sistemas de alto riesgo).

Estructura del Model Card:
- Model details (arquitectura, versión, autores)
- Intended use (para qué se debe usar, para qué NO)
- Factors (variables protegidas evaluadas)
- Metrics (utilidad + fairness)
- Evaluation data (splits, distribuciones)
- Ethical considerations (disparate treatment, limitaciones)

## 6. Documentar limitación de `gender`

En el dataset viene binario Male/Female. No hay categoría "no declarado" ni identidades no binarias. Esto **debe declararse** explícitamente en el Model Card — la auditoría es limitada a este universo binario.

---

# Preguntas típicas de sustentación para U3

## Sobre features
1. ¿Qué es proxy leakage y por qué lo probamos con LogReg y no XGBoost?
2. ¿Por qué el umbral del proxy test es 0.7 y no 0.6 o 0.8?
3. Si una feature tiene AUC=0.85 sobre gender pero segmenta churn perfectamente, ¿la incluirías? Justifica.
4. ¿Por qué `SeniorCitizen` fue removido?

## Sobre el baseline
5. ¿Por qué `n_jobs=1` en XGBoost?
6. ¿Por qué `stratify=y` es crítico en el split?
7. ¿Cómo escogieron los hiperparámetros de XGBoost?
8. Los defaults **reales** de XGBoost son `max_depth=6` y `lr=0.3`. ¿Por qué usaron valores distintos?

## Sobre las 3 técnicas
9. Explica en 3 frases qué hace cada técnica y en qué momento del pipeline actúa.
10. ¿Por qué reweighting cruza `gender × Churn` y no solo `Churn`?
11. ¿Por qué corrimos adversarial con 5 seeds?
12. ¿Cuál es el problema práctico de threshold adjustment en producción?
13. ¿Qué es *disparate treatment* y por qué es riesgo con threshold?

## Sobre la combinación
14. ¿Por qué reweighting va antes de adversarial y no al revés?
15. ¿Por qué combinar empeoró EOD?

## Sobre la recomendación final
16. Si el modelo ya era justo, ¿para qué me pidieron esta auditoría?
17. ¿Por qué recomiendan NO mitigar? Dame la razón numérica.
18. ¿En qué caso sí mitigarían?
19. ¿Por qué EOD y no DPD como métrica principal?

## Meta-preguntas
20. ¿Qué aprendieron sobre fairness haciendo este trabajo?
21. ¿Cuál sería el siguiente paso si tuvieran otra semana?

---

# Frases resumen para memorizar

## Big picture
> *"En U3 auditamos el sesgo por género del modelo de churn. Probamos 3 técnicas de fairness (reweighting, adversarial, threshold) y su combinación. Encontramos que el baseline ya cumplía el criterio (EOD < 0.20), y que ninguna mitigación mejoraba el conjunto sin costar precisión o AUC. Recomendamos no mitigar."*

## Sobre features
> *"Combinamos 3 criterios: (1) EDA cuantitativo con pandas — cardinalidad, distribuciones, tasa de churn por categoría; (2) test de proxy leakage — LogisticRegression prediciendo gender desde la feature candidata, umbral AUC < 0.7 (Barocas & Selbst 2016); (3) hipótesis de negocio explícita. Las 3 nuevas (InternetService, OnlineSecurity, TechSupport) pasaron los 3 filtros."*

## Sobre XGBoost
> *"Valores del notebook base — no optimizamos hiperparámetros en U3 porque el objetivo era auditar fairness sobre un modelo estable. Los defaults reales de XGBoost son distintos (max_depth=6, lr=0.3); usamos max_depth=4 y lr=0.1 por convención de la comunidad. La optimización sistemática la hicimos en U4 con Optuna."*

## Sobre las 3 técnicas
> *"Cada técnica interviene en un momento distinto: reweighting antes de entrenar (pesa gender × Churn), adversarial durante el entrenamiento (predictor vs adversario, 5 seeds por inestabilidad), threshold después (umbrales distintos por grupo). Threshold gana individualmente pero requiere conocer gender en inferencia — implicación legal (disparate treatment)."*

## Sobre la respuesta al PM
> *"Recomendamos NO mitigar porque el baseline ya cumple (EOD=0.052, DPD=0.010) y todas las mitigaciones cuestan precisión (0.66 → 0.51) o AUC (0.84 → 0.81). Combinar empeora aún más. La lección es que no todas las técnicas del enunciado hay que aplicarlas — hay que justificar con datos."*

---

# Archivos del entregable en el repo

```
u3-g02-nb-20260905.ipynb    ← notebook principal (54 celdas)
parte_b_mitigacion.py       ← implementación de las 3 técnicas individuales
parte_c_combinacion.py      ← cascada + tabla + Model Card + respuesta PM

artifacts/
  X_train.pkl, X_test.pkl
  y_train.pkl, y_test.pkl
  gender_train.pkl, gender_test.pkl
  modelo_base.pkl
  modelo_reweighting.pkl
  modelo_adversarial_bestseed.pt
  threshold_optimizer.pkl
  baseline_metrics.json
  tecnicas_individuales.json
  tecnicas_combinadas.json
  tabla_comparativa.json

RESULTADOS.md               ← tabla + respuesta al PM (auto-generado)
MODEL_CARD.md               ← Model Card estilo Mitchell 2019 (auto-generado)
PLAN_IMPLEMENTACION.md      ← plan dividido en 3 partes A/B/C
regenerate_docs.py          ← script del pre-commit hook
```
