# -*- coding: utf-8 -*-
"""
================================================================================
 BUSCAR AL CLIENTE POR SERVICIO, CEDULA O NOMBRE  --  28/10/2026
================================================================================

"Nuevo ticket" pedia el numero de servicio y nada mas. Quien atiende una
llamada casi nunca lo tiene: tiene el nombre, o la cedula. Esto busca por las
tres y devuelve SOLO servicio, nombre y estado -- lo mismo que ya mostraba
"Verificar" (ticket_desde_dexter.titular). La ficha cruda trae cedula,
telefono, GPS y cuatro contraseñas, y nada de eso sale de aca.

LAS TRES BUSQUEDAS
------------------
  * Solo digitos: como servicio Y como cedula, las dos. Una cedula tambien son
    digitos, y adivinar cual de las dos escribio la persona es justo el error
    que no se ve: le traeria otro cliente con aspecto de respuesta correcta.
  * Texto: contra un PADRON en memoria. El filtro por nombre del proveedor no
    alcanza -- el de WispHub compara EXACTO contra los nombres de pila, sin
    apellidos: '?nombre=MARIA' trae 27 de 7.574, '?nombre=MAR' trae 0, y en una
    muestra de 300 clientes ya habia 31 con MARIA en el nombre (medido el
    28/10/2026, metodo del valor imposible). Sin padron, buscar por nombre
    devolveria menos de lo que hay y no lo diria.

EL PADRON
---------
Servicio, nombre y estado de cada cliente -- nada mas --, recorriendo el
listado paginado del proveedor (26 paginas de 300, cerca de un minuto en
Rapilink). Vive en la RAM del proceso y no se escribe a disco ni a la base.
Se arma la primera vez que alguien busca por nombre, en un hilo aparte: esa
primera busqueda contesta 'cargando' en vez de colgar la pantalla un minuto.
Vencido ('padron_vigencia_horas'), se sigue usando el viejo mientras se arma
el nuevo: un cliente dado de alta hace cinco horas puede no aparecer por
nombre, y por servicio o cedula si.

La busqueda NUNCA va al log: es el nombre o la cedula de una persona.
================================================================================
"""

from __future__ import annotations

import threading
import time
import unicodedata

from nucleo.herramientas import http as ejecutor_http
from nucleo.observabilidad.registro import registrar
from nucleo.seguimiento import importacion_io

#: Tope de resultados por busqueda: mas que esto es una busqueda que hay que
#: afinar, no una lista para leer.
MAXIMO = 15
#: El proveedor corta cada pagina en 300 aunque se le pida mas (medido el
#: 28/10/2026 con limit=1000 y limit=2000: 300 filas las dos veces).
PAGINA = 300

_PADRONES: dict[str, dict] = {}
_CARGANDO: set[str] = set()
_CANDADO = threading.Lock()


class BusquedaInvalida(Exception):
    """Por que no se busco, con un codigo fijo que la pantalla traduce."""

    def __init__(self, codigo: str, http: int = 400):
        super().__init__(codigo)
        self.codigo = codigo
        self.http = http


def _normal(texto: str) -> str:
    """Mayusculas y sin tildes: 'Muñoz' y 'MUNOZ' son la misma busqueda."""
    sin = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sin if not unicodedata.combining(c)).upper()


def _fila(fila: dict, servicio=None) -> dict | None:
    s = str(servicio if servicio is not None else fila.get("id_servicio") or "").strip()
    if not s:
        return None
    return {"servicio": s, "nombre": fila.get("nombre") or "",
            "estado": fila.get("estado") or ""}


def _herramienta_con_filtro(config, filtro: str):
    """La que DECLARA ese filtro verificado -- la misma regla que resolver_servicios."""
    return next((h for h in config.herramientas
                 if h.tipo == "http" and filtro in (h.filtros_verificados or {})), None)


def _por_cedula(config, tenant: str, cedula: str) -> list[dict]:
    herr = _herramienta_con_filtro(config, "cedula")
    if herr is None:
        return []
    param = herr.filtros_verificados["cedula"].param
    datos = ejecutor_http.ejecutar(herr, {param: cedula}, tenant,
                                   variables_tenant=config.variables_tenant)
    filas = datos.get("results") if isinstance(datos, dict) else datos
    return [f for f in (_fila(x) for x in (filas or []) if isinstance(x, dict)) if f]


