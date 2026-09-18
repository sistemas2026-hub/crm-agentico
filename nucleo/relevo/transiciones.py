# -*- coding: utf-8 -*-
"""
Las transiciones del relevo IA <-> humano, escritas en la base.

B3.2 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md (§6, §9). ESCRITURA EN PARALELO: cada
transicion deja la verdad nueva (control, asignacion, relevo_eventos,
relevo_version) junto con la de legado que hoy decide todo. Nada de lo que
escribe este modulo cambia todavia quien responde al cliente: la pausa se
sigue decidiendo con las banderas de legado y la memoria, hasta el corte de
control (despues de G8).

UNA TRANSICION = UNA TRANSACCION CORTA, SOLO POSTGRESQL
------------------------------------------------------
    lock de la fila -> precondicion -> nueva verdad + legado -> evento -> COMMIT

Si cualquier escritura falla, rollback de todo: nunca control sin evento, ni
evento sin control. Y dentro de la transaccion NO hay HTTP, Meta, CRM, WispHub,
SmartOLT, modelo ni archivos: produccion corta a los 60 s una transaccion
ociosa (idle_in_transaction_session_timeout), y un efecto externo lento
dejaria la fila bloqueada. Quien llama hace los efectos externos DESPUES.

relevo_version
--------------
  0      la conversacion nunca entro al modelo nuevo (todo el legado).
  +1     exactamente una vez por transicion aceptada que cambia algo durable.
  igual  en un reintento con la misma clave o en un no-op: ni version nueva
         ni otro evento.
Cada evento guarda la version que dejo, en datos.version.

GOBERNADA O LEGADO
------------------
Escalar e intervenir son transiciones de ENTRADA: meten la conversacion al
modelo nuevo aunque este en version 0. Tomar, soltar, resolver y devolver sobre
una conversacion en version 0 escriben SOLO lo de legado, exactamente como hoy:
son las conversaciones anteriores al corte, que se reconcilian una por una en
G8, no por un efecto lateral de un clic.

LO QUE CADA UNA SIGNIFICA (y no significa)
------------------------------------------
  escalar          control humano / escalada, sin asignacion, Y las banderas
                   de legado que hoy deciden la pausa, en la misma transaccion.
                   Se reserva ANTES de crear ticket o caso; si esos efectos
                   fallan despues, el control NO vuelve a la IA (politica
                   fail-closed, Q5).
  intervenir       control humano / intervencion; con tomar=True, asignada al
                   actor en la misma transaccion. No tiene equivalente de
                   legado y no hay ruta que la exponga todavia.
  tomar            asigna una conversacion de personas LIBRE; control y motivo
                   intactos. Si ya tiene dueno, 'ya_asignada': nunca lo pisa
                   (B3.4, D4). Bajo control ia, 'control_ia': eso es intervenir.
  soltar           solo quien la tiene; SIGUE HUMANA. No es devolver.
  reasignar        la unica que cambia una asignacion ajena. ADMIN (lo exige
                   la ruta), motivo obligatorio, evento con anterior y nuevo.
  resolver         cierra y libera la asignacion; con persona, atendida_manual.
                   Tampoco es devolver: la conversacion queda cerrada, no en
                   manos de la IA.
  devolver_a_ia    la UNICA que deja control ia. El mecanismo queda probado;
                   la funcion "Responder y devolver" (T6) no se habilita hasta
                   G9.
  caso_externo_cerrado
                   SOLO un aviso y su evento: nunca cambia control ni
                   asignacion. El CRM es un sistema relacionado, no la
                   autoridad sobre quien atiende una conversacion de Dexter;
                   devolverla a la IA es siempre devolver_a_ia(), un solo
                   camino.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg
from psycopg.types.json import Jsonb

from nucleo.persistencia import db
from nucleo.relevo import control as regla_control

# Punto de inyeccion de fallas para las pruebas: se llama DENTRO de la
# transaccion, despues de escribir estado y evento y antes del commit.
_gancho_antes_del_commit = None


@dataclass
class Resultado:
    aplicada: bool                       # cambio algo durable en esta llamada
    gobernada: bool                      # la conversacion esta en el modelo nuevo
    version: int | None = None           # relevo_version despues de la llamada
    evento_id: str | None = None
    motivo: str = ""                     # por que no se aplico, si no se aplico
    datos: dict = field(default_factory=dict)


# El esquema de 'datos' por tipo (contrato §3.3, X19): solo estas claves y solo
# valores simples. Nunca respuestas de APIs externas ni datos del cliente.
ESQUEMAS: dict[str, frozenset[str]] = {
    "escalada": frozenset({"version", "motivo"}),
    "intervencion": frozenset({"version", "motivo_texto", "tomada"}),
    "tomada": frozenset({"version", "anterior_nombre"}),
    "soltada": frozenset({"version", "anterior_nombre"}),
    "reasignada": frozenset({"version", "anterior_usuario_id", "anterior_nombre",
                             "nuevo_usuario_id", "nuevo_nombre", "motivo"}),
    "cerrada": frozenset({"version", "por"}),
    "devuelta_a_ia": frozenset({"version"}),
    "caso_externo_cerrado": frozenset({"version", "aplicado"}),
}
DATOS_VERSION = 1
MAX_TEXTO = 500


def validar_datos(tipo: str, datos: dict) -> dict:
    permitidas = ESQUEMAS.get(tipo)
    if permitidas is None:
        raise ValueError(f"tipo de evento sin esquema: {tipo!r}")
    sobrantes = set(datos) - permitidas
    if sobrantes:
        raise ValueError(f"'{tipo}' no admite {sorted(sobrantes)}")
    for k, v in datos.items():
        if v is not None and not isinstance(v, (str, int, bool)):
            raise ValueError(f"'{tipo}.{k}' tiene que ser un valor simple")
        if isinstance(v, str) and len(v) > MAX_TEXTO:
            raise ValueError(f"'{tipo}.{k}' supera {MAX_TEXTO} caracteres")
    return datos


def _evento_previo(cur, org, conversation_id, clave):
    if not clave:
        return None
    cur.execute("""select id, datos, tipo, actor_usuario_id from asistente.relevo_eventos
                   where organization_id = %s and conversation_id = %s
                     and clave_idempotencia = %s""", (org, conversation_id, clave))
    return cur.fetchone()


def _fila(cur, org, conversation_id):
    cur.execute("""select control, control_motivo, asignada_a_usuario_id, asignada_a_nombre,
                          relevo_version, estado, pendiente_interno_desde,
                          escalada_a_humano, necesita_atencion_humana, tomada_por
                   from asistente.conversations
                   where organization_id = %s and id = %s
                   for update""", (org, conversation_id))
    return cur.fetchone()


def _evento(cur, org, conversation_id, tipo, actor_tipo, actor_id, actor_nombre, datos, clave):
    cur.execute("""insert into asistente.relevo_eventos
                     (organization_id, conversation_id, tipo, datos_version, actor_tipo,
                      actor_usuario_id, actor_nombre, datos, clave_idempotencia)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                (org, conversation_id, tipo, DATOS_VERSION, actor_tipo, actor_id, actor_nombre,
                 Jsonb(validar_datos(tipo, datos)), clave))
    return str(cur.fetchone()["id"])


