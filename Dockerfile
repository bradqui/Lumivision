FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LUMIVISION_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static assets at build time (dummy key — never used at runtime).
RUN LUMIVISION_SECRET_KEY=build-time-only LUMIVISION_DATA_DIR=/tmp/build-data \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 lumivision \
    && mkdir -p /data \
    && chown -R lumivision:lumivision /data /app
USER lumivision

VOLUME /data
EXPOSE 8000

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
