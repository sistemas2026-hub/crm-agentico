# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CREA LAS ORDENES DE DESPACHO  --  Fase 2.3 (23/10/2026)
================================================================================

Lo que hoy hace una persona con el boton «Despachar» --elegir la plantilla, la
fecha y la prioridad, y crear la orden con los datos del cliente-- lo va a
hacer el Supervisor solo, para cada caso de la cola de Despacho (decision del
usuario del 21/10: «si ya pasaron a despacho, estan aprobados para campo»).
Ficha: SPEC/objetivos/supervisor-arma-la-jornada.md, fase 2.3.

ENTREGA 1 (este archivo, por ahora): LA REGLA Y LA VISTA PREVIA. Decide, caso
por caso, que crearia y por que no crearia, SIN escribir nada y SIN
preguntarle al motor: todo sale de lo que ya esta guardado (la lectura del
Supervisor, el barrio de la propuesta, el asunto y la creacion del ticket). La
creacion de verdad es la entrega 2, y va a usar ESTA misma regla.

LO QUE NO SE CREA, Y SE DICE POR QUE (decisiones del 21/10)
---------------------------------------------------------
    ya tiene una orden viva         la tiene alguien, o espera el reparto
    ya tuvo una orden               cerrada o cancelada: una segunda visita la
                                    decide una persona, no el Supervisor
    sin barrio                      no se sabe a donde va; el barrio llega en
                                    las vueltas que siguen o el ISP no lo tiene
    barrio sin zona                 se carga en Zonas operativas
    sin plantilla                   el motivo de `plantilla_del_caso`

LA INSTALACION NUEVA SI SE CREA aunque no tenga barrio: su ficha es la del
cliente de instalaciones del ISP, que no dice donde es la casa. Sale marcada
«llamar al cliente para ubicarlo» (decision del usuario del 21/10).

UN CORTE DE RED ES UNA SOLA ORDEN POR PUERTO: el primer caso del puerto que se
puede crear lleva la orden; los demas quedan ATADOS a ella y no generan visita.

LA PRIORIDAD LA CALCULA EL CODIGO (decision del usuario del 23/10, CLAUDE.md
§4): con plazo en la plantilla, vencida o vence hoy = alta, vence mañana =
media, despues = baja; sin plazo, por la espera: dos dias o mas = alta, uno =
media, de hoy = baja.

EL DIA LO DECIDE LA HORA DE CORTE de la empresa (Cuadrillas -> Horario): lo que
entro a Despacho antes del corte sale hoy; lo que entro despues, mañana. Sin
hora de corte, el Supervisor no crea nada.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

CREAR = "crear"
NO_SE_CREA = "no_se_crea"
ATADA = "atada"

YA_TIENE_ORDEN = "ya_tiene_orden"
YA_TUVO_ORDEN = "ya_tuvo_orden"
SIN_BARRIO_TODAVIA = "sin_barrio_todavia"
SIN_BARRIO = "sin_barrio"
BARRIO_SIN_ZONA = "barrio_sin_zona"
OBRA_SIN_BARRIO = "obra_sin_barrio"
SIN_PLANTILLA = "sin_plantilla"

_POR_QUE_NO = {
    YA_TIENE_ORDEN: "Ya tiene una orden viva.",
    YA_TUVO_ORDEN: ("Ya tuvo una orden, cerrada o cancelada: una segunda "
                    "visita la decide una persona."),
    SIN_BARRIO_TODAVIA: ("Todavía no se sabe su barrio: el Supervisor lo pide "
                         "en las vueltas que siguen."),
    SIN_BARRIO: "El ISP no tiene el barrio del cliente.",
    BARRIO_SIN_ZONA: ("Su barrio no está en ninguna zona: se carga en Zonas "
                      "operativas."),
    OBRA_SIN_BARRIO: ("Es una obra de red y el ticket no nombra un barrio "
                      "cargado en Zonas (o nombra barrios de dos zonas): "
                      "dónde es lo decide una persona."),
}

#: La prioridad de la orden, con los valores de `OrdenTrabajo.prioridad`.
ALTA, MEDIA, BAJA = "alta", "media", "baja"


