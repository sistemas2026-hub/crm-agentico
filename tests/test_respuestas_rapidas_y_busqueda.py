# -*- coding: utf-8 -*-
"""
================================================================================
 RESPUESTAS RAPIDAS Y BUSQUEDA EN MENSAJES: LO QUE VIAJA POR HTTP
================================================================================

    py -3.13 tests/test_respuestas_rapidas_y_busqueda.py

Corre sin base y sin red, como tests/test_rotulos_bandeja.py: se sustituyen
'_config_de', la persistencia y la transaccion del editor. El mutador y la
validacion que corren en el PUT son los REALES. La consulta SQL de la busqueda
se prueba contra Postgres en tests/test_busqueda_mensajes_base.py.

POR QUE EXISTE  (11/11/2026)
----------------------------
Las dos funciones tienen saltos que una prueba del editor o de la base no ve:

  - Las respuestas rapidas se guardan por un endpoint y se LEEN por otro --
    viajan con el hilo de la conversacion (GET .../mensajes), que es lo que
    abre el compositor. Si ese segundo salto se cae, la pantalla de Ajustes
    las muestra y el «/» no abre nada.
  - La busqueda recibe texto de cliente. Lo que se protege: el rango de 'q'
    (3-100), que el termino NO aparezca en el log ni cuando la consulta falla
    con un error que lo cita, y que cada resultado llegue marcado como
    operativo o de prueba con el mismo criterio que la cola.
================================================================================
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.canales import canal as canales                         # noqa: E402
from nucleo.config import cargar_config, editor                     # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def documento() -> dict:
    """El volcado del primer tenants/*.config.yaml. No se nombra ninguno."""
    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    return cargar_config(yamls[0]).model_dump(mode="json")


TENANT = "prueba"
estado = {"doc": documento()}
estado["doc"].setdefault("conversaciones", {})["respuestas_rapidas"] = []


def _config_de(_tenant):
    return editor._validar(TENANT, estado["doc"])


def _editar_sin_transaccion(tenant, mutar):
    """editor._editar sin la base: muta el documento y lo valida. Si la
    validacion falla, el documento NO queda mutado -- igual que el rollback."""
    import copy
    doc = copy.deepcopy(estado["doc"])
    mutar(doc)
    config = editor._validar(tenant, doc)
    estado["doc"] = doc
    return config


TERMINO = "Calle 45 # 12-30 Soledad"
llamadas: list[str] = []


def _buscar(tenant, q):
    llamadas.append(q)
    return [
        {"mensaje_id": "m1", "conversation_id": "c1", "rol": "user", "creado_en": "2026-11-11T10:00:00Z",
         "fragmento": "vivo en " + q, "nombre_cliente": "Ana", "usuario_externo": "573001",
         "estado": "abierta", "canal": sorted(canales.REALES)[0], "es_nota": False},
        {"mensaje_id": "m2", "conversation_id": "c2", "rol": "nota", "creado_en": "2026-11-11T09:00:00Z",
         "fragmento": q, "nombre_cliente": None, "usuario_externo": "prueba-1",
         "estado": "cerrada", "canal": "canal_de_prueba_que_no_es_real", "es_nota": True},
    ]


def _buscar_que_falla(tenant, q):
    # Un error de base cita el valor que fallo: es justo lo que no puede
    # terminar en el log.
    raise ValueError(f"invalid input near '{q}'")


reales = (api._config_de, editor._editar, api.olvidar_config,
          api.persistencia.mensajes_de, api.persistencia.reincidencia_de,
          api.persistencia.buscar_en_mensajes)
api._config_de = _config_de
editor._editar = _editar_sin_transaccion
api.olvidar_config = lambda tenant: None
api.persistencia.mensajes_de = lambda tenant, cid: {
    "conversacion": {"id": cid, "canal": "simulador", "datos_sesion": {}}, "mensajes": []}
api.persistencia.reincidencia_de = lambda tenant, cid, dias: None

try:
    print()
    print("=" * 78)
    print("  RESPUESTAS RAPIDAS Y BUSQUEDA EN MENSAJES")
    print("=" * 78)

    with api.app.test_client() as c:
        print("\n-- respuestas rapidas --")
        r = c.get(f"/configuracion/bandeja/respuestas-rapidas?tenant={TENANT}")
        comprobar(r.status_code == 200 and (r.get_json() or {}).get("respuestas_rapidas") == [],
                  f"el GET responde con la lista vacia ({r.status_code})")

        r = c.put("/configuracion/bandeja/respuestas-rapidas", json={
            "tenant": TENANT,
            "respuestas_rapidas": [{"atajo": "/Saludo", "texto": "Hola {nombre}, ¿en qué te ayudo?"},
                                   {"atajo": "horario", "texto": "Atendemos de 7 a 19."}]})
        guardadas = (r.get_json() or {}).get("respuestas_rapidas") or []
        comprobar(r.status_code == 200, f"el PUT guarda ({r.status_code})")
        comprobar([x["atajo"] for x in guardadas] == ["saludo", "horario"],
                  "y devuelve lo guardado, con el atajo normalizado")

        r = c.get(f"/conversaciones/c-1/mensajes?tenant={TENANT}")
        viajan = (r.get_json() or {}).get("respuestas_rapidas") or []
        comprobar(r.status_code == 200 and [x["atajo"] for x in viajan] == ["saludo", "horario"],
                  "viajan con el hilo de la conversacion, que es lo que abre el compositor")
        comprobar(viajan and viajan[0]["texto"] == "Hola {nombre}, ¿en qué te ayudo?",
                  "con {nombre} sin resolver: lo resuelve la pantalla, que conoce al cliente")

        r = c.put("/configuracion/bandeja/respuestas-rapidas", json={"tenant": TENANT})
        comprobar(r.status_code == 400 and "lista vacía" in (r.get_json() or {}).get("error", ""),
                  "sin el campo no borra nada: 400 y dice como vaciarla")
        comprobar(len(_config_de(TENANT).conversaciones.respuestas_rapidas) == 2,
                  "y las que habia siguen")

        r = c.put("/configuracion/bandeja/respuestas-rapidas", json={
            "tenant": TENANT, "respuestas_rapidas": [{"atajo": "con espacio", "texto": "x"}]})
        comprobar(r.status_code == 400 and "atajo" in (r.get_json() or {}).get("error", ""),
                  "un atajo invalido vuelve con un mensaje que lo nombra")

        r = c.put("/configuracion/bandeja/respuestas-rapidas",
                  json={"tenant": TENANT, "respuestas_rapidas": []})
        comprobar(r.status_code == 200 and (r.get_json() or {}).get("respuestas_rapidas") == [],
                  "una lista vacia las borra")

        def _config_que_falla(_t):
            raise RuntimeError("sin config")
        api._config_de = _config_que_falla
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.get(f"/conversaciones/c-1/mensajes?tenant={TENANT}")
        api._config_de = _config_de
        comprobar(r.status_code == 200 and (r.get_json() or {}).get("respuestas_rapidas") == [],
                  "sin config el hilo se lee igual, con la lista vacia")

        print("\n-- busqueda en mensajes --")
        api.persistencia.buscar_en_mensajes = _buscar
        for q, que in (("ab", "menos de 3 caracteres"), ("x" * 101, "mas de 100 caracteres"),
                       ("   a  ", "3 caracteres pero con espacios que no cuentan"), ("", "vacia")):
            r = c.get("/conversaciones/buscar", query_string={"tenant": TENANT, "q": q})
            comprobar(r.status_code == 400, f"{que}: 400 ({r.status_code})")
        comprobar(not llamadas, "y ninguna llega a la base")
        r = c.get("/conversaciones/buscar", query_string={"q": "hola"})
        comprobar(r.status_code == 400, "sin tenant: 400")

        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = c.get("/conversaciones/buscar",
                      query_string={"tenant": TENANT, "q": "  " + TERMINO.replace(" ", "   ") + " "})
        datos = r.get_json() or {}
        comprobar(r.status_code == 200, f"una busqueda valida responde ({r.status_code})")
        comprobar(llamadas == [TERMINO], "los espacios se normalizan antes de buscar")
        res = datos.get("resultados") or []
        comprobar([x.get("canal_operativo") for x in res] == [True, False],
                  "cada resultado dice si es de un canal real, con el criterio de la cola")
        comprobar(res and res[1].get("es_nota") is True, "la nota interna llega marcada")
        comprobar(datos.get("tope") == api.persistencia.BUSQUEDA_MENSAJES_TOPE,
                  "y dice cual es el tope, para que la pantalla avise si lo alcanzo")
        comprobar(TERMINO not in salida.getvalue(), "el termino buscado no va al log")

        api.persistencia.buscar_en_mensajes = _buscar_que_falla
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            r = c.get("/conversaciones/buscar", query_string={"tenant": TENANT, "q": TERMINO})
        log = salida.getvalue()
        comprobar(r.status_code == 500 and TERMINO not in (r.get_json() or {}).get("error", ""),
                  "si la consulta falla: 500 sin el termino en la respuesta")
        comprobar("fallo al buscar en mensajes" in log,
                  "el fallo queda en el log (el evento, por tipo)")
        comprobar(TERMINO not in log and "Soledad" not in log,
                  "y ni el termino ni un pedazo de el aparecen, aunque el error lo citaba")
finally:
    (api._config_de, editor._editar, api.olvidar_config,
     api.persistencia.mensajes_de, api.persistencia.reincidencia_de,
     api.persistencia.buscar_en_mensajes) = reales

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
