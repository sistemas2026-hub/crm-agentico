# -*- coding: utf-8 -*-
"""
================================================================================
 UN AVISO PROACTIVO DECIDE A QUIEN, CUANDO, Y SI SALE  --  avisos.py (30/10/2026)
================================================================================

nucleo/seguimiento/avisos.py::avisar es la puerta comun de los avisos que
Dexter manda por iniciativa propia (PRD §8.17, Ola 2). Lo que se protege:

  - FUERA DEL HORARIO DE LA EMPRESA NO SALE: el Supervisor publica el dia de
    madrugada, y un WhatsApp a las 3 a. m. no se manda. Se contesta
    'todavia_no' con cuantos segundos faltan, para que quien llama reagende;
  - el chat del caso gana, pero SOLO si es de un canal real: el numero de una
    conversacion del simulador no es un cliente;
  - sin destino, no sale y dice por que;
  - lo demas (interruptor, prueba, baja, plantilla, una sola vez) lo decide
    mensajes_automaticos.enviar, que recibe el numero ya normalizado.

Sin base: las consultas y el envio se inyectan.

    py -3.13 tests/test_avisos_proactivos.py
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.seguimiento import avisos                      # noqa: E402

fallos: list[str] = []
BOGOTA = ZoneInfo("America/Bogota")


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


CONFIG = SimpleNamespace(
    identidad=SimpleNamespace(zona_horaria="America/Bogota"),
    autenticacion=SimpleNamespace(patron_extraccion=r"(?<!\d)3\d{9}(?!\d)", indicativo_pais="57"),
    horario_avisos=SimpleNamespace(desde=7, hasta=20))
enviados: list[tuple] = []


def enviar(config, tenant, evento, para, contexto, clave):
    enviados.append((evento, para, clave))
    return {"enviado": True, "motivo": None}


def llamar(ahora, *, conversacion=None, telefono=None, caso_id="caso-1", de_baja=()):
    enviados.clear()
    return avisos.avisar(CONFIG, "rapilink", "visita_programada", "visita:o-1:2026-10-31",
                         caso_id=caso_id, telefono_crudo=telefono, contexto={"franja": "8 a 12"},
                         ahora=ahora, conversacion_de=lambda caso: conversacion,
                         ya_escribio=lambda n: False, de_baja=lambda i: i in de_baja,
                         enviar=enviar)


print("\nel horario de la empresa")
r = llamar(datetime(2026, 10, 31, 3, 0, tzinfo=BOGOTA), telefono="3001234567")
comprobar(r["motivo"] == "todavia_no" and enviados == [], "a las 3 a. m. no sale", str(r))
comprobar(r.get("reintentar_en") == 4 * 3600, "y dice que vuelva a las 7 (4 h)", str(r))
r = llamar(datetime(2026, 10, 31, 21, 30, tzinfo=BOGOTA), telefono="3001234567")
comprobar(r["motivo"] == "todavia_no" and r.get("reintentar_en") == int(9.5 * 3600),
          "a las 21:30, vuelve a las 7 del dia siguiente (9.5 h)", str(r))
r = llamar(datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA), telefono="3001234567")
comprobar(r["enviado"] and enviados == [("visita_programada", "573001234567", "visita:o-1:2026-10-31")],
          "a las 9 sale, al numero normalizado y con su clave", str(enviados))

print("\na quien")
r = llamar(datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA),
           conversacion={"canal": "whatsapp", "usuario_externo": "573155550000"}, telefono="3001234567")
comprobar(enviados and enviados[0][1] == "573155550000", "el chat real del caso gana", str(enviados))
r = llamar(datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA),
           conversacion={"canal": "whatsapp-simulado", "usuario_externo": "573999999999"}, telefono="3001234567")
comprobar(enviados and enviados[0][1] == "573001234567",
          "un chat del simulador NO es un cliente: se usa el telefono del ISP", str(enviados))
r = llamar(datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA), telefono="fijo 6051234567")
comprobar(r == {"enviado": False, "motivo": "sin_movil"} and enviados == [],
          "sin destino no sale, y dice por que", str(r))

print("\nla baja con un identificador que no es un numero")
BSUID = {"canal": "whatsapp", "usuario_externo": "CO.1360399936298471"}
r = llamar(datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA), conversacion=BSUID, telefono="3001234567",
           de_baja={"CO.1360399936298471"})
comprobar(r == {"enviado": False, "motivo": "de_baja"} and enviados == [],
          "quien se dio de baja desde el chat no recibe el aviso en el movil del ISP", str(r))
r = llamar(datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA), conversacion=BSUID, telefono="3001234567")
comprobar(enviados and enviados[0][1] == "573001234567",
          "sin baja, el BSUID no se usa como numero: sale al movil del ISP", str(enviados))

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Un aviso proactivo sale a la persona correcta y a una hora decente.")
