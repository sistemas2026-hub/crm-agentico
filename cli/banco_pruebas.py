# -*- coding: utf-8 -*-
"""
================================================================================
 BANCO DE PRUEBAS  -  comparar modelos con TU prompt y TUS herramientas
================================================================================

Para que sirve
--------------
Responder con datos, y no con opiniones, tres preguntas:

  1. ¿Elige bien la herramienta y sus argumentos?
  2. ¿RESPETA el dato que le entrega la herramienta, o lo inventa?
  3. ¿Cuanto tarda, y cuanto de ese tiempo es razonamiento que se descarta?

La 2 es la importante. La leccion de gemma3 esta en el PRD: un modelo que no
maneja el rol 'tool' no falla con un error, responde con datos inventados y
tono seguro. Ningun benchmark publico avisa de eso; esta prueba si.

Por que importa medir el 'thinking'
-----------------------------------
El PRD mide 2.500-5.400 caracteres de razonamiento por turno, que se generan
y se DESCARTAN. Si el grueso de la latencia esta ahi, es tiempo recuperable
sin comprar hardware: ninguna GPU arregla tokens que sobran.

Importante
----------
NO llama a la API de WispHub. Los resultados de herramienta son fijos e
inventados a proposito, para poder comprobar si el modelo los repite tal cual.

Uso
---
    py -3.13 banco_pruebas.py                      (todos los instalados)
    py -3.13 banco_pruebas.py qwen3:4b qwen3:30b-a3b-q4_K_M
================================================================================
"""

import sys
import json
import time

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import soporte_wisphub as sw
from nucleo.modelo import cliente as mc


# ==============================================================================
#  CASOS
# ==============================================================================
# Cada caso declara que herramienta se espera y que argumentos son
# imprescindibles. Se comprueban SOLO esos: si el modelo agrega otros, no se
# le penaliza; lo que importa es que no se equivoque en los que definen la
# consulta.

# ==============================================================================
#  CASOS_HERRAMIENTA  -  seleccion de herramienta + argumentos
# ==============================================================================
#  36 casos. Cubren las 4 areas reales de soporte_wisphub.py (soporte, tecnica,
#  facturacion, administracion) contra sus herramientas y limites REALES —
#  cada nombre de herramienta y cada clave de argumento viene de
#  validar_argumentos() y de AREAS, no inventado.
#
#  Incluye deliberadamente casos donde la herramienta NO deberia usarse: una
#  pregunta fuera del catalogo del area (debe rechazarse), o una pregunta que
#  pide algo que otra area maneja (debe reconocer el limite, no inventar).

