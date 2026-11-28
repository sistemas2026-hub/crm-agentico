# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE LAS DOS HERRAMIENTAS DEL PRECIO
================================================================================

Que cubre y por que
-------------------
El precio de un plan hace falta para repartir el trabajo del dia (un plan alto
pesa). No sale del listado del proveedor --medido el 07/10/2026:
`/api/plan-internet/` devuelve 50 planes con id, nombre y tipo, ningun
precio-- sino del detalle, uno por uno. Son DOS llamadas distintas, y cual
herramienta hace cada una varia por empresa.

Hasta el 07/10/2026 esa eleccion solo se podia hacer editando
`tenants/<slug>.config.yaml` y cargandolo entero. El costo fue medido, no
hipotetico: el boton "Actualizar precios" devolvia 400 en produccion, y la
unica salida disponible era un `cargar_config` completo que de paso habria
apagado la vision (`vision_habilitada` false en el repo, true en la base) y
borrado dos cosas creadas desde la interfaz (`areas[ventas]`, toda
`importacion_tickets`). Eso es exactamente lo que CLAUDE.md 3.3 prohibe.

Lo que se verifica aqui es el EFECTO del endpoint, no que el campo exista:

  - sin elegir nada              -> 400 que DICE que falta elegir y OFRECE las
                                    candidatas (un 400 sin eso no le decia a
                                    nadie como salir del paso)
  - con las dos                  -> se GUARDAN antes de usarse, y la
                                    sincronizacion corre con las elegidas
  - con una sola                 -> 400 y no se guarda NADA a medias
  - el catalogo de la pantalla   -> resuelve por la MARCA, y cae al nombre
                                    cuando no hay marca (produccion todavia
                                    no la tiene: resolver solo por marca
                                    dejaria esa pantalla sin catalogo)

No habla con el proveedor ni con la base: `planes_precio.sincronizar` y el
editor se sustituyen, porque lo que se prueba son las decisiones de la ruta.

    py -3.13 tests/test_precios_herramientas.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                   # noqa: E402
from nucleo.config import editor                                 # noqa: E402
from nucleo.config.schema import Herramienta                     # noqa: E402
from nucleo.herramientas import planes_precio                    # noqa: E402

TENANT = "tenant-de-prueba"

fallos: list[str] = []


def check(descripcion: str, condicion: bool) -> None:
    print(f"  [{'ok' if condicion else 'FALLA'}]   {descripcion}")
    if not condicion:
        fallos.append(descripcion)


class _ConfigFalsa:
    """
    Lo minimo que mira la ruta. Se arma a mano y no desde el YAML de un
    tenant: la prueba no debe cambiar de resultado porque alguien marque o
    desmarque una herramienta en el archivo de una empresa.
    """

    def __init__(self, marcas=None, nombres=("trae_planes", "trae_el_detalle",
                                             "otra_cosa")):
        marcas = marcas or {}
        self.herramientas = [
            Herramienta(nombre=n, tipo="http",
                        descripcion=f"Descripcion de {n}.",
                        base_url="https://ejemplo", endpoint=f"/{n}/",
                        metodo="GET", roles_permitidos=["un_rol"],
                        sincroniza_precio_plan=marcas.get(n, ""))
            for n in nombres
        ]
        self.variables_tenant = {}
        self.planes_venta = []
        self.localidades = []
        self.localidades_actualizado_en = None
        self.precios_de_planes = []
        self.precios_actualizado_en = None


def _preparar(config, guardadas: list, sincronizadas: list) -> None:
    """Sustituye lo que sale del proceso: la base y el proveedor."""
    api._config_de = lambda t: config
    api.olvidar_config = lambda t=None: None

    def _guardar(tenant, listado, detalle):
        guardadas.append((tenant, listado, detalle))
        return _ConfigFalsa({listado: "listado", detalle: "detalle"})

    editor.guardar_marcas_precio = _guardar
    api.editor.guardar_marcas_precio = _guardar
    api.editor.guardar_precios = lambda t, filas: _ConfigFalsa()

    def _sinc(listado, detalle, tenant, variables):
        sincronizadas.append((listado.nombre, detalle.nombre))
        return {"planes": {}, "truncado": False, "error": False}

    planes_precio.sincronizar = _sinc


