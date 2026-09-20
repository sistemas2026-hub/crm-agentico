# -*- coding: utf-8 -*-
"""
================================================================================
 B4 -- LA COLA DE EFECTOS EXTERNOS  (contrato del relevo §3.6)
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_b4_sincronizaciones.py

Por que existe
--------------
Escalar produce dos cosas afuera: un caso en el CRM y, cuando corresponde, un
ticket en el sistema del ISP. Antes de B4, si alguna fallaba, el except la
mandaba al log y la intencion se perdia -- la conversacion quedaba escalada,
visible en la bandeja, y sin caso, hasta que alguien lo buscaba a mano.

Lo que estas pruebas protegen NO es que la cola exista, sino las dos reglas que
la hacen segura:

  1. LAS DOS VELOCIDADES. crear_caso se reintenta porque su idempotencia esta
     demostrada del lado de afuera. crear_ticket con resultado INCIERTO no se
     reintenta jamas: la API de WispHub no permite preguntar "¿esto ya se
     hizo?" (gate Q2). Un reintento a ciegas manda dos visitas tecnicas al
     mismo cliente, y eso no se deshace.

  2. QUE NADIE TOME EL MISMO TRABAJO DOS VECES. Dos reconciliadores corriendo
     a la vez no pueden crear dos casos para la misma conversacion.

  1. la cola: encolar, idempotencia, elegibles
  2. el candado: concurrencia real con dos conexiones
  3. los desenlaces, con la regla de Q2
  4. aislamiento entre empresas
  5. lo que NO sale a la pantalla
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}", flush=True)
    else:
        print(f"  [FALLA] {que}", flush=True)
        if porque:
            print(f"         {porque}", flush=True)
        fallos.append(que)


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] necesita {faltan} y una base construida por el ledger")
    sys.exit(0)

os.environ.pop("MOTOR_SERVICE_TOKEN", None)

import psycopg                                                    # noqa: E402

from nucleo.persistencia import db                                # noqa: E402
from nucleo.relevo import reconciliador                           # noqa: E402
from nucleo.relevo.reconciliador import ResultadoEfecto           # noqa: E402

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()
T_A = f"prueba-b4-{uuid.uuid4().hex[:8]}"
T_B = f"prueba-b4-{uuid.uuid4().hex[:8]}"
DATOS = dict(host=os.environ["DBHOST"], port=os.environ["DBPORT"],
             dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
             password=os.environ["DBPASSWORD"])
admin = psycopg.connect(**DATOS, autocommit=True)


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
        "insert into asistente.conversations (organization_id, canal, usuario_externo, estado) "
        "values (%s, 'whatsapp', %s, 'abierta') returning id",
        (str(org), f"57300{uuid.uuid4().int % 10**7:07d}")).fetchone()[0]


def encolar(tenant, org, conv, tipo, clave, datos=None):
    with db.sesion(tenant) as (cur, o):
        return db.encolar_sincronizacion(cur, o, conv, tipo=tipo, clave=clave,
                                         datos=datos or {"motivo": "prueba"})


def fila(sid):
    return admin.execute(
        "select estado, intentos, ultimo_error_clase, ultimo_error_codigo, "
        "referencia_externa, proximo_intento_en from "
        "asistente.sincronizaciones_externas where id = %s", (sid,)).fetchone()


try:
    sembrar_org(ORG_A, T_A)
    sembrar_org(ORG_B, T_B)

    # =========================================================================
    titulo("1. la cola")
    # =========================================================================
    conv = conversacion(ORG_A)
    sid = encolar(T_A, ORG_A, conv, "crear_caso", f"crear_caso:{conv}")
    revisar(sid is not None, "encolar devuelve el id del trabajo")
    revisar(fila(sid)[0] == "pendiente" and fila(sid)[5] is not None,
            "nace pendiente y CON hora: sin ella seria invisible para T20",
            f"{fila(sid)}")

    repetido = encolar(T_A, ORG_A, conv, "crear_caso", f"crear_caso:{conv}")
    n = admin.execute("select count(*) from asistente.sincronizaciones_externas "
                      "where conversation_id = %s", (conv,)).fetchone()[0]
    revisar(repetido is None and n == 1,
            "la misma transicion reintentada NO encola dos veces el mismo efecto",
            f"{n} filas")

    elegibles = db.sincronizaciones_elegibles(T_A)
    revisar(any(str(e["id"]) == sid for e in elegibles),
            "un pendiente con la hora cumplida es elegible")

    # Lo terminal no vuelve a la cola nunca: espera a una persona, no a un reloj.
    conv_t = conversacion(ORG_A)
    sid_t = encolar(T_A, ORG_A, conv_t, "crear_ticket", f"t:{conv_t}")
    db.resolver_sincronizacion(T_A, sid_t, estado="desconocida",
                               error_clase="incierto", error_codigo="timeout")
    revisar(all(str(e["id"]) != sid_t for e in db.sincronizaciones_elegibles(T_A)),
            "lo que quedo 'desconocida' NO vuelve a la cola de reintentos")
    revisar(fila(sid_t)[5] is None,
            "y se le borra la hora del proximo intento", f"{fila(sid_t)}")

    # =========================================================================
    titulo("2. el candado: dos reconciliadores a la vez")
    # =========================================================================
    conv2 = conversacion(ORG_A)
    sid2 = encolar(T_A, ORG_A, conv2, "crear_caso", f"crear_caso:{conv2}")

    primero = db.tomar_sincronizacion(T_A, sid2)
    segundo = db.tomar_sincronizacion(T_A, sid2)
    revisar(primero is True and segundo is False,
            "solo UNO de los dos se queda con el trabajo",
            f"{primero} {segundo}")
    revisar(fila(sid2)[1] == 1,
            "y el contador de intentos sube una sola vez", f"intentos={fila(sid2)[1]}")

    # El mismo candado, pero con dos conexiones reales compitiendo.
    conv3 = conversacion(ORG_A)
    sid3 = encolar(T_A, ORG_A, conv3, "crear_caso", f"crear_caso:{conv3}")
    upd = ("update asistente.sincronizaciones_externas set estado = 'en_curso', "
           "intentos = intentos + 1 where organization_id = %s and id = %s "
           "and estado = 'pendiente'")
    with psycopg.connect(**DATOS) as ca, psycopg.connect(**DATOS) as cb:
        ra = ca.execute(upd, (str(ORG_A), sid3)).rowcount
        cb.execute("set local lock_timeout = '700ms'")
        try:
            cb.execute(upd, (str(ORG_A), sid3))
            bloqueo = False
        except (psycopg.errors.LockNotAvailable, psycopg.errors.QueryCanceled):
            bloqueo = True
        cb.rollback()
        ca.commit()
        rb = cb.execute(upd, (str(ORG_A), sid3)).rowcount
        cb.commit()
    revisar(ra == 1 and bloqueo and rb == 0,
            "con dos conexiones reales: la segunda se bloquea y despues NO lo toma",
            f"a={ra} bloqueo={bloqueo} b={rb}")

    # =========================================================================
    titulo("3. los desenlaces, y la regla de Q2")
    # =========================================================================
    def correr_con(tipo, clase, codigo=None, referencia=None):
        c = conversacion(ORG_A)
        s = encolar(T_A, ORG_A, c, tipo, f"{tipo}:{c}")
        trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200)
                       if str(t["id"]) == s)
        reconciliador.procesar_una(
            T_A, trabajo,
            lambda *_: ResultadoEfecto(clase, codigo=codigo, referencia=referencia))
        return s, fila(s)

    s, f = correr_con("crear_caso", "exito", referencia="CASO-1")
    revisar(f[0] == "hecha" and f[4] == "CASO-1",
            "exito: queda 'hecha' con su referencia externa", f"{f}")

    # EL CASO QUE DEFINE B4.
    s, f = correr_con("crear_ticket", "incierto", codigo="timeout")
    revisar(f[0] == "desconocida",
            "crear_ticket INCIERTO queda 'desconocida', NO se reintenta", f"{f}")
    revisar(f[2] == "incierto" and f[5] is None,
            "con su causa y sin proximo intento", f"{f}")

    s, f = correr_con("crear_caso", "incierto", codigo="timeout")
    revisar(f[0] == "pendiente",
            "el MISMO incierto en crear_caso SI vuelve a la cola: se puede "
            "preguntar si ya existe", f"{f}")

    s, f = correr_con("crear_ticket", "transitorio", codigo="502")
    revisar(f[0] == "pendiente",
            "un transitorio de crear_ticket si se reintenta: no llego a salir", f"{f}")

    s, f = correr_con("crear_caso", "permanente", codigo="400")
    revisar(f[0] == "fallida_definitiva" and f[2] == "permanente",
            "un permanente no se reintenta y queda con su causa", f"{f}")

    # Una excepcion del ejecutor NO es "no salio": el pedido pudo haber viajado.
    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "crear_ticket", f"exc:{c}")
    trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s)

    def explota(*_):
        raise RuntimeError("se corto la conexion")

    reconciliador.procesar_una(T_A, trabajo, explota)
    revisar(fila(s)[0] == "desconocida",
            "una excepcion al ejecutar tambien es incierta, no un fallo", f"{fila(s)}")

    # Agotar los reintentos NO convierte un transitorio en 'desconocida'.
    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "crear_caso", f"agota:{c}")
    for _ in range(db.MAX_INTENTOS_SINCRONIZACION + 1):
        elegible = [t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s]
        if not elegible:
            admin.execute("update asistente.sincronizaciones_externas "
                          "set proximo_intento_en = now() where id = %s", (s,))
            elegible = [t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s]
        if not elegible:
            break
        reconciliador.procesar_una(T_A, elegible[0],
                                   lambda *_: ResultadoEfecto("transitorio", codigo="502"))
    revisar(fila(s)[0] == "fallida_definitiva",
            "pasados los intentos, un transitorio es 'fallida_definitiva'", f"{fila(s)}")

    # =========================================================================
    titulo("4. aislamiento entre empresas")
    # =========================================================================
    conv_b = conversacion(ORG_B)
    sid_b = encolar(T_B, ORG_B, conv_b, "crear_caso", f"crear_caso:{conv_b}")
    revisar(all(str(e["id"]) != sid_b for e in db.sincronizaciones_elegibles(T_A, 200)),
            "la empresa A no toma trabajos de B")
    revisar(db.tomar_sincronizacion(T_A, sid_b) is False,
            "y no puede tomarlo ni con el id en la mano")
    revisar(db.sincronizaciones_de(T_A, conv_b) == [],
            "ni ver sus sincronizaciones")
    revisar(len(db.sincronizaciones_de(T_B, conv_b)) == 1, "pero B si ve las suyas")

    # La misma clave en otra empresa es otro trabajo: no se pisan.
    revisar(encolar(T_B, ORG_B, conv_b, "crear_caso", f"crear_caso:{conv}") is not None,
            "la misma clave en OTRA empresa es otro trabajo")

    # =========================================================================
    titulo("5. lo que NO sale a la pantalla")
    # =========================================================================
    c = conversacion(ORG_A)
    encolar(T_A, ORG_A, c, "crear_caso", f"pii:{c}",
            datos={"motivo": "queja", "secreto_interno": "NO-DEBE-SALIR"})
    from nucleo.canales import api                                # noqa: E402
    api.app.config["TESTING"] = True
    cliente = api.app.test_client()
    r = cliente.get(f"/conversaciones/{c}/sincronizaciones?tenant={T_A}")
    crudo = str(r.get_json())
    revisar("NO-DEBE-SALIR" not in crudo and "datos_intencion" not in crudo,
            "la intencion NO viaja a la pantalla: solo que falto y si hay que mirarlo")
    revisar((r.get_json() or {}).get("sincronizaciones")[0]["tipo"] == "crear_caso",
            "pero si el tipo y su estado", f"{r.get_json()}")
    revisar(cliente.get(f"/conversaciones/{c}/sincronizaciones?tenant={T_B}")
            .get_json().get("sincronizaciones") == [],
            "y otra empresa no ve nada por el endpoint")
finally:
    admin.close()

print(f"\n{'=' * 76}")
if fallos:
    print(f"\nFALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\nOK: la cola reintenta lo que puede repetirse y deja lo demas para una persona")