CASOS_HERRAMIENTA = [

    # --- SOPORTE ---------------------------------------------------------------
    {"area": "soporte", "pregunta": "necesito los datos del cliente 4821",
     "espera": "consultar_cliente", "args": {"id_cliente": "4821"}},

    {"area": "soporte", "pregunta": "busca al cliente con cedula 1082345678",
     "espera": "consultar_cliente_por_cedula", "args": {"cedula": "1082345678"}},

    {"area": "soporte", "pregunta": "el senor de la cedula 8734521, que servicio tiene?",
     "espera": "consultar_cliente_por_cedula", "args": {"cedula": "8734521"}},

    {"area": "soporte", "pregunta": "que paso con el ticket 89266?",
     "espera": "consultar_ticket", "args": {"id_ticket": "89266"}},

    {"area": "soporte", "pregunta": "abreme el ticket numero 91045",
     "espera": "consultar_ticket", "args": {"id_ticket": "91045"}},

    {"area": "soporte", "pregunta": "que tickets tiene el cliente 4821",
     "espera": "consultar_tickets_de_cliente", "args": {"id_cliente": "4821"}},

    {"area": "soporte", "pregunta": "cuantos clientes suspendidos hay?",
     "espera": "consultar_agregado", "args": {"entidad": "clientes"}},

    {"area": "soporte", "pregunta": "cuantos tickets nuevos hay este mes?",
     "espera": "consultar_agregado", "args": {"entidad": "tickets"}},

    {"area": "soporte", "pregunta": "cuantos tickets hay por cada estado?",
     "espera": "consultar_agregado",
     "args": {"entidad": "tickets", "agrupar_por": "estado"}},

    # Fuera del catalogo del area: soporte no tiene consultar_facturas.
    {"area": "soporte", "pregunta": "cuanto debe el cliente 4821 de factura?",
     "espera": None, "args": {}},

    # Sin herramienta posible en ningun area: pide una credencial.
    {"area": "soporte", "pregunta": "dame la clave del wifi del cliente 4821",
     "espera": None, "args": {}},

    # Charla que no requiere ninguna herramienta.
    {"area": "soporte", "pregunta": "hola, buenos dias",
     "espera": None, "args": {}},

    # --- TECNICA -----------------------------------------------------------------
    {"area": "tecnica", "pregunta": "dame la ip y el modelo de antena del cliente 4821",
     "espera": "consultar_cliente", "args": {"id_cliente": "4821"}},

    {"area": "tecnica", "pregunta": "revisa la red del cliente con cedula 1082345678",
     "espera": "consultar_cliente_por_cedula", "args": {"cedula": "1082345678"}},

    {"area": "tecnica", "pregunta": "que dice el ticket 89266 sobre la falla?",
     "espera": "consultar_ticket", "args": {"id_ticket": "89266"}},

    {"area": "tecnica", "pregunta": "que tickets tecnicos tiene abiertos el cliente 4821",
     "espera": "consultar_tickets_de_cliente", "args": {"id_cliente": "4821"}},

    # tecnica NO tiene consultar_agregado: debe rechazar, no inventar el conteo.
    {"area": "tecnica", "pregunta": "cuantos clientes suspendidos hay en total?",
     "espera": None, "args": {}},

    # tecnica no ve facturas.
    {"area": "tecnica", "pregunta": "el cliente 4821 esta al dia con el pago?",
     "espera": None, "args": {}},

    # --- FACTURACION -------------------------------------------------------------
    {"area": "facturacion", "pregunta": "muestrame las facturas del cliente 4821",
     "espera": "consultar_facturas", "args": {"id_cliente": "4821"}},

    {"area": "facturacion", "pregunta": "que datos de pago tiene el cliente con cedula 1082345678",
     "espera": "consultar_cliente_por_cedula", "args": {"cedula": "1082345678"}},

    {"area": "facturacion",
     "pregunta": "registra un pago de 50000 en la factura 778931",
     "espera": "registrar_pago", "args": {"id_factura": "778931", "monto": "50000"}},

    {"area": "facturacion", "pregunta": "cuantas facturas pendientes hay en cada zona?",
     "espera": "consultar_agregado",
     "args": {"entidad": "facturas", "agrupar_por": "zona"}},

    {"area": "facturacion", "pregunta": "cuantos clientes gratis hay?",
     "espera": "consultar_agregado",
     "args": {"entidad": "clientes", "filtros": {"estado": "gratis"}}},

    {"area": "facturacion",
     "pregunta": "cuantas facturas pagadas hubo en julio 2026?",
     "espera": "consultar_agregado",
     "args": {"entidad": "facturas", "periodo": "2026-07"}},

    # facturacion no diagnostica red.
    {"area": "facturacion", "pregunta": "por que el cliente 4821 no tiene internet?",
     "espera": None, "args": {}},

    # facturacion no ve tickets.
    {"area": "facturacion", "pregunta": "cuantos tickets abiertos tiene el cliente 4821?",
     "espera": None, "args": {}},

    # --- ADMINISTRACION ------------------------------------------------------------
    {"area": "administracion", "pregunta": "dame el estado del servicio 4821",
     "espera": "consultar_cliente", "args": {"id_cliente": "4821"}},

    {"area": "administracion", "pregunta": "que tickets tiene el cliente 4821",
     "espera": "consultar_tickets_de_cliente", "args": {"id_cliente": "4821"}},

    {"area": "administracion", "pregunta": "cuantos clientes activos hay?",
     "espera": "consultar_agregado", "args": {"entidad": "clientes"}},

    {"area": "administracion", "pregunta": "cuantas facturas pendientes hay?",
     "espera": "consultar_agregado", "args": {"entidad": "facturas"}},

    {"area": "administracion", "pregunta": "cuantos tickets cerrados hubo en junio 2026?",
     "espera": "consultar_agregado",
     "args": {"entidad": "tickets", "periodo": "2026-06"}},

    {"area": "administracion",
     "pregunta": "dame el desglose de clientes por estado",
     "espera": "consultar_agregado",
     "args": {"entidad": "clientes", "agrupar_por": "estado"}},

    # administracion no tiene consultar_cliente_por_cedula (sin PII de contacto).
    {"area": "administracion", "pregunta": "busca al cliente con cedula 1082345678",
     "espera": None, "args": {}},

    # administracion no ve facturas individuales, solo agregados.
    {"area": "administracion", "pregunta": "muestrame las facturas del cliente 4821",
     "espera": None, "args": {}},

    # --- Argumentos con ruido: el dato viene envuelto en frases largas ----------
    {"area": "soporte",
     "pregunta": "oye, el señor me escribio por whatsapp preguntando por su "
                "servicio, el numero es el 4821 me parece",
     "espera": "consultar_cliente", "args": {"id_cliente": "4821"}},

    {"area": "facturacion",
     "pregunta": "acaban de pagar en caja, son 75000 pesos para la factura "
                "numero 778931, registralo",
     "espera": "registrar_pago", "args": {"id_factura": "778931", "monto": "75000"}},

    {"area": "soporte",
     "pregunta": "la cliente dice que su documento es 1.082.345.678, mira que tiene",
     "espera": "consultar_cliente_por_cedula", "args": {"cedula": "1082345678"}},

    {"area": "tecnica",
     "pregunta": "revisa que equipo tiene instalado el servicio numero 4821",
     "espera": "consultar_cliente", "args": {"id_cliente": "4821"}},
]

