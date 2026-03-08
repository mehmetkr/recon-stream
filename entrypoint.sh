#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
while ! python -c "
import os, psycopg
try:
    psycopg.connect(os.environ['DATABASE_URL'])
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL is ready."

echo "Applying migrations..."
python src/manage.py migrate --noinput

exec "$@"
