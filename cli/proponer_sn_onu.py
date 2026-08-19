# -*- coding: utf-8 -*-
"""
================================================================================
 PROPONER sn_onu  -  candidatos de backfill por NOMBRE y por MAC, SOLO LECTURA
================================================================================

Para los clientes activos de WispHub sin 'sn_onu', propone un candidato de
serial cruzando DOS fuentes independientes contra SmartOLT: el nombre del
cliente y la MAC de su CPE. NUNCA escribe nada, ni en WispHub ni en
SmartOLT -- la decision de cargar cada serial la toma una persona,
revisando este reporte.

Las dos fuentes son complementarias, no redundantes, y por eso conviene
tener las dos: medido el 18/08/2026 sobre los clientes sin serial, la MAC
propone en el 80% de los casos y el nombre solo en el 16%. Muchos de estos
clientes estan cargados en SmartOLT con un nombre que no se parece al de
WispHub; y al reves, hay 95 clientes activos sin MAC cargada, para los que
el nombre es lo unico que queda.

Ninguna de las dos sirve sola:
  - el nombre exacto acierta, pero hay homonimos y ONUs con el mismo nombre;
  - la MAC sola acierta 7 de cada 10, porque el desfase entre MAC y serial
    es chico y constante dentro de un lote, asi que la MAC de un cliente
    cae EXACTAMENTE sobre el serial de su vecino de embarque.
Cuando las dos coinciden, la precision medida es 97.9% (--validar).

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

Verificacion por IP (18/08/2026) -- segunda señal, independiente del nombre
-----------------------------------------------------------------------------
El nombre falla justo donde mas se necesita (typos, tildes, duplicados). La
IP que WispHub guarda por cliente (campo 'ip') es, en Rapilink, una
asignacion ESTATICA dentro de su red interna (confirmado en vivo: 'IPv4
access type: Static' en get_onu_full_status_info) -- no cambia con cada
reconexion como pasaria con un ISP residencial tipico. Verificado contra 8
clientes reales con sn_onu ya confirmado: quien tenia IP de los dos lados,
coincidio 8 de 8. Por eso sirve como confirmacion independiente del nombre,
no solo como otro dato mas.

Requiere get_onu_full_status_info (el endpoint PESADO, ~10s por ONU, el
proveedor pide no usarlo en bulk/polling) -- por eso es opt-in
(--verificar-ip) y solo se llama sobre candidatos ya acotados por nombre
(alta_confianza, revisar_typo, ambiguo con mas de un candidato), nunca
sobre todo el universo de ONUs.

Uso
---
    py -3.13 cli/proponer_sn_onu.py
    py -3.13 cli/proponer_sn_onu.py --verificar-ip
    py -3.13 cli/proponer_sn_onu.py --csv candidatos_sn_onu.csv
    py -3.13 cli/proponer_sn_onu.py --validar        # mide las reglas contra la realidad
    py -3.13 cli/proponer_sn_onu.py --verificar-mac  # confirma contra el equipo (lento)
================================================================================
"""

from __future__ import annotations

import argparse
import csv as csv_mod
import difflib
import json
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


def ip_de_onu(sn: str) -> str | None:
    """IP que SmartOLT ve realmente conectada en esa ONU, o None si no se
    pudo obtener (endpoint pesado -- ver el docstring del modulo, no se
    reintenta con la forma hexadecimal para no duplicar el costo de 10s).
    'full_status_json' es la forma real de la respuesta -- 'response' NO
    existe en este endpoint, a diferencia de get_outage_pons (confirmado
    en vivo, 18/08/2026: asumir la misma envoltura para dos endpoints
    distintos del mismo proveedor caus el primer intento de esto)."""
    try:
        r = requests.get(f"{SMARTOLT_BASE_URL}/api/onu/get_onu_full_status_info/{sn}",
                         headers=SMARTOLT_HEADERS, timeout=15)
        if not r.ok:
            return None
        wan = r.json().get("full_status_json", {}).get("ONU WAN Interfaces", {})
        return wan.get("IPv4 address") if isinstance(wan, dict) else None
    except requests.exceptions.RequestException:
        return None


