# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE HABILIDADES  --  un procedimiento llega entero, o no llega
================================================================================

Que son las habilidades y por que existen aparte del corpus esta explicado en
nucleo/habilidades/catalogo.py. Aca se fija lo que no puede romperse.

Lo que se fija
--------------
1. FALLA CERRADO EN DOS CAPAS. Un rol que no tiene la habilidad no la ve en el
   indice Y tampoco puede cargarla nombrando el codigo. No alcanza con no
   mostrarla: el codigo llega en un argumento que produce el modelo, y un
   modelo puede nombrar uno que vio en otra conversacion o inventarlo. Es el
   mismo criterio que PRD 8.1 exige para las herramientas.

2. UN CODIGO QUE NO EXISTE Y UNO AJENO SE CONTESTAN IGUAL. Distinguirlos le
   contaria al modelo que existe un procedimiento que no puede ver.

3. NO SE INVENTAN LOS PASOS. Cuando la carga falla, la instruccion que vuelve
   dice explicitamente que no se inventen los pasos. Sin eso, un modelo que
   pide un procedimiento y recibe un error tiende a improvisar -- que es
   exactamente el problema que las habilidades vienen a resolver.

4. EL INDICE NO TRAE LOS PASOS, Y LO DICE. Si el indice no aclarara que los
   pasos no estan ahi, el modelo lee el disparador, cree que ya sabe el
   procedimiento y contesta con lo que improvise. El mismo problema, un nivel
   mas arriba.

5. SIN HABILIDADES, NADA CAMBIA. Un tenant que no cargo ninguna tiene que
   trabajar exactamente como venia trabajando: bloque vacio, sin ruido en el
   prompt.

6. EL ANALISTA NO ACTIVA NADA. Toda propuesta nace 'propuesta'. Y el piso de
   casos existe: con dos conversaciones no hay patron. Se mira lo que el
   analista ESCRIBE, no si la palabra aparece: la version anterior de esta
   guarda se ponia en rojo cuando se agregaba una LECTURA legitima.

7. EL PROMPT DEL ANALISTA NO FILTRA SU PROPIO METADATO. Las dos primeras
   propuestas reales salieron inservibles porque el contexto del analisis
   (señal, motivo, n_casos) llegaba al procedimiento sin decirle que el
   agente NO puede ver nada de eso. Un disparador que dice "5 casos en los
   ultimos 60 dias" no se activa nunca.

8-10. LO QUE LA CONSULTA REAL DE catalogo.py PONE EN EL WHERE. Los puntos de
   arriba reemplazan 'catalogo.cargar' por un doble: prueban que el motor usa
   bien lo que el catalogo DEVUELVE, no que la consulta lleve los filtros que
   dice llevar. Aca se mira el SQL real -- organizacion, estado 'vigente' y
   rol, en 'indice_de()' Y en 'cargar()' (doble capa, PRD 8.1), y los tres
   como parametros bindeados, nunca interpolados en el texto.

11. EL LIMITE DE ESTA AUDITORIA, DICHO. Lo de arriba prueba que el CODIGO
   pide lo correcto, no que Postgres lo haga cumplir: eso exige RLS activo y
   dos organizaciones reales. Documentado, no resuelto aca.

Corre SIN BASE DE DATOS y sin red: el catalogo se sustituye por un doble.
================================================================================
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.habilidades import analista, catalogo                      # noqa: E402
from nucleo.habilidades.catalogo import EntradaIndice, Habilidad       # noqa: E402
from nucleo.modelo import motor                                        # noqa: E402

# Guardada ANTES de que _sin_base() (mas abajo) reemplace catalogo.cargar por
# un lambda -- ese reemplazo dura el resto del script, asi que la seccion 8-10
# necesita esta referencia para llamar a la funcion real y no al doble.
_cargar_real = catalogo.cargar

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


# --- doble del catalogo: una habilidad, visible solo para 'soporte' ----------
CARGADA = {("soporte", "HAB-01"): Habilidad(
    codigo="HAB-01", nombre="Reclamo de facturacion duplicada",
    cuando_usarla="el cliente dice que le cobraron dos veces el mismo mes",
    pasos="1. Consulta las facturas del cliente.\n2. ...")}


class ConfigFalsa:
    class identidad:
        slug = "tenant_de_prueba"


def _sin_base(monkeypatch_objetivo, rol_visible: str) -> None:
    """Sustituye el acceso a base por el diccionario de arriba."""
    catalogo.cargar = lambda tenant, rol, codigo: CARGADA.get((rol, codigo))
    catalogo.registrar_uso = lambda *a, **k: None


print("\n== 1-3. falla cerrado, y no se inventan los pasos ==")
_sin_base(None, "soporte")

salida = motor._ejecutar_carga_habilidad(ConfigFalsa(), "soporte", {"codigo": "HAB-01"})
afirmar(salida.get("pasos", "").startswith("1. Consulta"),
        "el rol que SI la tiene recibe los pasos completos")

