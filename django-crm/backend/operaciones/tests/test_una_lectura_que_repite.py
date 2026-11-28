# -*- coding: utf-8 -*-
"""
================================================================================
 POR QUE LAS LECTURAS REPETIDAS NO SE FILTRAN COMPARANDO TEXTOS
================================================================================

QUE GUARDA ESTE ARCHIVO
-----------------------
Una puerta cerrada, con el numero que la cerro. No prueba una funcion: prueba
que un camino que parece obvio NO sirve, para que la proxima sesion no lo
reintente y pierda la tarde.

DE DONDE SALE
-------------
El 13/10/2026 un ticket de reconexion quedo con DOS lecturas de la misma tarde
diciendo lo mismo con otras palabras:

    "...solicita la reconexion PAGANDO el costo indicado; el ticket es de
     gestion de reconexion, no una falla tecnica de red."

    "...solicita la reconexion ABONANDO el costo indicado; el ticket esta
     frenado en la validacion del pago, no en una falla tecnica."

Se escribio un filtro que descartaba la segunda cuando se parecia bastante a la
primera, con el umbral puesto en 0.90 "porque ese par comparte el 93%". Ese 93%
estaba INVENTADO -- nadie lo habia medido.

LO QUE DIO AL MEDIRLO
---------------------
    las dos lecturas REPETIDAS         0.576
    una lectura vs un CAMBIO REAL      0.565
    dos "falta para estar seguro"
      que dicen lo mismo               0.339

Son el mismo numero. Cualquier umbral que tapara la repeticion taparia tambien
la noticia --que el cliente pago y el servicio sigue caido--, que es justo lo
que el historial existe para mostrar. Y dos listas de "lo que falta" que dicen
lo mismo se parecen MENOS entre si que una lectura y un cambio real.

POR QUE IGUAL NO ES UN PROBLEMA ABIERTO
----------------------------------------
La duplicacion venia de una RELECTURA puntual, no de leer dos veces porque si:
el criterio que la pide ('el_juicio_ignora_la_lectura') se apaga en cuanto el
resumen cita la lectura, asi que dispara UNA sola vez por propuesta. Lo que
quedo duplicado de antes se limpia aparte, una vez.
================================================================================
"""

import unicodedata
from difflib import SequenceMatcher

import pytest
from django.utils import timezone

from operaciones import diagnostico_de_ticket as dxt

pytestmark = pytest.mark.django_db


#  Los textos REALES, copiados de la propuesta de produccion.
LECTURA_1 = ("lectura del reclamo: El servicio fue suspendido por deuda y el "
             "cliente solicita la reconexión pagando el costo indicado; el "
             "ticket es de gestión de reconexión, no una falla técnica de red. "
             "(confianza media)")
LECTURA_2 = ("lectura del reclamo: El servicio fue suspendido por deuda y el "
             "cliente solicita la reconexión abonando el costo indicado; el "
             "ticket está frenado en la validación del pago, no en una falla "
             "técnica. (confianza media)")
UN_CAMBIO_REAL = ("lectura del reclamo: El cliente ya pagó la reconexión y "
                  "adjuntó el comprobante; el servicio sigue suspendido, así "
                  "que ahora sí hay algo técnico que revisar. (confianza alta)")


def _parecido(a, b):
    """Lo mismo que haria el filtro descartado, para dejar el numero a la vista."""
    def norm(t):
        t = unicodedata.normalize("NFD", str(t or "").lower())
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
        return " ".join(t.split())

    return SequenceMatcher(None, norm(a), norm(b)).ratio()


# =============================================================================
#  §1  LA MEDICION QUE CIERRA LA PUERTA
# =============================================================================

def test_una_repeticion_y_un_cambio_real_se_parecen_IGUAL():
    """
    EL HALLAZGO. Si estos dos numeros se separaran, el filtro por parecido
    volveria a ser viable y habria que reconsiderarlo -- por eso la guarda
    afirma que NO se separan, en vez de dejar la medicion en un comentario.
    """
    repetida = _parecido(LECTURA_1, LECTURA_2)
    cambio = _parecido(LECTURA_1, UN_CAMBIO_REAL)

    assert abs(repetida - cambio) < 0.05, (
        f"repetida={repetida:.3f} vs cambio_real={cambio:.3f}. Si ahora SI se "
        f"separan, el filtro por parecido vuelve a ser posible")
    assert repetida < 0.80, (
        f"dos lecturas que dicen lo mismo se parecen apenas {repetida:.3f}: "
        f"el modelo no repite frases, reescribe")


def test_no_quedo_ningun_filtro_por_parecido_en_el_codigo():
    """
    Que la puerta siga cerrada. Un filtro reintroducido despues taparia un
    cambio real --el cliente pago y el servicio sigue caido-- sin avisar.
    """
    assert not hasattr(dxt, "dice_lo_mismo")
    assert not hasattr(dxt, "PARECIDO_PARA_SER_LA_MISMA")


# =============================================================================
#  §2  LA CONDUCTA QUE SE CONSERVA, Y QUE EL CLIENTE PIDIO
# =============================================================================

class _Propuesta:
    def __init__(self, evidencia):
        self.evidencia = evidencia
        self.motivo = "viejo"
        self.accion_propuesta = "x"
        self.prioridad = 10
        self.impacto = ""
        self.updated_at = None

    def save(self, update_fields=None):
        pass


def _pieza(texto):
    return {"fuente": dxt.FUENTE, "id": "1", "dato": texto,
            "observado_en": "2026-10-13T19:00:00+00:00"}


def _senal_con(texto):
    from operaciones.models import PropuestaSupervisor
    from operaciones.supervisor import Senal

    return Senal(tipo=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
                 origen_tipo="case", origen_id="1",
                 evidencia=[_pieza(texto)],
                 datos={"dias_abierto": 6, "diagnostico_leido": True,
                        "diagnostico_hipotesis": "algo",
                        "diagnostico_confianza": "media"})


def test_una_lectura_nueva_AGREGA_y_no_tapa_la_anterior():
    """
    Lo que el cliente pidio con esas palabras: "si el supervisor lee el mismo
    ticket mañana y la situacion cambio, agrega uno nuevo dejando ver un flujo
    del seguimiento del ticket".
    """
    p = _Propuesta([_pieza(LECTURA_1)])
    dxt.guardar_en_propuesta(p, _senal_con(UN_CAMBIO_REAL), timezone.now())

    lecturas = [x for x in p.evidencia if x.get("fuente") == dxt.FUENTE]
    assert len(lecturas) == 2
    assert lecturas[0]["dato"] == LECTURA_1, "se piso la lectura anterior"


def test_la_fecha_de_la_primera_lectura_no_se_toca():
    #  Es la antiguedad del hallazgo: pisarla haria parecer reciente algo que
    #  viene de hace dias.
    p = _Propuesta([_pieza(LECTURA_1)])
    dxt.guardar_en_propuesta(p, _senal_con(UN_CAMBIO_REAL), timezone.now())

    primera = [x for x in p.evidencia if x.get("fuente") == dxt.FUENTE][0]
    assert primera["observado_en"].startswith("2026-10-13T19:00")
