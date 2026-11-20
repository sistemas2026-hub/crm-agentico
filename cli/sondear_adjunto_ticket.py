# -*- coding: utf-8 -*-
"""
================================================================================
 ¿CUANTOS ARCHIVOS ACEPTA UNA RESPUESTA DE TICKET?  --  07/11/2026
================================================================================
Las fotos del tecnico ya se ven en el ticket de Dexter. Faltan las de WispHub,
y antes de escribir una linea hay que medir UNA cosa que decide todo el
diseño:

    POST /api/tickets/{id}/respuesta/  acepta el campo `archivo`.
    La skill lo tiene verificado (28/08/2026) y lo describe EN SINGULAR.

Si acepta varios en la misma llamada, seis fotos son UNA respuesta. Si acepta
uno solo, seis fotos son SEIS respuestas -- y cada respuesta a ese endpoint
MUEVE EL TICKET, porque `ticket-estado` es obligatorio. Seis escrituras de
estado para adjuntar seis fotos es otro diseño, y otra conversacion con quien
opera.

No se puede deducir del spec: el propio spec de esta API ya mintio sobre su
dominio, sobre campos obligatorios y sobre formatos de fecha. Se mide.

POR QUE ESCRIBE, Y QUE ESCRIBE
-------------------------------
No hay forma de medirlo leyendo. Entonces:

  · SOLO sobre un ticket de MARIO SABANAGRANDE (servicio 5832), el unico
    cliente autorizado para pruebas que escriben en WispHub
  · lee el ticket ANTES y manda su estado y prioridad ACTUALES, para que la
    prueba no lo mueva de cola
  · simula por defecto: sin --aplicar imprime lo que mandaria y no llama
  · deja una respuesta visible, en texto, diciendo que es una prueba tecnica

    py -3.13 cli/sondear_adjunto_ticket.py --ticket 97918
    py -3.13 cli/sondear_adjunto_ticket.py --ticket 97918 --aplicar

Corre donde viva `WISPHUB_API_KEY` (el contenedor del motor), igual que
`cli/sondear_api.py`. La clave se lee del entorno; este archivo no abre
ningun `.env`.
================================================================================
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

BASE = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
CLAVE = os.environ.get("WISPHUB_API_KEY")

#:  EL UNICO CLIENTE CON EL QUE SE PRUEBA ESCRIBIENDO. Regla del usuario, y no
#:  es una formalidad: lo de al lado son tickets de gente real.
SERVICIO_DE_PRUEBA = 5832

#:  Dos PNG de 1x1, uno rojo y uno azul, distintos entre si a proposito: si la
#:  API se queda con uno solo hay que poder decir CUAL.
import base64  # noqa: E402

ROJO = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg==")
AZUL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9"
    "awAAAABJRU5ErkJggg==")

TEXTO = ("Prueba tecnica de Dexter: se esta verificando cuantos archivos "
         "acepta una respuesta. Sin efecto sobre el servicio del cliente.")


def _headers() -> dict:
    #  SIN Content-Type: requests lo pone con el boundary del multipart. Si se
    #  fija a mano, la API recibe un cuerpo que no puede partir.
    return {"Authorization": f"Api-Key {CLAVE}"}


def leer_ticket(ident: str) -> dict:
    r = requests.get(f"{BASE}/api/tickets/{ident}/", headers={
        **_headers(), "Content-Type": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ticket", required=True, help="Id del ticket en WispHub.")
    p.add_argument("--aplicar", action="store_true",
                   help="Sin esto solo simula y no escribe nada.")
    o = p.parse_args()

    if not CLAVE:
        print("Falta WISPHUB_API_KEY en el entorno de este proceso.")
        return 2

    print(f"--- leyendo el ticket {o.ticket} ---")
    ticket = leer_ticket(o.ticket)
    servicio = (ticket.get("servicio") or {})
    id_servicio = servicio.get("id_servicio") if isinstance(servicio, dict) \
        else servicio
    print(f"  cliente     : servicio {id_servicio}")
    print(f"  estado      : {ticket.get('estado')}")
    print(f"  prioridad   : {ticket.get('prioridad')}")
    print(f"  respuestas  : {len(ticket.get('respuestas') or [])}")

    #  LA PUERTA. Antes de cualquier cosa que escriba.
    if str(id_servicio) != str(SERVICIO_DE_PRUEBA):
        print(f"\nEse ticket NO es del servicio de prueba "
              f"({SERVICIO_DE_PRUEBA}). No se escribe sobre el ticket de un "
              f"cliente real.")
        return 1

    #  EL ESTADO QUE YA TIENE, no uno elegido: `ticket-estado` es obligatorio
    #  y toda respuesta mueve el ticket. Mandar el actual lo deja donde esta.
    estado = ticket.get("estado")
    prioridad = ticket.get("prioridad")
    mapa_estado = {"Nuevo": 1, "En Progreso": 2, "Resuelto": 3, "Cerrado": 4}
    mapa_prioridad = {"Baja": 1, "Normal": 2, "Alta": 3, "Muy Alta": 4}
    cod_estado = mapa_estado.get(str(estado).strip())
    cod_prioridad = mapa_prioridad.get(str(prioridad).strip())
    if cod_estado is None or cod_prioridad is None:
        print(f"\nNo se pudo traducir estado={estado!r} / "
              f"prioridad={prioridad!r} a los codigos que pide /respuesta/. "
              f"Sin eso la prueba moveria el ticket de cola.")
        return 1

    print(f"\n--- lo que se mandaria a POST /api/tickets/{o.ticket}/respuesta/ ---")
    print(f"  respuesta       : {TEXTO[:60]}...")
    print(f"  ticket-estado   : {cod_estado}   (el que ya tiene: {estado})")
    print(f"  ticket-prioridad: {cod_prioridad}   (el que ya tiene: {prioridad})")
    print("  archivo         : DOS partes con el MISMO nombre de campo "
          "(prueba-1.png, prueba-2.png)")

    if not o.aplicar:
        print("\nSIMULACRO: no se llamo a la API. Volvé a correrlo con "
              "--aplicar.")
        return 0

    #  UNA LISTA DE TUPLAS, no un dict: es la unica forma de que `requests`
    #  mande dos partes con el MISMO nombre de campo. Un dict se quedaria con
    #  la ultima, y la prueba diria "acepta una" cuando el que mando una fue
    #  el cliente.
    partes = [
        ("respuesta", (None, TEXTO)),
        ("ticket-estado", (None, str(cod_estado))),
        ("ticket-prioridad", (None, str(cod_prioridad))),
        ("archivo", ("prueba-1.png", ROJO, "image/png")),
        ("archivo", ("prueba-2.png", AZUL, "image/png")),
    ]
    antes = len(ticket.get("respuestas") or [])
    r = requests.post(f"{BASE}/api/tickets/{o.ticket}/respuesta/",
                      headers=_headers(), files=partes, timeout=60)
    print(f"\n--- respuesta de la API ---")
    print(f"  HTTP {r.status_code}")
    print(f"  cuerpo: {r.text[:600]}")

    #  Y SE VERIFICA LEYENDO, no por el eco: esta API ya devolvio 200 con un
    #  cambio que no aplico, mas de una vez (ver la skill wisphub-api).
    print(f"\n--- leyendo el ticket de nuevo ---")
    fresco = leer_ticket(o.ticket)
    respuestas = fresco.get("respuestas") or []
    print(f"  respuestas   : {antes} -> {len(respuestas)}")
    print(f"  estado       : {fresco.get('estado')}  (era {estado})")
    if respuestas:
        ultima = respuestas[-1]
        print(f"  ultima       : {str(ultima)[:400]}")
    print("\nQUE MIRAR: si la ultima respuesta trae DOS archivos, seis fotos "
          "son una respuesta. Si trae uno, son seis respuestas y seis "
          "escrituras de estado -- y eso hay que decidirlo antes de "
          "construirlo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
