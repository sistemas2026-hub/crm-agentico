# -*- coding: utf-8 -*-
"""
================================================================================
 UN ENTORNO QUE NO SALE  --  20/10/2026
================================================================================

    SIN_EFECTOS_EXTERNOS=1

EL PROBLEMA QUE RESUELVE
------------------------
El usuario pidio un entorno local igual a produccion para probar ahi antes de
desplegar. Igual a produccion quiere decir con las credenciales reales: para
ver los estados de WispHub y las señales de SmartOLT hay que leerlos de
verdad. Y esas mismas credenciales ESCRIBEN.

Medido ese dia, todas las escrituras hacia afuera pasan por dos lugares:

  * el ejecutor de herramientas ('nucleo/herramientas/http.py'). Llegan ahi
    las que decide el modelo, las que aprueba una persona y las que pide el
    CRM por '/interno/herramienta/...' (cerrar un ticket en el proveedor,
    reasignar una instalacion, actualizar el serial de una ONU);
  * el canal de WhatsApp ('nucleo/canales/whatsapp.py').

El interruptor de autonomia NO alcanza para un entorno de pruebas, y no es un
defecto suyo: detiene lo que decide el modelo y deja pasar, a proposito, lo
que aprueba una persona. En un entorno de pruebas una persona aprobando un
pago de prueba sigue siendo un pago real.

LA REGLA
--------
Con la variable encendida, una herramienta que ESCRIBE solo puede llegar a un
servicio de la red local: un nombre sin punto ('backend', 'motor',
'localhost'). Un dominio o una IP es afuera, y no sale. Leer sigue saliendo:
es para lo que el entorno existe. WhatsApp no envia nada.

Se decide por el DESTINO y no por 'efecto_externo' porque las herramientas
que escriben en el propio CRM ('crear_caso_soporte', 'asignar_caso_crm')
no lo declaran y la frontera las cuenta como externas -- fallar cerrado es
lo correcto para la frontera, y aca dejaria sin escalamiento al entorno que
existe para probarlo.

FALLA CERRADO
-------------
Cualquier valor que no sea vacio, '0', 'false' o 'no' la ENCIENDE: un error de
tipeo en el entorno de pruebas no puede convertirse en un pago real. Y un
destino que no se puede resolver cuenta como afuera.

En produccion la variable no existe, y nada de esto cambia su conducta.

LA PRUEBA VIGILADA  --  26/11/2026
----------------------------------
    EFECTOS_EXTERNOS_PERMITIDOS=<herramienta>[,<herramienta>]

Para probar UNA escritura real con permiso explicito del usuario (la primera
autorizacion de una ONU, el primer alta de un cliente) sin apagar el entorno
entero: apagar SIN_EFECTOS_EXTERNOS abria todo lo demas --WhatsApp incluido--
mientras durara la prueba. Esta lista deja salir SOLO las herramientas que
nombra, por su nombre exacto; todo lo demas sigue sin salir, y WhatsApp no la
mira. Lo que sale por aca sigue pasando por la frontera entera. Vacia por
defecto, y se vacia al terminar la prueba.
================================================================================
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

VARIABLE = "SIN_EFECTOS_EXTERNOS"
PERMITIDAS = "EFECTOS_EXTERNOS_PERMITIDOS"
_APAGADA = ("", "0", "false", "no")


def activo() -> bool:
    """Si este proceso corre en un entorno que no produce efectos afuera."""
    return (os.environ.get(VARIABLE) or "").strip().lower() not in _APAGADA


def permitida(nombre: str | None) -> bool:
    """Si 'nombre' esta en la lista de la prueba vigilada. Por nombre EXACTO:
    ni prefijos ni comodines, para que una herramienta parecida no salga."""
    lista = {x.strip() for x in (os.environ.get(PERMITIDAS) or "").split(",") if x.strip()}
    return bool(nombre) and nombre in lista


def es_de_la_red_local(url: str | None) -> bool:
    """
    Si 'url' apunta a un servicio de la red local: un host sin punto.

    Una IP tiene puntos (o ':' si es v6) y cuenta como afuera; un host vacio,
    tambien.
    """
    host = urlparse(url or "").hostname or ""
    return bool(host) and "." not in host and ":" not in host


def motivo(que: str) -> str:
    return (f"{que} no salio: este entorno no produce efectos externos "
            f"({VARIABLE}). Solo escribe dentro de la red local.")
