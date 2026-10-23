# -*- coding: utf-8 -*-
"""
El contrato exacto de POST /api/campo/trabajos/<id>/evidencias/.

    uv run pytest campo/tests/test_contrato_respuesta_evidencias.py --no-cov -s

Existe para que el contrato quede FIJADO por una prueba y no descrito en un
documento que envejece aparte del codigo. Con -s imprime la respuesta real de
cada caso, que es lo que necesita quien escribe el cliente movil.

El campo 'upload' vale null cuando la evidencia ya esta en el servidor. No es
un descuido: el sha256 identifica la fila, no garantiza que lo que se suba
despues coincida, asi que entregar una URL de subida sobre una evidencia ya
aceptada -- o auditada, si esta verificada -- seria entregar la forma de
reemplazarla.
"""

import json

import pytest

from campo.models import (AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db

SHA = "dd" * 32
CUERPO = {
    "requisito_id": "foto_ont",
    "nombre": "ont.jpg",
    "mime_type": "image/jpeg",
    "bytes": 1024,
    "sha256": SHA,
}


@pytest.fixture
def version_ct(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_ct", nombre="Instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto ONT", "tipo": "foto", "obligatorio": True}]},
    )


@pytest.fixture
def orden_ct(org_a, user_profile, version_ct):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9701, tipo_trabajo_version=version_ct,
        cliente_nombre="Cliente Contrato", cliente_direccion="Calle 3",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=user_profile, rol="tecnico_lider", es_principal=True)
    return o


def _mostrar(titulo, respuesta):
    print(f"\n--- {titulo} --- HTTP {respuesta.status_code}")
    print(json.dumps(respuesta.json(), indent=2, ensure_ascii=False, sort_keys=True))


def test_contrato_en_los_tres_estados(user_client, orden_ct):
    url = f"/api/campo/trabajos/{orden_ct.id}/evidencias/"

    # --- A. primera vez: la evidencia nace en SUBIENDO ---------------------
    a = user_client.post(url, CUERPO, format="json")
    _mostrar("A. PENDIENTE/SUBIENDO (primera vez, y tambien el reintento)", a)
    assert a.status_code == 200
    assert set(a.json()) == {"evidencia_id", "estado_archivo", "storage_key", "upload"}
    assert a.json()["estado_archivo"] == "subiendo"
    up = a.json()["upload"]
    assert set(up) == {"method", "url", "headers", "requiere_auth_dexter", "expires_in"}
    assert up["method"] == "PUT"
    assert up["expires_in"] == 900
    # 'headers' existe desde ahora aunque vaya vacio: con S3/R2 llevara las
    # cabeceras firmadas del proveedor, y que aparezca recien ese dia seria un
    # cambio rompedor para una app ya publicada.
    assert up["headers"] == {}
    # Hoy true porque la subida la atiende esta misma API. Con una URL
    # prefirmada pasa a false: mandarle el JWT de Dexter a un proveedor
    # externo seria entregarle una credencial que abre toda la API.
    assert up["requiere_auth_dexter"] is True

    ev = EvidenciaTrabajo.objects.get(pk=a.json()["evidencia_id"])

    # --- B. la misma, ya RECIBIDA ------------------------------------------
    ev.estado_archivo = EvidenciaTrabajo.RECIBIDO
    ev.save(update_fields=["estado_archivo"])
    b = user_client.post(url, CUERPO, format="json")
    _mostrar("B. RECIBIDA", b)
    assert b.status_code == 200
    assert set(b.json()) == {"evidencia_id", "estado_archivo", "storage_key",
                             "upload", "mensaje"}
    assert b.json()["evidencia_id"] == str(ev.id)
    assert b.json()["estado_archivo"] == "recibido"
    assert b.json()["upload"] is None
    assert b.json()["storage_key"] == a.json()["storage_key"]

    # --- C. la misma, ya VERIFICADA ---------------------------------------
    ev.estado_archivo = EvidenciaTrabajo.VERIFICADO
    ev.save(update_fields=["estado_archivo"])
    c = user_client.post(url, CUERPO, format="json")
    _mostrar("C. VERIFICADA", c)
    assert c.status_code == 200
    assert c.json()["evidencia_id"] == str(ev.id)
    assert c.json()["estado_archivo"] == "verificado"
    assert c.json()["upload"] is None
    assert c.json()["storage_key"] == a.json()["storage_key"]

    # El estado no se movio en ninguno de los dos reintentos.
    ev.refresh_from_db()
    assert ev.estado_archivo == EvidenciaTrabajo.VERIFICADO
