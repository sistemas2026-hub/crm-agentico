# -*- coding: utf-8 -*-
"""
================================================================================
 EL CLIENTE FIRMA EL CONTRATO DEL PROVEEDOR  --  26/11/2026
================================================================================
Decisiones del usuario (Rapilink):

  * el cliente firma SOLO el contrato de WispHub, no uno de Dexter;
  * la instalacion se crea cuando el tecnico CONFIRMA el contrato;
  * la cedula (por delante y por detras) y el recibo van a «Subir Archivos»
    del cliente en WispHub (sin marcarse visibles para el cliente; al ticket
    siguen sin ir), y la app NO deja confirmar hasta que esten subidos.

EL RECORRIDO, con `ConfiguracionDeContrato.firma_en_el_proveedor` encendido
--------------------------------------------------------------------------------
1. El tecnico toma la cedula y el recibo y toca «Confirmar contrato»: el
   contrato de Dexter se guarda SIN firma (`contrato.firmar`) y se pide el alta
   COMO INSTALACION en ese momento (`contrato_views`).
2. Creada la instalacion (`alta_en_el_isp._creado`), se pide preparar el
   contrato del proveedor (`pedir`): el motor lo guarda tal como viene de su
   plantilla, sin firma, con los documentos, por la puerta humana de quien
   confirmo. Queda `lista`.
3. En la app: «Firmar en WispHub» pide el enlace (`enlace`) -- entra al portal
   del cliente SIN clave, asi que NO se guarda ni se registra: se pide cada
   vez -- y el cliente firma alli.
4. «Ya firmó: comprobar» (`comprobar_firma`) lee en el proveedor si ya tiene la
   firma (si/no) y deja el contrato `firmada`.

«NO SE» NO ES «FALLO», como en el alta: si el contrato salio y no se supo si
quedo, va `por_revisar` y NO se vuelve a mandar solo -- uno nuevo duplicaria
los documentos en el proveedor. Lo pide otra vez una persona, despues de mirar.

PRIVACIDAD. Los documentos se leen del disco y viajan al motor; no se escriben
en ningun log (errores por TIPO). El enlace no se guarda en ningun lado.
Nunca levanta lo que corre en una tarea.
================================================================================
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: El motor entra al panel, lee la instalacion y guarda con los archivos.
ESPERA_DEL_PEDIDO = 150
ESPERA_DE_LECTURA = 60
#: La tarea vuelve cada ESPERA s, hasta VUELTAS veces, si el motor no contesto
#: o no pudo leer; despues queda «por revisar».
ESPERA_ENTRE_VUELTAS = 30
VUELTAS = 6
PEDIDOS_POR_CONTRATO = 10

_POR_QUE = {
    "fallo": "El proveedor no guardó el contrato.",
    "no_encontrada": "No se encontró en el proveedor la instalación de este contrato.",
    "sin_usuario": "La instalación del proveedor no trae el usuario del cliente: sin él "
                   "no hay enlace de firma.",
    "bloqueado": "El contrato no salió: el sistema lo frenó antes de llegar al proveedor.",
    "datos_invalidos": "A los datos del contrato o a los documentos les falta algo.",
    "sin_herramienta": "La empresa no tiene configurado cómo se prepara el contrato del "
                       "proveedor.",
    "sin_documentos": "No se pudieron leer la cédula o el recibo del servidor.",
}
_NO_SE_SABE = ("Se mandó el contrato al proveedor y no se pudo confirmar si quedó. "
               "Míralo en el proveedor antes de pedirlo otra vez: pedirlo de nuevo "
               "sube los documentos otra vez.")


# =============================================================================
#  LOS DOCUMENTOS
# =============================================================================
def _privados(orden) -> dict | None:
    """`{id del requisito: titulo}` de las fotos «solo en la plataforma» de la
    plantilla de esta orden (la cedula y el recibo), o None si no se pudo leer."""
    from campo.fotos_al_ticket import requisitos_que_no_salen

    ids = requisitos_que_no_salen(orden)
    if ids is None:
        return None
    esquema = getattr(getattr(orden, "tipo_trabajo_version", None), "esquema", None) or {}
    titulos = {}
    for e in (esquema.get("evidencias") or []):
        if isinstance(e, dict) and e.get("id") in ids:
            titulos[e["id"]] = str(e.get("titulo") or e["id"])
    for i in ids:
        titulos.setdefault(i, i)
    return titulos


def _evidencias_privadas(orden, ids):
    return list(orden.evidencias
                .filter(vuelta=orden.vuelta, evento__isnull=True, requisito_id__in=list(ids))
                .order_by("recibida_en_servidor"))


def faltan_documentos(orden) -> list[str] | None:
    """Los titulos de los documentos que la plantilla pide y que todavia no
    estan en el servidor (esta vuelta). [] = estan todos. None = no se pudo
    saber, y quien llama NO confirma (fallar del lado seguro)."""
    try:
        privados = _privados(orden)
        if privados is None:
            return None
        hay = {ev.requisito_id for ev in _evidencias_privadas(orden, privados)}
        return [t for i, t in privados.items() if i not in hay]
    except Exception as e:                                       # noqa: BLE001
        logger.warning("contrato_del_proveedor: no se pudo saber que falta (%s)",
                       type(e).__name__)
        return None


def documentos_de(orden) -> list[dict] | None:
    """`[{"nombre", "tipo", "titulo", "base64"}]` de la cedula y el recibo de
    esta vuelta, o None si no se pudieron leer TODOS: un contrato no se guarda
    con documentos a medias."""
    import base64
    import os

    from campo.fotos_al_ticket import _nombre
    from campo.services.storage import CampoStorage

    try:
        privados = _privados(orden)
        if privados is None:
            return None
        evidencias = _evidencias_privadas(orden, privados)
        if {ev.requisito_id for ev in evidencias} != set(privados):
            return None
        salida, vistos = [], {}
        for i, ev in enumerate(evidencias, start=1):
            ruta = CampoStorage.ruta_absoluta(ev.storage_key)
            if not ruta or not os.path.exists(ruta):
                return None
            with open(ruta, "rb") as f:
                crudo = f.read()
            vistos[ev.requisito_id] = vistos.get(ev.requisito_id, 0) + 1
            titulo = privados[ev.requisito_id]
            if vistos[ev.requisito_id] > 1:
                titulo += f" ({vistos[ev.requisito_id]})"
            salida.append({"nombre": _nombre(ev, i), "titulo": titulo,
                           "tipo": (ev.mime_type or "image/jpeg").lower().strip(),
                           "base64": base64.b64encode(crudo).decode()})
        return salida
    except Exception as e:                                       # noqa: BLE001
        logger.warning("contrato_del_proveedor: no se pudieron leer los documentos (%s)",
                       type(e).__name__)
        return None


# =============================================================================
#  PREPARAR
# =============================================================================
def _anotar(contrato, **campos) -> None:
    from campo.contrato import ContratoDeServicio

    ahora = timezone.now()
    campos.setdefault("firma_proveedor_actualizada_en", ahora)
    if "firma_proveedor_detalle" in campos:
        campos["firma_proveedor_detalle"] = str(campos["firma_proveedor_detalle"] or "")[:300]
    (ContratoDeServicio.objects
     .filter(pk=contrato.pk, firma_en_el_proveedor=True)
     .exclude(estado=ContratoDeServicio.ANULADO)
     .update(updated_at=ahora, **campos))
    contrato.refresh_from_db()


class NoSePuedePedir(ValueError):
    """No corresponde preparar el contrato del proveedor. El texto se muestra."""


def pedir(contrato, *, por=None) -> bool:
    """Marca el contrato del proveedor como pedido y encola la tarea, DESPUES
    del commit. True si se encolo. Desde «nunca pedido», `fallida` o
    `por_revisar` (este ultimo, solo una persona: `por`). Cada pedido lleva un
    numero nuevo, y el cambio lleva su condicion en la misma sentencia."""
    from campo.contrato import ContratoDeServicio

    if not contrato.firma_en_el_proveedor:
        return False
    if contrato.estado not in (ContratoDeServicio.INSTALACION, ContratoDeServicio.EN_EL_ISP):
        return False
    desde = ["", ContratoDeServicio.FIRMA_PROVEEDOR_FALLIDA]
    if por is not None:
        desde.append(ContratoDeServicio.FIRMA_PROVEEDOR_POR_REVISAR)
    intento = int(contrato.firma_proveedor_intento or 0) + 1
    if intento > PEDIDOS_POR_CONTRATO:
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_FALLIDA,
                firma_proveedor_detalle="Se pidió demasiadas veces: revísalo en el proveedor.")
        return False
    ahora = timezone.now()
    tocadas = (ContratoDeServicio.objects
               .filter(pk=contrato.pk, firma_en_el_proveedor=True,
                       firma_proveedor_intento=int(contrato.firma_proveedor_intento or 0),
                       firma_proveedor_estado__in=desde,
                       estado__in=(ContratoDeServicio.INSTALACION,
                                   ContratoDeServicio.EN_EL_ISP))
               .update(firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_PEDIDA,
                       firma_proveedor_detalle="", firma_proveedor_avisos=[],
                       firma_proveedor_intento=intento, firma_proveedor_pedida_por=por,
                       firma_proveedor_actualizada_en=ahora, updated_at=ahora))
    contrato.refresh_from_db()
    if not tocadas:
        return False
    org_id, contrato_id = str(contrato.org_id), str(contrato.id)

    def _encolar():
        from campo.tasks import preparar_contrato_del_proveedor

        try:
            preparar_contrato_del_proveedor.delay(org_id, contrato_id)
        except Exception as e:                                   # noqa: BLE001
            logger.warning("contrato_del_proveedor: no se pudo encolar (%s)", type(e).__name__)
            try:
                _anotar(ContratoDeServicio.objects.get(pk=contrato_id),
                        firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_FALLIDA,
                        firma_proveedor_detalle="No se pudo poner en marcha. Pídelo otra vez.")
            except Exception:                                    # noqa: BLE001
                pass

    transaction.on_commit(_encolar)
    return True


def _aplicar(contrato, estado: str, cuerpo: dict) -> None:
    from campo.contrato import ContratoDeServicio

    avisos = [str(a)[:200] for a in (cuerpo.get("avisos") or [])][:5]
    if estado == "preparado":
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_LISTA,
                firma_proveedor_detalle="", firma_proveedor_avisos=avisos,
                contrato_proveedor=str(cuerpo.get("contrato_id") or "")[:64],
                usuario_proveedor=str(cuerpo.get("usuario") or "")[:200])
    elif estado in ("en_curso", "no_se_pudo_comprobar"):
        return                       # sigue pedida: la vuelta siguiente lo intenta otra vez
    elif estado == "no_se_sabe":
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_POR_REVISAR,
                firma_proveedor_detalle=_NO_SE_SABE, firma_proveedor_avisos=avisos)
    else:
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_FALLIDA,
                firma_proveedor_detalle=_POR_QUE.get(estado, "No se pudo preparar el contrato "
                                                             "del proveedor."),
                firma_proveedor_avisos=avisos)


def preparar(contrato) -> None:
    """Le pide al motor que guarde el contrato del proveedor. Solo sobre uno
    `pedida`. Si el motor no contesta, sigue `pedida`: la tarea lo vuelve a
    pedir con EL MISMO numero, y el motor no lo saca dos veces."""
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp
    from campo.services.ubicacion_al_isp import _nombre_de

    if (contrato.firma_proveedor_estado != ContratoDeServicio.FIRMA_PROVEEDOR_PEDIDA
            or contrato.estado not in (ContratoDeServicio.INSTALACION,
                                       ContratoDeServicio.EN_EL_ISP)):
        return
    actor = _nombre_de(contrato.firma_proveedor_pedida_por or contrato.firmado_por)
    if not actor:
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_FALLIDA,
                firma_proveedor_detalle="No se sabe quién confirmó el contrato: sin eso no "
                                        "se escribe en el proveedor.")
        return
    documentos = documentos_de(contrato.orden)
    if documentos is None:
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_FALLIDA,
                firma_proveedor_detalle=_POR_QUE["sin_documentos"])
        return
    estado, cuerpo = alta_en_el_isp._llamar(contrato, "preparar-contrato-proveedor", {
        "actor": actor, "datos": alta_en_el_isp.datos_para_reconocer(contrato),
        "id_servicio": contrato.servicio_isp, "archivos": documentos,
        "intento": int(contrato.firma_proveedor_intento or 1)}, ESPERA_DEL_PEDIDO)
    if estado is None:
        return
    _aplicar(contrato, estado, cuerpo)


def rendirse(contrato) -> None:
    """Se espero lo que se podia y sigue `pedida`: nadie sabe si salio."""
    from campo.contrato import ContratoDeServicio

    if contrato.firma_proveedor_estado == ContratoDeServicio.FIRMA_PROVEEDOR_PEDIDA:
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_POR_REVISAR,
                firma_proveedor_detalle=_NO_SE_SABE)


# =============================================================================
#  EL ENLACE Y LA FIRMA
# =============================================================================
class SinEnlace(ValueError):
    """No hay enlace que dar. El texto se muestra tal cual."""


def enlace(contrato) -> str:
    """El enlace para que el cliente firme. NO se guarda ni se registra: entra
    al portal del cliente sin clave. Levanta `SinEnlace` con el porque."""
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp

    if not contrato.firma_en_el_proveedor:
        raise SinEnlace("Este contrato no se firma en el proveedor.")
    if contrato.firma_proveedor_estado == ContratoDeServicio.FIRMA_PROVEEDOR_FIRMADA:
        raise SinEnlace("El cliente ya firmó el contrato.")
    if contrato.firma_proveedor_estado != ContratoDeServicio.FIRMA_PROVEEDOR_LISTA:
        raise SinEnlace("El contrato del proveedor todavía no está listo para firmar.")
    estado, cuerpo = alta_en_el_isp._llamar(contrato, "enlace-de-firma", {
        "usuario": contrato.usuario_proveedor, "id_servicio": contrato.servicio_isp},
        ESPERA_DE_LECTURA)
    valor = str((cuerpo or {}).get("enlace") or "")
    if estado != "listo" or not valor.startswith(("http://", "https://")):
        raise SinEnlace("El proveedor no dio el enlace. Intenta de nuevo en un momento.")
    return valor


def comprobar_firma(contrato):
    """Lee en el proveedor si el contrato ya tiene la firma. SOLO LEE. Devuelve
    el contrato, `firmada` si ya firmo."""
    from campo.contrato import ContratoDeServicio
    from campo.services import alta_en_el_isp

    if (not contrato.firma_en_el_proveedor or not contrato.contrato_proveedor
            or contrato.firma_proveedor_estado != ContratoDeServicio.FIRMA_PROVEEDOR_LISTA):
        return contrato
    estado, cuerpo = alta_en_el_isp._llamar(contrato, "firma-en-el-proveedor", {
        "contrato_id": contrato.contrato_proveedor}, ESPERA_DE_LECTURA)
    if estado == "listo" and (cuerpo or {}).get("firmado") is True:
        ahora = timezone.now()
        _anotar(contrato, firma_proveedor_estado=ContratoDeServicio.FIRMA_PROVEEDOR_FIRMADA,
                firma_proveedor_detalle="", firmado_en_el_proveedor_en=ahora)
    return contrato
