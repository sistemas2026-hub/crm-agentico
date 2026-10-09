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
    #  CINCO CLAVES, NO CUATRO, desde el 09/10/2026, y el conjunto sigue
    #  siendo EXACTO a proposito: una sexta vuelve a romper esta prueba, que
    #  es lo que se le pide -- lo que se guarda en una propuesta tiene que
    #  pasar por aca.
    #
    #  'veredicto' se agrego porque sin el la unica forma de saber si un
    #  diagnostico fue concluyente era leer su frase, y eso congelo noventa y
    #  cinco casos: diagnosticados con un instrumento viejo, dados por
    #  atendidos, sin reintento posible. Es un dato de TRES valores fijos --
    #  ningun texto libre, ningun dato de cliente-- y el frontend lee claves
    #  nombradas, asi que no aparece en pantalla.
    assert set(obs) == {"fuente", "id", "dato", "observado_en", "veredicto"}
    assert obs["veredicto"] == dx.CIERRE_SEGURO
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


# ===========================================================================
#  6. EL PILOTO EN SOMBRA DEL CIERRE AUTOMATICO
# ===========================================================================

@pytest.mark.django_db
def test_sin_equipo_registrado_lo_dice_con_todas_las_letras():
    #  Lo pidio el usuario con esas palabras, y la diferencia es accionable:
    #  "no se pudo diagnosticar" invita a reintentar; "no tiene equipo
    #  registrado" dice que el dato falta en WispHub y hay que decidir sin el.
    sin_onu = {"id_servicio": 5832, "equipo_registrado": False,
               "estado": "desconocido", "senal": "sin_dato",
               "motivo": "el servicio no tiene equipo registrado en el proveedor"}
    veredicto, porque = dx.clasificar(sin_onu)
    assert veredicto == dx.SIN_DIAGNOSTICO
    assert "no tiene equipo registrado" in porque
    #  Y no se lee como una falla del equipo.
    assert "falta el dato" in porque


@pytest.mark.django_db
def test_en_sombra_NO_se_cierra_ningun_caso(monkeypatch):
    """
    La afirmacion que sostiene todo el piloto: con la bandera apagada, ningun
    caso cambia de estado.

    Se mide sobre el CASO en la base --no sobre la bandera ni sobre un conteo
    del informe-- porque lo unico que importa es que el cliente siga con su
    caso abierto. Una prueba que dijera 'CIERRE_AUTOMATICO is False' pasaria
    en verde con el cierre ejecutandose igual.
    """
    from datetime import timedelta as td

    from cases.models import Case
    from common.models import Org
    from operaciones import chat_herramientas, supervisor

    org = Org.objects.create(name="Org de la sombra")
    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status="New",
        priority="Normal", external_status="Cerrado",
        external_ticket_id="555001", provider="wisphub",
        external_service_id="7001")
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - td(days=12),
        external_status_at=ahora - td(days=3),
        external_fetched_at=ahora - td(hours=1))

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)

    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "New", "el caso NO puede haber cambiado de estado"
    assert caso.resolved_at is None, "y no puede tener fecha de resolucion"


@pytest.mark.django_db
def test_la_sombra_deja_escrito_que_HABRIA_cerrado(monkeypatch):
    from datetime import timedelta as td

    from cases.models import Case
    from common.models import Org
    from operaciones import chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org del habria")
    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status="New",
        priority="Normal", external_status="Cerrado",
        external_ticket_id="555002", provider="wisphub",
        external_service_id="7002")
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - td(days=12),
        external_status_at=ahora - td(days=3),
        external_fetched_at=ahora - td(hours=1))

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)
    resumen = supervisor.correr_ciclo(org)

    #  CAMBIO EL CAMINO, NO LA GARANTIA (08/10/2026). Antes el diagnostico
    #  corria dentro de la transaccion del ciclo y la propuesta nacia ya con
    #  el; ahora corre AFUERA --ninguna transaccion abierta esperando a un
    #  tercero-- asi que la propuesta se crea primero y se completa enseguida.
    #
    #  Lo que se afirma sigue siendo lo mismo y es lo unico que importa: con la
    #  empresa SIN autorizar, el caso no se toca y la propuesta dice por que.
    assert resumen["cierre_automatico"]["cerraria"] == 1
    caso.refresh_from_db()
    assert caso.status == "New", "sin autorizacion de la empresa no se cierra"

    propuesta = PropuestaSupervisor.objects.get(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO)
    escrito = str(propuesta.evidencia)
    #  El diagnostico quedo escrito aunque no se haya cerrado: es lo que una
    #  persona necesita para decidir a mano.
    assert "diagnostico del equipo" in escrito
    assert "-20.55" in escrito
    assert propuesta.estado == P.PROPUESTA


