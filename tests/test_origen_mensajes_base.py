# -*- coding: utf-8 -*-
"""
================================================================================
 ORIGEN, AUTOR E IDEMPOTENCIA EN LA BASE  --  contra PostgreSQL de verdad
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_origen_mensajes_base.py

Fase B2.2 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md. Construye una base efimera con
cli/base_desde_cero.py (la cadena entera por el ledger, incluida
202609161600_origen_de_mensajes.sql), carga una organizacion y un tenant, y
ejerce los tres escritores reales de nucleo/persistencia/db.py con el rol
degradado (app_backend) y RLS, como en produccion:

  1. cada escritor deja 'origen' (y autor cuando es una persona)
  2. la MISMA clave en la misma conversacion no crea otra fila; en otra
     conversacion si; un fallo marcado se ve en el reintento
  3. lo que se rechaza no deja filas: origen incoherente, autor invalido,
     plantilla (solo_canal) en una conversacion que no es de WhatsApp
  4. la base: CHECK de origen, y el legado (origen NULL, rol 'humano') admitido
  5. B2.3: historial_para_el_modelo y conversacion_vencida siguen la regla unica
     (nucleo/relevo/historial.py); la nota no llega ni al modelo ni a lo que
     resumen.redactar le manda; bloque de legado una vez; bytes intactos

Se salta si faltan DBHOST/DBPORT/DBUSER/DBPASSWORD o Docker (igual que las
suites de ledger). Borra su base al terminar, pase lo que pase.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
BASE = "b2_origen_" + uuid.uuid4().hex[:6]
TENANT = "b2prueba"
AUTOR_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


def q(sentencia, params=None):
    with psycopg.connect(dsn(BASE), autocommit=True) as con:
        cur = con.execute(sentencia, params)
        return cur.fetchall() if cur.description else []


def borrar_base():
    with psycopg.connect(dsn("postgres"), autocommit=True) as con:
        con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = %s and pid <> pg_backend_pid()", (BASE,))
        con.execute(f'drop database if exists "{BASE}"')


def fila_minima(tabla: str, fijos: dict) -> None:
    """Inserta una fila en una tabla de Django llenando, por tipo, las columnas
    NOT NULL sin default: Django pone sus defaults en Python, no en la base."""
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


print("=" * 74)
print(" ORIGEN, AUTOR E IDEMPOTENCIA EN LA BASE")
print("=" * 74)

try:
    print(f"\n       -> construyendo {BASE} con cli/base_desde_cero.py", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO,
                            "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    comprobar(bool(q("select 1 from asistente.migraciones_aplicadas "
                     "where archivo = '202609161600_origen_de_mensajes.sql'")),
              "la migracion de origen quedo aplicada por el ledger")

    org = str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org B2"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))

    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import db                              # noqa: E402

    def contar(where="true", params=()):
        return q(f"select count(*) from asistente.messages where {where}", params)[0][0]

    # -----------------------------------------------------------------------
    print("\n== 1. cada escritor deja origen ==")
    conv_api, m_user = db.registrar_mensaje(TENANT, "api", "u1", "cliente_final", "user", "hola",
                                            origen="cliente")
    _, m_ia = db.registrar_mensaje(TENANT, "api", "u1", "cliente_final", "assistant", "que tal",
                                   origen="ia")
    _, m_sis = db.registrar_mensaje(TENANT, "api", "u1", "cliente_final", "assistant", "espera",
                                    origen="sistema")
    filas = dict(q("select id::text, origen from asistente.messages where id = any(%s::uuid[])",
                   ([m_user, m_ia, m_sis],)))
    comprobar(filas == {m_user: "cliente", m_ia: "ia", m_sis: "sistema"},
              f"registrar_mensaje: cliente / ia / sistema ({filas})")

    conv_wa, _ = db.registrar_mensaje(TENANT, "whatsapp", "573000000000", "cliente_final", "user",
                                      "hola", origen="cliente")
    d1 = db.agregar_mensaje_humano(TENANT, conv_wa, "ya quedo", "Ana Perez",
                                   autor_usuario_id=AUTOR_ID, clave_idempotencia="clave-1")
    fila = q("""select rol, origen, autor_usuario_id::text, autor_nombre, clave_idempotencia, estado_entrega
                from asistente.messages where id = %s""", (d1["mensaje_id"],))[0]
    comprobar(fila == ("assistant", "humano", AUTOR_ID, "Ana Perez", "clave-1", "pendiente")
              and d1["existente"] is False,
              f"agregar_mensaje_humano: assistant/humano con autor y clave ({fila})")

    nota = db.agregar_nota_interna(TENANT, conv_wa, "revisar OLT", "Ana Perez", autor_usuario_id=AUTOR_ID)
    fila = q("select rol, origen, autor_nombre, contenido from asistente.messages where id = %s", (nota,))[0]
    comprobar(fila == ("nota", "humano", "Ana Perez", "(Ana Perez) revisar OLT"),
              f"agregar_nota_interna: nota/humano con autor ({fila})")

    # -----------------------------------------------------------------------
    print("\n== 2. idempotencia ==")
    antes = contar()
    d2 = db.agregar_mensaje_humano(TENANT, conv_wa, "ya quedo", "Ana Perez",
                                   autor_usuario_id=AUTOR_ID, clave_idempotencia="clave-1")
    comprobar(contar() == antes and d2["existente"] is True and str(d2["mensaje_id"]) == str(d1["mensaje_id"])
              and d2["estado_entrega"] == "pendiente",
              f"misma clave, misma conversacion: cero filas nuevas, devuelve la existente ({d2})")

    db.marcar_envio(TENANT, d1["mensaje_id"], None, "ventana cerrada")
    fila = q("select estado_entrega, error_entrega, wamid from asistente.messages where id = %s",
             (d1["mensaje_id"],))[0]
    comprobar(fila == ("fallido", "ventana cerrada", None),
              f"marcar_envio con error GUARDA 'fallido' y el motivo ({fila}) -- sin el cast "
              f"%s::text el UPDATE fallaba siempre y nada quedaba")
    d_ok = db.agregar_mensaje_humano(TENANT, conv_wa, "salio bien", "Ana Perez",
                                     autor_usuario_id=AUTOR_ID, clave_idempotencia="clave-ok")
    db.marcar_envio(TENANT, d_ok["mensaje_id"], "wamid.HBgLNTcz", None)
    fila = q("select estado_entrega, error_entrega, wamid from asistente.messages where id = %s",
             (d_ok["mensaje_id"],))[0]
    comprobar(fila == ("enviado", None, "wamid.HBgLNTcz"),
              f"marcar_envio aceptado GUARDA el wamid y 'enviado' ({fila}): sin esto G9 no puede pasar")
    antes = contar()
    d3 = db.agregar_mensaje_humano(TENANT, conv_wa, "ya quedo", "Ana Perez",
                                   autor_usuario_id=AUTOR_ID, clave_idempotencia="clave-1")
    comprobar(contar() == antes and d3["existente"] is True and d3["estado_entrega"] == "fallido",
              "tras un fallo de entrega, el reintento ve 'fallido' sin crear fila")

    d4 = db.agregar_mensaje_humano(TENANT, conv_api, "otra conv", "Ana Perez",
                                   autor_usuario_id=AUTOR_ID, clave_idempotencia="clave-1")
    comprobar(contar() == antes + 1 and d4["existente"] is False,
              "la misma clave en OTRA conversacion es otro mensaje")

    d5 = db.agregar_mensaje_humano(TENANT, conv_wa, "sin clave", "Ana Perez", autor_usuario_id=AUTOR_ID)
    d6 = db.agregar_mensaje_humano(TENANT, conv_wa, "sin clave", "Ana Perez", autor_usuario_id=AUTOR_ID)
    comprobar(contar() == antes + 3 and d5["mensaje_id"] != d6["mensaje_id"],
              "sin clave no hay deduplicacion (dos filas): la clave es lo que la da")

    # -----------------------------------------------------------------------
    print("\n== 3. lo rechazado no deja filas ==")
    antes = contar()
    for rol, origen in (("user", "ia"), ("assistant", "humano"), ("assistant", "robot")):
        try:
            db.registrar_mensaje(TENANT, "api", "u1", "cliente_final", rol, "x", origen=origen)
            comprobar(False, f"{rol}/{origen} deberia fallar")
        except ValueError:
            pass
    for nombre, uid in (("", AUTOR_ID), ("Ana", "nope")):
        try:
            db.agregar_mensaje_humano(TENANT, conv_wa, "x", nombre, autor_usuario_id=uid)
            comprobar(False, "autor invalido deberia fallar")
        except db.AutorInvalido:
            pass
    try:
        db.agregar_mensaje_humano(TENANT, conv_api, "plantilla", "Ana Perez", autor_usuario_id=AUTOR_ID,
                                  clave_idempotencia="clave-p", solo_canal="whatsapp")
        comprobar(False, "plantilla en canal api deberia fallar")
    except db.CanalNoAdmite:
        pass
    comprobar(contar() == antes, f"origen incoherente, autor invalido y canal que no admite: cero filas "
                                 f"({contar() - antes} nuevas)")
    comprobar(contar("clave_idempotencia = 'clave-p'") == 0,
              "la plantilla rechazada por canal no dejo su fila (D16)")

    # -----------------------------------------------------------------------
    print("\n== 4. la base ==")
    try:
        q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, origen)
             values (%s, %s, 'assistant', 'x', 'robot')""", (org, conv_api))
        comprobar(False, "origen 'robot' deberia violar el CHECK")
    except psycopg.errors.CheckViolation:
        comprobar(True, "CHECK: origen fuera de cliente|ia|humano|sistema se rechaza en la base")
    q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido)
         values (%s, %s, 'humano', 'fila de legado')""", (org, conv_api))
    comprobar(contar("rol = 'humano' and origen is null") == 1,
              "el legado (origen NULL, rol 'humano') sigue admitido: no se exige NOT NULL")
    try:
        q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, clave_idempotencia)
             values (%s, %s, 'assistant', 'dup', 'clave-1')""", (org, conv_wa))
        comprobar(False, "clave duplicada deberia violar el indice unico")
    except psycopg.errors.UniqueViolation:
        comprobar(True, "el indice unico parcial rechaza la clave repetida en la misma conversacion")

    # -----------------------------------------------------------------------
    print("\n== 5. B2.3: el historial y el resumen leidos de la base ==")
    from nucleo.relevo import historial as H                        # noqa: E402
    from nucleo.seguimiento import resumen                          # noqa: E402

    conv_leg = q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                    values (%s, 'whatsapp', '573111111111') returning id""", (org,))[0][0]
    AMBIGUO = "Te reviso la conexion.  (bytes: ñ á \n fin)  "
    NOTA = "NOTA INTERNA: el cliente debe tres meses"
    filas_leg = [("user", "hola, sin internet", None, None),
                 ("assistant", AMBIGUO, None, None),
                 ("humano", "Ya reinicie tu equipo", None, None),
                 ("nota", NOTA, None, None),
                 ("user", "sigue igual", None, None),
                 ("assistant", "Te paso con Maria", "ia", None),
                 ("assistant", "Soy Maria, lo reviso", "humano", "Maria Gomez"),
                 ("user", "gracias", "cliente", None)]
    for i, (rol, contenido, origen, autor) in enumerate(filas_leg):
        q("""insert into asistente.messages
               (organization_id, conversation_id, rol, contenido, origen, autor_nombre, creado_en)
             values (%s, %s, %s, %s, %s, %s, now() - make_interval(hours => 48) + make_interval(secs => %s))""",
          (org, conv_leg, rol, contenido, origen, autor, i))
    q("update asistente.conversations set actualizado_en = now() - interval '48 hours' where id = %s", (conv_leg,))
    antes_bytes = q("select id, contenido from asistente.messages where conversation_id = %s order by creado_en",
                    (conv_leg,))

    rec = db.historial_para_el_modelo(TENANT, str(conv_leg), 20)
    esperado = H.construir([{"rol": r, "contenido": c, "origen": o, "autor_nombre": a}
                            for r, c, o, a in filas_leg])
    comprobar(rec == esperado, "historial_para_el_modelo == la regla unica sobre las mismas filas",
              f"\n rec={rec}\n esp={esperado}")
    comprobar(sum(1 for m in rec if m["content"] == H.BLOQUE_LEGADO) == 1,
              "un assistant sin origen: el bloque de legado aparece exactamente una vez")
    comprobar(all(NOTA not in m["content"] for m in rec), "la nota NO esta en el historial del modelo")
    comprobar({"role": "assistant", "content": AMBIGUO} in rec,
              "el assistant de legado entra con sus bytes, sin prefijo")
    comprobar({"role": "assistant", "content": "(del equipo) Ya reinicie tu equipo"} in rec,
              "la fila de legado rol='humano' entra como assistant del equipo, autor desconocido")
    comprobar({"role": "assistant", "content": "(Maria Gomez, del equipo) Soy Maria, lo reviso"} in rec,
              "el mensaje humano nuevo entra firmado con su autor")

    vencida = db.conversacion_vencida(TENANT, "whatsapp", "573111111111", 24)
    comprobar(vencida is not None and all(NOTA not in m["content"] for m in vencida["historial"]),
              "conversacion_vencida: la nota NO esta en el insumo del resumen")
    comprobar(vencida is not None and vencida["historial"] == esperado,
              "el insumo del resumen sale de la misma regla que el historial")
    enviado = []
    real_chat = resumen.cliente.chat
    resumen.cliente.chat = lambda modelo, mensajes, **k: (enviado.append(mensajes),
                                                          type("R", (), {"contenido": "resumen"})())[1]
    try:
        resumen.redactar(type("C", (), {"llm": type("L", (), {"modelo_por_defecto": "x"})()})(),
                         vencida["historial"])
    finally:
        resumen.cliente.chat = real_chat
    comprobar(enviado and all(NOTA not in m["content"] for m in enviado[0]),
              "lo que resumen.redactar le manda al modelo no contiene la nota")

    despues_bytes = q("select id, contenido from asistente.messages where conversation_id = %s order by creado_en",
                      (conv_leg,))
    comprobar(antes_bytes == despues_bytes, "leer y resumir no modifico ni un byte de las filas")

    conv_sin = q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                    values (%s, 'whatsapp', '573222222222') returning id""", (org,))[0][0]
    for i, (rol, contenido) in enumerate((("user", "hola"), ("humano", "te ayudo"), ("user", "ok"))):
        q("""insert into asistente.messages (organization_id, conversation_id, rol, contenido, creado_en)
             values (%s, %s, %s, %s, now() + make_interval(secs => %s))""", (org, conv_sin, rol, contenido, i))
    rec2 = db.historial_para_el_modelo(TENANT, str(conv_sin), 20)
    comprobar(len(rec2) == 3 and all(m["content"] != H.BLOQUE_LEGADO for m in rec2),
              "solo user/NULL y humano/NULL: ningun bloque de legado")
finally:
    try:
        borrar_base()
        print(f"\n       -> {BASE} borrada")
    except Exception as e:
        print(f"\n  [aviso] no se pudo borrar {BASE}: {type(e).__name__}: {e}")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] Origen, autor e idempotencia se sostienen contra PostgreSQL.")
