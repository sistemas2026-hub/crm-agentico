# -*- coding: utf-8 -*-
"""
================================================================================
 EL TOPE NO PUEDE ESCONDER TRABAJO SIN REVISAR
================================================================================

EL DEFECTO, MEDIDO EN PRODUCCION EL 06/10/2026
-----------------------------------------------
La pantalla decia «Pendientes por revisión: 0» con diez casos abiertos
esperando una decision. El unico rastro visible era el rotulo «Todas (200)».

Reconstruido contra la base:

    propuestas de la organizacion ............ 260
    tope de la respuesta ..................... 200
    orden del modelo ......................... ("prioridad", "-created_at")

    las 10 que esperaban decision caian en las posiciones 211 a 225
    (prioridad 32 a 40) y NO llegaban al navegador.

Ninguna de las dos piezas estaba mal por separado. Juntas, si: urgencia y
"espera una decision" son cosas distintas, y una propuesta YA aceptada con
prioridad 1 desplazaba a una pendiente con prioridad 40. El frontend pide la
lista entera y clasifica despues, asi que lo que el backend recorta la
pantalla no lo puede recuperar -- ni sabe que falta.

QUE SE ARREGLO
--------------
El orden pone primero lo que espera decision; dentro de cada grupo manda la
misma urgencia de siempre. El tope sigue existiendo: lo que cambia es que solo
puede recortar lo YA revisado. Y la respuesta ahora dice 'truncado', para que
una lista parcial no se lea como completa.

NO se cambio que es "pendiente", no se oculto nada y no se toco el detector.

QUE SE AFIRMA, Y POR QUE ASI
-----------------------------
Sobre el EFECTO: que con mas propuestas que el tope, las pendientes SIGAN
llegando. Una prueba que mirara el 'order_by' pasaria igual el dia que alguien
cambie el tope, el orden del modelo o la forma de la consulta.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from conftest import rls_org
from operaciones.models import PropuestaSupervisor
from operaciones.views import LOTE_MAXIMO

pytestmark = pytest.mark.django_db

RUTA = "/api/operaciones/propuestas/"


def _caso(org, *, cerrado: bool):
    """Un caso de la organizacion, terminado o abierto."""
    from cases.models import Case

    return Case.objects.create(
        org=org,
        name="caso de prueba",
        status="Closed" if cerrado else "New",
        resolved_at=timezone.now() if cerrado else None,
    )


def _propuesta(org, caso, *, estado, prioridad):
    """Una propuesta valida: la evidencia la exige una restriccion de la base."""
    return PropuestaSupervisor.objects.create(
        org=org,
        tipo_senal=PropuestaSupervisor.CASO_ANTIGUO,
        origen_tipo="case",
        origen_id=str(caso.id),
        accion_propuesta="Revisar y priorizar este caso",
        motivo="Lleva mas de 7 dias abierto.",
        evidencia=[{
            "fuente": "cases.Case",
            "id": str(caso.id),
            "dato": "abierto hace 9 dias",
            "observado_en": timezone.now().isoformat(),
        }],
        prioridad=prioridad,
        impacto="No aparece en ninguna cola de trabajo",
        huella_condicion="huella-" + uuid.uuid4().hex[:10],
        expira_en=timezone.now() + timezone.timedelta(days=7),
        estado=estado,
    )


def test_las_pendientes_llegan_aunque_el_tope_recorte(org_a, admin_client,
                                                      admin_profile):
    """
    LA REPRODUCCION DEL DEFECTO.

    Mismo reparto que habia en produccion: muchas YA revisadas con prioridad
    baja (= las mas urgentes) y unas pocas pendientes con prioridad alta. Con
    el orden anterior, las pendientes caian fuera del tope y la pantalla decia
    cero.
    """
    with rls_org(org_a):
        cerrado = _caso(org_a, cerrado=True)
        abierto = _caso(org_a, cerrado=False)
        for _ in range(LOTE_MAXIMO + 5):
            _propuesta(org_a, cerrado,
                       estado=PropuestaSupervisor.ACEPTADA, prioridad=1)
        for _ in range(10):
            _propuesta(org_a, abierto,
                       estado=PropuestaSupervisor.PROPUESTA, prioridad=40)

    r = admin_client.get(RUTA)
    assert r.status_code == 200
    cuerpo = r.json()

    assert cuerpo["count"] == LOTE_MAXIMO + 15
    assert len(cuerpo["resultados"]) == LOTE_MAXIMO
    assert cuerpo["truncado"] is True, "una lista recortada tiene que decirlo"

    #  EL EFECTO: las diez llegaron, pese al tope.
    pendientes = [p for p in cuerpo["resultados"]
                  if p["estado"] == PropuestaSupervisor.PROPUESTA]
    assert len(pendientes) == 10, (
        f"el tope volvio a esconder trabajo sin revisar: llegaron "
        f"{len(pendientes)} de 10")

    #  Y con lo que la pantalla necesita para clasificarlas.
    assert all(p["caso_cerrado"] is False for p in pendientes)


def test_sin_pendientes_el_cero_es_un_cero(org_a, admin_client, admin_profile):
    """Cero pendientes es cero, no un recorte disfrazado."""
    with rls_org(org_a):
        cerrado = _caso(org_a, cerrado=True)
        for _ in range(3):
            _propuesta(org_a, cerrado,
                       estado=PropuestaSupervisor.ACEPTADA, prioridad=1)

    cuerpo = admin_client.get(RUTA).json()
    assert cuerpo["truncado"] is False
    assert [p for p in cuerpo["resultados"]
            if p["estado"] == PropuestaSupervisor.PROPUESTA] == []


def test_las_de_caso_cerrado_llegan_marcadas_no_escondidas(org_a, admin_client,
                                                           admin_profile):
    """
    No se ocultan en el backend: llegan con 'caso_cerrado: true' y es la
    pantalla la que las saca de Pendientes. Esconderlas aqui seria cambiar la
    regla de negocio para que un contador diera el numero deseado.
    """
    with rls_org(org_a):
        cerrado = _caso(org_a, cerrado=True)
        _propuesta(org_a, cerrado,
                   estado=PropuestaSupervisor.PROPUESTA, prioridad=5)

    cuerpo = admin_client.get(RUTA).json()
    assert len(cuerpo["resultados"]) == 1
    assert cuerpo["resultados"][0]["estado"] == PropuestaSupervisor.PROPUESTA
    assert cuerpo["resultados"][0]["caso_cerrado"] is True


def test_dentro_del_grupo_sigue_mandando_la_urgencia(org_a, admin_client,
                                                     admin_profile):
    """El orden de siempre no cambio: solo se antepuso el grupo."""
    with rls_org(org_a):
        abierto = _caso(org_a, cerrado=False)
        _propuesta(org_a, abierto,
                   estado=PropuestaSupervisor.PROPUESTA, prioridad=50)
        _propuesta(org_a, abierto,
                   estado=PropuestaSupervisor.PROPUESTA, prioridad=10)

    cuerpo = admin_client.get(RUTA).json()
    prioridades = [p["prioridad"] for p in cuerpo["resultados"]]
    assert prioridades == sorted(prioridades)
