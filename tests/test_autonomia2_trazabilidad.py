# -*- coding: utf-8 -*-
"""
================================================================================
 TRAZABILIDAD DE LA EJECUCION AUTONOMA  --  el puente, y que no mienta
================================================================================

    py -3.13 tests/test_autonomia2_trazabilidad.py

EL PROBLEMA QUE CIERRA
----------------------
'asistente.ejecucion_autonoma' registraba QUE SE AUTORIZO.
'asistente.operaciones_externas' registra COMO TERMINO.
Entre las dos no habia puente: la clave estaba en una columna que nadie llenaba.

EL PUENTE ES EL QUE YA EXISTIA
------------------------------
No hay tabla nueva ni columna nueva. 'operaciones_externas' tiene clave
primaria (organization_id, clave), y 'ejecucion_autonoma' ya tenia
organization_id + clave_idempotencia. Lo unico que faltaba era escribirla.

DOS RENGLONES POR INTENTO, SIN COLUMNA NUEVA
--------------------------------------------
    resultado IS NULL      AUTORIZACION  -- 'creado_en' = momento de autorizacion
    resultado IS NOT NULL  DESENLACE     -- 'creado_en' = momento de ejecucion,
                                            y trae la clave

LO QUE SE AFIRMA
----------------
El efecto: cuantas llamadas SALIERON, y que dicen los renglones. No que exista
un mecanismo.
================================================================================
"""

from __future__ import annotations

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
from nucleo.seguridad import autonomia2, frontera                  # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug
PILOTO = "crear_tag_crm"

