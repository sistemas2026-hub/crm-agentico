# -*- coding: utf-8 -*-
"""
================================================================================
 M06-A  --  el gate de aprobacion de las acciones IRREVERSIBLES (R3/R4)
================================================================================

QUE SE PRUEBA
-------------
Que 'registrar_pago' (R4) y 'reiniciar_ont', 'activar_catv', 'cambiar_tipo_onu'
(R3) no pueden producir un efecto externo sin una aprobacion humana
PERSISTIDA y atada a la accion exacta, y que una aprobacion valida no es un
pase libre: la accion sigue teniendo que pasar el kill switch, la etapa, la
autorizacion granular, las previas medidas de nuevo, la idempotencia y el
ultimo metro.

COMO, SIN RED Y SIN BASE
------------------------
La red se sustituye UN NIVEL ABAJO del ejecutor: se reemplaza el modulo
'requests' dentro de nucleo/herramientas/http.py por uno que anota cada
llamada. El ejecutor HTTP es el REAL, asi que 'frontera.exigir' --el ultimo
metro-- corre de verdad en cada prueba. (tests/test_autonomia2.py reemplaza
'ejecutor_http.ejecutar' entero, y con eso se salta justo ese control: aca no
serviria.)

Las lecturas que re-miden las previas y la verificacion se sirven desde un
diccionario en 'motor._ejecutar_tool', SOLO para herramientas de lectura; una
escritura que llegue ahi sigue el camino real.

"CERO LLAMADAS EXTERNAS" se afirma sobre la red sustituida, que ve TODO lo que
el ejecutor manda. Y para que ese cero signifique algo, cada seccion tiene su
caso positivo con la misma red: con todo en regla, la llamada SI sale.

NINGUN DATO ES DE UN CLIENTE REAL
---------------------------------
ONU 'PRUEBA000001', servicio y factura '999001', dominio '.invalid'. Aunque la
red no existe en estas pruebas, no se usa ningun identificador de un cliente.
================================================================================
"""

from __future__ import annotations

import ast
import copy
import inspect
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                            # noqa: E402
from nucleo.herramientas import http as ejecutor_http              # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguridad import aprobacion as aprobaciones            # noqa: E402
from nucleo.seguridad import (autonomia2, autorizacion, frontera,  # noqa: E402
                              interruptor)
from nucleo.seguridad.idempotencia import hash_de                  # noqa: E402
from nucleo.seguridad.verificacion import Sesion                   # noqa: E402

FALLOS: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(titulo: str) -> None:
    print()
    print("-" * 78)
    print(f"  {titulo}")
    print("-" * 78)


# =============================================================================
#  DATOS DE PRUEBA  --  inventados, ninguno de un cliente
# =============================================================================

_BASE = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
CONFIG = copy.deepcopy(_BASE)
CONFIG.variables_tenant = dict(CONFIG.variables_tenant or {},
                               SMARTOLT_SUBDOMINIO="https://smartolt.prueba.invalid")
TENANT = CONFIG.identidad.slug
H = {h.nombre: h for h in CONFIG.herramientas}

R3 = ("reiniciar_ont", "activar_catv", "cambiar_tipo_onu")
#  M06-C (21/09/2026): agregar_promesa_pago tambien va atada.
R4 = ("registrar_pago", "agregar_promesa_pago")
#  M06-E (22/09/2026): excepcion conservadora documentada. Es R2 en M10-A,
#  pero la evidencia de M06-D la muestra irreversible y con cascada en
#  WispHub: va por la misma puerta critica y se prueba igual que R3/R4.
#  M06-F (22/09/2026): registrar_promesa_y_reactivar llego en origin despues
#  de la matriz de M06-D. Registra una promesa -- el efecto de una R4 -- y ademas
#  reactiva el servicio: por la regla mas restrictiva, va atada igual.
EXCEPCIONES = ("cancelar_solicitud_servicio", "registrar_promesa_y_reactivar")
IRREVERSIBLES = R3 + R4 + EXCEPCIONES

AHORA = datetime.now(timezone.utc)
ACTIVO = {"estado": "activo", "estado_anterior": None, "actor": "prueba",
          "motivo": "", "creado_en": None}
DETENIDO = {"estado": "detenido", "estado_anterior": "activo",
            "actor": "operaciones", "motivo": "incidente", "creado_en": None}

SESION = Sesion(identificador_canal="prueba-m06a")
SESION.verificado = True
SESION.nivel = 99
SESION.id_cliente = "999001"
SESION.sn_onu = "PRUEBA000001"
SESION.interfaz_lan = ""

MODELO = {
    "cancelar_solicitud_servicio": {"numero_documento": "999001",
                                    "nombre_confirmado": "PERSONA DE PRUEBA",
                                    "motivo": "prueba M06-E"},
    "agregar_promesa_pago": {"id_factura": 999001, "fecha_limite": "2026-10-15",
                             "accion": "registrar_promesa"},
    "registrar_pago": {"id_factura": 999001, "accion": "solo_registrar_pago",
                       "forma_pago": 1},
    "reiniciar_ont": {}, "activar_catv": {}, "cambiar_tipo_onu": {},
    "registrar_promesa_y_reactivar": {"id_factura": 999001,
                                      "fecha_limite": "2026-10-15"},
}
#  Resueltos UNA vez: 'fecha_pago' sale del reloj, y la huella tiene que ser
#  la misma en la fila y en lo que se ejecuta -- como en la realidad, donde se
#  guardan al proponer y no se recalculan.
ARGS = {n: motor._resolver_argumentos(H[n], SESION, dict(MODELO[n]))
        for n in IRREVERSIBLES}

