"""El nombre de una credencial se valida ANTES de la base (26/11/2026).

La base solo acepta la forma de una variable de entorno (`^[A-Z][A-Z0-9_]*$`)
y respondia con un error de restriccion que la pantalla mostraba como «no se
pudo guardar». Ahora: 400 con lo que esta mal, sin repetir el nombre (si ahi
se escribio la clave, no vuelve a la pantalla), y sin tocar la base.

    MOTOR_SERVICE_TOKEN= python tests/test_secreto_nombre.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["MOTOR_SERVICE_TOKEN"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import api                                     # noqa: E402
from nucleo.seguridad import secretos                              # noqa: E402

_fallos: list[str] = []


def afirmar(cond: bool, que: str) -> None:
    print(("  OK   " if cond else "  FALLA ") + que)
    if not cond:
        _fallos.append(que)


cliente = api.app.test_client()
tocadas = []
viejo = secretos._cifrador
secretos._cifrador = lambda: (_ for _ in ()).throw(AssertionError("no debia llegar a cifrar"))
try:
    for nombre in ("wisphub_web_usuario", "WISPHUB WEB", "desarrollo@rapilink-sas", "1CLAVE",
                   "WISPHUB-WEB", "CLAVÉ", "miClaveSecreta123"):
        r = cliente.post("/secretos", json={"tenant": "empresa-de-prueba", "nombre": nombre, "valor": "x" * 10})
        cuerpo = r.get_json() or {}
        afirmar(r.status_code == 400 and "MAYÚSCULAS" in cuerpo.get("error", "")
                and nombre not in cuerpo.get("error", ""),
                f"{nombre!r}: 400 que dice qué está mal, sin repetir el nombre ({r.status_code})")
finally:
    secretos._cifrador = viejo

try:
    secretos.guardar("empresa-de-prueba", "WISPHUB_WEB_USUARIO", "")
except secretos.ErrorSecreto as e:
    afirmar("vacio" in str(e), "un nombre bueno con el valor vacío sigue diciendo que falta el valor")

print()
if _fallos:
    print(f"FALLARON {len(_fallos)}")
    sys.exit(1)
print("TODO OK")
