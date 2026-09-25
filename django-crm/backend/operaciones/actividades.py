# -*- coding: utf-8 -*-
"""
================================================================================
 ACTIVIDADES OPERATIVAS  --  paso M02
================================================================================

Lo que FALTA hacer: tareas, pendientes, compromisos, dependencias, handoffs.

LA ENTIDAD YA EXISTIA. LO QUE FALTABA ERA PODER OPERARLA
--------------------------------------------------------
'operaciones.ActividadOperativa' estaba completa --nueve tipos, dos ejes de
estado, dependencia propia, motivo de bloqueo con CHECK en la base, tres
indices, RLS habilitada Y FORZADA-- y el Supervisor ya la leia con cinco
detectores. Lo que no habia era una sola forma de crear una actividad o de
moverla de estado que no fuera el panel de Django.

Este modulo es esa capa, y nada mas: no crea entidades, no redefine estados y
no toca lo que M09 ya consume.

ACTIVIDAD OPERATIVA NO ES common.Activity
-----------------------------------------
'common.Activity' es la bitacora del CRM: lo que YA paso, en pasado, sin estado
ni vencimiento -- 610 filas vivas en produccion. Aqui se ESCRIBE en ella (via
operaciones.auditoria) un hecho consumado por cada transicion, que es
exactamente para lo que esta hecha. Lo que falta hacer vive en la otra tabla.
La distincion la declaro el propio modelo y este modulo la respeta.

DOS EJES, NO UNO
----------------
'estado_operativo' dice si avanza. 'estado_validacion' dice si alguien la dio
por buena. Completar NO es cerrar: una actividad completada que espera
validacion sigue visible, y una devuelta vuelve a gestion con 'vuelta' + 1.
Con un solo eje habria que elegir, y se perderia el caso real --"completada y
requiere correccion"-- que la devolucion produce.

LO QUE NO HACE
--------------
No asigna responsables por su cuenta, no cierra nada automaticamente, no
reprograma, no escala solo y no llama a ningun sistema externo. El Supervisor
podra PROPONER; ejecutar es de una persona.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from operaciones import auditoria
from operaciones.models import (APROBADO, REQUIERE_CORRECCION,
                                REQUIERE_REVISION, SIN_EVALUAR,
                                VALIDACION_PENDIENTE, ActividadOperativa)

A = ActividadOperativa

#  Profundidad maxima al buscar ciclos de dependencia. Una cadena mas larga que
#  esto no es una dependencia operativa: es un error de datos, y se trata como
#  tal en vez de recorrerla para siempre.
PROFUNDIDAD_MAXIMA_DEPENDENCIA = 64

#  Ventana por defecto de "vence pronto". NO es un valor nuevo: es el mismo que
#  usa el detector 'compromiso_por_vencer' de M09
#  (supervisor.HORAS_COMPROMISO_POR_VENCER). Se importa tarde para no crear un
#  ciclo de imports, y quien consulta puede pasar otra ventana explicita.
def _ventana_por_defecto() -> int:
    from operaciones.supervisor import HORAS_COMPROMISO_POR_VENCER
    return HORAS_COMPROMISO_POR_VENCER


# ==============================================================================
#  ERRORES
# ==============================================================================

class ErrorActividad(Exception):
    """Algo impide la operacion. El mensaje va al operador, no al log."""


class TransicionInvalida(ErrorActividad):
    """Ese salto de estado no existe en la maquina."""


class DependenciaCiclica(ErrorActividad):
    """La dependencia cerraria un circulo y nada podria avanzar nunca."""


class ActividadDuplicada(ErrorActividad):
    """Ya hay una actividad viva igual para el mismo origen."""


# ==============================================================================
#  MAQUINA DE ESTADOS
# ==============================================================================
#  Explicita a proposito. Una transicion que no este aca no ocurre, y agregar
#  una obliga a escribirla -- que es lo contrario de descubrir en produccion
#  que algo paso de 'cancelada' a 'en gestion' porque nadie lo penso.

TRANSICIONES = {
    A.PENDIENTE: {A.EN_GESTION, A.EN_ESPERA, A.BLOQUEADA, A.ESCALADA,
                  A.COMPLETADA, A.CANCELADA},
    A.EN_GESTION: {A.EN_ESPERA, A.BLOQUEADA, A.ESCALADA, A.COMPLETADA,
                   A.CANCELADA},
    A.EN_ESPERA: {A.EN_GESTION, A.BLOQUEADA, A.ESCALADA, A.COMPLETADA,
                  A.CANCELADA},
    A.BLOQUEADA: {A.PENDIENTE, A.EN_GESTION, A.EN_ESPERA, A.ESCALADA,
                  A.CANCELADA},
    A.ESCALADA: {A.EN_GESTION, A.EN_ESPERA, A.BLOQUEADA, A.COMPLETADA,
                 A.CANCELADA},
    #  Completada NO es terminal del todo: una validacion devuelta la reabre a
    #  gestion. Cancelada si lo es -- reabrir una cancelacion seria otra
    #  actividad, no la misma.
    A.COMPLETADA: {A.EN_GESTION},
    A.CANCELADA: set(),
}


def _bloquear(actividad) -> ActividadOperativa:
    """
    Relee la fila bajo lock. Lo que decide es la fila bloqueada, no la copia en
    memoria -- mismo criterio que 'programar_orden' en M03.
    """
    return A.objects.select_for_update().get(pk=actividad.pk)


def _exigir_transicion(actual: str, nuevo: str) -> None:
    if nuevo not in TRANSICIONES.get(actual, set()):
        raise TransicionInvalida(
            f"Una actividad '{actual}' no puede pasar a '{nuevo}'.")


def _auditar(actividad, actor, accion, *, anterior="", nuevo="",
             motivo="", descripcion="", extra=None):
    return auditoria.registrar(
        org=actividad.org, actor=actor, accion=accion,
        entidad=auditoria.ENTIDAD_ACTIVIDAD, entidad_id=actividad.id,
        nombre=actividad.titulo, descripcion=descripcion,
        estado_anterior=anterior, estado_nuevo=nuevo, motivo=motivo,
        extra=extra,
    )


def _cambiar_estado(actividad, actor, nuevo, *, motivo="", accion="STATUS_CHANGED",
                    campos=None, descripcion="", extra=None):
    """
    El unico sitio donde cambia 'estado_operativo'. Todo pasa por aca.

    'extra' viaja a la metadata de la auditoria: lo usa el escalamiento para
    dejar escrito destinatario y nivel en la MISMA fila que registra el cambio
    de estado. Guardarlos en dos filas distintas permitiria que una existiera
    sin la otra.
    """
    anterior = actividad.estado_operativo
    _exigir_transicion(anterior, nuevo)
    actividad.estado_operativo = nuevo
    a_guardar = ["estado_operativo", "updated_at"] + list(campos or [])
    actividad.save(update_fields=a_guardar)
    _auditar(actividad, actor, accion, anterior=anterior, nuevo=nuevo,
             motivo=motivo, descripcion=descripcion, extra=extra)
    return actividad


# ==============================================================================
#  CREAR
# ==============================================================================

@transaction.atomic
def crear(*, org, actor, tipo=A.TAREA, titulo: str, descripcion: str = "",
          responsable=None, origen_tipo: str = "", origen_id: str = "",
          vence_en=None, depende_de=None,
          evitar_duplicado: bool = True) -> ActividadOperativa:
    """
    Una actividad nueva. Nace PENDIENTE y SIN_EVALUAR.

    'org' sale de la sesion, nunca del cuerpo de la peticion: lo que el cliente
    no debe elegir, no se declara -- misma decision que ProgramarSerializer en
    M03-B.

    UN COMPROMISO SIN FECHA ES LEGITIMO
    -----------------------------------
    No se le inventa una. 'vence_en' queda en null y quien consulte lo vera
    como SIN_VENCIMIENTO, que es un dato distinto de "vence hoy".
    """
    if not (titulo or "").strip():
        raise ErrorActividad("Una actividad sin título no se puede buscar ni leer.")
    if tipo not in dict(A.TIPOS):
        raise ErrorActividad(f"'{tipo}' no es un tipo de actividad.")
    if responsable is not None and responsable.org_id != org.id:
        raise ErrorActividad("Esa persona es de otra empresa.")
    if vence_en is not None and timezone.is_naive(vence_en):
        raise ErrorActividad("La fecha de vencimiento tiene que traer zona horaria.")

    if evitar_duplicado and origen_tipo and origen_id:
        ya = (A.objects.filter(org=org, tipo=tipo, origen_tipo=origen_tipo,
                               origen_id=origen_id)
              .exclude(estado_operativo__in=A.ESTADOS_FINALES).first())
        if ya is not None:
            raise ActividadDuplicada(
                f"Ya hay una actividad '{tipo}' viva para ese origen "
                f"({origen_tipo} {origen_id}): {ya.titulo}.")

    if depende_de is not None:
        if depende_de.org_id != org.id:
            raise ErrorActividad("Esa dependencia es de otra empresa.")

    actividad = A.objects.create(
        org=org, tipo=tipo, titulo=titulo.strip(), descripcion=descripcion,
        responsable=responsable, origen_tipo=origen_tipo, origen_id=origen_id,
        vence_en=vence_en, depende_de=depende_de,
        estado_operativo=A.PENDIENTE, estado_validacion=SIN_EVALUAR,
    )
    _auditar(actividad, actor, "CREATE", nuevo=A.PENDIENTE,
             descripcion=f"Creada como '{actividad.get_tipo_display()}'.",
             extra={"tipo": tipo, "origen_tipo": origen_tipo,
                    "origen_id": origen_id,
                    "con_vencimiento": vence_en is not None})
    return actividad


# ==============================================================================
#  RESPONSABLE
# ==============================================================================

@transaction.atomic
def asignar_responsable(actividad, *, actor, responsable, motivo: str = ""):
    """
    Pone o cambia al responsable. 'responsable=None' lo quita, y eso es
    legitimo: una actividad sin responsable es una senal, no un error -- lo
    dice el propio help_text del campo, y M09 tiene un detector para ella.

    NO la asigna nadie automaticamente. El Supervisor podra proponer.
    """
    fresca = _bloquear(actividad)
    if fresca.estado_operativo in A.ESTADOS_FINALES:
        raise ErrorActividad(
            f"La actividad está '{fresca.estado_operativo}'. No se le cambia "
            f"el responsable a algo que ya terminó.")
    if responsable is not None and responsable.org_id != fresca.org_id:
        raise ErrorActividad("Esa persona es de otra empresa.")

    anterior = fresca.responsable
    if (anterior.id if anterior else None) == (responsable.id if responsable else None):
        return fresca, False          # no-op: no escribe y no audita

    fresca.responsable = responsable
    fresca.save(update_fields=["responsable", "updated_at"])
    _auditar(fresca, actor, "ASSIGN", motivo=motivo,
             descripcion="Cambio de responsable.",
             extra={"anterior": str(anterior.id) if anterior else None,
                    "nuevo": str(responsable.id) if responsable else None})
    return fresca, True


# ==============================================================================
#  TRANSICIONES DE ESTADO
# ==============================================================================

@transaction.atomic
def iniciar_gestion(actividad, *, actor, motivo: str = ""):
    fresca = _bloquear(actividad)
    if fresca.estado_operativo == A.BLOQUEADA:
        raise ErrorActividad(
            "La actividad está bloqueada. Hay que desbloquearla primero, y "
            "eso deja dicho por qué dejó de estarlo.")
    return _cambiar_estado(fresca, actor, A.EN_GESTION, motivo=motivo)


@transaction.atomic
def poner_en_espera(actividad, *, actor, motivo: str = ""):
    """
    EN_ESPERA es distinto de BLOQUEADA: aqui se espera algo previsto --una
    respuesta, una fecha-- y alla hay un impedimento con causa. Mezclarlos
    haria que el Supervisor no pudiera distinguir "va lento" de "esta trabado".
    """
    fresca = _bloquear(actividad)
    return _cambiar_estado(fresca, actor, A.EN_ESPERA, motivo=motivo)


@transaction.atomic
def bloquear(actividad, *, actor, motivo: str):
    """
    Bloquear EXIGE motivo, y no por formalismo: sin causa, el Supervisor no
    puede distinguir "falta material" de "no sabemos". La base tambien lo
    exige (CHECK 'actividad_bloqueada_exige_motivo'), asi que esto no depende
    de que alguien se acuerde.

    Un bloqueo NO atribuye culpa a nadie: describe un impedimento.
    """
    if not (motivo or "").strip():
        raise ErrorActividad("Un bloqueo necesita su causa.")
    fresca = _bloquear(actividad)
    fresca.motivo_bloqueo = motivo.strip()[:255]
    return _cambiar_estado(fresca, actor, A.BLOQUEADA, motivo=motivo,
                           campos=["motivo_bloqueo"],
                           descripcion="Bloqueada.")


@transaction.atomic
def desbloquear(actividad, *, actor, motivo: str = "", destino=A.EN_GESTION):
    """Sale del bloqueo y el motivo se limpia: ya no esta bloqueada por eso."""
    fresca = _bloquear(actividad)
    if fresca.estado_operativo != A.BLOQUEADA:
        raise ErrorActividad("Esa actividad no está bloqueada.")
    if destino not in (A.PENDIENTE, A.EN_GESTION, A.EN_ESPERA):
        raise ErrorActividad("Al desbloquear solo se vuelve a pendiente, "
                             "gestión o espera.")
    causa_previa = fresca.motivo_bloqueo
    fresca.motivo_bloqueo = ""
    return _cambiar_estado(fresca, actor, destino, motivo=motivo,
                           campos=["motivo_bloqueo"],
                           descripcion=f"Desbloqueada (era: {causa_previa}).")


@transaction.atomic
def escalar(actividad, *, actor, motivo: str, escalado_a, nivel: str):
    """
    Pasa a otro nivel. Es un ESTADO, no un objeto nuevo -- lo declara el propio
    modelo.

    LOS TRES DATOS SON OBLIGATORIOS  (paso M05-B)
    ---------------------------------------------
    Antes bastaba el motivo, y eso dejaba un escalamiento que no llegaba a
    nadie: el estado decia "alguien pidio ayuda" sin decir a quien, asi que no
    habia forma de saber si la habia pedido bien. Ahora exige ademas
    destinatario y nivel.

    NO HAY DESTINATARIO POR DEFECTO, Y ES DELIBERADO
    ------------------------------------------------
    'cases.EscalationPolicy' resuelve destinatario a partir de 'Case.priority'.
    Una actividad no tiene esa prioridad, y construir el puente
    actividad -> caso -> prioridad -> politica seria inventar una semantica que
    nadie definio. Hasta que exista una politica operacional propia, el
    destinatario lo pone quien escala. Si no lo hay, esto se rechaza y el
    Supervisor lo dice en vez de elegir por su cuenta.

    REESCALAR NO SE PUEDE, Y NO ES UNA REGLA NUEVA
    ----------------------------------------------
    'TRANSICIONES[ESCALADA]' no se incluye a si misma: el proyecto ya decidia
    que una actividad escalada no vuelve a escalarse de golpe. Se respeta tal
    cual -- '_exigir_transicion' lo rechaza-- en vez de abrir esa puerta aqui.
    Para llevarla a otra instancia hay que devolverla a gestion primero, y ese
    camino queda escrito en la auditoria paso a paso.
    """
    if not (motivo or "").strip():
        raise ErrorActividad("Un escalamiento necesita su motivo.")
    if escalado_a is None:
        raise ErrorActividad(
            "Un escalamiento necesita destinatario: sin alguien que lo reciba, "
            "el estado 'escalada' no le llega a nadie.")
    if nivel not in dict(A.NIVELES_ESCALAMIENTO):
        raise ErrorActividad(
            f"'{nivel}' no es un nivel de escalamiento. Los niveles son: "
            f"{', '.join(dict(A.NIVELES_ESCALAMIENTO))}.")

    fresca = _bloquear(actividad)

    #  AISLAMIENTO POR ORGANIZACION. Se compara contra 'Profile.org', que es la
    #  misma convencion que usa el resto del modulo -- no una segunda logica de
    #  tenancy. Escalar a alguien de otra empresa filtraria el trabajo de un
    #  cliente al personal de otro.
    if escalado_a.org_id != fresca.org_id:
        raise ErrorActividad(
            "El destinatario pertenece a otra organización. Una actividad solo "
            "se escala dentro de su propia empresa.")

    fresca.escalado_a = escalado_a
    fresca.escalado_en = timezone.now()
    fresca.nivel_escalamiento = nivel
    return _cambiar_estado(
        fresca, actor, A.ESCALADA, motivo=motivo, accion="ESCALATED",
        campos=["escalado_a", "escalado_en", "nivel_escalamiento"],
        descripcion=f"Escalada a nivel {dict(A.NIVELES_ESCALAMIENTO)[nivel]}.",
        extra={"escalado_a": str(escalado_a.id),
               "nivel_escalamiento": nivel,
               "escalado_en": fresca.escalado_en.isoformat()})


@transaction.atomic
def completar(actividad, *, actor, requiere_validacion: bool = False,
              motivo: str = ""):
    """
    Marca el trabajo hecho. COMPLETAR NO ES CERRAR.

    Si requiere validacion, el eje operativo queda COMPLETADA y el de
    validacion PENDIENTE: la actividad sigue visible para quien valida. Solo
    'validar' resuelve ese segundo eje.
    """
    fresca = _bloquear(actividad)
    if fresca.estado_operativo == A.BLOQUEADA:
        raise ErrorActividad(
            "La actividad está bloqueada. Completar algo trabado tapa el "
            "impedimento en vez de resolverlo: desbloquéela primero.")
    if fresca.depende_de_id and fresca.bloqueada_por_dependencia:
        raise ErrorActividad(
            "Depende de otra actividad que todavía no termina.")

    fresca.completado_en = timezone.now()
    fresca.estado_validacion = (VALIDACION_PENDIENTE if requiere_validacion
                                else fresca.estado_validacion)
    return _cambiar_estado(
        fresca, actor, A.COMPLETADA, motivo=motivo,
        campos=["completado_en", "estado_validacion"],
        descripcion=("Completada, pendiente de validación."
                     if requiere_validacion else "Completada."))


@transaction.atomic
def validar(actividad, *, actor, decision: str, motivo: str = ""):
    """
    Resuelve el eje de validacion. 'decision' es 'aprobado', 'requiere_correccion'
    o 'requiere_revision'.

    Una devolucion NO borra lo hecho: sube 'vuelta' y devuelve la actividad a
    gestion, que es el caso real que un solo eje de estado no sabria expresar.
    """
    if decision not in (APROBADO, REQUIERE_CORRECCION, REQUIERE_REVISION):
        raise ErrorActividad(f"'{decision}' no es una decisión de validación.")
    fresca = _bloquear(actividad)
    if fresca.estado_validacion != VALIDACION_PENDIENTE:
        raise ErrorActividad(
            f"Esa actividad no está esperando validación "
            f"(su validación está en '{fresca.estado_validacion}').")
    if decision == REQUIERE_CORRECCION and not (motivo or "").strip():
        raise ErrorActividad("Devolver para corrección exige decir qué corregir.")

    anterior = fresca.estado_validacion
    fresca.estado_validacion = decision

    if decision == REQUIERE_CORRECCION:
        fresca.vuelta += 1
        fresca.completado_en = None       # ya no esta completada
        fresca.validado_en = None
        fresca.estado_operativo = A.EN_GESTION
        fresca.save(update_fields=["estado_validacion", "vuelta",
                                   "completado_en", "validado_en",
                                   "estado_operativo", "updated_at"])
        _auditar(fresca, actor, "REJECTED", anterior=anterior, nuevo=decision,
                 motivo=motivo, descripcion=f"Devuelta. Vuelta {fresca.vuelta}.")
        return fresca

    fresca.validado_en = timezone.now()
    fresca.save(update_fields=["estado_validacion", "validado_en", "updated_at"])
    _auditar(fresca, actor,
             "APPROVED" if decision == APROBADO else "APPROVAL_REQUESTED",
             anterior=anterior, nuevo=decision, motivo=motivo,
             descripcion="Validación resuelta.")
    return fresca


@transaction.atomic
def cancelar(actividad, *, actor, motivo: str):
    """
    Cancelar NO es completar, y no borra nada: la fila queda con quien canceló,
    cuándo y por qué. Exige motivo -- una cancelación sin causa no se puede
    revisar después.
    """
    if not (motivo or "").strip():
        raise ErrorActividad("Una cancelación necesita su motivo.")
    fresca = _bloquear(actividad)
    return _cambiar_estado(fresca, actor, A.CANCELADA, motivo=motivo,
                           descripcion="Cancelada.")


# ==============================================================================
#  DEPENDENCIAS
# ==============================================================================

def _cadena_llega_a(origen, destino_id, limite=PROFUNDIDAD_MAXIMA_DEPENDENCIA):
    """Recorre 'depende_de' hacia arriba buscando 'destino_id'."""
    visto = set()
    actual = origen
    for _ in range(limite):
        if actual is None:
            return False
        if actual.id == destino_id:
            return True
        if actual.id in visto:          # ciclo preexistente en los datos
            return False
        visto.add(actual.id)
        actual = actual.depende_de
    raise DependenciaCiclica(
        "La cadena de dependencias es demasiado larga para comprobarla; "
        "revísela a mano antes de agregar otra.")


@transaction.atomic
def establecer_dependencia(actividad, *, actor, depende_de, motivo: str = ""):
    """
    'actividad' no puede avanzar hasta que 'depende_de' termine.

    LOS CICLOS SE RECHAZAN, Y SE COMPRUEBA LA CADENA ENTERA
    -------------------------------------------------------
    El modelo ya impedia el ciclo de largo 1 (depender de si misma) en su
    clean(). Aca se recorre la cadena hacia arriba: si desde el candidato se
    llega de vuelta a esta actividad, el circulo se cerraria y ninguna de las
    dos avanzaria nunca. Es validacion de SERVICIO, no de base: PostgreSQL no
    puede expresar "sin ciclos" en una constraint.
    """
    fresca = _bloquear(actividad)
    if depende_de is None:
        previa = fresca.depende_de_id
        if previa is None:
            return fresca, False
        fresca.depende_de = None
        fresca.save(update_fields=["depende_de", "updated_at"])
        _auditar(fresca, actor, "UNLINKED_PARENT", motivo=motivo,
                 descripcion="Se quitó la dependencia.",
                 extra={"anterior": str(previa)})
        return fresca, True

    if depende_de.org_id != fresca.org_id:
        raise ErrorActividad("Esa dependencia es de otra empresa.")
    if depende_de.id == fresca.id:
        raise DependenciaCiclica("Una actividad no puede depender de sí misma.")

    #  Se RELEE el candidato antes de recorrer su cadena. El objeto que llega
    #  por parametro pudo leerse hace rato y traer un 'depende_de' viejo: con
    #  una copia rancia el recorrido no encuentra el ciclo y lo deja pasar.
    #  Lo midio una prueba (test_15, ciclo de largo 3) antes de que llegara a
    #  ninguna parte.
    candidato = A.objects.get(pk=depende_de.pk)
    if _cadena_llega_a(candidato, fresca.id):
        raise DependenciaCiclica(
            "Esa dependencia cerraría un círculo: la otra actividad ya "
            "depende de ésta, directa o indirectamente.")

    fresca.depende_de = candidato
    fresca.save(update_fields=["depende_de", "updated_at"])
    _auditar(fresca, actor, "LINKED_PARENT", motivo=motivo,
             descripcion="Se agregó una dependencia.",
             extra={"depende_de": str(candidato.id)})
    return fresca, True


# ==============================================================================
#  VENCIMIENTO
# ==============================================================================

VENCIDA = "VENCIDA"
VENCE_PRONTO = "VENCE_PRONTO"
A_TIEMPO = "A_TIEMPO"
SIN_VENCIMIENTO = "SIN_VENCIMIENTO"
CERRADA = "CERRADA"


def clasificar_vencimiento(actividad, ahora=None, ventana_horas=None) -> str:
    """
    Cuatro respuestas distintas, y la cuarta importa: SIN_VENCIMIENTO no es
    "vence hoy" ni "no vence nunca" -- es que nadie declaro una fecha, y un
    compromiso sin fecha es legitimo (no se le inventa una).

    'ventana_horas' es EXPLICITA. Por defecto toma la misma que ya usa el
    detector de M09, no un valor nuevo.
    """
    ahora = ahora or timezone.now()
    if actividad.estado_operativo in A.ESTADOS_FINALES:
        return CERRADA
    if actividad.vence_en is None:
        return SIN_VENCIMIENTO
    if actividad.vence_en < ahora:
        return VENCIDA
    horas = _ventana_por_defecto() if ventana_horas is None else ventana_horas
    if actividad.vence_en <= ahora + timedelta(hours=horas):
        return VENCE_PRONTO
    return A_TIEMPO


@transaction.atomic
def cambiar_vencimiento(actividad, *, actor, vence_en, motivo: str = ""):
    """
    Mover una fecha comprometida es una decision, no un ajuste: queda auditada
    con la anterior y la nueva. 'vence_en=None' la quita.
    """
    if vence_en is not None and timezone.is_naive(vence_en):
        raise ErrorActividad("La fecha de vencimiento tiene que traer zona horaria.")
    fresca = _bloquear(actividad)
    if fresca.estado_operativo in A.ESTADOS_FINALES:
        raise ErrorActividad(
            f"La actividad está '{fresca.estado_operativo}'. No se le mueve la "
            f"fecha a algo que ya terminó.")
    anterior = fresca.vence_en
    if anterior == vence_en:
        return fresca, False
    fresca.vence_en = vence_en
    fresca.save(update_fields=["vence_en", "updated_at"])
    _auditar(fresca, actor, "UPDATE", motivo=motivo,
             descripcion="Cambio de fecha comprometida.",
             extra={"anterior": anterior.isoformat() if anterior else None,
                    "nueva": vence_en.isoformat() if vence_en else None})
    return fresca, True


# ==============================================================================
#  CONSULTA
# ==============================================================================

def pendientes_relevantes(org, *, responsable=None, tipo=None, estado=None,
                          solo_abiertas=True, ahora=None, ventana_horas=None):
    """
    Lo que hay que mirar. Es una LECTURA: no escribe nada.

    Acotada SIEMPRE a 'org'. Quien consulta no elige la organizacion: sale de
    su sesion.
    """
    qs = A.objects.filter(org=org).select_related("responsable__user", "depende_de")
    if solo_abiertas:
        qs = qs.exclude(estado_operativo__in=A.ESTADOS_FINALES)
    if responsable is not None:
        qs = qs.filter(responsable=responsable)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if estado:
        qs = qs.filter(estado_operativo=estado)
    return qs.order_by("vence_en", "-created_at")


def resumen(actividades, ahora=None, ventana_horas=None) -> dict:
    """Los conteos que el Supervisor y una bandeja necesitan de un vistazo."""
    ahora = ahora or timezone.now()
    filas = list(actividades)
    por_vencimiento = {}
    for a in filas:
        k = clasificar_vencimiento(a, ahora, ventana_horas)
        por_vencimiento[k] = por_vencimiento.get(k, 0) + 1
    return {
        "total": len(filas),
        "sin_responsable": sum(1 for a in filas if a.responsable_id is None),
        "bloqueadas": sum(1 for a in filas if a.estado_operativo == A.BLOQUEADA),
        "esperando_dependencia": sum(
            1 for a in filas if a.bloqueada_por_dependencia),
        "esperando_validacion": sum(
            1 for a in filas if a.estado_validacion == VALIDACION_PENDIENTE),
        "por_vencimiento": por_vencimiento,
    }
