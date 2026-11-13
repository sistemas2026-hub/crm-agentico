# -*- coding: utf-8 -*-
"""
================================================================================
 UNA ONT DIBUJADA  --  para probar vision sin la foto de nadie
================================================================================

POR QUE EXISTE
--------------
Verificar contra la API real hace falta --el contrato de un tercero es una
hipotesis hasta que se mide-- pero mandarle a OpenAI la foto de un cliente
para comprobar un esquema no. Esta imagen se dibuja aca, no sale de ninguna
camara y no hay nadie adentro: ni cara, ni direccion, ni documento, ni
serial de un equipo que exista.

Es una ONT estilizada con lo que el catalogo necesita distinguir: la luz LOS
en rojo, la de encendido en verde, un par de puertos y una etiqueta con texto
inventado. Alcanza para responder la unica pregunta que esta prueba hace --
"la API acepta lo que le mandamos y devuelve lo que declaramos?"-- sin
responder ninguna sobre un cliente real.

LO QUE NO PRUEBA
----------------
Que vision funcione con fotos de verdad. Un dibujo limpio es mas facil que
una foto con reflejos, movido y mala luz. Eso se mide con una foto real de
equipo, y es una tarea aparte.
"""

from __future__ import annotations

import io

#: Tamano de la imagen. Chica a proposito: lo que se mide es el contrato de
#: la API, y una imagen grande solo gasta tokens.
ANCHO, ALTO = 900, 600


def construir() -> bytes:
    """La ONT dibujada, como JPEG. Levanta si no hay Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (ANCHO, ALTO), (232, 232, 230))
    d = ImageDraw.Draw(img)

    def fuente(px):
        for nombre in ("arial.ttf", "cour.ttf"):
            try:
                return ImageFont.truetype(nombre, px)
            except Exception:
                continue
        return ImageFont.load_default()

    #  La carcasa.
    d.rounded_rectangle([90, 120, 810, 470], radius=26, fill=(250, 250, 248),
                        outline=(176, 176, 172), width=3)

    #  Los indicadores, con su nombre al lado: es como se ven en un equipo
    #  de verdad, y es lo que permite que el modelo sepa cual es cual.
    luces = [
        ("POWER", (40, 200, 60)),      # verde fija
        ("PON",   (40, 200, 60)),      # verde fija
        ("LOS",   (225, 30, 30)),      # ROJA  <- lo que importa
        ("LAN",   (40, 200, 60)),
        ("WIFI",  (70, 70, 70)),       # apagada
    ]
    x = 150
    for nombre, color in luces:
        d.ellipse([x, 185, x + 34, 219], fill=color,
                  outline=(120, 120, 120), width=2)
        d.text((x - 6, 232), nombre, font=fuente(21), fill=(40, 40, 40))
        x += 128

    #  Puertos ethernet.
    for i in range(2):
        px = 160 + i * 120
        d.rectangle([px, 330, px + 86, 400], fill=(60, 60, 62),
                    outline=(30, 30, 30), width=3)
        d.rectangle([px + 30, 318, px + 56, 332], fill=(60, 60, 62))
        d.text((px + 16, 410), f"LAN{i + 1}", font=fuente(19),
               fill=(60, 60, 60))

    #  Un conector de fibra, verde, como el de una ONT.
    d.rectangle([470, 340, 560, 388], fill=(30, 150, 60),
                outline=(20, 100, 40), width=3)
    d.text((468, 398), "PON", font=fuente(19), fill=(60, 60, 60))

    #  Etiqueta. El texto es INVENTADO y no corresponde a ningun equipo ni a
    #  ningun cliente: es ahi justamente donde no se pone nada real.
    d.rectangle([600, 320, 790, 430], fill=(252, 252, 250),
                outline=(150, 150, 146), width=2)
    d.text((614, 334), "MODELO XR-100", font=fuente(18), fill=(20, 20, 20))
    d.text((614, 362), "S/N 0000-TEST", font=fuente(18), fill=(20, 20, 20))
    d.text((614, 390), "NO ES UN EQUIPO", font=fuente(15), fill=(120, 20, 20))

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


if __name__ == "__main__":
    import sys
    datos = construir()
    destino = sys.argv[1] if len(sys.argv) > 1 else "ont_sintetica.jpg"
    with open(destino, "wb") as f:
        f.write(datos)
    print(f"{destino}  {len(datos) // 1024} KB  {ANCHO}x{ALTO}")
