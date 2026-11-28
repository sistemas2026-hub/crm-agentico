# -*- coding: utf-8 -*-
"""
================================================================================
 LA REVISION VE EL TICKET QUE ORIGINO LA ORDEN  --  12/11/2026
================================================================================
El usuario:

    «debe haber relacion entre el asunto, la descripcion del ticket y la
     respuesta del tecnico. No puede haber una respuesta correcta en un
     asunto que ni por ahi iba al caso.»

`revisar()` evaluaba OCHO puntos --checklist, reporte, servicio, medicion,
material, fotos, potencia, rango-- y ninguno miraba el ticket. El tecnico
podia escribir cualquier cosa coherente consigo misma y los ocho daban verde,
porque no habia contra que compararla.

ES EL MISMO HUECO DEL 06/11, CON TEXTO EN VEZ DE FOTOS
-------------------------------------------------------
Ese dia el usuario pidio que el supervisor revisara si las fotos coinciden
con lo pedido, y la nota que quedo en `revisar()` lo dice entero: «el hueco
era de informacion, no de poder: el boton «Devolver al tecnico» ya existia,
pero esta lista mandaba solo el id y el titulo --sin las instrucciones y sin
la imagen--, asi que no habia con que comparar».

LO QUE ESTA GUARDA AFIRMA, Y LO QUE NO
---------------------------------------
Afirma el EFECTO: que el contenido del ticket LLEGA, con su texto, junto a lo
que el tecnico escribio. No afirma que la clave exista --una clave vacia pasa
esa prueba y no sirve para nada-- ni afirma ningun juicio: comparar es el
punto noveno (pieza 2), y esto es el insumo.

Se corre con Postgres real:
  pytest campo/tests/test_el_ticket_entra_a_la_revision.py --reuse-db --no-cov
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


CASO = ("Enviar a correctivo de red/planta externa: verificar el puerto 3/4/4 "
        "de la OLT, hay tres clientes en LOS a la vez.")


def _orden(org, numero, *, resumen=CASO, previo=None, asunto="Soporte Técnico"):
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org, codigo=f"tk{numero}", nombre=asunto,
                                 labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        #  `aplica()` pide las dos cosas: terminada en campo Y sin validar.
        #  Sin el segundo estado, `revisar()` devuelve None y la guarda mide
        #  la nada.
        estado_validacion=OrdenTrabajo.PENDIENTE,
        resumen=resumen,
        diagnostico_previo=previo or {},
        origen_sistema="crm", origen_tipo="case", origen_ref="91288",
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20")


# ---------------------------------------------------------------------------
#  1) EL CONTENIDO LLEGA, NO SOLO LA CLAVE
# ---------------------------------------------------------------------------

def test_EL_CASO_DEL_TICKET_LLEGA_CON_SU_TEXTO(org_a):
    """Lo que `resumen` trae en produccion es el caso: «verificar el puerto
    3/4/4...». Si esto llegara vacio, el punto noveno no tendria nada que
    comparar y daria por buena cualquier respuesta."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9900)
    t = RC.el_ticket(orden)

    assert t["caso"] == CASO, t
    assert "puerto 3/4/4" in t["caso"]


