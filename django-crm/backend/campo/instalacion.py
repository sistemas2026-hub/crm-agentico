# -*- coding: utf-8 -*-
"""
================================================================================
 LA INSTALACION QUE VALIDA UNA PERSONA  --  26/11/2026
================================================================================
El usuario, sobre como trabaja Rapilink:

    «en instalaciones se crea instalacion y despues un encargado valida si
    todo esta bien y activa, que pasa a cliente»

    «cuando el tecnico manda finalizar trabajo entra en validacion humana y si
    aprueba la instalacion se le informa al tecnico para que valide servicio y
    entregue al cliente, y despues cierra el ticket»

EL RECORRIDO, con `ConfiguracionDeContrato.validar_antes_de_activar` encendido
--------------------------------------------------------------------------------
1. El tecnico firma el contrato en la casa. NO se crea nada en el proveedor.
2. Toca «Finalizar trabajo»: la orden queda `completada_campo` y esperando a
   una persona, y se pide el alta COMO INSTALACION (`al_finalizar`), ya con lo
   que cobro el tecnico (costo de instalacion) y el serial de la ONU.
3. El encargado revisa en Dexter y aprueba: se pide la ACTIVACION
   (`pedir_activacion`), que la pasa a cliente en el proveedor. Da servicio:
   sale por la puerta humana de quien aprobo, y se confirma leyendo.
4. Activada: la orden queda APROBADA y al tecnico le llega «valida el servicio
   y entregalo» (`avisos.avisar_instalacion_aprobada`). El ticket NO se cierra.
5. El tecnico confirma la entrega (`InstalacionEntregadaView`): la orden se
   cierra y AHI se cierra el ticket del proveedor.

EL SUPERVISOR AUTOMATICO NO APRUEBA NI DEVUELVE ESTAS ORDENES
(`requiere_validacion_humana`): aprobar una es dar servicio.
================================================================================
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Cuanto se le espera al motor por pedido: el motor espera hasta 25 s leyendo,
#: y el pedido al proveedor tiene su propio tope.
ESPERA_DEL_PEDIDO = 100
#: La tarea vuelve cada ESPERA s, hasta VUELTAS veces, y despues lo deja
#: «por revisar» para que una persona lo mire en el proveedor.
ESPERA_DE_LA_ACTIVACION = 20
VUELTAS_DE_LA_ACTIVACION = 12
PEDIDOS_POR_CONTRATO = 20


def _config(org) -> dict:
    from campo.contrato import configuracion_de

    return configuracion_de(org)


def requiere_validacion_humana(orden) -> bool:
    """Si esta orden es una instalacion que aprueba una PERSONA: la empresa lo
    pide y la orden tiene un contrato vigente. Nunca levanta: ante la duda,
    una persona (fallar del lado seguro)."""
    from campo.contrato import vigente_de

    try:
        return bool(_config(orden.org).get("validar_antes_de_activar")) and vigente_de(orden) is not None
    except Exception:                                            # noqa: BLE001
        logger.warning("instalacion: no se pudo saber si requiere validacion; se asume que si")
        return True


# =============================================================================
#  LO QUE VIAJA AL PROVEEDOR DESDE LA ORDEN
# =============================================================================
def costo_y_serial(orden) -> dict:
    """El costo de instalacion que anoto el tecnico (el dato de la plantilla
    marcado `costo_de_instalacion`) y el serial de la ONU que quedo activada.
    Lo que no esta, no viaja."""
    from campo import activacion_onu, dinero

    salida: dict = {}
    esquema = getattr(orden.tipo_trabajo_version, "esquema", None) or {}
    datos = orden.datos or {}
    for c in (esquema.get("campos") or []):
        if isinstance(c, dict) and c.get("costo_de_instalacion") and c.get("id") in datos:
            valor = dinero._monto(datos.get(c["id"]))
            if datos.get(c["id"]) not in (None, ""):
                salida["costo_instalacion"] = dinero._numero(valor)
            break
    try:
        ultima = activacion_onu.ultima(orden)
    except Exception:                                            # noqa: BLE001
        ultima = None
    if ultima is not None and getattr(ultima, "estado", "") in ("activada", "ya_estaba"):
        salida["serial_onu"] = str(ultima.serial or "")
    return salida


def al_finalizar(orden, profile) -> bool:
    """El tecnico toco «Finalizar trabajo»: si la empresa valida antes de
    activar y crea en el proveedor, se pide el alta COMO INSTALACION. Nunca
    levanta: finalizar no puede romperse por esto."""
    from campo.contrato import ContratoDeServicio, vigente_de
    from campo.services import alta_en_el_isp

    #  LAS FOTOS DEL TRABAJO (26/11/2026): si el contrato se preparo en el
    #  proveedor, sus fotos van a los archivos del cliente. Depende de ESE
    #  contrato, no de como esten hoy los interruptores. Nunca rompe finalizar.
    try:
        from campo.contrato_del_proveedor import pedir_fotos

        hecho = vigente_de(orden)
        if hecho is not None:
            pedir_fotos(hecho, por=profile)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("instalacion: no se pudieron pedir las fotos (%s)", type(e).__name__)
    try:
        config = _config(orden.org)
        if not (config.get("crear_en_el_isp") and config.get("validar_antes_de_activar")):
            return False
        contrato = vigente_de(orden)
        if contrato is None or contrato.estado != ContratoDeServicio.FIRMADO:
            return False
        return alta_en_el_isp.pedir_alta(contrato, por=profile, como_instalacion=True)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("instalacion: no se pudo pedir el alta al finalizar (%s)", type(e).__name__)
        return False


# =============================================================================
#  LA ACTIVACION
# =============================================================================
class NoSePuedeActivar(ValueError):
    """La instalacion no esta para activar. El texto se muestra tal cual."""


def _anotar(contrato, **campos) -> None:
    from campo.contrato import ContratoDeServicio

    ahora = timezone.now()
    campos.setdefault("activacion_actualizada_en", ahora)
    if "activacion_detalle" in campos:
        campos["activacion_detalle"] = str(campos["activacion_detalle"] or "")[:300]
    (ContratoDeServicio.objects
     .filter(pk=contrato.pk, estado=ContratoDeServicio.INSTALACION)
     .update(updated_at=ahora, **campos))
    contrato.refresh_from_db()


def pedir_activacion(orden, *, por) -> "object":
    """El encargado aprobo: se pide la activacion, DESPUES del commit. Devuelve
    el contrato. Levanta `NoSePuedeActivar` con el por que."""
    from campo.contrato import ContratoDeServicio, vigente_de
    from campo.models import OrdenTrabajo

    if not requiere_validacion_humana(orden):
        raise NoSePuedeActivar("Esta orden no es una instalación que se valide aquí.")
    if orden.estado_operativo != OrdenTrabajo.COMPLETADA_CAMPO:
        raise NoSePuedeActivar("El técnico todavía no finalizó el trabajo.")
    if orden.estado_validacion not in (OrdenTrabajo.PENDIENTE, OrdenTrabajo.REQUIERE_REVISION):
        raise NoSePuedeActivar(
            f"La orden está en validación «{orden.get_estado_validacion_display()}».")
    contrato = vigente_de(orden)
    if contrato is None:
        raise NoSePuedeActivar("La orden no tiene contrato.")
    if contrato.estado == ContratoDeServicio.EN_EL_ISP:
        raise NoSePuedeActivar("Esta instalación ya es cliente.")
    if contrato.estado != ContratoDeServicio.INSTALACION:
        raise NoSePuedeActivar(
            "Todavía no hay una instalación en el proveedor: "
            + ("se está creando, espera un momento." if contrato.alta_estado in
               ContratoDeServicio.ALTA_EN_VUELO else "revisa cómo quedó el alta."))
    if contrato.activacion_estado in ContratoDeServicio.ACTIVACION_SIN_RESOLVER:
        raise NoSePuedeActivar("Ya se está activando.")
    intento = int(contrato.activacion_intento or 0) + 1
    if intento > PEDIDOS_POR_CONTRATO:
        raise NoSePuedeActivar("Se pidió demasiadas veces: revisa en el proveedor.")
    ahora = timezone.now()
    tocadas = (ContratoDeServicio.objects
               .filter(pk=contrato.pk, estado=ContratoDeServicio.INSTALACION,
                       activacion_intento=int(contrato.activacion_intento or 0))
               .exclude(activacion_estado__in=ContratoDeServicio.ACTIVACION_SIN_RESOLVER)
               .update(activacion_estado=ContratoDeServicio.ACTIVACION_PEDIDA,
                       activacion_detalle="", activacion_intento=intento,
                       activado_por=por, activacion_actualizada_en=ahora, updated_at=ahora))
    contrato.refresh_from_db()
    if not tocadas:
        raise NoSePuedeActivar("Ya se está activando.")
    org_id, contrato_id = str(contrato.org_id), str(contrato.id)

    def _encolar():
        from campo.tasks import activar_cliente_en_el_isp

        try:
            activar_cliente_en_el_isp.delay(org_id, contrato_id)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("instalacion: no se pudo encolar la activacion (%s)", type(e).__name__)
            try:
                _anotar(ContratoDeServicio.objects.get(pk=contrato_id),
                        activacion_estado=ContratoDeServicio.ACTIVACION_FALLIDA,
                        activacion_detalle="No se pudo pedir. Intenta de nuevo.")
            except Exception:                                    # noqa: BLE001
                pass

    transaction.on_commit(_encolar)
    return contrato


_POR_QUE = {
    "fallo": "El proveedor rechazó la activación.",
    "no_encontrada": "No hay en el proveedor una instalación de este contrato con ese número.",
    "bloqueado": "La activación no salió (el sistema la frenó antes de llegar al proveedor).",
    "datos_invalidos": "Faltan datos del contrato para activar.",
    "sin_herramienta": "La empresa no tiene configurado cómo activar en el proveedor.",
    "no_se_pudo_comprobar": "No se pudo leer el proveedor.",
}


def _activada(contrato) -> None:
    """Quedo cliente: el contrato pasa a `en_el_isp`, la orden queda APROBADA y
    al tecnico le llega que valide el servicio y entregue."""
    from campo.contrato import ContratoDeServicio
    from campo.revision_del_cierre import guardar_foto, revisar
    from campo.services.avisos import avisar_instalacion_aprobada
    from campo.services.transiciones import aprobar

    ahora = timezone.now()
    with transaction.atomic():
        tocadas = (ContratoDeServicio.objects
                   .filter(pk=contrato.pk, estado=ContratoDeServicio.INSTALACION)
                   .update(estado=ContratoDeServicio.EN_EL_ISP, activacion_estado="",
                           activacion_detalle="", activado_en=ahora,
                           activacion_actualizada_en=ahora, updated_at=ahora))
        contrato.refresh_from_db()
        if not tocadas:
            return
        orden = contrato.orden
        try:
            foto = revisar(orden)
        except Exception:                                        # noqa: BLE001
            foto = None
        orden = aprobar(orden, profile=contrato.activado_por,
                        observacion="Instalación validada y activada en el proveedor.")
        guardar_foto(orden, foto, contrato.activado_por)
        avisar_instalacion_aprobada(orden)
        #  YA ES CLIENTE: ahora si se le escriben el costo y el serial (el
        #  proveedor no deja escribirlos en una instalacion).
        pedir_completar(contrato)


def _aplicar(contrato, estado: str, cuerpo: dict) -> None:
    from campo.contrato import ContratoDeServicio

    if estado in ("activado", "ya_estaba"):
        _activada(contrato)
    elif estado == "en_curso":
        _anotar(contrato, activacion_estado=ContratoDeServicio.ACTIVACION_EN_CURSO,
                activacion_detalle="")
    else:
        motivo = str(cuerpo.get("motivo") or "")
        _anotar(contrato, activacion_estado=ContratoDeServicio.ACTIVACION_FALLIDA,
                activacion_detalle=_POR_QUE.get(estado, "No se pudo activar.")
                + (f" ({motivo})" if motivo and estado == "fallo" else ""))


def pedir(contrato) -> None:
    """Le pide al motor que active. Solo sobre una `pedida`."""
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp
    from campo.services.ubicacion_al_isp import _nombre_de

    if (contrato.estado != ContratoDeServicio.INSTALACION
            or contrato.activacion_estado != ContratoDeServicio.ACTIVACION_PEDIDA):
        return
    actor = _nombre_de(contrato.activado_por)
    if not actor:
        _anotar(contrato, activacion_estado=ContratoDeServicio.ACTIVACION_FALLIDA,
                activacion_detalle="No se sabe quién aprobó: sin eso no se activa.")
        return
    estado, cuerpo = alta_en_el_isp._llamar(contrato, "activar-cliente", {
        #  LO MINIMO PARA RECONOCERLO (revision de PII, 27/11/2026): el motor
        #  solo usa la IP, el nombre y el documento; la ficha entera viajaba.
        "actor": actor, "datos": alta_en_el_isp.datos_para_reconocer(contrato),
        "id_servicio": contrato.servicio_isp,
        "intento": int(contrato.activacion_intento or 1)}, ESPERA_DEL_PEDIDO)
    if estado is None:
        #  Salio y no se sabe: se mira en la vuelta siguiente, sin volver a pedir.
        _anotar(contrato, activacion_estado=ContratoDeServicio.ACTIVACION_EN_CURSO)
        return
    _aplicar(contrato, estado, cuerpo)


def comprobar(contrato) -> None:
    """Mira si ya es cliente. SOLO LEE."""
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp

    if (contrato.estado != ContratoDeServicio.INSTALACION
            or contrato.activacion_estado != ContratoDeServicio.ACTIVACION_EN_CURSO):
        return
    estado, cuerpo = alta_en_el_isp._llamar(contrato, "comprobar-activacion", {
        "datos": alta_en_el_isp.datos_para_reconocer(contrato),
        "id_servicio": contrato.servicio_isp}, ESPERA_DEL_PEDIDO)
    if estado in ("activado", "ya_estaba"):
        _activada(contrato)


def rendirse(contrato) -> None:
    from campo.contrato import ContratoDeServicio

    _anotar(contrato, activacion_estado=ContratoDeServicio.ACTIVACION_POR_REVISAR,
            activacion_detalle="Se pidió y no se pudo confirmar a tiempo. Míralo en el "
                               "proveedor: si quedó como cliente, vuelve a tocar «Aprobar».")


# =============================================================================
#  EL COSTO Y EL SERIAL, AL ACTIVAR  --  26/11/2026
# =============================================================================
#  Decision del usuario: el costo de instalacion que cobro el tecnico y el
#  serial de la ONU se escriben CUANDO LA OFICINA APRUEBA y la instalacion pasa
#  a cliente. El proveedor no deja editar una instalacion por su API, y su
#  formulario web cambiaria otros datos (ver alta_de_cliente.completar en el
#  motor). Sale por la puerta humana de QUIEN APROBO, una vez por pedido, y se
#  confirma leyendo. Si no se pudo, la oficina lo ve en «Por activar» y lo
#  escribe a mano: no hay reintento solo de un «no se sabe».
VUELTAS_DE_COMPLETAR = 6
ESPERA_DE_COMPLETAR = 20

_POR_QUE_COMPLETAR = {
    "fallo": "El proveedor rechazó escribir el costo y el serial.",
    "no_encontrada": "No se encontró el cliente de este contrato en el proveedor.",
    "bloqueado": "No salió: el sistema lo frenó antes de llegar al proveedor.",
    "datos_invalidos": "El costo o el serial no son válidos.",
    "sin_herramienta": "La empresa no tiene configurado cómo escribir el costo y el serial.",
}


def _anotar_completar(contrato, **campos) -> None:
    from campo.contrato import ContratoDeServicio

    ahora = timezone.now()
    if "completar_detalle" in campos:
        campos["completar_detalle"] = str(campos["completar_detalle"] or "")[:300]
    (ContratoDeServicio.objects.filter(pk=contrato.pk, estado=ContratoDeServicio.EN_EL_ISP)
     .update(updated_at=ahora, **campos))
    contrato.refresh_from_db()


def pedir_completar(contrato) -> bool:
    """Marca el pedido y encola la tarea, DESPUES del commit. Solo sobre un
    cliente recien activado, una vez (cada pedido, un numero nuevo)."""
    from campo.contrato import ContratoDeServicio

    if contrato.estado != ContratoDeServicio.EN_EL_ISP or contrato.completar_estado not in (
            "", ContratoDeServicio.COMPLETAR_FALLIDO):
        return False
    intento = int(contrato.completar_intento or 0) + 1
    if intento > PEDIDOS_POR_CONTRATO:
        return False
    ahora = timezone.now()
    tocadas = (ContratoDeServicio.objects
               .filter(pk=contrato.pk, estado=ContratoDeServicio.EN_EL_ISP,
                       completar_intento=int(contrato.completar_intento or 0))
               .update(completar_estado=ContratoDeServicio.COMPLETAR_PEDIDO,
                       completar_detalle="", completar_intento=intento, updated_at=ahora))
    contrato.refresh_from_db()
    if not tocadas:
        return False
    org_id, contrato_id = str(contrato.org_id), str(contrato.id)

    def _encolar():
        from campo.tasks import completar_cliente_en_el_isp

        try:
            completar_cliente_en_el_isp.delay(org_id, contrato_id)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("instalacion: no se pudo encolar completar (%s)", type(e).__name__)
            try:
                _anotar_completar(ContratoDeServicio.objects.get(pk=contrato_id),
                                  completar_estado=ContratoDeServicio.COMPLETAR_FALLIDO,
                                  completar_detalle="No se pudo poner en marcha.")
            except Exception:                                    # noqa: BLE001
                pass

    transaction.on_commit(_encolar)
    return True


def completar(contrato) -> None:
    """Le pide al motor que escriba el costo y el serial. Solo sobre un
    `pedido`. Si el motor no contesta o no pudo leer, sigue `pedido` y la
    tarea lo vuelve a pedir con EL MISMO numero."""
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp
    from campo.services.ubicacion_al_isp import _nombre_de

    if (contrato.estado != ContratoDeServicio.EN_EL_ISP
            or contrato.completar_estado != ContratoDeServicio.COMPLETAR_PEDIDO):
        return
    actor = _nombre_de(contrato.activado_por)
    if not actor:
        _anotar_completar(contrato, completar_estado=ContratoDeServicio.COMPLETAR_FALLIDO,
                          completar_detalle="No se sabe quién aprobó: sin eso no se escribe.")
        return
    try:
        valores = costo_y_serial(contrato.orden)
    except Exception:                                            # noqa: BLE001
        valores = {}
    estado, cuerpo = alta_en_el_isp._llamar(contrato, "completar-cliente", {
        "actor": actor, "datos": alta_en_el_isp.datos_para_reconocer(contrato),
        "id_servicio": contrato.servicio_isp,
        "valores": {k: v for k, v in valores.items() if k in ("costo_instalacion", "serial_onu")},
        "intento": int(contrato.completar_intento or 1)}, ESPERA_DEL_PEDIDO)
    if estado is None or estado in ("en_curso", "no_se_pudo_comprobar"):
        return
    if estado in ("completado", "ya_estaba"):
        _anotar_completar(contrato, completar_estado=ContratoDeServicio.COMPLETAR_HECHO,
                          completar_detalle="")
    elif estado == "nada_que_completar":
        _anotar_completar(contrato, completar_estado=ContratoDeServicio.COMPLETAR_NADA,
                          completar_detalle="No había nada que escribir: la ONU no se activó desde la app.")
    else:
        _anotar_completar(contrato, completar_estado=ContratoDeServicio.COMPLETAR_FALLIDO,
                          completar_detalle=_POR_QUE_COMPLETAR.get(
                              estado, "No se pudieron escribir el costo y el serial."))


def rendirse_completar(contrato) -> None:
    from campo.contrato import ContratoDeServicio

    if contrato.completar_estado == ContratoDeServicio.COMPLETAR_PEDIDO:
        _anotar_completar(contrato, completar_estado=ContratoDeServicio.COMPLETAR_POR_REVISAR,
                          completar_detalle="Se pidió y no se pudo confirmar: revisa en el "
                                            "proveedor el costo de instalación y el serial.")
