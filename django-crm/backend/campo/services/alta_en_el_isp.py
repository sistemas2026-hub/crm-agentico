# -*- coding: utf-8 -*-
"""Crear en el ISP al cliente de un contrato firmado  --  25/11/2026.

Decision del usuario, planeando el formato de instalacion: *«que el tecnico
solo valide y confirme y asi se genere en WispHub»*. Hasta hoy el contrato se
firmaba en la app y despues alguien tecleaba al cliente en el panel del
proveedor.

POR QUE PASA POR EL MOTOR Y NO LE PEGA AL ISP DIRECTO. Lo mismo que la
ubicacion (`ubicacion_al_isp.py`): Django nunca escribe en los sistemas del ISP
por su cuenta. La credencial vive solo en el motor, y la frontera --puerta
humana, interruptor, idempotencia-- tambien. La ruta es DEDICADA
(`/interno/contrato/<id>/crear-cliente`): la generica es la puerta autonoma.

POR QUE NO VA DENTRO DE LA FIRMA. La app espera 20 segundos una respuesta
(`api_client.dart`), y el proveedor crea en segundo plano: entre pedir y ver al
cliente creado pueden pasar mas. Y CLAUDE.md 12: ninguna transaccion de base
abierta mientras se espera una operacion externa. Firmar guarda el contrato y
contesta; el alta corre despues, en una tarea (`campo.tasks.crear_cliente_en_el_isp`).

«NO SE» NO ES «FALLO»  --  auditoria de frontera, el mismo dia
-------------------------------------------------------------
La primera version dejaba el alta `fallida` tambien cuando nadie sabia si el
proveedor habia creado al cliente, y un contrato `fallida` se puede anular. Y
el mensaje llegaba a decir «anula y firma otro con otra IP». Con el primer
cliente quiza ya creado, seguir ese consejo era crear DOS.

Ahora el alta tiene un estado para eso, `por_revisar`, y tres reglas:

  * `fallida` significa SIEMPRE que no hay cliente: el proveedor dijo que no,
    o nunca llegamos a pedirselo. Solo de ahi se puede reintentar o anular.
  * `por_revisar` significa que NADIE SABE: se pidio y el cliente no aparecio
    en el tiempo que se pudo esperar, o la IP quedo tomada por una ficha que
    no se reconoce. No se anula ni se reintenta. Lo resuelve una persona de
    GESTION despues de mirar en el proveedor: «si quedo, este es su numero» o
    «no quedo». Queda escrito quien lo dijo.
  * Una IP «ocupada por otro» solo se cree cuando NUNCA se habia pedido nada
    para ese contrato. Si ya se habia pedido, el que la tiene puede ser el
    nuestro: va a `por_revisar`.

QUE GARANTIZA ESTE LADO Y QUE NO. Este modulo no decide si se puede crear: eso
lo comprueba el motor, pegado a la escritura. Aca se decide CUANDO pedirlo, con
que numero de pedido, y se deja escrito como termino.

  * UN PEDIDO A LA VEZ. Marcar el alta como pedida es un cambio con condicion
    en la misma sentencia: dos toques seguidos encolan una sola tarea.
  * EL NUMERO DE PEDIDO SUBE SOLO CUANDO ALGUIEN LO PIDE: la firma (el 1) o
    una persona que toca «volver a intentar». Las vueltas de la tarea y los
    reintentos de red repiten el numero, y el motor no saca dos veces el
    mismo. Como solo se puede pedir desde «nunca pedido» o `fallida`, un
    numero nuevo nunca convive con un pedido anterior sin resolver.
  * SI EL MOTOR NO CONTESTA, NO SE SABE: el pedido sigue `pedida` y la tarea
    vuelve a pedirlo con EL MISMO numero.

PRIVACIDAD. Lo que viaja al motor son los datos de una persona. No se escriben
en ningun log: los errores van por TIPO, nunca con su texto. Para volver a
mirar un alta en curso viaja solo lo que hace falta para reconocer al cliente.

Nunca levanta: lo llama una tarea, y una excepcion ahi se pierde sin rastro.
"""
from __future__ import annotations

import logging
import os
import re

