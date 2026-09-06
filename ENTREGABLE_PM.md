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

Terminamos la auditoría del modelo de churn usando `gender` como único atributo protegido. Primero medimos el modelo actual y luego probamos reweighting, entrenamiento adversarial, ajuste de decisión y su combinación.

`gender` ya presentaba poca disparidad en el modelo actual (DPD=0.010; EOD=0.052). Reweighting redujo EOD a 0.035, mantuvo AUC en 0.839 y elevó recall de 0.519 a 0.794. El ajuste de decisión logró DPD=0.003, EOD=0.035 y recall=0.799; su AUC de referencia se mantuvo en 0.840.

Adversarial redujo EOD a 0.042, pero AUC cayó de 0.840 a 0.806 y recall quedó en 0.530. Combinar técnicas no valió la pena: EOD subió a 0.095 y AUC fue 0.815, aunque recall llegó a 0.730.

Recomendamos conservar el modelo actual y monitorearlo mensualmente. Si el negocio prioriza captar más clientes en riesgo y puede asumir más contactos innecesarios, el ajuste de decisión es la alternativa a evaluar. Para una auditoría conservamos versión, datos, errores por género y comparación de modelos.

Quedo atento a cualquier pregunta.