def prueba_sin_elegir_dice_que_falta_elegir() -> None:
    print("\nsin elegir nada")
    guardadas, sincronizadas = [], []
    _preparar(_ConfigFalsa(), guardadas, sincronizadas)
    c = api.app.test_client()
    r = c.post("/configuracion/precios/sincronizar", json={"tenant": TENANT})

    check("responde 400", r.status_code == 400)
    cuerpo = r.get_json() or {}
    check("dice que falta ELEGIR, no que fallo el proveedor",
          cuerpo.get("falta_elegir") is True)
    nombres = [h.get("nombre") for h in (cuerpo.get("herramientas") or [])]
    check("ofrece las candidatas para que la pantalla las pueda pedir",
          nombres == ["trae_planes", "trae_el_detalle", "otra_cosa"])
    check("y no sincronizo nada con el proveedor", sincronizadas == [])
    check("ni guardo ninguna marca", guardadas == [])


def prueba_elegir_las_dos_las_guarda_y_sincroniza() -> None:
    print("\neligiendo las dos")
    guardadas, sincronizadas = [], []
    _preparar(_ConfigFalsa(), guardadas, sincronizadas)
    c = api.app.test_client()
    r = c.post("/configuracion/precios/sincronizar",
               json={"tenant": TENANT, "listado": "trae_planes",
                     "detalle": "trae_el_detalle"})

    check("responde 200", r.status_code == 200)
    check("GUARDO la eleccion (sin esto habria que volver a elegirla cada vez)",
          guardadas == [(TENANT, "trae_planes", "trae_el_detalle")])
    check("y sincronizo con las dos elegidas, en su papel",
          sincronizadas == [("trae_planes", "trae_el_detalle")])


def prueba_una_sola_no_deja_la_config_a_medias() -> None:
    """
    El caso que importa es con la configuracion YA marcada.

    Sin configurar, media eleccion igual termina en 400 por el paso
    siguiente, asi que una prueba sobre un tenant virgen pasa sola y no
    prueba nada -- medido: la mutacion que borra este rechazo SOBREVIVIO a
    esa version de esta prueba.

    Con las marcas ya puestas, en cambio, media eleccion se tragaria sin
    decir nada: sincronizaria con las VIEJAS e informaria exito, y quien
    pidio el cambio creeria que se aplico.
    """
    print("\neligiendo una sola")
    for cuerpo in ({"tenant": TENANT, "listado": "otra_cosa"},
                   {"tenant": TENANT, "detalle": "otra_cosa"}):
        guardadas, sincronizadas = [], []
        _preparar(_ConfigFalsa({"trae_planes": "listado",
                                "trae_el_detalle": "detalle"}),
                  guardadas, sincronizadas)
        c = api.app.test_client()
        r = c.post("/configuracion/precios/sincronizar", json=cuerpo)
        cual = "listado" if "listado" in cuerpo else "detalle"
        check(f"cambiar solo el {cual} responde 400", r.status_code == 400)
        check(f"cambiar solo el {cual} no guarda nada a medias",
              guardadas == [])
        check(f"cambiar solo el {cual} NO sincroniza con las marcas viejas "
              f"informando exito", sincronizadas == [])


def prueba_ya_marcadas_sincronizan_sin_volver_a_elegir() -> None:
    print("\nya marcadas en la configuracion")
    guardadas, sincronizadas = [], []
    config = _ConfigFalsa({"trae_planes": "listado",
                           "trae_el_detalle": "detalle"})
    _preparar(config, guardadas, sincronizadas)
    c = api.app.test_client()
    r = c.post("/configuracion/precios/sincronizar", json={"tenant": TENANT})

    check("responde 200 sin que nadie elija de nuevo", r.status_code == 200)
    check("no reescribe la configuracion por una sincronizacion normal",
          guardadas == [])
    check("y usa las que ya estaban marcadas",
          sincronizadas == [("trae_planes", "trae_el_detalle")])