import requests
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: El motor espera hasta 25 s a que el cliente aparezca, mas sus lecturas.
ESPERA_DEL_PEDIDO = 75
ESPERA_DE_LA_COMPROBACION = 30

#: El tope de pedidos por contrato. El mismo que acepta la ruta del motor.
PEDIDOS_POR_CONTRATO = 20

#: Los resultados del motor. Se repiten aca porque son el contrato entre los
#: dos lados; uno que este lado no conoce cae en `fallida` con su codigo SOLO
#: si el motor dice que nunca llego a pedirlo -- si no, va a `por_revisar`.
CREADO = ("creado", "ya_estaba")
EN_CURSO = "en_curso"
NO_RECONOCIDO = "no_reconocido"
FALLO = "fallo"
IP_OCUPADA = "ip_ocupada"
#: Los que el motor devuelve ANTES de pedirle nada al proveedor (o cuando su
#: ejecutor se nego a salir): con estos, de esa pasada no salio nada.
SIN_EFECTO = frozenset({IP_OCUPADA, "ip_fuera_del_rango", "plan_desconocido",
                        "datos_invalidos", "sin_herramienta", "bloqueado",
                        "no_se_pudo_comprobar"})

#: Lo que este lado agrega.
SIN_RESPUESTA = "sin_respuesta"
SIN_EMPRESA = "sin_empresa"
SIN_ACTOR = "sin_actor"
SIN_CONFIRMAR = "sin_confirmar"
IP_TOMADA_TRAS_PEDIR = "ip_tomada_tras_pedir"
DEMASIADOS_PEDIDOS = "demasiados_pedidos"
RESUELTO_A_MANO = "resuelto_a_mano"
NO_QUEDO_CREADO = "no_quedo_creado"

_NO_ANULES = (" NO anules el contrato ni firmes otro: revisa primero en el "
              "sistema del proveedor si el cliente quedó creado.")

#: Lo que se le dice a una persona, por codigo. El motor manda su motivo, pero
#: en su idioma: esto es lo que lee quien esta en la oficina o en la calle.
EXPLICACION = {
    #  SOLO CUANDO NUNCA SE HABIA PEDIDO NADA: ahi si, la IP es de otro.
    IP_OCUPADA: "La dirección IP elegida ya la tiene otro cliente. Anula el "
                "contrato y firma otro con una IP distinta.",
    "ip_fuera_del_rango": "La IP elegida no es de los rangos cargados para ese "
                          "servidor, o ese servidor todavía no tiene rangos cargados.",
    "plan_desconocido": "El plan del contrato no está en el catálogo del proveedor.",
    "datos_invalidos": "Al contrato le falta un dato para crear al cliente.",
    "sin_herramienta": "La empresa todavía no tiene configurado cómo se crea un "
                       "cliente en su proveedor.",
    "bloqueado": "El sistema no escribió en el proveedor. No se creó nada.",
    "no_se_pudo_comprobar": "No se pudo consultar al proveedor para comprobar "
                            "antes de crear. No se creó nada.",
    FALLO: "El proveedor rechazó el pedido: el cliente no quedó creado.",
    SIN_RESPUESTA: "No se pudo poner el pedido en marcha. No se creó nada.",
    SIN_EMPRESA: "No se sabe de qué empresa es este contrato.",
    SIN_ACTOR: "No se pudo determinar quién pidió crear al cliente.",
    DEMASIADOS_PEDIDOS: "Este contrato ya se pidió demasiadas veces.",
    NO_QUEDO_CREADO: "Una persona revisó en el proveedor: el cliente no quedó creado.",
    #  LOS DE «NADIE SABE». Los tres dicen lo mismo al final, a proposito.
    SIN_CONFIRMAR: "Se pidió crear al cliente y no se pudo confirmar si quedó."
                   + _NO_ANULES,
    NO_RECONOCIDO: "Después de pedir, la IP quedó tomada por un cliente que no "
                   "se pudo reconocer como este. Casi seguro es él." + _NO_ANULES,
    IP_TOMADA_TRAS_PEDIR: "La IP está tomada y ya se había pedido crear a este "
                          "cliente antes: puede ser él." + _NO_ANULES,
}


def _motor():
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, cabeceras


