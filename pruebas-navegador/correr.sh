#!/bin/sh
#
#  La suite corre DENTRO de un contenedor, nunca en Windows.
#
#  Es la lección de `pnpm check`, que rompe el frontend por truncamiento de
#  rutas: en esta máquina las herramientas de Node se ejecutan en Linux.
#
#  POR QUE LA IMAGEN OFICIAL DE PLAYWRIGHT Y NO `node:22`. Se intentó con
#  `node:22` + `playwright install --with-deps`, y falla de una forma que sólo
#  se ve en la SEGUNDA corrida: el binario del navegador queda en el volumen
#  montado y persiste, pero las librerías del sistema que instala `--with-deps`
#  viven en el contenedor y se van con él. La primera corrida funciona; la
#  siguiente salta la instalación —porque el binario está— y el navegador no
#  arranca. El síntoma es "Target page, context or browser has been closed" en
#  las quince pruebas a la vez, que no se parece en nada a la causa.
#
#  `--add-host` hace que `host.docker.internal` resuelva al anfitrión también
#  en Linux; en Docker Desktop ya resuelve, y repetirlo no molesta.
set -e

#  EN GIT BASH LAS RUTAS SE TRADUCEN SOLAS, Y ESO ROMPE `docker`.
#
#  `-w /pruebas` llegaba al demonio como `C:/Program Files/Git/pruebas`. Son
#  dos arreglos y hacen falta los dos: `MSYS_NO_PATHCONV` apaga la traducción
#  de los argumentos, y `pwd -W` da la ruta en formato Windows, que es la que
#  Docker Desktop entiende para un montaje. En Linux y macOS, `pwd -W` no
#  existe y se cae a `pwd`, que ya es la correcta.
export MSYS_NO_PATHCONV=1
AQUI=$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })
IMAGEN=mcr.microsoft.com/playwright:v1.49.1-jammy

docker run --rm -t \
  -v "$AQUI":/pruebas \
  -w /pruebas \
  --add-host=host.docker.internal:host-gateway \
  -e PUERTO="${PUERTO:-55600}" \
  -e BASE="${BASE:-}" \
  -e USUARIO="${USUARIO:-admin@localhost}" \
  -e CLAVE="${CLAVE:-lab12345}" \
  -e ORG_CON="${ORG_CON:-MicroPyramid}" \
  -e ORG_SIN="${ORG_SIN:-Plumeline Media}" \
  -e CI=1 \
  "$IMAGEN" \
  sh /pruebas/dentro.sh "$@"