@pytest.mark.django_db
def test_un_diagnostico_que_NO_habilita_no_llega_a_evaluarse(monkeypatch):
    #  Señal debil: el diagnostico no habilita, asi que el cierre automatico ni
    #  se plantea. Si esto se rompiera, la sombra estaria midiendo como
    #  "cerraria" casos que una persona tiene que mirar.
    from datetime import timedelta as td

    from cases.models import Case
    from common.models import Org
    from operaciones import chat_herramientas, supervisor

    org = Org.objects.create(name="Org de la debil")
    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status="New",
        priority="Normal", external_status="Cerrado",
        external_ticket_id="555003", provider="wisphub",
        external_service_id="7003")
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - td(days=12),
        external_status_at=ahora - td(days=3),
        external_fetched_at=ahora - td(hours=1))

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: DEBIL)
    resumen = supervisor.correr_ciclo(org)

    assert resumen["cierre_automatico"]["cerraria"] == 0
    assert resumen["cierre_automatico"]["no_aplica"] == 1


@pytest.mark.django_db
def test_la_sombra_corre_las_condiciones_REALES_del_cierre():
    """
    Si el caso ya no cumple, la sombra dice 'no cerraria' con el motivo que
    daria el cierre de verdad.

    Esto es lo que hace que la sombra sirva: mide lo MISMO que va a ejecutar.
    Si reimplementara las condiciones, el dia que una cambie la sombra seguiria
    prometiendo un cierre que ya no procede.
    """
    from datetime import timedelta as td

    from cases.models import Case
    from common.models import Org
    from operaciones import cierre_de_caso

    org = Org.objects.create(name="Org del reabierto")
    ahora = timezone.now()
    #  El proveedor REABRIO el ticket: cerrar aca seria sincronizar al reves.
    caso = Case.objects.create(
        org=org, name="Sin servicio", status="New", priority="Normal",
        external_status="Abierto", external_ticket_id="555004",
        provider="wisphub", external_service_id="7004")
    Case.objects.filter(pk=caso.pk).update(
        external_status_at=ahora - td(days=3),
        external_fetched_at=ahora - td(hours=1))
    caso.refresh_from_db()

    senal = _senal(id_servicio="7004")
    senal.origen_id = str(caso.id)
    senal.datos["diagnostico_veredicto"] = dx.CIERRE_SEGURO

    informe = dx.evaluar_cierre_automatico(org, [senal], ahora=ahora)

    assert informe["no_cerraria"] == 1
    assert informe["cerraria"] == 0
    #  El motivo es el del cierre real, no uno inventado por la sombra.
    assert cierre_de_caso.PROVEEDOR_NO_LO_CERRO in informe["motivos"]
    assert "no cerraria" in senal.datos["cierre_automatico_porque"]


# ===========================================================================
#  7. EL CIERRE AUTOMATICO  --  las dos puertas, medidas sobre el caso
# ===========================================================================

def _delegar(org, perfil):
    """
    La tarea delegada, que desde el 08/10/2026 es la segunda puerta del cierre.

    Sin esto el caso no se cierra por mas que el nivel lo permita, y es lo
    correcto: el nivel dice CUANTO puede hacer el Supervisor, la tarea dice QUE
    le pidieron. Las pruebas que miden el cierre tienen que pasar las dos.
    """
    from operaciones import tareas_delegadas as td

    return td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
                      pedido_textual="prueba")


def _caso_desincronizado(org, ticket, servicio):
    from datetime import timedelta as td

    from cases.models import Case

    ahora = timezone.now()
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status="New",
        priority="Normal", external_status="Cerrado",
        external_ticket_id=ticket, provider="wisphub",
        external_service_id=servicio)
    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - td(days=12),
        external_status_at=ahora - td(days=3),
        external_fetched_at=ahora - td(hours=1))
    caso.refresh_from_db()
    return caso


def _motor_que_cierra(monkeypatch):
    """
    Parchea SOLO el borde HTTP, y emula lo que el motor hace del otro lado.

    EL CASO LO CIERRA EL MOTOR, no este codigo, y por eso el doble tambien
    escribe el estado. No es hacer trampa: la frontera entre los dos procesos
    esta ahi a proposito --'app_backend' no tiene privilegios sobre la tabla
    'case', medido el 25/09/2026-- y el motor cierra el caso llamando de vuelta
    al CRM. Un doble que devolviera "cerrado" sin cerrar nada haria pasar una
    prueba sobre un efecto que no ocurre.

    Lo que SI prueba este modulo, y es lo que se afirma aparte: que se le pidio
    el cierre, una sola vez, con la propuesta ya aceptada.
    """
    from cases.models import Case
    from operaciones import cierre_de_caso

    llamadas = []

    def falso(propuesta_id, caso_id):
        llamadas.append((propuesta_id, caso_id))
        Case.objects.filter(id=caso_id).update(
            status="Closed", resolved_at=timezone.now())
        return {"cerrado": True, "referencia": "idem:prueba-1"}

    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", falso)
    return llamadas


