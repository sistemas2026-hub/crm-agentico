# -*- coding: utf-8 -*-
"""
================================================================================
 LAS GUARDAS DEL RELEVO  --  con la IA atendiendo, nada humano le llega al cliente
================================================================================

    py -3.13 tests/test_guardas_control.py          (sin base)

B3.3 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md (X25, S36). La parte contra PostgreSQL
(control efectivo real, cero filas) esta en tests/test_relevo_transiciones_base.py,
seccion 7.

  1. INVENTARIO: toda ruta de api.py que llama a agregar_mensaje_humano llama
     ANTES a _exigir_control_humano. Una ruta nueva que se la saltee hace fallar
     esta suite.
  2. Con control efectivo 'ia': texto, media y plantilla -> 409, y NADA mas:
     ni una fila, ni Meta (tampoco la consulta de plantillas), ni la config.
     Tambien entrando por /casos/<id>/mensajes (la pantalla de tickets).
  3. Con 'humano' siguen de largo; conversacion inexistente -> 404; si no se
     puede leer el control -> 503 sin enviar nada (falla cerrado).
  4. La nota interna NO se bloquea: no sale del equipo.
================================================================================
"""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


AUTOR = {"autor": "Ana Perez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}

print("=" * 74)
print(" LAS GUARDAS DEL RELEVO")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. inventario ==")
arbol = ast.parse((RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8"))
rutas_que_escriben = {}
for nodo in arbol.body:
    if not isinstance(nodo, ast.FunctionDef):
        continue
    llamadas = [(n.lineno, n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", ""))
                for n in ast.walk(nodo) if isinstance(n, ast.Call)]
    escribe = [l for l, nombre in llamadas if nombre == "agregar_mensaje_humano"]
    if escribe:
        guarda = [l for l, nombre in llamadas if nombre == "_exigir_control_humano"]
        rutas_que_escriben[nodo.name] = bool(guarda) and min(guarda) < min(escribe)
comprobar(set(rutas_que_escriben) == {"conversaciones_enviar_plantilla", "conversaciones_responder_humano",
                                      "conversaciones_enviar_media"},
          f"las rutas que escriben mensajes humanos son las tres conocidas ({sorted(rutas_que_escriben)})")
for ruta, ok in sorted(rutas_que_escriben.items()):
    comprobar(ok, f"{ruta} llama a la guarda ANTES de escribir")


# ---------------------------------------------------------------------------
class Mundo:
    def __init__(self, control="ia", error_control=None):
        self.control, self.error_control = control, error_control
        self.llamadas: list[str] = []

    def _grabar(self, nombre, devuelve=None):
        def f(*a, **k):
            self.llamadas.append(nombre)
            return devuelve
        return f

    def __enter__(self):
        p = api.persistencia

        def control_de(tenant, conv):
            self.llamadas.append("control_efectivo_de")
            if self.error_control:
                raise self.error_control
            return self.control
        destino = {"canal": "whatsapp-simulado", "usuario_externo": "573000000000",
                   "ticket_operativo": None, "mensaje_id": "m-1", "existente": False, "estado_entrega": None}
        self.r = {
            (p, "control_efectivo_de"): control_de,
            (p, "agregar_mensaje_humano"): self._grabar("agregar_mensaje_humano", destino),
            (p, "agregar_nota_interna"): self._grabar("agregar_nota_interna", "nota-1"),
            (p, "marcar_envio"): self._grabar("marcar_envio", True),
            (p, "guardar_media"): self._grabar("guardar_media"),
            (p, "conversacion_de_caso"): lambda tenant, caso: {"id": "c1"},
            (api.whatsapp, "plantillas_aprobadas"): self._grabar("plantillas_aprobadas",
                [{"nombre": "bienvenida", "estado": "APPROVED", "variables": 0, "cuerpo": "Hola"}]),
            (api.whatsapp, "enviar_texto"): self._grabar("enviar_texto", "w"),
            (api.whatsapp, "enviar_media"): self._grabar("enviar_media", "w"),
            (api.whatsapp, "enviar_plantilla_aprobada"): self._grabar("enviar_plantilla", "w"),
            (api.whatsapp, "_validar_media"): lambda *a, **k: None,
            (api.media, "preparar"): lambda contenido, tipo, mime: (contenido, mime),
            (api, "_config_de"): self._grabar("_config_de", object()),
        }
        self.orig = {k: getattr(*k) for k in self.r}
        for (m, n), f in self.r.items():
            setattr(m, n, f)
        self.token = api._TOKEN_SERVICIO
        api._TOKEN_SERVICIO = None
        return self

    def __exit__(self, *e):
        for (m, n), f in self.orig.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = self.token
        return False


cliente = api.app.test_client()


def enviar_todo():
    return {
        "texto": cliente.post("/conversaciones/c1/mensajes", json={"tenant": "t", "mensaje": "hola", **AUTOR}),
        "media": cliente.post("/conversaciones/c1/humano/media",
                              data={"tenant": "t", "tipo": "image", **AUTOR,
                                    "archivo": (io.BytesIO(b"\x89PNG"), "a.png", "image/png")},
                              content_type="multipart/form-data"),
        "plantilla": cliente.post("/conversaciones/c1/plantilla",
                                  json={"tenant": "t", "plantilla": "bienvenida", **AUTOR}),
        "ticket": cliente.post("/casos/caso-1/mensajes", json={"tenant": "t", "mensaje": "hola", **AUTOR}),
    }


# ---------------------------------------------------------------------------
print("\n== 2. control efectivo 'ia': 409 y nada mas ==")
with Mundo(control="ia") as m:
    rs = enviar_todo()
for nombre, r in rs.items():
    d = r.get_json() or {}
    comprobar(r.status_code == 409 and d.get("codigo") == "control_ia",
              f"{nombre}: 409 control_ia ({r.status_code} {d.get('codigo')})")
comprobar(set(m.llamadas) == {"control_efectivo_de"},
          f"ni filas, ni Meta, ni consulta de plantillas, ni config ({sorted(set(m.llamadas))})")

print("\n== 3. humano sigue; inexistente 404; control ilegible 503 ==")
with Mundo(control="humano") as m:
    rs = enviar_todo()
comprobar(all(r.status_code in (200, 201) for r in rs.values()) and m.llamadas.count("agregar_mensaje_humano") == 4,
          f"con control humano las cuatro entradas guardan ({[r.status_code for r in rs.values()]})")
with Mundo(control=None) as m:
    rs = enviar_todo()
comprobar(all(r.status_code == 404 for r in rs.values()) and "agregar_mensaje_humano" not in m.llamadas,
          f"conversacion inexistente: 404 sin escribir ({[r.status_code for r in rs.values()]})")
with Mundo(error_control=RuntimeError("base caida")) as m:
    rs = enviar_todo()
comprobar(all(r.status_code == 503 for r in rs.values()) and set(m.llamadas) == {"control_efectivo_de"},
          f"no se pudo leer el control: 503 y nada enviado ({[r.status_code for r in rs.values()]})")

print("\n== 4. la nota interna no se bloquea ==")
with Mundo(control="ia") as m:
    r = cliente.post("/conversaciones/c1/nota", json={"tenant": "t", "mensaje": "revisar OLT", **AUTOR})
comprobar(r.status_code == 201 and "agregar_nota_interna" in m.llamadas and "control_efectivo_de" not in m.llamadas,
          f"nota con la IA atendiendo: 201 sin consultar el control ({r.status_code})")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] Con la IA atendiendo, nada de una persona le llega al cliente.")
