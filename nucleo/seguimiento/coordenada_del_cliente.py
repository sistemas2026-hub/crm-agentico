# -*- coding: utf-8 -*-
"""Dejar escrita la ubicacion de un cliente en los sistemas del ISP.

POR QUE EXISTE  --  10/11/2026.

El dato lo tiene el tecnico, parado en la casa del cliente, y hasta hoy no
habia forma de que lo dejara escrito. Medido el mismo dia contra la instancia
real: de 5.186 equipos, **10** tienen coordenada (0,19 %) -- 5.082 en `null` y
94 en cadena vacia. Del lado del otro sistema hay mas (1.350 de 2.700), pero
siguen faltando 1.350.

POR QUE NO ES UNA HERRAMIENTA DEL MODELO, Y NO ES UNA PREFERENCIA. La
coordenada esta en `nunca_revelar` para todos los roles: es el domicilio de
una persona. El modelo no la lee y no la escribe. Esto lo llama el backend
cuando una persona identificada toca un boton, y entra por `frontera.humana()`
-- nunca por `/interno/herramienta/`, que es la puerta AUTONOMA y hoy esta
cerrada por Autonomia 2 (`frontera.py`, `autonomia2.veredicto()`): por ese
camino el boton fallaria SOLO en produccion, con un sintoma que no senala la
causa.

EL ORDEN NO ES CASUAL, y lo decidio el usuario el 10/11/2026: **primero el
equipo**. Es donde el dato falta de verdad (0,19 % contra 50 %), asi que es el
que define si la accion sirvio. Si el equipo falla no se intenta el servicio:
dejar escrito solo el segundo produciria dos sistemas que se contradicen sin
que nadie lo sepa.

CADA DESTINO TIENE SU PROPIA CLAVE DE IDEMPOTENCIA, y eso es lo que hace
reintentable un exito a medias: si el equipo se escribio y el servicio no,
volver a tocar el boton reintenta SOLO el que falta -- el otro devuelve
`repetida` sin tocar al tercero. Una sola clave para los dos dejaria el caso
parcial sin salida, que es exactamente el defecto que se arreglo hoy en la cola
de la app.

LO QUE ESTO NO PUEDE PROMETER (CLAUDE.md 12): si la llamada salio y la
respuesta se perdio, nadie sabe si el tercero la aplico. La idempotencia evita
la segunda escritura; no convierte un `unknown` en un `confirmado`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nucleo.observabilidad.registro import registrar

#: Resultados posibles. Son los que el backend traduce a una respuesta HTTP.
GUARDADA = "guardada"
PARCIAL = "parcial"
FALLO = "fallo"
SIN_HERRAMIENTA = "sin_herramienta"
BLOQUEADO_POR_INTERRUPTOR = "bloqueado_por_interruptor"
COORDENADA_INVALIDA = "coordenada_invalida"
FALTA_IDENTIFICADOR = "falta_identificador"

#: El planeta. Fuera de esto no es una coordenada: es un dato roto, y
#: escribirlo pondria la casa en un lugar que no existe.
_LAT_MAX = 90.0
_LNG_MAX = 180.0

#: Cuantos decimales se escriben. Seis son ~11 cm en el ecuador, de sobra para
#: una casa; mas digitos son ruido del GPS presentado como precision.
_DECIMALES = 6


@dataclass
class DestinoEscrito:
    """Como le fue a UNO de los destinos."""

    herramienta: str
    ok: bool
    detalle: str = ""
    repetida: bool = False


@dataclass
class ResultadoCoordenada:
    estado: str
    motivo: str = ""
    referencia: str = ""
    destinos: list[DestinoEscrito] = field(default_factory=list)

    @property
    def escribio_algo(self) -> bool:
        return any(d.ok for d in self.destinos)


def _numero(valor) -> float | None:
    """Un float, o `None`. Nunca una excepcion hacia afuera."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    #  NaN e infinito pasan `float()` y rompen la comparacion de rango: `nan >
    #  90` es False, asi que sin esto un NaN se escribiria como coordenada
    #  valida.
    if n != n or n in (float("inf"), float("-inf")):
        return None
    return n


