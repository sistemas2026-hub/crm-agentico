"""El embudo de ventas del ISP, calculado (12/11/2026).

POR QUE EXISTE
--------------
La auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md, «Ventas y
Facturacion», item 10) lo encontro asi: el dueño necesita ver cuantos
prospectos llegan a cada paso -- link generado, formulario abierto, enviado,
aprobado, instalado -- y esa pantalla no existia en ningun lado, con todos los
datos ya guardados en `SolicitudServicio` y en la orden de campo.

EL MODELO COMPONE, EL CODIGO CALCULA (PRD §12.5)
-----------------------------------------------
Cada numero de esta pantalla sale de aca: conteos, tasas de paso y medianas.
Ninguno se le pide a un modelo, y la pantalla no suma ni divide: representa.

QUE ES UNA ETAPA, CON EXACTITUD
-------------------------------
Se mide una COHORTE: las solicitudes cuyo link se genero dentro del periodo, y
hasta donde llego cada una HASTA HOY. No es "cuantas se enviaron en el
periodo": con esa definicion una tasa de paso puede superar el 100 % (se
envian en noviembre links de octubre) y deja de significar algo.

  links        la solicitud existe (el asistente genero el link)
  abiertos     `abierta_en` no es nulo
  enviadas     `enviada_en` no es nulo
  aprobadas    estado = aprobada
  instaladas   la aprobada tiene una orden de campo CERRADA unida por la unica
               cadena que existe hoy: `solicitud.ticket_wisphub` ->
               `Case.external_ticket_id` (el importador la trae como caso) ->
               `OrdenTrabajo(origen_sistema='crm', origen_ref=<id del caso>)`.
               Una aprobada sin ticket, o cuyo ticket todavia no tiene caso,
               NO cuenta como instalada y NO se inventa: se informa aparte
               (`instalacion_sin_dato`), porque ahi la verdad es "no sabemos".

QUE QUEDA FUERA, Y POR QUE (dicho, no escondido)
------------------------------------------------
  chats de venta   las conversaciones viven en el motor y no hay un endpoint que
                   las cuente por rol: el listado de la Bandeja cuesta cuatro
                   subconsultas por conversacion y trae el rol ACTUAL, no "quien
                   la atendio". Contar sobre eso seria un numero que parece
                   dato. Hace falta una consulta propia en el motor.
  activas          saber si el servicio quedo activo en WispHub es preguntarle a
                   WispHub, cliente por cliente; no hay una lectura barata y ya
                   verificada para eso.

Las dos viajan en la respuesta como `null` con su motivo, para que la pantalla
diga "sin dato" en vez de dibujar un cero.

AISLAMIENTO
-----------
Todo filtra por `org` de forma explicita, ademas de la politica RLS: si la
politica faltara en alguna de estas tablas, el WHERE sigue acotando. Sin
organizacion no hay embudo -- la vista lo exige antes de llegar aca.
"""

from __future__ import annotations

import statistics
from datetime import timedelta

from django.utils import timezone

#: Las etapas, en orden. La pantalla las dibuja en este orden y no en otro.
ETAPAS = ("chats", "links", "abiertos", "enviadas", "aprobadas", "instaladas", "activas")

#: Las que no se pueden medir hoy, con el porque que ve la persona.
ETAPAS_SIN_DATO = {
    "chats": ("Las conversaciones de venta viven en el motor y todavía no hay "
              "una consulta que las cuente por agente."),
    "activas": ("Saber si el servicio quedó activo exige preguntarle al sistema "
                "del ISP cliente por cliente; no hay una lectura barata y verificada."),
}

#: Cuantas filas detenidas se devuelven por etapa. El total viaja aparte.
MAXIMO_DETENIDAS = 50
#: Cuantos motivos literales de caida se devuelven.
MAXIMO_MOTIVOS = 20


