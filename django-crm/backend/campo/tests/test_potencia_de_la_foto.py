# -*- coding: utf-8 -*-
"""
================================================================================
 LA POTENCIA DE LA FOTO CONTRA LA QUE ESCRIBIO EL TECNICO  --  07/11/2026
================================================================================
El usuario, mirando «Medicion al llegar» en la OT #187. El modelo habia leido
bien --«la pantalla se lee: 1310 nm, "Lo" y -70.00 dBm»-- y ese numero moria
en un parrafo, mientras el tecnico escribia el suyo a mano sin que nadie los
cruzara.

QUE AFIRMA ESTA GUARDA
----------------------
  · que el numero se saque del texto REAL del analisis, no de uno inventado
    para la prueba
  · que -70.00 entre: es la lectura que origino esto, y el extractor que ya
    existia la habria descartado
  · que «1310 nm» y «2 KHz» NO se lean como potencias
  · que con dos lecturas en la foto no se compare -- elegir una es inventar
    la mitad del juicio
  · que la falta de un numero de -> «no se sabe», nunca «no cumple»
================================================================================
"""
from __future__ import annotations

import pytest

from campo import potencia_de_la_foto as P

#  EL TEXTO REAL que el modelo escribio sobre la foto de la OT #187. Se usa
#  tal cual, con su ruido: una prueba escrita sobre una frase limpia mide una
#  frase que nunca va a llegar.
ANALISIS_187 = (
    "Se ve un medidor de potencia óptica azul, sin marca ni modelo legibles, "
    "con un conector/acoplador en el puerto superior; no se ven ONT, router, "
    "módem, access point, fuente, caja de distribución, roseta, patch cord, "
    "cable UTP ni fibra. La pantalla se lee: 1310 nm, “Lo” y -70.00 "
    "dBm; no hay luces indicadoras visibles. No se observa cable de fibra "
    "conectado ni cableado, y el equipo no se ve fijado; el fondo es un "
    "patrón de cuadros, sin contexto de instalación. MUESTRA: si ATENCION: no"
)

#  Y el de la OT #186, que trae mas ruido numerico todavia.
ANALISIS_186 = (
    "Se ve un medidor de potencia óptico de mano, con la marca Rouhán "
    "legible en el frente. En el display aparecen la indicación de longitud "
    "de onda 1550 nm, la lectura -21.0 dBm con 0.682 nW, la referencia 2 KHz "
    "y el rótulo ID. MUESTRA: si ATENCION: no"
)


# ---------------------------------------------------------------------------
#  SACAR EL NUMERO
# ---------------------------------------------------------------------------

def test_lee_la_potencia_del_ANALISIS_REAL():
    """-70.00 dBm, de la frase tal como el modelo la escribio."""
    assert P.uno_solo(ANALISIS_187) == -70.0


def test_el_70_ENTRA_aunque_el_extractor_viejo_lo_descartaria():
    """LA RAZON DE QUE ESTE MODULO EXISTA.

    `paso_a_despacho.niveles_reportados` corta en -45 dBm, y con razon: lee
    tickets, donde el numero sale de una ONU. Aca la fuente es un medidor de
    mano, que si baja de -45 -- y reusar aquel rango habria descartado justo
    la lectura que el usuario señalo.
    """
    from operaciones.paso_a_despacho import niveles_reportados

    assert -70.0 not in niveles_reportados(ANALISIS_187)
    assert -70.0 in P.niveles(ANALISIS_187)


def test_1310_nm_y_2_KHz_NO_son_potencias():
    """El display trae tres numeros y solo uno es dBm.

    Sin exigir el signo y la unidad, «1310 nm» entraria como lectura y la
    comparacion diria cualquier cosa con total aplomo.
    """
    assert P.niveles(ANALISIS_186) == [-21.0]
    assert 1310 not in P.niveles(ANALISIS_186)
    assert 2 not in P.niveles(ANALISIS_186)


def test_lee_la_coma_decimal_y_el_espacio():
    """«-23,1dBm» y «- 23.1 dBm» son el mismo numero escrito distinto."""
    assert P.niveles("llego con -23,1dBm") == [-23.1]
    assert P.niveles("llego con -23.1 dBm") == [-23.1]


def test_con_DOS_lecturas_no_se_compara():
    """Una foto con dos numeros no dice cual anoto el tecnico.

    Elegir uno seria inventar la mitad del juicio: se prefiere «no se sabe» a
    una coincidencia sacada a la suerte.
    """
    assert P.uno_solo("marca -21.0 dBm y antes -28.4 dBm") is None
    #  Pero los dos se leen: quien quiera los dos, los tiene.
    assert P.niveles("marca -21.0 dBm y antes -28.4 dBm") == [-21.0, -28.4]


def test_el_mismo_numero_repetido_sigue_siendo_UNO():
    """El modelo repite la lectura al resumir, y eso no son dos lecturas."""
    assert P.uno_solo("se lee -21.0 dBm ... la lectura -21.0 dBm") == -21.0


def test_lo_que_queda_fuera_de_rango_no_entra():
    """Por debajo de -80 ningun medidor lee: es un numero de otra cosa."""
    assert P.niveles("el cable de -99.5 dBm") == []
    assert P.niveles("ganancia de 12.0 dBm") == []     # sin signo


# ---------------------------------------------------------------------------
#  COMPARAR
# ---------------------------------------------------------------------------

def test_dos_lecturas_parecidas_COINCIDEN():
    """Dos instrumentos en el mismo punto no dan el mismo numero."""
    ok, por_que = P.comparar(-21.0, -21.4)
    assert ok is True
    assert "-21.0" in por_que and "-21.4" in por_que


def test_lo_que_el_usuario_vio_NO_COINCIDE():
    """EL CASO QUE ORIGINO ESTO.

    La foto marca -70.0 --perdida de senal-- y el reporte dice -21.0. No es
    ruido de medicion: 49 dBm de diferencia es otra instalacion u otro
    momento.
    """
    ok, por_que = P.comparar(-70.0, -21.0)
    assert ok is False
    assert "49.0 dBm de diferencia" in por_que, por_que


def test_sin_uno_de_los_dos_numeros_es_NO_SE_SABE():
    """NUNCA «no cumple».

    Una foto que el modelo no supo leer no es un tecnico que mintio. El
    tercer valor existe para no tener que elegir entre acusar y callar.
    """
    assert P.comparar(None, -21.0)[0] is None
    assert P.comparar(-21.0, None)[0] is None
    assert P.comparar(None, None)[0] is None


def test_justo_en_la_TOLERANCIA_todavia_coincide():
    """El borde se afirma, porque es donde un cambio de criterio se nota."""
    assert P.comparar(-21.0, -21.0 - P.TOLERANCIA_DBM)[0] is True
    assert P.comparar(-21.0, -21.0 - P.TOLERANCIA_DBM - 0.1)[0] is False


def test_el_texto_del_tecnico_se_lee_igual_que_el_de_la_foto():
    """Los dos lados son texto libre, y se leen con el mismo codigo.

    Dos lectores distintos para el mismo formato es garantizar que un dia
    uno acepte lo que el otro rechaza.
    """
    assert P.uno_solo("Potencia al llegar: -21.0 dBm") == -21.0
    assert P.uno_solo("potencia al salir -21,0 dBm") == -21.0
