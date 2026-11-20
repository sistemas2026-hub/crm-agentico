# -*- coding: utf-8 -*-
"""
================================================================================
 EL REPORTE ENTRA ENTERO EN LA NOTA DEL TICKET  --  07/11/2026
================================================================================
El usuario, comparando los dos tickets de la OT #188:

    «mira material queda mocho»

En WispHub el reporte llegaba completo -- «...MATERIAL Y CANTIDAD CONECTOR
APC 1 Evidencias en Dexter: 4.». En Dexter terminaba en «MATERIAL Y...», o
sea que la seccion que dice QUE SE GASTO caia entera, y con ella el unico
registro de material que ve quien lee el ticket.

LA CAUSA NO ERA EL RECORTE: era la columna. `Comment.comment` era un
`CharField(max_length=255)`, y ese 255 no venia de ninguna regla del negocio
ni de un limite de un tercero -- es el default de un CharField. El recorte
hacia bien su trabajo cortando donde termina una palabra; el problema es que
tenia que cortar.

QUE AFIRMA ESTA GUARDA
----------------------
  · que un reporte real entre ENTERO, con su material -- medido sobre el
    texto de la OT #188, no sobre uno inventado corto
  · que la columna acepte de verdad mas de 255, leido de vuelta de la base:
    cambiar el modelo sin la migracion deja el error para produccion
  · y que el tope siga existiendo: sin ninguno, un reporte largo convierte un
    renglon de bitacora en una pagina
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

#:  EL TEXTO QUE EL USUARIO VIO CORTADO, tal como WispHub lo recibio entero.
#:  Se usa este y no uno inventado: un reporte corto pasa con cualquier tope,
#:  y la guarda no diria nada.
REPORTE_188 = (
    "Mario Vasquez (Dexter): Reporte de campo de la OT #188. Pendiente de "
    "revision. Potencia al llegar: -21.0 dBm Que encontro: Problema dentro "
    "de la casa Que hizo: se cambia conector APC Potencia al salir: -21.0 "
    "dBm Servicio probado con el cliente: Hecho MATERIAL Y CANTIDAD "
    "CONECTOR APC 1 Evidencias en Dexter: 4."
)


def test_el_reporte_de_la_OT_188_NO_entraba_en_el_tope_viejo():
    """La premisa de todo esto. Si fallara, el caso elegido no prueba nada."""
    assert len(REPORTE_188) > 255, len(REPORTE_188)


def test_el_reporte_entra_ENTERO_con_su_material():
    from campo.avisar_al_ticket import recortar

    salida = recortar(REPORTE_188)

    assert salida == REPORTE_188
    assert "MATERIAL Y CANTIDAD CONECTOR APC 1" in salida
    assert "…" not in salida


def test_la_COLUMNA_acepta_mas_de_255_leido_de_la_base(org_a, user_profile):
    """El modelo sin la migracion es un error que aparece en produccion."""
    from django.contrib.contenttypes.models import ContentType

    from cases.models import Case
    from common.models import Comment

    caso = Case.objects.create(org=org_a, name="Problema de TV",
                               status="New", priority="Normal")
    Comment.objects.create(
        org=org_a, comment=REPORTE_188,
        content_type=ContentType.objects.get_for_model(Case),
        object_id=caso.id, commented_by=user_profile)

    guardado = Comment.objects.get(object_id=caso.id).comment

    assert guardado == REPORTE_188, len(guardado)
    assert "MATERIAL Y CANTIDAD CONECTOR APC 1" in guardado


def test_el_tope_SIGUE_EXISTIENDO():
    """Quitarlo convierte un renglon de bitacora en una pagina."""
    from campo.avisar_al_ticket import MAX_NOTA, recortar

    largo = ("palabra " * 1000).strip()

    salida = recortar(largo)

    assert len(salida) <= MAX_NOTA
    assert salida.endswith("…")


def test_el_corte_sigue_cayendo_donde_TERMINA_una_palabra():
    """Un corte a mitad de un dato se lee como el dato completo."""
    from campo.avisar_al_ticket import recortar

    assert recortar("uno dos tres cuatro", tope=11) == "uno dos…"
