# Sustentación U6 — Monitoreo del pipeline de retención

**Grupo 02 · Computación en la Nube para IA · Universidad Icesi**  
**Integrantes:** Gabriel Ernesto Escobar A00399291 · David Artunduaga Penagos A00396342 · Luis Manuel Rojas A00399289

## Idea central

El cliente observa que las campañas funcionan peor, pero el modelo todavía
devuelve predicciones. Por eso no basta con mirar si la API responde: hay que
revisar calidad de datos, cambio de población, validez del modelo y desempeño
de la campaña.

Con las diez semanas analizadas encontramos evidencia de que la población y el
formato de los datos cambiaron, especialmente en las dos últimas semanas. No
podemos afirmar todavía que el modelo perdió precisión real porque aún no
tenemos las etiquetas finales de churn de estos clientes.

### Resultados principales

| Evidencia | Resultado |
|---|---:|
| Filas procesadas | 703 |
| Predicciones válidas | 667 |
| Filas en cuarentena | 36 |
| Tasa global de rechazo | 5,12% |
| Rechazo semana 2026-08-24 | 13,19% |
| Rechazo semana 2026-08-31 | 30,30% |
| Errores de campo | 37 |
| Errores por valores nuevos de `PaymentMethod` | 27 de 37 = 73% |

El modelo no se rompió: el contrato rechazó datos que no podía interpretar y
el análisis detectó que la población reciente se aleja de la población de
entrenamiento.

## Decisión sobre `BancoPago`

`BancoPago` **no se agrega como feature del modelo todavía**.

La columna aparece por primera vez el 2026-07-27. De las 703 filas, 444 tienen
valor y 259 están vacías. Además, la misma entidad aparece con variantes como
`Bancolombia`, `Bancolombia S.A.`, `bancolombia`, `BANCOLOMBIA`, `Banco de
Bogota` y `BCO BOGOTA`. La canonicalización reduce 12 variantes originales a 6
categorías operativas, pero eso no significa que la columna ya esté lista para
entrenar.

Agregarla ahora produciría tres problemas:

1. El modelo registrado no fue entrenado con esa variable; habría que cambiar
   el pipeline de features, reentrenar, recalibrar el threshold y volver a
   comparar AUC, recall y costo.
2. La cobertura es temporalmente desigual: las primeras cuatro semanas tienen
   0% de captura y luego la cobertura sube aproximadamente a 91%–99%. El valor
   faltante está relacionado con la fecha, por lo que puede introducir sesgo
   de selección.
3. Las categorías todavía no tienen un contrato de datos estable. Un banco
   mal escrito podría convertirse en una categoría nueva, en vez de representar
   al banco correcto.

La decisión defendible es **no usarla como feature, sí monitorearla y
canonicalizarla para análisis operativo**. Antes de incorporarla se debe pedir
al cliente un diccionario oficial, una regla de captura obligatoria, una
política para faltantes y suficientes etiquetas de churn para medir si agrega
señal fuera de muestra.

Esto no significa descartar la columna para siempre. Significa separar calidad
de datos de entrenamiento: primero se gobierna la captura; después se evalúa
su valor incremental contra el modelo ganador.

`SeniorCitizen` tampoco participa en este pipeline: fue removida del modelo
por la instrucción del curso. La variable protegida de la auditoría anterior
fue `gender`, pero en esta unidad la pregunta principal es monitoreo de calidad,
drift y desempeño en producción.

## Directriz 1 — El umbral que ya tenemos

### Argumentación

El umbral de rechazo no debe ser un número arbitrario. Usamos las primeras
cuatro semanas como baseline, porque representan el comportamiento normal
observado antes de que apareciera `BancoPago` y antes del deterioro de las
últimas semanas.

En esas semanas:

- media de rechazo: **0,5%**;
- desviación estándar: **1,0 puntos porcentuales**;
- umbral recomendado: media + 2 desviaciones = **2,5%**;
- umbral alternativo más conservador: media + 3 desviaciones = **3,5%**.

