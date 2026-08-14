# -*- coding: utf-8 -*-
"""
================================================================================
 EJECUTOR DE HERRAMIENTAS TIPO 'http'
================================================================================

Genérico a propósito: no sabe qué API está llamando, ni qué tenant es, ni qué
significan los datos que devuelve. Solo sabe ejecutar lo que una
'Herramienta' (nucleo/config/schema.py) declara: endpoint, método, y cómo
resolver la clave desde el entorno.

Lo que decide (qué endpoint, qué filtros, qué campos se muestran despues) es
config. Lo que este modulo hace es mecanico: no interpreta la respuesta, no
filtra campos (eso es nucleo/seguridad/listas_blancas.py) y no decide si el
tenant puede o no llamarlo (eso lo resuelve el motor antes de invocar esto).
================================================================================
"""

from __future__ import annotations

import time

import requests

from nucleo.seguridad import secretos

TIMEOUT_SEGUNDOS = 15


class ErrorHerramientaHttp(Exception):
    """Fallo al resolver credenciales o al llamar al endpoint."""


def headers_de(herramienta, tenant: str | None = None) -> dict:
    """Header de autenticacion de una Herramienta. Publico porque
    nucleo/herramientas/agregado.py tambien lo necesita, con su propio manejo
    de errores (no puede usar 'ejecutar()' porque esa levanta en cualquier
    HTTP 400 en vez de devolver un error que el modelo pueda corregir).

    'tenant' decide si la credencial puede venir de la empresa: con el, se
    busca primero en sus secretos cifrados y despues en el entorno; sin el,
    solo en el entorno. Es opcional porque hay llamadores legitimos que no
    pertenecen a ninguna empresa (utilidades de cli/), y porque las claves de
    plataforma (la del modelo) siguen viviendo en el entorno a proposito --
    ver nucleo/seguridad/secretos.py.
    """
    if not herramienta.auth_ref:
        return {}
    clave = secretos.obtener(tenant, herramienta.auth_ref)
    if not clave:
        raise ErrorHerramientaHttp(
            f"Falta la credencial '{herramienta.auth_ref}'. La configuracion "
            f"guarda el NOMBRE del secreto, no su valor: cargalo desde los "
            f"ajustes de la empresa o agregalo al .env.")
    valor = f"{herramienta.auth_esquema} {clave}".strip()
    return {herramienta.auth_header: valor}


def base_url_de(herramienta, variables_tenant: dict | None = None) -> str:
    """
    La base_url efectiva de una Herramienta. Publico por el mismo motivo que
    headers_de().

    Si declara 'base_url' (literal, igual para cualquier empresa -- WispHub,
    BottleCRM self-hosted), esa es la respuesta directa. Si declara
    'base_url_ref' (varia por empresa -- SmartOLT, un subdominio por ISP), se
    resuelve contra 'variables_tenant' (TenantConfig.variables_tenant). El
    validador de schema.py ya garantiza que declara exactamente uno de los
    dos, nunca ninguno ni los dos.
    """
    if herramienta.base_url:
        return herramienta.base_url
    valor = (variables_tenant or {}).get(herramienta.base_url_ref)
    if not valor:
        raise ErrorHerramientaHttp(
            f"Falta la variable de tenant '{herramienta.base_url_ref}'. La "
            f"configuracion guarda el NOMBRE de la variable, no su valor: "
            f"cargala desde los ajustes de la empresa.")
    return valor


