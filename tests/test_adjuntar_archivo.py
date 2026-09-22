# -*- coding: utf-8 -*-
"""
================================================================================
 UN ARCHIVO QUE VIAJA DE UN SERVICIO A UNA API DE TERCEROS
================================================================================

Por que existe
--------------
El tecnico necesita la orden de instalacion en el celular, y el token del ISP
vive en el motor -- no en el backend que genera el PDF. Asi que el PDF tiene
que cruzar el puente entre servicios, que es JSON, y salir del otro lado como
un archivo de verdad en un cuerpo multipart.

Tres cosas que probar, y las tres fallan EN SILENCIO si nadie las mira:

1. LAS DOS DECLARACIONES VAN JUNTAS. Un archivo viaja por 'sobrescribir', y
   ese camino tiene lista blanca. Declarar 'argumentos_archivo' sin
   'argumentos_sobrescribibles' no da error en ningun lado: el adjunto se
   descarta, el ticket sale sin archivo, y nadie se entera hasta abrirlo en el
   ISP. Tiene que reventar al cargar la config.

2. EL MODELO NO PUEDE ADJUNTAR NADA. El archivo no esta en
   'filtros_verificados', asi que no hay camino desde una conversacion. Solo
   'ejecutar_para_servicio' -- es decir, otro servicio del despliegue-- puede
   mandarlo. Un modelo capaz de subir un archivo arbitrario a un sistema de
   terceros es una cosa distinta de un asistente.

3. SALE COMO ARCHIVO, NO COMO TEXTO. Si el diccionario se mandara con str(),
   la API recibiria la palabra "{'nombre': ...}" y guardaria basura con
   nombre de PDF.

Corre SIN BASE DE DATOS y sin red: se intercepta la llamada HTTP.

Uso
---
    py -3.13 tests/test_adjuntar_archivo.py
================================================================================
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config.schema import Herramienta                         # noqa: E402
from nucleo.herramientas import http as ejecutor_http                # noqa: E402
from nucleo.modelo import motor                                      # noqa: E402

# EL INTERRUPTOR DE AUTONOMIA, DECLARADO (15/09/2026)
# ---------------------------------------------------
# Desde la fase 1 de seguridad, toda escritura pasa por
# nucleo/seguridad/interruptor.py, que lee una fila de la base. Esta prueba
# corre SIN base, asi que esa lectura falla y el gate --haciendo exactamente lo
# que debe-- bloquea la accion; sin esta declaracion, lo que se probaria aca es
# el fail-closed y no lo que el archivo dice probar.
#
# Se declara 'activo' y no se desactiva el gate: lo que se sustituye es la
# RESPUESTA de la base, igual que se sustituye la respuesta de WispHub mas
# abajo. El camino del codigo es el real.
from nucleo.persistencia import db as _persistencia_de_prueba      # noqa: E402

_persistencia_de_prueba.estado_autonomia = lambda tenant: {
    "estado": "activo", "estado_anterior": None, "actor": "prueba",
    "motivo": "", "creado_en": None}
_persistencia_de_prueba.registrar_auditoria = lambda *a, **k: None
_persistencia_de_prueba.reclamar_operacion_externa = (
    lambda *a, **k: {"decision": "ejecutar", "fila": {"intentos": 1}})
_persistencia_de_prueba.finalizar_operacion_externa = lambda *a, **k: None

# --- AUTONOMIA 2 (19/09/2026) ---------------------------------------------
# Desde este bloque, una escritura autonoma necesita ADEMAS del interruptor:
# la etapa encendida, el prerequisito de B-7 y una autorizacion granular de ESA
# herramienta (nucleo/seguridad/autonomia2.py y autorizacion.py). Esta prueba
# no trata de eso, asi que declara las respuestas igual que declara el
# interruptor arriba -- se sustituye la RESPUESTA de la base, nunca el gate.
# El camino del codigo sigue siendo el real: frontera.autonoma() consulta las
# tres, y quien las prueba de verdad es tests/test_autonomia2.py.
import os                                                           # noqa: E402

os.environ["AUTONOMIA_2_ACTIVA"] = "1"
_persistencia_de_prueba.secreto_jwt_en_base = lambda: ""
_persistencia_de_prueba.nivel_autonomia = lambda tenant: {
    "nivel": 2, "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba", "actor": "prueba", "motivo": "",
    "creado_en": None}
_persistencia_de_prueba.autorizacion_herramienta = lambda tenant, herramienta: {
    "id": "00000000-0000-0000-0000-000000000001", "herramienta": herramienta,
    "estado": "autorizada", "estado_anterior": None, "nivel_maximo": 2,
    "vigente_desde": None, "vigente_hasta": None, "autorizado_por": "prueba",
    "motivo": "", "limites": {}, "creado_en": None}
_persistencia_de_prueba.registrar_ejecucion_autonoma = lambda *a, **k: None



fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


BASE = dict(nombre="adjuntar_orden", tipo="http",
            endpoint="/api/tickets/{id_ticket}/", base_url="https://api.ejemplo.io",
            descripcion="x", roles_permitidos=["administracion"],
            metodo="PATCH", solo_lectura=False, requiere_confirmacion=True,
            invocable_por_servicio=True)


print("== 1. las dos declaraciones van juntas o no se carga ==")

try:
    Herramienta(**BASE, multipart=True, argumentos_archivo=["archivo_ticket"])
    ok = False
except Exception:
    ok = True
afirmar(ok, "'argumentos_archivo' sin 'argumentos_sobrescribibles' se rechaza "
            "-- si no, el adjunto se descarta en silencio")

try:
    Herramienta(**BASE, argumentos_archivo=["archivo_ticket"],
                argumentos_sobrescribibles=["archivo_ticket"])
    ok = False
except Exception:
    ok = True
afirmar(ok, "y sin 'multipart: true' tambien: un archivo no cabe en un JSON")

# 'id_ticket' tambien es sobrescribible: resuelve el marcador de la URL y lo
# manda el backend, no el modelo. Sin declararlo, _resolver_argumentos lo
# descarta y la llamada muere con "endpoint sin resolver" -- que es
# exactamente como la cancelacion de una solicitud nunca cerro su ticket.
herr = Herramienta(**BASE, multipart=True,
                   argumentos_fijos={"_adjunto": "1"},
                   argumentos_archivo=["archivo_ticket"],
                   argumentos_sobrescribibles=["id_ticket", "archivo_ticket"])
afirmar(True, "con las tres declaradas, la herramienta carga")


print("\n== 2. el modelo no puede adjuntar nada ==")
# El unico camino por el que un valor del modelo entra a la llamada es
# 'filtros_verificados'. Un archivo nunca esta ahi.
args = motor._resolver_argumentos(
    herr, None, {"archivo_ticket": {"nombre": "malo.pdf", "base64": "eA=="}})
afirmar("archivo_ticket" not in args,
        "lo que propone el modelo se descarta: no hay via desde una "
        "conversacion a subir un archivo a un tercero")
afirmar(args.get("_adjunto") == "1",
        "y el campo fijo sigue saliendo (el que evita el 500 de WispHub)")


print("\n== 3. por el puente entre servicios SI pasa ==")

PDF = b"%PDF-1.4 contenido de prueba"
entrada = {"id_ticket": "92151",
           "archivo_ticket": {"nombre": "orden.pdf", "tipo": "application/pdf",
                              "base64": base64.b64encode(PDF).decode()}}

capturado: dict = {}


class _RespuestaFalsa:
    status_code = 200
    ok = True
    text = "{}"
    content = b"{}"
    headers = {"Content-Type": "application/json"}

    def json(self):
        return {"id_ticket": 92151}

    def raise_for_status(self):
        return None


def _request_falso(metodo, url, **kw):
    capturado["metodo"] = metodo
    capturado["url"] = url
    capturado["files"] = kw.get("files")
    capturado["json"] = kw.get("json")
    return _RespuestaFalsa()


class _ConfigFalsa:
    class identidad:
        slug = "prueba"
    variables_tenant: dict = {}
    herramientas: list = []


_real = ejecutor_http.requests.request
ejecutor_http.requests.request = _request_falso
try:
    motor.ejecutar_para_servicio(_ConfigFalsa(), herr, entrada)
finally:
    ejecutor_http.requests.request = _real

afirmar(capturado.get("metodo") == "PATCH", "sale por PATCH")
afirmar("92151" in (capturado.get("url") or ""),
        "y el id del ticket va en la URL, no en el cuerpo")

archivos = capturado.get("files") or {}
parte = archivos.get("archivo_ticket")
afirmar(isinstance(parte, tuple) and len(parte) == 3,
        "el archivo sale como parte de ARCHIVO (nombre, bytes, tipo), no como "
        "un campo de texto")
afirmar(bool(parte) and parte[0] == "orden.pdf", "conserva el nombre que se le dio")
afirmar(bool(parte) and parte[1] == PDF,
        "y los BYTES originales -- si se mandara str(), la API guardaria la "
        "palabra \"{'nombre': ...}\" con nombre de PDF")
afirmar(bool(parte) and parte[2] == "application/pdf", "con su tipo")

acompanante = archivos.get("_adjunto")
afirmar(acompanante == (None, "1"),
        "y el campo acompañante va como campo comun: WispHub devuelve 500 si "
        "el archivo viaja solo (medido el 09/09/2026)")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El archivo cruza el puente entre servicios y sale como archivo.")