def prueba_el_catalogo_resuelve_por_la_marca() -> None:
    """
    El nombre 'consultar_planes' estuvo FIJO en el motor hasta el
    07/10/2026 -- un dato del proveedor de un tenant dentro de nucleo/. El
    fallback al nombre se queda a proposito: produccion todavia no tiene la
    marca, y resolver solo por marca dejaria esta pantalla sin catalogo.
    """
    print("\nel catalogo de la pantalla")
    pedidas: list[str] = []

    def _ejecutar(h, args, tenant, variables):
        pedidas.append(h.nombre)
        return {"results": []}

    api.ejecutor_http.ejecutar = _ejecutar
    api.olvidar_config = lambda t=None: None
    c = api.app.test_client()

    api._config_de = lambda t: _ConfigFalsa({"trae_planes": "listado"})
    r = c.get(f"/configuracion/planes-venta?tenant={TENANT}&catalogo=1")
    check("usa la herramienta MARCADA como listado, no un nombre fijo",
          pedidas == ["trae_planes"])
    check("y no reporta error de catalogo",
          (r.get_json() or {}).get("error_catalogo") is None)

    pedidas.clear()
    api._config_de = lambda t: _ConfigFalsa(
        nombres=("consultar_planes", "otra", "mas"))
    c.get(f"/configuracion/planes-venta?tenant={TENANT}&catalogo=1")
    check("sin marca cae al nombre historico, que es lo que corre hoy en "
          "produccion", pedidas == ["consultar_planes"])

    pedidas.clear()
    api._config_de = lambda t: _ConfigFalsa(nombres=("ninguna_sirve",))
    r = c.get(f"/configuracion/planes-venta?tenant={TENANT}&catalogo=1")
    check("sin marca y sin el nombre historico, lo DICE en vez de callarse",
          "listado de planes" in ((r.get_json() or {}).get("error_catalogo") or ""))
    check("y no le pega al proveedor con una herramienta cualquiera",
          pedidas == [])


def prueba_la_pantalla_recibe_las_marcas_y_los_precios() -> None:
    print("\nlo que la pantalla necesita para ofrecer la eleccion")
    api.ejecutor_http.ejecutar = lambda *a, **k: {"results": []}
    api._config_de = lambda t: _ConfigFalsa({"trae_planes": "listado",
                                             "trae_el_detalle": "detalle"})
    c = api.app.test_client()
    cuerpo = c.get(f"/configuracion/planes-venta?tenant={TENANT}").get_json() or {}

    check("devuelve las marcas actuales",
          cuerpo.get("marcas_precio") == {"listado": "trae_planes",
                                          "detalle": "trae_el_detalle"})
    check("y las candidatas con su descripcion",
          [h["nombre"] for h in cuerpo.get("herramientas", [])]
          == ["trae_planes", "trae_el_detalle", "otra_cosa"])
    # La pantalla ya leia 'precios_de_planes' y este endpoint no lo devolvia:
    # mostraba "todavia no se sincronizo ninguno" con el catalogo cargado.
    check("devuelve los precios guardados, que la pantalla ya leia",
          "precios_de_planes" in cuerpo)
    check("y cuando se actualizaron", "precios_actualizado_en" in cuerpo)


if __name__ == "__main__":
    print("=" * 70)
    print(" LAS DOS HERRAMIENTAS DEL PRECIO  --  elegidas en la pantalla")
    print("=" * 70)

    prueba_sin_elegir_dice_que_falta_elegir()
    prueba_elegir_las_dos_las_guarda_y_sincroniza()
    prueba_una_sola_no_deja_la_config_a_medias()
    prueba_ya_marcadas_sincronizan_sin_volver_a_elegir()
    prueba_el_catalogo_resuelve_por_la_marca()
    prueba_la_pantalla_recibe_las_marcas_y_los_precios()

    print("\n" + "=" * 70)
    if fallos:
        print(f" {len(fallos)} FALLA(S):")
        for f in fallos:
            print(f"   - {f}")
        sys.exit(1)
    print(" Todo en orden.")
