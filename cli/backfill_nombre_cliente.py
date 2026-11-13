# -*- coding: utf-8 -*-
"""
================================================================================
 BACKFILL DEL NOMBRE DEL CLIENTE  --  el motor resuelve, el CRM escribe
================================================================================

QUE HACE
--------
Rellena 'cases.external_client_name' en los casos que ya estaban importados
cuando ese campo no existia. De aqui en adelante lo pone el importador solo
(nucleo/seguimiento/importacion_io.py); esto es para los de antes.

EL CAMINO, Y POR QUE ESTE
-------------------------
    WispHub  ->  motor  ->  POST /api/importacion/casos/nombre-cliente/  ->  CRM

La primera version de este comando hacia el UPDATE directo sobre
public."case", y no funciona. Medido contra produccion el 25/09/2026:

  - 'app_backend' -- el rol al que baja nucleo/persistencia/db.py::sesion --
    no tiene NINGUN privilegio sobre esa tabla: solo crm_owner, crm_user y
    service_role;
  - la RLS de public."case" esta activa Y FORZADA, y su politica compara
    org_id contra 'app.current_org', mientras que el motor fija
    'app.current_tenant'. Con permisos y sin esa variable habria visto cero
    filas y habria informado "0 actualizados" SIN UN ERROR.

Y el fondo del asunto: el motor no lee ni escribe ninguna tabla public.* del
CRM: cero ocurrencias en todo nucleo/. Esa frontera viene del incidente del
18/08/2026 que separo los usuarios de base, y se cruza por HTTP con el token
del importador -- como ya lo hacen la importacion y la reconciliacion.

Este comando, entonces, no escribe nada. Lee por la API, pregunta al proveedor,
y le pide al CRM que escriba.

POR QUE NO ES UNA MIGRACION DE DATOS
------------------------------------
Porque hay que preguntarle al proveedor, y 'migrate' corre SOLO en cada
despliegue. Una migracion que llama a WispHub convertiria cada deploy en
cientos de llamadas a un tercero, y un deploy que falla porque el proveedor no
contesta es un deploy roto por un dato de pantalla.

POR QUE NO ESCRIBE SALVO QUE SE LO PIDAN
----------------------------------------
Sin '--aplicar' solo mira y cuenta: no llama a la ruta de escritura ni una vez.
Con '--aplicar', la idempotencia la pone el CRM y no este bucle: su UPDATE
filtra por external_client_name="" y devuelve cuantos actualizo y cuantos ya
tenian. Un servicio sin nombre en el proveedor no se manda.

Uso:
    py -3.13 cli/backfill_nombre_cliente.py rapilink --tope 20 --dry-run
    py -3.13 cli/backfill_nombre_cliente.py rapilink --tope 20 --aplicar
    py -3.13 cli/backfill_nombre_cliente.py rapilink --aplicar
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv                          # noqa: E402

# override=False por el mismo motivo que en cli/diferencias_config.py: un .env
# viejo horneado en una imagen no puede mandar mas que el entorno del
# despliegue.
load_dotenv(RAIZ / ".env", override=False)

from nucleo.config import fuente                        # noqa: E402
from nucleo.seguimiento import importacion_io           # noqa: E402


def planificar(config, tenant: str, tope: int):
    """
    Que servicios hay que resolver y cuantos casos dependen de cada uno.

    Devuelve (pendientes, sin_servicio). 'pendientes' es {servicio: [tickets]}
    ya recortado a 'tope' SERVICIOS -- no a tope casos: la unidad de trabajo es
    la llamada al proveedor, que es una por servicio, y cortar por casos
    dejaria un servicio a medio resolver.
    """
    todos = importacion_io.casos_sin_nombre_de_cliente(config, tenant)
    sin_servicio = todos.pop("", [])
    if tope:
        pendientes = {s: todos[s] for s in sorted(todos)[:tope]}
    else:
        pendientes = todos
    return pendientes, sin_servicio


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tenant")
    p.add_argument("--aplicar", action="store_true",
                   help="escribe de verdad, por la ruta del CRM")
    p.add_argument("--dry-run", action="store_true",
                   help="explicito: consulta y cuenta, sin escribir. Es lo "
                        "que pasa por defecto; el flag existe para poder "
                        "decirlo en el comando.")
    p.add_argument("--tope", type=int, default=0,
                   help="cuantos SERVICIOS procesar como maximo (0 = todos)")
    p.add_argument("--actor", default="backfill-nombre-cliente",
                   help="quien queda registrado como origen de la operacion")
    args = p.parse_args()

    if args.aplicar and args.dry_run:
        print("--aplicar y --dry-run a la vez no se puede: elegi uno.")
        return 2

    cargada = fuente.cargar(args.tenant)
    config = cargada[0] if isinstance(cargada, tuple) else cargada
    if config is None:
        print(f"No se pudo cargar la config de '{args.tenant}'.")
        return 1

    pendientes, sin_servicio = planificar(config, args.tenant, args.tope)

    casos_alcanzables = sum(len(v) for v in pendientes.values())
    print(f"servicios a resolver      {len(pendientes)}")
    print(f"casos que dependen        {casos_alcanzables}")
    if sin_servicio:
        print(f"casos SIN servicio        {len(sin_servicio)}  "
              f"(no hay con que preguntarle al proveedor: se quedan sin nombre)")

    if not pendientes:
        print("\nNada que resolver.")
        return 0

    # La MISMA resolucion que usa el importador. No se duplica la eleccion de
    # herramienta ni el recorte de campos: si el catalogo cambia, los dos
    # caminos cambian juntos.
    resolver = importacion_io.resolver_servicios(config, args.tenant)
    fichas = resolver(sorted(pendientes))

    con_nombre = {s: str((fichas.get(s) or {}).get("nombre") or "").strip()
                  for s in pendientes}
    resolubles = {s: n for s, n in con_nombre.items() if n}
    print(f"el proveedor dio nombre   {len(resolubles)} de {len(pendientes)}")

    if not args.aplicar:
        casos_listos = sum(len(pendientes[s]) for s in resolubles)
        print()
        print(f"se escribirian            {casos_listos} casos")
        print(f"quedarian sin nombre      "
              f"{casos_alcanzables - casos_listos + len(sin_servicio)}")
        print()
        print("DRY-RUN: no se llamo a la ruta de escritura del CRM ni una vez.")
        print("Para escribir: --aplicar")
        return 0

    actualizados = ya_tenian = fallidos = 0
    for servicio, nombre in resolubles.items():
        try:
            r = importacion_io.fijar_nombre_cliente(
                config, args.tenant, servicio, nombre, actor=args.actor)
            actualizados += int(r.get("actualizados") or 0)
            ya_tenian += int(r.get("ya_tenian") or 0)
        except Exception as e:                              # noqa: BLE001
            # Un servicio que falla no corta el lote: el resto se puede
            # escribir, y volver a correr el comando reintenta solo los que
            # siguen vacios.
            fallidos += 1
            print(f"  [fallo] servicio {servicio}: {type(e).__name__}: {e}")

    sin_nombre = len(pendientes) - len(resolubles)
    print()
    print(f"ACTUALIZADOS              {actualizados} casos")
    print(f"ya tenian nombre          {ya_tenian}")
    print(f"servicios sin nombre      {sin_nombre}  (el proveedor no lo dio)")
    if fallidos:
        print(f"servicios que fallaron    {fallidos}  (se pueden reintentar: "
              f"volver a correr no sobrescribe nada)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
