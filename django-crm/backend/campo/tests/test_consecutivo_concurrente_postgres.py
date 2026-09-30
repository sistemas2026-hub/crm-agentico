# -*- coding: utf-8 -*-
"""
El consecutivo de la orden, bajo dos supervisores creando a la vez.

    docker run -d --name pg-campo-test -e POSTGRES_PASSWORD=test \
        -e POSTGRES_USER=test -e POSTGRES_DB=test -p 55432:5432 postgres:16-alpine
    set TEST_DATABASE_URL=postgres://test:test@localhost:55432/test
    pytest campo/tests/test_consecutivo_concurrente_postgres.py --no-cov -v

POR QUÉ EXIGE POSTGRESQL DE VERDAD
----------------------------------
`crear_orden` asigna `numero` con `max(numero) + 1` y deja que la restricción
`unique_numero_orden_per_org` decida: si dos supervisores leen el mismo máximo,
uno pierde y reintenta. Eso descansa en dos comportamientos que SQLite no
reproduce:

1. Un INSERT que viola una constraint **aborta la transacción entera** en
   PostgreSQL, y toda consulta posterior falla con `InFailedSqlTransaction` --
   incluida la relectura del máximo en el reintento. Por eso el reintento va
   dentro de un `atomic()` anidado, que abre un SAVEPOINT. Sin él, el `except`
   atrapa el `IntegrityError` y muere en la línea siguiente.
2. SQLite serializa la base entera con hilos concurrentes, así que la carrera
   ni siquiera ocurre.

Es exactamente la lección que ya costó una vez en el registro de evidencias
(08/09/2026), y la razón por la que estas pruebas existen aparte.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from django.db import connection
from rest_framework.test import APIClient

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

CANTIDAD = 5


@pytest.fixture
def version_concurrente(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="conc", nombre="Concurrente")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []},
    )


# transaction=True por el mismo motivo que la otra prueba de concurrencia: sin
# esto las fixtures viven en una transacción sin commitear y los otros hilos,
# que abren su propia conexión, no las ven.
@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_creaciones_simultaneas_no_repiten_consecutivo(org_a, version_concurrente):
    """
    Cinco supervisores creando a la vez en la misma empresa.

    Cada uno con su propia Idempotency-Key: son cinco intenciones distintas,
    no un botón apretado cinco veces. Así que tienen que salir CINCO órdenes
    con cinco números distintos -- ninguna perdida por la carrera, ninguna
    repetida, y ningún 500.
    """
    if connection.vendor != "postgresql":
        pytest.skip("La carrera del consecutivo solo se reproduce en PostgreSQL.")

    user = User.objects.create_user(email="sup.conc@test.com", password="x")
    profile = Profile.objects.create(user=user, org=org_a, role="SUPERVISOR",
                                     is_active=True)
    token = str(OrgAwareRefreshToken.for_user_and_org(user, org_a, profile).access_token)

    def crear(_):
        cli = APIClient()
        cli.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return cli.post(
            "/api/campo/trabajos/crear/",
            {"work_type_version_id": str(version_concurrente.id),
             "cliente_nombre": "Cliente concurrente"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

    with ThreadPoolExecutor(max_workers=CANTIDAD) as pool:
        respuestas = list(pool.map(crear, range(CANTIDAD)))

    codigos = [r.status_code for r in respuestas]
    assert all(c == 201 for c in codigos), f"codigos inesperados: {codigos}"

    numeros = [r.data["orden"]["numero"] for r in respuestas]
    assert len(set(numeros)) == CANTIDAD, f"consecutivos repetidos: {sorted(numeros)}"
    assert OrdenTrabajo.objects.filter(org=org_a).count() == CANTIDAD

    # Y son consecutivos de verdad, no cinco valores sueltos: la restricción
    # obliga a que cada reintento tome el siguiente libre.
    assert sorted(numeros) == list(range(min(numeros), min(numeros) + CANTIDAD))


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres_only
def test_la_misma_clave_repetida_sigue_creando_una_sola(org_a, version_concurrente):
    """
    Cinco peticiones simultáneas con la MISMA clave: eso sí es un botón
    apretado cinco veces, y tiene que salir una sola orden.

    Es la contracara de la prueba anterior, y las dos juntas son lo que hace
    que permitir varias órdenes por caso no signifique permitir duplicados
    accidentales.
    """
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real.")

    user = User.objects.create_user(email="sup.clic@test.com", password="x")
    profile = Profile.objects.create(user=user, org=org_a, role="SUPERVISOR",
                                     is_active=True)
    token = str(OrgAwareRefreshToken.for_user_and_org(user, org_a, profile).access_token)
    clave = str(uuid.uuid4())
    cuerpo = {"work_type_version_id": str(version_concurrente.id),
              "cliente_nombre": "Un solo clic"}

    def crear(_):
        cli = APIClient()
        cli.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return cli.post("/api/campo/trabajos/crear/", cuerpo, format="json",
                        HTTP_IDEMPOTENCY_KEY=clave)

    with ThreadPoolExecutor(max_workers=CANTIDAD) as pool:
        respuestas = list(pool.map(crear, range(CANTIDAD)))

    codigos = [r.status_code for r in respuestas]
    assert all(c in (201, 409) for c in codigos), f"codigos inesperados: {codigos}"
    assert 201 in codigos, "alguna tenia que ganar"
    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1