def _interruptor_encendido(monkeypatch):
    """
    El interruptor general de autonomia, que vive en el esquema del MOTOR.

    Se parchea porque la base de pruebas no tiene ese esquema, y sin el
    'autonomia.puede' falla CERRADO -- lo cual es correcto y esta probado en
    'test_el_interruptor_ilegible_impide_cerrar', pero impide medir el camino
    feliz. Es un borde externo mas, como el HTTP del motor.
    """
    from operaciones import autonomia

    monkeypatch.setattr(autonomia, "_interruptor_de", lambda org: (True, ""))


@pytest.mark.django_db
def test_con_la_empresa_en_nivel_1_NO_se_cierra_ningun_caso(monkeypatch):
    """
    La segunda puerta, que es la que hoy esta cerrada en produccion.

    Se mide sobre el CASO: que siga en 'New'. Afirmar que el nivel es 1 no
    prueba que el nivel se respete.
    """
    from common.models import Org
    from operaciones import chat_herramientas, supervisor

    org = Org.objects.create(name="Org sin autorizar")
    caso = _caso_desincronizado(org, "600001", "8001")
    llamadas = _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)

    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "New", "sin autorizacion de la empresa no se cierra"
    assert caso.resolved_at is None
    assert llamadas == [], "ni siquiera se le pidio al motor"


@pytest.mark.django_db
def test_con_la_empresa_en_nivel_3_el_caso_SI_se_cierra(monkeypatch):
    """
    La prueba que dice que todo esto SIRVE: el caso queda cerrado sin que
    ninguna persona haya apretado nada.
    """
    from common.models import Org
    from operaciones import autonomia, chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org autorizada")
    _interruptor_encendido(monkeypatch)
    caso = _caso_desincronizado(org, "600002", "8002")
    llamadas = _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)

    #  Una persona sube el nivel, con nombre, motivo y criterios: es la unica
    #  forma, y el codigo lo exige explicitamente.
    from common.models import Profile, User

    usuario = User.objects.create(email="jefa@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    autonomia.cambiar(
        org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
        motivo="piloto de cierre automatico de casos desincronizados",
        criterios="5 servicios reales medidos: 3 cierre seguro, 1 revisar, "
                  "1 sin diagnostico")
    _delegar(org, perfil)

    resumen = supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    #  El mensaje lleva TODO lo que decide, porque un "no se cerro" sin el
    #  motivo manda a buscar el problema a las tres puertas a la vez.
    prop = PropuestaSupervisor.objects.filter(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO).first()
    contexto = {
        "estado_caso": caso.status,
        "nivel_que_pidio": getattr(prop, "nivel_autonomia_requerido", None),
        "estado_propuesta": getattr(prop, "estado", None),
        "autonomia": autonomia.puede(org, P.NIVEL_EJECUTAR_REVERSIBLE),
        "cierre": resumen.get("cierre_automatico"),
        "llamadas_al_motor": llamadas,
    }
    assert caso.status == "Closed", f"el caso no se cerro: {contexto}"
    assert len(llamadas) == 1, "y se le pidio al motor exactamente una vez"

    propuesta = PropuestaSupervisor.objects.get(org=org,
                                                tipo_senal=P.CASO_DESINCRONIZADO)
    assert propuesta.estado == P.ACEPTADA
    #  LA AUDITORIA DISTINGUE lo automatico de lo humano: sin esto, dentro de
    #  seis meses nadie puede separar lo que decidio una persona de lo que
    #  decidio el sistema.
    assert propuesta.revisado_por is None
    assert "Supervisor NOC IA" in propuesta.resultado


@pytest.mark.django_db
def test_una_senal_debil_NO_se_cierra_aunque_la_empresa_autorice(monkeypatch):
    """
    La primera puerta sigue valiendo con la segunda abierta. Este es el caso
    medido en produccion (servicio 4045): ticket cerrado en WispHub, equipo en
    linea, pero con la señal debil. Ese cliente puede volver a caerse.
    """
    from common.models import Org, Profile, User
    from operaciones import autonomia, chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org con debil")
    _interruptor_encendido(monkeypatch)
    caso = _caso_desincronizado(org, "600003", "8003")
    llamadas = _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: DEBIL)

    usuario = User.objects.create(email="jefa2@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")
    _delegar(org, perfil)

    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "New", "una señal debil la mira una persona"
    assert llamadas == []
    propuesta = PropuestaSupervisor.objects.get(org=org,
                                                tipo_senal=P.CASO_DESINCRONIZADO)
    assert propuesta.estado == P.PROPUESTA, "queda esperando a una persona"
    assert propuesta.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR



