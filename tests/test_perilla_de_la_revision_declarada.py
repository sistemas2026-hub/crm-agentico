# -*- coding: utf-8 -*-
"""
Una variable que el contenedor no recibe no apaga nada.

    py -3.13 tests/test_perilla_de_la_revision_declarada.py

POR QUE EXISTE  --  22/11/2026
------------------------------
Programacion dejo de recalcular la revision del cierre en cada pedido
(`django-crm/backend/campo/revision_sin_repetir.py`), y ese atajo nacio con su
interruptor: una variable de entorno que lo apaga si alguna vez muestra algo
viejo. La auditoria independiente encontro que el interruptor no se podia
accionar: el backend de produccion recibe una lista EXPLICITA de
`environment:`, sin `env_file`, y la variable no estaba en ella. Ponerla en
Dokploy no llegaba a ningun proceso; apagar el atajo exigia editar el compose
y desplegar -- justo lo que un interruptor existe para evitar.

Es la falla que CLAUDE.md §6 llama «codigo construido no es codigo que corre»,
y ya paso una vez con `CAMPO_NOTA_AL_ISP` (PRD §8.31).

Lo que se prueba:

  1. El nombre de la variable se lee DEL CODIGO, no se repite aca: si alguien
     la renombra, esta guarda sigue mirando la que el codigo lee.
  2. El servicio `backend` del compose de produccion la declara tomandola de
     afuera (`${VAR:-valor}`), no fija: fija tampoco se podria cambiar sin
     desplegar.
  3. Su valor de fabrica en el compose es el mismo que el del codigo: dos
     valores de fabrica distintos son dos verdades.
"""
import pathlib
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:                                                # noqa: BLE001
    pass

RAIZ = pathlib.Path(__file__).resolve().parent.parent
fallos = []


def revisar(condicion, que, detalle=""):
    print(("  [ok]    " if condicion else "  [FALLA] ") + que
          + (f"  ({detalle})" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


codigo = (RAIZ / "django-crm" / "backend" / "campo"
          / "revision_sin_repetir.py").read_text(encoding="utf-8")
m = re.search(r'^VARIABLE = "([A-Z_]+)"', codigo, re.M)
revisar(m is not None, "el codigo nombra su variable de operacion")
variable = m.group(1) if m else "?"
m = re.search(r"^VIDA_POR_DEFECTO = (\d+)", codigo, re.M)
revisar(m is not None, "y su valor de fabrica")
de_fabrica = m.group(1) if m else "?"

compose = (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8")
backend = compose.split("\n  backend:\n", 1)[1].split("\n  celery-worker:", 1)[0]

declarada = re.search(
    r"^\s+" + re.escape(variable) + r":\s*\$\{" + re.escape(variable)
    + r":-([^}]*)\}", backend, re.M)
revisar(declarada is not None,
        f"el backend de produccion recibe {variable} desde afuera",
        "no esta en su lista de environment, o esta con un valor fijo")
revisar(declarada is not None and declarada.group(1) == de_fabrica,
        f"y su valor de fabrica es el del codigo ({de_fabrica})",
        f"en el compose: {declarada.group(1) if declarada else 'nada'}")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La perilla de la revision llega al contenedor que la lee.")
