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

from nucleo.persistencia import db as persistencia


def main(tenant: str, dias: int) -> None:
    r = persistencia.tasa_escalamiento(tenant, dias)

    print(f"Tenant: {tenant}  |  Ultimos {dias} dia(s)")
    print(f"Conversaciones: {r['total']}  |  Escaladas: {r['escaladas']}  |  "
         f"Tasa: {r['tasa']:.1%}")

    if not r["por_motivo"]:
        print("\n  (ninguna escalada en el periodo)")
        return

    print("\nPor motivo:")
    for motivo, n in sorted(r["por_motivo"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {motivo}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--dias", type=int, default=7)
    args = parser.parse_args()
    main(args.tenant, args.dias)
