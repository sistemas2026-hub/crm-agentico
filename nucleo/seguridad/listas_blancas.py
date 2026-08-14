# -*- coding: utf-8 -*-
"""
================================================================================
 LISTAS BLANCAS DE CAMPOS  -  filtro fail-closed
================================================================================

Puerto de filtrar_campos() (soporte_wisphub.py), parametrizado por
'Rol.campos_permitidos' (nucleo/config/schema.py) en vez del diccionario
AREAS hardcodeado del prototipo original. Misma logica, misma garantia.

IMPORTANTE (fail-closed): si el rol no tiene lista blanca para esa
herramienta, NO se deja pasar nada. Vale tanto para una herramienta nueva sin
configurar como para un rol que no deberia estar consultando eso.
================================================================================
"""

from __future__ import annotations


def _compilar_permitidos(permitidos: set[str]) -> tuple[set[str], dict[str, set[str]]]:
    """Separa la lista blanca en campos de primer nivel y campos anidados."""
    top, anidados = set(), {}
    for campo in permitidos:
        if "." in campo:
            padre, hijo = campo.split(".", 1)
            anidados.setdefault(padre, set()).add(hijo)
        else:
            top.add(campo)
    return top, anidados


def _solo_permitidos(permitidos: set[str], dato) -> dict:
    """
    Aplica la lista blanca a un dict suelto.

    Soporta notacion con punto ('servicio.id_servicio') para filtrar DENTRO
    de un objeto anidado: dejar pasar el objeto entero porque su nombre esta
    en la lista blanca seria una fuga (el 'servicio' de un ticket trae la IP
    del cliente y el router con sus credenciales). Un objeto anidado solo se
    entrega completo si se lo nombra sin punto, y eso debe reservarse a
    objetos inofensivos (plan_internet, zona).
    """
    if not isinstance(dato, dict):
        return {}
    top, anidados = _compilar_permitidos(permitidos)
    salida = {k: v for k, v in dato.items() if k in top}
    for padre, hijos in anidados.items():
        sub = dato.get(padre)
        if isinstance(sub, dict):
            salida[padre] = {k: v for k, v in sub.items() if k in hijos}
    return salida


def _empaquetar_lista(permitidos: set[str], filas: list, total: int) -> dict:
    """
    Normaliza una lista a {total, resultados}, filtrando cada fila.

    'total' es el count REAL que reporta el API, no el numero de filas
    traidas. Si se trajo menos que el total (paginacion), se avisa de forma
    EXPLICITA: un conteo hecho sobre una pagina incompleta es una respuesta
    incorrecta que no se nota.
    """
    filtradas = [_solo_permitidos(permitidos, f) for f in filas]
    paquete = {"total": total, "resultados": filtradas}
    if total > len(filtradas):
        paquete["aviso"] = (
            f"Resultado PARCIAL: se muestran {len(filtradas)} de {total} "
            f"registros. No cuentes sobre esta lista; el total real es {total}.")
    return paquete


def filtrar_campos(rol, nombre_herramienta: str, datos):
    """
    Deja solo los campos que ESE ROL puede ver de ESA herramienta.

    'rol' es una instancia de nucleo.config.schema.Rol. Maneja las tres
    formas en que puede responder una API tipo REST:
      - dict suelto            -> {"campo": valor, ...}
      - lista                  -> [ {...}, {...} ]
      - paginado estilo DRF    -> {"count": N, "results": [ {...} ]}
    Las dos ultimas se normalizan a {"total": N, "resultados": [...]}.
    """
    permitidos = rol.campos_permitidos.get(nombre_herramienta)
    if permitidos is None:
        return {"error": f"El rol no tiene permitido consultar "
                         f"'{nombre_herramienta}'. Resultado descartado."}
    permitidos = set(permitidos)

    # Los errores propios del codigo pasan tal cual (no traen datos del cliente).
    if isinstance(datos, dict) and "error" in datos:
        return {"error": datos["error"]}

    if isinstance(datos, list):
        return _empaquetar_lista(permitidos, datos, len(datos))

    if isinstance(datos, dict):
        if isinstance(datos.get("results"), list):
            return _empaquetar_lista(permitidos, datos["results"],
                                     datos.get("count", len(datos["results"])))
        return _solo_permitidos(permitidos, datos)

    # Valor suelto (str/int/float/bool/None): pasa cuando la herramienta usa
    # 'extraer_de' apuntando a un campo que en la API real es un valor
    # simple, no un objeto (ej. consultar_estado_ont, extraer_de: onu_status
    # -- la API responde {"onu_status": "Online", ...} y para aca ya llega
    # solo el string "Online"). La lista blanca en ese caso declara UN solo
    # nombre -- el campo que ese valor representa -- y se empaqueta de
    # vuelta en un dict con esa clave, para que el modelo sepa que dato es.
    # Con mas de un nombre no hay forma de saber cual le corresponde: se
    # rechaza en vez de adivinar.
    if datos is None or isinstance(datos, (str, int, float, bool)):
        if len(permitidos) == 1:
            return {next(iter(permitidos)): datos}
        return {"error": "Formato de respuesta no reconocido. Resultado descartado."}

    return {"error": "Formato de respuesta no reconocido. Resultado descartado."}
