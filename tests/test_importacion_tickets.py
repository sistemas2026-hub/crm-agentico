# -*- coding: utf-8 -*-
"""
El importador de tickets del sistema del ISP: que entra, a quien, y que NO.

    py -3.13 tests/test_importacion_tickets.py

Corre SIN RED y SIN BASE. Todo lo que sale al mundo -- listar tickets, leer un
cliente, saber que casos existen-- entra como funcion, asi que los caminos que
importan (los de fallo) se pueden probar de verdad en vez de esperar a que
ocurran en produccion.

LO QUE ESTE TEST DEFIENDE, EN UNA LINEA
---------------------------------------
Que una lista vacia no importe nada. Medido el 08/09/2026: WispHub crea 83
tickets por dia contra los 66 casos que la bandeja tiene en total, asi que la
lectura 'vacio = todo' convertiria un olvido de configuracion en 2.400 casos
al mes. Es el unico test de aca que protege contra un desastre y no contra un
error.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config.schema import (AreaDeTrabajo, DestinoTicket,  # noqa: E402
                                  ImportacionTickets)
from nucleo.seguimiento import importacion as imp  # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


# =============================================================================
#  Andamio: una config minima y unos tickets con la forma REAL del proveedor
# =============================================================================

class ConfigFalsa:
    """Lo unico que el importador mira de la config del tenant."""

    def __init__(self, importacion, areas=("soporte",)):
        self.importacion_tickets = importacion
        self.areas = [AreaDeTrabajo(nombre=a, etiqueta=a.title()) for a in areas]


CUENTA_API = "Rapilink SAS - admin@rapilink-sas"
PLACEHOLDER = "3545"


def ticket(id_ticket, departamento="Soporte Técnico", asunto="No Tiene Internet",
           servicio="5832", creado_por="SHEILA - licencia@rapilink-sas",
           estado="Nuevo"):
    """La forma REAL que devuelve GET /api/tickets/, no una inventada."""
    return {
        "id_ticket": id_ticket,
        "departamento": departamento,
        "asunto": asunto,
        "estado": estado,
        "creado_por": creado_por,
        "servicio": {"id_servicio": int(servicio) if servicio else None},
    }


def config_piloto(**extra):
    base = dict(
        departamentos=["Soporte Técnico"],
        asuntos=["soporte tecnico|no tiene internet"],
        estados_descubrimiento=["Nuevo", "En Progreso"],
        destinos={"soporte tecnico|no tiene internet": DestinoTicket(area="soporte")},
    )
    base.update(extra)
    return ConfigFalsa(ImportacionTickets(**base))


AREAS_UNA_PERSONA = {"p-ana": "soporte"}


def descubrir(config, tickets, **kw):
    kw.setdefault("conocidos", set())
    kw.setdefault("registrados_por_dexter", set())
    kw.setdefault("areas_por_persona", AREAS_UNA_PERSONA)
    kw.setdefault("cuenta_api", CUENTA_API)
    kw.setdefault("servicio_placeholder", PLACEHOLDER)
    kw.setdefault("resolver_servicio", lambda ids: {i: {"sn_onu": f"SN{i}"} for i in ids})
    return imp.descubrir(config, tickets, **kw)


def resultados(vs):
    return [v.resultado for v in vs]


# =============================================================================
#  1. FAIL CLOSED  --  el que protege contra el desastre
# =============================================================================

print("\nlista vacia significa NADA, nunca 'todo'")

vacia = ConfigFalsa(ImportacionTickets())
vs = descubrir(vacia, [ticket(1), ticket(2), ticket(3)])
revisar(all(v.resultado == imp.DESCARTADO_POR_DEPARTAMENTO for v in vs),
        "con la config por defecto no entra ni un ticket",
        "si esto falla, un despliegue sin configurar importa 2.400 casos al mes")
revisar(ImportacionTickets().cada_horas == 0,
        "y el barrido nace apagado (cada_horas = 0)")
revisar(not imp.debe_correr(ImportacionTickets()),
        "con cada_horas en 0, al barrido nunca le toca",
        "es la compuerta: desplegar el codigo no puede empezar a importar solo")
_ahora = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
revisar(imp.debe_correr(ImportacionTickets(cada_horas=1), None, _ahora),
        "encendido y sin corrida previa, le toca")
revisar(not imp.debe_correr(ImportacionTickets(cada_horas=6),
                            _ahora - timedelta(hours=2), _ahora),
        "y no vuelve a correr antes de tiempo")

solo_dep = ConfigFalsa(ImportacionTickets(departamentos=["Soporte Técnico"]))
vs = descubrir(solo_dep, [ticket(1)])
revisar(resultados(vs) == [imp.DESCARTADO_POR_ASUNTO],
        "el departamento permitido no alcanza: sin asuntos tampoco entra nada")


# =============================================================================
#  2. FILTRO  --  departamento + asunto, porque el asunto solo no distingue
# =============================================================================

print("\nel filtro es departamento + asunto")

cfg = config_piloto()
revisar(resultados(descubrir(cfg, [ticket(10)])) == [imp.CANDIDATO],
        "un ticket permitido llega a candidato")
revisar(resultados(descubrir(cfg, [ticket(11, departamento="Finanzas")]))
        == [imp.DESCARTADO_POR_DEPARTAMENTO],
        "otro departamento queda afuera")
revisar(resultados(descubrir(cfg, [ticket(12, asunto="Descuento")]))
        == [imp.DESCARTADO_POR_ASUNTO],
        "otro asunto queda afuera")

# El caso que obliga a que la clave lleve el departamento adentro: el mismo
# asunto existe en dos, con 100 tickets en uno y 28 en el otro.
dos_deps = ConfigFalsa(ImportacionTickets(
    departamentos=["Soporte Técnico", "Administrativo"],
    asuntos=["soporte tecnico|cambio de contrasena en router wifi"],
    estados_descubrimiento=["Nuevo"],
    destinos={"soporte tecnico|cambio de contrasena en router wifi":
              DestinoTicket(area="soporte")}))
vs = descubrir(dos_deps, [
    ticket(20, departamento="Soporte Técnico", asunto="Cambio De Contraseña En Router Wifi"),
    ticket(21, departamento="Administrativo", asunto="Cambio De Contraseña En Router Wifi"),
])
revisar(resultados(vs) == [imp.CANDIDATO, imp.DESCARTADO_POR_ASUNTO],
        "el mismo asunto en dos departamentos son dos reglas independientes",
        "sin el departamento en la clave, habilitar uno habilitaria los dos")

revisar(imp.normalizar("Soporte Técnico") == "soporte tecnico"
        and imp.normalizar("  SOPORTE   TECNICO ") == "soporte tecnico",
        "los nombres se normalizan igual vengan como vengan",
        "el filtro compara nombres porque la API no da ids para estos campos")

# 'departamento|*' es como se expresa 'toda la cola de Soporte' sin listar 41
# asuntos que ademas cambian solos.
comodin = ConfigFalsa(ImportacionTickets(
    departamentos=["Soporte Técnico"], asuntos=["soporte tecnico|*"],
    estados_descubrimiento=["Nuevo"],
    destinos={"soporte tecnico|*": DestinoTicket(area="soporte")}))
vs = descubrir(comodin, [ticket(30), ticket(31, asunto="CONFIGURACION DNS")])
revisar(resultados(vs) == [imp.CANDIDATO, imp.CANDIDATO],
        "'departamento|*' acepta todos los asuntos de ese departamento")


# =============================================================================
#  3. AUTORIA  --  dicha con el cuidado que los datos permiten
# =============================================================================

print("\nla autoria se afirma solo hasta donde el proveedor la sostiene")

vs = descubrir(cfg, [ticket(40, creado_por="SHEILA - licencia@rapilink-sas")])
revisar(vs[0].external_created_by_type == imp.HUMANO_VERIFICADO,
        "una cuenta nominal del proveedor es humano_verificado")

vs = descubrir(cfg, [ticket(41, creado_por=CUENTA_API)],
               registrados_por_dexter={"41"})
revisar(vs[0].external_created_by_type == imp.DEXTER,
        "la cuenta de la API, con registro nuestro, es dexter")

vs = descubrir(cfg, [ticket(42, creado_por=CUENTA_API)])
revisar(vs[0].external_created_by_type == imp.EXTERNO_DESCONOCIDO,
        "la cuenta de la API sin registro nuestro es externo_desconocido",
        "medido: 91 tickets en dos semanas entran asi -- la clave esta compartida")

# Un ticket que Dexter creo pero que todavia no tiene Case NO se descarta por
# eso: si la whitelist lo acepta, entra, marcado como dexter.
revisar(vs[0].resultado == imp.CANDIDATO
        and descubrir(cfg, [ticket(43, creado_por=CUENTA_API)],
                      registrados_por_dexter={"43"})[0].resultado == imp.CANDIDATO,
        "un ticket de Dexter sin caso todavia sigue siendo candidato")

solo_humanos = config_piloto(tipos_de_creador=["humano_verificado"])
vs = descubrir(solo_humanos, [ticket(44, creado_por=CUENTA_API)])
revisar(resultados(vs) == [imp.DESCARTADO_POR_CREADOR],
        "el filtro por tipo de creador excluye lo que no esta en la lista")


# =============================================================================
#  4. DESTINO  --  area en la config, persona en el momento
# =============================================================================

print("\nel destino se configura como area y se resuelve como persona")

vs = descubrir(cfg, [ticket(50)])
revisar(vs[0].area == "soporte" and vs[0].responsable == "p-ana",
        "el area configurada resuelve a un responsable concreto")
revisar(not hasattr(vs[0], "area_persistida"),
        "el veredicto no propone escribir el area en el Case",
        "'Case' no tiene columna de area: sale del responsable")

varios = {"p-ana": "soporte", "p-beto": "soporte", "p-caro": "finanzas"}
vs = descubrir(cfg, [ticket(51)], areas_por_persona=varios,
               carga={"p-ana": 9, "p-beto": 1})
revisar(vs[0].responsable == "p-beto",
        "con varios en el area, elige el menos cargado (reparto compartido)")
vs = descubrir(cfg, [ticket(52)], areas_por_persona=varios)
revisar(vs[0].responsable == "p-ana",
        "y sin datos de carga el desempate es estable, no al azar")

vs = descubrir(cfg, [ticket(53)], areas_por_persona={"p-caro": "finanzas"})
revisar(resultados(vs) == [imp.SIN_RESPONSABLE_DISPONIBLE],
        "un area sin nadie NO crea el caso: fail closed",
        "sin responsable no hay area, y el caso quedaria invisible en __sin_area__")

sin_mapa = ConfigFalsa(ImportacionTickets(
    departamentos=["Soporte Técnico"], estados_descubrimiento=["Nuevo"],
    asuntos=["soporte tecnico|no tiene internet"]))
revisar(resultados(descubrir(sin_mapa, [ticket(54)])) == [imp.SIN_DESTINO_CONFIGURADO],
        "pasa el filtro pero no hay destino declarado: fail closed")

area_mala = config_piloto(destinos={
    "soporte tecnico|no tiene internet": DestinoTicket(area="inexistente")})
revisar(resultados(descubrir(area_mala, [ticket(55)])) == [imp.AREA_DESTINO_INVALIDA],
        "un area que no existe en la config es un motivo propio, no 'sin destino'")


# =============================================================================
#  5. IDENTIDAD  --  una consulta por SERVICIO, no por ticket
# =============================================================================

print("\nla identidad se resuelve por servicio unico")

llamadas = []


def resolver(ids):
    llamadas.append(list(ids))
    return {i: {"sn_onu": f"SN{i}"} for i in ids if i != "9999"}


vs = descubrir(cfg, [ticket(60, servicio="5832"), ticket(61, servicio="5832"),
                     ticket(62, servicio="6555")], resolver_servicio=resolver)
revisar(len(llamadas) == 1 and sorted(llamadas[0]) == ["5832", "6555"],
        "tres tickets sobre dos servicios: una sola resolucion, con dos ids",
        "medido: 1.162 tickets son 607 servicios -- consultar por ticket es el doble")
revisar(all(v.external_service_id for v in vs),
        "cada candidato conserva su external_service_id")
revisar(all(v.tiene_onu for v in vs), "y su sn_onu cuando el cliente lo tiene")

llamadas.clear()
vs = descubrir(cfg, [ticket(63, servicio="9999")], resolver_servicio=resolver)
revisar(vs[0].resultado == imp.CANDIDATO and not vs[0].cliente_identificado
        and not vs[0].tiene_onu,
        "un servicio que no resuelve sigue siendo candidato, pero sin ONU")

llamadas.clear()
vs = descubrir(cfg, [ticket(64, servicio="9999")], resolver_servicio=resolver,
               conocidos={"64"})
revisar(vs[0].resultado == imp.YA_EXISTE and not llamadas,
        "un ticket que ya tiene caso no gasta ninguna consulta de identidad")

vs = descubrir(cfg, [ticket(65, servicio=None)])
revisar(resultados(vs) == [imp.SIN_SERVICIO],
        "un ticket sin servicio no se inventa una identidad")


# =============================================================================
#  6. INSTALACIONES NUEVAS  --  un registro, no una persona
# =============================================================================

print("\nel cliente ficticio de instalaciones no es un cliente")

llamadas.clear()
vs = descubrir(cfg, [ticket(70, servicio=PLACEHOLDER)], resolver_servicio=resolver)
v = vs[0]
revisar(v.identidad_es_placeholder and not v.cliente_identificado,
        "se marca como identidad no resuelta")
revisar(v.external_service_id == PLACEHOLDER,
        "se conserva la referencia externa: vino del proveedor y es cierta")
revisar(not v.sn_onu and (not llamadas or PLACEHOLDER not in llamadas[0]),
        "y NO se le busca ONU ni se lo consulta como cliente",
        "diagnosticar la ONU de un registro ficticio seria inventar un dato")


# =============================================================================
#  7. IDEMPOTENCIA  --  dos pasadas, un solo caso
# =============================================================================

print("\ndos pasadas seguidas no producen dos casos")

lote = [ticket(80), ticket(81)]
primera = descubrir(cfg, lote)
nuevos = {v.external_ticket_id for v in primera if v.resultado == imp.CANDIDATO}
revisar(nuevos == {"80", "81"}, "la primera pasada propone los dos")

segunda = descubrir(cfg, lote, conocidos=nuevos)
revisar(all(v.resultado == imp.YA_EXISTE for v in segunda),
        "la segunda, con esos casos ya creados, no propone ninguno",
        "el solapamiento de la ventana los vuelve a traer: aca se paran")

# Sin marca de agua: la ventana movil ES el checkpoint. Auditado antes de
# implementarla -- 'tenant_config' es configuracion EDITABLE, versionada y con
# copia completa en 'tenant_config_historial' en cada cambio; un watermark
# horario habria metido 24 versiones diarias de ruido de maquina en el registro
# de cambios humanos, y competido con la pantalla de ajustes por la misma fila.
conf = ImportacionTickets(ventana_dias=7)
desde, hasta = imp.ventana(conf, datetime(2026, 9, 9, 12, tzinfo=timezone.utc))
revisar(desde == "2026-09-02" and hasta == "2026-09-09",
        "la ventana es movil: siempre los ultimos 'ventana_dias'",
        "un ciclo que falla no deja nada atras porque no hay nada que avanzar")
revisar(not hasattr(ImportacionTickets(), "marca_de_agua"),
        "y la config NO guarda checkpoint de ejecucion",
        "configuracion y estado de un job son cosas distintas")
# El tope se valida al GUARDAR la config, no al pedir: un valor imposible
# tiene que verse cuando alguien lo escribe y no en el primer barrido.
try:
    ImportacionTickets(ventana_dias=400)
    revisar(False, "una ventana de 400 dias se rechaza al validar la config")
except Exception as e:
    revisar("entre 1 y 55" in str(e),
            "una ventana de 400 dias se rechaza al validar la config",
            "el proveedor responde HTTP 400 a mas de dos meses")
revisar(ImportacionTickets().ventana_dias == 30,
        "y la ventana operativa por defecto son 30 dias",
        "sin watermark, la ventana ES la red de recuperacion")


# =============================================================================
#  8. RECONCILIACION  --  external_status si, Case.status jamas
# =============================================================================

print("\nla reconciliacion no toca el estado de Dexter")

CASO = {"id": "c-1", "external_ticket_id": "91288", "status": "Assigned",
        "external_status": "Nuevo", "external_created_by": "",
        "external_created_by_type": "", "external_fetch_error": "algo viejo"}

cambios = imp.reconciliar(
    cfg, [dict(CASO)],
    leer_ticket=lambda t: ticket(t, estado="Cerrado", creado_por=CUENTA_API),
    cuenta_api=CUENTA_API, registrados_por_dexter=set())
c = cambios[0]
revisar("status" not in c.despues,
        "'Case.status' no esta entre lo que la reconciliacion cambiaria",
        "si aparece, el sondeo empieza a pisar el estado que decide una persona")
revisar(c.despues["external_status"] == "Cerrado",
        "'external_status' si se actualiza")
revisar(c.despues["external_created_by_type"] == imp.EXTERNO_DESCONOCIDO,
        "y la autoria se reclasifica con la misma regla que en descubrimiento")
revisar(c.despues["external_fetch_error"] == "" and c.despues["external_fetched_at"],
        "una lectura correcta limpia el error y sella la fecha de lectura")

# La divergencia se conserva: Dexter dice Assigned, el proveedor dice Cerrado,
# y nadie la resuelve sola.
revisar(CASO["status"] == "Assigned",
        "el caso original no se modifica: reconciliar solo propone")

roto = imp.reconciliar(
    cfg, [dict(CASO), {**CASO, "id": "c-2", "external_ticket_id": "99"}],
    leer_ticket=lambda t: (_ for _ in ()).throw(RuntimeError("502"))
    if t == "91288" else ticket(t),
    cuenta_api=CUENTA_API, registrados_por_dexter=set())
revisar(len(roto) == 2 and roto[0].error and not roto[1].error,
        "un ticket que falla no corta el lote: el otro se reconcilia igual")
revisar("status" not in roto[0].despues
        and roto[0].despues.get("external_fetch_error"),
        "y el fallo se escribe en la fila sin tocar el estado")

# El caso que costo un dry-run entero: con la herramienta equivocada, WispHub
# devuelve el LISTADO paginado en vez del ticket. Es un dict no vacio, asi que
# la guarda anterior lo daba por leido y proponia vaciar 'external_status' en
# los 16 casos conocidos -- "16/16 encontrados" con cero datos adentro.
listado = imp.reconciliar(
    cfg, [dict(CASO)],
    leer_ticket=lambda t: {"count": 534, "next": None, "results": [ticket(1)]},
    cuenta_api=CUENTA_API, registrados_por_dexter=set())
revisar(listado[0].error and "external_status" not in listado[0].despues,
        "un listado devuelto en vez de un ticket es un ERROR, no una lectura",
        "sin esto, la reconciliacion borra el estado que creia estar leyendo")

otro = imp.reconciliar(
    cfg, [dict(CASO)], leer_ticket=lambda t: ticket(99999),
    cuenta_api=CUENTA_API, registrados_por_dexter=set())
revisar(otro[0].error, "y un ticket con OTRO id tampoco se acepta")

cerrado_viejo = {"id": "c-3", "external_ticket_id": "1", "status": "Closed",
                 "closed_on": (datetime.now(timezone.utc)
                               - timedelta(days=90)).isoformat()}
cerrado_nuevo = {**cerrado_viejo, "id": "c-4",
                 "closed_on": (datetime.now(timezone.utc)
                               - timedelta(days=2)).isoformat()}
revisar(not imp.hay_que_reconciliar(cfg.importacion_tickets, cerrado_viejo),
        "un caso cerrado hace tres meses ya no se vuelve a consultar",
        "releer miles de cerrados es trafico permanente para no enterarse de nada")
revisar(imp.hay_que_reconciliar(cfg.importacion_tickets, cerrado_nuevo),
        "pero uno recien cerrado si, por la gracia: los dos cierres no coinciden")

# 'Case.closed_on' es un DateField: la base devuelve un 'date', no un
# 'datetime'. Con cadenas ISO esto pasaba en verde y reventaba con TypeError
# en el primer dry-run contra datos reales -- 'date.replace()' no acepta
# tzinfo. El test ahora usa la forma que la base entrega de verdad.
from datetime import date as _date  # noqa: E402

hoy = datetime.now(timezone.utc).date()
revisar(imp.hay_que_reconciliar(
    cfg.importacion_tickets, {"status": "Closed", "closed_on": hoy}),
    "un 'closed_on' que llega como date (no datetime) no rompe",
    "es exactamente lo que devuelve Django para un DateField")
revisar(not imp.hay_que_reconciliar(
    cfg.importacion_tickets,
    {"status": "Closed", "closed_on": _date(hoy.year - 1, 1, 1)}),
    "y un date viejo queda fuera de la gracia igual que un datetime viejo")


# =============================================================================
#  9. NADA DE ESCRITURA  --  ni a WispHub ni a Case
# =============================================================================

print("\nel importador no escribe en ningun lado")

fuente = (RAIZ / "nucleo" / "seguimiento" / "importacion.py").read_text(encoding="utf-8")
for verbo in ('"POST"', '"PATCH"', '"PUT"', "requests.post", "requests.patch",
              "requests.put", "metodo=\"POST\""):
    revisar(verbo not in fuente,
            f"el modulo no contiene {verbo}")
revisar("import requests" not in fuente and "ejecutor_http" not in fuente,
        "y no habla con nadie por su cuenta: todo lo externo entra como funcion",
        "asi el dry-run es el MISMO codigo que la corrida real, no una imitacion")
revisar("Case.objects" not in fuente and "insert into" not in fuente.lower(),
        "no crea ni actualiza ningun caso")

todos = descubrir(cfg, [ticket(90), ticket(91, departamento="Finanzas")])
r = imp.resumen(todos)
revisar(r["inspeccionados"] == 2 and r["candidatos"] == 1
        and "candidatos_por_responsable" in r,
        "el resumen cuenta lo que hay que mirar, incluido el reparto propuesto")


# =============================================================================
#  10. ESTADO EXTERNO  --  no importar problemas ya resueltos
# =============================================================================

print("\nlos cerrados no entran por descubrimiento")

revisar(resultados(descubrir(cfg, [ticket(100, estado="Cerrado")]))
        == [imp.DESCARTADO_POR_ESTADO],
        "un ticket ya Cerrado no crea caso",
        "medido: 118 de 139 del piloto ya estaban cerrados antes de existir Dexter")
revisar(resultados(descubrir(cfg, [ticket(101, estado="Nuevo")])) == [imp.CANDIDATO]
        and resultados(descubrir(cfg, [ticket(102, estado="En Progreso")]))
        == [imp.CANDIDATO],
        "'Nuevo' y 'En Progreso' si entran")

sin_estados = ConfigFalsa(ImportacionTickets(
    departamentos=["Soporte Técnico"],
    asuntos=["soporte tecnico|no tiene internet"],
    destinos={"soporte tecnico|no tiene internet": DestinoTicket(area="soporte")}))
revisar(resultados(descubrir(sin_estados, [ticket(103)])) == [imp.DESCARTADO_POR_ESTADO],
        "'estados_descubrimiento' vacio no importa ninguno, tampoco los nuevos")

llamadas.clear()
descubrir(cfg, [ticket(104, estado="Cerrado")], resolver_servicio=resolver)
revisar(not llamadas,
        "un descartado por estado no gasta ninguna consulta de identidad",
        "el filtro va ANTES del enriquecimiento, no despues")

# --- external_status_at: la fecha real, o nada -------------------------
# Las dos fechas del MISMO payload vienen en formatos distintos, y por poco se
# escribe mal:
#     fecha_creacion  2026-08-29T09:16:37.844072-05:00   ISO, con zona
#     fecha_fin       09/05/2026 15:22:38                MM/DD/YYYY, sin zona
# Guardar la segunda tal cual la habria archivado cinco horas antes de lo que
# paso, interpretada como UTC.
CERRADO = {"estado": "Cerrado", "fecha_fin": "09/05/2026 15:22:38",
           "fecha_creacion": "2026-08-29T09:16:37.844072-05:00"}
revisar(imp.momento_del_estado(CERRADO) == "2026-09-05T15:22:38-05:00",
        "de un cerrado se toma 'fecha_fin', normalizada y con zona",
        "la zona sale de 'fecha_creacion' del MISMO ticket: mismo sistema, "
        "mismo reloj, sin suponer el huso de ninguna empresa")
revisar(imp.momento_del_estado(
    {"estado": "Nuevo", "fecha_creacion": CERRADO["fecha_creacion"]}) is None,
    "de un nuevo NO se inventa un momento de cambio",
    "auditado: fecha_fin viene 40/40 en cerrados y 0/40 en nuevos")
revisar(imp.momento_del_estado({**CERRADO, "fecha_fin": None}) is None,
        "y sin fecha_fin tampoco se rellena con la lectura")
revisar(imp.momento_del_estado({**CERRADO, "fecha_fin": "2026-09-05 15:22:38"})
        is None,
        "un formato que no es el del proveedor no se adivina")
revisar(imp.momento_del_estado(
    {**CERRADO, "fecha_creacion": "2026-08-29 09:16:37"}) is None,
    "y sin zona de referencia no se afirma un instante",
    "un datetime sin zona guardado en una columna con zona corre las horas")
revisar(imp.momento_del_estado(CERRADO) is not None
        and imp.momento_del_estado({"estado": "Nuevo"}) is None,
        "devuelve None y no cadena vacia",
        "'' en una columna de fecha revienta al guardar")

# --- autoria pegajosa --------------------------------------------------
print("\nla autoria de Dexter no se degrada sola")

CASO_DEXTER = {**CASO, "external_created_by_type": imp.DEXTER}
c = imp.reconciliar(
    cfg, [dict(CASO_DEXTER)],
    leer_ticket=lambda t: ticket(t, creado_por=CUENTA_API),
    cuenta_api=CUENTA_API, registrados_por_dexter=set())[0]
revisar(c.despues["external_created_by_type"] == imp.DEXTER,
        "un caso ya clasificado 'dexter' sigue siendo dexter",
        "sin esto, la primera reconciliacion lo degrada: el proveedor contesta "
        "SIEMPRE con la cuenta compartida, tambien para lo nuestro")
c = imp.reconciliar(
    cfg, [{**CASO, "external_created_by_type": imp.EXTERNO_DESCONOCIDO}],
    leer_ticket=lambda t: ticket(t, creado_por="SHEILA - licencia@rapilink-sas"),
    cuenta_api=CUENTA_API, registrados_por_dexter=set())[0]
revisar(c.despues["external_created_by_type"] == imp.HUMANO_VERIFICADO,
        "pero las otras clasificaciones si se corrigen con lo que llega")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Lista vacia no importa nada, el area resuelve persona, "
      "y nada de esto escribe.")


# =============================================================================
#  11. EL RELOJ  --  se prueba en tests/test_reloj.py, contra el reloj de verdad
# =============================================================================
#
# Aca vivia una clase '_RelojDePrueba' que reimplementaba el bucle del reloj y
# cuatro comprobaciones contra esa copia, mas dos que leian
# 'nucleo/canales/api.py' buscando cadenas. Se borro entero el 10/09/2026, por
# dos motivos y los dos son lecciones caras:
#
#   1. El reloj se mudo a 'nucleo/reloj.py' (en api.py nunca corrio bajo
#      gunicorn). Las dos comprobaciones de texto quedaron mirando un archivo
#      que ya no tiene nada de esto y empezaron a FALLAR -- y nadie lo vio,
#      porque este archivo no tenia comprobacion final: corria ochocientas
#      lineas y salia en 0 pasara lo que pasara. Ahora si la tiene, al final.
#
#   2. Probar una reimplementacion del reloj no prueba el reloj. Puede quedar
#      en verde mientras el de verdad esta roto -- que es exactamente lo que
#      paso durante un mes.
#
# Lo que cubria (cada_horas=0 es no-op, un tenant roto no arrastra al otro, un
# fallo de importacion no toca los vencimientos, el sello se pone aunque el
# barrido falle) esta en 'tests/test_reloj.py', que entra por 'reloj.main' y
# corre el codigo que corre en produccion.
#
#     py -3.13 tests/test_reloj.py
#
# =============================================================================
#  12. LA FRONTERA CON DJANGO  --  el motor no lee tablas ajenas
# =============================================================================

print("\nel motor no consulta tablas de Django por SQL")

FUENTE_IO = (RAIZ / "nucleo" / "seguimiento"
             / "importacion_io.py").read_text(encoding="utf-8")

# El dry-run en produccion se cayo con 'permission denied for table
# solicitudes_solicitudservicio'. El motor corre con su propio usuario de base
# desde el incidente del 18/08/2026, en que compartia credencial con el CRM, y
# la salida no era un GRANT: habria deshecho esa separacion y atado el nucleo
# al esquema interno de otra app.
for tabla in ("solicitudes_solicitudservicio", "public.case", "public.profile",
              "from case ", "join case "):
    revisar(f"select {tabla}" not in FUENTE_IO.lower()
            and f"from {tabla}" not in FUENTE_IO.lower(),
            f"no hay SQL contra '{tabla.strip()}'",
            "esas tablas son de Django y se preguntan por /api/importacion/")

revisar("asistente.conversations" in FUENTE_IO,
        "y conversations SI se consulta directo: es del dominio del motor")
revisar("consultar_tickets_conocidos" in FUENTE_IO
        and "consultar_casos_externos" in FUENTE_IO,
        "las dos lecturas ajenas pasan por herramientas del catalogo")

# Un fallo al preguntar que ya existe es GLOBAL: sin esa respuesta se crearia
# de nuevo todo lo que ya estaba.
revisar("no se pudo consultar los tickets conocidos" in FUENTE_IO,
        "si esa consulta falla, el ciclo entero aborta",
        "seguir sin saber que existe significa volver a crearlo todo")


# =============================================================================
#  13. EL MAPEO DE ESTADOS  --  el bug que costo cuatro casos reales
# =============================================================================

print("\nun caso importado nace con el estado que le toca, no con uno fijo")

# La primera importacion real creo 28 casos y CUATRO nacieron mal: los que
# estaban 'En Progreso' en el proveedor quedaron 'New' en vez de 'Assigned',
# porque el caller mandaba "status": "New" fijo. El writer aceptaba los dos, y
# las pruebas del writer probaban el writer -- nadie probaba que el caller
# eligiera bien.
revisar(imp.estado_inicial("Nuevo") == "New",
        "'Nuevo' nace como 'New'")
revisar(imp.estado_inicial("En Progreso") == "Assigned",
        "'En Progreso' nace como 'Assigned'",
        "los tickets 91908, 91972, 91999 y 92137 nacieron 'New' por este bug")
revisar(imp.estado_inicial("EN  progreso") == "Assigned",
        "y el mapeo normaliza igual que el resto del filtro")

revisar(imp.estado_inicial("Cerrado") is None,
        "'Cerrado' NO tiene mapeo, a proposito",
        "segunda capa: si alguien lo agregara a estados_descubrimiento, "
        "tampoco entraria")
revisar(imp.estado_inicial("Reabierto") is None and imp.estado_inicial("") is None,
        "un estado desconocido tampoco tiene mapeo")

# Y lo que importa: sin mapeo NO se importa, en vez de caer a un valor por
# defecto que repetiria el error cada hora en silencio.
raro = config_piloto(estados_descubrimiento=["Nuevo", "Cerrado", "Reabierto"])
vs = descubrir(raro, [ticket(200, estado="Cerrado"),
                      ticket(201, estado="Reabierto"),
                      ticket(202, estado="Nuevo")])
revisar(resultados(vs) == [imp.ESTADO_SIN_MAPEO, imp.ESTADO_SIN_MAPEO,
                           imp.CANDIDATO],
        "un estado permitido pero sin mapeo se descarta con motivo propio",
        "fail-closed: 'no se como crearlo' no puede significar 'crealo igual'")

# El cuerpo que se le manda al CRM lleva ese estado, no uno fijo.
FUENTE_IO_2 = (RAIZ / "nucleo" / "seguimiento"
               / "importacion_io.py").read_text(encoding="utf-8")
revisar('"status": imp.estado_inicial(' in FUENTE_IO_2,
        "el cuerpo que va al writer usa el mapeo, no una constante")
revisar('"status": "New",' not in FUENTE_IO_2,
        "y ya no queda ningun 'New' fijo en el cuerpo")


# =============================================================================
#  14. EL FOOTER DEL CLI  --  no puede decir lo contrario de lo que paso
# =============================================================================

print("\nel CLI no afirma que no creo nada despues de crear casos")

FUENTE_CLI = (RAIZ / "cli" / "importar_tickets.py").read_text(encoding="utf-8")
cola = FUENTE_CLI.split("Importacion aplicada en Dexter")
revisar(len(cola) == 2, "el cierre distingue apply de dry-run")
# La frase de dry-run tiene que estar en la rama 'else', nunca suelta.
# La frase de dry-run tiene que estar DENTRO del else, no suelta: se comprueba
# sobre las lineas anteriores, no sobre el texto crudo.
_lineas = FUENTE_CLI.splitlines()
_i = next(n for n, l in enumerate(_lineas)
          if "No se creo ni actualizo ningun caso" in l)
revisar(any(l.strip() == "else:" for l in _lineas[max(0, _i - 3):_i]),
        "'no se creo ningun caso' vive dentro del else del apply",
        "la primera importacion real creo 28 casos y el CLI cerro diciendo "
        "que no habia creado ninguno")
revisar("_resultado['creados']" in FUENTE_CLI,
        "y el cierre del apply informa los numeros reales")


# =============================================================================
#  15. LA CREDENCIAL DE LA IMPORTACION  --  separada del resto del CRM
# =============================================================================

print("\nla importacion no usa la credencial general del CRM")

from nucleo.config.schema import cargar_config as _cargar  # noqa: E402

_CFG = _cargar(RAIZ / "tenants" / "rapilink.config.yaml")
_por_nombre = {h.nombre: h for h in _CFG.herramientas}

# Medido: 'BOTTLECRM_API_TOKEN' lo comparten doce herramientas de cuatro
# dominios, y la union de lo que necesitan incluye 'cases:write'. Con esa
# credencial, comprometer el importador daria capacidad sobre CUALQUIER caso
# del CRM -- justo lo que el recurso separado vino a evitar.
for nombre in ("consultar_tickets_conocidos", "consultar_casos_externos",
               "importar_caso_externo", "reconciliar_caso_externo"):
    h = _por_nombre[nombre]
    revisar(h.auth_ref == "IMPORTACION_API_TOKEN",
            f"'{nombre}' usa la credencial dedicada",
            f"usa {h.auth_ref!r}: le daria permisos sobre cases, solicitudes y tags")
    revisar("/importacion/" in (h.endpoint or ""),
            f"'{nombre}' vive bajo el recurso /importacion/",
            "el alcance de un token se calcula con el primer segmento tras /api/")

# Las de WispHub NO cambian: no hablan con el CRM.
for nombre in ("listar_tickets_recientes", "consultar_ticket_por_id"):
    revisar(_por_nombre[nombre].auth_ref == "WISPHUB_API_KEY",
            f"'{nombre}' sigue con la credencial de WispHub")

# Y ninguna de las cuatro esta al alcance del modelo.
for nombre in ("consultar_tickets_conocidos", "consultar_casos_externos",
               "importar_caso_externo", "reconciliar_caso_externo"):
    expuesta = [r for r, rol in _CFG.roles.items()
                if nombre in (rol.puede_consultar or [])]
    revisar(not expuesta, f"'{nombre}' no esta en el catalogo de ningun rol",
            f"expuesta a {expuesta}")

# El secreto no puede estar en el repo: la config guarda el NOMBRE.
revisar("IMPORTACION_API_TOKEN:" not in
        (RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"),
        "el YAML declara el nombre del secreto, nunca su valor")


# =============================================================================
#  EL SELLO DE LECTURA NO ES UN CAMBIO
# =============================================================================
# 'external_fetched_at' se refresca en cada lectura aunque el proveedor
# conteste lo mismo. Contarlo como diferencia hacia que la respuesta fuera
# siempre "todos": el primer dry-run del ciclo cableado informo 34 de 34, un
# numero que no distinguia nada. Los que cambiaban algo de verdad eran 16.

print("\nel sello de lectura no cuenta como diferencia")

_solo_sello = imp.Cambio(
    caso_id="c1", external_ticket_id="1",
    antes={"external_status": "Nuevo"},
    despues={"external_status": "Nuevo",
             imp.SELLO_DE_LECTURA: "2026-09-10T20:00:00+00:00"})
revisar(_solo_sello.hay_diferencia is False,
        "un caso donde solo cambia el sello NO cuenta como diferencia",
        "si contara, el contador diria siempre 'todos' y no informaria nada")

_de_verdad = imp.Cambio(
    caso_id="c2", external_ticket_id="2",
    antes={"external_status": "Nuevo"},
    despues={"external_status": "Cerrado",
             imp.SELLO_DE_LECTURA: "2026-09-10T20:00:00+00:00"})
revisar(_de_verdad.hay_diferencia is True,
        "y uno que cambia de estado si")

revisar(imp.SELLO_DE_LECTURA == "external_fetched_at",
        "el sello se nombra una sola vez y los dos consumidores lo leen de ahi",
        "el CLI lo tenia escrito a mano: dos lugares para el mismo concepto")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)


# =============================================================================
#  LO QUE EL CASO SE LLEVA DEL TICKET  (10/09/2026)
# =============================================================================
# Salio de mirar la pantalla al lado de la de WispHub: el ticket decia
# "Prioridad: Alta" y el caso nacio "Normal"; la descripcion tenia "Pago
# reconexion en factura" y el caso no la tenia. El dato estaba y lo
# tirabamos.

print("\nla descripcion del ticket llega limpia al caso")

_CRUDO = ("<p>No Tiene Internet</p>\r\n\r\n<p>Pago reconexion en factura&nbsp;</p>"
          "\r\n\r\n<p>Reporta Tecnico 6&nbsp;</p>")
_LIMPIO = imp.limpiar_descripcion(_CRUDO)

revisar("<p>" not in _LIMPIO and "&nbsp;" not in _LIMPIO,
        "sin etiquetas ni entidades HTML",
        "el proveedor la entrega en HTML; pegarla cruda en el CRM seria "
        "ilegible en el mejor caso, y marcado que nadie escribio en el peor")
revisar(_LIMPIO.splitlines() == ["No Tiene Internet",
                                 "Pago reconexion en factura",
                                 "Reporta Tecnico 6"],
        "y los parrafos siguen siendo lineas separadas",
        f"quedo: {_LIMPIO!r}")
revisar(imp.limpiar_descripcion("<p>a</p><p>b</p>") == "a\nb",
        "dos parrafos pegados no se convierten en una sola palabra",
        "por eso las etiquetas de cierre se traducen a salto ANTES de borrar")
revisar(imp.limpiar_descripcion(None) == "" and imp.limpiar_descripcion("") == "",
        "sin descripcion no revienta")
revisar(len(imp.limpiar_descripcion("<p>" + "x" * 5000 + "</p>")) == imp.TOPE_DESCRIPCION,
        f"se corta en {imp.TOPE_DESCRIPCION} caracteres",
        "no es un limite tecnico: es minimizacion, porque es texto libre de un "
        "operador y puede traer datos personales que nadie pidio")


print("\nla prioridad del proveedor se guarda pero no manda")

# '_cuerpo_de' vive en el modulo de efectos, pero es puro: arma el diccionario
# que se manda y no llama a nadie. Se prueba aca, junto a lo que decide que va
# adentro.
from nucleo.seguimiento import importacion_io as io  # noqa: E402

_v = imp.Veredicto(external_ticket_id="92204", asunto="No Tiene Internet",
                   prioridad_proveedor="Alta", prioridad="Normal",
                   descripcion="Pago reconexion en factura")
_cuerpo = io._cuerpo_de(_v, _CFG)

revisar(_cuerpo["priority"] == "Normal",
        "'priority' del caso NO toma la del proveedor",
        "la prioridad del caso es de Dexter; hoy es una constante de la "
        "configuracion y manana sera un score propio")
# Sin nombrar al proveedor: en el YAML semilla viene vacio y el valor real
# ('wisphub') vive en la base, que es la fuente de verdad. Afirmar sobre el
# nombre haria fallar la prueba por donde se leyo la config, no por lo que
# hace el codigo.
revisar("Prioridad en" in _cuerpo["description"]
        and "Alta." in _cuerpo["description"],
        "pero la del proveedor queda escrita y a la vista",
        "asi nadie lee ese 'Normal' como si fuera un juicio")
revisar("Pago reconexion en factura" in _cuerpo["description"],
        "y la descripcion del ticket viaja con el caso")
revisar(_cuerpo["description"].startswith("Importado de"),
        "la referencia va primero y el texto libre despues",
        "arriba lo que este sistema sabe con certeza, abajo lo del otro lado")
