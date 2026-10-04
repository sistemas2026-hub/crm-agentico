# -*- coding: utf-8 -*-
"""Mandar el aviso: a Google Chat y, cuando este configurado, al telefono.

LO QUE ESTE ARCHIVO NO PUEDE HACER, Y ES LA PARTE IMPORTANTE
------------------------------------------------------------
**No puede romper el hecho que avisa.** Si el webhook de chat esta caido, la
devolucion ocurrio igual: el supervisor la hizo, la orden subio su vuelta y la
bitacora lo registro. Un aviso que falla es un aviso que falla, no una
devolucion que no pasa.

**No puede correr dentro de la transaccion.** `requerir_correccion` es
`@transaction.atomic`, y el proyecto tiene una decision congelada: *ninguna
transaccion de base abierta mientras se espera una operacion externa*. Un webhook
lento dejaria filas bloqueadas durante segundos. Por eso quien avisa se engancha
con `transaction.on_commit`, que ademas da la garantia que uno quiere: **si la
devolucion se deshace, el aviso no sale**.

**No manda datos del cliente.** Ver el encabezado de `campo/avisos.py`.
"""

from __future__ import annotations

import json
import logging
from urllib import error as urlerror
from urllib import request as urlrequest

from django.db import IntegrityError, transaction

from campo.avisos import AvisoEnviado, CanalDeAvisos, DispositivoDeTecnico

log = logging.getLogger(__name__)

#: Cuanto se espera a un webhook. Corto a proposito: esto corre despues de que el
#: supervisor ya vio su pantalla responder, pero sigue ocupando un worker.
SEGUNDOS_DE_ESPERA = 6


def avisar_devolucion(orden, requisitos: list[str], observacion: str = "") -> None:
    """Le avisa a la cuadrilla que un trabajo volvio, y QUE hay que rehacer.

    El «qué» es la diferencia con el mensaje que hoy alguien escribe a mano: el
    chat dice que te devolvieron un trabajo, y la app sabe que evidencia hay que
    tomar de nuevo. Acá van las dos cosas juntas.
    """
    titulos = _titulos_de(orden, requisitos)
    lineas = [f"🔁 Te devolvieron la OT #{orden.numero} (vuelta {orden.vuelta})"]
    if observacion:
        # Lo que escribio el supervisor. Es sobre el TRABAJO, no sobre el
        # cliente, y es lo primero que el tecnico quiere leer.
        lineas.append(f"«{observacion}»")
    if titulos:
        lineas.append("Hay que volver a tomar: " + ", ".join(titulos))

    _despachar(
        org=orden.org,
        # La clave describe el HECHO: devolver la vuelta 2 de esta orden pasa una
        # sola vez. Un reintento no vuelve a avisar.
        clave=f"devolucion|{orden.id}|{orden.vuelta}",
        texto="\n".join(lineas),
        enlace_a=orden.id,
        perfiles=_asignados(orden),
        titulo_push=f"OT #{orden.numero} devuelta",
    )


def _titulos_de(orden, requisitos: list[str]) -> list[str]:
    """«Fotografía de la medición», no «foto_medicion».

    El id es como se llama el campo; el titulo es como se lo nombra a una
    persona. Sale de la plantilla INMUTABLE de la orden, asi que un cambio
    posterior del tipo de trabajo no reescribe lo que se pidio ese dia.
    """
    try:
        evidencias = (orden.tipo_trabajo_version.esquema or {}).get("evidencias", [])
    except AttributeError:
        return list(requisitos)
    por_id = {
        e.get("id"): (e.get("titulo") or e.get("id"))
        for e in evidencias
        if isinstance(e, dict)
    }
    return [por_id.get(r, r) for r in requisitos]


def _asignados(orden) -> list:
    """Los perfiles a los que les toca este trabajo."""
    return [a.profile for a in orden.asignaciones.select_related("profile").all()]


def _despachar(*, org, clave: str, texto: str, enlace_a, perfiles, titulo_push: str):
    """Programa el envio para DESPUES del commit. Nunca antes.

    Ver el encabezado: dentro de la transaccion esto bloquearia filas esperando a
    un tercero, y ademas avisaria de algo que todavia se puede deshacer.
    """
    transaction.on_commit(
        lambda: _enviar_ahora(
            org=org,
            clave=clave,
            texto=texto,
            enlace_a=enlace_a,
            perfiles=perfiles,
            titulo_push=titulo_push,
        )
    )


