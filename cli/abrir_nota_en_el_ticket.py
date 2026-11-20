# -*- coding: utf-8 -*-
"""
================================================================================
 PONE EN LA BASE LA EXENCION DE LAS NOTAS DE CAMPO  --  06/11/2026
================================================================================
Hermano de `cli/abrir_cierre_del_supervisor.py`, para la otra exencion.

POR QUE HACE FALTA UN SCRIPT, Y NO 'cargar_config.py'
-----------------------------------------------------
El motor lee `asistente.tenant_config`, NO el archivo del repositorio
(CLAUDE.md §3.2). Declarar la exencion en `tenants/<slug>.config.yaml` y no
ponerla en la base deja el camino construido y sin correr: la frontera
contesta APROBACION_HUMANA_REQUERIDA, la ruta del motor devuelve 409 y el CRM
solo deja una linea en el log. Sin error, sin alerta, sin que nadie se entere
-- el patron que §6 llama "codigo construido no es codigo que corre".

`cargar_config.py` reemplaza la configuracion entera con la del archivo, y en
produccion la base tiene cosas que el archivo no trae (agentes creados desde
la interfaz, por ejemplo). Esto toca SOLO las dos claves que hacen falta.

QUE CAMBIA, Y QUE NO
--------------------
Sobre la unica herramienta con la capacidad `responde_ticket_operativo`:

    aprobacion_humana_salvo : + 'nota_de_campo_en_el_ticket'
    nivel_autonomia         : 3

NO le quita `aprobacion_humana`. Quitarla la abriria tambien para la
conversacion y para cualquier servicio por /interno/herramienta, con el texto
que al modelo se le ocurra. La exencion abre UN camino, nombrado, donde el
texto lo arma el codigo desde la plantilla de la orden.

El nivel 3 no es un detalle: hasta que la exencion existio, `aprobacion_humana`
frenaba antes y el techo daba igual. Ahora que puede salir, el techo es una de
las cuatro compuertas que quedan, y una empresa en nivel 2 escribiria sola en
el sistema de un tercero (auditoria de frontera, H3 del 06/11 -- la misma
leccion que H4 del 31/10, que no se habia aplicado a esta herramienta).

COMO SE USA

    py -3.13 cli/abrir_nota_en_el_ticket.py rapilink              (simulacro)
    py -3.13 cli/abrir_nota_en_el_ticket.py rapilink --aplicar

SIN --aplicar NO ESCRIBE NADA: muestra que encontro y que dejaria.

DESPUES DE APLICAR, la tabla de §6 pide dos cosas:

    py -3.13 cli/diferencias_config.py rapilink
    py -3.13 cli/evaluar.py rapilink --humo --base

"el repo lo declara y la base no" es la direccion que rompe; "solo la base lo
tiene" es normal, porque la base es la fuente de verdad.

OJO CON EL DIFF (deuda D7): 'editor._editar' reescribe los defaults ausentes,
asi que el diff de una edicion minima no es minimo. Es conocido y no lo
arregla este script.
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config import editor                                  # noqa: E402
from nucleo.seguridad import frontera                             # noqa: E402

#: Por CAPACIDAD y no por nombre: cada empresa llama a sus herramientas como
#: quiera, y es el mismo criterio con el que el motor la encuentra
#: ('nota_en_el_ticket._herramienta_que_anota').
CAPACIDAD = "responde_ticket_operativo"
EXENCION = frontera.NOTA_DE_CAMPO_EN_EL_TICKET
NIVEL = 3


class NoSePudo(Exception):
    pass


def _la_que_anota(doc: dict) -> dict:
    """La unica herramienta con la capacidad. Si hay 0 o mas de 1, no se elige."""
    candidatas = [h for h in (doc.get("herramientas") or [])
                  if isinstance(h, dict) and h.get(CAPACIDAD)]
    if len(candidatas) != 1:
        raise NoSePudo(
            f"se esperaba UNA herramienta con '{CAPACIDAD}' y hay "
            f"{len(candidatas)}: {[h.get('nombre') for h in candidatas]}. "
            f"No se elige por adivinanza.")
    return candidatas[0]


def _la_del_cierre(doc: dict) -> dict | None:
    for h in doc.get("herramientas") or []:
        if isinstance(h, dict) and h.get("cierra_ticket_operativo"):
            return h
    return None


def _mutar(doc: dict) -> None:
    herr = _la_que_anota(doc)
    if not herr.get("aprobacion_humana"):
        #  Sin la marca, eximir no hace nada y deja escrito que si (el schema
        #  tambien lo rechaza). Mejor fallar aca con el motivo.
        raise NoSePudo(
            f"'{herr.get('nombre')}' no declara 'aprobacion_humana': no hay "
            f"nada que eximir. Revisar por que, en vez de forzarlo.")

    #  LA MISMA COMPROBACION QUE HACE EL MOTOR EN CALIENTE (H7). Si en la base
    #  esta herramienta le pide al proveedor lo mismo que la de cierre, no es
    #  una nota: cerraria tickets por la exencion equivocada. Se frena ACA,
    #  antes de escribir, porque abrirla y que el motor la rechace despues es
    #  dejar una config que miente.
    cierre = _la_del_cierre(doc)
    fijos_nota = dict(herr.get("argumentos_fijos") or {})
    fijos_cierre = dict((cierre or {}).get("argumentos_fijos") or {})
    if cierre is not None and fijos_nota and fijos_nota == fijos_cierre:
        raise NoSePudo(
            f"'{herr.get('nombre')}' le manda al proveedor lo mismo que "
            f"'{cierre.get('nombre')}' ({fijos_nota}): abrir la exencion ahi "
            f"dejaria cerrar tickets por la puerta de las notas.")

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
    print(f"         argumentos_fijos        = "
          f"{dict(actual.argumentos_fijos or {})}")
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
    #  SE AFIRMA SOBRE LO QUE QUEDO, releido del objeto validado -- no sobre
    #  que la llamada no haya levantado. Y se pregunta a la frontera, que es
    #  quien decide de verdad: que la clave este escrita no prueba que exima.
    exime = frontera.exime_la_aprobacion(quedo, EXENCION)
    ok = (EXENCION in (quedo.aprobacion_humana_salvo or [])
          and quedo.nivel_autonomia == NIVEL
          and quedo.aprobacion_humana is True
          and exime)
    print(f"\n  quedo: salvo={list(quedo.aprobacion_humana_salvo or [])} "
          f"nivel={quedo.nivel_autonomia} marca={quedo.aprobacion_humana}")
    print(f"  la frontera la exime: {exime}")
    print("  [OK] escrito." if ok else "  [FALLA] no quedo como se pedia.")
    if ok:
        print("\n  AHORA, segun CLAUDE.md §6:")
        print(f"    py -3.13 cli/diferencias_config.py {tenant}")
        print(f"    py -3.13 cli/evaluar.py {tenant} --humo --base")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
