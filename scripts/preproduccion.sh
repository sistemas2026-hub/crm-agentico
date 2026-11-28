#!/usr/bin/env bash
# PREPRODUCCIÓN EN TU PC  --  25/11/2026
#
# Dexter completo, compilado y arrancado COMO EN PRODUCCIÓN (el mismo
# docker-compose.prod.yml que despliega Dokploy), con su propia base y sin
# ninguna salida al mundo. Es la puerta antes de subir:
#
#   bash scripts/preproduccion.sh arriba       # arma todo desde cero (~10 min la 1.ª vez)
#   bash scripts/preproduccion.sh actualizar   # tu cambio, sobre la base que ya tiene datos
#   bash scripts/preproduccion.sh estado       # qué está arriba y dónde entrar
#   bash scripts/preproduccion.sh registros [servicio]   # logs en vivo
#   bash scripts/preproduccion.sh copiar-produccion <archivo>   # los DATOS de producción
#   bash scripts/preproduccion.sh abajo        # borra todo, base incluida
#
# Para que quede IDÉNTICA a producción (código y datos), ver copiar_produccion()
# más abajo o DESPLIEGUE.md, «Preproducción».
#
# 'actualizar' es lo que más importa: aplica TUS migraciones (las de Django al
# arrancar el backend y las del motor con cli/migrar_asistente.py) sobre una
# base que ya tiene conversaciones y datos, como va a pasar en producción.
# Si algo de eso falla, falla acá.
#
# Sin efectos afuera:
#   - WispHub simulado (WISPHUB_MODO_REAL=false);
#   - claves de OpenAI y DeepSeek FALSAS: el agente no contesta. Si querés
#     probar al agente, poné tus claves a mano en .preproduccion/variables.env
#     y corré 'actualizar' (cuesta lo mismo que en producción);
#   - WhatsApp: la config del tenant sale del YAML del repositorio, que no
#     trae las credenciales de Meta, así que no se le escribe a nadie;
#   - FRONTEND_URL es un dominio inválido a propósito: un correo que se mande
#     no lleva un enlace que funcione.
#
# Los secretos y las contraseñas de prueba se generan al azar en
# .preproduccion/ (fuera del repositorio, ver .gitignore).
#
# Necesita: Docker y Python 3.13 con psycopg (el mismo que usa cli/).

set -euo pipefail
#  En Git Bash, `pwd -W` da C:/... (Docker en Windows no entiende /c/...).
#  En Linux, `pwd -W` no existe y queda `pwd`.
RAIZ="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
PRE="$RAIZ/.preproduccion"
VARS="$PRE/variables.env"
PY="${PY:-py -3.13}"
export MSYS_NO_PATHCONV=1
cd "$RAIZ"

compose() {
  docker compose -p dexter-preprod --env-file "$VARS" \
    -f docker-compose.prod.yml -f docker-compose.preproduccion.yml "$@"
}
var() { grep "^$1=" "$VARS" | cut -d= -f2-; }

esperar() { # esperar <segundos> <descripción> <comando...>
  local hasta=$((SECONDS + $1)) que="$2"; shift 2
  until "$@" >/dev/null 2>&1; do
    [ $SECONDS -ge $hasta ] && { echo "No arrancó: $que. Mirá: bash scripts/preproduccion.sh registros"; exit 1; }
    sleep 3
  done
}

