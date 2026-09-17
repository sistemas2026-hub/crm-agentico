# -*- coding: utf-8 -*-
"""
================================================================================
 REGISTRO SIN PII  --  el log del motor no lleva telefonos, wamids ni textos
================================================================================

    py -3.13 tests/test_registro_sin_pii.py          (sin base, sin red)

Por que existe (D20, 16/09/2026)
--------------------------------
El log del motor persiste, y el camino de WhatsApp escribia ahi el telefono
completo del cliente, el wamid entero y el texto crudo de las excepciones -- que
es donde se esconden los valores: un error de PostgreSQL trae la fila que
fallo, uno de requests trae la URL. Arreglarlo print por print (cd7c4f5) dejo
decenas vivos. Ver nucleo/observabilidad/registro.py.

Una prueba que mira el codigo no alcanza: el texto de una excepcion aparece
recien al fallar. Una que mira la salida tampoco: solo cubre los caminos que
ejercita. Por eso son tres partes:

  1. registro.py por dentro: redaccion, HMAC (no hash plano), excepciones
  2. el CODIGO: ningun print en los modulos del turno, y registrar() solo con
     evento fijo y sin variables de PII sueltas
  3. la SALIDA: se inyectan valores canario (telefono, wamid, texto del
     cliente, texto de error de Meta) por cada camino de WhatsApp -- mensaje
     normal, duplicado, leido, alta/baja, fallos de envio y de aviso, payload
     incompleto, remitente opaco, acuses, red caida, error no manejado -- y se
     exige que NINGUNO aparezca en stdout, stderr ni logging. Cada escenario
     afirma ademas que su linea de log SI salio: si el camino no corrio, la
     ausencia de canarios no prueba nada.
  4. el registro de acceso de gunicorn no escribe la query string
================================================================================
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import logging
import os
import sys
import types
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ.pop("MOTOR_SERVICE_TOKEN", None)
os.environ["REGISTRO_CLAVE_HMAC"] = "clave-de-prueba-d20"

import requests                                                   # noqa: E402

from nucleo.observabilidad import registro                        # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


# Los canarios. Cada uno es algo que NUNCA puede terminar en un log.
TEL = "573014445566"
WAMID = "wamid.TEST_SECRET_ABC123"
MSG = "TEXTO_CLIENTE_NO_DEBE_APARECER"
ERR_META = "ERROR_META_NO_DEBE_APARECER"
BSUID = "CO.1360399936298471"
NOMBRE = "NOMBRE_PERFIL_NO_DEBE_APARECER"
VERIFY = "VERIFY_TOKEN_NO_DEBE_APARECER"
CANARIOS = [TEL, TEL[-7:], WAMID, "TEST_SECRET_ABC123", MSG, ERR_META, BSUID, "1360399936298471",
            NOMBRE, VERIFY]
TENANT = "tenant-prueba-d20"


# =============================================================================
titulo("1. registro.py por dentro")
# =============================================================================
f = registro.formatear
linea = f("x", "evento", tel=TEL, wamid=WAMID, texto=f"hola {MSG}", email="a@b.co",
          url="https://graph.facebook.com/v20.0/algo", uuid_ok="5a9e996e-2a9f-4cd0-9677-db33165c5fd0",
          estado="entregado", n=3, lista=["soporte", TEL], dic={"k": TEL})
revisar(all(c not in linea for c in (TEL, WAMID, MSG, "a@b.co", "graph.facebook")),
        "un campo con telefono, wamid, texto libre, email o URL se redacta aunque se pase por error",
        linea)
revisar("uuid_ok=5a9e996e-2a9f-4cd0-9677-db33165c5fd0" in linea and "estado=entregado" in linea
        and "n=3" in linea and "lista=[soporte,<redactado>]" in linea,
        "los identificadores internos, estados y numeros pasan tal cual", linea)
revisar(f("x", "evento", obj=object()) == "[x] evento obj=<object>",
        "un objeto cualquiera se describe por su tipo, nunca por su repr")

ref = registro.ref_sesion(TEL)
plano = hashlib.sha256(TEL.encode()).hexdigest()[:12]
revisar(ref.startswith("ses-") and TEL not in ref and plano not in ref,
        "ref_sesion es HMAC con clave: no coincide con el sha256 plano (enumerable) del telefono",
        f"{ref} vs sha256 {plano}")
revisar(registro.ref_sesion(TEL) == ref and registro.ref_sesion("573014445567") != ref,
        "y es estable para el mismo telefono y distinta para otro")
os.environ["REGISTRO_CLAVE_HMAC"] = "otra-clave"
revisar(registro.ref_sesion(TEL) != ref, "cambiar la clave cambia la referencia: depende del secreto")
del os.environ["REGISTRO_CLAVE_HMAC"]
maestra_previa = os.environ.pop("SECRETOS_CLAVE_MAESTRA", None)
sin_clave = registro.ref_sesion(TEL)
revisar(sin_clave.startswith("sesx-") and plano not in sin_clave,
        "sin ninguna clave NO cae a hash plano: usa una clave aleatoria del proceso y lo avisa con 'sesx-'",
        sin_clave)
os.environ["SECRETOS_CLAVE_MAESTRA"] = "maestra-de-prueba"
derivada = registro.ref_sesion(TEL)
revisar(derivada.startswith("ses-") and derivada != sin_clave,
        "con SECRETOS_CLAVE_MAESTRA se deriva una clave estable", derivada)
if maestra_previa is None:
    del os.environ["SECRETOS_CLAVE_MAESTRA"]
else:
    os.environ["SECRETOS_CLAVE_MAESTRA"] = maestra_previa
os.environ["REGISTRO_CLAVE_HMAC"] = "clave-de-prueba-d20"

prv = registro.ref_proveedor(WAMID)
revisar(prv == "prv-" + hashlib.sha256(WAMID.encode()).hexdigest()[:12],
        "ref_proveedor (wamid, media_id) es recalculable en SQL: prv- + 12 hex del sha256", prv)

try:
    import psycopg
    error_pg = psycopg.errors.UniqueViolation(
        f'duplicate key value violates unique constraint "x"\nDETAIL: Key (usuario_externo)=({TEL}) {ERR_META}')
except ImportError:                                               # pragma: no cover
    error_pg = RuntimeError(f"Key (usuario_externo)=({TEL}) {ERR_META}")


def lanzar(e):
    raise e


try:
    lanzar(error_pg)
except Exception as capturado:
    linea = f("x", "fallo", error=capturado)
revisar(TEL not in linea and ERR_META not in linea and "error=UniqueViolation" in linea
        and "sqlstate=23505" in linea,
        "una excepcion sale por tipo y sqlstate, nunca por su texto (que traia el valor de la fila)",
        linea)

try:
    lanzar(ValueError(MSG))
except Exception as capturado:
    datos = registro.error_seguro(capturado)
revisar(all(MSG not in str(v) for v in datos.values()),
        "error_seguro no conserva el texto de la excepcion aunque sea una sola palabra "
        "(la redaccion de campos no la taparia: no tiene espacios ni digitos)", f"{datos}")

from nucleo.canales import whatsapp                               # noqa: E402

linea = f("x", "fallo", error=whatsapp.ErrorWhatsApp("x", codigo=131026, http_status=400,
                                                        operacion="el envío"))
revisar("codigo=131026" in linea and "http_status=400" in linea,
        "un rechazo de WhatsApp conserva su codigo y estado HTTP, que es lo que sirve", linea)


# =============================================================================
titulo("2. el codigo: ningun print, registrar() con evento fijo")
# =============================================================================
# Los modulos que PUEDEN seguir usando print, y por que. Todo modulo nuevo del
# nucleo queda cubierto por defecto: no hay que acordarse de agregarlo.
EXENTOS = {
    "nucleo/observabilidad/registro.py": "es la puerta: el unico print del camino del turno",
    "nucleo/reloj.py": "proceso aparte (motor-reloj); no atiende WhatsApp. Deuda anotada en D20",
    "nucleo/programador/coordinador.py": "proceso del reloj. Deuda anotada en D20",
    "nucleo/programador/ejecutor.py": "proceso del reloj. Deuda anotada en D20",
    "nucleo/seguimiento/importacion_io.py": "importacion de WispHub en el reloj. Deuda anotada en D20",
    "nucleo/config/editor.py": "edicion de config desde la interfaz: no toca datos de clientes",
    "nucleo/config/schema.py": "bloque __main__ de diagnostico por consola",
    "nucleo/persistencia/conexion.py": "aviso de arranque con el DBHOST",
    "nucleo/conectores/catalogo.py": "lee YAML del repo",
    "nucleo/habilidades/analista.py": "analista fuera del turno. Deuda anotada en D20",
}
# Nombres que en el nucleo SIEMPRE son datos de una persona o de su mensaje.
# Pasarlos sueltos a registrar() es el error; envueltos en ref_sesion,
# ref_proveedor o id_interno, no.
PII = {"de", "para", "telefono", "id_sesion", "wamid", "texto", "mensaje", "contenido", "cuerpo",
       "crudo", "respuesta", "evidencia_humano", "motivo_forzado", "por_que", "frase", "media_id",
       "nombre_cliente", "descripcion", "pregunta", "resumen", "bsuid", "recibido", "token"}

con_print, mal_llamado, exentos_vacios = [], [], []
for ruta in sorted((RAIZ / "nucleo").rglob("*.py")):
    rel = ruta.relative_to(RAIZ).as_posix()
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    prints = [n.lineno for n in ast.walk(arbol) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "print"]
    if rel in EXENTOS:
        if not prints:
            exentos_vacios.append(rel)
        continue
    con_print += [f"{rel}:{l}" for l in prints]
    for n in ast.walk(arbol):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "registrar"):
            continue
        donde = f"{rel}:{n.lineno}"
        if (len(n.args) != 2 or not all(isinstance(a, ast.Constant) and isinstance(a.value, str)
                                        for a in n.args)):
            mal_llamado.append(f"{donde} componente y evento tienen que ser texto fijo")
        for k in n.keywords:
            for sub in ast.walk(k.value):
                if isinstance(sub, ast.JoinedStr) or (
                        isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "format"):
                    mal_llamado.append(f"{donde} {k.arg}= arma texto libre")
            v = k.value
            if isinstance(v, ast.Name) and v.id in PII:
                mal_llamado.append(f"{donde} {k.arg}={v.id} sin ref_sesion/ref_proveedor/id_interno")
            if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ("str", "repr")
                    and v.args and isinstance(v.args[0], ast.Name)
                    and (v.args[0].id in PII or v.args[0].id in ("e", "fallo"))):
                mal_llamado.append(f"{donde} {k.arg}={ast.unparse(v)}")
revisar(not con_print, "ningun print fuera de los modulos exentos (cada uno con su motivo)",
        f"{con_print}")
revisar(not mal_llamado, "registrar() siempre con evento fijo y sin PII suelta en los campos",
        "\n         ".join(mal_llamado))
revisar(not exentos_vacios, "ninguna exencion sobra (si un modulo ya no imprime, sale de la lista)",
        f"{exentos_vacios}")


# =============================================================================
titulo("3. la salida: canarios por cada camino de WhatsApp")
# =============================================================================
from nucleo.canales import api                                    # noqa: E402


class Captura:
    """stdout, stderr y logging -- lo que llegaria al log del contenedor."""

    def __enter__(self):
        self.buf = io.StringIO()
        self._out = contextlib.redirect_stdout(self.buf)
        self._err = contextlib.redirect_stderr(self.buf)
        self._out.__enter__()
        self._err.__enter__()
        self.handler = logging.StreamHandler(self.buf)
        self.handler.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(self.handler)
        self._nivel = logging.getLogger().level
        logging.getLogger().setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc):
        logging.getLogger().removeHandler(self.handler)
        logging.getLogger().setLevel(self._nivel)
        self._err.__exit__(*exc)
        self._out.__exit__(*exc)
        self.texto = self.buf.getvalue()
        return False


@contextlib.contextmanager
def parches(*trios):
    viejos = [(obj, nombre, getattr(obj, nombre)) for obj, nombre, _ in trios]
    for obj, nombre, valor in trios:
        setattr(obj, nombre, valor)
    try:
        yield
    finally:
        for obj, nombre, valor in reversed(viejos):
            setattr(obj, nombre, valor)


class HiloEnLinea:
    """El webhook atiende en un hilo; aca corre en linea para capturar su log."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def lanza(e):
    def _f(*a, **k):
        raise e
    return _f


