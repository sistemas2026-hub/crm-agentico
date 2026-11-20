# -*- coding: utf-8 -*-
"""
Aplica a la BASE solo el horario de atencion (09/11/2026), sin cargar el YAML entero.

    py -3.13 cli/aplicar_horario_de_atencion.py rapilink              dice que haria, no escribe
    py -3.13 cli/aplicar_horario_de_atencion.py rapilink --aplicar    escribe

POR QUE NO cargar_config.py: cargar el YAML entero pisaria lo que la base tiene y el repo
no (la encuesta de cierre, encendida con 'solo_a'). Esto toca cuatro cosas y nada mas:

  1. agrega las herramientas 'leer_calendario_laboral' (http, solo lectura) y
     'consultar_horario_de_atencion' (o las deja como las declara el repo);
  2. se la da a los cuatro roles de cliente (puede_consultar + lista blanca de campos);
  3. en el prompt de 'cliente_final': que el horario se consulta ANTES de contestar, y que
     "dejame confirmar y te digo" solo vale si de verdad se puede confirmar. Si una de las
     dos frases de las que cuelga ya no esta (alguien edito el prompt desde /agentes), NO
     escribe nada y lo dice.

ORDEN OBLIGATORIO: primero el push y que el motor termine de desplegar, DESPUES esto. El
motor viejo NO acepta la config: 'entrega_horario_de_atencion' es un campo nuevo del esquema y
el esquema rechaza campos desconocidos.
Despues: py -3.13 cli/diferencias_config.py rapilink  y  cli/evaluar.py rapilink --humo --base
Y comprobar que la empresa tiene cargado su Horario laboral (Configuracion -> Horario laboral):
sin eso el agente dice que no lo tiene, que es lo honesto.
"""
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

HERRAMIENTAS = ("leer_calendario_laboral", "consultar_horario_de_atencion")
HERRAMIENTA = "consultar_horario_de_atencion"
ROLES = ("cliente_final", "facturacion_cliente", "soporte_tecnico_cliente", "ventas")
ROL_ROUTER = "cliente_final"

# Las dos frases del prompt del router de las que cuelga el agregado, y lo que las reemplaza.
# Mismo texto que el YAML (un bloque '|' sin la sangria).
ANCLA_NO_SE = 'Nunca "no se" -> "dejame confirmar eso y te digo".'
NUEVO_NO_SE = (
    'Nunca "no se" -> "dejame confirmar eso y te digo" SOLO si de verdad puedes\n'
    '  confirmarlo (una herramienta tuya, o pasarlo con derivar_a_area a un\n'
    '  colaborador). Si no hay como, di que no lo tienes y que un colaborador se\n'
    '  lo confirma: nunca prometas volver con una respuesta que no vas a poder dar.')
ANCLA_HORARIOS = "ningun area (horarios, como contactar a la empresa). Si pregunta por"
NUEVO_HORARIOS = (
    "ningun area (el horario de atencion, como contactar a la\n"
    "empresa). Si pregunta hasta que hora atienden, si estan abiertos o cuando\n"
    "abren, llama consultar_horario_de_atencion ANTES de contestar y dile lo que\n"
    "devuelva, tal cual: no hace falta pedirle la cedula, es informacion publica.\n"
    "Si pregunta por")


def semilla(tenant):
    doc = yaml.safe_load((RAIZ / "tenants" / f"{tenant}.config.yaml").read_text(encoding="utf-8"))
    por_nombre = {h["nombre"]: h for h in doc["herramientas"]}
    herramientas = [por_nombre[n] for n in HERRAMIENTAS]
    campos = {r: doc["roles"][r]["campos_permitidos"][HERRAMIENTA] for r in ROLES}
    return herramientas, campos


def mutar(doc, herramientas, campos, avisos):
    router = doc["roles"][ROL_ROUTER]
    texto = router.get("descripcion") or ""
    # El prompt primero: si no se puede, se aborta ANTES de cambiar nada.
    if HERRAMIENTA in texto:
        cambiar_prompt = False
        avisos.append("prompt: ya estaba")
    else:
        faltan = [a for a in (ANCLA_NO_SE, ANCLA_HORARIOS) if a not in texto]
        if faltan:
            raise SystemExit(
                f"NO SE ESCRIBIO NADA: el prompt de '{ROL_ROUTER}' ya no tiene la frase de la "
                "que cuelga este agregado:\n  " + "\n  ".join(faltan) +
                "\nAlguien lo edito desde /agentes. Agregarlo a mano.")
        cambiar_prompt = True

    lista = doc.setdefault("herramientas", [])
    for herr in herramientas:
        for i, h in enumerate(lista):
            if h.get("nombre") == herr["nombre"]:
                lista[i] = dict(herr)
                avisos.append(f"{herr['nombre']}: ya estaba, queda como la declara el repo")
                break
        else:
            lista.append(dict(herr))
            avisos.append(f"{herr['nombre']}: agregada")

    for nombre in ROLES:
        rol = doc["roles"][nombre]
        if HERRAMIENTA not in rol["puede_consultar"]:
            rol["puede_consultar"].append(HERRAMIENTA)
            avisos.append(f"{nombre}: agregada a puede_consultar")
        rol.setdefault("campos_permitidos", {})[HERRAMIENTA] = list(campos[nombre])
    avisos.append("listas blancas al dia")

    if cambiar_prompt:
        router["descripcion"] = (texto.replace(ANCLA_NO_SE, NUEVO_NO_SE, 1)
                                 .replace(ANCLA_HORARIOS, NUEVO_HORARIOS, 1))
        avisos.append("prompt del router: agregado")


def main():
    tenant = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    if not tenant:
        raise SystemExit(__doc__)
    herramientas, campos = semilla(tenant)
    if "--aplicar" not in sys.argv:
        print(f"[solo lectura] aplicaria a '{tenant}': {', '.join(HERRAMIENTAS)} + permiso y lista "
              f"blanca en {', '.join(ROLES)} + el agregado al prompt de '{ROL_ROUTER}'.\n"
              "Para escribir: agregar --aplicar (DESPUES del push y del despliegue del motor).")
        return
    from nucleo.config import editor
    avisos = []
    editor._editar(tenant, lambda doc: mutar(doc, herramientas, campos, avisos))
    print("aplicado:")
    for a in avisos:
        print("  -", a)


if __name__ == "__main__":
    main()
