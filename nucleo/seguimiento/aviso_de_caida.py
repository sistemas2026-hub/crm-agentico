# -*- coding: utf-8 -*-
"""
================================================================================
 AVISARLE A LOS CLIENTES DE UNA CAIDA DE RED  --  30/10/2026 (PRD §8.17, Ola 2)
================================================================================

Cuando se cae un PON, sus clientes escriben todos a la vez "no tengo internet".
Avisarles primero es la reduccion de volumen mas grande disponible. Ya estaba
decidido que lo APRUEBE UNA PERSONA antes de mandar (PRD §8.17): esto arma la
lista para que esa persona la mire, y despues manda por lotes lo que aprobo.

A QUIEN, Y A QUIEN NO
---------------------
  1. Las ONU del puerto en LOS, de SmartOLT, pidiendo solo serial, estado y
     hora (fields=, verificado el 19/10/2026: ningun dato de cliente viaja).
  2. De esas, SOLO LAS QUE CAYERON JUNTAS (grupo_de_la_falla): un puerto
     acumula equipos muertos hace meses -- medido el 21/08/2026, 10 de 17 --,
     y decirle a un ex cliente "estamos arreglando su servicio" es mentirle.
     Mismo criterio y misma ventana que nucleo/herramientas/incidentes.py.
  3. Serial -> servicio por el padron del ISP (buscar_cliente), en sus dos
     formas. Un equipo sin cliente se cuenta, no se adivina.
  4. Solo clientes en un estado que la empresa declaro
     (aviso_de_caida.estados_que_se_avisan). Sin declaracion, no se arma nada.

EL ENVIO
--------
Por la puerta comun (avisos.py): horario, baja, interruptor, modo prueba,
plantilla aprobada, una vez por clave. La clave es (situacion, servicio):
confirmar dos veces, o reintentar un lote, no avisa dos veces. Fuera del
horario el lote entero espera; un ISP que no contesta deja ese servicio
pendiente para la proxima vuelta.

La respuesta nunca lleva seriales ni telefonos: servicios y conteos.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

import requests

from nucleo.herramientas import http as ejecutor_http
from nucleo.herramientas.incidentes import _a_fecha
from nucleo.observabilidad.registro import registrar
from nucleo.seguimiento import buscar_cliente

EVENTO = "caida_masiva"
TIMEOUT_SEGUNDOS = 30
#: 200 por pagina y hasta 10 paginas: un puerto GPON tiene como mucho 128
#: equipos; mas que esto es un filtro que se ignoro, y se corta.
PAGINA = 200
PAGINAS_MAXIMAS = 10


class CaidaNoAvisable(Exception):
    """Por que no se puede armar el aviso, con un codigo fijo."""

    def __init__(self, codigo: str, http: int = 400):
        super().__init__(codigo)
        self.codigo = codigo
        self.http = http


def clave(situacion: str, servicio: str) -> str:
    return f"caida:{situacion}:{servicio}"


def grupo_de_la_falla(filas, ventana_minutos: int) -> tuple[list[str], str | None]:
    """
    Los seriales del grupo de caidas mas grande dentro de una ventana, y desde
    cuando. A igual tamaño, el mas reciente (la falla en curso). Solo LOS.
    """
    caidas = []
    for f in filas or []:
        if not isinstance(f, dict):
            continue
        if str(f.get("status") or "").strip().lower() != "los":
            continue
        cuando = _a_fecha(f.get("last_status_change"))
        sn = str(f.get("sn") or "").strip().upper()
        if cuando is not None and sn:
            caidas.append((cuando, sn))
    if not caidas:
        return [], None
    caidas.sort()
    ventana = timedelta(minutes=ventana_minutos)
    mejor: tuple[int, int, int] = (0, 0, 0)          # (tamaño, fin, inicio)
    inicio = 0
    for fin in range(len(caidas)):
        while caidas[fin][0] - caidas[inicio][0] > ventana:
            inicio += 1
        candidato = (fin - inicio + 1, fin, inicio)
        if candidato[:2] >= mejor[:2]:
            mejor = candidato
    _, fin, inicio = mejor
    grupo = caidas[inicio:fin + 1]
    return [sn for _, sn in grupo], grupo[0][0].strftime("%Y-%m-%d %H:%M:%S")


def _herramienta_optica(config):
    return next((h for h in config.herramientas if getattr(h, "detecta_incidente", False)), None)


def _en_los(config, tenant, herr, olt, board, port) -> list[dict]:
    base_url = ejecutor_http.base_url_de(herr, config.variables_tenant).rstrip("/")
    headers = ejecutor_http.headers_de(herr, tenant)
    filas, pagina, paginas = [], 1, 1
    while pagina <= min(paginas, PAGINAS_MAXIMAS):
        r = requests.get(f"{base_url}/api/onu/get_all_onus_details", headers=headers,
                         timeout=TIMEOUT_SEGUNDOS,
                         params={"olt_id": olt, "board": board, "port": port, "status": "los",
                                 "fields": "status,last_status_change,sn",
                                 "page": pagina, "page_size": PAGINA})
        r.raise_for_status()
        cuerpo = r.json() or {}
        filas.extend(cuerpo.get("onus") or [])
        total = cuerpo.get("total_pages")
        paginas = total if isinstance(total, int) and total > 0 else 1
        pagina += 1
    return filas


def _buscar(indice: dict, sn: str) -> dict | None:
    fila = indice.get(sn)
    if fila is None:
        hexa = ejecutor_http._gpon_hex(sn)
        fila = indice.get(str(hexa).upper()) if hexa else None
    return fila


def afectados(config, tenant: str, olt, board, port, *, leer=None) -> dict:
    """
    {'servicios', 'equipos_en_falla', 'sin_cliente', 'fuera_de_estado', 'desde'}
    o {'cargando': True} si el padron del ISP todavia se esta armando. Lanza
    CaidaNoAvisable si la empresa no lo configuro, o si SmartOLT no contesto.
    """
    aviso = config.aviso_de_caida
    if not aviso.estados_que_se_avisan:
        raise CaidaNoAvisable("NO_CONFIGURADO", 503)
    if leer is None:
        herr = _herramienta_optica(config)
        if herr is None:
            raise CaidaNoAvisable("NO_CONFIGURADO", 503)

        def leer():
            return _en_los(config, tenant, herr, olt, board, port)
    indice = buscar_cliente.padron_por_serial(config, tenant)
    if indice is None:
        return {"cargando": True}
    try:
        filas = leer()
    except Exception as e:                                       # noqa: BLE001
        registrar("aviso_de_caida", "no se pudo leer el puerto en SmartOLT", error=e)
        raise CaidaNoAvisable("OPTICO_NO_CONTESTA", 502)

    grupo, desde = grupo_de_la_falla(filas, aviso.ventana_misma_falla_minutos)
    base = {"equipos_en_falla": len(grupo), "sin_cliente": 0, "fuera_de_estado": 0,
            "desde": desde}
    if len(grupo) < aviso.minimo_equipos:
        return {**base, "servicios": [], "motivo": "sin_falla_comun"}
    servicios: set[str] = set()
    for sn in grupo:
        fila = _buscar(indice, sn)
        if fila is None:
            base["sin_cliente"] += 1
        elif fila.get("estado") not in aviso.estados_que_se_avisan:
            base["fuera_de_estado"] += 1
        else:
            servicios.add(str(fila["servicio"]))
    return {**base, "servicios": sorted(servicios, key=lambda s: (len(s), s))}


def lote_confirmado(pedidos: list[str], vigentes: dict) -> tuple[list[str], int]:
    """
    De los servicios que aprobo la persona, los que SIGUEN en la falla ahora.
    (lote, cuantos se descartaron). La lista no se le cree a quien la manda:
    se cruza con lo que el motor acaba de leer. Y un cliente cuyo equipo
    volvio entre la aprobacion y su lote no recibe un aviso de una falla que
    para el ya termino.
    """
    vivos = set(vigentes.get("servicios") or [])
    lote = [s for s in pedidos if s in vivos]
    return lote, len(pedidos) - len(lote)


def avisar_lote(servicios: list[str], avisar_uno) -> dict:
    """
    Manda el aviso a cada servicio del lote. avisar_uno(servicio) -> lo que
    contesto avisos.avisar. {'enviados', 'motivos', 'pendientes', 'reintentar_en'}.
    """
    enviados, motivos, pendientes, reintentar = 0, {}, [], None
    for i, servicio in enumerate(servicios):
        r = avisar_uno(servicio) or {}
        if r.get("motivo") == "todavia_no":
            #  El horario es de la empresa, no del servicio: si este espera,
            #  esperan todos. No se pregunta por el resto.
            return {"enviados": enviados, "motivos": motivos,
                    "pendientes": list(servicios[i:]) + pendientes,
                    "reintentar_en": r.get("reintentar_en")}
        if r.get("enviado"):
            enviados += 1
            continue
        motivo = str(r.get("motivo") or "desconocido")
        motivos[motivo] = motivos.get(motivo, 0) + 1
        if r.get("reintentar_en") is not None:
            pendientes.append(servicio)
            reintentar = max(reintentar or 0, int(r["reintentar_en"]))
    return {"enviados": enviados, "motivos": motivos, "pendientes": pendientes,
            "reintentar_en": reintentar}