@pytest.mark.django_db
def test_el_interruptor_ilegible_impide_cerrar(monkeypatch):
    """
    Si el interruptor general de autonomia no se puede LEER, no se cierra.

    No es una hipotesis: salio midiendo. La primera corrida del camino feliz
    fallo con "no se pudo leer el interruptor de autonomia (ProgrammingError):
    no poder leer el control es lo mismo que no tenerlo" -- la base de pruebas
    no tiene el esquema del motor, donde ese interruptor vive.

    Eso es exactamente la conducta que se quiere: el interruptor vive fuera de
    la config del tenant y falla CERRADO a proposito, porque la ruta de la
    config falla ABIERTA por dos caminos medidos. Esta prueba lo deja fijado:
    sin interruptor legible, el caso no se toca por mas que todo lo demas
    autorice.
    """
    from common.models import Org, Profile, User
    from operaciones import autonomia, chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org sin interruptor")
    caso = _caso_desincronizado(org, "600004", "8004")
    llamadas = _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)

    usuario = User.objects.create(email="jefa3@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")
    _delegar(org, perfil)

    #  NO SE PARCHEA NADA: la base de pruebas no tiene el esquema del motor,
    #  donde vive el interruptor, asi que la lectura falla sola. Es la falla
    #  REAL y no una imitacion -- de hecho asi aparecio, haciendo fallar el
    #  camino feliz de la prueba de al lado.
    #
    #  Un intento anterior reemplazaba '_interruptor_de' entera por algo que
    #  levantaba, y eso medía otra cosa: esa funcion TIENE su propio try, asi
    #  que sustituirla completa rompia justamente la parte que se queria
    #  comprobar.

    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "New", (
        "con el interruptor ilegible el caso NO se toca, aunque el nivel "
        "configurado lo permita")
    assert llamadas == []

@pytest.mark.django_db
def test_el_sistema_NO_puede_rechazar_ni_modificar_automaticamente():
    #  Aceptar solo. Rechazar es una decision sobre algo que el sistema
    #  propuso: dejarlo descartar sus propias recomendaciones le permitiria
    #  borrar lo que una persona tenia que ver.
    from common.models import Org
    from operaciones import supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org del rechazo")
    propuesta = PropuestaSupervisor.objects.create(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO, origen_tipo="case",
        origen_id="22222222-2222-4222-8222-222222222222",
        accion_propuesta="x", motivo="y", prioridad=30,
        evidencia=[{"fuente": "caso", "id": "1", "dato": "z",
                    "observado_en": timezone.now().isoformat()}])

    with pytest.raises(ValueError):
        supervisor.revisar(propuesta, actor=None, automatico=True,
                           decision=P.RECHAZADA)
    #  Y sin 'automatico' sigue exigiendo persona, como siempre.
    with pytest.raises(ValueError):
        supervisor.revisar(propuesta, actor=None, decision=P.ACEPTADA)


# ===========================================================================
#  8. LAS PROPUESTAS QUE YA EXISTIAN  --  el caso real de produccion
# ===========================================================================

