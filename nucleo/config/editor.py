# -*- coding: utf-8 -*-
"""
================================================================================
 EDITOR DE ROLES  -  crear/editar/borrar agentes desde la interfaz
================================================================================

`schema.py` valida; este modulo ESCRIBE. Separado a proposito: `cargar_config`
no necesita saber nada de edicion, y este archivo no necesita saber nada de
como se sirve por HTTP (eso vive en canales/api.py).

Alcance deliberado (ver plan aprobado): solo se crean/editan/borran ROLES.
Crear una herramienta nueva -- conectar una API nueva, decidir sus filtros
verificados, su whitelist de campos -- sigue siendo trabajo de codigo. No es
un limite tecnico de este modulo, es que esa superficie es sensible en
seguridad y no encaja en "editar desde una pantalla".

Escribe en la base, no en el YAML
---------------------------------
Antes este modulo reescribia `tenants/<slug>.config.yaml` con ruamel.yaml para
preservar sus comentarios. En el servidor eso no sirve para nada: esa carpeta
viaja DENTRO de la imagen del contenedor, y el motor ya no la lee -- lee
`asistente.tenant_config` (ver nucleo/config/fuente.py). Un editor que escribia
ahi guardaba sin error en un archivo desechable que nadie iba a consultar: el
cambio se veia en pantalla, no tenia efecto, y desaparecia en el siguiente
despliegue.

Asi que se escribe donde se lee. La fuente de verdad es una sola.

  asistente.tenant_config.config (JSONB)   lo que este modulo escribe
  tenants/<slug>.config.yaml               semilla de alta, ya no se toca

⚠️  El YAML del repositorio NO se entera de lo que se edita aqui. Es
deliberado -- no hay disco donde escribirlo que sobreviva al despliegue -- pero
tiene una consecuencia: volver a correr `cli/cargar_config.py` sobre ese YAML
PISA lo que el cliente haya cambiado desde la interfaz. Ese comando es para
dar de alta un tenant o para aplicar un cambio de esquema, no rutina.

Leer, mutar y escribir en UNA transaccion
-----------------------------------------
`_editar()` toma la fila con `for update` y no la suelta hasta guardar. Sin
eso, dos administradores guardando a la vez se pisan: los dos leen la misma
configuracion, cada uno le agrega SU rol, y el segundo en escribir borra el
rol del primero -- sin error y sin rastro, porque cada uno escribe un
documento completo y valido.

Validar antes de escribir
--------------------------
El documento se muta en memoria y ESE resultado pasa por el mismo camino que
`cargar_config` (barrido de secretos + `TenantConfig(**...)`). Solo si valida
se escribe. Si no valida se lanza `ErrorEdicion` con TODOS los problemas
juntos, y como la excepcion sale de la transaccion, la base queda intacta.

Lo que se guarda es el volcado del modelo ya validado, no el diccionario
crudo: la misma forma canonica que escribe `cli/cargar_config.py`, para que
comparar ambas versiones siga siendo posible.
================================================================================
"""

from __future__ import annotations

import copy
import json
import re
from typing import Callable

from pydantic import ValidationError

from .schema import TenantConfig, _barrer_secretos

_RE_NOMBRE_ROL = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


class ErrorEdicion(ValueError):
    pass


# =============================================================================
#  VALIDACION Y ESCRITURA
# =============================================================================

def _validar(tenant: str, crudo: dict) -> TenantConfig:
    """Mismo camino que cargar_config(), pero sobre el documento en memoria."""
    secretos = _barrer_secretos(crudo)
    if secretos:
        raise ErrorEdicion(
            f"{tenant}: hay valores con pinta de credencial:\n  - "
            + "\n  - ".join(secretos))

    try:
        return TenantConfig(**crudo)
    except ValidationError as e:
        lineas = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                  for err in e.errors()]
        raise ErrorEdicion(
            f"{tenant}: {len(lineas)} problema(s) de configuracion:\n  - "
            + "\n  - ".join(lineas)) from None


