# -*- coding: utf-8 -*-
"""
El backfill del nombre del cliente: quien resuelve, quien escribe, y quien NO.

    py -3.13 tests/test_backfill_nombre_cliente.py

Corre SIN RED y SIN BASE. Todo lo que sale al mundo entra como funcion.

LO QUE ESTE TEST DEFIENDE, EN UNA LINEA
---------------------------------------
Que el motor no escriba en las tablas del CRM. La primera version de este
comando hacia un UPDATE directo sobre public."case" y estaba roto por dos
caminos medidos en produccion el 25/09/2026 -- 'app_backend' sin privilegios
sobre esa tabla, y la RLS comparando contra 'app.current_org' mientras el motor
fija 'app.current_tenant'. Habria informado "0 actualizados" sin un error, que
es la peor forma de fallar.

Ninguna prueba lo habria visto, porque no habia ninguna sobre ese camino. Esta
es la que falta.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


# =============================================================================
#  1. LA FRONTERA  --  el que protege contra el fallo silencioso
# =============================================================================

print("\nel motor no escribe en las tablas del CRM")

#  Se lee el CODIGO, porque lo que hay que afirmar es una AUSENCIA: que no
#  exista ninguna sentencia SQL contra una tabla de Django. Eso no se puede
#  ejercitar llamando a nada -- un camino que no se recorre no se prueba
#  recorriendolo.
#
#  El alcance es todo nucleo/ mas cli/backfill_nombre_cliente.py, y las tablas
#  buscadas son las del CRM: 'case' (con y sin comillas), 'accounts',
#  'campo_*', 'operaciones_*'. Las del motor viven en el esquema 'asistente' y
#  esas si son suyas.
TABLAS_DEL_CRM = re.compile(
    r"""(?ix)
    \b (insert \s+ into | update | delete \s+ from) \s+
    (public\.)? ["']? (case|accounts|contacts|campo_\w+|operaciones_\w+) ["']?
    """)

def escribe_en_el_crm(texto: str) -> bool:
    """
    Si este codigo tiene una escritura SQL contra una tabla del CRM.

    Los comentarios se quitan PRIMERO: este mismo repo explica el problema
    citando la sentencia prohibida en prosa, y una guarda que confunde la
    explicacion con el delito reclama por su propia documentacion. Por eso la
    comprobacion es esta funcion y no el patron suelto -- probar el patron
    aparte deja el descomentado sin probar, que es justo la mitad que importa.
    """
    return bool(TABLAS_DEL_CRM.search(re.sub(r"#[^\n]*", "", texto)))


archivos = list((RAIZ / "nucleo").rglob("*.py"))
archivos.append(RAIZ / "cli" / "backfill_nombre_cliente.py")

culpables = [
    str(a.relative_to(RAIZ)) for a in archivos
    if escribe_en_el_crm(a.read_text(encoding="utf-8", errors="replace"))
]

revisar(culpables == [],
        "ninguna escritura SQL del motor apunta a una tabla del CRM",
        f"sin privilegios y con la RLS de otra variable, un UPDATE de aca "
        f"informa 0 filas SIN error (culpables: {culpables})")

#  Y la guarda se comprueba a si misma, por el mismo camino que usa arriba: si
#  el patron no cazara nada, la afirmacion anterior pasaria con el problema vivo.
revisar(escribe_en_el_crm('cur.execute("""update public."case" set x = 1""")'),
        "y la guarda SI reconoce la sentencia que se quiere prohibir")
revisar(not escribe_en_el_crm('# antes hacia update public."case" y fallaba'),
        "sin reclamar por el comentario que lo explica")

#  El camino que SI existe: la herramienta HTTP del catalogo.
from nucleo.seguimiento import importacion_io as io      # noqa: E402

fuente_io = (RAIZ / "nucleo" / "seguimiento" / "importacion_io.py").read_text(
    encoding="utf-8")
revisar("fijar_nombre_cliente_externo" in fuente_io,
        "el motor escribe el nombre por una herramienta del catalogo",
        "misma via que importar_caso_externo y reconciliar_caso_externo")


# =============================================================================
#  2. QUE VIAJA AL CRM  --  dos datos, y nada mas
# =============================================================================

print("\nal CRM le llegan el servicio y el nombre, nada mas")


class HerramientaFalsa:
    nombre = "fijar_nombre_cliente_externo"


class ConfigFalsa:
    herramientas = [HerramientaFalsa()]
    variables_tenant = {}


enviados = []


def _ejecutar_falso(herr, cuerpo, tenant, variables_tenant=None):
    enviados.append(cuerpo)
    return {"actualizados": 1, "ya_tenian": 0, "sin_nombre": False}


class _PuertaFalsa:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


_ejecutor_real = io.ejecutor_http.ejecutar
_puerta_real = io._puerta
io.ejecutor_http.ejecutar = _ejecutar_falso
io._puerta = lambda *a, **k: _PuertaFalsa()

r = io.fijar_nombre_cliente(ConfigFalsa(), "rapilink", "6580",
                            "JUAN DAVID BARRIOS BARRIOS")
revisar(r == {"actualizados": 1, "ya_tenian": 0, "sin_nombre": False},
        "la respuesta del CRM se devuelve tal cual")
revisar(len(enviados) == 1 and set(enviados[0]) == {"external_service_id",
                                                    "external_client_name"},
        "y el cuerpo lleva EXACTAMENTE dos claves",
        f"nada de cedula, telefono ni direccion (lleva: {sorted(enviados[0])})")
revisar(enviados[0]["external_service_id"] == "6580"
        and enviados[0]["external_client_name"] == "JUAN DAVID BARRIOS BARRIOS",
        "con los valores que se le pasaron")
revisar("org" not in enviados[0] and "external_ticket_id" not in enviados[0],
        "sin organizacion ni id de caso: los decide el CRM desde el token",
        "mandar la org seria darle al motor la forma de escribir en otro tenant")


# =============================================================================
#  3. QUE SE CONSIDERA PENDIENTE
# =============================================================================

print("\nlos pendientes salen de la API, no de una consulta a la tabla")

CASOS = [
    {"external_ticket_id": "90001", "external_service_id": "6580",
     "tiene_nombre_cliente": False},
    {"external_ticket_id": "90002", "external_service_id": "6580",
     "tiene_nombre_cliente": False},
    {"external_ticket_id": "90003", "external_service_id": "7001",
     "tiene_nombre_cliente": True},
    {"external_ticket_id": "90004", "external_service_id": "7002",
     "tiene_nombre_cliente": False},
    # Un caso sin servicio: no hay con que preguntarle al proveedor.
    {"external_ticket_id": "90005", "external_service_id": "",
     "tiene_nombre_cliente": False},
]

_casos_real = io.casos_de_este_proveedor
io.casos_de_este_proveedor = lambda config, tenant: CASOS

pendientes = io.casos_sin_nombre_de_cliente(ConfigFalsa(), "rapilink")
revisar(set(pendientes) == {"6580", "7002", ""},
        "solo los que NO tienen nombre, agrupados por servicio")
revisar(pendientes["6580"] == ["90001", "90002"],
        "un servicio con dos casos aparece una vez, con sus dos tickets",
        "la unidad de trabajo es la llamada al proveedor, que es por servicio")
revisar("7001" not in pendientes,
        "el que ya tiene nombre no entra")
revisar(pendientes[""] == ["90005"],
        "y el caso sin servicio se cuenta aparte, no se descarta en silencio")


# =============================================================================
#  4. EL COMANDO  --  dry-run, tope, y la cuenta
# =============================================================================

print("\nel dry-run no escribe, y --tope corta por servicio")

import importlib.util                                    # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "backfill_nc", RAIZ / "cli" / "backfill_nombre_cliente.py")
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)

backfill.importacion_io.casos_de_este_proveedor = lambda config, tenant: CASOS

plan, sin_servicio = backfill.planificar(ConfigFalsa(), "rapilink", 0)
revisar(set(plan) == {"6580", "7002"},
        "sin tope entran todos los servicios resolubles")
revisar(sin_servicio == ["90005"],
        "y los casos sin servicio salen aparte del plan")

plan_1, _ = backfill.planificar(ConfigFalsa(), "rapilink", 1)
revisar(len(plan_1) == 1,
        "--tope 1 deja UN servicio",
        "corta por servicio y no por caso: cortar por casos dejaria un "
        "servicio a medio resolver")

#  Y el tope no parte un servicio: el que entra, entra con todos sus casos.
revisar(all(len(v) == len(plan[k]) for k, v in plan_1.items()),
        "y el servicio que entra se lleva todos sus casos")

#  DRY-RUN: se corre el main() entero con la escritura instrumentada. Se afirma
#  sobre el EFECTO -- que no se llamo a la ruta del CRM -- y no sobre que el
#  codigo tenga un 'if'.
escrituras = []
backfill.importacion_io.fijar_nombre_cliente = (
    lambda *a, **k: escrituras.append(a) or {"actualizados": 1, "ya_tenian": 0})
backfill.importacion_io.resolver_servicios = (
    lambda config, tenant: lambda ids: {i: {"nombre": f"CLIENTE {i}"} for i in ids})
backfill.fuente.cargar = lambda tenant: ConfigFalsa()

sys.argv = ["backfill", "rapilink", "--tope", "20", "--dry-run"]
codigo = backfill.main()
revisar(codigo == 0, "el dry-run termina en 0")
revisar(escrituras == [],
        "DRY-RUN: no se llamo a la ruta de escritura del CRM ni una vez",
        "es la unica garantia que hace que correrlo sea inofensivo")

sys.argv = ["backfill", "rapilink", "--tope", "20", "--aplicar"]
codigo = backfill.main()
revisar(codigo == 0, "y con --aplicar tambien termina en 0")
revisar(len(escrituras) == 2,
        "con --aplicar se escribe UNA vez por servicio resoluble",
        f"dos servicios pendientes, dos llamadas (hubo {len(escrituras)})")

#  Un servicio para el que el proveedor no da nombre NO se manda: escribir
#  vacio borraria el pendiente sin resolverlo.
escrituras.clear()
backfill.importacion_io.resolver_servicios = (
    lambda config, tenant: lambda ids: {i: {"nombre": ""} for i in ids})
sys.argv = ["backfill", "rapilink", "--aplicar"]
backfill.main()
revisar(escrituras == [],
        "sin nombre del proveedor no se manda nada al CRM")

#  Las dos banderas juntas no son una combinacion valida: elegir por defecto
#  una de las dos seria adivinar cual quiso quien la escribio.
sys.argv = ["backfill", "rapilink", "--aplicar", "--dry-run"]
revisar(backfill.main() == 2,
        "--aplicar y --dry-run a la vez se rechaza, no se adivina")


# =============================================================================
io.ejecutor_http.ejecutar = _ejecutor_real
io._puerta = _puerta_real
io.casos_de_este_proveedor = _casos_real

print()
if fallos:
    print(f"[FALLAN {len(fallos)}] " + " | ".join(fallos))
    raise SystemExit(1)
print("[OK] El motor resuelve y pide; el CRM escribe. El dry-run no escribe.")