@pytest.mark.django_db
def test_una_propuesta_VIEJA_sin_diagnostico_se_completa_y_se_cierra(monkeypatch):
    """
    LA PRUEBA DEL CASO REAL, y la razon de que este bloque exista.

    Medido en produccion el 08/10/2026: 75 casos desincronizados y los 75 YA
    tenian propuesta. El ciclo las descartaba como 'repetida' antes de
    mirarlas, asi que no quedaba ni una señal que diagnosticar -- el sistema
    estaba completo, autorizado por una persona, y sin nada sobre que actuar.
    La pantalla no mostraba ningun error: simplemente no pasaba nada.

    Se simula exacto: primero un ciclo que crea la propuesta SIN diagnostico
    (como las 75, que nacieron antes de que existiera), y despues el ciclo de
    hoy, que tiene que completarla y cerrar el caso.
    """
    from common.models import Org, Profile, User
    from operaciones import autonomia, chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org con backlog")
    caso = _caso_desincronizado(org, "700001", "9001")
    llamadas = _motor_que_cierra(monkeypatch)
    _interruptor_encendido(monkeypatch)

    #  PRIMER CICLO, como los de antes: sin diagnostico disponible. Se apaga
    #  el enriquecimiento para reproducir una propuesta nacida sin el.
    monkeypatch.setattr(dx, "enriquecer", lambda *a, **k: {"diagnosticados": 0})
    supervisor.correr_ciclo(org)

    vieja = PropuestaSupervisor.objects.get(org=org,
                                            tipo_senal=P.CASO_DESINCRONIZADO)
    assert vieja.estado == P.PROPUESTA
    assert dx.le_falta_diagnostico(vieja), "nacio sin diagnostico, como las 75"
    assert vieja.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR
    caso.refresh_from_db()
    assert caso.status == "New"
    assert llamadas == []

    #  SEGUNDO CICLO, el de hoy: el diagnostico vuelve, y una persona ya
    #  autorizo el nivel 3.
    monkeypatch.undo()
    _interruptor_encendido(monkeypatch)
    llamadas = _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)
    usuario = User.objects.create(email="jefa4@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")
    _delegar(org, perfil)

    supervisor.correr_ciclo(org)

    #  EL EFECTO: el caso quedo cerrado sin que nadie apretara nada.
    caso.refresh_from_db()
    assert caso.status == "Closed", "la propuesta vieja tiene que haber cerrado"
    assert len(llamadas) == 1

    vieja.refresh_from_db()
    assert vieja.estado == P.ACEPTADA
    assert vieja.revisado_por is None, "la cerro el sistema, no una persona"
    assert vieja.nivel_autonomia_requerido == P.NIVEL_EJECUTAR_REVERSIBLE
    #  Y LA EVIDENCIA SE AGREGO, no se reescribio: las observaciones
    #  originales siguen ahi y el diagnostico es una mas.
    fuentes = [p.get("fuente") for p in vieja.evidencia]
    assert "diagnostico" in fuentes
    assert fuentes.count("caso") >= 7, "no se perdio la evidencia original"


@pytest.mark.django_db
def test_el_interruptor_se_consulta_UNA_vez_por_ciclo(monkeypatch):
    """
    Con muchas propuestas pendientes, el interruptor NO se pregunta por cada
    una. Se cuentan las consultas, que es lo unico que lo prueba.

    Desde que el interruptor se lee por HTTP, cada consulta es una llamada de
    red. Preguntarla por propuesta son tantas llamadas como casos pendientes
    --75 en produccion-- dentro de un ciclo que alguien espera mirando la
    pantalla.
    """
    from common.models import Org, Profile, User
    from operaciones import autonomia, chat_herramientas, fuentes_adaptadores
    from operaciones import supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org con muchas")
    for n in range(6):
        _caso_desincronizado(org, f"8000{n}", f"95{n}0")

    #  Primer ciclo sin diagnostico: quedan 6 propuestas pendientes, como las 75.
    monkeypatch.setattr(dx, "enriquecer", lambda *a, **k: {"diagnosticados": 0})
    _interruptor_encendido(monkeypatch)
    supervisor.correr_ciclo(org)
    assert PropuestaSupervisor.objects.filter(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO).count() == 6

    monkeypatch.undo()

    #  Segundo ciclo: se cuentan las consultas al interruptor.
    consultas = []

    def falso_estado():
        consultas.append(1)
        return {"permitido": True, "estado": "activo", "motivo": ""}

    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia", falso_estado)
    _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)
    usuario = User.objects.create(email="jefa6@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")
    _delegar(org, perfil)
    consultas.clear()

    supervisor.correr_ciclo(org)

    #  Con el defecto viejo serian seis o mas. El margen de 2 es para las que
    #  el ciclo hace por otros caminos (el latido del resumen, por ejemplo):
    #  lo que esta prueba mata es el crecimiento CON la cantidad de casos.
    assert len(consultas) <= 2, (
        f"el interruptor se consulto {len(consultas)} veces con 6 propuestas "
        f"pendientes: se pregunta una vez por corrida, no una por caso")


@pytest.mark.django_db
def test_lo_que_no_se_le_pregunto_al_proveedor_no_se_marca_como_atendido(
        monkeypatch):
    """
    Un caso que se quedo sin presupuesto NO queda escrito como diagnosticado.

    Si se le anotara "no se diagnostico, se agoto el presupuesto" a la
    propuesta, 'le_falta_diagnostico' la daria por atendida y ese caso no
    volveria a intentarse NUNCA. El presupuesto dejaria de significar "mas
    tarde" y pasaria a significar "nunca" -- con un tope de 3 y 75 casos, 72
    quedarian fuera para siempre.
    """
    from common.models import Org
    from operaciones import chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org sin presupuesto")
    for n in range(5):
        _caso_desincronizado(org, f"8100{n}", f"96{n}0")

    monkeypatch.setattr(dx, "enriquecer", lambda *a, **k: {"diagnosticados": 0})
    _interruptor_encendido(monkeypatch)
    supervisor.correr_ciclo(org)
    monkeypatch.undo()

    _interruptor_encendido(monkeypatch)
    _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)
    supervisor.correr_ciclo(org)

    #  Se diagnosticaron 3 (el tope). Las otras 2 tienen que seguir esperando,
    #  no quedar marcadas.
    sin_diagnostico = [p for p in PropuestaSupervisor.objects.filter(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO)
        if dx.le_falta_diagnostico(p)]
    assert len(sin_diagnostico) == 2, (
        "las que no se consultaron tienen que seguir pendientes de "
        "diagnostico, para que el proximo ciclo las tome")


