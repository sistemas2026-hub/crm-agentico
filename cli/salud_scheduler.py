# -*- coding: utf-8 -*-
"""
================================================================================
 SALUD DEL SCHEDULER  --  numeros, sin decir de quien son
================================================================================

    py -3.13 cli/salud_scheduler.py            una foto
    py -3.13 cli/salud_scheduler.py --json     la misma foto, para un exportador

Conecta con el rol 'monitor_ro', que no puede leer ni una fila de 'job_*': solo
puede llamar a 'asistente.job_salud()', que devuelve agregados por job. No hay
forma de sacar de aca a que empresa pertenece un atraso, y es a proposito --
una alerta etiquetada por cliente termina en un dashboard compartido que nadie
conto como parte del perimetro de datos.

Termina en 1 si algo esta mal, para que sirva como chequeo automatico:

  * un job con leases vencidos     hay workers muertos sin rescatar
  * atraso mayor a un intervalo    el barrido se esta quedando atras
  * sin exito en mucho tiempo      corre, pero no le sale

Lo que NO hace: arreglar nada. Es un termometro.
================================================================================
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo.programador import puerta

# Cuando un atraso deja de ser normal. Un tick de 60 s mas el trabajo tarda
# segundos; cinco minutos de atraso es que algo no esta barriendo.
ATRASO_MALO_SEG = 300


def foto() -> list[dict]:
    with puerta.sesion(puerta.MONITOR) as cur:
        return [dict(f) for f in puerta.salud(cur)]


def problemas(filas: list[dict]) -> list[str]:
    malas = []
    for f in filas:
        if f.get("leases_vencidos"):
            malas.append(f"{f['job_code']}: {f['leases_vencidos']} lease(s) "
                         f"vencido(s) sin rescatar")
        atraso = f.get("atraso_max_seg") or 0
        if atraso > ATRASO_MALO_SEG:
            malas.append(f"{f['job_code']}: {atraso / 60:.1f} min de atraso "
                         f"maximo")
        sin_exito = f.get("sin_exito_max_seg")
        if sin_exito is not None and sin_exito > 24 * 3600:
            malas.append(f"{f['job_code']}: alguna organizacion lleva "
                         f"{sin_exito / 3600:.1f} h sin un exito")
    return malas


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    desconocidos = [a for a in argv if a != "--json"]
    if desconocidos:
        print(f"no entiendo {desconocidos}")
        return 2

    try:
        filas = foto()
    except Exception as e:                                       # noqa: BLE001
        print(f"[salud] no se pudo consultar: {type(e).__name__}: {e}")
        return 1

    if "--json" in argv:
        print(json.dumps({"jobs": filas, "problemas": problemas(filas)},
                         default=str, indent=2, ensure_ascii=False))
        return 1 if problemas(filas) else 0

    if not filas:
        print("[salud] ningun job programado todavia.")
        return 0

    print(f"{'job':<24} {'orgs':>5} {'corr':>5} {'retry':>6} {'lease!':>7} "
          f"{'pend':>5} {'atraso':>9} {'sin exito':>11}")
    for f in filas:
        atraso = f.get("atraso_max_seg")
        sin_exito = f.get("sin_exito_max_seg")
        print(f"{f['job_code']:<24} {f['organizaciones']:>5} "
              f"{f['corriendo']:>5} {f['en_backoff']:>6} "
              f"{f['leases_vencidos']:>7} {f['vencidos_sin_tomar']:>5} "
              f"{(f'{atraso / 60:.1f} min' if atraso else '-'):>9} "
              f"{(f'{sin_exito / 3600:.1f} h' if sin_exito else '-'):>11}")

    malas = problemas(filas)
    if malas:
        print()
        for m in malas:
            print(f"  [MAL] {m}")
        return 1
    print("\n  [OK] nada atrasado, nada abandonado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
