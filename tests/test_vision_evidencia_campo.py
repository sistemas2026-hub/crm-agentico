# -*- coding: utf-8 -*-
"""
================================================================================
 LA FOTO DE EVIDENCIA SE MIRA DISTINTO QUE LA DEL CLIENTE  --  31/10/2026
================================================================================

    py -3.13 tests/test_vision_evidencia_campo.py

QUE SE CAMBIO
-------------
`vision.INSTRUCCION` era una constante del modulo. Para mirar una foto de
evidencia de campo hace falta pedir justo lo que sus reglas 3 y 4 PROHIBEN
--si algo quedo mal instalado-- y eso es correcto para el canal del cliente:
quien lee alla es el cliente, y una foto no muestra un equipo danado.

La salida facil habria sido un segundo modulo que vuelva a hablarle al
proveedor. Eso es la historia del reloj escrito dos veces (CLAUDE.md §6): hay
UN solo sitio que manda imagenes, con sus garantias, y lo que cambia es que
se le pide. Por eso la instruccion es un PARAMETRO.

QUE SE AFIRMA, Y POR QUE ASI
-----------------------------
Sobre el EFECTO: que mensaje se arma, cual instruccion viaja, y que los topes
corren igual para las dos. Afirmar que la constante `INSTRUCCION_EVIDENCIA`
existe no probaria nada -- una constante que nadie pasa al modelo se ve igual
de bien en el diff.

NO SE LLAMA A NINGUNA API NI AL MODELO: todo es armado de mensajes y las
guardas que corren antes de la red.
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import vision                                # noqa: E402

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


#: Un JPEG minimo: basta la firma para pasar `es_imagen`.
JPEG = bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * 64
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 64

print("=" * 72)
print(" LA FOTO DE EVIDENCIA SE MIRA DISTINTO  (sin red, sin modelo)")
print("=" * 72)

# =============================================================================
print("\n-- A: sin instruccion, sigue siendo la de siempre --")
# =============================================================================
#  El canal del cliente no cambio. Si esto se rompiera, el cambio habria
#  tocado WhatsApp sin que nadie lo pidiera.
m = vision.mensaje_multimodal(JPEG)
comprobar("A1. el system es la instruccion de WhatsApp",
          m[0]["content"] == vision.INSTRUCCION)
comprobar("A2. y sigue prohibiendo decir que algo esta mal instalado",
          "NO afirmes que algo esta danado" in m[0]["content"])

# =============================================================================
print("\n-- B: con la de evidencia, se pide lo contrario --")
# =============================================================================
m = vision.mensaje_multimodal(JPEG, instruccion=vision.INSTRUCCION_EVIDENCIA)
comprobar("B1. el system es la de evidencia",
          m[0]["content"] == vision.INSTRUCCION_EVIDENCIA)
comprobar("B2. y SI pide decir lo que se ve del trabajo",
          "cables sueltos" in m[0]["content"])
comprobar("B3. pero sigue sin poder afirmar que el servicio funciona",
          "NO digas si el servicio funciona" in m[0]["content"])
comprobar("B4. ni inventar una medicion",
          "potencia optica" in m[0]["content"])
comprobar("B5. ni transcribir documentos",
          "cedulas" in m[0]["content"])

# =============================================================================
print("\n-- C: las dos son distintas de verdad --")
# =============================================================================
#  Si alguien hiciera INSTRUCCION_EVIDENCIA = INSTRUCCION para 'simplificar',
#  todo lo de arriba seguiria pasando menos esto.
comprobar("C1. no son el mismo texto",
          vision.INSTRUCCION_EVIDENCIA != vision.INSTRUCCION)

# =============================================================================
print("\n-- D: lo que la foto tenia que mostrar viaja como pie --")
# =============================================================================
m = vision.mensaje_multimodal(
    JPEG, pie="Esta foto tenia que mostrar: la ONT instalada.",
    instruccion=vision.INSTRUCCION_EVIDENCIA)
partes = m[1]["content"]
comprobar("D1. el pie va antes de la imagen", partes[0]["type"] == "text")
comprobar("D2. y lleva lo que la plantilla pedia",
          "la ONT instalada" in partes[0]["text"])
comprobar("D3. la imagen va como data URL",
          partes[-1]["type"] == "image_url"
          and partes[-1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

m = vision.mensaje_multimodal(PNG, instruccion=vision.INSTRUCCION_EVIDENCIA)
comprobar("D4. un PNG se manda como PNG",
          m[1]["content"][-1]["image_url"]["url"].startswith("data:image/png;base64,"))

# =============================================================================
print("\n-- E: los topes corren igual con la instruccion nueva --")
# =============================================================================
#  La instruccion cambia QUE se pide, no las garantias. Si alguna de estas
#  dejara de correr, la ruta de campo seria la puerta sin control.
r = vision.analizar(b"", "deepseek:x", instruccion=vision.INSTRUCCION_EVIDENCIA)
comprobar("E1. una imagen vacia no sale", r.estado == vision.ERROR, r.error)

r = vision.analizar(b"\x00" * (vision.MAX_BYTES + 1), "deepseek:x",
                    instruccion=vision.INSTRUCCION_EVIDENCIA)
comprobar("E2. una que se pasa del tope no sale", r.estado == vision.ERROR)
comprobar("E3. y el motivo lo dice", "maximo" in r.error, r.error)

r = vision.analizar(b"GIF89a" + b"\x00" * 64, "deepseek:x",
                    instruccion=vision.INSTRUCCION_EVIDENCIA)
comprobar("E4. un formato que no es JPEG ni PNG no sale",
          r.estado == vision.ERROR and "JPEG" in r.error, r.error)

r = vision.analizar(JPEG, "", instruccion=vision.INSTRUCCION_EVIDENCIA)
comprobar("E5. sin modelo configurado no sale", r.estado == vision.ERROR, r.error)

# =============================================================================
print("\n-- F: la instruccion llega HASTA EL MODELO, no solo al armador --")
# =============================================================================
#  SIN ESTA SECCION LA PRUEBA ERA UN FALSO VERDE, y se descubrio mutando:
#  quitarle `instruccion` a la llamada que `analizar()` le hace a
#  `mensaje_multimodal` dejaba todo lo de arriba en verde. B y D prueban el
#  ARMADOR; esto prueba el CAMINO -- que es lo que de verdad corre.
class _Respuesta:
    contenido = "Se ve una ONT con la luz PON fija."
    tokens_entrada = 10
    tokens_salida = 5


capturado: dict = {}


def _chat_falso(modelo, mensajes, **kw):
    capturado["modelo"] = modelo
    capturado["mensajes"] = mensajes
    return _Respuesta()


from nucleo.modelo import cliente as _cliente                     # noqa: E402

_original = _cliente.chat
_cliente.chat = _chat_falso
try:
    r = vision.analizar(JPEG, "deepseek:x", pie="Tenia que mostrar la ONT.",
                        instruccion=vision.INSTRUCCION_EVIDENCIA)
    system_de_evidencia = capturado.get("mensajes", [{}])[0].get("content")
    comprobar("F1. el analisis salio bien", r.ok, f"{r.estado} {r.error}")
    comprobar("F2. y al modelo le llego la instruccion de EVIDENCIA",
              system_de_evidencia == vision.INSTRUCCION_EVIDENCIA,
              str(system_de_evidencia)[:60])

    capturado.clear()
    vision.analizar(JPEG, "deepseek:x")
    system_por_defecto = capturado.get("mensajes", [{}])[0].get("content")
    comprobar("F3. y sin pedirla, le llega la de WhatsApp",
              system_por_defecto == vision.INSTRUCCION,
              str(system_por_defecto)[:60])
finally:
    _cliente.chat = _original

# =============================================================================
print("\n-- G: el rotulo del pie dice de quien es  (revisor de PII, H5) --")
# =============================================================================
#  El rotulo era constante: al proveedor le llegaba "El cliente escribio junto
#  a la foto: Esta foto tenia que mostrar la ONT", que es falso --lo escribio
#  un empleado en la plantilla-- y mueve el analisis, porque el modelo no
#  trata igual una frase del cliente que una instruccion de la oficina.
m = vision.mensaje_multimodal(JPEG, pie="la ONT instalada",
                              instruccion=vision.INSTRUCCION_EVIDENCIA,
                              rotulo_del_pie=vision.PIE_DE_LA_PLANTILLA)
texto_del_pie = m[1]["content"][0]["text"]
comprobar("G1. NO se le atribuye al cliente",
          "El cliente escribio" not in texto_del_pie, texto_del_pie[:60])
comprobar("G2. dice que es lo que la empresa pedia",
          texto_del_pie.startswith(vision.PIE_DE_LA_PLANTILLA), texto_del_pie[:60])

m = vision.mensaje_multimodal(JPEG, pie="mira la luz roja")
comprobar("G3. y sin rotulo sigue siendo el del cliente",
          m[1]["content"][0]["text"].startswith(vision.PIE_DEL_CLIENTE))

# =============================================================================
print("\n-- H: lo que la instruccion de evidencia NO puede perder --")
# =============================================================================
#  La de WhatsApp acota la foto fuera de tema ("deci en una linea que se ve y
#  nada mas"). Al escribir la de evidencia esa regla se habia perdido, y sus
#  reglas 1 y 4 piden describir: una foto donde entra una persona o un recibo
#  se describia entera, y eso queda guardado para siempre (revisor de PII,
#  H4). Estas dos afirmaciones existen para que no se pierda otra vez.
comprobar("H1. acota la foto que no muestra nada de telecomunicaciones",
          "no muestra equipos, cables ni red de telecomunicaciones"
          in vision.INSTRUCCION_EVIDENCIA
          and "nada mas. No describas el resto" in vision.INSTRUCCION_EVIDENCIA)
comprobar("H2. y prohibe describir personas, direcciones y papeles",
          "describas a las personas" in vision.INSTRUCCION_EVIDENCIA
          and "placas" in vision.INSTRUCCION_EVIDENCIA)

# =============================================================================
print("\n-- I: la foto del DAÑO no se rechaza por mostrar un daño --")
# =============================================================================
#  20/11/2026. El usuario: cada foto nueva del daño encontrado que el modelo
#  «no habia visto» se rechazaba. La instruccion solo nombraba equipos de
#  ADENTRO de la casa, mandaba a «no se ve lo que se pedia» todo lo que no
#  fuera «equipos ni una instalacion» --un cable partido en un poste no es
#  ninguna de las dos-- y pedia ATENCION por «material deteriorado», que es
#  exactamente lo que una foto del daño tiene que mostrar.
#
#  ESTAS GUARDAS MIDEN QUE LA REGLA LLEGA AL MODELO, NO QUE EL MODELO LA
#  CUMPLA. La seccion F ya prueba que el system que sale ES esta constante;
#  la conducta se mide con fotos reales (`comparar_calidad_vision`).
_I = vision.INSTRUCCION_EVIDENCIA
_i_bajo = _I.lower()
_i11 = _i_bajo.find("11. ")
_i12 = _i_bajo.find("12. ")
_i13 = _i_bajo.find("13. ")
comprobar("I1. la red de AFUERA tambien es del oficio",
          all(p in _i_bajo[:_i11] for p in
              ("acometida", "caja nap", "poste", "empalme")))
comprobar("I2. cuando se pide un daño, lo roto es la foto correcta",
          "la foto correcta es la de algo roto" in _i_bajo[:_i11])
comprobar("I3. y vale el daño que no esta en la lista",
          "aunque sea de un tipo que no este en esta lista" in _i_bajo[:_i11])
comprobar("I4. el daño pedido NO levanta atencion",
          "el daño que se ve no es motivo de atencion" in _i_bajo[_i11:_i12],
          "la excepcion tiene que vivir DENTRO de la regla 11")
comprobar("I5. pero la foto que no sirve la sigue levantando",
          "no muestra nada de telecomunicaciones" in _i_bajo[_i11:_i12])
comprobar("I6. MUESTRA: no queda solo para lo que no es del oficio",
          "queda solo para la imagen que no tiene nada de "
          "telecomunicaciones" in _i_bajo[_i12:_i13])
comprobar("I7. la falla que no se nota por fuera tambien sirve",
          "hay fallas que no se notan por fuera" in _i_bajo[:_i11])

# =============================================================================
print("\n-- J: una captura no frena la orden por ser captura --")
# =============================================================================
#  20/11/2026. El usuario: «el supervisor no puede detener una orden solo por
#  ser captura». ATENCION: si deja el veredicto en REVISAR y MUESTRA: no le
#  devuelve la orden al tecnico: las dos frenan, asi que la regla tiene que
#  estar en las DOS lineas. Igual que la seccion I: mide que la regla llega al
#  modelo, no que el modelo la cumpla.
comprobar("J1. ser captura no levanta atencion",
          "una captura de pantalla no es motivo de atencion por ser captura"
          in _i_bajo[_i11:_i12],
          "tiene que vivir DENTRO de la regla 11")
comprobar("J2. se juzga lo que la captura muestra",
          "juzgá lo que muestra igual que a cualquier foto"
          in _i_bajo[_i11:_i12])
comprobar("J3. y la captura que no sirve la sigue levantando",
          "si lo que la captura muestra no sirve como evidencia"
          in _i_bajo[_i11:_i12])
comprobar("J4. ser captura tampoco la vuelve MUESTRA: no",
          "tampoco la vuelve 'muestra: no'" in _i_bajo[_i12:_i13]
          and "si en la captura se ve lo que se pedia, es 'muestra: si'"
          in _i_bajo[_i12:_i13],
          "tiene que vivir DENTRO de la regla 12")

print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLAS:")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
sys.exit(0)
