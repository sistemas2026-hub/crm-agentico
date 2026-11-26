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

from nucleo.seguridad.redaccion import redactar
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
         "por_zona": {"20049": {"172.16.9.": 211, ...}},
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
    #  CUANTOS CLIENTES DE CADA ZONA EN CADA PREFIJO (25/11/2026). No cambia
    #  lo de arriba --la ocupacion sigue siendo global por prefijo--: sirve
    #  para SUGERIR los rangos de cada servidor. Solo conteos.
    por_zona: dict[str, dict[str, int]] = {}
    campo_zona = getattr(herramienta, "campo_zona_sync", "") or ""
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
                    #  REDACTADO, no crudo  --  revisor de PII, 14/11/2026.
                    #
                    #  Este campo lo teclea una persona, y todo lo que no sea
                    #  una IPv4 valida cae aca: medido en el interprete, una
                    #  cedula de 10 digitos, un telefono y «casa de juan
                    #  perez» los tres dan ValueError en `ipaddress` y terminan
                    #  en esta lista. Y esta lista sale por HTTP.
                    #
                    #  Se redacta en vez de borrarse porque sin ver QUE FORMA
                    #  tiene el valor malo nadie puede ir a corregir la fila,
                    #  que es para lo que se guardo. `redactar` saca cedula,
                    #  telefono, email, URL y coordenadas.
                    #
                    #  LO QUE NO CUBRE, y queda dicho: nombres propios y
                    #  direcciones en prosa. Si hace falta cero PII, lo que
                    #  sigue es devolver una clasificacion («3 con letras, 1
                    #  solo digitos») en vez del texto, y eso pierde la
                    #  capacidad de encontrar la fila. Es una decision del
                    #  usuario, no de este modulo.
                    ilegibles.append(redactar(crudo[:40]))
                continue
            ocupacion.setdefault(pref, set()).add(ultimo)
            zona = _zona_de(fila.get(campo_zona)) if campo_zona else ""
            if zona:
                cuenta = por_zona.setdefault(zona, {})
                cuenta[pref] = cuenta.get(pref, 0) + 1

        if not filas or len(filas) < TAMANIO_PAGINA:
            completo = True
            break
        offset += TAMANIO_PAGINA
        if total_esperado is not None and offset >= total_esperado:
            completo = True
            break

    return {
        "ocupacion": {p: sorted(o) for p, o in sorted(ocupacion.items())},
        "por_zona": {z: dict(sorted(c.items())) for z, c in sorted(por_zona.items())},
        "leidos": leidos,
        "sin_ip": sin_ip,
        "ilegibles": ilegibles,
        "completo": completo,
    }


def _zona_de(valor) -> str:
    """El id de la zona de una fila, como texto, o vacio.

    El proveedor la manda como objeto `{id, nombre}` (medido el 25/11/2026: 300
    de 300 filas). Se acepta tambien el id suelto. Un nombre suelto NO: casarlo
    con el catalogo seria adivinar, y esto es para sugerir, no para inventar.
    """
    if isinstance(valor, dict):
        valor = valor.get("id")
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, int):
        return str(valor) if valor > 0 else ""
    texto = str(valor or "").strip()
    return texto if texto.isdigit() and int(texto) > 0 else ""


#: Cuantos clientes de una zona tiene que haber en un prefijo para SUGERIRLO
#: como rango de esa zona. Medido el 14/11/2026: los pools de verdad tienen
#: cientos; decenas de prefijos tienen UNO (equipos mal cargados, link-local,
#: LANs privadas metidas en el campo de la IP). Diez deja afuera el ruido y no
#: esconde un pool nuevo que se este empezando a llenar.
MINIMO_PARA_SUGERIR = 10