def _horas(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


def _mediana(muestras: list[float]) -> dict:
    """La mediana en horas, con cuantas muestras la sostienen.

    Con cero muestras es `null`, no cero: "no hay datos" y "tardo cero horas"
    son dos afirmaciones distintas.
    """
    validas = [m for m in muestras if m is not None and m >= 0]
    if not validas:
        return {"horas": None, "muestras": 0}
    return {"horas": round(statistics.median(validas), 1), "muestras": len(validas)}


def _tasa(de: int | None, a: int | None) -> float | None:
    """Que fraccion paso de una etapa a la siguiente. Sin base, no hay tasa."""
    if not de or a is None:
        return None
    return round(a / de, 4)


def _instalaciones(org, solicitudes: list[dict]) -> dict:
    """Por cada solicitud con ticket: su caso y su orden de campo, si existen.

    Devuelve {solicitud_id: {"caso_id", "orden_id", "orden_numero",
    "orden_estado", "cerrada_en"}}. Tres consultas en total, no una por fila.
    """
    from campo.models import OrdenTrabajo
    from cases.models import Case

    tickets = {s["ticket_wisphub"].strip() for s in solicitudes
               if (s.get("ticket_wisphub") or "").strip()}
    if not tickets:
        return {}

    caso_de_ticket: dict[str, str] = {}
    for caso_id, ticket in (Case.objects
                            .filter(org=org, external_ticket_id__in=tickets)
                            .values_list("id", "external_ticket_id")):
        caso_de_ticket[str(ticket)] = str(caso_id)

    # La orden que importa: la CERRADA mas temprana; si ninguna cerro, la mas
    # reciente que siga viva, para decir en que estado quedo detenida.
    ordenes_de_caso: dict[str, list] = {}
    if caso_de_ticket:
        for o in (OrdenTrabajo.objects
                  .filter(org=org, origen_sistema="crm",
                          origen_ref__in=list(caso_de_ticket.values()))
                  .values("id", "numero", "origen_ref", "estado_operativo",
                          "cerrada_en", "created_at")):
            ordenes_de_caso.setdefault(str(o["origen_ref"]), []).append(o)

    salida = {}
    for s in solicitudes:
        ticket = (s.get("ticket_wisphub") or "").strip()
        if not ticket:
            continue
        caso_id = caso_de_ticket.get(ticket)
        fila = {"caso_id": caso_id, "orden_id": None, "orden_numero": None,
                "orden_estado": None, "cerrada_en": None}
        ordenes = ordenes_de_caso.get(caso_id or "", [])
        cerradas = sorted((o for o in ordenes
                           if o["estado_operativo"] == OrdenTrabajo.CERRADA and o["cerrada_en"]),
                          key=lambda o: o["cerrada_en"])
        vivas = sorted((o for o in ordenes if o["estado_operativo"] != OrdenTrabajo.CANCELADA),
                       key=lambda o: o["created_at"], reverse=True)
        elegida = cerradas[0] if cerradas else (vivas[0] if vivas else None)
        if elegida:
            fila.update(orden_id=str(elegida["id"]), orden_numero=elegida["numero"],
                        orden_estado=elegida["estado_operativo"],
                        cerrada_en=elegida["cerrada_en"] if elegida in cerradas else None)
        salida[str(s["id"])] = fila
    return salida


def _nombre(s: dict) -> str:
    nombre = f"{s.get('nombre') or ''} {s.get('apellido') or ''}".strip()
    return nombre or (s.get("lead__title") or "").strip() or "Sin nombre"


def calcular(org, desde, hasta, ahora=None) -> dict:
    """El embudo de la organizacion para los links generados en [desde, hasta).

    `desde` y `hasta` son instantes con zona. `ahora` existe para las pruebas.
    """
    from solicitudes.models import SolicitudServicio as S

    ahora = ahora or timezone.now()
    solicitudes = list(
        S.objects.filter(org=org, created_at__gte=desde, created_at__lt=hasta)
        .values("id", "lead_id", "lead__title", "nombre", "apellido",
                "plan_interesado", "barrio", "estado", "created_at", "expira_en",
                "abierta_en", "enviada_en", "revisada_en", "cancelada_en",
                "motivo_cancelacion", "nota_revision", "ticket_wisphub")
        .order_by("created_at"))
    inst = _instalaciones(org, [s for s in solicitudes if s["estado"] == S.APROBADA])

    abiertos = [s for s in solicitudes if s["abierta_en"]]
    enviadas = [s for s in solicitudes if s["enviada_en"]]
    aprobadas = [s for s in solicitudes if s["estado"] == S.APROBADA]
    instaladas = [s for s in aprobadas if (inst.get(str(s["id"])) or {}).get("cerrada_en")]
    # Una aprobada de la que no se puede saber si se instalo: sin ticket, o con
    # un ticket que el importador todavia no trajo como caso.
    sin_dato = [s for s in aprobadas
                if not (inst.get(str(s["id"])) or {}).get("caso_id")]

    conteos = {
        "chats": None,
        "links": len(solicitudes),
        "abiertos": len(abiertos),
        "enviadas": len(enviadas),
        "aprobadas": len(aprobadas),
        "instaladas": len(instaladas),
        "activas": None,
    }

    medibles = [e for e in ETAPAS if conteos[e] is not None]
    pasos = []
    for de, a in zip(medibles, medibles[1:]):
        pasos.append({"de": de, "a": a, "tasa": _tasa(conteos[de], conteos[a])})

    tiempos = [
        {"de": "links", "a": "abiertos", **_mediana(
            [_horas(s["abierta_en"] - s["created_at"]) for s in abiertos])},
        {"de": "abiertos", "a": "enviadas", **_mediana(
            [_horas(s["enviada_en"] - s["abierta_en"]) for s in enviadas if s["abierta_en"]])},
        {"de": "enviadas", "a": "decision", **_mediana(
            [_horas(s["revisada_en"] - s["enviada_en"]) for s in solicitudes
             if s["enviada_en"] and s["revisada_en"]
             and s["estado"] in (S.APROBADA, S.SIN_FACTIBILIDAD)])},
        {"de": "aprobadas", "a": "instaladas", **_mediana(
            [_horas(inst[str(s["id"])]["cerrada_en"] - s["revisada_en"])
             for s in instaladas if s["revisada_en"]])},
    ]

    # --- las caidas -------------------------------------------------------
    nuevas = [s for s in solicitudes if s["estado"] == S.NUEVA]
    vencidas = [s for s in nuevas if s["expira_en"] and s["expira_en"] <= ahora]
    vigentes = [s for s in nuevas if not (s["expira_en"] and s["expira_en"] <= ahora)]
    canceladas = [s for s in solicitudes if s["estado"] == S.CANCELADA]
    sin_factibilidad = [s for s in solicitudes if s["estado"] == S.SIN_FACTIBILIDAD]

    from solicitudes.motivos import SIN_MOTIVO

    def _motivos(filas, campo, fecha):
        recientes = sorted((f for f in filas if (f[campo] or "").strip()),
                           key=lambda f: f[fecha] or f["created_at"], reverse=True)
        return [{"solicitud_id": str(f["id"]), "texto": f[campo].strip(),
                 "en": f[fecha]} for f in recientes[:MAXIMO_MOTIVOS]]

    caidas = {
        "link_vencido_sin_enviar": len(vencidas),
        "canceladas": {
            "total": len(canceladas),
            # El cliente no quiso decir por que: se cuenta aparte, para que esos
            # no se lean como "motivo: El cliente no quiso indicar el motivo".
            "sin_motivo": sum(1 for s in canceladas
                              if (s["motivo_cancelacion"] or "").strip() in ("", SIN_MOTIVO)),
            "motivos": [m for m in _motivos(canceladas, "motivo_cancelacion", "cancelada_en")
                        if m["texto"] != SIN_MOTIVO],
        },
        "sin_factibilidad": {
            "total": len(sin_factibilidad),
            "notas": _motivos(sin_factibilidad, "nota_revision", "revisada_en"),
        },
    }

    # --- donde estan detenidas hoy -----------------------------------------
    def _fila(s, desde_cuando, **extra):
        return {"solicitud_id": str(s["id"]),
                "lead_id": str(s["lead_id"]) if s["lead_id"] else None,
                "nombre": _nombre(s), "plan": s["plan_interesado"] or "",
                "barrio": s["barrio"] or "", "desde": desde_cuando,
                "horas": round(_horas(ahora - desde_cuando), 1) if desde_cuando else None,
                **extra}

    def _grupo(filas):
        filas = sorted(filas, key=lambda f: f["desde"] or ahora)
        return {"total": len(filas), "filas": filas[:MAXIMO_DETENIDAS]}

    ids_instaladas = {str(s["id"]) for s in instaladas}
    aprobadas_sin_instalar = []
    for s in aprobadas:
        if str(s["id"]) in ids_instaladas:
            continue
        i = inst.get(str(s["id"])) or {}
        if not (s["ticket_wisphub"] or "").strip():
            motivo = "sin_ticket"
        elif not i.get("caso_id"):
            motivo = "ticket_sin_caso"
        elif not i.get("orden_id"):
            motivo = "caso_sin_orden"
        else:
            motivo = "orden_abierta"
        aprobadas_sin_instalar.append(_fila(
            s, s["revisada_en"] or s["created_at"], motivo=motivo,
            caso_id=i.get("caso_id"), orden_numero=i.get("orden_numero"),
            orden_estado=i.get("orden_estado")))

    detenidas = {
        "sin_abrir": _grupo([_fila(s, s["created_at"]) for s in vigentes if not s["abierta_en"]]),
        "abierto_sin_enviar": _grupo([_fila(s, s["abierta_en"])
                                      for s in vigentes if s["abierta_en"]]),
        "esperando_decision": _grupo([_fila(s, s["enviada_en"] or s["created_at"])
                                      for s in solicitudes if s["estado"] == S.ENVIADA]),
        "aprobada_sin_instalar": _grupo(aprobadas_sin_instalar),
    }

    return {
        "periodo": {"desde": desde, "hasta": hasta},
        "etapas": list(ETAPAS),
        "conteos": conteos,
        "sin_dato": dict(ETAPAS_SIN_DATO),
        "instalacion_sin_dato": len(sin_dato),
        "pasos": pasos,
        "tiempos": tiempos,
        "caidas": caidas,
        "detenidas": detenidas,
    }


def de_un_lead(org, lead) -> list[dict]:
    """Las solicitudes de un prospecto, con su instalacion si se puede unir.

    Para la ficha del prospecto (`/leads/[id]`): que paso con lo que el
    asistente le genero. Sin datos personales del formulario: la ficha ya
    muestra los del Lead, y la cedula o la direccion viven en el expediente,
    que tiene su propia llave.
    """
    from solicitudes.models import SolicitudServicio as S

    filas = list(S.objects.filter(org=org, lead=lead)
                 .values("id", "estado", "plan_interesado", "created_at", "expira_en",
                         "abierta_en", "enviada_en", "revisada_en", "cancelada_en",
                         "ticket_wisphub")
                 .order_by("-created_at"))
    inst = _instalaciones(org, filas)
    salida = []
    for s in filas:
        i = inst.get(str(s["id"])) or {}
        salida.append({
            "id": str(s["id"]), "estado": s["estado"], "plan": s["plan_interesado"] or "",
            "creada_en": s["created_at"], "expira_en": s["expira_en"],
            "abierta_en": s["abierta_en"], "enviada_en": s["enviada_en"],
            "revisada_en": s["revisada_en"], "cancelada_en": s["cancelada_en"],
            "ticket": (s["ticket_wisphub"] or "").strip() or None,
            "caso_id": i.get("caso_id"), "orden_numero": i.get("orden_numero"),
            "orden_estado": i.get("orden_estado"), "instalada_en": i.get("cerrada_en"),
        })
    return salida
