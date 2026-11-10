# -*- coding: utf-8 -*-
"""
================================================================================
 LA MISMA DEVOLUCION, DOS VECES  --  10/11/2026
================================================================================
MEDIDO EN LA BITACORA DE LA OT #218 (10/11, 11:58 Bogota)
----------------------------------------------------------
    11:58:20  correccion_requerida       vuelta_anterior=1  vuelta_nueva=2
    11:58:21  reapertura_correccion      vuelta=2
    11:58:21  correccion_requerida       vuelta_anterior=1  vuelta_nueva=2
    11:58:21  reapertura_correccion      vuelta=2
    11:58:21  devuelta_por_el_supervisor requisitos=[...]
    11:58:22  devuelta_por_el_supervisor requisitos=[...]

Las DOS dicen `vuelta_anterior=1`. Dos tareas leyeron la orden en la vuelta 1
--el reporte del tecnico y el "finalizar" son dos peticiones, segundos aparte,
y cada una despierta la fase-- y las dos escribieron la 2.

QUE LO DEJO PASAR
------------------
`_reclamar` cerro exactamente este choque para el CIERRE el 31/10 (H6).
`atender_la_que_no_cierra` nacio el 06/11, despues, y quedo como el unico
camino del Supervisor sin reclamo. `requerir_correccion` es
`@transaction.atomic`, y eso no alcanza: hace `orden.vuelta = vuelta_anterior
+ 1` sobre un objeto leido FUERA de la transaccion -- una actualizacion
perdida de manual.

LO QUE EL USUARIO VEIA
-----------------------
«solo me notifica una sola vez que la orden fue devuelta despues la mando y ya
no notifica pero la orden sigue devolviendose o apareciendo otra vez».
`avisar_devolucion` corre una vez por llamada: dos avisos por una devolucion.

QUE AFIRMAN ESTAS GUARDAS
--------------------------
El EFECTO sobre lo que queda escrito y lo que sale al tecnico, con el mismo
gesto que produjo el bug: DOS llamadas con el mismo objeto `orden`, que es lo
que tenian las dos tareas en la mano.

Y una afirma la CLAVE, no solo el conteo: la vuelta siguiente se tiene que
poder devolver. Reusar `_reclamar` --cuya marca dura 60 minutos-- habria
tapado este bug e introducido el inverso, que es el que el usuario reporto
primero.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


def _orden_devolvible(org, numero):
    """La OT #218 reducida: la foto del medidor es de catalogo."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"dd{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [],
                 "campos": [{"id": "potencia_al_llegar", "tipo": "decimal",
                             "titulo": "Medición al llegar",
                             "reglas": {"min": -60, "max": -8}}],
                 "evidencias": [{"id": "medicion_al_llegar", "tipo": "foto",
                                 "titulo": "Foto del medidor al llegar",
                                 "obligatorio": True}]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98009"},
        datos={"potencia_al_llegar": "-25.0"}, vuelta=1)
    evidencia = EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="medicion_al_llegar",
        vuelta=1, sha256=f"cat{numero}".ljust(64, "x")[:64],
        storage_key=f"k/cat{numero}", nombre_original="medidor.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    AnalisisDeEvidencia.objects.create(
        org=org, evidencia=evidencia, vuelta=1,
        origen=AnalisisDeEvidencia.IA,
        texto="Medidor óptico Rouhan de catálogo, sobre fondo blanco. "
              "Pantalla: 1550 nm, -25.00 dBm. No es evidencia del trabajo. "
              "CATALOGO: si MUESTRA: no ATENCION: si")
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1,
               "respuestas": {"potencia_al_llegar": "-25.0",
                              "solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"},
               "sin_material_confirmado": True})
    return orden


# ---------------------------------------------------------------------------
#  1) EL EFECTO: UNA SOLA DEVOLUCION
# ---------------------------------------------------------------------------

