# -*- coding: utf-8 -*-
"""
================================================================================
 CABLE TRAMPA: NINGUNA ESCRITURA HTTP NUEVA APARECE SIN DECLARARSE
================================================================================

    py -3.13 tests/test_escrituras_fuera_del_catalogo.py

Corre sin base, sin credenciales y sin red: mide el arbol sintactico del repo.

POR QUE EXISTE
--------------
Las guardas de M06 recorren 'CONFIG.herramientas', asi que **no pueden ver** una
escritura hecha con 'requests' directo. Por eso 'cli/aplicar_sn_onu.py' pudo
hacer PATCH contra la ficha de un cliente en WispHub de PRODUCCION durante
semanas sin que ninguna guarda dijera nada: no era una herramienta, era
requests.patch, y por lo tanto no lo veia el interruptor de autonomia, ni el
techo, ni quedaba en 'operaciones_externas'.

Se mitigo ese caso (exige '--aplicar', y hay una prueba que lo mide). Lo que
quedaba abierto es LA CLASE: nada impide que manana aparezca otro. Esta prueba
lo impide.

QUE AFIRMA
----------
Que el conjunto de escrituras HTTP directas es EXACTAMENTE el declarado aca
abajo, con su clasificacion y su motivo. Si aparece una nueva, se pone roja. Si
desaparece una declarada, tambien -- un inventario que se queda viejo deja de
ser un inventario.

Se mide por AST y no por grep: un grep cuenta lo que hay dentro de un docstring,
y con ese error este repositorio ya se dio un falso negativo el 26/09/2026.

COMO SE AGREGA UNA ENTRADA, SI HACE FALTA
-----------------------------------------
Agregarla aca NO es un tramite: es la decision de que ese camino puede escribir
en un tercero sin pasar por la frontera. Si la respuesta honesta es "deberia ser
una herramienta del catalogo", el arreglo es moverla, no declararla.
================================================================================
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []
afirmaciones = 0


def comprobar(condicion: bool, que: str) -> None:
    global afirmaciones
    afirmaciones += 1
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


#  El ejecutor del catalogo es el camino CORRECTO y por eso no cuenta: es el que
#  exige un permiso vigente de la frontera antes de salir (el ultimo metro).
EXCEPTUADO = "nucleo/herramientas/http.py"

VERBOS_DE_ESCRITURA = {"post", "put", "patch", "delete", "request"}
CLIENTES_HTTP = {"requests", "httpx", "session", "sesion"}

#  'urlopen' no tiene verbo: manda POST en cuanto le pasan 'data'. Se cuenta
#  siempre, porque distinguirlo exigiria seguir el argumento.
ABRIDORES = {"urlopen"}

#  Constructores que devuelven un cliente HTTP guardado en un nombre
#  cualquiera. Sin esto, 'mi_http = requests.Session()' y despues
#  'mi_http.post(...)' pasaba invisible -- las dos mutaciones que la quinta
#  auditoria logro colar.
CONSTRUCTORES = {("requests", "Session"), ("httpx", "Client"),
                 ("httpx", "AsyncClient")}

#  Fuera de alcance A PROPOSITO, y conviene decir por que en vez de dejarlo
#  implicito: 'django-crm/' es la plataforma vendorizada (BottleCRM), no el
#  motor. Sus escrituras HTTP son de Django y de sus tareas, viven bajo otro
#  ciclo de vida y no pasan ni deben pasar por la frontera de Dexter.
#  Incluirlas volveria este inventario ruido, y un inventario ruidoso se
#  saltea. Si algun dia el motor llama a una de ellas, el barrido de
#  'nucleo/' lo va a ver del lado del motor.
FUERA_DE_ALCANCE = ("django-crm",)


#  EL INVENTARIO. Clave: archivo. Valor: lista de (verbo, clase, motivo).
#  Las clases y lo que significan:
#
#    entrega        el transporte hacia el cliente final, no la mutacion del
#                   sistema de un tercero. Gobernado por los invariantes de
#                   entrega (CLAUDE.md 12), no por la frontera.
#    propio         habla con Dexter mismo. No hay tercero.
#    laboratorio    bypass DECLARADO y con compuerta, solo para el equipo de
#                   pruebas.
#    hueco          escribe en un tercero sin pasar por la frontera. Mitigado,
#                   pero la clase sigue abierta como decision de producto.
DECLARADAS: dict[str, list[tuple[str, str, str]]] = {
    "nucleo/canales/whatsapp.py": [
        ("post", "entrega",
         "manda el mensaje al cliente por la Graph API de Meta. La "
         "idempotencia vive en el llamador: asistente.whatsapp_salidas se "
         "reserva ANTES del POST"),
        ("post", "entrega",
         "sube un archivo a Meta y recibe el id temporal del medio"),
    ],
    "cli/aplicar_sn_onu.py": [
        ("patch", "hueco",
         "PATCH a la ficha del cliente en WispHub de produccion, sobre "
         "'sn_onu'. Mitigado: exige --aplicar, y lo mide "
         "tests/test_aplicar_sn_onu_no_escribe_por_defecto.py. La CLASE sigue "
         "abierta en SPEC/objetivos/puerta-humana-y-los-ocho-pasos.md"),
    ],
    "cli/bateria_tv.py": [
        ("post", "propio",
         "POST a /chat del propio motor: Dexter hablandose a si mismo para "
         "medir 23 conversaciones de punta a punta"),
    ],
    "cli/prueba_reinicio_con_ping.py": [
        ("post", "laboratorio",
         "ping a WispHub. Exige --confirmo-reinicio-de-laboratorio y que el "
         "serial sea el de la ONU de laboratorio"),
        ("post", "laboratorio",
         "reboot a SmartOLT, con la misma compuerta. Tiene efecto fisico, y "
         "por eso la compuerta nombra el serial"),
    ],
    "soporte_wisphub.py": [
        ("post", "prototipo",
         "EL PROTOTIPO VIEJO de un solo tenant (PRD 11). Hace POST al endpoint "
         "de PAGO -- 'registrar_pago', una de las cinco irreversibles de "
         "CLAUDE.md 5 -- y no pasa por la frontera. Nada de nucleo/ ni de cli/ "
         "lo importa: solo lo citan cuatro docstrings, verificado. Entro al "
         "inventario el 27/09/2026 porque la quinta auditoria midio que este "
         "archivo quedaba fuera del barrido mientras la prueba afirmaba 'el "
         "repo'. NO es una excepcion bendecida: es una que alguien tendria que "
         "decidir si se borra"),
    ],
}


def _archivos_a_revisar():
    """`nucleo/`, `cli/` y los .py de primer nivel del repo."""
    for carpeta in ("nucleo", "cli"):
        yield from sorted((RAIZ / carpeta).rglob("*.py"))
    #  Los de la raiz entran desde el 27/09/2026: el inventario decia "el repo"
    #  y medía dos carpetas, y afuera habia una escritura real -- un PAGO.
    yield from sorted(RAIZ.glob("*.py"))


def _nombres_de_cliente_http(arbol) -> set[str]:
    """
    Los nombres locales que guardan un cliente HTTP.

    'mi_http = requests.Session()' hace que 'mi_http.post(...)' sea una
    escritura, y sin esto era invisible.
    """
    nombres: set[str] = set()
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
            continue
        f = n.value.func
        if not isinstance(f, ast.Attribute) or not isinstance(f.value, ast.Name):
            continue
        if (f.value.id, f.attr) not in CONSTRUCTORES:
            continue
        for destino in n.targets:
            if isinstance(destino, ast.Name):
                nombres.add(destino.id)
            elif isinstance(destino, ast.Attribute):
                nombres.add(destino.attr)
    return nombres


def _encontradas() -> dict[str, list[tuple[int, str]]]:
    """Todas las escrituras HTTP directas del arbol, por AST."""
    fuera: dict[str, list[tuple[int, str]]] = {}
    for archivo in _archivos_a_revisar():
        relativo = archivo.relative_to(RAIZ).as_posix()
        if relativo == EXCEPTUADO or relativo.startswith(FUERA_DE_ALCANCE):
            continue
        try:
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        except SyntaxError:
            #  Un archivo que no parsea es un problema, pero no de esta
            #  prueba. Se dice y se sigue -- nunca se ignora en silencio.
            print(f"  [aviso] {relativo} no parsea; NO se pudo revisar")
            continue
        locales = _nombres_de_cliente_http(arbol)
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)):
                continue
            if n.func.attr in ABRIDORES:
                fuera.setdefault(relativo, []).append((n.lineno, n.func.attr))
                continue
            if n.func.attr not in VERBOS_DE_ESCRITURA:
                continue
            valor = n.func.value
            base = (valor.id if isinstance(valor, ast.Name)
                    else valor.attr if isinstance(valor, ast.Attribute)
                    else "")
            if base in CLIENTES_HTTP or base in locales:
                fuera.setdefault(relativo, []).append((n.lineno, n.func.attr))
    return fuera


print()
print("=" * 78)
print("  NINGUNA ESCRITURA HTTP NUEVA APARECE SIN DECLARARSE")
print("=" * 78)
print()

_hallado = _encontradas()

#  1. Nada sin declarar.
for archivo, sitios in sorted(_hallado.items()):
    esperados = DECLARADAS.get(archivo)
    comprobar(esperados is not None,
              f"{archivo} escribe por HTTP y ESTA declarado "
              f"(lineas {[l for l, _ in sitios]})")
    if esperados is None:
        continue
    comprobar(len(sitios) == len(esperados),
              f"{archivo}: {len(sitios)} escritura(s) y "
              f"{len(esperados)} declarada(s)")
    verbos_hallados = sorted(v for _, v in sitios)
    verbos_declarados = sorted(v for v, _c, _m in esperados)
    comprobar(verbos_hallados == verbos_declarados,
              f"{archivo}: los verbos coinciden "
              f"({verbos_hallados} vs {verbos_declarados})")

#  2. Nada declarado que ya no exista: un inventario viejo no es un inventario.
for archivo in sorted(DECLARADAS):
    comprobar(archivo in _hallado,
              f"{archivo} sigue existiendo y escribiendo (si se movio al "
              f"catalogo, sacalo del inventario)")

#  3. El ejecutor del catalogo SI exige permiso de la frontera. Sin esto, el
#     'exceptuado' de arriba seria un agujero en vez de una excepcion.
_http = (RAIZ / "nucleo" / "herramientas" / "http.py").read_text(encoding="utf-8")
_arbol_http = ast.parse(_http)
_exige = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "exigir"
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "frontera"
             for n in ast.walk(_arbol_http))
comprobar(_exige,
          "el ejecutor del catalogo llama a frontera.exigir, asi que "
          "exceptuarlo es correcto")

#  4. Y que el 'hueco' declarado sea UNO solo. Si algun dia son dos, la
#     decision de producto dejo de poder postergarse.
_huecos = [(a, m) for a, lista in DECLARADAS.items()
           for _v, c, m in lista if c == "hueco"]
comprobar(len(_huecos) == 1,
          f"hay UN solo camino declarado como hueco (hay {len(_huecos)}: "
          f"{[a for a, _ in _huecos]})")

print()
print("=" * 78)
print(f"  archivos con escritura HTTP directa  {len(_hallado)}")
print(f"  afirmaciones                         {afirmaciones}")
print(f"  fallos                               {len(fallos)}")
if fallos:
    print()
    print(f"[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    print()
    print("  Si agregaste una escritura HTTP nueva: declarala en DECLARADAS con")
    print("  su clase y su motivo. Y antes de hacerlo, preguntate si no deberia")
    print("  ser una herramienta del catalogo -- que es el camino que SI pasa")
    print("  por la frontera.")
    print("=" * 78)
    print()
    sys.exit(1)
print()
print("[OK] El inventario de escrituras fuera del catalogo esta completo y al dia.")
print("=" * 78)
print()