#  Lo que contestarian las lecturas si todo esta en regla.
LECTURAS_OK = {
    "reiniciar_ont": {"consultar_senal_ont": {"onu_signal_1490_veredicto": "aceptable"},
                      "ping_cliente": {"ping-exitoso": "3 de 3"},
                      "consultar_estado_ont": {"last_status_change": "2026-09-21 09:00:00"}},
    "cambiar_tipo_onu": {"consultar_estado_catv": {"catv": "Not supported by ONU-Type"}},
    "activar_catv": {"consultar_plan_tv": {"descripcion": "Internet 300 + TV"},
                     "consultar_estado_catv": {"catv": "Disabled"}},
    "registrar_pago": {},
    "agregar_promesa_pago": {},
    "cancelar_solicitud_servicio": {},
    "registrar_promesa_y_reactivar": {},
}

ORG_PRUEBA = "00000000-0000-0000-0000-0000000000aa"

#  Para el camino comun (R2), una herramienta con aprobacion NO irreversible.
R2_CON_APROBACION = "crear_ticket"


def autorizacion_fila(nombre: str, nivel: int = 2) -> dict:
    return {"id": f"aut-{nombre}", "herramienta": nombre, "estado": "autorizada",
            "estado_anterior": None, "nivel_maximo": nivel,
            "vigente_desde": AHORA - timedelta(days=1), "vigente_hasta": None,
            "autorizado_por": "jefe.prueba", "motivo": "prueba M06-A",
            "limites": {}, "creado_en": AHORA}


def fila(nombre: str, **cambios) -> dict:
    """La fila de acciones_propuestas de una irreversible YA aprobada."""
    args = copy.deepcopy(ARGS[nombre])
    f = {"id": f"prop-{nombre}", "herramienta": nombre, "argumentos": args,
         #  M06-F: la aprobacion vigente del ciclo B5 es la RESERVA.
         "estado": aprobaciones.APROBADA, "revisado_por": "supervisor.prueba",
         "revisado_en": AHORA, "origen": "evento:prueba-m06a",
         "hash_argumentos": hash_de(args),
         "contexto": motor._contexto_de_revalidacion(CONFIG, H[nombre], SESION, []),
         "conversation_id": "00000000-0000-0000-0000-00000000c0c0",
         "organization_id": ORG_PRUEBA}
    #  M06-C: el sello se calcula como lo haria reservar_accion (M06-F), sobre
    #  la fila TAL COMO SE APROBO. Los 'cambios' se aplican despues: simulan
    #  lo que alguien altero entre la aprobacion y la ejecucion.
    f["sello_aprobacion"] = aprobaciones.sello_de(
        tenant=TENANT, organization_id=f["organization_id"], herramienta=nombre,
        origen=f["origen"], huella=f["hash_argumentos"], aprobador=f["revisado_por"])
    f.update(cambios)
    return f


# =============================================================================
#  EL ENTORNO SUSTITUIDO
# =============================================================================

class _Resp:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status
        self.ok = status < 400

    def json(self):
        return self._cuerpo

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Red:
    """El modulo 'requests' que ve el ejecutor HTTP. Anota TODO."""

    def __init__(self):
        self.llamadas: list[tuple[str, str]] = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url))
        return _Resp({"status": True, "response": "comando de prueba aceptado"})

    def get(self, url, **kw):
        self.llamadas.append(("GET", url))
        return _Resp({})

    @property
    def escrituras(self):
        return [l for l in self.llamadas if l[0] != "GET"]