def prioridad_de(creado, plazo_dias, hoy: dt.date, zona) -> str:
    """Alta, media o baja: por el plazo de la plantilla, y si no tiene, por
    la espera. Regla del usuario del 23/10/2026.

    Se cuenta en DIAS de calendario de la empresa (`zona`), desde el dia en
    que se creo el ticket. Sin fecha de creacion no hay nada que medir: media.
    """
    if creado is None:
        return MEDIA
    dia_creado = creado.astimezone(zona).date()
    if plazo_dias is not None:
        restantes = (dia_creado + dt.timedelta(days=plazo_dias) - hoy).days
        if restantes <= 0:
            return ALTA
        return MEDIA if restantes == 1 else BAJA
    espera = (hoy - dia_creado).days
    if espera >= 2:
        return ALTA
    return MEDIA if espera == 1 else BAJA


_RANGO = {BAJA: 0, MEDIA: 1, ALTA: 2}


def prioridad_del_caso(creado, *, nivel, plazo_de_la_plantilla, caido: bool,
                       hoy: dt.date, zona) -> str:
    """La prioridad de la orden de un caso, con el nivel de su asunto  --
    regla del usuario del 24/10/2026 (informe «Plazo y prioridad por asunto»,
    seccion 3), integrada el 26/10:

        arranca en la prioridad del NIVEL del asunto (H-21,
          `campo.niveles.nivel_del_asunto`);
        sube con el tiempo y nunca baja: con el plazo del nivel, vence
          mañana -> al menos media; vence hoy o vencio -> alta;
        con el equipo medido caido, alta, aunque el asunto sea Normal o
          Programable.

    SIN NIVEL (un asunto sin ubicar, o un Normal provisional del Supervisor:
    `nivel_del_asunto` devuelve None) sigue la regla del 23/10, `prioridad_de`
    con el plazo de la plantilla y, sin plazo, la espera. La caida del equipo
    vale igual: es una medicion, no depende del asunto. Sin fecha de creacion,
    la del nivel tal cual.
    """
    if caido:
        return ALTA
    if nivel is None:
        return prioridad_de(creado, plazo_de_la_plantilla, hoy, zona)
    inicial = nivel.get("prioridad")
    if creado is None:
        return inicial if inicial in _RANGO else MEDIA
    por_el_plazo = prioridad_de(creado, nivel.get("plazo_dias"), hoy, zona)
    return max((inicial, por_el_plazo), key=lambda p: _RANGO.get(p, -1))


def equipo_medido_caido(propuesta) -> bool:
    """Si la medicion MAS RECIENTE del equipo del caso lo vio caido: «equipo
    caido = alta» (24/10/2026).

    La mas reciente entre la pieza y las re-mediciones de su historial
    (`paso_a_despacho.la_medicion_vigente` con las correcciones), este o no
    delegada esa tarea: aca no se decide si el caso pasa, se lee como esta el
    equipo. Con la pieza sola, un caso que paso porque una re-medicion lo vio
    caido salia con la prioridad de su asunto, y uno que una re-medicion vio
    en linea salia alta (auditor independiente, 26/10/2026, con sonda). El
    corte de red sigue con la pieza: el historial no guarda el puerto.

    Una pieza que no midio el motor (`medido_con`) no dice nada del equipo.
    Caido por falta de energia tambien cuenta: si llego a Despacho, la energia
    se descarto o una persona decidio mandar a alguien.
    """
    from operaciones import diagnostico_optico as optico
    from operaciones import paso_a_despacho as pad

    m = pad.la_medicion_vigente(pad.ultima_medicion(propuesta),
                                correcciones=True) or {}
    return (m.get("medido_con") == pad.MEDIDO_CON
            and m.get("estado") == optico.CAIDO)


def dia_de_la_orden(entro_en, hora_de_corte, ahora, zona):
    """Para que dia sale la orden, o None si no hay hora de corte.

    Lo que entro a Despacho antes del corte de HOY sale hoy, y lo que entro
    despues, mañana. Lo que entro un dia anterior sale hoy: ya espero. Sin la
    hora en que entro (una aceptada sin `revisado_en`), hoy: es el lado que no
    la deja esperando de mas.
    """
    if hora_de_corte is None:
        return None
    hoy = ahora.astimezone(zona).date()
    if entro_en is None:
        return hoy
    entro = entro_en.astimezone(zona)
    if entro.date() < hoy or entro.time() < hora_de_corte:
        return hoy
    return hoy + dt.timedelta(days=1)


