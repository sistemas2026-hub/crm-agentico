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
   casos existe: con dos conversaciones no hay patron.

Corre SIN BASE DE DATOS y sin red: el catalogo se sustituye por un doble.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.habilidades import analista, catalogo                      # noqa: E402
from nucleo.habilidades.catalogo import EntradaIndice, Habilidad       # noqa: E402
from nucleo.modelo import motor                                        # noqa: E402

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
afirmar("'propuesta'" in fuente_analista and "'vigente'" not in fuente_analista,
        "el analista solo escribe estado 'propuesta', nunca 'vigente'")

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


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Las habilidades fallan cerrado y el analista no activa nada.")
