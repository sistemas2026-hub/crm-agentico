# -*- coding: utf-8 -*-
"""
================================================================================
 LA IA MIRA LA FOTO  --  y todas las formas de que eso no haga daño
================================================================================

    py -3.13 tests/test_vision_imagen.py

CORRE SIN RED Y SIN CLAVE. Se sustituye la RESPUESTA del modelo, nunca la
logica: el camino del codigo es el real.

QUE CAMBIO, Y POR QUE ESTAS PRUEBAS SON OTRAS
----------------------------------------------
La primera version de vision.py usaba OpenAI con un catalogo cerrado: el
modelo elegia de una lista y lo que no estaba en ella se descartaba en
codigo. Eso se midio contra las dos APIs reales el 02/10/2026 y se cambio:

  - la OPENAI_API_KEY de la casa no tiene alcance para chat.completions
    (401 missing_scope), asi que esa via no arrancaba;
  - DeepSeek SI acepta imagenes (8.0 s, describe bien) pero NO acepta
    json_schema ni strict (400 'This response_format type is unavailable
    now'), y con json_object tardo 26.2 s para devolver listas vacias.

Asi que ahora es DeepSeek, el MISMO modelo que conversa, y la salida es
TEXTO LIBRE. Se gano un proveedor menos y una llamada que funciona; se
perdio la garantia estructural.

LO QUE SE VIGILA, EN ORDEN DE DAÑO
-----------------------------------
  1. Que el base64 de la imagen NO llegue al historial, ni a la base, ni al
     log, ni al texto del agente. Es lo unico que puede ensuciar una
     conversacion entera y multiplicar el costo de cada turno siguiente.
  2. Que la imagen se mande UNA vez y no vuelva en los turnos siguientes.
  3. Que un fallo NO produzca texto y el cliente igual reciba respuesta.
  4. Que lo que el modelo escriba pase por redaccion.py antes de persistirse.
     Es la unica defensa que queda sin catalogo, y no alcanza para todo --
     por eso se prueba exactamente lo que si cubre.
  5. Que el texto y el audio, que ya andaban, sigan andando igual.
================================================================================
"""

import contextlib as _ctx
import io as _io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import vision as vi

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


class _Parche:
    """monkeypatch sin pytest. Repone el original pase lo que pase."""

    def __init__(self, obj, nombre, valor):
        self.obj, self.nombre, self.previo = obj, nombre, getattr(obj, nombre)
        setattr(obj, nombre, valor)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        setattr(self.obj, self.nombre, self.previo)
        return False


def _cuerpo_de(fuente: str, nombre: str) -> str:
    """
    El texto de UNA funcion.

    Comparar posiciones dentro de 9.000 lineas no sirve: 'atender_turno' se
    llama en tres sitios y el primero esta en otra funcion, mil lineas antes
    -- una comprobacion de orden escrita asi daba rojo por eso.
    """
    desde = fuente.index(f"def {nombre}(")
    resto = fuente[desde + 1:]
    siguiente = resto.find("\ndef ")
    return resto[:siguiente] if siguiente != -1 else resto


#  Un JPEG minimo: la firma y relleno. No es una imagen que se pueda abrir, y
#  no hace falta -- lo que se prueba es que el codigo la RECONOZCA como JPEG.
JPEG = bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * 120
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 120
NO_IMAGEN = b"RIFF" + b"\x00" * 120

MODELO = "deepseek:deepseek-v4-flash"

#  Lo que DeepSeek contesto DE VERDAD mirando la ONT sintetica, el 02/10/2026.
#  Se usa su forma, no una inventada, para que las pruebas midan contra lo
#  que el modelo realmente escribe.
RESPUESTA_ONT = (
    "Se ve un equipo de red tipo ONT con cinco luces indicadoras rotuladas "
    "POWER, PON, LOS, LAN y WIFI. POWER, PON y LAN estan en verde; LOS esta "
    "en rojo; WIFI aparece apagada. Debajo hay dos puertos ethernet "
    "rotulados LAN1 y LAN2, un conector verde rotulado PON y una etiqueta. "
    "La luz LOS encendida suele asociarse a perdida de senal optica, pero la "
    "foto no permite confirmar la causa ni el estado del servicio."
)


