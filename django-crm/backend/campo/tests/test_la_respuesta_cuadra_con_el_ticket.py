# -*- coding: utf-8 -*-
"""
================================================================================
 EL PUNTO NOVENO: ¿EL TRABAJO ES EL QUE SE PIDIO?  --  12/11/2026
================================================================================
El usuario:

    «debe haber relacion entre el asunto, la descripcion del ticket y la
     respuesta del tecnico. No puede haber una respuesta correcta en un
     asunto que ni por ahi iba al caso.»

Los ocho puntos que habia miran si el trabajo esta COMPLETO. Este mira si es
EL TRABAJO QUE SE PIDIO, que es otra pregunta.

EL CASO REAL, capturado en produccion el 12/11/2026 apenas salio la pieza 1:

  se pidio:  «El cliente pide el cambio de router wifi, NO POR UNA FALLA: el
              equipo esta EN LINEA y con SENAL BUENA.»
  que hizo:  «Potencia al llegar: -50.0 dBm. Que encontro: FIBRA PARTIDA.»

y los ocho puntos estaban en verde.

LA AFIRMACION MAS IMPORTANTE DE ESTE ARCHIVO
---------------------------------------------
**El punto nunca vale `False`.** `campo/inspeccion_visual.py:24-36`
(31/10/2026): un punto de IA en `False` produce veredicto `NO_CERRAR`, y eso
le daria a la IA el poder de negar el trabajo de un tecnico. Aca vale `True`
o `None`.

Y aun asi se cumple lo que el usuario pidio, porque `None` produce `REVISAR`
y una orden en `REVISAR` no cierra sola. La contradiccion FRENA la orden sin
que ninguna IA repruebe a nadie. Si alguna vez alguien cambia eso, el test
`test_NUNCA_VALE_FALSE` se pone rojo.

LO QUE NO SE MIDE ACA
----------------------
La conducta del modelo. Estas guardas escriben la fila de `CotejoDelReporte`
a mano y miden que hace el codigo con cada veredicto. Lo que el modelo
contesta tiene varianza y no corre en CI (CLAUDE.md §6); su lado esta en
`tests/test_cotejo_reporte_contra_ticket.py`, tambien sin llamarlo.

  pytest campo/tests/test_la_respuesta_cuadra_con_el_ticket.py --reuse-db --no-cov
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

CASO = ("El cliente pide el cambio de router wifi, no por una falla: el "
        "equipo esta en linea y con senal buena.")
REPORTE = ("Potencia al llegar: -50.0 dBm. Que encontro: fibra partida "
           "antes del conector.")


def _orden(org, numero):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"ck{numero}",
                                 nombre="Soporte Técnico", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        resumen=CASO, origen_sistema="crm", origen_tipo="case",
        origen_ref="91288", cliente_nombre="Beatriz Pinzón")
    EventoTrabajo.objects.create(
        org=org, orden=o, tipo="cierre_campo",
        datos={"respuestas": {"solucion": REPORTE}})
    return o


def _cotejo(orden, veredicto, motivo="", vuelta=None):
    from campo.cotejo_del_reporte import CotejoDelReporte

    return CotejoDelReporte.objects.create(
        org=orden.org, orden=orden,
        vuelta=orden.vuelta if vuelta is None else vuelta,
        veredicto=veredicto, motivo=motivo)


def _punto(orden):
    from campo import revision_del_cierre as RC

    r = RC.revisar(orden)
    return next((p for p in (r or {}).get("puntos", [])
                 if p["clave"] == "cuadra"), None), r


# ---------------------------------------------------------------------------
#  1) LA AFIRMACION QUE NO SE PUEDE PERDER
# ---------------------------------------------------------------------------

def test_NUNCA_VALE_FALSE(org_a):
    """La decision del 31/10/2026. Un punto de IA en `False` produce
    `NO_CERRAR`, y eso seria la IA negando el trabajo de un técnico.

    Se prueban los TRES veredictos en la misma guarda a propósito: lo que no
    puede pasar es que ALGUNO llegue a False, y probar solo el malo dejaría
    los otros dos sin cubrir."""
    from campo.cotejo_del_reporte import CUADRA, NO_CUADRA, NO_SE_SABE

    for i, v in enumerate((CUADRA, NO_CUADRA, NO_SE_SABE)):
        orden = _orden(org_a, 9930 + i)
        _cotejo(orden, v, motivo="lo que sea")
        p, _ = _punto(orden)
        assert p is not None, f"con veredicto '{v}' el punto no apareció"
        assert p["ok"] is not False, (
            f"el veredicto '{v}' produjo ok=False: la IA no puede negar el "
            f"cierre del trabajo de un técnico")


# ---------------------------------------------------------------------------
#  2) UNA CONTRADICCION FRENA LA ORDEN
# ---------------------------------------------------------------------------

def test_SI_NO_CUADRA_LA_ORDEN_NO_CIERRA_SOLA(org_a):
    """Lo que el usuario pidió, y el efecto que de verdad importa: no que el
    punto diga algo, sino que la orden deje de poder cerrarse sola."""
    from campo import revision_del_cierre as RC
    from campo.cotejo_del_reporte import NO_CUADRA

    orden = _orden(org_a, 9940)
    _cotejo(orden, NO_CUADRA,
            motivo="el ticket dice que el equipo estaba en línea y el "
                   "reporte describe una fibra partida")
    p, r = _punto(orden)

    assert p["ok"] is None
    assert r["veredicto"] == RC.REVISAR, (
        f"una contradicción tiene que dejar la orden en REVISAR, no en "
        f"{r['veredicto']}")


def test_Y_EL_MOTIVO_SALE_EN_EL_TEXTO_DEL_PUNTO(org_a):
    """«No cuadra» sin el porqué es una acusación sin evidencia: quien lee la
    tarjeta tiene que entender QUÉ no cuadra sin abrir nada más."""
    from campo.cotejo_del_reporte import NO_CUADRA

    orden = _orden(org_a, 9941)
    _cotejo(orden, NO_CUADRA,
            motivo="el ticket dice en línea y el reporte una fibra partida")
    p, _ = _punto(orden)

    assert "fibra partida" in p["texto"], p["texto"]


def test_SI_CUADRA_NO_ESTORBA(org_a):
    """Un trabajo que sí corresponde no puede frenar nada: el punto en True
    deja el veredicto como lo dejarían los otros ocho."""
    from campo import revision_del_cierre as RC
    from campo.cotejo_del_reporte import CUADRA

    orden = _orden(org_a, 9942)
    _cotejo(orden, CUADRA)
    p, r = _punto(orden)

    assert p["ok"] is True
    assert r["veredicto"] != RC.NO_CERRAR


# ---------------------------------------------------------------------------
#  3) LO QUE NO SE SABE SE DICE; LO QUE NO SE INTENTO, NO
# ---------------------------------------------------------------------------

def test_SIN_COTEJO_EL_PUNTO_NO_APARECE(org_a):
    """Una empresa que no encendió esto, o una orden que todavía no se
    cotejó, no puede ver un interrogante permanente: la gente aprende a
    ignorarlo y entonces tampoco ve el que importa."""
    orden = _orden(org_a, 9943)
    p, r = _punto(orden)

    assert p is None, "el punto apareció sin que hubiera cotejo"
    assert r is not None and r["puntos"], "y el resto de la revisión sigue"


def test_UN_NO_SE_SABE_SI_SE_DICE(org_a):
    """Distinto de lo anterior: acá SÍ se intentó y no alcanzó. Esa
    diferencia es la que le dice a una persona si vale la pena esperar."""
    from campo.cotejo_del_reporte import NO_SE_SABE

    orden = _orden(org_a, 9944)
    _cotejo(orden, NO_SE_SABE, motivo="el técnico no escribió qué hizo")
    p, _ = _punto(orden)

    assert p is not None and p["ok"] is None
    assert "no se pudo comparar" in p["texto"].lower()


# ---------------------------------------------------------------------------
#  4) APAGADO NO ES «NO SE SUPO»: ES «NO SE PREGUNTO»
# ---------------------------------------------------------------------------

def test_CON_EL_COTEJO_APAGADO_LA_ORDEN_SIGUE_CERRANDO(org_a):
    """EL DESASTRE QUE ESTO EVITA, encontrado antes de desplegar.

    `cotejar_y_anotar` corre en CADA cierre, tenga la empresa el cotejo
    encendido o no. Con la bandera apagada el motor contesta --bien--
    `no_se_sabe`. Si eso dejara una fila, el punto noveno la leería, valdría
    None, y el veredicto sería REVISAR: **toda orden de toda empresa que no
    encendió el cotejo dejaría de cerrarse sola**, por una función apagada.

    La guarda afirma el EFECTO sobre el veredicto, no que falte una fila:
    una fila puede faltar por diez motivos, y lo que no puede pasar es que
    una empresa sin el cotejo vea sus órdenes frenadas."""
    from unittest import mock

    from campo import revision_del_cierre as RC
    from campo.cotejo_del_reporte import CotejoDelReporte, cotejar_y_anotar

    orden = _orden(org_a, 9950)
    antes = RC.revisar(orden)["veredicto"]

    #  Lo que el motor contesta con la bandera apagada, tal cual.
    with mock.patch("campo.cotejo_del_reporte.cotejar",
                    return_value={"veredicto": "no_se_sabe", "apagado": True,
                                  "motivo": "esta empresa no tiene "
                                            "habilitado el cotejo",
                                  "error": ""}):
        cotejar_y_anotar(orden)

    assert not CotejoDelReporte.objects.filter(orden=orden).exists(), (
        "apagado dejó una fila: el punto noveno la va a leer")
    p, r = _punto(orden)
    assert p is None, "el punto apareció con el cotejo apagado"
    assert r["veredicto"] == antes, (
        f"una empresa SIN el cotejo encendido cambió de veredicto: "
        f"{antes} -> {r['veredicto']}")


def test_PERO_UN_NO_SE_SABE_DE_VERDAD_SI_DEJA_FILA(org_a):
    """La otra mitad, y sin ella la de arriba se «arregla» no escribiendo
    nunca. Si se preguntó y no se supo --el proveedor no contestó, el texto
    no alcanzaba--, eso SÍ queda: es la diferencia entre «no se miró» y «se
    miró y no se supo», que es la que le dice a una persona si vale la pena
    esperar."""
    from unittest import mock

    from campo.cotejo_del_reporte import CotejoDelReporte, cotejar_y_anotar

    orden = _orden(org_a, 9951)

    with mock.patch("campo.cotejo_del_reporte.cotejar",
                    return_value={"veredicto": "no_se_sabe", "apagado": False,
                                  "motivo": "el técnico no escribió qué hizo",
                                  "error": ""}):
        cotejar_y_anotar(orden)

    assert CotejoDelReporte.objects.filter(orden=orden).count() == 1
    p, _ = _punto(orden)
    assert p is not None and p["ok"] is None


# ---------------------------------------------------------------------------
#  5) LA VUELTA, Y QUE LEER NO CUESTA UNA LLAMADA
# ---------------------------------------------------------------------------

def test_EL_COTEJO_DE_UNA_VUELTA_ANTERIOR_NO_VALE(org_a):
    """Una orden devuelta y rehecha trae OTRO reporte. El veredicto del
    anterior hablaría de un texto que ya no está."""
    orden = _orden(org_a, 9945)
    _cotejo(orden, "no", motivo="de la vuelta 1", vuelta=1)
    orden.vuelta = 2
    orden.save(update_fields=["vuelta"])

    p, _ = _punto(orden)
    assert p is None, "se usó el cotejo de la vuelta anterior"


def test_REVISAR_NO_LLAMA_AL_MOTOR(org_a):
    """LA RAZÓN DE TODO EL DISEÑO. Programación se refresca cada 15 segundos
    y cada refresco pasa por `revisar()`. Si esto llamara al motor serían
    ~1.920 llamadas por orden y por día, por cada supervisor con la pantalla
    abierta.

    Se afirma sobre el EFECTO —que nadie salga a la red— y no sobre que
    exista una tabla: una tabla puede existir y consultarse igual."""
    from unittest import mock

    from campo.cotejo_del_reporte import CUADRA

    orden = _orden(org_a, 9946)
    _cotejo(orden, CUADRA)

    with mock.patch("requests.post") as post, mock.patch("requests.get") as get:
        for _ in range(3):
            _punto(orden)

    assert not post.called, "revisar() salió a la red con un POST"
    assert not get.called, "revisar() salió a la red con un GET"
