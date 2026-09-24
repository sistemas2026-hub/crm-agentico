# -*- coding: utf-8 -*-
"""
================================================================================
 CENTRO DE MANDO  --  el estado que se muestra es el que se midio
================================================================================

    py -3.13 tests/test_centro_mando.py          (sin base, sin red)

Por que existe
--------------
/centro-mando pinta una sala donde el color de cada agente dice que esta
haciendo. Ese color no sale de la base: se DERIVA en la ruta a partir de lo
que la persistencia conto. Una derivacion mal ordenada no falla, no rompe
nada y no se ve al abrir la pantalla -- simplemente muestra tranquilo a un
agente que esta con errores, que es la unica cosa que esa pantalla no puede
hacer.

Lo que se afirma es el EFECTO (que estado sale para tal conteo), nunca que la
funcion de derivacion exista. Un test que solo comprueba que hay una funcion
sobrevive intacto a que alguien invierta el orden de sus condiciones.

  1. contrato HTTP: sin tenant 400, tenant inexistente 404
  2. la derivacion: fallos -> error; llamadas -> procesando; conversaciones
     sin actividad -> atendiendo; nada -> disponible
  3. 'esperando humano' NO es un estado -- viaja como cifra aparte. Se probo
     como estado y tapaba lo demas (ver el docstring de la ruta); si alguien
     lo reintroduce, este test lo caza
  4. el ticker no lleva contenido de conversaciones: las claves de cada
     evento son un conjunto cerrado
================================================================================
"""

from __future__ import annotations

import contextlib
import io
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                    # noqa: E402
from nucleo.persistencia import db                                # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, detalle=""):
    print(f"  [{'OK' if condicion else 'FALLA'}] {que}")
    if not condicion:
        if detalle:
            print(f"         {detalle}")
        fallos.append(que)


@contextlib.contextmanager
def parches(*trios):
    viejos = [(o, n, getattr(o, n)) for o, n, _ in trios]
    for o, n, v in trios:
        setattr(o, n, v)
    try:
        yield
    finally:
        for o, n, v in reversed(viejos):
            setattr(o, n, v)


def rol(nombre):
    return types.SimpleNamespace(descripcion=f"  {nombre}  ", area="Area",
                                 cargo="Cargo", orientado_a="cliente_final")


AGENTES = ["ocupado", "con_error", "en_cola", "libre", "escalado",
           "aprobando", "apagado", "espera_cliente"]
CONFIG = types.SimpleNamespace(roles={n: rol(n) for n in AGENTES})

PANORAMA = {
    "ventana_min": 10,
    "carga": {
        # tiene conversaciones Y esta llamando herramientas
        "ocupado": {"conversaciones": 3, "esperando_humano": 0, "recibidas_hoy": 4,
                    "ultima_actividad": None},
        "con_error": {"conversaciones": 1, "esperando_humano": 0, "recibidas_hoy": 1,
                      "ultima_actividad": None},
        # conversaciones abiertas, pero nada en la ventana
        "en_cola": {"conversaciones": 2, "esperando_humano": 0, "recibidas_hoy": 2,
                    "ultima_actividad": None},
        # el caso que motivo la regla: escaladas esperando persona Y trabajando
        "escalado": {"conversaciones": 3, "esperando_humano": 2, "recibidas_hoy": 5,
                     "ultima_actividad": None},
        # ejecuto algo cuyo efecto nadie comprobo todavia
        "aprobando": {"conversaciones": 2, "esperando_humano": 0, "recibidas_hoy": 2,
                      "ultima_actividad": None},
        # contesto y la pelota esta del lado del cliente
        "espera_cliente": {"conversaciones": 4, "esperando_humano": 0,
                           "esperando_cliente": 4, "recibidas_hoy": 4,
                           "ultima_actividad": None},
    },
    "actividad": {
        "ocupado": {"llamadas": 5, "fallos": 0, "duracion_media_ms": 300,
                    "ultima_llamada": None, "ultima_herramienta": "consultar_cliente"},
        "con_error": {"llamadas": 2, "fallos": 1, "duracion_media_ms": 900,
                      "ultima_llamada": None, "ultima_herramienta": "consultar_olt"},
        "escalado": {"llamadas": 4, "fallos": 0, "duracion_media_ms": 250,
                     "ultima_llamada": None, "ultima_herramienta": "buscar_cliente"},
        "aprobando": {"llamadas": 2, "fallos": 0, "duracion_media_ms": 400,
                      "ultima_llamada": None, "ultima_herramienta": "reiniciar_ont"},
    },
    # 'aprobando' tiene una verificacion sin resolver; los demas, ninguna
    "aprobaciones": {"aprobando": 1},
    "totales": {"conversaciones_activas": 9, "esperando_humano": 2, "atendidas_hoy": 12,
                "herramientas_hoy": 40, "duracion_media_ms": 320, "fallos_hoy": 1},
    "servicios": [],
    "eventos_herramienta": [],
    "eventos_escalada": [],
}

cliente = api.app.test_client()


def pedir(url, panorama=PANORAMA, config=CONFIG):
    def _config(_t):
        if config is None:
            raise FileNotFoundError
        return config
    buf = io.StringIO()
    with parches((api, "_config_de", _config),
                 (db, "panorama_centro_mando", lambda t, v: panorama)), \
            contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        r = cliente.get(url)
    return r


print("\n1. contrato HTTP")
r = pedir("/centro-mando")
revisar(r.status_code == 400, "sin 'tenant' responde 400", f"dio {r.status_code}")

r = pedir("/centro-mando?tenant=no-existe", config=None)
revisar(r.status_code == 404, "tenant inexistente responde 404", f"dio {r.status_code}")


