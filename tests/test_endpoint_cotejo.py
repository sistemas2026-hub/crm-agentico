# -*- coding: utf-8 -*-
"""
================================================================================
 LA RUTA DEL COTEJO NO PUEDE CONTESTAR «SI» POR NINGUN CAMINO MALO  --  12/11
================================================================================
`/interno/cotejo/reporte-contra-ticket` le pregunta al modelo si lo que el
tecnico reporto explica el ticket. El modulo que decide ya tiene sus guardas
(`tests/test_cotejo_reporte_contra_ticket.py`); esto mide la RUTA: el
interruptor de la empresa, el tope de gasto, la config que no carga, y que
nada de eso termine en un 500 ni en un «cuadra».

POR QUE CADA UNA, Y NO «PORQUE HAY QUE PROBAR LA RUTA»
-------------------------------------------------------
* **El interruptor** es el consentimiento de una empresa para mandarle a un
  tercero lo que su personal escribe. Es la TERCERA perilla --las otras dos
  mandan imagenes-- y se separo por el mismo argumento del 31/10: juntarlas
  haria que encender una encienda la otra sin que nadie lo decida.
* **El tope de gasto** porque esta ruta paga, y el gate del turno no la
  cubre: si no se consultara aca, el tope del tenant no incluiria los cotejos
  y la factura se dispararia por un camino que nadie mira. Es textualmente lo
  que le paso a vision (auditoria del arquitecto, 31/10/2026).
* **Nunca 500** porque un 500 obliga al CRM a decidir que hacer con una
  excepcion, y ahi es donde se cuela un fail-open. Contestando siempre 200
  con `no_se_sabe`, el CRM no tiene nada que decidir.
* **Y que el log no lleve los textos**, porque los dos lados son de personas:
  uno lo escribio un analista y el otro un tecnico.

Se corre sola:  py -3.13 tests/test_endpoint_cotejo.py
================================================================================
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FALLAS: list[str] = []


def afirmar(condicion, mensaje: str) -> None:
    if condicion:
        print(f"  [ok] {mensaje}")
    else:
        print(f"  [FALLA] {mensaje}")
        FALLAS.append(mensaje)


os.environ.setdefault("DEEPSEEK_API_KEY", "x")

from nucleo.canales import api as API  # noqa: E402
from nucleo.canales import cotejo as C  # noqa: E402


class _Llm:
    modelo_por_defecto = "deepseek/deepseek-chat"


class _Config:
    """Lo minimo que la ruta mira."""
    def __init__(self, cotejo_on=True):
        self.cotejo_reporte_campo = cotejo_on
        self.llm = _Llm()


#: El `cotejar` de verdad, guardado ANTES de que ninguna prueba lo sustituya.
#: Sin esto, `cotejar_real=True` no restauraba nada: dejaba puesto el doble
#: de la llamada anterior, y la prueba medía el doble en vez de la ruta.
COTEJAR_REAL = C.cotejar

SE_PIDIO = ("El cliente pide el cambio de router wifi, no por una falla: "
            "el equipo esta en linea y con senal buena.")
QUE_HIZO = "Potencia al llegar: -50.0 dBm. Que encontro: fibra partida."


def _pedir(cliente, cuerpo=None, tenant="rapilink"):
    url = "/interno/cotejo/reporte-contra-ticket"
    if tenant is not None:
        url += f"?tenant={tenant}"
    return cliente.post(url, json=cuerpo if cuerpo is not None
                        else {"se_pidio": SE_PIDIO, "que_hizo": QUE_HIZO})


def _monta(*, config=None, revienta_config=False, frenar=False,
           veredicto=C.NO_CUADRA, tokens=400, cotejar_real=False):
    """Sustituye lo que la ruta consulta. Devuelve lo que se registro."""
    anotado = []
    registrado = []

    API._config_de = (lambda t: (_ for _ in ()).throw(RuntimeError("base caida"))
                      ) if revienta_config else (lambda t: config or _Config())
    API.consumo.estado_del_gasto = lambda c, t: {
        "accion": "frenar" if frenar else "seguir"}
    API.consumo.partir_referencia = lambda m: ("deepseek", "deepseek-chat")
    API.consumo.costo_de = lambda c, m, e, s: (0.0001, True)
    API.eventos_consumo.anotar_evento = (
        lambda *a, **kw: anotado.append((a, kw)))
    #  `cotejar_real` deja pasar el modulo de verdad. Hace falta para medir
    #  el caso del cuerpo vacio: con el doble puesto --que siempre devuelve
    #  el mismo veredicto-- la prueba mediria el doble, no la ruta. Es seguro
    #  porque sin uno de los dos textos el modulo no llama al proveedor.
    if cotejar_real:
        C.cotejar = COTEJAR_REAL
    else:
        C.cotejar = lambda a, b, m: C.Resultado(
            veredicto=veredicto, motivo="el ticket dice en linea y el reporte "
                                        "una fibra partida",
            tokens=tokens, segundos=1.2)

    original = API.registrar

    def espia(*a, **kw):
        registrado.append((a, kw))
        return original(*a, **kw)

    API.registrar = espia
    return anotado, registrado


print(__doc__)
API.app.config["TESTING"] = True
cli = API.app.test_client()

# ---------------------------------------------------------------------------
#  1) EL CAMINO BUENO
# ---------------------------------------------------------------------------
print("\n1) con todo en orden, el veredicto viaja")

anotado, registrado = _monta()
r = _pedir(cli)
d = r.get_json()
afirmar(r.status_code == 200, f"200 (dio {r.status_code})")
afirmar(d["veredicto"] == C.NO_CUADRA,
        f"el veredicto llega sin cambiarse (dio {d['veredicto']})")
afirmar("fibra partida" in d["motivo"], "y el motivo tambien")
afirmar(len(anotado) == 1,
        f"se anoto UN evento de consumo (dio {len(anotado)})")
afirmar(anotado[0][1]["metadatos"]["origen"] == "cotejo_reporte_campo",
        "con su origen, para poder separarlo en /consumo de las fotos")

# ---------------------------------------------------------------------------
#  2) NINGUN CAMINO MALO DEVUELVE «SI», Y NINGUNO DEVUELVE 500
# ---------------------------------------------------------------------------
print("\n2) todos los caminos malos dan «no se sabe», con 200")

class _ConfigVieja:
    """Una config que NO tiene el campo. Pasa de verdad: una empresa cuya
    fila en `tenant_config` se escribio antes de que el campo existiera, o
    una version del esquema que no lo trae."""
    llm = _Llm()


casos = [
    ("la empresa lo tiene apagado", dict(config=_Config(cotejo_on=False))),
    #  EL DEFAULT DEL `getattr`, QUE NINGUNA OTRA PRUEBA EJERCE. Se agrego el
    #  12/11/2026 despues de romper el codigo a proposito: cambiar ese
    #  `False` por `True` --o sea, que el interruptor falle ABIERTO cuando el
    #  campo no existe-- dejaba este archivo entero EN VERDE, porque todas
    #  las configs de prueba tenian el atributo. Una guarda que no ejerce el
    #  default no protege el default.
    ("la config no trae el campo todavia", dict(config=_ConfigVieja())),
    ("la config no carga", dict(revienta_config=True)),
    ("la empresa alcanzo su tope de gasto", dict(frenar=True)),
]
for como, kw in casos:
    anotado, _ = _monta(**kw)
    r = _pedir(cli)
    d = r.get_json()
    afirmar(r.status_code == 200 and d["veredicto"] == C.NO_SE_SABE,
            f"{como}: 200 y 'no_se_sabe' (dio {r.status_code}, "
            f"'{d.get('veredicto')}')")
    afirmar(d.get("motivo"), f"{como}: y dice por que, no un motivo vacio")
    afirmar(not anotado,
            f"{como}: NO se anota consumo, porque no se le pago a nadie")

#  Y EL CASO QUE DE VERDAD IMPORTA: ninguno de esos caminos puede, por un
#  descuido futuro, devolver 'si'. Si alguien cambia `sin_juicio`, esto cae.
for como, kw in casos:
    _monta(veredicto=C.CUADRA, **kw)
    afirmar(_pedir(cli).get_json()["veredicto"] != C.CUADRA,
            f"{como}: NO contesta 'si' ni aunque el modelo diria que si")

# ---------------------------------------------------------------------------
#  3) LA PETICION MAL ARMADA SI ES UN 400 -- Y SOLO ESA
# ---------------------------------------------------------------------------
print("\n3) se distingue «no se pudo juzgar» de «la peticion estaba mal»")

_monta(cotejar_real=True)
r = _pedir(cli, tenant=None)
afirmar(r.status_code == 400,
        f"sin tenant es 400: eso es un error de quien llama (dio {r.status_code})")

r = _pedir(cli, cuerpo={})
d = r.get_json()
afirmar(r.status_code == 200 and d["veredicto"] == C.NO_SE_SABE,
        "un cuerpo sin los textos NO es 400: es un cotejo que no se puede "
        "hacer, y el modulo ya sabe contestarlo sin pagar")

# ---------------------------------------------------------------------------
#  4) LOS DOS TEXTOS NO VAN AL LOG
# ---------------------------------------------------------------------------
print("\n4) del contenido no va nada al registro")

_, registrado = _monta()
_pedir(cli)
todo = json.dumps(registrado, default=str, ensure_ascii=False)
afirmar("fibra partida" not in todo,
        "el motivo que el modelo escribio NO se registra")
afirmar("router wifi" not in todo,
        "lo que se pidio tampoco")
afirmar("cotejo" in todo and "veredicto" in todo,
        "pero si el evento, el veredicto y los conteos: sin eso no se puede "
        "contar cuantos cotejos salen ni cuanto tardan")

print()
if FALLAS:
    print(f"FALLARON {len(FALLAS)}:")
    for f in FALLAS:
        print(f"  - {f}")
    sys.exit(1)
print("[OK] La ruta del cotejo no contesta «si» por ningun camino malo, no "
      "tira 500, y no registra los textos.")