class _RespuestaFalsa:
    """Lo que devuelve cliente.chat(), con la forma de modelo.cliente.Respuesta."""

    def __init__(self, contenido="", entrada=1100, salida=160):
        self.contenido = contenido
        self.llamadas = []
        self.tokens_entrada = entrada
        self.tokens_salida = salida


def _chat_que(devuelve="", levanta=None, registro=None):
    """Un cliente.chat de mentira. Guarda lo que se le mando."""
    def _chat(modelo, mensajes, tools=None, temperatura=0.1,
              timeout=None, razonamiento=None, **kw):
        if registro is not None:
            registro.append({"modelo": modelo, "mensajes": mensajes,
                             "timeout": timeout, "temperatura": temperatura})
        if levanta:
            raise levanta
        return _RespuestaFalsa(devuelve)
    return _chat


def _con_modelo(fn):
    """Mete el chat falso donde analizar() hace su import perezoso."""
    from nucleo.modelo import cliente
    return _Parche(cliente, "chat", fn)


print(__doc__)

# =============================================================================
print("\n1. EL FORMATO QUE SE LE MANDA AL MODELO")
# =============================================================================

msgs = vi.mensaje_multimodal(JPEG, "Mira como esta mi modem")
comprobar("son dos mensajes: la instruccion y el del cliente", len(msgs) == 2)
comprobar("el primero es el system con la instruccion",
          msgs[0]["role"] == "system" and msgs[0]["content"] == vi.INSTRUCCION)
comprobar("el segundo es del usuario", msgs[1]["role"] == "user")
comprobar("y su content es una LISTA (multimodal), no una cadena",
          isinstance(msgs[1]["content"], list))

partes = msgs[1]["content"]
tipos = [p["type"] for p in partes]
comprobar("con el pie del cliente como texto", "text" in tipos)
comprobar("y la imagen como image_url", "image_url" in tipos)
comprobar("el pie va ANTES de la imagen", tipos.index("text") < tipos.index("image_url"))

url = [p for p in partes if p["type"] == "image_url"][0]["image_url"]["url"]
comprobar("la imagen viaja como data URL en base64",
          url.startswith("data:image/jpeg;base64,"))
comprobar("un PNG se declara como PNG, por su firma y no por lo que digan",
          vi.mensaje_multimodal(PNG)[1]["content"][0]["image_url"]["url"]
          .startswith("data:image/png;base64,"))

comprobar("el pie del cliente llega rotulado como suyo",
          "El cliente escribio junto a la foto: Mira como esta mi modem"
          in [p.get("text", "") for p in partes])

#  Sin pie no se inventa un texto vacio que el modelo tenga que interpretar.
solo_imagen = vi.mensaje_multimodal(JPEG)[1]["content"]
comprobar("sin pie, va solo la imagen", len(solo_imagen) == 1
          and solo_imagen[0]["type"] == "image_url")

# =============================================================================
print("\n2. UNA SOLA LLAMADA, CON LO QUE CORRESPONDE")
# =============================================================================

enviados = []
with _con_modelo(_chat_que(RESPUESTA_ONT, registro=enviados)):
    r = vi.analizar(JPEG, MODELO, "Mira como esta mi modem")

comprobar("se llamo al modelo UNA sola vez", len(enviados) == 1,
          f"{len(enviados)} llamadas")
comprobar("con el modelo del tenant, no con una constante del archivo",
          enviados[0]["modelo"] == MODELO)
comprobar("con el timeout corto de vision, no el del turno",
          enviados[0]["timeout"] == vi.TIMEOUT_SEGUNDOS)
comprobar("NO se pidio response_format: el endpoint lo rechaza (medido)",
          "response_format" not in str(enviados[0]))
comprobar("el resultado quedo procesado", r.ok and r.estado == vi.PROCESADO)
comprobar("los tokens se suman de entrada y salida", r.tokens == 1260,
          str(r.tokens))
comprobar("queda registrado que modelo lo hizo", r.modelo == MODELO)

# =============================================================================
print("\n3. EL BASE64 NO SALE DE LA LLAMADA  (caso L)")
# =============================================================================

#  El unico lugar donde el base64 puede existir es el mensaje que se manda.
#  Se comprueba contra el PREFIJO del base64 real de la imagen, no contra una
#  cadena inventada: si algun dia se guarda la imagen por otro camino, esto
#  lo encuentra igual.
import base64 as _b64
PREFIJO = _b64.b64encode(JPEG).decode("ascii")[:40]

