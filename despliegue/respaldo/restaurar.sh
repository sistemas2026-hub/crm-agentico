#!/bin/sh
# =============================================================================
#  RESTAURACION  --  el procedimiento completo, sin pasos manuales fuera de aqui
# =============================================================================
#
#   ./restaurar.sh <carpeta_artefactos> <sello> <base_destino> [conexion psql...]
#
#   ejemplo:
#     ./restaurar.sh /r 20260917_100237 postgres -U postgres
#
#  Los TRES artefactos son obligatorios. Con dos, pg_restore termina en 0 y el
#  scheduler queda roto: las funciones job_* son SECURITY DEFINER de
#  asistente_owner, llaman a extensions.digest con search_path=pg_catalog, y
#  fallan en la PRIMERA llamada -- no al restaurar. Medido en el paso 10.2.
#
#  ORDEN, y por que es ese:
#    1. roles     -- cada OWNER TO y cada GRANT del volcado necesita que el rol
#                    exista. Va primero o falla todo.
#    2. entorno   -- extensiones (pg_trgm y vector los usan indices del
#                    volcado), ACL de esquemas ajenos, ajustes por rol.
#                    Va DESPUES de roles porque concede a asistente_owner, y
#                    ANTES del volcado porque los indices necesitan pg_trgm.
#    3. datos     -- con el indice filtrado: se quita SOLO la entrada que CREA
#                    el esquema public, que ya existe en cualquier base nueva.
#                    Su ACL (crm_user=UC, crm_owner=UC) NO se filtra.
# =============================================================================
set -eu

CARPETA="${1:?falta la carpeta de artefactos}"
SELLO="${2:?falta el sello}"
BASE="${3:?falta la base destino}"
shift 3
CONEXION="$@"

DATOS="$CARPETA/${SELLO}_datos.dump"
ROLES="$CARPETA/${SELLO}_roles.sql"
ENTORNO="$CARPETA/${SELLO}_entorno.sql"

for f in "$DATOS" "$ROLES" "$ENTORNO"; do
  [ -s "$f" ] || { echo "FALTA el artefacto: $f"; exit 1; }
done
echo "  artefactos: $(basename "$DATOS"), $(basename "$ROLES"), $(basename "$ENTORNO")"

# --- 1) roles ---------------------------------------------------------------
#  Sin ON_ERROR_STOP a proposito: el volcado trae 'CREATE ROLE postgres', que
#  ya existe en cualquier destino, y un 'ALTER ROLE postgres' que un destino no
#  superusuario rechaza. Ninguno de los dos importa -- el rol ya esta. Lo que
#  SI importa se verifica despues, en verificar_restauracion.py.
echo "  1/3 roles..."
psql $CONEXION -d "$BASE" -q -f "$ROLES" 2>&1 \
  | grep -vE 'role "postgres" already exists|permission denied to alter role|bootstrap superuser|^$' \
  | sed 's/^/        /' || true

# --- 2) entorno -------------------------------------------------------------
echo "  2/3 entorno (extensiones, ACL de esquemas, ajustes por rol)..."
psql $CONEXION -d "$BASE" -q -v ON_ERROR_STOP=1 \
     -v base_destino="$BASE" -f "$ENTORNO" 2>&1 | sed 's/^/        /'

# --- 3) datos ---------------------------------------------------------------
echo "  3/3 datos..."
INDICE="$(mktemp)"
pg_restore --list "$DATOS" \
  | grep -vE '^[0-9]+; [0-9]+ [0-9]+ SCHEMA - public ' > "$INDICE"
pg_restore $CONEXION -d "$BASE" --exit-on-error -L "$INDICE" "$DATOS"
rm -f "$INDICE"

echo "  restauracion terminada. Ahora corre verificar_restauracion.py:"
echo "  un pg_restore en 0 NO demuestra que el scheduler funcione."
