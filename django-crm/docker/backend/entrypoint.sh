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

# 'db' es el unico host que el compose de desarrollo levanta el mismo; todo lo
# demas (en la practica, siempre el Supabase de produccion -- ver
# DESPLIEGUE.md, "Desarrollo local contra la base real") es una base de
# verdad, y las migraciones de aca abajo se le aplican igual que si esto
# corriera en el VPS.
if [ "$DBHOST" != "db" ] && [ "$DBHOST" != "localhost" ] && [ "$DBHOST" != "127.0.0.1" ]; then
    echo ""
    echo "  ATENCION: DBHOST=$DBHOST no es la base local del compose."
    echo "  Las migraciones y el superusuario de arranque van contra esa base"
    echo "  de verdad, no contra una copia. Ver DESPLIEGUE.md."
    echo ""
fi

# =============================================================================
#  CREDENCIALES  --  quien sirve y quien migra no son el mismo
# =============================================================================
# Hasta la Etapa B.4, 'migrate' corria con las MISMAS credenciales con las que
# gunicorn sirve las peticiones. Mientras esas credenciales fueron las de
# 'postgres' no se noto: es dueno de las 129 tablas y puede con todo. El dia que
# el CRM se corte a 'crm_user' -que no es dueno de ninguna- la primera migracion
# que necesite 'ALTER TABLE ... ENABLE ROW LEVEL SECURITY' falla con 'must be
# owner of table'. Medido contra PostgreSQL 17 en la Etapa B.3.
#
# MIGRATOR_DBUSER/MIGRATOR_DBPASSWORD son OPCIONALES a proposito: sin ellas esto
# se comporta exactamente como antes. Asi el archivo se puede desplegar sin
# haber creado todavia ningun rol nuevo.

echo "Checking traffic credentials..."
python manage.py verificar_credenciales --proposito trafico

if [ -n "${MIGRATOR_DBUSER:-}" ]; then
    echo "Running migrations as ${MIGRATOR_DBUSER%%.*} (separate credential)..."
    # El override vale SOLO para estos dos procesos. La variable del contenedor
    # no cambia, asi que gunicorn -mas abajo- sigue levantando con la de
    # trafico. Es la diferencia entre separar las credenciales y cambiarlas.
    DBUSER="$MIGRATOR_DBUSER" DBPASSWORD="$MIGRATOR_DBPASSWORD" \
        python manage.py verificar_credenciales --proposito migraciones --con-base
    DBUSER="$MIGRATOR_DBUSER" DBPASSWORD="$MIGRATOR_DBPASSWORD" \
        python manage.py migrate --noinput
else
    echo "Running migrations with DBUSER (no separate migration credential)..."
    # Sin credencial propia, se migra con la de siempre -- pero se comprueba
    # igual, y CONTRA LA BASE: lo que decide si esta credencial sirve para
    # migrar no es como se llama, sino de cuantas tablas puede ejercer el rol
    # dueno. En desarrollo crm_user las posee todas y esto pasa; en produccion
    # no posee ninguna y esto falla aca, con el motivo escrito, en vez de a
    # mitad de una migracion con 'must be owner of table'.
    python manage.py verificar_credenciales --proposito migraciones --con-base
    python manage.py migrate --noinput
fi

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
