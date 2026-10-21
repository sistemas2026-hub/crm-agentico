# -*- coding: utf-8 -*-
"""
================================================================================
 EL HORARIO DE LAS CUADRILLAS  --  21/10/2026
================================================================================

Pedido del usuario, al ver el calendario por defecto de la empresa (UTC, 09 a
17, sin feriados): «ese horario seria de CRM atencion al cliente». Lo es: ese
calendario cuenta los objetivos de respuesta de los tickets, y el Supervisor lo
estaba usando para saber cuando trabajan las cuadrillas
(`operaciones.capacidad.jornada_de`). Dos usos con horarios distintos no pueden
compartir una fila.

QUE ES
------
Un `BusinessCalendar` PROPIO de la operacion de campo --no el por defecto--,
enlazado desde `ConfiguracionDeReparto.calendario_de_cuadrillas`, con la hora
de corte al lado. Se reusa el calendario (dias, zona horaria, feriados) en vez
de inventar otro formato: `capacidad.jornada_de` ya sabe leerlo.

QUIEN LO USA
------------
`capacidad.jornada_de`: si la empresa lo cargo, la ventana de campo sale de
aca. Si no lo cargo, lo que ya corria (la madrugada, la capacidad de la
programacion) sigue con el calendario por defecto, como hasta hoy; y lo que el
Supervisor hace SOLO (armar cada hora, crear ordenes, publicar) no corre y lo
dice (`solo_de_cuadrillas=True`). Decision del usuario: sin horario de
cuadrillas, el Supervisor no arma ni despacha.

Ficha: SPEC/objetivos/supervisor-arma-la-jornada.md (decision del 21/10).
================================================================================
"""

from __future__ import annotations

import datetime as _dt
from zoneinfo import available_timezones

from django.db import transaction

#: Los dias como los ve la pantalla, y la columna del calendario de cada uno.
DIAS = (("lunes", "monday"), ("martes", "tuesday"), ("miercoles", "wednesday"),
        ("jueves", "thursday"), ("viernes", "friday"), ("sabado", "saturday"),
        ("domingo", "sunday"))

#: El nombre del calendario: se ve en el admin y distingue esta fila del
#: calendario de atencion al cliente.
NOMBRE = "Cuadrillas"

MAX_FERIADOS = 60


class ErrorHorario(ValueError):
    """El horario no se puede guardar. El mensaje es para quien lo edita."""


def calendario_de_cuadrillas(org):
    """El calendario de las cuadrillas de esta empresa, o None si no lo cargo.

    Solo uno de ESTA empresa: una fila de configuracion apuntando a otro org
    (no deberia pasar, pero `campo_*` no tiene RLS) se trata como ausente.
    """
    from campo.cuadrillas import ConfiguracionDeReparto

    fila = (ConfiguracionDeReparto.objects.filter(org=org)
            .select_related("calendario_de_cuadrillas").first())
    cal = getattr(fila, "calendario_de_cuadrillas", None)
    if cal is None or cal.org_id != getattr(org, "id", org):
        return None
    return cal


def _hora(valor, que: str):
    if valor in (None, ""):
        return None
    if isinstance(valor, _dt.time):
        return valor
    try:
        return _dt.time.fromisoformat(str(valor).strip()[:5])
    except ValueError:
        raise ErrorHorario(f"{que}: la hora va como HH:MM.")


def leer(org) -> dict:
    """Lo que muestra la pantalla. `configurado` dice si existe."""
    from campo.cuadrillas import configuracion_de_reparto

    cal = calendario_de_cuadrillas(org)
    config = configuracion_de_reparto(org)
    corte = getattr(config, "hora_de_corte", None)
    salida = {
        "configurado": cal is not None,
        "zona_horaria": cal.timezone if cal else "",
        #  La de la empresa (`Org.timezone`), para que la pantalla avise si no
        #  coinciden: el dia de la empresa y la hora de las cuadrillas en dos
        #  relojes distintos ya costo un hallazgo (17/10/2026).
        "zona_de_la_empresa": getattr(org, "timezone", "") or "UTC",
        "dias": {},
        "feriados": [],
        "hora_de_corte": corte.strftime("%H:%M") if corte else "",
    }
    for dia, col in DIAS:
        abre = getattr(cal, f"{col}_open", None) if cal else None
        cierra = getattr(cal, f"{col}_close", None) if cal else None
        salida["dias"][dia] = ({"abre": abre.strftime("%H:%M"),
                                "cierra": cierra.strftime("%H:%M")}
                               if abre and cierra else None)
    if cal is not None:
        salida["feriados"] = [{"fecha": h.date.isoformat(), "nombre": h.name}
                              for h in cal.holidays.order_by("date")]
    return salida


