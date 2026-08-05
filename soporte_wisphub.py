"""
================================================================================
  ASISTENTE DE SOPORTE  —  Qwen3 (Ollama)  +  API de WispHub
  Version con: configuracion en .env  +  filtro de campos PII  +  consulta por cedula
================================================================================

El modelo DECIDE que herramienta llamar; ESTE codigo VALIDA, EJECUTA y ADEMAS
FILTRA los datos: a Qwen3 solo le llegan los campos necesarios, nunca IP, MAC,
ni contrasenas de equipos. La clave API vive en un archivo .env aparte, jamas
dentro del codigo.

--------------------------------------------------------------------------------
REQUISITOS (una sola vez):
    py -3.13 -m pip install ollama requests python-dotenv
    ollama pull qwen3:4b

CONFIGURACION (archivo .env en la MISMA carpeta que este script):
    WISPHUB_API_KEY=tu_clave_real_aqui
    WISPHUB_MODO_REAL=false        -> datos simulados (para probar sin tocar nada)
    WISPHUB_MODO_REAL=true         -> llama a WispHub de verdad
    WISPHUB_BASE_URL=https://api.wisphub.io   (opcional; este es el valor por defecto)

    NO subas el .env a OneDrive, Git, ni lo compartas. Guarda el proyecto en
    una carpeta LOCAL (ej. C:\\wisphub\\), fuera de OneDrive.
================================================================================
"""

import os
import re
import sys
import json
import time
import calendar
from datetime import datetime

import requests
import ollama

# La consola de Windows suele usar cp1252 y rompe los acentos y las "n" con tilde
# ("¿En qu� puedo ayudar?"). Forzamos UTF-8 en entrada y salida.
for _flujo in (sys.stdout, sys.stderr, sys.stdin):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

### Cargar configuracion desde el archivo .env --------------------------------
# load_dotenv() lee el archivo .env y mete las variables en el entorno,
# ANTES de que el resto del script intente leerlas.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("AVISO: falta python-dotenv. Instala con:  py -3.13 -m pip install python-dotenv")
# -----------------------------------------------------------------------------


# ==============================================================================
#  CONFIGURACION  (toda desde el entorno; nada quemado en el codigo)
# ==============================================================================

def _env_bool(nombre, por_defecto=False):
    """Lee una variable de entorno como booleano. Solo 'true/1/si/yes' activan."""
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "y")

# Modelo que DECIDE la herramienta. Debe ser fiable en tool calling: qwen3.
MODELO = os.environ.get("MODELO_SLM", "qwen3:4b")

# Modelo que REDACTA la respuesta final (segunda llamada, ya sin herramientas).
# Por defecto el mismo, para no cambiar el comportamiento sin querer.
#
# CUIDADO al cambiarlo: este modelo recibe el dato real en un mensaje de rol
# 'tool' y debe limitarse a redactarlo.
#   - phi4-mini  -> medido: correcto y ~2x mas rapido que qwen3 (6.9 s vs 15.6 s).
#   - gemma3:4b  -> NO USAR. Su plantilla no maneja el rol 'tool': ignoro el dato
#     e INVENTO un cliente, un plan y una factura que no existian. Viola RF-07.
# Si se cambia, verificar antes que respeta el dato de la herramienta.
MODELO_REDACCION = os.environ.get("MODELO_REDACCION", MODELO)

# Modo real vs simulado: se decide en el .env, NO editando este archivo.
# Por defecto es SIMULADO: hay que activar el modo real de forma explicita.
USAR_WISPHUB_REAL = _env_bool("WISPHUB_MODO_REAL", False)

WISPHUB_BASE_URL = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
WISPHUB_API_KEY  = os.environ.get("WISPHUB_API_KEY")

if USAR_WISPHUB_REAL and not WISPHUB_API_KEY:
    raise SystemExit(
        "ERROR: WISPHUB_MODO_REAL=true pero no se encontro WISPHUB_API_KEY.\n"
        "Crea un archivo .env en esta carpeta con:  WISPHUB_API_KEY=tu_clave"
    )

def _headers():
    return {
        "Authorization": f"Api-Key {WISPHUB_API_KEY}",
        "Content-Type": "application/json",
    }

# Endpoints verificados contra la doc oficial (wisphub.net/api-docs) y contra la
# API en produccion. Ver notas de integracion en el PRD (7.6).
#
# Los DOS tipos de consulta de cliente usan el mismo endpoint de LISTA con filtro,
# no el de detalle: /api/clientes/{id}/ devuelve un conjunto de campos DISTINTO
# (trae 'facturas_pagadas' pero no 'estado_facturas', 'saldo' ni 'fecha_corte').
# Usando la lista para ambos casos, las dos herramientas devuelven la misma forma
# y una sola lista blanca las cubre.
EP_CLIENTES = "/api/clientes/"      # filtros: ?cedula=  |  ?id_servicio=
EP_FACTURAS = "/api/facturas/"      # filtro por cliente: ?cliente=<usuario>  (NO el id)
EP_TICKET   = "/api/tickets/{id}/"
EP_TICKETS  = "/api/tickets/"       # filtros: ?estado= (numerico), fecha_creacion_0/_1
EP_PAGO     = "/api/facturas/{id}/registrar-pago/"
EP_ZONAS    = "/api/zonas/"         # 5 zonas; se usa para agrupar y para nombrarlas

# Maximo de filas que se le entregan al modelo en una consulta de lista.
# No es un limite de la API sino del modelo: volcarle cientos de registros
# desborda su contexto y degrada la respuesta. Cuando el total supera este tope,
# el filtro avisa explicitamente que el resultado es parcial (ver filtrar_campos).
#
# Para CONTAR no hace falta traer filas: el paginado del API ya devuelve 'count'.
# Una consulta agregada debe pedir limit=1 y leer ese numero (ver PRD 12.5).
LIMITE_FILAS = 50

# Estados de ticket (valores del filtro ?estado=, verificados en produccion).
# El filtro es NUMERICO: ?estado=Nuevo devuelve 0 resultados, sin error.
ESTADOS_TICKET = {1: "Nuevo", 2: "En Progreso", 4: "Cerrado"}
ESTADOS_ABIERTOS = (1, 2)

# Tope de paginas al barrer tickets. Los abiertos son ~280 (3 paginas de 100,
# medido en 5.3 s); los cerrados son 2.255 y por eso NO se barren en vivo.
MAX_PAGINAS = 10

# Cuantos tickets se le muestran al modelo al listar los de un cliente.
# MEDIDO: con 50 tickets en el contexto, qwen3:4b dejo de seguir el prompt
# (respondio en ingles), se puso a "analizar" la lista y saco una conclusion
# inventada. El asesor no necesita la lista: necesita cuantos hay, de que tipo,
# y los ultimos. El conteo lo hace Python (PRD 12.5).
TOPE_TICKETS_LISTA = 5

# Accion al registrar un pago (campo 'accion' del API):
#   0 = solo registrar el pago
#   1 = registrar el pago Y reactivar el servicio
# Se usa 0 por defecto: reactivar es un efecto adicional que el asesor no pidio.
ACCION_PAGO = int(os.environ.get("WISPHUB_ACCION_PAGO", "0"))

# Tope de grupos al agrupar un conteo. Agrupar cuesta UNA llamada por valor:
# por estado son 3-5 (barato), por plan serian 55 (no). Si el campo tiene mas
# valores que este tope, se rechaza la consulta en vez de disparar 55 requests.
TOPE_GRUPOS = 12


# ==============================================================================
#  FILTRO DE CAMPOS (PII)  —  capa de seguridad en CODIGO, no en el prompt
# ==============================================================================
# WispHub devuelve MUCHOS campos, varios sensibles (IP, MAC, contrasenas del CPE
# y del router, etc.). El asistente NO necesita nada de eso para atender.
# Aqui definimos, por herramienta, la lista BLANCA de campos que si puede ver
# el modelo. Todo lo demas se descarta antes de pasarselo a Qwen3.
#
# Para las herramientas que devuelven una LISTA (facturas, busquedas), la lista
# blanca se aplica a CADA elemento de la lista.

# --- Grupos de campos ---------------------------------------------------------
# Nombres VERIFICADOS contra la API en produccion (el endpoint de clientes
# devuelve 54 campos). Se agrupan por naturaleza para componer cada area sin
# repetir listas y sin que una se desactualice respecto de la otra.

_CLIENTE_IDENTIDAD = ["id_servicio", "nombre", "cedula", "estado"]
_CLIENTE_CONTACTO  = ["email", "telefono", "direccion", "localidad", "ciudad"]
_CLIENTE_SERVICIO  = ["plan_internet", "zona", "fecha_instalacion"]
_CLIENTE_PAGO      = ["estado_facturas", "saldo", "fecha_corte"]
_CLIENTE_FINANCIERO = ["precio_plan", "costo_instalacion", "descuento"]
_CLIENTE_RED       = ["ip", "mac_cpe", "sn_onu", "modelo_antena",
                      "modelo_router_wifi", "ssid_router_wifi", "interfaz_lan",
                      "sectorial", "router.nombre", "router.id"]

