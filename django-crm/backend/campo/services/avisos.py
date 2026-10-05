# -*- coding: utf-8 -*-
"""Mandar el aviso por los canales que la empresa configuro.

LO QUE ESTE ARCHIVO NO PUEDE HACER, Y ES LA PARTE IMPORTANTE
------------------------------------------------------------
**No puede romper el hecho que avisa.** Si el webhook esta caido, la devolucion
ocurrio igual: el supervisor la hizo, la orden subio su vuelta y la bitacora lo
registro. Un aviso que falla es un aviso que falla, no una devolucion que no
pasa.

**No puede correr dentro de la transaccion.** `requerir_correccion` es
`@transaction.atomic`, y el proyecto tiene una decision congelada: *ninguna
transaccion de base abierta mientras se espera una operacion externa*. Un webhook
lento dejaria filas bloqueadas durante segundos. Por eso quien avisa se engancha
con `transaction.on_commit`, que ademas da la garantia que uno quiere: **si la
devolucion se deshace, el aviso no sale**.

**No manda datos del cliente.** Ver el encabezado de `campo/avisos.py`.

UN PROVEEDOR NUEVO ES UNA LINEA, NO UNA CLASE
---------------------------------------------
Google Chat, Slack, Teams y Discord son el mismo gesto: un POST con un JSON de
una clave. La diferencia --como se llama esa clave-- esta en una tabla del
modelo. Agregar Mattermost manana es agregar una fila ahi.
"""

from __future__ import annotations

import json
import logging
from urllib import error as urlerror
from urllib import request as urlrequest

from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from campo.services import push_fcm

from campo.avisos import (
    AvisoEnviado,
    CanalDeAvisos,
    ConfiguracionDeAvisos,
    DispositivoDeTecnico,
)

log = logging.getLogger(__name__)

#: Cuanto se espera a un webhook. Corto a proposito: esto corre despues de que el
#: supervisor ya vio su pantalla responder, pero sigue ocupando un worker.
SEGUNDOS_DE_ESPERA = 6


def avisar_devolucion(orden, requisitos: list[str], observacion: str = "") -> None:
    """Le avisa a la cuadrilla que un trabajo volvio, y QUE hay que rehacer.

    El «que» es la diferencia con el mensaje que hoy alguien escribe a mano: el
    chat dice que te devolvieron un trabajo, y la app sabe que evidencia hay que
    tomar de nuevo. Aca van las dos cosas juntas.
    """
    titulos = _titulos_de(orden, requisitos)
    lineas = [f"🔁 Te devolvieron la OT #{orden.numero} (vuelta {orden.vuelta})"]
    if observacion:
        # Lo que escribio el supervisor. Es sobre el TRABAJO, no sobre el
        # cliente, y es lo primero que el tecnico quiere leer.
        lineas.append(f"«{observacion}»")
    if titulos:
        lineas.append("Hay que volver a tomar: " + ", ".join(titulos))

    perfiles = _asignados(orden)

    # El contenido del aviso, construido UNA vez. Lo escribe la notificacion de
    # la plataforma y VIAJA TAMBIEN EN EL PUSH, y eso no es duplicacion: el
    # telefono espeja la fila al recibirla, y una fila espejada a medias se
    # queda a medias. `guardarNotificaciones` inserta sin pisar --para no
    # perder un «leida» que todavia no subio--, asi que la sincronizacion
    # posterior NO la completaria.
    contenido = {
        "vuelta": orden.vuelta,
        "observacion": observacion,
        "rehacer": titulos,
        "orden_numero": orden.numero,
    }

    # 1. LA NOTIFICACION, QUE ES EL HECHO
    # -----------------------------------
    # Va DENTRO de la transaccion, al reves que el envio de abajo. No es una
    # inconsistencia: la notificacion es parte del hecho --si la devolucion se
    # deshace, la notificacion tiene que deshacerse con ella-- mientras que
    # mandarla por un canal externo es una ENTREGA, y una entrega no puede
    # bloquear filas esperando a un tercero.
    #
    # Es la misma distincion que el proyecto ya tiene escrita para los mensajes:
    # `aceptado != entregado != leido`.
    avisos_por_perfil = _notificar_en_la_app(orden, perfiles, contenido)

    # 2. LAS ENTREGAS, que son opcionales y van despues del commit.
    _despachar(
        org=orden.org,
        # La clave describe el HECHO: devolver la vuelta 2 de esta orden pasa una
        # sola vez. Un reintento no vuelve a avisar.
        clave=f"devolucion|{orden.id}|{orden.vuelta}",
        asunto=f"OT #{orden.numero} devuelta",
        texto="\n".join(lineas),
        enlace_a=orden.id,
        perfiles=perfiles,
        # El push necesita DOS cosas que los canales externos no: el enlace
        # relativo --el telefono no navega a un dominio-- y el id de la
        # notificacion de cada persona, para que el aviso que llega por push sea
        # LA MISMA fila que despues baja la sincronizacion y no una copia.
        enlace_interno=f"/ot/{orden.id}",
        avisos_por_perfil=avisos_por_perfil,
        contenido=contenido,
    )


