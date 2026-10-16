# -*- coding: utf-8 -*-
"""
================================================================================
 UN PASE A DESPACHO Y UNA ACEPTACION DE CIERRE NO SON LO MISMO
================================================================================

EL DEFECTO, MEDIDO EN PRODUCCION  --  16/10/2026
-------------------------------------------------
El filtro "Pasados a Despacho" del panel marcaba 597, y el detalle de esas
filas decia "Cerrar el caso en Dexter para sincronizar su estado". No eran
pases: eran aceptaciones automaticas de propuestas de CIERRE.

La causa: las dos cosas escriben exactamente la misma fila de auditoria
--'PropuestaSupervisor' + 'APPROVED' + el mismo 'extra'-- y el grupo del panel
se armaba solo con ese par. Nada en la fila decia que tarea la habia producido.

LO QUE SE HIZO: 'revisar' acepta 'tarea' y la deja en 'metadata'. El grupo
'pasa_a_despacho' exige esa tarea; 'acepta' recoge el resto.

LO QUE NO SE PUDO HACER, y se dice: las filas anteriores a hoy no tienen la
clave. Caen en 'acepta'. Repartirlas seria inventar un dato que nadie escribio.

POR QUE ESTAS PRUEBAS MIRAN LOS DOS LADOS A LA VEZ: el filtro y el contador se
parten por criterios distintos --uno arma un Q, el otro agrega un 'values_list'--
y si divergen, el boton dice un numero y la lista muestra otro. Eso es peor que
el defecto original, porque parece que faltan filas.
================================================================================
"""
import pytest

from operaciones import auditoria

pytestmark = pytest.mark.django_db


def _fila(org, *, accion="APPROVED", entidad=None, tarea=None, nombre="x"):
    extra = {"tarea": tarea} if tarea else None
    return auditoria.registrar(
        org=org, actor=None, accion=accion,
        entidad=entidad or auditoria.ENTIDAD_PROPUESTA,
        entidad_id="11111111-1111-1111-1111-111111111111",
        nombre=nombre, extra=extra)


# =============================================================================
#  §1  SE SEPARAN
# =============================================================================

def test_un_pase_cae_en_pasa_a_despacho_y_un_cierre_NO(org_a):
    _fila(org_a, tarea=auditoria.TAREA_PASO_A_DESPACHO, nombre="pase")
    _fila(org_a, tarea=None, nombre="Cerrar el caso en Dexter")

    pases = list(auditoria.recientes(org_a, 20, grupo="pasa_a_despacho"))
    aceptadas = list(auditoria.recientes(org_a, 20, grupo="acepta"))

    assert [a.entity_name for a in pases] == ["pase"]
    assert [a.entity_name for a in aceptadas] == ["Cerrar el caso en Dexter"], (
        "la aceptación de un cierre no es un pase a Despacho: mostrarla ahí "
        "fue lo que hizo que el panel dijera 597")


def test_lo_HISTORICO_sin_tarea_cae_en_aceptadas(org_a):
    """Las 597 filas de producción: no tienen la clave y no se inventan."""
    for _ in range(3):
        _fila(org_a, tarea=None)

    assert len(list(auditoria.recientes(org_a, 20, grupo="pasa_a_despacho"))) == 0
    assert len(list(auditoria.recientes(org_a, 20, grupo="acepta"))) == 3


def test_una_tarea_DISTINTA_tampoco_es_un_pase(org_a):
    """Fail-closed: solo la tarea del paso cuenta como pase."""
    _fila(org_a, tarea="cerrar_desincronizados_con_diagnostico")

    assert len(list(auditoria.recientes(org_a, 20, grupo="pasa_a_despacho"))) == 0
    assert len(list(auditoria.recientes(org_a, 20, grupo="acepta"))) == 1


# =============================================================================
#  §2  EL CONTADOR DICE LO MISMO QUE LA LISTA
# =============================================================================

def test_el_contador_se_parte_IGUAL_que_el_filtro(org_a):
    _fila(org_a, tarea=auditoria.TAREA_PASO_A_DESPACHO)
    _fila(org_a, tarea=auditoria.TAREA_PASO_A_DESPACHO)
    _fila(org_a, tarea=None)
    _fila(org_a, tarea=None)
    _fila(org_a, tarea=None)

    conteo = auditoria.cuantos_por_grupo(org_a)

    for grupo in ("pasa_a_despacho", "acepta"):
        cuantos_en_la_lista = len(list(auditoria.recientes(org_a, 50, grupo=grupo)))
        assert conteo[grupo] == cuantos_en_la_lista, (
            f"el botón de '{grupo}' dice {conteo[grupo]} y la lista trae "
            f"{cuantos_en_la_lista}: parece que faltan filas")

    assert conteo["pasa_a_despacho"] == 2
    assert conteo["acepta"] == 3


