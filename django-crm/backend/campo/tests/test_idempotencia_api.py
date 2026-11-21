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


def test_operacion_en_curso_pide_volver_en_un_rato(user_client, orden_test, org_a):
    """Con la clave todavia 'procesando', quien reintenta recibe 429 + Retry-After.

    Hasta el 21/11/2026 esto era 409, y la app de campo trata el 409 como un
    conflicto que alguien tiene que revisar: no lo reintenta mas. El primer
    intento seguia corriendo y terminaba bien, y el tecnico quedaba con «10
    cambios necesitan que alguien los revise» sobre cambios ya aplicados.

    429 con `Retry-After` es lo que la app YA sabe reintentar
    (`sync_queue_service.dart`, `_leerRetryAfter`): vuelve a los segundos y
    encuentra la respuesta guardada. Ver `_respuesta_en_curso`.
    """
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
    assert res.status_code == 429, res.content
    assert res.json()["error"] == "OPERACION_EN_CURSO"
    #  El plazo viaja en la cabecera, que es lo que la app lee. Sin ella la
    #  app reintenta igual, pero con su propio retroceso.
    assert res["Retry-After"] == "5"
    #  Y NO se ejecuto de nuevo: la orden sigue como estaba.
    orden_test.refresh_from_db()
    assert orden_test.estado_operativo == OrdenTrabajo.ASIGNADA


def test_el_reintento_ENCUENTRA_la_respuesta_cuando_el_primero_termina(
        user_client, orden_test, org_a):
    """El efecto completo, que es lo que le importa al tecnico.

    Primer reintento: «en curso, volve en un rato». El primer intento
    termina. Segundo reintento, con la MISMA clave: la respuesta guardada,
    200, y el cambio queda sincronizado en el telefono en vez de trabado.
    """
    key = "uuid-key-reintento-021"
    url = f"/api/campo/trabajos/{orden_test.id}/acciones/"
    body = {"accion": "marcar_en_camino"}
    fila = MutacionIdempotente.objects.create(
        org=org_a, idempotency_key=key, http_method="POST", endpoint=url,
        request_hash=calcular_hash_canonico(body),
        estado=MutacionIdempotente.PROCESANDO,
    )

    r1 = user_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert r1.status_code == 429, r1.content

    #  El primer intento termina.
    MutacionIdempotente.objects.filter(pk=fila.pk).update(
        estado=MutacionIdempotente.COMPLETADA, status_code=200,
        respuesta_json={"aplicada": True, "estado_operativo": "en_camino",
                        "revision": 2})

    r2 = user_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert r2.status_code == 200, r2.content
    assert r2["Idempotent-Replay"] == "true"
    assert r2.json()["estado_operativo"] == "en_camino"


def test_una_clave_HUERFANA_sigue_siendo_409(user_client, orden_test, org_a):
    """La otra mitad, y la que impide que el arreglo de arriba haga dano.

    Una fila que lleva 'procesando' mas de lo que una peticion dura no esta
    en curso: el proceso que la creo murio. Nadie va a completarla. Contestar
    429 ahi dejaria al telefono reintentando para siempre; eso SI es para una
    persona, y sigue siendo 409 como siempre.
    """
    from datetime import timedelta

    from django.utils import timezone

    from campo.services import idempotencia

    key = "uuid-key-huerfana-022"
    url = f"/api/campo/trabajos/{orden_test.id}/acciones/"
    body = {"accion": "marcar_en_camino"}
    fila = MutacionIdempotente.objects.create(
        org=org_a, idempotency_key=key, http_method="POST", endpoint=url,
        request_hash=calcular_hash_canonico(body),
        estado=MutacionIdempotente.PROCESANDO,
    )
    vieja = timezone.now() - timedelta(
        seconds=idempotencia.EN_CURSO_HASTA_SEGUNDOS + 30)
    MutacionIdempotente.objects.filter(pk=fila.pk).update(created_at=vieja)

    res = user_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert res.status_code == 409, res.content
    assert res.json()["error"] == "OPERACION_EN_CURSO"
    assert "Retry-After" not in res
    orden_test.refresh_from_db()
    assert orden_test.estado_operativo == OrdenTrabajo.ASIGNADA


def test_justo_ANTES_del_tope_todavia_es_en_curso(user_client, orden_test,
                                                  org_a):
    """El borde, para que el tope no se corra solo."""
    from datetime import timedelta

    from django.utils import timezone

    from campo.services import idempotencia

    key = "uuid-key-borde-023"
    url = f"/api/campo/trabajos/{orden_test.id}/acciones/"
    body = {"accion": "marcar_en_camino"}
    fila = MutacionIdempotente.objects.create(
        org=org_a, idempotency_key=key, http_method="POST", endpoint=url,
        request_hash=calcular_hash_canonico(body),
        estado=MutacionIdempotente.PROCESANDO,
    )
    casi = timezone.now() - timedelta(
        seconds=idempotencia.EN_CURSO_HASTA_SEGUNDOS - 30)
    MutacionIdempotente.objects.filter(pk=fila.pk).update(created_at=casi)

    res = user_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)

    assert res.status_code == 429, res.content
