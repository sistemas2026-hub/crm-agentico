# -*- coding: utf-8 -*-
"""
===============================================================================
 EL EQUIPO DE UN CLIENTE SIN SERIAL, BUSCADO POR LA MAC DE SU ROUTER
 26/11/2026
===============================================================================

POR QUE EXISTE
--------------
Cuando WispHub no tiene el 'sn_onu' de un servicio, Dexter no tiene con que
preguntarle a SmartOLT y el diagnostico se corta: «no se pudo leer el equipo
(onu_no_vinculada)». Medido en la copia de produccion del 25/11/2026: 108 de
2.349 casos de los ultimos 30 dias se quedaron asi.

WispHub SI suele tener la MAC del router del cliente ('mac_cpe'), y SmartOLT
tiene 'search_by_mac': la OLT dice detras de que ONU aprendio esa MAC.
Verificado en vivo el 10/11/2026 (cli/proponer_sn_onu.py --buscar-mac): sobre
10 clientes con serial conocido, de cinco tramos distintos de la base, devolvio
la ONU correcta en los 10. Es un dato del EQUIPO, no un parecido de nombre: no
tiene homonimos.

POR QUE EN SEGUNDO PLANO, Y NO AL ABRIR EL TICKET
-------------------------------------------------
El proveedor limita 'search_by_mac' POR CUENTA: con olt_id, una cada 10 s y
100 por hora. Cada consulta tarda ~3,6 s y hay que hacer una por OLT. Hacerlo
dentro de la apertura de un ticket seria esperar 15 s o mas, y dos tickets a la
vez se pisarian el cupo. Por eso: quien necesita el dato lo PIDE y sigue sin
esperar ('pendiente'); un solo hilo hace las consultas espaciadas y guarda el
resultado; la proxima lectura del caso -- la ronda del Supervisor, o la persona
que lo vuelva a abrir -- ya lo encuentra.

UN SOLO HILO POR PROCESO, Y EL MOTOR ES UN PROCESO: gunicorn corre con
'--workers 1' (docker-compose.prod.yml). Si algun dia corre con mas, cada uno
tendria su propio espaciado y entre todos se pasarian del cupo: este limite
tendria que vivir en la base.

LO QUE NO RESUELVE, dicho para que nadie lo suponga
---------------------------------------------------
La consulta busca en la tabla de la OLT, asi que SOLO VE EQUIPOS ENCENDIDOS. Un
cliente que reclama porque su equipo esta apagado o en LOS no aparece: 'ninguna'
con un equipo caido no dice nada sobre de quien es. Por eso 'ninguna' se vuelve
a intentar a las pocas horas y no se guarda como respuesta.

NO ESCRIBE NADA, ni en WispHub ni en SmartOLT. Llevar el serial encontrado a
WispHub es 'actualizar_sn_onu', que sigue DECLARADA Y NO ACTIVADA hasta medir
que su PUT no vacia el resto de la ficha (ver tenants/rapilink.config.yaml).
===============================================================================
"""
from __future__ import annotations

import collections
import threading
import time
from typing import Callable

#: El proveedor permite una cada 10 s por cuenta con olt_id: un segundo de
#: margen por el reloj de cada lado.
SEGUNDOS_ENTRE_LLAMADAS = 11.0
#: El proveedor permite 100 por hora por cuenta. Diez de margen para cualquier
#: otra consulta de la misma cuenta (el script de backfill, una prueba a mano).
MAXIMO_POR_HORA = 90
#: Lo encontrado vale un dia: el equipo de una casa no cambia de un dia al otro,
#: y si lo cambiaron, la consulta siguiente lo corrige sola.
SEGUNDOS_ENCONTRADA = 24 * 3600.0
#: 'ninguna' y 'varias' se reintentan a las tres horas: puede que el equipo
#: estuviera apagado (ver arriba) o que la tabla de la OLT haya cambiado.
SEGUNDOS_SIN_RESULTADO = 3 * 3600.0
#: Un fallo de red o un 429 se reintenta a la media hora.
SEGUNDOS_TRAS_FALLO = 30 * 60.0
#: Cuantos pedidos esperan como maximo. Mas que eso es una avalancha (una caida
#: masiva sin serial): no se encolan, se piden de nuevo en la vuelta siguiente.
MAXIMO_EN_COLA = 200

