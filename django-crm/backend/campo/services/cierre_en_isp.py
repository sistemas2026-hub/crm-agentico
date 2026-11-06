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


def _material_consumido(orden) -> list[str]:
    """Las lineas de «MATERIAL Y CANTIDAD», como las escribe el tecnico hoy.

    FORMATO DE ELLOS, NO UNO NUEVO (06/11/2026). El usuario mostro como queda
    hoy un ticket de WispHub escrito a mano: el nombre del material en una
    linea y la cantidad en la siguiente. Quien lo lee ya sabe leer eso; un
    formato distinto obliga a aprender otro.

    Nunca levanta: un reporte sin la seccion de material es menos util que uno
    con ella, pero perder el reporte entero porque el inventario no contesto
    seria peor.
    """
    try:
        from campo.services.materiales_de_orden import materiales_de_orden

        consumido = (materiales_de_orden(orden) or {}).get("consumido") or []
    except Exception:                                            # noqa: BLE001
        logger.warning("cierre en el ISP: no se pudo leer el material")
        return []

    lineas: list[str] = []
    for linea in consumido:
        if not isinstance(linea, dict):
            continue
        material = linea.get("material") or {}
        nombre = str(material.get("nombre") or material.get("codigo") or "").strip()
        if not nombre:
            continue
        cantidad = str(linea.get("cantidad") or "").strip() or "0"
        #  La cantidad sin decimales cuando es entera: «1», no «1.000».
        if cantidad.replace(".", "", 1).isdigit() and "." in cantidad:
            try:
                n = float(cantidad)
                cantidad = str(int(n)) if n == int(n) else cantidad
            except ValueError:
                pass
        lineas.append(_tapar(nombre))
        lineas.append(cantidad)
        serie = str(linea.get("serie") or "").strip()
        if serie:
            lineas.append(f"Serie: {_tapar(serie)}")
    return lineas


def resumen_de(orden, nombre_de_quien_valida: str,
               encabezado: str = "") -> str:
    """Lo que queda escrito en el ticket del ISP: que se hizo, sin datos
    personales.

    CON LA FORMA QUE ELLOS YA USAN  --  06/11/2026
    ----------------------------------------------
    El usuario mostro un ticket real escrito a mano por un tecnico:

        Observaciones: se realiza instalacion, ya tenia fibra...
        VALOR CANCELADO POR EL USUARIO=
        Verificacion OZMAP: si
        Niveles de potencia: -21-26 dbm
        MATERIAL Y CANTIDAD
        ONU CATV
        1

    Antes esto escribia «- Titulo: valor» con guiones y sin material. Se
    parecia, pero no era lo mismo, y lo lee gente que ya tiene el ojo hecho al
    formato de arriba.

    LOS ROTULOS SALEN DE LA PLANTILLA, NO DEL CODIGO (decision del usuario,
    06/11/2026). «VALOR CANCELADO POR EL USUARIO» o «Verificacion OZMAP» son
    campos que la empresa define en /supervisor-noc/plantillas; si manana
    agrega uno o le cambia el nombre, el ticket lo refleja sin tocar nada. La
    alternativa --fijarlos aca-- habria salido identica hoy y habria dejado el
    formato de UNA empresa escrito en el codigo de todas.

    Solo lo que el tecnico respondio a una pregunta declarada, con el titulo
    de esa pregunta. Cada valor pasa por `tapar`: un «llamar al 300...»
    escrito en un texto libre no tiene por que terminar en el ticket.
    """
    version = orden.tipo_trabajo_version
    esquema = (version.esquema or {}) if version else {}
    tipo = version.work_type.nombre if version else "trabajo de campo"
    datos = orden.datos or {}

    #  Quien valido NO va aca: el motor antepone su nombre al texto
    #  (`operativo._firmado`), y ponerlo dos veces solo lo repite.
    lineas = [encabezado.strip() or
              f"Trabajo de campo OT #{orden.numero} ({tipo}) validado en Dexter."]
    for campo in esquema.get("campos") or []:
        if not isinstance(campo, dict):
            continue
        valor = datos.get(campo.get("id"))
        if valor in (None, ""):
            continue
        titulo = campo.get("titulo") or campo.get("id")
        unidad = f" {campo['unidad']}" if campo.get("unidad") else ""
        #  SIN el guion de antes: «Titulo: valor», como en el ticket escrito a
        #  mano. El guion hacia que se leyera como una lista de sistema.
        lineas.append(f"{titulo}: {_tapar(valor)}{unidad}")
        if len(lineas) > MAX_LINEAS:
            lineas.append("(sigue en Dexter)")
            break

    material = _material_consumido(orden)
    if material:
        lineas.append("")
        lineas.append("MATERIAL Y CANTIDAD")
        lineas.extend(material)

    fotos = orden.evidencias.count() if hasattr(orden, "evidencias") else 0
    if fotos:
        lineas.append("")
        lineas.append(f"Evidencias en Dexter: {fotos}.")
    return "\n".join(lineas)

