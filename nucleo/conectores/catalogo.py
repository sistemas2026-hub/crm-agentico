# -*- coding: utf-8 -*-
"""
================================================================================
 CONECTORES  --  conectar un sistema conocido eligiendolo de una lista
================================================================================

El problema
-----------
Dar de alta un ISP nuevo que usa WispHub obliga hoy a redescubrir la API: cual
filtro funciona, cual la API acepta y despues IGNORA en silencio devolviendo el
universo entero, que campos trae cada registro y cuales no puede ver un area.

Eso ya se hizo. Las 29 herramientas de WispHub que corren en produccion tienen
cada 'filtros_verificados' comprobado con el metodo del valor imposible, y
'filtros_ignorados_por_api' documenta los que mienten. Semanas de sondeo.

Un conector es ese trabajo, empaquetado. La empresa nueva elige de una lista en
vez de describir una API, y recibe lo que ya se verifico.

Que viaja y que no
------------------
VIAJA lo que es del SISTEMA y no cambia entre empresas: endpoint, filtros
verificados, filtros que la API ignora, veredictos, mapeos, precondiciones. Y
las LISTAS BLANCAS de campos, que son la parte sensible -- el registro de
cliente de WispHub trae 54 campos, cuatro de ellos contraseñas, y decidir que
ve cada area costo pensar. Un conector sin listas blancas entregaria acceso sin
limites.

NO VIAJA lo que es de la EMPRESA: la URL base (dos ISP con el mismo proveedor
pueden tener subdominios distintos), la credencial, y los nombres de sus roles.

Las areas, y por que no roles
-----------------------------
Un conector no puede saber como se llaman los roles del tenant nuevo. Declara
AREAS genericas ('soporte', 'facturacion') y quien lo aplica las mapea a sus
roles. Esa decision es de seguridad -- define quien ve datos de clientes -- y
por eso la toma una persona, no el conector.

Aplicar NO es irreversible pero SI es serio
-------------------------------------------
Escribe herramientas en el catalogo real del tenant. Se valida contra el mismo
esquema que todo lo demas y se rechaza entero si algo no cierra: nunca queda
un catalogo a medias. Y no pisa: una herramienta cuyo nombre ya existe se
informa y se saltea, en vez de reemplazar algo que quiza alguien afino a mano.
================================================================================
"""

from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "conectores"


class ErrorConector(ValueError):
    pass


def listar() -> list[dict]:
    """Los conectores disponibles, sin sus herramientas.

    Sin el detalle a proposito: una lista para elegir no necesita 29
    definiciones completas, y mandarlas convierte una pantalla de seleccion en
    una descarga de 40 KB.
    """
    if not CARPETA.is_dir():
        return []
    salida = []
    for ruta in sorted(CARPETA.glob("*.yaml")):
        try:
            doc = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
        except Exception as fallo:      # noqa: BLE001
            print(f"[conectores] {ruta.name} no se pudo leer: {fallo!r}")
            continue
        salida.append({
            "id": doc.get("id") or ruta.stem,
            "nombre": doc.get("nombre") or ruta.stem,
            "descripcion": doc.get("descripcion", ""),
            "n_herramientas": len(doc.get("herramientas") or []),
            "areas": list((doc.get("areas") or {}).keys()),
            "variables": doc.get("variables") or [],
            "secretos": doc.get("secretos") or [],
        })
    return salida


def leer(id_conector: str) -> dict:
    ruta = CARPETA / f"{id_conector}.yaml"
    # Se compara el nombre resuelto: '../../etc/passwd' como id no puede salir
    # de la carpeta de conectores.
    if not ruta.is_file() or ruta.parent.resolve() != CARPETA.resolve():
        raise ErrorConector(f"No existe el conector '{id_conector}'.")
    return yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}


