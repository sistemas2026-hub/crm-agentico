# -*- coding: utf-8 -*-
"""
================================================================================
 UBICACION, CONTACTO Y REACCION DEL CLIENTE  --  11/11/2026
================================================================================
    py -3.13 tests/test_ubicacion_contacto_reaccion.py            (sin base)

Hasta hoy los tres tipos llegaban como vacio:
  - la UBICACION, como el aviso «[El cliente compartio su ubicacion]», y las
    coordenadas se perdian -- nadie podia verlas y el modelo no podia usarlas;
  - el CONTACTO y la REACCION le devolvian al cliente «no puedo leer ese tipo
    de archivo», y el mensaje no se guardaba.

Se afirma sobre el EFECTO: que texto llega al turno (y por lo tanto al hilo y
al modelo) y que se le contesta al cliente. No llama a Meta, al modelo ni a la
base: se doblan.
================================================================================
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import whatsapp                       # noqa: E402
from nucleo.canales import api                            # noqa: E402

TENANT = "tenant-de-prueba"
fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def sobre(mensaje):
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "573001112233", "profile": {"name": "Juana"}}],
        "messages": [mensaje]}}]}]}


def entrante(mensaje):
    return whatsapp.mensajes_entrantes(sobre(mensaje))[0]


print("\n1. La traduccion del sobre de Meta")

m = entrante({"id": "w.L", "type": "location",
              "location": {"latitude": 10.9878123456, "longitude": -74.7889, "name": "Casa",
                           "address": "Calle 50 # 12-30"}})
revisar(m["texto"] == "[El cliente compartio su ubicacion: Casa · Calle 50 # 12-30 · "
                      "coordenadas 10.987812, -74.7889]",
        "la ubicacion llega con nombre, direccion y coordenadas", m["texto"])

m = entrante({"id": "w.L2", "type": "location", "location": {"latitude": 4.6, "longitude": -74.08}})
revisar(m["texto"] == "[El cliente compartio su ubicacion: coordenadas 4.6, -74.08]",
        "sin nombre ni direccion, solo las coordenadas", m["texto"])

m = entrante({"id": "w.L3", "type": "location", "location": {"name": "Casa"}})
revisar(m["texto"] == "", "sin coordenadas legibles no se inventa nada (cae al aviso)", m["texto"])

m = entrante({"id": "w.C", "type": "contacts", "contacts": [
    {"name": {"formatted_name": "Pedro Gomez"},
     "phones": [{"phone": "+57 300 111 2233", "wa_id": "573001112233"}],
     "emails": [{"email": "pedro@correo.com"}],
     "addresses": [{"street": "Calle 1"}]}]})
revisar(m["texto"] == "[El cliente compartio un contacto: Pedro Gomez — +57 300 111 2233]",
        "el contacto llega con nombre y telefono", m["texto"])
revisar("correo" not in m["texto"] and "Calle 1" not in m["texto"],
        "y SIN el correo ni la direccion del tercero", m["texto"])

m = entrante({"id": "w.C2", "type": "contacts",
              "contacts": [{"name": {"formatted_name": f"P{i}"}, "phones": [{"phone": str(i)}]}
                           for i in range(7)]})
revisar(m["texto"].count(" — ") == whatsapp.CONTACTOS_MAXIMOS and "(y 2 mas)" in m["texto"],
        "una agenda entera se corta en los primeros y dice cuantos quedaron", m["texto"])

m = entrante({"id": "w.R", "type": "reaction", "reaction": {"message_id": "w.NUESTRO", "emoji": "👍"}})
revisar(m["tipo"] == "reaction" and m["reaccion"] == {"emoji": "👍", "a": "w.NUESTRO"},
        "la reaccion trae el emoji y A QUE mensaje", f"{m}")

m = entrante({"id": "w.T", "type": "text", "text": {"body": "hola"}})
revisar(m["texto"] == "hola" and m["reaccion"] is None, "el texto de siempre no cambia", f"{m}")


print("\n2. Lo que llega al turno y lo que se le contesta al cliente")

turnos: list = []
textos: list = []
buscados: list = []
originales = [(api, n, getattr(api, n)) for n in
              ("atender_turno", "_atendio_baja_o_alta", "_guardar_adjunto",
               "_transcribir_si_es_voz", "_analizar_si_es_imagen")]
originales += [(api.whatsapp, "enviar_texto", api.whatsapp.enviar_texto),
               (api.whatsapp, "marcar_leido", api.whatsapp.marcar_leido),
               (api.encuesta, "responder_boton", api.encuesta.responder_boton),
               (api.consumo, "estado_del_gasto", api.consumo.estado_del_gasto),
               (api.persistencia, "contenido_de_wamid", api.persistencia.contenido_de_wamid),
               (api.persistencia, "estado_de_conversacion_abierta",
                api.persistencia.estado_de_conversacion_abierta)]
#: Lo que pregunta el canal antes de llevar una reaccion al turno (H6).
consultas_abierta: list = []
HORAS_INACTIVIDAD = 24


class Config:
    class limites:
        horas_inactividad_cierra = HORAS_INACTIVIDAD


try:
    api.atender_turno = lambda config, tenant, rol, de, texto, canal, **kw: (
        turnos.append(texto) or {"respuesta": "", "conversacion_id": None})
    api.whatsapp.enviar_texto = lambda c, t, de, texto: textos.append(texto)
    api.whatsapp.marcar_leido = lambda c, t, w: None
    api.encuesta.responder_boton = lambda c, t, e: None
    api._atendio_baja_o_alta = lambda c, t, de, texto: False
    api._guardar_adjunto = lambda *a, **k: None
    api._transcribir_si_es_voz = lambda *a, **k: {}
    api._analizar_si_es_imagen = lambda *a, **k: {}
    api.consumo.estado_del_gasto = lambda c, t: {"accion": "seguir"}
    api.persistencia.contenido_de_wamid = lambda t, w, canal, de: (
        buscados.append((w, canal, de))
        or ("¿Te interesa que registre la solicitud?" if w == "w.NUESTRO" else None))
    # Por defecto el chat TIENE una conversacion abierta: es el caso de todas
    # las reacciones de abajo hasta el bloque H6.
    api.persistencia.estado_de_conversacion_abierta = lambda t, canal, de, horas=None: (
        consultas_abierta.append((canal, de, horas)) or {"conversation_id": "c-abierta"})

    def procesar(mensaje):
        turnos.clear(); textos.clear()
        api._procesar_mensaje_whatsapp(Config(), TENANT, "cliente_final", entrante(mensaje))

    procesar({"id": "w.L", "type": "location", "location": {"latitude": 10.98, "longitude": -74.78}})
    revisar(turnos == ["[El cliente compartio su ubicacion: coordenadas 10.98, -74.78]"] and not textos,
            "la ubicacion va al turno CON las coordenadas, sin «no puedo leer»", f"{turnos} {textos}")

    procesar({"id": "w.L3", "type": "location", "location": {}})
    revisar(turnos == ["[El cliente compartio su ubicacion]"],
            "una ubicacion sin coordenadas cae al aviso de siempre", f"{turnos}")

    procesar({"id": "w.C", "type": "contacts",
              "contacts": [{"name": {"formatted_name": "Pedro"}, "phones": [{"phone": "3001112233"}]}]})
    revisar(turnos == ["[El cliente compartio un contacto: Pedro — 3001112233]"] and not textos,
            "el contacto va al turno, sin «no puedo leer»", f"{turnos} {textos}")

    procesar({"id": "w.R", "type": "reaction", "reaction": {"message_id": "w.NUESTRO", "emoji": "👍"}})
    revisar(turnos == ["[El cliente reacciono con 👍 a: «¿Te interesa que registre la solicitud?»]"]
            and not textos and buscados[-1] == ("w.NUESTRO", "whatsapp", "573001112233"),
            "un 👍 va al turno con el mensaje al que reacciono, buscado SOLO en el chat de quien "
            "reacciona (revisor de PII, H2)", f"{turnos} {textos} {buscados}")

    procesar({"id": "w.R2", "type": "reaction", "reaction": {"message_id": "w.VIEJO", "emoji": "❤️"}})
    revisar(turnos == ["[El cliente reacciono con ❤️ a un mensaje]"],
            "si el mensaje no se encuentra, se dice sin cita (no se inventa a que)", f"{turnos}")

    def rompe(t, w, canal, de):
        raise RuntimeError("la base no contesta")
    api.persistencia.contenido_de_wamid = rompe
    procesar({"id": "w.R3", "type": "reaction", "reaction": {"message_id": "w.NUESTRO", "emoji": "👍"}})
    revisar(turnos == ["[El cliente reacciono con 👍 a un mensaje]"],
            "si la base no contesta, la reaccion igual llega al turno", f"{turnos}")

    procesar({"id": "w.R4", "type": "reaction", "reaction": {"message_id": "w.NUESTRO", "emoji": ""}})
    revisar(turnos == [] and textos == [],
            "QUITAR una reaccion no despierta al modelo ni le contesta nada", f"{turnos} {textos}")

    largo = "x" * 400
    api.persistencia.contenido_de_wamid = lambda t, w, canal, de: largo
    procesar({"id": "w.R5", "type": "reaction", "reaction": {"message_id": "w.L", "emoji": "👍"}})
    revisar(turnos and len(turnos[0]) < 220 and turnos[0].endswith("…»]"),
            "un mensaje largo se cita recortado", f"{len(turnos[0]) if turnos else None}")

    # H6 (11/11/2026, auditoria): un 👍 a la despedida, con el chat ya cerrado,
    # abria una conversacion nueva que la IA contestaba. Decision: sin una
    # conversacion abierta, la reaccion no abre ninguna y no se contesta.
    revisar(consultas_abierta and consultas_abierta[-1] == ("whatsapp", "573001112233", HORAS_INACTIVIDAD),
            "pregunta por la abierta de ESE chat, con el mismo plazo de inactividad que usa el turno",
            f"{consultas_abierta[-1:]}")
    api.persistencia.contenido_de_wamid = lambda t, w, canal, de: (
        buscados.append((w, canal, de)) or "¡Gracias por escribirnos! Que tengas buen dia.")
    api.persistencia.estado_de_conversacion_abierta = lambda t, canal, de, horas=None: None
    buscados.clear()
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        procesar({"id": "w.R6", "type": "reaction", "reaction": {"message_id": "w.ADIOS", "emoji": "👍"}})
    log = salida.getvalue()
    revisar(turnos == [] and textos == [],
            "EL EFECTO: un 👍 sin conversacion abierta no llega al turno ni recibe respuesta",
            f"{turnos} {textos}")
    revisar(buscados == [], "ni siquiera se busca a que reacciono", f"{buscados}")
    revisar("reaccion sin conversacion abierta" in log
            and "573001112233" not in log and "👍" not in log and "w.ADIOS" not in log,
            "al log va el evento, sin el numero, el emoji ni el mensaje", log)

    procesar({"id": "w.T2", "type": "text", "text": {"body": "hola de nuevo"}})
    revisar(turnos == ["hola de nuevo"],
            "un TEXTO sin conversacion abierta abre una, como siempre: la regla es solo de reacciones",
            f"{turnos}")

    def abierta_rompe(t, canal, de, horas=None):
        raise RuntimeError("la base no contesta")
    api.persistencia.estado_de_conversacion_abierta = abierta_rompe
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        procesar({"id": "w.R7", "type": "reaction", "reaction": {"message_id": "w.ADIOS", "emoji": "👍"}})
    revisar(turnos == ["[El cliente reacciono con 👍 a: «¡Gracias por escribirnos! Que tengas buen dia.»]"],
            "si la consulta falla, se sigue como hasta hoy: la reaccion va al turno", f"{turnos}")
    revisar("573001112233" not in salida.getvalue(),
            "y el fallo se registra sin el numero", salida.getvalue())

    procesar({"id": "w.S", "type": "unsupported"})
    revisar(textos and "no puedo leer" in textos[0] and turnos == [],
            "un tipo que de verdad no se entiende sigue recibiendo el aviso de siempre", f"{turnos} {textos}")
finally:
    for obj, nombre, original in originales:
        setattr(obj, nombre, original)


print("\n3. Los avisos no se buscan en la documentacion (revisor de PII, H1)")

from nucleo.canales import avisos                         # noqa: E402
from nucleo.modelo import motor                           # noqa: E402

armados = [
    whatsapp.texto_de_ubicacion({"latitude": 4.6, "longitude": -74.08}),
    whatsapp.texto_de_contactos([{"name": {"formatted_name": "Pedro"}, "phones": [{"phone": "300"}]}]),
    api._AVISO_ADJUNTO["location"],
]
originales = [(api.persistencia, "contenido_de_wamid", api.persistencia.contenido_de_wamid)]
try:
    api.persistencia.contenido_de_wamid = lambda t, w, canal, de: "hola"
    armados.append(api._texto_de_reaccion(TENANT, {"emoji": "👍", "a": "w"}, "573001112233"))
finally:
    for obj, nombre, original in originales:
        setattr(obj, nombre, original)
revisar(all(avisos.es_aviso_con_datos(t) for t in armados),
        "lo que arma el canal se reconoce como aviso: si un lado cambia el texto, esto lo dice",
        f"{armados}")
revisar(not avisos.es_aviso_con_datos("mis coordenadas son 10.9, -74.7")
        and not avisos.es_aviso_con_datos("[El cliente envio una foto]")
        and not avisos.es_aviso_con_datos(None),
        "lo que escribe el cliente, o una foto, sigue siendo una pregunta")

# Que el motor lo use donde decide buscar: se mira la fuente porque recorrer
# motor.responder exige montar el turno entero. Si alguien saca la condicion,
# las coordenadas vuelven a ir al proveedor de embeddings.
import inspect                                            # noqa: E402
fuente = inspect.getsource(motor)
# La del TURNO, que busca con el mensaje del cliente; la otra llamada a
# recuperar() es la herramienta de documentacion, que busca con la consulta
# que arma el modelo.
i = fuente.index("nombre_rol, mensaje)")
revisar("avisos.es_aviso_con_datos(mensaje)" in fuente[max(0, i - 900):i],
        "el motor no llama a recuperar() con un aviso del canal")


print()
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("Todo en verde.")