def test_EL_ASUNTO_SALE_DEL_TIPO_DE_TRABAJO(org_a):
    """El «asunto» del usuario es la categoria del trabajo. Sin el, «cambié el
    router» y «empalmé la fibra» se juzgan igual aunque el asunto diga
    «Instalacion nueva»."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9901, asunto="Cambio De Domicilio")

    assert RC.el_ticket(orden)["asunto"] == "Cambio De Domicilio"


def test_EL_NUMERO_DEL_TICKET_DEL_ISP_VIAJA(org_a):
    """Para que quien revisa pueda ir al ticket original sin buscarlo."""
    from campo import revision_del_cierre as RC

    assert "91288" in RC.el_ticket(_orden(org_a, 9902))["origen"]


# ---------------------------------------------------------------------------
#  2) EL DIAGNOSTICO PREVIO: HOY VACIO, Y SE LEE IGUAL
# ---------------------------------------------------------------------------

def test_EL_DIAGNOSTICO_PREVIO_SE_LEE_CUANDO_LO_HAY(org_a):
    """`crear_orden` acepta `diagnostico_previo` y NINGUNO de sus dos
    llamadores se lo pasa, asi que en produccion sale vacio en toda orden
    real (medido el 12/11/2026). Se lee igual: el dia que alguien lo llene,
    este camino ya lo trae y no hay que acordarse."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9903,
                   previo={"resumen": "ONT en LOS desde las 14:02, tres "
                                      "vecinos del mismo puerto tambien.",
                           "nap_sugerida": "NAP-1042"})

    t = RC.el_ticket(orden)
    assert "LOS desde las 14:02" in t["diagnostico_previo"]
    #  Solo su 'resumen': volcar el JSON entero meteria claves internas
    #  ('nap_sugerida') en una pantalla que se lee como prosa.
    assert "nap_sugerida" not in t["diagnostico_previo"]


def test_SIN_DIAGNOSTICO_PREVIO_NO_REVIENTA_NI_INVENTA(org_a):
    """El caso de toda orden real de hoy."""
    from campo import revision_del_cierre as RC

    t = RC.el_ticket(_orden(org_a, 9904, previo={}))
    assert t["diagnostico_previo"] == ""
    #  Y el caso sigue llegando: que falte uno no apaga al otro.
    assert t["caso"] == CASO


def test_UNA_ORDEN_SIN_RESUMEN_LO_DICE_VACIO_Y_NO_FALLA(org_a):
    """Las ordenes 1842-1844 de produccion tienen `resumen` vacio. Son datos
    de demostracion que quedaron ahi, pero el codigo no puede romperse con
    ellas."""
    from campo import revision_del_cierre as RC

    t = RC.el_ticket(_orden(org_a, 9905, resumen=""))
    assert t["caso"] == ""
    assert t["asunto"]  # el asunto sigue estando


# ---------------------------------------------------------------------------
#  3) LLEGA A `revisar()`, QUE ES LO QUE LA PANTALLA LEE
# ---------------------------------------------------------------------------

def test_LOS_DOS_LADOS_VIAJAN_JUNTOS_EN_LA_REVISION(org_a):
    """El punto de todo esto: que quien revisa --persona o modelo-- reciba en
    la MISMA respuesta lo que se pidio y lo que se hizo. Separados en dos
    pantallas, nadie los cruza; es lo que paso hasta hoy."""
    from campo import revision_del_cierre as RC
    from campo.models import EventoTrabajo

    orden = _orden(org_a, 9906)
    EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo="cierre_campo",
        datos={"respuestas": {
            "solucion": "Se preparó nuevamente el conector y se restableció "
                        "el servicio.",
            "que_encontro": "fibra partida antes del conector"}})

    r = RC.revisar(orden)

    assert r is not None
    #  EL TICKET
    assert "puerto 3/4/4" in r["el_ticket"]["caso"], r["el_ticket"]
    assert r["el_ticket"]["asunto"] == "Soporte Técnico"
    #  LO QUE EL TECNICO HIZO, en la misma respuesta
    assert "conector" in r["solucion"]
    assert ("fibra partida"
            in r["lo_que_el_tecnico_escribio"].get("que_encontro", ""))


def test_TRAER_EL_TICKET_NO_CAMBIA_NINGUN_VEREDICTO(org_a):
    """Esta pieza es INFORMACION, no poder (la leccion del 06/11). Si traerla
    moviera un veredicto, estaria juzgando sin que nadie lo haya decidido:
    comparar es la pieza 2, y ahi el punto vale True o None, nunca False."""
    from campo import revision_del_cierre as RC

    con = RC.revisar(_orden(org_a, 9907, resumen=CASO))
    sin = RC.revisar(_orden(org_a, 9908, resumen=""))

    assert con["veredicto"] == sin["veredicto"], (
        "el contenido del ticket movio el veredicto, y no debe")
    assert ([p["clave"] for p in con["puntos"]]
            == [p["clave"] for p in sin["puntos"]])
