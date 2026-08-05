# -*- coding: utf-8 -*-
"""
================================================================================
 INFORME DE MATERIALES  -  consumo registrado por los tecnicos en los tickets
================================================================================

De donde sale el dato
---------------------
WispHub NO tiene modulo de materiales: '/api/gastos/' existe pero esta vacio y
el ticket no trae ningun campo de inventario. Lo que si hay es un formulario
"Firma de Ticket" que el tecnico diligencia al cerrar, dentro del campo
'respuestas' del detalle del ticket, con un catalogo FIJO de 16 materiales:

    MATERIAL Y CANTIDAD
    ONU CATV            1
    CONECTOR APC        2
    CABLE DROP          20m
    ...

Por que aqui no interviene el modelo
------------------------------------
El formulario es etiqueta -> valor, no prosa. Eso se parsea con codigo y de
forma determinista: no hay nada que interpretar y por lo tanto nada que
alucinar. El modelo, si acaso, redacta el texto ALREDEDOR de estos numeros;
los numeros los produce este archivo. Es la misma regla de PRD 12.5.

Que tan completo es (medido sobre julio 2026, 2.727 tickets cerrados)
---------------------------------------------------------------------
El diligenciamiento depende del tipo de trabajo, y hay que leerlo asi:

    trabajo de campo real        86% - 100%   (instalaciones, cambios de
                                               router, danos de fibra...)
    gestiones sin visita            0%        (no contesta, acuerdo de pago,
                                               encuestas, facturacion)

El 0% de la segunda fila NO es incumplimiento: ahi no se gasto material porque
nadie fue a ningun lado. Por eso el informe reporta la cobertura POR CATEGORIA
y no un porcentaje global, que mezclaria las dos cosas y enganaria.

Costo
-----
Requiere el detalle de cada ticket: ~2.700 llamadas para un mes, unos 10
minutos. Es un proceso POR LOTES (de noche, o bajo demanda), nunca una
herramienta interactiva.

Uso
---
    py -3.13 informe_materiales.py 2026-07
    py -3.13 informe_materiales.py 2026-07-01 2026-07-31
================================================================================
"""

import os
import re
import sys
import json
import calendar
from html import unescape
from datetime import datetime
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("AVISO: falta python-dotenv.")

BASE = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
KEY = os.environ.get("WISPHUB_API_KEY")
if not KEY:
    raise SystemExit("ERROR: falta WISPHUB_API_KEY en el .env")

HEADERS = {"Authorization": f"Api-Key {KEY}", "Content-Type": "application/json"}

ESTADO_CERRADO = 4       # verificado: el filtro de estado es NUMERICO
HILOS = 5                # moderado: es la API de produccion
POR_PAGINA = 100

# Catalogo fijo del formulario, en el orden en que aparece.
CATALOGO = [
    "ONU CATV", "ONU WIFI", "CONECTOR APC", "CONECTOR UPC", "CONECTOR COAXIAL",
    "SPLITTER DE TV 1X2", "SPLITTER DE TV 1X3", "CHAZO", "TORNILLO",
    "PRECINTO", "TENSOR", "TDT", "CABLE COAXIAL", "CABLE DROP", "CARGADOR",
    "OTRO:",
]
# El formulario sigue con estas secciones; ahi termina la lista de materiales.
FIN_SECCION = ("RECIBE LA VISITA", "EVIDENCIA")

# Frases que los tecnicos escriben en vez de un numero. Se traducen SOLO cuando
# el significado es inequivoco; cualquier otra cosa se reporta sin tocar.
# 'Tenia cableado' significa que el cliente ya tenia: no se consumio nada.
EQUIVALENCIAS = {
    "tenia cableado": 0.0,
    "tenia cable": 0.0,
    "tenia splitter": 0.0,
    "ya tenia": 0.0,
    "no": 0.0,
    "ninguno": 0.0,
    "n/a": 0.0,
    "na": 0.0,
    "medio metro": 0.5,
    "medio metros": 0.5,
    "metro y medio": 1.5,
}

RE_ID_LARGO = re.compile(r"\d{7,}")      # cedulas/telefonos embebidos
RE_NUMERO = re.compile(r"^(\d+(?:\.\d+)?)")


# ==============================================================================
#  PARSEO DEL FORMULARIO  (determinista, sin modelo)
# ==============================================================================

