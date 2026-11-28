# -*- coding: utf-8 -*-
"""
================================================================================
 INCIDENCIAS  --  lectura y analisis  (paso M05-A, corregido)
================================================================================

LA FUENTE DEL ESTADO ES LA COLUMNA, NO UN CALCULO
-------------------------------------------------
La primera version de este modulo DERIVABA el estado: una incidencia de bloqueo
se daba por resuelta en cuanto la actividad dejaba de estar bloqueada. Estaba
mal, y el error no era de implementacion sino de concepto:

    "la actividad ya no esta bloqueada"  !=  "la causa ya se atendio"

Un tecnico puede desbloquear para avanzar por otra via mientras el material
sigue sin llegar. Deducir lo segundo de lo primero cierra sola una causa que
nadie atendio.

Ahora el estado se lee de 'NovedadOperativa.estado' y solo cambia por las
operaciones explicitas de 'operaciones/novedades.py'. Este modulo LEE; no
decide, no transiciona, no escribe.

QUE SIGUE SIENDO ANALISIS
-------------------------
'contexto_operativo' -- lo que se puede observar alrededor de una incidencia
abierta: si la actividad que la origino sigue bloqueada, si la orden ya se
programo. Eso es informacion util para quien va a resolverla, y NO es su
estado.

    estado         lo que alguien declaro      (persistente)
    contexto       lo que se puede observar    (derivado, informativo)

NO_DETERMINABLE vive solo en el contexto: significa "no hay dato para observar
esto", y nunca sustituye a RESUELTA.
================================================================================
"""

from __future__ import annotations

from django.utils import timezone

from operaciones.models import ActividadOperativa, NovedadOperativa

N = NovedadOperativa

#  Resultados del ANALISIS de contexto. No son estados de la incidencia.
CONTEXTO_VIGENTE = "CAUSA_OBSERVABLE_VIGENTE"
CONTEXTO_CESO = "CAUSA_OBSERVABLE_CESO"
NO_DETERMINABLE = "NO_DETERMINABLE"

ORDEN_TERMINADA = ("cerrada", "cancelada")


def _contexto_bloqueo(novedad) -> tuple[str, str]:
    a = novedad.actividad
    if a is None:
        return NO_DETERMINABLE, "la novedad no apunta a ninguna actividad"
    if a.estado_operativo == ActividadOperativa.BLOQUEADA:
        return CONTEXTO_VIGENTE, (f"la actividad sigue bloqueada: "
                                  f"{a.motivo_bloqueo or 'sin causa'}")
    #  OJO: esto NO dice que la incidencia este resuelta. Dice que la actividad
    #  se desbloqueo, que es otra cosa y puede haber pasado por otra via.
    return CONTEXTO_CESO, (f"la actividad ya no esta bloqueada (esta en "
                           f"'{a.estado_operativo}'), lo que no significa que "
                           f"la causa se haya atendido")


def _contexto_dependencia(novedad) -> tuple[str, str]:
    a = novedad.actividad
    if a is None:
        return NO_DETERMINABLE, "la novedad no apunta a ninguna actividad"
    if a.depende_de_id is None:
        return CONTEXTO_CESO, "la actividad ya no depende de ninguna otra"
    previa = a.depende_de
    if previa.estado_operativo in ActividadOperativa.ESTADOS_FINALES:
        return CONTEXTO_CESO, f"la actividad previa termino ({previa.estado_operativo})"
    return CONTEXTO_VIGENTE, (f"la actividad previa '{previa.titulo}' sigue en "
                              f"'{previa.estado_operativo}'")


def _contexto_dato_incompleto(novedad) -> tuple[str, str]:
    o = novedad.orden
    if o is None:
        return NO_DETERMINABLE, "la novedad no apunta a ninguna orden"
    if o.estado_operativo in ORDEN_TERMINADA:
        return CONTEXTO_CESO, f"la orden termino ({o.estado_operativo})"
    if o.programada_para is not None:
        return CONTEXTO_CESO, "la orden ya tiene fecha programada"
    return CONTEXTO_VIGENTE, "la orden sigue sin fecha programada"


SIN_CONTEXTO_OBSERVABLE = {
    N.FALTA_MATERIAL: "nada registra cuando llega el material",
    N.DEMORA_SIN_CAUSA: "no se registro una causa, asi que tampoco su fin",
    N.AUSENCIA: "no hay un campo que diga hasta cuando dura la ausencia",
    N.REPROGRAMACION: "describe un hecho puntual, no una condicion observable",
    N.CAMBIO_PRIORIDAD: "describe un hecho puntual, no una condicion observable",
}


