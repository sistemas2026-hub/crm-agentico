# -*- coding: utf-8 -*-
"""
================================================================================
 PONER 'diagnosticar_servicio' EN LA CONFIG DE UN TENANT  --  quirurgico
================================================================================

QUE HACE, Y QUE NO
------------------
Agrega UNA herramienta y SUS DOS autorizaciones de rol. Nada mas. No carga el
YAML entero, no toca ninguna otra herramienta, no reescribe ningun agente.

POR QUE NO SE USA 'cargar_config.py'
------------------------------------
Porque cargar el archivo completo pisa lo que la base tenga y el archivo no
traiga -- tipicamente un agente creado desde la interfaz. La regla del proyecto
es que LA BASE MANDA y el YAML es semilla: para un cambio de dos cosas, el
camino es el editor quirurgico, que lee lo vigente, muta lo justo, valida el
resultado entero y guarda, todo en la misma transaccion con la fila bloqueada.

DOS MODOS, Y EL PRIMERO NO ESCRIBE
----------------------------------
    py -3.13 cli/aplicar_diagnostico_servicio.py rapilink --ver
        Dice que hay hoy en la base y que cambiaria. NO escribe.

    py -3.13 cli/aplicar_diagnostico_servicio.py rapilink --aplicar
        Lo aplica.

ES IDEMPOTENTE: si ya esta, no hace nada y lo dice. Correrlo dos veces es
seguro.

ANTES DE APLICAR, MIRAR LA DIFERENCIA EN LOS DOS SENTIDOS
---------------------------------------------------------
    py -3.13 cli/diferencias_config.py rapilink

"Solo la base lo tiene" es NORMAL -- es la fuente de verdad. "El repo lo declara
y la base no" es la que rompe. Si aparece algo inesperado, no seguir: hay algo
en produccion que el archivo no sabe.

DESPUES DE APLICAR
------------------
    py -3.13 cli/diferencias_config.py rapilink
    py -3.13 cli/evaluar.py rapilink --humo --base

El '--base' no es opcional: sin el, el corredor lee el YAML, que es justo el
lado donde el dato si estaba.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv          # noqa: E402
# override=False: el entorno explicito gana, el archivo solo rellena. Mismo
# criterio que el resto de cli/. Sin esto el script no encuentra la base y
# fallaria con un error que no dice que falto la credencial.
load_dotenv(override=False)

#  Lo que se agrega. Es el MISMO contenido que la semilla declara: si los dos
#  divergen, el que manda es este archivo, porque es el que se aplica.
HERRAMIENTA = {
    "nombre": "diagnosticar_servicio",
    "tipo": "interno",
    "diagnostica_servicio": True,
    "resolver_equipo_con": "consultar_cliente",
    "descripcion": (
        "El estado optico del equipo de UN SERVICIO, pedido por su id. Devuelve "
        "si el equipo esta en linea o caido, su senal de bajada en dBm, y --si "
        "esta caido-- POR QUE se cayo, que es lo que de verdad cambia la "
        "decision: 'sin_energia' significa que el equipo aviso que se quedo sin "
        "luz justo antes de apagarse (la casa del cliente: un corte, o lo "
        "desenchufaron; no es una falla de la red). 'fibra' significa que perdio "
        "la senal optica: un corte o una falla en la NAP, y eso es NUESTRO -- el "
        "cliente va a volver a llamar. Son cosas opuestas y no se pueden tratar "
        "igual. Si devuelve 'equipo_registrado: false', ese servicio no tiene "
        "equipo cargado en el proveedor y NO se puede afirmar nada sobre el; eso "
        "no es lo mismo que 'esta sano'. 'estado: desconocido' siempre trae su "
        "'motivo' y tampoco se lee como sano."),
    "solo_lectura": True,
    "roles_permitidos": ["supervisor_noc", "soporte"],
    #  El MISMO que usan las otras de SmartOLT. Se equivoco una vez con
    #  'SMARTOLT_BASE_URL', que no existe, y la herramienta quedo escrita
    #  en la base sin poder resolver su URL.
    "base_url_ref": "SMARTOLT_SUBDOMINIO",
    "auth_ref": "SMARTOLT_API_KEY",
    "auth_esquema": "",
    "auth_header": "X-Token",
    "endpoint": "/api/onu/get_onu_full_status_info/{sn_onu}",
    "metodo": "GET",
    "filtros_verificados": {
        "id_servicio": {"param": "id_servicio", "tipo": "id",
                        "verificado_el": "2026-10-07"},
    },
}

ROL = "supervisor_noc"

#  Lo que el Supervisor VE del diagnostico. NO esta el serial, y esa ausencia es
#  el diseno: si saliera, bastaria una conversacion para cosecharlos y la
#  garantia de inyeccion se perderia por otra puerta.
CAMPOS = ["id_servicio", "equipo_registrado", "estado", "causa_caida",
          #  'senal' es la CLASIFICACION que calcula el codigo; 'senal_dbm' el
          #  numero crudo. Los dos, porque el modelo no compara numeros y la
          #  persona que lea la propuesta si quiere ver el valor.
          "senal_dbm", "senal",
          #  'estado_config' es el 'Match state' de la OLT y NO habla de la
          #  señal. Estuvo mapeado a un campo llamado 'senal_texto' y la primera
          #  corrida real devolvio 'mismatch' ahi con una señal buena.
          "estado_config",
          "ultima_caida", "ultima_conexion", "motivo"]


def _mutar(cfg: dict) -> None:
    """Agrega la herramienta y sus dos autorizaciones. Idempotente."""
    #  REEMPLAZA si ya existe, no la saltea. La primera version se escribio con
    #  un 'base_url_ref' que no existe ('SMARTOLT_BASE_URL' en vez de
    #  'SMARTOLT_SUBDOMINIO') y quedo en la base sin poder resolver su URL. Un
    #  script que solo agregue cuando falta no puede arreglar eso, y obligaria a
    #  editar produccion a mano -- que es justo lo que este script evita.
    hs = cfg.setdefault("herramientas", [])
    for i, h in enumerate(hs):
        if h.get("nombre") == HERRAMIENTA["nombre"]:
            hs[i] = dict(HERRAMIENTA)
            break
    else:
        hs.append(dict(HERRAMIENTA))

    roles = cfg.setdefault("roles", {})
    rol = roles.get(ROL)
    if rol is None:
        raise SystemExit(
            f"el rol '{ROL}' no existe en la base de este tenant. No se "
            f"inventa: revisar que configuracion esta cargada.")

    puede = rol.setdefault("puede_consultar", [])
    if HERRAMIENTA["nombre"] not in puede:
        puede.insert(0, HERRAMIENTA["nombre"])

    campos = rol.setdefault("campos_permitidos", {})
    campos[HERRAMIENTA["nombre"]] = list(CAMPOS)


def _estado_actual(cfg: dict) -> dict:
    """Que hay hoy, para poder decir que cambiaria."""
    hs = cfg.get("herramientas") or []
    rol = (cfg.get("roles") or {}).get(ROL) or {}
    return {
        "herramienta": any(h.get("nombre") == HERRAMIENTA["nombre"] for h in hs),
        #  No alcanza con que ESTE: puede estar mal. Se compara el campo que ya
        #  fallo una vez, que es el que decide si la herramienta puede siquiera
        #  armar su URL.
        "ref_correcta": any(h.get("nombre") == HERRAMIENTA["nombre"]
                            and h.get("base_url_ref") == HERRAMIENTA["base_url_ref"]
                            for h in hs),
        "puede_consultar": HERRAMIENTA["nombre"] in (rol.get("puede_consultar") or []),
        "campos": (rol.get("campos_permitidos") or {}).get(HERRAMIENTA["nombre"]),
        "cuantas_herramientas": len(hs),
        "rol_existe": bool(rol),
    }


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[2] not in ("--ver", "--aplicar"):
        print(__doc__)
        return 2
    tenant, modo = sys.argv[1], sys.argv[2]

    from nucleo.config import fuente

    cfg = fuente.cargar(tenant).model_dump(mode="json", exclude_none=True)
    antes = _estado_actual(cfg)

    print(f"\n  TENANT: {tenant}")
    print(f"  herramientas en la base ahora: {antes['cuantas_herramientas']}")
    if not antes["rol_existe"]:
        print(f"  >>> el rol '{ROL}' NO existe en la base. Se detiene.")
        return 1

    print(f"\n  QUE HAY HOY:")
    print(f"    la herramienta declarada ......... {'SI' if antes['herramienta'] else 'no'}")
    print(f"    el rol puede consultarla ......... {'SI' if antes['puede_consultar'] else 'no'}")
    print(f"    campos permitidos del rol ........ {antes['campos'] or 'ninguno'}")

    print(f"    base_url_ref correcta ............ "
          f"{'SI' if antes['ref_correcta'] else 'NO'}")

    if (antes["herramienta"] and antes["ref_correcta"]
            and antes["puede_consultar"] and antes["campos"]):
        print("\n  Ya esta todo puesto. No hay nada que aplicar.\n")
        return 0

    print(f"\n  QUE CAMBIARIA:")
    if not antes["herramienta"]:
        print(f"    + herramienta '{HERRAMIENTA['nombre']}' (tipo interno, solo lectura)")
    elif not antes["ref_correcta"]:
        print(f"    ~ herramienta '{HERRAMIENTA['nombre']}' se REEMPLAZA "
              f"(su base_url_ref estaba mal)")
    if not antes["puede_consultar"]:
        print(f"    + '{ROL}'.puede_consultar += {HERRAMIENTA['nombre']}")
    if antes["campos"] != CAMPOS:
        print(f"    + '{ROL}'.campos_permitidos[{HERRAMIENTA['nombre']}] = {CAMPOS}")
    print("\n    No se toca NINGUNA otra herramienta, ningun otro rol, ningun agente.")

    if modo == "--ver":
        print("\n  Modo --ver: no se escribio nada.\n")
        return 0

    from nucleo.config import editor
    editor._editar(tenant, _mutar)

    #  Se vuelve a LEER de la base para afirmar sobre el efecto, no sobre que la
    #  funcion no levanto. Una escritura que no se relee no esta comprobada.
    despues = _estado_actual(
        fuente.cargar(tenant).model_dump(mode="json", exclude_none=True))
    ok = (despues["herramienta"] and despues["ref_correcta"]
          and despues["puede_consultar"] and despues["campos"] == CAMPOS)
    print(f"\n  APLICADO. Releido de la base: "
          f"herramienta={'SI' if despues['herramienta'] else 'NO'}, "
          f"ref={'SI' if despues['ref_correcta'] else 'NO'}, "
          f"puede_consultar={'SI' if despues['puede_consultar'] else 'NO'}, "
          f"campos={'SI' if despues['campos'] == CAMPOS else 'NO'}")
    if not ok:
        print("  >>> NO quedo como se esperaba. Revisar antes de seguir.\n")
        return 1
    print("\n  Siguiente: py -3.13 cli/diferencias_config.py " + tenant)
    print("             py -3.13 cli/evaluar.py " + tenant + " --humo --base\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
