# -*- coding: utf-8 -*-
"""
El reloj: que arranque, que se apague, que aisle y que exista UNA sola vez.

    py -3.13 tests/test_reloj.py

POR QUE EXISTE
--------------
Este trabajo estuvo muerto un mes entero sin que nada lo dijera. El hilo se
creaba desde el bloque '__main__' de nucleo/canales/api.py, y produccion
arranca el motor con gunicorn, que IMPORTA el modulo en vez de ejecutarlo. No
hubo excepcion, ni log, ni alerta: el unico sintoma era que nada se cerraba
solo, indistinguible de "no venció ninguna todavia".

Ninguna prueba lo habria detectado, porque todas probaban las REGLAS
('cerrar_vencidas' decide bien a quien cerrar) y ninguna probaba el
CABLEADO (quien llama a 'cerrar_vencidas', y si ese alguien corre).

Asi que esto prueba el cableado. No hay red ni base: los efectos se sustituyen
por espias y lo que se mide es a quien se llamo, con que, y quien sobrevivio a
que.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import yaml  # noqa: E402

from nucleo import reloj  # noqa: E402
from nucleo.config.schema import ImportacionTickets  # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


# --- utileria ------------------------------------------------------------

class Espia:
    """Cuenta llamadas y guarda con que se hizo cada una. Nada mas."""

    def __init__(self, devuelve=None, revienta=None):
        self.llamadas: list[tuple] = []
        self._devuelve = devuelve
        self._revienta = revienta

    def __call__(self, *a, **k):
        self.llamadas.append((a, k))
        if self._revienta:
            raise self._revienta
        if isinstance(self._devuelve, list):
            return list(self._devuelve)
        return dict(self._devuelve or {})


def config_falsa(horas=0, cada_horas=0):
    return SimpleNamespace(
        escalamiento=SimpleNamespace(cerrar_sin_respuesta_horas=horas),
        # El objeto REAL del schema, no un doble: 'debe_correr' es la compuerta
        # que hay que probar, y probarla contra un namespace inventado no
        # probaria la compuerta que corre en produccion.
        importacion_tickets=ImportacionTickets(cada_horas=cada_horas))


class Escenario:
    """Cambia el mundo de 'reloj' por espias y lo deja como estaba al salir."""

    def __init__(self, tenants, configs, vencidas=None, barrido=None):
        self.tenants = tenants
        self.configs = configs          # tenant -> config, o una excepcion
        self.vencidas = vencidas or Espia({"revisadas": 0, "cerradas": 0})
        self.barrido = barrido or Espia({"creados": 0})
        self.db = Espia([])

    def _cargar(self, tenant, raiz=None):
        valor = self.configs[tenant]
        if isinstance(valor, Exception):
            raise valor
        return valor

    def __enter__(self):
        from nucleo.persistencia import db

        self._db_mod = db
        self._previo = {
            "tenants": reloj.tenants_conocidos,
            "cargar": reloj.fuente.cargar,
            "vencidas": reloj.operativo.cerrar_vencidas,
            "barrido": reloj.importacion_io.barrido,
            # El seco de vencimientos consulta la base. Sin espiarla, la
            # prueba necesitaria Postgres para responder algo que no es sobre
            # Postgres.
            "consulta": db.conversaciones_sin_respuesta,
        }
        reloj.tenants_conocidos = lambda: list(self.tenants)
        reloj.fuente.cargar = self._cargar
        reloj.operativo.cerrar_vencidas = self.vencidas
        reloj.importacion_io.barrido = self.barrido
        db.conversaciones_sin_respuesta = self.db
        reloj._ultimo_intento_importacion.clear()
        return self

    def __exit__(self, *_):
        reloj.tenants_conocidos = self._previo["tenants"]
        reloj.fuente.cargar = self._previo["cargar"]
        reloj.operativo.cerrar_vencidas = self._previo["vencidas"]
        reloj.importacion_io.barrido = self._previo["barrido"]
        self._db_mod.conversaciones_sin_respuesta = self._previo["consulta"]
        reloj._ultimo_intento_importacion.clear()
        return False


def sin_interruptor(valor=None):
    """El entorno con 'RELOJ_HABILITADO' puesto en 'valor' (None = ausente)."""
    previo = os.environ.get("RELOJ_HABILITADO")
    if valor is None:
        os.environ.pop("RELOJ_HABILITADO", None)
    else:
        os.environ["RELOJ_HABILITADO"] = valor
    return previo


# ==========================================================================
#  1. EL ENTRYPOINT REAL ARRANCA COMO PROCESO
# ==========================================================================
# Esto es lo que ninguna prueba hacia antes. Se ejecuta el modulo de verdad,
# como lo va a ejecutar el contenedor, con el mismo comando que dice el
# compose. Si un import no resuelve, aca se ve.

print("\nel entrypoint arranca de verdad")

entorno = dict(os.environ)
entorno.pop("RELOJ_HABILITADO", None)
r = subprocess.run([sys.executable, "-m", "nucleo.reloj", "--once"],
                   capture_output=True, text=True, timeout=180,
                   cwd=str(RAIZ), env=entorno)
revisar(r.returncode == 0,
        "'python -m nucleo.reloj --once' termina en 0 sin el interruptor",
        (r.stderr or r.stdout)[-500:])
revisar("ImportError" not in r.stderr and "ModuleNotFoundError" not in r.stderr,
        "sin ImportError ni ModuleNotFoundError al cargarlo",
        r.stderr[-500:])
revisar("RELOJ_HABILITADO" in r.stdout,
        "y dice por que no hizo nada, en vez de callarse",
        "un proceso que arranca y no hace nada sin decirlo es el bug original")
# Un proceso apagado que igual toca la base seria peor que uno encendido: haria
# trabajo invisible. Con el interruptor en 0 no hay una sola linea de tenant.
revisar("[reloj] rapilink" not in r.stdout,
        "apagado no procesa ningun tenant",
        r.stdout[-400:])

r2 = subprocess.run([sys.executable, "-m", "nucleo.reloj", "--dry-run"],
                    capture_output=True, text=True, timeout=180,
                    cwd=str(RAIZ), env=entorno)
revisar(r2.returncode == 2 and "--once" in r2.stdout,
        "'--dry-run' sin '--once' se niega, en vez de quedar en bucle en seco",
        f"codigo {r2.returncode}: {r2.stdout[-300:]}")


# ==========================================================================
#  1.b  APAGADO = VIVO E INERTE, NO UN CONTENEDOR REBOTANDO
# ==========================================================================
# El servicio corre con 'restart: unless-stopped'. Si el daemon imprimiera "no
# habilitado" y TERMINARA --aunque terminara en 0-- Docker lo reiniciaria en el
# acto, y otra vez, y otra: una ametralladora de contenedores con cara de
# servicio apagado. Asi que se levanta el daemon de verdad (sin '--once') y se
# comprueba que sigue vivo y callado.

print("\napagado: vivo e inerte, sin bucle de reinicio")

daemon = subprocess.Popen([sys.executable, "-u", "-m", "nucleo.reloj"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, cwd=str(RAIZ), env=entorno)
try:
    # Margen amplio: si fuera a terminar, terminaria en el arranque -- no hay
    # nada entre el print y el sleep. Lo que se mide es que NO termine.
    try:
        daemon.wait(timeout=12)
        vivo = False
    except subprocess.TimeoutExpired:
        vivo = True
    revisar(vivo,
            "el daemon apagado SIGUE VIVO (no termina, asi que Docker no lo reinicia)",
            f"termino con codigo {daemon.returncode}")
finally:
    daemon.terminate()
    salida_daemon = ""
    try:
        salida_daemon = daemon.communicate(timeout=15)[0] or ""
    except subprocess.TimeoutExpired:
        daemon.kill()
        salida_daemon = daemon.communicate()[0] or ""

# Y el arranque tiene que ser inequivoco leyendo solo el log.
for linea in ("motor-reloj iniciado", "RELOJ_HABILITADO=0", "scheduler inerte"):
    revisar(linea in salida_daemon,
            f"el log de arranque dice '{linea}'",
            salida_daemon[-400:])
revisar("ciclo inicio" not in salida_daemon,
        "y no arranca ningun ciclo",
        salida_daemon[-400:])


# ==========================================================================
#  2. EL INTERRUPTOR
# ==========================================================================

print("\nel interruptor de despliegue")

previo = sin_interruptor(None)
try:
    revisar(reloj.habilitado() is False, "sin la variable, apagado")
    sin_interruptor("0")
    revisar(reloj.habilitado() is False, "'0', apagado")
    sin_interruptor("")
    revisar(reloj.habilitado() is False, "cadena vacia, apagado")
    sin_interruptor("true")
    revisar(reloj.habilitado() is False,
            "'true' NO enciende: se exige '1' exacto",
            "aceptar varias formas de decir si multiplica las de decir no")
    sin_interruptor(" 1 ")
    revisar(reloj.habilitado() is True,
            "'1' con espacios enciende (Dokploy los deja pegados a veces)")

    # Apagado = CERO efectos. No "menos" efectos.
    sin_interruptor("0")
    with Escenario(["a"], {"a": config_falsa(horas=48, cada_horas=1)}) as e:
        codigo = reloj.main(["--once"])
    revisar(codigo == 0 and not e.vencidas.llamadas and not e.barrido.llamadas,
            "apagado con TODO configurado: cero cierres, cero importaciones",
            f"vencidas={len(e.vencidas.llamadas)} barrido={len(e.barrido.llamadas)}")
finally:
    sin_interruptor(previo)


# ==========================================================================
#  3. --once HACE UNA PASADA Y TERMINA
# ==========================================================================

print("\n--once")

previo = sin_interruptor("1")
try:
    with Escenario(["a", "b"], {"a": config_falsa(horas=48),
                                "b": config_falsa(horas=24)}) as e:
        codigo = reloj.main(["--once"])
    revisar(codigo == 0, "termina, y en 0")
    revisar(len(e.vencidas.llamadas) == 2,
            "una pasada = una vuelta por tenant, ni mas ni menos",
            f"llamadas: {len(e.vencidas.llamadas)}")

    # ------------------------------------------------------------------
    #  4. --dry-run NO ESCRIBE
    # ------------------------------------------------------------------
    print("\n--dry-run")

    espia_barrido = Espia({"creados": 0})
    with Escenario(["a"], {"a": config_falsa(horas=48, cada_horas=1)},
                   barrido=espia_barrido) as e:
        reloj.main(["--once", "--dry-run"])
    revisar(not e.vencidas.llamadas,
            "no llama a 'cerrar_vencidas'",
            "el que cierra es ese; en seco se consulta, no se cierra")
    revisar(len(espia_barrido.llamadas) == 1
            and espia_barrido.llamadas[0][1].get("aplicar_cambios") is False,
            "llama al barrido con aplicar_cambios=False",
            f"{espia_barrido.llamadas}")

    # El dry-run de vencimientos usa la MISMA consulta que decide en serio.
    # Si algun dia alguien le escribe una regla propia, esto lo delata.
    fuente_reloj = (RAIZ / "nucleo" / "reloj.py").read_text(encoding="utf-8")
    revisar("conversaciones_sin_respuesta" in fuente_reloj,
            "y el seco de vencimientos consulta la misma fuente que el humedo",
            "dos motores de reglas terminan discrepando justo cuando importa")

    # ------------------------------------------------------------------
    #  5. cada_horas = 0 NO IMPORTA NADA
    # ------------------------------------------------------------------
    print("\nla compuerta de la importacion")

    with Escenario(["a"], {"a": config_falsa(horas=48, cada_horas=0)}) as e:
        salida = reloj.main(["--once"])
    revisar(not e.barrido.llamadas,
            "cada_horas=0: ni una llamada al proveedor",
            "es el valor por defecto: desplegar no puede empezar a importar")
    revisar(len(e.vencidas.llamadas) == 1,
            "y aun asi los vencimientos corren")

    with Escenario(["a"], {"a": config_falsa(horas=0, cada_horas=1)}) as e:
        reloj.main(["--once"])
    revisar(not e.vencidas.llamadas,
            "sin plazo declarado: 'cerrar_vencidas' ni se llama")
    revisar(len(e.barrido.llamadas) == 1,
            "y aun asi la importacion corre")

    # ------------------------------------------------------------------
    #  6. AISLAMIENTO DE FALLOS
    # ------------------------------------------------------------------
    print("\naislamiento: un fallo no puede llevarse nada por delante")

    # (a) config rota de un tenant vs los demas
    with Escenario(["a", "b"],
                   {"a": RuntimeError("config podrida"),
                    "b": config_falsa(horas=48, cada_horas=1)}) as e:
        reloj.main(["--once"])
    revisar(len(e.vencidas.llamadas) == 1 and len(e.barrido.llamadas) == 1,
            "la config rota de 'a' no deja sin atender a 'b'",
            f"vencidas={len(e.vencidas.llamadas)} barrido={len(e.barrido.llamadas)}")

    # (b) vencimientos rotos vs importacion del MISMO tenant
    with Escenario(["a"], {"a": config_falsa(horas=48, cada_horas=1)},
                   vencidas=Espia(revienta=RuntimeError("CRM caido"))) as e:
        reloj.main(["--once"])
    revisar(len(e.barrido.llamadas) == 1,
            "vencimientos rotos NO bloquean la importacion del mismo tenant")

    # (c) importacion rota vs vencimientos del MISMO tenant
    with Escenario(["a"], {"a": config_falsa(horas=48, cada_horas=1)},
                   barrido=Espia(revienta=RuntimeError("proveedor caido"))) as e:
        reloj.main(["--once"])
    revisar(len(e.vencidas.llamadas) == 1,
            "importacion rota NO impide cerrar las vencidas del mismo tenant")

    # (d) nada de eso mata la pasada
    with Escenario(["a", "b"],
                   {"a": config_falsa(horas=48, cada_horas=1),
                    "b": config_falsa(horas=48, cada_horas=1)},
                   vencidas=Espia(revienta=RuntimeError("todo mal")),
                   barrido=Espia(revienta=RuntimeError("todo peor"))) as e:
        codigo = reloj.main(["--once"])
        resultados = None
    revisar(codigo == 0,
            "con los dos trabajos rotos en los dos tenants, la pasada termina",
            "una excepcion que sube deja de hacer TODO para siempre")

    # (e) SystemExit tampoco. No es una 'Exception', y hay codigo de la casa
    # que lo lanza: conexion.py::dsn lo hace cuando faltan los datos de la
    # base. En un CLI esta bien; aca mataria el reloj, y un solo tenant mal
    # configurado se llevaria puestos a todos los demas.
    with Escenario(["a", "b"],
                   {"a": config_falsa(horas=48, cada_horas=1),
                    "b": config_falsa(horas=48, cada_horas=1)},
                   vencidas=Espia(revienta=SystemExit("sin datos de conexion"))) as e:
        codigo = reloj.main(["--once"])
    revisar(codigo == 0 and len(e.barrido.llamadas) == 2,
            "un SystemExit de un trabajo no mata la pasada ni salta al otro tenant",
            f"codigo={codigo} barridos={len(e.barrido.llamadas)}")

    # (f) el fallo queda registrado, no se traga en silencio
    with Escenario(["a"], {"a": config_falsa(horas=48, cada_horas=1)},
                   barrido=Espia(revienta=RuntimeError("proveedor caido"))):
        resultados = reloj.una_pasada()
    revisar("error" in resultados[0]["importacion"]
            and "proveedor caido" in resultados[0]["importacion"]["error"],
            "y el fallo sale en el resultado con su causa adentro",
            f"{resultados}")

    # ------------------------------------------------------------------
    #  7. EL SELLO SE PONE ANTES DE TRABAJAR
    # ------------------------------------------------------------------
    # Con el sello solo en exito, una credencial vencida haria que el reloj
    # golpeara al proveedor en cada vuelta en vez de esperar su hora.
    print("\nel regulador de frecuencia")

    with Escenario(["a"], {"a": config_falsa(horas=0, cada_horas=1)},
                   barrido=Espia(revienta=RuntimeError("credencial vencida"))):
        reloj.main(["--once"])
        sellado = "a" in reloj._ultimo_intento_importacion
        reloj.main(["--once"])
        segunda = len(reloj.importacion_io.barrido.llamadas)
    revisar(sellado, "un barrido que falla igual deja sello")
    revisar(segunda == 1,
            "asi que la pasada siguiente NO reintenta hasta que le toque",
            f"llamadas al proveedor: {segunda}")
finally:
    sin_interruptor(previo)



# ==========================================================================
#  7.b  EL CICLO REAL RECONCILIA  --  cableado, no funciones sueltas
# ==========================================================================
# La reconciliacion estuvo construida, probada y NO conectada a nada: el
# 'barrido' hacia descubrimiento e importacion, y 'aplicar_reconciliacion'
# solo se alcanzaba desde el CLI. Se descubrio auditando el primer ciclo
# automatico real -- 3 casos creados y cero reconciliados.
#
# Es el mismo bug que el reloj muerto, en chico: codigo correcto que nadie
# llama. Por eso lo que se prueba aca NO es que 'reconciliar' decida bien
# --eso ya tiene sus pruebas-- sino que el ciclo la LLAME. Se corre el
# 'barrido' de verdad, entrando por 'reloj.main', y se sustituye solo lo que
# sale del proceso.

print("\nel ciclo reconcilia, y lo hace el barrido de verdad")

from nucleo.seguimiento import importacion_io as io_real  # noqa: E402

# La funcion de verdad, capturada ANTES de que ningun escenario toque el
# modulo. 'Escenario' reemplaza 'importacion_io.barrido' por un espia, asi
# que leer el atributo despues devuelve el espia, no el barrido.
BARRIDO_REAL = io_real.barrido


class CicloReal:
    """Sustituye SOLO lo que sale del proceso. El barrido corre entero."""

    def __init__(self, *, aplicar=None, reconciliar=None, casos=None,
                 aplicar_recon=None, descubrir=None):
        self.orden: list[str] = []
        self.aplicar = aplicar or (lambda *a, **k: {
            "creados": 2, "ya_estaban": 1, "fallidos": 0, "ids": ["1", "2"]})
        self.aplicar_recon = aplicar_recon or (lambda *a, **k: {
            "actualizados": 3, "sin_cambios": 4, "fallidos": 0})
        self.casos = casos if casos is not None else [
            {"id": "c1", "external_ticket_id": "1", "status": "New"}]
        self._reconciliar = reconciliar
        self._descubrir = descubrir

    def _envuelto(self, nombre, fn):
        def envoltura(*a, **k):
            self.orden.append(nombre)
            return fn(*a, **k)
        return envoltura

    def __enter__(self):
        from nucleo.persistencia import db
        from nucleo.seguimiento import importacion as imp_real

        self._db = db
        self._previo = {
            "areas": db.areas_de_colaboradores,
            "listar": io_real.listar_tickets,
            "conocidos": io_real.tickets_conocidos,
            "servicios": io_real.resolver_servicios,
            "casos": io_real.casos_de_este_proveedor,
            "leer": io_real.leer_ticket,
            "aplicar": io_real.aplicar,
            "aplicar_recon": io_real.aplicar_reconciliacion,
            "descubrir": imp_real.descubrir,
            "reconciliar": imp_real.reconciliar,
        }
        self._imp = imp_real
        db.areas_de_colaboradores = lambda t: {}
        io_real.listar_tickets = lambda *a, **k: [{"id_ticket": "1"}]
        io_real.tickets_conocidos = lambda *a, **k: (set(), {"1"})
        io_real.resolver_servicios = lambda *a, **k: (lambda ids: {})
        io_real.casos_de_este_proveedor = lambda *a, **k: list(self.casos)
        io_real.leer_ticket = lambda *a, **k: {"id_ticket": "1"}
        io_real.aplicar = self._envuelto("importacion", self.aplicar)
        io_real.aplicar_reconciliacion = self._envuelto(
            "reconciliacion", self.aplicar_recon)
        imp_real.descubrir = self._descubrir or (lambda *a, **k: [
            SimpleNamespace(resultado=imp_real.CANDIDATO)])
        imp_real.reconciliar = self._reconciliar or (lambda *a, **k: [
            SimpleNamespace(error="", hay_diferencia=True),
            SimpleNamespace(error="lectura rota", hay_diferencia=False)])
        return self

    def __exit__(self, *_):
        self._db.areas_de_colaboradores = self._previo["areas"]
        io_real.listar_tickets = self._previo["listar"]
        io_real.tickets_conocidos = self._previo["conocidos"]
        io_real.resolver_servicios = self._previo["servicios"]
        io_real.casos_de_este_proveedor = self._previo["casos"]
        io_real.leer_ticket = self._previo["leer"]
        io_real.aplicar = self._previo["aplicar"]
        io_real.aplicar_reconciliacion = self._previo["aplicar_recon"]
        self._imp.descubrir = self._previo["descubrir"]
        self._imp.reconciliar = self._previo["reconciliar"]
        return False


def config_real(horas=0, cada_horas=1):
    """Como config_falsa, pero con lo que el barrido de verdad necesita."""
    c = config_falsa(horas=horas, cada_horas=cada_horas)
    c.importacion_tickets.proveedor = "wisphub"
    c.importacion_tickets.cuenta_api = "cuenta - api"
    c.herramientas = []
    c.variables_tenant = {}
    return c


previo = sin_interruptor("1")
try:
    # --- las dos corren, en orden, y los contadores no se mezclan ---------
    with CicloReal() as ciclo:
        with Escenario(["a"], {"a": config_real()}) as e:
            # El barrido REAL: se le devuelve el control a importacion_io.
            reloj.importacion_io.barrido = BARRIDO_REAL
            # Una sola pasada: 'main(["--once"])' antes dejaria el sello de
            # frecuencia puesto y la segunda no le tocaria.
            r = reloj.una_pasada()[0]["importacion"]

    revisar(ciclo.orden[:2] == ["importacion", "reconciliacion"],
            "el ciclo importa y DESPUES reconcilia, en esa orden",
            f"orden observado: {ciclo.orden}")
    revisar("reconciliacion" in ciclo.orden,
            "la reconciliacion se ejecuta dentro del ciclo del reloj",
            "estuvo construida y desconectada: es lo que esta prueba existe para evitar")

    revisar(r["importacion"] == {"inspeccionados": 1, "candidatos": 1,
                                 "creados": 2, "ya_estaban": 1, "fallidos": 0},
            "los contadores de importacion salen separados",
            f"{r.get('importacion')}")
    revisar(r["reconciliacion"] == {"alcanzados": 2, "con_diferencia": 1,
                                    "actualizados": 3, "sin_cambios": 4,
                                    "fallidos": 0, "errores_lectura": 1},
            "y los de reconciliacion tambien, con errores_lectura aparte",
            f"{r.get('reconciliacion')}")
    # 'fallidos' existe en los dos a proposito -- son fallos de trabajos
    # distintos. Lo que no puede existir es un contador PLANO, arriba, que los
    # sume: ese es el numero que se lee mal cuando algo anda mal.
    planos = {"creados", "fallidos", "candidatos", "actualizados",
              "inspeccionados", "alcanzados"} & set(r)
    revisar(not planos,
            "no hay contadores planos arriba que mezclen los dos trabajos",
            f"al tope del resultado aparecen: {planos}")
    revisar(isinstance(r["importacion"], dict)
            and isinstance(r["reconciliacion"], dict),
            "cada trabajo tiene su propio bloque")

    # --- un fallo de importacion NO impide reconciliar --------------------
    def importacion_rota(*a, **k):
        raise RuntimeError("el CRM rechazo el POST")

    with CicloReal(aplicar=importacion_rota) as ciclo:
        with Escenario(["a"], {"a": config_real()}):
            reloj.importacion_io.barrido = BARRIDO_REAL
            r = reloj.una_pasada()[0]["importacion"]
    revisar("reconciliacion" in ciclo.orden,
            "la importacion rota NO impide la reconciliacion del mismo tenant",
            f"orden: {ciclo.orden}")
    revisar("el CRM rechazo el POST" in r.get("error_global", ""),
            "y el fallo de importacion queda escrito con su causa",
            f"{r.get('error_global')!r}")
    revisar(r["reconciliacion"]["actualizados"] == 3,
            "la reconciliacion hizo su trabajo igual")

    # --- un fallo de reconciliacion NO revierte ni mata nada --------------
    def reconciliacion_rota(*a, **k):
        raise RuntimeError("el proveedor no responde")

    with CicloReal(aplicar_recon=reconciliacion_rota) as ciclo:
        with Escenario(["a", "b"], {"a": config_real(horas=48),
                                    "b": config_real(horas=48)}) as e:
            reloj.importacion_io.barrido = BARRIDO_REAL
            salida = reloj.una_pasada()
    r = salida[0]["importacion"]
    revisar(r["importacion"]["creados"] == 2,
            "lo importado sigue importado: la reconciliacion no lo revierte",
            f"{r['importacion']}")
    revisar("el proveedor no responde" in r["reconciliacion"].get("error", ""),
            "el fallo de reconciliacion queda en el resultado",
            f"{r['reconciliacion']}")
    revisar(len(salida) == 2 and "importacion" in salida[1],
            "y no impide que se atienda al siguiente tenant",
            f"{[s['tenant'] for s in salida]}")
    revisar(len(e.vencidas.llamadas) == 2,
            "ni que corran los vencimientos de los dos")

    # --- cada_horas=0 apaga el subsistema ENTERO (politica elegida) -------
    # La decision: 'cada_horas' manda sobre importacion_tickets completo. No
    # queda un estado raro donde no se importa nada pero se sigue hablando
    # con el proveedor cada hora.
    with CicloReal() as ciclo:
        with Escenario(["a"], {"a": config_real(horas=48, cada_horas=0)}):
            reloj.importacion_io.barrido = BARRIDO_REAL
            r = reloj.una_pasada()[0]["importacion"]
    revisar(ciclo.orden == [],
            "cada_horas=0: NI importacion NI reconciliacion",
            f"corrio: {ciclo.orden}")
    revisar(r == {"le_toca": False, "cada_horas": 0,
                  "haria": "nada: cada_horas=0, la importacion esta apagada"},
            "y lo dice, en vez de callarse",
            f"{r}")

    # --- en seco no escribe ninguna de las dos ----------------------------
    with CicloReal() as ciclo:
        with Escenario(["a"], {"a": config_real(horas=48)}):
            reloj.importacion_io.barrido = BARRIDO_REAL
            r = reloj.una_pasada(seco=True)[0]["importacion"]
    revisar(ciclo.orden == [],
            "--dry-run: ni 'aplicar' ni 'aplicar_reconciliacion' se llaman",
            f"corrio: {ciclo.orden}")
    revisar(r["reconciliacion"]["alcanzados"] == 2
            and r["reconciliacion"]["con_diferencia"] == 1
            and r["reconciliacion"]["actualizados"] == 0,
            "pero SI informa cuantos cambiarian",
            f"{r['reconciliacion']}")
finally:
    sin_interruptor(previo)


# ==========================================================================
#  7.c  Case.status NO ES PARTE DE NINGUNA ESCRITURA DE RECONCILIACION
# ==========================================================================
# El invariante entero de la fase. Se comprueba en los DOS lados, porque
# cualquiera de los dos alcanza para romperlo: el que arma el cuerpo y el que
# lo recibe.

print("\nCase.status no se toca reconciliando")

fuente_imp = (RAIZ / "nucleo" / "seguimiento"
              / "importacion.py").read_text(encoding="utf-8")
cuerpo_reconciliar = fuente_imp.split("def reconciliar(")[1].split("\ndef ")[0]
for prohibido in ('"status"', "'status'", '"assigned_to"', '"priority"',
                  '"stage"'):
    revisar(prohibido not in cuerpo_reconciliar,
            f"'reconciliar' no arma {prohibido} en lo que va a escribir",
            "el estado de Dexter es de Dexter; lo del proveedor va en external_*")

vista = (RAIZ / "django-crm" / "backend" / "cases"
         / "importacion_views.py").read_text(encoding="utf-8")
permitidos = vista.split("CAMPOS_RECONCILIACION = frozenset({")[1].split("})")[0]
for prohibido in ("status", "assigned_to", "stage", "priority"):
    revisar(f'"{prohibido}"' not in permitidos,
            f"y el endpoint tampoco acepta '{prohibido}'",
            f"CAMPOS_RECONCILIACION: {permitidos.strip()}")
revisar("external_status" in permitidos,
        "lo que si acepta es external_status, que es donde vive lo del proveedor")


# ==========================================================================
#  8. UNA SOLA IMPLEMENTACION
# ==========================================================================
# El riesgo de mover algo es dejar las dos copias. Aca no se prueba una
# funcion: se prueba que la vieja ya no existe en ningun lado.

print("\nno quedan dos relojes")

fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
for rastro in ("_reloj_de_vencimientos", "_ultimo_intento_importacion",
               "_tenants_conocidos", "INTERVALO_BARRIDO_SEGUNDOS"):
    revisar(rastro not in fuente_api,
            f"api.py ya no menciona '{rastro}'",
            "quedo una copia del reloj adentro del servidor web")

revisar("threading.Thread" not in fuente_api.split('if __name__ == "__main__":')[-1],
        "el bloque __main__ de api.py no arranca ningun hilo",
        "es exactamente el patron que nunca corrio bajo gunicorn")

def llamantes_de(texto: str) -> list[str]:
    return sorted(
        str(p.relative_to(RAIZ)).replace("\\", "/")
        for p in RAIZ.rglob("*.py")
        if "test" not in p.name and "\\.git" not in str(p)
        and texto in p.read_text(encoding="utf-8", errors="ignore"))


# El barrido completo lo dispara el reloj y nadie mas. (El CLI no aparece
# porque llama a 'aplicar' directamente, con sus propias banderas de piloto.)
revisar(llamantes_de("importacion_io.barrido(") == ["nucleo/reloj.py"],
        "solo el reloj llama al barrido completo",
        f"llamantes: {llamantes_de('importacion_io.barrido(')}")

# 'cerrar_vencidas' tiene dos llamantes y los dos son legitimos: el reloj, y
# el endpoint '/mantenimiento/cerrar-sin-respuesta', que es un disparo MANUAL
# --existe para poder verlo correr sin esperar la pasada-- no un segundo
# planificador. Si aparece un tercero, hay que mirarlo.
revisar(llamantes_de("operativo.cerrar_vencidas(")
        == ["nucleo/canales/api.py", "nucleo/reloj.py"],
        "'cerrar_vencidas' lo llaman el reloj y el endpoint manual, nadie mas",
        f"llamantes: {llamantes_de('operativo.cerrar_vencidas(')}")


# ==========================================================================
#  9. EL COMPOSE
# ==========================================================================

print("\nel compose")

compose = yaml.safe_load(
    (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8"))
servicios = compose["services"]
revisar("motor-reloj" in servicios, "existe el servicio 'motor-reloj'")

svc = servicios.get("motor-reloj", {})
revisar(svc.get("command") == "python -m nucleo.reloj",
        "corre el entrypoint real",
        f"command={svc.get('command')!r}")
revisar("gunicorn" not in str(svc.get("command", "")),
        "sin servidor web adentro: no atiende a nadie, espera")
revisar(str(svc.get("environment", {}).get("RELOJ_HABILITADO", ""))
        .endswith(":-0}"),
        "llega inerte: RELOJ_HABILITADO por defecto en 0",
        f"{svc.get('environment', {}).get('RELOJ_HABILITADO')!r}")
revisar("deploy" not in svc and "scale" not in svc,
        "una sola replica (no se declara ninguna escala)",
        "cerrar_vencidas no es idempotente ante ejecucion simultanea")
revisar(svc.get("networks") == ["default"],
        "solo en 'default': no tiene dominio, no va a dokploy-network",
        f"networks={svc.get('networks')}")
revisar("dokploy-network" not in str(svc.get("networks", [])),
        "y nadie lo puede alcanzar desde afuera")

# --- las credenciales que el reloj va a necesitar --------------------------
#
# 'motor' y 'motor-reloj' son contenedores distintos: que una credencial exista
# en uno no dice NADA del otro. Lo que hay que garantizar no es "la variable
# esta en el compose" --varias no viajan por ahi-- sino que este proceso pueda
# RESOLVERLAS. Hay dos caminos y el servicio necesita al menos uno de cada:
#
#   tenant_secrets   cifrado en la base, editable desde la pantalla de
#                    credenciales. Exige 'SECRETOS_CLAVE_MAESTRA'.
#   entorno          respaldo, para un tenant que todavia no la cargo.
print("\nlas credenciales que el reloj necesita")

env_reloj = svc.get("environment", {})
revisar("SECRETOS_CLAVE_MAESTRA" in env_reloj,
        "motor-reloj declara SECRETOS_CLAVE_MAESTRA",
        "sin ella no puede descifrar NINGUNA credencial de tenant_secrets, y "
        "es el unico camino que tienen las cargadas por pantalla")

# La lista canonica de herramientas de importacion vive en importacion_io, y
# esto exige que no derive: cada '_herramienta(config, \"x\")' de ese modulo
# tiene que estar declarada ahi.
from nucleo.seguimiento import importacion_io as io_mod  # noqa: E402

fuente_io = (RAIZ / "nucleo" / "seguimiento"
             / "importacion_io.py").read_text(encoding="utf-8")
usadas = set(re.findall(r'_herramienta\(config,\s*"([a-z_]+)"', fuente_io))
faltantes = sorted(usadas - io_mod.HERRAMIENTAS)
revisar(not faltantes,
        "importacion_io.HERRAMIENTAS no derivo de lo que el modulo usa",
        f"usa por nombre y no declara: {faltantes}")

# Y el reloj deduce las credenciales del catalogo del tenant, no de una lista
# escrita a mano.
from nucleo.config.schema import cargar_config  # noqa: E402

cfg_yaml = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
necesarias = reloj.credenciales_necesarias(cfg_yaml)
revisar("IMPORTACION_API_TOKEN" in necesarias,
        "el reloj sabe que va a necesitar IMPORTACION_API_TOKEN",
        f"deducidas: {sorted(necesarias)}")
revisar(len(necesarias.get("IMPORTACION_API_TOKEN", [])) == 4,
        "y que son las cuatro herramientas internas de Fase 2 las que la piden",
        f"{necesarias.get('IMPORTACION_API_TOKEN')}")
revisar({"WISPHUB_API_KEY", "BOTTLECRM_API_TOKEN"} <= set(necesarias),
        "y las dos del cierre de vencidas",
        f"deducidas: {sorted(necesarias)}")

# El secreto no puede estar escrito en el repo. Ni el valor, ni una variable
# que invite a pegarlo en el compose.
compose_texto = (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8")
revisar("${IMPORTACION_API_TOKEN" not in compose_texto,
        "el compose no pide IMPORTACION_API_TOKEN por entorno",
        "vive cifrada en tenant_secrets; declararla ademas aca seria un "
        "segundo lugar de edicion para el mismo secreto, y la base gana")

# El interruptor es del DESPLIEGUE. Si aparece en la config del tenant, se
# convirtio en otra cosa.
for yml in (RAIZ / "tenants").glob("*.yaml"):
    revisar("RELOJ_HABILITADO" not in yml.read_text(encoding="utf-8"),
            f"'{yml.name}' no declara el interruptor",
            "encender el reloj es una decision de operacion, no de tenant")

# Y gunicorn deja de tener nada que ver con esto.
motor = servicios["motor"]
revisar("gunicorn" in str(motor.get("command", "")),
        "'motor' sigue siendo gunicorn (no se toco)")
revisar("nucleo.reloj" not in str(motor.get("command", "")),
        "y 'motor' no es responsable de ninguna tarea periodica")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El reloj arranca, llega apagado, aisla sus fallos y existe una sola vez.")
