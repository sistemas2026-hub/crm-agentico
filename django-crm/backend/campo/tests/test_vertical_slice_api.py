# -*- coding: utf-8 -*-
"""Vertical Slice completa de la API de Campo: bootstrap -> detalle -> acciones -> datos -> evidencias -> completar."""

import pytest
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion


@pytest.fixture
def version_ftth_completa(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_inst", nombre="Instalación FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={
            "pasos": [{"id": "paso_tecnico", "titulo": "Parámetros Ópticos"}],
            "campos": [
                {"id": "serial_ont", "tipo": "texto", "reglas": {"required": True}},
                {"id": "potencia_rx", "tipo": "decimal", "reglas": {"required": True, "min": -28.0, "max": -8.0}},
            ],
            "evidencias": [
                {"id": "foto_ont", "titulo": "Foto ONT", "tipo": "foto", "obligatorio": True},
            ],
        },
    )


@pytest.fixture
def orden_flujo_completo(org_a, user_profile, version_ftth_completa):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=5001,
        tipo_trabajo_version=version_ftth_completa,
        cliente_nombre="Familia Restrepo",
        cliente_direccion="Transversal 12 # 45-67",
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


def test_vertical_slice_jornada_tecnico(user_client, user_profile, orden_flujo_completo):
    """Ejecuta el ciclo de vida completo de un trabajo desde la perspectiva de la app móvil."""
    orden_id = str(orden_flujo_completo.id)

    # 1. Bootstrap al abrir la app móvil
    res_boot = user_client.get("/api/campo/bootstrap/")
    assert res_boot.status_code == 200
    boot_data = res_boot.json()
    assert boot_data["usuario"]["email"] == user_profile.user.email
    assert boot_data["capacidades"]["offline"] is True

    # 2. Descargar detalle completo para trabajo offline
    res_det = user_client.get(f"/api/campo/trabajos/{orden_id}/")
    assert res_det.status_code == 200
    det_data = res_det.json()
    assert det_data["id"] == orden_id
    assert det_data["estado_operativo"] == "asignada"
    assert det_data["revision"] == 1
    assert "schema" in det_data
    assert "campos" in det_data["schema"]

    # 3. Acción: Iniciar desplazamiento (hacia la casa del cliente)
    res_acc1 = user_client.post(
        f"/api/campo/trabajos/{orden_id}/acciones/",
        {"accion": "marcar_en_camino"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-001",
    )
    assert res_acc1.status_code == 200
    assert res_acc1.json()["estado_operativo"] == "en_camino"
    assert res_acc1.json()["revision"] == 2

    # 4. Acción: Registrar llegada (geolocalización en sitio)
    res_acc2 = user_client.post(
        f"/api/campo/trabajos/{orden_id}/acciones/",
        {"accion": "marcar_llegada", "metadatos": {"lat": 4.65, "lng": -74.05}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-002",
    )
    assert res_acc2.status_code == 200
    assert res_acc2.json()["estado_operativo"] == "en_sitio"
    assert res_acc2.json()["revision"] == 3

    # 5. Guardar datos técnicos con control de concurrencia optimista
    # 5.1 Si enviamos una revision_base desactualizada con campos en conflicto, rechaza con 409
    # Primero guardamos serial_ont con revision 3
    res_d1 = user_client.patch(
        f"/api/campo/trabajos/{orden_id}/datos/",
        {"revision_base": 3, "valores": {"serial_ont": "ORIGINAL123"}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-datos-1",
    )
    assert res_d1.status_code == 200
    assert res_d1.json()["revision"] == 4

    # Ahora un técnico offline que tenía revision_base 3 intenta pisar serial_ont con otro valor
    res_datos_stale = user_client.patch(
        f"/api/campo/trabajos/{orden_id}/datos/",
        {"revision_base": 3, "valores": {"serial_ont": "CONFLICTO456"}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-datos-stale",
    )
    assert res_datos_stale.status_code == 409
    assert res_datos_stale.json()["error"] == "STALE_WORK_ORDER"

    # 5.2 Con la revision_base correcta (4), aplica los cambios
    res_datos_ok = user_client.patch(
        f"/api/campo/trabajos/{orden_id}/datos/",
        {"revision_base": 4, "valores": {"serial_ont": "HUAWEI12345", "potencia_rx": -19.5}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-datos-ok",
    )
    assert res_datos_ok.status_code == 200
    assert res_datos_ok.json()["revision"] == 5

    # 6. Subir evidencia fotográfica requerida
    # 6.1 Intentar subir una foto con un requisito_id que no existe en el esquema de la versión
    res_ev_inv = user_client.post(
        f"/api/campo/trabajos/{orden_id}/evidencias/",
        {
            "requisito_id": "foto_inventada",
            "nombre": "foto.jpg",
            "mime_type": "image/jpeg",
            "bytes": 1024,
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-005",
    )
    assert res_ev_inv.status_code == 400
    assert res_ev_inv.json()["error"] == "REQUISITO_INVALIDO"

    # 6.2 Subir con el requisito válido "foto_ont"
    res_ev_ok = user_client.post(
        f"/api/campo/trabajos/{orden_id}/evidencias/",
        {
            "requisito_id": "foto_ont",
            "nombre": "ont_instalada.jpg",
            "mime_type": "image/jpeg",
            "bytes": 2048,
            "sha256": "1111c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-006",
    )
    assert res_ev_ok.status_code == 200
    evidencia_id = res_ev_ok.json()["evidencia_id"]
    assert "upload" in res_ev_ok.json()

    # 6.3 Simular subida física al storage y confirmar
    import os
    from django.conf import settings
    from campo.models import EvidenciaTrabajo
    ev_obj = EvidenciaTrabajo.objects.get(pk=evidencia_id)
    ruta_fisica = os.path.join(settings.MEDIA_ROOT, ev_obj.storage_key)
    os.makedirs(os.path.dirname(ruta_fisica), exist_ok=True)
    with open(ruta_fisica, "wb") as f:
        f.write(b"fake image bytes")

    res_conf = user_client.post(
        f"/api/campo/evidencias/{evidencia_id}/confirmar/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-007",
    )
    assert res_conf.status_code == 200
    assert res_conf.json()["estado"] == "recibida"

    # 7. Completar trabajo de campo (cierre estricto con validación de checklist)
    res_comp = user_client.post(
        f"/api/campo/trabajos/{orden_id}/completar/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="key-vs-008",
    )
    assert res_comp.status_code == 200
    assert res_comp.json()["ok"] is True
    assert res_comp.json()["estado_operativo"] == "completada_campo"

    # 8. Comprobación del historial operativo (EventoTrabajo)
    orden_flujo_completo.refresh_from_db()
    tipos_eventos = list(orden_flujo_completo.eventos.values_list("tipo", flat=True))
    assert "accion_marcar_en_camino" in tipos_eventos
    assert "accion_marcar_llegada" in tipos_eventos
    assert "datos_actualizados" in tipos_eventos
    assert "evidencia_confirmada" in tipos_eventos
    assert "trabajo_completado_campo" in tipos_eventos
