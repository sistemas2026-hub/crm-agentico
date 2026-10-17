# -*- coding: utf-8 -*-
"""
Las variables de una plantilla de WhatsApp: cuantas son, donde van y como
viajan.

    py -3.13 tests/test_plantillas_variables.py

Corre SIN RED y SIN BASE.

QUE SE ARREGLO AQUI (20/09/2026)
--------------------------------
Dos defectos de envio, los dos del mismo sitio -- el conteo de huecos se
hacia con `re.findall(r"\\{\\{(\\d+)\\}\\}", cuerpo)`:

  1. EL ENCABEZADO NO CONTABA. El regex corria solo sobre el cuerpo, asi que
     una plantilla con {{1}} en el encabezado pedia un valor de menos y
     llegaba a Meta sin el componente 'header'. Meta la rechaza, y el rechazo
     es generico: no dice que falto.

  2. LOS PARAMETROS NOMBRADOS DABAN CERO. El regex exige digitos, asi que
     {{customer_name}} no matcheaba: la plantilla salia sin ningun parametro.
     Mismo rechazo generico.

LO QUE NO SE TOCO
-----------------
El contrato de entrega (aceptado != entregado != leido), el flujo de wamid y
los acuses sent/delivered/read/failed. Nada de esto los roza: se audito y
estaba entero (G9).

EL PUNTO DELICADO: EL ORDEN
---------------------------
La pantalla manda UNA lista plana de valores y la plantilla tiene DOS
componentes. El reparto es contractual -- primero el encabezado, despues el
cuerpo-- y vive en dos lugares que tienen que coincidir:

    whatsapp.componentes_de_plantilla   lo que se le manda a Meta
    api._armar_plantilla                lo que se guarda en el hilo

Si dejaran de coincidir, el cliente leeria una cosa y el hilo guardaria otra,
y nadie lo notaria hasta que alguien reciba el nombre de otra persona. Por eso
la ultima seccion compara las dos salidas sobre la misma entrada.

Y en posicional CADA COMPONENTE numera desde 1: un encabezado con {{1}} y un
cuerpo con {{1}} {{2}} son TRES valores, no dos. Es la trampa mas facil.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import whatsapp  # noqa: E402

fallos: list[str] = []


def revisar(condicion: bool, que: str, porque: str = "") -> None:
    print(f"  {'[OK]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)
        if porque:
            print(f"          {porque}")


def ficha(*, encabezado: str = "", cuerpo: str = "") -> dict:
    """La plantilla tal como la devuelve Meta, ya desarmada."""
    componentes = [{"type": "BODY", "text": cuerpo}]
    if encabezado:
        componentes.insert(0, {"type": "HEADER", "format": "TEXT",
                               "text": encabezado})
    return whatsapp._desarmar_plantilla({
        "name": "prueba", "status": "APPROVED", "language": "es",
        "category": "UTILITY", "components": componentes})


def parametros_de(componentes: list[dict], tipo: str) -> list[dict]:
    for c in componentes:
        if c["type"] == tipo:
            return c["parameters"]
    return []


def textos_de(componentes: list[dict], tipo: str) -> list[str]:
    return [p["text"] for p in parametros_de(componentes, tipo)]


# =============================================================================
print("\n-- 1. lo que ya funcionaba sigue funcionando ---------------------")
# =============================================================================

sin_variables = ficha(cuerpo="Hola, ya te atendemos.")
revisar(sin_variables["variables"] == 0,
        "una plantilla sin variables pide cero valores")
revisar(whatsapp.componentes_de_plantilla(sin_variables, []) == [],
        "y viaja sin 'components': mandar uno vacio es mandar basura")

solo_cuerpo = ficha(cuerpo="Hola {{1}}, tu factura de {{2}} vence manana.")
revisar(solo_cuerpo["variables"] == 2,
        "el cuerpo con {{1}} y {{2}} sigue pidiendo dos valores")
revisar(textos_de(whatsapp.componentes_de_plantilla(solo_cuerpo, ["Ana", "$80.000"]),
                  "body") == ["Ana", "$80.000"],
        "y los dos siguen viajando en el componente 'body', en orden")

# Un {{1}} repetido, o un numero salteado, no cambian cuantos valores espera
# Meta: espera la lista completa hasta el mayor.
repetida = ficha(cuerpo="{{1}}, te escribimos a ti, {{1}}. Corte: {{3}}")
revisar(repetida["variables"] == 3,
        "un hueco repetido y otro salteado siguen pidiendo hasta el mayor")


# =============================================================================
print("\n-- 2. el encabezado tambien tiene variables (defecto 1) ----------")
# =============================================================================

encabezado_solo = ficha(encabezado="Aviso para {{1}}", cuerpo="Tu servicio.")
revisar(encabezado_solo["variables"] == 1,
        "un {{1}} SOLO en el encabezado se cuenta",
        "Antes daba 0: el regex corria unicamente sobre el cuerpo.")
componentes = whatsapp.componentes_de_plantilla(encabezado_solo, ["Ana"])
revisar(textos_de(componentes, "header") == ["Ana"],
        "y viaja en el componente 'header', que antes no se armaba nunca")
revisar(parametros_de(componentes, "body") == [],
        "sin inventar un 'body' vacio")

# La trampa: los dos componentes numeran desde 1 por su cuenta.
ambos = ficha(encabezado="Aviso para {{1}}",
              cuerpo="Hola {{1}}, tu factura de {{2}} vence manana.")
revisar(ambos["variables"] == 3,
        "encabezado {{1}} + cuerpo {{1}}{{2}} son TRES valores, no dos",
        "Cada componente numera desde 1: los dos {{1}} son valores distintos.")
componentes = whatsapp.componentes_de_plantilla(ambos, ["ANA GOMEZ", "Ana", "$80.000"])
revisar(textos_de(componentes, "header") == ["ANA GOMEZ"],
        "el primero de la lista es el del encabezado (orden contractual)")
revisar(textos_de(componentes, "body") == ["Ana", "$80.000"],
        "y los que siguen son los del cuerpo, en orden")


# =============================================================================
print("\n-- 3. parametros nombrados (defecto 2) ---------------------------")
# =============================================================================

nombrada = ficha(cuerpo="Hola {{customer_name}}, debes {{amount}}.")
revisar(nombrada["formato_variables"] == "nombrado",
        "una plantilla con {{customer_name}} se reconoce como nombrada")
revisar(nombrada["variables"] == 2,
        "y pide sus dos valores",
        "Antes daba 0 y la plantilla salia sin un solo parametro.")
revisar(nombrada["variables_cuerpo"] == ["customer_name", "amount"],
        "los nombres se conservan, en orden de aparicion")

componentes = whatsapp.componentes_de_plantilla(nombrada, ["Ana", "$80.000"])
revisar([p.get("parameter_name") for p in parametros_de(componentes, "body")]
        == ["customer_name", "amount"],
        "cada parametro viaja con su 'parameter_name'",
        "Meta ata el valor por nombre: sin ese campo rechaza el envio.")

nombrada_encabezado = ficha(encabezado="Aviso para {{full_name}}",
                            cuerpo="Tu factura de {{amount}}.")
revisar(nombrada_encabezado["variables"] == 2,
        "un nombrado en el encabezado tambien se cuenta")
componentes = whatsapp.componentes_de_plantilla(nombrada_encabezado, ["Ana Gomez", "$80.000"])
revisar([p.get("parameter_name") for p in parametros_de(componentes, "header")]
        == ["full_name"],
        "y viaja en 'header' con su nombre")
revisar([p.get("parameter_name") for p in parametros_de(componentes, "body")]
        == ["amount"],
        "sin que se le pegue el del cuerpo")

# Un nombre repetido es UN valor: Meta lo ata por nombre, no por posicion.
repetido = ficha(cuerpo="{{name}}, te buscamos a ti, {{name}}.")
revisar(repetido["variables"] == 1,
        "un nombre repetido pide un solo valor",
        "Al reves que en posicional, donde se cuenta hasta el mayor.")

# Un posicional NO lleva parameter_name: mandarselo a Meta es un error.
posicionales = whatsapp.componentes_de_plantilla(solo_cuerpo, ["Ana", "$80.000"])
revisar(all("parameter_name" not in p for p in parametros_de(posicionales, "body")),
        "una plantilla posicional NO manda 'parameter_name'")


# =============================================================================
print("\n-- 4. la mezcla, que no es un formato de Meta --------------------")
# =============================================================================

mixta = ficha(cuerpo="Hola {{1}}, debes {{amount}}.")
revisar(mixta["formato_variables"] == "mixto",
        "mezclar {{1}} con {{amount}} se marca como 'mixto'")
revisar(mixta["variables_cuerpo"] == [],
        "y no se adivina un orden",
        "Cualquiera de las dos lecturas pone un valor en el lugar de otro.")

# Tambien cuando la mezcla esta repartida entre los dos componentes: cada uno
# es valido por su cuenta y la plantilla entera no lo es.
cruzada = ficha(encabezado="Aviso para {{1}}", cuerpo="Debes {{amount}}.")
revisar(cruzada["formato_variables"] == "mixto",
        "encabezado posicional + cuerpo nombrado tambien es 'mixto'")

# Y el endpoint la rechaza ANTES de comparar cantidades.
ruta = Path(__file__).resolve().parents[1] / "nucleo" / "canales" / "api.py"
api = ruta.read_text(encoding="utf-8")
cuerpo_endpoint = api[api.index("def conversaciones_enviar_plantilla("):
                      api.index("\ndef _rellenar(")]
revisar('"mixto"' in cuerpo_endpoint,
        "el endpoint de enviar rechaza una plantilla mixta")
revisar(cuerpo_endpoint.index('"mixto"') < cuerpo_endpoint.index('!= elegida["variables"]'),
        "y la rechaza ANTES de contar",
        "Una mixta cuenta 0 huecos: sin este orden pasaria como 'sin variables'.")


# =============================================================================
print("\n-- 5. ninguna plantilla sale con menos valores de los que pide ---")
# =============================================================================
# La comprobacion general, sobre toda la bateria: lo que Meta espera es un
# parametro por hueco de cada componente. Esta seccion es la que caza el
# defecto original sin saber cual era.

bateria = [
    ("solo cuerpo posicional", ficha(cuerpo="Hola {{1}} y {{2}}")),
    ("solo encabezado posicional", ficha(encabezado="Para {{1}}", cuerpo="Hola")),
    ("encabezado y cuerpo", ficha(encabezado="Para {{1}}", cuerpo="Hola {{1}} {{2}}")),
    ("solo cuerpo nombrado", ficha(cuerpo="Hola {{name}} y {{plan}}")),
    ("solo encabezado nombrado", ficha(encabezado="Para {{name}}", cuerpo="Hola")),
    ("ambos nombrados", ficha(encabezado="Para {{who}}", cuerpo="{{name}} - {{plan}}")),
    ("sin variables", ficha(cuerpo="Ya te atendemos.")),
    ("repetido posicional", ficha(cuerpo="{{1}} y {{1}} y {{3}}")),
]

for etiqueta, plantilla in bateria:
    cuantas = plantilla["variables"]
    valores = [f"v{i}" for i in range(1, cuantas + 1)]
    componentes = whatsapp.componentes_de_plantilla(plantilla, valores)
    enviados = sum(len(c["parameters"]) for c in componentes)

    # Lo que Meta exige, contado sobre el TEXTO de cada componente y no sobre
    # lo que el propio codigo dedujo -- si no, se estaria comparando el
    # defecto contra si mismo.
    exige = (len(whatsapp.huecos_de(plantilla["encabezado"])[1])
             + len(whatsapp.huecos_de(plantilla["cuerpo"])[1]))
    revisar(enviados == exige == cuantas,
            f"{etiqueta}: manda {enviados}, Meta pide {exige}, se piden {cuantas}")

    # Y ningun valor se pierde por el camino.
    mandados = [p["text"] for c in componentes for p in c["parameters"]]
    revisar(mandados == valores,
            f"{etiqueta}: los valores llegan completos y en orden")


# =============================================================================
print("\n-- 6. lo que se manda y lo que se guarda son lo mismo ------------")
# =============================================================================
# _armar_plantilla arma el texto del hilo; componentes_de_plantilla arma el
# envio. Reparten la MISMA lista plana y tienen que hacerlo igual.

from nucleo.canales.api import _armar_plantilla  # noqa: E402

for etiqueta, plantilla in bateria:
    valores = [f"v{i}" for i in range(1, plantilla["variables"] + 1)]
    texto = _armar_plantilla(plantilla, valores)
    componentes = whatsapp.componentes_de_plantilla(plantilla, valores)

    # Cada hueco que EXISTE en el texto recibio su valor, y el mismo que se
    # le mando a Meta.
    #
    # No se afirma sobre todos los valores enviados: en posicional la lista va
    # completa hasta el mayor, asi que un texto con {{1}} y {{3}} manda un
    # segundo valor que NO aparece en ningun lado. Meta lo exige igual, y el
    # hilo no tiene donde ponerlo -- afirmar lo contrario seria exigir que el
    # texto muestre un hueco que la plantilla no tiene.
    del_encabezado = plantilla["variables_encabezado"]
    corte = len(del_encabezado)
    for origen, huecos, suyos in (
            (plantilla["encabezado"], del_encabezado, valores[:corte]),
            (plantilla["cuerpo"], plantilla["variables_cuerpo"], valores[corte:])):
        for hueco, valor in zip(huecos, suyos):
            if "{{" + hueco + "}}" not in origen:
                continue
            revisar(valor in texto,
                    f"{etiqueta}: el hueco {{{{{hueco}}}}} quedo con '{valor}'")
    # ...y no queda ningun hueco sin llenar.
    revisar("{{" not in texto,
            f"{etiqueta}: no queda ningun hueco sin rellenar en el hilo",
            "Antes el encabezado se concatenaba crudo: el hilo mostraba {{1}}.")

# El caso que mas duele: el mismo numero en los dos componentes tiene que
# recibir valores DISTINTOS.
dos = ficha(encabezado="Para {{1}}", cuerpo="Hola {{1}}")
texto = _armar_plantilla(dos, ["ANA GOMEZ", "Ana"])
revisar(texto.startswith("Para ANA GOMEZ") and texto.endswith("Hola Ana"),
        "el {{1}} del encabezado y el del cuerpo reciben valores distintos",
        "Rellenarlos con la misma lista pondria el mismo valor en los dos.")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Las variables se cuentan enteras y viajan donde Meta las espera.")