def test_los_grupos_siguen_sumando_el_total(org_a):
    """
    Si una fila cayera en dos grupos, o en ninguno, los números dejarían de
    cerrar y nadie podría confiar en 'Todo'.
    """
    _fila(org_a, tarea=auditoria.TAREA_PASO_A_DESPACHO)
    _fila(org_a, tarea=None)
    _fila(org_a, accion="CREATE")
    _fila(org_a, accion="REJECTED")
    _fila(org_a, accion="STATUS_CHANGED", entidad=auditoria.ENTIDAD_CASO)

    c = auditoria.cuantos_por_grupo(org_a)
    partes = sum(c[g] for g in c if g not in ("todo",))

    assert partes == c["todo"], f"las partes suman {partes} y el total es {c['todo']}"


def test_un_APPROVED_con_tarea_rara_no_cae_en_otros(org_a):
    """
    'otros' mira el PAR y nunca la tarea. Si mirara la tarea, una fila con una
    tarea desconocida caería en 'otros' Y en 'acepta', y el total no cerraría.
    """
    _fila(org_a, tarea="una_tarea_que_nadie_declaro")

    c = auditoria.cuantos_por_grupo(org_a)

    assert c["otros"] == 0
    assert c["acepta"] == 1
    assert c["todo"] == 1


# =============================================================================
#  §3  LA CLAVE NO DIVERGE DEL CATALOGO
# =============================================================================

def test_la_tarea_declarada_aca_es_la_MISMA_del_catalogo(org_a):
    """
    'auditoria' la declara por su cuenta para no importar 'paso_a_despacho'
    (ciclo de imports). Dos copias del mismo texto divergen en silencio: si
    alguien renombra la tarea, el filtro deja de encontrar nada y el panel
    muestra cero sin un solo error.
    """
    from operaciones import paso_a_despacho as pad

    assert auditoria.TAREA_PASO_A_DESPACHO == pad.TAREA


# =============================================================================
#  §4  Y EL PASO DE VERDAD ESCRIBE ESA TAREA
# =============================================================================
#  ESTA PRUEBA EXISTE POR UN ERROR MIO  --  16/10/2026
#
#  'paso_a_despacho' pasaba 'tarea=TAREA' a 'revisar', y un banco de mutaciones
#  restauro 'supervisor.py' desde un respaldo anterior al cambio: 'revisar'
#  quedo sin ese parametro. El arbol quedo en un estado que levanta TypeError
#  en cuanto un ticket pasa a Despacho.
#
#  LAS 24 PRUEBAS SIGUIERON EN VERDE, porque ninguna recorria
#  'pasar_si_corresponde -> revisar': las de arriba llaman a
#  'auditoria.registrar' directo. Afirmaban que el GRUPO sabe separar, no que
#  alguien escriba la clave por la que separa.

def _caso(org):
    import uuid as _uuid

    from cases.models import Case

    return Case.objects.create(
        org=org, name="CTO 11-43", status="New", priority="Normal",
        is_active=True, provider="wisphub",
        external_ticket_id=f"t{_uuid.uuid4().hex[:8]}",
        external_service_id="3614",
        description="Intervencion de la CTO 11-43 de villa maria.")


def _propuesta_que_pasa(org, caso):
    from operaciones import clasificacion_de_trabajo as clf
    from operaciones import diagnostico_de_ticket as dxt
    from operaciones import paso_a_despacho as pad
    from operaciones.models import PropuestaSupervisor

    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.PROPUESTA,
        evidencia=[{
            "fuente": dxt.FUENTE, "dato": "lectura del reclamo",
            "observado_en": "2026-10-15T20:00:00Z",
            "grupo": pad.OBRA_DE_RED, "labor": clf.CORRECTIVO,
            "labor_verificada": False, "labor_porque": "",
            "confianza": "media", "confianza_del_grupo": "alta",
        }])


def test_pasar_a_despacho_DEJA_la_tarea_en_la_auditoria(org_a, monkeypatch):
    """
    El efecto completo: se pasa un ticket y la fila queda en el grupo correcto.

    Recorre 'pasar_si_corresponde -> revisar -> auditoria', que es justo el
    camino que las otras pruebas no tocaban.
    """
    from operaciones import autonomia, cierre_de_caso, tareas_delegadas
    from operaciones import paso_a_despacho as pad
    from operaciones import supervisor as sup

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, c: True)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})
    monkeypatch.setattr(cierre_de_caso, "_pedirle_al_motor",
                        lambda propuesta_id, id_caso: {"cerrado": True})

    caso = _caso(org_a)
    p = _propuesta_que_pasa(org_a, caso)

    r = pad.pasar_si_corresponde(org_a, sup._SinSenal(p), p)

    assert r["paso"] is True, f"no pasó: {r.get('porque')}"

    #  Y la fila quedó donde corresponde, no en 'acepta'.
    pases = list(auditoria.recientes(org_a, 20, grupo="pasa_a_despacho"))
    assert len(pases) == 1, (
        "el pase no quedó marcado con su tarea: el panel lo mostraría "
        "mezclado con las aceptaciones de cierres, que es el defecto que "
        "este archivo entero viene a cerrar")
    assert pases[0].metadata.get("tarea") == auditoria.TAREA_PASO_A_DESPACHO
    assert len(list(auditoria.recientes(org_a, 20, grupo="acepta"))) == 0
