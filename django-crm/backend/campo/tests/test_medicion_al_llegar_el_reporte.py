# -*- coding: utf-8 -*-
"""
================================================================================
 LA SENAL SE MIDE AL LLEGAR EL REPORTE, NO UNA HORA DESPUES  --  06/11/2026
================================================================================
El usuario, leyendo la revision de la OT #184:

    «mira que dice que el supervisor mide despues de 1 hora y no debe ser asi
     el supervisor debe medir cuando le llega el reporte»

Tenia razon, y el hueco era mas fino de lo que el texto dejaba ver. El cierre
inmediato YA existia (`cerrar_esta_orden`, 31/10): el Supervisor miraba la
orden a los segundos. Lo que seguia colgado del ciclo horario era la MEDICION
de la senal. La aceleracion llegaba y se frenaba contra una pieza que nadie
habia acelerado -- y la revision mostraba «el Supervisor mide una vez por
hora», que para quien lo lee es una espera sin motivo.

QUE AFIRMA ESTA GUARDA
----------------------
  · que al llegar el reporte se MIDA -- el efecto, no que exista la funcion
  · que la medicion corra ANTES del cierre: si corriera despues, el cierre
    veria que falta y devolveria la orden a la espera, que es el bug entero
  · que NO sea una segunda puerta: lo que el ciclo horario descarta
    --un cambio de equipo-- se sigue descartando aca
  · que un fallo de la medicion no impida el intento de cierre
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
#  1) EL EFECTO: llega el reporte -> se mide
# ---------------------------------------------------------------------------

def test_al_llegar_el_reporte_SE_MIDE(org_a):
    """Lo que el usuario pidio, afirmado sobre el efecto.

    Se mira que `revisar_el_cierre_ya` llame a la medicion de ESTA orden. Que
    la funcion exista no prueba nada: antes de hoy existia `verificar_los
    _arreglos` y tampoco se disparaba al llegar el reporte.
    """
    from campo import tasks as T

    orden = mock.Mock(org_id=str(org_a.id), id="x", org=org_a)
    with mock.patch("campo.models.OrdenTrabajo.objects") as objs, \
         mock.patch("common.tasks.set_rls_context"), \
         mock.patch("common.tasks.clear_rls_context"), \
         mock.patch("operaciones.verificacion_de_arreglos.medir_este_arreglo",
                    return_value={"medida": True}) as medir, \
         mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    return_value={"resultado": "cerrada"}):
        objs.get.return_value = orden
        T.revisar_el_cierre_ya(str(org_a.id), "x")

    assert medir.call_count == 1, "el reporte llego y nadie midio la senal"


def test_la_medicion_va_ANTES_del_cierre(org_a):
    """EL ORDEN ES EL BUG.

    Si la medicion corriera despues del cierre, el cierre leeria la revision
    sin la medicion, diria «todavia no se midio» y devolveria la orden a la
    espera -- exactamente lo que el usuario estaba viendo. Que las dos se
    llamen no alcanza: importa cual primero.
    """
    from campo import tasks as T

    orden = mock.Mock(org_id=str(org_a.id), id="x", org=org_a)
    quien_llamo = []
    with mock.patch("campo.models.OrdenTrabajo.objects") as objs, \
         mock.patch("common.tasks.set_rls_context"), \
         mock.patch("common.tasks.clear_rls_context"), \
         mock.patch("operaciones.verificacion_de_arreglos.medir_este_arreglo",
                    side_effect=lambda *a, **k: quien_llamo.append("medir")), \
         mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    side_effect=lambda *a, **k: quien_llamo.append("cerrar")):
        objs.get.return_value = orden
        T.revisar_el_cierre_ya(str(org_a.id), "x")

    assert quien_llamo == ["medir", "cerrar"], quien_llamo


def test_si_la_medicion_FALLA_el_cierre_se_intenta_igual(org_a):
    """La medicion es una mejora; el cierre puede darse por otro camino.

    Y el ciclo horario sigue siendo la red de atras para la medicion.
    """
    from campo import tasks as T

    orden = mock.Mock(org_id=str(org_a.id), id="x", org=org_a)
    with mock.patch("campo.models.OrdenTrabajo.objects") as objs, \
         mock.patch("common.tasks.set_rls_context"), \
         mock.patch("common.tasks.clear_rls_context"), \
         mock.patch("operaciones.verificacion_de_arreglos.medir_este_arreglo",
                    side_effect=RuntimeError("el proveedor no esta")), \
         mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    return_value={"resultado": "cerrada"}) as cerrar:
        objs.get.return_value = orden
        r = T.revisar_el_cierre_ya(str(org_a.id), "x")

    assert cerrar.call_count == 1, "un fallo de la medicion tumbo el cierre"
    assert r["resultado"] == "cerrada"


# ---------------------------------------------------------------------------
#  2) NO ES UNA SEGUNDA PUERTA
# ---------------------------------------------------------------------------

def test_lo_que_el_ciclo_descarta_tambien_se_descarta_aca(org_a):
    """La cola sale de `candidatas()`, la MISMA del ciclo horario.

    Si `candidatas` no trae la orden --no es falla de servicio, es un cambio
    de equipo, se paso la ventana de dos dias, se agotaron los reintentos--
    aca no se mide y no se le habla al proveedor. Una aceleracion que midiera
    mas cosas que el ciclo seria una puerta nueva, no una aceleracion.
    """
    from operaciones import verificacion_de_arreglos as VA

    orden = mock.Mock(org=org_a, id="la-que-no-entra")
    with mock.patch.object(VA, "candidatas", return_value=[]), \
         mock.patch("operaciones.medicion_de_fallas._medir_con_el_motor") as m:
        r = VA.medir_este_arreglo(orden)

    assert r["medida"] is False
    assert m.call_count == 0, "se le hablo al proveedor por una orden que el ciclo descarta"


def test_solo_se_mide_LA_orden_pedida(org_a):
    """Si hay tres candidatas, se mide una: la que acaba de reportar.

    Sin este filtro, cada reporte dispararia la cola entera y el tope por
    vuelta --que existe para no hacer polling de un endpoint que el proveedor
    prohibe usar asi-- dejaria de significar nada.
    """
    from operaciones import verificacion_de_arreglos as VA

    orden = mock.Mock(org=org_a, id="la-mia")
    otra, caso = mock.Mock(), mock.Mock(external_service_id="999")
    mia, caso_mio = mock.Mock(), mock.Mock(external_service_id="5832")

    with mock.patch.object(VA, "candidatas", return_value=[
            (otra, caso, "otra-orden"),
            (mia, caso_mio, "la-mia"),
            (otra, caso, "tercera")]), \
         mock.patch("operaciones.medicion_de_fallas._medir_con_el_motor",
                    return_value={}) as m, \
         mock.patch("operaciones.medicion_de_fallas.de_la_respuesta",
                    return_value=None):
        VA.medir_este_arreglo(orden)

    assert m.call_count == 1, "se midio mas de una orden"
    assert m.call_args.args[1] == "5832", m.call_args


# ---------------------------------------------------------------------------
#  3) EL TEXTO YA NO PROMETE UNA HORA
# ---------------------------------------------------------------------------

def test_la_revision_ya_no_dice_una_vez_por_hora():
    """El texto que el usuario leyo y que ya no es verdad.

    No es cosmetica: quien lo lee decide si esperar. «Mide una vez por hora»
    hacia esperar una hora por algo que ahora sale en segundos.
    """
    import io
    import pathlib

    ruta = (pathlib.Path(__file__).resolve().parents[1] /
            "revision_del_cierre.py")
    fuente = io.open(ruta, encoding="utf-8").read()
    #  Solo en el texto que ve la persona: el comentario de la cabecera SI
    #  nombra la hora, y debe, porque cuenta que antes decia eso.
    assert '"Supervisor mide una vez por hora."' not in fuente
