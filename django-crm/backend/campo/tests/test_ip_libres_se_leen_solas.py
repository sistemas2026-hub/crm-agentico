"""LAS IP LIBRES SE LEEN SOLAS  --  27/11/2026.

Pedido del usuario: que las IP disponibles se actualicen solas. Cada empresa
elige en Programacion cada cuantas horas (`ocupacion_ip_cada_horas` en su
config del motor; 0 = solo con el boton) y `campo.tasks.leer_ocupacion_de_ip`
corre cada hora: pregunta al motor y, si toca, pide la misma lectura del
boton «Leer ocupacion». Aca no hay motor: se simulan sus dos rutas.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from campo import tasks


def test_a_la_tarea_esta_en_el_calendario_de_celery():
    from celery.schedules import crontab

    from crm.celery import app

    entrada = app.conf.beat_schedule.get("leer-ocupacion-de-ip")
    assert entrada, "sin entrada en beat_schedule el reloj no la despierta nunca"
    assert entrada["task"] == "campo.tasks.leer_ocupacion_de_ip"
    assert entrada["schedule"] == crontab(minute=20), "cada hora, lejos del minuto 5 y el 7"


def _oc(cada=1, hace=None, se_puede=True, cuando=None):
    ahora = timezone.now()
    actualizado = cuando if cuando is not None else (
        (ahora - hace).isoformat() if hace is not None else None)
    return {"cada_horas": cada, "se_puede_leer": se_puede, "actualizado_en": actualizado}, ahora


@pytest.mark.parametrize("ocupacion,toca,por_que", [
    (_oc(cada=0, hace=timedelta(days=3)), False, "0 = solo con el boton, aunque sea vieja"),
    (_oc(cada=1, hace=timedelta(days=3), se_puede=False), False, "sin herramienta que lea"),
    (_oc(cada=1, hace=None), True, "nunca se leyo: ya"),
    (_oc(cada=1, hace=timedelta(minutes=55)), True, "la de hace una hora menos segundos: SI (holgura)"),
    (_oc(cada=1, hace=timedelta(minutes=40)), False, "la de hace 40 minutos: todavia no"),
    (_oc(cada=6, hace=timedelta(hours=5, minutes=55)), True, "cada 6 horas: a las 5:55 ya"),
    (_oc(cada=6, hace=timedelta(hours=5, minutes=30)), False, "cada 6 horas: a las 5:30 no"),
    (_oc(cada="una", hace=timedelta(days=1)), False, "un numero que no es numero: no se lee"),
    (_oc(cada=1, cuando="no-es-fecha"), True, "una fecha ilegible no frena la lectura"),
    (_oc(cada=1, cuando="2026-11-27T08:00:00"), True, "una fecha sin zona se lee como UTC"),
])
def test_b_cuando_le_toca_a_una_empresa(ocupacion, toca, por_que):
    oc, ahora = ocupacion
    assert tasks._toca_leer(oc, ahora) is toca, por_que


class _Respuesta:
    def __init__(self, cuerpo, estado=200):
        self._cuerpo, self.status_code = cuerpo, estado

    def json(self):
        return self._cuerpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def motor(monkeypatch, org_a, org_b):
    """El motor simulado: org_a tiene tenant y le toca; org_b no tiene tenant."""
    import requests

    from operaciones import areas_del_tenant

    estado = {"preguntas": [], "lecturas": [], "ocupacion": {}, "falla_get": set()}
    tenants = {org_a.id: "empresa-a", org_b.id: ""}
    monkeypatch.setattr(areas_del_tenant, "tenant_de", lambda org: tenants.get(org.id, ""))
    monkeypatch.setenv("MOTOR_SERVICE_TOKEN", "token-de-prueba")

    def get(url, headers=None, params=None, timeout=None):
        estado["preguntas"].append((url.rsplit("/", 2)[-2:], params, headers, timeout))
        if params["tenant"] in estado["falla_get"]:
            return _Respuesta({}, 502)
        return _Respuesta({"ocupacion": estado["ocupacion"].get(params["tenant"], {})})

    def post(url, headers=None, json=None, timeout=None):
        estado["lecturas"].append((url.rsplit("/", 3)[-3:], json, headers, timeout))
        return _Respuesta({"leidos": 7711, "completa": True, "prefijos": 40})

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    estado["tenants"] = tenants
    return estado


def test_c_la_que_le_toca_se_lee_con_la_misma_ruta_del_boton(motor):
    motor["ocupacion"]["empresa-a"] = {"cada_horas": 1, "se_puede_leer": True,
                                       "actualizado_en": None}
    salida = tasks.leer_ocupacion_de_ip()
    assert len(motor["lecturas"]) == 1
    ruta, cuerpo, cabeceras, espera = motor["lecturas"][0]
    assert ruta == ["configuracion", "ocupacion-ip", "sincronizar"] and cuerpo == {"tenant": "empresa-a"}
    assert cabeceras.get("X-Servicio-Token") == "token-de-prueba", "el motor exige el token de servicio"
    assert espera == tasks.ESPERA_DE_LA_LECTURA_S
    assert salida["leidas"] == [{"tenant": "empresa-a", "leidos": 7711, "completa": True}]
    assert [p[1]["tenant"] for p in motor["preguntas"]] == ["empresa-a"], \
        "la empresa sin tenant no le pregunta nada al motor"


def test_d_la_que_esta_al_dia_o_no_lo_pidio_no_le_pega_al_proveedor(motor, org_b):
    motor["ocupacion"]["empresa-a"] = {"cada_horas": 1, "se_puede_leer": True,
                                       "actualizado_en": timezone.now().isoformat()}
    assert tasks.leer_ocupacion_de_ip()["al_dia"] == 1 and motor["lecturas"] == []
    motor["ocupacion"]["empresa-a"] = {"cada_horas": 0, "se_puede_leer": True,
                                       "actualizado_en": None}
    tasks.leer_ocupacion_de_ip()
    assert motor["lecturas"] == [], "0 = solo con el boton"


def test_e_una_empresa_que_falla_no_frena_a_las_demas(motor, org_b):
    motor["tenants"][org_b.id] = "empresa-b"
    motor["falla_get"].add("empresa-a")
    motor["ocupacion"]["empresa-b"] = {"cada_horas": 2, "se_puede_leer": True,
                                       "actualizado_en": None}
    salida = tasks.leer_ocupacion_de_ip()
    assert salida["errores"] == [{"tenant": "empresa-a", "error": "RuntimeError"}]
    assert [l[1] for l in motor["lecturas"]] == [{"tenant": "empresa-b"}]
