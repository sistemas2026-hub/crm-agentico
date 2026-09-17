# -*- coding: utf-8 -*-
"""
================================================================================
 ENTREGA REGISTRADA  --  lo que WhatsApp respondio queda en la fila, o se dice
================================================================================

    py -3.13 tests/test_entrega_registrada.py                     (sin base)
    DBHOST=localhost DBPORT=55435 DBNAME=<base construida por el ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_entrega_registrada.py

Por que existe
--------------
Medido en produccion el 16/09/2026 (D17): una respuesta humana enviada desde la
bandeja a un WhatsApp de prueba quedo en estado_entrega='pendiente', sin wamid y
sin error, para siempre. marcar_envio() fallaba en TODAS las llamadas desde que
existe: su 'case when %s is null' no tiene tipo para psycopg 3, PostgreSQL lo
rechaza con IndeterminateDatatype, y la funcion se tragaba la excepcion. El
seguimiento de entregas figuraba como construido el 06/09 y nunca funciono.

Ninguna prueba lo vio porque ninguna prueba ejercitaba marcar_envio contra una
base de verdad. Por eso esta corre contra PostgreSQL real con psycopg 3: un mock
de la base habria aceptado ese SQL sin quejarse, que es exactamente como se
escondio el problema.

  1. el texto de un error de Meta lo escribe Dexter; lo de Meta va solo al log
  2. un solo mecanismo: ningun camino de envio llama a marcar_envio por su cuenta
  3. marcar_envio contra la base: exito, fallo, sin id, fila ajena, base rota
  4. el mecanismo completo contra la base, incluido "Meta acepto y no se guardo"
  5. punta a punta: POST de la respuesta humana -> fila con wamid
================================================================================
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Sin token de servicio: el endpoint de la parte 5 se llama sin cabecera.
os.environ.pop("MOTOR_SERVICE_TOKEN", None)

import requests                                                   # noqa: E402

from nucleo.canales import whatsapp                               # noqa: E402

fallos: list[str] = []
CRUDO = "CUERPO-CRUDO-DE-META-que-no-puede-persistirse"


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
        return True
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""), flush=True)
    return False


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


class RespuestaFalsa:
    """Lo minimo de requests.Response que usa whatsapp._rechazo."""

    def __init__(self, status, cuerpo_json=None, texto=""):
        self.status_code, self._json, self.text = status, cuerpo_json, texto

    def json(self):
        if self._json is None:
            raise ValueError("no es json")
        return self._json


# =============================================================================
titulo("1. el texto del error lo escribe Dexter")
# =============================================================================
def no_retiene_crudo(error) -> bool:
    """Ni en el texto ni en NINGUN atributo: lo que no se guarda no se filtra."""
    return CRUDO not in str(error) and all(CRUDO not in str(v) for v in vars(error).values())


sin_json = whatsapp._rechazo(RespuestaFalsa(502, None, CRUDO), "el envío")
revisar(no_retiene_crudo(sin_json),
        "una respuesta no-JSON no deja su cuerpo crudo ni en el texto ni en un atributo",
        f"{sin_json} {vars(sin_json)}")
revisar(sin_json.http_status == 502 and "HTTP 502" in str(sin_json),
        "y en su lugar dice el estado HTTP, que es lo que sirve para buscar", str(sin_json))

con_mensaje = whatsapp._rechazo(
    RespuestaFalsa(400, {"error": {"code": 131026, "message": CRUDO,
                                   "error_data": {"details": CRUDO}}}), "el envío")
revisar(no_retiene_crudo(con_mensaje) and con_mensaje.codigo == 131026,
        "un error JSON con mensaje tampoco lo retiene: queda solo el codigo",
        f"{con_mensaje} {vars(con_mensaje)}")

acuses = whatsapp.estados_entrantes({"entry": [{"changes": [{"value": {"statuses": [{
    "id": "wamid.ACUSE", "status": "failed", "recipient_id": "573001234567",
    "errors": [{"code": 131026, "message": CRUDO, "error_data": {"details": CRUDO}}]}]}}]}]})
revisar(len(acuses) == 1 and acuses[0].get("codigo") == 131026
        and CRUDO not in str(acuses[0]),
        "el parser de acuses se queda con el codigo y descarta el texto de Meta", f"{acuses}")

from nucleo.canales import api                                    # noqa: E402

conocido = api._motivo_de_envio(whatsapp.ErrorWhatsApp("x", codigo=131026))
revisar(conocido == api.MOTIVOS_DE_FALLO[131026],
        "un codigo conocido se traduce con la misma tabla que los acuses", conocido)
revisar(CRUDO not in api._motivo_de_envio(con_mensaje),
        "un codigo desconocido deja el texto de Dexter, sin lo de Meta")
revisar(api._motivo_de_envio(requests.ConnectionError(CRUDO)).startswith("No se pudo contactar"),
        "un fallo de red se dice como tal, sin el texto de la excepcion")
revisar(CRUDO not in api._motivo_de_envio(KeyError(CRUDO)),
        "una excepcion cualquiera no filtra su texto")
revisar(CRUDO not in api._motivo_de_fallo({"codigo": 999999, "detalle": CRUDO, "error": CRUDO}),
        "el acuse fallido del webhook tampoco guarda lo que dijo Meta")

WAMID = "wamid.HBgMNTczMDAxMjM0NTY3FQIAERgSQUJDREVGMTIzNDU2Nzg5MAA="
huella = api._huella_wamid(WAMID)
revisar(len(huella) == 12 and WAMID not in huella and huella == api._huella_wamid(WAMID),
        "el log lleva una huella estable del wamid, no el wamid", huella)
fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
bloque_acuses = fuente_api[fuente_api.index("huella = _huella_wamid"):
                           fuente_api.index("nuestro = ESTADOS_DE_ENTREGA.get(crudo)")]
revisar("estado.get(\"de\")" not in bloque_acuses and "estado.get('de')" not in bloque_acuses
        and "estado.get('wamid')}" not in bloque_acuses,
        "el log de acuses no imprime el telefono (ni parcial) ni el wamid entero")

# =============================================================================
titulo("2. un solo mecanismo de envio")
# =============================================================================
arbol = ast.parse((RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8"))
llamadas_fuera, usan_mecanismo = [], set()
for funcion in (n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)):
    for n in ast.walk(funcion):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "marcar_envio" and funcion.name != "_entregar_y_registrar":
                llamadas_fuera.append(f"{funcion.name}:{n.lineno}")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_entregar_y_registrar":
            usan_mecanismo.add(funcion.name)
revisar(not llamadas_fuera,
        "nadie llama a marcar_envio salvo el mecanismo unico", f"{llamadas_fuera}")
esperados = {"conversaciones_responder_humano"}
revisar(len(usan_mecanismo) == 3 and esperados <= usan_mecanismo,
        "texto, plantilla y multimedia pasan por _entregar_y_registrar",
        f"lo usan: {sorted(usan_mecanismo)}")

# =============================================================================
titulo("3 a 5. contra la base")
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] la parte con base necesita {faltan} y una base construida "
          f"por el ledger (cli/base_desde_cero.py)")
else:
    import psycopg                                                # noqa: E402

    from nucleo.persistencia import db                            # noqa: E402

    ORG, OTRA = uuid.uuid4(), uuid.uuid4()
    TENANT = f"prueba-entrega-{uuid.uuid4().hex[:8]}"
    OTRO_TENANT = f"prueba-entrega-{uuid.uuid4().hex[:8]}"
    SIN_CONFIG = f"prueba-sin-config-{uuid.uuid4().hex[:8]}"
    admin = psycopg.connect(
        host=os.environ["DBHOST"], port=os.environ["DBPORT"], dbname=os.environ["DBNAME"],
        user=os.environ["DBUSER"], password=os.environ["DBPASSWORD"], autocommit=True)

    def sembrar_org(org, slug):
        oblig = admin.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='public' and table_name='organization' "
            "and is_nullable='NO' and column_default is null").fetchall()
        valores = {"id": str(org), "name": slug, "api_key": f"clave-{org}", "company_name": slug}
        for campo, tipo in oblig:
            if campo in valores:
                continue
            valores[campo] = ("now()" if "timestamp" in tipo or tipo == "date"
                              else True if tipo == "boolean"
                              else 0 if tipo in ("integer", "bigint", "smallint", "numeric")
                              else "{}" if tipo in ("json", "jsonb", "ARRAY") else "")
        cols = ", ".join(f'"{k}"' for k in valores)
        marcas = ", ".join("now()" if v == "now()" else "%s" for v in valores.values())
        admin.execute(f"insert into public.organization ({cols}) values ({marcas})",
                      [v for v in valores.values() if v != "now()"])
        admin.execute("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)",
                      (str(org), slug))

    def conversacion(org):
        return admin.execute(
            "insert into asistente.conversations (organization_id, canal, usuario_externo, "
            "escalada_a_humano, necesita_atencion_humana) values (%s, 'whatsapp', %s, true, true) "
            "returning id", (str(org), f"57300{uuid.uuid4().int % 10**7:07d}")).fetchone()[0]

    def mensaje_pendiente(org, conv):
        return admin.execute(
            "insert into asistente.messages (organization_id, conversation_id, rol, contenido, "
            "estado_entrega) values (%s, %s, 'assistant', 'prueba', 'pendiente') returning id",
            (str(org), conv)).fetchone()[0]

    def fila(mid):
        return admin.execute("select wamid, estado_entrega, error_entrega from asistente.messages "
                             "where id = %s", (mid,)).fetchone()

    try:
        sembrar_org(ORG, TENANT)
        sembrar_org(OTRA, OTRO_TENANT)
        conv = conversacion(ORG)

        titulo("3. marcar_envio contra PostgreSQL real")
        m = mensaje_pendiente(ORG, conv)
        ok = db.marcar_envio(TENANT, m, "wamid.EXITO")
        revisar(ok is True and fila(m) == ("wamid.EXITO", "enviado", None),
                "exito: wamid guardado, 'enviado', sin error, y devuelve True", f"{ok} {fila(m)}")

        m = mensaje_pendiente(ORG, conv)
        ok = db.marcar_envio(TENANT, m, None, "No salio por algo que Dexter explica.")
        revisar(ok is True and fila(m) == (None, "fallido", "No salio por algo que Dexter explica."),
                "fallo: 'fallido' con su motivo, sin wamid, y devuelve True", f"{ok} {fila(m)}")

        m = mensaje_pendiente(ORG, conv)
        ok = db.marcar_envio(TENANT, m, None)
        w, estado, err = fila(m)
        revisar(ok is True and w is None and estado == "pendiente" and err == db.SIN_IDENTIFICADOR,
                "200 sin id: queda 'pendiente' con la explicacion", f"{ok} {fila(m)}")
        revisar(estado != "fallido",
                "y NO 'fallido': la bandeja ofreceria reintentar y el cliente lo recibiria dos veces")

        ok = db.marcar_envio(TENANT, uuid.uuid4(), "wamid.NADIE")
        revisar(ok is False, "una fila que no existe devuelve False, no True silencioso")

        conv_otra = conversacion(OTRA)
        ajena = mensaje_pendiente(OTRA, conv_otra)
        ok = db.marcar_envio(TENANT, ajena, "wamid.AJENO")
        revisar(ok is False and fila(ajena) == (None, "pendiente", None),
                "la fila de OTRA empresa no se toca y devuelve False", f"{ok} {fila(ajena)}")

        m = mensaje_pendiente(ORG, conv)
        try:
            ok = db.marcar_envio(SIN_CONFIG, m, "wamid.BASE_ROTA")
            revisar(ok is False and fila(m) == (None, "pendiente", None),
                    "si la base no puede escribir, devuelve False y no lanza", f"{ok} {fila(m)}")
        except Exception as e:
            revisar(False, "si la base no puede escribir, devuelve False y no lanza",
                    f"lanzo {type(e).__name__}")

        titulo("4. el mecanismo unico contra la base")
        import contextlib                                         # noqa: E402
        import io                                                 # noqa: E402

        def con_log(funcion):
            """Corre funcion() capturando lo que imprime: lo que iria al log."""
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                resultado = funcion()
            return resultado, salida.getvalue()

        m = mensaje_pendiente(ORG, conv)
        r = api._entregar_y_registrar(TENANT, m, lambda: "wamid.MECANISMO", "prueba")
        revisar(r == {"resultado": "aceptado", "entregado": True, "registrado": True}
                and fila(m)[1] == "enviado",
                "Meta acepta: resultado 'aceptado', entregado y registrado", f"{r} {fila(m)}")

        m = mensaje_pendiente(ORG, conv)

        def rechaza():
            # Un rechazo armado como lo arma _post, desde una respuesta que trae
            # el texto de Meta: si ese texto sobreviviera, apareceria abajo.
            raise whatsapp._rechazo(RespuestaFalsa(
                400, {"error": {"code": 131026, "message": CRUDO,
                                "error_data": {"details": CRUDO}}}), "el envío")
        r, log = con_log(lambda: api._entregar_y_registrar(TENANT, m, rechaza, "prueba"))
        revisar(r["resultado"] == "rechazado" and r["entregado"] is False
                and r["registrado"] is True and r["aviso"] == api.MOTIVOS_DE_FALLO[131026]
                and fila(m)[1] == "fallido",
                "Meta rechaza: 'fallido', aviso legible, registrado", f"{r} {fila(m)}")
        revisar(all(CRUDO not in (c or "") for c in fila(m)) and CRUDO not in str(r),
                "lo que dijo Meta no llega ni a la base ni a la respuesta")
        revisar(CRUDO not in log and "codigo=131026" in log and "http_status=400" in log,
                "y tampoco al LOG: queda solo metadata (codigo, estado HTTP)", log.strip())

        m = mensaje_pendiente(ORG, conv)
        r, log = con_log(lambda: api._entregar_y_registrar(
            TENANT, m, lambda: (_ for _ in ()).throw(requests.ConnectionError(CRUDO)), "prueba"))
        revisar(r["resultado"] == "rechazado" and CRUDO not in log and CRUDO not in str(r)
                and CRUDO not in (fila(m)[2] or ""),
                "una excepcion ajena no filtra su texto al log, la respuesta ni la base",
                log.strip())

        m = mensaje_pendiente(ORG, conv)
        r = api._entregar_y_registrar(TENANT, m, lambda: None, "prueba")
        revisar(r == {"resultado": "sin_id", "entregado": False, "registrado": True}
                and fila(m)[1] == "pendiente",
                "200 sin id: 'sin_id', no se da por entregado y no hay aviso", f"{r} {fila(m)}")

        titulo("4b. Meta acepto y la base NO lo guardo: entrega incierta")
        m = mensaje_pendiente(ORG, conv)
        llamadas = []

        def acepta():
            llamadas.append(1)
            return "wamid.NO_GUARDADO"
        r, log = con_log(lambda: api._entregar_y_registrar(SIN_CONFIG, m, acepta, "prueba"))
        revisar(r["resultado"] == "aceptado_sin_registro" and r["entregado"] is True
                and r["registrado"] is False,
                "se distingue como 'aceptado_sin_registro', no como exito ni como fallo", f"{r}")
        revisar(len(llamadas) == 1,
                "el envio se hizo UNA sola vez: no hay reenvio automatico", f"{len(llamadas)} envios")
        revisar("aviso" not in r,
                "sin aviso: la bandeja no dice 'No le llego al cliente' ni ofrece Reintentar")
        revisar(fila(m)[1] != "fallido",
                "y la fila no queda 'fallido', que tambien ofreceria reintentar", f"{fila(m)}")
        revisar("ENTREGA INCIERTA" in log and "no reenviar" in log,
                "el log lo dice como entrega incierta, para que nadie la reenvie a mano", log.strip())

        titulo("5. punta a punta: la respuesta humana desde el endpoint")
        enviar_original, config_original = whatsapp.enviar_texto, api._config_de
        whatsapp.enviar_texto = lambda config, tenant, para, texto: "wamid.PUNTA_A_PUNTA"
        api._config_de = lambda tenant: object()
        try:
            cliente = api.app.test_client()
            resp = cliente.post(f"/conversaciones/{conv}/mensajes",
                                json={"tenant": TENANT, "mensaje": "respuesta de prueba"})
            datos = resp.get_json() or {}
            mid = datos.get("mensaje_id")
            revisar(resp.status_code == 201 and datos.get("entregado") is True
                    and datos.get("registrado") is True,
                    "el endpoint responde entregado y registrado", f"{resp.status_code} {datos}")
            revisar(bool(mid) and fila(mid) == ("wamid.PUNTA_A_PUNTA", "enviado", None),
                    "y la fila creada por el endpoint tiene el wamid y 'enviado' (G9-A en local)",
                    f"{fila(mid) if mid else 'sin mensaje_id'}")
            atendida = admin.execute("select atendida_manual from asistente.conversations "
                                     "where id = %s", (conv,)).fetchone()[0]
            revisar(atendida is True, "la conversacion queda atendida por una persona")

            # Y el acuse posterior del webhook ahora SI tiene con que casar.
            casado = db.marcar_entrega(TENANT, "wamid.PUNTA_A_PUNTA", "entregado")
            revisar(casado is True and fila(mid)[1] == "entregado",
                    "un acuse con ese wamid avanza la misma fila a 'entregado' (G9-B en local)",
                    f"{casado} {fila(mid)}")
        finally:
            whatsapp.enviar_texto, api._config_de = enviar_original, config_original
    finally:
        admin.execute("delete from public.organization where id in (%s, %s)", (str(ORG), str(OTRA)))
        admin.close()

print()
if fallos:
    print(f"FALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("OK: lo que respondio WhatsApp queda en la fila, o se dice que no quedo")
