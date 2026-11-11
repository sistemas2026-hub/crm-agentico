# -*- coding: utf-8 -*-
"""
================================================================================
 LA APERTURA DE UNA CONVERSACION: OCHO LECTURAS EN UNA
================================================================================

    py -3.13 tests/test_apertura_conversacion.py

Corre sin base y sin red, como tests/test_respuestas_rapidas_y_busqueda.py:
se sustituyen '_config_de' y las ocho funciones de persistencia que alimentan
la pantalla de una conversacion. Las rutas, el enriquecimiento del hilo
(ventana, control efectivo, equipo, respuestas rapidas) y la cuenta del
diagnostico son los REALES.

POR QUE EXISTE  (11/11/2026)
----------------------------
Abrir una conversacion disparaba ocho lecturas en paralelo contra un motor de
un proceso y 16 hilos: ocho hilos y ocho sesiones por apertura. Ahora hay una
ruta, GET /conversaciones/<id>/apertura, que las junta. Lo que se afirma, sobre
el EFECTO:

  - cada clave de /apertura es EL MISMO cuerpo que la ruta individual (si
    alguien cambia una ruta y la otra no, se nota aca);
  - cada funcion de persistencia se llama UNA vez por apertura: juntar no
    puede ser duplicar;
  - un panel que falla llega en null y el resto llega igual, con una linea de
    log de texto fijo y sin el error;
  - una conversacion que no existe es 404 CON codigo; la ruta que el motor no
    conoce es 404 SIN codigo (lo que distingue, desde la pantalla, "no existe"
    de "motor viejo"); y si falla el hilo, 500.
================================================================================
"""

from __future__ import annotations

import contextlib
import io
import sys
from collections import Counter
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
CID = "c-apertura-1"
REAL = sorted(canales.REALES)[0]
CONFIG = editor._validar(TENANT, documento())

llamadas: Counter = Counter()
fallan: set[str] = set()
DETALLE_SECRETO = "ROUTE_ERROR_cedula_1234567"


def _doble(nombre, valor):
    def f(tenant, cid, *args, **kwargs):
        llamadas[nombre] += 1
        if nombre in fallan:
            raise ValueError(DETALLE_SECRETO)
        return valor(cid) if callable(valor) else valor
    return f


def _mensajes(cid):
    if cid == "no-existe":
        return {"conversacion": None, "mensajes": []}
    return {"conversacion": {"id": cid, "canal": REAL, "usuario_externo": "573001",
                             "relevo_version": 1, "control": "humano",
                             "escalada_a_humano": True, "necesita_atencion_humana": True,
                             "ultimo_mensaje_cliente": None, "etiquetas_del_equipo": ["x"],
                             "datos_sesion": {"areas_visitadas": ["soporte"]}},
            "mensajes": [{"id": "m1", "rol": "user"}]}


def _hilo(cid):
    return {"canal": REAL, "ancla": cid, "tramos": [{"id": "t0"}], "hay_anteriores": True,
            "antes": "t0", "mas_reciente_id": cid, "abiertas": [], "posteriores": [],
            "total_tramos": 2}


hilo_kwargs: list[dict] = []


def _hilo_del_numero(tenant, cid, **kwargs):
    hilo_kwargs.append(kwargs)
    return _doble("hilo_del_numero", _hilo)(tenant, cid)


DOBLES = {
    "mensajes_de": _doble("mensajes_de", _mensajes),
    "reincidencia_de": _doble("reincidencia_de", {"veces": 2, "dias": 7}),
    "hilo_del_numero": _hilo_del_numero,
    "herramientas_de": _doble("herramientas_de", [{"nombre": "a", "exito": True},
                                                  {"nombre": "b", "exito": False, "es_bloqueo": True},
                                                  {"nombre": "c", "exito": False}]),
    "sincronizaciones_de": _doble("sincronizaciones_de", [{"id": "s1", "estado": "pendiente"}]),
    "acciones_de_conversacion": _doble("acciones_de_conversacion", [{"id": "a1", "estado": "vencida"}]),
    "acciones_sobre_el_equipo": _doble("acciones_sobre_el_equipo", [{"id": "e1", "veredicto": "ok"}]),
    "eventos_de_relevo": _doble("eventos_de_relevo", [{"tipo": "escalada", "nuevo_estado": "humano"}]),
}
INDIVIDUALES = {
    "mensajes": f"/conversaciones/{CID}/mensajes",
    "hilo": f"/conversaciones/{CID}/hilo",
    "herramientas": f"/conversaciones/{CID}/herramientas",
    "relevo": f"/conversaciones/{CID}/relevo",
    "equipo": f"/conversaciones/{CID}/equipo",
    "sincronizaciones": f"/conversaciones/{CID}/sincronizaciones",
    "acciones": f"/conversaciones/{CID}/acciones",
    "casos": "/manual/casos",
}

reales = {n: getattr(api.persistencia, n) for n in DOBLES}
config_real = api._config_de
api._config_de = lambda _t: CONFIG
for n, f in DOBLES.items():
    setattr(api.persistencia, n, f)

