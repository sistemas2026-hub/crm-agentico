# -*- coding: utf-8 -*-
"""
================================================================================
 ASISTENTES OPERATIVOS  --  paso M09-M
================================================================================

Dos asistentes, y ninguno es un sistema nuevo:

    PROGRAMACION   lee las senales de M03 y recomienda sobre el trabajo de campo
    COMPROMISOS    lee las senales de M02 y recomienda sobre lo que falta hacer

LO QUE ESTO NO ES
-----------------
No hay cola nueva, no hay entidad de recomendacion, no hay 'AssistantTask' ni
'AIRecommendation'. La propuesta sigue siendo 'PropuestaSupervisor', que ya
tiene evidencia obligatoria con CHECK en la base, deduplicacion por huella,
expiracion y revision humana. Agregar una segunda cola seria el tercer lugar
donde buscar una recomendacion.

Tampoco hay detectores nuevos ni habilidades nuevas. Un asistente es un
RECORTE de 'supervisor.detectar()' por dominio, mas la forma estructurada que
distingue cuatro cosas que hasta ahora viajaban mezcladas en un texto:

    observado      el hecho, literal, tal como quedo en la evidencia
    inferencia     lo que el analisis deduce de ese hecho
    recomendacion  lo que se propone hacer
    dato faltante  lo que NO se sabe, nombrado

LA CUARTA ES LA QUE IMPORTA
---------------------------
Un asistente que calla lo que no sabe produce una recomendacion que parece
completa. Aca 'datos_faltantes' se MIDE sobre la fila --que campo esta en
null-- y no se deduce de una plantilla. Y cuando el analisis no alcanza para
sostener una recomendacion, el resultado es DATOS_INSUFICIENTES y NO se crea
ninguna propuesta: una propuesta sin base es peor que ninguna.

QUE HABILIDAD SUSTENTA CADA RECOMENDACION
-----------------------------------------
Cada recomendacion viaja con la ficha que la explica Y CON SU ESTADO. Importa
porque no todas estan vigentes: H-05 esta BLOQUEADA desde M09-J y su detector
sigue corriendo. Callar eso dejaria al Jefe de Operaciones sin saber que una
de las recomendaciones que lee se apoya en una habilidad que el propio sistema
declaro no confiable todavia.

LEE -> ANALIZA -> PROPONE. NO EJECUTA.
--------------------------------------
Este modulo no importa ni un solo servicio de escritura operativa: ni
'programacion', ni 'actividades', ni 'despacho'. No puede programar, asignar,
cerrar ni cancelar aunque quisiera -- no tiene con que. El interruptor de
autonomia vive en el motor y aca no hace falta consultarlo: no hay nada que
apagar.
================================================================================
"""

from __future__ import annotations

from django.db import transaction

from common.models import Org
from operaciones import habilidades, incidencias, sla, supervisor
from operaciones.models import (ActividadOperativa, APROBADO,
                                ESTADOS_VALIDACION, ProgramacionOrden,
                                ProgramacionSemanal, PropuestaSupervisor,
                                VALIDACION_PENDIENTE)

P = PropuestaSupervisor

PROGRAMACION = "programacion"
COMPROMISOS = "compromiso"

#  El reparto es por DOMINIO DE DATOS, no por gusto: cada senal la produce un
#  detector que lee una fuente concreta. 'caso_abierto_antiguo' no esta en
#  ninguno de los dos -- es del dominio de Casos, y este paso no lo cubre.
SENALES = {
    PROGRAMACION: (
        P.ORDEN_SIN_PROGRAMAR,
        P.PROGRAMACION_SIN_PUBLICAR,
        P.ORDEN_EN_RIESGO,
        P.DATO_INCOMPLETO,
        #  M04-A. Riesgo TEMPORAL de la orden. El calculo no vive aqui: lo
        #  hace 'operaciones/sla.py', la misma fuente que alimenta el campo
        #  'sla' de cada recomendacion. Una segunda copia de la formula seria
        #  el modo de que el detector y el asistente dijeran cosas distintas.
        P.ORDEN_SLA_VENCIDO,
        P.ORDEN_SLA_POR_VENCER,
        #  M05-A. Incidencia con lifecycle persistente.
        P.INCIDENCIA_SIN_RESOLVER,
    ),
    COMPROMISOS: (
        P.ACTIVIDAD_VENCIDA,
        P.ACTIVIDAD_SIN_RESPONSABLE,
        P.ACTIVIDAD_BLOQUEADA,
        P.COMPROMISO_POR_VENCER,
        P.DEPENDENCIA_PENDIENTE,
        #  M05-B. Es del dominio de la actividad, no del plan.
        P.ESCALAMIENTO_SIN_DESTINATARIO,
    ),
}

