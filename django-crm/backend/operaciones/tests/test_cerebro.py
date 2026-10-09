# -*- coding: utf-8 -*-
"""
================================================================================
 EL CEREBRO DEL SUPERVISOR  --  que no pueda inventar, medido en la salida
================================================================================

QUE SE PRUEBA
-------------
'operaciones/cerebro.py': el bucle que comparten el chat y el ciclo, y el
veredicto estructurado que el ciclo puede persistir.

LA FORMA DE CADA PRUEBA, Y POR QUE
----------------------------------
Casi todas le pasan a 'validar()' un dict CRUDO --lo que diria el modelo-- y
una traza, y afirman sobre el VEREDICTO: que el dato inventado NO esta. No
sobre que exista un 'if', no sobre que el prompt lo prohiba. Es la unica forma
de que "no inventa" signifique algo: el prompt es una instruccion, y una
instruccion se puede ignorar.

Por eso 'validar()' recibe el crudo y la traza en vez de llamar al modelo:
hace que la garantia sea comprobable sin red, sin base y sin modelo.

LAS CINCO GARANTIAS
-------------------
  §2  un hecho cuya fuente no se consulto se descarta
  §3  una recomendacion sin hechos se cae entera
  §4  hipotesis y confianza viajan juntas, o ninguna
  §5  los enums son cerrados y caen al lado conservador
  §6  lo que falta se declara, y vuelve el veredicto NO concluyente

LO QUE SE SUSTITUYE
-------------------
Una sola cosa: la llamada al modelo. El catalogo, el despachador, la lista
blanca de argumentos y el tenant son reales.
================================================================================
"""

from __future__ import annotations

from unittest import mock

import pytest

from operaciones import cerebro
from operaciones.situaciones_modelos import Confianza, Riesgo

RUTA_MODELO = "operaciones.cerebro._pedirle_al_modelo"


# =============================================================================
#  andamio
# =============================================================================

def _traza(*nombres, con_error=(), agotado=False):
    """Una traza como la que deja el bucle: que herramientas se consultaron."""
    r = cerebro.Razonamiento(agotado=agotado)
    for n in nombres:
        r.consultadas.append({"nombre": n, "argumentos": {},
                              "hubo_error": n in con_error})
    return r


def _crudo(**kw):
    """Un veredicto crudo plausible, con lo que se le pase encima."""
    base = {
        "hechos": [{"dato": "12 ONT caídas en el PON 3/1/4",
                    "fuente": "listar_situaciones"}],
        "inferencias": ["la concentración sugiere un tramo óptico"],
        "riesgos": ["si no se atiende, los 12 abonados siguen sin servicio"],
        "riesgo": Riesgo.ALTO,
        "hipotesis": "posible corte en la troncal",
        "confianza": Confianza.MEDIA,
        "recomendacion": "enviar una cuadrilla a revisar el empalme",
        "falta": [],
    }
    base.update(kw)
    return base


# =============================================================================
#  §1  EL CAMINO FELIZ  --  el contrapunto de todo lo demas
# =============================================================================

def test_1_un_veredicto_bien_formado_pasa_entero(org_a):
    """
    Sin esto, "se descarta X" podria significar "se descarta todo". Esta prueba
    fija que el cerebro SI concluye cuando hay con qué.
    """
    v = cerebro.validar(_crudo(), _traza("listar_situaciones"))

    assert v.concluyente is True
    assert v.descartes == []
    assert len(v.hechos) == 1
    assert v.hechos[0]["fuente"] == "listar_situaciones"
    assert v.riesgo == Riesgo.ALTO
    assert v.hipotesis == "posible corte en la troncal"
    assert v.confianza == Confianza.MEDIA
    assert v.recomendacion.startswith("enviar una cuadrilla")
    assert v.vacio is False


def test_2_las_tres_capas_viajan_SEPARADAS(org_a):
    """
    Juntas en un párrafo, una sospecha se lee como una medición. Se afirma que
    el campo de hechos NO contiene la inferencia ni el riesgo.
    """
    v = cerebro.validar(_crudo(), _traza("listar_situaciones"))

    hechos = str(v.hechos)
    assert "sugiere" not in hechos, "una inferencia se colgó de los hechos"
    assert "si no se atiende" not in hechos
    assert v.inferencias and v.riesgos
    assert set(v.como_dict()) >= set(cerebro.CAMPOS_VEREDICTO)


