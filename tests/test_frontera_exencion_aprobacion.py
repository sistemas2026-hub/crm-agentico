# -*- coding: utf-8 -*-
"""
================================================================================
 LA EXENCION DE 'aprobacion_humana' ABRE UNA PUERTA, NO LA PARED  --  31/10/2026
================================================================================

    py -3.13 tests/test_frontera_exencion_aprobacion.py

QUE SE CAMBIO Y POR QUE
-----------------------
'cerrar_ticket_operativo' declara 'aprobacion_humana' desde M06-E (22/09/2026,
no se midio si WispHub le avisa al cliente). El 31/10/2026 el usuario decidio
que para el cierre de una orden de campo YA REVISADA eso no aplica -- la misma
decision que habia tomado el 13/10 para la puerta humana y que nunca se habia
extendido al Supervisor.

Se podia resolver quitandole la marca a la herramienta. Habria sido un agujero:
el rol 'soporte' la tiene en 'roles_permitidos', asi que el modelo podria
pedirla en una conversacion, y '/interno/herramienta' la aceptaria de cualquier
servicio con token. En vez de eso se agrego una exencion CON NOMBRE, que exige
dos llaves -- el codigo la declara en 'frontera.EXENCIONES' y el tenant la
nombra en 'aprobacion_humana_salvo' de ESA herramienta.

QUE SE AFIRMA, Y POR QUE ASI
-----------------------------
Sobre el EFECTO de 'frontera.exigir', que es el ultimo metro y donde vive el
control: si deja pasar o si levanta, y CON QUE codigo. Una prueba que afirmara
que el campo 'aprobacion_humana_salvo' existe se veria igual de verde con la
compuerta invertida -- es exactamente el falso verde que CLAUDE.md §6 describe.

El caso que importa (A) usa la HERRAMIENTA REAL del YAML del tenant, no una
inventada: el 30/10/2026 las pruebas de este mismo camino no vieron que la
frontera lo frenaba justamente porque sustituian lo real por un doble.

Los casos que tienen que seguir bloqueados se corren con todo lo demas ABIERTO,
para que no haya duda de quien los freno. Y los de las OTRAS compuertas se
corren CON la exencion puesta: si se hubiera escrito como un bypass general,
pasarian y esta prueba se pondria roja.

NO SE LLAMA A NINGUNA API NI AL MODELO.
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml                                                      # noqa: E402

from nucleo.config.schema import Herramienta, TenantConfig       # noqa: E402
from nucleo.seguridad import frontera                            # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


class _V:
    """Un veredicto, como el que devuelven interruptor/techo/autonomia2."""

    def __init__(self, permitido, codigo="", motivo=""):
        self.permitido, self.codigo, self.motivo = permitido, codigo, motivo
        self.estado, self.nivel_efectivo, self.autorizacion_id = codigo, 3, ""
        self.techo, self.requerido = 3, 3


class Banco:
    """Sustituye las compuertas de ARRIBA y captura la bitacora.

    Todo abierto por defecto a proposito: asi, lo que frene en cada caso es la
    compuerta que el caso esta mirando y no otra.
    """

    def __init__(self, *, interruptor=True, techo=True, etapa=True, granular=True):
        self.cfg = dict(interruptor=interruptor, techo=techo, etapa=etapa,
                        granular=granular)
        self.bitacora: list[dict] = []

    def __enter__(self):
        self._orig = {
            "interruptor": frontera.interruptor.veredicto,
            "techo": frontera.techos.veredicto,
            "etapa": frontera.autonomia2.veredicto,
            "granular": frontera.autorizacion.veredicto,
            "_bitacora": frontera._bitacora,
            "_anotar": frontera._anotar,
        }
        c = self.cfg
        frontera.interruptor.veredicto = lambda t: _V(
            c["interruptor"], "activo" if c["interruptor"] else "detenido", "x")
        frontera.techos.veredicto = lambda t, n: _V(
            c["techo"], "ok" if c["techo"] else "TECHO_INSUFICIENTE", "x")
        frontera.autonomia2.veredicto = lambda *a, **k: _V(
            c["etapa"], "ok" if c["etapa"] else "AUTONOMIA_2_NO_ACTIVA", "x")
        frontera.autorizacion.veredicto = lambda t, h, **k: _V(
            c["granular"], "ok" if c["granular"] else "HERRAMIENTA_SIN_AUTORIZACION",
            "x")
        frontera._bitacora = lambda *a, **k: self.bitacora.append({"a": a, "kw": k})
        frontera._anotar = lambda *a, **k: None
        return self

    def __exit__(self, *e):
        frontera.interruptor.veredicto = self._orig["interruptor"]
        frontera.techos.veredicto = self._orig["techo"]
        frontera.autonomia2.veredicto = self._orig["etapa"]
        frontera.autorizacion.veredicto = self._orig["granular"]
        frontera._bitacora = self._orig["_bitacora"]
        frontera._anotar = self._orig["_anotar"]
        return False


def hasta_el_ultimo_metro(herr, *, exencion="", banco_kw=None, argumentos=None):
    """Abre el permiso y llega al ULTIMO METRO, como el ejecutor real.

    Devuelve (paso, codigo, banco). 'paso' solo es True si 'exigir' devolvio
    permiso: abrir la puerta no alcanza, que es justo el error que esta
    exencion podria haber introducido.
    """
    with Banco(**(banco_kw or {})) as b:
        try:
            with frontera.autonoma("rapilink", herr.nombre, origen="orden:1",
                                   actor="supervisor", nivel_requerido=3,
                                   efecto_externo=True, exencion=exencion):
                frontera.exigir(herr, "rapilink", argumentos or {"x": 1})
            return True, "", b
        except frontera.AccionExternaNoAutorizada as e:
            return False, e.codigo, b


def herramienta(nombre, **kw):
    base = dict(nombre=nombre, tipo="http", roles_permitidos=["soporte"],
                metodo="POST", endpoint="/x/", base_url="https://api.wisphub.io",
                solo_lectura=False, requiere_confirmacion=True)
    base.update(kw)
    return Herramienta(**base)


print("=" * 72)
print(" LA EXENCION ABRE UNA PUERTA, NO LA PARED  (sin red, sin modelo)")
print("=" * 72)

# =============================================================================
print("\n-- A: la herramienta REAL del tenant, por el camino del Supervisor --")
# =============================================================================
#  Nada de dobles aca: es la que esta en tenants/rapilink.config.yaml, cargada
#  y validada por el mismo schema que usa produccion.
datos = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(
    encoding="utf-8"))
config = TenantConfig.model_validate(datos)
REAL = next(h for h in config.herramientas if h.nombre == "cerrar_ticket_operativo")

comprobar("A0. la real sigue declarando aprobacion_humana",
          REAL.aprobacion_humana is True,
          "si esto se apago, la exencion dejo de ser lo que dice ser")

paso, codigo, banco = hasta_el_ultimo_metro(
    REAL, exencion=frontera.CIERRE_DE_ORDEN_REVISADA)
comprobar("A1. CON la exencion, el ultimo metro la deja salir", paso,
          f"codigo={codigo}")

anotadas = [x for x in banco.bitacora if "aprobacion_humana_exenta" in x["a"]]
comprobar("A2. y queda anotada en la bitacora, no en silencio",
          len(anotadas) == 1, f"anotaciones={len(anotadas)}")
comprobar("A3. anotada como PERMITIDA, no como bloqueo",
          bool(anotadas) and anotadas[0]["kw"].get("decision") == "permitida",
          str(anotadas[0]["kw"] if anotadas else None))

# =============================================================================
print("\n-- B: el mismo permiso autonomo SIN exencion sigue frenado --")
# =============================================================================
#  Es el camino de la conversacion y el del reloj: abren 'autonoma()' sin
#  pedir ninguna exencion. Todo lo demas esta abierto, asi que lo unico que
#  puede frenarlos es la quinta compuerta.
paso, codigo, _ = hasta_el_ultimo_metro(REAL)
comprobar("B1. sin exencion NO sale", not paso)
comprobar("B2. y el codigo es el de siempre",
          codigo == frontera.APROBACION_REQUERIDA, codigo)

# =============================================================================
print("\n-- C: la exencion no se contagia a otra herramienta --")
# =============================================================================
#  'responder_ticket_operativo' tiene la misma marca y NO declara la exencion.
#  Un permiso con la exencion puesta no tiene que alcanzarle.
OTRA = next(h for h in config.herramientas
            if h.nombre == "responder_ticket_operativo")
comprobar("C0. la otra tambien declara aprobacion_humana",
          OTRA.aprobacion_humana is True)
comprobar("C1. y NO declara la exencion",
          not OTRA.aprobacion_humana_salvo, str(OTRA.aprobacion_humana_salvo))
paso, codigo, _ = hasta_el_ultimo_metro(
    OTRA, exencion=frontera.CIERRE_DE_ORDEN_REVISADA)
comprobar("C2. con la exencion puesta, la otra NO sale", not paso)
comprobar("C3. con el codigo de aprobacion",
          codigo == frontera.APROBACION_REQUERIDA, codigo)

# =============================================================================
print("\n-- C2: la exencion vale para SU herramienta, no para el bloque --")
# =============================================================================
#  Auditoria de frontera 31/10/2026 (H2), medido con una sonda: el permiso se
#  abria sin 'herramienta', asi que una SEGUNDA escritura dentro del mismo
#  'with' salia eximida. Hoy no hay dos efectos ahi adentro; el dia que los
#  haya, esto lo frena en vez de descubrirse en produccion.
#
#  Y la segunda llave: una herramienta que declare el salvo en el YAML pero
#  que NO sea la que cierra tickets tampoco se exime -- el emparejamiento lo
#  sostiene una capacidad del catalogo, no el buen criterio de quien lo edita.
IMPOSTORA = herramienta("otra_escritura_cualquiera", aprobacion_humana=True,
                        aprobacion_humana_salvo=[frontera.CIERRE_DE_ORDEN_REVISADA])
comprobar("C2a. una herramienta sin 'cierra_ticket_operativo' no se exime",
          not frontera.exime_la_aprobacion(IMPOSTORA,
                                           frontera.CIERRE_DE_ORDEN_REVISADA))
paso, codigo, _ = hasta_el_ultimo_metro(
    IMPOSTORA, exencion=frontera.CIERRE_DE_ORDEN_REVISADA)
comprobar("C2b. y por el ultimo metro no sale", not paso)

#  El permiso se abre para la REAL y adentro se intenta otra: no sale.
with Banco() as _b:
    try:
        with frontera.autonoma("rapilink", REAL.nombre, origen="orden:1",
                               actor="supervisor", nivel_requerido=3,
                               efecto_externo=True,
                               exencion=frontera.CIERRE_DE_ORDEN_REVISADA):
            frontera.exigir(OTRA_CON_SALVO := REAL.model_copy(
                update={"nombre": "cerrar_ticket_operativo_estado"}),
                "rapilink", {"x": 1})
        comprobar("C2c. una segunda herramienta dentro del mismo with NO sale",
                  False, "salio")
    except frontera.AccionExternaNoAutorizada as e:
        comprobar("C2c. una segunda herramienta dentro del mismo with NO sale",
                  e.codigo == frontera.APROBACION_REQUERIDA, e.codigo)

# =============================================================================
print("\n-- D: un nombre de exencion que el codigo no conoce RECHAZA --")
# =============================================================================
#  Degradarse en silencio a "sin exencion" seria peor: el sintoma seria
#  APROBACION_HUMANA_REQUERIDA y nadie buscaria el typo.
paso, codigo, _ = hasta_el_ultimo_metro(REAL, exencion="cierre_de_orden_revisad")
comprobar("D1. un typo en el nombre no deja salir", not paso)
comprobar("D2. y lo dice con su propio codigo",
          codigo == frontera.EXENCION_DESCONOCIDA, codigo)

# =============================================================================
print("\n-- E: la exencion NO abre ninguna de las otras compuertas --")
# =============================================================================
#  Cada caso corre CON la exencion puesta y UNA compuerta cerrada. Si la
#  exencion se hubiera escrito como un bypass general, estos pasarian.
for etiqueta, kw in (
        ("el interruptor detenido", {"interruptor": False}),
        ("el techo insuficiente", {"techo": False}),
        ("la etapa de Autonomia 2 apagada", {"etapa": False}),
        ("la autorizacion granular revocada", {"granular": False})):
    paso, codigo, _ = hasta_el_ultimo_metro(
        REAL, exencion=frontera.CIERRE_DE_ORDEN_REVISADA, banco_kw=kw)
    comprobar(f"E. con {etiqueta}, NO sale", not paso, f"codigo={codigo}")

# =============================================================================
print("\n-- F: una irreversible no se exime ni declarandolo --")
# =============================================================================
#  Las irreversibles salen SOLO por frontera.critica(). Que una empresa
#  escriba la exencion en una de ellas no puede cambiarlo.
IRREV = herramienta("reiniciar_ont_falsa", irreversible=True,
                    aprobacion_humana=True,
                    aprobacion_humana_salvo=[frontera.CIERRE_DE_ORDEN_REVISADA])
paso, codigo, _ = hasta_el_ultimo_metro(
    IRREV, exencion=frontera.CIERRE_DE_ORDEN_REVISADA)
comprobar("F1. una irreversible con la exencion NO sale", not paso)
comprobar("F2. y la frena la regla de las irreversibles",
          codigo == frontera.IRREVERSIBLE_SIN_APROBACION, codigo)

# =============================================================================
print("\n-- G: la puerta humana no cambio --")
# =============================================================================
#  'humana()' nunca miro 'aprobacion_humana' y no tiene que empezar ahora:
#  una persona identificada que aprueba una accion concreta ya es la
#  aprobacion que la marca pide.
try:
    with Banco():
        with frontera.humana("rapilink", REAL.nombre, actor="Ana",
                             evidencia="orden_validada:1"):
            frontera.exigir(REAL, "rapilink", {"x": 1})
    comprobar("G1. una persona sigue pudiendo cerrar el ticket", True)
except frontera.AccionExternaNoAutorizada as e:
    comprobar("G1. una persona sigue pudiendo cerrar el ticket", False, e.codigo)

# =============================================================================
print("\n-- H: el schema rechaza lo que no se puede cumplir --")
# =============================================================================
#  Las dos contradicciones tumban el archivo al CARGARLO, no en produccion.
try:
    herramienta("inventada", aprobacion_humana=True,
                aprobacion_humana_salvo=["no_existe_esta_exencion"])
    comprobar("H1. un nombre inexistente no carga", False, "cargo igual")
except Exception as e:                                            # noqa: BLE001
    comprobar("H1. un nombre inexistente no carga",
              "no existen en" in str(e) or "EXENCIONES" in str(e), str(e)[:120])

try:
    herramienta("inventada2", aprobacion_humana=False,
                aprobacion_humana_salvo=[frontera.CIERRE_DE_ORDEN_REVISADA])
    comprobar("H2. eximir sin la marca puesta no carga", False, "cargo igual")
except Exception as e:                                            # noqa: BLE001
    comprobar("H2. eximir sin la marca puesta no carga",
              "sin 'aprobacion_humana: true'" in str(e), str(e)[:120])

# =============================================================================
print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLAS:")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
sys.exit(0)