class Entorno:
    """
    La base, la red y las credenciales, sustituidas. Por omision TODO esta en
    regla (kill switch activo, etapa encendida, B-7 cerrado, nivel 2, las
    cuatro irreversibles autorizadas): asi cada prueba apaga UNA cosa y lo que
    se mide es el efecto de esa sola cosa.
    """

    def __init__(self, *, interruptor_fila=ACTIVO, etapa=True, nivel=2,
                 autorizadas=IRREVERSIBLES + ("crear_tag_crm",), lecturas=None):
        self.interruptor_fila = interruptor_fila
        self.etapa = etapa
        self.nivel = nivel
        self.autorizadas = set(autorizadas)
        self.lecturas = lecturas or {}
        self.red = _Red()
        self.lecturas_hechas: list[str] = []
        self.bitacora: list[dict] = []
        self.operaciones: dict[str, dict] = {}
        self.consultas_autorizacion = 0
        self._originales: dict = {}
        self._etapa_previa = None

    def _autorizacion(self, tenant, herr):
        self.consultas_autorizacion += 1
        return autorizacion_fila(herr) if herr in self.autorizadas else None

    def _reclamar(self, tenant, clave, herr, huella, origen, vence,
                  reintentar_fallida=False):
        previa = self.operaciones.get(clave)
        if previa is None:
            self.operaciones[clave] = {"huella": huella, "estado": "ejecutando",
                                       "respuesta": None}
            return {"decision": "ejecutar", "fila": {"intentos": 1}}
        if previa["huella"] != huella:
            return {"decision": "rechazada", "fila": previa,
                    "motivo": "la misma clave con otros argumentos"}
        if previa["estado"] == "exitosa":
            return {"decision": "repetida",
                    "fila": {"estado": "exitosa", "intentos": 1,
                             "respuesta": previa["respuesta"]}}
        return {"decision": "en_curso", "fila": previa}

    def _finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        if clave in self.operaciones:
            self.operaciones[clave].update(estado=estado, respuesta=respuesta)

    def _ejecutar_tool(self, herramienta, sesion, argumentos, *a, **k):
        if herramienta.solo_lectura:
            self.lecturas_hechas.append(herramienta.nombre)
            if herramienta.nombre not in self.lecturas:
                raise RuntimeError(f"lectura no preparada: {herramienta.nombre}")
            return copy.deepcopy(self.lecturas[herramienta.nombre])
        return self._originales[(motor, "_ejecutar_tool")](
            herramienta, sesion, argumentos, *a, **k)

    def __enter__(self):
        self._etapa_previa = os.environ.get(autonomia2.VAR_ETAPA)
        os.environ[autonomia2.VAR_ETAPA] = "1" if self.etapa else "0"
        parches = [
            (persistencia, "estado_autonomia", lambda t: self.interruptor_fila),
            (persistencia, "registrar_auditoria", lambda *a, **k: None),
            (persistencia, "nivel_autonomia",
             lambda t: {"nivel": self.nivel, "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba",
                        "actor": "prueba", "motivo": "", "creado_en": None}),
            (persistencia, "autorizacion_herramienta", self._autorizacion),
            (persistencia, "secreto_jwt_en_base", lambda: ""),
            (persistencia, "registrar_ejecucion_autonoma",
             lambda t, **kw: self.bitacora.append(dict(kw))),
            (persistencia, "reclamar_operacion_externa", self._reclamar),
            (persistencia, "finalizar_operacion_externa", self._finalizar),
            (ejecutor_http, "requests", self.red),
            (ejecutor_http.secretos, "obtener", lambda t, ref: "clave-de-prueba"),
            (ejecutor_http.time, "sleep", lambda s: None),
            (motor, "_ejecutar_tool", self._ejecutar_tool),
        ]
        for modulo, nombre, reemplazo in parches:
            self._originales[(modulo, nombre)] = getattr(modulo, nombre)
            setattr(modulo, nombre, reemplazo)
        return self

    def __exit__(self, *e):
        for (modulo, nombre), original in self._originales.items():
            setattr(modulo, nombre, original)
        self._originales.clear()
        if self._etapa_previa is None:
            os.environ.pop(autonomia2.VAR_ETAPA, None)
        else:
            os.environ[autonomia2.VAR_ETAPA] = self._etapa_previa
        return False


def ejecutar(nombre: str, entorno_kw: dict | None = None, **cambios_fila):
    """Aprobar-y-ejecutar por el camino REAL de una irreversible."""
    kw = {"lecturas": LECTURAS_OK[nombre]}
    kw.update(entorno_kw or {})
    with Entorno(**kw) as e:
        res, cod, pend = motor.ejecutar_accion_irreversible(
            CONFIG, fila(nombre, **cambios_fila), TENANT)
    return res, cod, pend, e


def intento_directo(fn):
    """Corre 'fn' y devuelve el codigo con que la frontera la freno, o None."""
    try:
        fn()
    except frontera.AccionExternaNoAutorizada as ex:
        return ex.codigo
    except motor.AutonomiaDetenida:
        return interruptor.CODIGO_BLOQUEO
    return None


# =============================================================================
#  0. EL CATALOGO: QUE ES IRREVERSIBLE, Y NADA MAS
# =============================================================================

def catalogo():
    seccion("0. Las cuatro irreversibles, y solo ellas")
    marcadas = sorted(h.nombre for h in CONFIG.herramientas if h.irreversible)
    afirmar(marcadas == sorted(IRREVERSIBLES),
            f"irreversibles en el catalogo: {marcadas}",
            f"esperadas: {sorted(IRREVERSIBLES)}")
    for n in IRREVERSIBLES:
        h = H[n]
        afirmar(h.aprobacion_humana and not h.invocable_por_servicio,
                f"'{n}': con aprobacion humana y NO invocable por un servicio")

    #  El validador impide declarar una irreversible sin aprobacion.
    from nucleo.config.schema import Herramienta
    datos = H["reiniciar_ont"].model_dump()
    datos["aprobacion_humana"] = False
    try:
        Herramienta(**datos)
        rechazada = False
    except Exception:                                            # noqa: BLE001
        rechazada = True
    afirmar(rechazada,
            "el validador RECHAZA una irreversible sin aprobacion_humana "
            "(no se descubre en produccion)")


# =============================================================================
#  A-J. CADA IRREVERSIBLE: SIN APROBACION -> NADA; CON APROBACION -> SIGUE
# =============================================================================