def _replay(previo, tipo, actor_id) -> Resultado:
    """
    Lo que se responde cuando la clave ya se uso. Es un reintento SOLO si es la
    misma operacion (mismo tipo de evento) del mismo actor. Otro operador con
    la misma clave -- un id repetido, un cliente mal hecho -- no puede recibir
    exito como si hubiera sido el quien intervino o tomo la conversacion.
    """
    version = (previo["datos"] or {}).get("version")
    actor_previo = str(previo["actor_usuario_id"]) if previo["actor_usuario_id"] else None
    if previo["tipo"] != tipo or actor_previo != (str(actor_id) if actor_id else None):
        return Resultado(False, True, version, None, "clave_ajena")
    return Resultado(False, True, version, str(previo["id"]), "reintento")


def _ejecutar(tenant, conversation_id, clave, cuerpo, *, tipo, actor_id=None) -> Resultado:
    """
    Corre 'cuerpo(cur, org, fila)' en UNA transaccion. Resuelve aca lo comun:
    conversacion inexistente, reintento con la misma clave (antes de tocar
    nada, y tambien si dos pedidos iguales llegan a la vez y el segundo choca
    con el indice unico), y el gancho de fallas.

    'tipo' y 'actor_id' son los del evento que escribiria esta llamada: un
    reintento solo es reintento si los dos coinciden con el evento previo.
    """
    try:
        with db.sesion(tenant) as (cur, org):
            previo = _evento_previo(cur, org, conversation_id, clave)
            if previo:
                return _replay(previo, tipo, actor_id)
            fila = _fila(cur, org, conversation_id)
            if fila is None:
                return Resultado(False, False, None, None, "no_existe")
            resultado = cuerpo(cur, org, fila)
            if resultado.aplicada and _gancho_antes_del_commit:
                _gancho_antes_del_commit()
            return resultado
    except psycopg.errors.UniqueViolation:
        with db.sesion(tenant) as (cur, org):
            previo = _evento_previo(cur, org, conversation_id, clave)
        if previo:
            return _replay(previo, tipo, actor_id)
        raise


