# -*- coding: utf-8 -*-
"""
================================================================================
 LA PROPUESTA TIENE QUE ENTRAR EN SU COLUMNA
================================================================================

DE DONDE SALE
-------------
Del log de produccion, 14/10/2026 01:39:49, y es el final de una cadena de
sintomas que no se parecian a su causa:

    django.db.utils.DataError: value too long for type character varying(255)
    Supervisor: lecturas guardadas=2 · no se leyeron=28 · fallaron=8 (de 38)

'PropuestaSupervisor.accion_propuesta' es CharField(255) y su ayuda lo dice:
"Qué recomienda, en una línea legible". Cuando el Supervisor paso a proponer de
verdad --ese mismo dia-- empezo a guardar ahi la recomendacion del modelo, que
son parrafos: "Separar el ticket en dos gestiones: (1) el cambio de domicilio
va al area comercial/cartera, que debe confirmar...".

LO PEOR NO ES QUE NO ENTRE: es que la base rechaza el guardado ENTERO. Con la
accion se perdia tambien la evidencia de la lectura, que ya estaba escrita. El
trabajo se hacia, se pagaba la consulta al modelo, y no quedaba nada -- y en la
pantalla se veia como "el Supervisor no analiza, solo mira la fecha".

LO QUE AFIRMA
-------------
Que entra, que sigue diciendo algo, y que el texto completo no se pierde.
================================================================================
"""

import pytest

from operaciones.models import PropuestaSupervisor
from operaciones.supervisor import LARGO_DE_UNA_LINEA, Senal, _en_una_linea, analizar

#  La recomendacion REAL que reviento el guardado, copiada del log.
LARGA = ("Separar el ticket en dos gestiones: (1) el cambio de domicilio va al "
         "área comercial/cartera, que debe confirmar la factibilidad técnica en "
         "la nueva dirección y el costo del traslado antes de agendar nada; y "
         "(2) si el cliente además reporta falla de servicio en la dirección "
         "actual, eso sí va a correctivo técnico, pero hoy el equipo responde y "
         "la señal está en rango, así que no hay falla que atender.")


# =============================================================================
#  §1  EL RECORTE
# =============================================================================

def test_una_propuesta_larga_entra_en_la_columna():
    r = _en_una_linea(LARGA)
    assert len(r) <= LARGO_DE_UNA_LINEA, (
        f"{len(r)} caracteres no entran en {LARGO_DE_UNA_LINEA}: la base "
        f"rechaza el guardado ENTERO y se pierde tambien la evidencia")


def test_y_lo_que_queda_sigue_diciendo_algo():
    """
    Un corte a los 255 secos deja la mitad de una palabra. Se corta en la
    primera frase, que es una unidad que se entiende sola.
    """
    r = _en_una_linea(LARGA)
    assert r.startswith("Separar el ticket en dos gestiones")
    assert not r.endswith(" "), "quedo un corte sucio al final"


def test_una_propuesta_corta_no_se_toca():
    corta = "Derivar a cartera: confirmar si el pago de la reconexión se acreditó."
    assert _en_una_linea(corta) == corta


def test_un_texto_sin_puntos_se_corta_en_una_palabra_entera():
    #  Sin frase donde cortar, el recorte no puede partir una palabra al medio.
    sin_puntos = "palabra " * 80
    r = _en_una_linea(sin_puntos)
    assert len(r) <= LARGO_DE_UNA_LINEA
    assert r.endswith("…"), "no se avisa que el texto sigue"
    assert "palabr…" not in r, "se partio una palabra por la mitad"


def test_vacio_sigue_vacio():
    assert _en_una_linea("") == ""
    assert _en_una_linea(None) == ""


# =============================================================================
#  §2  EL EFECTO SOBRE LA PROPUESTA
# =============================================================================

def _senal_con(recomendacion):
    return Senal(
        tipo=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id="1", evidencia=[],
        datos={"dias_abierto": 6, "sin_movimiento": True,
               "diagnostico_leido": True,
               "diagnostico_hipotesis": "El ticket es administrativo.",
               "diagnostico_confianza": "media",
               "accion_sugerida": recomendacion})


def test_el_juicio_devuelve_una_accion_que_cabe():
    juicio = analizar(_senal_con(LARGA))
    assert len(juicio["accion_propuesta"]) <= LARGO_DE_UNA_LINEA


def test_y_el_texto_COMPLETO_sobrevive_en_el_motivo():
    """
    Recortar la columna no puede significar perder lo que el Supervisor
    propuso: el motivo es TextField y ahi entra entero.
    """
    juicio = analizar(_senal_con(LARGA))
    assert LARGA in juicio["motivo"], (
        "se recorto la accion y la propuesta completa no quedo en ningun lado")


def test_sin_recomendacion_no_se_inventa_una():
    juicio = analizar(_senal_con(""))
    assert "PROPONE:" not in juicio["motivo"]
