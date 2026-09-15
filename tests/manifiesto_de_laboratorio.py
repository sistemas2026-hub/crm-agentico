# -*- coding: utf-8 -*-
"""
================================================================================
 EL MANIFIESTO DE LABORATORIO  --  el de las suites rapidas, no el de produccion
================================================================================

Hay dos manifiestos y no hay que confundirlos:

  supabase/ledger/manifiesto_adopcion.json   el ARTEFACTO OFICIAL. Describe
        PRODUCCION: PostgreSQL 17.6, pgcrypto en 'extensions', ACL con MAINTAIN.
        Se certifica sobre la imagen exacta de produccion; ver la suite del
        artefacto oficial.

  el que genera este modulo                  el de LABORATORIO. Se genera contra
        la referencia PostgreSQL 16 que cada suite construye, y vive solo en su
        directorio temporal. Sirve para ejercitar el MECANISMO: adopcion,
        baseline, evidencia, carreras, huecos, checksums y la compuerta de
        huella.

Por que estan separados. La compuerta de huella es correcta: un manifiesto de
PostgreSQL 17 NO debe ser aceptado por un servidor 16, porque comparar
definiciones de catalogo entre versiones mayores no dice nada confiable. Antes
las suites usaban el manifiesto versionado como fixture y eso solo funcionaba
mientras el artefacto oficial describiera un PG16. Debilitar la compuerta para
que siguiera funcionando habria sido romper justamente lo que protege.

Se usa el generador REAL (cli/manifiesto_adopcion.py) de la copia del repo que
la suite ya arma: nada de un segundo generador de pruebas, nada de JSON escrito
a mano. El manifiesto se escribe DENTRO de esa copia, que es donde el migrador
lo busca.
================================================================================
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Los dos de P2 se aplican DESPUES de la adopcion: no son parte del conjunto que
# se adopta. Ver supabase/202609141200_* y 202609141300_*.
P2 = ("202609141200_scheduler_persistente.sql", "202609141300_scheduler_funciones.sql")


def archivos_de_adopcion(raiz: Path) -> set[str]:
    """Los SQL que se adoptan: todos los de supabase/ menos los dos de P2."""
    return {p.name for p in (raiz / "supabase").glob("*.sql")} - set(P2)


def ruta(copia: Path) -> Path:
    return copia / "supabase" / "ledger" / "manifiesto_adopcion.json"


def generar(copia: Path, entorno: dict, descripcion: str = "") -> dict:
    """
    Genera el manifiesto de la referencia que describe 'entorno' (DBNAME) y lo deja
    en 'copia', pisando el artefacto oficial que se copio del repo. Devuelve el JSON.
    """
    destino = ruta(copia)
    r = subprocess.run(
        [sys.executable, str(copia / "cli" / "manifiesto_adopcion.py"), "--generar",
         "--salida", str(destino), "--descripcion",
         descripcion or "manifiesto de laboratorio: referencia efimera de esta suite, NO el artefacto de produccion"],
        capture_output=True, text=True, env=entorno, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"no se pudo generar el manifiesto de laboratorio: "
                           f"{((r.stdout or '') + (r.stderr or ''))[-500:]}")
    return json.loads(destino.read_bytes().decode("utf-8"))


def replicar(origen: Path, *copias: Path) -> None:
    """Deja los MISMOS bytes del manifiesto de laboratorio en otras copias del repo."""
    crudo = ruta(origen).read_bytes()
    for c in copias:
        ruta(c).write_bytes(crudo)


def automaticas(manifiesto: dict) -> set[str]:
    return {a for a, e in manifiesto["migraciones"].items()
            if e["estado"] == "verificable_automaticamente"}


def identidad(copia: Path) -> tuple[str, str]:
    """(sha256, git_blob) de los bytes canonicos, como los calcula el motor."""
    canon = ruta(copia).read_bytes().replace(b"\r\n", b"\n")
    return (hashlib.sha256(canon).hexdigest(),
            hashlib.sha1(b"blob %d\0" % len(canon) + canon).hexdigest())
