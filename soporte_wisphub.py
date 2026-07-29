"""
================================================================================
  ASISTENTE DE SOPORTE  —  Qwen3 (Ollama)  +  API de WispHub
  Version con: credenciales en .env  +  filtro de campos PII
================================================================================

El modelo DECIDE que herramienta llamar; ESTE codigo VALIDA, EJECUTA y ADEMAS
FILTRA los datos: a Qwen3 solo le llegan los campos necesarios, nunca IP, MAC,
ni contrasenas de equipos. La clave API vive en un archivo .env aparte, jamas
dentro del codigo.

--------------------------------------------------------------------------------
REQUISITOS (una sola vez):
    py -3.13 -m pip install ollama requests python-dotenv
    ollama pull qwen3:4b

CREDENCIALES (archivo .env en la MISMA carpeta que este script):
    Crea un archivo llamado  .env  con este contenido:
        WISPHUB_API_KEY=tu_clave_real_aqui
    NO subas el .env a OneDrive, Git, ni lo compartas. Guarda el proyecto en
    una carpeta LOCAL (ej. C:\\wisphub\\), fuera de OneDrive.

MODOS:
    USAR_WISPHUB_REAL = False  -> datos simulados (para probar sin tocar nada)
    USAR_WISPHUB_REAL = True   -> llama a WispHub de verdad
================================================================================
"""

import os
import json
import requests
import ollama

### NUEVO: cargar credenciales desde el archivo .env ---------------------------
# load_dotenv() lee el archivo .env y mete WISPHUB_API_KEY en el entorno,
# ANTES de que el resto del script intente leerla.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("AVISO: falta python-dotenv. Instala con:  py -3.13 -m pip install python-dotenv")
# -----------------------------------------------------------------------------


# ==============================================================================
#  CONFIGURACION
# ==============================================================================

MODELO = "qwen3:4b"
USAR_WISPHUB_REAL = True     # empieza en False; cambia a True para produccion

WISPHUB_BASE_URL = "https://api.wisphub.io"   # produccion (confirma en la doc)
WISPHUB_API_KEY  = os.environ.get("WISPHUB_API_KEY")   ### NUEVO: solo del entorno

if USAR_WISPHUB_REAL and not WISPHUB_API_KEY:
    raise SystemExit(
        "ERROR: no se encontro WISPHUB_API_KEY.\n"
        "Crea un archivo .env en esta carpeta con:  WISPHUB_API_KEY=tu_clave"
    )

def _headers():
    return {
        "Authorization": f"Api-Key {WISPHUB_API_KEY}",
        "Content-Type": "application/json",
    }

EP_CLIENTE  = "/api/clientes/{id}/"
EP_FACTURAS = "/api/facturas/"
EP_TICKET   = "/api/tickets/{id}/"
EP_PAGO     = "/api/facturas/{id}/pagar/"


# ==============================================================================
#  ### NUEVO: FILTRO DE CAMPOS (PII)
# ==============================================================================
# WispHub devuelve MUCHOS campos, varios sensibles (IP, MAC, contrasenas del CPE
# y del router, etc.). El asistente NO necesita nada de eso para atender.
# Aqui definimos, por herramienta, la lista BLANCA de campos que si puede ver
# el modelo. Todo lo demas se descarta antes de pasarselo a Qwen3.

CAMPOS_PERMITIDOS = {
    "consultar_cliente": [
        "id_servicio", "usuario_rb", "estado",
        "facturas_pagadas", "plan_internet", "fecha_instalacion",
    ],
    "consultar_facturas": ["facturas"],
    "consultar_ticket": ["id_ticket", "estado", "asunto", "tecnico"],
    "registrar_pago": ["resultado", "id_factura", "monto", "estado"],
}

def filtrar_campos(nombre, datos):
    """Deja solo los campos de la lista blanca. Descarta IP, MAC, passwords, etc."""
    if not isinstance(datos, dict):
        return datos
    permitidos = CAMPOS_PERMITIDOS.get(nombre)
    if not permitidos:
        return datos
    # Si algun campo permitido es a su vez un objeto (ej. plan_internet), se
    # conserva completo; si quisieras, podrias filtrarlo tambien aqui.
    return {k: v for k, v in datos.items() if k in permitidos}


# ==============================================================================
#  1) DEFINICION DE LAS 4 HERRAMIENTAS
# ==============================================================================

HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "consultar_cliente",
        "description": "Obtiene los datos y el estado de un cliente por su ID de servicio.",
        "parameters": {"type": "object", "properties": {
            "id_cliente": {"type": "string", "description": "ID de servicio del cliente."}
        }, "required": ["id_cliente"]}}},
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

_SIMULADO = {
    "clientes": {
        "A-4821": {"id_servicio": "A-4821", "usuario_rb": "Maria Gomez",
                   "estado": "Activo", "plan_internet": {"nombre": "Fibra 100MB"},
                   "facturas_pagadas": True, "ip": "10.0.0.5", "mac_cpe": "AA:BB:CC"},
    },
    "facturas": {
        "A-4821": [{"id_factura": "F-9001", "estado": "pagada", "monto": 80000}],
        "B-1050": [{"id_factura": "F-9002", "estado": "pendiente", "monto": 45000}],
    },
    "tickets": {
        "T-300": {"id_ticket": "T-300", "estado": "en proceso",
                  "asunto": "Sin servicio de internet", "tecnico": "asignado"},
    },
}

def ejecutar_herramienta(nombre, args):
    """Devuelve la respuesta CRUDA (sin filtrar todavia)."""
    if not USAR_WISPHUB_REAL:
        if nombre == "consultar_cliente":
            return _SIMULADO["clientes"].get(args["id_cliente"], {"error": "Cliente no encontrado"})
        if nombre == "consultar_facturas":
            return {"facturas": _SIMULADO["facturas"].get(args["id_cliente"], [])}
        if nombre == "consultar_ticket":
            return _SIMULADO["tickets"].get(args["id_ticket"], {"error": "Ticket no encontrado"})
        if nombre == "registrar_pago":
            return {"resultado": "ok", "id_factura": args["id_factura"],
                    "monto": args["monto"], "estado": "pagada (simulado)"}

    try:
        if nombre == "consultar_cliente":
            url = WISPHUB_BASE_URL + EP_CLIENTE.format(id=args["id_cliente"])
            r = requests.get(url, headers=_headers(), timeout=15)
        elif nombre == "consultar_facturas":
            url = WISPHUB_BASE_URL + EP_FACTURAS
            r = requests.get(url, headers=_headers(),
                             params={"cliente": args["id_cliente"]}, timeout=15)
        elif nombre == "consultar_ticket":
            url = WISPHUB_BASE_URL + EP_TICKET.format(id=args["id_ticket"])
            r = requests.get(url, headers=_headers(), timeout=15)
        elif nombre == "registrar_pago":
            url = WISPHUB_BASE_URL + EP_PAGO.format(id=args["id_factura"])
            r = requests.post(url, headers=_headers(),
                              json={"monto": args["monto"]}, timeout=15)
        else:
            return {"error": "herramienta desconocida"}
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {"error": f"Fallo al llamar a WispHub: {e}"}


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
    "- Si una herramienta no devuelve un dato, dilo explicitamente ('No se encontro esa informacion') en vez de rellenar.\n"
    "- Si el asesor pide algo para lo que no tienes herramienta, indica que no puedes consultarlo, no improvises.\n"
    "- Presenta la informacion de forma ordenada (puedes usar una lista corta si son varios campos).\n"
    "- Para acciones que modifican datos (como registrar un pago), confirma primero con el asesor lo que vas a hacer.\n"
)

def responder(mensaje_cliente, historial):
    historial.append({"role": "user", "content": mensaje_cliente})
    resp = ollama.chat(model=MODELO, messages=historial, tools=HERRAMIENTAS)
    msg = resp["message"]
    historial.append(msg)

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
            salida = filtrar_campos(nombre, crudo)   ### NUEVO: filtra antes de pasarlo al modelo
            print(f"     [herramienta {nombre} -> {salida}]")

        historial.append({"role": "tool", "content": json.dumps(salida, ensure_ascii=False)})

    if tool_calls:
        resp = ollama.chat(model=MODELO, messages=historial)
        final = resp["message"]
        historial.append(final)
        return final["content"]
    return msg["content"]


# ==============================================================================
#  6) EJECUCION INTERACTIVA
# ==============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print(f"  Asistente de soporte  ({MODELO})")
    print(f"  Modo: {'WISPHUB REAL' if USAR_WISPHUB_REAL else 'SIMULADO (sin API key)'}")
    print("  Escribe 'salir' para terminar.")
    print("=" * 60)

    historial = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            entrada = input("Cliente > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if entrada.lower() in ("salir", "exit", "quit"):
            break
        if not entrada:
            continue
        print(f"\nAsistente > {responder(entrada, historial)}\n")