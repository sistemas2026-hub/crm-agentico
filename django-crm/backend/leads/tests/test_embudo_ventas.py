"""El embudo de ventas, contra Postgres de verdad (12/11/2026).

Se siembra una organizacion con una solicitud en cada etapa -- sin abrir,
abierta sin enviar, enviada, aprobada e instalada, aprobada con la orden
abierta, aprobada sin ticket, cancelada, sin factibilidad, vencida y una de
fuera del periodo -- y OTRA organizacion con tickets de los MISMOS numeros y
ordenes cerradas. Si cualquier consulta del embudo se olvida de la
organizacion, la otra empresa le "instala" una solicitud a esta y los
conteos de abajo dejan de cerrar.

    pytest leads/tests/test_embudo_ventas.py
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from cases.models import EXTERNAL_AUTHOR_HUMAN, Case
from common.models import Profile
from conftest import rls_org
from leads.models import Lead
from solicitudes.models import SolicitudServicio as S

pytestmark = pytest.mark.django_db

URL = "/api/leads/embudo/"
AHORA = timezone.now()


def _sol(org, n, estado=S.NUEVA, hace_dias=3, lead=None, **campos):
    with rls_org(org):
        campos.setdefault("expira_en", AHORA + timedelta(days=5))
        s = S.objects.create(org=org, lead=lead, token_hash=f"{org.id.hex[:8]}{n:056d}",
                             estado=estado,
                             nombre=f"Prospecto{n}", plan_interesado="Fibra 100",
                             **campos)
        S.objects.filter(pk=s.pk).update(created_at=AHORA - timedelta(days=hace_dias))
        s.refresh_from_db()
    return s


def _caso(org, autor, ticket):
    with rls_org(org):
        return Case.objects.create(
            name=f"Ticket {ticket}", status="New", priority="Normal", org=org,
            created_by=autor, provider="wisphub", external_ticket_id=ticket,
            external_service_id="1", external_status="Nuevo",
            external_created_by_type=EXTERNAL_AUTHOR_HUMAN)


def _version(org):
    with rls_org(org):
        wt = WorkType.objects.create(org=org, codigo="ftth", nombre="FTTH")
        return WorkTypeVersion.objects.create(work_type=wt, version=1,
                                              estado=WorkTypeVersion.PUBLICADA,
                                              esquema={"campos": []})


def _orden(org, version, numero, caso, cerrada=False):
    with rls_org(org):
        return OrdenTrabajo.objects.create(
            org=org, numero=numero, tipo_trabajo_version=version,
            origen_sistema="crm", origen_tipo="case", origen_ref=str(caso.id),
            estado_operativo=OrdenTrabajo.CERRADA if cerrada else OrdenTrabajo.ASIGNADA,
            cerrada_en=(AHORA - timedelta(hours=10)) if cerrada else None,
            cliente_nombre="X", cliente_direccion="Calle 1")


@pytest.fixture
def sembrado(org_a, org_b, admin_user, user_b):
    h = lambda d: AHORA - timedelta(days=d)                      # noqa: E731
    s = {}
    s["sin_abrir"] = _sol(org_a, 1)
    s["abierta"] = _sol(org_a, 2, abierta_en=h(2))
    s["enviada"] = _sol(org_a, 3, S.ENVIADA, abierta_en=h(2.9), enviada_en=h(2.5))
    s["instalada"] = _sol(org_a, 4, S.APROBADA, abierta_en=h(2.9), enviada_en=h(2.5),
                          revisada_en=h(2), ticket_wisphub="7004")
    s["orden_abierta"] = _sol(org_a, 5, S.APROBADA, abierta_en=h(2.9), enviada_en=h(2.5),
                              revisada_en=h(2), ticket_wisphub="7005")
    s["sin_ticket"] = _sol(org_a, 6, S.APROBADA, abierta_en=h(2.9), enviada_en=h(2.5),
                           revisada_en=h(2))
    s["cancelada"] = _sol(org_a, 7, S.CANCELADA, abierta_en=h(2.9), enviada_en=h(2.5),
                          cancelada_en=h(1), motivo_cancelacion="Le parecio caro")
    s["sin_fact"] = _sol(org_a, 8, S.SIN_FACTIBILIDAD, abierta_en=h(2.9),
                         enviada_en=h(2.5), revisada_en=h(1.5),
                         nota_revision="No hay caja NAP cerca")
    s["vencida"] = _sol(org_a, 9, expira_en=h(1))
    s["vieja"] = _sol(org_a, 10, S.APROBADA, hace_dias=60, enviada_en=h(59),
                      revisada_en=h(58))

    va = _version(org_a)
    _orden(org_a, va, 1, _caso(org_a, admin_user, "7004"), cerrada=True)
    _orden(org_a, va, 2, _caso(org_a, admin_user, "7005"), cerrada=False)

    # La otra empresa: los mismos numeros de ticket, con su orden CERRADA. Si
    # el embudo une sin la organizacion, la 7005 de org_a sale "instalada".
    vb = _version(org_b)
    _sol(org_b, 1, S.APROBADA, enviada_en=h(2), revisada_en=h(1), ticket_wisphub="7005")
    _sol(org_b, 2, S.ENVIADA, enviada_en=h(2))
    _orden(org_b, vb, 1, _caso(org_b, user_b, "7005"), cerrada=True)
    _orden(org_b, vb, 2, _caso(org_b, user_b, "7004"), cerrada=True)
    return s


def test_cada_etapa_cuenta_lo_suyo_y_nada_de_la_otra_empresa(admin_client, sembrado):
    r = admin_client.get(URL, {"dias": 30})
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["conteos"] == {"chats": None, "links": 9, "abiertos": 7, "enviadas": 6,
                            "aprobadas": 3, "instaladas": 1, "activas": None}
    # Las dos que no se pueden medir llegan con su porque, no como cero.
    assert set(d["sin_dato"]) == {"chats", "activas"}
    # La aprobada sin ticket no se cuenta ni como instalada ni como no: "no se sabe".
    assert d["instalacion_sin_dato"] == 1


def test_las_tasas_las_calcula_el_backend(admin_client, sembrado):
    pasos = {(p["de"], p["a"]): p["tasa"] for p in admin_client.get(URL).json()["pasos"]}
    assert pasos[("links", "abiertos")] == round(7 / 9, 4)
    assert pasos[("enviadas", "aprobadas")] == 0.5
    assert pasos[("aprobadas", "instaladas")] == round(1 / 3, 4)


def test_las_medianas_salen_en_horas_con_sus_muestras(admin_client, sembrado):
    t = {(x["de"], x["a"]): x for x in admin_client.get(URL).json()["tiempos"]}
    # enviada -> decision: cuatro aprobadas/sin factibilidad... tres aprobadas a
    # 12 h y una sin factibilidad a 24 h: la mediana es 12.
    assert t[("enviadas", "decision")] == {"de": "enviadas", "a": "decision",
                                           "horas": 12.0, "muestras": 4}
    # aprobada -> instalada: revisada hace 48 h, orden cerrada hace 10 h.
    assert t[("aprobadas", "instaladas")]["horas"] == 38.0
    assert t[("aprobadas", "instaladas")]["muestras"] == 1


def test_las_caidas_y_las_detenidas(admin_client, sembrado):
    d = admin_client.get(URL).json()
    c = d["caidas"]
    assert c["link_vencido_sin_enviar"] == 1
    assert c["canceladas"]["total"] == 1
    assert [m["texto"] for m in c["canceladas"]["motivos"]] == ["Le parecio caro"]
    assert [m["texto"] for m in c["sin_factibilidad"]["notas"]] == ["No hay caja NAP cerca"]

    det = d["detenidas"]
    assert det["sin_abrir"]["total"] == 1
    assert det["abierto_sin_enviar"]["total"] == 1
    assert det["esperando_decision"]["total"] == 1
    motivos = {f["solicitud_id"]: f["motivo"] for f in det["aprobada_sin_instalar"]["filas"]}
    assert motivos == {str(sembrado["orden_abierta"].id): "orden_abierta",
                       str(sembrado["sin_ticket"].id): "sin_ticket"}
    # Ni telefono ni documento en la lista: solo lo que hace falta para actuar.
    fila = det["abierto_sin_enviar"]["filas"][0]
    assert "telefono" not in fila and "numero_documento" not in fila


def test_la_otra_empresa_ve_solo_lo_suyo(org_b_client, sembrado):
    d = org_b_client.get(URL).json()
    assert d["conteos"]["links"] == 2
    assert d["conteos"]["aprobadas"] == 1
    assert d["conteos"]["instaladas"] == 1


def test_un_usuario_sin_rol_de_gestion_no_ve_el_embudo(user_client, sembrado):
    assert user_client.get(URL).status_code == 403


def test_un_supervisor_si_lo_ve(user_client, user_profile, sembrado):
    Profile.objects.filter(pk=user_profile.pk).update(role="SUPERVISOR")
    assert user_client.get(URL).status_code == 200


def test_sin_sesion_no_hay_embudo(unauthenticated_client):
    assert unauthenticated_client.get(URL).status_code in (401, 403)


@pytest.mark.parametrize("params", [{"dias": 15}, {"dias": "x"}, {"desde": "2026-01-01"},
                                    {"desde": "2026-02-01", "hasta": "2026-01-01"},
                                    {"desde": "2024-01-01", "hasta": "2026-01-01"},
                                    {"desde": "ayer", "hasta": "2026-01-01"}])
def test_un_periodo_que_no_se_entiende_se_rechaza(admin_client, params):
    assert admin_client.get(URL, params).status_code == 400


def test_el_rango_incluye_el_ultimo_dia(admin_client, sembrado):
    hoy = timezone.localdate()
    d = admin_client.get(URL, {"desde": (hoy - timedelta(days=90)).isoformat(),
                              "hasta": hoy.isoformat()}).json()
    assert d["conteos"]["links"] == 10                 # ahora entra la de hace 60 dias


# --- la ficha del prospecto --------------------------------------------------

def _lead(org, **kw):
    with rls_org(org):
        return Lead.objects.create(title="Solicitud Fibra 100 - Centro", org=org, **kw)


def test_la_ficha_del_prospecto_trae_su_solicitud_y_su_instalacion(
        admin_client, org_a, admin_user):
    lead = _lead(org_a)
    s = _sol(org_a, 20, S.APROBADA, lead=lead, enviada_en=AHORA, revisada_en=AHORA,
             ticket_wisphub="7020")
    caso = _caso(org_a, admin_user, "7020")
    _orden(org_a, _version(org_a), 9, caso, cerrada=True)
    r = admin_client.get(f"/api/leads/{lead.id}/solicitud/")
    assert r.status_code == 200, r.content
    [fila] = r.json()["solicitudes"]
    assert fila["id"] == str(s.id) and fila["estado"] == "aprobada"
    assert fila["caso_id"] == str(caso.id) and fila["instalada_en"]


def test_la_ficha_de_otro_no_se_lee(user_client, org_a):
    lead = _lead(org_a)
    assert user_client.get(f"/api/leads/{lead.id}/solicitud/").status_code == 403


def test_la_ficha_de_otra_empresa_no_existe(org_b_client, org_a):
    lead = _lead(org_a)
    assert org_b_client.get(f"/api/leads/{lead.id}/solicitud/").status_code == 404
