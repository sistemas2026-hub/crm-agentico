# -*- coding: utf-8 -*-
"""
================================================================================
 COORDINACION  --  el Supervisor pide trabajo, y la autonomia decide si puede
================================================================================

QUE ES ESTO, Y QUE NO ES
------------------------
Es el puente que faltaba. El Supervisor ya DETECTA (quince detectores en
'supervisor.py'), ya AGRUPA ('correlacion.py'), ya SIGUE ('situaciones_
seguimiento.py') y ya RECOMIENDA ('PropuestaSupervisor'). Lo que no podia hacer
era pedir trabajo: no existia ninguna forma de que una situacion produjera una
actividad de M02 y quedara trazada.

NO es un sistema de tareas nuevo. Cada funcion de aqui termina llamando a
'actividades.crear' --el servicio de M02-- con sus validaciones, su maquina de
transiciones, su auditoria y su deduplicacion. Si este modulo desapareciera, M02
seguiria funcionando igual; lo que se perderia es el puente.

EL PUENTE, Y POR QUE ES ESE Y NO OTRO
-------------------------------------
Auditado el 05/10/2026: NO EXISTE ningun campo que ligue 'ActividadOperativa'
con 'SituacionOperativa', en ninguna direccion. Se comprobo por cinco vias
(modelos, servicio, serializers, migraciones y los valores de 'origen_tipo' que
el codigo escribe de verdad: 'case', 'orden_trabajo', 'ticket', 'manual',
'actividad', 'jornada' -- nunca 'situacion').

Asi que el puente es el par generico que M02 ya tiene y que ya esta indexado
('operaciones_org_id_62b885_idx' sobre org+origen_tipo+origen_id):

    origen_tipo = "situacion"      <- valor nuevo, declarado aqui
    origen_id   = str(situacion.id)

Se eligio eso en vez de agregar una FK por dos razones. La primera es que el
mecanismo ya existe y esta indexado, y una FK nueva seria una segunda forma de
decir lo mismo. La segunda es mas util: 'crear(evitar_duplicado=True)' deduplica
exactamente por (org, tipo, origen_tipo, origen_id) excluyendo estados finales,
asi que el puente TRAE la idempotencia de dominio puesta. Dos ciclos del
Supervisor sobre la misma situacion no abren dos veces la misma actividad.

Y la traza va en los dos sentidos: ademas de 'origen_id' en la actividad, se
anota un 'SituacionEvento' de tipo 'coordinacion' en el timeline, que es
append-only por codigo ('save' y 'delete' levantan). Lo que aparece ahi, paso.

LA PUERTA  --  y que esta CERRADA hoy, a proposito
--------------------------------------------------
Pedir trabajo escribe en la base operativa, asi que no puede depender de que el
Supervisor lo considere buena idea. Cada funcion de aqui pasa primero por
'autonomia.puede(org, NIVEL_COORDINAR)', que es el nivel 2 de P4.

Con la configuracion de hoy eso RECHAZA: 'PropuestaSupervisor.NIVEL_MAXIMO_
ETAPA' es NIVEL_RECOMENDAR (1), y 'autonomia.nivel_efectivo' recorta a 1 cuando
el interruptor del motor esta detenido o ilegible. Es decir: este modulo
construye la capacidad y la deja probada, y no la habilita. Habilitarla es subir
el nivel, y eso lo hace una persona con 'autonomia.cambiar' -- jamas el
Supervisor, que solo puede leerlo.

El rechazo NO es silencioso: se audita en 'common.Activity' con accion
'REJECTED' antes de levantar. Un intento fuera de autonomia tiene que dejar
rastro, porque si no la unica forma de saber que paso es que alguien estuviera
mirando.

LO QUE M02 NO TIENE, Y POR ESO ESTO NO LO INVENTA
-------------------------------------------------
'ActividadOperativa' NO tiene campo 'evidencia' ni campo 'condicion_exito'
(auditado: 'grep evidencia operaciones/actividades.py' = 0 resultados). Este
modulo EXIGE los dos como argumento --una coordinacion sin condicion de exito es
una orden sin forma de saber si se cumplio-- y los guarda donde si hay lugar: el
texto compuesto en 'descripcion', y la version estructurada en los 'datos' del
evento del timeline, que es JSON. No se agrega un campo a M02 para esto; si mas
adelante se decide agregarlo, el dato ya esta escrito y se puede migrar.

'actividades.crear' tampoco acepta un "area": el responsable es un Profile o
nada. Cuando no hay persona, el area queda en la descripcion y en los datos del
evento, y la actividad nace SIN responsable -- que es honesto, y ademas es justo
lo que el detector '_actividades_sin_responsable' ya busca.
================================================================================
"""

