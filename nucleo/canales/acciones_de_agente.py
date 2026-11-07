# -*- coding: utf-8 -*-
"""
QUE PUEDE HACER HOY UN AGENTE, Y QUE NO.

Esta pregunta parece tener una respuesta facil --la lista blanca del rol,
`Rol.puede_consultar`-- y esa respuesta es FALSA. La lista blanca es UNO de los
ocho pasos de la frontera de autorizacion: pasarla no habilita nada, solo deja
de bloquear. Una herramienta que esta en la lista puede ser hoy imposible
porque el interruptor de autonomia esta detenido, o porque exige un nivel por
encima del techo que la empresa tiene fijado.

Mostrar la lista blanca como «acciones permitidas» seria exactamente el error
que este proyecto no comete: afirmar una capacidad que el backend no da.

ASI QUE AQUI SE CRUZA. Para cada herramienta del rol:

    nivel que EXIGE   (techo.nivel_requerido_de, del catalogo de la empresa)
    techo VIGENTE     (techo.leer, de la base, sin cache)
    interruptor       (interruptor.veredicto, de la base, sin cache)

y se devuelve `disponible` con su `motivo` cuando no lo esta. Un nivel que no
se puede leer NO se asume: sale `disponible: false` con el motivo que dio el
bloqueo. Es la misma regla fail-closed de la frontera -- si no se sabe, no se
promete.

LO QUE ESTO NO ES. No es un permiso ni se parece a uno: no autoriza nada, no
viaja a ningun ejecutor y nadie decide nada mirandolo. Es una DESCRIPCION, y la
unica garantia sigue estando donde estuvo siempre, en `frontera.exigir()`.
Dos consecuencias que importan:

  · Que una accion salga `disponible: true` NO significa que vaya a ejecutarse
    sin mas. Las irreversibles exigen ademas una aprobacion humana atada, y eso
    se dice por separado (`requiere_aprobacion`) en vez de esconderse dentro de
    un booleano.

  · Esto se calcula con el tenant que el servidor resolvio de la sesion. No
    recibe ningun identificador del navegador, por el mismo motivo que el resto:
    que el cliente pudiera elegir la empresa convertiria esto en un visor de la
    configuracion ajena.

QUE DATO SALE. Nombres de herramienta y su descripcion -- la misma informacion
que `/agentes` ya sirve a cualquier usuario de la empresa desde que existe esa
pantalla. Ningun campo de cliente, ninguna credencial, ningun argumento.
"""
from __future__ import annotations

from nucleo.modelo import motor
from nucleo.seguridad import interruptor, techo


def _clase(herramienta) -> str:
    """
    Mirar, hacer, o hacer algo que no se puede deshacer.

    Son tres y no dos a proposito. `agendar_visita_tecnica` crea una visita con
    costo y logistica, y `reiniciar_ont` corta el servicio de una casa: en una
    lista plana las dos se ven igual que una consulta, que es justo lo que
    hacia falta separar.
    """
    if getattr(herramienta, "irreversible", False):
        return "irreversible"
    if getattr(herramienta, "solo_lectura", True):
        return "consulta"
    return "efecto"


def acciones_de(config, rol) -> list[dict]:
    """
    Las herramientas de un rol, clasificadas. SIN tocar la base.

    Se separa de `estado_de_autonomia` porque son dos lecturas de naturaleza
    distinta: esto es configuracion de la empresa y no cambia entre dos
    agentes; aquello es estado operativo y se lee UNA vez para todos.
    """
    #  La resolucion lista-blanca -> catalogo la hace `herramientas_del_rol`,
    #  que es la MISMA que usa el motor para armar las herramientas del turno.
    #  Reimplementarla aqui seria una segunda verdad sobre que puede llamar un
    #  rol, y el dia que se separen esta pantalla describiria a un agente que
    #  no existe.
    salida = []
    for h in motor.herramientas_del_rol(config, rol):
        salida.append({
            "nombre": h.nombre,
            "descripcion": (getattr(h, "descripcion", "") or "").strip(),
            "clase": _clase(h),
            "nivel_requerido": techo.nivel_requerido_de(h),
            #  Por separado y no dentro de `disponible`: una irreversible
            #  disponible sigue necesitando que una persona la apruebe, y
            #  meterlo en un booleano lo haria desaparecer.
            "requiere_aprobacion": bool(getattr(h, "irreversible", False)),
        })
    return sorted(salida, key=lambda a: (a["clase"] != "consulta", a["nombre"]))