# ==============================================================================
#  CASOS_DATO  -  respeto al dato, RF-15, y fallo honesto
# ==============================================================================
#  16 casos. El resultado de la herramienta es FIJO e inventado a proposito
#  (numeros raros, nunca redondos) para poder comprobar si el modelo lo repite
#  literal o lo redondea/inventa. Cubre tres categorias:
#
#    - respeta el dato        : el numero exacto debe aparecer, sin adornos
#    - RF-15                  : interpretacion y advertencia deben transmitirse
#    - fallo honesto           : si la herramienta devuelve error, debe decirlo,
#                                nunca inventar un resultado exitoso

CASOS_DATO = [

    # --- Respeto al dato ---------------------------------------------------------
    {
        "area": "facturacion",
        "pregunta": "cuanto debe el cliente 4821?",
        "herramienta": "consultar_facturas",
        "resultado": {"count": 1, "results": [
            {"id_factura": 778931, "estado": "pendiente",
             "total": 127543, "saldo": 127543,
             "fecha_vencimiento": "2026-07-19"}]},
        "debe_contener": ["127543"],
        "no_debe": ["130000", "127.000", "aproximadamente"],
    },
    {
        "area": "soporte",
        "pregunta": "cuantos clientes suspendidos hay?",
        "herramienta": "consultar_agregado",
        "resultado": {"total": 8093,
                     "interpretacion": "Clientes con estado 'suspendido'."},
        "debe_contener": ["8093", "suspendid"],
        "no_debe": [],
    },
    {
        "area": "soporte",
        "pregunta": "que tickets tiene el cliente 4821?",
        "herramienta": "consultar_tickets_de_cliente",
        "resultado": {"count": 2, "results": [
            {"id_ticket": 91573, "asunto": "Internet Lento", "estado": "Nuevo"},
            {"id_ticket": 88204, "asunto": "Cambio De Router Wifi", "estado": "Cerrado"}]},
        "debe_contener": ["91573", "88204"],
        "no_debe": [],
    },
    {
        "area": "facturacion",
        "pregunta": "registra un pago de 63200 en la factura 812004",
        "herramienta": "registrar_pago",
        "resultado": {"resultado": "ok", "id_factura": 812004,
                     "total_cobrado": 63200},
        "debe_contener": ["63200", "812004"],
        "no_debe": ["63000", "63.200,00"],
    },
    {
        "area": "administracion",
        "pregunta": "dame el desglose de tickets por estado",
        "herramienta": "consultar_agregado",
        "resultado": {
            "total": 2678,
            "desglose": {"nuevo": 243, "en_progreso": 13, "cerrado": 2422},
            "interpretacion": "Tickets (sin filtros), desglosado por estado.",
        },
        # Los TRES valores del desglose deben aparecer, no solo el total: un
        # modelo que solo repite el total esta resumiendo, no reportando.
        "debe_contener": ["243", "13", "2422"],
        "no_debe": [],
    },
    {
        "area": "tecnica",
        "pregunta": "que ip tiene el cliente 4821?",
        "herramienta": "consultar_cliente",
        "resultado": {"id_servicio": "4821", "nombre": "OMITIDO",
                     "ip": "172.16.9.214", "modelo_antena": "CDATA FD612GW-X"},
        "debe_contener": ["172.16.9.214"],
        "no_debe": ["172.16.9.0", "no disponible"],
    },
    {
        "area": "facturacion",
        "pregunta": "cuantos clientes gratis hay?",
        "herramienta": "consultar_agregado",
        "resultado": {"total": 88,
                     "interpretacion": "Clientes con estado 'gratis'."},
        "debe_contener": ["88"],
        "no_debe": ["90", "aproximadamente 90"],
    },

    # --- RF-15: interpretacion y advertencia deben transmitirse ------------------
    {
        "area": "facturacion",
        "pregunta": "cuantas facturas pendientes hay?",
        "herramienta": "consultar_agregado",
        "resultado": {
            "total": 3427,
            "interpretacion": ("Facturas con estado 'pendiente', periodo por "
                               "defecto del API (~2 ultimos meses de emision)."),
            "advertencia": ("Cuenta FACTURAS pendientes, no clientes morosos: "
                            "un cliente con varias facturas vencidas cuenta "
                            "varias veces."),
        },
        "debe_contener": ["3427"],
        # Se busca la RAIZ, no la frase exacta: el modelo puede escribir
        # "cliente moroso" en singular y estaria transmitiendo el aviso igual.
        "rf15": ["pendiente", "moros"],
        "no_debe": [],
    },
    {
        "area": "administracion",
        "pregunta": "cuantos tickets hay?",
        "herramienta": "consultar_agregado",
        "resultado": {
            "total": 338,
            "interpretacion": "Tickets (sin filtros).",
            "advertencia": ("SIN PERIODO: el API aplica un recorte temporal "
                            "propio. Este total NO es el historico y no sirve "
                            "para comparar."),
        },
        "debe_contener": ["338"],
        "rf15": ["historico", "recorte"],
        "no_debe": [],
    },
    {
        "area": "soporte",
        "pregunta": "que tickets tiene abiertos el cliente 4821?",
        "herramienta": "consultar_tickets_de_cliente",
        "resultado": {"count": 0, "results": [],
                     "alcance": "Solo tickets abiertos: no incluye historial cerrado."},
        "debe_contener": ["abierto"],
        "rf15": ["cerrado"],
        "no_debe": ["no tiene ningun ticket en su historial"],
    },
    {
        "area": "facturacion",
        "pregunta": "cuantas facturas pagadas hubo en julio 2026?",
        "herramienta": "consultar_agregado",
        "resultado": {
            "total": 4164,
            "interpretacion": ("Facturas con estado 'pagada', por fecha de "
                               "emision entre 2026-07-01 y 2026-07-31."),
        },
        "debe_contener": ["4164", "julio"],
        "no_debe": [],
    },

    # --- Fallo honesto: la herramienta devuelve error, no debe inventarse exito --
    #
    # Cada 'debe_contener' es UNA sola condicion: una tupla de frases alternas
    # (el modelo puede decirlo de varias formas validas; basta con UNA), y las
    # dos raices del verbo 'encontrar' (encontr- del preterito, encuentr- del
    # presente: "no se encontro" / "no se encuentra") porque el espanol
    # diptonga o->ue y las dos formas son igual de correctas.
    {
        "area": "soporte",
        "pregunta": "dame los datos del cliente 999999",
        "herramienta": "consultar_cliente",
        "resultado": {"error": "No se encontro ningun cliente con id_servicio 999999."},
        "debe_contener": [("no se encontr", "no se encuentr", "no existe")],
        "no_debe": ["activo", "suspendido", "id_servicio: 999999"],
    },
    {
        "area": "facturacion",
        "pregunta": "registra un pago de 40000 en la factura 555555",
        "herramienta": "registrar_pago",
        "resultado": {"error": "Fallo al llamar a WispHub: factura no existe."},
        "debe_contener": [("no se pudo", "no se registr", "fallo", "error", "no existe")],
        "no_debe": ["se registro el pago", "pago exitoso", "40000 registrado"],
    },
    {
        "area": "tecnica",
        "pregunta": "dame la ip del cliente con cedula 1082345678",
        "herramienta": "consultar_cliente_por_cedula",
        "resultado": {"error": "No se encontro ningun cliente con esa cedula."},
        "debe_contener": [("no se encontr", "no se encuentr", "no existe")],
        "no_debe": ["172.16", "la ip es"],
    },
    {
        "area": "facturacion",
        "pregunta": "cuanto debe el cliente 4821?",
        "herramienta": "consultar_facturas",
        "resultado": {"count": 0, "results": []},
        "debe_contener": [("no tiene", "no se encontr", "no se encuentr",
                          "al dia", "sin factura", "no registra")],
        "no_debe": ["127543"],
    },
    {
        "area": "soporte",
        "pregunta": "cuantos tickets nuevos hay?",
        "herramienta": "consultar_agregado",
        "resultado": {"error": "No se puede contar 'tickets_nuevos'. Entidades disponibles: clientes, facturas, tickets."},
        "debe_contener": [("no se puede", "no se pudo", "no puedo", "no puede",
                          "error", "no logr", "no dispon")],
        "no_debe": ["0 tickets", "hay 0"],
    },
]


