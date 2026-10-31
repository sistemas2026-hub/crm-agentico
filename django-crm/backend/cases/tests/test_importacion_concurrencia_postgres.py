# -*- coding: utf-8 -*-
"""
Dos importaciones simultaneas del MISMO ticket dejan un solo caso.

    uv run pytest cases/tests/test_importacion_concurrencia_postgres.py --no-cov -v

POR QUE NO ALCANZA CON LA SUITE NORMAL
--------------------------------------
El writer resuelve la carrera con un SELECT, un INSERT que puede chocar contra
UNIQUE(org, provider, external_ticket_id), y una relectura del ganador.

En PostgreSQL ese choque ABORTA la transaccion: toda consulta posterior falla
con InFailedSqlTransaction, incluida esa relectura. Por eso el create va dentro
de un atomic() anidado, que abre un SAVEPOINT y permite seguir usando la
transaccion despues del choque.

Nada de eso se ve en SQLite: ahi la transaccion no queda abortada y la version
SIN savepoint pasa la suite entera en verde. Es un fallo que solo aparece en
produccion, y solo cuando dos peticiones caen a la vez -- exactamente lo que un
barrido horario con reintentos produce tarde o temprano.

Es el mismo defecto que ya se pago una vez en las evidencias de campo. Esta
guarda existe para no pagarlo dos.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from cases.models import Case
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db(transaction=True)

IMPORTAR = "/api/importacion/casos/"
CUERPO = {
    "provider": "wisphub",
    "external_ticket_id": "92777",
    "external_service_id": "5832",
    "external_status": "Nuevo",
    "external_created_by": "SHEILA - licencia@rapilink-sas",
    "external_created_by_type": "humano_verificado",
    "name": "No Tiene Internet",
    "priority": "Normal",
    "status": "New",
}


@pytest.mark.postgres_only
def test_dos_importaciones_simultaneas_del_mismo_ticket(admin_user, org_a,
                                                        admin_profile):
    if connection.vendor != "postgresql":
        pytest.skip(
            "Exige PostgreSQL real: en SQLite la transaccion no queda abortada "
            "tras el IntegrityError, asi que la falta del savepoint no se nota")

    acceso = str(OrgAwareRefreshToken.for_user_and_org(
        admin_user, org_a, admin_profile).access_token)

    def importar():
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {acceso}")
        return c.post(IMPORTAR, CUERPO, format="json")

    with ThreadPoolExecutor(max_workers=2) as ex:
        respuestas = [f.result() for f in [ex.submit(importar) for _ in range(2)]]

    codigos = sorted(r.status_code for r in respuestas)
    # Un 500 aca seria exactamente el sintoma de la transaccion abortada: el
    # IntegrityError atrapado y la relectura muriendo detras.
    assert codigos == [200, 201], f"codigos inesperados: {codigos}"

    creados = [r.json()["created"] for r in respuestas]
    assert sorted(creados) == [False, True], "los dos creyeron haber creado"

    ids = {r.json()["case_id"] for r in respuestas}
    assert len(ids) == 1, f"los dos callers deben terminar en el mismo caso: {ids}"

    assert Case.objects.filter(
        org=org_a, provider="wisphub", external_ticket_id="92777").count() == 1

    # Y el que quedo es utilizable: con su identidad puesta desde el INSERT,
    # no a medias por un update posterior que pudo no llegar.
    caso = Case.objects.get(pk=ids.pop())
    assert caso.external_service_id == "5832"
    assert caso.status == "New"


@pytest.mark.postgres_only
def test_la_misma_carrera_en_dos_orgs_no_se_estorba(admin_user, org_a, admin_profile,
                                                    user_b, org_b, profile_b):
    """El UNIQUE lleva 'org' adentro: dos ISP pueden tener su ticket 92777."""
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real")

    tokens = [
        str(OrgAwareRefreshToken.for_user_and_org(admin_user, org_a,
                                                  admin_profile).access_token),
        str(OrgAwareRefreshToken.for_user_and_org(user_b, org_b,
                                                  profile_b).access_token),
    ]

    def importar(acceso):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {acceso}")
        return c.post(IMPORTAR, CUERPO, format="json")

    with ThreadPoolExecutor(max_workers=2) as ex:
        respuestas = [f.result() for f in [ex.submit(importar, t) for t in tokens]]

    assert all(r.status_code == 201 for r in respuestas)
    assert all(r.json()["created"] for r in respuestas)
    assert Case.objects.filter(external_ticket_id="92777").count() == 2
