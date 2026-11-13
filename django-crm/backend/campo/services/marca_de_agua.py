# -*- coding: utf-8 -*-
"""
================================================================================
 LA MARCA DE AGUA DE UNA EVIDENCIA  --  12/11/2026
================================================================================

Dibuja sobre la foto de un trabajo: el nombre de la empresa, su logo, quien la
tomo, donde y cuando. Lo pidio el usuario para las instalaciones, y despues
para toda evidencia.

SE DIBUJA EN EL SERVIDOR, Y ESO FUE UNA DECISION
------------------------------------------------
La alternativa era estamparla en el telefono. Se descarto por una razon
concreta de este proyecto: la aplicacion se actualiza A MANO, telefono por
telefono, y una marca de agua se va a querer ajustar varias veces. En el
servidor cada ajuste es un valor en una pantalla; en el telefono serian 77 MB
por tecnico, cada vez.

Lo que se pierde, dicho: la copia que queda EN EL TELEFONO no lleva marca. Si
el tecnico comparte esa foto por fuera de la aplicacion, va sin sello.

NO CONOCE NINGUNA EMPRESA
-------------------------
Esta funcion recibe `(bytes, config, datos)` y devuelve bytes. No lee la base,
no sabe que existe Rapilink, y lo que se estampa lo decide la configuracion de
cada empresa (CLAUDE.md §3.3). Lo generico es COMO se dibuja; lo que varia es
QUE se dibuja.

FALLA ABIERTA, SIEMPRE
----------------------
Si la imagen no se puede abrir --un HEIC sin `pillow-heif`, un PDF, un archivo
cortado-- se devuelve el original sin tocar. Es el mismo criterio que la
aplicacion ya aplica a la ubicacion ("la ubicacion nunca puede costar una
evidencia") y la inspeccion visual ("NUNCA LEVANTA"): una marca de agua no
puede hacer que se pierda la prueba de un trabajo.

LAS TRES MENTIRAS QUE ESTA FUNCION SE NIEGA A ESTAMPAR
-------------------------------------------------------
Medidas sobre lo que la aplicacion ya manda, antes de escribir una linea:

  1. UNA FOTO DE GALERIA NO DICE DONDE SE TOMO. Desde el 09/11/2026 el tecnico
     puede elegir una imagen de la galeria y la aplicacion lo marca con
     `de_galeria`. Estamparle las coordenadas del momento en que la eligio
     afirma «esto se tomo aca» sobre algo que pudo ser de otro dia y otra
     casa, y lo deja horneado en el pixel, con cara de prueba.
  2. SIN GPS NO ES `0,0`. `UbicacionDeCaptura` (la app) omite `lat`/`lng`
     cuando no pudo fijar, y manda `ubicacion_motivo` con el porque. Cero
     grados por cero grados es una coordenada valida, en el golfo de Guinea.
  3. UNA POSICION SIMULADA NO ES UNA POSICION. La app manda
     `ubicacion_simulada` cuando el sistema declara la ubicacion falseada.
     Estamparla como real es exactamente el dano que esta marca existe para
     evitar.

Y una cuarta que no es mentira sino ruido: `precision_m`. Seis decimales sobre
una posicion triangulada con ±2000 m aparentan una precision que no hay, asi
que la marca redondea segun lo que el aparato dijo saber.
================================================================================
"""
from __future__ import annotations

import io
import logging
from datetime import timezone as _tz
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

#: Las horas se reportan en la zona de la operacion, no en UTC (CLAUDE.md §8).
ZONA = ZoneInfo("America/Bogota")

#: Donde se puede poner la marca.
ESQUINAS = ("abajo_izquierda", "abajo_derecha", "arriba_izquierda",
            "arriba_derecha")

#: POR QUE NO SE IMPRIME EL MOTIVO CRUDO: ver `_texto_de_coordenada`. Son los
#: cuatro que la app emite (`core/storage/ubicacion_de_captura.dart`), y la
#: traduccion los vuelve legibles para quien mira la foto en un ticket.
MOTIVOS_DE_UBICACION = {
    "servicio_apagado": "GPS apagado",
    "permiso_denegado": "sin permiso de ubicacion",
    "sin_senal_gps": "sin señal GPS",
}

#: Tipos sobre los que se dibuja. Un PDF o un HEIC caen al fallo abierto.
MIMES_QUE_SE_ESTAMPAN = ("image/jpeg", "image/jpg", "image/png", "image/webp")

