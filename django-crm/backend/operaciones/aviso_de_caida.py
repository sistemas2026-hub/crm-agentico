# -*- coding: utf-8 -*-
"""
================================================================================
 AVISARLE UNA CAIDA DE RED A SUS CLIENTES  --  30/10/2026 (PRD §8.17, Ola 2)
================================================================================

Cuando se cae un PON, sus clientes escriben todos a la vez "no tengo internet".
Avisarles primero es la reduccion de volumen mas grande que hay -- y estaba
decidido que lo APRUEBE UNA PERSONA antes de mandar. Esto es ese circuito:

  1. 'vista_previa': a cuantos clientes se les avisaria. Lo calcula el motor
     (nucleo/seguimiento/aviso_de_caida.py): solo los equipos que cayeron
     JUNTOS, cruzados con el padron del ISP, en un estado que la empresa
     declaro. Aca llegan conteos, no nombres.
  2. 'aprobar': una persona lo confirma. Queda escrito quien y cuando (la fila
     AvisoDeCaida y un evento en la linea de tiempo de la situacion), y arranca
     el envio. Una sola vez por situacion: lo garantiza la base.
  3. 'avanzar': un lote por vuelta, con una pausa entre lotes. El motor vuelve
     a leer quienes SIGUEN en la falla en cada lote y descarta al resto: un
     cliente cuyo equipo volvio no recibe un aviso viejo. Si la situacion se
     resolvio o se descarto, el envio se DETIENE.

QUE CAIDAS SE AVISAN: las de PON con alerta de fibra ('los', 'partial_los').
Un corte de energia ('power') no es una falla del ISP: decir "estamos
arreglando la red" seria falso. 'offline' no dice que paso: tampoco.
================================================================================
"""

from __future__ import annotations

import logging
import os
import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from operaciones import situaciones as svc
from operaciones.aviso_de_caida_modelos import AvisoDeCaida
from operaciones.situaciones_modelos import SituacionOperativa, TipoAfectado, TipoEvento

logger = logging.getLogger(__name__)
S = SituacionOperativa

TIPOS_QUE_SE_AVISAN = frozenset({"los", "partial_los"})
VIVOS = frozenset({S.DETECTADA, S.INVESTIGANDO, S.CONFIRMADA, S.EN_ATENCION})
#: Pausa entre lotes. La calidad del numero de la empresa en Meta baja si salen
#: cientos de plantillas de golpe.
ESPERA_ENTRE_LOTES_S = 60
#: Si el motor no contesta, cuando volver.
ESPERA_SI_EL_MOTOR_NO_CONTESTA_S = 300
#: Tope de vueltas: un envio que no termina no queda vivo para siempre.
MAX_VUELTAS = 60