DATOS_INSUFICIENTES = "DATOS_INSUFICIENTES"
PROPUESTA = "propuesta"
REPETIDA = "repetida"


class ErrorAsistente(Exception):
    """El asistente no puede trabajar con lo que se le pidio."""


# ==============================================================================
#  DATOS FALTANTES  --  medidos sobre la fila, no deducidos de una plantilla
# ==============================================================================

def _faltantes_de_actividad(actividad) -> list[dict]:
    """Que NO se sabe de esta actividad. Se mira el campo, no el tipo de senal."""
    faltan = []
    if actividad.responsable_id is None:
        faltan.append({"entidad": "actividad", "campo": "responsable",
                       "por_que": "nadie figura como responsable"})
    if actividad.vence_en is None:
        faltan.append({"entidad": "actividad", "campo": "vence_en",
                       "por_que": "no hay fecha comprometida declarada"})
    if actividad.estado_operativo == ActividadOperativa.BLOQUEADA \
            and not actividad.motivo_bloqueo:
        #  La base lo impide con un CHECK; si aparece, es un dato viejo.
        faltan.append({"entidad": "actividad", "campo": "motivo_bloqueo",
                       "por_que": "bloqueada sin causa registrada"})
    if actividad.estado_validacion == VALIDACION_PENDIENTE:
        faltan.append({"entidad": "actividad", "campo": "estado_validacion",
                       "por_que": "completada pero nadie resolvio su validacion"})
    #  M05-B. Escalada y sin constar a quien: el dato falta, y se nombra. NO se
    #  propone un destinatario -- no hay politica que permita elegirlo.
    if actividad.estado_operativo == ActividadOperativa.ESCALADA:
        if actividad.escalado_a_id is None:
            faltan.append({"entidad": "actividad", "campo": "escalado_a",
                           "por_que": "escalada sin constar a quien"})
        if not actividad.nivel_escalamiento:
            faltan.append({"entidad": "actividad", "campo": "nivel_escalamiento",
                           "por_que": "escalada sin constar con que nivel"})
    return faltan


def _faltantes_de_orden(orden) -> list[dict]:
    faltan = []
    if orden.programada_para is None:
        faltan.append({"entidad": "orden_trabajo", "campo": "programada_para",
                       "por_que": "la orden no tiene fecha vigente"})
    if not orden.asignaciones.exists():
        faltan.append({"entidad": "orden_trabajo", "campo": "asignaciones",
                       "por_que": "no hay nadie en la cuadrilla"})
    esquema = getattr(orden.tipo_trabajo_version, "esquema", None) or {}
    if not isinstance(esquema.get("duracion_estimada_minutos"), int):
        faltan.append({"entidad": "tipo_trabajo", "campo": "duracion_estimada_minutos",
                       "por_que": "sin duracion no hay capacidad calculable"})
    return faltan


