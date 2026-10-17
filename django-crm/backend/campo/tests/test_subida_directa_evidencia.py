# -*- coding: utf-8 -*-
"""
El circuito completo de una evidencia, de punta a punta.

    uv run pytest campo/tests/test_subida_directa_evidencia.py --no-cov -v

    registrar -> PUT del binario -> confirmar -> RECIBIDO

POR QUE EXISTE
--------------
El paso del medio no existia. 'CampoStorage' prometia un PUT contra
'/api/campo/evidencias/upload-directo/?key=<storage_key>' y esa ruta no estaba
registrada en ningun lado: la app registraba la evidencia, recibia una URL de
subida y no tenia donde subir el archivo. El circuito quedaba cortado
exactamente en el medio, y 'confirmar' fallaba con ARCHIVO_NO_ENCONTRADO
porque nada habia podido escribir nunca.

LA FORMA IMPORTA
----------------
La URL se indexa por EVIDENCIA, no por la storage_key. La version anterior
llevaba la ruta en la query string, o sea que le pedia al servidor escribir
donde dijera el cliente -- con el path traversal como problema a resolver
despues. Con el id, la key la resuelve el servidor leyendo la fila: no hay
ruta que sanear porque no hay ruta que el cliente pueda proponer. Por eso el
test de traversal de aca abajo comprueba que la ruta con '../' ni siquiera
resuelve a esta vista, no que la vista la rechace.
"""

import os

import pytest
from django.conf import settings

from campo.models import (AsignacionTrabajo, EventoTrabajo, EvidenciaTrabajo,
                          OrdenTrabajo, WorkType, WorkTypeVersion)
from campo.services.storage import CampoStorage

pytestmark = pytest.mark.django_db

SHA = "ee" * 32
CUERPO = {
    "requisito_id": "foto_ont",
    "nombre": "ont.jpg",
    "mime_type": "image/jpeg",
    "bytes": 15,
    "sha256": SHA,
}
BINARIO = b"BYTES DE LA FOTO"


@pytest.fixture
def version_sd(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_sd", nombre="Instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto ONT", "tipo": "foto", "obligatorio": True}]},
    )


@pytest.fixture
def orden_sd(org_a, user_profile, version_sd):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9801, tipo_trabajo_version=version_sd,
        cliente_nombre="Cliente Subida", cliente_direccion="Calle 5",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=user_profile, rol="tecnico_lider", es_principal=True)
    return o


def _registrar(client, orden, **extra):
    return client.post(f"/api/campo/trabajos/{orden.id}/evidencias/",
                       {**CUERPO, **extra}, format="json")


# --- el circuito completo, que es la razon de todo esto -------------------

def test_circuito_registrar_subir_confirmar(user_client, orden_sd):
    reg = _registrar(user_client, orden_sd)
    assert reg.status_code == 200
    ev_id = reg.json()["evidencia_id"]

    # La URL que entrega el backend se usa TAL CUAL: es lo unico que la app
    # conoce. Si esta prueba tuviera que construirla a mano, no estaria
    # probando el contrato.
    url_subida = reg.json()["upload"]["url"]
    assert reg.json()["upload"]["method"] == "PUT"

    subida = user_client.put(url_subida, BINARIO, content_type="image/jpeg")
    assert subida.status_code == 200, subida.content
    assert subida.json()["bytes"] == len(BINARIO)

    ev = EvidenciaTrabajo.objects.get(pk=ev_id)
    assert CampoStorage.verify_upload(ev.storage_key), (
        "el archivo no quedo donde verify_upload lo busca: confirmar iba a fallar")

    conf = user_client.post(f"/api/campo/evidencias/{ev_id}/confirmar/", {}, format="json")
    assert conf.status_code == 200
    ev.refresh_from_db()
    assert ev.estado_archivo == EvidenciaTrabajo.RECIBIDO

    with open(os.path.join(settings.MEDIA_ROOT, ev.storage_key), "rb") as f:
        assert f.read() == BINARIO, "se guardo algo distinto de lo que se subio"


# --- lo que NO puede pasar ------------------------------------------------

def test_evidencia_inexistente_da_404(user_client, orden_sd):
    inexistente = "00000000-0000-0000-0000-000000000000"
    r = user_client.put(f"/api/campo/evidencias/{inexistente}/subir/",
                        BINARIO, content_type="image/jpeg")
    assert r.status_code == 404


def test_evidencia_de_otro_tenant_da_404(org_b_client, user_client, orden_sd):
    ev_id = _registrar(user_client, orden_sd).json()["evidencia_id"]
    r = org_b_client.put(f"/api/campo/evidencias/{ev_id}/subir/",
                         BINARIO, content_type="image/jpeg")
    assert r.status_code == 404, "otro tenant no puede escribir sobre esta evidencia"

    ev = EvidenciaTrabajo.objects.get(pk=ev_id)
    assert not CampoStorage.verify_upload(ev.storage_key), "igual le escribio el archivo"


