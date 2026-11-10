# -*- coding: utf-8 -*-
"""La ubicacion de la casa, camino al ISP.

LO QUE ESTE ARCHIVO DEFIENDE  --  10/11/2026

* **Django no le pega al ISP.** Lo que sale de aca va al MOTOR, que es donde
  viven la credencial y la frontera. Medido el mismo dia: `backend/` tiene
  CERO `requests.put`/`patch` contra un proveedor, y esa propiedad vale mas
  que ahorrarse un salto.
* **Los identificadores salen de la ficha CONGELADA al despachar**, no de una
  consulta nueva: un cliente puede tener mas de un equipo, y resolverlo otra
  vez escribiria la ubicacion en el equipo equivocado sin que nadie se entere.
* **Lo que no es una coordenada no viaja.** Se afirma con CERO llamadas al
  motor, no con un codigo de retorno: un codigo se puede devolver igual
  despues de haber mandado.
* **Un exito a medias se dice como tal.** Darlo por bueno deja al tecnico
  creyendo que quedo en los dos sistemas.
* **La coordenada no entra en ningun log.** Es el domicilio de una persona.
"""
from unittest import mock

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import ubicacion_al_isp

pytestmark = pytest.mark.django_db

SERIAL = "ZTEGC0A1B2C3"
SERVICIO = "WH-1042"
LAT, LNG = 10.9108, -74.8186

CONTEXTO_CONGELADO = {
    "contexto_disponible": True,
    "capturado_en": "2026-10-05T08:10:00+00:00",
    "servicio": SERVICIO,
    "sn_onu": SERIAL,
}


@pytest.fixture(autouse=True)
def _empresa(monkeypatch):
    monkeypatch.setattr(
        "operaciones.areas_del_tenant.tenant_de_organizacion",
        lambda org_id: "rapilink")


@pytest.fixture
def orden(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ubic_test",
                                 nombre="Reparación")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )
    return OrdenTrabajo.objects.create(
        org=org_a, numero=7101, tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
        contexto=dict(CONTEXTO_CONGELADO),
    )


class _Respuesta:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}" if payload is not None else b""

    def json(self):
        if self._payload is None:
            raise ValueError("sin cuerpo")
        return self._payload


def _motor_contesta(payload, status_code=200):
    return mock.patch.object(
        ubicacion_al_isp.requests, "post",
        return_value=_Respuesta(status_code, payload))


def _motor_cae():
    return mock.patch.object(
        ubicacion_al_isp.requests, "post",
        side_effect=OSError("se corto la red"))


GUARDADA = {"estado": "guardada", "motivo": "", "destinos": [
    {"herramienta": "equipo", "ok": True},
    {"herramienta": "servicio", "ok": True}]}


class _Usuario:
    """Como es el User de verdad: UN campo `name`, y nada mas.

    El doble anterior tenia `get_full_name()` y `first_name`, que este modelo
    NO tiene (`common/models.py`: `name`, y `USERNAME_FIELD = "email"`). Por
    eso las quince pruebas estaban en verde mientras el boton devolvia 400 en
    produccion: median contra un usuario imaginario.
    """

    def __init__(self, name=""):
        self.name = name


class _Perfil:
    def __init__(self, name="Mario Vasquez", pid="perfil-123"):
        self.user = _Usuario(name)
        self.id = pid


# --------------------------------------------------------------------------- #
# A. Lo que sale hacia el motor
# --------------------------------------------------------------------------- #
def test_a1_va_al_motor_y_no_al_proveedor(orden):
    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    assert r["guardada"] is True
    url = post.call_args.args[0]
    #  AL MOTOR, y por la ruta DEDICADA: la generica entra por la puerta
    #  autonoma, cerrada hoy por Autonomia 2, y el boton fallaria solo en
    #  produccion.
    assert "/interno/orden/" in url and url.endswith("/guardar-ubicacion")
    assert "wisphub" not in url and "smartolt" not in url
    assert post.call_args.kwargs["params"] == {"tenant": "rapilink"}


def test_a2_los_identificadores_salen_de_la_ficha_congelada(orden):
    #  La ficha congelada dice ESTE equipo y ESTE servicio. Resolverlos de
    #  nuevo podria dar otros, y la casa quedaria marcada en el equipo
    #  equivocado.
    orden.contexto = dict(CONTEXTO_CONGELADO, sn_onu="OTRO-SERIAL-VIEJO")
    orden.save(update_fields=["contexto"])

    with _motor_contesta(GUARDADA) as post:
        ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    enviado = post.call_args.kwargs["json"]
    assert enviado["identificadores"]["sn_onu"] == "OTRO-SERIAL-VIEJO"
    assert enviado["identificadores"]["id_servicio"] == SERVICIO


def test_a3_manda_quien_lo_decidio_y_por_su_nombre(orden):
    with _motor_contesta(GUARDADA) as post:
        ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    #  SIN ACTOR NO HAY PUERTA HUMANA: es la evidencia de que detras de la
    #  escritura hay una persona.
    assert post.call_args.kwargs["json"]["actor"] == "Mario Vasquez"


def test_a4_sin_poder_saber_quien_fue_no_se_manda(orden):
    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=None)

    assert r["guardada"] is False and r["codigo"] == "sin_actor"
    assert post.call_count == 0, "y no se hizo el viaje"


