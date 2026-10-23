# -*- coding: utf-8 -*-
"""
================================================================================
 LA FRONTERA DE ACCIONES EXTERNAS  --  que no quede ningun camino de salida
================================================================================

    py -3.13 tests/test_frontera_externa.py

DOS PRUEBAS DISTINTAS, Y HACEN FALTA LAS DOS
--------------------------------------------
1. COBERTURA (estatica). Recorre el AST de todo 'nucleo/' y encuentra cada
   llamada que puede producir un efecto externo. Falla si aparece una que no
   este en la lista permitida. Es la que caza el archivo NUEVO que alguien
   escriba el mes que viene.

2. BYPASS (dinamica). Intenta de verdad, por diez caminos distintos, que salga
   una escritura sin autorizacion. Cuenta las llamadas que HABRIAN salido.

COMO SE MIDE, Y POR QUE ASI
---------------------------
No se sustituye 'ejecutor_http.ejecutar' --eso saltearia justo el control que
hay que probar-- sino 'requests' DENTRO de ese modulo. Asi corre el codigo
real, incluida la comprobacion de la frontera, y lo unico que no ocurre es el
viaje por la red. Si el contador sube, la llamada habria salido.

LIMITES DE LA PARTE ESTATICA  --  dichos, no escondidos
-------------------------------------------------------
El AST ve lo que esta escrito. NO ve:
  * despacho dinamico ('getattr(requests, metodo)(...)', 'globals()[...]');
  * una libreria HTTP nueva que nadie declare aca (urllib3, aiohttp, httpx);
  * un subproceso que llame a 'curl';
  * codigo fuera de 'nucleo/' (cli/, django-crm/).
Por eso la lista permitida se revisa a mano cuando cambia, y la prueba dinamica
existe aparte: la estatica dice "no hay caminos nuevos ESCRITOS", la dinamica
dice "los que hay, frenan".
================================================================================
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                          # noqa: E402
from nucleo.herramientas import http as ejecutor_http            # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402
from nucleo.seguimiento import operativo                         # noqa: E402
from nucleo.seguridad import frontera                            # noqa: E402
from nucleo.seguridad import idempotencia                        # noqa: E402
from nucleo.seguridad import interruptor                         # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TENANT = CONFIG.identidad.slug

fallos: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  [{'ok' if condicion else 'NO'}]    {que}"
          + (f"\n           -> {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(que)


# =============================================================================
#  1. COBERTURA ESTATICA
# =============================================================================
#  Cada entrada es 'modulo::funcion' donde se admite una llamada con posible
#  efecto externo. Agregar una fila aca es una decision consciente: quien la
#  agregue tiene que poder decir por que esa llamada no necesita la frontera,
#  o donde la abre.
PERMITIDAS = {
    # --- EL EMBUDO DE ESCRITURAS ---------------------------------------------
    # Es el unico que manda POST/PUT/PATCH/DELETE de herramientas, y es quien
    # EXIGE el permiso (_exigir_frontera). 'ejecutar' aparece dos veces porque
    # '_pedir' esta anidada dentro suyo.
    "nucleo/herramientas/http.py::ejecutar",
    "nucleo/herramientas/http.py::_pedir",
    "nucleo/herramientas/http.py::ejecutar_asincrono",   # GET que sondea la tarea

    # --- LECTURAS (GET) ------------------------------------------------------
    # No son acciones: no llevan frontera a proposito. Detener la autonomia no
    # puede dejar ciego al que atiende.
    "nucleo/canales/api.py::diagnostico_smartolt",
    "nucleo/canales/api.py::_inventario_onu",
    "nucleo/herramientas/agregado.py::_contar",
    "nucleo/herramientas/estabilidad.py::resumir",
    "nucleo/herramientas/incidentes.py::_caidas_simultaneas",
    "nucleo/herramientas/incidentes.py::detectar",
    "nucleo/herramientas/incidentes.py::_detalle_de",
    "nucleo/herramientas/localidades.py::sincronizar",
    "nucleo/herramientas/sondeo.py::_pedir",
    "nucleo/observabilidad/consumo.py::consultar_saldo",
    "nucleo/seguimiento/escalamiento.py::caso_sigue_abierto",
    "nucleo/canales/whatsapp.py::plantillas_aprobadas",
    "nucleo/canales/whatsapp.py::descargar_media",

    # --- EL CANAL ------------------------------------------------------------
    # Mandarle el mensaje al cliente NO es una accion autonoma: con la autonomia
    # detenida el asistente sigue atendiendo, y eso es parte del diseño (ver el
    # encabezado de nucleo/seguridad/interruptor.py). Si algun dia se decide que
    # tambien debe frenarse, se saca de aqui y esta prueba lo exige.
    "nucleo/canales/whatsapp.py::_post",
    "nucleo/canales/whatsapp.py::subir_media",
}

SOSPECHOSAS = ("post", "put", "patch", "delete", "request", "get")


def _llamadas_externas(ruta: Path) -> list[tuple[str, str]]:
    """(funcion, que se llamo) de cada llamada a requests.* en el archivo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    encontradas = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for hijo in ast.walk(nodo):
            if not isinstance(hijo, ast.Call):
                continue
            f = hijo.func
            if (isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.value.id == "requests"
                    and f.attr in SOSPECHOSAS):
                encontradas.append((nodo.name, f"requests.{f.attr}"))
    return encontradas


