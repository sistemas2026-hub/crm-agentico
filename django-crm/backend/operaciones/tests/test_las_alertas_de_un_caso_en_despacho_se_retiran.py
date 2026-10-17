"""
================================================================================
 LAS ALERTAS DE UN CASO QUE YA ESTA EN DESPACHO SE RETIRAN  --  17/10/2026
================================================================================

LO QUE AFIRMA
-------------
Que el Supervisor cancela, con motivo, la alerta de "caso abierto antiguo" de
un caso que ya esta en la cola de Despacho; que no toca nada mas; que no la
vuelve a proponer mientras el caso siga ahi; y que todo eso corre dentro de
'correr_ciclo', despues del paso a Despacho. Sobre el efecto en la fila, con
un caso de control en cada prueba.

POR QUE
-------
La noche del 16/10/2026 pasaron 15 casos a Despacho solos, y la bandeja de
Pendientes seguia pidiendo "revisar y priorizar" al menos tres de ellos: cada
uno tenia una alerta de caso abierto antiguo que nadie retiraba. Lo vio el
usuario en la pantalla.

'En Despacho' es la definicion de la pantalla de Despacho, que desde este
cambio vive en 'paso_a_despacho.casos_en_despacho' y la pantalla importa.
================================================================================
"""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from cases.models import Case
from common.models import Activity, Profile, User
from operaciones import areas_del_tenant as areas
from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

#  Datos que NO pueden aparecer en ningun texto que este cambio escriba.
NOMBRE_CLIENTE = "Zoraida Clientela"
TELEFONO = "3113683499"


@pytest.fixture
def tecnico(org_a, monkeypatch):
    """Un tecnico de soporte, y el mapa persona -> area como lo sirve el motor."""
    u = User.objects.create(email=f"t{uuid.uuid4().hex[:6]}@x.test",
                            name="Rigoberto Tecnicatura")
    t = Profile.objects.create(org=org_a, user=u, role="USER", is_active=True)
    monkeypatch.setattr(areas, "area_por_persona",
                        lambda: {str(t.id): "soporte_tecnico"})
    return t


def _caso(org, tecnico=None, *, status="Assigned", dias=10):
    """Un caso de soporte abierto hace 'dias' dias: una alerta de caso antiguo."""
    c = Case.objects.create(
        org=org, name="No tiene internet", status=status, priority="Normal",
        is_active=True, provider="wisphub", area="soporte_tecnico",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}", external_status="Nuevo",
        description=f"El cliente dice que no tiene internet. Tel {TELEFONO}.",
        external_client_name=NOMBRE_CLIENTE)
    Case.objects.filter(pk=c.pk).update(
        created_at=timezone.now() - timedelta(days=dias))
    if tecnico is not None:
        c.assigned_to.add(tecnico)
    c.refresh_from_db()
    return c


def _propuesta(org, caso, *, tipo, estado=P.PROPUESTA, revisada_hace_dias=0,
               origen_id=None):
    #  'revisar' escribe 'revisado_en' en toda decision, a mano o automatica.
    decidida = estado in (P.ACEPTADA, P.MODIFICADA, P.RECHAZADA)
    return P.objects.create(
        org=org, tipo_senal=tipo, origen_tipo="case",
        origen_id=origen_id or str(caso.id), estado=estado,
        revisado_en=(timezone.now() - timedelta(days=revisada_hace_dias)
                     if decidida else None),
        #  Como la redactaria quien lee el ticket: con lo que el ticket traia.
        #  Es lo que el renglon de la cancelacion NO debe repetir.
        accion_propuesta=f"Llamar a {NOMBRE_CLIENTE} al {TELEFONO}",
        motivo="x", prioridad=30,
        evidencia=[{"fuente": "caso", "id": str(caso.id), "dato": "z",
                    "observado_en": timezone.now().isoformat()}])


def _con_alerta(org, tecnico=None, *, tipo=P.TICKET_SIN_DIAGNOSTICO,
                estado=P.ACEPTADA, **kw):
    """Un caso con su lectura en 'estado' y una alerta de caso antiguo pendiente."""
    caso = _caso(org, tecnico, **kw)
    _propuesta(org, caso, tipo=tipo, estado=estado)
    return caso, _propuesta(org, caso, tipo=P.CASO_ANTIGUO)


def _estado(p):
    return P.objects.get(pk=p.pk).estado


def _retirar(org):
    return sup.retirar_alertas_de_casos_en_despacho(org, timezone.now())


# =============================================================================
#  §1  LA ALERTA DE UN CASO EN DESPACHO SE CANCELA; LA DE UNO QUE NO, SE QUEDA
# =============================================================================

