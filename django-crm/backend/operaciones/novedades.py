# -*- coding: utf-8 -*-
"""
================================================================================
 INCIDENCIAS  --  el ciclo de vida de una NovedadOperativa  (paso M05-A)
================================================================================

LA REGLA QUE GOBIERNA ESTE MODULO
---------------------------------
    DESBLOQUEAR UNA ACTIVIDAD NO RESUELVE UNA INCIDENCIA.

Son dos hechos distintos y hay que poder distinguirlos:

    "la actividad ya no esta bloqueada"   <- estado del trabajo
    "la causa operacional ya se atendio"  <- estado de la incidencia

Un tecnico puede desbloquear para seguir avanzando por otra via mientras el
material sigue sin llegar. Si el sistema dedujera lo segundo de lo primero,
daria por cerrada una causa que nadie atendio, y despues mediria, escalaria y
reportaria sobre esa mentira.

Por eso el estado se PERSISTE en 'NovedadOperativa.estado' y solo cambia por
una de las tres operaciones de aqui. Ningun servicio de M02 ni de M03 lo toca.

ABIERTA -> EN_GESTION -> RESUELTA
---------------------------------
    ABIERTA     -> EN_GESTION, RESUELTA
    EN_GESTION  -> RESUELTA
    RESUELTA    -> (nada)

No hay reapertura. No existe hoy en el proyecto y no se inventa en este paso:
una transicion que nadie diseño es una puerta que despues hay que cerrar.

RESOLVER EXIGE DECIR COMO
-------------------------
'resolucion' es obligatoria. Sin explicacion no se puede distinguir una causa
atendida de una que alguien marco para sacarla de la lista, y esa diferencia es
justo lo que hace util el registro.
================================================================================
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from operaciones import auditoria
from operaciones.models import NovedadOperativa

N = NovedadOperativa


class ErrorIncidencia(Exception):
    """La transicion pedida no es valida para el estado actual."""


def _fresca(novedad) -> NovedadOperativa:
    """
    Relee la fila BLOQUEADA. Entre leer el estado y escribirlo cabe otra
    transicion: sin el bloqueo, dos resoluciones simultaneas pisarian una a la
    otra y la segunda ganaria en silencio.
    """
    return N.objects.select_for_update().get(pk=novedad.pk)


def _exigir_transicion(actual: str, nuevo: str) -> None:
    permitidas = N.TRANSICIONES.get(actual, ())
    if nuevo not in permitidas:
        legibles = ", ".join(permitidas) if permitidas else "ninguna"
        raise ErrorIncidencia(
            f"Una incidencia en '{actual}' no puede pasar a '{nuevo}'. "
            f"Desde '{actual}' solo se puede ir a: {legibles}.")


def _auditar(novedad, actor, accion, *, anterior="", nuevo="", motivo="",
             descripcion="", extra=None):
    return auditoria.registrar(
        org=novedad.org, actor=actor, accion=accion,
        entidad=auditoria.ENTIDAD_NOVEDAD, entidad_id=novedad.id,
        nombre=novedad.get_tipo_display(),
        descripcion=descripcion, estado_anterior=anterior, estado_nuevo=nuevo,
        motivo=motivo, extra=extra)


@transaction.atomic
def abrir(*, org, actor, tipo: str, descripcion: str = "", impacto: str = "",
          orden=None, actividad=None, profile=None,
          programada_anterior=None, programada_nueva=None) -> NovedadOperativa:
    """
    Registra una incidencia. Nace ABIERTA: nadie la ha atendido todavia.

    'impacto' es opcional y se deja vacio cuando no se declara. Vacio NO es
    'bajo' -- es "nadie lo midio", y confundirlos haria que una incidencia sin
    evaluar pareciera menos grave que una evaluada como baja.
    """
    if tipo not in dict(N.TIPOS):
        raise ErrorIncidencia(f"'{tipo}' no es un tipo de novedad conocido.")
    if impacto and impacto not in dict(N.IMPACTOS):
        raise ErrorIncidencia(f"'{impacto}' no es un impacto conocido.")

    novedad = N.objects.create(
        org=org, tipo=tipo, descripcion=descripcion, impacto=impacto,
        orden=orden, actividad=actividad, profile=profile,
        programada_anterior=programada_anterior,
        programada_nueva=programada_nueva,
        registrada_por=actor, estado=N.ABIERTA)
    _auditar(novedad, actor, "CREATED", nuevo=N.ABIERTA,
             descripcion=f"Incidencia registrada: {novedad.get_tipo_display()}.")
    return novedad


@transaction.atomic
def iniciar_gestion(novedad, *, actor, motivo: str = "") -> NovedadOperativa:
    """Alguien se hizo cargo. No la resuelve: dice que esta siendo atendida."""
    fresca = _fresca(novedad)
    _exigir_transicion(fresca.estado, N.EN_GESTION)
    anterior = fresca.estado
    fresca.estado = N.EN_GESTION
    fresca.save(update_fields=["estado", "updated_at"])
    _auditar(fresca, actor, "STATUS_CHANGED", anterior=anterior,
             nuevo=N.EN_GESTION, motivo=motivo,
             descripcion="La incidencia pasó a gestión.")
    return fresca


@transaction.atomic
def resolver(novedad, *, actor, resolucion: str, ahora=None) -> NovedadOperativa:
    """
    La UNICA forma de resolver una incidencia.

    Exige 'resolucion' con texto. No hay resolucion silenciosa ni automatica:
    ni al desbloquear una actividad, ni al reprogramar una orden, ni al cerrar
    nada. Si la causa se atendio, alguien lo dice y queda escrito quien y como.
    """
    if not (resolucion or "").strip():
        raise ErrorIncidencia(
            "Resolver una incidencia exige decir cómo se resolvió: sin "
            "explicación no se distingue una causa atendida de una olvidada.")

    fresca = _fresca(novedad)
    _exigir_transicion(fresca.estado, N.RESUELTA)
    anterior = fresca.estado
    creada_original = fresca.created_at      # se conserva, no se toca

    fresca.estado = N.RESUELTA
    fresca.resuelta_en = ahora or timezone.now()
    fresca.resolucion = resolucion.strip()
    fresca.resuelta_por = actor
    fresca.save(update_fields=["estado", "resuelta_en", "resolucion",
                               "resuelta_por", "updated_at"])
    fresca.refresh_from_db()
    assert fresca.created_at == creada_original, "se movio la fecha de creacion"

    _auditar(fresca, actor, "STATUS_CHANGED", anterior=anterior,
             nuevo=N.RESUELTA, motivo=fresca.resolucion,
             descripcion="La incidencia se resolvió.",
             extra={"resuelta_en": fresca.resuelta_en.isoformat()})
    return fresca


def declarar_impacto(novedad, *, actor, impacto: str) -> NovedadOperativa:
    """
    Fija la afectacion operacional. Es un dato aparte del ciclo de vida: se
    puede declarar en cualquier momento y no mueve el estado.

    'impacto' describe cuanto estorba esto para operar. NO es culpa, ni
    incumplimiento, ni desempeño de nadie.
    """
    if impacto not in dict(N.IMPACTOS):
        raise ErrorIncidencia(f"'{impacto}' no es un impacto conocido.")
    with transaction.atomic():
        fresca = _fresca(novedad)
        anterior = fresca.impacto
        fresca.impacto = impacto
        fresca.save(update_fields=["impacto", "updated_at"])
        _auditar(fresca, actor, "UPDATED",
                 descripcion=f"Impacto declarado: {fresca.get_impacto_display()}.",
                 extra={"impacto_anterior": anterior, "impacto_nuevo": impacto})
    return fresca


def sin_resolver(org, ahora=None):
    """Las incidencias vivas: ABIERTA o EN_GESTION. Lo que M09 tiene que ver."""
    return (N.objects
            .filter(org=org, estado__in=(N.ABIERTA, N.EN_GESTION))
            .select_related("orden", "actividad", "registrada_por")
            .order_by("created_at"))
