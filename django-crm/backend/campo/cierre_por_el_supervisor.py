# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR CIERRA SOLO LO QUE SU REVISION DIO POR BUENO  --  30/10/2026
================================================================================

SPEC/objetivos/revision-del-cierre.md. El usuario: «¿de que manera hacemos
para que el supervisor cierre solo?». Una FASE del ciclo del Supervisor
(`operaciones/supervisor.py::correr_ciclo`), despues de la medicion despues
del arreglo: una vez por hora, como las demas.

LAS PUERTAS, las mismas que las otras tareas de accion y todas fail-closed
(`operaciones/ordenes_de_despacho._puertas`):

    la tarea `aprobar_y_cerrar_lo_que_dio_por_bueno`, delegada por una
    persona desde el chat del Supervisor (`tareas_delegadas`)
    el nivel 3 de la empresa (`autonomia.puede`): con el interruptor de
    emergencia detenido no se cierra NADA, tampoco lo de adentro
    que la organizacion tenga empresa en el motor (`areas_del_tenant.tenant_de`)

Sin alguna, SOMBRA: no escribe nada y dice cuantas cerraria. Y del lado del
motor, el ticket pasa por cinco compuertas mas (interruptor, techo, Autonomia 2
con B-7, autorizacion de la herramienta, y que la herramienta no exija
aprobacion humana -- hoy la exige: M06-E).

QUE CIERRA: lo que `revision_del_cierre` marca «Se puede cerrar». Primero el
ticket afuera; SOLO si quedo cerrado (o no habia ticket), aprobar y cerrar
adentro, bajo bloqueo. Si el motor se niega o no se sabe, queda para una
persona y la tarjeta dice por que.

QUE NO (auditoria de frontera, 30/10/2026):
- «Revisalo» y «No se cierra»: una persona.
- Una orden en vuelta > 1, SALVO la que devolvio el propio Supervisor y cuyo
  ticket nunca se cerro. Su ticket pudo cerrarse y reabrirse en el ISP, y
  nadie lo sabe desde aca (H4). Hasta el 09/11/2026 el filtro era «toda
  vuelta > 1»; se afino porque desde el 08/11 el Supervisor devuelve ordenes
  el mismo, y de ESA trayectoria hay registro entero: `EVENTO_DEVUELTA` dice
  que la devolvio el, y la ausencia de `EVENTO_CERRADO` que nunca toco el
  ticket. Si la devolvio una PERSONA sigue afuera: esa persona pudo cerrar el
  ticket a mano en WispHub, y ahi no hay fila que leer.
- Una de falla cuya medicion despues del arreglo todavia no llego: la revision
  la marca «Revisalo» (H6). Si no se pudo saber cuales esperan medicion, no se
  cierra ninguna.

SI CAMBIO EN EL MEDIO: el ticket quedo cerrado y, mientras tanto, una persona
devolvio o valido la orden. No se pisa lo que hizo la persona; se deja una
ALERTA en la orden, porque el ticket del ISP dice una cosa y Dexter otra (H4).
================================================================================
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

SOMBRA = "sombra"
ACCION = "accion"

#: Lo que se anota en la bitacora de la orden.
EVENTO_BLOQUEADO = "cierre_del_supervisor_bloqueado"
EVENTO_CERRADA = "cerrada_por_el_supervisor"
EVENTO_DIVERGENCIA = "ticket_cerrado_con_la_orden_cambiada"
#: Se tomo ESTA orden para intentarla. Se escribe ANTES de hablarle al motor.
EVENTO_INTENTO = "cierre_del_supervisor_en_curso"
#: El Supervisor devolvio la orden solo, porque la revision encontro
#: algo que NO cumple. Distinto de `EVENTO_BLOQUEADO`, que es "no se pudo".
EVENTO_DEVUELTA = "devuelta_por_el_supervisor"

#: Cada cuanto se vuelve a intentar una orden que el motor no dejo cerrar. Una
#: persona puede despertar el ciclo con el boton; esto evita que cada toque
#: sea otro intento.
MINUTOS_ENTRE_INTENTOS = 60

#: Lo que el CRM le contesta a este lado y deja seguir: el ticket quedo
#: cerrado, ya lo estaba, o la orden no tiene ticket del ISP.
SIGUE = ("cerrado", "ya_cerrado", "sin_ticket")


def _tarea():
    from operaciones import tareas_delegadas as td
    return td.CERRAR_LO_REVISADO


