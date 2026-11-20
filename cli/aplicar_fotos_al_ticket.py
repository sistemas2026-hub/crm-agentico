# -*- coding: utf-8 -*-
"""
Aplica a la BASE solo lo que deja viajar las fotos al ticket del ISP (07/11/2026).

    py -3.13 cli/aplicar_fotos_al_ticket.py rapilink              dice que haria, no escribe
    py -3.13 cli/aplicar_fotos_al_ticket.py rapilink --aplicar    escribe

QUE TOCA, y nada mas: dos claves de UNA herramienta,
`responder_ticket_operativo`.

    argumentos_archivo:        [archivo]
    argumentos_sobrescribibles: ... + archivo

Sin esas dos, el codigo nuevo corre igual y NO MANDA NINGUNA FOTO: el
reporte del tecnico llega al ticket como antes y nada falla. Es el caso que
CLAUDE.md §6 llama «codigo construido no es codigo que corre», y por eso esto
existe.

POR QUE NO `cargar_config.py`. Cargar el YAML entero pisaria lo que la base
tiene y el repo no. Medido con `diferencias_config.py` el 07/11/2026: son
DOCE cosas, entre ellas las 132 localidades, los 50 precios de planes, los
100 de la parrilla de canales, `umbral_rx_dbm`, el `LINK_DE_PAGO` y la
encuesta de cierre encendida con `solo_a`. Todo eso se escribio desde la
interfaz, que es donde debe escribirse; el YAML es semilla, no fuente de
verdad (CLAUDE.md §3.2).

MISMO PATRON que `cli/aplicar_estado_de_cuenta.py`, del mismo dia: se reusa
en vez de inventar una segunda forma de hacer lo mismo.

SI YA ESTA, NO ESCRIBE. Y si la herramienta no esta en la base, no la crea:
eso seria otro cambio y se veria como este.

ORDEN: primero el push --el motor viejo no conoce estos campos y su esquema
los rechazaria-- y despues esto.
Despues: py -3.13 cli/diferencias_config.py rapilink
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

HERRAMIENTA = "responder_ticket_operativo"
CAMPO = "archivo"


def mutar(doc, avisos):
    herramientas = doc.get("herramientas") or []
    herr = next((h for h in herramientas
                 if isinstance(h, dict) and h.get("nombre") == HERRAMIENTA), None)
    if herr is None:
        raise SystemExit(
            f"NO SE ESCRIBIO NADA: la base no tiene '{HERRAMIENTA}'. "
            "Crearla es otro cambio, y tiene que verse como tal.")

    #  SIN `multipart` NO SE TOCA NADA. El validador rechaza
    #  'argumentos_archivo' sin el, asi que escribirlo dejaria la config sin
    #  poder cargarse -- y eso se descubre en el proximo arranque del motor,
    #  no aca.
    if not herr.get("multipart"):
        raise SystemExit(
            f"NO SE ESCRIBIO NADA: '{HERRAMIENTA}' no declara 'multipart' en "
            "la base. Un archivo no cabe en un cuerpo JSON.")

    archivos = list(herr.get("argumentos_archivo") or [])
    if CAMPO in archivos:
        avisos.append("argumentos_archivo: ya estaba")
    else:
        archivos.append(CAMPO)
        herr["argumentos_archivo"] = archivos
        avisos.append(f"argumentos_archivo: + {CAMPO}")

    #  LAS DOS JUNTAS O NINGUNA. El validador exige que todo
    #  'argumentos_archivo' este tambien en 'argumentos_sobrescribibles': si
    #  no, el backend manda las fotos y se descartan EN SILENCIO antes de
    #  llegar al proveedor.
    sobre = list(herr.get("argumentos_sobrescribibles") or [])
    if CAMPO in sobre:
        avisos.append("argumentos_sobrescribibles: ya estaba")
    else:
        sobre.append(CAMPO)
        herr["argumentos_sobrescribibles"] = sobre
        avisos.append(f"argumentos_sobrescribibles: + {CAMPO}")


def main():
    tenant = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    if not tenant:
        raise SystemExit(__doc__)
    if "--aplicar" not in sys.argv:
        print(f"[solo lectura] aplicaria a '{tenant}': "
              f"'{HERRAMIENTA}' pasa a declarar '{CAMPO}' en "
              f"argumentos_archivo y en argumentos_sobrescribibles.\n"
              "Nada mas de la config se toca.\n"
              "Para escribir: agregar --aplicar (DESPUES del push).")
        return
    from nucleo.config import editor
    avisos = []
    editor._editar(tenant, lambda doc: mutar(doc, avisos))
    print("aplicado:")
    for a in avisos:
        print("  -", a)


if __name__ == "__main__":
    main()
