# -*- coding: utf-8 -*-
"""
===============================================================================
 EL SUPERVISOR LEE EL TICKET, Y EL DATO PERSONAL NO SALE
===============================================================================

LO QUE ESTAS PRUEBAS SOSTIENEN
------------------------------
El diagnostico de un ticket abierto sale de LEER texto libre escrito a mano. Y
esta medido que de 300 tickets reales, 136 traian un numero de documento ahi
adentro. La lista blanca de campos no sirve contra eso: controla QUE CAMPOS
pasan, no QUE CONTIENE cada campo.

Las dos cosas que no se pueden aflojar:

  1. Lo que viaja al modelo no lleva documento, telefono ni correo.
  2. Lo que sale de leer un texto NO manda una cuadrilla. Eso lo decide una
     medicion, o una persona.
"""
import pytest

from operaciones import lectura_de_ticket as lt


# ===========================================================================
#  1. LO QUE SE TAPA
# ===========================================================================

def test_tapa_la_cedula_escrita_a_mano():
    """El caso medido: 136 de cada 300 tickets la traen."""
    t = lt.tapar("Cliente MARIA GOMEZ CC 1098765432 no tiene internet")
    assert "1098765432" not in t
    assert lt.TAPADO in t
    #  Y NO SE LLEVA EL DIAGNOSTICO PUESTO: lo que sostiene la lectura queda.
    assert "no tiene internet" in t


def test_tapa_la_cedula_con_puntos():
    assert "1.098.765.432" not in lt.tapar("CC 1.098.765.432 reporta falla")


def test_tapa_el_celular():
    for crudo in ("3001234567", "300 123 4567", "300-123-4567"):
        t = lt.tapar(f"llamar al {crudo} para coordinar")
        assert "123" not in t.replace(lt.TAPADO, ""), f"quedo {t}"
        assert "para coordinar" in t


def test_tapa_el_correo():
    t = lt.tapar("escribir a maria.gomez@gmail.com antes de ir")
    assert "@" not in t
    assert "antes de ir" in t


def test_no_toca_lo_que_sostiene_el_diagnostico():
    """
    LA OTRA MITAD DEL TRATO. Un tapado que se lleva puesto el problema
    protegeria el dato y arruinaria el diagnostico, y nadie lo notaria hasta
    que las hipotesis empezaran a venir vacias.
    """
    crudo = ("Cliente reporta que no tiene internet desde ayer en la tarde, "
             "ya reinicio el router y el LED rojo sigue encendido")
    assert lt.tapar(crudo) == crudo


def test_un_texto_vacio_no_se_convierte_en_None():
    #  Devolver 'None' dejaria un valor recorriendo medio sistema sin que
    #  nadie lo mire. Cadena vacia obliga a decidir en el acto.
    assert lt.tapar("") == ""
    assert lt.tapar(None) == ""
    assert lt.tapar(12345) == ""


def test_se_puede_medir_cuantos_se_taparon():
    """
    Para vigilar en produccion SIN leer un texto real. Un cero sostenido en
    miles de tickets no significaria "no hay datos personales": significaria
    que los patrones dejaron de coincidir, y esa falla no da error.
    """
    assert lt.cuantos_se_taparon("CC 1098765432 tel 3001234567") == 2
    assert lt.cuantos_se_taparon("no tiene internet") == 0


# ===========================================================================
#  2. LO QUE SALE DEL TEXTO NO MANDA UNA CUADRILLA
# ===========================================================================
#  Es la regla que el detector 'CASO_REQUIERE_VISITA' ya dejo escrita: "una
#  labor que salio del texto queda fuera, porque proponerle a alguien que
#  mande una cuadrilla porque un asunto decia cierta palabra seria pedirle que
#  confie en lo que nadie verifico".

def test_una_labor_sacada_del_texto_no_queda_verificada():
    from operaciones import clasificacion_de_trabajo as clf

    #  Sin contexto medido, solo el texto.
    v = clf.clasificar({}, texto="hay que cambiar el cable de la acometida")
    if not v or not v.get("labor"):
        pytest.skip("el clasificador no saca labor de este texto")
    assert v.get("verificada") is not True, (
        "una labor deducida del texto quedo marcada como verificada: con eso "
        "el reparto mandaria una cuadrilla por lo que decia una frase")


# ===========================================================================
#  3. TODA SEÑAL TIENE QUE PRODUCIR UNA PROPUESTA
# ===========================================================================
#  MEDIDO EN PRODUCCION el 13/10/2026, el dia que esto salio: el detector
#  emitio 750 señales y NO SE CREO NI UNA PROPUESTA. 'analizar' devuelve None
#  para un tipo que no conoce, y el ciclo lo cuenta como "datos insuficientes"
#  sin crear nada. En silencio, porque devolver None es una respuesta legitima
#  para otros casos.
#
#  El sintoma fue "755 hallazgos y 5 pendientes": la deteccion funcionaba, el
#  juicio no, y los dos numeros juntos lo decian sin que nadie los leyera asi.
#
#  POR ESO LA GUARDA ES SOBRE TODOS LOS TIPOS y no sobre el nuevo: el proximo
#  que alguien agregue va a tener el mismo agujero, y esta prueba lo va a
#  encontrar el dia que lo escriba y no un mes despues.

def test_todo_tipo_de_senal_sabe_producir_una_propuesta():
    from operaciones import supervisor as sup
    from operaciones.models import PropuestaSupervisor as P

    class _Senal:
        def __init__(self, tipo):
            self.tipo = tipo
            self.origen_id = "1"
            self.origen_tipo = "case"
            self.evidencia = []
            #  Datos vacios A PROPOSITO: lo que se mide es que 'analizar'
            #  RECONOZCA el tipo, no que arme una frase bonita. Un tipo
            #  conocido con datos pobres devuelve algo; uno desconocido
            #  devuelve None, que es el agujero.
            self.datos = {}

    sin_juicio = []
    for tipo, _etiqueta in P.TIPOS_SENAL:
        try:
            r = sup.analizar(_Senal(tipo))
        except Exception:                                    # noqa: BLE001
            #  Levantar es otra cosa y la cubren las pruebas de cada tipo: lo
            #  que esta guarda busca es el silencio.
            continue
        if not r:
            sin_juicio.append(tipo)

    assert not sin_juicio, (
        f"estos tipos de señal se detectan y NO producen propuesta: "
        f"{sin_juicio}. El ciclo los cuenta como 'datos insuficientes' y no "
        f"crea nada, sin error y sin aviso -- asi 750 tickets detectados "
        f"dieron cero propuestas el 13/10/2026")
