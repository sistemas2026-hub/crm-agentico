# -*- coding: utf-8 -*-
"""
================================================================================
 LA BANDEJA POR CHAT Y T21  --  contra PostgreSQL, por las rutas reales
================================================================================

    DBHOST=127.0.0.1 DBPORT=55450 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_bandeja_por_chat_base.py

21/10/2026. SPEC/objetivos/bandeja-como-whatsapp.md, criterios 2 y 4.
Base efimera del ledger (cli/base_desde_cero.py), nunca la local ni la de
produccion. Ninguna llamada sale a Meta: el envio se sustituye por un doble que
anota a quien se le habria escrito.

  A. LA LISTA Y EL HILO. Un numero con una cerrada por una persona (T17), una
     cerrada por inactividad (T18), una abierta escalada vieja y una abierta
     nueva que atiende la IA:
       - GET /conversaciones?por_numero=1 -> UNA fila; representa la abierta
         mas reciente por creado_en; la banda es la de la escalada; las dos
         abiertas visibles; el mismo numero en el simulador y en otra empresa
         no se mezcla. Sin el parametro, una fila por conversacion, como hoy.
       - Y donde cae el proximo mensaje del cliente con dos abiertas: en la
         que se movio ultima (registrar_mensaje no cambia) -- por eso el chat
         tiene que mostrar las dos. La fila lleva el estado ENTERO de la
         urgente (escalada, desde cuando), no solo su banda.
       - GET /conversaciones/<id>/hilo -> las anteriores, de la mas vieja a la
         mas nueva, con la marca de cierre SOLO con lo registrado, paginado.
  B. T21. Escribirle a un chat cerrado abre una conversacion nueva, en manos
     de quien escribe; la cerrada queda byte a byte igual; el reintento no
     abre otra; fuera de las 24 h el texto se rechaza sin crear nada y la
     plantilla pasa; un numero de baja no recibe la plantilla; la respuesta
     del cliente cae en la conversacion nueva. Y X26: el motor ya no le acepta
     texto ni media a una conversacion cerrada.
  C. Lo del auditor de frontera: carreras de cierre, la misma clave.
  D. Lo del auditor independiente: responder desde el CASO de una
     conversacion cerrada llega al cliente y al ticket, dos veces; T21 no
     corre en el simulador; una cerrada no se devuelve a la IA (tampoco de
     legado); y las dos carreras que prometen el contrato (S37) -- el lock
     de T21 y el FOR UPDATE del guardado -- se miden de verdad.
================================================================================
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

faltan = [v for v in ("DBHOST", "DBPORT", "DBUSER", "DBPASSWORD") if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] faltan {faltan}")
    raise SystemExit(0)
if not shutil.which("docker"):
    print("  [saltado] hace falta Docker")
    raise SystemExit(0)

import psycopg                                                      # noqa: E402

HOST, PUERTO = os.environ["DBHOST"], os.environ["DBPORT"]
USUARIO, CLAVE = os.environ["DBUSER"], os.environ["DBPASSWORD"]
BASE = "chat_" + uuid.uuid4().hex[:6]
TENANT = "rapilink"
ANA = ("7c9e6679-7425-40de-944b-e07fc1f90ae7", "Ana Perez")
LUIS = ("0f8fad5b-d9cb-469f-a165-70867728950e", "Luis Rojas")
fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sentencia, params=None):
    with psycopg.connect(dsn(BASE), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def fila_minima(tabla: str, fijos: dict) -> None:
    cols = q("""select column_name, data_type, character_maximum_length from information_schema.columns
                where table_schema = 'public' and table_name = %s
                  and is_nullable = 'NO' and column_default is null""", (tabla,))
    valores = dict(fijos)
    por_tipo = {"uuid": lambda: str(uuid.uuid4()), "boolean": lambda: False,
                "integer": lambda: 0, "bigint": lambda: 0, "smallint": lambda: 0,
                "jsonb": lambda: "{}", "json": lambda: "{}",
                "timestamp with time zone": lambda: "now", "date": lambda: "2026-01-01"}
    for nombre, tipo, largo in cols:
        if nombre not in valores:
            valor = por_tipo.get(tipo, lambda: "x" + uuid.uuid4().hex[:8])()
            valores[nombre] = valor[:largo] if largo and isinstance(valor, str) else valor
    nombres = list(valores)
    q(f"insert into public.{tabla} ({', '.join(nombres)}) values ({', '.join(['%s'] * len(nombres))})",
      [valores[n] for n in nombres])


def conv(org, numero, *, dias, canal="whatsapp"):
    return str(q("""insert into asistente.conversations
                      (organization_id, canal, usuario_externo, creado_en, actualizado_en)
                    values (%s, %s, %s, now() - make_interval(days => %s),
                            now() - make_interval(days => %s)) returning id""",
                 (org, canal, numero, dias, dias))[0][0])


def mensaje(org, cid, rol, origen, *, minutos, contenido="x"):
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen, creado_en)
         values (%s, %s, %s, %s, %s, now() - make_interval(mins => %s))""",
      (org, cid, rol, contenido, origen, minutos))


