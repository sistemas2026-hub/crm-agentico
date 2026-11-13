# -*- coding: utf-8 -*-
"""
================================================================================
 EL HILO DEL CLIENTE, POR LA API  --  12/11/2026
================================================================================
Las tres lecturas de campo/hilo_del_cliente_views.py, atravesando URL → vista
→ servicio → base (Postgres de verdad con TEST_DATABASE_URL):

  A  el bloque «Campo» del ticket: quien puede abrir el ticket ve sus visitas
     (tecnico, estado, fecha); el enlace a la orden solo si la puede abrir;
     otra empresa 404; quien no puede abrir el ticket, 403
  B  la pagina de la orden: ticket, servicio y cuadrilla; sin telefono ni GPS;
     un tecnico no asignado y otra empresa, 404
  C  la ficha del cliente: tickets que la persona puede abrir, ordenes por el
     abonado o por el ticket, solicitudes solo para la gestion; otra empresa
     no ve nada; un servicio con barras o espacios es 404
  D  «OT-n» viaja con su id en los reportes y con su numero en la historia

    pytest campo/tests/test_hilo_del_cliente_api.py
================================================================================
"""
import datetime as dt
import itertools

import pytest
from django.utils import timezone

from cases.models import Case
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import despacho as D
from conftest import rls_org

pytestmark = pytest.mark.django_db

_n = itertools.count(7000)
SERVICIO = "4986"


def _version(org):
    tipo = WorkType.objects.get_or_create(org=org, codigo="t", defaults={
        "nombre": "Correctivo", "labor": "correctivo"})[0]
    return WorkTypeVersion.objects.get_or_create(
        work_type=tipo, version=1, defaults={
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"campos": [{"id": "x", "tipo": "texto"}]}})[0]


def _caso(org, **kw):
    return Case.objects.create(org=org, name=kw.pop("name", "No tiene internet"),
                               status="New", priority="Normal", **kw)


def _orden(org, caso=None, abonado="", tecnico=None):
    o = D.crear_orden(
        org=org, profile=None, version=_version(org),
        cliente={"nombre": "Ana Cliente", "telefono": "3001112222",
                 "direccion": "Calle 1", "id_abonado": abonado,
                 "gps_lat": 10.4, "gps_lng": -75.5},
        origen_sistema="crm" if caso else "manual",
        origen_tipo="case" if caso else "",
        origen_ref=str(caso.pk) if caso else "",
        programada_para=timezone.now())
    if tecnico is not None:
        AsignacionTrabajo.objects.create(orden=o, profile=tecnico, es_principal=True)
    return o


# ---------------------------------------------------------------------------
# A · el bloque «Campo» del ticket
# ---------------------------------------------------------------------------

def test_a_la_gestion_ve_las_visitas_del_ticket(admin_client, org_a, user_profile):
    caso = _caso(org_a, external_service_id=SERVICIO)
    o = _orden(org_a, caso, tecnico=user_profile)
    _orden(org_a)                                     # otra orden, sin ticket
    r = admin_client.get(f"/api/campo/casos/{caso.pk}/ordenes/")
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["servicio"] == SERVICIO
    assert [x["numero"] for x in d["ordenes"]] == [o.numero]
    fila = d["ordenes"][0]
    assert fila["tecnico"] == (user_profile.user.name or user_profile.user.email)
    assert fila["estado_operativo"] == "asignada" and fila["fecha"]
    assert fila["puede_abrir"] is True
    # Sin datos del cliente en el resumen.
    assert not {"telefono", "cliente", "gps_lat", "direccion"} & set(fila)


def test_a2_quien_abre_el_ticket_ve_la_visita_sin_poder_abrirla(
        user_client, org_a, regular_user, admin_profile):
    caso = _caso(org_a, created_by=regular_user)
    _orden(org_a, caso, tecnico=admin_profile)
    r = user_client.get(f"/api/campo/casos/{caso.pk}/ordenes/")
    assert r.status_code == 200, r.content
    [fila] = r.json()["ordenes"]
    assert fila["puede_abrir"] is False


def test_a3_quien_no_puede_abrir_el_ticket_recibe_403(user_client, org_a, admin_user):
    #  El ticket es de otro, no lo tiene asignado ni es de su area.
    caso = _caso(org_a, created_by=admin_user)
    _orden(org_a, caso)
    r = user_client.get(f"/api/campo/casos/{caso.pk}/ordenes/")
    assert r.status_code == 403


def test_a4_otra_empresa_404(org_b_client, org_a):
    caso = _caso(org_a)
    _orden(org_a, caso)
    r = org_b_client.get(f"/api/campo/casos/{caso.pk}/ordenes/")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# B · la pagina de la orden
# ---------------------------------------------------------------------------

