# -*- coding: utf-8 -*-
"""
================================================================================
 DE UNA SITUACION A UNA PROPUESTA  --  sin fundir las dos cosas
================================================================================

QUE HACE
--------
Cuando el seguimiento de una situacion concluye algo que amerita una persona,
deja una 'PropuestaSupervisor' para que alguien la revise. Una situacion puede
producir VARIAS propuestas a lo largo de su vida, y ninguna la reemplaza.

POR QUE NO SE FUNDEN, Y NO ES UNA PREFERENCIA DE DISEÑO
-------------------------------------------------------
    SituacionOperativa   lo que esta pasando. Vive mientras el problema exista, se
                         actualiza entre ciclos y tiene estado propio.
    PropuestaSupervisor  lo que se recomienda hacer AHORA. Es puntual: se acepta,
                         se rechaza o expira.

Una situacion que dura cuatro horas puede necesitar tres recomendaciones
distintas --verificar, atender, escalar-- y cada una se decide por separado.
Fundirlas obligaria a que aceptar una recomendacion cerrara el problema, que es
exactamente la confusion que el bloque anterior desarmo.

LO QUE REUSA, Y NO VUELVE A ESCRIBIR
------------------------------------
'supervisor.registrar_propuesta' con su exigencia de evidencia, su estampado de
version de habilidad y su auditoria; y 'supervisor._ya_propuesta' para la
deduplicacion. Lo segundo es una funcion privada de otro modulo del MISMO
paquete, y se usa a proposito: duplicar esa consulta habria creado una segunda
regla de deduplicacion que se desincroniza de la primera -- y la primera ya tiene
su historia escrita (M09-D: una propuesta rechazada volvia identica al dia
siguiente). Reusar la de verdad vale mas que respetar el guion bajo.

POR QUE EL TIPO DE SEÑAL ES 'incidencia_sin_resolver' Y NO UNO NUEVO
--------------------------------------------------------------------
Porque ya describe esto. 'operaciones/models.py' define una incidencia como "una
falla de red que afecta a varios", que es literalmente lo que es una afectacion de
PON. Declarar un tipo nuevo habria costado tres cambios --la constante, una
migracion sobre el enum de una tabla con historial, y una ficha de habilidad, que
'test_las_diez_senales_del_modelo_tienen_ficha' exige-- para nombrar algo que ya
tenia nombre.

NO EJECUTA NADA, Y EL NIVEL LO DICE
-----------------------------------
Toda propuesta que sale de aqui pide nivel 1 (recomendar). No es una formalidad:
es lo que la hace revisable por una persona sin ningun camino de ejecucion detras.
================================================================================
"""

from __future__ import annotations

from django.utils import timezone

from operaciones import supervisor
from operaciones.models import PropuestaSupervisor
from operaciones.situaciones_modelos import (Riesgo, SituacionAfectado,
                                             SituacionOperativa, TipoAfectado,
                                             TipoEvento)
from operaciones.situaciones_seguimiento import Veredicto

S = SituacionOperativa

#  Que veredictos ameritan molestar a una persona. 'estable' y 'mejora' NO estan:
#  una situacion que se mantiene o se recupera no necesita una recomendacion nueva
#  en cada ciclo, y generarla convertiria la bandeja en ruido -- que es la forma
#  mas segura de que nadie la mire. 'sin_evidencia' tampoco: el seguimiento ya
#  escala a 'requiere_humano' cuando la falta de datos se vuelve un patron.
VEREDICTOS_QUE_PROPONEN = (Veredicto.REQUIERE_HUMANO, Veredicto.EMPEORA,
                           Veredicto.PUEDE_RESOLVERSE)

RECOMENDACION = {
    Veredicto.REQUIERE_HUMANO: "Revisar esta situación: el Supervisor no puede "
                               "concluir solo",
    Veredicto.EMPEORA: "Atender esta situación: la afectación está creciendo",
    Veredicto.PUEDE_RESOLVERSE: "Verificar si la afectación se resolvió, antes "
                                "de cerrar",
}


def proponer(situacion, salida_seguimiento: dict, *, ahora=None):
    """
    Deja una propuesta para esta situacion, si el veredicto lo amerita.

    Devuelve la propuesta, o None cuando no corresponde o ya habia una igual sin
    decidir.

    LA DEDUPLICACION ES LA QUE YA EXISTIA
    -------------------------------------
    La huella incluye la situacion Y el veredicto, asi que la misma situacion en
    el mismo estado no genera una propuesta por ciclo -- pero si pasa de 'empeora'
    a 'requiere_humano', eso SI es una recomendacion nueva y debe poder entrar.
    Y sigue valiendo la regla de M09-D: una propuesta ya decidida bloquea; una
    expirada no, porque expirar significa que nadie la miro.
    """
    ahora = ahora or timezone.now()
    veredicto = salida_seguimiento.get("veredicto")
    if veredicto not in VEREDICTOS_QUE_PROPONEN:
        return None

    senal = _senal_de(situacion, salida_seguimiento, ahora)
    if supervisor._ya_propuesta(situacion.org, senal):
        return None

    analisis = _analisis_de(situacion, salida_seguimiento)
    propuesta = supervisor.registrar_propuesta(situacion.org, senal, analisis,
                                               ahora=ahora)

    from operaciones import situaciones as svc

    svc.anotar(situacion, TipoEvento.RECOMENDACION,
               RECOMENDACION.get(veredicto, "revisar"),
               datos={"propuesta_id": str(propuesta.id),
                      "veredicto": veredicto,
                      "nivel_requerido": propuesta.nivel_autonomia_requerido},
               ocurrido_en=ahora)
    return propuesta


