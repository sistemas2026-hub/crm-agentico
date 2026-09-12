# -*- coding: utf-8 -*-
"""Pruebas estrictas de aislamiento multi-tenant y matriz de permisos de cuadrilla (Regla 404 estricta)."""

import pytest
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from rest_framework.test import APIClient

from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


@pytest.fixture
def version_ftth_a(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH A")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []},
    )


@pytest.fixture
def orden_org_a(org_a, user_profile, version_ftth_a):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=4001,
        tipo_trabajo_version=version_ftth_a,
        cliente_nombre="Cliente Empresa A",
        cliente_direccion="Calle 100 # 20-30",
        estado_operativo=OrdenTrabajo.ASIGNADA,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=orden,
        profile=user_profile,
        rol="tecnico_lider",
        es_principal=True,
    )
    return orden


@pytest.fixture
def tecnico_ajeno_org_a(org_a):
    """Segundo técnico en Org A pero NO asignado a la orden_org_a."""
    user = User.objects.create_user(email="tecnico.pedro@test.com", password="password123")
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    client = APIClient()
    token = OrgAwareRefreshToken.for_user_and_org(user, org_a, profile)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client, profile


def test_aislamiento_cross_tenant_estricto_404(org_b_client, orden_org_a):
    """Cualquier acceso de Org B a un recurso de Org A debe devolver 404 (nunca 403 ni revelar existencia)."""
    endpoints = [
        ("get", f"/api/campo/trabajos/{orden_org_a.id}/", {}),
        ("post", f"/api/campo/trabajos/{orden_org_a.id}/acciones/", {"accion": "marcar_en_camino"}),
        ("patch", f"/api/campo/trabajos/{orden_org_a.id}/datos/", {"revision_base": 1, "valores": {}}),
        (
            "post",
            f"/api/campo/trabajos/{orden_org_a.id}/evidencias/",
            {
                "requisito_id": "foto_ont",
                "nombre": "f.jpg",
                "mime_type": "image/jpeg",
                "bytes": 100,
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
        ),
        ("post", f"/api/campo/trabajos/{orden_org_a.id}/completar/", {}),
    ]

    for method, url, payload in endpoints:
        headers = {"HTTP_IDEMPOTENCY_KEY": f"key-cross-{url}"} if method in ["post", "patch"] else {}
        client_fn = getattr(org_b_client, method)
        if method == "get":
            res = client_fn(url)
        else:
            res = client_fn(url, payload, format="json", **headers)

        assert res.status_code == 404, f"Fallo en endpoint {url}: retornó {res.status_code} en lugar de 404"


def test_listado_trabajos_solo_retorna_tenant_propio(org_b_client, user_client, orden_org_a):
    """Org B no ve las órdenes de Org A en el listado /api/campo/trabajos/."""
    res_b = org_b_client.get("/api/campo/trabajos/")
    assert res_b.status_code == 200
    assert len(res_b.json()["results"]) == 0

    res_a = user_client.get("/api/campo/trabajos/")
    assert res_a.status_code == 200
    ids_a = [o["id"] for o in res_a.json()["results"]]
    assert str(orden_org_a.id) in ids_a


def test_tecnico_no_asignado_mismo_tenant_retorna_404(tecnico_ajeno_org_a, admin_client, orden_org_a):
    """Un técnico del mismo tenant que no esté asignado a la orden recibe 404 para no fisgonear órdenes ajenas."""
    tecnico_client, _ = tecnico_ajeno_org_a

    # El técnico no asignado recibe 404
    res_tecnico = tecnico_client.get(f"/api/campo/trabajos/{orden_org_a.id}/")
    assert res_tecnico.status_code == 404

    # Pero el Administrador/Supervisor de su misma organización SÍ puede verla
    res_admin = admin_client.get(f"/api/campo/trabajos/{orden_org_a.id}/")
    assert res_admin.status_code == 200
    assert res_admin.json()["id"] == str(orden_org_a.id)
