# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- una accion no se da por buena porque el comando se haya mandado
================================================================================

    py -3.13 tests/test_verificacion_accion.py

POR QUE EXISTE
--------------
'reiniciar_ont' responde "Device reboot command sent" en medio segundo. Eso
dice que el comando salio, no que el equipo reinicio ni que volvio. Hasta el
02/09/2026 lo unico que separaba una cosa de la otra era que el modelo leyera
bien esa palabra -- y el modelo no tiene forma de saber lo que pasa en la
calle.

LA TRAMPA QUE ESTE ARCHIVO CUIDA
--------------------------------
La condicion obvia seria "si el ping responde, funciono". No sirve, y no es
opinion: la propia config del tenant lo tiene medido (15/08/2026), el MISMO
equipo sano devolvio '1 de 3', '2 de 3' y '3 de 3' en tres corridas seguidas.
Con esa varianza, comparar el ping de antes contra el de despues fabrica
confirmaciones por puro ruido.

Por eso lo que prueba el reinicio es un campo discreto -- el sello de la
ultima vez que el equipo cambio de estado -- y el ping se usa solo para lo
unico que no es ruido: si contesta o no contesta.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import Comprobacion                    # noqa: E402
from nucleo.seguimiento import verificacion_accion as va         # noqa: E402

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


# Las dos comprobaciones que el tenant declara para 'reiniciar_ont'.
COMPROBACIONES = [
    Comprobacion(herramienta="consultar_estado_ont", campo="last_status_change",
                 regla="cambio"),
    Comprobacion(herramienta="ping_cliente", campo="ping-exitoso",
                 regla="valores", valores=["1 de 3", "2 de 3", "3 de 3"]),
]


def estado(antes_sello, despues_sello, ping_despues, intento=3, max_intentos=3,
           antes_ping="1 de 3"):
    """Arma las dos mediciones con la forma REAL de cada proveedor."""
    antes = {
        "consultar_estado_ont": None if antes_sello is None
        else {"onu_status": "Online", "last_status_change": antes_sello},
        # ping_cliente devuelve una LISTA de diccionarios, no un dict plano.
        "ping_cliente": None if antes_ping is None
        else [{"ping-1": {"packet-loss": "0%"}}, {"ping-exitoso": antes_ping}],
    }
    despues = {
        "consultar_estado_ont": None if despues_sello is None
        else {"onu_status": "Online", "last_status_change": despues_sello},
        "ping_cliente": None if ping_despues is None
        else [{"ping-1": {"packet-loss": "0%"}}, {"ping-exitoso": ping_despues}],
    }
    return va.evaluar(COMPROBACIONES, antes, despues, intento, max_intentos)


print(__doc__.split("POR QUE EXISTE")[0])
print("=" * 70)
print(" VERIFICACION POSTERIOR A UNA ACCION")
print("=" * 70)

print()
print("CASO A -- el equipo reinicio y volvio")
res, por_que = estado("2026-09-02 10:00:00", "2026-09-02 10:06:12", "3 de 3")
print(f"      -> {res}: {por_que}")
afirmar(res == va.CONFIRMADA,
        "sello distinto + ping contestando = ACCION_CONFIRMADA")

print()
print("CASO B -- el comando salio y no paso nada")
res, por_que = estado("2026-09-02 10:00:00", "2026-09-02 10:00:00", "1 de 3")
print(f"      -> {res}: {por_que}")
afirmar(res == va.NO_CONFIRMADA,
        "mismo sello, con los intentos agotados = ACCION_NO_CONFIRMADA")

res, _ = estado("2026-09-02 10:00:00", "2026-09-02 10:00:00", "1 de 3",
                intento=1, max_intentos=3)
afirmar(res == va.PENDIENTE,
        "y con intentos por delante sigue PENDIENTE, no se condena de una")

print()
print("CASO C -- no se pudo medir")
res, por_que = estado("2026-09-02 10:00:00", None, "3 de 3")
print(f"      -> {res}: {por_que}")
afirmar(res == va.NO_VERIFICABLE,
        "si el instrumento no responde = NO_VERIFICABLE")
afirmar(res != va.NO_CONFIRMADA,
        "y NO se confunde con que la accion haya fallado")

