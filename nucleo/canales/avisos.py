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

UBICACION = "[El cliente compartio su ubicacion"
CONTACTO = "[El cliente compartio un contacto"
REACCION = "[El cliente reacciono con"

AVISOS_CON_DATOS = (UBICACION, CONTACTO, REACCION)


def es_aviso_con_datos(texto: str | None) -> bool:
    """True si el texto lo armo el canal a partir de algo que no era texto."""
    return (texto or "").lstrip().startswith(AVISOS_CON_DATOS)
