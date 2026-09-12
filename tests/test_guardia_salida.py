# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE LA GUARDIA DE SALIDA
================================================================================

Por que existe
--------------
nucleo/seguridad/salida.py es la tercera capa de RNF-02 (PRD.md): un chequeo
sobre el TEXTO que el modelo redacta, antes de que llegue al cliente. Las
otras dos capas (listas blancas de campos, confirmacion humana) protegen la
entrada de datos al modelo; esta protege la salida.

El riesgo que esta guarda evita no es hipotetico: se penso reusar
'Rol.nunca_revelar' para este chequeo, y se descarto a proposito porque
'cliente_final' tiene 'cedula' y 'direccion' en esa lista -- son nombres de
CAMPO para filtrar datos crudos de API, no frases prohibidas en lenguaje
natural. El agente dice "pasame tu cedula" en cada verificacion; buscar esa
palabra en el texto libre habria bloqueado el flujo normal. Este test deja
esa decision escrita para que nadie la reintente sin revisar por que se
descarto.

Uso
---
    py -3.13 tests/test_guardia_salida.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config              # noqa: E402
from nucleo.seguridad import salida as guardia        # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


print("un codigo interno filtrado se bloquea, tal cual o con tildes/mayusculas distintas")
texto, fuga = guardia.verificar("Error: IDENTIDAD_NO_VERIFICADA, pedile la cedula")
comprobar(fuga == "IDENTIDAD_NO_VERIFICADA", "detecta el patron exacto")
comprobar(texto == guardia.MENSAJE_FUGA, "no deja pasar el texto original (fail-closed)")

texto2, fuga2 = guardia.verificar("no se pudo, precondicion_no_cumplida para esa accion")
comprobar(fuga2 == "PRECONDICION_NO_CUMPLIDA", "detecta en minusculas, sin tildes")

print("\nuna respuesta normal, con palabras parecidas pero no el patron, pasa intacta")
normal = "Tu identidad ya quedo verificada antes en esta conversacion."
texto3, fuga3 = guardia.verificar(normal)
comprobar(fuga3 is None, "no dispara con 'identidad' + 'verificada' sueltas")
comprobar(texto3 == normal, "el texto normal no se toca")

print("\nel chequeo NO usa 'nunca_revelar' -- palabras normales de la conversacion no disparan")
# Esto es lo que se evito: 'cedula' y 'direccion' estan en nunca_revelar de
# cliente_final (ver tenants/rapilink.config.yaml) pero son parte del habla
# normal del agente. Confirmado que la guarda las ignora.
pide_cedula = "Para verificar tu identidad, pasame tu numero de cedula por favor."
texto4, fuga4 = guardia.verificar(pide_cedula)
comprobar(fuga4 is None, "pedir la cedula (palabra normal) no se bloquea")

confirma_direccion = "Tu direccion registrada es la que aparece en el contrato."
texto5, fuga5 = guardia.verificar(confirma_direccion)
comprobar(fuga5 is None, "mencionar 'direccion' (palabra normal) no se bloquea")

print("\nla configuracion real de Rapilink confirma el riesgo que se evito")
real = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
cliente_final = real.roles.get("cliente_final")
comprobar(cliente_final is not None and "cedula" in cliente_final.nunca_revelar,
         "'cedula' esta en nunca_revelar de cliente_final -- por eso no se reusa esa lista")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La guardia de salida bloquea plomeria interna sin tocar el habla normal.")
