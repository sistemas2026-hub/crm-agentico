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


#: La instruccion para una foto que un COLABORADOR adjunta en el asistente
#: interno (02/11/2026). Ni el cliente ni una evidencia de orden: alguien de
#: la empresa que esta preguntando algo y acompana una foto.
#:
#: Se parece a la de evidencia --quien lee es la oficina, asi que puede decir
#: lo que ve del trabajo-- y conserva las tres reglas que no dependen de
#: quien mira: no afirmar que el servicio funciona, no inventar mediciones, y
#: no leer datos personales. La diferencia es que aca la foto puede ser de
#: cualquier cosa, asi que la regla de "si no es de esto, decilo en una
#: linea" pesa mas.
INSTRUCCION_ASISTENTE = (
    "Alguien del equipo de un proveedor de internet te adjunto esta foto "
    "mientras te preguntaba algo. Describi lo que se ve, para que puedas "
    "contestarle.\n\n"
    "Reglas:\n"
    "1. Deci que se ve: equipos de telecomunicaciones (ONT, router, modem, "
    "fuente, caja, roseta, conectores, cables), una pantalla, un documento "
    "tecnico, un lugar. Solo lo que se ve.\n"
    "2. Marca, modelo y numeros de serie SOLO si se leen en la imagen.\n"
    "3. Si hay luces indicadoras, deci cuales, de que color y si estan "
    "fijas o parpadeando. No digas que significan: cambia con cada "
    "fabricante.\n"
    "4. Si se ve una instalacion, deci como quedo --cableado, fijacion, "
    "conectores-- como lo que se OBSERVA y no como un diagnostico.\n"
    "5. NO digas si el servicio funciona, si hay senal, ni inventes "
    "mediciones de potencia optica, velocidad o continuidad.\n"
    "6. Si algo esta borroso, oscuro o tapado, decilo.\n"
    "7. Si la foto no tiene que ver con equipos, instalaciones ni "
    "servicio, deci en una linea que se ve y nada mas.\n"
    "8. NO transcribas documentos, cedulas, telefonos ni datos "
    "personales, aunque se lean. No describas a las personas que "
    "aparezcan.\n"
    "9. Se breve: un parrafo corto. Sin saludos."
)

#: Cada proposito, con su instruccion, su interruptor en la config del tenant
#: y como se rotula la foto en el turno. UN SOLO LUGAR donde se declaran, para
#: que agregar un camino nuevo sea una fila y no tres `if` repartidos.
#:
#: CADA UNO TIENE SU INTERRUPTOR, y no es burocracia: no es el mismo
#: consentimiento la foto que un cliente DECIDE mandar, la que un tecnico toma
#: DENTRO de su casa, y la que un colaborador adjunta en el chat interno. Una
#: empresa puede autorizar una y no las otras, y con un solo campo no podria
#: decirlo. Todos nacen apagados.
PROPOSITOS = {
    "whatsapp_cliente": {
        "bandera": "vision_habilitada",
        "rotulo": "[Foto que envio el cliente]",
    },
    "evidencia_campo": {
        "bandera": "vision_evidencias_campo",
        "rotulo": "[Foto de evidencia que subio el tecnico]",
    },
    "asistente_interno": {
        "bandera": "vision_asistente_interno",
        "rotulo": "[Foto que adjuntaste]",
    },
}


def instruccion_de(proposito: str) -> str:
    """La instruccion de ese proposito. Un nombre desconocido cae en la del
    cliente, que es la MAS restrictiva: no afirma nada sobre instalaciones."""
    if proposito == "evidencia_campo":
        return INSTRUCCION_EVIDENCIA
    if proposito == "asistente_interno":
        return INSTRUCCION_ASISTENTE
    return INSTRUCCION


def bandera_de(proposito: str) -> str:
    """El campo de la config que habilita ese proposito, o "" si no existe.

    Falla CERRADO en quien llama: un proposito desconocido no tiene bandera,
    y sin bandera no se habilita nada.
    """
    return (PROPOSITOS.get(proposito) or {}).get("bandera", "")


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


