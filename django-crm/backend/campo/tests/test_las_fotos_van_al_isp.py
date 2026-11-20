# -*- coding: utf-8 -*-
"""
================================================================================
 LAS FOTOS DEL TECNICO VIAJAN CON EL REPORTE AL TICKET DEL ISP  --  07/11/2026
================================================================================
El usuario: las fotos se ven en el ticket de Dexter y no en el de WispHub, y
su equipo mira los dos.

VAN EN LA MISMA RESPUESTA QUE EL REPORTE. Medido contra produccion ese dia
(ticket 97918, servicio de prueba 5832): WispHub acepta varios `archivo` en
una sola llamada. Una por foto habria sido seis respuestas y seis escrituras
de estado sobre el ticket de un cliente, porque `ticket-estado` es
obligatorio en ese endpoint.

QUE AFIRMA ESTA GUARDA
----------------------
  · que las fotos SALGAN con el reporte, en el mismo cuerpo -- el efecto, no
    que la funcion exista
  · que se llamen IGUAL que en Dexter: cruzar los dos tickets es lo que el
    equipo hace, y dos nombres distintos lo vuelven adivinanza
  · que solo vaya la vuelta que corre
  · que una foto que no esta en disco no tumbe el reporte
  · y que una orden sin fotos mande una lista vacia, no un error

Lo que CADA foto puede pesar o ser lo acota el motor
(`tests/test_fotos_en_la_nota.py`), que es quien le habla al proveedor. Aca
se afirma que salen y con que nombre.
================================================================================
"""
from __future__ import annotations

import base64
from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

JPG = b"\xff\xd8\xff\xe0 no es un jpg real, pero son bytes"


def _orden_con_ticket(org, numero=801):
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org, codigo=f"isp{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        origen_sistema="wisphub", origen_ref="97918",
        #  LA FORMA QUE EL PRODUCTOR ESCRIBE, no una inventada: el dict
        #  que arma `despacho._ticket_del_proveedor`, con 'numero'. La
        #  primera version uso 'id' y `anotar_reporte_del_tecnico` salio por
        #  "sin_ticket" sin llamar a nadie -- la guarda del EFECTO lo caza,
        #  la de la funcion sola no lo habria visto.
        #
        #  Es el mismo error que origino `numero_de_ticket` el 05/11/2026:
        #  las suites del cierre construian `contexto={"ticket": "94721"}` y
        #  produccion guardaba un dict, asi que nadie vio que al motor
        #  viajaba el `repr` del diccionario.
        contexto={"ticket": {"numero": "97918", "proveedor": "wisphub"}})


def _evidencia(orden, requisito, *, vuelta=None, tmp_path=None, escribir=True):
    from campo.models import EvidenciaTrabajo

    vuelta = orden.vuelta if vuelta is None else vuelta
    clave = f"{orden.numero}/{requisito}-v{vuelta}.jpg"
    if escribir and tmp_path is not None:
        destino = tmp_path / clave.replace("/", "_")
        destino.write_bytes(JPG)
        ruta = str(destino)
    else:
        ruta = ""
    ev = EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=vuelta, storage_key=clave,
        nombre_original=f"IMG_{requisito}.jpg", mime_type="image/jpeg",
        bytes=len(JPG),
        sha256=f"{requisito}{vuelta}{orden.numero}".ljust(64, "x")[:64],
        estado_archivo=EvidenciaTrabajo.VERIFICADO)
    ev._ruta_falsa = ruta
    return ev


def _con_storage(mapa):
    """`CampoStorage.ruta_absoluta` resuelto desde un mapa, sin tocar disco
    de verdad mas alla de los archivos que la prueba escribio."""
    from campo.services import storage

    return mock.patch.object(storage.CampoStorage, "ruta_absoluta",
                             staticmethod(lambda k: mapa.get(k, "")))


# ---------------------------------------------------------------------------
#  LO QUE SALE
# ---------------------------------------------------------------------------

def test_las_fotos_SALEN_con_el_reporte(org_a, tmp_path):
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 801)
    a = _evidencia(orden, "dano_encontrado", tmp_path=tmp_path)
    b = _evidencia(orden, "medicion_al_salir", tmp_path=tmp_path)
    mapa = {a.storage_key: a._ruta_falsa, b.storage_key: b._ruta_falsa}

    with _con_storage(mapa):
        fotos = nota_al_isp.fotos_de_la_vuelta(orden)

    assert len(fotos) == 2, fotos
    assert base64.b64decode(fotos[0]["base64"]) == JPG
    assert all(f["tipo"] == "image/jpeg" for f in fotos), fotos