print("=" * 78)
print("  1. COBERTURA ESTATICA  --  ningun camino externo fuera de la lista")
print("=" * 78)

nuevas, vistas = [], 0
for ruta in sorted((RAIZ / "nucleo").rglob("*.py")):
    for funcion, llamada in _llamadas_externas(ruta):
        vistas += 1
        clave = f"{ruta.relative_to(RAIZ).as_posix()}::{funcion}"
        if clave not in PERMITIDAS:
            nuevas.append(f"{clave}  ({llamada})")

afirmar(not nuevas,
        f"las {vistas} llamadas HTTP de nucleo/ estan todas clasificadas",
        "" if not nuevas else "SIN CLASIFICAR:\n           - "
                              + "\n           - ".join(nuevas))

sobrantes = sorted(PERMITIDAS - {
    f"{r.relative_to(RAIZ).as_posix()}::{f}"
    for r in (RAIZ / "nucleo").rglob("*.py") for f, _ in _llamadas_externas(r)})
afirmar(not sobrantes,
        "la lista permitida no tiene entradas muertas",
        "" if not sobrantes else "ya no existen: " + ", ".join(sobrantes))


# =============================================================================
#  2. BYPASS DINAMICO
# =============================================================================
print("")
print("=" * 78)
print("  2. BYPASS  --  el interruptor DETENIDO, y diez intentos de saltarlo")
print("=" * 78)

salidas: list[str] = []


class _RespuestaFalsa:
    ok = True
    status_code = 200
    text = "{}"

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True, "id_ticket": "FALSO", "created": True}


class _RequestsFalso:
    """Cuenta lo que HABRIA salido. Nada viaja por la red."""

    def _anotar(self, metodo, url, **kw):
        salidas.append(f"{metodo} {url}")
        return _RespuestaFalsa()

    def get(self, url, **kw):
        return self._anotar("GET", url, **kw)

    def request(self, metodo, url, **kw):
        return self._anotar(metodo, url, **kw)

    def post(self, url, **kw):
        return self._anotar("POST", url, **kw)


ejecutor_http.requests = _RequestsFalso()

#  Las credenciales salen de la base y esta prueba corre sin base. Se sustituyen
#  DESPUES de la frontera: _exigir_frontera() corre antes que headers_de(), asi
#  que los bloqueos se miden igual.
ejecutor_http.headers_de = lambda herramienta, tenant=None: {}

#  El interruptor: DETENIDO siempre. Se sustituye la LECTURA, no el veredicto:
#  asi corre el codigo real de interruptor.py, que es parte de lo que se prueba.
interruptor.persistencia.estado_autonomia = lambda t: {"estado": "detenido",
                                                       "actor": "prueba",
                                                       "motivo": "prueba 10.14A"}
interruptor.persistencia.registrar_auditoria = lambda *a, **k: None


def escritura():
    #  Una escritura COMUN: ni irreversible (solo sale por frontera.critica,
    #  ver tests/test_m06a_gate_critico.py) ni con aprobacion humana (no sale
    #  por la puerta autonoma). Hasta M06-E se tomaba la primera escritura
    #  http del catalogo, y paso a ser cancelar_solicitud_servicio -- que ahora
    #  es irreversible, asi que el control positivo de la puerta humana dejaba
    #  de medir la puerta humana.
    for h in CONFIG.herramientas:
        if (h.tipo == "http" and not getattr(h, "solo_lectura", True)
                and not getattr(h, "irreversible", False)
                and not getattr(h, "aprobacion_humana", False)):
            return h
    raise SystemExit("el catalogo no tiene herramientas http de escritura")