def _es_de_personas(f) -> Resultado | None:
    """Precondicion de tomar y reasignar: abierta y en manos de personas por
    control EFECTIVO (legado: las banderas; gobernada: la columna)."""
    gobernada = f["relevo_version"] > 0
    if f["estado"] != "abierta":
        return Resultado(False, gobernada, f["relevo_version"], None, "no_abierta")
    if regla_control.control_efectivo(f) != "humano":
        return Resultado(False, gobernada, f["relevo_version"], None, "control_ia")
    return None


def _subir_version(cur, org, conversation_id, set_sql, params) -> int:
    cur.execute(f"""update asistente.conversations
                    set {set_sql}, relevo_version = relevo_version + 1
                    where organization_id = %s and id = %s
                    returning relevo_version""", (*params, org, conversation_id))
    return cur.fetchone()["relevo_version"]


# =============================================================================
#  transiciones de entrada
# =============================================================================

def escalar(tenant: str, conversation_id: str, *, motivo: str = "",
            clave: str | None = None) -> Resultado:
    """
    Reserva el control humano por escalada. Sin asignacion. No-op si la
    conversacion ya esta en control humano o cerrada.

    Escribe TAMBIEN las banderas de legado que hoy deciden la pausa
    (escalada_a_humano, necesita_atencion_humana), en la misma transaccion.
    Sin eso la verdad nueva diria 'humano' mientras el runtime deja hablar a
    la IA: con las guardas de B3.3 una persona y la IA podrian atender a la
    vez. Si despues fallan el ticket o el CRM, la conversacion SIGUE pausada
    (fail-closed, Q5): la atencion humana ya quedo pedida; el efecto externo
    es otra cosa y se reconcilia aparte (B4).
    """
    def cuerpo(cur, org, f):
        if f["estado"] != "abierta" or regla_control.control_efectivo(f) == "humano":
            return Resultado(False, f["relevo_version"] > 0, f["relevo_version"], None, "sin_cambio")
        version = _subir_version(
            cur, org, conversation_id,
            "control = 'humano', control_motivo = 'escalada', escalada_a_humano = true, "
            "necesita_atencion_humana = true, escalada_en = coalesce(escalada_en, now()), "
            "motivo_escalamiento = coalesce(%s, motivo_escalamiento), actualizado_en = now()",
            ((motivo or None),))
        datos = {"version": version, "motivo": (motivo or "")[:MAX_TEXTO] or None}
        ev = _evento(cur, org, conversation_id, "escalada", "ia", None, None, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="escalada")


