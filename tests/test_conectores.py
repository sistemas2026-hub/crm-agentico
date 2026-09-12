# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE CONECTORES  --  lo que se entrega hecho, y lo que sigue siendo humano
================================================================================

Un conector empaqueta el conocimiento de una API que ya se verifico: que filtro
funciona, cual la API acepta y despues IGNORA en silencio devolviendo el
universo entero, y que campos puede ver cada area de un registro que trae 54,
cuatro de ellos contraseñas.

Eso es lo que hace valioso al conector y lo que lo vuelve peligroso: entrega
acceso a datos de clientes. Aca se fija que lo entregue bien.

Lo que se fija
--------------
1. LAS LISTAS BLANCAS VIAJAN, Y NINGUNA TRAE CONTRASEÑAS. Un conector sin
   listas blancas daria acceso sin limites al registro completo. Esa decision
   -- que ve cada area -- costo pensarla y no se vuelve a tomar en cada alta.

2. UN AREA SIN MAPEAR NO ENTRA. Es mejor conectar la mitad a proposito que
   asignarle datos de cliente a un rol que nadie eligio.

3. NO SE PISA LO QUE YA EXISTE. Una herramienta con nombre repetido se saltea
   y se informa. Quiza alguien la afino a mano contra su instancia.

4. DOS AREAS AL MISMO ROL UNEN SUS CAMPOS, no se pisan. Si 'soporte' y
   'facturacion' mapean al mismo rol, ese rol ve la union -- no lo que quedo
   ultimo en el bucle.

5. UN ROL QUE NO EXISTE SE RECHAZA ANTES DE ESCRIBIR NADA.

6. EL id NO PUEDE SALIR DE LA CARPETA DE CONECTORES. '../../algo' es una ruta,
   no un identificador.

7. EL RESULTADO VALIDA CONTRA EL ESQUEMA REAL. Es lo unico que prueba que el
   conector produce una configuracion utilizable y no un YAML con buena pinta.

Corre SIN BASE DE DATOS y sin red.
================================================================================
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml                                                        # noqa: E402

from nucleo.conectores import catalogo                             # noqa: E402
from nucleo.config.schema import TenantConfig                      # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


def tenant_nuevo() -> tuple[dict, TenantConfig]:
    """Una empresa recien dada de alta: sus roles, sin ninguna herramienta.

    Se parte de una configuracion REAL y se le sacan las herramientas, en vez
    de inventar un tenant de laboratorio: asi el test se rompe si el esquema
    cambia de forma, que es justo cuando hay que mirarlo.
    """
    doc = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "tenants" / "rapilink.config.yaml")
        .read_text(encoding="utf-8"))
    d = copy.deepcopy(doc)
    d["herramientas"] = []
    for r in d["roles"].values():
        r["puede_consultar"] = []
        r["campos_permitidos"] = {}
    # Las reglas que nombran herramientas tampoco existen en un alta nueva.
    for _ in range(12):
        try:
            return d, TenantConfig(**d)
        except Exception as e:                                     # noqa: BLE001
            m = re.search(r"escalamiento\.(\w+)", str(e))
            if not m:
                raise
            d.get("escalamiento", {}).pop(m.group(1), None)
    raise AssertionError("no se pudo construir un tenant nuevo valido")


TODAS = ("soporte", "facturacion", "administracion",
         "facturacion_cliente", "soporte_tecnico_cliente", "ventas")


print("\n== 1 y 7. lo que entrega, y que el resultado sirva ==")
doc, cfg = tenant_nuevo()
afirmar(len(cfg.herramientas) == 0, "el tenant nuevo arranca sin herramientas")

plan = catalogo.preparar("wisphub", {a: a for a in TODAS}, cfg)
catalogo._mutar_aplicar(doc, plan)
final = TenantConfig(**doc)          # <- si esto lanza, el conector no sirve
afirmar(len(final.herramientas) >= 20,
        f"aplicar wisphub deja {len(final.herramientas)} herramientas y VALIDA")

