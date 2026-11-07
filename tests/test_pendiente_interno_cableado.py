# -*- coding: utf-8 -*-
"""
================================================================================
 «QUEDA EN ESPERA» ESTA CONECTADO AL RESPONDER  --  leido del codigo
================================================================================

    py -3.13 tests/test_pendiente_interno_cableado.py

La transicion se prueba contra Postgres en test_relevo_pendiente_interno_base;
esto afirma el salto que aquella no ve: que POST /conversaciones/<id>/mensajes
la LLAME con la marca que manda la pantalla, que no lo haga al devolver a la
IA, y que su fallo no tumbe la respuesta ya guardada. Corre sin base.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
fuente = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
inicio = fuente.index('@app.post("/conversaciones/<id_conversacion>/mensajes")')
handler = fuente[inicio:fuente.index("\n@app.", inicio + 10)]

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


i = handler.find("transiciones.marcar_pendiente_interno(")
comprobar(i > 0, "el endpoint de respuesta llama a marcar_pendiente_interno")
bloque = handler[max(0, i - 300): i + 400]
comprobar('nota=cuerpo.get("pendiente_interno")' in bloque,
          "con la marca que manda la pantalla, sin reinterpretarla")
comprobar("if not devolver:" in bloque, "y no al devolver a la IA")
comprobar("except Exception" in bloque and "registrar(" in bloque,
          "un fallo queda en el log y no tumba la respuesta ya guardada")
comprobar(handler.find("agregar_mensaje_humano(") < i,
          "se llama DESPUES de guardar el mensaje")

if fallos:
    print(f"\n  {len(fallos)} FALLA(S)")
    sys.exit(1)
print("\n  Todo en orden.")
