# -*- coding: utf-8 -*-
"""
================================================================================
 LA PANTALLA SE CONTRADICE A SI MISMA  --  12/11/2026
================================================================================
Un medidor optico muestra la MISMA potencia en dos unidades, dBm y µW, y son
convertibles: `dBm = 10·log10(µW/1000)`. Si los dos numeros que el modelo
leyo de una sola pantalla no son el mismo valor, esa lectura no sirve --
cualquiera sea cual de los dos esta mal.

EL BUG QUE ESTO ATACA, Y LOS DOS INTENTOS QUE NO ALCANZARON
------------------------------------------------------------
El modelo corre el punto decimal: dice «-2.10» donde la pantalla muestra
«-21.0». Se intento dos veces:

  * **La doble lectura (11/11)** ataca la VARIANZA. El bug resulto ser
    SESGO: 4 de 4 lecturas de la misma foto dijeron -2.10, una agregando
    «punto decimal visible».
  * **El rango de la empresa en el pie (11/11)**. Llego, y el modelo lo uso
    --contesto «lectura legible, fuera del rango declarado»-- y reporto
    -2.10 igual. La instruccion le daba permiso: «si despues de mirarlo otra
    vez seguis leyendo lo mismo, escribi lo que ves». Obedecio.

Esto es distinto: **no le pide al modelo que se corrija**. El codigo cruza
los dos numeros y descarta. Es fisica, no configuracion.

LOS TEXTOS DE ESTAS GUARDAS SON REALES
---------------------------------------
Copiados de `AnalisisDeEvidencia` en produccion, 11 y 12/11/2026. No son
inventados: un texto inventado prueba que la funcion hace lo que yo creo que
hace, no que sirva para lo que pasa de verdad.

  pytest campo/tests/test_la_pantalla_se_contradice.py --reuse-db --no-cov
================================================================================
"""
from __future__ import annotations

import pytest

from campo import potencia_de_la_foto as PF

#  LA LECTURA CON EL BUG, tal cual la guardo produccion el 12/11 15:46.
CON_BUG = ("Se ve medidor Rouhan: 1550 nm, -2.10 dBm, 0.682 µW, 2kHz. "
           "Lectura legible, fuera del rango declarado. No se ven otros "
           "equipos. CATALOGO: no MUESTRA: si ATENCION: si")

#  LA DE «AL LLEGAR», con el display en su piso. 12/11 15:44.
EN_EL_PISO = ("Medidor Rouhan: pantalla legible con 1550 nm, -50.0 dBm, "
              "0.000 µW, 2kHz. Solo se ve el medidor. CATALOGO: no "
              "MUESTRA: si ATENCION: no")

#  COMO SE VERIA LA MISMA FOTO BIEN LEIDA: -21.0 dBm son 7.94 µW.
BIEN_LEIDA = ("Se ve medidor Rouhan: 1550 nm, -21.0 dBm, 7.94 µW, 2kHz. "
              "Lectura legible. CATALOGO: no MUESTRA: si ATENCION: no")

#  EL CASO QUE ESTA VERIFICACION EXISTE PARA ATRAPAR, Y QUE EL RANGO NO
#  PUEDE  --  descubierto rompiendo el codigo a proposito el 12/11/2026.
#
#  Con el texto de la OT #214 (-2.10 dBm) esta guarda pasaba en verde CON EL
#  DESCARTE DESACTIVADO: -2.10 cae fuera del rango de Rapilink (-27..-8) y
#  `_lectura_creible` ya lo tiraba. La verificacion cruzada no agregaba nada
#  ahi, y el archivo entero afirmaba que si.
#
#  Donde SI agrega: cuando el numero mal leido cae DENTRO del rango. Si la
#  pantalla muestra -21.0 (7.94 µW) y el modelo transpone a -12.0, ese -12.0
#  es perfectamente creible para el rango --esta entre -27 y -8-- y pasaria
#  al veredicto como si fuera el dato. El µW lo desmiente: 7.94 µW son -21.0
#  dBm, no -12.0. Nueve dB de diferencia.
DENTRO_DEL_RANGO_PERO_IMPOSIBLE = (
    "Se ve medidor Rouhan: 1550 nm, -12.0 dBm, 7.94 µW, 2kHz. "
    "Lectura legible. CATALOGO: no MUESTRA: si ATENCION: no")


# ---------------------------------------------------------------------------
#  1) LA CONVERSION, CONTRA NUMEROS QUE SE PUEDEN VERIFICAR A MANO
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("uw,dbm", [
    (1000.0, 0.0),      # 1 mW = 0 dBm, por definicion
    (100.0, -10.0),
    (10.0, -20.0),
    (7.94, -21.0),      # el valor que el tecnico escribio
    (1.0, -30.0),
    (0.682, -31.66),    # el que el modelo leyo en la foto del bug
])
def test_la_conversion_da_lo_que_dice_la_fisica(uw, dbm):
    assert abs(PF.dbm_de_microwatts(uw) - dbm) < 0.01


def test_un_microwatt_imposible_no_revienta():
    """Cero y negativo no tienen logaritmo. Devuelven None, no excepción."""
    assert PF.dbm_de_microwatts(0) is None
    assert PF.dbm_de_microwatts(-5) is None
    assert PF.dbm_de_microwatts(None) is None


# ---------------------------------------------------------------------------
#  2) EL CASO REAL
# ---------------------------------------------------------------------------

def test_LA_LECTURA_DE_LA_OT_214_SE_DETECTA(PF_=PF):
    """El texto exacto que producción guardó. Si esta guarda se pone verde
    con el código roto, no sirve: se rompe a propósito más abajo."""
    coherente, por_que = PF.coherente_con_los_microwatts(CON_BUG)

    assert coherente is False, por_que
    #  El motivo tiene que decir LOS DOS números y la diferencia: sin eso,
    #  quien lee el diagnóstico no sabe qué pasó.
    assert "-2.1" in por_que and "0.682" in por_que, por_que
    assert "-31.7" in por_que, por_que


