# -*- coding: utf-8 -*-
"""
================================================================================
 LA PAUSA DESPUES DE ESCALAR  --  a nivel de TURNO, no de funcion suelta
================================================================================

    py -3.13 tests/test_pausa_escalada.py

EL BUG QUE CIERRA (12/09/2026)
------------------------------
El traspaso se daba por confirmado si quedaba registro en CUALQUIERA de tres
lugares -- caso del CRM, ticket automatico o ticket operativo -- pero la pausa
solo sabia vigilar uno: 'caso_id'. Prometiamos con tres llaves y vigilabamos
con una.

Con ticket operativo y sin caso del CRM:

    al cliente     "un compañero lo va a revisar y te escribe por aca"
    estado         escalada=True, caso_id=None
    turno siguiente  caso_sigue_abierto(None) -> False
    efecto         el codigo concluye que el caso cerro y el bot vuelve a
                   atender a alguien a quien se le prometio una persona

Dos interlocutores para el mismo cliente, que es exactamente lo que la pausa
existe para impedir.

POR QUE NO ALCANZABA CON 'caso_sigue_abierto(None) -> True'
-----------------------------------------------------------
Porque hay un segundo estado que tambien llega sin 'caso_id': cuando NO quedo
registrado nada. Ahi al cliente se le dice la verdad ("no quedo registrado,
escribime de nuevo") y ese mensaje existe para que el proximo intento vuelva a
escalar. Pausarlo seria pedirle que insista y despues no escucharlo.

Son dos estados distintos y habia que separarlos en el origen: 'escalada' solo
queda en true si el traspaso quedo registrado en algun lado. Recien entonces
"sin caso" significa sin ambiguedad "quedo en la otra cola", y el fail-safe de
caso_sigue_abierto es correcto.

POR QUE A NIVEL DE TURNO
------------------------
La regla no vive en una funcion: vive en el acuerdo entre tres piezas -- lo
que confirma el traspaso, lo que persiste el estado y lo que decide la pausa.
Probar cada una por separado deja pasar justo el desacuerdo entre ellas, que
es lo que fallo. Asi que estas pruebas llaman a atender_turno() y miran el
efecto: si el bot contesta o se calla, y si se gasto una llamada al modelo.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")


def estado_previo(escalada, necesita_humano, caso_id):
    """Lo que la base devuelve de una conversacion abierta."""
    return {"escalada": escalada, "necesita_atencion_humana": necesita_humano,
            "caso_id": caso_id, "conversation_id": "conv-1",
            "motivo_escalada": "solicitud_explicita", "rol_efectivo": None,
            "id_cliente": "5832", "nombre_cliente": "CLIENTE DE PRUEBA",
            "datos_sesion": {}}


class Turno:
    """
    Corre atender_turno() con el mundo exterior sustituido, y anota lo que se
    toco: si hablo el modelo, si se evaluo, y que se guardo.

    'caso_abierto' es lo que contestaria el CRM. Se deja como None para el
    caso sin caso_id, donde ni siquiera hay a quien preguntarle.
    """

    def __init__(self, previo, caso_abierto=True, hubo_humano=False):
        self.previo = previo
        self.caso_abierto = caso_abierto
        self.hubo_humano = hubo_humano
        self.respondio_el_modelo = False
        self.evaluo = False
        self.guardados = []

    def correr(self, mensaje="sigue sin funcionar"):
        p, esc, mot = api.persistencia, api.escalamiento, api.motor

        real_caso_sigue_abierto = esc.caso_sigue_abierto

        def _responder(*a, **k):
            self.respondio_el_modelo = True
            return ("respuesta del bot", [], [])

        def _evaluar(*a, **k):
            self.evaluo = True
            return {}

        def _caso_sigue_abierto(config, caso_id):
            # La REAL para el caso sin id -- es justo lo que se esta probando.
            if not caso_id:
                return real_caso_sigue_abierto(config, caso_id)
            return self.caso_abierto

        # Todo lo que este turno toca de la base, sustituido por nombre. La
        # prueba mide la DECISION de pausar, no la persistencia.
        postizos = {
            p: {"estado_de_conversacion_abierta": lambda *a, **k: self.previo,
                "atendida_por_humano": lambda *a, **k: self.hubo_humano,
                "registrar_mensaje": lambda t_, c_, i_, r_, rol_, txt_, *a, **k:
                    (self.guardados.append((rol_, txt_)), ("conv-1", "msg-1"))[1],
                "conversacion_vencida": lambda *a, **k: False,
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
                "registrar_marca_tv_desconocida": lambda *a, **k: None},
            esc: {"caso_sigue_abierto": _caso_sigue_abierto,
                  "evaluar": _evaluar},
            mot: {"responder": _responder},
            api: {"_resolver_verificacion_pendiente": lambda *a, **k: None,
                  "_hay_verificacion_pendiente": lambda *a, **k: False},
            api.consumo: {"estado_del_gasto": lambda *a, **k:
                          {"accion": "seguir", "gastado": 0, "tope": 0,
                           "porcentaje": 0.0}},
        }
        orig = {(m, n): getattr(m, n) for m, d in postizos.items() for n in d
                if hasattr(m, n)}
        for m, d in postizos.items():
            for n, f in d.items():
                if hasattr(m, n):
                    setattr(m, n, f)
        # La sesion vive en memoria entre turnos (api._sesiones). Sin
        # limpiarla, el segundo caso reusa el estado del primero y la prueba
        # mide la cache, no la decision. Paso al escribirla: tres casos
        # "fallaron" porque heredaron la pausa del anterior.
        api._sesiones.clear()
        try:
            return api.atender_turno(CONFIG, "rapilink", "cliente_final",
                                     "573000000000", mensaje, "api")
        finally:
            for (m, n), f in orig.items():
                setattr(m, n, f)


print("=" * 74)
print(" LA PAUSA DESPUES DE ESCALAR  --  el bot no le habla a quien espera")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. ticket operativo SIN caso del CRM: se pausa ==")
# El bug. Antes: caso_sigue_abierto(None) daba False, el codigo leia "el caso
# cerro" y el bot volvia a atender.
t = Turno(estado_previo(escalada=True, necesita_humano=True, caso_id=None))
r = t.correr()
comprobar(r.get("pausada") is True, "el turno queda pausado")
comprobar(not t.respondio_el_modelo,
          "NO se llama al modelo: el bot no compone nada mientras espera")
comprobar(not t.evaluo,
          "ni al evaluador -- sin humano que haya escrito no hay cierre "
          "posible, asi que su veredicto se descartaria igual")

# ---------------------------------------------------------------------------
print("\n== 2. caso del CRM abierto: se pausa; cerrado: retoma ==")
t = Turno(estado_previo(True, True, "caso-123"), caso_abierto=True)
r = t.correr()
comprobar(r.get("pausada") is True and not t.respondio_el_modelo,
          "con el caso abierto el bot se calla")

t = Turno(estado_previo(True, True, "caso-123"), caso_abierto=False)
r = t.correr()
comprobar(t.respondio_el_modelo,
          "y cuando el humano lo cierra, el asistente retoma solo")

# ---------------------------------------------------------------------------
print("\n== 3. ticket automatico sin humano: NO se pausa ==")
# Una visita agendada sola no tiene a nadie a quien esperar. Pausarla dejaria
# al cliente mudo con el bot para siempre.
t = Turno(estado_previo(escalada=True, necesita_humano=False, caso_id=None))
r = t.correr()
comprobar(t.respondio_el_modelo,
          "el bot sigue atendiendo normal")
comprobar(not r.get("pausada"), "y el turno no se marca pausado")

# ---------------------------------------------------------------------------
print("\n== 4. sin escalada previa: atiende, y puede reintentar ==")
# El estado que deja una escalada que NO quedo registrada en ningun lado. El
# aviso le pidio al cliente que escriba de nuevo; ese reintento depende de
# que el bot ATIENDA este turno.
t = Turno(estado_previo(escalada=False, necesita_humano=False, caso_id=None))
r = t.correr("hola, sigo esperando")
comprobar(t.respondio_el_modelo,
          "el bot atiende: es lo que permite que el reintento ocurra")

# ---------------------------------------------------------------------------
print("\n== 5. si una persona YA escribio, el bot se calla y guarda ==")
t = Turno(estado_previo(True, True, "caso-123"), caso_abierto=True,
          hubo_humano=True)
r = t.correr("ok, gracias")
comprobar(r.get("respuesta") == "" and r.get("pausada") is True,
          "no manda nada: contradecir a la persona que acaba de escribir es "
          "peor que callarse")
comprobar(any(rol == "user" for rol, _ in t.guardados),
          "pero el mensaje del cliente SI queda guardado, que es donde la "
          "persona lo va a leer")
comprobar(t.evaluo,
          "y ahi SI se evalua: con una persona en el medio, un 'ok' del "
          "cliente puede cerrar el caso de verdad")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print("[OK] El bot no le habla a quien esta esperando a una persona.")
