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
"""
import base64
import io
from datetime import datetime, timezone

import pytest

from campo.contrato import ConfiguracionDeContrato, ContratoDeServicio
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
    assert b["autorizaciones"]["habeas_data"] is True
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