def _ordenes_por_caso(org, casos: list) -> tuple[set, set]:
    """(los casos con una orden viva, los que tuvieron una cerrada o
    cancelada). Viva = la misma regla de `ordenes_vivas_del_caso`."""
    from campo.models import OrdenTrabajo

    if not casos:
        return set(), set()
    terminadas = (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA)
    vivas, tuvieron = set(), set()
    for ref, estado in (OrdenTrabajo.objects
                        .filter(org=org, origen_sistema="crm",
                                origen_ref__in=casos)
                        .values_list("origen_ref", "estado_operativo")):
        (tuvieron if estado in terminadas else vivas).add(str(ref))
    return vivas, tuvieron


def decidir(org, ahora=None) -> dict:
    """Que crearia el Supervisor ahora, caso por caso. No escribe nada.

        {"hoy", "hora_de_corte", "porque",   # porque: por que no correria
         "crear":      [{caso, ticket, asunto, plantilla, version, por,
                         labor, prioridad, nivel, nivel_nombre,
                         equipo_caido, para, barrio, zona,
                         llamar_al_cliente, corte_de_red}],
         "no_se_crea": [{caso, ticket, asunto, motivo, detalle}],
         "atadas":     [{caso, ticket, asunto, a_caso, a_ticket}]}

    En el orden en que se crearon los tickets: el corte de red lo lleva el
    caso mas viejo del puerto que se puede crear.
    """
    from campo import niveles as N
    from campo import plantillas as P
    from campo.cuadrillas import (
        configuracion_de_reparto,
        labor_de_cada_grupo,
        onus_para_corte_de_red,
    )
    from campo.labores import nombres_de_labor
    from campo.reparto import _zona_de
    from campo.zonas import AliasDeZona, MapaDeBarrios, normalizar_localidad
    from cases.models import Case
    from operaciones import armado_de_jornadas as adj
    from operaciones import paso_a_despacho as pad
    from operaciones import ubicacion_del_caso as ub

    ahora = ahora or timezone.now()
    zona_horaria = _zona_de(org)
    hoy = ahora.astimezone(zona_horaria).date()
    corte = configuracion_de_reparto(org).hora_de_corte
    salida = {"hoy": hoy.isoformat(),
              "hora_de_corte": corte.strftime("%H:%M") if corte else "",
              "porque": ("" if corte else
                         "Falta la hora de corte (Cuadrillas → Horario de "
                         "las cuadrillas): sin ella, el Supervisor no crea "
                         "órdenes."),
              "crear": [], "no_se_crea": [], "atadas": []}

    propuestas = adj.propuestas_en_despacho(org)
    if not propuestas:
        return salida
    casos = {str(c.id): c for c in Case.objects.filter(
        org=org, id__in=list(propuestas))}
    vivas, tuvieron = _ordenes_por_caso(org, list(propuestas))
    labores = labor_de_cada_grupo(org)
    nombres = nombres_de_labor(org)
    ofrecidas = P.plantillas_que_se_ofrecen(org)
    #  El nivel del asunto de cada caso (H-21), leido una vez (26/10/2026).
    nivel_de = N.lector_de_niveles(org)
    nombre_del_nivel = {n["codigo"]: n["nombre"] for n in N.niveles_de(org)}
    #  Con o sin tilde: `MapaDeBarrios` (25/10/2026).
    zona_de_barrio = MapaDeBarrios({
        a.localidad: a.zona.nombre
        for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
        .select_related("zona")
    })
    buscables = ub.preparar(zona_de_barrio)
    umbral = onus_para_corte_de_red(org.id)
    #  El puerto de cada caso que es parte de un corte de red, y el caso que
    #  lleva la orden de cada puerto. Los que ya tienen orden viva van primero:
    #  si el caso con la orden viene despues en la cola, los otros se atan a el.
    puerto_de = {}
    for caso_id, p in propuestas.items():
        medicion = pad.ultima_medicion(p)
        if pad.es_corte_de_red(medicion, umbral):
            puerto_de[caso_id] = medicion["puerto"]
    con_orden = {puerto_de[c]: c for c in puerto_de if c in vivas}

    def _fila(caso_id, caso):
        return {"caso": caso_id,
                "ticket": (getattr(caso, "external_ticket_id", "") or "").strip(),
                "asunto": getattr(caso, "name", "") or ""}

    #  POR ANTIGUEDAD: el corte lo lleva el mas viejo, y la pantalla lee la
    #  cola en el orden en que llego.
    nunca = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    orden = sorted(propuestas, key=lambda c: (
        getattr(casos.get(c), "created_at", None) or nunca, c))
    for caso_id in orden:
        p, caso = propuestas[caso_id], casos.get(caso_id)
        if caso is None:
            continue
        fila = _fila(caso_id, caso)

        def no(motivo, detalle=""):
            salida["no_se_crea"].append({
                **fila, "motivo": motivo,
                "detalle": detalle or _POR_QUE_NO.get(motivo, "")})

        if caso_id in vivas:
            no(YA_TIENE_ORDEN)
            continue
        if caso_id in tuvieron:
            no(YA_TUVO_ORDEN)
            continue
        puerto = puerto_de.get(caso_id)
        if puerto and puerto in con_orden:
            lleva = con_orden[puerto]
            salida["atadas"].append({
                **fila, "a_caso": lleva,
                "a_ticket": (getattr(casos.get(lleva), "external_ticket_id", "")
                             or "").strip()})
            continue

        pieza = adj.localidad_guardada(p)
        lectura = pad._ultima_lectura_con_grupo(p) or {}
        nuevo = adj._es_de_un_cliente_nuevo(pieza or {}, lectura)
        #  EL BARRIO DE UNA OBRA DE RED LO NOMBRA EL TICKET (25/10/2026): el
        #  de la cuenta es el de la oficina. Ver `ubicacion_del_caso`.
        obra = ub.es_obra_de_red(lectura, es_corte=bool(puerto))
        barrio, de_donde = ub.barrio_del_caso(
            normalizar_localidad((pieza or {}).get("localidad") or ""),
            f"{caso.name or ''} {getattr(caso, 'description', '') or ''}",
            es_obra=obra, buscables=buscables)
        zona = zona_de_barrio.get(barrio) if barrio else None
        if not barrio and obra:
            no(OBRA_SIN_BARRIO)
            continue
        if not barrio and not nuevo:
            no(SIN_BARRIO_TODAVIA if pieza is None else SIN_BARRIO)
            continue
        if barrio and zona is None:
            no(BARRIO_SIN_ZONA,
               f"Su barrio ({barrio}) no está en ninguna zona: se carga en "
               "Zonas operativas.")
            continue

        labor = adj.labor_del_caso(p, labores, es_corte=bool(puerto))
        elegida = P.plantilla_del_caso(
            org, labor=labor or "", asunto=caso.name or "",
            #  Medida = la decidio una medicion del equipo, no la lectura.
            labor_medida=bool(adj.labor_de_la_visita(p)),
            ofrecidas=ofrecidas)
        version = elegida["version"]
        if version is None:
            no(SIN_PLANTILLA, elegida["detalle"])
            continue

        if puerto:
            con_orden[puerto] = caso_id
        tipo = version.work_type
        para = dia_de_la_orden(p.revisado_en, corte, ahora, zona_horaria)
        nivel = nivel_de(caso.name or "")
        caido = equipo_medido_caido(p)
        salida["crear"].append({
            **fila,
            "plantilla": tipo.nombre,
            "version": str(version.id),
            "por": elegida["por"],
            "labor": nombres.get(tipo.labor, tipo.labor),
            "prioridad": prioridad_del_caso(
                caso.created_at, nivel=nivel,
                plazo_de_la_plantilla=tipo.plazo_dias,
                caido=caido, hoy=hoy, zona=zona_horaria),
            #  De donde sale la prioridad (26/10/2026): el codigo del nivel del
            #  asunto ("" si no tiene), su nombre en la empresa, y si la
            #  medicion mas reciente vio el equipo caido.
            "nivel": (nivel or {}).get("nivel", ""),
            "nivel_nombre": nombre_del_nivel.get((nivel or {}).get("nivel"), ""),
            "equipo_caido": caido,
            "para": para.isoformat() if para else "",
            "barrio": barrio,
            "barrio_de": de_donde,
            "zona": zona or "",
            #  La instalacion nueva no trae direccion aunque el ticket nombre
            #  el barrio (y con el, la zona): igual hay que llamar al cliente.
            "llamar_al_cliente": nuevo,
            "corte_de_red": bool(puerto),
        })
    return salida


