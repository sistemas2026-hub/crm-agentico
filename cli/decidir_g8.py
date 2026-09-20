# -*- coding: utf-8 -*-
"""
================================================================================
 DECIDIR G8  --  registrar lo que una persona decidio sobre una conversacion
================================================================================

    DBHOST=... DBPORT=... DBNAME=... DBUSER=... DBPASSWORD=... \\
      py -3.13 cli/decidir_g8.py --tenant rapilink \\
        --conversacion <uuid> --decision seguir_humano \\
        --operador-id <uuid> --operador "Ana Gomez"

ESCRIBE. Una conversacion por invocacion, a proposito.

POR QUE UNA POR UNA
-------------------
§11.2 no dice "revisar las 16": dice que una persona las revisa **una por una**
y decide para cada una. Un comando que aceptara una lista convertiria eso en un
tramite, y el tramite es justamente lo que el gate existe para impedir --que 16
conversaciones de clientes se resuelvan con un gesto.

No hay '--todas'. No hay '--desde-archivo'. Y la clasificacion A/B/C que
produce 'revision_g8.py' NO llega hasta aca: esa herramienta es de solo lectura
y no puede escribir aunque alguien se lo pidiera.

LAS CUATRO DECISIONES, Y LAS DOS QUE NO SE PUEDEN REGISTRAR TODAVIA
-------------------------------------------------------------------
  seguir_humano            queda en manos de una persona, como hoy
  volver_ia                la IA la retoma
  cerrar_con_desenlace     NO todavia: el desenlace es B6
  resolver_estado_externo  NO todavia: es un efecto externo, no una transicion

Las dos ultimas fallan con su motivo en vez de hacer algo parecido. Registrar
un cierre sin desenlace seria cerrar la conversacion de un cliente sin decir
por que, en el registro que existe para poder decirlo.
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.relevo import transiciones                            # noqa: E402


def construir_parser():
    """El parser, aparte, para que una prueba pueda comprobar QUE ACEPTA el
    comando en vez de buscar cadenas en el archivo -- el docstring de arriba
    nombra '--todas' justamente para decir que no existe."""
    p = argparse.ArgumentParser(
        description="Registra la decision humana de G8 sobre UNA conversacion")
    p.add_argument("--tenant", required=True)
    p.add_argument("--conversacion", required=True, metavar="UUID")
    p.add_argument("--decision", required=True,
                   choices=list(transiciones.DECISIONES_G8))
    p.add_argument("--operador-id", required=True, metavar="UUID",
                   help="el id del usuario que decide. Obligatorio: una "
                        "adopcion sin responsable no se puede auditar")
    p.add_argument("--operador", required=True, metavar="NOMBRE")
    p.add_argument("--clave", default=None,
                   help="clave de idempotencia. Repetir la misma decision con "
                        "la misma clave no escribe dos veces")
    return p


def main():
    args = construir_parser().parse_args()

    faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
              if not os.environ.get(v)]
    if faltan:
        print(f"[g8] faltan variables de conexion: {faltan}")
        return 2

    try:
        r = transiciones.adoptar_de_legado(
            args.tenant, args.conversacion, decision=args.decision,
            operador_id=args.operador_id, operador_nombre=args.operador,
            clave=args.clave)
    except NotImplementedError as e:
        print(f"\n  [NO SE PUEDE REGISTRAR] {e}\n")
        print("  La decision es valida; lo que falta es donde escribirla.")
        print("  Ver SPEC/auditorias/G8-LEGADO-WHATSAPP.md.")
        return 3
    except ValueError as e:
        print(f"\n  [RECHAZADO] {e}\n")
        return 2

    if r.aplicada:
        print(f"\n  [registrado] {args.decision}   version {r.version}"
              f"   evento {r.evento_id}")
        print(f"  conversacion {args.conversacion}")
        return 0

    print(f"\n  [sin cambios] {r.motivo}")
    if r.motivo == "ya_adoptada":
        print("  Alguien ya decidio sobre esta conversacion. No se pisa: "
              "mirar el evento anterior.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
