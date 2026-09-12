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
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip

RUN pip install --no-cache-dir -r /app/requirements.txt

# ---------------------------------------------------------
# Application
# ---------------------------------------------------------

COPY . /app

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
RUN python manage.py collectstatic --noinput

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn student_project_manager.wsgi:application --bind 0.0.0.0:$PORT"]