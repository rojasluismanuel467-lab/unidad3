"""D5 — Que hacer con la columna nueva BancoPago."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "analysis" / "hallazgos_u6.json") as f:
    H = json.load(f)
b = H["D5_banco_pago"]

st.title(":bank: D5 — La columna nueva `BancoPago`")

st.markdown(
    """
El cliente avisa: *"desde hace unas semanas empezamos a capturar el banco desde
el cual nos pagan. Es un campo nuevo, asi que en los primeros envios viene vacio
y aparece a partir de cierta fecha. Sabemos que la captura no ha sido perfecta."*

Hay que decidir que hacer con esta columna. **No hay una respuesta correcta —
hay decisiones defendibles y decisiones improvisadas.**
"""
)

col1, col2, col3 = st.columns(3)
col1.metric("Primera semana con datos", b["primera_semana_con_datos"])
col2.metric("Filas con BancoPago", b["n_valores_no_nulos"])
col3.metric("Filas sin BancoPago (nulls)", b["n_valores_nulos"])

st.markdown("---")

st.subheader("Cobertura semana a semana")
cov = pd.DataFrame(b["cobertura_por_semana"])
col1, col2 = st.columns([2, 1])
with col1:
    st.bar_chart(cov.set_index("fecha_lote")["cobertura_pct"])
with col2:
    st.dataframe(cov, use_container_width=True, hide_index=True)

st.info(
    "La cobertura salta de 0% a 94% entre 2026-07-20 y 2026-07-27 (arranque). "
    "Despues se estabiliza entre 92-98%."
)

st.markdown("---")

# ------------------------- Variantes -------------------------
st.header("Captura inconsistente")

col1, col2 = st.columns(2)
with col1:
    st.metric("Variantes originales", b["n_variantes_originales"])
    st.subheader("Top 15 valores RAW")
    st.dataframe(
        pd.DataFrame(b["top_variantes_raw"].items(),
                     columns=["valor_raw", "n"]),
        use_container_width=True, hide_index=True,
    )

with col2:
    st.metric("Despues de canonicalizacion", b["n_variantes_despues_canon"])
    st.subheader("Top valores CANONICALIZADOS")
    st.dataframe(
        pd.DataFrame(b["top_valores_canonicalizados"].items(),
                     columns=["banco_canon", "n"]),
        use_container_width=True, hide_index=True,
    )

st.warning(
    "El mismo banco aparece bajo hasta 3 variantes:\n"
    "- **Bancolombia** / Bancolombia S.A. / bancolombia\n"
    "- **Banco de Bogota** / BCO BOGOTA\n"
    "- **Davivienda** / davivienda\n\n"
    "Nuestra funcion de canonicalizacion reduce las variantes de "
    f"**{b['n_variantes_originales']} a {b['n_variantes_despues_canon']}**."
)

st.markdown("---")

# ------------------------- Decision -------------------------
st.header(":dart: Decision defendible")
st.success(b["decision_defendible"])

st.markdown("""
### Alternativas que descartamos (con justificacion)

**A) Imputar los nulos con el banco mas frecuente**
- ❌ Metria sesgo sistematico: el cliente sin BancoPago no es aleatorio.
- ❌ Las primeras 4 semanas son 100% nulls porque la columna no existia; imputarlas
  contamina el baseline de drift.

**B) Descartar todas las filas sin BancoPago**
- ❌ Perderiamos 259 clientes (37% del CSV), casi todos de las primeras 4 semanas.
- ❌ Rompe la promesa del pipeline de scorear todo lo que pasa el contrato.

**C) Agregar BancoPago como feature del modelo YA**
- ❌ El modelo actual no la conoce (features cerradas en U3/U4). Agregarla
  requiere re-entrenar con nueva feature engineering.
- ❌ Con captura tan sucia, el modelo aprenderia los typos como categorias
  distintas.

**D) Ignorar como feature + canonicalizar para uso operativo** ✅ (elegida)
- ✓ No rompe el contrato del modelo.
- ✓ Permite dashboards y analisis operativo.
- ✓ Deja documentado el problema de captura al cliente sin dependencia tecnica.
""")
