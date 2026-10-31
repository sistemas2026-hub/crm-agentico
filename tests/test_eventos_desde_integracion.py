# -*- coding: utf-8 -*-
"""
================================================================================
 eventos_desde()  --  la FUNCION, no la consulta que copia una prueba
================================================================================

Por que existe, y lo que costo
-------------------------------
'tests/test_eventos_cursor_con_base.py' prueba la GARANTIA del cursor: que no
pierde eventos y que dos empresas no se ven. Lo hace COPIANDO la consulta, y lo
dice en su propio comentario -- "se copia aqui en vez de importar db.py porque
ese modulo abre su propia sesion contra la base de verdad".

Esa decision dejo un hueco del tamaño de la funcion entera. 'eventos_desde'
estaba escrita leyendo las filas POR INDICE --'cur.fetchone()[0]',
'for (a, b, c) in filas', 'filas[-1][0]'-- y 'sesion()' abre la conexion con
'row_factory=dict_row'. Con dict_row una fila es un diccionario: '[0]' levanta
KeyError.

O sea que la funcion NUNCA habia funcionado, y la prueba de E1 estaba en verde.
Se descubrio el 31/10/2026, la primera vez que el motor sirvio '/eventos' de
verdad contra una base migrada: HTTP 500.

Y habia un segundo fallo escondido detras del primero: '_retraso_del_flujo'
hacia 'fila[0]' dentro de un 'try/except Exception: return None' puesto para el
caso sin permiso sobre 'pg_stat_activity'. El KeyError caia ahi, asi que la
funcion devolvia None SIEMPRE y la pantalla leia "no se pudo medir el retraso"
sin que nada fallara. Un fallo silencioso escondido detras de un fallo
silencioso previsto.

Lo que esta prueba afirma es lo unico que aquella no podia: que la funcion
CORRE. Es la leccion de PARSEA != IMPORTA != FUNCIONA, aplicada al unico sitio
donde faltaba.

Como se corre
-------------
Necesita una base con el esquema 'asistente' COMPLETO (migrado por el ledger) y
un tenant cargado. Se salta sola si no la hay, con exit 0 y diciendolo.

    set DBHOST=127.0.0.1 & set DBPORT=55500 & set DBNAME=crm_db
    set DBUSER=postgres & set DBPASSWORD=... & set TENANT_DE_PRUEBA=rapilink
    py -3.13 tests/test_eventos_desde_integracion.py

No escribe nada: solo lee. No toca produccion.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TENANT = os.environ.get("TENANT_DE_PRUEBA", "")
if not os.environ.get("DBHOST") or not TENANT:
    print("[saltada] Hacen falta DBHOST... y TENANT_DE_PRUEBA apuntando a una")
    print("          base con el esquema 'asistente' migrado. NO se comprobo nada.")
    raise SystemExit(0)

_HOST = os.environ.get("DBHOST", "")
if _HOST not in ("localhost", "127.0.0.1", "::1", "host.docker.internal"):
    print(f"[ABORTA] DBHOST='{_HOST}' no es local.")
    raise SystemExit(1)

from nucleo.persistencia import db                           # noqa: E402

fallos: list[str] = []


def comprobar(ok: bool, que: str) -> None:
    print(f"  [{'OK' if ok else 'FALLA'}]  {que}")
    if not ok:
        fallos.append(que)


def main() -> int:
    print("\n[F1] la funcion CORRE sin cursor y devuelve la frontera")
    try:
        inicio = db.eventos_desde(TENANT, None)
    except Exception as e:                                   # noqa: BLE001
        comprobar(False, f"eventos_desde(None) levanto {type(e).__name__}: {e}")
        return 1
    comprobar(isinstance(inicio, dict), "devuelve un diccionario")
    comprobar(inicio.get("eventos") == [],
              "sin cursor NO entrega historico (es el arranque)")
    siguiente = inicio.get("siguiente")
    comprobar(isinstance(siguiente, list) and len(siguiente) == 2,
              "la frontera viene como (tx, id)")
    comprobar(str(siguiente[0]).isdigit(),
              f"y el tx es un numero ({siguiente[0]})")

    print("\n[F2] la funcion CORRE con cursor y entrega eventos")
    try:
        desde_cero = db.eventos_desde(TENANT, ("1", "00000000-0000-0000-0000-000000000000"))
    except Exception as e:                                   # noqa: BLE001
        comprobar(False, f"eventos_desde(cursor) levanto {type(e).__name__}: {e}")
        return 1
    eventos = desde_cero.get("eventos", [])
    comprobar(isinstance(eventos, list), "devuelve una lista de eventos")

    if eventos:
        e = eventos[0]
        #  Las claves que la pantalla consume. Con el acceso por indice, estas
        #  salian corridas o directamente no salian.
        for clave in ("id", "en", "agente", "tipo", "herramienta", "datos"):
            comprobar(clave in e, f"cada evento trae '{clave}'")
        comprobar(e["tipo"] in ("consulta", "accion", "herramienta_fallida",
                                "escalada"),
                  f"el tipo es del vocabulario conocido ('{e['tipo']}')")
        comprobar(isinstance(e["datos"], dict),
                  "'datos' es la lista blanca, no los parametros crudos")
        comprobar(all(c in db.CLAVES_PUBLICAS for c in e["datos"]),
                  "y solo trae claves de la lista blanca")
        comprobar(desde_cero["siguiente"][0] != "1",
                  "el cursor AVANZA tras entregar")
    else:
        print("  [aviso] la base no tiene eventos: F2 comprobo que corre, no que entrega")

    print("\n[F3] el retraso del flujo se MIDE, no se devuelve None a ciegas")
    #  Es el fallo que estaba escondido: `fila[0]` dentro de un except que lo
    #  tragaba. Con la base quieta el valor correcto ES None, asi que lo que se
    #  afirma es que la clave existe y que el tipo es el esperado -- no que
    #  haya un numero.
    comprobar("retraso_s" in inicio, "la respuesta trae 'retraso_s'")
    comprobar(inicio["retraso_s"] is None or isinstance(inicio["retraso_s"], float),
              f"y es None o un numero ({inicio['retraso_s']!r})")

    print("\n[F4] un cursor imposible no rompe")
    try:
        lejos = db.eventos_desde(TENANT, ("999999999", "ffffffff-ffff-4fff-8fff-ffffffffffff"))
        comprobar(lejos.get("eventos") == [], "un cursor del futuro entrega cero, no revienta")
    except Exception as e:                                   # noqa: BLE001
        comprobar(False, f"cursor imposible levanto {type(e).__name__}")

    print("\n" + "=" * 70)
    if fallos:
        print(f"[FALLA] {len(fallos)} comprobacion(es):")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print("[OK] eventos_desde() corre de verdad, no solo su consulta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
