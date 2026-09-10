# -*- coding: utf-8 -*-
"""
================================================================================
 LOS PASOS DE SINTONIZACION NO SE ESCRIBEN DE MEMORIA
================================================================================

EL FALLO QUE REPRODUCE, tal como se midio el 10/09/2026
-------------------------------------------------------
Mensaje: "no me aparecen los canales en el tv, es un Samsung y el cable
coaxial entra directo al televisor". Tres corridas del MISMO mensaje contra
el motor real, con la guia de Samsung cargada:

    corrida 1: consulto la guia
    corrida 2: NO consulto -- escribio los pasos de memoria
    corrida 3: NO consulto -- escribio los pasos de memoria

Lo que entrego sin consultar: "entra al menu, busca la opcion de Canales o
Emisoras y elige Sintonizacion automatica". Suena bien. Por eso el fallo no
se ve leyendo la respuesta -- solo en la traza.

Con 'Kalley' (marca que no reconoce) y con TDT consulto 3 de 3. La diferencia
no es el flujo: una marca famosa lo convence de que ya sabe, y solo busca la
herramienta cuando se siente ignorante.

La instruccion de no hacerlo estaba escrita CUATRO veces (tres en el prompt
del rol, una en la descripcion de la herramienta, en mayusculas). PRD 7.4:
el prompt guia, el codigo garantiza. Esta guarda es la garantia.

POR QUE ESTA PRUEBA NO LLAMA AL MODELO
--------------------------------------
Correr el caso real tres veces tarda minutos, necesita red, y prueba con una
moneda: la corrida 1 de la medicion PASABA. Un test asi entra en verde con el
sintoma vivo, que es exactamente el error que este proyecto ya cometio y dejo
anotado en CLAUDE.md ("una prueba que afirma que un mecanismo EXISTE no
prueba que funcione").

Aca el modelo se sustituye por un doble que hace, a proposito, lo que hizo el
real: improvisar los pasos sin llamar la herramienta. Deja de ser una moneda
y pasa a ser una afirmacion sobre el EFECTO -- si el motor le deja entregar
ese texto al cliente, falla siempre; si lo obliga a consultar, pasa siempre.

    py -3.13 tests/test_guia_tv_obligatoria.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config
from nucleo.config.schema import GuiaTV
from nucleo.modelo import cliente, motor
from nucleo.seguridad.verificacion import Sesion

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


# El texto EXACTO que el modelo real entrego sin haber consultado nada
# (corridas 2 y 3 de la medicion). No es un ejemplo inventado para que la
# guarda lo cace: es la evidencia.
IMPROVISADO = (
    "Del lado nuestro la señal de TV sale bien, así que el tema está en la "
    "casa. Vamos a sintonizar tu Samsung: entra al menú, busca la opción de "
    "Canales o Emisoras y elige Sintonización automática (o Búsqueda "
    "automática).\n\n¿La encuentras?")

# La pregunta que el agente DEBE poder hacer sin que la guarda lo frene:
# sin saber como esta conectado no hay guia que elegir, asi que preguntarlo
# es el paso correcto, no un desliz.
PREGUNTA_CONEXION = (
    "¿El cable coaxial entra directo al televisor o pasa antes por una "
    "cajita (TDT)?")


GUIAS = [
    GuiaTV(marca="Samsung", tipo_conexion="directo",
           instrucciones="Menu > Todos los ajustes > Emision > "
                         "Sintonizacion automatica > ANTENA.",
           url_video="https://videos.rapilink.co/samsung"),
    GuiaTV(marca="", tipo_conexion="directo",
           instrucciones="Busca sintonizacion automatica de canales y "
                         "elegi ANTENA."),
    GuiaTV(marca="", tipo_conexion="tdt",
           instrucciones="Enciende el TDT, poné el TV en HDMI 1 y corré la "
                         "busqueda de canales del TDT."),
]

# El YAML real y no una config minima: una hecha a mano se cae por campos que
# no tienen nada que ver con lo que se mide, y arreglarla termina en un test
# que pasa sin probar. (Paso el 10/09/2026 con este mismo archivo.)
BASE = cargar_config(str(RAIZ / "tenants" / "rapilink.config.yaml"))
CON_GUIAS = BASE.model_copy(update={"guias_tv": GUIAS})
SIN_GUIAS = BASE.model_copy(update={"guias_tv": []})

ROL = "soporte_tecnico_cliente"


def sesion_nueva() -> Sesion:
    return Sesion(verificado=True, nivel=1, id_cliente="5832",
                  nombre="CLIENTE DE PRUEBA", sn_onu="AAAA00000000",
                  identificador_canal="3001234567")


class ModeloGuionado:
    """
    Un doble del modelo que responde un guion fijo, turno por turno.

    Cada entrada del guion es (texto, [(herramienta, argumentos), ...]).
    Cuando el guion se agota devuelve la ultima entrada para siempre: asi un
    modelo que se empeña en improvisar se comporta como el real -- insiste--
    en vez de quedarse sin respuestas y falsear el resultado.
    """

    def __init__(self, guion: list[tuple[str, list]]):
        self.guion = guion
        self.turnos: list[str] = []
        self.sistemas: list[str] = []

    def __call__(self, referencia_modelo, mensajes, tools=None,
                 temperatura=0.1, timeout=None, **resto):
        # Lo que el motor le fue diciendo entre vuelta y vuelta. Es donde se
        # ve si la guarda le pidio consultar, y con que palabras.
        self.sistemas = [m["content"] for m in mensajes
                         if m.get("role") == "system"]
        i = min(len(self.turnos), len(self.guion) - 1)
        texto, llamadas = self.guion[i]
        self.turnos.append(texto)
        # 'tools=None' es la redaccion final, no una vuelta del bucle: ahi el
        # catalogo ya esta apagado y pedir herramientas no tendria sentido.
        if tools is None:
            return cliente.Respuesta(contenido=texto, llamadas=[])
        return cliente.Respuesta(
            contenido=texto,
            llamadas=[cliente.Llamada(nombre=n, argumentos=a)
                      for n, a in llamadas])


def correr(guion, config=CON_GUIAS, mensaje="no me aparecen los canales en "
                                            "el tv, es un Samsung y el cable "
                                            "coaxial entra directo al televisor"):
    """Un turno completo con el modelo guionado. Devuelve (respuesta, traza, doble)."""
    doble = ModeloGuionado(guion)
    original = motor.cliente.chat
    # El rol tiene 'cargar_habilidad', asi que el motor arma el indice de
    # habilidades y eso SI va a la base. Es lo unico de este turno que la
    # necesita, y no tiene nada que ver con lo que se mide -- sin devolverlo
    # vacio, la prueba exigiria red y credenciales para comprobar una regla
    # que es puro codigo.
    indice_original = motor.catalogo_habilidades.indice_de
    motor.cliente.chat = doble
    motor.catalogo_habilidades.indice_de = lambda *a, **k: []
    try:
        respuesta, registro, _ = motor.responder(
            config, ROL, mensaje, [], sesion_nueva())
    finally:
        motor.cliente.chat = original
        motor.catalogo_habilidades.indice_de = indice_original
    return respuesta, [r["herramienta"] for r in registro], doble


print("=" * 74)
print(" LA GUIA DE SINTONIZACION ES OBLIGATORIA  --  no se contesta de memoria")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. el detector separa dictar un paso de preguntar como esta conectado ==")

comprobar(motor._da_pasos_de_sintonizacion(IMPROVISADO),
          "el texto improvisado que se midio en vivo se detecta")
comprobar(not motor._da_pasos_de_sintonizacion(PREGUNTA_CONEXION),
          "la pregunta obligatoria por la conexion NO se detecta -- "
          "frenarla haria girar el turno cuando el agente hace lo correcto")
comprobar(not motor._da_pasos_de_sintonizacion(
              "Ya quedó activada la televisión. ¿El cable entra directo al "
              "TV o pasa por una cajita?"),
          "avisar que hay que sintonizar, sin decir como, tampoco se detecta")
comprobar(not motor._da_pasos_de_sintonizacion(
              "Entra al menú de tu router y busca la opción de WiFi."),
          "una ruta de menu que no es de television no se detecta")
comprobar(motor._da_pasos_de_sintonizacion(
              "Encendé el TDT y poné el televisor en HDMI 1."),
          "los pasos de TDT tambien se detectan")

# ---------------------------------------------------------------------------
print("\n== 2. TV directo + marca REGISTRADA: el fallo medido, ya no pasa ==")

# Turno 1: exactamente lo que hizo el modelo real -- improvisa sin llamar
# nada. Turno 2 en adelante: cede y consulta.
respuesta, traza, doble = correr([
    (IMPROVISADO, []),
    ("", [("consultar_guia_sintonizacion",
           {"tipo_conexion": "directo", "marca": "Samsung"})]),
    ("Probá esto: Menu > Todos los ajustes > Emision > Sintonizacion "
     "automatica > ANTENA.", []),
])

comprobar("consultar_guia_sintonizacion" in traza,
          "el motor lo OBLIGO a consultar la guia -- antes del cambio esta "
          "traza salia vacia y el cliente recibia los pasos inventados")
comprobar(len(doble.turnos) > 1,
          "no se dio por terminado con la primera respuesta")
# Se afirma contra el texto PROPIO de la guarda y no contra "algun mensaje de
# sistema que hable de sintonizacion": el prompt del rol ya habla de eso y ya
# nombra la herramienta, asi que la version floja pasaba con la guarda
# apagada. Comprobado apagandola: dos de estas comprobaciones seguian en
# verde. Afirmar sobre el efecto, nunca sobre la presencia del mecanismo.
reclamo = [s for s in doble.sistemas if "NO escribas pasos" in s]
comprobar(len(reclamo) == 1,
          "se le dijo, una sola vez, que no escriba pasos todavia")
comprobar(bool(reclamo) and "consultar_guia_sintonizacion" in reclamo[0],
          "y ese mismo reclamo le nombra la herramienta que tiene que usar")
comprobar(bool(reclamo) and "preguntale" in reclamo[0],
          "y le da la salida honesta si no sabe como esta conectado: "
          "preguntar, no inventar")

# ---------------------------------------------------------------------------
print("\n== 3. el que ya consulto no paga nada ==")

respuesta, traza, doble = correr([
    ("", [("consultar_guia_sintonizacion",
           {"tipo_conexion": "directo", "marca": "Samsung"})]),
    ("Probá esto: Menu > Todos los ajustes > Emision > Sintonizacion "
     "automatica > ANTENA.", []),
])

comprobar(traza.count("consultar_guia_sintonizacion") == 1,
          "consulto una sola vez: la guarda no lo hace repetir")
comprobar(not any("NO escribas pasos" in s for s in doble.sistemas),
          "y no se le reclamo nada -- un turno correcto no cuesta vueltas")

# ---------------------------------------------------------------------------
print("\n== 4. TV directo + marca DESCONOCIDA: tambien obliga (cae a la general) ==")

respuesta, traza, doble = correr(
    [(IMPROVISADO.replace("Samsung", "Kalley"), []),
     ("", [("consultar_guia_sintonizacion",
            {"tipo_conexion": "directo", "marca": "Kalley"})]),
     ("Buscá sintonizacion automatica de canales y elegi ANTENA.", [])],
    mensaje="no me aparecen los canales, el tv es un Kalley y el cable entra "
            "directo al televisor")

comprobar("consultar_guia_sintonizacion" in traza,
          "una marca sin guia propia tambien tiene que pasar por la "
          "herramienta: la general la elige el codigo, no el modelo")

# ---------------------------------------------------------------------------
print("\n== 5. TV + TDT: obliga igual, y ahi la marca no interviene ==")

respuesta, traza, doble = correr(
    [("Encendé el TDT y poné el televisor en HDMI 1, después buscá los "
      "canales.", []),
     ("", [("consultar_guia_sintonizacion", {"tipo_conexion": "tdt"})]),
     ("Encendé el TDT, poné el TV en HDMI 1 y corré la busqueda del TDT.", [])],
    mensaje="no me aparecen los canales, el coaxial va a una cajita y de ahi "
            "al televisor")

comprobar("consultar_guia_sintonizacion" in traza,
          "los pasos de TDT tampoco salen de la memoria del modelo")

# ---------------------------------------------------------------------------
print("\n== 6. una llamada que se pierde no habilita a seguir de memoria ==")

# El otro modo de falla, visto el 10/09/2026: DeepSeek escribio la llamada
# como texto con sus tokens de control en vez de usar el tool-calling
# ('crudo=<...invoke name="consultar_guia_sinto'). Esa no se puede rescatar
# --'_llamadas_fugadas' solo recupera herramientas SIN argumentos, y esta
# necesita 'tipo_conexion'-- asi que la intencion se pierde entera. Si el
# motor lo dejara pasar, el turno sigue y los pasos salen igual de la memoria.
respuesta, traza, doble = correr([
    ('<｜｜DSML｜｜invoke name="consultar_guia_sintonizacion">', []),
    (IMPROVISADO, []),
    ("", [("consultar_guia_sintonizacion",
           {"tipo_conexion": "directo", "marca": "Samsung"})]),
    ("Probá esto: Menu > Todos los ajustes > Emision > Sintonizacion "
     "automatica > ANTENA.", []),
])

comprobar("consultar_guia_sintonizacion" in traza,
          "tras perderse la llamada malformada, igual termino consultando")

# ---------------------------------------------------------------------------
print("\n== 7. una consulta a medias NO cuenta como consultada ==")

# Sin 'tipo_conexion' la herramienta contesta "preguntale como esta
# conectado" y no trae ni un paso. Darla por buena dejaria la puerta abierta
# justo despues: la traza diria que consulto y el texto seguiria inventado.
respuesta, traza, doble = correr([
    ("", [("consultar_guia_sintonizacion", {"marca": "Samsung"})]),
    (IMPROVISADO, []),
    ("", [("consultar_guia_sintonizacion",
           {"tipo_conexion": "directo", "marca": "Samsung"})]),
    ("Probá esto: Menu > Todos los ajustes > Emision > Sintonizacion "
     "automatica > ANTENA.", []),
])

comprobar(traza.count("consultar_guia_sintonizacion") == 2,
          "la llamada sin 'tipo_conexion' no lo libero: tuvo que volver "
          "con la conexion puesta")

# ---------------------------------------------------------------------------
print("\n== 8. sin guia cargada sigue siendo fail-closed ==")

# El catalogo vacio no habilita a inventar: la herramienta devuelve el aviso
# de _sin_guia, que no es una guia. Lo que NO puede pasar es que el turno se
# cuelgue -- la guarda tiene tope y despues deja seguir.
respuesta, traza, doble = correr([
    ("", [("consultar_guia_sintonizacion",
           {"tipo_conexion": "directo", "marca": "Samsung"})]),
    (IMPROVISADO, []),
], config=SIN_GUIAS)

comprobar(bool(respuesta),
          "el turno termina igual: la guarda tiene tope, no gira sola")
comprobar(any("NO inventes" in s or "NO escribas pasos" in s
              for s in doble.sistemas),
          "y se le insistio que sin guia cargada no hay pasos que dar")

# ---------------------------------------------------------------------------
print("\n== 9. la guarda no le aplica a un rol que no atiende television ==")

comprobar(all(not getattr(h, "consulta_guias_tv", False)
              for h in BASE.roles["facturacion_cliente"].puede_consultar
              if hasattr(h, "consulta_guias_tv")),
          "facturacion no tiene la herramienta de guias en su catalogo")

herramientas_tv = [h.nombre for h in BASE.herramientas
                   if getattr(h, "consulta_guias_tv", False)]
comprobar(len(herramientas_tv) == 1,
          f"hay una sola herramienta marcada 'consulta_guias_tv' "
          f"({', '.join(herramientas_tv) or 'ninguna'}) -- si aparecieran "
          f"dos, la guarda tomaria la primera y el mensaje nombraria la "
          f"que no es")

# ---------------------------------------------------------------------------
print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print("[OK] Los pasos de sintonizacion salen del catalogo o no salen.")
