# -*- coding: utf-8 -*-
"""
================================================================================
 CON QUE HUSO SE SELLA UNA RESPUESTA DEL PROVEEDOR
================================================================================

    py -3.13 tests/test_zona_de_respuestas.py

Por que existe
--------------
WispHub entrega la fecha de cada respuesta como '09/12/2026 09:34:25': hora
local, sin zona. Del otro lado hay una columna con USE_TZ=True y
TIME_ZONE='UTC', que interpreta lo naive como UTC sin preguntarle a nadie. Una
respuesta escrita a las 09:34 de Bogota quedaba archivada como las 09:34 de
Londres.

Medido en produccion el 12/09/2026 sobre dos barridos seguidos: el de las 09:19
de Bogota dejo la respuesta mas nueva sellada a las 09:19 UTC, y el de las 10:20
a las 10:20 UTC. Dos coincidencias al segundo. Una respuesta no puede haberse
creado cinco horas antes del barrido que fue el primero en verla.

La primera correccion sacaba el huso del propio ticket ('fecha_creacion' viene
con offset). Sirve para Colombia y se rompe con horario de verano: un offset es
un numero medido en un instante, no una zona. Por eso la fuente canonica ahora
es 'identidad.zona_horaria', que es IANA, vive en la config por empresa y ya
existia en el esquema.

Lo que se fija aca
------------------
 a) el ticket informa su fecha con offset, y NO es de ahi de donde sale el huso
 b) una respuesta naive se sella con la zona del tenant
 c) una respuesta que ya viene con zona conserva la suya
 d) un tenant con otra zona sella distinto
 e) un tenant CON horario de verano sella distinto en enero y en julio --
    que es exactamente lo que un offset copiado no puede hacer
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.seguimiento import importacion as imp                 # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


class IdentidadFalsa:
    def __init__(self, zona):
        self.zona_horaria = zona


class ConfigFalsa:
    def __init__(self, zona):
        self.identidad = IdentidadFalsa(zona)


def ticket(fecha_creacion="2026-09-10T09:16:37.844072-05:00", created=None):
    return {
        "fecha_creacion": fecha_creacion,
        "respuestas": [{
            "respuesta": "<p>SE VALIDA TICKET</p>",
            "created": created or "09/10/2026 14:15:50",
            "autor": {"id": 1, "username": "jefe.operacion@rapilink-sas",
                      "nombre": "TOMAS ENRIQUE MORENO"},
            "archivos": [],
        }],
    }


def instante(iso):
    return datetime.fromisoformat(iso)


print("=" * 74)
print("  la zona sale de la CONFIG DEL TENANT, no del offset de otra fecha")
print("=" * 74)

# --- (a) el ticket informa un offset, y no es de ahi de donde sale -----------
zona = imp.zona_del_tenant(ConfigFalsa("America/Bogota"), ticket())
revisar(getattr(zona, "key", None) == "America/Bogota",
        "con zona_horaria configurada se usa esa, y es IANA (no un offset)",
        f"devolvio {zona!r}")

# Aunque el ticket mienta con otro offset, manda la config.
zona_pese_al_ticket = imp.zona_del_tenant(
    ConfigFalsa("America/Bogota"), ticket(fecha_creacion="2026-09-10T09:16:37+09:00"))
revisar(getattr(zona_pese_al_ticket, "key", None) == "America/Bogota",
        "y un offset distinto en el ticket NO la pisa",
        f"devolvio {zona_pese_al_ticket!r}")

# --- (b) una respuesta naive se sella con la zona del tenant -----------------
hilo = imp.leer_respuestas(ticket(), imp.zona_del_tenant(
    ConfigFalsa("America/Bogota"), ticket()))
revisar(len(hilo) == 1, "la respuesta entra", f"{len(hilo)}")
sellada = instante(hilo[0]["creada_en_proveedor"])
revisar(sellada.utcoffset().total_seconds() == -5 * 3600,
        "una respuesta naive se sella en la zona del tenant (-05:00 en Bogota)",
        f"quedo {hilo[0]['creada_en_proveedor']}")
revisar(sellada.astimezone(instante("2026-01-01T00:00:00+00:00").tzinfo).hour == 19,
        "y en UTC son las 19:15, no las 14:15",
        f"{sellada.astimezone(instante('2026-01-01T00:00:00+00:00').tzinfo)}")

# --- (c) una respuesta que YA viene con zona conserva la suya ---------------
con_zona = imp.leer_respuestas(
    ticket(created="2026-09-10T14:15:50"),
    imp.zona_del_tenant(ConfigFalsa("America/Bogota"), ticket()))
revisar(con_zona and con_zona[0]["creada_en_proveedor"].endswith("-05:00"),
        "el formato ISO tambien se sella con la zona del tenant",
        f"{con_zona[0]['creada_en_proveedor'] if con_zona else 'vacio'}")

# --- (d) otro tenant, otra zona ---------------------------------------------
hilo_mx = imp.leer_respuestas(ticket(), imp.zona_del_tenant(
    ConfigFalsa("America/Mexico_City"), ticket()))
revisar(instante(hilo_mx[0]["creada_en_proveedor"]).utcoffset().total_seconds()
        == -6 * 3600,
        "otro tenant con otra zona sella distinto (-06:00 en Ciudad de Mexico)",
        f"quedo {hilo_mx[0]['creada_en_proveedor']}")

# --- (e) EL CASO QUE UN OFFSET COPIADO NO PUEDE RESOLVER ---------------------
print()
print("=" * 74)
print("  horario de verano: el mismo tenant sella distinto en enero y en julio")
print("=" * 74)

# Santiago de Chile cambia de huso dos veces al año. Rapilink no lo usa, pero
# el proximo tenant puede, y un offset copiado de otra fecha estaria corrido
# medio año.
config_dst = ConfigFalsa("America/Santiago")
zona_dst = imp.zona_del_tenant(config_dst, ticket())

enero = imp.momento_de_respuesta("01/15/2026 12:00:00", zona_dst)
julio = imp.momento_de_respuesta("07/15/2026 12:00:00", zona_dst)
off_enero = instante(enero).utcoffset().total_seconds() / 3600
off_julio = instante(julio).utcoffset().total_seconds() / 3600

revisar(enero is not None and julio is not None,
        "las dos fechas se sellan", f"{enero!r} / {julio!r}")
revisar(off_enero != off_julio,
        "el mismo tenant sella con offsets DISTINTOS segun la epoca del año",
        f"enero={off_enero:+.0f} julio={off_julio:+.0f} -- si son iguales, se "
        f"esta copiando un offset fijo en vez de resolver la zona")
print(f"       enero -> {enero}   ({off_enero:+.0f})")
print(f"       julio -> {julio}   ({off_julio:+.0f})")

# --- sin zona no se inventa nada --------------------------------------------
print()
print("=" * 74)
print("  sin zona no hay instante")
print("=" * 74)

revisar(imp.momento_de_respuesta("09/10/2026 14:15:50", None) is None,
        "sin zona no se devuelve fecha",
        "un instante sin zona no es un instante")
revisar(imp.zona_del_tenant(ConfigFalsa(""), {"fecha_creacion": "no es fecha"}) is None,
        "sin zona en la config y sin offset en el ticket, no hay huso")

# Config con una zona que esta maquina no conoce: cae al respaldo del ticket.
respaldo = imp.zona_del_tenant(ConfigFalsa("Marte/Olympus"), ticket())
revisar(respaldo is not None and respaldo.utcoffset(None).total_seconds() == -5 * 3600,
        "una zona desconocida cae al offset que informa el ticket, y avisa",
        f"devolvio {respaldo!r}")

hilo_vacio = imp.leer_respuestas(ticket(), None)
revisar(len(hilo_vacio) == 1 and hilo_vacio[0]["creada_en_proveedor"] is None,
        "sin huso la respuesta entra igual, pero SIN fecha",
        "el texto y el autor valen; la fecha ausente se dice como ausente")

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] La zona sale de la config del tenant y resuelve DST por instante.")
print("=" * 74)