def validar(latitud, longitud) -> tuple[float, float] | None:
    """La coordenada, o `None` si no se puede afirmar que sea una.

    FAIL-CLOSED, con el mismo criterio que el parser que las LEE
    (`campo/coordenadas_del_cliente.py`): lo que no se reconoce no se arregla,
    se descarta. Acá importa el doble, porque esto no interpreta un dato ajeno:
    lo ESCRIBE sobre el domicilio de una persona.
    """
    lat = _numero(latitud)
    lng = _numero(longitud)
    if lat is None or lng is None:
        return None
    if abs(lat) > _LAT_MAX or abs(lng) > _LNG_MAX:
        return None
    #  EL CRUCE DEL ECUADOR CON EL MERIDIANO CERO, descartado a proposito y por
    #  la misma razon que en el parser: `0,0` es como se ve un formulario a
    #  medio llenar, no un cliente en el Golfo de Guinea.
    if lat == 0.0 and lng == 0.0:
        return None
    return (lat, lng)


def _texto(n: float) -> str:
    return f"{n:.{_DECIMALES}f}"


def _herramientas(config) -> tuple[object | None, object | None]:
    """Las dos escrituras, buscadas POR SU MARCA y nunca por su nombre.

    El nucleo no conoce a ningun cliente (CLAUDE.md 3.1). Un `if nombre ==
    '...'` aca seria el nombre de una herramienta de un ISP concreto dentro del
    motor, y la guarda de arquitectura lo caza.
    """
    equipo = next((h for h in config.herramientas
                   if getattr(h, "escribe_coordenada_equipo", False)), None)
    servicio = next((h for h in config.herramientas
                     if getattr(h, "escribe_coordenada_servicio", False)), None)
    return (equipo, servicio)


def _argumentos(herr, identificador: str, lat: float, lng: float) -> dict:
    """El cuerpo, con los nombres que ESTE proveedor declara."""
    pc = herr.parametros_de_coordenada
    args = dict(getattr(herr, "argumentos_fijos", None) or {})
    args[pc.identificador] = identificador
    if pc.combinada:
        #  Coma y sin espacio: es la forma que el proveedor ya tiene cargada y
        #  la unica que el parser lee sin ambiguedad.
        args[pc.combinada] = f"{_texto(lat)},{_texto(lng)}"
    else:
        args[pc.latitud] = _texto(lat)
        args[pc.longitud] = _texto(lng)
    return args