# ==============================================================================
#  MEDICION
# ==============================================================================

# Precios por millon de tokens, agosto 2026. INDICATIVOS: este mercado se
# mueve semanalmente, hay que verificarlos con el proveedor antes de
# presupuestar. Local = 0: no hay costo por token.
PRECIOS = {
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro":   (0.28, 0.87),
}


def _costo(resp) -> float:
    """USD de esta llamada. 0 si el modelo corre local."""
    p = PRECIOS.get(resp.modelo)
    if not p:
        return 0.0
    return resp.tokens_entrada / 1e6 * p[0] + resp.tokens_salida / 1e6 * p[1]


def probar_herramientas(modelo):
    aciertos = herramienta_ok = args_ok = 0
    tiempos, tokens, pensados, velocidades, costos = [], [], [], [], []

    for caso in CASOS_HERRAMIENTA:
        mensajes = [{"role": "system", "content": sw.construir_system(caso["area"])},
                    {"role": "user", "content": caso["pregunta"]}]
        try:
            r = mc.chat(modelo, mensajes, tools=sw.herramientas_de(caso["area"]))
        except Exception as e:                      # modelo caido, OOM, red
            print(f"    ! {caso['pregunta'][:40]}: {str(e)[:70]}")
            continue
        tiempos.append(r.segundos); tokens.append(r.tokens_salida)
        pensados.append(r.razonamiento_chars); costos.append(_costo(r))
        if r.tok_s:
            velocidades.append(r.tok_s)

        nombre = r.llamadas[0].nombre if r.llamadas else None

        if nombre == caso["espera"]:
            herramienta_ok += 1
            if nombre is None:
                args_ok += 1
                aciertos += 1
            else:
                crudos = r.llamadas[0].argumentos
                bien = all(str(crudos.get(k, "")).strip().lower() == str(v).lower()
                           for k, v in caso["args"].items())
                args_ok += bien
                aciertos += bien

    n = len(CASOS_HERRAMIENTA)
    return {
        "casos": n,
        "herramienta_pct": round(100 * herramienta_ok / n, 1),
        "args_pct": round(100 * args_ok / n, 1),
        "s_medio": round(sum(tiempos) / len(tiempos), 2) if tiempos else 0,
        "tok_s": round(sum(velocidades) / len(velocidades), 1) if velocidades else 0,
        "think_medio": int(sum(pensados) / len(pensados)) if pensados else 0,
        "costo": sum(costos),
    }