def confirmar_por_ip(candidatos: list[dict], ip_wisphub: str | None) -> tuple[dict | None, str, str]:
    """Entre varios candidatos de ONU (mismo nombre o nombre parecido),
    cual tiene la IP que WispHub tiene guardada para este cliente -- si
    hay exactamente uno, ESE es el correcto, sin importar cuantos otros
    compartian el nombre.

    Devuelve (onu_confirmada, razon, nota):
      razon es un codigo fijo para decidir el nivel de confianza sin
      comparar texto libre -- 'sin_ip', 'confirmado', 'no_coincide',
      'multiple'. 'nota' es la version legible para el reporte.
      onu_confirmada es None salvo en 'confirmado' -- que no confirme no
      es un fallo, solo falta de dato (no toda ONU trae IP en
      get_onu_full_status_info)."""
    if not ip_wisphub:
        return None, "sin_ip", "sin IP en WispHub para comparar"

    coincidencias = []
    for onu in candidatos:
        sn = onu.get("sn") or onu.get("unique_external_id") or ""
        ip_so = ip_de_onu(sn)
        if ip_so and ip_so == ip_wisphub:
            coincidencias.append(onu)

    if len(coincidencias) == 1:
        return coincidencias[0], "confirmado", "IP coincide -- confirmado"
    if len(coincidencias) > 1:
        return None, "multiple", f"{len(coincidencias)} candidatos con la MISMA ip que WispHub -- revisar a mano"
    return None, "no_coincide", "ninguna IP de los candidatos coincide con la de WispHub"


def tokens_clave(norm: str) -> list[str] | None:
    """Primer nombre + primer apellido como PALABRAS sueltas -- heuristica
    para nombres latinos 'NOMBRE [NOMBRE2] APELLIDO1 [APELLIDO2]'. None si
    el nombre no tiene ni dos palabras (no hay con que buscar)."""
    partes = norm.split()
    if len(partes) < 2:
        return None
    apellido = partes[2] if len(partes) >= 3 else partes[1]
    return [partes[0], apellido]


def candidatos_por_tokens(tokens: list[str], indice: dict) -> list[dict]:
    """Toda ONU cuyo nombre normalizado tenga AMBOS tokens como PALABRAS
    completas, en cualquier orden y con cualquier cosa alrededor --
    'VILMA LUCIA CASADIEGO MANOSALVA-1' matchea tokens ['VILMA',
    'CASADIEGO'] aunque el string completo no coincida ni por similitud.
    Palabras completas, no substring pegado: 'ANA' no matchea dentro de
    'SUSANA' (serian palabras distintas al hacer .split())."""
    candidatos = []
    for nombre_norm, onus in indice.items():
        palabras = set(nombre_norm.split())
        if all(t in palabras for t in tokens):
            candidatos.extend(onus)
    return candidatos


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

# Los desfases REALES entre la cola de la MAC y la cola del serial, medidos
# sobre 2.404 clientes que tienen los dos campos cargados (18/08/2026):
#
#     +1  38.8%    +6  31.3%    +2  20.5%    +7  2.7%   -> 93.3% del total
#
# No es una nube de valores: son cuatro numeros. Y dentro de cada
# combinacion (prefijo del serial + OUI de la MAC) el desfase dominante se
# lleva entre el 91% y el 100% -- 'DF3D / 80F7A6' da +2 en los 177 casos,
# sin una sola excepcion. Es una constante de lote, no una coincidencia.
#
# Por que importa que sean valores EXACTOS y no un rango: buscar en una
# ventana de +-4 da 72.8% de precision (se saltea el grupo +6 entero, que es
# un tercio de la red). Probar estos cuatro valores exactos da 97.5%, con
# 92.8% de cobertura y CERO candidatos ambiguos.
DESFASES_CONOCIDOS = (1, 2, 6, 7)


def cola_hex(valor: str) -> str:
    """Los 8 hexadecimales finales, que son los que comparten MAC y serial.
    El prefijo no sirve para comparar: 'HWTC' es el identificador GPON del
    fabricante y '80F7A6' su OUI de MAC -- dos codificaciones distintas del
    mismo Huawei."""
    return re.sub(r"[^0-9A-F]", "", (valor or "").upper())


