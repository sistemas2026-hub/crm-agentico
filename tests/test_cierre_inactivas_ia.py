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

    def __call__(self, tenant, horas, *, corte=None, cohorte="normal", limite=None,
                 rol_de_entrada=None):
        self.pedidos.append((cohorte, limite, corte))
        # Guarda anti-limbo (26/09/2026): que rol le pidieron exceptuar. Se
        # anota aparte para afirmar el EFECTO y no solo la firma.
        self.roles_exceptuados = getattr(self, "roles_exceptuados", []) + [rol_de_entrada]
        if corte is None:
            return []
        n = self.nuevas if cohorte == "normal" else self.backlog
        filas = [conv(i) for i in range(n)]
        return filas[:limite] if (limite and cohorte == "backlog") else filas


_lista = persistencia.conversaciones_ia_inactivas
_cerrar = operativo.cerrar_todo


def correr(config, nuevas=0, backlog=0, simular=False, espia=None,
           modo_backlog=False, lote=None):
    cerrados = []
    persistencia.conversaciones_ia_inactivas = espia or Falsa(nuevas, backlog)
    operativo.cerrar_todo = lambda *a, **k: (
        cerrados.append(a[2]["id"]) or
        {"conversacion": True, "ticket": False, "caso": False})
    try:
        r = operativo.cerrar_inactivas_de_ia(
            config, "t", simular=simular, backlog=modo_backlog, lote=lote)
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
print("\n--- el reloj NUNCA consume backlog ---")

r = correr(cfg(), nuevas=3, backlog=147)
afirmar(r["cerradas"] == 3,
        "cierra el flujo normal (3) y no toca el backlog")
afirmar(r["backlog_elegible"] == 147,
        "pero informa cuantas hay, para saber cuanto falta")

r = correr(cfg(backfill=True, lote=10), nuevas=3, backlog=147)
afirmar(r["cerradas"] == 3,
        "AUNQUE el backfill este autorizado, la pasada del reloj cierra solo "
        "las 3 nuevas: no consume lote. Con el reloj cada 60 min, 10 por ciclo "
        "serian 240 al dia y el backlog se iria en menos de un dia")
afirmar(r["modo"] == "normal",
        "y la pasada se declara como normal")

r = correr(cfg(backfill=True, lote=10), nuevas=0, backlog=147)
afirmar(r["cerradas"] == 0,
        "sin nuevas, el reloj no cierra nada aunque haya 147 esperando")

print("\n--- el comando explicito ---")

r = correr(cfg(backfill=False), nuevas=3, backlog=147, modo_backlog=True)
afirmar(r["cerradas"] == 0 and "apagado" in r.get("motivo", ""),
        "con el backfill apagado, el comando tampoco toca el backlog: uno "
        "autoriza y el otro ejecuta, y hacen falta los dos")

r = correr(cfg(backfill=True, lote=10), nuevas=3, backlog=147, modo_backlog=True)
afirmar(r["cerradas"] == 10,
        "con lote 10 cierra 10, no 147")
afirmar(r["modo"] == "backlog",
        "y se declara como corrida de backlog")

r = correr(cfg(backfill=True, lote=10), nuevas=50, backlog=147, modo_backlog=True)
afirmar(r["cerradas"] == 10,
        "el comando NO toca las nuevas: 10, no 60")

# 'backfill_lote' es un TECHO DURO: el --limit puede bajarlo, nunca subirlo.
# Un limite que el comando puede pisar no es un limite -- un '--limit 500'
# tecleado de apuro se llevaria el backlog entero.
r = correr(cfg(backfill=True, lote=10), nuevas=0, backlog=147,
           modo_backlog=True, lote=3)
afirmar(r["cerradas"] == 3,
        "--limit 3 con config 10 toma 3: el comando puede BAJAR el lote")

r = correr(cfg(backfill=True, lote=10), nuevas=0, backlog=147,
           modo_backlog=True, lote=50)
afirmar(r["cerradas"] == 10,
        "--limit 50 con config 10 toma 10: el comando NO puede subirlo")

r = correr(cfg(backfill=True, lote=10), nuevas=0, backlog=147,
           modo_backlog=True, lote=None)
afirmar(r["cerradas"] == 10,
        "sin --limit toma el lote de la config")


