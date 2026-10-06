# -*- coding: utf-8 -*-
"""
================================================================================
 ESCRIBIR NO ES SALIR  --  la frontera distingue adentro de afuera
================================================================================

    py -3.13 tests/test_frontera_efecto_externo.py

EL DEFECTO QUE ESTO FIJA  --  medido en produccion el 06/10/2026
----------------------------------------------------------------
'frontera.autonoma()' consultaba 'autonomia2.veredicto()' SIN argumentos: una
compuerta global de etapa, igual para todo. Las tres herramientas de
sincronizacion de tickets tienen 'solo_lectura: false' --correcto, hacen
POST-- y por eso caian ahi.

Pero escriben contra 'http://backend:8000/api' con IMPORTACION_API_TOKEN: es
Dexter escribiendose a si mismo. Ningun cliente recibe nada, ningun estado de
un tercero cambia. Comparar con 'responder_ticket_operativo', que va a
'/api/tickets/{id}/respuesta/' con WISPHUB_API_KEY -- esa si sale.

Costo medido: entre el 21/09 y el 06/10 el reloj no importo un solo ticket,
con 49 candidatos esperando y sin un aviso. El kill switch pasaba y el techo
tambien ('techo 2 >= 2'); el unico que bloqueaba era la etapa.

QUE SE AFIRMA, Y POR QUE ASI
-----------------------------
Sobre el EFECTO: que la llamada pase o levante, y que lo que se afloja sea
UNA compuerta y no la frontera. No alcanza con comprobar que el campo existe
-- un campo que existe y que nadie lee se ve igual de bien en el diff.

Por eso cada caso de "sigue bloqueando" se corre con Autonomia 2 APAGADA, que
es el estado real de produccion: si la exencion se hubiera escrito mas ancha
de la cuenta, estos casos pasarian y la prueba se pondria roja.

NO SE LLAMA A NINGUNA API NI AL MODELO. Las compuertas se sustituyen por
dobles; lo que se prueba es la decision de la frontera, no la red.
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config.schema import Herramienta                      # noqa: E402
from nucleo.seguridad import frontera                             # noqa: E402

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
        self.estado, self.nivel_efectivo, self.autorizacion_id = codigo, 2, ""
        self.techo, self.requerido = 2, 2


class Banco:
    """
    Sustituye las compuertas y captura la bitacora.

    'autonomia2' queda APAGADA en el default, que es el estado de produccion:
    asi, cualquier caso que pase es porque la exencion lo dejo pasar, no
    porque la etapa estuviera abierta.
    """
    def __init__(self, *, interruptor=True, techo=True, etapa=False, granular=True):
        self.cfg = dict(interruptor=interruptor, techo=techo, etapa=etapa,
                        granular=granular)
        self.bitacora: list[dict] = []
        self.etapa_consultada = 0

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

        def _etapa(*a, **k):
            self.etapa_consultada += 1
            return _V(c["etapa"], "AUTONOMIA_2_NO_ACTIVA", "la etapa no esta activa")

        frontera.interruptor.veredicto = lambda t: _V(
            c["interruptor"], "detenido" if not c["interruptor"] else "activo", "x")
        frontera.techos.veredicto = lambda t, n: _V(
            c["techo"], "techo_insuficiente" if not c["techo"] else "ok", "x")
        frontera.autonomia2.veredicto = _etapa
        frontera.autorizacion.veredicto = lambda t, h, **k: _V(
            c["granular"], "HERRAMIENTA_SIN_AUTORIZACION", "x")
        frontera._bitacora = lambda *a, **k: self.bitacora.append(
            {"args": a, "kw": k})
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


def herramienta(nombre, **kw):
    base = dict(nombre=nombre, tipo="http", roles_permitidos=["soporte"],
                metodo="POST", endpoint="/x/", base_url="http://backend:8000/api",
                solo_lectura=False, requiere_confirmacion=True)
    base.update(kw)
    return Herramienta(**base)


def corre(nombre, *, externo, banco_kw=None):
    """(paso, codigo). 'paso' dice si la frontera abrio el permiso."""
    with Banco(**(banco_kw or {})) as b:
        try:
            with frontera.autonoma("rapilink", nombre, origen="importacion",
                                   efecto_externo=externo):
                pass
            return True, "", b
        except frontera.AccionExternaNoAutorizada as e:
            return False, e.codigo, b


print("=" * 72)
print(" ESCRIBIR NO ES SALIR  (sin red, sin modelo)")
print("=" * 72)

# =============================================================================
print("\n-- A, B, C: el reloj puede correr las tres escrituras internas --")
# =============================================================================
#  Las cuatro escrituras internas de la importacion. Las tres primeras las
#  corre el reloj; la cuarta solo 'cli/backfill_nombre_cliente.py', que pasa
#  actor y entra por la puerta humana -- ver el bloque del final.
INTERNAS = ("importar_caso_externo", "reconciliar_caso_externo",
            "sincronizar_respuestas_externas", "fijar_nombre_cliente_externo")
for n in INTERNAS:
    paso, codigo, b = corre(n, externo=False)
    comprobar(f"{n} pasa con Autonomia 2 APAGADA", paso, codigo)

# =============================================================================
print("\n-- I: y con la etapa apagada, lo externo SIGUE bloqueado --")
# =============================================================================
paso, codigo, _ = corre("responder_ticket_operativo", externo=True)
comprobar("responder_ticket_operativo sigue bloqueada",
          not paso and codigo == "AUTONOMIA_2_NO_ACTIVA", f"paso={paso} {codigo}")
paso, codigo, _ = corre("una_herramienta_cualquiera", externo=True)
comprobar("y cualquier otra que no declare nada, tambien",
          not paso and codigo == "AUTONOMIA_2_NO_ACTIVA", f"paso={paso} {codigo}")

#  El default del PARAMETRO, no solo el del catalogo.
with Banco() as b:
    try:
        with frontera.autonoma("rapilink", "sin_declarar", origen="x"):
            pass
        ok = False
    except frontera.AccionExternaNoAutorizada as e:
        ok = e.codigo == "AUTONOMIA_2_NO_ACTIVA"
comprobar("sin pasar el parametro, se asume EXTERNO (fail-closed)", ok)

# =============================================================================
print("\n-- D: la exencion queda ANOTADA, no es un silencio --")
# =============================================================================
paso, _, b = corre("importar_caso_externo", externo=False)
textos = [str(x["args"]) for x in b.bitacora]
comprobar("hay bitacora de la decision", len(b.bitacora) >= 1, str(len(b.bitacora)))
comprobar("...y una fila dice por que no paso por la etapa",
          any("etapa_no_aplica" in t for t in textos), str(textos)[:200])
comprobar("...y tambien la fila de 'autorizada' de siempre",
          any("autorizada" in t for t in textos), str(textos)[:200])

# =============================================================================
print("\n-- G: el kill switch sigue bloqueando a las internas --")
# =============================================================================
for n in INTERNAS:
    paso, codigo, _ = corre(n, externo=False, banco_kw={"interruptor": False})
    comprobar(f"{n} NO pasa con el interruptor detenido", not paso, codigo)

# =============================================================================
print("\n-- F: el tenant sigue siendo obligatorio --")
# =============================================================================
for malo in ("", "   ", None):
    with Banco():
        try:
            with frontera.autonoma(malo, "importar_caso_externo",
                                   efecto_externo=False):
                pass
            paso = True; codigo = ""
        except frontera.AccionExternaNoAutorizada as e:
            paso, codigo = False, e.codigo
    comprobar(f"tenant {malo!r} rechazado", not paso and codigo == frontera.SIN_TENANT,
              codigo)

# =============================================================================
print("\n-- el techo y la autorizacion granular siguen aplicando --")
# =============================================================================
paso, codigo, _ = corre("importar_caso_externo", externo=False,
                        banco_kw={"techo": False})
comprobar("el techo insuficiente sigue frenando a una interna", not paso, codigo)
paso, codigo, _ = corre("importar_caso_externo", externo=False,
                        banco_kw={"granular": False})
comprobar("la autorizacion granular tambien",
          not paso and codigo == "HERRAMIENTA_SIN_AUTORIZACION", codigo)

# =============================================================================
print("\n-- J: la exencion toca UNA compuerta, no la frontera --")
# =============================================================================
paso, _, b = corre("importar_caso_externo", externo=False)
comprobar("con la exencion, la etapa NI SE CONSULTA", b.etapa_consultada == 0,
          str(b.etapa_consultada))
paso, _, b2 = corre("responder_ticket_operativo", externo=True)
comprobar("sin la exencion, se consulta", b2.etapa_consultada == 1,
          str(b2.etapa_consultada))
comprobar("y 'critica' no acepta el parametro: una irreversible no tiene salida",
          "efecto_externo" not in frontera.critica.__wrapped__.__code__.co_varnames
          if hasattr(frontera.critica, "__wrapped__") else True)

# =============================================================================
print("\n-- H: el schema rechaza una declaracion peligrosa --")
# =============================================================================
def rechaza(**kw):
    try:
        herramienta("x", efecto_externo=False, **kw)
        return False
    except Exception:
        return True

comprobar("irreversible + efecto_externo:false -> rechazada al cargar",
          rechaza(irreversible=True, aprobacion_humana=True))
comprobar("aprobacion_humana + efecto_externo:false -> rechazada",
          rechaza(aprobacion_humana=True))
comprobar("una escritura interna normal SI se puede declarar",
          not rechaza())

# =============================================================================
print("\n-- el catalogo real del tenant --")
# =============================================================================
import yaml                                                        # noqa: E402
from nucleo.config.schema import TenantConfig                      # noqa: E402

doc = yaml.safe_load((Path(__file__).resolve().parents[1]
                      / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
cfg = TenantConfig(**doc)
H = {h.nombre: h for h in cfg.herramientas}

for n in INTERNAS:
    comprobar(f"{n} declara efecto_externo=false en el catalogo",
              n in H and not H[n].efecto_externo)
comprobar("responder_ticket_operativo NO lo declara: sigue externa",
          H["responder_ticket_operativo"].efecto_externo)
exentas = sorted(h.nombre for h in cfg.herramientas if not h.efecto_externo)
comprobar("y son EXACTAMENTE esas cuatro las exentas, ni una mas",
          exentas == sorted(INTERNAS), str(exentas))
comprobar("ninguna exenta es irreversible ni pide aprobacion",
          not [h.nombre for h in cfg.herramientas
               if not h.efecto_externo and (h.irreversible or h.aprobacion_humana)])
#  Todas las exentas escriben contra NUESTRO backend. Si manana alguien exime
#  una que apunta a un tercero, esto se pone rojo.
ajenas = [h.nombre for h in cfg.herramientas
          if not h.efecto_externo and "backend:8000" not in (h.base_url or "")]
comprobar("y todas apuntan al backend propio, no a un tercero",
          not ajenas, str(ajenas))

print("\n" + "=" * 72)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("TODO EN VERDE")
print("=" * 72)
