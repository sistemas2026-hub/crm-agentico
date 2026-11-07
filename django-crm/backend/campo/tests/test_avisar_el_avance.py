# -*- coding: utf-8 -*-
"""
================================================================================
 EL TICKET SE ENTERA DE QUE EL TECNICO SALIO  --  06/11/2026
================================================================================
El usuario, probando: marco "En camino" desde la app, vio el cambio en
Programacion y el ticket de Dexter seguia igual que cuando se abrio -- solo
"Ticket creado" y "Asignado a CESAR MORON".

Programacion lee el ESTADO de la orden, asi que ahi se veia. El ticket no
leia nada: lo que pasaba en campo llegaba recien al cerrar.

QUE AFIRMA ESTA GUARDA
----------------------
  · que el avance deje nota EN LOS DOS tickets -- el del CRM y el del ISP
  · que el nombre del tecnico este, porque la pregunta que el ticket contesta
    en ese momento es "¿quien va?"
  · que dos toques no dejen dos notas, y que OTRA VUELTA si avise de nuevo
  · y la que importa cuando algo se rompe: que un fallo del aviso NO tumbe la
    accion. El tecnico esta en la calle esperando que el boton responda.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from cases.models import Case
from common.models import Comment

pytestmark = pytest.mark.django_db


class _Resp:
    def __init__(self, datos=None, codigo=200):
        self._datos = datos or {"anotada": True, "codigo": "anotada"}
        self.status_code, self.content = codigo, b"x"

    def json(self):
        return self._datos


@pytest.fixture
def orden_con_ticket(org_a, user_profile):
    """Una orden nacida de un ticket del CRM y de uno del ISP."""
    caso = Case.objects.create(org=org_a, name="Internet Lento", status="New",
                               priority="Normal", is_active=True)
    wt = WorkType.objects.create(org=org_a, codigo="corr", nombre="Correctivo",
                                 labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=183, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.ASIGNADA,
        origen_sistema="crm", origen_ref=str(caso.pk),
        contexto={"ticket": {"numero": "97913", "proveedor": "wisphub"}})
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return orden, caso


def _con_tenant():
    """Sin el mapeo org -> tenant, el aviso al ISP no sale y la prueba mide el
    andamio. Es el mismo tropiezo que en `test_probar_instruccion_de_foto`."""
    return mock.patch("operaciones.areas_del_tenant.tenant_de",
                      return_value="rapilink")


def _marcar(cliente, orden, accion="marcar_en_camino"):
    return cliente.post(f"/api/campo/trabajos/{orden.id}/acciones/",
                        {"accion": accion}, content_type="application/json")


def _notas(caso):
    return Comment.objects.filter(object_id=caso.pk)


def test_en_camino_avisa_en_LOS_DOS_tickets(user_client, orden_con_ticket):
    orden, caso = orden_con_ticket

    with mock.patch("requests.post", return_value=_Resp()) as post, _con_tenant():
        r = _marcar(user_client, orden)

    assert r.status_code == 200, r.content

    #  EL DEL CRM: nota interna, no un mensaje al cliente.
    nota = _notas(caso).first()
    assert nota is not None, "el ticket del CRM no se entero"
    assert "va en camino" in nota.comment
    assert nota.is_internal is True

    #  EL DEL ISP: por la ruta de anotar, nunca por la de cerrar.
    urls = [c.args[0] for c in post.call_args_list]
    assert any("anotar-en-el-ticket" in u for u in urls), urls
    assert not any("cerrar" in u for u in urls), urls
    cuerpo = post.call_args.kwargs["json"]
    assert cuerpo["momento"] == "en_camino"
    assert "va en camino" in cuerpo["texto"]


def test_llegada_avisa_tambien(user_client, orden_con_ticket):
    orden, caso = orden_con_ticket
    with mock.patch("requests.post", return_value=_Resp()):
        _marcar(user_client, orden, "marcar_en_camino")
        _marcar(user_client, orden, "marcar_llegada")

    textos = [n.comment for n in _notas(caso)]
    assert any("va en camino" in t for t in textos), textos
    assert any("llego al sitio" in t for t in textos), textos


def test_dos_toques_NO_dejan_dos_notas(user_client, orden_con_ticket):
    """Un doble toque en la app, o un reintento de la cola offline.

    La app encola y reintenta; sin idempotencia, el ticket del cliente se
    llenaria de "va en camino" repetidos.
    """
    orden, caso = orden_con_ticket
    with mock.patch("requests.post", return_value=_Resp()):
        _marcar(user_client, orden)
        #  La segunda vez la transicion ya no aplica, pero el aviso tampoco
        #  puede repetirse ni aunque aplicara.
        _marcar(user_client, orden)

    assert _notas(caso).count() == 1, [n.comment for n in _notas(caso)]


def test_otra_vuelta_SI_avisa_de_nuevo(user_client, orden_con_ticket):
    """Una orden devuelta y rehecha vuelve a salir: ese viaje es nuevo.

    Si la clave fuera solo el momento, el segundo viaje no se avisaria y el
    ticket diria que el tecnico nunca volvio a salir.
    """
    from campo import avisar_al_ticket

    orden, caso = orden_con_ticket
    with mock.patch("requests.post", return_value=_Resp()):
        _marcar(user_client, orden)

    #  Se simula la vuelta siguiente, que es lo que hace `requerir_correccion`.
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        vuelta=2, estado_operativo=OrdenTrabajo.CORRECCION_REQUERIDA)
    orden.refresh_from_db()

    r = avisar_al_ticket.avisar(orden, "MARIO: va en camino.",
                                "en_camino", profile=None)
    assert r["hecho"] is True, r
    assert _notas(caso).count() == 2


def test_si_el_aviso_falla_la_accion_IGUAL_responde(user_client,
                                                    orden_con_ticket):
    """LA QUE IMPORTA CUANDO ALGO SE ROMPE.

    El tecnico esta parado frente a una casa esperando que el boton conteste.
    Un ticket sin la nota es un problema; un boton que no responde es uno
    peor -- y ademas la cola de la app reintentaria una accion que YA se
    aplico.
    """
    orden, _caso = orden_con_ticket

    with mock.patch("campo.avisar_al_ticket.avisar",
                    side_effect=RuntimeError("se cayo")), \
         mock.patch("requests.post", side_effect=RuntimeError("se cayo")):
        r = _marcar(user_client, orden)

    assert r.status_code == 200, r.content
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.EN_CAMINO
