# -*- coding: utf-8 -*-
"""
================================================================================
 EL HISTORIAL UNICO  --  lo que ve el modelo en vivo es lo que ve tras reiniciar
================================================================================

    py -3.13 tests/test_historial_unico.py          (sin base)

Fase B2.3 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md (D8, D12, §10). La parte contra
PostgreSQL (reconstruccion real, resumen, bytes intactos) esta en
tests/test_origen_mensajes_base.py, seccion 5.

  1. La regla (nucleo/relevo/historial.py): cada combinacion rol/origen, notas
     fuera, bloque de legado SOLO por 'assistant' sin origen y UNA vez, y la
     entrada no se modifica.
  2. VIVO = RECONSTRUIDO de punta a punta: turnos reales de atender_turno() con
     la base y el modelo sustituidos, mas una respuesta de persona por la ruta
     HTTP. Lo que quedo en memoria (sin los mensajes de sistema y herramientas,
     que no se guardan) es igual a construir() sobre las filas que se guardaron.
  3. Una guarda que reescribe la respuesta despues de guardarla (la promesa de
     traspaso sin registro): memoria y fila quedan con el MISMO texto final.
================================================================================
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402
from nucleo.relevo import historial as H                            # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


print("=" * 74)
print(" EL HISTORIAL UNICO")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. la regla ==")
TEXTO = "Ya revisé tu conexión.\n  (con espacios y acentos: ñ, á)  "
casos = [
    (("user", "cliente", None), {"role": "user", "content": TEXTO}),
    (("user", None, None), {"role": "user", "content": TEXTO}),
    (("assistant", "ia", None), {"role": "assistant", "content": TEXTO}),
    (("assistant", "sistema", None), {"role": "assistant", "content": TEXTO}),
    (("assistant", "humano", "María Gómez"), {"role": "assistant", "content": "(María Gómez, del equipo) " + TEXTO}),
    (("assistant", None, None), {"role": "assistant", "content": TEXTO}),
    (("humano", None, None), {"role": "assistant", "content": "(del equipo) " + TEXTO}),
    (("nota", "humano", "María Gómez"), None),
    (("nota", None, None), None),
]
for (rol, origen, autor), esperado in casos:
    comprobar(H.entrada(rol, origen, TEXTO, autor) == esperado,
              f"rol={rol} origen={origen} -> {esperado and esperado['role']}",
              f"{H.entrada(rol, origen, TEXTO, autor)!r}")


def fila(rol, contenido, origen=None, autor=None):
    return {"rol": rol, "contenido": contenido, "origen": origen, "autor_nombre": autor}


def bloques(historial):
    return sum(1 for m in historial if m["role"] == "system" and m["content"] == H.BLOQUE_LEGADO)


solo_user_y_humano = [fila("user", "hola"), fila("humano", "te ayudo"), fila("user", "gracias")]
comprobar(bloques(H.construir(solo_user_y_humano)) == 0,
          "user/NULL y humano/NULL sin ambiguos: NINGUN bloque de legado")
con_ambiguos = [fila("user", "a"), fila("assistant", "b"), fila("user", "c"), fila("assistant", "d"),
                fila("assistant", "e", "ia")]
r = H.construir(con_ambiguos)
comprobar(bloques(r) == 1 and r[0]["content"] == H.BLOQUE_LEGADO,
          "dos assistant/NULL: el bloque aparece EXACTAMENTE una vez, al principio")
comprobar(bloques(H.construir([fila("user", "a", "cliente"), fila("assistant", "b", "ia")])) == 0,
          "filas nuevas con origen: ningun bloque")
comprobar(bloques(H.construir([fila("nota", "x"), fila("user", "a")])) == 0,
          "una nota sin origen NO activa el bloque (no llega al modelo)")
entrada_original = copy.deepcopy(con_ambiguos + [fila("assistant", "f", "humano", "Ana")])
copia = copy.deepcopy(entrada_original)
H.construir(copia)
comprobar(copia == entrada_original, "construir() no modifica las filas que recibe")
r = H.construir([fila("assistant", TEXTO), fila("user", TEXTO, "cliente")])
comprobar([m["content"] for m in r if m["role"] != "system"] == [TEXTO, TEXTO],
          "el contenido de legado y de cliente pasa byte a byte, sin prefijo")
r = H.construir([fila("user", "a"), fila("nota", "SECRETO DEL EQUIPO", "humano", "Ana"), fila("assistant", "b", "ia")])
comprobar(all("SECRETO" not in m["content"] for m in r), "las notas no aparecen en el historial")
# D24: una respuesta de la IA descartada (no salio) no entra. El resumen de una
# conversacion vencida solo tiene esta regla como filtro.
r = H.construir([{"rol": "user", "contenido": "hola", "origen": "cliente"},
                 {"rol": "assistant", "contenido": "NO-SALIO", "origen": "ia", "estado_entrega": "descartado"},
                 {"rol": "assistant", "contenido": "si salio", "origen": "ia", "estado_entrega": "enviado"}])
comprobar([m["content"] for m in r] == ["hola", "si salio"],
          f"una respuesta descartada (D24) no entra al historial ni al resumen ({r})")


# ---------------------------------------------------------------------------
print("\n== 2. vivo = reconstruido, de punta a punta ==")
CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
TEL = "573000000000"
filas_guardadas: list[dict] = []
por_id: dict[str, dict] = {}


def _registrar(tenant, canal, usuario, rol_efectivo, rol, contenido, *a, origen, **k):
    mid = f"m-{len(filas_guardadas)}"
    f = {"id": mid, "rol": rol, "contenido": contenido, "origen": origen, "autor_nombre": None}
    filas_guardadas.append(f)
    por_id[mid] = f
    return "conv-1", mid


def _actualizar(tenant, mensaje_id, contenido):
    por_id[mensaje_id]["contenido"] = contenido


def _agregar_humano(tenant, conv, contenido, autor, *, autor_usuario_id, clave_idempotencia=None, solo_canal=None):
    mid = f"m-{len(filas_guardadas)}"
    f = {"id": mid, "rol": "assistant", "contenido": contenido, "origen": "humano", "autor_nombre": autor}
    filas_guardadas.append(f)
    por_id[mid] = f
    return {"canal": "whatsapp-simulado", "usuario_externo": TEL, "ticket_operativo": None,
            "mensaje_id": mid, "existente": False, "estado_entrega": None}


respuestas_modelo: list[str] = []


def _responder(config, rol, mensaje, historial, sesion, nota_continuidad=None, **_kw):
    #  M06-F: el turno real pasa ademas 'origen' (la solicitud, para la idempotencia).
    # Como el motor real: agrega mensajes de sistema y la respuesta al historial.
    historial.append({"role": "system", "content": "instrucciones del turno"})
    historial.append({"role": "user", "content": mensaje})
    texto = respuestas_modelo.pop(0)
    historial.append({"role": "assistant", "content": texto})
    return texto, [], []


class Mundo:
    def __init__(self, reescribir=None):
        self.reescribir = reescribir

    def __enter__(self):
        p, esc, mot = api.persistencia, api.escalamiento, api.motor
        previo = {"escalada": False, "necesita_atencion_humana": False, "caso_id": None,
                  "conversation_id": "conv-1", "motivo_escalada": None, "rol_efectivo": None,
                  "id_cliente": None, "nombre_cliente": None, "datos_sesion": {}}
        reescribir = self.reescribir

        def _cerrar(config, tenant, conversation_id, mensaje_id, respuesta, id_sesion, **k):
            if reescribir is None:
                return respuesta
            # Como la guarda real: cambia el texto y corrige SOLO la fila.
            api.persistencia.actualizar_contenido_mensaje(tenant, mensaje_id, reescribir)
            return reescribir

        self.postizos = {
            p: {"estado_de_conversacion_abierta": lambda *a, **k: previo,
                # B3.3b: el control se lee de la base en cada turno. Se deriva del
                # mismo estado previo, con la regla de legado de control_efectivo.
                "control_de_conversacion_abierta": lambda *a, **k: (
                    None if not previo else {
                        "conversation_id": previo.get("conversation_id") or "conv-1",
                        "control_efectivo": "humano" if (previo.get("escalada")
                                                         and previo.get("necesita_atencion_humana")) else "ia",
                        "control_motivo": None, "relevo_version": 0}),
                "atendida_por_humano": lambda *a, **k: False,
                "registrar_mensaje": _registrar,
                "actualizar_contenido_mensaje": _actualizar,
                "agregar_mensaje_humano": _agregar_humano,
                # B3.3: la guarda de control (la persona tiene la conversacion).
                "control_efectivo_de": lambda *a, **k: "humano",
                "conversacion_vencida": lambda *a, **k: None,
                "identificar_cliente": lambda *a, **k: None,
                "resumen_anterior": lambda *a, **k: None,
                "historial_para_el_modelo": lambda *a, **k: [],
                "registrar_turno": lambda *a, **k: None,
                "caso_de_conversacion": lambda *a, **k: None,
                "ticket_operativo_de": lambda *a, **k: None,
                "cerrar_conversacion": lambda *a, **k: None,
                "guardar_resumen": lambda *a, **k: None,
                "marcar_caso": lambda *a, **k: None,
                "completar_medicion": lambda *a, **k: None,
                "guardar_estado_routing": lambda *a, **k: None,
                "registrar_estado_escalada": lambda *a, **k: None,
                "registrar_marca_tv_desconocida": lambda *a, **k: None},
            esc: {"caso_sigue_abierto": lambda *a, **k: True, "evaluar": lambda *a, **k: {}},
            mot: {"responder": _responder},
            api: {"_resolver_verificacion_pendiente": lambda *a, **k: None,
                  "_hay_verificacion_pendiente": lambda *a, **k: False,
                  "_cerrar_el_traspaso": _cerrar,
                  "_config_de": lambda t: CONFIG},
            api.consumo: {"estado_del_gasto": lambda *a, **k:
                          {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0}},
        }
        self.orig = {(m, n): getattr(m, n) for m, d in self.postizos.items() for n in d if hasattr(m, n)}
        for m, d in self.postizos.items():
            for n, f in d.items():
                if hasattr(m, n):
                    setattr(m, n, f)
        self.token = api._TOKEN_SERVICIO
        api._TOKEN_SERVICIO = None
        return self

    def __exit__(self, *e):
        for (m, n), f in self.orig.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = self.token
        return False


def memoria():
    ses = api._sesiones.get(("rapilink", "whatsapp-simulado", TEL))
    return [m for m in (ses or {}).get("historial", []) if m.get("role") in ("user", "assistant")]


api._sesiones.clear()
filas_guardadas.clear()
por_id.clear()
respuestas_modelo[:] = ["Hola, ¿en qué te ayudo?", "Ya lo reviso.", "Listo."]
with Mundo():
    api.atender_turno(CONFIG, "rapilink", "cliente_final", TEL, "hola", "whatsapp-simulado")
    api.atender_turno(CONFIG, "rapilink", "cliente_final", TEL, "no tengo internet", "whatsapp-simulado")
    r = api.app.test_client().post("/conversaciones/conv-1/mensajes", json={
        "tenant": "rapilink", "mensaje": "Soy María, ya reinicié tu equipo.",
        "autor": "María Gómez", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"})
    api.atender_turno(CONFIG, "rapilink", "cliente_final", TEL, "ya funciona", "whatsapp-simulado")
comprobar(r.status_code == 201, f"la respuesta de persona se guardo ({r.status_code})")
vivo = memoria()
reconstruido = H.construir(filas_guardadas)
comprobar(vivo == reconstruido,
          f"historial vivo == construir(filas guardadas) ({len(vivo)} mensajes)",
          f"\n vivo={vivo}\n rec ={reconstruido}")
comprobar(any(m["content"] == "(María Gómez, del equipo) Soy María, ya reinicié tu equipo." for m in vivo),
          "la respuesta de la persona entra firmada, igual en vivo y reconstruida")
comprobar(all(f["contenido"] == "Soy María, ya reinicié tu equipo." for f in filas_guardadas if f["origen"] == "humano"),
          "y la fila guardada conserva el texto sin firma")

# ---------------------------------------------------------------------------
print("\n== 3. una guarda reescribe la respuesta: memoria = fila ==")
api._sesiones.clear()
filas_guardadas.clear()
por_id.clear()
respuestas_modelo[:] = ["Tu caso ya quedó con un compañero humano."]
CORREGIDO = "No pude registrar tu pedido. Escribime de nuevo, por favor."
with Mundo(reescribir=CORREGIDO):
    salida = api.atender_turno(CONFIG, "rapilink", "cliente_final", TEL, "gracias por la info", "whatsapp-simulado")
ultima_fila = [f for f in filas_guardadas if f["rol"] == "assistant"][-1]
ultima_memoria = [m for m in memoria() if m["role"] == "assistant"][-1]
comprobar(salida["respuesta"] == CORREGIDO and ultima_fila["contenido"] == CORREGIDO,
          "al cliente y a la fila les llega el texto corregido")
comprobar(ultima_memoria["content"] == CORREGIDO,
          "y la memoria del modelo tambien (antes recordaba la promesa que nunca se envio)",
          f"memoria={ultima_memoria}")
comprobar(memoria() == H.construir(filas_guardadas), "vivo == reconstruido tambien despues de la guarda")

api._sesiones.clear()
if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] El modelo ve lo mismo en vivo y tras un reinicio, y nunca ve una nota.")