#: LA MARCA QUE CIERRA EL ANALISIS DE UNA EVIDENCIA  --  05/11/2026
#:
#: LA FOTO ES LO QUE SE PIDIO, O NO (06/11/2026). El usuario: «si piden foto
#: del router y manda el TV no debe pasar».
#:
#: VA APARTE DE `ATENCION` PORQUE SON DOS COSAS DISTINTAS, y mezclarlas le
#: quita a cada una lo suyo: «se ve un cable suelto» dice que el TRABAJO tiene
#: un problema; «hay un televisor donde pedian el router» dice que la FOTO
#: esta mal. La primera se arregla volviendo a la casa; la segunda, sacando
#: otra foto. El supervisor necesita distinguirlas de un vistazo.
#:
#: NO BLOQUEA NADA, y eso no cambia: la IA puede pedir atencion y nunca negar
#: un cierre (ver `campo/inspeccion_visual.py`, decidido el 31/10/2026). Esto
#: es una señal mas para quien mira.
MARCA_MUESTRA = "muestra:"

#: El modelo termina con "ATENCION: si" o "ATENCION: no", y eso es lo que el
#: CRM lee para decidir si una persona tiene que mirar la foto
#: (`campo/tasks.py::_pide_atencion`).
#:
#: POR QUE UNA MARCA Y NO BUSCAR PALABRAS. La primera version buscaba
#: "borroso", "no se ve", "no se puede"... en el texto. Medido en produccion
#: el 04/11/2026: 4 de 4 fotos pedian una mirada, en todas las ordenes. El
#: motivo estaba a la vista y era de esta misma instruccion: sus reglas le
#: PIDEN al modelo que diga "si algo esta borroso... deci que no se puede
#: determinar" y "contesta si eso se ve o no se ve". O sea, se le pedian las
#: frases y despues se usaban como alarma.
#:
#: El costo no fue el ruido: el veredicto quedaba en REVISAR y el cierre
#: autonomo del Supervisor exige CERRAR, asi que ninguna orden con fotos se
#: cerraba sola. Y un aviso que aparece siempre deja de avisar.
#:
#: ES GUIA, NO GARANTIA (PRD 7.4): nada impide que el modelo no la escriba.
#: Por eso el CRM cae a una lista de palabras --ya limpia de las que esta
#: instruccion exige-- cuando la marca no esta.
MARCA_ATENCION = "ATENCION"

