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

import re
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


def _gpon_hex(valor: str) -> str | None:
    """
    El serial de una ONU se escribe de dos formas equivalentes: 'DC90E681213E'
    (los 4 primeros caracteres son el fabricante, en ASCII) y
    '44433930E681213E' (ese mismo prefijo en hexadecimal). Es la
    representacion estandar GPON, no una rareza de un proveedor.

    Devuelve None si el valor no tiene la forma esperada -- convertir a ciegas
    daria un identificador inventado, y pedir datos de "algun" equipo es peor
    que fallar.
    """
    if len(valor) != 12 or not valor.isalnum():
        return None
    return "".join(f"{ord(ch):02X}" for ch in valor[:4]) + valor[4:]


# Transformaciones que un tenant puede pedir por nombre desde
# 'Herramienta.reintentar_identificador_como' (ver schema.py). El nucleo
# provee el mecanismo; que herramienta lo necesita es decision del tenant.
_TRANSFORMACIONES = {"gpon_hex": _gpon_hex}


def _alternativas(herramienta, argumentos: dict) -> dict:
    """Los argumentos con su identificador ya convertido, o {} si no hay
    ninguna transformacion aplicable. No muta el original."""
    cambiados = dict(argumentos)
    hubo_cambio = False
    for clave, nombre in (herramienta.reintentar_identificador_como or {}).items():
        valor = argumentos.get(clave)
        transformar = _TRANSFORMACIONES.get(nombre)
        if not isinstance(valor, str) or transformar is None:
            continue
        nuevo = transformar(valor)
        if nuevo and nuevo != valor:
            cambiados[clave] = nuevo
            hubo_cambio = True
    return cambiados if hubo_cambio else {}


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

    argumentos = dict(argumentos or {})
    headers = headers_de(herramienta, tenant)

    def _pedir(args: dict):
        # Copia por intento: url_de() popea las claves que van en la RUTA, asi
        # que un segundo intento con el mismo dict ya no las encontraria.
        args = dict(args)
        url = url_de(herramienta, args, variables_tenant)
        if herramienta.metodo == "GET":
            return requests.get(url, headers=headers, params=args,
                                timeout=TIMEOUT_SEGUNDOS)
        if herramienta.multipart:
            # requests solo arma multipart/form-data cuando hay un 'files=' --
            # con (None, valor) se manda cada campo como parte de formulario
            # comun, sin ser un archivo real. Ver el campo 'multipart' en
            # nucleo/config/schema.py:Herramienta para el motivo.
            archivos = {c: (None, str(v)) for c, v in args.items()}
            return requests.request(herramienta.metodo, url, headers=headers,
                                    files=archivos, timeout=TIMEOUT_SEGUNDOS)
        return requests.request(herramienta.metodo, url, headers=headers,
                                json=args, timeout=TIMEOUT_SEGUNDOS)

    r = _pedir(argumentos)

    # Un identificador con dos escrituras validas: si la primera no le sirve a
    # la API, se prueba la otra ANTES de dar el dato por inexistente. Ver
    # 'reintentar_identificador_como' en schema.py -- sin esto, los clientes
    # cuyo equipo esta registrado con la otra forma se quedan sin diagnostico
    # y el error no dice por que. Un solo reintento, y solo si la
    # transformacion produjo algo distinto.
    if not r.ok:
        alternativos = _alternativas(herramienta, argumentos)
        if alternativos:
            print(f"[http] '{herramienta.nombre}': {r.status_code} con el "
                  f"identificador original, reintentando con la forma alternativa")
            r = _pedir(alternativos)

    r.raise_for_status()
    crudo = r.json()

    if herramienta.extraer_de:
        # Notacion con punto: hay respuestas con el dato util a dos niveles de
        # profundidad ('response.hostlist' en get_onu_router_hosts). Sin esto
        # habria que dejar pasar el nivel intermedio ENTERO por la lista
        # blanca, que es justo como se filtro la IP del cliente por 'ping-1'.
        for parte in herramienta.extraer_de.split("."):
            if isinstance(crudo, dict) and parte in crudo:
                crudo = crudo[parte]
            else:
                break

    # Diccionario indexado por numero -> lista. Algunas APIs devuelven
    # {"1": {...}, "2": {...}} donde cualquiera esperaria un arreglo (SmartOLT
    # lo hace en la lista de equipos conectados). La lista blanca sabe filtrar
    # una lista de registros; un dict con claves dinamicas no, porque los
    # nombres de campo serian "1" y "2".
    if isinstance(crudo, dict) and crudo and all(k.isdigit() for k in crudo):
        crudo = list(crudo.values())

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