fallos: list[str] = []
salidas: list[str] = []
BITACORA: list[dict] = []
OPERACIONES: dict[str, dict] = {}
AHORA = datetime.now(timezone.utc)
CANDADO = threading.Lock()


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    print(("  [ok]    " if condicion else "  [FALLA] ") + que
          + (f"   <- {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def seccion(t: str) -> None:
    print(f"\n--- {t} ---")


def herramienta(nombre: str):
    h = next((x for x in CONFIG.herramientas if x.nombre == nombre), None)
    assert h is not None, nombre
    return h


class _Respuesta:
    ok = True
    status_code = 200
    text = "{}"
    headers = {"Content-Type": "application/json"}

    def raise_for_status(self):
        return None

    def json(self):
        return {"tag": {"id": "tag-falso", "name": "x"},
                "id": "tag-falso", "name": "x"}


REVIENTA = {"si": False}


class _RequestsFalso:
    def _anotar(self, metodo, url, **kw):
        salidas.append(f"{metodo} {url}")
        if REVIENTA["si"]:
            raise RuntimeError("el CRM contesto 500")
        return _Respuesta()

    def get(self, url, **kw):
        return self._anotar("GET", url, **kw)

    def post(self, url, **kw):
        return self._anotar("POST", url, **kw)

    def request(self, metodo, url, **kw):
        return self._anotar(metodo, url, **kw)


ejecutor_http.requests = _RequestsFalso()
ejecutor_http.headers_de = lambda herramienta, tenant=None: {}

ESTADO = {"autoriza": True}


def _reclamar(tenant, clave, herr, huella, origen, vence,
              reintentar_fallida=False):
    """El registro real, en memoria. Con candado: el indice unico de Postgres."""
    with CANDADO:
        previa = OPERACIONES.get(clave)
        if previa is None:
            OPERACIONES[clave] = {"huella": huella, "estado": "ejecutando",
                                  "herramienta": herr, "origen": origen,
                                  "respuesta": None, "error": None}
            return {"decision": "ejecutar", "fila": {"intentos": 1}}
        if previa["huella"] != huella:
            return {"decision": "rechazada", "fila": previa}
        if previa["estado"] == "exitosa":
            return {"decision": "repetida",
                    "fila": {"estado": "exitosa", "intentos": 1,
                             "respuesta": previa["respuesta"]}}
        if previa["estado"] == "fallida" and not reintentar_fallida:
            return {"decision": "fallida", "fila": previa}
        return {"decision": "en_curso", "fila": previa}


def _finalizar(tenant, clave, estado, respuesta=None, error=None):
    fila = OPERACIONES.get(clave)
    if fila is not None:
        fila.update(estado=estado, respuesta=respuesta, error=error)


def _preparar():
    persistencia.estado_autonomia = lambda t: {
        "estado": "activo", "estado_anterior": None, "actor": "prueba",
        "motivo": "", "creado_en": None}
    persistencia.registrar_auditoria = lambda *a, **k: None
    persistencia.nivel_autonomia = lambda t: {
        "nivel": 2, "nivel_anterior": None, "organization_id": "org-prueba", "org_consultada": "org-prueba", "actor": "prueba", "motivo": "",
        "creado_en": None}
    persistencia.autorizacion_herramienta = lambda t, h: (
        None if (h != PILOTO or not ESTADO["autoriza"]) else
        {"id": "00000000-0000-0000-0000-0000000000a1", "herramienta": h,
         "estado": "autorizada", "estado_anterior": None, "nivel_maximo": 2,
         "vigente_desde": AHORA - timedelta(days=1), "vigente_hasta": None,
         "autorizado_por": "jefe.operaciones", "motivo": "piloto",
         "limites": {}, "creado_en": AHORA})
    persistencia.secreto_jwt_en_base = lambda: ""
    persistencia.registrar_ejecucion_autonoma = (
        lambda tenant, **kw: BITACORA.append(dict(kw, tenant=tenant)))
    persistencia.reclamar_operacion_externa = _reclamar
    persistencia.finalizar_operacion_externa = _finalizar
    os.environ[autonomia2.VAR_ETAPA] = "1"


class Sesion:
    verificado = True
    nivel = 99
    id_cliente = "5832"
    sn_onu = "X"
    interfaz_lan = ""
    identificador_canal = "573000000000"
    rol_siguiente = None


def reiniciar(**cambios):
    ESTADO.update({"autoriza": True})
    ESTADO.update(cambios)
    REVIENTA["si"] = False
    BITACORA.clear()
    OPERACIONES.clear()
    salidas.clear()
    _preparar()


def intentar(origen, argumentos=None):
    try:
        motor._ejecutar_tool(
            herramienta(PILOTO), Sesion(),
            argumentos if argumentos is not None else {"name": "etiqueta"},
            TENANT, CONFIG.variables_tenant, origen=origen)
    except Exception:                                            # noqa: BLE001
        pass


def autorizaciones():
    return [b for b in BITACORA if b.get("decision") == "permitida"
            and b.get("resultado") in (None, "")]


def desenlaces():
    return [b for b in BITACORA if b.get("decision") == "permitida"
            and b.get("resultado") not in (None, "")]


def bloqueadas():
    return [b for b in BITACORA if b.get("decision") == "bloqueada"]


def vinculado(fila) -> bool:
    """El renglon apunta a una fila real de operaciones_externas."""
    clave = fila.get("clave_idempotencia") or ""
    return bool(clave) and clave in OPERACIONES


# ===========================================================================
seccion("CASO 1 -- autorizacion BLOQUEADA")

reiniciar(autoriza=False)
intentar("wamid-c1")
afirmar(len(salidas) == 0, f"1. no hay efecto externo ({len(salidas)})")
afirmar(len(bloqueadas()) == 1 and len(desenlaces()) == 0,
        f"1. queda UNA fila bloqueada y NINGUN desenlace "
        f"({len(bloqueadas())}/{len(desenlaces())})")
afirmar(bloqueadas()[0].get("resultado") == "no_ejecutada",
        f"1. NO se registra como fallida ({bloqueadas()[0].get('resultado')!r})")
afirmar(OPERACIONES == {},
        f"1. ni aparece como operacion ejecutada: el registro esta vacio "
        f"({list(OPERACIONES)})")
afirmar(not bloqueadas()[0].get("clave_idempotencia"),
        "1. y sin clave: nunca hubo operacion que reclamar")

# ===========================================================================
seccion("CASO 2 -- ejecucion EXITOSA")

reiniciar()
intentar("wamid-c2")
afirmar(len(salidas) == 1, f"2. ocurre exactamente UN efecto ({len(salidas)})")
afirmar(len(autorizaciones()) == 1, f"2. existe la fila de autorizacion "
                                    f"({len(autorizaciones())})")
afirmar(len(OPERACIONES) == 1, f"2. existe la fila de operaciones_externas "
                               f"({len(OPERACIONES)})")
afirmar(len(desenlaces()) == 1, f"2. y la fila de desenlace ({len(desenlaces())})")
d = desenlaces()[0] if desenlaces() else {}
afirmar(vinculado(d),
        f"2. AMBAS quedan vinculadas por la clave "
        f"({d.get('clave_idempotencia')})")
afirmar(d.get("resultado") == frontera.EXITOSA,
        f"2. el estado final es EXITOSA ({d.get('resultado')!r})")
clave = d.get("clave_idempotencia")
afirmar(OPERACIONES[clave]["estado"] == "exitosa",
        f"2. y coincide con el de operaciones_externas "
        f"({OPERACIONES[clave]['estado']!r})")
afirmar(clave.startswith("wamid-c2|" + PILOTO + "|"),
        f"2. la idempotencia sigue asociada: la clave conserva origen y "
        f"herramienta ({clave})")
afirmar(d.get("herramienta") == PILOTO and d.get("tenant") == TENANT,
        "2. y el renglon dice herramienta y organizacion")
afirmar(d.get("actor") and d.get("evidencia"),
        f"2. con origen/autonomia: actor={d.get('actor')!r} "
        f"evidencia={d.get('evidencia')!r}")

# ===========================================================================
seccion("CASO 3 -- ejecucion con ERROR REAL")

reiniciar()
REVIENTA["si"] = True
intentar("wamid-c3")
afirmar(len(salidas) == 1, f"3. el efecto SI se intento ({len(salidas)})")
afirmar(len(OPERACIONES) == 1, f"3. existe la fila de operaciones_externas "
                               f"({len(OPERACIONES)})")
d = desenlaces()[0] if desenlaces() else {}
afirmar(len(desenlaces()) == 1 and vinculado(d),
        f"3. el desenlace queda vinculado ({d.get('clave_idempotencia')})")
afirmar(d.get("resultado") == frontera.FALLIDA,
        f"3. estado final FALLIDA ({d.get('resultado')!r})")
clave = d.get("clave_idempotencia")
afirmar((OPERACIONES[clave].get("error") or "").strip() != "",
        f"3. el error queda disponible por la referencia, en "
        f"operaciones_externas ({OPERACIONES[clave].get('error')})")
texto = " ".join(str(v) for v in d.values())
afirmar("500" not in texto,
        "3. y NO se copia el error: una referencia basta")

# ===========================================================================
seccion("CASO 4 -- repeticion con la MISMA clave")

reiniciar()
intentar("wamid-c4")
intentar("wamid-c4")
afirmar(len(salidas) == 1, f"4. no existe un segundo efecto ({len(salidas)})")
exitosos = [x for x in desenlaces() if x.get("resultado") == frontera.EXITOSA]
afirmar(len(exitosos) == 1,
        f"4. y UN solo desenlace EXITOSA: no se inventa una segunda ejecucion "
        f"({len(exitosos)})")
no_ejec = [x for x in desenlaces() if x.get("resultado") == frontera.NO_EJECUTADA]
afirmar(len(no_ejec) == 1 and no_ejec[0].get("codigo") == "repetida",
        f"4. el segundo intento queda anotado como 'repetida', no como "
        f"ejecucion ({[x.get('codigo') for x in no_ejec]})")
afirmar(len({x.get("clave_idempotencia") for x in desenlaces()}) == 1,
        "4. la referencia permanece consistente: los dos apuntan a la misma clave")
afirmar(len(OPERACIONES) == 1,
        f"4. y hay UNA sola fila en operaciones_externas ({len(OPERACIONES)})")

# ===========================================================================
seccion("CASO 5 -- concurrencia")

reiniciar()


def una():
    intentar("wamid-c5")


hilos = [threading.Thread(target=una) for _ in range(8)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()

afirmar(len(salidas) == 1, f"5. 8 hilos -> UN solo efecto ({len(salidas)})")
afirmar(len(OPERACIONES) == 1,
        f"5. y UNA sola fila en operaciones_externas ({len(OPERACIONES)})")
exitosos = [x for x in desenlaces() if x.get("resultado") == frontera.EXITOSA]
afirmar(len(exitosos) == 1,
        f"5. un solo desenlace EXITOSA ({len(exitosos)})")
afirmar(all(vinculado(x) for x in desenlaces()),
        "5. todos los renglones de desenlace apuntan a una fila real")
afirmar(len({x.get("clave_idempotencia") for x in desenlaces()}) == 1,
        "5. y todos a la MISMA: trazabilidad consistente")
otros = [x.get("resultado") for x in desenlaces()
         if x.get("resultado") != frontera.EXITOSA]
afirmar(all(r == frontera.NO_EJECUTADA for r in otros),
        f"5. los demas intentos quedan 'no_ejecutada', ninguno fingido "
        f"({sorted(set(otros))})")

# ===========================================================================
seccion("C. los estados, y la diferencia que importa")

afirmar((frontera.EXITOSA, frontera.FALLIDA, frontera.NO_EJECUTADA)
        == ("exitosa", "fallida", "no_ejecutada"),
        "C. los tres desenlaces de la bitacora estan declarados")
#  'ejecutando' y 'expirada' NO son de esta bitacora: viven en
#  operaciones_externas, que es quien reclama. Duplicarlos seria un segundo
#  mecanismo.
texto_fr = (RAIZ / "nucleo" / "seguridad" / "frontera.py").read_text(
    encoding="utf-8")
#  Por AST y no por texto: frontera.py NOMBRA 'SEGUNDOS_VENCIDA' en un
#  comentario para explicar de quien es. Buscarlo como texto leia esa prosa
#  como si fuera una definicion -- el mismo error de la prueba que se lee a si
#  misma. Lo que importa es que NO lo DEFINA.
import ast as _ast                                               # noqa: E402
_arbol_fr = _ast.parse(texto_fr)
_definidos = {t.id for n in _ast.walk(_arbol_fr)
              if isinstance(n, _ast.Assign)
              for t in n.targets if isinstance(t, _ast.Name)}
afirmar(not (_definidos & {"EJECUTANDO", "EXPIRADA"}),
        f"C. 'ejecutando' y 'expirada' no se duplican en la frontera "
        f"({sorted(_definidos & {'EJECUTANDO', 'EXPIRADA'})})")
afirmar("SEGUNDOS_VENCIDA" not in _definidos,
        "C. y el vencimiento de 300 s sigue definido solo en idempotencia.py")

import inspect                                                   # noqa: E402
from nucleo.seguridad import idempotencia                        # noqa: E402
afirmar(idempotencia.SEGUNDOS_VENCIDA == 300,
        f"C. el vencimiento sigue en 300 s ({idempotencia.SEGUNDOS_VENCIDA})")

# ===========================================================================
seccion("G. no hay arquitectura paralela")

fuente_fr = inspect.getsource(frontera)
afirmar("create table" not in fuente_fr.lower(),
        "G. la frontera no crea tablas")
sql = (RAIZ / "supabase" / "202609221000_autonomia2_autorizacion.sql").read_text(
    encoding="utf-8")
sin_comentarios = " ".join(l for l in sql.splitlines()
                           if not l.strip().startswith("--"))
afirmar(sin_comentarios.lower().count("create table") == 3,
        "G. siguen siendo TRES tablas: no se agrego una cuarta")
afirmar("clave_idempotencia" in sql,
        "G. y el puente usa la columna que ya existia")

# ===========================================================================
print("\n" + "=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"   - {f}")
else:
    print(" TODO EN VERDE  --  trazabilidad cerrada sin arquitectura paralela")
print("=" * 74)
sys.exit(1 if fallos else 0)
