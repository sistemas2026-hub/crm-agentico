# -*- coding: utf-8 -*-
"""
================================================================================
 COMO QUEDAN ESCRITOS LOS DATOS DEL CLIENTE EN EL CONTRATO  --  25/11/2026
================================================================================
Decision del usuario, planeando el formato de instalacion: *«los datos del
cliente ya tienen que llegar precargados como vienen escritos en el ticket.
Todos los datos en mayusculas. La cedula solamente los numeros sin puntos y sin
el CC. El numero de telefono igual, solamente los 10 digitos [...]. Igual el
correo minuscula, la direccion igual mayuscula, todo. La direccion mas el barrio
pegado, el barrio abajo solo.»*

El motivo es el mismo que trajo el contrato a la app: el tecnico no deberia
teclear. Si el dato llega con la forma que la empresa usa, lo unico que hace es
mirarlo contra la cedula y confirmar.

QUE ES DE CADA EMPRESA Y QUE NO  (CLAUDE.md 3.3)
------------------------------------------------
* MAYUSCULAS, BARRIO PEGADO A LA DIRECCION y CUANTOS DIGITOS LLEVA EL TELEFONO
  son costumbre de una empresa y de un pais. Viven en
  `ConfiguracionDeContrato` y se cambian desde Programacion. Sin configurar,
  ninguna de las tres se aplica.
* Que un documento sean solo sus numeros y que un correo vaya en minusculas no
  varia por empresa: se hace siempre.

SE APLICA DOS VECES, Y TIENE QUE DAR LO MISMO
---------------------------------------------
Una al armar el borrador y otra al firmar, sobre lo que el telefono devuelve
--que es el borrador, ya con formato, mas lo que el tecnico corrigio--. Por eso
todo aca es IDEMPOTENTE: pasar dos veces no pega el barrio dos veces ni recorta
dos veces el telefono. Hay una prueba por cada funcion que lo afirma.

Este modulo no toca la base ni la red: recibe textos y devuelve textos.
================================================================================
"""
from __future__ import annotations

import re
import unicodedata

#: Las costumbres de una empresa que no cargo ninguna.
SIN_COSTUMBRES = {"datos_en_mayusculas": False, "barrio_en_la_direccion": False,
                  "digitos_del_telefono": 0, "abreviaturas_de_direccion": []}

#: Un indicativo de pais tiene de 1 a 3 digitos. Lo que sobra por encima de eso
#: no es un indicativo: son dos numeros escritos en el mismo campo.
_LARGO_MAXIMO_DE_INDICATIVO = 3

#: Como se separan dos telefonos escritos en un solo campo.
_ENTRE_DOS_TELEFONOS = re.compile(r"[/,;]|\s+[yo]\s+", re.I)


def _espacios(texto) -> str:
    """Sin espacios de mas: ni a los lados ni dobles en el medio."""
    return " ".join(str(texto or "").split())


