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
contextos: list[dict] = []


def enviar(config, tenant, evento, para, contexto, clave):
    enviados.append((evento, para, clave))
    contextos.append(dict(contexto or {}))
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

print("\nla ficha del ISP: se lee solo si hace falta, y no se inventa")
lecturas: list[str] = []


def ficha(servicio):
    lecturas.append(servicio)
    return {"nombre": "BEATRIZ PINZON RUIZ", "telefono": "+57 312 455 8901 / 6051234567"}


def caida(servicio):
    lecturas.append(servicio)
    raise ConnectionError("el ISP no contesta")


def con_servicio(ahora, *, conversacion=None, contexto=None, ficha_de=ficha, telefono=None):
    enviados.clear(); contextos.clear(); lecturas.clear()
    return avisos.avisar(CONFIG, "rapilink", "ticket_creado_cliente", "ticket:wisphub:95001",
                         caso_id="caso-2", telefono_crudo=telefono, contexto=contexto or {},
                         ahora=ahora, conversacion_de=lambda caso: conversacion,
                         ya_escribio=lambda n: False, de_baja=lambda i: False,
                         enviar=enviar, servicio="5832", ficha_de=ficha_de)


NUEVE = datetime(2026, 10, 31, 9, 0, tzinfo=BOGOTA)
r = con_servicio(NUEVE, contexto={"ticket_numero": "95001"})
comprobar(bool(enviados) and enviados[0][1] == "573124558901" and lecturas == ["5832"],
          "sin chat ni telefono, el movil sale de la ficha del servicio (una lectura)",
          f"{enviados} {lecturas}")
comprobar(bool(contextos) and contextos[0].get("cliente_nombre") == "Beatriz"
          and contextos[0].get("cliente_apellidos") == "Pinzon Ruiz"
          and contextos[0].get("cliente_nombre_completo") == "Beatriz Pinzon Ruiz"
          and contextos[0].get("ticket_numero") == "95001",
          "y el nombre se completa desde la ficha, legible", str(contextos))
comprobar(not any("telefono" in c for c in contextos),
          "el telefono NO viaja en los datos de la plantilla", str(contextos))
r = con_servicio(NUEVE, conversacion={"canal": "whatsapp", "usuario_externo": "573155550000"},
                 contexto={"cliente_nombre": "Bea"})
comprobar(lecturas == [] and bool(enviados) and enviados[0][1] == "573155550000"
          and contextos[0]["cliente_nombre"] == "Bea",
          "con chat real y nombre en mano, NO se lee el ISP", f"{lecturas} {contextos}")
r = con_servicio(datetime(2026, 10, 31, 22, 0, tzinfo=BOGOTA))
comprobar(r["motivo"] == "todavia_no" and lecturas == [],
          "fuera del horario no se lee nada", str(r))
r = con_servicio(NUEVE, ficha_de=caida)
comprobar(r.get("enviado") is False and r.get("motivo") == "isp_no_contesta"
          and r.get("reintentar_en") == getattr(avisos, "REINTENTO_ISP_S", -1) and enviados == [],
          "si el ISP no contesta, no sale y pide volver", str(r))
r = con_servicio(NUEVE, ficha_de=lambda s: None)
comprobar(r == {"enviado": False, "motivo": "sin_movil"} and enviados == [],
          "un servicio que no existe no inventa destino", str(r))
r = con_servicio(NUEVE, contexto={"cliente_nombre": "Bea"},
                 conversacion={"canal": "whatsapp", "usuario_externo": "573155550000"},
                 ficha_de=caida)
comprobar(bool(r.get("enviado")) and lecturas == [],
          "si no hace falta la ficha, un ISP caido no frena el aviso", str(r))

print("\nun chat que no es un numero no tapa el movil de la ficha")
r = con_servicio(NUEVE, conversacion={"canal": "whatsapp", "usuario_externo": "CO.1360ABC"})
comprobar(bool(enviados) and enviados[0][1] == "573124558901" and lecturas == ["5832"],
          "con un BSUID en el chat, el aviso sale al movil de la ficha", f"{r} {enviados}")

print("\nel hecho del ticket (avisos.hecho_del_ticket)")
CONF_T = SimpleNamespace(importacion_tickets=SimpleNamespace(proveedor="wisphub"),
                         variables_tenant={"WISPHUB_ID_SERVICIO_INSTALACIONES": "3545"})
ASUNTOS = lambda: {"Sin internet", "Internet lento"}            # noqa: E731
h = avisos.hecho_del_ticket(CONF_T, "95001", leer=lambda n: {"servicio": "5832", "asunto": "Sin internet"},
                            asuntos=ASUNTOS)
comprobar(h == {"clave": "ticket:wisphub:95001", "servicio": "5832",
                "contexto": {"ticket_numero": "95001", "ticket_asunto": "Sin internet"}},
          "el servicio y el asunto salen del ticket del ISP; la clave la arma el motor", str(h))
h = avisos.hecho_del_ticket(CONF_T, "95002", asuntos=ASUNTOS,
                            leer=lambda n: {"servicio": "5832", "asunto": "Andrea Castillo | Villa Maria |"})
