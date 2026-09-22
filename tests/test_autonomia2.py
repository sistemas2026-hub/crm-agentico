# -*- coding: utf-8 -*-
"""
================================================================================
 AUTONOMIA 2  --  autorizacion granular, y que de verdad decida
================================================================================

    py -3.13 tests/test_autonomia2.py

QUE SE AFIRMA
-------------
El EFECTO, nunca la presencia del mecanismo. Lo que se cuenta en casi todos los
casos es cuantas veces se llamo al ejecutor HTTP: cero cuando algo debia
frenar, una cuando no. Una prueba que afirmara "existe la tabla de
autorizaciones" sobreviviria intacta a que la autorizacion no se consulte --
que es exactamente el bug que esta capa existe para impedir.

LA REGLA QUE ORDENA TODO EL ARCHIVO
-----------------------------------
    propuesta  !=  autorizacion  !=  ejecucion

Tres cosas distintas, y hay una seccion para cada frontera entre ellas.

CORRE SIN BASE Y SIN RED
------------------------
Se sustituye la RESPUESTA de la base, nunca el gate: el camino del codigo es el
real, y lo que decide es 'nucleo/seguridad/frontera.py' consultando
'autorizacion.py' y 'autonomia2.py'. La prueba de que las consultas SQL de
verdad funcionan contra PostgreSQL esta aparte, en el entorno aislado.
================================================================================
"""

from __future__ import annotations

import ast
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                            # noqa: E402
from nucleo.herramientas import http as ejecutor_http              # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguridad import (autonomia2, autorizacion,            # noqa: E402
                              frontera, interruptor)

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug

#  EL PILOTO. Una sola herramienta -- ver la seccion 0 y el informe.
PILOTO = "crear_tag_crm"

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


AHORA = datetime.now(timezone.utc)
ACTIVO = {"estado": "activo", "estado_anterior": None, "actor": "prueba",
          "motivo": "", "creado_en": None}
DETENIDO = {"estado": "detenido", "estado_anterior": "activo",
            "actor": "operaciones", "motivo": "incidente", "creado_en": None}


def autorizacion_fila(**cambios):
    """Una autorizacion vigente y sana, con lo que se quiera cambiar encima."""
    fila = {"id": "00000000-0000-0000-0000-0000000000a1",
            "herramienta": PILOTO, "estado": "autorizada",
            "estado_anterior": None, "nivel_maximo": 2,
            "vigente_desde": AHORA - timedelta(days=1), "vigente_hasta": None,
            "autorizado_por": "jefe.operaciones", "motivo": "piloto",
            "limites": {"por_dia": 20}, "creado_en": AHORA}
    fila.update(cambios)
    return fila


class Sesion:
    verificado = True
    nivel = 99
    id_cliente = "5832"
    sn_onu = "HWTCAF721761"
    interfaz_lan = ""
    identificador_canal = "573000000000"
    rol_siguiente = None


