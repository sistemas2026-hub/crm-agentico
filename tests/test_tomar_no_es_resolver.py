# -*- coding: utf-8 -*-
"""
Tomar un caso no es haberlo resuelto.

    py -3.13 tests/test_tomar_no_es_resolver.py

Corre SIN RED y SIN BASE: lee el codigo fuente.

QUE PASO
--------
El 07/09/2026 se agrego la pestaña "En atencion" y se calculo reusando
'atendida_manual'. Lo detecto una revision de la pantalla, no un test: "si
solo reutiliza atendida_manual, ojo, porque eso significa resuelta fuera del
chat y no 'estoy trabajando en esto'".

Era exacto, y el daño no era de vocabulario. 'atendida_manual' gobierna DOS
cierres automaticos del motor:

    db.py:625   un "ok, gracias" del cliente CIERRA el caso -- pero solo si
                alguien ya lo atendio. Ese chequeo existe por un incidente
                real: se cerro una conversacion con el cambio de clave sin
                hacer, porque un "ok" a nadie no confirma nada.

    db.py:799   el barrido por plazo vencido cierra SOLO lo ya atendido. Una
                que nadie toco no espera al cliente: espera al equipo, y
                cerrarla enterraria trabajo sin hacer con cara de terminado.

Con "Atender" escribiendo esa marca, pulsarlo para decir "me hago cargo"
dejaba el caso cerrable por un agradecimiento del cliente y por el barrido. Y
marcar_atendida() no tiene desmarcar, escrito a proposito.

No llego a corromper datos: la migracion que corrige lo marcado ese dia
encontro CERO filas. Se arreglo antes de que nadie lo pulsara.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fallos: list[str] = []


def revisar(ok: bool, que: str, detalle: str = "") -> None:
    if ok:
        print(f"  ok     {que}")
    else:
        fallos.append(que)
        print(f"  FALLA  {que}" + (f"\n         {detalle}" if detalle else ""))


db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
estado = (RAIZ / "django-crm" / "frontend" / "src" / "lib" / "conversaciones"
          / "estado.js").read_text(encoding="utf-8")


def _cuerpo(fuente: str, encabezado: str, sin_doc: bool = False) -> str:
    """El cuerpo de una funcion, hasta la siguiente definicion de nivel 0.

    'sin_doc' saca la documentacion. Sin eso, buscar 'atendida_manual'
    encuentra el parrafo que explica POR QUE no se toca esa marca, y el
    test falla por la explicacion de lo que esta BIEN hecho. Paso al
    escribir este archivo: el primer rojo fue del test, no del codigo."""
    i = fuente.index(encabezado)
    resto = fuente[i + len(encabezado):]
    corte = re.search(r"\n@app\.|\ndef ", resto)
    cuerpo = resto[: corte.start()] if corte else resto
    if sin_doc:
        partes = cuerpo.split(chr(34) * 3)
        if len(partes) > 2:
            cuerpo = partes[0] + "".join(partes[2:])
    return cuerpo


# --- 1. tomar no toca la marca de resolucion ---------------------------------
# Es LA propiedad. Si tomar_caso escribe 'atendida_manual', vuelve todo el
# problema: el caso queda cerrable por un "gracias" y por el barrido.
fn = _cuerpo(db, "def tomar_caso(tenant: str, conversation_id: str, por: str | None,",
             sin_doc=True)
revisar("atendida_manual" not in fn,
        "tomar un caso NO escribe 'atendida_manual'",
        "Esa marca significa 'resuelto por otro canal' y habilita el cierre "
        "por 'gracias' del cliente (db.py:625) y el barrido por plazo "
        "(db.py:799). Tomar un caso no resuelve nada.")

# --- 2. tomar se puede deshacer ----------------------------------------------
# Al reves que marcar_atendida(), que no tiene desmarcar a proposito: un caso
# se toma por error, se acaba un turno, o resulta que era de otra area.
revisar("soltar" in fn and "tomada_por = null" in fn,
        "tomar es reversible: se puede soltar")

# --- 3. la ruta de 'atender' usa tomar, no marcar_atendida -------------------
ruta = _cuerpo(api, "def conversaciones_atender(id_conversacion):")
revisar("tomar_caso" in ruta and "marcar_atendida" not in ruta,
        "la ruta /atender toma el caso, no lo marca como resuelto")

# --- 4. marcar_atendida sigue existiendo, para lo suyo -----------------------
# No se borro: 'Marcar como resuelta' la sigue necesitando, y ahi SI
# corresponde -- el caso se resolvio por telefono o en persona.
resolver = _cuerpo(api, "def conversaciones_resolver(id_conversacion):") \
    if "def conversaciones_resolver(" in api else ""
revisar("def marcar_atendida(" in db,
        "marcar_atendida sigue existiendo para 'Marcar como resuelta'",
        "Se borro: entonces no queda forma de decir que un caso se resolvio "
        "por telefono, que es para lo que se creo.")

# --- 5. la bandeja separa las dos cosas --------------------------------------
revisar("tomada_por" in estado,
        "la pestaña 'En atencion' mira quien lo tomo")
revisar("c.estado === 'cerrada'" in estado and "atendida_manual" not in
        estado.split("export const resuelta")[1].split("\n")[0],
        "'resuelta' es el estado cerrado, no la marca de atendida")

# --- 6. una conversacion tomada sale de 'Por atender' ------------------------
# Si no, sigue en la cola de todos y dos personas la toman a la vez.
pend = estado.split("export const pendiente")[1].split("export const")[0]
revisar("tomada_por" in pend,
        "una conversacion tomada sale de 'Por atender'",
        "Si sigue en la cola, dos personas pueden tomarla a la vez.")

# --- 7. la migracion existe y no toca lo historico ---------------------------
sql = RAIZ / "supabase" / "202609071900_tomar_caso.sql"
texto = sql.read_text(encoding="utf-8") if sql.exists() else ""
revisar("tomada_por" in texto and "2026-09-07" in texto,
        "la migracion corrige SOLO lo marcado el dia del error",
        "'atendida_manual' existe desde el 13/08 y todo lo anterior si "
        "significa resuelto: tocarlo reescribiria historia correcta.")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Tomar un caso y resolverlo son dos cosas distintas.")
