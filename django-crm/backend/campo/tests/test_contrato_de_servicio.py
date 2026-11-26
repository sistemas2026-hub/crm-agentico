# -*- coding: utf-8 -*-
"""El contrato del cliente, firmado desde la app (13/11/2026).

  A  EL BORRADOR -- los datos salen de la solicitud del cliente, encontrada
     por su ticket del ISP; sin solicitud, de la orden. Una cancelada o de
     otra empresa no sirve.
  B  FIRMAR -- el contrato queda con su PDF y su huella, una sola vez por
     orden, y lo que el tecnico corrigio gana sobre la solicitud.
  C  LO QUE SE RECHAZA -- sin firma, sin servidor, sin documento.
  D  QUIEN -- otra empresa y otro tecnico ven 404, nunca el contrato.
  E  LA CONFIGURACION -- servidores, NIT y condiciones, solo gestion.

Y el formato de instalacion (25/11/2026), al final del archivo:

  F  LOS DATOS llegan escritos como los escribe la empresa.
  G  EL PLAN se reconoce contra los que la empresa vende; el SERVIDOR se elige
     entre los de ese plan.
  H  UN CONTRATO SE ANULA y la orden firma otro.
  I  LAS COORDENADAS -- mandan las del ticket; donde se firmo se guarda aparte.
"""
import base64
import io
from datetime import datetime, timezone

import pytest

from campo.contrato import ConfiguracionDeContrato, ContratoDeServicio
from campo.contrato import _ip_automatica as _IP_REAL   # antes de que el conftest la tape
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

SERVIDORES = [{"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1"},
              {"id_zona": 20061, "nombre": "CORTE 30 - SERVIDOR 2"}]


def _firma_png() -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 300), "white")
    ImageDraw.Draw(img).line([(40, 200), (200, 80), (380, 220), (560, 90)],
                             fill="black", width=4)
    b = io.BytesIO()
    img.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


@pytest.fixture
def version_instalacion(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="instalacion_fibra",
                                 nombre="Instalación de fibra", labor="instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})


@pytest.fixture
def orden(org_a, user_profile, version_instalacion):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=301, tipo_trabajo_version=version_instalacion,
        cliente_nombre="LAURA GOMEZ", cliente_direccion="Cra 21 # 45-12",
        cliente_telefono="3000000000",
        origen_sistema="wisphub", origen_tipo="ticket", origen_ref="#91288",
        estado_operativo=OrdenTrabajo.ASIGNADA, revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico_lider", es_principal=True)
    return o


def _solicitud(org, ticket="91288", **extra):
    from solicitudes.models import SolicitudServicio

    base = dict(
        org=org, token_hash=f"h-{ticket}-{org.id}-{len(extra)}",
        nombre="Laura", apellido="Gómez Ríos", tipo_documento="CC",
        numero_documento="1043000000", telefono="3000000000",
        correo="laura@ejemplo.co", direccion="Cra 21 # 45-12",
        barrio="Villa Estadio", plan_interesado="Fibra 300 Mb",
        gps_lat="10.9108", gps_lng="-74.8186", gps_precision_m="6",
        autoriza_habeas_data=True, autoriza_centrales_riesgo=True,
        estado=SolicitudServicio.APROBADA, ticket_wisphub=ticket,
        enviada_en=datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc),
        expira_en=datetime(2026, 12, 10, 15, 0, tzinfo=timezone.utc))
    base.update(extra)
    return SolicitudServicio.objects.create(**base)


@pytest.fixture
def config(org_a):
    return ConfiguracionDeContrato.objects.create(
        org=org_a, nit="900.000.000-0", servidores=SERVIDORES,
        texto_condiciones="Primera. El servicio se presta...\nSegunda. Permanencia...")


def _url(orden):
    return f"/api/campo/trabajos/{orden.id}/contrato/"


def _cuerpo(**extra):
    c = {"plan": "Fibra 300 Mb", "id_zona": 20053, "firma_png_base64": _firma_png(),
         "gps": {"lat": 10.91081, "lng": -74.81862, "precision_m": 7}}
    c.update(extra)
    return c


# =========================================================================== #
#  A. EL BORRADOR
# =========================================================================== #
def test_a1_los_datos_salen_de_la_solicitud_del_cliente(user_client, orden, config, org_a):
    _solicitud(org_a)
    r = user_client.get(_url(orden))
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["contrato"] is None
    b = d["borrador"]
    assert b["origen"] == "solicitud"
    assert b["cliente"]["nombre"] == "Laura"
    assert b["cliente"]["numero_documento"] == "1043000000"
    assert b["plan"] == "Fibra 300 Mb"
    assert b["autorizaciones"] is None, \
        "las casillas de habeas data ya no van a la pantalla (el usuario, 25/11/2026)"
    assert b["cliente"]["tipo_documento"] == "" and b["tipo_documento"] == "CC", \
        "el «CC» no se dibuja delante del número; el tipo viaja aparte"
    assert d["servidores"] == SERVIDORES, "el técnico elige entre los servidores"
    assert d["condiciones_cargadas"] is True


def test_a2_sin_solicitud_sale_de_la_orden(user_client, orden, config):
    b = user_client.get(_url(orden)).json()["borrador"]
    assert b["origen"] == "orden"
    assert b["cliente"]["nombre"] == "LAURA GOMEZ"
    assert b["cliente"]["numero_documento"] == "", "no se inventa un documento"
    assert b["autorizaciones"] is None


def test_a3_una_solicitud_CANCELADA_no_sirve(user_client, orden, config, org_a):
    from solicitudes.models import SolicitudServicio
    _solicitud(org_a, estado=SolicitudServicio.CANCELADA)
    assert user_client.get(_url(orden)).json()["borrador"]["origen"] == "orden"


def test_a4_la_solicitud_de_OTRA_EMPRESA_con_el_mismo_ticket_no_sirve(
        user_client, orden, config, org_b):
    _solicitud(org_b)
    assert user_client.get(_url(orden)).json()["borrador"]["origen"] == "orden"


def test_a5_la_app_sabe_la_labor_para_ofrecer_el_contrato(user_client, orden):
    tipo = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()["tipo"]
    assert tipo["labor"] == "instalacion"


# =========================================================================== #
#  B. FIRMAR
# =========================================================================== #
def test_b1_firmar_deja_el_contrato_con_su_pdf_y_su_huella(user_client, orden, config, org_a):
    s = _solicitud(org_a)
    r = user_client.post(_url(orden), _cuerpo(), format="json")
    assert r.status_code == 201, r.content
    c = r.json()["contrato"]
    assert c["numero"].endswith("-000301")
    assert c["estado"] == "firmado", "el alta en WispHub es la fase 2"
    assert c["servidor"] == {"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1"}
    assert len(c["huella"]) == 64 and c["tiene_pdf"] is True

    fila = ContratoDeServicio.objects.get(orden=orden)
    assert fila.solicitud_id == s.id
    with fila.pdf.open("rb") as f:
        pdf = f.read()
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000

    #  Después de firmar, la pantalla muestra el contrato y no el borrador.
    d = user_client.get(_url(orden)).json()
    assert d["contrato"]["id"] == c["id"] and d["borrador"] is None


