# -*- coding: utf-8 -*-
"""
================================================================================
 EL INTERRUPTOR DE AUTONOMIA, DESDE LA LINEA DE COMANDOS
================================================================================

    py -3.13 cli/autonomia.py rapilink                          (estado e historial)
    py -3.13 cli/autonomia.py rapilink --detener \\
        --actor "nombre de quien decide" --motivo "por que"
    py -3.13 cli/autonomia.py rapilink --reactivar \\
        --actor "nombre de quien decide" --motivo "por que"

    py -3.13 cli/autonomia.py rapilink --techo 1 --desde ninguno \\
        --actor "nombre de quien decide" --motivo "por que"   (M06-B)

EL TECHO (M06-B)
----------------
'--techo N' fija HASTA QUE NIVEL puede actuar sola la empresa (0 observar,
1 recomendar, 2 coordinar, 3 ejecutar autorizado; 3 es el tope de politica).
Es un techo, no un permiso: no ejecuta nada por si solo. '--desde' es el techo
que viste antes de pedir el cambio ('ninguno' si no habia): si entretanto otro
operador lo movio, el cambio NO se aplica y hay que volver a mirar. Cada
intento queda en asistente.techo_autonomia_intentos. Este comando es el UNICO
camino por el que se mueve el techo.

POR QUE EXISTE ADEMAS DE LAS RUTAS HTTP
---------------------------------------
Porque el momento en que hace falta tirar el interruptor es, muchas veces, el
momento en que algo no anda. Si la unica forma de pararlo fuera una pantalla
que habla con el motor, que habla con la base, cualquier problema en esa cadena
dejaria el interruptor fuera de alcance justo cuando se lo necesita.

Esto habla con la base y con nadie mas: no carga la configuracion del tenant,
no llama al motor, no necesita que el frontend este arriba.

QUE HACE Y QUE NO
-----------------
Detenido, la empresa deja de ejecutar acciones autonomas -- escrituras contra
sistemas externos decididas por el modelo, y trabajos del scheduler. Sigue
atendiendo conversaciones y sigue consultando. Ver el encabezado de
nucleo/seguridad/interruptor.py.

'--actor' y '--motivo' son obligatorios para mover el interruptor, en los dos
sentidos. No es burocracia: quien encuentra el sistema detenido un lunes a la
mañana necesita saber quien lo paro y por que antes de decidir si puede
levantarlo.

CODIGOS DE SALIDA
-----------------
  0  la consulta salio bien, o el interruptor se movio
  1  no se pudo leer o escribir el interruptor
  2  uso invalido (falta el tenant, falta --actor o --motivo)
  3  solo consulta: la autonomia NO esta permitida (para encadenar en scripts)
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import uuid                                                      # noqa: E402

from nucleo.seguridad import interruptor                         # noqa: E402
from nucleo.seguridad import techo as techos                     # noqa: E402


def _mostrar(tenant: str) -> int:
    veredicto = interruptor.veredicto(tenant)
    marca = "PERMITIDA" if veredicto.permitido else "DETENIDA"
    print(f"\n  {tenant}: autonomia {marca}  (estado '{veredicto.estado}')")
    print(f"  motivo: {veredicto.motivo}")
    if veredicto.actor:
        print(f"  ultimo movimiento por: {veredicto.actor}")
    nivel, fallo = techos.leer(tenant)
    if fallo is not None:
        print(f"  techo: SIN TECHO VALIDO ({fallo.codigo}) -- no ejecuta nada solo")
    else:
        print(f"  techo: {nivel} ({techos.NOMBRES[nivel]}), tope de politica "
              f"{techos.TECHO_MAXIMO_POLITICA}")

    try:
        historial = interruptor.historial(tenant, limite=20)
    except Exception as e:                                       # noqa: BLE001
        print(f"\n  (no se pudo leer el historial: {type(e).__name__}: {e})")
        return 0 if veredicto.permitido else 3

    if historial:
        print("\n  historial (lo mas reciente primero):")
        for h in historial:
            cuando = h["creado_en"].isoformat(timespec="seconds") if h["creado_en"] else "?"
            desde = h["estado_anterior"] or "-"
            print(f"    {cuando}  {desde} -> {h['estado']}  por {h['actor']}")
            if h["motivo"]:
                print(f"        {h['motivo']}")
    print()
    return 0 if veredicto.permitido else 3


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Consulta o mueve el interruptor de autonomia de una empresa.")
    p.add_argument("tenant", help="slug del tenant, ej. 'rapilink'")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--detener", action="store_true",
                       help="la empresa deja de ejecutar acciones autonomas")
    grupo.add_argument("--reactivar", action="store_true",
                       help="vuelve a permitirlas")
    grupo.add_argument("--techo", type=int, default=None,
                       help="fija el techo de autonomia (0..3). Exige --desde")
    p.add_argument("--desde", default=None,
                   help="el techo que viste antes de cambiarlo, o 'ninguno'")
    p.add_argument("--actor", default="",
                   help="quien toma la decision (obligatorio para mover)")
    p.add_argument("--motivo", default="",
                   help="por que (obligatorio para mover)")
    args = p.parse_args(argv)

    if args.techo is not None:
        return _mover_techo(args)

    if not (args.detener or args.reactivar):
        try:
            return _mostrar(args.tenant)
        except Exception as e:                                   # noqa: BLE001
            print(f"[autonomia] no se pudo leer el interruptor: "
                  f"{type(e).__name__}: {e}")
            return 1

    if not args.actor.strip() or not args.motivo.strip():
        print("[autonomia] para mover el interruptor hacen falta --actor y "
              "--motivo. Quien lo encuentre detenido tiene que poder saber "
              "quien lo paro y por que.")
        return 2

    accion = interruptor.detener if args.detener else interruptor.reactivar
    try:
        fila = accion(args.tenant, args.actor, args.motivo)
    except ValueError as e:
        print(f"[autonomia] {e}")
        return 2
    except Exception as e:                                       # noqa: BLE001
        print(f"[autonomia] no se pudo mover el interruptor: "
              f"{type(e).__name__}: {e}")
        return 1

    anterior = fila["estado_anterior"] or "(sin estado previo)"
    print(f"\n  {args.tenant}: {anterior} -> {fila['estado']}")
    print(f"  por {fila['actor']}: {fila['motivo']}\n")
    if fila["estado"] == interruptor.DETENIDO:
        print("  Las conversaciones siguen atendiendose y las consultas de")
        print("  lectura tambien. Lo que se detuvo son las acciones y los")
        print("  trabajos automaticos.\n")
    return 0


def _mover_techo(args) -> int:
    if args.desde is None:
        print("[autonomia] --techo exige --desde: el techo que viste antes de "
              "cambiarlo ('ninguno' si no habia). Asi un cambio simultaneo de "
              "otro operador no se pisa.")
        return 2
    if args.desde.strip().lower() == "ninguno":
        desde = None
    else:
        try:
            desde = int(args.desde)
        except ValueError:
            print(f"[autonomia] --desde tiene que ser un nivel o 'ninguno', no "
                  f"{args.desde!r}")
            return 2
    try:
        fila = techos.cambiar(args.tenant, args.techo, actor=args.actor,
                              motivo=args.motivo,
                              origen=f"cli:{uuid.uuid4()}",
                              anterior_esperado=desde)
    except techos.CambioRechazado as e:
        print(f"[autonomia] el techo NO se movio ({e.codigo}): {e.motivo}")
        return 2
    except Exception as e:                                       # noqa: BLE001
        print(f"[autonomia] no se pudo mover el techo: {type(e).__name__}: {e}")
        return 1
    anterior = "ninguno" if fila["nivel_anterior"] is None else fila["nivel_anterior"]
    print(f"\n  {args.tenant}: techo {anterior} -> {fila['nivel_solicitado']} "
          f"({fila['resultado']})")
    print(f"  por {fila['actor']}: {fila['motivo']}\n")
    print("  El techo acota, no autoriza: ninguna accion sale por esto solo.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
