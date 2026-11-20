# -*- coding: utf-8 -*-
"""
UN CLIENTE QUE VUELVE TAMBIEN RECIBE EL PROMPT DEL AGENTE.

atender_turno mete en el historial el resumen de la conversacion anterior (o los ultimos
mensajes, tras un reinicio) ANTES de llamar a motor.responder. El motor solo armaba su
preambulo si el historial estaba vacio, asi que un cliente que volvia le llegaba al modelo
con SOLO ese resumen: sin identidad, sin reglas, sin la franja del dia. Medido el 09/11/2026:
roles ['system','user','system'] y el unico system era el resumen; a las 11:58 contesto
"Buenas noches" a un "Buenas noches". Ningun test lo veia: todos arrancaban con historial vacio.

Se afirma sobre lo que RECIBE el modelo (sin modelo, sin red, sin base):

    py -3.13 tests/test_system_con_resumen_previo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from pathlib import Path  # noqa: E402

from nucleo.config import cargar_config  # noqa: E402
from nucleo.modelo import cliente, motor  # noqa: E402
from nucleo.recuperacion.prompt import construir_system  # noqa: E402
from nucleo.seguimiento import resumen  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class _Parar(Exception):
    pass


RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
ROL = "soporte_tecnico_cliente"
SYSTEM = construir_system(CONFIG, ROL)


def lo_que_recibe_el_modelo(historial):
    """Corre el turno con el cliente del modelo reemplazado: devuelve los mensajes que le llegarian."""
    capturado = []

    def espia(ref, mensajes, *a, **k):
        capturado.append([dict(m) for m in mensajes])
        raise _Parar()

    original = cliente.chat
    cliente.chat = espia
    # Lo que va a la base queda fuera: esto mide el ARMADO del historial, no la persistencia.
    motor.catalogo_habilidades.indice_de = lambda *a, **k: []
    motor.recuperar = lambda *a, **k: ([], None)
    try:
        motor.responder(CONFIG, ROL, "buenas noches", historial, None)
    except _Parar:
        pass
    finally:
        cliente.chat = original
    return capturado[0] if capturado else []


def tiene_system_del_agente(mensajes):
    return any(m["role"] == "system" and m["content"] == SYSTEM for m in mensajes)


print("\n1. historial vacio (como siempre)")
m = lo_que_recibe_el_modelo([])
afirmar(bool(m) and m[0]["content"] == SYSTEM, "el primer mensaje es el prompt del agente")

print("\n2. cliente que vuelve: el historial ya trae el resumen de la conversacion anterior")
ctx = resumen.como_contexto("Problema de internet resuelto.", 720)
m = lo_que_recibe_el_modelo([dict(ctx)])
afirmar(bool(m) and m[0]["content"] == SYSTEM, "el modelo RECIBE el prompt del agente, y va primero")
afirmar(any(x["content"] == ctx["content"] for x in m), "el resumen sigue estando")
iu = max(i for i, x in enumerate(m) if x["role"] == "user" and x["content"] == "buenas noches")
ir = next(i for i, x in enumerate(m) if x["content"] == ctx["content"])
afirmar(0 < ir < iu, "el resumen queda entre el prompt y el mensaje del cliente")
afirmar(sum(1 for x in m if x["content"] == SYSTEM) == 1, "el prompt no se duplica")

print("\n3. tras un reinicio: el historial rehidratado trae solo mensajes de usuario y asistente")
hist = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "Hola, ¿en que te ayudo?"}]
m = lo_que_recibe_el_modelo([dict(x) for x in hist])
afirmar(bool(m) and m[0]["content"] == SYSTEM, "el prompt va primero tambien aqui")
afirmar([x["content"] for x in m if x["role"] in ("user", "assistant")][:2] == [h["content"] for h in hist],
        "los mensajes rehidratados se conservan, en orden")

print("\n4. una conversacion en curso (el prompt ya esta) no lo repite")
m1 = lo_que_recibe_el_modelo([{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hola"},
                              {"role": "assistant", "content": "Hola"}])
afirmar(sum(1 for x in m1 if x["content"] == SYSTEM) == 1, "una sola vez")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] Un cliente que vuelve recibe el prompt del agente.")
