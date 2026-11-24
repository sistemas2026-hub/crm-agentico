#!/usr/bin/env bash
# UN LABORATORIO PARA LA PRUEBA DE CARGA, EN TU PC  --  24/11/2026
#
# Levanta Dexter completo y aislado (base, Redis, backend, motor y frontend
# COMPILADO COMO EN PRODUCCIÓN) con nombres y puertos propios, sin tocar la
# base de producción ni ningún otro contenedor:
#
#   bash pruebas-carga/laboratorio.sh arriba     # arma todo (~10 min la primera vez)
#   bash pruebas-carga/laboratorio.sh humo       # corre la prueba humo contra él
#   bash pruebas-carga/laboratorio.sh abajo      # borra todo lo del laboratorio
#
# Sirve para comprobar que la prueba funciona y para comparar un cambio contra
# otro (¿esta rama hace más lenta la Bandeja?). NO sirve para saber cuánta gente
# aguanta producción: tu PC no es el VPS.
#
# Sin efectos afuera: WispHub en modo simulado, claves de modelo falsas, y las
# contraseñas de las cuentas de prueba se generan al azar en .laboratorio/
# (fuera del repositorio, ver .gitignore).
#
# Necesita: Docker y Python 3.13 con psycopg (el mismo que usa cli/).

set -euo pipefail
#  En Git Bash, `pwd -W` da C:/... : Docker en Windows no entiende /c/... y con
#  MSYS_NO_PATHCONV (que hace falta para las rutas DENTRO de los contenedores)
#  nadie se lo traduce. En Linux, `pwd -W` no existe y queda `pwd`.
RAIZ="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
AQUI="$RAIZ/pruebas-carga"
LAB="$AQUI/.laboratorio"
RED=cargalab
PY="${PY:-py -3.13}"
export MSYS_NO_PATHCONV=1

abajo() {
  docker rm -f cargalab-frontend cargalab-motor cargalab-backend cargalab-redis cargalab-db >/dev/null 2>&1 || true
  docker network rm "$RED" >/dev/null 2>&1 || true
  echo "Laboratorio borrado."
}

esperar() { # esperar <segundos> <descripción> <comando...>
  local hasta=$((SECONDS + $1)) que="$2"; shift 2
  until "$@" >/dev/null 2>&1; do
    [ $SECONDS -ge $hasta ] && { echo "No arrancó: $que"; exit 1; }
    sleep 3
  done
}

