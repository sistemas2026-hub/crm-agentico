# -*- coding: utf-8 -*-
"""
La ventana de 24 h la abre el CLIENTE, y nadie mas.

    py -3.13 tests/test_ventana_whatsapp.py

Corre SIN RED y SIN BASE.

QUE ES
------
Meta solo acepta texto libre dentro de las 24 h desde el ultimo mensaje del
cliente. Fuera de eso solo pasan plantillas aprobadas. Hasta el 08/09/2026 el
operador se enteraba de esa regla cuando pulsaba Enviar y fallaba: el motivo
quedaba marcado en la burbuja (bien) pero despues de haber escrito la
respuesta (tarde).

EL ERROR FACIL, Y POR QUE ESTE ARCHIVO EXISTE
---------------------------------------------
Calcular la ventana desde "el ultimo mensaje de la conversacion" en vez de
"el ultimo mensaje DEL CLIENTE". Las dos lecturas dan igual en la mayoria de
los casos y la diferencia solo aparece cuando importa: cada respuesta nuestra
--del asistente o de una persona-- renovaria la ventana en la pantalla
mientras Meta la considera cerrada. La pantalla diria "quedan 23 h 58 min" y
el envio fallaria igual. Seria peor que no mostrar nada, porque ahora ademas
hay un cartel afirmandolo.

'conversations' tiene 'actualizado_en' y 'ultimo_mensaje_en' a mano, y las
dos son la respuesta equivocada.

LA PANTALLA INFORMA, EL BACKEND MANDA
-------------------------------------
Nada de esto es una autorizacion: quien decide es Meta cuando recibe el
envio, y el reloj de este proceso puede estar corrido respecto del suyo. Por
eso el manejo del error 131047 sigue existiendo -- se comprueba mas abajo que
no se haya reemplazado por el calculo local.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nucleo.canales.whatsapp import (                          # noqa: E402
    CODIGO_FUERA_DE_VENTANA, VENTANA_HORAS, estado_de_ventana)

fallos: list[str] = []


def revisar(ok: bool, que: str, detalle: str = "") -> None:
    if ok:
        print(f"  ok     {que}")
    else:
        fallos.append(que)
        print(f"  FALLA  {que}" + (f"\n         {detalle}" if detalle else ""))


AHORA = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def hace(**kw):
    return AHORA - timedelta(**kw)


# =============================================================================
#  Los cuatro casos
# =============================================================================

# --- 1. el cliente escribio hace 23:59 -> abierta -----------------------------
v = estado_de_ventana(hace(hours=23, minutes=59), AHORA)
revisar(v["abierta"] is True and v["restante_seg"] == 60,
        "cliente hace 23:59 -> ventana ABIERTA",
        f"abierta={v['abierta']}, restante={v['restante_seg']}s")

# Y avisa que esta por cerrarse, que es el unico momento en que el dato
# cambia lo que alguien hace: contestar ahora en vez de manana.
revisar(v["por_cerrarse"] is True,
        "a un minuto del cierre, avisa que esta por cerrarse")

# --- 2. hace 24:01 -> cerrada -------------------------------------------------
v = estado_de_ventana(hace(hours=24, minutes=1), AHORA)
revisar(v["abierta"] is False,
        "cliente hace 24:01 -> ventana CERRADA",
        f"abierta={v['abierta']}")
revisar(v["restante_seg"] == 0,
        "cerrada no devuelve un restante negativo",
        f"restante={v['restante_seg']} -- un negativo se dibuja como un "
        f"contador al reves.")

# --- 3. nosotros escribimos hace 2 min, el cliente hace 25 h -> CERRADA -------
# El caso que hace falta blindar. La firma de la funcion ya lo hace imposible
# de confundir --recibe el ultimo ENTRANTE, no "el ultimo mensaje"-- pero lo
# que se equivoca no es esta funcion sino QUIEN LA LLAMA.
v = estado_de_ventana(hace(hours=25), AHORA)
revisar(v["abierta"] is False,
        "cliente hace 25 h aunque nosotros escribimos hace 2 min -> CERRADA")

# Asi que se comprueba el dato que llega: la consulta que lo produce tiene
# que filtrar por rol de cliente, no mirar cualquier mensaje.
db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
sub = re.search(
    r"\(select max\(u\.creado_en\).{0,400}?as ultimo_mensaje_cliente",
    db, re.S)
revisar(sub is not None,
        "el encabezado de la conversacion trae 'ultimo_mensaje_cliente'",
        "Sin ese dato la pantalla no tiene de donde calcular la ventana.")
if sub:
    texto = sub.group(0)
    revisar("u.rol = 'user'" in texto,
            "ese dato mira SOLO los mensajes del cliente",
            "Si no filtra por rol, cada respuesta nuestra renueva la ventana "
            "en la pantalla mientras Meta la considera cerrada.")
    revisar("actualizado_en" not in texto and "ultimo_mensaje_en" not in texto,
            "no se resuelve con 'actualizado_en' ni 'ultimo_mensaje_en'",
            "Las dos estan a mano en la misma tabla y las dos se mueven "
            "cuando escribimos nosotros.")

# --- 4. se manda una plantilla con la ventana cerrada -> SIGUE cerrada --------
# Estructural: lo que decide es con que rol se guarda. La plantilla entra por
# agregar_mensaje_humano(), que escribe 'assistant' -- y la ventana solo
# cuenta 'user'. No hay ninguna bandera que alguien pueda olvidar de apagar.
api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
i = api.index("def conversaciones_enviar_plantilla(")
ruta_plantilla = api[i:api.index("\ndef _armar_plantilla(")]

revisar("agregar_mensaje_humano" in ruta_plantilla,
        "la plantilla se guarda por el mismo camino que una respuesta humana")
revisar("'user'" not in ruta_plantilla and '"user"' not in ruta_plantilla,
        "mandar una plantilla NO escribe un mensaje de cliente",
        "Si lo hiciera, mandar una plantilla abriria la ventana sola y el "
        "operador podria escribir texto libre que Meta va a rechazar.")

# Y que se guarde el texto ARMADO, no el nombre de la plantilla: el hilo tiene
# que mostrar lo que el cliente leyo.
revisar("_armar_plantilla" in ruta_plantilla,
        "se guarda el texto final, no el nombre de la plantilla")


# =============================================================================
#  Lo que sostiene a los cuatro
# =============================================================================

# --- el backend sigue siendo quien decide ------------------------------------
wa = (RAIZ / "nucleo" / "canales" / "whatsapp.py").read_text(encoding="utf-8")
revisar(CODIGO_FUERA_DE_VENTANA == 131047 and "CODIGO_FUERA_DE_VENTANA" in wa,
        "el manejo del rechazo de Meta por ventana sigue existiendo",
        "El calculo local es una ayuda para la pantalla, no un permiso: el "
        "reloj de este proceso puede estar corrido respecto del de Meta.")

revisar(VENTANA_HORAS == 24,
        f"la ventana son 24 horas (hoy: {VENTANA_HORAS})")

# --- sin mensajes del cliente no se afirma nada ------------------------------
# Una conversacion que abrimos nosotros, o de otro canal, no tiene ventana
# 'cerrada': tiene ventana desconocida. Decir 'cerrada' bloquearia el
# compositor por un dato que no existe.
v = estado_de_ventana(None, AHORA)
revisar(v["abierta"] is None,
        "sin ningun mensaje del cliente, la ventana es DESCONOCIDA, no cerrada",
        f"devolvio abierta={v['abierta']}, que la pantalla leeria como una "
        f"prohibicion.")

# --- solo WhatsApp ------------------------------------------------------------
# El simulador y la API no tienen esta regla. Heredarla por descuido dejaria a
# alguien sin poder escribir donde nadie se lo impide.
j = api.index("def conversaciones_mensajes(")
ruta_mensajes = api[j:api.index("@app.get(\"/canales/plantillas\")")]
revisar('canal") == "whatsapp"' in ruta_mensajes
        or "canal') == 'whatsapp'" in ruta_mensajes,
        "la ventana solo se calcula para el canal whatsapp")

# --- la plantilla que se manda es una que Meta aprobo -------------------------
revisar("APPROVED" in ruta_plantilla,
        "solo se manda una plantilla aprobada",
        "Ofrecer una en revision es ofrecer un envio que va a fallar.")
# Y se vuelve a mirar la lista al enviar, no se confia en lo que mando la
# pantalla: el nombre viaja por la red y el selector se dibujo hace rato.
revisar("plantillas_aprobadas" in ruta_plantilla,
        "el nombre que llega de la pantalla se vuelve a validar contra Meta")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La ventana la abre el cliente, y nadie mas.")