def _datos_faltantes(senal) -> list[dict]:
    """
    Lo que falta, LEIDO de la fila que origino la senal. Si la fila ya no
    existe se dice, en vez de devolver una lista vacia que pareceria "no falta
    nada".
    """
    d = senal.datos or {}

    #  La senal de capacidad ya trae los numeros concretos que le faltan.
    if d.get("numeros_sin_duracion"):
        return [{"entidad": "tipo_trabajo", "campo": "duracion_estimada_minutos",
                 "por_que": f"sin duracion en las ordenes "
                            f"{', '.join('#' + str(n) for n in d['numeros_sin_duracion'])}"}]
    if senal.origen_tipo == "actividad":
        a = ActividadOperativa.objects.filter(pk=senal.origen_id).first()
        if a is None:
            return [{"entidad": "actividad", "campo": "*",
                     "por_que": "la actividad ya no existe"}]
        return _faltantes_de_actividad(a)
    if senal.origen_tipo == "orden_trabajo":
        from campo.models import OrdenTrabajo
        o = (OrdenTrabajo.objects.filter(pk=senal.origen_id)
             .select_related("tipo_trabajo_version").first())
        if o is None:
            return [{"entidad": "orden_trabajo", "campo": "*",
                     "por_que": "la orden ya no existe"}]
        return _faltantes_de_orden(o)
    if senal.origen_tipo == "novedad":
        #  La ficha de la incidencia ya los midio sobre la fila; no se
        #  recalculan aqui para que no puedan divergir.
        from operaciones.models import NovedadOperativa
        n = NovedadOperativa.objects.filter(pk=senal.origen_id).first()
        if n is None:
            return [{"entidad": "novedad", "campo": "*",
                     "por_que": "la incidencia ya no existe"}]
        return incidencias.ficha(n)["datos_faltantes"]
    if senal.origen_tipo == "programacion_semanal":
        return []
    return []


def _dependencias_de(senal) -> list[dict]:
    """Solo para compromisos: de que esta esperando esta actividad."""
    if senal.origen_tipo != "actividad":
        return []
    a = (ActividadOperativa.objects.filter(pk=senal.origen_id)
         .select_related("depende_de").first())
    if a is None or a.depende_de_id is None:
        return []
    previa = a.depende_de
    #  'resuelta' es del EJE OPERATIVO y se deja como estaba: contesta si la
    #  previa dejo de avanzar. Lo que se agrega al lado es el otro eje, porque
    #  aca es donde "ejecutado" y "validado" se confunden de verdad: una
    #  dependencia COMPLETADA pero con validacion pendiente figura resuelta, y
    #  todavia puede volver con 'requiere_correccion'. Quien lea la
    #  recomendacion tiene que poder ver las dos cosas.
    ejecutada = previa.estado_operativo == ActividadOperativa.COMPLETADA
    validada = previa.estado_validacion == APROBADO
    return [{"actividad": str(previa.id), "titulo": previa.titulo,
             "estado_operativo": previa.estado_operativo,
             "resuelta": previa.estado_operativo in ActividadOperativa.ESTADOS_FINALES,
             "estado_validacion": previa.estado_validacion,
             "validada": validada,
             "ejecutada_sin_validar": ejecutada and not validada}]


#  Las etiquetas se leen del propio modelo. Escribirlas aca otra vez seria un
#  segundo catalogo que se desincroniza en silencio el dia que alguien agregue
#  un estado.
_ETIQUETA_OPERATIVA = dict(ActividadOperativa.ESTADOS_OPERATIVOS)
_ETIQUETA_VALIDACION = dict(ESTADOS_VALIDACION)


