# -*- coding: utf-8 -*-
"""
Aplica a la BASE solo la cuenta de colaborador (07/11/2026), sin cargar el YAML entero.

    py -3.13 cli/aplicar_cuenta_de_colaborador.py rapilink              dice que haria, no escribe
    py -3.13 cli/aplicar_cuenta_de_colaborador.py rapilink --aplicar    escribe

POR QUE NO cargar_config.py: cargar el YAML entero pisaria lo que la base tiene y el repo
no (la encuesta de cierre, encendida con 'solo_a'). Esto toca cuatro cosas y nada mas:

  1. agrega la herramienta 'consultar_cuenta_de_cliente' (o la deja como la declara el repo);
  2. se la da a 'facturacion' y 'soporte' (puede_consultar) con su lista blanca de campos;
  3. quita 'saldo' de las fichas de cliente (consultar_cliente y consultar_cliente_por_cedula)
     de soporte, facturacion y supervisor_noc: vale siempre 0.00 y se leia como "no debe";
  4. cambia el prompt de 'facturacion' para que sepa de donde sale lo que se debe. Si ya no
     es el texto de antes (alguien lo edito desde /agentes), NO escribe nada y lo dice.

ORDEN OBLIGATORIO: primero el push y que el motor termine de desplegar, DESPUES esto. A
diferencia de otras cargas, aca el motor viejo NO acepta la config: 'cuenta_de_colaborador'
es un campo nuevo del esquema y el esquema rechaza campos desconocidos. Aplicarlo antes
deja al motor viejo con una config que su propio esquema no acepta.
Despues: py -3.13 cli/diferencias_config.py rapilink  y  cli/evaluar.py rapilink --humo --base
"""
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

HERRAMIENTA = "consultar_cuenta_de_cliente"
ROLES_CON_LA_HERRAMIENTA = ("facturacion", "soporte")
ROLES_CON_FICHA = ("soporte", "facturacion", "supervisor_noc")
FICHAS = ("consultar_cliente", "consultar_cliente_por_cedula")
ROL_CON_PROMPT = "facturacion"
PROMPT_DE_ANTES = "Revisa facturas, saldos y registra pagos."


def semilla(tenant):
    doc = yaml.safe_load((RAIZ / "tenants" / f"{tenant}.config.yaml").read_text(encoding="utf-8"))
    herr = next(h for h in doc["herramientas"] if h["nombre"] == HERRAMIENTA)
    campos = {r: doc["roles"][r]["campos_permitidos"][HERRAMIENTA] for r in ROLES_CON_LA_HERRAMIENTA}
    prompt = doc["roles"][ROL_CON_PROMPT]["descripcion"]
    return herr, campos, prompt


def mutar(doc, herr, campos, prompt, avisos):
    # El prompt primero: si no es lo esperado, se aborta ANTES de cambiar nada.
    rol_p = doc["roles"][ROL_CON_PROMPT]
    actual = (rol_p.get("descripcion") or "").strip()
    if HERRAMIENTA in actual:
        avisos.append("prompt de facturacion: ya estaba")
        cambiar_prompt = False
    elif actual == PROMPT_DE_ANTES:
        cambiar_prompt = True
    else:
        raise SystemExit("NO SE ESCRIBIO NADA: el prompt de 'facturacion' ya no es el de antes:\n"
                         f"  {actual[:90]!r}\nAlguien lo edito desde /agentes. Corregirlo a mano.")

    herramientas = doc.setdefault("herramientas", [])
    for i, h in enumerate(herramientas):
        if h.get("nombre") == HERRAMIENTA:
            herramientas[i] = dict(herr)
            avisos.append("herramienta: ya estaba, queda como la declara el repo")
            break
    else:
        herramientas.append(dict(herr))
        avisos.append("herramienta agregada")

    for rol_n in ROLES_CON_LA_HERRAMIENTA:
        rol = doc["roles"][rol_n]
        if HERRAMIENTA not in rol["puede_consultar"]:
            rol["puede_consultar"].append(HERRAMIENTA)
            avisos.append(f"{rol_n}: puede consultarla")
        rol.setdefault("campos_permitidos", {})[HERRAMIENTA] = list(campos[rol_n])

    quitados = []
    for rol_n in ROLES_CON_FICHA:
        cp = (doc["roles"].get(rol_n) or {}).get("campos_permitidos") or {}
        for ficha in FICHAS:
            lista = cp.get(ficha)
            if isinstance(lista, list) and "saldo" in lista:
                lista[:] = [c for c in lista if c != "saldo"]
                quitados.append(f"{rol_n}.{ficha}")
    avisos.append(f"fichas sin 'saldo': {quitados}" if quitados else "fichas: ya sin 'saldo'")

    if cambiar_prompt:
        rol_p["descripcion"] = prompt
        avisos.append("prompt de facturacion: actualizado")


def main():
    tenant = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    if not tenant:
        raise SystemExit(__doc__)
    herr, campos, prompt = semilla(tenant)
    if "--aplicar" not in sys.argv:
        print(f"[solo lectura] aplicaria a '{tenant}': herramienta {HERRAMIENTA} + permiso y lista "
              f"blanca en {list(ROLES_CON_LA_HERRAMIENTA)} + 'saldo' fuera de las fichas de "
              f"{list(ROLES_CON_FICHA)} + prompt de {ROL_CON_PROMPT}.\n"
              "Para escribir: agregar --aplicar (DESPUES del push y del despliegue del motor).")
        return
    from nucleo.config import editor
    avisos = []
    editor._editar(tenant, lambda doc: mutar(doc, herr, campos, prompt, avisos))
    print("aplicado:")
    for a in avisos:
        print("  -", a)


if __name__ == "__main__":
    main()
