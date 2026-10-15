# -*- coding: utf-8 -*-
"""
================================================================================
 EL PASO A DESPACHO CORRE AUNQUE NO SE HAYA LEIDO NADA
================================================================================

EL SINTOMA QUE ESTA PRUEBA REPRODUCE  --  14/10/2026
----------------------------------------------------
El cliente ejecuto el ciclo y no paso nada. Medido: el ciclo registro 5
razonamientos y CERO lecturas de ticket, ninguna propuesta cambio de estado, y
no hubo un solo error en ningun log.

La causa: el paso a Despacho vivia DENTRO de la fase de lectura, que arranca
con "if not candidatas: return informe". Una propuesta que ya tiene su lectura
no es candidata a leerse, asi que con las 80 propuestas del dia ya leidas la
fase salia por ese return y el paso no corria nunca.

LA TERCERA VEZ DEL MISMO ERROR, y por eso esta prueba existe
-----------------------------------------------------------
    1. los desincronizados ya diagnosticados no entraban en ninguna cola
    2. el paso exigia 'diagnostico_leido', que solo tienen los de esa vuelta
    3. el paso vivia en una fase que se va temprano

Las tres son la misma forma: la decision puesta en una rama a la que los casos
que importan no llegan. Y las tres veces el sintoma fue "no hace nada" sin un
error. Lo que las cierra no es mover un 'if': es que el paso CONSULTE las
propuestas pendientes por su cuenta, y que una prueba afirme que corre con la
fase de lectura sin nada que hacer.
================================================================================
"""

import pytest
from django.utils import timezone

from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


def _caso(org, nombre="No tiene internet"):
    from cases.models import Case

    #  'case_external_ref_complete' exige proveedor y ticket, las dos o ninguna.
    import uuid

    return Case.objects.create(
        org=org, name=nombre, status="New", priority="Normal", is_active=True,
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614",
        description="El cliente dice que no tiene internet.")


def _propuesta_ya_leida(org, caso, *, grupo, verificada=True,
                        confianza_del_grupo="alta"):
    """
    Una propuesta como las 80 del dia: con su lectura YA guardada, de otra
    vuelta. Es la que el paso tiene que poder decidir sin releer nada.
    """
    from operaciones import clasificacion_de_trabajo as clf
    from operaciones import diagnostico_de_ticket as dxt

    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.PROPUESTA,
        evidencia=[{
            "fuente": dxt.FUENTE,
            "dato": "lectura del reclamo: no tiene servicio",
            "observado_en": "2026-10-13T20:00:00Z",
            "grupo": grupo,
            "labor": clf.CORRECTIVO,
            "labor_verificada": verificada,
            "labor_porque": "el equipo esta caido por perdida de señal optica",
            "confianza": "media",
            "confianza_del_grupo": confianza_del_grupo,
        }])


def _correr_la_fase(org, ahora=None):
    """El reporte de la fase, desenvuelto de su clave.

    La fase devuelve {"despacho": ...} porque 'correr_ciclo' hace
    'resumen.update(fase())' y asi cada fase aporta su propia clave en vez de
    mezclarse en la raiz. Lo encontro esta prueba, leyendo el resumen del
    ciclo: la version anterior devolvia el reporte plano y nadie lo hallaba
    donde lo buscaba.
    """
    return sup._pasar_a_despacho_los_que_las_reglas_habiliten(
        org, ahora or timezone.now())["despacho"]


def _las_puertas_abiertas(monkeypatch):
    from operaciones import autonomia, cierre_de_caso, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada",
                        lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})
    #  Por si algun camino intentara hablar con el motor: que no salga nada.
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        lambda propuesta_id, id_caso: {
                            "cerrado": True, "codigo": "CERRADO",
                            "motivo": "", "referencia": "propuesta:x"})


# =============================================================================
#  §1  LA FASE CORRE SOLA
# =============================================================================

def test_pasa_una_propuesta_LEIDA_EN_OTRA_VUELTA(org_a, monkeypatch):
    """
    EL CASO QUE FALLABA. No se lee nada en esta corrida --la propuesta ya tenia
    su lectura-- y el paso tiene que ocurrir igual.
    """
    caso = _caso(org_a)
    p = _propuesta_ya_leida(org_a, caso, grupo=pad.FALLA_DE_SERVICIO)
    _las_puertas_abiertas(monkeypatch)

    reporte = _correr_la_fase(org_a)

    assert reporte["pasaron"] == 1, reporte
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA, (
        "la propuesta no se acepto, asi que el caso no esta en la cola de "
        "Despacho: es el sintoma de 'ejecute el ciclo y no hizo nada'")