def _editar(tenant: str, mutar: Callable[[dict], None]) -> TenantConfig:
    """
    Lee la configuracion vigente, le aplica 'mutar', valida el resultado y lo
    guarda -- todo dentro de la misma transaccion, con la fila bloqueada.

    Cualquier excepcion (la que lance 'mutar' o la de validacion) sale de la
    transaccion sin escribir: nucleo/persistencia/db.py hace rollback.
    """
    from nucleo.persistencia.db import sesion     # perezoso: evita ciclo

    with sesion(tenant) as (cur, org):
        cur.execute("""select config, config_version
                       from asistente.tenant_config
                       where organization_id = %s
                       for update""", (org,))
        fila = cur.fetchone()
        if not fila or not fila["config"]:
            raise ErrorEdicion(
                f"'{tenant}' no tiene configuracion cargada en la base, asi que "
                f"no hay nada que editar. Cargarla primero con: "
                f"py -3.13 cli/cargar_config.py tenants/{tenant}.config.yaml")

        # Copia independiente a proposito: 'mutar' cambia dicts anidados en el
        # lugar (ej. _mutar_editar hace rol["descripcion"] = ...). Sin copiar,
        # 'doc' y 'fila["config"]' son el MISMO objeto, así que mutar 'doc'
        # tambien corrompe el "antes" que se usa mas abajo para detectar
        # cambios -- el resultado quedaba comparado contra si mismo y
        # 'datos == fila["config"]' daba True siempre, así que ninguna edicion
        # a un rol EXISTENTE llegaba a guardarse (crear_rol no lo sufria por
        # casualidad: el rol nuevo no traia los campos con default que Pydantic
        # agrega al validar, y esa diferencia de claves bastaba para que el
        # 'if' de abajo diera False).
        doc = copy.deepcopy(fila["config"])
        mutar(doc)
        config = _validar(tenant, doc)
        datos = config.model_dump(mode="json")

        # Igual que cli/cargar_config.py: si el contenido no cambio, no se sube
        # la version. Asi 'config_version' cuenta cambios reales y no clics en
        # el boton de guardar.
        if datos == fila["config"]:
            print(f"[config] {tenant}: sin cambios (v{fila['config_version']})")
            return config

        cur.execute("""update asistente.tenant_config
                       set config = %s,
                           config_version = config_version + 1,
                           actualizado_en = now()
                       where organization_id = %s
                       returning config_version""",
                    (json.dumps(datos), org))
        version = cur.fetchone()["config_version"]

    print(f"[config] {tenant}: v{version} guardada desde el editor")
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
#  MUTACIONES  -  sobre el documento, sin saber de donde salio
# =============================================================================
#  Separadas de la transaccion a proposito: son funciones puras sobre un dict
#  y se pueden probar sin base de datos (tests/test_editor_config.py).

def _comprobar_nadie_se_queda_sin_roles(doc: dict) -> None:
    """
    Una herramienta cuyo ultimo rol se va queda sin nadie que pueda usarla, y
    el esquema la rechaza (roles_permitidos exige al menos uno).

    Se avisa aca y no se deja llegar al validador porque ahi el error sale como
    'herramientas.8.roles_permitidos: List should have at least 1 item': indica
    una posicion en una lista que el administrador no ve y no dice que hacer.
    El caso llega solo -- desmarcar en un rol la unica herramienta que ese rol
    tenia en exclusiva -- y desde el formulario parece un cambio inocente.
    """
    huerfanas = [h.get("nombre") for h in doc.get("herramientas", [])
                 if not h.get("roles_permitidos")]
    if huerfanas:
        raise ErrorEdicion(
            f"{', '.join(huerfanas)}: se quedaria(n) sin ningun rol que "
            f"pueda(n) usarla(s), y una herramienta que nadie puede consultar "
            f"no se puede guardar. Asignala a otro rol antes de quitarsela a "
            f"este.")


def _aplicar_herramientas(doc: dict, nombre_rol: str, herramientas: list[dict],
                          campos_permitidos_out: dict, anterior: set[str] | None = None) -> None:
    """
    Muta 'herramientas' del documento: agrega nombre_rol a roles_permitidos de
    cada herramienta seleccionada (si no estaba), y lo quita de las que ya no
    estan seleccionadas. Documental/defensa en profundidad -- el motor autoriza
    por Rol.puede_consultar, no por esto -- pero dejarlo desactualizado seria
    mentir en la config.

    'anterior' es el 'puede_consultar' del rol ANTES de esta edicion. Solo se
    le quita 'nombre_rol' a una herramienta si de verdad estaba ahi -- nunca
    por una herramienta que el rol nunca ofrecio en su catalogo, aunque
    'roles_permitidos' la apunte a este rol por otro motivo. Caso real: las
    herramientas de uso interno de escalamiento (nucleo/seguimiento/
    escalamiento.py, ej. 'crear_caso_soporte') no las llama ningun modelo, asi
    que ningun rol las tiene en 'puede_consultar' -- pero el esquema exige
    'roles_permitidos' con al menos un elemento, asi que quedan apuntando a un
    rol cualquiera (ej. 'administracion') solo para cumplir esa cota minima.
    Sin este chequeo, CUALQUIER guardado de ese rol las desvinculaba (no
    estaban entre las seleccionadas del formulario, que ni las ofrece) y el
    validador rechazaba el guardado entero por dejarlas huerfanas.
    """
    anterior = anterior or set()
    seleccionadas = {h["nombre"] for h in herramientas}
    for herr in doc.get("herramientas", []):
        nombre_herr = herr.get("nombre")
        permitidos = herr.setdefault("roles_permitidos", [])
        ya_esta = nombre_rol in permitidos
        if nombre_herr in seleccionadas and not ya_esta:
            permitidos.append(nombre_rol)
        elif nombre_herr not in seleccionadas and ya_esta and nombre_herr in anterior:
            permitidos.remove(nombre_rol)

    for h in herramientas:
        campos = h.get("campos_permitidos") or []
        if campos:
            campos_permitidos_out[h["nombre"]] = list(campos)


