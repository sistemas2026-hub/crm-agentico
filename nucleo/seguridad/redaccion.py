# -*- coding: utf-8 -*-
"""
================================================================================
 REDACCION DE TEXTO LIBRE  --  lo que la lista blanca no puede filtrar
================================================================================

Por que existe
--------------
La lista blanca (listas_blancas.py) controla que CAMPOS pasan, no que
CONTIENE cada campo. Un campo de texto libre puede traer embebido cualquier
dato, y ahi la lista blanca no ve nada -- llega tal cual lo escribio el
operador.

Caso real documentado en PRD.md (7.4, "Limite conocido: los campos de texto
libre"): la 'descripcion' de un ticket de instalacion traia nombre completo,
telefono, email, direccion, coordenadas GPS, numero de documento, plan
contratado con precio y un enlace publico al PDF de la solicitud -- todo en
un solo string de 419 caracteres. Se decidio MANTENER el campo (Soporte no
puede trabajar sin el) y dejar la redaccion por patron para mas adelante.
Esto es esa parte.

Que se redacta y que se conserva
---------------------------------
Solo los patrones de PII identificable: cedulas/telefonos, emails, URLs y
coordenadas GPS. El resto del texto -- que fallo, que dijo el cliente sobre
el problema -- queda intacto: es justamente lo que el colaborador necesita
para atender el ticket. Redactar el campo entero lo volveria inutil; el
objetivo es sacar la PII, no el contenido operativo.

Ante la duda se redacta (mismo criterio fail-closed que el resto del
proyecto): un patron que coincide con un numero de referencia legitimo y no
con una cedula es un falso positivo tolerable -- lo contrario, dejar pasar
una cedula real, no lo es.
================================================================================
"""

from __future__ import annotations

import re

# Mismo patron de telefono colombiano que Autenticacion.patron_extraccion
# (nucleo/config/schema.py), mas generico para cedulas: 8 a 11 digitos
# seguidos, sin que haya otro digito pegado antes o despues (para no partir
# un numero mas largo, como un telefono internacional o un ID de ticket con
# mas cifras).
_CEDULA_O_TELEFONO = re.compile(r"(?<!\d)\d{8,11}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_URL = re.compile(r"https?://\S+")
# 'lat, lon' con al menos 4 decimales -- el formato real visto en produccion
# (PRD 7.4). Con menos decimales el rango es demasiado ancho y aumenta el
# riesgo de tapar un numero que no es una coordenada.
_COORDENADAS = re.compile(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}")

_PATRONES = (
    (_COORDENADAS, "[coordenadas ocultas]"),  # antes que cedula: si no, los
                                               # digitos de la coordenada
                                               # matchean como cedula primero
    (_URL, "[enlace oculto]"),
    (_EMAIL, "[email oculto]"),
    (_CEDULA_O_TELEFONO, "[numero de identificacion oculto]"),
)


def redactar(texto: str) -> str:
    """Aplica todos los patrones, en orden. Texto vacio o None pasa igual."""
    if not texto:
        return texto
    resultado = texto
    for patron, reemplazo in _PATRONES:
        resultado = patron.sub(reemplazo, resultado)
    return resultado


def redactar_campos(datos, campos: set[str] | list[str]):
    """
    Aplica redactar() a los campos nombrados, en cualquiera de las formas que
    ya maneja listas_blancas.py: dict suelto, o {"total","resultados":[...]}
    ya normalizado (se aplica a cada fila). No conoce Herramienta ni Rol --
    solo nombres de campo, para poder llamarse justo despues de
    filtrar_campos() sin acoplarse a su firma.
    """
    campos = set(campos)
    if not campos or not datos:
        return datos

    def _en_un_dict(d: dict) -> dict:
        return {k: (redactar(v) if k in campos and isinstance(v, str) else v)
               for k, v in d.items()}

    if isinstance(datos, dict) and isinstance(datos.get("resultados"), list):
        datos = dict(datos)
        datos["resultados"] = [_en_un_dict(f) if isinstance(f, dict) else f
                               for f in datos["resultados"]]
        return datos
    if isinstance(datos, dict):
        return _en_un_dict(datos)
    return datos
