"""
================================================================================
 AUTORIZACION GRANULAR POR HERRAMIENTA  --  Autonomia 2
================================================================================

QUE PREGUNTA CONTESTA, Y CUAL NO
--------------------------------
El kill switch contesta "¿esta empresa puede actuar sola?". Este modulo
contesta otra: "¿puede hacer ESTO, ahora, hasta que nivel?". Son preguntas
distintas y hasta hoy la segunda se deducia de la primera -- o sea que
autorizar la autonomia autorizaba las veintisiete escrituras del catalogo de
una vez.

TRES COSAS QUE NO SON ESTO
--------------------------
1. NO es 'tenant_config.requiere_confirmacion'. Esa bandera es una preferencia
   de producto ("preguntale al usuario antes"), viaja en la config cacheada y
   -- medido el 15/09/2026 -- esa ruta falla ABIERTA por dos caminos. Una
   autorizacion que se pueda perder por un cache vencido no es una
   autorizacion.
2. NO es el nivel global. El nivel es un TECHO: acota, nunca habilita. Una
   empresa en nivel 4 sin autorizaciones no ejecuta nada.
3. NO es una cola. Autorizar no agenda trabajo; la unica agenda sigue siendo
   operaciones.PropuestaSupervisor.

FALLA CERRADO, Y SIN CACHE
--------------------------
Misma decision que el interruptor, por el mismo motivo medido: si no se puede
leer la autorizacion, no se ejecuta. "No se pudo comprobar" no es "adelante".
Y se lee sin cache antes de cada efecto -- un permiso revocado tiene que dejar
de valer cuando se revoca, no cuando expire un TTL.

EL TECHO Y LA AUTORIZACION SE CRUZAN CON EL MENOR
-------------------------------------------------
nivel_efectivo = min(techo de la empresa, nivel de la autorizacion). Asi bajar
el techo desactiva todo sin borrar nada, y revocar una herramienta no obliga a
tocar a las demas.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar  # noqa: E402

from dataclasses import dataclass, field
from datetime import datetime, timezone

from nucleo.persistencia import db as persistencia

# Motivos de bloqueo. Viajan a la bitacora y a la traza, no como error.
SIN_AUTORIZACION = "HERRAMIENTA_SIN_AUTORIZACION"
REVOCADA = "AUTORIZACION_REVOCADA"
EXPIRADA = "AUTORIZACION_EXPIRADA"
AUN_NO_VIGENTE = "AUTORIZACION_AUN_NO_VIGENTE"
NIVEL_INSUFICIENTE = "NIVEL_AUTONOMIA_INSUFICIENTE"
DESCONOCIDO = "AUTORIZACION_DESCONOCIDA"
SIN_INSTALAR = "AUTORIZACION_NO_INSTALADA"
#  RESERVADO, NO USADO (medido el 19/09/2026). Ningun camino lo devuelve
#  todavia porque 'limites' es METADATA: se guarda y se transporta, no se
#  evalua. Existe para el dia que se implemente, y se deja dicho aca para que
#  nadie lo lea como si ya hubiera un control detras.
LIMITE_EXCEDIDO = "LIMITE_DE_AUTORIZACION_EXCEDIDO"

#  Sin fila de nivel, la empresa esta en 0. No es un default arbitrario: 0 es
#  "observar", el unico nivel que no produce ningun efecto.
NIVEL_POR_OMISION = 0

#  Autonomia 2 es el minimo para ejecutar una accion previamente autorizada.
NIVEL_EJECUCION = 2


@dataclass(frozen=True)
class Veredicto:
    """El resultado de preguntar por UNA herramienta en UNA empresa."""
    permitido: bool
    codigo: str
    motivo: str
    nivel_efectivo: int = 0
    nivel_techo: int = 0
    nivel_autorizado: int = 0
    autorizacion_id: str = ""
    autorizado_por: str = ""
    #  METADATA, NO CONTROL (medido el 19/09/2026). Se lee de la fila y se
    #  transporta hasta aca, y NADIE lo evalua: un {"por_dia": 20} no limita
    #  nada hoy. Se conserva porque describe la intencion de quien autorizo y
    #  porque el dia que se implemente el dato ya va a estar; decir que
    #  "protege" la ejecucion seria falso. Lo comprueba
    #  tests/test_autonomia2_preactivacion.py.
    limites: dict = field(default_factory=dict)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _a_utc(valor):
    """Una fecha de la base puede venir naive si alguien la escribio sin zona."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor


def _tabla_ausente(e: BaseException) -> bool:
    #  Se reusa la del interruptor a proposito: si las dos capas discreparan
    #  sobre que cuenta como "falta la migracion", una bloquearia y la otra no.
    from nucleo.seguridad import interruptor
    return interruptor.tabla_ausente(e)


def _leer(consulta, etiqueta: str, que: str):
    """Una lectura, y el mismo reparto de salidas que usa el interruptor."""
    try:
        return consulta(), None
    except BaseException as e:                                   # noqa: BLE001
        if _tabla_ausente(e):
            # Sin el registro instalado no hay forma de saber si alguien la
            # autorizo: falta supabase/202609221000_autonomia2_autorizacion.sql.
            registrar("autorizacion", "tabla no instalada: se BLOQUEA la ejecucion autonoma",
                      tenant=etiqueta, que=que)
            return None, Veredicto(False, SIN_INSTALAR,
                                   f"el registro de {que} todavia no esta instalado")
        registrar("autorizacion", "no se pudo leer: se BLOQUEA la ejecucion autonoma",
                  tenant=etiqueta, que=que, error=e)
        return None, Veredicto(False, DESCONOCIDO,
                               f"no se pudo leer {que}: {type(e).__name__}")