def intervenir(tenant: str, conversation_id: str, *, operador_id: str, operador_nombre: str,
               tomar: bool = True, motivo_texto: str = "", clave: str | None = None) -> Resultado:
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        # Precondicion por control EFECTIVO: una conversacion de legado escalada
        # (control 'ia' por default) ya esta en manos de personas -- intervenir
        # ahi seria robarle la conversacion a la escalada. Con el lock de la fila,
        # de dos operadores que intervienen a la vez solo el primero la encuentra
        # en manos de la IA; el segundo recibe sin_cambio y no reasigna nada.
        if f["estado"] != "abierta" or regla_control.control_efectivo(f) == "humano":
            return Resultado(False, f["relevo_version"] > 0, f["relevo_version"], None, "sin_cambio")
        if tomar:
            version = _subir_version(
                cur, org, conversation_id,
                "control = 'humano', control_motivo = 'intervencion', asignada_a_usuario_id = %s, "
                "asignada_a_nombre = %s, asignada_en = now(), tomada_por = %s, tomada_en = now()",
                (usuario, nombre, nombre))
        else:
            version = _subir_version(cur, org, conversation_id,
                                     "control = 'humano', control_motivo = 'intervencion'", ())
        datos = {"version": version, "motivo_texto": (motivo_texto or "")[:MAX_TEXTO] or None,
                 "tomada": bool(tomar)}
        ev = _evento(cur, org, conversation_id, "intervencion", "operador", usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="intervencion", actor_id=usuario)


# =============================================================================
#  transiciones sobre una conversacion en manos de personas
# =============================================================================

def tomar(tenant: str, conversation_id: str, *, operador_id: str, operador_nombre: str,
          clave: str | None = None) -> Resultado:
    """
    B3.4 (D4). Una conversacion en manos de personas y SIN asignar la toma
    exactamente un operador. Con la fila bloqueada (_fila, FOR UPDATE), de dos
    que toman a la vez el segundo la encuentra asignada y recibe 'ya_asignada':
    nunca se pisa al primero. Pasar una conversacion de una persona a otra es
    reasignar(), explicito y solo ADMIN.

    'control_ia' si la atiende la IA: tomar no es un segundo camino para
    intervenir. Legado (version 0): la misma exclusion sobre 'tomada_por', sin
    evento ni version -- G8 adopta, no un clic.
    """
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        precondicion = _es_de_personas(f)
        if precondicion:
            return precondicion
        if f["relevo_version"] == 0:
            if f["tomada_por"]:
                if f["tomada_por"] == nombre:
                    return Resultado(False, False, 0, None, "ya_era_suya")
                return Resultado(False, False, 0, None, "ya_asignada",
                                 datos={"asignada_a_nombre": f["tomada_por"]})
            cur.execute("""update asistente.conversations
                           set tomada_por = %s, tomada_en = now(), actualizado_en = actualizado_en
                           where organization_id = %s and id = %s""", (nombre, org, conversation_id))
            return Resultado(True, False, 0, None, "legado")
        if f["asignada_a_usuario_id"]:
            if str(f["asignada_a_usuario_id"]) == usuario:
                return Resultado(False, True, f["relevo_version"], None, "ya_era_suya")
            return Resultado(False, True, f["relevo_version"], None, "ya_asignada",
                             datos={"asignada_a_nombre": f["asignada_a_nombre"]})
        version = _subir_version(
            cur, org, conversation_id,
            "asignada_a_usuario_id = %s, asignada_a_nombre = %s, asignada_en = now(), "
            "tomada_por = %s, tomada_en = now(), actualizado_en = actualizado_en",
            (usuario, nombre, nombre))
        datos = {"version": version, "anterior_nombre": None}
        ev = _evento(cur, org, conversation_id, "tomada", "operador", usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="tomada", actor_id=usuario)