Elegimos 2,5% porque detecta cambios relevantes con una tolerancia razonable a
variaciones normales. Es una primera calibración: con más semanas se debe
recalcular, idealmente con intervalos bootstrap.

### Respuestas a las preguntas del enunciado

**¿Sigue siendo correcto el número?**  
Sí, como umbral operativo inicial. La evidencia lo valida: las semanas
2026-08-24 y 2026-08-31 superan 2,5% con tasas de 13,19% y 30,30%.

**¿Qué habría pasado con el doble o la mitad?**  
Interpretamos “el doble” como 5% y “la mitad” como 1,25%:

- con **5%**, todavía se detectan las dos últimas semanas;
- con **1,25%**, se detectan también 2026-08-17 (1,41%), además de las dos
  últimas, pero se vuelve más sensible al ruido;
- con **20%**, solo se detectaría 2026-08-31 y se perdería la primera señal de
  deterioro.

La conclusión es que el 20% habría alertado demasiado tarde y el 1,25% podría
generar fatiga de alertas. El 2,5% permite actuar desde la primera ruptura
clara del comportamiento histórico.

### Qué se implementó

El DAG calcula la tasa por lote, la compara con `UMBRAL_CUARENTENA_PCT=2.5`
y escribe una advertencia `[WARN]` cuando la supera. El lote no se descarta
automáticamente por superar este umbral; queda registrado y continúa para que
podamos analizar qué ocurrió.

## Directriz 2 — Lo que hay dentro de la cuarentena

### Argumentación

Una tasa alta solo dice que algo falló. Para responder al cliente hay que
identificar el campo, el tipo de error y la fecha en que empezó.

La cuarentena contiene 36 filas y 37 errores de campo porque una fila puede
tener más de un problema. La distribución es:

| Campo o tipo | Errores |
|---|---:|
| `PaymentMethod` con categoría no permitida | 27 |
| `MonthlyCharges` vacío o no numérico | 7 |
| `tenure` vacío o no entero | 3 |

El problema crece al final del archivo: las últimas dos semanas acumulan 12 y
21 errores. En `PaymentMethod` aparecen `PSE`, `PayPal`, `Digital wallet`,
`Corporate billing` y `Credit card (manual)`, categorías que no existían en el
contrato original.

### Respuestas a las preguntas del enunciado

**¿Qué falló exactamente?**  
Principalmente el catálogo de `PaymentMethod`; en menor proporción faltantes o
valores no numéricos de `MonthlyCharges` y `tenure`.

**¿En qué campos y desde cuándo?**  
Los errores aislados aparecen desde las primeras semanas, pero el salto fuerte
empieza el 2026-08-24 y continúa el 2026-08-31. El 73% de los errores de campo
corresponde a `PaymentMethod`.

**¿Es lo mismo que fallaba al principio?**  
No completamente. Al principio predominan errores aislados de calidad
numérica. Al final aparece un problema semántico nuevo: el CRM envía valores
legítimos para el negocio, pero desconocidos para el enum de la API.

**¿Está bien diseñada la cuarentena como texto crudo?**  
No es el diseño ideal. Guardar el registro crudo permite reconstruir el caso,
pero obliga a reparsearlo para agrupar errores. La mejora es guardar, además,
`error_detail` como JSON estructurado con campo, tipo y mensaje. En el DAG
corregido, BigQuery recibe `error_detail` y `raw` como columnas JSON.

### Qué se implementó

El DAG conserva los registros rechazados, el estado HTTP, el tipo de error, el
detalle y el lote. La página **Cuarentena** del dashboard permite observar la
distribución por semana y campo en lugar de mostrar únicamente un contador.

## Directriz 3 — Lo que no está en la cuarentena

### Argumentación

Los registros aceptados también pueden evidenciar un cambio. Por eso usamos
dos referencias:

1. **Training de U4:** responde si la población actual todavía se parece a la
   población con la que aprendió el modelo.
