# -*- coding: utf-8 -*-
"""
================================================================================
 PRE-ACTIVACION DE AUTONOMIA 2  --  validacion final del piloto 'crear_tag_crm'
================================================================================

    py -3.13 tests/test_autonomia2_preactivacion.py

QUE SE MIDE, Y POR QUE ASI
--------------------------
Se sustituye 'requests' DENTRO de 'nucleo/herramientas/http.py', no el ejecutor:
asi corre el codigo real --frontera incluida-- y lo unico que no ocurre es el
viaje por la red. Si el contador sube, la llamada HABRIA SALIDO. Es la misma
tecnica de tests/test_frontera_externa.py, y por el mismo motivo: sustituir el
ejecutor saltearia justo el control que hay que probar.

LOS DOCE PUNTOS DEL BLOQUE A
----------------------------
No se afirma que un mecanismo exista. Se afirma cuantas llamadas salieron.

LIMITE, DICHO
-------------
La parte estatica (puntos 8 y 9) lee el arbol sintactico: ve lo que esta
ESCRITO en 'nucleo/'. No ve despacho dinamico, ni una libreria HTTP que nadie
declare, ni codigo fuera de 'nucleo/'. Por eso los puntos 8 y 9 tienen ademas
su mitad dinamica -- la estatica dice "no hay caminos nuevos escritos", la
dinamica dice "los que hay, frenan".
================================================================================
"""

from __future__ import annotations

import ast
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                            # noqa: E402
from nucleo.herramientas import http as ejecutor_http              # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguridad import (autonomia2, autorizacion,            # noqa: E402
                              frontera, idempotencia, interruptor)

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug
PILOTO = "crear_tag_crm"

