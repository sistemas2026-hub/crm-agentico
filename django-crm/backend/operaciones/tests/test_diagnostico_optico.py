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

    assert resumen["cierre_automatico"]["cerraria"] == 1
    propuesta = PropuestaSupervisor.objects.get(
        org=org, tipo_senal=P.CASO_DESINCRONIZADO)
    escrito = str(propuesta.evidencia)
    assert "cierre automatico" in escrito
    #  Y dice explicitamente que NO se hizo, para que nadie lea la evidencia
    #  como si el caso ya estuviera cerrado.
    assert "modo sombra" in escrito


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