con_filtros = sum(1 for h in final.herramientas if h.filtros_verificados)
con_ignorados = sum(1 for h in final.herramientas if h.filtros_ignorados_por_api)
afirmar(con_filtros >= 15,
        f"{con_filtros} herramientas llegan con sus filtros ya verificados")
afirmar(con_ignorados >= 1,
        f"{con_ignorados} documentan filtros que la API IGNORA en silencio")

campos = {c for r in final.roles.values()
          for cs in r.campos_permitidos.values() for c in cs}
afirmar(bool(campos), "las listas blancas de campos viajan con el conector")
afirmar(not [c for c in campos if "password" in c],
        "NINGUNA lista blanca trae una contraseña")


print("\n== 2. un area sin mapear no entra ==")
doc2, cfg2 = tenant_nuevo()
solo_soporte = catalogo.preparar("wisphub", {"soporte": "soporte"}, cfg2)
nombres_solo = {h["nombre"] for h in solo_soporte["nuevas"]}
nombres_todas = {h["nombre"] for h in plan["nuevas"]}
afirmar(nombres_solo < nombres_todas,
        f"mapeando un area entran {len(nombres_solo)}, con todas {len(nombres_todas)}")
afirmar(all(h["roles_permitidos"] == ["soporte"] for h in solo_soporte["nuevas"]),
        "y ninguna queda asignada a un rol que no se mapeo")


print("\n== 3. no se pisa lo que ya existe ==")
repetido = catalogo.preparar("wisphub", {a: a for a in TODAS}, final)
afirmar(not repetido["nuevas"] and len(repetido["salteadas"]) >= 20,
        f"aplicarlo dos veces no agrega nada: {len(repetido['salteadas'])} salteadas")


print("\n== 4. dos areas al mismo rol UNEN sus campos ==")
doc3, cfg3 = tenant_nuevo()
junto = catalogo.preparar("wisphub", {"soporte": "soporte",
                                      "facturacion": "soporte"}, cfg3)
sep_s = catalogo.preparar("wisphub", {"soporte": "soporte"}, cfg3)
sep_f = catalogo.preparar("wisphub", {"facturacion": "soporte"}, cfg3)
# 'consultar_cliente' existe en las dos areas con listas distintas.
u = set(junto["campos_por_rol"]["soporte"].get("consultar_cliente", []))
s = set(sep_s["campos_por_rol"]["soporte"].get("consultar_cliente", []))
f = set(sep_f["campos_por_rol"]["soporte"].get("consultar_cliente", []))
afirmar(u == (s | f) and len(u) > max(len(s), len(f)) - 1,
        f"el rol recibe la union ({len(u)}), no la ultima area procesada "
        f"({len(s)} / {len(f)})")


print("\n== 5 y 6. lo que se rechaza antes de escribir ==")
try:
    catalogo.preparar("wisphub", {"soporte": "rol_que_no_existe"}, cfg)
    afirmar(False, "un rol inexistente se rechaza")
except catalogo.ErrorConector as e:
    afirmar("no existen en el tenant" in str(e), "un rol inexistente se rechaza")

for malicioso in ("../../etc/passwd", "..\\..\\secreto", "no_existe"):
    try:
        catalogo.leer(malicioso)
        afirmar(False, f"'{malicioso[:18]}' se rechaza")
    except catalogo.ErrorConector:
        afirmar(True, f"'{malicioso[:18]}' se rechaza")


print("\n== el listado no arrastra las definiciones ==")
# Una pantalla para elegir no necesita 29 definiciones completas; mandarlas
# convierte una lista en una descarga de decenas de KB.
lista = catalogo.listar()
afirmar(bool(lista), f"hay {len(lista)} conector(es) disponible(s)")
afirmar(all("herramientas" not in c for c in lista),
        "el listado trae el conteo, no las definiciones")
afirmar(all(c.get("secretos") is not None for c in lista),
        "cada conector declara que credenciales pide")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Un conector entrega el conocimiento de la API sin entregar los datos.")