UNA = "una"                    # una ONU detras de esa MAC: el serial sale
NINGUNA = "ninguna"            # las OLT contestaron y nadie la tiene
VARIAS = "varias"              # mas de una ONU: no se elige
SIN_RESPUESTA = "sin_respuesta"  # una OLT no contesto, o la consulta fallo
SIN_MAC = "sin_mac"            # WispHub no tiene una MAC completa
SIN_OLT = "sin_olt"            # no se sabe en que OLT preguntar
PENDIENTE = "pendiente"        # pedida, todavia no consultada


def mac_normalizada(mac) -> str:
    """'aa:bb:cc:dd:ee:ff' en minusculas, o '' si no son 12 digitos hex.

    WispHub la guarda a mano y llega de cualquier forma: con dos puntos, con
    guiones, en mayusculas, con espacios. La OLT la busca con dos puntos.
    """
    hexa = "".join(c for c in str(mac or "") if c in "0123456789abcdefABCDEF")
    if len(hexa) != 12:
        return ""
    hexa = hexa.lower()
    return ":".join(hexa[i:i + 2] for i in range(0, 12, 2))


def _vigencia(como: str) -> float:
    if como == UNA:
        return SEGUNDOS_ENCONTRADA
    if como in (NINGUNA, VARIAS):
        return SEGUNDOS_SIN_RESULTADO
    return SEGUNDOS_TRAS_FALLO


def _codigo_http(error) -> int | None:
    respuesta = getattr(error, "response", None)
    return getattr(respuesta, "status_code", None)


def _segundos_de_espera(error) -> float:
    respuesta = getattr(error, "response", None)
    try:
        return float((respuesta.headers or {}).get("Retry-After") or 60)
    except Exception:                                       # noqa: BLE001
        return 60.0