def guardar(config, tenant: str, *, actor: str, identificadores: dict,
            latitud, longitud, origen: str) -> ResultadoCoordenada:
    """Escribe la ubicacion en los sistemas del ISP que la sepan recibir.

    `identificadores` trae, por nombre de parametro, con que se identifica al
    cliente en cada sistema -- por ejemplo `{"sn_onu": ..., "id_servicio":
    ...}`. Los nombres salen de la configuracion, no de aca.

    `origen` identifica LA SOLICITUD y es la base de la clave idempotente: el
    id de la orden sirve; un uuid nuevo por intento NO, que es un identificador
    unico y no una clave idempotente (CLAUDE.md 12).
    """
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguridad import frontera, idempotencia, interruptor

    punto = validar(latitud, longitud)
    if punto is None:
        #  SIN EL VALOR EN EL LOG: una coordenada es el domicilio de una
        #  persona, y el registro del motor no lleva datos de cliente.
        registrar("coordenada_cliente",
                  "la ubicacion recibida no es una coordenada: no se escribe")
        return ResultadoCoordenada(COORDENADA_INVALIDA,
                                   "la ubicacion no esta en el planeta o es 0,0")
    lat, lng = punto

    equipo, servicio = _herramientas(config)
    if equipo is None and servicio is None:
        return ResultadoCoordenada(
            SIN_HERRAMIENTA,
            "el tenant no declara ninguna herramienta que escriba una ubicacion")

    #  EL INTERRUPTOR ANTES DE TODO, y leido sin cache: si no se puede
    #  comprobar, NO se escribe. Falla CERRADO
    #  (`nucleo/seguridad/interruptor.py`).
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("coordenada_cliente",
                  "no se pudo leer el interruptor: NO se escribe la ubicacion",
                  error=e)
        return ResultadoCoordenada(
            BLOQUEADO_POR_INTERRUPTOR,
            f"no se pudo comprobar el interruptor ({type(e).__name__})")
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(
            tenant, actor=actor, recurso="coordenada_del_cliente",
            motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoCoordenada(BLOQUEADO_POR_INTERRUPTOR,
                                   f"{veredicto.estado}: {veredicto.motivo}")

    destinos: list[DestinoEscrito] = []

    def _escribir(herr) -> DestinoEscrito:
        ident = identificadores.get(herr.parametros_de_coordenada.identificador)
        if not ident:
            return DestinoEscrito(
                herr.nombre, False,
                f"falta '{herr.parametros_de_coordenada.identificador}'")
        args = _argumentos(herr, str(ident), lat, lng)

        def _hacer():
            return ejecutor_http.ejecutar(
                herr, args, tenant,
                variables_tenant=config.variables_tenant)

        try:
            with frontera.humana(tenant, herr.nombre, actor=actor,
                                 evidencia=origen, origen=origen):
                #  UNA CLAVE POR DESTINO. Con una sola para los dos, un exito
                #  a medias no se puede reintentar: el que fallo volveria como
                #  'repetida' por culpa del que si salio.
                res = idempotencia.ejecutar(
                    tenant, herr.nombre, args, origen, _hacer,
                    clave=f"{origen}|{herr.nombre}",
                    #  REINTENTAR LO QUE FALLO, Y ACA SI (10/11/2026).
                    #
                    #  Por omision una operacion 'fallida' no se vuelve a
                    #  intentar, y es a proposito: "un reintento automatico
                    #  sobre una mutacion que no es idempotente es justo lo
                    #  que esta tabla existe para evitar"
                    #  ('persistencia/db.py'). Un pago repetido es un pago de
                    #  mas.
                    #
                    #  Esta mutacion SI es idempotente por naturaleza, y esa
                    #  es la diferencia: el efecto es "el campo queda en ESTE
                    #  valor", no "sumar un hecho". Escribir dos veces la
                    #  misma coordenada deja la misma coordenada. Sin esto, un
                    #  exito a medias no tendria salida --el tecnico tocaria
                    #  el boton y no pasaria nada-- que es exactamente el
                    #  defecto que se arreglo hoy en la cola de la app.
                    #
                    #  Lo que sigue sin poder prometerse: si la llamada salio
                    #  y la respuesta se perdio, nadie sabe si el tercero la
                    #  aplico. Acá no importa, porque el reintento la deja en
                    #  el mismo valor de todos modos.
                    reintentar_fallida=True)
        except Exception as e:                               # noqa: BLE001
            registrar("coordenada_cliente",
                      "no se pudo escribir la ubicacion en un sistema",
                      error=e)
            return DestinoEscrito(herr.nombre, False, type(e).__name__)

        if res.decision == "repetida":
            return DestinoEscrito(herr.nombre, True, "ya estaba escrita",
                                  repetida=True)
        if not res.ejecutada:
            return DestinoEscrito(herr.nombre, False,
                                  res.codigo or res.decision or "no ejecutada")
        return DestinoEscrito(herr.nombre, True)

    #  PRIMERO EL EQUIPO. Si falla, el servicio NO se intenta: ver la cabecera.
    if equipo is not None:
        d = _escribir(equipo)
        destinos.append(d)
        if not d.ok:
            return ResultadoCoordenada(
                FALTA_IDENTIFICADOR if d.detalle.startswith("falta ") else FALLO,
                d.detalle, referencia=origen, destinos=destinos)

    if servicio is not None:
        d = _escribir(servicio)
        destinos.append(d)
        if not d.ok:
            #  PARCIAL Y NO FALLO, y la diferencia importa: lo que se escribio
            #  NO se deshace --no hay con que-- y volver a tocar el boton
            #  reintenta solo este, porque el otro tiene su propia clave.
            return ResultadoCoordenada(
                PARCIAL,
                f"{servicio.nombre}: {d.detalle}",
                referencia=origen, destinos=destinos)

    return ResultadoCoordenada(GUARDADA, referencia=origen, destinos=destinos)