def candidatos_por_mac(mac_cpe: str, indice_cola: dict) -> list:
    """
    ONUs cuyo serial es exactamente la MAC menos uno de los desfases
    conocidos. Devuelve [] si la MAC no esta cargada o no cae en ninguno.

    OJO -- esto PROPONE, no confirma. Medido sobre los clientes con serial
    ya conocido: cuando esta lista trae un solo candidato acierta el 97.5%,
    pero si el NOMBRE no lo respalda baja al 70.8%. El motivo es mecanico y
    no se arregla afinando el numero: como el desfase es chico y constante
    dentro de un lote, la MAC de un cliente cae EXACTAMENTE sobre el serial
    de su vecino de embarque. Por eso una propuesta sostenida solo por la
    MAC nunca se escribe sin una segunda señal.
    """
    m = cola_hex(mac_cpe)
    if len(m) < 8:
        return []
    try:
        valor = int(m[-8:], 16)
    except ValueError:
        return []
    vistas = []
    for desfase in DESFASES_CONOCIDOS:
        for onu in indice_cola.get(f"{valor - desfase:08X}", []):
            if onu not in vistas:
                vistas.append(onu)
    return vistas

# Orden del reporte: primero lo que se puede escribir sin pensar, despues lo
# que necesita una persona, de mas prometedor a menos.
# El orden de los niveles vive en '_NIVELES', dentro de main(): una sola
# lista de la que salen el resumen y el orden del reporte, en vez de dos
# estructuras que hay que acordarse de actualizar juntas.


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


