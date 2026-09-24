from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "EVIDENCIAS_U5.pdf"
IMG = ROOT / "evidencias_u5"
OUT.parent.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
title = ParagraphStyle(
    "EvidenceTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=19, leading=23, alignment=TA_CENTER, textColor=colors.HexColor("#17365D"),
    spaceAfter=16,
)
subtitle = ParagraphStyle(
    "EvidenceSubtitle", parent=styles["Normal"], fontSize=10.5, leading=15,
    alignment=TA_CENTER, textColor=colors.HexColor("#404040"), spaceAfter=14,
)
section = ParagraphStyle(
    "EvidenceSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=14, leading=18, textColor=colors.HexColor("#17365D"), spaceBefore=8, spaceAfter=8,
)
body = ParagraphStyle(
    "EvidenceBody", parent=styles["BodyText"], fontSize=10.5, leading=15,
    textColor=colors.HexColor("#222222"), spaceAfter=10,
)
summary = ParagraphStyle(
    "EvidenceSummary", parent=body, backColor=colors.HexColor("#EAF2F8"),
    borderColor=colors.HexColor("#B8CCE4"), borderWidth=0.5, borderPadding=8,
)
caption = ParagraphStyle(
    "EvidenceCaption", parent=styles["Normal"], fontSize=8.5, leading=11,
    alignment=TA_CENTER, textColor=colors.HexColor("#666666"), spaceBefore=4, spaceAfter=10,
)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E2F3"))
    canvas.line(doc.leftMargin, 0.52 * inch, letter[0] - doc.rightMargin, 0.52 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(doc.leftMargin, 0.34 * inch, "Evidencias U5 · Grupo 02 · computacionnube20262")
    canvas.drawRightString(letter[0] - doc.rightMargin, 0.34 * inch, f"Página {doc.page}")
    canvas.restoreState()


def evidence_image(filename, caption_text):
    path = IMG / filename
    image = Image(str(path))
    max_width = 7.0 * inch
    max_height = 4.35 * inch
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight, 1.0)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    image.hAlign = "CENTER"
    return [image, Paragraph(caption_text, caption)]


story = [
    Paragraph("Evidencias de despliegue U5", title),
    Paragraph("Servicio de churn · Grupo 02", subtitle),
    Paragraph(
        "<b>Proyecto GCP:</b> computacionnube20262 &nbsp;&nbsp; "
        "<b>Servicio:</b> u5-g02-cr-20260917 &nbsp;&nbsp; "
        "<b>Región:</b> us-central1",
        subtitle,
    ),
    Paragraph(
        "<b>Integrantes:</b> Gabriel Escobar Bravo · David Artunduaga Penagos · "
        "Luis Manuel Rojas",
        subtitle,
    ),
    Spacer(1, 0.25 * inch),
    Paragraph(
        "Este documento reúne las evidencias del despliegue del servicio FastAPI en Cloud Run, "
        "la disponibilidad del endpoint de salud, una predicción válida y la validación de una "
        "solicitud incorrecta.",
        summary,
    ),
    Spacer(1, 0.3 * inch),
    Paragraph("Modelo utilizado: u4_g02_mdl_20260914 (MLP ganador)", body),
    PageBreak(),
]

sections = [
    (
        "1. Servicio activo en Cloud Run",
        "La salida de <font name='Courier'>gcloud run services list</font> confirma que el servicio "
        "del grupo 02 fue desplegado en el proyecto indicado y aparece activo en la región "
        "<font name='Courier'>us-central1</font>.",
        "01-cloud-run.png",
        "Evidencia 1. Servicio Cloud Run activo.",
    ),
    (
        "2. Endpoint /health",
        "La respuesta HTTP <b>200</b> confirma que el servicio responde correctamente y está "
        "disponible para recibir solicitudes.",
        "02-health.png",
        "Evidencia 2. Endpoint de salud respondido correctamente.",
    ),
    (
        "3. Predicción válida en /predict",
        "La respuesta HTTP <b>200</b> demuestra que el contrato de entrada fue aceptado y que el "
        "modelo devolvió el puntaje de riesgo, la predicción de churn, el threshold utilizado y "
        "la versión del modelo.",
        "03-predict-valido.png",
        "Evidencia 3. Predicción válida con respuesta JSON completa.",
    ),
    (
        "4. Validación de entrada con respuesta 422",
        "La respuesta HTTP <b>422</b> se genera porque <font name='Courier'>tenure</font> recibió el "
        "texto <font name='Courier'>veinte</font> en lugar de un entero. Esto demuestra que el "
        "contrato protege el servicio frente a tipos de datos inválidos.",
        "04-predict-422.png",
        "Evidencia 4. Solicitud rechazada por tipo de dato inválido.",
    ),
]

for heading, description, filename, image_caption in sections:
    if heading.startswith("3."):
        story.append(PageBreak())
    story.append(KeepTogether([Paragraph(heading, section), Paragraph(description, body)]))
    story.extend(evidence_image(filename, image_caption))
    story.append(Spacer(1, 0.15 * inch))

story.extend([
    Paragraph("Resumen", section),
    Paragraph(
        "Las evidencias confirman el despliegue del servicio, la disponibilidad del endpoint de "
        "salud, una predicción válida y el rechazo de una solicitud que no cumple el esquema de "
        "entrada. El modelo utilizado corresponde a <font name='Courier'>u4_g02_mdl_20260914</font>.",
        body,
    ),
])

doc = SimpleDocTemplate(
    str(OUT), pagesize=letter, rightMargin=0.75 * inch, leftMargin=0.75 * inch,
    topMargin=0.7 * inch, bottomMargin=0.75 * inch,
    title="Evidencias de despliegue U5 - Grupo 02",
    author="Grupo 02",
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
