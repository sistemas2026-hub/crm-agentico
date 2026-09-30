# -*- coding: utf-8 -*-
"""
NINGUNA CONEXION A POSTGRES SE QUEDA TOMADA ESPERANDO A ALGUIEN DE AFUERA.

LA REGLA, Y POR QUE
-------------------
Un turno tarda segundos: el modelo, WispHub, SmartOLT, Meta. Una conexion a
Postgres solo debe ocuparse durante operaciones CORTAS -- tomar, consultar,
soltar. Si una conexion queda retenida mientras se espera una llamada
externa, un pool no arregla nada: en vez de quedarse sin conexiones nuevas se
queda sin las del pool, y encima con todos los demas haciendo cola.

POR QUE ESTA PRUEBA SIGUE LAS LLAMADAS Y NO SOLO MIRA EL BLOQUE
---------------------------------------------------------------
La primera version de esta auditoria (22/09/2026) miraba unicamente las
llamadas ESCRITAS dentro del `with sesion(...)` y dio "ninguno". Era falso:
`ingesta.ingerir(cur, ...)` recibia el cursor y llamaba a OpenAI una vez por
fragmento, un nivel mas abajo. Un documento largo retenia la conexion
minutos.

Asi que esto sigue la cadena de llamadas dentro de `nucleo/`. Es una
aproximacion --resuelve por nombre, no por tipo-- y por eso puede senalar de
mas; no puede senalar de menos, que es lo que importa en una guarda.

    py -3.13 tests/test_conexiones_sin_espera.py
"""
import ast
import os
import pathlib
import sys

RAIZ = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Esperar a alguien de afuera. No es "toda llamada de red posible": son las
# que este sistema hace, nombradas por lo que aparece en el codigo.
EXTERNO = {
    "requests": "HTTP (WispHub / SmartOLT / Meta)",
    "httpx": "HTTP",
    "urlopen": "HTTP",
    "vectorizar": "embeddings (OpenAI)",
    "enviar_texto": "WhatsApp (Meta)",
    "enviar_plantilla": "WhatsApp (Meta)",
    "marcar_leido": "WhatsApp (Meta)",
    "responder": "el modelo",
    "sleep": "una espera explicita",
}

# Lo que NO cuenta aunque el nombre coincida. Cada uno con su motivo: son
# funciones locales que comparten nombre con algo de afuera.
PERDONADOS = {
    # 'responder' del motor es el bucle del agente y NUNCA corre con una
    # conexion abierta -- esta prueba lo comprobaria igual, pero el nombre
    # aparece en helpers locales de la API que solo arman texto.
    "jsonify", "Response", "make_response",
}


def nombre_de(nodo):
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        base = nombre_de(nodo.value)
        return f"{base}.{nodo.attr}" if base else nodo.attr
    return ""


def es_externa(llamada: str):
    hoja = llamada.split(".")[-1]
    raiz = llamada.split(".")[0]
    if hoja in PERDONADOS:
        return None
    for clave, que in EXTERNO.items():
        if hoja == clave or raiz == clave:
            return que
    return None


# ── mapa de funciones de nucleo/: nombre -> las llamadas que hace ───────────
funciones = {}
bloques = []

for archivo in sorted(RAIZ.joinpath("nucleo").rglob("*.py")):
    rel = archivo.relative_to(RAIZ).as_posix()
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))

    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            llamadas = {nombre_de(x.func) for x in ast.walk(n) if isinstance(x, ast.Call)}
            funciones.setdefault(n.name, set()).update(llamadas)

        if isinstance(n, ast.With):
            abre = any(
                isinstance(i.context_expr, ast.Call)
                and nombre_de(i.context_expr.func) in ("sesion", "persistencia.sesion")
                for i in n.items)
            if abre:
                bloques.append({
                    "donde": f"{rel}:{n.lineno}",
                    "llamadas": {nombre_de(x.func)
                                 for s in n.body for x in ast.walk(s)
                                 if isinstance(x, ast.Call)},
                })


def alcanza_externo(llamadas, profundidad=4):
    """La primera llamada externa que se alcanza desde este conjunto."""
    vistas = set()
    frontera = set(llamadas)
    for _ in range(profundidad):
        siguiente = set()
        for llamada in frontera:
            que = es_externa(llamada)
            if que:
                return llamada, que
            hoja = llamada.split(".")[-1]
            if hoja in vistas:
                continue
            vistas.add(hoja)
            siguiente |= funciones.get(hoja, set())
        if not siguiente:
            break
        frontera = siguiente
    return None, None


print(f"\n  {len(bloques)} bloques con una conexion abierta, "
      f"sobre {len(funciones)} funciones de nucleo/\n")

malos = []
for b in bloques:
    llamada, que = alcanza_externo(b["llamadas"])
    if llamada:
        malos.append((b["donde"], llamada, que))

for donde, llamada, que in malos:
    print(f"  [FALLA] {donde}")
    print(f"          alcanza {llamada}()  ->  {que}")

if malos:
    print(f"\n[FALLA] {len(malos)} bloque(s) retienen una conexion esperando a "
          f"un sistema externo.")
    print("        Hay que partirlos: consultar, soltar, esperar afuera, volver "
          "a tomar para escribir.")
    sys.exit(1)

print("  [ok] ninguna conexion abierta alcanza una llamada externa, ni directa")
print("       ni a traves de un ayudante")
print("\n[OK] Las conexiones se toman para consultar y se sueltan antes de esperar.")