def estado_de_autonomia(tenant: str) -> dict:
    """
    El techo y el interruptor de la empresa, ahora. Fail-closed.

    Las dos lecturas van a la base a proposito y sin cache: es el mismo criterio
    por el que el interruptor NO vive en `tenant_config` (CLAUDE.md §8). Una
    copia cacheada podria decir «activo» con la empresa detenida, y esta
    pantalla estaria afirmando que un agente puede hacer algo que el backend ya
    no deja hacer.
    """
    nivel, bloqueo = techo.leer(tenant)
    v = interruptor.veredicto(tenant)
    #  `permitido`, no `permite`. Escribirlo mal con un `getattr(..., False)`
    #  dejaba `detenido` en True SIEMPRE, con la empresa activa: fail-closed
    #  escondia el defecto en vez de delatarlo, y la ficha habria dicho
    #  «autonomia detenida» para siempre sin que nada fallara. Lo caza la
    #  prueba que mira el estado en las DOS posiciones del interruptor.
    detenido = not v.permitido
    return {
        "techo": nivel,
        "techo_nombre": techo.NOMBRES.get(nivel) if nivel is not None else None,
        "techo_motivo": getattr(bloqueo, "motivo", None) if bloqueo else None,
        "detenido": detenido,
        "detenido_motivo": (getattr(v, "motivo", "") or "").strip() if detenido else None,
    }


def disponibilidad(accion: dict, estado: dict) -> dict:
    """
    La misma accion, con `disponible` y su `motivo`.

    UNA CONSULTA NO LA GOBIERNAN NI EL INTERRUPTOR NI EL TECHO, y darlo por
    sentado fue el primer error de este archivo: la primera version marcaba
    «no disponible: la autonomia esta detenida» las ocho consultas de cada
    agente. Es falso, y lo dice el propio interruptor:

        'es_accion_autonoma': escribe -> 'solo_lectura=False'. Una consulta no
        es una accion: detener la autonomia no puede dejar ciego al que
        atiende.

    El techo corre dentro de `frontera.exigir()`, por donde una lectura no
    pasa. Asi que una consulta esta disponible mientras este en la lista blanca
    del rol, y eso es todo.

    PARA LAS QUE SI ESCRIBEN, EL ORDEN ES EL DE LA FRONTERA: primero el
    interruptor, despues el techo. Al reves, una empresa detenida con techo
    alto diria «el techo no alcanza» y mandaria a quien lo lea a subir un
    numero que no es el problema.
    """
    if accion["clase"] == "consulta":
        return {**accion, "disponible": True, "motivo": None}

    if estado.get("detenido"):
        detalle = estado.get("detenido_motivo")
        return {**accion, "disponible": False,
                "motivo": "la autonomia de la empresa esta detenida"
                          + (f": {detalle}" if detalle else "")}

    techo_vigente = estado.get("techo")
    if techo_vigente is None:
        #  No se pudo leer. NO se asume un nivel: es la misma regla fail-closed
        #  por la que la frontera bloquea cuando no puede comprobar.
        return {**accion, "disponible": False,
                "motivo": estado.get("techo_motivo")
                          or "no se pudo leer el techo de autonomia de la empresa"}

    if accion["nivel_requerido"] > techo_vigente:
        tiene = techo.NOMBRES.get(techo_vigente, str(techo_vigente))
        exige = techo.NOMBRES.get(accion["nivel_requerido"], str(accion["nivel_requerido"]))
        return {**accion, "disponible": False,
                "motivo": f"exige nivel «{exige}» y el techo de la empresa es «{tiene}»"}

    return {**accion, "disponible": True, "motivo": None}
