#!/bin/sh
set -e

echo "Lumivision — applying database migrations…"
python manage.py migrate --noinput

echo "Lumivision — ensuring admin account…"
python manage.py ensure_admin

WORKERS="${LUMIVISION_WORKERS:-3}"
PORT="${LUMIVISION_PORT:-8000}"

echo "Lumivision — starting gunicorn on :${PORT} (${WORKERS} workers)…"
exec gunicorn lumivision.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --timeout 300 \
    --access-logfile - \
    --error-logfile -
