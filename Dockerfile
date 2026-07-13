FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LUMIVISION_DATA_DIR=/data

WORKDIR /app

# ffmpeg extracts poster frames from uploaded videos
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('LUMIVISION_PORT','8000')+'/healthz', timeout=4)"

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
