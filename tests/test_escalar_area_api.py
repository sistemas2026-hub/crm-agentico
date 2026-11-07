# -*- coding: utf-8 -*-
"""
================================================================================
 ESCALAR A UN AREA (T22): EL ENDPOINT
================================================================================

    py -3.13 tests/test_escalar_area_api.py

Corre sin base: se sustituyen la config, la transicion y la nota interna, y se
pide POST /conversaciones/<id>/escalar-area con el cliente de Flask. La
transicion misma se prueba contra Postgres en
tests/test_relevo_pendiente_interno_base.py.

Lo que se protege: que un area que no es de la empresa, o sin motivo o sin
nota, no llegue a la transicion; que "la tiene otra persona" sea 409 y diga
que eso es Reasignar; y que la nota quede en el hilo UNA vez -- un reintento
no la repite.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.relevo.transiciones import Resultado                    # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


CFG = SimpleNamespace(areas=[SimpleNamespace(nombre="soporte_tecnico", etiqueta="Soporte Técnico")])
AUTOR = {"autor": "Ana", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}
llamadas: list = []
notas: list = []
respuesta = {"r": Resultado(True, True, 5, "ev-1", datos={"area": "soporte_tecnico"})}


def escalar(*a, **k):
    llamadas.append(k)
    return respuesta["r"]


reales = (api._config_de, api.transiciones.escalar_a_area, api.persistencia.agregar_nota_interna,
          api._TOKEN_SERVICIO)
api._config_de = lambda t: CFG
api.transiciones.escalar_a_area = escalar
api.persistencia.agregar_nota_interna = lambda *a, **k: notas.append(a) or "nota-1"
api._TOKEN_SERVICIO = None


def pedir(**cuerpo):
    with api.app.test_client() as c:
        r = c.post("/conversaciones/c1/escalar-area",
                   json={"tenant": "t", **AUTOR, **cuerpo})
        return r.status_code, r.get_json() or {}


try:
    print()
    print("=" * 78)
    print("  ESCALAR A UN AREA (T22): EL ENDPOINT")
    print("=" * 78)
    BUENO = {"area": "soporte_tecnico", "motivo": "no levanta", "nota": "reinicie"}

    codigo, cuerpo = pedir(**{**BUENO, "area": "inventada"})
    comprobar(codigo == 400 and cuerpo.get("codigo") == "area_invalida" and not llamadas,
              f"un area que no es de la empresa: 400 y no llega a la transicion ({codigo})")
    codigo, cuerpo = pedir(**{**BUENO, "nota": "  "})
    comprobar(codigo == 400 and cuerpo.get("codigo") == "faltan_datos" and not llamadas,
              f"sin nota: 400 ({codigo})")
    codigo, cuerpo = pedir(**{**BUENO, "motivo": ""})
    comprobar(codigo == 400 and not llamadas, f"sin motivo: 400 ({codigo})")

    codigo, cuerpo = pedir(**BUENO)
    comprobar(codigo == 200 and cuerpo.get("area_etiqueta") == "Soporte Técnico",
              f"bien: 200 con la etiqueta del area ({codigo}, {cuerpo})")
    comprobar(llamadas and set(llamadas[-1]["areas_validas"]) == {"soporte_tecnico"},
              "la transicion recibe las areas de la EMPRESA, no las del navegador")
    comprobar(len(notas) == 1 and "Soporte Técnico" in notas[0][2] and "reinicie" in notas[0][2],
              f"la nota queda en el hilo, con el area y lo validado ({notas})")

    respuesta["r"] = Resultado(False, True, 5, "ev-1", "reintento")
    codigo, _ = pedir(**BUENO)
    comprobar(codigo == 200 and len(notas) == 1, "un reintento: 200 y la nota NO se repite")

    respuesta["r"] = Resultado(False, True, 5, None, "no_es_suya", datos={"asignada_a_nombre": "Luis"})
    codigo, cuerpo = pedir(**BUENO)
    comprobar(codigo == 409 and cuerpo.get("codigo") == "no_es_suya" and "Reasignar" in cuerpo.get("error", "")
              and cuerpo.get("asignada_a") == "Luis",
              f"de otra persona: 409, dice que eso es Reasignar y quien la tiene ({codigo})")

    respuesta["r"] = Resultado(False, True, 5, None, "control_ia")
    codigo, _ = pedir(**BUENO)
    comprobar(codigo == 409, f"con la IA atendiendo: 409 ({codigo})")
finally:
    (api._config_de, api.transiciones.escalar_a_area, api.persistencia.agregar_nota_interna,
     api._TOKEN_SERVICIO) = reales

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