#: Calidad del reencode. NO ES UN NUMERO ELEGIDO AL AZAR: la foto llega del
#: telefono ya a calidad 85 y 1920 px de ancho, y de aca sale hacia WispHub,
#: que descarta en silencio relativo toda foto de mas de 5 MB
#: (`nucleo/seguimiento/nota_en_el_ticket.py`). Reencodear por encima de la
#: calidad de origen agranda el archivo sin agregar detalle --el detalle ya se
#: perdio en el telefono-- y acerca el tope sin ganar nada.
CALIDAD = 85

#: Alto de la banda, como fraccion del lado corto. Una banda proporcional se
#: lee igual en una foto de 1920 y en una de 800; una de pixeles fijos es
#: enorme en la chica e invisible en la grande.
_ALTO_BANDA = 0.055
_MIN_TIPOGRAFIA = 11


def _texto_de_coordenada(metadatos: dict) -> str:
    """La linea de ubicacion, o por que no hay.

    Devuelve "" cuando la configuracion no la pide o cuando estamparla seria
    afirmar algo que no se midio.
    """
    if "lat" not in metadatos or "lng" not in metadatos:
        #  EL MOTIVO SALE DE UN CATALOGO CERRADO  --  12/11/2026, hallazgo
        #  H2 de la revision de PII, medido.
        #
        #  Esto imprimia `ubicacion_motivo` TAL CUAL, y ese campo llega dentro
        #  de `metadatos_captura`, que es un `DictField` SIN VALIDAR
        #  (`campo/serializers.py`): lo escribe quien sube. La revision midio
        #  un motivo de 190 caracteres con una cedula y un telefono adentro
        #  saliendo entero como linea de la marca -- y de ahi al ticket de
        #  WispHub, al caso del CRM y al proveedor de vision, horneado en el
        #  pixel. `nucleo/seguridad/redaccion.py` no puede ayudar: mira el
        #  texto que vuelve, no la imagen que va.
        #
        #  NO SE PIERDE NINGUN MOTIVO LEGITIMO: estos cuatro son los unicos
        #  que la app produce (`ubicacion_de_captura.dart`), y los cuatro
        #  mandan a revisar cosas distintas. Cualquier otra cosa cae al
        #  generico en vez de imprimirse.
        motivo = str(metadatos.get("ubicacion_motivo") or "").strip()
        legible = MOTIVOS_DE_UBICACION.get(motivo)
        if legible is None and motivo.startswith("error_"):
            #  La app arma `error_<TipoDeExcepcion>`, que es un nombre de
            #  clase de Dart: sin espacios y sin datos. Se acota igual.
            legible = "error del sistema"
        return f"Sin ubicacion ({legible})" if legible else "Sin ubicacion"

    try:
        lat = float(metadatos["lat"])
        lng = float(metadatos["lng"])
    except (TypeError, ValueError):
        return "Sin ubicacion"

    #  LOS DECIMALES SEGUN LA PRECISION QUE EL APARATO DIJO TENER. Seis
    #  decimales son ~11 cm; con ±2000 m de triangulacion, escribirlos es
    #  inventar precision. Cinco decimales ~1 m, cuatro ~11 m, tres ~110 m.
    try:
        precision = float(metadatos.get("precision_m") or 0)
    except (TypeError, ValueError):
        precision = 0
    if precision > 500:
        decimales = 3
    elif precision > 50:
        decimales = 4
    else:
        decimales = 6

    texto = f"{lat:.{decimales}f}, {lng:.{decimales}f}"
    if precision > 0:
        texto += f" (±{int(precision)} m)"
    if metadatos.get("ubicacion_simulada") is True:
        #  NO SE CALLA Y NO SE OMITE: una ubicacion simulada estampada como
        #  real es el dano que la marca existe para evitar, y omitirla sin mas
        #  dejaria la foto sin ubicacion por un motivo que nadie veria.
        #
        #  PERO NO ACUSA  --  12/11/2026, pregunta 6 de la revision de PII.
        #  Decia «UBICACION SIMULADA», que es una afirmacion sobre la conducta
        #  de un empleado horneada de forma irreversible en un archivo que
        #  sale de la empresa, y el flag tiene falsos positivos conocidos
        #  (emuladores, relojes desfasados, algunas ROMs). «No verificada» le
        #  dice exactamente lo mismo a quien audita la foto y no afirma nada
        #  sobre una persona.
        texto += "  (ubicacion no verificada)"
    return texto


