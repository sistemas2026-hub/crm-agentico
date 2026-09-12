# -*- coding: utf-8 -*-
"""
Dos subidas simultaneas de la MISMA foto dejan una sola evidencia.

    uv run pytest campo/tests/test_concurrencia_evidencias_postgres.py --no-cov -v

POR QUE NO ALCANZA CON LA SUITE NORMAL
--------------------------------------
El registro de evidencia resuelve la carrera con select_for_update mas un
INSERT que puede chocar contra el UniqueConstraint (orden, requisito, sha).
Ese choque se atrapa y se relee la fila que gano.

En PostgreSQL, un INSERT que viola una constraint ABORTA la transaccion: toda
consulta posterior falla con InFailedSqlTransaction, incluida esa relectura.
Por eso el create va dentro de un atomic() anidado, que abre un SAVEPOINT y
permite seguir usando la transaccion despues del choque.

Nada de eso se ve en SQLite: ahi la transaccion no queda abortada y la version
SIN savepoint pasa la suite entera en verde. Es un fallo que solo aparece en
produccion, y solo cuando dos peticiones caen a la vez. De ahi que esta guarda
exista aparte y exija PostgreSQL de verdad -- con hilos reales, no simulados.

QUE FIJA
--------
    dos requests simultaneos, mismo (orden, requisito_id, sha256)
      -> una sola EvidenciaTrabajo
      -> ninguna transaccion rota: ningun 500
      -> los dos callers terminan con el MISMO evidencia_id
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from common.serializer import OrgAwareRefreshToken
from campo.models import (AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db(transaction=True)

SHA = "cc" * 32
CUERPO = {
    "requisito_id": "foto_ont",
    "nombre": "ont.jpg",
    "mime_type": "image/jpeg",
    "bytes": 4096,
    "sha256": SHA,
}


@pytest.fixture
def version_conc(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_conc_ev", nombre="Instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto ONT", "tipo": "foto", "obligatorio": True}]},
    )


@pytest.fixture
def orden_conc(org_a, user_profile, version_conc):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9501, tipo_trabajo_version=version_conc,
        cliente_nombre="Cliente Concurrencia", cliente_direccion="Calle 9",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=user_profile, rol="tecnico_lider", es_principal=True)
    return o


@pytest.mark.postgres_only
def test_dos_subidas_simultaneas_de_la_misma_foto(org_a, regular_user, user_profile, orden_conc):
    if connection.vendor != "postgresql":
        pytest.skip(
            "Exige PostgreSQL real: en SQLite la transaccion no queda abortada "
            "tras el IntegrityError, asi que la falta del savepoint no se nota")

    token = OrgAwareRefreshToken.for_user_and_org(regular_user, org_a, user_profile)
    access = str(token.access_token)
    url = f"/api/campo/trabajos/{orden_conc.id}/evidencias/"

    def subir():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        # SIN Idempotency-Key a proposito: se prueba la carrera de la vista,
        # no el candado del decorador. Con la cabecera, una de las dos ni
        # llegaria a intentar el INSERT.
        return client.post(url, CUERPO, format="json")

    with ThreadPoolExecutor(max_workers=2) as executor:
        respuestas = [f.result() for f in [executor.submit(subir) for _ in range(2)]]

    codigos = [r.status_code for r in respuestas]
    # Un 500 aca seria exactamente el sintoma de la transaccion abortada: el
    # IntegrityError atrapado y la relectura muriendo detras.
    assert all(c == 200 for c in codigos), f"codigos inesperados: {codigos}"

    ids = {r.json()["evidencia_id"] for r in respuestas}
    assert len(ids) == 1, f"los dos callers deben terminar en la misma evidencia: {ids}"

    assert EvidenciaTrabajo.objects.filter(
        orden_trabajo=orden_conc, requisito_id="foto_ont", sha256=SHA).count() == 1

    # Y la que quedo es utilizable: con su storage_key puesta, no a medias.
    ev = EvidenciaTrabajo.objects.get(pk=ids.pop())
    assert ev.storage_key, "la evidencia sobreviviente quedo sin storage_key"
    assert ev.estado_archivo == EvidenciaTrabajo.SUBIENDO


@pytest.mark.postgres_only
def test_carrera_contra_una_evidencia_ya_recibida(org_a, regular_user, user_profile, orden_conc):
    """La carrera sobre un estado terminal tampoco lo degrada.

    Es el bug original y la concurrencia juntos: si dos reintentos tardios
    llegan a la vez sobre una evidencia YA recibida, ninguno puede devolverla
    a SUBIENDO ni cambiarle la storage_key.
    """
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real")

    token = OrgAwareRefreshToken.for_user_and_org(regular_user, org_a, user_profile)
    access = str(token.access_token)
    url = f"/api/campo/trabajos/{orden_conc.id}/evidencias/"

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    primera = client.post(url, CUERPO, format="json")
    ev = EvidenciaTrabajo.objects.get(pk=primera.json()["evidencia_id"])
    key_original = ev.storage_key
    ev.estado_archivo = EvidenciaTrabajo.RECIBIDO
    ev.save(update_fields=["estado_archivo"])

    def reintentar():
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return c.post(url, CUERPO, format="json")

    with ThreadPoolExecutor(max_workers=3) as executor:
        respuestas = [f.result() for f in [executor.submit(reintentar) for _ in range(3)]]

    assert all(r.status_code == 200 for r in respuestas)
    assert all(r.json()["evidencia_id"] == str(ev.id) for r in respuestas)
    assert all(r.json()["upload"] is None for r in respuestas)

    ev.refresh_from_db()
    assert ev.estado_archivo == EvidenciaTrabajo.RECIBIDO
    assert ev.storage_key == key_original
    assert EvidenciaTrabajo.objects.filter(
        orden_trabajo=orden_conc, requisito_id="foto_ont", sha256=SHA).count() == 1
