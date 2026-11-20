# -*- coding: utf-8 -*-
"""
================================================================================
 EL TELEFONO DE UN TERCERO NO SALE AL PROVEEDOR DEL MODELO  --  11/11/2026
================================================================================
    py -3.13 tests/test_contacto_sin_telefono_al_modelo.py        (sin base)

Cuando el cliente comparte una tarjeta de contacto, el canal guarda el aviso
con el numero entero (la Bandeja se lo muestra al equipo). La persona de la
tarjeta no firmo la autorizacion de tratamiento (PRD RNF-01), asi que al
proveedor del modelo le llega el nombre y los ultimos 4 digitos, nada mas.
Decision del dueño, PRD §8.20.

Se afirma sobre el EFECTO: lo que recibe el cliente del proveedor cuando se
llama a cliente.chat(), por cualquier camino -- el turno, el historial, un
resumen, la cita de una reaccion, una parte de texto en vision --. El
proveedor se dobla; no sale nada a la red.
================================================================================
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import avisos, whatsapp               # noqa: E402
from nucleo.modelo import cliente                         # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


class ProveedorDoble:
    """Guarda lo que le llegaria al proveedor."""
    def __init__(self):
        self.recibido = None

    def chat(self, modelo, mensajes, tools=None, temperatura=0.1, timeout=None,
             razonamiento=None):
        self.recibido = mensajes
        return cliente.Respuesta(contenido="ok", llamadas=[])


doble = ProveedorDoble()
cliente._cache["deepseek"] = doble


def lo_que_sale(mensajes):
    cliente.chat("deepseek:deepseek-chat", mensajes)
    return doble.recibido


# El aviso como lo arma el canal de verdad, no a mano.
aviso = whatsapp.texto_de_contactos([
    {"name": {"formatted_name": "Maria Lopez"},
     "phones": [{"phone": "+57 300 123 4567"}, {"wa_id": "573109876543"}]},
])
revisar("+57 300 123 4567" in aviso and "573109876543" in aviso,
        "el aviso que se GUARDA lleva los numeros enteros (la Bandeja los muestra)",
        aviso)

print("\nEl turno: el mensaje del cliente es el aviso")
historial = [{"role": "system", "content": "Sos el asistente."},
             {"role": "user", "content": aviso}]
original = copy.deepcopy(historial)
salio = lo_que_sale(historial)
texto = salio[-1]["content"]
revisar("300 123 4567" not in texto and "1234567" not in texto
        and "9876543" not in texto,
        "EL EFECTO: ningun numero entero llega al proveedor", texto)
revisar("Maria Lopez" in texto, "el nombre si llega", texto)
revisar("terminado en 4567" in texto and "terminado en 6543" in texto,
        "llegan los ultimos 4 digitos de cada numero", texto)
revisar(historial == original,
        "el historial del llamador queda intacto (lo que se guarda no cambia)")

print("\nEl aviso DENTRO de otro texto: historial resumido o cita de una reaccion")
cita = f"[El cliente reacciono con 👍 a: «{aviso}»]"
resumen = f"Cliente: hola\nCliente: {aviso}\nAsistente: gracias, Maria lo recibe"
salio = lo_que_sale([{"role": "user", "content": cita},
                     {"role": "assistant", "content": resumen}])
revisar(all("4567" not in m["content"].replace("terminado en 4567", "")
            for m in salio),
        "EL EFECTO: tampoco sale dentro de una cita o un resumen",
        str(salio))

print("\nVision: el contenido es una lista de partes")
salio = lo_que_sale([{"role": "user", "content": [
    {"type": "text", "text": aviso},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}])
partes = salio[0]["content"]
revisar("300 123 4567" not in partes[0]["text"]
        and partes[1]["image_url"]["url"] == "data:image/png;base64,AAAA",
        "la parte de texto se recorta y la imagen pasa igual", str(partes))

print("\nLo que NO se toca")
propio = "mi numero es 3001234567, llamenme"
salio = lo_que_sale([{"role": "user", "content": propio}])
revisar(salio[0]["content"] == propio,
        "el numero que escribe el propio cliente es SUYO y pasa entero")
nombre_con_numero = "[El cliente compartio un contacto: Local 3 — +57 300 123 4567]"
salio = lo_que_sale([{"role": "user", "content": nombre_con_numero}])
revisar("Local 3" in salio[0]["content"]
        and "300 123 4567" not in salio[0]["content"],
        "un numero corto en el nombre no se confunde con un telefono",
        salio[0]["content"])
revisar(avisos.sin_telefonos_de_terceros("") == ""
        and avisos.sin_telefonos_de_terceros(None) is None,
        "sin texto, nada que recortar")

del cliente._cache["deepseek"]

print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Todo en verde.")
