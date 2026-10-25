# -*- coding: utf-8 -*-
"""
===============================================================================
 EL SUPERVISOR ARMA LA JORNADA DEL DIA  --  17/10/2026
===============================================================================
Objetivo `SPEC/objetivos/supervisor-arma-la-jornada.md`, Fase 1. Lo pidio el
usuario despues de leer, en una ficha de Despacho, "ese dia ninguna cuadrilla
cubre SOLEDAD": la cola tenia trabajo y nadie habia armado el dia.

QUE HACE, EN CADA VUELTA
------------------------
  1. Le pone el BARRIO a los casos de Despacho que todavia no lo tienen. Es una
     llamada al motor por caso (`contexto_del_caso`, que habla con el ISP), asi
     que va con tope por vuelta y se guarda en la propuesta para no volver a
     pedirlo. Ningun dato guardado tenia el barrio de un caso de Despacho: la
     ficha lo pide cada vez que alguien la abre.
  2. Cuenta la DEMANDA: cuantos casos hay en cada zona, por labor. La zona sale
     del barrio (los alias de `campo.zonas`); la labor, del grupo de la lectura
     del reclamo, con la tabla de la empresa (`labor_de_cada_grupo`).
  3. PLANEA la jornada de hoy de cada cuadrilla con la regla de
     `campo.jornada_automatica`, la misma del ciclo de la madrugada.
  4. Si la tarea esta delegada y la empresa lo autoriza, la ARMA. Si no, deja
     en el log lo que armaria: la SOMBRA, para compararla con lo que una
     persona arma ese dia antes de encenderlo.

LAS PUERTAS, COMO EN EL PASO A DESPACHO
---------------------------------------
  - QUE ALGUIEN LO HAYA PEDIDO: la tarea `armar_la_jornada_del_dia`, propia.
    Habilitar el paso a Despacho no habilita esto de rebote.
  - QUE LA EMPRESA LO AUTORICE: `autonomia.puede(org, 3)`. No poder leerlo es
    lo mismo que no tenerlo: se queda en sombra.
  - QUE LA EMPRESA ESTE TRABAJANDO: solo un dia abierto de su calendario y
    antes de su cierre. Armar a las 20:00 la jornada de un dia que ya termino
    ensuciaria la historia que lee `informe_de_jornadas`, y en sombra igual:
    lo que no se puede armar tampoco se cuenta como "se armaria".

NO ES UNA ACCION EXTERNA
------------------------
Armar una jornada escribe filas de Cuadrillas y nada mas: no crea ordenes, no
reparte, y al tecnico no le llega nada hasta que alguien publica el reparto
(Fases 2 y 3, que van aparte y con su propia puerta).
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from operaciones import tareas_delegadas

logger = logging.getLogger(__name__)

#:  La tarea que una persona delega desde el chat del Supervisor.
TAREA = tareas_delegadas.ARMAR_LA_JORNADA

#:  El nivel que pide armar: 3 --ejecutar algo reversible-- como el paso a
#:  Despacho. SALE DEL CATALOGO, y no se copia: eran dos numeros que nada
#:  ataba, y una prueba que los compara (auditor de frontera, 17/10/2026).
NIVEL_PARA_ARMAR = tareas_delegadas.CATALOGO[TAREA]["exige_nivel"]

#:  La pieza de evidencia con el barrio del cliente.
FUENTE_LOCALIDAD = "localidad_del_cliente"

#:  Cuantos barrios se piden por vuelta. Cada uno es una llamada al motor de
#:  hasta 30 s; con la cola medida el 17/10 (22 casos) se completa en tres
#:  vueltas, y despues no se vuelve a pedir ninguno.
TOPE_LOCALIDADES_POR_VUELTA = 8

#:  Un barrio que el ISP no tiene --o un caso sin servicio-- se vuelve a pedir
#:  una vez por dia: alguien puede cargarlo en el ISP, pero no cada hora.
HORAS_PARA_RELEER_SIN_LOCALIDAD = 24

#:  Los motivos que se GUARDAN junto a un barrio vacio. Cerrado a proposito: el
#:  motivo se ve en el panel y llega desde `sin_contexto`, que hoy usa claves
#:  fijas; si mañana alguien le pasa texto, aca no entra (revisor de PII,
#:  17/10/2026).
_MOTIVOS_GUARDABLES = frozenset({
    "caso_sin_servicio", "sin_identidad_resoluble", "el_isp_no_tiene_barrio",
})

#:  El motivo de una INSTALACION NUEVA  --  18/10/2026. Su ticket cuelga del
#:  cliente de instalaciones del ISP ("INSTALACIONES NUEVAS"), y el barrio de
#:  esa ficha es el del cliente ficticio, no el de la casa a instalar: todas
#:  las instalaciones caerian en el mismo barrio. Se guarda sin barrio, con
#:  este motivo, y la pieza queda marcada 'cliente_nuevo'.
MOTIVO_INSTALACION_NUEVA = "instalacion_nueva"

#:  Los nombres de excepcion que dicen "el motor no esta": sin conexion. Con
#:  estos se deja de preguntar en la vuelta; con cualquier otro, solo se salta
#:  ese caso.
_SIN_CONEXION = frozenset({"ConnectionError", "ConnectTimeout"})

#:  Como corrio la fase.
ARMADO = "armado"
SOMBRA = "sombra"
NO_CORRIO = "no_corrio"


# =============================================================================
#  EL BARRIO DE CADA CASO
# =============================================================================

def localidad_guardada(propuesta) -> dict | None:
    """La pieza con el barrio del cliente guardada en la propuesta, o None."""
    for pieza in reversed(getattr(propuesta, "evidencia", None) or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE_LOCALIDAD:
            return pieza
    return None


def _hay_que_leer(pieza, ahora) -> bool:
    """Si este caso necesita que se le pida el barrio en esta vuelta."""
    if pieza is None:
        return True
    if "cliente_nuevo" not in pieza:
        #  UNA PIEZA DE ANTES DEL 18/10/2026: no sabe si el caso es de un
        #  cliente nuevo, y si lo es, su barrio es el del cliente ficticio. Se
        #  pide una vez mas; la nueva ya trae la marca.
        return True
    if str(pieza.get("localidad") or "").strip():
        return False
    leida = parse_datetime(str(pieza.get("observado_en") or ""))
    return (leida is None
            or ahora - leida >= timedelta(hours=HORAS_PARA_RELEER_SIN_LOCALIDAD))


def leer_localidad(caso_id) -> tuple:
    """(barrio, motivo) del cliente de un caso, preguntandole al motor.

    El barrio es None cuando NO SE PUDO PREGUNTAR --el motor no respondio--: no
    se guarda nada y se reintenta la vuelta que viene. Cadena vacia es que se
    pregunto y no hay: el caso no tiene servicio, el motor no identifico al
    cliente, o el ISP no tiene barrio. Eso se guarda, y se vuelve a pedir en
    `HORAS_PARA_RELEER_SIN_LOCALIDAD`.
    """
    from campo.services.despacho import contexto_del_caso

    try:
        contexto = contexto_del_caso(str(caso_id))
    except Exception as e:                                       # noqa: BLE001
        return None, type(e).__name__
    if not isinstance(contexto, dict):
        return None, "sin_respuesta"
    if not contexto.get("contexto_disponible"):
        if not contexto.get("motor_alcanzado"):
            #  EL MOTOR CAIDO NO ES LO MISMO QUE UN CASO QUE FALLA (auditor
            #  independiente, 17/10). `contexto_del_caso` pone el nombre de la
            #  excepcion: sin conexion, el motor no esta; un 500 o una demora
            #  de ESTE caso no dicen nada de los demas, y cortar la vuelta por
            #  eso dejaba a toda la cola sin barrio detras de un caso roto.
            crudo = str(contexto.get("motivo") or "")
            return None, ("motor_no_alcanzado" if crudo in _SIN_CONEXION
                          else "fallo_del_caso")
        motivo = str(contexto.get("motivo") or "")
        return "", (motivo if motivo in _MOTIVOS_GUARDABLES else "sin_contexto")
    #  EL CLIENTE DE INSTALACIONES DEL ISP: el mismo discriminador que usa
    #  `clasificacion_de_trabajo` (220 de 220, medido el 08/10/2026).
    servicio = str(contexto.get("servicio") or "").strip()
    ficticio = str(contexto.get("id_servicio_instalaciones") or "").strip()
    if servicio and ficticio and servicio == ficticio:
        return "", MOTIVO_INSTALACION_NUEVA
    cliente = contexto.get("cliente") or {}
    if not cliente:
        #  EL MOTOR CONTESTO SIN FICHA: se traga el error del ISP y devuelve
        #  igual la identidad. Guardarlo como "no tiene barrio" dejaba el caso
        #  afuera de la cuenta 24 horas por una caida de minutos (auditor
        #  independiente, 17/10). Se vuelve a pedir la vuelta que viene.
        return None, "sin_ficha_del_cliente"
    barrio = str(cliente.get("localidad") or "").strip()
    return barrio, ("" if barrio else "el_isp_no_tiene_barrio")


def guardar_localidad(propuesta, barrio: str, motivo: str, ahora) -> bool:
    """Deja el barrio en la propuesta, reemplazando el anterior.

    La llamada de red ya ocurrio, afuera: aca solo se bloquea la fila y se
    reescribe su evidencia. Solo si la propuesta sigue llevando el caso a
    Despacho: si alguien la revirtio en el medio, no hay a quien anotarselo.
    """
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    with transaction.atomic():
        fresca = (P.objects.select_for_update()
                  .filter(pk=propuesta.pk, estado__in=(P.ACEPTADA, P.MODIFICADA))
                  .first())
        if fresca is None:
            return False
        nuevo = motivo == MOTIVO_INSTALACION_NUEVA
        if barrio:
            dato = f"Barrio del cliente en el ISP: {barrio}."
        elif nuevo:
            dato = ("Instalacion de un cliente nuevo: el ticket cuelga del "
                    "cliente de instalaciones del ISP, que no trae el barrio "
                    "de la casa.")
        else:
            dato = "El barrio del cliente no se pudo saber."
        pieza = sup._observacion(FUENTE_LOCALIDAD, fresca.origen_id, dato, ahora)
        pieza["localidad"] = barrio
        pieza["motivo"] = motivo
        pieza["cliente_nuevo"] = nuevo
        resto = [x for x in (fresca.evidencia or [])
                 if not (isinstance(x, dict)
                         and x.get("fuente") == FUENTE_LOCALIDAD)]
        fresca.evidencia = [*resto, pieza]
        fresca.save(update_fields=["evidencia", "updated_at"])
    propuesta.evidencia = fresca.evidencia
    return True


def propuestas_en_despacho(org) -> dict:
    """{id de caso: la propuesta mas reciente que lo tiene en Despacho}.

    Los casos de la cola son los de `paso_a_despacho.casos_en_despacho`, la
    misma definicion de la pantalla. Un caso con dos propuestas aceptadas se
    cuenta una vez, con la ultima.
    """
    from operaciones import paso_a_despacho as pad

    abiertos = pad.ids_en_despacho(org)
    salida = {}
    for p in pad.propuestas_que_llevan_a_despacho(org).order_by("created_at"):
        caso = str(p.origen_id)
        if caso in abiertos:
            salida[caso] = p
    return salida


def completar_localidades(propuestas: dict, *, ahora, tope=None,
                          leer=None) -> dict:
    """Pide el barrio de los casos que no lo tienen, hasta el tope.

    'leer' SE INYECTA, como 'medir' en 'medicion_de_fallas': este modulo decide
    QUE se pide y que se guarda, no como se habla con el motor.
    """
    tope = TOPE_LOCALIDADES_POR_VUELTA if tope is None else tope
    leer = leer or leer_localidad
    reporte = {"leidas": 0, "sin_dato": 0, "no_se_pudo": 0,
               "esperan_el_tope": 0, "motor_caido": 0}
    pedidas = 0
    caido = False
    for caso, p in propuestas.items():
        if not _hay_que_leer(localidad_guardada(p), ahora):
            continue
        if caido:
            #  EL MOTOR NO RESPONDE: no se le sigue preguntando en esta vuelta
            #  (auditor de frontera, 17/10). Cada pedido son hasta 30 s, y ocho
            #  seguidos contra un motor caido eran cuatro minutos por empresa.
            reporte["motor_caido"] += 1
            continue
        if pedidas >= tope:
            reporte["esperan_el_tope"] += 1
            continue
        pedidas += 1
        barrio, motivo = leer(caso)
        if barrio is None:
            reporte["no_se_pudo"] += 1
            caido = motivo == "motor_no_alcanzado"
            continue
        try:
            if guardar_localidad(p, barrio, motivo, ahora):
                reporte["leidas" if barrio else "sin_dato"] += 1
        except Exception as e:                                   # noqa: BLE001
            #  Anotar no puede tumbar la vuelta: el barrio se vuelve a pedir.
            reporte["no_se_pudo"] += 1
            logger.warning("Supervisor: no se pudo guardar el barrio de un "
                           "caso de Despacho (%s)", type(e).__name__)
    return reporte


# =============================================================================
#  CUANTO TRABAJO HAY EN CADA ZONA
# =============================================================================

def demanda_de_despacho(org, propuestas: dict) -> dict:
    """Los casos de Despacho de cada zona, por labor, y los que no se cuentan.

        {"por_zona": {zona_id: {labor: casos}},
         "casos": n, "contados": n,
         "ya_despachados": n,  # su orden ya esta en manos de alguien, o hecha
         "sin_barrio": n,    # todavia no se sabe, o el ISP no lo tiene
         "instalaciones_sin_barrio": n,  # cliente nuevo: su ficha no lo trae
         "sin_zona": n,      # el barrio no esta mapeado a ninguna zona
         "sin_labor": n}     # su grupo no tiene labor (o no tiene lectura)

    LO YA DESPACHADO NO PIDE CUADRILLA (auditor independiente, 17/10). La cola
    de Despacho es "aceptado y no cerrado", y un caso sigue ahi con su orden
    completada o asignada: contarlo inclinaba la labor hacia trabajo hecho. No
    cuenta el caso cuya orden viva ya tiene a alguien, o ya se completo.

    LA VISITA QUE PIDIO UNA MEDICION SI CUENTA. Esos casos entran por
    `CASO_REQUIERE_VISITA`, sin lectura del reclamo y por lo tanto sin grupo, y
    quedaban todos en "sin labor". Su labor la decidio el clasificador
    medido, y viaja en la accion que escribe `supervisor.analizar`.

    Los tres que no se cuentan van aparte porque se arreglan distinto: el
    barrio llega solo en las vueltas que siguen; la zona se mapea en
    Cuadrillas; la labor se declara en la tabla de la empresa.

    EL TRABAJO PEDIDO DE UN CLIENTE NUEVO ES INSTALACION, el de uno que ya
    existe no (correccion 1 del usuario, 18/10/2026): su labor sale de la fila
    `INSTALACION_NUEVA` de la tabla. Una instalacion nueva no trae barrio --su
    ficha es la del cliente ficticio--, asi que hoy se cuenta aparte, en
    'instalaciones_sin_barrio', y no en 'sin_barrio'.

    Y ESAS INSTALACIONES SE LE CUENTAN A LAS ZONAS DE LAS CUADRILLAS DE
    INSTALACION  --  auditor independiente, 19/10/2026. Sin barrio no entraban
    en ninguna zona, y con el trabajo pedido de los clientes que ya existen
    contado como correctivo, ningun caso real pedia instalacion: la cuadrilla
    de instalacion salia con la labor de la mayoria de su zona, y las ordenes
    de instalacion quedaban sin cuadrilla en el reparto. No se sabe en que
    zona va a caer cada una, pero si que la va a hacer una cuadrilla de esa
    labor: se suman a las zonas habituales de las cuadrillas activas cuya
    labor habitual es la de la instalacion nueva. Va aparte de 'contados', que
    sigue siendo de casos con zona.
    """
    from campo.cuadrillas import (
        INSTALACION_NUEVA,
        labor_de_cada_grupo,
        onus_para_corte_de_red,
    )
    from campo.zonas import AliasDeZona, normalizar_localidad
    from operaciones import paso_a_despacho as pad
    from operaciones import ubicacion_del_caso as ub

    labores = labor_de_cada_grupo(org)
    #  Se arma una vez, como en `reparto.proponer`: preguntarlo por caso seria
    #  una consulta por fila.
    zona_de_barrio = {
        a.localidad: str(a.zona_id)
        for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
    }
    buscables = ub.preparar(zona_de_barrio)
    textos = _textos_de_los_casos(org, list(propuestas))
    despachados = _ya_despachados(org, list(propuestas))
    salida = {"por_zona": {}, "casos": len(propuestas), "contados": 0,
              "ya_despachados": 0, "sin_barrio": 0,
              "instalaciones_sin_barrio": 0, "sin_zona": 0, "sin_labor": 0,
              #  Casos de un corte de red que ya conto otro caso del mismo
              #  puerto (19/10/2026): un solo trabajo, no uno por cliente.
              "mismo_corte_de_red": 0,
              #  Obras de red cuyo ticket no nombra un barrio cargado (o
              #  nombra dos zonas): no se sabe donde son (25/10/2026).
              "obras_sin_barrio": 0}
    umbral_corte = onus_para_corte_de_red(org.id)
    #  EL CORTE DE RED SE CUENTA UNA VEZ (auditor independiente, 19/10/2026).
    #  La llave es el PUERTO, no la zona: un puerto puede alimentar dos zonas y
    #  sigue siendo un solo trabajo. Y los cortes que YA tienen su orden --que
    #  es justo lo que la marca le pide al despachador-- se juntan ANTES de
    #  recorrer: si el caso con la orden venia despues en la cola, el primero
    #  del puerto contaba una obra que ya estaba hecha.
    corte_de = {}
    for caso, p in propuestas.items():
        medicion = pad.ultima_medicion(p)
        if pad.es_corte_de_red(medicion, umbral_corte):
            corte_de[caso] = medicion["puerto"]
    cortes_contados = {corte_de[c] for c in corte_de if c in despachados}
    for caso, p in propuestas.items():
        if caso in despachados:
            salida["ya_despachados"] += 1
            continue
        corte = corte_de.get(caso)
        if corte and corte in cortes_contados:
            salida["mismo_corte_de_red"] += 1
            continue
        pieza = localidad_guardada(p) or {}
        #  EL BARRIO DE UNA OBRA DE RED LO NOMBRA EL TICKET (25/10/2026): el
        #  de la cuenta es el de la oficina. Ver `ubicacion_del_caso`.
        obra = ub.es_obra_de_red(pad._ultima_lectura_con_grupo(p) or {},
                                 es_corte=bool(corte))
        barrio, _de_donde = ub.barrio_del_caso(
            normalizar_localidad(pieza.get("localidad") or ""),
            textos.get(caso, ""), es_obra=obra, buscables=buscables)
        if not barrio:
            salida["obras_sin_barrio" if obra
                   else "instalaciones_sin_barrio" if pieza.get("cliente_nuevo")
                   else "sin_barrio"] += 1
            continue
        zona = zona_de_barrio.get(barrio)
        if zona is None:
            salida["sin_zona"] += 1
            continue
        if corte:
            #  EL CORTE DE RED ES UN SOLO TRABAJO (caso 4, 19/10/2026): el
            #  primer caso del puerto que se puede ubicar cuenta como obra de
            #  red; los demas no suman (arriba).
            cortes_contados.add(corte)
        labor = labor_del_caso(p, labores, es_corte=bool(corte))
        if not labor:
            salida["sin_labor"] += 1
            continue
        de_la_zona = salida["por_zona"].setdefault(zona, {})
        de_la_zona[labor] = de_la_zona.get(labor, 0) + 1
        salida["contados"] += 1

    labor_nueva = labores.get(INSTALACION_NUEVA)
    salida["zonas_con_instalaciones_sin_barrio"] = 0
    if salida["instalaciones_sin_barrio"] and labor_nueva:
        from campo.cuadrillas import Cuadrilla
        from campo.zonas import ZonaOperativa

        habituales = [z for z in Cuadrilla.objects
                      .filter(org=org, activa=True, labor_habitual=labor_nueva)
                      .values_list("zonas_habituales", flat=True) if z]
        zonas = {str(z) for z in ZonaOperativa.objects
                 .filter(org=org, activa=True, id__in=habituales)
                 .values_list("id", flat=True)}
        for zona in zonas:
            de_la_zona = salida["por_zona"].setdefault(zona, {})
            de_la_zona[labor_nueva] = (de_la_zona.get(labor_nueva, 0)
                                       + salida["instalaciones_sin_barrio"])
        salida["zonas_con_instalaciones_sin_barrio"] = len(zonas)
    return salida


def _textos_de_los_casos(org, casos: list) -> dict:
    """{caso: asunto y descripcion}, en una consulta. Solo para buscar ahi el
    barrio (`ubicacion_del_caso`): no se guarda ni va a ningun log."""
    from cases.models import Case

    if not casos:
        return {}
    return {str(i): f"{n or ''} {d or ''}"
            for i, n, d in Case.objects.filter(org=org, id__in=casos)
            .values_list("id", "name", "description")}


def _es_de_un_cliente_nuevo(localidad: dict, lectura: dict) -> bool:
    """Si el trabajo pedido es la instalacion de un cliente nuevo: lo marco la
    lectura del barrio, o el clasificador lo verifico por el cliente de
    instalaciones del ISP al leer el ticket. Por el texto solo, NO: el asunto
    de un trabajo pedido dice "instalacion" tambien para un punto de TV."""
    if localidad.get("cliente_nuevo"):
        return True
    return (lectura.get("labor") == "instalacion"
            and bool(lectura.get("labor_verificada")))


#:  La accion que escribe `supervisor.analizar` para una visita medida. Es un
#:  texto del CODIGO, no del modelo; `test_visita` lo ata a esa funcion para
#:  que no diverjan en silencio.
_VISITA = re.compile(r"^Despachar una visita de (correctivo|trabajos|instalacion)\b")


def labor_de_la_visita(propuesta) -> str:
    """La labor medida de una propuesta `CASO_REQUIERE_VISITA`, o ""."""
    from operaciones.models import PropuestaSupervisor as P

    if getattr(propuesta, "tipo_senal", "") != P.CASO_REQUIERE_VISITA:
        return ""
    m = _VISITA.match(str(getattr(propuesta, "accion_propuesta", "") or ""))
    return m.group(1) if m else ""


def labor_del_caso(propuesta, labores: dict, *, es_corte: bool = False):
    """La labor de un caso de Despacho: la que cuenta para armar la jornada.

    Extraida de `demanda_de_despacho` sin cambiar nada (21/10/2026, Fase 2.1
    de supervisor-arma-la-jornada): el Supervisor va a crear la orden de cada
    caso (2.3) y la labor de esa orden tiene que ser LA MISMA que inclino la
    jornada -- si no, la orden sale de una labor y la cuadrilla de otra, y el
    reparto no la empareja (el motivo de D2 de labores-propias).

    El grupo de la lectura, por la tabla de la empresa (`labores`); un
    trabajo pedido de un cliente nuevo es instalacion nueva (correccion 1
    del 18/10); un corte de red es obra de red; sin grupo, la labor medida
    de la visita. None o "" = no se sabe (quien llama lo cuenta aparte).
    """
    from campo.cuadrillas import INSTALACION_NUEVA
    from operaciones import paso_a_despacho as pad

    lectura = pad._ultima_lectura_con_grupo(propuesta) or {}
    grupo = str(lectura.get("grupo") or "")
    if grupo == pad.TRABAJO_PEDIDO and _es_de_un_cliente_nuevo(
            localidad_guardada(propuesta) or {}, lectura):
        grupo = INSTALACION_NUEVA
    if es_corte:
        grupo = pad.OBRA_DE_RED
    return labores.get(grupo) if grupo else labor_de_la_visita(propuesta)


def _ya_despachados(org, casos: list) -> set:
    """Los casos cuya orden viva ya tiene a alguien asignado, o ya se hizo."""
    from django.db.models import Exists, OuterRef

    from campo.models import AsignacionTrabajo, OrdenTrabajo

    if not casos:
        return set()
    hechas = (OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA)
    filas = (OrdenTrabajo.objects
             .filter(org=org, origen_sistema="crm", origen_ref__in=casos)
             .exclude(estado_operativo=OrdenTrabajo.CANCELADA)
             .annotate(con_alguien=Exists(
                 AsignacionTrabajo.objects.filter(orden=OuterRef("pk"))))
             .values_list("origen_ref", "estado_operativo", "con_alguien"))
    return {str(ref) for ref, estado, con_alguien in filas
            if estado in hechas or con_alguien}


# =============================================================================
#  LA FASE
# =============================================================================

def _la_empresa_trabaja(org, fecha, ahora) -> tuple:
    """(por que ahora NO se arma, aviso). Cadena vacia = se puede.

    TODO EN EL RELOJ DEL CALENDARIO  --  auditor de frontera, 17/10/2026. La
    primera version tomaba la FECHA de la empresa (`Org.timezone`) y comparaba
    la HORA en la del calendario. Con el calendario en UTC y la empresa en
    Bogota --lo que D-4 midio en produccion el 28/09-- armaba de 19:07 a 23:07
    un dia que ya habia terminado, y no corria de 12:07 a 18:07. Ahora:

      - si a esta hora el calendario ya esta en OTRO dia que la empresa, no se
        arma: no hay forma de saber que horario vale;
      - si no, el cierre se compara en el reloj del calendario, que es como lo
        lee `capacidad` ("se respeta su timezone tal como esta": si no es la
        de la operacion, se corrige editando el calendario, no aca).

    El aviso dice cuando las dos zonas difieren, aunque se pueda armar: es la
    configuracion que hay que corregir, y sin decirlo nadie la mira.
    """
    import zoneinfo

    from campo.tasks import _ahora_local
    from operaciones import capacidad

    try:
        #  EL HORARIO DE LAS CUADRILLAS, NO EL DE ATENCION AL CLIENTE
        #  (21/10/2026, pedido del usuario): sin el, no se arma solo.
        jornada = capacidad.jornada_de(org, fecha, solo_de_cuadrillas=True)
    except Exception as e:                                       # noqa: BLE001
        return (f"no se pudo leer el calendario de la empresa "
                f"({type(e).__name__})", "")
    if jornada.motivo == capacidad.SIN_HORARIO_DE_CUADRILLAS:
        return ("falta el horario de las cuadrillas (se carga en Cuadrillas): "
                "sin el, el Supervisor no arma solo", "")
    if not jornada.abierta:
        return f"la empresa no trabaja ese dia ({jornada.motivo or 'cerrada'})", ""
    del_calendario = jornada.zona_horaria or "UTC"
    try:
        zona = zoneinfo.ZoneInfo(del_calendario)
    except Exception:                                            # noqa: BLE001
        return ("el calendario de la empresa tiene una zona horaria que no se "
                "puede leer", "")
    de_la_empresa = getattr(_ahora_local(org).tzinfo, "key", "")
    if de_la_empresa and de_la_empresa != del_calendario:
        aviso = (f"el calendario esta en {del_calendario} y la empresa en "
                 f"{de_la_empresa}: revisar la zona del calendario")
    elif del_calendario == "UTC":
        #  La zona de fabrica de las dos. Puede ser la real, pero en un ISP de
        #  Colombia casi seguro no lo es, y con ella el dia corta a las 19:00.
        aviso = ("la empresa y su calendario estan en UTC: revisar si es la "
                 "zona de la operacion")
    else:
        aviso = ""
    en_el_calendario = ahora.astimezone(zona)
    if en_el_calendario.date() != fecha:
        return ("para el calendario de la empresa ya es otro dia", aviso)
    #  NO ANTES DE QUE ABRA (auditor independiente, 17/10). A las 00:07 se
    #  armaba la del dia, y una ausencia cargada esa mañana ya no sacaba al
    #  lider: una jornada armada solo se reajusta de labor. Desde la apertura,
    #  lo que se declaro temprano entra.
    if (jornada.apertura is not None
            and en_el_calendario.time() < jornada.apertura):
        return "todavia no abrio la jornada de la empresa", aviso
    if jornada.cierre is not None and en_el_calendario.time() >= jornada.cierre:
        return "ya cerro la jornada de la empresa", aviso
    return "", aviso


def armar_las_jornadas_del_dia(org, ahora=None, *, leer=None) -> dict:
    """La fase del ciclo. Nunca levanta: lo que no se pudo, se dice."""
    from campo import jornada_automatica as ja
    from campo.tasks import _ahora_local
    from operaciones import autonomia

    ahora = ahora or timezone.now()
    fecha = ahora.astimezone(_ahora_local(org).tzinfo).date()
    salida = {"modo": NO_CORRIO, "fecha": fecha.isoformat(), "porque": "",
              "aviso": "", "resultado": None, "barrios": None,
              "demanda": None}

    porque, salida["aviso"] = _la_empresa_trabaja(org, fecha, ahora)
    if porque:
        salida["porque"] = porque
        logger.info("Supervisor: jornadas del dia · no corrio · %s%s", porque,
                    f" · {salida['aviso']}" if salida["aviso"] else "")
        return {"jornadas_del_dia": salida}

    propuestas = propuestas_en_despacho(org)
    salida["barrios"] = completar_localidades(propuestas, ahora=ahora, leer=leer)
    demanda = demanda_de_despacho(org, propuestas)
    salida["demanda"] = {k: v for k, v in demanda.items() if k != "por_zona"}
    planes = ja.planear_el_dia(org, fecha, demanda=demanda["por_zona"])

    #  LAS PUERTAS. No poder comprobarlas es lo mismo que no tenerlas.
    try:
        delegada = tareas_delegadas.esta_delegada(org, TAREA)
    except Exception as e:                                       # noqa: BLE001
        delegada, porque = False, (
            f"no se pudo comprobar si la tarea esta delegada "
            f"({type(e).__name__})")
    if delegada:
        try:
            veredicto = autonomia.puede(org, NIVEL_PARA_ARMAR) or {}
        except Exception as e:                                   # noqa: BLE001
            veredicto = {"puede": False,
                         "motivo": f"no se pudo leer ({type(e).__name__})"}
        if not veredicto.get("puede"):
            #  TEXTO FIJO: el motivo del interruptor arrastra lo que una
            #  persona escribio al moverlo, y esto va a un log.
            porque = "la empresa no tiene autorizado que el Supervisor la arme"
    elif not porque:
        porque = ("nadie le delego al Supervisor que arme la jornada: se le "
                  "pide desde su chat")

    if delegada and not porque:
        salida["modo"] = ARMADO
        salida["resultado"] = ja.aplicar(org, fecha, planes, origen=TAREA)
    else:
        salida["modo"] = SOMBRA
        salida["porque"] = porque
        salida["resultado"] = ja.resumen(planes)

    r = salida["resultado"]
    b = salida["barrios"]
    d = salida["demanda"]
    #  NOMBRES DE CUADRILLA Y CONTEOS, nunca un caso ni una persona: esto va a
    #  un log, que no tiene control de acceso. Las de lider ausente se CUENTAN y
    #  no se nombran: una empresa que nombra sus cuadrillas por su lider
    #  estaria diciendo en el log quien falta hoy (revisor de PII, 17/10). Los
    #  nombres quedan en el resumen, que solo ve quien entra a la plataforma.
    logger.info(
        "Supervisor: jornadas del dia · %s · fecha=%s · armadas=%s · "
        "reajustadas=%s · ya estaban=%s · sin zona=%s · lider ausente=%s · "
        "sin gente=%s · sin base=%s · labores=%s · casos=%s · "
        "ya despachados=%s · contados=%s · "
        "sin barrio=%s · instalaciones sin barrio=%s · barrio sin zona=%s · "
        "sin labor=%s · barrios leidos=%s "
        "· sin dato=%s · no se pudo=%s · esperan el tope=%s · sin preguntar "
        "por el motor caido=%s%s",
        salida["modo"] + (f" ({porque})" if porque else ""), fecha,
        [c["cuadrilla"] for c in r["copiadas"]] + r["estrenadas"],
        r["reajustadas"], r["ya_estaban"], r["sin_zona"],
        len(r["lider_ausente"]), len(r["sin_gente"]), r["sin_base"],
        r["labores"], d["casos"], d["ya_despachados"],
        d["contados"], d["sin_barrio"], d.get("instalaciones_sin_barrio", 0),
        d["sin_zona"], d["sin_labor"],
        b["leidas"], b["sin_dato"], b["no_se_pudo"], b["esperan_el_tope"],
        b["motor_caido"], f" · {salida['aviso']}" if salida["aviso"] else "")
    return {"jornadas_del_dia": salida}


# =============================================================================
#  LA VISTA PREVIA  --  21/10/2026
# =============================================================================
#  Pedido del usuario: «¿por que no se pone que arme ahora y muestre solo para
#  yo ver y asi saber que va a funcionar? Esperar a mañana es tiempo perdido».
#  Es la sombra, puesta en la pantalla en vez de en el log: el MISMO
#  planificador (`planear_el_dia`) y la MISMA demanda que usa la fase horaria,
#  sin escribir nada.
#
#  LO QUE NO HACE, A PROPOSITO: no le pregunta al motor el barrio de los casos
#  que todavia no lo tienen. `completar_localidades` GUARDA lo que encuentra y
#  tarda hasta 30 s por caso; mirar una pantalla no puede escribir ni colgarse.
#  Esos casos se cuentan aparte, y la fase de cada hora los lee.

_QUE_HARIA = {
    ("armar", "copiada"): "Se arma con la gente de su última jornada",
    ("armar", "estrenada"): "Se arma por primera vez, solo con el líder",
    ("reajustar", "otra_labor"): "Ya está armada: le cambia la labor",
    ("dejar", "armada_por_una_persona"): "La armó una persona: no se toca",
    ("dejar", "ya_tiene_ordenes"): "Ya tiene órdenes: no se toca",
    ("dejar", "misma_labor"): "Ya está armada con la labor que corresponde",
    ("no_se_arma", "sin_zona"): "No se arma: no tiene zonas habituales",
    ("no_se_arma", "lider_ausente"): "No se arma: el líder está ausente",
    ("no_se_arma", "sin_base"): "No se arma: no tiene líder ni una jornada anterior",
    ("no_se_arma", "sin_gente"): "No se arma: no le queda gente",
}


def _barrios_sin_zona(org, propuestas: dict) -> list[dict]:
    """Los barrios de la cola que ninguna zona activa tiene: esos casos no le
    llegan a ninguna cuadrilla. Se NOMBRAN para que una persona los cargue en
    Zonas operativas -- la vista previa del 21/10 mostro 21 casos asi, y un
    numero sin nombres no dice a donde ir. Mismo criterio que
    `demanda_de_despacho`: lo ya despachado no cuenta."""
    from collections import Counter

    from campo.zonas import AliasDeZona, normalizar_localidad
    from operaciones import paso_a_despacho as pad
    from operaciones import ubicacion_del_caso as ub

    #  EL MISMO BARRIO QUE CUENTA LA DEMANDA (25/10/2026): el de una obra de
    #  red sale del ticket, y la cuenta de la oficina no se pide cargar.
    zona_de_barrio = {a.localidad: str(a.zona_id) for a in
                      AliasDeZona.objects.filter(org=org, zona__activa=True)}
    buscables = ub.preparar(zona_de_barrio)
    textos = _textos_de_los_casos(org, list(propuestas))
    from campo.cuadrillas import onus_para_corte_de_red
    umbral = onus_para_corte_de_red(org.id)
    despachados = _ya_despachados(org, list(propuestas))
    cuenta = Counter()
    for caso, p in propuestas.items():
        if caso in despachados:
            continue
        medicion = pad.ultima_medicion(p)
        barrio, _de_donde = ub.barrio_del_caso(
            normalizar_localidad((localidad_guardada(p) or {}).get("localidad") or ""),
            textos.get(caso, ""),
            es_obra=ub.es_obra_de_red(
                pad._ultima_lectura_con_grupo(p) or {},
                es_corte=pad.es_corte_de_red(medicion, umbral)),
            buscables=buscables)
        if barrio and barrio not in zona_de_barrio:
            cuenta[barrio] += 1
    return [{"barrio": b, "casos": n}
            for b, n in sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))]


def vista_previa(org, fecha) -> dict:
    """Lo que armaria el Supervisor ese dia, SIN escribir nada."""
    from campo import jornada_automatica as ja
    from campo.labores import nombres_de_labor
    from campo.zonas import ZonaOperativa
    from operaciones import capacidad

    nombres = nombres_de_labor(org)
    salida = {"fecha": fecha.isoformat(), "trabaja": False, "porque": "",
              "apertura": "", "cierre": "", "cuadrillas": [], "demanda": {},
              "por_zona": []}

    jornada = capacidad.jornada_de(org, fecha, solo_de_cuadrillas=True)
    if jornada.motivo == capacidad.SIN_HORARIO_DE_CUADRILLAS:
        salida["porque"] = ("Falta el horario de las cuadrillas: sin él, el "
                            "Supervisor no arma.")
        return salida
    if not jornada.abierta:
        salida["porque"] = {
            capacidad.FERIADO: "Ese día es feriado y no tiene horario.",
            capacidad.CERRADA: "Ese día las cuadrillas no trabajan.",
        }.get(jornada.motivo, "Ese día no se trabaja.")
        return salida
    salida["trabaja"] = True
    salida["apertura"] = jornada.apertura.strftime("%H:%M") if jornada.apertura else ""
    salida["cierre"] = jornada.cierre.strftime("%H:%M") if jornada.cierre else ""

    propuestas = propuestas_en_despacho(org)
    demanda = demanda_de_despacho(org, propuestas)
    salida["demanda"] = {k: v for k, v in demanda.items() if k != "por_zona"}
    salida["barrios_sin_zona"] = _barrios_sin_zona(org, propuestas)
    #  Por texto: la demanda guarda el id de la zona como cadena.
    zonas = {str(i): n for i, n in ZonaOperativa.objects.filter(org=org)
             .values_list("id", "nombre")}
    salida["por_zona"] = sorted(
        ({"zona": zonas.get(str(z), "?"),
          "labores": sorted(({"labor": nombres.get(l, l), "casos": n}
                             for l, n in por_labor.items()),
                            key=lambda x: -x["casos"])}
         for z, por_labor in demanda["por_zona"].items()),
        key=lambda x: x["zona"])

    for p in ja.planear_el_dia(org, fecha, demanda=demanda["por_zona"]):
        #  LA GENTE: la de la jornada si ya esta armada (el plan no la trae
        #  porque no la va a cambiar), la que se copiaria si no.
        if p.jornada is not None:
            lider = getattr(p.jornada.lider, "user", None)
            gente = [(i.persona, i.rol) for i in
                     p.jornada.integrantes.select_related("persona")]
        else:
            lider = getattr(p.lider, "user", None)
            gente = p.integrantes
        salida["cuadrillas"].append({
            "cuadrilla": p.cuadrilla.nombre,
            "accion": p.accion,
            "que_haria": _QUE_HARIA.get((p.accion, p.motivo),
                                        f"{p.accion} ({p.motivo})"),
            "labor": nombres.get(p.labor, p.labor) if p.labor else "",
            "labor_antes": (nombres.get(p.labor_antes, p.labor_antes)
                            if p.labor_antes else ""),
            "zonas": [z.nombre for z in p.zonas],
            "lider": ((getattr(lider, "name", "") or getattr(lider, "email", ""))
                      if lider else ""),
            "gente": [{"nombre": persona.nombre, "rol": rol}
                      for persona, rol in gente],
        })
    return salida
