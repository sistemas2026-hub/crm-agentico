# -*- coding: utf-8 -*-
"""
================================================================================
 EL TECHO DE AUTONOMIA  --  M06-B, 21/09/2026
================================================================================

QUE ES, Y QUE NO ES
-------------------
El kill switch (interruptor.py) contesta "¿esta empresa puede actuar sola?", y
contesta si o no. Este modulo contesta "¿HASTA QUE NIVEL?". Es el mismo techo
que ya existia en asistente.nivel_autonomia (Autonomia 2), con dos cambios:

  1. se consulta como PASO PROPIO de la frontera, justo despues del kill
     switch -- antes estaba escondido adentro de la autorizacion granular;
  2. es la UNICA lectura del techo: autorizacion.py lo lee de aca, asi que las
     dos capas no pueden ver techos distintos.

EL TECHO ACOTA, NUNCA AUTORIZA. Una accion que pasa el techo todavia tiene que
pasar la etapa, la autorizacion granular, la aprobacion humana si es
irreversible, la idempotencia y el ultimo metro. Un techo 3 no ejecuta nada
por si solo.

LOS NIVELES
-----------
  0  OBSERVAR              ve, analiza, propone. Ningun efecto.
  1  RECOMENDAR            recomienda; toda ejecucion la hace una persona.
  2  COORDINAR             coordinacion operativa de bajo riesgo, autorizada.
  3  EJECUTAR AUTORIZADO   acciones reversibles y previamente autorizadas.

Es la escala de M09-J (operaciones.PropuestaSupervisor), que ademas define un
4 -- "accion critica, siempre humano". El 4 NO es un techo que se pueda fijar:
lo critico (R3/R4) lo gobierna su gate propio (frontera.critica), no un
numero. Por eso TECHO_MAXIMO_POLITICA es 3, y un techo guardado por encima de
eso se lee como INVALIDO, no como "todavia mas permiso".

FALLA CERRADO, SIN NIVEL POR DEFECTO
------------------------------------
Hasta M06-B, "no hay fila" se leia como nivel 0. En la practica bloqueaba
(toda escritura pide 2), pero era un valor ASUMIDO. Ahora cada caso tiene su
codigo y todos bloquean: ausente, invalido, ilegible, sin instalar, de otra
empresa. Ninguno se convierte en un numero.

QUIEN LO MUEVE
--------------
Nadie desde el runtime. 'cambiar()' escribe como 'autonomia_operador' (la
identidad separada del paso 10.12), y la base no le da INSERT a 'app_backend'.
Ademas 'cambiar()' se niega:
  - si hay una accion en curso (un permiso de la frontera abierto): una
    herramienta, una aprobacion o un agente ejecutando no pueden subir el
    techo bajo el que se estan ejecutando;
  - si el origen no es un canal de operador ('cli:');
  - si el actor es una identidad del sistema;
  - si el nivel pasa el tope de politica;
  - si el nivel anterior no es el que el operador vio (compare-and-set).
Cada intento, aplicado o no, queda en asistente.techo_autonomia_intentos.

LIMITE, DICHO ACA: 'actor' y 'origen' los declara quien llama. Lo que los
vuelve confiables no es este modulo: es que solo la CLI de operador llega a
'cambiar()' (tests/test_m06b_techo_autonomia.py lo comprueba por AST) y que
solo 'autonomia_operador' puede escribir el techo en la base.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar  # noqa: E402

from dataclasses import dataclass

from nucleo.persistencia import db as persistencia

OBSERVAR = 0
RECOMENDAR = 1
COORDINAR = 2
EJECUTAR_AUTORIZADO = 3
NOMBRES = {OBSERVAR: "observar", RECOMENDAR: "recomendar",
           COORDINAR: "coordinar", EJECUTAR_AUTORIZADO: "ejecutar autorizado"}

#  La politica GLOBAL: ninguna empresa puede fijar un techo por encima. Es una
#  constante del nucleo y no un dato del tenant a proposito -- si viviera en
#  la config de la empresa, la empresa podria subirla.
TECHO_MAXIMO_POLITICA = EJECUTAR_AUTORIZADO

#  Lo que exige una escritura que no declara su nivel. Es el mismo 2 que la
#  autorizacion granular exigia a todas antes de M06-B: no se reasigna nada.
NIVEL_ESCRITURA_POR_DEFECTO = COORDINAR
#  Ninguna escritura puede exigir menos que esto: el nivel 0 no produce
#  efectos, por definicion.
NIVEL_MINIMO_ESCRITURA = RECOMENDAR

#  Canales de operador. Hoy existe uno: la CLI (cli/autonomia.py).
ORIGENES_DE_OPERADOR = ("cli:",)

#  Identidades del sistema: nunca pueden figurar como quien cambia el techo.
ACTORES_DEL_SISTEMA = ("motor", "sistema", "agente", "supervisor", "asistente",
                       "modelo", "frontera", "aprobacion", "propuesta",
                       "reloj", "scheduler", "servicio", "herramienta",
                       "evento:", "turno:", "accion_aprobada:", "invocacion:")

# Codigos de bloqueo. Viajan a la traza como bloqueo, no como error.
AUSENTE = "TECHO_AUTONOMIA_AUSENTE"
INVALIDO = "TECHO_AUTONOMIA_INVALIDO"
NO_LEGIBLE = "TECHO_AUTONOMIA_NO_LEGIBLE"
NO_INSTALADO = "TECHO_AUTONOMIA_NO_INSTALADO"
OTRO_TENANT = "TECHO_AUTONOMIA_DE_OTRO_TENANT"
INSUFICIENTE = "TECHO_AUTONOMIA_INSUFICIENTE"
REQUERIDO_INVALIDO = "NIVEL_REQUERIDO_INVALIDO"

# Codigos de un cambio rechazado.
CAMBIO_DESDE_UNA_ACCION = "CAMBIO_DE_TECHO_DESDE_UNA_ACCION"
CAMBIO_ORIGEN_NO_OPERADOR = "CAMBIO_DE_TECHO_ORIGEN_NO_OPERADOR"
CAMBIO_ACTOR_DEL_SISTEMA = "CAMBIO_DE_TECHO_ACTOR_DEL_SISTEMA"
CAMBIO_SIN_MOTIVO = "CAMBIO_DE_TECHO_SIN_MOTIVO"
CAMBIO_FUERA_DE_POLITICA = "CAMBIO_DE_TECHO_FUERA_DE_POLITICA"
CAMBIO_SIN_TENANT = "CAMBIO_DE_TECHO_SIN_TENANT"
CAMBIO_CONFLICTO = "CAMBIO_DE_TECHO_CONFLICTO"


@dataclass(frozen=True)
class Veredicto:
    permitido: bool
    codigo: str
    motivo: str
    techo: int | None = None
    requerido: int | None = None


class CambioRechazado(Exception):
    """Un intento de mover el techo que no se aplico. Lleva su codigo."""

    def __init__(self, codigo: str, motivo: str):
        self.codigo = codigo
        self.motivo = motivo
        super().__init__(f"{codigo}: {motivo}")


def _es_nivel(valor) -> bool:
    #  bool es subclase de int en Python: True no es un nivel.
    return (isinstance(valor, int) and not isinstance(valor, bool)
            and OBSERVAR <= valor <= TECHO_MAXIMO_POLITICA)


def _tenant_valido(tenant) -> bool:
    return isinstance(tenant, str) and bool(tenant.strip())


def leer(tenant: str) -> tuple[int | None, Veredicto | None]:
    """
    El techo vigente de la empresa, o (None, bloqueo). Nunca un nivel asumido.
    """
    if not _tenant_valido(tenant):
        return None, Veredicto(False, OTRO_TENANT,
                               "sin empresa no hay techo que leer")
    try:
        fila = persistencia.nivel_autonomia(tenant)
    except BaseException as e:                                   # noqa: BLE001
        from nucleo.seguridad import interruptor
        if interruptor.tabla_ausente(e):
            return None, Veredicto(False, NO_INSTALADO,
                                   "el registro del techo de autonomia no esta "
                                   "instalado")
        registrar("techo", "no se pudo leer el techo: se BLOQUEA", tenant=tenant, error=e)
        return None, Veredicto(False, NO_LEGIBLE,
                               f"no se pudo leer el techo: {type(e).__name__}")
    if not fila:
        return None, Veredicto(False, AUSENTE,
                               "esta empresa no tiene techo de autonomia fijado; "
                               "sin techo no se ejecuta nada solo")
    #  La fila tiene que ser de la empresa que se pregunto. La consulta ya
    #  filtra y la RLS tambien -- esto es la tercera capa, y la unica que no
    #  depende de que las otras dos esten bien escritas.
    org_fila = str(fila.get("organization_id") or "")
    org_pedida = str(fila.get("org_consultada") or "")
    if not org_fila or not org_pedida or org_fila != org_pedida:
        return None, Veredicto(False, OTRO_TENANT,
                               "la fila de techo no pertenece a esta empresa")
    nivel = fila.get("nivel")
    if not _es_nivel(nivel):
        return None, Veredicto(False, INVALIDO,
                               f"techo guardado invalido ({nivel!r}): tiene que "
                               f"ser un entero entre {OBSERVAR} y "
                               f"{TECHO_MAXIMO_POLITICA}")
    return nivel, None


def nivel_requerido_de(herramienta) -> int:
    """
    El nivel que exige una herramienta. Lo declara el catalogo
    ('Herramienta.nivel_autonomia'); si no, 0 para una lectura y el mismo 2 de
    siempre para una escritura. Nunca sale de los argumentos de la llamada.
    """
    explicito = getattr(herramienta, "nivel_autonomia", None)
    if explicito is not None:
        return explicito
    if getattr(herramienta, "solo_lectura", True):
        return OBSERVAR
    return NIVEL_ESCRITURA_POR_DEFECTO


def veredicto(tenant: str, nivel_requerido) -> Veredicto:
    """¿El techo de ESTA empresa alcanza para una accion de ESE nivel?"""
    if not _es_nivel(nivel_requerido):
        return Veredicto(False, REQUERIDO_INVALIDO,
                         f"nivel requerido invalido ({nivel_requerido!r})")
    techo, fallo = leer(tenant)
    if fallo is not None:
        return Veredicto(fallo.permitido, fallo.codigo, fallo.motivo,
                         requerido=nivel_requerido)
    if techo < nivel_requerido:
        return Veredicto(False, INSUFICIENTE,
                         f"la accion exige nivel {nivel_requerido} "
                         f"({NOMBRES[nivel_requerido]}) y el techo de la empresa "
                         f"es {techo} ({NOMBRES[techo]})",
                         techo=techo, requerido=nivel_requerido)
    return Veredicto(True, "techo_suficiente",
                     f"techo {techo} >= {nivel_requerido}",
                     techo=techo, requerido=nivel_requerido)


def cambiar(tenant: str, nivel_nuevo, *, actor: str, motivo: str,
            origen: str, anterior_esperado) -> dict:
    """
    Mueve el techo. Solo la CLI de operador llega aca.

    'anterior_esperado' es el techo que el operador VIO antes de pedir el
    cambio (None si no habia). Si entretanto cambio, no se aplica: dos
    operadores que suben y bajan a la vez no pueden dejar un historial que
    diga "de 1 a 3" cuando lo que habia era 2.

    Devuelve la fila del intento. Levanta CambioRechazado si no se aplico
    (el intento igual queda auditado).
    """
    actor = (actor or "").strip()
    motivo = (motivo or "").strip()
    origen = (origen or "").strip()

    def _rechazar(codigo: str, explicacion: str):
        _auditar_rechazo(tenant, nivel_nuevo, anterior_esperado, actor, motivo,
                         origen, codigo)
        raise CambioRechazado(codigo, explicacion)

    if not _tenant_valido(tenant):
        raise CambioRechazado(CAMBIO_SIN_TENANT,
                              "un cambio de techo sin empresa no se aplica")

    #  Ninguna accion en curso puede mover el techo bajo el que corre. Import
    #  adentro: frontera importa este modulo.
    from nucleo.seguridad import frontera
    if frontera.permiso_vigente() is not None:
        _rechazar(CAMBIO_DESDE_UNA_ACCION,
                  "hay una accion en ejecucion (permiso de la frontera abierto); "
                  "el techo no se mueve desde adentro de una accion")
    if not origen.startswith(ORIGENES_DE_OPERADOR):
        _rechazar(CAMBIO_ORIGEN_NO_OPERADOR,
                  f"el techo solo se mueve desde un canal de operador "
                  f"{ORIGENES_DE_OPERADOR}, no desde '{origen or '(vacio)'}'")
    if not actor or actor.lower().startswith(ACTORES_DEL_SISTEMA):
        _rechazar(CAMBIO_ACTOR_DEL_SISTEMA,
                  f"'{actor or '(vacio)'}' no es una persona: el techo lo mueve "
                  f"un operador con nombre")
    if not motivo:
        _rechazar(CAMBIO_SIN_MOTIVO, "hay que decir POR QUE se mueve el techo")
    if not _es_nivel(nivel_nuevo):
        _rechazar(CAMBIO_FUERA_DE_POLITICA,
                  f"nivel {nivel_nuevo!r} fuera de la politica: entre "
                  f"{OBSERVAR} y {TECHO_MAXIMO_POLITICA}")
    if anterior_esperado is not None and not _es_nivel(anterior_esperado):
        _rechazar(CAMBIO_FUERA_DE_POLITICA,
                  f"nivel anterior esperado invalido ({anterior_esperado!r})")

    resultado = persistencia.registrar_cambio_techo(
        tenant, nivel_nuevo, anterior_esperado, actor, motivo, origen)
    if resultado.get("resultado") == "conflicto":
        raise CambioRechazado(
            CAMBIO_CONFLICTO,
            f"el techo cambio mientras tanto: se esperaba "
            f"{anterior_esperado!r} y hay {resultado.get('nivel_anterior')!r}. "
            f"Volver a leerlo y decidir de nuevo.")
    return resultado


def _auditar_rechazo(tenant, nivel_nuevo, anterior_esperado, actor, motivo,
                     origen, codigo) -> None:
    """Un intento rechazado tambien queda. Nunca tumba el rechazo."""
    try:
        persistencia.registrar_intento_techo(
            tenant, nivel_solicitado=(nivel_nuevo if _es_nivel(nivel_nuevo)
                                      else None),
            nivel_anterior=(anterior_esperado if _es_nivel(anterior_esperado)
                            else None),
            actor=actor or "(vacio)", motivo=motivo, origen=origen or "(vacio)",
            resultado="rechazado", codigo=codigo)
    except BaseException as e:                                   # noqa: BLE001
        registrar("techo", "no se pudo auditar el rechazo", tenant=tenant,
                  codigo=codigo, error=e)


def historial(tenant: str, limite: int = 50) -> list[dict]:
    return persistencia.historial_techo(tenant, limite)
