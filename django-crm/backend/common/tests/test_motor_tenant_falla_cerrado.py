"""
CADA COSA SE LE PIDE AL MOTOR EN NOMBRE DE SU EMPRESA (30-31/10/2026, PRD §8.17).

Historia en dos pasos:
  - Hasta el 30/10/2026, nueve lugares del backend leian 'MOTOR_TENANT' con
    respaldo 'or "rapilink"': si la variable faltaba, le pedian al motor los
    datos de una empresa fija.
  - Hasta el 31/10/2026, sin respaldo pero de la variable: UNA por
    instalacion. Con dos empresas en la misma, la solicitud de la segunda
    creaba el ticket en el WispHub de la primera, su Supervisor razonaba con el
    modelo de la primera y leia sus areas.

La ingesta de documentos al asistente, la purga de retencion y la encuesta de
cierre hacian lo mismo con 'ASISTENTE_TENANT': el documento de una empresa
terminaba en el corpus de otra, y su encuesta salia del WhatsApp de la otra.

Ahora la empresa sale de la ORGANIZACION del objeto que se trata -- la orden,
la solicitud, el caso, la propuesta, el documento -- y se la pregunta al motor
('areas_del_tenant.tenant_de'). Sin empresa, NADA: la misma regla que
'app_backend' sin tenant -> 0 filas (ARQUITECTURA.md).

Tres guardas:
  - la de arquitectura recorre el backend y falla si algo vuelve a leer
    'MOTOR_TENANT' del entorno;
  - las de "sin empresa" afirman que no sale ninguna peticion y que el
    resultado lo dice;
  - las de "dos empresas" afirman que lo de la empresa B sale con el tenant de
    B aunque el servidor tenga la variable apuntando a A.
"""

import re
from pathlib import Path

import pytest
import requests

RAIZ = Path(__file__).resolve().parents[2]

#  La lectura real de las areas, tomada al importar: el conftest raiz la
#  reemplaza por un mapa vacio en cada prueba para que nadie salga a la red.
from operaciones import areas_del_tenant as _areas  # noqa: E402

_AREAS_DE_ORG = _areas.area_por_persona_de_org

#  os.environ.get("MOTOR_TENANT" ...)  os.environ["ASISTENTE_TENANT"]
#  os.getenv("MOTOR_TENANT" ...)
LECTURA_DEL_ENTORNO = re.compile(
    r"""(environ\s*(\.get\s*\(|\[)|getenv\s*\()\s*["'](MOTOR|ASISTENTE)_TENANT["']""")


def _fuentes():
    for ruta in RAIZ.rglob("*.py"):
        partes = set(ruta.relative_to(RAIZ).parts)
        if partes & {"tests", "migrations", ".venv", "node_modules"}:
            continue
        yield ruta


def test_nadie_lee_la_empresa_de_una_variable_del_servidor():
    culpables = []
    for ruta in _fuentes():
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if LECTURA_DEL_ENTORNO.search(linea):
                culpables.append(f"{ruta.relative_to(RAIZ)}:{n}")
    assert culpables == [], (
        "Estos lugares leen la empresa de MOTOR_TENANT, que es una por "
        "instalacion: con dos empresas le piden al motor por la otra. La "
        "empresa sale de la organizacion (areas_del_tenant.tenant_de): "
        + ", ".join(culpables))


def test_la_guarda_reconoce_las_formas_de_leer_la_variable():
    # Sin esto, una guarda que no encuentra nada podria estar ciega.
    assert LECTURA_DEL_ENTORNO.search('(os.environ.get("MOTOR_TENANT", "") or "").strip()')
    assert LECTURA_DEL_ENTORNO.search("os.environ['MOTOR_TENANT']")
    assert LECTURA_DEL_ENTORNO.search('os.getenv("MOTOR_TENANT")')
    assert LECTURA_DEL_ENTORNO.search('os.environ.get("ASISTENTE_TENANT")')
    assert not LECTURA_DEL_ENTORNO.search("#  Hasta ese dia era 'MOTOR_TENANT', una variable")


@pytest.fixture
def salidas(monkeypatch):
    """Toda peticion HTTP queda anotada (url, tenant) en vez de salir."""
    anotadas = []

    def anotar(*args, **kwargs):
        url = kwargs.get("url") or (args[1] if len(args) > 1 and args[0] in
                                    ("GET", "POST", "PUT", "PATCH") else args[0])
        #  El tenant viaja en la consulta, en el cuerpo, o en la ruta.
        tenant = ((kwargs.get("params") or {}).get("tenant")
                  or (kwargs.get("json") or {}).get("tenant")
                  or (kwargs.get("data") or {}).get("tenant"))
        anotadas.append((str(url), tenant))
        raise requests.ConnectionError("no sale a la red en esta prueba")

    for metodo in ("get", "post", "put", "patch", "request"):
        monkeypatch.setattr(requests, metodo, anotar)
    return anotadas


