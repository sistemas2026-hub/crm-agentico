# -*- coding: utf-8 -*-
"""
================================================================================
 LA GUARDA  -  el nucleo no puede conocer a ningun cliente
================================================================================

El diseno pide: "Si detectas que estas por escribir logica especifica de un
cliente, detente y avisame." El problema de esa regla es que depende de que
alguien se acuerde, y nadie se acuerda a las 11 de la noche de un viernes.

Esta prueba la vuelve automatica. Lee los slugs de tenants/*.config.yaml y
falla si alguno aparece bajo nucleo/. Tambien caza las formas tipicas de
colar logica por cliente sin nombrarlo.

Que hacer cuando falla
----------------------
NO agregar una excepcion. La falla significa que hay un comportamiento
especifico de un cliente metido en el motor: eso va a tenants/<slug>.config.yaml
y el nucleo lo lee de la configuracion.

    py -3.13 tests/test_nucleo_sin_tenants.py
================================================================================
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
NUCLEO = RAIZ / "nucleo"
TENANTS = RAIZ / "tenants"

# Se ignora la plantilla: su slug es de ejemplo y no corresponde a nadie.
SLUGS_EXENTOS = {"mi-isp"}

# Hosts de PROVEEDORES DE MODELO. Son infraestructura de la plataforma, no de
# un cliente: identicos para todos los tenants, como el endpoint de cualquier
# libreria. Moverlos a la configuracion obligaria a repetir la misma URL en el
# YAML de cada empresa — mas fragil, no menos.
#
# La distincion no es de conveniencia: el endpoint de un sistema de GESTION
# (WispHub y equivalentes) SI es de un cliente, porque otra empresa puede usar
# otro sistema. Esos siguen prohibidos aqui.
HOSTS_DE_PLATAFORMA = {
    "api.deepseek.com",
    "dashscope-intl.aliyuncs.com",
    "open.bigmodel.cn",
    "api.moonshot.cn",
    "api.openai.com",
    "api.anthropic.com",
}

# Formas de meter logica por cliente sin escribir su nombre.
PATRONES_SOSPECHOSOS = [
    (re.compile(r"\bif\s+tenant(_id|_slug)?\s*==", re.I),
     "rama condicional por tenant"),
    (re.compile(r"\bslug\s*==\s*[\"']", re.I),
     "comparacion contra un slug literal"),
    (re.compile(r"\bwisphub\b", re.I),
     "nombre de un proveedor concreto (va en la config, como endpoint)"),
    (re.compile(r"https?://(?!localhost|127\.0\.0\.1)[a-z0-9.\-]+\.[a-z]{2,}", re.I),
     "URL de un servicio concreto embebida"),
]


def slugs_de_tenants() -> list[str]:
    out = []
    for archivo in sorted(TENANTS.glob("*.yaml")):
        try:
            datos = yaml.safe_load(archivo.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        slug = (datos.get("identidad") or {}).get("slug")
        if slug and slug not in SLUGS_EXENTOS:
            out.append(slug)
    return out


def archivos_del_nucleo() -> list[Path]:
    return [p for p in NUCLEO.rglob("*.py") if "__pycache__" not in p.parts]


def solo_codigo(texto: str) -> list[str]:
    """
    Devuelve las lineas con los COMENTARIOS y DOCSTRINGS en blanco.

    Se ignoran porque son documentacion: un comentario que dice "medido en la
    base de Rapilink" explica una decision, no la implementa. Marcarlo seria un
    falso positivo, y una guarda que grita en falso deja de leerse.

    Las CADENAS del codigo NO se blanquean, a proposito: ahi es justamente
    donde se esconde un slug hardcodeado ( if tenant == "rapilink" ).

    Se conserva el numero de linea para que el informe sea util.
    """
    lineas = texto.splitlines()
    en_blanco = [False] * (len(lineas) + 1)

    # 1) docstrings: cadena suelta como primera sentencia de modulo/clase/funcion
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return lineas                      # si no parsea, se revisa tal cual
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cuerpo = getattr(nodo, "body", [])
        if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                and isinstance(cuerpo[0].value, ast.Constant)
                and isinstance(cuerpo[0].value.value, str)):
            doc = cuerpo[0]
            for n in range(doc.lineno, (doc.end_lineno or doc.lineno) + 1):
                if n < len(en_blanco):
                    en_blanco[n] = True

    salida = ["" if en_blanco[i + 1] else l for i, l in enumerate(lineas)]

    # 2) comentarios: se recorta la porcion comentada de cada linea
    try:
        for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
            if tok.type == tokenize.COMMENT:
                fila, col = tok.start
                if fila - 1 < len(salida):
                    salida[fila - 1] = salida[fila - 1][:col]
    except (tokenize.TokenError, IndentationError):
        pass
    return salida


def revisar() -> list[str]:
    fallas: list[str] = []
    slugs = slugs_de_tenants()
    archivos = archivos_del_nucleo()

    if not archivos:
        return ["nucleo/ no tiene ningun .py — ¿estructura incompleta?"]

    for ruta in archivos:
        rel = ruta.relative_to(RAIZ)
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        for n, linea in enumerate(solo_codigo(texto), 1):
            if not linea.strip():
                continue
            for slug in slugs:
                if re.search(rf"\b{re.escape(slug)}\b", linea, re.I):
                    fallas.append(
                        f"{rel}:{n}  menciona el tenant '{slug}'\n"
                        f"      -> {linea.strip()[:90]}")
            for patron, motivo in PATRONES_SOSPECHOSOS:
                m = patron.search(linea)
                if not m:
                    continue
                # Un endpoint de proveedor de modelo es infraestructura de la
                # plataforma, no conocimiento de un cliente.
                if "URL" in motivo and any(h in m.group(0)
                                           for h in HOSTS_DE_PLATAFORMA):
                    continue
                fallas.append(f"{rel}:{n}  {motivo}\n"
                              f"      -> {linea.strip()[:90]}")
    return fallas


if __name__ == "__main__":
    slugs = slugs_de_tenants()
    archivos = archivos_del_nucleo()
    print(f"Revisando {len(archivos)} archivo(s) de nucleo/ contra "
          f"{len(slugs)} tenant(s): {', '.join(slugs) or '(ninguno)'}\n")

    fallas = revisar()
    if fallas:
        print(f"[FALLA] {len(fallas)} filtracion(es) de logica por cliente:\n")
        for f in fallas:
            print(f"  {f}")
        print("\n  Esto NO se arregla con una excepcion: el comportamiento va a")
        print("  tenants/<slug>.config.yaml y el nucleo lo lee de ahi.")
        sys.exit(1)

    print("[OK] El nucleo no conoce a ningun cliente.")
