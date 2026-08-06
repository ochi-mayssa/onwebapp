FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
<<<<<<< HEAD

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*
=======
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2-dev \
    libglib2.0-0 \
    libxml2-dev \
    libxslt1-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
>>>>>>> 9716ea5 (Add deployment files and static assets)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

<<<<<<< HEAD
EXPOSE 8000

CMD python manage.py migrate --noinput && \
    gunicorn websity_project.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120
=======
EXPOSE 3000

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn websity_project.wsgi:application --bind 0.0.0.0:${PORT:-3000} --workers 3 --timeout 120"]
>>>>>>> 9716ea5 (Add deployment files and static assets)