2. **Primeras cuatro semanas del archivo:** responde si la semana actual se
   parece al comportamiento inicial del mismo envío del cliente.

No son referencias intercambiables. El training es la referencia de validez
histórica del modelo; las primeras semanas son una referencia operacional
reciente.

### Respuestas a las preguntas del enunciado

**¿Qué encontramos contra el training?**  
En las últimas semanas el `PSI` contra U4 es extremo:

- `tenure`: **3,93 → 5,04 → 8,16** entre 2026-08-17 y 2026-08-31;
- `MonthlyCharges`: **1,57 → 3,75 → 5,09** en el mismo tramo.

Ambos valores están muy por encima de 0,25, el umbral de drift material usado
como referencia.

**¿Qué encontramos contra las primeras semanas?**  
Las primeras semanas son relativamente estables, pero la distancia crece
fuertemente desde agosto. Por eso las dos comparaciones cuentan la misma
historia direccional: la población reciente se separó del inicio del archivo y
del training. Las magnitudes no son idénticas porque cada baseline representa
una población diferente.

**¿Qué variable sirve como control?**  
`Contract` no muestra el mismo crecimiento sostenido. Esto sugiere que no
estamos viendo simplemente ruido en todas las columnas, sino un cambio dirigido
en algunas partes de la población.

### Qué se implementó

El análisis calcula drift por semana contra ambos baselines. La página **Drift**
presenta PSI y KS para variables numéricas y la comparación categórica de
`Contract`. Esto permite diferenciar “la fuente cambió” de “el modelo está
recibiendo exactamente la población aprendida”.

## Directriz 4 — Cómo se mide un cambio

### Objetivo explicado de forma sencilla

La directriz 4 busca responder dos preguntas:

1. **¿Cómo comparamos cambios de variables que usan unidades distintas?**
   `tenure` se mide en meses, mientras `MonthlyCharges` se mide en dinero. No
   podemos comparar sus diferencias crudas, como “cambió 10”, porque 10 meses y
   10 dólares no significan lo mismo.
2. **¿Cuándo el cambio es suficientemente grande para alertar?** No se debe
   elegir el límite a dedo; se necesita una regla común y defendible.

En otras palabras, la directriz 4 convierte cambios con escalas distintas en
una medida comparable de cambio de distribución y calcula límites que separan
variación normal de drift material.

### Argumentación y método

Usamos medidas basadas en distribuciones, no diferencias de promedios:

- **PSI** para medir cuánto cambió la distribución de una feature;
- **KS-test** para complementar el análisis de variables numéricas;
- **chi-cuadrado** para comparar categorías como `Contract`.

Como guía interpretable:

- PSI menor que 0,10: población estable;
- PSI entre 0,10 y 0,25: cambio leve, continuar monitoreando;
- PSI mayor que 0,25: cambio material, investigar y considerar reentrenar;
- KS con `p < 0,05`: evidencia estadística de cambio en la distribución
  numérica.

El 0,25 no es una ley universal: es una convención de scorecards. Por eso lo
complementamos con KS y con la comparación contra dos baselines.

### Respuestas a las preguntas del enunciado

**¿Cómo se comparan variables con escalas diferentes?**  
Comparando sus distribuciones mediante PSI/KS, que no dependen directamente de
que una variable esté expresada en meses o pesos.

**¿Cómo se calcula el límite?**  
Para la tasa de rechazo, el límite se calculó desde la media y desviación del
baseline: 0,5% + 2×1,0% = 2,5%. Para drift usamos la referencia PSI 0,25 y
`p < 0,05` en KS como reglas de screening, reconociendo que deben recalibrarse
con más historia.

**¿Cómo se consideran los lotes de tamaños distintos?**  
Se calcula la tasa, no solo el número absoluto de rechazos. En drift se reporta
el tamaño de cada lote (`n`) junto con PSI y KS. Un lote pequeño puede producir
estimaciones más variables, por lo que no se interpreta una sola semana sin
mirar la tendencia.

