# -*- coding: utf-8 -*-
"""
================================================================================
 AUTORIZAR UNA HERRAMIENTA  --  la puerta que la tabla no tenia
================================================================================

    py -3.13 cli/autorizar_herramienta.py rapilink
    py -3.13 cli/autorizar_herramienta.py rapilink --autorizar importar_caso_externo \\
        --nivel 2 --actor marioth727 --motivo "sincronizacion WispHub -> Dexter"
    py -3.13 cli/autorizar_herramienta.py rapilink --revocar reiniciar_ont \\
        --actor marioth727 --motivo "se revisa el procedimiento"

POR QUE EXISTE
--------------
'asistente.autorizacion_herramienta' se creo el 22/09/2026, el lector existe y
la frontera la exige antes de CADA accion autonoma. Lo que nunca se escribio
fue la forma de conceder: ninguna linea del repositorio insertaba una fila, y
las pruebas sustituian el lector.

Medido en produccion el 06/10/2026, con la tabla en 0 filas: el reloj intento
2 importaciones, 177 reconciliaciones y 146 sincronizaciones de hilo, y las
325 murieron con HERRAMIENTA_SIN_AUTORIZACION. No era un permiso mal puesto:
era una puerta sin picaporte.

LO QUE ESTE COMANDO NO HACE
---------------------------
No toca el kill switch, no mueve el techo, no cambia la etapa de autonomia y
no edita el catalogo del tenant. Autoriza UNA herramienta, hasta un nivel, con
nombre y motivo. Las cuatro compuertas siguen aplicando en el mismo orden:

    kill switch -> techo -> etapa -> ESTA autorizacion

y la autorizacion mas generosa del mundo no ejecuta nada si cualquiera de las
tres anteriores dice que no. Acota, no habilita por su cuenta.

QUIEN PUEDE
-----------
Escribe con el rol 'autonomia_operador', no con el del runtime. La base ya lo
impone --'app_backend' tiene SELECT y nada mas sobre esta tabla-- asi que el
motor no puede concederse lo que la frontera acaba de negarle, ni aunque
alguien escriba el codigo para intentarlo.

SOLO SE AGREGA
--------------
Revocar escribe una fila nueva con estado='revocada'. No se borra nada: meses
despues tiene que poder reconstruirse quien autorizo que, cuando y por que.
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

from nucleo.persistencia import db  # noqa: E402

NIVELES = {0: "observar", 1: "recomendar", 2: "coordinar",
           3: "ejecutar reversible", 4: "critico"}


def _listar(tenant: str) -> int:
    filas = db.autorizaciones_vigentes(tenant)
    print(f"\n  AUTORIZACIONES DE {tenant}\n" + "  " + "-" * 64)
    if not filas:
        #  La lista vacia es informacion, y es la que explico el bloqueo del
        #  06/10: sin filas, la frontera niega TODO lo autonomo.
        print("  (ninguna)\n")
        print("  Sin una fila aqui, la frontera responde")
        print("  HERRAMIENTA_SIN_AUTORIZACION a toda accion autonoma, tenga el")
        print("  techo que tenga la empresa. Falla cerrado a proposito.\n")
        return 0
    for f in filas:
        marca = "ok " if f["estado"] == "autorizada" else "REV"
        hasta = f["vigente_hasta"].isoformat() if f["vigente_hasta"] else "sin vencimiento"
        print(f"  [{marca}] {f['herramienta']:<34} nivel {f['nivel_maximo']} "
              f"({NIVELES.get(f['nivel_maximo'], '?')})")
        print(f"        por {f['autorizado_por']} el "
              f"{f['creado_en']:%Y-%m-%d %H:%M} · {hasta}")
        if f["motivo"]:
            print(f"        {f['motivo']}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Autoriza o revoca una herramienta para la ejecucion autonoma.")
    p.add_argument("tenant", help="slug del tenant, ej. 'rapilink'")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--autorizar", metavar="HERRAMIENTA",
                       help="habilita esa herramienta para la ejecucion autonoma")
    grupo.add_argument("--revocar", metavar="HERRAMIENTA",
                       help="deja de habilitarla (escribe una fila nueva)")
    p.add_argument("--nivel", type=int, default=None,
                   help="nivel maximo que habilita (0..4). Obligatorio al autorizar")
    p.add_argument("--actor", default="",
                   help="quien autoriza (obligatorio)")
    p.add_argument("--motivo", default="",
                   help="por que (obligatorio)")
    args = p.parse_args(argv)

    if not args.autorizar and not args.revocar:
        try:
            return _listar(args.tenant)
        except Exception as e:                                   # noqa: BLE001
            print(f"[autorizar] no se pudieron leer las autorizaciones: "
                  f"{type(e).__name__}: {e}")
            return 1

    #  ACTOR Y MOTIVO SIEMPRE, igual que en el interruptor. Quien encuentre una
    #  herramienta habilitada tiene que poder saber quien la habilito y por que
    #  -- una autorizacion sin firma es indistinguible de un descuido.
    if not args.actor.strip() or not args.motivo.strip():
        print("[autorizar] hacen falta --actor y --motivo. Una autorizacion sin "
              "firma no se registra.")
        return 2

    herramienta = (args.autorizar or args.revocar).strip()
    estado = "autorizada" if args.autorizar else "revocada"

    if estado == "autorizada" and args.nivel is None:
        print("[autorizar] --nivel es obligatorio al autorizar: decir 'puede' "
              "sin decir 'hasta donde' no es una autorizacion.")
        return 2
    #  Revocar no necesita nivel; se guarda 0 para que la fila sea valida sin
    #  sugerir que habilita algo.
    nivel = args.nivel if args.nivel is not None else 0

    try:
        fila = db.registrar_autorizacion_herramienta(
            args.tenant, herramienta, estado, nivel,
            autorizado_por=args.actor, motivo=args.motivo)
    except ValueError as e:
        print(f"[autorizar] {e}")
        return 2
    except Exception as e:                                       # noqa: BLE001
        print(f"[autorizar] no se pudo registrar: {type(e).__name__}: {e}")
        return 1

    antes = fila["estado_anterior"] or "(sin autorizacion previa)"
    print(f"\n  {args.tenant} · {fila['herramienta']}")
    print(f"  {antes} -> {fila['estado']}  (nivel {fila['nivel_maximo']}, "
          f"{NIVELES.get(fila['nivel_maximo'], '?')})")
    print(f"  por {fila['autorizado_por']}: {fila['motivo']}\n")
    if estado == "autorizada":
        print("  Esto NO ejecuta nada por si solo: el kill switch, el techo y")
        print("  la etapa de autonomia siguen aplicando antes que esta puerta.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
