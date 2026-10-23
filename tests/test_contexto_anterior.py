# -*- coding: utf-8 -*-
"""
Cuando se le cuenta al modelo una conversacion anterior, se le dice CUANDO fue.

    py -3.13 tests/test_contexto_anterior.py

Corre SIN RED y SIN BASE.

QUE PASO
--------
07/09/2026, cliente real. Primer mensaje de la conversacion: "Hola". El
asistente contesto:

    "Veo que estuvimos hablando HACE UN MOMENTO sobre un problema de internet
     que no se habia resuelto. ¿Quieres retomar ese tema?"

Esa conversacion era del 12/08 -- veintiseis dias antes.

Lo primero que se penso fue que el modelo lo habia inventado. No: el motor le
PASA el resumen de la conversacion anterior a proposito, para no hacerle
repetir al cliente lo que ya conto. El resumen era correcto. Lo que faltaba
era la FECHA -- sin ella, una conversacion de hace dos horas y una de hace un
mes le llegan al modelo exactamente iguales, y el hueco lo rellena con
"recien".

POR QUE ESTE TEST Y NO SOLO UN CASO DORADO
------------------------------------------
Hay un caso dorado ('no dice que hablaron recien si fue hace semanas'), y
sirve como muestra. Pero NO alcanza como guarda, y esta medido: revirtiendo
el arreglo, el caso pasa 4 de 4. Sin fecha el modelo casi siempre no menciona
nada; solo a veces rellena. Un fallo intermitente no se atrapa con una
afirmacion sobre lo que el modelo dijo una vez.

Lo que si es determinista es el MENSAJE que se le manda. Eso es lo que fija
este test: que el tiempo este ahi, y que este bien contado.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nucleo.seguimiento.resumen import como_contexto, hace_cuanto  # noqa: E402

fallos: list[str] = []


def revisar(ok: bool, que: str, detalle: str = "") -> None:
    if ok:
        print(f"  ok     {que}")
    else:
        fallos.append(que)
        print(f"  FALLA  {que}" + (f"\n         {detalle}" if detalle else ""))


# --- 1. el tiempo se cuenta en palabras, y bien ------------------------------
# En palabras y no en una fecha porque es lo que el modelo va a REPETIR: "el
# 12 de agosto" lo obliga a calcular cuanto hace de eso.
ESPERADO = [
    (0.25, "hace 15 minutos"),
    (1.0, "hace 1 hora"),
    (5.0, "hace 5 horas"),
    (23.9, "hace 23 horas"),
    (25.0, "ayer"),
    (48.0, "hace 2 dias"),
    (624.0, "hace 26 dias"),      # el caso real
    (1680.0, "hace 2 meses"),
]
malos = [(h, e, hace_cuanto(h)) for h, e in ESPERADO if hace_cuanto(h) != e]
revisar(not malos, "el tiempo transcurrido se dice en palabras y da bien",
        "; ".join(f"{h}h -> {d!r}, se esperaba {e!r}" for h, e, d in malos))


# --- 2. la fecha ESTA en el mensaje que ve el modelo -------------------------
# Esto es lo que faltaba. Sin esto no hay nada que impida que vuelva a pasar.
mensaje = como_contexto("El cliente reporto falta de internet.", 624.0)["content"]
revisar("26 dias" in mensaje.lower(),
        "el mensaje al modelo dice cuanto hace que fue esa conversacion",
        "Sin el tiempo, una conversacion de hace dos horas y una de hace un "
        "mes son indistinguibles para el modelo.")

# Y no solo mencionado al pasar: se le dice explicitamente que no la llame
# reciente si no lo fue.
revisar("hace un momento" in mensaje.lower() and "de verdad" in mensaje.lower(),
        "se le prohibe explicitamente decir 'hace un momento' si no lo fue")


# --- 3. sin el dato, se DICE que no se sabe ----------------------------------
# Callarlo es lo que produjo el fallo: un modelo sin fecha rellena el hueco, y
# rellena con "recien". Decir "no consta" es peor redaccion y mejor verdad.
sin_fecha = como_contexto("Algo paso.", None)["content"]
revisar("no consta" in sin_fecha.lower(),
        "sin la fecha, el mensaje dice que no consta en vez de callarlo")


# --- 4. quien lo llama tiene de donde sacar las horas ------------------------
# El test no toca la base: comprueba el CONTRATO. Si resumen_anterior vuelve a
# devolver solo el texto, el llamador no tiene que pasarle a como_contexto y
# el arreglo se deshace en silencio -- el valor por defecto lo taparia.
fuente_db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
i = fuente_db.index("def resumen_anterior(")
firma = fuente_db[i:fuente_db.index('"""', i)]
revisar("tuple[str, float]" in firma,
        "resumen_anterior devuelve el resumen Y cuanto hace",
        "Devolver solo el texto deja al llamador sin las horas, y como "
        "como_contexto las tiene opcionales, el arreglo se perderia sin "
        "ningun error.")

fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
revisar("como_contexto(texto_previo, horas_previo)" in fuente_api,
        "el motor le pasa las horas a como_contexto",
        "api.py llama a como_contexto sin el segundo argumento: el mensaje "
        "volveria a no decir cuando fue.")


# --- 5. el parametro sigue siendo opcional, pero avisando --------------------
# No se hace obligatorio a proposito: romper a un llamador viejo por esto
# seria peor. Lo que no puede es fallar en silencio, y por eso el caso 3.
firma_ctx = inspect.signature(como_contexto)
revisar(list(firma_ctx.parameters) == ["resumen", "horas"],
        "como_contexto recibe el resumen y las horas")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Al modelo se le dice cuando fue la conversacion anterior.")