# =============================================================================
#  §2  GARANTIA 1  --  un hecho sin fuente consultada no es un hecho
# =============================================================================

def test_3_un_hecho_atribuido_a_una_herramienta_NO_consultada_se_descarta(org_a):
    """
    La garantía que más importa. El modelo dice que un dato salió de
    'consultar_cliente', pero en este razonamiento nunca se llamó: ese dato no
    salió de una medición, salió de él.
    """
    crudo = _crudo(hechos=[
        {"dato": "12 ONT caídas", "fuente": "listar_situaciones"},
        {"dato": "el abonado 5832 tiene saldo en mora",
         "fuente": "consultar_cliente"},
    ])

    v = cerebro.validar(crudo, _traza("listar_situaciones"))

    assert len(v.hechos) == 1
    assert "mora" not in str(v.hechos), "el hecho inventado llegó a la salida"
    assert any("consultar_cliente" in d for d in v.descartes)
    assert any("no se consultó" in d for d in v.descartes)


def test_4_un_hecho_SIN_fuente_se_descarta(org_a):
    crudo = _crudo(hechos=[{"dato": "hay una caída de red", "fuente": ""}])

    v = cerebro.validar(crudo, _traza("listar_situaciones"))

    assert v.hechos == []
    assert any("sin fuente" in d for d in v.descartes)
    assert v.concluyente is False, "sin un hecho no se puede concluir"


def test_5_un_hecho_que_no_es_objeto_se_descarta(org_a):
    crudo = _crudo(hechos=["12 ONT caídas en el PON 3/1/4"])

    v = cerebro.validar(crudo, _traza("listar_situaciones"))

    assert v.hechos == []
    assert any("no es un objeto" in d for d in v.descartes)


def test_6_con_CERO_herramientas_consultadas_no_sobrevive_ningun_hecho(org_a):
    """
    El caso límite: el modelo contesta sin haber consultado nada. Todo lo que
    diga es invención, y el veredicto queda vacío y no concluyente.
    """
    v = cerebro.validar(_crudo(), _traza())

    assert v.hechos == []
    assert v.vacio is True
    assert v.concluyente is False
    assert v.recomendacion == "", "no se recomienda sobre nada"


# =============================================================================
#  §3  GARANTIA 2  --  una recomendacion sin hechos se cae
# =============================================================================

def test_7_una_recomendacion_sin_hechos_se_descarta_entera(org_a):
    crudo = _crudo(hechos=[],
                   recomendacion="reiniciar la OLT cuanto antes")

    v = cerebro.validar(crudo, _traza("listar_situaciones"))

    assert v.recomendacion == ""
    assert "reiniciar" not in str(v.como_dict())
    assert any("sin ningún hecho" in d for d in v.descartes)


def test_8_con_hechos_la_misma_recomendacion_SI_pasa(org_a):
    """El contrapunto: no es que se descarten todas las recomendaciones."""
    v = cerebro.validar(_crudo(recomendacion="reiniciar la OLT cuanto antes"),
                        _traza("listar_situaciones"))

    assert v.recomendacion == "reiniciar la OLT cuanto antes"


# =============================================================================
#  §4  GARANTIA 3  --  hipotesis y confianza, juntas o ninguna
# =============================================================================

def test_9_una_hipotesis_sin_confianza_valida_se_descarta(org_a):
    """
    Es la misma regla que el CheckConstraint 'situacion_hipotesis_con_confianza'
    impone en la tabla. Aplicada antes, el veredicto nunca produce algo que la
    base vaya a rechazar.
    """
    v = cerebro.validar(_crudo(confianza="bastante"),
                        _traza("listar_situaciones"))

    assert v.hipotesis == ""
    assert v.confianza == Confianza.SIN_HIPOTESIS
    assert any("sin confianza válida" in d for d in v.descartes)
    assert "no se le pone una confianza inventada" in " ".join(v.descartes)


def test_10_una_confianza_sin_hipotesis_tambien(org_a):
    v = cerebro.validar(_crudo(hipotesis=""), _traza("listar_situaciones"))

    assert v.hipotesis == ""
    assert v.confianza == Confianza.SIN_HIPOTESIS
    assert any("sin hipótesis que la sostenga" in d for d in v.descartes)


@pytest.mark.parametrize("c", [Confianza.BAJA, Confianza.MEDIA,
                               Confianza.ALTA])
