# -*- coding: utf-8 -*-
"""
================================================================================
 LA NOTA DE CAMPO EN EL TICKET DEL ISP  --  06/11/2026
================================================================================
Guarda de `nucleo/seguimiento/nota_en_el_ticket.py`.

QUE AFIRMA, Y POR QUE ASI
-------------------------
No que el modulo exista. Dos cosas que se pueden romper sin que nada avise:

  1. **La clave idempotente cuenta el momento y la vuelta.** Un reporte, una
     devolucion y el reporte siguiente son TRES escrituras legitimas sobre el
     mismo ticket. Si la clave fuera solo la orden --como en el cierre, donde
     una orden se cierra una vez y nada mas-- la segunda y la tercera se
     descartarian EN SILENCIO con "operacion ya ejecutada", y el ticket se
     quedaria con el primer reporte para siempre. Ese es el defecto que no se
     ve: no hay error, no hay log, el ticket simplemente no cambia.

  2. **La exencion abre esta puerta y ninguna otra.** Sin la declaracion del
     tenant no sale; sin la capacidad en la herramienta no sale; y no exime de
     las demas compuertas.

Mutaciones que esta guarda mata (medidas el 06/11/2026):
  · sacar la `vuelta` de la clave        -> rojo en B1
  · sacar el `momento` de la clave       -> rojo en B2
  · aceptar un momento libre             -> rojo en C1
  · dejar pasar sin la declaracion       -> rojo en D1
  · no exigir la capacidad               -> rojo en D2
  · escribir antes del interruptor       -> rojo en E1

LO QUE NO PRUEBA: que WispHub escriba la nota. Eso esta del otro lado de un
HTTP y aca se usa un proveedor falso. Lo que se mide es que la llamada se
arme, se autorice y se recuente bien -- no el contrato del tercero.
================================================================================
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db as persistencia               # noqa: E402
from nucleo.seguimiento import nota_en_el_ticket as nota         # noqa: E402
from nucleo.seguridad import frontera                            # noqa: E402

TENANT = "tenant-de-prueba"
ORDEN = "11111111-2222-3333-4444-555555555555"
TICKET = "94721"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str, dato: str = "") -> None:
    print(("  OK    " if condicion else "  FALLA ") + que
          + (f"  [{dato}]" if dato and not condicion else ""))
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


class Herramienta:
    """La que anota: con su capacidad y la exencion declarada por el tenant."""

    def __init__(self, *, capacidad=True, declara=True, aprobacion=True):
        self.nombre = "responder_ticket_operativo"
        self.responde_ticket_operativo = capacidad
        self.aprobacion_humana = aprobacion
        self.aprobacion_humana_salvo = (
            [frontera.NOTA_DE_CAMPO_EN_EL_TICKET] if declara else [])
        #  En Progreso: el estado lo fija la herramienta, no quien llama.
        self.argumentos_fijos = {"ticket-estado": "2", "ticket-prioridad": "2"}
        self.irreversible = False


class Config:
    def __init__(self, herramientas=None):
        self.herramientas = ([Herramienta()] if herramientas is None
                             else herramientas)

    variables_tenant: dict = {}


class Registro:
    """Como `persistencia.reclamar_operacion_externa`, en memoria.

    `filas` es lo que hace medible la parte dificil: las CLAVES que se
    reclamaron. Afirmar sobre ellas es afirmar sobre el recuento, que es lo
    que decide si una escritura legitima se descarta.
    """

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

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        self.llamadas.append(dict(argumentos))
        return {"id_ticket": argumentos.get("id_ticket")}


class Compuertas:
    """Las cuatro compuertas de `frontera.autonoma`, sustituidas.

    Hace falta porque el techo y Autonomia 2 se leen de Postgres y, sin base,
    fallan CERRADO -- que es la conducta correcta y justamente por eso tapa lo
    que esta prueba quiere medir. Calcada de `test_cierre_por_validacion.py`.
    """

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


@contextlib.contextmanager
def escenario(registro, proveedor, **compuertas):
    import nucleo.herramientas.http as ejecutor_http

    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  ejecutor_http.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar
    ejecutor_http.ejecutar = proveedor.ejecutar
    try:
        with Compuertas(**compuertas):
            #  Que el andamio no deje un permiso abierto NO es decorativo: si
            #  lo dejara, el caso siguiente saldria por el permiso del
            #  anterior y toda la seccion D mediria otra cosa.
            afirmar(frontera.permiso_vigente() is None,
                    "el andamio NO deja ningun permiso abierto")
            yield
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa,
         ejecutor_http.ejecutar) = originales


def anotar(momento=nota.REPORTE_DEL_TECNICO, vuelta=1, config=None,
           texto="Reporte de campo de la OT #7001.", actor=""):
    return nota.anotar(config or Config(), TENANT, orden_id=ORDEN,
                       ticket=TICKET, texto=texto, momento=momento,
                       vuelta=vuelta, actor=actor)


# =============================================================================
seccion("A: la nota sale, y firmada por quien corresponde")
# =============================================================================
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    r = anotar(actor="Carlos Perez")
    afirmar(r.anotada, "A1. el reporte del tecnico queda anotado", r.codigo)
    afirmar(len(prov.llamadas) == 1, "A2. y llega UNA sola llamada al ISP",
            str(len(prov.llamadas)))
    arg = prov.llamadas[0] if prov.llamadas else {}
    afirmar(arg.get("id_ticket") == TICKET, "A3. con el ticket que se pidio")
    afirmar("Carlos Perez" in str(arg.get("respuesta", "")),
            "A4. firmada con el nombre del tecnico", str(arg.get("respuesta"))[:70])
    #  El estado sale del catalogo, no de quien llama: si esto cambiara, una
    #  nota se volveria un cierre sin la exencion del cierre.
    afirmar(arg.get("ticket-estado") == "2",
            "A5. y el ticket queda En Progreso, no cerrado",
            str(arg.get("ticket-estado")))

reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    anotar(momento=nota.DEVUELTA_AL_TECNICO, actor="Carlos Perez",
           texto="La OT #7001 vuelve a campo para corregir (vuelta 1).")
    arg = prov.llamadas[0] if prov.llamadas else {}
    firmada = str(arg.get("respuesta", ""))
    afirmar(nota.FIRMA_DEL_SUPERVISOR in firmada,
            "A6. la devolucion la firma el Supervisor", firmada[:70])
    afirmar("Carlos Perez" not in firmada,
            "A7. y NO lleva el nombre de quien apreto el boton", firmada[:70])

# =============================================================================
seccion("B: la clave cuenta el momento y la vuelta  (el defecto invisible)")
# =============================================================================
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    a = anotar(vuelta=1)
    b = anotar(vuelta=2)
    afirmar(a.anotada and b.anotada,
            "B1. el reporte de la vuelta 2 TAMBIEN se anota",
            f"{a.codigo}/{b.codigo}")
    afirmar(len(prov.llamadas) == 2,
            "B1b. y el ISP recibe las dos", str(len(prov.llamadas)))
    afirmar(len(reg.filas) == 2,
            "B1c. con claves distintas", str(sorted(reg.filas)))

reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    anotar(momento=nota.REPORTE_DEL_TECNICO, vuelta=1)
    anotar(momento=nota.DEVUELTA_AL_TECNICO, vuelta=1)
    afirmar(len(prov.llamadas) == 2,
            "B2. reporte y devolucion de la MISMA vuelta no se pisan",
            str(len(prov.llamadas)))
    afirmar(len(reg.filas) == 2, "B2b. con claves distintas",
            str(sorted(reg.filas)))

reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    a = anotar(vuelta=1)
    b = anotar(vuelta=1)
    afirmar(len(prov.llamadas) == 1,
            "B3. el MISMO momento y vuelta no se publica dos veces",
            str(len(prov.llamadas)))
    afirmar(b.anotada, "B3b. y el segundo intento reporta el efecto como hecho",
            b.codigo)

# =============================================================================
seccion("C: lo que no se puede inventar")
# =============================================================================
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    r = anotar(momento="lo_que_se_me_ocurra")
    afirmar(not r.anotada and r.codigo == nota.MOMENTO_DESCONOCIDO,
            "C1. un momento que el codigo no declara NO sale", r.codigo)
    afirmar(not prov.llamadas,
            "C1b. y no llega nada al ISP", str(len(prov.llamadas)))
    afirmar(not reg.filas,
            "C1c. ni se quema una clave", str(sorted(reg.filas)))

    r = anotar(vuelta=None)
    afirmar(not r.anotada and r.codigo == nota.FALTAN_DATOS,
            "C2. sin vuelta NO sale", r.codigo)
    afirmar(not prov.llamadas, "C2b. y no llega nada al ISP")

    r = anotar(texto="   ")
    afirmar(not r.anotada and r.codigo == nota.FALTAN_DATOS,
            "C3. sin texto NO sale", r.codigo)

# =============================================================================
seccion("C4: un momento raro nunca sale como excepcion cruda")
# =============================================================================
#  LO ENCONTRO UNA MUTACION (06/11/2026). Al desactivar el chequeo de
#  `momento`, `_firma_de` levantaba `KeyError` antes del `try` del modulo: el
#  motor habria contestado 500 en vez de 400 con su motivo. La validacion que
#  lo hacia imposible vive en OTRA funcion, asi que esto afirma la invariante
#  donde se rompe y no donde se cumple.
try:
    _firma = nota._firma_de("un_momento_que_nadie_declaro", "Carlos Perez")
    afirmar(bool(_firma), "C4. firmar un momento desconocido no levanta nada",
            repr(_firma))
    afirmar("Carlos Perez" not in _firma,
            "C4b. y no le atribuye el reporte a una persona", _firma)
except Exception as e:                                           # noqa: BLE001
    afirmar(False, "C4. firmar un momento desconocido no levanta nada",
            type(e).__name__)


# =============================================================================
seccion("D: la exencion tiene que estar declarada Y atada a la capacidad")
# =============================================================================
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    r = anotar(config=Config([Herramienta(declara=False)]))
    afirmar(not r.anotada and r.codigo == nota.NO_AUTORIZADA,
            "D1. sin la declaracion del tenant NO sale", r.codigo)
    afirmar(not prov.llamadas, "D1b. y no llega nada al ISP")
    #  Que no queme la clave es la mitad que importa: si la quemara, la nota
    #  no se podria reintentar nunca despues de arreglar la config.
    afirmar(not reg.filas, "D1c. ni se quema la clave del intento",
            str(sorted(reg.filas)))

reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    #  Declara la exencion pero NO es la herramienta que anota: el
    #  emparejamiento lo sostiene una capacidad del catalogo, no el buen
    #  criterio de quien lo edita.
    impostora = Herramienta(capacidad=False)
    impostora.nombre = "otra_escritura_cualquiera"
    r = anotar(config=Config([impostora]))
    afirmar(not r.anotada, "D2. una herramienta sin la capacidad NO anota",
            r.codigo)
    afirmar(r.codigo == nota.SIN_HERRAMIENTA,
            "D2b. y se dice que el tenant no declara ninguna", r.codigo)

reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    #  Sin 'aprobacion_humana' no hay nada que eximir, y la nota sale igual:
    #  una guarda que solo sabe negar no distingue "bien atada" de "nunca pasa".
    r = anotar(config=Config([Herramienta(aprobacion=False, declara=False)]))
    afirmar(r.anotada, "D3. sin la marca puesta, la nota sale sin exencion",
            r.codigo)

# =============================================================================
seccion("E: la exencion NO abre las otras compuertas")
# =============================================================================
for nombre, apagada in (("E1. el interruptor", "interruptor"),
                        ("E2. la etapa de Autonomia 2", "etapa"),
                        ("E3. la autorizacion granular", "granular")):
    reg, prov = Registro(), Proveedor()
    with escenario(reg, prov, **{apagada: False}):
        r = anotar()
        afirmar(not r.anotada, f"{nombre} cerrada -> la nota NO sale", r.codigo)
        afirmar(not prov.llamadas, f"{nombre} cerrada -> nada llega al ISP")
        #  Y no quema la clave: una compuerta cerrada hoy no puede dejar la
        #  nota sin poder reintentarse manana.
        afirmar(not reg.filas, f"{nombre} cerrada -> no se quema la clave",
                str(sorted(reg.filas)))

# =============================================================================
seccion("G: lo que la auditoria de frontera encontro el 06/11/2026")
# =============================================================================
#  Los tres casos de esta seccion nacieron de hallazgos del
#  `auditor-de-frontera`, cada uno medido con una sonda antes de arreglarse.
#  Van juntos porque comparten el mismo error de fondo: la copia de
#  `cierre_por_validacion` perdio sus distinciones y se quedo con la rama
#  optimista.

# --- G1 (H1): la base no contesta -> el efecto NO ocurrio ---------------
class RegistroCaido(Registro):
    """Como la base cuando no contesta: `reclamar` revienta.

    `idempotencia.ejecutar` lo atrapa y devuelve `ejecutada=False` con
    OPERACION_SIN_REGISTRO. Antes del 06/11/2026 eso salia de aca como
    'ya_anotada' -> anotada=True -> HTTP 200, con CERO llamadas al ISP.
    """

    def reclamar(self, *a, **k):
        raise RuntimeError("la base no contesta")


reg, prov = RegistroCaido(), Proveedor()
with escenario(reg, prov):
    r = anotar()
    afirmar(not r.anotada,
            "G1. con la base caida la nota NO se declara anotada", r.codigo)
    afirmar(r.codigo == nota.NO_EJECUTADA,
            "G1b. y el codigo dice que no se ejecuto", r.codigo)
    #  La mitad que importa: el efecto no ocurrio, asi que nada puede decir
    #  que si. Esta afirmacion es la que convierte el caso en una guarda y no
    #  en una prueba de la forma del codigo.
    afirmar(not prov.llamadas,
            "G1c. y de hecho NADA llego al ISP", str(len(prov.llamadas)))

# --- G2 (H4): un timeout no es un fallo --------------------------------
class ProveedorQueSeCuelga(Proveedor):
    def ejecutar(self, *a, **k):
        import requests

        raise requests.exceptions.Timeout("se corto despues de mandar")


reg, prov = Registro(), ProveedorQueSeCuelga()
with escenario(reg, prov):
    r = anotar()
    afirmar(r.codigo == nota.INCIERTO,
            "G2. un timeout del ISP sale como INCIERTO, no como FALLO",
            r.codigo)
    afirmar(not r.anotada, "G2b. y no se declara anotada", r.codigo)
    #  Por que importa: sobre 'fallo' alguien reintentaria y publicaria dos
    #  veces; sobre 'incierto' hay que ir a mirar el sistema del ISP.
    afirmar(r.codigo != nota.FALLO,
            "G2c. decir 'fallo' afirmaria que no paso nada, y no se sabe")

# --- G3 (H5): la vuelta se normaliza, y lo que no es entero se rechaza --
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    #  Las cinco formas de escribir la MISMA vuelta tienen que producir UNA
    #  sola escritura. Antes producian hasta cinco claves distintas.
    for forma in (1, "1", " 1 ", 1.0, "01"):
        anotar(vuelta=forma)
    afirmar(len(prov.llamadas) == 1,
            "G3. 1, '1', ' 1 ', 1.0 y '01' son la MISMA vuelta",
            f"{len(prov.llamadas)} llamadas, claves={sorted(reg.filas)}")
    afirmar(len(reg.filas) == 1, "G3b. y una sola clave",
            str(sorted(reg.filas)))

reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    for malo in ("x", "", "1,5", None, True, [1]):
        r = anotar(vuelta=malo)
        afirmar(not r.anotada,
                f"G3c. vuelta={malo!r} NO sale", r.codigo)
    afirmar(not prov.llamadas,
            "G3d. y nada de eso llego al ISP", str(len(prov.llamadas)))
    afirmar(not reg.filas, "G3e. ni quemo una clave", str(sorted(reg.filas)))


# =============================================================================
seccion("H: contra el CATALOGO REAL, no contra el doble de esta prueba")
# =============================================================================
#  H7/H2 de la auditoria: hasta aca todo se mide contra `Herramienta`, que
#  esta prueba construye. Eso no dice nada del catalogo desplegado -- y lo
#  que decide si esto funciona en produccion es el catalogo.
import yaml                                                        # noqa: E402

from nucleo.config.schema import TenantConfig                       # noqa: E402

_doc = yaml.safe_load(
    (RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
_cfg = TenantConfig(**_doc)
_real = nota._herramienta_que_anota(_cfg)

afirmar(_real is not None,
        "H1. el catalogo real declara una herramienta que anota")
if _real is not None:
    afirmar(frontera.NOTA_DE_CAMPO_EN_EL_TICKET
            in (_real.aprobacion_humana_salvo or []),
            "H2. y declara la exencion de la nota",
            str(_real.aprobacion_humana_salvo))
    afirmar(frontera.exime_la_aprobacion(_real,
                                         frontera.NOTA_DE_CAMPO_EN_EL_TICKET),
            "H3. y la frontera la exime de verdad")
    #  El techo: la leccion H4 del 31/10 aplicada a esta herramienta.
    from nucleo.seguridad import techo as _techos                   # noqa: E402

    afirmar(_techos.nivel_requerido_de(_real) == 3,
            "H4. y exige nivel 3, como el cierre",
            str(_techos.nivel_requerido_de(_real)))
    #  Y que no sea un cierre disfrazado.
    afirmar(not nota._pide_lo_mismo_que_el_cierre(_cfg, _real),
            "H5. y NO le pide al proveedor lo mismo que la de cierre",
            str(dict(_real.argumentos_fijos or {})))

#  Y el cierre disfrazado, con el catalogo real de testigo: se construye una
#  herramienta que copia los argumentos de la de cierre y se exige que NO
#  salga. Sin este caso, H5 pasaria por como esta hoy el YAML y no por la
#  regla.
_cierre_real = next((h for h in _cfg.herramientas
                     if getattr(h, "cierra_ticket_operativo", False)), None)
if _cierre_real is not None:
    class Disfrazada(Herramienta):
        def __init__(self):
            super().__init__()
            self.argumentos_fijos = dict(_cierre_real.argumentos_fijos or {})

    reg, prov = Registro(), Proveedor()
    _disfrazada = Disfrazada()
    with escenario(reg, prov):
        r = nota.anotar(Config([_disfrazada, _cierre_real]), TENANT,
                        orden_id=ORDEN, ticket=TICKET, texto="t",
                        momento=nota.REPORTE_DEL_TECNICO, vuelta=1)
        afirmar(r.codigo == nota.ANOTARIA_UN_CIERRE,
                "H6. una herramienta de notas con los argumentos del cierre "
                "NO sale", r.codigo)
        afirmar(not prov.llamadas, "H6b. y nada llega al ISP")


# =============================================================================
seccion("F: el andamio no se queda con nada abierto")
# =============================================================================
afirmar(frontera.permiso_vigente() is None,
        "F1. al terminar no hay ningun permiso vigente")

# =============================================================================
print("\n" + "=" * 72)
if _fallos:
    print(f" {len(_fallos)} FALLAS:")
    for f in _fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
