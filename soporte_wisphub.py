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
EP_PAGO     = "/api/facturas/{id}/registrar-pago/"

# Maximo de filas que se le entregan al modelo en una consulta de lista.
# No es un limite de la API sino del modelo: volcarle cientos de registros
# desborda su contexto y degrada la respuesta. Cuando el total supera este tope,
# el filtro avisa explicitamente que el resultado es parcial (ver filtrar_campos).
#
# Para CONTAR no hace falta traer filas: el paginado del API ya devuelve 'count'.
# Una consulta agregada debe pedir limit=1 y leer ese numero (ver PRD 12.5).
LIMITE_FILAS = 50

# Accion al registrar un pago (campo 'accion' del API):
#   0 = solo registrar el pago
#   1 = registrar el pago Y reactivar el servicio
# Se usa 0 por defecto: reactivar es un efecto adicional que el asesor no pidio.
ACCION_PAGO = int(os.environ.get("WISPHUB_ACCION_PAGO", "0"))


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

# Nombres de campo VERIFICADOS contra la API en produccion (no inventados).
# El endpoint de clientes devuelve 54 campos; aqui pasan 13.
# Deliberadamente FUERA de la lista blanca:
#   - 'usuario': identificador interno (nombre-completo@empresa). El codigo lo
#     necesita para consultar facturas, pero el modelo no tiene por que verlo.
#   - red y credenciales (ip, mac_cpe, password_*, sn_onu, router, ssid...):
#     nunca, para ningun area salvo Tecnica.
#   - financieros del plan (precio_plan, costo_instalacion, descuento): area de
#     Facturacion, no de Soporte (ver tabla de areas del PRD, seccion 3).
CAMPOS_PERMITIDOS = {
    "consultar_cliente": [
        "id_servicio", "nombre", "cedula", "estado",
        "estado_facturas", "saldo", "fecha_corte",
        "plan_internet", "zona", "fecha_instalacion",
        # Contacto: el asesor los necesita para ubicar al cliente o coordinar
        # una visita. Son PII: cuando exista control por area (Fase 2), revisar
        # si todas las areas deben verlos.
        "email", "telefono", "direccion",
    ],
    "consultar_facturas": [
        "id_factura", "estado", "total", "saldo",
        "fecha_emision", "fecha_vencimiento", "fecha_pago",
    ],
    # 'servicio' NO se deja pasar entero: trae la IP del cliente y el router con
    # sus credenciales. Solo se abren sus campos inofensivos, con notacion punto.
    # Fuera a proposito: 'respuestas' (hilo del ticket, util pero de tamano
    # imprevisible; revisar al implementar el tope de volumen) y 'email_tecnico',
    # 'creado_por', 'tickets_mensual/anual' (datos internos que no ayudan a
    # responder por el estado de un ticket).
    # OJO con 'descripcion': es TEXTO LIBRE. Visto en produccion, puede traer
    # embebidos nombre, telefono, email, direccion, GPS, documento y enlaces.
    # La lista blanca filtra campos, no el contenido de un campo. Se conserva
    # porque es el contenido del ticket, pero es un limite real (ver PRD 7.4).
    "consultar_ticket": [
        "id_ticket", "asunto", "descripcion", "razon_falla",
        "estado", "prioridad", "tecnico", "departamento", "origen_reporte",
        "fecha_creacion", "fecha_inicio", "fecha_fin",
        "servicio.id_servicio", "servicio.plan_internet", "servicio.zona",
    ],
    # El API responde {task_id, messages}; el modo simulado, {resultado, ...}.
    "registrar_pago": ["resultado", "id_factura", "total_cobrado",
                       "mensajes", "messages", "task_id", "errors"],
}
# Las dos consultas de cliente devuelven la misma forma: comparten lista blanca.
CAMPOS_PERMITIDOS["consultar_cliente_por_cedula"] = CAMPOS_PERMITIDOS["consultar_cliente"]

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

