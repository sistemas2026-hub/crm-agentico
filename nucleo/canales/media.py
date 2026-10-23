# -*- coding: utf-8 -*-
"""
================================================================================
 MULTIMEDIA  -  achicar antes de guardar
================================================================================

Por que existe
--------------
Un telefono moderno manda fotos de 3 a 8 MB. Lo que hace falta para atender el
caso es ver que la luz del router esta en rojo, y para eso sobra una decima
parte. Guardar el original multiplica por diez el tamano de la base y no agrega
un solo dato util.

No sabe de WhatsApp ni de ningun canal: recibe bytes y devuelve bytes. El canal
lo llama despues de descargar (nucleo/canales/whatsapp.py) y antes de escribir
(nucleo/persistencia/db.py).

DEGRADA, NO FALLA
-----------------
Si Pillow no esta instalado, si el formato es raro o si la imagen viene rota,
se devuelve el original sin tocar. Perder la foto porque no se pudo comprimir
seria cambiar un problema de espacio por uno de informacion.
================================================================================
"""

from __future__ import annotations

import io

# Lado mayor al que se reduce una foto. 1600 px sigue permitiendo leer una
# etiqueta de router o el numero de serie de una ONT ampliando; mas que eso es
# resolucion que nadie mira en la pantalla de un CRM.
LADO_MAXIMO = 1600
CALIDAD_JPEG = 80


def comprimir_imagen(contenido: bytes, mime: str = "") -> tuple[bytes, str]:
    """
    (bytes, mime) listos para guardar.

    Devuelve el original si no hay nada que ganar -- comprimir una imagen que
    ya es chica la deja igual o mas pesada, y encima le agrega una recodificacion
    que solo pierde calidad.
    """
    try:
        from PIL import Image
    except ImportError:
        # Sin Pillow se guarda tal cual: pesa mas, pero la foto llega.
        return contenido, mime

    try:
        img = Image.open(io.BytesIO(contenido))
        img.load()
    except Exception:
        return contenido, mime

    try:
        # Un PNG con transparencia o un modo raro no se puede guardar como
        # JPEG. Se aplana contra blanco, que es como se va a ver en la interfaz.
        if img.mode in ("RGBA", "LA", "P"):
            fondo = Image.new("RGB", img.size, (255, 255, 255))
            img = img.convert("RGBA")
            fondo.paste(img, mask=img.split()[-1])
            img = fondo
        elif img.mode != "RGB":
            img = img.convert("RGB")

        if max(img.size) > LADO_MAXIMO:
            img.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)

        buffer = io.BytesIO()
        # optimize + progressive: dos pasadas mas al guardar, ~10% menos peso y
        # la foto se ve entera antes al cargarla en la bandeja.
        img.save(buffer, format="JPEG", quality=CALIDAD_JPEG,
                 optimize=True, progressive=True)
        comprimido = buffer.getvalue()
    except Exception:
        return contenido, mime

    if len(comprimido) >= len(contenido):
        return contenido, mime
    return comprimido, "image/jpeg"


def preparar(contenido: bytes, tipo: str, mime: str = "") -> tuple[bytes, str]:
    """
    Aplica lo que corresponda segun el tipo.

    El audio NO se recomprime: recodificar audio comprimido pierde calidad
    justo en lo que importa (entender que dijo alguien en la calle, con viento)
    y ahorra poco, porque WhatsApp ya lo manda en opus. Se guarda tal cual.
    """
    if tipo == "image":
        return comprimir_imagen(contenido, mime)
    return contenido, mime