def test_a_la_alerta_de_un_caso_en_despacho_se_cancela_con_motivo(org_a):
    caso, alerta = _con_alerta(org_a)
    _, control = _con_alerta(org_a, estado=P.PROPUESTA)

    assert _retirar(org_a) == 1

    assert _estado(alerta) == P.CANCELADA
    assert _estado(control) == P.PROPUESTA, (
        "una lectura sin decidir no pone el caso en Despacho")
    #  El renglon del feed lleva el id del caso y el motivo, y nada del
    #  ticket: el titulo es fijo, no la accion propuesta.
    renglon = (Activity.objects.filter(description=sup.YA_EN_DESPACHO)
               .latest("created_at"))
    motivo = (renglon.metadata or {}).get("motivo", "")
    assert sup.YA_EN_DESPACHO in motivo and str(caso.id) in motivo
    assert renglon.entity_name == sup.YA_EN_DESPACHO
    assert renglon.user_id is None, "retirar no es una decision de nadie"
    todo = " ".join([renglon.description, renglon.entity_name,
                     str(renglon.metadata)]).lower()
    for dato in (NOMBRE_CLIENTE, TELEFONO, "no tiene internet"):
        assert dato.lower() not in todo, f"se escribio {dato!r}"


@pytest.mark.parametrize(
    "tipo, estado, en_despacho",
    [
        pytest.param(P.TICKET_SIN_DIAGNOSTICO, P.MODIFICADA, True,
                     id="lectura_modificada"),
        pytest.param(P.CASO_REQUIERE_VISITA, P.ACEPTADA, True,
                     id="visita_aceptada"),
        pytest.param(P.TICKET_SIN_DIAGNOSTICO, P.RECHAZADA, False,
                     id="lectura_rechazada"),
        pytest.param(P.CASO_ANTIGUO, P.ACEPTADA, False,
                     id="caso_antiguo_aceptado"),
    ],
)
def test_b_en_despacho_es_la_regla_de_la_pantalla(org_a, tipo, estado,
                                                 en_despacho):
    """
    Los dos caminos a campo, aceptados o modificados. Rechazar es decir que
    no, y aceptar un caso antiguo no manda nada a Despacho.
    """
    caso, alerta = _con_alerta(org_a, tipo=tipo, estado=estado)

    assert (str(caso.id) in pad.ids_en_despacho(org_a)) is en_despacho
    _retirar(org_a)
    assert _estado(alerta) == (P.CANCELADA if en_despacho else P.PROPUESTA)


def test_c_un_caso_cerrado_no_esta_en_la_cola_y_su_alerta_se_queda(org_a):
    """La pantalla ya oculta las propuestas de un caso cerrado: no hay que retirarlas."""
    _, alerta = _con_alerta(org_a, status="Closed")

    assert _retirar(org_a) == 0
    assert _estado(alerta) == P.PROPUESTA


def test_d_las_otras_alertas_del_caso_no_se_tocan(org_a):
    caso, alerta = _con_alerta(org_a)
    visita = _propuesta(org_a, caso, tipo=P.CASO_REQUIERE_VISITA)

    _retirar(org_a)

    assert _estado(alerta) == P.CANCELADA
    assert _estado(visita) == P.PROPUESTA


def test_e_lo_que_una_persona_ya_decidio_queda_como_esta(org_a):
    caso = _caso(org_a)
    _propuesta(org_a, caso, tipo=P.TICKET_SIN_DIAGNOSTICO, estado=P.ACEPTADA)
    decidida = _propuesta(org_a, caso, tipo=P.CASO_ANTIGUO, estado=P.RECHAZADA)

    assert _retirar(org_a) == 0
    assert _estado(decidida) == P.RECHAZADA


def test_f_no_toca_otra_empresa_y_la_segunda_vuelta_no_hace_nada(org_a, org_b):
    """
    Bajo un rol que el RLS ata, los datos de cada empresa se crean y se leen
    con su propio contexto: desde la sesion de una, la otra ni se puede
    escribir. Con el superusuario de las pruebas el RLS no actua, y lo que
    cuida es el filtro por empresa: la prueba vale en los dos.
    """
    from conftest import set_rls_context

    set_rls_context(org_b)
    _, ajena = _con_alerta(org_b)
    set_rls_context(org_a)
    _, propia = _con_alerta(org_a)

    assert _retirar(org_a) == 1
    assert _estado(propia) == P.CANCELADA
    assert _retirar(org_a) == 0, "la segunda vuelta no tiene nada que retirar"
    set_rls_context(org_b)
    assert _estado(ajena) == P.PROPUESTA


# =============================================================================
#  §2  EL DETECTOR NO LA VUELVE A PROPONER MIENTRAS EL CASO SIGA EN DESPACHO
# =============================================================================

def test_g_el_detector_no_propone_un_caso_que_ya_esta_en_despacho(org_a,
                                                                  tecnico):
    """
    'cancelada' no bloquea repetir: sin esto, la alerta retirada volveria en
    la vuelta siguiente.
    """
    en_despacho = _caso(org_a, tecnico)
    _propuesta(org_a, en_despacho, tipo=P.TICKET_SIN_DIAGNOSTICO,
               estado=P.ACEPTADA)
    control = _caso(org_a, tecnico)

    ids = {s.origen_id
           for s in sup._casos_abiertos_antiguos(org_a, timezone.now())}

    assert str(control.id) in ids, (
        "sin el de control, una lista vacia tambien seria verde")
    assert str(en_despacho.id) not in ids