def test_la_fase_NO_depende_de_que_la_lectura_haya_corrido(org_a, monkeypatch):
    """
    LA GUARDA ESTRUCTURAL, y es la que cierra la clase de error.

    Se desarma la fase de lectura a proposito --se la reemplaza por una que no
    hace nada, como cuando no hay tickets por leer-- y el paso tiene que
    ocurrir igual. Si alguna vez se lo vuelve a colgar de esa fase, esto se
    pone en rojo.
    """
    caso = _caso(org_a)
    p = _propuesta_ya_leida(org_a, caso, grupo=pad.OBRA_DE_RED,
                            verificada=False)
    _las_puertas_abiertas(monkeypatch)
    monkeypatch.setattr(sup, "_leer_tickets_abiertos",
                        lambda org, ahora: {"tickets": {}})

    sup.correr_ciclo(org_a)

    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.ACEPTADA, (
        "con la lectura sin hacer nada, el paso no ocurrio: volvio a depender "
        "de esa fase")


def test_el_ciclo_reporta_la_fase_y_cuenta_lo_que_miro(org_a, monkeypatch):
    """
    Un paso que ocurre y no se cuenta es un paso que nadie puede medir, y el
    14/10 eso costo varias consultas a mano contra produccion.
    """
    caso = _caso(org_a)
    _propuesta_ya_leida(org_a, caso, grupo=pad.FALLA_DE_SERVICIO)
    _las_puertas_abiertas(monkeypatch)
    monkeypatch.setattr(sup, "_leer_tickets_abiertos",
                        lambda org, ahora: {"tickets": {}})

    resumen = sup.correr_ciclo(org_a)

    d = resumen.get("despacho") or {}
    assert d.get("pendientes_miradas") == 1, resumen
    assert d.get("pasaron") == 1, resumen
    assert d.get("por_grupo") == {pad.FALLA_DE_SERVICIO: 1}, d
    #  Y LA DISTRIBUCION DE LA CONFIANZA, que es lo que falta calibrar.
    assert d.get("por_confianza") == {"alta": 1}, d
    assert "fases_que_fallaron" not in resumen, resumen


# =============================================================================
#  §2  LO QUE SIGUE SIN PASAR
# =============================================================================

def test_una_pagina_bloqueada_leida_en_otra_vuelta_tampoco_pasa(org_a,
                                                                monkeypatch):
    caso = _caso(org_a, "Paginas Bloqueadas")
    p = _propuesta_ya_leida(org_a, caso, grupo=pad.NADA_LO_MIDE)
    _las_puertas_abiertas(monkeypatch)

    reporte = _correr_la_fase(org_a)

    assert reporte["pasaron"] == 0
    assert reporte["se_quedaron"] == 1
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.PROPUESTA


def test_una_propuesta_YA_DECIDIDA_no_se_vuelve_a_tocar(org_a, monkeypatch):
    """
    Alguien la rechazo: volver sobre ella seria pisar lo que una persona dijo.
    """
    caso = _caso(org_a)
    p = _propuesta_ya_leida(org_a, caso, grupo=pad.FALLA_DE_SERVICIO)
    PropuestaSupervisor.objects.filter(pk=p.pk).update(
        estado=PropuestaSupervisor.RECHAZADA)
    _las_puertas_abiertas(monkeypatch)

    reporte = _correr_la_fase(org_a)

    assert reporte.get("pendientes_miradas", 0) == 0, (
        "se miro una propuesta que ya tenia decision humana")
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.RECHAZADA


def test_una_propuesta_de_OTRA_empresa_no_se_toca(org_a, org_b, monkeypatch):
    caso = _caso(org_b)
    p = _propuesta_ya_leida(org_b, caso, grupo=pad.FALLA_DE_SERVICIO)
    _las_puertas_abiertas(monkeypatch)

    _correr_la_fase(org_a)

    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.PROPUESTA, (
        "se paso a Despacho un caso de otra empresa")


def test_sin_propuestas_pendientes_la_fase_no_se_cae(org_a, monkeypatch):
    _las_puertas_abiertas(monkeypatch)

    reporte = _correr_la_fase(org_a)

    assert reporte["pasaron"] == 0
    assert reporte.get("pendientes_miradas", 0) == 0