# NUNCA, para NINGUN area:
#   password_servicio, password_cpe, password_router_wifi,
#   password_ssid_router_wifi, usuario_router_wifi
# Un tecnico que necesite una credencial la saca de WispHub. Pasarla por el
# modelo no le ahorra nada y la deja escrita en el historial de la conversacion.
#
# Tampoco 'usuario' (identificador interno nombre@empresa): el codigo lo usa
# para consultar facturas, el modelo no tiene por que verlo.

# 'servicio' dentro de un ticket NO se abre entero: trae la IP y el router.
_TICKET_BASE = [
    "id_ticket", "asunto", "descripcion", "razon_falla",
    "estado", "prioridad", "tecnico", "departamento", "origen_reporte",
    "fecha_creacion", "fecha_inicio", "fecha_fin",
    "servicio.id_servicio", "servicio.plan_internet", "servicio.zona",
]
# OJO con 'descripcion': es TEXTO LIBRE. Visto en produccion, puede traer
# embebidos nombre, telefono, email, direccion, GPS, documento y enlaces.
# La lista blanca filtra campos, no el contenido de un campo (ver PRD 7.4).

# La LISTA de tickets es mas pobre a proposito que el ticket suelto: sin
# 'descripcion' (texto libre largo, multiplicado por N filas desborda el
# contexto) y sin 'servicio' (redundante: ya sabemos de que cliente son).
_TICKET_LISTA = ["id_ticket", "asunto", "estado", "prioridad",
                 "tecnico", "fecha_creacion"]

_FACTURA = ["id_factura", "estado", "total", "saldo",
            "fecha_emision", "fecha_vencimiento", "fecha_pago"]

# El API responde {task_id, messages}; el modo simulado, {resultado, ...}.
_PAGO_RESULTADO = ["resultado", "id_factura", "total_cobrado",
                   "mensajes", "messages", "task_id", "errors"]

# Una consulta agregada NO devuelve registros: devuelve numeros ya calculados por
# Python mas la declaracion de como se calcularon. No hay PII que filtrar, pero la
# entrada en la lista blanca es obligatoria igual (fail-closed): sin ella la
# herramienta no devolveria nada.
_AGREGADO = ["total", "desglose", "interpretacion", "advertencia"]


# ==============================================================================
#  CATALOGO POR AREA  —  quien pregunta determina que herramientas y que campos
# ==============================================================================
# El motor (validacion, tool calling, filtrado, confirmacion) NO cambia entre
# areas: solo recibe distintas herramientas y distintos campos.
#
# Regla: una herramienta que no aparece en 'herramientas' no se le muestra al
# modelo, y una que no tiene entrada en 'campos' no devuelve nada (fail-closed).
# Las dos condiciones deben cumplirse; no alcanza con una.

# ==============================================================================
#  CATALOGO DE AGREGACION  —  la lista blanca aplicada a la FORMA de la consulta
# ==============================================================================
# El modelo COMPONE la consulta; Python la CALCULA (PRD 12.5). El modelo nunca ve
# filas ni suma nada: propone entidad + filtros + agrupacion, y el codigo traduce
# eso a parametros del API y lee el 'count' del paginado.
#
# TODO lo que hay aqui esta VERIFICADO contra la API en produccion (julio 2026)
# con el metodo del valor imposible: se prueba cada parametro con un valor que no
# puede existir y se compara el total con el de la consulta sin filtro. Si son
# iguales, el API esta IGNORANDO el parametro y no puede entrar a este catalogo.
# Un filtro ignorado no da error: devuelve el universo entero disfrazado de
# respuesta exacta. Lo que sigue son los que sobrevivieron esa prueba.
#
# Verificado que el API IGNORA (y por eso NO estan aqui):
#   clientes: zona, estado_facturas, saldo, fecha_instalacion (en cualquier forma)
#   facturas: facturadas
#   tickets:  departamento, tecnico, prioridad

_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

AGREGACIONES = {
    "clientes": {
        "endpoint": EP_CLIENTES,
        "etiqueta": "clientes",
        # Verificado: 4260+811+2093+88 = 7252 = total sin filtro. Cuadra exacto.
        "filtros": {
            "estado": {"param": "estado",
                       "valores": {"activo": 1, "suspendido": 2,
                                   "cancelado": 3, "gratis": 4}},
            "plan_internet": {"param": "plan_internet", "tipo": "id",
                              "ayuda": "ID numerico del plan (hay 55 planes)."},
            "ciudad": {"param": "ciudad", "tipo": "texto"},
            "localidad": {"param": "localidad", "tipo": "texto"},
        },
        "agrupar_por": ["estado"],
        # Clientes NO tiene ningun filtro de fecha: su conteo es absoluto y no
        # depende de un periodo. Es la unica entidad de la que se puede decir
        # "hay N" sin fechar la afirmacion.
        "periodo": None,
        "no_soportado": {
            "zona": "El API de clientes ignora el filtro por zona. Las facturas "
                    "SI se pueden contar por zona.",
            "estado_facturas": "El API de clientes ignora este filtro. Para saber "
                               "quien debe, se cuentan facturas en estado "
                               "'pendiente' (cuenta facturas, no clientes).",
            "saldo": "El API de clientes ignora el filtro por saldo.",
            "periodo": "El API de clientes no filtra por fecha: no se pueden "
                       "contar altas de un mes.",
        },
    },
    "facturas": {
        "endpoint": EP_FACTURAS,
        "etiqueta": "facturas",
        # Verificado: 3606+5087+7 = 8700 = total. Y las 5 zonas suman 8700 exacto.
        "filtros": {
            "estado": {"param": "estado",
                       "valores": {"pendiente": 1, "pagada": 2, "cancelada": 3,
                                   "en_revision": 4, "transferida": 5}},
            "zona": {"param": "zona", "tipo": "id", "catalogo": "zonas"},
        },
        "agrupar_por": ["estado", "zona"],
        "periodo": {
            "campos": {"emision": "fecha_emision__range",
                       "vencimiento": "fecha_vencimiento__range",
                       "pago": "fecha_pago__range"},
            "por_defecto": "emision",
            "sufijos": ("_0", "_1"),
            "max_meses": 3,      # verificado: 4 meses -> HTTP 400 del API
            # Sin periodo explicito el API aplica el suyo. MEDIDO: el total base
            # (8700) es exactamente junio+julio 2026, o sea los ~2 ultimos meses,
            # no el historico. Por eso el periodo se declara SIEMPRE.
            # Dos textos y no uno: la 'nota' entra en la frase que describe la
            # consulta y debe ser corta; la 'advertencia' explica el riesgo.
            "nota_defecto": "periodo por defecto del API (~2 ultimos meses de emision)",
            "advertencia_defecto": (
                "Sin periodo explicito, el API cuenta solo sus ultimos ~2 meses "
                "de emision, no el historico completo."),
        },
        "no_soportado": {
            "cliente": "Para las facturas de UN cliente usa consultar_facturas, "
                       "no la consulta agregada.",
        },
    },
    "tickets": {
        "endpoint": EP_TICKETS,
        "etiqueta": "tickets",
        # Verificado: 266+18+2351 = 2635 = total devuelto sin filtro de fecha.
        "filtros": {
            "estado": {"param": "estado",
                       "valores": {"nuevo": 1, "en_progreso": 2, "cerrado": 4}},
        },
        "agrupar_por": ["estado"],
        "periodo": {
            # Tickets usa UN solo guion bajo: fecha_creacion_0/_1 (no '__range').
            "campos": {"creacion": "fecha_creacion"},
            "por_defecto": "creacion",
            "sufijos": ("_0", "_1"),
            "max_meses": 2,      # verificado: 3 meses -> HTTP 400 del API
            # CUIDADO. Aqui el default del API es engañoso de verdad: sin filtro
            # de fecha devuelve 2635, pero SOLO julio ya da 2637 y junio da 3341.
            # Un subconjunto no puede superar al conjunto: ese 2635 es un recorte
            # temporal propio del API, no el total historico de tickets.
            # Por eso un conteo de tickets sin periodo es un numero sin
            # significado, y la advertencia lo dice sin adornos.
            "nota_defecto": "sin periodo: recorte temporal propio del API, "
                            "no el historico",
            "advertencia_defecto": (
                "SIN PERIODO: el API aplica un recorte temporal propio. Este "
                "total NO es el historico y no sirve para comparar. Para un "
                "dato fiable hay que pedir un periodo explicito (max 2 meses)."),
        },
        "no_soportado": {
            "cliente": "El API de tickets no filtra por cliente. Para los tickets "
                       "de UN cliente usa consultar_tickets_de_cliente.",
            "tecnico": "El API de tickets ignora el filtro por tecnico.",
            "prioridad": "El API de tickets ignora el filtro por prioridad.",
            "departamento": "El API de tickets ignora el filtro por departamento.",
        },
    },
}

# Los nombres de zona se leen del API la primera vez y se recuerdan: son 5 y no
# cambian en una sesion. Sirven para agrupar y para poder decir "CORTE 30 -
# SERVIDOR 1" en vez de "zona 20049".
_CACHE_ZONAS = {}

