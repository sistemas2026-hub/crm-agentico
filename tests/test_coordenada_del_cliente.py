# -*- coding: utf-8 -*-
"""La ubicacion del cliente se escribe una vez, por la puerta humana, y en orden.

LO QUE ESTE ARCHIVO DEFIENDE  --  10/11/2026

* **El equipo primero, y si falla NO se escribe el servicio.** Es la decision
  del usuario: en el equipo falta el 99,8 % del dato, asi que es el que define
  si la accion sirvio. Dejar escrito solo el segundo produce dos sistemas que
  se contradicen sin que nadie lo sepa.
* **Una clave de idempotencia POR DESTINO.** Con una sola, un exito a medias
  queda sin salida: el que fallo volveria como «repetida» por culpa del que si
  salio. Esta prueba lo mide contando las filas del registro.
* **Los nombres de los parametros salen de la configuracion**, no del codigo:
  un sistema pide dos campos separados y el otro uno combinado.
* **Nada se escribe si la coordenada no es una coordenada, ni si el
  interruptor no se puede leer.** Las dos afirman CERO llamadas al proveedor,
  no un codigo de retorno: un codigo se puede devolver igual despues de haber
  escrito.
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db as persistencia                  # noqa: E402
from nucleo.seguimiento import coordenada_del_cliente as coord      # noqa: E402
from nucleo.seguridad import frontera                               # noqa: E402

TENANT = "tenant-de-prueba"
ORIGEN = "coordenada_de_orden:11111111-2222-3333-4444-555555555555"
LAT, LNG = 10.9108, -74.8186

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


class Params:
    def __init__(self, identificador, latitud=None, longitud=None,
                 combinada=None):
        self.identificador = identificador
        self.latitud = latitud
        self.longitud = longitud
        self.combinada = combinada


class HerrEquipo:
    nombre = "escribir_ubicacion_del_equipo"
    escribe_coordenada_equipo = True
    escribe_coordenada_servicio = False
    argumentos_fijos: dict = {}
    parametros_de_coordenada = Params("sn_onu", latitud="latitude",
                                      longitud="longitude")


class HerrServicio:
    nombre = "escribir_ubicacion_del_servicio"
    escribe_coordenada_equipo = False
    escribe_coordenada_servicio = True
    argumentos_fijos: dict = {}
    parametros_de_coordenada = Params("id_servicio", combinada="coordenadas")


class Config:
    def __init__(self, herramientas=None):
        self.herramientas = ([HerrEquipo(), HerrServicio()]
                             if herramientas is None else herramientas)
    variables_tenant: dict = {}


class Veredicto:
    def __init__(self, permitido=True):
        self.permitido = permitido
        self.estado = "activo" if permitido else "detenido"
        self.motivo = "" if permitido else "apagado a mano"


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
        #  LA FALLIDA, COMO LA TRATA LA TABLA REAL: no se reintenta salvo que
        #  quien llama lo pida. Si el andamio no modelara esto, la prueba del
        #  reintento pasaria por un stub permisivo y no por la regla que de
        #  verdad gobierna ('persistencia/db.py', reclamar_operacion_externa).
        if fila["estado"] == "fallida":
            if not reintentar_fallida:
                return {"decision": "fallida", "fila": fila}
            fila["estado"] = "ejecutando"
            fila["intentos"] += 1
            return {"decision": "ejecutar", "fila": fila, "reintento": True}
        return {"decision": "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        fila = self.filas.setdefault(clave, {"intentos": 1})
        fila["estado"] = estado
        fila["respuesta"] = respuesta


class Proveedor:
    """Anota cada llamada. `rompe_en` hace fallar a esa herramienta."""

    def __init__(self, rompe_en: str | None = None):
        self.llamadas: list[tuple[str, dict]] = []
        self.permisos: list = []
        self.rompe_en = rompe_en

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        self.llamadas.append((herramienta.nombre, dict(argumentos)))
        self.permisos.append(frontera.permiso_vigente())
        if self.rompe_en and herramienta.nombre == self.rompe_en:
            raise RuntimeError("el proveedor rechazo la escritura")
        return {"ok": True}

    @property
    def nombres(self) -> list[str]:
        return [n for n, _ in self.llamadas]


@contextlib.contextmanager
def escenario(registro, proveedor, permitido=True, interruptor_rompe=False):
    import nucleo.herramientas.http as ejecutor_http
    from nucleo.seguridad import interruptor

    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  interruptor.veredicto, interruptor.anotar_bloqueo,
                  ejecutor_http.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar

    def _veredicto(t):
        if interruptor_rompe:
            raise RuntimeError("la base no responde")
        return Veredicto(permitido)

    interruptor.veredicto = _veredicto
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


def guardar(config=None, actor="Laura Gomez", ident=None, lat=LAT, lng=LNG,
            origen=ORIGEN):
    return coord.guardar(
        config or Config(), TENANT, actor=actor,
        identificadores=ident if ident is not None
        else {"sn_onu": "HWTCA6FB5263", "id_servicio": "5832"},
        latitud=lat, longitud=lng, origen=origen)


# ---------------------------------------------------------------------------
seccion("1. las dos escrituras salen, EL EQUIPO PRIMERO")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.GUARDADA,
        f"queda guardada (estado={r.estado}, motivo={r.motivo})")
afirmar(proveedor.nombres == ["escribir_ubicacion_del_equipo",
                              "escribir_ubicacion_del_servicio"],
        f"el equipo PRIMERO y el servicio despues: {proveedor.nombres}")
afirmar(all(p is not None for p in proveedor.permisos),
        "las dos salieron con un permiso de la frontera abierto")
afirmar(len(registro.filas) == 2,
        f"DOS claves de idempotencia, una por destino: {len(registro.filas)}")
afirmar(len(set(registro.filas)) == 2, "y las dos claves son distintas")

# ---------------------------------------------------------------------------
seccion("2. cada proveedor recibe los nombres que DECLARA")
if len(proveedor.llamadas) == 2:
    _, args_equipo = proveedor.llamadas[0]
    _, args_serv = proveedor.llamadas[1]
    afirmar(args_equipo.get("latitude") == "10.910800"
            and args_equipo.get("longitude") == "-74.818600",
            f"el equipo: dos campos separados -> {args_equipo}")
    afirmar("coordenadas" not in args_equipo,
            "al equipo NO se le manda el campo combinado del otro sistema")
    afirmar(args_serv.get("coordenadas") == "10.910800,-74.818600",
            f"el servicio: un campo 'lat,lon' con coma y sin espacio -> {args_serv}")
    afirmar("latitude" not in args_serv,
            "al servicio NO se le mandan los dos campos del otro sistema")
    afirmar(args_equipo.get("sn_onu") == "HWTCA6FB5263"
            and args_serv.get("id_servicio") == "5832",
            "cada uno con SU identificador")

# ---------------------------------------------------------------------------
seccion("3. si el EQUIPO falla, el servicio NI SE INTENTA")
registro, proveedor = Registro(), Proveedor(
    rompe_en="escribir_ubicacion_del_equipo")
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.FALLO, f"la accion fallo (estado={r.estado})")
afirmar(proveedor.nombres == ["escribir_ubicacion_del_equipo"],
        f"UNA sola llamada, la del equipo: {proveedor.nombres}")
afirmar(not r.escribio_algo, "y no quedo nada escrito en ningun lado")

# ---------------------------------------------------------------------------
seccion("4. si falla el SERVICIO, es PARCIAL y el equipo no se repite")
registro, proveedor = Registro(), Proveedor(
    rompe_en="escribir_ubicacion_del_servicio")
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.PARCIAL,
        f"parcial, no fallo: lo escrito no se deshace (estado={r.estado})")
afirmar(r.escribio_algo, "el equipo si quedo escrito")

#  El reintento: con el MISMO origen, el equipo vuelve como 'repetida' y el
#  servicio se intenta de nuevo. Eso es lo que hace reintentable el parcial.
proveedor2 = Proveedor()
with escenario(registro, proveedor2):
    r2 = guardar()
afirmar(r2.estado == coord.GUARDADA,
        f"al reintentar queda completa (estado={r2.estado})")
afirmar(proveedor2.nombres == ["escribir_ubicacion_del_servicio"],
        f"solo se reintento EL QUE FALTABA: {proveedor2.nombres}")

# ---------------------------------------------------------------------------
seccion("5. lo que NO es una coordenada no llega al proveedor")
for etiqueta, lat, lng in (("0,0", 0, 0), ("fuera del planeta", 91.0, -74.8),
                           ("texto", "aca nomas", -74.8), ("vacio", None, None),
                           ("NaN", float("nan"), -74.8)):
    registro, proveedor = Registro(), Proveedor()
    with escenario(registro, proveedor):
        r = guardar(lat=lat, lng=lng)
    afirmar(r.estado == coord.COORDENADA_INVALIDA and not proveedor.llamadas,
            f"{etiqueta}: se rechaza y CERO llamadas al proveedor "
            f"({r.estado}, {len(proveedor.llamadas)} llamadas)")

# ---------------------------------------------------------------------------
seccion("6. el interruptor manda, y falla CERRADO")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor, permitido=False):
    r = guardar()
afirmar(r.estado == coord.BLOQUEADO_POR_INTERRUPTOR and not proveedor.llamadas,
        f"apagado: no se escribe nada ({r.estado}, {len(proveedor.llamadas)})")

registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor, interruptor_rompe=True):
    r = guardar()
afirmar(r.estado == coord.BLOQUEADO_POR_INTERRUPTOR and not proveedor.llamadas,
        "si NO SE PUEDE LEER el interruptor tampoco se escribe: fail-closed "
        f"({r.estado}, {len(proveedor.llamadas)})")

# ---------------------------------------------------------------------------
seccion("7. sin identificador no se inventa nada")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = guardar(ident={"id_servicio": "5832"})          # falta el del equipo
afirmar(r.estado == coord.FALTA_IDENTIFICADOR and not proveedor.llamadas,
        f"falta el del equipo: no se escribe nada ({r.estado}, "
        f"{len(proveedor.llamadas)} llamadas)")

# ---------------------------------------------------------------------------
seccion("8. un tenant sin herramientas no explota")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = guardar(config=Config(herramientas=[]))
afirmar(r.estado == coord.SIN_HERRAMIENTA and not proveedor.llamadas,
        f"lo dice y no escribe ({r.estado})")

# ---------------------------------------------------------------------------
print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO EN VERDE")
