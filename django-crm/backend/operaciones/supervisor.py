# -*- coding: utf-8 -*-
"""
================================================================================
 SUPERVISOR NOC IA  --  SHADOW MODE: observa, analiza, propone. No ejecuta.
================================================================================

EL CICLO, Y DONDE SE CORTA
--------------------------
    SEÑAL -> NORMALIZACION -> CLASIFICACION -> ANALISIS -> PROPUESTA
          -> REGISTRO -> REVISION HUMANA
                                    |
                                    X  aqui se corta, en esta etapa

Aceptar una propuesta significa "el Jefe de Operaciones esta de acuerdo", NO
"se hizo". No existe ningun camino de ejecucion: 'ejecutar_propuesta' levanta
siempre, y el estado 'ejecutada' ni siquiera esta entre los valores posibles
del modelo. Las dos cosas juntas son lo que vuelve comprobable el Shadow Mode
en vez de prometido.

DE DONDE SALEN LAS SEÑALES
--------------------------
Solo de lo que los datos de hoy sostienen. Cada deteccion es una consulta de
LECTURA sobre estructuras que ya existen -- ninguna escribe, ninguna llama a un
sistema externo, ninguna toca WispHub ni SmartOLT.

LA SEÑAL QUE NO ESTA, Y POR QUE
-------------------------------
No hay ninguna sobre incumplimiento de primera respuesta. 'first_response_at'
esta poblado en 4 de 165 casos (medido el 15/09/2026), asi que su ausencia no
prueba nada: un caso sin ese dato puede haber sido atendido en diez minutos.
Afirmar un incumplimiento sobre eso seria acusar a alguien de algo que el dato
no sostiene. Si alguna vez hace falta usarlo, se reporta como
'dato insuficiente / medicion no disponible', nunca como incumplimiento.

Y por el mismo motivo ninguna propuesta puede nombrar a una persona como causa:
una demora puede ser un bloqueo, un material, una dependencia, una ausencia, un
cambio de prioridad o un dato mal cargado. La lista de causas vive en
NovedadOperativa.TIPOS y 'incumplimiento_de_persona' no esta en ella.

LA PRIORIDAD NO ES UN NUMERO MAGICO
-----------------------------------
Se calcula sumando componentes con nombre, y cada componente que sumo queda
escrito en la evidencia de la propuesta. Quien la lea puede reconstruir por que
quedo donde quedo, en vez de confiar en un score.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from campo.models import OrdenTrabajo
from common.models import Org
from cases.models import Case
from operaciones import auditoria, capacidad, habilidades
from operaciones.models import (
    ActividadOperativa,
    DisponibilidadTecnico,
    ProgramacionOrden,
    ProgramacionSemanal,
    PropuestaSupervisor,
)

# =============================================================================
#  EL INTERRUPTOR DE ESTA ETAPA
# =============================================================================
#  No es un segundo kill switch: el de autonomia vive en el motor
#  (asistente.interruptor_autonomia, Fase 1) y gobierna las ESCRITURAS del
#  motor contra sistemas externos. Esto es otra cosa -- la bandera de fase que
#  declara que el Supervisor todavia no tiene ningun camino de ejecucion.
#
#  Esta en True y no hay codigo que lo apague. Ponerlo en False no habilitaria
#  nada: 'ejecutar_propuesta' levanta igual. Existe para que la condicion se
#  pueda AFIRMAR en una prueba en vez de deducirse de que no hay llamadas.
SHADOW_MODE = True


class EjecucionNoPermitida(RuntimeError):
    """
    El Supervisor intentó ejecutar algo. En esta etapa no puede, y punto.

    Es una excepción y no un valor de retorno para que ningún camino pueda
    ignorarla por descuido -- mismo criterio que FaltaIdentidadEnSesion en el
    motor.
    """


# Ventanas de deteccion. Son de esta etapa y estan juntas a proposito: cambiar
# una no obliga a leer el codigo de deteccion.
DIAS_CASO_ANTIGUO = 7
HORAS_COMPROMISO_POR_VENCER = 24
DIAS_VIGENCIA_PROPUESTA = 7


@dataclass
class Senal:
    """Un hecho observado, ya normalizado. Todavía no es una propuesta."""

    tipo: str
    origen_tipo: str
    origen_id: str
    evidencia: list[dict] = field(default_factory=list)
    datos: dict[str, Any] = field(default_factory=dict)
    #  LA IDENTIDAD DE LA CONDICION  --  paso M09-D
    #  Lleva solo lo que, si cambia, convierte esto en otra situacion: el
    #  motivo de un bloqueo, la fecha comprometida, la dependencia concreta.
    #  NUNCA una magnitud que avanza sola (los dias que lleva abierto un caso),
    #  porque entonces cada ciclo veria una condicion "nueva" y una propuesta
    #  rechazada volveria al dia siguiente. Ver PropuestaSupervisor.huella_condicion.
    huella: str = ""


def _observacion(fuente: str, identificador, dato: str, observado_en=None) -> dict:
    """
    Una pieza de evidencia. Siempre las mismas cuatro claves.

    'observado_en' es cuándo se LEYÓ el dato, no cuándo ocurrió el hecho: es lo
    que permite saber, semanas después, si la propuesta se tomó con información
    fresca o vieja.
    """
    return {
        "fuente": fuente,
        "id": str(identificador),
        "dato": dato,
        "observado_en": (observado_en or timezone.now()).isoformat(),
    }


# =============================================================================
#  DETECCION  --  ocho señales, todas de solo lectura
# =============================================================================


def detectar(org, ahora=None) -> list[Senal]:
    """Todas las señales vigentes de una organización. No escribe nada."""
    ahora = ahora or timezone.now()
    señales: list[Senal] = []
    for detector in (
        _casos_abiertos_antiguos,
        _actividades_vencidas,
        _actividades_sin_responsable,
        _actividades_bloqueadas,
        _compromisos_por_vencer,
        _dependencias_pendientes,
        _ordenes_sin_programar,
        _ordenes_desincronizadas,
        _programaciones_sin_publicar,
        _ordenes_en_riesgo,
        #  M09-L. Consume M03-G; no recalcula capacidad por su cuenta.
        _capacidad_de_jornada,
        #  M04-A. Consume operaciones/sla.py; no recalcula el plazo.
        _ordenes_con_sla_vencido,
        _ordenes_con_sla_por_vencer,
        #  M05-A. Lee el lifecycle PERSISTENTE; no deduce nada del estado de
        #  la actividad.
        _incidencias_sin_resolver,
        #  M05-B. Solo lo OBSERVABLE: que falte el destinatario.
        _escalamientos_sin_destinatario,
    ):
        señales.extend(detector(org, ahora))
    return señales


#  M09-N (22/09/2026). LO QUE EL ESTADO EXTERNO CAMBIA, Y POR QUE.
#
#  Hasta hoy, "abierto en el CRM hace mas de 7 dias" alcanzaba para proponer
#  revisar el caso. Medido en produccion (diagnostico del 22/09/2026, 100%
#  lectura): de 96 casos antiguos, 78 figuraban CERRADOS en WispHub, 5 estaban
#  en curso con respuestas registradas y 13 no tenian ninguna respuesta. O sea
#  que 78 de 96 propuestas habrian mandado a revisar clientes ya atendidos, y
#  el Supervisor habria nacido desacreditado.
#
#  El estado externo no se consulta al proveedor: se lee de la columna que la
#  importacion ya dejo en el caso ('external_status', con 'external_fetched_at'
#  diciendo cuando se leyo). Este detector NO llama a ningun sistema externo.
#
#  Los cuatro caminos, y lo que cada uno permite concluir:
#
#    cerrado afuera        -> INCONSISTENCIA DE SINCRONIZACION, tipo propio.
#                             Ni abandono, ni desatencion, ni incumplimiento.
#    en curso + respuestas -> NO se emite señal: la antiguedad sola no prueba
#                             estancamiento, y hay actividad registrada.
#    en curso sin respuestas -> señal de caso antiguo. La evidencia es
#                             exactamente esa: no hay respuesta registrada.
#    sin estado externo    -> señal de caso antiguo marcada DATOS_FALTANTES.
#                             No se asume cerrado, ni en curso, ni atendido:
#                             la ausencia de dato no se convierte en un dato.
#
#  Lo que NINGUN camino afirma: que el problema del cliente este resuelto. Eso
#  no lo dice ninguna columna -- lo sabe el cliente.
CERRADO_EN_PROVEEDOR = ("cerrado",)
EN_CURSO_EN_PROVEEDOR = ("nuevo", "en progreso")

#  Como se clasifica cada señal, para que quien la lee sepa que peso tiene.
OBSERVADO = "OBSERVADO"
DATOS_FALTANTES = "DATOS_FALTANTES"


def _estado_externo(caso) -> str:
    """El estado que el proveedor reporto, normalizado. '' si no se sabe."""
    return (getattr(caso, "external_status", "") or "").strip().lower()


def _casos_abiertos_antiguos(org, ahora) -> list[Senal]:
    corte = ahora - timedelta(days=DIAS_CASO_ANTIGUO)
    casos = Case.objects.filter(
        org=org, resolved_at__isnull=True, created_at__lt=corte
    ).only("id", "name", "created_at", "status", "priority",
           "external_status", "external_fetched_at", "provider")
    salida = []
    for c in casos:
        dias = (ahora - c.created_at).days
        externo = _estado_externo(c)
        respuestas = c.respuestas_externas.count()
        base = [
            _observacion("caso", c.id, f"abierto desde {c.created_at:%Y-%m-%d} ({dias} dias)", ahora),
            _observacion("caso", c.id, f"estado actual: {c.status}", ahora),
        ]
        datos = {"dias": dias, "prioridad_caso": c.priority, "nombre": c.name,
                 "estado_externo": getattr(c, "external_status", "") or "",
                 "respuestas_externas": respuestas}

        if externo in CERRADO_EN_PROVEEDOR:
            leido = getattr(c, "external_fetched_at", None)
            salida.append(Senal(
                tipo=PropuestaSupervisor.CASO_DESINCRONIZADO,
                origen_tipo="case",
                origen_id=str(c.id),
                evidencia=base + [
                    _observacion("caso", c.id,
                                 f"estado en el proveedor: {c.external_status}", ahora),
                    _observacion("caso", c.id,
                                 f"estado externo leido el "
                                 f"{leido:%Y-%m-%d %H:%M} UTC" if leido else
                                 "el estado externo no dice cuando se leyo", ahora),
                ],
                datos={**datos, "clasificacion": OBSERVADO},
                #  La condicion es "los dos sistemas no coinciden". No lleva la
                #  magnitud (los dias) por el mismo motivo que la de abajo.
                huella="cerrado_en_proveedor_abierto_en_crm",
            ))
            continue

        if externo in EN_CURSO_EN_PROVEEDOR:
            if respuestas:
                #  En curso afuera y con actividad registrada: la antiguedad
                #  sola no prueba estancamiento, y no hay otra evidencia. No se
                #  inventa una causa: no se emite señal.
                continue
            salida.append(Senal(
                tipo=PropuestaSupervisor.CASO_ANTIGUO,
                origen_tipo="case",
                origen_id=str(c.id),
                evidencia=base + [
                    _observacion("caso", c.id,
                                 f"estado en el proveedor: {c.external_status}", ahora),
                    _observacion("caso", c.id,
                                 "sin ninguna respuesta registrada en el hilo", ahora),
                ],
                datos={**datos, "clasificacion": OBSERVADO},
                huella="abierto_sin_respuesta_registrada",
            ))
            continue

        #  Sin estado externo, o con uno que este detector no reconoce. Se
        #  emite la señal --el caso sigue abierto hace mas de 7 dias, que es un
        #  hecho-- y se dice que falta el dato, en vez de suponerlo.
        salida.append(Senal(
            tipo=PropuestaSupervisor.CASO_ANTIGUO,
            origen_tipo="case",
            origen_id=str(c.id),
            evidencia=base + [
                _observacion("caso", c.id,
                             f"estado en el proveedor: desconocido"
                             f"{f' (valor no reconocido: {c.external_status})' if externo else ''}",
                             ahora),
                _observacion("caso", c.id,
                             f"respuestas registradas en el hilo: {respuestas}", ahora),
            ],
            datos={**datos, "clasificacion": DATOS_FALTANTES},
            #  "sigue abierto" es el hecho; los dias son la magnitud. Si la
            #  huella llevara los dias, mañana seria otra condicion.
            huella="abierto_sin_resolucion",
        ))
    return salida


def _actividades_vencidas(org, ahora) -> list[Senal]:
    pendientes = ActividadOperativa.objects.filter(
        org=org, vence_en__lt=ahora
    ).exclude(estado_operativo__in=ActividadOperativa.ESTADOS_FINALES)
    return [
        Senal(
            tipo=PropuestaSupervisor.ACTIVIDAD_VENCIDA,
            origen_tipo="actividad",
            origen_id=str(a.id),
            evidencia=[
                _observacion("actividad", a.id, f"vencia {a.vence_en:%Y-%m-%d %H:%M}", ahora),
                _observacion("actividad", a.id, f"estado: {a.estado_operativo}", ahora),
            ],
            datos={"horas_vencida": int((ahora - a.vence_en).total_seconds() // 3600),
                   "titulo": a.titulo, "tipo": a.tipo},
            #  La fecha comprometida ES la condicion: si alguien la mueve,
            #  el compromiso es otro y volver a proponer corresponde.
            huella=f"vence:{a.vence_en:%Y-%m-%dT%H:%M}",
        )
        for a in pendientes
    ]


def _actividades_sin_responsable(org, ahora) -> list[Senal]:
    huerfanas = ActividadOperativa.objects.filter(
        org=org, responsable__isnull=True
    ).exclude(estado_operativo__in=ActividadOperativa.ESTADOS_FINALES)
    return [
        Senal(
            tipo=PropuestaSupervisor.ACTIVIDAD_SIN_RESPONSABLE,
            origen_tipo="actividad",
            origen_id=str(a.id),
            evidencia=[
                _observacion("actividad", a.id, "no tiene responsable asignado", ahora),
                _observacion("actividad", a.id, f"estado: {a.estado_operativo}", ahora),
            ],
            datos={"titulo": a.titulo, "tipo": a.tipo},
            huella="sin_responsable",
        )
        for a in huerfanas
    ]


def _actividades_bloqueadas(org, ahora) -> list[Senal]:
    bloqueadas = ActividadOperativa.objects.filter(
        org=org, estado_operativo=ActividadOperativa.BLOQUEADA
    )
    return [
        Senal(
            tipo=PropuestaSupervisor.ACTIVIDAD_BLOQUEADA,
            origen_tipo="actividad",
            origen_id=str(a.id),
            evidencia=[
                # El motivo es la evidencia. La restriccion de la tabla
                # garantiza que exista, asi que esta señal nunca puede ser una
                # acusacion vaga.
                _observacion("actividad", a.id, f"bloqueada por: {a.motivo_bloqueo}", ahora),
            ],
            datos={"titulo": a.titulo, "motivo": a.motivo_bloqueo},
            #  Otro motivo de bloqueo es otro bloqueo, aunque sea la misma
            #  actividad: la decision anterior se tomo sobre otra causa.
            huella=f"bloqueo:{(a.motivo_bloqueo or '')[:48]}",
        )
        for a in bloqueadas
    ]


def _compromisos_por_vencer(org, ahora) -> list[Senal]:
    limite = ahora + timedelta(hours=HORAS_COMPROMISO_POR_VENCER)
    proximos = ActividadOperativa.objects.filter(
        org=org,
        tipo=ActividadOperativa.COMPROMISO,
        vence_en__gte=ahora,
        vence_en__lte=limite,
    ).exclude(estado_operativo__in=ActividadOperativa.ESTADOS_FINALES)
    return [
        Senal(
            tipo=PropuestaSupervisor.COMPROMISO_POR_VENCER,
            origen_tipo="actividad",
            origen_id=str(a.id),
            evidencia=[
                _observacion("actividad", a.id, f"vence {a.vence_en:%Y-%m-%d %H:%M}", ahora),
            ],
            datos={"horas_restantes": int((a.vence_en - ahora).total_seconds() // 3600),
                   "titulo": a.titulo},
            huella=f"vence:{a.vence_en:%Y-%m-%dT%H:%M}",
        )
        for a in proximos
    ]


def _dependencias_pendientes(org, ahora) -> list[Senal]:
    conDependencia = ActividadOperativa.objects.filter(
        org=org, depende_de__isnull=False
    ).exclude(
        estado_operativo__in=ActividadOperativa.ESTADOS_FINALES
    ).select_related("depende_de")
    salida = []
    for a in conDependencia:
        previa = a.depende_de
        if previa.estado_operativo in ActividadOperativa.ESTADOS_FINALES:
            continue
        salida.append(Senal(
            tipo=PropuestaSupervisor.DEPENDENCIA_PENDIENTE,
            origen_tipo="actividad",
            origen_id=str(a.id),
            evidencia=[
                _observacion("actividad", a.id, f"depende de la actividad {previa.id}", ahora),
                _observacion("actividad", previa.id,
                             f"esa actividad esta en '{previa.estado_operativo}'", ahora),
            ],
            datos={"titulo": a.titulo, "depende_de": str(previa.id),
                   "estado_previa": previa.estado_operativo},
            #  Si pasa a depender de OTRA actividad, es otra situacion.
            huella=f"depende:{previa.id}",
        ))
    return salida


# =============================================================================
#  M09-L  --  CAPACIDAD DE LA JORNADA
# =============================================================================
#  El unico detector que este paso agrega. Entra ahora porque M03-G recien dejo
#  la capacidad calculable; antes no habia con que sostener la senal.
#
#  NO REIMPLEMENTA EL CALCULO. Llama a 'operaciones.capacidad', que es la unica
#  fuente: duplicarlo aca crearia dos verdades sobre el mismo numero, y la
#  segunda quedaria vieja en cuanto cambiara cualquiera de las cinco cosas de
#  las que depende.
#
#  DOS SENALES, Y LA SEGUNDA NO ES UN COMODIN
#  ------------------------------------------
#    sobrecarga          -> 'jornada_sobrecargada'. Solo cuando se PUEDE
#                           afirmar: la carga conocida ya no cabe.
#    falta duracion      -> 'dato_incompleto'. Nombra las ordenes concretas a
#                           las que les falta el dato. No se emite una
#                           sobrecarga sobre datos incompletos, porque con
#                           datos parciales la ausencia de sobrecarga NO se
#                           puede demostrar -- esa asimetria la fijo M03-G y
#                           aca se respeta.


def _jornadas_con_trabajo(org, ahora):
    """
    Los dias que tienen trabajo comprometido, dentro del horizonte que ya rige
    para las propuestas. No se inventa una ventana: es 'DIAS_VIGENCIA_PROPUESTA',
    la misma que decide cuanto vive una recomendacion.
    """
    hoy = timezone.localtime(ahora).date()
    return sorted(set(
        ProgramacionOrden.objects
        .filter(org=org, dia__gte=hoy,
                dia__lte=hoy + timedelta(days=DIAS_VIGENCIA_PROPUESTA),
                estado__in=(ProgramacionOrden.PLANIFICADA,
                            ProgramacionOrden.CONFIRMADA))
        .values_list("dia", flat=True)))


def _capacidad_de_jornada(org, ahora) -> list[Senal]:
    """
    Lo unico que este detector EMITE es 'dato_incompleto', y no por timidez.

    POR QUE LA SOBRECARGA NO SE PROPONE TODAVIA
    -------------------------------------------
    H-05 --"Estimar riesgo operacional de una orden por capacidad"-- esta
    declarada BLOQUEADA, y su propia ficha dice por que:

        "BLOQUEADA POR D-4: no existe una definicion medible de capacidad
         operativa, y M09-J decidio no inventarla."
        "Sin definicion de capacidad, cualquier umbral seria arbitrario y la
         senal no seria defendible ante quien la reciba."

    M03-G levanto la MITAD de ese bloqueo: la capacidad ya es medible y
    derivada, no inferida. La otra mitad sigue en pie -- ninguna habilidad
    explica la senal de sobrecarga, y el guarda de M09-K exige que toda senal
    tenga una ("Ninguna senal puede quedar sin habilidad que la explique").
    Emitir una propuesta sin esa ficha seria darle al Jefe de Operaciones una
    recomendacion que el sistema no puede justificar.

    La sobrecarga NO se calla: viaja en el resumen del ciclo como OBSERVACION
    (ver 'correr_ciclo' -> 'capacidad'). Se ve, no se propone.

    LA FALTA DE DURACION SI SE PROPONE, y encaja sin forzar nada:
    'dato_incompleto' es exactamente eso -- un objeto concreto (la jornada de
    una persona) con un campo concreto que falta (la duracion de unas ordenes
    que se pueden nombrar) -- y tiene su ficha desde M09-K.
    """
    salida = []
    for dia in _jornadas_con_trabajo(org, ahora):
        jornada = capacidad.capacidad_de_jornada(org, dia)
        for fila in jornada["resultados"]:
            faltan = fila["carga"]["numeros_sin_duracion"]
            if not faltan:
                continue
            pid = fila["profile"]["id"]
            origen_id = f"{dia}:{pid}"[:128]
            numeros = ", ".join(f"#{n}" for n in faltan)
            salida.append(Senal(
                tipo=PropuestaSupervisor.DATO_INCOMPLETO,
                origen_tipo="jornada",
                origen_id=origen_id,
                evidencia=[
                    _observacion("jornada", origen_id,
                                 f"sin duracion estimada: {numeros}", ahora),
                    _observacion("jornada", origen_id,
                                 f"carga conocida {fila['carga']['minutos_conocidos']} min "
                                 f"de {fila['carga']['ordenes']} orden(es); es una cota "
                                 f"inferior, no el total", ahora),
                ],
                datos={"dia": str(dia), "persona": fila["profile"]["nombre"],
                       "profile_id": pid, "numeros_sin_duracion": faltan,
                       "campo": "duracion_estimada_minutos",
                       "estado_datos": fila["estado_datos"]},
                #  Otra orden sin duracion es otro hecho.
                huella=f"sin_duracion:{dia}:{','.join(str(n) for n in faltan)}"[:128],
            ))
    return salida


def observar_capacidad(org, ahora) -> dict:
    """
    La foto de capacidad del horizonte, para el RESUMEN del ciclo. NO emite
    senales ni propuestas: es una lectura.

    Existe porque la sobrecarga se puede ver aunque todavia no se pueda
    proponer (ver '_capacidad_de_jornada'). Callarla seria peor: el dato
    existe, es defendible, y quien revisa el ciclo tiene que poder mirarlo.
    """
    sobrecargadas, no_determinables = [], []
    for dia in _jornadas_con_trabajo(org, ahora):
        jornada = capacidad.capacidad_de_jornada(org, dia)
        for fila in jornada["resultados"]:
            if fila["riesgo"] == capacidad.SOBRECARGA:
                sobrecargadas.append({
                    "dia": str(dia), "persona": fila["profile"]["nombre"],
                    "profile_id": fila["profile"]["id"],
                    "capacidad_minutos": fila["capacidad_minutos"],
                    "carga_minutos": fila["carga"]["minutos_conocidos"],
                    "exceso_minutos": fila["exceso_minutos"],
                    "ordenes": fila["carga"]["ordenes"],
                    "es_cota_inferior": fila["carga"]["es_cota_inferior"],
                })
            elif fila["resultado"] == capacidad.NO_DETERMINABLE:
                no_determinables.append({
                    "dia": str(dia), "persona": fila["profile"]["nombre"],
                    "motivo": fila["jornada"]["motivo"],
                })
    return {
        "jornadas_sobrecargadas": sobrecargadas,
        "jornadas_no_determinables": no_determinables,
        #  Se dice aqui, no en un comentario: quien lea el resumen tiene que
        #  saber por que una sobrecarga visible no genero una recomendacion.
        "nota": ("La sobrecarga se OBSERVA y no se propone: H-05 está "
                 "BLOQUEADA y ninguna habilidad explica todavía esa señal. "
                 "M03-G ya aportó la definición medible de capacidad que su "
                 "ficha declaraba faltante; desbloquearla es una decisión "
                 "pendiente."),
    }


def _programacion_vigente(org, orden):
    """
    La línea de plan que RIGE para esta orden, si existe.

    'planificada' y 'confirmada' cuentan; 'reprogramada' y 'cancelada' no --
    una línea reprogramada ya fue reemplazada y una cancelada no compromete
    nada. Se devuelve la línea y no un booleano porque quien llama necesita
    saber en qué estado está el plan semanal que la contiene.
    """
    return (
        ProgramacionOrden.objects.filter(
            org=org,
            orden=orden,
            estado__in=(ProgramacionOrden.PLANIFICADA,
                        ProgramacionOrden.CONFIRMADA),
        )
        .select_related("programacion")
        .first()
    )


def _ordenes_sin_programar(org, ahora) -> list[Senal]:
    """
    Órdenes que REQUIEREN programación y no tienen ninguna vigente.

    POR QUE NO ALCANZA CON 'programada_para IS NULL'  --  paso M09-D
    ---------------------------------------------------------------
    ProgramacionOrden y OrdenTrabajo.programada_para son dos cosas distintas y
    NADA las sincroniza -- lo dice el propio modelo: la primera es lo que se
    planificó el viernes anterior, la segunda lo que rige ahora mismo. Una
    orden puede estar en el plan semanal con 'programada_para' todavía en NULL.

    Con la condición anterior esa orden disparaba la señal y el Supervisor
    recomendaba programar algo que ya estaba programado. No era hipotético:
    'programada_para' está en 0 de 3 órdenes de producción (medido el
    17/09/2026), así que el primer plan que M03 cargue produce el falso
    positivo.

    'estado_operativo = asignada' YA implica que no arrancó: ninguna transición
    vuelve a ese estado (campo/services/transiciones.py) y 'iniciada_en' sólo
    se escribe al salir de él. Por eso no se comprueba aparte -- agregarlo
    sugeriría una protección que la máquina de estados ya da. Y por lo mismo
    quedan fuera cancelada, completada, cerrada y correccion_requerida.
    """
    candidatas = OrdenTrabajo.objects.filter(
        org=org,
        programada_para__isnull=True,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )
    salida = []
    for o in candidatas:
        if _programacion_vigente(org, o) is not None:
            # Está en un plan: no es un problema de programación. Si además le
            # falta 'programada_para', lo dice _ordenes_desincronizadas.
            continue
        salida.append(Senal(
            tipo=PropuestaSupervisor.ORDEN_SIN_PROGRAMAR,
            origen_tipo="orden_trabajo",
            origen_id=str(o.id),
            evidencia=[
                _observacion("orden_trabajo", o.id, "sin 'programada_para'", ahora),
                _observacion("orden_trabajo", o.id,
                             f"estado: {o.estado_operativo}", ahora),
                _observacion("programacion_orden", o.id,
                             "sin linea de plan en 'planificada' ni 'confirmada'",
                             ahora),
            ],
            datos={"numero": o.numero, "cliente": o.cliente_nombre},
            huella=f"estado:{o.estado_operativo}",
        ))
    return salida


def _ordenes_desincronizadas(org, ahora) -> list[Senal]:
    """
    La orden SÍ está en un plan publicado, pero 'programada_para' está vacío.

    Es 'dato_incompleto' y no una propuesta de programación: volver a
    programarla duplicaría lo que el plan ya dice. Lo que falta es la
    sincronización entre el plan y el campo que rige -- un dato, no una
    decisión operativa.

    SOLO sobre planes PUBLICADOS. Un borrador todavía no compromete nada, así
    que su falta de sincronización no es una inconsistencia: es un plan a medio
    hacer, y de eso habla 'programacion_sin_publicar'.
    """
    candidatas = OrdenTrabajo.objects.filter(
        org=org,
        programada_para__isnull=True,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )
    salida = []
    for o in candidatas:
        linea = _programacion_vigente(org, o)
        if linea is None:
            continue
        if linea.programacion.estado != ProgramacionSemanal.PUBLICADA:
            continue
        publicada = linea.programacion.publicada_en
        salida.append(Senal(
            tipo=PropuestaSupervisor.DATO_INCOMPLETO,
            origen_tipo="orden_trabajo",
            origen_id=str(o.id),
            evidencia=[
                _observacion("orden_trabajo", o.id,
                             "campo faltante: 'programada_para' (NULL)", ahora),
                _observacion("programacion_orden", linea.id,
                             f"hay plan vigente para el {linea.dia} "
                             f"(estado '{linea.estado}')", ahora),
                _observacion(
                    "programacion_semanal", linea.programacion_id,
                    (f"plan publicado el {publicada:%Y-%m-%d %H:%M}"
                     if publicada
                     else "plan marcado publicado sin 'publicada_en'"),
                    ahora),
            ],
            datos={"numero": o.numero, "campo": "programada_para",
                   "dia_planificado": str(linea.dia)},
            huella="campo:programada_para",
        ))
    return salida


def _programaciones_sin_publicar(org, ahora) -> list[Senal]:
    """
    La semana ya empezó y su plan sigue en borrador.

    Se demuestra con lo que el modelo ya guarda: 'estado', 'publicada_en' y
    'publicada_por'. NO se infiere la publicación de que existan líneas de
    plan -- un borrador también las tiene, y confundir las dos cosas es
    exactamente lo que esta señal no debe hacer.
    """
    hoy = timezone.localtime(ahora).date()
    borradores = ProgramacionSemanal.objects.filter(
        org=org,
        estado=ProgramacionSemanal.BORRADOR,
        semana_inicio__lte=hoy,
    )
    return [
        Senal(
            tipo=PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR,
            origen_tipo="programacion_semanal",
            origen_id=str(pr.id),
            evidencia=[
                _observacion("programacion_semanal", pr.id,
                             f"semana del {pr.semana_inicio}, "
                             f"estado '{pr.estado}'", ahora),
                _observacion("programacion_semanal", pr.id,
                             "'publicada_en' vacio", ahora),
                _observacion("programacion_semanal", pr.id,
                             f"la semana empezo hace "
                             f"{(hoy - pr.semana_inicio).days} dia(s)", ahora),
            ],
            datos={"semana": str(pr.semana_inicio),
                   "dias_corridos": (hoy - pr.semana_inicio).days},
            huella=f"semana:{pr.semana_inicio}",
        )
        for pr in borradores
    ]


def _ordenes_en_riesgo(org, ahora) -> list[Senal]:
    """
    Órdenes programadas cuyo técnico principal está declarado ausente ese día.

    Es el único cruce entre M03 y M09, y es el que justifica que exista
    DisponibilidadTecnico: sin esa tabla, esta señal no se puede emitir sin
    inventar la ausencia.
    """
    programadas = OrdenTrabajo.objects.filter(
        org=org, programada_para__isnull=False,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    ).prefetch_related("asignaciones")
    salida = []
    for o in programadas:
        principal = o.tecnico_principal
        if principal is None:
            continue
        dia = timezone.localtime(o.programada_para).date()
        ausencia = DisponibilidadTecnico.objects.filter(
            org=org, profile=principal, fecha=dia, disponible=False
        ).first()
        if not ausencia:
            continue
        salida.append(Senal(
            tipo=PropuestaSupervisor.ORDEN_EN_RIESGO,
            origen_tipo="orden_trabajo",
            origen_id=str(o.id),
            evidencia=[
                _observacion("orden_trabajo", o.id,
                             f"programada para {o.programada_para:%Y-%m-%d %H:%M}", ahora),
                _observacion("disponibilidad", ausencia.id,
                             f"el tecnico asignado esta ausente ese dia: {ausencia.motivo}",
                             ahora),
            ],
            datos={"numero": o.numero, "motivo_ausencia": ausencia.motivo,
                   "tecnico": str(principal.id)},
            #  Otra fecha programada u otra ausencia es otro riesgo.
            huella=f"prog:{o.programada_para:%Y-%m-%d}|aus:{ausencia.id}"[:64],
        ))
    return salida


# =============================================================================
#  ANALISIS  --  de una señal a una recomendación
# =============================================================================
#  Cada señal tiene UNA recomendacion y una forma de priorizar. Nada de esto lo
#  decide un modelo: es codigo, y por eso se puede explicar.

# ==============================================================================
#  M04-A  --  RIESGO TEMPORAL DE UNA ORDEN
# ==============================================================================
#  Los dos detectores de abajo NO calculan nada: preguntan a 'operaciones.sla',
#  que es la unica fuente del plazo. Si el calculo cambiara, cambia alli y aqui
#  no hay que tocar una linea -- y, sobre todo, no puede empezar a decir algo
#  distinto de lo que ven los asistentes.
#
#  Solo emiten sobre plazos CALCULABLES. SIN_PLAZO, NO_APLICA y
#  DATOS_INSUFICIENTES no producen propuesta: una recomendacion apoyada en un
#  plazo que nadie declaro seria inventar el compromiso y despues reclamarlo.

def _ordenes_con_plazo(org, ahora):
    """Las ordenes vivas de la organizacion, con su plazo ya resuelto."""
    from campo.models import OrdenTrabajo
    from operaciones import sla

    ordenes = (OrdenTrabajo.objects
               .filter(org=org)
               .exclude(estado_operativo__in=sla.ESTADOS_TERMINADOS)
               .select_related("tipo_trabajo_version"))
    for o in ordenes:
        yield o, sla.plazo_de(o, ahora)


def _evidencia_de_plazo(orden, plazo, ahora) -> list[dict]:
    """
    Lo que hace explicable la senal. Son hechos leidos, no conclusiones: el
    numero de orden, el plazo que declara su tipo de trabajo, desde cuando se
    cuenta, hasta cuando y con que calendario.
    """
    return [
        _observacion("orden_trabajo", orden.id,
                     f"orden #{orden.numero}, estado '{orden.estado_operativo}'", ahora),
        _observacion("tipo_trabajo", orden.tipo_trabajo_version_id,
                     f"plazo declarado: {plazo['minutos_objetivo']} minuto(s)", ahora),
        _observacion("orden_trabajo", orden.id,
                     f"se cuenta desde {plazo['ancla']} (creacion de la orden)", ahora),
        _observacion("orden_trabajo", orden.id,
                     f"limite: {plazo['limite']}", ahora),
        _observacion("calendario", plazo.get("calendario") or "24/7",
                     f"calendario laboral usado: {plazo.get('calendario') or '24/7'}", ahora),
    ]


def _ordenes_con_sla_vencido(org, ahora) -> list[Senal]:
    from operaciones import sla

    salida = []
    for o, plazo in _ordenes_con_plazo(org, ahora):
        if plazo["estado"] != sla.VENCIDA:
            continue
        evidencia = _evidencia_de_plazo(o, plazo, ahora)
        evidencia.append(_observacion(
            "orden_trabajo", o.id,
            f"atraso: {plazo['minutos_atraso']} minuto(s)", ahora))
        salida.append(Senal(
            tipo=PropuestaSupervisor.ORDEN_SLA_VENCIDO,
            origen_tipo="orden_trabajo",
            origen_id=str(o.id),
            evidencia=evidencia,
            datos={"minutos_objetivo": plazo["minutos_objetivo"],
                   "minutos_atraso": plazo["minutos_atraso"],
                   "limite": plazo["limite"], "ancla": plazo["ancla"],
                   "calendario": plazo.get("calendario"),
                   "numero": o.numero},
            #  La huella NO lleva los minutos de atraso: crecen solos, y una
            #  propuesta rechazada volveria en el ciclo siguiente como si fuera
            #  otra condicion. Lo que identifica la situacion es que ESTA orden
            #  paso su plazo, no cuanto lleva pasado.
            huella="sla_vencido",
        ))
    return salida


def _ordenes_con_sla_por_vencer(org, ahora) -> list[Senal]:
    from operaciones import sla

    salida = []
    for o, plazo in _ordenes_con_plazo(org, ahora):
        if plazo["estado"] != sla.VENCE_PRONTO:
            continue
        evidencia = _evidencia_de_plazo(o, plazo, ahora)
        evidencia.append(_observacion(
            "orden_trabajo", o.id,
            f"quedan {plazo['minutos_restantes']} minuto(s); "
            f"la ventana de aviso es de {plazo['ventana_horas']:.2f} h "
            f"({int(sla.FRACCION_VENTANA * 100)}% del plazo, tope "
            f"{sla.TOPE_VENTANA_HORAS} h)", ahora))
        salida.append(Senal(
            tipo=PropuestaSupervisor.ORDEN_SLA_POR_VENCER,
            origen_tipo="orden_trabajo",
            origen_id=str(o.id),
            evidencia=evidencia,
            datos={"minutos_objetivo": plazo["minutos_objetivo"],
                   "minutos_restantes": plazo["minutos_restantes"],
                   "limite": plazo["limite"], "ancla": plazo["ancla"],
                   "ventana_horas": plazo["ventana_horas"],
                   "ventana_fraccion": plazo["ventana_fraccion"],
                   "calendario": plazo.get("calendario"),
                   "numero": o.numero},
            #  Mismo criterio: los minutos restantes bajan solos.
            huella="sla_por_vencer",
        ))
    return salida


def _escalamientos_sin_destinatario(org, ahora) -> list[Senal]:
    """
    Actividades en estado ESCALADA a las que les falta el destinatario.

    LO QUE ESTE DETECTOR NO HACE, Y ES EL PUNTO
    -------------------------------------------
    No decide que una actividad "necesita escalamiento". No existe una politica
    objetiva que lo determine: antiguedad, atraso o impacto NO son esa politica
    --un compromiso viejo puede estar perfectamente atendido, y uno critico
    puede no necesitar a nadie mas--. Inventarla seria convertir una medida de
    tiempo en una decision de organigrama.

    Lo que SI es observable es una contradiccion en el dato: algo figura como
    escalado y no consta a quien. Eso es un dato faltante, y se dice como tal.
    Puede ocurrir con actividades escaladas antes de M05-B, cuando el sistema
    todavia no registraba destinatario.
    """
    escaladas = (ActividadOperativa.objects
                 .filter(org=org, estado_operativo=ActividadOperativa.ESCALADA)
                 .filter(Q(escalado_a__isnull=True) | Q(nivel_escalamiento=""))
                 .select_related("escalado_a"))
    salida = []
    for a in escaladas:
        faltan = []
        if a.escalado_a_id is None:
            faltan.append("destinatario")
        if not a.nivel_escalamiento:
            faltan.append("nivel")
        salida.append(Senal(
            tipo=PropuestaSupervisor.ESCALAMIENTO_SIN_DESTINATARIO,
            origen_tipo="actividad",
            origen_id=str(a.id),
            evidencia=[
                _observacion("actividad", a.id,
                             f"'{a.titulo}' figura en estado 'escalada'", ahora),
                _observacion("actividad", a.id,
                             f"destinatario: "
                             f"{a.escalado_a_id or 'NO CONSTA'}", ahora),
                _observacion("actividad", a.id,
                             f"nivel: {a.nivel_escalamiento or 'NO CONSTA'}", ahora),
                _observacion("actividad", a.id,
                             f"escalada el: {a.escalado_en or 'NO CONSTA'}", ahora),
            ],
            datos={"titulo": a.titulo, "faltan": faltan,
                   "escalado_a": str(a.escalado_a_id) if a.escalado_a_id else None,
                   "nivel": a.nivel_escalamiento or None},
            #  La huella lleva QUE falta, no cuanto lleva asi.
            huella=f"faltan:{','.join(faltan)}",
        ))
    return salida


def _incidencias_sin_resolver(org, ahora) -> list[Senal]:
    """
    Incidencias ABIERTA o EN_GESTION. Las RESUELTA se ignoran.

    El filtro es sobre la COLUMNA 'estado'. No se mira si la actividad sigue
    bloqueada: desbloquear no resuelve una incidencia, y un detector que lo
    dedujera dejaria de ver causas que nadie atendio.
    """
    from operaciones import incidencias, novedades

    salida = []
    for n in novedades.sin_resolver(org, ahora):
        f = incidencias.ficha(n, ahora)
        evidencia = [
            _observacion("novedad", n.id,
                         f"incidencia {n.get_tipo_display()} en estado "
                         f"'{n.get_estado_display()}'", ahora),
            _observacion("novedad", n.id,
                         f"registrada el {n.created_at:%Y-%m-%d %H:%M} "
                         f"(hace {f['antiguedad_horas']} h)", ahora),
            _observacion("novedad", n.id,
                         f"impacto declarado: {f['impacto_etiqueta'] or 'ninguno'}",
                         ahora),
            _observacion("novedad", n.id,
                         f"descripcion: {f['descripcion'] or '(vacia)'}", ahora),
            _observacion("novedad", n.id,
                         f"registrada por: {f['registrada_por'] or 'sin registrar'}",
                         ahora),
            _observacion("novedad", n.id,
                         f"contexto observable: {f['contexto']['por_que']}", ahora),
        ]
        if n.orden_id:
            evidencia.append(_observacion(
                "orden_trabajo", n.orden_id,
                f"orden relacionada #{n.orden.numero}", ahora))
        if n.actividad_id:
            evidencia.append(_observacion(
                "actividad", n.actividad_id,
                f"actividad relacionada: {n.actividad.titulo}", ahora))
        for falta in f["datos_faltantes"]:
            evidencia.append(_observacion(
                "novedad", n.id, f"falta {falta['campo']}: {falta['por_que']}", ahora))

        salida.append(Senal(
            tipo=PropuestaSupervisor.INCIDENCIA_SIN_RESOLVER,
            origen_tipo="novedad",
            origen_id=str(n.id),
            evidencia=evidencia,
            datos={"tipo": n.tipo, "estado": n.estado, "impacto": n.impacto,
                   "antiguedad_horas": f["antiguedad_horas"],
                   "orden": f["orden"], "actividad": f["actividad"],
                   "datos_faltantes": [x["campo"] for x in f["datos_faltantes"]]},
            #  La huella lleva el ESTADO, no la antiguedad: las horas crecen
            #  solas y harian volver cada ciclo una propuesta ya rechazada.
            #  Pasar de ABIERTA a EN_GESTION si es otra situacion.
            huella=f"estado:{n.estado}",
        ))
    return salida


def _prioridad(base: int, componentes: dict[str, int]) -> tuple[int, list[str]]:
    """
    Prioridad = base menos lo que la hace más urgente. Devuelve el número y la
    lista de componentes, para que la propuesta pueda explicarlo.

    Menor es más urgente, igual que en ProgramacionOrden.
    """
    valor = base
    explicacion = [f"base {base}"]
    for nombre, peso in componentes.items():
        valor -= peso
        explicacion.append(f"{nombre} -{peso}")
    return max(0, min(99, valor)), explicacion


def analizar(senal: Senal) -> dict:
    """
    Qué propone el Supervisor ante esta señal, y por qué.

    Devuelve las piezas de la propuesta. NO la crea ni la guarda: separar el
    juicio del registro permite probar el juicio sin base de datos.
    """
    d = senal.datos
    if senal.tipo == PropuestaSupervisor.CASO_ANTIGUO:
        prioridad, comp = _prioridad(50, {"antiguedad": min(d.get("dias", 0), 30)})
        #  M09-N: el motivo dice QUE evidencia hay, y cual falta. Antes decia
        #  siempre lo mismo -- "no hay fecha de resolucion" -- aunque el caso
        #  estuviera cerrado del otro lado.
        if d.get("clasificacion") == DATOS_FALTANTES:
            motivo = (f"Lleva {d.get('dias')} días abierto sin resolución registrada, "
                      f"y no consta el estado del caso en el sistema del proveedor. "
                      f"No se afirma que nadie lo haya atendido ni que siga pendiente: "
                      f"falta el dato para saberlo.")
        else:
            motivo = (f"Lleva {d.get('dias')} días abierto sin resolución registrada y "
                      f"sin ninguna respuesta en el hilo, mientras el proveedor lo "
                      f"reporta como '{d.get('estado_externo')}'. No se afirma quién "
                      f"debía atenderlo.")
        return {
            "accion_propuesta": "Revisar y priorizar este caso, o cerrarlo si ya está resuelto",
            "motivo": motivo,
            "prioridad": prioridad,
            "impacto": "Un caso abierto sin movimiento no aparece en ninguna cola de trabajo",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.CASO_DESINCRONIZADO:
        #  Base mas baja que la de un caso antiguo: el cliente ya fue atendido
        #  del lado del proveedor, asi que esto es deuda de registro, no riesgo
        #  operativo. Y NIVEL_OBSERVAR, no recomendar una accion sobre el caso:
        #  lo que hay que revisar es la sincronizacion, que es otro asunto.
        prioridad, comp = _prioridad(30, {})
        return {
            "accion_propuesta": ("Revisar la sincronización con el proveedor: el caso "
                                 "figura cerrado allá y abierto en el CRM"),
            "motivo": (f"El proveedor lo reporta como '{d.get('estado_externo')}' y en el "
                       f"CRM sigue sin fecha de resolución, {d.get('dias')} días después "
                       f"de creado. Es una inconsistencia entre los dos sistemas: no se "
                       f"afirma incumplimiento de nadie, ni atraso, ni que el problema "
                       f"del cliente esté resuelto."),
            "prioridad": prioridad,
            "impacto": ("Un caso cerrado afuera y abierto acá infla la cola del CRM y "
                        "hace que los conteos de casos abiertos no describan la operación"),
            "nivel": PropuestaSupervisor.NIVEL_OBSERVAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ESCALAMIENTO_SIN_DESTINATARIO:
        faltan = d.get("faltan") or []
        prioridad, comp = _prioridad(50, {})
        return {
            "accion_propuesta": "Completar el registro del escalamiento: "
                                "declarar a quién se escaló y con qué nivel",
            #  NO se propone UN destinatario. El Supervisor no tiene politica
            #  que le permita elegirlo, y elegirlo igual seria inventar la
            #  decision que este bloque decidio no automatizar.
            "motivo": (
                f"La actividad figura como escalada pero no consta "
                f"{' ni '.join(faltan)}. Un escalamiento sin destinatario no "
                f"llega a nadie. No se sugiere a quién escalarla: no existe "
                f"todavía una política operativa que lo determine, y elegirlo "
                f"sin ella sería inventar la decisión."),
            "prioridad": prioridad,
            "impacto": "Un escalamiento que no consta a quién fue no se puede seguir",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.INCIDENCIA_SIN_RESOLVER:
        horas = d.get("antiguedad_horas") or 0
        #  El impacto declarado pesa; su AUSENCIA no se castiga ni se premia.
        peso = {"critico": 25, "alto": 15, "medio": 8, "bajo": 3}.get(d.get("impacto"), 0)
        prioridad, comp = _prioridad(
            45, {"antiguedad": min(horas // 24, 15), "impacto": peso})
        falta = d.get("datos_faltantes") or []
        return {
            "accion_propuesta": "Atender esta incidencia, o registrar cómo se resolvió",
            "motivo": (
                f"Sigue en '{d.get('estado')}' desde hace {horas} h. Una "
                f"incidencia solo se resuelve declarándolo: que la actividad "
                f"se haya desbloqueado no significa que la causa se haya "
                f"atendido."
                + (f" No se declaró: {', '.join(falta)}." if falta else "")),
            "prioridad": prioridad,
            "impacto": "Una causa operativa sin resolver se repite en la siguiente orden",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ORDEN_SLA_VENCIDO:
        atraso = d.get("minutos_atraso", 0)
        prioridad, comp = _prioridad(40, {"atraso": min(atraso // 30, 30)})
        return {
            "accion_propuesta": "Revisar esta orden: su plazo operativo ya pasó",
            #  El texto describe TIEMPO, no conducta. No dice "nadie la
            #  atendió" ni "se incumplió": dice cuánto plazo había, desde
            #  cuándo se cuenta y cuánto lleva pasado. Si hay una causa --una
            #  ausencia, una falta de material-- vive en las novedades, y este
            #  detector no la conoce.
            "motivo": (f"El tipo de trabajo declara {d.get('minutos_objetivo')} "
                       f"minuto(s) de plazo. Contado desde que se creó la orden y "
                       f"sobre el calendario laboral, el límite era "
                       f"{d.get('limite')}; lleva {atraso} minuto(s) pasado. "
                       f"Esto mide tiempo transcurrido, no responsabilidad: la "
                       f"causa, si la hay, está en las novedades de la orden."),
            "prioridad": prioridad,
            "impacto": "Una orden fuera de su plazo no aparece como tal en ninguna cola",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ORDEN_SLA_POR_VENCER:
        restantes = d.get("minutos_restantes", 0)
        prioridad, comp = _prioridad(55, {"cercania": min(30 - restantes // 30, 20)})
        return {
            "accion_propuesta": "Confirmar que esta orden alcanza su plazo, o reprogramarla",
            "motivo": (f"Quedan {restantes} minuto(s) para el límite "
                       f"({d.get('limite')}), dentro de la ventana de aviso de "
                       f"{d.get('ventana_horas'):.2f} h. La ventana es "
                       f"proporcional al plazo, no fija: un trabajo de dos horas "
                       f"no se avisa con la misma antelación que uno de tres días."),
            "prioridad": prioridad,
            "impacto": "Avisar antes del límite es lo único que permite reprogramar a tiempo",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ACTIVIDAD_VENCIDA:
        horas = d.get("horas_vencida", 0)
        prioridad, comp = _prioridad(40, {"horas_vencida": min(horas // 4, 30)})
        return {
            "accion_propuesta": "Reprogramar la fecha objetivo o reasignar la actividad",
            "motivo": (f"Pasó su fecha objetivo hace {horas} h y sigue sin cerrarse. "
                       f"La causa no está registrada: puede ser un bloqueo, una "
                       f"dependencia o una reprogramación que nadie anotó."),
            "prioridad": prioridad,
            "impacto": "Un compromiso vencido sin causa registrada no se puede explicar al cliente",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ACTIVIDAD_SIN_RESPONSABLE:
        prioridad, comp = _prioridad(45, {})
        return {
            "accion_propuesta": "Asignar un responsable",
            "motivo": "Nadie figura como responsable, así que no está en la cola de ninguna persona.",
            "prioridad": prioridad,
            "impacto": "Trabajo que existe y que nadie ve",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ACTIVIDAD_BLOQUEADA:
        prioridad, comp = _prioridad(35, {"bloqueo_declarado": 10})
        return {
            "accion_propuesta": "Resolver el bloqueo declarado o escalar",
            "motivo": f"Está bloqueada por: {d.get('motivo')}.",
            "prioridad": prioridad,
            "impacto": "Todo lo que dependa de esta actividad queda detenido",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.COMPROMISO_POR_VENCER:
        restantes = d.get("horas_restantes", 24)
        prioridad, comp = _prioridad(45, {"cercania": max(0, 24 - restantes)})
        return {
            "accion_propuesta": "Confirmar que el compromiso se va a cumplir, o avisar antes",
            "motivo": f"Vence en {restantes} h y todavía no está cerrado.",
            "prioridad": prioridad,
            "impacto": "Avisar tarde de un incumplimiento cuesta más que avisar antes",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.DEPENDENCIA_PENDIENTE:
        prioridad, comp = _prioridad(55, {"dependencia": 5})
        return {
            "accion_propuesta": "Atender primero la actividad de la que esta depende",
            "motivo": (f"No puede avanzar: la actividad {d.get('depende_de')} sigue "
                       f"en '{d.get('estado_previa')}'."),
            "prioridad": prioridad,
            "impacto": "Trabajar sobre esta antes que sobre la otra no la desbloquea",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ORDEN_SIN_PROGRAMAR:
        prioridad, comp = _prioridad(40, {"sin_fecha": 10})
        return {
            "accion_propuesta": "Programar la orden dentro del plan de la semana",
            "motivo": (f"La OT #{d.get('numero')} está asignada, no tiene fecha "
                       f"programada y no aparece en ninguna línea vigente del "
                       f"plan semanal. No se afirma que esté atrasada: sin fecha "
                       f"comprometida no hay atraso que medir."),
            "prioridad": prioridad,
            "impacto": "Una orden sin fecha no se despacha y no aparece en la ruta de nadie",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.PROGRAMACION_SIN_PUBLICAR:
        prioridad, comp = _prioridad(
            35, {"dias_corridos": min(d.get("dias_corridos", 0) * 3, 20)})
        return {
            "accion_propuesta": "Revisar y publicar el plan de la semana",
            "motivo": (f"La semana del {d.get('semana')} ya empezó y su plan sigue "
                       f"en borrador. No se afirma que esté incompleto ni que "
                       f"alguien lo haya olvidado: sólo que no está publicado."),
            "prioridad": prioridad,
            "impacto": "Un plan en borrador no compromete a nadie: las cuadrillas no lo ven",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.DATO_INCOMPLETO:
        #  NIVEL 0: informa, no recomienda. No tiene revisor ni prioridad
        #  operativa -- no es una decisión que alguien deba tomar, es un dato
        #  que falta. Se le da la prioridad más baja a propósito.
        prioridad, comp = _prioridad(90, {})

        #  M09-L: el mismo tipo de señal cubre dos hechos concretos distintos.
        #  El texto los distingue en vez de fundirlos en una frase genérica:
        #  "falta un dato" no le sirve a nadie si no dice cuál y dónde.
        if d.get("numeros_sin_duracion"):
            numeros = ", ".join(f"#{n}" for n in d["numeros_sin_duracion"])
            return {
                "accion_propuesta": (f"Declarar la duración estimada de "
                                     f"{numeros}"),
                "motivo": (f"La jornada del {d.get('dia')} de "
                           f"{d.get('persona')} no se puede evaluar: "
                           f"{numeros} no tienen duración estimada. La carga "
                           f"calculada es una COTA INFERIOR, no el total, así "
                           f"que no se puede afirmar que la jornada quepa. No "
                           f"se supone ninguna duración."),
                "prioridad": prioridad,
                "impacto": ("Sin duración no hay capacidad calculable: la "
                            "sobrecarga de ese día no se puede descartar"),
                "nivel": PropuestaSupervisor.NIVEL_OBSERVAR,
                "componentes_prioridad": comp,
            }

        return {
            "accion_propuesta": (f"Dato faltante: '{d.get('campo')}' en la OT "
                                 f"#{d.get('numero')}"),
            "motivo": (f"La orden está en el plan publicado para el "
                       f"{d.get('dia_planificado')}, pero su campo "
                       f"'{d.get('campo')}' está vacío. El plan y el campo que "
                       f"rige no coinciden. No se infiere por qué ni de quién "
                       f"es: sólo que el dato falta."),
            "prioridad": prioridad,
            "impacto": "Lo que el plan dice y lo que rige no coinciden",
            "nivel": PropuestaSupervisor.NIVEL_OBSERVAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.ORDEN_EN_RIESGO:
        prioridad, comp = _prioridad(30, {"tecnico_ausente": 15})
        return {
            "accion_propuesta": "Reprogramar la orden o reasignarla a otra cuadrilla",
            "motivo": (f"La OT #{d.get('numero')} está programada para un día en que "
                       f"su técnico principal está declarado ausente "
                       f"({d.get('motivo_ausencia')})."),
            "prioridad": prioridad,
            "impacto": "La visita no se va a poder hacer, y el cliente se entera el mismo día",
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    # Una señal sin analisis declarado no produce propuesta. Es fail-closed:
    # antes que inventar una recomendacion, no se hace ninguna.
    return {}


# =============================================================================
#  REGISTRO  --  crear la propuesta, con su evidencia
# =============================================================================


def registrar_propuesta(org, senal: Senal, analisis: dict, ahora=None) -> PropuestaSupervisor:
    """
    Crea la propuesta. Levanta si no hay evidencia o si no hay análisis.

    La validación va antes del INSERT y además está en la base (ver la
    restricción 'propuesta_exige_evidencia'): las dos, porque una sola se
    puede saltear llamando por el otro camino.
    """
    ahora = ahora or timezone.now()
    if not senal.evidencia:
        raise ValueError(
            f"Señal '{senal.tipo}' sin evidencia: no se registra ninguna propuesta."
        )
    if not analisis:
        raise ValueError(
            f"Señal '{senal.tipo}' sin análisis declarado: el Supervisor no inventa "
            f"una recomendación para una señal que no sabe interpretar."
        )

    # Los componentes de la prioridad viajan COMO EVIDENCIA. Asi la propuesta
    # puede explicar por que quedo donde quedo, en vez de mostrar un numero.
    evidencia = list(senal.evidencia)
    evidencia.append(_observacion(
        "calculo_prioridad", senal.origen_id,
        " · ".join(analisis.get("componentes_prioridad", [])), ahora))

    propuesta = PropuestaSupervisor(
        org=org,
        tipo_senal=senal.tipo,
        origen_tipo=senal.origen_tipo,
        origen_id=senal.origen_id,
        huella_condicion=senal.huella,
        accion_propuesta=analisis["accion_propuesta"],
        motivo=analisis["motivo"],
        evidencia=evidencia,
        prioridad=analisis["prioridad"],
        impacto=analisis.get("impacto", ""),
        nivel_autonomia_requerido=analisis.get(
            "nivel", PropuestaSupervisor.NIVEL_RECOMENDAR),
        #  QUE HABILIDAD, Y EN QUE VERSION  --  paso M09-K
        #  ----------------------------------------------
        #  Hasta aca el campo quedaba vacio en todas las propuestas (52 de 52,
        #  medido en M09-E), asi que no habia forma de saber con que definicion
        #  se habia emitido una recomendacion de hace seis meses.
        #
        #  Guarda SOLO la version de la habilidad, con el prefijo 'habilidad:'
        #  puesto a proposito: el campo se llama 'conocimiento_version' y todavia
        #  no existe ningun documento de conocimiento versionado. Poner ahi algo
        #  que pareciera una version de conocimiento seria inventar una precision
        #  que no tenemos. Ver operaciones/habilidades.py::referencia_de.
        #
        #  Una señal sin ficha devuelve "" -- el mismo valor que tenia antes.
        conocimiento_version=habilidades.referencia_de(senal.tipo),
        expira_en=ahora + timedelta(days=DIAS_VIGENCIA_PROPUESTA),
    )
    propuesta.full_clean(exclude=["created_by", "updated_by"])
    propuesta.save()

    # El autor es la IA: 'actor=None' a proposito. Inventar un usuario de
    # sistema haria que despues se confunda con una persona en la bitacora.
    auditoria.registrar(
        org=org, actor=None, accion="CREATE",
        entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id,
        nombre=propuesta.accion_propuesta,
        descripcion=f"Supervisor NOC IA (Shadow Mode) detectó: {senal.tipo}",
        estado_nuevo=propuesta.estado,
        extra={"tipo_senal": senal.tipo, "origen": f"{senal.origen_tipo}:{senal.origen_id}",
               "nivel_requerido": propuesta.nivel_autonomia_requerido},
    )
    return propuesta


def _ya_propuesta(org, senal: Senal) -> bool:
    """
    Si esta misma condición ya fue propuesta y alguien ya decidió sobre ella.

    QUE CAMBIO EN EL PASO M09-D, Y POR QUE
    --------------------------------------
    Antes miraba solo 'estado=propuesta'. El efecto, reportado en M09-C.1: el
    Jefe de Operaciones rechazaba una recomendacion y al ciclo siguiente volvia
    identica. Rechazar es una decision; repetir la pregunta la ignora -- y es
    exactamente el mecanismo que dejo la cola de 'acciones_propuestas' con 36
    pendientes sin revisar.

    Ahora bloquean los cuatro estados de ESTADOS_QUE_BLOQUEAN: pendiente de
    revision, o ya revisada de las tres formas. 'expirada' y 'cancelada' NO
    bloquean, y es deliberado: expirar significa que nadie la miro, asi que
    volver a preguntar es lo correcto.

    LA HUELLA ES LO QUE PERMITE QUE VUELVA CUANDO DEBE
    --------------------------------------------------
    Si la condicion cambia --otro motivo de bloqueo, otra fecha comprometida,
    otra dependencia-- la huella cambia y la propuesta nueva SI se crea, aunque
    la anterior este rechazada. Una decision se toma sobre unos hechos; con
    hechos distintos, la pregunta es otra.

    Lo que NO hace volver a preguntar es que avance una magnitud: un caso no
    deja de ser el mismo caso porque hoy lleve nueve dias en vez de ocho.
    """
    return PropuestaSupervisor.objects.filter(
        org=org,
        tipo_senal=senal.tipo,
        origen_tipo=senal.origen_tipo,
        origen_id=senal.origen_id,
        huella_condicion=senal.huella,
        estado__in=PropuestaSupervisor.ESTADOS_QUE_BLOQUEAN,
    ).exists()


def correr_ciclo(org, ahora=None) -> dict:
    """
    Una pasada completa de Shadow Mode. Devuelve el resumen de lo que pasó.

    NO EJECUTA NADA. Lo único que escribe son filas de PropuestaSupervisor y
    sus renglones de auditoría.
    """
    ahora = ahora or timezone.now()
    with transaction.atomic():
        #  UN CICLO A LA VEZ POR ORGANIZACION  --  paso M09-L
        #  --------------------------------------------------
        #  La deduplicacion es leer ('_ya_propuesta') y despues escribir, y
        #  entre las dos cosas cabe otro ciclo entero. MEDIDO: dos ciclos
        #  simultaneos sobre la misma organizacion dejaban DOS propuestas para
        #  el mismo hecho, con la misma huella. El indice 'idx_propuesta_dedup'
        #  acelera la consulta pero no es unico, asi que la base no lo impedia.
        #
        #  Se bloquea la fila de la ORGANIZACION, que ya existe: no hace falta
        #  un mecanismo nuevo ni una tabla de locks. Es el mismo patron que usa
        #  M03 ('programar_orden' bloquea la orden antes de leer su estado).
        #
        #  CONSECUENCIA QUE HAY QUE SABER: el ciclo pasa a ser UNA transaccion.
        #  Si falla a la mitad no quedan propuestas a medias -- antes quedaban
        #  las de las senales ya procesadas. Para un ciclo manual que se puede
        #  volver a correr, todo-o-nada es mas facil de explicar que un
        #  resultado parcial silencioso.
        Org.objects.select_for_update().get(pk=org.pk)
        return _correr_ciclo(org, ahora)


def _correr_ciclo(org, ahora) -> dict:
    resumen = {"senales": 0, "propuestas": 0, "repetidas": 0,
               "sin_analisis": 0, "expiradas": 0,
               #  M09-L. Las claves de arriba ya existian y no cambian de
               #  significado: las de abajo se AGREGAN para que el ciclo pueda
               #  responder que paso, no solo cuantas cosas pasaron.
               "datos_insuficientes": 0,
               "por_tipo": {},
               "organizacion": {"id": str(org.id), "nombre": org.name},
               "ahora": ahora.isoformat()}
    detalle = []

    resumen["expiradas"] = expirar_vencidas(org, ahora)

    for senal in detectar(org, ahora):
        resumen["senales"] += 1
        resumen["por_tipo"][senal.tipo] = resumen["por_tipo"].get(senal.tipo, 0) + 1
        if senal.tipo == PropuestaSupervisor.DATO_INCOMPLETO:
            resumen["datos_insuficientes"] += 1

        fila = {"tipo": senal.tipo, "origen_tipo": senal.origen_tipo,
                "origen_id": senal.origen_id, "huella": senal.huella,
                "evidencia": senal.evidencia, "datos": senal.datos}

        if _ya_propuesta(org, senal):
            resumen["repetidas"] += 1
            #  Una repetida NO desaparece del detalle: la situacion sigue
            #  ocurriendo y quien mira tiene que verla. Lo que no se repite es
            #  la PROPUESTA, no el hecho.
            detalle.append({**fila, "resultado": "repetida", "propuesta": None})
            continue

        analisis = analizar(senal)
        if not analisis:
            resumen["sin_analisis"] += 1
            detalle.append({**fila, "resultado": "sin_analisis",
                            "propuesta": None})
            continue

        propuesta = registrar_propuesta(org, senal, analisis, ahora)
        resumen["propuestas"] += 1
        detalle.append({**fila, "resultado": "propuesta", "propuesta": {
            "id": str(propuesta.id),
            "accion_propuesta": propuesta.accion_propuesta,
            "motivo": propuesta.motivo,
            "prioridad": propuesta.prioridad,
            "impacto": propuesta.impacto,
            "nivel_autonomia_requerido": propuesta.nivel_autonomia_requerido,
            "conocimiento_version": propuesta.conocimiento_version,
            "estado": propuesta.estado,
            "expira_en": propuesta.expira_en.isoformat(),
        }})

    #  Lo mas urgente primero, y los empates en orden estable por tipo: una
    #  lista que cambia de orden entre dos lecturas iguales no se puede revisar.
    detalle.sort(key=lambda f: (
        (f["propuesta"] or {}).get("prioridad", 99), f["tipo"], f["origen_id"]))
    resumen["detalle"] = detalle
    #  M09-L. La capacidad se OBSERVA en el resumen. No produce propuestas
    #  mientras H-05 siga bloqueada -- ver '_capacidad_de_jornada'.
    resumen["capacidad"] = observar_capacidad(org, ahora)
    return resumen


def expirar_vencidas(org, ahora=None) -> int:
    """
    Marca como expiradas las propuestas que nadie revisó a tiempo.

    Una recomendación de hace tres semanas sobre un caso ya cerrado es ruido, y
    la cola de propuestas que ya existe en el motor (36 pendientes, la más
    vieja del 19/08) es la demostración de a dónde lleva no tener esto.
    """
    ahora = ahora or timezone.now()
    vencidas = PropuestaSupervisor.objects.filter(
        org=org, estado=PropuestaSupervisor.PROPUESTA, expira_en__lt=ahora
    )
    n = 0
    for p in vencidas:
        anterior = p.estado
        p.estado = PropuestaSupervisor.EXPIRADA
        p.save(update_fields=["estado", "updated_at"])
        auditoria.registrar(
            org=org, actor=None, accion="STATUS_CHANGED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=p.id,
            nombre=p.accion_propuesta,
            descripcion="Expiró sin revisión humana",
            estado_anterior=anterior, estado_nuevo=p.estado,
        )
        n += 1
    return n


# =============================================================================
#  REVISION HUMANA  --  el Jefe de Operaciones decide
# =============================================================================


#  QUE PUEDE CAMBIAR UN REVISOR, Y QUE NO  --  paso M09-F
#  ------------------------------------------------------
#  La lista es BLANCA, no negra, por el mismo motivo por el que lo es la de
#  campos de WispHub: con lista negra, un campo nuevo del modelo queda editable
#  por defecto, y el dia que alguien agregue 'ejecutar_ahora' nadie se entera.
#
#  Lo que NO esta y no debe estar:
#    - 'evidencia'        el hecho observado. Un revisor que pudiera editarla
#                         podria fabricar el hecho que justifica su decision.
#    - 'tipo_senal', 'origen_*', 'huella_condicion'   la IDENTIDAD de la
#                         condicion. Cambiarla convierte la propuesta en otra y
#                         rompe la deduplicacion: la misma condicion volveria a
#                         proponerse mañana con la huella vieja.
#    - 'estado'           lo decide la decision, no un campo suelto.
#    - 'accion_propuesta_ref'  el puente a la ejecucion. Vacio toda la etapa.
#    - 'nivel_autonomia_requerido'  subirlo a mano seria darse permiso.
CAMPOS_MODIFICABLES = frozenset({
    "accion_propuesta",
    "motivo",
    "prioridad",
    "impacto",
    "responsable_sugerido",
    "observaciones",
})

#  Lo que escribe la IA al crear una propuesta. 'responsable_sugerido' y
#  'observaciones' NO estan aca a proposito: M09-C prohibe que el Supervisor
#  señale personas, y la unica forma de que no lo haga es que ninguna ruta suya
#  escriba ese campo. Ver registrar_propuesta.
CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR = frozenset({
    "org", "tipo_senal", "origen_tipo", "origen_id", "accion_propuesta",
    "motivo", "evidencia", "prioridad", "impacto",
    "nivel_autonomia_requerido", "huella_condicion", "conocimiento_version",
    "expira_en", "estado",
})


class YaRevisada(ValueError):
    """
    Alguien llegó primero.

    Hereda de ValueError a proposito: la vista ya contesta 400 ante un
    ValueError, y este caso ES una peticion invalida --no un error del
    servidor--. Que sea una clase propia permite distinguirla sin leer el texto
    del mensaje, que es lo que hace la prueba de concurrencia.
    """


def _aplicar_cambios(propuesta, cambios: dict) -> dict:
    """
    Valida y aplica la edicion humana. Devuelve el antes/despues para auditar.

    Se valida TODO antes de escribir nada: una modificacion a medias dejaria la
    propuesta en un estado que el revisor no pidio.
    """
    prohibidos = sorted(set(cambios) - CAMPOS_MODIFICABLES)
    if prohibidos:
        raise ValueError(
            f"Estos campos no los cambia un revisor: {', '.join(prohibidos)}. "
            f"Modificables: {', '.join(sorted(CAMPOS_MODIFICABLES))}. "
            f"La evidencia y la identidad de la condición no se editan: son el "
            f"hecho observado, no una opinión sobre él."
        )

    # El responsable sugerido tiene que ser de la MISMA organizacion. Sin esta
    # comprobacion, un id de otro tenant entraria por la puerta de la edicion.
    responsable = cambios.get("responsable_sugerido")
    if responsable is not None and getattr(responsable, "org_id", None) != propuesta.org_id:
        raise ValueError(
            "El responsable sugerido pertenece a otra organización.")

    if cambios.get("prioridad") is not None:
        p = cambios["prioridad"]
        if not isinstance(p, int) or not (0 <= p <= 100):
            raise ValueError("La prioridad va de 0 a 100.")

    registro = {}
    for campo, nuevo in cambios.items():
        anterior = getattr(propuesta, campo)
        if campo == "responsable_sugerido":
            anterior = str(anterior.id) if anterior else None
            nuevo_serializable = str(nuevo.id) if nuevo else None
        else:
            nuevo_serializable = nuevo
        if anterior == nuevo_serializable:
            continue                      # no se audita lo que no cambio
        setattr(propuesta, campo, nuevo)
        registro[campo] = {"antes": anterior, "despues": nuevo_serializable}
    return registro


def revisar(propuesta: PropuestaSupervisor, *, actor, decision: str,
            comentario: str = "", cambios: dict | None = None,
            ahora=None) -> PropuestaSupervisor:
    """
    Aceptar, modificar o rechazar. Queda auditado quién, cuándo y con qué.

    ACEPTAR NO EJECUTA NADA en esta etapa, y es deliberado: sirve para validar
    si el Supervisor recomienda bien antes de darle ninguna capacidad.

    LA FILA SE BLOQUEA ANTES DE MIRARLE EL ESTADO  --  paso M09-F
    ------------------------------------------------------------
    Hasta M09-D esta funcion comprobaba 'propuesta.estado' sobre el objeto que
    ya tenia en memoria. Dos peticiones HTTP cargan cada una SU copia con
    'get_object_or_404', asi que las dos veian 'propuesta' y las dos escribian:
    quedaban dos renglones de auditoria contradictorios y ganaba el ultimo.
    Reproducido el 17/09/2026 --A acepto, B rechazo encima, estado final
    'rechazada', 2 decisiones auditadas-- antes de cerrarlo.

    El 'select_for_update' hace que la segunda peticion espere a que la primera
    termine y LUEGO lea el estado ya cambiado. El bloqueo es de la base, no del
    proceso: dos contenedores del backend detras de un balanceador no comparten
    memoria, pero si comparten Postgres.
    """
    if decision not in PropuestaSupervisor.ESTADOS_REVISADOS:
        raise ValueError(
            f"Decisión desconocida: {decision!r}. "
            f"Solo {PropuestaSupervisor.ESTADOS_REVISADOS}."
        )
    if actor is None:
        raise ValueError("Una revisión sin revisor no es una revisión.")

    cambios = cambios or {}
    if cambios and decision != PropuestaSupervisor.MODIFICADA:
        raise ValueError(
            f"Para cambiar campos la decisión es 'modificar', no '{decision}'. "
            f"Aceptar con una edición encubierta no es aceptar."
        )

    with transaction.atomic():
        fresca = (PropuestaSupervisor.objects
                  .select_for_update()
                  .get(pk=propuesta.pk))

        if fresca.estado != PropuestaSupervisor.PROPUESTA:
            raise YaRevisada(
                f"Esta propuesta ya está en '{fresca.estado}': una decisión no "
                f"se revisa dos veces."
            )

        anterior = fresca.estado
        campos = ["estado", "revisado_por", "revisado_en", "resultado",
                  "updated_at"]
        registro_cambios = {}

        if cambios:
            #  El hecho historico se copia ANTES de tocar nada, y una sola vez:
            #  si el revisor modificara dos veces, la "original" seguiria siendo
            #  la de la IA y no la de su primera edicion. Hoy no puede --una
            #  propuesta modificada ya no vuelve a 'propuesta'-- pero la guarda
            #  no depende de eso.
            if not fresca.propuesta_original:
                fresca.propuesta_original = {
                    "accion_propuesta": fresca.accion_propuesta,
                    "motivo": fresca.motivo,
                    "prioridad": fresca.prioridad,
                    "impacto": fresca.impacto,
                    "nivel_autonomia_requerido": fresca.nivel_autonomia_requerido,
                    "modificada_por": str(actor.id),
                    "modificada_en": (ahora or timezone.now()).isoformat(),
                }
            registro_cambios = _aplicar_cambios(fresca, cambios)
            campos += sorted(set(cambios) | {"propuesta_original"})

        fresca.estado = decision
        fresca.revisado_por = actor
        fresca.revisado_en = ahora or timezone.now()
        fresca.resultado = comentario
        fresca.save(update_fields=campos)

        # APPROVED y REJECTED ya existian en el registro de verbos de Activity:
        # no se invento ninguno.
        verbo = {
            PropuestaSupervisor.ACEPTADA: "APPROVED",
            PropuestaSupervisor.RECHAZADA: "REJECTED",
            PropuestaSupervisor.MODIFICADA: "UPDATE",
        }[decision]
        extra = {"revisor": str(actor.id), "sin_ejecucion": True}
        if registro_cambios:
            extra["cambios"] = registro_cambios
        auditoria.registrar(
            org=fresca.org, actor=actor, accion=verbo,
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=fresca.id,
            nombre=fresca.accion_propuesta,
            descripcion=comentario,
            estado_anterior=anterior, estado_nuevo=fresca.estado,
            motivo=comentario,
            extra=extra,
        )
    return fresca


def cancelar(propuesta: PropuestaSupervisor, *, motivo: str) -> PropuestaSupervisor:
    """
    La condición desapareció antes de que nadie la mirara.

    POR QUE NO ALCANZABA CON RECHAZAR Y EXPIRAR  --  paso M09-F
    ----------------------------------------------------------
    'cancelada' estaba declarada en ESTADOS desde M09-C y NINGUNA funcion la
    escribia: era un estado inalcanzable, y la metrica "canceladas" del diseño
    habria contado cero para siempre sin que ese cero significara nada.

    Los tres finales dicen cosas distintas y no son intercambiables:

        RECHAZADA  un humano la miro y dijo que no.  -> hay revisor y motivo
        EXPIRADA   nadie la miro a tiempo.           -> no hay revisor
        CANCELADA  dejo de tener sentido mirarla.    -> no hay revisor, y la
                   razon es un hecho del mundo (el caso se cerro por otra via),
                   no una opinion.

    Por eso NO escribe 'revisado_por': cancelar no es una decision humana sobre
    el fondo del asunto, y firmar con el nombre de alguien seria atribuirle una
    opinion que no dio. El motivo si es obligatorio -- una cancelacion sin
    motivo es indistinguible de una fila perdida.

    Una propuesta cancelada SI puede volver a proponerse: 'cancelada' no esta
    en ESTADOS_QUE_BLOQUEAN, porque si la condicion reaparece es una condicion
    nueva que nadie ha juzgado.
    """
    if not (motivo or "").strip():
        raise ValueError(
            "Cancelar sin motivo deja una propuesta muerta sin explicación.")

    with transaction.atomic():
        fresca = (PropuestaSupervisor.objects
                  .select_for_update()
                  .get(pk=propuesta.pk))
        if fresca.estado != PropuestaSupervisor.PROPUESTA:
            raise YaRevisada(
                f"Esta propuesta ya está en '{fresca.estado}': cancelar no pisa "
                f"una decisión que ya se tomó."
            )

        anterior = fresca.estado
        fresca.estado = PropuestaSupervisor.CANCELADA
        fresca.save(update_fields=["estado", "updated_at"])

        auditoria.registrar(
            org=fresca.org, actor=None, accion="STATUS_CHANGED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=fresca.id,
            nombre=fresca.accion_propuesta,
            descripcion="La condición dejó de existir antes de ser revisada",
            estado_anterior=anterior, estado_nuevo=fresca.estado,
            motivo=motivo,
        )
    return fresca


# =============================================================================
#  LA PUERTA QUE NO SE ABRE
# =============================================================================


def ejecutar_propuesta(propuesta: PropuestaSupervisor, *args, **kwargs):
    """
    NO EJECUTA. Levanta siempre, y está aquí para que eso sea afirmable.

    Es la diferencia entre "no encontramos ninguna llamada a un sistema
    externo" --que es una afirmación sobre lo que alguien no vio-- y "el único
    camino declarado hacia la ejecución levanta una excepción", que es una
    afirmación sobre lo que el código hace.

    Cuando la ejecución llegue, no va a pasar por aquí: va a pasar por el
    motor, donde Fase 1 ya dejó el interruptor de autonomía y el registro de
    operaciones idempotentes. Este módulo no le habla a WispHub ni a SmartOLT,
    y no debería empezar a hacerlo.
    """
    raise EjecucionNoPermitida(
        f"Shadow Mode: la propuesta {propuesta.id} no se ejecuta. "
        f"El Supervisor observa y recomienda; ejecutar es otra fase."
    )
