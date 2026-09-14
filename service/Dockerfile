# Dockerfile - servicio churn-api (Grupo 2, U5)
# Base: Python 3.11 slim (imagen chica, arranque rapido en Cloud Run)
FROM python:3.11-slim

# Evita bytecode + logging con buffer (los logs salen al toque a Cloud Logging)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Dependencias primero (aprovecha cache de layers)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Codigo del servicio
COPY app/ ./app/

# Cloud Run llama al puerto $PORT (default 8080)
EXPOSE 8080

# Uvicorn con 1 worker (Cloud Run autoscala por instancia, no por worker)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
