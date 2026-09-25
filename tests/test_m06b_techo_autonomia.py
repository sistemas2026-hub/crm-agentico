# -*- coding: utf-8 -*-
"""
================================================================================
 M06-B  --  el techo de autonomia por niveles (sin base)
================================================================================

Las 20 pruebas del bloque y las negativas especiales, contra el CODIGO REAL:
la frontera, el ejecutor HTTP y el motor corren de verdad. Lo que se sustituye
es la base (las respuestas que daria) y la red (un nivel por debajo del
ejecutor, que anota cada llamada). Mismo entorno que
tests/test_m06a_gate_critico.py, que se importa en vez de copiarse.

Lo que necesita PostgreSQL de verdad -- RLS entre empresas, permisos del
runtime, el tope en la tabla, la concurrencia de dos cambios -- esta en
tests/test_m06b_techo_postgres.py, que corre contra una base descartable.

Ningun dato es de un cliente real. Ninguna prueba mueve el techo de nadie:
'registrar_cambio_techo' esta sustituido en todas.
================================================================================
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from tests import test_m06a_gate_critico as g                      # noqa: E402
from nucleo.config.schema import Herramienta                      # noqa: E402
from nucleo.herramientas import http as ejecutor_http             # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguridad import aprobacion as aprobaciones            # noqa: E402
from nucleo.seguridad import autorizacion, frontera, interruptor   # noqa: E402
from nucleo.seguridad import techo as techos                       # noqa: E402

FALLOS: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(t: str) -> None:
    print()
    print("-" * 78)
    print(f"  {t}")
    print("-" * 78)


CONFIG, H, TENANT, SESION = g.CONFIG, g.H, g.TENANT, g.SESION
PILOTO = "crear_tag_crm"          # R2, sin aprobacion: el que puede ir solo


def con_nivel(nivel: int):
    """El piloto, con el nivel declarado en una COPIA en memoria. El catalogo
    no se toca: el bloque prohibe reasignar niveles."""
    return H[PILOTO].model_copy(update={"nivel_autonomia": nivel})


def fila_techo(nivel, org_fila="org-a", org_consultada="org-a"):
    return {"organization_id": org_fila, "org_consultada": org_consultada,
            "nivel": nivel, "nivel_anterior": None, "actor": "operador",
            "motivo": "prueba", "creado_en": None}


class Techo:
    """Dentro de un Entorno: fija lo que contestaria la base sobre el techo,
    cuenta las consultas y prohibe que alguien lo mueva."""

    def __init__(self, respuesta, *, autorizacion_nivel=None):
        self.respuesta = respuesta
        self.autorizacion_nivel = autorizacion_nivel
        self.consultas = 0
        self.cambios = []
        self._orig = {}

    def _leer(self, tenant):
        self.consultas += 1
        if isinstance(self.respuesta, BaseException):
            raise self.respuesta
        return self.respuesta

    def _cambio(self, *a, **k):
        self.cambios.append((a, k))
        raise AssertionError("nadie deberia mover el techo en esta prueba")

    def __enter__(self):
        parches = [(persistencia, "nivel_autonomia", self._leer),
                   (persistencia, "registrar_cambio_techo", self._cambio),
                   (persistencia, "registrar_intento_techo", lambda *a, **k: None)]
        if self.autorizacion_nivel is not None:
            nivel = self.autorizacion_nivel
            parches.append((persistencia, "autorizacion_herramienta",
                            lambda t, h: g.autorizacion_fila(h, nivel)))
        for m, n, f in parches:
            self._orig[(m, n)] = getattr(m, n)
            setattr(m, n, f)
        return self

    def __exit__(self, *e):
        for (m, n), f in self._orig.items():
            setattr(m, n, f)
        return False


def autonoma(herr, techo_resp, *, entorno_kw=None, autorizacion_nivel=None,
             argumentos=None):
    """Una escritura por el camino REAL de la conversacion/agente."""
    with g.Entorno(**(entorno_kw or {})) as e, \
            Techo(techo_resp, autorizacion_nivel=autorizacion_nivel) as t:
        cod = g.intento_directo(lambda: motor._ejecutar_tool(
            herr, SESION, dict(argumentos or {"name": "etiqueta"}), TENANT,
            CONFIG.variables_tenant, origen="evento:m06b"))
    return cod, e, t


# =============================================================================
#  1-6  EL TECHO ACOTA, NO AUTORIZA
# =============================================================================

def niveles():
    seccion("1-6. El techo es un techo, no una autorizacion")

    cod, e, _ = autonoma(con_nivel(1), fila_techo(0))
    afirmar(cod == techos.INSUFICIENTE and e.red.llamadas == [],
            f"1. techo 0 bloquea una accion nivel 1 -> {cod}, {len(e.red.llamadas)} llamadas")

    cod, e, _ = autonoma(con_nivel(1), fila_techo(1), entorno_kw={"autorizadas": ()})
    afirmar(cod == autorizacion.SIN_AUTORIZACION and e.red.llamadas == [],
            f"2. techo 1 deja PASAR EL TECHO a una nivel 1, y la frena la barrera "
            f"siguiente (sin autorizacion granular) -> {cod}")
    cod, e, _ = autonoma(con_nivel(1), fila_techo(1), entorno_kw={"etapa": False})
    afirmar(cod == "AUTONOMIA_2_NO_ACTIVA" and e.red.llamadas == [],
            f"2. ...o la etapa apagada -> {cod}")

    cod, e, _ = autonoma(con_nivel(2), fila_techo(1))
    afirmar(cod == techos.INSUFICIENTE and e.red.llamadas == [],
            f"3. techo 1 bloquea una accion nivel 2 -> {cod}")

    cod, e, _ = autonoma(con_nivel(2), fila_techo(2))
    afirmar(cod is None and len(e.red.escrituras) == 1,
            f"4. techo 2 + todas las barreras en regla -> la nivel 2 SALE "
            f"({len(e.red.escrituras)} escritura)")

    cod, e, _ = autonoma(con_nivel(3), fila_techo(2))
    afirmar(cod == techos.INSUFICIENTE and e.red.llamadas == [],
            f"5. techo 2 bloquea una accion nivel 3 -> {cod}")

    cod, e, _ = autonoma(con_nivel(3), fila_techo(3))
    afirmar(cod == autorizacion.NIVEL_INSUFICIENTE and e.red.llamadas == [],
            f"6. techo 3 deja pasar el techo a una nivel 3, pero la autorizacion "
            f"granular de nivel 2 la frena -> {cod}")
    cod, e, _ = autonoma(con_nivel(3), fila_techo(3), autorizacion_nivel=3)
    afirmar(cod is None and len(e.red.escrituras) == 1,
            "6. ...y con autorizacion de nivel 3 sale (control positivo)")

    #  El default no cambio: una escritura sin nivel declarado exige 2.
    cod, e, _ = autonoma(H[PILOTO], fila_techo(1))
    afirmar(cod == techos.INSUFICIENTE,
            f"una escritura SIN nivel declarado sigue exigiendo 2 -> techo 1: {cod}")
    cod, e, _ = autonoma(H[PILOTO], fila_techo(2))
    afirmar(cod is None and len(e.red.escrituras) == 1,
            "...y con techo 2 sale igual que antes de M06-B")


# =============================================================================
#  7-9  R3/R4 Y EL KILL SWITCH NO SE SALTAN CON UN TECHO ALTO
# =============================================================================

def criticas_y_kill_switch():
    seccion("7-8. R3/R4 con techo 3 siguen necesitando su aprobacion")
    for n in g.IRREVERSIBLES:
        with g.Entorno(lecturas=g.LECTURAS_OK[n]) as e, Techo(fila_techo(3)):
            _, cod, _ = motor.ejecutar_accion_irreversible(
                CONFIG, g.fila(n, estado="pendiente", revisado_por=None,
                               revisado_en=None), TENANT)
            cod2 = g.intento_directo(lambda: motor._ejecutar_tool(
                H[n], SESION, dict(g.MODELO[n]), TENANT, CONFIG.variables_tenant,
                origen="evento:m06b"))
        clase = ("R4" if n in g.R4 else "R3" if n in g.R3
                 else "R2 (excepcion M06-E)")
        afirmar(cod == aprobaciones.NO_APROBADA
                and cod2 == frontera.IRREVERSIBLE_SIN_APROBACION
                and e.red.llamadas == [],
                f"{'8' if clase == 'R4' else '7'}. {clase} '{n}' con techo 3 y sin "
                f"aprobacion -> {cod} / {cod2}, {len(e.red.llamadas)} llamadas")

    #  El control de M06-B para lo que declara aprobacion humana y NO es
    #  irreversible (desde M06-C agregar_promesa_pago ya es irreversible y la
    #  cubre el ciclo de arriba). Se prueba con una COPIA en memoria del piloto
    #  que declara aprobacion: con techo 3, etapa y autorizacion granular, la
    #  puerta autonoma igual no la deja salir.
    con_aprobacion = H[PILOTO].model_copy(update={"aprobacion_humana": True})
    with g.Entorno() as e, Techo(fila_techo(3)):
        cod = g.intento_directo(lambda: motor._ejecutar_tool(
            con_aprobacion, SESION, {"name": "x"}, TENANT,
            CONFIG.variables_tenant, origen="evento:m06b"))
    afirmar(cod == frontera.APROBACION_REQUERIDA and e.red.llamadas == [],
            f"8. una escritura con aprobacion humana (no irreversible), techo 3 y "
            f"autorizada: no sale sola -> {cod}, {len(e.red.llamadas)} llamadas")
    #  ...y por su camino de aprobacion (humana) sigue saliendo.
    fila_t = {"id": "prop-ticket", "herramienta": "crear_ticket",
              "argumentos": {"asunto": "Prueba", "servicio": 999001},
              "estado": "aprobada", "revisado_por": "supervisor.prueba"}
    with g.Entorno() as e, Techo(fila_techo(3)):
        _, cod = motor.ejecutar_accion_aprobada(CONFIG, fila_t)
    afirmar(cod is None and len(e.red.escrituras) == 1,
            "   ...y 'crear_ticket' APROBADA por una persona sale por su camino de siempre")

    seccion("9. Kill switch detenido bloquea aunque el techo sea 3")
    with g.Entorno(interruptor_fila=g.DETENIDO) as e, Techo(fila_techo(3)) as t:
        cod = g.intento_directo(lambda: motor._ejecutar_tool(
            H[PILOTO], SESION, {"name": "x"}, TENANT, CONFIG.variables_tenant,
            origen="evento:m06b"))
    afirmar(cod == interruptor.CODIGO_BLOQUEO and e.red.llamadas == []
            and t.consultas == 0,
            f"9. autonoma: {cod}, 0 llamadas, y el techo ni se consulto "
            f"({t.consultas} consultas)")
    with g.Entorno(interruptor_fila=g.DETENIDO,
                   lecturas=g.LECTURAS_OK["reiniciar_ont"]) as e, \
            Techo(fila_techo(3)) as t:
        _, cod, _ = motor.ejecutar_accion_irreversible(
            CONFIG, g.fila("reiniciar_ont"), TENANT)
    afirmar(cod == interruptor.CODIGO_BLOQUEO and e.red.llamadas == []
            and t.consultas == 0,
            f"9. critica (aprobada): {cod}, 0 llamadas, techo sin consultar")

    seccion("Orden: kill switch -> techo -> etapa -> autorizacion (AST)")
    for puerta in (frontera.autonoma, frontera.critica):
        import inspect
        arbol = ast.parse(inspect.getsource(puerta).lstrip())
        pos = {}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call):
                pos.setdefault(ast.unparse(n.func), n.lineno)
        orden = ["interruptor.veredicto", "_exigir_techo", "autonomia2.veredicto",
                 "autorizacion.veredicto"]
        lineas = [pos.get(x) for x in orden]
        afirmar(None not in lineas and lineas == sorted(lineas),
                f"{puerta.__name__}: {' -> '.join(orden)}", str(dict(zip(orden, lineas))))
    afirmar("_exigir_techo" not in inspect.getsource(frontera.humana),
            "humana() no consulta el techo: gobierna decisiones autonomas, no personas")


# =============================================================================
#  10-12  FALLA CERRADO Y AISLAMIENTO
# =============================================================================

class _TablaAusente(Exception):
    sqlstate = "42P01"


def fail_closed():
    seccion("10. Configuracion invalida -> NO se ejecuta")
    for valor in (4, 99, -1, "2", 2.0, True, None, [2]):
        cod, e, _ = autonoma(H[PILOTO], fila_techo(valor))
        afirmar(cod == techos.INVALIDO and e.red.llamadas == [],
                f"techo {valor!r} -> {cod}")
    for exc, esperado in ((RuntimeError("base caida"), techos.NO_LEGIBLE),
                          (TimeoutError("tarda"), techos.NO_LEGIBLE),
                          (_TablaAusente("no existe"), techos.NO_INSTALADO)):
        cod, e, _ = autonoma(H[PILOTO], exc)
        afirmar(cod == esperado and e.red.llamadas == [],
                f"lectura que falla ({type(exc).__name__}) -> {cod}")
    afirmar(techos.veredicto(TENANT, 7).codigo == techos.REQUERIDO_INVALIDO,
            "una accion que declara un nivel inexistente no se evalua: se bloquea")

    seccion("11. Configuracion inexistente -> NO se ejecuta")
    cod, e, _ = autonoma(H[PILOTO], None)
    afirmar(cod == techos.AUSENTE and e.red.llamadas == [],
            f"sin fila de techo -> {cod} (antes se leia como nivel 0)")
    with g.Entorno() as e, Techo(None):
        v = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(not v.permitido and v.codigo == techos.AUSENTE,
            f"la autorizacion granular lee el MISMO techo y tambien bloquea ({v.codigo})")

    seccion("12. Tenant A no usa el techo de tenant B")
    cod, e, _ = autonoma(H[PILOTO], fila_techo(3, org_fila="org-b", org_consultada="org-a"))
    afirmar(cod == techos.OTRO_TENANT and e.red.llamadas == [],
            f"fila de techo de otra empresa -> {cod}")
    for faltante in ("organization_id", "org_consultada"):
        f = fila_techo(3)
        f.pop(faltante)
        cod, e, _ = autonoma(H[PILOTO], f)
        afirmar(cod == techos.OTRO_TENANT, f"fila sin '{faltante}' -> {cod}")
    with g.Entorno() as e, Techo(fila_techo(3)):
        with frontera.autonoma(TENANT, PILOTO, origen="x"):
            cod = g.intento_directo(lambda: ejecutor_http.ejecutar(
                H[PILOTO], {"name": "x"}, "otra-empresa", CONFIG.variables_tenant))
    afirmar(cod == frontera.TENANT_DISTINTO and e.red.llamadas == [],
            f"un permiso abierto con el techo de una empresa no escribe en otra -> {cod}")


# =============================================================================
#  13-17  NADIE SE SUBE EL TECHO
# =============================================================================

def cambiar(nivel, *, actor="Operador Prueba", motivo="prueba", origen="cli:x",
            anterior=None, respuesta=None):
    registrados, rechazos = [], []
    orig = (persistencia.registrar_cambio_techo, persistencia.registrar_intento_techo)
    persistencia.registrar_cambio_techo = (
        lambda *a, **k: registrados.append((a, k)) or (respuesta or {
            "organization_id": "org-a", "nivel_anterior": anterior,
            "nivel_solicitado": nivel, "actor": actor, "motivo": motivo,
            "origen": origen, "resultado": "aplicado", "codigo": None,
            "creado_en": "ahora"}))
    persistencia.registrar_intento_techo = lambda *a, **k: rechazos.append((a, k))
    try:
        try:
            fila = techos.cambiar(TENANT, nivel, actor=actor, motivo=motivo,
                                  origen=origen, anterior_esperado=anterior)
            return None, fila, registrados, rechazos
        except techos.CambioRechazado as ex:
            return ex.codigo, None, registrados, rechazos
    finally:
        persistencia.registrar_cambio_techo, persistencia.registrar_intento_techo = orig


def nadie_se_sube():
    seccion("13. Un agente no puede elevar su propio techo")
    for origen in ("evento:wamid-1", "turno:abc", "accion_aprobada:prop-1",
                   "propuesta:9", "servicio:x", "", "cli"):
        cod, _, reg, _ = cambiar(3, origen=origen)
        afirmar(cod == techos.CAMBIO_ORIGEN_NO_OPERADOR and reg == [],
                f"origen {origen!r} (no es canal de operador) -> {cod}")
    for actor in ("motor", "Supervisor NOC IA", "sistema", "agente-x",
                  "asistente", "aprobacion", "reloj", ""):
        cod, _, reg, _ = cambiar(3, actor=actor)
        afirmar(cod == techos.CAMBIO_ACTOR_DEL_SISTEMA and reg == [],
                f"actor {actor!r} -> {cod}")
    with g.Entorno(), Techo(fila_techo(2)):
        with frontera.autonoma(TENANT, PILOTO, origen="x"):
            cod, _, reg, _ = cambiar(3)
    afirmar(cod == techos.CAMBIO_DESDE_UNA_ACCION and reg == [],
            f"desde adentro de una accion autonoma en curso -> {cod}")
    #  El modelo no puede bajarse la exigencia con argumentos.
    cod, e, _ = autonoma(con_nivel(3), fila_techo(2),
                         argumentos={"name": "x", "nivel_autonomia": 0,
                                     "nivel_requerido": 0, "techo": 3})
    afirmar(cod == techos.INSUFICIENTE and e.red.llamadas == [],
            f"argumentos del modelo con 'nivel_autonomia':0 / 'techo':3 no cambian "
            f"nada -> {cod}")
    #  Estatica: solo la CLI de operador llega a mover el techo.
    llamadores = []
    for base in ("nucleo", "cli", "django-crm/backend"):
        for ruta in (RAIZ / base).rglob("*.py"):
            if "node_modules" in ruta.parts or "migrations" in ruta.parts:
                continue
            try:
                arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(arbol):
                if isinstance(n, ast.Call) and ast.unparse(n.func) in (
                        "techos.cambiar", "techo.cambiar",
                        "persistencia.registrar_cambio_techo",
                        "registrar_cambio_techo"):
                    llamadores.append(ruta.relative_to(RAIZ).as_posix())
    permitidos = {"cli/autonomia.py", "nucleo/seguridad/techo.py"}
    afirmar(set(llamadores) <= permitidos and "cli/autonomia.py" in llamadores,
            f"solo cli/autonomia.py mueve el techo (via techo.cambiar): {sorted(set(llamadores))}")
    texto_schema = (RAIZ / "nucleo" / "config" / "schema.py").read_text(encoding="utf-8")
    afirmar("techo" not in {c.lower() for c in Herramienta.model_fields}
            and "cambia_techo" not in texto_schema,
            "ninguna herramienta del catalogo puede declararse como 'mueve el techo'")

    seccion("14. Una aprobacion humana no eleva el techo")
    with g.Entorno(lecturas=g.LECTURAS_OK["reiniciar_ont"]) as e, \
            Techo(fila_techo(2)) as t:
        _, cod, _ = motor.ejecutar_accion_irreversible(
            CONFIG, g.fila("reiniciar_ont"), TENANT)
    afirmar(cod is None and t.cambios == [],
            "ejecutar una irreversible aprobada no toca el techo (0 cambios)")
    with g.Entorno(), Techo(fila_techo(2)):
        aprob = aprobaciones.desde_fila(g.fila("registrar_pago"), TENANT)
        with frontera.critica(TENANT, "registrar_pago",
                              argumentos=g.ARGS["registrar_pago"], aprobacion=aprob):
            cod, _, reg, _ = cambiar(3)
    afirmar(cod == techos.CAMBIO_DESDE_UNA_ACCION and reg == [],
            f"desde adentro de una accion aprobada (puerta critica) -> {cod}")
    with g.Entorno(), Techo(fila_techo(2)):
        with frontera.humana(TENANT, "crear_ticket", actor="supervisor.prueba",
                             evidencia="prop-1"):
            cod, _, reg, _ = cambiar(3)
    afirmar(cod == techos.CAMBIO_DESDE_UNA_ACCION and reg == [],
            f"desde adentro de una aprobacion comun (puerta humana) -> {cod}")

    seccion("15. Una propuesta no eleva el techo")
    import copy as _copy
    fila_rara = g.fila("registrar_pago")
    fila_rara["argumentos"] = dict(fila_rara["argumentos"], techo=3,
                                   nivel_autonomia=3)
    with g.Entorno() as e, Techo(fila_techo(2)) as t:
        _, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila_rara, TENANT)
    afirmar(cod == aprobaciones.OTROS_ARGUMENTOS and t.cambios == []
            and e.red.llamadas == [],
            f"una propuesta con 'techo':3 en sus argumentos no mueve nada -> {cod}")
    texto_django = " ".join(
        p.read_text(encoding="utf-8", errors="replace").lower()
        for p in (RAIZ / "django-crm" / "backend").rglob("*.py")
        if "migrations" not in p.parts)
    afirmar("asistente.nivel_autonomia" not in texto_django
            and "techo_autonomia" not in texto_django,
            "el Supervisor NOC IA (Django) no referencia la tabla del techo")

    seccion("16. El cambio queda auditado (con todos los campos)")
    cod, fila, reg, rech = cambiar(2, anterior=1, origen="cli:op-1",
                                   actor="Operador Prueba", motivo="piloto")
    args = reg[0][0] if reg else ()
    afirmar(cod is None and args == (TENANT, 2, 1, "Operador Prueba", "piloto", "cli:op-1"),
            f"aplicado: se registra tenant, nuevo, anterior, quien, motivo, origen {args}")
    afirmar(fila and fila["resultado"] == "aplicado" and fila["creado_en"],
            "y vuelve la fila del intento con resultado y fecha")
    cod, _, reg, rech = cambiar(3, actor="motor")
    k = rech[0][1] if rech else {}
    afirmar(cod and reg == [] and k.get("resultado") == "rechazado"
            and k.get("codigo") == cod and k.get("origen") == "cli:x"
            and k.get("nivel_solicitado") == 3,
            f"rechazado: tambien queda, con su codigo ({k})")

    seccion("17. El nivel nuevo no supera la politica global")
    for nivel in (4, 5, 99, -1, "3", 3.0, True):
        cod, _, reg, _ = cambiar(nivel)
        afirmar(cod == techos.CAMBIO_FUERA_DE_POLITICA and reg == [],
                f"cambiar a {nivel!r} -> {cod}")
    afirmar(techos.TECHO_MAXIMO_POLITICA == 3,
            "el tope de politica es 3 y es una constante del nucleo, no del tenant")
    datos = H[PILOTO].model_dump()
    for nivel, valido in ((4, False), (3, True), (0, False)):
        datos["nivel_autonomia"] = nivel
        try:
            Herramienta(**datos)
            ok = True
        except Exception:                                        # noqa: BLE001
            ok = False
        afirmar(ok == valido,
                f"el catalogo {'acepta' if valido else 'RECHAZA'} una escritura "
                f"con nivel_autonomia {nivel}")

    seccion("18. Replay / concurrencia (la mitad sin base)")
    cod, _, _, _ = cambiar(3, anterior=2, respuesta={
        "resultado": "conflicto", "nivel_anterior": 1})
    afirmar(cod == techos.CAMBIO_CONFLICTO,
            f"si el techo cambio entretanto, el cambio NO se aplica -> {cod}")
    cod, fila, _, _ = cambiar(3, anterior=2, respuesta={
        "resultado": "repetido", "nivel_anterior": 2, "nivel_solicitado": 3})
    afirmar(cod is None and fila["resultado"] == "repetido",
            "el mismo pedido repetido devuelve 'repetido', no una transicion nueva")
    print("  (la concurrencia real, con dos conexiones a PostgreSQL, esta en "
          "tests/test_m06b_techo_postgres.py)")


# =============================================================================
#  19-20  NADA DEL CATALOGO NI DE M06-A CAMBIO
# =============================================================================

def sin_cambios_de_catalogo():
    #  M06-F: 76 y 30 desde que origin sumo siete herramientas (cuatro
    #  lecturas, dos R2 y una R4). Ninguna declara nivel: siguen en el de
    #  siempre.
    seccion("19. Las 76 herramientas conservan su clasificacion")
    from tests.test_m10a_gobierno_frontera import (R1_INTERNO, R2_REGISTRO_EXTERNO,
                                                   R3_EQUIPO_FISICO, R4_DINERO)
    todas = CONFIG.herramientas
    escrituras = {h.nombre for h in todas if not h.solo_lectura}
    afirmar(len(todas) == 76 and len(escrituras) == 30,
            f"{len(todas)} herramientas, {len(escrituras)} escrituras")
    afirmar((len(R1_INTERNO), len(R2_REGISTRO_EXTERNO), len(R3_EQUIPO_FISICO),
             len(R4_DINERO)) == (3, 21, 3, 3)
            and (R1_INTERNO | R2_REGISTRO_EXTERNO | R3_EQUIPO_FISICO | R4_DINERO) == escrituras,
            "R1=3 R2=21 R3=3 R4=3, y cubren exactamente las 30 escrituras")
    afirmar(all(h.nivel_autonomia is None for h in todas),
            "ninguna herramienta del catalogo declara nivel: no se reasigno ninguna")
    afirmar({techos.nivel_requerido_de(h) for h in todas if h.solo_lectura} == {0}
            and {techos.nivel_requerido_de(h) for h in todas if not h.solo_lectura} == {2},
            "exigencia efectiva: lecturas 0, escrituras 2 -- igual que antes")

    seccion("20. Las barreras R3/R4 de M06-A no cambiaron")
    irreversibles = sorted(h.nombre for h in todas if h.irreversible)
    afirmar(irreversibles == sorted(g.IRREVERSIBLES),
            f"las mismas cuatro irreversibles: {irreversibles}")
    r = subprocess.run([sys.executable, str(RAIZ / "tests" / "test_m06a_gate_critico.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = r.stdout.count("[ok]")
    afirmar(r.returncode == 0 and "[FALLA]" not in r.stdout,
            f"la bateria de M06-A pasa entera ({ok} comprobaciones)")


# =============================================================================
#  NEGATIVAS ESPECIALES: intentar mover el techo desde cada lugar
# =============================================================================

def negativas_especiales():
    seccion("Negativas especiales: nadie mueve el techo desde afuera del operador")
    #  Peticion manipulada: ninguna ruta del motor mueve el techo.
    from nucleo.canales import api
    rutas = [str(r) for r in api.app.url_map.iter_rules()]
    afirmar(not [r for r in rutas if "techo" in r.lower() or "nivel" in r.lower()],
            f"ninguna de las {len(rutas)} rutas HTTP del motor habla de techo o nivel")
    fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
    afirmar("techos.cambiar" not in fuente_api and "registrar_cambio_techo" not in fuente_api,
            "api.py no llama a mover el techo desde ninguna ruta")
    cliente = api.app.test_client()
    with g.Entorno(), Techo(fila_techo(1)) as t:
        for ruta in ("/interno/techo", "/autonomia/techo", "/techo",
                     "/interno/autonomia/nivel"):
            r = cliente.post(ruta, json={"tenant": TENANT, "nivel": 3, "techo": 3})
            afirmar(r.status_code in (404, 405),
                    f"POST {ruta} con {{nivel:3}} -> HTTP {r.status_code}")
    afirmar(t.cambios == [], "y el techo no se movio (0 cambios)")
    #  Herramienta: ninguna herramienta del catalogo, ejecutada, mueve el techo.
    afirmar(not any("techo" in (h.endpoint or "") or "nivel_autonomia" in (h.endpoint or "")
                    for h in CONFIG.herramientas),
            "ningun endpoint del catalogo apunta al techo")


def main() -> int:
    print("=" * 78)
    print("  M06-B  --  techo de autonomia por niveles (sin base)")
    print("=" * 78)
    niveles()
    criticas_y_kill_switch()
    fail_closed()
    nadie_se_sube()
    sin_cambios_de_catalogo()
    negativas_especiales()
    print()
    print("=" * 78)
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for f in FALLOS:
            print(f"    - {f}")
        print("=" * 78)
        return 1
    print("  [OK] El techo acota y falla cerrado; nadie fuera del operador lo mueve.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
