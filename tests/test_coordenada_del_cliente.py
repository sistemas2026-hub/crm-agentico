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
                                 "respuesta": None, "huella": argumentos_hash}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        #  LA HUELLA SE COMPARA PRIMERO, COMO EN LA TABLA REAL (10/11/2026).
        #
        #  El andamio modelaba la regla de `fallida` y OMITIA esta, con un
        #  comentario que afirmaba fidelidad a `db.py`. Y es la que rompia la
        #  capacidad: `reclamar` compara `argumentos_hash` ANTES que
        #  `exitosa` y antes que `fallida`, asi que una clave fija con otra
        #  coordenada salia `CLAVE_REUTILIZADA` y el reintento no existia.
        #  Lo encontro una auditoria de frontera; las ocho secciones en verde
        #  no podian verlo porque reintentaban con la MISMA coordenada.
        if fila.get("huella") not in (None, argumentos_hash):
            return {"decision": "rechazada", "fila": fila,
                    "codigo": "CLAVE_REUTILIZADA"}
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
        #  EL ECO DEL PROVEEDOR, COMO ES DE VERDAD (10/11/2026). Antes esto
        #  devolvia {"ok": True} --un acuse corto-- y por eso las ocho
        #  secciones en verde no podian ver que ese cuerpo se guardaba entero
        #  en `operaciones_externas.respuesta`. Uno de los dos destinos es un
        #  PUT sobre el RECURSO DEL CLIENTE, y su serializer contesta la ficha.
        return {"id_servicio": "5832", "coordenadas": "10.910800,-74.818600",
                "cedula": "1.234.567-8", "password_servicio": "NO-DEBE-QUEDAR",
                "telefono": "3001234567"}

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
seccion("1. las dos escrituras salen, EL SERVICIO PRIMERO")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.GUARDADA,
        f"queda guardada (estado={r.estado}, motivo={r.motivo})")
#  EL SERVICIO PRIMERO: es el que manda (decision del usuario, 11/11/2026).
#  El equipo va despues y es el que puede faltar o fallar sin tumbar la accion.
afirmar(proveedor.nombres == ["escribir_ubicacion_del_servicio",
                              "escribir_ubicacion_del_equipo"],
        f"el servicio PRIMERO y el equipo despues: {proveedor.nombres}")
afirmar(all(p is not None for p in proveedor.permisos),
        "las dos salieron con un permiso de la frontera abierto")
afirmar(len(registro.filas) == 2,
        f"DOS claves de idempotencia, una por destino: {len(registro.filas)}")
afirmar(len(set(registro.filas)) == 2, "y las dos claves son distintas")

# ---------------------------------------------------------------------------
seccion("2. cada proveedor recibe los nombres que DECLARA")
if len(proveedor.llamadas) == 2:
    _, args_serv = proveedor.llamadas[0]
    _, args_equipo = proveedor.llamadas[1]
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
seccion("3. si el SERVICIO falla, el equipo NI SE INTENTA")
registro, proveedor = Registro(), Proveedor(
    rompe_en="escribir_ubicacion_del_servicio")
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.FALLO, f"la accion fallo (estado={r.estado})")
afirmar(proveedor.nombres == ["escribir_ubicacion_del_servicio"],
        f"UNA sola llamada, la del servicio: {proveedor.nombres}")
afirmar(not r.escribio_algo, "y no quedo nada escrito en ningun lado")

# ---------------------------------------------------------------------------
seccion("4. si falla el EQUIPO, es PARCIAL: el dato ya quedo donde importa")
registro, proveedor = Registro(), Proveedor(
    rompe_en="escribir_ubicacion_del_equipo")
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.PARCIAL,
        f"parcial, no fallo: lo escrito no se deshace (estado={r.estado})")
afirmar(r.escribio_algo, "el servicio si quedo escrito, que es el que manda")

#  El reintento: con el MISMO origen, el equipo vuelve como 'repetida' y el
#  servicio se intenta de nuevo. Eso es lo que hace reintentable el parcial.
proveedor2 = Proveedor()
with escenario(registro, proveedor2):
    r2 = guardar()
afirmar(r2.estado == coord.GUARDADA,
        f"con el MISMO punto, al reintentar queda completa (estado={r2.estado})")
