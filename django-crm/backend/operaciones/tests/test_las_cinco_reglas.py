# -*- coding: utf-8 -*-
"""
================================================================================
 LAS CINCO REGLAS DEL PASO A DESPACHO
================================================================================

QUE AFIRMAN ESTAS PRUEBAS
-------------------------
La TABLA: dado un grupo, un veredicto de labor y una confianza, si el ticket
puede entrar solo a la cola de Despacho. Corre SIN modelo y SIN red, asi que
cada regla se afirma sobre el RESULTADO y no sobre la existencia de un 'if'.

Lo que estas pruebas NO cubren, y se dice para que nadie lo lea como cubierto:
que el caso APAREZCA en 'GET /campo/casos-despachables/'. Eso es el efecto del
otro lado del limite y tiene su propia prueba, con la base de datos puesta.

LAS REGLAS, Y QUIEN LAS DECIDIO
-------------------------------
El cliente, el 14/10/2026, sobre la cola real de ese dia (71 tickets abiertos
de 'soporte_tecnico' y 'operativo'). Cada bloque de abajo nombra su grupo y
cuantos tickets tenia ese dia, porque una regla sin el caso que la motivo se
reabre sola en la sesion siguiente.

POR QUE CADA REGLA TIENE SU CONTRAFACTICO
-----------------------------------------
Una prueba que solo verifica que algo PASA no distingue "la regla funciona" de
"todo pasa". El 14/10 ocho pruebas de este repositorio estuvieron en verde con
el sintoma vivo por afirmar de menos. Asi que por cada "pasa" hay un "y esto
NO pasa" al lado.
================================================================================
"""

import pytest

from operaciones import clasificacion_de_trabajo as clf
from operaciones import paso_a_despacho as pad


# =============================================================================
#  andamio
# =============================================================================

def _medido(labor, porque="el equipo esta caido por perdida de señal optica"):
    """Un veredicto de labor que salio de MEDIR el equipo."""
    return {"labor": labor, "porque": porque, "fuente": "por_prueba",
            "verificada": True}


def _leido(labor=clf.CORRECTIVO):
    """Uno que salio de leer el TEXTO. Es la diferencia que decide todo."""
    return {"labor": labor, "porque": "lo dice el texto del caso",
            "fuente": "por_texto", "verificada": False}


def _sin_concluir():
    """No se pudo medir. NO es lo mismo que "el equipo esta sano"."""
    return {"labor": clf.SIN_CONCLUIR,
            "porque": "no se pudo traer la ficha tecnica del caso",
            "fuente": "", "verificada": False}


# =============================================================================
#  REGLA 1 · FALLA DE SERVICIO  (24 tickets el 14/10)
#  "no tiene internet" 20 · "intermitente/niveles altos" 3 · "lento" 1
#  La medicion tiene que CONFIRMAR la falla.
# =============================================================================

def test_r1_caido_por_fibra_pasa_solo():
    #  LOS/LOF: la falla es de la red, y es nuestra.
    d = pad.decidir(pad.FALLA_DE_SERVICIO, _medido(clf.CORRECTIVO))

    assert d.pasa is True, d.porque
    assert "CONFIRMADA por la medicion" in d.porque


def test_r1_senal_debil_pasa_solo():
    d = pad.decidir(pad.FALLA_DE_SERVICIO,
                    _medido(clf.CORRECTIVO,
                            "la señal de bajada es debil (-27.4 dBm)"))

    assert d.pasa is True, d.porque
    assert "-27.4 dBm" in d.porque, (
        "el numero medido no viaja al porque: quien lea la decision despues "
        "no puede saber contra que se decidio")