def respuesta_http(status):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps({"error": {"message": ERR_META, "code": 131026}}).encode()
    return r


def error_http():
    return requests.HTTPError(f"400 Client Error: {ERR_META} for url: "
                              f"https://graph.facebook.com/v20.0/{WAMID}?to={TEL}",
                              response=respuesta_http(400))


def error_red():
    return requests.ConnectionError(f"HTTPSConnectionPool: /v20.0/{WAMID}/messages?to={TEL} {ERR_META}")


cfg_wa = types.SimpleNamespace(
    activo=True, token_ref="T", phone_number_id_ref="P", waba_id_ref="W", app_secret_ref="S",
    verify_token_ref="V", api_base="https://graph.facebook.com", version_api="v20.0",
    palabras_baja=["baja"], palabras_alta=["alta"], respuesta_baja="listo", respuesta_alta="listo",
    plantillas=[])
CONFIG = types.SimpleNamespace(canales=types.SimpleNamespace(whatsapp=cfg_wa),
                               rol_de_entrada="cliente", roles={},
                               identidad=types.SimpleNamespace(slug=TENANT))

atendidos: list[tuple] = []


def atender_ok(config, tenant, rol, de, texto, canal):
    atendidos.append((de, texto))
    return {"respuesta": f"respuesta a {MSG}", "conversacion_id": str(uuid.uuid4())}


