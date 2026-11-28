# -*- coding: utf-8 -*-
"""
EL HORARIO DE ATENCION DE LA EMPRESA, YA CALCULADO (09/11/2026).

Un cliente pregunto "hasta que hora laboran?" y el agente contesto "no tengo el horario a
mano": el prompt del router dice que los horarios los resuelve el, pero no habia de donde
sacarlos. El horario NO va en el prompt:

  - lo que varia por empresa es configuracion editable desde la interfaz (CLAUDE.md §3.3), y
    ya existe: el calendario laboral del CRM (Configuracion -> Horario laboral), con horas
    por dia de la semana, zona horaria y festivos. Esto lo LEE; no es una segunda fuente.
  - "¿estan abiertos ahora?" es un calculo (dia, hora, festivo): lo hace el codigo, no el
    modelo (CLAUDE.md §4). Y meterlo en el prompt cambiaria el prefijo cada minuto y rompe
    el cacheo del proveedor (RNF-03).

LA TRAMPA DE ESTE ORIGEN. `GET /api/business-hours/calendar/` CREA el calendario si la
empresa nunca lo configuro: lunes a viernes de 9:00 a 17:00 en UTC (que en Colombia son las
4 a.m. a las 12 m.). Servido tal cual, el agente diria un horario que nadie cargo. Un
calendario que es exactamente ese valor de fabrica se trata como NO CONFIGURADO y se dice
asi: 'no disponible' es honesto, un horario inventado no.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from nucleo.herramientas import http as ejecutor_http
from nucleo.observabilidad.registro import registrar

_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_DIAS_BONITOS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_CAMPOS = tuple((f"{d}_open", f"{d}_close") for d in
                ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))
# Cuantos dias hacia adelante se mira un festivo, y cuantos se le cuentan al modelo.
_DIAS_DE_FESTIVOS = 14
_MAXIMO_DE_FESTIVOS = 5


def _no_disponible(motivo: str) -> dict:
    """Una respuesta que dice QUE no se pudo. Nunca algo con forma de horario."""
    return {"disponible": False, "motivo": motivo}


def _a_hora(valor) -> time | None:
    """'09:00:00' / '09:00' -> time. Cualquier otra cosa, None (el dia queda cerrado)."""
    if not valor:
        return None
    try:
        partes = str(valor).strip().split(":")
        return time(int(partes[0]), int(partes[1]) if len(partes) > 1 else 0)
    except (ValueError, IndexError):
        return None


def _en_texto(t: time) -> str:
    """8:00 a. m. / 6:30 p. m. / 12:00 m."""
    if t.hour == 12 and t.minute == 0:
        return "12:00 m."
    h12 = t.hour % 12 or 12
    return f"{h12}:{t.minute:02d} {'a. m.' if t.hour < 12 else 'p. m.'}"


def _tramo(abre: time | None, cierra: time | None) -> str:
    return f"{_en_texto(abre)} a {_en_texto(cierra)}" if abre and cierra and cierra > abre else "cerrado"


def _tramos(calendario: dict) -> list[tuple[time | None, time | None]]:
    """Los siete dias, lunes a domingo. Un dia con solo una de las dos horas queda cerrado."""
    salida = []
    for campo_abre, campo_cierra in _CAMPOS:
        abre, cierra = _a_hora(calendario.get(campo_abre)), _a_hora(calendario.get(campo_cierra))
        salida.append((abre, cierra) if abre and cierra and cierra > abre else (None, None))
    return salida


def _de_fabrica(calendario: dict, tramos) -> bool:
    """Es el calendario que el CRM fabrica cuando la empresa nunca lo configuro."""
    tz = str(calendario.get("timezone") or "").strip().upper()
    nueve, cinco = time(9, 0), time(17, 0)
    return (tz == "UTC" and str(calendario.get("name") or "").strip() == "Default"
            and not calendario.get("holidays")
            and all(t == (nueve, cinco) for t in tramos[:5])
            and all(t == (None, None) for t in tramos[5:]))


def _festivos(calendario: dict) -> dict[date, str]:
    salida: dict[date, str] = {}
    for f in calendario.get("holidays") or []:
        try:
            salida[date.fromisoformat(str(f.get("date")))] = str(f.get("name") or "").strip()
        except (ValueError, TypeError, AttributeError):
            continue
    return salida


def calcular(calendario: dict, ahora_utc: datetime) -> dict:
    """
    El horario ya digerido, a la hora local de la empresa. Pura: sin red ni reloj propio.

    'abierto_ahora' y 'proxima_apertura' los decide el codigo; el modelo solo los dice.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        zona = ZoneInfo(str(calendario.get("timezone") or ""))
    except (ZoneInfoNotFoundError, ValueError):
        return _no_disponible("el calendario laboral no tiene una zona horaria valida")
    tramos = _tramos(calendario)
    if all(t == (None, None) for t in tramos):
        return _no_disponible("el calendario laboral no tiene ningun dia abierto")
    if _de_fabrica(calendario, tramos):
        return _no_disponible("la empresa todavia no configuro su horario laboral")

    ahora = ahora_utc.astimezone(zona)
    festivos = _festivos(calendario)

    def abierto_el(dia: date) -> tuple[time, time] | None:
        if dia in festivos:
            return None
        abre, cierra = tramos[dia.weekday()]
        return (abre, cierra) if abre else None

    hoy = abierto_el(ahora.date())
    abierto = bool(hoy and hoy[0] <= ahora.time().replace(tzinfo=None) < hoy[1])

    proxima = None
    if not abierto:
        if hoy and ahora.time().replace(tzinfo=None) < hoy[0]:
            proxima = f"hoy a las {_en_texto(hoy[0])}"
        else:
            for i in range(1, 15):
                dia = ahora.date() + timedelta(days=i)
                tramo = abierto_el(dia)
                if tramo:
                    cuando = "mañana" if i == 1 else f"el {_DIAS_BONITOS[dia.weekday()]} {dia.day}"
                    proxima = f"{cuando} a las {_en_texto(tramo[0])}"
                    break

    proximos = sorted((d, n) for d, n in festivos.items()
                      if ahora.date() <= d <= ahora.date() + timedelta(days=_DIAS_DE_FESTIVOS))
    respuesta = {
        "disponible": True,
        # Lista de textos y no un diccionario: la lista blanca por rol filtra tambien las
        # claves de un objeto anidado, y una lista de strings pasa entera.
        "horario": [f"{_DIAS_BONITOS[i]}: {_tramo(*tramos[i])}" for i in range(7)],
        "abierto_ahora": abierto,
    }
    if hoy is None and ahora.date() in festivos:
        respuesta["hoy_es_festivo"] = festivos[ahora.date()] or True
    if proxima:
        respuesta["proxima_apertura"] = proxima
    if proximos:
        respuesta["festivos_proximos"] = [
            f"{_DIAS_BONITOS[d.weekday()]} {d.day}/{d.month}" + (f" ({n})" if n else "")
            for d, n in proximos[:_MAXIMO_DE_FESTIVOS]]
    return respuesta