def _feriados(valor) -> list[tuple[_dt.date, str]]:
    if valor in (None, ""):
        return []
    if not isinstance(valor, list):
        raise ErrorHorario("Los feriados van como una lista.")
    salida, vistos = [], set()
    for f in valor:
        f = f if isinstance(f, dict) else {}
        try:
            fecha = _dt.date.fromisoformat(str(f.get("fecha") or "").strip())
        except ValueError:
            raise ErrorHorario("Un feriado tiene la fecha mal escrita "
                               "(va AAAA-MM-DD).")
        if fecha in vistos:
            continue
        vistos.add(fecha)
        nombre = " ".join(str(f.get("nombre") or "").split())[:100] or "Feriado"
        salida.append((fecha, nombre))
    if len(salida) > MAX_FERIADOS:
        raise ErrorHorario(f"Pasan de {MAX_FERIADOS} feriados.")
    return salida


def guardar(org, datos: dict) -> dict:
    """Reemplaza el horario entero: dias, zona, feriados y hora de corte.

    ENTERO Y NO POR PARTES: la pantalla manda el estado completo, y un merge
    haria que desmarcar un dia no lo cerrara. Todo se valida ANTES de escribir:
    un dia mal escrito no deja el horario a medias.
    """
    from business_hours.models import BusinessCalendar, BusinessHoliday
    from campo.cuadrillas import ConfiguracionDeReparto

    datos = datos if isinstance(datos, dict) else {}
    zona = str(datos.get("zona_horaria") or "").strip()
    if zona not in available_timezones():
        raise ErrorHorario("Elegi la zona horaria de las cuadrillas "
                           "(por ejemplo America/Bogota).")

    dias = datos.get("dias") if isinstance(datos.get("dias"), dict) else {}
    ventanas = {}
    for dia, col in DIAS:
        d = dias.get(dia)
        if not d:
            ventanas[col] = (None, None)
            continue
        abre = _hora((d or {}).get("abre"), f"El {dia}")
        cierra = _hora((d or {}).get("cierra"), f"El {dia}")
        if abre is None or cierra is None:
            raise ErrorHorario(f"El {dia} necesita la hora en que abre y la "
                               "hora en que cierra, o quedar cerrado.")
        if cierra <= abre:
            #  Lo mismo que `capacidad.jornada_de`: una jornada que cierra
            #  antes de abrir no se arregla suponiendo un turno de noche.
            raise ErrorHorario(f"El {dia} cierra antes de abrir.")
        ventanas[col] = (abre, cierra)
    if not any(a for a, _ in ventanas.values()):
        raise ErrorHorario("Las cuadrillas tienen que trabajar al menos un dia.")

    corte = _hora(datos.get("hora_de_corte"), "La hora de corte")
    feriados = _feriados(datos.get("feriados"))

    with transaction.atomic():
        config, _ = ConfiguracionDeReparto.objects.get_or_create(org=org)
        cal = calendario_de_cuadrillas(org)
        if cal is None:
            #  is_default=False A PROPOSITO: el por defecto es el de atencion
            #  al cliente, y la base admite uno solo por empresa.
            cal = BusinessCalendar.objects.create(
                org=org, name=NOMBRE, is_default=False, timezone=zona)
        cal.timezone = zona
        for col, (abre, cierra) in ventanas.items():
            setattr(cal, f"{col}_open", abre)
            setattr(cal, f"{col}_close", cierra)
        cal.save()
        cal.holidays.all().delete()
        BusinessHoliday.objects.bulk_create([
            BusinessHoliday(calendar=cal, org=org, date=fecha, name=nombre)
            for fecha, nombre in feriados])
        config.calendario_de_cuadrillas = cal
        config.hora_de_corte = corte
        config.save(update_fields=["calendario_de_cuadrillas", "hora_de_corte"])
    return leer(org)