def _estado_de(senal) -> dict | None:
    """
    Los DOS ejes de una actividad, separados y nombrados.

    NO son ocho estados en una lista, y no es un detalle de presentacion:
    'models.py' lo deja escrito donde los declara -- "completada" y "falta
    validarla" son dos ejes a la vez, y aplanarlos obliga a elegir uno,
    perdiendo el caso real de "completada + requiere correccion" que produce
    una devolucion.

    Por eso 'ejecutada' y 'validada' se contestan POR SEPARADO: son la
    confusion que este asistente existe para no cometer. Una actividad
    ejecutada y sin validar no esta terminada, y una recomendacion que las
    junte estaria diciendo algo que nadie midio.
    """
    if senal.origen_tipo != "actividad":
        return None
    a = (ActividadOperativa.objects
         .filter(pk=senal.origen_id)
         .only("estado_operativo", "estado_validacion", "motivo_bloqueo",
               "escalado_a", "escalado_en", "nivel_escalamiento")
         .first())
    if a is None:
        #  La fila ya no esta. Se dice, en vez de devolver None, que se leeria
        #  como "esta senal no tiene estado".
        return {"operativo": None, "operativo_etiqueta": "",
                "validacion": None, "validacion_etiqueta": "",
                "es_final": None, "ejecutada": None, "validada": None,
                "validacion_pendiente": None, "escalamiento": None,
                "nota": "la actividad ya no existe"}
    return {
        "operativo": a.estado_operativo,
        "operativo_etiqueta": _ETIQUETA_OPERATIVA.get(a.estado_operativo, ""),
        "validacion": a.estado_validacion,
        "validacion_etiqueta": _ETIQUETA_VALIDACION.get(a.estado_validacion, ""),
        #  'final' es del eje operativo y NO significa validada.
        "es_final": a.estado_operativo in ActividadOperativa.ESTADOS_FINALES,
        "ejecutada": a.estado_operativo == ActividadOperativa.COMPLETADA,
        #  M05-B. Quien recibio el escalamiento, cuando y con que nivel. None
        #  cuando no se escalo -- no se rellena con un destinatario inventado.
        "escalamiento": ({"escalado_a": str(a.escalado_a_id),
                          "escalado_en": a.escalado_en.isoformat() if a.escalado_en else None,
                          "nivel": a.nivel_escalamiento or None}
                         if a.estado_operativo == ActividadOperativa.ESCALADA
                         or a.escalado_a_id else None),
        "validada": a.estado_validacion == APROBADO,
        "validacion_pendiente": a.estado_validacion == VALIDACION_PENDIENTE,
        #  Una bloqueada sin causa no es lo mismo que una no realizada: la
        #  causa es lo que distingue "no se pudo, por esto" de "no se hizo".
        "motivo_bloqueo": a.motivo_bloqueo or "",
    }


def _contexto_operativo(senal, ahora=None) -> dict:
    """
    El plan vigente de una orden: jornada, secuencia y novedades registradas.

    Todo LEIDO de lo que ya existe. La secuencia no se recalcula y la
    prioridad no se reinterpreta: si el plan dice 3, aqui dice 3. Un asistente
    que recalcula el plan mientras lo describe deja de poder usarse para
    contrastarlo.
    """
    if senal.origen_tipo != "orden_trabajo":
        return {}
    salida: dict = {}
    linea = (ProgramacionOrden.objects
             .filter(orden_id=senal.origen_id)
             .exclude(estado=ProgramacionOrden.CANCELADA)
             .select_related("programacion")
             .order_by("-dia", "-created_at")
             .first())
    if linea is not None:
        salida["programacion"] = {
            "semana": str(linea.programacion.semana_inicio),
            "plan_estado": linea.programacion.estado,
            "plan_publicado": (linea.programacion.estado
                               != ProgramacionSemanal.BORRADOR),
            "dia": str(linea.dia),
            "secuencia": linea.secuencia,
            "prioridad": linea.prioridad,
            "estado_linea": linea.estado,
        }
    #  Las novedades son el registro de por que algo no salio como estaba
    #  planeado. Sin ellas, "la orden sigue sin ejecutarse" se lee como
    #  desidia cuando puede ser una ausencia o una falta de material ya
    #  reportada por alguien.
    #
    #  M05-A: cada una viaja con su estado DERIVADO -- si la causa sigue
    #  vigente o no. Una novedad de hace tres semanas cuya actividad ya se
    #  desbloqueo no es lo mismo que una que sigue pasando, y la lista plana
    #  las mostraba igual.
    #  M05-A: cada una con su LIFECYCLE PERSISTENTE (abierta / en gestion /
    #  resuelta), no con un estado deducido de la actividad.
    novedades = incidencias.de_orden(senal.origen_id, ahora)
    if novedades:
        salida["novedades"] = novedades
        salida["incidencias"] = incidencias.resumen(novedades)
    return salida


