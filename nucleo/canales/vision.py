# -*- coding: utf-8 -*-
"""
================================================================================
 VISION  --  que se ve en la foto que mando el cliente
================================================================================

POR QUE EXISTE
--------------
Una foto llegaba al modelo como '[El cliente envio una foto]'. El cliente
mandaba la luz roja de su ONT --el gesto mas natural que existe en soporte de
un ISP-- y el asistente le pedia que lo describiera en palabras. La foto se
guardaba, se le mostraba a la persona en la bandeja, y nunca llegaba a la IA.

Mismo hueco que tenia la nota de voz antes de nucleo/canales/transcripcion.py,
y este modulo es su espejo: recibe bytes, devuelve texto, y quien llama decide.

UN SOLO PROVEEDOR, EL MISMO QUE CONVERSA
-----------------------------------------
La imagen la mira DeepSeek, que es el mismo modelo que despues contesta. No
hay un segundo proveedor para imagenes.

Medido el 02/10/2026 contra la API real, con la ONT sintetica de
tests/imagen_ont_sintetica.py:

    multimodal libre          8.0 s   2.399 tokens   describe bien
    response_format json      26.2 s  6.686 tokens   devolvio listas vacias
    json_schema               400 'This response_format type is unavailable now'
    json_schema + strict      400, el mismo error

Por eso aca no se pide JSON de ninguna forma: se pide texto. Pedir
'json_object' triplicaba la latencia, multiplicaba por tres los tokens y
devolvia MENOS -- el modelo se quedaba sin nada que decir al tener que
encajar en una forma que el endpoint no sabe declarar.

NO SE USA cliente.py A MEDIAS: SE USA ENTERO
---------------------------------------------
La llamada va por nucleo/modelo/cliente.py::chat, el mismo camino que el
turno. Se comprobo que 'ClienteCompatibleOpenAI._adaptar' copia el mensaje y
solo reescribe 'tool_calls': un 'content' que es una LISTA pasa intacto, asi
que el formato multimodal no necesito ningun cambio en el cliente.

Lo que se gana: el modelo sale de la config del TENANT (no es una constante
de plataforma), el consumo se puede contabilizar con las tarifas que ya estan
declaradas, y no hay un segundo SDK abierto en paralelo.

LO QUE ESTE MODULO NO PUEDE GARANTIZAR, Y HAY QUE SABERLO
-----------------------------------------------------------
Devuelve TEXTO LIBRE. La version anterior usaba un catalogo cerrado --el
modelo elegia de una lista y lo que no estaba en ella se descartaba en
codigo-- y eso daba dos garantias que aca NO existen:

  1. Anti-alucinacion por construccion. Ahora la unica defensa es la
     instruccion de abajo, que es guia y no garantia (PRD 7.4). El modelo
     PUEDE afirmar algo que no esta en la foto.
  2. Que al historial solo llegaran palabras de un catalogo. Ahora puede
     llegar cualquier cosa que el modelo escriba, y la conversacion vive 365
     dias mientras la foto se borra a los 30
     (limites.retencion_multimedia_dias).

Contra (2) queda una defensa parcial y barata: el texto pasa por
nucleo/seguridad/redaccion.py antes de salir, que es el mismo modulo que ya
tapa cedulas, telefonos, correos y coordenadas en el resto del sistema. No
cubre todo lo que un catalogo cerrado cubria --no puede-- pero cierra el caso
concreto que importa: un numero de documento que se veia en la foto.

LA CLAVE
--------
DEEPSEEK_API_KEY, la misma que ya usa el turno, leida por cliente.py del
entorno. Este modulo no la toca, no la lee y no la registra.
================================================================================
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass

from nucleo.seguridad.redaccion import redactar

#: Cuanto se espera. La prueba real multimodal tardo 8.0 s; 30 s deja margen
#: de 3.7x para una foto mas grande o un dia lento. MAS CORTO que el turno
#: (90 s) a proposito: el analisis corre ANTES, asi que cada segundo se lo
#: suma a lo que espera el cliente, y una foto tolera peor la espera que una
#: nota de voz -- quien manda una foto ya hizo el esfuerzo de tomarla.
TIMEOUT_SEGUNDOS = 30.0

#: Tope de tamano. Mas bajo que MAX_BYTES_DESCARGA (16 MB) de whatsapp.py: lo
#: que llega aca ya paso por media.comprimir_imagen() y una foto comprimida
#: pesa decenas de KB. Un archivo de 8 MB en este punto significa que la
#: compresion no corrio, y mandarlo igual seria pagar de mas por nada.
MAX_BYTES = 8 * 1024 * 1024

#: Cuanto texto se le acepta al modelo. Una descripcion util de una foto de
#: soporte entra en un parrafo; mil palabras son el modelo divagando, y eso
#: entra al historial y se paga en cada turno siguiente.
MAX_CARACTERES = 1200

#: Los estados por los que pasa. Se nombran aca para que la base y el codigo
#: usen las mismas palabras (igual que en transcripcion.py).
PENDIENTE = "pendiente"
PROCESANDO = "procesando"
PROCESADO = "procesado"
ERROR = "error"

#: Firmas de los unicos dos formatos que se envian. Mismo criterio que
#: FIRMA_OGG en transcripcion.py: llamarle JPEG a algo que no lo es solo
#: cambia el error de sitio. comprimir_imagen() ya entrega JPEG, asi que algo
#: que no sea JPEG ni PNG aca es senal de que la compresion no corrio, y esa
#: senal no se tapa.
FIRMA_JPEG = bytes([0xFF, 0xD8, 0xFF])
FIRMA_PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])

#: El tipo de mensaje de WhatsApp que trae imagen. Tupla, y no una cadena,
#: para que se lea igual que TIPOS_DE_VOZ en transcripcion.py.
TIPOS_DE_IMAGEN_ENTRANTE = ("image",)

#: La instruccion. Es GUIA, no garantia (PRD 7.4): sin catalogo cerrado, nada
#: en el codigo impide que el modelo afirme algo que no esta en la foto. Por
#: eso esta escrita alrededor de una sola idea --decir lo que se ve y nombrar
#: lo que no se puede saber-- y no alrededor de diagnosticar.
#:
#: Las reglas 3 y 4 son las que mas importan. Un cliente que manda la foto de
#: su router quiere que le arreglen el internet, y un modelo servicial tiende
#: a contestar eso: "su equipo esta danado". Una foto no muestra un equipo
#: danado, muestra una luz roja.
INSTRUCCION = (
    "Eres el asistente de soporte de un proveedor de internet. Un cliente "
    "acaba de enviar esta foto por WhatsApp. Describi lo que se ve, para que "
    "otro agente pueda usarlo.\n\n"
    "Reglas:\n"
    "1. Describi UNICAMENTE lo que se ve en la imagen. Si algo esta borroso, "
    "tapado o fuera de cuadro, decilo.\n"
    "2. Si hay luces indicadoras, deci cuales son, de que color y si estan "
    "fijas o parpadeando. El color importa: rojo y naranja no son lo mismo.\n"
    "3. NO afirmes que algo esta danado, roto, mal instalado o fuera de "
    "servicio. Eso no se ve en una foto: se ve una luz, un cable o una marca. "
    "Si queres sugerir una causa, decila como posibilidad y deci en que te "
    "basas.\n"
    "4. NO digas si el servicio funciona o no, ni si hay senal. Una foto no "
    "lo muestra.\n"
    "5. NO transcribas numeros de documento, cedulas, telefonos ni datos "
    "personales que aparezcan en la imagen, aunque se lean.\n"
    "6. Si la foto no tiene nada que ver con equipos, instalaciones o "
    "servicio de internet, deci en una linea que se ve y nada mas.\n"
    "7. Se breve: un parrafo corto. Sin saludos y sin ofrecer ayuda -- de eso "
    "se encarga el agente que lee esto."
)


@dataclass
class Resultado:
    """
    Que salio. Misma forma que transcripcion.Resultado para que quien llame
    no tenga que aprender dos contratos.
    """
    texto: str = ""
    estado: str = PENDIENTE
    error: str = ""
    segundos: float = 0.0
    tokens: int = 0
    modelo: str = ""

    @property
    def ok(self) -> bool:
        return self.estado == PROCESADO and bool(self.texto)


def es_imagen(contenido: bytes) -> bool:
    """Si estos bytes son un JPEG o un PNG. Nada mas se envia."""
    if not contenido:
        return False
    return contenido[:3] == FIRMA_JPEG or contenido[:8] == FIRMA_PNG


def _mime_de(contenido: bytes) -> str:
    """El mime segun la firma, no segun lo que diga quien lo mando."""
    return "image/png" if contenido[:8] == FIRMA_PNG else "image/jpeg"


def mensaje_multimodal(contenido: bytes, pie: str = "") -> list[dict]:
    """
    Los dos mensajes que se le mandan al modelo.

    La imagen viaja como data URL en base64, que es el formato que el endpoint
    acepta -- verificado contra la API real el 02/10/2026, no deducido de la
    documentacion.

    EL PIE DEL CLIENTE VA JUNTO A LA IMAGEN y rotulado como suyo. Sin eso el
    modelo describe la foto entera por igual; con eso sabe que mirar. "Mira la
    lucecita roja" cambia por completo que vale la pena contar de una foto en
    la que tambien se ve la sala.

    El base64 vive SOLO en el valor que devuelve esta funcion: no se guarda,
    no se registra y no entra al historial.
    """
    datos = base64.b64encode(contenido).decode("ascii")
    partes: list[dict] = []
    if (pie or "").strip():
        partes.append({
            "type": "text",
            "text": f"El cliente escribio junto a la foto: {pie.strip()}"})
    partes.append({
        "type": "image_url",
        "image_url": {"url": f"data:{_mime_de(contenido)};base64,{datos}"}})
    return [{"role": "system", "content": INSTRUCCION},
            {"role": "user", "content": partes}]


def analizar(contenido: bytes, modelo: str, pie: str = "",
             temperatura: float = 0.1) -> Resultado:
    """
    Los bytes de una imagen -> que se ve, o el motivo de por que no se pudo.

    'modelo' es la referencia completa del tenant ('deepseek:deepseek-v4-flash'):
    sale de la config, no de una constante de este archivo, porque es un dato
    que varia por empresa (CLAUDE.md 3.3).

    NUNCA LEVANTA, por la misma razon que transcripcion.transcribir(): quien
    llama esta atendiendo a un cliente que espera respuesta, y una foto que no
    se pudo mirar no puede dejarlo sin nada. El error viaja en el Resultado y
    se decide arriba.
    """
    if not contenido:
        return Resultado(estado=ERROR, error="la imagen llego vacia")

    if len(contenido) > MAX_BYTES:
        return Resultado(
            estado=ERROR,
            error=f"la imagen pesa {len(contenido) // 1024} KB, mas del maximo")

    if not es_imagen(contenido):
        #  No se intenta convertir: lo que llega aca ya paso por
        #  media.comprimir_imagen(), que entrega JPEG. Convertir a ciegas
        #  taparia la senal de que esa compresion no corrio.
        return Resultado(
            estado=ERROR,
            error="el archivo no es JPEG ni PNG: no se envia a analizar")

    if not modelo:
        return Resultado(estado=ERROR,
                         error="no hay modelo configurado para vision")

    #  Perezoso y adentro del try: importar el cliente arrastra el SDK, y un
    #  fallo de import no puede tumbar el turno.
    inicio = time.monotonic()
    try:
        from nucleo.modelo import cliente

        r = cliente.chat(
            modelo,
            mensaje_multimodal(contenido, pie),
            temperatura=temperatura,
            timeout=TIMEOUT_SEGUNDOS)

        texto = (r.contenido or "").strip()
        tokens = (r.tokens_entrada or 0) + (r.tokens_salida or 0)

        if not texto:
            #  El modelo contesto sin decir nada. No es un error del sistema,
            #  pero tampoco hay nada que pasarle al agente: inventar una
            #  descripcion seria exactamente lo que no se puede hacer.
            return Resultado(estado=PROCESADO, texto="", modelo=modelo,
                             segundos=time.monotonic() - inicio, tokens=tokens)

        #  SE RECORTA ANTES DE REDACTAR, y el orden importa: recortar despues
        #  podria partir un reemplazo al medio y dejar media etiqueta.
        if len(texto) > MAX_CARACTERES:
            texto = texto[:MAX_CARACTERES].rsplit(" ", 1)[0] + "..."

        #  LA UNICA DEFENSA QUE QUEDA DEL LADO DEL CODIGO. Sin catalogo
        #  cerrado, esto es lo que impide que una cedula que se veia en la
        #  foto viva 365 dias en el historial de una conversacion cuya imagen
        #  se borra a los 30. La instruccion ya le pide al modelo que no las
        #  transcriba; esto es lo que pasa cuando igual lo hace.
        texto = redactar(texto)

        return Resultado(texto=texto, estado=PROCESADO, modelo=modelo,
                         segundos=time.monotonic() - inicio, tokens=tokens)

    except Exception as e:
        #  Sin el texto del proveedor: lo que contesto no es de Dexter y este
        #  mensaje termina en logs. La clase de la excepcion alcanza para
        #  saber si fue red, cuota o formato. Mismo criterio que
        #  transcripcion.py y embeddings.py.
        return Resultado(estado=ERROR, modelo=modelo,
                         segundos=time.monotonic() - inicio,
                         error=f"el modelo rechazo la imagen ({type(e).__name__})")


def texto_para_el_agente(r: Resultado, pie: str = "") -> str:
    """
    El Resultado -> las lineas que lee el modelo conversacional.

    LO QUE ESCRIBIO LA PERSONA VA PRIMERO, y despues lo que vio la maquina.
    El orden no es estetico: "Asi esta la luz LOS" dice que mirar, y leerlo
    antes del analisis ordena el resto. Ademas deja claro de quien es cada
    cosa -- una es un cliente hablando, la otra es una lectura automatica, y
    el agente no puede tratarlas igual.

    EL PIE APARECE UNA SOLA VEZ. Quien llama le pasa el pie ya resuelto (ver
    api.py::_analizar_si_es_imagen) y esta funcion no lo busca por su cuenta
    en ningun otro lado.

    'Analisis automatico de la foto' y no 'Se observa': el rotulo le dice al
    modelo que esto lo escribio otra IA mirando pixeles, no una persona
    verificando. Sin esa marca, el agente repite la descripcion como un hecho
    comprobado.
    """
    if not r.ok:
        return ""

    lineas = ["[Foto que envio el cliente]"]

    if (pie or "").strip():
        lineas.append("")
        lineas.append("[Texto que escribio junto con la imagen]")
        lineas.append(pie.strip())

    lineas.append("")
    lineas.append("[Analisis automatico de la foto, no verificado]")
    lineas.append(r.texto)

    return "\n".join(lineas)
