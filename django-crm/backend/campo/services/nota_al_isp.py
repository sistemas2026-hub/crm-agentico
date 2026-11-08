# -*- coding: utf-8 -*-
"""
================================================================================
 EL TICKET DEL ISP SE ENTERA CUANDO PASA, NO AL FINAL  --  06/11/2026
================================================================================
El usuario, describiendo como ya trabajan hoy a mano:

    "actualmente en wisphub el tecnico envia por wisphub el reporte por el
     ticket y le pide al encargado revisar y el deja escrito en el ticket la
     revision [...] el tecnico manda el reporte y el supervisor tambien deja
     su respuesta de lo validado y si pasa a cierro o devuelve al tecnico"

Hasta hoy el ticket del ISP no se enteraba de NADA hasta el cierre. Si el
Supervisor tardaba dos dias, quien miraba WispHub veia un ticket "Nuevo" con el
plazo vencido mientras el trabajo ya estaba hecho. `devolver_al_ticket.py`
arreglo eso el 02/11 del lado del CRM; esto lo extiende al proveedor.

TRES MOMENTOS, DOS PUERTAS
--------------------------
  1. el tecnico manda su reporte      -> nota, el ticket sigue abierto
  2. el Supervisor devuelve           -> nota, el ticket sigue abierto
  3. el Supervisor valida y cierra     -> ya existia (`cierre_en_isp`)

Los dos primeros van por `/interno/orden/<id>/anotar-en-el-ticket`, con la
exencion `nota_de_campo_en_el_ticket`. El tercero sigue por su propia puerta.

LO QUE NO HACE, A PROPOSITO
---------------------------
**No tumba nada si falla.** Igual que `devolver_al_ticket`: si esto no sale, la
orden sigue su curso y queda el motivo anotado. Un ticket sin actualizar es un
problema; una orden que no avanza porque el ISP tuvo un hipo es uno peor.

**No manda el estado del ticket.** Lo fija la herramienta del catalogo. La ruta
del motor rechaza el argumento, asi que esto no puede convertirse en un cierre.

**No arma texto libre del cliente.** Todo sale de la PLANTILLA de la orden y
pasa por `tapar` (`cierre_en_isp`), que es lo que saca un "llamar al 300..."
escrito en una observacion.

DEUDA CONOCIDA: la llamada al motor son ~20 lineas calcadas de
`cierre_en_isp._pedirle_al_motor`. No se unifico en este cambio para no tocar
el camino de cierre, que esta en produccion y se arreglo esta misma semana.
Unificar cuando haya una tercera.
================================================================================
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: Los momentos que el motor declara. Si no coinciden, la ruta contesta 400.
REPORTE_DEL_TECNICO = "reporte_del_tecnico"
DEVUELTA_AL_TECNICO = "devuelta_al_tecnico"
REVISION_SIN_CIERRE = "revision_sin_cierre"
EN_CAMINO = "en_camino"
EN_SITIO = "en_sitio"

#: Lo que se escribe en cada avance. En infinitivo no: el ticket cuenta lo que
#: paso, y "va en camino" se lee como lo que es.
TEXTO_DEL_AVANCE = {
    EN_CAMINO: "va en camino",
    EN_SITIO: "llego al sitio",
}

#  ---------------------------------------------------------------------------
#   EL INTERRUPTOR, Y POR QUE SON DOS  --  H6, auditoria de frontera 06/11/2026
#  ---------------------------------------------------------------------------
#  Esto nacio sin ninguna bandera, y el hallazgo fue concreto: una instancia
#  que hoy tiene las escrituras al ISP apagadas con
#  'CAMPO_CERRAR_TICKET_AL_VALIDAR=0' **empezaria a escribir notas igual** al
#  desplegar. Quien apago ese interruptor dijo "no le escribas al ISP"; no
#  dijo "no le cierres tickets pero mandale notas".
#
#  Por eso se respetan los dos:
#    · 'CAMPO_NOTA_AL_ISP'  -- el propio, para apagar SOLO las notas
#    · 'CAMPO_CERRAR_TICKET_AL_VALIDAR=0' -- si esta apagado explicitamente,
#      las notas tambien, porque es la señal que ya existia para "no escribir
#      alla" y hay operadores que la usaron.
#
#  Los dos encendidos por omision: §8 dice que si un proceso debe estar
#  corriendo es una decision de operacion, y la decision del usuario del
#  06/11/2026 fue que esto corra.
BANDERA = "CAMPO_NOTA_AL_ISP"
BANDERA_DEL_CIERRE = "CAMPO_CERRAR_TICKET_AL_VALIDAR"

#: Lo que queda en la bitacora de la orden. Sin esto, nadie en el CRM podia
#: contestar si el ISP recibio la nota: no habia fila, ni evento, ni pantalla.
EVENTO_ANOTADA = "nota_isp_anotada"
EVENTO_NO_ANOTADA = "nota_isp_no_anotada"


def _apagado() -> str:
    """Que bandera lo apaga, o `""` si esta habilitado.

    Devuelve el NOMBRE y no un bool para que el motivo quede escrito en la
    bitacora: "no se anoto" sin decir por que manda a buscar un fallo que no
    existe.
    """
    if (os.environ.get(BANDERA, "1") or "1").strip() in ("0", "false", "no"):
        return BANDERA
    #  Solo si esta puesta EXPLICITAMENTE en 0: no estar es lo normal.
    if (os.environ.get(BANDERA_DEL_CIERRE, "") or "").strip() in ("0", "false",
                                                                  "no"):
        return BANDERA_DEL_CIERRE
    return ""


def _json_seguro(valor):
    """Un valor que `JSONField` pueda guardar, o su `repr` acortado.

    POR QUE  --  06/11/2026, lo encontro `test_b_devolver_para_corregir`
    -------------------------------------------------------------------
    `EventoTrabajo.datos` es un JSONField. Cualquier cosa que no sea JSON ahi
    adentro revienta EL INSERT, y un INSERT que falla deja la transaccion de
    quien llamo en estado roto: a partir de ahi toda consulta posterior falla
    con `TransactionManagementError`, aunque esta funcion se trague la
    excepcion. Atrapar no es aislar.

    Paso en la prueba con `mock.patch("requests.post")`: `r.status_code` era
    un `MagicMock` y entraba al rastro. En produccion es un int, asi que no se
    habria visto -- hasta el dia que algo devuelva otra cosa.
    """
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return repr(valor)[:200]


def _anotar_evento(orden, profile, tipo: str, datos: dict) -> None:
    """Deja el rastro en la orden. Nunca levanta Y NO ENSUCIA LA TRANSACCION.

    El `atomic` propio no es decoracion: es un savepoint. Sin el, un INSERT
    que falla rompe la transaccion de quien llamo --`ValidarTrabajoView`,
    `CompletarTrabajoView`-- y la vista entera revienta DESPUES, por una
    bitacora. El efecto ya ocurrio y la orden ya avanzo; perder el rastro es
    aceptable, perder la respuesta de la vista no.
    """
    from django.db import transaction

    limpios = {k: _json_seguro(v) for k, v in (datos or {}).items()}
    try:
        from campo.models import EventoTrabajo

        with transaction.atomic():
            EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                         profile=profile, datos=limpios)
    except Exception:                                           # noqa: BLE001
        logger.warning("nota_al_isp: no se pudo anotar el evento %s", tipo)

#: Cuantos requisitos se nombran en la nota de devolucion.
MAX_REQUISITOS = 12


def _tenant_de(orden):
    from operaciones import areas_del_tenant

    return areas_del_tenant.tenant_de(orden.org_id)


def _nombre_de(profile) -> str:
    """El NOMBRE, nunca el email.

    `user.name` cae a vacio cuando no hay nombre, y si cayera al correo ese
    correo terminaria escrito en el ticket del cliente. Misma regla que
    `cierre_en_isp`.
    """
    user = getattr(profile, "user", None)
    return (getattr(user, "name", "") or "").strip()


def _pedir(orden, cuerpo: dict, profile=None) -> dict:
    """Le pide al motor que anote. Devuelve `{"anotada": bool, "codigo": str}`.

    Nunca levanta: quien llama sigue su curso igual (ver la cabecera).
    """
    import requests

    apagada = _apagado()
    if apagada:
        return {"anotada": False, "codigo": "apagado",
                "detalle": f"{apagada}=0"}

    tenant = _tenant_de(orden)
    if not tenant:
        return {"anotada": False, "codigo": "sin_empresa",
                "detalle": "sin saber de que empresa es la orden no se le "
                           "escribe al ISP"}

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.post(
            f"{base}/interno/orden/{orden.id}/anotar-en-el-ticket",
            params={"tenant": tenant}, json=cuerpo,
            headers=cabeceras, timeout=45)
        datos = r.json() if r.content else {}
        if not isinstance(datos, dict):
            datos = {}
    except Exception as e:                                      # noqa: BLE001
        #  Por tipo, sin `str(e)`: el mensaje de un cliente HTTP puede traer la
        #  URL con la clave.
        logger.warning("nota_al_isp: no se pudo anotar (%s)", type(e).__name__)
        return {"anotada": False, "codigo": "sin_respuesta",
                "detalle": type(e).__name__}
    #  EL RASTRO EN LA ORDEN (H6). Un `logger.info` lo ve quien mira los
    #  logs del contenedor; el evento lo ve quien mira la orden, que es quien
    #  pregunta si el ISP se entero.
    #  `_json_seguro` se aplica igual en `_anotar_evento`; esto es que el
    #  valor nazca legible y no como el `repr` de un objeto.
    codigo = datos.get("codigo")
    if not codigo:
        codigo = getattr(r, "status_code", None)
    rastro = {"momento": cuerpo.get("momento"), "vuelta": cuerpo.get("vuelta"),
              "ticket": cuerpo.get("ticket"), "codigo": codigo,
              #  EL MOTIVO, NO SOLO EL CODIGO  --  06/11/2026
              #
              #  Sin esto el evento decia 'no_autorizada' y nada mas, y hubo
              #  que salir a adivinar CUAL de las cuatro compuertas la freno.
              #  Un rastro que dice que algo fallo pero no por que obliga a
              #  reproducir el fallo para diagnosticarlo, que es justo lo que
              #  el rastro existe para evitar.
              "detalle": str(datos.get("detalle") or "")[:300]}
    if datos.get("anotada"):
        _anotar_evento(orden, profile, EVENTO_ANOTADA, rastro)
    else:
        logger.info("nota_al_isp: el motor no anoto (%s)", rastro["codigo"])
        _anotar_evento(orden, profile, EVENTO_NO_ANOTADA, rastro)
    return datos


def _vuelta_de(orden) -> int:
    """La vuelta de la orden, que entra en la clave idempotente.

    Cae a 1 y no a 0: una orden que nunca se devolvio esta en su primera
    vuelta, y `vuelta=0` haria que la nota de la primera y la de la segunda
    compartieran clave si el campo llegara nulo.
    """
    try:
        return int(getattr(orden, "vuelta", None) or 1)
    except (TypeError, ValueError):
        return 1


# ---------------------------------------------------------------------------
#  1) EL REPORTE DEL TECNICO
# ---------------------------------------------------------------------------

def fotos_de_la_vuelta(orden) -> list[dict]:
    """Las evidencias de ESTA vuelta, listas para viajar al ticket del ISP.

    `[{"nombre", "tipo", "base64"}]`. Nunca levanta: si no se puede leer una
    foto, el reporte se escribe igual sin ella. Lo que el ticket no tenia es
    el reporte.

    EL MISMO NOMBRE QUE EN DEXTER. Se reusa `fotos_al_ticket._nombre`, que
    pone el requisito adelante («dano_encontrado-2.jpg») en vez del nombre
    que trajo el telefono. Si cada lado nombrara distinto, cruzar los dos
    tickets --que es lo que el equipo hace-- seria adivinar.

    SOLO LA VUELTA QUE CORRE, y por el mismo motivo que en todos lados: una
    orden devuelta y rehecha trae fotos NUEVAS, y las viejas ya se mandaron
    en su momento.

    EL TOPE DE ACA ES PARA NO LEER DE MAS del disco; el que decide que viaja
    de verdad vive en el motor (`nota_en_el_ticket`), que es quien le habla
    al proveedor. Dos topes del mismo numero a proposito: si alguien sube
    uno sin el otro, el de abajo sigue acotando.
    """
    import base64
    import os

    try:
        from campo.fotos_al_ticket import MAX_POR_VUELTA, _nombre
        from campo.services.storage import CampoStorage
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota_al_isp: no se pudieron preparar las fotos (%s)",
                       type(e).__name__)
        return []

    salida = []
    try:
        evidencias = list(orden.evidencias
                          .filter(vuelta=orden.vuelta, evento__isnull=True)
                          .order_by("recibida_en_servidor")[:MAX_POR_VUELTA])
    except Exception as e:                                       # noqa: BLE001
        logger.warning("nota_al_isp: no se pudieron listar las fotos (%s)",
                       type(e).__name__)
        return []

    for i, ev in enumerate(evidencias, start=1):
        try:
            ruta = CampoStorage.ruta_absoluta(ev.storage_key)
            #  DEFENSA REDUNDANTE, Y SE DEJA A SABIENDAS. Quitar este `if`
            #  NO cambia la conducta: `open("")` levanta y el `except` de
            #  abajo lo convierte en el mismo "esta no, las otras si".
            #  Medido el 07/11/2026: la mutacion que lo borra sobrevive a las
            #  siete guardas, y es correcto que sobreviva -- no hay efecto
            #  que afirmar. Mismo caso, y misma decision, que en
            #  `fotos_al_ticket.adjuntar`.
            #
            #  Se conserva porque un archivo faltante es lo ESPERADO --un
            #  borrado manual, una subida a medias-- y pasar por una
            #  excepcion lo registraria como un fallo en el log, mezclado con
            #  los que si lo son.
            if not ruta or not os.path.exists(ruta):
                continue
            with open(ruta, "rb") as f:
                crudo = f.read()
            salida.append({
                "nombre": _nombre(ev, i),
                #  EL TIPO QUE LA EVIDENCIA DECLARA, en minusculas: el motor
                #  lo compara contra una lista blanca y 'IMAGE/JPEG' no es
                #  'image/jpeg' para un `in`.
                "tipo": (ev.mime_type or "image/jpeg").lower().strip(),
                "base64": base64.b64encode(crudo).decode(),
            })
        except Exception as e:                                   # noqa: BLE001
            #  Por tipo, sin `str(e)`: el mensaje puede traer la ruta.
            logger.warning("nota_al_isp: una foto no se pudo leer (%s)",
                           type(e).__name__)
    return salida


def anotar_reporte_del_tecnico(orden, profile=None) -> dict:
    """Escribe en el ticket del ISP lo que el tecnico reporto desde la app.

    Es el momento que hoy el tecnico hace a mano en WispHub. El texto sale de
    la plantilla, igual que el del cierre.
    """
    from campo.services.cierre_en_isp import numero_de_ticket, resumen_de

    ticket = numero_de_ticket(orden.contexto)
    if not ticket:
        return {"anotada": False, "codigo": "sin_ticket",
                "detalle": "la orden no nacio de un ticket del ISP"}

    texto = resumen_de(
        orden, "",
        encabezado=f"Reporte de campo de la OT #{orden.numero}. "
                   f"Pendiente de revision.")
    return _pedir(orden, {
        "ticket": ticket,
        "texto": texto,
        "momento": REPORTE_DEL_TECNICO,
        "vuelta": _vuelta_de(orden),
        #  LAS FOTOS VAN CON EL REPORTE, en la misma respuesta. El usuario:
        #  se ven en el ticket de Dexter y no en el de WispHub, y su equipo
        #  mira los dos. Una sola respuesta y no una por foto, porque
        #  `ticket-estado` es obligatorio en ese endpoint y cada llamada
        #  mueve el ticket (medido el 07/11/2026 contra produccion).
        "fotos": fotos_de_la_vuelta(orden),
        #  El nombre del tecnico SI va en este momento: es quien firma el
        #  reporte hoy a mano. En la devolucion no (decide el Supervisor).
        "actor": _nombre_de(profile),
    }, profile=profile)


# ---------------------------------------------------------------------------
#  2) LA DEVOLUCION
# ---------------------------------------------------------------------------

def anotar_devolucion(orden, *, requisitos=None, observacion: str = "",
                      profile=None) -> dict:
    """Escribe en el ticket que el trabajo volvio al tecnico, y por que.

    El ticket NO se cierra: queda En Progreso, que es lo que de verdad pasa.
    """
    from campo.services.cierre_en_isp import _tapar, numero_de_ticket

    ticket = numero_de_ticket(orden.contexto)
    if not ticket:
        return {"anotada": False, "codigo": "sin_ticket",
                "detalle": "la orden no nacio de un ticket del ISP"}

    lineas = [f"La OT #{orden.numero} vuelve a campo para corregir "
              f"(vuelta {_vuelta_de(orden)})."]
    pedidos = [str(x).strip() for x in (requisitos or []) if str(x).strip()]
    for nombre in pedidos[:MAX_REQUISITOS]:
        lineas.append(f"- Rehacer: {_tapar(nombre)}")
    if len(pedidos) > MAX_REQUISITOS:
        lineas.append(f"- (y {len(pedidos) - MAX_REQUISITOS} mas en Dexter)")
    #  La observacion es TEXTO LIBRE de una persona: pasa por `tapar` como
    #  todo lo demas. Es justo donde apareceria un telefono escrito a mano.
    if (observacion or "").strip():
        lineas.append(f"Observacion: {_tapar(observacion.strip())}")

    return _pedir(orden, {
        "ticket": ticket,
        "texto": "\n".join(lineas),
        "momento": DEVUELTA_AL_TECNICO,
        "vuelta": _vuelta_de(orden),
    }, profile=profile)


# ---------------------------------------------------------------------------
#  3) LO QUE EL SUPERVISOR VALIDO, para el texto del CIERRE
# ---------------------------------------------------------------------------

def anotar_avance(orden, momento: str, profile=None) -> dict:
    """Avisa en el ticket del ISP que el tecnico salio, o que llego.

    POR QUE  --  06/11/2026
    -----------------------
    El usuario marco "En camino" desde la app y el ticket siguio igual que
    cuando se abrio. Programacion mostraba el cambio --lee el estado de la
    orden-- y quien miraba el ticket no sabia si habia pasado algo.

    El ticket queda En Progreso, que lo fija la herramienta del catalogo
    (`argumentos_fijos: ticket-estado: "2"`). No se elige desde aca: si quien
    llama pudiera, un avance podria cerrar el ticket.

    Lleva el NOMBRE del tecnico: la pregunta que el ticket contesta en este
    momento es "¿quien va?", y una firma generica no la contesta.
    """
    from campo.services.cierre_en_isp import numero_de_ticket

    if momento not in TEXTO_DEL_AVANCE:
        return {"anotada": False, "codigo": "momento_desconocido",
                "detalle": momento}

    ticket = numero_de_ticket(orden.contexto)
    if not ticket:
        return {"anotada": False, "codigo": "sin_ticket",
                "detalle": "la orden no nacio de un ticket del ISP"}

    return _pedir(orden, {
        "ticket": ticket,
        "texto": f"{TEXTO_DEL_AVANCE[momento]} a la OT #{orden.numero}.",
        "momento": momento,
        "vuelta": _vuelta_de(orden),
        "actor": _nombre_de(profile),
    }, profile=profile)


def lo_que_falto(revision) -> list[str]:
    """Los puntos que la revision marco como NO cumplidos, en texto.

    Es lo que el tecnico necesita leer para saber que rehacer. Sale de la
    revision, que ya lo calculo punto por punto; aca no se vuelve a decidir
    nada, solo se escribe.
    """
    if not isinstance(revision, dict):
        return []
    fuera = []
    for p in revision.get("puntos") or []:
        if not isinstance(p, dict) or p.get("ok") is not False:
            continue
        texto = str(p.get("texto") or p.get("clave") or "").strip()
        if texto:
            fuera.append(texto)
    return fuera


def requisitos_a_rehacer(revision) -> list[str]:
    """Que se le pide al tecnico que rehaga.

    Primero lo que el checklist nombra como faltante (`sugeridas`), que son
    ids de requisitos de verdad. Si no hay --porque fallo otra cosa, como el
    reporte-- se usan las CLAVES de los puntos que no cumplieron: no es un id
    de evidencia, pero nombra el problema, y `requerir_correccion` exige que
    la devolucion diga QUE rehacer.
    """
    if not isinstance(revision, dict):
        return []
    sugeridas = [str(x).strip() for x in (revision.get("sugeridas") or [])
                 if str(x).strip()]
    if sugeridas:
        return sugeridas
    return [str(p.get("clave")).strip()
            for p in (revision.get("puntos") or [])
            if isinstance(p, dict) and p.get("ok") is False and p.get("clave")]


def anotar_revision_sin_cierre(orden, revision) -> dict:
    """El Supervisor reviso, NO cerro y tampoco devolvio: quedo una duda.

    POR QUE SE ESCRIBE IGUAL  --  06/11/2026
    ----------------------------------------
    El usuario pidio que el Supervisor deje su respuesta "sea cierre o no".
    Hasta hoy, una orden que quedaba en duda no dejaba NADA en el ticket del
    ISP: quien lo miraba veia el reporte del tecnico y despues silencio, sin
    saber si alguien lo habia mirado.

    No devuelve el trabajo a propósito: una duda no es un error. El caso que
    lo motiva es real -- «4 de 4 fotos piden una mirada» sobre fotos oscuras
    de un trabajo que estaba bien hecho. Devolverlo por eso le haria rehacer
    al tecnico algo que no esta mal.
    """
    from campo.services.cierre_en_isp import _tapar, numero_de_ticket

    ticket = numero_de_ticket(orden.contexto)
    if not ticket:
        return {"anotada": False, "codigo": "sin_ticket",
                "detalle": "la orden no nacio de un ticket del ISP"}

    lineas = [f"El Supervisor reviso la OT #{orden.numero} y NO la cerro: "
              f"queda para que la mire una persona."]
    dudas = [p for p in (revision or {}).get("puntos") or []
             if isinstance(p, dict) and p.get("ok") is None]
    for p in dudas[:MAX_REQUISITOS]:
        texto = str(p.get("texto") or p.get("clave") or "").strip()
        if texto:
            lineas.append(f"- {_tapar(texto)}")
    for texto in lo_que_falto(revision)[:MAX_REQUISITOS]:
        lineas.append(f"- {_tapar(texto)}")

    return _pedir(orden, {
        "ticket": ticket,
        "texto": "\n".join(lineas),
        "momento": REVISION_SIN_CIERRE,
        "vuelta": _vuelta_de(orden),
    })


def texto_de_la_revision(foto) -> str:
    """Lo que el Supervisor escribe en el ticket al validar y cerrar.

    COMO LO ESCRIBE UNA PERSONA HOY  --  06/11/2026
    -----------------------------------------------
    El usuario mostro un ticket real: el supervisor valida con dos palabras,
    "SE VALIDA TICKET", y nada mas. Esa es la frase que su equipo reconoce, y
    una validacion del Supervisor IA no tiene por que leerse distinta de una
    humana -- quien revisa el ticket meses despues no deberia tener que
    aprender dos formatos para el mismo hecho.

    Se le suma UNA linea con los puntos que la revision miro, por decision del
    usuario: la frase sola no deja rastro de QUE se valido, y eso es lo unico
    que un cierre automatico puede ofrecer que uno a mano no.

    SOLO LA ESTRUCTURA, NUNCA EL TEXTO DE CADA PUNTO. Cada punto puede traer
    el detalle de una medicion o de un material; lo que hace falta en el
    ticket es QUE se miro y como salio. Menos superficie para que un dato del
    cliente se escape a un sistema de terceros, y mas corto para quien lo lee.

    Devuelve `''` cuando no hay revision -- y entonces el cierre escribe el
    reporte completo, como hacia antes, en vez de afirmar que alguien reviso.
    """
    if not isinstance(foto, dict):
        return ""
    puntos = foto.get("puntos")
    if not isinstance(puntos, list) or not puntos:
        return ""

    #  «SIN DATOS» NO DICE NADA  --  07/11/2026
    #
    #  El usuario, leyendo su propia validacion en el ticket: «fotos sin
    #  datos». En el checklist se lee bien; en fotos suena a que la foto no
    #  traia metadatos, y lo que paso es otra cosa -- la inspeccion no pudo
    #  concluir, porque una foto quedo pidiendo atencion.
    #
    #  «no se pudo verificar» es verdad para los cuatro puntos y no inventa
    #  detalle. Quien lea el ticket en seis meses sabe que ese punto quedo
    #  abierto, que es justo lo que «sin datos» escondia.
    como = {True: "ok", False: "no cumple", None: "no se pudo verificar"}
    partes = []
    for p in puntos:
        if not isinstance(p, dict):
            continue
        clave = str(p.get("clave") or "").strip()
        if not clave:
            continue
        partes.append(f"{clave} {como.get(p.get('ok'), 'sin datos')}")
    if not partes:
        return ""
    return ("SE VALIDA TICKET" + '\n' + "Revision: " + "; ".join(partes))
