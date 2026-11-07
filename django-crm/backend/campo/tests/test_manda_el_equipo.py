# -*- coding: utf-8 -*-
"""
================================================================================
 CUANDO EL EQUIPO Y EL NUMERO ESCRITO SE CONTRADICEN, MANDA EL EQUIPO
================================================================================
07/11/2026. El usuario cerro la OT #185 con -35.0 dBm escritos a mano, fuera
del rango bueno (-27 a -8), mientras SmartOLT media -20.65 dBm en la ONT. Al
preguntarle si eso debia frenar el cierre:

    «no, si esta midiendo bien en la OLT esta bien, y tambien debe comparar
    la foto del ticket»

Y tiene razon sobre quien sabe. El numero escrito es la transcripcion de una
persona que mira una pantalla; la lectura del equipo la da el equipo. Frenar
un cierre por la transcripcion es frenarlo por el eslabon mas debil.

PERO NO SE CALLA. Que no frene no lo vuelve irrelevante: 15 dBm de
diferencia entre lo escrito y lo medido es un dato malo en el ticket. Queda
en «miralo vos», con las tres lecturas que haya juntas en un renglon.

QUE AFIRMA ESTA GUARDA
----------------------
  · que con el equipo en rango el punto NO diga que no, y el cierre no se
    frene -- el efecto, no el texto
  · que igual aparezca, con las tres lecturas: equipo, foto y lo escrito
  · que SIN lectura del equipo siga frenando: lo contrario seria dejar pasar
    toda medida mala cada vez que la medicion no se pudo hacer, que es
    seguido
  · y que con el equipo FUERA de rango tambien frene -- ahi los dos coinciden
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

PISO, TECHO = -27.0, -8.0


def _orden(org, numero, *, al_salir="-35.0"):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"eq{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=9, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [], "campos": [
            {"id": "potencia_al_salir", "tipo": "decimal",
             "titulo": "Potencia al salir", "unidad": "dBm",
             "bueno": {"min": PISO, "max": TECHO}}]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={},
        datos={"potencia_al_salir": al_salir})
    cierre = EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": {"solucion": "se cambia conector"}})
    return orden, cierre


def _midio_el_equipo(orden, *, en_rango, dbm=None):
    """La pieza que el Supervisor deja tras medir contra el equipo."""
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    pieza = {"fuente": FUENTE, "orden": str(orden.id),
             "quedo_en_rango": en_rango}
    if dbm is not None:
        pieza["senal_dbm"] = dbm
    return PropuestaSupervisor.objects.create(
        org=orden.org, origen_id="caso-185",
        estado=PropuestaSupervisor.ACEPTADA, evidencia=[pieza])


def _con_foto(orden, texto):
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    evidencia = EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id="medicion_al_salir",
        vuelta=orden.vuelta, sha256=f"f{orden.numero}".ljust(64, "x")[:64],
        storage_key=f"k/{orden.numero}", nombre_original="f.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    AnalisisDeEvidencia.objects.create(
        org=orden.org, evidencia=evidencia, vuelta=orden.vuelta, texto=texto)


# ---------------------------------------------------------------------------
#  EL EQUIPO EN RANGO: NO FRENA
# ---------------------------------------------------------------------------

def test_con_el_equipo_en_rango_el_punto_NO_dice_que_no(org_a):
    from campo.revision_del_cierre import _en_rango, _cierre_de_esta_vuelta

    orden, cierre = _orden(org_a, 601)
    _midio_el_equipo(orden, en_rango=True, dbm=-20.65)

    p = _en_rango(orden, _cierre_de_esta_vuelta(orden) or cierre)

    assert p is not None, "callarse no es lo pedido: hay que mostrarlo"
    assert p["ok"] is None, p


def test_con_el_equipo_en_rango_el_CIERRE_NO_SE_FRENA(org_a):
    """El efecto. Que el punto diga `None` no prueba que el veredicto cambie."""
    from campo.revision_del_cierre import NO_CERRAR, revisar

    orden, _c = _orden(org_a, 602)
    _midio_el_equipo(orden, en_rango=True, dbm=-20.65)

    assert revisar(orden)["veredicto"] != NO_CERRAR


def test_el_punto_muestra_LAS_TRES_lecturas(org_a):
    """Equipo, foto y lo escrito: lo unico que permite decidir cual sobra."""
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 603, al_salir="-35.0")
    _midio_el_equipo(orden, en_rango=True, dbm=-20.65)
    _con_foto(orden, "la pantalla se lee: 1310 nm y -20.70 dBm")

    texto = _en_rango(orden, _cierre_de_esta_vuelta(orden))["texto"]

    assert "-20.65" in texto or "-20.7" in texto, texto   # el equipo
    assert "-20.7" in texto, texto                        # la foto
    assert "-35" in texto, texto                          # lo escrito


def test_sin_foto_igual_muestra_equipo_y_escrito(org_a):
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 604)
    _midio_el_equipo(orden, en_rango=True, dbm=-20.65)

    texto = _en_rango(orden, _cierre_de_esta_vuelta(orden))["texto"]

    assert "-20.65" in texto and "-35" in texto, texto


# ---------------------------------------------------------------------------
#  SIN EQUIPO QUE LA CONTRADIGA: SIGUE FRENANDO
# ---------------------------------------------------------------------------

def test_SIN_medicion_del_equipo_sigue_frenando(org_a):
    """Si no, toda medida mala pasa cada vez que la medicion no se pudo."""
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 605)

    p = _en_rango(orden, _cierre_de_esta_vuelta(orden))

    assert p["ok"] is False, p


def test_SIN_medicion_el_cierre_SE_FRENA(org_a):
    from campo.revision_del_cierre import NO_CERRAR, revisar

    orden, _c = _orden(org_a, 606)

    assert revisar(orden)["veredicto"] == NO_CERRAR


def test_con_el_equipo_FUERA_de_rango_tambien_frena(org_a):
    """Los dos coinciden en que la señal quedo mal."""
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 607)
    _midio_el_equipo(orden, en_rango=False, dbm=-35.0)

    assert _en_rango(orden, _cierre_de_esta_vuelta(orden))["ok"] is False


def test_con_la_medicion_SIN_VEREDICTO_tambien_frena(org_a):
    """`quedo_en_rango=None` es «no se pudo medir», no «esta bien»."""
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 608)
    _midio_el_equipo(orden, en_rango=None)

    assert _en_rango(orden, _cierre_de_esta_vuelta(orden))["ok"] is False


def test_la_medicion_DE_OTRA_ORDEN_no_la_salva(org_a):
    """La pieza trae el id de la orden; la del vecino no cuenta."""
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 609)
    otra, _c2 = _orden(org_a, 610)
    _midio_el_equipo(otra, en_rango=True, dbm=-20.65)

    assert _en_rango(orden, _cierre_de_esta_vuelta(orden))["ok"] is False


# ---------------------------------------------------------------------------
#  LO QUE NO CAMBIA
# ---------------------------------------------------------------------------

def test_una_medida_BUENA_sigue_diciendo_que_si(org_a):
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 611, al_salir="-18.0")

    assert _en_rango(orden, _cierre_de_esta_vuelta(orden))["ok"] is True


def test_UNA_propuesta_con_dos_ordenes_no_confunde_las_piezas(org_a):
    """El caso que el filtro del queryset NO alcanza.

    Una `PropuestaSupervisor` es del CASO, y su `evidencia` es una lista: puede
    llevar la medicion de varias ordenes. El filtro `evidencia__contains`
    encuentra la propuesta porque trae una pieza de esta orden, y a partir de
    ahi quien elige es el `next()` en Python.

    Medido el 07/11/2026: con una propuesta por orden, la mutacion que borra
    ese `orden == str(orden.id)` sobrevivia a las diez guardas. Con las dos
    piezas en la MISMA propuesta --y la ajena ultima, que es la que
    `reversed()` toca primero-- se muere.
    """
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE
    from campo.revision_del_cierre import _cierre_de_esta_vuelta, _en_rango

    orden, _c = _orden(org_a, 612)        # -35.0 escrito, sin medir
    vecina, _c2 = _orden(org_a, 613)
    PropuestaSupervisor.objects.create(
        org=org_a, origen_id="caso-compartido",
        estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[
            {"fuente": FUENTE, "orden": str(orden.id),
             "quedo_en_rango": None},
            #  LA AJENA VA ULTIMA: es la primera que `reversed()` toca.
            {"fuente": FUENTE, "orden": str(vecina.id),
             "quedo_en_rango": True, "senal_dbm": -20.65},
        ])

    p = _en_rango(orden, _cierre_de_esta_vuelta(orden))

    assert p["ok"] is False, (
        "se uso la medicion de la orden vecina para dejar pasar esta: " + str(p))