def _mutar_crear(doc: dict, nombre: str, area: str | None, cargo: str | None,
                 descripcion: str, orientado_a: str, herramientas: list[dict]) -> None:
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
    _comprobar_nadie_se_queda_sin_roles(doc)


def _mutar_editar(doc: dict, nombre: str, area: str | None, cargo: str | None,
                  descripcion: str, orientado_a: str, herramientas: list[dict]) -> None:
    if nombre not in doc.get("roles", {}):
        raise ErrorEdicion(f"el rol '{nombre}' no existe")

    anterior = set(doc["roles"][nombre].get("puede_consultar") or [])
    campos_permitidos: dict = {}
    _aplicar_herramientas(doc, nombre, herramientas, campos_permitidos, anterior)

    rol = doc["roles"][nombre]
    rol["descripcion"] = descripcion
    rol["area"] = area
    rol["cargo"] = cargo
    rol["orientado_a"] = orientado_a
    rol["puede_consultar"] = [h["nombre"] for h in herramientas]
    rol["campos_permitidos"] = campos_permitidos
    _comprobar_nadie_se_queda_sin_roles(doc)


def _mutar_persona(doc: dict, nombre_asistente: str, tono: str,
                   longitud_respuesta: str, instrucciones_adicionales: str) -> None:
    """
    Como se presenta y como escribe el asistente.

    No toca permisos: ni que herramientas hay, ni que campos devuelve cada
    una. Por eso es lo primero que se puede dejar en manos del cliente sin
    revisar nada -- lo peor que puede hacer aca es que su asistente hable
    raro, no que muestre un dato que no debia.
    """
    doc.setdefault("persona", {}).update({
        "nombre_asistente": nombre_asistente,
        "tono": tono,
        "longitud_respuesta": longitud_respuesta,
        "instrucciones_adicionales": instrucciones_adicionales,
    })


def _mutar_identidad_descripcion(doc: dict, descripcion: str) -> None:
    """
    Que servicios y planes ofrece la empresa, en prosa -- se inyecta SIEMPRE
    en el prompt de cualquier rol (ver nucleo/recuperacion/prompt.py), a
    diferencia del corpus (RAG, solo si la pregunta matchea). No toca
    permisos ni roles, mismo criterio de riesgo bajo que _mutar_persona.
    """
    doc.setdefault("identidad", {})["descripcion"] = descripcion


def _mutar_canal_whatsapp(doc: dict, activo: bool, numero_visible: str | None) -> None:
    """
    Prender/apagar el canal y el numero que se muestra en la pantalla de
    ajustes ("estas atendiendo desde el 300...").

    NO toca los '*_ref' (phone_number_id_ref, token_ref, etc): esos son los
    NOMBRES de los secretos y ya vienen declarados desde el alta del tenant,
    siguiendo la convencion de la plataforma (WHATSAPP_PHONE_NUMBER_ID...).
    Lo que carga el cliente desde la interfaz son los VALORES, que van
    aparte, cifrados, en asistente.tenant_secrets -- nunca en este documento
    (ver nucleo/seguridad/secretos.py).

    Pydantic exige que los cuatro refs indispensables esten DECLARADOS para
    poner 'activo: true' (CanalWhatsApp._activo_exige_lo_indispensable), pero
    eso no confirma que haya un VALOR cargado para cada uno -- ese chequeo es
    de la pantalla, no de este documento, porque este documento nunca ve
    valores de secretos.
    """
    doc.setdefault("canales", {}).setdefault("whatsapp", {})
    doc["canales"]["whatsapp"]["activo"] = activo
    doc["canales"]["whatsapp"]["numero_visible"] = numero_visible or None


def _mutar_borrar(doc: dict, nombre: str) -> None:
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

    _comprobar_nadie_se_queda_sin_roles(doc)


# =============================================================================
#  CREAR / EDITAR / BORRAR
# =============================================================================

def crear_rol(tenant: str, nombre: str, area: str | None, cargo: str | None,
              descripcion: str, orientado_a: str,
              herramientas: list[dict]) -> TenantConfig:
    _validar_nombre_rol(nombre)
    return _editar(tenant, lambda doc: _mutar_crear(
        doc, nombre, area, cargo, descripcion, orientado_a, herramientas))


def editar_rol(tenant: str, nombre: str, area: str | None, cargo: str | None,
               descripcion: str, orientado_a: str,
               herramientas: list[dict]) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_editar(
        doc, nombre, area, cargo, descripcion, orientado_a, herramientas))


def borrar_rol(tenant: str, nombre: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_borrar(doc, nombre))


def guardar_persona(tenant: str, nombre_asistente: str, tono: str,
                    longitud_respuesta: str,
                    instrucciones_adicionales: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_persona(
        doc, nombre_asistente, tono, longitud_respuesta,
        instrucciones_adicionales))


def guardar_identidad_descripcion(tenant: str, descripcion: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_identidad_descripcion(doc, descripcion))


def guardar_canal_whatsapp(tenant: str, activo: bool,
                           numero_visible: str | None) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_canal_whatsapp(doc, activo, numero_visible))
