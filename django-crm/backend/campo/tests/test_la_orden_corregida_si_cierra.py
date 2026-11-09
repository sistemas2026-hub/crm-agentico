# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE EL TECNICO CORRIGIO SE PUEDE CERRAR  --  09/11/2026
================================================================================
El usuario, sobre la OT 212, despues de que la devolucion automatica
funcionara:

    «ya hice la prueba, lo devolvio como se esperaba, y despues que el tecnico
     corrigio la foto pero no la cerro aunque tenia todo bien»

Y la tarjeta mostraba «El Supervisor reviso el cierre: Se puede cerrar» con
los siete puntos en verde. El veredicto no era el problema: la orden quedaba
fuera ANTES, en `revisadas`, por `vuelta__lte=1`.

POR QUE ESE FILTRO EXISTIA, Y POR QUE SE AFINA
----------------------------------------------
Lo puso la auditoria de frontera del 30/10/2026 (H4) con este motivo escrito:

    «Una orden ya DEVUELTA al tecnico (vuelta > 1): su ticket pudo cerrarse y
     reabrirse en el ISP en la vuelta anterior, y NADIE LO SABE DESDE ACA»

La condicion era la IGNORANCIA, no el numero de vuelta. Y el 30/10 las
devoluciones las hacia una persona; desde el 08/11 el Supervisor devuelve
ordenes el mismo, asi que existe una clase entera de ordenes devueltas cuyo
ticket Dexter JAMAS toco -- y eso se puede leer, porque cerrar el ticket del
ISP escribe `EVENTO_CERRADO`.

ESTO NO REVIERTE H4. Una orden en vuelta > 1 cuyo ticket si se cerro alguna
vez sigue exactamente igual de afuera. Lo que cambia es dejar de suponer por
el numero de vuelta lo que la bitacora dice con precision.

Y LO QUE SE AGREGA PORQUE ESTO SE ABRE: una sola devolucion automatica por
orden. Hasta hoy ese tope lo daba `vuelta__lte=1` sin decirlo; sin el, el
tecnico podria quedar en ping-pong con el Supervisor sin que nadie lo mire.

QUE AFIRMA ESTA GUARDA
----------------------
  · que la orden devuelta por el Supervisor, ya corregida, CIERRE -- el caso
    del usuario, de punta a punta
  · que la que SI tuvo su ticket cerrado siga afuera: H4, intacto
  · que una vuelta 1 normal no cambie en nada
  · que la segunda devolucion automatica NO pase, y quede para una persona
  · que una devolucion hecha POR UNA PERSONA no gaste ese unico intento
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def abierto(org_a, admin_profile, monkeypatch):
    """Las puertas del cierre autonomo, por el camino real."""
    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    td.delegar(org_a, td.CERRAR_LO_REVISADO, actor=admin_profile,
               pedido_textual="aprobá y cerrá lo que des por bueno")
    autonomia.cambiar(org_a, 3, actor=admin_profile,
                      motivo="cerrar lo revisado",
                      criterios="la revision del cierre en codigo")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion",
                        lambda org_id: "tenant-de-prueba")
    return org_a


@pytest.fixture(autouse=True)
def _nada_espera_medicion(monkeypatch):
    from campo import revision_del_cierre as RC

    monkeypatch.setattr(RC, "pendientes_de_medir",
                        lambda org, ahora=None: set())


def _orden(org, numero, *, vuelta):
    """Terminada y con todo bien: la revision dice «Se puede cerrar»."""
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"cor{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": [
            {"id": "foto_ont", "tipo": "foto", "titulo": "Foto de la ONT",
             "obligatorio": True}]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={}, vuelta=vuelta)
    EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="foto_ont", vuelta=vuelta,
        sha256=f"ont{numero}".ljust(64, "x")[:64],
        storage_key=f"k/ont{numero}", nombre_original="ont.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": vuelta,
               "respuestas": {"solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"},
               "sin_material_confirmado": True})
    return orden


def _evento(orden, tipo, datos=None):
    from campo.models import EventoTrabajo

    return EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                        datos=datos or {})


def _candidatas(org):
    from django.utils import timezone

    from campo.cierre_por_el_supervisor import revisadas

    return [o.numero for o, _ in (revisadas(org, timezone.now()) or [])]


# ---------------------------------------------------------------------------
#  1) EL CASO DEL USUARIO
# ---------------------------------------------------------------------------

