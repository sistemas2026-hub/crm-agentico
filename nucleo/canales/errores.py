# -*- coding: utf-8 -*-
"""
================================================================================
 ERRORES HTTP  --  lo que una respuesta de error puede decir, y lo que no
================================================================================

Por que existe (D19 + D23, 17/09/2026)
--------------------------------------
Cuarenta y seis respuestas del motor devolvian el texto de una excepcion:
'{"error": str(e)}', 'f"No se pudo sincronizar: {type(e).__name__}: {e}"',
el cuerpo crudo de un proveedor (r.text[:200]). Ese texto es de quien lanzo la
excepcion, no de Dexter: un error de PostgreSQL trae el valor de la fila, uno
de requests la URL con sus parametros, uno de OpenAI o del ISP lo que el
proveedor haya querido contestar. D19 lo encontro en la sincronizacion de
localidades; D23 en las rutas de administracion. D20 ya lo habia sacado del
LOG; esto lo saca de la RESPUESTA.

La regla
--------
Una respuesta de error lleva:
  - un mensaje escrito por Dexter, y
  - un 'codigo' estable para que la pantalla y quien soporta puedan
    distinguir casos sin leer el texto.
Nunca str(e) de algo que Dexter no escribio, nunca el cuerpo de un proveedor,
nunca una traza. Lo que sirve para diagnosticar va al log por registrar(), que
ya lo reduce a tipo, sqlstate, codigo HTTP y archivo:linea.

Las excepciones PROPIAS cuyo mensaje se escribe para quien opera la pantalla
("el agente X no existe", "la version aprobada no se puede pisar") SI se
muestran: son la forma en que una regla del producto se explica. Estan listadas
en _publicas(), y tests/test_errores_http.py exige que ninguna se construya
interpolando una excepcion atrapada -- si una lo hiciera, su texto dejaria de
ser de Dexter.
================================================================================
"""

from __future__ import annotations

from flask import jsonify

from nucleo.observabilidad.registro import error_seguro, registrar


def _publicas() -> tuple[type, ...]:
    """Las excepciones de Dexter cuyo mensaje puede ir a la pantalla.

    Import tardio: estos modulos importan media aplicacion y este se importa
    desde api.py."""
    from nucleo.canales.whatsapp import ErrorWhatsApp
    from nucleo.conectores.catalogo import ErrorConector
    from nucleo.config.editor import ErrorEdicion
    from nucleo.config.fusion import FusionInvalida
    from nucleo.ingesta.corpus import RolesInvalidos, VersionAprobadaInmutable
    from nucleo.modelo.motor import ErrorMotor
    from nucleo.persistencia.db import TenantSinConfiguracion
    from nucleo.seguridad.secretos import ErrorSecreto
    return (ErrorWhatsApp, ErrorConector, ErrorEdicion, FusionInvalida, RolesInvalidos,
            VersionAprobadaInmutable, ErrorMotor, TenantSinConfiguracion, ErrorSecreto)


def mensaje_publico(e: BaseException, por_defecto: str) -> str:
    """El texto de 'e' si es una excepcion propia de Dexter; si no, 'por_defecto'.

    Un except que atrapa una clase amplia (ValueError, RuntimeError) puede
    recibir tanto la propia como una de una biblioteca: se decide por la clase
    real de la instancia, no por la del except."""
    return str(e) if isinstance(e, _publicas()) else por_defecto


def fallo(estado: int, codigo: str, mensaje: str, *, componente: str,
          e: BaseException | None = None, **extra):
    """Respuesta de error con mensaje fijo. Si hubo excepcion, va al log saneada."""
    if e is not None:
        # 'origen' y no 'componente': en produccion registrar() todavia no tiene
        # sus parametros solo-posicionales (D26 llega con el relevo) y un campo
        # llamado 'componente' chocaria.
        registrar("http", "respuesta de error", origen=componente, codigo=codigo,
                  estado=estado, error=e)
    return jsonify({"error": mensaje, "codigo": codigo, **extra}), estado


def estado_http_de(e: BaseException) -> int | None:
    """El codigo HTTP del proveedor si la excepcion lo trae (requests, WhatsApp).
    Es metadata, no texto: se puede devolver para que quien administra sepa si
    fue un 401, un 404 o un 500 del otro lado."""
    valor = error_seguro(e).get("http_status")
    return valor if isinstance(valor, int) else None
