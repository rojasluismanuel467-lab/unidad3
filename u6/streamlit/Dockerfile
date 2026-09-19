# Dockerfile - Streamlit U6 (Grupo 2)
#
# Build context: u6/ (padre de streamlit/) para poder COPY analysis/ y data/
# desde su ubicacion real y no depender de symlinks.
#
# Uso desde u6/:
#   docker build -t <tag> -f streamlit/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8501

WORKDIR /app

COPY streamlit/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App + paginas
COPY streamlit/app.py .
COPY streamlit/pages/ ./pages/

# Datos y hallazgos precalculados (los symlinks en dev apuntan aca)
COPY analysis/hallazgos_u6.json ./analysis/hallazgos_u6.json
COPY data/lotes_retencion_u6.csv ./data/lotes_retencion_u6.csv

EXPOSE 8501

# Streamlit: --server.address 0.0.0.0 obligatorio para Cloud Run
CMD exec streamlit run app.py \
    --server.port ${PORT} \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