def soltar(tenant: str, conversation_id: str, *, operador_id: str, operador_nombre: str,
           clave: str | None = None) -> Resultado:
    """
    Solo quien la tiene asignada la suelta. Otro operador recibe 'no_es_suya';
    sacarsela a alguien es reasignar(), de ADMIN. Soltar deja la conversacion
    esperando a OTRA persona: el control no se toca.
    """
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        if f["relevo_version"] == 0:
            if not f["tomada_por"]:
                return Resultado(False, False, 0, None, "sin_asignacion")
            if f["tomada_por"] != nombre:
                return Resultado(False, False, 0, None, "no_es_suya",
                                 datos={"asignada_a_nombre": f["tomada_por"]})
            cur.execute("""update asistente.conversations set tomada_por = null, tomada_en = null
                           where organization_id = %s and id = %s""", (org, conversation_id))
            return Resultado(True, False, 0, None, "legado")
        if f["asignada_a_usuario_id"] is None:
            return Resultado(False, True, f["relevo_version"], None, "sin_asignacion")
        if str(f["asignada_a_usuario_id"]) != usuario:
            return Resultado(False, True, f["relevo_version"], None, "no_es_suya",
                             datos={"asignada_a_nombre": f["asignada_a_nombre"]})
        version = _subir_version(
            cur, org, conversation_id,
            "asignada_a_usuario_id = null, asignada_a_nombre = null, asignada_en = null, "
            "tomada_por = null, tomada_en = null", ())
        datos = {"version": version, "anterior_nombre": f["asignada_a_nombre"]}
        ev = _evento(cur, org, conversation_id, "soltada", "operador", usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="soltada", actor_id=usuario)


def reasignar(tenant: str, conversation_id: str, *, admin_id: str, admin_nombre: str,
              destino_id: str, destino_nombre: str, motivo: str,
              clave: str | None = None) -> Resultado:
    """
    T4 (D4). Pasa la conversacion a 'destino', este asignada a otro o libre.
    Es la UNICA escritura que cambia una asignacion ajena, y la autoriza quien
    llama: la ruta exige rol ADMIN (403) y valida el destino contra la
    organizacion antes de llegar aca. Motivo obligatorio.

    Evento 'reasignada' con quien la hizo (actor), el anterior y el nuevo
    asignado, el motivo y la version.

    Legado (version 0): 'legado_sin_relevo', no se escribe nada. Una
    reasignacion tiene que quedar auditada, y el legado no tiene eventos:
    se adopta primero (G8).
    """
    nombre_admin, id_admin = db.validar_autor(admin_nombre, admin_id)
    nombre_destino, id_destino = db.validar_autor(destino_nombre, destino_id)
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("la reasignacion exige un motivo")
    if len(motivo) > MAX_TEXTO:
        raise ValueError(f"el motivo supera {MAX_TEXTO} caracteres")

    def cuerpo(cur, org, f):
        if f["relevo_version"] == 0:
            return Resultado(False, False, 0, None, "legado_sin_relevo")
        precondicion = _es_de_personas(f)
        if precondicion:
            return precondicion
        if f["asignada_a_usuario_id"] and str(f["asignada_a_usuario_id"]) == id_destino:
            return Resultado(False, True, f["relevo_version"], None, "ya_era_del_destino")
        version = _subir_version(
            cur, org, conversation_id,
            "asignada_a_usuario_id = %s, asignada_a_nombre = %s, asignada_en = now(), "
            "tomada_por = %s, tomada_en = now(), actualizado_en = actualizado_en",
            (id_destino, nombre_destino, nombre_destino))
        datos = {"version": version,
                 "anterior_usuario_id": str(f["asignada_a_usuario_id"]) if f["asignada_a_usuario_id"] else None,
                 "anterior_nombre": f["asignada_a_nombre"],
                 "nuevo_usuario_id": id_destino, "nuevo_nombre": nombre_destino,
                 "motivo": motivo}
        ev = _evento(cur, org, conversation_id, "reasignada", "operador", id_admin, nombre_admin, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="reasignada", actor_id=id_admin)


