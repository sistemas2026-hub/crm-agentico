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

LAS CUATRO DECISIONES, Y LA QUE NO SE PUEDE REGISTRAR TODAVIA
--------------------------------------------------------------
  seguir_humano            queda en manos de una persona, como hoy
  volver_ia                la IA la retoma
  cerrar_con_desenlace     cierra Y adopta, con un codigo elegido (--desenlace).
                           Disponible desde B6.
  resolver_estado_externo  NO todavia: es un efecto externo, no una transicion

La ultima falla con su motivo en vez de hacer algo parecido: registrar un
cierre que no cierra nada afuera seria decirle a quien revisa que el caso y el
ticket quedaron resueltos cuando siguen abiertos.

Si el desenlace falta o no esta en el catalogo, el comando imprime los codigos
validos y no escribe nada. No sugiere uno: elegir por el operador es
exactamente lo que B6 prohibe.
================================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import fuente                                  # noqa: E402
from nucleo.relevo import desenlaces                              # noqa: E402
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
    p.add_argument("--desenlace", default=None, metavar="CODIGO",
                   help="obligatorio con 'cerrar_con_desenlace'. Sale del "
                        "catalogo: --listar-desenlaces lo imprime. No hay "
                        "valor por defecto a proposito")
    p.add_argument("--nota", default=None,
                   help="texto corto del operador sobre el cierre. Sin datos "
                        "del cliente (X19)")
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

    # El catalogo de la empresa, si se puede leer. Sin config quedan los doce
    # de plataforma, que es lo que una empresa sin nada configurado tiene.
    try:
        config = fuente.cargar(args.tenant, RAIZ)
    except Exception as e:
        print(f"  [aviso] sin config de '{args.tenant}' ({type(e).__name__}): "
              f"solo el catalogo base de plataforma")
        config = None

    try:
        r = transiciones.adoptar_de_legado(
            args.tenant, args.conversacion, decision=args.decision,
            operador_id=args.operador_id, operador_nombre=args.operador,
            desenlace=args.desenlace, nota=args.nota, config=config,
            clave=args.clave)
    except NotImplementedError as e:
        print(f"\n  [NO SE PUEDE REGISTRAR] {e}\n")
        print("  La decision es valida; lo que falta es donde escribirla.")
        print("  Ver SPEC/auditorias/G8-LEGADO-WHATSAPP.md.")
        return 3
    except ValueError as e:
        print(f"\n  [RECHAZADO] {e}\n")
        if "desenlace" in str(e):
            print("  Codigos validos para este tenant:")
            for d in desenlaces.catalogo(config):
                print(f"    {d['codigo']:<24} {d['nombre']}")
            print("\n  Ninguno se elige solo: el que cierra decide cual.")
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