def test_se_llaman_IGUAL_que_en_dexter(org_a, tmp_path):
    """Cruzar los dos tickets es lo que el equipo hace."""
    from campo.fotos_al_ticket import _nombre
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 802)
    a = _evidencia(orden, "dano_encontrado", tmp_path=tmp_path)

    with _con_storage({a.storage_key: a._ruta_falsa}):
        fotos = nota_al_isp.fotos_de_la_vuelta(orden)

    assert fotos[0]["nombre"] == _nombre(a, 1), fotos[0]["nombre"]
    assert fotos[0]["nombre"].startswith("dano_encontrado"), fotos[0]["nombre"]


def test_el_CUERPO_que_se_manda_al_motor_las_lleva(org_a, tmp_path):
    """EL EFECTO. Que `fotos_de_la_vuelta` acierte no prueba que alguien la
    llame: hasta hoy nadie lo hacia."""
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 803)
    a = _evidencia(orden, "dano_encontrado", tmp_path=tmp_path)
    capturado = {}

    def _pedir_falso(orden_, cuerpo, profile=None):
        capturado.update(cuerpo)
        return {"anotada": True, "codigo": "anotada"}

    with _con_storage({a.storage_key: a._ruta_falsa}), \
            mock.patch.object(nota_al_isp, "_pedir", _pedir_falso):
        nota_al_isp.anotar_reporte_del_tecnico(orden)

    assert "fotos" in capturado, sorted(capturado)
    assert len(capturado["fotos"]) == 1, capturado["fotos"]
    assert capturado["fotos"][0]["nombre"].startswith("dano_encontrado")


# ---------------------------------------------------------------------------
#  LO QUE NO SALE
# ---------------------------------------------------------------------------

def test_solo_la_VUELTA_que_corre(org_a, tmp_path):
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 804)
    orden.vuelta = 2
    orden.save(update_fields=["vuelta"])
    vieja = _evidencia(orden, "dano_encontrado", vuelta=1, tmp_path=tmp_path)
    nueva = _evidencia(orden, "dano_encontrado", vuelta=2, tmp_path=tmp_path)
    mapa = {vieja.storage_key: vieja._ruta_falsa,
            nueva.storage_key: nueva._ruta_falsa}

    with _con_storage(mapa):
        fotos = nota_al_isp.fotos_de_la_vuelta(orden)

    assert len(fotos) == 1, fotos
    assert "v2" in nueva.storage_key


def test_una_foto_que_NO_ESTA_EN_DISCO_no_tumba_el_reporte(org_a, tmp_path):
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 805)
    buena = _evidencia(orden, "dano_encontrado", tmp_path=tmp_path)
    _evidencia(orden, "medicion_al_salir", escribir=False)

    with _con_storage({buena.storage_key: buena._ruta_falsa}):
        fotos = nota_al_isp.fotos_de_la_vuelta(orden)

    assert len(fotos) == 1, fotos
    assert fotos[0]["nombre"].startswith("dano_encontrado")


def test_una_orden_SIN_FOTOS_manda_una_lista_vacia(org_a):
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 806)

    with _con_storage({}):
        assert nota_al_isp.fotos_de_la_vuelta(orden) == []


def test_no_se_leen_mas_del_TOPE(org_a, tmp_path):
    """El de aca es para no leer de mas del disco; el que decide que viaja
    vive en el motor. Dos topes del mismo numero, a proposito."""
    from campo.fotos_al_ticket import MAX_POR_VUELTA
    from campo.services import nota_al_isp

    orden = _orden_con_ticket(org_a, 807)
    mapa = {}
    for i in range(MAX_POR_VUELTA + 3):
        ev = _evidencia(orden, f"req_{i}", tmp_path=tmp_path)
        mapa[ev.storage_key] = ev._ruta_falsa

    with _con_storage(mapa):
        fotos = nota_al_isp.fotos_de_la_vuelta(orden)

    assert len(fotos) == MAX_POR_VUELTA, len(fotos)
