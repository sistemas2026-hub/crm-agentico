# -*- coding: utf-8 -*-
"""La lista blanca de lo que sale de una herramienta de equipo.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
Hasta el 05/10/2026 `_estado_equipo` dejaba pasar **cualquier campo escalar**
que devolviera la herramienta. Con las dos livianas de siempre eso no hacia
daño: devuelven estado y niveles opticos.

El dia que entro `consultar_topologia_ont` --para contestar "¿en que caja esta y
en que puerto?", que es una de las llamadas al NOC mas frecuentes del tecnico--
eso dejo de ser inofensivo: esa respuesta trae `name`, que es el **nombre
completo del cliente** en el registro de la ONU. Sin lista blanca, ese nombre
habria entrado al contexto que se CONGELA en la orden de trabajo y se sincroniza
al telefono.

El panel de optica ya tenia su lista por esta misma razon. Esto la pone donde
faltaba, y esta prueba es lo que impide que se afloje despues.

QUE SE AFIRMA
-------------
1. Que los campos que la aplicacion de campo YA LEE siguen pasando. Cerrar la
   puerta no puede romper la pantalla que se queria arreglar.
2. Que el nombre del cliente NO pasa -- con los nombres reales que devuelve
   SmartOLT, no con uno inventado.
3. Que es fail-closed: un campo que nadie nombro no sale **aunque el proveedor
   lo agregue mañana**, que es el unico sentido de tener una lista.

Se afirma sobre el EFECTO --que filtra-- y no sobre que la constante exista.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _filtrar(datos: dict) -> dict:
    """Aplica exactamente el filtro de `_estado_equipo`, sin tocar la red.

    Se reimplementa la linea en vez de llamar a `_estado_equipo` porque esa
    funcion sale a hacer HTTP por cada herramienta de la configuracion. Lo que
    hay que medir es el FILTRO; montar un servidor falso para medir un `if`
    probaria menos y se romperia por motivos ajenos.

    La contrapartida honesta: si alguien cambia la linea de `_estado_equipo` sin
    tocar esto, la prueba no se entera. Por eso la guarda `test_z_...` de abajo
    compara las dos contra el codigo real.
    """
    from nucleo.canales.api import _CAMPOS_DE_EQUIPO

    return {
        k: v
        for k, v in datos.items()
        if k in _CAMPOS_DE_EQUIPO
        and isinstance(v, (str, int, float, bool))
        and v != ""
    }


#: Una respuesta de `get_onu_details` con la forma real, segun la skill de
#: SmartOLT (verificada en vivo el 14/08/2026). Incluye los campos peligrosos.
DETALLE_REAL = {
    "name": "CARLOS ELIECER DIAZ LAZO",
    "address_or_comment": "CALLE 38 # 78-33, APTO 302",
    "mobile_phone": "3005380776",
    "zone_name": "CANDELARIA 2",
    "odb_name": "CTO 56",
    "olt_id": 3,
    "olt_name": "OLT-RAPILINKSAS_X7",
    "board": 4,
    "port": 14,
    "onu": 17,
    "onu_type_name": "ZTE F660",
    "signal": "Very good",
    "signal_1310": -23.98,
    "signal_1490": -21.74,
    "status": "Online",
}


def test_a_los_campos_que_la_app_ya_lee_siguen_pasando():
    """Cerrar la puerta no puede romper la pantalla que se queria arreglar.

    Estos son los que `TrabajoVista._delEquipo` consulta hoy en la aplicacion de
    campo. Si uno dejara de pasar, la ficha mostraria "Dato no disponible" sobre
    un dato que el sistema tiene.
    """
    entrada = {
        "onu_status": "Online",
        "onu_signal": "Very good",
        "onu_signal_1310": -23.98,
        "onu_signal_1490": -21.74,
        "onu_signal_1490_veredicto": "aceptable",
        "distance": "1.2 km",
        "last_status_change": "2026-10-01 08:12:00",
        "board": 4,
        "port": 14,
        "onu": 17,
        "olt_name": "OLT-RAPILINKSAS_X7",
        "zone_name": "CANDELARIA 2",
        "odb_name": "CTO 56",
        "onu_type_name": "ZTE F660",
    }

    assert _filtrar(entrada) == entrada


def test_b_la_topologia_que_motivo_el_cambio_SI_pasa():
    """Las cuatro que contestan «¿en que caja y en que puerto?»."""
    salida = _filtrar(DETALLE_REAL)

    assert salida["odb_name"] == "CTO 56"
    assert salida["board"] == 4
    assert salida["port"] == 14
    assert salida["zone_name"] == "CANDELARIA 2"


def test_c_el_NOMBRE_DEL_CLIENTE_no_pasa():
    """LA MAS IMPORTANTE DEL ARCHIVO.

    `get_onu_details` trae el nombre completo del cliente en el registro de la
    ONU. Ese contexto se CONGELA en la orden y se sincroniza al telefono: una vez
    adentro, ya no sale.
    """
    salida = _filtrar(DETALLE_REAL)

    assert "name" not in salida
    entero = str(salida)
    assert "CARLOS" not in entero
    assert "DIAZ LAZO" not in entero


def test_d_la_direccion_y_el_telefono_tampoco():
    """Viajan en la misma respuesta. La direccion de la orden la pone el
    despacho; la del registro de la ONU es otra fuente y no tiene por que
    entrar por esta puerta."""
    salida = _filtrar(DETALLE_REAL)

    assert "address_or_comment" not in salida
    assert "mobile_phone" not in salida
    entero = str(salida)
    assert "3005380776" not in entero
    assert "CALLE 38" not in entero


def test_e_es_FAIL_CLOSED_con_un_campo_que_nadie_nombro():
    """El unico sentido de tener una lista.

    Si el proveedor agrega `customer_document` mañana, no sale -- y nadie tiene
    que acordarse de prohibirlo.
    """
    salida = _filtrar({
        "onu_status": "Online",
        "customer_document": "1012345678",
        "pppoe_password": "secreto",
        "campo_que_no_existe_todavia": "lo que sea",
    })

    assert salida == {"onu_status": "Online"}


def test_f_un_valor_vacio_no_entra_aunque_este_en_la_lista():
    """Un `odb_name` vacio es «no esta cargado», no «la caja se llama nada».

    Entra como clave presente haria que la pantalla dibuje la fila de la caja en
    blanco, que se lee como un dato que no cargo en vez de como uno que el
    sistema no tiene.
    """
    salida = _filtrar({"onu_status": "Online", "odb_name": "", "board": ""})

    assert salida == {"onu_status": "Online"}


def test_g_un_objeto_anidado_no_entra():
    """Solo escalares. Un objeto podria traer adentro cualquier cosa, y la lista
    nombra campos de primer nivel."""
    salida = _filtrar({
        "onu_status": "Online",
        "zone_name": {"id": 2, "name": "CANDELARIA 2", "owner": "Carlos Díaz"},
    })

    assert salida == {"onu_status": "Online"}


def test_z_la_herramienta_de_topologia_esta_pedida_de_verdad():
    """Que la lista deje pasar la caja no sirve si nadie pide la caja.

    Es la mitad que se olvida: el motor pedia dos herramientas y la topologia no
    estaba entre ellas, asi que esos campos NUNCA llegaban. Una prueba que solo
    midiera el filtro habria quedado en verde con el sintoma vivo.
    """
    from nucleo.canales.api import _HERRAMIENTAS_EQUIPO

    assert "consultar_topologia_ont" in _HERRAMIENTAS_EQUIPO
    # Y las dos de siempre siguen: agregar una no puede sacar otra.
    assert "consultar_estado_ont" in _HERRAMIENTAS_EQUIPO
    assert "consultar_senal_ont" in _HERRAMIENTAS_EQUIPO


def test_z2_el_filtro_de_esta_prueba_es_el_del_codigo():
    """La guarda de la guarda.

    `_filtrar` reimplementa la linea de `_estado_equipo` para no salir a la red.
    Esto comprueba que esa linea siga siendo la misma: sin esto, alguien podria
    aflojar el filtro real y las siete pruebas de arriba seguirian verdes.
    """
    import inspect

    from nucleo.canales import api

    fuente = inspect.getsource(api._estado_equipo)
    assert "_CAMPOS_DE_EQUIPO" in fuente, (
        "_estado_equipo dejo de usar la lista blanca"
    )
    assert "k in _CAMPOS_DE_EQUIPO" in fuente
    # Las OTRAS dos condiciones de la misma linea. Medido al mutar: sacar
    # `v != ""` del codigo real dejaba las ocho pruebas de arriba en VERDE,
    # porque el ayudante de este archivo tiene su propia copia. Una guarda que
    # solo mira un trozo de la linea protege solo ese trozo.
    assert 'v != ""' in fuente, (
        "_estado_equipo dejo de descartar los valores vacios"
    )
    assert "isinstance(v, (str, int, float, bool))" in fuente, (
        "_estado_equipo dejo de exigir que el valor sea un escalar"
    )


if __name__ == "__main__":
    import traceback

    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if not nombre.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"[OK]    {nombre}")
        except Exception:
            fallos += 1
            print(f"[FALLA] {nombre}")
            traceback.print_exc()
    print()
    print("todas en verde" if not fallos else f"{fallos} en rojo")
    sys.exit(1 if fallos else 0)