# =============================================================================
#  ENTREGA 2  --  CREARLAS DE VERDAD (24/10/2026)
# =============================================================================
#
#  La fase del ciclo. Usa ESTA regla (`decidir`) y crea con la MISMA
#  traduccion que el boton Despachar (`campo.services.despacho`): la ficha del
#  motor, `cliente_para_la_orden`, `anotar_labor_sugerida`, `crear_orden`.
#
#  LAS PUERTAS, todas fail-closed (no poder comprobarlas es no tenerlas):
#
#      la tarea `crear_las_ordenes_de_despacho`, delegada por una persona
#      el nivel 3 de la empresa (`autonomia.puede`, con su interruptor)
#      la hora de corte (sin ella `decidir` no pone dia)
#      `MOTOR_TENANT`: la ficha del cliente se le pide al tenant del motor, y
#      sin saber cual no se pide (mismo criterio que `lazo_isp` y
#      `cierre_en_isp`). Que una empresa del CRM este atada a ese tenant es la
#      decision D5 de CLAUDE.md (una instalacion por ISP), y vale para todas
#      las acciones del Supervisor, no solo para esta.
#
#  Sin alguna, la fase queda en SOMBRA: no escribe nada y dice en el log
#  cuantas crearia. Lo que crearia se ve en «Ver qué crearía el Supervisor».
#
#  UNA ORDEN POR CASO, AUNQUE CORRAN DOS VUELTAS A LA VEZ: la restriccion unica
#  de la orden excluye el origen `crm`, asi que la garantia es esta: la
#  propuesta del caso se bloquea, y bajo ese bloqueo se vuelve a preguntar si
#  el caso ya tiene una orden. La segunda vuelta espera y ve la primera.
#
#  LA FICHA SE PIDE AFUERA DE TODA TRANSACCION (CLAUDE.md §12: ninguna
#  transaccion abierta mientras se espera una operacion externa), hasta
#  `TOPE_POR_VUELTA` casos, y si el motor no contesta se deja para la vuelta
#  que viene en vez de preguntarle uno por uno.