def lineas_de(config: dict, datos: dict) -> list[str]:
    """Que dice la marca. Separado del dibujo para poder probarlo solo.

    `config` es lo que la empresa eligio; `datos` lo que el sistema sabe de
    ESTA evidencia. Ninguna de las dos cosas se inventa aca.
    """
    metadatos = datos.get("metadatos_captura") or {}
    de_galeria = metadatos.get("de_galeria") is True
    lineas: list[str] = []

    if config.get("mostrar_empresa") and datos.get("empresa"):
        lineas.append(str(datos["empresa"]))

    if config.get("mostrar_tecnico") and datos.get("tecnico"):
        lineas.append(str(datos["tecnico"]))

    if config.get("mostrar_fecha") and datos.get("fecha"):
        cuando = datos["fecha"]
        try:
            if cuando.tzinfo is None:
                cuando = cuando.replace(tzinfo=_tz.utc)
            lineas.append(cuando.astimezone(ZONA).strftime("%d/%m/%Y %H:%M"))
        except (AttributeError, ValueError, OSError):
            pass

    if config.get("mostrar_coordenadas"):
        if de_galeria:
            #  Ver la mentira 1 del encabezado. No se calla que la imagen no
            #  es del momento: callarlo dejaria una foto sin ubicacion
            #  indistinguible de una que no pudo fijar el GPS.
            lineas.append("Imagen de galeria (sin ubicacion de captura)")
        else:
            texto = _texto_de_coordenada(metadatos)
            if texto:
                lineas.append(texto)

    extra = str(config.get("texto_extra") or "").strip()
    if extra:
        lineas.append(extra)

    return lineas


#: Las firmas de los formatos que se dibujan. Se mira EL ARCHIVO, no lo que
#: la fila declara -- ver `_se_estampa`.
_FIRMAS_JPEG_PNG = (
    b'\xff\xd8\xff',
    b'\x89PNG\r\n\x1a\n',
)


def _es_imagen_dibujable(contenido: bytes) -> bool:
    """Si estos BYTES son una imagen que se puede dibujar.

    SE MIRA EL ARCHIVO Y NO EL `mime_type` DECLARADO  --  12/11/2026,
    hallazgo H3 de la revision de PII.
    
    Antes esto decidia con el mime que la evidencia declaro al registrarse, y
    ese valor lo manda quien sube. `image/heic` esta en la lista blanca del
    storage y NO esta en la lista de los que se dibujan, asi que registrar
    como HEIC y subir un JPEG guardaba la foto SIN MARCA. No es una fuga: es
    el reverso, y es peor para lo que la marca promete -- la garantia la
    podia apagar justamente el que deberia quedar certificado por ella.

    El repositorio ya habia aprendido esto en otro lado: `solicitudes/pdf.py`
    sniffea los primeros bytes «porque el nombre del archivo miente seguido».
    """
    if not contenido or len(contenido) < 12:
        return False
    if contenido.startswith(_FIRMAS_JPEG_PNG):
        return True
    #  WebP es RIFF....WEBP: el RIFF solo tambien lo usan WAV y AVI.
    return contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP"


def _se_estampa(config: dict, datos: dict) -> bool:
    """Si esta evidencia lleva marca.

    Tres negativas, y cada una tiene su motivo escrito:
      * la empresa la tiene apagada;
      * el archivo no es una imagen que Pillow dibuje (PDF, HEIC);
      * es una FIRMA o una CAPTURA DE PANTALLA. El logo encima de la firma de
        un cliente, o encima de los numeros de un test de velocidad, tapa
        justo lo que la evidencia venia a probar.
    """
    if not config.get("activa"):
        return False
    if not _es_imagen_dibujable(datos.get("contenido") or b""):
        return False
    if datos.get("es_firma"):
        return False
    if datos.get("es_captura") and not config.get("estampar_capturas"):
        return False
    return True


def estampar(contenido: bytes, config: dict, datos: dict) -> bytes:
    """La imagen con su marca, o el ORIGINAL si no se pudo.

    Nunca levanta. Nunca devuelve vacio. Si algo sale mal, lo que vuelve es
    exactamente lo que entro -- perder la prueba de un trabajo por una marca
    de agua seria un intercambio absurdo.
    """
    if not contenido or not _se_estampa(config, {**datos,
                                                  "contenido": contenido}):
        return contenido

    lineas = lineas_de(config, datos)
    logo = datos.get("logo_bytes") if config.get("mostrar_logo") else None
    if not lineas and not logo:
        #  Nada que dibujar: devolver el original es mas honesto que
        #  reencodearlo para no agregarle nada.
        return contenido

    try:
        return _dibujar(contenido, config, lineas, logo)
    except Exception:                                            # noqa: BLE001
        #  Sin `str(e)`: el mensaje de Pillow puede traer la ruta del archivo.
        logger.warning("marca de agua: no se pudo estampar, se guarda el "
                       "original")
        return contenido