def sin_aprobacion():
    seccion("A/E/G/I. Sin aprobacion -> bloqueado, cero llamadas externas")
    for n in IRREVERSIBLES:
        #  Todo lo demas en regla: lo UNICO que falta es la aprobacion.
        _, cod, _, e = ejecutar(n, estado="pendiente", revisado_por=None,
                                revisado_en=None)
        afirmar(cod == aprobaciones.NO_APROBADA and e.red.llamadas == []
                and e.lecturas_hechas == [],
                f"'{n}' pendiente de aprobacion -> {cod}, "
                f"{len(e.red.llamadas)} llamadas, {len(e.lecturas_hechas)} lecturas")

        #  Sin fila en absoluto.
        with Entorno(lecturas=LECTURAS_OK[n]) as e2:
            cod2 = intento_directo(lambda: frontera.critica(
                TENANT, n, argumentos=ARGS[n], aprobacion=None).__enter__())
        afirmar(cod2 == aprobaciones.SIN_APROBACION and e2.red.llamadas == [],
                f"'{n}' sin ninguna aprobacion -> {cod2}, {len(e2.red.llamadas)} llamadas")


def con_aprobacion():
    seccion("B/F/H/J. Con aprobacion valida -> supera el gate y SIGUE")
    for n in IRREVERSIBLES:
        res, cod, pend, e = ejecutar(n)
        esperado = H[n].endpoint.split("{")[0]
        afirmar(cod is None and len(e.red.escrituras) == 1
                and esperado in e.red.escrituras[0][1],
                f"'{n}' aprobada y con todo lo demas en regla -> el efecto sale "
                f"UNA vez ({e.red.escrituras})")
        permitida = [b for b in e.bitacora if b.get("decision") == "permitida"
                     and "aprobada por supervisor.prueba" in (b.get("motivo") or "")]
        afirmar(len(permitida) == 1,
                f"'{n}' la auditoria registra la autorizacion CON el aprobador")
        if H[n].exige_previas:
            previas = sorted(p.herramienta for p in H[n].exige_previas)
            afirmar(all(p in e.lecturas_hechas for p in previas),
                    f"'{n}' las previas se VOLVIERON a medir al aprobar: {previas}")
        if H[n].verificacion:
            afirmar(pend is not None and pend.get("medicion_previa"),
                    f"'{n}' deja la verificacion posterior, con su medicion previa")

    seccion("...y 'pasar la aprobacion' no es 'salir': las barreras de despues deciden")
    #  Aprobada y valida, pero la senal ya no es aceptable al aprobar.
    lect = dict(LECTURAS_OK["reiniciar_ont"],
                consultar_senal_ont={"onu_signal_1490_veredicto": "baja"})
    _, cod, _, e = ejecutar("reiniciar_ont", {"lecturas": lect})
    afirmar(cod == motor.PREVIAS_NO_VIGENTES and e.red.escrituras == [],
            f"reiniciar_ont aprobado con la senal ya degradada -> {cod}, {len(e.red.escrituras)} escrituras")
    lect = dict(LECTURAS_OK["activar_catv"],
                consultar_plan_tv={"descripcion": "Internet 300"})
    _, cod, _, e = ejecutar("activar_catv", {"lecturas": lect})
    afirmar(cod == motor.PREVIAS_NO_VIGENTES and e.red.escrituras == [],
            f"activar_catv aprobado con un plan que ya no incluye TV -> {cod}, {len(e.red.escrituras)} escrituras")
    #  Una previa que no se puede medir cuenta como no cumplida.
    _, cod, _, e = ejecutar("cambiar_tipo_onu", {"lecturas": {}})
    afirmar(cod == motor.PREVIAS_NO_VIGENTES and e.red.escrituras == [],
            f"cambiar_tipo_onu con la previa imposible de medir -> {cod} (falla cerrado)")
    #  Contexto incoherente: las previas se medirian sobre OTRA ONU.
    ctx = motor._contexto_de_revalidacion(CONFIG, H["reiniciar_ont"], SESION, [])
    ctx["sesion"]["sn_onu"] = "PRUEBA000002"
    _, cod, _, e = ejecutar("reiniciar_ont", contexto=ctx)
    afirmar(cod == motor.CONTEXTO_INCOHERENTE and e.red.llamadas == []
            and e.lecturas_hechas == [],
            f"previas sobre una ONU y accion sobre otra -> {cod}, nada medido ni enviado")


# =============================================================================
#  C/D/K/L. LA APROBACION ESTA ATADA A LA ACCION EXACTA
# =============================================================================

