# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CREA LAS ORDENES DE DESPACHO  --  23/10/2026
================================================================================

Fase 2.3 de SPEC/objetivos/supervisor-arma-la-jornada.md, entrega 1: la regla
(`operaciones.ordenes_de_despacho.decidir`) y su vista previa. Afirma:

  P  la prioridad: con plazo, vencida o vence hoy = alta, mañana = media,
     despues = baja; sin plazo, por la espera (decision del usuario, 23/10)
  D  el dia: antes de la hora de corte, hoy; despues, mañana; sin hora de
     corte, no hay dia
  C  que crea y que no, cada motivo con su caso, sembrado junto a lo que si
  R  el corte de red: una sola orden por puerto, los demas atados
  N  que no escribe nada ni le pregunta al motor, que no mira otra empresa,
     y que la pantalla la pide solo quien gestiona

    pytest operaciones/tests/test_el_supervisor_crea_las_ordenes.py
================================================================================
"""
import datetime as dt
import uuid
import zoneinfo
from unittest import mock

import pytest

from campo.cuadrillas import ConfiguracionDeReparto
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.zonas import AliasDeZona, ZonaOperativa
from cases.models import Case
from operaciones import armado_de_jornadas as adj
from operaciones import ordenes_de_despacho as O
from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")
#: Martes 06/10/2026 a las 15:00 de Bogota.
A_LAS_3 = dt.datetime(2026, 10, 6, 15, 0, tzinfo=BOGOTA)
MARTES = dt.date(2026, 10, 6)
BARRIO = "SOLEDAD CENTRO"
VISTA = "/api/operaciones/ordenes/vista-previa/"


def _bogota(dia, hora, minuto=0):
    return dt.datetime(2026, 10, dia, hora, minuto, tzinfo=BOGOTA)


# ---------------------------------------------------------------------------
# P · la prioridad
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("creado_el, plazo, esperada", [
    (3, 2, O.ALTA),     # vencio el 5
    (4, 2, O.ALTA),     # vence hoy
    (5, 2, O.MEDIA),    # vence mañana
    (6, 2, O.BAJA),     # vence pasado
    (4, None, O.ALTA),  # sin plazo: dos dias esperando
    (5, None, O.MEDIA),  # uno
    (6, None, O.BAJA),  # de hoy
])
def test_p_por_plazo_y_si_no_por_espera(creado_el, plazo, esperada):
    creado = _bogota(creado_el, 10)
    assert O.prioridad_de(creado, plazo, MARTES, BOGOTA) == esperada


def test_p2_el_dia_es_el_de_la_empresa():
    #  Las 9 de la noche del lunes en Bogota son el martes en UTC: con el dia
    #  de UTC seria «de hoy» y no «un dia esperando».
    creado = _bogota(5, 21)
    assert creado.astimezone(dt.timezone.utc).date() == MARTES
    assert O.prioridad_de(creado, None, MARTES, BOGOTA) == O.MEDIA


def test_p3_sin_creacion_es_media():
    assert O.prioridad_de(None, 2, MARTES, BOGOTA) == O.MEDIA


# ---------------------------------------------------------------------------
# D · el dia
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entro, esperado", [
    (_bogota(6, 11, 59), MARTES),                        # antes del corte
    (_bogota(6, 12, 0), MARTES + dt.timedelta(days=1)),  # en el corte
    (_bogota(6, 14, 0), MARTES + dt.timedelta(days=1)),  # despues
    (_bogota(5, 18, 0), MARTES),                         # ayer: ya espero
    (None, MARTES),                                      # sin la hora
])
def test_d_la_hora_de_corte(entro, esperado):
    assert O.dia_de_la_orden(entro, dt.time(12, 0), A_LAS_3, BOGOTA) == esperado


def test_d2_sin_hora_de_corte_no_hay_dia():
    assert O.dia_de_la_orden(_bogota(6, 9), None, A_LAS_3, BOGOTA) is None


# ---------------------------------------------------------------------------
# Lo que se siembra
# ---------------------------------------------------------------------------

@pytest.fixture
def empresa(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    ConfiguracionDeReparto.objects.update_or_create(
        org=org_a, defaults={"hora_de_corte": dt.time(12, 0)})
    z = ZonaOperativa.objects.create(org=org_a, nombre="SOLEDAD")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad=BARRIO)
    return org_a


def _plantilla(org, codigo, labor, asuntos=(), plazo=None):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.title(),
                                   labor=labor, asuntos=list(asuntos),
                                   plazo_dias=plazo)
    return WorkTypeVersion.objects.create(
        work_type=tipo, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "x", "tipo": "texto"}]})


@pytest.fixture
def plantillas(empresa):
    return {
        "soporte": _plantilla(empresa, "soporte", "correctivo",
                              ["No tiene internet"], plazo=2),
        "red": _plantilla(empresa, "red", "trabajos", ["Corte de fibra"]),
        "instalacion": _plantilla(empresa, "instalacion", "instalacion",
                                  ["Instalacion nueva"], plazo=3),
    }


def _caso(org, asunto="No tiene internet", grupo=pad.FALLA_DE_SERVICIO, *,
          barrio=BARRIO, nuevo=False, creado=None, entro=None, medicion=None):
    """Un caso en la cola de Despacho. `barrio` None = todavia no se pidio."""
    caso = Case.objects.create(
        org=org, name=asunto, status="Assigned", priority="Normal",
        is_active=True, provider="wisphub", area="soporte_tecnico",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=f"s{uuid.uuid4().hex[:6]}",
        external_client_name="Zoraida Clientela")
    Case.objects.filter(pk=caso.pk).update(created_at=creado or _bogota(5, 9))
    caso.refresh_from_db()
    ahora = A_LAS_3.isoformat()
    evidencia = [{"fuente": pad.FUENTE_DE_LA_LECTURA, "id": str(caso.id),
                  "dato": "lectura", "observado_en": ahora, "grupo": grupo}]
    if barrio is not None:
        evidencia.append({"fuente": adj.FUENTE_LOCALIDAD, "id": str(caso.id),
                          "dato": "barrio", "observado_en": ahora,
                          "localidad": barrio, "motivo": "",
                          "cliente_nuevo": nuevo})
    if medicion is not None:
        evidencia.append({"fuente": pad.FUENTE_MEDICION, "id": str(caso.id),
                          "observado_en": ahora, **medicion})
    P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.ACEPTADA,
        revisado_en=entro or _bogota(6, 9), accion_propuesta="Revisar",
        motivo="x", prioridad=30, evidencia=evidencia)
    return caso


def _orden_de(org, caso, version, estado=OrdenTrabajo.ASIGNADA):
    return OrdenTrabajo.objects.create(
        org=org, numero=OrdenTrabajo.objects.count() + 100,
        tipo_trabajo_version=version, estado_operativo=estado,
        origen_sistema="crm", origen_ref=str(caso.id))


def _por_caso(salida):
    return ({f["caso"]: f for f in salida["crear"]},
            {f["caso"]: f for f in salida["no_se_crea"]},
            {f["caso"]: f for f in salida["atadas"]})


# ---------------------------------------------------------------------------
# C · que crea y que no
# ---------------------------------------------------------------------------

def test_c_cada_caso_con_su_respuesta(empresa, plantillas):
    crea = _caso(empresa, creado=_bogota(3, 9))
    sin_leer = _caso(empresa, barrio=None)
    sin_barrio = _caso(empresa, barrio="")
    sin_zona = _caso(empresa, barrio="OFICINA")
    sin_plantilla = _caso(empresa, asunto="Algo raro", grupo=pad.NADA_LO_MIDE)
    con_orden = _caso(empresa)
    _orden_de(empresa, con_orden, plantillas["soporte"])
    cancelada = _caso(empresa)
    _orden_de(empresa, cancelada, plantillas["soporte"], OrdenTrabajo.CANCELADA)
    nueva = _caso(empresa, asunto="Instalacion nueva", grupo=pad.TRABAJO_PEDIDO,
                  barrio="", nuevo=True)

    crear, no, _ = _por_caso(O.decidir(empresa, A_LAS_3))

    c = crear[str(crea.id)]
    assert (c["plantilla"], c["por"], c["prioridad"], c["para"], c["zona"]) == (
        "Soporte", "asunto", O.ALTA, "2026-10-06", "SOLEDAD")
    assert c["llamar_al_cliente"] is False
    assert {k: no[str(v.id)]["motivo"] for k, v in {
        "sin_leer": sin_leer, "sin_barrio": sin_barrio, "sin_zona": sin_zona,
        "sin_plantilla": sin_plantilla, "con_orden": con_orden,
        "cancelada": cancelada}.items()} == {
        "sin_leer": O.SIN_BARRIO_TODAVIA, "sin_barrio": O.SIN_BARRIO,
        "sin_zona": O.BARRIO_SIN_ZONA, "sin_plantilla": O.SIN_PLANTILLA,
        "con_orden": O.YA_TIENE_ORDEN, "cancelada": O.YA_TUVO_ORDEN}
    #  El barrio sin zona se NOMBRA: es lo que hay que ir a cargar.
    assert "OFICINA" in no[str(sin_zona.id)]["detalle"]
    #  La instalacion nueva se crea igual, sin barrio: llamar al cliente.
    n = crear[str(nueva.id)]
    assert (n["plantilla"], n["llamar_al_cliente"], n["barrio"]) == (
        "Instalacion", True, "")
    assert len(crear) == 2


def test_c2_despues_del_corte_sale_mañana(empresa, plantillas):
    antes = _caso(empresa, entro=_bogota(6, 11))
    despues = _caso(empresa, entro=_bogota(6, 13))

    crear, _, _ = _por_caso(O.decidir(empresa, A_LAS_3))

    assert crear[str(antes.id)]["para"] == "2026-10-06"
    assert crear[str(despues.id)]["para"] == "2026-10-07"


def test_c3_sin_hora_de_corte_dice_por_que_y_no_pone_dia(empresa, plantillas):
    ConfiguracionDeReparto.objects.filter(org=empresa).update(hora_de_corte=None)
    caso = _caso(empresa)

    salida = O.decidir(empresa, A_LAS_3)

    assert "hora de corte" in salida["porque"]
    assert _por_caso(salida)[0][str(caso.id)]["para"] == ""


def test_c4_la_labor_medida_no_la_pisa_el_asunto(empresa, plantillas):
    """Una visita medida de trabajos con un asunto de soporte: sale con la
    plantilla de su labor medida, no con la del asunto."""
    caso = _caso(empresa, grupo="")
    P.objects.filter(origen_id=str(caso.id)).update(
        tipo_senal=P.CASO_REQUIERE_VISITA,
        accion_propuesta="Despachar una visita de trabajos al cliente")

    crear, _, _ = _por_caso(O.decidir(empresa, A_LAS_3))

    assert (crear[str(caso.id)]["plantilla"], crear[str(caso.id)]["por"]) == (
        "Red", "labor")


# ---------------------------------------------------------------------------
# R · el corte de red
# ---------------------------------------------------------------------------

CORTE = {"puerto": "0/1/3", "onus_en_los_a_la_vez": 4, "causa_caida": "fibra"}


def test_r_una_orden_por_puerto(empresa, plantillas):
    #  Un asunto que ninguna plantilla tiene: la labor la decide el corte.
    primero = _caso(empresa, asunto="Sin servicio", creado=_bogota(4, 9),
                    medicion=CORTE)
    segundo = _caso(empresa, asunto="No tiene internet", creado=_bogota(5, 9),
                    medicion=CORTE)
    otro_puerto = _caso(empresa, asunto="No tiene internet",
                        medicion={**CORTE, "puerto": "0/1/4"})

    crear, _, atadas = _por_caso(O.decidir(empresa, A_LAS_3))

    #  El mas viejo lleva la orden, de obra de red; el otro va atado a el.
    assert crear[str(primero.id)]["corte_de_red"] is True
    assert (crear[str(primero.id)]["labor"], crear[str(primero.id)]["por"]) == (
        "Trabajos", "labor")
    assert atadas[str(segundo.id)]["a_caso"] == str(primero.id)
    assert atadas[str(segundo.id)]["a_ticket"] == primero.external_ticket_id
    assert str(otro_puerto.id) in crear


def test_r2_si_el_puerto_ya_tiene_orden_todos_se_atan_a_ella(
        empresa, plantillas):
    sin_orden = _caso(empresa, creado=_bogota(3, 9), medicion=CORTE)
    con_orden = _caso(empresa, creado=_bogota(5, 9), medicion=CORTE)
    _orden_de(empresa, con_orden, plantillas["red"])

    crear, no, atadas = _por_caso(O.decidir(empresa, A_LAS_3))

    assert atadas[str(sin_orden.id)]["a_caso"] == str(con_orden.id)
    assert no[str(con_orden.id)]["motivo"] == O.YA_TIENE_ORDEN
    assert crear == {}


# ---------------------------------------------------------------------------
# N · lo que no hace
# ---------------------------------------------------------------------------

def test_n_no_escribe_ni_le_pregunta_al_motor(empresa, plantillas):
    _caso(empresa)
    _caso(empresa, barrio=None)
    antes = (OrdenTrabajo.objects.count(),
             list(P.objects.order_by("id").values_list("evidencia", flat=True)))

    with mock.patch("campo.services.despacho.contexto_del_caso",
                    side_effect=AssertionError("no se le pregunta al motor")):
        O.decidir(empresa, A_LAS_3)

    assert (OrdenTrabajo.objects.count(),
            list(P.objects.order_by("id").values_list("evidencia", flat=True))
            ) == antes


def test_n2_otra_empresa_no(empresa, plantillas, org_b):
    from conftest import rls_org

    with rls_org(org_b):
        _caso(org_b)
    salida = O.decidir(empresa, A_LAS_3)
    assert salida["crear"] == salida["no_se_crea"] == salida["atadas"] == []


def test_n3_la_pantalla_la_pide_quien_gestiona(
        admin_client, user_client, empresa, plantillas):
    caso = _caso(empresa)

    r = admin_client.get(VISTA)
    assert r.status_code == 200
    assert [f["caso"] for f in r.json()["crear"]] == [str(caso.id)]
    assert user_client.get(VISTA).status_code == 403
