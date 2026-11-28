"""
ACTIVAR LA ONU DE UNA INSTALACION DESDE LA APP  --  26/11/2026

Ver campo/activacion_onu.py. El motor (que es el que escribe) tiene sus propias
pruebas (tests/test_activar_onu.py); aca se prueba lo de este lado: lo que se
le pide, cuando NO se pide, como se anota lo que contesta, y que «no se» nunca
queda como «fallo».
"""
import pytest
from django.utils import timezone

from campo import activacion_onu as A
from campo.contrato import ConfiguracionDeContrato, ContratoDeServicio
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

ZONAS = ["VILLA ADELA 2", "VILLA ADELA 1", "SAN VICENTE", "CANDELARIA 1", "CIUDAD BOLIVAR"]


@pytest.fixture
def orden(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="instalacion_fibra", nombre="Instalación",
                                 labor="instalacion")
    v = WorkTypeVersion.objects.create(work_type=wt, version=1, schema_version=1,
                                       estado=WorkTypeVersion.PUBLICADA,
                                       esquema={"campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(org=org_a, numero=701, tipo_trabajo_version=v,
                                    cliente_nombre="LAURA", estado_operativo=OrdenTrabajo.ASIGNADA,
                                    revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico_lider",
                                     es_principal=True)
    return o


@pytest.fixture
def config(org_a):
    return ConfiguracionDeContrato.objects.create(
        org=org_a, activar_onu=True,
        servidores=[{"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1", "vlan": 300},
                    {"id_zona": 20061, "nombre": "CORTE 30 - SERVIDOR 2"}])


@pytest.fixture
def contrato(org_a, orden, user_profile):
    return ContratoDeServicio.objects.create(
        org=org_a, orden=orden, numero="C-1", huella="h" * 64, estado="firmado",
        firmado_por=user_profile, firmado_en=timezone.now(),
        datos={"cliente": {"nombre": "LAURA MARCELA", "apellido": "PINEDA", "barrio": "Villa Adela 2"},
               "servidor": {"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1"}})


@pytest.fixture
def motor(monkeypatch):
    """El motor, de mentira: anota lo que se le pide y contesta lo que se le diga."""
    class Motor:
        llamadas = []
        respuestas = {}

        def __call__(self, org_id, ruta, cuerpo, espera):
            self.llamadas.append((ruta, cuerpo))
            for clave, r in self.respuestas.items():
                if clave in ruta:
                    return r
            return None

    m = Motor()
    m.llamadas, m.respuestas = [], {}
    monkeypatch.setattr(A, "_llamar", m)
    return m


@pytest.fixture
def cola(monkeypatch):
    from campo import tasks

    encoladas = []
    monkeypatch.setattr(tasks.activar_onu_en_la_red, "delay", lambda *a: encoladas.append(a))
    monkeypatch.setattr(tasks.activar_onu_en_la_red, "apply_async",
                        lambda args, countdown: encoladas.append(tuple(args)))
    return encoladas


# =========================================================================== #
#  A. LA ZONA SUGERIDA
# =========================================================================== #
@pytest.mark.parametrize("barrio,esperada", [
    ("Villa Adela 2", "VILLA ADELA 2"),           # igual, sin importar mayusculas
    ("san vicente", "SAN VICENTE"),
    ("Barrio Candelaria 1", "CANDELARIA 1"),      # la contiene
    ("Ciudad Bolívar", "CIUDAD BOLIVAR"),         # sin tildes
    ("Villa Adela", ""),                          # dos la contienen: no adivina
    ("El Prado", ""),                             # ninguna
    ("", ""),
])
def test_a1_la_zona_se_SUGIERE_por_el_barrio_y_no_se_adivina(barrio, esperada):
    assert A.sugerir_zona(barrio, ZONAS) == esperada


# =========================================================================== #
#  B. LA CONFIGURACION: el interruptor y la VLAN de cada servidor
# =========================================================================== #
def test_b1_la_vlan_va_con_su_servidor_y_el_interruptor_es_si_o_no(admin_client):
    url = "/api/campo/contrato/configuracion/"
    r = admin_client.put(url, {"activar_onu": True, "servidores": [
        {"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1", "vlan": 300},
        {"id_zona": 20061, "nombre": "CORTE 30 - SERVIDOR 2"}]}, format="json")
    assert r.status_code == 200, r.content
    d = admin_client.get(url).json()
    assert d["activar_onu"] is True
    assert d["servidores"] == [{"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1", "vlan": 300},
                               {"id_zona": 20061, "nombre": "CORTE 30 - SERVIDOR 2"}]
    for malo in ({"activar_onu": "true"},
                 {"servidores": [{"id_zona": 1, "nombre": "X", "vlan": 5000}]},
                 {"servidores": [{"id_zona": 1, "nombre": "X", "vlan": "300"}]}):
        assert admin_client.put(url, malo, format="json").status_code == 400


def test_b2_de_fabrica_esta_APAGADO(org_a):
    from campo.contrato import configuracion_de
    assert configuracion_de(org_a)["activar_onu"] is False


# =========================================================================== #
#  C. CUANDO NO SE PIDE
# =========================================================================== #
def test_c1_apagado_sin_contrato_o_sin_vlan_NO_se_pide(orden, user_profile, config, contrato, cola):
    config.activar_onu = False
    config.save()
    with pytest.raises(A.NoSePuedeActivar, match="no encendió"):
        A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    config.activar_onu = True
    config.save()
    for serial, zona, dice in (("ab", "X", "forma de serial"), ("FHTT12345678", " ", "Elige la zona")):
        with pytest.raises(A.NoSePuedeActivar, match=dice):
            A.pedir(orden, user_profile, serial=serial, zona=zona)
    contrato.datos = {**contrato.datos, "servidor": {"id_zona": 20061, "nombre": "CORTE 30 - SERVIDOR 2"}}
    contrato.save()
    with pytest.raises(A.NoSePuedeActivar, match="Falta la VLAN del servidor «CORTE 30 - SERVIDOR 2»"):
        A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    contrato.estado = "anulado"
    contrato.save()
    with pytest.raises(A.NoSePuedeActivar, match="Primero crea el contrato"):
        A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    assert not A.ActivacionDeOnu.objects.exists() and cola == []


# =========================================================================== #
#  D. EL PEDIDO
# =========================================================================== #
def test_d1_se_pide_con_la_vlan_del_servidor_y_un_pedido_en_vuelo_NO_se_duplica(
        orden, user_profile, config, contrato, cola):
    a = A.pedir(orden, user_profile, serial=" fhtt12345678 ", zona="VILLA ADELA 2")
    assert (a.serial, a.zona, a.vlan, a.intento, a.estado) == (
        "FHTT12345678", "VILLA ADELA 2", 300, 1, "pedida")
    assert cola == [(str(orden.org_id), str(a.id))]
    b = A.pedir(orden, user_profile, serial="FHTT12345678", zona="OTRA")
    assert b.id == a.id and A.ActivacionDeOnu.objects.count() == 1 and len(cola) == 1


def test_d2_al_motor_va_el_nombre_del_contrato_la_zona_la_vlan_y_el_numero(
        orden, user_profile, config, contrato, cola, motor):
    a = A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    motor.respuestas = {"activar-onu": {"estado": "activada", "olt": "3", "placa": "3", "puerto": "6"}}
    A.ejecutar(a)
    ruta, cuerpo = motor.llamadas[0]
    assert ruta == f"/interno/orden/{orden.id}/activar-onu"
    assert cuerpo["intento"] == 1
    assert cuerpo["datos"] == {"serial": "FHTT12345678", "zona": "VILLA ADELA 2", "vlan": 300,
                               "nombre": "LAURA MARCELA PINEDA"}
    a.refresh_from_db()
    assert (a.estado, a.olt, a.placa, a.puerto) == ("activada", "3", "3", "6")


@pytest.mark.parametrize("respuesta,estado", [
    ({"estado": "ya_estaba"}, "ya_estaba"),
    ({"estado": "no_espera", "motivo": "no aparece esperando"}, "no_espera"),
    ({"estado": "fallo"}, "fallida"),
    ({"estado": "bloqueado"}, "no_salio"),
    ({"estado": "en_curso"}, "en_curso"),
    (None, "en_curso"),                     # el motor no contesto: NO es «fallo»
])
def test_d3_cada_respuesta_queda_como_lo_que_es(orden, user_profile, config, contrato, cola, motor,
                                                 respuesta, estado):
    a = A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    motor.respuestas = {"activar-onu": respuesta} if respuesta else {}
    A.ejecutar(a)
    a.refresh_from_db()
    assert a.estado == estado


def test_d4_la_tarea_mira_hasta_el_tope_y_ahi_queda_POR_REVISAR(
        orden, user_profile, config, contrato, cola, motor, org_a):
    from campo import tasks

    a = A.pedir(orden, user_profile, serial="FHTT12345678", zona="VILLA ADELA 2")
    motor.respuestas = {"activar-onu": {"estado": "en_curso"}, "comprobar": {"estado": "en_curso"}}
    tasks.activar_onu_en_la_red(str(org_a.id), str(a.id), 0)
    a.refresh_from_db()
    assert a.estado == "en_curso" and cola[-1] == (str(org_a.id), str(a.id), 1)
    tasks.activar_onu_en_la_red(str(org_a.id), str(a.id), tasks.VUELTAS_DE_LA_ONU)
    a.refresh_from_db()
    assert a.estado == "por_revisar", "no saber no es «fallo»: lo mira la oficina"
    motor.respuestas = {"comprobar": {"estado": "activada"}}
    a.estado = "en_curso"
    a.save()
    tasks.activar_onu_en_la_red(str(org_a.id), str(a.id), 1)
    a.refresh_from_db()
    assert a.estado == "activada"


# =========================================================================== #
#  E. POR HTTP, COMO EL TECNICO
# =========================================================================== #
def test_e1_el_tecnico_busca_la_onu_y_ve_la_zona_sugerida_y_la_vlan(
        user_client, orden, config, contrato, motor):
    motor.respuestas = {"buscar": {"estado": "esperando", "olt": "3", "placa": "3", "puerto": "6",
                                   "tipo": "FD714GS1-R850", "zonas": ZONAS}}
    d = user_client.get(f"/api/campo/trabajos/{orden.id}/onu/?serial=fhtt12345678").json()
    assert d["encendido"] is True and d["ultima"] is None
    assert d["onu"]["estado"] == "esperando" and d["onu"]["zona_sugerida"] == "VILLA ADELA 2"
    assert d["onu"]["vlan"] == 300 and d["onu"]["servidor"] == "CORTE 30 - SERVIDOR 1"
    assert motor.llamadas[0] == ("/interno/onu/buscar", {"serial": "FHTT12345678"})


def test_e2_pedir_por_http_y_un_error_se_dice(user_client, orden, config, contrato, cola):
    url = f"/api/campo/trabajos/{orden.id}/onu/activar/"
    r = user_client.post(url, {"serial": "FHTT12345678", "zona": ""}, format="json")
    assert r.status_code == 400 and "zona" in r.json()["detail"]
    r = user_client.post(url, {"serial": "FHTT12345678", "zona": "VILLA ADELA 2"}, format="json")
    assert r.status_code == 202 and r.json()["activacion"]["en_vuelo"] is True
    d = user_client.get(f"/api/campo/trabajos/{orden.id}/onu/").json()
    assert d["ultima"]["estado"] == "pedida"