def atada_a_la_accion():
    seccion("C. Argumentos modificados despues de aprobar -> bloqueado")
    otros = dict(ARGS["registrar_pago"], id=999002)
    _, cod, _, e = ejecutar("registrar_pago", argumentos=otros)
    afirmar(cod == aprobaciones.OTROS_ARGUMENTOS and e.red.llamadas == [],
            f"registrar_pago con la factura cambiada en la fila -> {cod}, {len(e.red.llamadas)} llamadas")
    otros = dict(ARGS["reiniciar_ont"], sn_onu="PRUEBA000002")
    _, cod, _, e = ejecutar("reiniciar_ont", argumentos=otros)
    afirmar(cod == aprobaciones.OTROS_ARGUMENTOS and e.red.llamadas == [],
            f"reiniciar_ont con otra ONU en la fila -> {cod}, {len(e.red.llamadas)} llamadas")
    #  Y aunque alguien cambie argumentos Y huella juntos, el trigger de la
    #  migracion lo impide en la base (no se puede probar sin base: se
    #  comprueba que el trigger EXISTE y cubre esas columnas).
    sql = (RAIZ / "supabase" / "202609221030_aprobacion_vinculante_b5.sql").read_text(encoding="utf-8")
    afirmar(all(f"new.{c}" in sql for c in ("argumentos", "hash_argumentos",
                                             "herramienta", "origen")),
            "la migracion vuelve inmutables argumentos, huella, herramienta y origen")

    seccion("D. Aprobacion de otra operacion -> bloqueada")
    aprob_a = aprobaciones.desde_fila(fila("registrar_pago"), TENANT)
    otra = dict(ARGS["registrar_pago"], id=999002)
    with Entorno() as e:
        cod = intento_directo(lambda: frontera.critica(
            TENANT, "registrar_pago", argumentos=otra,
            aprobacion=aprob_a).__enter__())
    afirmar(cod == aprobaciones.OTROS_ARGUMENTOS and e.red.llamadas == [],
            f"la aprobacion de la factura 999001 usada para la 999002 -> {cod}")

    seccion("K. Aprobacion R3 reutilizada para otra accion -> bloqueada")
    aprob_reinicio = aprobaciones.desde_fila(fila("reiniciar_ont"), TENANT)
    with Entorno() as e:
        cod = intento_directo(lambda: frontera.critica(
            TENANT, "cambiar_tipo_onu", argumentos=ARGS["reiniciar_ont"],
            aprobacion=aprob_reinicio).__enter__())
    afirmar(cod == aprobaciones.OTRA_HERRAMIENTA and e.red.llamadas == [],
            f"la aprobacion de reiniciar_ont usada para cambiar_tipo_onu -> {cod}")
    #  Y dentro de un permiso critico abierto para reiniciar, el ejecutor no
    #  deja salir otra herramienta.
    with Entorno() as e:
        with frontera.critica(TENANT, "reiniciar_ont", argumentos=ARGS["reiniciar_ont"],
                              aprobacion=aprob_reinicio):
            cod = intento_directo(lambda: ejecutor_http.ejecutar(
                H["activar_catv"], ARGS["activar_catv"], TENANT, CONFIG.variables_tenant))
    afirmar(cod == frontera.PERMISO_DE_OTRA_ACCION and e.red.llamadas == [],
            f"permiso critico de reiniciar_ont usado para activar_catv -> {cod}")

    seccion("L. Aprobacion R4 reutilizada para otra operacion -> bloqueada")
    with Entorno() as e:
        with frontera.critica(TENANT, "registrar_pago", argumentos=ARGS["registrar_pago"],
                              aprobacion=aprob_a):
            cod = intento_directo(lambda: ejecutor_http.ejecutar(
                H["registrar_pago"], dict(ARGS["registrar_pago"], id=999002), TENANT))
            cod_r2 = intento_directo(lambda: ejecutor_http.ejecutar(
                H[R2_CON_APROBACION], {"asunto": "x"}, TENANT))
    afirmar(cod == frontera.PERMISO_DE_OTRA_ACCION and e.red.llamadas == [],
            f"el permiso del pago de 999001 usado para pagar 999002 -> {cod}")
    afirmar(cod_r2 == frontera.PERMISO_DE_OTRA_ACCION,
            f"...ni siquiera sirve para una escritura comun (crear_ticket) -> {cod_r2}")
    afirmar(frontera.permiso_vigente() is None,
            "el permiso critico no sobrevive al bloque que lo abrio")

    seccion("Las demas ataduras: quien, cuando, origen, huella, tenant")
    for campo, valor, codigo in (("revisado_por", "", aprobaciones.SIN_APROBADOR),
                                 ("revisado_en", None, aprobaciones.SIN_MOMENTO),
                                 ("origen", "", aprobaciones.SIN_ORIGEN),
                                 ("hash_argumentos", None, aprobaciones.SIN_HUELLA),
                                 ("estado", "rechazada", aprobaciones.NO_APROBADA)):
        _, cod, _, e = ejecutar("registrar_pago", **{campo: valor})
        afirmar(cod == codigo and e.red.llamadas == [],
                f"aprobacion con '{campo}'={valor!r} -> {cod}")
    aprob_otra = aprobaciones.desde_fila(fila("registrar_pago"), "otra-empresa")
    with Entorno() as e:
        cod = intento_directo(lambda: frontera.critica(
            TENANT, "registrar_pago", argumentos=ARGS["registrar_pago"],
            aprobacion=aprob_otra).__enter__())
    afirmar(cod == aprobaciones.OTRO_TENANT and e.red.llamadas == [],
            f"una aprobacion de otra empresa -> {cod}")


# =============================================================================
#  M. KILL SWITCH  /  N. IDEMPOTENCIA
# =============================================================================

def kill_switch():
    seccion("M. Kill switch detenido + aprobacion valida -> bloqueado")
    for n in IRREVERSIBLES:
        _, cod, _, e = ejecutar(n, {"interruptor_fila": DETENIDO})
        afirmar(cod == interruptor.CODIGO_BLOQUEO and e.red.llamadas == []
                and e.lecturas_hechas == [],
                f"'{n}' aprobada con el kill switch tirado -> {cod}, {len(e.red.llamadas)} llamadas, {len(e.lecturas_hechas)} lecturas")