def test_b_el_hilo_de_la_orden_lleva_ticket_y_servicio(admin_client, org_a):
    caso = _caso(org_a, external_service_id=SERVICIO, external_ticket_id="91288",
                 provider="wisphub")
    o = _orden(org_a, caso)
    r = admin_client.get(f"/api/campo/trabajos/{o.pk}/hilo/")
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["caso"]["id"] == str(caso.pk)
    assert d["caso"]["external_ticket_id"] == "91288"
    # La orden no copio el abonado: el servicio sale de su ticket.
    assert d["servicio"] == SERVICIO
    assert d["cliente"] == {"nombre": "Ana Cliente", "direccion": "Calle 1"}
    texto = r.content.decode()
    assert "3001112222" not in texto and "10.4" not in texto


def test_b2_tecnico_no_asignado_y_otra_empresa_404(user_client, org_b_client, org_a):
    o = _orden(org_a)
    assert user_client.get(f"/api/campo/trabajos/{o.pk}/hilo/").status_code == 404
    assert org_b_client.get(f"/api/campo/trabajos/{o.pk}/hilo/").status_code == 404


def test_b3_el_tecnico_asignado_la_ve(user_client, org_a, user_profile):
    o = _orden(org_a, tecnico=user_profile)
    assert user_client.get(f"/api/campo/trabajos/{o.pk}/hilo/").status_code == 200


# ---------------------------------------------------------------------------
# C · la ficha del cliente
# ---------------------------------------------------------------------------

def _solicitud(org, ticket):
    from solicitudes.models import SolicitudServicio

    return SolicitudServicio.objects.create(
        org=org, token_hash=f"h{next(_n)}", expira_en=timezone.now() + dt.timedelta(days=1),
        nombre="Ana", numero_documento="1234567890", ticket_wisphub=ticket,
        estado="enviada")


def test_c_la_ficha_junta_tickets_ordenes_y_solicitudes(admin_client, org_a):
    caso = _caso(org_a, external_service_id=SERVICIO, external_ticket_id="91288",
                 provider="wisphub")
    _caso(org_a, external_service_id="otro")          # de otro cliente
    por_ticket = _orden(org_a, caso)
    por_abonado = _orden(org_a, abonado=SERVICIO)
    _orden(org_a, abonado="otro")
    _solicitud(org_a, "91288")
    _solicitud(org_a, "55555")
    r = admin_client.get(f"/api/campo/clientes/{SERVICIO}/")
    assert r.status_code == 200, r.content
    d = r.json()
    assert [t["id"] for t in d["tickets"]] == [str(caso.pk)]
    assert {x["numero"] for x in d["ordenes"]} == {por_ticket.numero, por_abonado.numero}
    assert [s["ticket_wisphub"] for s in d["solicitudes"]] == ["91288"]
    assert "1234567890" not in r.content.decode()


def test_c2_sin_gestion_no_hay_solicitudes_ni_lo_ajeno(user_client, org_a, regular_user,
                                                        admin_user):
    suyo = _caso(org_a, external_service_id=SERVICIO, created_by=regular_user,
                 external_ticket_id="1", provider="wisphub")
    ajeno = _caso(org_a, external_service_id=SERVICIO, created_by=admin_user,
                  external_ticket_id="2", provider="wisphub")
    _orden(org_a, ajeno)
    _solicitud(org_a, "1")
    d = user_client.get(f"/api/campo/clientes/{SERVICIO}/").json()
    assert [t["id"] for t in d["tickets"]] == [str(suyo.pk)]
    assert d["ordenes"] == []
    assert d["solicitudes"] is None


def test_c3_otra_empresa_no_ve_nada(org_b_client, org_a):
    caso = _caso(org_a, external_service_id=SERVICIO)
    _orden(org_a, caso, abonado=SERVICIO)
    d = org_b_client.get(f"/api/campo/clientes/{SERVICIO}/").json()
    assert d["tickets"] == [] and d["ordenes"] == [] and d["solicitudes"] == []


@pytest.mark.parametrize("malo", ["a b", "x" * 65, "..%2F"])
def test_c4_servicio_invalido_404(admin_client, malo):
    assert admin_client.get(f"/api/campo/clientes/{malo}/").status_code == 404


# ---------------------------------------------------------------------------
# D · «OT-n» viaja con lo que hace falta para enlazarlo
# ---------------------------------------------------------------------------

def test_d_reportes_e_historia_llevan_la_orden(org_a, user_profile):
    from campo.models import MaterialCatalogo, MovimientoDeMaterial, PedidoDeMaterial
    from campo.services.inventario import historia_de
    from campo.services.inventario_operacion import pedidos_a_bodega

    o = _orden(org_a)
    mat = MaterialCatalogo.objects.create(org=org_a, codigo="ONT", nombre="ONT")
    PedidoDeMaterial.objects.create(org=org_a, material=mat, cantidad=1, orden=o,
                                    profile=user_profile)
    [fila] = pedidos_a_bodega(org_a)
    assert fila["orden_id"] == str(o.pk) and fila["orden_numero"] == o.numero

    MovimientoDeMaterial.objects.create(
        org=org_a, material=mat, serie="S1", cantidad=1, orden=o,
        tipo=MovimientoDeMaterial.CONSUMO, profile=user_profile,
        idempotency_key="hilo-d", ocurrido_en=timezone.now())
    [h] = historia_de(org_a, mat, "S1")
    assert h["orden"] == str(o.pk) and h["orden_numero"] == o.numero