def filtrar_campos(nombre, datos):
    """
    Deja solo los campos de la lista blanca. Descarta IP, MAC, passwords, etc.

    Maneja las tres formas en que responde WispHub:
      - dict suelto            -> {"campo": valor, ...}
      - lista                  -> [ {...}, {...} ]
      - paginado estilo DRF    -> {"count": N, "results": [ {...} ]}

    Las dos ultimas se normalizan a {"total": N, "resultados": [...]} para que
    el modelo siempre reciba la misma forma.

    IMPORTANTE (fail-closed): si una herramienta no tiene lista blanca definida,
    NO se deja pasar nada. Antes se devolvia el dato crudo, lo que abria un hueco
    en la capa de seguridad al agregar herramientas nuevas.
    """
    permitidos = CAMPOS_PERMITIDOS.get(nombre)
    if permitidos is None:
        return {"error": f"Sin lista blanca de campos para '{nombre}'. Resultado descartado."}
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

    return {"error": "Formato de respuesta no reconocido. Resultado descartado."}


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

def validar_argumentos(nombre, args):
    if nombre in ("consultar_cliente", "consultar_facturas"):
        idc = str(args.get("id_cliente", "")).strip()
        if not idc:
            return False, "Falta el ID de servicio del cliente."
        return True, {"id_cliente": idc}
    if nombre == "consultar_cliente_por_cedula":
        # Se limpian separadores comunes (puntos, espacios, guiones) antes de buscar.
        cedula = str(args.get("cedula", "")).strip()
        for sobra in (".", " ", "-"):
            cedula = cedula.replace(sobra, "")
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
    except ValueError:
        return {"error": "WispHub devolvio una respuesta que no es JSON valido."}


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

SYSTEM = (
    "Eres un asistente interno de soporte para los asesores de un proveedor de internet (ISP). "
    "IMPORTANTE: quien te escribe SIEMPRE es un ASESOR de la empresa, NUNCA el cliente final. "
    "Por lo tanto, habla del cliente en TERCERA PERSONA y nunca lo saludes ni te dirijas a el. "
    "Ejemplo correcto: 'El cliente 7553 (Joan Nieto) esta activo, plan PLAN HOGAR, sin facturas pendientes.' "
    "Ejemplo incorrecto: 'Hola Joan, tu servicio esta activo.' "
    "\n\n"
    "REGLAS DE COMPORTAMIENTO:\n"
    "- Responde en espanol, de forma breve, clara y profesional. Ve al grano; el asesor quiere datos rapidos.\n"
    "- Usa SIEMPRE las herramientas para consultar datos reales antes de responder. Nunca inventes ni supongas datos.\n"
    "- Si el asesor da un numero de cedula (documento), usa consultar_cliente_por_cedula; "
    "si da un ID de servicio, usa consultar_cliente.\n"
    "- Si una herramienta no devuelve un dato, dilo explicitamente ('No se encontro esa informacion') en vez de rellenar.\n"
    "- Si el asesor pide algo para lo que no tienes herramienta, indica que no puedes consultarlo, no improvises.\n"
    "- Presenta la informacion de forma ordenada (puedes usar una lista corta si son varios campos).\n"
    "- Para acciones que modifican datos (como registrar un pago), confirma primero con el asesor lo que vas a hacer.\n"
)

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


def responder(mensaje_cliente, historial):
    historial.append({"role": "user", "content": mensaje_cliente})
    resp = ollama.chat(model=MODELO, messages=historial, tools=HERRAMIENTAS)
    msg = resp["message"]
    historial.append(_limpiar_mensaje(msg))

    tool_calls = msg.get("tool_calls") or []
    for tc in tool_calls:
        nombre = tc["function"]["name"]
        args = tc["function"]["arguments"]
        if isinstance(args, str):
            args = json.loads(args)

        ok, resultado = validar_argumentos(nombre, args)
        if not ok:
            salida = {"error": resultado}
        elif not requiere_confirmacion(nombre, resultado):
            salida = {"error": "Accion cancelada por el operador."}
        else:
            crudo = ejecutar_herramienta(nombre, resultado)
            salida = filtrar_campos(nombre, crudo)   # filtra antes de pasarlo al modelo
            print(f"     [herramienta {nombre} -> {salida}]")

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

if __name__ == "__main__":
    print("=" * 60)
    print(f"  Asistente de soporte  ({MODELO})")
    print(f"  Modo: {'WISPHUB REAL -> ' + WISPHUB_BASE_URL if USAR_WISPHUB_REAL else 'SIMULADO (sin tocar la API)'}")
    print("  Escribe 'salir' para terminar.")
    print("=" * 60)

    historial = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            entrada = input("Asesor > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if entrada.lower() in ("salir", "exit", "quit"):
            break
        if not entrada:
            continue
        print(f"\nAsistente > {responder(entrada, historial)}\n")
