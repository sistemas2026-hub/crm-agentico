# -*- coding: utf-8 -*-
"""
================================================================================
 /chat Y EL CANAL  --  un canal real no entra por /chat, y el canal separa sesiones
================================================================================

    py -3.13 tests/test_chat_canal.py

LO QUE CIERRA (fase B1 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md)
------------------------------------------------------------
D3. Desde la bandeja, en una conversacion real de WhatsApp que la IA estaba
atendiendo, el texto del operador iba a /chat con canal 'whatsapp'. /chat no
envia nada a Meta: el turno se procesaba igual y quedaba guardado como
mensaje del CLIENTE algo que el cliente no escribio, moviendo la ventana de
24 h y el cierre por plazo.

X2. La clave de la sesion en memoria era (tenant, identificador). El
simulador usa el telefono como identificador, igual que el webhook real: una
prueba con el numero de un cliente compartia historial, rol activo y
escalada con la conversacion real de ese cliente.

QUE SE AFIRMA
-------------
Efectos, no mecanismos: que no se llamo NADA de persistencia, que la memoria
quedo identica, que el turno legitimo si llega, y que dos canales con el
mismo telefono terminan en dos objetos distintos. Una prueba que solo
mirara el codigo de estado pasaria aunque el rechazo ocurriera despues de
escribir -- que es exactamente lo que no se quiere.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.canales import canal as canales                         # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TEL = "573000000000"


class Espia:
    """
    Sustituye TODAS las funciones publicas de persistencia por grabadoras, mas
    la carga de config y atender_turno(). Lo que se llame queda anotado; nada
    llega a una base.
    """

    def __init__(self, atender=None, respuestas=None):
        self.llamadas: list[str] = []
        self.atender_args = None
        self._atender = atender
        self._respuestas = respuestas or {}
        self._orig: dict = {}

    def __enter__(self):
        p = api.persistencia
        for nombre in dir(p):
            f = getattr(p, nombre)
            if nombre.startswith("_") or not callable(f) or isinstance(f, type):
                continue
            # Las validadoras son funciones puras (no tocan la base): se dejan
            # reales, o el espia convertiria un autor valido en None.
            if nombre.startswith("validar_"):
                continue
            if getattr(f, "__module__", None) != p.__name__:
                continue
            self._orig[(p, nombre)] = f
            setattr(p, nombre, self._grabadora(nombre))
        for nombre, f in (("_config_de", lambda t: CONFIG),
                          ("atender_turno", self._atender_turno)):
            self._orig[(api, nombre)] = getattr(api, nombre)
            setattr(api, nombre, f)
        self._orig_token = api._TOKEN_SERVICIO
        api._TOKEN_SERVICIO = None
        return self

    def __exit__(self, *exc):
        for (m, n), f in self._orig.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = self._orig_token
        return False

    def _grabadora(self, nombre):
        def f(*a, **k):
            self.llamadas.append(nombre)
            return self._respuestas.get(nombre)
        return f

    def _atender_turno(self, config, tenant, rol, id_sesion, mensaje, canal, **k):
        self.llamadas.append("atender_turno")
        self.atender_args = {"tenant": tenant, "id_sesion": id_sesion, "canal": canal}
        return {"respuesta": "ok", "verificado": False}


def post_chat(cliente, **campos):
    cuerpo = {"tenant": "rapilink", "rol": "cliente_final",
              "identificador_sesion": TEL, "mensaje": "hola"}
    cuerpo.update(campos)
    cuerpo = {k: v for k, v in cuerpo.items() if v is not _SIN}
    return cliente.post("/chat", json=cuerpo)


_SIN = object()   # "no mandar este campo"


print("=" * 74)
print(" /chat Y EL CANAL")
print("=" * 74)

cliente = api.app.test_client()

# ---------------------------------------------------------------------------
print("\n== B1-T1/T2. /chat con canal real: 403, sin escribir y sin tocar memoria ==")
centinela = {"sesion": "real", "historial": [{"role": "user", "content": "previo"}]}
for variante in ("whatsapp", "WhatsApp", "  whatsapp  ", "WHATSAPP"):
    api._sesiones.clear()
    api._sesiones[("rapilink", "whatsapp", TEL)] = centinela
    antes = dict(api._sesiones)
    with Espia() as e:
        r = post_chat(cliente, canal=variante)
    comprobar(r.status_code == 403, f"canal={variante!r} -> 403 (fue {r.status_code})")
    comprobar(e.llamadas == [],
              f"canal={variante!r}: cero llamadas a persistencia, config o turno "
              f"(hubo {e.llamadas})")
    comprobar(api._sesiones == antes and api._sesiones[("rapilink", "whatsapp", TEL)] is centinela
              and centinela["historial"] == [{"role": "user", "content": "previo"}],
              f"canal={variante!r}: _sesiones identica, sin claves nuevas ni cambios")

# Tambien sin tenant ni mensaje: el canal se decide antes que los demas campos.
with Espia() as e:
    r = cliente.post("/chat", json={"canal": "whatsapp"})
comprobar(r.status_code == 403 and e.llamadas == [],
          "canal real con el resto de campos faltando: 403 igual, antes de validar lo demas")

# ---------------------------------------------------------------------------
print("\n== B1-T7. canal desconocido o vacio: falla cerrado, no cae en un default ==")
for variante in ("sms", "", "   ", "simulado", "whatsapp_simulado", 123, ["whatsapp"]):
    api._sesiones.clear()
    with Espia() as e:
        r = post_chat(cliente, canal=variante)
    comprobar(r.status_code == 400 and e.llamadas == [] and api._sesiones == {},
              f"canal={variante!r} -> 400, cero llamadas, sin sesion "
              f"(fue {r.status_code}, llamadas={e.llamadas})")

# Ausente (o null) SI tiene default, el de siempre: 'api'. No es 'whatsapp'.
for nombre, valor in (("ausente", _SIN), ("null", None)):
    with Espia() as e:
        r = post_chat(cliente, canal=valor)
    comprobar(r.status_code == 200 and e.atender_args and e.atender_args["canal"] == "api",
              f"canal {nombre} -> se atiende como 'api' (fue {r.status_code}, "
              f"{e.atender_args})")

# ---------------------------------------------------------------------------
print("\n== B1-T4. los canales legitimos de /chat siguen llegando al turno ==")
for pedido, esperado in (("whatsapp-simulado", "whatsapp-simulado"),
                         ("Whatsapp-Simulado ", "whatsapp-simulado"),
                         ("api", "api"),
                         ("configuracion-guiada", "configuracion-guiada")):
    with Espia() as e:
        r = post_chat(cliente, canal=pedido)
    comprobar(r.status_code == 200 and e.atender_args["canal"] == esperado,
              f"canal={pedido!r} -> 200 y el turno recibe {esperado!r} normalizado "
              f"(fue {r.status_code}, {e.atender_args})")

# ---------------------------------------------------------------------------
print("\n== B1-T8. normalizacion: una sola funcion, sin alias inventados ==")
comprobar(canales.normalizar_canal(" WhatsApp-Simulado ") == "whatsapp-simulado",
          "mayusculas y espacios alrededor no cambian el canal")
comprobar(canales.clave_sesion("t", "WHATSAPP", TEL) == canales.clave_sesion("t", "whatsapp", TEL),
          "dos escrituras del mismo canal dan una sola clave")
comprobar(canales.clave_sesion("t", "whatsapp", TEL) != canales.clave_sesion("t", "whatsapp-simulado", TEL),
          "real y simulado con el mismo telefono dan claves distintas")
for malo in ("simulado", "wa", "", None):
    try:
        canales.normalizar_canal(malo)
        comprobar(False, f"{malo!r} deberia rechazarse")
    except canales.CanalInvalido:
        comprobar(True, f"{malo!r} se rechaza (no hay alias ni default)")
comprobar(canales.clave_sesion_de_fila("t", "canal-historico-raro", TEL) is None,
          "canal desconocido en una fila de la base: clave None, sin excepcion")
comprobar(canales.ATENDIBLES_POR_CHAT == {"whatsapp-simulado", "api", "configuracion-guiada"},
          "/chat atiende exactamente los tres canales internos")


# ---------------------------------------------------------------------------
print("\n== B1-T3. mismo tenant y telefono: real y simulado son dos sesiones ==")

def turno_real(canal, mensaje="hola"):
    """atender_turno() de verdad, con la base y el modelo sustituidos (mismo
    patron que tests/test_pausa_escalada.py)."""
    p, esc, mot = api.persistencia, api.escalamiento, api.motor
    previo = {"escalada": False, "necesita_atencion_humana": False, "caso_id": None,
              "conversation_id": None, "motivo_escalada": None, "rol_efectivo": None,
              "id_cliente": None, "nombre_cliente": None, "datos_sesion": {}}
    postizos = {
        p: {"estado_de_conversacion_abierta": lambda *a, **k: previo,
            "atendida_por_humano": lambda *a, **k: False,
            "registrar_mensaje": lambda *a, **k: ("conv-1", "msg-1"),
            "conversacion_vencida": lambda *a, **k: None,
            "identificar_cliente": lambda *a, **k: None,
            "resumen_anterior": lambda *a, **k: None,
            "historial_para_el_modelo": lambda *a, **k: [],
            "registrar_turno": lambda *a, **k: None,
            "actualizar_contenido_mensaje": lambda *a, **k: None,
            "caso_de_conversacion": lambda *a, **k: None,
            "ticket_operativo_de": lambda *a, **k: None,
            "cerrar_conversacion": lambda *a, **k: None,
            "guardar_resumen": lambda *a, **k: None,
            "marcar_caso": lambda *a, **k: None,
            "completar_medicion": lambda *a, **k: None,
            "guardar_estado_routing": lambda *a, **k: None,
            "registrar_estado_escalada": lambda *a, **k: None,
            "registrar_marca_tv_desconocida": lambda *a, **k: None},
        esc: {"caso_sigue_abierto": lambda *a, **k: True,
              "evaluar": lambda *a, **k: {}},
        mot: {"responder": lambda *a, **k: ("respuesta del bot", [], [])},
        api: {"_resolver_verificacion_pendiente": lambda *a, **k: None,
              "_hay_verificacion_pendiente": lambda *a, **k: False},
        api.consumo: {"estado_del_gasto": lambda *a, **k:
                      {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0}},
    }
    orig = {(m, n): getattr(m, n) for m, d in postizos.items() for n in d if hasattr(m, n)}
    for m, d in postizos.items():
        for n, f in d.items():
            if hasattr(m, n):
                setattr(m, n, f)
    try:
        return api.atender_turno(CONFIG, "rapilink", "cliente_final", TEL, mensaje, canal)
    finally:
        for (m, n), f in orig.items():
            setattr(m, n, f)


api._sesiones.clear()
turno_real("whatsapp", "soy el cliente real")
turno_real("whatsapp-simulado", "soy una prueba")
real = api._sesiones.get(("rapilink", "whatsapp", TEL))
simulada = api._sesiones.get(("rapilink", "whatsapp-simulado", TEL))
comprobar(real is not None and simulada is not None and real is not simulada,
          "dos objetos de sesion distintos para el mismo telefono")
comprobar(len(api._sesiones) == 2, f"exactamente dos claves (hay {list(api._sesiones)})")
if real and simulada:
    textos_real = " ".join(str(m.get("content")) for m in real["historial"])
    textos_sim = " ".join(str(m.get("content")) for m in simulada["historial"])
    comprobar("soy una prueba" not in textos_real,
              "el historial real no contiene el mensaje de la prueba")
    comprobar("soy el cliente real" not in textos_sim,
              "el historial simulado no contiene el mensaje real")

turno_real("WhatsApp-Simulado ", "segundo turno simulado")
comprobar(len(api._sesiones) == 2 and api._sesiones[("rapilink", "whatsapp-simulado", TEL)] is simulada,
          "el mismo canal escrito distinto reusa la MISMA sesion, sin crear una tercera")

try:
    turno_real("canal-inventado")
    comprobar(False, "atender_turno con canal desconocido deberia fallar")
except canales.CanalInvalido:
    comprobar(len(api._sesiones) == 2,
              "atender_turno con canal desconocido falla ANTES de crear sesion")

# ---------------------------------------------------------------------------
print("\n== limpiar o completar una sesion toca solo la de SU canal ==")

def dos_sesiones():
    api._sesiones.clear()
    r = {"historial": [], "escalada": True}
    s = {"historial": [], "escalada": True}
    api._sesiones[("rapilink", "whatsapp", TEL)] = r
    api._sesiones[("rapilink", "whatsapp-simulado", TEL)] = s
    return r, s

AUTOR = {"autor": "Ana", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}


from contextlib import contextmanager                              # noqa: E402
from nucleo.relevo import transiciones as _T                       # noqa: E402


@contextmanager
def resolver_devuelve(ident):
    """Desde B3.2 /resolver pasa por transiciones.resolver(): se sustituye para
    que devuelva la identidad de la conversacion sin tocar una base."""
    real = _T.resolver
    _T.resolver = lambda *a, **k: _T.Resultado(True, False, 0, None, "legado", datos=ident)
    try:
        yield
    finally:
        _T.resolver = real


# resolver un hilo simulado
r_ses, s_ses = dos_sesiones()
with Espia(), resolver_devuelve({"usuario_externo": TEL, "canal": "whatsapp-simulado"}):
    resp = cliente.post("/conversaciones/conv-sim/resolver", json={"tenant": "rapilink", **AUTOR})
comprobar(resp.status_code == 200
          and ("rapilink", "whatsapp-simulado", TEL) not in api._sesiones
          and api._sesiones.get(("rapilink", "whatsapp", TEL)) is r_ses,
          "resolver el hilo simulado descarta la sesion simulada y NO la real")

# borrar (prueba) un hilo simulado
r_ses, s_ses = dos_sesiones()
with Espia(respuestas={"borrar_conversacion":
                       {"usuario_externo": TEL, "canal": "whatsapp-simulado"}}):
    resp = cliente.delete("/conversaciones/conv-sim?tenant=rapilink")
comprobar(resp.status_code == 204
          and ("rapilink", "whatsapp-simulado", TEL) not in api._sesiones
          and api._sesiones.get(("rapilink", "whatsapp", TEL)) is r_ses,
          "borrar el hilo simulado descarta la sesion simulada y NO la real")

# respuesta de una persona en un hilo simulado, devolviendo al asistente
r_ses, s_ses = dos_sesiones()
# B3.3: la respuesta humana pasa por la guarda de control; este caso mide las
# sesiones, asi que la conversacion esta en manos de una persona.
with Espia(respuestas={"control_efectivo_de": "humano", "agregar_mensaje_humano":
                       {"canal": "whatsapp-simulado", "usuario_externo": TEL,
                        "ticket_operativo": None, "mensaje_id": "m-1"}}):
    resp = cliente.post("/conversaciones/conv-sim/mensajes",
                        json={"tenant": "rapilink", "mensaje": "ya quedo",
                              "autor": "Ana", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                              "devolver_al_asistente": True})
comprobar(resp.status_code == 201, f"la respuesta humana se guarda (fue {resp.status_code})")
comprobar(s_ses["historial"] and s_ses["escalada"] is False,
          "la respuesta y la devolucion llegan a la sesion SIMULADA")
comprobar(r_ses["historial"] == [] and r_ses["escalada"] is True,
          "la sesion REAL del mismo telefono no recibe el mensaje ni pierde su pausa")

# una fila con un canal historico desconocido no rompe una operacion ya guardada
r_ses, s_ses = dos_sesiones()
with Espia(), resolver_devuelve({"usuario_externo": TEL, "canal": "canal-viejo"}):
    resp = cliente.post("/conversaciones/conv-vieja/resolver", json={"tenant": "rapilink", **AUTOR})
comprobar(resp.status_code == 200 and len(api._sesiones) == 2,
          "resolver con canal historico desconocido: 200 y ninguna sesion tocada")

api._sesiones.clear()

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] Un canal real no entra por /chat, y el canal separa las sesiones.")
