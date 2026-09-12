# -*- coding: utf-8 -*-
"""
Dos sincronizaciones simultaneas del mismo hilo dejan una sola fila por huella.

    uv run pytest cases/tests/test_respuestas_concurrencia_postgres.py --no-cov -v

POR QUE NO ALCANZA CON LA SUITE NORMAL
--------------------------------------
El upsert por huella resuelve la repeticion dejando chocar el INSERT contra
UniqueConstraint(case, provider, huella) y contando el choque como "ya estaba".

En PostgreSQL ese choque ABORTA la transaccion: toda consulta posterior falla
con InFailedSqlTransaction, incluidas las filas que faltan del mismo lote. Por
eso cada create va dentro de un atomic() anidado, que abre un SAVEPOINT.

Nada de eso se ve en SQLite: ahi la transaccion no queda abortada y la version
sin savepoint pasa la suite entera en verde. Es un fallo que solo aparece en
produccion, y solo cuando dos peticiones caen a la vez -- que es lo que un
barrido horario con reintentos produce tarde o temprano.

Es el mismo defecto que ya se pago una vez en las evidencias de campo y otra en
el writer de casos importados. Esta guarda existe para no pagarlo tres.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from cases.models import Case, RespuestaExterna
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db(transaction=True)


def _lote(n=5):
    return {
        "provider": "wisphub",
        "respuestas": [
            {
                "huella": f"{i:064d}",
                "autor_nombre": "JULIO MORENO",
                "autor_usuario": "tecnico3@rapilink-sas",
                "cuerpo": f"Respuesta numero {i}.",
                "creada_en_proveedor": "2026-09-12T09:34:25-05:00",
                "archivos": 0,
            }
            for i in range(n)
        ],
    }


def _caso(org, user, ticket="92777"):
    return Case.objects.create(
        name="No Tiene Internet", status="New", priority="Normal",
        org=org, created_by=user, provider="wisphub",
        external_ticket_id=ticket, external_service_id="5832",
        external_status="Nuevo")


@pytest.mark.postgres_only
def test_dos_sincronizaciones_simultaneas_no_duplican(admin_user, org_a,
                                                      admin_profile):
    if connection.vendor != "postgresql":
        pytest.skip(
            "Exige PostgreSQL real: en SQLite la transaccion no queda abortada "
            "tras el IntegrityError, asi que la falta del savepoint no se nota")

    caso = _caso(org_a, admin_user)
    acceso = str(OrgAwareRefreshToken.for_user_and_org(
        admin_user, org_a, admin_profile).access_token)
    url = f"/api/importacion/casos/{caso.id}/respuestas/"

    def sincronizar():
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {acceso}")
        return c.post(url, _lote(), format="json")

    with ThreadPoolExecutor(max_workers=2) as ex:
        respuestas = [f.result() for f in [ex.submit(sincronizar) for _ in range(2)]]

    codigos = [r.status_code for r in respuestas]
    # Un 500 aca seria el sintoma exacto de la transaccion abortada: el
    # IntegrityError atrapado y las filas siguientes del lote muriendo detras.
    assert codigos == [200, 200], f"codigos inesperados: {codigos}"

    # La base es la que decide. Da igual como se repartieron las cinco entre
    # los dos hilos -- lo que no puede pasar es que haya seis.
    assert RespuestaExterna.objects.filter(case=caso).count() == 5
    assert RespuestaExterna.objects.filter(case=caso).values(
        "huella").distinct().count() == 5

    # Y entre los dos tienen que sumar exactamente cinco escrituras nuevas:
    # si sumaran mas, alguno conto como nueva una fila que ya existia.
    assert sum(r.json()["nuevas"] for r in respuestas) == 5
    assert sum(r.json()["ya_estaban"] for r in respuestas) == 5


@pytest.mark.postgres_only
def test_la_misma_huella_en_dos_empresas_no_se_estorba(
        admin_user, org_a, admin_profile, user_b, org_b, profile_b):
    """La restriccion lleva 'case' adentro, y cada caso es de una empresa.

    Dos ISP pueden tener el mismo ticket con las mismas respuestas: el hilo de
    uno no puede bloquear el del otro.
    """
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real")

    caso_a = _caso(org_a, admin_user)
    caso_b = _caso(org_b, user_b)

    faenas = [
        (str(OrgAwareRefreshToken.for_user_and_org(
            admin_user, org_a, admin_profile).access_token), caso_a),
        (str(OrgAwareRefreshToken.for_user_and_org(
            user_b, org_b, profile_b).access_token), caso_b),
    ]

    def sincronizar(faena):
        acceso, caso = faena
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {acceso}")
        return c.post(f"/api/importacion/casos/{caso.id}/respuestas/",
                      _lote(), format="json")

    with ThreadPoolExecutor(max_workers=2) as ex:
        respuestas = [f.result() for f in [ex.submit(sincronizar, f) for f in faenas]]

    assert [r.status_code for r in respuestas] == [200, 200]
    assert all(r.json()["nuevas"] == 5 for r in respuestas), (
        "una empresa bloqueo el hilo de la otra")

    assert RespuestaExterna.objects.filter(case=caso_a).count() == 5
    assert RespuestaExterna.objects.filter(case=caso_b).count() == 5
    assert RespuestaExterna.objects.filter(org=org_a).count() == 5
    assert RespuestaExterna.objects.filter(org=org_b).count() == 5


@pytest.mark.postgres_only
def test_un_lote_rechazado_a_mitad_no_deja_filas(admin_user, org_a, admin_profile):
    """El todo-o-nada, comprobado contra PostgreSQL y no contra SQLite.

    La validacion corre entera antes de escribir. Si esta prueba falla, es que
    alguien volvio a mezclar validar con escribir y el lote quedo a medias.
    """
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real")

    caso = _caso(org_a, admin_user)
    acceso = str(OrgAwareRefreshToken.for_user_and_org(
        admin_user, org_a, admin_profile).access_token)

    cuerpo = _lote(8)
    cuerpo["respuestas"][5]["campo_que_no_existe"] = "x"

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {acceso}")
    r = c.post(f"/api/importacion/casos/{caso.id}/respuestas/", cuerpo,
               format="json")

    assert r.status_code == 400, r.content
    assert RespuestaExterna.objects.filter(case=caso).count() == 0, (
        "quedaron filas de un lote rechazado")
