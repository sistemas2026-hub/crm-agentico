# -*- coding: utf-8 -*-
"""
================================================================================
 APLICAR sn_onu  -  escribe los candidatos de alta confianza, con verificacion
================================================================================

Toma el CSV que genera cli/proponer_sn_onu.py y escribe 'sn_onu' en WispHub
SOLO para las filas 'alta_confianza'. Cada escritura se relee aparte para
confirmar que persistio de verdad -- ya esta documentado (skill wisphub-api)
que un PATCH puede devolver 200 sin guardar nada. No confiar en el codigo de
respuesta, confiar en lo que se lee despues.

Ademas de lo escrito, genera un documento con TODO lo que queda pendiente de
revision manual: los niveles 'revisar_typo'/'ambiguo'/'sin_candidato' del CSV
original, MAS cualquier 'alta_confianza' que haya fallado al escribir o al
persistir -- nada se pierde silenciosamente.

Uso
---
    py -3.13 cli/aplicar_sn_onu.py --csv candidatos_sn_onu.csv --piloto 10
        # solo escribe los primeros 10 alta_confianza, para validar el patron
        # antes de comprometerse con el resto

    py -3.13 cli/aplicar_sn_onu.py --csv candidatos_sn_onu.csv
        # escribe TODOS los alta_confianza

    py -3.13 cli/aplicar_sn_onu.py --csv candidatos_sn_onu.csv --dry-run
        # no escribe nada, solo simula y arma el reporte
================================================================================
"""

from __future__ import annotations

import argparse
import csv as csv_mod
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

import requests

WISPHUB_BASE_URL = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
WISPHUB_HEADERS = {"Authorization": f"Api-Key {os.environ.get('WISPHUB_API_KEY', '')}"}


def _con_reintento(fn, intentos: int = 3, espera: float = 2.0):
    for i in range(intentos):
        try:
            return fn()
        except requests.exceptions.RequestException:
            if i == intentos - 1:
                raise
            time.sleep(espera)


def leer_cliente(id_servicio: str) -> dict | None:
    r = _con_reintento(lambda: requests.get(
        f"{WISPHUB_BASE_URL}/api/clientes/", headers=WISPHUB_HEADERS,
        params={"id_servicio": id_servicio}, timeout=20))
    r.raise_for_status()
    resultados = r.json().get("results", [])
    return resultados[0] if resultados else None