from django.db import transaction
from django.utils import timezone

from operaciones import actividades, auditoria
from operaciones import autonomia as gob_autonomia
from operaciones import situaciones as svc
from operaciones.models import ActividadOperativa, PropuestaSupervisor
from operaciones.situaciones_modelos import SituacionOperativa, TipoEvento

A = ActividadOperativa
P = PropuestaSupervisor
S = SituacionOperativa

#  Coordinar es el nivel 2 de P4. No se redefine aqui: se importa.
NIVEL_COORDINAR = P.NIVEL_COORDINAR

#  El valor nuevo de 'origen_tipo'. Vive aqui, en una constante, y no suelto en
#  una cadena: el dia que alguien busque "quien escribe origen_tipo='situacion'"
#  tiene que encontrar un solo lugar.
ORIGEN_SITUACION = "situacion"

#  Las cinco clases de evidencia que el bloque nombra. Es una lista cerrada a
#  proposito: "solicitar algo" sin decir QUE se solicita produce una actividad
#  que nadie sabe cuando esta cumplida.
CLASES_DE_EVIDENCIA = {
    "fotografia": "Fotografía",
    "medicion": "Medición",
    "diagnostico": "Diagnóstico",
    "comprobacion": "Comprobación",
    "resultado_procedimiento": "Resultado de procedimiento",
}

#  Los tipos de M02 que una coordinacion del Supervisor puede pedir. No son los
#  nueve: 'handoff' y 'correccion' nacen de una persona que entrega o corrige
#  trabajo, no de una deteccion.
TIPOS_COORDINABLES = (A.TAREA, A.PENDIENTE_T, A.SEGUIMIENTO,
                      A.SOLICITUD_INFORMACION, A.SOPORTE)


class CoordinacionNoPermitida(Exception):
    """La autonomia vigente no alcanza. Trae el veredicto, no solo un 'no'."""

    def __init__(self, mensaje, veredicto=None):
        super().__init__(mensaje)
        self.veredicto = veredicto or {}


class CoordinacionInvalida(Exception):
    """Falta contexto para que la coordinacion tenga sentido."""


def _firma(texto: str) -> str:
    """Ocho caracteres estables de un texto, para que quepa en la huella."""
    import hashlib

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:8]


# =============================================================================
#  LA PUERTA
# =============================================================================

def _auditar_rechazo(org, actor, *, situacion, que: str, veredicto: dict):
    """
    Deja constancia de que se intento algo que la autonomia no permite.

    Se escribe contra la SITUACION y no contra una actividad, porque no hay
    ninguna: el rechazo ocurre ANTES de crear nada, y eso es el punto.
    """
    auditoria.registrar(
        org=org, actor=actor, accion="REJECTED",
        entidad=auditoria.ENTIDAD_SITUACION,
        entidad_id=situacion.id,
        nombre=situacion.codigo,
        descripcion=f"Coordinación rechazada: {que}",
        motivo=veredicto.get("motivo", ""),
        extra={"nivel_requerido": NIVEL_COORDINAR,
               "nivel_efectivo": veredicto.get("efectivo"),
               "que_se_intento": que,
               "se_modifico_algo": False})


def _exigir_autonomia(org, *, actor, situacion, que: str) -> dict:
    """
    El veredicto de P4, consultado EN VIVO. Si no alcanza, audita y levanta.

    Se consulta en cada llamada y no una vez por ciclo: si una persona baja el
    nivel mientras un ciclo corre, la coordinacion siguiente tiene que verlo.
    """
    veredicto = gob_autonomia.puede(org, NIVEL_COORDINAR)
    if not veredicto["puede"]:
        _auditar_rechazo(org, actor, situacion=situacion, que=que,
                         veredicto=veredicto)
        raise CoordinacionNoPermitida(
            f"coordinar requiere nivel {NIVEL_COORDINAR} y no está permitido: "
            f"{veredicto['motivo']}", veredicto)
    return veredicto