class Buscador:
    """
    Guarda lo encontrado por (empresa, MAC) y hace las consultas de a una.

    `consultar(mac, olt_id)` es la llamada al proveedor: devuelve el cuerpo de
    la respuesta o levanta la excepcion de 'requests'. Viene de afuera para que
    el modulo no sepa de credenciales ni de URLs, y para poder probarlo sin red.
    """

    def __init__(self, *, reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], None] = time.sleep):
        self._reloj = reloj
        self._dormir = dormir
        self._lock = threading.Lock()
        self._hay_trabajo = threading.Condition(self._lock)
        #  (empresa, mac) -> (cuando, serial, como)
        self._resultados: dict = {}
        self._cola: collections.deque = collections.deque()
        self._en_cola: set = set()
        #  empresa -> momentos de las llamadas de la ultima hora
        self._llamadas: dict = collections.defaultdict(collections.deque)
        #  empresa -> no llamar antes de este momento (espaciado o un 429)
        self._no_antes_de: dict = {}
        self._hilo: threading.Thread | None = None

    # ------------------------------------------------------------------
    #  Lo que usa quien arma el contexto
    # ------------------------------------------------------------------
    def resultado(self, tenant: str, mac: str) -> tuple[str, str]:
        """(serial, como) si hay algo vigente; ('', PENDIENTE) si no."""
        with self._lock:
            guardado = self._resultados.get((tenant, mac))
            if guardado and (self._reloj() - guardado[0]) < _vigencia(guardado[2]):
                return guardado[1], guardado[2]
            return "", PENDIENTE

    def pedir(self, tenant: str, mac: str, olts: list,
              consultar: Callable[[str, str], dict]) -> bool:
        """Encola la busqueda si no hay nada vigente ni ya pedido. No espera."""
        if not mac:
            return False
        with self._lock:
            clave = (tenant, mac)
            guardado = self._resultados.get(clave)
            if guardado and (self._reloj() - guardado[0]) < _vigencia(guardado[2]):
                return False
            if clave in self._en_cola or len(self._cola) >= MAXIMO_EN_COLA:
                return False
            self._cola.append((tenant, mac, list(olts), consultar))
            self._en_cola.add(clave)
            self._hay_trabajo.notify()
            return True

    # ------------------------------------------------------------------
    #  El trabajo
    # ------------------------------------------------------------------
    def procesar_uno(self) -> bool:
        """Toma un pedido y lo resuelve. False si no habia ninguno."""
        with self._lock:
            if not self._cola:
                return False
            tenant, mac, olts, consultar = self._cola.popleft()
        try:
            serial, como = self._buscar(tenant, mac, olts, consultar)
        except Exception:                                   # noqa: BLE001
            serial, como = "", SIN_RESPUESTA
        with self._lock:
            self._resultados[(tenant, mac)] = (self._reloj(), serial, como)
            self._en_cola.discard((tenant, mac))
        return True

    def _esperar_turno(self, tenant: str) -> None:
        """Duerme lo que haga falta para respetar el cupo de la cuenta."""
        while True:
            with self._lock:
                ahora = self._reloj()
                hechas = self._llamadas[tenant]
                while hechas and (ahora - hechas[0]) >= 3600:
                    hechas.popleft()
                espera = max(0.0, self._no_antes_de.get(tenant, 0.0) - ahora)
                if len(hechas) >= MAXIMO_POR_HORA:
                    espera = max(espera, 3600 - (ahora - hechas[0]))
                if espera <= 0:
                    hechas.append(ahora)
                    self._no_antes_de[tenant] = ahora + SEGUNDOS_ENTRE_LLAMADAS
                    return
            self._dormir(espera)

    def _buscar(self, tenant, mac, olts, consultar) -> tuple[str, str]:
        if not olts:
            return "", SIN_OLT
        for olt_id in olts:
            self._esperar_turno(tenant)
            try:
                cuerpo = consultar(mac, str(olt_id)) or {}
            except Exception as e:                          # noqa: BLE001
                if _codigo_http(e) == 429:
                    with self._lock:
                        self._no_antes_de[tenant] = (
                            self._reloj() + _segundos_de_espera(e))
                return "", SIN_RESPUESTA
            #  'verified' es como la OLT dice que de verdad miro su tabla. Sin
            #  eso, cero coincidencias no prueba nada.
            if not cuerpo.get("verified"):
                return "", SIN_RESPUESTA
            coincidencias = [m for m in (cuerpo.get("matches") or [])
                             if isinstance(m, dict)]
            if len(coincidencias) > 1:
                return "", VARIAS
            if coincidencias:
                m = coincidencias[0]
                serial = str(m.get("sn") or m.get("onu_external_id") or "").strip()
                return (serial.upper(), UNA) if serial else ("", SIN_RESPUESTA)
        return "", NINGUNA

    def arrancar(self) -> None:
        """Un hilo de fondo que atiende la cola. Idempotente."""
        with self._lock:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._hilo = threading.Thread(target=self._bucle, name="onu-por-mac",
                                          daemon=True)
            self._hilo.start()

    def _bucle(self) -> None:
        while True:
            with self._lock:
                while not self._cola:
                    self._hay_trabajo.wait()
            self.procesar_uno()


_buscador: Buscador | None = None
_buscador_lock = threading.Lock()


def buscador() -> Buscador:
    """El buscador del proceso, con su hilo ya andando."""
    global _buscador
    with _buscador_lock:
        if _buscador is None:
            _buscador = Buscador()
        _buscador.arrancar()
        return _buscador