def preparar(id_conector: str, mapa_areas: dict[str, str],
             config_actual) -> dict:
    """
    Traduce el conector a lo que hay que escribir, SIN escribir nada.

    Separado de aplicar() para que la pantalla pueda mostrar exactamente que va
    a pasar antes de que pase: cuantas herramientas entran, cuales se saltean
    por nombre repetido, y que campos gana cada rol.

    'mapa_areas' va del area del conector al rol del tenant:
        {"soporte": "mi_soporte", "facturacion": "cobranzas"}
    Un area sin mapear se ignora entera -- sus herramientas no entran. Es
    deliberado: es mejor conectar la mitad a proposito que asignarle datos de
    cliente a un rol que nadie eligio.
    """
    doc = leer(id_conector)
    roles_tenant = set((config_actual.roles or {}).keys())
    desconocidos = [r for r in mapa_areas.values() if r not in roles_tenant]
    if desconocidos:
        raise ErrorConector(
            f"Estos roles no existen en el tenant: {', '.join(sorted(desconocidos))}. "
            f"Creralos primero, o corregi el mapeo.")

    existentes = {h.nombre for h in (config_actual.herramientas or [])}
    nuevas, salteadas, campos_por_rol = [], [], {}

    for h in (doc.get("herramientas") or []):
        areas = [a for a in (h.get("areas") or []) if a in mapa_areas]
        if not areas:
            continue                    # ningun area mapeada: no entra
        if h["nombre"] in existentes:
            salteadas.append(h["nombre"])
            continue

        herramienta = {k: v for k, v in h.items()
                       if k not in ("areas", "campos_por_area")}
        herramienta["roles_permitidos"] = sorted({mapa_areas[a] for a in areas})
        nuevas.append(herramienta)

        # Las listas blancas se acumulan por ROL: dos areas distintas pueden
        # mapear al mismo rol, y ahi el rol tiene que ver la union de los dos
        # -- no el ultimo que se proceso.
        for area in areas:
            campos = (h.get("campos_por_area") or {}).get(area)
            if campos:
                rol = mapa_areas[area]
                previos = campos_por_rol.setdefault(rol, {}).get(h["nombre"], [])
                campos_por_rol[rol][h["nombre"]] = sorted(set(previos) | set(campos))

    faltan_secretos = [s["nombre"] for s in (doc.get("secretos") or [])]
    return {
        "conector": doc.get("nombre") or id_conector,
        "nuevas": nuevas,
        "salteadas": salteadas,
        "campos_por_rol": campos_por_rol,
        "variables": doc.get("variables") or [],
        "secretos": faltan_secretos,
    }


def _mutar_aplicar(doc: dict, plan: dict) -> None:
    """Escribe herramientas y listas blancas. Todo o nada -- lo garantiza _editar."""
    doc.setdefault("herramientas", []).extend(plan["nuevas"])
    for rol, por_herramienta in plan["campos_por_rol"].items():
        r = doc["roles"][rol]
        r.setdefault("puede_consultar", [])
        r.setdefault("campos_permitidos", {})
        for nombre, campos in por_herramienta.items():
            if nombre not in r["puede_consultar"]:
                r["puede_consultar"].append(nombre)
            r["campos_permitidos"][nombre] = campos
    # Las herramientas sin lista blanca igual tienen que quedar en el catalogo
    # del rol, o el modelo no las ve. El filtro de campos es fail-closed y se
    # encarga del resto.
    for h in plan["nuevas"]:
        for rol in h["roles_permitidos"]:
            pc = doc["roles"][rol].setdefault("puede_consultar", [])
            if h["nombre"] not in pc:
                pc.append(h["nombre"])


def aplicar(tenant: str, id_conector: str, mapa_areas: dict[str, str]) -> dict:
    """Escribe el conector en el catalogo del tenant. Devuelve el plan aplicado."""
    from nucleo.config import editor, fuente

    plan = preparar(id_conector, mapa_areas, fuente.cargar(tenant))
    if not plan["nuevas"]:
        raise ErrorConector(
            "No hay nada que agregar: todas las herramientas de este conector "
            "ya existen en el catalogo, o ningun area quedo mapeada.")
    editor._editar(tenant, lambda d: _mutar_aplicar(d, plan))
    return plan
