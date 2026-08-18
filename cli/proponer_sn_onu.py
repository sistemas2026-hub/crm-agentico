# -*- coding: utf-8 -*-
"""
================================================================================
 PROPONER sn_onu POR NOMBRE  -  candidatos de backfill, SOLO LECTURA
================================================================================

Para el ~32% de clientes activos de WispHub sin 'sn_onu' (ver skill
wisphub-api), cruza el nombre del cliente contra los nombres de ONU en
SmartOLT y propone un candidato de serial. NUNCA escribe nada, ni en
WispHub ni en SmartOLT -- la decision de cargar cada serial la toma una
persona, revisando este reporte.

Por que existe
---------------
Verificado en vivo (agosto 2026, muestra de 25 clientes con 'sn_onu' ya
conocido, ver skill smartolt-api): el nombre del cliente en SmartOLT
coincide EXACTO con el de WispHub en el 68% de los casos. El resto no son
nombres distintos -- son typos y diferencias de codificacion (la enie mal
codificada en WispHub, puntuacion de mas) entre dos cargas independientes.
El nombre sirve como pista de correlacion, pero no es infalible: hay 8
nombres EXACTOS duplicados entre 4.170 clientes activos (0.38%), y una
coincidencia "cercana" puede estar emparejando a la persona equivocada. Por
eso cada propuesta sale con su nivel de confianza explicito -- este script
NUNCA decide, solo ordena la revision.

Por que no escribe nada
-------------------------
Ya esta documentado en la skill wisphub-api que un PATCH a
/api/clientes/{id}/ devolvio 200 sin persistir de verdad, en un intento
anterior. Escribir 'sn_onu' a ciegas, ademas de arriesgar la identidad
equivocada por el nombre, heredaria ese riesgo sin verificar. El dia que
exista una decision explicita de escribir, es un script APARTE, con
confirmacion y modo dry-run primero -- no este.

Uso
---
    py -3.13 cli/proponer_sn_onu.py
    py -3.13 cli/proponer_sn_onu.py --csv candidatos_sn_onu.csv
================================================================================
"""

from __future__ import annotations

import argparse
import csv as csv_mod
import difflib
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

import requests

WISPHUB_BASE_URL = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
WISPHUB_HEADERS = {"Authorization": f"Api-Key {os.environ.get('WISPHUB_API_KEY', '')}"}
SMARTOLT_BASE_URL = os.environ.get("SMARTOLT_BASE_URL", "").rstrip("/")
SMARTOLT_HEADERS = {"X-Token": os.environ.get("SMARTOLT_API_KEY", "")}

# IDs reales de las OLTs de Rapilink (ver .claude/skills/smartolt-api/SKILL.md
# -- /api/system/get_olts, 2 OLTs). Fijo aca porque este es un script de
# Rapilink, no generico de tenant -- si se reusa para otro ISP, hay que
# sondear sus IDs primero.
OLT_IDS = [3, 4]

UMBRAL_CERCANO = 0.90  # difflib.ratio() -- por debajo de esto no se propone nada


def _get_con_reintento(url: str, headers: dict, params: dict | None = None,
                       intentos: int = 3, timeout: int = 30):
    for i in range(intentos):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException:
            if i == intentos - 1:
                raise
            time.sleep(2)


