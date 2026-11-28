# -*- coding: utf-8 -*-
"""
================================================================================
 TRANSCRIPCION DE NOTAS DE VOZ  --  y las formas de que no
================================================================================

    py -3.13 tests/test_transcripcion_audio.py

CORRE SIN RED Y SIN CLAVE. Se sustituye la RESPUESTA de OpenAI, nunca la
logica: el camino del codigo es el real.

LO QUE SE VIGILA
----------------
Que un fallo NO produzca texto. Es el unico modo en que esto puede hacer daño:
un audio mal transcrito --o inventado-- hace que el agente conteste con
seguridad a algo que el cliente no dijo, y el cliente no tiene forma de saber
que le entendieron otra cosa. Por eso casi todas las comprobaciones miran que
'texto' quede VACIO, no que el error tenga tal o cual palabra.

Y que el texto siga andando igual. La transcripcion es una rama nueva sobre un
camino que ya funcionaba para miles de mensajes: §1 comprueba que un mensaje de
texto no toca nada de esto.
================================================================================
"""

import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import transcripcion as tr

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


#  Un Ogg minimo: la firma y relleno. No es audio reproducible, y no hace
#  falta -- lo que se prueba es que el codigo lo RECONOZCA como Ogg.
OGG = b"OggS" + b"\x00" * 60
NO_OGG = b"RIFF" + b"\x00" * 60


class _RespuestaFalsa:
    def __init__(self, texto="", tokens=36):
        self.text = texto
        self.usage = type("U", (), {"total_tokens": tokens})()


def _cliente_que(responde=None, levanta=None):
    """Un OpenAI de mentira que devuelve lo que se le diga."""
    class _Trans:
        @staticmethod
        def create(**kw):
            _Trans.ultima = kw
            if levanta:
                raise levanta
            return responde
    _Trans.ultima = {}

    class _Cli:
        def __init__(self, **kw):
            self.audio = type("A", (), {"transcriptions": _Trans})()
    return _Cli, _Trans


def _con_openai(cli, clave="sk-de-prueba"):
    """Mete el cliente falso donde el import perezoso lo va a buscar."""
    import types
    modulo = types.ModuleType("openai")
    modulo.OpenAI = cli
    previo_mod = sys.modules.get("openai")
    previo_clave = os.environ.get("OPENAI_API_KEY")
    sys.modules["openai"] = modulo
    if clave is None:
        os.environ.pop("OPENAI_API_KEY", None)
    else:
        os.environ["OPENAI_API_KEY"] = clave

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *_):
            if previo_mod is not None:
                sys.modules["openai"] = previo_mod
            else:
                sys.modules.pop("openai", None)
            if previo_clave is not None:
                os.environ["OPENAI_API_KEY"] = previo_clave
            else:
                os.environ.pop("OPENAI_API_KEY", None)
            return False
    return _Ctx()


# =============================================================================
#  §2  UN AUDIO VALIDO SE TRANSCRIBE
# =============================================================================

def test_2_audio_valido_devuelve_el_texto():
    cli, trans = _cliente_que(_RespuestaFalsa("Que la television se volvio a ir!"))
    with _con_openai(cli):
        r = tr.transcribir(OGG, "audio/ogg; codecs=opus")
    comprobar("2 · un audio valido devuelve su texto",
              r.ok and r.texto == "Que la television se volvio a ir!", r.error)
    comprobar("2b · queda en estado 'procesado'", r.estado == tr.PROCESADO)
    comprobar("2c · informa los tokens que consumio", r.tokens == 36)


def test_2d_el_idioma_y_el_modelo_viajan_fijados():
    cli, trans = _cliente_que(_RespuestaFalsa("hola"))
    with _con_openai(cli):
        tr.transcribir(OGG)
    comprobar("2d · se pide en español y con el modelo declarado",
              trans.ultima.get("language") == "es"
              and trans.ultima.get("model") == "gpt-4o-transcribe",
              str(trans.ultima.get("model")))


# =============================================================================
#  §3  EL .OPUS SE RENOMBRA, NO SE RECODIFICA
# =============================================================================