def test_11_las_tres_confianzas_validas_pasan(org_a, c):
    v = cerebro.validar(_crudo(confianza=c), _traza("listar_situaciones"))
    assert v.confianza == c and v.hipotesis


def test_12_la_pareja_que_la_BASE_aceptaria(org_a):
    """
    Se afirma sobre el efecto que importa: el par (hipotesis, confianza) que
    sale del veredicto es siempre uno que el CheckConstraint admite.
    """
    for crudo in (_crudo(), _crudo(confianza="x"), _crudo(hipotesis=""),
                  _crudo(hipotesis="", confianza="sin_hipotesis")):
        v = cerebro.validar(crudo, _traza("listar_situaciones"))
        con_hip = bool(v.hipotesis)
        con_conf = v.confianza != Confianza.SIN_HIPOTESIS
        assert con_hip == con_conf, (v.hipotesis, v.confianza)


# =============================================================================
#  §5  GARANTIA 4  --  los enums son cerrados
# =============================================================================

def test_13_un_riesgo_inventado_cae_al_lado_conservador(org_a):
    v = cerebro.validar(_crudo(riesgo="catastrofico"),
                        _traza("listar_situaciones"))

    assert v.riesgo == Riesgo.INFORMATIVO, "no se acepta el valor que inventó"
    assert any("riesgo inválido" in d for d in v.descartes)


@pytest.mark.parametrize("r", list(Riesgo.TODOS))
def test_14_los_cinco_riesgos_validos_pasan(org_a, r):
    assert cerebro.validar(_crudo(riesgo=r),
                           _traza("listar_situaciones")).riesgo == r


# =============================================================================
#  §6  GARANTIA 5  --  lo que falta se declara
# =============================================================================

def test_15_si_el_modelo_dice_que_le_falta_algo_NO_es_concluyente(org_a):
    v = cerebro.validar(_crudo(falta=["no sé cuántos abonados hay en ese PON"]),
                        _traza("listar_situaciones"))

    assert v.concluyente is False
    assert v.falta == ["no sé cuántos abonados hay en ese PON"]


def test_16_una_herramienta_que_FALLO_vuelve_el_veredicto_no_concluyente(org_a):
    """
    El caso que más importa de los cinco: una fuente que no contestó NO
    autoriza a afirmar que todo está bien.
    """
    traza = _traza("listar_situaciones", "estado_fuentes",
                   con_error=("estado_fuentes",))

    v = cerebro.validar(_crudo(), traza)

    assert v.concluyente is False
    assert any("no contestaron" in f and "estado_fuentes" in f
               for f in v.falta)


def test_17_agotar_las_vueltas_tambien_lo_vuelve_no_concluyente(org_a):
    v = cerebro.validar(_crudo(), _traza("listar_situaciones", agotado=True))

    assert v.concluyente is False
    assert any("se agotaron las vueltas" in f for f in v.falta)


def test_18_un_veredicto_vacio_dice_QUE_falta_en_vez_de_callarse(org_a):
    v = cerebro.validar({"hechos": []}, _traza())

    assert v.vacio is True
    assert v.falta, "un veredicto vacío sin motivo es indistinguible de uno sano"
    assert "ningún hecho" in " ".join(v.falta)


def test_19_prosa_en_vez_de_JSON_no_es_un_veredicto_sano(org_a):
    """
    Si el modelo contesta un párrafo, el veredicto sale no concluyente -- NO
    vacío y concluyente, que se leería como 'no hay nada que reportar'.
    """
    v = cerebro.validar("Todo parece estar en orden.", _traza("estado_fuentes"))

    assert v.concluyente is False
    assert v.hechos == []
    assert any("no es un objeto JSON" in d for d in v.descartes)


# =============================================================================
#  §7  CADA DESCARTE SE ANOTA  --  un filtro silencioso miente
# =============================================================================

def test_20_los_descartes_se_pueden_leer(org_a):
    """
    Un filtro que no deja rastro hace indistinguible 'el modelo inventó' de 'el
    modelo no dijo nada', y la diferencia decide si hay que revisar el prompt o
    la herramienta.
    """
    crudo = _crudo(hechos=[{"dato": "x", "fuente": "inventada"}],
                   riesgo="horrible", confianza="muchisima")

    v = cerebro.validar(crudo, _traza("listar_situaciones"))

    assert len(v.descartes) >= 3
    assert all(isinstance(d, str) and d for d in v.descartes)


