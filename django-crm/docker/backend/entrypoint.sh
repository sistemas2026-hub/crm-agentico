#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
retries=0
max_retries=30
while ! python -c "
import socket, os
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((os.environ['DBHOST'], int(os.environ['DBPORT'])))
s.close()
" 2>/dev/null; do
    retries=$((retries + 1))
    if [ "$retries" -ge "$max_retries" ]; then
        echo "ERROR: Could not connect to PostgreSQL after $max_retries attempts."
        exit 1
    fi
    echo "  PostgreSQL not ready yet (attempt $retries/$max_retries)..."
    sleep 1
done
echo "PostgreSQL is ready."

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating default admin user (if needed)..."
python manage.py create_default_admin

echo "Collecting static files..."
python manage.py collectstatic --noinput

# runserver es de un solo hilo y la propia documentacion de Django dice que no
# se use fuera de desarrollo. gunicorn ya viene en las dependencias
# (backend/pyproject.toml), asi que en produccion solo hay que usarlo.
# Los estaticos los sigue sirviendo whitenoise, que ya esta en MIDDLEWARE, asi
# que no hace falta un servidor aparte para ellos.
if [ "$ENV_TYPE" = "prod" ]; then
    echo "Starting gunicorn..."
    exec gunicorn crm.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-3}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        --access-logfile - \
        --error-logfile -
else
    echo "Starting development server..."
    exec python manage.py runserver 0.0.0.0:8000
fi
