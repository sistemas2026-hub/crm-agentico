# -*- coding: utf-8 -*-
"""
================================================================================
 LAS HERRAMIENTAS TECNICAS DEL SUPERVISOR  --  WispHub por el motor, filtrado
================================================================================

QUE SE PRUEBA
-------------
El chat del Supervisor incorpora cuatro herramientas tecnicas del catalogo del
tenant ('consultar_ticket', 'consultar_tickets_de_cliente',
'consultar_tecnicos', 'consultar_cliente'). No se reimplementan: se piden por
'POST /interno/herramienta/<nombre>' del motor, que es el unico que tiene la
credencial de WispHub.

LAS TRES PROPIEDADES QUE JUSTIFICAN EL ARCHIVO
----------------------------------------------
  1. SIEMPRE SE PIDE LA POLITICA. Cada llamada pasa 'rol=supervisor_noc', y por
     eso el motor filtra antes de contestar. Una llamada sin rol devolveria la
     ficha cruda --54 campos, cuatro contrasenas, GPS-- y nadie se enteraria
     hasta leer una cedula en una respuesta.
  2. NO SE DUPLICA EL CATALOGO. El HTTP lo hace el caller que ya existia
     ('fuentes_adaptadores._pedirle_al_motor'), no una copia.
  3. UN FALLO SE CONTESTA, NO SE CALLA. Si el motor no esta o la herramienta no
     esta declarada, el modelo recibe un error legible en vez de un turno
     muerto.

LO QUE SE SUSTITUYE, Y LO QUE NO
--------------------------------
Se sustituye UNA cosa: la peticion HTTP al motor. Todo lo demas --el
despachador, la lista blanca de argumentos, el tenant-- es real. El filtro de
campos NO se prueba aqui porque no vive aqui: vive en el motor y lo mide
'tests/test_politica_de_rol_ruta_interna.py' sobre la salida.
================================================================================
"""

from __future__ import annotations

from unittest import mock

import pytest

from common.models import Activity
from operaciones import chat_herramientas as ch

RUTA_CALLER = "operaciones.fuentes_adaptadores._pedirle_al_motor"

TECNICAS = ("consultar_ticket", "consultar_tickets_de_cliente",
            "consultar_tecnicos", "consultar_cliente")


# =============================================================================
#  §1  ESTAN, Y SE PUEDEN LLAMAR
# =============================================================================

def test_1_las_cuatro_estan_registradas_con_su_lista_blanca(org_a):
    for nombre in TECNICAS:
        assert nombre in ch.HERRAMIENTAS, nombre
        assert nombre in ch.ARGUMENTOS, f"{nombre} sin lista blanca"
        assert any(h["function"]["name"] == nombre for h in ch.esquema()), (
            f"{nombre} no esta en el esquema que ve el modelo")


def test_2_el_catalogo_son_19_y_las_dos_familias_conviven(org_a):
    """
    Las 15 operativas leen las tablas del Supervisor; las 4 tecnicas leen
    WispHub. La interseccion es cero y las dos tienen que estar.
    """
    assert len(ch.HERRAMIENTAS) == 19
    assert set(ch.ARGUMENTOS) == set(ch.HERRAMIENTAS)
    assert "listar_situaciones" in ch.HERRAMIENTAS
    assert "consultar_cliente" in ch.HERRAMIENTAS


# =============================================================================
#  §2  LA POLITICA SE PIDE SIEMPRE  --  la propiedad que mas importa
# =============================================================================

@pytest.mark.parametrize("nombre", TECNICAS)
def test_3_toda_tecnica_pide_la_politica_del_rol(org_a, nombre):
    """
    Se afirma sobre el EFECTO: el 'rol' con el que se llamo al motor. Sin eso,
    el motor no filtra y contesta la ficha cruda.
    """
    args = {"id_servicio": "5832"} if nombre == "consultar_cliente" else {}

    with mock.patch(RUTA_CALLER, return_value={"ok": True}) as caller:
        ch.ejecutar(org_a, nombre, args)

    assert caller.call_count == 1
    assert caller.call_args.kwargs.get("rol") == "supervisor_noc", (
        f"{nombre} no pidio la politica de campos")
    assert ch.ROL_POLITICA == "supervisor_noc"


def test_4_un_rol_vacio_no_es_una_llamada_valida(org_a):
    """
    El contrapunto de la propiedad 1: si alguien dejara el rol en blanco, el
    motor devolveria crudo. Esta prueba existe para que ese cambio se vea.
    """
    with mock.patch(RUTA_CALLER, return_value={"ok": True}) as caller:
        ch.ejecutar(org_a, "consultar_tecnicos", {})

    rol = caller.call_args.kwargs.get("rol")
    assert rol, "se llamo al motor SIN rol: la salida vendria sin filtrar"
    assert rol.strip() == rol and rol != ""


def test_5_no_se_duplica_el_HTTP(org_a):
    """
    §2: el caller es el que ya existia. Se afirma sobre el codigo: ni 'requests'
    ni una URL del motor aparecen en este modulo.
    """
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(ch))
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    assert "requests" not in nombres
    assert "httpx" not in nombres
    fuente = inspect.getsource(ch)
    assert "interno/herramienta" not in fuente.replace(
        "'POST /interno/herramienta/<nombre>'", "")


# =============================================================================
#  §3  LO QUE DEVUELVE
# =============================================================================

def test_6_la_salida_del_motor_se_pasa_tal_cual(org_a):
    """
    El filtro ya corrio del otro lado. Esta capa NO reinterpreta: si agregara o
    quitara algo, habria dos lugares decidiendo que ve el modelo.
    """
    filtrado = {"id_servicio": "5832", "estado": "Activo", "zona": "SABANAGRANDE"}

    with mock.patch(RUTA_CALLER, return_value=filtrado):
        salida = ch.ejecutar(org_a, "consultar_cliente",
                             {"id_servicio": "5832"})

    assert salida == filtrado


