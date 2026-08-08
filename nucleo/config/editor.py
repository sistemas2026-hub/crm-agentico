# -*- coding: utf-8 -*-
"""
================================================================================
 EDITOR DE ROLES  -  crear/editar/borrar agentes sin perder el YAML a mano
================================================================================

`schema.py` valida; este modulo ESCRIBE. Separado a proposito: `cargar_config`
no necesita saber nada de edicion, y este archivo no necesita saber nada de
como se sirve por HTTP (eso vive en canales/api.py).

Alcance deliberado (ver plan aprobado): solo se crean/editan/borran ROLES.
Crear una herramienta nueva -- conectar una API nueva, decidir sus filtros
verificados, su whitelist de campos -- sigue siendo trabajo de codigo. No es
un limite tecnico de este modulo, es que esa superficie es sensible en
seguridad y no encaja en "editar desde una pantalla".

Por que ruamel.yaml y no yaml.safe_dump
----------------------------------------
`tenants/*.yaml` esta profundamente comentado -- notas de verificacion en
vivo, tablas de comparacion de modelos, motivos de cada exclusion. Un
`yaml.safe_dump` (PyYAML plano, lo que ya usa `cargar_config`) los borraria
todos: no es cosmetico, es informacion de produccion. `ruamel.yaml` en modo
round-trip carga y vuelve a guardar preservando comentarios, orden y estilo
de bloques.

Validar antes de escribir
--------------------------
Nunca se toca el archivo en disco directo. Se arma el documento round-trip
en memoria, se vuelca a texto, y ESE texto pasa por el mismo camino que
`cargar_config` (barrido de secretos + `TenantConfig(**yaml.safe_load(...))`).
Solo si valida se escribe, y de forma atomica (archivo temporal + replace)
para que un fallo a mitad de escritura no deje el YAML corrupto. Si no
valida, se devuelven TODOS los problemas juntos y el disco no se toca.
================================================================================
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError
from ruamel.yaml import YAML

from .schema import TenantConfig, _barrer_secretos

_RE_NOMBRE_ROL = re.compile(r"^[a-z][a-z0-9_]{1,29}$")

_yaml_rt = YAML(typ="rt")
_yaml_rt.preserve_quotes = True
_yaml_rt.width = 100
# Mismo estilo que ya usa el archivo a mano: el guion de una lista va
# indentado 2 espacios respecto de su clave padre, no pegado a la izquierda.
_yaml_rt.indent(mapping=2, sequence=4, offset=2)


class ErrorEdicion(ValueError):
    pass


def _cargar_rt(ruta: Path):
    with ruta.open("r", encoding="utf-8") as f:
        return _yaml_rt.load(f)


def _volcar_rt(doc) -> str:
    from io import StringIO
    buf = StringIO()
    _yaml_rt.dump(doc, buf)
    return buf.getvalue()


def _validar_texto(ruta: Path, texto: str) -> TenantConfig:
    """Mismo camino que cargar_config(), pero sobre texto en memoria."""
    crudo = yaml.safe_load(texto) or {}

    secretos = _barrer_secretos(crudo)
    if secretos:
        raise ErrorEdicion(
            f"{ruta.name}: hay valores con pinta de credencial:\n  - "
            + "\n  - ".join(secretos))

    try:
        return TenantConfig(**crudo)
    except ValidationError as e:
        lineas = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                  for err in e.errors()]
        raise ErrorEdicion(
            f"{ruta.name}: {len(lineas)} problema(s) de configuracion:\n  - "
            + "\n  - ".join(lineas)) from None


def _escribir_y_validar(ruta: Path, doc_rt) -> TenantConfig:
    texto = _volcar_rt(doc_rt)
    config = _validar_texto(ruta, texto)  # lanza ErrorEdicion sin tocar disco

    fd, ruta_tmp = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(ruta_tmp, ruta)
    except BaseException:
        if os.path.exists(ruta_tmp):
            os.remove(ruta_tmp)
        raise
    return config


def _validar_nombre_rol(nombre: str) -> None:
    if not _RE_NOMBRE_ROL.match(nombre):
        raise ErrorEdicion(
            f"'{nombre}': el nombre debe ser minuscula, empezar con letra y "
            f"usar solo letras/numeros/guion bajo (2-30 caracteres)")


# =============================================================================
#  CATALOGO  -  lo que la UI necesita para armar el formulario
# =============================================================================

def catalogo_herramientas(config: TenantConfig) -> list[dict]:
    """
    Por herramienta: de que tipo es, si es de verificacion (sin whitelist de
    campos), y que campos ya declaro CUALQUIER rol existente para ella -- no
    hay catalogo de campos de las APIs externas en ningun lado del sistema,
    asi que lo unico confiable para ofrecer como checklist es lo que ya paso
    por un humano que leyo la respuesta real.
    """
    conocidos: dict[str, set[str]] = {}
    for rol in config.roles.values():
        for herr, campos in rol.campos_permitidos.items():
            conocidos.setdefault(herr, set()).update(campos)

    return [
        {
            "nombre": h.nombre,
            "descripcion": h.descripcion.strip(),
            "tipo": h.tipo,
            "verifica_identidad": h.verifica_identidad,
            "campos_conocidos": sorted(conocidos.get(h.nombre, set())),
        }
        for h in config.herramientas
    ]


# =============================================================================
#  CREAR / EDITAR / BORRAR
# =============================================================================

def _aplicar_herramientas(doc, nombre_rol: str, herramientas: list[dict],
                           campos_permitidos_out: dict) -> None:
    """
    Muta 'herramientas' del documento round-trip: agrega nombre_rol a
    roles_permitidos de cada herramienta seleccionada (si no estaba), y lo
    quita de las que ya no estan seleccionadas. Documental/defensa en
    profundidad -- el motor autoriza por Rol.puede_consultar, no por esto --
    pero dejarlo desactualizado seria mentir en la config.
    """
    seleccionadas = {h["nombre"] for h in herramientas}
    for herr in doc.get("herramientas", []):
        nombre_herr = herr.get("nombre")
        permitidos = herr.get("roles_permitidos", [])
        ya_esta = nombre_rol in permitidos
        if nombre_herr in seleccionadas and not ya_esta:
            permitidos.append(nombre_rol)
        elif nombre_herr not in seleccionadas and ya_esta:
            permitidos.remove(nombre_rol)

    for h in herramientas:
        campos = h.get("campos_permitidos") or []
        if campos:
            campos_permitidos_out[h["nombre"]] = list(campos)


def crear_rol(ruta: str | Path, nombre: str, area: str | None, cargo: str | None,
              descripcion: str, orientado_a: str, herramientas: list[dict]) -> TenantConfig:
    ruta = Path(ruta)
    _validar_nombre_rol(nombre)
    doc = _cargar_rt(ruta)

    if nombre in doc.get("roles", {}):
        raise ErrorEdicion(f"ya existe un rol llamado '{nombre}'")

    campos_permitidos: dict = {}
    _aplicar_herramientas(doc, nombre, herramientas, campos_permitidos)

    nuevo_rol = {
        "descripcion": descripcion,
        "orientado_a": orientado_a,
        "puede_consultar": [h["nombre"] for h in herramientas],
        "campos_permitidos": campos_permitidos,
    }
    if area:
        nuevo_rol["area"] = area
    if cargo:
        nuevo_rol["cargo"] = cargo
    doc.setdefault("roles", {})[nombre] = nuevo_rol

    return _escribir_y_validar(ruta, doc)


def editar_rol(ruta: str | Path, nombre: str, area: str | None, cargo: str | None,
               descripcion: str, orientado_a: str, herramientas: list[dict]) -> TenantConfig:
    ruta = Path(ruta)
    doc = _cargar_rt(ruta)

    if nombre not in doc.get("roles", {}):
        raise ErrorEdicion(f"el rol '{nombre}' no existe")

    campos_permitidos: dict = {}
    _aplicar_herramientas(doc, nombre, herramientas, campos_permitidos)

    rol = doc["roles"][nombre]
    rol["descripcion"] = descripcion
    rol["area"] = area
    rol["cargo"] = cargo
    rol["orientado_a"] = orientado_a
    rol["puede_consultar"] = [h["nombre"] for h in herramientas]
    rol["campos_permitidos"] = campos_permitidos

    return _escribir_y_validar(ruta, doc)


def borrar_rol(ruta: str | Path, nombre: str) -> TenantConfig:
    ruta = Path(ruta)
    doc = _cargar_rt(ruta)

    if nombre not in doc.get("roles", {}):
        raise ErrorEdicion(f"el rol '{nombre}' no existe")

    destino_escalamiento = (doc.get("escalamiento") or {}).get("destino_rol")
    if destino_escalamiento == nombre:
        raise ErrorEdicion(
            f"'{nombre}' es el destino de escalamiento (escalamiento.destino_rol). "
            f"Cambia ese destino antes de borrar el rol.")

    del doc["roles"][nombre]

    for herr in doc.get("herramientas", []):
        permitidos = herr.get("roles_permitidos", [])
        if nombre in permitidos:
            permitidos.remove(nombre)

    overrides = (doc.get("llm") or {}).get("overrides")
    if overrides:
        for clave in [c for c in overrides if c == f"rol:{nombre}"]:
            del overrides[clave]

    return _escribir_y_validar(ruta, doc)
