# -*- coding: utf-8 -*-
"""
================================================================================
 SINCRONIZACION DE LOCALIDADES  --  localidad -> zona(s) real(es)
================================================================================

Generico a proposito: no sabe que "WispHub" existe, ni que "Rapilink"
existe. Recorre el endpoint que declara 'Herramienta.sincroniza_localidades'
(cualquier listado paginado con 'count'/'results', tipo {count, results}),
lee dos campos por fila -- 'campo_localidad_sync' (texto) y
'campo_zona_sync' (objeto {id, nombre}) -- y arma el catalogo
TenantConfig.localidades (ver nucleo/config/schema.py:LocalidadZona).

No lo llama nunca el motor durante una conversacion. Es un job bajo
demanda (boton "Actualizar localidades" en /settings/planes-venta, ver
nucleo/canales/api.py) -- nace de sacar contar_clientes del camino
caliente de 'ventas' (agregaba 1-2s de latencia por mensaje, ver
incidente 20/08/2026, "doña manuela").
================================================================================
"""

from __future__ import annotations

import requests

from nucleo.config.schema import LocalidadZona, ZonaConteo, _sin_tildes
from nucleo.herramientas.http import ErrorHerramientaHttp, headers_de, url_de

TIMEOUT_SEGUNDOS = 30
# Tope real observado del proveedor (WispHub): pedir limit=500 o 1000
# igual devuelve 300 filas. No es un numero elegido a mano.
TAMANIO_PAGINA = 300


def sincronizar(herramienta, tenant: str | None = None,
                variables_tenant: dict | None = None) -> list[LocalidadZona]:
    """
    Recorre TODO el endpoint de 'herramienta' (paginado por offset) y
    agrupa por localidad normalizada (_sin_tildes: minusculas, sin tildes
    -- mismo criterio que ya usa el proyecto para comparar texto que
    escribio una persona). Una fila sin localidad se ignora; una fila con
    localidad pero sin zona reconocible se cuenta igual (localidad
    presente, sin zona asociada).

    Puede tardar decenas de segundos en una base de miles de clientes --
    no se llama desde el camino de una conversacion.
    """
    if herramienta.tipo not in ("agregado", "http"):
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no sirve como fuente de sincronizacion "
            f"de localidades (tipo '{herramienta.tipo}', se espera 'agregado' "
            f"o 'http').")

    headers = headers_de(herramienta, tenant)
    url = url_de(herramienta, variables_tenant=variables_tenant)

    campo_localidad = herramienta.campo_localidad_sync
    campo_zona = herramienta.campo_zona_sync

    # clave normalizada -> {"display": str, "zonas": {zona_id: {"nombre": str, "n": int}}}
    agregados: dict[str, dict] = {}

    offset = 0
    total_esperado: int | None = None
    while True:
        params = {"limit": TAMANIO_PAGINA, "offset": offset}
        r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SEGUNDOS)
        r.raise_for_status()
        payload = r.json()
        filas = payload.get("results", []) if isinstance(payload, dict) else (payload or [])
        if total_esperado is None:
            total_esperado = payload.get("count") if isinstance(payload, dict) else len(filas)

        for fila in filas:
            if not isinstance(fila, dict):
                continue
            localidad = str(fila.get(campo_localidad) or "").strip()
            if not localidad:
                continue
            clave = _sin_tildes(localidad)
            entrada = agregados.setdefault(clave, {"display": localidad, "zonas": {}})

            zona = fila.get(campo_zona)
            if isinstance(zona, dict) and zona.get("id") is not None:
                zid = zona["id"]
                z = entrada["zonas"].setdefault(zid, {"nombre": zona.get("nombre", ""), "n": 0})
                z["n"] += 1

        if not filas or len(filas) < TAMANIO_PAGINA:
            break
        offset += TAMANIO_PAGINA
        if total_esperado is not None and offset >= total_esperado:
            break

    return [
        LocalidadZona(
            localidad=entrada["display"],
            zonas=[ZonaConteo(zona_id=zid, zona_nombre=z["nombre"], n_clientes=z["n"])
                   for zid, z in entrada["zonas"].items()],
            n_clientes=sum(z["n"] for z in entrada["zonas"].values()),
        )
        for entrada in agregados.values()
    ]
