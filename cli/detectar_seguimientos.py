# -*- coding: utf-8 -*-
"""
================================================================================
 DETECTOR DE SEGUIMIENTOS PENDIENTES  --  primer entregable del scheduler
================================================================================

DETECTA quien no tuvo contacto en mas de N dias. NO actua -- no manda
mensajes, no decide que decirle a nadie. Eso es logica de negocio del rol
que use esto (ej. un futuro Vendedor) y todavia no esta definida.

Corrida manual hoy, cron mañana: el mecanismo (persistencia +
'actualizado_en' por conversacion) ya es el mismo que necesitaria un
scheduler real -- lo que falta despues es quien dispara esto solo y que
hace con la lista.

Uso
---
    py -3.13 cli/detectar_seguimientos.py --tenant rapilink --dias 3
    py -3.13 cli/detectar_seguimientos.py --tenant rapilink --dias 3 --canal whatsapp
================================================================================
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from nucleo.persistencia import db as persistencia


def _parsear_fecha(texto: str) -> datetime:
    # SQLite guarda 'AAAA-MM-DDTHH:MM:SS.ffffffZ' (strftime %Y-%m-%dT%H:%M:%fZ).
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def main(tenant: str, dias: int, canal: str | None) -> None:
    ahora = datetime.now(timezone.utc)
    corte = ahora - timedelta(days=dias)

    conversaciones = persistencia.ultima_actividad(tenant, canal)
    pendientes = [c for c in conversaciones if _parsear_fecha(c["actualizado_en"]) < corte]

    print(f"Tenant: {tenant}  |  Umbral: {dias} dia(s) sin contacto"
         f"{f'  |  Canal: {canal}' if canal else ''}")
    print(f"Conversaciones totales: {len(conversaciones)}  |  "
         f"Sin contacto hace mas de {dias} dia(s): {len(pendientes)}")
    print()

    if not pendientes:
        print("  (nada pendiente)")
        return

    for c in pendientes:
        inactivo_desde = ahora - _parsear_fecha(c["actualizado_en"])
        print(f"  - {c['usuario_externo']:<20} canal={c['canal']:<10} "
             f"rol={c['rol_efectivo'] or '?':<15} "
             f"ultimo contacto hace {inactivo_desde.days} dia(s) "
             f"({c['actualizado_en']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--dias", type=int, required=True,
                        help="Umbral de dias sin contacto para considerarlo pendiente.")
    parser.add_argument("--canal", default=None)
    args = parser.parse_args()
    main(args.tenant, args.dias, args.canal)