def normalizar(nombre: str) -> str:
    """Mismo nombre, sin las diferencias que no importan: mayusculas, sin
    tildes/enie, sin caracteres de reemplazo por mojibake (WispHub trae 'enie'
    mal codificada en algunos registros -- se ve como U+FFFD), sin puntuacion,
    espacios colapsados. Los TYPOS reales (GUERRERO/GUERREEO) esto no los
    arregla -- para eso esta el nivel 'cercano' con difflib, aparte."""
    n = (nombre or "").upper()
    n = n.replace("Ñ", "N")  # Ñ
    n = unicodedata.normalize("NFKD", n)
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = n.replace("�", "")
    n = re.sub(r"[^A-Z ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def clientes_activos_wisphub() -> list[dict]:
    """TODOS los clientes activos, paginando hasta el final -- no una
    muestra de las primeras paginas (la leccion de la medicion de cobertura
    de sn_onu: una muestra parcial dio 75% donde el total real era 68%)."""
    clientes: list[dict] = []
    offset = 0
    limite = 200
    total_declarado = None
    while True:
        r = _get_con_reintento(f"{WISPHUB_BASE_URL}/api/clientes/", WISPHUB_HEADERS,
                               {"estado": 1, "limit": limite, "offset": offset})
        datos = r.json()
        if total_declarado is None:
            total_declarado = datos.get("count")
        resultados = datos.get("results", [])
        if not resultados:
            break
        clientes.extend(resultados)
        offset += limite
        if len(resultados) < limite:
            break

    ids = {c["id_servicio"] for c in clientes}
    print(f"[wisphub] {len(clientes)} clientes leidos, {len(ids)} ids distintos "
         f"(la API declaro count={total_declarado})")
    if total_declarado is not None and len(ids) != total_declarado:
        print(f"[wisphub] AVISO: {len(ids)} != {total_declarado} declarado -- "
             f"la paginacion pudo haber cortado antes de tiempo, revisar")
    return clientes


def onus_smartolt() -> list[dict]:
    """TODAS las ONUs de las dos OLTs de Rapilink, via el endpoint masivo.
    'pon_port' se sabe roto (ver skill) pero aca no se filtra por eso -- se
    trae todo y no importa."""
    onus: list[dict] = []
    for olt_id in OLT_IDS:
        r = _get_con_reintento(f"{SMARTOLT_BASE_URL}/api/onu/get_all_onus_details",
                               SMARTOLT_HEADERS, {"olt_id": olt_id})
        datos = r.json()
        lote = datos.get("onus", datos if isinstance(datos, list) else [])
        onus.extend(lote)
        print(f"[smartolt] olt_id={olt_id}: {len(lote)} ONUs")
    return onus


# Tolerancia del desfase entre la MAC del CPE y el serial de la ONU. Medido
# sobre 801 clientes que tienen los DOS campos cargados: en 619 el serial es
# la MAC menos un numero chico (618 veces exactamente 1), y en los 182
# restantes el desfase es cualquier cosa o no hay relacion. O sea: la MAC NO
# sirve para deducir el serial -- 77% no alcanza cuando equivocarse significa
# reiniciar el equipo de otra casa.
#
# Pero si sirve para lo contrario, que es para lo que se usa aca: cuando el
# NOMBRE ya propuso un candidato, la MAC dice si ese candidato es coherente.
# Es una segunda señal independiente, y las dos tienen que estar de acuerdo.
MAX_DESFASE_MAC = 64

# Orden del reporte: primero lo que se puede escribir sin pensar, despues lo
# que necesita una persona, de mas prometedor a menos.
ORDEN_NIVEL = {"alta_confianza": 0, "revisar_mac": 1, "revisar_typo": 2,
               "ambiguo": 3, "sin_candidato": 4}


def mac_corrobora(mac_cpe: str, sn_onu: str) -> bool | None:
    """
    True si la MAC del CPE es coherente con ese serial, False si lo
    contradice, None si no se puede saber (falta uno de los dos, o no son
    hexadecimales).

    None NO es "no coincide": es "no hay con que comparar", y por eso no
    descalifica a un candidato -- solo lo deja sostenido por el nombre, que es
    exactamente lo que pasaba antes de agregar esta comprobacion.
    """
    hexmac = (mac_cpe or "").replace(":", "").replace("-", "").strip().upper()
    sn = (sn_onu or "").strip().upper()
    if len(hexmac) < 8 or len(sn) < 5:
        return None
    try:
        # El serial es <prefijo de 4 del fabricante> + 8 hexadecimales; la MAC
        # comparte esos ultimos 8, o cae cerca.
        desfase = int(hexmac[-8:], 16) - int(sn[4:], 16)
    except ValueError:
        return None
    return 0 <= desfase <= MAX_DESFASE_MAC


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", help="Si se pasa, ademas guarda el reporte en este archivo CSV")
    args = ap.parse_args()

    if not SMARTOLT_BASE_URL or not SMARTOLT_HEADERS["X-Token"]:
        print("Falta SMARTOLT_BASE_URL / SMARTOLT_API_KEY en el entorno.")
        sys.exit(1)

    print("=" * 72)
    print("  Candidatos de sn_onu por nombre -- SOLO LECTURA, no escribe nada")
    print("=" * 72)

    clientes = clientes_activos_wisphub()
    sin_serial = [c for c in clientes if not c.get("sn_onu")]
    seriales_ya_usados = {c["sn_onu"] for c in clientes if c.get("sn_onu")}
    print(f"[wisphub] {len(sin_serial)} de {len(clientes)} clientes activos SIN sn_onu")

    # Nombres duplicados EXACTOS entre los clientes SIN serial (y tambien
    # cruzando contra los que SI tienen, por si el duplicado es uno de cada):
    # si dos personas activas comparten nombre, el nombre solo no alcanza
    # para saber a cual corresponde un candidato.
    nombres_activos: dict[str, int] = {}
    for c in clientes:
        n = normalizar(c.get("nombre") or "")
        if n:
            nombres_activos[n] = nombres_activos.get(n, 0) + 1
    nombres_duplicados = {n for n, cnt in nombres_activos.items() if cnt > 1}
    print(f"[wisphub] {len(nombres_duplicados)} nombres (normalizados) que se "
         f"repiten entre clientes activos")

    onus = onus_smartolt()
    indice: dict[str, list[dict]] = {}
    for o in onus:
        n = normalizar(o.get("name") or "")
        if n:
            indice.setdefault(n, []).append(o)
    # Segundo indice, por CONJUNTO de palabras. Existe porque el nombre exacto
    # falla por dos motivos que estan en los datos de WispHub y no se van a
    # arreglar solos: apellidos duplicados al cargar ("JUAN DAVID BARRIOS
    # BARRIOS") y la enie mal codificada ("NIÃO" donde SmartOLT tiene "NIÑO").
    # Comparar palabra por palabra sobrevive a las dos.
    onus_tokens = [(o, set(normalizar(o.get("name") or "").split())) for o in onus]
    print(f"[smartolt] {len(onus)} ONUs, {len(indice)} nombres distintos (normalizados)")
    print()

    filas = []
    for c in sin_serial:
        nombre_wh = c.get("nombre") or ""
        norm_wh = normalizar(nombre_wh)
        id_servicio = c["id_servicio"]

        if not norm_wh:
            filas.append((id_servicio, nombre_wh, "", "", "sin_candidato",
                         "el cliente no tiene nombre cargado"))
            continue

        candidatos_exactos = indice.get(norm_wh, [])

        if len(candidatos_exactos) == 1 and norm_wh not in nombres_duplicados:
            onu = candidatos_exactos[0]
            sn = onu.get("sn") or onu.get("unique_external_id") or ""
            if sn in seriales_ya_usados:
                filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                             "ambiguo", "ese sn_onu ya esta asignado a OTRO cliente en WispHub"))
            else:
                # Segunda señal: la MAC del CPE. Un nombre exacto NO alcanza
                # para escribir sin revisar -- medido el 18/08/2026 sobre los
                # clientes activos sin serial, de los que resolvian a una sola
                # ONU por nombre habia 10 en los que la MAC apuntaba a otro
                # equipo. Esos 10 salian como 'alta_confianza' y se habrian
                # escrito: el cliente quedaria apuntando al equipo de otra
                # casa, y ahi un reinicio remoto se lo hace a un tercero.
                acuerdo = mac_corrobora(c.get("mac_cpe") or "", sn)
                if acuerdo is False:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "revisar_mac",
                                 "el nombre coincide exacto pero la MAC del CPE "
                                 "apunta a otro equipo -- confirmar a mano cual "
                                 "de los dos datos esta mal"))
                elif acuerdo is None:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "alta_confianza",
                                 "nombre exacto, sin ambiguedad (sin MAC cargada "
                                 "para corroborar)"))
                else:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "alta_confianza",
                                 "nombre exacto y MAC del CPE coherente"))
            continue

        if len(candidatos_exactos) > 1:
            sns = ", ".join(o.get("sn") or o.get("unique_external_id") or "?"
                            for o in candidatos_exactos)
            filas.append((id_servicio, nombre_wh, sns, "", "ambiguo",
                         f"{len(candidatos_exactos)} ONUs distintas con ese mismo nombre"))
            continue

        if norm_wh in nombres_duplicados:
            filas.append((id_servicio, nombre_wh, "", "", "ambiguo",
                         "hay otro cliente ACTIVO con el mismo nombre en WispHub"))
            continue

        # Sin match exacto: probar por conjunto de palabras, pero SOLO se acepta
        # si la MAC del CPE tambien esta de acuerdo. Un nombre parecido por si
        # solo no alcanza para escribir; dos señales independientes que
        # coinciden, si. Si la MAC no esta cargada o contradice, la propuesta
        # baja a revision manual en vez de escribirse.
        tok_wh = set(norm_wh.split())
        if len(tok_wh) >= 3:
            cerca = []
            for onu, tok_onu in onus_tokens:
                if len(tok_onu) < 3:
                    continue
                comunes = tok_wh & tok_onu
                menor = min(len(tok_wh), len(tok_onu))
                # Al menos 3 palabras iguales y como maximo UNA que no cuadre
                # del nombre mas corto: eso tolera el apellido repetido y una
                # palabra mal codificada, sin abrir la puerta a dos personas
                # que solo comparten el nombre de pila.
                if len(comunes) >= 3 and len(comunes) >= menor - 1:
                    cerca.append(onu)
            if len(cerca) == 1:
                onu = cerca[0]
                sn = onu.get("sn") or onu.get("unique_external_id") or ""
                acuerdo = mac_corrobora(c.get("mac_cpe") or "", sn)
                if sn in seriales_ya_usados:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "ambiguo", "ese sn_onu ya esta asignado a OTRO cliente en WispHub"))
                elif acuerdo is True:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "alta_confianza",
                                 "nombre casi igual (palabra por palabra) Y MAC del "
                                 "CPE coherente -- dos señales de acuerdo"))
                else:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "revisar_typo",
                                 "nombre casi igual palabra por palabra, pero la MAC "
                                 + ("contradice" if acuerdo is False else "no esta cargada")
                                 + " -- confirmar a mano"))
                continue
            if len(cerca) > 1:
                sns = ", ".join(o.get("sn") or "?" for o in cerca)
                filas.append((id_servicio, nombre_wh, sns, "", "ambiguo",
                             f"{len(cerca)} ONUs con nombre casi igual"))
                continue

        # Ultimo recurso: el mas parecido por similitud de texto (typo).
        mejor_nombre, mejor_ratio = None, 0.0
        for n in indice:
            ratio = difflib.SequenceMatcher(None, norm_wh, n).ratio()
            if ratio > mejor_ratio:
                mejor_nombre, mejor_ratio = n, ratio
        if mejor_nombre and mejor_ratio >= UMBRAL_CERCANO:
            candidatos = indice[mejor_nombre]
            sns = ", ".join(o.get("sn") or o.get("unique_external_id") or "?"
                            for o in candidatos)
            filas.append((id_servicio, nombre_wh, sns, mejor_nombre,
                         "revisar_typo", f"similitud {mejor_ratio:.0%} -- posible typo, confirmar a mano"))
        else:
            filas.append((id_servicio, nombre_wh, "", "", "sin_candidato",
                         "no se encontro ninguna ONU con nombre parecido"))

    conteo: dict[str, int] = {}
    for fila in filas:
        conteo[fila[4]] = conteo.get(fila[4], 0) + 1

    print("Resumen:")
    for nivel in ("alta_confianza", "revisar_mac", "revisar_typo", "ambiguo", "sin_candidato"):
        print(f"  {nivel}: {conteo.get(nivel, 0)}")
    print()

    print(f"{'id_servicio':<12}{'nombre':<35}{'confianza':<16}{'candidato(s)':<30}motivo")
    print("-" * 130)
    for id_servicio, nombre, sn, nombre_so, confianza, motivo in sorted(
            filas, key=lambda f: (ORDEN_NIVEL.get(f[4], 99), f[0])):
        print(f"{id_servicio:<12}{nombre[:33]:<35}{confianza:<16}{sn[:28]:<30}{motivo}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv_mod.writer(f)
            w.writerow(["id_servicio", "nombre_wisphub", "sn_onu_candidato",
                       "nombre_smartolt", "confianza", "motivo"])
            w.writerows(filas)
        print(f"\nGuardado en {args.csv}")


if __name__ == "__main__":
    main()
