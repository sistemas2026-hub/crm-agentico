# -*- coding: utf-8 -*-
"""
================================================================================
 LA DECISIÓN DE ESCALAR PUEDE DECIR QUE NO SABE
================================================================================

Por qué existe
--------------
`escalar` era un **booleano**, y un booleano no tiene dónde alojar una duda:
«no molesto a nadie» y «no sé si molestar a alguien» salían idénticos.

Eso se midió, y el número es el que justifica todo esto. Contra 12 casos
escritos a mano como ambiguos, el decisor dio **0 de 12 abstenciones**. Ese
cero **no era un fallo de criterio: era una imposibilidad** — no existía la
salida con la que decir que no sabe.

Y del otro lado hay otro número: 88 casos dorados × 5 corridas = 440 llamadas,
y el evaluador **decide distinto con la entrada idéntica en 6 de 88**, justo en
`escalar`. O sea que el sistema ya dudaba; lo que faltaba era que pudiera
decirlo.

**El caso peligroso no es el que despierta de más.** Es `escalar: false` con
confianza baja: el agente decide no molestar a nadie y no está seguro. A las 3
de la mañana nadie lo revisa.

Qué afirma, y qué NO
--------------------
Afirma sobre el **esquema que de verdad viaja al modelo**, no sobre una
constante ni sobre la presencia de una variable: §6 recuerda que una prueba que
afirma que algo EXISTE sobrevivió intacta a una inversión completa de la
conducta.

NO afirma que el modelo use bien la escala: eso pide el modelo, tiene varianza
y se mide con el corpus de trampas, no acá.

    py -3.13 tests/test_la_decision_puede_decir_que_no_sabe.py
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import cargar_config                      # noqa: E402
from nucleo.seguimiento import escalamiento                         # noqa: E402

FALLOS = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  [{'ok' if condicion else 'FALLA'}]   {que}")
    if not condicion:
        FALLOS.append(que)


cfg = cargar_config("tenants/rapilink.config.yaml")
esquema = escalamiento._esquema_evaluacion(cfg, cfg.roles["cliente_final"])
params = esquema["function"]["parameters"]
props = params["properties"]

print("\n  EL CAMPO EXISTE EN EL ESQUEMA QUE VIAJA AL MODELO")
comprobar("confianza" in props,
          "la decisión declara 'confianza'")

print("\n  ES OBLIGATORIO  --  un campo que se puede omitir, se omite")
#  LA MUTACIÓN QUE ESTA PRUEBA EXISTE PARA MATAR. Sin esto, el modelo lo deja
#  afuera cuando no tiene ganas, y la AUSENCIA se lee como "no tuvo dudas" --
#  que es exactamente la confusión que el campo viene a deshacer.
comprobar("confianza" in params["required"],
          "y está entre los requeridos, no como opcional")

print("\n  EL VOCABULARIO ES EL QUE EL SISTEMA YA USA")
#  'alta'/'media'/'baja' es el mismo que 'confianza_del_grupo' en
#  'operaciones/paso_a_despacho.py'. Inventar una escala propia habría dejado
#  dos formas de decir lo mismo, y la segunda se desincroniza sin que nadie lo
#  note -- el patrón que este repositorio ya pagó varias veces.
comprobar(props["confianza"].get("enum") == ["alta", "media", "baja"],
          "con el enum alta/media/baja, el mismo de paso_a_despacho")

print("\n  EL ENUM ES LA GARANTÍA, NO LA DESCRIPCIÓN")
#  Un enum lo hace cumplir el proveedor; una descripción es una sugerencia. Si
#  esto fuera un string libre, 'confianza' podría volver "bastante" o "creo que
#  sí" y nadie podría comparar dos decisiones entre sí.
comprobar(props["confianza"].get("type") == "string",
          "declarado como string acotado por enum")

print("\n  LA DESCRIPCIÓN DICE CUÁNDO USAR 'baja', QUE ES LO QUE SE QUIERE")
desc = str(props["confianza"].get("description") or "")
comprobar("baja" in desc,
          "nombra 'baja' explícitamente")
comprobar("valida" in desc or "válida" in desc,
          "y le dice al modelo que es una respuesta VÁLIDA, no un fracaso")
#  Sin esta línea el modelo trata la baja confianza como algo que hay que
#  evitar, y vuelve el 0 de 12.
comprobar("'escalar'" in desc or "escalar" in desc,
          "y aclara que califica a 'escalar', no al resto de la ficha")

print("\n  NO SE PISÓ NADA DE LO QUE YA HABÍA")
#  El campo se AGREGA. Si al agregarlo se hubiera perdido uno de los que ya
#  decidían, esto sería un cambio de conducta disfrazado de campo nuevo.
for previo in ("escalar", "etiqueta", "resuelta", "no_se_pudo_comprobar",
               "siguiente_paso", "motivo"):
    comprobar(previo in params["required"],
              f"'{previo}' sigue siendo obligatorio")

print("\n  Y NO DECIDE NADA TODAVÍA, A PROPÓSITO")
#  El campo se declara y se guarda; quien lo lea para cambiar una conducta es
#  otro paso, y va en sombra primero -- el mismo patrón que el paso a Despacho
#  y que las correcciones del usuario. Esta afirmación es sobre el EFECTO: el
#  módulo no ramifica por confianza en ninguna parte.
import inspect                                                      # noqa: E402

fuente = inspect.getsource(escalamiento)
#  Se busca la LECTURA del valor, no la palabra: el esquema y los comentarios
#  la nombran muchas veces y eso no es ramificar.
lecturas = [l for l in fuente.splitlines()
            if ('["confianza"]' in l or '.get("confianza"' in l)
            and not l.strip().startswith("#")]
comprobar(not lecturas,
          f"nadie ramifica por 'confianza' todavía (encontradas: {lecturas})")

print("\n" + "=" * 70)
if FALLOS:
    print(f" {len(FALLOS)} afirmacion(es) en rojo:")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print(" La decisión de escalar puede decir que no sabe.")
print("=" * 70)