def test_b2_UNA_SOLA_VEZ_por_orden(user_client, orden, config, org_a):
    _solicitud(org_a)
    uno = user_client.post(_url(orden), _cuerpo(), format="json")
    dos = user_client.post(_url(orden), _cuerpo(), format="json")
    assert uno.status_code == 201 and dos.status_code == 200
    assert uno.json()["contrato"]["id"] == dos.json()["contrato"]["id"]
    assert ContratoDeServicio.objects.filter(orden=orden).count() == 1


def test_b3_LO_QUE_CORRIGE_EL_TECNICO_gana_sobre_la_solicitud(user_client, orden, config, org_a):
    #  El técnico tiene la cédula delante: si la solicitud la trae mal, manda él.
    _solicitud(org_a)
    r = user_client.post(_url(orden), _cuerpo(cliente={"numero_documento": "1043000001"}),
                         format="json")
    assert r.json()["contrato"]["cliente"]["numero_documento"] == "1043000001"
    assert r.json()["contrato"]["cliente"]["nombre"] == "Laura", "lo no tocado sigue igual"


def test_b4_cambiar_un_dato_cambia_la_huella(org_a, user_profile, version_instalacion, config):
    from campo.contrato import firmar

    def _orden(n):
        return OrdenTrabajo.objects.create(
            org=org_a, numero=n, tipo_trabajo_version=version_instalacion,
            cliente_nombre="X", cliente_direccion="Calle 1",
            estado_operativo=OrdenTrabajo.ASIGNADA, revision=1)

    a, _ = firmar(_orden(1), user_profile, _cuerpo(cliente={"numero_documento": "1"}))
    b, _ = firmar(_orden(2), user_profile, _cuerpo(cliente={"numero_documento": "2"}))
    assert a.huella != b.huella


# =========================================================================== #
#  C. LO QUE SE RECHAZA
# =========================================================================== #
@pytest.mark.parametrize("extra,palabra", [
    ({"firma_png_base64": ""}, "firma"),
    ({"firma_png_base64": base64.b64encode(b"no soy un png").decode()}, "firma"),
    ({"id_zona": 99999}, "servidor"),
    ({"plan": ""}, "plan"),
])
def test_c1_sin_lo_minimo_no_hay_contrato(user_client, orden, config, org_a, extra, palabra):
    _solicitud(org_a, plan_interesado="")
    r = user_client.post(_url(orden), _cuerpo(**extra), format="json")
    assert r.status_code == 400, r.content
    assert palabra in r.json()["detail"].lower()
    assert not ContratoDeServicio.objects.filter(orden=orden).exists()


def test_c2_sin_documento_no_hay_contrato(user_client, orden, config):
    r = user_client.post(_url(orden), _cuerpo(), format="json")   # sin solicitud
    assert r.status_code == 400
    assert "documento" in r.json()["detail"]


def test_c3_sin_servidores_cargados_lo_dice(user_client, orden, org_a):
    _solicitud(org_a)
    r = user_client.post(_url(orden), _cuerpo(), format="json")
    assert r.status_code == 400
    assert "no cargó sus servidores" in r.json()["detail"]


def test_c4_un_gps_cero_cero_no_se_guarda(user_client, orden, config, org_a):
    _solicitud(org_a, gps_lat="", gps_lng="")
    user_client.post(_url(orden), _cuerpo(gps={"lat": 0, "lng": 0}), format="json")
    assert ContratoDeServicio.objects.get(orden=orden).datos["gps"] is None


# =========================================================================== #
#  D. QUIEN
# =========================================================================== #
def test_d1_OTRA_EMPRESA_ve_404(org_b_client, orden, config):
    assert org_b_client.get(_url(orden)).status_code == 404
    assert org_b_client.post(_url(orden), _cuerpo(), format="json").status_code == 404


def test_d2_el_PDF_lo_abre_su_tecnico_y_no_otra_empresa(user_client, org_b_client,
                                                       orden, config, org_a):
    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    r = user_client.get(f"/api/campo/contratos/{cid}/pdf/")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert b"".join(r.streaming_content).startswith(b"%PDF")
    assert org_b_client.get(f"/api/campo/contratos/{cid}/pdf/").status_code == 404


def test_d3_un_tecnico_NO_ASIGNADO_ve_404(orden, config, org_a):
    from common.models import Profile, User
    from common.serializer import OrgAwareRefreshToken
    from rest_framework.test import APIClient

    u = User.objects.create_user(email="otro.tecnico@test.com", password="x")
    p = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    cli = APIClient()
    cli.credentials(HTTP_AUTHORIZATION="Bearer "
                    f"{OrgAwareRefreshToken.for_user_and_org(u, org_a, p).access_token}")
    assert cli.get(_url(orden)).status_code == 404


# =========================================================================== #
#  E. LA CONFIGURACION
# =========================================================================== #
URL_CONFIG = "/api/campo/contrato/configuracion/"


