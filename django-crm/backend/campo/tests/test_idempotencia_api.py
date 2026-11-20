# -*- coding: utf-8 -*-
"""Pruebas de idempotencia a nivel de API REST, protección contra colisiones y repetición canónica."""

import json
import pytest
from campo.models import AsignacionTrabajo, MutacionIdempotente, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services.idempotencia import calcular_hash_canonico


@pytest.fixture
def version_ftth(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_inst", nombre="Instalación")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={
            "campos": [{"id": "potencia_rx", "tipo": "decimal", "reglas": {"required": True}}],
            "evidencias": [],
        },
    )


@pytest.fixture
def orden_test(org_a, user_profile, version_ftth):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=3001,
        tipo_trabajo_version=version_ftth,
        cliente_nombre="Cliente Idempotente",
        cliente_direccion="Calle Falsa 123",
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


def test_flujo_idempotencia_replay_y_hash_canonico(user_client, orden_test):
    """Verifica primera ejecución, replay exacto con header Idempotent-Replay, e invariancia de orden de claves JSON."""
    url = f"/api/campo/trabajos/{orden_test.id}/acciones/"
    key = "uuid-key-transicion-001"

    # 1. Primera petición: ejecuta y responde 200
    res1 = user_client.post(
        url,
        {"accion": "marcar_en_camino"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["estado_operativo"] == "en_camino"
    assert "Idempotent-Replay" not in res1.headers

    # 2. Reintento con exactamente la misma key y payload: debe ser un replay sin error
    res2 = user_client.post(
        url,
        {"accion": "marcar_en_camino"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert res2.status_code == 200
    assert res2.headers.get("Idempotent-Replay") == "true"
    assert res2.json() == data1

    # 3. Mismo contenido pero claves en diferente orden (comprobación JSON canónico)
    key_canon = "uuid-key-canonico-002"
    url_llegada = f"/api/campo/trabajos/{orden_test.id}/acciones/"

    res_c1 = user_client.post(
        url_llegada,
        {"accion": "marcar_llegada", "metadatos": {"lat": 4.5, "lng": -74.1}},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key_canon,
    )
    assert res_c1.status_code == 200

    # Segunda llamada invirtiendo las claves JSON manualmente en el payload
    payload_invertido = json.dumps({"metadatos": {"lng": -74.1, "lat": 4.5}, "accion": "marcar_llegada"})
    res_c2 = user_client.post(
        url_llegada,
        data=payload_invertido,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key_canon,
    )
    assert res_c2.status_code == 200
    assert res_c2.headers.get("Idempotent-Replay") == "true"


def test_reuso_de_key_con_distinto_payload_genera_409(user_client, orden_test):
    """Reutilizar una key existente con un payload modificado debe retornar 409 IDEMPOTENCY_KEY_REUSED."""
    url = f"/api/campo/trabajos/{orden_test.id}/acciones/"
    key = "uuid-key-conflicto-003"

    # Primera petición
    res1 = user_client.post(
        url,
        {"accion": "marcar_en_camino"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert res1.status_code == 200

    # Misma key pero payload totalmente diferente
    res2 = user_client.post(
        url,
        {"accion": "cancelar"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert res2.status_code == 409
    data2 = res2.json()
    assert data2["error"] == "IDEMPOTENCY_KEY_REUSED"


def test_operacion_en_curso_genera_409(user_client, orden_test, org_a):
    """Si la key se encuentra en estado 'procesando', llamadas concurrentes reciben 409 OPERACION_EN_CURSO."""
    key = "uuid-key-concurrente-004"
    url = f"/api/campo/trabajos/{orden_test.id}/acciones/"

    body = {"accion": "marcar_en_camino"}
    req_hash = calcular_hash_canonico(body)
    MutacionIdempotente.objects.create(
        org=org_a,
        idempotency_key=key,
        http_method="POST",
        endpoint=url,
        request_hash=req_hash,
        estado=MutacionIdempotente.PROCESANDO,
    )

    res = user_client.post(
        url,
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert res.status_code == 409
    assert res.json()["error"] == "OPERACION_EN_CURSO"