#: La instruccion para una foto de EVIDENCIA de una orden de campo
#: (31/10/2026). Es otra cosa que la de arriba, y la diferencia es el punto:
#: las reglas 3 y 4 de INSTRUCCION prohiben decir que algo esta mal instalado
#: --correcto cuando quien mira es el cliente por WhatsApp-- y aca eso es
#: justo lo que se pregunta. Quien lee esto es la oficina.
#:
#: LO QUE NO CAMBIA, y por eso se repite entero: sigue sin poder afirmar que
#: el servicio funciona ni inventar una medicion. Una foto muestra un cable y
#: una luz; la potencia optica no se ve.
#:
#: NO VA EN LA CONFIG DEL TENANT. Lo que varia por empresa es QUE tiene que
#: mostrar cada foto, y eso ya vive en el esquema de la plantilla
#: ('evidencias[].instrucciones', campo/plantillas.py:507) -- se pasa como
#: 'pie'. Esto es como se mira una foto de instalacion, igual para cualquiera.
INSTRUCCION_EVIDENCIA = (
    "Sos un inspector de instalaciones de un proveedor de internet. Un "
    "tecnico subio esta foto como evidencia de un trabajo. La lee la oficina, "
    "no el cliente.\n\n"
    "Reglas:\n"
    "1. Deci que elementos de telecomunicaciones se ven: ONT, router, modem, "
    "access point, fuente, caja de distribucion, roseta, conectores, patch "
    "cord, cable UTP, fibra. SOLO los que se ven: NO enumeres los que no "
    "estan. Esta lista esta para que los reconozcas, no para recorrerla.\n"
    "2. Marca y modelo SOLO si se leen en la imagen. Si no, no los nombres.\n"
    "3. Si hay luces indicadoras, deci cuales, de que color y si estan fijas "
    "o parpadeando. No digas que significan: eso cambia con cada fabricante. "
    "Si no se ven luces, no lo menciones.\n"
    "4. Deci lo que se ve del trabajo: como quedo el cableado, si los equipos "
    "estan fijados, si hay cables sueltos o conectores que parecen no estar "
    "puestos. Decilo como lo que es --lo que se OBSERVA-- y no como un "
    "diagnostico. 'Se ve un cable suelto' esta bien; 'la instalacion esta "
    "mal' no.\n"
    "5. NO digas si el servicio funciona, si hay senal, ni inventes "
    "mediciones de potencia optica, velocidad o continuidad. Nada de eso se "
    "ve en una foto.\n"
    "6. Si algo esta borroso, oscuro, tapado o fuera de cuadro, decilo, y "
    "deci que no se puede determinar por eso.\n"
    "6b. Si en la imagen hay una PANTALLA con numeros --un medidor, un test--, "
    "copiá cada numero digito por digito tal como aparece, con el punto "
    "decimal donde esta. No lo reacomodes ni lo redondees: '-21.0' y '-2.10' "
    "son numeros distintos, y moverle el punto cambia el dato. Si el punto "
    "decimal no se distingue, deci que no se distingue en vez de elegir uno.\n"
    "6c. EL HUECO QUE DEJA UN 1 NO ES UN PUNTO DECIMAL. En los visores "
    "de siete segmentos el digito 1 son dos barras verticales pegadas al "
    "lado DERECHO de su casilla, asi que a su izquierda queda un espacio "
    "vacio tan ancho como medio digito. Ese espacio no es nada: es la "
    "parte apagada de la casilla del 1. Un punto decimal de verdad es un "
    "cuadrito oscuro ABAJO, a la altura de la base de los digitos, nunca "
    "un hueco centrado. Antes de poner un punto, fijate si a su derecha "
    "hay un 1: si lo hay, lo mas probable es que ese hueco sea del 1 y no "
    "haya punto ahi. Medido en produccion el 12/11/2026: un visor que "
    "marcaba -21.0 se leyo -2.10 cinco veces seguidas, una de ellas "
    "agregando que el punto decimal era visible.\n"
    "7. Si te dicen que tenia que mostrar esta foto, contesta ademas si eso "
    "se ve o no se ve, en una linea.\n"
    "8. NO transcribas numeros de documento, cedulas, telefonos ni datos "
    "personales que aparezcan en la imagen, aunque se lean. Tampoco "
    "describas a las personas que aparezcan, ni leas direcciones, placas ni "
    "papeles que esten en el encuadre.\n"
    "9. Si la foto no muestra equipos ni una instalacion, deci en una linea "
    "que no se ve lo que se pedia y nada mas. No describas el resto.\n"
    "10. CUARENTA PALABRAS COMO MAXIMO, sin saludos. Si no entra, sacá la "
    "descripcion de lo que no se pidio, nunca el veredicto.\n"
    "11. Terminá con una ultima linea, sola, que diga exactamente "
    "'ATENCION: si' o 'ATENCION: no'. Poné 'si' SOLO si viste algo que "
    "sugiere que el trabajo quedo mal --un cable suelto, un conector que "
    "parece no estar puesto, un equipo sin fijar, material deteriorado-- "
    "o si la foto no sirve como evidencia de lo que se pedia. Si lo unico "
    "que hiciste fue describir lo que hay, poné 'ATENCION: no'. Que algo "
    "este borroso o fuera de cuadro NO alcanza por si solo: decilo en el "
    "parrafo y poné 'si' unicamente si por eso la foto no sirve.\n"
    "12. Si --y SOLO si-- te dijeron que tenia que mostrar esta foto, agregá "
    "ANTES de esa linea otra sola que diga exactamente 'MUESTRA: si', "
    "'MUESTRA: no' o 'MUESTRA: no se sabe'. 'no' es para cuando la imagen "
    "muestra algo DISTINTO de lo que se pedia --pidieron el router y hay un "
    "televisor--. 'no se sabe' es para cuando no se puede determinar: esta "
    "borrosa, oscura, tapada, o es un primer plano del que no se deduce que "
    "equipo es. Si no te dijeron que tenia que mostrar, NO escribas esta "
    "linea.\n"
    "13. Agregá SIEMPRE, antes de las dos lineas anteriores, otra sola que "
    "diga exactamente 'CATALOGO: si' o 'CATALOGO: no'. Poné 'si' cuando la "
    "imagen no sea una foto tomada en el trabajo sino material de producto: "
    "el equipo solo, recortado o sobre un fondo blanco o liso, sin nada "
    "alrededor, como en la pagina de una tienda. Una foto tomada de otra "
    "pantalla NO es catalogo, y una captura tampoco: para esas poné 'no'. "
    "Ante la duda poné 'no'."
)