afirmar(proveedor2.nombres == ["escribir_ubicacion_del_equipo"],
        f"y solo se reintento EL QUE FALTABA: {proveedor2.nombres}")

# ---------------------------------------------------------------------------
seccion("4b. el reintento CON OTRO PUNTO -- el caso de campo")
#  ESTE ES EL CASO REAL Y ES EL QUE ESTABA ROTO. El boton re-lee el GPS en cada
#  toque, y a 6 decimales (~11 cm) dos lecturas seguidas casi nunca coinciden.
#  Con la clave fija, el segundo toque salia CLAVE_REUTILIZADA y la orden
#  quedaba bloqueada PARA SIEMPRE --la fila exitosa no vence--. La seccion 4 no
#  podia verlo porque reintentaba con la misma coordenada.
registro, proveedor = Registro(), Proveedor(
    rompe_en="escribir_ubicacion_del_equipo")
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.PARCIAL, "el primer toque queda a medias")

proveedor3 = Proveedor()
with escenario(registro, proveedor3):
    #  El tecnico se corrio tres metros, que es lo que la propia app le pide
    #  cuando la precision es mala.
    r3 = guardar(lat=10.9108234, lng=-74.8186567)
afirmar(r3.estado == coord.GUARDADA,
        f"con OTRO punto el segundo toque TAMBIEN completa (estado={r3.estado}, "
        f"motivo={r3.motivo})")
afirmar("escribir_ubicacion_del_equipo" in proveedor3.nombres,
        f"y el que faltaba se escribe: {proveedor3.nombres}")

# ---------------------------------------------------------------------------
seccion("4b. el ECO DEL PROVEEDOR no queda guardado")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = guardar()
afirmar(r.estado == coord.GUARDADA, "la escritura salio bien")
guardado = repr(sorted(registro.filas.items()))
#  EL EFECTO: lo que queda en la fila de idempotencia. Ese valor se escribe
#  TAL CUAL en la base, en claro y sin truncar, y por este camino no corre
#  ninguna lista blanca --vive en el bucle del modelo, y esta ruta no pasa por
#  ahi--. Afirmar "no se loguea" no alcanzaba: la fuga no era el log.
for prohibido, que_es in (("10.910800", "la coordenada"),
                          ("NO-DEBE-QUEDAR", "una contrasena del servicio"),
                          ("1.234.567-8", "la cedula"),
                          ("3001234567", "el telefono")):
    afirmar(prohibido not in guardado,
            f"{que_es} del eco del proveedor NO queda en la fila guardada")
afirmar("escrita" in guardado,
        "y si queda un acuse, que es lo unico que este flujo necesita")

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
seccion("7. un destino sin identificador NO APLICA, y no frena al otro")
#  LA PRUEBA ANTERIOR BENDECIA EL DEFECTO. Afirmaba «falta el del equipo: no se
#  escribe nada», y eso es justo lo que rompio la primera prueba de campo
#  (11/11/2026): la OT #255 no tiene serial de ONU --la ficha se congela al
#  despachar y el equipo no estaba cargado-- y si tiene servicio. El motor
#  cortaba en el equipo y la casa quedaba sin ubicar en LOS DOS lados,
#  pudiendo escribir en uno. 400 al telefono, y el tecnico leyendo «proba de
#  nuevo en un momento» para siempre.
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    #  EL CASO REAL DE LA PRIMERA PRUEBA DE CAMPO: la OT #255 no tiene serial
    #  de ONU y si tiene servicio. Es justo el que manda, asi que la casa
    #  queda ubicada igual.
    r = guardar(ident={"id_servicio": "5832"})          # sin el del equipo
afirmar(r.estado == coord.GUARDADA,
        f"se escribe donde SI se puede (estado={r.estado}, motivo={r.motivo})")
afirmar(proveedor.nombres == ["escribir_ubicacion_del_servicio"],
        f"solo el destino que aplica: {proveedor.nombres}")
afirmar(any(d.no_aplica for d in r.destinos),
        "y el otro queda marcado como que no aplica, no como fallado")

#  Y AL REVES: si no se puede intentar NINGUNO, eso si es un problema.
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = guardar(ident={})
afirmar(r.estado == coord.FALTA_IDENTIFICADOR and not proveedor.llamadas,
        f"sin ningun identificador no se escribe nada ({r.estado}, "
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