#: Cuantas ordenes crea, como mucho, en una vuelta. Cada una le pide la ficha
#: al motor (hasta 30 s); el resto espera la vuelta siguiente, una hora.
TOPE_POR_VUELTA = 8

CREO = "creo"
SOMBRA = "sombra"
NO_CORRIO = "no_corrio"

FUENTE_ORDEN = "orden_de_despacho"
FUENTE_ATADURA = "atada_a_corte_de_red"
FUENTE_SIN_FICHA = "orden_sin_ficha"

#: Cuanto se espera para volver a pedir la ficha de un caso que el motor
#: contesto sin ella (auditoria de frontera, 24/10/2026): sin esto, los mismos
#: ocho casos viejos sin ficha ocupaban el tope de cada vuelta y los demas no
#: llegaban nunca.
HORAS_PARA_VOLVER_A_PEDIR_LA_FICHA = 6

#: Lo que dice que el MOTOR no esta, y no que a ESTE caso le falta algo: se
#: corta la vuelta. Un `ReadTimeout` tambien: son 30 s por pregunta.
_MOTOR_NO_ESTA = frozenset({"ConnectionError", "ConnectTimeout", "ReadTimeout",
                            "Timeout"})


def _tarea():
    from operaciones import tareas_delegadas as td
    return td.CREAR_LAS_ORDENES


def _puertas(org) -> str:
    """Por que NO puede crear, o "" si puede. Texto fijo: va a un log."""
    import os

    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    if not (os.environ.get("MOTOR_TENANT", "") or "").strip():
        return ("falta MOTOR_TENANT: sin saber de qué empresa es la ficha del "
                "cliente, no se pide")
    try:
        if not td.esta_delegada(org, _tarea()):
            return ("nadie le delegó al Supervisor que cree las órdenes: se le "
                    "pide desde su chat")
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo comprobar la tarea ({type(e).__name__})"
    try:
        veredicto = autonomia.puede(
            org, td.CATALOGO[_tarea()]["exige_nivel"]) or {}
    except Exception as e:                                       # noqa: BLE001
        veredicto = {"puede": False, "motivo": type(e).__name__}
    if not veredicto.get("puede"):
        #  TEXTO FIJO: el motivo del interruptor arrastra lo que una persona
        #  escribio al moverlo, y esto va a un log.
        return "la empresa no tiene autorizado que el Supervisor cree órdenes"
    return ""


