"""El expediente en PDF: la plantilla, las tres fotos y la firma en un archivo.

Este PDF NO es un adjunto mas -- es EL entregable. Es lo que Operaciones abre
para ir a instalar, y lo unico que reemplaza al correo que mandaba el
formulario del sitio web. Si sale mal, la solicitud queda igual (ver
'fallo_integracion' en el modelo), pero alguien tiene que rehacerlo a mano.

PROVISIONAL (27/08/2026): esta plantilla se armo a partir de los campos del
formulario que ya existia, no del PDF real que produce hoy -- todavia no lo
tengo a la vista. Cuando aparezca hay que comparar y ajustar: lo que importa
es que quien recibe el archivo encuentre las cosas donde ya esta acostumbrado
a buscarlas, no que sea bonito.

Las imagenes se incrustan como data: URI en vez de escribirlas al disco. Es a
proposito: las fotos sueltas no se guardan en ningun lado (cedula, recibo y
foto del solicitante son lo mas sensible que pasa por el sistema), viven solo
dentro de este archivo.
"""

from __future__ import annotations

import base64
from io import BytesIO

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

ROTULOS_IMAGEN = {
    "foto_cedula": "Documento de identidad",
    "foto_recibo": "Recibo de agua o luz",
    "foto_solicitante": "Foto del solicitante",
}


def _data_uri(contenido: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(contenido).decode("ascii")


def _mime_de(contenido: bytes) -> str:
    """El tipo real segun los primeros bytes, no segun como se llame el archivo.

    Un celular manda PNG, JPEG o HEIC segun el modelo y como saco la foto, y
    el nombre del archivo miente seguido. Si el data: URI declara un tipo que
    no es, la imagen no se dibuja y el expediente sale con un hueco donde iba
    la cedula.
    """
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if contenido[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if contenido[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if contenido[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc"):
        # WeasyPrint no dibuja HEIC. Se declara igual para no romper el
        # render entero: el hueco de una imagen se ve, y es mejor que un PDF
        # que no se genera.
        return "image/heic"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def armar_expediente(solicitud, imagenes: dict, firma: bytes) -> ContentFile:
    """El PDF completo, listo para guardar en el FileField."""
    from invoices.pdf import check_weasyprint

    check_weasyprint()
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    contexto = {
        "s": solicitud,
        "generado_en": timezone.localtime(),
        "imagenes": [
            {"rotulo": ROTULOS_IMAGEN[n], "src": _data_uri(b, _mime_de(b))}
            for n, b in imagenes.items() if b
        ],
        "firma": _data_uri(firma, _mime_de(firma)) if firma else "",
        "mapa": (
            f"https://www.google.com/maps?q={solicitud.gps_lat},{solicitud.gps_lng}"
            if solicitud.tiene_gps else ""
        ),
    }
    html = render_to_string("solicitudes/expediente.html", contexto)

    salida = BytesIO()
    HTML(string=html).write_pdf(salida, font_config=FontConfiguration())
    return ContentFile(salida.getvalue())