# =============================================================================
#  §3  EL LIMBO DE LAS LEIDAS CON EL FORMATO ANTERIOR
# =============================================================================
#
#  Las 80 propuestas que existian el 14/10/2026 se leyeron antes de que la
#  lectura guardara el grupo. Quedaban con las dos puertas cerradas:
#
#      tienen lectura          ->  no eran candidatas a leerse de nuevo
#      su lectura no da grupo  ->  el paso no podia decidirlas
#
#  Y el sintoma habria sido el de siempre --"no se movio nada"-- para siempre.

def _propuesta_con_lectura_VIEJA(org, caso):
    """Como las 80: la frase escrita, y ninguna de las claves nuevas."""
    from operaciones import diagnostico_de_ticket as dxt

    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.PROPUESTA,
        evidencia=[{"fuente": dxt.FUENTE,
                    "dato": "lectura del reclamo: no tiene servicio",
                    "observado_en": "2026-10-13T20:00:00Z"}])


def test_una_lectura_sin_grupo_vuelve_a_la_cola_de_lectura(org_a):
    """
    LA PUERTA QUE SE ABRE. Sin esto esas 80 no se releen nunca, porque para la
    fase de lectura ya estan al dia.
    """
    from operaciones import diagnostico_de_ticket as dxt

    caso = _caso(org_a)
    vieja = _propuesta_con_lectura_VIEJA(org_a, caso)

    #  DOS CRITERIOS, NO UNO. 'le_falta_lectura' sigue diciendo que la
    #  lectura ESTA --y tiene razon, la evidencia esta ahi--; el que detecta
    #  que esta incompleta es 'le_falta_el_grupo'. Mezclarlos rompia la guarda
    #  que distingue los casos, y asi lo encontro.
    assert dxt.le_falta_lectura(vieja) is False
    assert dxt.le_falta_el_grupo(vieja) is True, (
        "una lectura sin el grupo se dio por completa: esa propuesta queda en "
        "el limbo, sin releerse y sin poder decidirse")


def test_una_lectura_CON_grupo_no_se_relee(org_a):
    """
    El contrafactico, y es el que impide que esto releea todo para siempre:
    cada relectura cuesta una consulta al modelo.
    """
    from operaciones import diagnostico_de_ticket as dxt

    caso = _caso(org_a)
    nueva = _propuesta_ya_leida(org_a, caso, grupo=pad.FALLA_DE_SERVICIO)

    assert dxt.le_falta_lectura(nueva) is False
    assert dxt.le_falta_el_grupo(nueva) is False


def test_el_grupo_NO_se_deduce_del_texto_de_la_lectura_vieja(org_a,
                                                             monkeypatch):
    """
    La frase vieja dice 'no tiene servicio', que suena a falla de servicio. No
    se la interpreta: es texto libre escrito para que lo lea una persona, y
    clasificar un ticket a partir de eso es justo lo que este modulo evita.

    La propuesta se queda, y su motivo dice que hay que volver a leer.
    """
    caso = _caso(org_a)
    vieja = _propuesta_con_lectura_VIEJA(org_a, caso)
    _las_puertas_abiertas(monkeypatch)

    reporte = _correr_la_fase(org_a)

    assert reporte["pasaron"] == 0, (
        "se clasifico un ticket leyendo la frase de una lectura vieja")
    vieja.refresh_from_db()
    assert vieja.estado == PropuestaSupervisor.PROPUESTA
    assert any("volver a leer" in m for m in reporte["motivos"]), (
        f"el motivo no dice que falta releer: {reporte['motivos']}")


def test_sin_NINGUNA_lectura_no_es_lo_mismo_que_una_incompleta(org_a):
    """
    Los tres casos son distintos y cada criterio contesta el suyo. Que
    'le_falta_el_grupo' contestara True aqui lo haria indistinguible de
    'le_falta_lectura', y entonces uno de los dos no haria falta -- o peor,
    taparia al otro.
    """
    from operaciones import diagnostico_de_ticket as dxt

    caso = _caso(org_a)
    sin_nada = PropuestaSupervisor.objects.create(
        org=org_a, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.PROPUESTA,
        evidencia=[{"fuente": "caso", "dato": "ticket en el proveedor: 1",
                    "observado_en": "2026-10-14T18:00:00Z"}])

    assert dxt.le_falta_lectura(sin_nada) is True
    assert dxt.le_falta_el_grupo(sin_nada) is False, (
        "sin ninguna lectura no hay grupo que falte: ese caso es del otro "
        "criterio")
