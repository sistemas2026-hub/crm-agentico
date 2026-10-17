# -*- coding: utf-8 -*-
"""
================================================================================
 PRECIO DE CADA PLAN  --  sincronizado, nunca consultado en el camino caliente
================================================================================

POR QUE UN JOB Y NO UNA CONSULTA AL VUELO
-----------------------------------------
El precio no esta en el listado de planes: `/api/plan-internet/` devuelve tres
campos --id, nombre, tipo-- y nada mas. Medido el 07/10/2026 contra la
instancia real: 50 planes, ningun precio.

El precio vive en el DETALLE, uno por uno:

    GET /api/plan-internet/queue/{id}/
        precio       "199900.00"
        bajada       "700M"
        descripcion  "PLAN ELITE (700MB + TV + DISNEY+ + CAMARA)"

O sea que saber el precio de los 50 planes son 50 llamadas. Hacerlas cuando
alguien reparte el trabajo repetiria un error que este proyecto ya pago: sacar
`contar_clientes` del camino caliente de 'ventas' costo un incidente el
20/08/2026 porque agregaba 1-2s de latencia POR MENSAJE. Un precio que cambia
pocas veces al año no se pregunta cada vez que se usa.

Mismo patron que `localidades.py`: un job bajo demanda que recorre y guarda, y
quien lo necesita lee lo guardado.

EL PRECIO ES TEXTO, Y HAY QUE CONVERTIRLO
-----------------------------------------
Llega como "199900.00". Comparado como texto, "99900" queda POR ENCIMA de
"199900" --porque '9' es mayor que '1'-- y el plan mas caro quedaria ultimo.
Es el tipo de error que no falla con dos planes de prueba y si con cincuenta
en produccion.

LO QUE ESTE MODULO NO HACE
--------------------------
No decide que es un "plan alto". Guarda el numero; donde esta el corte es una
decision de negocio y vive en quien ordena, no aca.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import requests

from nucleo.herramientas.http import headers_de, url_de
from nucleo.observabilidad.registro import registrar

TIMEOUT_SEGUNDOS = 30

#: Cuantos planes se recorren como maximo en una corrida.
#:
#: No es una preferencia: son 50 en la instancia medida, y el tope evita que un
#: catalogo que crezca sin control convierta el job en algo que nunca termina.
#: Si se alcanza, se dice -- un corte silencioso haria creer que se recorrio
#: todo.
MAX_PLANES = 300


def a_decimal(texto) -> Decimal | None:
    """El precio como numero, o `None` si no se puede leer.

    `None` NO es cero: un plan sin precio legible no es un plan gratis, y
    tratarlo como cero lo mandaria al fondo del orden como si fuera el mas
    barato de todos.
    """
    if texto is None:
        return None
    try:
        return Decimal(str(texto).strip().replace(",", ""))
    except (InvalidOperation, ValueError, AttributeError):
        return None


def sincronizar(herramienta_listado, herramienta_detalle, tenant: str,
                variables_tenant: dict | None = None) -> dict:
    """Recorre el catalogo y devuelve {id: {nombre, precio, bajada}}.

    Las dos herramientas se pasan en vez de fijarse aca: el endpoint, el
    header de auth y el subdominio son del tenant, no de este modulo. Un ISP
    nuevo que tenga otro proveedor declara sus herramientas y esto funciona
    igual -- que es la regla de nucleo/ que ARQUITECTURA hace cumplir.
    """
    salida: dict = {}
    base = url_de(herramienta_listado, {}, variables_tenant or {})
    cabeceras = headers_de(herramienta_listado, tenant)

    try:
        r = requests.get(base, headers=cabeceras, timeout=TIMEOUT_SEGUNDOS)
        r.raise_for_status()
        cuerpo = r.json()
    except Exception as e:
        registrar("planes", "no se pudo leer el catalogo de planes", error=e)
        return {"planes": {}, "truncado": False, "error": True}

    filas = cuerpo.get("results") if isinstance(cuerpo, dict) else cuerpo
    filas = list(filas or [])
    truncado = len(filas) > MAX_PLANES
    if truncado:
        filas = filas[:MAX_PLANES]

    for fila in filas:
        if not isinstance(fila, dict) or not fila.get("id"):
            continue
        plan_id = str(fila["id"])
        detalle_url = url_de(
            herramienta_detalle, {"id_plan": plan_id}, variables_tenant or {}
        )
        try:
            d = requests.get(
                detalle_url,
                headers=headers_de(herramienta_detalle, tenant),
                timeout=TIMEOUT_SEGUNDOS,
            )
            if d.status_code != 200:
                # Un plan que no responde NO se inventa ni se saltea en
                # silencio: se omite y queda fuera del catalogo, asi que quien
                # lo lea va a ver que no esta en vez de un precio falso.
                continue
            detalle = d.json()
        except Exception as e:
            registrar("planes", "no se pudo leer el detalle de un plan",
                      error=e)
            continue

        precio = a_decimal(detalle.get("precio"))
        salida[plan_id] = {
            "nombre": (detalle.get("nombre") or fila.get("nombre") or "").strip(),
            # Se guarda como texto para que el JSON no pierda decimales, pero
            # ya validado como numero: lo que no se pudo leer viaja como None
            # y no como "0".
            "precio": str(precio) if precio is not None else None,
            "bajada": (detalle.get("bajada") or "").strip(),
            "descripcion": (detalle.get("descripcion") or "").strip(),
        }

    return {"planes": salida, "truncado": truncado, "error": False}