def _exigir_situacion_viva(situacion):
    if situacion.estado not in S.VIVAS:
        raise CoordinacionInvalida(
            f"la situación {situacion.codigo} está en '{situacion.estado}': no "
            f"se coordina trabajo sobre una situación que ya no está viva")


def _texto(*, objetivo: str, condicion_exito: str, area: str,
           situacion, extra: str = "") -> str:
    """
    La descripcion que lee una persona. Lleva el codigo de la situacion.

    No es decoracion: quien abre la actividad en el tablero tiene que poder
    llegar a la situacion que la origino sin consultar la base.
    """
    partes = [f"Origen: situación {situacion.codigo} — {situacion.titulo}",
              f"Objetivo: {objetivo}",
              f"Condición de éxito: {condicion_exito}"]
    if area:
        partes.append(f"Área responsable: {area}")
    if extra:
        partes.append(extra)
    partes.append("Solicitado por el Supervisor NOC IA. Completar no es "
                  "validar: el resultado se valida aparte.")
    return "\n".join(partes)


# =============================================================================
#  §4A  --  SOLICITAR UNA ACTIVIDAD
# =============================================================================

def solicitar_actividad(situacion, *, actor=None, tipo=A.TAREA, titulo: str,
                        objetivo: str, condicion_exito: str, responsable=None,
                        area: str = "", vence_en=None, ahora=None,
                        permitir_repetida: bool = False) -> dict:
    """
    Pide una actividad de M02 a partir de una situacion, y la deja trazada.

    LO QUE EXIGE ANTES DE ESCRIBIR, y por que cada cosa:

      * autonomia de nivel 2  -- escribir en la operacion no es una lectura;
      * la situacion VIVA     -- coordinar sobre una situacion cerrada produce
                                 trabajo que nadie pidio;
      * objetivo              -- una actividad sin objetivo no se puede cerrar;
      * condicion de exito    -- sin ella, "hecho" es una opinion;
      * responsable O area    -- si no hay ninguno de los dos, nadie la va a
                                 mirar, y el Supervisor estaria generando ruido.

    POR QUE ESTA FUNCION NO LLEVA '@transaction.atomic' ENCIMA
    ----------------------------------------------------------
    Lo llevaba, y estaba MAL. Medido el 05/10/2026 por 'test_E2E_4': con el
    decorador, el rechazo por autonomia se auditaba y entonces la excepcion
    salia de la funcion, el bloque atomico hacia rollback, y la fila de
    auditoria DESAPARECIA. Es decir: un intento no autorizado no dejaba rastro,
    que es exactamente lo contrario de lo que el rechazo tiene que lograr.

    Asi que las validaciones y la puerta corren FUERA de la transaccion --no
    escriben nada salvo la auditoria del rechazo, que debe sobrevivir-- y solo
    la creacion de la actividad mas su evento van dentro de un bloque atomico.

    Devuelve {'actividad', 'evento', 'veredicto', 'repetida'}. 'repetida' es
    True cuando M02 ya tenia una viva para esta situacion y este tipo: en ese
    caso NO se crea otra y se devuelve la que habia. Eso no es un error -- es la
    idempotencia de dominio de 'crear(evitar_duplicado=True)' haciendo su
    trabajo.
    """
    ahora = ahora or timezone.now()
    org = situacion.org

    titulo = (titulo or "").strip()
    objetivo = (objetivo or "").strip()
    condicion_exito = (condicion_exito or "").strip()
    area = (area or "").strip()

    if tipo not in TIPOS_COORDINABLES:
        raise CoordinacionInvalida(
            f"tipo '{tipo}' no es coordinable por el Supervisor; los que sí: "
            f"{', '.join(TIPOS_COORDINABLES)}")
    if not titulo:
        raise CoordinacionInvalida("falta el título")
    if not objetivo:
        raise CoordinacionInvalida(
            "falta el objetivo: una actividad sin objetivo no se puede cerrar")
    if not condicion_exito:
        raise CoordinacionInvalida(
            "falta la condición de éxito: sin ella, 'hecho' es una opinión y "
            "no un hecho verificable")
    if responsable is None and not area:
        raise CoordinacionInvalida(
            "falta responsable o área: una actividad que no es de nadie no la "
            "mira nadie")

    _exigir_situacion_viva(situacion)
    veredicto = _exigir_autonomia(org, actor=actor, situacion=situacion,
                                  que=f"solicitar actividad '{titulo}'")

    #  Desde aqui si: la actividad y su evento son un solo hecho.
    with transaction.atomic():
        #  EL CANDADO, y por que hace falta. Medido el 05/10/2026 con
        #  'test_p6_concurrencia_postgres': sin esto, dos hilos pidiendo la MISMA
        #  actividad para la MISMA situacion creaban DOS. La deduplicacion de M02
        #  ('crear(evitar_duplicado=True)') es un SELECT previo y NO tiene
        #  'UniqueConstraint' que la respalde --lo dice su propia auditoria--,
        #  asi que los dos hilos pasaban el chequeo antes de que ninguno
        #  insertara. En produccion eso es trabajo de campo duplicado: dos
        #  cuadrillas al mismo PON.
        #
        #  Se serializa sobre la fila de la SITUACION y no sobre la actividad,
        #  porque la actividad todavia no existe -- no hay nada que bloquear. Es
        #  el mismo patron que 'correlacion.agrupar' ya usa.
        #
        #  Lo que esto NO arregla, y queda dicho: cualquier OTRO camino que llame
        #  a 'actividades.crear' sigue con la carrera abierta. Cerrarla de verdad
        #  seria un indice unico parcial en 'operaciones_actividad', y eso toca
        #  M02 y los datos que ya existen.
        S.objects.select_for_update().get(pk=situacion.pk)
        return _escribir(situacion, actor=actor, tipo=tipo, titulo=titulo,
                         objetivo=objetivo, condicion_exito=condicion_exito,
                         responsable=responsable, area=area, vence_en=vence_en,
                         ahora=ahora, permitir_repetida=permitir_repetida,
                         veredicto=veredicto)


