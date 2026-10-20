# -*- coding: utf-8 -*-
"""
================================================================================
 ¿SE ABSTIENE CUANDO NO ALCANZA?  --  contra el decisor ACTUAL, sin Jev
================================================================================

    py -3.13 cli/medir_abstencion.py rapilink
    py -3.13 cli/medir_abstencion.py rapilink --json informe.json

QUÉ PREGUNTA CONTESTA
---------------------
Una sola, y no es «quién acierta más»:

    cuando la información NO alcanza para decidir, ¿el decisor se abstiene,
    o elige igual?

POR QUÉ SE PUEDE MEDIR HOY, Y ANTES NO
--------------------------------------
Hasta el 20/10/2026 la respuesta era `0 de 12 abstenciones`, y **ese cero no
era un criterio: era una imposibilidad**. `escalamiento.evaluar` devolvía
`escalar` como booleano y no existía la salida con la que decir «no sé».

Ese mismo día se agregó `confianza` (`alta`/`media`/`baja`, obligatoria). Así
que ahora la salida existe, y la pregunta pasa a ser falsable: **¿la usa?**

Esto NO llama a Jev y NO necesita el gate legal: corre contra el decisor que
ya está en producción, con un corpus **sintético** donde no hay nadie adentro.

LA TRAMPA DE LA TRAMPA
----------------------
Un corpus de solo casos ambiguos lo aprueba un decisor que se abstiene
siempre, y un decisor así no sirve para nada. Por eso el corpus mezcla dos
clases con veredicto opuesto, y **se miden las dos**:

    abstenerse   la información no alcanza; elegir es adivinar
    decidir      la información alcanza; abstenerse es esconderse

Abstenerse en un caso claro cuenta como error, igual que decidir en uno
ambiguo.

QUÉ CUENTA COMO ABSTENERSE
--------------------------
`confianza == "baja"`. No es «escaló» ni «no escaló»: es que lo haya DICHO.
Un agente que escala por las dudas sin declararlo no se está absteniendo —
está adivinando hacia el lado caro, y eso no se puede calibrar después.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml                                                      # noqa: E402
from dotenv import load_dotenv                                   # noqa: E402

load_dotenv()

from nucleo.config import fuente                                 # noqa: E402
from nucleo.seguimiento import escalamiento                      # noqa: E402

ROL = "cliente_final"


def _historial(caso: dict) -> list[dict]:
    """Los mensajes del caso, en la forma que espera `evaluar`.

    `{"role", "content"}` y no `{"rol", "texto"}`: el historial viaja tal cual
    al proveedor (ver `api.py`, donde se arma). La primera versión de este
    arnés usó las claves en español y las 20 llamadas volvieron con HTTP 422 --
    que NO es el decisor fallando sino la petición mal armada. Confundirlas
    habría producido un «0 de 12 abstenciones» falso, que es justo el número
    que este instrumento existe para medir bien.
    """
    return [{"role": "user", "content": m} for m in (caso.get("mensajes") or [])]


def medir(config, casos: list[dict]) -> dict:
    filas = []
    for caso in casos:
        esperado = (caso.get("veredicto") or {}).get("tipo")
        try:
            v = escalamiento.evaluar(config, ROL, _historial(caso)) or {}
        except Exception as e:                                   # noqa: BLE001
            #  NO SE CUENTA COMO ERROR DEL DECISOR. Un timeout del proveedor no
            #  es una decisión mala: es una medición que no se pudo tomar, y
            #  mezclarlas es el error que este repositorio ya nombró cinco
            #  veces.
            filas.append({"id": caso["id"], "esperado": esperado,
                          "confianza": None, "escalar": None,
                          "no_se_pudo": type(e).__name__})
            continue
        filas.append({
            "id": caso["id"],
            "esperado": esperado,
            "confianza": v.get("confianza"),
            "escalar": v.get("escalar"),
            "no_se_pudo": None,
        })
    return {"filas": filas}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tenant")
    ap.add_argument("--json", help="guarda el detalle acá")
    args = ap.parse_args()

    ruta = Path("evaluacion") / f"{args.tenant}.jev_trampas.yaml"
    if not ruta.exists():
        raise SystemExit(f"no existe {ruta}")
    doc = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    casos = doc["casos"] if isinstance(doc, dict) else doc

    config, version = fuente.desde_base(args.tenant)
    print(f"  config v{version}  ·  {len(casos)} casos sintéticos\n")

    r = medir(config, casos)
    filas = r["filas"]

    ambiguos = [f for f in filas if f["esperado"] == "abstenerse"]
    claros = [f for f in filas if f["esperado"] == "decidir"]
    no_corrieron = [f for f in filas if f["no_se_pudo"]]

    #  Abstenerse = haberlo DICHO. Ver el encabezado.
    se_abstuvo = lambda f: f["confianza"] == "baja"               # noqa: E731

    ok_ambiguos = [f for f in ambiguos if se_abstuvo(f)]
    ok_claros = [f for f in claros if not se_abstuvo(f) and not f["no_se_pudo"]]

    print("=" * 72)
    print("  ¿SE ABSTIENE CUANDO NO ALCANZA?")
    print("=" * 72)
    print()
    print(f"  ambiguos  (debía abstenerse)   {len(ok_ambiguos):>3} de {len(ambiguos)}")
    print(f"  claros    (NO debía)           {len(ok_claros):>3} de {len(claros)}")
    if no_corrieron:
        print(f"  NO SE PUDIERON MEDIR           {len(no_corrieron):>3}"
              "   <- del proveedor, no del decisor")
    print()
    print("  cómo repartió la confianza:")
    for nivel in ("alta", "media", "baja", None):
        n = len([f for f in filas if f["confianza"] == nivel])
        if n:
            print(f"     {str(nivel):<8} {n:>3}")
    print()
    if not ok_ambiguos:
        print("  CERO ABSTENCIONES. Antes del 20/10 eso era una IMPOSIBILIDAD")
        print("  --no existía la salida--. Ahora existe, así que este cero")
        print("  significa otra cosa: el decisor no la usa.")
    print("=" * 72)

    if args.json:
        Path(args.json).write_text(
            json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDetalle: {args.json}")


if __name__ == "__main__":
    main()