def test_LA_CORREGIDA_POR_EL_TECNICO_CIERRA(abierto, org_a):
    """EL EFECTO, de punta a punta: el Supervisor la devolvio, el tecnico
    corrigio, y ahora cierra. Hasta hoy quedaba congelada en verde."""
    from campo.cierre_por_el_supervisor import cerrar_esta_orden
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 212, vuelta=2)
    _evento(orden, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(
            status_code=200, content=b"{}",
            json=lambda: {"cerrado": True, "resultado": "cerrado"})
        r = cerrar_esta_orden(orden)

    assert r["resultado"] == "cerrada", r
    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_validacion == OrdenTrabajo.APROBADO, \
        fresca.estado_validacion
    assert fresca.estado_operativo == OrdenTrabajo.CERRADA, \
        fresca.estado_operativo


def test_entra_a_las_candidatas_estando_en_vuelta_2(org_a):
    """La capa de abajo: el filtro. Si no entra aca, el veredicto no se mira."""
    orden = _orden(org_a, 213, vuelta=2)
    _evento(orden, "devuelta_por_el_supervisor")

    assert 213 in _candidatas(org_a)


# ---------------------------------------------------------------------------
#  2) H4 SIGUE EN PIE
# ---------------------------------------------------------------------------

def test_la_que_YA_CERRO_SU_TICKET_sigue_afuera(org_a):
    """LO QUE NO CAMBIA, y es la mitad del cambio.

    Si el ticket del ISP se cerro alguna vez, pudo reabrirse y nadie lo sabe
    desde aca. Esa orden queda para una persona, igual que el 30/10.

    LA DEVOLUCION DEL SUPERVISOR VA PUESTA, y no es decoracion: sin ella la
    orden quedaba afuera por el OTRO lado de la condicion, y esta guarda
    pasaba sin tocar el `~Q(id__in=ya_cerraron)` que dice proteger. Dos
    mutaciones sobrevivieron asi --volver a dejar entrar a la que ya cerro su
    ticket, y leer el id del EVENTO en vez del de la orden-- hasta que el
    caso se escribio con las dos condiciones a la vez.
    """
    from campo.services.cierre_en_isp import EVENTO_CERRADO

    orden = _orden(org_a, 214, vuelta=2)
    _evento(orden, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})
    _evento(orden, EVENTO_CERRADO, {"ticket": "9999"})

    assert 214 not in _candidatas(org_a)


def test_la_que_DEVOLVIO_UNA_PERSONA_sigue_afuera(org_a):
    """EL ACOTE QUE UNA GUARDA EXISTENTE OBLIGO A HACER.

    La primera version de este cambio dejaba entrar toda orden en vuelta > 1
    sin `EVENTO_CERRADO`, y puso en rojo a
    `test_v_una_orden_ya_devuelta_no_la_cierra_solo`. Tenia razon: si la
    devolvio una PERSONA, esa persona pudo cerrar el ticket a mano en
    WispHub, y de eso no hay fila que leer -- H4 entero.

    Solo la trayectoria que Dexter conoce de punta a punta entra: la que
    devolvio el propio Supervisor.
    """
    _orden(org_a, 222, vuelta=2)          # devuelta por una persona: sin evento

    assert 222 not in _candidatas(org_a)


def test_una_vuelta_1_NORMAL_no_cambia(org_a):
    _orden(org_a, 215, vuelta=1)

    assert 215 in _candidatas(org_a)


def test_una_vuelta_1_que_ya_cerro_su_ticket_TAMPOCO_se_toca(org_a):
    """El `exclude` es por las DOS condiciones a la vez. Una vuelta 1 que ya
    cerro su ticket no es el caso de H4 --no hubo devolucion en el medio-- y
    sigue entrando, como entraba antes de este cambio.
    """
    from campo.services.cierre_en_isp import EVENTO_CERRADO

    orden = _orden(org_a, 216, vuelta=1)
    _evento(orden, EVENTO_CERRADO, {"ticket": "8888"})

    assert 216 in _candidatas(org_a)


def test_el_ticket_cerrado_de_OTRA_orden_no_tapa_a_esta(org_a):
    """La consulta de los eventos es por org, no por orden: sin el filtro por
    orden, el primer ticket cerrado de la empresa congelaria todas las
    devueltas que vinieran despues."""
    from campo.services.cierre_en_isp import EVENTO_CERRADO

    otra = _orden(org_a, 217, vuelta=1)
    _evento(otra, EVENTO_CERRADO, {"ticket": "7777"})
    esta = _orden(org_a, 218, vuelta=2)
    _evento(esta, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})

    assert 218 in _candidatas(org_a)


# ---------------------------------------------------------------------------
#  3) UNA SOLA DEVOLUCION AUTOMATICA
# ---------------------------------------------------------------------------

