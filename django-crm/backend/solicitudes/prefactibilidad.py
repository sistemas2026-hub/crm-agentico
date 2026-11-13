"""Pre-factibilidad automatica: Dexter aprueba sola la solicitud que esta clara.

POR QUE EXISTE (12/11/2026)
---------------------------
Decidir si el servicio llega a una direccion era la tarea humana mas grande de
Campo (auditoria del menu, §4 item 4), y NO es critica (PRD §2): no mueve
dinero, no deja a nadie sin servicio, no toca a muchos clientes. Lo que una
persona miraba ya se calcula: barrio -> zona -> cuadrilla
('campo.reparto.cobertura', la MISMA regla que usa el despacho, reusada y no
copiada), y la precision del GPS que mando el formulario.

LA REGLA, Y LO QUE QUEDA PARA UNA PERSONA
-----------------------------------------
Se aprueba sola SOLO si todo esto es cierto:
  * la empresa la encendio (Ajustes -> Instalaciones; nace APAGADA);
  * la solicitud ya tiene su ticket en el ISP (aprobar es moverlo);
  * el barrio cae en una zona, y esa zona la cubre una cuadrilla con la labor
    de instalacion de esa empresa -- hoy en una jornada, o habitualmente;
  * hay GPS y su precision es igual o mejor que el umbral de la empresa.
Si algo falla, queda en la bandeja CON EL MOTIVO («fuera de zona», «GPS
dudoso (±850 m)», «sin GPS»...). Nunca se RECHAZA sola: rechazar le escribe al
cliente que no hay servicio, y eso no lo decide una regla que solo sabe que
no esta segura.

La garantia no se va con la persona: la aprobacion pasa por el mismo camino
que la de una persona (solicitudes.decision.decidir: UPDATE condicionado,
reasignacion con clave de idempotencia, Lead), y el motor sigue aplicando su
interruptor de autonomia a la reasignacion.
"""

from __future__ import annotations

import logging

from solicitudes.models import AjustesDeInstalacion, SolicitudServicio

logger = logging.getLogger(__name__)

GRUPO_INSTALACION = "instalacion_nueva"


def _precision_m(s) -> float | None:
    try:
        valor = float(str(s.gps_precision_m or "").replace(",", ".").strip())
    except ValueError:
        return None
    return valor if valor >= 0 else None


def evaluar(s, ajustes, *, fecha=None) -> tuple[bool, str]:
    """(se aprueba sola, motivo). No escribe nada."""
    from campo.cuadrillas import labor_de_cada_grupo
    from campo.reparto import cobertura

    if fecha is None:
        from campo.tasks import _ahora_local

        fecha = _ahora_local(s.org).date()

    motivos = []
    if not s.ticket_wisphub:
        motivos.append("sin ticket del ISP todavía")

    labor = labor_de_cada_grupo(s.org).get(GRUPO_INSTALACION, "")
    cob = cobertura(s.org, s.barrio or "", fecha, labor)
    zona = (cob.get("zona") or {}).get("nombre", "")
    cuadrilla = ""
    if cob.get("motivo") == "sin_barrio":
        motivos.append("sin barrio")
    elif cob.get("motivo") == "sin_zona":
        motivos.append(f"fuera de zona (el barrio «{cob.get('barrio')}» no está en ninguna)")
    else:
        hoy = [j for j in cob.get("jornadas") or [] if j.get("coincide_labor")]
        habituales = [h for h in cob.get("habituales") or []
                      if not labor or h.get("labor") == labor]
        if hoy:
            cuadrilla = hoy[0]["cuadrilla"]
        elif habituales:
            cuadrilla = habituales[0]["cuadrilla"]
        else:
            motivos.append(f"la zona {zona} no tiene cuadrilla de {labor or 'instalación'}")

    if not s.tiene_gps:
        motivos.append("sin GPS")
    else:
        precision = _precision_m(s)
        if precision is None:
            motivos.append("GPS dudoso (sin precisión)")
        elif precision > ajustes.precision_gps_maxima_m:
            motivos.append(f"GPS dudoso (±{round(precision)} m)")

    if motivos:
        return False, " · ".join(motivos)
    return True, (f"Barrio {cob.get('barrio')} en la zona {zona}, que cubre {cuadrilla}; "
                  f"GPS ±{round(_precision_m(s))} m.")


def aplicar(s) -> str:
    """Evalua y, si corresponde, aprueba. Devuelve el motivo anotado ('' si la
    pre-factibilidad esta apagada). Nunca lanza: corre despues de que la
    solicitud ya esta guardada y entregada."""
    from solicitudes import decision

    try:
        ajustes = AjustesDeInstalacion.objects.filter(org_id=s.org_id).first()
        if ajustes is None or not ajustes.prefactibilidad_activa:
            return ""
        if s.estado != SolicitudServicio.ENVIADA:
            return ""
        aprueba, motivo = evaluar(s, ajustes)
        if aprueba:
            decision.decidir(s, aprueba=True, nota="", autor=None, automatica=True,
                             motivo_auto=motivo)
        else:
            SolicitudServicio.objects.filter(pk=s.pk).update(
                prefactibilidad_motivo=motivo[:300])
            s.prefactibilidad_motivo = motivo[:300]
        return motivo
    except Exception as e:                              # noqa: BLE001
        logger.warning("solicitudes: la pre-factibilidad no se pudo evaluar (%s)",
                       type(e).__name__)
        return ""