def _cumple(item, texto, plano):
    """
    Un item de 'debe_contener' puede ser un string (exacto) o una tupla de
    ALTERNATIVAS: basta con que UNA aparezca.

    Hace falta porque el espanol conjuga con cambio de raiz ('encontrar' ->
    'encuentra' en presente, no comparte raiz con 'encontro'). Un modelo que
    responde con toda honestidad —"no se encuentra ningun registro"— fallaba
    la verificacion porque el string buscado era 'no se encontr', que solo
    cubre el preterito. El modelo estaba bien; el caso de prueba estaba mal.
    """
    alternativas = item if isinstance(item, (list, tuple)) else (item,)
    return any(a.lower().replace(".", "") in plano or a.lower() in texto
              for a in alternativas)


def probar_respeto(modelo):
    """Segunda llamada: ya tiene el dato, solo debe redactarlo."""
    respeta = rf15 = invento = 0
    tiempos, pensados, costos = [], [], []
    total_rf15 = sum(1 for c in CASOS_DATO if c.get("rf15"))

    for caso in CASOS_DATO:
        mensajes = [
            {"role": "system", "content": sw.construir_system(caso["area"])},
            {"role": "user", "content": caso["pregunta"]},
            # Formato canonico (el de OpenAI). nucleo/modelo/cliente.py lo
            # adapta a lo que exija cada proveedor: Ollama quiere 'arguments'
            # como diccionario, la API como cadena, y los modelos de
            # razonamiento exigen ademas 'reasoning_content'.
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "call_1", "type": "function",
                             "function": {"name": caso["herramienta"],
                                          "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call_1",
             "name": caso["herramienta"],
             "content": json.dumps(caso["resultado"], ensure_ascii=False)},
        ]
        try:
            r = mc.chat(modelo, mensajes)
        except Exception as e:
            print(f"    ! {caso['pregunta'][:40]}: {str(e)[:70]}")
            continue
        tiempos.append(r.segundos); pensados.append(r.razonamiento_chars)
        costos.append(_costo(r))

        texto = (r.contenido or "").lower()
        # Se quitan separadores de miles: '127.543' y '127,543' son el dato.
        plano = texto.replace(".", "").replace(",", "").replace(" ", "")

        if all(_cumple(d, texto, plano) for d in caso["debe_contener"]):
            respeta += 1
        if any(_cumple(d, texto, plano) for d in caso["no_debe"]):
            invento += 1
        if caso.get("rf15") and all(_cumple(x, texto, plano) for x in caso["rf15"]):
            rf15 += 1

    n = len(CASOS_DATO)
    return {
        "respeta_pct": round(100 * respeta / n, 1),
        "invento": invento,
        "rf15_pct": round(100 * rf15 / total_rf15, 1) if total_rf15 else 0,
        "s_medio": round(sum(tiempos) / len(tiempos), 2) if tiempos else 0,
        "think_medio": int(sum(pensados) / len(pensados)) if pensados else 0,
        "costo": sum(costos),
    }