comprobar(h.get("contexto") == {"ticket_numero": "95002"},
          "un asunto fuera del catalogo (texto libre, nombre de un prospecto) no viaja", str(h))
h = avisos.hecho_del_ticket(CONF_T, "95003", leer=lambda n: {"servicio": "3545", "asunto": "Sin internet"},
                            asuntos=ASUNTOS)
comprobar(h == {"enviado": False, "motivo": "servicio_sin_titular"},
          "un ticket sobre el cliente ficticio de instalaciones no se avisa a esa ficha", str(h))
comprobar(avisos.hecho_del_ticket(CONF_T, "9", leer=lambda n: None, asuntos=ASUNTOS)
          == {"enviado": False, "motivo": "ticket_no_existe"}, "un ticket que no existe no se avisa")


def isp_caido(n):
    raise ConnectionError("x")


h = avisos.hecho_del_ticket(CONF_T, "9", leer=isp_caido, asuntos=ASUNTOS)
comprobar(h.get("motivo") == "isp_no_contesta" and h.get("reintentar_en") == avisos.REINTENTO_ISP_S,
          "si el ISP no contesta, pide volver", str(h))


def asuntos_caidos():
    raise ConnectionError("x")


h = avisos.hecho_del_ticket(CONF_T, "95001", leer=lambda n: {"servicio": "5832", "asunto": "Sin internet"},
                            asuntos=asuntos_caidos)
comprobar(h.get("contexto") == {"ticket_numero": "95001"},
          "sin el catalogo a mano, el asunto no viaja (no se adivina)", str(h))

print("\nel lector del ticket (importacion_io.ticket_para_aviso)")
from nucleo.seguimiento import importacion_io             # noqa: E402

importacion_io.leer_ticket = lambda config, tenant, n: (
    {"id_ticket": int(n), "asunto": "Sin internet", "servicio": {"id_servicio": 5832, "nombre": "X"},
     "descripcion": "texto libre"} if n == "95001" else {"id_ticket": 1, "servicio": {"id_servicio": 7}})
t = importacion_io.ticket_para_aviso(None, "rapilink", "95001")
comprobar(t == {"servicio": "5832", "asunto": "Sin internet"},
          "devuelve servicio y asunto, nada mas", str(t))
comprobar(importacion_io.ticket_para_aviso(None, "rapilink", "95002") is None,
          "si el ISP devuelve OTRO ticket, no se confia")

print("\nel lector de la ficha (importacion_io.contacto_del_servicio)")
from nucleo.seguimiento import importacion_io             # noqa: E402

FILA = {"id_servicio": 5832, "nombre": "BEATRIZ PINZON", "movil_principal": "3124558901",
        "telefono": "6051234567", "cedula": "1098765432", "password_router": "x"}
OTRO = {"id_servicio": 1, "nombre": "PRIMER CLIENTE", "movil_principal": "3000000001"}
pedidos: list[tuple] = []


def falso_ejecutar(herr, args, tenant, variables_tenant=None):
    pedidos.append((herr.nombre, args))
    if args["id_servicio"] == "5832":
        return {"results": [FILA]}
    if args["id_servicio"] == "7777":
        return {"results": [OTRO]}          # un filtro que el ISP ignoro
    return {"results": []}


importacion_io.ejecutor_http.ejecutar = falso_ejecutar
ESCRIBE = SimpleNamespace(nombre="actualizar_sn_onu", tipo="http", metodo="PUT", solo_lectura=False,
                          filtros_verificados={"id_servicio": "2026-09-28"})
HERR = SimpleNamespace(nombre="consultar_cliente", tipo="http", metodo="GET", solo_lectura=True,
                       filtros_verificados={"id_servicio": "2026-09-10"})
CONF_ISP = SimpleNamespace(herramientas=[ESCRIBE, HERR], variables_tenant={},
                           autenticacion=SimpleNamespace(campo_identidad="movil_principal"))
c = importacion_io.contacto_del_servicio(CONF_ISP, "rapilink", "5832")
comprobar(c == {"nombre": "BEATRIZ PINZON", "telefono": "3124558901"},
          "devuelve nombre y el campo de identidad QUE DECLARA LA EMPRESA, y nada mas", str(c))
comprobar(pedidos == [("consultar_cliente", {"id_servicio": "5832"})],
          "con una herramienta de LECTURA, filtrando por el servicio", str(pedidos))
comprobar(importacion_io.contacto_del_servicio(CONF_ISP, "rapilink", "9999") is None,
          "un servicio que no existe: None")
comprobar(importacion_io.contacto_del_servicio(CONF_ISP, "rapilink", "7777") is None,
          "si el ISP devuelve OTRO cliente (filtro ignorado), no se confia")
sin_herr = SimpleNamespace(herramientas=[SimpleNamespace(nombre="x", tipo="http", metodo="GET",
                                                         solo_lectura=True, filtros_verificados={}),
                                         ESCRIBE],
                           variables_tenant={}, autenticacion=CONF_ISP.autenticacion)
comprobar(importacion_io.contacto_del_servicio(sin_herr, "rapilink", "5832") is None,
          "sin una herramienta de lectura con el filtro verificado, no lee nada")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Un aviso proactivo sale a la persona correcta y a una hora decente.")
