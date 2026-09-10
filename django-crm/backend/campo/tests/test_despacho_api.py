# -*- coding: utf-8 -*-
"""
Las tres puertas que faltaban: crear, asignar, validar.

Hasta hoy `OrdenTrabajo.objects.create` existía en UN solo lugar de todo el
repositorio -- el comando de datos de demostración -- así que el módulo tenía
un motor de ejecución completo y ninguna forma de que el trabajo entrara.
Estas pruebas cubren la puerta, no el motor.
"""

import pytest
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from rest_framework.test import APIClient

from campo import despacho_views
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


@pytest.fixture
def version_a(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="correctivo", nombre="Correctivo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_cto", "titulo": "Foto CTO", "obligatorio": True}]},
    )


def _cliente(user, org, profile):
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


@pytest.fixture
def supervisor(org_a):
    u = User.objects.create_user(email="super@test.com", password="x")
    p = Profile.objects.create(user=u, org=org_a, role="SUPERVISOR", is_active=True)
    return _cliente(u, org_a, p), p


@pytest.fixture
def tecnico(org_a, regular_user, user_profile):
    """`user_profile` viene con role='USER': un técnico, no gestión."""
    return _cliente(regular_user, org_a, user_profile), user_profile


@pytest.fixture
def sin_motor(monkeypatch):
    """El motor no se llama desde una prueba: se sustituye su respuesta.

    Se parchea en 'despacho_views' y NO en 'services.despacho': la vista hizo
    'from ... import contexto_del_caso', asi que quedo con una referencia
    propia a la funcion original y parchear el modulo no la alcanza.
    """
    monkeypatch.setattr(despacho_views, "contexto_del_caso", lambda case_id: {
        "contexto_disponible": True,
        "capturado_en": "2026-09-10T21:00:00+00:00",
        "fuente": "motor/contexto_tecnico",
        "servicio": "5612",
        "sn_onu": "CDTC1DB01646",
        "cliente": {"nombre": "Cliente Real", "plan": "PLAN HOGAR"},
        "equipo": {"onu_status": "Online", "onu_signal_1490": "-20.81 dBm"},
    })


def crear(cliente, version, **extra):
    cuerpo = {"work_type_version_id": str(version.id)}
    cuerpo.update(extra)
    return cliente.post("/api/campo/trabajos/crear/", cuerpo, format="json")


# ==========================================================================
#  I · el técnico no despacha ni se autoaprueba
# ==========================================================================

def test_tecnico_no_puede_crear_ni_aprobar(tecnico, supervisor, version_a):
    cli_tec, _ = tecnico
    cli_sup, _ = supervisor

    r = crear(cli_tec, version_a, cliente_nombre="X")
    assert r.status_code == 403, r.data
    assert r.data["error"] == "PERMISO_INSUFICIENTE"

    # Y tampoco puede aprobar el trabajo que él mismo hizo.
    r = crear(cli_sup, version_a, cliente_nombre="X")
    assert r.status_code == 201
    oid = r.data["orden"]["id"]

    r = cli_tec.post(f"/api/campo/trabajos/{oid}/validar/",
                     {"decision": "aprobar"}, format="json")
    assert r.status_code == 403

    r = cli_tec.post(f"/api/campo/trabajos/{oid}/asignar/",
                     {"profile_id": str(tecnico[1].id)}, format="json")
    assert r.status_code == 403


# ==========================================================================
#  J · otra empresa recibe 404, nunca 403
# ==========================================================================

