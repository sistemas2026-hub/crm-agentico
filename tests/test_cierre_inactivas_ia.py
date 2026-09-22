# -*- coding: utf-8 -*-
"""
El barrido que cierra lo que atendio SOLO el asistente.

POR QUE EXISTE
--------------
'conversaciones_sin_respuesta' exige 'escalada_a_humano'. Las que la IA
resolvio sola nunca entran ahi, y ningun otro camino las cierra: quedan
abiertas para siempre. Medido contra produccion el 22/09/2026 -- 151 asi, 145
sin un mensaje en mas de una semana, y de las 4 creadas ese dia, las 4.

POR QUE DOS COHORTES Y NO UN TOPE POR PASADA
--------------------------------------------
La primera version de la guarda era un tope, ordenando por mas antigua
primero. Estaba mal de dos formas, las dos medidas:

  - Ordenar por antiguedad cierra EL BACKLOG PRIMERO, que es exactamente lo
    que el tope pretendia evitar.
  - El reloj corre cada 60 minutos. Con tope 10 son 240 cierres por dia: las
    147 historicas se iban en 0,6 dias, no en dos semanas.

Ir mas despacio no era la respuesta. La frontera temporal si.

LO QUE SE AFIRMA ACA ES EL EFECTO
---------------------------------
Que NO se cierre lo que no corresponde. Sobre todo dos cosas: el backlog
mientras el backfill este apagado, y cualquier conversacion donde el ULTIMO
que hablo fue el cliente -- ahi hay una pregunta sin contestar, y cerrarla
seria enterrar trabajo sin hacer con cara de trabajo terminado.

Sin base y sin red: persistencia falsa para el barrido, y lectura del SQL
para comprobar que cada guarda este declarada.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import nucleo.persistencia.db as persistencia  # noqa: E402
import nucleo.seguimiento.operativo as operativo  # noqa: E402
from nucleo.config.schema import CierreInactivasIA  # noqa: E402

fallos = []


def afirmar(cond, que):
    print(f"  [{'ok' if cond else 'FALLA'}]{'   ' if cond else ' '}{que}")
    if not cond:
        fallos.append(que)


CORTE = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)


def cfg(habilitado=True, corte=CORTE, backfill=False, lote=10, horas=24):
    return SimpleNamespace(
        limites=SimpleNamespace(horas_inactividad_cierra=horas),
        cierre_inactivas_ia=CierreInactivasIA(
            habilitado=habilitado, rollout_cutoff=corte,
            backfill_habilitado=backfill, backfill_lote=lote))


def conv(n):
    return {"id": f"{n:08d}-0000-0000-0000-000000000000", "caso_id": None,
            "ticket_operativo": None, "usuario_externo": "57300000000",
            "nombre_cliente": "CLIENTE DE PRUEBA"}


class Falsa:
    """Devuelve filas segun la cohorte que le pidan, y anota que le pidieron."""

    def __init__(self, nuevas=0, backlog=0):
        self.nuevas, self.backlog = nuevas, backlog
        self.pedidos = []

    def __call__(self, tenant, horas, *, corte=None, cohorte="normal", limite=None):
        self.pedidos.append((cohorte, limite, corte))
        if corte is None:
            return []
        n = self.nuevas if cohorte == "normal" else self.backlog
        filas = [conv(i) for i in range(n)]
        return filas[:limite] if (limite and cohorte == "backlog") else filas


_lista = persistencia.conversaciones_ia_inactivas
_cerrar = operativo.cerrar_todo


def correr(config, nuevas=0, backlog=0, simular=False, espia=None):
    cerrados = []
    persistencia.conversaciones_ia_inactivas = espia or Falsa(nuevas, backlog)
    operativo.cerrar_todo = lambda *a, **k: (
        cerrados.append(a[2]["id"]) or
        {"conversacion": True, "ticket": False, "caso": False})
    try:
        r = operativo.cerrar_inactivas_de_ia(config, "t", simular=simular)
        r["_cerrados"] = cerrados
        return r
    finally:
        persistencia.conversaciones_ia_inactivas = _lista
        operativo.cerrar_todo = _cerrar


# ── los dos interruptores ────────────────────────────────────────────────────
print("\n--- fail-closed: dos interruptores, y los dos apagan ---")

r = correr(cfg(habilitado=False), nuevas=5, backlog=100)
afirmar(r["cerradas"] == 0 and "apagado" in r.get("motivo", ""),
        "con 'habilitado' en false no cierra nada, aunque haya 105 candidatas")

r = correr(cfg(corte=None), nuevas=5, backlog=100)
afirmar(r["cerradas"] == 0 and "rollout_cutoff" in r.get("motivo", ""),
        "SIN corte no cierra nada: desplegar el codigo no puede empezar a "
        "cerrar conversaciones sin que alguien elija desde cuando")

r = correr(cfg(horas=0), nuevas=5)
afirmar(r["cerradas"] == 0,
        "y sin plazo de inactividad declarado, tampoco")

afirmar(CierreInactivasIA().habilitado is False
        and CierreInactivasIA().rollout_cutoff is None
        and CierreInactivasIA().backfill_habilitado is False,
        "los tres vienen apagados por defecto: un tenant que no lo pidio no se "
        "encuentra conversaciones cerradas solas")

# ── las dos cohortes ─────────────────────────────────────────────────────────
print("\n--- las dos cohortes ---")

r = correr(cfg(), nuevas=3, backlog=147)
afirmar(r["cerradas"] == 3,
        "cierra el flujo normal (3) y NO toca el backlog, aunque sean 147")
afirmar(r["backlog_elegible"] == 147,
        "pero informa cuantas hay en el backlog: sin ese numero no se sabe si avanza")
afirmar(r["backfill_que_cerraria"] == 0,
        "con el backfill apagado no cerraria ninguna vieja")

r = correr(cfg(backfill=True, lote=10), nuevas=3, backlog=147)
afirmar(r["cerradas"] == 13,
        "con backfill encendido: las 3 nuevas MAS el lote de 10")
afirmar(r["backfill_que_cerraria"] == 10,
        "el lote se respeta -- 10, no 147")

r = correr(cfg(backfill=True, lote=10), nuevas=50, backlog=147)
afirmar(r["cerradas"] == 60,
        "el flujo normal NO consume el cupo del backfill: 50 + 10, no 10")

r = correr(cfg(backfill=True, lote=10), nuevas=0, backlog=4)
afirmar(r["cerradas"] == 4,
        "si el backlog es menor que el lote, cierra lo que hay y no falla")

# ── simular ──────────────────────────────────────────────────────────────────
print("\n--- simular ---")

r = correr(cfg(backfill=True), nuevas=3, backlog=147, simular=True)
afirmar(r["cerradas"] == 0 and not r["_cerrados"],
        "simular cuenta pero NO cierra")
afirmar(r["nuevas_elegibles"] == 3 and r["backlog_elegible"] == 147
        and r["backfill_que_cerraria"] == 10,
        "e informa las dos cohortes por separado, con lo que haria el backfill")
afirmar("57300000000" not in str(r) and "CLIENTE DE PRUEBA" not in str(r),
        "sin el telefono del cliente ni su nombre en el informe")

# ── que le pide a la base ────────────────────────────────────────────────────
print("\n--- lo que le pide a la base ---")

espia = Falsa(1, 1)
correr(cfg(backfill=True, lote=7), espia=espia, simular=True)
cohortes = [p[0] for p in espia.pedidos]
afirmar("normal" in cohortes and "backlog" in cohortes,
        "pide las dos cohortes por separado, no una lista que filtra despues")
afirmar(any(p[0] == "backlog" and p[1] == 7 for p in espia.pedidos),
        "y el lote viaja a la consulta -- no se recorta en memoria despues de "
        "traer 147 filas")
afirmar(all(p[2] == CORTE for p in espia.pedidos),
        "las dos reciben el MISMO corte: una frontera, no dos")

# ── la consulta declara cada guarda ──────────────────────────────────────────
print("\n--- la consulta de elegibilidad ---")

fuente = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
i = fuente.index("def conversaciones_ia_inactivas")
j = fuente.index("def conversaciones_sin_respuesta", i)
consulta = fuente[i:j]

for fragmento, que in [
    ("not coalesce(c.escalada_a_humano, false)", "no cierra una escalada"),
    ("not coalesce(c.necesita_atencion_humana, false)", "ni una marcada para revision"),
    ("coalesce(c.tomada_por, '') = ''", "ni una que alguien tomo"),
    ("not coalesce(c.atendida_manual, false)", "ni una ya atendida"),
    ("coalesce(c.control, 'ia') = 'ia'", "solo si el asistente tiene el control"),
    ("c.pendiente_interno_desde is null", "ni con un pendiente interno abierto"),
    ("not coalesce(c.conservar, false)", "ni una marcada para conservar"),
    ("acciones_propuestas", "ni con una accion propuesta sin resolver"),
    ("sincronizaciones_externas", "ni con una sincronizacion sin confirmar"),
    ("c.ticket_operativo is null", "ni una con ticket del ISP: seria un POST externo"),
    ("c.caso_id is null",
     "ni una con caso del CRM -- sin llamadas externas el barrido es idempotente, "
     "que es lo que le falta a 'cerrar_vencidas' y por eso aquel no esta en el reloj"),
    ("order by m.creado_en desc limit 1) = 'assistant'",
     "EL ULTIMO MENSAJE TIENE QUE SER DEL ASISTENTE -- si hablo el cliente hay "
     "una pregunta sin contestar"),
]:
    afirmar(fragmento in consulta, que)

afirmar("if corte is None:" in consulta and "return []" in consulta,
        "y sin corte devuelve vacio antes de tocar la base")

print("\n" + "=" * 62)
if fallos:
    print(f" {len(fallos)} falla(s).")
    raise SystemExit(1)
print(" Todo en orden.")