def entrante(texto=MSG, con_id=True, contacto=True, desde=TEL):
    m = {"from": desde, "type": "text", "text": {"body": texto}, "timestamp": "1"}
    if con_id:
        m["id"] = WAMID
    valor = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "P"}, "messages": [m]}
    if contacto:
        valor["contacts"] = [{"wa_id": desde, "profile": {"name": NOMBRE}}]
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": valor}]}]}


cliente = api.app.test_client()
FIRMA_REAL = whatsapp.firma_valida      # BASE la reemplaza; el escenario de la firma usa la real


def webhook(cuerpo):
    return cliente.post(f"/canales/whatsapp/{TENANT}", data=json.dumps(cuerpo),
                        content_type="application/json",
                        headers={"X-Hub-Signature-256": "sha256=firma"})


BASE = (
    (api, "_config_de", lambda tenant: CONFIG),
    (api.whatsapp, "firma_valida", lambda *a, **k: True),
    (api.threading, "Thread", HiloEnLinea),
    (api.persistencia, "evento_ya_visto", lambda tenant, wamid: False),
    (api.whatsapp, "_secreto", lambda tenant, ref, para_que: "SECRETO"),
    (api.whatsapp.requests, "post", lambda *a, **k: types.SimpleNamespace(
        status_code=200, json=lambda: {"messages": [{"id": "wamid.OUT"}]})),
    (api, "atender_turno", atender_ok),
    (api.whatsapp, "enviar_texto", lambda config, tenant, para, texto: "wamid.OUT"),
)