def test_SE_DEVUELVE_LAS_VECES_QUE_HAGA_FALTA(org_a):
    """DECISION DEL USUARIO, 09/11/2026.

    Esta guarda afirmaba lo contrario hace una hora. Se escribio junto con un
    tope de una sola devolucion automatica --el que `vuelta__lte=1` daba sin
    decirlo-- y la primera prueba en vivo lo encontro: el usuario puso mal la
    foto del daño en una orden ya devuelta, «y esta vez no devolvio el ticket
    al tecnico». Preguntado entre devolver siempre, una sola vez, o dos o
    tres, eligio SIEMPRE.

    QUEDA ESCRITA EN VEZ DE BORRADA porque el tope tenia un motivo --que
    nadie se entere de que ya van tres-- y ese motivo sigue existiendo; lo
    que cambio es quien paga el costo. Lo que lo hace seguro es que no hay
    bucle que la maquina corra sola: una orden devuelta queda en
    CORRECCION_REQUERIDA y `revisadas` solo mira las COMPLETADA_CAMPO, asi
    que no vuelve a entrar hasta que EL TECNICO mande otro reporte.
    """
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo
    from campo.revision_del_cierre import NO_CERRAR

    orden = _orden(org_a, 219, vuelta=2)
    _evento(orden, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})
    revision = {"veredicto": NO_CERRAR, "sugeridas": ["foto_ont"],
                "puntos": []}

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        r = atender_la_que_no_cierra(orden, revision)

    assert r == "devuelta", r
    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert fresca.vuelta == 3, "la segunda devolucion no subio la vuelta"


def test_y_la_TERCERA_tambien(org_a):
    """«Siempre» quiere decir siempre: una guarda que solo mira la segunda
    pasaria en verde con un tope de dos puesto."""
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo
    from campo.revision_del_cierre import NO_CERRAR

    orden = _orden(org_a, 223, vuelta=3)
    _evento(orden, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})
    _evento(orden, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})
    revision = {"veredicto": NO_CERRAR, "sugeridas": ["foto_ont"],
                "puntos": []}

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        r = atender_la_que_no_cierra(orden, revision)

    assert r == "devuelta", r
    assert OrdenTrabajo.objects.get(pk=orden.pk).vuelta == 4


def test_una_orden_DEVUELTA_no_vuelve_a_entrar_sola_al_ciclo(org_a):
    """LO QUE HACE SEGURO NO TENER TOPE, afirmado en vez de razonado.

    Si `revisadas` alcanzara una orden en CORRECCION_REQUERIDA, el ciclo de
    cada hora la miraria de nuevo sin que el tecnico hiciera nada, y «sin
    tope» pasaria a significar una devolucion por hora para siempre. Lo que
    lo impide es el filtro por estado operativo.
    """
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 224, vuelta=2)
    _evento(orden, "devuelta_por_el_supervisor", {"requisitos": ["foto_ont"]})
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        estado_operativo=OrdenTrabajo.CORRECCION_REQUERIDA)

    assert 224 not in _candidatas(org_a)


def test_la_PRIMERA_devolucion_sigue_pasando(org_a):
    """El tope no puede comerse el caso que este mismo Supervisor resolvio
    ayer. Sin esta guarda, apagar la devolucion entera pasaria en verde."""
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo
    from campo.revision_del_cierre import NO_CERRAR

    orden = _orden(org_a, 220, vuelta=1)
    revision = {"veredicto": NO_CERRAR, "sugeridas": ["foto_ont"],
                "puntos": []}

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        r = atender_la_que_no_cierra(orden, revision)

    assert r == "devuelta", r
    assert OrdenTrabajo.objects.get(pk=orden.pk).vuelta == 2


def test_una_devolucion_HECHA_POR_UNA_PERSONA_no_gasta_el_intento(org_a):
    """Devolver a mano es una decision tomada, no un intento automatico.

    Si contara, un supervisor humano que devuelve una orden le quitaria al
    Supervisor su unica devolucion automatica sobre ella -- y el tope existe
    para frenar el ping-pong de la maquina, no el trabajo de la persona.
    """
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo
    from campo.revision_del_cierre import NO_CERRAR

    orden = _orden(org_a, 221, vuelta=2)
    #  La transicion que usa la pantalla, no la del Supervisor.
    _evento(orden, "correccion_requerida", {"requisitos": ["foto_ont"]})
    revision = {"veredicto": NO_CERRAR, "sugeridas": ["foto_ont"],
                "puntos": []}

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        r = atender_la_que_no_cierra(orden, revision)

    assert r == "devuelta", r
    assert OrdenTrabajo.objects.get(pk=orden.pk).vuelta == 3