def a_la_derecha(posicion: str) -> bool:
    """Si el logo y el texto van contra el borde derecho de la banda."""
    return str(posicion or "").endswith("derecha")


def _dibujar(contenido: bytes, config: dict, lineas: list[str],
             logo: bytes | None) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    with Image.open(io.BytesIO(contenido)) as imagen:
        #  `convert("RGB")` ANTES de dibujar: un PNG con transparencia o un
        #  JPEG en escala de grises no acepta el mismo pegado, y guardarlos
        #  como JPEG sin convertir levanta.
        base = imagen.convert("RGB")

    ancho, alto = base.size
    lado_corto = min(ancho, alto)
    alto_banda = max(int(lado_corto * _ALTO_BANDA) * max(len(lineas), 1),
                     int(lado_corto * _ALTO_BANDA))
    tipografia_px = max(_MIN_TIPOGRAFIA, int(lado_corto * _ALTO_BANDA * 0.6))

    try:
        fuente = ImageFont.truetype("DejaVuSans.ttf", tipografia_px)
    except OSError:
        #  La imagen del backend trae DejaVu (medido el 12/11/2026), pero una
        #  imagen futura podria no traerla: antes de perder la marca entera se
        #  usa la de Pillow, aunque se vea peor.
        fuente = ImageFont.load_default()

    #  La banda se dibuja en una capa aparte y se pega con alfa: escribir
    #  directo sobre la foto no deja regular la opacidad, y un recuadro opaco
    #  tapa parte de la evidencia.
    opacidad = max(0, min(100, int(config.get("opacidad") or 55)))
    capa = Image.new("RGBA", (ancho, alto_banda),
                     (0, 0, 0, int(255 * opacidad / 100)))
    lapiz = ImageDraw.Draw(capa)

    margen = max(8, int(lado_corto * 0.012))
    posicion = str(config.get("posicion") or "abajo_izquierda")
    #  «A LA DERECHA» NO HACIA NADA  --  13/11/2026. La pantalla ofrece cuatro
    #  esquinas y esto solo miraba si era arriba o abajo: elegir «abajo a la
    #  derecha» dejaba la marca exactamente igual que «abajo a la izquierda».
    #  La banda sigue ocupando todo el ancho --una banda angosta tapa lo mismo
    #  y se lee peor--; lo que cambia de lado es el contenido. La app dibuja
    #  la misma regla (`marca_de_agua.dart`), y por eso vive en una funcion.
    derecha = a_la_derecha(posicion)
    x_texto = margen
    ancho_logo = 0
    if logo:
        alto_logo = alto_banda - margen
        try:
            with Image.open(io.BytesIO(logo)) as crudo:
                marca = crudo.convert("RGBA")
            proporcion = alto_logo / max(marca.height, 1)
            marca = marca.resize(
                (max(1, int(marca.width * proporcion)), max(1, alto_logo)))
            x_logo = ancho - margen - marca.width if derecha else margen
            capa.paste(marca, (x_logo, margen // 2), marca)
            ancho_logo = marca.width
            x_texto = margen * 2 + marca.width
        except Exception:                                        # noqa: BLE001
            #  El logo no puede costar la marca entera: si no abre, va el
            #  texto solo.
            logger.warning("marca de agua: el logo no se pudo dibujar")

    y = (alto_banda - tipografia_px * len(lineas)) // 2
    for linea in lineas:
        if derecha:
            borde = ancho - margen - (ancho_logo + margen if ancho_logo else 0)
            x = max(margen, int(borde - lapiz.textlength(linea, font=fuente)))
        else:
            x = x_texto
        lapiz.text((x, y), linea, font=fuente, fill=(255, 255, 255, 255))
        y += tipografia_px

    arriba = posicion.startswith("arriba")
    base_rgba = base.convert("RGBA")
    base_rgba.alpha_composite(capa, (0, 0 if arriba else alto - alto_banda))

    salida = io.BytesIO()
    base_rgba.convert("RGB").save(salida, format="JPEG", quality=CALIDAD,
                                  optimize=True)
    return salida.getvalue()