escenarios: list[tuple[str, str, list[str]]] = []   # (nombre, log, marcadores esperados)


def escenario(nombre, funcion, *marcadores, extra=()):
    atendidos.clear()
    with parches(*BASE, *extra), Captura() as cap:
        resultado = funcion()
    escenarios.append((nombre, cap.texto, list(marcadores)))
    return resultado


r = escenario("mensaje entrante normal", lambda: webhook(entrante()), "entrega recibida")
revisar(r.status_code == 200 and atendidos == [(TEL, MSG)],
        "mensaje normal: se atiende con el telefono y el texto reales (el camino corrio)",
        f"{r.status_code} {len(atendidos)}")

escenario("marcar leido falla por red", lambda: webhook(entrante()), "no se pudo marcar leido",
          "error=ConnectionError",
          extra=((api.whatsapp.requests, "post", lanza(error_red())),))
revisar(len(atendidos) == 1, "si falla el leido, el mensaje igual se atiende")

escenario("duplicado", lambda: webhook(entrante()),
          extra=((api.persistencia, "evento_ya_visto", lambda t, w: True),))
revisar(not atendidos, "un duplicado no se atiende")
escenario("no se puede verificar duplicado", lambda: webhook(entrante()),
          "no se pudo verificar si es duplicado", "sqlstate=23505",
          extra=((api.persistencia, "evento_ya_visto", lanza(error_pg)),))

