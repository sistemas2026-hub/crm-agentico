# -*- coding: utf-8 -*-
"""
================================================================================
 UN TENANT NUEVO NACE CON SU INTERRUPTOR, Y NACE DETENIDO
================================================================================

    py -3.13 tests/test_alta_tenant_autonomia.py

POR QUE EXISTE
--------------
La verificacion previa a produccion (15/09/2026) midio el escenario H: una
empresa dada de alta DESPUES de la migracion no tenia fila de interruptor, y el
gate --haciendo lo correcto-- la bloqueaba con 'sin_registro'. En silencio, y
sin que nada dijera como arreglarlo.

La correccion no es que alguien se acuerde de correr cli/autonomia.py: es que
el alta escriba la fila en la MISMA transaccion que crea el tenant. Un tenant
valido sin registro de autonomia no puede existir.

QUE SE AFIRMA
-------------
El efecto, no la presencia. Que la fila quede con el estado y el actor
correctos; que correr el alta de nuevo no duplique; que con esa fila una
escritura quede bloqueada y una LECTURA siga andando; y que la fila de una
empresa no diga nada sobre otra.

Y una que es facil de olvidar: que el INSERT ocurra ANTES del commit. Si
quedara despues seria un segundo paso disfrazado de atomico -- exactamente el
agujero que esto viene a tapar.

CORRE SIN BASE DE DATOS
-----------------------
El cursor se sustituye por uno en memoria que respeta la semantica del
'where not exists' -- no un doble que devuelve lo que se le pide. El SQL que se
ejercita es el de nucleo/seguridad/interruptor.py, sin reescribir.
================================================================================
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.persistencia import db as persistencia                # noqa: E402
from nucleo.seguridad import interruptor                          # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


def seccion(titulo: str) -> None:
    print(f"\n--- {titulo} ---")


ORG_UNO = "11111111-1111-1111-1111-111111111111"
ORG_DOS = "22222222-2222-2222-2222-222222222222"


class CursorEnMemoria:
    """
    Ejecuta el INSERT de interruptor.sembrar() contra una lista.

    Respeta el 'where not exists': si ya hay fila para esa organizacion, no
    escribe y deja rowcount en 0, igual que haria Postgres. Es lo unico que
    hace falta emular para que el codigo real corra tal cual.
    """

    def __init__(self):
        self.filas: list[dict] = []
        self.sql: list[tuple] = []
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.sql.append((" ".join(sql.split()), params))
        s = " ".join(sql.split()).lower()
        if "insert into asistente.interruptor_autonomia" in s:
            org, estado, actor, motivo, org_guarda = params
            if "where not exists" in s and any(
                    f["organization_id"] == org_guarda for f in self.filas):
                self.rowcount = 0
                return
            self.filas.append({"organization_id": org, "estado": estado,
                               "estado_anterior": None, "actor": actor,
                               "motivo": motivo})
            self.rowcount = 1
            return
        self.rowcount = 0

    def fetchone(self):
        return None


# ===========================================================================
seccion("1-4. el alta escribe la fila, detenida, con actor y motivo")

cur = CursorEnMemoria()
escribio = interruptor.sembrar(cur, ORG_UNO, actor="alta_de_tenant",
                              motivo="Alta de 'nueva_isp' (config v1)")

afirmar(escribio is True, "sembrar() informa que escribio la fila")
afirmar(len(cur.filas) == 1, f"2 · quedo UNA fila de autonomia ({len(cur.filas)})")

fila = cur.filas[0] if cur.filas else {}
afirmar(fila.get("estado") == "detenido",
        f"3 · el estado es 'detenido', no 'activo' ({fila.get('estado')})")
afirmar(fila.get("estado") == interruptor.DETENIDO,
        "   y sale de la constante del modulo, no de un literal suelto")
afirmar(fila.get("actor") == "alta_de_tenant",
        f"4 · el actor dice de donde salio ({fila.get('actor')})")
afirmar("nueva_isp" in (fila.get("motivo") or ""),
        f"   y el motivo nombra al tenant ({fila.get('motivo')})")

# ===========================================================================
seccion("8. reejecutar el alta NO duplica")

antes = len(cur.filas)
otra_vez = interruptor.sembrar(cur, ORG_UNO, actor="alta_de_tenant",
                              motivo="segundo intento")
afirmar(otra_vez is False, "sembrar() informa que no escribio nada")
afirmar(len(cur.filas) == antes,
        f"sigue habiendo {antes} fila(s), no {len(cur.filas)}")
afirmar(cur.filas[0]["motivo"] != "segundo intento",
        "y la fila original queda intacta -- no se pisa el motivo")

# Una tercera pasada tampoco, y el guard esta en el SQL, no en Python.
interruptor.sembrar(cur, ORG_UNO, actor="x", motivo="tercer intento")
afirmar(len(cur.filas) == 1, f"tercera pasada: sigue en 1 ({len(cur.filas)})")
afirmar(any("where not exists" in s.lower() for s, _ in cur.sql),
        "el guard vive en el SQL ('where not exists'), no en un if de Python "
        "-- dos procesos a la vez chocan contra la base, no contra memoria")

# ===========================================================================
seccion("7. la fila de una empresa no dice nada de otra")

interruptor.sembrar(cur, ORG_DOS, actor="alta_de_tenant",
                    motivo="Alta de 'otra_isp' (config v1)")
afirmar(len(cur.filas) == 2, f"la segunda empresa SI recibe la suya ({len(cur.filas)})")
afirmar({f["organization_id"] for f in cur.filas} == {ORG_UNO, ORG_DOS},
        "una por organizacion, cada una con su id")

# ===========================================================================
seccion("1. el alta de cli/cargar_config.py lo hace, y ANTES del commit")
# El INSERT tiene que ocurrir dentro de la transaccion que crea el tenant. Si
# quedara despues del commit seria un segundo paso disfrazado de atomico.

import cli.cargar_config as cc                                    # noqa: E402


class CursorDeAlta:
    """Cursor de mentira para el camino de alta: nunca encuentra tenant previo,
    asi que cargar() toma la rama que crea uno nuevo."""

    def __init__(self, diario):
        self.diario = diario
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.diario.append(("sql", " ".join(sql.split())))

    def fetchone(self):
        # Ni vinculo previo en tenant_config, ni fila de config: asi cargar()
        # toma la rama que CREA un tenant, que es la que hay que probar.
        return None

    def fetchall(self):
        # _organizacion() cae a "la unica organizacion del CRM" cuando el slug
        # todavia no esta vinculado. Devolver exactamente una es lo que hace
        # que el alta pueda continuar sin pedir --org-id.
        return [("11111111-1111-1111-1111-111111111111", "Empresa de prueba")]

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


class ConexionDeAlta:
    def __init__(self, diario):
        self.diario = diario
        self._cur = CursorDeAlta(diario)

    def cursor(self):
        return self._cur

    def commit(self):
        self.diario.append(("commit", ""))

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


diario: list[tuple] = []
conectar_original = cc._conectar
sin_empujar_original = cc.editor.commits_sin_empujar
atrasados_original = cc.editor.commits_atrasados
#  M06-F: en origin el guardia se volvio una sola funcion que ademas mira la
#  rama que despliega (RAMA_DESPLIEGUE). Mismo criterio: aca no se prueba eso.
problemas_original = getattr(cc.editor, "problemas_de_alineacion_git", None)
try:
    cc._conectar = lambda: ConexionDeAlta(diario)
    # El guardia de alineacion con git es otro asunto y tiene su propia prueba
    # (tests/test_guarda_alineacion_git.py); aca se lo deja conforme para poder
    # llegar a la rama de alta. Las DOS funciones, y devuelven un entero -- con
    # una sola, o con una tupla, el guardia sigue abortando.
    cc.editor.commits_sin_empujar = lambda: 0
    cc.editor.commits_atrasados = lambda: 0
    if problemas_original is not None:
        cc.editor.problemas_de_alineacion_git = lambda *a, **k: []
    cc.cargar(RAIZ / "tenants" / "rapilink.config.yaml")
    corrio = True
except SystemExit as e:
    corrio = False
    print(f"          cargar() salio con SystemExit: {e}")
finally:
    cc._conectar = conectar_original
    cc.editor.commits_sin_empujar = sin_empujar_original
    cc.editor.commits_atrasados = atrasados_original
    if problemas_original is not None:
        cc.editor.problemas_de_alineacion_git = problemas_original

sentencias = [s for tipo, s in diario if tipo == "sql"]
tipos = [tipo for tipo, _ in diario]

afirmar(corrio, "cargar() llego hasta el final por la rama de alta")
afirmar(any("insert into asistente.tenant_config" in s.lower() for s in sentencias),
        "crea la fila de tenant_config (es la rama de alta, no la de update)")
afirmar(any("insert into asistente.interruptor_autonomia" in s.lower()
            for s in sentencias),
        "y crea tambien la fila del interruptor")

if "commit" in tipos:
    i_interruptor = next((i for i, (tipo, s) in enumerate(diario)
                          if tipo == "sql"
                          and "insert into asistente.interruptor_autonomia" in s.lower()),
                         None)
    i_commit = tipos.index("commit")
    afirmar(i_interruptor is not None and i_interruptor < i_commit,
            f"el interruptor se escribe ANTES del commit "
            f"(posicion {i_interruptor} vs commit en {i_commit}) -- si fuera "
            f"despues, no seria atomico")
else:
    afirmar(False, "no hubo commit: el camino de alta no se completo")

# Y que lo que escribe sea 'detenido'. Se mira el SQL que de verdad se mando.
sql_interruptor = [s for s in sentencias
                   if "insert into asistente.interruptor_autonomia" in s.lower()]
afirmar(bool(sql_interruptor) and "select %s, %s, null, %s, %s" in sql_interruptor[0],
        "con la forma parametrizada de sembrar() -- el estado viaja como "
        "parametro, no pegado en el SQL")

# ===========================================================================
seccion("5 y 6. con el tenant recien creado: la escritura se frena, la "
        "lectura no")

from nucleo.config import cargar_config                           # noqa: E402
from nucleo.herramientas import http as ejecutor_http             # noqa: E402
from nucleo.modelo import motor                                   # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")


class SesionDePrueba:
    verificado = True
    nivel = 99
    id_cliente = "5832"
    sn_onu = "HWTCAF721761"
    interfaz_lan = ""
    identificador_canal = "573000000000"
    rol_siguiente = None


llamadas: list[str] = []
originales = {
    "http": ejecutor_http.ejecutar,
    "http_async": ejecutor_http.ejecutar_asincrono,
    "estado": persistencia.estado_autonomia,
    "auditoria": persistencia.registrar_auditoria,
    # El registro de operaciones externas TAMBIEN se sustituye. Sin esto, la
    # parte que ejecuta de verdad abria una sesion contra la base del .env --
    # que en esta maquina es PRODUCCION. Ninguna prueba de tests/ puede
    # depender de eso, ni por un camino que "total falla".
    "reclamar": persistencia.reclamar_operacion_externa,
    "finalizar": persistencia.finalizar_operacion_externa,
}
try:
    ejecutor_http.ejecutar = lambda h, a, t=None, v=None: (
        llamadas.append(h.nombre), {"status": True})[1]
    ejecutor_http.ejecutar_asincrono = lambda h, a, tenant=None, variables_tenant=None: (
        llamadas.append(h.nombre), {"status": True})[1]
    persistencia.registrar_auditoria = lambda *a, **k: None
    #  AUTONOMIA 2 (19/09/2026): una escritura autonoma necesita ademas la
    #  etapa, el prerequisito de B-7 y una autorizacion granular. Este archivo
    #  prueba el ALTA DE UN TENANT con la autonomia detenida por omision; se
    #  declaran las respuestas de la base para que lo que decida siga siendo
    #  el interruptor, que es lo que el archivo dice probar.
    os.environ["AUTONOMIA_2_ACTIVA"] = "1"
    persistencia.secreto_jwt_en_base = lambda: ""
    persistencia.nivel_autonomia = lambda t: {
        "nivel": 2, "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba", "actor": "prueba", "motivo": "",
        "creado_en": None}
    persistencia.autorizacion_herramienta = lambda t, h: {
        "id": "00000000-0000-0000-0000-000000000001", "herramienta": h,
        "estado": "autorizada", "estado_anterior": None, "nivel_maximo": 2,
        "vigente_desde": None, "vigente_hasta": None,
        "autorizado_por": "prueba", "motivo": "", "limites": {},
        "creado_en": None}
    persistencia.registrar_ejecucion_autonoma = lambda *a, **k: None
    persistencia.reclamar_operacion_externa = (
        lambda *a, **k: {"decision": "ejecutar", "fila": {"intentos": 1}})
    persistencia.finalizar_operacion_externa = lambda *a, **k: None
    # Lo que la base contestaria para un tenant recien dado de alta.
    persistencia.estado_autonomia = lambda t: {
        "estado": "detenido", "estado_anterior": None,
        "actor": "alta_de_tenant", "motivo": "Alta de 'nueva_isp' (config v1)",
        "creado_en": None}

    escritura = next(h for h in CONFIG.herramientas if h.nombre == "reiniciar_ont")
    try:
        motor._ejecutar_tool(escritura, SesionDePrueba(), {"servicio": "5832"},
                             "nueva_isp", CONFIG.variables_tenant, origen="alta")
        bloqueada = False
    except motor.AutonomiaDetenida:
        bloqueada = True
    afirmar(bloqueada,
            "5 · una accion autonoma queda bloqueada en el tenant recien creado")
    afirmar(llamadas == [],
            f"   y nada salio al proveedor ({llamadas})")

    lectura = next(h for h in CONFIG.herramientas
                   if h.tipo == "http" and h.solo_lectura)
    motor._ejecutar_tool(lectura, SesionDePrueba(), {}, "nueva_isp",
                         CONFIG.variables_tenant, origen="alta")
    afirmar(llamadas == [lectura.nombre],
            f"6 · una consulta de solo lectura SIGUE funcionando ({llamadas})")

    # 7 (la otra mitad): otra empresa, con su propio estado, no se ve afectada.
    llamadas.clear()
    persistencia.estado_autonomia = lambda t: (
        {"estado": "detenido", "estado_anterior": None, "actor": "alta_de_tenant",
         "motivo": "", "creado_en": None} if t == "nueva_isp" else
        {"estado": "activo", "estado_anterior": None, "actor": "migracion",
         "motivo": "", "creado_en": None})
    motor._ejecutar_tool(escritura, SesionDePrueba(), {"servicio": "5832"},
                         "otra_isp", CONFIG.variables_tenant, origen="alta")
    afirmar(llamadas == ["reiniciar_ont"],
            f"7 · la empresa de al lado, con su interruptor activo, ejecuta "
            f"normal ({llamadas})")
finally:
    ejecutor_http.ejecutar = originales["http"]
    ejecutor_http.ejecutar_asincrono = originales["http_async"]
    persistencia.estado_autonomia = originales["estado"]
    persistencia.registrar_auditoria = originales["auditoria"]
    persistencia.reclamar_operacion_externa = originales["reclamar"]
    persistencia.finalizar_operacion_externa = originales["finalizar"]

# ===========================================================================
print()
if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] Un tenant nuevo nace con su interruptor, detenido, y sin duplicar.")