def test_e1_gestion_carga_servidores_nit_y_condiciones(admin_client):
    r = admin_client.put(URL_CONFIG, {"nit": " 900.1 ", "servidores": SERVIDORES,
                                      "texto_condiciones": "Primera..."}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["nit"] == "900.1"
    assert admin_client.get(URL_CONFIG).json()["servidores"] == SERVIDORES


@pytest.mark.parametrize("servidores", [
    [{"id_zona": True, "nombre": "X"}],              # un bool es int en Python
    [{"id_zona": -1, "nombre": "X"}],
    [{"id_zona": 1, "nombre": ""}],
    [{"id_zona": 1, "nombre": "A"}, {"id_zona": 1, "nombre": "B"}],
    "no soy una lista",
])
def test_e2_un_servidor_malo_se_rechaza(admin_client, servidores):
    assert admin_client.put(URL_CONFIG, {"servidores": servidores},
                            format="json").status_code == 400


def test_e3_quien_no_gestiona_no_la_toca(user_client):
    assert user_client.put(URL_CONFIG, {"nit": "x"},
                           format="json").status_code in (403, 404)


# =========================================================================== #
#  LA IP QUE ELIGIO EL TECNICO  --  14/11/2026
#
#  Queda en los datos FIRMADOS porque es parte de lo que se decidio en la casa,
#  y de ahi la lee el alta cuando se construya. Se valida la FORMA, no que este
#  libre: comprobarlo exige preguntarle al motor, y si el motor no contesta el
#  tecnico no podria firmar por un problema de red que no es suyo. Firmar no
#  crea el cliente en el ISP.
# =========================================================================== #
#: Lo que `firmar` exige y el borrador de esta orden no trae: esta orden no
#: tiene solicitud, asi que el documento lo manda el telefono.
_CLIENTE_IP = {"nombre": "Laura", "apellido": "Gomez",
               "numero_documento": "1043000000", "tipo_documento": "CC",
               "direccion": "Cra 21 # 45-12", "telefono": "3000000000",
               "correo": "", "barrio": "Villa Estadio"}


def test_ip_la_que_eligio_queda_en_los_datos_firmados(user_client, orden, config):
    r = user_client.post(_url(orden), _cuerpo(cliente=_CLIENTE_IP, ip="172.16.9.37"), format="json")

    assert r.status_code in (200, 201), r.content
    assert ContratoDeServicio.objects.get(orden=orden).datos["ip_elegida"] == "172.16.9.37"


def test_ip_sin_elegir_ninguna_se_firma_igual(user_client, orden, config):
    """Una empresa sin pools declarados tiene que poder firmar."""
    r = user_client.post(_url(orden), _cuerpo(cliente=_CLIENTE_IP), format="json")

    assert r.status_code in (200, 201), r.content
    assert ContratoDeServicio.objects.get(orden=orden).datos["ip_elegida"] == ""


@pytest.mark.parametrize("mala,trozo", [
    ("no-es-una-ip", "válida"),
    ("172.16.9", "válida"),
    ("999.1.1.1", "válida"),
    ("::1", "IPv4"),
    ("172.16.9.0", "red o el broadcast"),
    ("172.16.9.255", "red o el broadcast"),
    ("172.16.9.1", "puerta de enlace"),
])
def test_ip_una_direccion_que_no_puede_ser_se_rechaza(user_client, orden, config,
                                                      mala, trozo):
    r = user_client.post(_url(orden), _cuerpo(cliente=_CLIENTE_IP, ip=mala), format="json")

    assert r.status_code == 400, r.content
    assert trozo in r.json().get("detail", "")
    assert not ContratoDeServicio.objects.filter(orden=orden).exists(),         "y NO queda un contrato a medias"


def test_ip_el_punto_uno_se_rechaza_aunque_el_rango_este_vacio(user_client, orden, config):
    """EL CONTROL de la medicion del 14/11: el .1 estaba libre en 83 de 86
    pools, uno de ellos con 240 de 254 ocupadas. Es la puerta de enlace, y eso
    no depende de que el rango tenga clientes."""
    r = user_client.post(_url(orden), _cuerpo(cliente=_CLIENTE_IP, ip="10.9.9.1"), format="json")

    assert r.status_code == 400, r.content


# =========================================================================== #
#  EL FORMATO DE INSTALACION  --  25/11/2026
#
#  Lo que sigue atraviesa la API: lo que el telefono pide y manda, y lo que
#  queda en la base. Las reglas solas estan en test_contrato_formato_y_plan.py.
#
#    F  LOS DATOS LLEGAN ESCRITOS COMO LOS ESCRIBE LA EMPRESA, y lo que el
#       tecnico corrige queda igual.
#    G  EL PLAN se reconoce contra los que la empresa vende, y el SERVIDOR se
#       elige entre los de ese plan.
#    H  UN CONTRATO SE ANULA y la orden firma otro.
#    I  LAS COORDENADAS: mandan las del ticket.
# =========================================================================== #
CATALOGO = [
    {"nombre": "PLAN FAMILIA", "zonas": [20053, 20049]},
    {"nombre": "PLAN HOGAR", "zonas": [20053, 20049]},
    {"nombre": "PLAN FIBRA OPTICA 200MB SV", "zonas": [32278]},
]
TRES_SERVIDORES = [{"id_zona": 20053, "nombre": "CORTE 15 - SERVIDOR 1"},
                   {"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1"},
                   {"id_zona": 32278, "nombre": "SERVIDOR SABANAGRANDE"}]


@pytest.fixture
def con_catalogo(monkeypatch):
    """La empresa vende esos planes (lo que contestaria el motor)."""
    from campo import contrato_plan

    monkeypatch.setattr(contrato_plan, "catalogo_de", lambda org: list(CATALOGO))


@pytest.fixture
def config_rapida(org_a):
    """La empresa con sus tres costumbres encendidas y sus tres servidores."""
    return ConfiguracionDeContrato.objects.create(
        org=org_a, nit="900.000.000-0", servidores=TRES_SERVIDORES,
        texto_condiciones="Primera...", datos_en_mayusculas=True,
        barrio_en_la_direccion=True, digitos_del_telefono=10)


def _solicitud_del_formulario(org, **extra):
    """Como la llena una persona: minusculas, puntos en la cedula, indicativo."""
    base = dict(nombre="laura marcela", apellido="Pineda Ortega",
                numero_documento="1.234.500.001", telefono="+57 300 555 0101",
                correo="Laura.Pineda@Example.com", direccion="Cra 3B # 54-20",
                barrio="Villa del Sol", plan_interesado="FAMILIA 200MB - $89.900",
                fecha_corte="CORTE 30")
    base.update(extra)
    return _solicitud(org, **base)


# --------------------------------------------------------------------------- #
#  F. EL FORMATO
# --------------------------------------------------------------------------- #
def test_f1_el_borrador_llega_ESCRITO_como_lo_escribe_la_empresa(
        user_client, orden, config_rapida, org_a):
    _solicitud_del_formulario(org_a)
    c = user_client.get(_url(orden)).json()["borrador"]["cliente"]
    assert c["nombre"] == "LAURA MARCELA" and c["apellido"] == "PINEDA ORTEGA"
    assert c["numero_documento"] == "1234500001", "sin puntos y sin CC"
    assert c["telefono"] == "3005550101", "los 10 dígitos, sin indicativo"
    assert c["correo"] == "laura.pineda@example.com"
    assert c["direccion"] == "CRA 3B # 54-20 VILLA DEL SOL", "con el barrio pegado"
    assert c["barrio"] == "VILLA DEL SOL", "y el barrio, además, solo"


def test_f2_SIN_las_costumbres_cargadas_no_se_le_impone_ese_formato(
        user_client, orden, config, org_a):
    """EL CONTROL de f1: otra empresa (la config de siempre, sin costumbres)
    recibe los datos con su escritura. Si f1 pasara por un formato fijo en el
    código, esta fallaría."""
    _solicitud_del_formulario(org_a)
    c = user_client.get(_url(orden)).json()["borrador"]["cliente"]
    assert c["nombre"] == "laura marcela"
    assert c["direccion"] == "Cra 3B # 54-20" and c["barrio"] == "Villa del Sol"
    assert c["telefono"] == "573005550101", "sin saber cuántos dígitos, no se recorta"
    assert c["numero_documento"] == "1234500001", "esto no varía por empresa"


def test_f3_LO_QUE_EL_TECNICO_CORRIGE_queda_con_el_mismo_formato(
        user_client, orden, config_rapida, org_a):
    """El técnico corrige el nombre con la cédula delante, y lo teclea como
    sale: en minúsculas y con puntos. Al contrato entra como todo lo demás."""
    _solicitud_del_formulario(org_a)
    borrador = user_client.get(_url(orden)).json()["borrador"]["cliente"]
    corregido = {**borrador, "nombre": "laura marcéla", "numero_documento": "1.234.500.009"}
    r = user_client.post(_url(orden), _cuerpo(cliente=corregido, plan="PLAN FAMILIA"),
                         format="json")
    assert r.status_code == 201, r.content
    c = ContratoDeServicio.objects.get(orden=orden).datos["cliente"]
    assert c["nombre"] == "LAURA MARCÉLA" and c["numero_documento"] == "1234500009"
    assert c["direccion"] == "CRA 3B # 54-20 VILLA DEL SOL", "el barrio no se pega dos veces"


def test_f4_si_CORRIGE_EL_BARRIO_la_direccion_no_se_queda_con_el_viejo(
        user_client, orden, config_rapida, org_a):
    _solicitud_del_formulario(org_a)
    borrador = user_client.get(_url(orden)).json()["borrador"]["cliente"]
    r = user_client.post(_url(orden), _cuerpo(cliente={**borrador, "barrio": "las nieves"},
                                              plan="PLAN FAMILIA"), format="json")
    assert r.status_code == 201, r.content
    c = ContratoDeServicio.objects.get(orden=orden).datos["cliente"]
    assert c["barrio"] == "LAS NIEVES"
    assert c["direccion"] == "CRA 3B # 54-20 LAS NIEVES"


@pytest.fixture
def lo_que_se_imprime(monkeypatch):
    """La página de la que sale el PDF, en vez del PDF: el PDF no se puede leer
    acá, y lo que importa es qué dice. El mismo `armar_pdf`, con el motor que
    lo pinta cambiado por uno que guarda lo que le dan."""
    import weasyprint

    vistos = []

    class _Html:
        def __init__(self, string):
            vistos.append(string)

        def write_pdf(self, salida, **kw):
            salida.write(b"%PDF-1.7 " + b"x" * 6000)

    monkeypatch.setattr(weasyprint, "HTML", _Html)
    return vistos


def test_f5_el_PDF_no_imprime_el_barrio_dos_veces_en_la_direccion(
        user_client, orden, config_rapida, org_a, lo_que_se_imprime):
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FAMILIA"), format="json")
    assert r.status_code == 201, r.content
    html = lo_que_se_imprime[0]
    assert "CRA 3B # 54-20 VILLA DEL SOL" in html
    assert "VILLA DEL SOL, VILLA DEL SOL" not in html
    assert "VILLA DEL SOL VILLA DEL SOL" not in html


# --------------------------------------------------------------------------- #
#  G. EL PLAN Y EL SERVIDOR
# --------------------------------------------------------------------------- #
def test_g1_el_plan_del_ticket_llega_con_el_nombre_del_catalogo_y_SUS_servidores(
        user_client, orden, config_rapida, org_a, con_catalogo):
    _solicitud_del_formulario(org_a)        # «FAMILIA 200MB - $89.900», corte 30
    d = user_client.get(_url(orden)).json()
    b = d["borrador"]
    assert b["plan"] == "PLAN FAMILIA" and b["plan_reconocido"] is True
    assert b["plan_del_ticket"] == "FAMILIA 200MB - $89.900", "lo que pidió el cliente, a la vista"
    assert [s["id_zona"] for s in d["servidores"]] == [20049, 20053], \
        "el del corte del ticket PRIMERO (la app lo marca), y los demás del plan " \
        "para poder cambiarlo: «en la parte de corte no deja escoger» (26/11/2026)"
    assert b["servidor_sugerido"] == 20049 and b["corte"] == "CORTE 30"
    assert d["falta_cargar_servidores"] is False
    por_plan = {p["nombre"]: [s["id_zona"] for s in p["servidores"]] for p in d["planes"]}
    assert por_plan == {"PLAN FAMILIA": [20053, 20049], "PLAN HOGAR": [20053, 20049],
                        "PLAN FIBRA OPTICA 200MB SV": [32278]}
    #  El menú de planes de la app: si el técnico cambia de plan, queda
    #  marcado solo el servidor del corte DE ESE PLAN (y ninguno si no lo tiene).
    sugerido = {p["nombre"]: p["servidor_sugerido"] for p in d["planes"]}
    assert sugerido == {"PLAN FAMILIA": 20049, "PLAN HOGAR": 20049,
                        "PLAN FIBRA OPTICA 200MB SV": None}


def test_g2_firmar_guarda_el_NOMBRE_DEL_CATALOGO_y_no_el_texto_del_ticket(
        user_client, orden, config_rapida, org_a, con_catalogo):
    _solicitud_del_formulario(org_a)
    #  La app de hoy devuelve el plan tal como lo recibió o como lo tecleó el técnico.
    r = user_client.post(_url(orden), _cuerpo(plan="familia 200 megas", id_zona=20049),
                         format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["plan"] == "PLAN FAMILIA" and datos["plan_del_catalogo"] is True
    assert datos["servidor"] == {"id_zona": 20049, "nombre": "CORTE 30 - SERVIDOR 1"}


def test_g3_un_servidor_que_NO_ES_DEL_PLAN_se_rechaza(
        user_client, orden, config_rapida, org_a, con_catalogo):
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FAMILIA", id_zona=32278), format="json")
    assert r.status_code == 400, r.content
    detalle = r.json()["detail"]
    assert "no es del plan PLAN FAMILIA" in detalle
    assert "CORTE 15 - SERVIDOR 1" in detalle and "CORTE 30 - SERVIDOR 1" in detalle
    assert not ContratoDeServicio.objects.filter(orden=orden).exists()


def test_g4_un_plan_que_la_empresa_NO_VENDE_se_rechaza_y_dice_cuales_si(
        user_client, orden, config_rapida, org_a, con_catalogo):
    _solicitud_del_formulario(org_a, plan_interesado="Fibra 300 Mb")
    b = user_client.get(_url(orden)).json()["borrador"]
    assert b["plan_reconocido"] is False and b["plan"] == "Fibra 300 Mb"
    r = user_client.post(_url(orden), _cuerpo(plan="Fibra 300 Mb", id_zona=20053), format="json")
    assert r.status_code == 400, r.content
    assert "PLAN FAMILIA" in r.json()["detail"] and "PLAN HOGAR" in r.json()["detail"]
    assert not ContratoDeServicio.objects.filter(orden=orden).exists()


def test_g5_SIN_CATALOGO_se_firma_con_lo_escrito_y_queda_dicho(
        user_client, orden, config_rapida, org_a):
    """El motor no contestó (en pruebas ninguna organización tiene empresa).
    No poder preguntar no deja al técnico sin firmar; el contrato dice que el
    plan no se comprobó."""
    _solicitud_del_formulario(org_a, plan_interesado="Fibra 300 Mb")
    r = user_client.post(_url(orden), _cuerpo(plan="Fibra 300 Mb", id_zona=32278), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["plan"] == "Fibra 300 Mb" and datos["plan_del_catalogo"] is False


def test_g6_un_plan_de_UN_SOLO_servidor_no_hace_elegir(
        user_client, orden, config_rapida, org_a, con_catalogo):
    _solicitud_del_formulario(org_a, plan_interesado="FIBRA OPTICA 200MB SV", fecha_corte="")
    d = user_client.get(_url(orden)).json()
    assert [s["id_zona"] for s in d["servidores"]] == [32278]
    cuerpo = _cuerpo(plan="PLAN FIBRA OPTICA 200MB SV")
    cuerpo.pop("id_zona")
    r = user_client.post(_url(orden), cuerpo, format="json")
    assert r.status_code == 201, r.content
    assert ContratoDeServicio.objects.get(orden=orden).datos["servidor"]["id_zona"] == 32278


def test_g7_si_la_empresa_NO_CARGO_el_servidor_del_plan_no_se_ofrecen_los_otros(
        user_client, orden, org_a, con_catalogo):
    ConfiguracionDeContrato.objects.create(org=org_a, servidores=TRES_SERVIDORES[:2])
    _solicitud_del_formulario(org_a, plan_interesado="FIBRA OPTICA 200MB SV")
    d = user_client.get(_url(orden)).json()
    assert d["servidores"] == [] and d["falta_cargar_servidores"] is True
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FIBRA OPTICA 200MB SV", id_zona=20053),
                         format="json")
    assert r.status_code == 400, r.content
    assert "no cargó en su contrato el servidor del plan" in r.json()["detail"]
    assert not ContratoDeServicio.objects.filter(orden=orden).exists()


def test_g8_SIN_SOLICITUD_el_plan_y_el_corte_salen_de_lo_que_dice_el_ticket(
        user_client, orden, config_rapida, org_a, con_catalogo):
    from cases.models import Case

    orden.caso = Case.objects.create(
        org=org_a, name="Instalacion Nueva", status="New", priority="Normal", is_active=True,
        description="Instalacion Nueva - LAURA GOMEZ | Tel: 3000000000 | Cra 21 # 45-12"
                    " | Plan: HOGAR 100MB - $59.900 | Corte: CORTE 15 | Medio: VECINO")
    orden.save(update_fields=["caso"])
    d = user_client.get(_url(orden)).json()
    assert d["borrador"]["origen"] == "orden"
    assert d["borrador"]["plan"] == "PLAN HOGAR"
    assert d["borrador"]["servidor_sugerido"] == 20053
    assert [s["id_zona"] for s in d["servidores"]] == [20053, 20049]


# --------------------------------------------------------------------------- #
#  H. ANULAR Y FIRMAR OTRO
# --------------------------------------------------------------------------- #
def _anular(cliente, contrato_id, motivo="El plan quedó mal elegido"):
    return cliente.post(f"/api/campo/contratos/{contrato_id}/anular/", {"motivo": motivo},
                        format="json")


def test_h1_un_contrato_se_ANULA_y_la_orden_firma_OTRO(user_client, user_profile,
                                                       orden, config, org_a):
    _solicitud(org_a)
    primero = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]
    assert primero["se_puede_anular"] is True

    r = _anular(user_client, primero["id"])
    assert r.status_code == 200, r.content
    assert r.json()["contrato"]["estado"] == "anulado"

    fila = ContratoDeServicio.objects.get(pk=primero["id"])
    assert fila.estado == "anulado" and fila.anulado_por_id == user_profile.id
    assert fila.anulado_en is not None and fila.motivo_anulacion == "El plan quedó mal elegido"
    assert fila.pdf, "el anulado conserva su PDF: lo firmó un cliente"

    #  La pantalla vuelve al borrador, y dice que hubo uno antes.
    d = user_client.get(_url(orden)).json()
    assert d["contrato"] is None and d["borrador"] is not None and d["anulados"] == 1

    #  Y se firma otro: es un contrato NUEVO, con otro número.
    segundo = user_client.post(_url(orden), _cuerpo(), format="json")
    assert segundo.status_code == 201, segundo.content
    nuevo = segundo.json()["contrato"]
    assert nuevo["id"] != primero["id"] and nuevo["estado"] == "firmado"
    assert nuevo["numero"] == primero["numero"] + "-2", "dos papeles no llevan el mismo número"
    assert ContratoDeServicio.objects.filter(orden=orden).count() == 2
    assert user_client.get(_url(orden)).json()["contrato"]["id"] == nuevo["id"]


def test_h2_sin_decir_POR_QUE_no_se_anula(user_client, orden, config, org_a):
    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    for motivo in ("", "   ", "ok"):
        r = _anular(user_client, cid, motivo)
        assert r.status_code == 400, r.content
        assert "por qué" in r.json()["detail"]
    assert ContratoDeServicio.objects.get(pk=cid).estado == "firmado"


def test_h3_uno_que_YA_ESTA_EN_EL_ISP_no_se_anula_desde_aca(user_client, orden, config, org_a):
    """Anularlo solo en la plataforma dejaría al cliente creado en el proveedor
    y la orden lista para crearlo otra vez."""
    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    ContratoDeServicio.objects.filter(pk=cid).update(estado="en_el_isp", servicio_isp="12345")

    assert user_client.get(_url(orden)).json()["contrato"]["se_puede_anular"] is False
    r = _anular(user_client, cid)
    assert r.status_code == 409, r.content
    assert "proveedor" in r.json()["detail"]
    fila = ContratoDeServicio.objects.get(pk=cid)
    assert fila.estado == "en_el_isp" and fila.anulado_en is None
    #  Y la orden NO puede firmar otro: sigue teniendo uno vigente.
    otra_vez = user_client.post(_url(orden), _cuerpo(), format="json")
    assert otra_vez.status_code == 200 and otra_vez.json()["contrato"]["id"] == cid


def test_h4_OTRA_EMPRESA_no_anula_el_contrato(user_client, org_b_client, orden, config, org_a):
    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    assert _anular(org_b_client, cid).status_code == 404
    assert ContratoDeServicio.objects.get(pk=cid).estado == "firmado"


def test_h4b_un_tecnico_de_la_MISMA_empresa_que_NO_TIENE_la_orden_tampoco(
        user_client, orden, config, org_a):
    from common.models import Profile, User
    from common.serializer import OrgAwareRefreshToken
    from rest_framework.test import APIClient

    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    u = User.objects.create_user(email="otro.tecnico@test.com", password="x")
    p = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    ajeno = APIClient()
    ajeno.credentials(HTTP_AUTHORIZATION="Bearer "
                      f"{OrgAwareRefreshToken.for_user_and_org(u, org_a, p).access_token}")
    assert _anular(ajeno, cid).status_code == 404
    assert ContratoDeServicio.objects.get(pk=cid).estado == "firmado"


def test_h4c_un_cuerpo_que_no_es_un_objeto_no_rompe_y_no_anula(user_client, orden, config, org_a):
    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    r = user_client.post(f"/api/campo/contratos/{cid}/anular/", ["El plan quedó mal"], format="json")
    assert r.status_code == 400, r.content
    assert ContratoDeServicio.objects.get(pk=cid).estado == "firmado"


def test_h5_anular_dos_veces_no_cambia_ni_quien_ni_cuando(user_client, admin_client,
                                                         orden, config, org_a):
    _solicitud(org_a)
    cid = user_client.post(_url(orden), _cuerpo(), format="json").json()["contrato"]["id"]
    assert _anular(user_client, cid, "Primer motivo válido").status_code == 200
    antes = ContratoDeServicio.objects.get(pk=cid)
    assert _anular(admin_client, cid, "Otro motivo distinto").status_code == 200
    despues = ContratoDeServicio.objects.get(pk=cid)
    assert (despues.anulado_en, despues.anulado_por_id, despues.motivo_anulacion) == \
           (antes.anulado_en, antes.anulado_por_id, "Primer motivo válido")


def test_h6_LA_BASE_no_deja_dos_contratos_vigentes_en_una_orden(orden, user_profile,
                                                                config, org_a):
    """La garantía no es la pregunta previa de firmar: es la restricción. Dos
    vigentes no entran; uno anulado y uno vigente, sí."""
    from django.db import IntegrityError, transaction
    from django.utils import timezone as tz

    def _fila(estado, numero):
        return ContratoDeServicio(org=org_a, orden=orden, numero=numero, datos={},
                                  huella="h" * 64, estado=estado, firmado_por=user_profile,
                                  firmado_en=tz.now())

    _fila("anulado", "C-1").save()
    _fila("anulado", "C-2").save()
    _fila("firmado", "C-3").save()
    for estado in ("firmado", "en_el_isp"):
        with pytest.raises(IntegrityError), transaction.atomic():
            _fila(estado, "C-4").save()
    assert ContratoDeServicio.objects.filter(orden=orden).count() == 3


# --------------------------------------------------------------------------- #
#  I. LAS COORDENADAS
# --------------------------------------------------------------------------- #
def test_i1_MANDAN_LAS_DEL_TICKET_y_las_del_telefono_se_guardan_aparte(
        user_client, orden, config, org_a):
    _solicitud(org_a)                                   # 10.9108, -74.8186
    user_client.post(_url(orden), _cuerpo(), format="json")   # el teléfono: 10.91081, -74.81862
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert (str(datos["gps"]["lat"]), str(datos["gps"]["lng"])) == ("10.9108", "-74.8186")
    assert datos["gps_del_telefono"] == {"lat": 10.91081, "lng": -74.81862, "precision_m": 7}, \
        "dónde se firmó no se pierde"


def test_i2_si_el_ticket_NO_TRAE_coordenadas_quedan_las_del_telefono(
        user_client, orden, config, org_a):
    _solicitud(org_a, gps_lat="", gps_lng="")
    user_client.post(_url(orden), _cuerpo(), format="json")
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["gps"] == {"lat": 10.91081, "lng": -74.81862, "precision_m": 7}


def test_i3_el_papel_no_dice_que_se_firmo_donde_dice_el_ticket(
        user_client, orden, config, org_a, lo_que_se_imprime):
    """Son dos lugares: las coordenadas de la INSTALACIÓN (las del ticket) van
    con los datos del suscriptor; el pie dice dónde se FIRMÓ (el teléfono)."""
    _solicitud(org_a)                                   # ticket: 10.9108, -74.8186 (±6 m)
    user_client.post(_url(orden), _cuerpo(), format="json")   # teléfono: 10.91081, -74.81862 (±7 m)
    html = lo_que_se_imprime[0]
    instalacion, pie = html.split('class="huella"')
    assert "Coordenadas de la instalación" in instalacion
    assert "10.9108, -74.8186 (±6 m)" in instalacion
    assert "en 10.91081, -74.81862 (±7 m)" in pie, "el pie dice dónde se firmó"
    assert "10.9108, -74.8186 (±6 m)" not in pie


# --------------------------------------------------------------------------- #
#  E (sigue). LAS COSTUMBRES DE LA EMPRESA, EN SU CONFIGURACION
# --------------------------------------------------------------------------- #
def test_e4_gestion_carga_como_escribe_su_empresa_y_APAGADAS_por_defecto(admin_client):
    d = admin_client.get(URL_CONFIG).json()
    assert (d["datos_en_mayusculas"], d["barrio_en_la_direccion"],
            d["digitos_del_telefono"]) == (False, False, 0)

    r = admin_client.put(URL_CONFIG, {"datos_en_mayusculas": True,
                                      "barrio_en_la_direccion": True,
                                      "digitos_del_telefono": 10}, format="json")
    assert r.status_code == 200, r.content
    d = admin_client.get(URL_CONFIG).json()
    assert (d["datos_en_mayusculas"], d["barrio_en_la_direccion"],
            d["digitos_del_telefono"]) == (True, True, 10)

    #  Guardar otra cosa no las apaga.
    admin_client.put(URL_CONFIG, {"nit": "900.2"}, format="json")
    assert admin_client.get(URL_CONFIG).json()["datos_en_mayusculas"] is True


# =========================================================================== #
#  J. LO QUE PIDIO EL USUARIO AL PROBAR LA 1.0.20  --  26/11/2026
# =========================================================================== #
def test_j1_LA_IP_LA_ASIGNA_EL_SISTEMA_la_primera_libre_que_no_tenga_otro_contrato(
        user_client, orden, config_rapida, org_a, monkeypatch, user_profile):
    from campo import contrato as C
    from campo.services import ips_libres

    pedidas = []
    monkeypatch.setattr(C, "_ip_automatica", _IP_REAL)
    monkeypatch.setattr(ips_libres, "para_la_zona", lambda org, zona, cuantas: (
        pedidas.append(zona) or {"libres": ["172.16.30.1", "172.16.30.12", "172.16.30.13"]}))
    #  Otro contrato vigente ya eligió la .12.
    from django.utils import timezone as tz
    otra = OrdenTrabajo.objects.create(
        org=org_a, numero=302, tipo_trabajo_version=orden.tipo_trabajo_version,
        cliente_nombre="OTRO", estado_operativo=OrdenTrabajo.ASIGNADA, revision=1)
    ContratoDeServicio.objects.create(org=org_a, orden=otra, numero="C-OTRA", huella="h" * 64,
                                      estado="firmado", firmado_por=user_profile, firmado_en=tz.now(),
                                      datos={"ip_elegida": "172.16.30.12"})
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FAMILIA", id_zona=20053), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert pedidas == [20053], "se le pregunta al motor por el servidor elegido"
    assert datos["ip_elegida"] == "172.16.30.13", "ni la .1 (puerta de enlace) ni la que ya tiene otro"
    assert datos["ip_origen"] == "sistema"


def test_j2_SIN_IP_LIBRE_se_firma_igual_y_la_que_mande_una_app_vieja_se_respeta(
        user_client, orden, config_rapida, org_a, monkeypatch):
    from campo import contrato as C

    monkeypatch.setattr(C, "_ip_automatica", _IP_REAL)
    from campo.services import ips_libres
    monkeypatch.setattr(ips_libres, "para_la_zona",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("motor caido")))
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FAMILIA", id_zona=20053), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["ip_elegida"] == "" and datos["ip_origen"] == "", \
        "sin motor no hay IP, y no hay error: el técnico tiene la firma hecha"