try:
    print()
    print("=" * 78)
    print("  LA APERTURA DE UNA CONVERSACION")
    print("=" * 78)

    with api.app.test_client() as c:
        print("\n-- cada clave es el cuerpo de la ruta individual --")
        individuales = {}
        for clave, ruta in INDIVIDUALES.items():
            r = c.get(f"{ruta}?tenant={TENANT}")
            comprobar(r.status_code == 200, f"GET {ruta} sigue respondiendo 200 ({r.status_code})")
            individuales[clave] = r.get_json()

        llamadas.clear()
        hilo_kwargs.clear()
        r = c.get(f"/conversaciones/{CID}/apertura?tenant={TENANT}")
        apertura = r.get_json() or {}
        comprobar(r.status_code == 200, f"GET /apertura responde 200 ({r.status_code})")
        comprobar(apertura.get("apertura") is True, "y se declara como apertura")
        comprobar(set(apertura) == {"apertura", *INDIVIDUALES},
                  f"trae exactamente las ocho claves ({sorted(apertura)})")
        for clave in INDIVIDUALES:
            comprobar(apertura.get(clave) == individuales[clave],
                      f"'{clave}' es byte a byte el cuerpo de su ruta")
        # Lo que distingue un cuerpo enriquecido de uno crudo: si /apertura
        # devolviera lo que da la base sin pasar por la misma funcion, estas
        # tres cosas faltarian o serian distintas.
        conv = (apertura.get("mensajes") or {}).get("conversacion") or {}
        comprobar(conv.get("control_efectivo") == "humano" and "datos_sesion" not in conv
                  and conv.get("etiquetas_del_equipo") == [] and "ventana_whatsapp" in conv,
                  "el hilo viene ENRIQUECIDO como en /mensajes: control, sin datos_sesion, etiquetas vigentes, ventana")
        comprobar((apertura.get("herramientas") or {}).get("diagnostico")
                  == {"normales": 1, "bloqueadas": 1, "errores": 1},
                  "el diagnostico de herramientas viene contado")
        comprobar((apertura.get("hilo") or {}).get("agrupa") is True, "el chat trae 'agrupa'")
        comprobar(hilo_kwargs == [{"antes": None, "limite": api.persistencia.TRAMOS_POR_PAGINA}],
                  f"el chat se pide con los valores por defecto ({hilo_kwargs})")

        print("\n-- juntar no es duplicar --")
        esperadas = {n: 1 for n in DOBLES}
        comprobar(dict(llamadas) == esperadas,
                  f"cada funcion de persistencia se llamo UNA vez en la apertura ({dict(llamadas)})")

        print("\n-- un panel que falla no tumba el resto --")
        for panel, funcion in (("herramientas", "herramientas_de"), ("hilo", "hilo_del_numero"),
                               ("relevo", "eventos_de_relevo")):
            fallan.add(funcion)
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                r = c.get(f"/conversaciones/{CID}/apertura?tenant={TENANT}")
            fallan.discard(funcion)
            cuerpo = r.get_json() or {}
            otros = [k for k in INDIVIDUALES if k != panel]
            comprobar(r.status_code == 200 and cuerpo.get(panel) is None,
                      f"con '{funcion}' roto: 200 y '{panel}' en null ({r.status_code})")
            comprobar(all(cuerpo.get(k) == individuales[k] for k in otros),
                      "y los otros siete llegan iguales")
            log = salida.getvalue()
            comprobar("fallo un panel de la apertura" in log and f"panel={panel}" in log,
                      "queda una linea de log que nombra el panel")
            comprobar(DETALLE_SECRETO not in log and DETALLE_SECRETO not in r.get_data(as_text=True),
                      "y ni el log ni la respuesta llevan el texto del error")

        print("\n-- sin el hilo no hay pantalla --")
        fallan.add("mensajes_de")
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.get(f"/conversaciones/{CID}/apertura?tenant={TENANT}")
        fallan.discard("mensajes_de")
        comprobar(r.status_code == 500, f"si falla 'mensajes': 500 como /mensajes ({r.status_code})")

        print("\n-- los dos 404 --")
        r = c.get(f"/conversaciones/no-existe/apertura?tenant={TENANT}")
        cuerpo = r.get_json() or {}
        comprobar(r.status_code == 404 and cuerpo.get("codigo") == "conversacion_inexistente",
                  f"una conversacion que no existe: 404 con codigo ({r.status_code}, {cuerpo.get('codigo')})")
        r = c.get(f"/conversaciones/{CID}/ruta-que-no-existe?tenant={TENANT}")
        comprobar(r.status_code == 404 and not (r.get_json(silent=True) or {}).get("codigo"),
                  f"una ruta que el motor no conoce: 404 SIN codigo ({r.status_code})")
        r = c.get(f"/conversaciones/{CID}/apertura")
        comprobar(r.status_code == 400, f"sin tenant: 400 ({r.status_code})")
finally:
    api._config_de = config_real
    for n, f in reales.items():
        setattr(api.persistencia, n, f)

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