def test_7_un_descarte_del_filtro_llega_al_modelo(org_a):
    """
    Cuando el rol no tiene lista blanca para esa herramienta, el motor devuelve
    'Resultado descartado'. Eso se deja pasar: el modelo tiene que poder decir
    que no pudo consultarlo, en vez de recibir un hueco.
    """
    descarte = {"error": "El rol no tiene permitido consultar 'x'. "
                         "Resultado descartado."}

    with mock.patch(RUTA_CALLER, return_value=descarte):
        salida = ch.ejecutar(org_a, "consultar_tecnicos", {})

    assert salida == descarte


def test_8_sin_resultado_no_se_inventa_uno(org_a):
    with mock.patch(RUTA_CALLER, return_value=None):
        salida = ch.ejecutar(org_a, "consultar_tecnicos", {})

    assert salida["error"] == "SIN_RESULTADO"


# =============================================================================
#  §4  LOS FALLOS SE CONTESTAN
# =============================================================================

def test_9_si_la_herramienta_no_esta_declarada_se_dice(org_a):
    from operaciones.fuentes_adaptadores import _NoDeclarada

    with mock.patch(RUTA_CALLER,
                    side_effect=_NoDeclarada("no es invocable por servicio")):
        salida = ch.ejecutar(org_a, "consultar_ticket", {})

    assert salida["error"] == "HERRAMIENTA_NO_DISPONIBLE"
    assert "invocable" in salida["detalle"]


def test_10_si_el_motor_no_esta_el_turno_no_se_cae(org_a):
    from operaciones.fuentes_adaptadores import MotorNoDisponible

    with mock.patch(RUTA_CALLER,
                    side_effect=MotorNoDisponible("no se pudo preguntar")):
        salida = ch.ejecutar(org_a, "consultar_tecnicos", {})

    assert salida["error"] == "MOTOR_NO_DISPONIBLE"


def test_11_consultar_cliente_sin_id_no_gasta_una_llamada(org_a):
    with mock.patch(RUTA_CALLER) as caller:
        salida = ch.ejecutar(org_a, "consultar_cliente", {"id_servicio": "  "})

    assert salida["error"] == "FALTA_ID_SERVICIO"
    caller.assert_not_called()


# =============================================================================
#  §5  FAIL-CLOSED EN LOS ARGUMENTOS
# =============================================================================

def test_12_un_argumento_inventado_no_llega_al_motor(org_a):
    """
    La lista blanca de 'ejecutar' descarta lo que no esta declarado. Sin esto,
    un 'cedula=...' dictado en un mensaje viajaria como parametro de consulta.
    """
    with mock.patch(RUTA_CALLER, return_value={"ok": True}) as caller:
        ch.ejecutar(org_a, "consultar_cliente",
                    {"id_servicio": "5832", "cedula": "1234567890",
                     "campos": "todos"})

    enviados = caller.call_args.args[1]
    assert enviados == {"id_servicio": "5832"}
    assert "cedula" not in enviados


def test_13_las_que_no_aceptan_argumentos_no_los_reenvian(org_a):
    """
    'consultar_tecnicos' y 'consultar_tickets_de_cliente' no declaran ninguno.
    El motor los ignoraria igual, pero no se le manda basura.
    """
    for nombre in ("consultar_tecnicos", "consultar_tickets_de_cliente"):
        with mock.patch(RUTA_CALLER, return_value={"ok": True}) as caller:
            ch.ejecutar(org_a, nombre, {"id_servicio": "9", "limite": 5})
        assert caller.call_args.args[1] == {}, nombre


# =============================================================================
#  §6  NO ESCRIBEN, Y NO CRUZAN EMPRESAS
# =============================================================================

def test_14_ninguna_tecnica_escribe_una_fila(org_a):
    from operaciones.chat_modelos import ConversacionSupervisor
    from operaciones.models import PropuestaSupervisor
    from operaciones.situaciones_modelos import SituacionOperativa

    antes = (Activity.objects.count(), PropuestaSupervisor.objects.count(),
             SituacionOperativa.objects.count(),
             ConversacionSupervisor.objects.count())

    with mock.patch(RUTA_CALLER, return_value={"ok": True}):
        for nombre in TECNICAS:
            args = ({"id_servicio": "5832"}
                    if nombre == "consultar_cliente" else {})
            ch.ejecutar(org_a, nombre, args)

    assert (Activity.objects.count(), PropuestaSupervisor.objects.count(),
            SituacionOperativa.objects.count(),
            ConversacionSupervisor.objects.count()) == antes


def test_15_el_tenant_del_motor_no_lo_elige_el_modelo(org_a, org_b):
    """
    La empresa a la que se le consulta sale de 'MOTOR_TENANT', del entorno del
    servicio -- no de un argumento. Se afirma sobre lo que se le manda al
    caller: ni el org ni nada parecido viaja ahi.
    """
    with mock.patch(RUTA_CALLER, return_value={"ok": True}) as caller:
        ch.ejecutar(org_b, "consultar_tecnicos", {})

    assert caller.call_args.args[0] == "consultar_tecnicos"
    assert caller.call_args.args[1] == {}
    texto = str(caller.call_args)
    assert str(org_a.id) not in texto and str(org_b.id) not in texto


def test_16_una_desconocida_sigue_rechazandose(org_a):
    """El catalogo sigue cerrado: agregar cuatro no abrio la puerta."""
    with pytest.raises(ch.HerramientaDesconocida):
        ch.ejecutar(org_a, "consultar_lo_que_sea", {})
