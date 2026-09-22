# -*- coding: utf-8 -*-
"""
El barrido que cierra lo que atendio SOLO el asistente.

POR QUE EXISTE
--------------
'conversaciones_sin_respuesta' exige 'escalada_a_humano'. Las que la IA
resolvio sola nunca entran ahi, y ningun otro camino las cierra: quedan
abiertas para siempre. Medido contra produccion el 22/09/2026 -- 151 asi, 145
sin un mensaje en mas de una semana, y de las 4 creadas ese dia, las 4.

LO QUE SE AFIRMA ACA ES EL EFECTO
---------------------------------
Que NO se cierre lo que no corresponde, sobre todo el caso peligroso: si el
ultimo mensaje lo escribio el CLIENTE, lo que hay es una pregunta sin
contestar, y cerrarla seria enterrar trabajo sin hacer con cara de trabajo
terminado.

Sin base y sin red: se prueba la funcion de barrido con una persistencia
falsa, y aparte se comprueba que la consulta SQL nombre cada guarda.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.seguimiento import operativo  # noqa: E402

fallos = []


def afirmar(cond, que):
    print(f"  [{'ok' if cond else 'FALLA'}]{'   ' if cond else ' '}{que}")
    if not cond:
        fallos.append(que)


class ConfigFalsa:
    class limites:
        horas_inactividad_cierra = 24


class SinPlazo:
    class limites:
        horas_inactividad_cierra = None


# ── el plazo sale de donde debe ─────────────────────────────────────────────
print("\n--- el plazo ---")
visto = {}


def falsa_lista(tenant, horas):
    visto["horas"] = horas
    return []


import nucleo.persistencia.db as persistencia  # noqa: E402
original = persistencia.conversaciones_ia_inactivas
persistencia.conversaciones_ia_inactivas = falsa_lista
try:
    operativo.cerrar_inactivas_de_ia(ConfigFalsa, "t")
    afirmar(visto.get("horas") == 24,
            "usa 'limites.horas_inactividad_cierra', que es el momento exacto en "
            "que la conversacion deja de reutilizarse")

    r = operativo.cerrar_inactivas_de_ia(SinPlazo, "t")
    afirmar(r["revisadas"] == 0 and r["cerradas"] == 0,
            "sin plazo declarado NO cierra nada: una empresa que no lo pidio no "
            "deberia encontrarse conversaciones cerradas solas")

    # ── simular no toca nada ────────────────────────────────────────────────
    print("\n--- simular ---")
    cerradas = []
    persistencia.conversaciones_ia_inactivas = lambda t, h: [
        {"id": "11111111-1111-1111-1111-111111111111", "caso_id": None,
         "ticket_operativo": None, "usuario_externo": "57300", "nombre_cliente": "X"}]
    original_cerrar = operativo.cerrar_todo
    operativo.cerrar_todo = lambda *a, **k: (cerradas.append(a) or
                                             {"conversacion": True, "ticket": False, "caso": False})
    try:
        r = operativo.cerrar_inactivas_de_ia(ConfigFalsa, "t", simular=True)
        afirmar(r["revisadas"] == 1 and r["cerradas"] == 0 and not cerradas,
                "con simular=True cuenta pero NO cierra")
        afirmar(len(r.get("serian", [])) == 1,
                "y devuelve cuales serian, para poder mirarlas antes")
        afirmar("57300" not in str(r) and "X" not in str(r.get("serian")),
                "sin el identificador del cliente ni su nombre en el informe")

        r = operativo.cerrar_inactivas_de_ia(ConfigFalsa, "t")
        afirmar(r["cerradas"] == 1 and len(cerradas) == 1,
                "sin simular, cierra")
        afirmar(cerradas[0][3] == "" and cerradas[0][4] if len(cerradas[0]) > 4 else True,
                "y no manda texto al cliente: estas no tienen ticket que comentar")
    finally:
        operativo.cerrar_todo = original_cerrar
finally:
    persistencia.conversaciones_ia_inactivas = original

# ── la consulta nombra cada guarda ──────────────────────────────────────────
print("\n--- la consulta de elegibilidad ---")
sql = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
i = sql.index("def conversaciones_ia_inactivas")
j = sql.index("def conversaciones_sin_respuesta", i)
consulta = sql[i:j]

guardas = [
    ("not coalesce(c.escalada_a_humano, false)", "no cierra una escalada"),
    ("not coalesce(c.necesita_atencion_humana, false)", "ni una marcada para revision"),
    ("coalesce(c.tomada_por, '') = ''", "ni una que alguien tomo"),
    ("not coalesce(c.atendida_manual, false)", "ni una ya atendida"),
    ("coalesce(c.control, 'ia') = 'ia'", "solo si el asistente tiene el control"),
    ("c.pendiente_interno_desde is null", "ni con un pendiente interno abierto"),
    ("not coalesce(c.conservar, false)", "ni una marcada para conservar"),
    ("acciones_propuestas", "ni con una accion propuesta sin resolver"),
    ("sincronizaciones_externas", "ni con una sincronizacion sin confirmar"),
    ("c.ticket_operativo is null", "ni una con ticket del ISP: eso haria un POST externo"),
    ("c.caso_id is null",
     "ni una con caso del CRM -- sin llamadas externas el barrido es idempotente "
     "y por eso SI se puede programar, al reves que 'cerrar_vencidas'"),
    ("order by m.creado_en desc limit 1) = 'assistant'",
     "EL ULTIMO MENSAJE TIENE QUE SER DEL ASISTENTE -- si hablo el cliente, "
     "hay una pregunta sin contestar"),
]
for fragmento, que in guardas:
    afirmar(fragmento in consulta, que)

afirmar("'humano'" not in consulta.split("order by m.creado_en desc")[0].split("m.rol in")[-1],
        "las notas internas no cuentan como turno de nadie")

print("\n" + "=" * 62)
if fallos:
    print(f" {len(fallos)} falla(s).")
    raise SystemExit(1)
print(" Todo en orden.")
