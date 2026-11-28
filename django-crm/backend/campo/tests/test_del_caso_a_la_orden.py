# -*- coding: utf-8 -*-
"""
================================================================================
 DEL CASO A LA ORDEN: UNA SOLA TRADUCCION  --  21/10/2026
================================================================================

Fase 2.1 de SPEC/objetivos/supervisor-arma-la-jornada.md: lo que la vista de
«Despachar» hacia adentro, extraido a funciones para que el Supervisor (2.3)
traduzca el caso EXACTAMENTE como el boton. Sin cambio de conducta: las
pruebas de la vista (test_despacho_api, test_crear_orden_textos_largos, ...)
siguen afirmando lo de siempre; estas afirman las piezas.

  A  `ordenes_vivas_del_caso`: ni cerradas ni canceladas, solo del CRM, solo
     de esa empresa
  B  `cliente_para_la_orden`: lo escrito gana; si no, la ficha, recortada al
     largo de la columna; el telefono va con sus comas
  C  `anotar_labor_sugerida`: solo con ficha; nunca levanta

    pytest campo/tests/test_del_caso_a_la_orden.py
================================================================================
"""

from unittest import mock

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import despacho as D

pytestmark = pytest.mark.django_db


def _orden(org, ref, estado=OrdenTrabajo.ASIGNADA, origen="crm"):
    tipo = WorkType.objects.get_or_create(org=org, codigo="t", defaults={
        "nombre": "T", "labor": "correctivo"})[0]
    v = WorkTypeVersion.objects.get_or_create(
        work_type=tipo, version=1, defaults={
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"campos": [{"id": "x", "tipo": "texto"}]}})[0]
    o = D.crear_orden(org=org, profile=None, version=v,
                      cliente={"nombre": "Cliente"}, origen_sistema=origen,
                      origen_ref=ref)
    OrdenTrabajo.objects.filter(pk=o.pk).update(estado_operativo=estado)
    return o


# ---------------------------------------------------------------------------
# A · las ordenes vivas
# ---------------------------------------------------------------------------

def test_a_ni_cerradas_ni_canceladas_ni_de_otro_origen(org_a):
    viva = _orden(org_a, "caso-1")
    _orden(org_a, "caso-1", estado=OrdenTrabajo.CERRADA)
    _orden(org_a, "caso-1", estado=OrdenTrabajo.CANCELADA)
    _orden(org_a, "caso-1", origen="manual")
    _orden(org_a, "caso-2")
    assert list(D.ordenes_vivas_del_caso(org_a, "caso-1")) == [viva]


def test_a2_otra_empresa_no(org_a, org_b):
    _orden(org_a, "caso-1")
    assert not D.ordenes_vivas_del_caso(org_b, "caso-1").exists()


# ---------------------------------------------------------------------------
# B · el cliente
# ---------------------------------------------------------------------------

FICHA = {"servicio": 4986, "contexto_disponible": True,
         "cliente": {"nombre": "Ana", "telefono": "300 111 2222, 301 333 4444",
                     "direccion": "Calle " + "x" * 300}}


def test_b_sin_lo_escrito_va_la_ficha_recortada(org_a):
    c = D.cliente_para_la_orden(FICHA)
    assert c["nombre"] == "Ana"
    assert c["telefono"] == "300 111 2222, 301 333 4444"
    assert len(c["direccion"]) == 255
    assert c["id_abonado"] == "4986"


def test_b2_lo_escrito_gana(org_a):
    c = D.cliente_para_la_orden(FICHA, {"cliente_nombre": "Ana María",
                                        "cliente_direccion": "Cra 1",
                                        "cliente_detalle_acceso": "Apto 302"})
    assert (c["nombre"], c["direccion"], c["detalle_acceso"]) == (
        "Ana María", "Cra 1", "Apto 302")


def test_b3_sin_ficha_queda_vacio_y_no_rompe(org_a):
    c = D.cliente_para_la_orden({"contexto_disponible": False})
    assert c["nombre"] == c["telefono"] == c["direccion"] == c["id_abonado"] == ""


# ---------------------------------------------------------------------------
# B4 · DONDE QUEDA LA CASA  --  05/11/2026
#
# El ISP guarda UN texto; la orden guarda DOS numeros. Hasta hoy el punto solo
# salia de lo que tecleaba quien despacha, asi que una orden IMPORTADA --que no
# pasa por ningun formulario-- nacia siempre sin coordenadas y el mapa del
# Supervisor decia «sin ubicacion» con el dato cargado del otro lado.
#
# Lo que se prueba no es el parseo (eso vive en
# test_coordenadas_del_cliente.py): es que el par LLEGUE A LA ORDEN, y que una
# correccion hecha a mano no se pierda.
# ---------------------------------------------------------------------------

#  Forma real medida contra la API (05/11/2026), con los digitos cambiados.
CRUDO = "10.910800,-74.818600"
PUNTO = (10.9108, -74.8186)


