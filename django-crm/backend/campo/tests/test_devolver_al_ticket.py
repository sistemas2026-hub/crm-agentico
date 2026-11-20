"""
================================================================================
 LO QUE PASA EN CAMPO VUELVE AL TICKET  --  02/11/2026
================================================================================
`campo/devolver_al_ticket.py`. El usuario, con dos pantallas abiertas: *"ya ese
ticket se cerro en supervisor pero en ticket de dexter sigue abierto y sin
ningun diagnostico... deberian ser uno solo, no duplicar"*.

  D  al CERRAR la orden, el ticket se cierra y le queda la nota con lo que
     hizo el tecnico --el "diagnostico" que no aparecia--.
  U  UNA SOLA VEZ: cerrar dos veces no deja dos notas ni dos cierres.
  R  se RESPETA al que ya cerro: la nota queda, el estado no se toca.
  N  lo que NO corresponde: una orden sin ticket detras no hace nada, y un
     fallo del CRM NO impide cerrar la orden.
  C  el CAMINO REAL: `cerrar_orden` lo hace, no hay que acordarse de llamarlo.

    pytest campo/tests/test_devolver_al_ticket.py
================================================================================
"""
import datetime as dt
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from campo import devolver_al_ticket as D
from campo.models import EventoTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from cases.models import Case
from common.models import Activity, Comment

pytestmark = pytest.mark.django_db

_n = iter(range(7000, 9999))


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})


@pytest.fixture
def ticket(org_a):
    return Case.objects.create(
        org=org_a, name="Cambio De Contraseña En Router Wifi",
        status="New", priority="Normal")


def _orden(org, version, ticket=None, estado=OrdenTrabajo.COMPLETADA_CAMPO):
    return OrdenTrabajo.objects.create(
        org=org, numero=next(_n), tipo_trabajo_version=version,
        estado_operativo=estado,
        origen_sistema="crm" if ticket else "manual",
        origen_ref=str(ticket.pk) if ticket else "")


def _reporte(orden, texto="se cambia contraseña"):
    """Lo que el tecnico mando al cerrar en el telefono."""
    return EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="cierre_campo",
        datos={"respuestas": {"solucion": texto}})


def _mias(ticket):
    """SOLO las actividades que escribe este modulo. El ticket genera las
    suyas al crearse y al asignarse: contarlas todas media otra cosa."""
    return Activity.objects.filter(entity_type="Case", entity_id=ticket.pk,
                                   action=D.ACCION, metadata__fuente="campo")


def _notas(ticket):
    return Comment.objects.filter(
        content_type=ContentType.objects.get_for_model(Case),
        object_id=ticket.pk)


# ---------------------------------------------------------------------------
# D · el ticket se entera
# ---------------------------------------------------------------------------

def test_d_el_ticket_se_cierra_y_queda_el_diagnostico(org_a, version, ticket):
    """EL DEFECTO (02/11/2026): el ticket quedaba «Nuevo» con el plazo vencido
    hacia semanas mientras en Supervisor figuraba cerrado."""
    orden = _orden(org_a, version, ticket)
    _reporte(orden)

    r = D.devolver(orden)

    ticket.refresh_from_db()
    assert r["hecho"] is True
    assert ticket.status == "Closed"
    assert ticket.closed_on == timezone.localdate()
    assert ticket.resolved_at is not None
    nota = _notas(ticket).get()
    assert "se cambia contraseña" in nota.comment, "el diagnostico que faltaba"
    assert f"OT #{orden.numero}" in nota.comment, "y de que orden salio"
    assert nota.is_internal is True, "es el reporte del tecnico, no un mensaje al cliente"


def test_d2_queda_en_la_linea_de_tiempo_del_ticket(org_a, version, ticket):
    orden = _orden(org_a, version, ticket)
    _reporte(orden)

    D.devolver(orden)

    a = _mias(ticket).get()
    assert a.action == D.ACCION
    assert a.metadata["fuente"] == "campo"
    assert a.metadata["orden_numero"] == orden.numero
    assert a.metadata["cerro_el_ticket"] is True


def test_d3_sin_reporte_del_tecnico_la_nota_igual_dice_de_que_orden_salio(
        org_a, version, ticket):
    """Una orden sin reporte igual cerro: el ticket no puede quedarse sin
    rastro solo porque falto un texto."""
    orden = _orden(org_a, version, ticket)

    D.devolver(orden)

    nota = _notas(ticket).get()
    assert f"OT #{orden.numero}" in nota.comment
    assert Case.objects.get(pk=ticket.pk).status == "Closed"


