# -*- coding: utf-8 -*-
"""
================================================================================
 PRUEBA ADVERSARIAL DE LA FRONTERA  --  intentar romperla, no confirmarla
================================================================================

    py -3.13 tests/test_frontera_adversarial.py

La diferencia con tests/test_frontera_externa.py: aquella comprueba que los
caminos QUE EXISTEN frenan. Esta intenta inventar caminos nuevos -- hilos,
tareas async, un modulo que no sabe que la frontera existe, argumentos
fabricados-- y mide si alguno sale.

COMO SE MIDE
------------
Se sustituye 'requests' DENTRO de nucleo/herramientas/http.py. Corre el codigo
real completo, incluida la comprobacion de la frontera; lo unico que no ocurre
es el viaje por la red. Si el contador sube, la llamada HABRIA salido.

CERO LLAMADAS REALES a WispHub, SmartOLT o el CRM.
================================================================================
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                          # noqa: E402
from nucleo.herramientas import http as ejecutor_http            # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402
from nucleo.seguimiento import importacion_io                    # noqa: E402
from nucleo.seguimiento import operativo                         # noqa: E402
from nucleo.seguridad import frontera                            # noqa: E402
from nucleo.seguridad import idempotencia                        # noqa: E402
from nucleo.seguridad import interruptor                         # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug

fallos: list[str] = []
salidas: list[str] = []
matriz: list[dict] = []


class _Resp:
    ok = True
    status_code = 200
    text = "{}"

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "id_ticket": "FALSO", "task_id": "T1",
                "created": True, "results": []}


class _Req:
    def _a(self, m, url, **kw):
        salidas.append(f"{m} {url}")
        return _Resp()

    def get(self, url, **kw):
        return self._a("GET", url, **kw)

    def post(self, url, **kw):
        return self._a("POST", url, **kw)

    def request(self, m, url, **kw):
        return self._a(m, url, **kw)


ejecutor_http.requests = _Req()
ejecutor_http.headers_de = lambda h, tenant=None: {}

#  El interruptor: DETENIDO. Se sustituye la LECTURA, no el veredicto, para que
#  corra el codigo real de interruptor.py.
interruptor.persistencia.estado_autonomia = lambda t: {
    "estado": "detenido", "actor": "prueba", "motivo": "adversarial 10.14B"}
interruptor.persistencia.registrar_auditoria = lambda *a, **k: None

#  Una escritura COMUN (ni irreversible ni con aprobacion humana): desde M06-E
#  la primera escritura http del catalogo es cancelar_solicitud_servicio, que
#  solo sale por frontera.critica, y los casos de "dentro del permiso SI sale"
#  dejaban de medir lo que dicen. Las irreversibles tienen su propia bateria.
HERR_W = next(h for h in CONFIG.herramientas
              if h.tipo == "http" and not getattr(h, "solo_lectura", True)
              and not getattr(h, "irreversible", False)
              and not getattr(h, "aprobacion_humana", False))
HERR_R = next(h for h in CONFIG.herramientas
              if h.tipo == "http" and getattr(h, "solo_lectura", True))


def caso(ruta, tipo, fn, *, tenant=TENANT, actor="", espera="bloqueado"):
    """Corre un intento y lo anota en la matriz."""
    n0 = len(salidas)
    detalle = ""
    try:
        fn()
    except Exception as e:
        detalle = type(e).__name__
    externas = len(salidas) - n0
    bloqueado = (externas == 0)
    ok = bloqueado if espera == "bloqueado" else (not bloqueado)
    matriz.append({"ruta": ruta, "tipo": tipo, "tenant": tenant or "(vacio)",
                   "actor": actor or "-", "externas": externas,
                   "resultado": "BLOQUEADO" if bloqueado else "ejecutado",
                   "motivo": detalle or "-", "ok": ok})
    print(f"  [{'ok' if ok else 'NO'}]    {ruta}  ->  "
          f"{'BLOQUEADO' if bloqueado else 'EJECUTADO'} "
          f"(externas={externas}) {detalle}")
    if not ok:
        fallos.append(ruta)


def escribir(tenant=TENANT):
    return motor._ejecutar_tool(HERR_W, None, {"servicio": "1"}, tenant,
                                CONFIG.variables_tenant)


# =============================================================================
print("=" * 78)
print("  1. EL EJECUTOR, POR LA PUERTA DE ATRAS")
print("=" * 78)

caso("ejecutor_http.ejecutar directo", "B",
     lambda: ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT))
caso("ejecutor_http.ejecutar_asincrono directo", "B",
     lambda: ejecutor_http.ejecutar_asincrono(HERR_W, {"servicio": "1"},
                                              tenant=TENANT))
caso("ejecutor con tenant=None", "B",
     lambda: ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, None),
     tenant=None)

# =============================================================================
print("")
print("=" * 78)
print("  2. EL MOTOR Y EL TENANT")
print("=" * 78)

caso("motor._ejecutar_tool (modelo)", "B", lambda: escribir())
caso("motor._ejecutar_tool tenant=None", "B", lambda: escribir(None), tenant=None)
caso("motor._ejecutar_tool tenant=''", "B", lambda: escribir(""), tenant="")
caso("motor._ejecutar_tool tenant inexistente", "B",
     lambda: escribir("isp-fantasma"), tenant="isp-fantasma")
caso("motor.ejecutar_para_servicio (/interno)", "B",
     lambda: motor.ejecutar_para_servicio(CONFIG, HERR_W, {"servicio": "1"}))

# =============================================================================
print("")
print("=" * 78)
print("  3. HILOS, POOLS Y ASYNC  --  donde el contexto podria filtrarse")
print("=" * 78)


def _en_hilo(dentro_del_permiso: bool):
    resultado = {}

    def cuerpo():
        try:
            ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)
            resultado["salio"] = True
        except Exception as e:
            resultado["err"] = type(e).__name__

    if dentro_del_permiso:
        with frontera.humana(TENANT, HERR_W.nombre, actor="mayra",
                             evidencia="hilo"):
            h = threading.Thread(target=cuerpo)
            h.start()
            h.join()
    else:
        h = threading.Thread(target=cuerpo)
        h.start()
        h.join()


caso("threading.Thread creado FUERA del permiso", "B",
     lambda: _en_hilo(False))
caso("threading.Thread creado DENTRO del permiso "
     "(el contexto NO se hereda)", "B", lambda: _en_hilo(True))


def _en_pool():
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra", evidencia="pool"):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(ejecutor_http.ejecutar, HERR_W,
                      {"servicio": "1"}, TENANT).result()


caso("ThreadPoolExecutor.submit dentro del permiso", "B", _en_pool)


async def _corutina():
    ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


def _async_fuera():
    asyncio.run(_corutina())


def _async_dentro():
    #  asyncio COPIA el contexto al arrancar la corutina, asi que aqui el
    #  permiso SI viaja. Se mide, no se supone.
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra",
                         evidencia="async"):
        asyncio.run(_corutina())


caso("asyncio.run FUERA del permiso", "B", _async_fuera)
caso("asyncio.run DENTRO del permiso (el contexto SI se copia)", "A",
     _async_dentro, actor="mayra", espera="ejecutado")

# =============================================================================
print("")
print("=" * 78)
print("  4. FABRICAR LA AUTORIZACION")
print("=" * 78)


def _kwarg_publico():
    #  No existe tal parametro. Si algun dia alguien lo agrega, esto deja de
    #  levantar TypeError y la prueba lo canta.
    idempotencia.ejecutar(TENANT, HERR_W.nombre, {"a": 1}, "x",
                          lambda: None, autorizado=True)


try:
    _kwarg_publico()
    print("  [NO]    idempotencia.ejecutar acepta 'autorizado=True'")
    fallos.append("existe un parametro publico 'autorizado'")
except TypeError as e:
    print(f"  [ok]    no existe 'autorizado=True' publico  ->  TypeError: "
          f"{str(e).split(chr(10))[0][:60]}")


def _exigir_kwarg():
    frontera.exigir(HERR_W, TENANT, autorizado=True)


try:
    _exigir_kwarg()
    print("  [NO]    frontera.exigir acepta 'autorizado=True'")
    fallos.append("frontera.exigir acepta 'autorizado'")
except TypeError:
    print("  [ok]    frontera.exigir tampoco acepta 'autorizado='")
except frontera.AccionExternaNoAutorizada:
    print("  [NO]    frontera.exigir acepto el kwarg y solo fallo por permiso")
    fallos.append("frontera.exigir acepta 'autorizado'")

def _permiso_falso():
    testigo = frontera._PERMISO.set({"tenant": TENANT, "clase": "autonoma"})
    try:
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)
    finally:
        frontera._PERMISO.reset(testigo)


caso("un dict cualquiera puesto donde va el permiso", "B", _permiso_falso)


print("")
print("  --- el ContextVar privado: se puede tocar, y se ve ---")
externas_antes = len(salidas)
testigo = frontera._PERMISO.set(
    frontera._Permiso(tenant=TENANT, clase="autonoma", actor="atacante",
                      origen="forjado"))
try:
    ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)
    forjado_salio = True
finally:
    frontera._PERMISO.reset(testigo)
forjado = len(salidas) - externas_antes
print(f"  [--]    frontera._PERMISO.set(frontera._Permiso(...)) SI funciona "
      f"(externas={forjado})")
print("          Es el limite declarado en 10.14A y no se esconde: hacen falta")
print("          DOS nombres privados en la misma linea, y eso no se escribe")
print("          por accidente ni pasa desapercibido en un diff.")
print("  [ok]    y no hay ninguna via PUBLICA que consiga lo mismo")

# =============================================================================
print("")
print("=" * 78)
print("  5. UNA RUTA NUEVA QUE NO SABE QUE LA FRONTERA EXISTE")
print("=" * 78)
print("  (importa el ejecutor y escribe; no menciona frontera, ni interruptor,")
print("   ni idempotencia -- como el archivo que alguien escriba el mes que viene)")


def modulo_nuevo_ingenuo(config, tenant, servicio):
    """Lo que escribiria alguien que no leyo nada de esto."""
    from nucleo.herramientas import http as ejec
    herr = next(h for h in config.herramientas
                if h.tipo == "http" and not getattr(h, "solo_lectura", True))
    return ejec.ejecutar(herr, {"servicio": servicio}, tenant)


caso("modulo nuevo que ignora la frontera", "B",
     lambda: modulo_nuevo_ingenuo(CONFIG, TENANT, "1"))

# =============================================================================
print("")
print("=" * 78)
print("  6. LOS MODULOS REALES")
print("=" * 78)

caso("operativo.responder SIN actor", "B",
     lambda: operativo._ejecutar(CONFIG, TENANT, "responde_ticket_operativo",
                                 "1", "t", ""))
caso("operativo.cerrar", "B", lambda: operativo.cerrar(CONFIG, TENANT, "1", "t"))
caso("operativo.cerrar_caso_crm", "B",
     lambda: operativo.cerrar_caso_crm(CONFIG, TENANT, "1"))
caso("operativo.cerrar_todo (los tres lados)", "B",
     lambda: operativo.cerrar_todo(
         CONFIG, TENANT,
         {"id": "c1", "caso_id": "k1", "ticket_operativo": "1"}, "texto"))


#  UN CANDIDATO DE VERDAD, CON LA CLASE REAL.
#  Con la lista vacia 'aplicar' no entra al bucle y no llama a nada: "0 llamadas
#  externas" seria un falso positivo -- diria "bloqueado" cuando lo que paso es
#  que no habia nada que hacer. Y con un doble a medias, '_cuerpo_de' revienta
#  con AttributeError, 'aplicar' lo cuenta como fallido y tampoco llama: el
#  mismo falso positivo por otra puerta. Por eso se usa la dataclass real.
from nucleo.seguimiento import importacion as _imp                # noqa: E402

CANDIDATOS = [_imp.Veredicto(external_ticket_id="T-999",
                             external_service_id="S-1",
                             asunto="prueba adversarial 10.14B",
                             resultado=_imp.CANDIDATO)]

caso("importacion_io.aplicar SIN actor", "B",
     lambda: importacion_io.aplicar(CONFIG, TENANT, CANDIDATOS))
caso("idempotencia.ejecutar como puerta suelta", "B",
     lambda: idempotencia.ejecutar(
         TENANT, HERR_W.nombre, {"a": 1}, "suelto",
         lambda: ejecutor_http.ejecutar(HERR_W, {"a": 1}, TENANT)))

# =============================================================================
print("")
print("=" * 78)
print("  7. LO QUE NO DEBE BLOQUEARSE")
print("=" * 78)

caso("una LECTURA con el interruptor tirado", "C",
     lambda: ejecutor_http.ejecutar(HERR_R, {}, TENANT),
     espera="ejecutado")


def _humana_completa():
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra.vasquez",
                         evidencia="propuesta:abc-123"):
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


caso("puerta humana con actor + evidencia", "A", _humana_completa,
     actor="mayra.vasquez", espera="ejecutado")


def _operativo_humano():
    operativo._ejecutar(CONFIG, TENANT, "responde_ticket_operativo",
                        "1", "respuesta del agente", "mayra.vasquez")


caso("operativo.responder CON actor (agente humano)", "A", _operativo_humano,
     actor="mayra.vasquez", espera="ejecutado")


def _importacion_humana():
    importacion_io.aplicar(CONFIG, TENANT, CANDIDATOS, actor="cli:mayra")


caso("importacion_io.aplicar CON actor (CLI)", "D", _importacion_humana,
     actor="cli:mayra", espera="ejecutado")

def _humana_parcial(actor, evidencia):
    with frontera.humana(TENANT, HERR_W.nombre, actor=actor, evidencia=evidencia):
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


print("")
print("  --- la puerta humana no se abre a medias ---")
for nombre, _actor, _evid in (("sin actor", "", "x"),
                              ("sin evidencia", "mayra", ""),
                              ("actor en blanco", "   ", "x")):
    caso(f"puerta humana {nombre}", "A",
         lambda a=_actor, e=_evid: _humana_parcial(a, e), actor=_actor)


# =============================================================================
print("")
print("=" * 78)
print("  8. AUDITORIA DE LO QUE SI PASA")
print("=" * 78)

with frontera.humana(TENANT, "x", actor="mayra", evidencia="propuesta:9"):
    p = frontera.permiso_vigente()
    print(f"  permiso vigente: tenant={p.tenant} clase={p.clase} "
          f"actor={p.actor} evidencia={p.evidencia}")
    for campo in ("tenant", "clase", "actor"):
        v = getattr(p, campo)
        print(f"  [{'ok' if v else 'NO'}]    el permiso declara '{campo}'")
        if not v:
            fallos.append(f"permiso sin {campo}")

print(f"  [{'ok' if frontera.permiso_vigente() is None else 'NO'}]"
      f"    fuera del bloque no queda permiso vigente")
if frontera.permiso_vigente() is not None:
    fallos.append("el permiso sobrevive al bloque")

# =============================================================================
print("")
print("=" * 78)
print("  MATRIZ")
print("=" * 78)
print(f"  {'ruta':<48} {'tipo':<5} {'tenant':<14} {'ext':>4}  resultado")
print("  " + "-" * 92)
for f in matriz:
    print(f"  {f['ruta'][:48]:<48} {f['tipo']:<5} {f['tenant'][:14]:<14} "
          f"{f['externas']:>4}  {f['resultado']}")

autonomas = [f for f in matriz if f["tipo"] == "B"]
ext_autonomas = sum(f["externas"] for f in autonomas)
print("")
print(f"  rutas AUTONOMAS probadas: {len(autonomas)}  "
      f"-> llamadas externas: {ext_autonomas}")
if ext_autonomas:
    fallos.append(f"{ext_autonomas} llamada(s) externa(s) por ruta autonoma")

print("")
print("=" * 78)
if fallos:
    print(f"  {len(fallos)} FALLO(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  [OK] Ninguna ruta autonoma produjo un efecto externo.")
print(f"       llamadas externas REALES: 0  ({len(salidas)} simuladas, "
      f"todas por rutas humanas o de lectura)")
print("=" * 78)