ajena = motor._ejecutar_carga_habilidad(ConfigFalsa(), "ventas", {"codigo": "HAB-01"})
afirmar(ajena.get("error") == "HABILIDAD_DESCONOCIDA",
        "un rol ajeno NO puede cargarla nombrando el codigo exacto")

inexistente = motor._ejecutar_carga_habilidad(ConfigFalsa(), "soporte", {"codigo": "HAB-99"})
afirmar(inexistente.get("error") == ajena.get("error")
        and inexistente.get("instruccion_interna") == ajena.get("instruccion_interna"),
        "un codigo ajeno y uno inexistente se contestan IGUAL")

afirmar("no te inventes" in ajena.get("instruccion_interna", "").lower(),
        "al fallar, la instruccion prohibe inventarse los pasos")

vacio = motor._ejecutar_carga_habilidad(ConfigFalsa(), "soporte", {})
afirmar(vacio.get("error") == "FALTA_CODIGO",
        "sin codigo devuelve un error propio, no busca a ciegas")

afirmar("al pie de la letra" in salida.get("instruccion_interna", ""),
        "al acertar, la instruccion dice que el procedimiento se sigue, no se opina")


print("\n== 4-5. el indice dice lo que es, y sin habilidades no molesta ==")
bloque = catalogo.bloque_de_indice([EntradaIndice(
    codigo="HAB-01", nombre="Reclamo de facturacion duplicada",
    cuando_usarla="el cliente dice que le cobraron dos veces")])

afirmar("HAB-01" in bloque and "cobraron dos veces" in bloque,
        "el indice trae el codigo y el disparador")
afirmar("pasos NO estan" in bloque,
        "el indice avisa que los pasos no estan ahi")
afirmar("cargar_habilidad" in bloque,
        "el indice dice como pedir el procedimiento")
afirmar("1." not in bloque.split("Usala cuando")[-1].split("\n")[0],
        "el indice no filtra pasos por accidente")

afirmar(catalogo.bloque_de_indice([]) == "",
        "sin habilidades el bloque es vacio: nada se agrega al prompt")


print("\n== 6. el analista propone, nunca activa ==")
afirmar(analista.MINIMO_CASOS >= 3,
        f"el piso de casos es {analista.MINIMO_CASOS}: con menos no hay patron")

fuente_analista = Path("nucleo/habilidades/analista.py").read_text(encoding="utf-8")
# Se mira lo que ESCRIBE, no si la palabra aparece. La version anterior
# buscaba "'vigente'" en todo el archivo y se puso en rojo al agregarse una
# LECTURA legitima -- consultar que patrones ya estan cubiertos. Un test que
# no distingue leer de escribir obliga a elegir entre romperlo o no leer.
escrituras = re.findall(r"(?:insert into|update)\s+asistente\.habilidades(.*?)(?:\"\"\"|$)",
                        fuente_analista, re.S | re.I)
afirmar(bool(escrituras), "el analista escribe habilidades (si no, no hace nada)")
afirmar(all("'vigente'" not in e for e in escrituras),
        "ninguna ESCRITURA del analista pone estado 'vigente'")
afirmar(any("'propuesta'" in e for e in escrituras),
        "y al menos una escribe 'propuesta'")

fuente_sql = Path("supabase/202609031100_habilidades.sql").read_text(encoding="utf-8")
afirmar("default 'propuesta'" in fuente_sql,
        "el estado por defecto en la base tambien es 'propuesta'")

# El JSON del modelo llega envuelto en cortesias cada tantas corridas; perder
# el analisis entero por eso seria tirar una llamada paga a la basura.
afirmar(analista._extraer_json('Claro:\n{"codigo":"X"}\nEspero sirva')
        == {"codigo": "X"},
        "un JSON envuelto en explicaciones se rescata igual")
afirmar(analista._extraer_json("no hay json aca") is None,
        "una respuesta sin JSON devuelve None, no revienta")

print("\n== 7. el prompt del analista no filtra su propio metadato ==")
# Las dos primeras propuestas reales del analista salieron inservibles, y por
# la misma causa: mi prompt le pasaba el contexto del analisis (senal, motivo,
# n_casos) sin decirle que el agente NO puede ver nada de eso.
#
# Una salio con este disparador:
#     "El ticket tiene señal escalada_repetida y motivo frustracion_detectada,
#      con 5 casos en los ultimos 60 dias..."
# Un agente no puede observar "5 casos en los ultimos 60 dias". Ese
# procedimiento no se habria activado jamas.
#
# Y las dos le ordenaban al ENRUTADOR verificar identidad -- que tiene una
# sola herramienta ('derivar_a_area') y por diseño no verifica: eso se movio a
# cada especialista. La regla decia "no inventes una herramienta", y el modelo
# obedecio al pie de la letra: no nombro ninguna, lo pidio en prosa.