def resolver(tenant: str, conversation_id: str, *, operador_id: str, operador_nombre: str,
             clave: str | None = None) -> Resultado:
    """Cierra la conversacion. datos del Resultado: usuario_externo y canal,
    para descartar la sesion en memoria (los devuelve aun en legado)."""
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        cur.execute("""select usuario_externo, canal from asistente.conversations
                       where organization_id = %s and id = %s""", (org, conversation_id))
        ident = dict(cur.fetchone())
        legado_sql = ("estado = 'cerrada', atendida_manual = true, "
                      "atendida_por = coalesce(%s, atendida_por), actualizado_en = now()")
        if f["relevo_version"] == 0:
            cur.execute(f"""update asistente.conversations set {legado_sql}
                            where organization_id = %s and id = %s""", (nombre, org, conversation_id))
            return Resultado(True, False, 0, None, "legado", datos=ident)
        if f["estado"] == "cerrada":
            return Resultado(False, True, f["relevo_version"], None, "ya_cerrada", datos=ident)
        # Libera la asignacion y NO toca el control: cerrar no es devolver.
        version = _subir_version(
            cur, org, conversation_id,
            legado_sql + ", asignada_a_usuario_id = null, asignada_a_nombre = null, asignada_en = null",
            (nombre,))
        datos = {"version": version, "por": "operador"}
        ev = _evento(cur, org, conversation_id, "cerrada", "operador", usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos=ident)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="cerrada", actor_id=usuario)


def devolver_a_ia(tenant: str, conversation_id: str, *, operador_id: str, operador_nombre: str,
                  clave: str | None = None) -> Resultado:
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        legado_sql = "escalada_a_humano = false, necesita_atencion_humana = false"
        if f["relevo_version"] == 0:
            cur.execute(f"""update asistente.conversations set {legado_sql}
                            where organization_id = %s and id = %s""", (org, conversation_id))
            return Resultado(True, False, 0, None, "legado")
        if f["estado"] != "abierta" or f["control"] != "humano":
            return Resultado(False, True, f["relevo_version"], None, "no_es_humana")
        version = _subir_version(
            cur, org, conversation_id,
            legado_sql + ", control = 'ia', control_motivo = null, asignada_a_usuario_id = null, "
            "asignada_a_nombre = null, asignada_en = null, pendiente_interno_desde = null, "
            "pendiente_interno_nota = null, aviso_relevo = null", ())
        datos = {"version": version}
        ev = _evento(cur, org, conversation_id, "devuelta_a_ia", "operador", usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="devuelta_a_ia", actor_id=usuario)


def caso_externo_cerrado(tenant: str, conversation_id: str, *, clave: str | None = None) -> Resultado:
    def cuerpo(cur, org, f):
        if (f["relevo_version"] == 0 or f["estado"] != "abierta" or f["control"] != "humano"
                or f["control_motivo"] != "escalada"):
            return Resultado(False, f["relevo_version"] > 0, f["relevo_version"], None, "no_aplica")
        cur.execute("""select aviso_relevo from asistente.conversations
                       where organization_id = %s and id = %s""", (org, conversation_id))
        if cur.fetchone()["aviso_relevo"] == "caso_externo_cerrado":
            return Resultado(False, True, f["relevo_version"], None, "ya_avisado")
        # Haya o no alguien a cargo: aviso, y nada mas. Ni control ni asignacion.
        version = _subir_version(cur, org, conversation_id,
                                 "aviso_relevo = 'caso_externo_cerrado'", ())
        datos = {"version": version, "aplicado": False}
        ev = _evento(cur, org, conversation_id, "caso_externo_cerrado", "sistema", None, None, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="caso_externo_cerrado")