print("\n2. la derivacion del estado")
r = pedir("/centro-mando?tenant=x")
revisar(r.status_code == 200, "responde 200 con datos", f"dio {r.status_code}")
por_nombre = {a["nombre"]: a for a in (r.get_json() or {}).get("agentes", [])}

esperado = {
    "con_error": "error",             # un fallo manda sobre todo lo demas
    "aprobando": "waiting_approval",  # una accion sin comprobar gana al trabajo
    "ocupado": "working",             # llamo herramientas dentro de la ventana
    "en_cola": "working",             # tiene conversaciones y le toca a el
    "espera_cliente": "waiting_user",  # contesto y espera al cliente
    "libre": "idle",                  # ni conversaciones ni llamadas
}
for nombre, estado in esperado.items():
    real = por_nombre.get(nombre, {}).get("estado")
    revisar(real == estado, f"'{nombre}' queda en '{estado}'", f"quedo en '{real}'")


print("\n3. 'esperando humano' es cifra, no estado")
escalado = por_nombre.get("escalado", {})
revisar(escalado.get("estado") == "working",
        "un agente con escaladas y trabajo sale 'working', no detenido",
        f"quedo en '{escalado.get('estado')}'")
revisar(escalado.get("esperando_humano") == 2,
        "la cifra de escaladas viaja igual", f"viajo {escalado.get('esperando_humano')}")
estados = {a["estado"] for a in por_nombre.values()}
revisar("esperando" not in estados,
        "'esperando' a secas no es un estado", f"estados: {sorted(estados)}")
# Los dos que la interfaz sabe pintar pero el motor no puede medir todavia.
# Si alguien los emite sin registrar la llamada al invocarla, esto lo caza.
revisar("waiting_tool" not in estados,
        "no se emite 'waiting_tool': tool_calls se escribe al terminar")
revisar("completed" not in estados,
        "no se emite 'completed': es estado de una tarea, no de un agente")
# 'apagado' no tiene ninguna fila en la base. Eso NO es estar caido: un agente
# que hoy no atendio a nadie se ve igual. Si alguien lo pinta como 'offline',
# la pantalla avisa de una averia que no existe.
revisar(por_nombre.get("apagado", {}).get("estado") == "idle",
        "un agente sin filas queda 'idle', no 'offline'",
        f"quedo en '{por_nombre.get('apagado', {}).get('estado')}'")
revisar("offline" not in estados,
        "no se emite 'offline': nada dice que un agente este apagado")


print("\n5. la frase de tarea se compone de lo medido, no del contenido")
frases = {n: a.get("haciendo") for n, a in por_nombre.items()}
revisar(all(frases.values()), "todos los agentes traen frase", f"{frases}")
revisar("consultar_olt" in (frases.get("con_error") or ""),
        "el agente con error nombra la herramienta que fallo", frases.get("con_error"))
revisar("consultar_cliente" in (frases.get("ocupado") or ""),
        "el que procesa nombra la herramienta en curso", frases.get("ocupado"))
revisar("Sin conversaciones" in (frases.get("libre") or ""),
        "el disponible lo dice sin inventar actividad", frases.get("libre"))
# la frase se arma con conteos y nombres de herramienta; si alguien la compone
# alguna vez con el ultimo mensaje del cliente, esto lo caza
revisar(all("@" not in f and "+57" not in f for f in frases.values()),
        "ninguna frase trae algo con forma de dato de cliente")

print("\n6. la franja de arriba no puede contradecir a las tarjetas")
totales = (r.get_json() or {}).get("totales", {})
con_trabajo = [n for n, a in por_nombre.items()
               if a["estado"] not in ("idle", "offline", "completed")]
revisar(totales.get("agentes_activos") == len(con_trabajo),
        "'agentes con trabajo' cuenta los mismos que muestran las tarjetas",
        f"la franja dice {totales.get('agentes_activos')} y hay {len(con_trabajo)}: {sorted(con_trabajo)}")
# Nace de un error real: al renombrar los estados, este conteo se quedo
# buscando 'procesando' y 'atendiendo'. Nadie lo vio hasta abrir la pantalla
# en produccion y leer '0 agentes con trabajo' sobre tres tarjetas activas.
revisar(totales.get("agentes_activos") > 0,
        "con agentes trabajando, el contador no es cero")

print("\n4. el ticker no lleva contenido de conversaciones")
panorama_con_eventos = dict(PANORAMA)
panorama_con_eventos["eventos_herramienta"] = [{
    "creado_en": types.SimpleNamespace(isoformat=lambda: "2026-09-23T10:00:00+00:00"),
    "agente": "ocupado", "herramienta": "consultar_cliente", "exito": True,
    "duracion_ms": 120, "es_escritura": False,
}]
panorama_con_eventos["eventos_escalada"] = [{
    "creado_en": types.SimpleNamespace(isoformat=lambda: "2026-09-23T09:59:00+00:00"),
    "agente": "escalado", "motivo_escalamiento": "pide_humano",
}]
r = pedir("/centro-mando?tenant=x", panorama=panorama_con_eventos)
eventos = (r.get_json() or {}).get("eventos", [])
revisar(len(eventos) == 2, "los dos origenes salen en un solo ticker", f"salieron {len(eventos)}")

permitidas = {"en", "agente", "tipo", "herramienta", "duracion_ms", "motivo"}
extras = {k for e in eventos for k in e} - permitidas
revisar(not extras, "ningun evento trae claves fuera del conjunto permitido",
        f"sobran: {sorted(extras)}")

cuerpo = r.get_data(as_text=True)
for prohibido in ("contenido", "usuario_externo", "telefono", "parametros"):
    revisar(prohibido not in cuerpo, f"la respuesta no menciona '{prohibido}'")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("[OK] El centro de mando muestra el estado que midio.")
