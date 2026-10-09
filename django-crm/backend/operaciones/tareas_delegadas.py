# -*- coding: utf-8 -*-
"""
===============================================================================
 LO QUE UNA PERSONA LE DELEGO AL SUPERVISOR, UNA SOLA VEZ
===============================================================================

QUE RESUELVE
------------
Que alguien le diga al Supervisor, hablando normal: "todo ticket cerrado en
WispHub y abierto en Dexter, diagnosticalo y si esta todo bien cerralo" -- y a
partir de ahi lo haga siempre, sin que nadie tenga que volver a apretar nada.

EL CATALOGO ES CERRADO, Y ESA ES TODA LA DECISION
--------------------------------------------------
Habia dos formas de construir esto.

La primera: que el modelo interprete la frase y de ahi salga la accion. Mas
flexible, y con la garantia en el texto -- si alguien escribe "cerra los que
esten cerrados en WispHub" sin la parte del diagnostico, el Supervisor cerraria
casos sin mirar el equipo. Lo que hoy protege a un cliente dejaria de ser
codigo y pasaria a ser como estaba redactada una frase.

La segunda, que es esta: el modelo ENTIENDE la frase y ACTIVA una tarea que el
codigo ya sabe hacer. La persona habla igual de natural; lo que el chat decide
es cual de las tareas del catalogo encender, no que hace esa tarea. Si le piden
algo que no esta en la lista, lo dice en vez de improvisarlo.

Es la misma regla que sostiene el resto del proyecto: "el modelo compone, el
codigo calcula", y "seguridad en codigo, nunca solo en el prompt".

DELEGAR NO ES AMPLIAR EL ALCANCE
--------------------------------
Son dos cosas distintas y hacen falta las dos:

    LA TAREA     QUE se delego. La enciende una persona desde el chat.
    EL NIVEL     CUANTO puede hacer solo. Lo sube una persona desde la
                 pantalla de autonomia, con motivo y criterios medidos.

Delegar una tarea con el nivel en 1 no cierra nada, y subir el nivel sin
delegar la tarea tampoco. El Supervisor no puede hacer ninguna de las dos por
su cuenta: las dos exigen una persona, y la de autonomia lo exige ademas con
una restriccion de base.
"""
from __future__ import annotations

from django.utils import timezone

#  ===========================================================================
#   EL CATALOGO
#  ===========================================================================
#  Cada entrada es una tarea que el CODIGO ya sabe hacer, con su clave estable,
#  como nombrarla a una persona, y que exige para funcionar.
#
#  AGREGAR UNA TAREA AQUI NO LA CONSTRUYE. La entrada declara algo que ya
#  existe y esta probado; si no existe, lo que corresponde es construirlo
#  primero. Una clave sin implementacion seria una promesa que el chat podria
#  aceptar y el ciclo no cumpliria.
CERRAR_DESINCRONIZADOS = "cerrar_desincronizados_con_diagnostico"
CICLO_AUTOMATICO = "revisar_solo_con_cada_actualizacion"

CATALOGO = {
    CERRAR_DESINCRONIZADOS: {
        "nombre": "Cerrar los casos ya cerrados en WispHub, con diagnóstico",
        "que_hace": (
            "Por cada caso que figura cerrado en WispHub y abierto en Dexter, "
            "le pregunta a SmartOLT por el equipo del cliente. Lo cierra solo "
            "si el equipo está en línea con señal buena, o caído por falta de "
            "energía en el domicilio. Si la señal está débil o la caída es por "
            "fibra, lo deja para que lo mire una persona."),
        "que_no_hace": (
            "No toca WispHub, no reabre nada, y no cierra ningún caso cuyo "
            "equipo no haya podido diagnosticar."),
        "exige_nivel": 3,
    },
    CICLO_AUTOMATICO: {
        "nombre": "Revisar solo, una vez por hora",
        "que_hace": (
            "Una vez por hora el Supervisor revisa la operación por su "
            "cuenta: detecta lo que cambió, deja las propuestas que "
            "correspondan, y ejecuta las tareas que ya estén delegadas. Sin "
            "que nadie apriete nada. Cada hora y no más seguido porque los "
            "tickets del proveedor también llegan cada hora: mirar más "
            "seguido sería preguntar cuatro veces por el mismo dato."),
        "que_no_hace": (
            "No habilita ninguna acción por sí misma. Solo hace que el "
            "Supervisor mire cada tanto en vez de esperar a que alguien lo "
            "despierte: lo que puede hacer al mirar sigue siendo lo que esté "
            "delegado aparte, con su propio nivel de autonomía."),
        #  NO EXIGE NIVEL, y la diferencia importa: mirar no es ejecutar. Si
        #  no hay ninguna tarea de accion delegada, esto solo produce
        #  propuestas para que las lea una persona -- que es lo que el
        #  Supervisor ya hacia cuando alguien apretaba el boton.
        "exige_nivel": 0,
    },
}