def url_de(herramienta, argumentos: dict | None = None,
           variables_tenant: dict | None = None) -> str:
    """
    URL completa (base_url + endpoint) de una Herramienta. Publico por el
    mismo motivo que headers_de().

    'endpoint' puede traer marcadores '{clave}' (ej. '/clientes/{id_servicio}/
    ping/') para APIs que exigen el id en la RUTA, no en query/body -- WispHub
    hace esto en sus endpoints de accion (ping, agregar-cliente). Si se pasa
    'argumentos', cada marcador que matchea una clave la CONSUME (pop): asi
    ese valor no se manda ademas como parametro suelto.
    """
    base_url = base_url_de(herramienta, variables_tenant)
    if not herramienta.endpoint:
        raise ErrorHerramientaHttp(f"'{herramienta.nombre}' no declara 'endpoint'.")
    endpoint = herramienta.endpoint
    if argumentos:
        for clave in list(argumentos):
            marcador = "{" + clave + "}"
            if marcador in endpoint:
                endpoint = endpoint.replace(marcador, str(argumentos.pop(clave)))
    if "{" in endpoint and "}" in endpoint:
        # Un marcador de ruta sin reemplazar significa que el dato que iba ahi
        # no llego -- tipicamente un valor de sesion vacio (ver el 'pop' de
        # inyectar_sesion en motor.py, que OMITE en vez de mandar null). Sin
        # esta guarda se manda el literal '{sn_onu}' como si fuera un
        # identificador real: fallaria del lado del proveedor (si valida) o,
        # peor, podria coincidir con datos de otro cliente (si no valida). No
        # se puede confiar en que la API de turno rechace un valor asi.
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' necesita un dato que no esta disponible "
            f"para este cliente (endpoint sin resolver: '{endpoint}').")
    return base_url.rstrip("/") + endpoint


def ejecutar(herramienta, argumentos: dict, tenant: str | None = None,
             variables_tenant: dict | None = None) -> dict | list:
    """
    'herramienta' es una instancia de nucleo.config.schema.Herramienta con
    tipo='http'. 'argumentos' ya viene validado por el llamador -- este
    modulo no valida forma de negocio, solo ejecuta.

    'tenant' solo se usa para resolver la credencial -- ver headers_de().
    'variables_tenant' solo se usa si la herramienta declara 'base_url_ref'
    -- ver base_url_de().
    """
    if herramienta.tipo != "http":
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}' no es tipo 'http' (es '{herramienta.tipo}').")

    # Copia: url_de() puede popear claves que van en la ruta, y el llamador
    # (nucleo/modelo/motor.py) no espera que su dict se mute por debajo.
    argumentos = dict(argumentos or {})
    url = url_de(herramienta, argumentos, variables_tenant)
    headers = headers_de(herramienta, tenant)

    if herramienta.metodo == "GET":
        r = requests.get(url, headers=headers, params=argumentos, timeout=TIMEOUT_SEGUNDOS)
    elif herramienta.multipart:
        # requests solo arma multipart/form-data cuando hay un 'files=' --
        # con (None, valor) se manda cada campo como parte de formulario
        # comun, sin ser un archivo real. Ver el campo 'multipart' en
        # nucleo/config/schema.py:Herramienta para el motivo.
        archivos = {clave: (None, str(valor)) for clave, valor in argumentos.items()}
        r = requests.request(herramienta.metodo, url, headers=headers,
                             files=archivos, timeout=TIMEOUT_SEGUNDOS)
    else:
        r = requests.request(herramienta.metodo, url, headers=headers,
                             json=argumentos, timeout=TIMEOUT_SEGUNDOS)
    r.raise_for_status()
    crudo = r.json()

    if herramienta.extraer_de and isinstance(crudo, dict) and herramienta.extraer_de in crudo:
        crudo = crudo[herramienta.extraer_de]

    _aplicar_veredictos(herramienta, crudo)
    _aplicar_mapeos(herramienta, crudo)
    return crudo


def _leer_anidado(dato: dict, campo: str):
    """Lee 'campo' de 'dato', con notacion de UN nivel ("Padre.Hijo") para
    objetos anidados -- mismo formato que Rol.campos_permitidos
    (nucleo/seguridad/listas_blancas.py)."""
    if "." in campo:
        padre, hijo = campo.split(".", 1)
        sub = dato.get(padre)
        return sub.get(hijo) if isinstance(sub, dict) else None
    return dato.get(campo)


def _escribir_anidado(dato: dict, campo: str, sufijo: str, valor) -> None:
    """Escribe '{ultimo_tramo}{sufijo}' = valor en el mismo lugar de donde
    se leyo 'campo' -- si es anidado, DENTRO del objeto padre, para que la
    lista blanca lo pueda referenciar con la misma notacion con punto que
    uso para leer el original."""
    if "." in campo:
        padre, hijo = campo.split(".", 1)
        sub = dato.get(padre)
        if isinstance(sub, dict):
            sub[f"{hijo}{sufijo}"] = valor
    else:
        dato[f"{campo}{sufijo}"] = valor


