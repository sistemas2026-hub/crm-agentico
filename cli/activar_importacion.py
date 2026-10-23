# -*- coding: utf-8 -*-
"""
================================================================================
 ACTIVAR LA IMPORTACION DE TICKETS  --  actualizacion SELECTIVA de la config
================================================================================

    py -3.13 cli/activar_importacion.py rapilink            # muestra el cambio
    py -3.13 cli/activar_importacion.py rapilink --aplicar   # lo guarda

QUE HACE Y QUE NO
-----------------
Agrega a la config del tenant SOLO lo que la importacion necesita: las
herramientas que todavia no esten, y la seccion 'importacion_tickets'. Todo lo
demas queda como esta.

POR QUE NO SE CARGA EL YAML ENTERO
----------------------------------
Medido con 'cli/diferencias_config.py' el 09/09/2026: entre el archivo y la
base habia 232 diferencias en la direccion "solo la base lo tiene", y no son
deriva -- son el funcionamiento normal. La base tiene las localidades
sincronizadas desde el sistema del ISP, la parrilla de canales, roles editados
desde la interfaz, y 'llm.razonamiento: disabled', que es una medicion en curso.
Cargar el archivo completo habria reactivado el razonamiento y borrado lo
demas.

Por eso esto va por 'editor._editar', que es el mismo camino que usan las
pantallas: lee la version vigente, aplica la mutacion, valida, sube
'config_version' y deja copia en 'tenant_config_historial'. Un UPDATE del JSONB
se saltearia las tres cosas.

LLEGA APAGADO
-------------
'cada_horas' queda en 0. Esto agrega la CAPACIDAD de importar, no la
importacion. Encenderla es una segunda edicion, deliberada y aparte.
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

from nucleo.config import editor, fuente  # noqa: E402
from nucleo.config.schema import cargar_config  # noqa: E402

# Las que la importacion necesita en el catalogo. Se copian TAL CUAL del YAML
# --que es donde estan escritas, revisadas y commiteadas-- en vez de repetirlas
# aca: dos definiciones de la misma herramienta terminan diciendo cosas
# distintas.
HERRAMIENTAS = [
    "listar_tickets_recientes",
    "consultar_ticket_por_id",
    "consultar_tickets_conocidos",
    "consultar_casos_externos",
    "importar_caso_externo",
    "reconciliar_caso_externo",
]

# El piloto A, aprobado con los numeros de la Fase 0 delante: 84,9 % de lo que
# la lista blanca acepta ya esta cerrado, asi que solo entran los estados
# operativos.
ASUNTOS_A = [
    "No Tiene Internet",
    "Problemas De Tv",
    "Internet Intermitente/Niveles Altos",
    "Vista Reiterativa Post Soporte",
    "Internet Intermitente",
    "CONFIGURACION DNS",
]
DEPARTAMENTO = "Soporte Técnico"
AREA_DESTINO = "soporte_tecnico"


def _clave(dep: str, asunto: str) -> str:
    from nucleo.seguimiento import importacion as imp

    return imp.clave(dep, asunto)


def _importacion_tickets() -> dict:
    claves = [_clave(DEPARTAMENTO, a) for a in ASUNTOS_A]
    return {
        # APAGADO. Esto agrega la capacidad, no la importacion.
        "cada_horas": 0,
        "proveedor": "wisphub",
        "cuenta_api": "Rapilink SAS - admin@rapilink-sas",
        "departamentos": [DEPARTAMENTO],
        "asuntos": claves,
        "estados_descubrimiento": ["Nuevo", "En Progreso"],
        "destinos": {k: {"area": AREA_DESTINO, "prioridad": "Normal"} for k in claves},
        "ventana_dias": 30,
        "solapamiento_horas": 6,
        "reconciliar_estados": ["New", "Assigned", "Pending"],
        "gracia_cierre_dias": 7,
        "tipos_de_creador": [],
    }


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    tenant = args[0]
    aplicar = "--aplicar" in args

    del_yaml = cargar_config(RAIZ / "tenants" / f"{tenant}.config.yaml")
    por_nombre = {h.nombre: h for h in del_yaml.herramientas}
    faltan_en_yaml = [n for n in HERRAMIENTAS if n not in por_nombre]
    if faltan_en_yaml:
        raise SystemExit(f"El YAML no declara {faltan_en_yaml}. Nada que copiar.")

    viva = fuente.cargar(tenant, RAIZ)
    ya_estan = {h.nombre for h in viva.herramientas}
    a_agregar = [n for n in HERRAMIENTAS if n not in ya_estan]

    print("=" * 74)
    print(f"  ACTUALIZACION SELECTIVA  --  {'APLICANDO' if aplicar else 'SIMULACION'}")
    print("=" * 74)
    print(f"  herramientas en la base ahora ....... {len(viva.herramientas)}")
    print(f"  se agregarian ....................... {len(a_agregar)}")
    for n in a_agregar:
        h = por_nombre[n]
        print(f"      + {n:<30} {h.metodo or 'GET':<6} auth_ref={h.auth_ref}")
    if ya_estan & set(HERRAMIENTAS):
        print(f"  ya estaban (no se tocan) ............ "
              f"{sorted(ya_estan & set(HERRAMIENTAS))}")

    nueva = _importacion_tickets()
    actual = viva.importacion_tickets.model_dump(mode="json")
    print(f"\n  importacion_tickets:")
    for k, v in nueva.items():
        antes = actual.get(k)
        marca = "  (sin cambio)" if antes == v else ""
        corto = v if not isinstance(v, (list, dict)) else f"{len(v)} entrada(s)"
        print(f"      {k:<24} {corto}{marca}")
    print(f"\n  cada_horas queda en {nueva['cada_horas']}: agrega la capacidad, "
          f"no la importacion.")

    if not aplicar:
        print("\n  Nada se guardo. Con --aplicar se escribe.")
        return

    definiciones = [por_nombre[n].model_dump(mode="json", exclude_none=True)
                    for n in a_agregar]

    def mutar(doc: dict) -> None:
        # Solo se AGREGA. Ninguna herramienta existente se toca, y ninguna
        # otra seccion de la config se lee siquiera.
        doc.setdefault("herramientas", []).extend(definiciones)
        doc["importacion_tickets"] = nueva

    config = editor._editar(tenant, mutar)
    print(f"\n  Guardado. Herramientas ahora: {len(config.herramientas)}")
    print(f"  importacion_tickets.cada_horas = "
          f"{config.importacion_tickets.cada_horas}")


if __name__ == "__main__":
    main()
