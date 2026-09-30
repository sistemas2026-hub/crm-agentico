# -*- coding: utf-8 -*-
"""
================================================================================
 TRANSCRIPCION DE AUDIO  --  lo que el cliente dijo, en palabras
================================================================================

POR QUE EXISTE
--------------
Una nota de voz llegaba al modelo como '[El cliente envio un audio]'. El
cliente contaba su problema hablando y el asistente contestaba sin saber cual
era: le pedia que lo escribiera. Para un ISP eso es media conversacion perdida,
porque la nota de voz es como la gente cuenta que se le fue el internet.

RESPONSABILIDAD UNICA
---------------------
Recibe bytes y devuelve texto. No sabe que es una conversacion, ni un tenant,
ni el agente: quien llama decide que hacer con lo que salga. Mismo criterio que
'nucleo/recuperacion/embeddings.py', que es el otro modulo que le habla a
OpenAI y del que este copia la forma.

EL .OPUS NO SE RECODIFICA, SE RENOMBRA
--------------------------------------
Medido el 30/09/2026 contra la API real: un audio de WhatsApp enviado con
nombre '.opus' responde 400 'Unsupported file format opus'. EL MISMO ARCHIVO,
byte por byte --md5 identico-- enviado como '.ogg' responde 200 y transcribe
bien.

O sea que el rechazo era por el NOMBRE, no por el contenido: WhatsApp entrega
un contenedor Ogg y 'ogg' si esta en la lista de formatos aceptados. Por eso
aqui no hay ffmpeg ni recodificacion: recodificar audio ya comprimido pierde
justo lo que importa --entender a alguien que habla en la calle, con viento--
y no haria falta para nada.

Se comprueba la firma 'OggS' antes de renombrar. Llamarle .ogg a algo que no
lo es solo cambiaria el error de sitio.

LA CLAVE
--------
OPENAI_API_KEY es de PLATAFORMA, no por tenant: mismo criterio que
DEEPSEEK_API_KEY y que el OPENAI_API_KEY que ya usa embeddings.py. Se lee del
entorno, nunca de la config ni de la base, y nunca se registra.

LO QUE NO HACE
--------------
No inventa. Si la API falla, si falta la clave, si el audio no tiene forma de
Ogg o si pesa de mas, devuelve el error y NINGUN texto. Un texto inventado
seria peor que no tener transcripcion: el agente contestaria con seguridad a
algo que el cliente no dijo.
================================================================================
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from nucleo.observabilidad.registro import registrar

#: El modelo. Se declara arriba y no se lee de la config: cambiarlo cambia el
#: costo y la calidad, y es una decision de plataforma como la de embeddings.
MODELO = "gpt-4o-transcribe"

#: El idioma. Decirlo ahorra que el modelo lo adivine y equivoque un audio
#: corto o con ruido -- 'que la tele se fue' son dos segundos.
IDIOMA = "es"

#: Cuanto se espera. Mas corto que el turno del modelo (90 s) a proposito: la
#: transcripcion es parte de la respuesta que el cliente espera, y un audio de
#: 2,7 s tardo 2,9 s en la prueba real. Si tarda un minuto, algo va mal y es
#: mejor contestar sin ella que dejar a alguien esperando.
TIMEOUT_SEGUNDOS = 45.0

#: Tope de tamano. Mas bajo que MAX_BYTES_DESCARGA (16 MB) porque un audio de
#: 16 MB son ~2 horas de voz: eso no es una consulta de soporte, y transcribirlo
#: cuesta caro sin que nadie lo haya pedido.
MAX_BYTES = 25 * 1024 * 1024

#: Los estados por los que pasa. Se nombran aqui para que la base y el codigo
#: usen las mismas palabras.
PENDIENTE = "pendiente"
PROCESANDO = "procesando"
PROCESADO = "procesado"
ERROR = "error"

#: Todo Ogg empieza con estos cuatro bytes. Es lo que distingue un audio de
#: WhatsApp de un archivo que solo se llama parecido.
FIRMA_OGG = b"OggS"

#: Los tipos de mensaje de WhatsApp que traen voz.
TIPOS_DE_VOZ = ("audio", "voice")


@dataclass
class Resultado:
    """
    Que salio. 'texto' vacio y 'error' con algo son el MISMO caso visto de dos
    lados, y quien llama solo tiene que mirar 'texto'.
    """
    texto: str = ""
    error: str = ""
    estado: str = PENDIENTE
    segundos: float = 0.0
    #: Lo que la API dijo que consumio, cuando lo dice. Sirve para saber cuanto
    #: costo de verdad en vez de estimarlo por la duracion.
    tokens: int = 0

    @property
    def ok(self) -> bool:
        return self.estado == PROCESADO and bool(self.texto)


def es_ogg(contenido: bytes) -> bool:
    """Si estos bytes son un contenedor Ogg."""
    return bool(contenido) and contenido[:4] == FIRMA_OGG


def nombre_para_la_api(mime: str = "") -> str:
    """
    Con que nombre subirlo.

    Siempre '.ogg' para un Ogg, venga el mime que venga: WhatsApp manda
    'audio/ogg; codecs=opus' y la API mira la extension, no el mime.
    """
    return "audio.ogg"


def transcribir(contenido: bytes, mime: str = "") -> Resultado:
    """
    Los bytes de un audio -> lo que dice, o el motivo de por que no se pudo.

    NUNCA LEVANTA. Quien llama esta atendiendo a un cliente que espera
    respuesta: una transcripcion que falla no puede dejarlo sin nada. El error
    viaja en el Resultado y se decide arriba.
    """
    import time

    if not contenido:
        return Resultado(estado=ERROR, error="el audio llego vacio")

    if len(contenido) > MAX_BYTES:
        return Resultado(
            estado=ERROR,
            error=f"el audio pesa {len(contenido) // 1024} KB, mas del maximo aceptado")

    if not es_ogg(contenido):
        #  No se intenta convertir: el unico formato que llega por este canal
        #  es Ogg/Opus, y cualquier otra cosa es una señal de que algo cambio
        #  rio arriba. Convertir a ciegas taparia esa señal.
        return Resultado(
            estado=ERROR,
            error="el audio no es un contenedor Ogg: no se envia a transcribir")

    clave = os.environ.get("OPENAI_API_KEY")
    if not clave:
        return Resultado(
            estado=ERROR,
            error="falta OPENAI_API_KEY en el entorno: no se transcribe")

    from openai import OpenAI                            # import perezoso

    #  El archivo temporal existe SOLO para darle un nombre con la extension
    #  correcta. Los bytes son los mismos que llegaron -- no se recodifica
    #  nada -- y el archivo se borra al salir del bloque, pase lo que pase.
    inicio = time.monotonic()
    ruta = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(contenido)
            ruta = tmp.name

        cliente = OpenAI(api_key=clave, timeout=TIMEOUT_SEGUNDOS)
        with open(ruta, "rb") as f:
            r = cliente.audio.transcriptions.create(
                model=MODELO, file=f, language=IDIOMA)

        texto = (getattr(r, "text", "") or "").strip()
        uso = getattr(r, "usage", None)
        tokens = int(getattr(uso, "total_tokens", 0) or 0) if uso else 0

        if not texto:
            #  Un audio sin voz --un toque sin querer, ruido-- devuelve texto
            #  vacio con 200. NO es un error del sistema, pero tampoco hay
            #  nada que pasarle al agente.
            return Resultado(estado=PROCESADO, error="", texto="",
                             segundos=time.monotonic() - inicio, tokens=tokens)

        return Resultado(texto=texto, estado=PROCESADO,
                         segundos=time.monotonic() - inicio, tokens=tokens)

    except Exception as e:
        #  Sin el texto de OpenAI: lo que contesto el proveedor no es de Dexter
        #  y este mensaje termina en logs. La clase de la excepcion alcanza
        #  para saber si fue red, cuota o formato. Mismo criterio que
        #  embeddings.py.
        return Resultado(estado=ERROR, segundos=time.monotonic() - inicio,
                         error=f"{MODELO} rechazo el audio ({type(e).__name__})")
    finally:
        if ruta:
            try:
                os.unlink(ruta)
            except OSError:
                #  Un temporal que no se pudo borrar no puede tumbar un turno.
                registrar("transcripcion", "no se pudo borrar el temporal")


def texto_para_el_agente(transcrito: str, caption: str = "") -> str:
    """
    Como se le cuenta al modelo que esto vino hablado.

    SE DICE QUE ES UNA NOTA DE VOZ, y no es decoracion: el modelo redacta
    distinto cuando sabe que la persona hablo --frases sueltas, sin puntuacion,
    a veces a medias-- que cuando cree que las escribio. Sin el rotulo, una
    transcripcion entrecortada parece un cliente que escribe mal.

    El caption viaja aparte cuando lo hay: son dos cosas que dijo la misma
    persona de dos maneras, y colapsarlas pierde cual fue cual.
    """
    partes = [f"[Nota de voz del cliente] {transcrito}".strip()]
    if (caption or "").strip():
        partes.append(f"[Texto que escribio junto al audio] {caption.strip()}")
    return "\n".join(partes)