prompt = analista.PROMPT_REDACCION
afirmar("SOLO PARA VOS" in prompt,
        "el contexto del analisis se marca como no observable por el agente")
afirmar("no se va a activar nunca" in prompt or "no se activaria nunca" in prompt,
        "y se dice la consecuencia de filtrarlo, no solo que no se haga")
afirmar("en prosa" in prompt,
        "la restriccion de herramientas alcanza a las acciones en prosa, no "
        "solo a los nombres")
afirmar("VE EN LA CONVERSACION" in prompt,
        "el disparador se define por lo que el agente ve, no por el patron")


print("\n== 8-10. lo que la CONSULTA REAL de catalogo.py pone en el WHERE ==")
# Las pruebas de arriba reemplazan catalogo.cargar entero por un diccionario:
# prueban que _ejecutar_carga_habilidad usa bien lo que catalogo LE DEVUELVE,
# pero no prueban que catalogo.py arme la consulta SQL con los filtros que
# describe. Fase #2.2 los leyo una vez a mano; esto los deja con guarda: si
# alguien borra 'estado = vigente' o el filtro de organization_id sin darse
# cuenta, esto falla, no hace falta releer el archivo para notarlo.
#
# Sin base de datos: se reemplaza SOLO 'sesion' (el context manager que abre
# la conexion), por un cursor falso que graba que SQL y que parametros
# recibio, en vez de ejecutar nada.


class _CursorFalso:
    def __init__(self, filas=None):
        self.llamadas = []           # [(sql, params), ...]
        self._filas = filas or []

    def execute(self, sql, params=None):
        self.llamadas.append((sql, params))

    def fetchall(self):
        return self._filas

    def fetchone(self):
        return self._filas[0] if self._filas else None


class _SesionFalsa:
    """Mismo shape que nucleo.persistencia.db.sesion: un context manager que
    entrega (cursor, organization_id)."""
    def __init__(self, cursor, org="org-fantasma-000"):
        self.cursor = cursor
        self.org = org

    def __call__(self, tenant):
        return self

    def __enter__(self):
        return self.cursor, self.org

    def __exit__(self, *exc):
        return False


cursor = _CursorFalso()
sesion_falsa = _SesionFalsa(cursor)
catalogo.sesion = sesion_falsa

catalogo.indice_de("cualquier_tenant", "soporte")
sql_indice, params_indice = cursor.llamadas[-1]
afirmar("organization_id = %s" in sql_indice,
        "indice_de() filtra por organization_id en el SQL real")
afirmar("estado = 'vigente'" in sql_indice,
        "indice_de() exige estado='vigente' en el SQL real -- una propuesta u "
        "obsoleta no puede aparecer en el indice")
afirmar("any(roles_permitidos)" in sql_indice,
        "indice_de() filtra por rol en el SQL real")
afirmar(params_indice[0] == sesion_falsa.org and params_indice[1] == "soporte",
        "los parametros que se bindean son el org de la SESION (no algo que "
        "el modelo pueda mandar) y el rol pedido")

cursor.llamadas.clear()
_cargar_real("cualquier_tenant", "facturacion", "HAB-X")
sql_cargar, params_cargar = cursor.llamadas[-1]
afirmar("organization_id = %s" in sql_cargar,
        "cargar() TAMBIEN filtra por organization_id -- doble capa, no solo "
        "en el indice")
afirmar("estado = 'vigente'" in sql_cargar,
        "cargar() TAMBIEN exige estado='vigente' -- una obsoleta no se puede "
        "cargar nombrando el codigo, aunque el indice ya la hubiera ocultado")
afirmar("any(roles_permitidos)" in sql_cargar,
        "cargar() repite el filtro de rol -- PRD 8.1: no alcanza con no "
        "mostrarla, tambien se rechaza si igual la invocan")
afirmar(sesion_falsa.org in params_cargar and "facturacion" in params_cargar
        and "HAB-X" in params_cargar,
        "los tres filtros -- org, rol, codigo -- viajan como parametros "
        "reales, no interpolados en el texto (sin riesgo de inyeccion)")

print("\n== 11. limite de lo que esta auditoria SI y NO prueba ==")
# Esto prueba que el CODIGO arma bien la consulta. No prueba que Postgres
# de verdad la responda filtrada -- eso exige RLS activo (asistente.habilidades
# lo declara con FORCE, ver supabase/202609031100_habilidades.sql) y una base
# real con dos organizaciones para intentar cruzarlas. Sin esa integracion
# contra Postgres, la afirmacion de aislamiento sigue siendo "el codigo pide
# lo correcto", no "la base lo hace cumplir". Documentado, no resuelto aca.
afirmar(True, "aislamiento a nivel RLS/Postgres queda FUERA de esta prueba a "
              "proposito -- requiere una base real, ver nota arriba")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Las habilidades fallan cerrado y el analista no activa nada.")
