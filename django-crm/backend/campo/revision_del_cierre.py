# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR REVISA EL CIERRE DEL TECNICO  --  30/10/2026
================================================================================

SPEC/objetivos/revision-del-cierre.md. El usuario: «al momento que el tecnico
envia el reporte final, el supervisor debe revisar si quedo bien y indicar si
lo cierra o no y por que».

INDICA; Y SI SE LE DELEGA, CIERRA POR SU PUERTA
-----------------------------------------------
Esto devuelve un veredicto con sus motivos y no escribe nada. Lo usan dos:
una persona, que lo confirma con un toque en Programacion (y entonces el ticket
del ISP se cierra por la puerta HUMANA del motor); y el Supervisor, si se le
delego la tarea (`campo/cierre_por_el_supervisor.py`), que cierra solo lo que
esto marca «Se puede cerrar» por la puerta AUTONOMA, con sus compuertas. Un
Supervisor por la puerta humana seria una IA usando una puerta que no es la
suya (CLAUDE.md §4).

EN CODIGO, PUNTO POR PUNTO
--------------------------
Cada punto responde si (True), no (False) o no se sabe (None), con su texto:

    checklist     los datos y las fotos obligatorias (`verificar_checklist_completo`)
    reporte       que el tecnico mando el cierre de ESTA vuelta
    servicio      si el tecnico AFIRMO que el servicio quedo funcionando
    medicion      la señal despues del arreglo: si el Supervisor ya la
                  midio, en rango o no; si la orden la espera y todavia no
                  llego, «no se sabe» (auditoria, 30/10/2026: la ausencia no
                  puede contar como aprobacion)
    material      si registro lo que gasto, o confirmo que no gasto nada

El veredicto: algun «no» -> NO SE CIERRA; algun «no se sabe» -> REVISAR; todo
«si» -> SE PUEDE CERRAR. Un punto que no aplica (una plantilla sin la pregunta
del servicio, una orden que no es de falla) no se cuenta.