def test_r1_CONTRAFACTICO_el_equipo_sano_NO_pasa():
    """
    El reclamo dice que no hay internet y el equipo esta sano: se CONTRADICEN.

    Un equipo en linea con señal buena no produce veredicto verificado
    --'_de_la_prueba' devuelve None y el caso cae al texto-- asi que llega aca
    con 'verificada' en False.
    """
    d = pad.decidir(pad.FALLA_DE_SERVICIO, _leido())

    assert d.pasa is False
    assert "contradicen" in d.porque
    assert "preguntarle al cliente" in d.porque


def test_r1_CONTRAFACTICO_sin_poder_medir_NO_pasa():
    d = pad.decidir(pad.FALLA_DE_SERVICIO, _sin_concluir())

    assert d.pasa is False
    assert "no es lo mismo que estar sano" in d.porque, (
        "'no se pudo medir' se esta leyendo como 'esta sano', que es la peor "
        "lectura posible de una ausencia de dato")


def test_r1_falta_de_energia_NO_pasa_aunque_este_medido():
    """
    Esta MEDIDO y es firme. Lo que prueba es que una visita no sirve: el corte
    de luz es en la casa del cliente.
    """
    d = pad.decidir(pad.FALLA_DE_SERVICIO, _medido(clf.NO_REQUIERE_VISITA))

    assert d.pasa is False
    assert "falta de energia" in d.porque
    assert "preguntarle al cliente" in d.porque


# =============================================================================
#  REGLA 2 · TRABAJO PEDIDO POR EL CLIENTE  (16 tickets el 14/10)
#  domicilio 5 · TDT 4 · punto de TV 2 · retiro de equipos 2 · clave wifi 1 ·
#  camara 1 · reconexion 1
#  El equipo sano es NORMAL: la medicion no es condicion.
# =============================================================================

def test_r2_pasa_solo_con_el_equipo_SANO():
    """
    Cambiar la clave del wifi igual necesita que alguien vaya. Exigirle a la
    medicion que confirme una falla dejaria afuera todos estos.
    """
    d = pad.decidir(pad.TRABAJO_PEDIDO, _leido(clf.TRABAJOS), confianza="alta")

    assert d.pasa is True, d.porque
    assert "el equipo sano es lo normal" in d.porque


def test_r2_pasa_solo_aunque_NO_se_haya_podido_medir():
    d = pad.decidir(pad.TRABAJO_PEDIDO, _sin_concluir(), confianza="alta")

    assert d.pasa is True, (
        "no se pudo medir y eso lo freno: para un trabajo pedido la medicion "
        f"no es condicion. {d.porque}")


def test_r2_CONTRAFACTICO_con_confianza_media_NO_pasa():
    """
    LA UNICA PUERTA QUE QUEDA CUANDO NO HAY MEDICION.

    Sin esto, una lectura dudosa manda un caso a la cola -- que es justo lo
    que el comentario de 'models.py' sobre TICKET_SIN_DIAGNOSTICO advertia.
    """
    d = pad.decidir(pad.TRABAJO_PEDIDO, _leido(clf.TRABAJOS),
                    confianza="media")

    assert d.pasa is False
    assert "se exige confianza 'alta'" in d.porque


def test_r2_CONTRAFACTICO_sin_confianza_NO_pasa():
    d = pad.decidir(pad.TRABAJO_PEDIDO, _leido(clf.TRABAJOS))

    assert d.pasa is False
    assert "ninguna" in d.porque


# =============================================================================
#  REGLA 3 · OBRA DE RED  (24 tickets el 14/10)
#  CTO / caja / splitter 16 · ampliaciones de sector 6 · proyectos 2
#  Medir al abonado del que cuelga el ticket no dice nada de una caja.
# =============================================================================

def test_r3_una_obra_de_red_pasa_sola_sin_medir():
    d = pad.decidir(pad.OBRA_DE_RED, _sin_concluir(), confianza="alta")

    assert d.pasa is True, d.porque
    assert "obra de red" in d.porque


def test_r3_CONTRAFACTICO_con_confianza_baja_NO_pasa():
    d = pad.decidir(pad.OBRA_DE_RED, _sin_concluir(), confianza="baja")

    assert d.pasa is False
    assert "se exige confianza 'alta'" in d.porque


