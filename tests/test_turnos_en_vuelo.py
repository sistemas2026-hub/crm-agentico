# -*- coding: utf-8 -*-
"""
Un despliegue no se come el mensaje que el motor estaba atendiendo.

    py -3.13 tests/test_turnos_en_vuelo.py

POR QUE EXISTE
--------------
El webhook de WhatsApp registra el wamid como visto, le contesta 200 a Meta y
recien despues atiende el mensaje, en un hilo aparte. Meta no reintenta un
mensaje al que ya se le contesto 200, y el texto del cliente solo vive en la
memoria de ese hilo hasta que el turno lo guarda.

Medido el 31/10/2026 con el mismo gunicorn de produccion (26.0.0, --workers 1
--threads 8 --graceful-timeout 30): se lanza un hilo daemon de 8 s, llega el
SIGTERM a los 5 s, y el worker sale EN EL ACTO -- 'TURNO TERMINA' no se
imprime nunca. Con el autodeploy, cada push con un turno en vuelo le dejaba a
un cliente sin respuesta, sin error y sin una linea en el log.

Lo que se prueba:

  1. 'esperar' espera a los turnos que terminan dentro del tope, y tambien a
     lo que ellos lanzan al terminar (la traza): una sola foto la dejaba afuera.
  2. No espera de mas: un turno que no termina se corta al tope, y queda
     NOMBRADO en el log -- pasando por el formateo REAL del registro, que es
     el que tapaba el nombre cuando traia siete digitos.
  3. Un turno que falla sale del registro igual.
  4. Un solo reloj: la espera descuenta lo que gunicorn ya gasto desde el
     SIGTERM esperando peticiones HTTP.
  5. El cableado: webhook, devolucion, traza y autonomia lanzan por en_vuelo;
     la autonomia no EMPIEZA un efecto con el proceso saliendo; gunicorn anota
     el SIGTERM y espera al salir el worker.
  6. Contra gunicorn REAL (solo donde gunicorn corre -- en el contenedor del
     motor; en Windows se reporta OMITIDA):
       a. el turno en vuelo termina antes de que el proceso salga;
       b. con una peticion HTTP lenta en curso y un turno mas largo que lo que
          queda, el turno se corta PERO el resumen llega al log antes del
          SIGKILL, y el proceso sale antes del graceful_timeout.

    MSYS_NO_PATHCONV=1 docker run --rm -v <repo>:/repo:ro -w /repo \
      -e PYTHONPATH=/repo dexter-motor:latest python tests/test_turnos_en_vuelo.py
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import en_vuelo  # noqa: E402
from nucleo.observabilidad import registro  # noqa: E402

fallos: list[str] = []


def revisar(cond: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if cond else "  [FALLA] ") + que)
    if not cond:
        fallos.append(que)
        if detalle:
            print(f"          {detalle}")


#  El log pasa por el formateo REAL: lo que se afirma es lo que se veria en
#  el contenedor, redaccion incluida.
lineas: list[str] = []
_registrar_real = en_vuelo.registrar
en_vuelo.registrar = lambda c, e, **k: lineas.append(registro.formatear(c, e, **k))


print("\n--- 1. espera a los que terminan, y a lo que lanzan al terminar ---")
hechos: list[str] = []
en_vuelo.lanzar(lambda: (time.sleep(0.4), hechos.append("corto")), nombre="turno-corto")
r = en_vuelo.esperar(5)
revisar(hechos == ["corto"], "el turno corto termino antes de que 'esperar' volviera",
        f"hechos: {hechos}")
revisar(r == {"habia": 1, "terminaron": 1, "cortados": []},
        "y el resumen lo cuenta", f"resumen: {r}")
revisar(en_vuelo.esperar(1) == {"habia": 0, "terminaron": 0, "cortados": []},
        "terminado, sale del registro")

traza_escrita: list[str] = []


def _traza():
    time.sleep(0.5)
    traza_escrita.append("traza")


def _turno_que_lanza_su_traza():
    time.sleep(0.2)
    en_vuelo.lanzar(_traza, nombre="traza")


en_vuelo.lanzar(_turno_que_lanza_su_traza, nombre="turno-whatsapp")
r = en_vuelo.esperar(5)
revisar(traza_escrita == ["traza"] and r["habia"] == 2 and not r["cortados"],
        "la traza que el turno lanza al terminar tambien se espera",
        f"traza: {traza_escrita}, resumen: {r}")


print("\n--- 2. no espera de mas, y nombra al que corta ---")
lineas.clear()
huellas = [registro.ref_proveedor(f"wamid.HBgMNTczMDAxMjM0NTY3{i}") for i in range(40)]
sueltas = threading.Event()
for h in huellas:
    en_vuelo.lanzar(sueltas.wait, 30, nombre="turno-whatsapp", ref=h)
antes = time.monotonic()
r = en_vuelo.esperar(0.5)
tardo = time.monotonic() - antes
revisar(0.4 <= tardo < 2, "respeta el tope", f"tardo {tardo:.2f} s")
revisar(sorted(r["cortados"]) == sorted(huellas), "los que no terminaron quedan nombrados",
        f"cortados: {len(r['cortados'])} de {len(huellas)}")
cortes = [l for l in lineas if "cortados" in l]
revisar(cortes and all(str(h) in cortes[0] for h in huellas)
        and registro.REDACTADO not in cortes[0],
        "y el log los nombra a TODOS por su huella, sin que la redaccion tape ninguno",
        cortes[0][:300] if cortes else f"lineas: {lineas}")
revisar(not any("HBgM" in l or "5730012345" in l for l in lineas),
        "el wamid y sus digitos no aparecen en el log")
revisar(any("esperando" in l for l in lineas) and lineas.index(
            next(l for l in lineas if "esperando" in l)) < lineas.index(cortes[0]),
        "dice que empieza a esperar ANTES de esperar (si gunicorn lo mata, queda esa linea)")
sueltas.set()
time.sleep(0.2)


print("\n--- 3. un turno que falla sale del registro ---")
def _revienta():
    raise RuntimeError("se cayo el modelo")


_hook = threading.excepthook
threading.excepthook = lambda args: None
try:
    en_vuelo.lanzar(_revienta, nombre="turno-que-falla")
    time.sleep(0.2)
finally:
    threading.excepthook = _hook
revisar(en_vuelo.esperar(0.1)["habia"] == 0, "el que fallo no queda como fantasma")


print("\n--- 4. un solo reloj con gunicorn ---")
from nucleo.canales import gunicorn_conf as gc  # noqa: E402

revisar(gc.tope_de_espera(0) == gc.ESPERA_TURNOS_SEGUNDOS,
        "recien llegado el SIGTERM, espera lo suyo")
revisar(gc.tope_de_espera(20) == gc.graceful_timeout - gc.MARGEN_SEGUNDOS - 20,
        "si gunicorn ya gasto 20 s en peticiones HTTP, espera solo lo que queda",
        f"tope: {gc.tope_de_espera(20)}")
revisar(gc.tope_de_espera(60) == 0, "y si no queda nada, no espera")
revisar(gc.ESPERA_TURNOS_SEGUNDOS + gc.MARGEN_SEGUNDOS <= gc.graceful_timeout,
        "la espera y el margen caben antes del SIGKILL del arbitro")
revisar(en_vuelo.apagando(), "despues de 'esperar', el proceso se sabe saliendo")


print("\n--- 5. el cableado ---")
api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
for objetivo in ("_procesar_mensaje_whatsapp", "_atender_pendiente_tras_devolver",
                 "_guardar_traza"):
    revisar(not re.search(rf"threading\.Thread\(\s*target={objetivo}", api)
            and re.search(rf"en_vuelo\.lanzar\(\s*{objetivo}", api),
            f"'{objetivo}' se lanza por en_vuelo")
revisar(re.search(r"en_vuelo\.lanzar\(\s*correr,\s*nombre=\"autonomia-ganada\"", api) is not None,
        "la autonomia ganada tambien (una ejecucion empezada termina)")
autonoma = api.split("def _lanzar_autonomas", 1)[1].split("\ndef ", 1)[0]
revisar(autonoma.find("en_vuelo.apagando()") != -1
        and autonoma.find("en_vuelo.apagando()") < autonoma.find("_ejecutar_si_es_autonoma("),
        "y no EMPIEZA un efecto con el proceso saliendo: lo mira antes de ejecutar")
revisar(not re.search(r'nombre=f"', api.split("en_vuelo.lanzar", 1)[1]) and
        all('nombre=f"' not in tramo.split(")", 1)[0]
            for tramo in api.split("en_vuelo.lanzar(")[1:]),
        "ningun nombre de hilo se arma con datos: la identidad va en 'ref'")

#  post_worker_init envuelve el SIGTERM y anota la hora; worker_exit espera
#  con el tope del reloj compartido.
class _Worker:
    def __init__(self):
        self.salidas = []

    def handle_exit(self, sig, frame):
        self.salidas.append(sig)


w = _Worker()
previo = signal.getsignal(signal.SIGTERM)
en_vuelo._apagado.clear()
en_vuelo._apagado_desde.clear()
try:
    gc.post_worker_init(w)
    w.handle_exit(signal.SIGTERM, None)
    revisar(w.salidas == [signal.SIGTERM] and en_vuelo.apagando(),
            "el SIGTERM sigue llegando a gunicorn, y queda anotado que empezo el apagado")
    #  Como si gunicorn hubiera gastado 10 s esperando peticiones HTTP.
    en_vuelo._apagado_desde[0] -= 10
    llamados: list[float] = []
    _esperar_real = en_vuelo.esperar
    en_vuelo.esperar = lambda tope: llamados.append(tope) or {}
    try:
        gc.worker_exit(None, None)
    finally:
        en_vuelo.esperar = _esperar_real
    revisar(len(llamados) == 1
            and abs(llamados[0] - (gc.graceful_timeout - gc.MARGEN_SEGUNDOS - 10)) < 0.5,
            "al salir el worker se espera, descontando lo que ya paso desde el SIGTERM",
            f"tope: {llamados}")
finally:
    signal.signal(signal.SIGTERM, previo)

compose = (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8")
motor = compose.split("\n  motor:\n", 1)[1].split("\n  motor-reloj:", 1)[0]
revisar("--config python:nucleo.canales.gunicorn_conf" in motor,
        "el compose arranca el motor con esa configuracion")
revisar(not re.search(r"--graceful-timeout", motor),
        "y no la pisa con otro graceful-timeout en la linea de comandos")
gracia = re.search(r"stop_grace_period:\s*(\d+)s", motor)
revisar(gracia and int(gracia.group(1)) > gc.graceful_timeout,
        "Docker espera mas que gunicorn antes del SIGKILL",
        f"stop_grace_period={gracia and gracia.group(1)}")


print("\n--- 6. contra gunicorn real ---")
en_vuelo.registrar = _registrar_real
try:
    import fcntl  # noqa: F401  -- gunicorn lo necesita; en Windows no existe
    import gunicorn  # noqa: F401
except ImportError:
    print("  OMITIDA: gunicorn no corre en este interprete (corre en el contenedor del "
          "motor; ver el encabezado). Ninguna comprobacion de esta parte se ejecuto.")
else:
    APP = (
        "import time\n"
        "from flask import Flask\n"
        "from nucleo.canales import en_vuelo\n"
        "app = Flask(__name__)\n"
        "def turno(segundos):\n"
        "    print('TURNO EMPIEZA', flush=True)\n"
        "    time.sleep(segundos)\n"
        "    print('TURNO TERMINA', flush=True)\n"
        "@app.post('/lanzar/<int:segundos>')\n"
        "def lanzar(segundos):\n"
        "    en_vuelo.lanzar(turno, segundos, nombre='turno-de-prueba')\n"
        "    return 'ok'\n"
        "@app.get('/lenta/<int:segundos>')\n"
        "def lenta(segundos):\n"
        "    time.sleep(segundos)\n"
        "    return 'lenta'\n")

    def _pedir(url, metodo="GET"):
        for _ in range(50):
            try:
                return urllib.request.urlopen(urllib.request.Request(url, method=metodo),
                                              timeout=60).read()
            except OSError:
                time.sleep(0.2)

    def _escenario(puerto: int, turno_s: int, lenta_s: int | None):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "app_de_prueba.py").write_text(APP, encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, "-m", "gunicorn", "app_de_prueba:app",
                 "--config", "python:nucleo.canales.gunicorn_conf",
                 "--bind", f"127.0.0.1:{puerto}", "--workers", "1", "--threads", "8"],
                cwd=d, env={**os.environ, "PYTHONPATH": f"{d}:{RAIZ}"},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                _pedir(f"http://127.0.0.1:{puerto}/lanzar/{turno_s}", "POST")
                if lenta_s:
                    threading.Thread(target=_pedir, daemon=True,
                                     args=(f"http://127.0.0.1:{puerto}/lenta/{lenta_s}",)).start()
                time.sleep(1)
                antes = time.monotonic()
                proc.send_signal(signal.SIGTERM)
                salida, _ = proc.communicate(timeout=90)
                return salida, time.monotonic() - antes
            finally:
                if proc.poll() is None:
                    proc.kill()

    salida, tardo = _escenario(5099, turno_s=6, lenta_s=None)
    revisar("TURNO EMPIEZA" in salida and "TURNO TERMINA" in salida,
            "a. el turno en vuelo TERMINA antes de que el proceso salga", salida[-800:])
    revisar(tardo < gc.graceful_timeout, f"   y el apagado no espero de mas ({tardo:.1f} s)")

    salida, tardo = _escenario(5098, turno_s=60, lenta_s=20)
    revisar("turnos cortados" in salida and "TURNO TERMINA" not in salida,
            "b. con una peticion lenta y un turno largo, el corte queda ESCRITO en el log "
            "(el resumen llega antes del SIGKILL)", salida[-1200:])
    revisar(tardo < gc.graceful_timeout,
            f"   y el proceso sale antes del graceful_timeout ({tardo:.1f} s < "
            f"{gc.graceful_timeout})")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Un despliegue espera a los turnos en vuelo, y nombra al que tuvo que cortar.")
