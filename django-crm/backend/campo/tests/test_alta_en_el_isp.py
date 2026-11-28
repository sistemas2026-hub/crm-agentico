# -*- coding: utf-8 -*-
"""El cliente de un contrato firmado se crea en el ISP (25/11/2026).

El motor de aca es de mentira: contesta lo que cada prueba le dice. Lo que el
motor comprueba de verdad --la IP libre, el plan, el interruptor-- esta en
`tests/test_alta_de_cliente.py` y `tests/test_alta_ruta.py`, en la raiz. Aca se
afirma lo que es de ESTE lado: cuando se pide, que viaja, y como queda escrito.

  A  AL FIRMAR -- se pide solo si la empresa lo encendio, y la firma no espera.
  B  LA TAREA -- creado, en curso, fallido, y cuando el motor no contesta.
  C  ANULAR -- no mientras nadie sabe si el cliente quedo creado.
  D  EL BOTON -- una persona lo vuelve a pedir: es OTRO pedido, y queda quien.
  E  LA CONFIGURACION -- el interruptor, apagado de fabrica.
  F  LA OFICINA LO VE.
  G  «NO SE» NO ES «FALLO» -- por revisar: ni se anula ni se reintenta, y lo
     resuelve una persona de gestion (auditoria de frontera, el mismo dia).
  H  UNA IP, UN CONTRATO.
"""
import pytest

from campo import tasks
from campo.contrato import ConfiguracionDeContrato, ContratoDeServicio
from campo.models import AsignacionTrabajo, OrdenTrabajo
from campo.services import alta_en_el_isp
#  Las mismas piezas que las pruebas del contrato: la orden, la solicitud y el
#  cuerpo de la firma. Los fixtures se registran al importarlos.
from campo.tests.test_contrato_de_servicio import (  # noqa: F401
    TRES_SERVIDORES, _cuerpo, _solicitud, _url, orden, version_instalacion)

pytestmark = pytest.mark.django_db

IP = "172.16.9.37"


class _Respuesta:
    def __init__(self, cuerpo, estado=200):
        self._cuerpo, self.status_code = cuerpo, estado
        self.content = b"x"

    def json(self):
        return self._cuerpo