def puertas(org) -> str:
    """Por que NO puede cerrar, o "" si puede. Texto fijo: va a un log."""
    from operaciones import areas_del_tenant, autonomia
    from operaciones import tareas_delegadas as td

    if not areas_del_tenant.tenant_de(org):
        return f"{areas_del_tenant.SIN_EMPRESA}: sin saber de que empresa es el ticket, no se cierra"
    try:
        if not td.esta_delegada(org, _tarea()):
            return ("nadie le delego al Supervisor que cierre lo que da por "
                    "bueno: se le pide desde su chat")
    except Exception as e:                                       # noqa: BLE001
        return f"no se pudo comprobar la tarea ({type(e).__name__})"
    try:
        veredicto = autonomia.puede(org, td.CATALOGO[_tarea()]["exige_nivel"]) or {}
    except Exception as e:                                       # noqa: BLE001
        veredicto = {"puede": False, "motivo": type(e).__name__}
    if not veredicto.get("puede"):
        return "la empresa no tiene autorizado que el Supervisor cierre ordenes"
    return ""


def _reclamar(orden, ahora) -> bool:
    """Toma ESTA orden para intentarla, o dice que ya la tomo alguien.

    POR QUE UN RECLAMO Y NO UN 'select' PREVIO  --  auditoria de frontera,
    31/10/2026 (H6)
    ----------------------------------------------------------------------
    El reporte del tecnico y el "finalizar" son DOS peticiones, segundos
    aparte, y cada una despierta esta fase. Los dos filtros que habia se
    pueden pasar a la vez: `EVENTO_BLOQUEADO` solo existe si ya fallo, y el
    `_ya_cerrado` de `cierre_en_isp` es un select cuyo evento se escribe
    DESPUES del 200. La clave primaria del motor garantiza que a WispHub le
    llegue un solo POST --eso ya andaba-- pero el desenlace de la segunda
    tarea no era inocuo: escribia una alerta de divergencia falsa sobre el
    camino feliz, o apagaba los reintentos una hora, o dejaba la clave
    quemada y la orden sin poder cerrarse sola nunca mas.

    Esto serializa las dos sobre la FILA de la orden: la segunda espera a que
    la primera escriba su marca, la lee y se va. La transaccion se cierra
    ANTES de hablarle al motor -- ninguna transaccion abierta mientras se
    espera una operacion externa (CLAUDE.md §12).

    LA MARCA CADUCA con la misma ventana que los bloqueos: una tarea que se
    muera dejandola puesta no puede congelar la orden para siempre.
    """
    from campo.models import EventoTrabajo

    desde = ahora - timedelta(minutes=MINUTOS_ENTRE_INTENTOS)
    with transaction.atomic():
        #  El lock es sobre la orden y no sobre los eventos: es la fila que
        #  las dos tareas tienen en comun.
        type(orden).objects.select_for_update().filter(pk=orden.pk).first()
        if EventoTrabajo.objects.filter(
                org=orden.org, orden=orden,
                tipo__in=(EVENTO_BLOQUEADO, EVENTO_INTENTO),
                created_at__gte=desde).exists():
            return False
        EventoTrabajo.objects.create(org=orden.org, orden=orden,
                                     tipo=EVENTO_INTENTO, datos={})
    return True


