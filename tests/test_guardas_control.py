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

# ---------------------------------------------------------------------------
print("\n== 5. B3.3b: /intervenir ==")
from nucleo.relevo import transiciones as T                         # noqa: E402

llamadas_meta = []
for nombre_m in ("enviar_texto", "enviar_media", "enviar_plantilla_aprobada", "plantillas_aprobadas"):
    setattr(api.whatsapp, nombre_m, (lambda n: lambda *a, **k: llamadas_meta.append(n))(nombre_m))
visto = {}


def intervenir_falso(resultado):
    def f(tenant, conv, **k):
        visto.update(k)
        return resultado
    return f


real_intervenir = T.intervenir
api._TOKEN_SERVICIO = None
try:
    r = cliente.post("/conversaciones/c1/intervenir", json={"tenant": "t"})
    comprobar(r.status_code == 400, f"sin autor: 400 ({r.status_code})")
    for resultado, codigo, que in (
            (T.Resultado(True, True, 3, "ev"), 200, "aplicada"),
            (T.Resultado(False, True, 3, "ev", "reintento"), 200, "reintento de la misma operacion"),
            (T.Resultado(False, True, 3, None, "sin_cambio"), 409, "ya no es de la IA (otra persona o escalada)"),
            (T.Resultado(False, False, None, None, "no_existe"), 404, "no existe")):
        T.intervenir = intervenir_falso(resultado)
        r = cliente.post("/conversaciones/c1/intervenir",
                         json={"tenant": "t", "clave_operacion": "op-9", "motivo": "respuesta mala", **AUTOR})
        comprobar(r.status_code == codigo, f"{que}: {codigo} ({r.status_code})")
    comprobar(visto.get("operador_id") == AUTOR["autor_usuario_id"] and visto.get("operador_nombre") == AUTOR["autor"]
              and visto.get("clave") == "op-9", "el actor y la clave llegan a la transicion")
    comprobar(llamadas_meta == [], "intervenir no le manda nada al cliente (cero llamadas a Meta)")
finally:
    T.intervenir = real_intervenir

print("\n== 6. B3.3b: la compuerta falla cerrado ==")
modelo = []
reemplazos = {
    (api.persistencia, "control_de_conversacion_abierta"):
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("base caida")),
    (api.persistencia, "conversacion_vencida"): lambda *a, **k: None,
    (api.persistencia, "estado_de_conversacion_abierta"): lambda *a, **k: None,
    (api.persistencia, "resumen_anterior"): lambda *a, **k: None,
    (api.persistencia, "identificar_cliente"): lambda *a, **k: None,
    (api.motor, "responder"): lambda *a, **k: modelo.append(1) or ("hola", [], []),
    (api, "_resolver_verificacion_pendiente"): lambda *a, **k: None,
}
orig = {k: getattr(*k) for k in reemplazos}
for (m, n), f in reemplazos.items():
    setattr(m, n, f)
api._sesiones.clear()
try:
    from nucleo.config import cargar_config                         # noqa: E402
    try:
        salida = api.atender_turno(cargar_config(RAIZ / "tenants" / "rapilink.config.yaml"), "rapilink",
                                   "cliente_final", "573000000000", "hola", "whatsapp-simulado")
    except (Exception, SystemExit) as e:
        # Si la compuerta no corta, el turno sigue de largo hasta otra lectura
        # de la base (que aca no existe): eso tambien es fallar abierto.
        salida = {"siguio_de_largo": type(e).__name__}
    comprobar(not modelo and salida.get("respuesta") == "" and salida.get("control_desconocido"),
              f"no se pudo leer el control: el modelo NO corre y no se responde nada ({salida})")
finally:
    for (m, n), f in orig.items():
        setattr(m, n, f)
    api._sesiones.clear()

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] Con la IA atendiendo, nada de una persona le llega al cliente.")
