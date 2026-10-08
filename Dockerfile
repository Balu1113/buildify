FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY react_frontend/package*.json ./
RUN npm ci
COPY react_frontend/ ./
# An empty value makes the frontend use its same-origin /api endpoint.
ENV REACT_APP_API_BASE_URL=
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---------------------------------------------------------
# System dependencies
# ---------------------------------------------------------

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    pkg-config \
    default-libmysqlclient-dev \
    libcairo2-dev \
    libffi-dev \
    libpango1.0-dev \
    libgirepository1.0-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------
# Node.js / npm (for building generated React frontends)
# ---------------------------------------------------------

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN node --version && npm --version
# ---------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------

WORKDIR /app

COPY django_backend/requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip

RUN pip install --no-cache-dir -r /app/requirements.txt

# ---------------------------------------------------------
# Application
# ---------------------------------------------------------

COPY . /app
COPY --from=frontend-build /frontend/build /app/django_backend/frontend_build

# Django project directory
WORKDIR /app/django_backend

# Create required directories
RUN mkdir -p \
    /app/django_backend/staticfiles \
    /app/django_backend/media \
    /app/django_backend/logs

# Collect static files
RUN python manage.py collectstatic --noinput

# ---------------------------------------------------------
# Django/Gunicorn
# ---------------------------------------------------------

EXPOSE 8000

# gthread workers: health checks and other requests must keep being served
# while a long AI call is in flight (a single sync worker blocks them, which
# makes Render mark the instance unhealthy and return 504s). Threads also keep
# the generated-app preview proxy concurrent while an AI request is running.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn student_project_manager.wsgi:application --bind 0.0.0.0:${PORT:-8000} --worker-class gthread --workers 1 --threads 8 --timeout 120"]