def revisadas(org, ahora, *, solo=None) -> list | None:
    """TODAS las candidatas con su revision, sin filtrar por veredicto.

    EXISTE PARA QUE LOS TRES CAMINOS MIREN LO MISMO  --  06/11/2026
    ---------------------------------------------------------------
    Hasta hoy solo se recorrian las de veredicto "se puede cerrar"; las otras
    dos --"no cumple" y "hay dudas"-- no las miraba nadie, y el ticket del ISP
    no se enteraba de que alguien las habia revisado. El usuario pidio que el
    Supervisor deje su respuesta "sea cierre o no".

    Una sola consulta y un solo juego de filtros: la vuelta, el estado y la
    medicion pendiente. Duplicarlos en un camino nuevo es como se pierde una
    guarda sin que nadie lo note.
    """
    from campo import revision_del_cierre as RC
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.services.cierre_en_isp import EVENTO_CERRADO

    pendientes = RC.pendientes_de_medir(org, ahora)
    if pendientes is None:
        return None

    #  LA VUELTA SOLA NO ERA LA PREGUNTA  --  09/11/2026
    #
    #  H4 dejaba afuera toda orden en vuelta > 1 con este motivo escrito: «su
    #  ticket pudo cerrarse y reabrirse en el ISP en la vuelta anterior, y
    #  NADIE LO SABE DESDE ACA». La condicion era la ignorancia, no el numero
    #  de vuelta -- y desde el 08/11 el Supervisor devuelve ordenes el mismo,
    #  asi que hay una clase entera de ordenes devueltas cuyo ticket Dexter
    #  JAMAS toco.
    #
    #  Y eso si se sabe: cerrar el ticket del ISP escribe `EVENTO_CERRADO`
    #  (`campo/services/cierre_en_isp.py`). Sin esa fila, no hubo cierre que
    #  alguien pudiera reabrir. Se lee la bitacora en vez de suponer.
    #
    #  LO QUE NO CAMBIA: una orden en vuelta > 1 cuyo ticket SI se cerro
    #  alguna vez sigue afuera, exactamente como la dejo H4. Y esto no dice
    #  nada de un cierre hecho a mano por una persona en WispHub: eso Dexter
    #  no lo ve, ni lo veia en la vuelta 1 -- el filtro por vuelta nunca
    #  protegio de ese caso.
    #
    #  El usuario lo encontro en la OT 212: la devolvio el Supervisor, el
    #  tecnico corrigio la foto, los siete puntos quedaron en verde y la
    #  orden no cerraba, sin que la pantalla pudiera decir por que.
    #  SOLO LA TRAYECTORIA QUE DEXTER CONOCE ENTERA. Una orden en vuelta > 1
    #  entra unicamente si EL SUPERVISOR fue quien la devolvio y su ticket
    #  nunca se cerro. Si la devolvio una PERSONA, esa persona pudo cerrar el
    #  ticket a mano en WispHub, y ahi H4 sigue entero: no hay fila que leer.
    #
    #  Lo encontro la guarda `test_v_una_orden_ya_devuelta_no_la_cierra_solo`,
    #  que se puso en rojo con la primera version de este cambio -- su orden
    #  en vuelta 2 no tiene devolucion del Supervisor, y aun asi entraba.
    devueltas_por_el_supervisor = EventoTrabajo.objects.filter(
        org=org, tipo=EVENTO_DEVUELTA).values_list("orden_id", flat=True)
    ya_cerraron = EventoTrabajo.objects.filter(
        org=org, tipo=EVENTO_CERRADO).values_list("orden_id", flat=True)
    candidatas = OrdenTrabajo.objects.filter(
        org=org, estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion__in=(OrdenTrabajo.PENDIENTE, OrdenTrabajo.REQUIERE_REVISION),
    ).filter(
        Q(vuelta__lte=1)
        | (Q(id__in=devueltas_por_el_supervisor) & ~Q(id__in=ya_cerraron)))
    if solo is not None:
        candidatas = candidatas.filter(pk=solo)
    salida = []
    for orden in candidatas:
        revision = RC.revisar(orden, pendientes=pendientes)
        if revision:
            salida.append((orden, revision))
    return salida


def listas_para_cerrar(org, ahora, *, solo=None) -> list | None:
    """[(orden, revision)] que dio por buenas, o None si no se pudo saber
    cuales esperan medicion (y entonces no se cierra ninguna).

    `solo` acota a UNA orden (su pk) sin cambiar ni un criterio: lo usa el
    disparo inmediato de `cerrar_esta_orden`. Que el filtro viva en UN solo
    lugar es lo que evita que las dos entradas --el ciclo horario y el reporte
    recien llegado-- se separen el dia que se agregue una condicion. Desde el
    06/11/2026 ese lugar es `revisadas`, que ademas alcanza a las que no se
    cierran.
    """
    from campo import revision_del_cierre as RC

    todas = revisadas(org, ahora, solo=solo)
    if todas is None:
        return None
    return [(o, r) for o, r in todas if r["veredicto"] == RC.CERRAR]


