# -*- coding: utf-8 -*-
"""
El punto donde vive el cliente, sacado del texto que guarda el ISP.

POR QUE EXISTE ESTE MODULO
--------------------------
El proveedor guarda UN campo de texto; la orden de trabajo guarda DOS numeros
(`gps_lat`, `gps_lng`, FloatField). Alguien tiene que partir ese texto, y
partirlo mal NO DA ERROR: da una casa equivocada, con un pin que el supervisor
lee como un hecho. Por eso vive aparte, con su propia prueba, en vez de ser
tres lineas dentro de `despacho.py`.

LO QUE SE MIDIO, Y CUANDO (05/11/2026)
--------------------------------------
Contra la API real, con `cli/medir_coordenadas.py rapilink 5832`:

    forma      'DD.DDDDDD,-DD.DDDDDD'
    separador  coma, SIN espacio
    decimal    punto
    decimales  6
    orden      lat,lng  -- primer componente 10.9108 (positivo, Soledad),
                           segundo -74.8186 (negativo). El SIGNO lo prueba:
                           la longitud es la negativa en esta parte del mundo.

No se dedujo de la documentacion, y no se podia: el spec declara
`coordenadas: {type: string}` sin `format`, sin `example` y sin `pattern`, y
su unico ejemplo es el literal "String". La doc confirma que no documenta el
formato (ver la skill `wisphub-api`).

FAIL-CLOSED, Y ES LA REGLA ENTERA DE ESTE ARCHIVO
--------------------------------------------------
Se midio UNA forma, de UN cliente. Puede haber otras --con espacio, con
parentesis, con un enlace pegado, con coma decimal-- y este modulo NO intenta
adivinarlas: lo que no reconoce devuelve `(None, None)`, la orden queda sin
coordenadas y la pantalla dice «sin ubicacion». Esa frase es verdad; un punto
aproximado seria mentira, y se leeria como un hecho sobre donde esta la casa
de alguien. Es la misma decision que ya esta escrita en `dia_publicado.py`:
no se geocodifica la direccion ni se usa el centro del barrio.

El dia que aparezca otra forma, el camino es MEDIRLA y agregarla acá con su
fecha, no aflojar el parseo "por si acaso".
"""
import logging
import re

logger = logging.getLogger(__name__)

#: Lo que el proveedor devuelve cuando el cliente NO tiene el dato cargado, o
#: lo que quedo de un formulario a medio llenar.
#:
#: EL CRUCE DEL ECUADOR CON EL MERIDIANO CERO NO ESTA ACA, Y SE MIDIO POR QUE
#: (05/11/2026). Estuvo: la lista tenia "0,0" y "0.0,0.0". Una mutacion que
#: los sacaba SOBREVIVIO -- las pruebas seguian en verde-- porque la
#: comparacion numerica de mas abajo ya los atrapa, y ademas atrapa lo que una
#: lista de textos nunca podria: "0.000000,0.000000", "00,00", "0.0, 0".
#: Dos redes para lo mismo, una estrictamente mas debil. Quedo la fuerte.
AUSENTES = ("", "none", "null", "nan", "-", "n/a", "s/n", "0")

#: Dos numeros con signo opcional, separados por coma. Se toleran espacios
#: alrededor aunque lo medido no los traiga: un espacio de mas no cambia el
#: significado de nada, y es el unico ablande que este modulo se permite.
_PAR = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

#: Los limites del planeta. No los de Colombia: esto es multi-empresa y el
#: proximo ISP puede estar en otro pais. Lo que se descarta aca no es «raro
#: para Rapilink», es IMPOSIBLE para cualquiera.
LAT_MAX = 90.0
LNG_MAX = 180.0


def leer(crudo) -> tuple[float | None, float | None]:
    """El par (latitud, longitud), o (None, None) si no se puede afirmar.

    NUNCA levanta y NUNCA aproxima. Un caso que no entra en lo medido sale
    como ausente, que es lo que de verdad pasa: no se sabe donde es.

    >>> leer("10.910800,-74.818600")
    (10.9108, -74.8186)
    >>> leer("0,0")
    (None, None)
    >>> leer("")
    (None, None)
    """
    if crudo is None:
        return (None, None)
    #  Un numero suelto, un dict, una lista: no es lo medido. No se interpreta.
    if not isinstance(crudo, str):
        return (None, None)

    texto = crudo.strip()
    if texto.lower().replace(" ", "") in tuple(
            a.replace(" ", "") for a in AUSENTES):
        return (None, None)

    casa = _PAR.match(texto)
    if casa is None:
        #  SE REGISTRA LA FORMA, NUNCA EL VALOR: un log con la coordenada seria
        #  el domicilio de una persona en un archivo de texto. La silueta
        #  alcanza para darse cuenta de que apareció un formato nuevo.
        logger.info("coordenadas con forma no reconocida",
                    extra={"forma": _silueta(texto)})
        return (None, None)

    try:
        lat, lng = float(casa.group(1)), float(casa.group(2))
    except ValueError:                                   # pragma: no cover
        return (None, None)

    if abs(lat) > LAT_MAX or abs(lng) > LNG_MAX:
        logger.info("coordenadas fuera del planeta",
                    extra={"forma": _silueta(texto)})
        return (None, None)

    #  EL CERO EXACTO, OTRA VEZ, ahora despues de parsear: `"0.000000,0.000000"`
    #  no esta en AUSENTES --tiene otra cantidad de decimales-- y es el mismo
    #  punto del Atlantico. Se compara el NUMERO, que es lo que no se puede
    #  escribir de mil formas.
    if lat == 0.0 and lng == 0.0:
        return (None, None)

    return (lat, lng)


def _silueta(texto: str) -> str:
    """La forma, sin el dato. Igual criterio que `cli/medir_coordenadas.py`."""
    return re.sub(r"[0-9A-Za-z]",
                  lambda m: "D" if m.group().isdigit() else "a", texto)[:40]
