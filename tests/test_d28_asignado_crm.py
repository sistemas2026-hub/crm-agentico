# -*- coding: utf-8 -*-
"""
================================================================================
 D28 -- QUIEN FIGURA ATENDIENDO EL CASO EN EL CRM
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_d28_asignado_crm.py

LO QUE ESTE ARCHIVO PROTEGE, en orden de lo que costaria

  1. QUE NADIE DESAPAREZCA DEL CASO. El CRM guarda un CONJUNTO de asignados y
     no un dueño. Si un supervisor sumo un segundo tecnico esta manana, la
     sincronizacion no puede borrarlo -- y el CRM no guarda quien creo cada
     relacion, asi que no hay forma de distinguirlo de una asignacion vieja.
     Se preserva y se muestra, nunca se limpia.

  2. QUE LA IDENTIDAD SE CRUCE POR ID. Dos personas pueden llamarse igual. Un
     nombre que coincide no prueba nada, y actuar sobre esa coincidencia asigna
     el caso a quien no es.

  3. QUE UN 200 NO SE CONFUNDA CON EL EFECTO. El endpoint masivo del CRM
     responde 200 y deja el caso SIN NADIE cuando el perfil no resuelve. Se
     relee siempre; si no se confirma, es 'incierto', nunca 'exito'.

  4. QUE EL CRM NO MANDE. Un cambio hecho alla no mueve el operador durable de
     Dexter, pase lo que pase.
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
    else:
        print(f"  [FALLA] {que}", flush=True)
        if porque:
            print(f"         {porque}", flush=True)
        fallos.append(que)


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


from nucleo.relevo import asignados_crm                          # noqa: E402
from nucleo.relevo import efectos_externos                       # noqa: E402

# Perfiles tal como los devuelve el CRM (ProfileSerializer).
ANA = {"id": "perfil-ana", "user_details": {"id": "user-ana", "name": "Ana Gomez"}}
LUIS = {"id": "perfil-luis", "user_details": {"id": "user-luis", "name": "Luis Paz"}}
# Mismo NOMBRE que Ana, otra persona. Existe solo para esta prueba.
OTRA_ANA = {"id": "perfil-ana-2", "user_details": {"id": "user-ana-2", "name": "Ana Gomez"}}


# =============================================================================
titulo("1. la identidad se cruza por id, nunca por nombre")
# =============================================================================

revisar(asignados_crm.perfil_de_usuario([ANA, LUIS], "user-ana") == ANA,
        "el perfil se encuentra por el User.id")

# Dos personas con el mismo nombre. Si se cruzara por nombre, cualquiera de las
# dos podria ganar segun el orden de la lista.
encontrado = asignados_crm.perfil_de_usuario([OTRA_ANA, ANA], "user-ana")
revisar(encontrado == ANA,
        "dos personas con el MISMO nombre no se confunden",
        "Un nombre que coincide no prueba identidad; el id si.")

revisar(asignados_crm.perfil_de_usuario([ANA], "user-nadie") is None,
        "un usuario sin perfil en esta organizacion devuelve None")
revisar(asignados_crm.perfil_de_usuario([ANA], "") is None,
        "sin usuario no se resuelve nada")

# Y el modulo no mira nombres en ningun lado.
fuente = (RAIZ / "nucleo" / "relevo" / "asignados_crm.py").read_text(encoding="utf-8")
codigo = "\n".join(l for l in fuente.splitlines()
                   if not l.strip().startswith("#"))
codigo = codigo.split('"""')[0] + '"""'.join(codigo.split('"""')[2:])
revisar('"name"' not in codigo and "'name'" not in codigo,
        "el codigo no lee el campo 'name' en ningun momento",
        "Afirmado sobre el codigo, no sobre el archivo: el docstring habla de "
        "nombres para explicar por que NO se usan.")


# =============================================================================
titulo("2. los colaboradores se preservan")
# =============================================================================

d = asignados_crm.diferencia([LUIS], "user-ana", perfiles=[ANA, LUIS])
revisar(d["falta_agregar"] is True,
        "si el operador no esta en el caso, falta agregarlo")
revisar(d["colaboradores"] == [LUIS],
        "y el que ya estaba queda como colaborador",
        "Podria ser un segundo tecnico que sumo un supervisor esta manana.")
revisar(d["a_cargo_en_dexter"] == ANA, "con su perfil resuelto, para poder asignarlo")

d = asignados_crm.diferencia([ANA, LUIS], "user-ana")
revisar(d["falta_agregar"] is False,
        "si ya esta, no hay nada que hacer")
revisar(d["colaboradores"] == [LUIS],
        "y los demas siguen siendo colaboradores, no sobrantes")

# Sin operador (la IA lleva la conversacion) NO se limpia nada.
d = asignados_crm.diferencia([ANA, LUIS], None)
revisar(d["falta_agregar"] is False and d["colaboradores"] == [ANA, LUIS],
        "soltar no vacia el caso: lo que hay queda como colaboradores",
        "Quitar a ciegas borraria trabajo que no se puede recuperar.")

# Un operador sin perfil en el CRM: se dice, no se inventa.
d = asignados_crm.diferencia([LUIS], "user-fantasma", perfiles=[ANA, LUIS])
revisar(d["sin_perfil"] is True and d["falta_agregar"] is False,
        "un operador sin perfil en el CRM no se fuerza contra nadie")
revisar(d["colaboradores"] == [LUIS], "y el caso no se toca")

