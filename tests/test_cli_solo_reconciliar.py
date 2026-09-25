# -*- coding: utf-8 -*-
"""
'--solo-reconciliar' refresca los external_* y NO PUEDE crear un caso.

    py -3.13 tests/test_cli_solo_reconciliar.py

Corre SIN RED y SIN BASE: el CLI se ejecuta de verdad, con cada salida al mundo
sustituida por una funcion que registra lo que se le pidio.

POR QUE EXISTE
--------------
El dry-run del 25/09/2026 en produccion dio 161 casos elegibles para
reconciliar y 16 candidatos NUEVOS. Se necesita lo primero y no lo segundo: los
161 recuperan el estado de WispHub que el reloj no puede escribir, y los 16
crearian casos que nadie pidio en una corrida de recuperacion.

La alternativa era '--dias 1', que acota la ventana del listado y por lo tanto
reduce los candidatos -- pero no los elimina: un ticket nuevo de hoy entraria
igual. Una bandera que DICE lo que hace es mejor que un parametro que lo
consigue de refilon.

LO QUE SE AFIRMA
----------------
El EFECTO: que la herramienta de creacion no se llame ni una vez, y que la de
reconciliacion se llame una vez por caso elegible. No que el codigo tenga un
'if': un 'if' se puede agregar en un sitio y olvidar en otro, y de hecho el
corte real esta en DOS sitios a proposito.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
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
#  el andamio: un tenant con la forma de produccion, y cero red
# =============================================================================

from nucleo.config.schema import (AreaDeTrabajo, DestinoTicket,  # noqa: E402
                                  ImportacionTickets, Herramienta)

import cli.importar_tickets as cli                            # noqa: E402


#  161 elegibles y 16 candidatos nuevos: las mismas cifras que el dry-run de
#  produccion, para que lo que se prueba sea el caso real y no uno de juguete.
ELEGIBLES = 161
CANDIDATOS_NUEVOS = 16


class ConfigFalsa:
    def __init__(self):
        self.identidad = type("I", (), {"slug": "rapilink"})()
        self.importacion_tickets = ImportacionTickets(
            cada_horas=1,
            proveedor="wisphub",
            departamentos=["Soporte Técnico"],
            asuntos=["soporte tecnico|no tiene internet"],
            estados_descubrimiento=["Nuevo", "En Progreso"],
            reconciliar_estados=["New", "Assigned", "Pending"],
            gracia_cierre_dias=7,
            ventana_dias=30,
            destinos={"soporte tecnico|no tiene internet":
                      DestinoTicket(area="soporte")},
        )
        self.areas = [AreaDeTrabajo(nombre="soporte", etiqueta="Soporte")]
        self.variables_tenant = {}
        self.herramientas = [
            Herramienta(nombre="importar_caso_externo", tipo="http",
                        descripcion="crea el caso", solo_lectura=False,
                        requiere_confirmacion=True,
                        roles_permitidos=["administracion"],
                        base_url="http://backend:8000/api",
                        endpoint="/importacion/casos/", metodo="POST"),
            Herramienta(nombre="reconciliar_caso_externo", tipo="http",
                        descripcion="refresca los external_*", solo_lectura=False,
                        requiere_confirmacion=True,
                        roles_permitidos=["administracion"],
                        base_url="http://backend:8000/api",
                        endpoint="/importacion/casos/{id_caso}/reconciliar/",
                        metodo="POST"),
        ]


def _caso(n, status="New"):
    return {"id": f"caso-{n}", "external_ticket_id": str(90000 + n),
            "status": status, "closed_on": None, "external_status": "Nuevo",
            "external_created_by": "SHEILA - licencia@rapilink-sas",
            "external_created_by_type": "humano_verificado",
            "external_fetch_error": ""}


def _ticket_nuevo(n):
    """Un ticket que el descubrimiento aceptaria: departamento y asunto validos."""
    return {"id_ticket": 95000 + n, "departamento": "Soporte Técnico",
            "asunto": "No Tiene Internet", "estado": "Nuevo",
            "creado_por": "SHEILA - licencia@rapilink-sas",
            "servicio": {"id_servicio": 6580 + n}}


def correr(argv):
    """
    Corre el CLI de verdad con todas sus salidas al mundo instrumentadas.

    Devuelve (llamadas, salida). 'llamadas' cuenta por nombre de funcion, que es
    lo unico que importa: si 'aplicar' se llamo, se creo un caso.
    """
    llamadas = {"listar_tickets": 0, "aplicar": 0, "aplicar_reconciliacion": 0,
                "casos_de_este_proveedor": 0, "ids_a_conocidos": []}

    casos = [_caso(i) for i in range(ELEGIBLES)]
    tickets = [_ticket_nuevo(i) for i in range(CANDIDATOS_NUEVOS)]

    def _listar(config, tenant, desde, hasta, tope=5000):
        llamadas["listar_tickets"] += 1
        return list(tickets)

    def _casos(config, tenant):
        llamadas["casos_de_este_proveedor"] += 1
        return list(casos)

    def _conocidos(config, tenant, ids):
        llamadas["ids_a_conocidos"] = list(ids)
        return set(ids), set()

    def _aplicar(config, tenant, veredictos, actor=""):
        llamadas["aplicar"] += 1
        creados = sum(1 for v in veredictos if v.resultado == "candidato")
        return {"creados": creados, "ya_estaban": 0, "fallidos": 0}

    def _aplicar_rec(config, tenant, cambios, actor=""):
        llamadas["aplicar_reconciliacion"] += 1
        llamadas["reconciliados"] = len(cambios)
        return {"actualizados": len(cambios), "sin_cambios": 0, "fallidos": 0}

    def _leer_ticket(config, tenant, id_ticket):
        return {"id_ticket": int(id_ticket), "estado": "Cerrado",
                "creado_por": "SHEILA - licencia@rapilink-sas",
                "fecha_final": "09/20/2026 10:00:00", "respuestas": []}

    def _resolver(config, tenant):
        return lambda ids: {i: {"sn_onu": "SN", "nombre": "CLIENTE"} for i in ids}

    #  La config sale de la base via 'fuente.cargar'. Se sustituye el atributo
    #  del modulo 'fuente' tal como el CLI lo usa, no una copia importada.
    fuente_real = cli.fuente.cargar
    cli.fuente.cargar = lambda tenant, raiz=None: ConfigFalsa()

    guardado = {}
    for nombre, falso in (
        ("listar_tickets", _listar),
        ("casos_de_este_proveedor", _casos),
        ("tickets_conocidos", _conocidos),
        ("aplicar", _aplicar),
        ("aplicar_reconciliacion", _aplicar_rec),
        ("leer_ticket", _leer_ticket),
        ("resolver_servicios", _resolver),
    ):
        if hasattr(cli, nombre):
            guardado[nombre] = getattr(cli, nombre)
            setattr(cli, nombre, falso)

    #  Las areas salen de la base: se sustituye el modulo entero de persistencia
    #  por uno que contesta una persona con area, que es lo minimo para que el
    #  descubrimiento pueda asignar responsable.
    persistencia_real = cli.persistencia
    cli.persistencia = type("P", (), {
        "areas_de_colaboradores": staticmethod(lambda t: {"p-ana": "soporte"})})()

    buffer = io.StringIO()
    try:
        sys.argv = ["importar_tickets.py"] + argv
        with redirect_stdout(buffer):
            cli.main()
    finally:
        for nombre, real in guardado.items():
            setattr(cli, nombre, real)
        cli.persistencia = persistencia_real
        cli.fuente.cargar = fuente_real

    return llamadas, buffer.getvalue()


# =============================================================================
#  1. LA BANDERA NO PUEDE CREAR NADA
# =============================================================================

print("\n--solo-reconciliar no crea ni un caso")

l, salida = correr(["rapilink", "--solo-reconciliar", "--aplicar"])

revisar(l["aplicar"] == 0,
        "'aplicar' NO se llamo ni una vez",
        "es la unica funcion que crea casos; si se llamo, la bandera no sirve")
revisar(l["listar_tickets"] == 0,
        "y no se listo WispHub: sin tickets no hay candidatos",
        "el corte va en el origen del dato, no en un if antes de escribir")
revisar("0 casos creados" in salida,
        "la ultima linea dice que no se creo ninguno")
revisar("NO se crea ningun caso" in salida,
        "y lo avisa ANTES de empezar, no solo al final")

# =============================================================================
#  2. Y SI RECONCILIA LOS 161
# =============================================================================

print("\ny reconcilia todos los casos elegibles")

revisar(l["aplicar_reconciliacion"] == 1,
        "'aplicar_reconciliacion' se llamo una vez")
revisar(l.get("reconciliados") == ELEGIBLES,
        f"con los {ELEGIBLES} casos elegibles",
        f"llego {l.get('reconciliados')}: la bandera no debe recortar el lote")
revisar(l["casos_de_este_proveedor"] == 1,
        "los casos se leyeron una sola vez")

#  El set de 'tickets que abrio Dexter' alimenta la clasificacion de autoria. En
#  este modo sale de los ids de los CASOS, no del listado: con un set vacio, un
#  caso cuyo tipo guardado no fuera ya 'dexter' podria degradarse.
revisar(len(l["ids_a_conocidos"]) == ELEGIBLES,
        "y el registro de autoria se armo con los ids de los propios casos",
        f"llegaron {len(l['ids_a_conocidos'])} ids: con la lista vacia, la "
        f"clasificacion de autoria puede empeorar sola")

# =============================================================================
#  3. EL DRY-RUN DE ESTE MODO TAMPOCO ESCRIBE
# =============================================================================

print("\nsin --aplicar no escribe nada, ni siquiera reconciliando")

l2, salida2 = correr(["rapilink", "--solo-reconciliar"])
revisar(l2["aplicar"] == 0 and l2["aplicar_reconciliacion"] == 0,
        "ninguna de las dos escrituras se llamo",
        "'--dry-run' es el default y tiene que seguir siendolo con la bandera nueva")
revisar(l2["casos_de_este_proveedor"] == 1,
        "pero los casos SI se leyeron: el dry-run tiene que poder informar")
revisar("RECONCILIACION" in salida2,
        "y se imprimio el informe de que cambiaria")

# =============================================================================
#  4. LA BANDERA IMPLICA --reconciliar
# =============================================================================

print("\nla bandera sola alcanza: implica --reconciliar")

revisar(l2["casos_de_este_proveedor"] == 1,
        "pasarla sin --reconciliar igual reconcilia",
        "sin la implicacion, el comando no haria nada y diria que no actualizo "
        "ningun caso -- sobre la bandera que se pidio para actualizar")

# =============================================================================
#  5. EL MODO NORMAL NO CAMBIO
# =============================================================================

print("\nel modo de siempre sigue creando, que es lo que hace")

l3, salida3 = correr(["rapilink", "--reconciliar", "--aplicar"])
revisar(l3["listar_tickets"] == 1,
        "sin la bandera SI se lista WispHub")
revisar(l3["aplicar"] == 1,
        "y 'aplicar' se llama",
        "si esto falla, la bandera nueva rompio el camino existente")
revisar(l3["aplicar_reconciliacion"] == 1 and l3.get("reconciliados") == ELEGIBLES,
        "y la reconciliacion sigue alcanzando los mismos casos")
revisar("Importacion aplicada" in salida3,
        "con el mensaje final de siempre")

# =============================================================================
print()
if fallos:
    print(f"[FALLAN {len(fallos)}] " + " | ".join(fallos))
    raise SystemExit(1)
print(f"[OK] --solo-reconciliar refresca {ELEGIBLES} casos y crea 0.")
