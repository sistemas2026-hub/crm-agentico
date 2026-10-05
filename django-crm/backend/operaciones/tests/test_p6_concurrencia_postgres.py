# -*- coding: utf-8 -*-
"""
================================================================================
 P6  --  DOS COORDINACIONES A LA VEZ, contra PostgreSQL de verdad
================================================================================

POR QUE ESTE ARCHIVO EXISTE APARTE
----------------------------------
Las pruebas con 'transaction=True' hacen que pytest-django haga FLUSH de la base
y vuelva a emitir 'post_migrate'. Varias de esas en el mismo proceso chocan en
'auth_permission', y el sintoma no se parece a la causa: fallan pruebas vecinas
que no tienen nada que ver. Es la convencion que el repositorio ya sigue
('test_fuentes_concurrencia_postgres.py', 'test_situaciones_concurrencia_
postgres.py'), y se respeta.

QUE SE MIDE, Y POR QUE NO SE PODIA SUPONER
------------------------------------------
La auditoria de M02 dejo esto por escrito: 'crear(evitar_duplicado=True)'
deduplica con un SELECT previo y NO hay 'UniqueConstraint' que lo respalde --
"es de servicio, no de base". Con eso en la mano, la pregunta no es retorica:
dos ciclos del Supervisor que lleguen juntos sobre la misma situacion PODRIAN
pasar los dos el chequeo y crear dos actividades.

Asi que se mide en vez de afirmarse. Si el resultado es dos, no es un fallo de
la prueba: es el hueco real, y la prueba lo deja medido con su numero.
================================================================================
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from django.db import connections

from common.models import Profile, User
from operaciones import autonomia as gob
from operaciones import coordinacion as coord
from operaciones.models import ActividadOperativa, PropuestaSupervisor
from operaciones.tests.test_p5_chat_supervisor import _situacion

A = ActividadOperativa
P = PropuestaSupervisor


@pytest.mark.django_db(transaction=True)
def test_dos_coordinaciones_simultaneas_sobre_la_misma_situacion(org_a):
    """
    Dos hilos piden la MISMA actividad para la MISMA situacion, a la vez.

    Lo que se afirma: que no queden dos actividades vivas del mismo tipo para la
    misma situacion. Es la garantia que el Supervisor necesita para poder correr
    su ciclo sin miedo: dos ticks que se solapen no pueden duplicar trabajo de
    campo.
    """
    u = User.objects.create_user(email="jefe.conc.p6@prueba.local",
                                 password="clave-de-prueba-1")
    jefe = Profile.objects.create(user=u, org=org_a, role="OPERACIONES",
                                  is_active=True)
    s = _situacion(org_a)
    gob.cambiar(org_a, P.NIVEL_COORDINAR, actor=jefe,
                motivo="piloto de concurrencia",
                criterios="se revierte al terminar")

    def pedir():
        #  El interruptor se sustituye DENTRO del hilo: 'mock.patch' no cruza
        #  hilos, y sin esto el segundo hilo veria la autonomia recortada y la
        #  prueba pasaria por el motivo equivocado.
        with mock.patch("operaciones.autonomia._interruptor_de",
                        return_value=(True, "")):
            try:
                return coord.solicitar_actividad(
                    s, actor=jefe, tipo=A.TAREA,
                    titulo="Diagnosticar el PON 3/1/4",
                    objetivo="Confirmar la causa",
                    condicion_exito="Causa registrada", area="NOC")
            except Exception as e:                           # noqa: BLE001
                return e
            finally:
                connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = [f.result() for f in
                      [pool.submit(pedir), pool.submit(pedir)]]

    vivas = A.objects.filter(
        org=org_a, tipo=A.TAREA, origen_tipo=coord.ORIGEN_SITUACION,
        origen_id=str(s.id)).exclude(estado_operativo__in=A.ESTADOS_FINALES)

    #  LA AFIRMACION: una sola actividad viva.
    assert vivas.count() == 1, (
        f"quedaron {vivas.count()} actividades vivas para la misma situación: "
        f"la deduplicación de M02 es por SELECT previo y no hay UniqueConstraint "
        f"que la respalde, así que una carrera puede duplicar trabajo de campo. "
        f"Resultados: {resultados}")

    #  Y ninguno de los dos hilos quedo sin respuesta: o devolvio la actividad,
    #  o devolvio una excepcion legible. Un hilo que se cuelga sin nada seria
    #  peor que un duplicado, porque nadie sabria que paso.
    assert len(resultados) == 2
    for r in resultados:
        assert isinstance(r, (dict, Exception)), r