def _enviar_ahora(*, org, clave, texto, enlace_a, perfiles, titulo_push):
    """El envio de verdad. Fuera de toda transaccion, y nunca lanza.

    Si algo acá explota, lo peor que puede pasar es que no llegue un aviso. Dejar
    que una excepcion suba desde un `on_commit` ensucia el log con un fallo que
    el supervisor ya no puede ver -- su peticion termino hace rato.
    """
    try:
        canal = CanalDeAvisos.objects.filter(org=org, activo=True).first()
        if canal is None:
            # Ninguna empresa nace con esto configurado. No avisar es el estado
            # por defecto y no es un error.
            return

        # IDEMPOTENCIA POR CLAVE PRIMARIA, no por un `select` previo: ahi vive la
        # carrera. Si la fila ya estaba, alguien mas ya aviso y esto no hace nada.
        try:
            with transaction.atomic():
                registro = AvisoEnviado.objects.create(org=org, clave=clave)
        except IntegrityError:
            return

        enlace = canal.enlace_a(enlace_a)
        cuerpo = texto if not enlace else f"{texto}\n{enlace}"

        canales_ok = []
        if canal.chat_webhook and _publicar_en_chat(canal.chat_webhook, cuerpo):
            canales_ok.append("chat")
        if _notificar_a_telefonos(
            org=org, perfiles=perfiles, titulo=titulo_push, texto=texto, enlace=enlace
        ):
            canales_ok.append("push")

        # Se guarda QUE canales funcionaron. Una fila con la lista vacia dice
        # "se intento y no llego por ninguno", que es distinto de "no se intento".
        registro.canales = canales_ok
        registro.save(update_fields=["canales", "updated_at"])
    except Exception:  # noqa: BLE001 -- ver el docstring
        log.warning("aviso_no_enviado", exc_info=False)


def _publicar_en_chat(webhook: str, texto: str) -> bool:
    """Publica en un espacio de Google Chat. Devuelve si llego.

    Sin dependencias nuevas: es un POST con un JSON de una sola clave. Traer un
    cliente HTTP entero para esto seria pagar una dependencia por una linea.
    """
    datos = json.dumps({"text": texto}).encode("utf-8")
    peticion = urlrequest.Request(
        webhook,
        data=datos,
        headers={"Content-Type": "application/json; charset=UTF-8"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(peticion, timeout=SEGUNDOS_DE_ESPERA) as r:
            return 200 <= r.status < 300
    except (urlerror.URLError, OSError, ValueError):
        # El webhook puede estar mal pegado, vencido o el espacio borrado. Nada
        # de eso es culpa de quien devolvio el trabajo.
        log.warning("chat_no_publicado")
        return False


def _notificar_a_telefonos(*, org, perfiles, titulo, texto, enlace) -> bool:
    """Manda la notificacion a los telefonos registrados de esos perfiles.

    QUE FALTA PARA QUE ESTO HAGA ALGO (04/10/2026)
    ----------------------------------------------
    El registro de dispositivos y el despacho estan construidos; lo que falta es
    el PROVEEDOR. Hoy devuelve `False` siempre y lo dice en el log, en vez de
    fingir que mando algo.

    Encenderlo es escribir `_enviar_una(token, ...)` contra FCM y nada mas: el
    resto --a quien, con que texto, sin datos del cliente, sin duplicar-- ya esta
    resuelto acá.

    Y hay una pregunta que se contesta ANTES de encenderlo, no despues: el token
    del dispositivo viaja a un tercero. En este proyecto eso no se activa sin
    resolver la autorizacion de tratamiento. Por eso el canal de chat va primero:
    Google Chat ya esta en la operacion y el aviso no lleva datos del cliente.
    """
    ids = [p.id for p in perfiles if p is not None]
    if not ids:
        return False

    tokens = list(
        DispositivoDeTecnico.objects.filter(
            org=org, profile_id__in=ids, activo=True
        ).values_list("token", flat=True)
    )
    if not tokens:
        return False

    enviados = [t for t in tokens if _enviar_una(t, titulo, texto, enlace)]
    return bool(enviados)


def _enviar_una(token: str, titulo: str, texto: str, enlace: str) -> bool:
    """Un envio al proveedor de notificaciones. Todavia no hay proveedor.

    Devuelve `False` a proposito: decir que no se mando es la verdad, y el
    registro de `AvisoEnviado` queda con `canales: ["chat"]` --o vacio-- en vez
    de afirmar un envio que no ocurrio.
    """
    log.info("push_sin_proveedor")
    return False
