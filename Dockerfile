# Base Image
FROM python:3.11-slim

# Evitar prompts interactivos y buffers de Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Instalar dependencias del sistema para Playwright, WeasyPrint y red
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    libgomp1 \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar requerimientos de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Instalar Chromium para Playwright y sus librerías de sistema
RUN playwright install chromium && \
    playwright install-deps chromium

# Copiar código del proyecto
COPY . .

# Crear directorios de datos necesarios
RUN mkdir -p data/processed_json data/reports data/uploaded_pdfs data/qdrant_db

# Exponer puertos para FastAPI (8000) y Streamlit (8501)
EXPOSE 8000 8501

# Comando por defecto (inicia FastAPI; docker-compose sobreescribe para Streamlit)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
