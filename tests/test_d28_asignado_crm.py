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


# =============================================================================
titulo("5. el catalogo puede declarar las capacidades")
# =============================================================================
# Las cuatro banderas NO existian en el schema y el codigo de B4 ya leia
# 'busca_caso' con getattr(..., False): se consultaba una capacidad que ningun
# YAML podia declarar --extra="forbid" hacia fallar la carga entera-- y el
# getattr devolvia False en silencio. G7 dependia de eso.
from nucleo.config.schema import Herramienta                      # noqa: E402

_BASE = dict(nombre="x", tipo="http", descripcion="d", solo_lectura=True,
             roles_permitidos=["soporte"], endpoint="/api/x/",
             base_url="https://x.co")
for bandera in ("busca_caso", "asigna_caso", "lee_asignados", "lee_perfiles"):
    try:
        h = Herramienta(**_BASE, **{bandera: True})
        revisar(getattr(h, bandera) is True,
                f"el catalogo acepta '{bandera}' y lo conserva")
    except Exception as e:
        revisar(False, f"el catalogo acepta '{bandera}'", str(e)[:120])

# Y siguen siendo banderas, no nombres fijos: cada empresa llama a sus
# herramientas como quiere.
revisar(Herramienta(**_BASE).asigna_caso is False,
        "sin declararla, la capacidad es False y el efecto falla cerrado")


# =============================================================================
titulo("6. el productor: quien encola, y quien no")
# =============================================================================
fuente_tr = (RAIZ / "nucleo" / "relevo" / "transiciones.py").read_text(encoding="utf-8")


def cuerpo_de(nombre):
    i = fuente_tr.index(f"def {nombre}(tenant: str")
    j = fuente_tr.index(chr(10) + "def ", i + 10)
    return fuente_tr[i:j]


for transicion in ("tomar", "reasignar"):
    revisar("_encolar_asignacion_crm" in cuerpo_de(transicion),
            f"{transicion} encola la asignacion del caso")

for transicion in ("soltar", "devolver_a_ia", "resolver", "escalar"):
    revisar("_encolar_asignacion_crm" not in cuerpo_de(transicion),
            f"{transicion} NO encola nada",
            "Soltar no limpia el caso: deja divergencia visible, que es "
            "preferible a borrar una colaboracion.")

# Reasignar encola al que ENTRA, no al que sale.
revisar("_encolar_asignacion_crm(cur, org, conversation_id, f, id_destino)"
        in cuerpo_de("reasignar"),
        "reasignar encola al destino, no al anterior")

# El efecto se encola DESPUES del evento, dentro de la misma transaccion: si
# se encolara antes, un fallo al escribir el evento dejaria encolado un reflejo
# de algo que no paso.
cuerpo_tomar = cuerpo_de("tomar")
revisar(cuerpo_tomar.index('"tomada", "operador"') < cuerpo_tomar.index("_encolar_asignacion_crm"),
        "se encola despues de escribir el evento, en la misma transaccion")

# Y no hay ninguna llamada HTTP dentro de la transaccion (X23).
revisar("requests" not in fuente_tr and "herramientas_http" not in fuente_tr,
        "las transiciones no hablan con el CRM: solo anotan la intencion")


# =============================================================================
titulo("7. el worker: fail-closed sin las tres capacidades")
# =============================================================================
fuente_w = (RAIZ / "nucleo" / "relevo" / "worker_reconciliador.py").read_text(encoding="utf-8")
revisar('for bandera in ("asigna_caso", "lee_asignados", "lee_perfiles")' in fuente_w,
        "se exigen LAS TRES capacidades, no una")
revisar("agregar_asignado=agregar_asignado if puede_asignar else None" in fuente_w,
        "y sin ellas no se inyecta nada: el efecto queda permanente y visible")

# Traducir el usuario al perfil sin catalogo es permanente, no incierto.
r = efectos_externos.ejecutor(
    None, "t", crear=None, buscar_por_nombre=None,
    agregar_asignado=lambda c, p: None, leer_asignados=lambda c: [],
)("asignar_caso", {"caso_id": "c", "usuario_id": "user-ana"}, None)
revisar(r.clase == "permanente" and r.codigo == "sin_catalogo_de_perfiles",
        "sin catalogo de perfiles no se adivina: permanente")

# Con catalogo, se traduce por id.
ejec = efectos_externos.ejecutor(
    None, "t", crear=None, buscar_por_nombre=None,
    agregar_asignado=lambda c, p: {"added": True},
    leer_asignados=lambda c: {"assigned_to": [ANA, LUIS]},
    leer_perfiles=lambda: [OTRA_ANA, ANA, LUIS])
r = ejec("asignar_caso", {"caso_id": "c", "usuario_id": "user-ana"}, None)
revisar(r.clase == "exito" and r.referencia == "perfil-ana",
        "el usuario durable se traduce al perfil correcto, no al homonimo",
        "OTRA_ANA se llama igual y va primero en la lista.")

# Un operador sin perfil en el CRM: permanente, no se fuerza contra nadie.
r = ejec("asignar_caso", {"caso_id": "c", "usuario_id": "user-fantasma"}, None)
revisar(r.clase == "permanente" and r.codigo == "operador_sin_perfil_en_crm",
        "un operador sin perfil en el CRM queda visible, sin reintentos inutiles")

# Si no se puede leer el catalogo, se reintenta entero: no se escribio nada.
def perfiles_rotos():
    raise TimeoutError("sin respuesta")

r = efectos_externos.ejecutor(
    None, "t", crear=None, buscar_por_nombre=None,
    agregar_asignado=lambda c, p: {"added": True},
    leer_asignados=lambda c: {"assigned_to": []},
    leer_perfiles=perfiles_rotos)("asignar_caso", {"caso_id": "c", "usuario_id": "u"}, None)
revisar(r.clase in ("transitorio", "incierto") and r.clase != "exito",
        "si no se puede traducir, no se escribe y se reintenta")


# =============================================================================
titulo("8. la pantalla esta cableada")
# =============================================================================
FRONT = RAIZ / "django-crm" / "frontend" / "src"
panel = (FRONT / "lib" / "conversaciones" / "context" / "AssigneesPanel.svelte").read_text(encoding="utf-8")
pagina = (FRONT / "routes" / "(app)" / "conversaciones" / "[id]" / "+page.svelte").read_text(encoding="utf-8")

marcado = panel[panel.rindex("</script>"):]
revisar("AssigneesPanel" in pagina, "el panel esta montado en la conversacion")
revisar("ETIQUETAS.dexter" in marcado and "ETIQUETAS.crm" in marcado,
        "y usa las etiquetas del modulo, no texto propio")
revisar("vistaDeAsignados" in panel,
        "la vista sale de asignados.js y no se decide en el panel")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Se agrega al operador sin borrar a nadie, y no se afirma lo que no se vio.")
