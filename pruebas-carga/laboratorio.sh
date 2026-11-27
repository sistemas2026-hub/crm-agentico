#!/usr/bin/env bash
# LA PRUEBA DE CARGA CONTRA LA PREPRODUCCIÓN DE TU PC  --  24/11/2026
#
# Desde el 25/11/2026 el laboratorio ES la preproducción (scripts/preproduccion.sh):
# el mismo docker-compose.prod.yml que despliega Dokploy, con base propia,
# WispHub simulado y nada que salga de tu PC. Antes armaba sus propios
# contenedores; eran dos entornos casi iguales que se iban a desincronizar.
#
#   bash pruebas-carga/laboratorio.sh arriba     # = scripts/preproduccion.sh arriba
#   bash pruebas-carga/laboratorio.sh humo       # o normal, doble, estres
#   bash pruebas-carga/laboratorio.sh abajo      # = scripts/preproduccion.sh abajo
#
# Sirve para comprobar que la prueba funciona y para comparar una rama contra
# otra (¿este cambio hace más lenta la Bandeja?). NO sirve para saber cuánta
# gente aguanta producción: tu PC no es el VPS.

set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
AQUI="$RAIZ/pruebas-carga"
CUENTAS="$RAIZ/.preproduccion/cuentas.json"
export MSYS_NO_PATHCONV=1

correr() { # correr <perfil> [más -e]
  local perfil="$1"; shift
  #  Sin el archivo, Docker crearía una CARPETA con ese nombre al montarlo.
  [ -f "$CUENTAS" ] || { echo "No hay preproducción armada: primero 'laboratorio.sh arriba'."; exit 1; }
  docker run --rm --network dexter-preprod_default -v "$AQUI:/carga" -v "$CUENTAS:/carga/cuentas.json:ro" -w /carga \
    grafana/k6:1.0.0 run -q -e FRONT=http://frontend:3000 -e API=http://backend:8000 \
    -e PERFIL="$perfil" -e CARGA_ESCRIBE=si "$@" dexter.js
}

case "${1:-}" in
  arriba | abajo) bash "$RAIZ/scripts/preproduccion.sh" "$1" ;;
  humo | normal | doble | estres) p="$1"; shift; correr "$p" "$@" ;;
  *) echo "Uso: bash pruebas-carga/laboratorio.sh arriba | humo | normal | doble | estres | abajo"; exit 1 ;;
esac