def datos_del_alta(contrato) -> dict:
    """Lo que el motor necesita, sacado de los datos TAL COMO SE FIRMARON.

    No se vuelve a leer la solicitud ni la orden: el cliente acepto estos
    datos, y son los que se le crean.
    """
    d = contrato.datos or {}
    c = d.get("cliente") or {}
    gps = d.get("gps") or {}
    tiene_punto = gps.get("lat") not in (None, "") and gps.get("lng") not in (None, "")
    return {
        "zona": (d.get("servidor") or {}).get("id_zona"),
        "ip": d.get("ip_elegida") or "",
        "plan": d.get("plan") or "",
        "cliente": {
            "nombre": c.get("nombre", ""), "apellido": c.get("apellido", ""),
            "documento": c.get("numero_documento", ""),
            "correo": c.get("correo", ""), "telefono": c.get("telefono", ""),
            "direccion": c.get("direccion", ""), "barrio": c.get("barrio", ""),
        },
        "coordenadas": ({"lat": gps.get("lat"), "lng": gps.get("lng")}
                        if tiene_punto else None),
        #  26/11/2026: lo que cobro el tecnico y la ONU que instalo, cuando el
        #  alta es una INSTALACION (se pide al finalizar, ya con esos datos).
        **(_de_la_orden(contrato) if contrato.alta_como_instalacion else {}),
        #  Para que quien abra la ficha en el proveedor sepa de donde salio.
        "nota": f"Contrato {contrato.numero} · OT-{d.get('orden_numero')}",
    }


def _de_la_orden(contrato) -> dict:
    from campo.instalacion import costo_y_serial

    try:
        return costo_y_serial(contrato.orden)
    except Exception:                                            # noqa: BLE001
        return {}


def datos_para_reconocer(contrato) -> dict:
    """Lo MINIMO para volver a mirar un alta: donde buscar y como reconocerlo.

    Revision de PII, 25/11/2026: para comprobar viajaba la ficha entera
    --correo, telefono, domicilio, coordenadas-- hasta doce veces por
    contrato, y el motor solo usa la IP, el nombre y el documento.
    """
    d = datos_del_alta(contrato)
    return {"zona": d["zona"], "ip": d["ip"], "plan": d["plan"],
            "cliente": {c: d["cliente"][c] for c in ("nombre", "apellido", "documento")}}


def _anotar(contrato, **campos) -> None:
    """Deja escrito como va el alta. Solo sobre un contrato `firmado`: uno que
    ya esta en el ISP o que se anulo no se toca."""
    from campo.contrato import ContratoDeServicio

    ahora = timezone.now()
    campos.setdefault("alta_actualizada_en", ahora)
    if "alta_detalle" in campos:
        campos["alta_detalle"] = str(campos["alta_detalle"] or "")[:300]
    (ContratoDeServicio.objects
     .filter(pk=contrato.pk, estado=ContratoDeServicio.FIRMADO)
     .update(updated_at=ahora, **campos))
    contrato.refresh_from_db()


def _detalle(codigo: str, motivo: str = "") -> str:
    explicacion = EXPLICACION.get(codigo, "No se pudo crear al cliente en el proveedor.")
    #  EL MOTIVO DEL MOTOR VA DESPUES, entre parentesis: es el dato para quien
    #  tenga que arreglarlo. Es texto fijo del motor, sin datos del cliente.
    return explicacion + (f" ({motivo})" if motivo and motivo not in explicacion else "")


def _fallida(contrato, codigo: str, motivo: str = "", avisos=None, **mas) -> None:
    """NO HAY CLIENTE: el proveedor dijo que no, o nunca se le pidio."""
    from campo.contrato import ContratoDeServicio

    _anotar(contrato, alta_estado=ContratoDeServicio.ALTA_FALLIDA,
            alta_codigo=codigo[:40], alta_detalle=_detalle(codigo, motivo),
            alta_avisos=list(avisos or []), **mas)


def _por_revisar(contrato, codigo: str, motivo: str = "", avisos=None, **mas) -> None:
    """NADIE SABE si el cliente quedo creado. Lo resuelve una persona."""
    from campo.contrato import ContratoDeServicio

    _anotar(contrato, alta_estado=ContratoDeServicio.ALTA_POR_REVISAR,
            alta_codigo=codigo[:40], alta_detalle=_detalle(codigo, motivo),
            alta_avisos=list(avisos or []), **mas)


