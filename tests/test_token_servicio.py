# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL TOKEN DE SERVICIO  --  la segunda capa que le faltaba a /chat y /agentes
================================================================================

Por que existe
--------------
DESPLIEGUE.md ya documentaba el hueco: lo unico que separaba /chat, /agentes
y el resto de rutas internas de internet era el 'PathPrefix' de una regla de
Traefik -- una sola capa, cuando el resto del proyecto usa dos por principio
(PRD.md 7.4). nucleo/canales/api.py::_exigir_token_de_servicio() agrega la
segunda: un token compartido, fail-closed cuando esta configurado.

Deliberadamente NO bloquea nada si 'MOTOR_SERVICE_TOKEN' no esta en el
entorno -- eso evita romper el arranque local o un despliegue que todavia no
cargo la variable. El lado del frontend (18 archivos en django-crm/frontend
que le hablan al motor) queda pendiente a proposito: verificar que cada
fetch manda el header exige poder levantar el CRM y probar cada pantalla
(ajustes, agentes, conversaciones, simulador, manual, corpus), que este
test no puede hacer. NO activar 'MOTOR_SERVICE_TOKEN' en Dokploy hasta que
ese lado este wireado, o todas esas pantallas se rompen de una vez.

Uso
---
    py -3.13 tests/test_token_servicio.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv               # noqa: E402
load_dotenv(RAIZ / ".env", override=True)     # noqa: E402

import nucleo.canales.api as api              # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


cliente = api.app.test_client()

print("sin MOTOR_SERVICE_TOKEN configurado, nada se bloquea (no romper arranques sin la variable)")
api._TOKEN_SERVICIO = None
resp = cliente.get("/salud")
comprobar(resp.status_code == 200, "/salud responde igual sin token configurado")
resp = cliente.get("/configuracion?tenant=rapilink")
comprobar(resp.status_code != 401, "una ruta interna no exige token si la variable no esta puesta")

print("\ncon MOTOR_SERVICE_TOKEN configurado, las rutas internas lo exigen")
api._TOKEN_SERVICIO = "secreto-de-prueba"
resp = cliente.get("/configuracion?tenant=rapilink")
comprobar(resp.status_code == 401, "sin el header, 401")
resp = cliente.get("/configuracion?tenant=rapilink",
                   headers={"X-Servicio-Token": "otro-valor"})
comprobar(resp.status_code == 401, "con el header pero el valor equivocado, 401 igual")
resp = cliente.get("/configuracion?tenant=rapilink",
                   headers={"X-Servicio-Token": "secreto-de-prueba"})
comprobar(resp.status_code != 401, "con el token correcto, pasa el gate (puede fallar mas adelante por otra razon, pero no por auth)")

print("\nlas rutas con OTRO mecanismo de autenticacion quedan exentas, token puesto o no")
resp = cliente.get("/salud")
comprobar(resp.status_code == 200, "/salud sigue abierta con el token activo (lo pega el healthcheck, sin credenciales)")
resp = cliente.get("/canales/whatsapp/rapilink?hub.verify_token=x&hub.challenge=y")
comprobar(resp.status_code != 401, "el webhook de WhatsApp no exige el token de servicio (Meta no puede mandarlo)")

api._TOKEN_SERVICIO = None  # no dejar el proceso de test con el gate prendido

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] El token de servicio protege las rutas internas sin romper lo que no debe.")