def catalogo_legible() -> list[dict]:
    """El catálogo con su clave, para que el chat lo muestre y lo nombre."""
    return [{"clave": c, **datos} for c, datos in CATALOGO.items()]


def esta_delegada(org, clave: str) -> bool:
    """
    Si esta tarea esta delegada y vigente para esta empresa.

    FALLA CERRADO: una clave que no esta en el catalogo devuelve False, no
    levanta. El ciclo pregunta esto antes de actuar, y una excepcion ahi
    tumbaria una corrida entera por una clave vieja en la base.
    """
    from operaciones.tareas_modelos import TareaDelegada

    if clave not in CATALOGO:
        return False
    return TareaDelegada.objects.filter(
        org=org, clave=clave, activa=True).exists()


def delegadas(org) -> list[dict]:
    """Las tareas vigentes de esta empresa, con quién y cuándo las delegó."""
    from operaciones.tareas_modelos import TareaDelegada

    filas = (TareaDelegada.objects
             .filter(org=org, activa=True)
             .select_related("delegada_por")
             .order_by("-delegada_en"))
    return [{
        "clave": f.clave,
        "nombre": CATALOGO.get(f.clave, {}).get("nombre", f.clave),
        "delegada_en": f.delegada_en.isoformat(),
        #  El ID y nunca el nombre ni el correo: esto puede terminar en un log.
        "delegada_por": str(f.delegada_por_id or ""),
        "con_estas_palabras": f.pedido_textual,
    } for f in filas]


class ErrorTarea(Exception):
    """No se pudo delegar o quitar. El mensaje lo lee una persona."""


def delegar(org, clave: str, *, actor, pedido_textual: str = "",
            conversacion_id=None, ahora=None):
    """
    Deja delegada una tarea del catálogo. Exige persona.

    'pedido_textual' es la frase con la que se pidió, guardada tal cual. No se
    usa para decidir nada -- lo que se ejecuta es la tarea del catálogo-- pero
    es lo que permite, meses después, saber qué creía estar pidiendo quien la
    delegó. Si la tarea hace algo distinto de lo que esa frase dice, el
    problema es del catálogo y conviene poder verlo.
    """
    from operaciones.tareas_modelos import TareaDelegada

    if clave not in CATALOGO:
        raise ErrorTarea(
            f"'{clave}' no es una tarea que el sistema sepa hacer. Las que hay: "
            f"{', '.join(CATALOGO)}")
    if actor is None:
        raise ErrorTarea(
            "delegar una tarea necesita la persona que la delega: el "
            "Supervisor no puede darse trabajo a sí mismo")

    ahora = ahora or timezone.now()
    fila, creada = TareaDelegada.objects.get_or_create(
        org=org, clave=clave,
        defaults={"activa": True, "delegada_por": actor,
                  "pedido_textual": (pedido_textual or "")[:500],
                  "conversacion_id": conversacion_id,
                  "delegada_en": ahora})
    if not creada:
        #  Volver a delegar una que ya estaba es REACTIVARLA, y queda a nombre
        #  de quien lo pidió esta vez. Lo contrario --dejar el actor viejo--
        #  haría que la auditoría culpara a quien la delegó hace meses.
        fila.activa = True
        fila.delegada_por = actor
        fila.delegada_en = ahora
        if pedido_textual:
            fila.pedido_textual = pedido_textual[:500]
        #  LA CONVERSACION SE MUEVE A LA ULTIMA, igual que el actor: el aviso
        #  tiene que llegar donde se pidio esta vez, no donde se pidio hace
        #  meses. Y solo si viene una: volver a delegar desde fuera del chat
        #  no deberia dejar la tarea sin donde avisar.
        if conversacion_id:
            fila.conversacion_id = conversacion_id
        fila.save(update_fields=["activa", "delegada_por", "delegada_en",
                                 "pedido_textual", "conversacion_id",
                                 "updated_at"])
    return fila


def quitar(org, clave: str, *, actor, ahora=None):
    """
    Deja de delegar una tarea. NO la borra: queda el registro de que existió.

    Borrarla haría imposible contestar "¿esto estuvo delegado alguna vez?", que
    es justo la pregunta que alguien va a hacer el día que un caso aparezca
    cerrado y nadie recuerde por qué.
    """
    from operaciones.tareas_modelos import TareaDelegada

    if actor is None:
        raise ErrorTarea("quitar una tarea necesita la persona que lo decide")
    fila = TareaDelegada.objects.filter(org=org, clave=clave).first()
    if fila is None:
        raise ErrorTarea(f"'{clave}' no estaba delegada")
    fila.activa = False
    fila.quitada_por = actor
    fila.quitada_en = ahora or timezone.now()
    fila.save(update_fields=["activa", "quitada_por", "quitada_en",
                             "updated_at"])
    return fila
