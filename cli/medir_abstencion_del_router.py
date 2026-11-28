# -*- coding: utf-8 -*-
"""
================================================================================
 ¿SE ABSTIENE EL ROUTER CUANDO NO SABE A QUÉ ÁREA VA?
================================================================================

    py -3.13 cli/medir_abstencion_del_router.py rapilink
    py -3.13 cli/medir_abstencion_del_router.py rapilink --json informe.json

POR QUÉ EXISTE, Y POR QUÉ NO ALCANZABA `medir_abstencion.py`
------------------------------------------------------------
Aquel mide la confianza de la decisión de **escalar** llamando a
`escalamiento.evaluar` directo. Este corpus, en cambio, etiqueta ambigüedad de
**ruteo** —sus doce casos ambiguos listan ÁREAS en `veredicto.entre`— y el
ruteo lo decide el router, dentro del turno, llamando a `derivar_a_area`.

Así que para medir lo que el corpus realmente etiqueta hay que **correr el
turno entero** y mirar con qué argumentos llamó a esa herramienta. Eso es lo
que hace esto, y es la diferencia entre «el campo existe» y «el campo sirve»:
la guarda `tests/test_el_router_puede_decir_que_no_sabe.py` afirma lo primero,
y no podía afirmar lo segundo.

QUÉ CUENTA COMO ABSTENERSE
--------------------------
Que la llamada a `derivar_a_area` haya traído `confianza: "baja"`. No alcanza
con que el router acierte el área: lo que se mide es si **dijo** que dudaba.
Un router que acierta por suerte y no lo declara no se puede calibrar después.

Y SE MIDE EL CASO CONTRARIO, que es la mitad que se olvida: en los ocho casos
claros, abstenerse es un error. Un corpus de solo trampas lo aprueba un router
que duda siempre, y un router así no sirve para nada.

UN TERCER RESULTADO, Y NO ES UN FALLO
-------------------------------------
Que el router **no derive**. Ante «buenas» puede ser lo correcto: preguntar
antes de mandar a nadie a ninguna cola. Se cuenta aparte -- mezclarlo con
«derivó sin dudar» sería el mismo error de las listas vacías que este
repositorio ya nombró cinco veces.

NO MANDA NADA. Corpus sintético, sin nadie adentro.
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
from nucleo.modelo import motor                                  # noqa: E402

DERIVAR = "derivar_a_area"


def _rol_de_entrada(config) -> str:
    """El rol con el que entra una conversación nueva: el que rutea."""
    nombre = getattr(config, "rol_de_entrada", None)
    if nombre and nombre in config.roles:
        return nombre
    #  Sin el campo, el primero orientado a cliente_final -- que es lo que
    #  hace el motor, con su aviso. Se replica y no se adivina otra cosa.
    for n, r in (config.roles or {}).items():
        if getattr(r, "orientado_a", "") == "cliente_final":
            return n
    raise SystemExit("no hay un rol de entrada para rutear")


def medir(config, casos: list[dict], rol: str) -> list[dict]:
    filas = []
    for caso in casos:
        esperado = (caso.get("veredicto") or {}).get("tipo")
        historial: list[dict] = []
        confianza = area = None
        derivo = False
        no_se_pudo = None
        try:
            for mensaje in (caso.get("mensajes") or []):
                _resp, registro, _ = motor.responder(
                    config, rol, mensaje, historial, None)
                for r in registro:
                    if r.get("herramienta") == DERIVAR:
                        derivo = True
                        p = r.get("parametros") or {}
                        confianza = p.get("confianza")
                        area = p.get("area")
        except Exception as e:                                   # noqa: BLE001
            #  Un fallo del proveedor NO es una decisión mala: es una
            #  medición que no se pudo tomar. Se cuenta aparte.
            no_se_pudo = type(e).__name__
        filas.append({"id": caso["id"], "esperado": esperado,
                      "derivo": derivo, "area": area,
                      "confianza": confianza, "no_se_pudo": no_se_pudo,
                      "entre": (caso.get("veredicto") or {}).get("entre")})
    return filas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tenant")
    ap.add_argument("--json")
    args = ap.parse_args()

    ruta = Path("evaluacion") / f"{args.tenant}.jev_trampas.yaml"
    if not ruta.exists():
        raise SystemExit(f"no existe {ruta}")
    doc = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    casos = doc["casos"] if isinstance(doc, dict) else doc

    config, version = fuente.desde_base(args.tenant)
    rol = _rol_de_entrada(config)
    print(f"  config v{version}  ·  rol de entrada: {rol}  ·  "
          f"{len(casos)} casos sintéticos\n")

    filas = medir(config, casos, rol)

    ambiguos = [f for f in filas if f["esperado"] == "abstenerse"]
    claros = [f for f in filas if f["esperado"] == "decidir"]
    dudo = lambda f: f["confianza"] == "baja"                     # noqa: E731

    #  Tres resultados, no dos. Ver el encabezado.
    amb_dudo = [f for f in ambiguos if f["derivo"] and dudo(f)]
    amb_seguro = [f for f in ambiguos if f["derivo"] and not dudo(f)]
    amb_no_derivo = [f for f in ambiguos if not f["derivo"] and not f["no_se_pudo"]]
    cla_ok = [f for f in claros if f["derivo"] and not dudo(f)]
    no_corrieron = [f for f in filas if f["no_se_pudo"]]

    print("=" * 72)
    print("  ¿SE ABSTIENE EL ROUTER CUANDO NO SABE?")
    print("=" * 72)
    print()
    print(f"  AMBIGUOS  ({len(ambiguos)})  -- el área no está clara")
    print(f"     derivó Y dijo que dudaba      {len(amb_dudo):>3}   <- lo que se busca")
    print(f"     derivó SIN dudar              {len(amb_seguro):>3}   <- el error caro")
    print(f"     no derivó                     {len(amb_no_derivo):>3}"
          "   <- también vale: preguntó antes")
    print()
    print(f"  CLAROS  ({len(claros)})  -- el área se deduce")
    print(f"     derivó sin dudar              {len(cla_ok):>3}   <- lo correcto")
    print(f"     derivó dudando                "
          f"{len([f for f in claros if f['derivo'] and dudo(f)]):>3}"
          "   <- esconderse")
    if no_corrieron:
        print()
        print(f"  NO SE PUDIERON MEDIR            {len(no_corrieron):>3}"
              "   <- del proveedor, no del router")

    if amb_seguro:
        print()
        print("  LOS QUE DERIVARON SIN DUDAR, uno por uno:")
        for f in amb_seguro:
            print(f"     {f['id']:<32} -> {f['area']:<18}"
                  f" (el corpus dice: {f['entre']})")

    print("=" * 72)

    if args.json:
        Path(args.json).write_text(
            json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDetalle: {args.json}")


if __name__ == "__main__":
    main()