#: Como se le presenta al modelo el texto que acompana a la imagen. El de
#: WhatsApp es lo que escribio el cliente; el de campo es lo que la plantilla
#: de la empresa declara que esa foto tenia que mostrar. Decirle al proveedor
#: que lo segundo "lo escribio el cliente" es una afirmacion falsa sobre el
#: origen del dato, y ademas mueve el analisis: el modelo no trata igual una
#: frase del cliente que una instruccion de la oficina (revisor de PII,
#: 31/10/2026, H5). Por eso el rotulo lo elige quien llama, igual que la
#: instruccion.
PIE_DEL_CLIENTE = "El cliente escribio junto a la foto"
PIE_DE_LA_PLANTILLA = "Lo que esta foto tenia que mostrar, segun la empresa"


def mensaje_multimodal(contenido: bytes, pie: str = "",
                       instruccion: str = "",
                       rotulo_del_pie: str = "") -> list[dict]:
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
            "text": f"{rotulo_del_pie or PIE_DEL_CLIENTE}: {pie.strip()}"})
    partes.append({
        "type": "image_url",
        "image_url": {"url": f"data:{_mime_de(contenido)};base64,{datos}"}})
    #  La instruccion es un PARAMETRO con el default de siempre (31/10/2026).
    #  Antes era la constante del modulo, y para mirar una foto de evidencia
    #  de campo --donde se pregunta justo lo que las reglas 3 y 4 de
    #  INSTRUCCION prohiben-- la salida facil habria sido un segundo modulo
    #  que vuelva a hablarle al proveedor. Eso es la historia del reloj
    #  escrito dos veces (CLAUDE.md §6): hay UN solo sitio que manda imagenes,
    #  con sus seis garantias --timeout, tope, formato, redaccion, evento de
    #  costo e idempotencia-- y lo que cambia es que se le pide.
    return [{"role": "system", "content": instruccion or INSTRUCCION},
            {"role": "user", "content": partes}]


def analizar(contenido: bytes, modelo: str, pie: str = "",
             temperatura: float = 0.1, instruccion: str = "",
             rotulo_del_pie: str = "") -> Resultado:
    """
    Los bytes de una imagen -> que se ve, o el motivo de por que no se pudo.

    'modelo' es la referencia completa del tenant ('deepseek:deepseek-v4-flash'):
    sale de la config, no de una constante de este archivo, porque es un dato
    que varia por empresa (CLAUDE.md 3.3).

    'instruccion' vacia = la de WhatsApp. Para una foto de evidencia de campo
    se pasa INSTRUCCION_EVIDENCIA. Todo lo demas --los topes, el formato, el
    recorte y la redaccion-- corre igual para las dos.

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
            mensaje_multimodal(contenido, pie, instruccion, rotulo_del_pie),
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


def texto_para_el_agente(r: Resultado, pie: str = "",
                         proposito: str = "whatsapp_cliente") -> str:
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

    #  EL ROTULO DICE DE DONDE SALIO LA FOTO, y hasta el 02/11/2026 era
    #  la constante "[Foto que envio el cliente]". Con el asistente
    #  interno eso pasaba a ser falso: la adjunta un colaborador. El
    #  modelo no trata igual una foto del cliente que una de la oficina,
    #  asi que la etiqueta importa.
    lineas = [(PROPOSITOS.get(proposito) or {}).get(
        "rotulo", PROPOSITOS["whatsapp_cliente"]["rotulo"])]

    if (pie or "").strip():
        lineas.append("")
        lineas.append("[Texto que escribio junto con la imagen]")
        lineas.append(pie.strip())

    lineas.append("")
    lineas.append("[Analisis automatico de la foto, no verificado]")
    lineas.append(r.texto)

    return "\n".join(lineas)