def _escribir(situacion, *, actor, tipo, titulo, objetivo, condicion_exito,
              responsable, area, vence_en, ahora, permitir_repetida,
              veredicto) -> dict:
    """La parte que escribe. Separada para que la puerta quede fuera del atomic."""
    org = situacion.org
    repetida = False
    try:
        actividad = actividades.crear(
            org=org, actor=actor, tipo=tipo, titulo=titulo[:255],
            descripcion=_texto(objetivo=objetivo,
                               condicion_exito=condicion_exito, area=area,
                               situacion=situacion),
            responsable=responsable,
            origen_tipo=ORIGEN_SITUACION, origen_id=str(situacion.id),
            vence_en=vence_en,
            evitar_duplicado=not permitir_repetida)
    except actividades.ActividadDuplicada:
        #  Ya hay una viva para esta situacion y este tipo. Se devuelve ESA.
        actividad = (A.objects
                     .filter(org=org, tipo=tipo,
                             origen_tipo=ORIGEN_SITUACION,
                             origen_id=str(situacion.id))
                     .exclude(estado_operativo__in=A.ESTADOS_FINALES)
                     .order_by("-created_at").first())
        if actividad is None:                       # pragma: no cover
            raise
        repetida = True

    evento = svc.anotar(
        situacion, TipoEvento.COORDINACION,
        ("Ya existía la coordinación: " if repetida
         else "Se solicitó: ") + titulo[:200],
        datos={"actividad_id": str(actividad.id),
               "tipo": tipo,
               "objetivo": objetivo,
               "condicion_exito": condicion_exito,
               "area": area,
               "responsable_id": (str(responsable.id) if responsable else ""),
               "vence_en": vence_en.isoformat() if vence_en else None,
               "repetida": repetida,
               "nivel_efectivo": veredicto.get("efectivo")},
        actor=actor, ocurrido_en=ahora)

    return {"actividad": actividad, "evento": evento,
            "veredicto": veredicto, "repetida": repetida}


# =============================================================================
#  §4B  --  SOLICITAR EVIDENCIA
# =============================================================================

