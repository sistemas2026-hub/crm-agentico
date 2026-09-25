# -*- coding: utf-8 -*-
"""
================================================================================
 AUTOR, ORIGEN Y REINTENTO  --  sin base: rutas del motor y el inventario de escritores
================================================================================

    py -3.13 tests/test_autor_y_reintento.py

Fase B2.2 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md (D2, D15, D16, I4). La parte que
necesita PostgreSQL (CHECK, ON CONFLICT, "no inserta") esta en
tests/test_origen_mensajes_base.py.

  1. INVENTARIO. Todo 'insert into asistente.messages' del repo vive en uno de
     los tres escritores conocidos y nombra la columna 'origen'. Un escritor
     nuevo que la omita hace fallar esta suite, no aparece en produccion como
     filas sin procedencia.
  2. Las cuatro rutas de personas (texto, media, plantilla, nota) rechazan
     con 400 un mensaje sin autor o con id invalido, SIN llamar a la base.
  3. Reintento con la misma clave: si el mensaje ya existe y no fallo, no se
     vuelve a enviar, ni a copiar al ticket, ni a meter en el historial. Si
     fallo, se entrega UNA vez mas.
  4. Plantilla en una conversacion que no es de WhatsApp: 400 sin envio.
  5. registrar_mensaje sin 'origen' falla por firma; con un origen que no
     corresponde al rol, falla antes de abrir conexion.
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
from nucleo.persistencia import db                                  # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


AUTOR = {"autor": "Ana Perez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}

print("=" * 74)
print(" AUTOR, ORIGEN Y REINTENTO")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. inventario: todo INSERT en messages nombra 'origen' ==")
ESCRITORES = {"registrar_mensaje", "agregar_mensaje_humano", "agregar_nota_interna"}
encontrados: list[tuple[str, str, bool]] = []
for ruta in sorted(list((RAIZ / "nucleo").rglob("*.py")) + list((RAIZ / "cli").rglob("*.py"))
                   + list((RAIZ / "django-crm" / "backend").rglob("*.py"))):
    if "__pycache__" in ruta.parts:
        continue
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        continue
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.FunctionDef):
            continue
        for sub in ast.walk(nodo):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                    and "insert into asistente.messages" in " ".join(sub.value.lower().split()):
                encontrados.append((f"{ruta.relative_to(RAIZ)}::{nodo.name}", sub.value,
                                    "origen" in sub.value))
comprobar({f.split("::")[1] for f, _s, _o in encontrados} == ESCRITORES,
          f"los escritores son exactamente los tres conocidos "
          f"({sorted({f for f, _s, _o in encontrados})})")
for donde, _sql, tiene in encontrados:
    comprobar(tiene, f"{donde} inserta 'origen'")

# ---------------------------------------------------------------------------
print("\n== 5. registrar_mensaje: origen obligatorio y coherente con el rol ==")
abrio = []
real_sesion = db.sesion
db.sesion = lambda *a, **k: abrio.append(1) or (_ for _ in ()).throw(AssertionError("no deberia conectar"))
try:
    try:
        db.registrar_mensaje("t", "api", "u", "r", "user", "hola")
        comprobar(False, "sin origen deberia fallar")
    except TypeError:
        comprobar(True, "sin 'origen': TypeError por firma")
    for rol, origen in (("user", "ia"), ("assistant", "cliente"), ("nota", "ia"),
                        ("user", "robot"), ("assistant", None), ("assistant", "humano")):
        try:
            db.registrar_mensaje("t", "api", "u", "r", rol, "x", origen=origen)
            comprobar(False, f"rol={rol} origen={origen} deberia fallar")
        except ValueError:
            comprobar(True, f"rol={rol!r} origen={origen!r}: ValueError")
        except Exception as e:
            comprobar(False, f"rol={rol!r} origen={origen!r}: esperaba ValueError, fue {type(e).__name__}")
    comprobar(abrio == [], "ninguno de esos casos abrio una conexion")
    for nombre, uid in (("", AUTOR["autor_usuario_id"]), ("Ana", ""), ("Ana", "no-es-uuid"), (None, None)):
        try:
            db.agregar_mensaje_humano("t", "c", "x", nombre, autor_usuario_id=uid)
            comprobar(False, f"autor={nombre!r} id={uid!r} deberia fallar")
        except db.AutorInvalido:
            comprobar(True, f"agregar_mensaje_humano autor={nombre!r} id={uid!r}: AutorInvalido")
        except Exception as e:
            comprobar(False, f"agregar_mensaje_humano autor={nombre!r} id={uid!r}: esperaba "
                             f"AutorInvalido, fue {type(e).__name__} (llego a la base)")
        try:
            db.agregar_nota_interna("t", "c", "x", nombre, autor_usuario_id=uid)
            comprobar(False, f"nota autor={nombre!r} deberia fallar")
        except db.AutorInvalido:
            comprobar(True, f"agregar_nota_interna autor={nombre!r} id={uid!r}: AutorInvalido")
        except Exception as e:
            comprobar(False, f"agregar_nota_interna autor={nombre!r} id={uid!r}: esperaba "
                             f"AutorInvalido, fue {type(e).__name__} (llego a la base)")
    comprobar(abrio == [], "tampoco abrieron conexion los mensajes sin autor")
finally:
    db.sesion = real_sesion


# ---------------------------------------------------------------------------
class Mundo:
    """Sustituye persistencia, WhatsApp, operativo y config; anota todo."""

    def __init__(self, destino=None, error_agregar=None):
        self.llamadas: list[tuple] = []
        self.destino = destino
        self.error_agregar = error_agregar
        self._orig = {}

    def __enter__(self):
        p = api.persistencia
        def agregar(*a, **k):
            self.llamadas.append(("agregar_mensaje_humano", a, k))
            if self.error_agregar:
                raise self.error_agregar
            return self.destino
        reemplazos = {
            (p, "agregar_mensaje_humano"): agregar,
            # B3.3: la guarda de control; esta suite mide autor y reintento con
            # la conversacion en manos de una persona.
            (p, "control_efectivo_de"): lambda *a, **k: "humano",
            (p, "agregar_nota_interna"): lambda *a, **k: self.llamadas.append(("nota", a, k)) or "nota-1",
            (p, "marcar_envio"): lambda *a, **k: self.llamadas.append(("marcar_envio", a, k)),
            (p, "guardar_media"): lambda *a, **k: self.llamadas.append(("guardar_media", a, k)),
            (api.transiciones, "devolver_a_ia"): lambda *a, **k: self.llamadas.append(("devolver", a, k)),
            (api.whatsapp, "enviar_texto"): lambda *a, **k: self.llamadas.append(("enviar_texto", a, k)) or "wamid.1",
            (api.whatsapp, "enviar_media"): lambda *a, **k: self.llamadas.append(("enviar_media", a, k)) or "wamid.2",
            (api.whatsapp, "enviar_plantilla_aprobada"): lambda *a, **k: self.llamadas.append(("enviar_plantilla", a, k)) or "wamid.3",
            (api.whatsapp, "plantillas_aprobadas"): lambda *a, **k: [
                {"nombre": "bienvenida", "estado": "APPROVED", "variables": 0, "cuerpo": "Hola"}],
            (api.whatsapp, "_validar_media"): lambda *a, **k: None,
            (api.media, "preparar"): lambda contenido, tipo, mime: (contenido, mime),
            (api.operativo, "responder"): lambda *a, **k: self.llamadas.append(("ticket", a, k)) or True,
            (api, "_config_de"): lambda t: object(),
        }
        for (m, n), f in reemplazos.items():
            self._orig[(m, n)] = getattr(m, n)
            setattr(m, n, f)
        self._token = api._TOKEN_SERVICIO
        api._TOKEN_SERVICIO = None
        return self

    def __exit__(self, *e):
        for (m, n), f in self._orig.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = self._token
        return False

    def nombres(self):
        return [c[0] for c in self.llamadas]


cliente = api.app.test_client()
TEL = "573000000000"

# ---------------------------------------------------------------------------
print("\n== 2. sin autor valido: 400 y la base no se toca ==")
for nombre, cuerpo_autor in (("sin autor", {}),
                             ("autor sin id", {"autor": "Ana"}),
                             ("id invalido", {"autor": "Ana", "autor_usuario_id": "123"}),
                             ("nombre vacio", {"autor": "  ", "autor_usuario_id": AUTOR["autor_usuario_id"]})):
    with Mundo(destino={"canal": "whatsapp"}) as m:
        r1 = cliente.post("/conversaciones/c1/mensajes", json={"tenant": "t", "mensaje": "hola", **cuerpo_autor})
        r2 = cliente.post("/conversaciones/c1/nota", json={"tenant": "t", "mensaje": "hola", **cuerpo_autor})
        r3 = cliente.post("/conversaciones/c1/plantilla", json={"tenant": "t", "plantilla": "bienvenida", **cuerpo_autor})
        r4 = cliente.post("/conversaciones/c1/humano/media",
                          data={"tenant": "t", "tipo": "image", **cuerpo_autor,
                                "archivo": (io.BytesIO(b"\x89PNG"), "a.png", "image/png")},
                          content_type="multipart/form-data")
    comprobar([r.status_code for r in (r1, r2, r3, r4)] == [400, 400, 400, 400] and m.llamadas == [],
              f"{nombre}: texto, nota, plantilla y media -> 400, cero llamadas "
              f"(fue {[r.status_code for r in (r1, r2, r3, r4)]}, {m.nombres()})")

# ---------------------------------------------------------------------------
print("\n== 3. reintento con la misma clave ==")
CLAVE = "11111111-2222-3333-4444-555555555555"
base_destino = {"canal": "whatsapp", "usuario_externo": TEL, "ticket_operativo": "T-9",
                "mensaje_id": "m-1"}

for estado in ("enviado", "pendiente", "entregado", "leido"):
    api._sesiones.clear()
    api._sesiones[("t", "whatsapp", TEL)] = {"historial": [], "escalada": True}
    with Mundo(destino={**base_destino, "existente": True, "estado_entrega": estado}) as m:
        r = cliente.post("/conversaciones/c1/mensajes",
                         json={"tenant": "t", "mensaje": "hola", "clave_idempotencia": CLAVE, **AUTOR})
    comprobar(r.status_code == 200 and r.get_json().get("ya_existia")
              and m.nombres() == ["agregar_mensaje_humano"]
              and api._sesiones[("t", "whatsapp", TEL)]["historial"] == [],
              f"ya existia en '{estado}': 200, sin envio, sin copia al ticket, sin historial "
              f"(fue {r.status_code}, {m.nombres()})")

api._sesiones.clear()
api._sesiones[("t", "whatsapp", TEL)] = {"historial": [], "escalada": True}
with Mundo(destino={**base_destino, "existente": True, "estado_entrega": "fallido"}) as m:
    r = cliente.post("/conversaciones/c1/mensajes",
                     json={"tenant": "t", "mensaje": "hola", "clave_idempotencia": CLAVE, **AUTOR})
comprobar(r.status_code == 201 and m.nombres().count("enviar_texto") == 1
          and "ticket" not in m.nombres()
          and api._sesiones[("t", "whatsapp", TEL)]["historial"] == [],
          f"ya existia y FALLO: se entrega una vez mas, sin otra copia al ticket ni al historial "
          f"(fue {r.status_code}, {m.nombres()})")

api._sesiones.clear()
api._sesiones[("t", "whatsapp", TEL)] = {"historial": [], "escalada": True}
with Mundo(destino={**base_destino, "existente": False, "estado_entrega": "pendiente"}) as m:
    r = cliente.post("/conversaciones/c1/mensajes",
                     json={"tenant": "t", "mensaje": "hola", "clave_idempotencia": CLAVE, **AUTOR})
llamada = next((c for c in m.llamadas if c[0] == "agregar_mensaje_humano"), None)
hist = api._sesiones[("t", "whatsapp", TEL)]["historial"]
comprobar(r.status_code == 201 and m.nombres().count("enviar_texto") == 1 and "ticket" in m.nombres()
          and len(hist) == 1 and hist[0]["content"] == "(Ana Perez, del equipo) hola",
          f"mensaje nuevo: se entrega, se copia al ticket y entra al historial firmado "
          f"(fue {r.status_code}, {m.nombres()}, {hist})")
comprobar(llamada is not None and llamada[2].get("autor_usuario_id") == AUTOR["autor_usuario_id"]
          and llamada[2].get("clave_idempotencia") == CLAVE,
          "el autor y la clave llegan a persistencia tal como los mando el proxy")

for ruta, datos, envio in (
        ("/conversaciones/c1/plantilla", {"json": {"tenant": "t", "plantilla": "bienvenida",
                                                   "clave_idempotencia": CLAVE, **AUTOR}}, "enviar_plantilla"),
        ("/conversaciones/c1/humano/media", {"data": {"tenant": "t", "tipo": "image", "clave_idempotencia": CLAVE, **AUTOR,
                                                      "archivo": (io.BytesIO(b"\x89PNG"), "a.png", "image/png")},
                                             "content_type": "multipart/form-data"}, "enviar_media")):
    with Mundo(destino={**base_destino, "existente": True, "estado_entrega": "enviado"}) as m:
        r = cliente.post(ruta, **datos)
    comprobar(r.status_code == 200 and envio not in m.nombres() and "guardar_media" not in m.nombres(),
              f"{ruta.rsplit('/', 1)[1]}: reintento de algo ya enviado no reenvia "
              f"(fue {r.status_code}, {m.nombres()})")

# ---------------------------------------------------------------------------
print("\n== 4. plantilla en conversacion que no es de WhatsApp ==")
with Mundo(error_agregar=db.CanalNoAdmite("es api")) as m:
    r = cliente.post("/conversaciones/c1/plantilla",
                     json={"tenant": "t", "plantilla": "bienvenida", **AUTOR})
comprobar(r.status_code == 400 and "enviar_plantilla" not in m.nombres() and "marcar_envio" not in m.nombres(),
          f"400 sin envio ni marca (fue {r.status_code}, {m.nombres()})")
comprobar(m.llamadas and m.llamadas[0][2].get("solo_canal") == "whatsapp",
          "la plantilla le pide a persistencia validar el canal ANTES de insertar")

api._sesiones.clear()
if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] Sin autor no se guarda, reintentar no duplica, y todo INSERT lleva origen.")
