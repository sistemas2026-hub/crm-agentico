# -*- coding: utf-8 -*-
"""
================================================================================
 G8 -- la revision encuentra lo que tiene que encontrar
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_g8_revision_base.py

Contra PostgreSQL real, con conversaciones SINTETICAS que reproducen los casos
limite. Las 16 de verdad viven en produccion y no se tocan desde aca.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
La revision de G8 se corre UNA vez, contra produccion, y de su resultado sale
una decision por conversacion que despues se aplica. Si la consulta que las
selecciona no coincide con la regla del backfill, se estaria revisando un
conjunto distinto del que el corte va a producir -- y nadie lo notaria hasta
despues del cutover.

Lo que se prueba, entonces, no es "la herramienta corre". Es:

  1. que seleccione EXACTAMENTE lo que el backfill de §11.2 va a tocar;
  2. que NO saque contenido de mensajes ni nombres de autores;
  3. que no escriba absolutamente nada.
================================================================================
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}", flush=True)
    if not condicion:
        fallos.append(que)
        if porque:
            print(f"          {porque}", flush=True)


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] necesita {faltan} y una base construida por el ledger")
    sys.exit(0)

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

_spec = importlib.util.spec_from_file_location("g8", RAIZ / "cli" / "revision_g8.py")
g8 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g8)

DATOS = dict(host=os.environ["DBHOST"], port=os.environ["DBPORT"],
             dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
             password=os.environ["DBPASSWORD"])
admin = psycopg.connect(**DATOS, autocommit=True, row_factory=dict_row)
ORG = uuid.uuid4()
TEN = f"prueba-g8-{uuid.uuid4().hex[:8]}"

#: Texto que NO puede salir en el informe. Si aparece, la herramienta esta
#: volcando la conversacion de un cliente a un archivo de trabajo.
SECRETO = "mi cedula es 1098765432 y vivo en la calle 5"
AUTOR = "Ana Gomez Operadora"


def sembrar_org():
    oblig = admin.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name='organization' "
        "and is_nullable='NO' and column_default is null").fetchall()
    valores = {"id": str(ORG), "name": TEN, "api_key": f"k-{ORG}",
               "company_name": TEN}
    for f in oblig:
        campo, tipo = f["column_name"], f["data_type"]
        if campo in valores:
            continue
        valores[campo] = ("now()" if "timestamp" in tipo or tipo == "date"
                          else True if tipo == "boolean"
                          else 0 if tipo in ("integer", "bigint", "smallint", "numeric")
                          else "{}" if tipo in ("json", "jsonb", "ARRAY") else "")
    cols = ", ".join('"' + k + '"' for k in valores)
    marcas = ", ".join("now()" if v == "now()" else "%s" for v in valores.values())
    admin.execute("insert into public.organization (" + cols + ") values (" + marcas + ")",
                  [v for v in valores.values() if v != "now()"])
    admin.execute("insert into asistente.tenant_config (organization_id, slug) "
                  "values (%s, %s)", (str(ORG), TEN))


def conversacion(**kw):
    campos = {"canal": "whatsapp", "estado": "abierta",
              "escalada_a_humano": True, "necesita_atencion_humana": True,
              "atendida_manual": False, "relevo_version": 0,
              "tomada_por": None, "caso_id": None, "ticket_operativo": None}
    campos.update(kw)
    cid = admin.execute(
        """insert into asistente.conversations
             (organization_id, canal, usuario_externo, estado, escalada_a_humano,
              necesita_atencion_humana, atendida_manual, relevo_version,
              tomada_por, caso_id, ticket_operativo)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        (str(ORG), campos["canal"], f"57300{uuid.uuid4().int % 10**7:07d}",
         campos["estado"], campos["escalada_a_humano"],
         campos["necesita_atencion_humana"], campos["atendida_manual"],
         campos["relevo_version"], campos["tomada_por"],
         campos["caso_id"], campos["ticket_operativo"])).fetchone()["id"]
    return str(cid)


