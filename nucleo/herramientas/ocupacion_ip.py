# -*- coding: utf-8 -*-
"""
================================================================================
 QUE DIRECCIONES IP ESTAN OCUPADAS, POR PREFIJO
================================================================================
Generico a proposito: no sabe que "WispHub" existe, ni que "Rapilink" existe,
ni que `172.16.x` significa algo. Recorre el listado paginado que declara
`Herramienta.sincroniza_ocupacion_ip`, lee UN campo por fila --el que nombra
`Herramienta.campo_ip_sync`-- y devuelve, por prefijo /24, que ultimos octetos
estan tomados.

POR QUE EXISTE  --  14/11/2026
------------------------------
Cuando se instala un cliente nuevo, **la IP la elige el tecnico en la casa**
(decision del usuario). Hoy la saca de una lupa en el panel del proveedor, y
ese listado NO esta en la API: medido ese dia, el indice del spec tiene 54
rutas y ninguna es de direcciones libres.

Para poder ofrecerle las libres --en vez de pedirle que teclee una IP, que es
como un cliente queda sin servicio o dos chocan-- hay que saber que esta
tomado. El dato existe, repartido en una fila por cliente.

LO QUE ESTE MODULO NO SABE, Y NO PUEDE
--------------------------------------
**Que una direccion libre sea USABLE.** Los equipos de red --antenas, switches,
cajas-- no son clientes, asi que no estan en el listado y esta resta no los ve.
Si una direccion la tiene una antena, aca aparece libre. Dice «ningun cliente
la tiene», que es otra cosa, y quien llama tiene que decirlo igual de claro.

LO QUE SE APRENDIO MIDIENDO, Y POR ESO SE CUENTA POR PREFIJO Y NO POR ZONA
--------------------------------------------------------------------------
La primera version agrupaba por zona. En produccion, `172.16.9.0/24` tenia 42
clientes en una zona y 211 en otra --y las dos zonas eran el mismo servidor con
distinto dia de corte de factura--: restando solo los de una, el informe decia
«212 libres» donde habia UNA.

En 16 prefijos la suma de las dos zonas nunca pasaba de 254 y nueve estaban al
98-99%: no eran dos redes, era una. Por eso la ocupacion es **global por
prefijo**: la zona dice de que prefijos se puede sacar, pero lo tomado se
cuenta sobre todos los clientes, sin importar en que zona esten.

NO SE LLAMA DURANTE UNA CONVERSACION. Son decenas de llamadas al proveedor:
es un job bajo demanda, como `localidades.py`, y su resultado se guarda en la
config del tenant.
================================================================================
"""

from __future__ import annotations

import ipaddress

import requests

from nucleo.herramientas.http import ErrorHerramientaHttp, headers_de, url_de

TIMEOUT_SEGUNDOS = 30
#: El mismo tope que `localidades.py`: pedir 500 o 1000 igual devuelve 300.
TAMANIO_PAGINA = 300

#: Cuantas paginas como maximo. Un bucle roto no hace mil llamadas al
#: proveedor: corta y lo dice (`completo=False`).
MAX_PAGINAS = 200

#: El primer y el ultimo octeto de un /24 no son de un cliente: `.0` es la red
#: y `.255` el broadcast. No es una convencion de este proyecto, es IPv4.
RED = 0
BROADCAST = 255

#: `.1` TAMPOCO se ofrece, y esto SI es una medicion y no una regla general.
#:
#: El usuario dijo el 14/11/2026 que se usan las 254 y que solo quedan fuera la
#: primera y la ultima. Cierto para `.0` y `.255`; para el `.1` los datos
#: dijeron otra cosa: estaba libre en 83 de 86 pools, incluido uno con 240 de
#: 254 ocupadas. Si fuera asignable, en un pool al 94% tendria que estar tomado
#: nueve de cada diez veces. Es la puerta de enlace.
#:
#: Se deja como constante y no escondido en un `range(2, ...)` para que la
#: proxima empresa pueda discutirlo con el dato a la vista.
PUERTA_DE_ENLACE = 1