def _senal_de(situacion, salida, ahora) -> supervisor.Senal:
    """
    La señal con la forma que 'registrar_propuesta' espera.

    Se arma en vez de crear la propuesta a mano para que la validacion, el
    estampado de version y la auditoria sigan siendo las que ya existian.
    """
    pon = SituacionAfectado.objects.filter(
        situacion=situacion, tipo=TipoAfectado.PON,
        recuperado_en__isnull=True).first()

    evidencia = list(situacion.evidencia or [])
    if not evidencia:
        #  'registrar_propuesta' exige evidencia, y la base tambien. Si la
        #  situacion no la trae, se construye UNA observacion con lo unico que se
        #  sabe de cierto --el veredicto y su porque-- en vez de dejar la
        #  propuesta sin respaldo o inventar un dato de la red.
        evidencia = [{
            "fuente": "operaciones.situaciones_seguimiento",
            "id": situacion.codigo,
            "dato": salida["porque"],
            "observado_en": ahora.isoformat(),
        }]

    return supervisor.Senal(
        tipo=PropuestaSupervisor.INCIDENCIA_SIN_RESOLVER,
        origen_tipo="situacion_operativa",
        origen_id=str(situacion.id),
        evidencia=evidencia,
        datos={"codigo": situacion.codigo,
               "veredicto": salida["veredicto"],
               "abonados_afectados": salida.get("abonados_afectados"),
               "delta": salida.get("delta"),
               "pon": pon.identificador if pon else "",
               "riesgo": situacion.riesgo},
        #  La huella lleva el VEREDICTO y NO el conteo de afectados. Es la regla
        #  de M09-D: una magnitud que avanza sola haria que cada ciclo pareciera
        #  una condicion nueva, y una propuesta rechazada volveria al rato.
        huella=f"situacion:{situacion.id}:{salida['veredicto']}",
    )


def _analisis_de(situacion, salida) -> dict:
    """
    El analisis con las claves que 'registrar_propuesta' usa.

    SIEMPRE nivel 1. Lo que sale de aqui es una RECOMENDACION para que una persona
    la lea: no hay ningun camino de ejecucion detras, y declarar un nivel mas alto
    insinuaria que si.
    """
    veredicto = salida["veredicto"]
    prioridad, componentes = _prioridad_de(situacion, veredicto)
    return {
        "accion_propuesta": RECOMENDACION.get(veredicto,
                                              "Revisar esta situación"),
        "motivo": f"{situacion.titulo}. {salida['porque']}.",
        "prioridad": prioridad,
        #  Los componentes viajan como evidencia: asi la propuesta puede explicar
        #  por que quedo donde quedo, en vez de mostrar un numero.
        "componentes_prioridad": componentes,
        "impacto": _impacto_de(salida),
        "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR,
    }


def _prioridad_de(situacion, veredicto) -> tuple[int, list[str]]:
    """
    La prioridad, derivada del riesgo y del veredicto. La CALCULA el codigo.

    El proyecto ya tiene escrito que el codigo calcula y el modelo redacta: una
    prioridad que dependa de que un LLM sume bien es una prioridad que a veces
    esta mal con tono seguro.
    """
    base = {Riesgo.CRITICO: 90, Riesgo.ALTO: 70, Riesgo.MEDIO: 50,
            Riesgo.BAJO: 30, Riesgo.INFORMATIVO: 10}.get(situacion.riesgo, 30)
    componentes = [f"riesgo {situacion.riesgo}: {base}"]

    if veredicto == Veredicto.EMPEORA:
        base += 10
        componentes.append("la afectacion crece: +10")
    if veredicto == Veredicto.PUEDE_RESOLVERSE:
        #  Verificar es importante y no urgente: si se deja un rato, nadie se
        #  queda sin servicio por eso.
        base -= 20
        componentes.append("solo falta verificar: -20")

    prioridad = max(1, min(100, base))
    componentes.append(f"total: {prioridad}")
    return prioridad, componentes


def _impacto_de(salida) -> str:
    n = salida.get("abonados_afectados") or 0
    if n:
        return f"{n} abonado(s) afectado(s) segun la ultima lectura"
    return "sin abonados afectados en la ultima lectura"