@pytest.fixture
def sin_empresa(empresa_del_motor, salidas, monkeypatch):
    """Ninguna organizacion tiene empresa en el motor, aunque el servidor
    todavia tenga la variable vieja."""
    monkeypatch.setenv("MOTOR_TENANT", "la-del-servidor")
    return salidas


@pytest.fixture
def dos_empresas(empresa_del_motor, salidas, monkeypatch, org_a, org_b):
    """A y B, cada una con su empresa; la variable vieja apunta a A."""
    empresa_del_motor(org_a, "empresa-a")
    empresa_del_motor(org_b, "empresa-b")
    monkeypatch.setenv("MOTOR_TENANT", "empresa-a")
    return salidas


def _solicitud(org, token):
    import datetime as dt

    from django.utils import timezone

    from solicitudes.models import SolicitudServicio

    ahora = timezone.now()
    return SolicitudServicio.objects.create(
        org=org, token_hash=token, expira_en=ahora + dt.timedelta(days=1),
        nombre="Beatriz", telefono="3124558901", enviada_en=ahora,
        ticket_wisphub="77001")


# --- sin empresa: no sale nada, y se dice ---------------------------------

@pytest.mark.django_db
def test_planes_de_una_localidad_sin_empresa_devuelve_vacio_sin_preguntar(sin_empresa, org_a):
    from solicitudes.views import _planes_de

    assert _planes_de("Soledad", org_a.id) == []
    assert sin_empresa == []


@pytest.mark.django_db
def test_conversacion_del_caso_sin_empresa_devuelve_vacio_sin_preguntar(sin_empresa, org_a):
    from campo.services.despacho import _conversacion_del_caso

    assert _conversacion_del_caso("caso-1", org_a.id) == {}
    assert sin_empresa == []


@pytest.mark.django_db
def test_contexto_del_caso_sin_empresa_lo_dice_y_no_pregunta(sin_empresa):
    from campo.services.despacho import contexto_del_caso

    contexto = contexto_del_caso("00000000-0000-0000-0000-000000000000")
    assert sin_empresa == []
    assert contexto.get("motivo") == "sin_empresa"


@pytest.mark.django_db
def test_ping_sin_empresa_lo_dice_y_no_pregunta(sin_empresa, org_a):
    from campo.services.telemetria import pinguear_servicio

    resultado = pinguear_servicio("5832", org=org_a)
    assert sin_empresa == []
    assert resultado == {"ok": False, "motivo": "sin_empresa"}


@pytest.mark.django_db
@pytest.mark.parametrize("funcion", ["_crear_ticket_wisphub", "_completar_ticket",
                                     "cerrar_ticket_wisphub"])
def test_las_de_solicitudes_lanzan_sin_empresa_y_no_preguntan(sin_empresa, org_a, funcion):
    from solicitudes import entrega

    s = _solicitud(org_a, "c" * 64)
    argumentos = (s, "motivo") if funcion == "cerrar_ticket_wisphub" else (s,)
    with pytest.raises(RuntimeError, match="sin empresa en el motor"):
        getattr(entrega, funcion)(*argumentos)
    assert sin_empresa == []


@pytest.mark.django_db
def test_el_cierre_de_caso_sin_empresa_lanza_y_no_pregunta(sin_empresa, org_a):
    from operaciones import cierre_de_caso

    with pytest.raises(cierre_de_caso.SinEmpresa):
        cierre_de_caso._pedirle_al_motor("p-1", "c-1", org=org_a)
    assert sin_empresa == []


@pytest.mark.django_db
def test_gestion_de_solicitudes_sin_empresa_lanza(sin_empresa, org_a):
    from solicitudes.gestion import _tenant

    with pytest.raises(RuntimeError, match="sin empresa en el motor"):
        _tenant(org_a)
    assert sin_empresa == []


def test_el_cerebro_fuera_de_una_pasada_no_pregunta(sin_empresa):
    """La puerta al modelo sin 'razonar(org, ...)' alrededor no sabe de que
    empresa es la consulta: no sale."""
    from operaciones import cerebro

    with pytest.raises(cerebro.ErrorCerebro, match="sin empresa en el motor"):
        cerebro._pedirle_al_modelo([], [])
    assert sin_empresa == []


