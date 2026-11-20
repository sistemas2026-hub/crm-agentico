# -*- coding: utf-8 -*-
"""
================================================================================
 LA FICHA DEL CLIENTE SEGUN QUIEN MIRA  -  filtro fail-closed (12/11/2026)
================================================================================

POR QUE EXISTE
--------------
La auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md, §1 punto 6) encontro
el mismo hueco tres veces: la ficha del titular de un servicio -- cedula,
direccion, telefono, correo, saldo -- la veia CUALQUIER rol, en la Bandeja y en
el detalle del ticket, mientras el importador ya habia decidido para el tablero
del Supervisor que «su cedula no» (nucleo/seguimiento/importacion_io.py). Dos
criterios para el mismo dato, y ninguno en un solo lugar.

Este modulo es ese lugar. Las listas blancas por rol de agente
(listas_blancas.py) deciden que ve el MODELO; esto decide que ve una PERSONA del
equipo en una pantalla. Son preguntas distintas y no se mezclan: ampliar una no
amplia la otra.

EL CRITERIO, ENTERO
-------------------
  1. Roles de gestion del CRM (ADMIN, SUPERVISOR, OPERACIONES): la ficha
     entera. Deciden sobre el caso completo -- reparten, validan, cierran -- y
     es el mismo conjunto que ROLES_GESTION del backend (campo/permissions.py).
  2. Cualquier otro rol: lo que declare SU AREA de trabajo
     ('AreaDeTrabajo.ficha_cliente' en la configuracion de la empresa). El area
     sale de 'asistente.area_colaborador' por el id de perfil, la lee el motor:
     no se acepta de quien llama.
  3. Si el area no se puede resolver -- sin perfil, sin area, area que la
     configuracion ya no declara, la base no contesta -- o el area no declaro
     nada: el DEFECTO SEGURO de abajo.

Un campo fuera del catalogo (schema.CAMPOS_FICHA_DEL_CLIENTE) no se entrega a
nadie, ni a gestion: fail-closed ante un campo nuevo que nadie clasifico.

EL DEFECTO, Y POR QUE ESE
-------------------------
Todo el catalogo MENOS cedula, correo y coordenadas.

  - cedula: es la llave de identidad del titular (en el ISP y fuera de el), la
    que el asistente usa para verificar a quien le escribe. Quien atiende ya ve
    si la identidad quedo verificada; leer el numero no le agrega nada para
    atender y si lo expone. Es lo mismo que decidio el importador.
  - correo: ninguna pantalla lo usa para atender (la Bandeja no lo dibuja).
  - coordenadas: el punto exacto del domicilio. La direccion alcanza para
    ubicar el caso; el GPS lo necesita quien va, y ese lo lleva la orden de
    campo, no esta ficha.
  - telefono y direccion SE QUEDAN: el 10/09/2026 se decidio explicitamente
    que quien atiende un ticket tiene que poder llamar al cliente y saber a
    donde ir sin salir a otro sistema (api.py, comentario de '_CAMPOS_FICHA').
    Ocultarlos por defecto rompe ese trabajo el dia del despliegue en una
    empresa que todavia no configuro sus areas. El numero del chat, ademas, ya
    esta a la vista de quien atiende la conversacion.
  - saldo, estado, plan, fecha de corte: lo que hace falta para contestar
    "¿por que no tengo internet?" (PRD §3: Soporte necesita estado, plan,
    facturas, saldo, fecha de corte).

QUE GARANTIZA Y QUE NO
----------------------
El motor autentica al SERVICIO que lo llama (X-Servicio-Token), no a la persona.
El rol del CRM lo manda la capa servidor del frontend, que lo saca del JWT que
verifico en hooks.server.js; el navegador nunca habla con el motor. Entonces:

  GARANTIZA: sin rol o con un rol desconocido, no hay ficha entera; el area no
  la elige quien llama (sale de la base del motor por el perfil); un perfil sin
  area, o una falla al leerla, cae al defecto y no a "todo".
  NO GARANTIZA: que el rol que llega sea el verdadero. Quien tenga el token de
  servicio puede declararse ADMIN. Eso es lo mismo que ya pasa con 'profile_id'
  en /chat, y el limite real es que ese token solo lo tiene el servidor.
================================================================================
"""

from __future__ import annotations

from nucleo.config.schema import CAMPOS_FICHA_DEL_CLIENTE

#  Los roles del CRM que deciden sobre el caso completo. Vocabulario del
#  producto (common/utils.py::ROLES), igual para todas las empresas.
ROLES_GESTION: frozenset[str] = frozenset({"ADMIN", "SUPERVISOR", "OPERACIONES"})

#  Lo que NO entra en el defecto. Se declara lo que sale, no lo que entra: un
#  campo nuevo del catalogo que nadie miro queda en el defecto solo si alguien
#  lo agrega al catalogo, que es donde se lo clasifica.
FUERA_DEL_DEFECTO: frozenset[str] = frozenset({"cedula", "email", "coordenadas"})

DEFECTO_COLABORADOR: frozenset[str] = frozenset(
    c for c in CAMPOS_FICHA_DEL_CLIENTE if c not in FUERA_DEL_DEFECTO)