def _contexto(novedad) -> dict:
    """
    Lo que se puede OBSERVAR alrededor de la incidencia. Informativo.

    Nunca contesta si esta resuelta: eso lo dice la columna 'estado'.
    """
    if novedad.tipo in SIN_CONTEXTO_OBSERVABLE:
        estado, por_que = NO_DETERMINABLE, SIN_CONTEXTO_OBSERVABLE[novedad.tipo]
    elif novedad.tipo == N.BLOQUEO:
        estado, por_que = _contexto_bloqueo(novedad)
    elif novedad.tipo == N.DEPENDENCIA:
        estado, por_que = _contexto_dependencia(novedad)
    elif novedad.tipo == N.DATO_INCOMPLETO:
        estado, por_que = _contexto_dato_incompleto(novedad)
    else:
        estado, por_que = NO_DETERMINABLE, f"tipo '{novedad.tipo}' sin contexto observable"
    return {"observacion": estado, "por_que": por_que}


def _faltantes(novedad) -> list[dict]:
    """Lo que NO se sabe de esta incidencia. Medido sobre la fila."""
    faltan = []
    if not novedad.impacto:
        faltan.append({"entidad": "novedad", "campo": "impacto",
                       "por_que": "nadie declaro la afectacion operacional"})
    if not (novedad.descripcion or "").strip():
        faltan.append({"entidad": "novedad", "campo": "descripcion",
                       "por_que": "la incidencia no dice que paso"})
    if novedad.orden_id is None and novedad.actividad_id is None:
        faltan.append({"entidad": "novedad", "campo": "orden/actividad",
                       "por_que": "no esta vinculada a ninguna orden ni actividad"})
    if novedad.registrada_por_id is None:
        faltan.append({"entidad": "novedad", "campo": "registrada_por",
                       "por_que": "no consta quien la registro"})
    return faltan


def ficha(novedad, ahora=None) -> dict:
    """
    Una incidencia, completa. El ESTADO sale de la columna; el contexto es
    analisis y se devuelve aparte para que nadie los confunda.
    """
    ahora = ahora or timezone.now()
    creada = novedad.created_at
    antiguedad = int((ahora - creada).total_seconds() // 3600) if creada else None
    return {
        "id": str(novedad.id),
        "tipo": novedad.tipo,
        "tipo_etiqueta": novedad.get_tipo_display(),
        "descripcion": (novedad.descripcion or "")[:160],
        #  --- lifecycle PERSISTENTE ---
        "estado": novedad.estado,
        "estado_etiqueta": novedad.get_estado_display(),
        "sin_resolver": novedad.estado in (N.ABIERTA, N.EN_GESTION),
        "impacto": novedad.impacto or None,
        "impacto_etiqueta": novedad.get_impacto_display() if novedad.impacto else None,
        "resuelta_en": novedad.resuelta_en.isoformat() if novedad.resuelta_en else None,
        "resolucion": novedad.resolucion or None,
        "resuelta_por": (str(novedad.resuelta_por_id)
                         if novedad.resuelta_por_id else None),
        "registrada_en": creada.isoformat() if creada else None,
        "antiguedad_horas": antiguedad,
        "registrada_por": (str(novedad.registrada_por_id)
                           if novedad.registrada_por_id else None),
        "orden": str(novedad.orden_id) if novedad.orden_id else None,
        "actividad": str(novedad.actividad_id) if novedad.actividad_id else None,
        #  --- analisis, claramente separado ---
        "contexto": _contexto(novedad),
        "datos_faltantes": _faltantes(novedad),
    }


def _fichas(qs, ahora, limite):
    ahora = ahora or timezone.now()
    return [ficha(n, ahora) for n in qs[:limite]]


def de_orden(orden_id, ahora=None, limite: int = 5) -> list[dict]:
    if not orden_id:
        return []
    qs = (NovedadOperativa.objects.filter(orden_id=orden_id)
          .select_related("actividad", "orden").order_by("-created_at"))
    return _fichas(qs, ahora, limite)


def de_actividad(actividad_id, ahora=None, limite: int = 5) -> list[dict]:
    if not actividad_id:
        return []
    qs = (NovedadOperativa.objects.filter(actividad_id=actividad_id)
          .select_related("actividad", "orden").order_by("-created_at"))
    return _fichas(qs, ahora, limite)


def resumen(fichas) -> dict:
    """
    El reparto del lifecycle. 'sin_resolver' se cuenta aparte porque es la
    pregunta que el Jefe de Operaciones hace de verdad.
    """
    por_impacto: dict[str, int] = {}
    for f in fichas:
        if f["impacto"]:
            por_impacto[f["impacto"]] = por_impacto.get(f["impacto"], 0) + 1
    return {
        "abiertas": sum(1 for f in fichas if f["estado"] == N.ABIERTA),
        "en_gestion": sum(1 for f in fichas if f["estado"] == N.EN_GESTION),
        "resueltas": sum(1 for f in fichas if f["estado"] == N.RESUELTA),
        "sin_resolver": sum(1 for f in fichas if f["sin_resolver"]),
        "por_impacto": por_impacto,
        "sin_impacto_declarado": sum(1 for f in fichas if not f["impacto"]),
    }
