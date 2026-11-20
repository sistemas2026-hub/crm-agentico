# -*- coding: utf-8 -*-
"""Prueba de concurrencia optimista y control de revisión offline (Carlos vs Pedro)."""

import pytest
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


@pytest.fixture
def version_ftth(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_rev", nombre="Instalación Revisión")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={
            "campos": [
                {"id": "potencia_rx", "tipo": "decimal", "reglas": {"required": True, "min": -30.0, "max": -5.0}},
                {"id": "nap", "tipo": "texto", "reglas": {"required": False}},
                {"id": "observaciones", "tipo": "texto", "reglas": {"required": False}},
            ],
            "evidencias": [],
        },
    )


@pytest.fixture
def orden_carlos_y_pedro(org_a, user_profile, version_ftth):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=7001,
        tipo_trabajo_version=version_ftth,
        cliente_nombre="Familia Gómez",
        cliente_direccion="Cra 15 # 80-20",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        revision=4,
        datos={"potencia_rx": -19.0, "nap": "NAP-01"},
    )
    AsignacionTrabajo.objects.create(
        orden=orden,
        profile=user_profile,
        rol="tecnico_lider",
        es_principal=True,
    )
    return orden


def test_conflicto_stale_work_order_mismo_campo(user_client, orden_carlos_y_pedro):
    """
    Carlos y Pedro descargan la orden en revision=4.
    Carlos actualiza potencia_rx -> revision=5 en servidor.
    Pedro, habiendo estado offline, intenta enviar potencia_rx con revision_base=4.
    El backend DEBE rechazar con 409 STALE_WORK_ORDER para evitar pisar silenciosamente el valor.
    """
    url = f"/api/campo/trabajos/{orden_carlos_y_pedro.id}/datos/"

    # 1. Carlos aplica su cambio desde revision_base=4
    res_carlos = user_client.patch(
        url,
        {"revision_base": 4, "valores": {"potencia_rx": -20.5}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-carlos-001",
    )
    assert res_carlos.status_code == 200
    assert res_carlos.json()["revision"] == 5

    # 2. Pedro intenta mandar su cambio offline desde revision_base=4 sobre el MISMO campo
    res_pedro = user_client.patch(
        url,
        {"revision_base": 4, "valores": {"potencia_rx": -23.0}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-pedro-002",
    )
    assert res_pedro.status_code == 409
    data_pedro = res_pedro.json()
    assert data_pedro["error"] == "STALE_WORK_ORDER"
    assert data_pedro["revision_actual"] == 5
    assert "potencia_rx" in data_pedro["detalle"]


def test_merge_exitoso_campos_diferentes_offline(user_client, orden_carlos_y_pedro):
    """
    Carlos y Pedro descargan en revision=4.
    Carlos actualiza potencia_rx -> revision=5.
    Pedro actualiza un campo NO en conflicto (ej. observaciones o nap) con revision_base=4.
    El backend permite el merge no destructivo, incrementa a revision=6 y ambos campos persisten.
    """
    url = f"/api/campo/trabajos/{orden_carlos_y_pedro.id}/datos/"

    # 1. Carlos actualiza potencia_rx
    res_carlos = user_client.patch(
        url,
        {"revision_base": 4, "valores": {"potencia_rx": -20.5}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-merge-carlos",
    )
    assert res_carlos.status_code == 200
    assert res_carlos.json()["revision"] == 5

    # 2. Pedro actualiza observaciones con revision_base=4 (no colisiona con potencia_rx)
    res_pedro = user_client.patch(
        url,
        {"revision_base": 4, "valores": {"observaciones": "Cliente solicita fibra extendida hasta estudio"}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-merge-pedro",
    )
    assert res_pedro.status_code == 200
    assert res_pedro.json()["revision"] == 6

    # 3. Comprobar que en la base de datos se unificaron ambos campos sin pérdida
    orden_carlos_y_pedro.refresh_from_db()
    assert orden_carlos_y_pedro.revision == 6
    assert orden_carlos_y_pedro.datos["potencia_rx"] == -20.5
    assert orden_carlos_y_pedro.datos["nap"] == "NAP-01"
    assert orden_carlos_y_pedro.datos["observaciones"] == "Cliente solicita fibra extendida hasta estudio"
