# -*- coding: utf-8 -*-
"""
================================================================================
 VALIDADA LA ORDEN, EL TICKET DEL ISP SE CIERRA
================================================================================

Hasta el 13/10/2026 lo que el tecnico registraba en la app quedaba solo en
Dexter. El ticket del ISP se cerraba a mano en otro lado, o no se cerraba, y
los dos sistemas contaban historias distintas del mismo trabajo.

CUANDO: al VALIDAR la oficina, no al cerrar el tecnico. Lo que el tecnico
cierra todavia puede volver por una foto que falta; lo validado ya no.

QUE: el ticket queda CERRADO, con un resumen de lo que se hizo y el nombre de
quien valido. Decision del usuario del 13/10/2026: se cierra aunque el ISP le
avise al cliente, porque el aviso no dice quien lo cerro.

COMO: por la ruta angosta del motor `/interno/orden/<id>/cerrar-ticket`, que
entra por la puerta HUMANA con la orden como evidencia, consulta el kill switch
y es idempotente por orden. El estado de cierre lo fija la herramienta del
tenant, no este codigo. Ver nucleo/seguimiento/cierre_por_validacion.py.

NUNCA ROMPE LA VALIDACION. La orden ya esta validada (hecho) y el ISP la tiene
cerrada (otro hecho): el segundo puede fallar sin que el primero deje de ser
cierto. Lo que paso queda en la bitacora de la orden, para que se vea.

Se apaga con `CAMPO_CERRAR_TICKET_AL_VALIDAR=0`.
================================================================================
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

BANDERA = "CAMPO_CERRAR_TICKET_AL_VALIDAR"

#: Los eventos que deja en la bitacora de la orden.
EVENTO_CERRADO = "ticket_isp_cerrado"
EVENTO_NO_CERRADO = "ticket_isp_no_cerrado"

#: Tope del resumen. El ticket es para la operacion, no para el informe entero.
MAX_LINEAS = 15


def _habilitado() -> bool:
    return (os.environ.get(BANDERA, "1") or "1").strip() != "0"


def _tapar(texto) -> str:
    from operaciones.lectura_de_ticket import tapar

    return tapar(str(texto or ""))


def resumen_de(orden, nombre_de_quien_valida: str) -> str:
    """Lo que queda escrito en el ticket: que se hizo, sin datos personales.

    Sale de la PLANTILLA de la orden, no de todo `orden.datos`: solo lo que el
    tecnico respondio a una pregunta declarada, con el titulo de esa pregunta.
    Cada valor pasa por `tapar` -- un «llamar al 300...» escrito en un texto
    libre no tiene por que terminar en el ticket.
    """
    version = orden.tipo_trabajo_version
    esquema = (version.esquema or {}) if version else {}
    tipo = version.work_type.nombre if version else "trabajo de campo"
    datos = orden.datos or {}

    lineas = [f"Trabajo de campo OT #{orden.numero} ({tipo}) validado en Dexter "
              f"por {nombre_de_quien_valida}."]
    for campo in esquema.get("campos") or []:
        if not isinstance(campo, dict):
            continue
        valor = datos.get(campo.get("id"))
        if valor in (None, ""):
            continue
        titulo = campo.get("titulo") or campo.get("id")
        unidad = f" {campo['unidad']}" if campo.get("unidad") else ""
        lineas.append(f"- {titulo}: {_tapar(valor)}{unidad}")
        if len(lineas) > MAX_LINEAS:
            lineas.append("- (sigue en Dexter)")
            break
    fotos = orden.evidencias.count() if hasattr(orden, "evidencias") else 0
    if fotos:
        lineas.append(f"Evidencias en Dexter: {fotos}.")
    return "\n".join(lineas)


def _ya_cerrado(orden) -> bool:
    from campo.models import EventoTrabajo

    return EventoTrabajo.objects.filter(orden=orden, tipo=EVENTO_CERRADO).exists()


def _anotar(orden, profile, tipo, datos):
    from campo.models import EventoTrabajo

    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                 profile=profile, datos=datos)


def cerrar_ticket_al_validar(orden, profile) -> dict:
    """Cierra en el ISP el ticket de una orden recien validada. Nunca lanza.

    Devuelve `{"estado": ..., "detalle": ...}` para que la respuesta de la
    validacion pueda decir que paso con el ticket.
    """
    from campo.services.inventario import nombre_de

    if not _habilitado():
        return {"estado": "apagado", "detalle": f"{BANDERA}=0"}
    ticket = str((orden.contexto or {}).get("ticket") or "").strip()
    if not ticket:
        #  Una orden sin ticket del ISP (manual, o de un caso nacido en el chat)
        #  no tiene nada que cerrar alla. No es un fallo, y no se anota.
        return {"estado": "sin_ticket", "detalle": "la orden no tiene ticket del ISP"}
    if _ya_cerrado(orden):
        return {"estado": "ya_cerrado", "detalle": f"ticket {ticket}"}

    tenant = (os.environ.get("MOTOR_TENANT", "") or "").strip()
    if not tenant:
        return {"estado": "no_cerrado",
                "detalle": "falta MOTOR_TENANT: sin saber de que empresa es la "
                           "orden no se le escribe al ISP"}

    import requests

    quien = nombre_de(profile)
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.post(
            f"{base}/interno/orden/{orden.id}/cerrar-ticket",
            params={"tenant": tenant},
            json={"ticket": ticket, "texto": resumen_de(orden, quien),
                  "actor": quien},
            headers=cabeceras, timeout=45)
        cuerpo = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("cierre en el ISP: no se pudo hablar con el motor (%s)",
                       type(e).__name__)
        _anotar(orden, profile, EVENTO_NO_CERRADO,
                {"ticket": ticket, "codigo": type(e).__name__})
        return {"estado": "no_cerrado", "detalle": type(e).__name__}

    if r.status_code == 200 and cuerpo.get("cerrado"):
        _anotar(orden, profile, EVENTO_CERRADO,
                {"ticket": ticket, "referencia": cuerpo.get("referencia", "")})
        return {"estado": "cerrado", "detalle": f"ticket {ticket}"}

    codigo = cuerpo.get("codigo") or f"HTTP {r.status_code}"
    logger.warning("cierre en el ISP: el motor no cerro (%s)", codigo)
    _anotar(orden, profile, EVENTO_NO_CERRADO, {"ticket": ticket, "codigo": codigo})
    return {"estado": "no_cerrado", "detalle": codigo}
