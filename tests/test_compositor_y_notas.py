# -*- coding: utf-8 -*-
"""
Lo que NUNCA puede pasar en el compositor de la bandeja.

    py -3.13 tests/test_compositor_y_notas.py

Corre SIN RED y SIN BASE: lee el codigo fuente y comprueba propiedades
estructurales. No prueba que enviar funcione --eso se prueba contra la API
real-- sino que ciertos caminos no EXISTAN.

LAS TRES COSAS QUE FIJA
-----------------------
1. Una nota interna no se le puede enviar al cliente.
   La garantia no es una bandera que alguien puede olvidar mirar: es que la
   ruta que guarda notas no llama al canal en ningun punto, y que la funcion
   que las persiste no toca la tabla de conversaciones (no marca atendida:
   dejar anotado algo no es haberse hecho cargo del caso).

2. No se declara un tipo de multimedia que no se probo.
   Video y sticker existen en la API de Meta. Declararlos sin haberlos
   probado contra esta cuenta es exactamente lo que costo tiempo con la API
   de WispHub -- ver la skill 'wisphub-api'.

3. Un audio no lleva pie de foto.
   Meta acepta 'caption' en imagen y documento, y en AUDIO lo ignora EN
   SILENCIO. Si alguien marcara audio como que acepta pie, el texto que
   escribio junto a su nota de voz no le llegaria nunca al cliente y nada lo
   avisaria.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nucleo.canales.whatsapp import LIMITES_MEDIA  # noqa: E402

fallos: list[str] = []


def revisar(ok: bool, que: str, detalle: str = "") -> None:
    if ok:
        print(f"  ok     {que}")
    else:
        fallos.append(que)
        print(f"  FALLA  {que}" + (f"\n         {detalle}" if detalle else ""))


def _cuerpo(fuente: str, encabezado: str) -> str:
    """El cuerpo de una funcion, hasta la siguiente definicion de nivel 0."""
    i = fuente.index(encabezado)
    resto = fuente[i + len(encabezado):]
    corte = re.search(r"\n@app\.|\ndef ", resto)
    return resto[: corte.start()] if corte else resto


api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")


# --- 1. la nota no tiene por donde salir ------------------------------------
ruta_nota = _cuerpo(api, "def conversaciones_nota(id_conversacion):")
revisar("whatsapp." not in ruta_nota,
        "la ruta de nota interna no llama al canal",
        "Si tiene que enviar algo, no es una nota: es una respuesta, y va "
        "por /humano.")

fn_nota = _cuerpo(db, "def agregar_nota_interna(tenant: str, conversation_id: str, contenido: str,")
revisar("update asistente.conversations" not in fn_nota.lower(),
        "guardar una nota no marca la conversacion como atendida",
        "Dejar anotado algo no es haberse hecho cargo del caso: si esto "
        "marcara atendida, el caso saldria de la cola sin que nadie le "
        "contestara a quien espera.")

# La lista de la bandeja muestra el ultimo mensaje. Una nota ahi se leeria
# como algo que se le dijo al cliente.
revisar("rol <> 'nota'" in db,
        "la nota no aparece como ultimo mensaje en la bandeja")


# --- 2. no se declara lo que no se probo ------------------------------------
PROBADOS = {"image", "document", "audio"}
extra = set(LIMITES_MEDIA) - PROBADOS
revisar(not extra,
        "no hay tipos de multimedia declarados sin probar",
        f"{sorted(extra)} aparecen en LIMITES_MEDIA. Si se probaron de "
        "verdad contra la cuenta real, sumarlos a PROBADOS aca y decir "
        "cuando se probaron. Si no, sacarlos: declarar un tipo sin "
        "verificarlo es lo que costo tiempo con la API de WispHub."
        if extra else "")


# --- 3. el audio no acepta pie ----------------------------------------------
revisar(LIMITES_MEDIA["audio"]["acepta_pie"] is False,
        "el audio no se declara como que acepta pie de foto",
        "Meta ignora 'caption' en audio EN SILENCIO: el texto que alguien "
        "escriba junto a su nota de voz no le llegaria al cliente y nada lo "
        "avisaria.")

# Y que la pantalla haga algo con esa distincion, en vez de tirar el texto.
pantalla = (RAIZ / "django-crm" / "frontend" / "src" / "routes" / "(app)"
            / "conversaciones" / "[id]" / "+page.svelte").read_text(encoding="utf-8")
revisar("acepta_pie" in pantalla,
        "la pantalla consulta acepta_pie antes de mandar el texto como pie")


# --- 4. los limites salen del canal, no de una copia en la pantalla ---------
# Una tabla de topes duplicada en el frontend se desincroniza el dia que Meta
# cambie uno, y el sintoma seria un archivo que se sube entero para que lo
# rechacen al final.
copiados = [str(l["max_bytes"]) for l in LIMITES_MEDIA.values()]
revisar(not any(c in pantalla for c in copiados),
        "la pantalla no tiene una copia de los topes de tamaño",
        "Los pide por /api/canales/limites-media a proposito.")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Una nota no sale al cliente, y no se declara nada sin probar.")