comprobar("el base64 SI esta en el mensaje que se manda (es su lugar)",
          PREFIJO in str(enviados[0]["mensajes"]))
comprobar("NO esta en el texto del resultado", PREFIJO not in r.texto)
comprobar("NO esta en el texto para el agente",
          PREFIJO not in vi.texto_para_el_agente(r, "Mira como esta mi modem"))
comprobar("NO esta en el error", PREFIJO not in r.error)
comprobar("el Resultado no guarda los bytes de la imagen",
          not any(isinstance(v, bytes) for v in vars(r).values()))

# =============================================================================
print("\n4. LO QUE EL MODELO ESCRIBE PASA POR LA REDACCION")
# =============================================================================

CON_CEDULA = ("Se ve una etiqueta con el documento 1098765432 del titular y "
              "un telefono 3001234567, junto a un router con la luz roja.")
with _con_modelo(_chat_que(CON_CEDULA)):
    r_ced = vi.analizar(JPEG, MODELO)

comprobar("una cedula que el modelo transcribio no sobrevive",
          "1098765432" not in r_ced.texto, r_ced.texto)
comprobar("un telefono tampoco", "3001234567" not in r_ced.texto, r_ced.texto)
comprobar("pero lo util del texto se conserva",
          "router" in r_ced.texto and "luz roja" in r_ced.texto)
comprobar("y lo tapado se ve tapado, no borrado en silencio",
          "oculto" in r_ced.texto.lower(), r_ced.texto)

#  El recorte por largo, para que una divagacion no entre al historial y se
#  pague en cada turno siguiente.
LARGO = "palabra " * 400
with _con_modelo(_chat_que(LARGO)):
    r_largo = vi.analizar(JPEG, MODELO)
comprobar("un texto larguisimo se recorta",
          len(r_largo.texto) <= vi.MAX_CARACTERES + 4,
          f"{len(r_largo.texto)} caracteres")
comprobar("y se marca que fue recortado", r_largo.texto.endswith("..."))

# =============================================================================
print("\n5. EL TEXTO QUE RECIBE EL AGENTE  (casos A, B, C)")
# =============================================================================

#  B) foto + caption
texto = vi.texto_para_el_agente(r, "Mira como esta mi modem")
print("\n  --- foto + caption ---")
print("  " + "\n  ".join(texto.splitlines()))
comprobar("rotulado como foto del cliente",
          texto.startswith("[Foto que envio el cliente]"))
comprobar("el caption llega", "Mira como esta mi modem" in texto)
comprobar("rotulado como escrito por el cliente",
          "[Texto que escribio junto con la imagen]" in texto)
comprobar("el analisis llega rotulado como automatico Y sin verificar",
          "[Analisis automatico de la foto, no verificado]" in texto)
comprobar("lo que escribio la persona va ANTES del analisis",
          texto.index("Mira como esta mi modem")
          < texto.index("[Analisis automatico"))
comprobar("el caption aparece UNA sola vez",
          texto.count("Mira como esta mi modem") == 1)
comprobar("la descripcion del modelo llega entera", r.texto in texto)

#  A) foto + pregunta
texto_a = vi.texto_para_el_agente(r, "Que ves en esta foto?")
comprobar("una pregunta como pie tambien llega",
          "Que ves en esta foto?" in texto_a)

#  C) foto sin caption
texto_c = vi.texto_para_el_agente(r)
comprobar("sin caption no queda un rotulo huerfano",
          "[Texto que escribio" not in texto_c, texto_c)
comprobar("y el analisis igual llega",
          "[Analisis automatico de la foto, no verificado]" in texto_c)

# =============================================================================
print("\n6. UN FALLO NO PRODUCE TEXTO  (caso G)")
# =============================================================================

for etiqueta, entrada in (
        ("una imagen vacia", b""),
        ("algo que no es JPEG ni PNG", NO_IMAGEN),
        ("una imagen gigante", bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * vi.MAX_BYTES),
):
    r_mal = vi.analizar(entrada, MODELO)
    comprobar(f"{etiqueta}: estado error", r_mal.estado == vi.ERROR)
    comprobar(f"{etiqueta}: sin texto para el agente",
              vi.texto_para_el_agente(r_mal) == "")

r_sin_modelo = vi.analizar(JPEG, "")
comprobar("sin modelo configurado: error, no excepcion",
          r_sin_modelo.estado == vi.ERROR)