def test_3_el_archivo_sube_como_ogg_con_los_mismos_bytes():
    """
    LA PRUEBA QUE JUSTIFICA TODO EL DISEÑO.

    Medido contra la API real el 30/09/2026: el mismo archivo con nombre
    '.opus' responde 400 y con nombre '.ogg' responde 200. Asi que lo unico
    que hay que cambiar es el NOMBRE -- y hay que comprobar que los bytes que
    suben son IDENTICOS a los que llegaron, o se estaria recodificando sin
    querer.
    """
    enviados = {}

    class _Trans:
        @staticmethod
        def create(**kw):
            f = kw["file"]
            enviados["nombre"] = os.path.basename(getattr(f, "name", ""))
            enviados["bytes"] = f.read()
            return _RespuestaFalsa("ok")

    class _Cli:
        def __init__(self, **kw):
            self.audio = type("A", (), {"transcriptions": _Trans})()

    original = b"OggS" + bytes(range(256)) * 3
    with _con_openai(_Cli):
        tr.transcribir(original, "audio/ogg; codecs=opus")

    comprobar("3 · sube con extension .ogg",
              enviados.get("nombre", "").endswith(".ogg"), enviados.get("nombre"))
    comprobar("3b · los bytes son EXACTAMENTE los que llegaron",
              enviados.get("bytes") == original,
              f"{len(enviados.get('bytes') or b'')} vs {len(original)}")


def test_3c_no_queda_ningun_temporal():
    import glob
    import tempfile
    antes = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.ogg")))
    cli, _ = _cliente_que(_RespuestaFalsa("ok"))
    with _con_openai(cli):
        tr.transcribir(OGG)
    despues = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.ogg")))
    comprobar("3c · el temporal se borra despues de la llamada", antes == despues,
              str(despues - antes))


# =============================================================================
#  §4  UN AUDIO INVALIDO NO SE ENVIA
# =============================================================================

def test_4_lo_que_no_es_ogg_no_llega_a_la_api():
    llamadas = []

    class _Trans:
        @staticmethod
        def create(**kw):
            llamadas.append(kw)
            return _RespuestaFalsa("no deberia llegar aca")

    class _Cli:
        def __init__(self, **kw):
            self.audio = type("A", (), {"transcriptions": _Trans})()

    with _con_openai(_Cli):
        r = tr.transcribir(NO_OGG, "audio/mpeg")

    comprobar("4 · un archivo que no es Ogg no se envia", llamadas == [])
    comprobar("4b · y no produce texto", r.texto == "" and r.estado == tr.ERROR)


def test_4c_un_audio_vacio_no_se_envia():
    r = tr.transcribir(b"")
    comprobar("4c · un audio vacio se rechaza antes de salir",
              r.estado == tr.ERROR and r.texto == "")


def test_4d_un_audio_enorme_no_se_envia():
    enorme = b"OggS" + b"\x00" * (tr.MAX_BYTES + 1)
    r = tr.transcribir(enorme)
    comprobar("4d · un audio por encima del tope no se envia",
              r.estado == tr.ERROR and r.texto == "")


# =============================================================================
#  §5  UN ERROR DE OPENAI NO INVENTA NADA
# =============================================================================

def test_5_si_la_api_falla_no_hay_texto():
    cli, _ = _cliente_que(levanta=RuntimeError("502 Bad Gateway"))
    with _con_openai(cli):
        r = tr.transcribir(OGG)
    comprobar("5 · un fallo de la API deja el texto VACIO",
              r.texto == "" and r.estado == tr.ERROR)
    comprobar("5b · nunca levanta: el turno sigue", isinstance(r, tr.Resultado))


def test_5c_el_error_no_repite_el_texto_del_proveedor():
    """
    Lo que contesto OpenAI no es de Dexter y este mensaje termina en logs.
    Mismo criterio que embeddings.py.
    """
    cli, _ = _cliente_que(levanta=RuntimeError("clave sk-proj-SECRETO invalida"))
    with _con_openai(cli):
        r = tr.transcribir(OGG)
    comprobar("5c · el error no arrastra el texto del proveedor",
              "SECRETO" not in r.error and "sk-proj" not in r.error, r.error)


def test_5d_un_audio_sin_voz_es_procesado_y_no_error():
    """
    Un toque sin querer transcribe a nada con 200. NO es un fallo del sistema
    -- y distinguirlo importa: uno se reintenta y el otro no.
    """
    cli, _ = _cliente_que(_RespuestaFalsa(""))
    with _con_openai(cli):
        r = tr.transcribir(OGG)
    comprobar("5d · un audio sin voz queda 'procesado', no 'error'",
              r.estado == tr.PROCESADO and r.texto == "", r.estado)