# =============================================================================
#  REGLA 4 · RECLAMO QUE NADA MIDE  (2 tickets el 14/10: paginas bloqueadas)
#  Ni el ping ni los niveles opticos lo ven.
# =============================================================================

def test_r4_nunca_pasa_solo():
    d = pad.decidir(pad.NADA_LO_MIDE, _leido(), confianza="alta")

    assert d.pasa is False, (
        "una pagina bloqueada no la ve ninguna herramienta de red: no hay "
        "forma de que el Supervisor la respalde")
    assert "ninguna herramienta de red puede comprobar" in d.porque


def test_r4_tampoco_con_el_equipo_caido_y_medido():
    """
    EL ATAJO QUE ESTA PRUEBA CIERRA.

    Que el equipo este caido y medido no convierte un reclamo de paginas
    bloqueadas en una falla de servicio: son dos cosas distintas, y pasar por
    la medicion de una para despachar la otra seria usar una garantia para
    sostener algo que no garantiza.
    """
    d = pad.decidir(pad.NADA_LO_MIDE, _medido(clf.CORRECTIVO),
                    confianza="alta")

    assert d.pasa is False


# =============================================================================
#  REGLA 5 · NI CLIENTE NI RED  (5 tickets el 14/10)
#  cambio de aceite · entrega de guantes · 3 que solo traen un nombre
# =============================================================================

def test_r5_nunca_pasa_solo():
    d = pad.decidir(pad.NI_CLIENTE_NI_RED, _leido(), confianza="alta")

    assert d.pasa is False
    assert "no hay nada que diagnosticar" in d.porque


def test_r5_tampoco_con_una_medicion_que_confirma():
    d = pad.decidir(pad.NI_CLIENTE_NI_RED, _medido(clf.CORRECTIVO),
                    confianza="alta")

    assert d.pasa is False


# =============================================================================
#  LO QUE PASA CUANDO ALGO NO SE ENTIENDE  --  fail-closed
# =============================================================================

def test_sin_grupo_lo_mira_una_persona():
    """
    El modelo no supo clasificar, o dijo un valor que 'cerebro' descarto. La
    ausencia del dato NO se completa con el grupo que mas se parezca.
    """
    d = pad.decidir("", _medido(clf.CORRECTIVO), confianza="alta")

    assert d.pasa is False
    assert "no pudo decir en que grupo" in d.porque


def test_un_grupo_inventado_lo_mira_una_persona():
    d = pad.decidir("urgente_de_verdad", _medido(clf.CORRECTIVO),
                    confianza="alta")

    assert d.pasa is False
    assert "no declarado" in d.porque


@pytest.mark.parametrize("basura", [None, "", 0, [], "un texto", {"otra": 1}])
def test_un_veredicto_de_labor_que_no_se_entiende_no_pasa(basura):
    """
    FAIL-CLOSED ante cualquier forma inesperada. Un camino no previsto tiene
    que degradar hacia "lo mira una persona", nunca hacia "pasa".
    """
    d = pad.decidir(pad.FALLA_DE_SERVICIO, basura, confianza="alta")

    assert d.pasa is False


def test_ninguna_decision_sale_sin_porque():
    """
    Una decision sin motivo es indistinguible de un bug, y es lo que alguien
    va a leer dentro de seis meses para entender por que este caso se despacho
    solo.
    """
    casos = [
        (pad.FALLA_DE_SERVICIO, _medido(clf.CORRECTIVO), "alta"),
        (pad.FALLA_DE_SERVICIO, _leido(), "alta"),
        (pad.TRABAJO_PEDIDO, _sin_concluir(), "alta"),
        (pad.TRABAJO_PEDIDO, _sin_concluir(), "baja"),
        (pad.OBRA_DE_RED, _sin_concluir(), "alta"),
        (pad.NADA_LO_MIDE, _medido(clf.CORRECTIVO), "alta"),
        (pad.NI_CLIENTE_NI_RED, _leido(), "alta"),
        ("", None, ""),
    ]
    for grupo, lv, conf in casos:
        d = pad.decidir(grupo, lv, confianza=conf)
        assert d.porque and len(d.porque) > 20, (grupo, d.porque)


