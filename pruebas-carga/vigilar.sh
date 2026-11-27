#!/usr/bin/env bash
# LO QUE LE PASA AL SERVIDOR MIENTRAS DURA LA PRUEBA  --  24/11/2026
#
# Se corre EN EL SERVIDOR (por SSH), en otra ventana, mientras k6 corre desde
# afuera. k6 dice cuánto tardó cada pedido; esto dice POR QUÉ: si se acabó la
# CPU, la memoria o las conexiones a la base.
#
#   bash vigilar.sh                 # cada 5 s, hasta Ctrl+C
#   CADA=10 BASE=supabase-db bash vigilar.sh
#
# Deja dos archivos CSV al lado: contenedores-<hora>.csv y base-<hora>.csv.
# Solo LEE: docker stats y una consulta a pg_stat_activity.

set -u
CADA="${CADA:-5}"
#  El contenedor de Postgres. Si no se pasa, se busca uno cuyo nombre diga "db".
BASE="${BASE:-$(docker ps --format '{{.Names}}' | grep -E '(^|[-_])db([-_.]|$)' | head -1)}"
SELLO="$(date +%Y%m%d-%H%M%S)"
CONT="contenedores-$SELLO.csv"
BD="base-$SELLO.csv"

echo "hora,contenedor,cpu,memoria,red_entrada_salida" > "$CONT"
echo "hora,activas,en_espera,ociosas_en_transaccion,total,maximo" > "$BD"
echo "Vigilando cada ${CADA}s. Base: ${BASE:-ninguna}. Ctrl+C para terminar."

while true; do
  HORA="$(date +%H:%M:%S)"
  docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}}" \
    | sed "s/^/$HORA,/" >> "$CONT"

  if [ -n "$BASE" ]; then
    FILA="$(docker exec "$BASE" psql -U postgres -At -F, -c "
      select count(*) filter (where state = 'active'),
             count(*) filter (where wait_event_type = 'Lock'),
             count(*) filter (where state = 'idle in transaction'),
             count(*),
             current_setting('max_connections')
      from pg_stat_activity where backend_type = 'client backend'" 2>/dev/null)"
    [ -n "$FILA" ] && echo "$HORA,$FILA" >> "$BD"
  fi

  # Una línea en pantalla para ver que avanza: lo que más CPU usa ahora.
  docker stats --no-stream --format "{{.CPUPerc}} {{.Name}}" | sort -rn | head -1 | sed "s/^/$HORA  más cargado: /"
  sleep "$CADA"
done
