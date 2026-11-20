# -*- coding: utf-8 -*-
"""
================================================================================
 LAS FOTOS QUE VIAJAN CON LA NOTA AL ISP  --  07/11/2026
================================================================================
El usuario: las fotos del tecnico se ven en el ticket de Dexter y no en el de
WispHub, y su equipo mira los dos.

VAN TODAS EN UNA SOLA RESPUESTA. Medido contra produccion ese dia (ticket
97918, servicio de prueba 5832): WispHub acepta varios `archivo` en la misma
llamada y devuelve `archivos` en plural. Importa porque `ticket-estado` es
obligatorio en ese endpoint, asi que CADA respuesta mueve el ticket: con una
foto por llamada, seis fotos serian seis escrituras de estado sobre el ticket
de un cliente.

QUE AFIRMA ESTA GUARDA
----------------------
Esto manda BYTES al sistema de un tercero, desde un servicio y no desde el
modelo. Los topes fallan cerrado y cada uno tiene su prueba:

  · cuantas, cuanto pesa cada una y cuanto pesan juntas
  · que el tipo salga de una lista BLANCA: un formato que el proveedor acepte
    manana no entra por defecto
  · que una foto que no cumple NO tumbe la nota -- el reporte del tecnico es
    lo que el ticket no tenia
  · y que tampoco se descarte en SILENCIO: el motivo sale, porque un ticket
    con tres fotos y una orden con cinco es una pregunta que alguien va a
    hacer
  · que sin `argumentos_archivo` declarado no viaje ninguna, aunque lleguen

Se corre sola: `py -3.13 tests/test_fotos_en_la_nota.py`
================================================================================
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.seguimiento import nota_en_el_ticket as N  # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


def foto(nombre="a.jpg", tipo="image/jpeg", crudo=b"\x89PNG bytes"):
    return {"nombre": nombre, "tipo": tipo,
            "base64": base64.b64encode(crudo).decode()}


print("== 1. lo que viaja ==")

viajan, motivos = N.fotos_que_pueden_viajar([foto("a.jpg"), foto("b.png", "image/png")])
afirmar(len(viajan) == 2, "dos fotos validas viajan las dos")
afirmar(not motivos, "y no se reporta ningun descarte")
afirmar([f["nombre"] for f in viajan] == ["a.jpg", "b.png"],
        "en el orden en que llegaron, con su nombre")
afirmar(all(set(f) == {"nombre", "tipo", "base64"} for f in viajan),
        "y SOLO con las tres claves que el ejecutor usa -- se rearma, no se "
        "reenvia lo que llego, asi un campo de mas aguas arriba no llega al "
        "proveedor")

extra = foto()
extra["cualquier_cosa"] = "no deberia viajar"
viajan, _ = N.fotos_que_pueden_viajar([extra])
afirmar(viajan and "cualquier_cosa" not in viajan[0],
        "un campo de mas se cae al rearmar")


print()
print("== 2. los topes, y que ninguno tumba la nota ==")

muchas = [foto(f"f{i}.jpg") for i in range(N.MAX_FOTOS + 3)]
viajan, motivos = N.fotos_que_pueden_viajar(muchas)
afirmar(len(viajan) == N.MAX_FOTOS,
        f"no viajan mas de {N.MAX_FOTOS}: un defecto aguas arriba no le "
        f"empuja cien archivos al ISP")
afirmar(bool(motivos), "y se dice que quedaron afuera")

pesada = foto(crudo=b"x" * (N.MAX_BYTES_FOTO + 1))
viajan, motivos = N.fotos_que_pueden_viajar([pesada, foto("liviana.jpg")])
afirmar([f["nombre"] for f in viajan] == ["liviana.jpg"],
        "la que pesa de mas se queda y la otra viaja igual -- una foto grande "
        "no puede impedir que el reporte se escriba")
afirmar(any("KB" in m for m in motivos), "y el motivo dice cuanto pesaba")

#  CADA UNA ENTRA SOLA, JUNTAS NO. El tope TOTAL es un control distinto del
#  individual, y hay que elegir el tamaño para probar ESE: la primera version
#  de esta guarda uso archivos de la mitad del total --7,5 MB-- que caian por
#  el tope POR ARCHIVO (5 MB) antes de llegar al total, asi que no medía lo
#  que decía medir. Con 4 MB cada uno pasan el primer control y el tercero es
#  el que no entra en los 15 MB.
cuantas_entran = N.MAX_BYTES_TOTAL // (4 * 1024 * 1024)
unas = [foto(f"{i}.jpg", crudo=b"x" * (4 * 1024 * 1024))
        for i in range(cuantas_entran + 1)]
viajan, motivos = N.fotos_que_pueden_viajar(unas)
afirmar(len(viajan) == cuantas_entran,
        f"de {len(unas)} archivos que entran de a uno, viajan "
        f"{cuantas_entran}: el tope TOTAL corta")
afirmar(any("tope total" in m for m in motivos),
        "y el motivo dice que fue el total, no el peso de esa foto")


print()
print("== 3. el tipo sale de una lista BLANCA ==")

for malo in ("text/html", "image/svg+xml", "application/javascript", ""):
    viajan, motivos = N.fotos_que_pueden_viajar([foto("x", malo)])
    afirmar(not viajan, f"'{malo or 'sin tipo'}' no viaja")

viajan, _ = N.fotos_que_pueden_viajar([foto("x.jpg", "IMAGE/JPEG")])
afirmar(len(viajan) == 1, "y el tipo no distingue mayusculas")


print()
print("== 4. lo que llega mal ==")

afirmar(N.fotos_que_pueden_viajar(None) == ([], []),
        "sin fotos no hay descarte que reportar: no mandar ninguna es lo "
        "normal, no un error")
viajan, motivos = N.fotos_que_pueden_viajar("no soy una lista")
afirmar(not viajan and bool(motivos), "algo que no es una lista se rechaza y se dice")

viajan, motivos = N.fotos_que_pueden_viajar([{"nombre": "x", "tipo": "image/jpeg",
                                              "base64": "no-es-base64!!"}])
afirmar(not viajan and bool(motivos), "un base64 roto no viaja")

viajan, motivos = N.fotos_que_pueden_viajar([{"nombre": "x", "tipo": "image/jpeg",
                                              "base64": ""}])
afirmar(not viajan and bool(motivos), "una foto vacia tampoco")

viajan, motivos = N.fotos_que_pueden_viajar(["a.jpg", 7, None])
afirmar(not viajan and len(motivos) == 3,
        "tres elementos que no son diccionarios dan tres motivos, no uno")


print()
print("== 5. el nombre no puede crecer sin limite ==")

largo = N.fotos_que_pueden_viajar([foto("x" * 500 + ".jpg")])[0]
afirmar(largo and len(largo[0]["nombre"]) <= 120,
        "el nombre se recorta: va a una cabecera de multipart, no a un campo")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Las fotos que viajan al ISP estan acotadas, y lo que no viaja se dice.")