# =============================================================================
#  EL REPARTO: 40 DE 71 PASAN SIN MEDICION, Y ESO ES DELIBERADO
# =============================================================================

def test_los_dos_grupos_que_pasan_sin_medicion_son_exactamente_dos():
    """
    Esta prueba existe para que agregar un tercero sea una DECISION y no un
    descuido. El 14/10 el cliente decidio que 'trabajo_pedido' y 'obra_de_red'
    --40 de los 71 tickets de ese dia-- pasen sin que ninguna medicion los
    respalde, revirtiendo a proposito lo que 'models.py' advertia sobre mandar
    gente por lo que dice un texto.

    Sumar un grupo mas a ese conjunto amplia eso. Si es deliberado, se cambia
    aca y se dice por que.
    """
    assert pad.SIN_CONDICION_DE_MEDICION == {pad.TRABAJO_PEDIDO,
                                             pad.OBRA_DE_RED}
    assert pad.SIEMPRE_UNA_PERSONA == {pad.NADA_LO_MIDE,
                                       pad.NI_CLIENTE_NI_RED}
    #  Y el quinto no esta en ninguno de los dos: lo decide la medicion.
    assert pad.FALLA_DE_SERVICIO not in pad.SIN_CONDICION_DE_MEDICION
    assert pad.FALLA_DE_SERVICIO not in pad.SIEMPRE_UNA_PERSONA


# =============================================================================
#  LAS DOS CONSTANTES COPIADAS, Y SU GUARDA
# =============================================================================

@pytest.mark.django_db
def test_el_nivel_que_se_pide_es_el_reversible_y_no_el_critico():
    """
    'paso_a_despacho' escribe el 3 a mano en vez de importar el enum, para no
    arrastrar 'models' y con el medio paquete (ver la nota de imports de ese
    modulo). Una constante copiada sin guarda se desincroniza en silencio, y
    esta prueba es la guarda.

    Y afirma las DOS cosas: que es el reversible, y que NO es el critico. El 4
    es "siempre lo aprueba una persona" y 'autonomia.puede' lo niega siempre:
    pedir 4 seria pedir algo que ninguna configuracion puede conceder, o sea
    apagar esto sin que el log lo diga.
    """
    from operaciones.models import PropuestaSupervisor as P

    assert pad.NIVEL_PARA_PASAR == P.NIVEL_EJECUTAR_REVERSIBLE
    assert pad.NIVEL_PARA_PASAR < P.NIVEL_CRITICO


@pytest.mark.django_db
def test_la_tarea_que_habilita_esto_es_PROPIA():
    """
    No puede ser la del cierre de desincronizados: habilitar una cosa no puede
    habilitar la otra de rebote. Son dos efectos distintos y cada uno se pide
    aparte.
    """
    from operaciones import tareas_delegadas as td

    assert pad.TAREA != td.CERRAR_DESINCRONIZADOS
    assert pad.TAREA != td.CICLO_AUTOMATICO


def test_la_confianza_exigida_es_un_valor_del_enum_del_cerebro():
    """
    Si 'alta' deja de ser un valor valido de 'Confianza', esta regla dejaria
    de poder cumplirse NUNCA -- y el sintoma seria "ningun trabajo pedido pasa",
    sin ningun error.
    """
    from operaciones.cerebro import Confianza

    assert pad.CONFIANZA_EXIGIDA_SIN_MEDICION == Confianza.ALTA


