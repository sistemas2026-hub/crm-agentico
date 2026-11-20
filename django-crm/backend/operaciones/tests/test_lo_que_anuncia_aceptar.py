# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE LA PANTALLA ANUNCIA AL ACEPTAR ES LO QUE PASA AL ACEPTAR
================================================================================

Que cubre y por que
-------------------
Hasta el 19/10/2026 el modal de revision decia «aceptar no ejecuta nada» para
todo lo que no fuera un cierre, y era falso para los dos tipos que llevan a
Despacho: aceptarlos pone el caso en la cola de campo. Lo pregunto el usuario
--«si acepto la propuesta, ¿se pasa a despacho?»-- con una lectura en pantalla
que decia «no corresponde despachar un tecnico».

Ahora cada propuesta trae 'al_aceptar'. Se afirma sobre el EFECTO: se acepta
por la API y se mira la cola de Despacho. Si el anuncio y la cola se separan
--alguien vuelve a escribir la lista de tipos en un solo lado--, esto se pone
en rojo.

    pytest operaciones/tests/test_lo_que_anuncia_aceptar.py
================================================================================
"""

import pytest

from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

PROPUESTAS = "/api/operaciones/propuestas/"


def _caso(org, nombre="Sin internet"):
    from cases.models import Case

    return Case.objects.create(org=org, name=nombre, status="New",
                               priority="Normal", is_active=True)


def _pendiente(org, tipo, origen_tipo="case", origen_id=None):
    #  'propuesta_exige_evidencia' la prohibe vacia.
    return P.objects.create(
        org=org, tipo_senal=tipo, origen_tipo=origen_tipo,
        origen_id=origen_id or str(_caso(org).id),
        estado=P.PROPUESTA,
        evidencia=[{"fuente": "equipo", "dato": "caido por fibra",
                    "momento": "2026-10-19T03:00:00Z"}],
    )


@pytest.mark.parametrize("tipo, anuncio", [
    (P.CASO_REQUIERE_VISITA, pad.AL_ACEPTAR_PASA_A_DESPACHO),
    (P.TICKET_SIN_DIAGNOSTICO, pad.AL_ACEPTAR_PASA_A_DESPACHO),
    (P.CASO_ANTIGUO, pad.AL_ACEPTAR_REGISTRA),
])
def test_a_lo_anunciado_es_lo_que_pasa_con_la_cola_de_despacho(
    admin_client, org_a, tipo, anuncio
):
    p = _pendiente(org_a, tipo)

    detalle = admin_client.get(f"{PROPUESTAS}{p.id}/").json()
    assert detalle["al_aceptar"] == anuncio

    r = admin_client.post(f"{PROPUESTAS}{p.id}/revisar/",
                          {"decision": P.ACEPTADA}, format="json")
    assert r.status_code == 200, r.content

    en_despacho = p.origen_id in pad.ids_en_despacho(org_a)
    assert en_despacho == (anuncio == pad.AL_ACEPTAR_PASA_A_DESPACHO)


def test_b_la_lista_tambien_lo_trae_para_el_boton_de_aceptar_varias(
    admin_client, org_a
):
    visita = _pendiente(org_a, P.CASO_REQUIERE_VISITA)
    antiguo = _pendiente(org_a, P.CASO_ANTIGUO)

    filas = {f["id"]: f["al_aceptar"]
             for f in admin_client.get(PROPUESTAS).json()["resultados"]}
    assert filas[str(visita.id)] == pad.AL_ACEPTAR_PASA_A_DESPACHO
    assert filas[str(antiguo.id)] == pad.AL_ACEPTAR_REGISTRA


def test_c_una_desincronizacion_anuncia_el_cierre():
    """El intento de cierre lo hace 'views.RevisarPropuestaView'; su efecto lo
    prueba 'test_m09s_cierre_al_aceptar'. Aca solo que se anuncia."""
    p = P(tipo_senal=P.CASO_DESINCRONIZADO, origen_tipo="case")
    assert pad.efecto_al_aceptar(p) == pad.AL_ACEPTAR_CIERRA_CASO


def test_d_sin_un_caso_detras_no_hay_nada_que_pasar_a_despacho():
    """La cola es de CASOS: una lectura sobre otra cosa no la alcanza."""
    p = P(tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="orden")
    assert pad.efecto_al_aceptar(p) == pad.AL_ACEPTAR_REGISTRA