# =============================================================================
#  §8  EL BUCLE  --  compartido, y sin efectos
# =============================================================================

def test_21_el_bucle_consulta_y_cierra(org_a):
    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "estado_fuentes",
                                        "argumentos": {}}],
         "modelo": "deepseek-v4-flash", "proveedor": "deepseek"},
        {"contenido": "Las seis fuentes están al día.", "llamadas": [],
         "modelo": "deepseek-v4-flash", "proveedor": "deepseek"},
    ]
    with mock.patch(RUTA_MODELO, side_effect=respuestas):
        r = cerebro.razonar(org_a, instrucciones="sos el supervisor",
                            entrada="¿cómo están las fuentes?")

    assert r.contenido.startswith("Las seis")
    assert r.vueltas == 2 and r.agotado is False
    assert r.herramientas_usadas == {"estado_fuentes"}
    assert r.hubo_error_de_herramienta is False
    assert r.modelo == "deepseek-v4-flash"


def test_22_si_se_agotan_las_vueltas_se_DICE(org_a):
    pide_siempre = {"contenido": "", "llamadas": [{"nombre": "estado_fuentes",
                                                   "argumentos": {}}]}
    with mock.patch(RUTA_MODELO, return_value=pide_siempre):
        r = cerebro.razonar(org_a, instrucciones="x", entrada="y",
                            vueltas_maximas=2)

    assert r.agotado is True
    assert r.vueltas == 2
    assert len(r.consultadas) == 2


def test_23_una_herramienta_desconocida_se_le_DICE_al_modelo(org_a):
    """No se inventa un resultado ni se aborta: puede corregirse en la vuelta
    siguiente."""
    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "no_existe",
                                        "argumentos": {}}]},
        {"contenido": "No tengo esa herramienta.", "llamadas": []},
    ]
    with mock.patch(RUTA_MODELO, side_effect=respuestas):
        r = cerebro.razonar(org_a, instrucciones="x", entrada="y")

    assert r.consultadas[0]["hubo_error"] is True
    assert r.hubo_error_de_herramienta is True


def test_24_la_traza_NO_guarda_el_resultado_de_la_herramienta(org_a):
    """
    Puede traer datos operativos, y la fila quedaría con una copia vieja del
    mundo. Se guarda QUE se consultó y si falló; nunca qué decía.
    """
    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "listar_situaciones",
                                        "argumentos": {"limite": 5}}]},
        {"contenido": "listo", "llamadas": []},
    ]
    with mock.patch(RUTA_MODELO, side_effect=respuestas):
        r = cerebro.razonar(org_a, instrucciones="x", entrada="y")

    assert set(r.consultadas[0]) == {"nombre", "argumentos", "hubo_error"}
    assert "resultado" not in r.consultadas[0]


def test_25_el_bucle_NO_escribe_una_fila(org_a):
    from common.models import Activity
    from operaciones.chat_modelos import ConversacionSupervisor
    from operaciones.models import PropuestaSupervisor
    from operaciones.situaciones_modelos import SituacionOperativa

    antes = (Activity.objects.count(), ConversacionSupervisor.objects.count(),
             PropuestaSupervisor.objects.count(),
             SituacionOperativa.objects.count())

    with mock.patch(RUTA_MODELO, return_value={"contenido": "ok",
                                               "llamadas": []}):
        cerebro.razonar(org_a, instrucciones="x", entrada="y")
        cerebro.concluir(org_a, instrucciones="x", entrada="y")

    assert (Activity.objects.count(), ConversacionSupervisor.objects.count(),
            PropuestaSupervisor.objects.count(),
            SituacionOperativa.objects.count()) == antes


def test_26_sin_MOTOR_TENANT_no_se_consulta_el_modelo(org_a):
    """Fail-closed: ese parámetro decide de qué empresa es la config."""
    import os

    with mock.patch.dict(os.environ, {"MOTOR_TENANT": ""}, clear=False):
        with mock.patch("requests.post") as salida:
            with pytest.raises(cerebro.ErrorCerebro) as e:
                cerebro.razonar(org_a, instrucciones="x", entrada="y")

    assert "MOTOR_TENANT" in str(e.value)
    salida.assert_not_called()


# =============================================================================
#  §9  'concluir'  --  el bucle y el veredicto juntos
# =============================================================================

