# -*- coding: utf-8 -*-
"""
================================================================================
 A QUIEN SE LE AVISA UNA CAIDA DE RED  --  aviso_de_caida.py (30/10/2026)
================================================================================

PRD §8.17, Ola 2, punto 4: cuando se cae un PON, cientos de clientes escriben a
la vez "no tengo internet". Avisarles primero es la reduccion de volumen mas
grande disponible -- y la que mas dano hace si se equivoca de gente. Lo que se
protege:

  - SOLO LOS QUE CAYERON JUNTOS: un puerto acumula equipos en LOS desde hace
    meses (clientes que se fueron; medido el 21/08/2026: 10 de 17). Avisarle a
    un ex cliente "estamos arreglando su servicio" es mentirle. Se toma el
    grupo de caidas cercanas entre si, no todo lo que esta en LOS;
  - solo clientes en un estado que la empresa declaro (un suspendido no tiene
    servicio que restablecer); sin esa declaracion, no se arma nada;
  - el serial se cruza en sus dos formas (corta y hexadecimal);
  - el envio va por lotes, una vez por (situacion, servicio), y fuera del
    horario espera entero; un ISP que no contesta deja al servicio pendiente.

Sin red: SmartOLT, el padron, la ficha y el envio se inyectan.

    py -3.13 tests/test_aviso_de_caida.py
================================================================================
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.herramientas import http as ejecutor_http    # noqa: E402
from nucleo.seguimiento import aviso_de_caida, buscar_cliente  # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


def onu(sn, cuando, status="los"):
    return {"sn": sn, "status": status, "last_status_change": cuando}


# Un puerto real: 4 se cayeron juntos hoy, 2 llevan meses muertos, 1 se cayo
# solo mas tarde (un cliente que desenchufo), 1 esta en linea.
PUERTO = [
    onu("HWTC00000001", "2026-10-30 07:16:44.419668"),
    onu("HWTC00000002", "2026-10-30 07:16:44.419668"),
    onu("HWTC00000003", "2026-10-30 07:17:02"),
    onu("HWTC00000004", "2026-10-30 07:21:10"),
    onu("HWTC00000005", "2026-03-02 11:00:00"),
    onu("HWTC00000006", "2026-06-15 18:40:00"),
    onu("HWTC00000007", "2026-10-30 09:55:00"),
    onu("HWTC00000008", "2026-10-30 07:16:44", status="online"),
]

print("\nel grupo de la falla")
grupo, desde = aviso_de_caida.grupo_de_la_falla(PUERTO, ventana_minutos=20)
comprobar(sorted(sn for sn, _ in grupo) == ["HWTC00000001", "HWTC00000002", "HWTC00000003", "HWTC00000004"],
          "solo los que cayeron juntos: ni los muertos de meses ni el que cayo solo despues", str(grupo))
comprobar(desde == "2026-10-30 07:16:44", "desde la primera caida del grupo", str(desde))
comprobar("HWTC00000008" not in grupo, "uno en linea no es parte de la falla")
grupo, _ = aviso_de_caida.grupo_de_la_falla([onu("A1", "2026-10-30 07:00:00"),
                                             onu("A2", "2026-10-30 07:05:00"),
                                             onu("B1", "2026-10-30 10:00:00"),
                                             onu("B2", "2026-10-30 10:01:00")], ventana_minutos=20)
comprobar(sorted(sn for sn, _ in grupo) == ["B1", "B2"], "a igual tamaño gana el grupo mas reciente",
          str(grupo))
comprobar(dict(grupo)["B1"] == "2026-10-30 10:00:00", "cada equipo con la hora en que cayo", str(grupo))
grupo, _ = aviso_de_caida.grupo_de_la_falla([onu("V1", "2026-09-01 07:00:00"),
                                             onu("V2", "2026-09-01 07:00:00"),
                                             onu("V3", "2026-09-01 07:01:00"),
                                             onu("V4", "2026-09-01 07:02:00"),
                                             onu("N1", "2026-10-30 10:00:00"),
                                             onu("N2", "2026-10-30 10:00:30")], ventana_minutos=20, minimo=2)
comprobar(sorted(sn for sn, _ in grupo) == ["N1", "N2"],
          "un corte viejo con mas equipos muertos NO le gana a la falla de hoy", str(grupo))
comprobar(aviso_de_caida.grupo_de_la_falla([onu("X", "basura"), onu("Y", "")], 20) == ([], None),
          "sin horas legibles no hay grupo")

print("\nel padron por serial (buscar_cliente)")
filas = [{"servicio": "101", "nombre": "A", "estado": "Activo", "_sn": "HWTC00000001"},
         {"servicio": "102", "nombre": "B", "estado": "Activo",
          "_sn": str(ejecutor_http._gpon_hex("HWTC00000002") or "").upper()},
         {"servicio": "103", "nombre": "C", "estado": "Suspendido", "_sn": "HWTC00000003"},
         {"servicio": "104", "nombre": "D", "estado": "Activo", "_sn": ""}]
CONFIG = SimpleNamespace(
    tickets_desde_dexter=SimpleNamespace(padron_vigencia_horas=6),
    aviso_de_caida=SimpleNamespace(estados_que_se_avisan=["Activo"], ventana_misma_falla_minutos=20,
                                   minimo_equipos=2, lote=25),
    herramientas=[SimpleNamespace(nombre="consultar_incidente_red", detecta_incidente=True)],
    variables_tenant={"WISPHUB_ID_SERVICIO_INSTALACIONES": "3545"})
buscar_cliente._PADRONES["prueba"] = {"filas": filas, "cuando": time.monotonic()}
indice = buscar_cliente.padron_por_serial(CONFIG, "prueba")
comprobar(indice is not None and indice.get("HWTC00000001", {}).get("servicio") == "101",
          "el serial corto encuentra su servicio", str(indice and list(indice)[:4]))
comprobar(aviso_de_caida._buscar(indice, "HWTC00000002") is not None
          and aviso_de_caida._buscar(indice, "HWTC00000002")["servicio"] == "102",
          "un serial corto encuentra al cliente guardado en hexadecimal")
buscar_cliente._PADRONES.pop("prueba")

print("\nlos afectados")
buscar_cliente._PADRONES["prueba"] = {"filas": filas, "cuando": time.monotonic()}
r = aviso_de_caida.afectados(CONFIG, "prueba", "3", "2", "11", leer=lambda: PUERTO)
comprobar(r.get("cayo") == {"101": "2026-10-30 07:16:44", "102": "2026-10-30 07:16:44"},
          "con la hora en que cayo cada uno (para la clave)", str(r.get("cayo")))
comprobar(r.get("servicios") == ["101", "102"],
          "avisa a los clientes activos del grupo, y a nadie mas", str(r))
comprobar(r.get("equipos_en_falla") == 4 and r.get("fuera_de_estado") == 1 and r.get("sin_cliente") == 1,
          "y cuenta lo que deja afuera: un suspendido, un equipo sin cliente", str(r))
comprobar("_sn" not in str(r) and "HWTC" not in str(r), "ningun serial sale en la respuesta", str(r))
r = aviso_de_caida.afectados(CONFIG, "prueba", "3", "2", "11",
                             leer=lambda: [onu("HWTC00000001", "2026-10-30 07:16:44")])
comprobar(r.get("servicios") == [] and r.get("motivo") == "sin_falla_comun",
          "un solo equipo caido no es una caida masiva", str(r))
buscar_cliente._PADRONES.pop("prueba")
buscar_cliente._CARGANDO.add("prueba")
r = aviso_de_caida.afectados(CONFIG, "prueba", "3", "2", "11", leer=lambda: PUERTO)
comprobar(r == {"cargando": True}, "sin padron todavia, dice 'cargando' en vez de inventar", str(r))
buscar_cliente._CARGANDO.discard("prueba")
sin_estados = SimpleNamespace(**{**vars(CONFIG), "aviso_de_caida": SimpleNamespace(
    estados_que_se_avisan=[], ventana_misma_falla_minutos=20, minimo_equipos=2, lote=25)})
try:
    aviso_de_caida.afectados(sin_estados, "prueba", "3", "2", "11", leer=lambda: PUERTO)
    comprobar(False, "sin estados declarados no se arma nada")
except aviso_de_caida.CaidaNoAvisable as e:
    comprobar(e.codigo == "NO_CONFIGURADO", "sin estados declarados no se arma nada", e.codigo)
sin_herr = SimpleNamespace(**{**vars(CONFIG), "herramientas": []})
try:
    aviso_de_caida.afectados(sin_herr, "prueba", "3", "2", "11")
    comprobar(False, "sin herramienta optica no se lee nada")
except aviso_de_caida.CaidaNoAvisable as e:
    comprobar(e.codigo == "NO_CONFIGURADO", "sin herramienta optica no se lee nada", e.codigo)

print("\nel lote")
pedidos: list[str] = []


def uno(respuestas):
    def avisar_uno(servicio):
        pedidos.append(servicio)
        return respuestas.get(servicio, {"enviado": True, "motivo": None})
    return avisar_uno


pedidos.clear()
r = aviso_de_caida.avisar_lote(["101", "102", "103"], uno({
    "102": {"enviado": False, "motivo": "de_baja"},
    "103": {"enviado": False, "motivo": "isp_no_contesta", "reintentar_en": 900}}))
comprobar(r["enviados"] == 1 and r["motivos"] == {"de_baja": 1, "isp_no_contesta": 1},
          "cuenta lo enviado y por que no salio el resto", str(r))
comprobar(r["pendientes"] == ["103"] and r["reintentar_en"] == 900,
          "el que el ISP no contesto queda pendiente, con cuando volver", str(r))
pedidos.clear()
r = aviso_de_caida.avisar_lote(["101", "102"], uno({
    "101": {"enviado": False, "motivo": "todavia_no", "reintentar_en": 3600}}))
comprobar(pedidos == ["101"] and r["pendientes"] == ["101", "102"] and r["reintentar_en"] == 3600,
          "fuera del horario el lote entero espera, sin preguntar por los demas", str(r))
comprobar(aviso_de_caida.clave("101", "2026-10-30 07:16:44") == "caida:101:2026-10-30 07:16:44",
          "la clave es el servicio y la hora en que cayo SU equipo: la arma el motor")
pedidos.clear()
r = aviso_de_caida.avisar_lote(["101"], uno({"101": {"enviado": False, "motivo": "meta_no_contesta"}}))
comprobar(r["pendientes"] == ["101"] and r["reintentar_en"] == 300,
          "si Meta no contesta, el cliente queda pendiente en vez de perder el aviso", str(r))

print("\nlo que el padron no puede decidir")
filas2 = [{"servicio": "3545", "nombre": "INSTALACIONES NUEVAS", "estado": "Activo", "_sn": "HWTC00000001"},
          {"servicio": "201", "nombre": "A", "estado": "Activo", "_sn": "HWTC00000002"},
          {"servicio": "202", "nombre": "B", "estado": "Activo", "_sn": "HWTC00000002"},
          {"servicio": "203", "nombre": "C", "estado": "Activo", "_sn": "HWTC00000003"}]
buscar_cliente._PADRONES["prueba"] = {"filas": filas2, "cuando": time.monotonic()}
r = aviso_de_caida.afectados(CONFIG, "prueba", "3", "2", "11", leer=lambda: PUERTO)
comprobar(r.get("servicios") == ["203"] and r.get("sin_cliente") == 3,
          "ni el cliente ficticio de instalaciones ni un equipo que figura en dos fichas", str(r))
buscar_cliente._PADRONES.pop("prueba")

print("\nsi el aviso puede salir, ANTES de aprobar (mensajes_automaticos.listo)")
from nucleo.seguimiento import mensajes_automaticos as ma  # noqa: E402

aprobadas = [{"nombre": "falla_en_la_red", "estado": "APPROVED", "variables": 1}]
ma.whatsapp.activo = lambda config: True
ma.whatsapp.plantillas_aprobadas = lambda config, tenant: aprobadas


def conf_mensajes(**m):
    base = {"activo": True, "plantilla": "falla_en_la_red", "datos": ["cliente_nombre"], "solo_a": []}
    return SimpleNamespace(mensajes_automaticos={"caida_masiva": SimpleNamespace(**{**base, **m})},
                           plantillas_desactivadas=[])


comprobar(ma.listo(conf_mensajes(), "t", "caida_masiva") is None, "encendido y aprobado: listo")
comprobar(ma.listo(conf_mensajes(activo=False), "t", "caida_masiva") == "apagado", "apagado lo dice")
comprobar(ma.listo(SimpleNamespace(mensajes_automaticos={}, plantillas_desactivadas=[]), "t",
                   "caida_masiva") == "apagado", "sin configurar es apagado")
comprobar(ma.listo(conf_mensajes(plantilla="otra"), "t", "caida_masiva") == "plantilla_no_aprobada",
          "una plantilla sin aprobar lo dice")
comprobar(ma.listo(conf_mensajes(datos=["cliente_nombre", "empresa"]), "t", "caida_masiva")
          == "plantilla_no_coincide", "una plantilla con otra cantidad de datos lo dice")
ma.whatsapp.activo = lambda config: False
comprobar(ma.listo(conf_mensajes(), "t", "caida_masiva") == "canal_apagado", "sin WhatsApp lo dice")
ma.whatsapp.activo = lambda config: True
comprobar(ma.en_prueba(conf_mensajes(solo_a=["573001234567"]), "caida_masiva")
          and not ma.en_prueba(conf_mensajes(), "caida_masiva"), "y si esta en modo prueba")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Una caida se avisa a los que cayeron juntos, y a nadie mas.")