# ---------------------------------------------------------------------------
# U · una sola vez
# ---------------------------------------------------------------------------

def test_u_cerrar_dos_veces_NO_deja_dos_notas(org_a, version, ticket):
    """Un reintento, una conciliacion o dos pestañas no pueden dejar el ticket
    con dos notas iguales."""
    orden = _orden(org_a, version, ticket)
    _reporte(orden)

    primera = D.devolver(orden)
    orden.refresh_from_db()
    segunda = D.devolver(orden)

    assert primera["hecho"] is True
    assert segunda == {"hecho": False, "motivo": "ya_devuelto"}
    assert _notas(ticket).count() == 1
    assert _mias(ticket).count() == 1


# ---------------------------------------------------------------------------
# R · se respeta al que ya cerro
# ---------------------------------------------------------------------------

def test_r_un_ticket_ya_cerrado_no_se_toca_pero_igual_recibe_la_nota(
        org_a, version, ticket):
    """A quien ya decidio no se le cambia su decision; el trabajo igual consta."""
    ayer = timezone.localdate() - dt.timedelta(days=1)
    Case.objects.filter(pk=ticket.pk).update(status="Closed", closed_on=ayer)
    orden = _orden(org_a, version, ticket)
    _reporte(orden)

    r = D.devolver(orden)

    ticket.refresh_from_db()
    assert r == {"hecho": True, "motivo": "ya_estaba_cerrado"}
    assert ticket.closed_on == ayer, "no se le pisa la fecha a quien ya cerro"
    assert _notas(ticket).count() == 1, "la nota queda igual"


# ---------------------------------------------------------------------------
# N · lo que no corresponde
# ---------------------------------------------------------------------------

def test_n_una_orden_sin_ticket_detras_no_hace_nada(org_a, version):
    orden = _orden(org_a, version, None)

    assert D.devolver(orden) == {"hecho": False, "motivo": "sin_ticket"}
    assert Comment.objects.count() == 0


def test_n2_un_ticket_de_OTRA_empresa_no_se_toca(org_a, org_b, version):
    ajeno = Case.objects.create(org=org_b, name="De otra empresa",
                                status="New", priority="Normal")
    orden = _orden(org_a, version, ajeno)

    r = D.devolver(orden)

    assert r == {"hecho": False, "motivo": "ticket_no_encontrado"}
    assert Case.objects.get(pk=ajeno.pk).status == "New"


def test_n3_si_el_CRM_falla_la_orden_igual_se_cierra(org_a, version, ticket):
    """CODIGO QUE NO PUEDE TUMBAR AL QUE LO LLAMA. Un ticket sin actualizar es
    un problema; una orden que no se puede cerrar porque el CRM tuvo un hipo
    es uno peor."""
    orden = _orden(org_a, version, ticket)

    with mock.patch("common.models.Comment.objects.create",
                    side_effect=RuntimeError("el CRM se cayo")):
        r = D.devolver(orden)

    assert r["hecho"] is False
    assert r["motivo"].startswith("error:"), r
    #  Y NO quedo la marca: cuando el CRM vuelva, se puede reintentar.
    orden.refresh_from_db()
    assert not (orden.contexto or {}).get(D.CLAVE)


# ---------------------------------------------------------------------------
# C · el camino real
# ---------------------------------------------------------------------------

def test_c_cerrar_la_orden_devuelve_al_ticket_SIN_que_nadie_lo_pida(
        org_a, version, ticket):
    """CODIGO CONSTRUIDO NO ES CODIGO QUE CORRE (CLAUDE.md §6). Lo que importa
    no es que la funcion exista: es que el cierre de verdad la ejecute. Va
    dentro de `cerrar_orden` para que ningun camino --la pantalla, el
    Supervisor, o uno nuevo-- herede el olvido."""
    from campo.services.transiciones import cerrar_orden

    orden = _orden(org_a, version, ticket)
    _reporte(orden, "se habilita acceso remoto y se cambia contraseña")

    cerrar_orden(orden)

    ticket.refresh_from_db()
    assert ticket.status == "Closed", "nadie llamo a devolver() a mano"
    assert "acceso remoto" in _notas(ticket).get().comment
