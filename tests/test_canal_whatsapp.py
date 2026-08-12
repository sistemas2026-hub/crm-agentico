# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL CANAL DE WHATSAPP
================================================================================

Que cubre y por que
-------------------
El webhook es la UNICA ruta del motor expuesta a internet (ver DESPLIEGUE.md:
el resto no lleva dominio a proposito). Su autenticacion no es un token de
sesion sino la FIRMA del cuerpo, asi que lo que hay que verificar no es "que
funcione" sino que RECHACE:

  - sin cabecera de firma          -> no se procesa
  - con firma de otro secreto      -> no se procesa
  - con el cuerpo alterado         -> no se procesa
  - handshake con token incorrecto -> no se da de alta

Y la deduplicacion, que no es cosmetica: sin ella un reintento de Meta cobra un
segundo turno del modelo y le manda al cliente la misma respuesta dos veces.

No llama a la API de Meta ni al modelo: son pruebas de la traduccion y de las
decisiones de seguridad, que es donde se rompen las cosas en silencio.

    py -3.13 tests/test_canal_whatsapp.py
================================================================================
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import whatsapp                      # noqa: E402
from nucleo.config.schema import CanalWhatsApp           # noqa: E402
from nucleo.seguridad import secretos                    # noqa: E402

APP_SECRET = "secreto-de-prueba-de-la-app"
VERIFY_TOKEN = "token-que-elige-la-empresa"
TENANT = "tenant-de-prueba"

fallos = []


def check(descripcion: str, condicion: bool):
    print(f"  [{'ok' if condicion else 'FALLA'}]   {descripcion}")
    if not condicion:
        fallos.append(descripcion)


class _ConfigFalsa:
    """Lo minimo que miran las funciones del canal. Se arma a mano en vez de
    cargar el YAML del tenant: la prueba no debe depender de si Rapilink tiene
    el canal activo hoy."""
    def __init__(self, **kwargs):
        opciones = dict(
            activo=True,
            phone_number_id_ref="WHATSAPP_PHONE_NUMBER_ID",
            token_ref="WHATSAPP_TOKEN",
            app_secret_ref="WHATSAPP_APP_SECRET",
            verify_token_ref="WHATSAPP_VERIFY_TOKEN",
        )
        opciones.update(kwargs)
        self.canales = type("C", (), {"whatsapp": CanalWhatsApp(**opciones)})()