def prefijo_de(ip: str) -> str:
    """El /24 de una IP, como texto terminado en punto. '' si no es una IP.

    Se usa `ipaddress` y no un `split('.')` a proposito: '10.0.0.1.5',
    '10.0.0', '  ' y '169.254.1.1/24' son todos texto que un `split` deja
    pasar y que no son una direccion.
    """
    try:
        red = ipaddress.ip_network(f"{str(ip).strip()}/24", strict=False)
    except ValueError:
        return ""
    if red.version != 4:
        return ""
    return str(red.network_address).rsplit(".", 1)[0] + "."


def _ultimo_octeto(ip: str) -> int | None:
    try:
        direccion = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    if direccion.version != 4:
        return None
    return int(str(direccion).rsplit(".", 1)[1])


def sincronizar(herramienta, tenant: str | None = None,
                variables_tenant: dict | None = None) -> dict:
    """Recorre TODO el listado y devuelve que esta ocupado, por prefijo.

        {"ocupacion": {"172.16.9.": [2, 3, 7, ...]},
         "leidos": 7679,
         "sin_ip": 12,
         "ilegibles": ["no-es-una-ip", ...],
         "completo": True}

    `completo=False` significa que se corto por `MAX_PAGINAS` y que la
    ocupacion esta INCOMPLETA: quien llama no puede ofrecer direcciones libres
    a partir de una lectura parcial, porque lo que falto leer es justamente lo
    que haria que una direccion pareciera libre.
    """
    if herramienta.tipo not in ("agregado", "http"):
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no sirve como fuente de ocupacion de IP "
            f"(tipo '{herramienta.tipo}', se espera 'agregado' o 'http').")

    campo = herramienta.campo_ip_sync
    if not campo:
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no declara 'campo_ip_sync': sin saber que "
            f"columna trae la direccion, no hay nada que leer.")

    headers = headers_de(herramienta, tenant)
    url = url_de(herramienta, variables_tenant=variables_tenant)

    ocupacion: dict[str, set] = {}
    leidos = sin_ip = 0
    ilegibles: list[str] = []
    completo = False
    offset = 0
    total_esperado: int | None = None

    for _ in range(MAX_PAGINAS):
        r = requests.get(url, headers=headers,
                         params={"limit": TAMANIO_PAGINA, "offset": offset},
                         timeout=TIMEOUT_SEGUNDOS)
        r.raise_for_status()
        payload = r.json()
        filas = (payload.get("results", []) if isinstance(payload, dict)
                 else (payload or []))
        if total_esperado is None:
            total_esperado = (payload.get("count")
                              if isinstance(payload, dict) else len(filas))

        for fila in filas:
            if not isinstance(fila, dict):
                continue
            leidos += 1
            crudo = str(fila.get(campo) or "").strip()
            if not crudo:
                sin_ip += 1
                continue
            pref = prefijo_de(crudo)
            ultimo = _ultimo_octeto(crudo)
            if not pref or ultimo is None:
                #  Se guardan unas pocas para poder mirarlas, no todas: es
                #  texto que escribio una persona y puede ser cualquier cosa.
                if len(ilegibles) < 20:
                    ilegibles.append(crudo[:40])
                continue
            ocupacion.setdefault(pref, set()).add(ultimo)

        if not filas or len(filas) < TAMANIO_PAGINA:
            completo = True
            break
        offset += TAMANIO_PAGINA
        if total_esperado is not None and offset >= total_esperado:
            completo = True
            break

    return {
        "ocupacion": {p: sorted(o) for p, o in sorted(ocupacion.items())},
        "leidos": leidos,
        "sin_ip": sin_ip,
        "ilegibles": ilegibles,
        "completo": completo,
    }


def libres_de(prefijo: str, ocupados, cuantas: int | None = None) -> list[str]:
    """Las direcciones de un /24 que ningun cliente tiene.

    Fuera: la red (`.0`), el broadcast (`.255`) y la puerta de enlace (`.1`).
    `cuantas` recorta la lista -- una pantalla no necesita 253 opciones.

    NO DICE «USABLES». Un equipo de red no es un cliente y no esta en el
    listado, asi que una direccion que tenga una antena sale de aca como
    libre. Quien muestre esto tiene que decirlo con esas palabras.
    """
    pref = str(prefijo or "").strip()
    if not pref.endswith("."):
        pref = prefijo_de(pref + "0") or ""
    if not pref:
        return []
    tomados = set(ocupados or ())
    salida = [f"{pref}{n}" for n in range(1, 255)
              if n not in tomados and n != PUERTA_DE_ENLACE]
    return salida[:cuantas] if cuantas else salida
