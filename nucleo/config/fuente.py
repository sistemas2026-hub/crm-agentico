# -*- coding: utf-8 -*-
"""
================================================================================
 FUENTE DE LA CONFIGURACION  --  la base manda, el YAML siembra
================================================================================

Por que existe
--------------
El motor leia la configuracion de 'tenants/<slug>.config.yaml', y el editor de
la interfaz escribia en ese mismo archivo. En un servidor eso NO funciona: la
carpeta 'tenants/' viaja dentro de la imagen del contenedor, que es
desechable. Lo que un cliente cambiara desde la interfaz sobrevivia hasta el
siguiente despliegue y despues volvia a lo que dijera el repositorio -- sin
error, sin aviso, sin rastro.

Para un producto donde cada empresa se autogestiona, eso es incompatible con
el modelo de negocio, no un detalle de implementacion.

Quien manda
-----------
  asistente.tenant_config (JSONB)   fuente de verdad
  tenants/<slug>.config.yaml        semilla de alta y respaldo legible

El YAML no desaparece: sigue siendo como se da de alta un tenant nuevo
(cli/cargar_config.py lo lee y lo escribe en la base) y como se revisa en una
revision de codigo. Pero en ejecucion nadie lo lee.

Se valida igual venga de donde venga
------------------------------------
La configuracion de la base pasa por el MISMO TenantConfig que la del archivo.
No es ceremonia: el validador es el que rechaza claves pegadas en vez de
referencias, filtros sin verificar y herramientas sin lista blanca de campos.
Una configuracion editada desde una interfaz web merece esa revision mas que
una escrita a mano por alguien del equipo, no menos.
================================================================================
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from nucleo.config.schema import TenantConfig, cargar_config


class ErrorConfig(ValueError):
    pass


def _validar(crudo: dict, origen: str) -> TenantConfig:
    try:
        return TenantConfig(**crudo)
    except ValidationError as e:
        lineas = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                  for err in e.errors()]
        raise ErrorConfig(
            f"{origen}: {len(lineas)} problema(s) de configuracion:\n  - "
            + "\n  - ".join(lineas)) from None


def desde_base(tenant: str) -> tuple[TenantConfig, int] | None:
    """
    (configuracion, version) desde asistente.tenant_config, o None si ese
    tenant todavia no esta cargado en la base.
    """
    from nucleo.persistencia.db import sesion       # perezoso: evita ciclo

    with sesion(tenant) as (cur, _org):
        cur.execute("""select config, config_version
                       from asistente.tenant_config where slug = %s""", (tenant,))
        fila = cur.fetchone()

    if not fila or not fila["config"]:
        return None
    return _validar(fila["config"], f"tenant_config[{tenant}]"), fila["config_version"]


def cargar(tenant: str, raiz: str | Path = ".") -> TenantConfig:
    """
    La configuracion vigente del tenant.

    Base primero. Si no esta ahi -tenant recien creado, o una instalacion de
    desarrollo sin base- cae al YAML, para que levantar el motor en una
    maquina no exija tener Postgres arriba.

    El fallback avisa por consola: si en produccion aparece ese aviso,
    significa que se esta sirviendo una configuracion que nadie puede editar
    desde la interfaz, y eso hay que verlo.
    """
    try:
        resultado = desde_base(tenant)
        if resultado is not None:
            config, version = resultado
            print(f"[config] {tenant}: v{version} desde la base")
            return config
        motivo = "el tenant no esta en asistente.tenant_config"
    except ErrorConfig:
        raise
    except Exception as e:
        motivo = f"no se pudo leer la base ({type(e).__name__})"

    ruta = Path(raiz) / "tenants" / f"{tenant}.config.yaml"
    print(f"[config] {tenant}: usando {ruta} -- {motivo}. "
          f"Los cambios hechos desde la interfaz NO se veran aqui.")
    return cargar_config(ruta)