class NoAvisable(Exception):
    """Por que no se puede avisar esta caida, con un codigo fijo."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


def _pon(situacion):
    return next((a for a in situacion.afectados.all() if a.tipo == TipoAfectado.PON), None)


def puerto_de(situacion) -> tuple[str, str, str] | None:
    """('3', '2', '11') desde el PON afectado ('olt/placa/puerto'), o None."""
    pon = _pon(situacion)
    partes = str(pon.identificador if pon else "").split("/")
    if len(partes) != 3 or not all(re.fullmatch(r"\d{1,6}", p) for p in partes):
        return None
    return partes[0], partes[1], partes[2]


def por_que_no(situacion) -> str | None:
    """None si esta caida se puede avisar; si no, por que."""
    if situacion.tipo != S.AFECTACION_PON:
        return "no_es_de_pon"
    if situacion.estado not in VIVOS:
        return "ya_no_esta_activa"
    pon = _pon(situacion)
    tipo = str(((pon.datos or {}) if pon else {}).get("tipo_alerta") or "")
    if tipo == "power":
        return "corte_de_energia"
    if tipo not in TIPOS_QUE_SE_AVISAN:
        return "alerta_sin_aviso"
    if puerto_de(situacion) is None:
        return "sin_puerto"
    return None


def _motor_y_empresa(org_id):
    from operaciones import areas_del_tenant

    url = os.environ.get("ASISTENTE_URL")
    tenant = areas_del_tenant.tenant_de_organizacion(org_id)
    if not url or not tenant:
        raise NoAvisable("NO_CONFIGURADO")
    return url.rstrip("/"), tenant


def _pedir(url, ruta, cuerpo):
    """(http, json) del motor, o None si no contesto."""
    import requests

    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.post(f"{url}{ruta}", json=cuerpo, headers=cabeceras, timeout=60)
        return r.status_code, (r.json() if r.content else {})
    except Exception:  # noqa: BLE001 -- un motor caido no rompe la pantalla
        logger.warning("aviso de caida: el motor no contesto (%s)", ruta)
        return None


def _afectados(situacion) -> dict:
    url, tenant = _motor_y_empresa(situacion.org_id)
    olt, board, port = puerto_de(situacion)
    respuesta = _pedir(url, "/avisos/caida/afectados",
                       {"tenant": tenant, "olt": olt, "board": board, "port": port})
    if respuesta is None:
        raise NoAvisable("MOTOR_NO_CONTESTA")
    http, datos = respuesta
    if http >= 400:
        raise NoAvisable(str(datos.get("error") or "MOTOR_RECHAZO"))
    return datos


def vista_previa(situacion) -> dict:
    """
    Lo que la persona mira antes de aprobar: a cuantos clientes, cuantos
    equipos caidos quedan afuera y por que. O {'cargando': True}.
    """
    motivo = por_que_no(situacion)
    if motivo:
        raise NoAvisable(motivo)
    datos = _afectados(situacion)
    if datos.get("cargando"):
        return {"cargando": True}
    return {"clientes": len(datos.get("servicios") or []),
            "equipos_en_falla": datos.get("equipos_en_falla", 0),
            "sin_cliente": datos.get("sin_cliente", 0),
            "fuera_de_estado": datos.get("fuera_de_estado", 0),
            "desde": datos.get("desde"),
            "motivo": datos.get("motivo"),
            #  Si el aviso no puede salir (apagado, sin plantilla aprobada), se
            #  dice ACA, antes de que alguien apruebe.
            "no_listo": datos.get("no_listo"),
            "modo_prueba": bool(datos.get("modo_prueba"))}


def aprobar(situacion, profile) -> AvisoDeCaida:
    """Una persona aprueba el aviso: queda escrito quien, y arranca el envio."""
    if profile is None:
        raise NoAvisable("FALTA_QUIEN_APRUEBA")
    motivo = por_que_no(situacion)
    if motivo:
        raise NoAvisable(motivo)
    if AvisoDeCaida.objects.filter(situacion=situacion).exists():
        raise NoAvisable("YA_APROBADO")
    #  La lista se arma AHORA, no la de la vista previa: entre mirar y aprobar
    #  pudo volver gente.
    datos = _afectados(situacion)
    if datos.get("cargando"):
        raise NoAvisable("CARGANDO")
    if datos.get("no_listo"):
        #  Aprobar un aviso que no puede salir consumiria la aprobacion: cada
        #  lote volveria con 'apagado' y nadie se enteraria de la caida.
        raise NoAvisable(f"AVISO_{str(datos['no_listo']).upper()}")
    servicios = [str(s) for s in (datos.get("servicios") or [])]
    if not servicios:
        raise NoAvisable("SIN_CLIENTES")
    olt, board, port = puerto_de(situacion)
    try:
        with transaction.atomic():
            aviso = AvisoDeCaida.objects.create(
                org=situacion.org, situacion=situacion, aprobado_por=profile,
                aprobado_en=timezone.now(), olt=olt, board=board, port=port,
                servicios=servicios, pendientes=list(servicios),
                lote=int(datos.get("lote") or 25))
            svc.anotar(situacion, TipoEvento.COORDINACION,
                       f"Aviso de la caída aprobado para {len(servicios)} clientes",
                       datos={"aviso_de_caida": str(aviso.id), "clientes": len(servicios)},
                       actor=profile)
    except IntegrityError:
        #  Dos personas aprobaron a la vez: decide la base, y es la misma respuesta.
        raise NoAvisable("YA_APROBADO")
    aviso_id, org_id = str(aviso.id), str(situacion.org_id)
    transaction.on_commit(lambda: _pedir_vuelta(aviso_id, org_id, 0))
    return aviso


def _pedir_vuelta(aviso_id, org_id, espera):
    try:
        from operaciones.tasks import avanzar_aviso_de_caida

        avanzar_aviso_de_caida.apply_async(args=[aviso_id, org_id], countdown=espera)
    except Exception:  # noqa: BLE001 -- un broker caido no deshace la aprobacion
        logger.exception("aviso de caida: no se pudo agendar la vuelta (%s)", aviso_id)


def avanzar(aviso: AvisoDeCaida) -> int | None:
    """
    Manda el siguiente lote. Devuelve en cuantos segundos volver, o None si el
    envio termino (o se detuvo).
    """
    if aviso.estado != AvisoDeCaida.EN_CURSO:
        return None
    situacion = aviso.situacion
    if situacion.estado not in VIVOS:
        return _cerrar(aviso, AvisoDeCaida.DETENIDO)
    if not aviso.pendientes:
        return _cerrar(aviso, AvisoDeCaida.TERMINADO)
    if aviso.vueltas >= MAX_VUELTAS:
        logger.warning("aviso de caida: tope de vueltas (%s), quedan %s", aviso.id, len(aviso.pendientes))
        return _cerrar(aviso, AvisoDeCaida.TERMINADO)
    try:
        url, tenant = _motor_y_empresa(aviso.org_id)
    except NoAvisable:
        return _cerrar(aviso, AvisoDeCaida.DETENIDO)
    lote, resto = aviso.pendientes[:aviso.lote], aviso.pendientes[aviso.lote:]
    respuesta = _pedir(url, "/avisos/caida/lote", {
        "tenant": tenant, "olt": aviso.olt, "board": aviso.board, "port": aviso.port,
        "situacion": str(situacion.id), "servicios": lote,
        #  Quien aprobo, por su id: el motor exige una persona, no su nombre.
        "autor": f"profile:{aviso.aprobado_por_id}"})
    aviso.vueltas += 1
    if respuesta is None or respuesta[0] >= 500:
        aviso.save(update_fields=["vueltas", "updated_at"])
        return ESPERA_SI_EL_MOTOR_NO_CONTESTA_S
    http, datos = respuesta
    if http >= 400:
        logger.warning("aviso de caida: el motor rechazo el lote (%s): %s", aviso.id, datos.get("error"))
        return _cerrar(aviso, AvisoDeCaida.DETENIDO)
    aviso.enviados += int(datos.get("enviados") or 0)
    aviso.descartados += int(datos.get("descartados") or 0)
    motivos = dict(aviso.motivos or {})
    for k, v in (datos.get("motivos") or {}).items():
        motivos[k] = motivos.get(k, 0) + int(v)
    aviso.motivos = motivos
    pendientes_del_motor = [str(s) for s in (datos.get("pendientes") or []) if str(s) in set(lote)]
    aviso.pendientes = pendientes_del_motor + resto
    aviso.save(update_fields=["enviados", "descartados", "motivos", "pendientes", "vueltas",
                              "updated_at"])
    if not aviso.pendientes:
        return _cerrar(aviso, AvisoDeCaida.TERMINADO)
    if datos.get("reintentar_en"):
        return max(int(datos["reintentar_en"]), ESPERA_ENTRE_LOTES_S)
    return ESPERA_ENTRE_LOTES_S


def _cerrar(aviso, estado) -> None:
    aviso.estado = estado
    aviso.terminado_en = timezone.now()
    aviso.save(update_fields=["estado", "terminado_en", "updated_at"])
    return None


def resumen(aviso: AvisoDeCaida | None) -> dict | None:
    """Lo que la pantalla muestra del aviso. Sin servicios: conteos."""
    if aviso is None:
        return None
    return {"estado": aviso.estado, "clientes": len(aviso.servicios or []),
            "enviados": aviso.enviados, "descartados": aviso.descartados,
            "pendientes": len(aviso.pendientes or []), "motivos": aviso.motivos or {},
            "aprobado_en": aviso.aprobado_en.isoformat(),
            "aprobado_por": _nombre(aviso.aprobado_por),
            "terminado_en": aviso.terminado_en.isoformat() if aviso.terminado_en else None}


def _nombre(profile) -> str:
    if profile is None:
        return ""
    user = getattr(profile, "user", None)
    return ((getattr(user, "name", "") or "").strip() or getattr(user, "email", "") or "") if user else ""