# =============================================================================
#  §3  CORRE DENTRO DE correr_ciclo, Y DESPUES DEL PASO
# =============================================================================

def test_h_correr_ciclo_la_retira_y_lo_cuenta(org_a, tecnico):
    """Codigo construido no es codigo que corre: tiene que pasar por 'correr_ciclo'."""
    _, alerta = _con_alerta(org_a, tecnico)

    resumen = sup.correr_ciclo(org_a)

    assert _estado(alerta) == P.CANCELADA
    assert resumen.get("alertas_retiradas_en_despacho") == 1


def test_i_un_caso_que_pasa_en_esta_vuelta_no_espera_a_la_siguiente(
        org_a, tecnico, monkeypatch):
    """
    El retiro corre DESPUES del paso a Despacho. El paso se reemplaza por uno
    que acepta la lectura, para no depender de sus puertas: si el retiro
    corriera antes, la alerta quedaria hasta la vuelta siguiente.
    """
    caso = _caso(org_a, tecnico)
    lectura = _propuesta(org_a, caso, tipo=P.TICKET_SIN_DIAGNOSTICO)
    alerta = _propuesta(org_a, caso, tipo=P.CASO_ANTIGUO)

    def _paso(org, ahora):
        #  Como 'revisar': el estado y la fecha de la decision.
        P.objects.filter(pk=lectura.pk).update(estado=P.ACEPTADA,
                                               revisado_en=timezone.now())
        return {}

    monkeypatch.setattr(sup, "_pasar_a_despacho_los_que_las_reglas_habiliten",
                        _paso)

    sup.correr_ciclo(org_a)

    assert _estado(alerta) == P.CANCELADA


# =============================================================================
#  §4  LO QUE NO ESTA EN LA COLA, Y LO QUE LLEVA DEMASIADO EN ELLA
# =============================================================================

@pytest.mark.parametrize("como", ["fusionado", "inactivo"])
def test_j_un_caso_fusionado_o_inactivo_no_esta_en_la_cola(org_a, como):
    """La pantalla no los lista: tampoco cuentan para retirar su alerta."""
    caso, alerta = _con_alerta(org_a)
    if como == "fusionado":
        Case.objects.filter(pk=caso.pk).update(merged_into=_caso(org_a))
    else:
        Case.objects.filter(pk=caso.pk).update(is_active=False)

    assert str(caso.id) not in pad.ids_en_despacho(org_a)
    assert _retirar(org_a) == 0
    assert _estado(alerta) == P.PROPUESTA


def test_k_un_origen_id_que_no_es_un_caso_no_rompe_nada(org_a, tecnico):
    """
    Una fila rara se ignora. Si rompiera, romperia el DETECTOR, que corre
    dentro de la transaccion del ciclo: se revertiria la vuelta entera.
    """
    caso, alerta = _con_alerta(org_a, tecnico)
    _propuesta(org_a, caso, tipo=P.TICKET_SIN_DIAGNOSTICO, estado=P.ACEPTADA,
               origen_id="no-es-un-caso")

    assert str(caso.id) in pad.ids_en_despacho(org_a)
    sup._casos_abiertos_antiguos(org_a, timezone.now())
    assert _retirar(org_a) == 1
    assert _estado(alerta) == P.CANCELADA


def test_l_un_caso_que_lleva_mas_de_siete_dias_en_despacho_vuelve_a_avisar(
        org_a, tecnico):
    """
    Sin un limite, la alerta de un caso despachado que nadie cierra se
    apagaria para siempre: la cola no tiene otra salida que cerrar el caso.
    Con el mismo corte que la alerta, el caso es antiguo otra vez.
    """
    viejo = _caso(org_a, tecnico, dias=20)
    _propuesta(org_a, viejo, tipo=P.TICKET_SIN_DIAGNOSTICO, estado=P.ACEPTADA,
               revisada_hace_dias=sup.DIAS_CASO_ANTIGUO + 1)
    alerta = _propuesta(org_a, viejo, tipo=P.CASO_ANTIGUO)
    reciente = _caso(org_a, tecnico, dias=20)
    _propuesta(org_a, reciente, tipo=P.TICKET_SIN_DIAGNOSTICO,
               estado=P.ACEPTADA, revisada_hace_dias=1)

    assert _retirar(org_a) == 0
    assert _estado(alerta) == P.PROPUESTA
    ids = {s.origen_id
           for s in sup._casos_abiertos_antiguos(org_a, timezone.now())}
    assert str(viejo.id) in ids, "lleva mas de siete dias en Despacho"
    assert str(reciente.id) not in ids, "entro hace un dia"