def _notificar_en_la_app(orden, perfiles, contenido: dict):
    """Escribe una notificacion por persona, con el despachador que YA existe.

    POR QUE NO SE CONSTRUYO UNO NUEVO
    ---------------------------------
    `common/notifications.py` es el unico punto de llamada de toda la plataforma
    --watchers, menciones, escalamientos-- y su propio encabezado dice «y futuras
    apps». Campo era la unica parte que no lo usaba: se habia ido a buscar un
    canal hacia afuera teniendo el mecanismo adentro.

    Con esto el supervisor la ve en su campanita y el tecnico en su aplicacion,
    sin que ninguna empresa configure nada. Los canales externos --chat, correo--
    quedan como lo que son: ENTREGAS opcionales de esto.

    QUE VA EN `data`, Y QUE NO
    --------------------------
    Lo que hace falta para actuar: la vuelta, que hay que rehacer y lo que
    escribio el supervisor. **Ni nombre, ni direccion, ni telefono del cliente**:
    una notificacion se sincroniza al telefono y se queda ahi, y el detalle del
    cliente ya vive en la ficha, detras de la sesion.

    Devuelve `{profile_id: notificacion_id}`. Lo usa el push: sin el id, el
    aviso que llega al telefono seria una fila nueva, y la sincronizacion
    traeria la misma notificacion otra vez, sin leer.
    """
    from common import notifications

    ids: dict = {}
    for perfil in perfiles:
        notificacion = notifications.create(
            perfil,
            "trabajo_devuelto",
            entity=orden,
            entity_name=f"OT #{orden.numero}",
            # Relativo: quien lo abre ya esta autenticado, y el dominio lo pone
            # cada cliente. Un absoluto obligaria a que la notificacion sepa si
            # la lee la web o el telefono.
            link=f"/ot/{orden.id}",
            data=contenido,
        )
        # Puede devolver None: a una persona desactivada no se le notifica. Ese
        # caso no se filtra aca --el perfil sigue en la lista para los canales
        # externos-- pero tampoco entra al push, porque no hay fila que espejar.
        if notificacion is not None:
            ids[perfil.id] = str(notificacion.id)
    return ids


