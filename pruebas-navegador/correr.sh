#!/bin/sh
#
#  La suite corre DENTRO del contenedor oficial de Playwright.
#
#  Asi no se instala un navegador en Windows -- la leccion de `pnpm check`, que
#  rompe el frontend por truncamiento de rutas -- y la version del navegador es
#  la misma en cualquier maquina.
#
#  `--add-host` hace que `host.docker.internal` resuelva al anfitrion tambien
#  en Linux; en Docker Desktop ya resuelve, y repetirlo no molesta.
set -e
AQUI=$(cd "$(dirname "$0")" && pwd)
IMAGEN=mcr.microsoft.com/playwright:v1.49.1-jammy

docker run --rm -t \
  -v "$AQUI":/pruebas \
  -w /pruebas \
  --add-host=host.docker.internal:host-gateway \
  -e BASE="${BASE:-http://host.docker.internal:55600}" \
  -e USUARIO="${USUARIO:-admin@localhost}" \
  -e CLAVE="${CLAVE:-lab12345}" \
  -e ORG_CON="${ORG_CON:-MicroPyramid}" \
  -e ORG_SIN="${ORG_SIN:-Plumeline Media}" \
  -e CI=1 \
  "$IMAGEN" \
  sh -c 'test -d node_modules || npm install --no-audit --no-fund; npx playwright test "$@"' -- "$@"