@pytest.mark.django_db(transaction=True)
def test_NINGUNA_llamada_externa_ocurre_con_la_transaccion_abierta(monkeypatch):
    """
    La decision congelada de CLAUDE.md §12, medida sobre el efecto.

    "Ninguna transaccion de base abierta mientras se espera una operacion
    externa." Se rompio el 08/10/2026 metiendo el diagnostico, la consulta del
    interruptor y el cierre DENTRO del 'atomic' del ciclo, con la fila de la
    organizacion bloqueada. Tres diagnosticos de ~10 s dejaban la transaccion
    abierta casi un minuto esperando a terceros, y en produccion la conexion se
    caia: 'OperationalError: the connection is closed'. No cerraba nada y
    tardaba una eternidad, las dos cosas por el mismo motivo.

    'transaction=True' NO ES OPCIONAL, y el primer intento sin eso fallo
    diciendo que las tres llamadas ocurrian dentro de una transaccion: pytest
    envuelve CADA prueba en una, asi que 'in_atomic_block' era True pasara lo
    que pasara. Una guarda de este tipo sin esa marca no mide el codigo, mide
    a pytest.

    SE MIDE PREGUNTANDOLE A DJANGO si hay una transaccion atomica activa en el
    momento exacto de cada llamada externa. No se lee el codigo ni se cuenta
    nada: se mira el estado real de la conexion cuando la llamada ocurre, que
    es lo unico que distingue "esta afuera" de "parece que esta afuera".
    """
    from django.db import transaction

    from common.models import Org, Profile, User
    from operaciones import autonomia, chat_herramientas, cierre_de_caso
    from operaciones import fuentes_adaptadores, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org de la transaccion")
    _caso_desincronizado(org, "900001", "9801")

    dentro = []

    def _anotar(quien):
        #  'get_connection().in_atomic_block' es lo que Django usa para saberlo.
        from django.db import connection
        if connection.in_atomic_block:
            dentro.append(quien)

    def falso_diagnostico(o, *, id_servicio):
        _anotar(f"diagnostico({id_servicio})")
        return SANO

    def falso_interruptor():
        _anotar("interruptor")
        return {"permitido": True, "estado": "activo", "motivo": ""}

    def falso_motor(propuesta_id, caso_id):
        _anotar("cierre")
        from cases.models import Case
        Case.objects.filter(id=caso_id).update(
            status="Closed", resolved_at=timezone.now())
        return {"cerrado": True, "referencia": "idem:prueba"}

    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        falso_diagnostico)
    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia",
                        falso_interruptor)
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor", falso_motor)

    usuario = User.objects.create(email="jefa7@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    autonomia.cambiar(org, P.NIVEL_EJECUTAR_REVERSIBLE, actor=perfil,
                      motivo="piloto", criterios="medido")
    _delegar(org, perfil)

    #  Dos corridas: la primera crea la propuesta, la segunda la completa y
    #  cierra. Las llamadas externas de LAS DOS tienen que ocurrir afuera.
    supervisor.correr_ciclo(org)
    supervisor.correr_ciclo(org)

    assert dentro == [], (
        f"estas llamadas externas ocurrieron con la transaccion abierta: "
        f"{dentro}. CLAUDE.md §12: ninguna transaccion de base abierta "
        f"mientras se espera una operacion externa.")
    #  Y que de verdad hubo llamadas, o la prueba pasaria sin medir nada.
    assert not transaction.get_connection().in_atomic_block


@pytest.mark.django_db
def test_una_propuesta_YA_DECIDIDA_no_se_vuelve_a_tocar(monkeypatch):
    #  Rechazar es una decision. Volver sobre ella --completarla y cerrarla--
    #  seria pisar lo que una persona dijo.
    from common.models import Org, Profile, User
    from operaciones import chat_herramientas, supervisor
    from operaciones.models import PropuestaSupervisor as P

    org = Org.objects.create(name="Org con rechazo")
    caso = _caso_desincronizado(org, "700002", "9002")
    _interruptor_encendido(monkeypatch)
    monkeypatch.setattr(dx, "enriquecer", lambda *a, **k: {"diagnosticados": 0})
    supervisor.correr_ciclo(org)

    propuesta = PropuestaSupervisor.objects.get(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO)
    usuario = User.objects.create(email="jefa5@ejemplo.test", name="Jefa")
    perfil = Profile.objects.create(org=org, user=usuario, role="ADMIN",
                                    is_active=True)
    supervisor.revisar(propuesta, actor=perfil, decision=P.RECHAZADA,
                       comentario="este no se cierra")

    monkeypatch.undo()
    _interruptor_encendido(monkeypatch)
    llamadas = _motor_que_cierra(monkeypatch)
    monkeypatch.setattr(chat_herramientas, "diagnosticar_servicio",
                        lambda o, *, id_servicio: SANO)
    supervisor.correr_ciclo(org)

    caso.refresh_from_db()
    assert caso.status == "New", "una propuesta rechazada no se reabre sola"
    assert llamadas == []


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