escenario("baja de avisos", lambda: webhook(entrante(texto="baja")), "baja de avisos", "remitente=ses-",
          extra=((api.persistencia, "dar_de_baja", lambda *a: None),))
escenario("alta de avisos con la base caida", lambda: webhook(entrante(texto="alta")),
          "fallo al procesar baja/alta de avisos",
          extra=((api.persistencia, "dar_de_alta", lanza(error_pg)),))
revisar(len(atendidos) == 1, "si falla el alta, el mensaje sigue al modelo")

escenario("envio de la respuesta rechazado por Meta", lambda: webhook(entrante()),
          "fallo al atender un mensaje entrante", "http_status=400",
          extra=((api.whatsapp, "enviar_texto", lanza(error_http())),))
escenario("el turno falla con un error de base", lambda: webhook(entrante()),
          "fallo al atender un mensaje entrante", "sqlstate=23505",
          extra=((api, "atender_turno", lanza(error_pg)),))

escenario("el turno falla con una excepcion de una sola palabra", lambda: webhook(entrante()),
          "fallo al atender un mensaje entrante", "error=ValueError",
          extra=((api, "atender_turno", lanza(ValueError(MSG))),))

escenario("mensaje sin wamid", lambda: webhook(entrante(con_id=False)), "mensaje descartado")
escenario("entrega sin mensajes ni estados", lambda: webhook(
    {"entry": [{"changes": [{"field": "messages", "value": {TEL: MSG, "otra": ERR_META}}]}]}),
    "entrega SIN mensajes ni estados")

opaco = entrante(contacto=False, desde=None)
m = opaco["entry"][0]["changes"][0]["value"]["messages"][0]
m.pop("from")
m["from_user_id"] = BSUID
opaco["entry"][0]["changes"][0]["value"]["contacts"] = [{"user_id": BSUID, "profile": {"name": NOMBRE}}]
escenario("remitente opaco (BSUID)", lambda: webhook(opaco), "remitente opaco",
          "remitente sin telefono (BSUID)")

acuse = {"entry": [{"changes": [{"field": "messages", "value": {"statuses": [{
    "id": WAMID, "status": "failed", "recipient_id": TEL, "timestamp": "1",
    "errors": [{"code": 131026, "message": ERR_META, "error_data": {"details": ERR_META}}]}]}}]}]}
escenario("acuse fallido que no se puede anotar", lambda: webhook(acuse), "acuse", "codigo=131026",
          "wamid=prv-", "no se pudo anotar el acuse",
          extra=((api.persistencia, "marcar_entrega", lanza(error_pg)),))
acuse_ok = json.loads(json.dumps(acuse).replace('"failed"', '"delivered"'))
escenario("acuse entregado", lambda: webhook(acuse_ok), "estado=delivered",
          extra=((api.persistencia, "marcar_entrega", lambda *a: True),))


def aviso():
    return cliente.post(f"/avisos/whatsapp/{TENANT}", json={"para": TEL, "plantilla": "cobro"})


escenario("aviso: no se puede comprobar la baja", aviso, "no se pudo comprobar la baja",
          extra=((api.persistencia, "esta_de_baja", lanza(error_pg)),))
