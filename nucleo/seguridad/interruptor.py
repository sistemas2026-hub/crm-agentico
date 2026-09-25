# -*- coding: utf-8 -*-
"""
================================================================================
 EL INTERRUPTOR DE AUTONOMIA  --  detener al agente sin apagar el asistente
================================================================================

QUE DETIENE Y QUE NO
--------------------
Detenido, la empresa deja de tener acciones AUTONOMAS:

  * ninguna escritura contra un sistema externo decidida por el modelo
    (reiniciar una ONT, activar CATV, cambiar el tipo de ONU, crear un ticket);
  * ningun trabajo del scheduler para ese tenant;
  * ningun reintento de lo anterior.

Sigue andando todo lo demas, y eso es parte del diseño, no una concesion:

  * las consultas de lectura, con sus permisos de siempre;
  * lo que un humano aprueba explicitamente (Herramienta.aprobacion_humana:
    proponer una accion no la ejecuta, y aprobarla despues es un acto de una
    persona, no del agente);
  * la conversacion entera -- el cliente sigue siendo atendido.

Un interruptor que apaga el asistente completo no se usa nunca, porque el
costo de usarlo es dejar a los clientes sin atencion. Este se puede tirar un
martes a las tres de la tarde.

FAIL-CLOSED, Y QUE SIGNIFICA EXACTAMENTE
----------------------------------------
Dos resultados permiten o bloquean por lo que dice el registro; todo lo demas
bloquea porque NO SE SABE. La ausencia de control nunca es autorizacion:

  la fila dice 'activo'       PERMITE. Alguien lo autorizo explicitamente.
  la fila dice 'detenido'     BLOQUEA. Es para lo que existe.
  no se pudo LEER la fila     BLOQUEA ('desconocido'). Si un error de base se
                              tradujera en "segui", cortar la base seria la
                              forma de saltear el interruptor.
  no HAY fila                 BLOQUEA ('sin_registro'). Un tenant sin registro
                              de autonomia esta a medias de darse de alta.
  la tabla NO EXISTE          BLOQUEA ('sin_instalar').

SOBRE ESE ULTIMO CASO  --  corregido el 17/09/2026 (paso 10.10)
---------------------------------------------------------------
Hasta esa fecha, "la tabla no existe" PERMITIA, con este argumento: es el
unico caso en que se sabe con certeza que nadie pudo tirar el interruptor
todavia, y sin eso desplegar el codigo antes que la migracion apagaria la
operacion de golpe.

El argumento era coherente y aun asi estaba mal, por dos razones:

  1. Convierte "el control no esta instalado" en "esta autorizado", que es
     exactamente la inversion que un mecanismo de seguridad no puede hacer.
     Una base restaurada sin esa migracion -- el escenario que el propio
     procedimiento de respaldo contempla -- quedaba con la autonomia
     permitida sin que nadie lo decidiera.
  2. Su premisa era "el codigo va antes que la migracion". Se puede invertir,
     y se invirtio: las migraciones van primero, y recien despues el codigo
     que las consulta. Con ese orden este caso no se alcanza nunca en
     operacion normal -- y si se alcanza, es justo la señal de que algo falta.

Medido antes de cambiarlo: con la tabla ausente, 'veredicto()' devolvia
permitido=True y el modulo de idempotencia llegaba a ejecutar la llamada
externa. Ver PASO10.9 y PASO10.10.

NO SE CACHEA. NUNCA
-------------------
Cada evaluacion va a la base. Es una consulta por indice que devuelve una fila,
y solo corre antes de una accion de escritura -- que son raras. El precio de
cachearlo es que alguien tire el interruptor y el agente siga ejecutando N
segundos mas, que es justo el escenario para el que se tira.

Ese es tambien el motivo por el que esto NO vive en 'asistente.tenant_config':
esa ruta se sirve cacheada y cae al YAML de la imagen cuando la base no
responde. El detalle completo esta en la migracion
supabase/202609151710_interruptor_autonomia.sql.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar  # noqa: E402

from dataclasses import dataclass

from nucleo.persistencia import db as persistencia

ACTIVO = "activo"
DETENIDO = "detenido"
ESTADOS = (ACTIVO, DETENIDO)

# Estados que no salen de una fila: los produce este modulo cuando no puede
# afirmar que la autonomia este permitida. TODOS bloquean.
SIN_REGISTRO = "sin_registro"      # la tabla existe, esta empresa no tiene fila
DESCONOCIDO = "desconocido"        # no se pudo leer: caida, timeout, permiso
SIN_INSTALAR = "sin_instalar"      # la tabla no existe: falta la migracion

# El control no esta disponible. Se distingue de DETENIDO --que es una decision
# tomada-- porque se lee distinto en la traza y se arregla distinto, pero las
# dos impiden lo mismo.
ESTADOS_SIN_CONTROL = (SIN_REGISTRO, DESCONOCIDO, SIN_INSTALAR)

# Viaja a la traza como bloqueo, no como error: es la proteccion funcionando.
# Se agrega a motor.CODIGOS_DE_BLOQUEO, igual que los otros gates.
CODIGO_BLOQUEO = "AUTONOMIA_DETENIDA"


@dataclass(frozen=True)
class Veredicto:
    """Si esta empresa puede ejecutar acciones autonomas ahora mismo."""
    permitido: bool
    estado: str
    motivo: str
    actor: str = ""

    def __bool__(self) -> bool:                      # noqa: D105
        return self.permitido


def tabla_ausente(e: BaseException) -> bool:
    """
    Si el fallo es 'esa tabla no existe' y no otra cosa.

    Se mira por nombre de clase y por el SQLSTATE 42P01, sin importar psycopg
    aca: este modulo lo importan pruebas que corren sin base, y cargar el
    driver para clasificar un error seria pedirle una dependencia a quien no la
    necesita. El texto del mensaje NO se usa -- cambia entre versiones y entre
    idiomas del servidor.
    """
    if getattr(e, "sqlstate", None) == "42P01":
        return True
    return type(e).__name__ in ("UndefinedTable", "UndefinedTableError")


def _leer(consulta, etiqueta: str) -> Veredicto:
    """El nucleo del veredicto: una lectura, y las cuatro salidas de arriba."""
    try:
        fila = consulta()
    except BaseException as e:                                   # noqa: BLE001
        if tabla_ausente(e):
            # Falta supabase/202609151710_interruptor_autonomia.sql: sin el
            # registro instalado no hay forma de saber si alguien la autorizo.
            registrar("interruptor", "tabla no instalada: se BLOQUEA la accion autonoma",
                      tenant=etiqueta)
            return Veredicto(False, SIN_INSTALAR,
                             "el interruptor todavia no esta instalado")
        registrar("interruptor", "no se pudo leer: se BLOQUEA la accion autonoma",
                  tenant=etiqueta, error=e)
        return Veredicto(False, DESCONOCIDO,
                         f"no se pudo leer el interruptor: {type(e).__name__}")

    if not fila:
        return Veredicto(False, SIN_REGISTRO,
                         "esta empresa no tiene interruptor registrado")

    estado = fila["estado"]
    if estado == ACTIVO:
        return Veredicto(True, ACTIVO, "autonomia permitida",
                         fila.get("actor") or "")
    return Veredicto(False, DETENIDO,
                     (fila.get("motivo") or "").strip() or "sin motivo declarado",
                     fila.get("actor") or "")


def veredicto(tenant: str) -> Veredicto:
    """Si el tenant (por slug) puede ejecutar acciones autonomas ahora."""
    return _leer(lambda: persistencia.estado_autonomia(tenant), tenant)


def veredicto_de_organizacion(organization_id: str) -> Veredicto:
    """
    Igual, pero por organizacion. Lo usa el coordinador del scheduler, que
    recibe 'organization_id' y no el slug (ver nucleo/programador/puerta.py).
    """
    return _leer(
        lambda: persistencia.estado_autonomia_de_organizacion(organization_id),
        f"org {organization_id}")


def es_accion_autonoma(herramienta, aprobada_por_humano: bool = False) -> bool:
    """
    Si ejecutar esta herramienta aqui y ahora cuenta como accion autonoma.

    Dos condiciones, y las dos son necesarias:

      escribe          'solo_lectura=False'. Una consulta no es una accion:
                       detener la autonomia no puede dejar ciego al que
                       atiende.
      sin un humano    nadie la aprobo explicitamente. 'ejecutar_accion_
                       aprobada' pasa aprobada_por_humano=True: ahi la decision
                       la tomo una persona y el interruptor no la revoca.

    Se mira 'solo_lectura' y no 'requiere_confirmacion' a proposito: ese campo
    lo pone el validador en TODA herramienta de escritura para poder guardarse,
    y nunca se evaluo en ejecucion (ver el comentario de aprobacion_humana en
    nucleo/config/schema.py). Usarlo aca lo convertiria en algo que nadie
    decidio que fuera.
    """
    if aprobada_por_humano:
        return False
    return not getattr(herramienta, "solo_lectura", True)


def detener(tenant: str, actor: str, motivo: str) -> dict:
    """
    Tira el interruptor. Devuelve la transicion escrita.

    'actor' y 'motivo' son obligatorios y no tienen default: una parada de
    emergencia sin nombre ni razon es la que despues nadie sabe si puede
    levantar.
    """
    return _mover(tenant, DETENIDO, actor, motivo)


def reactivar(tenant: str, actor: str, motivo: str) -> dict:
    """Levanta el interruptor. Mismos requisitos que detener()."""
    return _mover(tenant, ACTIVO, actor, motivo)


def _mover(tenant: str, destino: str, actor: str, motivo: str) -> dict:
    if destino not in ESTADOS:
        raise ValueError(f"estado desconocido: {destino!r}")
    if not (actor or "").strip():
        raise ValueError("hay que decir QUIEN mueve el interruptor")
    if not (motivo or "").strip():
        raise ValueError("hay que decir POR QUE se mueve el interruptor")

    previo = veredicto(tenant)
    # 'estado_anterior' solo se declara cuando se leyo de verdad. Si el
    # interruptor no se pudo leer, anotar un estado inventado ensuciaria el
    # historial justo en el momento en que hay que confiar en el.
    anterior = previo.estado if previo.estado in ESTADOS else None

    fila = persistencia.registrar_transicion_autonomia(
        tenant, destino, anterior, actor.strip(), motivo.strip())

    # La misma transicion tambien va al registro de autorizacion, que es donde
    # se lee la linea de tiempo de seguridad completa (las paradas y las
    # denegaciones juntas). El detalle --el motivo-- vive en la tabla del
    # interruptor; aca queda el hecho.
    persistencia.registrar_auditoria(
        tenant, actor=actor.strip(),
        accion=("autonomia_detenida" if destino == DETENIDO
                else "autonomia_reactivada"),
        recurso=f"autonomia:{tenant}", resultado="permitido")
    return fila


def sembrar(cur, organization_id: str, actor: str, motivo: str) -> bool:
    """
    El interruptor inicial de una empresa que se acaba de dar de alta. Devuelve
    True si escribio la fila, False si ya habia una.

    RECIBE UN CURSOR, NO ABRE SESION  --  y es el punto entero
    ----------------------------------------------------------
    Se llama desde cli/cargar_config.py DENTRO de la transaccion que crea la
    fila de asistente.tenant_config, para que las dos escrituras sean una sola
    cosa: si esta falla, el alta del tenant se deshace con ella. No puede
    existir un tenant valido sin registro de autonomia, y la unica forma de
    garantizarlo es que compartan el commit -- no un segundo paso que alguien
    tenga que acordarse de correr.

    Es el mismo patron que editor.anotar_version(cur, org, version, datos),
    que vive justo al lado en ese archivo y por el mismo motivo.

    NO ATRAPA NADA, a proposito. Un fallo tiene que subir y tumbar la
    transaccion; tragarlo dejaria exactamente el tenant a medias que esta
    funcion existe para impedir.

    NACE DETENIDO  --  decision de politica, no de implementacion
    -------------------------------------------------------------
    Crear un tenant no equivale a autorizar que su agente actue solo.

    La fila semilla de la migracion decia 'activo' hasta el 17/09/2026 y ahora
    dice 'detenido' tambien: hay UNA sola regla, sin casos especiales. El
    argumento para la excepcion --"esas empresas ya operaban, apagarlas seria un
    cambio que nadie pidio"-- resulto apoyarse en una premisa falsa: el commit
    desplegado no consulta el interruptor en ningun archivo, asi que sembrar
    'detenido' no apaga nada. Ver supabase/202609151710_interruptor_autonomia.sql
    y PASO10.10.

    Levantarlo es un acto explicito y queda registrado como cualquier otro:

        py -3.13 cli/autonomia.py <slug> --reactivar --actor "..." --motivo "..."

    NO DUPLICA
    ----------
    El 'where not exists' hace que correr el alta otra vez sobre una empresa
    que ya tiene interruptor no escriba nada -- ni siquiera si alguien la
    ejecuta a mano. El alta ocurre una vez; lo que pase despues con el
    interruptor son transiciones, y esas las escribe detener()/reactivar().
    """
    cur.execute(
        """insert into asistente.interruptor_autonomia
             (organization_id, estado, estado_anterior, actor, motivo)
           select %s, %s, null, %s, %s
            where not exists (select 1 from asistente.interruptor_autonomia
                               where organization_id = %s)""",
        (organization_id, DETENIDO, actor, motivo, organization_id))
    return cur.rowcount > 0


def historial(tenant: str, limite: int = 50) -> list[dict]:
    """Todas las veces que se movio, lo mas reciente primero."""
    return persistencia.historial_autonomia(tenant, limite)


def anotar_bloqueo(tenant: str, actor: str, recurso: str, motivo: str) -> None:
    """
    Deja constancia de una accion que el interruptor freno.

    Va a asistente.audit_log y no a asistente.tool_calls porque una accion
    autonoma puede no tener conversacion -- el scheduler no la tiene. Ver
    registrar_auditoria() en nucleo/persistencia/db.py.
    """
    persistencia.registrar_auditoria(
        tenant, actor=actor, accion="accion_autonoma_bloqueada",
        recurso=recurso, resultado="denegado", motivo_denegacion=motivo)