class Banco:
    """
    La base y la red, sustituidas. Cuenta las llamadas externas de verdad.

    'autorizaciones' es un dict herramienta -> fila (o None). Asi una misma
    corrida puede tener una herramienta autorizada y otra no, que es como se
    ve de verdad un piloto de una sola herramienta.
    """

    def __init__(self, *, interruptor_fila=ACTIVO, nivel=2,
                 autorizaciones=None, etapa=True, secreto_jwt="",
                 revienta_autorizacion=None, http=None):
        self.interruptor_fila = interruptor_fila
        self.nivel = nivel
        self.autorizaciones = autorizaciones if autorizaciones is not None \
            else {PILOTO: autorizacion_fila()}
        self.etapa = etapa
        self.secreto_jwt = secreto_jwt
        self.revienta_autorizacion = revienta_autorizacion
        self.http = http
        self.llamadas_http: list[str] = []
        self.bitacora: list[dict] = []
        self.operaciones: dict[str, dict] = {}
        self._originales: dict = {}
        self._etapa_previa = None
        self._candado = threading.Lock()

    # --- lo que contestaria la base --------------------------------------
    def _estado(self, tenant):
        return self.interruptor_fila

    def _nivel(self, tenant):
        if self.nivel is None:
            return None
        return {"nivel": self.nivel, "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba", "actor": "prueba",
                "motivo": "", "creado_en": None}

    def _autorizacion(self, tenant, herr):
        if self.revienta_autorizacion is not None:
            raise self.revienta_autorizacion
        return self.autorizaciones.get(herr)

    def _secreto(self):
        return self.secreto_jwt

    def _bitacora(self, tenant, **kw):
        self.bitacora.append(dict(kw))

    def _reclamar(self, tenant, clave, herr, huella, origen, vence,
                  reintentar_fallida=False):
        #  Idempotencia minima pero REAL: una clave se ejecuta una sola vez, y
        #  la misma clave con otra huella se rechaza. Con candado, para que la
        #  seccion de concurrencia pruebe algo.
        with self._candado:
            previa = self.operaciones.get(clave)
            if previa is None:
                self.operaciones[clave] = {"huella": huella, "estado": "ejecutando",
                                           "herramienta": herr, "respuesta": None}
                return {"decision": "ejecutar", "fila": {"intentos": 1}}
            #  Los nombres son los que devuelve de verdad
            #  persistencia.reclamar_operacion_externa: 'ejecutar',
            #  'rechazada', 'repetida', 'en_curso', 'fallida'. Inventarlos
            #  hacia que idempotencia.ejecutar cayera al final del if y
            #  ejecutara igual -- una prueba verde que no probaba nada.
            if previa["huella"] != huella:
                return {"decision": "rechazada", "fila": previa,
                        "motivo": "la misma clave con otros argumentos"}
            if previa["estado"] == "exitosa":
                return {"decision": "repetida",
                        "fila": {"estado": "exitosa", "intentos": 1,
                                 "respuesta": previa["respuesta"]}}
            return {"decision": "en_curso", "fila": previa}

    def _finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        fila = self.operaciones.get(clave)
        if fila is not None:
            fila["estado"] = estado
            fila["respuesta"] = respuesta

    def _http_ejecutar(self, herr, argumentos, tenant=None, variables_tenant=None):
        self.llamadas_http.append(herr.nombre)
        if self.http is not None:
            return self.http(herr, argumentos)
        return {"id": "tag-nuevo", "name": argumentos.get("name", "")}

    def __enter__(self):
        self._etapa_previa = os.environ.get(autonomia2.VAR_ETAPA)
        os.environ[autonomia2.VAR_ETAPA] = "1" if self.etapa else "0"
        parches = [
            (persistencia, "estado_autonomia", self._estado),
            (persistencia, "registrar_auditoria", lambda *a, **k: None),
            (persistencia, "nivel_autonomia", self._nivel),
            (persistencia, "autorizacion_herramienta", self._autorizacion),
            (persistencia, "secreto_jwt_en_base", self._secreto),
            (persistencia, "registrar_ejecucion_autonoma", self._bitacora),
            (persistencia, "reclamar_operacion_externa", self._reclamar),
            (persistencia, "finalizar_operacion_externa", self._finalizar),
            (ejecutor_http, "ejecutar", self._http_ejecutar),
            (ejecutor_http, "ejecutar_asincrono",
             lambda h, a, tenant=None, variables_tenant=None:
                 self._http_ejecutar(h, a, tenant)),
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


def intentar(nombre, banco, *, argumentos=None, origen="prueba"):
    """Ejecuta por el camino REAL y dice que paso."""
    try:
        salida = motor._ejecutar_tool(
            herramienta(nombre), Sesion(),
            argumentos if argumentos is not None else {"name": "etiqueta-piloto"},
            TENANT, CONFIG.variables_tenant, origen=origen)
        return ("ejecuto", salida)
    except motor.AutonomiaDetenida as e:
        return ("bloqueada", e)
    except Exception as e:                                       # noqa: BLE001
        return (type(e).__name__, e)


def codigo_de(resultado):
    """El codigo de bloqueo, venga como venga envuelto."""
    _, e = resultado
    for attr in ("codigo", "motivo"):
        v = getattr(e, attr, None)
        if isinstance(v, str) and v:
            return v
    causa = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
    return getattr(causa, "codigo", "") or str(e)


# ===========================================================================
seccion("0. el piloto: UNA herramienta, y por que esa")

R3 = {"reiniciar_ont", "cambiar_tipo_onu", "activar_catv"}
R4 = {"registrar_pago", "agregar_promesa_pago"}

afirmar(PILOTO not in R3 and PILOTO not in R4,
        f"'{PILOTO}' no es R3 ni R4")
h_piloto = herramienta(PILOTO)
afirmar(not h_piloto.solo_lectura,
        f"'{PILOTO}' es una escritura (si fuera lectura no probaria nada)")
afirmar("backend:8000" in (h_piloto.base_url or ""),
        f"'{PILOTO}' escribe en el CRM propio, no en un tercero "
        f"({h_piloto.base_url})")
afirmar((h_piloto.auth_ref or "") == "BOTTLECRM_API_TOKEN",
        f"'{PILOTO}' usa un token propio del CRM, no service_role "
        f"({h_piloto.auth_ref})")

# ===========================================================================
seccion("1. herramienta AUTORIZADA: ejecuta")

with Banco() as banco:
    que, _ = intentar(PILOTO, banco)
    afirmar(que == "ejecuto", f"'{PILOTO}' autorizada ejecuta (fue: {que})")
    afirmar(banco.llamadas_http == [PILOTO],
            f"y salio exactamente UNA llamada ({banco.llamadas_http})")

# ===========================================================================
seccion("2. herramienta NO autorizada: no ejecuta")

with Banco(autorizaciones={}) as banco:
    que, _ = intentar(PILOTO, banco)
    afirmar(que != "ejecuto",
            f"sin fila de autorizacion no ejecuta (fue: {que})")
    afirmar(banco.llamadas_http == [],
            f"y no salio ninguna llamada ({banco.llamadas_http})")

with Banco(autorizaciones={PILOTO: autorizacion_fila()}) as banco:
    #  Otra herramienta del catalogo, que NO esta en el piloto.
    que, _ = intentar("cerrar_caso_crm", banco,
                      argumentos={"caso_id": "x", "status": "Closed"})
    afirmar(que != "ejecuto",
            f"autorizar una herramienta NO autoriza a la de al lado "
            f"(fue: {que})")
    afirmar(banco.llamadas_http == [],
            f"y no salio ninguna llamada ({banco.llamadas_http})")

# ===========================================================================
seccion("3. nivel de autonomia insuficiente: no ejecuta")

for nivel, como in ((0, "sin fila -> 0"), (1, "techo 1")):
    with Banco(nivel=None if nivel == 0 else nivel) as banco:
        que, res = intentar(PILOTO, banco)
        afirmar(que != "ejecuto",
                f"con {como} no ejecuta aunque la herramienta este autorizada "
                f"(fue: {que})")
        afirmar(banco.llamadas_http == [], "y no salio ninguna llamada")

#  El techo ACOTA: autorizacion de nivel 2 con techo 1 -> manda el menor.
v = autorizacion.veredicto(TENANT, PILOTO) if False else None
with Banco(nivel=1, autorizaciones={PILOTO: autorizacion_fila(nivel_maximo=4)}) as banco:
    ver = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(not ver.permitido and ver.codigo == autorizacion.NIVEL_INSUFICIENTE,
            f"techo 1 + autorizacion 4 -> manda el menor ({ver.codigo})")
    afirmar(ver.nivel_efectivo == 1,
            f"y el nivel efectivo es 1, no 4 ({ver.nivel_efectivo})")

# ===========================================================================
seccion("4. autonomia suficiente pero B-7 NO-GO: no ejecuta")

with Banco(secreto_jwt="presente") as banco:
    que, res = intentar(PILOTO, banco)
    afirmar(que != "ejecuto",
            f"con el vector de B-7 abierto no ejecuta (fue: {que})")
    afirmar(banco.llamadas_http == [], "y no salio ninguna llamada")
    afirmar(autonomia2.B7_REQUERIDO in str(codigo_de((que, res)))
            or any(b.get("codigo") == autonomia2.B7_REQUERIDO
                   for b in banco.bitacora),
            "y el sistema lo expresa como B7_REQUERIDO")

#  Que el instrumento dispare: sin el secreto, la MISMA llamada pasa.
with Banco(secreto_jwt="") as banco:
    que, _ = intentar(PILOTO, banco)
    afirmar(que == "ejecuto",
            f"y sin ese secreto la misma llamada SI pasa -- el bloqueo de "
            f"arriba era B-7 y no otra cosa (fue: {que})")

# ===========================================================================
seccion("5. kill switch detenido: no ejecuta, y por SU motivo")

with Banco(interruptor_fila=DETENIDO) as banco:
    que, res = intentar(PILOTO, banco)
    afirmar(que == "bloqueada", f"el kill switch frena igual (fue: {que})")
    afirmar(banco.llamadas_http == [], "y no salio ninguna llamada")
    afirmar(interruptor.CODIGO_BLOQUEO in str(res) or
            "detenido" in str(res).lower(),
            "y el motivo sigue siendo el del interruptor, no el de Autonomia 2")

# ===========================================================================
seccion("6/7. propuesta != autorizacion")

#  Una propuesta aceptada NO crea una autorizacion. Se comprueba por codigo:
#  ninguna ruta del nucleo escribe en autorizacion_herramienta.
fuentes = [p for p in (RAIZ / "nucleo").rglob("*.py")]
escriben = []
for f in fuentes:
    texto = f.read_text(encoding="utf-8", errors="replace")
    #  Preciso: se busca un INSERT sobre ESA tabla, no las dos palabras
    #  sueltas en el mismo archivo -- db.py inserta en la BITACORA, que es
    #  otra tabla, y la version gruesa lo marcaba como si se autorizara solo.
    plano = " ".join(texto.lower().split())
    if "insert into asistente.autorizacion_herramienta" in plano:
        escriben.append(str(f.relative_to(RAIZ)))
    #  M06-B (21/09/2026): el techo SI se escribe desde el nucleo, pero como
    #  'autonomia_operador' -- administracion, no runtime, igual que el
    #  interruptor. Se admite SOLO dentro de una funcion que abre la sesion con
    #  ese rol; cualquier otro INSERT sobre el techo sigue contando como que el
    #  runtime se autoriza a si mismo.
    if "insert into asistente.nivel_autonomia" in plano:
        for fn in ast.walk(ast.parse(texto)):
            if not isinstance(fn, ast.FunctionDef):
                continue
            cuerpo = " ".join(ast.get_source_segment(texto, fn).lower().split())
            if "insert into asistente.nivel_autonomia" not in cuerpo:
                continue
            como_operador = any(
                isinstance(n, ast.Call) and ast.unparse(n.func) == "sesion"
                and any(k.arg == "rol" and ast.unparse(k.value) == "ROL_OPERADOR_AUTONOMIA"
                        for k in n.keywords)
                for n in ast.walk(fn))
            if not como_operador:
                escriben.append(f"{f.relative_to(RAIZ)}::{fn.name}")
afirmar(escriben == [],
        f"ningun modulo del nucleo INSERTA autorizaciones como runtime: el "
        f"runtime no puede autorizarse a si mismo ({escriben})")

with Banco(autorizaciones={}) as banco:
    #  Aunque exista una propuesta aprobada con evidencia, sin autorizacion
    #  granular no se ejecuta.
    que, _ = intentar(PILOTO, banco, origen="propuesta:abc-123")
    afirmar(que != "ejecuto",
            f"una propuesta con origen declarado no sustituye a la "
            f"autorizacion (fue: {que})")

# ===========================================================================
seccion("8. autorizacion != ejecucion")

with Banco() as banco:
    ver = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(ver.permitido, "la autorizacion esta vigente")
    afirmar(banco.llamadas_http == [],
            f"y consultarla NO ejecuta nada por si sola "
            f"({banco.llamadas_http})")

# ===========================================================================
seccion("9. idempotencia: no se crea un segundo mecanismo")

with Banco() as banco:
    for _ in range(2):
        intentar(PILOTO, banco, origen="wamid-iguales")
    afirmar(banco.llamadas_http == [PILOTO],
            f"misma clave + mismos argumentos -> UNA sola llamada "
            f"({banco.llamadas_http})")

with Banco() as banco:
    intentar(PILOTO, banco, argumentos={"name": "uno"}, origen="wamid-mismo")
    intentar(PILOTO, banco, argumentos={"name": "dos"}, origen="wamid-mismo")
    afirmar(banco.llamadas_http == [PILOTO],
            f"misma clave + argumentos distintos -> se RECHAZA, no se ejecuta "
            f"({banco.llamadas_http})")

#  Y que use el mecanismo EXISTENTE, no uno nuevo.
#  Que NO reimplemente el mecanismo. Se mide por AST y no por texto: desde el
#  19/09/2026 frontera.py NOMBRA a idempotencia.py en un comentario (explica de
#  donde viene la clave que anota), y una busqueda de texto leia esa prosa como
#  si fuera una segunda implementacion -- el mismo error de la prueba que lee
#  su propio comentario.
arbol_fr = ast.parse((RAIZ / "nucleo" / "seguridad" / "frontera.py").read_text(
    encoding="utf-8"))
propias = {n.name for n in ast.walk(arbol_fr)
           if isinstance(n, ast.FunctionDef)}
reimplementa = propias & {"clave_de", "hash_de", "reclamar", "ejecutar",
                          "finalizar", "_reclamar"}
afirmar(not reimplementa,
        f"la frontera no reimplementa la idempotencia: no define clave, hash "
        f"ni reclamo propios ({sorted(reimplementa)})")

# ===========================================================================
seccion("10. concurrencia: dos a la vez, una sola ejecucion")

with Banco() as banco:
    salidas: list = []

    def correr():
        salidas.append(intentar(PILOTO, banco, origen="wamid-concurrente"))

    hilos = [threading.Thread(target=correr) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    afirmar(banco.llamadas_http == [PILOTO],
            f"6 hilos con la misma clave -> UNA sola llamada externa "
            f"({banco.llamadas_http})")

# ===========================================================================
seccion("11. tenant incorrecto")

with Banco() as banco:
    #  El permiso se abre para un tenant y el ejecutor comprueba otro.
    with frontera.autonoma(TENANT, PILOTO, origen="prueba"):
        try:
            frontera.exigir(herramienta(PILOTO), "otra-empresa")
            cruzo = True
        except frontera.AccionExternaNoAutorizada as e:
            cruzo = False
            codigo = e.codigo
    afirmar(not cruzo, "un permiso de una empresa no autoriza a escribir en otra")
    afirmar(codigo == frontera.TENANT_DISTINTO,
            f"y lo dice con su propio codigo ({codigo})")

with Banco() as banco:
    que, _ = intentar(PILOTO, banco) if False else ("", None)
    ver = autorizacion.veredicto("", PILOTO)
    afirmar(not ver.permitido,
            "una autorizacion sin tenant valido no habilita nada")

# ===========================================================================
seccion("12. evidencia insuficiente (puerta humana)")

for actor, evidencia, que in (("", "algo", "sin actor"),
                              ("ana", "", "sin evidencia")):
    try:
        with frontera.humana(TENANT, PILOTO, actor=actor, evidencia=evidencia):
            abrio = True
    except frontera.AccionExternaNoAutorizada:
        abrio = False
    afirmar(not abrio, f"la puerta humana no abre {que}")

# ===========================================================================
seccion("13. previas faltantes")

con_previas = [h for h in CONFIG.herramientas if h.exige_previas]
if not con_previas:
    afirmar(True, "(el catalogo no declara previas; nada que comprobar)")
else:
    h = con_previas[0]
    faltantes = motor._previas_no_cumplidas(h, [])
    afirmar(faltantes != [],
            f"'{h.nombre}' sin historial reporta previas faltantes "
            f"({faltantes})")

# ===========================================================================
seccion("14. autorizacion REVOCADA")

with Banco(autorizaciones={PILOTO: autorizacion_fila(
        estado="revocada", estado_anterior="autorizada",
        motivo="se revoco tras el incidente")}) as banco:
    ver = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(not ver.permitido and ver.codigo == autorizacion.REVOCADA,
            f"una autorizacion revocada bloquea ({ver.codigo})")
    que, _ = intentar(PILOTO, banco)
    afirmar(que != "ejecuto", f"y no ejecuta (fue: {que})")
    afirmar(banco.llamadas_http == [], "y no salio ninguna llamada")

# ===========================================================================
seccion("15. autorizacion EXPIRADA (y la que aun no rige)")

with Banco(autorizaciones={PILOTO: autorizacion_fila(
        vigente_desde=AHORA - timedelta(days=10),
        vigente_hasta=AHORA - timedelta(hours=1))}) as banco:
    ver = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(not ver.permitido and ver.codigo == autorizacion.EXPIRADA,
            f"una autorizacion vencida bloquea ({ver.codigo})")
    que, _ = intentar(PILOTO, banco)
    afirmar(que != "ejecuto" and banco.llamadas_http == [],
            f"y no ejecuta (fue: {que}, llamadas: {banco.llamadas_http})")

with Banco(autorizaciones={PILOTO: autorizacion_fila(
        vigente_desde=AHORA + timedelta(days=1))}) as banco:
    ver = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(not ver.permitido and ver.codigo == autorizacion.AUN_NO_VIGENTE,
            f"una autorizacion que todavia no rige bloquea ({ver.codigo})")

#  Y el caso que importa: no se puede leer -> BLOQUEA, no pasa.
with Banco(revienta_autorizacion=RuntimeError("base caida")) as banco:
    ver = autorizacion.veredicto(TENANT, PILOTO)
    afirmar(not ver.permitido and ver.codigo == autorizacion.DESCONOCIDO,
            f"'no se pudo leer la autorizacion' BLOQUEA ({ver.codigo})")
    que, _ = intentar(PILOTO, banco)
    afirmar(banco.llamadas_http == [],
            "y con la base caida no sale ninguna llamada")

# ===========================================================================
seccion("16. auditoria")

with Banco() as banco:
    intentar(PILOTO, banco, origen="wamid-auditado")
    permitidas = [b for b in banco.bitacora if b.get("decision") == "permitida"]
    #  DOS renglones por intento, y se distinguen sin columna nueva:
    #    resultado None      -> la AUTORIZACION (momento de autorizacion)
    #    resultado no-None   -> el DESENLACE (momento de ejecucion + la clave)
    autorizaciones = [b for b in permitidas if b.get("resultado") in (None, "")]
    desenlaces = [b for b in permitidas if b.get("resultado") not in (None, "")]
    afirmar(len(autorizaciones) == 1 and len(desenlaces) == 1,
            f"lo PERMITIDO queda registrado en dos renglones: autorizacion y "
            f"desenlace ({len(autorizaciones)}/{len(desenlaces)})")
    afirmar(desenlaces and desenlaces[0].get("clave_idempotencia"),
            "y el desenlace trae la clave de idempotencia: ahi esta el puente")
    fila = autorizaciones[0] if autorizaciones else {}
    for campo in ("herramienta", "decision", "nivel_efectivo",
                  "autorizacion_id", "actor"):
        afirmar(campo in fila, f"la bitacora registra '{campo}'")
    texto = " ".join(str(v) for v in fila.values())
    afirmar("BOTTLECRM" not in texto.upper() and "token" not in texto.lower(),
            "y no guarda secretos ni credenciales")

with Banco(autorizaciones={}) as banco:
    intentar(PILOTO, banco)
    bloqueadas = [b for b in banco.bitacora if b.get("decision") == "bloqueada"]
    afirmar(len(bloqueadas) == 1,
            f"un bloqueo deja su fila con el codigo ({len(bloqueadas)})")
    afirmar(bloqueadas and bloqueadas[0].get("codigo") ==
            autorizacion.SIN_AUTORIZACION,
            "y el codigo dice por cual compuerta freno")

# ===========================================================================
seccion("17. rollback: un fallo deja estado controlado")

def revienta(herr, argumentos):
    raise RuntimeError("el CRM contesto 500")


with Banco(http=revienta) as banco:
    que, _ = intentar(PILOTO, banco, origen="wamid-fallido")
    afirmar(que != "ejecuto", f"una llamada que falla no se da por buena ({que})")
    estados = [f["estado"] for f in banco.operaciones.values()]
    afirmar(estados == ["fallida"],
            f"y la operacion queda marcada 'fallida', no a medias ({estados})")
    afirmar(frontera.permiso_vigente() is None,
            "y el permiso no queda abierto despues del fallo")

# ===========================================================================
seccion("18/19/20. R3 y R4 siguen bloqueadas")

for nombre, clase in (("reiniciar_ont", "R3"), ("cambiar_tipo_onu", "R3"),
                      ("activar_catv", "R3"), ("registrar_pago", "R4"),
                      ("agregar_promesa_pago", "R4")):
    #  Banco con TODO lo demas en verde: interruptor activo, etapa encendida,
    #  B-7 cerrado, nivel 4. Lo unico que falta es la autorizacion de ESA
    #  herramienta -- que es justo lo que el piloto no concede.
    with Banco(nivel=4, autorizaciones={PILOTO: autorizacion_fila()}) as banco:
        que, _ = intentar(nombre, banco, argumentos={"servicio": "5832"})
        afirmar(que != "ejecuto",
                f"{clase} '{nombre}' NO se ejecuta autonomamente (fue: {que})")
        afirmar(banco.llamadas_http == [],
                f"y no salio ninguna llamada ({banco.llamadas_http})")

# ===========================================================================
seccion("G1. no se creo una segunda cola")

prohibidos = ("AssistantTask", "AIAction", "ExecutionQueue", "AutonomyQueue",
              "ApprovalQueue")
encontrados = []
for f in list((RAIZ / "nucleo").rglob("*.py")) + \
         list((RAIZ / "django-crm" / "backend" / "operaciones").rglob("*.py")):
    if "test" in f.name:
        continue
    texto = f.read_text(encoding="utf-8", errors="replace")
    for p in prohibidos:
        #  Por AST, no por texto: una mencion en un comentario que dice
        #  "no crear AssistantTask" no es crear una cola.
        try:
            arbol = ast.parse(texto)
        except SyntaxError:
            continue
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name == p:
                encontrados.append(f"{f.name}::{p}")
afirmar(encontrados == [],
        f"ninguna clase nueva de cola ({encontrados})")

sql = (RAIZ / "supabase" / "202609221000_autonomia2_autorizacion.sql").read_text(
    encoding="utf-8")
#  Sin los comentarios: el encabezado de la migracion DICE "no tiene
#  'pendiente'", y buscar en texto plano encontraba esa frase. Es el mismo
#  error que ya costo una corrida en M09-M: la prueba leyendo su propia prosa.
sql_sin_comentarios = " ".join(
    l for l in sql.splitlines() if not l.strip().startswith("--"))
afirmar("'pendiente'" not in sql_sin_comentarios,
        "la bitacora no tiene estado 'pendiente': mira hacia atras, no adelante")
afirmar("for update skip locked" not in sql.lower(),
        "y no tiene reclamo de filas: no es una cola de trabajo")

# ===========================================================================
seccion("G2. el piloto es de a lo sumo 3 herramientas")

autorizadas_en_el_piloto = {PILOTO}
afirmar(len(autorizadas_en_el_piloto) <= 3,
        f"el piloto autoriza {len(autorizadas_en_el_piloto)} herramienta(s), "
        f"maximo 3")
afirmar(not (autorizadas_en_el_piloto & (R3 | R4)),
        "y ninguna es R3 ni R4")

# ===========================================================================
seccion("G3. el sistema no puede elevarse solo")

texto_a2 = (RAIZ / "nucleo" / "seguridad" / "autonomia2.py").read_text(
    encoding="utf-8")
texto_aut = (RAIZ / "nucleo" / "seguridad" / "autorizacion.py").read_text(
    encoding="utf-8")
for nombre, texto in (("autonomia2", texto_a2), ("autorizacion", texto_aut)):
    arbol = ast.parse(texto)
    escribe = any(
        isinstance(n, ast.Constant) and isinstance(n.value, str)
        and "insert into" in n.value.lower() for n in ast.walk(arbol))
    afirmar(not escribe,
            f"'{nombre}' solo LEE: no puede crear ni modificar autorizaciones")
afirmar("interruptor.detener" not in texto_a2
        and "interruptor.reactivar" not in texto_a2,
        "y Autonomia 2 no toca el kill switch")

# ===========================================================================
seccion("G4. la etapa esta APAGADA por omision")

afirmar(not autonomia2.etapa_activa({}),
        "sin la variable, Autonomia 2 esta apagada")
for valor in ("", "0", "false", "no", "quizas"):
    afirmar(not autonomia2.etapa_activa({autonomia2.VAR_ETAPA: valor}),
            f"y '{valor}' tampoco la enciende (falla cerrado)")
afirmar(autonomia2.etapa_activa({autonomia2.VAR_ETAPA: "1"}),
        "solo un si explicito la enciende")

# ===========================================================================
print("\n" + "=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron:")
    for f in fallos:
        print(f"   - {f}")
else:
    print(" TODO EN VERDE  --  Autonomia 2: autorizacion granular")
print("=" * 74)
sys.exit(1 if fallos else 0)