#  Claves con las que la MISMA informacion llega por otro camino. El detalle del
#  ticket recibe el plan como 'plan' (el nombre) y 'plan_id'; la Bandeja como
#  'plan_internet'. Es un dato y se decide una vez.
ALIAS: dict[str, str] = {"plan": "plan_internet", "plan_id": "plan_internet"}

#  La clave con la que una ficha filtrada dice que se le saco. Con guion bajo
#  para que nunca se confunda con un campo del sistema del ISP.
CLAVE_OCULTOS = "_ocultos"


def campos_visibles(config, rol_crm: str | None, area: str | None) -> tuple[frozenset[str], str]:
    """
    Los campos del catalogo que puede ver quien mira, y por que criterio.

    Pura: no lee la base. 'area' es el nombre interno del area de la persona
    (ya resuelto, o None si no se pudo). Devuelve (visibles, criterio) con
    criterio en 'gestion' | 'area' | 'defecto'. El criterio es para el
    diagnostico de la pantalla, nunca para decidir.
    """
    if str(rol_crm or "").strip().upper() in ROLES_GESTION:
        return frozenset(CAMPOS_FICHA_DEL_CLIENTE), "gestion"
    if area:
        declarada = next((a for a in (getattr(config, "areas", None) or [])
                          if a.nombre == area), None)
        if declarada is not None and declarada.ficha_cliente is not None:
            return (frozenset(c for c in declarada.ficha_cliente
                              if c in CAMPOS_FICHA_DEL_CLIENTE), "area")
    return DEFECTO_COLABORADOR, "defecto"


def claves_visibles(visibles) -> frozenset[str]:
    """Los nombres de clave que se entregan: los campos visibles mas sus alias."""
    visibles = frozenset(visibles)
    return visibles | {alias for alias, base in ALIAS.items() if base in visibles}


def ocultos(visibles) -> list[str]:
    """Los campos del catalogo que quien mira NO ve, en el orden del catalogo.

    Se dicen todos, haya o no valor: «oculto» no puede revelar que el cliente
    tiene cargado un correo que la persona no puede leer."""
    visibles = frozenset(visibles)
    return [c for c in CAMPOS_FICHA_DEL_CLIENTE if c not in visibles]


def filtrar_ficha(ficha, visibles) -> dict:
    """
    La ficha con solo lo que quien mira puede ver, mas '_ocultos'.

    Cualquier clave que no sea un campo visible (o su alias) se cae: tambien
    las que nadie clasifico. Una ficha que no es un diccionario devuelve
    diccionario vacio -- nunca la entrada tal cual.
    """
    if not isinstance(ficha, dict):
        return {}
    permitidas = claves_visibles(visibles)
    salida = {k: v for k, v in ficha.items() if k in permitidas}
    salida[CLAVE_OCULTOS] = ocultos(visibles)
    return salida


def area_de(tenant: str, profile_id: str | None) -> str | None:
    """
    El area de trabajo de un perfil, leida de la base del motor. None si no
    tiene, si no vino perfil o si la base no contesta: quien llama cae al
    defecto, nunca a la ficha entera.
    """
    if not str(profile_id or "").strip():
        return None
    try:
        from nucleo.persistencia import db as persistencia
        return persistencia.areas_de_colaboradores(tenant).get(str(profile_id).strip())
    #  SystemExit TAMBIEN (CLAUDE.md §13, D11): la capa de conexion lo lanza
    #  sin credenciales de base, y no hereda de Exception. Sin esto, "no se
    #  pudo resolver el area" mataria el proceso en vez de caer al defecto.
    except (Exception, SystemExit) as e:                    # noqa: BLE001
        from nucleo.observabilidad.registro import registrar
        registrar("ficha", "no se pudo resolver el area de quien mira", error=e)
        return None


def visibilidad_para(config, tenant: str, rol_crm: str | None,
                     profile_id: str | None) -> dict:
    """
    LA FUNCION QUE SE REUSA: que ve de la ficha esta persona.

    {"campos": [claves que se entregan, con alias], "visibles": [campos],
     "ocultos": [campos], "criterio": 'gestion'|'area'|'defecto'}

    Lo de gestion no consulta la base: no la necesita para decidir.
    """
    if str(rol_crm or "").strip().upper() in ROLES_GESTION:
        visibles, criterio = campos_visibles(config, rol_crm, None)
    else:
        visibles, criterio = campos_visibles(config, rol_crm, area_de(tenant, profile_id))
    return {"campos": sorted(claves_visibles(visibles)),
            "visibles": [c for c in CAMPOS_FICHA_DEL_CLIENTE if c in visibles],
            "ocultos": ocultos(visibles),
            "criterio": criterio}


def ficha_para(config, tenant: str, rol_crm: str | None, profile_id: str | None,
               ficha) -> dict:
    """Atajo: la ficha ya filtrada para quien mira (ver visibilidad_para)."""
    v = visibilidad_para(config, tenant, rol_crm, profile_id)
    return filtrar_ficha(ficha, v["visibles"])
