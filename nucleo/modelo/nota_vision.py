# -*- coding: utf-8 -*-
"""
================================================================================
 LA NOTA DE VISION  --  el analisis es contexto, no es la respuesta
================================================================================

POR QUE EXISTE
--------------
Cuando el cliente manda una foto, al modelo le llega el analisis entero: un
parrafo de 500 caracteres que enumera el equipo, las antenas, los LED, los
cables, los conectores y lo que no se pudo ver. Eso es exactamente lo que
tiene que llegarle -- con menos, razona peor.

Pero medido en produccion el 05/10/2026: el modelo lo COPIA al cliente. Le
devuelve varios parrafos describiendole su propio equipo, con las limitaciones
de la lectura incluidas, y termina con cuatro o cinco preguntas. Por WhatsApp
eso es una pared de texto que nadie lee, y el cliente escribio para que le
arreglen el internet, no para que le describan su router.

El modelo no hace nada raro: le dieron un texto largo y lo trata como
informacion que hay que transmitir. Nadie le dijo que era para el.

QUE HACE Y QUE NO
-----------------
Agrega una instruccion. NO quita ni recorta nada de lo que el modelo recibe
--seguiria razonando igual de bien sin esta nota-- y no toca el analisis, que
sigue entero en el historial y en la bandeja.

POR QUE EN EL MOTOR Y NO EN LA CONFIG DEL TENANT
-------------------------------------------------
El tono, el trato y el dialecto SON del tenant y ya viven en
'persona.instrucciones_adicionales'. Pero "lo que te paso una camara es
contexto tuyo, no un mensaje para reenviar" no es una preferencia de una
empresa: es como funciona este canal para cualquiera que use vision. Lo que
varia por empresa es configuracion; lo que lo interpreta es motor.

Por eso aca no hay ningun nombre de empresa, y la nota solo se inyecta cuando
el turno de verdad trae un analisis -- un mensaje de texto, una nota de voz o
una foto que no se pudo mirar no la ven nunca.

LO QUE ESTA NOTA NO PUEDE PROMETER
-----------------------------------
Es una instruccion, o sea GUIA, no garantia (PRD 7.4). Nada en el codigo
impide que el modelo conteste largo igual. Una prueba puede comprobar que la
nota se inyecta y que el analisis sigue completo; que la respuesta se acorte
se MIDE llamando al modelo, y varia entre corridas. Las dos cosas estan en
tests/test_nota_vision.py, separadas y rotuladas como lo que son.
================================================================================
"""

from __future__ import annotations

#: El rotulo que pone nucleo/canales/vision.py::texto_para_el_agente. Es la
#: unica senal de que este turno trae una foto mirada: se compara contra el
#: texto del turno y no contra una bandera aparte, para que no puedan quedar
#: desincronizadas.
ROTULO_ANALISIS = "[Analisis automatico de la foto, no verificado]"

#: La instruccion. Esta escrita alrededor de UNA idea --el analisis es para
#: vos, no para el cliente-- y despues dice que hacer, porque prohibir sin
#: decir que hacer en su lugar deja al modelo adivinando.
#:
#: Las reglas 4 y 5 son las que mas importan y son las menos obvias:
#:
#:   4. Decir que la foto no alcanza es UTIL y hay que decirlo -- pero en una
#:      linea. El problema nunca fue que lo dijera: fue el parrafo explicando
#:      por que.
#:   5. Un cliente que manda una foto quiere que le resuelvan algo. Cinco
#:      preguntas lo obligan a redactar un informe, y lo normal es que
#:      conteste una sola y se pierdan las otras cuatro.
NOTA = (
    "SOBRE LA FOTO QUE ACABAS DE RECIBIR.\n"
    "Lo que viene bajo '[Analisis automatico de la foto, no verificado]' es "
    "CONTEXTO PARA TI, no un mensaje para el cliente. El ya vio su foto: no "
    "necesita que se la describan.\n"
    "\n"
    "Al contestarle:\n"
    "1. No enumeres lo que aparece en la imagen (el equipo, los cables, los "
    "conectores, las antenas). Usalo para pensar, no para escribir.\n"
    "2. No copies frases del analisis ni lo repitas con otras palabras.\n"
    "3. Nunca menciones que hubo un analisis, ni hables de modelo, imagen "
    "procesada, sistema ni nada parecido. Para el cliente, simplemente "
    "miraste su foto.\n"
    "4. Si en la foto se ve algo que contesta su pregunta, decilo directo y "
    "en una linea. Si NO se alcanza a ver, decilo en una linea y pregunta lo "
    "que haga falta -- sin explicar por que no se ve.\n"
    "5. Una o dos preguntas, tres como maximo, y que sean las que de verdad "
    "sirven para avanzar. Prioriza siempre si el servicio esta funcionando "
    "ahora.\n"
    "6. Dos o tres parrafos CORTOS. Tiene que poder leerse de un vistazo en "
    "WhatsApp.\n"
    "7. No afirmes como un hecho algo que la foto no demuestra. Si parece una "
    "falla pero no esta confirmada, decilo como posibilidad, en pocas "
    "palabras."
)


def turno_con_foto(mensaje: str) -> bool:
    """Si este turno trae una foto que se pudo mirar."""
    return bool(mensaje) and ROTULO_ANALISIS in mensaje


def nota_para(mensaje: str) -> str:
    """
    La instruccion que corresponde a este turno, o cadena vacia.

    Vacia es lo normal: la enorme mayoria de los turnos son texto. Quien
    llama no agrega nada al historial cuando esto devuelve vacio, asi que un
    turno sin foto queda EXACTAMENTE como estaba antes de que esto existiera.
    """
    return NOTA if turno_con_foto(mensaje) else ""
