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

print()
if _fallos:
    print(f"[FALLA] {len(_fallos)} afirmaciones no se cumplen.")
    sys.exit(1)
print("[OK] Validada la orden, el ticket del ISP se cierra una vez, por la "
      "puerta humana y con el kill switch consultado.")
