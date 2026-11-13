# -*- coding: utf-8 -*-
"""
Aplica a la BASE solo la consulta de medios de pago (07/11/2026), sin cargar el YAML entero.

    py -3.13 cli/aplicar_medios_de_pago_consulta.py rapilink              dice que haria, no escribe
    py -3.13 cli/aplicar_medios_de_pago_consulta.py rapilink --aplicar    escribe

POR QUE NO cargar_config.py: cargar el YAML entero pisaria lo que la base tiene y el repo
no (la encuesta de cierre, encendida con 'solo_a'). Esto toca cuatro cosas y nada mas:

  1. agrega la herramienta 'consultar_medios_de_pago' (o la deja como la declara el repo);
  2. se la da a 'facturacion_cliente' (puede_consultar) con su lista blanca de campos;
  3. agrega al prompt de 'facturacion_cliente' cuando usarla, y a su 'atiende' (lo que lee el
     router) que tambien atiende "donde y como pagar". Si la frase de la que cuelga ya
     no esta (alguien edito el prompt desde /agentes), NO escribe nada y lo dice.

ORDEN OBLIGATORIO: primero el push y que el motor termine de desplegar, DESPUES esto. El
motor viejo NO acepta la config: 'entrega_medios_de_pago' es un campo nuevo del esquema y
el esquema rechaza campos desconocidos.
Despues: py -3.13 cli/diferencias_config.py rapilink  y  cli/evaluar.py rapilink --humo --base
"""
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

HERRAMIENTA = "consultar_medios_de_pago"
ROL = "facturacion_cliente"

# La frase de la que cuelga el agregado, y lo que se le agrega. Mismo texto que el YAML.
ANCLA = "no digas que existen otros medios."
# Lo que el ROUTER lee para decidir a quien mandar una conversacion (campo 'atiende'): sin esto,
# quien llega solo preguntando donde pagar no necesariamente llega a este agente.
ATIENDE_ANCLA = "promesas de pago."
ATIENDE_NUEVO = "promesas de pago, donde y como pagar (puntos de pago, convenios)."

AGREGADO = (
    "no digas que existen otros medios. Cuando le digas cuanto debe, ofrece\n"
    "tambien esos medios. Si el cliente ya verificado pregunta DONDE o COMO\n"
    "puede pagar -- aunque no deba nada --, llama consultar_medios_de_pago y\n"
    "dale lo que devuelva, tal cual. Si devuelve hay_medios_de_pago=false, dile\n"
    "que no los tienes a mano y que un colaborador se los comparte\n"
    "(derivar_a_area), sin inventar ninguno."
)


def semilla(tenant):
    doc = yaml.safe_load((RAIZ / "tenants" / f"{tenant}.config.yaml").read_text(encoding="utf-8"))
    herr = next(h for h in doc["herramientas"] if h["nombre"] == HERRAMIENTA)
    campos = doc["roles"][ROL]["campos_permitidos"][HERRAMIENTA]
    return herr, campos


def mutar(doc, herr, campos, avisos):
    rol = doc["roles"][ROL]
    texto = rol.get("descripcion") or ""
    # El prompt primero: si no se puede, se aborta ANTES de cambiar nada.
    if HERRAMIENTA in texto:
        cambiar_prompt = False
        avisos.append("prompt: ya estaba")
    elif ANCLA in texto:
        cambiar_prompt = True
    else:
        raise SystemExit("NO SE ESCRIBIO NADA: el prompt de "
                         f"'{ROL}' ya no tiene la frase de la que cuelga este agregado:\n  {ANCLA}\n"
                         "Alguien lo edito desde /agentes. Agregarlo a mano.")

    atiende = rol.get("atiende") or ""
    if "donde y como pagar" in atiende:
        cambiar_atiende = False
        avisos.append("atiende: ya estaba")
    elif ATIENDE_ANCLA in atiende:
        cambiar_atiende = True
    else:
        raise SystemExit("NO SE ESCRIBIO NADA: el 'atiende' de "
                         f"'{ROL}' ya no tiene la frase de la que cuelga este agregado:\n  {ATIENDE_ANCLA}\n"
                         "Alguien lo edito desde /agentes/flujo. Agregarlo a mano.")

    herramientas = doc.setdefault("herramientas", [])
    for i, h in enumerate(herramientas):
        if h.get("nombre") == HERRAMIENTA:
            herramientas[i] = dict(herr)
            avisos.append("herramienta: ya estaba, queda como la declara el repo")
            break
    else:
        herramientas.append(dict(herr))
        avisos.append("herramienta agregada")

    if HERRAMIENTA not in rol["puede_consultar"]:
        rol["puede_consultar"].append(HERRAMIENTA)
        avisos.append("agregada a puede_consultar")
    rol.setdefault("campos_permitidos", {})[HERRAMIENTA] = list(campos)
    avisos.append("lista blanca al dia")

    if cambiar_atiende:
        rol["atiende"] = atiende.replace(ATIENDE_ANCLA, ATIENDE_NUEVO, 1)
        avisos.append("atiende: agregado")
    if cambiar_prompt:
        rol["descripcion"] = texto.replace(ANCLA, AGREGADO, 1)
        avisos.append("prompt: agregado")


def main():
    tenant = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    if not tenant:
        raise SystemExit(__doc__)
    herr, campos = semilla(tenant)
    if "--aplicar" not in sys.argv:
        print(f"[solo lectura] aplicaria a '{tenant}': herramienta {HERRAMIENTA} + permiso y lista "
              f"blanca en '{ROL}' + el agregado al prompt.\n"
              "Para escribir: agregar --aplicar (DESPUES del push y del despliegue del motor).")
        return
    from nucleo.config import editor
    avisos = []
    editor._editar(tenant, lambda doc: mutar(doc, herr, campos, avisos))
    print("aplicado:")
    for a in avisos:
        print("  -", a)


if __name__ == "__main__":
    main()