def horario_de_atencion(herramienta, argumentos, tenant, variables_tenant, catalogo=None,
                        ahora_utc: datetime | None = None) -> dict:
    """Despacho: lee el calendario laboral del CRM y devuelve el horario calculado."""
    if catalogo is None:
        try:
            from nucleo.config import fuente as fuente_config
            catalogo = fuente_config.cargar(tenant).herramientas
        except Exception as e:                                   # noqa: BLE001
            registrar("horario", "no se pudo leer la configuracion del tenant", error=e)
            return _no_disponible("no se pudo leer la configuracion")
    lectora = next((h for h in catalogo if h.nombre == herramienta.calendario_con), None)
    if lectora is None:
        return _no_disponible("la configuracion nombra una herramienta que no existe")
    try:
        crudo = ejecutor_http.ejecutar(lectora, {}, tenant=tenant, variables_tenant=variables_tenant)
    except Exception as e:                                       # noqa: BLE001
        registrar("horario", "no se pudo leer el calendario laboral", error=e)
        return _no_disponible("no se pudo consultar el calendario laboral")
    if not isinstance(crudo, dict):
        return _no_disponible("el calendario laboral llego en una forma inesperada")
    from datetime import timezone
    return calcular(crudo, ahora_utc or datetime.now(timezone.utc))
