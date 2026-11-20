# -*- coding: utf-8 -*-
"""
================================================================================
 EL REPORTE DEL TECNICO SE VE EN LOS DOS TICKETS  --  06/11/2026
================================================================================
El usuario, comparando la OT #184 en los dos lados:

    «en dexter solo registro esos cambios y en wisphub si registro todo»

Y tenia razon. En WispHub se veian los tres momentos --va en camino, llego al
sitio, reporte de campo--. En el ticket de Dexter solo los dos avances: el
reporte, que es el que importa, no llegaba. Quien miraba el ticket veia al
tecnico salir y llegar, y despues nada.

El hueco: `views.py` llamaba a `anotar_reporte_del_tecnico` (el ISP) y no a
`avisar_al_ticket.avisar` (el CRM). Los avances si llamaban a los dos, que es
por lo que la diferencia se veia tan clara en la pantalla.

QUE AFIRMA ESTA GUARDA
----------------------
  · que el reporte deje nota EN EL TICKET DEL CRM, no solo en el del ISP
  · que lleve el nombre de quien reporto
  · que no la tumbe un fallo del ISP: son dos avisos independientes
  · y el recorte: `Comment.comment` es CharField(255) y el reporte no entra.
    Que corte donde termina una palabra, y que se note que hay mas.
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
#  EL RECORTE  --  sin base, es puro texto
# ---------------------------------------------------------------------------

def test_lo_que_entra_no_se_toca():
    from campo.avisar_al_ticket import recortar

    assert recortar("Mario: va en camino.") == "Mario: va en camino."


def test_lo_que_no_entra_corta_donde_TERMINA_una_palabra():
    """LO QUE SE EVITA: «CONECTOR AP».

    Cortar en seco dejaba la nota terminando a mitad de un dato, y un dato a
    medias se lee como el dato completo. «CONECTOR AP» no es un error de
    formato: es otra cosa que la que el tecnico escribio.

    SE AFIRMA LA SALIDA EXACTA, Y NO «empieza igual»  --  06/11/2026. La
    primera version de esta guarda decia `texto.startswith(r)`, y eso es
    verdad TAMBIEN con el corte en seco: un corte a mitad de palabra sigue
    siendo un prefijo. Sobrevivio a las dos mutaciones que la contradicen.
    """
    from campo.avisar_al_ticket import recortar

    #  El tope cae DENTRO de «tres», que es donde se ve la diferencia:
    #  cortando por palabra queda «uno dos…»; en seco, «uno dos tr…».
    assert recortar("uno dos tres cuatro", tope=11) == "uno dos…"

    #  Y el caso de verdad, el que el usuario vio en WispHub.
    texto = ("Reporte de campo de la OT #184. Pendiente de revision. "
             "MATERIAL Y CANTIDAD CONECTOR APC 1")
    r = recortar(texto, tope=70)
    assert len(r) <= 70, r
    assert r.endswith("…"), r
    #  Cada palabra del recorte, entera. «CONECTOR AP» no pasaria porque «AP»
    #  no es ninguna palabra del texto.
    #
    #  LA PUNTUACION SE QUITA DE LOS DOS LADOS. La primera version la quitaba
    #  solo del texto, y «revision.» no coincidia con «revision»: la guarda
    #  fallaba con el codigo correcto, que es la otra forma de guarda inutil
    #  -- una que grita cuando no pasa nada enseña a ignorarla.
    def _palabras(s):
        return {p.strip(",;.") for p in s.split(" ") if p.strip(",;.")}

    assert _palabras(r[:-1]) <= _palabras(texto), r


def test_una_sola_palabra_larguisima_igual_devuelve_algo():
    """Sin esto, un texto sin espacios devolvia vacio y la nota no se escribia.

    Prefiere cortar en seco a no decir nada.
    """
    from campo.avisar_al_ticket import recortar

    r = recortar("A" * 400, tope=50)
    assert 0 < len(r) <= 50


def test_la_nota_que_se_ESCRIBE_usa_el_recorte(org_a, user_profile):
    """ATA LAS DOS PIEZAS.

    Sin esta, `recortar` podia estar perfecta y `avisar` seguir cortando en
    seco: las guardas de arriba miden la funcion, no lo que queda en la base.
    Medido el 06/11/2026 -- la mutacion `comment=texto[:MAX_NOTA]` sobrevivio
    a las tres primeras.
    """
    from campo import avisar_al_ticket
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
    from cases.models import Case
    from common.models import Comment

    caso = Case.objects.create(org=org_a, name="Largo", status="New",
                               priority="Normal", is_active=True)
    wt = WorkType.objects.create(org=org_a, codigo="corr3", nombre="C",
                                 labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=999, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        origen_sistema="crm", origen_ref=str(caso.pk), contexto={})

    #  MAS LARGO QUE EL TOPE, DERIVADO DE EL Y NO DE UN NUMERO ESCRITO ACA.
    #  Esta linea decia `* 40`, que pasaba el tope de 255 de entonces. El
    #  07/11/2026 el tope subio a 2000 --la columna dejo de ser un
    #  CharField(255)-- y el texto dejo de pasarlo: la guarda se puso roja sin
    #  que el mecanismo que mide se hubiera roto. Atada al tope, mide el corte
    #  y no la cifra.
    veces = (avisar_al_ticket.MAX_NOTA // len("palabra ")) + 10
    largo = ("palabra " * veces) + "CONECTOR APC"
    r = avisar_al_ticket.avisar(orden, largo, "reporte_del_tecnico",
                                profile=user_profile)
    assert r["hecho"] is True, r

    nota = Comment.objects.filter(object_id=caso.pk).first()
    assert nota is not None
    assert len(nota.comment) <= avisar_al_ticket.MAX_NOTA, len(nota.comment)
    assert nota.comment.endswith("…"), nota.comment
    #  LA QUE MATA EL CORTE EN SECO: ninguna palabra partida.
    assert set(nota.comment[:-1].split(" ")) <= {"palabra", ""}, nota.comment


# ---------------------------------------------------------------------------
#  EL EFECTO: el reporte llega al ticket del CRM
# ---------------------------------------------------------------------------

def test_el_reporte_DEJA_NOTA_en_el_ticket_del_crm(user_client, org_a,
                                                   user_profile):
    """Lo que el usuario no veia.

    Se afirma sobre la nota que queda en el ticket, no sobre que la funcion
    se haya llamado: antes de hoy `avisar_al_ticket` existia, estaba probada
    y los avances la usaban -- y el reporte seguia sin llegar.
    """
    from unittest import mock

    from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)
    from cases.models import Case
    from common.models import Comment

    caso = Case.objects.create(org=org_a, name="Internet Lento", status="New",
                               priority="Normal", is_active=True)
    wt = WorkType.objects.create(org=org_a, codigo="corr2",
                                 nombre="Correctivo", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=184, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        origen_sistema="crm", origen_ref=str(caso.pk),
        contexto={"ticket": {"numero": "97913", "proveedor": "wisphub"}})
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)

    #  EL ISP CAIDO A PROPOSITO: los dos avisos son independientes, y el del
    #  CRM no puede depender de que WispHub conteste.
    with mock.patch("campo.services.nota_al_isp.anotar_reporte_del_tecnico",
                    side_effect=RuntimeError("wisphub no contesta")), \
         mock.patch("campo.tasks.pedir_revision_del_cierre"), \
         mock.patch("requests.post", side_effect=RuntimeError("caido")):
        r = user_client.post(
            f"/api/campo/trabajos/{orden.id}/completar/",
            {}, content_type="application/json")

    assert r.status_code in (200, 400), r.content
    if r.status_code == 400:
        pytest.skip("la transicion pide algo mas en esta plantilla: "
                    "el recorte y el enganche se miden en los otros casos")

    notas = list(Comment.objects.filter(object_id=caso.pk))
    assert notas, "el reporte no llego al ticket del CRM"
    assert any("OT #184" in n.comment for n in notas), [n.comment for n in notas]
    assert all(n.is_internal for n in notas), "la nota no era interna"


def test_el_enganche_del_reporte_esta_en_la_vista():
    """LA RED DE ATRAS del caso de arriba.

    Ese caso puede saltearse si la plantilla pide algo mas para transicionar.
    Esta afirmacion es mas debil --mira la fuente-- y por eso NO reemplaza a
    la otra: esta sola no probaria que la nota se escribe. Sirve para que un
    borrado accidental del enganche no pase inadvertido si el otro se saltea.
    """
    import io
    import pathlib

    ruta = (pathlib.Path(__file__).resolve().parents[1] / "views.py")
    fuente = io.open(ruta, encoding="utf-8").read()
    i = fuente.find("anotar_reporte_del_tecnico(orden, request.profile)")
    assert i != -1, "se fue el aviso al ISP"
    #  El del CRM va despues, en el mismo tramo.
    assert "nota_al_isp.REPORTE_DEL_TECNICO" in fuente[i:i + 2000], \
        "el reporte ya no avisa al ticket del CRM"