def _a_lineas(texto_html):
    """
    HTML del formulario -> lineas limpias.

    Se enmascaran de una vez los identificadores largos: el campo es texto
    libre y puede traer cedula o telefono embebidos (mismo riesgo que
    'descripcion', ver soporte_wisphub.py). Al informe solo deben llegar
    materiales y cantidades, nunca datos de una persona.
    """
    # Las entidades se DECODIFICAN, no se borran: reemplazarlas por un espacio
    # partia las palabras acentuadas ('Ten&iacute;a' -> 'Ten a') y con eso
    # 'Tenia cableado' dejaba de casar con la tabla de equivalencias y caia a
    # revision manual. Primero se quitan las etiquetas y despues se decodifica,
    # para que un '&lt;' del texto no genere una etiqueta falsa.
    t = re.sub(r"<[^>]+>", "\n", texto_html or "")
    t = unescape(t).replace("\xa0", " ")
    t = RE_ID_LARGO.sub("***", t)
    return [l.strip() for l in t.split("\n") if l.strip()]


def _norm(s):
    s = (s or "").upper().strip()
    for a, b in (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"),
                 ("Ú", "U"), ("Ñ", "N")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s)


def parsear_formulario(html):
    """
    Extrae {material: valor_crudo} del formulario.

    Devuelve None si no hay formulario, {} si esta en blanco.

    La estructura es una etiqueta por linea y su valor en la siguiente. Si la
    linea siguiente es OTRA etiqueta del catalogo, ese material quedo sin
    diligenciar y no se inventa un cero: simplemente no aparece.
    """
    lineas = _a_lineas(html)
    normal = [_norm(l) for l in lineas]
    try:
        i = next(k for k, l in enumerate(normal) if "MATERIAL Y CANTIDAD" in l)
    except StopIteration:
        return None

    out = {}
    for k in range(i + 1, len(normal)):
        if any(f in normal[k] for f in FIN_SECCION):
            break
        if normal[k] in CATALOGO:
            sig = normal[k + 1] if k + 1 < len(normal) else ""
            es_etiqueta = sig in CATALOGO or any(f in sig for f in FIN_SECCION)
            if sig and not es_etiqueta:
                out[normal[k]] = lineas[k + 1].strip()
    return out


def normalizar_cantidad(texto):
    """
    Valor crudo -> (cantidad, motivo_si_no_se_pudo).

    Regla: ante la duda NO se inventa un numero. Un total inflado por una
    suposicion es peor que un total con una nota de que falta revisar.
    """
    v = (texto or "").strip().replace(",", ".")
    if not v:
        return None, "vacio"

    m = RE_NUMERO.match(v)              # "20m", "2", "0.5 mts"
    if m:
        return float(m.group(1)), None

    clave = _norm(v).lower()
    for frase, cantidad in EQUIVALENCIAS.items():
        if clave.startswith(frase):
            return cantidad, None

    return None, texto.strip()


# ==============================================================================
#  LECTURA DE LA API
# ==============================================================================

_sesion = requests.Session()
_sesion.headers.update(HEADERS)


def listar_cerrados(desde, hasta):
    """Todos los tickets cerrados creados en el periodo."""
    todos, offset = [], 0
    while True:
        r = _sesion.get(BASE + "/api/tickets/", timeout=40,
                        params={"limit": POR_PAGINA, "offset": offset,
                                "estado": ESTADO_CERRADO,
                                "fecha_creacion_0": desde,
                                "fecha_creacion_1": hasta})
        r.raise_for_status()
        p = r.json()
        filas = p.get("results", []) if isinstance(p, dict) else p
        if not filas:
            break
        todos.extend(filas)
        offset += POR_PAGINA
        if len(todos) >= (p.get("count") or 0):
            break
    return todos


def _leer_ticket(t):
    """(categoria, materiales|None). None = no hay formulario diligenciado."""
    categoria = (t.get("razon_falla") or "sin clasificar").strip()
    try:
        d = _sesion.get(f"{BASE}/api/tickets/{t['id_ticket']}/", timeout=40).json()
    except (requests.RequestException, ValueError):
        return categoria, None, t.get("id_ticket")

    for item in (d.get("respuestas") or []):
        txt = item.get("respuesta", "") if isinstance(item, dict) else str(item)
        form = parsear_formulario(txt)
        if form:
            return categoria, form, t.get("id_ticket")
    return categoria, None, t.get("id_ticket")


# ==============================================================================
#  INFORME
# ==============================================================================

