# -*- coding: utf-8 -*-
"""
================================================================================
 APROBACION VINCULANTE  --  la aprobacion humana de una accion IRREVERSIBLE
================================================================================

QUE PROBLEMA RESUELVE
---------------------
Hasta M06-A, "aprobada" era una palabra que se escribia DESPUES de ejecutar:
el endpoint de aprobacion llamaba a la API y recien entonces marcaba la fila.
Mientras la accion viajaba no habia ningun registro de que una persona la
hubiera aprobado -- la garantia era que el endpoint existia, no un dato que la
frontera pudiera comprobar.

Para una herramienta 'irreversible' (Herramienta.irreversible: R3 equipo del
cliente, R4 dinero) eso no alcanza. La aprobacion tiene que:

  1. existir ANTES del efecto, persistida, con quien y cuando;
  2. estar atada a la accion EXACTA: tenant + herramienta + origen + la huella
     canonica de los argumentos que se van a mandar;
  3. dejar de valer si cualquiera de esas cosas cambia -- aprobar el reinicio
     de una ONU no autoriza cambiarle el tipo, aprobar el pago de la factura A
     no paga la B, y tocar los argumentos despues de aprobar invalida la
     aprobacion.

ESTE MODULO NO LEE LA BASE
--------------------------
Recibe la fila ya leida y contesta si vale para lo que se esta por ejecutar.
Asi se prueba entero sin base, y la unica fuente de la fila es
'persistencia.accion_propuesta_de' -- el cuerpo del request nunca llega aca
(ver tests/test_m06a_frontera_autorizacion.py, §8-§9).

QUIEN LO CONSULTA
-----------------
'frontera.critica()', despues del kill switch, la etapa y la autorizacion
granular, y antes de abrir el permiso. Y la frontera vuelve a comparar la
huella en el ultimo metro ('frontera.exigir'), contra los argumentos que el
ejecutor HTTP esta por mandar de verdad: lo que se aprobo y lo que sale tienen
que ser lo mismo byte a byte (en forma canonica).

LIMITE, DICHO ACA
-----------------
'aprobador' es quien el llamador dice que aprobo -- el motor no autentica
personas, lo hace la plataforma que llama al endpoint (mismo limite que
'actor' en frontera.puerta). Lo que este modulo garantiza es que sin un
aprobador con nombre, sin momento y sin estado 'aprobada' persistidos, la
accion no sale.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from nucleo.seguridad.idempotencia import hash_de

# Codigos de bloqueo. Viajan a la bitacora y a la traza como bloqueo.
SIN_APROBACION = "APROBACION_AUSENTE"
NO_APROBADA = "APROBACION_NO_VIGENTE"
OTRO_TENANT = "APROBACION_DE_OTRO_TENANT"
OTRA_HERRAMIENTA = "APROBACION_DE_OTRA_HERRAMIENTA"
OTROS_ARGUMENTOS = "APROBACION_DE_OTROS_ARGUMENTOS"
SIN_APROBADOR = "APROBACION_SIN_APROBADOR"
SIN_MOMENTO = "APROBACION_SIN_MOMENTO"
SIN_ORIGEN = "APROBACION_SIN_ORIGEN"
SIN_HUELLA = "APROBACION_SIN_HUELLA"
SIN_SELLO = "APROBACION_SIN_SELLO"
ALTERADA = "APROBACION_ALTERADA"

#  M06-F (22/09/2026): el estado en que una aprobacion VALE es el del ciclo B5
#  de origin, no uno propio. En B5 aprobar es RESERVAR: una persona pasa la fila
#  de 'pendiente' a 'ejecutando' con compare-and-set (db.reservar_accion), y en
#  esa misma escritura queda su sello. 'ejecutando' es entonces "aprobada por
#  alguien y todavia sin desenlace" -- el unico momento en que la aprobacion
#  puede autorizar el efecto.
#
#  'aprobada' ya NO vale: en B5 es un estado terminal de filas anteriores
#  (legado), que no tienen sello ni conversacion. Y cualquier desenlace
#  (ejecutada_ok, ejecutada_fallo, desconocida, vencida) tampoco: una
#  aprobacion ya usada no se reutiliza.
APROBADA = "ejecutando"


def sello_de(*, tenant: str, organization_id: str, herramienta: str,
             origen: str, huella: str, aprobador: str) -> str:
    """
    EL SELLO DE LA APROBACION (M06-C, 21/09/2026).

    Se calcula UNA vez, al aprobar, sobre todo lo que la aprobacion ata:
    empresa (slug y organizacion), herramienta, origen, huella de los
    argumentos y quien aprobo. Al ejecutar se vuelve a calcular con lo que hay
    en ese momento. Si cambio CUALQUIERA de esas cosas -- el origen, el tenant,
    la herramienta, los argumentos, el aprobador -- los dos sellos no
    coinciden y la aprobacion no vale.

    Hasta M06-C el origen y el tenant solo se exigian "no vacios": una fila con
    el origen cambiado seguia valiendo. El sello los compara de verdad.
    """
    return hash_de({"tenant": (tenant or "").strip(),
                    "organization_id": str(organization_id or ""),
                    "herramienta": herramienta or "",
                    "origen": (origen or "").strip(),
                    "huella": huella or "",
                    "aprobador": (aprobador or "").strip()})


@dataclass(frozen=True)
class Aprobacion:
    """
    Lo que una persona aprobo, tal como quedo PERSISTIDO.

    'huella' es la que se calculo al PROPONER, sobre los argumentos resueltos.
    'argumentos' son los que la fila tiene AHORA. Si alguien los toco despues,
    las dos cosas dejan de coincidir -- y eso es exactamente lo que se mira.
    """
    id: str
    tenant: str
    herramienta: str
    origen: str
    huella: str
    argumentos: dict
    aprobador: str
    aprobada_en: object
    estado: str
    #  M06-C: la organizacion de la fila y el sello escrito al aprobar.
    organization_id: str = ""
    sello: str = ""


@dataclass(frozen=True)
class Veredicto:
    permitido: bool
    codigo: str
    motivo: str


def desde_fila(fila: dict | None, tenant: str) -> Aprobacion | None:
    """
    La fila de asistente.acciones_propuestas, leida bajo la sesion de
    'tenant' (la RLS ya la filtro por organizacion). None si no hay fila.
    """
    if not fila:
        return None
    argumentos = fila.get("argumentos")
    if not isinstance(argumentos, dict):
        argumentos = {}
    return Aprobacion(
        id=str(fila.get("id") or ""),
        tenant=tenant,
        herramienta=str(fila.get("herramienta") or ""),
        origen=str(fila.get("origen") or ""),
        huella=str(fila.get("hash_argumentos") or ""),
        argumentos=argumentos,
        aprobador=str(fila.get("revisado_por") or "").strip(),
        aprobada_en=fila.get("revisado_en"),
        estado=str(fila.get("estado") or ""),
        organization_id=str(fila.get("organization_id") or ""),
        sello=str(fila.get("sello_aprobacion") or ""),
    )


def veredicto(aprobacion: Aprobacion | None, *, tenant: str, herramienta: str,
              argumentos: dict) -> Veredicto:
    """
    ¿Autoriza esta aprobacion a ejecutar ESTA herramienta con ESTOS argumentos
    en ESTE tenant?

    Cada comprobacion tiene su propio codigo: un bloqueo tiene que decir cual
    de las ataduras se rompio, no solo que "algo" no cuadra.
    """
    if aprobacion is None:
        return Veredicto(False, SIN_APROBACION,
                         "una accion irreversible exige una aprobacion humana "
                         "persistida, y no hay ninguna")
    if aprobacion.estado != APROBADA:
        return Veredicto(False, NO_APROBADA,
                         f"la aprobacion esta '{aprobacion.estado or 'vacia'}', "
                         f"no '{APROBADA}'")
    if (tenant or "").strip() != (aprobacion.tenant or "").strip():
        return Veredicto(False, OTRO_TENANT,
                         f"la aprobacion es de '{aprobacion.tenant}' y la "
                         f"accion de '{tenant}'")
    if herramienta != aprobacion.herramienta:
        return Veredicto(False, OTRA_HERRAMIENTA,
                         f"se aprobo '{aprobacion.herramienta}', no "
                         f"'{herramienta}'")
    if not aprobacion.aprobador:
        return Veredicto(False, SIN_APROBADOR,
                         "la aprobacion no dice QUIEN aprobo")
    if not aprobacion.aprobada_en:
        return Veredicto(False, SIN_MOMENTO,
                         "la aprobacion no dice CUANDO se aprobo")
    if not aprobacion.origen.strip():
        return Veredicto(False, SIN_ORIGEN,
                         "la aprobacion no dice de que solicitud salio")
    if not aprobacion.huella:
        return Veredicto(False, SIN_HUELLA,
                         "la propuesta no guardo la huella de sus argumentos: "
                         "no hay contra que comparar lo que se va a mandar")
    #  Dos comparaciones, no una: la fila contra si misma (¿la tocaron despues
    #  de proponer?) y la fila contra lo que se esta por ejecutar (¿se va a
    #  mandar otra cosa?). Cualquiera de las dos que falle, bloquea.
    if hash_de(aprobacion.argumentos) != aprobacion.huella:
        return Veredicto(False, OTROS_ARGUMENTOS,
                         "los argumentos de la propuesta cambiaron despues de "
                         "proponerse: la aprobacion ya no vale")
    if hash_de(argumentos) != aprobacion.huella:
        return Veredicto(False, OTROS_ARGUMENTOS,
                         "lo que se va a ejecutar no es lo que se aprobo")
    #  EL SELLO (M06-C): se recalcula con el tenant que ESTA ejecutando y la
    #  herramienta que SE VA a ejecutar -- no con los de la fila -- mas lo que
    #  la fila dice hoy. Cambio el tenant, el origen, la herramienta, la huella
    #  o el aprobador desde que se aprobo: no coincide.
    if not aprobacion.sello:
        return Veredicto(False, SIN_SELLO,
                         "la aprobacion no tiene sello: no se escribio por el "
                         "camino que la ata a la accion")
    esperado = sello_de(tenant=tenant, organization_id=aprobacion.organization_id,
                        herramienta=herramienta, origen=aprobacion.origen,
                        huella=aprobacion.huella, aprobador=aprobacion.aprobador)
    if esperado != aprobacion.sello:
        return Veredicto(False, ALTERADA,
                         "la aprobacion no corresponde a esta accion: cambio el "
                         "tenant, el origen, la herramienta, los argumentos o "
                         "quien aprobo desde que se aprobo")
    return Veredicto(True, "aprobacion_vigente",
                     f"aprobada por {aprobacion.aprobador}")
