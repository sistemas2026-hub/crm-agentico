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
    # =========================================================================
    titulo("6. el ejecutor real de crear_caso")
    # =========================================================================
    from nucleo.relevo import efectos_externos                   # noqa: E402

    NOMBRE = f"Sin internet - Ana - {uuid.uuid4()}"

    def ejecutar_con(crear, buscar):
        c = conversacion(ORG_A)
        s = encolar(T_A, ORG_A, c, "crear_caso", f"ej:{c}",
                    datos={"nombre_caso": NOMBRE, "descripcion": "x"})
        trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200)
                       if str(t["id"]) == s)
        reconciliador.procesar_una(
            T_A, trabajo,
            efectos_externos.ejecutor(None, T_A, crear=crear, buscar_por_nombre=buscar))
        return fila(s)

    creados = []

    def crear_ok(nombre, datos):
        creados.append(nombre)
        return "CASO-NUEVO"

    f = ejecutar_con(crear_ok, lambda n: None)
    revisar(f[0] == "hecha" and f[4] == "CASO-NUEVO",
            "no existia: se crea y queda su id", f"{f}")

    # EL CASO QUE HACE SEGURO EL REINTENTO.
    creados.clear()
    f = ejecutar_con(crear_ok, lambda n: "CASO-VIEJO")
    revisar(f[0] == "hecha" and f[4] == "CASO-VIEJO" and creados == [],
            "si YA existia se adopta y NO se crea un segundo caso",
            f"{f} creados={creados}")

    # Buscar primero no es un detalle de orden: es lo que evita el duplicado.
    def crear_no_deberia(nombre, datos):
        creados.append(nombre)
        return "NO-DEBIO-CREARSE"

    creados.clear()
    f = ejecutar_con(crear_no_deberia, lambda n: "YA-ESTA")
    revisar(creados == [], "no se llama a crear cuando la busqueda encontro uno",
            f"creados={creados}")

    # Si no se puede BUSCAR, no se crea a ciegas.
    def buscar_roto(n):
        raise RuntimeError("CRM caido")

    creados.clear()
    f = ejecutar_con(crear_no_deberia, buscar_roto)
    revisar(f[0] == "pendiente" and creados == [],
            "si la busqueda falla NO se crea a ciegas: se reintenta entero",
            f"{f} creados={creados}")

    # El CRM acepta y no devuelve id: pudo quedar creado. No se crea otro.
    f = ejecutar_con(lambda n, d: None, lambda n: None)
    revisar(f[0] == "pendiente" and f[2] == "incierto",
            "sin id de vuelta queda incierto: el proximo ciclo lo adopta", f"{f}")

    # Carrera: 400 de nombre repetido entre la busqueda y la creacion.
    class Repetido(Exception):
        http_status = 400

    def crear_choca(n, d):
        raise Repetido()

    llamadas = {"n": 0}

    def buscar_despues(n):
        llamadas["n"] += 1
        return None if llamadas["n"] == 1 else "CASO-DE-LA-CARRERA"

    f = ejecutar_con(crear_choca, buscar_despues)
    revisar(f[0] == "hecha" and f[4] == "CASO-DE-LA-CARRERA",
            "una carrera con 400 se resuelve adoptando el que gano", f"{f}")

    # =========================================================================
    titulo("6b. el ejecutor real de cerrar_caso (B6)")
    # =========================================================================
    # Lo que hace seguro este efecto es LEER PRIMERO. Medido contra el CRM real
    # (django-crm/backend/cases/tests/test_cierre_idempotente.py): un PATCH
    # sobre un caso ya cerrado responde 200 y le reescribe 'closed_on' con la
    # fecha del reintento, asi que el caso pasa a decir que se cerro un dia en
    # el que no se cerro.
    CASO = str(uuid.uuid4())

    def cerrar_con(lecturas, cerrar):
        """`lecturas` se consume en orden: la primera es el ANTES, la segunda
        la relectura de confirmacion."""
        c = conversacion(ORG_A)
        s = encolar(T_A, ORG_A, c, "cerrar_caso", f"cc:{c}",
                    datos={"caso_id": CASO})
        trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200)
                       if str(t["id"]) == s)
        pendientes = list(lecturas)

        def leer(_id):
            r = pendientes.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        reconciliador.procesar_una(
            T_A, trabajo,
            efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                      buscar_por_nombre=lambda n: None,
                                      leer_caso=leer, cerrar_caso_crm=cerrar))
        return fila(s)

    escrituras = []

    def cerrar_ok(caso_id):
        escrituras.append(caso_id)
        return {"id": caso_id}

    f = cerrar_con([{"status": "New"}, {"status": "Closed"}], cerrar_ok)
    revisar(f[0] == "hecha" and escrituras == [CASO],
            "abierto: se cierra y se CONFIRMA releyendo", f"{f}")

    # EL CASO QUE HACE SEGURO EL REINTENTO, y el que la medicion justifica.
    escrituras.clear()
    f = cerrar_con([{"status": "Closed"}], cerrar_ok)
    revisar(f[0] == "hecha" and escrituras == [],
            "ya cerrado: se adopta y NO se reescribe",
            "Un PATCH ciego le correria la fecha de cierre (medido). Esta "
            "linea es la que impide que un reintento reescriba el pasado.")

    escrituras.clear()
    f = cerrar_con([{"status": "Rejected"}], cerrar_ok)
    revisar(f[0] == "hecha" and escrituras == [],
            "y 'Rejected' tambien cuenta como terminado")

    # No poder LEER no autoriza a escribir.
    escrituras.clear()
    f = cerrar_con([RuntimeError("CRM caido")], cerrar_ok)
    revisar(f[0] == "pendiente" and escrituras == [],
            "si no se puede leer, NO se escribe: vuelve a la cola", f"{f}")

    escrituras.clear()
    f = cerrar_con([{"sin": "status"}], cerrar_ok)
    revisar(f[0] == "pendiente" and escrituras == [],
            "y una respuesta que no se entiende tampoco autoriza a escribir")

    # Acepto y no cerro: insistir daria lo mismo.
    escrituras.clear()
    f = cerrar_con([{"status": "New"}, {"status": "New"}], cerrar_ok)
    revisar(f[0] == "fallida_definitiva" and f[2] == "permanente",
            "acepto y el caso NO quedo cerrado: permanente y visible", f"{f}")

    # No se pudo confirmar. El pedido PUDO haber llegado -- y aqui, a
    # diferencia de crear_ticket, eso SI se puede resolver preguntando: el
    # proximo intento lee primero y adopta el cierre si ya ocurrio. Por eso
    # vuelve a la cola en vez de quedar 'desconocida'.
    f = cerrar_con([{"status": "New"}, RuntimeError("timeout")], cerrar_ok)
    revisar(f[0] == "pendiente" and f[2] == "incierto",
            "sin confirmacion vuelve a la cola: el reintento pregunta antes",
            f"Esa es toda la diferencia con Q2: alli no hay a quien preguntar. {f}")

    # Un rechazo legitimo del CRM: la regla de aprobacion previa al cierre.
    def cerrar_400(caso_id):
        e = RuntimeError("approval required")
        e.codigo_http = 400
        raise e

    f = cerrar_con([{"status": "New"}], cerrar_400)
    revisar(f[0] == "fallida_definitiva" and f[2] == "permanente",
            "un 400 del CRM (hace falta una aprobacion) no se reintenta",
            "Necesita que una persona apruebe, no un temporizador. Medido: "
            "TestCerrarCasoPuedeSerRechazado.")

    # Sin LAS DOS capacidades no se intenta nada.
    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "cerrar_caso", f"sincap:{c}", datos={"caso_id": CASO})
    trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s)
    reconciliador.procesar_una(
        T_A, trabajo,
        efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                  buscar_por_nombre=lambda n: None,
                                  leer_caso=None, cerrar_caso_crm=cerrar_ok))
    revisar(fila(s)[0] == "fallida_definitiva"
            and "sin_ejecutor" in (fila(s)[3] or ""),
            "sin la capacidad de LEER no se cierra nada", f"{fila(s)}")

    # Un tipo sin ejecutor no es una duda: no ocurrio y no va a ocurrir solo.
    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "cerrar_ticket", f"sinej:{c}")
    trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s)
    reconciliador.procesar_una(
        T_A, trabajo,
        efectos_externos.ejecutor(None, T_A, crear=crear_ok, buscar_por_nombre=lambda n: None))
    revisar(fila(s)[0] == "fallida_definitiva" and fila(s)[2] == "permanente",
            "un tipo sin ejecutor queda fallida_definitiva, no 'desconocida'",
            f"{fila(s)}")


    # =========================================================================
    titulo("6c. crear_ticket: a lo sumo UN POST por intencion (Q2.1)")
    # =========================================================================
    # WispHub no acepta clave de idempotencia y no deja buscar por nada util
    # (Q2). Lo que si se puede es embeber una referencia propia en
    # 'descripcion' --medido: sobrevive exacta y viene en el listado-- y
    # recuperarla barriendo una ventana. De ahi sale toda la regla.
    REF = efectos_externos.referencia_de("crear_ticket:conv-1:ev-1")

    revisar(REF.startswith("DEXTER_REF:") and len(REF) == len("DEXTER_REF:") + 32,
            f"la referencia sale de la clave idempotente ({REF[:24]}...)")
    revisar(efectos_externos.referencia_de("a") != efectos_externos.referencia_de("b"),
            "dos intenciones distintas dan referencias distintas",
            "Una misma conversacion puede generar mas de un ticket legitimo.")

    posts = []

    def crear_ok(ref, datos):
        posts.append(ref)
        return "T-NUEVO"

    def ticket_con(busquedas, crear=crear_ok):
        """`busquedas` se consume en orden: antes del POST y, si hace falta,
        despues."""
        pendientes = list(busquedas)

        def buscar(ref):
            r = pendientes.pop(0) if pendientes else []
            if isinstance(r, Exception):
                raise r
            return r
        c = conversacion(ORG_A)
        s = encolar(T_A, ORG_A, c, "crear_ticket", f"ct:{c}",
                    datos={"referencia": REF, "servicio": 6555})
        trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200)
                       if str(t["id"]) == s)
        reconciliador.procesar_una(
            T_A, trabajo,
            efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                      buscar_por_nombre=lambda n: None,
                                      crear_ticket_isp=crear,
                                      buscar_ticket_por_referencia=buscar))
        return fila(s)

    posts.clear()
    f = ticket_con([[]])                       # no existe -> se crea
    revisar(f[0] == "hecha" and f[4] == "T-NUEVO" and posts == [REF],
            f"no existia: se crea UNA vez y queda su id ({f[0]}, {posts})")

    # EL CASO QUE HACE SEGURA LA VIA. Un intento anterior lo creo y murio
    # antes de anotarlo: se busca ANTES, aparece, y NO se crea otro.
    posts.clear()
    f = ticket_con([["T-VIEJO"]])
    revisar(f[0] == "hecha" and f[4] == "T-VIEJO" and posts == [],
            f"ya existia con esa referencia: se adopta y NO se crea otro ({posts})",
            "Sin esto, dos POST de la misma intencion son dos visitas tecnicas "
            "al mismo cliente.")

    # No poder BUSCAR no autoriza a crear.
    posts.clear()
    f = ticket_con([RuntimeError("API caida")])
    revisar(f[0] == "pendiente" and posts == [],
            f"si no se puede buscar, NO se crea a ciegas ({f[0]}, {posts})")

    # Timeout del POST: se busca, aparece, se adopta. UN solo POST.
    def crear_incierto(ref, datos):
        posts.append(ref)
        raise RuntimeError("timeout")

    posts.clear()
    f = ticket_con([[], ["T-QUEDO"]], crear=crear_incierto)
    revisar(f[0] == "hecha" and f[4] == "T-QUEDO" and len(posts) == 1,
            f"POST incierto -> se BUSCA y se adopta, sin segundo POST ({f[0]}, {len(posts)})",
            "Es la unica recuperacion posible: WispHub no devuelve nada con que "
            "reconciliar un reintento.")

    posts.clear()
    f = ticket_con([[], []], crear=crear_incierto)
    revisar(f[0] == "desconocida" and len(posts) == 1,
            f"POST incierto y no aparece -> desconocida, NUNCA otro POST ({f[0]})",
            "0 coincidencias no autoriza a recrear: puede ser que no exista o "
            "que todavia no se vea. Ninguna de las dos habilita un segundo POST.")

    posts.clear()
    f = ticket_con([["T-1", "T-2"]])
    revisar(f[0] == "desconocida" and posts == []
            and f[3] == "varias_coincidencias",
            f">1 coincidencia -> desconocida, y el motivo lo DICE ({f[0]}/{f[3]})",
            "Ya hay un duplicado. Elegir uno lo tapa; crear otro lo empeora.")

    # Acepto y no devolvio id: tampoco se crea otro.
    posts.clear()
    f = ticket_con([[], ["T-SIN-ID"]], crear=lambda r, d: posts.append(r) or None)
    revisar(f[0] == "hecha" and f[4] == "T-SIN-ID" and len(posts) == 1,
            f"acepto sin devolver id -> se busca y se adopta ({f[0]})")

    # Sin referencia no hay idempotencia: no se intenta.
    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "crear_ticket", f"ctsr:{c}", datos={"servicio": 1})
    trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s)
    posts.clear()
    reconciliador.procesar_una(
        T_A, trabajo,
        efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                  buscar_por_nombre=lambda n: None,
                                  crear_ticket_isp=crear_ok,
                                  buscar_ticket_por_referencia=lambda r: []))
    revisar(fila(s)[0] == "fallida_definitiva" and posts == [],
            f"sin referencia NO se crea nada ({fila(s)[0]})")

    # Sin capacidad de buscar, no se intenta siquiera.
    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "crear_ticket", f"ctsc:{c}", datos={"referencia": REF})
    trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s)
    posts.clear()
    reconciliador.procesar_una(
        T_A, trabajo,
        efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                  buscar_por_nombre=lambda n: None,
                                  crear_ticket_isp=crear_ok,
                                  buscar_ticket_por_referencia=None))
    revisar(fila(s)[0] == "fallida_definitiva" and posts == [],
            "sin la capacidad de BUSCAR no se crea ningun ticket",
            "Poder escribir sin poder preguntar es lo que Q2 prohibe.")

    # =========================================================================
    titulo("6d. cerrar_ticket: leer, cerrar por PUT, releer (B6)")
    # =========================================================================
    escrituras = []

    def cerrar_ok(tid):
        escrituras.append(tid)
        return {"id_ticket": tid}

    def cerrar_con(lecturas, cerrar=cerrar_ok):
        pendientes = list(lecturas)

        def leer(tid):
            r = pendientes.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        c = conversacion(ORG_A)
        s = encolar(T_A, ORG_A, c, "cerrar_ticket", f"xt:{c}",
                    datos={"ticket": "90354"})
        trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200)
                       if str(t["id"]) == s)
        reconciliador.procesar_una(
            T_A, trabajo,
            efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                      buscar_por_nombre=lambda n: None,
                                      leer_ticket=leer, cerrar_ticket_isp=cerrar))
        return fila(s)

    escrituras.clear()
    f = cerrar_con([{"estado": "Nuevo"}, {"estado": "Cerrado"}])
    revisar(f[0] == "hecha" and escrituras == ["90354"],
            f"abierto: se cierra y se CONFIRMA releyendo ({f[0]})")

    escrituras.clear()
    f = cerrar_con([{"estado": "Cerrado"}])
    revisar(f[0] == "hecha" and escrituras == [],
            "ya cerrado: se adopta y NO se reescribe",
            "Medido el 21/09/2026: un PUT repetido le mueve 'fecha_fin' de "
            "14:42:10 a 14:42:12, sin error. El ticket pasa a decir que se "
            "cerro en un momento en que no se cerro.")

    escrituras.clear()
    f = cerrar_con([RuntimeError("500")])
    revisar(f[0] == "pendiente" and escrituras == [],
            f"si no se puede leer, NO se escribe ({f[0]})")

    escrituras.clear()
    f = cerrar_con([{"sin": "estado"}])
    revisar(f[0] == "pendiente" and escrituras == [],
            "y un estado ilegible tampoco autoriza a escribir")

    escrituras.clear()
    f = cerrar_con([{"estado": "Nuevo"}, {"estado": "Nuevo"}])
    revisar(f[0] == "fallida_definitiva" and f[2] == "permanente",
            f"acepto y el ticket NO quedo cerrado -> permanente y visible ({f[0]})",
            "El codigo de estado dice que el pedido se acepto, no que el "
            "ticket se haya cerrado.")

    f = cerrar_con([{"estado": "Nuevo"}, RuntimeError("timeout")])
    revisar(f[0] == "desconocida",
            f"sin confirmacion -> desconocida, espera a una persona ({f[0]})")

    # La etiqueta, no el codigo: se escribe 4 y se lee 'Cerrado'.
    escrituras.clear()
    f = cerrar_con([{"estado": "4"}, {"estado": "Cerrado"}])
    revisar(escrituras == ["90354"],
            "un '4' en la LECTURA no cuenta como cerrado",
            "WispHub escribe por codigo y lee por etiqueta. Comparar el numero "
            "contra el GET no funciona nunca.")

    c = conversacion(ORG_A)
    s = encolar(T_A, ORG_A, c, "cerrar_ticket", f"xtsc:{c}", datos={"ticket": "1"})
    trabajo = next(t for t in db.sincronizaciones_elegibles(T_A, 200) if str(t["id"]) == s)
    escrituras.clear()
    reconciliador.procesar_una(
        T_A, trabajo,
        efectos_externos.ejecutor(None, T_A, crear=crear_ok,
                                  buscar_por_nombre=lambda n: None,
                                  leer_ticket=None, cerrar_ticket_isp=cerrar_ok))
    revisar(fila(s)[0] == "fallida_definitiva" and escrituras == [],
            "sin la capacidad de LEER no se cierra ningun ticket")

    # Y NUNCA por /respuesta/: esa via publica un comentario en cada intento.
    #
    # Se mide sobre el CODIGO, sin el docstring. El docstring nombra
    # '/respuesta/' justamente para decir que NO se usa, asi que una busqueda
    # de texto se pone roja por la frase que defiende la regla -- es el mismo
    # error que ya aparecio varias veces en esta rama.
    import ast as _ast

    fuente_ef = (RAIZ / "nucleo" / "relevo" / "efectos_externos.py").read_text(encoding="utf-8")
    funcion = next(n for n in _ast.walk(_ast.parse(fuente_ef))
                   if isinstance(n, _ast.FunctionDef) and n.name == "cerrar_ticket")
    cuerpo = list(funcion.body)
    if (cuerpo and isinstance(cuerpo[0], _ast.Expr)
            and isinstance(cuerpo[0].value, _ast.Constant)):
        cuerpo = cuerpo[1:]                      # fuera el docstring
    codigo_cerrar = "\n".join(_ast.unparse(n) for n in cuerpo)
    revisar("respuesta" not in codigo_cerrar,
            "el cierre no usa '/respuesta/' en ninguna parte de su codigo",
            "Esa via exige un texto y lo PUBLICA: cada reintento le deja al "
            "cliente otra copia del mensaje de cierre.")

    # =========================================================================
    titulo("7. el worker")
    # =========================================================================
    from nucleo.relevo import worker_reconciliador as worker      # noqa: E402

    revisar(worker.INTERVALO_SEGUNDOS == 300,
            "la cadencia es de 5 minutos", f"{worker.INTERVALO_SEGUNDOS}")
    os.environ.pop("RECONCILIADOR_HABILITADO", None)
    revisar(worker.encendido() is False,
            "apagado por defecto: encenderlo es G7, no un descuido")
    revisar(worker.main(["--once"]) == 0,
            "con el interruptor en 0, una pasada no hace nada y sale bien")
    os.environ["RECONCILIADOR_HABILITADO"] = "1"
    revisar(worker.encendido() is True, "y su interruptor es PROPIO, no el del reloj general")
    os.environ.pop("RECONCILIADOR_HABILITADO", None)
finally:
    admin.close()

print(f"\n{'=' * 76}")
if fallos:
    print(f"\nFALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\nOK: la cola reintenta lo que puede repetirse y deja lo demas para una persona")
