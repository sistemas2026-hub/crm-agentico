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

#  TRES FORMAS MAS, MEDIDAS EL 10/11/2026 -- y por que se agregan ahora.
#
#  La cabecera de este modulo decia: «el dia que aparezca otra forma, el camino
#  es MEDIRLA y agregarla aca con su fecha, no aflojar el parseo por si acaso».
#  Aparecieron. Sobre los 4.644 clientes que sirve la API:
#
#      2.982  el campo vacio
#      1.071  los leia esta forma de arriba
#        591  TENIAN EL DATO Y NO SE LEIAN  <-- la pantalla decia «sin
#                                               ubicacion» teniendo la casa
#
#  Y las 591 se reparten asi:
#
#        435  DD°DD'DD.D"a DD°DD'DD.D"a   grados-minutos-segundos
#        134  DD.DDDD -DD.DDDD            separados por ESPACIO, no por coma
#          4  DD.DDDDDD°a, DD.DDDDDD°a    decimal con el hemisferio en letra
#          4  aa. DDa # Da-DD             una direccion de calle
#          4  --DD.DDDD                   doble signo
#
#  Se agregan las tres primeras: 573 clientes que pasan a tener ubicacion sin
#  que nadie salga a buscarla. Las dos ultimas siguen saliendo ausentes, y es
#  la verdad: de una direccion de calle no se deduce un punto --eso ya esta
#  decidido en `dia_publicado.py`, no se geocodifica-- y `--74` no es ni -74 ni
#  74, es un dato que alguien escribio mal.

#: Dos decimales con signo propio, separados SOLO por espacios.
#:
#: EL `-?` ADMITE UN SIGNO, y `--74` no entra por aca. Pero esa NO es la unica
#: red, y conviene saberlo: una pasada de mutacion (10/11/2026) aflojo este `-?`
#: a `-*` y las 54 pruebas siguieron en verde, porque con el patron abierto
#: `--74.8186` matchea y lo que lo ataja es el `float()` de `_partir`. El
#: `except ValueError` de ahi abajo no es el codigo inalcanzable que parece: es
#: la red que trabaja el dia que alguien afloje un patron.
_PAR_ESPACIO = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s+(-?\d{1,3}(?:\.\d+)?)\s*$")

#: Grados-minutos-segundos con el hemisferio en letra, la forma de Google Maps.
#: Los segundos pueden traer decimales; las comillas de segundo son opcionales
#: porque entre los casos medidos hay de las dos maneras.
_DMS = re.compile(
    r"^\s*(\d{1,3})\s*°\s*(\d{1,2})\s*\'\s*(\d{1,2}(?:\.\d+)?)\s*\"?\s*"
    r"([NSEWnsew])\s*,?\s+"
    r"(\d{1,3})\s*°\s*(\d{1,2})\s*\'\s*(\d{1,2}(?:\.\d+)?)\s*\"?\s*"
    r"([NSEWnsew])\s*$")

#: Decimal con el grado y el hemisferio escritos. Los numeros vienen SIN signo
#: --el signo lo pone la letra-- asi que un signo explicito aca es una
#: contradiccion, y mas abajo sale ausente.
_GRADO_LETRA = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([NSEWnsew])\s*,?\s*"
    r"(-?\d{1,3}(?:\.\d+)?)\s*°?\s*([NSEWnsew])\s*$")

#: Que eje y que signo pone cada hemisferio.
_HEMISFERIOS = {"N": ("lat", 1.0), "S": ("lat", -1.0),
                "E": ("lng", 1.0), "W": ("lng", -1.0)}


def _por_hemisferio(v1, h1, v2, h2):
    """Asigna cada componente a su eje POR LA LETRA, no por el orden.

    Entre los casos medidos la latitud viene primero, pero usar la letra es
    estrictamente mejor y no es adivinar: el dato lo trae escrito. Y deja
    cerrada la puerta de dos latitudes juntas, que no son un punto.
    """
    a = _HEMISFERIOS.get(h1.upper())
    b = _HEMISFERIOS.get(h2.upper())
    if a is None or b is None or a[0] == b[0]:
        return (None, None)
    por_eje = {a[0]: v1 * a[1], b[0]: v2 * b[1]}
    return (por_eje["lat"], por_eje["lng"])


def _dms(grados, minutos, segundos):
    """Grados-minutos-segundos a decimal, o None si los tramos son imposibles.

    60 minutos son un grado: pasar de ahi es un dato roto. Normalizarlo por
    las nuestras moveria la casa sin que nadie se enterara.
    """
    m, s = float(minutos), float(segundos)
    if m >= 60.0 or s >= 60.0:
        return None
    return float(grados) + m / 60.0 + s / 3600.0

#: Los limites del planeta. No los de Colombia: esto es multi-empresa y el
#: proximo ISP puede estar en otro pais. Lo que se descarta aca no es «raro
#: para Rapilink», es IMPOSIBLE para cualquiera.
LAT_MAX = 90.0
LNG_MAX = 180.0


def _partir(texto: str) -> tuple[float | None, float | None]:
    """El par crudo de cada forma conocida, SIN validar planeta ni cero.

    Esas dos validaciones viven en `leer` y se aplican igual por donde se haya
    entrado: una forma nueva no puede traer su propia puerta de atras.
    """
    casa = _PAR.match(texto) or _PAR_ESPACIO.match(texto)
    if casa is not None:
        try:
            return (float(casa.group(1)), float(casa.group(2)))
        except ValueError:
            #  SIN `pragma: no cover`, a proposito (10/11/2026). Lo tenia, y
            #  era falso: con el patron de arriba nada que matchee puede fallar
            #  en `float()`, pero este `except` es lo que atajo `--74.8186`
            #  cuando una mutacion aflojo el `-?`. Marcarlo como inalcanzable
            #  invitaba a borrarlo, y es la segunda red del doble signo.
            return (None, None)

    casa = _DMS.match(texto)
    if casa is not None:
        g = casa.groups()
        uno, dos = _dms(g[0], g[1], g[2]), _dms(g[4], g[5], g[6])
        if uno is None or dos is None:
            return (None, None)
        return _por_hemisferio(uno, g[3], dos, g[7])

    casa = _GRADO_LETRA.match(texto)
    if casa is not None:
        g = casa.groups()
        #  El signo lo pone la letra. Un menos escrito ADEMAS de la letra dice
        #  dos cosas opuestas, y no se elige una.
        if g[0].startswith("-") or g[2].startswith("-"):
            return (None, None)
        try:
            return _por_hemisferio(float(g[0]), g[1], float(g[2]), g[3])
        except ValueError:                               # pragma: no cover
            return (None, None)

    return (None, None)


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

    lat, lng = _partir(texto)
    if lat is None or lng is None:
        #  SE REGISTRA LA FORMA, NUNCA EL VALOR: un log con la coordenada seria
        #  el domicilio de una persona en un archivo de texto. La silueta
        #  alcanza para darse cuenta de que apareció un formato nuevo.
        logger.info("coordenadas con forma no reconocida",
                    extra={"forma": _silueta(texto)})
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
