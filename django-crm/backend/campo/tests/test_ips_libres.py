# -*- coding: utf-8 -*-
"""Las IP que la app le ofrece al tecnico.

Afirma sobre el EFECTO de la ruta y del servicio, no sobre que existan. Lo que
mas vale: que una lista vacia NUNCA se rellene y que la advertencia llegue
hasta la respuesta -- la pantalla la tiene que poder mostrar, y si se queda en
un docstring nadie la ve.

El motor se reemplaza: esto no sale a la red.
"""
import pytest

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import ips_libres

pytestmark = pytest.mark.django_db


@pytest.fixture
def orden(org_a, user_profile):
    """Una orden de instalacion asignada a quien hace el pedido.

    Los mismos fixtures que `test_contrato_de_servicio.py`: es la misma
    pantalla y la misma orden.
    """
    wt = WorkType.objects.create(org=org_a, codigo="instalacion_fibra",
                                 nombre="Instalacion de fibra",
                                 labor="instalacion")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=777, tipo_trabajo_version=version,
        cliente_nombre="LAURA GOMEZ", cliente_direccion="Cra 21 # 45-12",
        origen_sistema="wisphub", origen_tipo="ticket", origen_ref="#91288",
        estado_operativo=OrdenTrabajo.ASIGNADA, revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico_lider", es_principal=True)
    return o


def _url(orden):
    return f"/api/campo/trabajos/{orden.id}/ips-libres/"


class _Respuesta:
    def __init__(self, cuerpo, ok=True, status_code=200):
        self._cuerpo = cuerpo
        self.ok = ok
        self.status_code = status_code

    def json(self):
        if self._cuerpo is _ROTO:
            raise ValueError("no es JSON")
        return self._cuerpo


_ROTO = object()


def _con_motor(monkeypatch, respuesta, tenant="rapilink", registro=None):
    def _get(url, headers=None, params=None, timeout=None):
        if registro is not None:
            registro.append({"url": url, "params": dict(params or {})})
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(ips_libres.requests, "get", _get)
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de",
                        lambda org: tenant)


LISTA = {
    "libres": ["172.16.9.2", "172.16.9.3"],
    "zona_nombre": "CORTE 15 - SERVIDOR 1",
    "prefijos": ["172.16.9."],
    "actualizado_en": "2026-11-14T10:00:00+00:00",
    "advertencia": "Ninguna de estas la tiene un CLIENTE. Los equipos de red...",
}


# =========================================================================== #
#  A · EL SERVICIO
# =========================================================================== #
def test_a1_devuelve_lo_que_el_motor_dijo(org_a, monkeypatch):
    registro = []
    _con_motor(monkeypatch, _Respuesta(LISTA), registro=registro)

    datos = ips_libres.para_la_zona(org_a, 7)

    assert datos["libres"] == ["172.16.9.2", "172.16.9.3"]
    assert datos["zona_nombre"] == "CORTE 15 - SERVIDOR 1"
    assert datos["actualizado_en"] == "2026-11-14T10:00:00+00:00"
    assert registro[0]["params"]["zona"] == 7
    assert registro[0]["params"]["tenant"] == "rapilink"


def test_a2_LA_ADVERTENCIA_LLEGA(org_a, monkeypatch):
    """Si se queda en el docstring, nadie la ve.

    Una IP libre es una que ningun CLIENTE tiene. Las antenas y los switches no
    son clientes y no estan en el listado del proveedor.
    """
    _con_motor(monkeypatch, _Respuesta(LISTA))

    assert "equipos de red" in ips_libres.para_la_zona(org_a, 7)["advertencia"]


def test_a3_el_motivo_del_motor_viaja(org_a, monkeypatch):
    _con_motor(monkeypatch, _Respuesta(
        {"libres": [], "motivo": "la ocupacion de IP no se ha sincronizado nunca"}))

    datos = ips_libres.para_la_zona(org_a, 7)
    assert datos["libres"] == []
    assert "sincronizado" in datos["motivo"]


# =========================================================================== #
#  B · LAS FORMAS DE NO SABER  --  ninguna rellena nada
# =========================================================================== #
def test_b1_sin_empresa_en_el_motor_no_ofrece(org_a, monkeypatch):
    _con_motor(monkeypatch, _Respuesta(LISTA), tenant="")

    datos = ips_libres.para_la_zona(org_a, 7)
    assert datos["libres"] == []
    assert "empresa" in datos["motivo"]


def test_b2_si_el_motor_no_contesta_no_ofrece(org_a, monkeypatch):
    _con_motor(monkeypatch, RuntimeError("se cayo"))

    datos = ips_libres.para_la_zona(org_a, 7)
    assert datos["libres"] == []
    assert datos["motivo"], "y dice por que"


def test_b3_un_error_http_del_motor_no_ofrece(org_a, monkeypatch):
    """EL CUERPO TRAE DIRECCIONES Y AUN ASI NO SE USAN.

    La primera version mandaba un 500 con el cuerpo VACIO, asi que la
    afirmacion «libres == []» se cumplia por dos motivos distintos --porque se
    rechazo el 500, o porque no habia nada que devolver-- y no distinguia
    cual. Quitar el chequeo de `r.ok` no la rompia. Con direcciones en el
    cuerpo, solo pasa si el 500 se rechaza de verdad.
    """
    _con_motor(monkeypatch, _Respuesta(LISTA, ok=False, status_code=500))

    assert ips_libres.para_la_zona(org_a, 7)["libres"] == []