def sugeridos_por_zona(por_zona: dict) -> dict[str, list[dict]]:
    """Los prefijos que conviene SUGERIR para cada zona, de mas a menos usado.

        {"20049": [{"prefijo": "172.16.9.", "clientes": 211}, ...]}

    Fuera siempre `169.254.x` (link-local: la direccion que un equipo se da
    solo cuando no hay DHCP) aunque tenga clientes. Es una sugerencia: la
    empresa la revisa y la guarda, o no.

    CADA UNO DICE SI ES DE RED PRIVADA (`privado`), y la pantalla solo llena
    sola los privados. Medido el 25/11/2026 en la primera empresa: junto a sus
    25 pools `172.16.x` aparecian 51 prefijos `168.0.x`/`168.16.x` --con el
    mismo tercer numero que los `172.16.x`-- con decenas de clientes cada uno.
    Que son (una red publica de verdad, o direcciones mal tecleadas) no lo
    sabe el codigo: se muestran aparte y lo decide una persona.
    """
    import ipaddress as _ip

    def _privado(pref: str) -> bool:
        try:
            return _ip.ip_address(f"{pref}1").is_private
        except ValueError:
            return False

    salida: dict[str, list[dict]] = {}
    for zona, conteos in (por_zona or {}).items():
        filas = [{"prefijo": p, "clientes": int(n), "privado": _privado(p)}
                 for p, n in (conteos or {}).items()
                 if int(n) >= MINIMO_PARA_SUGERIR and not str(p).startswith("169.254.")]
        if filas:
            salida[str(zona)] = sorted(filas, key=lambda f: (-f["clientes"], f["prefijo"]))
    return salida


def sombra_de_mal_escritas(ocupacion: dict) -> dict[str, set[int]]:
    """Por TERCER numero del prefijo, los ultimos octetos que tienen clientes
    cuya IP NO es de red privada.

        {"4": {25, 31, ...}}   <- hay un 168.16.4.25 y un 168.0.4.31

    POR QUE EXISTE  --  25/11/2026. Para la empresa cuyos clientes tengan IP
    MAL ESCRITAS en el proveedor: la IP real de esos clientes no esta en
    ningun lado que la plataforma pueda leer, asi que una direccion del rango
    puede aparecer libre y estar en uso. Es una opcion de la empresa
    (`contar_ip_mal_escritas`), apagada de fabrica.

    LA PRIMERA EMPRESA LA TIENE APAGADA, y la historia vale: se construyo
    creyendo que sus 2.360 IP `168.x`/`100.x` eran errores, y al sacar la
    lista resulto que 2.356 eran de clientes CANCELADOS --el usuario confirmo
    que al cancelar se les cambia la IP para liberar la verdadera--. No hay
    nada que proteger ahi. Medir antes de tratar un dato raro como error.

    La regla, generica y declarada: una IP fuera de red privada se toma como
    un posible error de digitacion en los PRIMEROS numeros, y la direccion de
    cualquier rango con los mismos dos ultimos numeros no se ofrece. Es
    conservadora a proposito: pierde direcciones libres (medido: de 951, 1.398
    y 359 libres por servidor quedan 299, 693 y 330), y a cambio no le da a un
    cliente nuevo la IP de uno que ya existe.

    No arregla nada en el proveedor: el arreglo de verdad es corregir esas
    fichas. Esto evita que el error se reparta mientras tanto.
    """
    import ipaddress as _ip

    sombra: dict[str, set[int]] = {}
    for pref, octetos in (ocupacion or {}).items():
        try:
            if _ip.ip_address(f"{pref}1").is_private:
                continue
        except ValueError:
            continue
        partes = str(pref).rstrip(".").split(".")
        if len(partes) != 3:
            continue
        sombra.setdefault(partes[2], set()).update(int(o) for o in (octetos or []))
    return sombra


def tomadas_en(prefijo: str, ocupacion: dict, sombra: dict | None = None) -> set[int]:
    """Los ultimos octetos de ese /24 que NO se ofrecen: los que tiene un
    cliente, y --si se pasa la sombra-- los que podria tener uno con la IP mal
    escrita."""
    tomadas = set(int(o) for o in ((ocupacion or {}).get(prefijo) or []))
    if sombra:
        partes = str(prefijo).rstrip(".").split(".")
        if len(partes) == 3:
            tomadas |= sombra.get(partes[2], set())
    return tomadas


def normalizar_prefijo(texto) -> str:
    """'172.16.9', '172.16.9.' o '172.16.9.0/24' -> '172.16.9.'. Vacio si no es
    un /24 de IPv4. Lo que la persona escribe pasa por aca antes de guardarse."""
    t = str(texto or "").strip()
    if t.endswith("/24"):
        t = t[:-3]
    partes = t.rstrip(".").split(".")
    if len(partes) == 4 and partes[3] == "0":
        partes = partes[:3]
    if len(partes) != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in partes):
        return ""
    return ".".join(str(int(p)) for p in partes) + "."


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