def numero_de_ticket(contexto) -> str:
    """El numero del ticket del ISP que guarda la ficha de la orden, o "".

    POR QUE ESTA FUNCION EXISTE  --  05/11/2026
    -------------------------------------------
    `contexto["ticket"]` NO es un numero: es el dict que arma
    `campo/services/despacho.py::_ticket_del_proveedor`, con `numero`,
    `proveedor`, `estado` y `abierto_por`. Hasta hoy se leia con `str(...)`,
    asi que lo que viajaba al motor era el `repr` del diccionario:

        "{'numero': '94721', 'proveedor': 'wisphub', 'estado': 'Nuevo'}"

    Ese texto trae llaves, asi que el ejecutor HTTP sustituia `{id_ticket}` y
    despues veia que el endpoint SEGUIA con llaves sin resolver, y levantaba
    `ErrorHerramientaHttp` ANTES de llamar a WispHub. Resultado medido en
    produccion: `FALLO_AL_CERRAR`, ningun ticket cerrado del otro lado, y
    --en el camino del Supervisor-- la orden sin cerrarse tampoco, porque un
    fallo del ISP corta antes de `cerrar_orden`.

    POR QUE NINGUNA PRUEBA LO VIO: las dos suites del cierre construyen la
    orden con `contexto={"ticket": "94721"}`, un string. Nunca con la forma
    que el productor de verdad escribe. Era deriva entre quien guarda el dato
    y quien lo lee, y ninguna prueba cruzaba los dos.

    ACEPTA LAS DOS FORMAS a proposito: hay ordenes ya guardadas con el dict y
    puede haber alguna vieja con un string suelto. Rechazar una de las dos
    dejaria ordenes sin poder cerrarse por como quedo escrito su contexto.
    """
    valor = (contexto or {}).get("ticket")
    if isinstance(valor, dict):
        valor = valor.get("numero")
    return str(valor or "").strip()


def _ya_cerrado(orden) -> bool:
    from campo.models import EventoTrabajo

    return EventoTrabajo.objects.filter(orden=orden, tipo=EVENTO_CERRADO).exists()


def _anotar(orden, profile, tipo, datos):
    from campo.models import EventoTrabajo

    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                 profile=profile, datos=datos)


def cerrar_ticket_al_validar(orden, profile, extra: str = "") -> dict:
    """Cierra en el ISP el ticket de una orden recien validada. NUNCA lanza.

    Devuelve `{"estado": ..., "detalle": ...}` para que la respuesta de la
    validacion pueda decir que paso con el ticket. Todo va envuelto: la orden
    ya esta validada, y un fallo al anotar en la bitacora no puede convertir
    esa validacion en un 500 (auditoria de frontera, 13/10/2026).
    """
    try:
        return _cerrar(orden, profile, extra=extra)
    except Exception as e:  # noqa: BLE001
        logger.warning("cierre en el ISP: fallo inesperado (%s)", type(e).__name__)
        return {"estado": "no_cerrado", "detalle": type(e).__name__}


def cerrar_ticket_por_el_supervisor(orden, revision=None,
                                   extra: str = "") -> dict:
    """El Supervisor cierra el ticket SOLO (30/10/2026,
    `campo/cierre_por_el_supervisor.py`). Por la ruta AUTONOMA del motor, que
    consulta el interruptor, el techo, Autonomia 2 con B-7 y la autorizacion de
    la herramienta. NUNCA lanza. Mismo contrato que `cerrar_ticket_al_validar`.

    `revision` es la que autoriza el cierre. Viaja al motor porque alla no se
    puede recalcular, y sin ella la ruta ahora RECHAZA (auditoria de frontera,
    31/10/2026, H1): la bitacora de ejecucion autonoma tiene que poder decir
    que revision autorizo cada cierre.
    """
    try:
        return _cerrar(orden, None, ruta="cerrar-ticket-supervisor",
                       revision=_referencia_de(orden, revision), extra=extra)
    except Exception as e:  # noqa: BLE001
        logger.warning("cierre del Supervisor: fallo inesperado (%s)", type(e).__name__)
        return {"estado": "no_cerrado", "detalle": type(e).__name__}