# La clave de idempotencia distingue a QUIEN se asigna.
k1 = asignados_crm.clave_de_asignacion("c1", "caso1", "perfil-ana")
k2 = asignados_crm.clave_de_asignacion("c1", "caso1", "perfil-luis")
revisar(k1 != k2,
        "reasignar a otra persona es otro efecto, con otra clave",
        "Con la misma clave, la reasignacion se descartaria como repetida y el "
        "CRM quedaria mostrando al operador anterior -- el defecto de D28.")
revisar(k1 == asignados_crm.clave_de_asignacion("c1", "caso1", "perfil-ana"),
        "y el mismo efecto da siempre la misma clave")


# =============================================================================
titulo("3. un 200 no es el efecto: se relee y se comprueba")
# =============================================================================

llamadas = {"agregar": 0, "leer": 0}


def ejecutar_con(agregar, leer):
    def _agregar(caso, perfil):
        llamadas["agregar"] += 1
        return agregar(caso, perfil)

    def _leer(caso):
        llamadas["leer"] += 1
        return leer(caso)

    return efectos_externos.ejecutor(
        None, "t", crear=None, buscar_por_nombre=None,
        agregar_asignado=_agregar, leer_asignados=_leer)


DATOS = {"caso_id": "caso1", "perfil_id": "perfil-ana"}

# Caso feliz: escribe y la relectura lo confirma.
llamadas.update(agregar=0, leer=0)
r = ejecutar_con(lambda c, p: {"added": True},
                 lambda c: {"assigned_to": [ANA, LUIS]})("asignar_caso", DATOS, None)
revisar(r.clase == "exito" and r.referencia == "perfil-ana",
        "se asigna y la relectura lo confirma -> exito")
revisar(llamadas["leer"] == 1,
        "SIEMPRE se relee, incluso cuando la escritura no dio error",
        "El codigo de estado no prueba el efecto.")

# El 200 que no hizo nada: escribio sin error y el perfil NO esta.
r = ejecutar_con(lambda c, p: {"added": True},
                 lambda c: {"assigned_to": [LUIS]})("asignar_caso", DATOS, None)
revisar(r.clase == "incierto",
        "escribio sin error y el perfil NO quedo -> INCIERTO, no exito",
        "Es el 200 que vacia el conjunto: sin esto se afirmaria un efecto falso.")

# No se puede releer: el efecto probablemente ocurrio, pero no se demuestra.
def leer_roto(c):
    raise TimeoutError("la API no contesto")

r = ejecutar_con(lambda c, p: {"added": True}, leer_roto)("asignar_caso", DATOS, None)
revisar(r.clase == "incierto",
        "escribio y no se pudo comprobar -> incierto, nunca exito",
        "Afirmar que el caso quedo asignado sin haberlo visto es lo que X22 "
        "prohibe.")

# La escritura falla pero la relectura muestra que si quedo (carrera).
class ErrorHttp(Exception):
    http_status = 500

def agregar_roto(c, p):
    raise ErrorHttp()

r = ejecutar_con(agregar_roto,
                 lambda c: {"assigned_to": [ANA]})("asignar_caso", DATOS, None)
revisar(r.clase == "exito",
        "si la escritura fallo pero el perfil ESTA, se adopta el resultado",
        "Mismo criterio que crear_caso: se comprueba antes de reintentar.")

# Falta el dato: permanente, no incierto -- no ocurrio y no va a ocurrir solo.
r = ejecutar_con(lambda c, p: None, lambda c: [])("asignar_caso", {}, None)
revisar(r.clase == "permanente" and r.codigo == "sin_caso_o_perfil",
        "sin caso o sin perfil es permanente, no incierto")

# Sin las dos capacidades inyectadas no se intenta nada.
sin_capacidad = efectos_externos.ejecutor(None, "t", crear=None, buscar_por_nombre=None)
r = sin_capacidad("asignar_caso", DATOS, None)
revisar(r.clase == "permanente" and "sin_ejecutor" in r.codigo,
        "sin capacidad de asignar, el efecto es permanente y visible",
        "No hay duda de si ocurrio: no se intento.")


# =============================================================================
titulo("4. el CRM no manda")
# =============================================================================

# Nada en este modulo puede tocar la base. Se afirma sobre lo que el codigo
# PUEDE hacer --no importa persistencia, no ejecuta SQL-- y no sobre si
# menciona el nombre del campo: el docstring lo nombra justamente para explicar
# que Dexter es la autoridad. Buscar la cadena en el archivo entero daria rojo
# por su propia explicacion, y es el cuarto archivo de esta fase donde pasa.
revisar("persistencia" not in codigo and "import db" not in codigo,
        "asignados_crm.py no puede escribir en la base: no importa persistencia",
        "Sin acceso a la base, el CRM no tiene por donde mover el operador "
        "durable aunque alguien lo intentara.")
for prohibido in ("update ", "insert ", "delete ", "cur.execute"):
    revisar(prohibido not in codigo.lower(),
            f"y no ejecuta SQL ({prohibido.strip()})")

# Y el ejecutor nunca reemplaza el conjunto.
ejec = (RAIZ / "nucleo" / "relevo" / "efectos_externos.py").read_text(encoding="utf-8")
revisar(".set(" not in ejec and "assigned_to=" not in ejec,
        "el ejecutor no usa .set() ni manda el conjunto entero")

# El proxy del frontend tampoco puede llegar al PUT destructivo.
proxies = list((RAIZ / "django-crm" / "frontend" / "src" / "routes" / "api").rglob("*.js"))
malos = [p.name for p in proxies
         if "assignees" in str(p) and "PUT" in p.read_text(encoding="utf-8")]
revisar(not malos, f"ningun proxy de asignados usa PUT ({malos})")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Se agrega al operador sin borrar a nadie, y no se afirma lo que no se vio.")
