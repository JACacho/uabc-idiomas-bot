# Dockerfile para UABCBot Idiomas — Google Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-descargar modelo de embeddings (acelera el arranque en Cloud Run)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copiar el resto del proyecto
COPY . .

# Cloud Run usa la variable PORT (default 8080, sobreescribimos a 7860)
ENV PORT=7860
EXPOSE 7860

# Comando de arranque
CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "7860"]