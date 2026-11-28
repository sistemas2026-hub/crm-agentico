# -*- coding: utf-8 -*-
"""
================================================================================
 LAS FOTOS DEL TECNICO SE VEN EN EL TICKET  --  07/11/2026
================================================================================
El usuario, probando la OT #186: «en dexter sale bien hasta donde dice
evidencia en... no muestra las fotos».

La nota decia «Evidencias en Dexter: 4» y quien leia el ticket tenia que irse
a buscarlas a otra pantalla. Las fotos estaban en el servidor desde que el
tecnico las subio.

QUE AFIRMA ESTA GUARDA
----------------------
  · que las fotos queden ADJUNTAS AL CASO -- el efecto, no que la funcion
    se llame
  · que cuelguen de `Attachments`, que es lo que la pantalla del ticket lista
  · que dos reportes no dejen ocho fotos repetidas, y que OTRA VUELTA si
    adjunte las nuevas
  · el tope por vuelta: un reporte no puede volver el ticket ilegible
  · que un archivo que falta no se lleve a los demas
  · y que un fallo del adjunto NO tumbe el reporte del tecnico
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


def _orden(org_a, user_profile, numero=186):
    from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)
    from cases.models import Case

    caso = Case.objects.create(org=org_a, name="Internet Lento", status="New",
                               priority="Normal", is_active=True)
    wt = WorkType.objects.create(org=org_a, codigo=f"f{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        origen_sistema="crm", origen_ref=str(caso.pk), contexto={})
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return orden, caso


def _evidencia(orden, requisito, tmp_path, vuelta=1, con_archivo=True):
    """Una evidencia con su archivo en disco, como la deja el tecnico."""
    from campo.models import EvidenciaTrabajo

    key = f"{requisito}-{vuelta}-{orden.numero}.jpg"
    if con_archivo:
        destino = tmp_path / key
        destino.write_bytes(b"\xff\xd8\xff-una-foto")
    return EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=vuelta, storage_key=key,
        nombre_original=f"IMG_2026_{requisito}.jpg",
        mime_type="image/jpeg", bytes=12,
        #  UNICO POR VUELTA: la base tiene un unique
        #  (orden, requisito, sha256) -- dos fotos iguales en
        #  vueltas distintas chocarian, y eso es correcto en
        #  produccion: la foto rehecha es otra foto.
        sha256=(f"{requisito}{vuelta}".ljust(64, "x"))[:64],
        estado_archivo=EvidenciaTrabajo.VERIFICADO)


def _adjuntos(caso):
    from common.models import Attachments

    return Attachments.objects.filter(object_id=caso.pk)


# ---------------------------------------------------------------------------
#  EL EFECTO
# ---------------------------------------------------------------------------

def test_las_fotos_QUEDAN_adjuntas_al_ticket(org_a, user_profile, tmp_path,
                                             settings):
    """LO QUE EL USUARIO NO VEIA.

    Se afirma sobre las filas que quedan colgando del caso, no sobre que
    `adjuntar` se haya llamado: la funcion puede correr entera y no escribir
    nada si el archivo no esta donde cree.
    """
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile)
    _evidencia(orden, "dano_encontrado", tmp_path)
    _evidencia(orden, "test_de_velocidad", tmp_path)

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["hecho"] is True, r
    assert r["cuantas"] == 2, r
    assert _adjuntos(caso).count() == 2


def test_el_nombre_dice_QUE_FOTO_ES(org_a, user_profile, tmp_path, settings):
    """«dano_encontrado-1.jpg», no «IMG_2026_dano_encontrado.jpg».

    Quien abre el ticket quiere saber cual foto es. El nombre que trajo el
    telefono no se lo dice.
    """
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=187)
    _evidencia(orden, "dano_encontrado", tmp_path)

    fotos_al_ticket.adjuntar(orden, profile=user_profile)

    nombre = _adjuntos(caso).first().file_name
    assert nombre.startswith("dano_encontrado"), nombre


# ---------------------------------------------------------------------------
#  IDEMPOTENCIA Y TOPE
# ---------------------------------------------------------------------------

def test_dos_reportes_NO_dejan_las_fotos_dos_veces(org_a, user_profile,
                                                   tmp_path, settings):
    """La app encola y reintenta.

    Sin esto, un reintento deja ocho fotos repetidas en el ticket -- y desde
    la pantalla no se pueden sacar.
    """
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=188)
    _evidencia(orden, "dano_encontrado", tmp_path)

    fotos_al_ticket.adjuntar(orden, profile=user_profile)
    orden.refresh_from_db()
    segunda = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert segunda["motivo"] == "ya_adjuntas", segunda
    assert _adjuntos(caso).count() == 1


def test_OTRA_VUELTA_si_adjunta_las_fotos_nuevas(org_a, user_profile,
                                                 tmp_path, settings):
    """Una orden devuelta y rehecha trae fotos NUEVAS.

    Si la marca fuera sola --sin la vuelta-- el segundo intento del tecnico
    no mostraria nada, y el ticket seguiria con las fotos que el supervisor ya
    rechazo.
    """
    from campo import fotos_al_ticket
    from campo.models import OrdenTrabajo

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=189)
    _evidencia(orden, "dano_encontrado", tmp_path, vuelta=1)
    fotos_al_ticket.adjuntar(orden, profile=user_profile)

    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=2)
    orden.refresh_from_db()
    _evidencia(orden, "dano_encontrado", tmp_path, vuelta=2)

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["hecho"] is True, r
    assert _adjuntos(caso).count() == 2


def test_hay_un_TOPE_por_vuelta(org_a, user_profile, tmp_path, settings):
    """Un reporte no puede volver el ticket ilegible.

    Las que no entran siguen estando en la orden, que es donde viven de
    verdad.
    """
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=190)
    for i in range(fotos_al_ticket.MAX_POR_VUELTA + 4):
        _evidencia(orden, f"foto_{i}", tmp_path)

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["cuantas"] == fotos_al_ticket.MAX_POR_VUELTA, r
    assert _adjuntos(caso).count() == fotos_al_ticket.MAX_POR_VUELTA


# ---------------------------------------------------------------------------
#  LO QUE PASA CUANDO ALGO SE ROMPE
# ---------------------------------------------------------------------------

def test_un_archivo_que_FALTA_no_se_lleva_a_los_demas(org_a, user_profile,
                                                      tmp_path, settings):
    """Una evidencia cuya fila existe y cuyo archivo no.

    Pasa: un disco lleno a mitad de subida, un borrado manual. La foto que si
    esta tiene que llegar igual.
    """
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=191)
    _evidencia(orden, "existe", tmp_path, con_archivo=True)
    _evidencia(orden, "no_existe", tmp_path, con_archivo=False)

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["cuantas"] == 1, r
    assert _adjuntos(caso).count() == 1


def test_sin_profile_NO_intenta_ocho_veces(org_a, user_profile, tmp_path,
                                           settings):
    """`create_attachment` escribe `created_by` y `org` desde el profile.

    Sin el, revienta DENTRO del bucle: ocho intentos, un log por foto y
    ninguna adjunta. Se corta antes y se dice cual fue el motivo.
    """
    from campo import fotos_al_ticket

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=192)
    _evidencia(orden, "dano_encontrado", tmp_path)

    with mock.patch("common.utils.create_attachment") as crear:
        r = fotos_al_ticket.adjuntar(orden, profile=None)

    assert r["motivo"] == "sin_profile", r
    assert crear.call_count == 0
    assert _adjuntos(caso).count() == 0


def test_una_orden_SIN_TICKET_no_hace_nada(org_a, user_profile, tmp_path,
                                           settings):
    """Una orden manual, que no nacio de un ticket."""
    from campo import fotos_al_ticket
    from campo.models import OrdenTrabajo

    settings.MEDIA_ROOT = str(tmp_path)
    orden, _caso = _orden(org_a, user_profile, numero=193)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        origen_sistema="manual", origen_ref="")
    orden.refresh_from_db()

    r = fotos_al_ticket.adjuntar(orden, profile=user_profile)

    assert r["motivo"] == "sin_ticket", r


def test_si_ADJUNTAR_falla_el_reporte_del_tecnico_igual_responde(
        user_client, org_a, user_profile, tmp_path, settings):
    """LA QUE IMPORTA CUANDO ALGO SE ROMPE.

    El tecnico esta parado frente a una casa. Un ticket sin las fotos es un
    problema; un boton que no contesta es uno peor -- y ademas la cola de la
    app reintentaria un reporte que YA se guardo.
    """
    from campo.models import OrdenTrabajo

    settings.MEDIA_ROOT = str(tmp_path)
    orden, _caso = _orden(org_a, user_profile, numero=194)
    #  EN_SITIO, no COMPLETADA_CAMPO: la vista transiciona, y desde el estado
    #  final no hay transicion que aplicar -- la orden quedaria sin fecha de
    #  completada_campo_en y la respuesta revienta armando el JSON.
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        estado_operativo=OrdenTrabajo.EN_SITIO)
    orden.refresh_from_db()

    with mock.patch("campo.fotos_al_ticket.adjuntar",
                    side_effect=RuntimeError("se cayo")), \
         mock.patch("campo.tasks.pedir_revision_del_cierre"), \
         mock.patch("requests.post", side_effect=RuntimeError("caido")):
        r = user_client.post(f"/api/campo/trabajos/{orden.id}/completar/",
                             {}, content_type="application/json")

    assert r.status_code in (200, 400), r.content


def test_MANDAR_EL_REPORTE_deja_las_fotos_en_el_ticket(
        user_client, org_a, user_profile, tmp_path, settings):
    """EL CAMINO ENTERO, QUE ES EL QUE EL USUARIO RECORRE.

    Las guardas de arriba miden `adjuntar` directamente. Esta mide lo que
    pasa cuando el tecnico toca el boton -- que es donde faltaba el enganche.
    Sin ella, borrar la llamada de `views.py` no rompe nada: medido el
    07/11/2026, esa mutacion sobrevivio a las nueve primeras.
    """
    from campo.models import OrdenTrabajo

    settings.MEDIA_ROOT = str(tmp_path)
    orden, caso = _orden(org_a, user_profile, numero=195)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        estado_operativo=OrdenTrabajo.EN_SITIO)
    orden.refresh_from_db()
    _evidencia(orden, "dano_encontrado", tmp_path)
    _evidencia(orden, "test_de_velocidad", tmp_path)

    #  El ISP caido a proposito: los dos caminos son independientes.
    with mock.patch("campo.tasks.pedir_revision_del_cierre"), \
         mock.patch("requests.post", side_effect=RuntimeError("caido")):
        r = user_client.post(f"/api/campo/trabajos/{orden.id}/completar/",
                             {}, content_type="application/json")

    assert r.status_code == 200, r.content
    assert _adjuntos(caso).count() == 2, [a.file_name for a in _adjuntos(caso)]