class Motor:
    """Contesta, en orden, lo que la prueba le cargo. Anota lo que le piden."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []

    def post(self, url, params=None, json=None, headers=None, timeout=None):
        self.pedidos.append({"url": url, "params": params, "json": json})
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, _Respuesta) else _Respuesta(r)

    def rutas(self):
        return [p["url"].rsplit("/", 1)[1] for p in self.pedidos]


@pytest.fixture
def motor(monkeypatch, org_a, empresa_del_motor):
    empresa_del_motor(org_a, "empresa-uno")

    def _con(*respuestas):
        m = Motor(*respuestas)
        monkeypatch.setattr(alta_en_el_isp.requests, "post", m.post)
        return m

    return _con


@pytest.fixture
def cola(monkeypatch):
    """Lo que se encola, sin worker. Cada prueba decide cuando corre la tarea."""
    encoladas = []
    monkeypatch.setattr(tasks.crear_cliente_en_el_isp, "delay",
                        lambda *a: encoladas.append({"args": list(a), "espera": 0}))
    monkeypatch.setattr(
        tasks.crear_cliente_en_el_isp, "apply_async",
        lambda args=None, countdown=None, **k: encoladas.append(
            {"args": list(args), "espera": countdown}))
    return encoladas


@pytest.fixture
def encendida(org_a):
    return ConfiguracionDeContrato.objects.create(
        org=org_a, servidores=TRES_SERVIDORES, texto_condiciones="Primera...",
        crear_en_el_isp=True)


@pytest.fixture
def apagada(org_a):
    return ConfiguracionDeContrato.objects.create(
        org=org_a, servidores=TRES_SERVIDORES, texto_condiciones="Primera...")


@pytest.fixture
def firmar(user_client, orden, org_a, django_capture_on_commit_callbacks):
    """Firma el contrato como lo hace la app, con lo de `on_commit` ejecutado."""
    def _firmar(**extra):
        _solicitud(org_a)
        with django_capture_on_commit_callbacks(execute=True):
            r = user_client.post(_url(orden), _cuerpo(ip=IP, **extra), format="json")
        assert r.status_code in (200, 201), r.content
        return r.json()["contrato"]

    return _firmar


def _correr(encolada):
    """Corre la tarea como la correria el worker."""
    return tasks.crear_cliente_en_el_isp(*encolada["args"])


def _hasta_rendirse(contrato_id, org_id):
    """La ultima vuelta: la que ya no espera mas."""
    return tasks.crear_cliente_en_el_isp(str(org_id), contrato_id, tasks.VUELTAS_DEL_ALTA)


def _fila(contrato_id):
    return ContratoDeServicio.objects.get(pk=contrato_id)


def _pedir(cliente, contrato_id, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        return cliente.post(f"/api/campo/contratos/{contrato_id}/crear-en-el-isp/",
                            {}, format="json")


def _anular(cliente, contrato_id):
    return cliente.post(f"/api/campo/contratos/{contrato_id}/anular/",
                        {"motivo": "El plan quedó mal elegido"}, format="json")


def _resolver(cliente, contrato_id, **cuerpo):
    return cliente.post(f"/api/campo/contratos/{contrato_id}/resolver-alta/",
                        cuerpo, format="json")


EN_CURSO = _Respuesta({"estado": "en_curso", "tarea": "tarea-1", "emitido": True}, 202)
NO_RECONOCIDO = _Respuesta({"estado": "no_reconocido", "tarea": "tarea-1",
                            "emitido": True, "motivo": "no se pudo reconocer"}, 202)
RECHAZADO = _Respuesta({"estado": "fallo", "emitido": True,
                        "motivo": "el proveedor rechazo el pedido"}, 502)
IP_DE_OTRO = _Respuesta({"estado": "ip_ocupada", "emitido": False,
                         "motivo": "esa IP ya la tiene otro cliente"}, 409)


# =========================================================================== #
#  A. AL FIRMAR
# =========================================================================== #
def test_a1_con_la_empresa_ENCENDIDA_firmar_pide_el_alta_y_NO_ESPERA(
        firmar, encendida, cola, motor):
    m = motor({"estado": "creado", "id_cliente": "9001"})
    c = firmar()

    assert c["estado"] == "firmado", "la firma contesta enseguida: el alta va después"
    assert c["alta"]["estado"] == "pedida"
    assert c["se_puede_anular"] is False, "con el alta en vuelo no se anula"
    assert len(cola) == 1 and cola[0]["args"][1] == c["id"], "UNA tarea, de ESTE contrato"
    assert m.pedidos == [], "y dentro de la firma no se le pidió nada al motor"


def test_a2_con_la_empresa_APAGADA_firmar_no_pide_nada(firmar, apagada, cola, motor):
    """EL CONTROL de a1, y la garantía de que desplegar esto no cambia nada
    para una empresa que no lo encendió."""
    m = motor({"estado": "creado", "id_cliente": "9001"})
    c = firmar()

    assert c["estado"] == "firmado" and c["alta"]["estado"] is None
    assert c["se_puede_anular"] is True
    assert cola == [] and m.pedidos == []


def test_a3_reintentar_la_firma_NO_pide_otra_alta(firmar, user_client, orden, encendida,
                                                  cola, motor,
                                                  django_capture_on_commit_callbacks):
    motor({"estado": "creado", "id_cliente": "9001"})
    c = firmar()
    with django_capture_on_commit_callbacks(execute=True):
        otra = user_client.post(_url(orden), _cuerpo(ip=IP), format="json")

    assert otra.status_code == 200 and otra.json()["contrato"]["id"] == c["id"]
    assert len(cola) == 1, "el segundo envío del teléfono no encola otra tarea"


# =========================================================================== #
#  B. LA TAREA
# =========================================================================== #
def test_b1_el_motor_lo_crea_y_el_contrato_queda_EN_EL_ISP_con_su_numero(
        firmar, encendida, cola, motor, orden):
    m = motor({"estado": "creado", "id_cliente": "9001", "avisos": [], "emitido": True})
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.estado == "en_el_isp" and fila.servicio_isp == "9001"
    assert fila.alta_estado == "" and fila.alta_codigo == "creado"
    assert len(cola) == 1, "resuelto: no se vuelve a encolar"

    #  LO QUE VIAJÓ: los datos TAL COMO SE FIRMARON, quién firmó, y el pedido 1.
    pedido = m.pedidos[0]
    assert pedido["url"].endswith(f"/interno/contrato/{c['id']}/crear-cliente")
    assert pedido["params"] == {"tenant": "empresa-uno"}
    cuerpo = pedido["json"]
    assert cuerpo["intento"] == 1
    assert cuerpo["actor"] and "@" not in cuerpo["actor"], "el nombre, nunca el correo"
    datos = cuerpo["datos"]
    assert datos["zona"] == 20053 and datos["ip"] == IP and datos["plan"] == "Fibra 300 Mb"
    assert datos["cliente"] == {
        "nombre": "Laura", "apellido": "Gómez Ríos", "documento": "1043000000",
        "correo": "laura@ejemplo.co", "telefono": "3000000000",
        "direccion": "Cra 21 # 45-12", "barrio": "Villa Estadio"}
    assert (str(datos["coordenadas"]["lat"]), str(datos["coordenadas"]["lng"])) == \
           ("10.9108", "-74.8186"), "las coordenadas del contrato: las del ticket"
    assert datos["nota"] == f"Contrato {fila.numero} · OT-{orden.numero}"
    assert set(cuerpo) == {"actor", "datos", "intento"}, \
        "y nada más: ni «reintentar» ni un origen propio; la ruta del motor los rechaza"


def test_b2_EN_CURSO_se_vuelve_a_mirar_SIN_volver_a_crear_y_con_LO_MINIMO(
        firmar, encendida, cola, motor):
    m = motor(EN_CURSO, {"estado": "creado", "id_cliente": "9002", "emitido": True})
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.estado == "firmado" and fila.alta_estado == "en_curso"
    assert fila.alta_tarea == "tarea-1" and fila.alta_emitida is True
    assert len(cola) == 2 and cola[1]["espera"] == tasks.ESPERA_DEL_ALTA, \
        "se encola a sí misma para más tarde"
    assert cola[1]["args"][2] == 1, "y es la vuelta siguiente"

    _correr(cola[1])
    fila = _fila(c["id"])
    assert fila.estado == "en_el_isp" and fila.servicio_isp == "9002"
    assert m.rutas() == ["crear-cliente", "comprobar-cliente"], \
        "la segunda vuelta solo COMPRUEBA: no pide crear otra vez"
    segundo = m.pedidos[1]["json"]
    assert set(segundo) == {"datos", "tarea"} and segundo["tarea"] == "tarea-1"
    #  REVISIÓN DE PII: para reconocer al cliente no hace falta su domicilio.
    assert segundo["datos"] == {
        "zona": 20053, "ip": IP, "plan": "Fibra 300 Mb",
        "cliente": {"nombre": "Laura", "apellido": "Gómez Ríos", "documento": "1043000000"}}


def test_b3_la_IP_de_OTRO_sin_haber_pedido_nada_es_un_fallo_y_se_dice_que_hacer(
        firmar, encendida, cola, motor):
    motor(IP_DE_OTRO)
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.estado == "firmado", "el contrato sigue firmado"
    assert fila.alta_estado == "fallida" and fila.alta_codigo == "ip_ocupada"
    assert fila.alta_emitida is False, "nunca se le pidió nada al proveedor"
    assert "otro cliente" in fila.alta_detalle and "firma otro" in fila.alta_detalle, \
        "aquí SÍ corresponde elegir otra IP: nunca habíamos pedido nada"
    assert len(cola) == 1, "un fallo NO se vuelve a encolar: lo decide una persona"
    d = fila.como_dict()
    assert d["se_puede_anular"] is True and d["alta"]["se_puede_pedir"] is True


def test_b4_si_el_MOTOR_NO_CONTESTA_no_se_da_por_fallido_y_se_pide_con_el_MISMO_numero(
        firmar, encendida, cola, motor, caplog):
    m = motor(ConnectionError("no se pudo conectar pidiendo el alta de 1043000000"),
              {"estado": "creado", "id_cliente": "9003", "emitido": True})
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.alta_estado == "pedida" and fila.alta_codigo == "sin_respuesta", \
        "no se sabe si salió: sigue pedida, no fallida"
    assert fila.alta_emitida is True, "y desde ahora cuenta como que pudo haber salido"
    assert len(cola) == 2, "y se vuelve a intentar más tarde"
    assert "1043000000" not in caplog.text, "el error va por TIPO: sin datos del cliente en el log"

    _correr(cola[1])
    assert _fila(c["id"]).estado == "en_el_isp"
    assert [p["json"]["intento"] for p in m.pedidos] == [1, 1], \
        "el MISMO número de pedido: el motor no lo saca dos veces"
    assert m.rutas() == ["crear-cliente", "crear-cliente"]


def test_b6_un_contrato_que_ya_NO_esta_firmado_no_se_toca(firmar, encendida, cola, motor):
    m = motor({"estado": "creado", "id_cliente": "9004"})
    c = firmar()
    ContratoDeServicio.objects.filter(pk=c["id"]).update(estado="anulado")
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.estado == "anulado" and fila.servicio_isp == ""
    assert m.pedidos == [], "a un contrato anulado no se le crea ningún cliente"


def test_b7_sin_saber_de_que_EMPRESA_es_no_se_le_pide_nada_al_motor(
        firmar, encendida, cola, monkeypatch):
    pedidos = []
    monkeypatch.setattr(alta_en_el_isp.requests, "post",
                        lambda *a, **k: pedidos.append(a) or _Respuesta({"estado": "creado"}))
    c = firmar()                    # sin `motor`: la organización no tiene empresa
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.alta_estado == "fallida" and fila.alta_codigo == "sin_empresa"
    assert pedidos == []


# =========================================================================== #
#  C. ANULAR
# =========================================================================== #
def test_c1_con_el_alta_EN_VUELO_no_se_anula_y_cuando_falla_si(
        firmar, user_client, encendida, cola, motor):
    motor(_Respuesta({"estado": "plan_desconocido", "motivo": "no está"}, 409))
    c = firmar()

    r = _anular(user_client, c["id"])
    assert r.status_code == 409, r.content
    assert "todavía no se sabe" in r.json()["detail"]
    assert _fila(c["id"]).estado == "firmado"

    _correr(cola[0])                                   # termina: fallida
    r = _anular(user_client, c["id"])
    assert r.status_code == 200, r.content
    assert _fila(c["id"]).estado == "anulado"


# =========================================================================== #
#  D. EL BOTON
# =========================================================================== #
def test_d1_volver_a_pedirlo_es_OTRO_pedido_y_queda_QUIEN_lo_pidio(
        firmar, admin_client, admin_profile, encendida, cola, motor,
        django_capture_on_commit_callbacks):
    m = motor(RECHAZADO, {"estado": "creado", "id_cliente": "9005", "emitido": True})
    c = firmar()                                       # firma el técnico
    _correr(cola[0])
    fila = _fila(c["id"])
    assert fila.alta_estado == "fallida" and fila.alta_codigo == "fallo"
    assert "rechazó" in fila.alta_detalle

    r = _pedir(admin_client, c["id"], django_capture_on_commit_callbacks)   # insiste gestión
    assert r.status_code == 202, r.content
    assert r.json()["contrato"]["alta"]["estado"] == "pedida"
    fila = _fila(c["id"])
    assert fila.alta_intento == 2 and fila.alta_pedida_por_id == admin_profile.id
    assert len(cola) == 2 and len(cola[1]["args"]) == 2, \
        "la tarea no lleva ningún «reintentar»: solo de qué contrato es"

    _correr(cola[1])
    assert _fila(c["id"]).estado == "en_el_isp"
    assert [p["json"]["intento"] for p in m.pedidos] == [1, 2], \
        "un pedido nuevo: lo que falló no se reejecuta, se pide otra vez"
    assert m.pedidos[0]["json"]["actor"] != m.pedidos[1]["json"]["actor"], \
        "y el actor del segundo es quien tocó el botón, no quien firmó"


def test_d3_con_el_alta_en_vuelo_el_boton_no_encola_otra(
        firmar, user_client, encendida, cola, motor, django_capture_on_commit_callbacks):
    motor({"estado": "creado", "id_cliente": "9007"})
    c = firmar()                                       # queda pedida

    r = _pedir(user_client, c["id"], django_capture_on_commit_callbacks)
    assert r.status_code == 409, r.content
    assert len(cola) == 1 and _fila(c["id"]).alta_intento == 1


def test_d4_con_la_empresa_apagada_el_boton_lo_dice(
        firmar, user_client, apagada, cola, motor, django_capture_on_commit_callbacks):
    motor({"estado": "creado", "id_cliente": "9008"})
    c = firmar()

    r = _pedir(user_client, c["id"], django_capture_on_commit_callbacks)
    assert r.status_code == 409 and "no tiene encendido" in r.json()["detail"]
    assert cola == [] and _fila(c["id"]).alta_estado == ""


def test_d5_OTRA_EMPRESA_no_pide_el_alta_de_este_contrato(
        firmar, org_b_client, encendida, cola, motor, django_capture_on_commit_callbacks):
    motor({"estado": "creado", "id_cliente": "9009"})
    c = firmar()

    assert _pedir(org_b_client, c["id"], django_capture_on_commit_callbacks).status_code == 404
    assert len(cola) == 1


def test_d6_un_contrato_que_YA_ESTA_en_el_ISP_no_se_pide_otra_vez(
        firmar, user_client, encendida, cola, motor, django_capture_on_commit_callbacks):
    motor({"estado": "creado", "id_cliente": "9010"})
    c = firmar()
    _correr(cola[0])

    r = _pedir(user_client, c["id"], django_capture_on_commit_callbacks)
    assert r.status_code == 200 and r.json()["contrato"]["estado"] == "en_el_isp"
    assert len(cola) == 1, "ya está creado: no hay nada que pedir"


def test_d7_el_contrato_no_se_pide_SIN_FIN(firmar, user_client, encendida, cola, motor,
                                           django_capture_on_commit_callbacks):
    motor(RECHAZADO)
    c = firmar()
    _correr(cola[0])
    ContratoDeServicio.objects.filter(pk=c["id"]).update(
        alta_intento=alta_en_el_isp.PEDIDOS_POR_CONTRATO)

    r = _pedir(user_client, c["id"], django_capture_on_commit_callbacks)
    assert r.status_code == 409, r.content
    fila = _fila(c["id"])
    assert fila.alta_codigo == "demasiados_pedidos" and len(cola) == 1


# =========================================================================== #
#  G. «NO SE» NO ES «FALLO»
#
#  Auditoría de frontera, 25/11/2026. Lo incierto quedaba `fallida`, un
#  contrato `fallida` se puede anular, y el mensaje llegaba a decir «anula y
#  firma otro con otra IP». Con el primer cliente quizá creado, eso es DOS.
# =========================================================================== #
def test_g1_si_NO_SE_PUDO_CONFIRMAR_queda_POR_REVISAR_y_no_se_anula_ni_se_reintenta(
        firmar, user_client, encendida, cola, motor, org_a,
        django_capture_on_commit_callbacks):
    motor(EN_CURSO)
    c = firmar()
    _correr(cola[0])
    _hasta_rendirse(c["id"], org_a.id)

    fila = _fila(c["id"])
    assert fila.estado == "firmado" and fila.alta_estado == "por_revisar"
    assert fila.alta_estado != "fallida", "EL CONTROL: «no sé» no se escribe como «falló»"
    assert fila.alta_codigo == "sin_confirmar" and "NO anules" in fila.alta_detalle
    d = fila.como_dict()
    assert d["se_puede_anular"] is False and d["alta"]["se_puede_pedir"] is False
    assert d["alta"]["por_revisar"] is True
    antes = len(cola)

    r = _anular(user_client, c["id"])
    assert r.status_code == 409 and "gestión" in r.json()["detail"]
    r = _pedir(user_client, c["id"], django_capture_on_commit_callbacks)
    assert r.status_code == 409 and "gestión" in r.json()["detail"]
    fila = _fila(c["id"])
    assert fila.estado == "firmado" and fila.alta_estado == "por_revisar"
    assert len(cola) == antes and fila.alta_intento == 1, "y no salió ningún pedido nuevo"


def test_g2_una_ficha_SIN_RECONOCER_se_sigue_mirando_y_al_final_va_a_revision(
        firmar, encendida, cola, motor, org_a):
    """Puede ser la nuestra a medio armar: no se decide en la primera mirada."""
    motor(NO_RECONOCIDO)
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.alta_estado == "en_curso" and fila.alta_codigo == "no_reconocido"
    assert len(cola) == 2, "se sigue mirando"
    assert fila.servicio_isp == "", "y NO se escribe el número de una ficha sin reconocer"

    _hasta_rendirse(c["id"], org_a.id)
    fila = _fila(c["id"])
    assert fila.alta_estado == "por_revisar" and fila.alta_codigo == "no_reconocido"
    assert "Casi seguro es él" in fila.alta_detalle and "NO anules" in fila.alta_detalle


def test_g3_la_IP_TOMADA_despues_de_haber_pedido_NO_es_de_otro(
        firmar, admin_client, encendida, cola, motor, django_capture_on_commit_callbacks):
    """El camino del duplicado, cerrado: el primer pedido salió, el segundo
    encuentra la IP tomada. Antes decía «elige otra IP»."""
    motor(RECHAZADO, IP_DE_OTRO)
    c = firmar()
    _correr(cola[0])                                   # salió, y el proveedor dijo que no
    assert _fila(c["id"]).alta_emitida is True
    assert _pedir(admin_client, c["id"], django_capture_on_commit_callbacks).status_code == 202
    _correr(cola[1])                                   # ahora la IP está tomada

    fila = _fila(c["id"])
    assert fila.alta_estado == "por_revisar" and fila.alta_codigo == "ip_tomada_tras_pedir"
    assert "puede ser él" in fila.alta_detalle and "NO anules" in fila.alta_detalle
    assert "firma otro con una IP distinta" not in fila.alta_detalle


def test_g4_un_resultado_DESCONOCIDO_de_un_pedido_que_salio_no_se_adivina(
        firmar, encendida, cola, motor):
    motor(_Respuesta({"estado": "algo_nuevo_del_motor", "emitido": True}, 409))
    c = firmar()
    _correr(cola[0])
    assert _fila(c["id"]).alta_estado == "por_revisar"


def test_g5_GESTION_dice_que_SI_quedo_y_el_contrato_pasa_al_ISP_con_ese_numero(
        firmar, user_client, admin_client, admin_profile, encendida, cola, motor, org_a):
    motor(EN_CURSO)
    c = firmar()
    _correr(cola[0])
    _hasta_rendirse(c["id"], org_a.id)

    #  El técnico no: es afirmar algo sobre el sistema del proveedor.
    assert _resolver(user_client, c["id"], quedo_creado=True,
                     id_cliente="9020").status_code in (403, 404)
    assert _fila(c["id"]).alta_estado == "por_revisar"

    #  Sin el número no alcanza, y sin decir sí o no tampoco.
    assert _resolver(admin_client, c["id"], quedo_creado=True).status_code == 400
    assert _resolver(admin_client, c["id"], quedo_creado="si", id_cliente="9020").status_code == 400
    assert _resolver(admin_client, c["id"], quedo_creado=True,
                     id_cliente="9020; drop").status_code == 400
    assert _fila(c["id"]).alta_estado == "por_revisar"

    r = _resolver(admin_client, c["id"], quedo_creado=True, id_cliente="9020")
    assert r.status_code == 200, r.content
    fila = _fila(c["id"])
    assert fila.estado == "en_el_isp" and fila.servicio_isp == "9020"
    assert fila.alta_codigo == "resuelto_a_mano"
    assert fila.alta_resuelta_por_id == admin_profile.id and fila.alta_resuelta_en is not None


def test_g6_GESTION_dice_que_NO_quedo_y_recien_ahi_se_puede_anular_o_reintentar(
        firmar, user_client, admin_client, admin_profile, encendida, cola, motor, org_a,
        django_capture_on_commit_callbacks):
    #  En curso al pedir, en curso en la última mirada, y creado en el pedido nuevo.
    m = motor(EN_CURSO, EN_CURSO, {"estado": "creado", "id_cliente": "9021", "emitido": True})
    c = firmar()
    _correr(cola[0])
    _hasta_rendirse(c["id"], org_a.id)

    r = _resolver(admin_client, c["id"], quedo_creado=False)
    assert r.status_code == 200, r.content
    fila = _fila(c["id"])
    assert fila.alta_estado == "fallida" and fila.alta_codigo == "no_quedo_creado"
    assert fila.alta_resuelta_por_id == admin_profile.id
    d = fila.como_dict()
    assert d["se_puede_anular"] is True and d["alta"]["se_puede_pedir"] is True

    antes = len(cola)
    assert _pedir(user_client, c["id"], django_capture_on_commit_callbacks).status_code == 202
    _correr(cola[antes])
    assert _fila(c["id"]).estado == "en_el_isp"
    assert m.pedidos[-1]["json"]["intento"] == 2, "y es un pedido nuevo"


def test_g7_solo_se_resuelve_lo_que_ESTA_por_revisar(firmar, admin_client, encendida,
                                                     cola, motor, org_b_client):
    motor(IP_DE_OTRO)
    c = firmar()
    _correr(cola[0])                                   # fallida, no por revisar

    assert _resolver(admin_client, c["id"], quedo_creado=True, id_cliente="1").status_code == 400
    assert _resolver(org_b_client, c["id"], quedo_creado=False).status_code in (403, 404)
    fila = _fila(c["id"])
    assert fila.estado == "firmado" and fila.alta_estado == "fallida"


# =========================================================================== #
#  H. UNA IP, UN CONTRATO
# =========================================================================== #
def _otra_orden(org, profile, version, numero=302, ticket="91299"):
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="PEDRO RUIZ", cliente_direccion="Cll 9 # 1-2",
        origen_sistema="wisphub", origen_tipo="ticket", origen_ref=f"#{ticket}",
        estado_operativo=OrdenTrabajo.ASIGNADA, revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=profile,
                                     rol="tecnico_lider", es_principal=True)
    _solicitud(org, ticket=ticket, numero_documento="1043000777")
    return o


def test_h1_dos_contratos_NO_eligen_la_misma_IP(firmar, user_client, user_profile, apagada,
                                               org_a, version_instalacion):
    c = firmar()
    otra = _otra_orden(org_a, user_profile, version_instalacion)

    r = user_client.post(_url(otra), _cuerpo(ip=IP), format="json")
    assert r.status_code == 400, r.content
    assert "ya la eligió otro contrato" in r.json()["detail"]
    assert not ContratoDeServicio.objects.filter(orden=otra).exists()

    #  EL CONTROL: con OTRA IP sí, y con la misma cuando el primero se anula.
    assert _anular(user_client, c["id"]).status_code == 200
    r = user_client.post(_url(otra), _cuerpo(ip=IP), format="json")
    assert r.status_code == 201, r.content


def test_h2_sin_IP_elegida_no_hay_nada_que_reservar(user_client, user_profile, orden, apagada,
                                                    org_a, version_instalacion):
    _solicitud(org_a)
    assert user_client.post(_url(orden), _cuerpo(), format="json").status_code == 201
    otra = _otra_orden(org_a, user_profile, version_instalacion)
    assert user_client.post(_url(otra), _cuerpo(), format="json").status_code == 201


# =========================================================================== #
#  F. LA OFICINA LO VE
#
#  La app instalada no muestra un alta que fallo. La bandeja de Instalaciones
#  es donde queda a la vista; sin esto seria un fallo en silencio.
# =========================================================================== #
URL_BANDEJA = "/api/solicitudes/bandeja/?estado=aprobada"


def test_f1_la_oficina_VE_que_el_cliente_no_quedo_creado_y_por_que(
        firmar, admin_client, encendida, cola, motor):
    motor(IP_DE_OTRO)
    c = firmar()
    _correr(cola[0])

    filas = admin_client.get(URL_BANDEJA).json()["solicitudes"]
    assert len(filas) == 1
    contrato = filas[0]["contrato"]
    assert contrato["id"] == c["id"] and contrato["estado"] == "firmado"
    assert contrato["alta"]["estado"] == "fallida"
    assert "otro cliente" in contrato["alta"]["detalle"]
    assert contrato["alta"]["se_puede_pedir"] is True, "y la pantalla puede ofrecer reintentar"


def test_f2_cuando_quedo_creado_dice_el_numero_del_cliente(
        firmar, admin_client, encendida, cola, motor):
    motor({"estado": "creado", "id_cliente": "9011"})
    firmar()
    _correr(cola[0])

    contrato = admin_client.get(URL_BANDEJA).json()["solicitudes"][0]["contrato"]
    assert contrato["estado"] == "en_el_isp" and contrato["servicio_isp"] == "9011"
    assert contrato["alta"]["estado"] is None


def test_f3_una_solicitud_SIN_contrato_no_trae_ninguno(admin_client, org_a):
    _solicitud(org_a)
    assert admin_client.get(URL_BANDEJA).json()["solicitudes"][0]["contrato"] is None


def test_f4_un_contrato_ANULADO_no_es_el_de_la_solicitud(firmar, admin_client, apagada, cola):
    c = firmar()
    ContratoDeServicio.objects.filter(pk=c["id"]).update(estado="anulado")
    assert admin_client.get(URL_BANDEJA).json()["solicitudes"][0]["contrato"] is None


def test_f5_lo_que_esta_POR_REVISAR_llega_a_la_oficina_como_tal(
        firmar, admin_client, encendida, cola, motor, org_a):
    motor(EN_CURSO)
    c = firmar()
    _correr(cola[0])
    _hasta_rendirse(c["id"], org_a.id)

    alta = admin_client.get(URL_BANDEJA).json()["solicitudes"][0]["contrato"]["alta"]
    assert alta["estado"] == "por_revisar" and alta["por_revisar"] is True
    assert alta["se_puede_pedir"] is False


# =========================================================================== #
#  E. LA CONFIGURACION
# =========================================================================== #
URL_CONFIG = "/api/campo/contrato/configuracion/"


def test_e1_el_interruptor_viene_APAGADO_y_lo_enciende_gestion(admin_client, user_client):
    assert admin_client.get(URL_CONFIG).json()["crear_en_el_isp"] is False
    assert user_client.put(URL_CONFIG, {"crear_en_el_isp": True},
                           format="json").status_code in (403, 404)
    assert admin_client.get(URL_CONFIG).json()["crear_en_el_isp"] is False, \
        "quien no gestiona no lo enciende"

    assert admin_client.put(URL_CONFIG, {"crear_en_el_isp": True},
                            format="json").status_code == 200
    assert admin_client.get(URL_CONFIG).json()["crear_en_el_isp"] is True


def test_e2_un_si_que_no_es_un_si_no_lo_enciende(admin_client):
    assert admin_client.put(URL_CONFIG, {"crear_en_el_isp": "true"},
                            format="json").status_code == 400
    assert admin_client.get(URL_CONFIG).json()["crear_en_el_isp"] is False


# =========================================================================== #
#  I. UN RECHAZO DE ENTRADA DEL MOTOR ES «NO SALIO» (27/11/2026)
#     OT-502: el motor contesto 400 «un alta no acepta [...]» 13 veces y el
#     contrato quedo «por revisar», como si hubiera podido salir. Un 4xx sin
#     «estado» es su validacion: no le pidio nada al proveedor.
# =========================================================================== #
def test_i1_el_400_de_entrada_deja_el_alta_FALLIDA_con_el_motivo_y_sin_reintentos(
        firmar, encendida, cola, motor):
    motor(_Respuesta({"error": "un alta no acepta ['marca_de_la_caja']: como se llama cada "
                               "dato en el proveedor lo dice la configuracion del tenant."}, 400))
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.alta_estado == "fallida" and fila.alta_codigo == "rechazado_por_el_motor"
    assert "no se creó nada" in fila.alta_detalle and "marca_de_la_caja" in fila.alta_detalle
    assert fila.alta_emitida is False, "se sabe que no salió"
    assert len(cola) == 1, "y no se repite: el mismo pedido se rechazaría igual"


@pytest.mark.parametrize("respuesta", [
    _Respuesta({"error": "algo"}, 500),        # el motor se cayó: no se sabe
    _Respuesta({"error": "algo"}, 408),        # se cortó esperando: no se sabe
])
def test_i2_un_5xx_o_un_408_siguen_siendo_NO_SE_SABE(firmar, encendida, cola, motor, respuesta):
    motor(respuesta)
    c = firmar()
    _correr(cola[0])

    fila = _fila(c["id"])
    assert fila.alta_estado == "pedida" and fila.alta_codigo == "sin_respuesta"
    assert fila.alta_emitida is True


def test_i3_si_YA_HABIA_SALIDO_antes_un_400_no_lo_da_por_fallido(firmar, encendida, cola, motor):
    motor(ConnectionError("cortado"), _Respuesta({"error": "un alta no acepta ['x']"}, 400))
    c = firmar()
    _correr(cola[0])                       # el primero pudo haber salido
    _correr(cola[1])

    fila = _fila(c["id"])
    assert fila.alta_estado == "pedida" and fila.alta_emitida is True, \
        "un pedido anterior pudo haber salido: eso no lo borra un 400 posterior"
