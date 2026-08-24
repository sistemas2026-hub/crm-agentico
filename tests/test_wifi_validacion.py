# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- validacion de nombre de red y clave (nucleo/herramientas/wifi.py)
================================================================================

Corre sin base y sin modelo:

    py -3.13 tests/test_wifi_validacion.py

Existe porque estas reglas son la unica barrera entre un cliente escribiendo
cualquier cosa y una persona tomando un trabajo que el equipo no va a aceptar.
Si se aflojan sin querer, no se nota en ninguna pantalla: se nota semanas
despues, en un pedido que alguien intento aplicar y fallo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.herramientas import wifi  # noqa: E402

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


print("=" * 70)
print(" VALIDACION DE WIFI")
print("=" * 70)

print("\nnombre de red (SSID)")
afirmar(wifi.validar_ssid("Casa Rodriguez") == [],
        "un nombre normal pasa")
afirmar(wifi.validar_ssid("") and wifi.validar_ssid("   "),
        "vacio o solo espacios se rechaza")
afirmar(wifi.validar_ssid(" Casa"), "espacio al principio se rechaza")
afirmar(wifi.validar_ssid("Casa "), "espacio al final se rechaza")
afirmar(wifi.validar_ssid("A" * 32) == [], "32 caracteres justos pasan")
afirmar(wifi.validar_ssid("A" * 33), "33 caracteres se rechazan")

# La ñ, las tildes y los emojis se rechazan en el NOMBRE, no solo en la clave:
# los equipos de un ISP no los manejan bien y el sintoma no es un error al
# guardar sino una red que el cliente no encuentra.
afirmar(wifi.validar_ssid("Casa Peña"), "la ñ en el nombre se rechaza")
afirmar(wifi.validar_ssid("Mi Camión"), "una tilde en el nombre se rechaza")
afirmar(wifi.validar_ssid("Casa 🙂"), "un emoji en el nombre se rechaza")

# El conteo por octetos sigue importando y se mide aparte: la regla de arriba
# ya rechaza esos caracteres, asi que el largo se comprueba en la funcion.
afirmar(wifi._largo_en_octetos("Casa Peña") == 10 and len("Casa Peña") == 9,
        "el largo se mide en octetos, no en letras (la ñ ocupa dos)")

afirmar(wifi.validar_ssid("Casa\tRed"), "una tabulacion se rechaza")
afirmar(wifi.validar_ssid("Casa-Rodriguez", desaconsejados="-"),
        "el guion se rechaza cuando el tenant lo desaconseja")
afirmar(wifi.validar_ssid("Casa-Rodriguez") == [],
        "y pasa cuando el tenant NO lo desaconseja (no es regla del nucleo)")

print("\nclave")
afirmar(wifi.validar_clave("clave1234") == [], "una clave normal pasa")
afirmar(wifi.validar_clave("corta12"), "7 caracteres se rechazan")
afirmar(wifi.validar_clave("clave123") == [], "8 caracteres justos pasan")
afirmar(wifi.validar_clave("x" * 63) == [], "63 caracteres justos pasan")
afirmar(wifi.validar_clave("x" * 64), "64 NO hexadecimales se rechazan")
afirmar(wifi.validar_clave("0123456789abcdef" * 4) == [],
        "64 hexadecimales SI pasan: es la PSK ya derivada, no una frase")
afirmar(wifi.validar_clave("clave con ñ"), "la ñ se rechaza (fuera de ASCII)")
afirmar(wifi.validar_clave("clave1234🙂"), "un emoji se rechaza")
afirmar(wifi.validar_clave("clave1234 "), "espacio al final se rechaza")

print("\nclaves debiles -- avisan, NO rechazan")
afirmar(wifi.validar_clave("12345678") == [],
        "'12345678' es valida para el estandar y NO se rechaza")
afirmar(wifi.clave_es_debil("12345678"), "'12345678' se marca como debil")
afirmar(wifi.clave_es_debil("password"), "'password' se marca como debil")
afirmar(wifi.clave_es_debil("11111111"), "todo el mismo caracter se marca")
afirmar(not wifi.clave_es_debil("mi clave de casa 2026"),
        "una clave razonable no se marca")

print("\nnada revienta con entradas raras")
afirmar(wifi.validar_ssid(None), "un nombre None se rechaza sin explotar")
afirmar(wifi.validar_clave(None), "una clave None se rechaza sin explotar")
afirmar(not wifi.clave_es_debil(None), "clave_es_debil(None) no explota")

print()
print("=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden.")
print("=" * 70)
