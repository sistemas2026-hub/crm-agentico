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


# Los tres tramos de confianza de la ubicacion, y que hacer con cada uno. No
# son adorno: deciden si alguien sale a la calle o llama primero.
#
# El corte esta en 50 y 100 metros. Arriba de 100 el punto puede caer a
# cuadras de la casa -- pasa siempre que el formulario se abre desde una
# computadora, donde no hay GPS y la ubicacion sale de la IP (se vieron
# lecturas de 50.000 m).
PRECISION_OPTIMA_M = 50
PRECISION_MEDIA_M = 100


def _calidad_ubicacion(solicitud) -> dict:
    """Como se muestra la ubicacion y que se le dice a quien la lee."""
    if not solicitud.tiene_gps:
        return {"nivel": "baja", "rotulo": "SIN UBICACION",
                "detalle": "El solicitante no compartio su ubicacion.",
                "accion": "UBICACION NO CONFIABLE. Contactar al solicitante "
                          "antes de asignar visita."}
    try:
        metros = int(float(solicitud.gps_precision_m or 0))
    except (TypeError, ValueError):
        metros = 0
    if not metros:
        return {"nivel": "media", "rotulo": "SIN PRECISION", "metros": None,
                "detalle": "No se registro la precision de la lectura.",
                "accion": "Verificar en mapa y confirmar con el solicitante."}
    if metros <= PRECISION_OPTIMA_M:
        return {"nivel": "optima", "rotulo": "Excelente", "metros": metros,
                "accion": "Listo para validar cobertura y asignar visita."}
    if metros <= PRECISION_MEDIA_M:
        return {"nivel": "media", "rotulo": "Media", "metros": metros,
                "accion": "Verificar en mapa y confirmar con el solicitante."}
    return {"nivel": "baja", "rotulo": "Baja", "metros": metros,
            "accion": "UBICACION NO CONFIABLE. Contactar al solicitante antes "
                      "de asignar visita."}


def _logo_de(org) -> str:
    """El logo de la empresa como data: URI, o "" si no cargo ninguno.

    Sale de `Org.logo` -- el mismo campo que ya usan las facturas-- y NO de un
    archivo puesto en el repo. Es la diferencia entre que la proxima empresa
    que se conecte suba su logo desde Ajustes, y que necesite que alguien le
    toque el codigo. El expediente no puede depender de que exista: sin logo
    imprime el nombre en texto y sale igual.

    Se lee el archivo entero y se incrusta, como las fotos: al renderizar no
    se hace ninguna peticion de red ni al disco, que es lo que permite generar
    el PDF dentro de un contenedor sin salida a internet.
    """
    archivo = getattr(org, "logo", None)
    if not archivo:
        return ""
    try:
        with archivo.open("rb") as f:
            contenido = f.read()
    except (OSError, ValueError) as fallo:
        # Un logo que no se puede leer no puede costar el expediente entero:
        # el archivo pudo borrarse del almacenamiento y la fila seguir ahi.
        print(f"[solicitudes] no se pudo leer el logo de la org: {fallo!r}")
        return ""
    return _data_uri(contenido, _mime_de(contenido))


def _radicado(solicitud) -> str:
    """
    El numero con el que se nombra este expediente.

    Se DERIVA de la fecha y del id, no se lleva un contador: un contador
    necesita una secuencia que dos servicios pueden pisarse, y esto solo tiene
    que ser legible y unico. Con la fecha adelante, ordena solo en una carpeta.
    """
    fecha = timezone.localtime(solicitud.enviada_en or timezone.now())
    return f"R-{fecha:%Y-%m-%d}-{str(solicitud.id).replace('-', '')[-7:].upper()}"


def armar_expediente(solicitud, imagenes: dict, firma: bytes) -> ContentFile:
    """El PDF completo, listo para guardar en el FileField."""
    from invoices.pdf import check_weasyprint

    check_weasyprint()
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    contexto = {
        "s": solicitud,
        "generado_en": timezone.localtime(),
        "radicado": _radicado(solicitud),
        "empresa": getattr(getattr(solicitud, "org", None), "name", "") or "",
        "logo": _logo_de(getattr(solicitud, "org", None)),
        "ubicacion": _calidad_ubicacion(solicitud),
        "imagenes": [
            {"numero": i, "rotulo": ROTULOS_IMAGEN[n], "src": _data_uri(b, _mime_de(b))}
            for i, (n, b) in enumerate(
                ((n, imagenes.get(n)) for n in ROTULOS_IMAGEN), start=1) if b
        ],
        "firma": _data_uri(firma, _mime_de(firma)) if firma else "",
        # El formato que usa OZMAP para pegar una coordenada: latitud y
        # longitud separadas por coma, sin espacio y sin grados. Se imprime
        # asi para poder copiarla y pegarla tal cual, que es lo que hace
        # quien valida la cobertura.
        "ozmap": (f"{solicitud.gps_lat},{solicitud.gps_lng}"
                  if solicitud.tiene_gps else ""),
        "mapa": (
            f"https://www.google.com/maps?q={solicitud.gps_lat},{solicitud.gps_lng}"
            if solicitud.tiene_gps else ""
        ),
    }
    html = render_to_string("solicitudes/expediente.html", contexto)

    salida = BytesIO()
    HTML(string=html).write_pdf(salida, font_config=FontConfiguration())
    return ContentFile(salida.getvalue())
