# RESULTADOS — Auditoría de sesgo por `gender`

## Tabla comparativa

| Config | Recall (Churn) | Precision | AUC | DPD (gender) | EOD (gender) |
|---|---|---|---|---|---|
| Base (sin mitigar) | 0.519 | 0.664 | 0.84 | 0.01 | 0.052 |
| Reweighting | 0.794 | 0.514 | 0.839 | 0.014 | 0.035 |
| Adversarial (media±std, 5 seeds) | 0.530 ± 0.025 | 0.609 ± 0.034 | 0.806 ± 0.006 | 0.048 ± 0.019 | 0.042 ± 0.019 |
| Threshold adjustment | 0.799 | 0.525 | 0.84 | 0.003 | 0.035 |
| Combinado (rw→adv→thr) | 0.73 | 0.465 | 0.815 | 0.02 | 0.095 |

- DPD/EOD: más cerca de 0 = más equitativo.
- Adversarial reporta media±std sobre 5 seeds (Zhang et al. 2018).
- AUC del combinado corresponde al predictor adversarial subyacente (el ThresholdOptimizer no expone probas comparables).

## Respuesta al PM

**Asunto: Auditoría de sesgo por género — modelo de churn**

Hola,

Auditamos el modelo con `gender` como variable protegida y aplicamos las tres técnicas por separado y combinadas.

**Gender ya estaba parejo desde el modelo base.** DPD=0.010, EOD=0.052 — ambos muy por debajo del umbral de 0.10 que Fairlearn considera aceptable. Tu intuición era correcta: no hay un problema visible de discriminación de género que necesite mitigarse.

**Qué pasó al aplicar las técnicas de todos modos** (como pediste). Reweighting subió recall de 0.52 a 0.79 y mantuvo AUC intacto (0.839 vs 0.840), a costa de precisión (0.66→0.51). Threshold-adjustment bajó DPD a 0.003 con recall=0.80, pero ojo — legalmente usa umbrales distintos por género (posible *disparate treatment*, revisar con legal). Adversarial degradó AUC ~4 puntos sin ganancia clara.

**Combinar (reweighting→adversarial→threshold) no valió la pena:** recall=0.73, DPD=0.020, EOD=0.095. Añade complejidad sin mejora consistente sobre reweighting solo.

**Recomendación:** no aplicar mitigación adicional sobre género en producción. Monitorear DPD/EOD mensualmente. El sesgo real observable estaba en SeniorCitizen (removido esta iteración por instrucción académica) — vale la pena revisarlo si vuelve al alcance.
