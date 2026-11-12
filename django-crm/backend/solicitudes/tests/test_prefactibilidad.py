"""Pre-factibilidad automatica (12/11/2026).

Apagada no aprueba nada; encendida y con cobertura aprueba sola con autor
Dexter y la misma reasignacion del ticket; sin cobertura o con GPS dudoso deja
el motivo. Y la cadena entera: el formulario publico enviado -> ticket creado
-> aprobada sola -> ticket reasignado -> Lead 'converted' -> bandeja.
"""

from __future__ import annotations

import io

import pytest
import requests

from campo.cuadrillas import Cuadrilla
from campo.zonas import AliasDeZona, ZonaOperativa
from leads.models import Lead
from solicitudes import prefactibilidad
from solicitudes.models import AjustesDeInstalacion, SolicitudServicio
from solicitudes.tests.comun import Respuesta, cliente_de, persona, solicitud
from solicitudes.tests.test_rechazo_y_reintento import MotorFalso


@pytest.fixture
def motor(monkeypatch, empresa_del_motor, org_a):
    m = MotorFalso()
    base_post = m.post

    def post(url, **k):
        #  Crear el ticket devuelve su numero, como el motor real.
        if url.endswith("/crear_ticket_instalacion"):
            m.efectos.append(("crear_ticket_instalacion", k.get("json")))
            return Respuesta({"resultado": {"id": "95200"}})
        return base_post(url, **k)

    monkeypatch.setattr(requests, "post", post)
    empresa_del_motor(org_a, "empresa_prueba")
    return m


@pytest.fixture
def cubierta(org_a):
    """El barrio CENTRO en la zona Norte, que cubre la cuadrilla A de instalacion."""
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=zona, localidad="CENTRO")
    cuadrilla = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla A",
                                         labor_habitual="instalacion")
    cuadrilla.zonas_habituales.add(zona)
    return zona


def _encender(org, **extra):
    AjustesDeInstalacion.objects.update_or_create(
        org=org, defaults={"prefactibilidad_activa": True, **extra})


def _clara(org, **extra):
    datos = dict(ticket_wisphub="95201", gps_lat="10.9", gps_lng="-74.8",
                 gps_precision_m="35", barrio="centro")
    datos.update(extra)
    return solicitud(org, **datos)


def test_apagada_no_aprueba(org_a, motor, cubierta):
    AjustesDeInstalacion.objects.create(org=org_a)          # existe, apagada
    s = _clara(org_a)

    assert prefactibilidad.aplicar(s) == ""

    s.refresh_from_db()
    assert s.estado == SolicitudServicio.ENVIADA
    assert motor.efectos == []


def test_sin_ajuste_no_aprueba(org_a, motor, cubierta):
    s = _clara(org_a)
    prefactibilidad.aplicar(s)
    s.refresh_from_db()
    assert s.estado == SolicitudServicio.ENVIADA


def test_encendida_y_cubierta_aprueba_sola(org_a, motor, cubierta):
    _encender(org_a)
    s = _clara(org_a)

    prefactibilidad.aplicar(s)

    s.refresh_from_db()
    assert s.estado == SolicitudServicio.APROBADA
    assert s.decision_automatica is True
    assert s.revisada_por is None
    assert "zona Norte" in s.prefactibilidad_motivo
    assert "Cuadrilla A" in s.prefactibilidad_motivo
    assert [e[0] for e in motor.efectos] == ["reasignar_ticket_instalacion"]
    assert "Dexter (pre-factibilidad)" in motor.efectos[0][1]["descripcion"]
    assert s.ticket_reasignado_en is not None


def test_fuera_de_zona_queda_con_el_motivo(org_a, motor, cubierta):
    _encender(org_a)
    s = _clara(org_a, barrio="Otro Barrio")

    prefactibilidad.aplicar(s)

    s.refresh_from_db()
    assert s.estado == SolicitudServicio.ENVIADA
    assert "fuera de zona" in s.prefactibilidad_motivo
    assert motor.efectos == []


def test_gps_dudoso_queda_con_el_motivo(org_a, motor, cubierta):
    _encender(org_a, precision_gps_maxima_m=200)
    s = _clara(org_a, gps_precision_m="850")

    prefactibilidad.aplicar(s)

    s.refresh_from_db()
    assert s.estado == SolicitudServicio.ENVIADA
    assert s.prefactibilidad_motivo == "GPS dudoso (±850 m)"


def test_zona_sin_cuadrilla_de_instalacion(org_a, motor):
    zona = ZonaOperativa.objects.create(org=org_a, nombre="Sur")
    AliasDeZona.objects.create(org=org_a, zona=zona, localidad="CENTRO")
    otra = Cuadrilla.objects.create(org=org_a, nombre="Correctivos", labor_habitual="correctivo")
    otra.zonas_habituales.add(zona)
    _encender(org_a)
    s = _clara(org_a)

    prefactibilidad.aplicar(s)

    s.refresh_from_db()
    assert s.estado == SolicitudServicio.ENVIADA
    assert "no tiene cuadrilla de instalacion" in s.prefactibilidad_motivo


def test_la_bandeja_muestra_las_aprobadas_por_dexter(org_a, motor, cubierta):
    _encender(org_a)
    prefactibilidad.aplicar(_clara(org_a))
    solicitud(org_a, estado=SolicitudServicio.APROBADA)      # una de una persona

    jefe = cliente_de(persona(org_a, rol="ADMIN"))
    filas = jefe.get("/api/solicitudes/bandeja/?estado=aprobada&automatica=1").json()["solicitudes"]

    assert len(filas) == 1
    assert filas[0]["revisada_por"] == "Dexter (pre-factibilidad)"
    assert "zona Norte" in filas[0]["prefactibilidad_motivo"]


# --- la cadena entera, desde el formulario publico ------------------------------

def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_el_formulario_enviado_se_aprueba_solo_y_mueve_el_prospecto(org_a, motor, cubierta):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from rest_framework.test import APIClient

    from common.portal_tokens import register_portal_token
    from solicitudes.tokens import hash_token, nuevo_token, vencimiento

    _encender(org_a)
    lead = Lead.objects.create(org=org_a, title="Solicitud", phone="573001234567",
                               status="assigned")
    crudo = nuevo_token()
    s = SolicitudServicio.objects.create(org=org_a, lead=lead, token_hash=hash_token(crudo),
                                         expira_en=vencimiento(), telefono="573001234567")
    register_portal_token(crudo, org_a.id, "solicitud", s.id)

    archivo = lambda n: SimpleUploadedFile(f"{n}.png", _png(), content_type="image/png")  # noqa: E731
    r = APIClient().post(f"/api/public/solicitud/{crudo}/", {
        "nombre": "Ana", "apellido": "Prueba", "telefono": "573001234567",
        "numero_documento": "123", "direccion": "Calle 1", "barrio": "Centro",
        "gps_lat": "10.9", "gps_lng": "-74.8", "gps_precision_m": "20",
        "autoriza_habeas_data": "true",
        "foto_cedula": archivo("c"), "foto_recibo": archivo("r"),
        "foto_solicitante": archivo("s"), "firma": archivo("f"),
    }, format="multipart")

    assert r.status_code == 201, r.content
    s.refresh_from_db()
    assert s.ticket_wisphub == "95200"
    assert s.estado == SolicitudServicio.APROBADA
    assert s.decision_automatica is True
    assert "reasignar_ticket_instalacion" in [e[0] for e in motor.efectos]
    lead.refresh_from_db()
    assert lead.status == "converted"
