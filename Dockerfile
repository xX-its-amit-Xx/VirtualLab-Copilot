# Single-stage image that runs both the FastAPI backend and the
# Streamlit frontend. For production-style deployments split into two
# services (see docker-compose.yml).
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for scientific python wheels (most are pre-built but be safe).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app

# Default to the API; docker-compose overrides this for the Streamlit service.
ENV VLC_DB_PATH=/app/data/virtuallab.db \
    VLC_API_HOST=0.0.0.0 \
    VLC_API_PORT=8000 \
    VLC_API_BASE_URL=http://api:8000

EXPOSE 8000 8501

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