def atender_la_que_no_cierra(orden, revision) -> str:
    """El Supervisor devuelve al tecnico lo que objetivamente le falto.

    EL USUARIO  --  06/11/2026
    --------------------------
    "en caso de que no cumpla uno de los requisito debe devolver al tecnico
    indicando el error o lo que falto".

    LO QUE ESTA FUNCION NO TOCA, Y POR QUE
    ---------------------------------------
    El alcance nacio mas ancho y cuatro guardas lo frenaron. No eran pruebas
    desactualizadas: cada una describe un caso donde actuar es peor que no
    hacer nada, y las cuatro afirman `post.assert_not_called()` -- que al ISP
    no le llegue NADA.

    1. LA QUE ESPERA LA MEDICION (`test_m`, `test_m2`). La medicion de la ONU
       se mira a las 48 h; hasta entonces el veredicto es "hay dudas" con
       `medicion: None`. Escribir "queda para que lo mire una persona" en el
       ticket del CLIENTE seria mentir --no hay nada que mirar, se espera un
       reloj-- y repetirlo cada hora llenaria el ticket de ruido.

    2. "HAY DUDAS" EN GENERAL. Hoy ese veredicto no distingue "falta esperar"
       de "algo no se pudo verificar", y sin esa distincion no hay nada
       honesto que escribir. Queda afuera hasta que el veredicto sepa decir
       cual es cual.

    3. LO QUE FALLA SIN UN REQUISITO CONCRETO (`test_s4`, `test_i2b`). Cuando
       el tecnico dice que el servicio no quedo funcionando, el punto que
       falla es "servicio", que no es algo que el pueda "rehacer": puede
       necesitar material, un tercero, o que alguien decida. Devolverselo
       seria mandarle de vuelta un problema que no es suyo.

    Queda SOLO el caso inequivoco: "no cumple" con requisitos del checklist
    --falta esta foto, falta este campo--, donde el dato es duro y el tecnico
    puede hacer algo con el.

    Devuelve 'devuelta' | 'nada'. Nunca levanta: corre dentro del ciclo y un
    fallo aca no puede frenar las demas ordenes.
    """
    from campo import revision_del_cierre as RC
    from campo.models import EventoTrabajo
    from campo.services import nota_al_isp
    from campo.services.transiciones import requerir_correccion

    #  «HAY DUDAS» ENTRA, PERO SOLO CON ALGO CONCRETO QUE PEDIR  --  08/11/2026
    #
    #  El punto 2 de arriba dejaba afuera todo veredicto REVISAR, y nombraba
    #  la condicion para levantarlo: «hoy ese veredicto no distingue "falta
    #  esperar" de "algo no se pudo verificar", y sin esa distincion no hay
    #  nada honesto que escribir. Queda afuera HASTA QUE EL VEREDICTO SEPA
    #  DECIR CUAL ES CUAL».
    #
    #  Ya sabe. `revision_del_cierre._fotos_que_muestran_otra_cosa` nombra el
    #  requisito cuya foto el modelo afirma que muestra OTRA COSA --la marca
    #  `MUESTRA: no`, nunca «no se sabe»--, y eso entra en `sugeridas`. Una
    #  revision que dice «hay dudas» Y ademas nombra que rehacer no es «falta
    #  esperar»: es algo que el tecnico puede arreglar.
    #
    #  Lo de siempre lo sigue filtrando el `if not requisitos` de abajo: una
    #  duda sin nada concreto que pedir --la medicion que no llego todavia,
    #  una foto que el modelo no supo leer-- sale por ahi y no se devuelve.
    veredicto = (revision or {}).get("veredicto")
    if veredicto not in (RC.NO_CERRAR, RC.REVISAR):
        return "nada"

    #  SOLO LOS DEL CHECKLIST. `requisitos_a_rehacer` cae a las claves de los
    #  puntos que fallaron cuando no hay faltantes; esas no sirven para pedir
    #  que se rehaga algo (ver el punto 3 de arriba).
    requisitos = [str(x).strip() for x in (revision or {}).get("sugeridas") or []
                  if str(x).strip()]
    if not requisitos:
        return "nada"

    #  SIN TOPE DE DEVOLUCIONES  --  decision del usuario, 09/11/2026
    #
    #  Se probo con un tope de una sola devolucion automatica --el que
    #  `vuelta__lte=1` daba sin decirlo-- y la primera prueba en vivo lo
    #  encontro enseguida: una foto equivocada en una orden ya devuelta no
    #  volvia al tecnico. Preguntado, el usuario eligio que devuelva siempre.
    #
    #  POR QUE ES SEGURO, Y NO UNA SIMPLE PREFERENCIA: no hay bucle que la
    #  maquina pueda correr sola. Una orden devuelta queda en
    #  CORRECCION_REQUERIDA, y `revisadas` solo mira las COMPLETADA_CAMPO: no
    #  vuelve a entrar hasta que EL TECNICO mande otro reporte. Cada vuelta
    #  exige trabajo humano del otro lado, asi que el ida y vuelta no puede
    #  acelerarse solo ni repetirse sin que alguien lo provoque.
    #
    #  LO QUE SE PIERDE: si el tecnico no entiende que le piden, nadie se
    #  entera de que ya van tres. Hoy eso lo cubre la bitacora de la orden,
    #  que cuenta las vueltas. El dia que haya una medicion de cuantas
    #  ordenes pasan de dos vueltas, se puede reabrir con ese numero.

    try:
        observacion = " | ".join(nota_al_isp.lo_que_falto(revision))[:500]
        #  EL TICKET PRIMERO, LA TRANSICION DESPUES. Al reves, subir la vuelta
        #  cambiaria la clave idempotente de la nota y la devolucion de ESTA
        #  vuelta se escribiria con el numero de la siguiente.
        nota_al_isp.anotar_devolucion(orden, requisitos=requisitos,
                                      observacion=observacion)
        requerir_correccion(orden, requisitos=requisitos,
                            observacion=observacion)
        EventoTrabajo.objects.create(
            org=orden.org, orden=orden, tipo=EVENTO_DEVUELTA,
            datos={"requisitos": requisitos})
        return "devuelta"
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Supervisor: no se pudo devolver la orden (%s)",
                       type(e).__name__)
        return "nada"

