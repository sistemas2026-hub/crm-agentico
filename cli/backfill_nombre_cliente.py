# -*- coding: utf-8 -*-
"""
================================================================================
 BACKFILL DEL NOMBRE DEL CLIENTE  --  para los casos que se importaron sin el
================================================================================

QUE HACE
--------
Rellena 'cases.external_client_name' en los casos que ya estaban importados
cuando ese campo no existia. De aqui en adelante lo pone el importador solo
(nucleo/seguimiento/importacion_io.py); esto es para los de antes, una vez.

POR QUE NO ES UNA MIGRACION DE DATOS
------------------------------------
Porque hay que preguntarle al proveedor, y 'migrate' corre SOLO en cada
despliegue (ver el entrypoint del backend). Una migracion que llama a WispHub
convertiria cada deploy en cientos de llamadas a un tercero, y un deploy que
falla porque el proveedor no contesta es un deploy roto por un dato de
pantalla. Asi que es un comando: se corre cuando alguien decide correrlo.

POR QUE NO ESCRIBE SALVO QUE SE LO PIDAN
----------------------------------------
Sin '--aplicar' solo mira y cuenta. Con '--aplicar' escribe, y aun asi:

  - el UPDATE lleva "and coalesce(external_client_name,'') = ''" SIEMPRE, asi
    que no puede pisar un nombre que ya estuviera puesto -- ni el de una
    corrida anterior ni uno cargado a mano;
  - no borra: un servicio para el que el proveedor no da nombre se cuenta y se
    deja como estaba;
  - va acotado a la organizacion del tenant, igual que todo lo demas.

Uso:
    py -3.13 cli/backfill_nombre_cliente.py rapilink              # solo mira
    py -3.13 cli/backfill_nombre_cliente.py rapilink --aplicar    # escribe
    py -3.13 cli/backfill_nombre_cliente.py rapilink --tope 20    # de a poco
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
from nucleo.persistencia import db                      # noqa: E402
from nucleo.seguimiento import importacion_io           # noqa: E402


def _columna_existe(cur) -> bool:
    """
    Si la migracion ya llego a esta base.

    Sin esto, correr el comando antes del despliegue da un
    'UndefinedColumn: external_client_name' crudo de Postgres, que manda a
    buscar un error de codigo donde lo que falta es un deploy.
    """
    cur.execute("""select 1 from information_schema.columns
                    where table_schema = 'public' and table_name = 'case'
                      and column_name = 'external_client_name'""")
    return cur.fetchone() is not None


def _casos_sin_nombre(cur, org_id, tope: int | None):
    """
    Los casos importados a los que les falta el nombre.

    Se piden el id y el servicio, nada mas: el nombre que falta viene del
    proveedor y ningun otro campo del caso hace falta para ponerlo.
    """
    sql = """select id, external_service_id
             from public."case"
             where org_id = %s
               and coalesce(external_service_id, '') <> ''
               and coalesce(external_client_name, '') = ''
             order by created_at"""
    if tope:
        sql += "\n             limit %s"
        cur.execute(sql, (org_id, tope))
    else:
        cur.execute(sql, (org_id,))
    return cur.fetchall()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tenant")
    p.add_argument("--aplicar", action="store_true",
                   help="escribe de verdad. Sin esto solo cuenta.")
    p.add_argument("--tope", type=int, default=0,
                   help="cuantos casos mirar como maximo (0 = todos)")
    args = p.parse_args()

    cargada = fuente.cargar(args.tenant)
    config = cargada[0] if isinstance(cargada, tuple) else cargada
    if config is None:
        print(f"No se pudo cargar la config de '{args.tenant}'.")
        return 1

    with db.sesion(args.tenant) as (cur, org_id):
        if not _columna_existe(cur):
            print("La columna 'case.external_client_name' no existe en esta "
                  "base todavia: la migracion 0032 no esta aplicada.")
            print("Este comando se corre DESPUES del despliegue, no antes.")
            return 1
        filas = _casos_sin_nombre(cur, org_id, args.tope or None)

    if not filas:
        print("No hay casos con servicio externo y sin nombre. Nada que hacer.")
        return 0

    servicios = sorted({str(f["external_service_id"]) for f in filas})
    print(f"casos sin nombre        {len(filas)}")
    print(f"servicios a consultar   {len(servicios)}")

    if not args.aplicar:
        print()
        print("Solo se miro. Para escribir: --aplicar")
        return 0

    # La MISMA resolucion que usa el importador. No se duplica la eleccion de
    # herramienta ni el recorte de campos: si un dia el catalogo cambia, los
    # dos caminos cambian juntos.
    resolver = importacion_io.resolver_servicios(config, args.tenant)
    fichas = resolver(servicios)

    nombres = {sid: str((f or {}).get("nombre") or "").strip()
               for sid, f in fichas.items()}
    con_nombre = {s: n for s, n in nombres.items() if n}
    print(f"el proveedor dio nombre {len(con_nombre)} de {len(servicios)} servicios")

    actualizados = 0
    with db.sesion(args.tenant) as (cur, org_id):
        for fila in filas:
            nombre = con_nombre.get(str(fila["external_service_id"]))
            if not nombre:
                continue
            # La condicion del vacio va en el UPDATE y no en un 'if' de Python:
            # entre la lectura de arriba y esta escritura pudo correr una
            # importacion. Que lo decida la base, no una copia en memoria.
            cur.execute(
                """update public."case"
                      set external_client_name = %s, updated_at = now()
                    where id = %s and org_id = %s
                      and coalesce(external_client_name, '') = ''""",
                (nombre[:255], fila["id"], org_id))
            actualizados += cur.rowcount

    sin_nombre = len(filas) - actualizados
    print()
    print(f"ACTUALIZADOS            {actualizados}")
    print(f"siguen sin nombre       {sin_nombre}")
    if sin_nombre:
        print("  (el proveedor no dio nombre para su servicio, o ya lo tenian "
              "puesto cuando se fue a escribir)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