@transaction.atomic
def solicitar_evidencia(situacion, *, actor=None, clase: str, detalle: str,
                        condicion_exito: str, responsable=None,
                        area: str = "", vence_en=None, ahora=None) -> dict:
    """
    Pide una comprobacion concreta: foto, medicion, diagnostico, resultado.

    Es 'solicitar_actividad' con el tipo fijado en 'solicitud_informacion' --el
    tipo de M02 que ya existe para esto-- y con la clase de evidencia dentro de
    una lista cerrada.

    LO QUE NO HACE: no inventa la evidencia, y no la recibe. M02 no tiene campo
    de evidencia (auditado el 05/10/2026), asi que lo que vuelve del campo entra
    por donde entra hoy: 'completar' + 'validar', y la novedad si hubo un
    problema. Esta funcion abre la solicitud; cerrarla con un dato real es de
    quien la ejecuta.
    """
    clase = (clase or "").strip()
    if clase not in CLASES_DE_EVIDENCIA:
        raise CoordinacionInvalida(
            f"clase de evidencia desconocida: {clase!r}; las que hay: "
            f"{', '.join(sorted(CLASES_DE_EVIDENCIA))}")
    detalle = (detalle or "").strip()
    if not detalle:
        raise CoordinacionInvalida(
            "falta el detalle: 'solicitar una medición' sin decir de qué no se "
            "puede cumplir")

    etiqueta = CLASES_DE_EVIDENCIA[clase]
    salida = solicitar_actividad(
        situacion, actor=actor, tipo=A.SOLICITUD_INFORMACION,
        titulo=f"{etiqueta}: {detalle}",
        objetivo=f"Obtener {etiqueta.lower()} — {detalle}",
        condicion_exito=condicion_exito, responsable=responsable, area=area,
        vence_en=vence_en, ahora=ahora)

    #  La clase queda en los datos del evento, que es JSON y si tiene lugar.
    salida["clase_evidencia"] = clase
    return salida


# =============================================================================
#  §4C/§4D  --  LO QUE YA SE PUEDE CONTROLAR, RESUELTO EN UNA LECTURA
# =============================================================================

def pendientes_de_la_situacion(situacion) -> dict:
    """
    Las actividades que esta situacion origino, y en que estado estan.

    Es LECTURA: no toca la autonomia, no escribe y no decide nada. Sirve para
    que el chat pueda contestar "¿que pedi para esta situacion y que paso?" sin
    que el modelo tenga que cruzar dos consultas a mano.

    'ejecutada != validada' se devuelve separado a proposito: una actividad
    COMPLETADA con 'estado_validacion' pendiente NO es una actividad resuelta, y
    presentarlas juntas seria afirmar que el problema se atendio.
    """
    qs = (A.objects
          .filter(org=situacion.org, origen_tipo=ORIGEN_SITUACION,
                  origen_id=str(situacion.id))
          .select_related("responsable__user", "depende_de")
          .order_by("vence_en", "-created_at"))

    filas = []
    for a in qs:
        filas.append({
            "id": str(a.id), "tipo": a.tipo, "titulo": a.titulo,
            "estado": a.estado_operativo,
            "validacion": a.estado_validacion,
            "vencimiento": actividades.clasificar_vencimiento(a),
            "sin_responsable": a.responsable_id is None,
            "bloqueada": a.estado_operativo == A.BLOQUEADA,
            "motivo_bloqueo": a.motivo_bloqueo,
            "esperando_dependencia": bool(a.depende_de_id
                                          and a.bloqueada_por_dependencia),
            "vuelta": a.vuelta,
        })

    completadas_sin_validar = [f for f in filas
                               if f["estado"] == A.COMPLETADA
                               and f["validacion"] != "aprobado"]
    return {
        "actividades": filas,
        "cuantas": len(filas),
        "resumen": actividades.resumen(qs),
        #  La distincion que el bloque pide que no se pierda.
        "completadas_sin_validar": len(completadas_sin_validar),
    }