generar_variables() {
  mkdir -p "$PRE"
  [ -f "$VARS" ] && return 0
  $PY - "$PRE" <<'EOF'
import base64, json, os, secrets, sys
d = sys.argv[1]; c = lambda: secrets.token_urlsafe(18)
pg = c()
front, back = "http://localhost:3300", "http://localhost:8300"
v = {
    # Puertos en tu PC (solo 127.0.0.1)
    "PUERTO_BASE": "54330", "PUERTO_BACKEND": "8300", "PUERTO_FRONTEND": "3300",
    # Base local: el servicio 'db' de docker-compose.preproduccion.yml
    "DBHOST": "db", "DBPORT": "5432", "DBNAME": "dexter_preprod", "DBUSER": "postgres", "DBPASSWORD": pg,
    "MOTOR_DBUSER": "postgres", "MOTOR_DBPASSWORD": pg,
    # Secretos propios, al azar: nunca los de producción
    "SECRET_KEY": secrets.token_urlsafe(48), "MOTOR_SERVICE_TOKEN": c(),
    "SECRETOS_CLAVE_MAESTRA": base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "ADMIN_EMAIL": "admin@preproduccion.test", "ADMIN_PASSWORD": c(),
    # Dominios: el navegador entra por localhost
    "ALLOWED_HOSTS": "localhost,127.0.0.1", "DOMAIN_NAME": back, "PUBLIC_DJANGO_API_URL": back,
    "CORS_ALLOWED_ORIGINS": front, "CSRF_TRUSTED_ORIGINS": f"{front},{back}",
    #  El backend en modo producción no acepta localhost acá (es la base de los
    #  enlaces de los correos). Un dominio .invalid nunca resuelve: ningún
    #  correo que salga de preproducción lleva un enlace que funcione.
    "FRONTEND_URL": "https://preproduccion.invalid",
    "DEFAULT_FROM_EMAIL": "noreply@preproduccion.test",
    # Nada sale de tu PC
    "WISPHUB_MODO_REAL": "false", "WISPHUB_API_KEY": "falsa",
    "OPENAI_API_KEY": "falsa", "DEEPSEEK_API_KEY": "falsa", "BOTTLECRM_API_TOKEN": "falsa",
    "RELOJ_HABILITADO": "0",
}
open(f"{d}/variables.env", "w").write("".join(f"{k}={x}\n" for k, x in v.items()))
cuentas = {"admin": [{"email": v["ADMIN_EMAIL"], "password": v["ADMIN_PASSWORD"]}],
           "oficina": [{"email": f"oficina{i}@preproduccion.test", "password": c()} for i in (1, 2)],
           "supervisor": [{"email": "supervisor@preproduccion.test", "password": c()}],
           "tecnico": [{"email": f"tecnico{i}@preproduccion.test", "password": c()} for i in (1, 2, 3)]}
open(f"{d}/cuentas.json", "w").write(json.dumps(cuentas, indent=1))
EOF
}

migrar_motor() {
  ( DBHOST=localhost DBPORT="$(var PUERTO_BASE)" DBNAME="$(var DBNAME)" DBUSER=postgres \
      DBPASSWORD="$(var DBPASSWORD)" $PY cli/migrar_asistente.py --aplicar ) | tail -3
}

arriba() {
  if docker volume inspect dexter-preprod_preprod_db >/dev/null 2>&1; then
    echo "Ya hay una preproducción armada. Para tu cambio: 'actualizar'. Para empezar de cero: 'abajo' y después 'arriba'."
    exit 1
  fi
  generar_variables
  #  docker-compose.prod.yml declara la red de Dokploy como externa; en tu PC
  #  no existe, y sin ella Compose no arranca. Es una red vacía, nada más.
  docker network inspect dokploy-network >/dev/null 2>&1 || docker network create dokploy-network >/dev/null

  echo "1/6 Imágenes de ESTE código, como las construye Dokploy..."
  compose build -q

  echo "2/6 Base y Redis..."
  compose up -d db redis >/dev/null 2>&1
  esperar 90 "la base" compose exec -T db pg_isready -U postgres -d crm_db
  sleep 3

  echo "3/6 La base desde cero, por el ledger (Django + motor)..."
  DBPASSWORD="$(var DBPASSWORD)" IMAGEN_DJANGO=dexter-preprod-backend \
    $PY cli/base_desde_cero.py --base "$(var DBNAME)" --host localhost --puerto "$(var PUERTO_BASE)" --usuario postgres | tail -1

  echo "4/6 Backend (gunicorn y migraciones, como en producción)..."
  compose up -d backend >/dev/null 2>&1
  esperar 300 "el backend" sh -c "docker logs dexter-preprod-backend-1 2>&1 | grep -q 'Booting worker'"

  echo "5/6 Empresa, cuentas, config del tenant y 600 chats de ejemplo..."
  sembrar_cuentas
  sembrar_ejemplo

  echo "6/6 El resto: motor, reloj, celery y frontend..."
  compose up -d >/dev/null 2>&1
  esperar 120 "el frontend" curl -sf -o /dev/null "http://localhost:$(var PUERTO_FRONTEND)/login"
  git rev-parse HEAD > "$PRE/commit"
  estado
}

sembrar_cuentas() {
  #  Las cuentas de prueba de .preproduccion/cuentas.json, en la empresa
  #  Rapilink (la de producción, si la base es una copia; si no, se crea).
  docker cp "$PRE/cuentas.json" dexter-preprod-backend-1:/tmp/cuentas.json >/dev/null
  compose exec -T backend sh -c "cd /app && python manage.py shell" >/dev/null <<'EOF'
import json
from common.models import Org, Profile, User
c = json.load(open("/tmp/cuentas.json"))
org = (Org.objects.filter(name__iexact="Rapilink").first() or Org.objects.order_by("id").first()
       or Org.objects.create(name="Rapilink"))
roles = {"admin": "ADMIN", "oficina": "USER", "supervisor": "SUPERVISOR", "tecnico": "USER"}
for grupo, lista in c.items():
    for cu in lista:
        u = User.objects.filter(email=cu["email"]).first() or User.objects.create_user(email=cu["email"], password=cu["password"])
        u.set_password(cu["password"]); u.is_active = True; u.save()
        Profile.objects.get_or_create(user=u, org=org, defaults={"role": roles[grupo]})
EOF
  compose exec -T backend rm -f /tmp/cuentas.json
}

