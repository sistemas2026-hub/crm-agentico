"""
SIN EMPRESA NO SE LE PREGUNTA NADA AL MOTOR (30/10/2026, PRD §8.17 Ola 1).

Nueve lugares del backend leian 'MOTOR_TENANT' con respaldo 'or "rapilink"':
si la variable faltaba, le pedian al motor los datos de una empresa fija. Con
una segunda empresa en la misma instalacion, eso le sirve a una los datos de
la otra. Es la misma regla que 'app_backend' sin tenant -> 0 filas
(ARQUITECTURA.md): no saber de que empresa es significa NADA, no "la de
siempre".

Dos guardas:
  - la de arquitectura recorre el backend y falla si un lector de
    'MOTOR_TENANT' vuelve a tener un valor por defecto;
  - las de comportamiento llaman a cada funcion sin la variable y afirman que
    NO salio ninguna peticion al motor, y que el resultado lo dice.
"""

import re
from pathlib import Path

import pytest
import requests

RAIZ = Path(__file__).resolve().parents[2]

#  os.environ.get("MOTOR_TENANT", "rapilink")   o
#  os.environ.get("MOTOR_TENANT", "") or "rapilink"
CON_RESPALDO = re.compile(
    r"""MOTOR_TENANT["']\s*,\s*["'][^"']+["']\s*\)"""
    r"""|MOTOR_TENANT["'][^)\n]*\)\s*or\s*["'][^"']+["']""")


def _fuentes():
    for ruta in RAIZ.rglob("*.py"):
        partes = set(ruta.relative_to(RAIZ).parts)
        if partes & {"tests", "migrations", ".venv", "node_modules"}:
            continue
        yield ruta


def test_ningun_lector_de_motor_tenant_cae_a_una_empresa_por_defecto():
    culpables = []
    for ruta in _fuentes():
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if CON_RESPALDO.search(linea):
                culpables.append(f"{ruta.relative_to(RAIZ)}:{n}")
    assert culpables == [], (
        "Estos lectores de MOTOR_TENANT caen a una empresa fija si la variable "
        "falta. Sin empresa no se pregunta: " + ", ".join(culpables))


def test_la_guarda_reconoce_las_dos_formas_de_respaldo():
    # Sin esto, una guarda que no encuentra nada podria estar ciega.
    assert CON_RESPALDO.search('os.environ.get("MOTOR_TENANT", "") or "rapilink"')
    assert CON_RESPALDO.search("os.environ.get('MOTOR_TENANT', 'otra')")
    assert not CON_RESPALDO.search('(os.environ.get("MOTOR_TENANT", "") or "").strip()')
    assert not CON_RESPALDO.search('os.environ.get("MOTOR_TENANT", "") or ""')


@pytest.fixture
def sin_empresa(monkeypatch):
    """Sin MOTOR_TENANT, y toda peticion HTTP queda anotada en vez de salir."""
    monkeypatch.delenv("MOTOR_TENANT", raising=False)
    salidas = []

    def anotar(*args, **kwargs):
        salidas.append(args[:2])
        raise requests.ConnectionError("no deberia haber salido")

    for metodo in ("get", "post", "put", "patch", "request"):
        monkeypatch.setattr(requests, metodo, anotar)
    return salidas


def test_planes_de_una_localidad_sin_empresa_devuelve_vacio_sin_preguntar(sin_empresa):
    from solicitudes.views import _planes_de

    assert _planes_de("Soledad") == []
    assert sin_empresa == []


def test_conversacion_del_caso_sin_empresa_devuelve_vacio_sin_preguntar(sin_empresa):
    from campo.services.despacho import _conversacion_del_caso

    assert _conversacion_del_caso("caso-1") == {}
    assert sin_empresa == []


@pytest.mark.django_db
def test_contexto_del_caso_sin_empresa_lo_dice_y_no_pregunta(sin_empresa):
    from campo.services.despacho import contexto_del_caso

    contexto = contexto_del_caso("00000000-0000-0000-0000-000000000000")
    assert sin_empresa == []
    assert "MOTOR_TENANT" in str(contexto.get("motivo", "")).upper()


def test_ping_sin_empresa_lo_dice_y_no_pregunta(sin_empresa):
    from campo.services.telemetria import pinguear_servicio

    resultado = pinguear_servicio("5832")
    assert sin_empresa == []
    assert resultado["ok"] is False
    assert resultado["motivo"] == "falta_motor_tenant"


@pytest.mark.parametrize("modulo, funcion, argumentos", [
    ("solicitudes.entrega", "_crear_ticket_wisphub", (object(),)),
    ("solicitudes.entrega", "_completar_ticket", (object(),)),
    ("solicitudes.entrega", "cerrar_ticket_wisphub", (object(), "motivo")),
    ("operaciones.cierre_de_caso", "_pedirle_al_motor", ("p-1", "c-1")),
])
def test_las_que_lanzan_si_falla_lanzan_sin_empresa_y_no_preguntan(
        sin_empresa, modulo, funcion, argumentos):
    import importlib

    f = getattr(importlib.import_module(modulo), funcion)
    with pytest.raises(RuntimeError, match="MOTOR_TENANT"):
        f(*argumentos)
    assert sin_empresa == []