fallos: list[str] = []
salidas: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que
          + (f"   <- {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def seccion(t: str) -> None:
    print(f"\n--- {t} ---")


def herramienta(nombre: str):
    h = next((x for x in CONFIG.herramientas if x.nombre == nombre), None)
    assert h is not None, f"'{nombre}' no esta en el catalogo"
    return h


# ---------------------------------------------------------------------------
#  LA RED, SUSTITUIDA. Nada viaja; se cuenta lo que habria viajado.
# ---------------------------------------------------------------------------
class _Respuesta:
    #  'ok' hace falta: http.py lo consulta despues de la llamada. Sin el, el
    #  efecto SALE y revienta al post-procesar -- lo que deja un desenlace
    #  FALLIDA correcto para un falso incompleto, no para una ejecucion sana.
    ok = True
    status_code = 200
    text = "{}"
    headers = {"Content-Type": "application/json"}

    def raise_for_status(self):
        return None

    def json(self):
        #  Con la forma que espera 'extraer_de: tag'. Sin esto el efecto SALE y
        #  el post-proceso revienta: el desenlace queda FALLIDA, que es correcto
        #  pero no es el caso que esta seccion quiere demostrar.
        return {"tag": {"id": "tag-falso", "name": "x"},
                "id": "tag-falso", "name": "x"}


class _RequestsFalso:
    def _anotar(self, metodo, url, **kw):
        salidas.append(f"{metodo} {url}")
        return _Respuesta()

    def get(self, url, **kw):
        return self._anotar("GET", url, **kw)

    def post(self, url, **kw):
        return self._anotar("POST", url, **kw)

    def request(self, metodo, url, **kw):
        return self._anotar(metodo, url, **kw)


ejecutor_http.requests = _RequestsFalso()
ejecutor_http.headers_de = lambda herramienta, tenant=None: {}

AHORA = datetime.now(timezone.utc)
BITACORA: list[dict] = []


def _autorizacion(_tenant, herr, **kw):
    """Solo el piloto esta autorizado. Las demas, no -- como en el piloto real."""
    if herr != PILOTO:
        return None
    return {"id": "00000000-0000-0000-0000-0000000000a1", "herramienta": herr,
            "estado": "autorizada", "estado_anterior": None, "nivel_maximo": 2,
            "vigente_desde": AHORA - timedelta(days=1), "vigente_hasta": None,
            "autorizado_por": "jefe.operaciones", "motivo": "piloto",
            "limites": {"por_dia": 20}, "creado_en": AHORA}


ESTADO = {"interruptor": "activo", "nivel": 2, "jwt": "", "etapa": True,
          "autoriza": True}


def _preparar():
    """Las respuestas de la base. Se sustituye la RESPUESTA, nunca el gate."""
    persistencia.estado_autonomia = lambda t: {
        "estado": ESTADO["interruptor"], "estado_anterior": None,
        "actor": "prueba", "motivo": "prueba", "creado_en": None}
    persistencia.registrar_auditoria = lambda *a, **k: None
    persistencia.nivel_autonomia = lambda t: (
        None if ESTADO["nivel"] is None else
        {"nivel": ESTADO["nivel"], "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba", "actor": "prueba",
         "motivo": "", "creado_en": None})
    persistencia.autorizacion_herramienta = (
        lambda t, h: _autorizacion(t, h) if ESTADO["autoriza"] else None)
    persistencia.secreto_jwt_en_base = lambda: ESTADO["jwt"]
    persistencia.registrar_ejecucion_autonoma = (
        lambda tenant, **kw: BITACORA.append(dict(kw)))
    persistencia.reclamar_operacion_externa = _reclamar
    persistencia.finalizar_operacion_externa = _finalizar
    os.environ[autonomia2.VAR_ETAPA] = "1" if ESTADO["etapa"] else "0"


OPERACIONES: dict[str, dict] = {}


def _reclamar(tenant, clave, herr, huella, origen, vence,
              reintentar_fallida=False):
    previa = OPERACIONES.get(clave)
    if previa is None:
        OPERACIONES[clave] = {"huella": huella, "estado": "ejecutando",
                              "respuesta": None}
        return {"decision": "ejecutar", "fila": {"intentos": 1}}
    if previa["huella"] != huella:
        return {"decision": "rechazada", "fila": previa}
    if previa["estado"] == "exitosa":
        return {"decision": "repetida",
                "fila": {"estado": "exitosa", "intentos": 1,
                         "respuesta": previa["respuesta"]}}
    return {"decision": "en_curso", "fila": previa}


def _finalizar(tenant, clave, estado, respuesta=None, error=None):
    if clave in OPERACIONES:
        OPERACIONES[clave].update(estado=estado, respuesta=respuesta)


class Sesion:
    verificado = True
    nivel = 99
    id_cliente = "5832"
    sn_onu = "X"
    interfaz_lan = ""
    identificador_canal = "573000000000"
    rol_siguiente = None


def intentar(nombre=PILOTO, *, origen="prueba", argumentos=None):
    """Ejecuta por el camino real. Devuelve cuantas llamadas SALIERON."""
    n0 = len(salidas)
    error = ""
    try:
        motor._ejecutar_tool(
            herramienta(nombre), Sesion(),
            argumentos if argumentos is not None else {"name": "etiqueta"},
            TENANT, CONFIG.variables_tenant, origen=origen)
    except Exception as e:                                       # noqa: BLE001
        error = f"{type(e).__name__}: {str(e).splitlines()[0][:80]}"
    return len(salidas) - n0, error


def reiniciar(**cambios):
    ESTADO.update({"interruptor": "activo", "nivel": 2, "jwt": "",
                   "etapa": True, "autoriza": True})
    ESTADO.update(cambios)
    OPERACIONES.clear()
    BITACORA.clear()
    _preparar()


# ===========================================================================
seccion("1. sujeto al kill switch")

reiniciar(interruptor="detenido")
salio, err = intentar()
afirmar(salio == 0, f"1. con el interruptor DETENIDO no sale nada ({salio})", err)
afirmar(interruptor.CODIGO_BLOQUEO in err or "detenido" in err.lower(),
        "1. y el motivo es el del interruptor", err)

reiniciar()
salio, err = intentar()
afirmar(salio == 1,
        f"1. desarme: con el interruptor ACTIVO y todo lo demas en regla, "
        f"sale UNA ({salio})", err)

# ===========================================================================
seccion("2. sujeto al nivel de autonomia")

for nivel, como in ((None, "sin fila (=0)"), (0, "techo 0"), (1, "techo 1")):
    reiniciar(nivel=nivel)
    salio, err = intentar()
    afirmar(salio == 0, f"2. con {como} no sale nada ({salio})", err)

reiniciar(nivel=2)
salio, _ = intentar()
afirmar(salio == 1, f"2. desarme: con techo 2 sale UNA ({salio})")

# ===========================================================================
seccion("3. sujeto a autorizacion especifica de la herramienta")

reiniciar(autoriza=False)
salio, err = intentar()
afirmar(salio == 0, f"3. sin autorizacion de '{PILOTO}' no sale nada ({salio})", err)

reiniciar()
ver = autorizacion.veredicto(TENANT, PILOTO)
afirmar(ver.permitido and ver.autorizacion_id,
        f"3. desarme: con la fila puesta, la autorizacion es la que manda "
        f"({ver.codigo})")

# ===========================================================================
seccion("4. sujeto a idempotencia")

reiniciar()
intentar(origen="wamid-idem")
salio, _ = intentar(origen="wamid-idem")
afirmar(salio == 0, f"4. el segundo pedido con la misma clave no sale ({salio})")
afirmar(len(salidas) > 0, "4. (y el primero si habia salido)")

# ===========================================================================
seccion("5. un 'decision' distinto exactamente de 'ejecutar' bloquea")

reiniciar()
originales = persistencia.reclamar_operacion_externa
for valor in ("ejecutar ", "EJECUTAR", "devolver", "", None, 0, True):
    reiniciar()
    persistencia.reclamar_operacion_externa = (
        lambda *a, **k: {"decision": valor, "fila": {"intentos": 1}})
    salio, err = intentar(origen=f"wamid-{valor!r}")
    afirmar(salio == 0, f"5. decision {valor!r} no ejecuta ({salio})", err)
persistencia.reclamar_operacion_externa = originales

reiniciar()
persistencia.reclamar_operacion_externa = (
    lambda *a, **k: {"decision": "ejecutar", "fila": {"intentos": 1}})
salio, _ = intentar(origen="wamid-desarme")
afirmar(salio == 1,
        f"5. desarme: con 'ejecutar' exacto SI sale ({salio}) -- los ceros de "
        f"arriba son la decision, no otra cosa")
reiniciar()

# ===========================================================================
seccion("6. no autorizada NO ejecuta aunque el nivel alcance")

#  Techo 3 y no 4 (M06-B, 21/09/2026): 3 es el tope de politica global, y un
#  techo guardado por encima se lee como INVALIDO -- falla cerrado. Con 4 este
#  punto seguiria dando 0, pero por el motivo equivocado.
reiniciar(nivel=3)
salio, err = intentar("cerrar_caso_crm",
                      argumentos={"caso_id": "x", "status": "Closed"})
afirmar(salio == 0,
        f"6. 'cerrar_caso_crm' con techo 3 y el piloto autorizado: no sale "
        f"nada ({salio})", err)

reiniciar(nivel=3)
salio, _ = intentar()
afirmar(salio == 1,
        f"6. desarme: en la MISMA corrida, la autorizada si sale ({salio})")

# ===========================================================================
seccion("7. la autorizacion no eleva el techo por si sola")

reiniciar(nivel=1)
persistencia.autorizacion_herramienta = lambda t, h: (
    None if h != PILOTO else {**_autorizacion(t, h), "nivel_maximo": 4})
ver = autorizacion.veredicto(TENANT, PILOTO)
afirmar(not ver.permitido and ver.codigo == autorizacion.NIVEL_INSUFICIENTE,
        f"7. autorizacion de nivel 4 con techo 1: bloquea ({ver.codigo})")
afirmar(ver.nivel_efectivo == 1,
        f"7. y el efectivo es el TECHO, no la autorizacion "
        f"({ver.nivel_efectivo})")
salio, err = intentar()
afirmar(salio == 0, f"7. y no sale nada ({salio})", err)
reiniciar()

# ===========================================================================
seccion("8. no hay ruta que ejecute el piloto saltandose frontera.py")

#  8a. ESTATICA: quien puede llegar al ejecutor con este nombre de herramienta.
llamadores = []
for f in (RAIZ / "nucleo").rglob("*.py"):
    texto = f.read_text(encoding="utf-8", errors="replace")
    if PILOTO not in texto:
        continue
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        continue
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("ejecutar", "ejecutar_asincrono"):
            llamadores.append(str(f.relative_to(RAIZ)))
llamadores = sorted(set(llamadores))
print(f"       modulos que nombran '{PILOTO}' y llaman al ejecutor: {llamadores}")

#  Todo lo que llega al ejecutor pasa por _exigir_frontera(): el control esta
#  EN el ejecutor, no en los llamadores. Se comprueba que siga estando.
texto_http = (RAIZ / "nucleo" / "herramientas" / "http.py").read_text(
    encoding="utf-8")
#  Por AST y no por texto (M06-A agrego 'argumentos=' a la llamada, y un
#  texto exacto habria fallado por la forma y no por el fondo): lo que importa
#  es que el ejecutor LLAME a frontera.exigir.
llama_exigir = any(
    isinstance(n, ast.Call) and ast.unparse(n.func) == "frontera.exigir"
    for n in ast.walk(ast.parse(texto_http)))
afirmar(llama_exigir,
        "8a. el ejecutor sigue exigiendo el permiso de la frontera")
afirmar(texto_http.count("def ejecutar") >= 1
        and "_exigir" in texto_http,
        "8a. y lo hace en un solo lugar, no por llamador")

#  8b. DINAMICA: la ruta de escalamiento -- la unica del nucleo que nombra el
#  piloto ademas del motor-- NO abre permiso, asi que queda BLOQUEADA.
texto_esc = (RAIZ / "nucleo" / "seguimiento" / "escalamiento.py").read_text(
    encoding="utf-8")
afirmar("frontera" not in texto_esc,
        "8b. escalamiento.py no abre permiso (no lo necesita: no debe escribir "
        "solo)")
n0 = len(salidas)
testigo = frontera._PERMISO.set(None)
try:
    ejecutor_http.ejecutar(herramienta(PILOTO), {"name": "x"}, TENANT,
                           CONFIG.variables_tenant)
    bloqueo = ""
except frontera.AccionExternaNoAutorizada as e:
    bloqueo = e.codigo
except Exception as e:                                           # noqa: BLE001
    bloqueo = type(e).__name__
finally:
    frontera._PERMISO.reset(testigo)
afirmar(len(salidas) - n0 == 0 and bloqueo == frontera.SIN_AUTORIZAR,
        f"8b. llamar al ejecutor sin permiso NO saca nada "
        f"(salio {len(salidas)-n0}, codigo {bloqueo})")

#  8c. ni siquiera con el tenant vacio, que era el fail-open del paso 10.14.
n0 = len(salidas)
testigo = frontera._PERMISO.set(None)
try:
    ejecutor_http.ejecutar(herramienta(PILOTO), {"name": "x"}, None, None)
except Exception:                                                # noqa: BLE001
    pass
finally:
    frontera._PERMISO.reset(testigo)
afirmar(len(salidas) - n0 == 0,
        f"8c. tampoco con tenant vacio ({len(salidas)-n0})")

# ===========================================================================
seccion("9. no hay endpoint de ejecucion directa que la saltee")

h = herramienta(PILOTO)
afirmar(not getattr(h, "invocable_por_servicio", False),
        "9. el piloto NO es invocable por servicio: la ruta "
        "/interno/herramienta/<nombre> no puede dispararlo")

#  9b. La ruta lo hace cumplir: la comprobacion esta escrita en api.py.
texto_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
afirmar("if not herramienta.invocable_por_servicio:" in texto_api,
        "9b. la ruta /interno rechaza lo que no esta declarado invocable")

#  9c. CORREGIDO el 19/09/2026. Antes la comprobacion vivia SOLO en la ruta y
#  llamar a 'ejecutar_para_servicio' directamente con una herramienta NO
#  invocable la ejecutaba (1 llamada externa contada). Ahora la funcion la hace
#  cumplir donde ocurre el efecto. La de la ruta no se quito: contesta un 400
#  con un mensaje util antes de llegar hasta aca.
reiniciar()
n0 = len(salidas)
err9c = ""
try:
    motor.ejecutar_para_servicio(CONFIG, h, {"name": "x"})
except Exception as e:                                           # noqa: BLE001
    err9c = f"{type(e).__name__}: {str(e).splitlines()[0][:70]}"
directo = len(salidas) - n0
afirmar(directo == 0,
        f"9c. una herramienta NO invocable por servicio no sale por esa via "
        f"({directo})", err9c)
afirmar("invocable_por_servicio" in err9c,
        f"9c. y lo dice por su nombre, no por un fallo lateral", err9c)

#  Y el desarme: una que SI es invocable, con todo en verde, sale.
invocable = next(x for x in CONFIG.herramientas
                 if getattr(x, "invocable_por_servicio", False)
                 and not x.solo_lectura)
persistencia.autorizacion_herramienta = lambda t, hh: (
    _autorizacion(t, PILOTO) if hh == invocable.nombre else None)
err_inv = ""
try:
    motor.ejecutar_para_servicio(CONFIG, invocable, {"servicio": "5832"})
except Exception as e:                                           # noqa: BLE001
    err_inv = f"{type(e).__name__}: {str(e).splitlines()[0][:70]}"
#  Lo que se afirma es que NO la frena ESTE control. Que llegue o no a la red
#  depende de argumentos que esta prueba no tiene, y afirmarlo aqui mediria
#  otra cosa.
afirmar("invocable_por_servicio" not in err_inv,
        f"9c. desarme: '{invocable.nombre}' SI es invocable y el control no la "
        f"frena", err_inv)

#  invocable + SIN autorizacion granular -> 0. Las demas barreras siguen.
persistencia.autorizacion_herramienta = lambda t, hh: None
n0 = len(salidas)
try:
    motor.ejecutar_para_servicio(CONFIG, invocable, {"servicio": "5832"})
except Exception:                                                # noqa: BLE001
    pass
afirmar(len(salidas) - n0 == 0,
        f"9c. invocable pero SIN autorizacion: no sale ({len(salidas)-n0})")
reiniciar()

#  9d. Y lo que de verdad la gobierna sigue siendo la frontera: por esa misma
#  via, sin autorizacion granular, no sale nada.
reiniciar(autoriza=False)
n0 = len(salidas)
try:
    motor.ejecutar_para_servicio(CONFIG, h, {"name": "x"})
except Exception:                                                # noqa: BLE001
    pass
afirmar(len(salidas) - n0 == 0,
        f"9d. por esa MISMA via, sin autorizacion granular no sale nada "
        f"({len(salidas)-n0}): la frontera la gobierna igual")

#  9e. Y con una R3, que el piloto no autoriza, tampoco.
reiniciar(nivel=4)
n0 = len(salidas)
try:
    motor.ejecutar_para_servicio(CONFIG, herramienta("reiniciar_ont"),
                                 {"servicio": "5832"})
except Exception:                                                # noqa: BLE001
    pass
afirmar(len(salidas) - n0 == 0,
        f"9e. ni con una R3 y techo 4: no esta autorizada ({len(salidas)-n0})")

#  Las dos unicas puertas siguen siendo las de frontera.py.
texto_frontera = (RAIZ / "nucleo" / "seguridad" / "frontera.py").read_text(
    encoding="utf-8")
arbol_f = ast.parse(texto_frontera)
puertas = sorted(n.name for n in ast.walk(arbol_f)
                 if isinstance(n, ast.FunctionDef)
                 and any(isinstance(d, ast.Name) and d.id == "contextmanager"
                         for d in n.decorator_list))
#  M06-A (21/09/2026) agrego la tercera A PROPOSITO: 'critica', la unica por
#  la que sale una herramienta irreversible, y que exige TODAS las compuertas
#  de 'autonoma' mas una aprobacion humana atada a la accion. Una cuarta
#  tiene que volver a romper esta prueba.
afirmar(puertas == ["autonoma", "critica", "humana"],
        f"9. frontera.py tiene exactamente sus tres puertas ({puertas})")

# ===========================================================================
seccion("10/11. que registra la bitacora")

reiniciar()
salio, _ = intentar(origen="wamid-bitacora")
permitidas = [b for b in BITACORA if b.get("decision") == "permitida"]
autorizaciones = [b for b in permitidas if b.get("resultado") in (None, "")]
desenlaces = [b for b in permitidas if b.get("resultado") not in (None, "")]
afirmar(salio == 1 and len(autorizaciones) == 1 and len(desenlaces) == 1,
        f"10. una ejecucion real deja DOS filas: autorizacion + desenlace "
        f"(salio={salio}, {len(autorizaciones)}/{len(desenlaces)})")
afirmar(desenlaces and desenlaces[0].get("resultado") == "exitosa",
        f"10. y el desenlace es EXITOSA "
        f"({desenlaces[0].get('resultado') if desenlaces else None!r})")
afirmar(desenlaces and desenlaces[0].get("clave_idempotencia"),
        "10. con la clave de idempotencia: el puente con operaciones_externas")
fila = autorizaciones[0] if autorizaciones else {}
afirmar(fila.get("resultado") in (None, ""),
        f"11. la fila de autorizacion no se marca como fallida "
        f"({fila.get('resultado')!r})")

reiniciar(autoriza=False)
salio, _ = intentar(origen="wamid-bloqueada")
bloqueadas = [b for b in BITACORA if b.get("decision") == "bloqueada"]
afirmar(salio == 0 and len(bloqueadas) == 1,
        f"11. una bloqueada deja UNA fila 'bloqueada' ({len(bloqueadas)})")
afirmar(bloqueadas and bloqueadas[0].get("resultado") == "no_ejecutada",
        f"11. con resultado 'no_ejecutada', NO 'fallida': nunca llego al efecto "
        f"({bloqueadas[0].get('resultado') if bloqueadas else None!r})")
afirmar(bloqueadas and bloqueadas[0].get("codigo") ==
        autorizacion.SIN_AUTORIZACION,
        "11. y con el codigo de la compuerta que freno")

#  EL PUENTE, medido: la clave del desenlace es la de operaciones_externas.
reiniciar()
intentar(origen="wamid-resultado")
desenlace = [b for b in BITACORA
             if b.get("decision") == "permitida"
             and b.get("resultado") not in (None, "")][0]
claves_registro = list(OPERACIONES.keys())
afirmar(desenlace.get("clave_idempotencia") in claves_registro,
        f"10. la clave del desenlace existe en operaciones_externas "
        f"({desenlace.get('clave_idempotencia')})")

# ===========================================================================
seccion("12. una repetida no produce un segundo efecto")

reiniciar()
for _ in range(3):
    intentar(origen="wamid-repetida")
propios = [s for s in salidas if True]
reiniciar()
n0 = len(salidas)
for _ in range(3):
    intentar(origen="wamid-repetida-2")
afirmar(len(salidas) - n0 == 1,
        f"12. tres pedidos con la misma clave -> UN solo efecto "
        f"({len(salidas)-n0})")

# ===========================================================================
seccion("B. 'limites': metadata, no control  --  clasificado, no supuesto")

#  Se AFIRMA el efecto: un limite imposible no cambia nada. Si algun dia
#  alguien empieza a evaluarlos, esta prueba falla y hay que reclasificarlos
#  en el informe -- que es exactamente lo que debe pasar.
reiniciar()
persistencia.autorizacion_herramienta = lambda t, h: (
    None if h != PILOTO else {**_autorizacion(t, h),
                              "limites": {"por_dia": 0, "maximo": 0,
                                          "prohibido": True}})
ver = autorizacion.veredicto(TENANT, PILOTO)
afirmar(ver.permitido,
        f"B. con limites imposibles el veredicto SIGUE siendo permitido "
        f"({ver.codigo}): no se evaluan")
afirmar(ver.limites == {"por_dia": 0, "maximo": 0, "prohibido": True},
        "B. los limites se transportan tal cual (son metadata legible)")
salio, _ = intentar(origen="wamid-limites")
afirmar(salio == 1,
        f"B. y la ejecucion sale igual ({salio}): 'limites' NO protege nada hoy")

#  Y el codigo reservado no lo devuelve nadie: esta definido y sin usar.
usos = []
for f in (RAIZ / "nucleo").rglob("*.py"):
    for i, linea in enumerate(f.read_text(encoding="utf-8",
                                          errors="replace").splitlines(), 1):
        pelado = linea.strip()
        if "LIMITE_EXCEDIDO" not in pelado:
            continue
        if pelado.startswith("#") or "LIMITE_EXCEDIDO =" in pelado:
            continue
        usos.append(f"{f.name}:{i}")
afirmar(usos == [],
        f"B. LIMITE_DE_AUTORIZACION_EXCEDIDO sigue sin devolverse en ningun "
        f"camino ({usos})")
reiniciar()

# ===========================================================================
print("\n" + "=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"   - {f}")
else:
    print(" TODO EN VERDE  --  pre-activacion: el piloto tiene una sola frontera")
print("=" * 74)
sys.exit(1 if fallos else 0)
