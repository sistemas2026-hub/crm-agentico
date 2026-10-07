# -*- coding: utf-8 -*-
"""
================================================================================
 CARGA HISTORICA  --  los tickets abiertos que la ventana movil nunca alcanza
================================================================================

    py -3.13 cli/importar_historico.py rapilink --desde 2025-04-29
    py -3.13 cli/importar_historico.py rapilink --desde 2025-04-29 --detalle
    py -3.13 cli/importar_historico.py rapilink --desde 2025-04-29 --aplicar

POR QUE EXISTE
--------------
El reloj mira una ventana MOVIL de 'ventana_dias' (hoy 30) por fecha de
creacion. Un ticket que sigue abierto pero nacio antes de esa ventana no entra
nunca, por mas veces que el ciclo corra: cada pasada mira los mismos 30 dias.

Medido en produccion el 07/10/2026, contando solo desde enero: 835 tickets
abiertos en WispHub y 710 sin caso en Dexter. De Finanzas eran 545. No es un
fallo del reloj -- es el precio de la ventana movil, y se paga una sola vez
con una carga como esta.

QUE NO ES
---------
No reemplaza al reloj ni lo modifica. Es una pasada UNICA hacia atras; cuando
termina, el ciclo sigue con su ventana de 30 dias exactamente como estaba.

POR QUE EN TRAMOS DE 55 DIAS
-----------------------------
El proveedor responde HTTP 400 a cualquier rango mayor a dos meses -- probado
el 07/10/2026 pidiendo '2026-01-01 -> 2026-10-07'. El tope de 55 deja margen
y es el mismo que ya usa 'imp.ventana'. De abril de 2025 a hoy son 10 tramos.

LAS MISMAS REGLAS QUE EL RELOJ, A PROPOSITO
--------------------------------------------
Los tickets pasan por 'imp.descubrir', igual que en el ciclo: mismo filtro de
departamento, misma whitelist de asuntos, mismo reparto por area, misma
clasificacion de autoria. Un historico que importara con criterio propio
crearia casos que el ciclo nunca habria creado, y la diferencia solo se
notaria meses despues.

SE PUEDE REPETIR SIN MIEDO
---------------------------
La idempotencia no la pone este comando: la pone
UNIQUE(org, provider, external_ticket_id) del otro lado. Un ticket que ya
tiene caso vuelve como 'ya_estaban' y no se toca. Si la corrida se interrumpe
a la mitad, se vuelve a lanzar y sigue.
================================================================================
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

from nucleo.config import fuente                      # noqa: E402
from nucleo.persistencia import db as persistencia    # noqa: E402
from nucleo.seguimiento import importacion as imp     # noqa: E402
from nucleo.seguimiento.importacion_io import (       # noqa: E402
    aplicar, listar_tickets, resolver_servicios, tickets_conocidos)

#  El proveedor rechaza rangos de mas de dos meses. 55 deja margen y es el
#  mismo tope que ya aplica 'imp.ventana'.
DIAS_POR_TRAMO = 55


def tramos(desde: date, hasta: date):
    """Los tramos de 55 dias que cubren el rango, del mas viejo al mas nuevo."""
    cursor = desde
    while cursor <= hasta:
        fin = min(cursor + timedelta(days=DIAS_POR_TRAMO - 1), hasta)
        yield cursor.isoformat(), fin.isoformat()
        cursor = fin + timedelta(days=1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Importa los tickets ABIERTOS anteriores a la ventana del reloj.")
    p.add_argument("tenant", help="slug del tenant, ej. 'rapilink'")
    p.add_argument("--desde", required=True, metavar="AAAA-MM-DD",
                   help="fecha del ticket abierto mas viejo que se quiere traer")
    p.add_argument("--hasta", metavar="AAAA-MM-DD",
                   help="por omision, hoy")
    p.add_argument("--detalle", action="store_true",
                   help="una linea por ticket que entraria")
    p.add_argument("--aplicar", action="store_true",
                   help="ESCRIBE los casos. Sin esto solo informa.")
    args = p.parse_args(argv)

    try:
        desde = date.fromisoformat(args.desde)
        hasta = date.fromisoformat(args.hasta) if args.hasta else datetime.now().date()
    except ValueError as e:
        print(f"[historico] fecha invalida: {e}")
        return 2
    if desde > hasta:
        print("[historico] '--desde' es posterior a '--hasta'.")
        return 2

    config = fuente.cargar(args.tenant, RAIZ)
    conf = config.importacion_tickets
    if not conf.proveedor:
        print("[historico] el tenant no tiene 'proveedor' en importacion_tickets.")
        return 2

    lista = list(tramos(desde, hasta))
    print(f"\n  CARGA HISTORICA  --  {args.tenant}")
    print(f"  {desde} -> {hasta}   ({len(lista)} tramos de hasta {DIAS_POR_TRAMO} dias)")
    print(f"  estados: {conf.estados_descubrimiento or '(ninguno: no traeria nada)'}")
    print(f"  departamentos: {conf.departamentos}")
    if not conf.estados_descubrimiento:
        print("\n[historico] sin 'estados_descubrimiento' no hay nada que pedir.")
        return 2

    #  1. TRAER. Un tramo que falla no corta la corrida: se anota y se sigue,
    #     porque perder 55 dias por un timeout obligaria a repetir todo.
    por_id: dict[str, dict] = {}
    fallidos: list[str] = []
    for i, (d, h) in enumerate(lista, 1):
        try:
            tickets = listar_tickets(config, args.tenant, d, h)
            for t in tickets:
                tid = str(t.get("id_ticket") or "")
                if tid:
                    por_id[tid] = t
            print(f"   [{i:>2}/{len(lista)}] {d} -> {h}   {len(tickets):>4} tickets"
                  f"   acumulado {len(por_id)}")
        except Exception as e:                                   # noqa: BLE001
            fallidos.append(f"{d} -> {h}: {type(e).__name__}")
            print(f"   [{i:>2}/{len(lista)}] {d} -> {h}   FALLO: {type(e).__name__}")

    if fallidos:
        print(f"\n  [aviso] {len(fallidos)} tramo(s) no se pudieron leer. Los tickets")
        print("          de esos tramos NO entran en este informe ni en la escritura.")

    tickets = list(por_id.values())
    if not tickets:
        print("\n  No se obtuvo ningun ticket. Nada que hacer.")
        return 1 if fallidos else 0

    #  2. CLASIFICAR con las mismas reglas del reloj.
    ids = [str(t.get("id_ticket")) for t in tickets if t.get("id_ticket")]
    conocidos, registro = tickets_conocidos(config, args.tenant, ids)
    areas_por_persona = persistencia.areas_de_colaboradores(args.tenant)
    print(f"\n  ya tienen caso en Dexter: {len(conocidos)} de {len(ids)}")
    print(f"  colaboradores con area  : {len(areas_por_persona)}"
          f"  {sorted(set(areas_por_persona.values()))}")

    veredictos = imp.descubrir(
        config, tickets,
        conocidos=conocidos,
        registrados_por_dexter=registro,
        areas_por_persona=areas_por_persona,
        cuenta_api=conf.cuenta_api,
        servicio_placeholder=(config.variables_tenant or {}).get(
            "WISPHUB_ID_SERVICIO_INSTALACIONES", ""),
        resolver_servicio=resolver_servicios(config, args.tenant))

    print(f"\n  {'=' * 66}")
    for resultado, n in Counter(v.resultado for v in veredictos).most_common():
        print(f"    {resultado:<34} {n}")
    candidatos = [v for v in veredictos if v.resultado == imp.CANDIDATO]
    print(f"  {'=' * 66}")
    print(f"    ENTRARIAN: {len(candidatos)}")
    if candidatos:
        print(f"    por area : {dict(Counter(v.area for v in candidatos))}")
        #  La carga por persona importa tanto como el total: un historico que
        #  le cae entero a una sola persona no es una cola, es un archivo.
        print(f"    por responsable: {dict(Counter(v.responsable for v in candidatos))}")
    if args.detalle:
        print()
        for v in candidatos:
            print(f"      {v.external_ticket_id:<9} {v.departamento:<16} "
                  f"{(v.asunto or '')[:34]:<36} -> {v.area}")

    if not args.aplicar:
        print(f"\n  EN SECO: no se escribio nada.")
        print(f"  Para aplicar:  py -3.13 cli/importar_historico.py {args.tenant} "
              f"--desde {args.desde} --aplicar\n")
        return 0

    if not candidatos:
        print("\n  No hay candidatos: no hay nada que escribir.\n")
        return 0

    #  3. ESCRIBIR. Con actor, asi entra por la puerta HUMANA de la frontera:
    #     este comando lo corre una persona, no el agente.
    #
    #     LIMITE, el mismo que declara cli/importar_tickets.py: el usuario del
    #     sistema dice QUIEN corrio el comando, no PRUEBA que fuera una
    #     persona. Lo que queda garantizado es la atribucion.
    actor = f"cli:{getpass.getuser()}"
    print(f"\n  {'=' * 66}")
    print(f"  APLICANDO  --  esto ESCRIBE casos en el CRM   (actor: {actor})")
    print(f"  {'=' * 66}")
    r = aplicar(config, args.tenant, veredictos, actor=actor)
    print(f"    creados ..... {r['creados']}")
    print(f"    ya estaban .. {r['ya_estaban']}")
    print(f"    fallidos .... {r['fallidos']}")
    print()
    print("  El reloj sigue como estaba: ventana movil de "
          f"{conf.ventana_dias} dias. Esto no lo toco.\n")
    return 1 if r["fallidos"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