def _llano(texto) -> str:
    """Para COMPARAR, nunca para guardar: sin tildes, sin mayusculas, sin signos."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.lower()).split())


def _es_pasaporte(tipo) -> bool:
    t = _llano(tipo)
    return t in ("pa", "pp", "ppt", "pep") or "pasaporte" in t


def documento(valor, tipo="") -> str:
    """El numero de documento, solo.

    «CC 1.043.000.000» -> «1043000000». El tipo ya viaja en su propio campo, y
    los puntos son como lo escribe una persona, no parte del numero.

    Un pasaporte SI lleva letras: se le quitan los signos y nada mas. Borrarle
    las letras lo convertiria en el documento de otra persona.
    """
    crudo = _espacios(valor)
    if _es_pasaporte(tipo):
        return re.sub(r"[^0-9A-Za-z]", "", crudo).upper()
    return re.sub(r"\D", "", crudo)


def telefono(valor, digitos=0) -> str:
    """El telefono, solo sus numeros; y sin indicativo si la empresa dice cuantos son.

    `digitos` es cuantos lleva un numero en el pais de la empresa (10 en
    Colombia). Con 0 no se recorta nada: solo se quitan los signos.

    DOS NUMEROS EN EL MISMO CAMPO. La gente escribe «300 123 4567 / 301 ...».
    Se toma el PRIMERO: pegar los dos y quedarse con los ultimos digitos
    devolveria el segundo numero sin que nadie lo pidiera, o un numero que no
    es de nadie.
    """
    crudo = str(valor or "")
    primero = next((p for p in _ENTRE_DOS_TELEFONOS.split(crudo)
                    if len(re.sub(r"\D", "", p)) >= 7), crudo)
    solo = re.sub(r"\D", "", primero)
    try:
        digitos = int(digitos or 0)
    except (TypeError, ValueError):
        digitos = 0
    if digitos <= 0 or len(solo) <= digitos:
        return solo
    if len(solo) - digitos <= _LARGO_MAXIMO_DE_INDICATIVO:
        return solo[-digitos:]          # lo que sobra adelante es el indicativo
    return solo[:digitos]               # son dos numeros pegados: el primero


def correo(valor) -> str:
    """Un correo no distingue mayusculas ni lleva espacios."""
    return "".join(str(valor or "").split()).lower()


def _sin_barrio_al_final(direccion: str, barrio: str) -> str:
    """La direccion sin ESE barrio pegado al final, si lo tenia.

    Compara sin tildes ni signos («Villa Estadio,» es «VILLA ESTADIO»), pero
    devuelve la direccion con su escritura intacta.
    """
    buscado = _llano(barrio)
    if not buscado:
        return direccion
    palabras = direccion.split()
    #  Desde 1 y no desde 0: si TODA la direccion es el barrio, no hay nada
    #  que separar, y dejarla vacia perderia lo unico que habia.
    for i in range(1, len(palabras)):
        if _llano(" ".join(palabras[i:])) == buscado:
            return " ".join(palabras[:i]).rstrip(" ,;.-")
    return direccion


def direccion_con_barrio(direccion, barrio, barrio_anterior="") -> str:
    """La direccion con el barrio pegado al final, UNA sola vez.

    `barrio_anterior` es el que traia el borrador. Si el tecnico corrigio el
    barrio, la direccion que devuelve el telefono todavia termina en el viejo:
    sin esto quedaria «CRA 3 # 5-20 VILLA DEL SOL LAS NIEVES».
    """
    d, b = _espacios(direccion), _espacios(barrio)
    for pegado in (_espacios(barrio_anterior), b):
        d = _sin_barrio_al_final(d, pegado)
    if not b:
        return d
    return b if _llano(d) == _llano(b) else f"{d} {b}".strip()


def abreviar(direccion, reglas) -> str:
    """La direccion con cada palabra escrita como la escribe la empresa.

    El usuario, 25/11/2026: *«si esta escrita cll debe ser calle y si esta kra
    es cra, y asi corrija como se escribe bien la direccion»*. Las reglas son
    de la empresa (`ConfiguracionDeContrato.abreviaturas_de_direccion`):

        [{"como_lo_escriben": ["CLL", "CL"], "como_queda": "CALLE"}, ...]

    SOLO PALABRAS ENTERAS. «CL» cambia en «CL 48» y no en «CLARA» ni en «3CL».
    Se compara sin mayusculas, sin tildes y sin el punto final («Cra.» es
    «CRA»). Lo que no esta en las reglas queda como estaba. Idempotente:
    pasar dos veces da lo mismo, aunque la forma final este entre las que se
    escriben.
    """
    texto = _espacios(direccion)
    if not texto or not reglas:
        return texto
    mapa = {}
    for regla in reglas:
        if not isinstance(regla, dict):
            continue
        queda = _espacios(regla.get("como_queda"))
        if not queda:
            continue
        for variante in regla.get("como_lo_escriben") or []:
            clave = _llano(variante).replace(" ", "")
            if clave:
                mapa[clave] = queda
    if not mapa:
        return texto
    salida = []
    for palabra in texto.split(" "):
        clave = _llano(palabra.rstrip(".")).replace(" ", "")
        salida.append(mapa.get(clave, palabra))
    return " ".join(salida)


def direccion_ya_trae_el_barrio(direccion, barrio) -> bool:
    """Si esa direccion ya termina en ese barrio (para no imprimirlo dos veces)."""
    d, b = _llano(direccion), _llano(barrio)
    return bool(b) and (d == b or d.endswith(" " + b))


def cliente_con_formato(cliente: dict, costumbres: dict | None = None,
                        barrio_anterior: str = "") -> dict:
    """Los datos del cliente como la empresa los escribe. Idempotente.

    Devuelve un diccionario NUEVO con las mismas claves: no cambia el que recibe.
    """
    costumbres = costumbres or SIN_COSTUMBRES
    mayusculas = bool(costumbres.get("datos_en_mayusculas"))

    def _texto(valor) -> str:
        t = _espacios(valor)
        return t.upper() if mayusculas else t

    c = dict(cliente)
    c["nombre"] = _texto(c.get("nombre"))
    c["apellido"] = _texto(c.get("apellido"))
    c["tipo_documento"] = _texto(c.get("tipo_documento"))
    c["numero_documento"] = documento(c.get("numero_documento"), c["tipo_documento"])
    c["telefono"] = telefono(c.get("telefono"), costumbres.get("digitos_del_telefono"))
    c["correo"] = correo(c.get("correo"))
    barrio = _texto(c.get("barrio"))
    direccion = _texto(c.get("direccion"))
    reglas = costumbres.get("abreviaturas_de_direccion") or []
    if costumbres.get("barrio_en_la_direccion"):
        #  LAS ABREVIATURAS SE APLICAN A LA CALLE, NO AL BARRIO: primero se
        #  saca el barrio que traia pegado, se abrevia lo que queda y recien
        #  ahi se le vuelve a pegar. Un barrio «La Carrera» no es una carrera.
        calle = direccion
        for pegado in (_texto(barrio_anterior), barrio):
            calle = _sin_barrio_al_final(calle, pegado)
        direccion = direccion_con_barrio(_texto(abreviar(calle, reglas)), barrio)
    else:
        direccion = _texto(abreviar(direccion, reglas))
    c["direccion"], c["barrio"] = direccion, barrio
    return c
