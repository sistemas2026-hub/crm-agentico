# -*- coding: utf-8 -*-
"""
================================================================================
 M06-F  --  la aprobacion vinculante DENTRO del ciclo B5, contra PostgreSQL real
================================================================================

Lo que se prueba aca no se puede probar sin base: que la cola de B5 y la
aprobacion de M06 son UNA sola cadena, y que la base -- no solo el codigo --
la sostiene.

    propuesta -> aprobacion (reserva B5 con sello) -> tenant/identidad ->
    sello -> kill switch/techo/etapa/autorizacion -> idempotencia ->
    frontera -> efecto -> desenlace B5 con su evento

REAL: la base entera (construida desde cero con las 63 migraciones del repo
por cli/base_desde_cero.py), la cola, el trigger, la RLS, el kill switch, el
techo, la autorizacion granular, la bitacora, el registro de operaciones
externas, el endpoint de aprobacion y el boton de reinicio de la Bandeja.

SIMULADO, y dicho: la red (el modulo 'requests' que ve el ejecutor HTTP, un
nivel por debajo del ejecutor real), las credenciales, y las LECTURAS que
repiten las previas (motor._ejecutar_tool para herramientas solo_lectura). Las
previas estan probadas en tests/test_m06a_gate_critico.py; aca importa la
cadena y la base.

SEGURIDAD DE LA PROPIA PRUEBA
  * se niega si M06F_PG no esta definida (queda OMITIDA, exit 0);
  * solo acepta 127.0.0.1 / localhost / pg-b7 y una plantilla que empiece con
    'm06f_' -- nunca una base con datos;
  * crea una base NUEVA desde esa plantilla y la BORRA al final.

    M06F_PG=postgresql://postgres:CLAVE@127.0.0.1:55433/m06f_cero \\
        py -3.13 tests/test_m06f_integracion_postgres.py
================================================================================
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys
import uuid
from urllib.parse import urlparse

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

URL = os.environ.get("M06F_PG", "")
if not URL:
    print("[m06f_postgres] OMITIDA: definir M06F_PG con un Postgres DESCARTABLE.")
    raise SystemExit(0)
_u = urlparse(URL)
PLANTILLA = (_u.path or "/").lstrip("/")
if _u.hostname not in ("127.0.0.1", "localhost", "pg-b7") or not PLANTILLA.startswith("m06f_"):
    print(f"[m06f_postgres] NEGADA: {_u.hostname}/{PLANTILLA} no es un Postgres "
          f"local descartable con plantilla 'm06f_*'. No se toca nada.")
    raise SystemExit(2)

import psycopg                                                    # noqa: E402

BASE = f"m06f_prueba_{uuid.uuid4().hex[:8]}"
os.environ.update({"DBHOST": _u.hostname, "DBPORT": str(_u.port or 5432),
                   "DBNAME": BASE, "DBUSER": _u.username or "postgres",
                   "DBPASSWORD": _u.password or ""})
for v in ("DATABASE_URL", "MOTOR_SERVICE_TOKEN", "WISPHUB_API_KEY", "SMARTOLT_API_KEY"):
    os.environ.pop(v, None)

from nucleo.config import cargar_config                            # noqa: E402
from nucleo.herramientas import http as ejecutor_http              # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguridad import aprobacion as aprobaciones            # noqa: E402
from nucleo.seguridad import autonomia2                            # noqa: E402
from nucleo.seguridad.idempotencia import hash_de                  # noqa: E402

FALLOS: list[str] = []


def afirmar(c: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if c else "  [FALLA] ") + que)
    if not c:
        FALLOS.append(que)
        if detalle:
            print(f"          {detalle}")


def seccion(t: str) -> None:
    print(f"\n--- {t} ---")


def admin(base: str = "postgres"):
    return psycopg.connect(host=_u.hostname, port=_u.port or 5432, dbname=base,
                           user=_u.username, password=_u.password, autocommit=True)


def sql(q: str, p: tuple = (), *, replica: bool = False):
    """Como administrador de la base de prueba. 'replica' apaga los triggers
    de usuario: es la unica forma de simular a alguien que altera una fila
    por fuera del camino -- justo lo que el sello tiene que detectar."""
    with admin(BASE) as c:
        if replica:
            c.execute("set session_replication_role = replica")
        cur = c.execute(q, p)
        return cur.fetchall() if cur.description else None


# =============================================================================
#  DATOS  --  inventados; ninguna empresa, cliente ni equipo real
# =============================================================================

_BASE_CFG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
CONFIG = copy.deepcopy(_BASE_CFG)
CONFIG.variables_tenant = dict(CONFIG.variables_tenant or {},
                               SMARTOLT_SUBDOMINIO="https://smartolt.prueba.invalid")
TENANT = CONFIG.identidad.slug          # la config del motor usa este slug
OTRO = "empresa_b_prueba"
ORG = {TENANT: "00000000-0000-0000-0000-0000000f0001",
       OTRO: "00000000-0000-0000-0000-0000000f0002"}
H = {h.nombre: h for h in CONFIG.herramientas}
SN = "PRUEBA0M06F1"
ARGS_R3 = {"sn_onu": SN}
APROBADOR = "supervisor.prueba"

LECTURAS = {"consultar_senal_ont": {"onu_signal_1490_veredicto": "aceptable"},
            "ping_cliente": {"ping-exitoso": "3 de 3"},
            "consultar_estado_ont": {"last_status_change": "2026-09-22 09:00:00"}}


class _Resp:
    def __init__(self, cuerpo, status=200):
        self._c, self.status_code, self.ok = cuerpo, status, status < 400
        self.headers = {}
        self.text = json.dumps(cuerpo)

    def json(self):
        return self._c

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Red:
    def __init__(self):
        self.llamadas: list[tuple[str, str]] = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url))
        return _Resp({"status": True, "response": "comando de prueba aceptado"})

    def get(self, url, **kw):
        self.llamadas.append(("GET", url))
        return _Resp({})

    post = lambda self, url, **kw: self.request("POST", url, **kw)   # noqa: E731

    @property
    def escrituras(self):
        return [x for x in self.llamadas if x[0] != "GET"]


class Entorno:
    """Solo la red, las credenciales y las lecturas. TODO lo demas es la base."""

    def __init__(self):
        self.red = _Red()
        self._orig = {}

    def _ejecutar_tool(self, herramienta, sesion, argumentos, *a, **k):
        if herramienta.solo_lectura:
            return copy.deepcopy(LECTURAS[herramienta.nombre])
        return self._orig[(motor, "_ejecutar_tool")](herramienta, sesion, argumentos, *a, **k)

    def __enter__(self):
        from nucleo.canales import api
        parches = [(ejecutor_http, "requests", self.red),
                   (ejecutor_http.secretos, "obtener", lambda t, ref: "clave-de-prueba"),
                   (ejecutor_http.time, "sleep", lambda s: None),
                   (motor, "_ejecutar_tool", self._ejecutar_tool),
                   (api, "_config_de", lambda t: CONFIG)]
        for m, n, r in parches:
            self._orig[(m, n)] = getattr(m, n)
            setattr(m, n, r)
        return self

    def __exit__(self, *e):
        for (m, n), o in self._orig.items():
            setattr(m, n, o)
        return False


# =============================================================================
#  PREPARACION DE LA BASE DE PRUEBA
# =============================================================================

def preparar():
    with admin() as c:
        c.execute(f'create database "{BASE}" template "{PLANTILLA}"')
    for slug, org in ORG.items():
        sql("""insert into public.organization
                 (id, name, created_at, updated_at, api_key, is_active,
                  default_currency, address_line, city, company_name, country,
                  email, phone, postcode, state, tax_id, website, csat_enabled,
                  auto_close_children_on_parent_close, terminology, vertical, timezone)
               values (%s, %s, now(), now(), %s, true, 'COP', '', '', %s, 'CO', '',
                       '', '', '', '', '', false, false, '{}'::jsonb, 'isp', 'America/Bogota')""",
            (org, f"prueba {slug}", uuid.uuid4().hex, f"prueba {slug}"))
        sql("insert into asistente.tenant_config (slug, organization_id) values (%s, %s)",
            (slug, org))
        # La cadena autonoma EN REGLA, escrita como la escribiria cli/autonomia.py.
        sql("""insert into asistente.interruptor_autonomia (organization_id, estado, actor, motivo)
               values (%s, 'activo', 'cli:prueba', 'prueba M06-F')""", (org,))
        sql("""insert into asistente.nivel_autonomia (organization_id, nivel, actor, motivo, origen)
               values (%s, 2, 'cli:prueba', 'prueba M06-F', 'cli:prueba')""", (org,))
        for herr in ("reiniciar_ont", "registrar_pago"):
            sql("""insert into asistente.autorizacion_herramienta
                     (organization_id, herramienta, estado, nivel_maximo, autorizado_por, motivo)
                   values (%s, %s, 'autorizada', 2, 'jefe.prueba', 'prueba M06-F')""",
                (org, herr))
    os.environ[autonomia2.VAR_ETAPA] = "1"


def conversacion(slug: str, *, humano: bool = False) -> str:
    cid = str(uuid.uuid4())
    if humano:
        sql("""insert into asistente.conversations
                 (id, organization_id, canal, usuario_externo, estado, control,
                  control_motivo, asignada_a_usuario_id, asignada_a_nombre, datos_sesion,
                  id_cliente)
               values (%s, %s, 'whatsapp', %s, 'abierta', 'humano', 'intervencion',
                       %s, 'Operadora Prueba', %s, '999001')""",
            (cid, ORG[slug], f"prueba-{cid[:8]}", "11111111-1111-1111-1111-111111111111",
             json.dumps({"sn_onu": SN})))
    else:
        sql("""insert into asistente.conversations
                 (id, organization_id, canal, usuario_externo, estado)
               values (%s, %s, 'whatsapp', %s, 'abierta')""",
            (cid, ORG[slug], f"prueba-{cid[:8]}"))
    return cid


def proponer(slug: str, conv: str, herr: str = "reiniciar_ont", args=None,
             origen: str | None = None) -> str:
    """Lo que hace el motor al proponer una irreversible (M06-F: dentro de B5)."""
    args = dict(args or ARGS_R3)
    accion_id, ya = persistencia.guardar_accion_propuesta(
        slug, herr, args, f"prueba {herr}", "soporte", "cliente-prueba", conv, None,
        hash_argumentos=hash_de(args), origen=origen or f"evento:{uuid.uuid4()}",
        contexto={"sesion": {"sn_onu": SN, "id_cliente": "999001"}, "previas": {}})
    assert not ya
    return accion_id


def fila(slug: str, accion_id: str) -> dict:
    return persistencia.accion_propuesta_de(slug, accion_id) or {}


def aprobar(slug: str, accion_id: str, quien: str = APROBADOR):
    """El endpoint de aprobacion, sin HTTP: el mismo cuerpo que corre Flask."""
    from nucleo.canales import api
    with api.app.test_request_context():
        salida = api._aprobar_y_ejecutar(CONFIG, slug, accion_id, quien)
        r, cod = salida if isinstance(salida, tuple) else (salida, 200)
        return r.get_json(), cod


def eventos(accion_id: str) -> list[str]:
    return [f[0] for f in sql("select tipo from asistente.acciones_eventos "
                              "where accion_id = %s order by creado_en", (accion_id,))]


def violacion(q: str, p: tuple) -> str:
    try:
        sql(q, p)
        return ""
    except psycopg.Error as e:
        return str(e).split("\n")[0]


# =============================================================================
#  PRUEBAS
# =============================================================================

def main() -> int:
    print("=" * 78)
    print(f"  M06-F contra PostgreSQL descartable ({_u.hostname}/{BASE})")
    print("=" * 78)
    creada = False
    try:
        preparar()
        creada = True
        conv = conversacion(TENANT)

        seccion("0. Una sola maquina: la propuesta vinculante vive en la cola de B5")
        pid = proponer(TENANT, conv)
        f = fila(TENANT, pid)
        afirmar(f.get("estado") == "pendiente" and f.get("hash_argumentos") == hash_de(ARGS_R3)
                and f.get("origen", "").startswith("evento:") and not f.get("sello_aprobacion"),
                "nace 'pendiente' en acciones_propuestas, con huella y origen, sin sello")
        afirmar(str(f.get("conversation_id")) == conv and f.get("clave_equivalencia"),
                "ligada a su conversacion con la clave de equivalencia de B5 (T12)")
        otra, ya = persistencia.guardar_accion_propuesta(
            TENANT, "reiniciar_ont", dict(ARGS_R3), "x", "soporte", "c", conv, None,
            hash_argumentos=hash_de(ARGS_R3), origen="evento:repetido", contexto={})
        afirmar(ya and otra == pid, "proponer lo mismo otra vez devuelve LA MISMA (dedup B5)")
        n_trig = sql("""select count(*) from pg_trigger t join pg_class r on r.oid=t.tgrelid
                        where r.relname='acciones_propuestas' and not t.tgisinternal""")[0][0]
        afirmar(n_trig == 1, f"un solo trigger propio sobre acciones_propuestas ({n_trig})")

        seccion("13.1 SIN aprobacion -> bloqueada, cero efecto")
        with Entorno() as e:
            res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila(TENANT, pid), TENANT)
        afirmar(cod == aprobaciones.NO_APROBADA and e.red.llamadas == [],
                f"la fila 'pendiente' no autoriza nada -> {cod}, {len(e.red.llamadas)} llamadas")
        with Entorno() as e:
            try:
                ejecutor_http.ejecutar(H["reiniciar_ont"], dict(ARGS_R3), TENANT,
                                       CONFIG.variables_tenant)
                cod = None
            except Exception as ex:                                  # noqa: BLE001
                cod = getattr(ex, "codigo", type(ex).__name__)
        afirmar(cod and e.red.llamadas == [],
                f"el ejecutor directo, sin permiso -> {cod}, {len(e.red.llamadas)} llamadas")
        err = violacion("update asistente.acciones_propuestas set sello_aprobacion='x' "
                        "where id=%s", (pid,))
        afirmar("sello" in err, f"la base no deja sellar a mano una pendiente: {err[:70]}")

        seccion("13.2 CON aprobacion valida -> aprobacion, autorizacion, idempotencia, "
                "frontera, efecto")
        with Entorno() as e:
            cuerpo, http = aprobar(TENANT, pid)
        f = fila(TENANT, pid)
        afirmar(http == 200 and cuerpo.get("ok") and len(e.red.escrituras) == 1
                and "reboot" in e.red.escrituras[0][1],
                f"aprobar -> HTTP {http}, {len(e.red.escrituras)} escritura(s) {e.red.escrituras}")
        esperado = aprobaciones.sello_de(tenant=TENANT, organization_id=ORG[TENANT],
                                         herramienta="reiniciar_ont", origen=f["origen"],
                                         huella=hash_de(ARGS_R3), aprobador=APROBADOR)
        afirmar(f.get("estado") == "ejecutada_ok" and f.get("revisado_por") == APROBADOR
                and f.get("sello_aprobacion") == esperado,
                "la fila termina 'ejecutada_ok' con el aprobador y el sello de ESA operacion")
        ev = eventos(pid)
        afirmar(ev and ev[-1] == "accion_aprobada", f"evento B5 del desenlace: {ev}")
        ops = sql("select estado from asistente.operaciones_externas where herramienta = "
                  "'reiniciar_ont' and origen = %s", (f"accion_aprobada:{pid}",))
        afirmar(ops == [("exitosa",)], f"el registro de operaciones externas la anota: {ops}")
        bit = sql("select decision from asistente.ejecucion_autonoma where herramienta="
                  "'reiniciar_ont' and organization_id=%s", (ORG[TENANT],))
        afirmar(bool(bit), f"la bitacora de la frontera registra la puerta critica: {bit}")
        ver = sql("select count(*) from asistente.verificaciones_accion where conversation_id=%s",
                  (conv,)) if sql("select to_regclass('asistente.verificaciones_accion')")[0][0] \
            else [(None,)]
        afirmar(ver[0][0] in (1, None), f"la verificacion del reinicio queda anotada: {ver}")

        seccion("13.6 Aprobacion reutilizada -> bloqueada")
        with Entorno() as e:
            cuerpo, http = aprobar(TENANT, pid)
        afirmar(http == 409 and e.red.llamadas == [],
                f"aprobar otra vez la misma -> HTTP {http} ({cuerpo.get('codigo')}), "
                f"{len(e.red.llamadas)} llamadas")
        with Entorno() as e:
            res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila(TENANT, pid), TENANT)
        afirmar(cod == aprobaciones.NO_APROBADA and e.red.llamadas == [],
                f"la fila ya usada no autoriza otra ejecucion -> {cod}")
        err = violacion("update asistente.acciones_propuestas set estado='ejecutando' "
                        "where id=%s", (pid,))
        afirmar("no se reescribe" in err, f"la base no deja reabrir un desenlace: {err[:70]}")
        #  El sello de UNA propuesta copiado a otra, con los mismos argumentos.
        conv2 = conversacion(TENANT)
        p2 = proponer(TENANT, conv2)
        persistencia.reservar_accion(TENANT, p2, APROBADOR)
        sql("update asistente.acciones_propuestas set sello_aprobacion=%s where id=%s",
            (f["sello_aprobacion"], p2), replica=True)
        with Entorno() as e:
            res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila(TENANT, p2), TENANT)
        afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
                f"el sello de otra aprobacion (mismos argumentos, otro origen) -> {cod}")

        seccion("13.3 Argumentos modificados -> bloqueada")
        conv3 = conversacion(TENANT)
        p3 = proponer(TENANT, conv3)
        err = violacion("update asistente.acciones_propuestas set argumentos=%s where id=%s",
                        (json.dumps({"sn_onu": "OTRA0000000X"}), p3))
        afirmar("identidad" in err, f"la base no deja cambiar los argumentos: {err[:70]}")
        persistencia.reservar_accion(TENANT, p3, APROBADOR)
        sql("update asistente.acciones_propuestas set argumentos=%s where id=%s",
            (json.dumps({"sn_onu": "OTRA0000000X"}), p3), replica=True)
        with Entorno() as e:
            res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila(TENANT, p3), TENANT)
        afirmar(cod == aprobaciones.OTROS_ARGUMENTOS and e.red.llamadas == [],
                f"argumentos cambiados por fuera del camino (trigger apagado) -> {cod}, "
                f"{len(e.red.llamadas)} llamadas")

        seccion("13.4 Tenant diferente -> bloqueada")
        conv4 = conversacion(TENANT)
        p4 = proponer(TENANT, conv4)
        afirmar(persistencia.accion_propuesta_de(OTRO, p4) is None,
                "la otra empresa no ve la propuesta (RLS de acciones_propuestas)")
        r = persistencia.reservar_accion(OTRO, p4, APROBADOR)
        afirmar(r == {"ok": False, "motivo": "no_existe"},
                f"ni puede aprobarla: {r}")
        persistencia.reservar_accion(TENANT, p4, APROBADOR)
        with Entorno() as e:
            res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila(TENANT, p4), OTRO)
        afirmar(cod in (aprobaciones.OTRO_TENANT, aprobaciones.ALTERADA)
                and e.red.llamadas == [],
                f"la aprobacion de una empresa ejecutada como otra -> {cod}")

        seccion("13.5 Origen diferente -> bloqueada")
        sql("update asistente.acciones_propuestas set origen='evento:otro' where id=%s",
            (p4,), replica=True)
        with Entorno() as e:
            res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila(TENANT, p4), TENANT)
        afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
                f"origen cambiado despues de aprobar -> {cod}")
        err = violacion("update asistente.acciones_propuestas set origen='evento:x' "
                        "where id=%s", (p4,))
        afirmar("identidad" in err, f"y la base no deja cambiarlo por el camino: {err[:70]}")

        seccion("Kill switch y techo con la aprobacion en regla -> bloqueada, 'vencida'")
        conv5 = conversacion(TENANT)
        p5 = proponer(TENANT, conv5)
        sql("""insert into asistente.interruptor_autonomia (organization_id, estado,
                 estado_anterior, actor, motivo)
               values (%s, 'detenido', 'activo', 'cli:prueba', 'prueba M06-F')""",
            (ORG[TENANT],))
        with Entorno() as e:
            cuerpo, http = aprobar(TENANT, p5)
        afirmar(http == 409 and e.red.llamadas == [] and fila(TENANT, p5).get("estado") == "vencida"
                and fila(TENANT, p5).get("codigo_error"),
                f"kill switch detenido -> HTTP {http}, {cuerpo.get('codigo')}, "
                f"{len(e.red.llamadas)} llamadas, fila "
                f"'{fila(TENANT, p5).get('estado')}'")
        sql("""insert into asistente.interruptor_autonomia (organization_id, estado,
                 estado_anterior, actor, motivo)
               values (%s, 'activo', 'detenido', 'cli:prueba', 'prueba M06-F')""",
            (ORG[TENANT],))
        sql("""insert into asistente.nivel_autonomia (organization_id, nivel, nivel_anterior,
                 actor, motivo, origen)
               values (%s, 1, 2, 'cli:prueba', 'prueba M06-F', 'cli:prueba')""", (ORG[TENANT],))
        conv6 = conversacion(TENANT)
        p6 = proponer(TENANT, conv6)
        with Entorno() as e:
            cuerpo, http = aprobar(TENANT, p6)
        afirmar(http == 409 and e.red.llamadas == []
                and "TECHO" in (cuerpo.get("codigo") or ""),
                f"techo 1 < nivel 2 exigido -> HTTP {http}, {cuerpo.get('codigo')}")
        sql("""insert into asistente.nivel_autonomia (organization_id, nivel, nivel_anterior,
                 actor, motivo, origen)
               values (%s, 2, 1, 'cli:prueba', 'prueba M06-F', 'cli:prueba')""", (ORG[TENANT],))

        seccion("Liberar y rechazar respetan la aprobacion")
        conv7 = conversacion(TENANT)
        p7 = proponer(TENANT, conv7)
        persistencia.reservar_accion(TENANT, p7, APROBADOR)
        afirmar(bool(fila(TENANT, p7).get("sello_aprobacion")), "reservada: con sello")
        afirmar(not persistencia.resolver_accion_propuesta(TENANT, p7, "rechazada", "otro"),
                "rechazar NO pisa una accion ya aprobada (compare-and-set sobre 'pendiente')")
        persistencia.liberar_accion(TENANT, p7, "prueba")
        f7 = fila(TENANT, p7)
        afirmar(f7.get("estado") == "pendiente" and not f7.get("sello_aprobacion")
                and not f7.get("revisado_por"),
                "liberar la devuelve a 'pendiente' y el trigger le borra el sello")
        afirmar(persistencia.resolver_accion_propuesta(TENANT, p7, "rechazada", "otro", "no"),
                "una pendiente si se puede rechazar")

        seccion("El boton de reinicio de la Bandeja: la MISMA cadena")
        from nucleo.canales import api
        conv8 = conversacion(TENANT, humano=True)
        cuerpo_req = {"tenant": TENANT, "motivo": "el cliente pide reinicio, prueba",
                      "autor": "Operadora Prueba",
                      "autor_usuario_id": "11111111-1111-1111-1111-111111111111",
                      "autor_rol": "USER"}
        with Entorno() as e:
            r = api.app.test_client().post(f"/conversaciones/{conv8}/equipo/reiniciar",
                                           json=cuerpo_req)
        cuerpo = r.get_json() or {}
        acc = sql("select id, estado, revisado_por, sello_aprobacion is not null, origen "
                  "from asistente.acciones_propuestas where conversation_id=%s", (conv8,))
        afirmar(r.status_code == 200 and len(e.red.escrituras) == 1 and len(acc) == 1
                and acc[0][1] == "ejecutada_ok" and acc[0][2] == "Operadora Prueba"
                and acc[0][3] and acc[0][4].startswith("bandeja:"),
                f"el boton deja UNA accion en la cola, aprobada y sellada por quien lo "
                f"aprieta, y sale UNA vez -> HTTP {r.status_code}, {acc}, "
                f"{len(e.red.escrituras)} escrituras")
        sql("""insert into asistente.interruptor_autonomia (organization_id, estado,
                 estado_anterior, actor, motivo)
               values (%s, 'detenido', 'activo', 'cli:prueba', 'prueba M06-F')""",
            (ORG[TENANT],))
        conv9 = conversacion(TENANT, humano=True)
        with Entorno() as e:
            r = api.app.test_client().post(f"/conversaciones/{conv9}/equipo/reiniciar",
                                           json=cuerpo_req)
        afirmar(r.status_code == 409 and e.red.llamadas == [],
                f"con el kill switch detenido el boton tampoco reinicia -> HTTP "
                f"{r.status_code}, {(r.get_json() or {}).get('codigo')}, "
                f"{len(e.red.llamadas)} llamadas")
        sql("""insert into asistente.interruptor_autonomia (organization_id, estado,
                 estado_anterior, actor, motivo)
               values (%s, 'activo', 'detenido', 'cli:prueba', 'prueba M06-F')""",
            (ORG[TENANT],))

        seccion("El camino COMUN de B5 sigue igual (sin huella, sin sello)")
        conv10 = conversacion(TENANT)
        comun_args = {"asunto": "prueba", "descripcion": "prueba M06-F"}
        cid, _ = persistencia.guardar_accion_propuesta(
            TENANT, "crear_ticket", comun_args, "ticket", "soporte", "c", conv10, None)
        fc = fila(TENANT, cid)
        afirmar(not fc.get("hash_argumentos") and not fc.get("origen"),
                "una propuesta comun no guarda huella ni origen")
        r = persistencia.reservar_accion(TENANT, cid, APROBADOR)
        afirmar(r["ok"] and not fila(TENANT, cid).get("sello_aprobacion"),
                "y se reserva como en B5, sin sello")
    finally:
        os.environ.pop(autonomia2.VAR_ETAPA, None)
        if creada or True:
            try:
                with admin() as c:
                    c.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                              "where datname = %s and pid <> pg_backend_pid()", (BASE,))
                    c.execute(f'drop database if exists "{BASE}"')
                print(f"\n  (base {BASE} borrada)")
            except Exception as e:                                   # noqa: BLE001
                print(f"\n  [aviso] no se pudo borrar {BASE}: {e}")

    print()
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for x in FALLOS:
            print(f"    - {x}")
        return 1
    print("  [OK] Una sola cadena: la cola B5 aprueba, el sello ata, la base lo sostiene.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
