# -*- coding: utf-8 -*-
"""Validador determinista de esquemas JSON y datos técnicos de campo."""

from __future__ import annotations

import re
from typing import Any
from django.core.exceptions import ValidationError

TIPOS_PERMITIDOS = {
    "texto",
    "entero",
    "decimal",
    "booleano",
    "seleccion",
    "fecha",
    "foto",
    "documento",
}

REGLAS_PERMITIDAS = {
    "required",
    "min",
    "max",
    "regex",
    "options",
}


def validar_esquema_plantilla(esquema: dict) -> None:
    """Valida que una plantilla de trabajo respete el vocabulario estricto de schema_version=1."""
    if not isinstance(esquema, dict):
        raise ValidationError("El esquema debe ser un objeto JSON.")

    campos = esquema.get("campos", [])
    if not isinstance(campos, list):
        raise ValidationError("El atributo 'campos' debe ser una lista.")

    evidencias = esquema.get("evidencias", [])
    if not isinstance(evidencias, list):
        raise ValidationError("El atributo 'evidencias' debe ser una lista.")

    ids_vistos = set()
    for campo in campos:
        cid = campo.get("id")
        if not cid or not isinstance(cid, str):
            raise ValidationError("Todo campo debe tener un 'id' de tipo string.")
        if cid in ids_vistos:
            raise ValidationError(f"El campo con id '{cid}' está duplicado.")
        ids_vistos.add(cid)

        tipo = campo.get("tipo")
        if tipo not in TIPOS_PERMITIDOS:
            raise ValidationError(
                f"Campo '{cid}' usa tipo no soportado '{tipo}'. Permitidos: {list(TIPOS_PERMITIDOS)}"
            )

        reglas = campo.get("reglas", {})
        if not isinstance(reglas, dict):
            raise ValidationError(f"Las reglas de '{cid}' deben ser un objeto JSON.")
        for r in reglas:
            if r not in REGLAS_PERMITIDAS:
                raise ValidationError(
                    f"Regla '{r}' en campo '{cid}' no reconocida. Permitidas: {list(REGLAS_PERMITIDAS)}"
                )

    ids_evidencias = set()
    for ev in evidencias:
        eid = ev.get("id")
        if not eid or not isinstance(eid, str):
            raise ValidationError("Toda evidencia debe tener un 'id' de tipo string.")
        if eid in ids_evidencias:
            raise ValidationError(f"La evidencia con id '{eid}' está duplicada.")
        ids_evidencias.add(eid)

        tipo = ev.get("tipo", "foto")
        if tipo not in ("foto", "documento"):
            raise ValidationError(
                f"Evidencia '{eid}' tiene tipo no permitido '{tipo}'. Permitidos: ['foto', 'documento']"
            )


def validar_campos_tecnicos(esquema: dict, nuevos_valores: dict) -> tuple[dict, dict]:
    """
    Valida un conjunto de valores parciales o totales contra los campos del esquema.
    Retorna (valores_validados, errores_por_campo).
    """
    campos_map = {c["id"]: c for c in esquema.get("campos", [])}
    valores_limpios = {}
    errores = {}

    for clave, valor in nuevos_valores.items():
        if clave not in campos_map:
            errores[clave] = f"El campo '{clave}' no existe en la plantilla de este trabajo."
            continue

        definicion = campos_map[clave]
        tipo = definicion.get("tipo")
        reglas = definicion.get("reglas", {})

        # Validación de tipo
        try:
            val_limpio = _castear_tipo(valor, tipo)
        except (ValueError, TypeError) as e:
            errores[clave] = f"Valor no corresponde al tipo {tipo}: {e}"
            continue

        # Validación de reglas
        error_regla = _validar_reglas(val_limpio, tipo, reglas)
        if error_regla:
            errores[clave] = error_regla
            continue

        valores_limpios[clave] = val_limpio

    return valores_limpios, errores


