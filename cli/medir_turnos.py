# -*- coding: utf-8 -*-
"""
Los tres numeros de un turno, por dia y por canal.

    py -3.13 cli/medir_turnos.py rapilink
    py -3.13 cli/medir_turnos.py rapilink --dias 7

POR QUE EXISTE
--------------
El 08/09/2026 se desactivo el razonamiento del modelo ('thinking'), que en
banco de pruebas daba 4.26s contra 1.77s por llamada, y en los 51 casos
dorados no costo calidad (50/51, y el unico fallo era un timeout externo que
ya fallaba antes).

Un banco de pruebas y 51 casos NO son produccion. Lo que decide si el cambio
sirve son tres numeros seguidos varios dias, y separados -- porque pueden
moverse en direcciones opuestas y un promedio los taparia:

    cuanto espera el cliente
    cuanto cuesta el turno
    con que frecuencia termina mal (escalado o error de herramienta)

Si el tercero sube mientras los dos primeros bajan, el cambio esta pagando
rapidez con calidad y hay que revertirlo. Ese es justamente el fallo que un
promedio de latencia no muestra.

NO CALCULA NADA QUE NO ESTE MEDIDO. 'latencia_ms', 'llamadas_modelo' y los
tokens por mensaje existen desde el 08/09/2026; antes de esa fecha las
columnas estan vacias y las filas se omiten en vez de contarse como cero.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv                                   # noqa: E402
load_dotenv(RAIZ / ".env", override=False)

from nucleo.persistencia.db import sesion                        # noqa: E402


def informe(tenant: str, dias: int = 7) -> None:
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select m.creado_en::date d, cv.canal,
                      count(*) turnos,
                      percentile_cont(0.5) within group (order by m.latencia_ms) p50,
                      percentile_cont(0.95) within group (order by m.latencia_ms) p95,
                      avg(m.llamadas_modelo) llamadas,
                      sum(m.costo_usd) costo,
                      avg(m.tokens_entrada) entrada
                 from asistente.messages m
                 join asistente.conversations cv on cv.id = m.conversation_id
                where m.organization_id = %s and m.rol = 'assistant'
                  and m.latencia_ms is not null
                  and m.creado_en > now() - make_interval(days => %s)
                group by 1, 2 order by 1 desc, 3 desc""",
            (org, dias))
        filas = cur.fetchall()

        if not filas:
            print("Todavia no hay turnos medidos. Las columnas se llenan desde\n"
                  "el 08/09/2026 -- hace falta trafico posterior a esa fecha.")
            return

        print(f"  {'dia':11s} {'canal':18s} {'turnos':>6s} {'mediana':>8s} "
              f"{'p95':>7s} {'llamadas':>9s} {'entrada':>9s} {'costo':>9s}")
        for f in filas:
            # Un turno anterior al 08/09 tiene latencia pero no tokens: se
            # muestra con guion en vez de un 0 que se leeria como "salio
            # gratis".
            llam = f"{f['llamadas']:9.1f}" if f['llamadas'] is not None else f"{'-':>9s}"
            ent = f"{f['entrada']:9,.0f}" if f['entrada'] is not None else f"{'-':>9s}"
            print(f"  {f['d']:%d/%m}       {f['canal']:18s} {f['turnos']:6d} "
                  f"{f['p50']/1000:7.1f}s {f['p95']/1000:6.1f}s "
                  f"{llam} {ent} ${float(f['costo'] or 0):8.4f}")

        # El tercer numero, y el que decide si la rapidez salio cara.
        cur.execute(
            """select cv.canal,
                      count(*) conv,
                      count(*) filter (where cv.escalada_a_humano) escaladas,
                      (select count(*) from asistente.tool_calls t
                        where t.organization_id = %s and not t.exito
                          and not t.es_bloqueo
                          and t.creado_en > now() - make_interval(days => %s)) errores
                 from asistente.conversations cv
                where cv.organization_id = %s
                  and cv.creado_en > now() - make_interval(days => %s)
                group by 1 order by 2 desc""",
            (org, dias, org, dias))
        print(f"\n  {'canal':18s} {'conversaciones':>14s} {'escaladas':>10s} "
              f"{'% escalado':>11s}")
        for f in cur.fetchall():
            pct = 100.0 * f["escaladas"] / max(f["conv"], 1)
            print(f"  {f['canal']:18s} {f['conv']:14d} {f['escaladas']:10d} "
                  f"{pct:10.1f}%")
        print("\n  Si el % escalado o los errores SUBEN mientras la latencia baja,\n"
              "  la rapidez se esta pagando con calidad.")


if __name__ == "__main__":
    tenant = sys.argv[1] if len(sys.argv) > 1 else "rapilink"
    dias = 7
    if "--dias" in sys.argv:
        dias = int(sys.argv[sys.argv.index("--dias") + 1])
    print(f"\nTurnos medidos de '{tenant}', ultimos {dias} dia(s)\n")
    informe(tenant, dias)