def _a_las_cero(dia, zona):
    """El comienzo de ese dia en el reloj de la empresa: lo que el reparto lee
    como «programada para ese dia» (`reparto._para_otro_dia`)."""
    return dt.datetime.combine(dia, dt.time(0, 0), tzinfo=zona)


def crear_las_ordenes(org, ahora=None, *, leer=None) -> dict:
    """La fase del ciclo. Nunca levanta: lo que no se pudo, se dice."""
    from campo.reparto import _zona_de
    from campo.services.despacho import contexto_del_caso
    from operaciones import armado_de_jornadas as adj

    ahora = ahora or timezone.now()
    leer = leer or contexto_del_caso
    salida = {"modo": NO_CORRIO, "porque": "", "creadas": 0, "atadas": 0,
              "crearia": 0, "sin_ficha": 0, "sin_ficha_reciente": 0,
              "ya_tenian": 0, "esperan_el_tope": 0, "motor_caido": 0,
              "se_apago": 0, "errores": 0}

    decision = decidir(org, ahora)
    salida["crearia"] = len(decision["crear"])
    if decision["porque"]:
        salida["porque"] = "falta la hora de corte"
        return {"ordenes_de_despacho": salida}
    porque = _puertas(org)
    if porque:
        salida["modo"], salida["porque"] = SOMBRA, porque
        logger.info("Supervisor: ordenes de Despacho · sombra (%s) · crearia=%s "
                    "· no crearia=%s · atadas=%s", porque, len(decision["crear"]),
                    len(decision["no_se_crea"]), len(decision["atadas"]))
        return {"ordenes_de_despacho": salida}

    salida["modo"] = CREO
    zona = _zona_de(org)
    propuestas = adj.propuestas_en_despacho(org)
    caido = apagada = False
    preguntadas = 0
    for f in decision["crear"]:
        if caido:
            salida["motor_caido"] += 1
            continue
        if apagada:
            salida["se_apago"] += 1
            continue
        if _sin_ficha_hace_poco(propuestas.get(f["caso"]), ahora):
            salida["sin_ficha_reciente"] += 1
            continue
        #  EL TOPE CUENTA PREGUNTAS AL MOTOR, que es lo que cuesta tiempo.
        if preguntadas >= TOPE_POR_VUELTA:
            salida["esperan_el_tope"] += 1
            continue
        #  LAS PUERTAS OTRA VEZ, antes de cada una (auditoria de frontera):
        #  apagar el interruptor o quitar la tarea a mitad de vuelta la frena
        #  aca, y no despues de ocho fichas de hasta 30 s.
        if _puertas(org):
            apagada = True
            salida["se_apago"] += 1
            continue
        #  LA FICHA, AFUERA DE TODA TRANSACCION.
        preguntadas += 1
        try:
            contexto = leer(f["caso"])
        except Exception as e:                                   # noqa: BLE001
            contexto = {"motivo": type(e).__name__, "motor_alcanzado": False}
        if not (isinstance(contexto, dict) and contexto.get("contexto_disponible")):
            crudo = str((contexto or {}).get("motivo") or "")
            if not (contexto or {}).get("motor_alcanzado") and \
                    crudo in _MOTOR_NO_ESTA:
                caido = True
                salida["motor_caido"] += 1
                continue
            #  Sin ficha no se crea: la orden saldria sin con que llamar ni a
            #  donde ir. Se anota, y se vuelve a pedir en unas horas.
            salida["sin_ficha"] += 1
            try:
                _anotar_sin_ficha(propuestas.get(f["caso"]), crudo, ahora)
            except Exception as e:                               # noqa: BLE001
                logger.warning("Supervisor: no se pudo anotar un caso sin "
                               "ficha (%s)", type(e).__name__)
            continue
        try:
            r = _crear_una(org, propuestas.get(f["caso"]), f, contexto,
                           ahora=ahora, zona=zona)
        except Exception as e:                                   # noqa: BLE001
            #  Un caso roto no tumba la vuelta. Tipo y no texto: va a un log.
            salida["errores"] += 1
            logger.warning("Supervisor: no se pudo crear una orden de Despacho "
                           "(%s)", type(e).__name__)
            continue
        salida["creadas" if r == CREO else "ya_tenian"] += 1

    for fila in decision["atadas"]:
        try:
            if _atar(org, propuestas.get(fila["caso"]), fila, ahora=ahora):
                salida["atadas"] += 1
        except Exception as e:                                   # noqa: BLE001
            salida["errores"] += 1
            logger.warning("Supervisor: no se pudo atar un caso a su corte de "
                           "red (%s)", type(e).__name__)

    #  CONTEOS, nunca un caso ni un cliente: esto va a un log.
    logger.info("Supervisor: ordenes de Despacho · creadas=%s · ya tenian=%s · "
                "sin ficha=%s · sin ficha hace poco=%s · esperan el tope=%s · "
                "motor caido=%s · se apago=%s · atadas=%s · errores=%s",
                salida["creadas"], salida["ya_tenian"], salida["sin_ficha"],
                salida["sin_ficha_reciente"], salida["esperan_el_tope"],
                salida["motor_caido"], salida["se_apago"], salida["atadas"],
                salida["errores"])
    return {"ordenes_de_despacho": salida}


