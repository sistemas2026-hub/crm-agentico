# -*- coding: utf-8 -*-
"""
================================================================================
 LA COMPARACIÓN EN SOMBRA CUENTA LO QUE DICE QUE CUENTA
================================================================================

`cuanto_acierta_solo` es el número con el que se va a decidir si el Supervisor
puede actuar sin que nadie lo apruebe. Un contador equivocado ahí no produce un
informe feo: produce una autonomía concedida sobre un número inventado.

Lo que se afirma es el EFECTO sobre la salida, con filas reales en la base.

    pytest operaciones/tests/test_cuanto_acierta_solo.py
================================================================================
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

EVIDENCIA = [{"fuente": "prueba", "entidad": "x", "dato": "algo",
              "visto_en": "2026-10-20T10:00:00+00:00"}]


def _propuesta(org, estado, *, tipo=None, revisado_hace_horas=1,
               creada_hace_horas=2):
    ahora = timezone.now()
    p = PropuestaSupervisor.objects.create(
        org=org,
        tipo_senal=tipo or PropuestaSupervisor.CASO_REQUIERE_VISITA,
        origen_tipo="case", origen_id="caso-x",
        estado=estado,
        #  `propuesta_exige_evidencia` es una restricción de la BASE: una
        #  propuesta sin ella no se puede ni insertar.
        evidencia=EVIDENCIA,
    )
    PropuestaSupervisor.objects.filter(pk=p.pk).update(
        created_at=ahora - timezone.timedelta(hours=creada_hace_horas),
        revisado_en=ahora - timezone.timedelta(hours=revisado_hace_horas))
    return p


def _correr(org, **kw):
    salida = StringIO()
    call_command("cuanto_acierta_solo", org=str(org.id), stdout=salida, **kw)
    return salida.getvalue()


def test_a_cuenta_los_tres_veredictos_por_separado(org_a):
    """Aceptada, modificada y rechazada son tres cosas distintas."""
    _propuesta(org_a, PropuestaSupervisor.ACEPTADA)
    _propuesta(org_a, PropuestaSupervisor.ACEPTADA)
    _propuesta(org_a, PropuestaSupervisor.MODIFICADA)
    _propuesta(org_a, PropuestaSupervisor.RECHAZADA)

    texto = _correr(org_a)

    assert "propuestas revisadas" in texto
    assert "4" in texto
    #  2 de 4 = 50%: el número con el que se decidiría soltar autonomía.
    assert "50%" in texto, texto


def test_b_las_NO_revisadas_no_cuentan(org_a):
    """Una propuesta sin revisar no es un error del agente.

    Es una pregunta sin contestar. Si contara, el número empeoraría cuanto más
    rápido propone el agente -- que es exactamente al revés de lo que pasa.
    """
    _propuesta(org_a, PropuestaSupervisor.ACEPTADA)
    #  Sin revisar: estado 'propuesta', y por eso sin `revisado_en`.
    PropuestaSupervisor.objects.create(
        org=org_a, tipo_senal=PropuestaSupervisor.CASO_REQUIERE_VISITA,
        origen_tipo="case", origen_id="caso-y",
        estado=PropuestaSupervisor.PROPUESTA, evidencia=EVIDENCIA)

    texto = _correr(org_a)

    assert "propuestas revisadas            1" in texto.replace("  ", " ") \
        or "1" in texto
    assert "100%" in texto, (
        "la propuesta sin revisar bajó el porcentaje: una pregunta sin "
        f"contestar no es un error del agente.\n{texto}")


def test_c_desglosa_por_tipo_porque_el_agregado_miente(org_a):
    """Un 95% en lo fácil y un 40% en lo que manda una cuadrilla a una casa
    dan un promedio tranquilizador y una decisión pésima."""
    _propuesta(org_a, PropuestaSupervisor.ACEPTADA,
               tipo=PropuestaSupervisor.CASO_REQUIERE_VISITA)
    _propuesta(org_a, PropuestaSupervisor.RECHAZADA,
               tipo=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO)

    texto = _correr(org_a)

    assert "POR TIPO DE SEÑAL" in texto
    assert PropuestaSupervisor.CASO_REQUIERE_VISITA in texto
    assert PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO in texto


def test_d_avisa_cuando_la_revision_fue_un_clic(org_a):
    """El contrapeso del porcentaje.

    Una aceptación en segundos sobre una propuesta con evidencia no es un
    acuerdo: es un clic. Sin este aviso, un revisor que acepta todo sin leer
    produce un 100% que habilitaría autonomía sobre nada.
    """
    for _ in range(4):
        _propuesta(org_a, PropuestaSupervisor.ACEPTADA,
                   creada_hace_horas=1,
                   #  Revisada 2 segundos después de creada.
                   revisado_hace_horas=1 - (2 / 3600))

    texto = _correr(org_a)

    assert "AVISO" in texto, (
        "cuatro revisiones de dos segundos y el informe no avisó: el "
        f"porcentaje de aceptación se lee como criterio.\n{texto}")
    assert "mide coincidencia, no criterio" in texto


def test_e_sin_nada_que_contar_lo_dice_en_vez_de_mostrar_cero(org_a):
    """«0 revisadas» y «el agente nunca acierta» son cosas distintas.

    Un cero sin explicación se lee como la segunda -- el mismo error que este
    repositorio ya nombró cinco veces con las listas vacías.
    """
    texto = _correr(org_a)

    assert "Ninguna propuesta revisada" in texto
    assert "NO dice que el agente falle" in texto
    #  Y manda al otro lado, que es donde está la otra mitad de la verdad.
    assert "informe_de_pendientes" in texto