def idempotencia_replay():
    seccion("N. La misma aprobacion ejecutada dos veces -> un solo efecto")
    for n in ("registrar_pago", "reiniciar_ont"):
        with Entorno(lecturas=LECTURAS_OK[n]) as e:
            _, c1, p1 = motor.ejecutar_accion_irreversible(CONFIG, fila(n), TENANT)
            _, c2, p2 = motor.ejecutar_accion_irreversible(CONFIG, fila(n), TENANT)
        afirmar(c1 is None and c2 is None and len(e.red.escrituras) == 1,
                f"'{n}' dos veces -> {len(e.red.escrituras)} escritura(s) externa(s)")
        if H[n].verificacion:
            afirmar(p1 is not None and p2 is None,
                    f"'{n}' la repeticion NO anota una segunda verificacion")


# =============================================================================
#  5. EL ORDEN DE LOS CONTROLES
# =============================================================================

def orden():
    seccion("5. Orden: tenant -> kill switch -> etapa -> autorizacion -> "
            "aprobacion -> auditoria -> permiso")
    arbol = ast.parse(inspect.getsource(frontera.critica).lstrip())
    lineas = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            nombre = ast.unparse(nodo.func)
            if nombre == "_bitacora" and any(
                    isinstance(a, ast.Constant) and a.value == "autorizada"
                    for a in nodo.args):
                nombre = "_bitacora(autorizada)"
            lineas.setdefault(nombre, nodo.lineno)
        if isinstance(nodo, ast.Yield):
            lineas.setdefault("yield", nodo.lineno)
    secuencia = ["_tenant_valido", "interruptor.veredicto", "autonomia2.veredicto",
                 "autorizacion.veredicto", "aprobaciones.veredicto",
                 "_bitacora(autorizada)", "_PERMISO.set", "yield"]
    posiciones = [lineas.get(s) for s in secuencia]
    afirmar(None not in posiciones and posiciones == sorted(posiciones),
            "en el codigo de frontera.critica el orden es exactamente ese",
            str(dict(zip(secuencia, posiciones))))

    #  Y en la conducta: el primer control que dice no, gana, y los de
    #  despues NI SE CONSULTAN.
    _, cod, _, e = ejecutar("registrar_pago", {"interruptor_fila": DETENIDO},
                            estado="pendiente")
    afirmar(cod == interruptor.CODIGO_BLOQUEO and e.consultas_autorizacion == 0,
            f"kill switch tirado y sin aprobacion -> manda el kill switch ({cod}); "
            f"la autorizacion ni se consulto")
    _, cod, _, e = ejecutar("registrar_pago", {"etapa": False}, estado="pendiente")
    afirmar(cod == autonomia2.ETAPA_APAGADA and e.consultas_autorizacion == 0,
            f"etapa apagada y sin aprobacion -> manda la etapa ({cod})")
    _, cod, _, e = ejecutar("registrar_pago", {"autorizadas": ()}, estado="pendiente")
    afirmar(cod == autorizacion.SIN_AUTORIZACION,
            f"sin autorizacion granular y sin aprobacion -> manda la autorizacion ({cod})")
    #  Desde M06-B el techo es un paso PROPIO, pegado al kill switch: lo
    #  frena ahi, antes de llegar a la autorizacion granular.
    _, cod, _, e = ejecutar("registrar_pago", {"nivel": 1})
    afirmar(cod == "TECHO_AUTONOMIA_INSUFICIENTE" and e.red.llamadas == [],
            f"aprobada pero con el techo de la empresa en 1 -> {cod}: la aprobacion "
            f"no salta el nivel de autonomia")


# =============================================================================
#  4. NO HAY BYPASS
# =============================================================================

