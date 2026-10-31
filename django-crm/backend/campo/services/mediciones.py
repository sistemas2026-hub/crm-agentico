# -*- coding: utf-8 -*-
"""
Las mediciones que hace el técnico en el sitio quedan en la bitácora.

POR QUÉ EXISTE (18/10/2026)
---------------------------
«Volver a medir la señal» y «probar la conexión» devolvían el resultado al
teléfono y no lo guardaban en ningún lado. Se perdía justo el dato que
`MedirSenalView` dice que importa: cómo quedó el servicio DESPUÉS de la visita,
para ponerlo al lado de la lectura congelada de antes.

Ahora cada medición es un evento de la bitácora, con su hora y quién la pidió.
Lo que NO cambia: la ficha congelada (`orden.contexto`) no se pisa, y un ping no
es un veredicto --el conteo se anota crudo, «2 de 3», porque el mismo equipo
sano da 1, 2 y 3 de 3 en corridas seguidas--.

«NO SE PUDO MEDIR» TAMBIÉN SE ANOTA. Dice que el técnico lo intentó, y por qué
no salió; es distinto de «se midió y está mal», y los dos se leen distinto.

UNA PRUEBA DE CONEXIÓN SON TRES LLAMADAS (3, 3 y 4 paquetes, ver `TANDAS`). La
bitácora es de solo agregar, así que cada tanda es su propio evento; al LEERLA,
las tandas seguidas de una misma persona se juntan en un renglón (`juntar_tandas`).
Se calcula al leer, no se guarda: un evento editado después ya no sería el que
se escribió.
"""

from __future__ import annotations

import logging
import re

from campo.models import EventoTrabajo

logger = logging.getLogger(__name__)

SENAL = "senal_medida"
CONEXION = "conexion_probada"

#: Cuánto puede pasar entre dos tandas para que sean la misma prueba.
SEGUNDOS_ENTRE_TANDAS = 120

#: Por qué no se pudo, en palabras. Es lo que lee la oficina.
MOTIVOS = {
    "motor_no_responde": "el sistema de medición no respondió",
    "motor_rechazo": "el sistema de medición rechazó la consulta",
    "medicion_no_habilitada": "la medición no está habilitada para esta empresa",
    "ping_no_habilitado": "la prueba de conexión no está habilitada para esta empresa",
    "respuesta_ilegible": "la respuesta no se pudo leer",
    "respuesta_vacia": "no llegó respuesta del equipo",
    "sin_lectura": "el equipo no devolvió niveles",
    "sin_conteo": "no llegó el conteo de paquetes",
}

#: Los niveles de la lectura, en el orden en que se leen.
NIVELES = (
    ("onu_signal_1490", "1490 nm"),
    ("onu_signal_1310", "1310 nm"),
    ("onu_signal", "Señal"),
)


def _motivo(resultado: dict) -> str:
    codigo = resultado.get("motivo") or ""
    return MOTIVOS.get(codigo, codigo or "motivo desconocido")


def texto_de_senal(resultado: dict) -> str:
    if not resultado.get("ok"):
        return f"No se pudo medir: {_motivo(resultado)}"
    lectura = resultado.get("lectura") or {}
    partes = []
    for clave, rotulo in NIVELES:
        if lectura.get(clave) in (None, ""):
            continue
        parte = f"{rotulo}: {lectura[clave]}"
        if clave == "onu_signal_1490" and lectura.get("onu_signal_1490_veredicto"):
            parte += f" ({lectura['onu_signal_1490_veredicto']})"
        partes.append(parte)
    if lectura.get("onu_status"):
        partes.append(f"estado {lectura['onu_status']}")
    return " · ".join(partes) or "Se midió, sin niveles"


def _texto_de_ping(respondieron: list[str], fallas: list[str]) -> str:
    #  «3 de 3», «2 de 3»: se suman si todas se pueden leer así; si no, van
    #  tal cual llegaron. Nunca se convierte en un porcentaje ni en un «bien».
    conteos = [re.fullmatch(r"\s*(\d+)\s+de\s+(\d+)\s*", r) for r in respondieron]
    if respondieron and all(conteos):
        si = sum(int(m.group(1)) for m in conteos)
        de = sum(int(m.group(2)) for m in conteos)
        texto = f"Respondieron {si} de {de} paquetes"
    elif respondieron:
        texto = "Respondieron " + " · ".join(respondieron)
    else:
        texto = ""
    if fallas:
        falla = "No se pudo probar: " + ", ".join(dict.fromkeys(fallas))
        texto = f"{texto} · {falla}" if texto else falla
    return texto


def _anotar(orden, profile, tipo: str, datos: dict) -> None:
    """Anota el evento. Si no puede, la medición igual le llega al técnico.

    Está parado en la casa del cliente esperando la respuesta: negársela
    porque la bitácora falló le quitaría lo único que pidió.
    """
    try:
        EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                     profile=profile, datos=datos)
    except Exception as e:                                   # noqa: BLE001
        logger.warning("medicion_sin_anotar tipo=%s error=%s", tipo, type(e).__name__)


def anotar_senal(orden, profile, resultado: dict) -> None:
    datos = {"ok": bool(resultado.get("ok")), "resultado": texto_de_senal(resultado)}
    if resultado.get("ok"):
        datos["lectura"] = resultado.get("lectura") or {}
        datos["medido_en"] = resultado.get("medido_en")
    else:
        datos["motivo"] = resultado.get("motivo")
    _anotar(orden, profile, SENAL, datos)


def anotar_conexion(orden, profile, resultado: dict) -> None:
    if resultado.get("ok"):
        datos = {"ok": True, "respondieron": str(resultado.get("respondieron") or ""),
                 "enviados": len(resultado.get("paquetes") or [])}
        datos["resultado"] = _texto_de_ping([datos["respondieron"]], [])
    else:
        datos = {"ok": False, "motivo": resultado.get("motivo"),
                 "resultado": _texto_de_ping([], [_motivo(resultado)])}
    _anotar(orden, profile, CONEXION, datos)


def juntar_tandas(eventos: list) -> list:
    """Las tandas seguidas de una misma prueba, como un solo grupo.

    Devuelve listas de eventos: una por renglón. Dos tandas son la misma prueba
    si son de la misma persona, ninguna otra cosa pasó en el medio y no hay
    más de `SEGUNDOS_ENTRE_TANDAS` entre una y otra.
    """
    grupos: list[list] = []
    for e in eventos:
        previo = grupos[-1][-1] if grupos else None
        if (e.tipo == CONEXION and previo is not None and previo.tipo == CONEXION
                and previo.profile_id == e.profile_id
                and e.created_at and previo.created_at
                and (e.created_at - previo.created_at).total_seconds()
                <= SEGUNDOS_ENTRE_TANDAS):
            grupos[-1].append(e)
        else:
            grupos.append([e])
    return grupos


def resultado_de_tandas(tandas: list) -> str:
    respondieron = [(t.datos or {}).get("respondieron") for t in tandas
                    if (t.datos or {}).get("ok")]
    fallas = [MOTIVOS.get((t.datos or {}).get("motivo") or "",
                          (t.datos or {}).get("motivo") or "motivo desconocido")
              for t in tandas if not (t.datos or {}).get("ok")]
    return _texto_de_ping([r for r in respondieron if r], fallas)