comprobar("sin modelo: sin texto", vi.texto_para_el_agente(r_sin_modelo) == "")


class _Timeout(Exception):
    pass


with _con_modelo(_chat_que(levanta=_Timeout("el proveedor tardo demasiado"))):
    r_to = vi.analizar(JPEG, MODELO)
comprobar("timeout del proveedor: estado error", r_to.estado == vi.ERROR)
comprobar("timeout: sin texto", vi.texto_para_el_agente(r_to) == "")
comprobar("el error nombra la CLASE, no lo que dijo el proveedor",
          "_Timeout" in r_to.error and "tardo demasiado" not in r_to.error,
          r_to.error)

with _con_modelo(_chat_que("")):
    r_vacio = vi.analizar(JPEG, MODELO)
comprobar("el modelo que contesta nada: procesado pero sin texto",
          r_vacio.estado == vi.PROCESADO and not r_vacio.ok)
comprobar("y no se inventa una descripcion",
          vi.texto_para_el_agente(r_vacio) == "")

# =============================================================================
print("\n7. LAS FIRMAS")
# =============================================================================

comprobar("un JPEG se reconoce", vi.es_imagen(JPEG))
comprobar("un PNG se reconoce", vi.es_imagen(PNG))
comprobar("un RIFF no", not vi.es_imagen(NO_IMAGEN))
comprobar("vacio no", not vi.es_imagen(b""))
comprobar("el mime sale de la firma y no de lo que diga el canal",
          vi._mime_de(PNG) == "image/png" and vi._mime_de(JPEG) == "image/jpeg")

# =============================================================================
print("\n8. LA INSTRUCCION DICE LO QUE TIENE QUE DECIR")
# =============================================================================

#  Sin catalogo cerrado la instruccion es la unica guia, asi que al menos se
#  comprueba que diga las cuatro cosas que importan. Es una prueba DEBIL a
#  proposito --que el prompt lo diga no obliga al modelo-- y esta para que
#  nadie las borre sin darse cuenta.
for etiqueta, aguja in (
        ("no afirmar que algo esta danado", "danado"),
        ("no afirmar si el servicio funciona", "NO digas si el servicio"),
        ("no transcribir documentos", "cedulas"),
        ("distinguir rojo de naranja", "rojo y naranja no son lo mismo"),
):
    comprobar(f"la instruccion pide: {etiqueta}", aguja in vi.INSTRUCCION)

# =============================================================================
print("\n9. EL TURNO  (casos H, I, J, M)")
# =============================================================================

from nucleo.canales import api


class _LLM:
    modelo_por_defecto = MODELO


class _Config:
    def __init__(self, vision_habilitada=True):
        self.vision_habilitada = vision_habilitada
        self.llm = _LLM()


ENTRANTE = {"tipo": "image", "media_id": "wamid.FOTO1", "descripcion": ""}


def _sin_base():
    return lambda tenant, media_id: None


#  --- apagado por tenant: no baja nada y no llama a nadie ---
llamadas = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: llamadas.append("bajada") or (JPEG, "image/jpeg")), \
     _Parche(api.vision, "analizar",
             lambda *a, **k: llamadas.append("analisis")), \
     _Parche(api.persistencia, "analisis_visual_de", _sin_base()):
    salida = api._analizar_si_es_imagen(
        _Config(vision_habilitada=False), "unaempresa", ENTRANTE)
comprobar("vision apagada: sin texto", salida["texto"] == "")
comprobar("vision apagada: NO baja la imagen ni llama al modelo",
          llamadas == [], str(llamadas))

#  --- caso I y J: audio y texto no pasan por vision ---
tocado = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: tocado.append("bajada")), \
     _Parche(api.vision, "analizar", lambda *a, **k: tocado.append("vision")):
    for tipo in ("text", "audio", "voice", "document", "video"):
        s = api._analizar_si_es_imagen(
            _Config(), "unaempresa", dict(ENTRANTE, tipo=tipo))
        comprobar(f"un '{tipo}' no entra por el camino de vision",
                  s["texto"] == "")
comprobar("y por ninguno de esos se bajo ni se analizo nada", tocado == [])