@pytest.mark.django_db
def test_el_correo_de_una_solicitud_va_al_buzon_de_SU_empresa_y_sin_buzon_no_sale(
        monkeypatch, settings, org_a, org_b):
    """El correo lleva el PDF de la solicitud: documento, firma y GPS. Hasta el
    30/10/2026, sin destino configurado salia al buzon de UNA empresa, fijo en
    el codigo; el 31/10 se lo paso a una variable de entorno, que es una sola
    por instalacion. Ahora es de cada ORGANIZACION, y lo edita su administrador
    en Ajustes -> Organizacion (CLAUDE.md §3.3): la segunda empresa no necesita
    que nadie entre al servidor. Una variable de entorno no lo reemplaza."""
    from solicitudes.entrega import _destino

    monkeypatch.setenv("SOLICITUDES_EMAIL_DESTINO", "buzon-del-servidor@otra.co")
    settings.SOLICITUDES_EMAIL_DESTINO = "buzon-del-servidor@otra.co"
    org_a.correo_solicitudes = "a@empresa.co, b@empresa.co"
    org_a.save(update_fields=["correo_solicitudes"])
    assert _destino(org_a) == ["a@empresa.co", "b@empresa.co"]
    with pytest.raises(RuntimeError, match="correo_solicitudes"):
        _destino(org_b)


@pytest.mark.django_db
def test_el_administrador_edita_el_buzon_y_un_correo_invalido_no_entra(admin_client, org_a):
    r = admin_client.patch("/api/org/settings/", {"correo_solicitudes": "ventas@empresa.co, jefe@empresa.co"},
                           format="json")
    assert r.status_code == 200, r.content
    org_a.refresh_from_db()
    assert org_a.correo_solicitudes == "ventas@empresa.co, jefe@empresa.co"
    r = admin_client.patch("/api/org/settings/", {"correo_solicitudes": "ventas@empresa.co, no-es-un-correo"},
                           format="json")
    assert r.status_code == 400
    org_a.refresh_from_db()
    assert org_a.correo_solicitudes == "ventas@empresa.co, jefe@empresa.co"


#  Un correo entre comillas que nombra a la empresa en CUALQUIER parte: antes o
#  despues de la arroba ('info.rapilinksas@gmail.com' la nombra antes).
BUZON_DE_EMPRESA = re.compile(r"""["'][^"'\s]*@[^"'\s]*["']""")


def _buzones_de_empresa(linea: str) -> list[str]:
    return [m for m in BUZON_DE_EMPRESA.findall(linea) if "rapilink" in m.lower()]


def test_la_guarda_de_buzones_ve_el_caso_real():
    assert _buzones_de_empresa('DESTINO = "info.rapilinksas@gmail.com"')
    assert _buzones_de_empresa("x = 'ops@rapilink.co'")
    assert not _buzones_de_empresa('x = "a@empresa.co"')


def test_ningun_buzon_de_una_empresa_queda_fijo_en_el_codigo():
    culpables = []
    for ruta in _fuentes():
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if _buzones_de_empresa(linea):
                culpables.append(f"{ruta.relative_to(RAIZ)}:{n}")
    assert culpables == [], "Buzones de una empresa fijos en el codigo: " + ", ".join(culpables)


def test_gestion_de_solicitudes_sin_empresa_lanza(sin_empresa):
    from solicitudes.gestion import _tenant

    with pytest.raises(RuntimeError, match="MOTOR_TENANT"):
        _tenant()


@pytest.mark.django_db
def test_la_solicitud_de_cada_empresa_llega_a_su_buzon(org_a, org_b, mailoutbox):
    """La cadena entera hasta el correo: la solicitud de la empresa A sale al
    buzon de A, y la de B -- sin buzon configurado -- no sale a ninguno."""
    import datetime as dt

    from django.utils import timezone

    from solicitudes.entrega import _enviar_correo
    from solicitudes.models import SolicitudServicio

    org_a.correo_solicitudes = "ventas@empresa-a.co"
    org_a.save(update_fields=["correo_solicitudes"])
    ahora = timezone.now()

    def solicitud(org, token):
        return SolicitudServicio.objects.create(org=org, token_hash=token, expira_en=ahora + dt.timedelta(days=1),
                                                nombre="Beatriz", telefono="3124558901", enviada_en=ahora)

    _enviar_correo(solicitud(org_a, "a" * 64))
    assert [m.to for m in mailoutbox] == [["ventas@empresa-a.co"]]
    with pytest.raises(RuntimeError, match="correo_solicitudes"):
        _enviar_correo(solicitud(org_b, "b" * 64))
    assert len(mailoutbox) == 1, "la de la empresa sin buzon no sale a ningun otro"
