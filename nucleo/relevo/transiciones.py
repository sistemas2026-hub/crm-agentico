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
  cerrar           termina la conversacion Y deja dicho por que (B6): quien la
                   cerro (los cinco caminos de §6) y, cuando lo eligio una
                   persona, con que desenlace. Libera la asignacion. NO es
                   devolver: queda cerrada, no en manos de la IA. Y NO cierra
                   el caso ni el ticket de afuera: eso es la cola de §3.6.
  resolver         el cierre manual (T17), o sea cerrar(por='operador'). El
                   desenlace es obligatorio y no se infiere.
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
from nucleo.relevo import asignados_crm
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
    # 'legado' y 'g8' solo aparecen en la adopcion de G8: dicen que esta
    # conversacion venia de antes del corte y que fue una PERSONA la que
    # decidio que hacer con ella. Sin esas dos claves, dentro de un año nadie
    # podria distinguir una escalada real de una adopcion administrativa.
    "escalada": frozenset({"version", "motivo", "legado", "g8"}),
    "intervencion": frozenset({"version", "motivo_texto", "tomada"}),
    "tomada": frozenset({"version", "anterior_nombre"}),
    "soltada": frozenset({"version", "anterior_nombre"}),
    "reasignada": frozenset({"version", "anterior_usuario_id", "anterior_nombre",
                             "nuevo_usuario_id", "nuevo_nombre", "motivo"}),
    # B6. 'por' es QUIEN cerro (el camino: T15a/T15b/T16/T17/T18) y 'desenlace'
    # es QUE le paso al cliente. Son datos distintos y ninguno se deduce del
    # otro: un cierre por plazo y uno manual pueden terminar en el mismo
    # desenlace, y dos cierres manuales del mismo operador, en desenlaces
    # opuestos. 'categoria' viaja con el codigo porque la config de la empresa
    # puede cambiar y este evento no (§3.6).
    "cerrada": frozenset({"version", "por", "desenlace", "categoria", "nota",
                          "acciones_canceladas", "acciones_en_vuelo",
                          "legado", "g8"}),
    "devolucion_solicitada": frozenset({"mensaje_id"}),
    "devolucion_fallida": frozenset({"mensaje_id", "resultado"}),
    "devuelta_a_ia": frozenset({"version", "legado", "g8"}),
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
                          escalada_a_humano, necesita_atencion_humana, tomada_por,
                          caso_id, atendida_manual
                   from asistente.conversations
                   where organization_id = %s and id = %s
                   for update""", (org, conversation_id))
    return cur.fetchone()


def _evento(cur, org, conversation_id, tipo, actor_tipo, actor_id, actor_nombre, datos, clave):
    # 'creado_en' explicito con clock_timestamp() y NO el default now() (D27).
    # now() es la hora en que EMPEZO la transaccion: de dos transiciones a la
    # vez sobre la misma conversacion, la que espero el lock de la fila puede
    # quedar con una hora ANTERIOR habiendo escrito despues -- visto con una
    # reasignacion (v3) fechada antes que la toma (v2) que reemplazo.
    # clock_timestamp() se evalua al insertar, ya con la fila bloqueada, asi
    # que sigue el mismo orden que las versiones.
    #
    # El orden CAUSAL sigue siendo datos.version; esto hace que la hora que se
    # MUESTRA no lo contradiga. No se reescribe nada de lo ya guardado.
    cur.execute("""insert into asistente.relevo_eventos
                     (organization_id, conversation_id, tipo, datos_version, actor_tipo,
                      actor_usuario_id, actor_nombre, datos, clave_idempotencia, creado_en)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp()) returning id""",
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

def _encolar_asignacion_crm(cur, org, conversation_id, f, usuario_id: str) -> None:
    """
    Anota que el caso del CRM tiene que mostrar a este operador (D28).

    VA EN LA MISMA TRANSACCION que el cambio de asignacion, y eso NO contradice
    "no escribir en el CRM dentro de la transaccion": lo que se escribe aca es
    la INTENCION, en una tabla propia. Al CRM lo llama el reconciliador,
    despues del COMMIT y fuera de toda transaccion (§3.6, X23). Si se hiciera
    al reves --primero el CRM, despues el commit-- un fallo dejaria el caso
    asignado a alguien que en Dexter no lo tiene.

    Sin caso todavia no hay nada que asignar: una conversacion puede cambiar de
    manos antes de que exista el caso, y forzar uno aca seria inventar un
    efecto sobre algo que no esta. Cuando el caso se cree, la siguiente
    transicion lo encola.

    El PERFIL del CRM no se resuelve aca a proposito: eso exige preguntarle al
    CRM, y una llamada HTTP dentro de esta transaccion es justo lo que X23
    prohibe. Viaja el usuario durable y el ejecutor lo traduce.
    """
    caso_id = f.get("caso_id") if hasattr(f, "get") else None
    if not caso_id or not usuario_id:
        return

    # SIN try/except, y es deliberado. Antes habia uno, con el argumento de que
    # "no se puede tumbar la toma por no poder reflejarla". Estaba mal por dos
    # motivos:
    #
    #   1. NO SALVABA NADA. Esto corre con el cursor de la transaccion. Un error
    #      de base aqui deja la transaccion abortada, asi que atraparlo no
    #      permite seguir: el COMMIT termina en ROLLBACK igual. El except
    #      prometia una resistencia que no existia.
    #
    #   2. SI hubiera funcionado --para un error que no fuera de base-- habria
    #      dejado el estado que D28 existe para impedir: el operador cambiado en
    #      Dexter, ninguna intencion encolada, y nada durable que lo diga. La
    #      divergencia volveria en silencio, que es de donde venimos.
    #
    # Dejandolo propagar, la transicion entera hace rollback: o cambia el
    # operador Y queda la intencion, o no cambia nada. El operador ve un error y
    # reintenta, que es mucho mejor que una divergencia que nadie nota.
    #
    # Una clave repetida NO es un fallo: encolar_sincronizacion hace
    # 'on conflict do nothing' y devuelve None. La intencion ya existe y se
    # adopta -- que es justo lo que tiene que pasar cuando alguien toma dos
    # veces la misma conversacion.
    db.encolar_sincronizacion(
        cur, org, conversation_id, tipo="asignar_caso",
        clave=asignados_crm.clave_de_asignacion(
            conversation_id, str(caso_id), str(usuario_id)),
        datos={"caso_id": str(caso_id), "usuario_id": str(usuario_id)})


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
        _encolar_asignacion_crm(cur, org, conversation_id, f, usuario)
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
        # El que entra, no el que sale: el efecto es aditivo y al anterior NO se
        # lo quita (D28). El CRM no guarda quien asigno a quien, asi que sacarlo
        # podria borrar una colaboracion que nadie automatizo.
        _encolar_asignacion_crm(cur, org, conversation_id, f, id_destino)
        return Resultado(True, True, version, ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="reasignada", actor_id=id_admin)


# =============================================================================
#  G8 -- la adopcion de una conversacion de legado
# =============================================================================

#: Las cuatro decisiones que §11.2 pone en manos de una persona. TRES estan
#: implementadas y una NO, y la diferencia no es de esfuerzo:
#:
#:   seguir_humano           implementada
#:   volver_ia               implementada
#:   cerrar_con_desenlace    implementada desde B6, que trajo las columnas y el
#:                           catalogo. Antes se rechazaba: cerrar sin codigo
#:                           habria sido cerrar 16 conversaciones de clientes
#:                           sin decir por que, justo en el registro que existe
#:                           para poder decirlo.
#:   resolver_estado_externo NO ES UNA TRANSICION DEL RELEVO. Es cerrar el caso
#:                           o el ticket afuera, o sea un efecto externo
#:                           ('cerrar_caso'/'cerrar_ticket' de B4), y esos tipos
#:                           no tienen productor. Ademas 'cerrar_ticket' esta
#:                           bloqueado por el gate Q2.
#:
#: La que falta se rechaza explicitamente, con su motivo. Inventarla a medias
#: seria peor que no tenerla: quien revise creeria que decidio algo que el
#: sistema no registro.
DECISIONES_G8 = ("seguir_humano", "cerrar_con_desenlace",
                 "resolver_estado_externo", "volver_ia")

DECISIONES_G8_IMPLEMENTADAS = ("seguir_humano", "volver_ia",
                               "cerrar_con_desenlace")

#: Las que exigen un desenlace elegido por la persona que decide.
DECISIONES_G8_CON_DESENLACE = ("cerrar_con_desenlace",)

#: Que evento deja cada decision. Importa para el replay: una clave repetida
#: solo es reintento si coincide el TIPO de evento y el actor, asi que este
#: mapa tiene que decir la verdad o dos decisiones distintas con la misma clave
#: se leerian como la misma.
_EVENTO_G8 = {"seguir_humano": "escalada", "volver_ia": "devuelta_a_ia",
              "cerrar_con_desenlace": "cerrada"}

_POR_QUE_FALTA = {
    "resolver_estado_externo":
        "no es una transicion del relevo: es cerrar el caso o el ticket afuera, "
        "y esos efectos no tienen productor todavia (B4). 'cerrar_ticket' ademas "
        "esta bloqueado por el gate Q2.",
}


def adoptar_de_legado(tenant: str, conversation_id: str, *, decision: str,
                      operador_id: str, operador_nombre: str,
                      desenlace: str | None = None, nota: str | None = None,
                      config=None, clave: str | None = None) -> Resultado:
    """
    G8. Una PERSONA decidio que hacer con una conversacion de legado, y esto lo
    escribe.

    Es la unica via por la que una conversacion con 'relevo_version = 0' entra
    al modelo nuevo fuera de escalar e intervenir (C5, I21). No hay UPDATE
    masivo ni adopcion automatica: ninguna clasificacion A/B/C llega hasta aca,
    porque la clasificacion vive en una herramienta de SOLO LECTURA que no puede
    escribir aunque quisiera.

    El operador es obligatorio y se valida: una adopcion sin responsable no se
    puede auditar, y el registro entero existe para poder auditarla.

    La transicion y su evento van en la MISMA transaccion (I12). Si el evento
    falla, no queda la conversacion adoptada sin quien ni por que.

    Repetir la misma decision con la misma clave NO duplica: devuelve el evento
    anterior sin escribir otra vez (el replay de _ejecutar). Sin clave, una
    conversacion que ya fue adoptada responde 'ya_adoptada' y no se toca.
    """
    if decision not in DECISIONES_G8:
        raise ValueError(f"decision de G8 desconocida: {decision!r}. "
                         f"Son {list(DECISIONES_G8)}")
    if decision not in DECISIONES_G8_IMPLEMENTADAS:
        raise NotImplementedError(
            f"'{decision}' no se puede registrar todavia: {_POR_QUE_FALTA[decision]}")

    from nucleo.relevo import desenlaces as catalogo

    codigo = categoria = None
    if decision in DECISIONES_G8_CON_DESENLACE:
        # Mismo criterio que T17 y por la misma puerta: una conversacion de
        # legado se cierra con un codigo elegido, o no se cierra. Que sea vieja
        # no la hace menos de un cliente.
        if not (desenlace or "").strip():
            raise ValueError(
                "'cerrar_con_desenlace' exige un codigo de desenlace (§3.5)")
        codigo, categoria = catalogo.resolver_para_cerrar(desenlace, config)
    elif desenlace:
        raise ValueError(f"'{decision}' no lleva desenlace")

    nota = (nota or "").strip() or None
    if nota and decision not in DECISIONES_G8_CON_DESENLACE:
        raise ValueError(f"'{decision}' no lleva nota de cierre")
    if nota and len(nota) > catalogo.MAX_NOTA:
        raise ValueError(f"la nota supera {catalogo.MAX_NOTA} caracteres")

    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        # Ya gobernada: no se vuelve a adoptar. I21 dice que relevo_version
        # nunca baja, y adoptar de nuevo pisaria una decision que ya se tomo
        # --quiza la de otra persona, quiza con otro criterio.
        if f["relevo_version"] != 0:
            return Resultado(False, True, f["relevo_version"], None, "ya_adoptada",
                             datos={"version": f["relevo_version"]})
        if f["estado"] != "abierta":
            return Resultado(False, False, 0, None, "no_esta_abierta")

        if decision == "seguir_humano":
            # §11.2 al pie de la letra: control humano con motivo 'escalada', y
            # la asignacion copiada de 'tomada_por' SOLO como nombre.
            #
            # 'asignada_a_usuario_id' queda NULL a proposito: 'tomada_por' es un
            # nombre, y un nombre no prueba identidad. Inventar el id seria
            # atribuirle a una persona concreta una conversacion que quiza no
            # es suya -- el mismo error que D28 existe para no cometer.
            version = _subir_version(
                cur, org, conversation_id,
                "control = 'humano', control_motivo = 'escalada', "
                "asignada_a_nombre = tomada_por, asignada_a_usuario_id = null, "
                "asignada_en = case when tomada_por is not null "
                "                   then coalesce(tomada_en, now()) end, "
                "escalada_a_humano = true, necesita_atencion_humana = true, "
                "actualizado_en = actualizado_en", ())
            tipo_evento = "escalada"
        elif decision == "cerrar_con_desenlace":
            # Cierra Y adopta, en la misma escritura. La adopcion no es un
            # tramite previo: es lo que hace que este cierre quede en el
            # expediente del relevo con quien lo decidio, que es justo lo que
            # §11.2 pide y lo que un cierre por el boton de siempre no deja
            # (sobre una conversacion en version 0 no escribe ningun evento).
            #
            # El control queda en 'ia' como estaba: no se le entrega a nadie
            # una conversacion que acaba de terminar, y 'tomada_por' sigue sin
            # probar identidad. Las banderas de legado tampoco se tocan --una
            # conversacion cerrada no vuelve a ninguna cola, que selecciona
            # por estado 'abierta'.
            sets = ("estado = 'cerrada', cerrada_por_tipo = 'operador', "
                    "cerrada_por_usuario_id = %s, atendida_manual = true, "
                    "atendida_por = coalesce(%s, atendida_por), "
                    "desenlace_codigo = %s, desenlace_categoria_base = %s, "
                    "actualizado_en = now()")
            params: tuple = (usuario, nombre, codigo, categoria)
            if nota:
                sets += ", desenlace_nota = %s"
                params += (nota,)
            version = _subir_version(cur, org, conversation_id, sets, params)
            tipo_evento = "cerrada"
        else:  # volver_ia
            # Las banderas de legado se apagan junto con el control, en la misma
            # escritura: si quedaran puestas, la reconstruccion seguiria
            # pausando la conversacion y la decision no tendria efecto.
            version = _subir_version(
                cur, org, conversation_id,
                "control = 'ia', control_motivo = null, "
                "asignada_a_usuario_id = null, asignada_a_nombre = null, "
                "asignada_en = null, escalada_a_humano = false, "
                "necesita_atencion_humana = false, actualizado_en = actualizado_en", ())
            tipo_evento = "devuelta_a_ia"

        datos = {"version": version, "legado": True, "g8": decision}
        if codigo:
            datos["por"] = "operador"
            datos["desenlace"] = codigo
            datos["categoria"] = categoria
            if nota:
                datos["nota"] = nota
        ev = _evento(cur, org, conversation_id, tipo_evento, "operador",
                     usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos=datos)

    return _ejecutar(tenant, conversation_id, clave, cuerpo,
                     tipo=_EVENTO_G8[decision], actor_id=usuario)


# =============================================================================
#  B6 -- el cierre dice por que
# =============================================================================

#: Los cinco caminos de cierre de §6. El nombre dice QUIEN cerro, no por que.
#:
#:   cliente      T15a. El cliente confirmo, con una persona a cargo.
#:   ia_cliente   T15b. El cliente confirmo con la IA atendiendo.
#:   plazo        T16.  Barrido: el cliente dejo de contestar.
#:   inactividad  T18.  La conversacion quedo vieja y llego un mensaje nuevo.
#:   operador     T17.  Una persona la resolvio.
CERRADA_POR = ("cliente", "ia_cliente", "plazo", "inactividad", "operador")

#: Quien figura como actor del evento en cada camino. 'ia_cliente' es
#: 'cliente' y no 'ia' a proposito: el que decide que el caso termino es
#: siempre el cliente al confirmar; lo que cambia entre T15a y T15b es quien
#: estaba atendiendo, y eso ya lo dice 'por'.
_ACTOR_DE = {"cliente": "cliente", "ia_cliente": "cliente",
             "plazo": "sistema", "inactividad": "sistema",
             "operador": "operador"}

#: Los que exigen que una PERSONA elija el desenlace (§3.5: "el cierre manual
#: exige codigo").
_EXIGEN_DESENLACE = ("operador",)


def _acciones_vivas(cur, org, conversation_id) -> tuple[list[str], int]:
    """(ids de las 'pendiente', cuantas 'ejecutando' hay).

    Las dos se cuentan por separado porque se tratan distinto, y la diferencia
    no es de grado. Una 'pendiente' espera a que alguien decida: cerrar la
    conversacion la deja sin destinatario, asi que se cancela. Una 'ejecutando'
    ya salio hacia afuera y su desenlace lo escribe quien la ejecuta o el
    reconciliador (T20c); pisarla con 'cancelada' registraria que no se hizo
    algo que quiza si se hizo -- exactamente lo que X21 prohibe.
    """
    cur.execute(
        """select id, estado from asistente.acciones_propuestas
           where organization_id = %s and conversation_id = %s
             and estado in ('pendiente', 'ejecutando')""",
        (org, conversation_id))
    filas = cur.fetchall()
    return ([str(f["id"]) for f in filas if f["estado"] == "pendiente"],
            sum(1 for f in filas if f["estado"] == "ejecutando"))


def _verificacion_pendiente(cur, org, conversation_id) -> bool:
    cur.execute(
        """select 1 from asistente.verificaciones_accion
           where organization_id = %s and conversation_id = %s
             and estado = 'VERIFICACION_PENDIENTE' limit 1""",
        (org, conversation_id))
    return cur.fetchone() is not None


def cerrar(tenant: str, conversation_id: str, *, por: str,
           desenlace: str | None = None, nota: str | None = None,
           operador_id: str | None = None, operador_nombre: str | None = None,
           config=None, clave: str | None = None) -> Resultado:
    """
    T15a, T15b, T16, T17 y T18: la conversacion termina, y queda dicho por que.

    EL DESENLACE NO SE INFIERE, NUNCA
    ---------------------------------
    Es la regla central de B6 y esta escrita como guarda, no como intencion:

      operador     lo elige una persona. Sin codigo no se cierra (ValueError).
      plazo        'sin_respuesta_cliente' fijo, porque eso es lo que significa
                   que el cliente dejara de contestar. Mandar otro es un error.
      cliente / ia_cliente / inactividad
                   NULL. El cliente dijo "ya quedo" o la conversacion envejecio;
                   ninguna de las dos cosas dice cual era la falla. Mandar un
                   codigo por estos caminos tambien es un error, y por eso se
                   rechaza en vez de guardarse: el unico que podria completarlo
                   es alguien que lo revise despues (§3.5), y eso todavia no
                   tiene transicion definida.

    Deducirlo del veredicto del evaluador seria la tentacion obvia --"resuelta"
    parece un desenlace-- y seria falso: que el cliente diga que ya funciona no
    dice si era la ONT, el WiFi o un corte de fibra. Un dato inventado en una
    tabla que existe para aprender es peor que la columna vacia.

    CERRAR LA CONVERSACION NO ES CERRAR EL CASO NI EL TICKET
    --------------------------------------------------------
    Esto cierra la conversacion de Dexter y nada mas. El caso del CRM y el
    ticket del ISP son sistemas de afuera: se cierran por la cola de efectos
    externos (§3.6) y hoy no tienen ejecutor (ver BLOQUEOS en
    SPEC/auditorias/B6-CIERRE-DESENLACE.md). Un fallo alla NO reabre esto
    (T17), y por eso ninguno de los dos entra en esta transaccion.

    ATOMICO
    -------
    Estado de cierre, desenlace, cancelacion de las acciones pendientes con sus
    eventos, y el evento 'cerrada': todo en la misma transaccion (I12). No
    existe el estado donde la conversacion quedo cerrada y nadie sabe por que.

    En 'datos' del Resultado van 'usuario_externo' y 'canal', que quien llama
    necesita para descartar la sesion en memoria (tambien en legado).
    """
    from nucleo.relevo import desenlaces as catalogo

    if por not in CERRADA_POR:
        raise ValueError(f"'por' desconocido: {por!r}. Son {list(CERRADA_POR)}")

    nombre = usuario = None
    if por == "operador":
        # Un cierre manual sin responsable no se puede auditar, y es el unico
        # camino donde hay alguien a quien atribuirselo.
        nombre, usuario = db.validar_autor(operador_nombre, operador_id)
    elif operador_id or operador_nombre:
        raise ValueError(f"un cierre '{por}' no lo hace un operador")

    nota = (nota or "").strip() or None
    if nota and por != "operador":
        raise ValueError(f"un cierre '{por}' no lleva nota de operador")
    if nota and len(nota) > catalogo.MAX_NOTA:
        raise ValueError(f"la nota supera {catalogo.MAX_NOTA} caracteres")

    codigo = categoria = None
    if por in _EXIGEN_DESENLACE:
        if not (desenlace or "").strip():
            raise ValueError(
                "un cierre manual exige codigo de desenlace (§3.5, T17)")
        codigo, categoria = catalogo.resolver_para_cerrar(desenlace, config)
    elif por == "plazo":
        if desenlace and desenlace != catalogo.POR_PLAZO:
            raise ValueError(
                f"el cierre por plazo es siempre '{catalogo.POR_PLAZO}'")
        codigo, categoria = catalogo.resolver_para_cerrar(
            catalogo.POR_PLAZO, config)
    elif desenlace:
        raise ValueError(
            f"un cierre '{por}' deja el desenlace en NULL (§3.5): nadie eligio "
            f"uno y no se infiere")

    def cuerpo(cur, org, f):
        cur.execute("""select usuario_externo, canal from asistente.conversations
                       where organization_id = %s and id = %s""",
                    (org, conversation_id))
        ident = dict(cur.fetchone())
        gobernada = f["relevo_version"] > 0
        if f["estado"] == "cerrada":
            return Resultado(False, gobernada, f["relevo_version"], None,
                             "ya_cerrada", datos=ident)

        # Los cierres automaticos esperan; el manual no. T15a, T15b, T16 y T18
        # exigen que no haya nada vivo, y T17 dice "de inmediato" a proposito:
        # una persona que decide cerrar no deberia quedar bloqueada por una
        # propuesta que ella misma esta por cancelar.
        pendientes, en_vuelo = _acciones_vivas(cur, org, conversation_id)
        if por != "operador":
            if pendientes or en_vuelo:
                return Resultado(False, gobernada, f["relevo_version"], None,
                                 "accion_viva", datos=ident)
            if _verificacion_pendiente(cur, org, conversation_id):
                return Resultado(False, gobernada, f["relevo_version"], None,
                                 "verificacion_pendiente", datos=ident)

        # T15a contra T15b, decidido con la fila ya bloqueada. Quien llama
        # sabe que el CLIENTE confirmo; lo que no siempre sabe es si alguna
        # persona llego a atenderla, y esa es la unica diferencia entre las dos
        # (§6: T15a exige 'atendida_manual', T15b no). Es un hecho ya escrito,
        # no una inferencia: se lee, no se adivina.
        efectivo = ("ia_cliente" if por == "cliente" and not f["atendida_manual"]
                    else por)

        sets = ["estado = 'cerrada'", "actualizado_en = now()",
                "cerrada_por_tipo = %s"]
        params: list = [efectivo]
        if por == "operador":
            # Hecho historico: alguien actuo. No decide la cola (§3.1).
            sets += ["atendida_manual = true",
                     "atendida_por = coalesce(%s, atendida_por)",
                     "cerrada_por_usuario_id = %s"]
            params += [nombre, usuario]
        if codigo:
            sets += ["desenlace_codigo = %s", "desenlace_categoria_base = %s"]
            params += [codigo, categoria]
        if nota:
            sets.append("desenlace_nota = %s")
            params.append(nota)

        # Las acciones que esperaban una decision se quedaron sin quien la
        # tome. 'cancelada' y no 'rechazada': nadie las evaluo.
        canceladas = 0
        for accion_id in pendientes:
            cur.execute(
                """update asistente.acciones_propuestas
                   set estado = 'cancelada', motivo_rechazo = %s,
                       revisado_por = %s, revisado_en = now()
                   where organization_id = %s and id = %s and estado = 'pendiente'
                   returning id""",
                ("conversacion cerrada", nombre or f"cierre:{por}", org, accion_id))
            if cur.fetchone() is None:
                continue          # otro la resolvio entre la lectura y esto
            canceladas += 1
            # El expediente de una ACCION solo distingue 'operador' y
            # 'sistema' (acciones_eventos): un cierre por confirmacion del
            # cliente no lo cancelo el cliente -- lo cancelo el sistema al
            # cerrar. El quien fino esta en el evento 'cerrada' del relevo.
            db.registrar_evento_de_accion(
                cur, org, accion_id, "accion_cancelada",
                motivo="conversacion cerrada",
                actor_tipo=("operador" if por == "operador" else "sistema"),
                actor_nombre=nombre, conversation_id=conversation_id)

        if not gobernada:
            # Legado (§11): se escribe el cierre y su desenlace --que es un
            # dato de la conversacion, no del relevo-- pero NO entra al modelo.
            # Adoptar una conversacion de version 0 es una decision humana
            # explicita y tiene su propia puerta (adoptar_de_legado, C5/I21):
            # no puede pasar por el efecto lateral de un boton de cerrar.
            cur.execute(
                f"""update asistente.conversations set {', '.join(sets)}
                    where organization_id = %s and id = %s""",
                (*params, org, conversation_id))
            return Resultado(True, False, 0, None, "legado", datos=ident)

        # Libera la asignacion y NO toca el control: cerrar no es devolver.
        version = _subir_version(
            cur, org, conversation_id,
            ", ".join(sets) + ", asignada_a_usuario_id = null, "
            "asignada_a_nombre = null, asignada_en = null", tuple(params))
        datos = {"version": version, "por": efectivo}
        if codigo:
            datos["desenlace"] = codigo
            datos["categoria"] = categoria
        if nota:
            datos["nota"] = nota
        if canceladas:
            datos["acciones_canceladas"] = canceladas
        if en_vuelo:
            # Queda escrito que al cerrar habia algo afuera sin desenlace. Es
            # lo que despues explica una sincronizacion 'desconocida' en una
            # conversacion que ya nadie mira.
            datos["acciones_en_vuelo"] = en_vuelo
        ev = _evento(cur, org, conversation_id, "cerrada", _ACTOR_DE[por],
                     usuario, nombre, datos, clave)
        return Resultado(True, True, version, ev, datos={**ident, **datos})

    return _ejecutar(tenant, conversation_id, clave, cuerpo, tipo="cerrada",
                     actor_id=usuario)


def resolver(tenant: str, conversation_id: str, *, operador_id: str, operador_nombre: str,
             desenlace: str, nota: str | None = None, config=None,
             clave: str | None = None) -> Resultado:
    """T17: una persona resuelve y cierra. El desenlace es obligatorio."""
    return cerrar(tenant, conversation_id, por="operador", desenlace=desenlace,
                  nota=nota, operador_id=operador_id,
                  operador_nombre=operador_nombre, config=config, clave=clave)


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


def solicitar_devolucion(tenant: str, conversation_id: str, contenido: str, *,
                         operador_id: str, operador_nombre: str,
                         clave: str) -> dict | None:
    """T6 paso 1: mensaje + intención, sin cambiar control ni asignación."""
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)
    if not (clave or "").strip():
        raise ValueError("T6 necesita clave de idempotencia")
    with db.sesion(tenant) as (cur, org):
        fila = _fila(cur, org, conversation_id)
        if fila is None:
            return None
        if regla_control.control_efectivo(fila) != "humano" or fila["estado"] != "abierta":
            raise RuntimeError("la conversación no está bajo control humano")
        cur.execute(
            """select canal, usuario_externo, ticket_operativo
               from asistente.conversations
               where organization_id = %s and id = %s""", (org, conversation_id))
        destino = cur.fetchone()
        cur.execute(
            """insert into asistente.messages
                 (organization_id, conversation_id, rol, contenido, estado_entrega,
                  origen, autor_usuario_id, autor_nombre, clave_idempotencia)
               values (%s, %s, 'assistant', %s, %s, 'humano', %s, %s, %s)
               on conflict (organization_id, conversation_id, clave_idempotencia)
                 where clave_idempotencia is not null do nothing returning id""",
            (org, conversation_id, contenido,
             "pendiente" if destino["canal"] == "whatsapp" else None,
             usuario, nombre, clave))
        nueva = cur.fetchone()
        if not nueva:
            cur.execute(
                """select id, estado_entrega from asistente.messages
                   where organization_id = %s and conversation_id = %s
                     and clave_idempotencia = %s""", (org, conversation_id, clave))
            previa = cur.fetchone()
            return {**dict(destino), "mensaje_id": previa["id"], "existente": True,
                    "estado_entrega": previa["estado_entrega"]}
        mensaje_id = str(nueva["id"])
        cur.execute(
            """update asistente.conversations
               set actualizado_en = now(), atendida_manual = true,
                   atendida_por = coalesce(nullif(%s, ''), atendida_por)
               where organization_id = %s and id = %s""", (nombre, org, conversation_id))
        _evento(cur, org, conversation_id, "devolucion_solicitada", "operador",
                usuario, nombre, {"mensaje_id": mensaje_id}, f"solicitar:{clave}")
        return {**dict(destino), "mensaje_id": mensaje_id, "existente": False,
                "estado_entrega": "pendiente" if destino["canal"] == "whatsapp" else None}


def registrar_devolucion_fallida(tenant: str, conversation_id: str, mensaje_id: str, *,
                                 operador_id: str, operador_nombre: str,
                                 resultado: str, clave: str) -> Resultado:
    """T6 paso 3 fallido: deja evidencia sin soltar control ni asignación."""
    nombre, usuario = db.validar_autor(operador_nombre, operador_id)

    def cuerpo(cur, org, f):
        datos = {"mensaje_id": str(mensaje_id), "resultado": resultado}
        ev = _evento(cur, org, conversation_id, "devolucion_fallida", "operador",
                     usuario, nombre, datos, clave)
        return Resultado(True, f["relevo_version"] > 0, f["relevo_version"], ev, datos=datos)
    return _ejecutar(tenant, conversation_id, clave, cuerpo,
                     tipo="devolucion_fallida", actor_id=usuario)


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