#  --- el camino bueno: una sola descarga ---
veces = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: (veces.append("bajada"), (JPEG, "image/jpeg"))[1]), \
     _Parche(api.media, "preparar", lambda c, t, m: (c, m)), \
     _Parche(api.vision, "analizar",
             lambda *a, **k: (veces.append("analisis"),
                              vi.Resultado(texto=RESPUESTA_ONT,
                                           estado=vi.PROCESADO))[1]), \
     _Parche(api.persistencia, "analisis_visual_de", _sin_base()):
    salida = api._analizar_si_es_imagen(
        _Config(), "unaempresa", dict(ENTRANTE, descripcion="miren la lucecita"))

comprobar("el camino bueno devuelve texto para el agente",
          salida["texto"].startswith("[Foto que envio el cliente]"))
comprobar("la imagen se bajo UNA sola vez", veces.count("bajada") == 1,
          str(veces))
comprobar("vuelven los bytes crudos, para no bajarla de nuevo al guardar",
          salida["crudo"] == JPEG)
comprobar("y la copia ya comprimida, para no comprimirla dos veces",
          salida["listo"] == JPEG)
comprobar("lo que se guarda es la DESCRIPCION, sin el rotulo ni el pie",
          salida["analisis"] == RESPUESTA_ONT)
comprobar("lo guardado no trae el pie del cliente",
          "miren la lucecita" not in salida["analisis"])
comprobar("lo guardado no trae base64", PREFIJO not in salida["analisis"])

#  --- caso H: idempotencia por media_id ---
veces = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: (veces.append("bajada"), (JPEG, "image/jpeg"))[1]), \
     _Parche(api.vision, "analizar",
             lambda *a, **k: (veces.append("analisis"), vi.Resultado())[1]), \
     _Parche(api.persistencia, "analisis_visual_de",
             lambda t, m: {"analisis_visual": RESPUESTA_ONT,
                           "estado_analisis": vi.PROCESADO}):
    salida = api._analizar_si_es_imagen(
        _Config(), "unaempresa", dict(ENTRANTE, descripcion="de nuevo"))

comprobar("un analisis ya hecho se reusa: hay texto igual",
          RESPUESTA_ONT in salida["texto"])
comprobar("reusando NO se vuelve a llamar al modelo", "analisis" not in veces,
          str(veces))
comprobar("reusando NO se vuelve a bajar la imagen", "bajada" not in veces)
comprobar("y el pie NUEVO se arma sobre el analisis viejo",
          "de nuevo" in salida["texto"])
comprobar("sin duplicar el pie", salida["texto"].count("de nuevo") == 1)

#  --- un 'error' guardado SI se reintenta ---
veces = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: (veces.append("bajada"), (JPEG, "image/jpeg"))[1]), \
     _Parche(api.media, "preparar", lambda c, t, m: (c, m)), \
     _Parche(api.vision, "analizar",
             lambda *a, **k: (veces.append("analisis"),
                              vi.Resultado(texto=RESPUESTA_ONT,
                                           estado=vi.PROCESADO))[1]), \
     _Parche(api.persistencia, "analisis_visual_de",
             lambda t, m: {"analisis_visual": None,
                           "estado_analisis": vi.ERROR}):
    salida = api._analizar_si_es_imagen(_Config(), "unaempresa", ENTRANTE)
comprobar("un intento anterior FALLIDO se vuelve a intentar",
          "analisis" in veces, str(veces))

#  --- caso M: la imagen NO vuelve en los turnos siguientes --------------
#
#  Lo que entra al turno es TEXTO. No hay forma de que la imagen vuelva,
#  porque nunca estuvo en el historial -- y eso se afirma sobre el valor
#  que de verdad se le pasa a atender_turno.
comprobar("al turno entra una cadena, no una lista multimodal",
          isinstance(salida["texto"], str))
comprobar("y esa cadena no tiene base64", PREFIJO not in salida["texto"])

fuente_api = Path("nucleo/canales/api.py").read_text(encoding="utf-8")
cuerpo_turno = _cuerpo_de(fuente_api, "_procesar_mensaje_whatsapp")
comprobar("el turno recibe 'texto', que es lo que vision produjo",
          "atender_turno(config, tenant, rol, de, texto" in cuerpo_turno)
comprobar("el analisis corre ANTES del turno",
          cuerpo_turno.index("_analizar_si_es_imagen(config, tenant, entrante)")
          < cuerpo_turno.index("salida = atender_turno("))
comprobar("y el adjunto se guarda DESPUES",
          cuerpo_turno.index("salida = atender_turno(")
          < cuerpo_turno.index("_guardar_adjunto("))
