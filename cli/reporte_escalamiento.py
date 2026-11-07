# -*- coding: utf-8 -*-
"""
================================================================================
 REPORTE DE ESCALAMIENTO  --  cuanto escala el asistente, y por que
================================================================================

Nace de un hueco real: el 15/08/2026 se agrego 'escalamiento.
intentar_resolver_antes' (una vuelta extra antes de pasar a un humano, ver
tests/test_escalamiento_paciente.py) despues de que un cliente escalara en su
PRIMER mensaje sin que se intentara ningun diagnostico. El cambio se valido
mirando dos conversaciones a mano -- no hay forma de saber si funciona sobre
la poblacion real sin esto.

Mismo concepto que la 'tasa de escalada' que Intercom Fin reporta como
metrica de primera clase (investigado agosto 2026 comparando este proyecto
contra el rubro): cuantas conversaciones terminan en un humano, y por que
motivo, para poder ver si un cambio en el prompt o en la config lo mueve.

Uso
---
    py -3.13 cli/reporte_escalamiento.py --tenant rapilink --dias 7
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
# override=False: el entorno explicito gana, el archivo solo
# rellena. Ver el comentario largo en cli/cargar_config.py.
load_dotenv(override=False)

from nucleo.config import cargar_config
from nucleo.persistencia import db as persistencia
from nucleo.seguimiento import forzado


def main(tenant: str, dias: int) -> None:
    r = persistencia.tasa_escalamiento(tenant, dias)
    # Que motivos son forzados lo declara el catalogo del tenant
    # ('escalar_si_falla' / 'escalar_al_completar' por herramienta),
    # asi que hace falta la config para clasificar.
    config = cargar_config(
        Path(__file__).resolve().parent.parent / 'tenants'
        / f'{tenant}.config.yaml')

    print(f"Tenant: {tenant}  |  Ultimos {dias} dia(s)")
    print(f"Conversaciones: {r['total']}  |  Escaladas: {r['escaladas']}  |  "
         f"Tasa: {r['tasa']:.1%}")

    if not r["por_motivo"]:
        print("\n  (ninguna escalada en el periodo)")
        return

    print("\nPor motivo:")
    for motivo, n in sorted(r["por_motivo"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {motivo}")

    # Cuantas llegan a la bandeja diciendo que hay que hacer. Hasta el
    # 08/09/2026 este campo era opcional para el evaluador y salio vacio en
    # las 52 escaladas que habia: esa es la linea base contra la que comparar.
    #
    # EN DOS GRUPOS, y no en una sola tasa: a una escalada FORZADA por una
    # herramienta no se le exige relevo -- no hay de donde sacarlo, y que el
    # asistente lo invente es justo lo que se saco del resumen. Sumarlas al
    # mismo denominador haria ver mal al evaluador aunque estuviera
    # funcionando bien: de las 52 de la linea base, 26 son
    # 'pedido_para_ejecutar', todas forzadas.
    forzados = forzado.motivos_que_no_elige_el_modelo(config)
    grupos = {"evaluador": {"con": 0, "sin": 0}, "forzada": {"con": 0, "sin": 0}}
    for motivo, casilla in r["relevo_por_motivo"].items():
        destino = grupos["forzada" if motivo in forzados else "evaluador"]
        destino["con"] += casilla["con"]
        destino["sin"] += casilla["sin"]

    ev = grupos["evaluador"]
    print()
    print("RELEVO -- escaladas que decidio el evaluador")
    print(f"  {ev['con']:>4}  con proximo paso")
    print(f"  {ev['sin']:>4}  sin proximo paso")
    if ev["con"] + ev["sin"]:
        print(f"        {ev['con'] / (ev['con'] + ev['sin']):.0%} lo traen")
    else:
        print("        (ninguna en el periodo)")

    fz = grupos["forzada"]
    if fz["con"] + fz["sin"]:
        print()
        print("ESCALADAS FORZADAS por una herramienta")
        print(f"  {fz['con'] + fz['sin']:>4}  en total")
        print("        no se les exige relevo: lo forzo un hecho de la traza,")
        print("        no un juicio del evaluador")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--dias", type=int, default=7)
    args = parser.parse_args()
    main(args.tenant, args.dias)
