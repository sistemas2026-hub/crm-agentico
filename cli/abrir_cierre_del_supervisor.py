# -*- coding: utf-8 -*-
"""
================================================================================
 ABRIR EL CIERRE DEL SUPERVISOR EN LA CONFIG DE UN TENANT  --  31/10/2026
================================================================================

QUE HACE
--------
Pone en la herramienta de cierre de tickets los DOS campos que dejan al
Supervisor cerrar el ticket de una orden que su revision dio por buena:

    aprobacion_humana_salvo: [cierre_de_orden_revisada]
    nivel_autonomia: 3

POR QUE UN SCRIPT Y NO 'cli/cargar_config.py'
---------------------------------------------
Cargar el YAML entero pisa lo que la base tenga y el archivo no traiga --un
agente creado desde la interfaz, una variable editada en vivo--. Esto toca
DOS claves de UNA herramienta y deja el resto como esta (CLAUDE.md §8).

EL CODIGO VA PRIMERO, Y NO ES UN CONSEJO
----------------------------------------
'aprobacion_humana_salvo' es un campo NUEVO. Los modelos usan extra="forbid":
si se escribe esta config contra una base cuyo motor todavia no conoce el
campo, ese motor rechaza su propia configuracion entera y el asistente deja de
atender. Por eso se corre DESPUES de desplegar, y desde el entorno desplegado.

    py -3.13 cli/abrir_cierre_del_supervisor.py rapilink              (simulacro)
    py -3.13 cli/abrir_cierre_del_supervisor.py rapilink --aplicar

SIN --aplicar NO ESCRIBE NADA: muestra que encontro y que dejaria.

OJO CON EL DIFF (deuda D7): 'editor._editar' reescribe los defaults ausentes,
asi que la version nueva puede diferir en muchas hojas que nadie toco. Lo que
importa es que las dos claves de abajo queden puestas.
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config import editor                                  # noqa: E402
from nucleo.seguridad import frontera                             # noqa: E402

#: La herramienta se busca por su CAPACIDAD, no por su nombre: cada empresa la
#: llama como quiera. Es el mismo criterio que usa el motor para encontrarla
#: ('cierre_por_validacion._herramienta_de_cierre').
CAPACIDAD = "cierra_ticket_operativo"
EXENCION = frontera.CIERRE_DE_ORDEN_REVISADA
NIVEL = 3


class NoSePudo(Exception):
    pass


def _la_del_cierre(doc: dict) -> dict:
    """La unica herramienta con la capacidad. Si hay 0 o mas de 1, no se elige."""
    candidatas = [h for h in (doc.get("herramientas") or [])
                  if isinstance(h, dict) and h.get(CAPACIDAD)]
    if len(candidatas) != 1:
        raise NoSePudo(
            f"se esperaba UNA herramienta con '{CAPACIDAD}' y hay "
            f"{len(candidatas)}: {[h.get('nombre') for h in candidatas]}. "
            f"No se elige por adivinanza.")
    return candidatas[0]


def _mutar(doc: dict) -> None:
    herr = _la_del_cierre(doc)
    if not herr.get("aprobacion_humana"):
        #  Sin la marca, eximir no hace nada y deja escrito que si (el schema
        #  tambien lo rechaza). Mejor fallar aca con el motivo.
        raise NoSePudo(
            f"'{herr.get('nombre')}' no declara 'aprobacion_humana': no hay "
            f"nada que eximir. Revisar por que, en vez de forzarlo.")
    salvo = list(herr.get("aprobacion_humana_salvo") or [])
    if EXENCION not in salvo:
        salvo.append(EXENCION)
    herr["aprobacion_humana_salvo"] = salvo
    herr["nivel_autonomia"] = NIVEL


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--aplicar"]
    aplicar = "--aplicar" in sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        return 2
    tenant = args[0]

    from nucleo.config import fuente

    try:
        vigente = fuente.cargar(tenant)
    except Exception as e:                                        # noqa: BLE001
        print(f"[FALLA] no se pudo leer la config vigente de '{tenant}': "
              f"{type(e).__name__}")
        return 1

    actual = next((h for h in vigente.herramientas
                   if getattr(h, CAPACIDAD, False)), None)
    if actual is None:
        print(f"[FALLA] '{tenant}' no declara ninguna herramienta con "
              f"'{CAPACIDAD}'.")
        return 1

    print(f"  tenant      : {tenant}")
    print(f"  herramienta : {actual.nombre}")
    print(f"  ANTES  aprobacion_humana       = {actual.aprobacion_humana}")
    print(f"         aprobacion_humana_salvo = "
          f"{list(getattr(actual, 'aprobacion_humana_salvo', []) or [])}")
    print(f"         nivel_autonomia         = {actual.nivel_autonomia}")
    print(f"  DESPUES aprobacion_humana_salvo = ['{EXENCION}']")
    print(f"          nivel_autonomia         = {NIVEL}")

    if not aplicar:
        print("\n  SIMULACRO: no se escribio nada. Con --aplicar se escribe.")
        return 0

    try:
        nueva = editor._editar(tenant, _mutar)
    except NoSePudo as e:
        print(f"\n[FALLA] {e}")
        return 1
    except Exception as e:                                        # noqa: BLE001
        print(f"\n[FALLA] el editor no escribio: {type(e).__name__}: {e}")
        return 1

    quedo = next(h for h in nueva.herramientas if getattr(h, CAPACIDAD, False))
    ok = (EXENCION in (quedo.aprobacion_humana_salvo or [])
          and quedo.nivel_autonomia == NIVEL
          and quedo.aprobacion_humana is True)
    #  SE AFIRMA SOBRE LO QUE QUEDO, releido del objeto validado -- no sobre
    #  que la llamada no haya levantado.
    print(f"\n  quedo: salvo={list(quedo.aprobacion_humana_salvo or [])} "
          f"nivel={quedo.nivel_autonomia} marca={quedo.aprobacion_humana}")
    print("  [OK] escrito." if ok else "  [FALLA] no quedo como se pedia.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