def _creado(contrato, id_cliente: str, codigo: str, avisos=None, **mas) -> None:
    """El cliente existe en el proveedor: el contrato pasa a `en_el_isp`. Si
    se pidio como INSTALACION (26/11/2026), a `instalacion`: falta que una
    persona la valide y la active."""
    from campo.contrato import ContratoDeServicio

    ahora = timezone.now()
    (ContratoDeServicio.objects
     .filter(pk=contrato.pk, estado=ContratoDeServicio.FIRMADO)
     .update(estado=(ContratoDeServicio.INSTALACION if contrato.alta_como_instalacion
                     else ContratoDeServicio.EN_EL_ISP),
             servicio_isp=str(id_cliente or "")[:64],
             alta_estado="", alta_codigo=codigo[:40], alta_detalle="",
             alta_avisos=list(avisos or []), alta_actualizada_en=ahora,
             updated_at=ahora, **mas))
    contrato.refresh_from_db()


def _aplicar(contrato, estado: str, cuerpo: dict) -> None:
    """Lo que contesto el motor, vuelto estado del contrato."""
    from campo.contrato import ContratoDeServicio

    motivo = str(cuerpo.get("motivo") or "")
    avisos = [str(a)[:200] for a in (cuerpo.get("avisos") or [])][:5]
    #  SI EL PEDIDO LLEGO AL REGISTRO DEL MOTOR, queda dicho para siempre: a
    #  partir de ahi una IP tomada puede ser la del propio cliente.
    emitida = bool(contrato.alta_emitida) or cuerpo.get("emitido") is True
    mas = {"alta_emitida": emitida}

    if estado in CREADO:
        _creado(contrato, cuerpo.get("id_cliente") or "", estado, avisos, **mas)
    elif estado in (EN_CURSO, NO_RECONOCIDO):
        #  LOS DOS SON «TODAVIA NO SE SABE», y se sigue mirando. Una ficha sin
        #  reconocer puede ser la nuestra a medio armar. Si al final de las
        #  vueltas sigue asi, `rendirse` la manda a revision con este codigo.
        _anotar(contrato, alta_estado=ContratoDeServicio.ALTA_EN_CURSO,
                alta_codigo=estado, alta_detalle="",
                alta_tarea=str(cuerpo.get("tarea") or contrato.alta_tarea or "")[:80],
                alta_avisos=avisos, alta_emitida=True)
    elif estado == FALLO:
        _fallida(contrato, FALLO, motivo, avisos, **mas)
    elif estado == IP_OCUPADA and emitida:
        #  LA IP ESTA TOMADA Y YA HABIAMOS PEDIDO: puede ser el nuestro.
        _por_revisar(contrato, IP_TOMADA_TRAS_PEDIR, "", avisos, **mas)
    elif estado in SIN_EFECTO:
        _fallida(contrato, estado, motivo, avisos, **mas)
    elif cuerpo.get("emitido") is True:
        #  UN RESULTADO QUE ESTE LADO NO CONOCE, de un pedido que pudo haber
        #  salido: no se adivina que significa. Lo mira una persona.
        _por_revisar(contrato, SIN_CONFIRMAR, "", avisos, **mas)
    else:
        _fallida(contrato, estado or "sin_estado", motivo, avisos, **mas)


def _llamar(contrato, ruta: str, cuerpo: dict, espera: int):
    """`(estado, cuerpo)` de lo que contesto el motor, o `(None, {})` si no
    contesto algo que se pueda leer."""
    from operaciones import areas_del_tenant

    tenant = areas_del_tenant.tenant_de(contrato.org_id)
    if not tenant:
        return SIN_EMPRESA, {}
    base, cabeceras = _motor()
    try:
        r = requests.post(f"{base}/interno/contrato/{contrato.id}/{ruta}",
                          params={"tenant": tenant}, json=cuerpo,
                          headers=cabeceras, timeout=espera)
        datos = r.json() if r.content else {}
    except Exception as e:                                       # noqa: BLE001
        #  POR TIPO Y SIN `str(e)`: el mensaje de un cliente HTTP trae la URL.
        logger.warning("alta_en_el_isp: el motor no contesto (%s)", type(e).__name__)
        return None, {}
    if not isinstance(datos, dict) or not datos.get("estado"):
        logger.warning("alta_en_el_isp: el motor respondio %s sin estado", r.status_code)
        return None, {}
    return str(datos["estado"]), datos