def _a_numero(valor):
    """El valor como float, o None si no hay ningun numero que sacarle.

    Acepta texto con unidad pegada -- SmartOLT devuelve la señal optica como
    '-20.04 dBm', no como -20.04, y una ONU offline devuelve '-' a secas.
    Exigir que ya sea numerico (lo que hacia esta funcion antes) dejaba el
    veredicto sin calcular EN TODOS LOS CASOS para esa API, en silencio:
    'aceptable' nunca aparecia, y con el la precondicion de reiniciar_ont
    nunca podia cumplirse. Encontrado 14/08/2026."""
    if isinstance(valor, bool):
        return None                      # True/False no son medidas
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        m = re.search(r"-?\d+(?:\.\d+)?", valor)
        if m:
            return float(m.group(0))
    return None


def _aplicar_veredictos(herramienta, dato) -> None:
    """Muta 'dato' in-place agregando '{campo}_veredicto' segun los rangos
    declarados en Herramienta.veredictos -- ver el campo en schema.py.
    Silencioso si el campo no esta o no tiene un numero que leer: no toda
    respuesta trae todos los campos (ej. una ONU offline devuelve '-' en vez
    de la señal), y eso no es un error del ejecutor."""
    if not herramienta.veredictos or not isinstance(dato, dict):
        return
    for campo, rangos in herramienta.veredictos.items():
        valor = _a_numero(_leer_anidado(dato, campo))
        if valor is None:
            continue
        for rango in rangos:
            si_desde = rango.desde is None or valor >= rango.desde
            si_hasta = rango.hasta is None or valor <= rango.hasta
            if si_desde and si_hasta:
                _escribir_anidado(dato, campo, "_veredicto", rango.etiqueta)
                break


# Lo que se escribe cuando el proveedor manda un valor que el mapeo no
# conoce. NO lleva el valor crudo adentro a proposito: quien solo tiene
# '_interpretado' en su lista blanca no lo tiene por casualidad, y meterle el
# dato original aca lo colaria por la puerta de atras.
SIN_MAPEAR = "el sistema reporto una causa que no sabemos interpretar"


def _aplicar_mapeos(herramienta, dato) -> None:
    """Muta 'dato' in-place agregando '{campo}_interpretado' segun los
    mapeos de texto declarados en Herramienta.mapeos -- ver el campo en
    schema.py.

    Un valor que el mapeo NO conoce no inventa una etiqueta, pero tampoco se
    calla: escribe SIN_MAPEAR. Antes se quedaba en silencio, apoyandose en
    que "el dato crudo sigue disponible para quien tenga permiso" -- y eso es
    falso justo para el rol que hace el diagnostico, cuya lista blanca solo
    deja pasar '_interpretado'. Medido el 21/08/2026 contra la ONU de prueba:
    la causa real era 're-register', que no estaba en el mapeo, y la
    herramienta devolvio {"ONU details": {}}. El agente quedo ciego, no tenia
    forma de saberlo, y siguio pidiendo un reinicio manual como si nada.
    Una etiqueta que dice "no se" deja al modelo escalar por falta de datos;
    un dict vacio lo deja adivinando."""
    if not herramienta.mapeos or not isinstance(dato, dict):
        return
    for campo, tabla in herramienta.mapeos.items():
        valor = _leer_anidado(dato, campo)
        if not isinstance(valor, str) or not valor.strip():
            continue
        _escribir_anidado(dato, campo, "_interpretado",
                          tabla.get(valor, SIN_MAPEAR))


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
