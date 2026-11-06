# -*- coding: utf-8 -*-
"""
================================================================================
 LA CALIDAD CON QUE SE MIRA UNA FOTO  --  06/11/2026
================================================================================
`media.comprimir_imagen` acepta desde hoy `lado` y `calidad`, para poder medir
si la compresion es la que deja ciego al analisis de evidencias: el usuario
reporto fotos marcadas "no es lo que se pidio" que SI mostraban lo pedido, y
la foto que el modelo mira pasa por DOS recompresiones encadenadas.

QUE AFIRMA ESTA GUARDA, Y POR QUE ESO
--------------------------------------
Lo peligroso de agregar una palanca no es la palanca: es que alguien mueva el
DEFAULT sin darse cuenta. Por esta funcion pasa TODA imagen del sistema, no
solo las evidencias de campo -- tambien las fotos que manda un cliente por
WhatsApp. Subir la calidad por defecto multiplicaria el gasto de tokens de
cada foto del dia sin que nadie lo haya pedido.

Asi que lo central aca no es que los parametros funcionen --eso es una linea--
sino que **sin pasarlos, nada cambie**.

Y la otra mitad, la que de verdad importa para lo que se vino a medir: que el
EXIF se siga yendo en las DOS calidades. Esa recompresion existe para sacar el
GPS de la vivienda del cliente antes de mandar la foto a un tercero; una
variante que conserve la calidad y pierda esa garantia seria peor que el
problema que resuelve.
================================================================================
"""
from __future__ import annotations

import io as _io
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import media                                  # noqa: E402

_fallos: list[str] = []


def afirmar(ok: bool, que: str, dato: str = "") -> None:
    print(("  OK    " if ok else "  FALLA ") + que + (f"  [{dato}]" if dato and not ok else ""))
    if not ok:
        _fallos.append(que)


def _foto(ancho=2400, alto=1800, exif=True) -> bytes:
    """Una foto con ruido fino: lo primero que se come la compresion."""
    from PIL import Image

    random.seed(11)
    img = Image.new("RGB", (ancho, alto))
    img.putdata([(random.randint(0, 255),) * 3 for _ in range(ancho * alto)])
    b = _io.BytesIO()
    if exif:
        #  Un EXIF con coordenadas, que es justo lo que no puede sobrevivir.
        #  Tags simples: lo que se mide es que el bloque EXIF entero NO
        #  sobreviva. El GPS vive en ese mismo bloque, asi que si no queda
        #  nada, no queda el GPS tampoco -- y armar un GPSInfo valido a mano
        #  solo agregaria una forma de que la prueba falle por si misma.
        ex = Image.Exif()
        ex[271] = "Marca"              # Make
        ex[272] = "Modelo"             # Model
        ex[306] = "2026:11:06 21:53:00"  # DateTime
        img.save(b, format="JPEG", quality=95, exif=ex)
    else:
        img.save(b, format="JPEG", quality=95)
    return b.getvalue()


def _medidas(datos: bytes) -> tuple[int, int]:
    from PIL import Image

    return Image.open(_io.BytesIO(datos)).size


print("\n-- A: sin pasar nada, NADA cambia --")
print("-" * 46)
#  Los numeros se leen del modulo, no se repiten aca: una guarda que copia la
#  constante pasa igual el dia que alguien cambie la constante.
afirmar(media.LADO_MAXIMO == 1600, "A1. el lado por defecto sigue siendo 1600",
        str(media.LADO_MAXIMO))
afirmar(media.CALIDAD_JPEG == 80, "A2. la calidad por defecto sigue siendo 80",
        str(media.CALIDAD_JPEG))

cruda = _foto()
por_defecto, _ = media.preparar(cruda, "image", "image/jpeg")
ancho, alto = _medidas(por_defecto)
afirmar(max(ancho, alto) == media.LADO_MAXIMO,
        "A3. sin parametros reduce al lado de siempre", f"{ancho}x{alto}")

#  La misma llamada pidiendo explicitamente los valores de hoy tiene que dar
#  EXACTAMENTE lo mismo. Si difiere, el default y lo explicito se separaron.
explicito, _ = media.preparar(cruda, "image", "image/jpeg",
                              lado=media.LADO_MAXIMO, calidad=media.CALIDAD_JPEG)
afirmar(explicito == por_defecto,
        "A4. pedir los valores de hoy da el MISMO byte que no pedir nada",
        f"{len(por_defecto)} vs {len(explicito)}")

print("\n-- B: la palanca mueve lo que tiene que mover --")
print("-" * 50)
alta, _ = media.preparar(cruda, "image", "image/jpeg", lado=2048, calidad=92)
ancho_a, alto_a = _medidas(alta)
afirmar(max(ancho_a, alto_a) == 2048, "B1. con lado=2048 la imagen es mas grande",
        f"{ancho_a}x{alto_a}")
afirmar(len(alta) > len(por_defecto),
        "B2. y pesa mas, que es el costo de verla mejor",
        f"{len(alta)} vs {len(por_defecto)}")

print("\n-- C: el EXIF se va en las DOS calidades --")
print("-" * 46)
#  ESTA ES LA MITAD QUE NO SE PUEDE PERDER. La recompresion existe para sacar
#  el GPS de la vivienda del cliente antes de mandar la foto a un tercero.
from PIL import Image                                             # noqa: E402

afirmar(bool(Image.open(_io.BytesIO(cruda)).getexif()),
        "C0. la foto cruda SI trae EXIF (si no, el resto no prueba nada)")
for etiqueta, datos in (("por defecto", por_defecto), ("alta", alta)):
    exif = Image.open(_io.BytesIO(datos)).getexif()
    afirmar(not dict(exif), f"C. {etiqueta}: el EXIF se fue", str(dict(exif))[:80])

print("\n-- D: lo que no se puede romper --")
print("-" * 36)
#  Un valor absurdo no puede agrandar la foto ni dejarla en cero.
cero, _ = media.preparar(cruda, "image", "image/jpeg", lado=0, calidad=0)
afirmar(cero == por_defecto, "D1. lado=0 y calidad=0 son 'los de siempre'")
#  Y el audio sigue sin tocarse, que es la otra rama de `preparar`.
audio = b"\x00\x01\x02ogg"
mismo, mime = media.preparar(audio, "audio", "audio/ogg", lado=2048, calidad=92)
afirmar(mismo == audio and mime == "audio/ogg",
        "D2. el audio NO se recodifica, ni pasandole calidad")

print("\n" + "=" * 72)
if _fallos:
    print(f" {len(_fallos)} FALLAS:")
    for f in _fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