def pedir(contrato):
    """Le pide al motor que cree al cliente, y deja escrito como termino.

    Solo actua sobre un contrato `firmado` con el alta `pedida`: es lo que la
    tarea encuentra cuando alguien la encolo. Cualquier otra cosa se deja como
    esta.
    """
    from campo.contrato import ContratoDeServicio
    from campo.services.ubicacion_al_isp import _nombre_de

    if (contrato.estado != ContratoDeServicio.FIRMADO
            or contrato.alta_estado != ContratoDeServicio.ALTA_PEDIDA):
        return contrato
    try:
        #  QUIEN LO PIDIO: la persona que toco «volver a intentar», o quien
        #  firmo si el pedido salio de la firma. Es el actor de la puerta
        #  humana: la evidencia de que detras hay una persona.
        actor = _nombre_de(contrato.alta_pedida_por or contrato.firmado_por)
        datos = datos_del_alta(contrato)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("alta_en_el_isp: no se pudo leer el contrato (%s)", type(e).__name__)
        _fallida(contrato, "datos_invalidos")
        return contrato
    if not actor:
        _fallida(contrato, SIN_ACTOR)
        return contrato

    estado, cuerpo = _llamar(contrato, "crear-cliente", {
        "actor": actor, "datos": datos,
        "intento": int(contrato.alta_intento or 1)}, ESPERA_DEL_PEDIDO)
    if estado is None:
        #  NO SE SABE SI SALIO. Sigue `pedida`: la tarea lo vuelve a pedir con
        #  el MISMO numero, y el motor no lo saca dos veces. Y desde ahora se
        #  cuenta como que pudo haber salido.
        _anotar(contrato, alta_codigo=SIN_RESPUESTA, alta_emitida=True)
        return contrato
    if estado == SIN_EMPRESA:
        _fallida(contrato, SIN_EMPRESA)
        return contrato
    _aplicar(contrato, estado, cuerpo)
    return contrato


def comprobar(contrato):
    """Vuelve a mirar un alta que quedo `en_curso`. Solo lee: no crea nada."""
    from campo.contrato import ContratoDeServicio

    if (contrato.estado != ContratoDeServicio.FIRMADO
            or contrato.alta_estado != ContratoDeServicio.ALTA_EN_CURSO):
        return contrato
    try:
        datos = datos_para_reconocer(contrato)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("alta_en_el_isp: no se pudo leer el contrato (%s)", type(e).__name__)
        return contrato
    estado, cuerpo = _llamar(contrato, "comprobar-cliente",
                             {"datos": datos, "tarea": contrato.alta_tarea or ""},
                             ESPERA_DE_LA_COMPROBACION)
    if estado in (None, SIN_EMPRESA):
        return contrato                 # no saber no cambia nada: sigue en curso
    _aplicar(contrato, estado, cuerpo)
    return contrato


def rendirse(contrato) -> None:
    """Se espero lo que se podia esperar y sigue sin saberse.

    NO QUEDA `fallida`: fallida es «no hay cliente», y aca nadie lo sabe. Va a
    `por_revisar`, que no se puede anular ni reintentar hasta que una persona
    de gestion mire en el proveedor.
    """
    from campo.contrato import ContratoDeServicio

    if contrato.alta_estado not in ContratoDeServicio.ALTA_EN_VUELO:
        return
    if not contrato.alta_emitida and contrato.alta_estado == ContratoDeServicio.ALTA_PEDIDA:
        #  NUNCA LLEGO A PEDIRSE (ni siquiera se alcanzo al motor): ahi si se
        #  sabe que no hay cliente.
        _fallida(contrato, SIN_RESPUESTA)
        return
    codigo = NO_RECONOCIDO if contrato.alta_codigo == NO_RECONOCIDO else SIN_CONFIRMAR
    _por_revisar(contrato, codigo)