def test_27_concluir_devuelve_un_veredicto_validado(org_a):
    import json

    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "listar_situaciones",
                                        "argumentos": {}}]},
        {"contenido": json.dumps(_crudo()), "llamadas": []},
    ]
    with mock.patch(RUTA_MODELO, side_effect=respuestas):
        v = cerebro.concluir(org_a, instrucciones="x", entrada="y")

    assert v.concluyente is True
    assert len(v.hechos) == 1
    assert v.razonamiento is not None
    assert v.razonamiento.herramientas_usadas == {"listar_situaciones"}


def test_28_concluir_tolera_el_bloque_de_codigo_pero_no_el_contenido(org_a):
    """
    DeepSeek a veces envuelve el JSON en ```json aunque se le pida que no. Eso
    se tolera; lo que NO se tolera es el contenido inventado -- y de eso se
    ocupa 'validar', no el parser.
    """
    import json

    envuelto = "```json\n" + json.dumps(_crudo()) + "\n```"
    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "listar_situaciones",
                                        "argumentos": {}}]},
        {"contenido": envuelto, "llamadas": []},
    ]
    with mock.patch(RUTA_MODELO, side_effect=respuestas):
        v = cerebro.concluir(org_a, instrucciones="x", entrada="y")

    assert len(v.hechos) == 1 and v.concluyente is True


def test_29_un_fallo_del_modelo_LEVANTA_en_vez_de_dar_un_veredicto_vacio(org_a):
    """
    Un veredicto vacío y concluyente se leería como 'no hay nada que reportar',
    que es la peor lectura posible de un fallo.
    """
    with mock.patch(RUTA_MODELO,
                    side_effect=cerebro.ErrorCerebro("el modelo no contestó")):
        with pytest.raises(cerebro.ErrorCerebro):
            cerebro.concluir(org_a, instrucciones="x", entrada="y")


def test_30_el_contrato_se_le_manda_al_modelo(org_a):
    with mock.patch(RUTA_MODELO,
                    return_value={"contenido": "{}", "llamadas": []}) as m:
        cerebro.concluir(org_a, instrucciones="sos el supervisor", entrada="y")

    sistema = m.call_args.args[0][0]["content"]
    assert "sos el supervisor" in sistema
    assert '"hechos"' in sistema and '"fuente"' in sistema
    assert "se verifican en código" in sistema.lower()


# =============================================================================
#  §10  LO QUE EL CEREBRO NO PUEDE HACER
# =============================================================================

def test_31_el_catalogo_del_cerebro_es_de_LECTURA(org_a):
    """
    No es que el prompt lo prohíba: no hay una sola herramienta de escritura en
    el catálogo que ve. Se afirma sobre el AST del módulo del catálogo.
    """
    import ast
    import inspect

    from operaciones import chat_herramientas

    ESCRIBEN = {"create", "save", "update", "delete", "update_or_create",
                "get_or_create", "bulk_create", "add", "remove", "set",
                "clear", "put", "patch"}
    arbol = ast.parse(inspect.getsource(chat_herramientas))
    atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}

    assert not (atributos & ESCRIBEN), sorted(atributos & ESCRIBEN)


def test_32_el_cerebro_no_conoce_la_autonomia_ni_la_frontera(org_a):
    """
    El veredicto no tiene campo para un nivel de autonomía, y el módulo no
    importa nada que la pueda mover. Medido sobre el efecto: el atributo no
    existe.
    """
    import ast
    import inspect

    assert not hasattr(cerebro, "autonomia")
    assert not hasattr(cerebro, "frontera")
    assert not hasattr(cerebro, "supervisor")

    nombres = {n.id for n in ast.walk(ast.parse(inspect.getsource(cerebro)))
               if isinstance(n, ast.Name)}
    for prohibido in ("frontera", "interruptor", "ejecutar_propuesta",
                      "registrar_propuesta"):
        assert prohibido not in nombres, prohibido

    v = cerebro.Veredicto()
    for campo in ("nivel", "nivel_autonomia", "autonomia", "ejecutar",
                  "aprobacion"):
        assert not hasattr(v, campo), campo


def test_33_el_veredicto_no_puede_declararse_correcto_solo(org_a):
    """
    No hay campo de acierto ni de resultado: eso lo escribe una persona por
    'gobierno.registrar_resultado', y 'OrigenAprendizaje' no tiene
    'supervisor'.
    """
    v = cerebro.Veredicto()
    for campo in ("acierto", "correcto", "resultado", "funciono",
                  "verificado"):
        assert not hasattr(v, campo), campo