# ===========================================================================
#  EL RESPALDO POR PING  --  cuando no hay ONU que consultar
# ===========================================================================
#  POR QUE EXISTE. Un tercio de los clientes no tiene el serial de la ONU
#  cargado en WispHub (1.299 de 4.163, medido en la skill). Para esos, SmartOLT
#  no tiene a que responder, y hasta el 09/10/2026 el caso quedaba sin cerrar
#  PARA SIEMPRE -- no por una falla, sino porque faltaba el dato para
#  preguntar. Se acumulaban, y cada ticket nuevo sumaba otro.
#
#  LA REGLA, decidida por el cliente: los TRES paquetes tienen que volver.
#  Sabiendo el costo, que esta medido y escrito junto a la constante.

from operaciones.diagnostico_optico import (CIERRE_SEGURO, REVISAR_PERSONA,  # noqa: E402
                                            SIN_DIAGNOSTICO, clasificar)


def _sin_onu(ping):
    """Lo que devuelve el motor cuando el servicio no tiene ONU registrada."""
    return {"id_servicio": "5832", "equipo_registrado": False,
            "estado": "desconocido", "ping": ping}


def test_sin_onu_con_los_tres_pings_se_cierra():
    v, porque = clasificar(_sin_onu({"ok": True, "respondieron": "3 de 3"}))
    assert v == CIERRE_SEGURO
    #  Y EL MOTIVO DICE CON QUE SE VERIFICO. Un cierre por ping y uno por
    #  señal optica no son la misma afirmacion, y meses despues hay que poder
    #  distinguirlos leyendo la propuesta.
    assert "ping" in porque.lower()
    assert "3 de 3" in porque


def test_sin_onu_con_dos_de_tres_NO_se_cierra():
    """
    '2 de 3' no es "casi bien". El umbral lo fijo una persona y la guarda
    existe para que nadie lo afloje sin decirlo: convertir el texto a numero y
    comparar con '>' pasaria esta prueba a verde sin que nadie lo note.
    """
    v, _ = clasificar(_sin_onu({"ok": True, "respondieron": "2 de 3"}))
    assert v == REVISAR_PERSONA


def test_sin_onu_sin_respuesta_va_a_una_persona():
    v, _ = clasificar(_sin_onu({"ok": True, "respondieron": "0 de 3"}))
    assert v == REVISAR_PERSONA


def test_un_ping_que_no_se_pudo_hacer_no_es_un_ping_fallido():
    """
    LA DISTINCION QUE SOSTIENE TODO ESTE MODULO: "no se pudo medir" no es
    "se midio y no respondio". El primero se reintenta en la corrida
    siguiente; el segundo es un dato del equipo. Si los dos cayeran en
    'REVISAR_PERSONA', un corte de red del motor mandaria a mano casos que
    solo habia que volver a preguntar.
    """
    v, porque = clasificar(_sin_onu({"ok": False, "motivo": "motor_no_responde"}))
    assert v == SIN_DIAGNOSTICO
    #  EL MENSAJE NOMBRA LAS DOS COSAS, y la primera es la accionable: que
    #  falte el serial se arregla cargandolo en WispHub y sirve para
    #  siempre; que el ping no saliera es pasajero. Decir solo lo segundo
    #  mandaria a reintentar algo que va a fallar igual.
    assert "falta el dato" in porque
    assert "tampoco se pudo" in porque
    assert "motor_no_responde" in porque


def test_sin_onu_y_sin_ping_tampoco_inventa_un_cierre():
    """Un diagnostico viejo, anterior al respaldo, no cierra por omision."""
    v, _ = clasificar({"id_servicio": "1", "equipo_registrado": False,
                       "estado": "desconocido"})
    assert v == SIN_DIAGNOSTICO


