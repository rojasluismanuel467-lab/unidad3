"""Design tokens + helpers compartidos por app.py y las 6 paginas.

Motivacion (buenas practicas UI/UX aplicadas):
- Un solo source of truth para tokens (colores, spacing, typography).
- Sidebar y headers CONSISTENTES entre paginas (Nielsen H4: consistencia).
- Data-ink ratio alto (Tufte): sin adornos, todo elemento comunica.
- Color semantico, no decorativo (solo semaforos donde aporta significado).
- Progressive disclosure via helpers (`section_header`, `stat_row`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import streamlit as st

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
COLOR_INK = "#111827"       # texto principal
COLOR_MUTED = "#6b7280"     # texto secundario / captions
COLOR_BORDER = "#e5e7eb"    # dividers, bordes
COLOR_BG = "#ffffff"        # fondo
COLOR_ACCENT = "#0f172a"    # acento sobrio (near-black)
COLOR_OK = "#065f46"
COLOR_WARN = "#92400e"
COLOR_FAIL = "#991b1b"


# ---------------------------------------------------------------------------
# Layout + tema
# ---------------------------------------------------------------------------
def apply_page_config(*, page_title: str) -> None:
    """Configura layout, favicon-y-friends. Debe llamarse antes de cualquier st.*."""
    st.set_page_config(
        page_title=page_title,
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get Help": None,
            "Report a bug": None,
            "About": "Monitor del pipeline U6 — Grupo 2 — Universidad Icesi",
        },
    )
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = f"""
<style>
/* Layout: max-width tipo Vercel/Linear, spacing generoso */
.block-container {{
    padding-top: 2.5rem;
    padding-bottom: 4rem;
    max-width: 1150px;
}}

/* Typography: system stack, weight consistency, letter-spacing negativo en headings */
html, body, [class*="css"] {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
}}
h1 {{
    font-weight: 600;
    letter-spacing: -0.025em;
    color: {COLOR_INK};
    font-size: 2rem;
    margin-bottom: 0.25rem;
    line-height: 1.15;
}}
h2 {{
    font-weight: 600;
    letter-spacing: -0.015em;
    color: {COLOR_INK};
    font-size: 1.35rem;
    margin-top: 2.5rem;
    padding-top: 1.25rem;
    border-top: 1px solid {COLOR_BORDER};
}}
h3 {{
    font-weight: 600;
    color: {COLOR_INK};
    font-size: 1.05rem;
    margin-top: 1.5rem;
}}

/* Captions con color muted uniforme */
[data-testid="stCaptionContainer"], .stCaption {{
    color: {COLOR_MUTED};
    font-size: 0.85rem;
}}

/* Metrics: labels caps + gris, valores grandes */
[data-testid="stMetricLabel"] {{
    font-size: 0.72rem;
    color: {COLOR_MUTED};
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 500;
}}
[data-testid="stMetricValue"] {{
    font-size: 1.85rem;
    font-weight: 600;
    color: {COLOR_INK};
    line-height: 1.15;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.8rem;
}}

/* Sidebar: mismo fondo que main, sin sombra dura */
[data-testid="stSidebar"] {{
    background-color: #fafafa;
    border-right: 1px solid {COLOR_BORDER};
}}
[data-testid="stSidebar"] .block-container {{
    padding-top: 1.75rem;
    padding-left: 1.5rem;
    padding-right: 1.5rem;
}}
[data-testid="stSidebarNav"] {{
    padding-top: 0.5rem;
}}
[data-testid="stSidebarNav"] a {{
    font-size: 0.88rem;
    padding: 0.35rem 0.75rem;
    border-radius: 6px;
}}
[data-testid="stSidebarNav"] a:hover {{
    background-color: rgba(15, 23, 42, 0.04);
}}

/* Dataframes: bordes sutiles, header con contraste bajo */
[data-testid="stDataFrame"] {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    overflow: hidden;
}}

/* Alerts: quita el fondo pesado, deja solo el color de la barra izquierda */
.stAlert {{
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.9rem;
}}

/* Expander: header limpio */
[data-testid="stExpander"] summary {{
    font-weight: 500;
    font-size: 0.95rem;
}}

/* Ocultar chrome de Streamlit sobrante */
footer, [data-testid="stDecoration"], #MainMenu {{
    display: none !important;
}}
[data-testid="stToolbar"] {{
    display: none;
}}

/* Wordmark del proyecto en el sidebar */
.brand-wordmark {{
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: {COLOR_ACCENT};
    margin-bottom: 0.25rem;
}}
.brand-tag {{
    font-size: 0.72rem;
    color: {COLOR_MUTED};
    margin-bottom: 1.25rem;
}}
</style>
"""


# ---------------------------------------------------------------------------
# Sidebar branding — llamar en cada pagina para consistencia
# ---------------------------------------------------------------------------
def sidebar_branding() -> None:
    """Wordmark + tagline del proyecto arriba de la navegacion del sidebar."""
    with st.sidebar:
        st.markdown(
            """<div class="brand-wordmark">MONITOR U6</div>
<div class="brand-tag">Pipeline de retención · Grupo 2</div>""",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Header de pagina — un patron unico
# ---------------------------------------------------------------------------
def page_header(title: str, caption: str, *, directriz: str | None = None) -> None:
    """H1 + caption uniforme.

    directriz: tag corto (e.g. "D3+D4") que aparece antes del caption.
    """
    st.title(title)
    if directriz:
        st.caption(f"**{directriz}** · {caption}")
    else:
        st.caption(caption)


# ---------------------------------------------------------------------------
# Fila de KPIs — helper para grid de metrics con formato consistente
# ---------------------------------------------------------------------------
def kpi_row(metrics: Iterable[tuple[str, str, str | None]]) -> None:
    """Renderiza una fila de KPIs.

    metrics: iterable de (label, value, help_text|None).
    """
    metrics = list(metrics)
    cols = st.columns(len(metrics))
    for col, (label, value, help_text) in zip(cols, metrics):
        col.metric(label, value, help=help_text)


# ---------------------------------------------------------------------------
# Footer con trust signals
# ---------------------------------------------------------------------------
def footer(fuentes: list[str] | None = None) -> None:
    """Footer con fuente de datos + timestamp de render.

    Trust signal (Nielsen H1: system status visibility).
    """
    st.markdown("<br>", unsafe_allow_html=True)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    partes = [f"Renderizado {ahora}"]
    if fuentes:
        partes.append("Fuentes: " + " · ".join(f"`{f}`" for f in fuentes))
    st.caption(" · ".join(partes))