def test_Y_LA_MISMA_FOTO_BIEN_LEIDA_PASA(PF_=PF):
    """La otra mitad, y sin ella la de arriba se «arregla» descartando todo.
    -21.0 dBm son 7.94 µW y eso es la misma potencia."""
    coherente, por_que = PF.coherente_con_los_microwatts(BIEN_LEIDA)
    assert coherente is True, por_que


# ---------------------------------------------------------------------------
#  3) LO QUE NO SE PUEDE SABER NO SE DESCARTA
# ---------------------------------------------------------------------------

def test_EL_PISO_DEL_DISPLAY_NO_DESCARTA_NADA():
    """«0.000 µW» es consistente con cualquier dBm muy bajo: el display está
    por debajo de su resolución. Es el caso de TODA foto de «al llegar» con
    pérdida de señal, y descartarlas sería romper el diagnóstico que hoy
    funciona."""
    coherente, por_que = PF.coherente_con_los_microwatts(EN_EL_PISO)
    assert coherente is None, por_que
    assert "piso" in por_que


def test_SIN_MICROWATTS_NO_SE_VERIFICA():
    """Medido: el µW viene en 10 de 10 lecturas reales. Pero un modelo que
    un día no lo escriba no puede dejar la foto sin número."""
    coherente, _ = PF.coherente_con_los_microwatts("pantalla: -21.0 dBm")
    assert coherente is None


def test_CON_DOS_MICROWATTS_TAMPOCO():
    """Mismo motivo que `uno_solo` con dos dBm: elegir uno sería inventar la
    mitad del juicio."""
    coherente, _ = PF.coherente_con_los_microwatts(
        "pantalla: -21.0 dBm, 7.94 µW y antes 0.682 µW")
    assert coherente is None


def test_LAS_TRES_FORMAS_DE_ESCRIBIR_MICROWATTS():
    """`µW` con la mu griega, `uW` con u latina, y «microwatts». Las tres
    aparecen según cómo el proveedor transcriba el display."""
    for texto in ("-21.0 dBm, 7.94 µW", "-21.0 dBm, 7.94 uW",
                  "-21.0 dBm, 7.94 microwatts", "-21.0 dBm, 7,94 μW"):
        assert PF.microwatts(texto) == 7.94, texto


# ---------------------------------------------------------------------------
#  4) EL EFECTO: LA LECTURA INCOHERENTE NO LLEGA AL VEREDICTO
# ---------------------------------------------------------------------------

def test_LA_INCOHERENTE_QUE_EL_RANGO_NO_ATRAPA_SE_DESCARTA():
    """LA GUARDA QUE DE VERDAD MIDE ESTA VERIFICACIÓN.

    La primera versión usaba el texto de la OT #214 (-2.10 dBm) y pasaba en
    verde CON EL DESCARTE DESACTIVADO: -2.10 cae fuera del rango de la
    empresa y `_lectura_creible` ya lo tiraba. Se descubrió rompiendo el
    código a propósito.

    Acá el número mal leído (-12.0) es creíble para el rango —está entre
    -27 y -8— así que si esta guarda se pone verde con el descarte roto, la
    verificación cruzada no sirve para nada."""
    from campo.revision_del_cierre import _numero_de_la_foto

    valor, discordaron = _numero_de_la_foto(
        [DENTRO_DEL_RANGO_PERO_IMPOSIBLE], (-27.0, -8.0))

    assert valor is None, (
        f"un -12.0 con 7.94 µW llegó al veredicto: {valor}. Esos µW son "
        f"-21.0 dBm; el rango no puede verlo porque -12.0 es creíble")
    #  Y NO es «discordancia»: discordar es que dos lecturas creíbles den
    #  números distintos. Acá hubo una sola, y era imposible.
    assert discordaron is False


def test_Y_LA_DE_LA_OT_214_TAMBIEN_AUNQUE_EL_RANGO_YA_LA_TIRABA():
    """El caso real sigue cubierto. No prueba la verificación cruzada —el
    rango lo atrapa antes— pero si algún día una empresa configura un rango
    que acepte -2.10, esto lo sostiene."""
    from campo.revision_del_cierre import _numero_de_la_foto

    #  Rango ancho a propósito: así el rango NO lo descarta y lo único que
    #  queda en pie es la verificación cruzada.
    valor, _ = _numero_de_la_foto([CON_BUG], (-80.0, -1.0))
    assert valor is None, f"con un rango ancho, -2.10 pasó: {valor}"


def test_PERO_UNA_LECTURA_SANA_SI_LLEGA():
    """Sin esto, lo de arriba se cumple descartando todas."""
    from campo.revision_del_cierre import _numero_de_la_foto

    valor, _ = _numero_de_la_foto([BIEN_LEIDA], (-27.0, -8.0))
    assert valor == -21.0


def test_ENTRE_DOS_LECTURAS_SOBREVIVE_LA_COHERENTE():
    """El caso que junta los dos mecanismos: la doble lectura trae un texto
    bueno y uno con el punto corrido. Antes del 12/11 los dos eran
    «creíbles» —-2.10 cae dentro de -27..-8— y la foto quedaba sin número
    por discordancia. Ahora el incoherente se cae solo y queda el bueno."""
    from campo.revision_del_cierre import _numero_de_la_foto

    valor, discordaron = _numero_de_la_foto([CON_BUG, BIEN_LEIDA],
                                            (-27.0, -8.0))

    assert valor == -21.0, (valor, discordaron)
    assert discordaron is False
