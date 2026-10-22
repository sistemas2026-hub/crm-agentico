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

Medido ese dia, todas las escrituras del MOTOR hacia afuera pasan por dos
lugares:

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

LO QUE ESTO NO CUBRE (auditor de frontera, 20/10/2026)
-------------------------------------------------------
El backend Django tiene sus propias salidas: correo (EMAIL_BACKEND), avisos
por webhook de la empresa (campo/services/avisos.py) y push a los telefonos
(FCM). No pasan por el motor. El entorno local las cierra por su lado: correo
en consola y FCM vacio en docker-compose.local.yml, y los canales de avisos
apagados en la copia de la base.

En produccion la variable no existe, y nada de esto cambia su conducta.
================================================================================
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

VARIABLE = "SIN_EFECTOS_EXTERNOS"
_APAGADA = ("", "0", "false", "no")


def activo() -> bool:
    """Si este proceso corre en un entorno que no produce efectos afuera."""
    return (os.environ.get(VARIABLE) or "").strip().lower() not in _APAGADA


def es_de_la_red_local(url: str | None) -> bool:
    """
    Si 'url' apunta a un servicio de la red local: un host sin punto.

    Una IP tiene puntos (o ':' si es v6) y cuenta como afuera; un host vacio,
    tambien. Y una IP escrita SIN puntos tambien: '134744072' o '0x8080808'
    llegan a 8.8.8.8 (medido por el auditor de frontera, 20/10/2026). Lo que
    'inet_aton' acepta como direccion es una direccion, no un servicio.
    """
    partes = urlparse(url or "")
    host = partes.hostname or ""
    if not host or "." in host or ":" in host:
        return False
    try:
        #  'http://backend:8000' + '.otro.com/x' arma 'backend:8000.otro.com':
        #  el host parece local y el resto se fue al puerto. Un puerto que no
        #  es un numero no es la red local.
        partes.port
    except ValueError:
        return False
    try:
        socket.inet_aton(host)
        return False
    except OSError:
        return True


def motivo(que: str) -> str:
    return (f"{que} no salio: este entorno no produce efectos externos "
            f"({VARIABLE}). Solo escribe dentro de la red local.")