def firmar(cuerpo: bytes, secreto: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


def main():
    # Se siembra el cache de secretos en vez de tocar Postgres: obtener()
    # consulta la base solo si el tenant no esta cacheado, asi que precargarlo
    # ejercita el MISMO camino de produccion (resolver por empresa) sin
    # necesitar conexion. Es lo que permite correr esta guarda en cualquier
    # maquina, incluido un CI sin base.
    secretos._CACHE[TENANT] = {
        "WHATSAPP_APP_SECRET": APP_SECRET,
        "WHATSAPP_VERIFY_TOKEN": VERIFY_TOKEN,
    }

    config = _ConfigFalsa()
    cuerpo = json.dumps({"object": "whatsapp_business_account"}).encode()

    print("\n" + "=" * 70)
    print(" CANAL DE WHATSAPP  --  firma, handshake y traduccion")
    print("=" * 70)

    print("\nfirma del webhook (es la autenticacion de una URL publica)")
    check("una firma correcta pasa",
          whatsapp.firma_valida(config, TENANT, cuerpo, firmar(cuerpo)))
    check("sin cabecera se rechaza",
          not whatsapp.firma_valida(config, TENANT, cuerpo, None))
    check("con cabecera vacia se rechaza",
          not whatsapp.firma_valida(config, TENANT, cuerpo, ""))
    check("sin el prefijo 'sha256=' se rechaza",
          not whatsapp.firma_valida(config, TENANT, cuerpo,
                                    firmar(cuerpo).split("=", 1)[1]))
    check("firmada con OTRO secreto se rechaza",
          not whatsapp.firma_valida(config, TENANT, cuerpo,
                                    firmar(cuerpo, "secreto-de-un-impostor")))
    check("si el cuerpo cambia, la firma deja de valer",
          not whatsapp.firma_valida(config, TENANT, cuerpo + b" ", firmar(cuerpo)))
    check("basura en la cabecera se rechaza",
          not whatsapp.firma_valida(config, TENANT, cuerpo, "sha256=nada"))

    print("\nfalla cerrado: sin poder resolver el secreto, NO se acepta")
    guardado = secretos._CACHE[TENANT].pop("WHATSAPP_APP_SECRET")
    check("sin el app_secret cargado, una firma valida tampoco pasa",
          not whatsapp.firma_valida(config, TENANT, cuerpo, firmar(cuerpo)))
    secretos._CACHE[TENANT]["WHATSAPP_APP_SECRET"] = guardado

    print("\nhandshake de alta")
    check("el verify_token correcto pasa",
          whatsapp.token_de_verificacion_valido(config, TENANT, VERIFY_TOKEN))
    check("uno incorrecto se rechaza",
          not whatsapp.token_de_verificacion_valido(config, TENANT, "otro"))
    check("vacio se rechaza",
          not whatsapp.token_de_verificacion_valido(config, TENANT, ""))
    check("None se rechaza",
          not whatsapp.token_de_verificacion_valido(config, TENANT, None))

    print("\ncanal inactivo")
    inactivo = _ConfigFalsa(activo=False)
    check("activo() dice que no", not whatsapp.activo(inactivo))
    check("un canal apagado no valida firmas",
          not whatsapp.firma_valida(inactivo, TENANT, cuerpo, firmar(cuerpo)))

    print("\ntraduccion del sobre de Meta")
    sobre = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [
                        {"id": "wamid.AAA", "from": "573001112233",
                         "type": "text", "text": {"body": "no tengo internet"}},
                        {"id": "wamid.BBB", "from": "573004445566",
                         "type": "image", "image": {"id": "media-1"}},
                    ],
                    "statuses": [
                        {"id": "wamid.CCC", "status": "delivered",
                         "recipient_id": "573001112233"},
                    ],
                }
            }]
        }]
    }
    mensajes = whatsapp.mensajes_entrantes(sobre)
    check("saca los 2 mensajes del sobre anidado", len(mensajes) == 2)
    check("lee el texto", mensajes[0]["texto"] == "no tengo internet")
    check("lee el wamid", mensajes[0]["wamid"] == "wamid.AAA")
    check("lee el telefono", mensajes[0]["de"] == "573001112233")
    check("una imagen no trae texto", mensajes[1]["texto"] == "")
    check("pero si conserva el tipo", mensajes[1]["tipo"] == "image")

    estados = whatsapp.estados_entrantes(sobre)
    check("los acuses salen por separado, no como mensajes", len(estados) == 1)
    check("un acuse NO aparece entre los mensajes",
          all(m["wamid"] != "wamid.CCC" for m in mensajes))
    check("lee el estado del acuse", estados[0]["estado"] == "delivered")

    print("\nsobres degenerados (no pueden tumbar el webhook)")
    for nombre, valor in [("vacio", {}), ("None", None),
                          ("sin entry", {"object": "x"}),
                          ("entry vacio", {"entry": []}),
                          ("changes en None", {"entry": [{"changes": None}]}),
                          ("value sin messages", {"entry": [{"changes": [{"value": {}}]}]})]:
        try:
            whatsapp.mensajes_entrantes(valor)
            whatsapp.estados_entrantes(valor)
            check(f"{nombre}: devuelve vacio sin romper", True)
        except Exception as e:
            check(f"{nombre}: devuelve vacio sin romper -- {type(e).__name__}", False)

    print("\nconfiguracion: 'activo' exige lo indispensable")
    try:
        CanalWhatsApp(activo=True)
        check("activo sin refs se rechaza", False)
    except Exception:
        check("activo sin refs se rechaza", True)
    try:
        CanalWhatsApp(activo=True, phone_number_id_ref="A", token_ref="B",
                      verify_token_ref="D")
        check("activo sin app_secret_ref se rechaza", False)
    except Exception:
        check("activo sin app_secret_ref se rechaza", True)
    try:
        CanalWhatsApp(activo=False)
        check("inactivo sin refs es valido (es el estado inicial)", True)
    except Exception:
        check("inactivo sin refs es valido (es el estado inicial)", False)
    try:
        CanalWhatsApp(activo=True, phone_number_id_ref="EAAG-un-token-de-verdad",
                      token_ref="B", app_secret_ref="C", verify_token_ref="D")
        check("un VALOR donde va un NOMBRE se rechaza", False)
    except Exception:
        check("un VALOR donde va un NOMBRE se rechaza", True)

    print("\nplantillas: la indireccion clave -> nombre en Meta")
    con_plantillas = _ConfigFalsa(plantillas={"aviso_mora": "recordatorio_pago_v3"})
    try:
        whatsapp.enviar_plantilla(con_plantillas, TENANT, "573001112233", "no_declarada")
        check("una plantilla no declarada se rechaza ANTES de llamar a Meta", False)
    except whatsapp.ErrorWhatsApp as e:
        check("una plantilla no declarada se rechaza ANTES de llamar a Meta",
              "no esta declarada" in str(e))
        check("y el error dice cuales SI estan", "aviso_mora" in str(e))

    print("\nbaja de avisos: se compara el mensaje COMPLETO, no 'contiene'")
    from nucleo.canales import api as api_mod

    # Un set, no una lista: dar_de_baja de verdad es idempotente (upsert), y
    # una lista acumularia duplicados que la prueba confundiria con un fallo.
    bajas = set()
    api_mod.persistencia.dar_de_baja = lambda t, u, c="whatsapp", m=None: bajas.add(u)
    api_mod.persistencia.dar_de_alta = lambda t, u, c="whatsapp": bajas.discard(u)
    api_mod.whatsapp.enviar_texto = lambda cfg, t, para, texto: None

    def pidio(texto):
        return api_mod._atendio_baja_o_alta(config, TENANT, "573001112233", texto)

    check("'baja' da de baja", pidio("baja") and bajas == {"573001112233"})
    check("'BAJA.' tambien (mayusculas y punto final)", pidio("BAJA."))
    check("pedirla dos veces no rompe", bajas == {"573001112233"})
    check("'alta' revierte", pidio("alta") and bajas == set())
    check("una frase que CONTIENE 'baja' no da de baja",
          not pidio("no me llega nada, doy de baja el servicio?"))
    check("una consulta normal no da de baja",
          not pidio("hola, tengo problemas con el internet"))
    check("un mensaje vacio no hace nada", not pidio(""))

    probar_rutas(config)

    print("\n" + "=" * 70)
    if fallos:
        print(f" {len(fallos)} FALLA(S):")
        for f in fallos:
            print(f"   - {f}")
        sys.exit(1)
    print(" Todo en orden.")