def _crear_una(org, propuesta, f, contexto, *, ahora, zona) -> str:
    """Crea la orden de un caso, bajo el bloqueo de su propuesta. CREO, o
    "ya_tenia" si mientras tanto alguien (una persona, otra vuelta) la creo."""
    from django.db import transaction

    from campo.models import EventoTrabajo, OrdenTrabajo, WorkTypeVersion
    from campo.services.despacho import (
        anotar_labor_sugerida,
        bloquear_el_caso,
        cliente_para_la_orden,
        crear_orden,
    )
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    if propuesta is None:
        return "ya_tenia"
    with transaction.atomic():
        #  EL CASO, CON EL MISMO BLOQUEO QUE TOMA EL BOTON DESPACHAR
        #  (`bloquear_el_caso`): sin el, una persona y el Supervisor leian a la
        #  vez "no tiene orden" y salian dos (auditoria de frontera, medido).
        bloquear_el_caso(org, f["caso"])
        fresca = (P.objects.select_for_update()
                  .filter(pk=propuesta.pk, estado__in=(P.ACEPTADA, P.MODIFICADA))
                  .first())
        if fresca is None:
            return "ya_tenia"
        #  BAJO EL BLOQUEO: si una persona la despacho o otra vuelta la creo
        #  mientras se pedia la ficha, no se crea otra. Cualquier orden del
        #  caso cuenta, tambien una cerrada o cancelada (`decidir` ya no las
        #  ofrece: aca se vuelve a mirar porque pudo cambiar).
        if OrdenTrabajo.objects.filter(org=org, origen_sistema="crm",
                                       origen_ref=f["caso"]).exists():
            return "ya_tenia"
        #  Y QUE EL CASO SIGA EN LA COLA: abierto, activo y sin fusionar (la
        #  misma regla que la pantalla). Pudo cerrarse mientras se pedia la
        #  ficha de otro.
        if not pad.casos_en_despacho(org, {f["caso"]}).exists():
            return "ya_tenia"
        version = WorkTypeVersion.objects.select_related("work_type").get(
            pk=f["version"])
        resumen = (fresca.accion_propuesta or "").strip()[:1000]
        if f["llamar_al_cliente"]:
            #  LA INSTALACION DE UN CLIENTE NUEVO (decision del 21/10): su
            #  ficha es la del cliente de instalaciones del ISP. No se copia:
            #  mandaria al tecnico a otra casa. Sale con lo que trae el ticket.
            contexto = {**contexto, "cliente": {}}
            cliente = {"nombre": "", "telefono": "", "direccion": "",
                       "detalle_acceso": "", "id_abonado": ""}
            resumen = ("Llamar al cliente para ubicarlo: es una instalación "
                       "nueva y el ISP no tiene su dirección. "
                       + resumen).strip()
        else:
            cliente = cliente_para_la_orden(contexto)
        anotar_labor_sugerida(contexto, resumen)
        para = dt.date.fromisoformat(f["para"])
        orden = crear_orden(
            org=org, profile=None, version=version, cliente=cliente,
            origen_sistema="crm", origen_tipo="case", origen_ref=f["caso"],
            programada_para=_a_las_cero(para, zona), contexto=contexto,
            despacho={"prioridad": f["prioridad"], "zona": f["barrio"],
                      "resumen": resumen})
        #  QUE LA CREO EL SUPERVISOR, Y POR QUE ASI. Sin persona: el actor es
        #  la tarea (patron de `supervisor.revisar` con `automatico=True`).
        EventoTrabajo.objects.create(
            org=org, orden=orden, tipo="creada_por_el_supervisor", profile=None,
            datos={"tarea": _tarea(), "propuesta": str(fresca.pk),
                   "plantilla_por": f["por"], "prioridad": f["prioridad"],
                   #  Por que esa prioridad (26/10/2026): el nivel del asunto
                   #  puede cambiar despues, y la orden tiene que explicarse.
                   "nivel": f["nivel"], "equipo_caido": f["equipo_caido"],
                   "para": f["para"], "corte_de_red": f["corte_de_red"]})
        pieza = sup._observacion(
            FUENTE_ORDEN, fresca.origen_id,
            f"El Supervisor creó la orden #{orden.numero}.", ahora)
        pieza["orden"] = orden.numero
        fresca.evidencia = [*(fresca.evidencia or []), pieza]
        fresca.save(update_fields=["evidencia", "updated_at"])
    return CREO


