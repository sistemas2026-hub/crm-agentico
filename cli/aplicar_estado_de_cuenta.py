# -*- coding: utf-8 -*-
"""
Aplica a la BASE solo lo del estado de cuenta (07/11/2026), sin cargar el YAML entero.

    py -3.13 cli/aplicar_estado_de_cuenta.py rapilink              dice que haria, no escribe
    py -3.13 cli/aplicar_estado_de_cuenta.py rapilink --aplicar    escribe

POR QUE NO cargar_config.py: cargar el YAML entero pisaria lo que la base tiene y el
repo no (la encuesta de cierre, encendida con 'solo_a'). Esto toca cuatro cosas y nada mas:

  1. agrega la herramienta 'consultar_mi_cuenta' (si no esta);
  2. se la da a 'facturacion_cliente' (puede_consultar);
  3. cambia su lista blanca: ve 'consultar_mi_cuenta' y YA NO el 'saldo' de la ficha;
  4. corrige tres frases de su prompt. Si alguna ya no esta tal cual en la base (alguien
     la edito desde /agentes), NO escribe nada y lo dice: se corrige a mano.

ORDEN: primero el push (el codigo nuevo conoce los campos), despues esto. El esquema
rechaza campos desconocidos: aplicarlo antes deja al motor viejo con una config que su
propio esquema no acepta.
Despues: py -3.13 cli/diferencias_config.py rapilink  y  cli/evaluar.py rapilink --humo --base
"""
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ROL = "facturacion_cliente"
HERRAMIENTA = "consultar_mi_cuenta"
LISTA_BLANCA_FICHA = ["estado", "estado_facturas", "fecha_corte", "plan_internet"]

FRASES = [
    ("saldo concreto que debe y desde cuando figura cortado. Es lo que\nnecesita para resolverlo.",
     "monto que debe (el de consultar_mi_cuenta) y desde cuando figura\ncortado. Es lo que necesita para resolverlo."),
    ("Lo que resuelves: saldo actual, si tiene facturas pendientes, y la\nfecha de corte. Una factura PENDIENTE no corta el servicio por si",
     "Lo que resuelves: cuanto debe, si tiene facturas pendientes, y la\nfecha de corte.\n\n"
     "CUANTO DEBE sale SIEMPRE de consultar_mi_cuenta (monto_pendiente,\n"
     "facturas_pendientes, facturas_vencidas): la suma ya viene hecha, no la\n"
     "calcules. NO existe un \"saldo\" de la ficha que puedas decir: no lo\n"
     "tienes, y un 0.00 inventado le dice a quien debe que no debe nada. Si\n"
     "consultar_mi_cuenta devuelve disponible=false, NO pudiste calcular el\n"
     "monto: dile que no lo pudiste confirmar ahora y que un colaborador\n"
     "sigue el caso (derivar_a_area), sin dar una cifra ni decir que no\n"
     "debe nada. Si devuelve completo=false, el monto es lo que hay en la\n"
     "primera pagina: dilo como \"al menos\".\n\n"
     "Una factura PENDIENTE no corta el servicio por si"),
    # 07/11/2026: una sola factura con saldo anterior -> su total ya lo incluye.
    ('primera pagina: dilo como "al menos".',
     'primera pagina: dilo como "al menos". Si devuelve\n'
     'incluye_saldo_anterior=true, ese monto ya suma lo que arrastraba de\n'
     'facturas anteriores: dilo asi ("incluye saldo anterior") y no lo\n'
     'separes ni lo sumes otra vez.'),
    # 07/11/2026: el link de pago de la empresa, si lo cargo en Configuracion -> Pagos.
    ('separes ni lo sumes otra vez.',
     'separes ni lo sumes otra vez. Si devuelve link_de_pago, ofrecelo para\n'
     'que pague: ese link, tal cual. Si no llega, no digas que existe uno ni\n'
     'inventes otro.'),
    # 07/11/2026: otros medios de pago (punto fisico con convenio), de Configuracion -> Pagos.
    ('inventes otro.',
     'inventes otro. Si devuelve otros_medios_de_pago\n'
     '(puntos fisicos, bancos), es una lista de textos "Nombre: como pagar":\n'
     'ofrecelos tal cual, sin cambiar ni inventar ningun numero. Si no llega,\n'
     'no digas que existen otros medios.'),
]


def semilla(tenant):
    doc = yaml.safe_load((RAIZ / "tenants" / f"{tenant}.config.yaml").read_text(encoding="utf-8"))
    herr = next(h for h in doc["herramientas"] if h["nombre"] == HERRAMIENTA)
    rol = doc["roles"][ROL]
    return herr, rol["campos_permitidos"][HERRAMIENTA]


def mutar(doc, herr, campos_cuenta, avisos):
    if any(h.get("nombre") == HERRAMIENTA for h in doc.get("herramientas", [])):
        avisos.append("la herramienta ya estaba: no se agrega de nuevo")
        # Lo unico de ella que se actualiza: su 'cuenta' (de que variable sale el
        # link y de los otros medios de pago). Nada mas de la herramienta se toca.
        for h in doc["herramientas"]:
            if h.get("nombre") == HERRAMIENTA:
                h["cuenta"] = dict(herr["cuenta"])
        avisos.append("herramienta: 'cuenta' al dia")
    else:
        doc.setdefault("herramientas", []).append(herr)
        avisos.append("herramienta agregada")
    rol = doc["roles"][ROL]
    if HERRAMIENTA not in rol["puede_consultar"]:
        rol["puede_consultar"].append(HERRAMIENTA)
        avisos.append("agregada a puede_consultar")
    cp = rol.setdefault("campos_permitidos", {})
    cp["consultar_mi_servicio"] = list(LISTA_BLANCA_FICHA)
    cp[HERRAMIENTA] = list(campos_cuenta)
    avisos.append("lista blanca: ficha sin 'saldo' + consultar_mi_cuenta")
    texto = rol.get("descripcion") or ""
    for i, (viejo, nuevo) in enumerate(FRASES):
        # Una frase posterior EXTIENDE a las anteriores (se inserta dentro de su
        # texto), asi que si ya esta la ultima, las de antes tambien lo estan.
        if any(n in texto for _, n in FRASES[i:]):
            avisos.append("frase del prompt: ya estaba corregida")
        elif viejo in texto:
            texto = texto.replace(viejo, nuevo, 1)
            avisos.append("frase del prompt: corregida")
        else:
            raise SystemExit("NO SE ESCRIBIO NADA: una frase del prompt de "
                             f"'{ROL}' ya no esta tal cual en la base:\n  {viejo[:70]}...\n"
                             "Alguien la edito desde /agentes. Corregirla a mano.")
    rol["descripcion"] = texto


def main():
    tenant = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    if not tenant:
        raise SystemExit(__doc__)
    herr, campos = semilla(tenant)
    if "--aplicar" not in sys.argv:
        print(f"[solo lectura] aplicaria a '{tenant}': herramienta {HERRAMIENTA} + permiso + "
              f"lista blanca de {ROL} (sin 'saldo' de la ficha) + las frases del prompt.\n"
              "Para escribir: agregar --aplicar (DESPUES del push).")
        return
    from nucleo.config import editor
    avisos = []
    editor._editar(tenant, lambda doc: mutar(doc, herr, campos, avisos))
    print("aplicado:")
    for a in avisos:
        print("  -", a)


if __name__ == "__main__":
    main()