def mac_del_equipo(sn_onu: str) -> str:
    """
    La MAC que el equipo reporta AHORA, preguntandosela a la OLT.

    Es el unico dato que confirma una identidad sin lugar a dudas: la misma
    huella fisica anotada en dos sistemas que nadie sincronizo. Verificado
    sobre 6 clientes con serial ya conocido, coincidio en los 6, exacto
    ('C4:CD:50:5A:EA:B8' en WispHub contra 'C4CD-505A-EAB8' en SmartOLT).

    Devuelve "" si el equipo no la reporta -- pasa cuando esta caido, y NO
    significa que el candidato sea malo: significa que no se pudo saber.

    CUIDADO CON EL VOLUMEN: este endpoint tarda ~10s porque sale a
    interrogar la OLT en vivo, y el proveedor lo autoriza para investigar un
    caso puntual pero pide NO usarlo en bulk. Por eso corre solo detras de
    --verificar-mac y solo sobre las filas que quedaron sin resolver, no
    sobre todas.
    """
    try:
        r = _get_con_reintento(
            f"{SMARTOLT_BASE_URL}/api/onu/get_onu_full_status_info/{sn_onu}",
            SMARTOLT_HEADERS, timeout=120)
        js = (r.json() or {}).get("full_status_json") or {}
    except Exception:
        return ""
    partes = [js.get("ONU WAN Interfaces") or {}, js.get("MACs on OLT from this ONU") or {}]
    return cola_hex(json.dumps(partes, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", help="Si se pasa, ademas guarda el reporte en este archivo CSV")
    ap.add_argument("--validar", action="store_true",
                   help="No propone nada: corre EXACTAMENTE la misma logica sobre los "
                        "clientes que YA tienen sn_onu (tapandolo) y compara cada "
                        "propuesta contra el valor real. Es la unica forma de saber si "
                        "un cambio en las reglas mejoro o empeoro, sin escribir nada.")
    ap.add_argument("--verificar-mac", action="store_true",
                   help="Le pregunta a la OLT la MAC real de cada equipo y la compara "
                        "con la de WispHub. Es lo unico que confirma sin dudas, pero "
                        "OJO: en la corrida del 18/08/2026 la MITAD volvio SIN "
                        "veredicto -- hay ONUs que contestan bien y no exponen ninguna "
                        "MAC. No sirve para blindar la carga entera, solo para "
                        "confirmar una parte. Apagado por defecto: tarda horas y el "
                        "proveedor pide no usar ese endpoint en bulk.")
    ap.add_argument("--verificar-ip", action="store_true",
                    help="Cruza la IP de WispHub contra get_onu_full_status_info "
                         "para cada candidato -- mas lento (~10s por candidato), "
                         "pero confirma o desmiente lo que dice el nombre solo.")
    args = ap.parse_args()

    if not SMARTOLT_BASE_URL or not SMARTOLT_HEADERS["X-Token"]:
        print("Falta SMARTOLT_BASE_URL / SMARTOLT_API_KEY en el entorno.")
        sys.exit(1)

    print("=" * 72)
    print("  Candidatos de sn_onu por nombre -- SOLO LECTURA, no escribe nada")
    print("=" * 72)

    clientes = clientes_activos_wisphub()
    if args.validar:
        # Se les tapa el serial para que la logica no pueda hacer trampa, pero
        # se guarda aparte para comparar al final. 'seriales_ya_usados' NO
        # puede incluir el propio, o cada cliente se descartaria a si mismo
        # con "ese sn_onu ya esta asignado a OTRO cliente".
        verdad = {c["id_servicio"]: c["sn_onu"].upper()
                 for c in clientes if c.get("sn_onu")}
        sin_serial = [dict(c, sn_onu="") for c in clientes if c.get("sn_onu")]
        seriales_ya_usados = set()
        print(f"[validacion] {len(sin_serial)} clientes con serial conocido, tapado")
    else:
        verdad = {}
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
    # Indice por los 8 hexadecimales finales del serial: es lo que permite
    # buscar por MAC sin recorrer las 5.000 ONUs por cada cliente.
    indice_cola: dict[str, list[dict]] = {}
    for o in onus:
        sn = (o.get("sn") or o.get("unique_external_id") or "").upper()
        if len(sn) > 4:
            indice_cola.setdefault(sn[4:], []).append(o)
    print(f"[smartolt] {len(onus)} ONUs, {len(indice)} nombres distintos (normalizados)")
    print()

    por_id = {c["id_servicio"]: c for c in sin_serial}

    filas = []
    for c in sin_serial:
        nombre_wh = c.get("nombre") or ""
        norm_wh = normalizar(nombre_wh)
        id_servicio = c["id_servicio"]

        # Segunda fuente de candidatos, independiente del nombre. En esta
        # poblacion es la que mas rescata: medido el 18/08/2026, la MAC
        # propone en el 80% de los clientes sin serial y el nombre solo en
        # el 16% -- al reves de lo que se asumia cuando este script se
        # escribio. Muchos de estos clientes estan cargados en SmartOLT con
        # un nombre que no se parece al de WispHub, o directamente con otro.
        por_mac = candidatos_por_mac(c.get("mac_cpe") or "", indice_cola)
        onu_mac = por_mac[0] if len(por_mac) == 1 else None
        sn_mac = (onu_mac.get("sn") or onu_mac.get("unique_external_id") or "") if onu_mac else ""

        if not norm_wh:
            if sn_mac and sn_mac not in seriales_ya_usados:
                filas.append((id_servicio, nombre_wh, sn_mac, onu_mac.get("name", ""),
                             "solo_mac",
                             "el cliente no tiene nombre cargado; la MAC del CPE "
                             "apunta a este serial -- confirmar antes de escribir"))
                continue
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
            elif args.verificar_ip:
                confirmada, razon, nota = confirmar_por_ip([onu], c.get("ip"))
                # Un nombre exacto CON ip que NO coincide es mas sospechoso que
                # uno sin verificar -- se marca distinto, no se descarta (el
                # nombre exacto sigue siendo una senal real).
                nivel = {"confirmado": "confirmado_ip",
                        "no_coincide": "revisar_ip_no_coincide"}.get(razon, "alta_confianza")
                filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                             nivel, f"nombre exacto, sin ambiguedad -- {nota}"))
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
                elif sn == sn_mac:
                    # Las dos fuentes, que no se hablan entre si, llegaron al
                    # mismo serial. Medido: 99.34% de acierto (14 errores en
                    # 2.121 casos con serial ya conocido). Es lo mas firme
                    # que da este script sin tocar el equipo.
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "alta_confianza",
                                 "nombre exacto Y la MAC apunta al MISMO serial "
                                 "-- dos fuentes independientes de acuerdo"))
                else:
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""),
                                 "alta_confianza",
                                 "nombre exacto y MAC del CPE coherente"))
            continue

        if len(candidatos_exactos) > 1:
            sns_exactos = [o.get("sn") or o.get("unique_external_id") or "?"
                          for o in candidatos_exactos]
            # Dos desempates, y se prueban en orden de costo.
            #
            # Primero la MAC, que es GRATIS: entre candidatos que ya propuso
            # el nombre, el correcto esta a 1 o 2 de la MAC y el otro a
            # millones, asi que no es una pista debil sino una separacion
            # tajante. Medido: resuelve 18 de 28 ambiguos sin una sola llamada.
            if sn_mac in sns_exactos:
                filas.append((id_servicio, nombre_wh, sn_mac, onu_mac.get("name", ""),
                             "alta_confianza",
                             f"{len(candidatos_exactos)} ONUs con ese mismo nombre, "
                             f"y la MAC del CPE senala a esta"))
                continue
            # Recien si la MAC no alcanzo se paga la IP (~10s por candidato),
            # y solo si lo pidieron.
            if args.verificar_ip:
                confirmada, razon, nota = confirmar_por_ip(candidatos_exactos, c.get("ip"))
                if confirmada:
                    sn_confirmado = confirmada.get("sn") or confirmada.get("unique_external_id") or ""
                    filas.append((id_servicio, nombre_wh, sn_confirmado, confirmada.get("name", ""),
                                 "confirmado_ip",
                                 f"{len(candidatos_exactos)} ONUs con ese nombre, la IP desempato -- {nota}"))
                else:
                    filas.append((id_servicio, nombre_wh, ", ".join(sns_exactos), "", "ambiguo",
                                 f"{len(candidatos_exactos)} ONUs distintas con ese mismo nombre -- {nota}"))
            else:
                filas.append((id_servicio, nombre_wh, ", ".join(sns_exactos), "", "ambiguo",
                             f"{len(candidatos_exactos)} ONUs distintas con ese mismo nombre "
                             f"y la MAC no senala a ninguna"))
            continue

        if norm_wh in nombres_duplicados:
            # Dos clientes activos se llaman igual: el nombre no puede
            # decidir. Pero la MAC es de UN aparato, no de un nombre.
            if sn_mac and sn_mac not in seriales_ya_usados:
                filas.append((id_servicio, nombre_wh, sn_mac, onu_mac.get("name", ""),
                             "solo_mac",
                             "hay otro cliente ACTIVO con el mismo nombre, asi que el "
                             "nombre no sirve; la MAC del CPE apunta a este serial"))
                continue
            filas.append((id_servicio, nombre_wh, "", "", "ambiguo",
                         "hay otro cliente ACTIVO con el mismo nombre en WispHub"))
            continue

        # Sin match exacto contra 'nombre': antes de pasar a typo, probar contra
        # 'servicio' -- el campo separado que WispHub muestra en su propia
        # pantalla como "Servicio", a veces mas corto (sin segundo nombre) que
        # 'nombre'. Confirmado en vivo (18/08/2026): id_servicio 6727,
        # SmartOLT tenia la ONU con el nombre de 'servicio', no el de
        # 'nombre' -- por eso ese caso salia 'sin_candidato' antes de esto.
        # Cuesta cero cuando 'servicio' == 'nombre' (el caso mas comun): el
        # 'if norm_servicio != norm_wh' de abajo lo salta directo.
        norm_servicio = normalizar(c.get("servicio") or "")
        if norm_servicio and norm_servicio != norm_wh:
            candidatos_servicio = indice.get(norm_servicio, [])
            if len(candidatos_servicio) == 1:
                onu = candidatos_servicio[0]
                sn = onu.get("sn") or onu.get("unique_external_id") or ""
                if sn not in seriales_ya_usados:
                    nivel, nota_ip = "alta_confianza", ""
                    if args.verificar_ip:
                        confirmada, razon, nota = confirmar_por_ip([onu], c.get("ip"))
                        nivel = {"confirmado": "confirmado_ip",
                                "no_coincide": "revisar_ip_no_coincide"}.get(razon, "alta_confianza")
                        nota_ip = f" -- {nota}"
                    filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""), nivel,
                                 f"coincide por 'servicio' ({c.get('servicio')}), "
                                 f"no por 'nombre'{nota_ip}"))
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
                sns_cerca = [o.get("sn") or "?" for o in cerca]
                if sn_mac in sns_cerca:
                    filas.append((id_servicio, nombre_wh, sn_mac, onu_mac.get("name", ""),
                                 "alta_confianza",
                                 f"{len(cerca)} ONUs con nombre casi igual, y la MAC "
                                 f"del CPE senala a esta"))
                    continue
                filas.append((id_servicio, nombre_wh, ", ".join(sns_cerca), "", "ambiguo",
                             f"{len(cerca)} ONUs con nombre casi igual y la MAC no "
                             f"senala a ninguna"))
                continue


        # Sin match exacto: buscar el mas parecido (typo), solo si supera el umbral.
        mejor_nombre, mejor_ratio = None, 0.0
        for n in indice:
            ratio = difflib.SequenceMatcher(None, norm_wh, n).ratio()
            if ratio > mejor_ratio:
                mejor_nombre, mejor_ratio = n, ratio
        if mejor_nombre and mejor_ratio >= UMBRAL_CERCANO:
            candidatos = indice[mejor_nombre]
            sns_typo = [o.get("sn") or o.get("unique_external_id") or "?"
                       for o in candidatos]
            # Mismo orden de costo que en los otros desempates: la MAC no
            # cuesta nada, la IP cuesta una llamada de ~10s.
            if sn_mac in sns_typo:
                filas.append((id_servicio, nombre_wh, sn_mac, mejor_nombre,
                             "alta_confianza",
                             f"nombre parecido ({mejor_ratio:.0%}) Y la MAC del CPE "
                             f"senala al mismo serial -- el typo deja de importar"))
            elif args.verificar_ip:
                confirmada, razon, nota = confirmar_por_ip(candidatos, c.get("ip"))
                if confirmada:
                    sn_confirmado = confirmada.get("sn") or confirmada.get("unique_external_id") or ""
                    filas.append((id_servicio, nombre_wh, sn_confirmado, confirmada.get("name", ""),
                                 "confirmado_ip",
                                 f"similitud {mejor_ratio:.0%}, la IP lo confirma -- {nota}"))
                else:
                    filas.append((id_servicio, nombre_wh, ", ".join(sns_typo), mejor_nombre,
                                 "revisar_typo",
                                 f"similitud {mejor_ratio:.0%} -- posible typo, confirmar a mano "
                                 f"({nota})"))
            else:
                filas.append((id_servicio, nombre_wh, ", ".join(sns_typo), mejor_nombre,
                             "revisar_typo",
                             f"similitud {mejor_ratio:.0%} -- posible typo, confirmar a mano"))
            continue
        # Ultimo recurso: ni 'nombre' ni 'servicio' dieron un match exacto, y
        # el string completo no llega al umbral de similitud (tipico cuando
        # SmartOLT tiene texto extra pegado: '-1', 'PPT', '2'). Se busca mas
        # suelto -- nombre y apellido como palabras, en cualquier lugar del
        # candidato -- y como eso trae mas ruido, la IP es la que de verdad
        # decide cuando hay mas de un candidato.
        tokens = tokens_clave(norm_wh)
        candidatos_tokens = candidatos_por_tokens(tokens, indice) if tokens else []

        if len(candidatos_tokens) == 1:
            onu = candidatos_tokens[0]
            sn = onu.get("sn") or onu.get("unique_external_id") or ""
            if sn in seriales_ya_usados:
                filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""), "ambiguo",
                             "nombre+apellido encontrados en 1 candidato, pero ese sn_onu "
                             "ya esta asignado a OTRO cliente en WispHub"))
            else:
                # A diferencia de 'nombre'/'servicio' (campos completos,
                # confiables), dos palabras sueltas coincidiendo es una
                # senal MAS debil -- "ANA"+"IBANEZ" puede ser cualquiera de
                # varias personas. Sin IP que lo confirme, esto NUNCA es
                # alta_confianza -- 'revisar_tokens' dice explicitamente
                # "esto es menos seguro que un typo", no un nivel mas.
                nivel, nota_ip = "revisar_tokens", ""
                if args.verificar_ip:
                    confirmada, razon, nota = confirmar_por_ip([onu], c.get("ip"))
                    nivel = {"confirmado": "confirmado_ip",
                            "no_coincide": "revisar_tokens"}.get(razon, "revisar_tokens")
                    nota_ip = f" -- {nota}"
                filas.append((id_servicio, nombre_wh, sn, onu.get("name", ""), nivel,
                             f"nombre+apellido encontrados en 1 candidato, confirmar con "
                             f"cuidado ({onu.get('name', '')}){nota_ip}"))
        elif len(candidatos_tokens) > 1:
            sns = ", ".join(o.get("sn") or o.get("unique_external_id") or "?"
                            for o in candidatos_tokens[:5])
            if args.verificar_ip:
                confirmada, razon, nota = confirmar_por_ip(candidatos_tokens, c.get("ip"))
                if confirmada:
                    sn_confirmado = confirmada.get("sn") or confirmada.get("unique_external_id") or ""
                    filas.append((id_servicio, nombre_wh, sn_confirmado, confirmada.get("name", ""),
                                 "confirmado_ip",
                                 f"{len(candidatos_tokens)} candidatos con nombre+apellido, "
                                 f"la IP desempato -- {nota}"))
                else:
                    filas.append((id_servicio, nombre_wh, sns, "", "ambiguo",
                                 f"{len(candidatos_tokens)} candidatos con nombre+apellido -- {nota}"))
            else:
                filas.append((id_servicio, nombre_wh, sns, "", "ambiguo",
                             f"{len(candidatos_tokens)} candidatos con nombre+apellido, "
                             f"sin --verificar-ip para desempatar"))
        else:
            # Ni el nombre completo, ni 'servicio', ni palabras sueltas. Queda
            # la MAC, que es la unica senal que no depende de como haya quedado
            # escrito el nombre en ninguno de los dos sistemas. Es el caso mas
            # comun de todos aca (130 de 192 clientes) y el que este script
            # perdia entero antes de la busqueda por MAC.
            #
            # NO es alta_confianza: sostenida sola, la MAC acierta 7 de cada
            # 10. Va al reporte para que una persona lo confirme, o para que
            # --verificar-mac lo resuelva contra el equipo real.
            if sn_mac and sn_mac not in seriales_ya_usados:
                filas.append((id_servicio, nombre_wh, sn_mac, onu_mac.get("name", ""),
                             "solo_mac",
                             f"la MAC del CPE apunta a este serial, pero el nombre en "
                             f"SmartOLT es distinto ('{(onu_mac.get('name') or '')[:28]}') "
                             f"-- confirmar antes de escribir"))
            else:
                filas.append((id_servicio, nombre_wh, "", "", "sin_candidato",
                             "ni el nombre (completo, 'servicio' o palabras sueltas) "
                             "ni la MAC del CPE apuntan a ninguna ONU"))

    # --- filtro final: la MAC real del equipo, solo si se pidio ---------
    # Sube a 'alta_confianza' lo que confirme y baja a 'ambiguo' lo que
    # desmienta. Lo que el equipo no pueda contestar (caido) queda igual que
    # estaba: sin veredicto no se mueve nada.
    if args.verificar_mac:
        # TODA fila con un candidato unico, incluida 'alta_confianza'. Esa es
        # justamente la que se va a escribir, y mide 97.94% (--validar): sobre
        # 246 propuestas son ~5 clientes que quedarian apuntando al equipo de
        # otra casa, y ahi un reinicio remoto se lo hace a un tercero. Los
        # otros niveles se verifican tambien porque un CONFIRMADO los asciende
        # y deja de hacer falta que alguien los mire.
        pendientes = [i for i, f in enumerate(filas)
                     if f[4] in ("alta_confianza", "solo_mac", "revisar_mac",
                                 "revisar_typo")
                     and f[2] and "," not in f[2]]
        # Estado de cada ONU segun la lista masiva, que ya esta traida: a una
        # que figura Offline o Power fail no hace falta preguntarle nada, y
        # preguntarle cuesta el tiempo de espera completo para recibir lo
        # mismo. En la corrida del 18/08/2026, 33 de 277 se ahorraron asi.
        estado_onu = {(o.get("sn") or "").upper(): o.get("status") or "?"
                     for o in onus}
        print(f"[verificar-mac] {len(pendientes)} equipos. Tarda: el endpoint "
             f"contesta en 10-30s cuando contesta, y bastante mas cuando el "
             f"equipo no esta. Contar en horas, no en minutos.")
        confirmados = desmentidos = mudos = 0
        for n, i in enumerate(pendientes, 1):
            id_servicio, nombre_wh, sn, nombre_so, nivel, motivo = filas[i]
            mac_wh = cola_hex(por_id.get(id_servicio, {}).get("mac_cpe") or "")
            if estado_onu.get(sn.upper()) != "Online":
                mudos += 1
                if n % 10 == 0:
                    print(f"    {n}/{len(pendientes)}...")
                continue
            real = mac_del_equipo(sn)
            if not real or len(mac_wh) < 10:
                mudos += 1
            elif mac_wh[-10:] in real:
                confirmados += 1
                filas[i] = (id_servicio, nombre_wh, sn, nombre_so, "alta_confianza",
                           "CONFIRMADO contra el equipo: la MAC que reporta la ONU "
                           "es la misma que tiene WispHub")
            else:
                desmentidos += 1
                filas[i] = (id_servicio, nombre_wh, sn, nombre_so, "ambiguo",
                           "DESMENTIDO: el equipo reporta otra MAC -- este serial "
                           "NO es de este cliente")
            if n % 10 == 0:
                print(f"    {n}/{len(pendientes)}...")
            time.sleep(1)   # no atropellar la OLT
        print(f"[verificar-mac] confirmados {confirmados}, desmentidos "
             f"{desmentidos}, sin respuesta {mudos}")
        print()

    if args.validar:
        print("=" * 72)
        print("  VALIDACION -- cada propuesta contra el serial real")
        print("=" * 72)
        por_nivel: dict[str, list[int]] = {}
        for id_servicio, _n, sn, _ns, nivel, _m in filas:
            acierto = bool(sn) and "," not in sn and sn.upper() == verdad.get(id_servicio, "")
            propuso = bool(sn) and "," not in sn
            d = por_nivel.setdefault(nivel, [0, 0, 0])
            d[0] += 1
            d[1] += propuso
            d[2] += acierto
        print(f"{'nivel':<18}{'casos':>8}{'propone':>10}{'acierta':>10}{'precision':>12}")
        for nivel in ("alta_confianza", "solo_mac", "revisar_mac", "revisar_typo",
                     "ambiguo", "sin_candidato"):
            if nivel not in por_nivel:
                continue
            tot, prop, ok = por_nivel[nivel]
            pct = f"{100*ok/prop:.2f}%" if prop else "-"
            print(f"  {nivel:<16}{tot:>8}{prop:>10}{ok:>10}{pct:>12}")
        print()
        return

    conteo: dict[str, int] = {}
    for fila in filas:
        conteo[fila[4]] = conteo.get(fila[4], 0) + 1

    # Una sola lista, de mas firme a mas dudoso: la usan el resumen y el
    # orden del reporte. 'confirmado_ip' primero porque se comprobo contra el
    # equipo; 'solo_mac' abajo de 'alta_confianza' porque la MAC sola acierta
    # 7 de cada 10 (ver candidatos_por_mac).
    _NIVELES = ("confirmado_ip", "alta_confianza", "solo_mac", "revisar_typo",
               "revisar_mac", "revisar_ip_no_coincide", "revisar_tokens",
               "ambiguo", "sin_candidato")

    print("Resumen:")
    for nivel in _NIVELES:
        print(f"  {nivel}: {conteo.get(nivel, 0)}")
    print()

    print(f"{'id_servicio':<12}{'nombre':<35}{'confianza':<16}{'candidato(s)':<30}motivo")
    print("-" * 130)
    orden = {nivel: i for i, nivel in enumerate(_NIVELES)}
    for id_servicio, nombre, sn, nombre_so, confianza, motivo in sorted(
            filas, key=lambda f: (orden.get(f[4], len(_NIVELES)), f[0])):
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