@pytest.mark.django_db
def test_sin_organizacion_las_areas_no_se_preguntan(sin_empresa):
    from operaciones import areas_del_tenant

    criterio = areas_del_tenant.criterio_de_area()
    assert sin_empresa == []
    assert criterio.se_sabe is False


# --- dos empresas: lo de B sale como B -----------------------------------

def _tenants(salidas):
    return [t for _, t in salidas]


@pytest.mark.django_db
def test_la_solicitud_de_b_crea_el_ticket_en_el_isp_de_b(dos_empresas, org_a, org_b):
    from solicitudes import entrega

    for org, token in ((org_b, "b" * 64), (org_a, "a" * 64)):
        with pytest.raises(requests.ConnectionError):
            entrega._crear_ticket_wisphub(_solicitud(org, token))
    assert _tenants(dos_empresas) == ["empresa-b", "empresa-a"]


@pytest.mark.django_db
def test_cerrar_y_completar_el_ticket_de_b_van_al_isp_de_b(dos_empresas, org_b):
    from solicitudes import entrega

    s = _solicitud(org_b, "d" * 64)
    for paso in (lambda: entrega.cerrar_ticket_wisphub(s, "cancelada"),
                 lambda: entrega._completar_ticket(s)):
        try:
            paso()
        except Exception:                                    # noqa: BLE001
            pass
    assert _tenants(dos_empresas) and set(_tenants(dos_empresas)) == {"empresa-b"}


@pytest.mark.django_db
def test_el_ping_y_la_senal_de_b_se_miden_en_b(dos_empresas, org_b):
    from types import SimpleNamespace

    from campo.services import telemetria

    telemetria.pinguear_servicio("5832", org=org_b)
    telemetria.medir_senal(SimpleNamespace(org_id=org_b.id, contexto={"sn_onu": "HWT1"}))
    telemetria.probar_conexion(SimpleNamespace(org_id=org_b.id, contexto={"servicio": "5832"}))
    assert _tenants(dos_empresas) == ["empresa-b"] * 3


@pytest.mark.django_db
def test_el_supervisor_de_b_razona_con_la_config_de_b(dos_empresas, org_b):
    """La empresa decide el modelo y quien paga. La pone 'razonar(org)', y al
    terminar la pasada se suelta: la puerta queda otra vez sin empresa."""
    from operaciones import cerebro

    with pytest.raises(cerebro.ErrorCerebro):
        cerebro.razonar(org_b, instrucciones="x", entrada="y")
    assert _tenants(dos_empresas) == ["empresa-b"]
    with pytest.raises(cerebro.ErrorCerebro, match="sin empresa en el motor"):
        cerebro._pedirle_al_modelo([], [])
    assert len(dos_empresas) == 1


@pytest.mark.django_db
def test_lo_que_el_supervisor_de_b_consulta_o_cierra_es_de_b(dos_empresas, org_b):
    from campo.services.despacho import _conversacion_del_caso
    from operaciones import cierre_de_caso, fuentes_adaptadores
    from solicitudes.views import _planes_de

    for paso in (lambda: fuentes_adaptadores._pedirle_al_motor(org_b, "consultar_ticket", {}),
                 lambda: fuentes_adaptadores.estado_de_autonomia(org_b),
                 lambda: fuentes_adaptadores.mover_interruptor_de_autonomia(
                     org_b, detener=True, actor="p-1", motivo="humo"),
                 lambda: cierre_de_caso._pedirle_al_motor("p-1", "c-1", org=org_b),
                 lambda: _conversacion_del_caso("c-1", org_b.id),
                 lambda: _planes_de("Soledad", org_b.id)):
        try:
            paso()
        except Exception:                                    # noqa: BLE001
            pass
    #  Seis pasos; los planes prueban dos rutas del catalogo antes de rendirse.
    assert len(dos_empresas) >= 6 and set(_tenants(dos_empresas)) == {"empresa-b"}


@pytest.mark.django_db
def test_las_areas_de_b_son_las_de_b(dos_empresas, org_a, org_b, monkeypatch):
    from django.core.cache import cache

    from operaciones import areas_del_tenant

    cache.clear()
    monkeypatch.setattr(areas_del_tenant, "area_por_persona_de_org", _AREAS_DE_ORG)
    areas_del_tenant.criterio_de_area(org=org_b)
    areas_del_tenant.responsables_de("soporte_tecnico", org=org_a)
    assert set(_tenants(dos_empresas)) == {"empresa-b", "empresa-a"}
    assert _tenants(dos_empresas)[0] == "empresa-b"