def test_con_onu_registrada_el_ping_no_se_usa():
    """
    EL PING ES RESPALDO, NO ATAJO. Un equipo que SI esta en SmartOLT se juzga
    por su señal, que es mejor dato. Si esta prueba se pone en rojo, el ping
    empezo a decidir sobre equipos que se podian diagnosticar de verdad.
    """
    con_senal_mala = {"id_servicio": "1", "equipo_registrado": True,
                      "estado": "en_linea", "causa_caida": "",
                      "senal": "debil", "senal_dbm": -29.0,
                      "ping": {"ok": True, "respondieron": "3 de 3"}}
    v, _ = clasificar(con_senal_mala)
    assert v == REVISAR_PERSONA, (
        "un equipo con señal debil se cerro porque el ping respondio: el "
        "respaldo esta pisando al diagnostico optico")


# ===========================================================================
#  UN DIAGNOSTICO INCONCLUYENTE SE VUELVE A INTENTAR
# ===========================================================================
#  EL AGUJERO QUE CERRARON, medido el 09/10/2026 en produccion: noventa y
#  cinco casos atascados y seis corridas seguidas devolviendo 'cerrados: 0'
#  con los dos mapas VACIOS -- ni siquiera entraban al circuito. Todos habian
#  sido diagnosticados antes de que existiera el respaldo por ping, con "no
#  hay equipo registrado". Como ya tenian su linea de diagnostico, el ciclo
#  los daba por atendidos y no volvian a intentarse nunca.
#
#  Lo peor no fue el atasco: fue que NO SE VEIA. Un cero con los motivos
#  vacios se lee igual que "no habia nada que hacer".

from operaciones.diagnostico_optico import (  # noqa: E402
    hay_que_reintentar_diagnostico as reintentar)


class _Prop:
    """Una propuesta, reducida a lo unico que esta regla mira."""

    def __init__(self, evidencia):
        self.evidencia = evidencia


def _diag(veredicto=None):
    pieza = {"fuente": "diagnostico", "id": "1",
             "dato": "diagnostico del equipo: lo que sea",
             "observado_en": "2026-10-09T00:00:00+00:00"}
    if veredicto is not None:
        pieza["veredicto"] = veredicto
    return pieza


def test_un_diagnostico_que_no_se_pudo_hacer_se_reintenta():
    """'No se pudo preguntar' es transitorio: mañana puede haber respuesta."""
    assert reintentar(_Prop([_diag(SIN_DIAGNOSTICO)])) is True


def test_un_equipo_con_problema_NO_se_reintenta():
    """
    'Se pregunto y el equipo esta mal' es un HALLAZGO, no una falta de datos.
    Volver a preguntar no lo cambia, y reintentarlo cada hora gastaria el
    presupuesto en casos ya resueltos -- ademas de tapar a los que si pueden
    avanzar.
    """
    assert reintentar(_Prop([_diag(REVISAR_PERSONA)])) is False


def test_uno_ya_cerrable_no_se_reintenta():
    assert reintentar(_Prop([_diag(CIERRE_SEGURO)])) is False


def test_una_propuesta_VIEJA_sin_veredicto_se_reintenta():
    """
    LA QUE DESTRABA LOS NOVENTA Y CINCO. Las diagnosticadas antes del
    09/10/2026 no tienen la clave 'veredicto', y no hay forma de saber que
    decidieron sin leer su texto -- que es justo lo que este modulo no hace.
    Se reintentan una vez; despues quedan con su veredicto puesto y la regla
    normal decide sola.
    """
    assert reintentar(_Prop([_diag()])) is True


def test_sin_linea_de_diagnostico_no_es_un_reintento():
    """
    Esa es otra cosa y la atiende 'le_falta_diagnostico'. Si esta devolviera
    True, las dos reglas se pisarian y un caso entraria dos veces.
    """
    assert reintentar(_Prop([])) is False
    assert reintentar(_Prop([{"fuente": "caso", "dato": "x"}])) is False


@pytest.mark.django_db
def test_el_veredicto_queda_guardado_como_dato_y_no_como_texto(db):
    """
    SE AFIRMA CONTRA EL PRODUCTOR REAL. Si '_anotar' dejara de escribir la
    clave, todas las pruebas de arriba seguirian en verde --usan piezas
    escritas a mano-- y en produccion cada propuesta se reintentaria para
    siempre, porque 'sin veredicto' significa reintentar.
    """
    from operaciones import diagnostico_optico as dx

    class _Senal:
        tipo = PropuestaSupervisor.CASO_DESINCRONIZADO
        origen_id = "1"
        evidencia = []
        datos = {}

    senal = _Senal()
    dx._anotar(senal, dx.REVISAR_PERSONA, "señal debil", {}, timezone.now())

    pieza = senal.evidencia[0]
    assert pieza["veredicto"] == dx.REVISAR_PERSONA, (
        "el veredicto no quedo como dato: la unica forma de saberlo seria "
        "parsear la frase, y entonces un cambio de redaccion rompe la logica")
