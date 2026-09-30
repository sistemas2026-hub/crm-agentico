# -*- coding: utf-8 -*-
"""
================================================================================
 LA FRONTERA DE ACCIONES EXTERNAS  --  un solo lugar por el que se sale
================================================================================

POR QUE EXISTE
--------------
El interruptor de autonomia se puso primero en 'motor.py', que es por donde el
modelo pide herramientas. Estaba bien y no alcanzaba: el paso 10.14 midio CINCO
caminos que llegaban a escribir en WispHub o en el CRM sin pasar por ahi --
'operativo.responder', 'operativo.cerrar', 'operativo.cerrar_caso_crm', y
'_ejecutar_tool' con el tenant vacio. Ninguno era un descuido grande; todos eran
codigo razonable escrito en otro archivo, que simplemente no sabia que existia
un gate.

Agregar el interruptor a esas cinco funciones habria cerrado esas cinco. La
sexta la escribe alguien el mes que viene.

Asi que el control no vive en los llamadores: vive donde ocurre el EFECTO. La
frontera es el ultimo metro antes de que salga un POST/PUT/PATCH/DELETE, y la
comprueba el propio ejecutor (nucleo/herramientas/http.py). Un modulo nuevo que
quiera escribir afuera tiene que pasar por aqui aunque no sepa que aqui existe:
si no lo hace, su llamada NO sale.

QUE NO ES
---------
No es un segundo interruptor. Lee el MISMO
'asistente.interruptor_autonomia' a traves de 'interruptor.veredicto()'. El
interruptor sigue siendo binario, DETENIDO / ACTIVO; desde M06-B (21/09/2026)
lo acompaña el TECHO por niveles (nucleo/seguridad/techo.py), que se consulta
justo despues en autonoma() y critica(). El techo acota, no autoriza.

COMO SE PRUEBA QUE LA AUTORIZACION OCURRIO
------------------------------------------
Con un ContextVar privado de este modulo que guarda un objeto '_Permiso' que
SOLO este modulo construye. No hay un parametro 'autorizado=True' que un
llamador pueda pasar: para que la llamada salga, tiene que haber un permiso
vigente en el contexto, y el unico modo de ponerlo ahi es entrar por
'autonoma()' o por 'humana()'.

  LIMITE HONESTO: Python no tiene fronteras de verdad. Quien escriba
  'frontera._PERMISO.set(frontera._Permiso(...))' se salta esto. Lo que el
  diseño impide es el bypass ACCIDENTAL --el unico que ocurre en la practica--
  y deja el deliberado a la vista de cualquiera que lea el diff: no hay forma
  de escribirlo que parezca inocente. La prueba de cobertura
  (tests/test_frontera_externa.py) ademas falla si aparece una llamada nueva al
  ejecutor desde un modulo que no esta en la lista permitida.

LAS DOS PUERTAS, Y POR QUE SON DOS
----------------------------------
  autonoma()  nadie en particular lo pidio: lo decidio el agente, o llego la
              hora. CONSULTA EL INTERRUPTOR. Es lo que el kill switch existe
              para frenar.

  humana()    una persona concreta decidio esta accion concreta. NO consulta el
              interruptor -- detener la autonomia no puede impedirle a un
              operador hacer su trabajo-- pero EXIGE evidencia: quien fue y
              contra que registro se puede comprobar. Sin evidencia no abre.

La diferencia no es de confianza: es que en 'humana()' hay un responsable con
nombre, y queda anotado.

LA TERCERA PUERTA: critica()  (M06-A, 21/09/2026)
------------------------------------------------
Para las herramientas IRREVERSIBLES (Herramienta.irreversible: R3 equipo del
cliente, R4 dinero) ninguna de las dos alcanza: autonoma() no pide a una
persona, y humana() no mira el kill switch ni las compuertas de autonomia.
critica() exige TODO -- kill switch, etapa, autorizacion granular Y una
aprobacion humana persistida y atada a la accion exacta (ver
nucleo/seguridad/aprobacion.py). Y exigir() cierra el resto: una irreversible
que llegue al ejecutor con un permiso de otra clase NO sale, venga del camino
que venga.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar  # noqa: E402

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass

# 'interruptor' se importa arriba porque no crea ciclo: interruptor -> db.
# 'autonomia2' y 'autorizacion' tampoco: ninguno importa frontera.
# 'aprobacion' tampoco: importa idempotencia, que importa frontera solo
# adentro de una funcion.
from nucleo.seguridad import aprobacion as aprobaciones
from nucleo.seguridad import autonomia2, autorizacion, interruptor
from nucleo.seguridad import techo as techos
from nucleo.seguridad.idempotencia import hash_de


def _nivel_de_escritura(nivel_requerido) -> int:
    """
    El nivel que se le exige a una escritura en la frontera (M06-B).

    Sin declarar: el mismo 2 de siempre. Declarado: nunca menos que 1 -- el
    nivel 0 es observar, y por aca solo pasan cosas con efecto. Un valor que
    no es un nivel se deja pasar TAL CUAL para que techo.veredicto lo rechace
    con su codigo, en vez de corregirlo en silencio.
    """
    if nivel_requerido is None:
        return techos.NIVEL_ESCRITURA_POR_DEFECTO
    if (isinstance(nivel_requerido, int) and not isinstance(nivel_requerido, bool)
            and nivel_requerido < techos.NIVEL_MINIMO_ESCRITURA):
        return techos.NIVEL_MINIMO_ESCRITURA
    return nivel_requerido

# Motivos de bloqueo. Viajan a la traza como bloqueo, no como error.
SIN_TENANT = "ACCION_EXTERNA_SIN_TENANT"
SIN_AUTORIZAR = "ACCION_EXTERNA_SIN_AUTORIZAR"
TENANT_DISTINTO = "ACCION_EXTERNA_TENANT_DISTINTO"
#  Una herramienta irreversible llego al ejecutor con un permiso que no es el
#  de la puerta critica -- el de autonoma() o humana(), que no exigen la
#  aprobacion atada a la accion.
IRREVERSIBLE_SIN_APROBACION = "IRREVERSIBLE_SIN_APROBACION_VINCULANTE"
#  Un permiso critico usado para otra herramienta, o para otros argumentos.
PERMISO_DE_OTRA_ACCION = "PERMISO_CRITICO_DE_OTRA_ACCION"
#  Una herramienta que declara aprobacion humana llego con permiso autonomo.
APROBACION_REQUERIDA = "APROBACION_HUMANA_REQUERIDA"


class AccionExternaNoAutorizada(Exception):
    """
    Una accion con efecto externo llego al ejecutor sin permiso vigente.

    Es una EXCEPCION y no un valor de retorno por el mismo motivo que
    AutonomiaDetenida: ningun camino puede ignorarla por descuido.
    """

    def __init__(self, herramienta: str, codigo: str, motivo: str):
        self.herramienta = herramienta
        self.codigo = codigo
        self.motivo = motivo
        super().__init__(f"{codigo}: {motivo} ('{herramienta}')")


@dataclass(frozen=True)
class _Permiso:
    """
    La prueba de que la autorizacion ocurrio. Lo construye SOLO este modulo.

    'clase' es la del punto 2 del paso 10.14A:
      'autonoma'  el agente o el reloj; paso por el interruptor.
      'humana'    una persona concreta; trae actor y evidencia.
    """
    tenant: str
    clase: str
    actor: str
    origen: str
    evidencia: str = ""
    #  Solo los llena 'critica()'. Un permiso critico vale para UNA
    #  herramienta y UNOS argumentos (su huella canonica): el ultimo metro los
    #  compara contra lo que de verdad esta por salir.
    herramienta: str = ""
    huella: str = ""
    aprobacion_id: str = ""


_PERMISO: contextvars.ContextVar = contextvars.ContextVar("permiso_externo",
                                                          default=None)


def permiso_vigente() -> _Permiso | None:
    """El permiso activo en este contexto, o None."""
    return _PERMISO.get()


def escribe(herramienta) -> bool:
    """
    Si ejecutar esta herramienta produce un efecto afuera.

    Se mira 'solo_lectura' -- el mismo campo que usa
    interruptor.es_accion_autonoma, para que las dos capas no puedan discrepar
    sobre que cuenta como escritura.
    """
    return not getattr(herramienta, "solo_lectura", True)


def _tenant_valido(tenant) -> bool:
    return isinstance(tenant, str) and bool(tenant.strip())


@contextmanager
def autonoma(tenant: str, herramienta: str, *, origen: str = "",
             actor: str = "motor", nivel_requerido: int | None = None):
    """
    Abre permiso para una accion que NADIE pidio explicitamente.

    Consulta el interruptor. Si esta detenido, o no se pudo leer, o el tenant
    no es valido: levanta AccionExternaNoAutorizada y NO abre el permiso.

    'nivel_requerido' (M06-B) es el que declara la HERRAMIENTA en el catalogo
    (techo.nivel_requerido_de) -- nunca algo que venga de los argumentos de la
    llamada. Sin declarar, 2: lo mismo que se exigia antes.
    """
    nivel_requerido = _nivel_de_escritura(nivel_requerido)
    if not _tenant_valido(tenant):
        _anotar(tenant, actor, herramienta,
                f"{SIN_TENANT}: sin tenant valido no hay interruptor que consultar")
        raise AccionExternaNoAutorizada(
            herramienta, SIN_TENANT,
            "una accion externa sin tenant valido no se ejecuta: no hay "
            "interruptor que consultar, y 'sin control' no es autorizacion")

    veredicto = interruptor.veredicto(tenant)
    if not veredicto.permitido:
        _anotar(tenant, actor, herramienta,
                f"{veredicto.estado}: {veredicto.motivo}")
        raise AccionExternaNoAutorizada(
            herramienta, interruptor.CODIGO_BLOQUEO,
            f"{veredicto.estado}: {veredicto.motivo}")

    #  EL TECHO (M06-B): pegado al kill switch, antes que todo lo demas. Es la
    #  otra mitad de "¿puede esta empresa actuar sola?": el interruptor dice
    #  si, el techo dice hasta donde. Acota, no autoriza.
    _exigir_techo(tenant, herramienta, nivel_requerido, actor, origen)

    #  AUTONOMIA 2  --  las dos compuertas que el kill switch no cubre
    #  --------------------------------------------------------------
    #  Van AQUI y no en los llamadores por la misma razon que todo lo demas de
    #  este modulo: el control vive donde ocurre el efecto. Un llamador puede
    #  olvidarse; esta funcion es el unico camino por el que se abre un permiso
    #  autonomo, asi que lo que se compruebe aca no se puede saltear.
    #
    #  1. La etapa + el prerequisito de B-7 (nucleo/seguridad/autonomia2.py).
    #  2. La autorizacion granular de ESTA herramienta
    #     (nucleo/seguridad/autorizacion.py).
    #
    #  'humana()' NO pasa por aca a proposito: una persona identificada que
    #  aprueba una accion concreta no es el sistema actuando solo, y exigirle
    #  una autorizacion de autonomia dejaria sin operar al panel el dia que se
    #  revoque una herramienta.
    etapa = autonomia2.veredicto()
    if not etapa.permitido:
        _anotar(tenant, actor, herramienta, f"{etapa.codigo}: {etapa.motivo}")
        _bitacora(tenant, herramienta, etapa.codigo, etapa.motivo, actor,
                  origen)
        raise AccionExternaNoAutorizada(herramienta, etapa.codigo, etapa.motivo)

    permitida = autorizacion.veredicto(tenant, herramienta,
                                       nivel_requerido=nivel_requerido)
    if not permitida.permitido:
        _anotar(tenant, actor, herramienta,
                f"{permitida.codigo}: {permitida.motivo}")
        _bitacora(tenant, herramienta, permitida.codigo, permitida.motivo,
                  actor, origen, autorizacion_id=permitida.autorizacion_id,
                  nivel=permitida.nivel_efectivo)
        raise AccionExternaNoAutorizada(herramienta, permitida.codigo,
                                        permitida.motivo)

    _bitacora(tenant, herramienta, "autorizada", permitida.motivo, actor,
              origen, autorizacion_id=permitida.autorizacion_id,
              nivel=permitida.nivel_efectivo, decision="permitida")

    testigo = _PERMISO.set(_Permiso(tenant=tenant.strip(), clase="autonoma",
                                    actor=actor, origen=origen))
    try:
        yield
    finally:
        _PERMISO.reset(testigo)


@contextmanager
def humana(tenant: str, herramienta: str, *, actor: str, evidencia: str,
           origen: str = ""):
    """
    Abre permiso para una accion que decidio una PERSONA concreta.

    NO consulta el interruptor -- ver el encabezado. A cambio exige las dos
    cosas que permiten auditarla despues: quien fue ('actor') y contra que
    registro se comprueba ('evidencia': el id de la propuesta aprobada, el id
    del mensaje que escribio el agente, la fila del panel). Sin las dos, no
    abre: una "accion humana" sin responsable es exactamente el agujero por el
    que se cuela lo automatico disfrazado.
    """
    if not _tenant_valido(tenant):
        raise AccionExternaNoAutorizada(
            herramienta, SIN_TENANT,
            "una accion externa sin tenant valido no se ejecuta")
    if not (actor or "").strip():
        raise AccionExternaNoAutorizada(
            herramienta, SIN_AUTORIZAR,
            "una accion declarada humana tiene que decir QUIEN la hizo")
    if not (evidencia or "").strip():
        raise AccionExternaNoAutorizada(
            herramienta, SIN_AUTORIZAR,
            "una accion declarada humana tiene que traer evidencia "
            "comprobable (id de la propuesta, del mensaje o de la fila)")

    testigo = _PERMISO.set(_Permiso(tenant=tenant.strip(), clase="humana",
                                    actor=actor.strip(), origen=origen,
                                    evidencia=evidencia.strip()))
    try:
        yield
    finally:
        _PERMISO.reset(testigo)


def _exigir_techo(tenant: str, herramienta: str, nivel_requerido, actor: str,
                  origen: str) -> None:
    """El paso del techo (M06-B), igual en autonoma() y en critica()."""
    v = techos.veredicto(tenant, nivel_requerido)
    if not v.permitido:
        _anotar(tenant, actor, herramienta, f"{v.codigo}: {v.motivo}")
        _bitacora(tenant, herramienta, v.codigo, v.motivo, actor, origen,
                  nivel=v.techo)
        raise AccionExternaNoAutorizada(herramienta, v.codigo, v.motivo)


@contextmanager
def critica(tenant: str, herramienta: str, *, argumentos: dict,
            aprobacion, origen: str = "", nivel_requerido: int | None = None):
    """
    La UNICA puerta por la que sale una herramienta IRREVERSIBLE (R3/R4).

    No elige entre "la decidio una persona" y "la decidio el sistema": exige
    las dos cosas. La cadena entera, en este orden, y cualquier eslabon que
    diga no cierra la puerta ANTES de abrir el permiso:

        1. tenant valido
        2. kill switch                     interruptor.veredicto
       2b. techo de autonomia (M06-B)      techo.veredicto
        3. etapa de autonomia (+ B-7)      autonomia2.veredicto
        4. autorizacion granular (+nivel)  autorizacion.veredicto
        5. aprobacion humana VINCULANTE    aprobacion.veredicto
        6. auditoria                       bitacora de la decision
        7. permiso                         atado a herramienta + huella
       (8. idempotencia y 9. el ultimo metro los pone quien ejecuta: el
           llamador envuelve con idempotencia.ejecutar, y el ejecutor HTTP
           llama a exigir(), que vuelve a comparar la huella.)

    A diferencia de humana(), el kill switch SI la frena aunque haya
    aprobacion: una accion irreversible aprobada a las 10 no tiene por que
    salir a las 10:05 si a las 10:03 alguien tiro el interruptor. Es una
    decision del 21/09/2026 (M06-A), explicita y solo para irreversibles --
    humana() sigue igual para todo lo demas.

    'aprobacion' es una aprobacion.Aprobacion leida de la base; nunca algo
    que haya mandado el cliente del request.
    """
    actor = (getattr(aprobacion, "aprobador", "") or "").strip() or "aprobacion"
    nivel_requerido = _nivel_de_escritura(nivel_requerido)

    if not _tenant_valido(tenant):
        _anotar(tenant, actor, herramienta,
                f"{SIN_TENANT}: sin tenant valido no hay interruptor que consultar")
        raise AccionExternaNoAutorizada(
            herramienta, SIN_TENANT,
            "una accion irreversible sin tenant valido no se ejecuta")

    veredicto = interruptor.veredicto(tenant)
    if not veredicto.permitido:
        _anotar(tenant, actor, herramienta,
                f"{veredicto.estado}: {veredicto.motivo}")
        raise AccionExternaNoAutorizada(
            herramienta, interruptor.CODIGO_BLOQUEO,
            f"{veredicto.estado}: {veredicto.motivo}")

    #  2b. El techo (M06-B). Un techo alto NO reemplaza nada de lo que sigue:
    #  una irreversible con techo 3 sigue necesitando su aprobacion atada.
    _exigir_techo(tenant, herramienta, nivel_requerido, actor, origen)

    etapa = autonomia2.veredicto()
    if not etapa.permitido:
        _anotar(tenant, actor, herramienta, f"{etapa.codigo}: {etapa.motivo}")
        _bitacora(tenant, herramienta, etapa.codigo, etapa.motivo, actor, origen)
        raise AccionExternaNoAutorizada(herramienta, etapa.codigo, etapa.motivo)

    permitida = autorizacion.veredicto(tenant, herramienta,
                                       nivel_requerido=nivel_requerido)
    if not permitida.permitido:
        _anotar(tenant, actor, herramienta,
                f"{permitida.codigo}: {permitida.motivo}")
        _bitacora(tenant, herramienta, permitida.codigo, permitida.motivo,
                  actor, origen, autorizacion_id=permitida.autorizacion_id,
                  nivel=permitida.nivel_efectivo)
        raise AccionExternaNoAutorizada(herramienta, permitida.codigo,
                                        permitida.motivo)

    aprobada = aprobaciones.veredicto(aprobacion, tenant=tenant.strip(),
                                      herramienta=herramienta,
                                      argumentos=argumentos)
    if not aprobada.permitido:
        _anotar(tenant, actor, herramienta,
                f"{aprobada.codigo}: {aprobada.motivo}")
        _bitacora(tenant, herramienta, aprobada.codigo, aprobada.motivo,
                  actor, origen, autorizacion_id=permitida.autorizacion_id,
                  nivel=permitida.nivel_efectivo)
        raise AccionExternaNoAutorizada(herramienta, aprobada.codigo,
                                        aprobada.motivo)

    _bitacora(tenant, herramienta, "autorizada",
              f"{permitida.motivo}; {aprobada.motivo}", actor, origen,
              autorizacion_id=permitida.autorizacion_id,
              nivel=permitida.nivel_efectivo, decision="permitida")

    testigo = _PERMISO.set(_Permiso(
        tenant=tenant.strip(), clase="critica", actor=actor, origen=origen,
        evidencia=str(getattr(aprobacion, "id", "") or ""),
        herramienta=herramienta, huella=hash_de(argumentos),
        aprobacion_id=str(getattr(aprobacion, "id", "") or "")))
    try:
        yield
    finally:
        _PERMISO.reset(testigo)


def puerta(tenant: str, herramienta: str, actor: str = "",
           evidencia: str = "", origen: str = ""):
    """
    La eleccion de puerta, en un solo lugar.

    CON ACTOR  -> humana(): llega con un responsable identificado y una
                  referencia contra la que comprobarlo.
    SIN ACTOR  -> autonoma(): no hay a quien atribuirla, asi que se trata como
                  lo que es -- el sistema decidiendo solo-- y pasa por el
                  interruptor.

    La regla es deliberadamente esa y no "el modulo declara si es humana": un
    modulo puede equivocarse o cambiar de llamador. Un actor, o esta o no esta.

      LIMITE: 'actor' dice QUIEN, no PRUEBA que sea una persona. Un proceso
      automatico que pase un actor inventado entra por la puerta humana. Lo que
      el diseño garantiza es que la accion queda ATRIBUIDA -- si despues resulta
      que ese actor era un cron, el registro lo delata. Para los caminos donde
      esa evidencia es fuerte (una propuesta aprobada, un mensaje escrito en el
      panel) se pasa el id de la fila; donde es debil, se dice en el informe.
    """
    if (actor or "").strip():
        return humana(tenant, herramienta, actor=actor.strip(),
                      evidencia=evidencia or "(sin referencia)",
                      origen=origen)
    return autonoma(tenant, herramienta, origen=origen,
                    actor=origen or "sistema")


def exigir(herramienta, tenant=None, argumentos=None) -> _Permiso:
    """
    EL ULTIMO METRO. Lo llama el ejecutor antes de mandar una escritura.

    Devuelve el permiso vigente, o levanta AccionExternaNoAutorizada. Sobre las
    herramientas de LECTURA no se llama: detener la autonomia no puede dejar
    ciego al que atiende.

    'argumentos' son los que el ejecutor esta por mandar. Para una herramienta
    IRREVERSIBLE son obligatorios: se comparan contra la huella del permiso
    critico, asi que lo aprobado y lo que sale tienen que ser lo mismo.
    """
    nombre = getattr(herramienta, "nombre", str(herramienta))
    permiso = _PERMISO.get()
    if permiso is None:
        raise AccionExternaNoAutorizada(
            nombre, SIN_AUTORIZAR,
            "esta escritura llego al ejecutor sin pasar por la frontera "
            "(nucleo/seguridad/frontera.py). No sale.")
    if _tenant_valido(tenant) and tenant.strip() != permiso.tenant:
        # Un permiso abierto para una empresa no autoriza a escribir en la de
        # al lado. Es el mismo aislamiento que la RLS hace en la base.
        raise AccionExternaNoAutorizada(
            nombre, TENANT_DISTINTO,
            f"el permiso vigente es de '{permiso.tenant}' y la llamada es de "
            f"'{tenant}'")

    #  UN PERMISO CRITICO VALE PARA UNA SOLA ACCION. Abierto para reiniciar
    #  una ONU, no escribe nada mas -- ni otra irreversible ni una comun.
    if permiso.clase == "critica":
        if permiso.herramienta != nombre:
            raise AccionExternaNoAutorizada(
                nombre, PERMISO_DE_OTRA_ACCION,
                f"el permiso critico es para '{permiso.herramienta}', no "
                f"para '{nombre}'")
        if argumentos is None or hash_de(argumentos) != permiso.huella:
            raise AccionExternaNoAutorizada(
                nombre, PERMISO_DE_OTRA_ACCION,
                "lo que esta por salir no es lo que se aprobo (la huella de "
                "los argumentos no coincide)")

    #  UNA IRREVERSIBLE SOLO SALE CON PERMISO CRITICO. Es lo que cierra todos
    #  los caminos a la vez: la conversacion (autonoma), una ruta de servicio,
    #  el panel (humana), un modulo que se escriba el mes que viene. Ninguno
    #  de esos abre 'critica', asi que ninguno llega al efecto.
    if getattr(herramienta, "irreversible", False) and permiso.clase != "critica":
        raise AccionExternaNoAutorizada(
            nombre, IRREVERSIBLE_SIN_APROBACION,
            f"'{nombre}' es irreversible y el permiso vigente es "
            f"'{permiso.clase}': solo sale por frontera.critica(), con una "
            f"aprobacion humana atada a esta accion")

    #  LO QUE DECLARA APROBACION HUMANA NUNCA SALE POR LA PUERTA AUTONOMA
    #  (M06-B, 21/09/2026). Hasta aca la aprobacion de una herramienta no
    #  irreversible (agregar_promesa_pago, los tickets) solo existia en la
    #  CONVERSACION: el motor la mandaba a la cola. Por la puerta autonoma --con
    #  techo alto, etapa encendida y una autorizacion granular-- habria salido
    #  sin que nadie la aprobara. Ningun camino legitimo lo necesita: ninguna
    #  herramienta con aprobacion es invocable por un servicio.
    if (getattr(herramienta, "aprobacion_humana", False)
            and permiso.clase == "autonoma"):
        raise AccionExternaNoAutorizada(
            nombre, APROBACION_REQUERIDA,
            f"'{nombre}' declara aprobacion humana: no la ejecuta el sistema "
            f"solo, tenga el techo que tenga")
    return permiso


def _anotar(tenant, actor: str, herramienta: str, motivo: str) -> None:
    """Deja el bloqueo en el registro. Nunca tumba la accion por no poder anotar."""
    try:
        interruptor.anotar_bloqueo(
            tenant if _tenant_valido(tenant) else "(sin tenant)",
            actor=actor or "frontera",
            recurso=f"herramienta:{herramienta}", motivo=motivo)
    except Exception as e:                                       # noqa: BLE001
        registrar("frontera", "no se pudo anotar el bloqueo", herramienta=herramienta,
                  error=e)


def _bitacora(tenant, herramienta: str, codigo: str, motivo: str, actor: str,
              origen: str, *, autorizacion_id: str = "",
              nivel: int | None = None, decision: str = "bloqueada") -> None:
    """
    Deja la decision de Autonomia 2 en asistente.ejecucion_autonoma.

    Registra TAMBIEN lo permitido, no solo lo bloqueado: una bitacora que solo
    guarda rechazos no permite contestar "¿que ejecuto el sistema solo la
    semana pasada?", que es la pregunta que la auditoria existe para responder.

    Nunca tumba la accion: la decision ya se tomo arriba: esto la escribe.
    """
    try:
        from nucleo.persistencia import db as persistencia
        persistencia.registrar_ejecucion_autonoma(
            tenant, herramienta=herramienta, decision=decision, codigo=codigo,
            motivo=motivo, actor=actor, autorizacion_id=autorizacion_id,
            nivel_efectivo=nivel,
            resultado=None if decision == "permitida" else "no_ejecutada",
            evidencia=origen or "")
    except BaseException:                                        # noqa: BLE001
        pass


#  ESTADOS DE UNA EJECUCION AUTONOMA  --  y por que son estos y no otros
#  --------------------------------------------------------------------
#  La bitacora 'asistente.ejecucion_autonoma' es APPEND-ONLY, asi que un
#  intento deja hasta DOS renglones y se distinguen sin columna nueva:
#
#    resultado IS NULL      la fila de AUTORIZACION. Las compuertas pasaron y
#                           el efecto esta por intentarse. Su 'creado_en' es el
#                           MOMENTO DE AUTORIZACION.
#    resultado IS NOT NULL  la fila de DESENLACE. Su 'creado_en' es el MOMENTO
#                           DE EJECUCION, y trae 'clave_idempotencia': ahi esta
#                           el puente con asistente.operaciones_externas, cuya
#                           clave primaria es (organization_id, clave).
#
#  Los estados, y la diferencia que importa:
#
#    AUTORIZADA   decision='permitida', resultado NULL.
#    BLOQUEADA    decision='bloqueada', resultado='no_ejecutada'. Una compuerta
#                 freno ANTES del efecto. NO ES FALLIDA -- nunca se intento
#                 nada, y llamarla fallida haria creer que un tercero respondio
#                 mal cuando lo que paso es que el sistema no salio.
#    EJECUTANDO   no es un estado de esta bitacora: vive en
#                 operaciones_externas.estado, que es quien reclama la
#                 operacion. Duplicarlo aca seria un segundo mecanismo.
#    EXITOSA      el efecto SI ocurrio y el tercero contesto bien.
#    FALLIDA      el efecto SI se intento y volvio con error. Solo por este
#                 camino: es la unica diferencia que separa "no salio" de
#                 "salio y salio mal".
#    EXPIRADA     tampoco es de esta bitacora. El vencimiento de una
#                 reclamacion (SEGUNDOS_VENCIDA) y su rescate son de
#                 idempotencia.py, y esta version NO los toca.
#
#  NO se copia el resultado ni el error: ya estan en operaciones_externas y una
#  referencia alcanza. Lo que se guarda es la CLAVE.

#  Los desenlaces que esta bitacora acepta. 'no_ejecutada' cubre tanto el
#  bloqueo previo como la repeticion idempotente: en los dos casos el efecto no
#  ocurrio, y el 'codigo' dice cual de los dos fue.
EXITOSA = "exitosa"
FALLIDA = "fallida"
NO_EJECUTADA = "no_ejecutada"


def anotar_desenlace(tenant: str, herramienta: str, clave: str,
                     resultado: str, codigo: str = "", motivo: str = "") -> None:
    """
    Cierra el renglon: que paso con el efecto, y con que clave se puede cruzar.

    La llama nucleo/seguridad/idempotencia.py cuando la operacion termina --
    ahi es donde se conoce la clave y el desenlace, y no antes. Escribir esto
    en el llamador seria el mismo error que este modulo existe para corregir.

    SOLO anota ejecuciones AUTONOMAS. Una accion aprobada por una persona entra
    por humana(), tiene su propio rastro (actor + evidencia + la fila que
    aprobo) y no es "el sistema actuando solo": meterla aca ensuciaria la unica
    tabla que contesta esa pregunta.

    Nunca tumba la accion: la decision ya se tomo y el efecto ya ocurrio.
    """
    permiso = _PERMISO.get()
    #  'critica' tambien: paso por las compuertas de autonomia y ya dejo su
    #  renglon de autorizacion en esta bitacora; sin el desenlace quedaria
    #  "autorizada" para siempre, sin decir si salio.
    if permiso is None or permiso.clase not in ("autonoma", "critica"):
        return
    try:
        from nucleo.persistencia import db as persistencia
        persistencia.registrar_ejecucion_autonoma(
            tenant or permiso.tenant, herramienta=herramienta,
            decision="permitida", codigo=codigo or None, motivo=motivo or None,
            actor=permiso.actor, evidencia=permiso.origen or "",
            clave_idempotencia=clave, resultado=resultado)
    except BaseException:                                        # noqa: BLE001
        pass
