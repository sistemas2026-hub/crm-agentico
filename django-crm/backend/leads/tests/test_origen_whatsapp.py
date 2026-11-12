"""El prospecto que registra el asistente nace con origen WhatsApp (12/11/2026).

Atraviesa el endpoint real que llama el motor (`POST /api/solicitudes/`), no
la señal suelta: lo que importa es con que origen queda el Lead en la base.

    pytest leads/tests/test_origen_whatsapp.py
"""
import pytest

from common.utils import LEAD_SOURCE
from leads.models import Lead

pytestmark = pytest.mark.django_db

URL = "/api/solicitudes/"


def _crear(client, **extra):
    r = client.post(URL, {"title": "Solicitud Fibra 100 - Centro", "phone": "573001112233",
                          **extra}, format="json")
    assert r.status_code == 201, r.content
    return Lead.objects.get(pk=r.json()["lead_id"])


def test_whatsapp_es_un_origen_del_catalogo():
    assert dict(LEAD_SOURCE)["whatsapp"] == "WhatsApp"


def test_sin_origen_nace_whatsapp(admin_client):
    assert _crear(admin_client).source == "whatsapp"


def test_el_other_que_manda_la_config_de_hoy_tambien_nace_whatsapp(admin_client):
    # La config del tenant mapea whatsapp -> other porque el catalogo no tenia
    # el valor (tenants/*.config.yaml, registrar_solicitud_servicio). No se toca.
    assert _crear(admin_client, source="other").source == "whatsapp"


def test_un_origen_concreto_se_respeta(admin_client):
    assert _crear(admin_client, source="partner").source == "partner"


def test_un_lead_creado_a_mano_no_cambia(admin_client, org_a):
    lead = Lead.objects.create(title="A mano", org=org_a, source="other")
    lead.refresh_from_db()
    assert lead.source == "other"