def test_path_traversal_no_tiene_donde_entrar(user_client, orden_sd):
    """No se prueba que la vista rechace '../': se prueba que no hay por donde.

    La ruta espera un uid; una clave con separadores no resuelve a esta vista,
    asi que el intento muere en el enrutador. Es la diferencia entre validar
    una ruta peligrosa y no aceptar rutas.
    """
    for intento in ("../../etc/passwd", "campo/../../secreto.txt", "..%2f..%2fx"):
        r = user_client.put(f"/api/campo/evidencias/{intento}/subir/",
                            BINARIO, content_type="image/jpeg")
        assert r.status_code in (404, 301), f"'{intento}' respondio {r.status_code}"

    # Y la capa de storage tampoco escribiria fuera del arbol de medios si una
    # fila llegara con una key asi -- defensa en profundidad.
    assert CampoStorage.ruta_absoluta("../../fuera.txt") is None
    assert CampoStorage.guardar("../../fuera.txt", b"x") is False


@pytest.mark.parametrize("estado_terminal", [
    EvidenciaTrabajo.RECIBIDO,
    EvidenciaTrabajo.VERIFICADO,
])
def test_no_se_reemplaza_una_evidencia_ya_en_el_servidor(user_client, orden_sd, estado_terminal):
    ev_id = _registrar(user_client, orden_sd).json()["evidencia_id"]
    ev = EvidenciaTrabajo.objects.get(pk=ev_id)
    user_client.put(f"/api/campo/evidencias/{ev_id}/subir/", BINARIO, content_type="image/jpeg")
    ev.estado_archivo = estado_terminal
    ev.save(update_fields=["estado_archivo"])

    r = user_client.put(f"/api/campo/evidencias/{ev_id}/subir/",
                        b"CONTENIDO SUPLANTADO", content_type="image/jpeg")
    assert r.status_code == 409
    assert r.json()["error"] == "EVIDENCIA_NO_MODIFICABLE"

    with open(os.path.join(settings.MEDIA_ROOT, ev.storage_key), "rb") as f:
        assert f.read() == BINARIO, "le reemplazaron el archivo a una evidencia ya aceptada"
    ev.refresh_from_db()
    assert ev.estado_archivo == estado_terminal


def test_archivo_demasiado_grande_se_rechaza(user_client, orden_sd, monkeypatch):
    monkeypatch.setattr(CampoStorage, "MAX_BYTES", 10)
    ev_id = _registrar(user_client, orden_sd).json()["evidencia_id"]
    r = user_client.put(f"/api/campo/evidencias/{ev_id}/subir/",
                        b"x" * 50, content_type="image/jpeg")
    assert r.status_code == 413
    assert r.json()["error"] == "ARCHIVO_DEMASIADO_GRANDE"

    ev = EvidenciaTrabajo.objects.get(pk=ev_id)
    assert not CampoStorage.verify_upload(ev.storage_key), "lo guardo igual"


def test_mime_no_permitido_se_rechaza(user_client, orden_sd):
    ev_id = _registrar(user_client, orden_sd,
                       mime_type="application/x-msdownload").json()["evidencia_id"]
    r = user_client.put(f"/api/campo/evidencias/{ev_id}/subir/",
                        b"MZ ejecutable", content_type="application/octet-stream")
    assert r.status_code == 400
    assert r.json()["error"] == "MIME_NO_PERMITIDO"

    ev = EvidenciaTrabajo.objects.get(pk=ev_id)
    assert not CampoStorage.verify_upload(ev.storage_key)


def test_cuerpo_vacio_se_rechaza(user_client, orden_sd):
    ev_id = _registrar(user_client, orden_sd).json()["evidencia_id"]
    r = user_client.put(f"/api/campo/evidencias/{ev_id}/subir/", b"", content_type="image/jpeg")
    assert r.status_code == 400
    assert r.json()["error"] == "CUERPO_VACIO"


# --- reintentos ------------------------------------------------------------

def test_reintento_del_put_no_duplica_evidencia(user_client, orden_sd):
    ev_id = _registrar(user_client, orden_sd).json()["evidencia_id"]
    for _ in range(3):
        r = user_client.put(f"/api/campo/evidencias/{ev_id}/subir/",
                            BINARIO, content_type="image/jpeg")
        assert r.status_code == 200
        assert r.json()["evidencia_id"] == ev_id

    assert EvidenciaTrabajo.objects.filter(orden_trabajo=orden_sd).count() == 1
    conf = user_client.post(f"/api/campo/evidencias/{ev_id}/confirmar/", {}, format="json")
    assert conf.status_code == 200
    assert EventoTrabajo.objects.filter(
        orden=orden_sd, tipo="evidencia_confirmada").count() == 1


def test_en_produccion_la_ruta_no_existe(user_client, orden_sd, settings):  # noqa: F811
    """Con ENV_TYPE de produccion la subida local no participa: 404, no 403.

    Alli 'descriptor_subida' emitiria la URL prefirmada del proveedor. Quien no
    deberia usar esta ruta tampoco tiene por que enterarse de que existe.
    """
    ev_id = _registrar(user_client, orden_sd).json()["evidencia_id"]
    settings.IS_DEV_ENV = False
    r = user_client.put(f"/api/campo/evidencias/{ev_id}/subir/",
                        BINARIO, content_type="image/jpeg")
    assert r.status_code == 404