def _zonas():
    """{id: nombre} de las zonas. Cachea; ante un fallo devuelve {} (no rompe)."""
    if _CACHE_ZONAS:
        return _CACHE_ZONAS
    if not USAR_WISPHUB_REAL:
        _CACHE_ZONAS.update({3: "NORTE", 4: "SUR"})
        return _CACHE_ZONAS
    try:
        r = requests.get(WISPHUB_BASE_URL + EP_ZONAS, headers=_headers(),
                         params={"limit": 100}, timeout=15)
        r.raise_for_status()
        payload = r.json()
        filas = payload.get("results", payload) if isinstance(payload, dict) else payload
        for z in filas or []:
            if isinstance(z, dict) and z.get("id") is not None:
                _CACHE_ZONAS[z["id"]] = z.get("nombre") or str(z["id"])
    except (requests.RequestException, ValueError):
        pass
    return _CACHE_ZONAS


AREAS = {
    "soporte": {
        "descripcion": "Soporte: atiende al cliente, revisa su estado y sus tickets.",
        "herramientas": ["consultar_cliente", "consultar_cliente_por_cedula",
                         "consultar_ticket", "consultar_tickets_de_cliente",
                         "consultar_agregado"],
        # Que entidades puede CONTAR el area. Es una segunda lista blanca: una
        # entidad ausente se rechaza aunque la herramienta este permitida.
        "agregados": ["tickets", "clientes"],
        "campos": {
            "consultar_cliente": (_CLIENTE_IDENTIDAD + _CLIENTE_CONTACTO +
                                  _CLIENTE_SERVICIO + _CLIENTE_PAGO),
            "consultar_ticket": _TICKET_BASE,
            "consultar_tickets_de_cliente": _TICKET_LISTA,
            "consultar_agregado": _AGREGADO,
        },
    },
    "tecnica": {
        "descripcion": "Tecnica: diagnostica la conectividad y el equipo del cliente.",
        "herramientas": ["consultar_cliente", "consultar_cliente_por_cedula",
                         "consultar_ticket", "consultar_tickets_de_cliente"],
        "campos": {
            # Unica area que ve datos de red. Sin contacto: para diagnosticar no
            # hace falta el telefono, y si hay que llamar al cliente lo hace
            # Soporte. Credenciales, ninguna (ver arriba).
            "consultar_cliente": (_CLIENTE_IDENTIDAD + _CLIENTE_SERVICIO +
                                  _CLIENTE_RED),
            "consultar_ticket": _TICKET_BASE + ["servicio.ip"],
            "consultar_tickets_de_cliente": _TICKET_LISTA,
        },
    },
    "facturacion": {
        "descripcion": "Facturacion: revisa facturas, saldos y registra pagos.",
        "herramientas": ["consultar_cliente", "consultar_cliente_por_cedula",
                         "consultar_facturas", "registrar_pago",
                         "consultar_agregado"],
        "agregados": ["facturas", "clientes"],
        "campos": {
            # Sin datos de red ni tickets: no hacen a su trabajo.
            "consultar_cliente": (_CLIENTE_IDENTIDAD + _CLIENTE_CONTACTO +
                                  _CLIENTE_PAGO + _CLIENTE_FINANCIERO +
                                  ["plan_internet"]),
            "consultar_facturas": _FACTURA,
            "registrar_pago": _PAGO_RESULTADO,
            "consultar_agregado": _AGREGADO,
        },
    },
    "administracion": {
        "descripcion": "Administracion: consulta consolidada, sin datos personales.",
        "herramientas": ["consultar_cliente", "consultar_cliente_por_cedula",
                         "consultar_tickets_de_cliente", "consultar_agregado"],
        # Es la unica area que puede contar las tres entidades: su trabajo son
        # los consolidados, y un agregado no expone a ningun cliente concreto.
        "agregados": ["clientes", "facturas", "tickets"],
        "campos": {
            # Sin PII: ni cedula, ni contacto. Ve el estado y el servicio.
            "consultar_cliente": (["id_servicio", "nombre", "estado"] +
                                  _CLIENTE_SERVICIO + ["estado_facturas"]),
            "consultar_tickets_de_cliente": _TICKET_LISTA,
            "consultar_agregado": _AGREGADO,
        },
    },
}

# Las dos consultas de cliente devuelven la misma forma: comparten campos.
for _area in AREAS.values():
    if "consultar_cliente" in _area["campos"]:
        _area["campos"]["consultar_cliente_por_cedula"] = _area["campos"]["consultar_cliente"]

AREA_POR_DEFECTO = "soporte"

def area_valida(area):
    return (area or "").strip().lower() in AREAS

def campos_de(area, herramienta):
    """Lista blanca de esa herramienta PARA ESA AREA. None si no le corresponde."""
    return AREAS.get(area, {}).get("campos", {}).get(herramienta)

def herramientas_de(area):
    """Definiciones de las herramientas que el area puede usar."""
    permitidas = AREAS.get(area, {}).get("herramientas", [])
    return [h for h in HERRAMIENTAS if h["function"]["name"] in permitidas]

def agregados_de(area):
    """Entidades que ESA AREA puede contar. Vacio = ninguna (fail-closed)."""
    return AREAS.get(area, {}).get("agregados", [])

def _compilar_permitidos(permitidos):
    """Separa la lista blanca en campos de primer nivel y campos anidados."""
    top, anidados = set(), {}
    for campo in permitidos:
        if "." in campo:
            padre, hijo = campo.split(".", 1)
            anidados.setdefault(padre, set()).add(hijo)
        else:
            top.add(campo)
    return top, anidados

