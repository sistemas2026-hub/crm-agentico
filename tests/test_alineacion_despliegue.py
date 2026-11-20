# -*- coding: utf-8 -*-
"""
La guarda que impide cargar config antes de desplegar el codigo.

Existe desde el incidente del 03/09/2026 (se agrego un campo al esquema, se
cargo la config, el codigo no estaba desplegado, y produccion quedo con una
configuracion que su propio codigo rechazaba -- los modelos usan
extra="forbid", asi que un campo desconocido no se ignora: tumba el archivo
entero).

EL AGUJERO QUE ESTAS PRUEBAS CIERRAN
------------------------------------
La deteccion comparaba contra '@{u}', el upstream de la RAMA ACTUAL. En una
rama de trabajo eso se satisface con un push que no despliega nada. Medido el
22/09/2026: con commits pendientes en 'feature/bandeja-relevo' la guarda
bloqueo; se pusheo esa rama a SU remoto y la guarda paso, con el codigo
todavia fuera de produccion.

Se prueba sobre repositorios git de verdad, creados al vuelo: la pregunta es
que rama mira, y eso no se puede simular con un mock sin probar el mock.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nucleo.config import editor  # noqa: E402

fallos = []


def afirmar(cond, que):
    print(f"  [{'ok' if cond else 'FALLA'}]{'   ' if cond else ' '}{que}")
    if not cond:
        fallos.append(que)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def repo_de_prueba(tmp: Path):
    """Un remoto y un clon, con una rama de despliegue y una de trabajo."""
    remoto = tmp / "remoto.git"
    git(tmp, "init", "--bare", "-b", "despliegue", str(remoto))
    local = tmp / "local"
    git(tmp, "clone", str(remoto), str(local))
    git(local, "config", "user.email", "qa@qa.local")
    git(local, "config", "user.name", "QA")
    (local / "a.txt").write_text("1", encoding="utf-8")
    git(local, "add", "a.txt")
    git(local, "commit", "-m", "base")
    git(local, "push", "-u", "origin", "despliegue")
    return local


def contar(local: Path, rama: str) -> int:
    """commits_sin_empujar() con la raiz y la rama de despliegue de la prueba."""
    ref = editor._ref_de_despliegue(local)
    r = git(local, "rev-list", "--count", f"{ref}..HEAD")
    return int((r.stdout or "0").strip() or 0)


with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    local = repo_de_prueba(tmp)
    previo = os.environ.get("RAMA_DESPLIEGUE")
    os.environ["RAMA_DESPLIEGUE"] = "despliegue"
    try:
        print("\n--- alineado ---")
        afirmar(contar(local, "despliegue") == 0,
                "sin commits nuevos, no hay nada pendiente")

        print("\n--- el agujero que se cerro ---")
        git(local, "checkout", "-b", "trabajo")
        (local / "b.txt").write_text("2", encoding="utf-8")
        git(local, "add", "b.txt")
        git(local, "commit", "-m", "cambio de esquema")
        afirmar(contar(local, "despliegue") == 1,
                "un commit en una rama de trabajo cuenta como pendiente")

        git(local, "push", "-u", "origin", "trabajo")
        afirmar(contar(local, "despliegue") == 1,
                "y SIGUE pendiente despues de empujar esa rama -- que es el agujero: "
                "empujar a otra rama no despliega nada")

        print("\n--- cuando de verdad se despliega ---")
        git(local, "push", "origin", "trabajo:despliegue")
        afirmar(contar(local, "despliegue") == 0,
                "recien al llegar a la rama de despliegue deja de estar pendiente")

        print("\n--- si la rama de despliegue no existe ---")
        os.environ["RAMA_DESPLIEGUE"] = "no-existe-esta-rama"
        afirmar(editor._ref_de_despliegue(local) == "@{u}",
                "se cae a '@{u}' en vez de romper: peor que nada, mejor que no comprobar")
    finally:
        if previo is None:
            os.environ.pop("RAMA_DESPLIEGUE", None)
        else:
            os.environ["RAMA_DESPLIEGUE"] = previo

print("\n" + "=" * 62)
if fallos:
    print(f" {len(fallos)} falla(s).")
    raise SystemExit(1)
print(" Todo en orden.")