# =============================================================================
#  §5  --  M03: SE CONSULTA Y SE RECOMIENDA. NO SE ESCRIBE.
# =============================================================================
#
#  POR QUE M02 SI ESCRIBE Y M03 NO, con la escalera del propio bloque en la mano
#  ----------------------------------------------------------------------------
#  No es una asimetria arbitraria: sale de leer §7 con cuidado.
#
#    Nivel 2 = "coordinar actividades; solicitar evidencias". Eso es M02: pedir
#              que alguien haga algo. Es reversible --'actividades.cancelar'-- y
#              no cambia ningun compromiso que ya exista con un cliente.
#
#    Nivel 3 = "unicamente acciones previamente autorizadas y reversibles". Eso
#              es M03: reprogramar una orden mueve una visita que ya se le
#              prometio a alguien, y resecuenciar una jornada reordena trabajo
#              que un tecnico ya tiene.
#
#  Y el nivel 3 exige "previamente autorizadas". En el CRM NO EXISTE registro de
#  autorizacion por accion: el que hay ('asistente.autorizacion_herramienta')
#  esta en el motor, cubre herramientas del motor y tenia 0 filas la ultima vez
#  que se midio. Asi que la primera de las ocho condiciones de §5 no se puede
#  cumplir hoy, y §7 es explicito: "Si alguna barrera no existe para una accion
#  M02/M03, NO implementarla como accion automatica".
#
#  Por eso aqui no hay ninguna llamada a 'reprogramar_orden',
#  'actualizar_secuencia', 'secuenciar_jornada' ni 'registrar_contingencia'. Lo
#  que hay es: leer el estado real, y dejar una PropuestaSupervisor de nivel 1
#  --que si esta permitido-- para que una persona decida.
#
#  Lo que falta para que M03 se pueda ejecutar esta escrito en el informe del
#  bloque, no resuelto a escondidas aqui.

from operaciones import capacidad as cap  # noqa: E402
from operaciones import novedades as inc  # noqa: E402
from operaciones import programacion as prog  # noqa: E402
from operaciones import sla as sla_mod  # noqa: E402
from operaciones import supervisor as sup  # noqa: E402

#  Los estados de plazo que son un problema, separados de los que no lo son.
PLAZOS_EN_RIESGO = (sla_mod.VENCIDA, sla_mod.VENCE_PRONTO)


def panorama_m03(org, *, dia=None, ahora=None) -> dict:
    """
    Lo que §5 pide CONSULTAR, resuelto en una lectura y sin escribir nada.

    Reutiliza los modulos que ya hacen cada cuenta --'capacidad_de_jornada',
    'lineas_de_jornada', 'resumen_de_jornada', 'sla.plazo_de',
    'novedades.sin_resolver'-- en vez de recalcularlas. Si alguno cambia su
    regla, esto la hereda; una copia se quedaria con la regla vieja.

    LO QUE DEVUELVE Y NO DEVUELVE: devuelve el veredicto de capacidad TAL CUAL
    lo da 'capacidad.py', incluido 'CAPACIDAD_NO_DETERMINABLE'. Eso es a
    proposito -- "no se puede determinar" NO es "no hay sobrecarga", y colapsar
    los dos es exactamente el error que la capa de fuentes existe para no
    repetir.
    """
    ahora = ahora or timezone.now()
    dia = dia or timezone.localtime(ahora).date()

    lineas = list(prog.lineas_de_jornada(org, dia=dia))
    capa = cap.capacidad_de_jornada(org, dia)

    en_riesgo = []
    sin_plazo_medible = 0
    for linea in lineas:
        plazo = sla_mod.plazo_de(linea.orden, ahora=ahora)
        estado = plazo.get("estado")
        if estado == sla_mod.DATOS_INSUFICIENTES:
            sin_plazo_medible += 1
        if estado in PLAZOS_EN_RIESGO:
            en_riesgo.append({
                "orden_id": str(linea.orden_id),
                "linea_id": str(linea.id),
                "dia": linea.dia.isoformat() if linea.dia else None,
                "secuencia": linea.secuencia,
                "zona": linea.zona,
                "estado_plazo": estado,
                "resumen": sla_mod.resumen(plazo),
            })

    novedades_abiertas = list(inc.sin_resolver(org, ahora=ahora)[:25])

    return {
        "dia": dia.isoformat(),
        "lineas_programadas": len(lineas),
        "resumen_jornada": prog.resumen_de_jornada(lineas),
        "capacidad": capa,
        "ordenes_en_riesgo_de_plazo": en_riesgo,
        "cuantas_en_riesgo": len(en_riesgo),
        #  Se cuenta aparte a proposito: una orden cuyo plazo no se puede medir
        #  no esta "a tiempo", esta sin medir.
        "ordenes_sin_plazo_medible": sin_plazo_medible,
        "novedades_sin_resolver": [
            {"id": str(n.id), "tipo": n.tipo, "estado": n.estado,
             "descripcion": n.descripcion[:160]} for n in novedades_abiertas],
        "contingencias_abiertas": len(novedades_abiertas),
    }