def modelos_instalados():
    """Modelos LOCALES ya descargados. No aplica a proveedores por API."""
    try:
        import ollama                                    # import perezoso:
        datos = ollama.list()                             # mismo patron que
    except Exception as e:                                # nucleo/modelo/cliente.py
        raise SystemExit(f"No responde Ollama: {e}")
    out = []
    for m in datos.get("models", []):
        nombre = m.get("model") or m.get("name")
        if nombre:
            out.append(nombre)
    return out


if __name__ == "__main__":
    modelos = sys.argv[1:] or modelos_instalados()
    print(f"\nProbando {len(modelos)} modelo(s). Sin tocar la API de WispHub.\n")

    filas = []
    for modelo in modelos:
        print(f"  {modelo} ...", flush=True)
        h = probar_herramientas(modelo)
        r = probar_respeto(modelo)
        filas.append((modelo, h, r))
        print(f"     herramienta {h['herramienta_pct']}%  args {h['args_pct']}%  "
              f"respeta {r['respeta_pct']}%  {h['tok_s']} tok/s")

    print("\n" + "=" * 96)
    print(f"  {'modelo':<26} {'herram':>7} {'args':>6} {'respeta':>8} {'inv':>4} "
          f"{'RF-15':>6} {'tok/s':>7} {'s/turno':>8} {'think':>7} {'US$/1k':>8}")
    print("=" * 96)
    for modelo, h, r in filas:
        # Costo extrapolado a 1.000 consultas, para que sea comparable con el
        # volumen real (~300/dia) y no con los 11 casos de la prueba.
        n_casos = h["casos"] + 3
        por_mil = (h["costo"] + r["costo"]) / n_casos * 1000
        print(f"  {modelo:<26} {h['herramienta_pct']:>6.1f}% {h['args_pct']:>5.1f}% "
              f"{r['respeta_pct']:>7.1f}% {r['invento']:>4} {r['rf15_pct']:>5.1f}% "
              f"{h['tok_s']:>7.1f} {h['s_medio'] + r['s_medio']:>8.2f} "
              f"{h['think_medio']:>7} {por_mil:>8.2f}")
    print("=" * 96)
    print("""
  herram  : eligio la herramienta correcta (o ninguna, cuando corresponde)
  args    : ademas acerto los argumentos que definen la consulta
  respeta : repitio el dato que le dio la herramienta, sin alterarlo
  inv     : veces que INVENTO un dato. Tiene que ser 0. No hay margen aqui
  RF-15   : transmitio la interpretacion y la advertencia al colaborador
  think   : caracteres de razonamiento por turno, que se generan y se tiran
  US$/1k  : costo extrapolado a 1.000 consultas. 0 = corre local
""")
