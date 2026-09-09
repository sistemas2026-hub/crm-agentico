# -*- coding: utf-8 -*-
"""
================================================================================
 IMPORTAR TICKETS DEL SISTEMA DEL ISP  --  hoy, solo en seco
================================================================================

    py -3.13 cli/importar_tickets.py rapilink --dry-run
    py -3.13 cli/importar_tickets.py rapilink --dry-run --piloto A
    py -3.13 cli/importar_tickets.py rapilink --dry-run --piloto A --detalle
    py -3.13 cli/importar_tickets.py rapilink --dry-run --reconciliar

QUE HACE
--------
Recorre el descubrimiento completo -- listar en WispHub, filtrar, resolver la
identidad del cliente, elegir el area y su responsable, mirar si el caso ya
existe-- y IMPRIME lo que haria. No crea ni actualiza ningun caso, y contra
WispHub solo hace GET.

POR QUE EL DRY-RUN NO ES UNA SIMULACION
---------------------------------------
Llama exactamente a las mismas funciones que va a llamar la corrida real
(nucleo/seguimiento/importacion.py). Lo unico que no hace es aplicar el
resultado. Un dry-run escrito aparte se parece al real el primer dia y miente
el segundo, que es cuando se lo necesita.

LOS PILOTOS
-----------
'--piloto A|B|C' arma una whitelist EN MEMORIA, sin tocar la config del
tenant. Sirve para medir tres alcances contra los datos reales antes de
habilitar ninguno. La config guardada sigue vacia y el barrido sigue en 0.

Sin '--piloto' usa la configuracion real del tenant, que por defecto no
importa nada -- y eso es lo correcto: la salida vacia es la prueba de que un
despliegue sin configurar no hace nada.
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

from nucleo.config import fuente  # noqa: E402
from nucleo.config.schema import (DestinoTicket, ImportacionTickets,  # noqa: E402
                                  cargar_config)
from nucleo.persistencia import db as persistencia  # noqa: E402
from nucleo.seguimiento import importacion as imp  # noqa: E402
from nucleo.seguimiento import importacion_io as io  # noqa: E402
from nucleo.seguimiento.importacion_io import (  # noqa: E402
    aplicar, aplicar_reconciliacion, casos_externos,
    leer_ticket, listar_tickets, registrados_por_dexter, resolver_servicios)

# La cuenta con la que firma la API key de WispHub. Todo lo que entra por API
# sale con este nombre, asi que NO identifica a Dexter: identifica "por API".
# Ver clasificar_creador. Se declara aca y no en el nucleo porque es un dato de
# empresa; el dia que haya un segundo ISP sale a variables_tenant.
CUENTA_API_POR_DEFECTO = "Rapilink SAS - admin@rapilink-sas"

HERRAMIENTA_LISTADO = "listar_tickets_recientes"


# =============================================================================
#  PILOTOS  --  whitelists en memoria, para medir antes de habilitar
# =============================================================================

ASUNTOS_A = [
    "No Tiene Internet",
    "Problemas De Tv",
    "Internet Intermitente/Niveles Altos",
    "Vista Reiterativa Post Soporte",
    "Internet Intermitente",
    "CONFIGURACION DNS",
]


def _pilotos(area: str) -> dict[str, ImportacionTickets]:
    """Las tres opciones medidas en la Fase 0, listas para comparar."""
    soporte = "Soporte Técnico"
    dest = DestinoTicket(area=area)

    a_claves = [imp.clave(soporte, x) for x in ASUNTOS_A]
    admin_claves = [imp.clave("Administrativo", x)
                    for x in ("Cambio De Contraseña En Router Wifi", "Internet Lento")]

    # Los tres pilotos comparten los estados operativos: el 84,9 % de lo que
    # la whitelist acepta ya esta cerrado, y esos no se importan.
    op = ["Nuevo", "En Progreso"]
    # El proveedor y su cuenta de API son datos de empresa: viajan en la
    # config, no en el nucleo. Aca se los pasa el piloto porque es una
    # whitelist en memoria que no toca la config guardada.
    ident = {"proveedor": "wisphub",
             "cuenta_api": "Rapilink SAS - admin@rapilink-sas"}

    return {
        # Lo que un tecnico realmente trabaja. ~10/dia.
        "A": ImportacionTickets(**ident, 
            departamentos=[soporte], asuntos=a_claves, estados_descubrimiento=op,
            destinos={k: dest for k in a_claves}),
        # Toda la cola de Soporte, sin listar 41 asuntos. ~19/dia.
        "B": ImportacionTickets(**ident, 
            departamentos=[soporte], asuntos=[imp.clave(soporte, "*")],
            estados_descubrimiento=op,
            destinos={imp.clave(soporte, "*"): dest}),
        # B mas lo que Dexter ya atiende hoy por chat. ~26/dia.
        "C": ImportacionTickets(**ident, 
            departamentos=[soporte, "Administrativo"],
            asuntos=[imp.clave(soporte, "*")] + admin_claves,
            estados_descubrimiento=op,
            destinos={imp.clave(soporte, "*"): dest,
                      **{k: dest for k in admin_claves}}),
    }


# =============================================================================
#  PUERTAS AL MUNDO  --  lo unico que sale de este proceso
# =============================================================================

# =============================================================================
#  INFORME
# =============================================================================

def imprimir(titulo, resumen, veredictos, detalle=False):
    print(f"\n{'=' * 74}\n  {titulo}\n{'=' * 74}")
    print(f"  tickets inspeccionados ................. {resumen['inspeccionados']}")
    print(f"  candidatos nuevos ...................... {resumen['candidatos']}")
    print("\n  por resultado:")
    for k, n in resumen["por_resultado"].items():
        print(f"      {n:>5}  {k}")
    print("\n  autoria de TODO lo inspeccionado:")
    for k, n in resumen["por_tipo_de_creador"].items():
        print(f"      {n:>5}  {k}")
    print("\n  autoria de los CANDIDATOS:")
    for k, n in (resumen["candidatos_por_tipo"] or {"(ninguno)": 0}).items():
        print(f"      {n:>5}  {k}")
    print("\n  identidad de los candidatos:")
    print(f"      {resumen['con_cliente_real']:>5}  con cliente real")
    print(f"      {resumen['placeholder_instalaciones']:>5}  placeholder de instalaciones")
    print(f"      {resumen['con_onu']:>5}  con ONU (llegan a SmartOLT)")
    print(f"      {resumen['sin_onu']:>5}  sin ONU")
    print("\n  reparto propuesto:")
    for k, n in (resumen["candidatos_por_responsable"] or {"(ninguno)": 0}).items():
        print(f"      {n:>5}  {k}")

    if detalle:
        print(f"\n  {'ticket':<8} {'servicio':<9} {'estado':<12} {'tipo':<20} "
              f"{'ONU':<4} {'area':<10} {'responsable':<14} resultado")
        for v in veredictos:
            if v.resultado in (imp.DESCARTADO_POR_DEPARTAMENTO,
                               imp.DESCARTADO_POR_ASUNTO):
                continue
            print(f"  {v.external_ticket_id:<8} {v.external_service_id:<9} "
                  f"{v.external_status:<12} {v.external_created_by_type:<20} "
                  f"{'si' if v.tiene_onu else 'no':<4} {v.area:<10} "
                  f"{str(v.responsable)[:12]:<14} {v.resultado}"
                  + (f"  ({v.detalle})" if v.detalle else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tenant")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="unico modo disponible hoy: no escribe nada")
    p.add_argument("--piloto", choices=["A", "B", "C"],
                   help="whitelist en memoria, sin tocar la config del tenant")
    # Tiene que ser un 'AreaDeTrabajo.nombre' declarado en la config, no la
    # etiqueta que se ve en pantalla: si no coincide, el veredicto es
    # AREA_DESTINO_INVALIDA y no se importa nada -- que es lo correcto, pero
    # conviene no descubrirlo con una corrida entera de por medio.
    p.add_argument("--area", default="soporte_tecnico",
                   help="area destino de la whitelist piloto")
    p.add_argument("--dias", type=int, help="ancho de la ventana, en dias")
    p.add_argument("--detalle", action="store_true", help="una linea por ticket")
    p.add_argument("--reconciliar", action="store_true",
                   help="ademas, que cambiaria de los casos ya conocidos")
    p.add_argument("--aplicar", action="store_true",
                   help="ESCRIBE: crea los casos de los candidatos. Sin esto, "
                        "el comando es de solo lectura.")
    p.add_argument("--config-yaml", action="store_true",
                   help="usar tenants/<slug>.config.yaml en vez de la base")
    args = p.parse_args()

    if args.config_yaml:
        config = cargar_config(RAIZ / "tenants" / f"{args.tenant}.config.yaml")
    else:
        config = fuente.cargar(args.tenant, RAIZ)

    if args.piloto:
        config.importacion_tickets = _pilotos(args.area)[args.piloto]
        print(f"[piloto {args.piloto}] whitelist EN MEMORIA -- la config "
              f"guardada del tenant no se toca")
    if args.dias:
        config.importacion_tickets.ventana_dias = args.dias

    conf = config.importacion_tickets
    desde, hasta = imp.ventana(conf)
    print(f"[ventana] {desde} -> {hasta}  "
          f"(cada_horas={conf.cada_horas}, departamentos={len(conf.departamentos)}, "
          f"asuntos={len(conf.asuntos)}, estados={conf.estados_descubrimiento or 'ninguno'})")

    registro = registrados_por_dexter(args.tenant)
    conocidos, casos = casos_externos(conf.proveedor)
    print(f"[casos] con referencia externa: {len(conocidos)}")

    areas_por_persona = persistencia.areas_de_colaboradores(args.tenant)
    print(f"[areas] colaboradores con area: {len(areas_por_persona)} "
          f"-- {sorted(set(areas_por_persona.values()))}")

    tickets = listar_tickets(config, args.tenant, desde, hasta)
    print(f"[wisphub] tickets en la ventana: {len(tickets)}")

    placeholder = (config.variables_tenant or {}).get(
        "WISPHUB_ID_SERVICIO_INSTALACIONES", "")

    veredictos = imp.descubrir(
        config, tickets,
        conocidos=conocidos,
        registrados_por_dexter=registro,
        areas_por_persona=areas_por_persona,
        cuenta_api=conf.cuenta_api,
        servicio_placeholder=placeholder,
        resolver_servicio=resolver_servicios(config, args.tenant))

    titulo = f"DRY RUN{' -- PILOTO ' + args.piloto if args.piloto else ''}"
    imprimir(titulo, imp.resumen(veredictos), veredictos, args.detalle)

    if args.aplicar:
        print(f"\n{'=' * 74}\n  APLICANDO  --  esto ESCRIBE casos\n{'=' * 74}")
        r = aplicar(config, args.tenant, veredictos)
        print(f"  creados ......... {r['creados']}")
        print(f"  ya estaban ...... {r['ya_estaban']}")
        print(f"  fallidos ........ {r['fallidos']}")

    if args.reconciliar:
        cambios = imp.reconciliar(
            config, casos,
            leer_ticket=lambda t: leer_ticket(config, args.tenant, t),
            cuenta_api=conf.cuenta_api, registrados_por_dexter=registro)
        print(f"\n{'=' * 74}\n  RECONCILIACION  (que cambiaria, sin escribir)\n{'=' * 74}")
        print(f"  casos con referencia externa .......... {len(casos)}")
        print(f"  alcanzados por la politica ............ {len(cambios)}")
        print(f"  con alguna diferencia ................. "
              f"{sum(1 for c in cambios if c.hay_diferencia)}")
        print(f"  con error de lectura .................. "
              f"{sum(1 for c in cambios if c.error)}")
        if args.aplicar:
            r = aplicar_reconciliacion(config, args.tenant, cambios)
            print(f"  actualizados .......................... {r['actualizados']}")
            print(f"  sin cambios ........................... {r['sin_cambios']}")
            print(f"  fallidos .............................. {r['fallidos']}")
        for c in cambios:
            if not c.hay_diferencia:
                continue
            dif = {k: (c.antes.get(k), v) for k, v in c.despues.items()
                   if c.antes.get(k) != v and k != "external_fetched_at"}
            print(f"    ticket {c.external_ticket_id}: {dif}")

    print(f"\n{'=' * 74}")
    print("  No se creo ni actualizo ningun caso. Contra WispHub, solo GET.")
    print(f"{'=' * 74}")


if __name__ == "__main__":
    main()