def _intentar(orden, revision, ahora) -> str:
    """Cerrar UNA: afuera primero, adentro despues. Devuelve que paso.

    'salteada' | 'cerrada' | 'bloqueada' | 'divergencia' | 'cambio'. Lo
    comparten la fase horaria y el disparo inmediato: un camino nuevo que
    repitiera estos pasos a mano es como se pierde una de las guardas.
    """
    from campo.models import EventoTrabajo
    from campo.services import cierre_en_isp

    if not _reclamar(orden, ahora):
        return "salteada"
    #  CON LO QUE VALIDO (06/11/2026): el usuario pidio que el Supervisor
    #  "deje su respuesta de lo validado". La `revision` ya esta en la mano;
    #  lo que faltaba era escribirla del lado del ISP y no solo en Dexter.
    try:
        from campo.services.nota_al_isp import texto_de_la_revision

        lo_validado = texto_de_la_revision(revision)
    except Exception:                                            # noqa: BLE001
        lo_validado = ""
    ticket = cierre_en_isp.cerrar_ticket_por_el_supervisor(
        orden, revision, extra=lo_validado)
    if ticket["estado"] not in SIGUE:
        EventoTrabajo.objects.create(
            org=orden.org, orden=orden, tipo=EVENTO_BLOQUEADO,
            datos={"estado": ticket["estado"], "detalle": ticket.get("detalle", "")})
        return "bloqueada"
    if _aprobar_y_cerrar(orden, revision, ticket):
        return "cerrada"
    if ticket["estado"] == "cerrado":
        EventoTrabajo.objects.create(
            org=orden.org, orden=orden, tipo=EVENTO_DIVERGENCIA,
            datos={"ticket_isp": ticket["estado"]})
        return "divergencia"
    return "cambio"


def cerrar_esta_orden(orden, *, ahora=None) -> dict:
    """EL MISMO CIERRE, APENAS LLEGA EL REPORTE  --  31/10/2026

    El usuario: «que después que el supervisor revise el ticket que mandó el
    técnico lo revise enseguida e indique si lo cierra o no». La fase de abajo
    corre una vez por hora; esto corre a los segundos, para ESTA orden.

    NO ES UNA SEGUNDA PUERTA. Pasa por `puertas()` y por `listas_para_cerrar`
    igual que la fase, con los mismos filtros --la vuelta, la medicion que
    falta, el veredicto-- y por `_intentar`, que es el mismo codigo. Lo unico
    que cambia es QUIEN la despierta y CUANTAS mira.

    Si todavia no corresponde --el reporte llego pero la orden aun no esta
    completada, o espera la medicion-- no escribe nada y lo dice. El ciclo
    horario la vuelve a mirar, que es la red de atras.
    """
    ahora = ahora or timezone.now()
    motivo = puertas(orden.org)
    if motivo:
        logger.info("Supervisor: cierre inmediato en sombra (%s)", motivo)
        return {"modo": SOMBRA, "por_que": motivo, "resultado": ""}
    from campo import revision_del_cierre as RC

    todas = revisadas(orden.org, ahora, solo=orden.pk)
    if todas is None:
        return {"modo": ACCION, "por_que": "no se pudo saber si espera la medicion",
                "resultado": ""}
    if not todas:
        #  TEXTO FIJO: ya esta validada, o es una vuelta posterior, o no esta
        #  completada todavia. No hay revision que mirar.
        return {"modo": ACCION, "por_que": "no hay nada que revisar ahora",
                "resultado": ""}
    una, revision = todas[0]
    if revision["veredicto"] == RC.CERRAR:
        return {"modo": ACCION, "por_que": "",
                "resultado": _intentar(una, revision, ahora)}
    #  NO CIERRA, PERO ALGO PASA IGUAL (06/11/2026). Antes esta rama se iba en
    #  silencio y el ticket del ISP no se enteraba de que alguien habia
    #  revisado. Ahora se devuelve --si falta algo duro-- o se deja escrito que
    #  quedo en duda.
    return {"modo": ACCION, "por_que": "la revision no la dio por buena ahora",
            "resultado": atender_la_que_no_cierra(una, revision)}