comprobar("nadie mete la imagen en el historial del motor",
          "image_url" not in Path("nucleo/modelo/motor.py").read_text(
              encoding="utf-8"))

#  --- no se pudo bajar / el analisis fallo (caso G, en el turno) ---
def _revienta(*a, **k):
    raise RuntimeError("la base no responde")


with _Parche(api.whatsapp, "descargar_media", _revienta), \
     _Parche(api.persistencia, "analisis_visual_de", _sin_base()):
    salida = api._analizar_si_es_imagen(_Config(), "unaempresa", ENTRANTE)
comprobar("si no se puede bajar: sin texto, sin excepcion",
          salida["texto"] == "" and salida["estado"] == vi.ERROR)

with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: (JPEG, "image/jpeg")), \
     _Parche(api.media, "preparar", lambda c, t, m: (c, m)), \
     _Parche(api.vision, "analizar",
             lambda *a, **k: vi.Resultado(estado=vi.ERROR,
                                          error="el modelo rechazo la imagen (X)")), \
     _Parche(api.persistencia, "analisis_visual_de", _sin_base()):
    salida_rota = api._analizar_si_es_imagen(_Config(), "unaempresa", ENTRANTE)
comprobar("si el analisis falla: sin texto", salida_rota["texto"] == "")
comprobar("si el analisis falla: no se guarda un analisis a medias",
          salida_rota["analisis"] == "")
comprobar("pero el estado y el motivo quedan, para depurar",
          salida_rota["estado"] == vi.ERROR and salida_rota["error"])

#  Y el turno degrada al aviso de siempre.
texto_degradado = (salida_rota.get("texto")
                   or "" or api._AVISO_ADJUNTO.get("image", ""))
comprobar("el cliente recibe el aviso de siempre, no un error tecnico",
          texto_degradado == "[El cliente envio una foto]", texto_degradado)
comprobar("y nunca se le muestra el motivo tecnico",
          "rechazo" not in texto_degradado)

#  --- una config vieja, sin la bandera ---
class _ConfigVieja:
    llm = _LLM()


with _Parche(api.whatsapp, "descargar_media", _revienta), \
     _Parche(api.persistencia, "analisis_visual_de", _sin_base()):
    s = api._analizar_si_es_imagen(_ConfigVieja(), "unaempresa", ENTRANTE)
comprobar("una config sin la bandera se comporta como apagada",
          s["texto"] == "")

# =============================================================================
print("\n10. EL FALLBACK GUARDA LA FOTO IGUAL")
# =============================================================================

guardados = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: (JPEG, "image/jpeg")), \
     _Parche(api.media, "preparar", lambda c, t, m: (c, m)), \
     _Parche(api.persistencia, "guardar_media",
             lambda *a, **k: (guardados.append((a, k)), "fila")[1]):
    api._guardar_adjunto(_Config(False), "unaempresa", ENTRANTE,
                         "conv", "msg", imagen={})
comprobar("vision apagada: la foto se guarda igual", len(guardados) == 1)
if guardados:
    _, kw = guardados[0]
    comprobar("apagada: no se guarda analisis",
              kw.get("analisis_visual") is None)
    comprobar("apagada: el estado queda NULL",
              kw.get("estado_analisis") is None)

guardados = []
with _Parche(api.whatsapp, "descargar_media",
             lambda *a, **k: (JPEG, "image/jpeg")), \
     _Parche(api.media, "preparar", lambda c, t, m: (c, m)), \
     _Parche(api.persistencia, "guardar_media",
             lambda *a, **k: (guardados.append((a, k)), "fila")[1]):
    api._guardar_adjunto(_Config(True), "unaempresa", ENTRANTE,
                         "conv", "msg", imagen=salida_rota)
comprobar("proveedor caido: la foto se guarda igual", len(guardados) == 1)
if guardados:
    args, kw = guardados[0]
    comprobar("proveedor caido: estado_analisis queda en 'error'",
              kw.get("estado_analisis") == vi.ERROR)
    comprobar("proveedor caido: el motivo queda para depurar",
              bool(kw.get("error_analisis")))
    comprobar("proveedor caido: NO se guarda un analisis a medias",
              kw.get("analisis_visual") is None)
    comprobar("los bytes que se guardan son los de la imagen, sin base64",
              any(a == JPEG for a in args))

# =============================================================================
print("\n11. EL REGISTRO NO LLEVA CONTENIDO")
# =============================================================================

