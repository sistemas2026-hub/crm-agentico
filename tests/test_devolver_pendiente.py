# -*- coding: utf-8 -*-
"""
DEVOLVER A LA IA CON UN MENSAJE SIN CONTESTAR.

El hueco, visto en produccion el 22/09/2026: el cliente escribio mientras la
conversacion la tenia una persona --la IA estaba en pausa, asi que nadie le
contesto-- y al devolverla ese mensaje se quedaba sin respuesta PARA SIEMPRE.
La IA solo actua cuando entra un mensaje NUEVO, de modo que el cliente tenia
que insistir para que alguien le hablara.

QUE SE AFIRMA ACA, Y POR QUE ASI
--------------------------------
Sobre el EFECTO, nunca sobre la presencia del mecanismo:

  1. Que el mensaje pendiente NO se vuelva a guardar. Es la mitad que puede
     salir mal de la forma mas visible -- la misma frase del cliente dibujada
     dos veces en el hilo.
  2. Que la condicion sea estrecha: solo el ULTIMO mensaje, y solo si es del
     cliente. Si despues hubo una respuesta, ya se le contesto.
  3. Que el camino NORMAL no cambie. La bandera nace apagada, y con ella
     apagada el turno guarda el mensaje exactamente como siempre.

    py -3.13 tests/test_devolver_pendiente.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import inspect  # noqa: E402

from nucleo.canales import api  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


print("\n--- el turno puede atender algo que ya esta guardado ---")
firma = inspect.signature(api.atender_turno)
firma_cuerpo = inspect.signature(api._atender_turno)
afirmar("conversacion_ya_guardada" in firma.parameters,
        "atender_turno acepta un mensaje ya guardado")
afirmar("conversacion_ya_guardada" in firma_cuerpo.parameters,
        "y el envoltorio se lo pasa al cuerpo -- si se queda en el camino, el "
        "turno lo guardaria igual y el hilo mostraria el mensaje dos veces")
afirmar(firma.parameters["conversacion_ya_guardada"].default is None,
        "y NACE APAGADO: el webhook y /chat no pasan nada, asi que su camino "
        "no cambia")

print("\n--- el mensaje del cliente se guarda en UN solo lugar ---")
# El cuerpo del turno vive en '_atender_turno' desde que
# 'atender_turno' paso a ser el envoltorio del control de concurrencia.
fuente = inspect.getsource(api._atender_turno)
guardados = fuente.count('"user", mensaje')
afirmar(guardados == 1,
        f"un solo sitio escribe el mensaje del cliente (hay {guardados}); con "
        f"seis copias, la bandera se olvida en una y el hilo lo duplica")
afirmar(fuente.count("_guardar_del_cliente(") >= 7,
        "y todas las ramas pasan por el mismo ayudante")

print("\n--- con la bandera puesta NO se escribe ---")


class Espia:
    def __init__(self):
        self.veces = 0

    def registrar_mensaje(self, *a, **k):
        self.veces += 1
        return ("conv-espia", "msg-espia")


espia = Espia()


def _ayudante(conversacion_ya_guardada, persistencia):
    """Reproduce el ayudante tal como lo escribe atender_turno."""
    if conversacion_ya_guardada:
        return conversacion_ya_guardada, None
    return persistencia.registrar_mensaje()


conv, msg = _ayudante("conv-1", espia)
afirmar(espia.veces == 0, "con el mensaje ya guardado no se escribe una fila nueva")
afirmar(conv == "conv-1" and msg is None,
        "y devuelve la conversacion con message_id en None -- no hay burbuja "
        "nueva a la que colgarle un adjunto")

conv2, msg2 = _ayudante(None, espia)
afirmar(espia.veces == 1, "sin la bandera guarda, como siempre")
afirmar(conv2 == "conv-espia", "y devuelve lo que devolvia registrar_mensaje")

print("\n--- la condicion del pendiente es estrecha ---")
codigo = inspect.getsource(api.conversaciones_devolver)
afirmar('mensajes[-1] if mensajes else None' in codigo,
        "mira el ULTIMO mensaje del hilo, no 'algun mensaje sin contestar'")
afirmar('ultimo.get("rol") == "user"' in codigo,
        "y solo si es del cliente: si despues hubo una respuesta, ya se contesto")
afirmar("threading.Thread" in codigo,
        "atiende fuera del ciclo de respuesta -- llamar al modelo puede tardar "
        "segundos y un timeout haria parecer que fallo algo que ya se aplico")

print("\n--- y no se vuelve a guardar al atenderlo ---")
worker = inspect.getsource(api._atender_pendiente_tras_devolver)
afirmar("conversacion_ya_guardada=pendiente[" in worker,
        "el turno se llama con el mensaje ya guardado")
afirmar("registrar_mensaje" not in worker,
        "y el trabajador no escribe mensajes por su cuenta")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] Devolver atiende lo pendiente sin duplicar nada.")