@pytest.mark.django_db
def test_las_puertas_del_supervisor_miran_la_empresa_de_su_organizacion(
        empresa_del_motor, org_a, org_b, monkeypatch):
    from campo import cierre_por_el_supervisor
    from operaciones import ordenes_de_despacho

    monkeypatch.setenv("MOTOR_TENANT", "empresa-a")
    empresa_del_motor(org_a, "empresa-a")
    for puertas in (cierre_por_el_supervisor.puertas, ordenes_de_despacho._puertas):
        assert "sin empresa en el motor" in puertas(org_b)
        assert "sin empresa en el motor" not in puertas(org_a)


@pytest.mark.django_db
def test_el_documento_de_b_va_al_corpus_de_b(dos_empresas, org_a, org_b, monkeypatch):
    """Un documento de la empresa B, en el corpus de A, lo leeria el asistente
    de A y se lo contaria a sus clientes."""
    from common import tasks

    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "empresa-a")
    assert tasks._motor(org_b.id) == ("http://motor:5000", "empresa-b")
    tasks.retirar_documento_del_asistente("doc-del-corpus", str(org_b.id))
    assert _tenants(dos_empresas) == ["empresa-b"]


@pytest.mark.django_db
def test_sin_empresa_el_documento_no_va_a_ningun_corpus(sin_empresa, org_a, monkeypatch):
    from common import tasks

    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "la-del-servidor")
    assert tasks._motor(org_a.id) == ("http://motor:5000", "")
    tasks.retirar_documento_del_asistente("doc-del-corpus", str(org_a.id))
    assert sin_empresa == []


@pytest.mark.django_db
def test_la_purga_aplica_la_retencion_de_cada_empresa_una_vez(
        empresa_del_motor, salidas, org_a, org_b, monkeypatch):
    """Antes purgaba solo la empresa de la variable: la retencion de una
    segunda no se aplicaba nunca. Dos organizaciones de la misma empresa no
    la purgan dos veces, y una sin empresa no purga nada."""
    from common.models import Org
    from common.tasks import purgar_retencion_asistente

    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "empresa-a")
    gemela = Org.objects.create(name="Otra sede de A")
    Org.objects.create(name="Sin empresa")
    empresa_del_motor(org_a, "empresa-a")
    empresa_del_motor(gemela, "empresa-a")
    empresa_del_motor(org_b, "empresa-b")
    purgar_retencion_asistente()
    rutas = sorted(url for url, _ in salidas)
    assert rutas == ["http://motor:5000/mantenimiento/empresa-a/purgar",
                     "http://motor:5000/mantenimiento/empresa-b/purgar"]


@pytest.mark.django_db
def test_la_encuesta_de_un_caso_de_b_sale_de_la_empresa_b(dos_empresas, org_b, monkeypatch):
    """La encuesta sale por el WhatsApp de la empresa: con la variable de antes,
    el cliente de B la recibia desde el numero de A."""
    from cases.models import Case
    from cases.tasks import enviar_encuesta_whatsapp
    from conftest import set_rls_context

    monkeypatch.setenv("ASISTENTE_URL", "http://motor:5000")
    monkeypatch.setenv("ASISTENTE_TENANT", "empresa-a")
    set_rls_context(org_b)
    caso = Case.objects.create(org=org_b, name="Sin internet", status="Closed",
                               priority="Normal")
    enviar_encuesta_whatsapp(str(caso.id), str(org_b.id))
    assert _tenants(dos_empresas) == ["empresa-b"]


# --- el buzon de las solicitudes ------------------------------------------

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


@pytest.mark.django_db
def test_la_solicitud_de_cada_empresa_llega_a_su_buzon(org_a, org_b, mailoutbox):
    """La cadena entera hasta el correo: la solicitud de la empresa A sale al
    buzon de A, y la de B -- sin buzon configurado -- no sale a ninguno."""
    from solicitudes.entrega import _enviar_correo

    org_a.correo_solicitudes = "ventas@empresa-a.co"
    org_a.save(update_fields=["correo_solicitudes"])

    _enviar_correo(_solicitud(org_a, "a" * 64))
    assert [m.to for m in mailoutbox] == [["ventas@empresa-a.co"]]
    with pytest.raises(RuntimeError, match="correo_solicitudes"):
        _enviar_correo(_solicitud(org_b, "b" * 64))
    assert len(mailoutbox) == 1, "la de la empresa sin buzon no sale a ningun otro"