def _sin_ficha_hace_poco(propuesta, ahora) -> bool:
    """Si al caso se le pidio la ficha hace menos de
    `HORAS_PARA_VOLVER_A_PEDIR_LA_FICHA` y el motor contesto sin ella."""
    from django.utils.dateparse import parse_datetime

    for pieza in reversed(getattr(propuesta, "evidencia", None) or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE_SIN_FICHA:
            cuando = parse_datetime(str(pieza.get("observado_en") or ""))
            return (cuando is not None and ahora - cuando
                    < dt.timedelta(hours=HORAS_PARA_VOLVER_A_PEDIR_LA_FICHA))
    return False


def _anotar_sin_ficha(propuesta, motivo: str, ahora) -> None:
    """Deja en la propuesta que el motor contesto sin la ficha, reemplazando la
    anterior: es lo que `_sin_ficha_hace_poco` lee, y lo que explica despues
    por que el caso no tiene orden. El motivo es un codigo fijo del motor."""
    from django.db import transaction

    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    if propuesta is None:
        return
    with transaction.atomic():
        fresca = (P.objects.select_for_update()
                  .filter(pk=propuesta.pk, estado__in=(P.ACEPTADA, P.MODIFICADA))
                  .first())
        if fresca is None:
            return
        pieza = sup._observacion(
            FUENTE_SIN_FICHA, fresca.origen_id,
            "El motor no trajo la ficha del cliente: la orden no se creó.", ahora)
        pieza["motivo"] = (motivo or "")[:64]
        resto = [x for x in (fresca.evidencia or [])
                 if not (isinstance(x, dict) and x.get("fuente") == FUENTE_SIN_FICHA)]
        fresca.evidencia = [*resto, pieza]
        fresca.save(update_fields=["evidencia", "updated_at"])
    propuesta.evidencia = fresca.evidencia


def _atar(org, propuesta, fila, *, ahora) -> bool:
    """Deja escrito en la propuesta de un caso de un corte de red a que orden
    va atado. Solo si esa orden existe, y solo si cambia: no reescribe la
    propuesta cada hora. Cerrar en el ISP los tickets atados lo hace una
    persona (decision del 21/10: es un efecto externo)."""
    from django.db import transaction

    from campo.models import OrdenTrabajo
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    if propuesta is None:
        return False
    orden = (OrdenTrabajo.objects
             .filter(org=org, origen_sistema="crm", origen_ref=fila["a_caso"])
             .order_by("numero").values_list("numero", flat=True).first())
    if orden is None:
        return False
    with transaction.atomic():
        fresca = (P.objects.select_for_update()
                  .filter(pk=propuesta.pk, estado__in=(P.ACEPTADA, P.MODIFICADA))
                  .first())
        if fresca is None:
            return False
        previa = [x for x in (fresca.evidencia or [])
                  if isinstance(x, dict) and x.get("fuente") == FUENTE_ATADURA]
        if previa and previa[-1].get("orden") == orden:
            return False
        pieza = sup._observacion(
            FUENTE_ATADURA, fresca.origen_id,
            f"Va con la orden #{orden} del mismo corte de red "
            f"(ticket {fila['a_ticket']}): no lleva una visita propia.", ahora)
        pieza["orden"] = orden
        pieza["a_caso"] = fila["a_caso"]
        resto = [x for x in (fresca.evidencia or [])
                 if not (isinstance(x, dict) and x.get("fuente") == FUENTE_ATADURA)]
        fresca.evidencia = [*resto, pieza]
        fresca.save(update_fields=["evidencia", "updated_at"])
    return True
