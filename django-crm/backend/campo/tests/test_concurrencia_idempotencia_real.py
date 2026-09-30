# -*- coding: utf-8 -*-
"""Prueba de concurrencia real para el mecanismo de idempotencia."""

from concurrent.futures import ThreadPoolExecutor
import pytest
from django.db import connection
from common.serializer import OrgAwareRefreshToken
from rest_framework.test import APIClient
from campo.models import AsignacionTrabajo, EventoTrabajo, MutacionIdempotente, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services.idempotencia import calcular_hash_canonico


@pytest.fixture
def version_ftth(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_conc", nombre="Instalación Concurrente")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []},
    )


@pytest.fixture
def orden_concurrente(org_a, user_profile, version_ftth):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=6001,
        tipo_trabajo_version=version_ftth,
        cliente_nombre="Cliente Carrera Concurrente",
        cliente_direccion="Calle 100",
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


# transaction=True: sin esto los datos de las fixtures viven en una
# transaccion sin commitear (el autouse _use_db de conftest) y los OTROS
# HILOS, que abren su propia conexion, no los ven -- el perfil no existe
# para ellos y las 5 peticiones vuelven 403. Nunca se noto porque en
# SQLite la prueba se saltea entera; al correrla contra PostgreSQL de
# verdad (08/09/2026, primera vez) fallo por esto y no por el mecanismo
# que dice probar.
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_concurrencia_cinco_requests_simultaneos(org_a, regular_user, user_profile, orden_concurrente):
    """
    Lanza 5 peticiones simultáneas con la MISMA Idempotency-Key contra PostgreSQL real con locking real.
    Garantiza:
    - Exactamente 1 mutación efectiva en la orden
    - Exactamente 1 registro EventoTrabajo
    - Exactamente 1 MutacionIdempotente en base de datos
    - Las otras 4 peticiones reciben 200 (replay) o 409 (operación en curso), NUNCA un 500
    - Cero duplicación de estado
    """
    if connection.vendor != "postgresql":
        pytest.skip("Prueba de concurrencia multihilo real requiere PostgreSQL (SQLite bloquea la base de datos completa en hilos concurrentes)")
    key = "uuid-concurrente-5-requests-test"
    url = f"/api/campo/trabajos/{orden_concurrente.id}/acciones/"
    payload = {"accion": "marcar_en_camino"}

    token = OrgAwareRefreshToken.for_user_and_org(regular_user, org_a, user_profile)
    access_token = str(token.access_token)

    def lanzar_peticion():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        return client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY=key)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futuros = [executor.submit(lanzar_peticion) for _ in range(5)]
        respuestas = [f.result() for f in futuros]

    codigos = [r.status_code for r in respuestas]
    # Todos los códigos deben ser 200 (éxito/replay) o 409 (operación en curso / conflicto)
    assert all(code in (200, 409) for code in codigos), f"Códigos inesperados: {codigos}"
    assert 200 in codigos, "Al menos una petición debió ganar y responder 200"

    # En la base de datos:
    orden_concurrente.refresh_from_db()
    assert orden_concurrente.estado_operativo == OrdenTrabajo.EN_CAMINO
    assert orden_concurrente.revision == 2  # Incrementada una sola vez

    # Exactamente 1 registro de mutación idempotente
    mutaciones = MutacionIdempotente.objects.filter(org=org_a, idempotency_key=key)
    assert mutaciones.count() == 1
    assert mutaciones.first().estado == MutacionIdempotente.COMPLETADA

    # Exactamente 1 EventoTrabajo para esta transición
    eventos = EventoTrabajo.objects.filter(orden=orden_concurrente, tipo="accion_marcar_en_camino")
    assert eventos.count() == 1


def test_carrera_concurrente_intercalada_cinco_intentos(user_client, orden_concurrente, org_a):
    """
    Verifica determinísticamente el ciclo de vida de 5 peticiones concurrentes con la misma key:
    1. Request 1 crea registro en estado PROCESANDO
    2. Request 2 llega mientras procesa -> 409 OPERACION_EN_CURSO
    3. Request 3 llega mientras procesa -> 409 OPERACION_EN_CURSO
    4. Request 1 finaliza con éxito -> estado COMPLETADA
    5. Request 4 llega tras completarse -> 200 OK con header Idempotent-Replay
    6. Request 5 llega con payload modificado -> 409 IDEMPOTENCY_KEY_REUSED
    Resultado en DB: exactamente 1 mutación, 1 evento, 1 registro en MutacionIdempotente.
    """
    key = "uuid-concurrencia-intercalada-005"
    url = f"/api/campo/trabajos/{orden_concurrente.id}/acciones/"
    payload = {"accion": "marcar_en_camino"}
    req_hash = calcular_hash_canonico(payload)

    # 1. Simular Request 1 adquiriendo el lock en estado PROCESANDO
    mutacion = MutacionIdempotente.objects.create(
        org=org_a,
        idempotency_key=key,
        http_method="POST",
        endpoint=url,
        request_hash=req_hash,
        estado=MutacionIdempotente.PROCESANDO,
    )

    # 2. Request 2 concurrente mientras está procesando
    res_2 = user_client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert res_2.status_code == 409
    assert res_2.json()["error"] == "OPERACION_EN_CURSO"

    # 3. Request 3 concurrente mientras sigue procesando
    res_3 = user_client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert res_3.status_code == 409
    assert res_3.json()["error"] == "OPERACION_EN_CURSO"

    # 4. Request 1 concluye su trabajo real: transiciona la orden y guarda la respuesta en COMPLETADA
    orden_concurrente.estado_operativo = OrdenTrabajo.EN_CAMINO
    orden_concurrente.revision = 2
    orden_concurrente.save()

    EventoTrabajo.objects.create(
        org=org_a,
        orden=orden_concurrente,
        tipo="accion_marcar_en_camino",
        datos={"revision": 2},
    )

    respuesta_exitosa = {
        "mutation_id": "req-1",
        "aplicada": True,
        "estado_operativo": "en_camino",
        "revision": 2,
    }
    mutacion.estado = MutacionIdempotente.COMPLETADA
    mutacion.status_code = 200
    mutacion.respuesta_json = respuesta_exitosa
    mutacion.save()

    # 5. Request 4 llega después: debe recibir el replay exacto
    res_4 = user_client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert res_4.status_code == 200
    assert res_4.headers.get("Idempotent-Replay") == "true"
    assert res_4.json()["estado_operativo"] == "en_camino"

    # 6. Request 5 intenta usar la misma key con otro payload
    res_5 = user_client.post(url, {"accion": "cancelar"}, format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert res_5.status_code == 409
    assert res_5.json()["error"] == "IDEMPOTENCY_KEY_REUSED"

    # 7. Verificación final de integridad en BD
    orden_concurrente.refresh_from_db()
    assert orden_concurrente.revision == 2
    assert MutacionIdempotente.objects.filter(org=org_a, idempotency_key=key).count() == 1
    assert EventoTrabajo.objects.filter(orden=orden_concurrente, tipo="accion_marcar_en_camino").count() == 1