def recomendar_programacion(situacion, *, actor=None, accion: str, motivo: str,
                            evidencia: list, impacto: str = "",
                            prioridad: int = 50, ahora=None):
    """
    Deja una PropuestaSupervisor de nivel 1 atada a esta situacion.

    Es el camino de M03: recomendar, no ejecutar. Reutiliza
    'supervisor.registrar_propuesta' --con su evidencia obligatoria, su
    expiracion y su version de habilidad-- y 'supervisor._ya_propuesta' para no
    emitir dos veces la misma, en vez de un segundo sistema de propuestas, que
    §8 prohibe explicitamente y con razon.

    NIVEL: siempre 'NIVEL_RECOMENDAR', fijado en el codigo. No se parametriza.
    Una funcion que acepta el nivel como argumento es una funcion a la que se le
    puede pedir nivel 3, y ese es justo el camino que no tiene que existir.

    Devuelve la propuesta, o None si ya habia una viva para la misma condicion.
    """
    ahora = ahora or timezone.now()
    org = situacion.org

    accion = (accion or "").strip()
    motivo = (motivo or "").strip()
    if not accion:
        raise CoordinacionInvalida("falta la acción que se recomienda")
    if not motivo:
        raise CoordinacionInvalida(
            "falta el motivo: una recomendación sin por qué no se puede decidir")
    if not evidencia:
        raise CoordinacionInvalida(
            "falta la evidencia: 'PropuestaSupervisor' la exige por constraint "
            "de base, y una recomendación sin respaldo es una opinión")

    _exigir_situacion_viva(situacion)

    #  La huella lleva la situacion y la accion, no una magnitud que avanza
    #  sola: si llevara los minutos que faltan para el plazo, cada ciclo veria
    #  una condicion nueva y una propuesta rechazada volveria al minuto
    #  siguiente. Es la misma leccion que 'Senal.huella' documenta.
    senal = sup.Senal(
        tipo=P.ORDEN_EN_RIESGO,
        origen_tipo=ORIGEN_SITUACION,
        origen_id=str(situacion.id),
        evidencia=list(evidencia),
        datos={"situacion": situacion.codigo},
        #  'huella_condicion' admite 64 caracteres y un UUID ya son 36, asi que
        #  la accion va HASHEADA y no recortada: dos acciones distintas que
        #  empiecen igual tienen que dar huellas distintas, o la segunda se
        #  leeria como repetida y no se emitiria nunca. Medido: con el recorte,
        #  'full_clean' rechazaba la propuesta con 79 caracteres.
        huella=f"sit:{situacion.id}:{_firma(accion)}",
    )

    #  La MISMA deduplicacion que usa el ciclo del Supervisor. Sin esto, cada
    #  llamada dejaria otra propuesta identica esperando decision.
    if sup._ya_propuesta(org, senal):
        svc.anotar(situacion, TipoEvento.RECOMENDACION,
                   f"Ya estaba recomendado: {accion[:180]}",
                   datos={"accion": accion, "repetida": True,
                          "nivel": P.NIVEL_RECOMENDAR},
                   actor=actor, ocurrido_en=ahora)
        return None

    analisis = {
        "accion_propuesta": accion[:255],
        "motivo": motivo,
        "prioridad": int(prioridad),
        "impacto": impacto or "",
        #  El techo, escrito aqui y no heredado por accidente.
        "nivel": P.NIVEL_RECOMENDAR,
        "componentes_prioridad": [f"situacion {situacion.codigo}",
                                  f"riesgo {situacion.riesgo}"],
    }
    propuesta = sup.registrar_propuesta(org, senal, analisis, ahora=ahora)

    svc.anotar(situacion, TipoEvento.RECOMENDACION,
               f"Recomendación de programación: {accion[:180]}",
               datos={"propuesta_id": str(propuesta.id),
                      "accion": accion, "impacto": impacto,
                      "nivel": P.NIVEL_RECOMENDAR},
               actor=actor, ocurrido_en=ahora)
    return propuesta
