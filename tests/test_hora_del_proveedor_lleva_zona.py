# -*- coding: utf-8 -*-
"""
================================================================================
 LA HORA DEL PROVEEDOR SALE DEL MOTOR CON SU ZONA  --  o sale tal como vino
================================================================================

Por que existe esta prueba
--------------------------
'last_status_change' sale de get_onu_status, que lo manda en hora LOCAL de la
instancia del proveedor y SIN offset ('2026-08-15 18:00:25'). Otro endpoint del
mismo proveedor manda el mismo instante CON offset.

Eso costo una conclusion equivocada el 15/08/2026: se comparo un
'last_status_change' de las 18:00 contra timestamps de la base (UTC, 23:0x) y
se concluyo que el reinicio habia sido "horas antes". Eran CINCO MINUTOS, y con
eso se descarto por error la causa real de un caso dorado en rojo.

Que se afirma
-------------
El EFECTO: que el valor que sale del motor traiga offset, y que el instante NO
se mueva al ponerselo. No se afirma que exista una funcion de normalizacion --
una prueba que dice que algo existe no prueba que funcione.

Y se afirma tambien lo que NO hace: sin zona resoluble, el valor sale crudo.
Inventarle una zona afirma un momento que puede estar cinco horas corrido, y
eso no lo nota nadie.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Se importa la funcion sola, sin levantar Flask: lo que se prueba es la
# normalizacion, no el servidor.
import importlib.util

_RUTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "nucleo", "canales", "api.py")


class ConfigFalsa:
    """Lo minimo que la funcion le pide a la configuracion de un tenant."""

    def __init__(self, zona_horaria="America/Bogota", variables=None):
        self.zona_horaria = zona_horaria
        self.variables_tenant = variables or {}


def _cargar_funcion():
    """
    Trae '_con_zona_declarada' sin ejecutar el modulo entero.

    api.py levanta una app Flask y abre conexiones al importarse. Lo que se
    prueba aca es una funcion pura, asi que se la extrae del arbol sintactico
    y se la compila sola. Si cambia de nombre, esta prueba falla -- y es lo
    correcto: una guarda que no encuentra lo que vigila tiene que decirlo, no
    pasar en verde.
    """
    import ast
    import io

    fuente = io.open(_RUTA, encoding="utf-8").read()
    arbol = ast.parse(fuente)

    piezas = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "_con_zona_declarada":
            piezas.append(nodo)
        if isinstance(nodo, ast.Assign):
            for t in nodo.targets:
                if isinstance(t, ast.Name) and t.id == "_CAMPOS_DE_EQUIPO_CON_HORA":
                    piezas.append(nodo)

    assert len(piezas) == 2, (
        "no se encontraron '_con_zona_declarada' y '_CAMPOS_DE_EQUIPO_CON_HORA' "
        "en api.py -- si se renombraron, esta prueba hay que actualizarla, "
        "no borrarla"
    )

    modulo = ast.Module(body=piezas, type_ignores=[])
    ambito = {"registrar": lambda *a, **k: None, "datetime": datetime}
    exec(compile(ast.fix_missing_locations(modulo), _RUTA, "exec"), ambito)
    return ambito["_con_zona_declarada"]


_con_zona_declarada = _cargar_funcion()


def _probar(nombre, condicion, detalle=""):
    estado = "OK  " if condicion else "FALLA"
    print(f"[{estado}] {nombre}" + (f"  --  {detalle}" if detalle and not condicion else ""))
    return condicion


def main():
    ok = []

    # ---------------------------------------------------------------- 1
    # Lo que llega SIN offset sale CON offset, y es el mismo instante.
    equipo = {"onu_status": "Offline",
              "last_status_change": "2026-08-15 18:00:25"}
    salida = _con_zona_declarada(dict(equipo), ConfigFalsa())
    valor = salida["last_status_change"]

    ok.append(_probar(
        "Sin offset, sale con offset",
        "-05:00" in valor,
        f"salio {valor!r}",
    ))

    leido = datetime.fromisoformat(valor)
    ok.append(_probar(
        "Los numeros NO se movieron (18:00 sigue siendo 18:00 alla)",
        (leido.hour, leido.minute) == (18, 0),
        f"salio {leido.hour}:{leido.minute:02d}",
    ))
    ok.append(_probar(
        "Y en UTC son las 23:00, que es el instante real",
        leido.utctimetuple().tm_hour == 23,
        f"UTC {leido.utctimetuple().tm_hour}",
    ))

    # ---------------------------------------------------------------- 2
    # Lo que YA venia con offset no se toca: es el otro contrato del mismo
    # proveedor, y volver a aplicarle una zona lo correria cinco horas.
    yaConZona = {"last_status_change": "2026-08-15T18:04:39-05:00"}
    salida = _con_zona_declarada(dict(yaConZona), ConfigFalsa())
    ok.append(_probar(
        "Lo que ya traia offset queda igual",
        datetime.fromisoformat(
            salida["last_status_change"]).utctimetuple().tm_hour == 23,
        f"salio {salida['last_status_change']!r}",
    ))

    # ---------------------------------------------------------------- 3
    # LA ZONA ES CONFIGURACION, no un valor fijo del pais de una empresa.
    equipo = {"last_status_change": "2026-08-15 18:00:25"}
    salida = _con_zona_declarada(
        dict(equipo),
        ConfigFalsa(variables={"SMARTOLT_ZONA_HORARIA": "America/Mexico_City"}),
    )
    ok.append(_probar(
        "La variable del tenant manda sobre su zona general",
        "-06:00" in salida["last_status_change"],
        f"salio {salida['last_status_change']!r}",
    ))

    # ---------------------------------------------------------------- 4
    # Lo que NO hace: inventar una zona.
    equipo = {"last_status_change": "2026-08-15 18:00:25"}
    salida = _con_zona_declarada(dict(equipo), ConfigFalsa(zona_horaria=""))
    ok.append(_probar(
        "Sin zona declarada, el valor sale CRUDO (no se adivina)",
        salida["last_status_change"] == "2026-08-15 18:00:25",
        f"salio {salida['last_status_change']!r}",
    ))

    salida = _con_zona_declarada(
        {"last_status_change": "2026-08-15 18:00:25"},
        ConfigFalsa(zona_horaria="No/Existe"),
    )
    ok.append(_probar(
        "Con una zona que no existe, tampoco se adivina",
        salida["last_status_change"] == "2026-08-15 18:00:25",
        f"salio {salida['last_status_change']!r}",
    ))

    salida = _con_zona_declarada(
        {"last_status_change": "ayer por la tarde"}, ConfigFalsa())
    ok.append(_probar(
        "Un formato ilegible se deja como esta",
        salida["last_status_change"] == "ayer por la tarde",
        f"salio {salida['last_status_change']!r}",
    ))

    # ---------------------------------------------------------------- 5
    # Los demas campos no se tocan.
    equipo = {"onu_status": "Online", "onu_signal_1490": "-21.19 dBm",
              "last_status_change": "2026-08-15 18:00:25"}
    salida = _con_zona_declarada(dict(equipo), ConfigFalsa())
    ok.append(_probar(
        "Solo se normaliza el campo de hora, el resto queda intacto",
        salida["onu_status"] == "Online"
        and salida["onu_signal_1490"] == "-21.19 dBm",
    ))
    ok.append(_probar(
        "Un equipo vacio no rompe nada",
        _con_zona_declarada({}, ConfigFalsa()) == {},
    ))

    print()
    if all(ok):
        print(f"[OK] {len(ok)} afirmaciones: la hora del proveedor sale con su zona.")
        return 0
    print(f"[FALLA] {ok.count(False)} de {len(ok)} afirmaciones no se cumplen.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
