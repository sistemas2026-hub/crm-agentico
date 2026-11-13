# -*- coding: utf-8 -*-
"""
QUE CAMBIO EN UN AGENTE, VERSION A VERSION  --  13/11/2026.

asistente.tenant_config_historial guarda la config COMPLETA de cada version
(a proposito: un diff obliga a reconstruir sumando pasos). Para la pestaña
"Cambios" de un agente hace falta lo contrario: de doscientas versiones de la
empresa, las pocas en que ESTE agente cambio, dichas en palabras.

Logica pura, sin base: recibe la seccion del rol de cada version (lo que
devuelve persistencia.agentes.versiones_del_rol) y devuelve los cambios. Asi
se prueba sin Postgres.

LO QUE NO DICE: quien hizo el cambio. El historial no lo guarda (solo
'creado_en'), y adivinarlo seria inventar un dato. La pantalla dice "no se
registra" en vez de un nombre.
"""
from __future__ import annotations

import difflib

#  Los campos de un rol en el orden en que se cuentan, con su nombre para una
#  persona. Un campo que no esta aca igual se detecta (ver _otros).
_NOMBRES = {
    "nombre_visible": "Nombre",
    "resumen": "Resumen",
    "descripcion": "Instrucciones (su rol específico)",
    "atiende": "Temas que atiende",
    "orientado_a": "A quién le habla",
    "area": "Área",
    "cargo": "Cargo",
    "exige_verificacion": "Verificar identidad",
    "deriva_verificacion": "Deriva la verificación",
    "nunca_revelar": "Lo que nunca revela",
    "motivos_escalada": "Motivos para pasar a una persona",
    "pausado": "En pausa",
}

#  Tope del diff del prompt que viaja a la pantalla. Un rol de Rapilink tiene
#  ~34.000 caracteres: un cambio grande en uno de esos no se lee en pantalla
#  igual, y mandarlo entero por cada version inflaria la respuesta.
MAX_LINEAS_DIFF = 300


def _texto(v) -> str:
    return v if isinstance(v, str) else ""


def _diff(antes: str, despues: str) -> str:
    lineas = list(difflib.unified_diff(
        antes.splitlines(), despues.splitlines(), "antes", "despues", n=1, lineterm=""))
    if len(lineas) > MAX_LINEAS_DIFF:
        lineas = lineas[:MAX_LINEAS_DIFF] + [f"… ({len(lineas) - MAX_LINEAS_DIFF} líneas más)"]
    return "\n".join(lineas)


def describir(antes: dict | None, despues: dict | None) -> dict | None:
    """
    El cambio de UNA version a la siguiente, o None si el rol quedo igual.

    Devuelve {'resumen': [frases], 'diff_instrucciones': str | None,
    'tipo': 'creado' | 'borrado' | 'editado'}.
    """
    if antes == despues:
        return None
    if not antes:
        return {"tipo": "creado", "resumen": ["Se creó el agente."], "diff_instrucciones": None}
    if not despues:
        return {"tipo": "borrado", "resumen": ["Se borró el agente."], "diff_instrucciones": None}

    frases: list[str] = []
    diff = None

    h_antes = set(antes.get("puede_consultar") or [])
    h_despues = set(despues.get("puede_consultar") or [])
    for h in sorted(h_despues - h_antes):
        frases.append(f"Se agregó la herramienta {h}.")
    for h in sorted(h_antes - h_despues):
        frases.append(f"Se quitó la herramienta {h}.")

    c_antes = antes.get("campos_permitidos") or {}
    c_despues = despues.get("campos_permitidos") or {}
    for h in sorted(set(c_antes) | set(c_despues)):
        #  Solo herramientas que siguen estando: agregar o quitar una ya lo
        #  dijo la frase de arriba, con sus campos incluidos.
        if h not in h_antes or h not in h_despues:
            continue
        a, d = set(c_antes.get(h) or []), set(c_despues.get(h) or [])
        if a != d:
            partes = []
            if d - a:
                partes.append(f"ve {len(d - a)} campo{'s' if len(d - a) != 1 else ''} más")
            if a - d:
                partes.append(f"deja de ver {len(a - d)}")
            frases.append(f"En {h}: " + " y ".join(partes) + ".")

    for clave, nombre in _NOMBRES.items():
        a, d = antes.get(clave), despues.get(clave)
        if a == d or (not a and not d):
            continue
        if clave == "descripcion":
            ta, td = _texto(a), _texto(d)
            frases.append(f"{nombre}: de {len(ta):,} a {len(td):,} caracteres.".replace(",", "."))
            diff = _diff(ta, td)
        elif clave == "pausado":
            frases.append("Se pausó." if d else "Se reanudó.")
        elif isinstance(a, bool) or isinstance(d, bool):
            frases.append(f"{nombre}: {'sí' if d else 'no'}.")
        elif isinstance(a, list) or isinstance(d, list):
            frases.append(f"{nombre}: cambió.")
        else:
            frases.append(f"{nombre}: «{_texto(d) or '—'}».")

    otros = sorted((set(antes) | set(despues)) - set(_NOMBRES)
                   - {"puede_consultar", "campos_permitidos"})
    for clave in otros:
        if antes.get(clave) != despues.get(clave):
            frases.append(f"Cambió «{clave}».")

    return {"tipo": "editado", "resumen": frases or ["Cambió la configuración."],
            "diff_instrucciones": diff}


def historial(versiones: list[dict]) -> list[dict]:
    """
    De la lista de versiones (la mas nueva primero, como la da
    versiones_del_rol) a la lista de CAMBIOS de este rol, la mas nueva primero.

    La version mas vieja de la lista no se compara con nada -- su anterior no
    vino -- asi que no genera entrada: decir "se creo" de un agente que ya
    existia antes del historial seria falso.
    """
    salida = []
    for nueva, vieja in zip(versiones, versiones[1:]):
        cambio = describir(vieja.get("rol"), nueva.get("rol"))
        if cambio is None:
            continue
        creado = nueva.get("creado_en")
        salida.append({
            "version": nueva["version"],
            "creado_en": creado.isoformat() if hasattr(creado, "isoformat") else creado,
            #  Restaurable si en esa version el rol existia: restaurar la que
            #  lo borro no tiene sentido (ver editor.restaurar_rol).
            "restaurable": bool(nueva.get("rol")),
            **cambio,
        })
    return salida