res, _ = estado("2026-09-02 10:00:00", "2026-09-02 10:06:12", None)
afirmar(res == va.NO_VERIFICABLE,
        "aunque la OTRA comprobacion si haya dado bien: confirmar a medias es "
        "afirmar de mas")

res, _ = estado(None, "2026-09-02 10:06:12", "3 de 3")
afirmar(res == va.NO_VERIFICABLE,
        "sin medicion previa tampoco se inventa: no hay contra que comparar")

print()
print("EL RUIDO DEL PING NO PUEDE FABRICAR UNA CONFIRMACION")
# Este es el caso que motiva todo el archivo. El ping mejora de 1 a 3 de 3
# --cosa que el mismo equipo sano hace solo, medido-- y el equipo NO reinicio.
res, por_que = estado("2026-09-02 10:00:00", "2026-09-02 10:00:00", "3 de 3",
                      antes_ping="1 de 3")
print(f"      -> {res}: {por_que}")
afirmar(res == va.NO_CONFIRMADA,
        "el ping pasa de 1 a 3 de 3 pero el equipo no reinicio: NO confirmada")

print()
print("nada raro rompe la decision")
res, _ = va.evaluar([], {}, {}, 1, 3)
afirmar(res == va.NO_VERIFICABLE,
        "una herramienta sin comprobaciones declaradas no se confirma sola")
afirmar(va.buscar_campo([{"a": 1}, {"ping-exitoso": "2 de 3"}], "ping-exitoso")
        == "2 de 3",
        "el campo se encuentra dentro de la lista que devuelve el proveedor")
afirmar(va.buscar_campo(None, "lo_que_sea") is None,
        "una medicion vacia no explota")
afirmar(va.CONFIRMADA in va.TERMINALES and va.PENDIENTE not in va.TERMINALES,
        "solo los estados terminales dejan de medirse")

print()
print("LA MEDICION POSTERIOR NO PUEDE VENIR DEL CACHE")
# El motor cachea las lecturas dentro de un turno para no repetirlas. Las dos
# herramientas que miden son de solo lectura, o sea que en un turno normal
# CAERIAN en ese cache -- y devolver el ping de antes del reinicio daria por
# confirmado justo lo que hay que comprobar. Esto se guarda mirando el codigo
# porque no se puede afirmar leyendo la salida: un cache que responde se ve
# igual que una medicion fresca.
import ast                                                       # noqa: E402

_motor = (Path(__file__).resolve().parent.parent / "nucleo" / "modelo" / "motor.py")
_fuente = _motor.read_text(encoding="utf-8")
_arbol = ast.parse(_fuente)
_fn = next(n for n in _arbol.body
           if isinstance(n, ast.FunctionDef) and n.name == "medir_para_verificar")
_cuerpo = _fn.body[1:] if (_fn.body and isinstance(_fn.body[0], ast.Expr)
                           and isinstance(_fn.body[0].value, ast.Constant)) else _fn.body
_codigo = chr(10).join(ast.get_source_segment(_fuente, s) for s in _cuerpo)
afirmar("cache" not in _codigo,
        "el codigo que mide no toca ningun cache")
afirmar("_ejecutar_tool(" in _codigo,
        "despacha directo, sin pasar por la rama que cachea")

_lineas = _fuente.splitlines()
afirmar(next(i for i, l in enumerate(_lineas) if "cache_turno: dict" in l)
        > next(i for i, l in enumerate(_lineas) if l.startswith("def responder(")),
        "el cache nace dentro de responder(): vive un turno, y la medicion "
        "posterior ocurre en otro")

_api = (Path(__file__).resolve().parent.parent / "nucleo" / "canales" / "api.py"
        ).read_text(encoding="utf-8").splitlines()
afirmar(next(i for i, l in enumerate(_api) if "_resolver_verificacion_pendiente(config" in l)
        < next(i for i, l in enumerate(_api) if "medios_pendientes = motor.responder(" in l),
        "la comprobacion se resuelve ANTES de que el modelo redacte: su "
        "resultado tiene que estar en el contexto cuando escribe")

print()
print("=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden: el estado sale de las mediciones, no del modelo.")
print("=" * 70)