def escribir_sn_onu(id_servicio: str, sn_onu: str) -> tuple[bool, str]:
    """PATCH + relectura. Devuelve (persistio, detalle)."""
    r = _con_reintento(lambda: requests.patch(
        f"{WISPHUB_BASE_URL}/api/clientes/{id_servicio}/", headers=WISPHUB_HEADERS,
        json={"sn_onu": sn_onu}, timeout=20))
    if r.status_code != 200:
        return False, f"PATCH devolvio HTTP {r.status_code}: {r.text[:150]}"

    # No confiar en el 200 -- releer aparte (ver docstring del modulo).
    time.sleep(0.3)
    releido = leer_cliente(id_servicio)
    if releido is None:
        return False, "PATCH devolvio 200 pero el cliente ya no aparece al releer"
    if (releido.get("sn_onu") or "") == sn_onu:
        return True, "confirmado por relectura"
    return False, f"PATCH devolvio 200 pero al releer sn_onu={releido.get('sn_onu')!r} (no persistio)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, help="CSV generado por proponer_sn_onu.py")
    ap.add_argument("--piloto", type=int, default=None,
                    help="Escribir solo los primeros N alta_confianza, para validar antes del resto")
    ap.add_argument("--dry-run", action="store_true", help="No escribe nada, solo simula")
    ap.add_argument("--pendientes-doc", default="pendientes_sn_onu_manual.md",
                    help="Donde guardar el documento de pendientes")
    ap.add_argument("--desde-indice", type=int, default=0,
                    help="Retomar desde esta posicion del listado alta_confianza "
                         "(0-based) -- para continuar un lote cortado a mitad de camino "
                         "sin repetir lo ya confirmado")
    ap.add_argument("--sin-relectura-previa", action="store_true",
                    help="Se salta el chequeo 'releer antes de escribir' (pensado para una "
                         "carrera con otra edicion simultanea, poco probable) -- va a la "
                         "escritura directo. Reduce a 2 llamadas por registro en vez de 3. "
                         "La verificacion POSTERIOR (releer para confirmar que persistio) "
                         "se mantiene siempre, esa no se negocia.")
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8") as f:
        filas = list(csv_mod.DictReader(f))

    alta = [f for f in filas if f["confianza"] == "alta_confianza"]
    resto = [f for f in filas if f["confianza"] != "alta_confianza"]

    ya_saltados_por_reanudacion = alta[:args.desde_indice]
    if args.piloto:
        alta_a_escribir = alta[args.desde_indice:args.desde_indice + args.piloto]
        print(f"MODO PILOTO: escribiendo solo {len(alta_a_escribir)} de {len(alta)} alta_confianza")
    else:
        alta_a_escribir = alta[args.desde_indice:]
    if args.desde_indice:
        print(f"Retomando desde el indice {args.desde_indice} "
             f"({len(ya_saltados_por_reanudacion)} ya confirmados antes, no se tocan)")

    print("=" * 72)
    print(f"  {'[DRY-RUN] ' if args.dry_run else ''}Aplicando sn_onu -- "
         f"{len(alta_a_escribir)} candidatos de alta confianza")
    print("=" * 72)

    confirmados = []
    ya_resueltos = []  # ya tenian EXACTO el candidato -- no es un pendiente
    fallidos = []

    for i, fila in enumerate(alta_a_escribir, 1):
        id_servicio = fila["id_servicio"]
        sn_onu = fila["sn_onu_candidato"]
        nombre = fila["nombre_wisphub"]

        if args.dry_run:
            print(f"[{i}/{len(alta_a_escribir)}] (simulado) {id_servicio} {nombre} -> {sn_onu}")
            confirmados.append(fila)
            continue

        if not args.sin_relectura_previa:
            # Releer ANTES de escribir: si alguien ya le cargo un serial entre
            # el sondeo y ahora, no lo pisamos.
            actual = leer_cliente(id_servicio)
            if actual is None:
                fallidos.append({**fila, "motivo_fallo": "el cliente ya no existe/no aparece"})
                print(f"[{i}/{len(alta_a_escribir)}] {id_servicio} {nombre}: OMITIDO -- no aparece")
                continue
            if actual.get("sn_onu"):
                if actual["sn_onu"] == sn_onu:
                    # Ya quedo en el estado deseado (ej. un piloto anterior) --
                    # NO es un pendiente, esta resuelto.
                    ya_resueltos.append(fila)
                    print(f"[{i}/{len(alta_a_escribir)}] {id_servicio} {nombre}: "
                         f"YA RESUELTO (ya tenia exactamente {sn_onu})")
                else:
                    fallidos.append({**fila, "motivo_fallo":
                                    f"ya tenia sn_onu={actual['sn_onu']!r} DISTINTO al candidato "
                                    f"propuesto ({sn_onu}) -- no se pisa, requiere revision"})
                    print(f"[{i}/{len(alta_a_escribir)}] {id_servicio} {nombre}: "
                         f"OMITIDO -- tiene otro serial ({actual['sn_onu']})")
                continue

        ok, detalle = escribir_sn_onu(id_servicio, sn_onu)
        if ok:
            confirmados.append(fila)
            print(f"[{i}/{len(alta_a_escribir)}] {id_servicio} {nombre} -> {sn_onu}: OK ({detalle})")
        else:
            fallidos.append({**fila, "motivo_fallo": detalle})
            print(f"[{i}/{len(alta_a_escribir)}] {id_servicio} {nombre} -> {sn_onu}: FALLO ({detalle})")

    print()
    print(f"Confirmados ahora: {len(confirmados)} / {len(alta_a_escribir)}")
    print(f"Ya resueltos de antes: {len(ya_resueltos)}")
    print(f"Fallidos: {len(fallidos)}")

    # El documento de pendientes: todo lo que NO quedo resuelto de forma
    # automatica -- el resto del CSV original (revisar_typo/ambiguo/
    # sin_candidato) MAS los alta_confianza que no se llegaron a escribir
    # en ESTA corrida (piloto parcial) o que fallaron al persistir. Los
    # saltados por '--desde-indice' NO entran aca -- esos ya se resolvieron
    # (o fallaron y quedaron registrados) en una corrida anterior, listarlos
    # de nuevo como pendientes seria un falso negativo.
    no_procesados_en_esta_corrida = [
        f for f in alta if f not in alta_a_escribir and f not in ya_saltados_por_reanudacion]
    pendientes = resto + no_procesados_en_esta_corrida + fallidos

    with open(args.pendientes_doc, "w", encoding="utf-8") as f:
        f.write("# Pendientes de sn_onu -- revision manual\n\n")
        f.write(f"Generado tras aplicar automaticamente {len(confirmados) + len(ya_resueltos)} de "
               f"{len(alta)} candidatos de alta confianza. Quedan **{len(pendientes)}** "
               f"clientes que necesitan que alguien los revise a mano.\n\n")

        secciones = [
            ("Fallaron al escribir/persistir (eran alta_confianza)", fallidos),
            ("No procesados en este lote (piloto parcial)", no_procesados_en_esta_corrida),
            ("Posible typo -- confirmar el candidato a simple vista", [r for r in resto if r["confianza"] == "revisar_typo"]),
            ("Ambiguo -- nombre duplicado o mas de un candidato", [r for r in resto if r["confianza"] == "ambiguo"]),
            ("Sin candidato -- ninguna ONU con nombre parecido", [r for r in resto if r["confianza"] == "sin_candidato"]),
        ]
        for titulo, grupo in secciones:
            if not grupo:
                continue
            f.write(f"## {titulo} ({len(grupo)})\n\n")
            f.write("| id_servicio | nombre | candidato(s) | motivo |\n")
            f.write("|---|---|---|---|\n")
            for r in grupo:
                candidato = r.get("sn_onu_candidato", "")
                motivo = r.get("motivo_fallo") or r.get("motivo", "")
                f.write(f"| {r['id_servicio']} | {r['nombre_wisphub']} | {candidato} | {motivo} |\n")
            f.write("\n")

    print(f"\nDocumento de pendientes: {args.pendientes_doc}")


if __name__ == "__main__":
    main()