arriba() {
  mkdir -p "$LAB"
  echo "1/7 Imágenes de este código (backend, frontend de producción, motor)..."
  docker build -q -t cargalab-backend:prueba "$RAIZ/django-crm" >/dev/null
  docker build -q -t cargalab-frontend:prueba "$RAIZ/django-crm/frontend" >/dev/null
  docker build -q -t cargalab-motor:prueba "$RAIZ" >/dev/null

  echo "2/7 Secretos y cuentas de prueba, al azar..."
  if [ ! -f "$LAB/secretos.env" ]; then
    $PY - "$LAB" <<'EOF'
import base64, json, os, secrets, sys
d = sys.argv[1]; c = lambda: secrets.token_urlsafe(18)
s = {"ADMIN_PASSWORD": c(), "SECRET_KEY": secrets.token_urlsafe(48), "MOTOR_SERVICE_TOKEN": c(),
     "SECRETOS_CLAVE_MAESTRA": base64.urlsafe_b64encode(os.urandom(32)).decode()}
cuentas = {"oficina": [{"email": f"oficina{i}@carga.test", "password": c()} for i in (1, 2)],
           "supervisor": [{"email": "supervisor@carga.test", "password": c()}],
           "tecnico": [{"email": f"tecnico{i}@carga.test", "password": c()} for i in (1, 2, 3)]}
open(f"{d}/secretos.env", "w").write("".join(f"{k}={v}\n" for k, v in s.items()))
open(f"{d}/cuentas.json", "w").write(json.dumps(cuentas, indent=1))
EOF
  fi

  echo "3/7 Base y Redis..."
  docker network create "$RED" >/dev/null 2>&1 || true
  docker run -d --name cargalab-db --network "$RED" --network-alias db -p 55432:5432 \
    -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=crm_db \
    -v "$RAIZ/django-crm/docker/postgres/init-rls-user.sql:/docker-entrypoint-initdb.d/init-rls-user.sql:ro" \
    pgvector/pgvector:pg16 >/dev/null
  docker run -d --name cargalab-redis --network "$RED" --network-alias redis redis:7-alpine >/dev/null
  esperar 90 "la base" docker exec cargalab-db pg_isready -U postgres -d crm_db
  sleep 3

  echo "4/7 La base desde cero, por el ledger (Django + motor)..."
  ( cd "$RAIZ" && DBPASSWORD=postgres IMAGEN_DJANGO=cargalab-backend:prueba \
      $PY cli/base_desde_cero.py --base dexter_carga --host localhost --puerto 55432 --usuario postgres ) | tail -1

  echo "5/7 Backend (gunicorn, como en producción)..."
  docker run -d --name cargalab-backend --network "$RED" --network-alias backend -p 58000:8000 \
    --env-file "$LAB/secretos.env" \
    -e ENV_TYPE=prod -e DEBUG=False -e ALLOWED_HOSTS=api.carga.test,localhost,backend \
    -e DOMAIN_NAME=https://api.carga.test -e FRONTEND_URL=https://app.carga.test \
    -e CORS_ALLOWED_ORIGINS=https://app.carga.test -e CSRF_TRUSTED_ORIGINS=https://app.carga.test,https://api.carga.test \
    -e DBHOST=db -e DBPORT=5432 -e DBNAME=dexter_carga -e DBUSER=postgres -e DBPASSWORD=postgres \
    -e CELERY_BROKER_URL=redis://redis:6379/0 -e CELERY_RESULT_BACKEND=redis://redis:6379/0 \
    -e MOTOR_URL=http://motor:5000 -e ASISTENTE_URL=http://motor:5000 \
    -e ADMIN_EMAIL=admin@carga.test -e CORS_ALLOW_ALL=False -e DEFAULT_FROM_EMAIL=noreply@carga.test \
    -v "$RAIZ/django-crm/docker/backend/entrypoint.sh:/entrypoint.sh:ro" \
    cargalab-backend:prueba /bin/bash /entrypoint.sh >/dev/null
  esperar 240 "el backend" sh -c "docker logs cargalab-backend 2>&1 | grep -q 'Booting worker'"

  echo "6/7 Empresa, cuentas, config del tenant y 600 chats de ejemplo..."
  docker exec cargalab-backend mkdir -p /lab
  docker cp "$LAB/cuentas.json" cargalab-backend:/lab/cuentas.json >/dev/null
  docker exec -i cargalab-backend sh -c "cd /app && python manage.py shell" >/dev/null <<'EOF'
import json
from common.models import Org, Profile, User
c = json.load(open("/lab/cuentas.json"))
org, _ = Org.objects.get_or_create(name="Rapilink")
roles = {"oficina": "USER", "supervisor": "SUPERVISOR", "tecnico": "USER"}
for grupo, lista in c.items():
    for cu in lista:
        u = User.objects.filter(email=cu["email"]).first() or User.objects.create_user(email=cu["email"], password=cu["password"])
        u.set_password(cu["password"]); u.is_active = True; u.save()
        Profile.objects.get_or_create(user=u, org=org, defaults={"role": roles[grupo]})
EOF
  ( cd "$RAIZ" && DBHOST=localhost DBPORT=55432 DBNAME=dexter_carga DBUSER=postgres DBPASSWORD=postgres \
      $PY cli/cargar_config.py tenants/rapilink.config.yaml --forzar ) | grep -E "cargada|ERROR" || true
  docker exec -i cargalab-db psql -q -U postgres -d dexter_carga -v ON_ERROR_STOP=1 <<'EOF'
insert into asistente.conversations (organization_id, canal, usuario_externo, nombre_cliente, estado, creado_en, actualizado_en, necesita_atencion_humana)
select (select id from public.organization limit 1), 'whatsapp', '5730000' || lpad(g::text, 5, '0'), 'Cliente de prueba ' || g,
       case when g % 5 = 0 then 'cerrada' else 'abierta' end,
       now() - (g || ' minutes')::interval, now() - (g || ' minutes')::interval, g % 7 = 0
from generate_series(1, 600) g;
insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
select c.organization_id, c.id, case when m % 2 = 0 then 'user' else 'assistant' end,
       case when m % 2 = 0 then 'Hola, no tengo internet desde esta mañana, la luz LOS está roja'
            else 'Entiendo, voy a revisar el estado de tu servicio y te cuento en un momento.' end,
       case when m % 2 = 0 then 'cliente' else 'ia' end, c.creado_en + (m || ' seconds')::interval
from asistente.conversations c, generate_series(1, 25) m;
EOF

  echo "7/7 Motor (1 proceso, 16 hilos) y frontend..."
  docker run -d --name cargalab-motor --network "$RED" --network-alias motor --env-file "$LAB/secretos.env" \
    -e DBHOST=db -e DBPORT=5432 -e DBNAME=dexter_carga -e DBUSER=postgres -e DBPASSWORD=postgres \
    -e WISPHUB_API_KEY=falsa -e WISPHUB_MODO_REAL=false -e DEEPSEEK_API_KEY=falsa -e OPENAI_API_KEY=falsa \
    -e BOTTLECRM_API_TOKEN=falsa -e DB_APPLICATION_NAME=dexter-motor \
    cargalab-motor:prueba gunicorn nucleo.canales.api:app --config python:nucleo.canales.gunicorn_conf \
    --bind 0.0.0.0:5000 --workers 1 --threads 16 --timeout 180 >/dev/null
  local token; token="$(grep '^MOTOR_SERVICE_TOKEN=' "$LAB/secretos.env" | cut -d= -f2-)"
  docker run -d --name cargalab-frontend --network "$RED" --network-alias frontend -p 53000:3000 \
    -e PUBLIC_DJANGO_API_URL=https://api.carga.test -e PRIVATE_DJANGO_API_URL=http://backend:8000 \
    -e PRIVATE_ASISTENTE_URL=http://motor:5000 -e PRIVATE_MOTOR_SERVICE_TOKEN="$token" \
    -e ORIGIN=https://app.carga.test cargalab-frontend:prueba >/dev/null
  esperar 60 "el frontend" curl -sf -o /dev/null http://localhost:53000/login
  echo "Listo. Frontend en http://localhost:53000 · cuentas en $LAB/cuentas.json"
}

correr() { # correr <perfil> [más -e]
  local perfil="$1"; shift
  #  Sin el archivo, Docker crearía una CARPETA con ese nombre al montarlo.
  [ -f "$LAB/cuentas.json" ] || { echo "Falta $LAB/cuentas.json: primero 'laboratorio.sh arriba'."; exit 1; }
  docker run --rm --network "$RED" -v "$AQUI:/carga" -v "$LAB/cuentas.json:/carga/cuentas.json:ro" -w /carga \
    grafana/k6:1.0.0 run -q -e FRONT=http://frontend:3000 -e API=http://backend:8000 \
    -e PERFIL="$perfil" -e CARGA_ESCRIBE=si "$@" dexter.js
}

case "${1:-}" in
  arriba) arriba ;;
  abajo) abajo ;;
  humo | normal | doble | estres) p="$1"; shift; correr "$p" "$@" ;;
  *) echo "Uso: bash pruebas-carga/laboratorio.sh arriba | humo | normal | doble | estres | abajo"; exit 1 ;;
esac
