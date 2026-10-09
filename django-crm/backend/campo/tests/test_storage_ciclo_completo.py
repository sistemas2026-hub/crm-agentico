# -*- coding: utf-8 -*-
"""Prueba del ciclo completo de almacenamiento de evidencias y protección de acceso cross-tenant."""

import os
import pytest
from django.conf import settings
from campo.models import AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


@pytest.fixture
def version_con_evidencia(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_ev", nombre="Instalación con Evidencias")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={
            "campos": [],
            "evidencias": [
                {"id": "foto_ont", "titulo": "Foto ONT Instalada", "tipo": "foto", "obligatorio": True}
            ],
        },
    )


@pytest.fixture
def orden_evidencias(org_a, user_profile, version_con_evidencia):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=8001,
        tipo_trabajo_version=version_con_evidencia,
        cliente_nombre="Cliente Evidencias",
        cliente_direccion="Calle 72 # 11-80",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=orden,
        profile=user_profile,
        rol="tecnico_lider",
        es_principal=True,
    )
    return orden


def test_circuito_completo_evidencias_y_aislamiento(user_client, org_b_client, orden_evidencias):
    """
    Circuito completo de almacenamiento de evidencia:
    1. Crear evidencia -> obtener upload firmado
    2. Intentar confirmar sin archivo físico -> falla con 400 ARCHIVO_NO_ENCONTRADO
    3. Simular subida física del archivo
    4. Confirmar subida -> éxito y estado pasa a 'recibida'
    5. Tenant B intenta generar download URL de esa evidencia -> 404 estricto
    6. Tenant A genera download URL segura -> 200 OK
    """
    orden_id = str(orden_evidencias.id)

    # 1. Crear intención de evidencia y obtener upload firmado
    res_crear = user_client.post(
        f"/api/campo/trabajos/{orden_id}/evidencias/",
        {
            "requisito_id": "foto_ont",
            "nombre": "ont_instalada.jpg",
            "mime_type": "image/jpeg",
            "bytes": 4096,
            "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-evidencia-circuito-1",
    )
    assert res_crear.status_code == 200
    evidencia_id = res_crear.json()["evidencia_id"]
    upload_info = res_crear.json()["upload"]
    assert "url" in upload_info
    assert upload_info["method"] == "PUT"

    # 2. Intentar confirmar antes de subir el archivo al storage: DEBE FALLAR
    res_conf_fallo = user_client.post(
        f"/api/campo/evidencias/{evidencia_id}/confirmar/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-ev-conf-fail",
    )
    assert res_conf_fallo.status_code == 400
    assert res_conf_fallo.json()["error"] == "ARCHIVO_NO_ENCONTRADO"

    # 3. Subir el archivo físicamente al storage
    ev_obj = EvidenciaTrabajo.objects.get(pk=evidencia_id)
    ruta_almacenamiento = os.path.join(settings.MEDIA_ROOT, ev_obj.storage_key)
    os.makedirs(os.path.dirname(ruta_almacenamiento), exist_ok=True)
    with open(ruta_almacenamiento, "wb") as f:
        f.write(b"CONTENIDO BINARIO FOTOGRAFIA ONT")

    # 4. Confirmar ahora que el archivo sí existe físicamente
    res_conf_ok = user_client.post(
        f"/api/campo/evidencias/{evidencia_id}/confirmar/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-ev-conf-ok",
    )
    assert res_conf_ok.status_code == 200
    assert res_conf_ok.json()["estado"] == "recibida"

    ev_obj.refresh_from_db()
    assert ev_obj.estado_archivo == EvidenciaTrabajo.RECIBIDO

    # 5. Tenant B intenta generar download URL o consultar la evidencia de Org A: DEBE RETORNAR 404
    res_tenant_b = org_b_client.get(f"/api/campo/evidencias/{evidencia_id}/url/")
    assert res_tenant_b.status_code == 404

    # 6. Tenant A genera download URL segura: 200 OK
    res_tenant_a = user_client.get(f"/api/campo/evidencias/{evidencia_id}/url/")
    assert res_tenant_a.status_code == 200
    data_url = res_tenant_a.json()
    assert data_url["evidencia_id"] == evidencia_id
    assert ev_obj.storage_key in data_url["download_url"]
    assert data_url["estado_archivo"] == EvidenciaTrabajo.RECIBIDO


def test_reintentos_evidencias_idempotencia_y_unicidad(user_client, orden_evidencias):
    """
    Verifica los 3 casos de retry offline:
    1. Si la respuesta al crear evidencia se pierde y el cliente reintenta con mismo SHA y requisito:
       - No crea evidencia nueva (reutiliza ID #1).
       - Devuelve nueva URL de upload válida.
       - La tabla tiene exactamente 1 registro.
    2. Reintento de confirmación repetida sobre evidencia ya recibida:
       - Retorna 200 OK inmediatamente.
       - No genera un segundo EventoTrabajo.
    """
    from campo.models import EventoTrabajo
    orden_id = str(orden_evidencias.id)
    sha_muestra = "11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff"

    # 1. Primer intento de creación
    res1 = user_client.post(
        f"/api/campo/trabajos/{orden_id}/evidencias/",
        {
            "requisito_id": "foto_ont",
            "nombre": "ont_1.jpg",
            "mime_type": "image/jpeg",
            "bytes": 2048,
            "sha256": sha_muestra,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-intento-1",
    )
    assert res1.status_code == 200
    ev1_id = res1.json()["evidencia_id"]

    # 2. Simulación de pérdida de conexión y reintento con otra key o sin key
    res2 = user_client.post(
        f"/api/campo/trabajos/{orden_id}/evidencias/",
        {
            "requisito_id": "foto_ont",
            "nombre": "ont_1.jpg",
            "mime_type": "image/jpeg",
            "bytes": 2048,
            "sha256": sha_muestra,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-reintento-2",
    )
    assert res2.status_code == 200
    ev2_id = res2.json()["evidencia_id"]

    # DEBEN ser el mismo registro fisico. OJO con el motivo: NO es
    # 'update_or_create' -- ese era justamente el bug (pisaba estado y
    # storage_key). Lo garantiza el UniqueConstraint (orden, requisito, sha)
    # mas el manejo por estado de la vista. Este test solo cubre el reintento
    # mientras la evidencia sigue en SUBIENDO; el caso peligroso -- reintentar
    # cuando ya esta RECIBIDA -- vive en
    # tests/test_reintento_evidencia_no_retrocede.py.
    assert ev1_id == ev2_id
    conteo_evidencias = EvidenciaTrabajo.objects.filter(
        orden_trabajo=orden_evidencias,
        requisito_id="foto_ont",
        sha256=sha_muestra,
    ).count()
    assert conteo_evidencias == 1

    # 3. Subir archivo físico y confirmar
    ev_obj = EvidenciaTrabajo.objects.get(pk=ev1_id)
    ruta = os.path.join(settings.MEDIA_ROOT, ev_obj.storage_key)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(b"DATA TEST")

    res_conf_1 = user_client.post(
        f"/api/campo/evidencias/{ev1_id}/confirmar/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="conf-key-1",
    )
    assert res_conf_1.status_code == 200
    eventos_iniciales = EventoTrabajo.objects.filter(
        orden=orden_evidencias, tipo="evidencia_confirmada"
    ).count()
    assert eventos_iniciales == 1

    # 4. Reintento de confirmación con OTRA Idempotency-Key
    res_conf_2 = user_client.post(
        f"/api/campo/evidencias/{ev1_id}/confirmar/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="conf-key-otra-diferente",
    )
    assert res_conf_2.status_code == 200
    assert res_conf_2.json()["estado"] == "recibida"

    # El número de eventos NO debe duplicarse
    eventos_posteriores = EventoTrabajo.objects.filter(
        orden=orden_evidencias, tipo="evidencia_confirmada"
    ).count()
    assert eventos_posteriores == 1
