# -*- coding: utf-8 -*-
"""
================================================================================
 SONDEO SISTEMATICO DE LA API DEL ISP
================================================================================

Recorre los endpoints de la API y reporta que existe, cuantos registros tiene y
que campos devuelve. Es el paso 1 para ampliar el catalogo de un tenant o para
dar de alta un ISP nuevo.

Por que existe
--------------
La documentacion de la API es una hipotesis. Medido contra produccion: anuncia
filtros que IGNORA en silencio, devolviendo el universo entero como si fuera la
respuesta filtrada. No da error. Un total exacto respondiendo otra pregunta es
peor que un error, porque nadie lo detecta.

Ver .claude/skills/wisphub-api/SKILL.md para el metodo completo y los hallazgos
ya confirmados.

Que hace y que NO hace
----------------------
Este script DESCUBRE: que endpoints responden, con cuantos registros y que
campos. NO verifica filtros — eso es el segundo paso, con el metodo del valor
imposible, porque requiere saber que filtro probar contra que valor real.

SOLO LECTURA. No escribe nada en la plataforma del ISP.

Uso
---
    py -3.13 cli/sondear_api.py                 # endpoints conocidos y candidatos
    py -3.13 cli/sondear_api.py --campos        # ademas lista los campos de cada uno
================================================================================
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv                                    # noqa: E402
load_dotenv(RAIZ / ".env", override=True)

BASE = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
CLAVE = os.environ.get("WISPHUB_API_KEY")
if not CLAVE:
    raise SystemExit("Falta WISPHUB_API_KEY en el .env")

HEADERS = {"Authorization": f"Api-Key {CLAVE}", "Content-Type": "application/json"}

# Los que ya estan en el catalogo, mas los que el PRD lista como sin explorar.
# Un endpoint que responde 200 con 0 registros EXISTE pero no tiene datos:
# '/api/gastos/' es el caso ya conocido, y por eso el informe de materiales
# tuvo que salir del texto de los tickets.
ENDPOINTS = [
    ("/api/clientes/",      "en uso"),
    ("/api/facturas/",      "en uso"),
    ("/api/tickets/",       "en uso"),
    ("/api/zonas/",         "en uso (catalogo de zonas)"),
    ("/api/gastos/",        "verificado: existe, vacio"),
    ("/api/plan-internet/", "sin explorar"),
    ("/api/staff/",         "sin explorar"),
    ("/api/routers/",       "candidato: 'router' es filtro valido en clientes"),
    ("/api/sectoriales/",   "candidato"),
    ("/api/servicios/",     "candidato"),
    ("/api/pagos/",         "candidato"),
    ("/api/cajas/",         "candidato"),
    ("/api/mapas/",         "candidato"),
]

# El detalle de un recurso expone metodos que la lista no: el DELETE de cliente
# vive ahi, no en /api/clientes/. Se prueban aparte porque necesitan un ID REAL:
# con uno inventado la API devuelve 404 y el endpoint parece no existir.
DETALLES = [
    ("/api/clientes/", "id_servicio"),
    ("/api/tickets/",  "id_ticket"),
]

# Campos que NUNCA deben entrar a una lista blanca, en ninguna entidad.
# Se marcan aqui para que salten a la vista al disenar el catalogo.
PELIGROSOS = ("password", "clave", "coordenada", "gps", "token", "secret")


def metodos(ruta: str) -> str:
    """
    Que se puede HACER en el endpoint, no solo que devuelve.

    Un sondeo por GET marca como inexistente cualquier endpoint de solo
    escritura. OPTIONS devuelve la cabecera 'Allow' y evita ese punto ciego.

    Fue asi como se descubrio que /api/tickets/ acepta POST (se pueden crear
    tickets) y que /api/clientes/{id}/ acepta DELETE — una capacidad
    destructiva viviendo en la misma clave que usa el asistente.
    """
    try:
        r = requests.options(BASE + ruta, headers=HEADERS, timeout=20)
        return r.headers.get("Allow", "—") if r.status_code < 400 else "—"
    except requests.RequestException:
        return "—"


def sondear(ruta: str) -> dict:
    """Una llamada, limit=1. Devuelve que se pudo averiguar del endpoint."""
    try:
        r = requests.get(BASE + ruta, headers=HEADERS,
                         params={"limit": 1}, timeout=25)
    except requests.RequestException as e:
        return {"estado": "red", "detalle": str(e)[:60]}

    if r.status_code == 404:
        return {"estado": "no existe"}
    if r.status_code in (401, 403):
        return {"estado": "sin permiso", "detalle": f"HTTP {r.status_code}"}
    if r.status_code != 200:
        return {"estado": f"HTTP {r.status_code}", "detalle": r.text[:60]}

    try:
        payload = r.json()
    except ValueError:
        return {"estado": "no es JSON"}

    if isinstance(payload, dict) and "count" in payload:
        filas = payload.get("results") or []
        return {"estado": "ok", "n": payload["count"],
                "campos": sorted(filas[0].keys()) if filas else []}
    if isinstance(payload, list):
        return {"estado": "ok", "n": len(payload), "sin_paginado": True,
                "campos": sorted(payload[0].keys())
                          if payload and isinstance(payload[0], dict) else []}
    if isinstance(payload, dict):
        return {"estado": "ok", "n": "?", "objeto": True,
                "campos": sorted(payload.keys())}
    return {"estado": "forma inesperada"}


def main(ver_campos: bool) -> None:
    print(f"Sondeando {BASE}  ({len(ENDPOINTS)} endpoints)\n")
    print(f"  {'endpoint':<24} {'estado':<10} {'registros':>10}  {'metodos':<32} nota")
    print("  " + "-" * 100)

    hallazgos, escrituras = [], []
    for ruta, nota in ENDPOINTS:
        r = sondear(ruta)
        n = r.get("n", "—")
        marca = r["estado"]
        if marca == "ok" and n == 0:
            marca = "vacio"
        allow = metodos(ruta) if marca not in ("no existe", "red") else "—"
        if any(m in allow for m in ("POST", "PUT", "PATCH", "DELETE")):
            escrituras.append((ruta, allow))
        print(f"  {ruta:<24} {marca:<10} {str(n):>10}  {allow:<32} {nota}")
        if r["estado"] == "ok":
            hallazgos.append((ruta, r))

    # --- detalle de recurso, con un ID real tomado de la propia lista ---
    for ruta, campo_id in DETALLES:
        try:
            r = requests.get(BASE + ruta, headers=HEADERS,
                             params={"limit": 1}, timeout=25)
            filas = r.json().get("results") or [] if r.status_code == 200 else []
        except (requests.RequestException, ValueError):
            filas = []
        if not filas or campo_id not in filas[0]:
            continue
        detalle = f"{ruta}{filas[0][campo_id]}/"
        allow = metodos(detalle)
        etiqueta = f"{ruta}{{id}}/"
        if any(m in allow for m in ("POST", "PUT", "PATCH", "DELETE")):
            escrituras.append((etiqueta, allow))
        print(f"  {etiqueta:<24} {'detalle':<10} {'—':>10}  {allow:<32} "
              f"metodos del recurso individual")

    if escrituras:
        print("\n" + "=" * 80)
        print("  ENDPOINTS QUE ACEPTAN ESCRITURA")
        print("=" * 80)
        print("  Toda herramienta que use uno de estos debe declarar")
        print("  'requiere_confirmacion: true'. DELETE no debe exponerse nunca.")
        print()
        print("  AVISO: verificado en produccion que OPTIONS puede listar un")
        print("  metodo que el endpoint NO implementa de verdad. Un DELETE")
        print("  'permitido' aqui devolvio HTTP 500 en la practica; el borrado")
        print("  real vivia en un sub-recurso aparte (/{id}/perfil/). Confirmar")
        print("  SIEMPRE con una llamada real antes de dar un metodo por bueno.\n")
        for ruta, allow in escrituras:
            aviso = "   <-- DESTRUCTIVO (verificar con llamada real)" if "DELETE" in allow else ""
            print(f"  {ruta:<26} {allow}{aviso}")

    # --- campos, y sobre todo los que no deben exponerse ---
    if ver_campos:
        print("\n" + "=" * 80)
        print("  CAMPOS POR ENDPOINT")
        print("=" * 80)
        for ruta, r in hallazgos:
            campos = r.get("campos") or []
            if not campos:
                print(f"\n  {ruta}  (sin registros, no se pueden leer campos)")
                continue
            print(f"\n  {ruta}  ({len(campos)} campos)")
            for i in range(0, len(campos), 4):
                print("      " + "  ".join(f"{c:<22}" for c in campos[i:i + 4]))

    # Este bloque importa mas que el resto: son los campos que jamas deben
    # entrar a una lista blanca. Se listan aparte para que no pasen inadvertidos
    # entre los otros cincuenta.
    print("\n" + "=" * 80)
    print("  CAMPOS SENSIBLES DETECTADOS  —  nunca en una lista blanca")
    print("=" * 80)
    hubo = False
    for ruta, r in hallazgos:
        malos = [c for c in (r.get("campos") or [])
                 if any(p in c.lower() for p in PELIGROSOS)]
        if malos:
            hubo = True
            print(f"\n  {ruta}")
            for c in malos:
                print(f"      {c}")
    if not hubo:
        print("  (ninguno en los endpoints con datos)")

    print("\n" + "=" * 80)
    print("  SIGUIENTE PASO")
    print("=" * 80)
    print("""
  Este sondeo DESCUBRE endpoints; no verifica filtros. Para cada endpoint que
  vaya a entrar al catalogo hay que probar sus filtros con el metodo del valor
  imposible:

      total sin filtro           = N
      total con ?campo=999999999 = N  ->  IGNORADO, no entra al catalogo
      total con ?campo=999999999 = 0  ->  RESPETADO, verificar con valor real

  Ver .claude/skills/wisphub-api/SKILL.md
""")


if __name__ == "__main__":
    main("--campos" in sys.argv)