def lectura():
    for h in CONFIG.herramientas:
        if h.tipo == "http" and getattr(h, "solo_lectura", True):
            return h
    raise SystemExit("el catalogo no tiene herramientas http de lectura")


HERR_W, HERR_R = escritura(), lectura()


def intento(nombre, fn, debe_bloquear=True):
    n0 = len(salidas)
    error = ""
    try:
        fn()
    except Exception as e:
        error = f"{type(e).__name__}: {str(e).splitlines()[0][:70]}"
    salio = len(salidas) - n0
    ok = (salio == 0) if debe_bloquear else (salio > 0)
    afirmar(ok, f"{nombre}  (llamadas externas: {salio})", error)


print("")
print("  --- A a G: por cada modulo que podria llegar al ejecutor ---")
intento("A · ejecutor directo, sin permiso",
        lambda: ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT))
intento("B · motor._ejecutar_tool (camino del modelo)",
        lambda: motor._ejecutar_tool(HERR_W, None, {"servicio": "1"}, TENANT,
                                     CONFIG.variables_tenant))
intento("C · motor.ejecutar_para_servicio (ruta /interno)",
        lambda: motor.ejecutar_para_servicio(CONFIG, HERR_W, {"servicio": "1"}))
intento("D · operativo.responder sin actor (autonoma)",
        lambda: operativo._ejecutar(CONFIG, TENANT, "responde_ticket_operativo",
                                    "1", "texto", ""))
intento("E · operativo.cerrar (cierra el ticket del ISP)",
        lambda: operativo.cerrar(CONFIG, TENANT, "1", "texto"))
intento("F · operativo.cerrar_caso_crm (cierra el caso del CRM)",
        lambda: operativo.cerrar_caso_crm(CONFIG, TENANT, "1"))
intento("G · idempotencia.ejecutar como puerta suelta",
        lambda: idempotencia.ejecutar(
            TENANT, HERR_W.nombre, {"a": 1}, "origen-suelto",
            lambda: ejecutor_http.ejecutar(HERR_W, {"a": 1}, TENANT)))

print("")
print("  --- H a J: el tenant ---")
intento("H · tenant=None",
        lambda: motor._ejecutar_tool(HERR_W, None, {"servicio": "1"}, None,
                                     CONFIG.variables_tenant))
intento("I · tenant=''",
        lambda: motor._ejecutar_tool(HERR_W, None, {"servicio": "1"}, "",
                                     CONFIG.variables_tenant))
intento("J · tenant inexistente",
        lambda: motor._ejecutar_tool(HERR_W, None, {"servicio": "1"},
                                     "isp-que-no-existe", CONFIG.variables_tenant))

def _humana_ok():
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra",
                         evidencia="propuesta:123"):
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


def _sin_actor():
    with frontera.humana(TENANT, HERR_W.nombre, actor="", evidencia="x"):
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


def _sin_evidencia():
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra", evidencia=""):
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


def _tenant_cruzado():
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra", evidencia="x"):
        ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, "otra_isp")


def _fuera_del_bloque():
    with frontera.humana(TENANT, HERR_W.nombre, actor="mayra", evidencia="x"):
        pass
    ejecutor_http.ejecutar(HERR_W, {"servicio": "1"}, TENANT)


print("")
print("  --- lo que NO debe bloquearse ---")
intento("las LECTURAS siguen pasando con el interruptor tirado",
        lambda: ejecutor_http.ejecutar(HERR_R, {}, TENANT),
        debe_bloquear=False)

print("")
print("  --- la puerta humana ---")
intento("la puerta humana SI deja pasar (actor + evidencia)",
        _humana_ok, debe_bloquear=False)
intento("la puerta humana SIN actor no abre", _sin_actor)
intento("la puerta humana SIN evidencia no abre", _sin_evidencia)

print("")
print("  --- el permiso de una empresa no sirve para la de al lado ---")
intento("un permiso de 'rapilink' no autoriza a escribir en 'otra_isp'",
        _tenant_cruzado)

print("")
print("  --- el permiso no sobrevive al bloque ---")
intento("al salir del 'with', el permiso ya no vale", _fuera_del_bloque)

print("")
print("=" * 78)
if fallos:
    print(f"  {len(fallos)} FALLO(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  [OK] No queda ningun camino de salida sin frontera.")
print(f"       llamadas externas REALES: 0  (requests sustituido; "
      f"{len(salidas)} habrian salido, todas legitimas)")
print("=" * 78)
