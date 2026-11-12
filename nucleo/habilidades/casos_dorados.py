# -*- coding: utf-8 -*-
"""
================================================================================
 CASO DORADO DESDE UNA CONVERSACION REAL  --  lo marcado llega a la evaluacion
================================================================================

El problema que resuelve (12/11/2026)
-------------------------------------
El equipo marca respuestas como «☆ Buen ejemplo» (asistente.ejemplos_validados)
y aprueba revisiones del supervisor (asistente.revisiones_supervisor). Hasta
hoy ninguna de las dos cosas tenia efecto: el unico lector de los ejemplos era
la consulta que pinta /manual, y 'estado = aprobado' no lo leia nadie
(SPEC/AUDITORIA_MENU_2026-11-12.md, grupo «Dexter»). El trabajo humano de
marcar se tiraba.

Lo que ya existia y no se usaba: la TRAZA del turno se persiste entera
(asistente.tool_calls, ver nucleo/canales/api.py::_guardar_traza) -- que
herramientas se llamaron, cuales fallaron, a que area se derivo. Es justo lo
que afirma un caso dorado (evaluacion/<slug>.casos.yaml): hechos de la traza,
nunca la redaccion. Este modulo traduce una cosa en la otra.

Que afirma el caso que sale de aca, y que no
--------------------------------------------
- 'mensajes': lo que escribio el CLIENTE, solo texto, REDACTADO por patron
  (nucleo/seguridad/redaccion.py). Un caso dorado va al repositorio: un
  telefono o una cedula no pueden llegar ahi. La redaccion por patron NO tapa
  nombres propios ni direcciones -- por eso el caso nace con un aviso y con
  'manual: true' (abajo).
- 'deriva_a': la ultima derivacion EFECTIVA de la traza. Se reconoce por la
  CONFIGURACION (Herramienta.deriva_rol), no por un nombre de herramienta: el
  nucleo no sabe como llama cada empresa a su herramienta de derivar.
- 'usa': las herramientas que CORRIERON (exito, no bloqueo), sin repetir.
- 'sin_errores': solo si la traza no tuvo ningun error que no fuera un
  bloqueo. Una conversacion buena con un error de herramienta no puede
  generar un caso que exija lo que no paso.

Lo que NO afirma: 'no_usa', 'responde_sin', 'escala'. Son afirmaciones sobre
lo que NO debia pasar, y eso no se deduce de una traza que salio bien: lo
agrega la persona que revisa el caso (ver la cabecera de
evaluacion/rapilink.casos.yaml, «afirmar que algo ocurrio, no que sirvio»).

Nace 'manual: true', a proposito
--------------------------------
cli/evaluar.py saltea los casos 'manual' en la corrida completa y los corre
nombrandolos con --caso. Un caso de una conversacion real corre con la sesion
de laboratorio ('sesion_por_defecto'), no con la del cliente: puede fallar por
datos y no por codigo. Un rojo permanente entrena a ignorar el rojo (la misma
leccion que la cabecera de evaluar.py cuenta de los casos con precondicion
manual). Una persona lo lee, lo ajusta y le saca la marca.

Es generico: ningun rol, herramienta, area ni empresa aparece aca.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timezone

import yaml

from nucleo.canales.canal import REALES, WHATSAPP_SIMULADO
from nucleo.persistencia.db import sesion
from nucleo.seguridad import redaccion

# Canales cuyo turno atiende el rol de ENTRADA (el de cliente final). Un caso
# del asistente interno ('api') se atiende con el rol del colaborador, que una
# conversacion no guarda: no hay con que armar el caso sin adivinar.
CANALES_DE_CLIENTE = frozenset(REALES | {WHATSAPP_SIMULADO})

# Cuantos mensajes del cliente entran en un caso. Cada mensaje es un turno del
# modelo cuando se corre (~20-60 s y su costo): una conversacion de treinta
# mensajes no es un caso, es una corrida. Si se recorta, la traza se recorta
# con los mismos turnos, y el caso lo dice.
MAXIMO_MENSAJES = 8


class SinCaso(Exception):
    """No hay con que armar un caso: el origen no existe, no es de un cliente o
    no tiene mensajes del cliente. El mensaje es apto para la pantalla."""


def rol_de_entrada(config) -> str | None:
    """El rol que recibe el primer mensaje de un cliente.

    Mismo criterio que nucleo/canales/api.py::_rol_de_cliente: lo dice
    'rol_de_entrada'; sin el, el primer rol orientado a cliente final.
    """
    if getattr(config, "rol_de_entrada", None):
        return config.rol_de_entrada
    for nombre, rol in (config.roles or {}).items():
        if rol.orientado_a == "cliente_final":
            return nombre
    return None


# --------------------------------------------------------------------------
#  Lectura de la conversacion -- una sola ida a la base
# --------------------------------------------------------------------------

def _leer(cur, org, conversation_id: str, hasta_mensaje_id: str | None) -> dict:
    """La conversacion acotada: mensajes del cliente y traza hasta el turno de
    'hasta_mensaje_id' (incluido), o entera si es None.

    La traza de un turno se escribe DESPUES de la respuesta (en un hilo, ver
    api.py::_guardar_traza), asi que su 'creado_en' es posterior al mensaje
    del agente. El corte del turno N no es la respuesta N sino el mensaje
    SIGUIENTE del cliente: todo lo anterior a ese mensaje es de los turnos
    1..N.
    """
    cur.execute(
        """select id::text, canal, rol_efectivo, escalada_a_humano, creado_en
             from asistente.conversations
            where organization_id = %s and id = %s""", (org, conversation_id))
    conv = cur.fetchone()
    if not conv:
        raise SinCaso("La conversacion no existe.")

    corte = None
    if hasta_mensaje_id:
        cur.execute(
            """select creado_en from asistente.messages
                where organization_id = %s and conversation_id = %s and id = %s""",
            (org, conversation_id, hasta_mensaje_id))
        marcado = cur.fetchone()
        if not marcado:
            raise SinCaso("El mensaje marcado ya no esta en la conversacion.")
        cur.execute(
            """select min(creado_en) as siguiente from asistente.messages
                where organization_id = %s and conversation_id = %s
                  and rol = 'user' and creado_en > %s""",
            (org, conversation_id, marcado["creado_en"]))
        corte = (cur.fetchone() or {}).get("siguiente")
        hasta = marcado["creado_en"]
    else:
        hasta = None

    # Solo TEXTO del cliente: un audio o una foto se guardan con su
    # transcripcion o descripcion como contenido, y reenviar eso como si el
    # cliente lo hubiera escrito no prueba lo mismo.
    cur.execute(
        """select m.contenido, m.creado_en
             from asistente.messages m
            where m.organization_id = %s and m.conversation_id = %s
              and m.rol = 'user'
              and coalesce(btrim(m.contenido), '') <> ''
              and (%s::timestamptz is null or m.creado_en <= %s)
              and not exists (select 1 from asistente.media x
                               where x.mensaje_id = m.id)
            order by m.creado_en, m.id""",
        (org, conversation_id, hasta, hasta))
    mensajes = [dict(f) for f in cur.fetchall()]

    cur.execute(
        """select herramienta, parametros, exito, codigo_error, es_bloqueo,
                  creado_en
             from asistente.tool_calls
            where organization_id = %s and conversation_id = %s
              and (%s::timestamptz is null or creado_en < %s)
            order by creado_en, id""",
        (org, conversation_id, corte, corte))
    llamadas = [dict(f) for f in cur.fetchall()]
    return {"conversacion": dict(conv), "mensajes": mensajes, "llamadas": llamadas}


# --------------------------------------------------------------------------
#  Armado del caso -- puro, sin base: lo que se prueba sin Postgres
# --------------------------------------------------------------------------

def armar_caso(config, datos: dict, *, origen: str, caso_manual: str | None,
               descripcion: str) -> tuple[dict, list[str]]:
    """El caso dorado y los avisos para quien lo revisa.

    'datos' es lo que devuelve _leer. 'origen' identifica de donde salio
    ('ejemplo:<id>' o 'revision:<id>') y es la clave con la que el importador
    no duplica.
    """
    conv = datos["conversacion"]
    if conv.get("canal") not in CANALES_DE_CLIENTE:
        raise SinCaso("Solo una conversacion con un cliente (WhatsApp o el "
                      "simulador) se puede convertir en caso dorado.")
    rol = rol_de_entrada(config)
    if not rol:
        raise SinCaso("La configuracion no tiene un rol que atienda clientes.")

    avisos: list[str] = []
    mensajes = datos["mensajes"]
    if not mensajes:
        raise SinCaso("La conversacion no tiene mensajes de texto del cliente.")
    llamadas = datos["llamadas"]
    if len(mensajes) > MAXIMO_MENSAJES:
        # La traza se corta en el mismo turno: lo que paso despues del ultimo
        # mensaje que entra no puede afirmarse de un caso que no lo manda.
        siguiente = mensajes[MAXIMO_MENSAJES]["creado_en"]
        llamadas = [l for l in llamadas if l["creado_en"] < siguiente]
        mensajes = mensajes[:MAXIMO_MENSAJES]
        avisos.append(f"La conversacion tenia mas de {MAXIMO_MENSAJES} mensajes "
                      f"del cliente: el caso usa los primeros {MAXIMO_MENSAJES} "
                      "y la traza de esos turnos.")

    derivadoras = {h.nombre for h in (config.herramientas or [])
                   if getattr(h, "deriva_rol", False)}
    usa: list[str] = []
    errores: list[str] = []
    actual, deriva_a = rol, None
    for l in llamadas:
        if l.get("es_bloqueo"):
            continue
        if not l.get("exito"):
            errores.append(f"{l['herramienta']}: {l.get('codigo_error') or 'error'}")
            continue
        if l["herramienta"] not in usa:
            usa.append(l["herramienta"])
        if l["herramienta"] in derivadoras:
            area = (l.get("parametros") or {}).get("area")
            # Una auto-derivacion (al area que ya atiende) no cambia nada:
            # el motor no fija 'rol_siguiente' y cli/evaluar.py no la ve.
            if isinstance(area, str) and area and area != actual:
                actual = deriva_a = area

    espera: dict = {}
    if deriva_a:
        espera["deriva_a"] = deriva_a
    if usa:
        espera["usa"] = usa
    if errores:
        avisos.append("La traza tuvo errores de herramienta (" + "; ".join(errores[:3])
                      + "): el caso no afirma 'sin_errores'.")
    else:
        espera["sin_errores"] = True
    if not usa and not deriva_a:
        avisos.append("La conversacion no llamo a ninguna herramienta: el caso "
                      "solo afirma que no hubo errores. Agregale lo que no debe "
                      "pasar ('no_usa', 'responde_sin').")
    if conv.get("canal") not in REALES:
        avisos.append("La conversacion es del simulador, no de un cliente real.")

    caso = {
        "nombre": descripcion,
        "origen": origen,
        "manual": True,
        "rol": rol,
        "mensajes": [redaccion.redactar(m["contenido"]) for m in mensajes],
        "espera": espera,
    }
    if caso_manual:
        caso["caso_manual"] = caso_manual
    return caso, avisos


def a_yaml(caso: dict, avisos: list[str]) -> str:
    """El caso como item de la lista 'casos:', listo para pegar al final del
    archivo (indentado a dos espacios, como los que ya estan).

    La cabecera es comentario: no cambia lo que carga cli/evaluar.py, y le
    dice a quien lo pega lo que la maquina no puede garantizar.
    """
    hoy = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    cabecera = [
        f"Generado el {hoy} desde una conversacion ({caso['origen']}).",
        "Afirma la TRAZA que se guardo, nunca la redaccion. Los mensajes pasaron",
        "por la redaccion por patron (numeros, correos, enlaces, coordenadas):",
        "un NOMBRE o una DIRECCION no se tapan solos -- leelos antes de commitear.",
        "Nace 'manual: true': no entra en la corrida automatica hasta que una",
        "persona lo revise, le agregue lo que NO debe pasar y le saque la marca.",
    ] + [f"AVISO: {a}" for a in avisos]
    cuerpo = yaml.safe_dump([caso], allow_unicode=True, sort_keys=False,
                            default_flow_style=None, width=88)
    lineas = ["  # " + c for c in cabecera]
    lineas += ["  " + l if l else l for l in cuerpo.rstrip("\n").split("\n")]
    return "\n".join(lineas) + "\n"


# --------------------------------------------------------------------------
#  Desde un ejemplo marcado o una revision
# --------------------------------------------------------------------------

def caso_de_ejemplo(config, tenant: str, ejemplo_id: str) -> tuple[dict, list[str]]:
    """El caso de un «☆ Buen ejemplo»: la conversacion hasta ese turno."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id::text, conversation_id::text, mensaje_id::text, caso
                 from asistente.ejemplos_validados
                where organization_id = %s and id = %s""", (org, ejemplo_id))
        ej = cur.fetchone()
        if not ej:
            raise SinCaso("Ese ejemplo no existe.")
        datos = _leer(cur, org, ej["conversation_id"], ej["mensaje_id"])
    return armar_caso(
        config, datos, origen=f"ejemplo:{ej['id']}", caso_manual=ej["caso"],
        descripcion=f"desde conversacion real: {ej['caso']} (ejemplo {ej['id'][:8]})")


def caso_de_revision(config, tenant: str, revision_id: str) -> tuple[dict, list[str]]:
    """El caso de una revision del supervisor: la conversacion entera.

    Solo de una revision que dice BUEN ejemplo. Una con problemas no tiene una
    traza que valga como lo que deberia pasar: generar un caso de ella fijaria
    el error como esperado.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id::text, conversation_id::text, caso, es_buen_ejemplo
                 from asistente.revisiones_supervisor
                where organization_id = %s and id = %s""", (org, revision_id))
        rev = cur.fetchone()
        if not rev:
            raise SinCaso("Esa revision no existe.")
        if not rev["es_buen_ejemplo"]:
            raise SinCaso("La revision dice que la conversacion tuvo problemas: "
                          "su traza no es lo que deberia pasar.")
        datos = _leer(cur, org, rev["conversation_id"], None)
    nombre_caso = rev["caso"] or "conversacion"
    return armar_caso(
        config, datos, origen=f"revision:{rev['id']}", caso_manual=rev["caso"],
        descripcion=f"desde conversacion real: {nombre_caso} (revision {rev['id'][:8]})")


def candidatos(tenant: str) -> list[tuple[str, str]]:
    """Todo lo que el equipo marco como dorado: los ejemplos marcados y las
    revisiones APROBADAS de buen ejemplo. [(tipo, id)], lo mas viejo primero
    para que el archivo crezca en el orden en que se marco."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select 'ejemplo' as tipo, id::text as id, creado_en
                 from asistente.ejemplos_validados where organization_id = %s
               union all
               select 'revision', id::text, coalesce(revisado_en, creado_en)
                 from asistente.revisiones_supervisor
                where organization_id = %s and estado = 'aprobado'
                  and es_buen_ejemplo
                order by 3, 2""", (org, org))
        return [(f["tipo"], f["id"]) for f in cur.fetchall()]


# --------------------------------------------------------------------------
#  Reproducir en el simulador
# --------------------------------------------------------------------------

def mensajes_para_reproducir(tenant: str, conversation_id: str) -> list[str]:
    """Lo que escribio el cliente, solo texto y redactado, en orden.

    Es lo que el simulador reenvia a una conversacion NUEVA con canal
    simulado: se prueba que haria Dexter HOY con la misma conversacion, sin
    tocar la original ni al cliente. Mismo recorte que un caso dorado.
    """
    with sesion(tenant) as (cur, org):
        datos = _leer(cur, org, conversation_id, None)
    return [redaccion.redactar(m["contenido"])
            for m in datos["mensajes"][:MAXIMO_MENSAJES * 2]]
