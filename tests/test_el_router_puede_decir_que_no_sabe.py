# -*- coding: utf-8 -*-
"""
================================================================================
 EL ROUTER PUEDE DECIR QUE NO SABE A QUÉ ÁREA VA
================================================================================

Por qué existe
--------------
El 20/10/2026 se le dio a la decisión de **escalar** un campo de confianza. Al
medirla contra el corpus de trampas apareció que ese corpus etiquetaba otra
cosa: sus doce casos ambiguos listan **ÁREAS** en `veredicto.entre`
—`[facturacion, soporte_tecnico]`, `[comercial, facturacion]`…—. La duda no
era «¿hace falta una persona?» sino **«¿a qué cola va esto?»**, y eso se
decide en el router, que es otro componente.

Tres casos del corpus que el router no podía expresar:

    "quiero cancelar"       baja el servicio, una solicitud, o un cobro
    "mandame el recibo"     falta el documento, o falta que le acrediten
    "buenas"                todavía no dijo nada

Ante los tres elegía un área y seguía, con total seguridad. Para un agente que
rutea solo de madrugada, **mandar un caso a la cola equivocada sin dudar** es
el error confiado-y-equivocado que más cuesta: nadie lo revisa después, porque
nada dijo que hubiera algo que revisar.

Qué afirma, y qué NO
--------------------
Sobre el **esquema que de verdad viaja al modelo**, construido desde el
catálogo real del tenant. No afirma que el modelo use bien la escala: eso pide
el modelo, tiene varianza, y hace falta un arnés que corra un turno entero y
mire los argumentos de la derivación — que hoy no existe (el informe de
`cli/evaluar.py` guarda nombres de herramienta, no argumentos).

    py -3.13 tests/test_el_router_puede_decir_que_no_sabe.py
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import cargar_config                   # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402

FALLOS = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  [{'ok' if condicion else 'FALLA'}]   {que}")
    if not condicion:
        FALLOS.append(que)


cfg = cargar_config("tenants/rapilink.config.yaml")
deriva = next((h for h in cfg.herramientas if h.deriva_rol), None)

print("\n  LA HERRAMIENTA QUE RUTEA EXISTE")
comprobar(deriva is not None, "hay una herramienta con deriva_rol")
if deriva is None:
    sys.exit(1)

esquema = motor._esquema_openai(deriva)
params = esquema["function"]["parameters"]
props = params["properties"]

print("\n  Y PUEDE DECLARAR CUÁNTA CONFIANZA TIENE")
comprobar("confianza" in props, "el esquema lleva 'confianza'")

print("\n  ES OBLIGATORIA  --  un campo que se puede omitir, se omite")
#  LA MUTACIÓN QUE ESTA PRUEBA MATA. Sin esto el modelo lo deja afuera cuando
#  no tiene ganas, y la AUSENCIA se lee como "no tuvo dudas".
comprobar("confianza" in params["required"],
          "y está entre los requeridos")

print("\n  CON EL MISMO VOCABULARIO QUE EL RESTO DEL SISTEMA")
#  'alta'/'media'/'baja' es el de `confianza_del_grupo` (paso_a_despacho) y el
#  de la decisión de escalar. Tres escalas para la misma idea serían tres
#  cosas que comparar a mano.
comprobar(props.get("confianza", {}).get("enum") == ["alta", "media", "baja"],
          "enum alta/media/baja, el mismo de escalamiento y paso_a_despacho")

print("\n  NO SE PISÓ LA ELECCIÓN DEL ÁREA, QUE ES LO QUE DECIDE")
comprobar("area" in params["required"], "'area' sigue siendo obligatoria")
comprobar(props["area"].get("enum") == deriva.areas_destino,
          "y sigue acotada al enum de areas_destino del tenant")

print("\n  LA DESCRIPCIÓN EMPUJA A USAR 'baja', QUE ES EL PUNTO")
desc = str(props.get("confianza", {}).get("description") or "")
comprobar("baja" in desc, "nombra 'baja'")
comprobar("valida" in desc or "válida" in desc,
          "y le dice que es una respuesta VÁLIDA, no un fracaso")
#  Sin esta línea el modelo trata la duda como algo que hay que evitar y
#  contesta 'alta' por cortesía -- que es exactamente lo que se midió en la
#  decisión de escalar antes de insistir en este punto.
comprobar("revise" in desc or "revisar" in desc,
          "y nombra el COSTO de mentir: que nadie revise una derivación mala")

print("\n  Y NO DECIDE NADA TODAVÍA, A PROPÓSITO")
#  Se declara y queda en la traza. Que alguien la lea para cambiar una
#  conducta --no derivar, preguntar primero-- es otro paso, y va en sombra.
import inspect                                                   # noqa: E402

fuente = inspect.getsource(motor._ejecutar_derivacion)
comprobar('"confianza"' not in fuente and "'confianza'" not in fuente,
          "el ejecutor de la derivación no ramifica por 'confianza'")

print("\n" + "=" * 70)
if FALLOS:
    print(f" {len(FALLOS)} afirmacion(es) en rojo:")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print(" El router puede decir que no sabe a qué área va.")
print("=" * 70)