# =============================================================================
#  DECIDIR SIN VOLVER A PAGAR EL MODELO
# =============================================================================
#
#  EL AGUJERO QUE CIERRA, medido el 14/10/2026 con la puerta ya delegada:
#  76 propuestas de ticket esperando y un tope de DIEZ lecturas por vuelta. Lo
#  que decide el paso vivia solo en 'senal.datos', que muere con el ciclo, asi
#  que las 66 restantes no podian pasar -- y un ticket frenado por una puerta
#  cerrada necesitaba que el modelo lo leyera otra vez para reintentar.
#
#  Es la misma forma del bug que tenia atascados a los desincronizados.


class _Propuesta:
    """Solo lo que 'de_la_propuesta' mira."""

    def __init__(self, evidencia):
        self.evidencia = evidencia


def _lectura_guardada(**claves):
    pieza = {"fuente": pad.FUENTE_DE_LA_LECTURA,
             "dato": "lectura del reclamo: no tiene servicio",
             "observado_en": "2026-10-14T18:00:00Z"}
    pieza.update(claves)
    return pieza


def test_la_lectura_guardada_alcanza_para_decidir():
    p = _Propuesta([_lectura_guardada(
        grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
        labor_verificada=True, labor_porque="caido por fibra",
        confianza="alta")])

    d = pad.de_la_propuesta(p)

    assert d.pasa is True, d.porque
    assert "caido por fibra" in d.porque


def test_la_lectura_MAS_NUEVA_es_la_que_vale():
    """
    La evidencia de un ticket se ACUMULA a proposito --es el historial del
    reclamo-- asi que la ultima lectura es la que describe la situacion de hoy.
    Tomar la primera decidiria con lo que pasaba la semana pasada.
    """
    p = _Propuesta([
        _lectura_guardada(grupo=pad.NADA_LO_MIDE, labor="",
                          labor_verificada=False, confianza="alta"),
        _lectura_guardada(grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
                          labor_verificada=True, confianza="alta"),
    ])

    assert pad.de_la_propuesta(p).pasa is True


def test_una_lectura_VIEJA_sin_grupo_no_decide_nada():
    """
    Las 76 propuestas que existian el 14/10 se leyeron antes de que el grupo se
    guardara: tienen la frase pero no la clave. Eso NO se interpreta leyendo el
    texto -- se queda esperando una relectura, y lo dice.
    """
    p = _Propuesta([{"fuente": pad.FUENTE_DE_LA_LECTURA,
                     "dato": "lectura del reclamo: no tiene servicio desde ayer",
                     "observado_en": "2026-10-13T20:00:00Z"}])

    d = pad.de_la_propuesta(p)

    assert d.pasa is False
    assert "volver a leer" in d.porque


def test_sin_ninguna_lectura_guardada_tampoco():
    assert pad.de_la_propuesta(_Propuesta([])).pasa is False
    assert pad.de_la_propuesta(_Propuesta(None)).pasa is False


def test_la_evidencia_de_OTRA_fuente_no_se_confunde_con_una_lectura():
    """
    Un caso trae observaciones de varias fuentes --el caso, el calculo de
    prioridad, el diagnostico optico--. Tomar cualquiera como lectura del
    reclamo decidiria con un dato que no es el que se busca.
    """
    p = _Propuesta([{"fuente": "diagnostico", "grupo": pad.FALLA_DE_SERVICIO,
                     "labor_verificada": True, "dato": "otra cosa"}])

    assert pad.de_la_propuesta(p).pasa is False


def test_la_fuente_que_se_repite_es_la_misma_de_las_dos_puntas():
    """
    'paso_a_despacho' repite la cadena en vez de importar el modulo de lectura,
    que arrastra el ciclo entero. Una cadena copiada sin guarda se desincroniza
    en silencio, y el sintoma seria "ningun ticket pasa" sin un solo error.
    """
    from operaciones import diagnostico_de_ticket as dxt

    assert pad.FUENTE_DE_LA_LECTURA == dxt.FUENTE
