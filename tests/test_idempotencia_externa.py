# -*- coding: utf-8 -*-
"""
================================================================================
 IDEMPOTENCIA DE OPERACIONES EXTERNAS  --  que la mutacion salga UNA vez
================================================================================

    py -3.13 tests/test_idempotencia_externa.py

QUE SE PRUEBA
-------------
Que una misma operacion logica no le llegue dos veces al proveedor por un
reintento, un timeout, dos procesos o un reenvio -- y que dos operaciones
DISTINTAS no se confundan en una, que es el error simetrico y el que rompe
algo que hoy funciona.

COMO, SIN BASE DE DATOS
-----------------------
No se sustituyen las funciones de nucleo/persistencia/db.py: se sustituye
'db.sesion()', el cursor. Asi corre el CODIGO REAL de
'reclamar_operacion_externa' -- su cadena de decisiones, la comparacion de
huellas, el calculo del vencimiento-- y lo unico emulado es la ejecucion de
las cinco sentencias SQL que esa funcion manda.

La diferencia importa: si se hubiera escrito un doble que devuelve
'{"decision": "repetida"}', lo que quedaria probado seria el doble.

LO QUE EL DOBLE NO PUEDE PROBAR, Y COMO SE CUBRE
------------------------------------------------
La atomicidad de verdad no es de Python: es de la clave primaria
(organization_id, clave) mas 'on conflict do nothing'. Un diccionario con un
candado la IMITA, no la demuestra. Por eso:

  * la prueba de concurrencia comprueba que el codigo usa bien la primitiva
    (uno ejecuta, el otro ve la fila del primero);
  * y aparte se afirma, sobre el texto del SQL y de la migracion, que la
    primitiva que se usa es esa y no un 'select' previo seguido de un
    'insert' -- que es la forma equivocada de escribir lo mismo, y la que
    tiene la carrera adentro.

LO QUE ESTO NO PROMETE, Y HAY QUE DECIRLO
-----------------------------------------
Si la llamada sale y la respuesta se pierde, nadie sabe si el tercero la
aplico. Lo que se garantiza es que el reintento es UNO, con dueño, contado y
anotado. El caso 8 de abajo prueba eso y no mas que eso.
================================================================================
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                          # noqa: E402
from nucleo.herramientas import http as ejecutor_http            # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402
from nucleo.persistencia import db as persistencia               # noqa: E402
from nucleo.seguridad import idempotencia                        # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


def seccion(titulo: str) -> None:
    print(f"\n--- {titulo} ---")


# ===========================================================================
#  LA TABLA FALSA  --  emula las cinco sentencias, no las decisiones
# ===========================================================================

class Tabla:
    """
    'asistente.operaciones_externas' en memoria.

    El candado emula lo que en Postgres hace el indice unico: dos inserciones
    simultaneas de la misma clave no pueden ganar las dos. Es una IMITACION de
    esa garantia, no la garantia -- ver el encabezado.
    """

    def __init__(self):
        self.filas: dict[tuple, dict] = {}
        self.candado = threading.Lock()

    def org(self, tenant: str) -> str:
        return f"org-{tenant}"


class Cursor:
    """Ejecuta las sentencias de db.py contra la tabla en memoria."""

    def __init__(self, tabla: Tabla, org: str):
        self.tabla = tabla
        self.org = org
        self._fila = None

    # -- helpers ---------------------------------------------------------
    def _clonar(self, fila):
        return dict(fila) if fila else None

    def execute(self, sql: str, params=()):
        s = " ".join(sql.split()).lower()
        self._fila = None

        if s.startswith("insert into asistente.operaciones_externas"):
            org, clave, herr, huella, origen = params
            with self.tabla.candado:
                if (org, clave) in self.tabla.filas:
                    return                       # on conflict do nothing
                ahora = datetime.now(timezone.utc)
                self.tabla.filas[(org, clave)] = {
                    "clave": clave, "herramienta": herr,
                    "argumentos_hash": huella, "estado": "ejecutando",
                    "origen": origen, "intentos": 1, "respuesta": None,
                    "error": None, "creado_en": ahora, "ejecutado_en": None,
                    "actualizado_en": ahora}
                self._fila = self._clonar(self.tabla.filas[(org, clave)])
            return

        if "from asistente.operaciones_externas" in s and "for update" in s:
            org, clave = params
            self._fila = self._clonar(self.tabla.filas.get((org, clave)))
            return

        if "update asistente.operaciones_externas" in s and "intentos = intentos + 1" in s:
            # Rescate por vencimiento, o reintento autorizado (lleva ademas
            # 'error = null'). Los dos vuelven a poner la fila en 'ejecutando'.
            org, clave = params
            fila = self.tabla.filas.get((org, clave))
            if fila is not None:
                fila["estado"] = "ejecutando"
                fila["intentos"] += 1
                fila["actualizado_en"] = datetime.now(timezone.utc)
                if "error = null" in s:
                    fila["error"] = None
                self._fila = self._clonar(fila)
            return

        if "update asistente.operaciones_externas" in s and "set estado = %s" in s:
            estado, respuesta, error, org, clave = params
            fila = self.tabla.filas.get((org, clave))
            # 'and estado = ejecutando' del SQL real: el dueño viejo de una
            # operacion ya rescatada no puede pisar al nuevo.
            if fila is not None and fila["estado"] == "ejecutando":
                fila["estado"] = estado
                # La columna es jsonb: db.py manda el texto serializado y
                # Postgres lo devuelve como dict/list al leerlo. El doble tiene
                # que hacer ese mismo viaje de ida y vuelta -- sin esto, la
                # respuesta guardada volveria como una cadena JSON y quien
                # recibe una repeticion obtendria algo distinto de lo que
                # obtuvo la primera vez. Lo encontro esta misma prueba.
                fila["respuesta"] = (json.loads(respuesta)
                                     if isinstance(respuesta, str) else respuesta)
                fila["error"] = error
                fila["ejecutado_en"] = datetime.now(timezone.utc)
                fila["actualizado_en"] = datetime.now(timezone.utc)
            return

        raise AssertionError(
            "sentencia no prevista por el doble -- si db.py cambio, esta "
            f"prueba tiene que enterarse:\n{sql}")

    def fetchone(self):
        return self._fila


@contextlib.contextmanager
def banco(tabla: Tabla):
    """
    Sustituye db.sesion() por un cursor contra la tabla en memoria, y abre un
    permiso de la frontera.

    EL PERMISO ES PRECONDICION, NO PARTE DE LO QUE SE PRUEBA  --  paso 10.14A
    ------------------------------------------------------------------------
    Desde ese paso, 'idempotencia.ejecutar()' se niega a correr si nadie paso
    antes por nucleo/seguridad/frontera.py: garantiza "una sola vez", no "esta
    permitido", y usarla suelta era un bypass del interruptor. Aca se abre la
    puerta humana --con actor y evidencia-- porque lo que estas pruebas miden
    es la repeticion, no la autorizacion. Que la falta de permiso BLOQUEA se
    prueba aparte, en la seccion 15 de este mismo archivo.
    """
    from nucleo.seguridad import frontera

    original = persistencia.sesion

    @contextlib.contextmanager
    def _sesion(tenant: str):
        yield Cursor(tabla, tabla.org(tenant)), tabla.org(tenant)

    persistencia.sesion = _sesion
    try:
        with frontera.humana(TENANT, "prueba", actor="suite",
                             evidencia="test_idempotencia_externa"):
            yield tabla
    finally:
        persistencia.sesion = original


class Proveedor:
    """Cuenta cuantas veces le llego la mutacion de verdad."""

    def __init__(self, revienta=None):
        self.veces = 0
        self.revienta = revienta

    def __call__(self):
        self.veces += 1
        if self.revienta is not None:
            raise self.revienta
        return {"status": True, "response": f"llamada {self.veces}"}


ARGS = {"onu": "HWTCAF721761"}
OTROS = {"onu": "OTRO12345678"}


# ===========================================================================
seccion("1. la primera llamada con una clave nueva SI ejecuta")

with banco(Tabla()) as tabla:
    prov = Proveedor()
    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(prov.veces == 1, f"la mutacion salio una vez (salio {prov.veces})")
    afirmar(r.ejecutada and r.decision == "ejecutar",
            f"y se informa como ejecutada (fue: {r.decision})")
    fila = list(tabla.filas.values())[0]
    afirmar(fila["estado"] == "exitosa",
            f"la operacion queda 'exitosa' (quedo '{fila['estado']}')")
    afirmar(fila["respuesta"] is not None, "con la respuesta del tercero guardada")

# ===========================================================================
seccion("2. la segunda llamada con la MISMA clave no vuelve a ejecutar")

with banco(Tabla()) as tabla:
    prov = Proveedor()
    idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    r2 = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(prov.veces == 1,
            f"el proveedor recibio UNA sola llamada, no dos (recibio {prov.veces})")
    afirmar(r2.decision == "repetida" and not r2.ejecutada,
            f"la segunda se informa como repeticion (fue: {r2.decision})")

# ===========================================================================
seccion("3. la repeticion DEVUELVE el resultado de la primera")
# Sin esto, quien llama recibiria un vacio y creeria que fallo -- y la
# reaccion tipica a eso es reintentar, o sea exactamente lo que hay que evitar.

with banco(Tabla()):
    prov = Proveedor()
    r1 = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    r2 = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(r2.respuesta == r1.respuesta,
            f"devuelve lo mismo que la primera vez ({r2.respuesta})")
    afirmar(r2.hubo_respuesta, "y quien llama la recibe como una respuesta valida")

# ===========================================================================
seccion("4. misma clave con OTROS argumentos: se rechaza, no se repite")
# Es el caso peligroso: si en vez de rechazar se devolviera el resultado
# guardado, quien pidio reiniciar el equipo B recibiria la confirmacion del
# equipo A y creeria que se hizo.

with banco(Tabla()) as tabla:
    prov = Proveedor()
    idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov,
                          clave="clave-fija")
    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", OTROS, "evento:A", prov,
                              clave="clave-fija")
    afirmar(r.decision == "rechazada", f"se rechaza (fue: {r.decision})")
    afirmar(r.codigo == idempotencia.CLAVE_REUTILIZADA,
            f"con su codigo propio ({r.codigo})")
    afirmar(not r.hubo_respuesta,
            "y NO se le entrega el resultado de la otra operacion")
    afirmar(prov.veces == 1, f"el proveedor sigue con una llamada ({prov.veces})")
    fila = tabla.filas[(tabla.org(TENANT), "clave-fija")]
    afirmar(fila["argumentos_hash"] == idempotencia.hash_de(ARGS),
            "y la fila legitima queda intacta -- el rechazo no la pisa")

# ===========================================================================
seccion("5. dos procesos a la vez con la misma clave: ejecuta uno solo")

with banco(Tabla()):
    prov = Proveedor()
    barrera = threading.Barrier(2)
    resultados: list = []
    candado = threading.Lock()

    def correr():
        #  UN ContextVar NO SE HEREDA EN UN HILO NUEVO  --  y esta bien
        #  ---------------------------------------------------------
        #  threading.Thread arranca con un contexto vacio, asi que el permiso
        #  que abrio 'banco' no llega aca. Eso es fail-closed y es deseable: un
        #  trabajo que se manda a un hilo no arrastra la autorizacion de quien
        #  lo mando. Lo que la prueba mide es la EXCLUSION entre dos procesos,
        #  asi que cada hilo abre el suyo, igual que haria el codigo real.
        from nucleo.seguridad import frontera
        barrera.wait()                     # que arranquen lo mas junto posible
        with frontera.humana(TENANT, "prueba", actor="suite",
                             evidencia="concurrencia"):
            r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS,
                                      "evento:A", prov)
        with candado:
            resultados.append(r)

    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    afirmar(prov.veces == 1,
            f"la mutacion le llego al proveedor UNA vez (llego {prov.veces})")
    ejecutaron = [r for r in resultados if r.ejecutada]
    afirmar(len(ejecutaron) == 1,
            f"un solo proceso se la adjudico (se la adjudicaron {len(ejecutaron)})")
    otro = [r for r in resultados if not r.ejecutada]
    afirmar(len(otro) == 1 and otro[0].decision in ("repetida", "en_curso"),
            f"y el otro se entera de que no es suya "
            f"({otro[0].decision if otro else 'no hubo otro'})")

# ===========================================================================
seccion("6. mientras una esta en curso, otra igual no arranca")

with banco(Tabla()) as tabla:
    prov = Proveedor()
    clave = idempotencia.clave_de("evento:A", "reiniciar_ont", ARGS)
    # Se deja una fila 'ejecutando' reciente, como la dejaria un proceso que
    # todavia esta esperando la respuesta del proveedor.
    tabla.filas[(tabla.org(TENANT), clave)] = {
        "clave": clave, "herramienta": "reiniciar_ont",
        "argumentos_hash": idempotencia.hash_de(ARGS), "estado": "ejecutando",
        "origen": "evento:A", "intentos": 1, "respuesta": None, "error": None,
        "creado_en": datetime.now(timezone.utc), "ejecutado_en": None,
        "actualizado_en": datetime.now(timezone.utc)}

    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(r.decision == "en_curso", f"se informa 'en curso' (fue: {r.decision})")
    afirmar(r.codigo == idempotencia.EN_CURSO, f"con su codigo ({r.codigo})")
    afirmar(prov.veces == 0,
            f"y el proveedor NO recibio nada (recibio {prov.veces})")

# ===========================================================================
seccion("7. un fallo del tercero deja la operacion 'fallida', no 'exitosa'")


class ErrorDelProveedor(Exception):
    pass


with banco(Tabla()) as tabla:
    prov = Proveedor(revienta=ErrorDelProveedor("502 del proveedor"))
    try:
        idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
        subio = False
    except ErrorDelProveedor:
        subio = True
    afirmar(subio,
            "la excepcion sube tal cual -- quien llama ya sabe manejarla y "
            "convertirla aca cambiaria el comportamiento de toda escritura")
    fila = list(tabla.filas.values())[0]
    afirmar(fila["estado"] == "fallida",
            f"la operacion queda 'fallida' (quedo '{fila['estado']}')")
    afirmar("502 del proveedor" in (fila["error"] or ""),
            f"con el error guardado ({fila['error']})")

# ===========================================================================
seccion("8. despues de un fallo, el reintento es una DECISION, no un reflejo")

with banco(Tabla()) as tabla:
    prov = Proveedor(revienta=ErrorDelProveedor("502"))
    with contextlib.suppress(ErrorDelProveedor):
        idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)

    # Sin autorizacion: no se repite.
    prov2 = Proveedor()
    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov2)
    afirmar(r.decision == "fallida" and prov2.veces == 0,
            f"sin autorizar, NO se repite sola (decision={r.decision}, "
            f"llamadas={prov2.veces})")
    afirmar(r.codigo == idempotencia.FALLIDA_PREVIA, f"y lo dice ({r.codigo})")

    # Con autorizacion explicita: se repite UNA vez, y queda contado.
    prov3 = Proveedor()
    r3 = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov3,
                               reintentar_fallida=True)
    afirmar(prov3.veces == 1 and r3.ejecutada,
            f"autorizado, se reintenta una vez (llamadas={prov3.veces})")
    fila = list(tabla.filas.values())[0]
    afirmar(fila["intentos"] == 2,
            f"y el intento queda contado, no perdido (intentos={fila['intentos']})")
    afirmar(fila["estado"] == "exitosa",
            f"con el estado final correcto ('{fila['estado']}')")

# ===========================================================================
seccion("9. una operacion colgada se rescata SOLO despues del plazo")
# El caso del timeout: el proceso murio entre mandar la llamada y anotar el
# resultado. Sin rescate, esa clave queda inutilizable para siempre; con un
# rescate demasiado temprano, se repite una mutacion que quizas seguia viva.


def con_fila_colgada(hace_segundos: int):
    tabla = Tabla()
    clave = idempotencia.clave_de("evento:A", "reiniciar_ont", ARGS)
    viejo = datetime.now(timezone.utc) - timedelta(seconds=hace_segundos)
    tabla.filas[(tabla.org(TENANT), clave)] = {
        "clave": clave, "herramienta": "reiniciar_ont",
        "argumentos_hash": idempotencia.hash_de(ARGS), "estado": "ejecutando",
        "origen": "evento:A", "intentos": 1, "respuesta": None, "error": None,
        "creado_en": viejo, "ejecutado_en": None, "actualizado_en": viejo}
    return tabla


plazo = idempotencia.SEGUNDOS_VENCIDA
with banco(con_fila_colgada(plazo - 60)):
    prov = Proveedor()
    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(r.decision == "en_curso" and prov.veces == 0,
            f"antes del plazo NO se rescata (decision={r.decision}, "
            f"llamadas={prov.veces})")

with banco(con_fila_colgada(plazo + 60)) as tabla:
    prov = Proveedor()
    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(r.ejecutada and prov.veces == 1,
            f"pasado el plazo se rescata y se ejecuta una vez "
            f"(llamadas={prov.veces})")
    fila = list(tabla.filas.values())[0]
    afirmar(fila["intentos"] == 2,
            f"y el rescate queda contado como segundo intento "
            f"({fila['intentos']})")

# ===========================================================================
seccion("10. cada empresa tiene su propio registro")
# Dos tenants pueden usar la misma clave sin pisarse: la fila se busca por
# (organizacion, clave), nunca por clave sola.

with banco(Tabla()) as tabla:
    prov = Proveedor()
    idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    idempotencia.ejecutar("otra_empresa", "reiniciar_ont", ARGS, "evento:A", prov)
    afirmar(prov.veces == 2,
            f"la misma clave en otra empresa SI ejecuta (llamadas={prov.veces})")
    orgs = {org for (org, _clave) in tabla.filas}
    afirmar(orgs == {tabla.org(TENANT), tabla.org("otra_empresa")},
            f"y quedan dos filas, una por organizacion ({sorted(orgs)})")

# ===========================================================================
seccion("11. dos solicitudes distintas NO se confunden en una")
# El error simetrico, y el que romperia algo que hoy anda: un cliente puede
# pedir legitimamente dos reinicios en la misma conversacion.

with banco(Tabla()):
    prov = Proveedor()
    idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:A", prov)
    idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:B", prov)
    afirmar(prov.veces == 2,
            f"dos mensajes distintos producen dos reinicios (llamadas={prov.veces})")

    # Y dos acciones distintas del MISMO mensaje tampoco se colapsan.
    prov2 = Proveedor()
    idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:C", prov2)
    idempotencia.ejecutar(TENANT, "crear_ticket", ARGS, "evento:C", prov2)
    afirmar(prov2.veces == 2,
            f"dos herramientas en el mismo turno son dos operaciones "
            f"(llamadas={prov2.veces})")

# ===========================================================================
seccion("12. sin registro no se ejecuta; sin TABLA se ejecuta y se avisa")


class FallaDeBase(Exception):
    pass


class TablaQueNoExiste(Exception):
    sqlstate = "42P01"


def con_reclamo_que_revienta(e):
    original = persistencia.reclamar_operacion_externa

    def _revienta(*a, **k):
        raise e

    persistencia.reclamar_operacion_externa = _revienta
    return original


@contextlib.contextmanager
def permiso():
    """
    El permiso de la frontera, que esta seccion necesita porque no usa 'banco'.

    Sin el, 'ejecutar()' rechaza por ACCION_EXTERNA_SIN_AUTORIZAR antes de
    llegar al caso que aqui se quiere medir -- que es que pasa cuando la base
    revienta o la tabla no existe.
    """
    from nucleo.seguridad import frontera
    with frontera.humana(TENANT, "prueba", actor="suite", evidencia="seccion12"):
        yield


# Corregido el 17/09/2026 (paso 10.10). La segunda fila exigia lo contrario
# --tabla ausente -> se ejecuta-- y eso hacia UNA llamada externa real sin
# ningun control de repeticion. Medido en PASO10.9 antes de cambiarlo. Ahora
# los dos caminos bloquean; lo unico que cambia es el codigo que informan.
for excepcion, codigo_esperado, texto in (
        (FallaDeBase("la base no responde"), idempotencia.SIN_REGISTRO,
         "si no se puede registrar la operacion, NO se ejecuta"),
        (TablaQueNoExiste("relation does not exist"), idempotencia.CONTROL_AUSENTE,
         "si la TABLA no existe todavia, TAMPOCO se ejecuta")):
    original = con_reclamo_que_revienta(excepcion)
    try:
        prov = Proveedor()
        with permiso():
            r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS,
                                      "evento:A", prov)
        afirmar(prov.veces == 0, texto + f" (llamadas externas: {prov.veces})")
        afirmar(r.ejecutada is False, "  y el Resultado dice ejecutada=False")
        afirmar(r.codigo == codigo_esperado,
                f"  y se informa con su codigo ({r.codigo})")
    finally:
        persistencia.reclamar_operacion_externa = original

# ===========================================================================
seccion("13. la exclusion la da la base, no un chequeo previo en Python")
# Lo unico que esta prueba NO puede demostrar con un doble. Se afirma sobre el
# texto: si alguien reescribe el reclamo como 'select ... if not existe:
# insert', la carrera vuelve y ningun doble lo notaria.

fuente_db = (RAIZ / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
inicio = fuente_db.index("def reclamar_operacion_externa")
fin = fuente_db.index("def finalizar_operacion_externa")
cuerpo = " ".join(fuente_db[inicio:fin].split())

afirmar("on conflict (organization_id, clave) do nothing" in cuerpo,
        "el reclamo se hace con 'insert ... on conflict do nothing'")
afirmar(cuerpo.index("insert into asistente.operaciones_externas")
        < cuerpo.index("for update"),
        "y el insert va ANTES de cualquier select -- no se mira y despues se "
        "crea, que es donde vive la carrera")

migracion = (RAIZ / "supabase" / "202609151715_operaciones_externas.sql"
             ).read_text(encoding="utf-8")
plano = " ".join(migracion.split()).lower()
afirmar("primary key (organization_id, clave)" in plano,
        "y la tabla declara esa clave primaria, que es lo que hace atomica la "
        "insercion")
afirmar("grant select, insert, update on asistente.operaciones_externas" in plano
        and "delete on asistente.operaciones_externas" not in plano,
        "el rol del motor no puede BORRAR una operacion ya registrada")

# ===========================================================================
seccion("14. de punta a punta por el motor: dos turnos iguales, una llamada")


def salieron(origen: str, tabla: Tabla) -> list[str]:
    llamadas: list[str] = []

    def _http(herr, argumentos, tenant=None, variables_tenant=None):
        llamadas.append(herr.nombre)
        return {"status": True}

    herramienta = next(h for h in CONFIG.herramientas
                       if h.nombre == "reiniciar_ont")

    class Sesion:
        verificado = True
        nivel = 99
        id_cliente = "5832"
        sn_onu = "HWTCAF721761"
        interfaz_lan = ""
        identificador_canal = "573000000000"
        rol_siguiente = None

    originales = {
        (ejecutor_http, "ejecutar"): ejecutor_http.ejecutar,
        (persistencia, "estado_autonomia"): persistencia.estado_autonomia,
        (persistencia, "registrar_auditoria"): persistencia.registrar_auditoria,
        #  AUTONOMIA 2 (19/09/2026): una escritura autonoma necesita ademas la
        #  etapa, el prerequisito de B-7 y una autorizacion granular. Este
        #  archivo prueba la IDEMPOTENCIA, no la autorizacion: se declaran las
        #  respuestas de la base, igual que se declara el interruptor.
        (persistencia, "secreto_jwt_en_base"): persistencia.secreto_jwt_en_base,
        (persistencia, "nivel_autonomia"): persistencia.nivel_autonomia,
        (persistencia, "autorizacion_herramienta"): persistencia.autorizacion_herramienta,
        (persistencia, "registrar_ejecucion_autonoma"): persistencia.registrar_ejecucion_autonoma,
    }
    ejecutor_http.ejecutar = _http
    persistencia.estado_autonomia = lambda t: {
        "estado": "activo", "estado_anterior": None, "actor": "migracion",
        "motivo": "", "creado_en": None}
    persistencia.registrar_auditoria = lambda *a, **k: None
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
    try:
        with banco(tabla):
            for _ in range(2):
                try:
                    motor._ejecutar_tool(herramienta, Sesion(),
                                         {"servicio": "5832"}, TENANT,
                                         CONFIG.variables_tenant, origen=origen)
                except motor.OperacionNoEjecutada:
                    pass
    finally:
        for (modulo, nombre), original in originales.items():
            setattr(modulo, nombre, original)
    return llamadas


tabla = Tabla()
mismas = salieron("evento:wamid-123", tabla)
afirmar(mismas == ["reiniciar_ont"],
        f"dos entregas del MISMO evento producen una sola llamada externa "
        f"(salieron {len(mismas)})")

distintas = salieron("evento:wamid-999", tabla)
afirmar(distintas == ["reiniciar_ont"],
        "y un evento distinto vuelve a poder ejecutar")

# ===========================================================================
print()
# ===========================================================================
seccion("15. sin permiso de la frontera NO se ejecuta (paso 10.14A)")

with banco(Tabla()) as tabla:
    from nucleo.seguridad import frontera as _f
    prov = Proveedor()
    #  Se sale del permiso que abrio 'banco' para dejar el contexto limpio, que
    #  es exactamente la situacion de un modulo que llama a ejecutar() por su
    #  cuenta sin haber pasado por el gate.
    testigo = _f._PERMISO.set(None)
    try:
        r = idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:Z", prov)
    finally:
        _f._PERMISO.reset(testigo)
    afirmar(prov.veces == 0,
            f"la mutacion NO salio (salio {prov.veces} vez/veces)")
    afirmar(not r.ejecutada and r.codigo == _f.SIN_AUTORIZAR,
            f"y se informa con su codigo (fue: {r.decision}/{r.codigo})")
    afirmar(not tabla.filas,
            "ni siquiera se reclamo la operacion en el registro")


# ===========================================================================
print()
# ===========================================================================
seccion("16. una decision que este modulo no conoce NO ejecuta (19/09/2026)")

#  EL DEFECTO QUE SE CORRIGE
#  -------------------------
#  El 'if' que interpreta la respuesta del reclamo cubria 'repetida',
#  'en_curso', 'rechazada' y 'fallida', y cualquier OTRO valor caia al final --
#  donde un comentario decia 'decision == "ejecutar"' sin que el codigo lo
#  comprobara. La mutacion salia.
#
#  No era alcanzable: el unico productor (db.py::reclamar_operacion_externa)
#  devuelve exactamente cinco valores. Pero la garantia la daba el productor y
#  no este modulo, y el dia que se agregue una decision nueva y se olvide su
#  rama, el sintoma es una escritura que sale sin que nadie la autorizara.
#
#  Se afirma el EFECTO: cuantas veces se llamo al proveedor.


class ReclamoQueContesta:
    """
    Un registro que contesta lo que se le diga. Sustituye SOLO la respuesta del
    reclamo -- el resto del camino (permiso, clave, huella, finalizado) es el
    real.
    """

    def __init__(self, decision, fila=None):
        self.decision = decision
        self.fila = fila if fila is not None else {"intentos": 1}
        self.finalizados: list[tuple] = []

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        return {"decision": self.decision, "fila": self.fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        self.finalizados.append((clave, estado))


@contextlib.contextmanager
def reclamo_que_contesta(decision, fila=None):
    reg = ReclamoQueContesta(decision, fila)
    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa)
    persistencia.reclamar_operacion_externa = reg.reclamar
    persistencia.finalizar_operacion_externa = reg.finalizar
    try:
        yield reg
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa) = originales


def con_permiso(fn):
    """La puerta humana abierta: el permiso es precondicion, no lo que se mide."""
    from nucleo.seguridad import frontera
    with frontera.humana(TENANT, "prueba", actor="suite",
                         evidencia="seccion16"):
        return fn()


# --- 1. decision valida permitida -> ejecuta cuando corresponde -------------
with reclamo_que_contesta("ejecutar") as reg:
    prov = Proveedor()
    r = con_permiso(lambda: idempotencia.ejecutar(
        TENANT, "reiniciar_ont", ARGS, "evento:s16-a", prov))
    afirmar(prov.veces == 1 and r.ejecutada,
            f"1. 'ejecutar' SI ejecuta, una vez (veces={prov.veces}, "
            f"ejecutada={r.ejecutada})")
    afirmar(reg.finalizados == [(r.clave, "exitosa")],
            f"   y se cierra como exitosa ({reg.finalizados})")

# --- 2. decisiones validas que rechazan -> no ejecutan ----------------------
for decision, codigo_esperado in (
        ("repetida", None),
        ("en_curso", idempotencia.EN_CURSO),
        ("rechazada", idempotencia.CLAVE_REUTILIZADA),
        ("fallida", idempotencia.FALLIDA_PREVIA)):
    with reclamo_que_contesta(decision) as reg:
        prov = Proveedor()
        r = con_permiso(lambda: idempotencia.ejecutar(
            TENANT, "reiniciar_ont", ARGS, f"evento:s16-{decision}", prov))
        afirmar(prov.veces == 0 and not r.ejecutada,
                f"2. '{decision}' NO ejecuta (veces={prov.veces})")
        afirmar(r.decision == decision and r.codigo == codigo_esperado,
                f"   y conserva su decision y su codigo "
                f"({r.decision}/{r.codigo})")

# --- 3. decision desconocida -> no ejecuta (EL DEFECTO) ---------------------
for desconocida in ("devolver", "esperar", "rechazar", "", "EJECUTAR",
                    "ejecutar ", None, 0, True):
    with reclamo_que_contesta(desconocida) as reg:
        prov = Proveedor()
        r = con_permiso(lambda: idempotencia.ejecutar(
            TENANT, "reiniciar_ont", ARGS, "evento:s16-desconocida", prov))
        afirmar(prov.veces == 0,
                f"3. {desconocida!r} NO ejecuta (veces={prov.veces})")
        afirmar(not r.ejecutada and r.codigo == idempotencia.DECISION_DESCONOCIDA,
                f"   y se informa con su codigo ({r.decision}/{r.codigo})")
        afirmar(reg.finalizados == [],
                f"   y NO se inventa una transicion en el registro "
                f"({reg.finalizados})")

#  El codigo tiene que llegar al modelo como BLOQUEO, no como error de un
#  tercero: si no, el modelo dice "hubo un problema con el proveedor".
afirmar(idempotencia.DECISION_DESCONOCIDA in motor.CODIGOS_DE_BLOQUEO,
        "3. el codigo esta declarado como bloqueo en motor.CODIGOS_DE_BLOQUEO")

#  Y la prueba de desarme: que el instrumento dispare. Con la MISMA tuberia,
#  'ejecutar' si pasa -- asi el cero de arriba es la decision y no otra cosa.
with reclamo_que_contesta("ejecutar") as reg:
    prov = Proveedor()
    con_permiso(lambda: idempotencia.ejecutar(
        TENANT, "reiniciar_ont", ARGS, "evento:s16-desarme", prov))
    afirmar(prov.veces == 1,
            "3. y con la MISMA tuberia 'ejecutar' si sale: el cero de arriba "
            "era la decision desconocida")

# --- 4/5/6. lo que NO debia cambiar sigue igual, contra el SQL real ---------
#  Estas tres no usan el reclamo sustituido: corren contra la emulacion de
#  'asistente.operaciones_externas' que ya usa el resto del archivo, o sea
#  contra las sentencias de db.py.
with banco(Tabla()) as tabla:
    prov = Proveedor()
    for _ in range(2):
        idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS, "evento:s16-4", prov)
    afirmar(prov.veces == 1,
            f"4. misma clave -> no duplica (salio {prov.veces} vez/veces)")

with banco(Tabla()) as tabla:
    prov = Proveedor()
    #  'clave' EXPLICITA. Sin ella, clave_de() mete el hash de los argumentos
    #  en la propia clave, asi que dos argumentos distintos dan dos claves
    #  distintas y el caso no existiria. El choque solo es posible cuando
    #  quien llama fija la clave -- que es justo el escenario que esta prueba
    #  cubre, igual que la seccion 4 de este archivo.
    idempotencia.ejecutar(TENANT, "reiniciar_ont", {"onu": "A"},
                          "evento:s16-5", prov, clave="s16-clave-fija")
    r = idempotencia.ejecutar(TENANT, "reiniciar_ont", {"onu": "B"},
                              "evento:s16-5", prov, clave="s16-clave-fija")
    afirmar(prov.veces == 1 and r.codigo == idempotencia.CLAVE_REUTILIZADA,
            f"5. misma clave con otros argumentos -> RECHAZA "
            f"(veces={prov.veces}, codigo={r.codigo})")

with banco(Tabla()) as tabla:
    prov = Proveedor()

    def una():
        #  threading.Thread arranca con un contexto VACIO: el permiso que abrio
        #  'banco' es un ContextVar y no cruza al hilo. Se abre aca dentro,
        #  igual que en la seccion 4 de este archivo -- sin esto los 8 hilos
        #  darian 0 llamadas y el verde no probaria nada sobre la concurrencia.
        from nucleo.seguridad import frontera as _fr
        with _fr.humana(TENANT, "prueba", actor="suite", evidencia="seccion16"):
            idempotencia.ejecutar(TENANT, "reiniciar_ont", ARGS,
                                  "evento:s16-6", prov)

    hilos = [threading.Thread(target=una) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    afirmar(prov.veces == 1,
            f"6. 8 hilos con la misma clave -> UN solo efecto "
            f"(salio {prov.veces} vez/veces)")

if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] Una mutacion externa sale una vez, y dos pedidos distintos siguen "
      "siendo dos.")

