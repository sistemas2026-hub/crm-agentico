# -*- coding: utf-8 -*-
"""
================================================================================
 M06-D  --  integridad de la matriz de clasificacion de autonomia
================================================================================

La matriz (M06-D_MATRIZ_AUTONOMIA.yaml) es una PROPUESTA: el runtime no la lee.
Esta prueba no la cree por lo que dice de si misma: la cruza contra el catalogo
real (tenants/rapilink.config.yaml) y contra la clasificacion R0-R4 de
tests/test_m10a_gobierno_frontera.py, y comprueba que las citas de evidencia
'archivo:linea' existan de verdad.

Validaciones del bloque:
  A. las 76 herramientas aparecen exactamente una vez (69 + 7 de origin, M06-F)
  B. ninguna duplicada
  C. ninguna desaparece, ninguna sobra
  D. R3/R4 identificadas como en M10-A
  E. las seis criticas conservan aprobacion humana obligatoria
  F. ninguna escritura es nivel 3 "por ser escritura": cada nivel 3 cita su regla
  G. ninguna lectura sube de nivel sin justificarlo
  H. lo irreversible no queda en un nivel permisivo
  I. las indeterminadas dicen que falta
Y ademas: que la matriz NO se aplico al runtime.
================================================================================
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                            # noqa: E402
from tests.test_m10a_gobierno_frontera import (R1_INTERNO,         # noqa: E402
                                               R2_REGISTRO_EXTERNO,
                                               R3_EQUIPO_FISICO, R4_DINERO)

FALLOS: list[str] = []
CAMPOS = ("nombre", "tipo", "clase", "nivel", "aprobacion_humana", "efecto_externo",
          "reversible", "riesgo", "justificacion", "barreras", "evidencia")
#  M06-F: registrar_promesa_y_reactivar (R4, llego en origin) es la sexta.
CRITICAS = {"reiniciar_ont", "activar_catv", "cambiar_tipo_onu",
            "registrar_pago", "agregar_promesa_pago", "registrar_promesa_y_reactivar"}
TOTAL = 76      # 69 de M06-D + 7 que trajo origin (M06-F)


def afirmar(c: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if c else "  [FALLA] ") + que)
    if not c:
        FALLOS.append(que)
        if detalle:
            print(f"          {detalle}")


def main() -> int:
    print("=" * 78)
    print("  M06-D  --  integridad de la matriz de autonomia")
    print("=" * 78)
    matriz = yaml.safe_load((RAIZ / "M06-D_MATRIZ_AUTONOMIA.yaml").read_text(encoding="utf-8"))
    filas = matriz["herramientas"]
    catalogo = {h.nombre: h for h in
                cargar_config(RAIZ / "tenants" / "rapilink.config.yaml").herramientas}
    nombres = [f["nombre"] for f in filas]
    por_nombre = {f["nombre"]: f for f in filas}

    print(f"\n-- A/B/C. Las {TOTAL}, una vez cada una --")
    afirmar(len(catalogo) == TOTAL, f"el catalogo tiene {len(catalogo)} herramientas")
    duplicadas = sorted({n for n in nombres if nombres.count(n) > 1})
    afirmar(not duplicadas, f"B. ninguna duplicada {duplicadas}")
    faltan = sorted(set(catalogo) - set(nombres))
    sobran = sorted(set(nombres) - set(catalogo))
    afirmar(not faltan and not sobran, f"C. ninguna falta {faltan} y ninguna sobra {sobran}")
    afirmar(len(filas) == TOTAL and set(nombres) == set(catalogo),
            f"A. las {TOTAL} exactamente una vez ({len(filas)} filas)")

    print("\n-- Cada fila completa y coherente con el catalogo --")
    incompletas = [f["nombre"] for f in filas
                   if any(f.get(c) in (None, "") for c in CAMPOS)]
    afirmar(not incompletas, f"las 11 columnas en todas las filas {incompletas}")
    mal_tipo = [n for n, f in por_nombre.items() if n in catalogo and
                f["tipo"] != ("lectura" if catalogo[n].solo_lectura else "escritura")]
    afirmar(not mal_tipo, f"lectura/escritura coincide con solo_lectura del catalogo {mal_tipo}")
    mal_aprob = [n for n, f in por_nombre.items() if n in catalogo and
                 bool(f["aprobacion_humana"]) != bool(catalogo[n].aprobacion_humana)]
    afirmar(not mal_aprob, f"la aprobacion humana coincide con el catalogo {mal_aprob}")
    niveles_validos = {0, 1, 2, 3, "INDETERMINADA"}
    raros = [n for n, f in por_nombre.items() if f["nivel"] not in niveles_validos]
    afirmar(not raros, f"todos los niveles son 0/1/2/3/INDETERMINADA {raros}")

    print("\n-- D. Clases R0-R4 como en M10-A --")
    esperada = {}
    for n, h in catalogo.items():
        esperada[n] = ("R0" if h.solo_lectura else "R1" if n in R1_INTERNO else
                       "R2" if n in R2_REGISTRO_EXTERNO else "R3" if n in R3_EQUIPO_FISICO
                       else "R4" if n in R4_DINERO else "?")
    mal_clase = [(n, por_nombre[n]["clase"], esperada[n]) for n in por_nombre
                 if n in esperada and por_nombre[n]["clase"] != esperada[n]]
    afirmar(not mal_clase, f"D. la clase de cada una es la de M10-A {mal_clase}")
    afirmar({n for n, f in por_nombre.items() if f["clase"] in ("R3", "R4")} == CRITICAS,
            f"D. R3 y R4 son exactamente las {len(CRITICAS)} criticas")

    print(f"\n-- E. Las {len(CRITICAS)} criticas conservan aprobacion humana obligatoria --")
    for n in sorted(CRITICAS):
        f, h = por_nombre[n], catalogo[n]
        afirmar(f["aprobacion_humana"] is True and h.aprobacion_humana and h.irreversible
                and f["nivel"] == 3,
                f"E. {n}: aprobacion en la matriz y en el catalogo, irreversible, nivel 3")

    print("\n-- F. Ningun nivel 3 'por ser escritura' --")
    sin_regla = [n for n, f in por_nombre.items() if f["nivel"] == 3
                 and not re.search(r"\bC3\b|\bC4b\b|\bC4c\b", f["justificacion"])]
    afirmar(not sin_regla, f"F. cada nivel 3 cita la regla que lo decide (C3/C4b/C4c) {sin_regla}")
    escrituras = [f for f in filas if f["tipo"] == "escritura"]
    distribucion = sorted({str(f["nivel"]) for f in escrituras})
    afirmar(len(distribucion) > 1, f"F. las escrituras NO son todas del mismo nivel {distribucion}")

    print("\n-- G. Ninguna lectura sube sin justificarlo --")
    lecturas_altas = [n for n, f in por_nombre.items()
                      if f["tipo"] == "lectura" and f["nivel"] not in (0, "INDETERMINADA")]
    afirmar(not lecturas_altas, f"G. toda lectura es 0 o INDETERMINADA {lecturas_altas}")

    print("\n-- H. Lo irreversible no queda en un nivel permisivo --")
    irreversibles = [n for n, f in por_nombre.items()
                     if str(f["reversible"]).strip().lower().startswith("no")
                     and not str(f["reversible"]).lower().startswith("no_aplica")
                     and f["tipo"] == "escritura"]
    permisivas = [n for n in irreversibles if por_nombre[n]["nivel"] in (0, 1, 2)]
    afirmar(not permisivas, f"H. ninguna escritura irreversible en 0/1/2 {permisivas}",
            str(irreversibles))
    no_verificadas = [n for n, f in por_nombre.items() if f["tipo"] == "escritura"
                      and f["reversible"] == "no_verificado"
                      and f["nivel"] in (0, 1, 2)]
    afirmar(not no_verificadas,
            f"H. ninguna escritura de reversibilidad no verificada en 0/1/2 {no_verificadas}")
    nivel2_sin_evidencia = [n for n, f in por_nombre.items() if f["nivel"] == 2
                            and not re.search(r"evidenciado|idempotente|re-derivable|upsert|inerte",
                                              str(f["reversible"]))]
    afirmar(not nivel2_sin_evidencia,
            f"H. cada nivel 2 declara en que se basa su reversibilidad {nivel2_sin_evidencia}")

    print("\n-- I. Las indeterminadas dicen que falta --")
    indet = [n for n, f in por_nombre.items() if f["nivel"] == "INDETERMINADA"]
    sin_falta = [n for n in indet if not str(por_nombre[n].get("falta") or "").strip()]
    afirmar(indet and not sin_falta, f"I. {len(indet)} indeterminadas, todas con 'falta' {sin_falta}")
    falta_de_mas = [n for n, f in por_nombre.items()
                    if f["nivel"] != "INDETERMINADA" and f.get("falta")]
    afirmar(not falta_de_mas, f"I. 'falta' solo aparece en las indeterminadas {falta_de_mas}")

    print("\n-- La evidencia citada existe --")
    rotas = []
    citas = 0
    for f in filas:
        for ruta, linea in re.findall(r"([\w./-]+\.py):(\d+)", f["evidencia"]):
            citas += 1
            cand = [RAIZ / ruta, RAIZ / "django-crm" / "backend" / ruta]
            archivo = next((c for c in cand if c.exists()), None)
            if archivo is None:
                rotas.append(f"{f['nombre']}: {ruta} no existe")
            elif int(linea) > len(archivo.read_text(encoding="utf-8").splitlines()):
                rotas.append(f"{f['nombre']}: {ruta}:{linea} fuera del archivo")
    afirmar(citas > 0 and not rotas, f"{citas} citas archivo:linea, todas apuntan a algo real {rotas}")

    print("\n-- La matriz NO se aplico al runtime --")
    declaradas = [n for n, h in catalogo.items() if h.nivel_autonomia is not None]
    afirmar(not declaradas, f"ninguna herramienta del catalogo declara nivel_autonomia {declaradas}")
    fuentes = " ".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in (RAIZ / "nucleo").rglob("*.py"))
    afirmar("M06-D_MATRIZ_AUTONOMIA" not in fuentes, "ningun modulo del nucleo lee la matriz")

    print("\n-- Resumen de la propuesta --")
    from collections import Counter
    cuenta = Counter(str(f["nivel"]) for f in filas)
    print("  " + "  ".join(f"nivel {k}: {v}" for k, v in sorted(cuenta.items())))

    print()
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for x in FALLOS:
            print(f"    - {x}")
        return 1
    print(f"  [OK] La matriz cubre las {TOTAL}, coincide con el catalogo y no se aplico al runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