def sin_bypass():
    seccion("4. Ningun camino llega al efecto sin la puerta critica")
    aprob = {n: aprobaciones.desde_fila(fila(n), TENANT) for n in IRREVERSIBLES}
    for n in IRREVERSIBLES:
        h = H[n]
        #  1. El camino de la conversacion / del agente (autonoma).
        with Entorno(lecturas=LECTURAS_OK[n]) as e:
            cod = intento_directo(lambda: motor._ejecutar_tool(
                h, SESION, dict(MODELO[n]), TENANT, CONFIG.variables_tenant,
                origen="evento:bypass"))
        afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
                f"'{n}' por _ejecutar_tool (conversacion/agente) -> {cod}")
        #  2. La puerta humana de siempre (el camino de R2).
        with Entorno() as e:
            with frontera.humana(TENANT, n, actor="alguien", evidencia="fila-x"):
                cod = intento_directo(lambda: ejecutor_http.ejecutar(
                    h, ARGS[n], TENANT, CONFIG.variables_tenant))
        afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
                f"'{n}' por frontera.humana + ejecutor -> {cod}")
        #  3. El ejecutor de aprobaciones COMUN, con una fila aprobada.
        with Entorno() as e:
            _, cod = motor.ejecutar_accion_aprobada(CONFIG, fila(n))
        afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
                f"'{n}' por ejecutar_accion_aprobada (camino R2) -> {cod}")
        #  4. El ejecutor pelado, sin ninguna puerta.
        with Entorno() as e:
            cod = intento_directo(lambda: ejecutor_http.ejecutar(
                h, ARGS[n], TENANT, CONFIG.variables_tenant))
            cod_a = intento_directo(lambda: ejecutor_http.ejecutar_asincrono(
                h, ARGS[n], tenant=TENANT, variables_tenant=CONFIG.variables_tenant))
        afirmar(cod == frontera.SIN_AUTORIZAR and cod_a == frontera.SIN_AUTORIZAR
                and e.red.llamadas == [],
                f"'{n}' por el ejecutor directo (sync y async) -> {cod}")
        #  5. La ruta de servicio (/interno).
        with Entorno() as e:
            try:
                motor.ejecutar_para_servicio(CONFIG, h, dict(MODELO[n]), TENANT)
                cod = None
            except Exception as ex:                              # noqa: BLE001
                cod = type(ex).__name__
        afirmar(cod is not None and e.red.llamadas == [],
                f"'{n}' por la ruta de servicio -> rechazada ({cod})")
        #  6. Una puerta autonoma con TODO en regla tampoco alcanza.
        with Entorno() as e:
            with frontera.autonoma(TENANT, n, origen="bypass"):
                cod = intento_directo(lambda: ejecutor_http.ejecutar(
                    h, ARGS[n], TENANT, CONFIG.variables_tenant))
        afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
                f"'{n}' por frontera.autonoma con etapa+autorizacion en regla -> {cod}")
        #  7. El control positivo: el MISMO ejecutor, con la puerta critica, sale.
        with Entorno() as e:
            with frontera.critica(TENANT, n, argumentos=ARGS[n], aprobacion=aprob[n]):
                ejecutor_http.ejecutar(h, ARGS[n], TENANT, CONFIG.variables_tenant)
        afirmar(len(e.red.escrituras) == 1,
                f"'{n}' CONTROL: por frontera.critica el mismo ejecutor SI sale")

    seccion("4b. Nadie en nucleo/ escribe afuera sin el ejecutor")
    permitidos = {"nucleo/herramientas/http.py",
                  #  API de mensajeria de Meta: manda texto al cliente, no
                  #  toca WispHub ni SmartOLT.
                  "nucleo/canales/whatsapp.py"}
    directos = []
    for ruta in (RAIZ / "nucleo").rglob("*.py"):
        rel = ruta.relative_to(RAIZ).as_posix()
        if rel in permitidos:
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr in ("post", "put", "patch", "delete", "request")
                    and ast.unparse(nodo.func.value) in ("requests", "httpx")):
                directos.append(f"{rel}:{nodo.lineno}")
    afirmar(directos == [], "ningun modulo de nucleo/ hace una escritura HTTP directa",
            str(directos))
    rutas = [H[n].endpoint.split("{")[0] for n in IRREVERSIBLES]
    mencionan = []
    #  M06-F: sobre los LITERALES que el codigo usa, no sobre el texto. Un
    #  docstring que explica un endpoint (nucleo/facturacion/promesas.py, de
    #  origin) no lo llama; un literal en una expresion si podria.
    for ruta in (RAIZ / "nucleo").rglob("*.py"):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        docstrings = {id(n.value) for n in ast.walk(arbol)
                      if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        literales = [n.value for n in ast.walk(arbol)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and id(n) not in docstrings]
        mencionan += [f"{ruta.relative_to(RAIZ).as_posix()}:{r}"
                      for r in rutas if any(r in s for s in literales)]
    afirmar(mencionan == [],
            "ningun modulo de nucleo/ conoce un endpoint R3/R4: solo el catalogo",
            str(mencionan))


# =============================================================================
#  EL CAMINO DE LA CONVERSACION: PROPONE, NO EJECUTA
# =============================================================================

def conversacion():
    seccion("La conversacion propone la accion atada; no la ejecuta")
    from nucleo.modelo.cliente import Llamada, Respuesta

    #  El historial ya trae las previas favorables, como en una conversacion
    #  real donde el modelo midio antes de pedir el reinicio.
    historial = [
        {"role": "assistant", "content": "", "tool_calls": [
            motor._tool_call_a_dict("consultar_senal_ont", {}, "call_0"),
            motor._tool_call_a_dict("ping_cliente", {}, "call_1")]},
        {"role": "tool", "name": "consultar_senal_ont", "tool_call_id": "call_0",
         "content": '{"onu_signal_1490_veredicto": "aceptable"}'},
        {"role": "tool", "name": "ping_cliente", "tool_call_id": "call_1",
         "content": '{"ping-exitoso": "3 de 3"}'},
    ]
    #  M06-F: origin exige declarar el sintoma (exige_declaracion): una queja
    #  de lentitud no reinicia. El modelo lo declara como en una conversacion
    #  real donde el cliente dijo que no tiene servicio.
    guion = [Respuesta(llamadas=[Llamada("reiniciar_ont", {"sintoma": "sin_servicio"})]),
             Respuesta(contenido="Quedo solicitado.")]
    propuestas = []

    def guardar(tenant, herr, argumentos, resumen, rol, quien, **kw):
        propuestas.append({"herramienta": herr, "argumentos": argumentos, **kw})
        #  M06-F: la firma de B5 devuelve (id, ya_existia).
        return "prop-conversacion", False

    with Entorno(lecturas=LECTURAS_OK["reiniciar_ont"]) as e:
        sustituir = [
            (motor.cliente, "chat",
             lambda *a, **k: guion.pop(0) if guion else Respuesta(contenido="fin")),
            (motor, "recuperar", lambda *a, **k: ([], 0.0)),
            (motor.catalogo_habilidades, "indice_de", lambda *a, **k: []),
            (motor.consumo, "anotar", lambda *a, **k: None),
            (motor.persistencia, "guardar_accion_propuesta", guardar),
        ]
        originales = [(o, a, getattr(o, a)) for o, a, _ in sustituir]
        for o, a, f in sustituir:
            setattr(o, a, f)
        try:
            _, registro, _ = motor.responder(
                CONFIG, "soporte", "sigo sin internet, reinicialo", historial,
                SESION, origen="evento:wamid-prueba")
        finally:
            for o, a, f in originales:
                setattr(o, a, f)

    afirmar(e.red.llamadas == [],
            f"reiniciar_ont pedido en la conversacion -> {len(e.red.llamadas)} llamadas externas")
    afirmar(len(propuestas) == 1 and propuestas[0]["herramienta"] == "reiniciar_ont",
            "...queda UNA propuesta en la cola", str(propuestas))
    if propuestas:
        p = propuestas[0]
        afirmar(p.get("hash_argumentos") == hash_de(p["argumentos"]),
                "...con la huella de los argumentos que se guardaron")
        afirmar(p.get("origen") == "evento:wamid-prueba",
                "...con el origen de la solicitud (el mensaje que la pidio)")
        ctx = p.get("contexto") or {}
        afirmar((ctx.get("sesion") or {}).get("sn_onu") == "PRUEBA000001"
                and "consultar_senal_ont" in (ctx.get("previas") or {}),
                "...y con lo necesario para volver a medir las previas al aprobar",
                str(ctx))
    fila_traza = next((r for r in registro if r["herramienta"] == "reiniciar_ont"), {})
    afirmar(fila_traza.get("verificacion_pendiente") is None,
            "la propuesta NO deja una verificacion pendiente (no hubo reinicio que "
            "verificar) -- el defecto encontrado al activar el gate",
            str(fila_traza.get("verificacion_pendiente")))
    afirmar(fila_traza.get("accion_id") == "prop-conversacion",
            "la traza lleva el id de la propuesta para atarla a su conversacion")


# =============================================================================
#  O. R1 Y R2 NO CAMBIAN
# =============================================================================

def r1_r2_sin_cambio():
    seccion("O. R1/R2 siguen sin este gate adicional")
    #  R2 con aprobacion: sigue por la puerta humana, aunque el kill switch
    #  este tirado y la etapa apagada -- exactamente como antes de M06-A.
    fila_r2 = {"id": "prop-r2", "herramienta": R2_CON_APROBACION,
               "argumentos": {"asunto": "Prueba", "servicio": 999001},
               "estado": "aprobada", "revisado_por": "supervisor.prueba"}
    with Entorno(interruptor_fila=DETENIDO, etapa=False, autorizadas=()) as e:
        _, cod = motor.ejecutar_accion_aprobada(CONFIG, fila_r2)
    afirmar(cod is None and len(e.red.escrituras) == 1,
            f"'{R2_CON_APROBACION}' aprobada sale por la puerta humana como siempre "
            f"({cod}, {len(e.red.escrituras)} escritura)")
    #  R2 autonoma: sigue por la puerta autonoma, sin pedir aprobacion.
    with Entorno() as e:
        motor._ejecutar_tool(H["crear_tag_crm"], SESION, {"name": "prueba"},
                             TENANT, CONFIG.variables_tenant, origen="evento:r2")
    afirmar(len(e.red.escrituras) == 1,
            "'crear_tag_crm' autorizada sale por la puerta autonoma sin aprobacion")
    no_irreversibles = [h.nombre for h in CONFIG.herramientas
                        if not h.solo_lectura and not h.irreversible]
    #  22 desde M06-C: agregar_promesa_pago paso a la puerta critica.
    #  21 desde M06-E: cancelar_solicitud_servicio paso a la puerta critica.
    #  23 desde M06-F: origin trajo dos escrituras nuevas que NO son
    #  irreversibles (asignar_caso_crm, cerrar_ticket_operativo_estado) y una
    #  que si (registrar_promesa_y_reactivar, que no cuenta aca).
    afirmar(len(no_irreversibles) == 23 and "agregar_promesa_pago" not in no_irreversibles
            and "registrar_promesa_y_reactivar" not in no_irreversibles
            and "cancelar_solicitud_servicio" not in no_irreversibles,
            f"las otras {len(no_irreversibles)} escrituras NO son irreversibles "
            f"(ni R1 ni R2 entran a este gate)")


def main() -> int:
    print("=" * 78)
    print("  M06-A  --  gate de aprobacion de las acciones irreversibles (R3/R4)")
    print("=" * 78)
    catalogo()
    sin_aprobacion()
    con_aprobacion()
    atada_a_la_accion()
    kill_switch()
    idempotencia_replay()
    orden()
    sin_bypass()
    conversacion()
    r1_r2_sin_cambio()
    print()
    print("=" * 78)
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for f in FALLOS:
            print(f"    - {f}")
        print("=" * 78)
        return 1
    print("  [OK] Sin aprobacion no hay efecto; con aprobacion la accion sigue por")
    print("       las demas barreras, y solo sale si todas la dejan.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
