# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL SONDEO SEGURO  --  el bloqueo SSRF no puede fallar en silencio
================================================================================

Por que existe
--------------
nucleo/herramientas/sondeo.py es la unica parte del proyecto que hace
pedidos HTTP a una URL que un humano escribio en el momento, no a un
endpoint pre-verificado. Si el bloqueo de direcciones privadas/internas
tiene un agujero, un ADMIN (o una cuenta ADMIN comprometida) podria usar al
servidor como proxy hacia su propia red interna -- el motor, la base, o el
endpoint de metadata de la nube. Esta guarda prueba el bloqueo con IPs y
hostnames reales, no solo con la logica en abstracto.

Uso
---
    py -3.13 tests/test_sondeo.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.herramientas import sondeo   # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def _rechaza(url: str) -> bool:
    try:
        sondeo._verificar_url_publica(url)
        return False
    except sondeo.ErrorSondeo:
        return True


print("esquema: solo https")
comprobar(_rechaza("http://api.wisphub.io/api/clientes/"), "http (sin s) se rechaza")
comprobar(_rechaza("ftp://api.wisphub.io/"), "un esquema que no es http/https se rechaza")

print("\nrangos privados/internos -- por IP literal")
comprobar(_rechaza("https://127.0.0.1/"), "loopback (127.0.0.1)")
comprobar(_rechaza("https://10.0.0.5/"), "RFC 1918 clase A (10.x)")
comprobar(_rechaza("https://172.17.0.1/"), "RFC 1918 clase B -- rango real de Docker")
comprobar(_rechaza("https://192.168.1.1/"), "RFC 1918 clase C (192.168.x)")
comprobar(_rechaza("https://169.254.169.254/"), "link-local -- ES el endpoint de metadata de AWS/GCP/Azure")
comprobar(_rechaza("https://[::1]/"), "loopback IPv6")

print("\nhostnames que resuelven a redes internas (no solo IPs literales)")
comprobar(_rechaza("https://localhost/"), "localhost resuelve a loopback")

print("\nuna URL publica real SI pasa la verificacion (no es fail-closed hasta el punto de bloquear todo)")
try:
    sondeo._verificar_url_publica("https://api.wisphub.io/api/clientes/")
    paso = True
except sondeo.ErrorSondeo as e:
    paso = False
    print(f"    (broto: {e})")
comprobar(paso, "un host publico real (api.wisphub.io) no se bloquea")

print("\nsondear() contra una API real y publica -- verifica que el resumen tiene la forma correcta")
import os                                                     # noqa: E402
from dotenv import load_dotenv                                # noqa: E402
load_dotenv(RAIZ / ".env", override=True)
clave = os.getenv("WISPHUB_API_KEY")
if clave:
    resultado = sondeo.sondear(
        "https://api.wisphub.io/api/clientes/",
        headers={"Authorization": f"Api-Key {clave}"},
        params={"limit": 3})
    comprobar("count" in resultado, "el resumen trae 'count'")
    comprobar("campos_disponibles" in resultado and len(resultado["campos_disponibles"]) > 0,
             "el resumen lista los campos disponibles, sacados de una fila real")
    comprobar(len(resultado["muestra"]) <= 3, "la muestra nunca supera el limite (nunca vuelca todo)")
else:
    print("  (sin WISPHUB_API_KEY en el entorno -- se salta la prueba contra la API real)")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El sondeo bloquea redes privadas/internas y resume sin volcar todo.")