def test_a5_el_nombre_sale_del_campo_QUE_EXISTE(orden):
    #  Medido el 10/11/2026 con el boton desplegado: la funcion buscaba
    #  `get_full_name`, `first_name` y `username`, y este modelo no tiene
    #  NINGUNO de los tres. Devolvia "" y la peticion moria en 400 sin salir
    #  de Django.
    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG,
            profile=_Perfil(name="Mario Vasquez"))

    assert r["guardada"] is True, "con un usuario REAL la ubicacion sale"
    assert post.call_args.kwargs["json"]["actor"] == "Mario Vasquez"


def test_a6_sin_nombre_cargado_usa_el_perfil_y_NO_rechaza(orden):
    #  Una cuenta sin nombre es un dato faltante, no una falta de
    #  responsable. Rechazarla dejaba la capacidad muerta para esa persona.
    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG,
            profile=_Perfil(name="", pid="perfil-abc"))

    assert r["guardada"] is True
    actor = post.call_args.kwargs["json"]["actor"]
    assert "perfil-abc" in actor, f"identifica por el perfil: {actor}"
    #  EL EMAIL NO: identifica igual, pero es un dato de contacto y este valor
    #  viaja al motor y puede quedar en una fila de auditoria.
    assert "@" not in actor, f"y nunca el email: {actor}"


# --------------------------------------------------------------------------- #
# B. Lo que NO viaja
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("etiqueta,lat,lng", [
    ("el cruce 0,0", 0, 0),
    ("fuera del planeta", 91.0, -74.8),
    ("texto", "aca nomas", -74.8),
    ("vacio", None, None),
    ("NaN", float("nan"), -74.8),
])
def test_b1_lo_que_no_es_coordenada_no_llega_al_motor(orden, etiqueta, lat, lng):
    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=lat, longitud=lng, profile=_Perfil())

    assert r["guardada"] is False
    assert r["codigo"] == "coordenada_invalida", etiqueta
    #  CERO LLAMADAS, no un codigo de retorno: un codigo se puede devolver
    #  igual despues de haber mandado.
    assert post.call_count == 0, etiqueta


def test_b2_sin_con_que_identificar_al_cliente_no_se_intenta(orden):
    orden.contexto = {"contexto_disponible": True}
    orden.save(update_fields=["contexto"])

    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    assert r["guardada"] is False and r["codigo"] == "sin_identificador"
    assert post.call_count == 0


def test_b3_con_UN_identificador_si_se_intenta(orden):
    #  Hay ordenes sin serial en el contexto. Que falte uno no puede impedir
    #  escribir en el sistema donde el otro si alcanza.
    orden.contexto = {"contexto_disponible": True, "servicio": SERVICIO}
    orden.save(update_fields=["contexto"])

    with _motor_contesta(GUARDADA) as post:
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    assert r["guardada"] is True
    assert post.call_args.kwargs["json"]["identificadores"] == {
        "id_servicio": SERVICIO}


# --------------------------------------------------------------------------- #
# C. Lo que contesta el motor
# --------------------------------------------------------------------------- #
def test_c1_un_exito_a_medias_se_dice_como_tal(orden):
    parcial = {"estado": "parcial", "motivo": "el servicio no acepto",
               "destinos": [{"herramienta": "equipo", "ok": True},
                            {"herramienta": "servicio", "ok": False}]}
    with _motor_contesta(parcial, status_code=207):
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    #  GUARDADA, porque algo quedo escrito y no se deshace; y PARCIAL, porque
    #  decirle al tecnico que quedo en los dos seria mentirle.
    assert r["guardada"] is True
    assert r.get("parcial") is True
    assert r["codigo"] == "parcial"


def test_c2_el_motor_sin_responder_no_tumba_nada(orden):
    with _motor_cae():
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    #  El tecnico esta en la calle: una excepcion aca le tumba la pantalla.
    assert r["guardada"] is False and r["codigo"] == "sin_respuesta"
    assert r["detalle"] == "OSError"


def test_c3_un_rechazo_del_motor_se_devuelve_con_su_motivo(orden):
    negado = {"estado": "bloqueado_por_interruptor",
              "motivo": "detenido: apagado a mano", "destinos": []}
    with _motor_contesta(negado, status_code=409):
        r = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    assert r["guardada"] is False
    assert r["codigo"] == "bloqueado_por_interruptor"
    #  EL MOTIVO Y NO SOLO EL CODIGO: un rastro que dice que algo fallo pero
    #  no por que obliga a reproducir el fallo para diagnosticarlo.
    assert "apagado a mano" in r["detalle"]


# --------------------------------------------------------------------------- #
# D. Privacidad
# --------------------------------------------------------------------------- #
def test_d1_la_coordenada_no_entra_en_el_log(orden, caplog):
    with caplog.at_level("DEBUG"), _motor_cae():
        ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=LAT, longitud=LNG, profile=_Perfil())

    texto = " ".join(r.getMessage() for r in caplog.records)
    #  Donde vive una persona es dato de esa persona. El log dice que no se
    #  pudo guardar, nunca donde.
    assert "10.9108" not in texto and "74.8186" not in texto
    assert "OSError" in texto, "pero el tipo del fallo si, para diagnosticar"
