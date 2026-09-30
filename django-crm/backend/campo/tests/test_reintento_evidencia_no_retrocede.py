# -*- coding: utf-8 -*-
"""
Un reintento nunca hace retroceder una evidencia ya recibida.

    uv run pytest campo/tests/test_reintento_evidencia_no_retrocede.py --no-cov -v

POR QUE EXISTE
--------------
El registro de evidencia hacia un 'update_or_create' cuyos defaults incluian
'estado_archivo': SUBIENDO y una storage_key NUEVA. Como la fila se identifica
por (orden, requisito_id, sha256) -- que es exactamente lo que vuelve a mandar
un movil que reintenta -- un reintento tardio encontraba la evidencia RECIBIDA
o VERIFICADA y la devolvia a SUBIENDO apuntando a una key vacia:

    * lo ya subido quedaba huerfano en el storage;
    * el checklist de la orden retrocedia solo, sin que nadie lo tocara;
    * una evidencia VERIFICADA (auditada) volvia a estar "en curso".

'manejar_idempotencia' no lo tapaba: solo actua si el cliente manda la
cabecera Idempotency-Key. Ante un corte de red un movil puede reintentar sin
ella, o con una clave nueva -- para el es otra intencion, aunque para el
servidor sea la misma. La garantia no puede depender de que el cliente
colabore, asi que estas pruebas reintentan SIN cabecera a proposito.

EL INVARIANTE
-------------
    PENDIENTE / SUBIENDO  -> puede reobtener URL de subida, sobre la MISMA key
    RECIBIDO / VERIFICADO -> nunca vuelve a SUBIENDO, ni cambia de storage_key
    en ningun caso        -> se crea una segunda EvidenciaTrabajo
"""

import os

import pytest
from django.conf import settings

from campo.models import EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo
from campo.models import AsignacionTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

SHA = "aa" * 32
CUERPO = {
    "requisito_id": "foto_ont",
    "nombre": "ont.jpg",
    "mime_type": "image/jpeg",
    "bytes": 2048,
    "sha256": SHA,
}


@pytest.fixture
def version_ev(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_retry", nombre="Instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto ONT", "tipo": "foto", "obligatorio": True}]},
    )


@pytest.fixture
def orden(org_a, user_profile, version_ev):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9101, tipo_trabajo_version=version_ev,
        cliente_nombre="Cliente Retry", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=user_profile, rol="tecnico_lider", es_principal=True)
    return o


def _registrar(client, orden, **extra):
    """POST /evidencias/ SIN Idempotency-Key: asi reintenta un movil real."""
    return client.post(
        f"/api/campo/trabajos/{orden.id}/evidencias/",
        {**CUERPO, **extra}, format="json",
    )


def _subir_archivo(evidencia):
    ruta = os.path.join(settings.MEDIA_ROOT, evidencia.storage_key)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(b"BYTES DE PRUEBA")


# --- 1. SUBIENDO + reintento: misma fila, URL renovada, misma key ----------

def test_reintento_en_subiendo_renueva_upload_sin_duplicar(user_client, orden):
    r1 = _registrar(user_client, orden)
    assert r1.status_code == 200
    id1, key1 = r1.json()["evidencia_id"], r1.json()["storage_key"]
    assert r1.json()["upload"] is not None

    r2 = _registrar(user_client, orden)
    assert r2.status_code == 200
    assert r2.json()["evidencia_id"] == id1, "un reintento no puede crear otra evidencia"
    # La URL se reemite -- es el caso de la URL firmada vencida -- pero sobre
    # la MISMA key: si cambiara, lo ya subido quedaria huerfano.
    assert r2.json()["upload"] is not None, "debe poder reobtener una URL de subida"
    assert r2.json()["storage_key"] == key1, "la storage_key no puede cambiar"

    assert EvidenciaTrabajo.objects.filter(
        orden_trabajo=orden, requisito_id="foto_ont", sha256=SHA).count() == 1


# --- 2 y 3. RECIBIDO / VERIFICADO: nunca retroceden ------------------------

@pytest.mark.parametrize("estado_terminal", [
    EvidenciaTrabajo.RECIBIDO,
    EvidenciaTrabajo.VERIFICADO,
])
def test_reintento_sobre_estado_terminal_no_retrocede(user_client, orden, estado_terminal):
    r1 = _registrar(user_client, orden)
    ev = EvidenciaTrabajo.objects.get(pk=r1.json()["evidencia_id"])
    key_original = ev.storage_key
    ev.estado_archivo = estado_terminal
    ev.save(update_fields=["estado_archivo"])

    r2 = _registrar(user_client, orden)
    assert r2.status_code == 200
    assert r2.json()["evidencia_id"] == str(ev.id)

    ev.refresh_from_db()
    assert ev.estado_archivo == estado_terminal, (
        f"volvio a '{ev.estado_archivo}': una evidencia ya en el servidor no "
        f"puede regresar a SUBIENDO")
    assert ev.storage_key == key_original, "no se puede reemplazar la storage_key"
    # Y no se entrega URL de subida: seria la forma de reemplazar una
    # evidencia ya aceptada, o auditada si esta verificada.
    assert r2.json()["upload"] is None
    assert EvidenciaTrabajo.objects.filter(
        orden_trabajo=orden, requisito_id="foto_ont", sha256=SHA).count() == 1


