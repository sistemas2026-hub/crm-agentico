# -*- coding: utf-8 -*-
"""
================================================================================
 CUÁNTAS CONVERSACIONES TERMINARÍAN PREGUNTÁNDOLE AL CLIENTE
================================================================================

    py -3.13 cli/medir_cuantos_preguntarian.py rapilink
    py -3.13 cli/medir_cuantos_preguntarian.py rapilink --dias 30

POR QUÉ EXISTE
--------------
El objetivo abierto `el-agente-sabe-cuando-no-sabe.md` tiene como paso 3
**preguntarle al cliente antes de despachar y antes de cerrar**. Es lo único
que un agente hace mejor que un supervisor humano, y no por criterio sino por
VOLUMEN: una persona no le puede escribir a cuarenta clientes; un agente sí.

Pero es también el primer paso que **manda mensajes a clientes reales**. Antes
de diseñarlo hace falta el número, porque diez por día y cuatrocientos por día
son dos productos distintos: cambian el canal, el tono, el momento, y si acaso
conviene.

Esto NO manda nada. Cuenta sobre lo que ya pasó.

QUÉ CUENTA, Y POR QUÉ CADA COSA
-------------------------------
La regla congelada (CLAUDE.md §12) dice que `ACCION_CONFIRMADA` **no** significa
que el problema del cliente esté resuelto: *«que la casa tenga internet no lo
dice ningún endpoint: lo sabe el cliente, y hay que preguntárselo»*. Así que la
pregunta no es retórica — es el único cierre posible para esos casos.

    acciones con efecto    cada una es una candidata: hicimos algo y no
                           sabemos si le sirvió
    conversaciones reales  `canal = 'whatsapp'` y nada más (decisión del
                           25/09: los otros canales son pruebas)
    las que escalaron      ahí ya hay una persona; preguntar sería redundante
    las que NO escalaron   **estas son las que hoy no cierra nadie**

LO QUE NO PUEDE MEDIR, y hay que decirlo
----------------------------------------
No sabe si al cliente le sirvió. Ese es justamente el dato que no existe, y la
razón de todo esto. Lo que da es la COTA: cuántas preguntas habría que mandar.
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv                                   # noqa: E402

load_dotenv()

from nucleo.persistencia.db import sesion                        # noqa: E402

ZONA = "America/Bogota"

#:  Las que producen un efecto que el cliente nota y que el sistema NO puede
#:  confirmar que haya resuelto su problema. `reiniciar_ont` es el caso
#:  canónico: se mide que el equipo reinició (`last_status_change`), no que la
#:  casa tenga internet.
CON_EFECTO = ("reiniciar_ont", "activar_catv", "cambiar_tipo_onu",
              "registrar_pedido_wifi")


def medir(cur, org: str, dias: int) -> dict:
    #  UNA CONVERSACIÓN, NO UNA LLAMADA. Si el agente reinició dos veces en la
    #  misma charla, es UNA pregunta al final, no dos. Contar llamadas
    #  sobreestimaría el volumen, que es justo el número que se quiere afinar.
    cur.execute(
        """select count(distinct t.conversation_id)
             from asistente.tool_calls t
             join asistente.conversations cv on cv.id = t.conversation_id
            where t.organization_id = %s
              and t.creado_en > now() - make_interval(days => %s)
              and t.herramienta = any(%s)
              and t.exito
              and cv.canal = 'whatsapp'""",
        (org, dias, list(CON_EFECTO)))
    con_accion = cur.fetchone()["count"]

    #  DE ESAS, LAS QUE YA TIENEN UNA PERSONA ENCIMA. Preguntarle al cliente
    #  mientras un compañero le está escribiendo es la redundancia que el
    #  proyecto ya midió y decidió evitar en otro lado.
    cur.execute(
        """select count(distinct t.conversation_id)
             from asistente.tool_calls t
             join asistente.conversations cv on cv.id = t.conversation_id
            where t.organization_id = %s
              and t.creado_en > now() - make_interval(days => %s)
              and t.herramienta = any(%s)
              and t.exito
              and cv.canal = 'whatsapp'
              and cv.escalada_a_humano""",
        (org, dias, list(CON_EFECTO)))
    escaladas = cur.fetchone()["count"]

    #  EL UNIVERSO, para saber qué proporción es. Un 2% y un 60% piden
    #  productos distintos aunque el número absoluto sea el mismo.
    cur.execute(
        """select count(*) from asistente.conversations
            where organization_id = %s
              and creado_en > now() - make_interval(days => %s)
              and canal = 'whatsapp'""",
        (org, dias))
    total = cur.fetchone()["count"]

    #  Y EL DESGLOSE POR HERRAMIENTA: si el 90% es `reiniciar_ont`, la
    #  pregunta se escribe una vez y no cuatro.
    cur.execute(
        """select t.herramienta, count(distinct t.conversation_id) n
             from asistente.tool_calls t
             join asistente.conversations cv on cv.id = t.conversation_id
            where t.organization_id = %s
              and t.creado_en > now() - make_interval(days => %s)
              and t.herramienta = any(%s)
              and t.exito
              and cv.canal = 'whatsapp'
            group by 1 order by 2 desc""",
        (org, dias, list(CON_EFECTO)))
    por_herramienta = cur.fetchall()

    return {"total": total, "con_accion": con_accion, "escaladas": escaladas,
            "preguntarian": con_accion - escaladas,
            "por_herramienta": por_herramienta}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tenant")
    ap.add_argument("--dias", type=int, default=30)
    args = ap.parse_args()

    #  `sesion(tenant)` entrega (cursor, organization_id) con el tenant YA
    #  fijado y el rol degradado a 'app_backend': el aislamiento lo da
    #  `set local role` + `set local app.current_tenant`, no la consulta. Se
    #  usa esta puerta y no una conexión propia justamente por eso (§5).
    with sesion(args.tenant) as (cur, org):
        r = medir(cur, org, args.dias)

    print("=" * 72)
    print(f"  CUÁNTAS PREGUNTARÍAN  --  {args.tenant}, últimos {args.dias} días")
    print("=" * 72)
    print()
    print(f"  conversaciones reales (whatsapp)        {r['total']:>6}")
    print(f"  con una acción de efecto, exitosa       {r['con_accion']:>6}")
    print(f"     de esas, ya escaladas a una persona  {r['escaladas']:>6}"
          "   <- no se pregunta: ya hay alguien")
    print()
    print(f"  **PREGUNTARÍAN**                        {r['preguntarian']:>6}", end="")
    if args.dias:
        print(f"   ({r['preguntarian'] / args.dias:.1f} por día)")
    else:
        print()
    if r["total"]:
        print(f"  es el {100 * r['preguntarian'] / r['total']:.1f}% de las conversaciones")
    print()
    print("  por herramienta:")
    for f in (r["por_herramienta"] or []):
        print(f"     {f['herramienta']:<28} {f['n']:>5}")
    if not r["por_herramienta"]:
        print("     (ninguna)")
    print()
    print("  Lo que esto NO dice: si al cliente le sirvió. Ese dato no existe,")
    print("  y es la razón de preguntarle. Esto es la COTA de cuántas preguntas.")
    print("=" * 72)


if __name__ == "__main__":
    main()
