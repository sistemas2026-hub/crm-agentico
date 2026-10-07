# -*- coding: utf-8 -*-
"""
===============================================================================
 EL DIAGNOSTICO OPTICO DE UN CASO DESINCRONIZADO
===============================================================================

QUE SE PRUEBA, Y POR QUE CADA COSA
----------------------------------
1. LA REGLA, que la definio el usuario y la ejecuta el CODIGO. Las dos
   condiciones que habilitan un cierre --caido por falta de energia, o en linea
   con señal buena-- y las que NO lo habilitan. Lo que se afirma es que
   'fibra' y 'sin_energia' terminan en veredictos OPUESTOS: si cayeran en el
   mismo cajon, se le cerraria el caso a gente que sigue sin servicio.

2. EL PRESUPUESTO, que es lo unico que impide que esto cuelgue el ciclo. Se
   mide CONTANDO LLAMADAS, no leyendo la constante: una prueba que afirmara
   'TOPE_DIAGNOSTICOS_POR_CICLO == 3' pasaria en verde con el tope
   desconectado.

3. QUE LO NO DIAGNOSTICADO SE DIGA. Sin llave, sin presupuesto o con error, la
   señal queda anotada diciendo que no se diagnostico. El modo de falla
   peligroso aqui no es el error: es el silencio que se lee como "esta sano".

4. QUE NO SE ESCRIBA NI EL SERIAL NI EL NOMBRE DEL CLIENTE. Esto termina
   guardado en una propuesta.

Nada de esto toca la red: 'diagnosticar' se inyecta.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from operaciones import diagnostico_optico as dx
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor


def _senal(id_servicio="5832", tipo=None):
    return sup.Senal(
        tipo=tipo or PropuestaSupervisor.CASO_DESINCRONIZADO,
        origen_tipo="case",
        origen_id="11111111-1111-4111-8111-111111111111",
        evidencia=[],
        datos={"id_servicio": id_servicio},
        huella="cerrado_en_proveedor_abierto_en_crm",
    )


SANO = {"estado": "en_linea", "causa_caida": "", "senal": "buena",
        "senal_dbm": -20.55, "estado_config": "mismatch"}
DEBIL = {"estado": "en_linea", "causa_caida": "", "senal": "debil",
         "senal_dbm": -27.4, "estado_config": "match"}
SIN_LUZ = {"estado": "caido", "causa_caida": "sin_energia", "senal": "sin_dato",
           "senal_dbm": None, "estado_config": "match"}
FIBRA = {"estado": "caido", "causa_caida": "fibra", "senal": "sin_dato",
         "senal_dbm": None, "estado_config": "match"}


# ===========================================================================
#  1. LA REGLA
# ===========================================================================

def test_en_linea_con_senal_buena_habilita_el_cierre():
    veredicto, porque = dx.clasificar(SANO)
    assert veredicto == dx.CIERRE_SEGURO
    #  El numero va en el texto: quien lee puede comprobarlo en vez de creerle
    #  a la clasificacion.
    assert "-20.55" in porque


def test_caido_por_falta_de_energia_habilita_el_cierre():
    veredicto, porque = dx.clasificar(SIN_LUZ)
    assert veredicto == dx.CIERRE_SEGURO
    assert "luz" in porque.lower() or "energia" in porque.lower()


def test_caido_por_fibra_NO_habilita_el_cierre():
    veredicto, porque = dx.clasificar(FIBRA)
    assert veredicto == dx.REVISAR_PERSONA
    assert "red" in porque.lower()


def test_sin_energia_y_fibra_dan_veredictos_OPUESTOS():
    #  LA AFIRMACION QUE IMPORTA, y la razon de que este modulo exista. Las dos
    #  son 'caido'; tratarlas igual --que es lo que pasaria si el veredicto
    #  mirara solo el estado-- cerraria el caso de un cliente cuya fibra esta
    #  cortada. Esta prueba muere si alguien colapsa las dos ramas.
    assert dx.clasificar(SIN_LUZ)[0] != dx.clasificar(FIBRA)[0]


def test_senal_debil_la_mira_una_persona():
    veredicto, porque = dx.clasificar(DEBIL)
    assert veredicto == dx.REVISAR_PERSONA
    assert "-27.4" in porque


def test_una_causa_que_el_codigo_no_conoce_no_se_decide_por_descarte():
    raro = dict(SIN_LUZ, causa_caida="algo que el proveedor no documento")
    assert dx.clasificar(raro)[0] == dx.REVISAR_PERSONA


def test_en_linea_sin_lectura_de_senal_no_propone_cerrar():
    #  'en linea' solo no alcanza: sin señal no se puede decir si va a aguantar.
    sin_senal = dict(SANO, senal="sin_dato", senal_dbm=None)
    assert dx.clasificar(sin_senal)[0] == dx.SIN_DIAGNOSTICO


def test_un_error_del_proveedor_no_se_lee_como_sano():
    veredicto, porque = dx.clasificar({"error": "MOTOR_NO_DISPONIBLE",
                                       "detalle": "HTTP 502"})
    assert veredicto == dx.SIN_DIAGNOSTICO
    assert "no hay dato" in porque


def test_estado_desconocido_no_se_lee_como_sano():
    desc = {"estado": "desconocido", "motivo": "sin equipo registrado"}
    assert dx.clasificar(desc)[0] == dx.SIN_DIAGNOSTICO


# ===========================================================================
#  2. EL PRESUPUESTO  --  contando llamadas, no leyendo la constante
# ===========================================================================

@pytest.mark.django_db
def test_el_tope_de_cantidad_corta_las_llamadas():
    llamadas = []

    def falso(org, id_servicio):
        llamadas.append(id_servicio)
        return SANO

    senales = [_senal(id_servicio=str(5000 + n)) for n in range(7)]
    p = sup.presupuesto(tope=2, segundos=600)
    informe = dx.enriquecer(None, senales, presupuesto_=p, diagnosticar=falso)

    #  SE CUENTAN LAS LLAMADAS. Con el tope desconectado serian 7.
    assert len(llamadas) == 2
    assert informe["diagnosticados"] == 2
    assert informe["sin_presupuesto"] == 5


@pytest.mark.django_db
def test_el_tope_de_reloj_corta_aunque_sobre_cantidad():
    #  Un tope de cantidad solo no alcanza: tres llamadas de 30 s cuelgan el
    #  ciclo igual que treinta. Se agota el reloj dandole un presupuesto ya
    #  vencido, que es como se ve una corrida que se paso de tiempo.
    llamadas = []

    def falso(org, id_servicio):
        llamadas.append(id_servicio)
        return SANO

    vencido = sup.presupuesto(
        tope=100, segundos=0,
        ahora=timezone.now() - timedelta(seconds=10))
    senales = [_senal(id_servicio=str(5000 + n)) for n in range(4)]
    informe = dx.enriquecer(None, senales, presupuesto_=vencido,
                            diagnosticar=falso)

    assert llamadas == []
    assert informe["sin_presupuesto"] == 4


@pytest.mark.django_db
def test_lo_que_no_se_diagnostico_por_presupuesto_queda_DICHO():
    senales = [_senal(id_servicio=str(5000 + n)) for n in range(3)]
    p = sup.presupuesto(tope=1, segundos=600)
    dx.enriquecer(None, senales, presupuesto_=p, diagnosticar=lambda o, i: SANO)

    omitida = senales[-1]
    assert omitida.datos["diagnostico_veredicto"] == dx.SIN_DIAGNOSTICO
    #  Y dice que NO habla del equipo. El silencio que se lee como "sano" es el
    #  modo de falla peligroso.
    assert "presupuesto" in omitida.datos["diagnostico_porque"]
    assert len(omitida.evidencia) == 1


# ===========================================================================
#  3. LO QUE NO SE PUDO, SE DICE
# ===========================================================================

@pytest.mark.django_db
def test_sin_id_de_servicio_no_se_pregunta_y_se_anota():
    llamadas = []
    senal = _senal(id_servicio="")
    informe = dx.enriquecer(
        None, [senal],
        diagnosticar=lambda o, i: llamadas.append(i) or SANO)

    assert llamadas == []
    assert informe["sin_llave"] == 1
    assert senal.datos["diagnostico_veredicto"] == dx.SIN_DIAGNOSTICO
    assert "id de servicio" in senal.datos["diagnostico_porque"]


@pytest.mark.django_db
def test_una_excepcion_no_tumba_el_ciclo_y_no_filtra_la_url():
    def explota(org, id_servicio):
        #  El texto de una excepcion de red trae la URL, y la URL de SmartOLT
        #  lleva el identificador del equipo de un cliente.
        raise ConnectionError(
            "https://ejemplo.smartolt.com/api/onu/HWTCAF721761")

    senal = _senal()
    informe = dx.enriquecer(None, [senal], diagnosticar=explota)

    assert informe["errores"] == 1
    porque = senal.datos["diagnostico_porque"]
    assert "ConnectionError" in porque
    assert "HWTCAF721761" not in porque
    assert "smartolt" not in porque.lower()


@pytest.mark.django_db
def test_una_senal_de_otro_tipo_no_se_toca():
    otra = _senal(tipo=PropuestaSupervisor.CASO_ANTIGUO)
    dx.enriquecer(None, [otra], diagnosticar=lambda o, i: SANO)
    assert "diagnostico_veredicto" not in otra.datos
    assert otra.evidencia == []


# ===========================================================================
#  4. DONDE QUEDA ESCRITO, Y QUE NO QUEDA
# ===========================================================================

@pytest.mark.django_db
def test_el_veredicto_queda_en_la_evidencia_Y_en_los_datos():
    senal = _senal()
    dx.enriquecer(None, [senal], diagnosticar=lambda o, i: SANO)

    #  En los datos, para el codigo de la fase siguiente.
    assert senal.datos["diagnostico_veredicto"] == dx.CIERRE_SEGURO
    assert senal.datos["diagnostico"]["senal_dbm"] == -20.55
    #  En la evidencia, para la persona que decide, con la forma de las otras.
    assert len(senal.evidencia) == 1
    obs = senal.evidencia[0]
    assert set(obs) == {"fuente", "id", "dato", "observado_en"}
    assert "-20.55" in obs["dato"]


@pytest.mark.django_db
def test_no_se_escribe_el_serial_ni_el_nombre_del_cliente():
    #  Lo que devolveria el ejecutor si alguna vez dejara pasar de mas. Esto
    #  termina GUARDADO en una propuesta, asi que se afirma sobre lo escrito y
    #  no sobre lo que el ejecutor promete no devolver.
    con_demas = dict(SANO, sn="HWTCAF721761", nombre="MARIO SABANAGRANDE",
                     ip="172.16.26.143")
    senal = _senal()
    dx.enriquecer(None, [senal], diagnosticar=lambda o, i: con_demas)

    escrito = str(senal.datos) + str(senal.evidencia)
    assert "HWTCAF721761" not in escrito
    assert "MARIO" not in escrito
    assert "172.16.26.143" not in escrito
    #  Y lo que SI tenia que quedar, quedo.
    assert "-20.55" in escrito


# ===========================================================================
#  5. EL CICLO REAL  --  la unica prueba que dice que esto SIRVE
# ===========================================================================

@pytest.mark.django_db
def test_el_ciclo_deja_el_diagnostico_ESCRITO_en_la_propuesta(monkeypatch):
    """
    De punta a punta, por el camino real: 'correr_ciclo' sobre un caso
    desincronizado de verdad, y el diagnostico aparece en la EVIDENCIA de la
    propuesta que queda guardada.

    ESTA ES LA PRUEBA QUE IMPORTA. Las de arriba miden la clasificacion y el
    presupuesto en aislamiento; ninguna dice que el ciclo las use. Cablear una
    funcion en el modulo equivocado --que ya paso en este mismo trabajo, al
    ponerla en 'correlacion.correr', que usa OTRA clase 'Senal'-- deja todas
    esas pruebas en verde y el ciclo sin diagnosticar nada.

    Se parchea el BORDE EXTERNO ('chat_herramientas.diagnosticar_servicio', lo
    unico que habla por HTTP) y no 'enriquecer': parchear 'enriquecer' probaria
    que la prueba llama a la prueba.
    """
    from datetime import timedelta as td

    from cases.models import Case
    from common.models import Org
    from operaciones import chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org del ciclo")
    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status="New",
        priority="Normal", external_status="Cerrado",
        external_ticket_id="998877", provider="wisphub",
        external_service_id="5832")
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - td(days=12),
        external_status_at=ahora - td(days=3),
        external_fetched_at=ahora - td(hours=1))

    pedidos = []

    def falso(org_, *, id_servicio):
        pedidos.append(id_servicio)
        return SANO

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio", falso)

    supervisor.correr_ciclo(org)

    #  El ciclo pidio el diagnostico, y con la llave del caso.
    assert pedidos == ["5832"]

    propuesta = PropuestaSupervisor.objects.get(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO)
    escrito = str(propuesta.evidencia)
    #  El veredicto quedo donde lo lee una persona.
    assert "diagnostico del equipo" in escrito
    assert "-20.55" in escrito
    #  Y no quedo lo que no tenia que quedar.
    assert "HWTCAF" not in escrito


@pytest.mark.django_db
def test_una_senal_YA_PROPUESTA_no_gasta_presupuesto(monkeypatch):
    """
    El presupuesto es de tres por ciclo: no se gasta en señales cuyo resultado
    el ciclo va a tirar.

    LA CICATRIZ (07/10/2026): la primera version enriquecia todas las señales
    desincronizadas, y el loop del ciclo recien despues descarta con 'continue'
    las que ya tienen una propuesta viva. Con 19 casos en produccion, los tres
    diagnosticos se gastaban en casos ya propuestos --se pagaban y se tiraban--
    y la propuesta nueva no traia diagnostico NUNCA, sin ningun error a la
    vista. Se descubrio mirando la pantalla, no el codigo.

    Se mide CONTANDO a quien se le pregunto: con un caso ya propuesto y otro
    sin proponer, la unica llamada tiene que ser la del segundo.
    """
    from datetime import timedelta as td

    from cases.models import Case
    from common.models import Org
    from operaciones import chat_herramientas, supervisor

    org = Org.objects.create(name="Org de la dedup")
    ahora = timezone.now()

    def _caso(ticket, servicio):
        c = Case.objects.create(
            org=org, name="Sin servicio de internet", status="New",
            priority="Normal", external_status="Cerrado",
            external_ticket_id=ticket, provider="wisphub",
            external_service_id=servicio)
        Case.objects.filter(pk=c.pk).update(
            created_at=ahora - td(days=12),
            external_status_at=ahora - td(days=3),
            external_fetched_at=ahora - td(hours=1))
        return c

    _caso("111111", "6001")
    pedidos = []

    def falso(org_, *, id_servicio):
        pedidos.append(id_servicio)
        return SANO

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio", falso)

    #  Primera corrida: el unico caso se propone, y se diagnostica.
    supervisor.correr_ciclo(org)
    assert pedidos == ["6001"]

    #  Entra un caso nuevo. La segunda corrida NO puede volver a gastar en el
    #  primero, que ya tiene propuesta viva.
    _caso("222222", "6002")
    pedidos.clear()
    supervisor.correr_ciclo(org)

    assert pedidos == ["6002"], (
        "se diagnostico un caso que ya tenia propuesta: ese presupuesto se "
        "paga y se tira")


@pytest.mark.django_db
def test_el_informe_cuenta_cada_veredicto():
    senales = [_senal(id_servicio="1"), _senal(id_servicio="2"),
               _senal(id_servicio="3")]
    respuestas = {"1": SANO, "2": FIBRA, "3": SIN_LUZ}
    informe = dx.enriquecer(None, senales, presupuesto_=sup.presupuesto(tope=9),
                            diagnosticar=lambda o, i: respuestas[i])

    assert informe["diagnosticados"] == 3
    assert informe["cierre_seguro"] == 2        # sano + sin luz
    assert informe["revisar_persona"] == 1      # fibra