### Qué se implementó

El script `u6/analysis/run_analysis.py` calcula las métricas por semana y
genera `hallazgos_u6.json`. El dashboard muestra el método, los umbrales, el
tamaño de los lotes y la evolución, evitando mezclar escalas o confundir un
lote grande con un cambio de negocio.

## Directriz 5 — La columna que no estaba

### Argumentación

`BancoPago` es una señal potencialmente útil, pero todavía es una fuente de
calidad y gobierno de datos, no una feature lista para producción. La columna
aparece a mitad del archivo, tiene faltantes estructurales y presenta variantes
de escritura.

### Respuestas a las preguntas del enunciado

**¿Qué hacemos con ella?**  
No la usamos para inferencia todavía. La conservamos para análisis de cobertura,
canonicalizamos las variantes para reportes y pedimos al cliente que
estandarice la captura.

**¿Por qué no imputamos o eliminamos filas?**  
Imputar un banco sin evidencia puede inventar información. Eliminar las 259
filas sin banco introduce sesgo porque esos faltantes dependen de la fecha de
captura. Ninguna opción arregla el problema de origen.

**¿Qué tendría que pasar para usarla en el modelo?**  
Definir categorías oficiales, medir cobertura estable, definir el tratamiento
de faltantes, entrenar con datos históricos suficientes y evaluar el aporte
incremental en AUC, recall, costo y equidad sobre un conjunto temporal fuera de
muestra.

### Qué se implementó

La página **BancoPago** muestra cobertura por semana, variantes crudas,
variantes canonicalizadas y las alternativas descartadas. El DAG no envía
`BancoPago` al endpoint y el modelo no lo usa como feature.

## Directriz 6 — La respuesta al cliente

### Qué pasó

La tasa de rechazo pasa de 0%–2% en las primeras semanas a 13,19% y 30,30% en
las dos últimas. Al mismo tiempo aparecen categorías nuevas de `PaymentMethod`
y el PSI de `tenure` y `MonthlyCharges` aumenta de forma extrema.

La explicación más consistente con la evidencia es un cambio de población
relacionado con el CRM: nuevos medios de pago, un criterio nuevo de selección
de clientes en riesgo o una campaña dirigida a clientes con menor antigüedad y
mayor cargo mensual. Esto es una hipótesis de negocio, no una afirmación causal
definitiva.

### Qué significa

El pipeline no demuestra todavía que el modelo tenga peor AUC o recall. No hay
labels de churn de estas diez semanas. Sí demuestra que el modelo recibe datos
fuera o alejados de la distribución con la que fue entrenado y que el contrato
no reconoce valores nuevos.

### Qué recomendamos

1. **Inmediato:** ampliar el contrato de `PaymentMethod` con un catálogo
   validado, sin agregar `BancoPago` al modelo todavía.
2. **Mientras se confirma:** marcar como fuera de dominio el segmento de
   clientes nuevos o con medios de pago nuevos y evitar decisiones automáticas
   de alto impacto sobre ese segmento.
3. **Cuando lleguen labels:** medir desempeño reciente, calibración y costo por
   segmentos; reentrenar con las últimas semanas si el deterioro se confirma.
4. **Operación continua:** mantener el DAG, la cuarentena y el monitoreo de
   drift; añadir un `drift_check` automático si se quiere convertir el
   indicador PSI en una alerta operativa.

## Pregunta central: ¿modelo, campaña o cambio en clientes?

No lo determinaríamos con una sola métrica. Haríamos un diagnóstico en cuatro
capas:

| Capa | Qué revisar | Qué concluiría |
|---|---|---|
| Calidad de entrada | Rechazos, campos, categorías nuevas, faltantes y fechas | Si el problema es CRM/contrato o datos mal formados |
| Cambio de clientes | PSI, KS, chi-cuadrado y comparación contra training y primeras semanas | Si cambió la población que recibe el modelo |
| Modelo | Con labels reales: AUC, recall, precision, calibración, threshold y métricas por segmento | Si el modelo sigue separando y ordenando bien el riesgo |
| Campaña | Tratamiento/control, exposición, oferta, canal, costo y churn observado | Si la acción de retención dejó de funcionar aunque el score sea correcto |