def fila_entera(cid):
    return q("select to_jsonb(c) from asistente.conversations c where id = %s", (cid,))[0][0]


print("=" * 74)
print(" LA BANDEJA POR CHAT Y T21")
print("=" * 74)
try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    org = str(uuid.uuid4())
    otra = str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org chat"})
    fila_minima("organization", {"id": otra, "name": "Otra empresa"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (otra, "otra_empresa"))
    os.environ["DBNAME"] = BASE
    from nucleo.canales import api                                 # noqa: E402
    from nucleo.persistencia import db                             # noqa: E402
    from nucleo.relevo import transiciones as T                    # noqa: E402

    api._TOKEN_SERVICIO = None
    http = api.app.test_client()

    # ======================================================================
    print("\n== A. la lista agrupada y el hilo, por la ruta real ==")
    N = "573000000501"
    c17 = conv(org, N, dias=10)
    mensaje(org, c17, "user", "cliente", minutos=10 * 1440, contenido="no tengo internet")
    T.escalar(TENANT, c17)
    T.tomar(TENANT, c17, operador_id=ANA[0], operador_nombre=ANA[1])
    r17 = T.cerrar(TENANT, c17, por="operador", desenlace="equipo_cliente",
                   nota="CANARIO-NOTA-7731", operador_id=ANA[0], operador_nombre=ANA[1])
    # La primera la verifico OTRO cliente: el numero cambio de dueno.
    q("update asistente.conversations set id_cliente = 'cliente-viejo-11' where id = %s", (c17,))
    c18 = conv(org, N, dias=6)
    mensaje(org, c18, "user", "cliente", minutos=6 * 1440, contenido="hola de nuevo")
    db.guardar_resumen(TENANT, c18, "resumen de la inactividad")
    vieja = conv(org, N, dias=3)
    mensaje(org, vieja, "user", "cliente", minutos=3 * 1440, contenido="sigo sin servicio")
    T.escalar(TENANT, vieja)
    nueva = conv(org, N, dias=1)
    q("update asistente.conversations set id_cliente = 'cliente-actual-22' where id = %s", (nueva,))
    mensaje(org, nueva, "user", "cliente", minutos=3, contenido="y ahora la tele")
    # La escalada vieja se movio ULTIMO; la nueva nacio despues. Asi un
    # representante elegido por actualizado_en caeria en la equivocada.
    q("update asistente.conversations set escalada_en = now() - interval '5 hours', "
      "actualizado_en = now() where id = %s", (vieja,))
    q("update asistente.conversations set actualizado_en = now() - interval '1 hour' where id = %s",
      (nueva,))
    simulada = conv(org, N, dias=1, canal="whatsapp-simulado")
    ajena = conv(otra, N, dias=1)

    e17 = q("select estado, cerrada_por_tipo, desenlace_codigo from asistente.conversations where id = %s",
            (c17,))[0]
    comprobar(r17.aplicada and e17 == ("cerrada", "operador", "equipo_cliente"),
              f"preparacion: T17 cerro la primera con su desenlace ({e17})")
    comprobar(q("select estado, cerrada_por_tipo from asistente.conversations where id = %s",
                (c18,))[0] == ("cerrada", None),
              "preparacion: T18 cerro la segunda SIN dejar quien (asi cierra hoy)")

    cuerpo = http.get(f"/conversaciones?tenant={TENANT}&por_numero=1").get_json()
    del_numero = [f for f in cuerpo["conversaciones"] if f["usuario_externo"] == N]
    operativas = [f for f in del_numero if f["canal_operativo"]]
    comprobar(cuerpo.get("agrupada") is True, "la respuesta dice que viene agrupada")
    comprobar(len(operativas) == 1, f"las cuatro conversaciones del numero son UN chat ({len(operativas)})")
    chat = operativas[0] if operativas else {}
    comprobar(chat.get("id") == nueva, "representa la abierta mas reciente por creado_en, no la ultima movida",
              f"{chat.get('id')} vs nueva={nueva} vieja={vieja}")
    comprobar(chat.get("banda") == 2 and chat.get("urgente_id") == vieja,
              f"la banda del chat es la de la escalada sin asignar ({chat.get('banda')}, {chat.get('motivo_cola')})")
    comprobar([a["id"] for a in chat.get("abiertas", [])] == [nueva],
              "ninguna abierta queda escondida: la que no es la urgente viaja en 'abiertas'")
    comprobar(chat.get("escalada_a_humano") is True and chat.get("escalada_en") is not None,
              "la fila dice que esta escalada y desde cuando (de la urgente, no de la de la IA)",
              f"{chat.get('escalada_a_humano')} {chat.get('escalada_en')}")
    comprobar(chat.get("ids") == [c17, c18, vieja, nueva] and chat.get("tramos") == 4,
              "'ids' trae las cuatro en el orden en que nacieron")
    comprobar(any(f["id"] == simulada and not f["canal_operativo"] for f in del_numero),
              "el mismo numero en el simulador queda aparte, sin agrupar")
    comprobar(all(f["id"] != ajena and ajena not in f.get("ids", []) for f in cuerpo["conversaciones"]),
              "el mismo numero en OTRA empresa no aparece ni se mezcla")
    # Dos canales REALES con el mismo numero son dos chats. Hoy el unico real
    # es whatsapp, asi que por la ruta real "agrupar sin canal" no se veia
    # (la mutacion sobrevivio el 21/10/2026). Se amplia REALES SOLO dentro de
    # la prueba para medirlo por la ruta de verdad.
    reales = api.canales.REALES
    api.canales.REALES = frozenset({*reales, "whatsapp-simulado"})
    try:
        dos = [f for f in http.get(f"/conversaciones?tenant={TENANT}&por_numero=1").get_json()["conversaciones"]
               if f["usuario_externo"] == N]
    finally:
        api.canales.REALES = reales
    comprobar(len(dos) == 2 and all(f["canal_operativo"] for f in dos)
              and any(f["id"] == simulada and f["ids"] == [simulada] for f in dos),
              f"dos canales reales con el mismo numero son DOS chats ({len(dos)})")
    plana = http.get(f"/conversaciones?tenant={TENANT}").get_json()
    comprobar(len([f for f in plana["conversaciones"] if f["usuario_externo"] == N and f["canal_operativo"]]) == 4
              and "ids" not in plana["conversaciones"][0] and plana.get("agrupada") is False,
              "sin 'por_numero', una fila por conversacion, como siempre")
    destino, _ = db.registrar_mensaje(TENANT, "whatsapp", N, "cliente_final", "user", "hola?",
                                      origen="cliente")
    comprobar(str(destino) == vieja,
              "con dos abiertas, el proximo mensaje del cliente cae en la que se movio ultima "
              "(registrar_mensaje no cambia): por eso el chat las muestra a las dos")

    h = http.get(f"/conversaciones/{nueva}/hilo?tenant={TENANT}").get_json()
    tramos = h.get("tramos", [])
    comprobar([t["conversacion"]["id"] for t in tramos] == [c17, c18, vieja],
              "el hilo trae las anteriores, de la mas vieja a la mas nueva, sin la pedida")
    if len(tramos) == 3:
        k17, k18, kv = (t["conversacion"] for t in tramos)
        comprobar(k17["cierre"]["por"] == "operador" and k17["cierre"]["en"]
                  and k17["cierre"]["desenlace"] == "equipo_cliente",
                  f"la marca de T17 trae quien, cuando (del evento) y el desenlace ({k17['cierre']})")
        comprobar(k18["cierre"] == {"por": None, "en": None, "desenlace": None},
                  f"la de T18 no inventa nada: sin quien ni cuando ({k18['cierre']})")
        comprobar(kv["cierre"] is None and kv["estado"] == "abierta", "la abierta no tiene marca de cierre")
        comprobar(all(m["conversation_id"] == t["conversacion"]["id"]
                      for t in tramos for m in t["mensajes"]) and tramos[0]["mensajes"],
                  "cada mensaje dice de que conversacion es (marcar ejemplo va por tramo)")
        crudo = http.get(f"/conversaciones/{nueva}/hilo?tenant={TENANT}").get_data(as_text=True)
        comprobar("CANARIO-NOTA-7731" not in crudo,
                  "la nota que escribio la persona al cerrar NO viaja en el hilo, bajo ninguna clave")
        comprobar(k17["otro_cliente"] is True and k18["otro_cliente"] is False
                  and "cliente-viejo-11" not in crudo,
                  "la conversacion verificada como OTRO cliente se marca, sin mandar quien era")
    comprobar(h.get("mas_reciente_id") == nueva and h.get("abiertas") == [nueva, vieja],
              f"y dice cual es la actual y cuales estan abiertas ({h.get('mas_reciente_id')}, {h.get('abiertas')})")
    comprobar(h.get("posteriores") == [] and h.get("agrupa") is True,
              f"la actual no tiene posteriores, y el canal agrupa ({h.get('posteriores')}, {h.get('agrupa')})")
    hv = http.get(f"/conversaciones/{vieja}/hilo?tenant={TENANT}").get_json()
    comprobar(hv.get("posteriores") == [nueva],
              f"desde la escalada vieja, el hilo dice que hay una posterior ({hv.get('posteriores')})")
    pag, vistos = None, []
    for _ in range(4):
        url = f"/conversaciones/{nueva}/hilo?tenant={TENANT}&limite=1" + (f"&antes={pag}" if pag else "")
        p = http.get(url).get_json()
        vistos += [t["conversacion"]["id"] for t in p["tramos"]]
        pag = p["antes"]
        if not p["hay_anteriores"]:
            break
    comprobar(vistos == [vieja, c18, c17], f"paginado de a una, hacia atras, sin repetir ({len(vistos)})")
    h17 = http.get(f"/conversaciones/{c17}/hilo?tenant={TENANT}").get_json()
    comprobar(h17["tramos"] == [] and h17["mas_reciente_id"] == nueva,
              "un enlace viejo (la primera) sabe que hay una mas reciente")
    comprobar(http.get(f"/conversaciones/{ajena}/hilo?tenant={TENANT}").status_code == 404,
              "el hilo de una conversacion de OTRA empresa no existe para esta")
    hs = http.get(f"/conversaciones/{simulada}/hilo?tenant={TENANT}").get_json()
    comprobar(hs["tramos"] == [] and hs["total_tramos"] == 1 and hs.get("agrupa") is False,
              "el simulador no arma hilo, y lo dice ('agrupa': false)")

    # ======================================================================
    print("\n== B. T21: escribirle a un chat cerrado ==")
    enviados = []

    def enviar_texto(config, tenant, para, texto):
        enviados.append(("texto", para))
        return "wamid.t21-" + uuid.uuid4().hex[:6]

    def enviar_plantilla(config, tenant, para, nombre, variables, idioma, plantilla=None):
        enviados.append(("plantilla", para))
        return "wamid.pl-" + uuid.uuid4().hex[:6]

    PLANTILLA = {"nombre": "seguimiento", "estado": "APPROVED", "variables": 0, "idioma": "es",
                 "formato_variables": "posicional", "cuerpo": "Hola, seguimos atentos a su caso.",
                 "variables_cuerpo": [], "variables_encabezado": []}
    api.whatsapp.enviar_texto = enviar_texto
    api.whatsapp.enviar_plantilla_aprobada = enviar_plantilla
    api.whatsapp.plantillas_aprobadas = lambda config, tenant: [PLANTILLA]

    def cerrada_con_cliente(numero, horas_desde_el_cliente):
        c = conv(org, numero, dias=2)
        mensaje(org, c, "user", "cliente", minutos=int(horas_desde_el_cliente * 60), contenido="hola")
        T.escalar(TENANT, c)
        T.tomar(TENANT, c, operador_id=ANA[0], operador_nombre=ANA[1])
        T.cerrar(TENANT, c, por="operador", desenlace="equipo_cliente",
                 operador_id=ANA[0], operador_nombre=ANA[1])
        return c

    def del_numero(numero):
        return [x[0] for x in q("select id::text from asistente.conversations "
                                "where organization_id = %s and usuario_externo = %s order by creado_en",
                                (org, numero))]

    def escribir(cid, texto, clave, quien=ANA, **extra):
        return http.post(f"/conversaciones/{cid}/mensajes", json={
            "tenant": TENANT, "mensaje": texto, "autor": quien[1], "autor_usuario_id": quien[0],
            "clave_idempotencia": clave, **extra})

    M = "573000000601"
    cm = cerrada_con_cliente(M, 2)
    antes = fila_entera(cm)
    r = escribir(cm, "Hola, seguimos con su caso", "k-t21-1")
    b = r.get_json() or {}
    comprobar(r.status_code == 201 and b.get("continua_de") == cm and b.get("conversation_id") not in (None, cm),
              f"escribir en la cerrada abre una conversacion NUEVA ({r.status_code}, {b.get('codigo')})")
    t21 = b.get("conversation_id")
    if t21:
        f = q("""select estado, control, control_motivo, asignada_a_nombre, relevo_version,
                        atendida_manual, usuario_externo, canal
                 from asistente.conversations where id = %s""", (t21,))[0]
        comprobar(f == ("abierta", "humano", "intervencion", "Ana Perez", 1, True, M, "whatsapp"),
                  f"nace abierta, en manos de quien escribe, como intervencion, version 1 ({f})")
        ev = q("select tipo, datos, actor_nombre from asistente.relevo_eventos where conversation_id = %s",
               (t21,))
        comprobar(len(ev) == 1 and ev[0][0] == "intervencion" and ev[0][1].get("continua_de") == cm
                  and ev[0][1].get("tomada") is True and ev[0][2] == "Ana Perez",
                  f"con UN evento 'intervencion' que dice de que cerrada continua ({ev})")
        msg = q("""select origen, autor_nombre, rol, estado_entrega from asistente.messages
                   where conversation_id = %s""", (t21,))
        comprobar(len(msg) == 1 and msg[0][:3] == ("humano", "Ana Perez", "assistant")
                  and msg[0][3] not in ("pendiente", "fallido"),
                  f"el mensaje queda en la nueva, firmado, y entregado ({msg})")
    comprobar(fila_entera(cm) == antes, "la cerrada queda BYTE A BYTE igual: estado, quien, desenlace, actualizado_en")
    comprobar(enviados == [("texto", M)], f"se le escribio una vez, al numero del chat ({enviados})")

    r2 = escribir(cm, "Hola, seguimos con su caso", "k-t21-1")
    comprobar(r2.status_code == 200 and (r2.get_json() or {}).get("conversation_id") == t21
              and len(del_numero(M)) == 2 and len(enviados) == 1,
              f"el reintento con la misma clave no abre otra ni reenvia ({r2.status_code})")
    r3 = escribir(cm, "otro mensaje", "k-t21-2")
    comprobar(r3.status_code == 409 and (r3.get_json() or {}).get("codigo") == "hay_conversacion_abierta"
              and (r3.get_json() or {}).get("conversation_id") == t21 and len(del_numero(M)) == 2,
              f"con una abierta en el chat, se escribe ahi: 409 con su id ({r3.status_code})")
    destino, _ = db.registrar_mensaje(TENANT, "whatsapp", M, "cliente_final", "user", "gracias",
                                      origen="cliente")
    comprobar(str(destino) == t21 and q("select control_motivo from asistente.conversations where id = %s",
                                        (t21,))[0][0] == "intervencion",
              "la respuesta del cliente cae en la conversacion que abrio la persona, que sigue en sus manos")

    P = "573000000701"
    cp = cerrada_con_cliente(P, 30)
    antes_p = len(enviados)
    r4 = escribir(cp, "texto libre", "k-t21-3")
    comprobar(r4.status_code == 409 and (r4.get_json() or {}).get("codigo") == "fuera_de_ventana"
              and del_numero(P) == [cp] and len(enviados) == antes_p,
              f"fuera de las 24 h del NUMERO, el texto se rechaza sin crear nada ni enviar ({r4.status_code})")
    r5 = http.post(f"/conversaciones/{cp}/plantilla", json={
        "tenant": TENANT, "plantilla": "seguimiento", "variables": [], "autor": ANA[1],
        "autor_usuario_id": ANA[0], "clave_idempotencia": "k-t21-4"})
    comprobar(r5.status_code == 201 and len(del_numero(P)) == 2 and enviados[-1] == ("plantilla", P),
              f"la plantilla si pasa, y abre la conversacion nueva ({r5.status_code} {r5.get_json()})")

    B = "573000000801"
    cb = cerrada_con_cliente(B, 30)
    q("insert into asistente.canal_bajas (organization_id, canal, usuario_externo) values (%s, 'whatsapp', %s)",
      (org, B))
    antes_b = len(enviados)
    r6 = http.post(f"/conversaciones/{cb}/plantilla", json={
        "tenant": TENANT, "plantilla": "seguimiento", "variables": [], "autor": ANA[1],
        "autor_usuario_id": ANA[0], "clave_idempotencia": "k-t21-5"})
    comprobar(r6.status_code == 409 and (r6.get_json() or {}).get("codigo") == "de_baja"
              and del_numero(B) == [cb] and len(enviados) == antes_b,
              f"un numero dado de baja no recibe la plantilla ni se le abre nada ({r6.status_code})")

    print("\n== C. lo que encontro el auditor de frontera (21/10/2026) ==")

    def abierta_tomada(numero):
        c = conv(org, numero, dias=1)
        mensaje(org, c, "user", "cliente", minutos=60, contenido="hola")
        T.escalar(TENANT, c)
        T.tomar(TENANT, c, operador_id=ANA[0], operador_nombre=ANA[1])
        return c

    def cerrar(c):
        T.cerrar(TENANT, c, por="operador", desenlace="equipo_cliente",
                 operador_id=ANA[0], operador_nombre=ANA[1])

    # S6: el cierre llega ENTRE la guarda y el guardado. La guarda leyo
    # "humano"; el guardado tiene que ver la cerrada y no guardar ni enviar.
    R = "573000000911"
    cr = abierta_tomada(R)
    cerrar(cr)
    guarda_real = api.persistencia.control_efectivo_de
    api.persistencia.control_efectivo_de = lambda *a, **k: "humano"   # la lectura vieja de la guarda
    try:
        antes_r = len(enviados)
        r9 = escribir(cr, "llega tarde", "k-s6")
    finally:
        api.persistencia.control_efectivo_de = guarda_real
    comprobar(r9.status_code == 409 and (r9.get_json() or {}).get("codigo") == "conversacion_cerrada"
              and len(enviados) == antes_r
              and not q("select 1 from asistente.messages where conversation_id = %s and origen = 'humano'",
                        (cr,)),
              f"I22: cerrada entre la guarda y el guardado -> 409, nada guardado ni enviado ({r9.status_code})")

    # S2: la misma clave despues de que la conversacion se cerro.
    K = "573000000921"
    ck = abierta_tomada(K)
    ok1 = escribir(ck, "le escribo", "k-s2")
    cerrar(ck)
    antes_k = len(enviados)
    r10 = escribir(ck, "le escribo", "k-s2")
    comprobar(ok1.status_code == 201 and r10.status_code == 409
              and (r10.get_json() or {}).get("codigo") == "clave_usada"
              and del_numero(K) == [ck] and len(enviados) == antes_k,
              f"la misma clave tras el cierre: 409 clave_usada, sin conversacion fantasma ni reenvio "
              f"({r10.status_code} {len(del_numero(K))})")

    # S1: lo mismo con una plantilla -- antes el cliente la recibia DOS veces.
    PL = "573000000931"
    cpl = abierta_tomada(PL)
    cuerpo_pl = {"tenant": TENANT, "plantilla": "seguimiento", "variables": [], "autor": ANA[1],
                 "autor_usuario_id": ANA[0], "clave_idempotencia": "k-s1"}
    ok2 = http.post(f"/conversaciones/{cpl}/plantilla", json=cuerpo_pl)
    cerrar(cpl)
    antes_pl = len(enviados)
    r11 = http.post(f"/conversaciones/{cpl}/plantilla", json=cuerpo_pl)
    comprobar(ok2.status_code == 201 and r11.status_code == 409 and len(enviados) == antes_pl
              and del_numero(PL) == [cpl],
              f"la misma plantilla tras el cierre no sale dos veces ({r11.status_code}, envios +{len(enviados) - antes_pl})")

    # S3: T21 con una clave desde una cerrada; la nueva se cierra; la misma
    # clave desde OTRA cerrada del mismo chat.
    Z = "573000000941"
    x1 = cerrada_con_cliente(Z, 2)
    x2 = cerrada_con_cliente(Z, 2)
    rz = escribir(x2, "seguimos", "k-s3")
    nueva_z = (rz.get_json() or {}).get("conversation_id")
    if nueva_z:
        cerrar(nueva_z)
    antes_z, abiertas_z = len(enviados), len(del_numero(Z))
    r12 = escribir(x1, "seguimos", "k-s3")
    comprobar(rz.status_code == 201 and r12.status_code == 409
              and (r12.get_json() or {}).get("codigo") == "clave_usada"
              and len(del_numero(Z)) == abiertas_z and len(enviados) == antes_z,
              f"la misma clave desde otra cerrada del chat: sin fantasma ni envio ({r12.status_code})")

    print("\n== X26: el motor ya no le acepta nada a una cerrada ==")
    S = "573000000901"
    cs = cerrada_con_cliente(S, 2)
    r7 = escribir(cs, "y devuelvo", "k-t21-6", devolver_al_asistente=True)
    comprobar(r7.status_code == 400 and (r7.get_json() or {}).get("codigo") == "devolver_no_disponible"
              and del_numero(S) == [cs],
              f"responder y devolver en un chat cerrado no se hace en un paso ({r7.status_code})")
    r8 = http.post(f"/conversaciones/{cs}/humano/media", data={
        "tenant": TENANT, "tipo": "image", "autor": ANA[1], "autor_usuario_id": ANA[0],
        "clave_idempotencia": "k-t21-7",
        "archivo": (io.BytesIO(b"\x89PNG\r\n\x1a\nfalso"), "foto.png", "image/png")},
        content_type="multipart/form-data")
    comprobar(r8.status_code == 409 and (r8.get_json() or {}).get("codigo") == "conversacion_cerrada"
              and not q("select 1 from asistente.messages where conversation_id = %s and origen = 'humano'",
                        (cs,)),
              f"una imagen a una conversacion cerrada: 409 y nada guardado ({r8.status_code})")

    print("\n== D. lo que encontro el auditor independiente (21/10/2026) ==")
    copias = []
    api.operativo.responder = lambda config, tenant, ticket, contenido, autor: copias.append(ticket) or True

    def responder_caso(caso, texto, clave):
        return http.post(f"/casos/{caso}/mensajes", json={
            "tenant": TENANT, "mensaje": texto, "autor": ANA[1], "autor_usuario_id": ANA[0],
            "clave_idempotencia": clave})

    # D1: dos respuestas desde la pantalla del TICKET a un caso cuya
    # conversacion se cerro. Antes de este arreglo: la primera abria una nueva
    # sin copiar al ticket del ISP y la segunda daba 409 -- y la pantalla lo
    # tragaba.
    CA = "573000000951"
    cca = cerrada_con_cliente(CA, 2)
    caso = str(uuid.uuid4())
    q("update asistente.conversations set caso_id = %s, ticket_operativo = 'TK-951' where id = %s",
      (caso, cca))
    antes_ca = len(enviados)
    ra = responder_caso(caso, "primera respuesta", "k-caso-1")
    rb = responder_caso(caso, "segunda respuesta", "k-caso-2")
    nuevas_ca = [c for c in del_numero(CA) if c != cca]
    comprobar(ra.status_code == 201 and rb.status_code == 201 and len(enviados) - antes_ca == 2
              and copias == ["TK-951", "TK-951"] and len(nuevas_ca) == 1,
              f"desde el caso cerrado, las DOS respuestas le llegan al cliente y al ticket del caso "
              f"({ra.status_code} {rb.status_code}, envios +{len(enviados) - antes_ca}, copias {copias})")
    comprobar(bool(nuevas_ca) and q("select count(*) from asistente.messages where conversation_id = %s "
                                    "and origen = 'humano'", (nuevas_ca[0],))[0][0] == 2,
              "las dos quedan en la misma conversacion nueva del chat (la segunda no abre otra)")
    # Variante: el cliente ya volvio a escribir y lo atiende la IA. Escribir
    # desde el caso no se cuela delante de la IA (X25): 409, nada sale.
    CB = "573000000961"
    ccb = cerrada_con_cliente(CB, 2)
    caso_b = str(uuid.uuid4())
    q("update asistente.conversations set caso_id = %s, ticket_operativo = 'TK-961' where id = %s",
      (caso_b, ccb))
    db.registrar_mensaje(TENANT, "whatsapp", CB, "cliente_final", "user", "hola otra vez", origen="cliente")
    antes_cb, copias_cb = len(enviados), len(copias)
    rc = responder_caso(caso_b, "respuesta", "k-caso-3")
    comprobar(rc.status_code == 409 and (rc.get_json() or {}).get("codigo") == "control_ia"
              and len(enviados) == antes_cb and len(copias) == copias_cb,
              f"si el chat sigue con la IA, la respuesta del caso no sale ni se copia ({rc.status_code})")

    # D6: T21 solo en un canal real. En el simulador dejaba el numero de
    # bateria en manos de una persona y la proxima corrida no la contestaba
    # la IA.
    SIM = "573000000971"
    csim = conv(org, SIM, dias=1, canal="whatsapp-simulado")
    mensaje(org, csim, "user", "cliente", minutos=60, contenido="hola")
    T.escalar(TENANT, csim)
    T.tomar(TENANT, csim, operador_id=ANA[0], operador_nombre=ANA[1])
    cerrar(csim)
    rs = escribir(csim, "hola", "k-sim-1")
    comprobar(rs.status_code == 409 and (rs.get_json() or {}).get("codigo") == "conversacion_cerrada"
              and del_numero(SIM) == [csim],
              f"en el simulador, escribirle a una cerrada no abre nada ({rs.status_code})")

    # D3: una cerrada de legado no se devuelve a la IA. Antes daba 200 y le
    # borraba 'escalada_a_humano' a una conversacion ya cerrada.
    LG = "573000000981"
    clg = conv(org, LG, dias=1)
    q("update asistente.conversations set escalada_a_humano = true, necesita_atencion_humana = true, "
      "estado = 'cerrada' where id = %s", (clg,))
    rd = http.post(f"/conversaciones/{clg}/devolver", json={
        "tenant": TENANT, "autor": ANA[1], "autor_usuario_id": ANA[0]})
    banderas = q("select relevo_version, escalada_a_humano, necesita_atencion_humana "
                 "from asistente.conversations where id = %s", (clg,))[0]
    comprobar(rd.status_code == 409 and banderas == (0, True, True),
              f"devolver una cerrada de legado: 409 y no toca sus banderas ({rd.status_code}, {banderas})")

    # D7a: S37, el lock de T21. Dos personas escriben a la vez desde dos
    # cerradas del mismo chat; el commit de la primera se demora. Sin el
    # lock quedaban DOS abiertas (medido con el lock quitado).
    W = "573000000991"
    w1 = cerrada_con_cliente(W, 2)
    w2 = cerrada_con_cliente(W, 2)
    salida = {}

    def t21_en(nombre, ancla, quien):
        try:
            rr = T.abrir_por_operador(TENANT, ancla, "hola de " + nombre, operador_id=quien[0],
                                      operador_nombre=quien[1], clave=str(uuid.uuid4()))
            salida[nombre] = rr.motivo if not rr.aplicada else "aplicada"
        except Exception as e:                                       # noqa: BLE001
            salida[nombre] = type(e).__name__

    T._gancho_antes_del_commit = lambda: time.sleep(1.5)
    try:
        ha = threading.Thread(target=t21_en, args=("A", w1, ANA))
        hb = threading.Thread(target=t21_en, args=("B", w2, LUIS))
        ha.start()
        time.sleep(0.3)
        hb.start()
        ha.join()
        hb.join()
    finally:
        T._gancho_antes_del_commit = None
    abiertas_w = q("select count(*) from asistente.conversations where organization_id = %s "
                   "and usuario_externo = %s and estado = 'abierta'", (org, W))[0][0]
    comprobar(abiertas_w == 1 and sorted(salida.values()) == ["aplicada", "ya_hay_abierta"],
              f"dos T21 a la vez sobre el mismo chat dejan UNA abierta ({abiertas_w}, {salida})")

    # D7b: S37, el FOR UPDATE del guardado. Otra transaccion cierra la
    # conversacion y tarda en confirmar; el guardado tiene que esperarla y ver
    # la cerrada. Sin el bloqueo leia 'abierta' y guardaba en una cerrada.
    F = "573000000992"
    cf = abierta_tomada(F)
    cerrando = threading.Event()

    def cierre_lento():
        with psycopg.connect(dsn(BASE)) as con:
            con.execute("update asistente.conversations set estado = 'cerrada' where id = %s", (cf,))
            cerrando.set()
            time.sleep(1.5)
            con.commit()

    hc = threading.Thread(target=cierre_lento)
    hc.start()
    cerrando.wait(10)
    try:
        db.agregar_mensaje_humano(TENANT, cf, "llega durante el cierre", ANA[1],
                                  autor_usuario_id=ANA[0], clave_idempotencia="k-fu-1")
        resultado_fu = "guardado"
    except api.persistencia.ConversacionCerrada:
        resultado_fu = "cerrada"
    hc.join()
    comprobar(resultado_fu == "cerrada"
              and not q("select 1 from asistente.messages where conversation_id = %s and origen = 'humano'",
                        (cf,)),
              f"un guardado durante un cierre espera y ve la cerrada: nada guardado ({resultado_fu})")
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f'drop database if exists "{BASE}" with (force)')
    except Exception as e:                                           # noqa: BLE001
        print(f"  (no se pudo borrar {BASE}: {type(e).__name__})")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Un chat por numero, sin esconder abiertas, y escribirle a un chat cerrado no reabre nada.")