sembrar_ejemplo() {
  #  --forzar: la guarda de alineación git no distingue una base local recién
  #  creada de la real (DESPLIEGUE.md, «Un entorno local de verdad»). Esta base
  #  tiene minutos y sale de esta misma copia de trabajo.
  ( DBHOST=localhost DBPORT="$(var PUERTO_BASE)" DBNAME="$(var DBNAME)" DBUSER=postgres DBPASSWORD="$(var DBPASSWORD)" \
      $PY cli/cargar_config.py tenants/rapilink.config.yaml --forzar ) | grep -E "cargada|ERROR" || true
  compose exec -T db psql -q -U postgres -d "$(var DBNAME)" -v ON_ERROR_STOP=1 <<'EOF'
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
}

actualizar() {
  [ -f "$VARS" ] || { echo "No hay preproducción armada: primero 'arriba'."; exit 1; }
  echo "1/3 Imágenes con tu código..."
  compose build -q
  echo "2/3 Migraciones del motor sobre la base CON datos (cli/migrar_asistente.py)..."
  migrar_motor
  echo "3/3 Reemplazando los contenedores (el backend aplica las de Django al arrancar)..."
  compose up -d >/dev/null 2>&1
  local hasta=$((SECONDS + 300))
  until docker logs --since 5m dexter-preprod-backend-1 2>&1 | grep -q 'Booting worker'; do
    if docker logs --since 5m dexter-preprod-backend-1 2>&1 | grep -qE 'Traceback|django.db.utils'; then
      echo "El backend falló al arrancar (¿una migración?):"; docker logs --tail 40 dexter-preprod-backend-1; exit 1
    fi
    [ $SECONDS -ge $hasta ] && { echo "El backend no arrancó en 5 min."; exit 1; }
    sleep 3
  done
  esperar 120 "el frontend" curl -sf -o /dev/null "http://localhost:$(var PUERTO_FRONTEND)/login"
  git rev-parse HEAD > "$PRE/commit"
  estado
}