def _con_punto(**extra):
    """Un contexto ya depurado, como lo deja `depurar_contexto`."""
    return {"servicio": 4986, "contexto_disponible": True,
            "cliente": {"nombre": "Ana"},
            "gps_lat": PUNTO[0], "gps_lng": PUNTO[1], **extra}


def test_b4_el_punto_de_la_ficha_llega_al_cliente_de_la_orden(org_a):
    c = D.cliente_para_la_orden(_con_punto())

    assert (c["gps_lat"], c["gps_lng"]) == PUNTO


def test_b4b_sin_punto_en_la_ficha_la_orden_queda_SIN_coordenadas(org_a):
    #  Y no con un cero, ni con el centro del barrio: una orden sin punto es
    #  lo que ya habia, y la pantalla dice «sin ubicacion», que es verdad.
    c = D.cliente_para_la_orden(FICHA)

    assert c["gps_lat"] is None and c["gps_lng"] is None


def test_b4c_lo_corregido_a_mano_GANA_sobre_la_ficha(org_a):
    #  Quien despacha pudo corregir un punto mal cargado mirando el mapa. Si
    #  la ficha lo pisara, esa correccion se perderia en el proximo despacho
    #  sin que nadie se entere.
    c = D.cliente_para_la_orden(_con_punto(),
                                {"gps_lat": 11.0, "gps_lng": -75.0})

    assert (c["gps_lat"], c["gps_lng"]) == (11.0, -75.0)


def test_b4d_un_cero_escrito_a_mano_NO_se_toma_por_ausente(org_a):
    #  `0.0` es la latitud del ecuador, y es falsy en Python: con un `or` en
    #  vez de una comparacion contra None, la ficha lo pisaria en silencio.
    c = D.cliente_para_la_orden(_con_punto(), {"gps_lat": 0.0, "gps_lng": 0.0})

    assert (c["gps_lat"], c["gps_lng"]) == (0.0, 0.0)


def test_b4e_la_orden_NACE_con_el_punto(org_a):
    """DE PUNTA A PUNTA: lo que importa es la fila, no el dict intermedio."""
    tipo = WorkType.objects.get_or_create(org=org_a, codigo="t4", defaults={
        "nombre": "T4", "labor": "correctivo"})[0]
    v = WorkTypeVersion.objects.get_or_create(
        work_type=tipo, version=1, defaults={
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"campos": [{"id": "x", "tipo": "texto"}]}})[0]

    orden = D.crear_orden(org=org_a, profile=None, version=v,
                          cliente=D.cliente_para_la_orden(_con_punto()),
                          origen_sistema="crm", origen_ref="caso-gps")

    guardada = OrdenTrabajo.objects.get(pk=orden.pk)
    assert (guardada.gps_lat, guardada.gps_lng) == PUNTO


def test_b4f_depurar_contexto_parsea_el_texto_y_NO_lo_congela(org_a):
    """El texto crudo no queda en el contexto: solo el par numerico.

    Si el texto se congelara, habria DOS copias del mismo punto --una que
    quien despacha puede corregir y otra que no-- y el comando de
    anonimizacion, que mira las columnas y no el JSONB, dejaria el domicilio
    intacto diciendo por pantalla que lo reemplazo.
    """
    snapshot = D.depurar_contexto({
        "cliente": {"nombre": "Ana", "coordenadas": CRUDO},
        "identidad": {"servicio": "4986"},
    })

    assert (snapshot["gps_lat"], snapshot["gps_lng"]) == PUNTO
    assert "coordenadas" not in snapshot["cliente"], (
        "el texto crudo no se congela: una sola representacion del punto")


def test_b4g_una_coordenada_que_no_se_entiende_no_inventa_la_clave(org_a):
    #  Fail-closed de punta a punta: `0,0` es el Golfo de Guinea y es valido.
    for malo in ("0,0", "", "lat 10.9 lng -74.8", None):
        snapshot = D.depurar_contexto({
            "cliente": {"nombre": "Ana", "coordenadas": malo},
            "identidad": {"servicio": "4986"},
        })
        assert "gps_lat" not in snapshot, f"{malo!r} no es una casa"
        assert "gps_lng" not in snapshot


# ---------------------------------------------------------------------------
# C · la labor sugerida
# ---------------------------------------------------------------------------

def test_c_solo_con_ficha():
    sin = {"contexto_disponible": False}
    D.anotar_labor_sugerida(sin, "Internet lento")
    assert "labor_sugerida" not in sin

    con = dict(FICHA)
    with mock.patch("operaciones.clasificacion_de_trabajo.clasificar",
                    return_value={"labor": "correctivo"}) as clasificar:
        D.anotar_labor_sugerida(con, "  Internet lento ")
    assert con["labor_sugerida"] == {"labor": "correctivo"}
    assert clasificar.call_args.kwargs["texto"] == "Internet lento"


def test_c2_si_clasificar_falla_no_levanta():
    con = dict(FICHA)
    with mock.patch("operaciones.clasificacion_de_trabajo.clasificar",
                    side_effect=RuntimeError("x")):
        D.anotar_labor_sugerida(con, "x")
    assert "labor_sugerida" not in con