def _titulos_de(orden, requisitos: list[str]) -> list[str]:
    """«Fotografia de la medicion», no `foto_medicion`.

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


def _despachar(
    *,
    org,
    clave: str,
    asunto: str,
    texto: str,
    enlace_a,
    perfiles,
    enlace_interno: str = "",
    avisos_por_perfil=None,
    contenido=None,
):
    """Programa el envio para DESPUES del commit. Nunca antes.

    Ver el encabezado: dentro de la transaccion esto bloquearia filas esperando a
    un tercero, y ademas avisaria de algo que todavia se puede deshacer.
    """
    transaction.on_commit(
        lambda: _enviar_ahora(
            org=org,
            clave=clave,
            asunto=asunto,
            texto=texto,
            enlace_a=enlace_a,
            perfiles=perfiles,
            enlace_interno=enlace_interno,
            avisos_por_perfil=avisos_por_perfil or {},
            contenido=contenido or {},
        )
    )


def _enviar_ahora(
    *, org, clave, asunto, texto, enlace_a, perfiles,
    enlace_interno="", avisos_por_perfil=None, contenido=None,
):
    """El envio de verdad. Fuera de toda transaccion, y nunca lanza.

    Si algo aca explota, lo peor que puede pasar es que no llegue un aviso. Dejar
    que una excepcion suba desde un `on_commit` ensucia el log con un fallo que
    el supervisor ya no puede ver -- su peticion termino hace rato.
    """
    try:
        canales = list(CanalDeAvisos.objects.filter(org=org, activo=True))
        perfiles_reales = [p for p in perfiles if p is not None]
        hay_push = (
            DispositivoDeTecnico.objects.filter(
                org=org, activo=True, profile__in=perfiles_reales
            ).exists()
            if perfiles_reales
            else False
        )
        if not canales and not hay_push:
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

        enlace = _enlace_de(org, enlace_a)
        cuerpo = texto if not enlace else f"{texto}\n{enlace}"

        usados = []
        for canal in canales:
            if enviar_por(canal, asunto=asunto, texto=cuerpo):
                usados.append(canal.tipo)
        # Al telefono va el enlace INTERNO, no el del dominio: la app abre
        # `/ot/<id>` en su propia pantalla. Si le llegara el absoluto, tocar el
        # aviso abriria el navegador --y pediria iniciar sesion en la web--.
        if _notificar_a_telefonos(
            org=org,
            perfiles=perfiles,
            titulo=asunto,
            texto=texto,
            enlace=enlace_interno or enlace,
            avisos_por_perfil=avisos_por_perfil or {},
            contenido=contenido or {},
        ):
            usados.append("push")

        # Se guarda QUE canales funcionaron. Una lista vacia dice «se intento y no
        # llego por ninguno», que es distinto de «no se intento».
        registro.canales = usados
        registro.save(update_fields=["canales", "updated_at"])
    except Exception:  # noqa: BLE001 -- ver el docstring
        log.warning("aviso_no_enviado", exc_info=False)


def _enlace_de(org, orden_id) -> str:
    """El enlace a la orden, segun el dominio que configuro la empresa."""
    config = ConfiguracionDeAvisos.objects.filter(org=org).first()
    return config.enlace_a(orden_id) if config else ""


def enviar_por(canal, *, asunto: str, texto: str) -> bool:
    """Manda por UN canal. Devuelve si llego.

    Publica a proposito --sin guion bajo--: la pantalla de configuracion la usa
    para el boton de probar. Probar y avisar tienen que recorrer exactamente el
    mismo camino, o la prueba deja de probar lo que importa.
    """
    if canal.tipo == CanalDeAvisos.CORREO:
        return _mandar_correo(canal.destino, asunto, texto)
    clave = CanalDeAvisos.CLAVE_DEL_TEXTO.get(canal.tipo, "text")
    return _publicar_en_webhook(canal.destino, clave, texto)


def _publicar_en_webhook(url: str, clave: str, texto: str) -> bool:
    """Un POST con un JSON de una clave. Eso es todo lo que piden.

    Sin dependencias nuevas: traer un cliente HTTP entero para esto seria pagar
    una dependencia por una linea.
    """
    datos = json.dumps({clave: texto}).encode("utf-8")
    peticion = urlrequest.Request(
        url,
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
        log.warning("webhook_no_publicado")
        return False


def _mandar_correo(direccion: str, asunto: str, texto: str) -> bool:
    """El minimo comun denominador: funciona sin configurar nada del otro lado."""
    try:
        enviados = send_mail(
            subject=asunto,
            message=texto,
            from_email=None,  # usa DEFAULT_FROM_EMAIL
            recipient_list=[direccion],
            fail_silently=False,
        )
        return bool(enviados)
    except Exception:  # noqa: BLE001 -- un correo caido no rompe nada
        log.warning("correo_no_enviado")
        return False


def probar(canal) -> tuple[bool, str]:
    """Manda un mensaje de prueba y deja escrito como fue.

    POR QUE LA PANTALLA TIENE ESTE BOTON
    ------------------------------------
    Pegar una URL y no saber si sirve es como se pudren estas configuraciones:
    alguien la carga, nadie la prueba, y el dia que hay una devolucion el aviso
    no llega y nadie sabe desde cuando.

    Recorre el MISMO camino que un aviso de verdad. Una prueba que usa otro
    camino prueba otra cosa.
    """
    ok = enviar_por(
        canal,
        asunto="Prueba de avisos",
        texto=(
            "✅ Prueba de Dexter Campo.\n"
            "Si estás leyendo esto, los avisos de trabajos devueltos van a "
            "llegar acá."
        ),
    )
    canal.probado_en = timezone.now()
    canal.ultimo_error = "" if ok else "No se pudo entregar."
    canal.save(update_fields=["probado_en", "ultimo_error", "updated_at"])
    return ok, canal.ultimo_error


def _notificar_a_telefonos(
    *, org, perfiles, titulo, texto, enlace, avisos_por_perfil=None, contenido=None
) -> bool:
    """Manda la notificacion a los telefonos registrados de esos perfiles.

    EL TOKEN QUE NO SIRVE SE DA DE BAJA ACA MISMO
    ---------------------------------------------
    FCM distingue «no llego» de «este telefono no existe mas», y la diferencia
    importa: lo primero se puede reintentar, lo segundo no. Un token muerto que
    se deja activo hace que cada aviso futuro pague un viaje a Google para que lo
    rechacen, y deja a `AvisoEnviado` contando intentos que no podian funcionar.
    Se desactiva, no se borra, por lo mismo que en `DispositivoDeCampoView`: que
    dejo de servir y CUANDO es lo que permite contestar por que un aviso no
    llego.

    DEVUELVE SI LLEGO A ALGUNO, NO SI LLEGO A TODOS
    -----------------------------------------------
    Un tecnico puede tener dos telefonos registrados y uno apagado. Que el aviso
    haya entrado por uno ya cumple el proposito; exigir los dos marcaria como
    fallido un aviso que la persona recibio.
    """
    ids = [p.id for p in perfiles if p is not None]
    if not ids:
        return False

    telefonos = list(
        DispositivoDeTecnico.objects.filter(
            org=org, profile_id__in=ids, activo=True
        ).values_list("token", "profile_id")
    )
    if not telefonos:
        return False

    if not push_fcm.esta_configurado():
        # Sin credencial no se intenta: un viaje a Google que va a fallar seguro
        # solo demora el aviso por los canales que SI estan configurados.
        log.info("push_sin_proveedor")
        return False

    por_perfil = avisos_por_perfil or {}
    llego = False
    muertos = []
    for token, profile_id in telefonos:
        resultado = _enviar_una(
            token,
            titulo,
            texto,
            enlace,
            por_perfil.get(profile_id, ""),
            contenido or {},
        )
        if resultado == push_fcm.ENTREGADO:
            llego = True
        elif resultado == push_fcm.TOKEN_MUERTO:
            muertos.append(token)

    if muertos:
        DispositivoDeTecnico.objects.filter(org=org, token__in=muertos).update(
            activo=False, updated_at=timezone.now()
        )

    return llego


def _enviar_una(
    token: str,
    titulo: str,
    texto: str,
    enlace: str,
    aviso_id: str = "",
    contenido: dict | None = None,
) -> str:
    """Un envio al proveedor. Devuelve el resultado de `push_fcm`, sin traducir.

    Sigue existiendo como funcion propia --y no una llamada directa-- porque es
    el unico punto donde se sustituye el proveedor en una prueba. Traducir el
    resultado a un booleano aca borraria justo la distincion que hace falta mas
    arriba: un token muerto no es un envio fallido.
    """
    return push_fcm.mandar_a_un_telefono(
        token,
        titulo,
        texto,
        enlace,
        aviso_id=aviso_id,
        verbo="trabajo_devuelto",
        contenido=contenido or {},
    )


def avisar_pedido_de_material(pedido) -> None:
    """Le avisa a bodega que un tecnico esta pidiendo material.

    POR QUE POR LOS MISMOS CANALES Y NO POR UNA BANDEJA NUEVA
    ---------------------------------------------------------
    Bodega ya recibe los avisos de esta empresa por donde los configuro --el
    chat, el correo--. Construirle una pantalla aparte seria pedirle que mire
    dos lugares, y la que mira menos es siempre la nueva.

    QUE LLEVA, Y QUE NO
    -------------------
    El material, cuanto, quien lo pide y para que orden si la hay. **Ningun dato
    del cliente**: a bodega no le hace falta saber a quien se le instala para
    sacar veinte conectores de una caja, y este mensaje sale del sistema igual
    que todos los demas.

    No puede romper el pedido. Si el chat esta caido, el pedido existe igual --y
    el tecnico lo ve en su lista-- porque el hecho es la fila, no el mensaje.
    """
    lineas = [f"📦 {pedido.profile_id and _nombre_de(pedido.profile)} pide material"]
    lineas.append(f"{_cantidad_legible(pedido.cantidad)} de {pedido.material.nombre}")
    if pedido.orden_id is not None:
        lineas.append(f"Para la OT #{pedido.orden.numero}")
    if pedido.motivo:
        lineas.append(f"«{pedido.motivo}»")

    _despachar(
        org=pedido.org,
        # La clave describe el HECHO: este pedido, una vez. Un reintento de la
        # cola no vuelve a avisar.
        clave=f"pedido_material|{pedido.id}",
        asunto=f"Pedido de material: {pedido.material.nombre}",
        texto="\n".join(lineas),
        enlace_a=pedido.orden_id,
        perfiles=[],
    )


def _nombre_de(profile) -> str:
    """El nombre de quien pide. Es un COMPAÑERO, no un cliente, y por eso va.

    Bodega tiene que saber a quien entregarle. Sin nombre, el pedido es una
    cantidad flotando.
    """
    try:
        return (profile.user.name or profile.user.email or "Un técnico").strip()
    except AttributeError:
        return "Un técnico"


def _cantidad_legible(valor) -> str:
    """Sin ceros de relleno: «20», no «20.000».

    PostgreSQL devuelve el Decimal con la escala de la columna, y en Colombia el
    punto separa MILES: «20.000 conectores» se lee como veinte mil.
    """
    texto = str(valor)
    if "." not in texto:
        return texto
    return texto.rstrip("0").rstrip(".") or "0"