def _cargar(config, tenant: str) -> None:
    """Recorre el listado entero y deja el padron. Corre en un hilo aparte."""
    try:
        herr = _herramienta_con_filtro(config, "id_servicio")
        if herr is None:
            return
        filas, desde, total = [], 0, None
        while True:
            datos = ejecutor_http.ejecutar(herr, {"limit": PAGINA, "offset": desde}, tenant,
                                           variables_tenant=config.variables_tenant)
            pagina = (datos.get("results") if isinstance(datos, dict) else datos) or []
            if total is None and isinstance(datos, dict):
                total = datos.get("count")
            for x in pagina:
                f = _fila(x) if isinstance(x, dict) else None
                if f:
                    f["_clave"] = _normal(f["nombre"])
                    filas.append(f)
            desde += PAGINA
            if not pagina or (total is not None and desde >= total):
                break
        with _CANDADO:
            _PADRONES[tenant] = {"filas": filas, "cuando": time.monotonic()}
        registrar("buscar_cliente", "padron cargado", tenant=tenant, filas=len(filas))
    except Exception as e:                                       # noqa: BLE001
        registrar("buscar_cliente", "no se pudo cargar el padron", tenant=tenant, error=e)
    finally:
        with _CANDADO:
            _CARGANDO.discard(tenant)


def _padron(config, tenant: str) -> list[dict] | None:
    """El padron vigente (o el vencido mientras se arma otro). None = todavia no hay."""
    vigencia = config.tickets_desde_dexter.padron_vigencia_horas * 3600
    with _CANDADO:
        p = _PADRONES.get(tenant)
        vencido = p is None or time.monotonic() - p["cuando"] >= vigencia
        if vencido and tenant not in _CARGANDO:
            _CARGANDO.add(tenant)
            threading.Thread(target=_cargar, args=(config, tenant),
                             name=f"padron-{tenant}", daemon=True).start()
    return p["filas"] if p else None


def _por_nombre(filas: list[dict], texto: str) -> list[dict]:
    """Todas las palabras tienen que estar; primero los que EMPIEZAN asi."""
    q = _normal(texto)
    palabras = q.split()
    hallados = [f for f in filas if all(p in f["_clave"] for p in palabras)]
    hallados.sort(key=lambda f: (not f["_clave"].startswith(q), f["_clave"]))
    return hallados


def buscar(config, tenant: str, texto) -> dict:
    """
    {'resultados': [{servicio, nombre, estado}], 'mas': bool, 'cargando': bool}

    'mas' = hubo mas de MAXIMO: hay que afinar. 'cargando' = el padron se esta
    armando y la busqueda por nombre todavia no puede contestar.
    """
    t = " ".join(str(texto or "").split())
    if len(t) < 3:
        raise BusquedaInvalida("BUSQUEDA_CORTA")
    if t.isdigit():
        if len(t) > 12:
            raise BusquedaInvalida("BUSQUEDA_CORTA")
        vistos, resultados = set(), []
        ficha = importacion_io.resolver_servicios(config, tenant)([t]).get(t)
        candidatos = ([_fila(ficha, servicio=t)] if ficha else []) + _por_cedula(config, tenant, t)
        for f in candidatos:
            if f and f["servicio"] not in vistos:
                vistos.add(f["servicio"])
                resultados.append(f)
        return {"resultados": resultados[:MAXIMO], "mas": len(resultados) > MAXIMO,
                "cargando": False}
    if not config.tickets_desde_dexter.buscar_por_nombre:
        raise BusquedaInvalida("SIN_BUSQUEDA_POR_NOMBRE")
    filas = _padron(config, tenant)
    if filas is None:
        return {"resultados": [], "mas": False, "cargando": True}
    hallados = _por_nombre(filas, t)
    return {"resultados": [{k: f[k] for k in ("servicio", "nombre", "estado")}
                           for f in hallados[:MAXIMO]],
            "mas": len(hallados) > MAXIMO, "cargando": False}