def _referencia_de(orden, revision) -> str:
    """Como se nombra la revision en la auditoria: orden, vuelta y veredicto.

    Nada del cliente ni texto libre: esto queda escrito en la bitacora del
    motor, que no lleva datos de persona (CLAUDE.md §5).
    """
    veredicto = (revision or {}).get("veredicto") or "sin_veredicto"
    return f"orden:{orden.id}|vuelta:{orden.vuelta}|{veredicto}"


def _cerrar(orden, profile, ruta: str = "cerrar-ticket", revision: str = "",
            extra: str = "") -> dict:
    if not _habilitado():
        return {"estado": "apagado", "detalle": f"{BANDERA}=0"}
    ticket = numero_de_ticket(orden.contexto)
    if not ticket:
        #  Una orden sin ticket del ISP (manual, o de un caso nacido en el chat)
        #  no tiene nada que cerrar alla. No es un fallo, y no se anota.
        return {"estado": "sin_ticket", "detalle": "la orden no tiene ticket del ISP"}
    if _ya_cerrado(orden):
        return {"estado": "ya_cerrado", "detalle": f"ticket {ticket}"}

    #  LA RUTA HUMANA EXIGE UNA PERSONA (auditoria de frontera, 30/10/2026,
    #  H2). Sin perfil no se inventa un «Oficina de operaciones»: el Supervisor
    #  tiene su ruta, la autonoma.
    if ruta == "cerrar-ticket" and profile is None:
        return {"estado": "no_cerrado",
                "detalle": "sin una persona que valide no se pide por la ruta humana"}

    from operaciones import areas_del_tenant

    #  La empresa de la ORDEN, no la de una variable del servidor (31/10/2026).
    tenant = areas_del_tenant.tenant_de(orden.org_id)
    if not tenant:
        return {"estado": "no_cerrado",
                "detalle": f"{areas_del_tenant.SIN_EMPRESA}: sin saber de que "
                           "empresa es la orden no se le escribe al ISP"}

    import requests

    #  El NOMBRE, nunca el email: `nombre_de` cae al correo cuando no hay
    #  nombre, y ese correo terminaria escrito en el ticket del cliente.
    user = getattr(profile, "user", None)
    quien = (getattr(user, "name", "") or "").strip() or "Oficina de operaciones"
    #  La ruta del Supervisor no acepta `actor`: quien cierra no lo elige el CRM.
    #  EL CIERRE YA NO REPITE EL REPORTE  --  06/11/2026, decision del usuario
    #
    #  Antes escribia `resumen_de` entero porque era la UNICA escritura que
    #  llegaba al ticket. Desde que el tecnico manda su reporte al completar
    #  (`nota_al_isp.anotar_reporte_del_tecnico`), repetirlo en el cierre
    #  duplica en el ticket lo que ya esta tres respuestas mas arriba.
    #
    #  Asi que cuando quien llama trae su propio texto --«SE VALIDA TICKET» mas
    #  que se reviso, que es lo que una persona escribe hoy a mano-- ese es el
    #  texto. Sin el, el de siempre: una instalacion vieja que se cierre por un
    #  camino que no calcula revision sigue dejando el reporte completo, que es
    #  mejor que no dejar nada.
    texto_del_ticket = extra.strip() if (extra or "").strip() else resumen_de(orden, quien)
    cuerpo_pedido = {"ticket": ticket, "texto": texto_del_ticket}
    if ruta == "cerrar-ticket":
        cuerpo_pedido["actor"] = quien
    else:
        #  La ruta del Supervisor la exige: ver `_referencia_de` y H1.
        cuerpo_pedido["revision"] = revision
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.post(
            f"{base}/interno/orden/{orden.id}/{ruta}",
            params={"tenant": tenant},
            json=cuerpo_pedido,
            headers=cabeceras, timeout=45)
        cuerpo = r.json() if r.content else {}
        if not isinstance(cuerpo, dict):
            cuerpo = {}
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
    #  El motivo (que compuerta lo freno) viaja: «B7_REQUERIDO: ...» le dice a
    #  la oficina que falta, «NO_AUTORIZADA» solo no.
    detalle = f"{codigo}: {cuerpo['motivo']}" if cuerpo.get("motivo") else codigo
    return {"estado": "no_cerrado", "detalle": detalle[:300]}