def pedir_alta(contrato, *, por=None, como_instalacion: bool = False) -> bool:
    """Marca el alta como pedida y encola la tarea, DESPUES del commit.

    `por` es la persona que lo pide (None cuando sale de la firma: ahi es
    quien firmo). True si se encolo. False si no correspondia: el contrato no
    esta `firmado`, hay un pedido en vuelo, o esta por revisar.

    EL CAMBIO LLEVA SU CONDICION EN LA MISMA SENTENCIA: dos toques seguidos, o
    un reintento de red, tocan la fila una sola vez y encolan una sola tarea.

    CADA PEDIDO LLEVA UN NUMERO NUEVO. Solo se llega aca desde «nunca pedido»
    o `fallida` --que es «no hay cliente»--, asi que un numero nuevo nunca
    convive con un pedido anterior sin resolver.
    """
    from campo.contrato import ContratoDeServicio

    intento = int(contrato.alta_intento or 0) + 1
    ahora = timezone.now()
    if intento > PEDIDOS_POR_CONTRATO:
        _fallida(contrato, DEMASIADOS_PEDIDOS)
        return False
    tocadas = (ContratoDeServicio.objects
               .filter(pk=contrato.pk, estado=ContratoDeServicio.FIRMADO,
                       alta_intento=int(contrato.alta_intento or 0))
               .exclude(alta_estado__in=ContratoDeServicio.ALTA_SIN_RESOLVER)
               .update(alta_estado=ContratoDeServicio.ALTA_PEDIDA, alta_codigo="",
                       alta_detalle="", alta_tarea="", alta_avisos=[],
                       alta_intento=intento, alta_pedida_por=por,
                       alta_como_instalacion=bool(como_instalacion),
                       alta_actualizada_en=ahora, updated_at=ahora))
    contrato.refresh_from_db()
    if not tocadas:
        return False

    org_id, contrato_id = str(contrato.org_id), str(contrato.id)

    def _encolar():
        from campo.tasks import crear_cliente_en_el_isp

        try:
            crear_cliente_en_el_isp.delay(org_id, contrato_id)
        except Exception as e:                                   # noqa: BLE001
            #  SIN COLA NO HAY ALTA, Y SE DICE: si esto quedara `pedida` para
            #  siempre, el contrato no se podria anular ni reintentar. Nada
            #  salio: ni siquiera se alcanzo al motor.
            logger.warning("alta_en_el_isp: no se pudo encolar (%s)", type(e).__name__)
            try:
                _fallida(ContratoDeServicio.objects.get(pk=contrato_id), SIN_RESPUESTA)
            except Exception:                                    # noqa: BLE001
                pass

    transaction.on_commit(_encolar)
    return True


class ResolucionInvalida(ValueError):
    """Lo que la persona mando no alcanza para resolver. El texto se muestra."""


def resolver(contrato, profile, *, quedo_creado: bool, id_cliente: str = ""):
    """Una persona de gestion dice, despues de mirar en el proveedor, si el
    cliente quedo creado.

    Es la UNICA salida de `por_revisar`, y es de una persona a proposito: el
    sistema ya dijo que no sabe, y adivinar aca es o un cliente duplicado o
    el numero de otra persona escrito en un contrato.

    * `quedo_creado=True` exige el numero del cliente en el proveedor: el
      contrato pasa a `en_el_isp` con ese numero.
    * `quedo_creado=False`: el alta queda `fallida` --ahora si se sabe que no
      hay cliente--, y se puede reintentar o anular.

    Queda escrito quien lo resolvio y cuando.
    """
    from campo.contrato import ContratoDeServicio

    if (contrato.estado != ContratoDeServicio.FIRMADO
            or contrato.alta_estado != ContratoDeServicio.ALTA_POR_REVISAR):
        raise ResolucionInvalida("Este contrato no está esperando una revisión.")
    ahora = timezone.now()
    quien = {"alta_resuelta_por": profile, "alta_resuelta_en": ahora}
    if quedo_creado:
        numero = str(id_cliente or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", numero):
            raise ResolucionInvalida(
                "Escribe el número del cliente tal como aparece en el proveedor.")
        _creado(contrato, numero, RESUELTO_A_MANO, contrato.alta_avisos, **quien)
    else:
        _fallida(contrato, NO_QUEDO_CREADO, "", contrato.alta_avisos, **quien)
    return contrato