def verificar_checklist_completo(orden) -> list[dict]:
    """
    Comprueba que todos los campos requeridos y todas las evidencias obligatorias
    estén presentes y válidas antes de permitir completar_campo.
    """
    esquema = orden.tipo_trabajo_version.esquema
    errores = []

    # 1. Verificar campos requeridos
    datos_actuales = orden.datos or {}
    for campo in esquema.get("campos", []):
        cid = campo["id"]
        es_obligatorio = campo.get("obligatorio", False) or campo.get("reglas", {}).get("required", False)
        if es_obligatorio:
            val = datos_actuales.get(cid)
            if val is None or (isinstance(val, str) and not val.strip()):
                errores.append({
                    "codigo": "CAMPO_FALTANTE",
                    "campo_id": cid,
                    "mensaje": f"El campo técnico '{campo.get('titulo', cid)}' es obligatorio.",
                })

    # 2. Verificar evidencias requeridas
    #
    # Dos listas, no una, y esa es toda la diferencia entre una devolucion con
    # dientes y una decorativa.
    #
    # Antes esto miraba si EXISTIA evidencia recibida del requisito, sobre toda
    # la orden. En una segunda vuelta la evidencia de la primera sigue ahi y
    # sigue en 'recibido', asi que '/completar/' habria pasado de inmediato sin
    # que el tecnico subiera nada: el supervisor devolvia el trabajo y el
    # sistema lo daba por corregido solo.
    #
    # Ahora los requisitos que el supervisor devolvio exigen evidencia DE LA
    # VUELTA ACTUAL. Los que no devolvio conservan como valida la que ya tenian
    # -- que es la razon de haber elegido vuelta dirigida y no vuelta completa:
    # nadie repite ocho fotos porque una estaba mal.
    recibidas = orden.evidencias.filter(
        estado_archivo__in=["recibido", "verificado"])
    de_cualquier_vuelta = set(recibidas.values_list("requisito_id", flat=True))
    de_esta_vuelta = set(
        recibidas.filter(vuelta__gte=orden.vuelta).values_list("requisito_id", flat=True))

    a_corregir = requisitos_a_corregir(orden)

    for ev in esquema.get("evidencias", []):
        eid = ev["id"]
        if not ev.get("obligatorio", False) and eid not in a_corregir:
            continue

        if eid in a_corregir:
            if eid not in de_esta_vuelta:
                errores.append({
                    "codigo": "CORRECCION_PENDIENTE",
                    "requisito_id": eid,
                    "mensaje": (
                        f"'{ev.get('titulo', eid)}' fue devuelto para corregir: "
                        f"hace falta evidencia nueva, de esta vuelta. La "
                        f"anterior queda en el historial pero no alcanza."),
                })
            continue

        if eid not in de_cualquier_vuelta:
            errores.append({
                "codigo": "EVIDENCIA_FALTANTE",
                "requisito_id": eid,
                "mensaje": f"Falta la evidencia requerida: '{ev.get('titulo', eid)}'.",
            })

    return errores


def requisitos_a_corregir(orden) -> set[str]:
    """
    Que requisitos pidio rehacer el supervisor para la vuelta que corre.

    Sale de la bitacora, no de una columna. 'EventoTrabajo' es append-only y
    esta ordenado por fecha, asi que el ultimo evento de devolucion es una
    fuente determinista -- y ademas conserva lo que se pidio en CADA vuelta,
    que una columna habria ido sobrescribiendo. Con el historial completo se
    puede responder despues cual requisito se devuelve mas seguido.

    En la vuelta 1 no hay devolucion todavia: devuelve vacio y el checklist se
    comporta como siempre.
    """
    if orden.vuelta <= 1:
        return set()
    evento = (
        orden.eventos.filter(tipo="correccion_requerida",
                             datos__vuelta_nueva=orden.vuelta)
        .order_by("-created_at")
        .first()
    )
    if evento is None:
        return set()
    return {str(r) for r in (evento.datos or {}).get("requisitos_a_corregir", [])}


def _castear_tipo(valor: Any, tipo: str) -> Any:
    if valor is None:
        return None
    if tipo == "texto":
        return str(valor).strip()
    if tipo == "entero":
        return int(valor)
    if tipo == "decimal":
        return float(valor)
    if tipo == "booleano":
        if isinstance(valor, bool):
            return valor
        if str(valor).lower() in ("true", "1", "si", "yes"):
            return True
        if str(valor).lower() in ("false", "0", "no"):
            return False
        raise ValueError("No es un valor booleano válido.")
    return valor


def _validar_reglas(valor: Any, tipo: str, reglas: dict) -> str | None:
    if valor is None:
        if reglas.get("required"):
            return "Este campo es requerido."
        return None

    if "min" in reglas:
        limite_min = reglas["min"]
        if tipo in ("entero", "decimal") and valor < limite_min:
            return f"El valor no puede ser menor a {limite_min}."
        if tipo == "texto" and len(str(valor)) < limite_min:
            return f"Debe tener al menos {limite_min} caracteres."

    if "max" in reglas:
        limite_max = reglas["max"]
        if tipo in ("entero", "decimal") and valor > limite_max:
            return f"El valor no puede ser mayor a {limite_max}."
        if tipo == "texto" and len(str(valor)) > limite_max:
            return f"No puede superar {limite_max} caracteres."

    if "regex" in reglas and tipo == "texto":
        patron = reglas["regex"]
        if not re.search(patron, str(valor)):
            return f"El valor no cumple el patrón requerido ({patron})."

    if "options" in reglas:
        opciones = reglas["options"]
        if valor not in opciones:
            return f"Opción inválida. Opciones permitidas: {opciones}."

    return None
