#!/bin/sh
#
#  Lo que corre DENTRO del contenedor. Vive en su propio archivo y no inline en
#  `correr.sh` porque un script dentro de comillas dentro de `docker run` es
#  exactamente donde se pierden las comillas, y el síntoma es un error de
#  sintaxis que no señala a nada.
set -e

#  EL LABORATORIO SE ALCANZA COMO `localhost`, Y NO ES UN CAPRICHO.
#
#  Dos cosas lo exigen, y las dos se midieron el 31/10/2026:
#
#  1. Vite comprueba la cabecera `Host` y devuelve 403 a
#     `host.docker.internal`, que no está en su `allowedHosts`.
#
#  2. Y lo serio: la cookie `org` —la que recuerda qué empresa se eligió— se
#     fija sin declarar `secure`, y SvelteKit la pone `Secure` por defecto en
#     CUALQUIER host que no sea localhost. Sobre `http://` el navegador la
#     rechaza en silencio: elegir empresa devolvía 303 a `/`, `/` no
#     encontraba la empresa y rebotaba a `/org`. El síntoma era «no encuentro
#     el edificio» trece pruebas más tarde, y la causa estaba en una cookie
#     que nunca llegó a guardarse.
#
#  Así que se abre un reenvío de `127.0.0.1:$PUERTO` a la pasarela del
#  anfitrión. El navegador ve `localhost` —contexto seguro, y pasa el control
#  de `Host`— sin tocar nada del frontend, que es código que se despliega.
if [ -z "$BASE" ]; then
  IP=$(getent ahostsv4 host.docker.internal | head -1 | awk '{print $1}')
  node /pruebas/reenvio.cjs "$PUERTO" "$IP" &
  #  Se espera a que el reenvío ACEPTE, en vez de dormir un número.
  i=0
  while [ "$i" -lt 60 ]; do
    if node -e 'require("net").connect(+process.argv[1],"127.0.0.1").on("connect",()=>process.exit(0)).on("error",()=>process.exit(1))' "$PUERTO" 2>/dev/null; then
      break
    fi
    i=$((i + 1))
    sleep 0.2
  done
  BASE="http://localhost:$PUERTO"
  export BASE
  echo "contra $BASE  (reenviado a $IP:$PUERTO)"
else
  echo "contra $BASE"
fi

test -d node_modules || npm install --no-audit --no-fund
exec npx playwright test "$@"
