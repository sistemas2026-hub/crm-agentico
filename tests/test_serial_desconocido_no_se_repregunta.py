# -*- coding: utf-8 -*-
"""
UN SERIAL QUE LA OLT NO CONOCE NO SE VUELVE A PREGUNTAR CADA VEZ (09/11/2026).

El Supervisor recorre sus casos varias veces por hora y, por cada serial que SmartOLT
rechaza con 400, pagaba tres lecturas por dos intentos. Se afirma sobre el EFECTO,
pasando por `_estado_equipo` real y sustituyendo solo la salida a la red:

  1. un rechazo definitivo en TODAS las lecturas se recuerda: la segunda vez no sale
     ninguna llamada y el resultado es el mismo ({});
  2. un fallo de RED o un timeout NO se recuerda (ahi si puede haber dato despues);
  3. si UNA lectura contesta, no se recuerda nada y el dato sale;
  4. otro serial no hereda el rechazo (corregirlo en WispHub lo libera solo);
  5. pasado el plazo, se vuelve a preguntar.

    py -3.13 tests/test_serial_desconocido_no_se_repregunta.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import requests  # noqa: E402

from nucleo.canales import api  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


def http_error(codigo):
    r = requests.Response()
    r.status_code = codigo
    return requests.HTTPError(f"{codigo}", response=r)


config = SimpleNamespace(
    herramientas=[SimpleNamespace(nombre=n) for n in api._HERRAMIENTAS_EQUIPO],
    variables_tenant={}, zona_horaria="")
llamadas = []


def con_respuestas(por_herramienta):
    original = api.ejecutor_http.ejecutar

    def falso(herr, args, tenant=None, **k):
        llamadas.append((herr.nombre, args["sn_onu"]))
        r = por_herramienta(herr.nombre, args["sn_onu"])
        if isinstance(r, Exception):
            raise r
        return r

    api.ejecutor_http.ejecutar = falso
    return original


def limpiar():
    api._seriales_desconocidos.clear()
    llamadas.clear()


def restaurar(original):
    api.ejecutor_http.ejecutar = original


print("\n1. el rechazo definitivo se recuerda")
limpiar()
o = con_respuestas(lambda n, s: http_error(400))
try:
    primera = api._estado_equipo(config, "SERIALMALO", "t")
    gastadas = len(llamadas)
    segunda = api._estado_equipo(config, "SERIALMALO", "t")
finally:
    restaurar(o)
afirmar(primera == {} and segunda == {}, "las dos veces el resultado es el mismo ({})")
afirmar(gastadas == 3 and len(llamadas) == 3, "la primera vez pregunta las tres; la segunda NO sale a la red")

print("\n2. un fallo de red no se recuerda")
limpiar()
o = con_respuestas(lambda n, s: requests.ConnectionError("sin ruta"))
try:
    api._estado_equipo(config, "SERIALRED", "t")
    api._estado_equipo(config, "SERIALRED", "t")
finally:
    restaurar(o)
afirmar(len(llamadas) == 6, "un ConnectionError vuelve a preguntarse (6 llamadas, no 3)")

limpiar()
o = con_respuestas(lambda n, s: requests.Timeout("lento"))
try:
    api._estado_equipo(config, "SERIALLENTO", "t")
    api._estado_equipo(config, "SERIALLENTO", "t")
finally:
    restaurar(o)
afirmar(len(llamadas) == 6, "un timeout tampoco se recuerda")

limpiar()
o = con_respuestas(lambda n, s: http_error(503))
try:
    api._estado_equipo(config, "SERIAL503", "t")
    api._estado_equipo(config, "SERIAL503", "t")
finally:
    restaurar(o)
afirmar(len(llamadas) == 6, "un 503 (el proveedor caido) tampoco se recuerda")

print("\n3. si una lectura contesta, no se recuerda y el dato sale")
limpiar()
o = con_respuestas(lambda n, s: {"onu_status": "Online"} if n == "consultar_estado_ont" else http_error(400))
try:
    r1 = api._estado_equipo(config, "SERIALMIXTO", "t")
    r2 = api._estado_equipo(config, "SERIALMIXTO", "t")
finally:
    restaurar(o)
afirmar(r1.get("onu_status") == "Online" and r2.get("onu_status") == "Online" and len(llamadas) == 6,
        "el estado sale las dos veces y nada se dio por desconocido")

print("\n4. otro serial no hereda el rechazo")
limpiar()
o = con_respuestas(lambda n, s: http_error(400) if s == "VIEJO" else {"onu_status": "Online"})
try:
    api._estado_equipo(config, "VIEJO", "t")
    corregido = api._estado_equipo(config, "NUEVO", "t")
    otro_tenant = api._estado_equipo(config, "VIEJO", "otra")
finally:
    restaurar(o)
afirmar(corregido.get("onu_status") == "Online", "el serial corregido se consulta y responde")
afirmar(sum(1 for _, s in llamadas if s == "VIEJO") == 6, "y el mismo serial en OTRA empresa tampoco hereda el rechazo")

print("\n5. pasado el plazo se vuelve a preguntar")
limpiar()
o = con_respuestas(lambda n, s: http_error(404))
try:
    api._estado_equipo(config, "SERIALVIEJO", "t")
    clave = ("t", "SERIALVIEJO")
    api._seriales_desconocidos[clave] -= api.SEGUNDOS_SERIAL_DESCONOCIDO + 1
    api._estado_equipo(config, "SERIALVIEJO", "t")
finally:
    restaurar(o)
afirmar(len(llamadas) == 6, "vencida la entrada, vuelve a preguntar")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] Un serial que la OLT no conoce se recuerda; lo demas se sigue preguntando.")
