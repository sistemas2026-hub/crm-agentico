# -*- coding: utf-8 -*-
"""
================================================================================
 UN ENTORNO QUE NO SALE  --  SIN_EFECTOS_EXTERNOS
================================================================================

    py -3.13 tests/test_entorno_sin_efectos.py

POR QUE EXISTE  --  20/10/2026
------------------------------
El entorno local igual a produccion usa las credenciales reales de WispHub y
SmartOLT para LEER. Esas mismas credenciales escriben, y el interruptor de
autonomia deja pasar a proposito lo que aprueba una persona. Ver
nucleo/seguridad/entorno.py.

QUE SE AFIRMA, Y POR QUE ASI
-----------------------------
Sobre el EFECTO: que la peticion de red SALGA o NO SALGA, y que la frontera
no se consulte cuando no va a salir (un permiso de un solo uso no se gasta).
La red y la frontera se sustituyen por dobles que anotan si se los llamo.

Cada caso de "no sale" tiene su pareja de "si sale": un freno que bloqueara
todo tambien pasaria la primera mitad.

NO SE LLAMA A NINGUNA API NI A LA BASE.
================================================================================
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import whatsapp                               # noqa: E402
from nucleo.config.schema import Herramienta                      # noqa: E402
from nucleo.herramientas import http                              # noqa: E402
from nucleo.seguridad import entorno, frontera                    # noqa: E402

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


class _Salio(Exception):
    """La peticion llego a la red. Cortarla aca evita armar una respuesta."""


class Banco:
    """Dobles de la red y de la frontera, y la variable puesta o no."""

    def __init__(self, valor):
        self.valor = valor
        self.red: list[str] = []
        self.frontera = 0

    def __enter__(self):
        self._antes = os.environ.get(entorno.VARIABLE)
        if self.valor is None:
            os.environ.pop(entorno.VARIABLE, None)
        else:
            os.environ[entorno.VARIABLE] = self.valor
        self._orig = (http.requests.get, http.requests.request,
                      whatsapp.requests.post, frontera.exigir, http.headers_de,
                      whatsapp._secreto, whatsapp._cfg)

        def _red(metodo):
            def f(url, *a, **k):
                self.red.append(f"{metodo} {url}")
                raise _Salio()
            return f

        def _exigir(*a, **k):
            self.frontera += 1

        http.requests.get = _red("GET")
        http.requests.request = lambda metodo, url, *a, **k: _red(metodo)(url)
        whatsapp.requests.post = _red("POST")
        frontera.exigir = _exigir
        http.headers_de = lambda h, t=None: {}
        whatsapp._secreto = lambda *a, **k: "x"
        whatsapp._cfg = lambda c: SimpleNamespace(
            token_ref="t", phone_number_id_ref="p", api_base="https://graph.example",
            version_api="v1")
        return self

    def __exit__(self, *e):
        (http.requests.get, http.requests.request, whatsapp.requests.post,
         frontera.exigir, http.headers_de, whatsapp._secreto,
         whatsapp._cfg) = self._orig
        if self._antes is None:
            os.environ.pop(entorno.VARIABLE, None)
        else:
            os.environ[entorno.VARIABLE] = self._antes
        return False


def herramienta(nombre, **kw):
    base = dict(nombre=nombre, tipo="http", roles_permitidos=["soporte"],
                metodo="POST", endpoint="/x/", base_url="https://api.wisphub.io",
                solo_lectura=False, requiere_confirmacion=True)
    base.update(kw)
    return Herramienta(**base)


def correr(h, variables=None):
    """('bloqueo' | 'salio' | 'otro:<tipo>', mensaje)"""
    try:
        http.ejecutar(h, {}, "t", variables)
    except _Salio:
        return "salio", ""
    except http.ErrorHerramientaHttp as e:
        return "bloqueo", str(e)
    except Exception as e:                                       # noqa: BLE001
        return f"otro:{type(e).__name__}", str(e)
    return "sin_red", ""


print("\n== 1. La variable se lee fallando cerrado")
for valor, esperado in ((None, False), ("", False), ("0", False), ("false", False),
                        ("No", False), ("1", True), ("si", True), ("true", True),
                        ("verdadero", True)):
    with Banco(valor):
        comprobar(f"{valor!r} -> {'encendida' if esperado else 'apagada'}",
                  entorno.activo() is esperado)

print("\n== 2. Que es la red local")
for url, esperado in (("http://backend:8000/api", True), ("http://localhost:5000", True),
                      ("https://api.wisphub.io", False), ("http://10.0.0.5:80", False),
                      ("http://[::1]:80", False), ("", False), (None, False),
                      #  Una IP sin puntos llega a 8.8.8.8 (auditor, 20/10/2026).
                      ("http://134744072/", False), ("http://0x8080808/", False)):
    comprobar(f"{url!r} -> {'local' if esperado else 'afuera'}",
              entorno.es_de_la_red_local(url) is esperado)

print("\n== 3. Encendida: escribir afuera NO sale")
with Banco("1") as b:
    r, msg = correr(herramienta("registrar_pago"))
    comprobar("una escritura a WispHub se bloquea", r == "bloqueo", r)
    comprobar("el motivo nombra la variable", entorno.VARIABLE in msg, msg)
    comprobar("no llego a la red", not b.red, str(b.red))

print("\n== 3b. Encendida: la frontera habla PRIMERO, como en produccion")


class _SinPermiso(Exception):
    pass


with Banco("1") as b:
    def _rechaza(*a, **k):
        raise _SinPermiso()
    frontera.exigir = _rechaza
    try:
        http.ejecutar(herramienta("registrar_pago"), {}, "t", None)
        r = "sin_error"
    except _SinPermiso:
        r = "frontera"
    except http.ErrorHerramientaHttp:
        r = "freno"
    comprobar("sin permiso, el rechazo es el de la frontera y no el del freno",
              r == "frontera", r)

print("\n== 3c. Encendida: se mira la URL que SALE, no solo la base")
with Banco("1") as b:
    r, _ = correr(herramienta("crear_caso_soporte", base_url="http://backend:8000",
                              endpoint="@api.wisphub.io/api/tickets/"))
    comprobar("un endpoint sin '/' que cambia el host se bloquea", r == "bloqueo", r)
    r, _ = correr(herramienta("crear_caso_soporte", base_url="http://backend",
                              endpoint=".wisphub.io/api/tickets/"))
    comprobar("un endpoint que alarga el host se bloquea", r == "bloqueo", r)
    r, _ = correr(herramienta("crear_caso_soporte", base_url="http://backend:8000",
                              endpoint=".wisphub.io/api/tickets/"))
    comprobar("y si el resto cae en el puerto, tambien", r == "bloqueo", r)
    try:
        http.ejecutar(herramienta("crear_caso_soporte", base_url="http://backend:8000",
                                  endpoint="{destino}/api/tickets/"),
                      {"destino": "@api.wisphub.io"}, "t", None)
        r = "sin_error"
    except _Salio:
        r = "salio"
    except http.ErrorHerramientaHttp:
        r = "bloqueo"
    comprobar("un marcador de ruta que cambia el host se bloquea", r == "bloqueo", r)
    comprobar("nada llego a la red", not b.red, str(b.red))

print("\n== 4. Encendida: escribir en la red local SI sale (el escalamiento)")
with Banco("1") as b:
    r, _ = correr(herramienta("crear_caso_soporte", base_url="http://backend:8000/api"))
    comprobar("una escritura al CRM local sale", r == "salio", r)
    comprobar("y paso por la frontera", b.frontera == 1, str(b.frontera))

print("\n== 5. Encendida: leer afuera SI sale")
with Banco("1") as b:
    r, _ = correr(herramienta("consultar_ticket", metodo="GET", solo_lectura=True))
    comprobar("una lectura a WispHub sale", r == "salio", r)

print("\n== 6. Apagada (produccion): escribir afuera sale como siempre")
with Banco(None) as b:
    r, _ = correr(herramienta("registrar_pago"))
    comprobar("una escritura a WispHub sale", r == "salio", r)
    comprobar("y paso por la frontera", b.frontera == 1, str(b.frontera))

print("\n== 7. El destino sale de 'base_url_ref' cuando la herramienta lo declara")
smartolt = dict(base_url=None, base_url_ref="SUBDOMINIO_OLT")
with Banco("1") as b:
    r, _ = correr(herramienta("reiniciar_ont", **smartolt),
                  {"SUBDOMINIO_OLT": "https://empresa.olt.example/"})
    comprobar("una variable que apunta afuera se bloquea", r == "bloqueo", r)
    r, _ = correr(herramienta("reiniciar_ont", **smartolt),
                  {"SUBDOMINIO_OLT": "http://backend:8000"})
    comprobar("la misma variable apuntando a la red local sale", r == "salio", r)
    r, _ = correr(herramienta("reiniciar_ont", **smartolt), {})
    comprobar("una variable que no se resuelve cuenta como afuera", r == "bloqueo", r)

print("\n== 8. WhatsApp no envia ni sube nada con la variable encendida")
with Banco("1") as b:
    for nombre, llamar in (
            ("enviar", lambda: whatsapp._post(None, "t", "123/messages", {})),
            ("subir media", lambda: whatsapp.subir_media(None, "t", b"x", "image/png"))):
        try:
            llamar()
            r = "sin_error"
        except whatsapp.ErrorWhatsApp as e:
            r = "bloqueo" if entorno.VARIABLE in str(e) else f"otro:{e}"
        except _Salio:
            r = "salio"
        comprobar(f"{nombre}: se bloquea nombrando la variable", r == "bloqueo", r)
    comprobar("nada llego a Meta", not b.red, str(b.red))

with Banco(None) as b:
    for nombre, llamar in (
            ("el envio", lambda: whatsapp._post(None, "t", "123/messages", {})),
            ("la subida", lambda: whatsapp.subir_media(None, "t", b"x", "image/png"))):
        try:
            llamar()
            r = "sin_error"
        except _Salio:
            r = "salio"
        except Exception as e:                                   # noqa: BLE001
            r = f"otro:{type(e).__name__}"
        comprobar(f"apagada, {nombre} sale como siempre", r == "salio", r)

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Un entorno con SIN_EFECTOS_EXTERNOS lee afuera y no escribe afuera.")
