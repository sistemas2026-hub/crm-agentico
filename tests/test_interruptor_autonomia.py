# -*- coding: utf-8 -*-
"""
================================================================================
 EL INTERRUPTOR DE AUTONOMIA  --  que detenga de verdad, y que no apague de mas
================================================================================

    py -3.13 tests/test_interruptor_autonomia.py

POR QUE EXISTE
--------------
Un interruptor de emergencia que no se prueba es peor que no tenerlo: da la
tranquilidad sin dar la garantia. Lo que hay que demostrar son dos cosas
opuestas a la vez --

    detenido    NINGUNA escritura externa sale, ni por el modelo, ni por otro
                servicio, ni por el reloj, ni por el scheduler;
    detenido    las consultas de lectura SIGUEN andando, porque un interruptor
                que deja a los clientes sin atencion no se usa nunca.

LO QUE SE AFIRMA ES EL EFECTO, NO EL MECANISMO
----------------------------------------------
Nada de esto comprueba que exista una funcion, una bandera o una tabla. Lo que
se cuenta es cuantas veces se llamo al ejecutor HTTP: cero cuando el
interruptor esta tirado, una cuando no. Es la leccion de CLAUDE.md -- una
prueba que afirma que un mecanismo EXISTE sobrevive intacta a que el mecanismo
se invierta.

CORRE SIN BASE Y SIN RED
------------------------
Todo lo que toca Postgres se sustituye. El interruptor real lee una fila; aca
esa lectura la contesta un diccionario, y lo que se ejercita es el codigo que
decide con esa respuesta.

LO QUE ESTE ARCHIVO NO PRUEBA
-----------------------------
Que la tabla exista en produccion con sus grants y su politica de RLS. Eso lo
dice la migracion (supabase/202609151710_interruptor_autonomia.sql) y se
verifica aplicandola, no desde aca.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                          # noqa: E402
from nucleo.herramientas import http as ejecutor_http            # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402
from nucleo.persistencia import db as persistencia               # noqa: E402
from nucleo.seguridad import interruptor                         # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


def seccion(titulo: str) -> None:
    print(f"\n--- {titulo} ---")


def herramienta(nombre: str):
    h = next((x for x in CONFIG.herramientas if x.nombre == nombre), None)
    assert h is not None, f"'{nombre}' no esta en el catalogo del tenant"
    return h


# ---------------------------------------------------------------------------
#  EL BANCO DE PRUEBAS
# ---------------------------------------------------------------------------
#  'estado' es lo que contesta la base cuando se le pregunta por el
#  interruptor: una fila, None (no hay), o una excepcion (no se pudo leer).
# ---------------------------------------------------------------------------

class Banco:
    """Sustituye la base y cuenta las llamadas externas de verdad."""

    def __init__(self, fila, *, revienta=None):
        self.fila = fila
        self.revienta = revienta
        self.llamadas_http: list[str] = []
        self.auditoria: list[dict] = []
        self.transiciones: list[dict] = []
        self.operaciones: dict[str, dict] = {}
        self._originales: dict = {}

    # --- lo que la base contestaria -------------------------------------
    def _estado(self, tenant):
        if self.revienta is not None:
            raise self.revienta
        return self.fila

    def _transicion(self, tenant, estado, anterior, actor, motivo):
        fila = {"estado": estado, "estado_anterior": anterior, "actor": actor,
                "motivo": motivo, "creado_en": None}
        self.transiciones.append(fila)
        self.fila = fila
        return fila

    def _auditar(self, tenant, actor, accion, recurso, resultado,
                 motivo_denegacion=None):
        self.auditoria.append({"actor": actor, "accion": accion,
                               "recurso": recurso, "resultado": resultado,
                               "motivo_denegacion": motivo_denegacion})

    # --- el registro de operaciones externas, minimo -------------------
    #  Aca no se prueba la idempotencia (eso es tests/test_idempotencia_
    #  externa.py): solo hace falta que no estorbe, dejando pasar siempre.
    def _reclamar(self, tenant, clave, herr, huella, origen, vence,
                  reintentar_fallida=False):
        self.operaciones[clave] = {"herramienta": herr, "origen": origen}
        return {"decision": "ejecutar", "fila": {"intentos": 1}}

    def _finalizar(self, *a, **k):
        return None

    # --- la llamada externa de verdad ----------------------------------
    def _http(self, herr, argumentos, tenant=None, variables_tenant=None):
        self.llamadas_http.append(herr.nombre)
        return {"status": True, "response": "hecho"}

    def __enter__(self):
        parches = [
            (persistencia, "estado_autonomia", self._estado),
            (persistencia, "registrar_transicion_autonomia", self._transicion),
            (persistencia, "registrar_auditoria", self._auditar),
            (persistencia, "historial_autonomia",
             lambda t, limite=50: list(reversed(self.transiciones))),
            (persistencia, "reclamar_operacion_externa", self._reclamar),
            (persistencia, "finalizar_operacion_externa", self._finalizar),
            #  AUTONOMIA 2 (19/09/2026). Desde ese bloque, una escritura
            #  autonoma necesita ademas la etapa encendida, el prerequisito de
            #  B-7 y una autorizacion granular. Este archivo prueba el KILL
            #  SWITCH, no la autorizacion: se declaran las respuestas de la
            #  base para que lo que decida siga siendo el interruptor.
            #  El orden de frontera.autonoma() lo garantiza -- el interruptor
            #  se consulta ANTES, asi que con DETENIDO el motivo del bloqueo
            #  sigue siendo el suyo y no el de Autonomia 2.
            (persistencia, "secreto_jwt_en_base", lambda: ""),
            (persistencia, "nivel_autonomia", lambda t: {
                "nivel": 2, "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba", "actor": "prueba",
                "motivo": "", "creado_en": None}),
            (persistencia, "autorizacion_herramienta", lambda t, h: {
                "id": "00000000-0000-0000-0000-000000000001", "herramienta": h,
                "estado": "autorizada", "estado_anterior": None,
                "nivel_maximo": 2, "vigente_desde": None,
                "vigente_hasta": None, "autorizado_por": "prueba",
                "motivo": "", "limites": {}, "creado_en": None}),
            (persistencia, "registrar_ejecucion_autonoma",
             lambda *a, **k: None),
            (ejecutor_http, "ejecutar", self._http),
            (ejecutor_http, "ejecutar_asincrono",
             lambda h, a, tenant=None, variables_tenant=None: self._http(h, a, tenant)),
        ]
        for modulo, nombre, reemplazo in parches:
            self._originales[(modulo, nombre)] = getattr(modulo, nombre)
            setattr(modulo, nombre, reemplazo)
        return self

    def __exit__(self, *e):
        for (modulo, nombre), original in self._originales.items():
            setattr(modulo, nombre, original)
        self._originales.clear()
        return False


import os  # noqa: E402

#  La etapa de Autonomia 2, encendida para este archivo: lo que se
#  prueba aca es el kill switch, no el interruptor de etapa.
os.environ["AUTONOMIA_2_ACTIVA"] = "1"

ACTIVO = {"estado": "activo", "estado_anterior": None, "actor": "migracion",
          "motivo": "estado inicial", "creado_en": None}
DETENIDO = {"estado": "detenido", "estado_anterior": "activo",
            "actor": "operaciones", "motivo": "incidente de red en curso",
            "creado_en": None}


class SesionDePrueba:
    """
    Lo minimo para que una herramienta de escritura llegue a ejecutarse.

    Hace falta porque 'reiniciar_ont' declara 'inyectados_obligatorios:
    [sn_onu]' -- sin ese dato el motor la frena ANTES de llegar a nada, con
    otro codigo (DATO_DEL_EQUIPO_NO_CARGADO). Si estas pruebas corrieran con
    sesion=None, todas darian "bloqueada" por el motivo equivocado y el verde
    no probaria nada sobre el interruptor. Es exactamente la trampa que
    CLAUDE.md describe: una prueba que pasa por una coincidencia.
    """
    verificado = True
    nivel = 99
    id_cliente = "5832"
    sn_onu = "HWTCAF721761"
    interfaz_lan = ""
    identificador_canal = "573000000000"
    rol_siguiente = None


def intentar(nombre_herramienta: str, banco: Banco):
    """Ejecuta una herramienta por el camino real y dice que paso."""
    try:
        salida = motor._ejecutar_tool(
            herramienta(nombre_herramienta), SesionDePrueba(),
            {"servicio": "5832"},
            TENANT, CONFIG.variables_tenant, origen="prueba")
        return ("ejecuto", salida)
    except motor.AutonomiaDetenida as e:
        return ("bloqueada", e)
    except Exception as e:                                       # noqa: BLE001
        return (type(e).__name__, e)


# ===========================================================================
seccion("1. detenido: una accion autonoma NO se ejecuta")

with Banco(DETENIDO) as banco:
    que_paso, _ = intentar("reiniciar_ont", banco)
    afirmar(que_paso == "bloqueada",
            f"'reiniciar_ont' queda bloqueada con el interruptor tirado "
            f"(fue: {que_paso})")
    afirmar(banco.llamadas_http == [],
            f"y NINGUNA llamada externa salio (salieron: {banco.llamadas_http})")

# ===========================================================================
seccion("2. detenido: tampoco sale por la ruta de otro servicio")

with Banco(DETENIDO) as banco:
    # Una herramienta de escritura invocable por un servicio del despliegue.
    escritura_de_servicio = next(
        (h for h in CONFIG.herramientas
         if h.invocable_por_servicio and not h.solo_lectura), None)
    if escritura_de_servicio is None:
        afirmar(True, "(el tenant no declara ninguna escritura invocable por "
                      "servicio; nada que comprobar por esta via)")
    else:
        try:
            motor.ejecutar_para_servicio(CONFIG, escritura_de_servicio,
                                         {"servicio": "5832"})
            bloqueo = False
        except motor.AutonomiaDetenida:
            bloqueo = True
        except Exception:                                        # noqa: BLE001
            bloqueo = False
        afirmar(bloqueo,
                f"'{escritura_de_servicio.nombre}' por /interno tambien se "
                f"bloquea")
        afirmar(banco.llamadas_http == [],
                f"y tampoco salio nada (salieron: {banco.llamadas_http})")

# ===========================================================================
seccion("3. detenido: las CONSULTAS siguen funcionando")
# Es la mitad que se olvida. Un interruptor que ademas deja ciego al que
# atiende no se tira nunca, y entonces no existe.

with Banco(DETENIDO) as banco:
    lectura = next(h for h in CONFIG.herramientas
                   if h.tipo == "http" and h.solo_lectura)
    que_paso, _ = intentar(lectura.nombre, banco)
    afirmar(que_paso == "ejecuto",
            f"'{lectura.nombre}' (solo lectura) se ejecuta igual (fue: {que_paso})")
    afirmar(banco.llamadas_http == [lectura.nombre],
            f"y la consulta SI salio (salieron: {banco.llamadas_http})")

# ===========================================================================
seccion("4. activo: el flujo normal no cambia")

with Banco(ACTIVO) as banco:
    que_paso, salida = intentar("reiniciar_ont", banco)
    afirmar(que_paso == "ejecuto",
            f"'reiniciar_ont' se ejecuta con el interruptor levantado "
            f"(fue: {que_paso})")
    afirmar(banco.llamadas_http == ["reiniciar_ont"],
            f"y salio exactamente UNA llamada (salieron: {banco.llamadas_http})")

# ===========================================================================
seccion("5. fail-closed: lo que no se puede afirmar, se bloquea")


class FallaDeBase(Exception):
    pass


with Banco(None) as banco:
    que_paso, _ = intentar("reiniciar_ont", banco)
    afirmar(que_paso == "bloqueada",
            f"sin fila de interruptor se BLOQUEA (fue: {que_paso})")
    afirmar(banco.llamadas_http == [], "y no sale nada")

with Banco(None, revienta=FallaDeBase("la base no responde")) as banco:
    que_paso, _ = intentar("reiniciar_ont", banco)
    afirmar(que_paso == "bloqueada",
            f"si no se puede LEER el interruptor se BLOQUEA (fue: {que_paso})")
    afirmar(banco.llamadas_http == [],
            "y tampoco sale nada -- cortar la base no puede ser la forma de "
            "saltear el interruptor")


class TablaQueNoExiste(Exception):
    sqlstate = "42P01"


with Banco(None, revienta=TablaQueNoExiste("relation does not exist")) as banco:
    que_paso, _ = intentar("reiniciar_ont", banco)
    # Corregido el 17/09/2026 (paso 10.10). Esta afirmacion exigia lo contrario
    # --"si la tabla no existe, se permite"-- y con ella el mecanismo pasaba de
    # controlar a autorizar en el unico caso en que no puede saber nada. Una
    # base restaurada sin la migracion quedaba con la autonomia permitida.
    afirmar(que_paso == "bloqueada",
            f"si la TABLA no existe todavia se BLOQUEA (fue: {que_paso}) -- "
            f"'el control no esta instalado' no puede significar 'adelante'")
    afirmar(banco.llamadas_http == [],
            "y no sale ninguna llamada externa")
    v = interruptor.veredicto(TENANT)
    afirmar(v.estado == interruptor.SIN_INSTALAR,
            f"el estado lo dice con nombre propio, distinto de 'detenido' y de "
            f"'desconocido' (fue: {v.estado})")
    afirmar(v.estado in interruptor.ESTADOS_SIN_CONTROL and not v.permitido,
            "y queda agrupado entre los estados sin control, todos bloqueantes")

# ===========================================================================
seccion("6. mover el interruptor deja trazabilidad")

with Banco(ACTIVO) as banco:
    fila = interruptor.detener(TENANT, actor="mayra",
                              motivo="prueba de la fase 1")
    afirmar(fila["estado"] == "detenido", "queda en 'detenido'")
    afirmar(fila["estado_anterior"] == "activo",
            f"anota el estado ANTERIOR ({fila['estado_anterior']})")
    afirmar(fila["actor"] == "mayra", "anota quien lo movio")
    afirmar(fila["motivo"] == "prueba de la fase 1", "anota por que")

    fila2 = interruptor.reactivar(TENANT, actor="mayra", motivo="ya paso")
    afirmar(fila2["estado"] == "activo" and fila2["estado_anterior"] == "detenido",
            "y la reactivacion anota la transicion inversa")

    acciones = [a["accion"] for a in banco.auditoria]
    afirmar(acciones == ["autonomia_detenida", "autonomia_reactivada"],
            f"las dos quedan en el registro de autorizacion (fueron: {acciones})")
    afirmar(all(a["actor"] == "mayra" for a in banco.auditoria),
            "con el nombre de quien decidio, no 'sistema'")

with Banco(ACTIVO) as banco:
    for falta, quien, porque in (("actor", "", "un motivo"),
                                 ("motivo", "alguien", "")):
        try:
            interruptor.detener(TENANT, actor=quien, motivo=porque)
            rechazo = False
        except ValueError:
            rechazo = True
        afirmar(rechazo, f"no se puede detener sin {falta}")
    afirmar(banco.transiciones == [],
            "y un intento incompleto no escribe ninguna transicion")

# ===========================================================================
seccion("7. un bloqueo queda auditado, aunque no haya conversacion")
# Es el punto entero de usar asistente.audit_log y no asistente.tool_calls: el
# scheduler no tiene conversation_id, asi que la traza de la bandeja no puede
# ser el registro de una accion autonoma.

with Banco(DETENIDO) as banco:
    intentar("reiniciar_ont", banco)
    negadas = [a for a in banco.auditoria if a["resultado"] == "denegado"]
    afirmar(len(negadas) == 1,
            f"el bloqueo deja UNA fila de denegacion (dejo {len(negadas)})")
    if negadas:
        afirmar("reiniciar_ont" in (negadas[0]["recurso"] or ""),
                "que dice QUE se bloqueo")
        afirmar("detenido" in (negadas[0]["motivo_denegacion"] or ""),
                f"y por que ({negadas[0]['motivo_denegacion']})")

# ===========================================================================
seccion("8. el reloj no trabaja para un tenant detenido")

from nucleo import reloj                                          # noqa: E402
from nucleo.config import fuente                                  # noqa: E402
from nucleo.seguimiento import importacion_io, operativo          # noqa: E402


def pasada_del_reloj(fila_interruptor):
    hechos = {"vencidas": 0, "importacion": 0}
    originales = {
        (fuente, "cargar"): fuente.cargar,
        (operativo, "cerrar_vencidas"): operativo.cerrar_vencidas,
        (importacion_io, "barrido"): importacion_io.barrido,
        (reloj, "tenants_conocidos"): reloj.tenants_conocidos,
    }

    def _vencidas(config, tenant):
        hechos["vencidas"] += 1
        return {"revisadas": 0, "cerradas": 0}

    def _barrido(config, tenant, aplicar_cambios=True):
        hechos["importacion"] += 1
        return {"descubiertos": 0}

    fuente.cargar = lambda tenant, raiz=".": CONFIG
    operativo.cerrar_vencidas = _vencidas
    importacion_io.barrido = _barrido
    reloj.tenants_conocidos = lambda: [TENANT]
    try:
        with Banco(fila_interruptor):
            salida = reloj.una_pasada()
    finally:
        for (modulo, nombre), original in originales.items():
            setattr(modulo, nombre, original)
    return hechos, salida


# El plazo tiene que estar declarado para que 'cerrar_vencidas' se llame;
# si el tenant no lo declara, esta comprobacion no prueba nada y hay que
# decirlo en vez de dar un verde vacio.
plazo = CONFIG.escalamiento.cerrar_sin_respuesta_horas
if not plazo:
    afirmar(False, "el tenant no declara 'cerrar_sin_respuesta_horas': esta "
                   "comprobacion no puede distinguir 'detenido' de 'no habia "
                   "nada que hacer'. Revisar el caso a mano.")
else:
    hechos_on, _ = pasada_del_reloj(ACTIVO)
    afirmar(hechos_on["vencidas"] == 1,
            f"con autonomia activa, el reloj SI hace su trabajo "
            f"(vencidas={hechos_on['vencidas']})")

    hechos_off, salida = pasada_del_reloj(DETENIDO)
    afirmar(hechos_off["vencidas"] == 0 and hechos_off["importacion"] == 0,
            f"con el interruptor tirado el reloj no hace NADA de ese tenant "
            f"(vencidas={hechos_off['vencidas']}, "
            f"importacion={hechos_off['importacion']})")
    afirmar(salida and salida[0].get("autonomia", {}).get("estado") == "detenido",
            "y lo deja dicho en el informe del ciclo, no en silencio")

# ===========================================================================
seccion("9. el scheduler no reclama turnos de un tenant detenido")

from nucleo.programador import coordinador, puerta, registro      # noqa: E402


def tick_con(fila_interruptor):
    reclamos: list[str] = []
    originales = {
        (puerta, "sesion"): puerta.sesion,
        (puerta, "vencidos"): puerta.vencidos,
        (puerta, "reclamar"): puerta.reclamar,
        (registro, "conocido"): registro.conocido,
        (coordinador.ejecutor, "ejecutar"): coordinador.ejecutor.ejecutar,
        (persistencia, "estado_autonomia_de_organizacion"):
            persistencia.estado_autonomia_de_organizacion,
    }

    import contextlib

    @contextlib.contextmanager
    def _sesion(rol):
        yield None

    def _reclamar(cur, job_code, org, slot, wid):
        reclamos.append(job_code)
        return {"run_id": "r1", "capability": "c1"}

    puerta.sesion = _sesion
    puerta.vencidos = lambda cur, limite=200: [
        {"job_code": "prueba_job", "organization_id": "org-1", "slot": "s1",
         "motivo": "vencido"}]
    puerta.reclamar = _reclamar
    registro.conocido = lambda job_code: True
    coordinador.ejecutor.ejecutar = lambda run_id, cap: {"registrado": "ok"}
    persistencia.estado_autonomia_de_organizacion = lambda org: fila_interruptor
    try:
        informe = coordinador.un_tick()
    finally:
        for (modulo, nombre), original in originales.items():
            setattr(modulo, nombre, original)
    return reclamos, informe


reclamos_on, _ = tick_con(ACTIVO)
afirmar(reclamos_on == ["prueba_job"],
        f"con autonomia activa el coordinador reclama el turno "
        f"(reclamo: {reclamos_on})")

reclamos_off, informe = tick_con(DETENIDO)
afirmar(reclamos_off == [],
        f"con el interruptor tirado NO reclama ni abre intento "
        f"(reclamo: {reclamos_off})")

reclamos_err, _ = tick_con(None)
afirmar(reclamos_err == [],
        "y sin fila de interruptor tampoco -- fail-closed tambien en el "
        "scheduler")

# ===========================================================================
seccion("10. las tres acciones de red conservan sus precondiciones")
# El interruptor se suma a lo que ya habia; no reemplaza ni relaja nada.
# Si alguna de estas afirmaciones falla, es que la fase 1 tocó algo que no
# tenia que tocar.

ESPERADO = {
    "reiniciar_ont": {
        "previas": {"consultar_senal_ont", "ping_cliente"},
        "limite": 1, "verificacion": True},
    "activar_catv": {
        "previas": {"consultar_plan_tv", "consultar_estado_catv"},
        "limite": 1, "verificacion": False},
    "cambiar_tipo_onu": {
        "previas": {"consultar_estado_catv"},
        "limite": 1, "verificacion": False},
}

for nombre, esperado in ESPERADO.items():
    h = herramienta(nombre)
    previas = {p.herramienta for p in h.exige_previas}
    afirmar(previas == esperado["previas"],
            f"'{nombre}' conserva sus precondiciones {sorted(esperado['previas'])} "
            f"(tiene: {sorted(previas)})")
    afirmar(h.limite_por_conversacion == esperado["limite"],
            f"'{nombre}' conserva su limite por conversacion "
            f"({h.limite_por_conversacion})")
    afirmar(h.solo_lectura is False and h.requiere_confirmacion is True,
            f"'{nombre}' sigue declarada como escritura con confirmacion")
    afirmar(bool(h.verificacion) is esperado["verificacion"],
            f"'{nombre}' conserva su verificacion posterior "
            f"({bool(h.verificacion)})")
    afirmar(h.invocable_por_servicio is False,
            f"'{nombre}' sigue SIN ser invocable por un servicio -- nadie "
            f"puede dispararla por la ruta interna")

# ===========================================================================
print()
if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] El interruptor detiene lo autonomo, deja pasar lo que se consulta, "
      "y queda escrito quien lo movio.")