# =============================================================================
#  §6  SIN CLAVE, ERROR CLARO Y SIN SALIR A LA RED
# =============================================================================

def test_6_sin_api_key_no_se_intenta():
    llamadas = []

    class _Trans:
        @staticmethod
        def create(**kw):
            llamadas.append(kw)
            return _RespuestaFalsa("no deberia")

    class _Cli:
        def __init__(self, **kw):
            self.audio = type("A", (), {"transcriptions": _Trans})()

    with _con_openai(_Cli, clave=None):
        r = tr.transcribir(OGG)

    comprobar("6 · sin OPENAI_API_KEY no se llama a la API", llamadas == [])
    comprobar("6b · y lo dice con claridad",
              r.estado == tr.ERROR and "OPENAI_API_KEY" in r.error, r.error)


def test_6c_la_clave_nunca_aparece_en_el_resultado():
    cli, _ = _cliente_que(levanta=RuntimeError("fallo"))
    with _con_openai(cli, clave="sk-proj-NO-DEBE-SALIR"):
        r = tr.transcribir(OGG)
    plano = f"{r.texto} {r.error} {r.estado}"
    comprobar("6c · la clave no aparece en ningun campo del resultado",
              "NO-DEBE-SALIR" not in plano, plano)


# =============================================================================
#  §7  CAPTION Y TRANSCRIPCION SON DOS COSAS
# =============================================================================

def test_7_el_caption_y_la_transcripcion_viajan_separados():
    salida = tr.texto_para_el_agente("Se me fue la tele", "mira")
    comprobar("7 · la transcripcion se rotula como nota de voz",
              "[Nota de voz del cliente]" in salida and "Se me fue la tele" in salida)
    comprobar("7b · el caption va aparte y se distingue",
              "mira" in salida and "junto al audio" in salida, salida)


def test_7c_sin_caption_no_se_inventa_una_seccion():
    salida = tr.texto_para_el_agente("Se me fue la tele", "")
    comprobar("7c · sin caption no aparece esa seccion",
              "junto al audio" not in salida, salida)


def test_7d_se_dice_que_vino_hablado():
    """
    El modelo redacta distinto si sabe que la persona HABLO: una transcripcion
    entrecortada sin el rotulo parece un cliente que escribe mal.
    """
    salida = tr.texto_para_el_agente("eh... se fue otra vez")
    comprobar("7d · el rotulo dice que vino hablado",
              salida.startswith("[Nota de voz del cliente]"), salida)


# =============================================================================
#  §10  LO QUE LLEGA AL AGENTE
# =============================================================================

def test_10_el_agente_recibe_la_transcripcion_como_contenido():
    """
    No un aviso: el texto. Es la diferencia entre que el agente pueda
    contestar la consulta y que pida que se la escriban.
    """
    salida = tr.texto_para_el_agente("Que la television se volvio a ir!")
    comprobar("10 · el contenido lleva lo que el cliente dijo",
              "Que la television se volvio a ir!" in salida)
    comprobar("10b · y NO el aviso generico de adjunto",
              "envio un audio" not in salida.lower(), salida)


# =============================================================================
#  §11  EL CAMINO DE SIEMPRE NO SE TOCA
# =============================================================================