copiar_produccion() {
  # Reemplaza los DATOS de la preproducción por los de producción. Solo lee
  # producción (pg_dump); no escribe nada allá.
  #
  # Para que quede idéntica, código y datos:
  #   git switch --detach origin/fix/integracion-wisphub      # el código de producción
  #   bash scripts/preproduccion.sh abajo
  #   bash scripts/preproduccion.sh arriba                    # la estructura de ese código
  #   bash scripts/preproduccion.sh copiar-produccion C:/wisphub/dexter/.env
  # Y para probar TU cambio sobre esos datos:
  #   git switch <tu rama>
  #   bash scripts/preproduccion.sh actualizar
  #
  # <archivo> es un .env con DBHOST, DBPORT, DBNAME, DBUSER y DBPASSWORD de
  # producción. Se leen solo esas cinco líneas y no se imprimen.
  #
  # Lo que NO se copia: asistente.tenant_secrets (credenciales de WhatsApp,
  # WispHub y demás). Igual estarían cifradas con la SECRETOS_CLAVE_MAESTRA de
  # producción, que esta copia no tiene. Sin ellas, nada sale de tu PC aunque
  # los datos sean reales: WispHub sigue simulado y las claves de modelo son
  # falsas.
  local origen="${1:-}"
  [ -n "$origen" ] && [ -f "$origen" ] || {
    echo "Uso: bash scripts/preproduccion.sh copiar-produccion <archivo .env con las DB* de producción>"; exit 1; }
  [ -f "$VARS" ] || { echo "No hay preproducción armada: primero 'arriba'."; exit 1; }

  #  Los datos entran en la estructura que armó el código de la preproducción:
  #  si no es el commit de producción, las tablas no coinciden.
  git fetch -q origin fix/integracion-wisphub
  local prod armada
  prod="$(git rev-parse origin/fix/integracion-wisphub)"
  armada="$(cat "$PRE/commit" 2>/dev/null || true)"
  if [ "$armada" != "$prod" ] && [ "${COPIA_OTRO_COMMIT:-}" != "si" ]; then
    echo "La preproducción está armada con ${armada:0:8} y producción está en ${prod:0:8}."
    echo "Los datos de producción solo entran en la estructura del código de producción:"
    echo "  git switch --detach origin/fix/integracion-wisphub"
    echo "  bash scripts/preproduccion.sh abajo && bash scripts/preproduccion.sh arriba"
    echo "  bash scripts/preproduccion.sh copiar-produccion $origen"
    exit 1
  fi

  local dump="$PRE/produccion.dump"
  trap "rm -f '$dump'" EXIT
  echo "1/4 Copiando los datos de producción (solo lectura; sin tenant_secrets)..."
  (
    set -a
    # shellcheck disable=SC1090
    . <(grep -E '^(DBHOST|DBPORT|DBNAME|DBUSER|DBPASSWORD)=' "$origen" | tr -d '\r')
    set +a
    [ -n "${DBHOST:-}" ] && [ -n "${DBPASSWORD:-}" ] || { echo "El archivo no trae DBHOST y DBPASSWORD."; exit 1; }
    #  La contraseña va por el entorno ('-e PGPASSWORD' sin valor), no en la
    #  línea de comandos, donde la vería cualquiera que liste los procesos.
    export PGPASSWORD="$DBPASSWORD"
    docker run --rm -e PGPASSWORD -v "$PRE:/salida" pgvector/pgvector:pg17 \
      pg_dump -h "$DBHOST" -p "$DBPORT" -U "$DBUSER" -d "$DBNAME" \
      --data-only -n public -n asistente --exclude-table-data=asistente.tenant_secrets \
      -Fc -f /salida/produccion.dump 2> >(grep -vE '^pg_dump: (warning|detail|hint)' >&2)
    #  Esas advertencias son por claves foráneas circulares (case,
    #  operaciones_actividad): las resuelve el --disable-triggers de la carga.
  )
  echo "    $(du -h "$dump" | cut -f1) copiados."

  echo "2/4 Vaciando la base de la preproducción..."
  compose stop motor motor-reloj celery-worker celery-beat backend frontend >/dev/null 2>&1
  #  session_replication_role=replica apaga los triggers, incluido el que hace
  #  de «solo agregar» al ledger del motor (asistente.migraciones_aplicadas).
  #  Acá corresponde: es una copia local que se reemplaza entera, y se trae el
  #  ledger de producción para que 'actualizar' decida qué migraciones aplicar
  #  exactamente como lo hará el despliegue.
  compose exec -T db psql -q -U postgres -d "$(var DBNAME)" -v ON_ERROR_STOP=1 <<'EOF'
set session_replication_role = replica;
do $$ begin
  execute (select 'truncate table ' || string_agg(format('%I.%I', schemaname, tablename), ', ') || ' restart identity cascade'
           from pg_tables where schemaname in ('public', 'asistente'));
end $$;
EOF

  echo "3/4 Cargando los datos de producción..."
  docker cp "$dump" dexter-preprod-db-1:/tmp/produccion.dump >/dev/null
  #  --disable-triggers: carga cada tabla sin mirar el orden de las claves
  #  foráneas ni disparar triggers (lo que pasó en producción ya pasó).
  compose exec -T db pg_restore -U postgres -d "$(var DBNAME)" --data-only --disable-triggers \
    --no-owner --exit-on-error /tmp/produccion.dump
  compose exec -T db rm -f /tmp/produccion.dump
  rm -f "$dump"

  echo "4/4 Arrancando, con las cuentas de prueba agregadas a la empresa..."
  compose up -d >/dev/null 2>&1
  esperar 300 "el backend" sh -c "docker logs --since 2m dexter-preprod-backend-1 2>&1 | grep -q 'Booting worker'"
  sembrar_cuentas
  esperar 120 "el frontend" curl -sf -o /dev/null "http://localhost:$(var PUERTO_FRONTEND)/login"
  compose exec -T db psql -U postgres -d "$(var DBNAME)" -tA -c \
    "select 'Empresas: ' || (select count(*) from public.organization) || ' · usuarios: ' || (select count(*) from public.users) || ' · conversaciones: ' || (select count(*) from asistente.conversations)" || true
  echo "OJO: ahora hay datos REALES de clientes en tu PC. 'abajo' los borra."
  estado
}

estado() {
  compose ps --format 'table {{.Service}}\t{{.Status}}'
  echo
  echo "Entrá en:  http://localhost:$(var PUERTO_FRONTEND)"
  echo "Cuentas:   $PRE/cuentas.json  (admin, oficina, supervisor, técnicos)"
  echo "Base:      localhost:$(var PUERTO_BASE)  base $(var DBNAME), usuario postgres (contraseña en variables.env)"
}

abajo() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$PRE"
  echo "Preproducción borrada (contenedores, base y secretos)."
}

case "${1:-}" in
  arriba) arriba ;;
  actualizar) actualizar ;;
  estado) estado ;;
  registros) shift; compose logs -f --tail 50 "$@" ;;
  copiar-produccion) shift; copiar_produccion "$@" ;;
  abajo) abajo ;;
  *) echo "Uso: bash scripts/preproduccion.sh arriba | actualizar | estado | registros [servicio] | copiar-produccion <archivo> | abajo"; exit 1 ;;
esac
