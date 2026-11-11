"""
Los avisos que el MOTOR escribe en nombre del cliente cuando lo que mando no es
texto (11/11/2026): una ubicacion, una tarjeta de contacto, una reaccion.

Viven aca, en un modulo sin dependencias, porque dos lados tienen que decir
exactamente lo mismo: el canal los ARMA (whatsapp.py, api.py) y el motor los
RECONOCE (modelo/motor.py) para no tratarlos como una pregunta.

No son preguntas, y llevan datos personales con forma fija -- coordenadas,
el telefono de un tercero --: buscarlos en la documentacion manda esos datos
al proveedor de embeddings para nada, y registrarlos como "pregunta sin
respuesta" los guarda en una tabla que promete no tener datos de cliente
(nucleo/recuperacion/busqueda.py::registrar_sin_resultados). Hallazgo del
revisor de PII sobre e542c651.
"""

import re

UBICACION = "[El cliente compartio su ubicacion"
CONTACTO = "[El cliente compartio un contacto"
REACCION = "[El cliente reacciono con"

AVISOS_CON_DATOS = (UBICACION, CONTACTO, REACCION)


def es_aviso_con_datos(texto: str | None) -> bool:
    """True si el texto lo armo el canal a partir de algo que no era texto."""
    return (texto or "").lstrip().startswith(AVISOS_CON_DATOS)


# Una tira de digitos con los separadores con que se escribe un telefono. Siete
# digitos como minimo: un nombre con un numero («Local 3») no es un telefono.
_TELEFONO = re.compile(r"\+?\d[\d\s().-]{5,}\d")
DIGITOS_A_LA_VISTA = 4


def _recortar(m: re.Match) -> str:
    digitos = re.sub(r"\D", "", m.group(0))
    if len(digitos) < 7:
        return m.group(0)
    return f"numero terminado en {digitos[-DIGITOS_A_LA_VISTA:]}"


def sin_telefonos_de_terceros(texto: str) -> str:
    """
    EL TELEFONO DE UN TERCERO NO SALE AL PROVEEDOR DEL MODELO  --  11/11/2026

    La autorizacion de tratamiento (PRD RNF-01) la firma el cliente y cubre SUS
    datos. La persona de una tarjeta de contacto no firmo nada, y que el cliente
    la comparta no es su autorizacion. Decision del dueño: el modelo ve el
    nombre y los ultimos 4 digitos -- alcanza para responder «recibi el contacto
    de Maria, ¿la contactamos a ella?» --, y el numero entero queda guardado
    para el equipo, que lo ve en la Bandeja.

    Recorta desde el aviso hasta el fin de esa linea, y no solo hasta el «]»:
    un nombre con corchetes no puede dejar un numero afuera. El aviso aparece
    tambien DENTRO de otros textos (el historial, un resumen, la cita de una
    reaccion), y por eso se busca en todo el texto y no solo al principio.
    """
    if not texto or CONTACTO not in texto:
        return texto
    partes = texto.split(CONTACTO)
    salida = [partes[0]]
    for resto in partes[1:]:
        linea, salto, despues = resto.partition("\n")
        salida.append(_TELEFONO.sub(_recortar, linea) + salto + despues)
    return CONTACTO.join(salida)