def cerrar_lo_revisado(org, *, ahora=None) -> dict:
    """La fase. `{"cierre_de_lo_revisado": {...}}` para el resumen del ciclo."""
    from campo import revision_del_cierre as RC

    ahora = ahora or timezone.now()
    listas = listas_para_cerrar(org, ahora)
    motivo = puertas(org)
    if listas is None:
        motivo = motivo or "no se pudo saber que ordenes esperan la medicion"
        listas = []
    if motivo:
        #  TEXTO FIJO y conteos: nada de la orden ni del cliente al log.
        logger.info("Supervisor: cierre de lo revisado en sombra (%s): cerraria %d",
                    motivo, len(listas))
        return {"cierre_de_lo_revisado": {"modo": SOMBRA, "por_que": motivo,
                                          "cerraria": len(listas), "cerradas": 0,
                                          "bloqueadas": 0}}
    cerradas = bloqueadas = 0
    for orden, revision in listas:
        paso = _intentar(orden, revision, ahora)
        if paso == "cerrada":
            cerradas += 1
        elif paso == "bloqueada":
            bloqueadas += 1

    #  Y LAS QUE NO CIERRAN (06/11/2026). Son las mismas candidatas, con otro
    #  veredicto: hasta hoy nadie las miraba y el ticket del ISP se quedaba sin
    #  saber que habian sido revisadas. Se recorren DESPUES de los cierres a
    #  proposito: si el ciclo se corta a la mitad, lo que se pierde es el aviso,
    #  no un cierre.
    devueltas = 0
    todas = revisadas(org, ahora) or []
    for orden, revision in todas:
        if revision["veredicto"] == RC.CERRAR:
            continue
        if atender_la_que_no_cierra(orden, revision) == "devuelta":
            devueltas += 1

    return {"cierre_de_lo_revisado": {"modo": ACCION, "por_que": "",
                                      "cerraria": len(listas), "cerradas": cerradas,
                                      "bloqueadas": bloqueadas,
                                      "devueltas": devueltas}}


def _aprobar_y_cerrar(orden, revision, ticket) -> bool:
    """Adentro, en una transaccion: aprobar y cerrar, a nombre del Supervisor
    (`profile=None`, y la bitacora lo dice). Si una persona la valido o la
    devolvio en el medio, no se pisa: se lee bajo bloqueo."""
    from campo.models import EventoTrabajo, OrdenTrabajo
    from campo.services.transiciones import aprobar, cerrar_orden

    motivos = "; ".join(p["texto"] for p in revision["puntos"])
    with transaction.atomic():
        fresca = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
        if (fresca.estado_operativo != OrdenTrabajo.COMPLETADA_CAMPO
                or fresca.estado_validacion not in (OrdenTrabajo.PENDIENTE,
                                                    OrdenTrabajo.REQUIERE_REVISION)
                or fresca.vuelta != orden.vuelta):
            return False
        from campo.revision_del_cierre import guardar_foto

        guardar_foto(fresca, revision)
        fresca = aprobar(fresca, profile=None,
                         observacion=f"Aprobada por el Supervisor: {motivos}")
        fresca = cerrar_orden(fresca, profile=None,
                              metadatos={"por": "supervisor", "ticket_isp": ticket["estado"]})
        EventoTrabajo.objects.create(
            org=fresca.org, orden=fresca, tipo=EVENTO_CERRADA,
            datos={"veredicto": revision["veredicto"], "ticket_isp": ticket["estado"],
                   "puntos": [p["clave"] for p in revision["puntos"]]})
    return True