class Drenando:
    """Persistencia que va sacando lo ya cerrado, como hace la de verdad.

    La consulta real filtra por "estado <> 'cerrada'", asi que una cerrada no
    vuelve a salir. Sin esto, la prueba de "la segunda tanda procesa las
    siguientes" pasaria devolviendo siempre las mismas diez.
    """

    def __init__(self, total):
        self.quedan = list(range(total))

    def __call__(self, tenant, horas, *, corte=None, cohorte="normal", limite=None,
                 rol_de_entrada=None):
        if cohorte == "normal":
            return []
        filas = [conv(i) for i in self.quedan]
        return filas[:limite] if limite else filas

    def cerrar(self, ids):
        vistos = {int(i[:8]) for i in ids}
        self.quedan = [q for q in self.quedan if q not in vistos]


d = Drenando(25)
tandas = []
for _ in range(3):
    r = correr(cfg(backfill=True, lote=10), espia=d, modo_backlog=True)
    d.cerrar(r["_cerrados"])
    tandas.append(r["cerradas"])
afirmar(tandas == [10, 10, 5] and not d.quedan,
        "tres tandas de 10 drenan las 25, y cada una procesa las SIGUIENTES")


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
    ("c.rol_efectivo is distinct from %s::text",
     "y con la banda 'sin_gestion' encendida NO cierra lo que nunca salio del rol "
     "de entrada con un pedido real: cerrarlo por plazo afirmaria que el cliente "
     "no respondio sobre una conversacion que nadie atendio (guarda anti-limbo)"),
]:
    afirmar(fragmento in consulta, que)

afirmar("if corte is None:" in consulta and "return []" in consulta,
        "y sin corte devuelve vacio antes de tocar la base")

# ── la excepcion del rol de entrada viaja SOLO con la banda encendida ─────────
# Afirmar el EFECTO en el llamador, no la presencia del kwarg: lo que importa
# es que operativo le pase a la consulta el rol que hay que exceptuar, y que
# no se lo pase cuando la banda de la Bandeja esta apagada -- exceptuar sin
# mostrar seria dejar esas conversaciones abiertas para siempre sin que
# nadie las vea.
print("\n--- la excepcion del rol de entrada ---")
con_banda = cfg()
con_banda.rol_de_entrada = "cliente_final"
con_banda.sin_gestion_horas = 6
espia = Falsa(nuevas=2, backlog=1)
correr(con_banda, espia=espia, modo_backlog=True)
afirmar(espia.roles_exceptuados and all(r == "cliente_final" for r in espia.roles_exceptuados),
        f"con rol_de_entrada y sin_gestion_horas, las {len(espia.roles_exceptuados)} llamadas "
        "piden exceptuar 'cliente_final' (nuevas, backlog y su total)")
sin_banda = cfg()
sin_banda.rol_de_entrada = "cliente_final"          # el rol existe, la banda no
espia = Falsa(nuevas=2, backlog=1)
correr(sin_banda, espia=espia, modo_backlog=True)
afirmar(espia.roles_exceptuados and all(r is None for r in espia.roles_exceptuados),
        "sin sin_gestion_horas no se exceptua nada: el barrido cierra como siempre")

# ── y la proteccion no se cae cuando la config no se pudo leer ────────────────
# El reloj lee con fuente.cargar, que ante una base que no contesta sirve el
# YAML de la imagen -- y el YAML no declara 'sin_gestion_horas'. Con la logica
# anterior eso apagaba la excepcion y el barrido cerraba, con
# 'sin_respuesta_cliente', las filas que la banda protegia. Lo que se afirma
# es el efecto: con la config marcada como degradada se exceptua igual, aunque
# el umbral llegue vacio. Un cierre es irreversible; dejarla abierta se ve en
# la Bandeja y se deshace.
degradada = cfg()
degradada.rol_de_entrada = "cliente_final"
degradada._origen = "yaml"                  # lo que hace fuente.cargar al caer
espia = Falsa(nuevas=2, backlog=1)
correr(degradada, espia=espia, modo_backlog=True)
afirmar(espia.roles_exceptuados and all(r == "cliente_final" for r in espia.roles_exceptuados),
        "con la config caida al YAML se exceptua igual, aunque el umbral llegue vacio")

# Y el contrario, para que la guarda no sea "exceptuar siempre": una config
# leida de la base y con la banda apagada sigue barriendo todo.
de_la_base = cfg()
de_la_base.rol_de_entrada = "cliente_final"
de_la_base._origen = "base"
espia = Falsa(nuevas=2, backlog=1)
correr(de_la_base, espia=espia, modo_backlog=True)
afirmar(espia.roles_exceptuados and all(r is None for r in espia.roles_exceptuados),
        "y con la config leida de la base y la banda apagada no se exceptua nada")

print("\n" + "=" * 62)
if fallos:
    print(f" {len(fallos)} falla(s).")
    raise SystemExit(1)
print(" Todo en orden.")