def _aplicar_veredictos(herramienta, dato) -> None:
    """Muta 'dato' in-place agregando '{campo}_veredicto' segun los rangos
    declarados en Herramienta.veredictos -- ver el campo en schema.py.
    Silencioso si el campo no esta o no es numerico: no toda respuesta trae
    todos los campos (ej. una ONU offline sin lectura de senal), y eso no es
    un error del ejecutor."""
    if not herramienta.veredictos or not isinstance(dato, dict):
        return
    for campo, rangos in herramienta.veredictos.items():
        valor = _leer_anidado(dato, campo)
        if not isinstance(valor, (int, float)):
            continue
        for rango in rangos:
            si_desde = rango.desde is None or valor >= rango.desde
            si_hasta = rango.hasta is None or valor <= rango.hasta
            if si_desde and si_hasta:
                _escribir_anidado(dato, campo, "_veredicto", rango.etiqueta)
                break


def _aplicar_mapeos(herramienta, dato) -> None:
    """Muta 'dato' in-place agregando '{campo}_interpretado' segun los
    mapeos de texto declarados en Herramienta.mapeos -- ver el campo en
    schema.py. Silencioso si el valor no esta mapeado: una causa nueva que
    el proveedor todavia no documento no inventa una etiqueta, se queda sin
    interpretar (el dato crudo sigue disponible para quien tenga permiso)."""
    if not herramienta.mapeos or not isinstance(dato, dict):
        return
    for campo, tabla in herramienta.mapeos.items():
        valor = _leer_anidado(dato, campo)
        if not isinstance(valor, str):
            continue
        etiqueta = tabla.get(valor)
        if etiqueta is not None:
            _escribir_anidado(dato, campo, "_interpretado", etiqueta)


def ejecutar_asincrono(herramienta, argumentos: dict,
                       intentos: int = 10, espera_segundos: float = 1.5,
                       tenant: str | None = None,
                       variables_tenant: dict | None = None) -> dict | list:
    """
    Para APIs que no responden en el momento: WispHub, al menos en ping y en
    crear/borrar cliente, devuelve {'task_id': ...} (202) y hay que consultar
    aparte -- ver .claude/skills/wisphub-api/SKILL.md. Generico a proposito
    (no menciona WispHub en el codigo): cualquier API que siga el mismo
    patron tarea/resultado sirve, mientras publique el resultado en
    '<base_url>/tasks/<task_id>/' con una clave 'status'.

    Verificado en vivo (agosto 2026, ping_cliente): tarda ~3 segundos en la
    practica -- 10 intentos a 1.5s de por medio (15s) es margen de sobra, no
    un numero elegido al azar.
    """
    inicial = ejecutar(herramienta, argumentos, tenant, variables_tenant)
    task_id = inicial.get("task_id") if isinstance(inicial, dict) else None
    if not task_id:
        raise ErrorHerramientaHttp(
            f"'{herramienta.nombre}': se esperaba 'task_id' en la respuesta y no vino.")

    url_tarea = base_url_de(herramienta, variables_tenant).rstrip("/") + f"/tasks/{task_id}/"
    headers = headers_de(herramienta, tenant)

    for _ in range(intentos):
        time.sleep(espera_segundos)
        r = requests.get(url_tarea, headers=headers, timeout=TIMEOUT_SEGUNDOS)
        r.raise_for_status()
        cuerpo = r.json()
        tarea = cuerpo.get("task", cuerpo) if isinstance(cuerpo, dict) else {}
        estado = tarea.get("status")
        if estado == "SUCCESS":
            return tarea.get("result")
        if estado in ("FAILURE", "REVOKED"):
            raise ErrorHerramientaHttp(
                f"'{herramienta.nombre}': la tarea termino en estado '{estado}'.")

    raise ErrorHerramientaHttp(
        f"'{herramienta.nombre}': la tarea no termino despues de "
        f"{intentos * espera_segundos:.0f}s.")