def generar(desde, hasta, progreso=True):
    tickets = listar_cerrados(desde, hasta)
    if progreso:
        print(f"  {len(tickets)} tickets cerrados. Leyendo detalle...")

    totales = Counter()
    por_categoria = defaultdict(lambda: [0, 0])     # [total, con_registro]
    sin_normalizar = []
    con_registro = 0
    todo_cero = 0

    with ThreadPoolExecutor(max_workers=HILOS) as ex:
        for n, (cat, form, tid) in enumerate(ex.map(_leer_ticket, tickets), 1):
            por_categoria[cat][0] += 1
            if not form:
                continue
            con_registro += 1
            por_categoria[cat][1] += 1

            hubo_consumo = False
            for material, crudo in form.items():
                cantidad, motivo = normalizar_cantidad(crudo)
                if cantidad is None:
                    sin_normalizar.append(
                        {"ticket": tid, "material": material, "valor": motivo})
                    hubo_consumo = True      # hay ALGO escrito, no es un cero
                elif cantidad > 0:
                    totales[material] += cantidad
                    hubo_consumo = True
            todo_cero += (not hubo_consumo)

            if progreso and n % 500 == 0:
                print(f"    ...{n}/{len(tickets)}")

    return {
        "periodo": f"{desde} a {hasta}",
        "totales": dict(totales.most_common()),
        "tickets_cerrados": len(tickets),
        "con_registro_de_material": con_registro,
        "registros_en_cero": todo_cero,
        "cobertura_por_categoria": {
            c: {"tickets": v[0], "con_registro": v[1],
                "pct": round(100 * v[1] / v[0], 1) if v[0] else 0.0}
            for c, v in sorted(por_categoria.items(), key=lambda x: -x[1][0])
        },
        "sin_normalizar": sin_normalizar,
        "interpretacion": (
            f"Materiales registrados por los tecnicos al cerrar tickets creados "
            f"entre {desde} y {hasta}. Los totales salen del formulario 'Firma "
            f"de Ticket'; los calculo este script, no un modelo."),
        "advertencia": (
            "Este informe refleja lo REGISTRADO, no lo realmente consumido: un "
            "trabajo sin formulario diligenciado no aparece, asi que el total "
            "SUBESTIMA en una proporcion desconocida. Sirve para tendencias y "
            "comparaciones entre periodos; NO sirve para cuadrar inventario ni "
            "para costeo contable. Revise la cobertura por categoria: un 0% en "
            "gestiones sin visita (no contesta, acuerdos de pago, encuestas) es "
            "correcto, porque ahi no se gasta material."),
    }


def imprimir(inf):
    print("\n" + "=" * 70)
    print(f"  INFORME DE MATERIALES  -  {inf['periodo']}")
    print("=" * 70)

    print("\n  CONSUMO REGISTRADO")
    if inf["totales"]:
        for material, cantidad in inf["totales"].items():
            print(f"    {material:<24} {cantidad:>10,.1f}")
    else:
        print("    (sin registros)")

    print(f"\n  Tickets cerrados            : {inf['tickets_cerrados']}")
    print(f"  Con registro de material    : {inf['con_registro_de_material']}")
    print(f"    de esos, todo en cero     : {inf['registros_en_cero']}"
          f"   (se reviso y no se cambio nada)")

    print("\n  COBERTURA POR CATEGORIA  (>=10 tickets)")
    for cat, v in inf["cobertura_por_categoria"].items():
        if v["tickets"] >= 10:
            print(f"    {cat[:34]:<36} {v['con_registro']:>4}/{v['tickets']:<5}"
                  f" {v['pct']:>5.1f}%")

    if inf["sin_normalizar"]:
        print(f"\n  A REVISAR - valores sin cantidad clara "
              f"({len(inf['sin_normalizar'])}). No se les invento un numero:")
        vistos = Counter((s["material"], s["valor"]) for s in inf["sin_normalizar"])
        for (mat, val), n in vistos.most_common(12):
            print(f"    x{n:<3} {mat:<22} -> {val!r}")

    print(f"\n  {inf['advertencia']}\n")


def _periodo_de_argumentos(args):
    if len(args) == 1 and re.fullmatch(r"\d{4}-\d{2}", args[0]):
        anio, mes = int(args[0][:4]), int(args[0][5:7])
        ultimo = calendar.monthrange(anio, mes)[1]
        return f"{anio:04d}-{mes:02d}-01", f"{anio:04d}-{mes:02d}-{ultimo:02d}"
    if len(args) == 2:
        for f in args:
            datetime.strptime(f, "%Y-%m-%d")     # valida o revienta
        return args[0], args[1]
    raise SystemExit(
        "Uso:  py -3.13 informe_materiales.py 2026-07\n"
        "      py -3.13 informe_materiales.py 2026-07-01 2026-07-31")


if __name__ == "__main__":
    desde, hasta = _periodo_de_argumentos(sys.argv[1:])
    print(f"\nGenerando informe de {desde} a {hasta}...")
    informe = generar(desde, hasta)
    imprimir(informe)

    salida = f"informe_materiales_{desde}_{hasta}.json"
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=2)
    print(f"  JSON guardado en: {salida}\n")
