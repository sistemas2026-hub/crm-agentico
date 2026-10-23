# -*- coding: utf-8 -*-
"""
================================================================================
 P0 CON UNA FOTO DE VERDAD  --  que sobrevive a comprimir_imagen()
================================================================================

    py -3.13 tests/p0_foto_real.py <ruta de la foto> [carpeta de salida]

POR QUE NO ALCANZABA LA MEDICION SINTETICA
-------------------------------------------
El P0 del 02/10/2026 se hizo con rasgos DIBUJADOS: circulos de color plano y
texto nitido sobre fondo liso. Midio lo que podia medir --que el escalado y
el JPEG 80 no corren el color de un LED, ni siquiera a 4.8 px-- y eso sigue
valiendo. Pero un dibujo no tiene nada de lo que de verdad complica una foto
de soporte: reflejo en el plastico, el LED quemado por sobreexposicion, el
movido, la luz de tungsteno que tine todo de naranja, el fondo cargado.

Un LED rojo y uno naranja son dos valores distintos del catalogo y dos
diagnosticos distintos. Si la camara de un telefono barato, con poca luz, los
acerca lo suficiente como para que la compresion los junte, el catalogo se
apoya en algo que no se sostiene -- y eso solo lo dice una foto real.

QUE HACE
--------
No inventa un veredicto automatico. Pasa la foto por la MISMA compresion de
produccion, guarda las dos versiones y recorta las zonas en las que hay algo
que mirar, ampliadas, para poder compararlas de verdad. El veredicto lo pone
quien mira -- que es justo lo que una heuristica no puede hacer.

Lo numerico que si se puede medir sin saber que hay en la foto va igual:
tamano, factor de escala y NITIDEZ por zona (varianza del Laplaciano), que
es lo que se desploma cuando un detalle fino se pierde.

LO QUE NO HACE
--------------
No manda la foto a ningun lado. Es medicion local de la compresion. Para
saber si el MODELO la entiende esta tests/test_vision_api_real.py, que
acepta una ruta como argumento.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales.media import comprimir_imagen, LADO_MAXIMO, CALIDAD_JPEG


def nitidez(img) -> float:
    """
    Varianza del Laplaciano: cuanto detalle fino queda.

    Es la medida clasica de enfoque. No dice si un LED se distingue --para eso
    hay que mirar-- pero se desploma cuando el detalle se perdio, y comparar
    la misma zona antes y despues SI dice cuanto se perdio.
    """
    from PIL import ImageFilter
    gris = img.convert("L")
    bordes = gris.filter(ImageFilter.FIND_EDGES)
    #  getdata() queda deprecada en Pillow 14 y get_flattened_data no existe
    #  en las anteriores: se pide la nueva y se cae a la vieja. Un aviso de
    #  deprecacion en la salida de una medicion es ruido que termina haciendo
    #  que no se lea el resto.
    leer = getattr(bordes, "get_flattened_data", None) or bordes.getdata
    px = list(leer())
    if not px:
        return 0.0
    media = sum(px) / len(px)
    return sum((p - media) ** 2 for p in px) / len(px)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("[falta] la ruta de la foto.")
        return 2

    from PIL import Image

    origen = Path(sys.argv[1])
    if not origen.exists():
        print(f"[error] no existe: {origen}")
        return 2

    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else origen.parent / "p0"
    salida.mkdir(parents=True, exist_ok=True)

    crudo = origen.read_bytes()
    antes = Image.open(origen)
    antes.load()

    comprimido, mime = comprimir_imagen(crudo, "image/jpeg")
    despues = Image.open(__import__("io").BytesIO(comprimido))
    despues.load()

    escala = despues.size[0] / antes.size[0]

    print("=" * 72)
    print(f" P0 REAL  --  {origen.name}")
    print("=" * 72)
    print(f" comprimir_imagen(): LADO_MAXIMO={LADO_MAXIMO} CALIDAD={CALIDAD_JPEG}")
    print()
    print(f"  original    {antes.size[0]}x{antes.size[1]}   "
          f"{len(crudo) // 1024} KB   {antes.mode}")
    print(f"  comprimida  {despues.size[0]}x{despues.size[1]}   "
          f"{len(comprimido) // 1024} KB   {mime}")
    print(f"  escala      {escala:.3f}"
          + (f"   (reduccion de {1 / escala:.2f}x)" if escala else ""))
    print(f"  peso        {100 - len(comprimido) * 100 // max(1, len(crudo))}% menos")

    #  La MISMA zona en las dos, al mismo tamano, para que la comparacion sea
    #  honesta: comparar una grande contra una chica siempre favorece a la
    #  grande por el solo hecho de ser grande.
    comparable = antes.resize(despues.size, Image.LANCZOS)

    print()
    print("  NITIDEZ POR ZONA (varianza del Laplaciano; mas alto = mas detalle)")
    print(f"  {'zona':<16} {'original':>12} {'comprimida':>12} {'queda':>8}")

    zonas = {
        "arriba izq": (0.00, 0.00, 0.50, 0.50),
        "arriba der": (0.50, 0.00, 1.00, 0.50),
        "abajo izq": (0.00, 0.50, 0.50, 1.00),
        "abajo der": (0.50, 0.50, 1.00, 1.00),
        "centro": (0.25, 0.25, 0.75, 0.75),
        "imagen entera": (0.00, 0.00, 1.00, 1.00),
    }
    an, al = despues.size
    for nombre, (x0, y0, x1, y1) in zonas.items():
        caja = (int(x0 * an), int(y0 * al), int(x1 * an), int(y1 * al))
        a = nitidez(comparable.crop(caja))
        d = nitidez(despues.crop(caja))
        pct = (d / a * 100) if a else 0
        print(f"  {nombre:<16} {a:>12.1f} {d:>12.1f} {pct:>7.0f}%")

    #  Los recortes, x3, para mirar de cerca. Es lo que de verdad contesta
    #  "se distingue el color del LED": el ojo, no un numero.
    print()
    print("  RECORTES AMPLIADOS (x3) para comparar a ojo:")
    for nombre, (x0, y0, x1, y1) in zonas.items():
        if nombre == "imagen entera":
            continue
        caja = (int(x0 * an), int(y0 * al), int(x1 * an), int(y1 * al))
        clave = nombre.replace(" ", "_")
        for etiqueta, img in (("original", comparable), ("comprimida", despues)):
            recorte = img.crop(caja)
            recorte = recorte.resize(
                (recorte.size[0] * 3, recorte.size[1] * 3), Image.LANCZOS)
            destino = salida / f"{clave}__{etiqueta}.png"
            recorte.save(destino)
    (salida / "comprimida_completa.jpg").write_bytes(comprimido)
    comparable.save(salida / "original_al_mismo_tamano.png")
    print(f"    {salida}")

    print()
    print("  LO QUE HAY QUE MIRAR EN ESOS RECORTES:")
    print("    1. cada LED conserva SU color (rojo != naranja es el diagnostico)")
    print("    2. se distingue encendido de apagado")
    print("    3. los conectores conservan forma (fibra verde vs ethernet)")
    print("    4. los puertos se cuentan")
    print("    5. la etiqueta -- y si se lee, NO habilita usarla como identidad")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