def test_b4_una_respuesta_que_no_es_json_no_ofrece(org_a, monkeypatch):
    _con_motor(monkeypatch, _Respuesta(_ROTO))

    assert ips_libres.para_la_zona(org_a, 7)["libres"] == []


@pytest.mark.parametrize("zona", [None, "", "siete", {}, "7.5"])
def test_b5_una_zona_que_no_es_un_id_no_ofrece(org_a, monkeypatch, zona):
    registro = []
    _con_motor(monkeypatch, _Respuesta(LISTA), registro=registro)

    assert ips_libres.para_la_zona(org_a, zona)["libres"] == []
    assert registro == [], "y no le pregunta al motor por nada"


@pytest.mark.parametrize("falla", [
    RuntimeError("se cayo"),
    ValueError("vaya"),
    OSError("sin ruta al host"),
])
def test_b6_ninguna_excepcion_DE_RED_se_escapa(org_a, monkeypatch, falla):
    """El llamador esta en la pantalla de alguien parado en una casa.

    LA AFIRMACION ES «ninguna excepcion de red», NO «nunca levanta». La
    primera version decia lo segundo y lo probaba con un `KeyboardInterrupt`
    --que es `BaseException` y no `Exception`-- asi que ni el `except` lo
    atrapaba ni el doble lo lanzaba: la prueba pasaba por el camino
    equivocado. Y esta bien que un Ctrl-C NO se trague: ver abajo.
    """
    _con_motor(monkeypatch, falla)

    assert ips_libres.para_la_zona(org_a, 7)["libres"] == []


def test_b6b_un_ctrl_c_SI_se_propaga(org_a, monkeypatch):
    #  `except Exception` y no `except BaseException`, a proposito: tragarse un
    #  KeyboardInterrupt o un SystemExit dejaria un proceso que no se puede
    #  matar. No es un descuido, es la linea.
    def _get(*a, **k):
        raise KeyboardInterrupt()

    monkeypatch.setattr(ips_libres.requests, "get", _get)
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de",
                        lambda org: "rapilink")

    with pytest.raises(KeyboardInterrupt):
        ips_libres.para_la_zona(org_a, 7)


# =========================================================================== #
#  C · EL TOPE
# =========================================================================== #
def test_c1_se_recorta_lo_que_el_motor_manda_de_mas(org_a, monkeypatch):
    #  No se confia en el tope del otro lado: si el motor manda 253, la
    #  pantalla no recibe 253.
    _con_motor(monkeypatch, _Respuesta(
        {"libres": [f"172.16.9.{n}" for n in range(2, 60)]}))

    assert len(ips_libres.para_la_zona(org_a, 7, cuantas=5)["libres"]) == 5


def test_c2_el_tope_tiene_techo(org_a, monkeypatch):
    registro = []
    _con_motor(monkeypatch, _Respuesta(LISTA), registro=registro)

    ips_libres.para_la_zona(org_a, 7, cuantas=100000)
    assert registro[0]["params"]["cuantas"] == ips_libres.CUANTAS_MAXIMO


@pytest.mark.parametrize("malo", [None, "", "muchas", -3, 0])
def test_c3_un_tope_ilegible_usa_el_de_fabrica(org_a, monkeypatch, malo):
    registro = []
    _con_motor(monkeypatch, _Respuesta(LISTA), registro=registro)

    ips_libres.para_la_zona(org_a, 7, cuantas=malo)
    assert registro[0]["params"]["cuantas"] >= 1


# =========================================================================== #
#  D · LA RUTA
# =========================================================================== #
def test_d1_sin_zona_contesta_200_y_lo_pide(user_client, orden):
    #  200 y no 400: la pantalla abre ANTES de que el tecnico elija la zona.
    r = user_client.get(_url(orden))

    assert r.status_code == 200, r.content
    datos = r.json()
    assert datos["libres"] == []
    assert "zona" in datos["motivo"]


def test_d2_con_zona_devuelve_la_lista(user_client, orden, monkeypatch):
    _con_motor(monkeypatch, _Respuesta(LISTA))

    r = user_client.get(_url(orden) + "?zona=7")

    assert r.status_code == 200, r.content
    assert r.json()["libres"] == ["172.16.9.2", "172.16.9.3"]
    assert "equipos de red" in r.json()["advertencia"]


def test_d3_sin_sesion_no_contesta(client, orden, monkeypatch):
    """EL PERMISO, Y NO EL 404 DE LA ORDEN.

    La primera version aceptaba 401, 403 O 404, y sin `permission_classes` la
    vista tambien termina en 404 --no hay `request.profile` con el que buscar
    la orden--. O sea que la prueba pasaba igual con el permiso quitado: no
    media el permiso, medía que la orden no se encontrara.

    Ahora se exige 401 o 403, que es lo que contesta el permiso, y se deja el
    motor contestando una lista: si alguna vez se cuela, se ve.
    """
    _con_motor(monkeypatch, _Respuesta(LISTA))

    r = client.get(_url(orden) + "?zona=7")

    assert r.status_code in (401, 403), r.content
    assert "172.16.9.2" not in r.content.decode(errors="replace")
