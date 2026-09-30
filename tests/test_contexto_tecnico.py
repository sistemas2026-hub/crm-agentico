# -*- coding: utf-8 -*-
"""
Con QUE servicio se resuelve la ficha tecnica de un caso.

    py -3.13 tests/test_contexto_tecnico.py

POR QUE EXISTE
--------------
Hasta el 10/09/2026 la ficha tecnica de un ticket colgaba de la conversacion
que lo habia originado: 'GET /conversaciones/por-caso/<id>' buscaba esa fila y,
si no existia, devolvia None y ni siquiera intentaba armar nada. Los casos
importados del sistema del ISP no tienen conversacion -- 49 de ellos en
produccion -- asi que ninguno mostraba cliente ni equipo.

La identidad ya estaba guardada ('Case.external_service_id', desde la Fase 1) y
no la leia nadie: tres apariciones en todo el repositorio, las tres de
escritura.

Lo que se prueba aca es la DECISION de identidad, que es pura: no hay red, ni
base, ni Flask. Los efectos (llamar al proveedor, leer la ONU) tienen sus
propias pruebas y no se repiten.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


# El modulo entero importa Flask y medio motor. Se lee el archivo y se ejecuta
# solo lo que hace falta -- las dos funciones de decision son puras y no
# dependen de nada de lo de arriba.
import ast  # noqa: E402

FUENTE = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
arbol = ast.parse(FUENTE)
espacio: dict = {}
for nodo in arbol.body:
    if isinstance(nodo, ast.FunctionDef) and nodo.name == "identidad_del_contexto":
        exec(compile(ast.Module([nodo], []), "<api>", "exec"), espacio)
    elif isinstance(nodo, ast.Assign) and getattr(
            nodo.targets[0], "id", "").startswith("IDENTIDAD_"):
        exec(compile(ast.Module([nodo], []), "<api>", "exec"), espacio)

identidad_del_contexto = espacio["identidad_del_contexto"]
CASE = espacio["IDENTIDAD_CASE"]
CONV = espacio["IDENTIDAD_CONVERSACION"]


def conversacion(id_cliente="", sn_onu=""):
    return {"id_cliente": id_cliente, "datos_sesion": {"sn_onu": sn_onu}}


# ==========================================================================
#  A. EL CASO IMPORTADO SE RESUELVE SOLO
# ==========================================================================
print("\nun caso sin conversacion ya no se queda sin ficha")

r = identidad_del_contexto(None, "1578")
revisar(r["id_servicio"] == "1578" and r["origen"] == CASE,
        "sin conversacion, manda el servicio del caso",
        f"{r}")
revisar(r["conflicto"] is None, "y no hay ningun conflicto que informar")
revisar(r["sn_onu_respaldo"] == "",
        "sin serial de respaldo: no hay conversacion de donde sacarlo")


# ==========================================================================
#  B. LO DE SIEMPRE SIGUE FUNCIONANDO
# ==========================================================================
print("\nun caso nacido de un chat se comporta igual que antes")

r = identidad_del_contexto(conversacion("5612", "CDTC50149356"), "")
revisar(r["id_servicio"] == "5612" and r["origen"] == CONV,
        "sin servicio en el caso, manda el de la conversacion")
revisar(r["sn_onu_respaldo"] == "CDTC50149356",
        "y el serial de la sesion viaja como respaldo",
        "es el mismo servicio, asi que el serial es de ese cliente")


# ==========================================================================
#  C. LOS DOS, Y COINCIDEN
# ==========================================================================
print("\nlos dos origenes de acuerdo")

r = identidad_del_contexto(conversacion("1578", "CDTC50149356"), "1578")
revisar(r["id_servicio"] == "1578" and r["origen"] == CASE,
        "gana el del caso (da igual, dicen lo mismo)")
revisar(r["conflicto"] is None, "sin conflicto")
revisar(r["sn_onu_respaldo"] == "CDTC50149356",
        "el serial de la sesion SI vale: es el mismo servicio")


# ==========================================================================
#  D. LOS DOS, Y SE CONTRADICEN  --  lo que mas importa
# ==========================================================================
print("\nlos dos origenes en desacuerdo")

r = identidad_del_contexto(conversacion("5612", "CDTC50149356"), "1578")
revisar(r["id_servicio"] == "1578" and r["origen"] == CASE,
        "gana el del caso: lo dijo el proveedor sobre ESE ticket")
revisar(r["conflicto"] == {"case": "1578", "conversacion": "5612"},
        "y la discrepancia sale como dato, con los dos identificadores",
        f"{r['conflicto']}")
revisar(r["sn_onu_respaldo"] == "",
        "el serial de la conversacion NO se arrastra",
        "es el equipo del OTRO servicio: mostrarlo daria niveles opticos "
        "ajenos con cara de dato correcto, y justo cuando ya sabemos que "
        "algo no cuadra")


# ==========================================================================
#  E. NINGUNO
# ==========================================================================
print("\nsin ninguna identidad")

for caso, etiqueta in ((None, "sin conversacion y sin servicio"),
                       (conversacion(), "conversacion sin cliente identificado"),
                       (conversacion(""), "id_cliente vacio")):
    r = identidad_del_contexto(caso, "")
    revisar(r["id_servicio"] == "" and r["origen"] == "" and not r["conflicto"],
            f"{etiqueta}: no se resuelve nada, y no es un error")


# ==========================================================================
#  F. NADA DE APROXIMACIONES
# ==========================================================================
print("\nnunca se elige por parecido")

r = identidad_del_contexto(conversacion("1578"), " 1578 ")
revisar(r["conflicto"] is None,
        "los espacios alrededor no inventan una discrepancia",
        "el identificador llega de una URL y de una base; recortarlo es "
        "normalizar, no adivinar")

r = identidad_del_contexto(conversacion("1578"), "15780")
revisar(r["conflicto"] is not None,
        "pero '15780' NO es '1578': un digito de mas es otro cliente",
        "aca es donde un 'parecido' abriria la ficha de otra persona")


# ==========================================================================
#  G. LA FUNCION NO SABE QUE EXISTE UN CASE
# ==========================================================================
print("\nel nucleo sigue sin conocer al CRM")

# El CODIGO, sin el docstring: la explicacion de por que la funcion no conoce
# el CRM nombra al CRM, y una comprobacion que se tropieza con su propia prosa
# no comprueba nada.
_fn = next(n for n in arbol.body
           if isinstance(n, ast.FunctionDef) and n.name == "contexto_tecnico")
_sin_doc = _fn.body[1:] if ast.get_docstring(_fn) else _fn.body
cuerpo = "\n".join(ast.unparse(n) for n in _sin_doc)
for prohibido in ("Case", "cases_case", "django", "models."):
    revisar(prohibido not in cuerpo,
            f"'contexto_tecnico' no menciona '{prohibido}'",
            "recibe identificadores, no modelos: por eso puede servir igual "
            "al CRM, a una orden de trabajo y a la API de campo")
revisar("id_servicio" in cuerpo and "identidad" in cuerpo,
        "recibe la identidad ya resuelta y no vuelve a decidirla")


# ==========================================================================
#  H. EL SERIAL SE RELEE, NO SE GUARDA
# ==========================================================================
print("\nel serial no se persiste en ningun lado")

revisar('"sn_onu"' in FUENTE.split("_CAMPOS_FICHA = ")[1].split(")")[0],
        "'sn_onu' esta en la lista blanca de la ficha del cliente",
        "es de donde sale ahora, en vivo, en cada apertura")

modelo = (RAIZ / "django-crm" / "backend" / "cases" / "models.py").read_text(
    encoding="utf-8")
revisar("sn_onu" not in modelo and "onu_sn" not in modelo,
        "y NO hay ninguna columna de serial en el Case",
        "guardarlo haria de Dexter una segunda fuente de verdad de un dato "
        "ajeno, con la obligacion de mantener las dos iguales")

vista = FUENTE.split("def conversacion_por_caso(")[1].split("\ndef ")[0]
revisar("if not datos:" not in vista,
        "la ruta ya no corta cuando no hay conversacion",
        "ese 'return' temprano era el acoplamiento entero")
revisar('"contexto"' in vista and '"conversacion"' in vista,
        "y devuelve las dos cosas por separado",
        "de donde vino el caso y que hay del otro lado son preguntas "
        "distintas; estaban pegadas porque la segunda solo se podia "
        "responder a traves de la primera")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La identidad se resuelve sin conversacion, sin adivinar y sin guardar el serial.")