def mensaje(cid, rol, contenido, dias_atras=0, autor=None):
    admin.execute(
        """insert into asistente.messages
             (organization_id, conversation_id, rol, contenido, creado_en,
              autor_nombre)
           values (%s,%s,%s,%s, now() - (%s || ' days')::interval, %s)""",
        (str(ORG), cid, rol, contenido, dias_atras, autor))


try:
    sembrar_org()

    # =========================================================================
    titulo("1. selecciona exactamente lo que el backfill va a tocar")
    # =========================================================================
    # La que SI: abierta, las dos banderas, legado.
    candidata = conversacion(caso_id=str(uuid.uuid4()))
    mensaje(candidata, "user", "no tengo internet", 1)
    mensaje(candidata, "assistant", "te ayudo", 1)

    # Las que NO, una por cada condicion de la regla.
    cerrada = conversacion(estado="cerrada", caso_id=str(uuid.uuid4()))
    sin_escalar = conversacion(escalada_a_humano=False, caso_id=str(uuid.uuid4()))
    sin_necesitar = conversacion(necesita_atencion_humana=False,
                                 caso_id=str(uuid.uuid4()))
    ya_gobernada = conversacion(relevo_version=3, caso_id=str(uuid.uuid4()))

    filas = g8.revisar(admin, incluir_pruebas=False)
    ids = {str(f["id"]) for f in filas}

    revisar(candidata in ids, "la candidata entra")
    for etiqueta, cid in (("cerrada", cerrada), ("sin escalar", sin_escalar),
                          ("sin necesitar atencion", sin_necesitar),
                          ("ya gobernada (version > 0)", ya_gobernada)):
        revisar(cid not in ids, f"la {etiqueta} NO entra")

    # La regla del codigo y la del contrato tienen que ser la misma. Se compara
    # contra el conteo que da la condicion escrita a mano.
    a_mano = admin.execute(
        """select count(*) as n from asistente.conversations
           where organization_id = %s and estado = 'abierta'
             and escalada_a_humano and necesita_atencion_humana
             and coalesce(relevo_version, 0) = 0
             and canal not in ('whatsapp-simulado','api','web')""",
        (str(ORG),)).fetchone()["n"]
    # Solo las de esta prueba: la herramienta mira la base entera a
    # proposito, y otras suites pueden dejar filas.
    mias = {str(c) for c in (candidata, cerrada, sin_escalar, sin_necesitar,
                             ya_gobernada)}
    propias = [f for f in filas if str(f["id"]) in mias]
    revisar(len(propias) == a_mano,
            f"la consulta y la regla de §11.2 dan lo mismo ({len(propias)} vs {a_mano})")

    # =========================================================================
    titulo("2. los canales de prueba se separan, no se mezclan")
    # =========================================================================
    simulada = conversacion(canal="whatsapp-simulado", caso_id=str(uuid.uuid4()))
    filas = g8.revisar(admin, incluir_pruebas=False)
    revisar(simulada not in {str(f["id"]) for f in filas},
            "un hilo de canal simulado no entra en la revision operativa",
            "Los 30 de A6 siguen el mismo modelo pero tienen otra politica.")
    filas_todas = g8.revisar(admin, incluir_pruebas=True)
    revisar(simulada in {str(f["id"]) for f in filas_todas},
            "y con --incluir-pruebas si aparece, para poder contarlos")

    # =========================================================================
    titulo("3. la sugerencia distingue los casos que importan")
    # =========================================================================
    # C: escalada y sin nada del otro lado.
    huerfana = conversacion()
    mensaje(huerfana, "user", "ayuda", 2)
    # B: la tiene alguien, por nombre, sin id.
    con_duenio = conversacion(caso_id=str(uuid.uuid4()), tomada_por="Luis Paz")
    mensaje(con_duenio, "user", "hola", 1)
    mensaje(con_duenio, "assistant", "hola", 1)
    # B: el cliente escribio despues de la ultima respuesta.
    esperando = conversacion(caso_id=str(uuid.uuid4()))
    mensaje(esperando, "assistant", "ya te atendemos", 2)
    mensaje(esperando, "user", "sigo sin internet", 1)
    # B: nadie la tomo y hace mucho.
    vieja = conversacion(caso_id=str(uuid.uuid4()))
    mensaje(vieja, "user", "hola", 30)
    mensaje(vieja, "assistant", "hola", 29)
    # A: con caso, sin dueño, reciente y sin cliente esperando.
    limpia = conversacion(caso_id=str(uuid.uuid4()))
    mensaje(limpia, "user", "hola", 1)
    mensaje(limpia, "assistant", "te ayudo", 0)

    por_id = {str(f["id"]): f for f in g8.revisar(admin, incluir_pruebas=False)}
    revisar(por_id[huerfana]["clase"] == "C",
            "sin caso ni ticket -> C (no adoptar)",
            "Adoptarla dejaria a alguien 'a cargo' sin nada del otro lado.")
    revisar(por_id[con_duenio]["clase"] == "B",
            "con dueño por nombre y sin id -> B (que alguien confirme quien es)")
    revisar(por_id[esperando]["clase"] == "B",
            "con el cliente esperando respuesta -> B")
    revisar(por_id[vieja]["clase"] == "B",
            "sin tomar y con 30 dias de espera -> B")
    revisar(por_id[limpia]["clase"] == "A",
            f"con caso, sin dueño y al dia -> A ({por_id[limpia]['por_que']})")

    # La sugerencia NO es una decision aplicada. Se compara un retrato de la
    # base ANTES y DESPUES de llamar a revisar(): comparar contra un estado
    # esperado cuenta tambien lo que la propia prueba sembro, que fue el error
    # de la primera version de esta asercion.
    def retrato():
        return admin.execute(
            """select id, control, control_motivo, relevo_version,
                      atendida_manual, estado, tomada_por, caso_id
               from asistente.conversations where organization_id = %s
               order by id""", (str(ORG),)).fetchall()

    antes_de_revisar = retrato()
    g8.revisar(admin, incluir_pruebas=False)
    g8.revisar(admin, incluir_pruebas=True)
    revisar(retrato() == antes_de_revisar,
            "revisar() no cambia una sola fila: no adopta ni resuelve",
            "G8 exige que decida una persona, una por una.")
    eventos = admin.execute(
        "select count(*) as n from asistente.relevo_eventos where organization_id = %s",
        (str(ORG),)).fetchone()["n"]
    revisar(eventos == 0, "y no escribio ningun evento")

    # =========================================================================
    titulo("4. no saca el contenido de nadie")
    # =========================================================================
    con_pii = conversacion(caso_id=str(uuid.uuid4()))
    mensaje(con_pii, "user", SECRETO, 1)
    mensaje(con_pii, "assistant", "entendido", 1, autor=AUTOR)

    filas = g8.revisar(admin, incluir_pruebas=False)
    crudo = json.dumps(filas, ensure_ascii=False, default=str)
    revisar(SECRETO not in crudo,
            "el contenido del mensaje NO sale en el informe",
            "Para leer la conversacion esta la bandeja, donde el acceso queda "
            "auditado y se lee en contexto.")
    revisar("1098765432" not in crudo, "ni la cedula que traia dentro")
    revisar(AUTOR not in crudo,
            "ni el nombre del autor de un mensaje")
    revisar(any(f["mensajes"] for f in filas),
            "pero si el conteo de mensajes, que es lo que permite priorizar")

    # Y el codigo no pide esas columnas en ningun momento.
    fuente = (RAIZ / "cli" / "revision_g8.py").read_text(encoding="utf-8")
    consulta = fuente[fuente.index("def revisar("):fuente.index("def informe(")]
    revisar("m.contenido" not in consulta and "autor_nombre" not in consulta,
            "la consulta no selecciona contenido ni autor_nombre")

    # =========================================================================
    titulo("5. es de solo lectura, y se puede demostrar")
    # =========================================================================
    codigo = "\n".join(l for l in fuente.splitlines()
                       if not l.strip().startswith("#"))
    for escritura in ("insert into", "update ", "delete from", "alter table"):
        revisar(escritura not in codigo.lower(),
                f"el codigo no contiene '{escritura.strip()}'")

finally:
    admin.execute("delete from public.organization where id = %s", (str(ORG),))
    admin.close()

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La revision selecciona lo correcto, no decide y no lee a nadie.")
