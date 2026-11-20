# -*- coding: utf-8 -*-
"""
EL HORARIO DE ATENCION, CALCULADO POR CODIGO Y SIN INVENTAR (09/11/2026).

Un cliente pregunto "hasta que hora laboran?" y el agente dijo "no tengo el horario a mano".
Ahora lo lee del calendario laboral del CRM. Se afirma sobre el EFECTO, sin modelo ni red:

  1. abierto / cerrado / antes de abrir / despues de cerrar / domingo / festivo, en la hora
     LOCAL de la empresa (no la del servidor);
  2. el calendario que el CRM fabrica cuando la empresa nunca lo configuro (lunes a viernes
     9-17 en UTC) NO se sirve como si fuera un horario: se dice 'no disponible';
  3. todo lo que falla (red, forma rara, zona mala) es 'no disponible', nunca un horario;
  4. la config: la lectora no la ve ningun agente y la herramienta publica si la ven los cuatro.

    py -3.13 tests/test_horario_de_atencion.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.config import cargar_config  # noqa: E402
from nucleo.herramientas import horario, http as ejecutor_http  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


def calendario(**cambios):
    dias = ("monday", "tuesday", "wednesday", "thursday", "friday")
    base = {"id": "x", "name": "Rapilink", "timezone": "America/Bogota", "is_default": True,
            "holidays": [], "saturday_open": "08:00:00", "saturday_close": "13:00:00",
            "sunday_open": None, "sunday_close": None}
    for d in dias:
        base[f"{d}_open"], base[f"{d}_close"] = "08:00:00", "18:00:00"
    base.update(cambios)
    return base


def a_las(dia, hora_bogota):
    """Un instante UTC que en Bogota (UTC-5) es esa fecha y hora de noviembre de 2026."""
    h, m = hora_bogota
    return datetime(2026, 11, dia, tzinfo=timezone.utc) + timedelta(hours=h + 5, minutes=m)


# 9/11/2026 es lunes.
print("\n1. abierto o cerrado, en la hora de la empresa")
r = horario.calcular(calendario(), a_las(9, (10, 0)))
afirmar(r["disponible"] and r["abierto_ahora"] is True, "lunes 10:00 de Bogota: abierto")
afirmar("proxima_apertura" not in r, "abierto: no hay 'proxima apertura'")
afirmar(r["horario"][0] == "lunes: 8:00 a. m. a 6:00 p. m." and r["horario"][6] == "domingo: cerrado"
        and r["horario"][5] == "sábado: 8:00 a. m. a 1:00 p. m.", "los siete dias, en texto")
r = horario.calcular(calendario(), a_las(9, (19, 30)))
afirmar(r["abierto_ahora"] is False and r["proxima_apertura"] == "mañana a las 8:00 a. m.",
        "lunes 19:30: cerrado, abre mañana a las 8:00 a. m.")
r = horario.calcular(calendario(), a_las(9, (6, 0)))
afirmar(r["abierto_ahora"] is False and r["proxima_apertura"] == "hoy a las 8:00 a. m.",
        "lunes 6:00: cerrado, abre hoy a las 8:00 a. m.")
r = horario.calcular(calendario(), a_las(14, (20, 0)))
afirmar(r["abierto_ahora"] is False and r["proxima_apertura"] == "el lunes 16 a las 8:00 a. m.",
        "sabado 20:00: cerrado, abre el lunes 16 (el domingo no atienden)")
afirmar(horario.calcular(calendario(), a_las(10, (18, 0)))["abierto_ahora"] is False,
        "justo a la hora de cierre ya esta cerrado (el cierre no se incluye)")
afirmar(horario.calcular(calendario(), a_las(10, (8, 0)))["abierto_ahora"] is True,
        "justo a la hora de apertura ya esta abierto")
# La HORA LOCAL manda, no la del servidor: las 14:00 UTC del lunes son las 9:00 en Bogota.
afirmar(horario.calcular(calendario(), datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc))["abierto_ahora"] is True,
        "14:00 UTC = 9:00 en Bogota: abierto (se mide en la zona de la empresa)")
afirmar(horario.calcular(calendario(), datetime(2026, 11, 9, 4, 0, tzinfo=timezone.utc))["abierto_ahora"] is False,
        "4:00 UTC = 23:00 del domingo en Bogota: cerrado")

print("\n2. festivos")
fest = calendario(holidays=[{"id": "1", "date": "2026-11-16", "name": "Festivo"},
                            {"id": "2", "date": "2026-11-09", "name": "Dia de la empresa"}])
r = horario.calcular(fest, a_las(9, (10, 0)))
afirmar(r["abierto_ahora"] is False and r.get("hoy_es_festivo") == "Dia de la empresa",
        "un festivo cierra el dia aunque el calendario diga que abre")
afirmar(r["proxima_apertura"] == "mañana a las 8:00 a. m.", "y la proxima apertura es la del siguiente dia abierto")
afirmar(any("16/11" in f for f in r.get("festivos_proximos", [])), "avisa los festivos de las proximas dos semanas")
r = horario.calcular(calendario(holidays=[{"id": "1", "date": "2026-11-10", "name": "X"}]), a_las(9, (19, 0)))
afirmar(r["proxima_apertura"] == "el miércoles 11 a las 8:00 a. m.", "salta el festivo al decir cuando vuelve a abrir")

print("\n3. el calendario de fabrica NO es un horario")
fabrica = calendario(name="Default", timezone="UTC", saturday_open=None, saturday_close=None)
for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
    fabrica[f"{d}_open"], fabrica[f"{d}_close"] = "09:00:00", "17:00:00"
r = horario.calcular(fabrica, a_las(9, (10, 0)))
afirmar(r["disponible"] is False and "horario" not in r and "abierto_ahora" not in r,
        "lo que el CRM fabrica solo (lun-vie 9-17 UTC) se dice 'no disponible', no se sirve")
r = horario.calcular(dict(fabrica, timezone="America/Bogota"), a_las(9, (10, 0)))
afirmar(r["disponible"] is True, "la misma jornada pero con zona de Bogota SI es un horario cargado")
r = horario.calcular(dict(fabrica, holidays=[{"id": "1", "date": "2026-12-25", "name": "Navidad"}]), a_las(9, (10, 0)))
afirmar(r["disponible"] is True, "con un festivo cargado ya alguien lo toco: es un horario")

print("\n4. lo que falla es 'no disponible', nunca un horario")
afirmar(horario.calcular(calendario(timezone="Marte/Olimpo"), a_las(9, (10, 0)))["disponible"] is False,
        "zona horaria invalida")
cerrado = calendario(saturday_open=None, saturday_close=None)
for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
    cerrado[f"{d}_open"] = cerrado[f"{d}_close"] = None
afirmar(horario.calcular(cerrado, a_las(9, (10, 0)))["disponible"] is False, "ningun dia abierto")
afirmar(horario.calcular(calendario(monday_close="07:00:00"), a_las(9, (10, 0)))["horario"][0] == "lunes: cerrado",
        "un dia con cierre antes de la apertura queda cerrado, no al reves")
afirmar(horario.calcular(calendario(monday_close=None), a_las(9, (10, 0)))["horario"][0] == "lunes: cerrado",
        "un dia con solo una de las dos horas queda cerrado")


class _Lectora:
    nombre = "leer_calendario_laboral"


class _Herr:
    calendario_con = "leer_calendario_laboral"


def con_http(resultado):
    original = ejecutor_http.ejecutar

    def falso(h, args, *a, **k):
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    ejecutor_http.ejecutar = falso
    try:
        return horario.horario_de_atencion(_Herr(), {}, "t", {}, catalogo=[_Lectora()],
                                           ahora_utc=a_las(9, (10, 0)))
    finally:
        ejecutor_http.ejecutar = original


afirmar(con_http(calendario())["abierto_ahora"] is True, "el despacho lee el calendario y lo calcula")
afirmar(con_http(RuntimeError("CRM caido"))["disponible"] is False, "el CRM caido: 'no disponible'")
afirmar(con_http(["no", "es", "un", "dict"])["disponible"] is False, "una forma inesperada: 'no disponible'")
afirmar(horario.horario_de_atencion(_Herr(), {}, "t", {}, catalogo=[])["disponible"] is False,
        "la config nombra una lectora que no existe: 'no disponible'")

print("\n5. la config de Rapilink")
RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
cfg = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
por = {h.nombre: h for h in cfg.herramientas}
h = por.get("consultar_horario_de_atencion")
afirmar(h is not None and h.entrega_horario_de_atencion and h.tipo == "interno" and h.solo_lectura,
        "la herramienta existe, es interna y de solo lectura")
afirmar(h is not None and h.calendario_con == "leer_calendario_laboral" and "leer_calendario_laboral" in por,
        "nombra a una lectora que existe")
afirmar(not any("leer_calendario_laboral" in r.puede_consultar for r in cfg.roles.values()),
        "ningun agente ve la lectora directamente")
cuatro = {"cliente_final", "facturacion_cliente", "soporte_tecnico_cliente", "ventas"}
afirmar({n for n, r in cfg.roles.items() if "consultar_horario_de_atencion" in r.puede_consultar} == cuatro,
        "la ven exactamente los cuatro roles de cliente")
afirmar(all("horario" in cfg.roles[n].campos_permitidos["consultar_horario_de_atencion"] for n in cuatro),
        "cada uno deja pasar el campo 'horario'")
afirmar("consultar_horario_de_atencion" in cfg.roles["cliente_final"].descripcion
        and "nunca prometas volver" in cfg.roles["cliente_final"].descripcion,
        "el router sabe llamarla y no promete 'te digo' sin poder cumplirlo")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] El horario de atencion se calcula por codigo y no se inventa.")