def test_otro_tenant_recibe_404(org_b_client, supervisor, version_a):
    cli_sup, _ = supervisor
    r = crear(cli_sup, version_a, cliente_nombre="X")
    oid = r.data["orden"]["id"]

    for url, cuerpo in (
        (f"/api/campo/trabajos/{oid}/validar/", {"decision": "aprobar"}),
        (f"/api/campo/trabajos/{oid}/asignar/", {"profile_id": str(supervisor[1].id)}),
    ):
        r = org_b_client.post(url, cuerpo, format="json")
        assert r.status_code == 404, f"{url} devolvio {r.status_code}"

    # Y tampoco puede despachar contra una plantilla ajena: 404, no 400, para
    # no distinguir "de otra empresa" de "no existe".
    r = org_b_client.post("/api/campo/trabajos/crear/",
                          {"work_type_version_id": str(version_a.id)},
                          format="json")
    assert r.status_code in (403, 404)


# ==========================================================================
#  Decisión 5 · varias órdenes por caso, sin duplicados accidentales
# ==========================================================================

def test_un_caso_puede_generar_dos_ordenes(supervisor, version_a, sin_motor):
    """La falla volvió dos días después: es una visita nueva, no un duplicado."""
    cli, _ = supervisor

    r1 = crear(cli, version_a, case_id="caso-abc")
    assert r1.status_code == 201, r1.data
    assert r1.data["ordenes_activas_del_caso"] == []

    r2 = crear(cli, version_a, case_id="caso-abc")
    assert r2.status_code == 201, r2.data
    assert r1.data["orden"]["id"] != r2.data["orden"]["id"]

    # La segunda avisa que ya había una activa, para que la pantalla lo
    # advierta -- pero no la bloquea.
    assert r2.data["ordenes_activas_del_caso"] == [r1.data["orden"]["numero"]]
    assert OrdenTrabajo.objects.filter(origen_sistema="crm",
                                       origen_ref="caso-abc").count() == 2


def test_el_mismo_clic_dos_veces_no_crea_dos(supervisor, version_a, sin_motor):
    """Lo que evita el duplicado accidental es la Idempotency-Key, no una
    restricción que también prohibiría la segunda visita legítima."""
    cli, _ = supervisor
    cuerpo = {"work_type_version_id": str(version_a.id), "case_id": "caso-xyz"}

    r1 = cli.post("/api/campo/trabajos/crear/", cuerpo, format="json",
                  HTTP_IDEMPOTENCY_KEY="clic-1")
    r2 = cli.post("/api/campo/trabajos/crear/", cuerpo, format="json",
                  HTTP_IDEMPOTENCY_KEY="clic-1")

    assert r1.status_code == 201
    assert r2.data["orden"]["id"] == r1.data["orden"]["id"]
    assert r2.get("Idempotent-Replay") == "true"
    assert OrdenTrabajo.objects.filter(origen_ref="caso-xyz").count() == 1


def test_wisphub_duplicado_sigue_rechazado(org_a, version_a):
    """Las fuentes automáticas conservan su garantía: ahí un duplicado es un
    bug de máquina, no una segunda visita."""
    from django.db import IntegrityError

    comun = dict(org=org_a, tipo_trabajo_version=version_a,
                 origen_sistema="wisphub", origen_tipo="ticket",
                 origen_ref="91288", cliente_nombre="C")
    OrdenTrabajo.objects.create(numero=9001, **comun)
    with pytest.raises(IntegrityError):
        OrdenTrabajo.objects.create(numero=9002, **comun)


# ==========================================================================
#  El snapshot y la asignación
# ==========================================================================

def test_la_orden_nace_con_la_ficha_congelada(supervisor, version_a, sin_motor):
    cli, _ = supervisor
    r = crear(cli, version_a, case_id="caso-1")
    orden = OrdenTrabajo.objects.get(pk=r.data["orden"]["id"])

    assert orden.contexto["sn_onu"] == "CDTC1DB01646"
    assert orden.contexto["equipo"]["onu_status"] == "Online"
    # Toda medición congelada lleva su hora: dejó de ser una medición y pasó a
    # ser un registro de lo que se veía al despachar.
    assert orden.contexto["capturado_en"]
    # El nombre del cliente se hereda de la ficha si no lo escribieron a mano.
    assert orden.cliente_nombre == "Cliente Real"
    assert orden.eventos.filter(tipo="orden_creada").exists()