# --- 4. Reintento de /confirmar/: 200 y un solo EventoTrabajo -------------

def test_reintento_de_confirmar_no_duplica_evento(user_client, orden):
    r1 = _registrar(user_client, orden)
    ev = EvidenciaTrabajo.objects.get(pk=r1.json()["evidencia_id"])
    _subir_archivo(ev)

    url = f"/api/campo/evidencias/{ev.id}/confirmar/"
    assert user_client.post(url, {}, format="json").status_code == 200
    # Sin Idempotency-Key en ninguno de los dos: el corte de red no garantiza
    # que el movil reintente con la misma clave.
    assert user_client.post(url, {}, format="json").status_code == 200

    assert EventoTrabajo.objects.filter(
        orden=orden, tipo="evidencia_confirmada").count() == 1
    ev.refresh_from_db()
    assert ev.estado_archivo == EvidenciaTrabajo.RECIBIDO


def test_confirmar_y_despues_reintentar_el_registro_no_deshace_la_confirmacion(user_client, orden):
    """El circuito completo del bug, de punta a punta.

    Es el orden real que rompia: subir, confirmar, y recien despues llega el
    reintento que se habia quedado esperando en la cola del telefono.
    """
    r1 = _registrar(user_client, orden)
    ev = EvidenciaTrabajo.objects.get(pk=r1.json()["evidencia_id"])
    _subir_archivo(ev)
    user_client.post(f"/api/campo/evidencias/{ev.id}/confirmar/", {}, format="json")

    r_tardio = _registrar(user_client, orden)

    ev.refresh_from_db()
    assert r_tardio.json()["evidencia_id"] == str(ev.id)
    assert ev.estado_archivo == EvidenciaTrabajo.RECIBIDO
    assert EventoTrabajo.objects.filter(
        orden=orden, tipo="evidencia_confirmada").count() == 1


# --- 5. Misma Idempotency-Key con payload distinto -> 409 -----------------

def test_misma_clave_con_payload_distinto_da_409(user_client, orden):
    url = f"/api/campo/trabajos/{orden.id}/evidencias/"
    r1 = user_client.post(url, CUERPO, format="json", HTTP_IDEMPOTENCY_KEY="k-1")
    assert r1.status_code == 200

    r2 = user_client.post(url, {**CUERPO, "bytes": 4096}, format="json",
                          HTTP_IDEMPOTENCY_KEY="k-1")
    assert r2.status_code == 409
    assert r2.json()["error"] == "IDEMPOTENCY_KEY_REUSED"


def test_misma_clave_mismo_payload_devuelve_la_respuesta_guardada(user_client, orden):
    url = f"/api/campo/trabajos/{orden.id}/evidencias/"
    r1 = user_client.post(url, CUERPO, format="json", HTTP_IDEMPOTENCY_KEY="k-2")
    r2 = user_client.post(url, CUERPO, format="json", HTTP_IDEMPOTENCY_KEY="k-2")
    assert r2.status_code == 200
    assert r2.json()["evidencia_id"] == r1.json()["evidencia_id"]
    assert r2.headers.get("Idempotent-Replay") == "true"
    assert EvidenciaTrabajo.objects.filter(orden_trabajo=orden).count() == 1


# --- 6. Aislamiento entre tenants: 404, tambien en lo nuevo ---------------

def test_cross_tenant_404_en_registro_y_confirmacion(org_b_client, user_client, orden):
    r1 = _registrar(user_client, orden)
    ev_id = r1.json()["evidencia_id"]

    assert org_b_client.post(
        f"/api/campo/trabajos/{orden.id}/evidencias/", CUERPO, format="json"
    ).status_code == 404, "otro tenant no puede registrar evidencia en esta orden"

    assert org_b_client.post(
        f"/api/campo/evidencias/{ev_id}/confirmar/", {}, format="json"
    ).status_code == 404, "ni confirmar una evidencia ajena"

    assert org_b_client.get(
        f"/api/campo/evidencias/{ev_id}/url/"
    ).status_code == 404, "ni obtener su URL"

    assert EvidenciaTrabajo.objects.filter(orden_trabajo=orden).count() == 1