def test_1_y_11_el_orden_del_webhook_es_el_declarado():
    """
    Se lee el fuente de api.py y se comprueba el ORDEN de tres cosas:

        transcribir  ->  atender_turno  ->  guardar adjunto

    Es una afirmacion sobre el codigo y no sobre el comportamiento, y se dice:
    montar el webhook entero aqui exigiria base, red y un tenant. Lo que esta
    prueba impide es la regresion concreta que rompe esto -- mover la
    transcripcion despues del turno, que la dejaria sin efecto sin romper
    ninguna otra prueba.
    """
    fuente = (Path(__file__).resolve().parents[1]
              / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
    #  LA FUNCION ENTERA, no una ventana de tamano fijo.
    #
    #  Antes esto era `fuente[i:i + 6000]` y se rompio el 05/10/2026 al
    #  agregar el gate de costo: la funcion paso a medir 8017 caracteres,
    #  'atender_turno' quedo fuera de la ventana y find() devolvio -1. Daba
    #  rojo con el orden INTACTO -- medido ese dia: transcribir en 4556,
    #  atender_turno en 6340, guardar en 6735.
    #
    #  Una prueba que se cae porque la funcion crecio no esta midiendo el
    #  orden: esta midiendo el largo del archivo, y enseña a ignorarla.
    i = fuente.index("def _procesar_mensaje_whatsapp")
    resto = fuente[i + 1:]
    siguiente = resto.find("\ndef ")
    bloque = resto[:siguiente] if siguiente != -1 else resto

    p_tr = bloque.find("_transcribir_si_es_voz(config")
    p_turno = bloque.find("atender_turno(config")
    p_guardar = bloque.find("_guardar_adjunto(config")

    comprobar("11 · la transcripcion ocurre ANTES del turno",
              -1 < p_tr < p_turno, f"tr={p_tr} turno={p_turno}")
    comprobar("11b · el adjunto se guarda DESPUES del turno",
              p_turno < p_guardar, f"turno={p_turno} guardar={p_guardar}")


def test_1_un_mensaje_de_texto_no_pasa_por_aca():
    """
    El texto sigue su camino de siempre: '_transcribir_si_es_voz' sale sin
    hacer nada si el tipo no es de voz. Se comprueba el catalogo, que es lo
    que decide.
    """
    comprobar("1 · solo audio y voice se transcriben",
              set(tr.TIPOS_DE_VOZ) == {"audio", "voice"}, str(tr.TIPOS_DE_VOZ))
    comprobar("1b · image y video NO estan en el catalogo",
              "image" not in tr.TIPOS_DE_VOZ and "video" not in tr.TIPOS_DE_VOZ)


def test_9_la_persistencia_sigue_sin_duplicar_por_media_id():
    """
    Un reintento del webhook no debe transcribir ni guardar dos veces. La
    guarda ya existia --'on conflict (organization_id, media_id) do nothing'--
    y esto comprueba que el insert nuevo, con tres columnas mas, la conserva.
    """
    fuente = (Path(__file__).resolve().parents[1]
              / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
    i = fuente.index("def guardar_media")
    bloque = fuente[i:i + 2500]
    comprobar("9 · el insert sigue siendo idempotente por media_id",
              "on conflict (organization_id, media_id) do nothing" in bloque)
    comprobar("9b · la transcripcion va en su propia columna",
              "transcripcion, estado_transcripcion, error_transcripcion" in bloque)


def test_9c_la_transcripcion_no_pisa_el_caption():
    """
    'descripcion' es el caption del cliente. Que las dos columnas viajen en el
    mismo insert, por separado, es lo que impide que una borre a la otra.
    """
    fuente = (Path(__file__).resolve().parents[1]
              / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
    i = fuente.index("def guardar_media")
    bloque = fuente[i:i + 2500]
    comprobar("9c · descripcion y transcripcion son columnas distintas",
              "descripcion,\n                  transcripcion" in bloque
              or "descripcion, transcripcion" in bloque
              or ("descripcion" in bloque and "transcripcion," in bloque))


def test_8_el_tenant_no_se_pierde_por_el_camino():
    """
    'guardar_media' abre la sesion con el tenant y de ahi sale el
    organization_id: la transcripcion entra por el MISMO insert, asi que
    hereda el aislamiento sin una segunda ruta que pudiera olvidarlo.
    """
    fuente = (Path(__file__).resolve().parents[1]
              / "nucleo" / "persistencia" / "db.py").read_text(encoding="utf-8")
    i = fuente.index("def guardar_media")
    bloque = fuente[i:i + 2500]
    comprobar("8 · la escritura sigue pasando por sesion(tenant)",
              "with sesion(tenant) as (cur, org):" in bloque)
    comprobar("8b · y el organization_id sigue viajando en el insert",
              "organization_id" in bloque and "(org," in bloque)


# =============================================================================
if __name__ == "__main__":
    print("=" * 74)
    print(" TRANSCRIPCION DE NOTAS DE VOZ  --  y las formas de que no")
    print("=" * 74)

    for nombre, funcion in sorted(list(globals().items())):
        if nombre.startswith("test_") and callable(funcion):
            try:
                funcion()
            except Exception as e:  # pragma: no cover
                comprobar(nombre[5:].replace("_", " "), False,
                          f"{type(e).__name__}: {e}")

    print(chr(10) + "=" * 74)
    if fallos:
        print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron:")
        for f in fallos:
            print(f"   - {f}")
    else:
        print(" TODO EN VERDE  --  ningun fallo produce texto inventado")
    print("=" * 74)
    sys.exit(1 if fallos else 0)
