# -*- coding: utf-8 -*-
"""
================================================================================
 QUE RANGOS DE IP USA CADA ZONA, LEIDOS DE LOS CLIENTES QUE YA EXISTEN
================================================================================
SOLO LECTURA. Ni una escritura contra la plataforma del ISP.

POR QUE EXISTE  --  14/11/2026
------------------------------
Decision del usuario: cuando se instala un cliente nuevo, **la IP la elige el
tecnico en la casa**. En el panel de WispHub aprieta una lupa, le salen las
disponibles y toma cualquiera.

Ese listado NO esta en la API: medido el 14/11/2026 con
`cli/sondear_api.py --campos`, `/api/zonas/` devuelve DOS campos (`id`,
`nombre`) y `/api/router/` devuelve la IP **del router**, no un pool. La lupa
vive en el panel (`wisphub.io`), no en `api.wisphub.io`.

Entonces, para poder OFRECERLE al tecnico las libres --en vez de pedirle que
teclee una IP, que es como un cliente queda sin servicio o dos clientes chocan--
hay que saber el rango de cada zona. Y antes de pedirle al usuario que lo
escriba a mano, conviene LEERLO de los 7.677 clientes que ya estan instalados:
el dato existe, solo que repartido en filas.

QUE SACA, Y QUE NO
------------------
Por zona y por router: el prefijo /24 de las IP en uso, cuantas hay y cuales
quedan libres dentro de ese prefijo.

**NADA DEL CLIENTE.** Ni nombre, ni cedula, ni telefono, ni direccion, ni
coordenadas: este script lee `ip`, `ip_local`, `zona` y `router`, y de esos solo
publica agregados. Una IP suelta no se imprime junto a nada que identifique a
nadie.

LO QUE NO PRUEBA
----------------
Que una IP libre dentro del prefijo sea USABLE. Puede estar reservada para
equipos de red, fuera del pool del servidor, o en otra VLAN. Esto dice que
NADIE la tiene hoy, que es distinto. La confirmacion es del usuario o del alta
real --y el alta no falla limpio: `agregar-cliente` devuelve 202 y un
`task_id`, no un 400 (ver la skill).

Uso
---
    py -3.13 cli/rangos_de_ip.py                 # todas las zonas
    py -3.13 cli/rangos_de_ip.py --libres 12     # cuantas libres listar por prefijo
================================================================================
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv                                    # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

BASE = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
CLAVE = os.environ.get("WISPHUB_API_KEY")
if not CLAVE:
    raise SystemExit("Falta WISPHUB_API_KEY en el entorno")
HEADERS = {"Authorization": f"Api-Key {CLAVE}", "Content-Type": "application/json"}

#: Cuantos clientes por pagina. La API pagina con limit/offset.
POR_PAGINA = 500
#: Tope de paginas, para que un bucle roto no haga 1.000 llamadas.
MAX_PAGINAS = 60


def _texto(valor) -> str:
    """Un campo que puede venir anidado ({'id':.., 'nombre':..}) o plano."""
    if isinstance(valor, dict):
        return str(valor.get("nombre") or valor.get("id") or "").strip()
    return str(valor or "").strip()


def traer_clientes() -> list[dict]:
    """Las filas que hacen falta, y SOLO esas cuatro columnas."""
    filas, offset = [], 0
    for _ in range(MAX_PAGINAS):
        r = requests.get(f"{BASE}/api/clientes/", headers=HEADERS,
                         params={"limit": POR_PAGINA, "offset": offset},
                         timeout=60)
        r.raise_for_status()
        cuerpo = r.json()
        pagina = cuerpo.get("results") or []
        if not pagina:
            break
        for c in pagina:
            #  Se copia SOLO lo que se va a usar: asi ni por accidente queda
            #  un nombre o una cedula en memoria para imprimirse despues.
            filas.append({
                "ip": str(c.get("ip") or "").strip(),
                "ip_local": str(c.get("ip_local") or "").strip(),
                "zona": _texto(c.get("zona")),
                "router": _texto(c.get("router")),
                "estado": _texto(c.get("estado")),
            })
        offset += len(pagina)
        print(f"  leidos {offset} de {cuerpo.get('count', '?')}", flush=True)
        if offset >= int(cuerpo.get("count") or 0):
            break
    return filas


def prefijo_de(ip: str) -> str:
    try:
        return str(ipaddress.ip_network(f"{ip}/24", strict=False).network_address)[:-1]
    except ValueError:
        return ""


def main(cuantas_libres: int) -> None:
    print(f"Leyendo clientes de {BASE}  (solo lectura)")
    filas = traer_clientes()
    print(f"\n{len(filas)} clientes leidos\n")

    #  zona -> prefijo -> {ultimo octeto en uso}
    mapa: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    routers: dict[str, set] = defaultdict(set)
    sin_ip = 0
    con_ip_local = 0
    raras: list[str] = []

    for f in filas:
        if f["ip_local"]:
            con_ip_local += 1
        if f["router"]:
            routers[f["zona"] or "— sin zona"].add(f["router"])
        if not f["ip"]:
            sin_ip += 1
            continue
        pref = prefijo_de(f["ip"])
        if not pref:
            if len(raras) < 8:
                raras.append(f["ip"][:20])
            continue
        try:
            ultimo = int(f["ip"].rsplit(".", 1)[1])
        except (IndexError, ValueError):
            continue
        mapa[f["zona"] or "— sin zona"][pref].add(ultimo)

    print("=" * 78)
    print("  RANGOS EN USO POR ZONA")
    print("=" * 78)
    for zona in sorted(mapa):
        rs = ", ".join(sorted(routers.get(zona, ()))) or "—"
        print(f"\n  ZONA: {zona}        router(es): {rs}")
        for pref in sorted(mapa[zona]):
            usados = mapa[zona][pref]
            #  1 suele ser la puerta y 255 el broadcast: se dicen, no se
            #  ofrecen como libres sin que alguien lo confirme.
            libres = [n for n in range(2, 255) if n not in usados]
            muestra = ", ".join(f"{pref}{n}" for n in libres[:cuantas_libres])
            print(f"    {pref}0/24     en uso {len(usados):>3}"
                  f"   libres {len(libres):>3}")
            if muestra:
                print(f"      libres (primeras {min(cuantas_libres, len(libres))}): {muestra}")

    print("\n" + "=" * 78)
    print("  LO QUE NO CUADRA, QUE ES LO QUE HAY QUE MIRAR")
    print("=" * 78)
    print(f"  clientes SIN ip ................... {sin_ip}")
    print(f"  clientes con ip_local (PPPoE?) .... {con_ip_local}")
    if raras:
        print(f"  ip con formato que no se pudo leer: {raras}")
    print()
    print("  UNA IP LIBRE AQUI NO ES UNA IP USABLE: puede estar reservada para")
    print("  equipos de red, fuera del pool del servidor o en otra VLAN. Esto")
    print("  dice que NADIE la tiene hoy, que es otra cosa.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--libres", type=int, default=10,
                   help="cuantas IP libres listar por prefijo (def. 10)")
    main(p.parse_args().libres)
