# -*- coding: utf-8 -*-
"""
===============================================================================
 TAPAR LO PERSONAL ANTES DE QUE EL TEXTO SALGA DEL SISTEMA
===============================================================================

POR QUE EXISTE
--------------
El Supervisor diagnostica un ticket leyendo la descripcion que escribio quien
tomo el reclamo. Ese texto es LIBRE, y esta medido lo que trae: de 300 tickets
reales, 136 tenian un numero de documento escrito a mano en la descripcion.

La lista blanca de campos no alcanza contra esto. La lista blanca controla QUE
CAMPOS pasan; no controla QUE CONTIENE cada campo. 'description' es un campo
legitimo que hace falta para diagnosticar, y adentro viene una cedula.

QUE SE TAPA Y QUE NO
--------------------
Se tapa lo que identifica a una persona: documento, telefono, correo. NO se
toca nada de lo que sostiene el diagnostico -- "no tiene internet desde ayer",
"ya reinicio el router", "se le va a cada rato". El diagnostico sale igual de
bueno; lo que no sale es el dato.

LO QUE ESTO NO ES: no es anonimizar el caso. El ticket completo se sigue
viendo en Dexter, en WispHub y en la app del tecnico, con nombre y cedula. Lo
unico que cambia es lo que viaja al modelo.

SE TAPA DE MAS ANTES QUE DE MENOS
---------------------------------
Un numero de diez digitos que resulte ser un codigo de equipo y no un telefono
se tapa igual. Perder ese dato cuesta un diagnostico un poco mas pobre;
dejarlo pasar cuesta un dato personal en un tercero. El cambio no es simetrico
y el criterio tampoco.

LO QUE NO ALCANZA A TAPAR, dicho para que nadie lo suponga resuelto: un nombre
propio escrito en el medio de una frase. No hay patron que lo distinga de
cualquier otra palabra. Por eso el nombre del cliente NO se manda aparte --ni
en el prompt ni en el contexto-- y el texto se manda siempre tapado, pero un
nombre dentro de la frase puede quedar. Es un limite conocido, no una promesa.
"""
from __future__ import annotations

import re

#:  Lo que se pone en lugar de cada hallazgo. Visible a proposito: quien lea
#:  el diagnostico despues tiene que poder ver que ahi habia algo tapado, en
#:  vez de encontrarse una frase que no cierra.
TAPADO = "███"

#  CADA PATRON CON SU MOTIVO. El orden importa: el correo va primero porque
#  contiene puntos y numeros que los otros patrones romperian en pedazos.
_PATRONES = (
    #  Correo. Antes que todo lo demas.
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    #  Celular colombiano: diez digitos que empiezan en 3, con o sin
    #  separadores. Es el formato que la skill de WispHub midio como el real
    #  (98,7% de cobertura con ese patron).
    re.compile(r"(?<!\d)3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    #  Cedula colombiana: de 6 a 11 digitos sueltos, con o sin puntos. Es el
    #  patron mas ancho y por eso va ultimo -- se queda con lo que los
    #  anteriores no se llevaron.
    re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{3}){1,3}(?![\w.])"),
    re.compile(r"(?<!\d)\d{6,11}(?!\d)"),
)


def tapar(texto: str) -> str:
    """
    El mismo texto, sin lo que identifica a una persona.

    Devuelve cadena vacia para una entrada vacia o no textual: quien llama
    decide que hacer con eso, y 'None' convertido a 'None' seria un valor que
    recorre medio sistema sin que nadie lo mire.
    """
    if not isinstance(texto, str) or not texto.strip():
        return ""
    limpio = texto
    for patron in _PATRONES:
        limpio = patron.sub(TAPADO, limpio)
    return limpio


def cuantos_se_taparon(texto: str) -> int:
    """
    Cuantos hallazgos se taparon. Para poder MEDIR que el tapado funciona en
    produccion sin leer un solo texto real.

    Un cero sostenido en miles de tickets no significaria "no hay datos
    personales": significaria que los patrones dejaron de coincidir, y es la
    clase de falla que no da error.
    """
    return max(0, tapar(texto).count(TAPADO))