def test_j3_la_IP_de_una_app_vieja_gana_y_no_se_pregunta_al_motor(
        user_client, orden, config_rapida, org_a, monkeypatch):
    from campo import contrato as C

    monkeypatch.setattr(C, "_ip_automatica", lambda *a: pytest.fail("no debía preguntar"))
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FAMILIA", id_zona=20053,
                                              ip="172.16.30.40"), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["ip_elegida"] == "172.16.30.40" and datos["ip_origen"] == "tecnico"


def test_j4_LAS_COORDENADAS_QUE_CORRIGE_EL_TECNICO_ganan_sobre_las_del_ticket(
        user_client, orden, config_rapida, org_a):
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(
        plan="PLAN FAMILIA", coordenadas={"lat": 10.96391, "lng": -74.79642}), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["gps"] == {"lat": 10.96391, "lng": -74.79642}
    assert datos["gps_origen"] == "tecnico"
    assert datos["gps_del_telefono"]["lat"] == 10.91081, "el GPS del teléfono, aparte: dónde se firmó"


@pytest.mark.parametrize("malas", [{"lat": 0, "lng": 0}, {"lat": 200, "lng": 1}, "10,-74", None])
def test_j5_unas_coordenadas_invalidas_no_cuentan_y_vale_lo_de_siempre(
        user_client, orden, config_rapida, org_a, malas):
    _solicitud_del_formulario(org_a)
    r = user_client.post(_url(orden), _cuerpo(plan="PLAN FAMILIA", coordenadas=malas), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["gps_origen"] in ("ticket", "telefono")
    assert datos["gps"] != {"lat": 0, "lng": 0}


def test_g9_SIN_CORTE_en_el_ticket_el_tecnico_elige_entre_los_del_plan(
        user_client, orden, config_rapida, org_a, con_catalogo):
    """EL CONTROL de g1: si el ticket no dice el corte, no se adivina."""
    _solicitud_del_formulario(org_a, fecha_corte="")
    d = user_client.get(_url(orden)).json()
    assert d["borrador"]["servidor_sugerido"] is None
    assert [s["id_zona"] for s in d["servidores"]] == [20053, 20049]


def test_f6_el_contrato_FIRMADO_si_lleva_el_tipo_de_documento_y_las_autorizaciones(
        user_client, orden, config_rapida, org_a):
    """La pantalla los recibe vacíos; el contrato no puede quedar sin ellos."""
    _solicitud_del_formulario(org_a)
    c = user_client.get(_url(orden)).json()["borrador"]["cliente"]
    assert c["tipo_documento"] == ""
    r = user_client.post(_url(orden), _cuerpo(cliente=c, plan="PLAN FAMILIA"), format="json")
    assert r.status_code == 201, r.content
    datos = ContratoDeServicio.objects.get(orden=orden).datos
    assert datos["cliente"]["tipo_documento"] == "CC", "el de la solicitud"
    assert datos["autorizaciones"]["habeas_data"] is True, "las autorizaciones, de la solicitud"


def test_f7_la_direccion_queda_con_las_ABREVIATURAS_de_la_empresa(
        user_client, orden, config_rapida, org_a):
    config_rapida.abreviaturas_de_direccion = [
        {"como_lo_escriben": ["CLL", "CL", "CALL"], "como_queda": "CALLE"},
        {"como_lo_escriben": ["KRA", "KR", "CR", "CARRERA"], "como_queda": "CRA"}]
    config_rapida.save()
    _solicitud_del_formulario(org_a, direccion="cll 48 # 3A-15 kra. 2", barrio="La Carrera")
    c = user_client.get(_url(orden)).json()["borrador"]["cliente"]
    assert c["direccion"] == "CALLE 48 # 3A-15 CRA 2 LA CARRERA", \
        "la calle se corrige; el barrio pegado, no («La Carrera» no es una carrera)"
    r = user_client.post(_url(orden), _cuerpo(cliente=c, plan="PLAN FAMILIA"), format="json")
    assert ContratoDeServicio.objects.get(orden=orden).datos["cliente"]["direccion"] == \
        "CALLE 48 # 3A-15 CRA 2 LA CARRERA", "y firmar no la abrevia dos veces"


@pytest.mark.parametrize("reglas", [
    [{"como_lo_escriben": ["CLL"], "como_queda": ""}],
    [{"como_lo_escriben": [], "como_queda": "CALLE"}],
    [{"como_lo_escriben": ["C L"], "como_queda": "CALLE"}],
    [{"como_lo_escriben": ["CR"], "como_queda": "CRA"}, {"como_lo_escriben": ["cr"], "como_queda": "CALLE"}],
    "no soy una lista",
])
def test_e6_una_regla_de_abreviatura_mal_escrita_se_rechaza(admin_client, reglas):
    assert admin_client.put(URL_CONFIG, {"abreviaturas_de_direccion": reglas},
                            format="json").status_code == 400
    assert admin_client.get(URL_CONFIG).json()["abreviaturas_de_direccion"] == []


@pytest.mark.parametrize("cuerpo", [
    {"datos_en_mayusculas": "false"},          # un texto no vacío es verdadero en Python
    {"barrio_en_la_direccion": 1},
    {"digitos_del_telefono": 16},
    {"digitos_del_telefono": -1},
    {"digitos_del_telefono": True},            # un bool es int en Python
    {"digitos_del_telefono": "10"},
])
def test_e5_una_costumbre_mal_escrita_se_rechaza_y_no_guarda_nada(admin_client, cuerpo):
    assert admin_client.put(URL_CONFIG, cuerpo, format="json").status_code == 400
    d = admin_client.get(URL_CONFIG).json()
    assert (d["datos_en_mayusculas"], d["barrio_en_la_direccion"],
            d["digitos_del_telefono"]) == (False, False, 0)


# =========================================================================== #
#  K. A NOMBRE DE OTRA PERSONA  --  26/11/2026
#
#  El usuario: «cuando el técnico llegue y el contrato se hace a nombre de otra
#  persona, pero los otros datos siguen igual: solo cambiarían el nombre, el
#  apellido y la cédula». Lo que no puede pasar es que el contrato diga que la
#  persona nueva aceptó las autorizaciones de una solicitud que llenó otra.
# =========================================================================== #
URL_BANDEJA = "/api/solicitudes/bandeja/?estado=aprobada"


def _otra_persona(**extra):
    c = {"nombre": "Carlos", "apellido": "Pérez Díaz", "tipo_documento": "Cédula de ciudadanía",
         "numero_documento": "72.111.222"}
    c.update(extra)
    return c


def _a_nombre_de_otro(cliente=None, autorizaciones=None, **extra):
    return _cuerpo(titular="otro", cliente=cliente if cliente is not None else _otra_persona(),
                   autorizaciones=(autorizaciones if autorizaciones is not None
                                   else {"habeas_data": True, "centrales_de_riesgo": False}),
                   **extra)


def test_k1_LA_PANTALLA_sabe_que_elegir_y_que_aceptar_y_con_el_nombre_de_la_empresa(
        user_client, orden, config, org_a):
    _solicitud(org_a)
    o = user_client.get(_url(orden)).json()["otro_titular"]
    assert "Cédula de ciudadanía" in o["tipos_de_documento"]
    habeas, centrales = o["autorizaciones"]
    assert (habeas["id"], habeas["obligatoria"]) == ("habeas_data", True)
    assert (centrales["id"], centrales["obligatoria"]) == ("centrales_de_riesgo", False)
    assert org_a.name in habeas["texto"], "la autoriza A ESTA empresa"


def test_k2_A_NOMBRE_DE_OTRA_PERSONA_cambian_nombre_y_documento_y_lo_demas_sigue_igual(
        user_client, orden, config, org_a):
    s = _solicitud(org_a)
    r = user_client.post(_url(orden), _a_nombre_de_otro(), format="json")
    assert r.status_code == 201, r.content
    c = r.json()["contrato"]
    assert (c["cliente"]["nombre"], c["cliente"]["apellido"]) == ("Carlos", "Pérez Díaz")
    assert c["cliente"]["tipo_documento"] == "Cédula de ciudadanía"
    assert c["cliente"]["numero_documento"].replace(".", "") == "72111222"
    #  Lo demás, de la solicitud.
    assert c["cliente"]["telefono"] == "3000000000"
    assert c["cliente"]["correo"] == "laura@ejemplo.co"
    assert c["cliente"]["direccion"].upper().startswith("CRA 21")
    assert c["otro_titular"] is True and c["documento_cambiado"] is False
    fila = ContratoDeServicio.objects.get(orden=orden)
    assert fila.solicitud_id == s.id, "sigue colgado de la solicitud que pidió el servicio"


def test_k3_LAS_AUTORIZACIONES_son_de_la_persona_nueva_aceptadas_al_firmar(
        user_client, orden, config, org_a):
    _solicitud(org_a)   # aceptó las dos el 10/11
    r = user_client.post(_url(orden), _a_nombre_de_otro(), format="json")
    assert r.status_code == 201, r.content
    aut = ContratoDeServicio.objects.get(orden=orden).datos["autorizaciones"]
    assert aut["habeas_data"] is True
    assert aut["centrales_de_riesgo"] is False, \
        "la persona nueva NO aceptó centrales; que la de la solicitud sí no cuenta"
    assert aut["donde"] == "al_firmar"
    assert not aut["aceptadas_en"].startswith("2026-11-10"), "no la fecha de la solicitud"


@pytest.mark.parametrize("autorizaciones", [
    {}, {"habeas_data": False, "centrales_de_riesgo": True}, {"habeas_data": "true"},
])
def test_k4_SIN_que_la_persona_nueva_autorice_sus_datos_no_se_firma(
        user_client, orden, config, org_a, autorizaciones):
    _solicitud(org_a)
    r = user_client.post(_url(orden), _a_nombre_de_otro(autorizaciones=autorizaciones),
                         format="json")
    assert r.status_code == 400
    assert "habeas data" in r.json()["detail"]
    assert not ContratoDeServicio.objects.filter(orden=orden).exists()


def test_k5_NO_CAE_a_los_datos_de_la_solicitud_lo_que_la_persona_nueva_no_dio(
        user_client, orden, config, org_a):
    _solicitud(org_a)
    #  Sin apellido: queda sin apellido, no con el de Laura.
    r = user_client.post(_url(orden), _a_nombre_de_otro(
        cliente={"nombre": "Carlos", "tipo_documento": "Pasaporte", "numero_documento": "AB123"}),
        format="json")
    assert r.status_code == 201, r.content
    assert r.json()["contrato"]["cliente"]["apellido"] == ""
    #  Sin documento: no se firma con el de Laura.
    ContratoDeServicio.objects.all().delete()
    r = user_client.post(_url(orden), _a_nombre_de_otro(
        cliente={"nombre": "Carlos", "tipo_documento": "Pasaporte"}), format="json")
    assert r.status_code == 400 and "documento" in r.json()["detail"]


def test_k6_un_tipo_de_documento_que_no_es_de_la_lista_se_rechaza(
        user_client, orden, config, org_a):
    _solicitud(org_a)
    r = user_client.post(_url(orden), _a_nombre_de_otro(cliente=_otra_persona(tipo_documento="")),
                         format="json")
    assert r.status_code == 400 and "tipo de documento" in r.json()["detail"]


def test_k7_el_MISMO_documento_de_la_solicitud_no_es_otra_persona(
        user_client, orden, config, org_a):
    _solicitud(org_a)
    r = user_client.post(_url(orden), _a_nombre_de_otro(
        cliente=_otra_persona(numero_documento="1.043.000.000")), format="json")
    assert r.status_code == 400 and "no es otra persona" in r.json()["detail"]


def test_k8_UNA_CEDULA_QUE_CAMBIA_SIN_DECIRLO_se_firma_y_queda_dicho(
        user_client, orden, config, org_a):
    #  Una app vieja, o un número mal escrito en la solicitud: como antes, y la
    #  oficina lo ve.
    _solicitud(org_a)
    r = user_client.post(_url(orden), _cuerpo(cliente={"numero_documento": "1043000001"}),
                         format="json")
    assert r.status_code == 201
    c = r.json()["contrato"]
    assert c["documento_cambiado"] is True and c["otro_titular"] is False
    aut = ContratoDeServicio.objects.get(orden=orden).datos["autorizaciones"]
    assert "donde" not in aut, "las de la solicitud, como antes"
    #  La misma cédula con puntos no es «cambiada».
    ContratoDeServicio.objects.all().delete()
    r = user_client.post(_url(orden), _cuerpo(cliente={"numero_documento": "1.043.000.000"}),
                         format="json")
    assert r.json()["contrato"]["documento_cambiado"] is False


def test_k9_EL_PAPEL_dice_que_no_es_quien_hizo_la_solicitud_y_que_aceptó_al_firmar(
        user_client, orden, config, org_a, lo_que_se_imprime):
    _solicitud(org_a)
    r = user_client.post(_url(orden), _a_nombre_de_otro(), format="json")
    assert r.status_code == 201, r.content
    html = lo_que_se_imprime[0]
    assert "no es quien hizo la solicitud" in html
    assert "aceptadas por el suscriptor al firmar" in html
    assert "aceptadas en la solicitud" not in html
    assert "Pérez Díaz" in html and "Gómez Ríos" not in html, "el apellido de Laura no va"


def test_k10_el_papel_de_SIEMPRE_sigue_diciendo_de_la_solicitud(
        user_client, orden, config, org_a, lo_que_se_imprime):
    _solicitud(org_a)
    assert user_client.post(_url(orden), _cuerpo(), format="json").status_code == 201
    html = lo_que_se_imprime[0]
    assert "aceptadas en la solicitud" in html and "no es quien hizo la solicitud" not in html


def test_k11_LA_OFICINA_ve_a_nombre_de_quien_quedó(user_client, admin_client, orden, config, org_a):
    _solicitud(org_a)
    assert user_client.post(_url(orden), _a_nombre_de_otro(), format="json").status_code == 201
    contrato = admin_client.get(URL_BANDEJA).json()["solicitudes"][0]["contrato"]
    assert contrato["otro_titular"] is True
    assert contrato["titular"]["nombre"] == "Carlos Pérez Díaz"
    assert contrato["titular"]["documento"].startswith("Cédula de ciudadanía 72")


def test_k12_en_un_contrato_NORMAL_la_oficina_no_recibe_otro_titular(
        user_client, admin_client, orden, config, org_a):
    _solicitud(org_a)
    assert user_client.post(_url(orden), _cuerpo(), format="json").status_code == 201
    contrato = admin_client.get(URL_BANDEJA).json()["solicitudes"][0]["contrato"]
    assert contrato["otro_titular"] is False and contrato["titular"] is None


def test_k13_EL_ALTA_en_el_proveedor_sale_con_la_persona_nueva(user_client, orden, config, org_a):
    from campo.services.alta_en_el_isp import datos_del_alta

    _solicitud(org_a)
    assert user_client.post(_url(orden), _a_nombre_de_otro(), format="json").status_code == 201
    d = datos_del_alta(ContratoDeServicio.objects.get(orden=orden))
    assert (d["cliente"]["nombre"], d["cliente"]["apellido"]) == ("Carlos", "Pérez Díaz")
    assert d["cliente"]["documento"].replace(".", "") == "72111222"
    assert d["cliente"]["telefono"] == "3000000000"


def test_k14_SIN_SOLICITUD_tambien_se_puede_y_las_autorizaciones_quedan_por_fin_aceptadas(
        user_client, orden, config):
    r = user_client.post(_url(orden), _a_nombre_de_otro(), format="json")
    assert r.status_code == 201, r.content
    aut = ContratoDeServicio.objects.get(orden=orden).datos["autorizaciones"]
    assert aut["habeas_data"] is True and aut["donde"] == "al_firmar"
