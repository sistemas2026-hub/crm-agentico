# -*- coding: utf-8 -*-
"""
================================================================================
 VALIDADA LA ORDEN, EL TICKET DEL ISP SE CIERRA  --  que SALGA, y una vez
================================================================================

    py -3.13 tests/test_cierre_por_validacion.py

Mismo andamio que tests/test_cierre_por_propuesta.py, por la misma razon: ese
modulo estuvo meses sin poder ejecutarse porque abria la puerta DENTRO de
`idempotencia.ejecutar`, que pregunta por el permiso antes de llamar. Aca se
afirma sobre el EFECTO -- que la mutacion le llega al proveedor, con permiso
humano -- y no se sustituye `idempotencia.ejecutar` ni se abre ningun permiso
desde la suite.

Se afirma:
  1  la mutacion SALE, una vez, por la puerta HUMANA, con el estado de cierre
     de la herramienta y el nombre de quien valido en el texto
  2  una segunda validacion de la misma orden NO la vuelve a publicar
  3  sin quien valido, no sale (no se adivina un responsable)
  4  con el interruptor tirado, no sale
  5  sin herramienta de cierre declarada, no sale
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db as persistencia               # noqa: E402
from nucleo.seguimiento import cierre_por_validacion as cierre   # noqa: E402
from nucleo.seguridad import frontera                            # noqa: E402

TENANT = "tenant-de-prueba"
ORDEN = "11111111-2222-3333-4444-555555555555"
TICKET = "94721"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


class Herramienta:
    nombre = "cerrar_ticket_operativo"
    cierra_ticket_operativo = True
    argumentos_fijos = {"ticket-estado": "4", "ticket-prioridad": "2"}


class Config:
    def __init__(self, herramientas=None):
        self.herramientas = [Herramienta()] if herramientas is None else herramientas
    variables_tenant: dict = {}


class Veredicto:
    def __init__(self, permitido=True):
        self.permitido = permitido
        self.estado = "activo" if permitido else "detenido"
        self.motivo = ""


class Registro:
    def __init__(self):
        self.filas: dict[str, dict] = {}

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        fila = self.filas.get(clave)
        if fila is None:
            self.filas[clave] = {"intentos": 1, "estado": "ejecutando",
                                 "respuesta": None}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        if fila["estado"] == "exitosa":
            return {"decision": "repetida", "fila": fila}
        return {"decision": "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        fila = self.filas.setdefault(clave, {"intentos": 1})
        fila["estado"] = estado
        fila["respuesta"] = respuesta


class Proveedor:
    def __init__(self):
        self.llamadas: list[dict] = []
        self.permisos: list = []

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        self.llamadas.append(dict(argumentos))
        self.permisos.append(frontera.permiso_vigente())
        return {"id_ticket": argumentos.get("id_ticket")}


@contextlib.contextmanager
def escenario(registro, proveedor, permitido=True):
    import nucleo.herramientas.http as ejecutor_http
    from nucleo.seguridad import interruptor

    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  interruptor.veredicto, interruptor.anotar_bloqueo,
                  ejecutor_http.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar
    interruptor.veredicto = lambda t: Veredicto(permitido)
    interruptor.anotar_bloqueo = lambda *a, **k: None
    ejecutor_http.ejecutar = proveedor.ejecutar
    try:
        afirmar(frontera.permiso_vigente() is None,
                "el andamio NO deja ningun permiso abierto")
        yield
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa,
         interruptor.veredicto, interruptor.anotar_bloqueo,
         ejecutor_http.ejecutar) = originales


def cerrar(actor="Laura Gomez", orden=ORDEN, config=None):
    return cierre.cerrar_ticket_de_orden(
        config or Config(), TENANT, orden_id=orden, ticket=TICKET,
        texto="Trabajo de campo OT #7001 validado en Dexter.", actor=actor)


seccion("1. la mutacion SALE, una vez, por la puerta humana")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = cerrar()
afirmar(r.cerrado, f"el ticket queda cerrado (codigo={r.codigo}, motivo={r.motivo})")
afirmar(len(proveedor.llamadas) == 1, "le llego UNA mutacion al proveedor")
if proveedor.llamadas:
    args = proveedor.llamadas[0]
    afirmar(args.get("ticket-estado") == "4",
            "con el estado de cierre de la HERRAMIENTA, no uno elegido aca")
    afirmar(args.get("id_ticket") == TICKET, "sobre el ticket de la orden")
    afirmar("Laura Gomez" in args.get("respuesta", ""),
            "con el nombre de quien valido en el texto (el ISP firma con la API key)")
    p = proveedor.permisos[0]
    afirmar(p is not None, "con un permiso de la frontera vigente al ejecutar")
    afirmar(p is not None and p.clase == "humana",
            "y ese permiso es HUMANO: lo decidio la persona que valido")
    afirmar(p is not None and p.actor == "Laura Gomez", "el permiso dice QUIEN")
    afirmar(p is not None and p.evidencia == f"orden_validada:{ORDEN}",
            "y contra que registro se comprueba: la orden validada")
afirmar(r.referencia == f"orden_validada:{ORDEN}",
        "la clave idempotente es la orden validada")

seccion("2. una segunda validacion de la misma orden no vuelve a publicar")
with escenario(registro, proveedor):
    r2 = cerrar()
afirmar(r2.cerrado, "responde cerrado ('ya se habia cerrado antes')")
afirmar(len(proveedor.llamadas) == 1, "y el proveedor sigue con UNA sola llamada")

seccion("2b. un segundo intento con OTRO texto tampoco vuelve a publicar")
#  Auditoria de frontera del 13/10/2026 (H2): la clave por defecto hashea los
#  argumentos y el texto va en ellos -- un texto distinto era otra operacion y
#  el ticket lo recibia dos veces. La clave es fija por orden.
with escenario(registro, proveedor):
    r3 = cierre.cerrar_ticket_de_orden(
        Config(), TENANT, orden_id=ORDEN, ticket=TICKET,
        texto="Otro texto: llego una foto mas.", actor="Laura Gomez")
afirmar(len(proveedor.llamadas) == 1,
        f"el proveedor sigue con UNA sola llamada (codigo={r3.codigo})")
afirmar(list(registro.filas) == [f"orden_validada:{ORDEN}|cerrar_ticket_operativo"],
        "y la clave es la orden, no el texto")

seccion("3. sin quien valido, no sale")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = cerrar(actor="  ")
afirmar(r.codigo == cierre.NO_EJECUTADA, f"no se ejecuta (codigo={r.codigo})")
afirmar(proveedor.llamadas == [], "y no le llega nada al proveedor")

seccion("4. con el interruptor tirado, no sale")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor, permitido=False):
    r = cerrar()
afirmar(r.codigo == cierre.BLOQUEADO_POR_INTERRUPTOR,
        f"se bloquea por el interruptor (codigo={r.codigo})")
afirmar(proveedor.llamadas == [], "y no le llega nada al proveedor")

seccion("5. sin herramienta de cierre declarada, no sale")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = cerrar(config=Config(herramientas=[]))
afirmar(r.codigo == cierre.SIN_HERRAMIENTA, f"lo dice (codigo={r.codigo})")
afirmar(proveedor.llamadas == [], "y no le llega nada al proveedor")

# =============================================================================
#  EL SUPERVISOR CIERRA SOLO  --  30/10/2026, por la puerta AUTONOMA
# =============================================================================
#  6  con las cuatro compuertas abiertas, sale UNA vez, con permiso AUTONOMO,
#     firmado por el Supervisor y con su propia clave
#  7  cada compuerta cerrada lo frena, dice cual, y no le llega nada al
#     proveedor: el interruptor, la etapa (B-7) y la autorizacion
#  8  la puerta humana NO se abre para el Supervisor


class HerramientaQueEscribe(Herramienta):
    solo_lectura = False


class Compuertas:
    """Las cuatro compuertas de `frontera.autonoma`, sustituidas."""

    def __init__(self, interruptor=True, etapa=True, granular=True):
        self.cfg = dict(interruptor=interruptor, etapa=etapa, granular=granular)

    def __enter__(self):
        class V:
            def __init__(self, ok, codigo):
                self.permitido, self.codigo, self.estado = ok, codigo, codigo
                self.motivo, self.nivel_efectivo, self.autorizacion_id = "x", 2, ""
                self.techo, self.requerido = 2, 2

        c = self.cfg
        self._orig = (frontera.interruptor.veredicto, frontera.techos.veredicto,
                      frontera.autonomia2.veredicto, frontera.autorizacion.veredicto,
                      frontera._bitacora, frontera._anotar)
        frontera.interruptor.veredicto = lambda t: V(c["interruptor"], "detenido")
        frontera.techos.veredicto = lambda t, n: V(True, "ok")
        frontera.autonomia2.veredicto = lambda *a, **k: V(c["etapa"], "B7_REQUERIDO")
        frontera.autorizacion.veredicto = lambda t, h, **k: V(
            c["granular"], "HERRAMIENTA_SIN_AUTORIZACION")
        frontera._bitacora = lambda *a, **k: None
        frontera._anotar = lambda *a, **k: None
        return self

    def __exit__(self, *e):
        (frontera.interruptor.veredicto, frontera.techos.veredicto,
         frontera.autonomia2.veredicto, frontera.autorizacion.veredicto,
         frontera._bitacora, frontera._anotar) = self._orig
        return False


def cierra_el_supervisor(**compuertas):
    registro, proveedor = Registro(), Proveedor()
    with escenario(registro, proveedor), Compuertas(**compuertas):
        r = cierre.cerrar_ticket_por_el_supervisor(
            Config([HerramientaQueEscribe()]), TENANT, orden_id=ORDEN, ticket=TICKET,
            texto="Trabajo de campo OT #7001 validado en Dexter.")
    return r, registro, proveedor


seccion("6. el Supervisor: sale UNA vez, por la puerta AUTONOMA")
r, registro, proveedor = cierra_el_supervisor()
afirmar(r.cerrado, f"el ticket queda cerrado (codigo={r.codigo}, motivo={r.motivo})")
afirmar(len(proveedor.llamadas) == 1, "le llego UNA mutacion al proveedor")
if proveedor.llamadas:
    p = proveedor.permisos[0]
    afirmar(p is not None and p.clase == "autonoma",
            "y el permiso es AUTONOMO, no humano: nadie valido en el momento")
    afirmar(p is not None and p.actor == cierre.SUPERVISOR, "el permiso dice que fue el Supervisor")
    afirmar(cierre.FIRMA_DEL_SUPERVISOR in proveedor.llamadas[0].get("respuesta", ""),
            "el texto del ticket dice que lo cerro el Supervisor")
    afirmar(proveedor.llamadas[0].get("ticket-estado") == "4",
            "con el estado de cierre de la HERRAMIENTA")
afirmar(list(registro.filas) == [f"orden_validada:{ORDEN}|cerrar_ticket_operativo"],
        "con la MISMA clave que la validacion humana: las dos puertas se excluyen "
        "por clave primaria (auditoria de frontera, 30/10/2026, H3)")

seccion("7. cada compuerta cerrada lo frena, y dice cual")
for etiqueta, kw, codigo in (
        ("el interruptor", {"interruptor": False}, "AUTONOMIA"),
        ("la etapa con B-7", {"etapa": False}, "B7_REQUERIDO"),
        ("la autorizacion de la herramienta", {"granular": False},
         "HERRAMIENTA_SIN_AUTORIZACION")):
    r, _, proveedor = cierra_el_supervisor(**kw)
    afirmar(r.codigo == cierre.NO_AUTORIZADA and proveedor.llamadas == [],
            f"{etiqueta}: no sale (codigo={r.codigo})")
    afirmar(codigo in r.motivo or etiqueta == "el interruptor",
            f"{etiqueta}: el motivo dice cual ({r.motivo[:60]})")

seccion("8. la puerta humana no se abre para el Supervisor")
_orig_humana = frontera.humana
_abiertas = []
frontera.humana = lambda *a, **k: _abiertas.append(k) or _orig_humana(*a, **k)
try:
    cierra_el_supervisor()
finally:
    frontera.humana = _orig_humana
afirmar(_abiertas == [], "frontera.humana() no se llamo")

# =============================================================================
#  9-11  CON EL CATALOGO REAL Y EL EJECUTOR REAL  --  auditoria, 30/10/2026
# =============================================================================
#  Las secciones de arriba sustituyen `ejecutor_http.ejecutar`, que es donde
#  corre el ultimo metro (`frontera.exigir`): con el catalogo real, la
#  herramienta declara `aprobacion_humana` y eso las secciones de arriba no lo
#  podian ver (H1). Aca solo se sustituye la RED (`requests.request`).
import yaml                                                       # noqa: E402

import nucleo.herramientas.http as ejecutor_real                  # noqa: E402
from nucleo.config.schema import TenantConfig                     # noqa: E402

_crudo = yaml.safe_load((RAIZ / "tenants/rapilink.config.yaml").read_text(encoding="utf-8"))
CATALOGO_REAL = TenantConfig(**_crudo)
HERR_REAL = next(h for h in CATALOGO_REAL.herramientas if h.cierra_ticket_operativo)


class RegistroComoLaBase(Registro):
    """Como `persistencia.reclamar_operacion_externa`: la huella se compara
    ANTES que el estado; la misma clave con otros argumentos es «rechazada»
    (nucleo/persistencia/db.py)."""

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        fila = self.filas.get(clave)
        if fila is not None and fila.get("hash") != argumentos_hash:
            return {"decision": "rechazada", "fila": fila,
                    "motivo": "la misma clave ya se uso con otros argumentos"}
        r = super().reclamar(tenant, clave, herramienta, argumentos_hash, origen,
                             segundos_vencida, reintentar_fallida)
        self.filas[clave].setdefault("hash", argumentos_hash)
        return r


class _Red:
    def __init__(self):
        self.pedidos = []

    def __call__(self, metodo, url, **k):
        self.pedidos.append(url)

        class _R:
            ok, status_code = True, 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": True}
        return _R()


@contextlib.contextmanager
def red_falsa(registro, red):
    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  getattr(persistencia, "registrar_ejecucion_autonoma", None),
                  ejecutor_real.headers_de, ejecutor_real.requests.request)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar
    persistencia.registrar_ejecucion_autonoma = lambda *a, **k: None
    ejecutor_real.headers_de = lambda h, t: {}
    ejecutor_real.requests.request = red
    try:
        with Compuertas():
            yield
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa,
         persistencia.registrar_ejecucion_autonoma,
         ejecutor_real.headers_de, ejecutor_real.requests.request) = originales


class _ConfigDe:
    def __init__(self, herr):
        self.herramientas = [herr]
        self.variables_tenant = CATALOGO_REAL.variables_tenant


seccion("9. catalogo REAL: la herramienta exige aprobacion humana y el Supervisor no la quema")
afirmar(HERR_REAL.aprobacion_humana is True,
        "el catalogo real declara aprobacion_humana en la herramienta de cierre (M06-E)")
registro, red = RegistroComoLaBase(), _Red()
with red_falsa(registro, red):
    r1 = cierre.cerrar_ticket_por_el_supervisor(
        _ConfigDe(HERR_REAL), TENANT, orden_id=ORDEN, ticket=TICKET, texto="T")
    r2 = cierre.cerrar_ticket_por_el_supervisor(
        _ConfigDe(HERR_REAL), TENANT, orden_id=ORDEN, ticket=TICKET, texto="T")
afirmar(r1.codigo == cierre.NO_AUTORIZADA and "APROBACION_HUMANA_REQUERIDA" in r1.motivo,
        f"no sale, y dice POR QUE (codigo={r1.codigo}, motivo={r1.motivo[:50]})")
afirmar(red.pedidos == [], "no le llega nada al ISP")
afirmar(registro.filas == {}, "y no quema el intento: la clave no se reclamo")
afirmar(r2.codigo == cierre.NO_AUTORIZADA,
        f"la vuelta siguiente dice lo mismo, no 'fallida previa' (codigo={r2.codigo})")

seccion("10. sin esa marca: una sola publicacion aunque las dos puertas cierren la misma orden")
sin_marca = HERR_REAL.model_copy(update={"aprobacion_humana": False})
for primero in ("supervisor", "persona"):
    registro, red = RegistroComoLaBase(), _Red()
    with red_falsa(registro, red):
        sup = lambda: cierre.cerrar_ticket_por_el_supervisor(          # noqa: E731
            _ConfigDe(sin_marca), TENANT, orden_id=ORDEN, ticket=TICKET,
            texto="Trabajo de campo OT #7001 validado en Dexter.")
        per = lambda: cierre.cerrar_ticket_de_orden(                   # noqa: E731
            _ConfigDe(sin_marca), TENANT, orden_id=ORDEN, ticket=TICKET,
            texto="Trabajo de campo OT #7001 validado en Dexter.", actor="Laura Gomez")
        a, b = (sup(), per()) if primero == "supervisor" else (per(), sup())
    afirmar(len(red.pedidos) == 1,
            f"primero {primero}: el ISP recibe UNA publicacion ({len(red.pedidos)})")
    afirmar(a.cerrado and not b.cerrado,
            f"primero {primero}: la segunda puerta no publica (codigo={b.codigo})")
    if primero == "persona":
        afirmar(b.codigo == cierre.INCIERTO,
                f"y el Supervisor lo dice como INCIERTO, no como 'no pudo' ({b.codigo})")

seccion("11. la puerta humana rechaza al Supervisor")
registro, red = RegistroComoLaBase(), _Red()
with red_falsa(registro, red):
    for actor in ("Supervisor", "supervisor", cierre.FIRMA_DEL_SUPERVISOR, "servicio:x"):
        r = cierre.cerrar_ticket_de_orden(
            _ConfigDe(sin_marca), TENANT, orden_id=ORDEN, ticket=TICKET,
            texto="T", actor=actor)
        afirmar(r.codigo == cierre.NO_EJECUTADA, f"actor {actor!r}: no entra (codigo={r.codigo})")
afirmar(red.pedidos == [], "y no le llega nada al ISP")

print()
if _fallos:
    print(f"[FALLA] {len(_fallos)} afirmaciones no se cumplen.")
    sys.exit(1)
print("[OK] Validada la orden, el ticket del ISP se cierra una vez, por la "
      "puerta humana y con el kill switch consultado; y el Supervisor, por la "
      "autonoma con sus cinco compuertas, sin quemar el intento y sin publicar "
      "dos veces.")