def _solo_permitidos(permitidos, dato):
    """
    Aplica la lista blanca a un dict suelto.

    Soporta notacion con punto ('servicio.id_servicio') para filtrar DENTRO de un
    objeto anidado. Es imprescindible: el 'servicio' que viene dentro de un ticket
    incluye la IP del cliente y el router con sus credenciales. Dejar pasar el
    objeto entero porque su nombre esta en la lista blanca seria una fuga.
    Un objeto anidado solo se entrega completo si se lo nombra sin punto, y eso
    debe reservarse a objetos inofensivos (plan_internet, zona).
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

def _empaquetar_lista(permitidos, filas, total):
    """
    Normaliza una lista a {total, resultados}, filtrando cada fila.

    'total' es el count REAL que reporta el API, no el numero de filas traidas.
    Si se trajo menos que el total (paginacion), se avisa de forma EXPLICITA:
    un conteo hecho sobre una pagina incompleta es una respuesta incorrecta que
    no se nota. Que el modelo lo vea escrito es preferible a que lo ignore.
    """
    filtradas = [_solo_permitidos(permitidos, f) for f in filas]
    paquete = {"total": total, "resultados": filtradas}
    if total > len(filtradas):
        paquete["aviso"] = (
            f"Resultado PARCIAL: se muestran {len(filtradas)} de {total} registros. "
            f"No cuentes sobre esta lista; el total real es {total}."
        )
    return paquete

def filtrar_campos(nombre, datos, area=AREA_POR_DEFECTO):
    """
    Deja solo los campos que ESA AREA puede ver. Descarta IP, MAC, passwords...

    Maneja las tres formas en que responde WispHub:
      - dict suelto            -> {"campo": valor, ...}
      - lista                  -> [ {...}, {...} ]
      - paginado estilo DRF    -> {"count": N, "results": [ {...} ]}

    Las dos ultimas se normalizan a {"total": N, "resultados": [...]} para que
    el modelo siempre reciba la misma forma.

    IMPORTANTE (fail-closed): si esa area no tiene lista blanca para esa
    herramienta, NO se deja pasar nada. Vale tanto para una herramienta nueva sin
    configurar como para un area que no deberia estar consultando eso.
    """
    permitidos = campos_de(area, nombre)
    if permitidos is None:
        return {"error": f"El area '{area}' no tiene permitido consultar "
                         f"'{nombre}'. Resultado descartado."}
    permitidos = set(permitidos)

    # Los errores propios del codigo pasan tal cual (no traen datos del cliente).
    if isinstance(datos, dict) and "error" in datos:
        return {"error": datos["error"]}

    if isinstance(datos, list):
        return _empaquetar_lista(permitidos, datos, len(datos))

    if isinstance(datos, dict):
        if isinstance(datos.get("results"), list):
            paquete = _empaquetar_lista(permitidos, datos["results"],
                                        datos.get("count", len(datos["results"])))
            # Estas claves las pone NUESTRO codigo, no el API: el alcance de la
            # busqueda y los totales ya calculados. Se dejan pasar para que el
            # modelo los repita en vez de deducirlos contando filas.
            for clave in ("alcance", "por_estado"):
                if clave in datos:
                    paquete[clave] = datos[clave]
            return paquete
        return _solo_permitidos(permitidos, datos)

    return {"error": "Formato de respuesta no reconocido. Resultado descartado."}


# ==============================================================================
#  AUDITORIA  —  quien consulto que, sin volcar datos sensibles
# ==============================================================================
# RF-13. Registra cada ACCESO A DATOS (una linea JSON por ejecucion de
# herramienta), no la conversacion. Lo que se guarda es el hecho de la consulta:
# area, herramienta, a que registro y con que resultado. NUNCA el dato devuelto.
#
# Un log de auditoria que copia los datos que vigila deja de ser un control y
# pasa a ser una segunda base de datos sin proteger.

ARCHIVO_AUDITORIA = os.environ.get("ARCHIVO_AUDITORIA", "auditoria.log")
AUDITORIA_ACTIVA = _env_bool("AUDITORIA_ACTIVA", True)

# Enmascara identificadores largos: cedulas (8-10 digitos) y telefonos quedan
# ocultos; los IDs cortos (servicio 4, ticket 5, factura 6) se conservan porque
# son los que hacen util la auditoria y no identifican a una persona por si solos.
_RE_ID_LARGO = re.compile(r"\d{8,}")

def _enmascarar(texto):
    return _RE_ID_LARGO.sub(lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:],
                            str(texto))

def registrar_auditoria(area, herramienta, args, estado, registros=None, ms=None):
    """Agrega una linea al log. Nunca interrumpe la atencion si falla."""
    if not AUDITORIA_ACTIVA:
        return
    entrada = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "area": area,
        "herramienta": herramienta,
        "args": {k: _enmascarar(v) for k, v in (args or {}).items() if v not in (None, "")},
        "estado": estado,
        "sensible": herramienta in ACCIONES_SENSIBLES,
    }
    if registros is not None:
        entrada["registros"] = registros
    if ms is not None:
        entrada["ms"] = ms
    try:
        with open(ARCHIVO_AUDITORIA, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except OSError as e:
        # Que no se pueda auditar no debe dejar sin servicio al colaborador,
        # pero tiene que verse: se avisa en pantalla en vez de fallar en silencio.
        print(f"     [aviso] no se pudo escribir la auditoria: {e}")

def _cuantos_registros(salida):
    """Cuantos registros devolvio la consulta (para el log, no el contenido)."""
    if isinstance(salida, dict):
        if "total" in salida:
            return salida["total"]
        if "error" in salida:
            return 0
        return 1
    return None


# ==============================================================================
#  1) DEFINICION DE LAS HERRAMIENTAS
# ==============================================================================

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "consultar_cliente",
        "description": "Obtiene los datos y el estado de un cliente por su ID de servicio.",
        "parameters": {"type": "object", "properties": {
            "id_cliente": {"type": "string", "description": "ID de servicio del cliente."}
        }, "required": ["id_cliente"]}}},
    {"type": "function", "function": {
        "name": "consultar_cliente_por_cedula",
        "description": ("Busca un cliente por su numero de cedula (documento de identidad) "
                        "y devuelve sus datos y estado. Usar cuando el asesor da la cedula "
                        "en vez del ID de servicio."),
        "parameters": {"type": "object", "properties": {
            "cedula": {"type": "string", "description": "Numero de cedula del cliente."}
        }, "required": ["cedula"]}}},
    {"type": "function", "function": {
        "name": "consultar_facturas",
        "description": "Devuelve las facturas de un cliente y si estan pagadas o pendientes.",
        "parameters": {"type": "object", "properties": {
            "id_cliente": {"type": "string", "description": "ID de servicio del cliente."}
        }, "required": ["id_cliente"]}}},
    {"type": "function", "function": {
        "name": "consultar_ticket",
        "description": "Consulta el estado de un ticket de soporte tecnico por su numero.",
        "parameters": {"type": "object", "properties": {
            "id_ticket": {"type": "string", "description": "Numero del ticket."}
        }, "required": ["id_ticket"]}}},
    {"type": "function", "function": {
        "name": "consultar_tickets_de_cliente",
        "description": ("Lista los tickets de soporte ABIERTOS (Nuevo o En Progreso) de un "
                        "cliente. Usar cuando el asesor pregunte si un cliente tiene tickets, "
                        "reportes o casos abiertos. Acepta el ID de servicio o la cedula: "
                        "basta con uno de los dos. No incluye tickets cerrados."),
        "parameters": {"type": "object", "properties": {
            "id_cliente": {"type": "string", "description": "ID de servicio del cliente."},
            "cedula": {"type": "string", "description": "Cedula del cliente."}
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "consultar_agregado",
        "description": (
            "CUENTA cuantos registros cumplen unas condiciones. Usar para preguntas "
            "de CUANTOS, totales, o comparaciones entre grupos. NO sirve para "
            "consultar un cliente concreto. "
            "Ejemplos: 'cuantos clientes suspendidos hay' -> entidad=clientes, "
            "filtros={estado:suspendido}. 'cuantas facturas pendientes por zona' -> "
            "entidad=facturas, filtros={estado:pendiente}, agrupar_por=zona. "
            "IMPORTANTE: no calcules tu el resultado, la herramienta ya devuelve "
            "el numero contado."),
        "parameters": {"type": "object", "properties": {
            "entidad": {"type": "string", "enum": ["clientes", "facturas", "tickets"],
                        "description": "Que se cuenta."},
            "filtros": {"type": "object", "description": (
                "Condiciones. clientes: estado (activo|suspendido|cancelado|gratis), "
                "plan_internet, ciudad, localidad. facturas: estado "
                "(pendiente|pagada|cancelada), zona. tickets: estado "
                "(nuevo|en_progreso|cerrado).")},
            "agrupar_por": {"type": "string", "description": (
                "Opcional. Devuelve el conteo desglosado por este campo: 'estado' "
                "en cualquier entidad, o 'zona' en facturas.")},
            "periodo": {"type": "string", "description": (
                "Opcional, solo facturas y tickets. Un mes 'AAAA-MM' o un rango "
                "'AAAA-MM-DD a AAAA-MM-DD'. Facturas admite hasta 3 meses; "
                "tickets hasta 2.")},
        }, "required": ["entidad"]}}},
    {"type": "function", "function": {
        "name": "registrar_pago",
        "description": "Registra un pago sobre una factura. ACCION SENSIBLE: requiere confirmacion.",
        "parameters": {"type": "object", "properties": {
            "id_factura": {"type": "string", "description": "ID de la factura."},
            "monto": {"type": "number", "description": "Monto del pago."}
        }, "required": ["id_factura", "monto"]}}},
]


# ==============================================================================
#  2) CAPA DE VALIDACION
# ==============================================================================

def _limpiar_cedula(valor):
    """Quita los separadores con que suele escribirse una cedula (1.098.765.432)."""
    cedula = str(valor or "").strip()
    for sobra in (".", " ", "-"):
        cedula = cedula.replace(sobra, "")
    return cedula

def _ultimo_dia(anio, mes):
    return calendar.monthrange(anio, mes)[1]

def _parsear_periodo(texto, max_meses):
    """
    Acepta 'AAAA-MM' (mes completo) o 'AAAA-MM-DD a AAAA-MM-DD'.

    Devuelve (ok, (desde, hasta)) o (False, motivo).

    La amplitud se valida AQUI y no se delega al API: el API la rechaza con un
    HTTP 400 que el asesor veria como 'fallo al llamar a WispHub'. Verificado en
    produccion: facturas corta en 3 meses, tickets en 2.
    """
    texto = str(texto or "").strip()
    if not texto:
        return False, "Periodo vacio."

    if re.fullmatch(r"\d{4}-\d{2}", texto):          # un mes completo
        anio, mes = int(texto[:4]), int(texto[5:7])
        if not 1 <= mes <= 12:
            return False, f"Mes invalido en '{texto}'."
        desde = f"{anio:04d}-{mes:02d}-01"
        hasta = f"{anio:04d}-{mes:02d}-{_ultimo_dia(anio, mes):02d}"
    else:
        partes = re.split(r"\s+a\s+|\.\.|\s+hasta\s+", texto)
        if len(partes) != 2:
            return False, (f"No entiendo el periodo '{texto}'. Usa 'AAAA-MM' "
                           f"o 'AAAA-MM-DD a AAAA-MM-DD'.")
        desde, hasta = partes[0].strip(), partes[1].strip()

    for f in (desde, hasta):
        if not _FECHA_ISO.match(f):
            return False, f"La fecha '{f}' no tiene el formato AAAA-MM-DD."
    try:
        d0 = datetime.strptime(desde, "%Y-%m-%d")
        d1 = datetime.strptime(hasta, "%Y-%m-%d")
    except ValueError:
        return False, f"Fecha inexistente en el periodo '{texto}'."
    if d1 < d0:
        return False, f"El periodo empieza despues de terminar ({desde} a {hasta})."

    # Se topa en dias porque el limite real del API es por amplitud, no por mes
    # calendario. Verificado: 92 dias pasa en facturas, 122 no.
    if (d1 - d0).days > max_meses * 31:
        return False, (f"El periodo {desde} a {hasta} es demasiado amplio: "
                       f"el API no acepta mas de {max_meses} meses por consulta.")
    return True, (desde, hasta)


def _validar_agregado(args):
    """
    Traduce la consulta que propuso el modelo a algo ejecutable, o la rechaza.

    Esta es la lista blanca de PRD 12.5 regla 3, aplicada a la forma de la
    consulta: que se puede filtrar, por que se puede agrupar y con que rango.
    Un filtro que el API ignora no se 'intenta igual': se rechaza con el motivo,
    porque intentarlo devolveria el universo entero como si fuera la respuesta.
    """
    entidad = str(args.get("entidad") or "").strip().lower()
    if entidad not in AGREGACIONES:
        return False, (f"No se puede contar '{entidad}'. Entidades disponibles: "
                       f"{', '.join(AGREGACIONES)}.")
    cfg = AGREGACIONES[entidad]

    # --- filtros ---
    crudos = args.get("filtros") or {}
    if isinstance(crudos, str):
        try:
            crudos = json.loads(crudos)
        except ValueError:
            return False, "El campo 'filtros' no es un objeto valido."
    if not isinstance(crudos, dict):
        return False, "El campo 'filtros' debe ser un objeto."

    filtros = {}
    for clave, valor in crudos.items():
        clave = str(clave).strip().lower()
        if valor in (None, ""):
            continue
        if clave in cfg.get("no_soportado", {}):
            return False, cfg["no_soportado"][clave]
        if clave not in cfg["filtros"]:
            return False, (f"No se puede filtrar {entidad} por '{clave}'. "
                           f"Disponibles: {', '.join(cfg['filtros'])}.")
        spec = cfg["filtros"][clave]
        if "valores" in spec:
            v = str(valor).strip().lower().replace(" ", "_")
            if v not in spec["valores"]:
                return False, (f"'{valor}' no es un valor de {clave} para "
                               f"{entidad}. Validos: {', '.join(spec['valores'])}.")
            filtros[clave] = v
        elif spec.get("tipo") == "id":
            if not str(valor).strip().isdigit():
                return False, (f"El filtro '{clave}' espera un ID numerico, "
                               f"no '{valor}'.")
            filtros[clave] = int(valor)
        else:
            filtros[clave] = str(valor).strip()

    # --- agrupacion ---
    agrupar = str(args.get("agrupar_por") or "").strip().lower() or None
    if agrupar and agrupar not in cfg["agrupar_por"]:
        return False, (f"No se puede agrupar {entidad} por '{agrupar}'. "
                       f"Disponibles: {', '.join(cfg['agrupar_por']) or 'ninguno'}.")
    # Agrupar por un campo que YA se esta filtrando es una contradiccion, y de las
    # peligrosas: el desglose recorre todos los valores de ese campo y sobreescribe
    # el filtro, asi que el numero saldria del universo completo mientras la
    # interpretacion seguiria anunciando el filtro. Un total exacto respondiendo
    # otra pregunta es peor que un error, por eso se rechaza en vez de corregirse
    # en silencio: el modelo pidio dos cosas incompatibles y debe elegir una.
    if agrupar and agrupar in filtros:
        return False, (f"No se puede filtrar {entidad} por {agrupar}='{filtros[agrupar]}' "
                       f"y a la vez desglosar por {agrupar}. Elige una: o el conteo "
                       f"de ese valor, o el desglose de todos.")

    # --- periodo ---
    periodo = None
    pedido = args.get("periodo")
    if pedido:
        if not cfg.get("periodo"):
            return False, cfg.get("no_soportado", {}).get(
                "periodo", f"Las {entidad} no se pueden filtrar por fecha.")
        ok, resultado = _parsear_periodo(pedido, cfg["periodo"]["max_meses"])
        if not ok:
            return False, resultado
        periodo = resultado

    return True, {"entidad": entidad, "filtros": filtros,
                  "agrupar_por": agrupar,
                  "periodo": f"{periodo[0]}..{periodo[1]}" if periodo else ""}


def validar_argumentos(nombre, args):
    if nombre in ("consultar_cliente", "consultar_facturas"):
        idc = str(args.get("id_cliente", "")).strip()
        if not idc:
            return False, "Falta el ID de servicio del cliente."
        return True, {"id_cliente": idc}
    if nombre == "consultar_cliente_por_cedula":
        cedula = _limpiar_cedula(args.get("cedula"))
        if not cedula:
            return False, "Falta el numero de cedula."
        if not cedula.isdigit() or len(cedula) > 15:
            return False, "La cedula no es un numero valido."
        return True, {"cedula": cedula}
    if nombre == "consultar_ticket":
        idt = str(args.get("id_ticket", "")).strip()
        if not idt:
            return False, "Falta el numero de ticket."
        return True, {"id_ticket": idt}
    if nombre == "consultar_tickets_de_cliente":
        # Acepta ID de servicio O cedula. Resolver la cedula aqui, en codigo,
        # evita que el modelo tenga que encadenar dos herramientas: hoy
        # responder() ejecuta una sola ronda por turno (ver PRD 12.3).
        idc = str(args.get("id_cliente") or "").strip()
        cedula = _limpiar_cedula(args.get("cedula"))
        if not idc and not cedula:
            return False, "Falta el ID de servicio o la cedula del cliente."
        if cedula and not cedula.isdigit():
            return False, "La cedula no es un numero valido."
        return True, {"id_cliente": idc, "cedula": cedula}
    if nombre == "consultar_agregado":
        return _validar_agregado(args)
    if nombre == "registrar_pago":
        idf = str(args.get("id_factura", "")).strip()
        try:
            monto = float(args.get("monto", 0))
        except (TypeError, ValueError):
            return False, "El monto no es un numero valido."
        if not idf or monto <= 0:
            return False, "Datos de pago invalidos (factura o monto)."
        return True, {"id_factura": idf, "monto": monto}
    return False, f"Herramienta desconocida: {nombre}"


# ==============================================================================
#  3) EJECUCION (simulada o real)
# ==============================================================================

# Los datos simulados replican los NOMBRES DE CAMPO reales de WispHub (incluidos
# los sensibles, para que el filtro se ejerza igual que en produccion). Si la
# forma simulada y la real divergen, lo que funciona en pruebas falla en vivo.
_SIMULADO = {
    "clientes": {
        "7001": {"id_servicio": "7001", "usuario": "maria-gomez@empresa-demo",
                 "nombre": "MARIA GOMEZ", "cedula": "1098765432",
                 "estado": "Activo", "estado_facturas": "Pagadas",
                 "saldo": "0.00", "fecha_corte": "6/08/2026",
                 "fecha_instalacion": "27/07/2026 12:30:00",
                 "plan_internet": {"id": 1, "nombre": "PLAN HOGAR"},
                 "zona": {"id": 3, "nombre": "NORTE"},
                 "ip": "10.0.0.5", "mac_cpe": "AA:BB:CC",
                 "password_cpe": "secreta", "telefono": "3000000000"},
    },
    "facturas": {
        "7001": [{"id_factura": "142573", "estado": "Pendiente de Pago",
                  "total": "30290.0", "saldo": "0.0",
                  "fecha_emision": "2026-07-25", "fecha_vencimiento": "2026-08-06",
                  "fecha_pago": None,
                  "cliente": {"usuario": "maria-gomez@empresa-demo",
                              "nombre": "MARIA GOMEZ", "cedula": "1098765432",
                              "telefono": "3000000000"}}],
    },
    "tickets": {
        "88754": {"id_ticket": "88754", "asunto": "Sin servicio de internet",
                  "descripcion": "El cliente reporta que no navega desde ayer.",
                  "razon_falla": "", "estado": "Nuevo", "prioridad": "Normal",
                  "tecnico": "Rapilink SAS", "email_tecnico": "tecnico@empresa-demo",
                  "departamento": "Soporte", "origen_reporte": "Portal Cliente",
                  "fecha_creacion": "2026-07-28T16:25:24-05:00",
                  "fecha_inicio": None, "fecha_fin": None,
                  "creado_por": "admin@empresa-demo",
                  "tickets_mensual": 198, "tickets_anual": 1576,
                  # 'servicio' anidado, tal como lo devuelve el API: con IP y router
                  "servicio": {"id_servicio": "7001", "ip": "10.0.0.5",
                               "comentarios": "", "fecha_instalacion": "10/03/2023",
                               "plan_internet": {"id": 1, "nombre": "PLAN HOGAR"},
                               "zona": {"id": 3, "nombre": "NORTE"},
                               "router": {"id": 9, "nombre": "RB-1",
                                          "password": "secreta"}}},
    },
}

def _primer_resultado(payload, vacio="No se encontro ningun cliente."):
    """
    El endpoint de busqueda devuelve un paginado {count, next, previous, results}.
    Nos quedamos con el primer registro encontrado.
    """
    if isinstance(payload, list):
        elementos = payload
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        elementos = payload["results"]
    elif isinstance(payload, dict):
        return payload
    else:
        elementos = []
    if not elementos:
        return {"error": vacio}
    return elementos[0]

def _buscar_cliente(filtro, valor):
    """Consulta /api/clientes/ con un filtro exacto ('cedula' o 'id_servicio')."""
    r = requests.get(WISPHUB_BASE_URL + EP_CLIENTES, headers=_headers(),
                     params={filtro: valor, "limit": 1}, timeout=15)
    r.raise_for_status()
    return _primer_resultado(
        r.json(), vacio=f"No se encontro ningun cliente con {filtro} {valor}.")

def _facturas_de_cliente(cliente):
    """
    Trae las facturas de UN cliente.

    OJO: el filtro del API es ?cliente=<usuario>, donde 'usuario' es el
    identificador interno (formato nombre@empresa), NO el id de servicio.
    Pasarle el id devuelve count=0 en silencio -> el asistente diria "no tiene
    facturas" para TODOS los clientes. Y un parametro mal escrito es peor: el API
    lo ignora y devuelve las 8.700 facturas de la empresa, que el modelo
    resumiria como si fueran de este cliente.
    Por eso, ademas de usar el filtro correcto, se VERIFICA la respuesta.

    El API filtra por defecto los ultimos 3 meses de fecha de emision.
    """
    usuario = cliente.get("usuario")
    if not usuario:
        return {"error": "El cliente no tiene usuario asociado; no se pueden consultar sus facturas."}

    r = requests.get(WISPHUB_BASE_URL + EP_FACTURAS, headers=_headers(),
                     params={"cliente": usuario, "limit": LIMITE_FILAS}, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict):
        filas = payload.get("results", [])
        total = payload.get("count", len(filas))
    else:
        filas, total = payload, len(payload or [])
    if not isinstance(filas, list):
        return {"error": "Respuesta inesperada del listado de facturas."}

    # Red de seguridad: si el filtro no se aplico, las filas serian de otros
    # clientes. Antes de entregar un dato equivocado, se devuelve un error.
    ajenas = [f for f in filas
              if isinstance(f.get("cliente"), dict)
              and f["cliente"].get("usuario") not in (None, usuario)]
    if ajenas:
        return {"error": "El filtro por cliente no se aplico correctamente; "
                         "consulta descartada por seguridad."}

    # Se devuelve la forma paginada para que el 'count' REAL del API llegue al
    # filtro. Si se devolviera solo la lista, el total seria el de la pagina.
    return {"count": total, "results": filas}

def _tickets_de_cliente(id_servicio):
    """
    Tickets ABIERTOS de un cliente.

    El API de tickets NO tiene filtro por cliente: probados 8 nombres de
    parametro (servicio, cliente, id_servicio, usuario, search...), todos son
    ignorados y devuelven los 2.536 tickets de la empresa. Tampoco el cliente
    expone sus tickets (ni /clientes/{id}/ ni /clientes/{id}/perfil/).

    Asi que se filtra por estado en el API -unico filtro que si funciona- y el
    cruce por cliente se hace AQUI, en codigo. Solo se barren los estados
    abiertos (~280 tickets, 3 paginas): los 2.255 cerrados serian ~23 paginas
    y no valen una consulta interactiva.

    NO se sigue el campo 'next' del paginado: el API lo devuelve en http://
    (verificado: 'http://api.wisphub.io/api/tickets/?...'). Seguirlo mandaria la
    clave del API en texto plano. Se pagina con offset propio, sobre HTTPS.
    """
    encontrados, barridos = [], 0
    url = WISPHUB_BASE_URL + EP_TICKETS
    for estado in ESTADOS_ABIERTOS:
        offset = 0
        for _ in range(MAX_PAGINAS):
            r = requests.get(url, headers=_headers(), timeout=25,
                             params={"estado": estado, "limit": 100, "offset": offset})
            r.raise_for_status()
            pagina = r.json()
            filas = pagina.get("results") or []
            barridos += len(filas)
            encontrados += [
                f for f in filas
                if str((f.get("servicio") or {}).get("id_servicio")) == str(id_servicio)
            ]
            offset += len(filas)
            if not filas or offset >= pagina.get("count", 0):
                break

    # Mas recientes primero: si hay que recortar, que sobrevivan los utiles.
    encontrados.sort(key=lambda f: str(f.get("fecha_creacion") or ""), reverse=True)

    # 'count' es el total real encontrado; se entregan como mucho LIMITE_FILAS.
    # El filtro avisa solo si recorto (ver _empaquetar_lista).
    # El desglose se calcula AQUI, no se le pide al modelo que cuente filas.
    por_estado = {}
    for f in encontrados:
        clave = str(f.get("estado") or "sin estado")
        por_estado[clave] = por_estado.get(clave, 0) + 1

    abiertos = ", ".join(ESTADOS_TICKET[e] for e in ESTADOS_ABIERTOS)
    return {
        "count": len(encontrados),
        "por_estado": por_estado,
        "results": encontrados[:TOPE_TICKETS_LISTA],
        # Se declara el alcance de la busqueda: una respuesta correcta sobre una
        # pregunta mal entendida es el error mas dificil de detectar (RF-15).
        "alcance": (f"Solo tickets abiertos ({abiertos}); los cerrados no se "
                    f"consultaron. Se revisaron {barridos} tickets."),
    }

# ==============================================================================
#  MOTOR DE AGREGACION  —  el modelo compone, ESTE codigo calcula (PRD 12.5)
# ==============================================================================

def _contar(endpoint, params):
    """
    Cuantos registros cumplen 'params'. UNA llamada, CERO filas.

    El paginado del API ya trae el total en 'count': se pide limit=1 y se lee ese
    numero. Contar 8.700 facturas cuesta lo mismo que contar 3, y el modelo no ve
    ni una fila. Pedirle a un SLM que cuente 8.700 filas no es lento: es imposible.
    """
    p = dict(params)
    p["limit"] = 1
    r = requests.get(WISPHUB_BASE_URL + endpoint, headers=_headers(),
                     params=p, timeout=30)
    if r.status_code == 400:
        # El API explica bien sus rechazos (rango muy amplio, formato de fecha).
        # Se propaga ese motivo en vez de un generico: el asesor puede corregir.
        try:
            motivo = r.json().get("error") or r.text[:120]
        except ValueError:
            motivo = r.text[:120]
        raise ValueError(f"WispHub rechazo la consulta: {motivo}")
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload, dict) and "count" in payload:
        return payload["count"]
    if isinstance(payload, list):
        return len(payload)
    raise ValueError("El API no devolvio un conteo reconocible.")


def _params_de(cfg, filtros, periodo):
    """Traduce los filtros del catalogo a parametros reales del API."""
    params = {}
    for clave, valor in filtros.items():
        spec = cfg["filtros"][clave]
        params[spec["param"]] = spec["valores"][valor] if "valores" in spec else valor
    if periodo and cfg.get("periodo"):
        desde, hasta = periodo.split("..")
        p = cfg["periodo"]
        base = p["campos"][p["por_defecto"]]
        s0, s1 = p["sufijos"]
        params[base + s0] = desde
        params[base + s1] = hasta
    return params


def _describir(cfg, entidad, filtros, periodo):
    """
    Redacta EN CODIGO como se interpreto la pregunta (RF-15).

    No se le pide al modelo que describa su propia consulta: describiria lo que
    creyo pedir, no lo que se ejecuto. Esta frase se arma con los filtros que de
    verdad se enviaron al API.
    """
    partes = []
    for clave, valor in filtros.items():
        if clave == "zona":
            partes.append(f"zona {_zonas().get(valor, valor)}")
        else:
            partes.append(f"{clave} '{valor}'")
    texto = f"{cfg['etiqueta'].capitalize()}"
    if partes:
        texto += " con " + ", ".join(partes)
    else:
        texto += " (sin filtros)"

    if periodo:
        desde, hasta = periodo.split("..")
        campo = cfg["periodo"]["por_defecto"]
        texto += f", por fecha de {campo} entre {desde} y {hasta}"
    elif cfg.get("periodo"):
        texto += f", {cfg['periodo']['nota_defecto']}"
    return texto + "."


def _valores_para_agrupar(cfg, campo):
    """Los valores por los que se va a agrupar: (clave_api, etiqueta legible)."""
    if campo == "zona":
        return [(zid, nombre) for zid, nombre in _zonas().items()]
    spec = cfg["filtros"][campo]
    return [(num, nom) for nom, num in spec["valores"].items()]


def consultar_agregado(entidad, filtros, agrupar_por, periodo):
    """
    Cuenta registros. Devuelve numeros ya calculados, nunca filas.

    Sin agrupacion: una llamada. Con agrupacion: una por valor del grupo (3-5),
    y el total es la SUMA que hace Python, no una cuenta que hace el modelo.
    """
    cfg = AGREGACIONES[entidad]
    base = _params_de(cfg, filtros, periodo)
    interpretacion = _describir(cfg, entidad, filtros, periodo)

    # Avisos que el asesor necesita para juzgar si el numero responde su pregunta.
    avisos = []
    if not periodo and cfg.get("periodo"):
        avisos.append(cfg["periodo"]["advertencia_defecto"])
    if entidad == "facturas" and filtros.get("estado") == "pendiente":
        # El error mas probable de esta herramienta, y el mas dificil de notar.
        avisos.append("Cuenta FACTURAS pendientes, no clientes morosos: un "
                      "cliente con varias facturas vencidas cuenta varias veces.")
    if any(AGREGACIONES[entidad]["filtros"].get(k, {}).get("tipo") == "texto"
           for k in filtros):
        avisos.append("Los filtros de texto (ciudad, localidad) se escriben libre "
                      "en WispHub y admiten variantes: 'SABANAGRANDE' y 'SABANA "
                      "GRANDE' son registros distintos.")

    if not agrupar_por:
        total = _contar(cfg["endpoint"], base)
        salida = {"total": total, "interpretacion": interpretacion}
        if avisos:
            salida["advertencia"] = " ".join(avisos)
        return salida

    valores = _valores_para_agrupar(cfg, agrupar_por)
    if len(valores) > TOPE_GRUPOS:
        return {"error": f"Agrupar por '{agrupar_por}' daria {len(valores)} grupos "
                         f"y el tope es {TOPE_GRUPOS}. Consulta un valor concreto."}

    desglose = {}
    for clave_api, etiqueta in valores:
        params = dict(base)
        params[cfg["filtros"].get(agrupar_por, {}).get("param", agrupar_por)] = clave_api
        desglose[str(etiqueta)] = _contar(cfg["endpoint"], params)

    # El total lo SUMA Python. Que lo sume el modelo es exactamente lo que
    # prohibe la regla 1 de PRD 12.5.
    salida = {
        "total": sum(desglose.values()),
        "desglose": desglose,
        "interpretacion": f"{interpretacion[:-1]}, desglosado por {agrupar_por}.",
    }
    if avisos:
        salida["advertencia"] = " ".join(avisos)
    return salida


def ejecutar_herramienta(nombre, args):
    """Devuelve la respuesta CRUDA (sin filtrar todavia)."""
    if not USAR_WISPHUB_REAL:
        if nombre == "consultar_cliente":
            return _SIMULADO["clientes"].get(args["id_cliente"], {"error": "Cliente no encontrado"})
        if nombre == "consultar_cliente_por_cedula":
            for cliente in _SIMULADO["clientes"].values():
                if cliente.get("cedula") == args["cedula"]:
                    return cliente
            return {"error": "No se encontro ningun cliente con esa cedula."}
        if nombre == "consultar_facturas":
            return _SIMULADO["facturas"].get(args["id_cliente"], [])
        if nombre == "consultar_ticket":
            return _SIMULADO["tickets"].get(args["id_ticket"], {"error": "Ticket no encontrado"})
        if nombre == "consultar_tickets_de_cliente":
            idc = args["id_cliente"]
            if not idc:
                for c in _SIMULADO["clientes"].values():
                    if c.get("cedula") == args["cedula"]:
                        idc = c["id_servicio"]
            propios = [t for t in _SIMULADO["tickets"].values()
                       if str((t.get("servicio") or {}).get("id_servicio")) == str(idc)]
            return {"count": len(propios), "results": propios,
                    "alcance": "Solo tickets abiertos (simulado)."}
        if nombre == "consultar_agregado":
            # Conteos fijos, con la MISMA forma que la ruta real (incluidas la
            # interpretacion y la advertencia): si divergen, lo que se prueba
            # aqui no es lo que corre en produccion.
            cfg = AGREGACIONES[args["entidad"]]
            fijos = {"clientes": 7252, "facturas": 8700, "tickets": 2635}
            interpretacion = _describir(cfg, args["entidad"],
                                        args["filtros"], args["periodo"])
            if args["agrupar_por"]:
                valores = _valores_para_agrupar(cfg, args["agrupar_por"])
                desglose = {str(et): (i + 1) * 100 for i, (_, et) in enumerate(valores)}
                return {"total": sum(desglose.values()), "desglose": desglose,
                        "interpretacion": f"{interpretacion[:-1]}, desglosado por "
                                          f"{args['agrupar_por']} (simulado).",
                        "advertencia": "Datos simulados."}
            return {"total": fijos[args["entidad"]],
                    "interpretacion": interpretacion,
                    "advertencia": "Datos simulados."}
        if nombre == "registrar_pago":
            return {"resultado": "ok", "id_factura": args["id_factura"],
                    "total_cobrado": args["monto"],
                    "mensajes": ["Pago registrado (simulado)"]}
        return {"error": "herramienta desconocida"}

    try:
        if nombre == "consultar_cliente":
            return _buscar_cliente("id_servicio", args["id_cliente"])

        if nombre == "consultar_cliente_por_cedula":
            return _buscar_cliente("cedula", args["cedula"])

        if nombre == "consultar_facturas":
            cliente = _buscar_cliente("id_servicio", args["id_cliente"])
            if "error" in cliente:
                return cliente
            return _facturas_de_cliente(cliente)

        if nombre == "consultar_tickets_de_cliente":
            if args["id_cliente"]:
                cliente = _buscar_cliente("id_servicio", args["id_cliente"])
            else:
                cliente = _buscar_cliente("cedula", args["cedula"])
            if "error" in cliente:
                return cliente
            return _tickets_de_cliente(cliente["id_servicio"])

        if nombre == "consultar_agregado":
            return consultar_agregado(args["entidad"], args["filtros"],
                                      args["agrupar_por"], args["periodo"])

        if nombre == "consultar_ticket":
            url = WISPHUB_BASE_URL + EP_TICKET.format(id=args["id_ticket"])
            r = requests.get(url, headers=_headers(), timeout=15)

        elif nombre == "registrar_pago":
            url = WISPHUB_BASE_URL + EP_PAGO.format(id=args["id_factura"])
            r = requests.post(url, headers=_headers(),
                              json={"total_cobrado": args["monto"],
                                    "accion": ACCION_PAGO}, timeout=15)
        else:
            return {"error": "herramienta desconocida"}

        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {"error": f"Fallo al llamar a WispHub: {e}"}
    except ValueError as e:
        # _contar() usa ValueError para propagar el motivo que da el API en un
        # 400 (rango muy amplio, formato de fecha). Ese motivo es accionable
        # para el asesor: se conserva en vez de taparlo con un generico.
        return {"error": str(e) if str(e)
                else "WispHub devolvio una respuesta que no es JSON valido."}


# ==============================================================================
#  4) CONFIRMACION HUMANA para acciones sensibles
# ==============================================================================

ACCIONES_SENSIBLES = {"registrar_pago"}

def requiere_confirmacion(nombre, args):
    if nombre not in ACCIONES_SENSIBLES:
        return True
    print(f"\n  [!] El modelo quiere ejecutar: {nombre}({args})")
    return input("     Autorizas esta accion? (s/n): ").strip().lower() == "s"


# ==============================================================================
#  5) BUCLE DE CONVERSACION CON TOOL CALLING
# ==============================================================================

_SYSTEM_BASE = (
    "Eres un asistente interno para los colaboradores de un proveedor de internet (ISP). "
    "IMPORTANTE: quien te escribe SIEMPRE es un COLABORADOR de la empresa, NUNCA el cliente final. "
    "Por lo tanto, habla del cliente en TERCERA PERSONA y nunca lo saludes ni te dirijas a el. "
    "Ejemplo correcto: 'El cliente 7553 (Joan Nieto) esta activo, plan PLAN HOGAR, sin facturas pendientes.' "
    "Ejemplo incorrecto: 'Hola Joan, tu servicio esta activo.' "
    "\n\n"
    "REGLAS DE COMPORTAMIENTO:\n"
    "- Responde en espanol, de forma breve, clara y profesional. Ve al grano; quien pregunta quiere datos rapidos.\n"
    "- Usa SIEMPRE las herramientas para consultar datos reales antes de responder. Nunca inventes ni supongas datos.\n"
    "- Si te dan un numero de cedula (documento), usa consultar_cliente_por_cedula; "
    "si te dan un ID de servicio, usa consultar_cliente.\n"
    "- Cuando un resultado traiga un campo 'alcance', 'aviso' o 'advertencia', repiteselo al "
    "colaborador: indica que se consulto y que no. No lo omitas.\n"
    "- NUNCA calcules tu: ni sumes, ni restes, ni cuentes, ni saques porcentajes. Para "
    "cualquier pregunta de CUANTOS usa consultar_agregado; el numero que devuelve ya esta "
    "calculado y es el que debes dar, tal cual.\n"
    # OJO con los ejemplos de este prompt: llevan MARCADORES entre < >, nunca
    # numeros ni nombres concretos. Medido en agosto 2026: con un ejemplo que
    # decia 'Facturas pendientes en zona X, julio 2026: 143', el modelo lo
    # copiaba TAL CUAL como respuesta a otra pregunta —una cifra segura,
    # especifica e inventada, sacada del propio prompt—. Un ejemplo que se
    # puede confundir con un dato tarde o temprano se entrega como dato.
    "- Al dar un dato agregado, di SIEMPRE como se interpreto la pregunta usando el campo "
    "'interpretacion' del resultado. No respondas solo el numero: acompanalo de que se "
    "conto y con que filtros, con la forma '<que se conto> <filtros> <periodo>: <numero>'. "
    "Usa siempre los valores del resultado, nunca de este ejemplo. "
    "Quien pregunta debe poder detectar si entendiste mal.\n"
    "- Si una herramienta no devuelve un dato, dilo explicitamente ('No se encontro esa informacion') en vez de rellenar.\n"
    "- Si te piden algo para lo que no tienes herramienta, di que no puedes consultarlo, no improvises. "
    "Puede ser que ese dato le corresponda a otra area; en ese caso, indicalo.\n"
    "- Presenta la informacion de forma ordenada (puedes usar una lista corta si son varios campos).\n"
    "- Para acciones que modifican datos, confirma primero lo que vas a hacer.\n"
)

# Instrucciones propias de cada area. El motor no cambia; cambia el encuadre.
_SYSTEM_AREA = {
    "soporte": (
        "\nAREA: SOPORTE. Atiendes a los asesores que hablan con el cliente.\n"
        "- Si preguntan por tickets DE UN CLIENTE, usa consultar_tickets_de_cliente "
        "(acepta cedula o ID de servicio). Si te dan un NUMERO DE TICKET, usa consultar_ticket.\n"
        "- No tienes acceso a datos de red (IP, MAC, router) ni a montos del plan. "
        "Si los piden, indica que corresponden a Tecnica o a Facturacion.\n"
    ),
    "tecnica": (
        "\nAREA: TECNICA. Diagnosticas conectividad y equipos.\n"
        "- Tienes acceso a los datos de red del cliente (IP, MAC, ONU, antena, router).\n"
        "- NO tienes acceso a contrasenas de equipos, ni a datos de contacto o de facturacion.\n"
    ),
    "facturacion": (
        "\nAREA: FACTURACION. Revisas facturas, saldos y cobros.\n"
        "- Registrar un pago es una accion sensible: explica antes que factura y que monto vas a registrar.\n"
        "- No tienes acceso a datos de red ni a tickets de soporte.\n"
    ),
    "administracion": (
        "\nAREA: ADMINISTRACION. Consultas consolidadas.\n"
        "- Trabajas sin datos personales del cliente: no ves cedula ni datos de contacto.\n"
        "- Si te piden un dato individual identificable, indica que no te corresponde.\n"
        "- Es tu herramienta principal consultar_agregado: puedes contar clientes, "
        "facturas y tickets, y desglosar por estado o por zona.\n"
    ),
}

def construir_system(area):
    """Arma el prompt del sistema para el area indicada."""
    return _SYSTEM_BASE + _SYSTEM_AREA.get(area, "")

# --- Razonamiento interno del modelo ("thinking") -----------------------------
# Qwen3 razona antes de responder y Ollama entrega ese razonamiento en un campo
# 'thinking', aparte del 'content'.
#
# MEDIDO: pasar think=False NO lo apaga. El modelo razona igual; lo unico que
# cambia es que Ollama deja de separarlo y el razonamiento crudo (en ingles, con
# un '</think>' en medio) termina en 'content', o sea, en la cara del asesor.
# El interruptor /no_think de Qwen3 tampoco lo detiene con esta plantilla.
# Por eso NO se toca el parametro: se deja que Ollama lo separe y se descarta.

_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)

def _sin_razonamiento(texto):
    """Red de seguridad: quita cualquier bloque de razonamiento que se filtre al texto."""
    texto = _RE_THINK.sub("", texto or "")
    if "</think>" in texto:          # bloque abierto antes del campo content
        texto = texto.split("</think>")[-1]
    return texto.strip()

def _limpiar_mensaje(msg):
    """
    Convierte la respuesta de Ollama en un dict plano para el historial.

    Descarta el campo 'thinking': si se reenvia, el razonamiento de cada turno se
    acumula en el contexto de los turnos siguientes (2.500-5.400 caracteres por
    turno, medido), encareciendolos sin aportar nada. Qwen3 esta disenado para
    que el razonamiento previo no se reenvie.
    """
    limpio = {"role": msg.get("role") or "assistant",
              "content": _sin_razonamiento(msg.get("content"))}
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        limpio["tool_calls"] = [
            {"function": {"name": tc["function"]["name"],
                          "arguments": tc["function"]["arguments"]}}
            for tc in tool_calls
        ]
    return limpio


def responder(mensaje_cliente, historial, area=AREA_POR_DEFECTO):
    historial.append({"role": "user", "content": mensaje_cliente})
    resp = ollama.chat(model=MODELO, messages=historial, tools=herramientas_de(area))
    msg = resp["message"]
    historial.append(_limpiar_mensaje(msg))

    tool_calls = msg.get("tool_calls") or []
    for tc in tool_calls:
        nombre = tc["function"]["name"]
        args = tc["function"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)

        ok, resultado = validar_argumentos(nombre, args)
        # Lo que se audita son los argumentos YA VALIDADOS cuando los hay; si la
        # validacion fallo, los crudos que propuso el modelo.
        auditables = resultado if ok else args
        inicio = time.monotonic()

        if nombre not in AREAS.get(area, {}).get("herramientas", []):
            # El modelo solo recibio las herramientas de su area, pero puede
            # inventar un nombre. Se corta aqui: la lista de herramientas es una
            # sugerencia para el modelo; el permiso lo decide el codigo.
            salida = {"error": f"El area '{area}' no tiene la herramienta '{nombre}'."}
            estado = "rechazado_por_area"
        elif (nombre == "consultar_agregado" and ok
              and resultado["entidad"] not in agregados_de(area)):
            # Tener la herramienta no da acceso a todas las entidades: Soporte
            # cuenta tickets, no facturas. Se verifica aparte porque la entidad
            # viaja como ARGUMENTO, y un permiso que solo mira el nombre de la
            # herramienta no la ve.
            salida = {"error": f"El area '{area}' no puede contar "
                               f"'{resultado['entidad']}'."}
            estado = "rechazado_por_area"
        elif not ok:
            salida = {"error": resultado}
            estado = "argumentos_invalidos"
        elif not requiere_confirmacion(nombre, resultado):
            salida = {"error": "Accion cancelada por el operador."}
            estado = "cancelado_por_operador"
        else:
            crudo = ejecutar_herramienta(nombre, resultado)
            salida = filtrar_campos(nombre, crudo, area)   # filtra segun el area
            estado = "error_api" if isinstance(salida, dict) and "error" in salida else "ok"
            print(f"     [herramienta {nombre} -> {salida}]")

        registrar_auditoria(area, nombre, auditables, estado,
                            registros=_cuantos_registros(salida),
                            ms=int((time.monotonic() - inicio) * 1000))

        # 'name' (y el id, si lo hay) permiten al modelo asociar cada resultado
        # con la herramienta que lo pidio cuando hay varias llamadas en un turno.
        mensaje_tool = {
            "role": "tool",
            "name": nombre,
            "content": json.dumps(salida, ensure_ascii=False),
        }
        if tc.get("id"):
            mensaje_tool["tool_call_id"] = tc["id"]
        historial.append(mensaje_tool)

    if tool_calls:
        # Segunda llamada SIN tools: ya tiene el dato, solo debe redactar.
        resp = ollama.chat(model=MODELO_REDACCION, messages=historial)
        final = _limpiar_mensaje(resp["message"])
        historial.append(final)
        return final["content"]
    return _sin_razonamiento(msg.get("content"))


# ==============================================================================
#  6) EJECUCION INTERACTIVA
# ==============================================================================

def identificar_area():
    """
    Identifica el area del colaborador.

    OJO: esto es IDENTIFICACION, no AUTENTICACION. No hay contrasena: quien abre
    la consola elige su area. Sirve para acotar lo que cada uno ve por defecto y
    para probar el catalogo por area, pero no impide que alguien elija otra.
    La autenticacion real llega con la interfaz web (Fase 5 del PRD).

    Se puede fijar en el .env (AREA_COLABORADOR) para pruebas no interactivas.
    """
    del_entorno = (os.environ.get("AREA_COLABORADOR") or "").strip().lower()
    if area_valida(del_entorno):
        return del_entorno

    print("\n  Areas disponibles:")
    for nombre, cfg in AREAS.items():
        print(f"    - {nombre:<15} {cfg['descripcion']}")
    while True:
        try:
            elegida = input(f"\n  Tu area [{AREA_POR_DEFECTO}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return AREA_POR_DEFECTO
        if not elegida:
            return AREA_POR_DEFECTO
        if area_valida(elegida):
            return elegida
        print(f"  '{elegida}' no es un area valida.")


if __name__ == "__main__":
    print("=" * 60)
    print(f"  Asistente interno  ({MODELO})")
    print(f"  Modo: {'WISPHUB REAL -> ' + WISPHUB_BASE_URL if USAR_WISPHUB_REAL else 'SIMULADO (sin tocar la API)'}")
    print("=" * 60)

    area = identificar_area()
    disponibles = [h["function"]["name"] for h in herramientas_de(area)]
    print(f"\n  Area: {area.upper()}  |  Herramientas: {', '.join(disponibles) or 'ninguna'}")
    print("  Escribe 'salir' para terminar.")
    print("=" * 60)

    historial = [{"role": "system", "content": construir_system(area)}]
    while True:
        try:
            entrada = input(f"{area} > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if entrada.lower() in ("salir", "exit", "quit"):
            break
        if not entrada:
            continue
        print(f"\nAsistente > {responder(entrada, historial, area)}\n")