def _incidencias_de(senal, ahora) -> list[dict]:
    """Las novedades de la actividad de esta senal, con su estado derivado."""
    if senal.origen_tipo != "actividad":
        return []
    return incidencias.de_actividad(senal.origen_id, ahora)


def _sla_de_senal(senal, ahora) -> dict | None:
    """
    El plazo de la orden a la que pertenece esta senal, si pertenece a alguna.

    A-1 lo resuelve directo: sus senales SON de ordenes.

    A-2 llega por el vinculo que ya existe en M02 -- 'origen_tipo' /
    'origen_id' de la actividad. Es un vinculo por CONVENCION y no una clave
    foranea (una actividad puede nacer de un caso, de una conversacion o a
    mano), asi que puede apuntar a una orden que ya no esta: por eso se
    resuelve leyendo, y si no hay orden se devuelve None en vez de inventar un
    plazo.
    """
    if senal.origen_tipo == "orden_trabajo":
        return _sla_de_orden(senal.origen_id, ahora)
    if senal.origen_tipo == "actividad":
        a = (ActividadOperativa.objects.filter(pk=senal.origen_id)
             .only("origen_tipo", "origen_id").first())
        if a is not None and a.origen_tipo == "orden_trabajo":
            return _sla_de_orden(a.origen_id, ahora)
    return None


def _sla_de_orden(orden_id, ahora) -> dict | None:
    """
    El plazo operativo de una orden (M04-A). Derivado en el momento, nunca
    leido de una columna: no existe tal columna, y esa es la decision.
    """
    if not orden_id:
        return None
    from campo.models import OrdenTrabajo
    o = (OrdenTrabajo.objects.filter(pk=orden_id)
         .select_related("tipo_trabajo_version").first())
    if o is None:
        return None
    plazo = sla.plazo_de(o, ahora)
    plazo["explicacion"] = sla.resumen(plazo)
    return plazo


def _ficha_de(tipo_senal) -> dict:
    """
    La habilidad que sustenta la recomendacion, CON SU ESTADO.

    Se declara el estado y no solo el id: H-05 esta BLOQUEADA y su detector
    sigue corriendo, asi que hay recomendaciones vivas que se apoyan en una
    ficha que el propio sistema marco como no confiable. Ocultarlo seria
    presentar como firme algo que no lo es.
    """
    id_h = habilidades.POR_SENAL.get(tipo_senal)
    if not id_h:
        return {"id": None, "estado": None, "referencia": ""}
    h = habilidades.HABILIDADES[id_h]
    return {"id": h.id, "nombre": h.nombre, "estado": h.estado,
            "referencia": habilidades.referencia_de(tipo_senal)}


def _riesgos(senal, analisis, ficha) -> list[str]:
    """
    Los riesgos DECLARADOS, no inventados: el impacto que el analisis ya
    razona, mas los que se pueden leer del estado del sistema.
    """
    salida = []
    if analisis.get("impacto"):
        salida.append(analisis["impacto"])
    if ficha.get("estado") == habilidades.BLOQUEADA:
        salida.append(
            f"La habilidad que sustenta esta senal ({ficha['id']}) esta "
            f"BLOQUEADA: su recomendacion todavia no es plenamente defendible.")
    if (senal.datos or {}).get("es_cota_inferior"):
        salida.append("La carga conocida es una cota inferior: el exceso real "
                      "puede ser mayor, nunca menor.")
    return salida


# ==============================================================================
#  EL ASISTENTE
# ==============================================================================

