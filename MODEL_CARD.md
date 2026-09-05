# Model Card — XGBoost Churn (Telco), auditado sobre `gender`

Basado en Mitchell et al. 2019 (*Model Cards for Model Reporting*).

## Model details
- **Algoritmo**: XGBoost Classifier (`n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42`).
- **Features**: 16 columnas tras one-hot (`gender`, `Partner`, `Dependents`, `tenure`, `Contract`, `PaymentMethod`, `MonthlyCharges`, `InternetService`, `OnlineSecurity`, `TechSupport`).
- **Variable protegida auditada**: `gender` (binaria Male/Female en el dataset). `SeniorCitizen` fue removido por instrucción académica.
- **Versión**: iteración de U3 — 2026.

## Intended use
- **Uso previsto**: priorizar clientes para campañas proactivas de retención en Telco.
- **Fuera de alcance**: decisiones automatizadas irreversibles (cancelación de servicio, cambio de tarifa sin intervención humana). Si se usa así, cae bajo GDPR Art. 22.

## Datos
- IBM Telco Customer Churn, 7043 clientes.
- Split: 80/20 estratificado por `Churn` (`random_state=42`).
- **Etiqueta**: `Churn` observado por la empresa — hay posible *label bias* (solo capturamos cancelaciones detectadas).
- **Limitación de `gender`**: solo Male/Female. No hay categoría "no declarado" ni no-binaria.

## Métricas — configuración recomendada (baseline)
| Métrica | Valor |
|---|---|
| AUC-ROC | 0.840 |
| Recall (Churn) | 0.519 |
| Precision (Churn) | 0.664 |
| DPD (gender) | 0.010 |
| EOD (gender) | 0.052 |
| Recall Female / Male | 0.544 / 0.492 |
| Precision Female / Male | 0.719 / 0.610 |

## Ethical considerations
- **Métrica prima declarada**: **EOD (Equal Opportunity Difference)** — en retención el daño principal es *quality-of-service* (clientas realmente en riesgo no reciben la oferta).
- **Trade-offs conocidos** (Kleinberg 2016, Pleiss 2017, Chouldechova 2017): DPD, EOD y calibración no son simultáneamente satisfacibles cuando las tasas base difieren. Optimizamos EOD y aceptamos el trade-off.
- **Threshold-por-grupo** (implementado como técnica individual): posible *disparate treatment* explícito (jurisprudencia estilo *Ricci v. DeStefano*). No se recomienda en producción sin revisión legal.
- **`fairness through unawareness` no es solución**: `gender` se mantiene como feature; removerlo no impide que proxies reintroduzcan el sesgo.

## Caveats and recommendations
- Ningún test de proxy leakage sobre las features candidatas superó AUC=0.508 vs. `gender` — cero riesgo de proxy en este dataset.
- Con `gender` casi parejo (DPD/EOD < 0.06 desde el baseline), aplicar mitigación agresiva **degrada utilidad sin ganancia real de equidad**.
- **Recomendación operacional**: usar el modelo base sin mitigación adicional; monitorear DPD/EOD mensualmente en producción; re-auditoría trimestral (NIST AI RMF Measure 2.11).