CANARIOS = ("1098765432", RESPUESTA_ONT[:40], PREFIJO, "miren la lucecita")

log = _io.StringIO()
with _ctx.redirect_stdout(log), _ctx.redirect_stderr(log):
    with _Parche(api.whatsapp, "descargar_media",
                 lambda *a, **k: (JPEG, "image/jpeg")), \
         _Parche(api.media, "preparar", lambda c, t, m: (c, m)), \
         _Parche(api.vision, "analizar",
                 lambda *a, **k: vi.Resultado(texto=RESPUESTA_ONT,
                                              estado=vi.PROCESADO,
                                              tokens=1260)), \
         _Parche(api.persistencia, "analisis_visual_de", _sin_base()):
        api._analizar_si_es_imagen(
            _Config(), "unaempresa",
            dict(ENTRANTE, descripcion="miren la lucecita"))

registrado = log.getvalue()
for canario in CANARIOS:
    comprobar(f"el log no lleva '{canario[:28]}...'",
              canario not in registrado, registrado[:300])
comprobar("el evento es de texto fijo",
          "imagen procesada" in registrado, registrado[:200])

import re as _re
eventos = set(_re.findall(r'registrar\("vision", "([^"]+)"', fuente_api))
comprobar("los eventos de vision son frases fijas, sin interpolar",
          all("{" not in e for e in eventos), str(eventos))

# =============================================================================
print("\n12. NADA DE ESTO HABILITA UNA ACCION")
# =============================================================================

fuente_vision = Path("nucleo/canales/vision.py").read_text(encoding="utf-8")


def _codigo_sin_prosa(fuente: str) -> str:
    """
    El archivo SIN docstrings ni comentarios.

    La primera version de esto buscaba las palabras en el archivo entero y se
    ponia roja por el propio docstring que explica que vision.py NO toca la
    frontera. Una guarda que se rompe con su propia documentacion no mide
    nada: o se borra la explicacion, que es lo valioso, o se la ignora.
    """
    import ast
    arbol = ast.parse(fuente)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            if (nodo.body and isinstance(nodo.body[0], ast.Expr)
                    and isinstance(nodo.body[0].value, ast.Constant)
                    and isinstance(nodo.body[0].value.value, str)):
                nodo.body[0].value.value = ""
    return ast.unparse(arbol)


codigo_vision = _codigo_sin_prosa(fuente_vision)
for prohibido in ("frontera", "ejecutar", "herramienta", "reiniciar",
                  "registrar_pago", "idempotencia", "aprobacion"):
    comprobar(f"el CODIGO de vision.py no usa '{prohibido}'",
              prohibido not in codigo_vision.lower())

comprobar("vision.py no abre su propio cliente de ningun proveedor",
          "OpenAI(" not in codigo_vision)
comprobar("vision.py no lee ninguna clave del entorno",
          "API_KEY" not in codigo_vision)
comprobar("el codigo de vision.py no nombra a ninguna empresa",
          "rapilink" not in codigo_vision.lower())

# =============================================================================
print("\n13. LA BANDERA ES CONFIGURACION")
# =============================================================================

from nucleo.config.schema import TenantConfig
comprobar("vision_habilitada esta en el esquema del tenant",
          "vision_habilitada" in TenantConfig.model_fields)
comprobar("y nace apagada",
          TenantConfig.model_fields["vision_habilitada"].default is False)
comprobar("el analisis se decide por la bandera, no por el tenant",
          'getattr(config, "vision_habilitada"'
          in _cuerpo_de(fuente_api, "_analizar_si_es_imagen"))
comprobar("el modelo sale de la config, no de una constante de vision.py",
          'modelo_por_defecto' in _cuerpo_de(fuente_api,
                                             "_analizar_si_es_imagen"))

# =============================================================================
print("\n14. EL AUDIO NO SE TOCO")
# =============================================================================

from nucleo.canales import transcripcion as tr
comprobar("transcripcion.py sigue con su propio modelo",
          tr.MODELO == "gpt-4o-transcribe")
comprobar("y su propio timeout, distinto del de vision",
          tr.TIMEOUT_SEGUNDOS == 45.0 and vi.TIMEOUT_SEGUNDOS == 30.0)
comprobar("vision no importa transcripcion",
          "transcripcion" not in codigo_vision)

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("TODO EN VERDE")
print("=" * 70)
