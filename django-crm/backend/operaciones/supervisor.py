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

import logging
import uuid
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

logger = logging.getLogger(__name__)
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


#: Cuantos casos abiertos se diagnostican por ciclo.
#:
#: No es una preferencia: cada uno cuesta una llamada al motor, que a su
#: vez habla con WispHub y SmartOLT. Sin tope, una empresa con doscientos
#: casos abiertos convertiria cada ciclo en doscientos viajes de red.
TOPE_CASOS_A_DIAGNOSTICAR = 15


def detectar(org, ahora=None) -> list[Senal]:
    """Todas las señales vigentes de una organización. No escribe nada."""
    ahora = ahora or timezone.now()
    señales: list[Senal] = []
    for detector in (
        _casos_abiertos_antiguos,
        #  M09-R. Detector PROPIO, y no un camino de '_casos_abiertos_antiguos'
        #  como hasta el 25/09/2026. El motivo esta medido: ahi dentro heredaba
        #  el filtro de DIAS_CASO_ANTIGUO, y de 112 casos cerrados en el
        #  proveedor y sin resolver en el CRM se detectaban 109 -- los 3 que
        #  faltaban eran los que cerraron alla hace menos de una semana. Un caso
        #  cerrado afuera ayer esta tan desincronizado como uno de hace dos
        #  meses: el CRM esta igual de equivocado en los dos.
        _casos_cerrados_en_el_proveedor,
        #  M10. La unica señal que termina en una cuadrilla manejando hasta
        #  una casa. Por eso solo propone lo que la MEDICION sostiene: una
        #  labor que salio del texto queda fuera.
        _casos_que_necesitan_visita,
        #  13/10/2026. La UNICA señal que sale de LEER y no de medir. No
        #  conduce a ninguna accion automatica: produce una hipotesis con su
        #  evidencia para que una persona la autorice.
        _tickets_abiertos_con_tecnico,
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

#  CUANTO PUEDE TENER LA LECTURA PARA SOSTENER UNA PROPUESTA DE CIERRE
#
#  No es prudencia abstracta: proponer cerrar un caso es proponer un cambio de
#  estado, y el unico dato que lo justifica es lo que el proveedor dijo. Si esa
#  lectura tiene semanas, lo que se propone es sincronizar contra una foto que
#  nadie sabe cuan vieja es -- y el ticket pudo reabrirse alla mientras tanto.
#
#  El numero sale de la cadencia real del importador, no de una intuicion: el
#  reloj barre cada hora ('cada_horas: 1' en la config desplegada), asi que una
#  lectura de mas de 3 dias significa que la sincronizacion lleva ~72 pasadas
#  sin escribir. Medido el 25/09/2026, es exactamente lo que pasa: la ultima
#  'external_fetched_at' era de 77,5 horas antes, porque las escrituras del
#  reloj estan bloqueadas por Autonomia 2. Con este corte, esos casos NO
#  generan propuesta de cierre -- que es la conducta correcta: primero se
#  arregla la sincronizacion, despues se decide sobre sus datos.
HORAS_LECTURA_FRESCA = 72

#  Como se clasifica cada señal, para que quien la lee sepa que peso tiene.
OBSERVADO = "OBSERVADO"
DATOS_FALTANTES = "DATOS_FALTANTES"


def _estado_externo(caso) -> str:
    """El estado que el proveedor reporto, normalizado. '' si no se sabe."""
    return (getattr(caso, "external_status", "") or "").strip().lower()


def _casos_abiertos_antiguos(org, ahora) -> list[Senal]:
    from operaciones import areas_del_tenant as areas
    from operaciones import paso_a_despacho as pad

    corte = ahora - timedelta(days=DIAS_CASO_ANTIGUO)
    #  SIN LOS AJENOS  --  16/10/2026. Esta señal proponia tickets de cartera
    #  y de ventas que el Supervisor no tiene por que mirar, y cada hora
    #  volvia a proponer lo que el retiro acababa de cancelar. Se quita lo
    #  que se SABE de otra area; sin el mapa del motor, tambien lo que solo
    #  el mapa puede decidir (sin area escrita y con alguien encima). Ver
    #  'areas_del_tenant.criterio_de_area' y 'sin_ajenos'.
    #
    #  NI LOS QUE ENTRARON A DESPACHO DESPUES DEL CORTE  --  17/10/2026. La
    #  alerta pide "revisar y priorizar"; un caso que esta en la cola de
    #  Despacho ya tiene ese paso dado. Es el mismo problema que el de arriba:
    #  sin esto, la alerta que retira 'retirar_alertas_de_casos_en_despacho'
    #  volveria en la vuelta siguiente, porque 'cancelada' no bloquea repetir.
    #  Y CON EL MISMO CORTE: un caso que lleva mas de DIAS_CASO_ANTIGUO dias en
    #  Despacho sin cerrarse es un caso antiguo otra vez, y la alerta vuelve.
    #  Sin ese limite se apagaria para siempre, porque la cola no tiene otra
    #  salida que cerrar el caso (auditor independiente, 17/10/2026).
    casos = areas.sin_ajenos(
        Case.objects.filter(
            org=org, resolved_at__isnull=True, created_at__lt=corte
        ).exclude(id__in=pad.casos_despachados_desde(org, corte).values("id")),
        areas.criterio_de_area(),
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
            #  Cerrado afuera: NO es un caso abandonado, y desde M09-R tampoco
            #  se emite desde aqui. Lo atiende '_casos_cerrados_en_el_proveedor',
            #  que es su detector propio y no hereda este filtro de antiguedad.
            #  Este 'continue' es lo que impide que el mismo caso salga dos
            #  veces: si se quita, cada desincronizacion vieja genera tambien
            #  una señal de caso antiguo, que es justo la afirmacion falsa que
            #  M09-N vino a corregir.
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


#  CERRADO EN EL PROVEEDOR, ABIERTO EN EL CRM  --  M09-R (25/09/2026)
#  =================================================================
#  ESTADOS QUE CUENTAN COMO ABIERTO EN DEXTER
#
#  Se compara contra 'Closed', que es el unico que 'cases/signals.py' trata
#  como resuelto (RESOLVED_STATUSES). Y se mira ADEMAS 'resolved_at': los dos,
#  porque son dos cosas distintas y la pantalla las usa distinto -- un caso con
#  'status=Closed' y 'resolved_at' nulo existia como bug de sello y hoy no hay
#  ninguno (medido: 0 de 237), pero volver a mirarlo cuesta nada.
#
#  Los estados reales de produccion son tres: New (156), Closed (69) y Assigned
#  (12). 'Pending', 'Rejected' y 'Duplicate' estan declarados y no se usan; se
#  tratan como abiertos porque no son 'Closed', que es lo unico afirmable.
CERRADO_EN_DEXTER = "Closed"


def _casos_que_necesitan_visita(org, ahora) -> list[Senal]:
    """Casos abiertos cuyo EQUIPO dice que la falla es de la red.

    POR QUE ESTA SEÑAL EXISTE
    -------------------------
    Nace el 09/10/2026 con la pantalla de despacho, y resuelve un problema
    concreto: el despacho no puede salir de «todos los casos abiertos». Que un
    caso merezca una visita depende de si ya se intento por telefono, si el
    cliente esta, si hay repuesto -- cosas que no estan en ningun campo y que
    este codigo no puede saber.

    Lo que SI se puede medir es cuando el equipo dice que la falla es de la
    red. Eso es lo que se propone; una persona lo acepta, y recien ahi el caso
    aparece en Despacho.

    NO LA CALCULA ESTE MODULO
    -------------------------
    El veredicto sale de `operaciones.clasificacion_de_trabajo`, que es el
    mismo que usa el despacho. Reconstruir el criterio aqui lo pondria a vivir
    en dos lados y uno de los dos se quedaria viejo -- es el defecto que la
    fase C del seguimiento ya encontro en el frontend.

    LO QUE NO PROPONE
    -----------------
    Un equipo SANO no genera señal: que no sea una falla de red no quiere decir
    que no haya trabajo --el cliente puede pedir una reubicacion-- pero eso lo
    decide una persona, no una medicion que no lo vio.

    Y SIN ENERGIA TAMPOCO. Si el equipo esta caido por dying-gasp, el problema
    es el corte de luz en la casa: mandar una cuadrilla es mandarla a mirar
    como alguien espera que vuelva la luz.

    EL TOPE NO ES UNA PREFERENCIA
    -----------------------------
    Cada caso cuesta una llamada al motor, que a su vez habla con WispHub y
    SmartOLT. Sin tope, una empresa con doscientos casos abiertos convertiria
    cada ciclo del Supervisor en doscientos viajes de red. Se dice cuantos
    quedaron sin mirar en vez de cortar en silencio.
    """
    from campo.services.despacho import contexto_del_caso
    from cases.models import Case
    from operaciones import areas_del_tenant as areas
    from operaciones import clasificacion_de_trabajo as clf

    salida: list[Senal] = []
    #  SIN LOS AJENOS  --  16/10/2026. Un ticket de cartera asignado a un
    #  tecnico llegaba hasta aca y costaba una llamada al motor para proponer
    #  una visita que no le toca a este equipo. Se quita lo que se SABE de
    #  otra area, antes del tope: ver 'areas_del_tenant.criterio_de_area'.
    abiertos = list(
        areas.sin_ajenos(
            Case.objects
            .filter(org=org, is_active=True, is_sample=False,
                    merged_into__isnull=True)
            .exclude(status="Closed")
            .exclude(external_service_id="")
            .exclude(external_service_id__isnull=True),
            areas.criterio_de_area(),
        )
        .order_by("-created_at")[:TOPE_CASOS_A_DIAGNOSTICAR]
    )

    for caso in abiertos:
        try:
            contexto = contexto_del_caso(str(caso.id))
        except Exception:                                    # noqa: BLE001
            #  Un caso que no se pudo consultar no es un caso sano: es uno del
            #  que no se sabe nada. No se propone, y tampoco se afirma que
            #  este bien.
            continue
        if not (isinstance(contexto, dict)
                and contexto.get("contexto_disponible")):
            continue

        veredicto = clf.clasificar(
            contexto,
            marcadores={
                "id_servicio_instalaciones":
                    contexto.get("id_servicio_instalaciones"),
            },
        )
        labor = veredicto.get("labor") or ""

        #  Solo lo que la MEDICION sostiene. Una labor que salio del texto
        #  queda fuera: proponerle a alguien que mande una cuadrilla porque un
        #  asunto decia cierta palabra seria pedirle que confie en lo que nadie
        #  verifico.
        if not veredicto.get("verificada"):
            continue
        if labor not in (clf.CORRECTIVO, clf.TRABAJOS, clf.INSTALACION):
            continue

        equipo = contexto.get("equipo") or {}
        salida.append(Senal(
            tipo=PropuestaSupervisor.CASO_REQUIERE_VISITA,
            origen_tipo="case",
            origen_id=str(caso.id),
            #  Lo que una persona necesita para decidir, cada dato con su
            #  fuente. Quien acepta esto manda a alguien a manejar hasta una
            #  casa: tiene que poder ver contra que.
            evidencia=[
                _observacion("caso", caso.id,
                             f"caso en el CRM: {caso.name}", ahora),
                _observacion("caso", caso.id,
                             f"servicio en el proveedor: "
                             f"{caso.external_service_id}", ahora),
                _observacion("equipo", caso.id,
                             f"estado del equipo: "
                             f"{equipo.get('estado') or 'sin lectura'}", ahora),
                _observacion("clasificacion", caso.id,
                             veredicto.get("porque") or "", ahora),
            ],
            datos={
                "labor_sugerida": labor,
                "fuente_de_la_sugerencia": veredicto.get("fuente") or "",
                #  Viaja la hora de la medicion: al congelarse, una medicion
                #  deja de ser una medicion y pasa a ser un registro de lo que
                #  se veia en un momento.
                "medido_en": contexto.get("capturado_en"),
            },
        ))

    return salida


#:  Cuantos tickets se leen por corrida. Cada diagnostico es una consulta al
#:  modelo MAS las herramientas que consulte: no es gratis, y una corrida que
#:  lee doscientos deja al resto del ciclo esperando. El tope corta; lo que no
#:  entro se lee en la vuelta siguiente, que es dentro de una hora.
TOPE_TICKETS_POR_CORRIDA = 10

#:  Y EL DE LA CORRIDA DEL RELOJ, donde no hay nadie esperando  --  16/10/2026
#:
#:  Mismo criterio que 'TOPE_DIAGNOSTICOS_DESATENDIDO' del modulo optico, que
#:  ya habia pagado esta leccion el 08/10: el tope corto esta pensado para que
#:  un boton conteste rapido, y aplicarlo tambien a la corrida desatendida hace
#:  que una cola grande tarde horas sin que nadie gane nada.
#:
#:  MEDIDO en produccion esa noche: 161 propuestas pendientes, ~50 de ellas
#:  esperando relectura porque su lectura es anterior al grupo. Con el tope en
#:  10 bajaban de 50 a 44 por vuelta: cinco horas para drenar. La corrida leyo
#:  10 tickets en 186 segundos -- unos 18,6 por ticket-- asi que 30 son unos
#:  9 minutos de worker, y drena ese atraso en dos vueltas.
#:
#:  SUBIDO DE 30 A 60 ESA MISMA NOCHE, con la medicion de tres corridas de
#:  produccion. La prediccion de "baja 10 por vuelta" fue FALSA: bajo 2. El
#:  motivo es que son dos conjuntos distintos y se los habia tratado como uno
#:  --la lectura toma 10 de las 161 pendientes, y el paso a Despacho solo
#:  miraba las 60 mas viejas ('TOPE_PASO_A_DESPACHO')--, asi que de los 10
#:  releidos solo algunos caian en la ventana que se estaba midiendo. Desde el
#:  16/10/2026 el paso las mira todas y el tope acota cuantas PASAN.
#:
#:      161 pendientes / 10 por hora  =  16 horas
#:      161 pendientes / 60 por hora  =  2,5 horas
#:
#:  A ~18,6 segundos por ticket, 60 son unos 19 minutos de worker por corrida.
#:  Es mucho para una corrida atendida y es nada para una que corre sola a las
#:  tres de la manana.
#:
#:  ES TRANSITORIO, igual que el del optico: los 161 son atraso acumulado. En
#:  regimen aparecen unos pocos por hora y este tope no se toca nunca.
#:
#:  EL DEFECTO SIGUE SIENDO EL ATENDIDO, a proposito: un llamador nuevo que se
#:  olvide de declararse hereda el tope corto -- tarda mas y no sorprende a
#:  nadie, que es el lado seguro para equivocarse.
TOPE_TICKETS_DESATENDIDO = 60

#:  CUANTOS SE DETECTAN, que es otra cosa y hace falta aparte  --  13/10/2026
#:
#:  Medido en produccion el mismo dia que esto salio: sin tope, el detector
#:  emitio 750 señales de una vez --todos los tickets abiertos con tecnico-- y
#:  el tablero paso de 5 hallazgos a 755. Un numero asi no informa: nadie mira
#:  una lista de setecientos, y ademas cada señal viaja por el ciclo entero.
#:
#:  SE DETECTAN LOS MAS VIEJOS QUE TODAVIA NO SE LEYERON, y esa segunda mitad
#:  se agrego el mismo dia, unas horas despues, porque sin ella el tope
#:  ATASCABA el sistema entero.
#:
#:  LO QUE DECIA ACA, Y ERA FALSO: "no se pierde ninguno: el que no entro hoy
#:  entra cuando los de adelante dejen de estar abiertos". Los de adelante son
#:  justamente los que llevan MAS tiempo abiertos -- no se cierran. MEDIDO esa
#:  misma tarde: 771 tickets cumplian las condiciones, el detector miraba
#:  siempre los mismos 40, y 38 de esos 40 ya estaban leidos. El ciclo corria,
#:  no leia nada, y los otros 731 no iban a mirarse NUNCA.
#:
#:  El sintoma no se parecia a la causa: "el Supervisor no registra lecturas"
#:  se lee como un registro roto, y lo que estaba roto era a QUIEN miraba.
#:
#:  Ahora cada vuelta trae 40 que FALTAN, asi que avanza de verdad. Sigue
#:  habiendo tope --cada lectura cuesta una consulta al modelo-- y los mas
#:  viejos siguen yendo primero dentro de los que faltan.
TOPE_TICKETS_DETECTADOS = 40

#:  Cuanto puede estar un ticket sin movimiento antes de que el Supervisor
#:  pregunte que paso. Lo fijo el cliente el 13/10/2026 con esas palabras: "un
#:  ticket no puede estar dos semanas, maximo 5 dias".
DIAS_SIN_MOVIMIENTO = 5


def _tickets_abiertos_con_tecnico(org, ahora) -> list[Senal]:
    """
    Tickets que siguen ABIERTOS en el proveedor y ya tienen tecnico asignado.

    QUE LOS DISTINGUE DE TODO LO DEMAS DE ESTE ARCHIVO
    --------------------------------------------------
    Las otras señales salen de MEDIR: un plazo que vencio, un equipo que no
    responde, un estado que no coincide. Esta sale de LEER la descripcion que
    escribio quien tomo el reclamo, y por eso no conduce a ninguna accion
    automatica -- produce una hipotesis para que una persona la autorice.

    POR QUE "CON TECNICO ASIGNADO", que fue lo que se pidio: un ticket que ya
    tiene a alguien encima es uno donde el diagnostico sirve para decidir si
    esta bien encaminado. Uno sin asignar es un problema distinto --nadie lo
    tomo-- y tiene su propia señal.

    SI HACE FALTA FILTRAR POR AREA  --  corregido el 14/10/2026
    -----------------------------------------------------------
    Aqui decia lo contrario: "no hace falta, la importacion ya lo hace, el
    tenant declara que departamentos trae ('Soporte Tecnico')". Era cierto
    cuando se escribio y dejo de serlo: la configuracion viva trae Ventas,
    Finanzas, Operativo y Administrativo ademas de Soporte.

    El cliente lo vio en la bandeja: "revise la lista de soporte tecnico en los
    ticket y no salen los ticket de descuentos programados, esos son de
    cartera". Medido: de los tickets abiertos, una sola persona concentraba 563
    --509 de cartera-- mientras la de soporte tenia 76, exactamente los 76 que
    la pantalla de Tickets muestra para esa area.

    EL AREA ES DEL CASO desde cdaa9b27 ('Case.area', escrita por la
    importacion); la de la PERSONA asignada solo decide mientras el caso no la
    tenga. Cuando se escribio esto el caso no la guardaba y salia de la
    persona, que es como la empresa la configura -- y la encontro el cliente
    preguntando lo obvio: "¿no puede el supervisor extraer de esa area los
    ticket sin tanto rodeo?". La regla vive en
    'areas_del_tenant.criterio_de_area', compartida con las otras señales.

    SI NO SE PUEDE SABER, NO SE LEE NADA. Leer un ticket cuesta una consulta al
    modelo: gastarla en uno de cartera es peor que no leer esta vuelta, y
    ademas produce una propuesta que no le toca a nadie de este equipo.

    LO QUE EXIGE, Y POR QUE CADA COSA
      external_status en curso    si el proveedor lo cerro, es otra señal
      resolved_at vacio           si ya se resolvio aqui, no hay nada que leer
      tiene tecnico asignado      lo que se pidio
      lectura fresca              un estado de hace una semana describe un
                                  ticket que pudo cambiar tres veces
      descripcion con texto       sin texto no hay nada que diagnosticar, y
                                  decirlo es distinto de callarlo

    NO DIAGNOSTICA. Devuelve las señales; leer el texto es otra fase, con su
    tope y su tapado de datos personales. Ver 'diagnostico_de_ticket.py'.
    """
    corte_lectura = ahora - timedelta(hours=HORAS_LECTURA_FRESCA)

    #  Perezoso: 'diagnostico_de_ticket' importa este modulo.
    from operaciones.diagnostico_de_ticket import FUENTE as dxt_FUENTE

    #  LOS QUE YA TIENEN SU LECTURA SALEN DE LA COLA. Sin esto el tope de mas
    #  abajo ATASCA el sistema: se miran siempre los mismos 40 --los mas
    #  viejos-- y como ya estan leidos, la vuelta no hace nada y el resto no
    #  entra jamas. Medido el 13/10/2026: 38 de esos 40 ya leidos, 731
    #  esperando detras.
    #
    #  Se pregunta por la EVIDENCIA y no por una bandera: es lo que de verdad
    #  tiene o no tiene la propuesta, el mismo criterio que usa
    #  'diagnostico_de_ticket.le_falta_lectura'. Una bandera puede quedar
    #  puesta sobre una propuesta donde no quedo escrito nada.
    #
    #  NO se mira el ESTADO de la propuesta: una ACEPTADA tambien esta leida, y
    #  volver a leerla gastaria la vuelta en algo que ya se decidio.
    ya_leidos = [
        i for i in (PropuestaSupervisor.objects
                    .filter(org=org,
                            tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
                            evidencia__icontains=dxt_FUENTE)
                    .values_list("origen_id", flat=True))
        if i
    ]

    from operaciones import areas_del_tenant as areas

    criterio = areas.criterio_de_area()
    if not criterio.se_sabe:
        #  SIN EL MAPA NO SE LEE NADA. Un mapa vacio es ambiguo --nadie tiene
        #  area, o el motor no contesto-- y se trata como "no se pudo": leer
        #  cuesta una llamada al modelo por ticket. Desde el 16/10/2026 la
        #  condicion es el mapa y no "nadie es de soporte": con gente en el
        #  mapa y nadie de soporte, lo que trae el area ESCRITA propia se lee
        #  igual, porque el area escrita manda.
        logger.info("Supervisor: sin mapa de areas, no se leen tickets "
                    "esta vuelta")
        return []

    casos = (Case.objects
             .filter(org=org, resolved_at__isnull=True)
             #  SOLO LOS DE SOPORTE. Va antes que todo lo demas porque es lo
             #  que mas recorta: de 771 abiertos con tecnico, los de esta area
             #  eran 76.
             #
             #  DOS CRITERIOS, Y EL ORDEN DE LA FRASE IMPORTA  --  16/10/2026
             #  -------------------------------------------------------------
             #  El area del CASO manda cuando esta escrita; la de la PERSONA
             #  solo decide mientras no lo este.
             #
             #  Hasta hoy el area se deducia del responsable, y esa deduccion
             #  es falsa en cuanto un ticket se asigna a alguien de otra area:
             #  en produccion el Supervisor NOC leia y proponia sobre tickets
             #  de cartera y de ventas asignados a tecnicos. 'Case.area' nacio
             #  para cortar eso, con el valor que 'destinos' ya calculaba.
             #
             #  LOS VIEJOS TODAVIA NO LA TIENEN: los ~1.300 importados antes
             #  del campo tienen 'area' vacia y se siguen filtrando por
             #  persona, igual que ayer. La reconciliacion los va completando
             #  a medida que relee cada ticket, y el dia que no quede ninguno
             #  vacio esta segunda mitad deja de hacer falta.
             #
             #  NO ES FAIL-OPEN: un caso con area vacia no pasa por no tener
             #  area -- pasa por el mismo filtro de persona de siempre. Lo que
             #  no puede ocurrir es que un caso CON area ajena entre por tener
             #  un tecnico encima, y eso es justo lo que la primera mitad
             #  impide.
             #
             #  Desde el 16/10/2026 el criterio vive en
             #  'areas_del_tenant.criterio_de_area', compartido con las otras
             #  señales de tickets y con el retiro de propuestas ajenas: la
             #  misma pregunta, una sola respuesta.
             .filter(criterio.propio)
             .exclude(status=CERRADO_EN_DEXTER)
             .exclude(external_fetched_at__isnull=True)
             .filter(external_fetched_at__gte=corte_lectura)
             #  'assigned_to' es muchos-a-muchos: sin el 'distinct' un caso con
             #  dos tecnicos saldria dos veces, y se diagnosticaria dos veces.
             .filter(assigned_to__isnull=False)
             .exclude(id__in=ya_leidos)
             .distinct()
             .only("id", "name", "status", "description", "created_at",
                   "external_status", "external_status_at",
                   "external_fetched_at", "external_ticket_id",
                   "external_service_id")
             .order_by("created_at")[:TOPE_TICKETS_DETECTADOS])

    salida = []
    for caso in casos:
        if _estado_externo(caso) not in EN_CURSO_EN_PROVEEDOR:
            continue

        texto = (caso.description or "").strip()
        if not texto:
            #  SE DICE, no se calla: un ticket sin descripcion no es un ticket
            #  sano, es uno sobre el que no se puede afirmar nada. Pero no
            #  genera señal: no hay nada que leer, y una propuesta vacia solo
            #  ocuparia lugar en la bandeja.
            continue

        dias = max(0, (ahora - caso.created_at).days) if caso.created_at else 0

        salida.append(Senal(
            tipo=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
            origen_tipo="case",
            origen_id=str(caso.id),
            evidencia=[
                _observacion("caso", caso.id,
                             f"caso en el CRM: {caso.name}", ahora),
                _observacion("proveedor", caso.id,
                             f"ticket {caso.external_ticket_id or 'sin numero'} "
                             f"en estado '{caso.external_status}'", ahora),
                _observacion("antiguedad", caso.id,
                             f"abierto hace {dias} dias", ahora),
            ],
            datos={
                "id_servicio": str(caso.external_service_id or ""),
                "ticket": str(caso.external_ticket_id or ""),
                "dias_abierto": dias,
                #  LA DESCRIPCION NO VIAJA EN LA SEÑAL. Una señal termina
                #  guardada en una propuesta, y el texto de un ticket trae
                #  cedulas escritas a mano -- 136 de cada 300, medido. Quien
                #  la necesita la lee del caso, tapada, en el momento de
                #  diagnosticar.
                "tiene_descripcion": True,
                "sin_movimiento": dias >= DIAS_SIN_MOVIMIENTO,
            },
        ))
    return salida


def _casos_cerrados_en_el_proveedor(org, ahora) -> list[Senal]:
    """
    El proveedor cerro el ticket y el CRM sigue con el caso abierto.

    SIN FILTRO DE ANTIGUEDAD, y es el motivo de que este detector exista
    aparte. Hasta el 25/09/2026 esta señal salia de '_casos_abiertos_antiguos'
    y heredaba su corte de 7 dias: de 112 casos que cumplian la condicion se
    detectaban 109, y los 3 que faltaban eran los mas recientes -- los unicos
    donde actuar todavia sirve de algo.

    LO QUE EXIGE, Y POR QUE CADA COSA
    ---------------------------------
    Proponer un cierre es proponer un cambio de estado, asi que el dato que lo
    sostiene tiene que ser utilizable:

      external_status = cerrado   la condicion misma
      status != Closed            si ya esta cerrado no hay nada que sincronizar
      external_status_at presente cuando cerro ALLA. Sin esto no se puede decir
                                  desde cuando estan desalineados
      external_fetched_at fresca  cuando se LEYO. Una lectura vieja describe un
                                  ticket que pudo reabrirse despues
      external_fetch_error vacio  una lectura que fallo no es una lectura

    Cualquiera que falte deja al caso FUERA: no se emite una señal degradada ni
    se supone el dato ausente. Un caso que no cumple no es un caso sano -- es
    un caso sobre el que no se puede afirmar nada, y decirlo es distinto de
    callarlo.

    NO CIERRA NADA. Devuelve señales; el cierre es otra fase y otra puerta.
    """
    corte_lectura = ahora - timedelta(hours=HORAS_LECTURA_FRESCA)

    casos = Case.objects.filter(
        org=org, resolved_at__isnull=True,
    ).exclude(
        status=CERRADO_EN_DEXTER
    ).exclude(
        external_status_at__isnull=True
    ).exclude(
        external_fetched_at__isnull=True
    ).filter(
        external_fetched_at__gte=corte_lectura
    ).only(
        "id", "name", "status", "priority", "created_at",
        "external_status", "external_status_at", "external_fetched_at",
        "external_fetch_error", "external_ticket_id", "provider",
        #  'external_service_id' VA EN EL .only() Y NO ES UN DETALLE: sin
        #  nombrarlo aqui Django lo deja diferido y cada lectura dispara una
        #  consulta propia. Medido en produccion el 07/10/2026: 19 casos
        #  desincronizados, los 19 con este campo poblado, asi que serian 19
        #  consultas extra por ciclo para un dato que entra en la misma fila.
        #
        #  Es la llave del diagnostico optico: el 'id_servicio' de WispHub, que
        #  es lo unico con lo que se puede preguntar por el equipo del cliente.
        "external_service_id",
    )

    salida = []
    for c in casos:
        if _estado_externo(c) not in CERRADO_EN_PROVEEDOR:
            continue
        #  Una lectura que dejo error anotado no sostiene nada, aunque haya
        #  traido un estado: el estado puede ser el de la lectura anterior.
        if (getattr(c, "external_fetch_error", "") or "").strip():
            continue

        #  UN NUMERO NEGATIVO NO SE MUESTRA, SE DECLARA DESCONOCIDO.
        #
        #  Visto en produccion el 07/10/2026: "(-1 dias desalineados)". Sale de
        #  que 'external_status_at' quedo DESPUES de 'ahora' -- el proveedor
        #  habria cerrado el ticket tres horas despues de que lo leimos, que es
        #  imposible. La causa esta aguas arriba, en como la sincronizacion
        #  interpreta la fecha que devuelve WispHub: su skill ya documenta un
        #  desfase de +5 h en fechas de cierre y formatos DD/MM y MM/DD
        #  mezclados en la misma API.
        #
        #  Aqui no se arregla eso --es la sincronizacion, y no se toca desde
        #  este modulo-- pero SI se deja de afirmar un numero que no se puede
        #  calcular. 'None' y su motivo, nunca un negativo con cara de dato:
        #  es la misma regla que el resto del Supervisor aplica con DESCONOCIDO.
        desfase = ahora - c.external_status_at
        dias_desalineado = desfase.days if desfase.total_seconds() >= 0 else None
        salida.append(Senal(
            tipo=PropuestaSupervisor.CASO_DESINCRONIZADO,
            origen_tipo="case",
            origen_id=str(c.id),
            #  Los siete datos que una persona necesita para decidir, cada uno
            #  nombrando su fuente. No se resume: quien acepta esto cambia el
            #  estado de un caso, y tiene que poder ver contra que.
            evidencia=[
                _observacion("caso", c.id,
                             f"ticket en el proveedor: {c.external_ticket_id or 'sin numero'}",
                             ahora),
                _observacion("caso", c.id, f"caso en el CRM: CS-{str(c.id)[:8]}", ahora),
                _observacion("caso", c.id,
                             f"estado en el proveedor: {c.external_status}", ahora),
                _observacion("caso", c.id, f"estado en el CRM: {c.status}", ahora),
                _observacion("caso", c.id,
                             f"el proveedor lo cerro el "
                             f"{c.external_status_at:%Y-%m-%d %H:%M} UTC "
                             + (f"({dias_desalineado} dias desalineados)"
                                if dias_desalineado is not None else
                                "(no se puede decir desde cuando: esa fecha "
                                "quedo en el futuro respecto de la lectura, "
                                "revisar la sincronizacion)"), ahora),
                _observacion("caso", c.id,
                             f"estado externo leido el "
                             f"{c.external_fetched_at:%Y-%m-%d %H:%M} UTC", ahora),
                _observacion("caso", c.id,
                             f"condicion: cerrado en el proveedor y abierto en "
                             f"el CRM, con lectura de menos de "
                             f"{HORAS_LECTURA_FRESCA} horas", ahora),
            ],
            datos={
                "estado_externo": c.external_status,
                "estado_crm": c.status,
                "ticket_externo": c.external_ticket_id or "",
                "proveedor": c.provider or "",
                "cerrado_en_proveedor_el": c.external_status_at.isoformat(),
                "leido_el": c.external_fetched_at.isoformat(),
                "dias_desalineado": dias_desalineado,
                "nombre": c.name,
                "prioridad_caso": c.priority,
                "clasificacion": OBSERVADO,
                #  LA LLAVE DEL DIAGNOSTICO OPTICO, y va en 'datos' y no en la
                #  evidencia: la evidencia es lo que una persona LEE, y el
                #  'id_servicio' no le dice nada a quien decide. Lo necesita el
                #  codigo, para poder preguntarle a SmartOLT por el equipo.
                #
                #  Cadena vacia cuando el caso no lo tiene, y eso NO se
                #  completa ni se adivina: sin llave no hay diagnostico, y la
                #  propuesta lo dice en vez de quedarse muda.
                "id_servicio": (c.external_service_id or "").strip(),
            },
            #  La condicion, no su magnitud: si la huella llevara los dias, cada
            #  dia seria una condicion nueva y la deduplicacion no serviria de
            #  nada. Se conserva el mismo texto que usaba el camino anterior a
            #  proposito: las propuestas ya emitidas siguen deduplicando contra
            #  esta, y cambiar la huella habria generado 109 duplicados el
            #  primer ciclo.
            huella="cerrado_en_proveedor_abierto_en_crm",
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
        #  operativo.
        #
        #  NIVEL_RECOMENDAR y no OBSERVAR desde M09-R, y el cambio no es
        #  cosmetico: hasta el 25/09/2026 la propuesta pedia "revisar la
        #  sincronizacion", que no es una accion sobre nada -- nadie puede
        #  aceptar "revisar". Ahora propone la accion concreta que corresponde,
        #  que es cerrar el caso en el CRM.
        #
        #  LO QUE 'RECOMENDAR' NO SIGNIFICA: que se ejecute al aceptar. El
        #  cierre necesita atravesar la frontera, y hoy la frontera dice NO por
        #  tres cerrojos medidos -- ver 'ejecutar_propuesta' y el informe de
        #  M09-R. Subir el nivel declara QUE se propone, no habilita nada.
        prioridad, comp = _prioridad(30, {})
        #  EL NIVEL LO DECIDE EL DIAGNOSTICO, y por eso se lee de la señal.
        #
        #  Sin diagnostico que lo habilite, esto sigue siendo una
        #  recomendacion: alguien tiene que mirarla. Con 'cierre_seguro' --el
        #  equipo en linea con señal buena, o caido por falta de energia en la
        #  casa del cliente-- la propuesta declara que pide EJECUTAR una accion
        #  reversible, que es lo que de verdad va a pasar.
        #
        #  Declarar el nivel no concede el permiso: lo concede
        #  'autonomia.puede(org, 3)', que depende de lo que una persona haya
        #  autorizado para esta empresa. Lo que cambia aqui es que la propuesta
        #  DICE lo que pide, en vez de pedir menos de lo que hace.
        _diag = (senal.datos or {}).get("diagnostico_veredicto")
        _nivel = (PropuestaSupervisor.NIVEL_EJECUTAR_REVERSIBLE
                  if _diag == "cierre_seguro"
                  else PropuestaSupervisor.NIVEL_RECOMENDAR)
        return {
            "accion_propuesta": ("Cerrar el caso en Dexter para sincronizar su "
                                 "estado con WispHub"),
            #  EL DESFASE SOLO SE NOMBRA SI SE PUDO CALCULAR. Cuando la fecha de
            #  cierre del proveedor queda en el futuro respecto de la lectura
            #  --visto en produccion el 07/10/2026-- el numero sale negativo, y
            #  "(-1 días desalineados)" no es un dato: es una resta rota con
            #  cara de dato. Se dice que no se sabe y por que, que es lo que el
            #  resto del Supervisor hace con un DESCONOCIDO.
            #
            #  La causa vive en la sincronizacion, no aqui: la skill de WispHub
            #  ya documenta un desfase de +5 h en fechas de cierre y formatos
            #  DD/MM y MM/DD mezclados en la misma API.
            "motivo": (f"WispHub reporta el ticket como cerrado, pero Dexter mantiene "
                       f"el caso abierto. El proveedor lo cerró el "
                       f"{(d.get('cerrado_en_proveedor_el') or '')[:16].replace('T', ' ')} "
                       f"y en el CRM sigue en '{d.get('estado_crm')}'"
                       + (f" ({d.get('dias_desalineado')} días desalineados)."
                          if d.get("dias_desalineado") is not None else
                          ". No se puede decir desde cuándo están desalineados: "
                          "la fecha de cierre del proveedor quedó en el futuro "
                          "respecto de la lectura, lo que apunta a la "
                          "sincronización y no al caso.")
                       + f" Es una "
                       f"inconsistencia entre los dos sistemas: no se afirma "
                       f"incumplimiento de nadie, ni atraso, ni que el problema del "
                       f"cliente esté resuelto -- eso lo sabe el cliente."),
            "prioridad": prioridad,
            "impacto": ("Un caso cerrado afuera y abierto acá infla la cola del CRM y "
                        "hace que los conteos de casos abiertos no describan la operación"),
            "nivel": _nivel,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.CASO_REQUIERE_VISITA:
        #  SIN ESTA RAMA NO HAY PROPUESTA, y es por esto que la pantalla de
        #  Despacho estuvo vacia: el detector venia emitiendo la señal desde
        #  que se escribio, 'analizar' no la conocia, y el ciclo la contaba
        #  como "datos insuficientes" sin crear nada. No hubo error, log ni
        #  aviso -- devolver None es una respuesta legitima para otros tipos,
        #  asi que el hueco se veia igual que el funcionamiento normal.
        #
        #  Lo encontro la guarda que recorre TODOS los tipos de señal
        #  (test_lectura_de_ticket.py, 13/10/2026), no una prueba de este
        #  bloque: una prueba por tipo solo cubre los tipos que alguien se
        #  acordo de escribir, y el que falta es justamente el que nadie vio.
        labor = (d.get("labor_sugerida") or "").strip()
        fuente = (d.get("fuente_de_la_sugerencia") or "").strip()

        #  La labor que llega aca YA ESTA MEDIDA: el detector solo emite la
        #  señal cuando 'veredicto["verificada"]' es verdadero, y descarta las
        #  que salieron del texto del asunto. Por eso la accion puede nombrar
        #  la labor en vez de preguntar cual es.
        #
        #  La prioridad sale de a QUIEN deja esperando cada labor, no de la
        #  antiguedad: un correctivo es un cliente que hoy no tiene servicio;
        #  una instalacion es alguien que todavia no lo tiene y lo sabe.
        #
        #  Se importa aca y no arriba por lo mismo que en el detector: el
        #  modulo de clasificacion arrastra el lazo con WispHub, y 'analizar'
        #  tiene que poder juzgar sin base de datos ni red.
        from operaciones import clasificacion_de_trabajo as clf

        base = {clf.CORRECTIVO: 60, clf.TRABAJOS: 45}.get(labor, 35)
        prioridad, comp = _prioridad(base, {})

        return {
            "accion_propuesta": (f"Despachar una visita de {labor}"
                                 if labor else "Despachar una visita"),
            "motivo": (
                f"El caso sigue abierto y la clasificación medida dice que se "
                f"resuelve con una visita de {labor or 'campo'}"
                + (f" (lo determinó {fuente})." if fuente else ".")
                + " La labor está verificada contra el dato del proveedor, no"
                  " deducida del asunto del ticket. Lo que no se decide acá es"
                  " cuándo ni con quién: eso lo arma el reparto del día."),
            "prioridad": prioridad,
            "impacto": ("Un caso que necesita visita y no entró a ninguna"
                        " programación espera sin que nadie lo esté mirando"),
            #  RECOMENDAR, nunca mas: aceptar esto manda a una persona a
            #  manejar hasta una casa. Es la frontera que el propio detector
            #  dejo escrita cuando descarto las labores no verificadas.
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
            "componentes_prioridad": comp,
        }

    if senal.tipo == PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO:
        #  SIN ESTA RAMA NO HAY PROPUESTA. Medido el 13/10/2026, el dia que
        #  esto salio: el detector emitio 750 señales y no se creo NI UNA
        #  propuesta. 'analizar' devuelve None para un tipo que no conoce, y el
        #  ciclo lo cuenta como "datos insuficientes" sin crear nada -- en
        #  silencio, porque es una respuesta legitima para otros casos.
        #
        #  La prioridad sube con los dias abiertos y da un salto a los 5, que
        #  es el limite que fijo el cliente: "un ticket no puede estar dos
        #  semanas, maximo 5 dias".
        dias = int(d.get("dias_abierto") or 0)
        prioridad, comp = _prioridad(
            40, {"antiguedad": min(dias, 30),
                 "sin_movimiento": 20 if d.get("sin_movimiento") else 0})

        hipotesis = (d.get("diagnostico_hipotesis") or "").strip()
        confianza = (d.get("diagnostico_confianza") or "").strip()
        labor = (d.get("labor") or "").strip()
        verificada = bool(d.get("labor_verificada"))

        #  LO QUE EL SUPERVISOR PROPONE, con sus palabras, y recien despues
        #  los respaldos. Hasta el 13/10/2026 esta rama solo sabia nombrar la
        #  LABOR --y cuando no habia labor caia en "Decidir qué se hace con
        #  este ticket", que es devolverle la pregunta a quien la hizo--.
        #
        #  La recomendacion del modelo no es palabra suelta: 'cerebro.validar'
        #  descarta la que no tenga ningun hecho detras, asi que para llegar
        #  aca hubo que consultar algo.
        sugerida = (d.get("accion_sugerida") or "").strip()
        if sugerida:
            #  RECORTADA A UNA LINEA, que es lo que el campo es:
            #  'accion_propuesta' es CharField(255) --"Qué recomienda, en una
            #  línea legible"-- y el modelo escribe parrafos.
            #
            #  MEDIDO EN PRODUCCION el 14/10/2026: ocho de treinta y ocho
            #  lecturas se perdieron con "value too long for type character
            #  varying(255)", y como la base rechaza el guardado ENTERO, con la
            #  accion se iba tambien la evidencia. El trabajo se hacia, se
            #  pagaba el modelo, y no quedaba nada.
            #
            #  El texto completo NO se pierde: va al motivo, que es TextField.
            accion = _en_una_linea(sugerida)
        elif labor:
            accion = (f"Confirmar que este ticket corresponde a {labor} "
                      f"y despacharlo" if verificada else
                      f"Decidir si este ticket corresponde a {labor}: lo dice "
                      f"el texto del reclamo, no una medición")
        else:
            accion = "Decidir qué se hace con este ticket, que sigue abierto"

        return {
            "accion_propuesta": accion,
            #  LO LEIDO VA PRIMERO, LA ANTIGÜEDAD DESPUES  --  13/10/2026
            #  ----------------------------------------------------------
            #  Estaba al reves, y el efecto lo dijo el cliente mirando la
            #  pantalla: "no esta analizando la descripcion del ticket, solo
            #  esta tomando el tiempo de creacion". El diagnostico estaba --se
            #  veia tres bloques mas abajo, con los dBm y todo-- pero el
            #  titular abria con los dias, y un titular que habla de fechas
            #  dice que se miro una fecha.
            #
            #  Los dias siguen estando: son el motivo de que esto sea urgente.
            #  Lo que cambia es cual de las dos cosas se lee primero.
            "motivo": (
                (f"Leyendo el reclamo: {hipotesis}"
                 + (f" (confianza {confianza})." if confianza else ".")
                 if hipotesis else
                 "Se leyó el reclamo y no alcanza para una hipótesis.")
                + f" El ticket sigue abierto en WispHub hace {dias} días"
                + (" y pasó el límite de 5 días sin movimiento."
                   if d.get("sin_movimiento") else ".")
                + (f" PROPONE: {sugerida}" if sugerida else "")
                + " Esto sale de LEER el texto, no de medir el equipo: por eso"
                  " lo decide una persona."),
            "prioridad": prioridad,
            "impacto": ("Un ticket que lleva días abierto sin que nadie diga qué"
                        " le pasa al cliente es tiempo que corre sin decisión"),
            #  RECOMENDAR, nunca mas. Lo que sale de un texto no ejecuta nada:
            #  es la regla que 'CASO_REQUIERE_VISITA' ya dejo escrita para el
            #  mismo riesgo -- mandar una cuadrilla por lo que decia una frase.
            "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
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


#  =============================================================================
#   FASE 2 · EL CICLO PUEDE RAZONAR  --  y por ahora no lo hace
#  =============================================================================
#
#  LA BANDERA ARRANCA APAGADA, Y ESO ES EL ENTREGABLE
#  --------------------------------------------------
#  Apagada, 'enriquecer' devuelve el analisis TAL CUAL y el ciclo es byte por
#  byte el de siempre. Eso se puede afirmar de la forma mas fuerte que hay:
#  comparando la propuesta campo por campo contra la de referencia
#  ('test_cerebro_ciclo::test_1').
#
#  POR QUE EN CODIGO Y NO EN 'tenant_config'
#  -----------------------------------------
#  Porque encender el razonamiento del ciclo no es una regla de negocio de una
#  empresa: es una decision de operacion sobre cuanto se gasta y cuanto se
#  confia. El proyecto ya tomo esa distincion para el interruptor de autonomia
#  y para RELOJ_HABILITADO (CLAUDE.md §8): la config del tenant dice QUE hacer;
#  si un proceso debe estar razonando es decision de operacion. Y asi
#  encenderlo es un commit revisado, no un UPDATE.
#
#  LO QUE EL CEREBRO NO PUEDE MOVER, Y DONDE VIVE ESA GARANTIA
#  ----------------------------------------------------------
#  No vive aqui: vive en 'cerebro.analisis_de_veredicto', que arma la salida
#  copiando el analisis y sobreescribiendo SOLO 'motivo' e 'impacto'. Esta
#  funcion no decide que se puede tocar -- solo decide SI se llama.
CEREBRO_EN_EL_CICLO = False

#  LA SEGUNDA BANDERA  --  registrar y enriquecer son dos permisos distintos
#  -------------------------------------------------------------------------
#  Con una sola bandera habia dos estados: el cerebro participa o no participa.
#  Faltaba el del medio, que es justamente la etapa de observacion del plan --
#  el cerebro razonando sobre señales reales, con su criterio guardado y sin
#  que nada de eso alcance a la propuesta.
#
#  AVISO PARA QUIEN EDITE ESTE ARCHIVO: 'test_m03e4' y 'test_m03e5' afirman que
#  cierta palabra de ocho letras --la que empieza por "sec" y nombra un orden
#  de pasos-- no aparece en el fuente de este modulo. La afirmacion es sobre el
#  TEXTO, no sobre la conducta, asi que la caza incluso dentro de otra palabra
#  mas larga que la contenga. Es un defecto conocido de esas dos guardas;
#  arreglarlas es trabajo de M03 y no de aqui, de modo que lo que se cambia es
#  la redaccion propia. Ya mordio cuatro veces: no gastes la quinta.
#
#      CEREBRO_REGISTRA   CEREBRO_EN_EL_CICLO   estado
#      ----------------   -------------------   ------------------------------
#      False              False                 apagado  (el de hoy)
#      True               False                 solo registra
#      True               True                  enriquece, y deja constancia
#
#  LA CUARTA COMBINACION NO EXISTE, Y SE IMPIDE EN CODIGO: enriquecer sin
#  dejar constancia seria exactamente el hueco que esta pieza vino a cerrar --
#  un cerebro influyendo en propuestas sin que se pueda comparar despues con
#  que criterio lo hizo. Ver '_el_cerebro_corre()'.
#  ENCENDIDA el 07/10/2026, por decision explicita. Lo que habilita es que el
#  cerebro razone sobre cada señal del ciclo y GUARDE su conclusion -- nada mas.
#  La propuesta sigue saliendo del analisis deterministico, intacta, y eso lo
#  afirma 'test_2b' campo por campo.
#
#  POR QUE SE ENCIENDE ESTA Y NO LA OTRA
#  -------------------------------------
#  Porque sin datos no hay con que decidir la otra. Esta posicion es la etapa de
#  observacion: produce la comparacion --que concluyo el cerebro contra que
#  concluyo la regla-- que es la unica evidencia con la que se puede justificar
#  despues subir el alcance. Encender las dos juntas se habria quedado sin la
#  medicion que la segunda necesita.
#
#  LO QUE ESTO CUESTA, Y NO ESTA MEDIDO TODAVIA
#  --------------------------------------------
#  Una llamada al modelo por señal detectada, de hasta 'VUELTAS_MAXIMAS' vueltas.
#  Un ciclo con 14 señales son 14 razonamientos. El numero real --cuantas señales
#  por ciclo, cuantos segundos, cuanto consumo-- sale de los primeros dias con
#  esto encendido, y es justamente lo que falta para decidir si se razona sobre
#  todas las señales o solo sobre las ambiguas.
#
#  Si el modelo no contesta, el ciclo sigue igual: 'razonar_sobre' degrada y la
#  propuesta sale correcta. Lo que se pierde es la constancia, no el trabajo.
CEREBRO_REGISTRA = True




# =============================================================================
#  EL PRESUPUESTO DE RAZONAMIENTO  --  un ciclo no puede tardar lo que quiera
# =============================================================================
#
#  EL DEFECTO QUE CIERRA, medido el 07/10/2026
#  -------------------------------------------
#  Al encender 'CEREBRO_REGISTRA' el ciclo paso a llamar al modelo UNA VEZ POR
#  SEÑAL, sin tope. Y el ciclo se dispara desde un boton: es una peticion HTTP
#  sincrona, con una persona esperando del otro lado.
#
#  La cuenta del peor caso: 'VUELTAS_MAXIMAS' = 3 llamadas por señal, cada una
#  con 'SEGUNDOS_TIMEOUT' = 150 s. Son 450 s por señal. Con diez señales nuevas
#  el ciclo tarda una hora y la pantalla se queda en "Analizando operacion..."
#  hasta que algo corta la conexion -- que fue exactamente lo que paso.
#
#  POR QUE DOS TOPES Y NO UNO
#  --------------------------
#  Un tope por CANTIDAD solo no alcanza: cinco señales que tarden lo maximo son
#  37 minutos. Un tope por RELOJ solo tampoco: con el modelo rapido dejaria
#  pasar cincuenta razonamientos y el costo se dispara sin que nadie lo vea.
#
#  Los dos juntos acotan las dos cosas que importan --lo que espera una persona
#  y lo que se gasta-- y cualquiera de los dos que se agote detiene al cerebro
#  sin detener el ciclo: las señales que siguen se procesan igual, solo que sin
#  interpretacion. Eso se CUENTA y sale en el resumen, porque un cerebro que
#  dejo de razonar a la mitad y no lo dice es peor que uno apagado.
#
#  ESTOS NUMEROS SON PROVISIONALES, y a proposito. El tope de verdad sale de
#  medir cuantas señales produce un ciclo real y cuanto tarda cada razonamiento
#  -- que es justo lo que el registro esta empezando a producir. Hasta tener ese
#  dato, mejor un tope conservador que una pantalla colgada.
TOPE_RAZONAMIENTOS_POR_CICLO = 5
SEGUNDOS_MAXIMOS_DE_RAZONAMIENTO = 90


def presupuesto(tope: int = TOPE_RAZONAMIENTOS_POR_CICLO,
                segundos: int = SEGUNDOS_MAXIMOS_DE_RAZONAMIENTO,
                ahora=None) -> dict:
    """
    Un presupuesto para una corrida: cuantos razonamientos y hasta cuando.

    Se crea UNO por corrida y se comparte entre los caminos que llaman al
    cerebro --la deteccion y el seguimiento-- porque lo que hay que acotar es lo
    que espera la persona, y eso no se parte por modulo.
    """
    desde = ahora or timezone.now()
    return {
        "restantes": max(0, int(tope)),
        "hasta": desde + timedelta(seconds=max(0, int(segundos))),
        "usados": 0,
        "omitidos": 0,
    }


def _hay_presupuesto(p) -> bool:
    """Si todavia se puede razonar. Sin presupuesto, no se acota nada."""
    if p is None:
        return True
    if p["restantes"] <= 0 or timezone.now() >= p["hasta"]:
        p["omitidos"] += 1
        return False
    return True


def _gastar(p) -> None:
    if p is not None:
        p["restantes"] -= 1
        p["usados"] += 1

def _el_cerebro_corre() -> bool:
    """
    Si hay que llamar al cerebro, en cualquiera de los dos modos.

    'CEREBRO_EN_EL_CICLO' implica registrar. No es una cortesia: es la
    invariante que impide la cuarta combinacion de la tabla de arriba.
    """
    return bool(CEREBRO_REGISTRA or CEREBRO_EN_EL_CICLO)


class Aporte:
    """
    Lo que el cerebro produjo, en transito entre razonar y guardar.

    POR QUE HACE FALTA UN OBJETO Y NO ALCANZA UNA FUNCION
    -----------------------------------------------------
    La constancia tiene que apuntar a la propuesta, y cuando el cerebro razona
    LA PROPUESTA TODAVIA NO EXISTE: en '_correr_ciclo' el razonamiento va
    justo antes de 'registrar_propuesta', porque es el unico punto donde la
    prioridad y el nivel ya estan fijados y el cerebro no los puede mover.

    Asi que el ciclo razona, crea la propuesta, y recien entonces deja la
    fila. Este objeto es el traspaso entre esos dos momentos, y guarda el
    analisis PREVIO porque despues del enriquecimiento ya no se puede
    recuperar.
    """

    __slots__ = ("analisis", "veredicto", "previo", "enriquecio")

    def __init__(self, analisis, veredicto=None, previo=None, enriquecio=False):
        self.analisis = analisis
        self.veredicto = veredicto
        self.previo = previo if previo is not None else {}
        self.enriquecio = enriquecio

    def dejar_constancia(self, org, *, propuesta=None, situacion=None,
                         ahora=None):
        """
        Guarda el razonamiento. Devuelve la fila, o None si no habia nada.

        Nunca levanta: 'razonamiento.registrar' atrapa todo por el mismo motivo
        que 'enriquecer' -- el ciclo no puede caerse por su bitacora.
        """
        if self.veredicto is None or not CEREBRO_REGISTRA:
            return None
        from operaciones import razonamiento
        from operaciones.razonamiento_modelos import FuenteRazonamiento
        return razonamiento.registrar(
            org, self.veredicto,
            fuente=FuenteRazonamiento.CICLO,
            propuesta=propuesta, situacion=situacion,
            analisis_previo=self.previo,
            enriquecio=self.enriquecio, ahora=ahora)


def razonar_sobre(org, senal: "Senal", analisis: dict, *, ahora=None,
                  presupuesto=None) -> Aporte:
    """
    Llama al cerebro y devuelve el aporte, sin guardar nada todavia.

    Es el camino completo: 'enriquecer()' es su envoltorio de compatibilidad y
    se queda con la mitad --transforma el analisis y descarta el veredicto--.
    Lo que esta funcion agrega es conservar el veredicto y el ESTADO PREVIO,
    que son las dos cosas que la constancia necesita.

    EL PREVIO SE COPIA ANTES DE TOCAR NADA, y por eso es una copia y no la
    referencia: si quedara guardado el analisis ya enriquecido, la comparacion
    seria contra si misma y daria coincidencia siempre. 'test_razonamiento'
    afirma eso sobre el efecto, no sobre la presencia de la copia.
    """
    if not _el_cerebro_corre():
        return Aporte(analisis)
    #  El presupuesto se consulta ANTES de armar el contexto: armarlo tambien
    #  cuesta consultas, y gastarlas para despues no preguntar no tiene sentido.
    if not _hay_presupuesto(presupuesto):
        return Aporte(analisis)
    _gastar(presupuesto)

    previo = dict(analisis) if isinstance(analisis, dict) else {}

    import json
    from operaciones import cerebro
    try:
        contexto = cerebro.contexto_para(org)

        #  LO QUE YA PASO CON ESTA MISMA CONDICION.
        #
        #  Sin esto el cerebro razona sobre una señal AISLADA y cada ciclo
        #  empieza de cero: reacciona, que es lo que hace un motor. Con esto
        #  retoma un hilo --"ya propuse esto, lo aceptaron, no funciono"--, que
        #  es lo que hace un agente. La llave es 'huella_condicion', que ya
        #  existia para deduplicar; lo que faltaba era leerla.
        #
        #  Vacio cuando es la primera vez, y el vacio tambien dice algo:
        #  condicion nueva no es condicion sana.
        #  getattr y no 'senal.huella': el except de abajo es amplio, asi que
        #  un atributo ausente desactivaria el cerebro EN SILENCIO. Una Senal
        #  real siempre la trae; esto cubre a cualquier otra cosa que llegue.
        antes = cerebro.antecedentes_de(org, getattr(senal, "huella", ""))
        bloque_antes = f"\n\n== ANTECEDENTES ==\n{antes}" if antes else ""

        veredicto = cerebro.concluir(
            org,
            instrucciones=_instrucciones_del_ciclo(org),
            entrada=(f"{contexto}{bloque_antes}\n\n== LA SEÑAL DETECTADA ==\n"
                     f"tipo: {senal.tipo}\n"
                     f"evidencia: {json.dumps(senal.evidencia, ensure_ascii=False, default=str)[:1500]}\n"
                     f"lo que la regla concluyo: {analisis.get('motivo', '')}"))
    except Exception:                                        # noqa: BLE001
        #  Mismo criterio que 'enriquecer': degradar al ciclo de siempre.
        return Aporte(analisis, previo=previo)

    if not CEREBRO_EN_EL_CICLO:
        #  Solo registra: el analisis sale INTACTO. Se devuelve el mismo objeto
        #  a proposito -- que no haya ni una copia por el medio es lo que hace
        #  que 'test_2' pueda afirmar identidad y no solo igualdad.
        return Aporte(analisis, veredicto=veredicto, previo=previo,
                      enriquecio=False)

    return Aporte(cerebro.analisis_de_veredicto(veredicto, analisis),
                  veredicto=veredicto, previo=previo, enriquecio=True)


def enriquecer(org, senal: "Senal", analisis: dict, *, ahora=None) -> dict:
    """
    Le pide al cerebro que aporte interpretacion sobre una señal ya detectada.

    NO DEJA CONSTANCIA, y eso es deliberado: la fila tiene que apuntar a la
    propuesta, que en este punto todavia no existe. Quien necesite las dos
    cosas usa 'razonar_sobre()' y despues 'Aporte.dejar_constancia()', que es
    lo que hace '_correr_ciclo'. Esta firma se mantiene porque 23 pruebas de
    'test_cerebro_ciclo' la ejercitan y no se tocan para agregar una
    funcionalidad nueva.

    EL DETECTOR SIGUE DECIDIENDO QUE HAY. Esta funcion no detecta, no descarta
    y no cambia la accion propuesta: recibe un analisis deterministico que ya
    es correcto y le agrega lo que el cerebro vio. Si el cerebro no aporta
    nada, el analisis sale igual.

    NUNCA LEVANTA, Y ESA ES SU PROPIEDAD MAS IMPORTANTE
    ---------------------------------------------------
    El ciclo no puede depender del cerebro para registrar una propuesta. Un
    modelo caido, un timeout, una respuesta que no es JSON o un veredicto que
    no cierra terminan todos igual: se devuelve el analisis
    deterministico. La propuesta sale igual, y sale correcta.

    Esa garantia ahora vive en 'razonar_sobre', que es quien atrapa. Aqui solo
    se descarta el veredicto y se devuelve el analisis -- que es, exactamente,
    lo que esta funcion siempre hizo.
    """
    return razonar_sobre(org, senal, analisis, ahora=ahora).analisis


#  Lo que el ciclo le pide al cerebro. NO es la identidad del chat: alla hay una
#  persona preguntando y aca hay una señal ya detectada, asi que lo que se pide
#  es distinto -- interpretar, no conversar.
def _instrucciones_del_ciclo(org) -> str:
    """
    El nucleo del ciclo mas el estilo editable de la empresa.

    Mismo corte que en el chat: '_INSTRUCCIONES_DEL_CICLO' queda en codigo
    porque contiene las garantias, y lo que se edita desde la interfaz es como
    se REDACTA el motivo -- que es presentacion. Si nadie edito, el estilo por
    defecto deja el prompt practicamente igual al de antes.

    Nunca levanta: 'estilo.vigente' devuelve el texto por defecto si la consulta
    falla, por el mismo motivo que el resto de este camino degrada en vez de
    romperse.
    """
    from operaciones import estilo as svc_estilo
    from operaciones.estilo_modelos import AmbitoEstilo
    separador = "\n\n"
    return (_INSTRUCCIONES_DEL_CICLO + separador
            + svc_estilo.vigente(org, AmbitoEstilo.CICLO))


_INSTRUCCIONES_DEL_CICLO = """\
Sos el Supervisor NOC IA de un ISP. Una REGLA DETERMINISTICA ya detectó una
señal y ya escribió una recomendación; vos no la reemplazás.

Tu trabajo es lo que la regla no puede hacer: mirar el resto de la operación y
decir si esta señal se entiende distinto en contexto. Correlacioná con lo que
haya alrededor, estimá el riesgo, y si tenés una causa POSIBLE decila como
hipótesis con su confianza.

Consultá las herramientas antes de afirmar cualquier cosa. Un hecho que no salga
de una herramienta no es un hecho, y se va a descartar.

Si no tenés nada que agregar, decilo en "falta" y no inventes una
interpretación para llenar el espacio. Una propuesta sin tu aporte ya es
correcta; una con un aporte inventado es peor que sin él.

No propongas ejecutar nada: no podés, y decir que lo hiciste sería mentir.
"""


def correr_ciclo(org, ahora=None, *, desatendido: bool = False) -> dict:
    """
    Una pasada completa de Shadow Mode. Devuelve el resumen de lo que pasó.

    'desatendido' lo pone la corrida del reloj ('operaciones/tasks.py'), donde
    no hay nadie esperando una respuesta. Lo UNICO que cambia es cuantos
    equipos alcanza a diagnosticar antes de cortar --ver los dos topes en
    'diagnostico_optico'-- y NO es un permiso: las tres puertas del cierre
    siguen iguales, y una corrida desatendida que diagnostica quince equipos
    puede cerrar cero.

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
        resumen = _correr_ciclo(org, ahora)

    #  ===================================================================
    #   FUERA DE LA TRANSACCION: lo que habla con sistemas externos
    #  ===================================================================
    #  NINGUNA TRANSACCION ABIERTA MIENTRAS SE ESPERA A UN TERCERO. Es una
    #  decision congelada del proyecto, y la rompi (08/10/2026): el diagnostico
    #  optico, la consulta del interruptor y el cierre quedaron DENTRO del
    #  'atomic' de arriba, con la fila de la organizacion bloqueada.
    #
    #  El sintoma fue 'OperationalError: the connection is closed' a mitad del
    #  ciclo. Tres diagnosticos de ~10 s mas las llamadas al motor dejaban la
    #  transaccion abierta casi un minuto esperando a terceros, y la conexion
    #  se caia. No cerraba nada y tardaba una eternidad, las dos cosas por el
    #  mismo motivo.
    #
    #  Aqui afuera cada escritura abre su propia transaccion corta:
    #  'cierre_de_caso.cerrar' ya estaba escrito asi --valida con la fila
    #  bloqueada, suelta el lock, y RECIEN AHI llama por red-- y ese patron es
    #  el que hay que respetar, no esquivar envolviendolo en otro atomic.
    #
    #  LO QUE SE PIERDE, Y ESTA BIEN QUE SE PIERDA: el todo-o-nada. Si el
    #  diagnostico falla a la mitad, las propuestas de arriba YA estan
    #  guardadas. Es lo correcto -- esas propuestas son trabajo valido, y
    #  tirarlas porque SmartOLT no contesto seria perder lo que si se pudo
    #  hacer. Un cierre que no ocurrio se reintenta en el ciclo siguiente.
    #  CADA FASE EN SU PROPIO 'try'  --  14/10/2026
    #  --------------------------------------------
    #  Estaban encadenadas: si la primera levantaba, la segunda NO CORRIA. Y el
    #  sintoma no se parecia a la causa -- lo que se veia era "se crearon 38
    #  propuestas y no se leyo ninguna", que apunta a la lectura, no al cierre
    #  de desincronizados que fue el que se cayo.
    #
    #  Son fases INDEPENDIENTES: cerrar lo que el proveedor ya cerro no tiene
    #  nada que ver con leer lo que sigue abierto. Que una se caiga no es
    #  motivo para no hacer la otra, y las propuestas de arriba ya estan
    #  guardadas igual.
    #
    #  SE REGISTRA EL FALLO CON SU FASE. Desde que el ciclo se encola, el
    #  resumen ya no vuelve a la pantalla: si una fase se cae en silencio, no
    #  queda rastro en ningun lado y solo se ve el hueco que dejo.
    for nombre, fase in (
        ("cierre de desincronizados",
         lambda: _atender_desincronizados(org, ahora, desatendido=desatendido)),
        #  LA LECTURA VA SEGUNDA a proposito: cerrar lo que ya esta resuelto es
        #  mas barato y mas seguro que leer lo que sigue abierto, y si el
        #  presupuesto de la vuelta se agota, que se agote en lo segundo.
        ("lectura de tickets abiertos",
         lambda: _leer_tickets_abiertos(org, ahora,
                                        desatendido=desatendido)),
        #  EL PASO A DESPACHO ES SU PROPIA FASE  --  14/10/2026, por la tarde
        #  ------------------------------------------------------------------
        #  Nacio DENTRO de la fase de lectura, y ahi estaba muerto: esa fase
        #  arranca con "if not candidatas: return informe", y una propuesta que
        #  YA tiene su lectura no es candidata a leerse. Con las 80 propuestas
        #  del dia ya leidas, el ciclo salia por ese return y el paso no corria
        #  nunca.
        #
        #  MEDIDO: tras el despliegue de las 21:55 UTC el ciclo registro 5
        #  razonamientos y CERO lecturas de ticket, y ninguna propuesta paso.
        #  El sintoma que vio el cliente fue "ejecute el ciclo y no hizo nada",
        #  sin un solo error en ningun log.
        #
        #  Es la tercera vez en el dia que el mismo error aparece con otra
        #  cara: poner la decision en una rama a la que los casos que importan
        #  no llegan. Antes fue la cola de los desincronizados ya
        #  diagnosticados, y despues la exigencia de "diagnostico_leido" en
        #  esta misma vuelta. La forma de cerrarlo no es mover el "if": es que
        #  el paso NO DEPENDA de que se haya leido algo, y consulte las
        #  propuestas pendientes por su cuenta.
        #
        #  LA MEDICION DE LAS FALLAS ES SU PROPIA FASE  --  16/10/2026, Fase 3
        #  -----------------------------------------------------------------
        #  Y no el final de la lectura: '_leer_tickets_abiertos' sale temprano
        #  cuando no hay nada nuevo que leer, que es justo cuando las fallas
        #  viejas, ya leidas, necesitan medirse. Va antes del paso porque el
        #  paso decide la regla 1 con lo que esta fase escribe.
        ("medicion de fallas",
         lambda: _medir_fallas_pendientes(org, desatendido=desatendido)),
        #  VA ULTIMA porque usa lo que las anteriores escribieron: una lectura
        #  y una medicion hechas en esta vuelta ya estan guardadas cuando esto
        #  corre.
        ("paso a Despacho",
         lambda: _pasar_a_despacho_los_que_las_reglas_habiliten(org, ahora)),
        #  DESPUES del paso: un caso que paso en esta vuelta no espera a la
        #  siguiente para que su alerta de caso antiguo se retire.
        ("retiro de alertas de casos en Despacho",
         lambda: {"alertas_retiradas_en_despacho":
                  retirar_alertas_de_casos_en_despacho(org, ahora)}),
        #  LA JORNADA DEL DIA VA ULTIMA  --  17/10/2026: cuenta la cola de
        #  Despacho como quedo despues del paso de ESTA vuelta. Sin la tarea
        #  delegada solo deja en el log lo que armaria (la sombra).
        ("armado de la jornada del dia",
         lambda: _armar_la_jornada_del_dia(org, ahora)),
    ):
        try:
            resumen.update(fase())
        except Exception as e:                               # noqa: BLE001
            logger.exception("Supervisor: fallo la fase '%s'", nombre)
            resumen.setdefault("fases_que_fallaron", []).append(
                {"fase": nombre, "error": type(e).__name__})

    return resumen


def _armar_la_jornada_del_dia(org, ahora) -> dict:
    """La fase de `armado_de_jornadas`, importada recien al correr: ese modulo
    trae los de Cuadrillas, que este no necesita para nada mas."""
    from operaciones import armado_de_jornadas
    return armado_de_jornadas.armar_las_jornadas_del_dia(org, ahora)


#:  Cuantas propuestas sin señal se traen por vuelta para releer. El tope real
#:  del gasto lo sigue poniendo 'diagnosticar', que corta en sus propias
#:  lecturas por corrida; esto solo evita construir una lista enorme.
TOPE_RELECTURA_SIN_SENAL = 60


def _las_que_esperan_relectura(org, senales):
    """
    Propuestas que necesitan releerse y que HOY no produjeron señal.

    LA CUARTA VEZ DEL MISMO ERROR  --  15/10/2026
    ---------------------------------------------
    '_leer_tickets_abiertos' recorre 'for s in senales', asi que solo pregunta
    por los tickets que 'detectar' trajo en ESTA vuelta. Una propuesta cuya
    lectura quedo incompleta --el grupo vino vacio-- necesita releerse, pero si
    el ticket no vuelve a generar señal, nadie le hace la pregunta nunca.

    MEDIDO ese dia: 15 de 44 propuestas con el grupo en blanco, corregidas las
    instrucciones del modelo, y el ciclo del boton terminando en 1,1 segundos
    con 'tickets leidos=None'. Las 35 señales de la vuelta eran todas
    'caso_abierto_antiguo'; ninguna tocaba a esas 15.

    Es la misma forma que ya costo tres veces --la decision puesta en una rama
    a la que los casos que importan no llegan-- y se cierra igual que la
    tercera: que la fase CONSULTE las propuestas pendientes por su cuenta en
    vez de esperar que una señal se las traiga.

    NO SE DUPLICA lo que ya vino por señal: se excluye por 'origen_id', que es
    la misma llave con la que 'diagnosticar' busca.
    """
    from operaciones import diagnostico_de_ticket as dxt

    ya = {str(getattr(s, "origen_id", "")) for s in senales}
    pendientes = (PropuestaSupervisor.objects
                  .filter(org=org,
                          tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
                          estado=PropuestaSupervisor.PROPUESTA,
                          origen_tipo="case")
                  .order_by("created_at")[:TOPE_RELECTURA_SIN_SENAL])

    extra = []
    for p in pendientes:
        if str(p.origen_id) in ya:
            continue
        #  Los mismos dos criterios que el bucle de abajo, y a proposito: si
        #  alguna vez se agrega un tercero, que falle en los dos lugares a la
        #  vez en vez de divergir en silencio.
        if dxt.le_falta_lectura(p) or dxt.le_falta_el_grupo(p):
            extra.append(_SinSenal(p))
    return extra


def _leer_tickets_abiertos(org, ahora, *,
                           desatendido: bool = False) -> dict:
    """
    Lee los tickets que siguen abiertos y deja el diagnostico en su propuesta.

    MISMA FORMA QUE '_atender_desincronizados', y no por simetria: las dos
    fases hacen lo mismo --tomar señales ya propuestas, preguntarle a algo de
    afuera, y escribir el resultado en la propuesta-- y resolverlo distinto
    daria dos lugares donde buscar el mismo error.

    NO LEVANTA: un ticket que no se pudo leer es un resultado posible del
    ciclo, y el resto ya termino y esta guardado.
    """
    from operaciones import diagnostico_de_ticket as dxt

    informe = {"tickets": {}}

    senales = [s for s in detectar(org, ahora)
               if s.tipo == PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO]
    #  Y LAS QUE NO PRODUJERON SEÑAL HOY pero esperan relectura: ver
    #  '_las_que_esperan_relectura'. Va ANTES del return temprano, que es
    #  justo por donde se escapaban.
    senales = senales + _las_que_esperan_relectura(org, senales)
    if not senales:
        return informe

    #  SOLO LAS QUE TODAVIA NO SE LEYERON. Una propuesta que ya tiene su
    #  diagnostico no se vuelve a pagar: fue lo primero que se pidio -- "debe
    #  guardar un registro de que ya reviso tales ticket para que no le corra
    #  nuevamente el diagnostico".
    #  TRES COLAS, Y EL ORDEN IMPORTA porque el tope de la vuelta corta donde
    #  llegue. Lo primero es lo que nadie miro nunca; lo ultimo, lo que ya se
    #  miro y solo necesita que el resumen se ponga al dia.
    pendientes = {}
    sin_leer = []        # 1 · ningun diagnostico todavia
    al_dia = []          # 2 · el resumen no refleja lo que ya se leyo
    for s in senales:
        #  SE BUSCA POR CASO, NO POR HUELLA  --  14/10/2026
        #  ------------------------------------------------
        #  '_ya_propuesta' pregunta "¿ya propuse esta MISMA CONDICION?" y usa la
        #  huella, que incluye datos que cambian --los dias abiertos, entre
        #  otros--. Para no repetir una pregunta ya decidida esta perfecto.
        #
        #  Para GUARDAR la lectura es la pregunta equivocada: lo que hace falta
        #  es "¿que propuesta viva tiene ESTE CASO?", y eso lo contesta
        #  '_propuesta_vigente_de', que busca por origen.
        #
        #  EL AGUJERO QUE DEJO, medido en produccion esa madrugada: cuando la
        #  huella cambiaba, la señal se iba por la rama de "sin propuesta", se
        #  diagnosticaba igual --pagando la consulta al modelo-- y despues el
        #  guardado no la encontraba en 'pendientes' y tiraba el resultado.
        #
        #      50  lecturas registradas
        #       3  propuestas que de verdad quedaron con su lectura
        #       0  propuestas cuya accion cambio
        #
        #  Y encima se repetia en cada vuelta: sin evidencia guardada,
        #  'le_falta_lectura' seguia diciendo que si, y la misma propuesta se
        #  leia una y otra vez.
        p = _propuesta_vigente_de(org, s)
        if p is None:
            if not _ya_propuesta(org, s):
                #  Ninguna propuesta viva y ninguna decidida: nace ahora. La
                #  registra el ciclo en su pasada normal.
                sin_leer.append(s)
            #  Si hay una DECIDIDA (aceptada, rechazada), no se toca: una
            #  persona ya resolvio, y releerla gastaria la vuelta.
            continue
        #  O LE FALTA EL GRUPO, que es una lectura incompleta para el paso
        #  a Despacho. Son dos criterios y no uno: ver la nota de
        #  'le_falta_lectura', que distingue los tres casos.
        if dxt.le_falta_lectura(p) or dxt.le_falta_el_grupo(p):
            #  'str()' en los dos lados: 'diagnostico_de_ticket' busca con
            #  'str(senal.origen_id)' y aca se guardaba crudo. Si alguna vez
            #  'origen_id' deja de ser texto, uno encuentra y el otro no --
            #  y el sintoma seria este mismo: la lectura se hace y se pierde.
            pendientes[str(s.origen_id)] = p
            sin_leer.append(s)
        elif dxt.el_juicio_ignora_la_lectura(p):
            #  YA SE LEYO Y EL RESUMEN NO LO DICE  --  13/10/2026
            #  --------------------------------------------------
            #  Las 52 propuestas vivas ese dia tenian la lectura guardada como
            #  evidencia y el resumen escrito ANTES de leerla, diciendo que no
            #  alcanzaba para una hipotesis con la hipotesis tres bloques mas
            #  abajo. 'le_falta_lectura' dice que no les falta nada, asi que
            #  sin esta rama se quedaban con el texto viejo para siempre.
            #
            #  Se relee en vez de recomponer el texto desde la evidencia: el
            #  veredicto viaja en los datos de la señal a proposito, y sacarlo
            #  del texto seria lo que '_anotar' advierte que no se haga. La
            #  relectura ademas AGREGA una observacion, que es lo que se pidio
            #  --ver el flujo del seguimiento-- en vez de tapar la anterior.
            #
            #  VA ULTIMO: ninguna de estas se queda sin atender por esperar,
            #  pero un ticket que nadie miro nunca va primero.
            pendientes[str(s.origen_id)] = p
            al_dia.append(s)

    candidatas = sin_leer + al_dia
    if not candidatas:
        return informe

    #  'pendientes' viaja para que cada lectura DEJE RASTRO: que herramientas
    #  pidio el modelo y si alguna midio el equipo. Sin eso, la pregunta "¿mide
    #  o solo lee?" solo se podia contestar deduciendo, y el 13/10/2026 se
    #  dedujo mal con un registro que no ve este camino.
    informe["tickets"] = dxt.diagnosticar(
        org, candidatas, ahora=ahora, propuestas=pendientes,
        tope=TOPE_TICKETS_DESATENDIDO if desatendido else None)

    #  LAS QUE YA TENIAN PROPUESTA: se les agrega el diagnostico recien
    #  escrito. Las que no la tenian las registra el ciclo en su pasada
    #  normal, con la evidencia ya puesta.
    #  SE CUENTA CADA SALIDA, y no es celo: el 14/10/2026 hubo 43 lecturas
    #  registradas y solo 8 propuestas con su pieza. El trabajo se hacia, se
    #  pagaba la consulta al modelo, y se perdia en este paso -- sin una sola
    #  linea que dijera cual de los tres caminos se tomo.
    guardadas = sin_propuesta = sin_leer_de_verdad = fallaron = 0
    for s in candidatas:
        p = pendientes.get(str(s.origen_id))
        if p is None:
            sin_propuesta += 1
            continue
        if not s.datos.get("diagnostico_leido"):
            sin_leer_de_verdad += 1
            continue
        try:
            dxt.guardar_en_propuesta(p, s, ahora)
            guardadas += 1
        except Exception as e:                                   # noqa: BLE001
            fallaron += 1
            logger.exception("Supervisor: no se pudo guardar la lectura (%s)",
                             type(e).__name__)

    informe["guardadas"] = guardadas
    logger.info("Supervisor: lecturas guardadas=%s · sin propuesta=%s · "
                "no se leyeron=%s · fallaron=%s (de %s candidatas)",
                guardadas, sin_propuesta, sin_leer_de_verdad, fallaron,
                len(candidatas))

    return informe


#:  Cuantas propuestas pueden PASAR a Despacho en una vuelta. No cuantas se
#:  MIRAN: esas son todas.
#:
#:  HASTA EL 16/10/2026 ERA AL REVES, y era el defecto. La consulta cortaba en
#:  las 60 mas viejas, y las que nunca califican --una falla con el equipo
#:  sano, un reclamo que nada mide-- ocupaban la ventana cada hora. Medido en
#:  produccion ese dia: 65 pendientes, la fase miraba 60. Una falla NUEVA
#:  confirmada por la medicion, que es justo la que tiene que pasar sola,
#:  entraba ultima y no se evaluaba hasta que salieran otras: dias, por la
#:  vigencia de siete.
#:
#:  Mirar es barato: se lee la evidencia guardada, sin red y sin modelo. Lo que
#:  hay que acotar es el EFECTO. Si una regla se equivoca, que el daño de una
#:  vuelta tenga techo; las que califican despues del tope pasan en la
#:  siguiente, sin escribir nada mientras esperan.
TOPE_PASO_A_DESPACHO = 60



class _SinSenal:
    """
    Una señal minima armada desde la propuesta, para los que no se leyeron hoy.

    Desde la Fase 3 (16/10/2026) 'pasar_si_corresponde' decide SOLO con lo
    guardado en la propuesta --la lectura y la medicion--, y esta señal vacia
    queda porque su firma la pide. No aporta nada a la decision.

    NO se inventa un 'datos' con valores por omision: un grupo puesto por
    defecto seria una clasificacion que nadie hizo.
    """

    __slots__ = ("tipo", "origen_tipo", "origen_id", "evidencia", "datos")

    def __init__(self, propuesta):
        self.tipo = propuesta.tipo_senal
        self.origen_tipo = propuesta.origen_tipo
        self.origen_id = str(propuesta.origen_id)
        self.evidencia = []
        self.datos = {}


def _medir_fallas_pendientes(org, *, desatendido: bool = False) -> dict:
    """
    La medicion de las fallas pendientes, como fase del ciclo. El detalle, y
    por que es una fase propia, en 'medicion_de_fallas'.

    SON CONTEOS, nunca un caso: el detalle queda en cada propuesta.
    """
    from operaciones import medicion_de_fallas

    informe = medicion_de_fallas.medir_fallas_pendientes(
        org, desatendido=desatendido)
    logger.info("Supervisor: medicion de fallas · candidatas=%s · medidas=%s · "
                "concluyentes=%s · sin medicion=%s · sin id de servicio=%s · "
                "sin presupuesto=%s · errores=%s",
                informe["candidatas"], informe["medidas"],
                informe["concluyentes"], informe["sin_medicion"],
                informe["sin_id_de_servicio"], informe["sin_presupuesto"],
                informe["errores"])
    return {"medicion": informe}


def _pasar_a_despacho_los_que_las_reglas_habiliten(org, ahora) -> dict:
    """
    Las cinco reglas, aplicadas a TODAS las propuestas de ticket sin decidir.

    CONSULTA LA BASE, no recibe las señales de la vuelta. Es lo que la vuelve
    independiente de la fase de lectura: con el tope en diez lecturas por
    corrida y 80 propuestas esperando, depender de lo recien leido dejaba
    fuera a 70 -- y cuando ya no quedaba nada por leer, dejaba fuera a todas.

    Lo que decide sale de la evidencia GUARDADA en cada propuesta, que
    'diagnostico_de_ticket' escribe con sus claves propias. Una lectura hecha
    en esta misma vuelta ya esta ahi: esta fase va tercera a proposito.

    Y la propuesta tiene su evidencia ANTES de aceptarse, que es la regla de
    persistencia de §12 -- guardar primero, producir el efecto despues. Un caso
    que llegara a la cola sin el porque a la vista seria peor que uno que no
    llega: quien despacha no tendria con que discutirlo.

    NO LEVANTA. Un paso que no ocurre es un resultado posible del ciclo.
    """
    from operaciones import autonomia, paso_a_despacho as pad

    #  LAS PENDIENTES, las mas viejas primero: una propuesta que lleva dias
    #  esperando es la que mas necesita moverse.
    #
    #  TODAS, sin cortar en el tope: ver TOPE_PASO_A_DESPACHO. El orden sigue
    #  importando, pero para otra cosa: decide quien pasa primero cuando
    #  califican mas que el tope, no quien se mira.
    sin_decidir = list(
        PropuestaSupervisor.objects
        .filter(org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
                estado=PropuestaSupervisor.PROPUESTA, origen_tipo="case")
        .order_by("created_at"))

    #  'por_confianza' SE CUENTA PARA PODER CALIBRAR  --  14/10/2026
    #
    #  La primera version de la regla exigio confianza 'alta' y resulto
    #  inalcanzable: 5 de 142 lecturas, el 3.5%. El umbral se habia fijado sin
    #  medir si el modelo lo alcanza, y el sintoma habria sido "las reglas no
    #  dejan pasar nada" sin ningun error.
    #
    #  Ahora la confianza que decide es otra --la del GRUPO, no la de la
    #  hipotesis-- y su distribucion todavia no se conoce. Contarla aca hace
    #  que UNA corrida alcance para saberla, en vez de salir a consultar la
    #  base propuesta por propuesta.
    reporte = {"pasaron": 0, "se_quedaron": 0, "fallaron": 0,
               "por_grupo": {}, "por_confianza": {}, "motivos": {},
               "pendientes_miradas": 0,
               #  Las que calificaron despues del tope: pasan la vuelta que
               #  viene. Se cuentan aparte porque NO se quedaron con una
               #  persona, y mezclarlas con 'se_quedaron' diria lo contrario.
               "esperan_el_tope": 0,
               #  Cuantas propuestas cambiaron de motivo en esta vuelta. Con
               #  la misma cola y las mismas lecturas tiene que dar cero.
               "motivos_escritos": 0,
               #  Anotar o quitar el motivo fallo. Anotar se reintenta solo,
               #  porque la propuesta sigue pendiente; quitar no, porque ya
               #  paso y ninguna vuelta la vuelve a mirar. Si no da cero,
               #  mirar el log.
               "anotaciones_fallidas": 0,
               #  Las que las reglas dejan pasar y frena una puerta de la
               #  empresa, por grupo. Ver LA SOMBRA, abajo.
               "pasarian_por_grupo": {}}
    reporte["pendientes_miradas"] = len(sin_decidir)
    if not sin_decidir:
        return {"despacho": reporte}

    #  UNA sola consulta del techo para toda la corrida: es una llamada de red,
    #  y preguntarla por caso son tantas como casos. Mismo criterio que el
    #  cierre de desincronizados.
    try:
        autorizacion = autonomia.puede(org, pad.NIVEL_PARA_PASAR)
    except Exception as e:                                       # noqa: BLE001
        #  No poder LEER el techo es lo mismo que no tenerlo: nada pasa.
        logger.info("Supervisor: no se pudo leer el techo de autonomia para "
                    "el paso a Despacho (%s): no pasa ninguno",
                    type(e).__name__)
        reporte["motivos"]["no se pudo leer el techo de autonomia"] = len(
            sin_decidir)
        reporte["se_quedaron"] = len(sin_decidir)
        return {"despacho": reporte}

    for p in sin_decidir:
        if reporte["pasaron"] >= TOPE_PASO_A_DESPACHO:
            #  EL TOPE DE LA VUELTA YA SE ALCANZO. Se sigue MIRANDO --por eso
            #  esta rama existe--, pero sin aceptar nada: se decide solo con
            #  las reglas, que no escriben. La que califica espera a la vuelta
            #  que viene sin anotar nada, porque no se quedo con una persona.
            #  La que no califica se anota igual que en la otra rama: el
            #  motivo es de las reglas, y las puertas no lo cambian.
            #  'evaluar' y no solo las reglas  --  16/10/2026, Fase 3: un caso
            #  cerrado no "espera el tope", se queda con su motivo.
            d = pad.evaluar(p, ahora)
            if d.pasa:
                reporte["esperan_el_tope"] += 1
                continue
            r = {"paso": False, "porque": d.porque, "grupo": d.grupo,
                 "puerta": d.puerta}
        else:
            try:
                r = pad.pasar_si_corresponde(
                    org, _SinSenal(p), p, ahora=ahora,
                    autorizacion=autorizacion)
            except Exception as e:                               # noqa: BLE001
                #  'pasar_si_corresponde' promete no levantar, pero una
                #  excepcion inesperada aqui no puede tumbar el resto de la
                #  vuelta.
                reporte["fallaron"] += 1
                logger.exception("Supervisor: el paso a Despacho fallo (%s)",
                                 type(e).__name__)
                continue

        grupo = r.get("grupo") or "sin grupo"
        reporte["por_grupo"][grupo] = reporte["por_grupo"].get(grupo, 0) + 1
        conf = (_de_la_lectura_guardada(p, "confianza_del_grupo")
                or "sin declarar")
        reporte["por_confianza"][conf] = reporte["por_confianza"].get(conf, 0) + 1
        #  LA SOMBRA  --  16/10/2026, Fase 3. Con la tarea sin delegar, o la
        #  empresa sin autorizar, las que las reglas dejan pasar se cuentan POR
        #  GRUPO. Es la medicion que el usuario pidio antes de encender la regla
        #  1 nueva, y sumadas no responderian la pregunta: con la tarea quitada
        #  se frenan tambien los trabajos pedidos.
        if (not r.get("paso")
                and r.get("puerta") in (pad.PUERTA_TAREA, pad.PUERTA_EMPRESA)):
            reporte["pasarian_por_grupo"][grupo] = (
                reporte["pasarian_por_grupo"].get(grupo, 0) + 1)
        if r.get("paso"):
            reporte["pasaron"] += 1
        else:
            reporte["se_quedaron"] += 1
            #  EL MOTIVO AGRUPADO, no el detalle por caso: el detalle queda en
            #  la propuesta, abajo. Esto es para poder leer de una corrida por
            #  que no paso nada, que el 14/10 costo varias mediciones a mano.
            #
            #  Este comentario decia "el detalle ya quedo en la propuesta"
            #  desde el 14/10, y no era cierto: el motivo solo vivia sumado en
            #  esta linea de log. Medido el 16/10: una propuesta revisada cada
            #  hora se veia en el panel igual que una que nadie miro.
            #
            #  La clave sale de 'motivo_para_el_registro' y no del 'porque'
            #  crudo: el de la puerta de la empresa trae lo que una persona
            #  escribio al mover el interruptor, y esto va a un log.
            m = _en_una_linea(pad.motivo_para_el_registro(r))[:120]
            reporte["motivos"][m] = reporte["motivos"].get(m, 0) + 1

        #  ANOTAR NO PUEDE TUMBAR LA VUELTA. Es informativo: si falla --un
        #  bloqueo, la conexion--, la propuesta sigue igual. Fuera de un try,
        #  una falla al anotar la mas vieja dejaba sin mirar a todas las que
        #  venian detras: el mismo defecto que esta fase vino a cerrar
        #  (auditor de frontera, 16/10). Lo que no se reintenta es QUITAR: la
        #  aceptada ya no vuelve a esta lista (A-11 en la nota de auditoria).
        try:
            if r.get("paso"):
                pad.quitar_por_que_se_quedaba(p)
            elif pad.anotar_por_que_se_queda(p, r, ahora):
                reporte["motivos_escritos"] += 1
        except Exception as e:                                   # noqa: BLE001
            reporte["anotaciones_fallidas"] += 1
            logger.warning("Supervisor: no se pudo anotar el motivo del paso "
                           "a Despacho (%s)", type(e).__name__)

    #  EL MOTIVO VA EN EL LOG, Y NO ES ADORNO  --  15/10/2026
    #  ------------------------------------------------------
    #  'reporte["motivos"]' se venia calculando desde el 14/10 --con el
    #  comentario de arriba diciendo que existe para "poder leer de una corrida
    #  por que no paso nada"-- y esta linea, que es el unico lugar donde una
    #  persona lo lee, lo dejaba afuera. El dato se juntaba y se tiraba.
    #
    #  LO QUE COSTO: una corrida informaba 'pasaron=0 · se quedaron=44' con el
    #  desglose por grupo y por confianza, y ninguno de los dos decia la causa
    #  real --'no se pudo leer el equipo (onu_no_vinculada)' en 13 de ellos--.
    #  Con el grupo y la confianza a la vista, la pista apuntaba a la
    #  calibracion del modelo; el motivo apuntaba al dato que faltaba. Se
    #  persiguio la pista equivocada durante horas.
    #
    #  SON CLAVES Y CONTEOS, nunca un caso: el detalle de cada uno ya quedo en
    #  su propuesta, que es donde una persona lo va a buscar y donde hay
    #  control de acceso. Esto va a un log, que no lo tiene.
    logger.info("Supervisor: paso a Despacho · miradas=%s · pasaron=%s · "
                "esperan el tope=%s · se quedaron=%s · motivos escritos=%s · "
                "anotaciones fallidas=%s · fallaron=%s · por grupo=%s · "
                "por confianza del grupo=%s · por que se quedaron=%s · "
                "pasarian por grupo=%s",
                reporte["pendientes_miradas"], reporte["pasaron"],
                reporte["esperan_el_tope"], reporte["se_quedaron"],
                reporte["motivos_escritos"], reporte["anotaciones_fallidas"],
                reporte["fallaron"], reporte["por_grupo"],
                reporte["por_confianza"], reporte["motivos"],
                reporte["pasarian_por_grupo"])
    return {"despacho": reporte}


def _de_la_lectura_guardada(propuesta, clave: str) -> str:
    """Una clave de la ultima lectura escrita en la propuesta, o cadena vacia.

    Existe solo para CONTAR: cuando el ciclo no leyo este ticket en esta
    vuelta, el dato esta en la propuesta y no en la señal. Lo que DECIDE sigue
    siendo 'paso_a_despacho', que hace su propia lectura -- esto no decide
    nada, y por eso puede devolver vacio sin consecuencias.
    """
    from operaciones import paso_a_despacho as pad

    for pieza in reversed(getattr(propuesta, "evidencia", None) or []):
        if (isinstance(pieza, dict)
                and pieza.get("fuente") == pad.FUENTE_DE_LA_LECTURA
                and clave in pieza):
            return str(pieza.get(clave) or "")
    return ""


def _propuesta_vigente_de(org, senal):
    """La propuesta pendiente de esta señal, si la hay."""
    return (PropuestaSupervisor.objects
            .filter(org=org, tipo_senal=senal.tipo,
                    origen_id=str(senal.origen_id),
                    estado=PropuestaSupervisor.PROPUESTA)
            .order_by("-created_at")
            .first())


def _atender_desincronizados(org, ahora, *, desatendido: bool = False) -> dict:
    """
    Diagnostica los casos desincronizados y cierra los que corresponda.

    CORRE FUERA DE CUALQUIER TRANSACCION, a proposito: todo lo de aqui habla
    con sistemas externos --SmartOLT para el diagnostico, el motor para el
    interruptor y para el cierre-- y ninguna de esas esperas puede ocurrir con
    una fila de la base bloqueada.

    No levanta: un diagnostico o un cierre que no salen son resultados
    posibles del ciclo, y el resto del ciclo ya termino y esta guardado.
    """
    from operaciones import autonomia, diagnostico_optico

    informe = {"diagnostico_optico": {}, "cierre_automatico": {
        "cerraria": 0, "no_cerraria": 0, "no_aplica": 0, "cerrados": 0,
        "motivos": {}}}

    senales = [s for s in detectar(org, ahora)
               if s.tipo == PropuestaSupervisor.CASO_DESINCRONIZADO]
    if not senales:
        return informe

    #  Solo las que van a producir algo: una propuesta nueva, o una pendiente
    #  que todavia no tiene diagnostico. Las ya decididas no se tocan.
    #  DOS GRUPOS, y separarlos es lo que impide que una propuesta se muera a
    #  medio camino (08/10/2026):
    #
    #    pendientes      ya tienen propuesta y les FALTA el diagnostico. Hay que
    #                    preguntarle al proveedor, y eso gasta presupuesto.
    #    por_cerrar      ya fueron diagnosticadas como seguras y NO se cerraron
    #                    --porque alguna puerta estaba cerrada ese dia-- y lo
    #                    unico que les falta es reintentar el cierre.
    #
    #  Sin el segundo grupo, una propuesta diagnosticada el lunes con el nivel
    #  en 1 no se cerraba nunca, por mas que el martes se autorizara todo: ya
    #  tenia diagnostico, asi que dejaba de entrar. El sintoma seria "le subi el
    #  nivel y no pasa nada", sin ningun error.
    pendientes = {}
    por_cerrar = {}
    #  TRES COLAS, Y EL ORDEN ENTRE ELLAS ES EL ARREGLO  --  13/10/2026
    #  ----------------------------------------------------------------
    #  El presupuesto es de quince diagnosticos por vuelta, y se gasta en el
    #  orden en que llegan las señales. 'Case' se consulta SIN 'order_by', asi
    #  que Postgres las devuelve en orden fisico: las mas viejas primero.
    #
    #  El 09/10 se agrego el reintento de los diagnosticos inconcluyentes, y
    #  eso destrabo noventa y cinco casos. Pero creo un problema nuevo: un caso
    #  que NUNCA se va a poder diagnosticar --sin serial en WispHub Y sin
    #  respuesta al ping-- vuelve a entrar en cada vuelta, es de los mas
    #  viejos, y se lleva el presupuesto. Los casos NUEVOS nunca llegaban a
    #  mirarse.
    #
    #  Sintoma reportado dos dias despues: "los casos desincronizados siguen
    #  creciendo y no se cierran solos". Crecian porque los nuevos no se
    #  tocaban, y no se cerraban porque los que si se tocaban eran
    #  precisamente los irresolubles.
    #
    #  SIN DIAGNOSTICAR PRIMERO, REINTENTOS DESPUES. Un caso nuevo siempre
    #  entra; un reintento usa lo que sobre. Es la diferencia entre "todavia no
    #  se pregunto" y "ya se pregunto y no alcanzo", y la primera es la que
    #  puede cambiar algo hoy.
    sin_diagnosticar = []
    reintentos = []
    #  LA CUARTA COLA  --  14/10/2026
    #  ------------------------------
    #  Las que YA tienen un diagnostico concluyente y cuyo nivel no alcanza
    #  para cerrar. Hasta hoy no entraban en ninguna cola: no les faltaba
    #  diagnostico, no habia nada que reintentar, y el nivel las dejaba afuera
    #  de 'por_cerrar'. Se caian por el 'continue' sin error, sin log y sin
    #  propuesta nueva -- 24 de 27 el dia que se midio.
    #
    #  Son precisamente las que la decision de ese dia queria destrabar: el
    #  equipo caido, y los clientes sin ONU registrada que no se van a poder
    #  diagnosticar nunca. Lo que decide si se cierran es si el PROVEEDOR ya
    #  cerro el ticket, y eso se evalua mas abajo.
    ya_diagnosticadas = {}
    for s in senales:
        if not _ya_propuesta(org, s):
            #  Ni siquiera tiene propuesta: lo mas nuevo que hay.
            sin_diagnosticar.append(s)
            continue
        p = diagnostico_optico.propuesta_pendiente_de(org, s)
        if p is None:
            continue
        if diagnostico_optico.le_falta_diagnostico(p):
            #  Tiene propuesta y nunca se le pregunto al proveedor.
            pendientes[s.origen_id] = p
            sin_diagnosticar.append(s)
        elif diagnostico_optico.hay_que_reintentar_diagnostico(p):
            #  Se le pregunto y no se pudo concluir. Vale reintentar --puede
            #  haberse cargado el serial, puede responder el ping-- pero
            #  DESPUES de los que nunca se preguntaron.
            pendientes[s.origen_id] = p
            reintentos.append(s)
        elif p.nivel_autonomia_requerido >= diagnostico_optico.NIVEL_PARA_CERRAR:
            por_cerrar[s.origen_id] = p
        else:
            ya_diagnosticadas[s.origen_id] = (s, p)

    candidatas = sin_diagnosticar + reintentos

    if not candidatas and not por_cerrar and not ya_diagnosticadas:
        return informe

    if candidatas:
        #  EL PRESUPUESTO SE CREA AQUI y se pasa, en vez de dejar que
        #  'enriquecer' se arme el suyo: es el unico lugar que sabe si esta
        #  corrida tiene a alguien esperando del otro lado.
        informe["diagnostico_optico"] = diagnostico_optico.enriquecer(
            org, candidatas, ahora=ahora,
            presupuesto_=diagnostico_optico.presupuesto(
                ahora=ahora, desatendido=desatendido))
        informe["cierre_automatico"] = diagnostico_optico.evaluar_cierre_automatico(
            org, candidatas, ahora=ahora)

    #  LAS QUE EL DIAGNOSTICO DEJABA AFUERA. No se les vuelve a preguntar al
    #  proveedor por el equipo --ya tienen su veredicto escrito y eso gastaria
    #  presupuesto para llegar al mismo numero--: se corren las condiciones
    #  REALES del caso, que son de base y no de red, y la que decide es si el
    #  ticket figura cerrado del otro lado.
    if ya_diagnosticadas:
        evaluadas = diagnostico_optico.evaluar_cierre_automatico(
            org, [s for s, _ in ya_diagnosticadas.values()], ahora=ahora)
        for clave, valor in evaluadas.items():
            if isinstance(valor, int):
                informe["cierre_automatico"][clave] = (
                    informe["cierre_automatico"].get(clave, 0) + valor)
        for senal_, propuesta_ in ya_diagnosticadas.values():
            if diagnostico_optico.habilitar_cierre_si_el_proveedor_cerro(
                    propuesta_, senal_, ahora=ahora):
                por_cerrar[senal_.origen_id] = propuesta_
        informe["cierre_automatico"]["destrabadas_por_el_proveedor"] = len(
            [1 for s_, _ in ya_diagnosticadas.values()
             if s_.datos.get("cierre_automatico") == "cerraria"])

    #  UNA sola consulta del interruptor para toda la corrida: es una llamada
    #  de red, y preguntarla por caso son tantas como casos.
    autorizacion = autonomia.puede(org, diagnostico_optico.NIVEL_PARA_CERRAR)
    _auto = informe["cierre_automatico"]

    for s in candidatas:
        p = pendientes.get(s.origen_id)
        if p is None:
            continue
        r = diagnostico_optico.completar_propuesta_existente(
            org, s, p, ahora=ahora, autorizacion=autorizacion)
        if r["cerrado"]:
            _auto["cerrados"] += 1
            _auto.setdefault("cerrados_detalle", []).append(r)
        else:
            _m = r.get("motivo") or "sin motivo"
            _mot = _auto.setdefault("motivos_de_no_cierre", {})
            _mot[_m] = _mot.get(_m, 0) + 1

    #  EL REINTENTO de las que ya estaban diagnosticadas y no se cerraron. No
    #  se las vuelve a diagnosticar: ya tienen su veredicto escrito, y pedirle
    #  otra vez al proveedor gastaria presupuesto para llegar al mismo numero.
    #  'cerrar_si_corresponde' vuelve a pasar las tres puertas igual.
    for p in por_cerrar.values():
        r = diagnostico_optico.cerrar_si_corresponde(
            org, p, ahora=ahora, autorizacion=autorizacion)
        if r["cerrado"]:
            _auto["cerrados"] += 1
            _auto.setdefault("cerrados_detalle", []).append(r)
        else:
            _m = r.get("motivo") or "sin motivo"
            _mot = _auto.setdefault("motivos_de_no_cierre", {})
            _mot[_m] = _mot.get(_m, 0) + 1

    #  EL AVISO, Y VA ULTIMO A PROPOSITO. Los casos ya estan cerrados y
    #  guardados; contarlo es lo menos importante de esta funcion, y no puede
    #  tumbarla. 'avisar_cierres' no levanta nunca -- lo registra y devuelve
    #  False-- asi que un chat caido no deshace un cierre correcto.
    #
    #  SOLO CUANDO HUBO CIERRES: un aviso por hora diciendo "no cerre nada"
    #  llenaria la conversacion de ruido y, peor, entraria en el historial que
    #  el modelo lee en el turno siguiente, empujando afuera lo que importa.
    cerrados_detalle = _auto.get("cerrados_detalle") or []
    if cerrados_detalle:
        from operaciones import aviso_al_chat
        _auto["avisado_en_el_chat"] = aviso_al_chat.avisar_cierres(
            org, cerrados_detalle, ahora=ahora)
    return informe


def _correr_ciclo(org, ahora) -> dict:
    #  UNO por corrida, compartido con el seguimiento mas abajo: lo que hay que
    #  acotar es lo que espera la persona del otro lado del boton, y eso no se
    #  parte por modulo. Ver 'presupuesto' para los dos topes y su motivo.
    presupuesto_del_ciclo = presupuesto(ahora=ahora)

    resumen = {"senales": 0, "propuestas": 0, "repetidas": 0,
               "sin_analisis": 0, "expiradas": 0, "retiradas_por_area": 0,
               #  M09-L. Las claves de arriba ya existian y no cambian de
               #  significado: las de abajo se AGREGAN para que el ciclo pueda
               #  responder que paso, no solo cuantas cosas pasaron.
               "datos_insuficientes": 0,
               "por_tipo": {},
               "organizacion": {"id": str(org.id), "nombre": org.name},
               "ahora": ahora.isoformat()}
    detalle = []

    resumen["expiradas"] = expirar_vencidas(org, ahora)
    #  ANTES de detectar, a proposito: lo que se retira aca no vuelve a
    #  proponerse en esta misma vuelta, y el panel que la persona abre
    #  despues del boton "Correr ciclo" ya esta limpio.
    resumen["retiradas_por_area"] = retirar_propuestas_fuera_de_area(org, ahora)

    senales = detectar(org, ahora)

    #  LA PANTALLA NO TIENE QUE VOLVER A CALCULAR ESTO  --  14/10/2026
    #  ---------------------------------------------------------------
    #  Los indicadores del tablero corren el MISMO 'detectar()' para pintarse,
    #  y se midio en 22 segundos. Tirar el resultado que acabamos de calcular
    #  para que lo rehaga quien abra la pantalla es pagar dos veces lo mismo --
    #  y la segunda la paga una persona esperando frente a la pagina.
    from operaciones import indicadores

    indicadores.refrescar_senales(org, senales, ahora)

    for senal in senales:
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

        #  FASE 2. El cerebro puede aportar interpretacion sobre una señal que
        #  la REGLA ya detecto. Va aqui y no antes porque aqui el contexto ya
        #  esta completo y las decisiones de seguridad --prioridad, nivel--
        #  YA ESTAN TOMADAS: el cerebro llega cuando no las puede mover.
        #
        #  Con las dos banderas apagadas esto devuelve 'analisis' tal cual y el
        #  ciclo es el de siempre. Nunca levanta: ver 'razonar_sobre'.
        #
        #  SE RAZONA ACA Y SE GUARDA DESPUES, y el orden no es un detalle: la
        #  constancia tiene que apuntar a la propuesta, que todavia no existe.
        #  Por eso 'Aporte' lleva el analisis PREVIO -- despues del
        #  enriquecimiento ya no se puede recuperar, y sin el estado previo no
        #  hay comparacion posible.
        aporte = razonar_sobre(org, senal, analisis, ahora=ahora,
                               presupuesto=presupuesto_del_ciclo)
        analisis = aporte.analisis

        propuesta = registrar_propuesta(org, senal, analisis, ahora)

        #  La bitacora del razonamiento, ya con la propuesta a la que apuntar.
        #  Nunca levanta: si la escritura falla, la propuesta ya esta creada y
        #  el ciclo sigue. Lo que se pierde es la constancia, no el trabajo.
        aporte.dejar_constancia(org, propuesta=propuesta, ahora=ahora)

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

    #  QUE PASO CON EL CEREBRO, y se dice aunque sea cero. Un cerebro que dejo
    #  de razonar a la mitad por falta de presupuesto y no lo cuenta es peor que
    #  uno apagado: la bandeja se veria igual y nadie sabria por que faltan
    #  interpretaciones.
    resumen["razonamientos"] = presupuesto_del_ciclo["usados"]
    resumen["razonamientos_omitidos"] = presupuesto_del_ciclo["omitidos"]

    #  Lo mas urgente primero, y los empates en orden estable por tipo: una
    #  lista que cambia de orden entre dos lecturas iguales no se puede revisar.
    detalle.sort(key=lambda f: (
        (f["propuesta"] or {}).get("prioridad", 99), f["tipo"], f["origen_id"]))
    resumen["detalle"] = detalle
    #  M09-L. La capacidad se OBSERVA en el resumen. No produce propuestas
    #  mientras H-05 siga bloqueada -- ver '_capacidad_de_jornada'.
    resumen["capacidad"] = observar_capacidad(org, ahora)
    return resumen


FUERA_DE_AREA = "Fuera del área del Supervisor NOC"

#  SOLO LO QUE PROPONEN LAS SEÑALES QUE FILTRAN POR AREA. 'CASO_DESINCRONIZADO'
#  (el proveedor cerro y el CRM no) sigue para TODAS las areas por decision del
#  usuario del 16/10/2026: es la unica señal que cierra en el CRM un ticket
#  que WispHub ya cerro, y hoy nadie mas lo hace. Retirar esas propuestas seria
#  deshacer cada hora lo que la señal permitida propone, y el cierre de un
#  ticket de cartera nunca llegaria a una persona.
TIPOS_RETIRABLES_POR_AREA = (
    PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
    PropuestaSupervisor.CASO_ANTIGUO,
    PropuestaSupervisor.CASO_REQUIERE_VISITA,
)


def propuestas_retirables_por_area(org):
    """
    Las candidatas al retiro: pendientes, sobre un caso, de una señal que
    filtra por area. Una sola consulta para el ciclo y para el comando que
    cuenta: si fueran dos, '--contar' mediria otra cosa que la que se retira.
    """
    return PropuestaSupervisor.objects.filter(
        org=org, estado=PropuestaSupervisor.PROPUESTA, origen_tipo="case",
        tipo_senal__in=TIPOS_RETIRABLES_POR_AREA,
    )


def retirar_propuestas_fuera_de_area(org, ahora=None) -> int:
    """
    Cancela las propuestas pendientes sobre tickets que SE SABE de otra área.

    EL DEFECTO  --  16/10/2026
    --------------------------
    Desde cdaa9b27 el Supervisor lee solo tickets de soporte técnico y
    operativo. Pero las propuestas hechas ANTES de ese filtro --sobre cartera,
    ventas, administrativo-- seguían en la pestaña Pendientes hasta que una
    persona las revisara o expiraran a los 7 días. El 15/10 "Pendientes" decía
    76 mientras Soporte Técnico tenía 64 tickets. Nada las retiraba por
    alcance: 'expirar_vencidas' solo mira el tiempo.

    QUÉ HACE, Y QUÉ NO
    ------------------
    Toma las propuestas en PROPUESTA con origen "case" de las señales que
    filtran por área (TIPOS_RETIRABLES_POR_AREA: la de cierre queda afuera por
    decisión del usuario), pregunta por el área de cada caso con el MISMO
    criterio que usan las señales ('areas_del_tenant.criterio_de_area') y
    cancela las que se sabe ajenas:
    área escrita de otra, o sin área escrita y con gente cuya área el motor
    conoce y es otra. Lo que NO se sabe --sin área escrita y sin nadie, o con
    alguien que el motor no conoce-- se queda: cancelar sin saber sería
    inventarle un área.

    Es CANCELADA y no EXPIRADA: "dejó de tener sentido mirarla, y la razón es
    un hecho del mundo", que es exactamente la semántica escrita en
    'cancelar'. No escribe 'revisado_por'. Una cancelada puede volver a
    proponerse por CASO_ANTIGUO o CASO_REQUIERE_VISITA si la reconciliación le
    escribe al caso un área propia: la condición reaparece y es nueva. La
    lectura con diagnóstico NO: '_tickets_abiertos_con_tecnico' excluye lo ya
    leído sin mirar el estado de la propuesta, así que una lectura cancelada
    por área se queda en su fila cancelada (auditoría independiente,
    16/10/2026; decisión abierta en la ficha).

    FAIL-CLOSED: sin el mapa del motor no se cancela nada. Escribir un estado
    por una lectura que no llegó es peor que esperar la próxima vuelta.

    Corre dentro de 'correr_ciclo' (a las :07 y con el botón "Correr ciclo")
    y a demanda con 'manage.py propuestas_fuera_de_area'.
    """
    from operaciones import areas_del_tenant as areas

    criterio = areas.criterio_de_area()
    if not criterio.se_sabe:
        logger.info("Supervisor: sin mapa de areas, no se retira ninguna "
                    "propuesta esta vuelta")
        return 0

    pendientes = list(
        propuestas_retirables_por_area(org)
        .only("id", "origen_id", "estado", "accion_propuesta")
    )
    if not pendientes:
        return 0

    ajenos = areas_de_los_ajenos(
        org, {p.origen_id for p in pendientes}, criterio)
    retiradas = 0
    for propuesta in pendientes:
        area = ajenos.get(propuesta.origen_id)
        if area is None:
            continue
        try:
            cancelar(
                propuesta,
                motivo=f"{FUERA_DE_AREA}: el caso {propuesta.origen_id} es "
                       f"del área '{area}'.",
                descripcion=FUERA_DE_AREA,
                #  Nombre fijo y no la accion propuesta: esa la redacto el
                #  modelo leyendo el ticket, y el feed no tiene por que
                #  repetirla una vez mas por cada cancelacion.
                nombre=FUERA_DE_AREA,
            )
        except YaRevisada:
            #  Alguien la decidio entre que se listo y se intento cancelar.
            #  La decision humana gana, y no es un error.
            continue
        retiradas += 1
    if retiradas:
        logger.info("Supervisor: %s propuestas retiradas por estar fuera del "
                    "area", retiradas)
    return retiradas


#:  Por que se retira la alerta de un caso que ya esta en Despacho. Texto fijo:
#:  ni el asunto del ticket ni el nombre del cliente.
YA_EN_DESPACHO = "El caso ya está en la cola de Despacho"


def retirar_alertas_de_casos_en_despacho(org, ahora=None) -> int:
    """
    Cancela las alertas de CASO ABIERTO ANTIGUO de los casos que ya estan en
    la cola de Despacho.

    EL DEFECTO  --  17/10/2026
    --------------------------
    La alerta pide "revisar y priorizar este caso, o cerrarlo si ya esta
    resuelto". La noche del 16/10 pasaron 15 casos a Despacho solos, y la
    bandeja seguia pidiendo eso de al menos tres: el caso ya estaba en la cola
    y Pendientes lo seguia mostrando como si no. Lo vio el usuario en la
    pantalla.

    QUE HACE, Y QUE NO
    ------------------
    Solo CASO_ANTIGUO y solo en PROPUESTA: lo que una persona ya decidio queda
    como esta, y las otras alertas del caso (visita, ordenes) no se tocan. 'En
    Despacho' es la definicion de la pantalla
    ('paso_a_despacho.casos_en_despacho'), no una copia: un caso cerrado no
    esta en la cola, y su alerta tampoco se retira -- la pantalla ya la
    oculta. Es CANCELADA, como el retiro por area: dejo de tener sentido
    mirarla, y la razon es un hecho del mundo.

    SOLO LOS QUE ENTRARON EN LOS ULTIMOS DIAS_CASO_ANTIGUO DIAS, con el mismo
    corte que el detector ('_casos_abiertos_antiguos'): mientras tanto no la
    vuelve a proponer, y despues el caso es antiguo otra vez y la alerta
    vuelve. Sin el corte, un caso despachado que nadie cierra no avisaria
    nunca mas: la cola no tiene otra salida que cerrar el caso.

    Corre dentro de 'correr_ciclo', despues del paso a Despacho. Una
    aceptacion a mano retira su alerta en la vuelta siguiente, no en el acto.
    El tablero y el latido, que comparten el detector, cuentan menos casos
    antiguos: los que estan en Despacho no lo son.
    """
    from operaciones import paso_a_despacho as pad

    ahora = ahora or timezone.now()
    en_despacho = pad.ids_despachados_desde(
        org, ahora - timedelta(days=DIAS_CASO_ANTIGUO))
    if not en_despacho:
        return 0
    pendientes = list(
        PropuestaSupervisor.objects
        .filter(org=org, tipo_senal=PropuestaSupervisor.CASO_ANTIGUO,
                estado=PropuestaSupervisor.PROPUESTA, origen_tipo="case",
                origen_id__in=en_despacho)
        .only("id", "origen_id", "estado", "accion_propuesta"))
    retiradas = 0
    for propuesta in pendientes:
        try:
            cancelar(
                propuesta,
                motivo=f"{YA_EN_DESPACHO}: la alerta de caso abierto antiguo "
                       f"pedia revisarlo y priorizarlo, y ya esta en la cola "
                       f"(caso {propuesta.origen_id}). Si sigue abierto "
                       f"{DIAS_CASO_ANTIGUO} dias despues de entrar, vuelve.",
                descripcion=YA_EN_DESPACHO,
                #  Nombre fijo, como el retiro por area: el feed no tiene por
                #  que repetir la accion propuesta en cada cancelacion.
                nombre=YA_EN_DESPACHO,
            )
        except YaRevisada:
            #  Alguien la decidio entre que se listo y se intento cancelar.
            #  La decision humana gana, y no es un error.
            continue
        retiradas += 1
    if retiradas:
        logger.info("Supervisor: %s alertas de caso antiguo retiradas: el caso "
                    "ya esta en Despacho", retiradas)
    return retiradas


def _uuids(ids) -> list:
    """Los que parsean como UUID; un 'origen_id' raro no se cancela ni se cuenta."""
    validos = []
    for i in ids:
        try:
            validos.append(uuid.UUID(str(i)))
        except (ValueError, AttributeError, TypeError):
            continue
    return validos


def propios_entre(org, ids_de_caso, criterio) -> set:
    """
    Los ids (str) de 'ids_de_caso' que se saben del Supervisor. Para contar
    lo que no se sabe: ni propio ni ajeno.
    """
    validos = _uuids(ids_de_caso)
    if not validos:
        return set()
    return {str(pk) for pk in Case.objects.filter(org=org, pk__in=validos)
            .filter(criterio.propio).values_list("pk", flat=True)}


def areas_de_los_ajenos(org, ids_de_caso, criterio) -> dict:
    """
    {id de caso (str): area} de los casos de 'ids_de_caso' que se saben
    ajenos. El area es la escrita; si el caso no la tiene, la de su primer
    responsable con area conocida, que es por lo que se lo supo ajeno.
    """
    from operaciones import areas_del_tenant as areas

    validos = _uuids(ids_de_caso)
    if not validos:
        return {}
    casos = Case.objects.filter(org=org, pk__in=validos)
    salida = {}
    for caso in areas.ajenos_entre(casos, criterio).prefetch_related("assigned_to"):
        area = caso.area
        if not area:
            for persona in caso.assigned_to.all():
                area = criterio.mapa.get(str(persona.id)) or ""
                if area:
                    break
        salida[str(caso.id)] = area or "otra área"
    return salida


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
#    - 'accion_propuesta_ref'  el puente a la ejecucion. Lo escribe el cierre
#                         controlado con la clave de la operacion idempotente,
#                         nunca un revisor: editarlo a mano seria inventar una
#                         ejecucion que no ocurrio.
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
            ahora=None, automatico: bool = False,
            tarea: str = "", nombre: str | None = None) -> PropuestaSupervisor:
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
    #  'automatico' ES LA UNICA FORMA DE REVISAR SIN PERSONA, y tiene que
    #  pedirse con todas las letras (08/10/2026).
    #
    #  La alternativa era permitir 'actor=None' a secas, y eso convertiria cada
    #  olvido de pasar el actor en un cierre automatico silencioso. Asi, quien
    #  no lo declara recibe el mismo error de siempre.
    #
    #  'revisado_por' queda en NULL, que es como la auditoria distingue lo
    #  automatico de lo humano. Se eligio eso sobre crear un usuario "Supervisor
    #  NOC IA" en la base: un usuario de sistema puede recibir permisos, puede
    #  iniciar sesion si alguien le pone contraseña, y aparece en los selectores
    #  de asignacion como si fuera una persona. Un NULL no hace ninguna de esas
    #  cosas, y el 'resultado' dice quien fue.
    if actor is None and not automatico:
        raise ValueError("Una revisión sin revisor no es una revisión.")
    if automatico and decision != PropuestaSupervisor.ACEPTADA:
        raise ValueError(
            "El sistema solo acepta automáticamente: rechazar o modificar es "
            "una decisión que necesita a una persona.")

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
        extra = {"revisor": str(actor.id) if actor else "sistema",
                 "automatico": bool(automatico),
                 "sin_ejecucion": True}
        #  QUE TAREA PRODUJO ESTA ACEPTACION  --  16/10/2026
        #  -------------------------------------------------
        #  Sin esto, aceptar una propuesta de CIERRE y pasar un ticket a
        #  DESPACHO escriben exactamente la misma fila --misma entidad, misma
        #  accion, mismo 'extra'-- y el panel no las puede separar.
        #
        #  MEDIDO en produccion: el filtro "Pasados a Despacho" mostraba 597 y
        #  el detalle de esas filas decia "Cerrar el caso en Dexter para
        #  sincronizar su estado". El numero contaba las dos cosas.
        #
        #  LO HISTORICO NO SE RECUPERA: las filas escritas antes de hoy no
        #  tienen esta clave y caen en "propuestas aceptadas", que es lo
        #  honesto -- inventarles una tarea seria afirmar algo que nadie
        #  registro.
        if tarea:
            extra["tarea"] = str(tarea)
        if registro_cambios:
            extra["cambios"] = registro_cambios
        auditoria.registrar(
            org=fresca.org, actor=actor, accion=verbo,
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=fresca.id,
            #  'nombre' FIJO cuando lo pide quien llama, como en 'cancelar':
            #  'accion_propuesta' la redacto el modelo leyendo el ticket, y
            #  'Activity' la ve cualquier usuario de la empresa. El pase
            #  automatico a Despacho lo pide desde el 16/10/2026 (Fase 3).
            nombre=nombre if nombre is not None else fresca.accion_propuesta,
            descripcion=comentario,
            estado_anterior=anterior, estado_nuevo=fresca.estado,
            motivo=comentario,
            extra=extra,
        )

        #  LA DECISION SE CAPTURA AQUI  --  paso P8.2 (05/10/2026)
        #
        #  'DecisionSupervisor' existia desde P4 con sus tres restricciones
        #  de base y NUNCA se escribia: la unica aparicion fuera de las
        #  pruebas era la definicion de la clase. Por eso
        #  'indicadores_situaciones' calculaba 'tasa_aceptacion' y
        #  'recomendaciones_que_funcionaron' leyendo una tabla vacia, y
        #  devolvia 0 / NO_APLICA para siempre.
        #
        #  Va DENTRO de esta transaccion a proposito: una propuesta revisada
        #  sin su fila de decision es exactamente el estado que dejaba las
        #  metricas en cero. Si esto falla, la revision entera se deshace.
        #
        #  El resultado nace PENDIENTE. 'aceptada' NO es 'funciono': eso se
        #  sabe despues y lo registra 'gobierno.registrar_resultado' con su
        #  evidencia. Medir las dos cosas juntas diria obediencia donde dice
        #  acierto.
        from operaciones import gobierno

        gobierno.registrar_decision(fresca, actor=actor, ahora=ahora,
                                    automatico=automatico)
    return fresca


def cancelar(propuesta: PropuestaSupervisor, *, motivo: str,
             descripcion: str = "La condición dejó de existir antes de ser revisada",
             nombre: str | None = None,
             ) -> PropuestaSupervisor:
    """
    La condición desapareció antes de que nadie la mirara -- o dejó de ser
    de este equipo ('descripcion' lo dice; ver retirar_propuestas_fuera_de_area).

    'nombre' es lo que el feed de actividad muestra como título del renglón.
    Por defecto es la acción propuesta, como siempre; el retiro por área pasa
    un texto fijo, porque para la lectura con diagnóstico esa acción la
    redactó el modelo leyendo el ticket y puede traer lo que el ticket traía.

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
            nombre=nombre if nombre is not None else fresca.accion_propuesta,
            descripcion=descripcion,
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

    QUE FALTA PARA CERRAR UN CASO AL ACEPTAR  --  M09-R (25/09/2026)
    ---------------------------------------------------------------
    La pregunta se hizo explícita al pedir que aceptar una propuesta de
    `caso_desincronizado` cierre el caso. La herramienta existe
    (`cerrar_caso_crm`: PATCH /api/cases/{id}/ con status=Closed y closed_on
    automático) y la puerta existe (`nucleo/seguridad/frontera.py`). Lo que
    falta son TRES autorizaciones, todas medidas contra producción, y ninguna
    se puede dar desde este archivo:

      1. `AUTONOMIA_2_ACTIVA` está apagada. 18.630 filas en
         `asistente.ejecucion_autonoma`, todas 'bloqueada'.
      2. El prerequisito B-7 sigue abierto: el GUC `app.settings.jwt_secret`
         está PRESENTE en la base, así que `autonomia2.veredicto_b7()` responde
         B7_REQUERIDO. Encender (1) sin cerrar esto solo cambia el código del
         bloqueo, no lo levanta.
      3. `asistente.autorizacion_herramienta` está vacía (0 filas), así que
         cada herramienta responde HERRAMIENTA_SIN_AUTORIZACION incluso con las
         dos anteriores resueltas.

    Hay una cuarta vía que NO está bloqueada y que por eso hay que nombrar:
    `frontera.humana()` no consulta el kill switch ni Autonomía 2 -- exige
    `actor` + `evidencia`, y el id de una propuesta aprobada es exactamente la
    evidencia que pide. Es la puerta conceptualmente correcta para una decisión
    humana. NO se usa todavía, y no por olvido: abrirla desde aquí sería el
    bypass que este módulo existe para no tener. Cuando se decida, el cambio va
    en el motor y con su propio bloque.
    """
    raise EjecucionNoPermitida(
        f"Shadow Mode: la propuesta {propuesta.id} no se ejecuta. "
        f"El Supervisor observa y recomienda; ejecutar es otra fase."
    )


# =============================================================================
#  EL CEREBRO EN EL SEGUIMIENTO  --  donde deja de reaccionar y sigue un hilo
# =============================================================================
#
#  QUE LO DIFERENCIA DE 'razonar_sobre'
#  ------------------------------------
#  'razonar_sobre' interpreta una señal RECIEN DETECTADA: un instante. Esto
#  interpreta una SITUACION CON HISTORIA -- cuantos afectados tenia, como cambio,
#  cuantas veces se reviso, que se anoto antes en su linea de tiempo.
#
#  Y hay una diferencia concreta, no retorica: aqui el contexto se arma CON la
#  situacion ('contexto_para(org, situacion=...)'), que es la forma en que el
#  cerebro al fin ve el hilo completo en vez del ultimo eslabon.
#
#  LO QUE PUEDE Y NO PUEDE TOCAR
#  -----------------------------
#  Solo 'porque'. El veredicto --estable, empeora, mejora, requiere_humano-- lo
#  decide 'situaciones_seguimiento.evaluar' con reglas y conteos, y seguira
#  decidiendolo: es lo que mueve el estado de la situacion y fija cuando volver a
#  mirarla. Un cerebro que pudiera cambiarlo estaria decidiendo la operacion.
#
#  La comprobacion no es un comentario: se recorre la salida campo por campo y se
#  levanta si algo que no es 'porque' cambio. Mismo patron que
#  'cerebro.analisis_de_veredicto'.
CAMPOS_QUE_EL_CEREBRO_ENRIQUECE_EN_SEGUIMIENTO = ("porque",)


def interpretar_seguimiento(situacion, salida: dict, *, ahora=None,
                            presupuesto=None) -> dict:
    """
    Le pide al cerebro que explique como va una situacion. Devuelve la salida.

    Con el cerebro apagado devuelve la salida TAL CUAL --el mismo objeto-- y el
    seguimiento es el de siempre.

    NUNCA LEVANTA por un fallo del modelo o de la base. 'seguir' ademas lo
    envuelve y cuenta el fallo aparte, pero no se delega: el veredicto ya es
    correcto sin el cerebro, y perderlo por una interpretacion seria el peor
    intercambio posible.

    LA UNICA EXCEPCION QUE SI SALE es el AssertionError de abajo, y es a
    proposito: si el cerebro modifico un campo que no puede tocar, seguir
    adelante escribiria un veredicto adulterado. Ahi vale mas cortar.
    """
    if not _el_cerebro_corre() or not isinstance(salida, dict):
        return salida
    if not _hay_presupuesto(presupuesto):
        return salida
    _gastar(presupuesto)

    previo = dict(salida)
    org = situacion.org

    import json
    from operaciones import cerebro, razonamiento
    from operaciones.razonamiento_modelos import FuenteRazonamiento

    try:
        #  CON la situacion: aqui esta el hilo, no el eslabon.
        contexto = cerebro.contexto_para(org, situacion=situacion)
        sin_porque = {k: v for k, v in salida.items() if k != "porque"}
        veredicto = cerebro.concluir(
            org,
            instrucciones=_instrucciones_del_seguimiento(org),
            entrada=(
                f"{contexto}\n\n== COMO VA, SEGUN LA REGLA ==\n"
                f"veredicto: {salida.get('veredicto')}\n"
                f"porque: {salida.get('porque')}\n"
                f"abonados afectados: {salida.get('abonados_afectados')}\n"
                f"cambio desde la ultima revision: {salida.get('delta')}\n"
                f"datos: "
                f"{json.dumps(sin_porque, ensure_ascii=False, default=str)[:900]}"))
    except Exception:                                        # noqa: BLE001
        return salida

    #  LA CONSTANCIA, siempre que el cerebro haya corrido -- tambien cuando no
    #  concluye, que es la mitad del valor de medirlo. Apunta a la SITUACION, lo
    #  otro que la restriccion de la tabla acepta ademas de una propuesta.
    enriquecera = bool(CEREBRO_EN_EL_CICLO and veredicto.concluyente
                       and veredicto.recomendacion.strip())
    razonamiento.registrar(
        org, veredicto, fuente=FuenteRazonamiento.SEGUIMIENTO,
        situacion=situacion, analisis_previo=previo,
        enriquecio=enriquecera, ahora=ahora)

    if not enriquecera:
        return salida

    nueva = dict(salida)
    nueva["porque"] = (f"{salida.get('porque', '')} "
                       f"{veredicto.recomendacion.strip()}").strip()[:1000]

    #  ESTRUCTURAL, no documental: si algo que no es 'porque' cambio, se corta.
    for clave, valor in previo.items():
        if clave in CAMPOS_QUE_EL_CEREBRO_ENRIQUECE_EN_SEGUIMIENTO:
            continue
        if nueva.get(clave) != valor:
            raise AssertionError(
                f"el cerebro modifico '{clave}' del seguimiento, que no puede "
                f"tocar: el veredicto y la proxima revision son de la regla")
    return nueva


_INSTRUCCIONES_DEL_SEGUIMIENTO = """\
Sos el Supervisor NOC IA de un ISP. Una situacion que ya conocias se acaba de
revisar, y una REGLA ya dijo como va: estable, empeora, mejora, sin evidencia,
requiere humano o puede resolverse. Vos NO cambias ese veredicto.

Tu trabajo es el que la regla no puede hacer: mirar la historia de esta
situacion y decir que se entiende de como viene evolucionando. No repitas el
conteo que la regla ya hizo -- deci lo que el conteo no dice.

Consulta las herramientas antes de afirmar cualquier cosa. Un hecho que no salga
de una herramienta no es un hecho, y se va a descartar.

Lo que mas sirve aqui: si lo que esta pasando se parece a algo que ya paso antes
en esta misma situacion, si el cambio desde la ultima revision significa algo
distinto de lo que parece, y que convendria verificar ahora.

Si no tenes nada que agregar, decilo en "falta". Un veredicto sin tu aporte ya es
correcto; uno con un aporte inventado es peor que sin el.

No propongas ejecutar nada: no podes, y decir que lo hiciste seria mentir.
"""


def _instrucciones_del_seguimiento(org) -> str:
    """
    El nucleo del seguimiento mas el estilo editable de la empresa.

    Reusa el ambito 'ciclo' a proposito y no inventa un tercero: lo que se afina
    ahi --que el texto sea corto y se lea de un vistazo-- es lo mismo que hace
    falta aqui, y un ambito mas seria una pantalla mas que nadie pidio. Si algun
    dia los dos necesitan tonos distintos, agregarlo es una linea.
    """
    from operaciones import estilo as svc_estilo
    from operaciones.estilo_modelos import AmbitoEstilo
    return (_INSTRUCCIONES_DEL_SEGUIMIENTO + "\n\n"
            + svc_estilo.vigente(org, AmbitoEstilo.CICLO))


#:  Cuanto entra en 'PropuestaSupervisor.accion_propuesta'. Es CharField(255) y
#:  su ayuda lo dice: "Qué recomienda, en una línea legible". No es un limite
#:  arbitrario -- es una COLUMNA de una tabla que se lee de un vistazo.
LARGO_DE_UNA_LINEA = 255


def _en_una_linea(texto: str) -> str:
    """
    La propuesta del modelo, recortada a lo que el campo aguanta.

    POR QUE HACE FALTA: el modelo escribe parrafos --"Separar el ticket en dos
    gestiones: (1) el cambio de domicilio va al area comercial..."-- y la
    columna admite 255. Medido el 14/10/2026: ocho de treinta y ocho lecturas
    se perdieron con 'value too long for type character varying(255)', y como
    la base rechaza el guardado ENTERO, con la accion se iba tambien la
    evidencia que ya estaba escrita.

    SE CORTA EN LA PRIMERA FRASE, no a los 255 caracteres secos: una frase
    entera dice algo ("Derivar el ticket a Cartera") y un corte a ciegas deja
    la mitad de una palabra. Si la primera frase tampoco entra, se corta en el
    ultimo espacio y se marca con puntos suspensivos para que se vea que sigue.

    EL TEXTO COMPLETO NO SE PIERDE: va al motivo, que es TextField.
    """
    t = " ".join(str(texto or "").split())
    if not t:
        return ""
    if len(t) <= LARGO_DE_UNA_LINEA:
        return t

    #  La primera frase, si alcanza. El punto de un "(1)" o de "Ej." no corta:
    #  se exige un espacio o el final detras.
    import re

    corte = re.search(r"\.(?=\s|$)", t[:LARGO_DE_UNA_LINEA])
    if corte and corte.start() > 40:
        return t[:corte.start() + 1]

    recorte = t[:LARGO_DE_UNA_LINEA - 1]
    if " " in recorte:
        recorte = recorte.rsplit(" ", 1)[0]
    return recorte + "…"
