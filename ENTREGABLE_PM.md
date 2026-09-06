# Auditoría de sesgo por `gender`

## Tabla comparativa

| Config | Recall (Churn) | Precision | AUC | DPD (gender) | EOD (gender) | Cumple criterio profesora (≤ 0.20) |
|---|---|---|---|---|---|---|
| Base (sin mitigar) | 0.519 | 0.664 | 0.84 | 0.01 | 0.052 | Sí |
| Reweighting | 0.794 | 0.514 | 0.839 | 0.014 | 0.035 | Sí |
| Adversarial (media±std, 5 seeds) | 0.530 ± 0.025 | 0.609 ± 0.034 | 0.806 ± 0.006 | 0.048 ± 0.019 | 0.042 ± 0.019 | Sí |
| Threshold adjustment | 0.799 | 0.525 | 0.84 | 0.003 | 0.035 | Sí |
| Combinado (rw→adv→thr) | 0.73 | 0.465 | 0.815 | 0.02 | 0.095 | Sí |

## Correo para el PM

**Asunto: Resultados de la auditoría de género — modelo de churn**

Hola,

Terminamos la auditoría del modelo de churn usando `gender` como único atributo protegido. Primero medimos el modelo actual; después probamos reweighting, entrenamiento adversarial, ajuste de decisión y una combinación de las tres alternativas.

El modelo actual ya cumple el criterio interno de equidad acordado para esta auditoría. Algunas alternativas aumentan la detección de clientes en riesgo, pero también reducen la precisión o añaden complejidad. La opción adversarial redujo una de las brechas entre géneros, pero perdió capacidad para identificar churn.

La combinación completa tampoco dio una mejora consistente. Recomendamos conservar el modelo actual y monitorearlo mensualmente; si el negocio prioriza captar más clientes en riesgo y puede asumir más contactos innecesarios, podemos evaluar el ajuste de decisión como alternativa operativa.

Si recibimos una auditoría, podremos responder con evidencia reproducible: versión del modelo y datos, tamaño y fecha de la muestra, tasas de acierto y error, resultados separados por género, brechas entre grupos, comparación de las alternativas evaluadas y la decisión tomada. Conservaremos estos resultados para respaldar cada cifra.

Quedo atento a cualquier pregunta.