escenario("aviso: la red se cae", aviso, "fallo el aviso", "error=ConnectionError",
          extra=((api.persistencia, "esta_de_baja", lambda *a: False),
                 (api.whatsapp, "enviar_plantilla", lanza(error_red()))))

escenario("respuesta humana: la red se cae", lambda: api._entregar_y_registrar(
    TENANT, str(uuid.uuid4()), lanza(error_red()), "texto"), "rechazado", "error=ConnectionError",
    extra=((api.persistencia, "marcar_envio", lambda *a: True),))
escenario("respuesta humana: aceptada y no registrada", lambda: api._entregar_y_registrar(
    TENANT, str(uuid.uuid4()), lambda: WAMID, "texto"), "ENTREGA INCIERTA", "wamid=prv-",
    extra=((api.persistencia, "marcar_envio", lambda *a: False),))

escenario("sesion: no se puede leer el estado previo", lambda: api._sesion_nueva(
    TENANT, TEL, "whatsapp"), "no se pudo leer el estado previo", "sesion=ses-",
    extra=((api.persistencia, "estado_de_conversacion_abierta", lanza(error_pg)),))
previo = {"escalada": True, "necesita_atencion_humana": True, "caso_id": None,
          "conversation_id": str(uuid.uuid4()), "motivo_escalada": None, "rol_efectivo": None,
          "id_cliente": None, "nombre_cliente": NOMBRE, "datos_sesion": {}}
escenario("sesion: se retoma una conversacion abierta", lambda: api._sesion_nueva(
    TENANT, TEL, "whatsapp"), "se retoma la conversacion abierta",
    extra=((api.persistencia, "estado_de_conversacion_abierta", lambda *a: previo),))

escenario("firma: el secreto no se puede leer", lambda: FIRMA_REAL(
    CONFIG, TENANT, b"{}", "sha256=abc"), "no se pudo verificar la firma",
    extra=((api.whatsapp, "_secreto", lanza(RuntimeError(f"{TEL} {ERR_META}"))),))

r = escenario("error no manejado en una ruta", lambda: cliente.get(
    f"/canales/whatsapp/{TENANT}?hub.mode=subscribe&hub.verify_token={VERIFY}&hub.challenge=1"),
    "error no manejado", "error=RuntimeError",
    extra=((api, "_config_de", lanza(RuntimeError(f"{TEL} {ERR_META} {VERIFY}"))),))
revisar(r.status_code == 500 and ERR_META not in r.get_data(as_text=True),
        "un error no manejado responde 500 generico, sin el texto de la excepcion",
        f"{r.status_code} {r.get_data(as_text=True)[:120]}")

for nombre, log, marcadores in escenarios:
    filtrados = [c for c in CANARIOS if c in log]
    faltan = [mk for mk in marcadores if mk not in log]
    revisar(not filtrados and not faltan,
            f"{nombre}: {'su linea de log salio y ' if marcadores else ''}ningun canario en la salida",
            (f"canarios filtrados: {filtrados}" if filtrados else "")
            + (f" marcadores ausentes: {faltan}" if faltan else "")
            + f"\n         log: {log.strip()[:900]}")


# =============================================================================
titulo("4. el registro de acceso no escribe la query string")
# =============================================================================
compose = (RAIZ / "docker-compose.prod.yml").read_text(encoding="utf-8")
bloque = compose[compose.index("gunicorn nucleo.canales.api:app"):]
bloque = bloque[:bloque.index("\n\n")]
revisar("--access-logformat" in bloque and "%(U)s" in bloque
        and "%(r)s" not in bloque and "%(q)s" not in bloque and "%(f)s" not in bloque,
        "gunicorn registra metodo y ruta (%(U)s), no la URL con query (hub.verify_token)", bloque)

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for falla in fallos:
        print(f"  - {falla}")
    raise SystemExit(1)
print("OK: el log del motor no lleva telefonos, wamids, textos de clientes ni errores de Meta")