El orden práctico sería:

1. Verificar que los registros enviados representen realmente a los clientes y
   que el contrato no esté rechazando categorías válidas.
2. Comparar la distribución actual con U4 y con las primeras semanas. En este
   caso ya observamos drift fuerte en `tenure` y `MonthlyCharges`.
3. Pedir las etiquetas finales de churn y el resultado de cada campaña. Con
   esas etiquetas se compara el modelo actual contra su validación histórica y
   se revisa la calibración del score.
4. Separar el efecto del modelo del efecto de la campaña mediante un grupo de
   control o una prueba A/B. Si el control y el tratado empeoran por igual,
   puede ser población o mercado; si solo empeora el tratado, hay que revisar
   oferta, canal, ejecución o segmentación; si el score deja de ordenar el
   riesgo, el problema es del modelo o del cambio de población.

### Lectura actual para nuestro caso

Con los datos disponibles, la evidencia apunta primero a **cambio de clientes y
del proceso del CRM**, no a una falla interna de la API: hay drift fuerte,
categorías nuevas y una tasa de rechazo creciente. Sin labels y sin información
de tratamiento de campañas no es válido afirmar todavía que la campaña o el
modelo perdieron efectividad. Los datos que pediríamos son: fecha de release de
nuevos medios de pago, versión del criterio CRM de “en riesgo”, asignación de
campaña/control, oferta y canal, churn observado y fecha de disponibilidad de
esas etiquetas.

## Alertas configuradas

### Alertas operativas actuales

| Alerta | Regla | Acción |
|---|---|---|
| Rechazo elevado | `tasa_rechazo > 2,5%` | El DAG imprime `[WARN]`, registra la tasa y continúa para analizar la cuarentena |
| Quality gate severo | `tasa_rechazo > 50%` | El DAG marca la corrida como `FAILED` y detiene el flujo posterior |

El 2,5% es el umbral calibrado con las primeras cuatro semanas. El 50% es un
freno de seguridad para una falla catastrófica; no reemplaza el umbral de
monitoreo. En los datos analizados se disparó la advertencia de 2,5% en las
semanas 2026-08-24 y 2026-08-31, pero no el quality gate de 50%.

### Indicadores de monitoreo que quedaron calculados

- `PSI > 0,25`: drift material de referencia;
- KS con `p < 0,05`: señal estadística de cambio numérico;
- chi-cuadrado para cambios categóricos;
- cobertura y variantes de `BancoPago`;
- distribución de errores de cuarentena por semana y campo.

Importante para la sustentación: PSI, KS y chi-cuadrado están calculados y
visibles en el dashboard, pero en esta versión el DAG no falla automáticamente
por PSI. Convertir PSI en un quality gate automático es una mejora planificada;
la alerta que detiene actualmente el DAG es la tasa de rechazo mayor que 50%.

## Implementación resumida del proyecto

1. El CSV de diez semanas se almacena en GCS.
2. El DAG lee el lote, valida el contrato y llama a la API privada U5.
3. Las respuestas 200 van a `resultados`; las respuestas inválidas o fallos de
   parseo van a `cuarentena`.
4. BigQuery conserva ambas tablas con `run_id`, archivo, lote, detalle y
   timestamps para trazabilidad.
5. El análisis offline calcula calibración del umbral, errores de cuarentena,
   drift contra training y baseline, y análisis de `BancoPago`.
6. Streamlit presenta la evidencia y una respuesta ejecutiva al cliente.

La conclusión de negocio es: **mantener el modelo para la población conocida
con monitoreo activo, corregir el contrato de entrada, no agregar `BancoPago`
todavía y reentrenar solo después de obtener datos etiquetados y estabilizar la
captura.**