def _recomendacion(senal, analisis, ficha, resultado, propuesta=None, ahora=None):
    """
    La forma estructurada. Separa las cuatro cosas que hasta ahora viajaban
    mezcladas en un parrafo.
    """
    faltantes = _datos_faltantes(senal)
    fila = {
        "tipo": None,                     # lo pone 'asistir'
        "senal_origen": senal.tipo,
        "origen_tipo": senal.origen_tipo,
        "origen_id": senal.origen_id,
        #  OBSERVADO: los hechos, literales, tal como quedaron en la evidencia.
        "hallazgo": (senal.evidencia[0]["dato"] if senal.evidencia else ""),
        "observado": [o.get("dato", "") for o in senal.evidencia],
        "evidencia": senal.evidencia,
        #  INFERENCIA y RECOMENDACION: lo que el analisis deduce y propone.
        "inferencia": analisis.get("motivo", "") if analisis else "",
        "recomendacion": analisis.get("accion_propuesta", "") if analisis else "",
        "prioridad": analisis.get("prioridad") if analisis else None,
        #  DATO FALTANTE: lo que NO se sabe, nombrado.
        "datos_faltantes": faltantes,
        #  ESTADO: los dos ejes de la actividad, sin aplanar. None cuando la
        #  senal no nace de una actividad -- una orden no tiene estos ejes, y
        #  devolver un estado vacio ahi seria inventar una forma comun.
        "estado": _estado_de(senal),
        #  CONTEXTO: el plan vigente de la orden, leido tal cual.
        "contexto": _contexto_operativo(senal, ahora),
        #  INCIDENCIAS (M05-A): las novedades de ESTA actividad con su estado
        #  derivado. Es lo que separa "bloqueada" de "bloqueada por esto, y
        #  eso sigue pasando".
        "incidencias": _incidencias_de(senal, ahora),
        #  SLA OPERATIVO (M04-A): derivado en el momento, nunca leido de
        #  una columna. None cuando la senal no cuelga de ninguna orden.
        "sla": _sla_de_senal(senal, ahora),
        "riesgos": _riesgos(senal, analisis or {}, ficha),
        "dependencias": _dependencias_de(senal),
        "habilidad": ficha,
        "requiere_revision_humana": True,
        "resultado": resultado,
        "propuesta_id": str(propuesta.id) if propuesta else None,
    }
    if resultado == DATOS_INSUFICIENTES:
        #  Sin analisis no hay recomendacion, y se dice: no se rellena con una
        #  frase generica que pareceria un consejo.
        fila["recomendacion"] = ""
        fila["inferencia"] = ""
    return fila


def _por_estado(recomendaciones) -> dict:
    """Cuantas recomendaciones hay por estado operativo. Solo lo observado."""
    reparto: dict[str, int] = {}
    for r in recomendaciones:
        estado = (r["estado"] or {}).get("operativo")
        if estado:
            reparto[estado] = reparto.get(estado, 0) + 1
    return reparto


def asistir(org, dominio: str, ahora=None, registrar: bool = True) -> dict:
    """
    Una pasada del asistente. LEE, ANALIZA y PROPONE. No ejecuta nada.

    'registrar=False' lo deja en lectura pura: util para mirar sin escribir.

    SE SERIALIZA POR ORGANIZACION igual que el ciclo de M09-L, y por la misma
    razon medida alli: la deduplicacion es leer y despues escribir, y entre las
    dos cosas cabe otra pasada entera. Se bloquea la fila de la organizacion,
    que ya existe -- no hay mecanismo nuevo.
    """
    if dominio not in SENALES:
        raise ErrorAsistente(
            f"'{dominio}' no es un asistente. Hay dos: "
            f"{', '.join(sorted(SENALES))}.")

    from django.utils import timezone
    ahora = ahora or timezone.now()

    with transaction.atomic():
        Org.objects.select_for_update().get(pk=org.pk)
        return _asistir(org, dominio, ahora, registrar)


