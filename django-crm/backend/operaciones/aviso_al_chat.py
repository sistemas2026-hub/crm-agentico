# -*- coding: utf-8 -*-
"""
===============================================================================
 EL SUPERVISOR AVISA EN EL CHAT LO QUE CERRO, SIN QUE NADIE PREGUNTE
===============================================================================

QUE RESUELVE
------------
Hasta el 09/10/2026 el Supervisor cerraba casos solo y no lo contaba en
ningun lado donde una persona estuviera mirando. Quedaba escrito en la
propuesta y en la auditoria --que es lo correcto para el registro-- pero
enterarse exigia ir a buscarlo. Quien delego la tarea desde el chat se iba sin
saber si habia pasado algo.

Ahora, cuando el ciclo cierra casos, deja un mensaje en LA MISMA conversacion
donde se delego la tarea.

A QUIEN SE LE ESCRIBE, Y A QUIEN NO
-----------------------------------
A quien delego la tarea, nunca a otro. Hay dos formas de encontrarlo, en este
orden:

  1. La conversacion guardada en la tarea ('TareaDelegada.conversacion_id').
     Ese dato viaja desde el chat por el mismo camino verificado que el actor
     -- nunca como algo que el modelo pueda dictar en un mensaje.

  2. Si no hay ninguna --la tarea se delego antes del 09/10/2026, cuando ese
     campo no existia-- la ULTIMA conversacion de la persona que la delego, y
     se guarda para que el respaldo corra una sola vez.

Lo que NO se hace es buscar "la ultima conversacion" a secas: esa puede ser de
otra persona, que veria aparecer cierres que no autorizo. El filtro es por
quien delego, no por fecha.

El respaldo no se agrego por prolijidad: sin el, las tareas ya delegadas no
recibirian aviso NUNCA, y el arreglo obvio --volver a delegarlas-- no
funciona. El chat ve que ya estan activas y contesta "no hace falta", que es
lo correcto de su parte. Medido en vivo el 09/10/2026.

ESTO NO ES UNA NOTIFICACION, ES UN RENGLON DE LA CONVERSACION
--------------------------------------------------------------
El mensaje se guarda con rol 'supervisor', igual que cualquier respuesta suya.
Eso tiene una consecuencia buena y hay que saberla: entra en el historial que
el modelo lee en el turno siguiente. Si despues preguntas "¿que cerraste?", el
Supervisor no necesita volver a consultarlo -- ya esta en la conversacion.

Y UNA MALA, que se acota aqui: un aviso por hora llenaria el historial de
ruido y empujaria afuera lo que importa. Por eso solo se escribe CUANDO HUBO
CIERRES. Una corrida que no cerro nada no deja mensaje; si alguien quiere
saber que el ciclo corrio igual, eso esta en el log y en el panel de
actividad, que es donde corresponde.

NO LEVANTA NUNCA
----------------
Avisar es lo ultimo que pasa y lo menos importante: los casos YA se cerraron,
y eso esta guardado. Si la conversacion se borro, si la base falla, si el
texto no se puede armar -- se registra y se sigue. Un cierre correcto no se
puede perder porque no se pudo contar.

SIN DATOS DE CLIENTE MAS ALLA DE LO QUE EL CHAT YA MUESTRA. Se nombra el caso
por su numero de ticket del proveedor, que es lo que una persona usa para
buscarlo, y nunca el nombre ni el documento del abonado.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#  CUANTOS CASOS SE NOMBRAN UNO POR UNO antes de resumir. Con el atraso de hoy
#  --noventa casos-- una lista completa seria un muro de texto que nadie lee, y
#  encima entra en el historial del modelo. Diez alcanzan para reconocer lo que
#  paso; el total siempre se dice.
TOPE_DETALLADOS = 10


#  La evidencia guarda el veredicto como "diagnostico del equipo: <razon>",
#  que tiene sentido en una lista de ocho observaciones donde hay que saber
#  cual es cual. En un aviso que YA dice que son cierres por diagnostico, ese
#  prefijo se repite en cada renglon y no agrega nada.
_PREFIJO_EVIDENCIA = "diagnostico del equipo:"


def _linea(cierre: dict) -> str:
    """
    Un renglon por caso: el ticket del proveedor y por que se cerro.

    SE PREFIERE EL TICKET y no la 'referencia': esa la devuelve el motor y es
    su clave de idempotencia ('propuesta:<uuid>'), que no sirve para buscar
    nada. Medido el 09/10/2026 leyendo el primer aviso que se escribio de
    verdad -- decia 'propuesta:a9499ad3-cb67-4c23-a85e-ac05fa3d1b24' y era
    ilegible.
    """
    ref = str(cierre.get("ticket") or cierre.get("referencia") or "").strip()
    porque = str(cierre.get("porque") or "").strip()
    if porque.lower().startswith(_PREFIJO_EVIDENCIA):
        porque = porque[len(_PREFIJO_EVIDENCIA):].strip()
    #  El porque viene redactado desde 'diagnostico_optico.porque_del_cierre',
    #  que es quien sabe si fue por señal optica o por ping. Aqui no se
    #  reinterpreta: repetirlo con otras palabras seria una segunda version de
    #  la misma afirmacion, y tarde o temprano dirian cosas distintas.
    if not ref:
        return f"- {porque}" if porque else "- (caso sin referencia)"
    return f"- ticket {ref}: {porque}" if porque else f"- ticket {ref}"


def redactar(cerrados: list[dict]) -> str:
    """
    El texto del aviso. Funcion aparte y pura, para poder probarla sin base.

    NO LO ESCRIBE EL MODELO, y es deliberado: esto afirma que unos casos se
    cerraron. Pedirle a un modelo que redacte un hecho consumado es darle la
    oportunidad de matizarlo, y lo que hay que decir aqui es exactamente lo
    que paso.
    """
    n = len(cerrados)
    if n == 1:
        cabeza = "Cerré 1 caso que el proveedor ya tenía cerrado:"
    else:
        cabeza = f"Cerré {n} casos que el proveedor ya tenía cerrados:"

    lineas = [_linea(c) for c in cerrados[:TOPE_DETALLADOS]]
    if n > TOPE_DETALLADOS:
        lineas.append(f"- …y {n - TOPE_DETALLADOS} más.")

    return "\n".join([cabeza, *lineas])


def avisar_cierres(org, cerrados: list[dict], *, ahora=None) -> bool:
    """
    Deja el aviso en la conversación donde se delegó la tarea.

    Devuelve si se escribió. No levanta: ver el encabezado.
    """
    if not cerrados:
        return False

    try:
        from django.utils import timezone

        from operaciones import tareas_delegadas as td
        from operaciones.chat_modelos import (ConversacionSupervisor,
                                              MensajeSupervisor, RolMensaje)
        from operaciones.tareas_modelos import TareaDelegada

        #  LA CONVERSACION DE LA TAREA QUE PRODUJO EL CIERRE. Es
        #  'CERRAR_DESINCRONIZADOS' y no la del ciclo: el ciclo solo despierta
        #  al Supervisor, y quien autorizo CERRAR es quien tiene que
        #  enterarse de que cerro.
        fila = (TareaDelegada.objects
                .filter(org=org, clave=td.CERRAR_DESINCRONIZADOS, activa=True)
                .first())
        if fila is None:
            logger.info("Supervisor: %s cierres y la tarea no esta delegada",
                        len(cerrados))
            return False

        conversacion = None
        if fila.conversacion_id:
            conversacion = ConversacionSupervisor.objects.filter(
                org=org, id=fila.conversacion_id).first()

        #  EL RESPALDO: LA ULTIMA CONVERSACION DE QUIEN LA DELEGO  --  09/10
        #  ----------------------------------------------------------------
        #  'conversacion_id' se empezo a guardar el 09/10/2026. Las tareas
        #  delegadas ANTES lo tienen vacio, y sin respaldo el aviso no saldria
        #  nunca para ellas. El arreglo obvio --"volve a delegarla"-- no
        #  funciona: el chat ve que ya esta activa y contesta "no hace falta",
        #  que es lo correcto de su parte. Medido en vivo ese mismo dia.
        #
        #  NO ES "CUALQUIER CONVERSACION", y la diferencia es toda: es la
        #  ultima de LA PERSONA QUE DELEGO LA TAREA. Esa persona autorizo
        #  estos cierres; contarle lo que se cerro no le revela nada que no
        #  haya habilitado. Escribirle a otro si seria un problema, y por eso
        #  el filtro es por 'actor' y no por fecha a secas.
        #
        #  Y SE GUARDA para la proxima: asi el respaldo corre una sola vez por
        #  tarea, y a partir de ahi el aviso va siempre a la misma
        #  conversacion en vez de saltar a la mas reciente cada hora.
        if conversacion is None and fila.delegada_por_id:
            conversacion = (ConversacionSupervisor.objects
                            .filter(org=org, actor_id=fila.delegada_por_id,
                                    archivada=False)
                            .order_by("-ultimo_mensaje_en")
                            .first())
            if conversacion is not None:
                fila.conversacion_id = conversacion.id
                fila.save(update_fields=["conversacion_id", "updated_at"])
        if conversacion is None:
            #  Ni la guardada ni ninguna de quien delego. Pasa si la
            #  conversacion se borro --la retencion las vence al año-- o si la
            #  tarea se delego desde fuera del chat y esa persona nunca abrio
            #  una. Es un caso normal, no un error, y no se busca a otro
            #  destinatario.
            logger.info("Supervisor: %s cierres sin conversacion donde avisar",
                        len(cerrados))
            return False

        MensajeSupervisor.objects.create(
            conversacion=conversacion,
            org=org,
            rol=RolMensaje.SUPERVISOR,
            contenido=redactar(cerrados),
            escrito_en=ahora or timezone.now(),
        )
        return True
    except Exception:                                            # noqa: BLE001
        #  LOS CASOS YA ESTAN CERRADOS. Que el aviso falle no puede volver
        #  atras eso ni tumbar la corrida: se registra con traza y se sigue.
        logger.exception("Supervisor: no se pudo avisar el cierre en el chat")
        return False



# =============================================================================
#  LO QUE HAY QUE DECIDIR, POR EL CHAT  --  21/10/2026
# =============================================================================
#  Pedido del usuario, al ver la propuesta del feriado en Pendientes: «seria
#  bueno que mande esas propuestas por el chat, que el supervisor escriba y no
#  solo cuando yo le pregunto algo».
#
#  A QUIEN: a quien delego «Revisar solo, una vez por hora» -- esa tarea es la
#  que hace que estas propuestas existan --, nunca a otro (mismo criterio que
#  los cierres de arriba).
#
#  A QUE CONVERSACION, Y ACA SE APARTA DE LOS CIERRES A PROPOSITO: a su
#  conversacion MAS RECIENTE, y se la marca como la ultima. El chat muestra la
#  mas reciente de cada persona; un aviso en una conversacion vieja no lo ve
#  nadie, y una decision con fecha (un feriado) que no se ve a tiempo es una
#  decision que no se toma.
#
#  SOLO LO QUE PIDE UNA DECISION CON FECHA. Todo lo demas sigue en Pendientes:
#  un aviso por cada propuesta llenaria la conversacion de ruido y empujaria
#  afuera lo que importa.

#: Los tipos de propuesta que se mandan por el chat apenas nacen.
TIPOS_QUE_SE_AVISAN = ("feriado_por_decidir",)


def redactar_decisiones(propuestas: list[dict]) -> str:
    """El mensaje. La accion y el motivo son los de la propuesta: una sola
    redaccion, la de `supervisor.analizar`, para el chat y para Pendientes."""
    lineas = ["Tengo algo para que decidas:", ""]
    for p in propuestas:
        lineas.append(f"• {p.get('accion_propuesta')}. {p.get('motivo')}")
    lineas += ["", "La propuesta está en Pendientes por revisión."]
    return "\n".join(lineas)


def _escribir_a_quien_delego(org, contenido: str, *, ahora, que: str,
                             cuantos: int) -> bool:
    """Deja `contenido` en la conversacion MAS RECIENTE de quien delego la
    revision de cada hora, y la marca como la ultima. La usan las decisiones
    y los niveles de los asuntos: una sola regla de a quien se le escribe."""
    from django.utils import timezone

    from operaciones import tareas_delegadas as td
    from operaciones.chat_modelos import (ConversacionSupervisor,
                                          MensajeSupervisor, RolMensaje)
    from operaciones.tareas_modelos import TareaDelegada

    fila = (TareaDelegada.objects
            .filter(org=org, clave=td.CICLO_AUTOMATICO, activa=True)
            .first())
    if fila is None or not fila.delegada_por_id:
        logger.info("Supervisor: %s %s sin revision delegada a quien avisar",
                    cuantos, que)
        return False
    conversacion = (ConversacionSupervisor.objects
                    .filter(org=org, actor_id=fila.delegada_por_id,
                            archivada=False)
                    .order_by("-ultimo_mensaje_en")
                    .first())
    if conversacion is None:
        logger.info("Supervisor: %s %s sin conversacion donde avisar",
                    cuantos, que)
        return False
    momento = ahora or timezone.now()
    MensajeSupervisor.objects.create(
        conversacion=conversacion,
        org=org,
        rol=RolMensaje.SUPERVISOR,
        contenido=contenido,
        escrito_en=momento,
    )
    conversacion.ultimo_mensaje_en = momento
    conversacion.save(update_fields=["ultimo_mensaje_en"])
    return True


def avisar_decisiones(org, propuestas: list[dict], *, ahora=None) -> bool:
    """Deja en el chat de quien delego la revision de cada hora lo que hay
    que decidir. Devuelve si se escribio. No levanta: las propuestas YA estan
    guardadas en Pendientes, y eso no se pierde porque el aviso falle."""
    if not propuestas:
        return False
    try:
        return _escribir_a_quien_delego(
            org, redactar_decisiones(propuestas), ahora=ahora,
            que="decisiones", cuantos=len(propuestas))
    except Exception:                                            # noqa: BLE001
        logger.exception("Supervisor: no se pudo avisar en el chat lo que "
                         "hay que decidir")
        return False


# =============================================================================
#  LOS NIVELES DE LOS ASUNTOS  --  H-21, 24/10/2026
# =============================================================================
#  Lo que el Supervisor ubico en esta vuelta: un asunto que entra por primera
#  vez, o uno que cambia de nivel. UN mensaje por vuelta, aunque sean muchos
#  (la primera vuelta ubica todos los de la empresa), con los primeros
#  TOPE_DETALLADOS y cuantos mas. Que el conteo de un asunto crezca sin
#  cambiarlo de nivel no se avisa.

#: Cuantos caracteres de un asunto entran en un renglon del aviso.
_LARGO_DEL_ASUNTO = 60


def _asunto_corto(texto) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= _LARGO_DEL_ASUNTO else t[:_LARGO_DEL_ASUNTO - 1] + "…"


def redactar_niveles(cambios: list[dict], nombres: dict) -> str:
    """El aviso de H-21. `nombres` = {codigo: nombre del nivel en la empresa}.
    Pura, para probarla sin base. NO LO ESCRIBE EL MODELO: afirma algo que ya
    se hizo, y lo que hay que decir es exactamente eso."""
    n = len(cambios)
    cabeza = ("Ubiqué 1 asunto en su nivel de respuesta:" if n == 1 else
              f"Ubiqué {n} asuntos en su nivel de respuesta:")
    lineas = [cabeza]
    #  SE NOMBRA SOLO LO QUE ES UN ASUNTO DE VERDAD (auditor independiente,
    #  25/10/2026): uno de una plantilla, o uno con 3 tickets o mas. El asunto
    #  sale del nombre del caso, y si el corte no alcanzo a sacar al cliente,
    #  un asunto de un solo ticket es justo donde quedaria su nombre -- y este
    #  mensaje lo lee el modelo en el turno siguiente.
    nombrables = [c for c in cambios
                  if c.get("de_plantilla") or (c.get("tickets") or 0) >= 3]
    sin_nombre = n - len(nombrables)
    for c in nombrables[:TOPE_DETALLADOS]:
        nivel = nombres.get(c.get("nivel"), c.get("nivel"))
        asunto = _asunto_corto(c.get("asunto"))
        motivo = str(c.get("motivo") or "")
        porque = (f"por ahora ({motivo.split(':', 1)[-1].strip()})"
                  if c.get("provisional") else f"porque {motivo}")
        if c.get("antes"):
            antes = nombres.get(c["antes"], c["antes"])
            lineas.append(f"- «{asunto}»: de {antes} a {nivel}, {porque}.")
        else:
            lineas.append(f"- «{asunto}»: {nivel}, {porque}.")
    if len(nombrables) > TOPE_DETALLADOS:
        lineas.append(f"- …y {len(nombrables) - TOPE_DETALLADOS} más.")
    if sin_nombre:
        lineas.append(
            f"- {sin_nombre} {'asunto' if sin_nombre == 1 else 'asuntos'} con "
            "pocos tickets y sin plantilla: los ves en Plantillas → Niveles de "
            "respuesta.")
    lineas += ["", "Si alguno no va ahí, se cambia en Plantillas → Niveles de "
                   "respuesta, y no lo vuelvo a tocar."]
    return "\n".join(lineas)


def avisar_niveles(org, cambios: list[dict], *, ahora=None) -> bool:
    """Cuenta en el chat lo que H-21 ubico. Devuelve si se escribio. No
    levanta: los niveles YA estan guardados."""
    if not cambios:
        return False
    try:
        from django.db import transaction

        from campo.niveles import niveles_de
        nombres = {n["codigo"]: n["nombre"] for n in niveles_de(org)}
        #  En su propio punto de guardado: H-21 avisa DENTRO de su
        #  transaccion, y un error de la base aca tiene que deshacer solo el
        #  aviso, no dejar la transaccion de afuera rota.
        with transaction.atomic():
            return _escribir_a_quien_delego(
                org, redactar_niveles(cambios, nombres), ahora=ahora,
                que="asuntos ubicados", cuantos=len(cambios))
    except Exception:                                            # noqa: BLE001
        logger.exception("Supervisor: no se pudo avisar en el chat los "
                         "niveles de los asuntos")
        return False