def nivel_de(tenant: str) -> tuple[int, Veredicto | None]:
    """
    El techo vigente de la empresa, leido por nucleo/seguridad/techo.py.

    Devuelve (nivel, fallo). Desde M06-B (21/09/2026) la lectura es UNA sola,
    la de techo.py, que falla cerrado sin asumir ningun nivel: sin fila, con
    un valor invalido, ilegible o de otra empresa, devuelve un fallo con su
    codigo. Antes "sin fila" se leia aca como 0; ahora es TECHO_AUSENTE. El
    NIVEL_POR_OMISION que acompaña al fallo no se usa para decidir: quien
    llama corta en el fallo.
    """
    from nucleo.seguridad import techo as techos
    nivel, fallo = techos.leer(tenant)
    if fallo is not None:
        return NIVEL_POR_OMISION, Veredicto(False, fallo.codigo, fallo.motivo)
    return nivel, None


def veredicto(tenant: str, herramienta: str,
              nivel_requerido: int = NIVEL_EJECUCION) -> Veredicto:
    """
    Si el sistema puede ejecutar SOLO esta herramienta en esta empresa, ahora.

    No consulta el kill switch: eso ya lo hizo la frontera antes de llamar
    aqui. Duplicar la lectura solo abriria la posibilidad de que las dos capas
    vean estados distintos.
    """
    if not isinstance(herramienta, str) or not herramienta.strip():
        return Veredicto(False, SIN_AUTORIZACION,
                         "no se puede autorizar una herramienta sin nombre")
    #  El tenant tambien se valida ACA, aunque la frontera ya lo haya hecho:
    #  este modulo es consultable por su cuenta y un veredicto 'permitido' con
    #  el tenant vacio seria un permiso que no pertenece a nadie.
    if not isinstance(tenant, str) or not tenant.strip():
        return Veredicto(False, SIN_AUTORIZACION,
                         "una autorizacion sin empresa no autoriza nada: no "
                         "hay a quien atribuirla ni contra que aislarla")
    herramienta = herramienta.strip()

    techo, fallo = nivel_de(tenant)
    if fallo is not None:
        return fallo

    fila, fallo = _leer(
        lambda: persistencia.autorizacion_herramienta(tenant, herramienta),
        f"{tenant}/{herramienta}", "la autorizacion de la herramienta")
    if fallo is not None:
        return fallo

    if not fila:
        return Veredicto(
            False, SIN_AUTORIZACION,
            f"'{herramienta}' no tiene autorizacion en esta empresa. El nivel "
            f"global ({techo}) es un techo, no un permiso.",
            nivel_techo=techo)

    autorizacion_id = str(fila.get("id") or "")
    autorizado_por = (fila.get("autorizado_por") or "").strip()
    limites = fila.get("limites") or {}
    nivel_aut = int(fila.get("nivel_maximo") or 0)

    if fila["estado"] != "autorizada":
        return Veredicto(
            False, REVOCADA,
            (fila.get("motivo") or "").strip()
            or f"la autorizacion de '{herramienta}' esta revocada",
            nivel_techo=techo, nivel_autorizado=nivel_aut,
            autorizacion_id=autorizacion_id, autorizado_por=autorizado_por,
            limites=limites)

    ahora = _ahora()
    desde = _a_utc(fila.get("vigente_desde"))
    hasta = _a_utc(fila.get("vigente_hasta"))
    if desde is not None and ahora < desde:
        return Veredicto(
            False, AUN_NO_VIGENTE,
            f"la autorizacion de '{herramienta}' empieza a regir el "
            f"{desde.isoformat()}",
            nivel_techo=techo, nivel_autorizado=nivel_aut,
            autorizacion_id=autorizacion_id, autorizado_por=autorizado_por,
            limites=limites)
    if hasta is not None and ahora >= hasta:
        return Veredicto(
            False, EXPIRADA,
            f"la autorizacion de '{herramienta}' vencio el {hasta.isoformat()}",
            nivel_techo=techo, nivel_autorizado=nivel_aut,
            autorizacion_id=autorizacion_id, autorizado_por=autorizado_por,
            limites=limites)

    #  EL MENOR DE LOS DOS. Ver el encabezado: el techo acota, no habilita.
    efectivo = min(techo, nivel_aut)
    if efectivo < nivel_requerido:
        cual = ("el techo de la empresa" if techo < nivel_aut
                else "la autorizacion de la herramienta")
        return Veredicto(
            False, NIVEL_INSUFICIENTE,
            f"hace falta nivel {nivel_requerido} y el efectivo es {efectivo} "
            f"(techo {techo}, autorizacion {nivel_aut}): manda {cual}",
            nivel_efectivo=efectivo, nivel_techo=techo,
            nivel_autorizado=nivel_aut, autorizacion_id=autorizacion_id,
            autorizado_por=autorizado_por, limites=limites)

    return Veredicto(
        True, "autorizada",
        f"'{herramienta}' autorizada hasta nivel {efectivo} por "
        f"{autorizado_por or '(sin declarar)'}",
        nivel_efectivo=efectivo, nivel_techo=techo, nivel_autorizado=nivel_aut,
        autorizacion_id=autorizacion_id, autorizado_por=autorizado_por,
        limites=limites)