def test_DOS_TAREAS_A_LA_VEZ_DEVUELVEN_UNA_SOLA_VEZ(org_a):
    """La guarda del bug. El mismo objeto `orden` dos veces es exactamente lo
    que tenian las dos tareas en la mano a las 11:58:20 y 11:58:21."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import EventoTrabajo, OrdenTrabajo

    orden = _orden_devolvible(org_a, 9911)
    revision = RC.revisar(orden, pendientes=set())
    assert revision["sugeridas"] == ["medicion_al_llegar"], revision["sugeridas"]

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        primera = atender_la_que_no_cierra(orden, revision)
        segunda = atender_la_que_no_cierra(orden, revision)

    assert primera == "devuelta", primera
    assert segunda == "nada", segunda

    def cuantos(tipo):
        return EventoTrabajo.objects.filter(org=org_a, orden=orden,
                                            tipo=tipo).count()

    assert cuantos("correccion_requerida") == 1, "la devolucion se aplico dos veces"
    assert cuantos("reapertura_correccion") == 1
    assert cuantos("devuelta_por_el_supervisor") == 1

    #  LA VUELTA. En la #218 quedo en 2 por casualidad --las dos copias leyeron
    #  1-- pero la segunda tarea, un instante mas tarde, habria leido 2 y
    #  escrito 3, dejando al checklist esperando evidencia de una vuelta que
    #  nadie pidio.
    assert OrdenTrabajo.objects.get(pk=orden.pk).vuelta == 2


def test_Y_AL_TECNICO_LE_LLEGA_UN_SOLO_AVISO(org_a):
    """Lo que el usuario veia. `avisar_devolucion` corre una vez por llamada a
    `requerir_correccion`: sin el reclamo, dos avisos por una devolucion."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra

    orden = _orden_devolvible(org_a, 9912)
    revision = RC.revisar(orden, pendientes=set())

    with mock.patch("campo.services.avisos.avisar_devolucion") as avisar, \
            mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        atender_la_que_no_cierra(orden, revision)
        atender_la_que_no_cierra(orden, revision)

    assert avisar.call_count == 1, f"{avisar.call_count} avisos por una devolucion"


def test_Y_EL_TICKET_DEL_ISP_SE_ESCRIBE_UNA_SOLA_VEZ(org_a):
    """La nota tiene su clave idempotente, pero la segunda llamada igual
    gastaba una peticion contra el ISP y podia escribir la vuelta corrida."""
    from campo import revision_del_cierre as RC
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra

    orden = _orden_devolvible(org_a, 9913)
    revision = RC.revisar(orden, pendientes=set())

    with mock.patch("campo.services.nota_al_isp._pedir") as pedir:
        pedir.return_value = {"anotada": True, "codigo": "anotada"}
        atender_la_que_no_cierra(orden, revision)
        atender_la_que_no_cierra(orden, revision)

    assert pedir.call_count == 1, pedir.call_args_list


# ---------------------------------------------------------------------------
#  2) LA CLAVE: LA VUELTA, NO UNA VENTANA DE TIEMPO
# ---------------------------------------------------------------------------

def test_LA_VUELTA_SIGUIENTE_SI_SE_PUEDE_DEVOLVER(org_a):
    """EL BUG INVERSO, que es el que el usuario reporto primero: «la mando y ya
    no notifica». Si el reclamo durara 60 minutos como el del cierre, el
    tecnico corrige en minutos, manda otro reporte y su devolucion se perderia.

    Esta guarda mata la mutacion de reusar `_reclamar` aca.
    """
    from campo.cierre_por_el_supervisor import _reclamar_la_devolucion
    from campo.models import OrdenTrabajo

    orden = _orden_devolvible(org_a, 9914)

    assert _reclamar_la_devolucion(orden) is True
    assert _reclamar_la_devolucion(orden) is False, "la misma vuelta dos veces"

    #  El tecnico corrigio y mando otro reporte: la orden avanzo de vuelta.
    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=2)
    orden.refresh_from_db()

    assert _reclamar_la_devolucion(orden) is True, \
        "la vuelta 2 quedo sin poder devolverse"
    assert _reclamar_la_devolucion(orden) is False


def test_SI_ALGUIEN_YA_LA_MOVIO_el_reclamo_se_va(org_a):
    """Una PERSONA la devolvio desde la pantalla entre la revision y esto. El
    objeto en la mano quedo viejo, y subir la vuelta otra vez la adelantaria
    sin que nadie lo pidiera."""
    from campo.cierre_por_el_supervisor import _reclamar_la_devolucion
    from campo.models import OrdenTrabajo

    orden = _orden_devolvible(org_a, 9915)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=3)

    #  `orden.vuelta` sigue en 1 en memoria, como en la tarea.
    assert orden.vuelta == 1
    assert _reclamar_la_devolucion(orden) is False


def test_UNA_ORDEN_QUE_NO_SE_DEVUELVE_NO_DEJA_MARCA(org_a):
    """El reclamo va DESPUES de los filtros de veredicto y requisitos. Si
    quedara antes, cada pasada del ciclo escribiria una marca por orden."""
    from campo.cierre_por_el_supervisor import (EVENTO_DEVOLUCION_EN_CURSO,
                                                atender_la_que_no_cierra)
    from campo.models import EventoTrabajo

    orden = _orden_devolvible(org_a, 9916)
    #  Veredicto que no devuelve: sin nada concreto que pedir.
    revision = {"veredicto": "cerrar", "puntos": [], "sugeridas": []}

    assert atender_la_que_no_cierra(orden, revision) == "nada"
    assert not EventoTrabajo.objects.filter(
        org=org_a, orden=orden, tipo=EVENTO_DEVOLUCION_EN_CURSO).exists()