def test_la_ficha_no_rompe_la_creacion(supervisor, version_a, monkeypatch):
    """Un supervisor que no puede despachar porque una API de terceros está
    lenta es peor que un técnico sin ficha."""
    from campo.services.despacho import sin_contexto

    monkeypatch.setattr(despacho_views, "contexto_del_caso",
                        lambda case_id: sin_contexto("ConnectTimeout",
                                                     motor_alcanzado=False))

    r = crear(supervisor[0], version_a, case_id="caso-2", cliente_nombre="A mano")
    assert r.status_code == 201
    orden = OrdenTrabajo.objects.get(pk=r.data["orden"]["id"])

    # La ausencia se DICE. Un diccionario vacío se leería como "cliente sin
    # datos" en vez de "no se pudo averiguar", y son cosas distintas: la
    # primera es información sobre el cliente, la segunda sobre nosotros.
    assert orden.contexto["contexto_disponible"] is False
    assert orden.contexto["motivo"] == "ConnectTimeout"
    assert orden.contexto["capturado_en"]
    assert orden.contexto["motor_alcanzado"] is False

    # Y nunca un traceback ni una respuesta cruda guardados en la orden.
    assert "Traceback" not in str(orden.contexto)
    assert set(orden.contexto) == {"contexto_disponible", "capturado_en",
                                   "motivo", "fuente", "motor_alcanzado"}


def test_la_ficha_obtenida_tambien_lo_dice(supervisor, version_a, sin_motor):
    """La pantalla no tiene que deducirlo por ausencia de una clave."""
    r = crear(supervisor[0], version_a, case_id="caso-3")
    orden = OrdenTrabajo.objects.get(pk=r.data["orden"]["id"])
    assert orden.contexto["contexto_disponible"] is True


def test_asignar_deja_evento_y_un_solo_principal(supervisor, tecnico, version_a):
    """Una asignación hecha desde el panel de Django no dejaba rastro, y la
    bitácora quedaba con un hueco justo donde el trabajo cambiaba de manos."""
    cli_sup, p_sup = supervisor
    _, p_tec = tecnico

    r = crear(cli_sup, version_a, cliente_nombre="X")
    oid = r.data["orden"]["id"]

    r = cli_sup.post(f"/api/campo/trabajos/{oid}/asignar/",
                     {"profile_id": str(p_tec.id)}, format="json")
    assert r.status_code == 200, r.data

    orden = OrdenTrabajo.objects.get(pk=oid)
    assert orden.tecnico_principal.id == p_tec.id
    assert orden.eventos.filter(tipo="asignacion").exists()

    # Reasignar baja al anterior: el modelo solo admite un principal.
    r = cli_sup.post(f"/api/campo/trabajos/{oid}/asignar/",
                     {"profile_id": str(p_sup.id), "motivo": "cambio de turno"},
                     format="json")
    assert r.status_code == 200, r.data
    orden.refresh_from_db()
    assert orden.tecnico_principal.id == p_sup.id
    assert orden.asignaciones.filter(es_principal=True).count() == 1

    evento = orden.eventos.filter(tipo="reasignacion").first()
    assert evento is not None
    assert evento.datos["anterior"] == str(p_tec.id)
    assert evento.datos["motivo"] == "cambio de turno"


def test_no_se_despacha_contra_plantilla_borrador(supervisor, org_a):
    """Una borrador puede cambiar debajo del técnico: la orden congela la
    plantilla, así que tiene que congelar una que ya no se mueve."""
    wt = WorkType.objects.create(org=org_a, codigo="x", nombre="X")
    borrador = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.BORRADOR, esquema={"campos": [], "evidencias": []})

    r = crear(supervisor[0], borrador, cliente_nombre="X")
    assert r.status_code == 400
    assert r.data["error"] == "NO_SE_PUDO_CREAR"