def _asistir(org, dominio, ahora, registrar) -> dict:
    tipos = set(SENALES[dominio])
    recomendaciones = []
    conteo = {PROPUESTA: 0, REPETIDA: 0, DATOS_INSUFICIENTES: 0}

    for senal in supervisor.detectar(org, ahora):
        if senal.tipo not in tipos:
            continue

        ficha = _ficha_de(senal.tipo)
        analisis = supervisor.analizar(senal)

        if not analisis:
            #  El Supervisor no sabe interpretar esta senal. NO se inventa una
            #  recomendacion ni se crea propuesta: se declara lo que falta.
            conteo[DATOS_INSUFICIENTES] += 1
            recomendaciones.append(
                _recomendacion(senal, None, ficha, DATOS_INSUFICIENTES, ahora=ahora))
            continue

        if supervisor._ya_propuesta(org, senal):
            #  El hecho sigue ocurriendo; lo que no se repite es la pregunta.
            conteo[REPETIDA] += 1
            recomendaciones.append(
                _recomendacion(senal, analisis, ficha, REPETIDA, ahora=ahora))
            continue

        propuesta = None
        if registrar:
            #  Se usa el registrador existente: exige evidencia, calcula la
            #  huella, fija la expiracion y audita. No hay un camino propio.
            propuesta = supervisor.registrar_propuesta(org, senal, analisis, ahora)
        conteo[PROPUESTA] += 1
        recomendaciones.append(
            _recomendacion(senal, analisis, ficha, PROPUESTA, propuesta, ahora=ahora))

    for r in recomendaciones:
        r["tipo"] = dominio

    #  Lo mas urgente primero; los empates en orden estable, para que dos
    #  lecturas iguales se puedan comparar.
    recomendaciones.sort(
        key=lambda r: (r["prioridad"] if r["prioridad"] is not None else 99,
                       r["senal_origen"], r["origen_id"]))

    return {
        "asistente": dominio,
        "organizacion": {"id": str(org.id), "nombre": org.name},
        "ahora": ahora.isoformat(),
        "registrado": registrar,
        "resumen": {
            "recomendaciones": len(recomendaciones),
            "propuestas_creadas": conteo[PROPUESTA] if registrar else 0,
            "repetidas": conteo[REPETIDA],
            "datos_insuficientes": conteo[DATOS_INSUFICIENTES],
            "con_datos_faltantes": sum(
                1 for r in recomendaciones if r["datos_faltantes"]),
            "con_habilidad_bloqueada": sum(
                1 for r in recomendaciones
                if r["habilidad"].get("estado") == habilidades.BLOQUEADA),
            #  El reparto por estado operativo, contado sobre lo que se leyo.
            #  Vacio cuando el dominio no produce actividades, en vez de un
            #  cero por estado que sugeriria que se miraron y no habia.
            "por_estado": _por_estado(recomendaciones),
            #  Se cuenta aparte a proposito: "ejecutada" no es "validada", y
            #  un resumen que las sume deja invisible justo lo que falta.
            #  Se mide sobre las DEPENDENCIAS y no sobre la actividad de la
            #  senal: ningun detector de M09 nace de una actividad completada
            #  --las excluye por estar en ESTADOS_FINALES-- asi que ahi el
            #  contador seria siempre 0 y pareceria que no hay nada que mirar.
            "dependencias_ejecutadas_sin_validar": sum(
                1 for r in recomendaciones
                for d in r["dependencias"] if d.get("ejecutada_sin_validar")),
            #  SLA operativo (M04-A). Se cuenta lo VENCIDO y lo que VENCE
            #  PRONTO por separado de lo que no tiene plazo: "sin plazo" no es
            #  "a tiempo", y sumarlos daria una foto tranquilizadora falsa.
            "sla_vencidas": sum(1 for r in recomendaciones
                                if (r["sla"] or {}).get("estado") == sla.VENCIDA),
            "sla_por_vencer": sum(1 for r in recomendaciones
                                  if (r["sla"] or {}).get("estado") == sla.VENCE_PRONTO),
            "sla_sin_plazo": sum(1 for r in recomendaciones
                                 if (r["sla"] or {}).get("estado") == sla.SIN_PLAZO),
            #  M05-A. 'no determinables' se cuenta APARTE de 'resueltas': no
            #  saber si algo sigue pasando no es lo mismo que saber que ya no.
            #  M05-A. El reparto del LIFECYCLE, no de una observacion.
            #  'sin_resolver' es la pregunta que se hace de verdad.
            "incidencias": incidencias.resumen([
                f for r in recomendaciones
                for f in (r["incidencias"] + r["contexto"].get("novedades", []))]),
        },
        "recomendaciones": recomendaciones,
    }