SE CALCULA, NO SE GUARDA
------------------------
Como `services/salud_seguimiento.py`: la medicion llega hasta una hora despues
del cierre, y un veredicto guardado diria «revisar» cuando ya se sabe.
================================================================================
"""
from __future__ import annotations

CERRAR = "se_puede_cerrar"
REVISAR = "revisar"
NO_CERRAR = "no_cerrar"

TEXTOS = {
    CERRAR: "Se puede cerrar",
    REVISAR: "Revisalo antes de cerrar",
    NO_CERRAR: "No se cierra",
}


def aplica(orden) -> bool:
    """Lo terminado en campo que todavia nadie valido."""
    from campo.models import OrdenTrabajo

    return (orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
            and orden.estado_validacion in (OrdenTrabajo.PENDIENTE,
                                            OrdenTrabajo.REQUIERE_REVISION))


#: No se pudo saber que ordenes necesitan la medicion: toda medicion que falta
#: es «no se sabe». Distinto de no haberlo preguntado (None).
NO_SE_SABE = "no_se_sabe"


def pendientes_de_medir(org, ahora=None) -> set | None:
    """Los ids de las ordenes terminadas sin validar que NECESITAN la medicion
    despues del arreglo: las de una FALLA DE SERVICIO (el mismo criterio que
    `operaciones/verificacion_de_arreglos.candidatas`), SIN su ventana de 48 h
    ni su «ya no se reintenta» (auditoria de frontera, 30/10/2026: pasada la
    ventana, una falla nunca medida volvia a contar como «no aplica»). None si
    no se pudo saber, y entonces quien cierra solo no cierra nada."""
    from campo.models import OrdenTrabajo
    from operaciones import paso_a_despacho as pad

    try:
        por_caso = {str(caso): str(orden_id) for orden_id, caso in (
            OrdenTrabajo.objects.filter(
                org=org, origen_sistema="crm",
                estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
                estado_validacion__in=(OrdenTrabajo.PENDIENTE,
                                       OrdenTrabajo.REQUIERE_REVISION))
            .values_list("id", "origen_ref"))}
        if not por_caso:
            return set()
        salida = set()
        for p in pad.propuestas_que_llevan_a_despacho(org).filter(
                origen_id__in=list(por_caso)):
            lectura = pad._ultima_lectura_con_grupo(p) or {}
            if (lectura.get("grupo") == pad.FALLA_DE_SERVICIO
                    and lectura.get("accion_autorizada") != pad.SI):
                salida.add(por_caso[str(p.origen_id)])
        return salida
    except Exception:                                            # noqa: BLE001
        return None


def revisar(orden, *, pendientes=None) -> dict | None:
    """El veredicto de UNA orden, o None si no hay nada que revisar.
    `pendientes`: los de `pendientes_de_medir`; sin ellos, una orden sin
    medicion se lee como una que no la necesita."""
    if not aplica(orden):
        return None
    cierre = _cierre_de_esta_vuelta(orden)
    puntos = [p for p in (_checklist(orden), _reporte(cierre), _servicio(cierre),
                          _medicion(orden, pendientes), _material(orden, cierre))
              if p is not None]
    if any(p["ok"] is False for p in puntos):
        veredicto = NO_CERRAR
    elif any(p["ok"] is None for p in puntos):
        veredicto = REVISAR
    else:
        veredicto = CERRAR
    esquema = getattr(orden.tipo_trabajo_version, "esquema", None) or {}
    return {
        "veredicto": veredicto,
        "texto": TEXTOS[veredicto],
        "puntos": puntos,
        #  Lo que una devolucion puede pedir rehacer (`requerir_correccion`
        #  exige nombrarlo), y lo que el checklist ya marca como faltante.
        "evidencias": [{"id": e["id"], "titulo": e.get("titulo") or e["id"]}
                       for e in esquema.get("evidencias", []) if e.get("id")],
        "sugeridas": next((p["faltan"] for p in puntos if p["clave"] == "checklist"), []),
        "solucion": _solucion(cierre),
    }


def _punto(clave, ok, texto, **extra) -> dict:
    return {"clave": clave, "ok": ok, "texto": texto, **extra}


def _cierre_de_esta_vuelta(orden):
    """El ultimo reporte de cierre DESPUES de la ultima devolucion: el de una
    vuelta anterior ya fue revisado y devuelto."""
    from campo.models import EventoTrabajo

    eventos = EventoTrabajo.objects.filter(org=orden.org, orden=orden)
    devuelta = (eventos.filter(tipo="reapertura_correccion")
                .order_by("-created_at").values_list("created_at", flat=True).first())
    cierres = eventos.filter(tipo="cierre_campo")
    if devuelta is not None:
        cierres = cierres.filter(created_at__gt=devuelta)
    return cierres.order_by("-created_at").first()


def _solucion(cierre) -> str:
    respuestas = ((cierre.datos or {}).get("respuestas") or {}) if cierre else {}
    return str(respuestas.get("solucion") or "")


def _checklist(orden):
    from campo.services.validador import verificar_checklist_completo

    errores = verificar_checklist_completo(orden)
    if not errores:
        return _punto("checklist", True, "El checklist está completo: datos y fotos.", faltan=[])
    faltan = sorted({e["requisito_id"] for e in errores if e.get("requisito_id")})
    return _punto("checklist", False, "Falta en el checklist: "
                  + "; ".join(e.get("mensaje", "") for e in errores[:3]), faltan=faltan)


def _reporte(cierre):
    if cierre is None:
        return _punto("reporte", False, "No mandó el reporte de cierre.")
    return _punto("reporte", True, "Mandó el reporte de cierre.")


def _servicio(cierre):
    """Lo que el tecnico AFIRMO. Si la plantilla de ese cierre no lo pregunta,
    el punto no aplica."""
    if cierre is None:
        return None
    datos = cierre.datos or {}
    pregunta = any(isinstance(c, dict) and c.get("id") == "servicio_validado"
                   for c in (datos.get("definicion") or []))
    if not pregunta:
        return None
    valor = (datos.get("respuestas") or {}).get("servicio_validado")
    if valor is True:
        return _punto("servicio", True, "El técnico afirma que el servicio quedó funcionando.")
    if valor is False:
        return _punto("servicio", False, "El técnico dice que el servicio NO quedó funcionando.")
    return _punto("servicio", None, "El reporte no dice si el servicio quedó funcionando.")


def _medicion(orden, pendientes=None):
    """La señal despues del arreglo (`operaciones/verificacion_de_arreglos.py`),
    si el Supervisor ya la midio para ESTA orden. Si la espera y no llego,
    «no se sabe». Si no la espera, no aplica."""
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    esperando = _punto("medicion", None,
                       "La señal después del arreglo todavía no se midió: el "
                       "Supervisor mide una vez por hora.")

    propuesta = (PropuestaSupervisor.objects
                 .filter(org=orden.org,
                         evidencia__contains=[{"fuente": FUENTE, "orden": str(orden.id)}])
                 .order_by("-updated_at").first())
    pieza = None if propuesta is None else next(
        (p for p in reversed(propuesta.evidencia or [])
         if isinstance(p, dict) and p.get("fuente") == FUENTE
         and p.get("orden") == str(orden.id)), None)
    if pieza is None:
        if pendientes == NO_SE_SABE:
            return _punto("medicion", None,
                          "No se pudo saber si esta orden espera la medición "
                          "después del arreglo.")
        return esperando if pendientes and str(orden.id) in pendientes else None
    rango = pieza.get("quedo_en_rango")
    if rango is True:
        return _punto("medicion", True, "La señal quedó en rango después del arreglo.")
    if rango is False:
        return _punto("medicion", False, "La señal NO quedó en rango después del arreglo.")
    return _punto("medicion", None, "No se pudo medir la señal después del arreglo.")


def _material(orden, cierre):
    from campo.models import MovimientoDeMaterial

    usados = MovimientoDeMaterial.objects.filter(
        org=orden.org, orden=orden, tipo=MovimientoDeMaterial.CONSUMO).count()
    if usados:
        return _punto("material", True,
                      f"Registró {usados} {'material' if usados == 1 else 'materiales'}.")
    if cierre is not None and (cierre.datos or {}).get("sin_material_confirmado"):
        return _punto("material", True, "Confirmó que no usó material.")
    return _punto("material", None, "No registró material ni confirmó que no usó.")