def probar_rutas(config):
    """
    Las rutas HTTP en si, con el cliente de pruebas de Flask.

    Se sustituyen las tres dependencias externas (la configuracion, que se lee
    de la base; el registro de eventos, que tambien; y el turno, que llamaria
    al modelo) para que lo que quede bajo prueba sea SOLO lo que decide la
    ruta: que codigo devuelve, y si llega a atender o no. Es la parte expuesta
    a internet, y sus decisiones son de seguridad.
    """
    from nucleo.canales import api

    print("\nrutas del webhook")

    atendidos = []
    vistos = set()

    api._config_de = lambda tenant: config
    api.persistencia.evento_ya_visto = lambda t, w, canal="whatsapp": (
        w in vistos or (vistos.add(w) and False))
    # El turno no llama al modelo ni envia nada: solo deja constancia.
    api._procesar_mensaje_whatsapp = lambda cfg, t, r, e: atendidos.append(e["wamid"])
    # La ruta busca un rol orientado a cliente_final en la configuracion.
    config.roles = {"cliente_final": type("R", (), {"orientado_a": "cliente_final"})()}

    cli = api.app.test_client()
    ruta = f"/canales/whatsapp/{TENANT}"

    r = cli.get(ruta, query_string={"hub.verify_token": VERIFY_TOKEN,
                                    "hub.challenge": "12345"})
    check("handshake correcto devuelve 200", r.status_code == 200)
    check("y el challenge TAL CUAL, en texto plano", r.get_data(as_text=True) == "12345")

    r = cli.get(ruta, query_string={"hub.verify_token": "incorrecto",
                                    "hub.challenge": "12345"})
    check("handshake con token incorrecto da 403", r.status_code == 403)
    check("y NO filtra el challenge", "12345" not in r.get_data(as_text=True))

    sobre = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"id": "wamid.RUTA1", "from": "573001112233", "type": "text",
         "text": {"body": "hola"}}]}}]}]}).encode()

    r = cli.post(ruta, data=sobre, content_type="application/json")
    check("webhook SIN firma da 401", r.status_code == 401)
    check("y no atiende nada", atendidos == [])

    r = cli.post(ruta, data=sobre, content_type="application/json",
                 headers={"X-Hub-Signature-256": firmar(sobre, "otro-secreto")})
    check("webhook con firma de otro secreto da 401", r.status_code == 401)
    check("y sigue sin atender nada", atendidos == [])

    r = cli.post(ruta, data=sobre, content_type="application/json",
                 headers={"X-Hub-Signature-256": firmar(sobre)})
    check("webhook firmado correctamente da 200", r.status_code == 200)
    check("y atiende el mensaje", atendidos == ["wamid.RUTA1"])

    # El caso que motiva toda la tabla de deduplicacion.
    r = cli.post(ruta, data=sobre, content_type="application/json",
                 headers={"X-Hub-Signature-256": firmar(sobre)})
    check("un reintento de Meta devuelve 200 igual", r.status_code == 200)
    check("pero NO vuelve a atender el mismo mensaje", atendidos == ["wamid.RUTA1"])

    # Un acuse de entrega llega por el mismo webhook y no es conversacion.
    acuse = json.dumps({"entry": [{"changes": [{"value": {"statuses": [
        {"id": "wamid.ACUSE", "status": "delivered",
         "recipient_id": "573001112233"}]}}]}]}).encode()
    r = cli.post(ruta, data=acuse, content_type="application/json",
                 headers={"X-Hub-Signature-256": firmar(acuse)})
    check("un acuse de entrega no despierta al modelo",
          r.status_code == 200 and atendidos == ["wamid.RUTA1"])


if __name__ == "__main__":
    main()
