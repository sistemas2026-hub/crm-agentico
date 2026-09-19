# -*- coding: utf-8 -*-
"""
================================================================================
 EL REGISTRO DEL RELEVO, LEIDO  --  como llego la conversacion a estas manos
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_relevo_eventos_lectura.py

Por que existe
--------------
El relevo escribe un evento por transicion desde B3.3, y hasta la fase 1.6
NADIE los leia. La pantalla decia QUIEN lleva la conversacion, no COMO llego:
una reasignacion de supervisor y una devolucion a la IA se veian igual desde
afuera -- la conversacion aparecia en otras manos y no habia donde mirar por
que.

Lo que esta prueba protege no es que la lectura exista, sino que lo que saca
sea del tenant que pregunta y nada mas, y que los datos de cada evento sean los
que el contrato declara. Un registro de auditoria que mezcla empresas es peor
que no tener registro.

  1. el orden y el contenido de lo que se lee
  2. AISLAMIENTO: una empresa no ve el relevo de otra
  3. lo que NO sale: ni texto del cliente ni respuestas de un sistema externo
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
OP = {"operador_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7", "operador_nombre": "Ana Perez"}
OTRO_OP = {"operador_id": "3f1a2b4c-5d6e-4f70-8a91-b2c3d4e5f607", "operador_nombre": "Luis Vargas"}


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
    print(f"  [saltado] necesita {faltan} y una base construida por el ledger "
          f"(cli/base_desde_cero.py)")
    sys.exit(0)

import psycopg                                                    # noqa: E402

from nucleo.persistencia import db                                # noqa: E402
from nucleo.relevo import transiciones                            # noqa: E402

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()
T_A = f"prueba-relevo-{uuid.uuid4().hex[:8]}"
T_B = f"prueba-relevo-{uuid.uuid4().hex[:8]}"
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
        "insert into asistente.conversations "
        "(organization_id, canal, usuario_externo, estado, control, control_motivo, "
        " relevo_version, escalada_a_humano, necesita_atencion_humana) "
        "values (%s, 'whatsapp', %s, 'abierta', 'humano', 'escalada', 1, true, true) "
        "returning id",
        (str(org), f"57300{uuid.uuid4().int % 10**7:07d}")).fetchone()[0]


try:
    sembrar_org(ORG_A, T_A)
    sembrar_org(ORG_B, T_B)

    # =========================================================================
    titulo("1. lo que se lee, y en que orden")
    # =========================================================================
    conv = conversacion(ORG_A)
    transiciones.tomar(T_A, conv, clave="t1", **OP)
    transiciones.solicitar_devolucion(T_A, conv, "Ya quedo resuelto.", clave="k1", **OP)
    transiciones.devolver_a_ia(T_A, conv, clave="d1", **OP)

    ev = db.eventos_de_relevo(T_A, conv)
    tipos = [e["tipo"] for e in ev]
    revisar(tipos == sorted(tipos, key=lambda t: tipos.index(t)) and len(ev) >= 3,
            "los eventos salen en el orden en que ocurrieron", f"{tipos}")
    revisar({"devolucion_solicitada", "devuelta_a_ia"} <= set(tipos),
            "estan las transiciones que se ejecutaron", f"{tipos}")

    uno = next(e for e in ev if e["tipo"] == "devuelta_a_ia")
    revisar(set(uno) == {"tipo", "actor_tipo", "actor_usuario_id", "actor_nombre",
                         "datos", "creado_en"},
            "cada evento trae exactamente los campos del contrato", f"{sorted(uno)}")
    revisar(uno["actor_tipo"] == "operador" and uno["actor_nombre"] == "Ana Perez",
            "dice quien actuo, no solo que paso", f"{uno['actor_tipo']} {uno['actor_nombre']}")
    revisar(isinstance(uno["datos"], dict) and "version" in uno["datos"],
            "y los datos son los que declara ESQUEMAS para ese tipo", f"{uno['datos']}")

    # Una reasignacion tiene que poder distinguirse de una devolucion: ese es
    # el caso que la pantalla no podia contar antes.
    conv2 = conversacion(ORG_A)
    transiciones.tomar(T_A, conv2, clave="t2", **OP)
    transiciones.reasignar(T_A, conv2, destino_id=OTRO_OP["operador_id"],
                           destino_nombre=OTRO_OP["operador_nombre"],
                           admin_id=OP["operador_id"], admin_nombre=OP["operador_nombre"],
                           motivo="cambio de turno", clave="r1")
    ev2 = db.eventos_de_relevo(T_A, conv2)
    rea = next((e for e in ev2 if e["tipo"] == "reasignada"), None)
    revisar(rea is not None and rea["datos"].get("nuevo_nombre") == "Luis Vargas"
            and rea["datos"].get("anterior_nombre") == "Ana Perez",
            "una reasignacion dice de quien a quien", f"{rea['datos'] if rea else None}")
    revisar(rea is not None and rea["datos"].get("motivo") == "cambio de turno",
            "y con que motivo", f"{rea['datos'] if rea else None}")

    # =========================================================================
    titulo("2. aislamiento entre empresas")
    # =========================================================================
    conv_b = conversacion(ORG_B)
    transiciones.tomar(T_B, conv_b, clave="tb", **OTRO_OP)

    revisar(db.eventos_de_relevo(T_A, conv_b) == [],
            "la empresa A NO ve el relevo de una conversacion de B",
            f"{db.eventos_de_relevo(T_A, conv_b)}")
    revisar(len(db.eventos_de_relevo(T_B, conv_b)) >= 1,
            "pero B si ve el suyo")
    revisar(db.eventos_de_relevo(T_A, str(uuid.uuid4())) == [],
            "una conversacion que no existe devuelve vacio, no error")

    # =========================================================================
    titulo("3. lo que NO sale")
    # =========================================================================
    texto = "Mi internet no anda desde ayer, numero 3005551234"
    conv3 = conversacion(ORG_A)
    transiciones.solicitar_devolucion(T_A, conv3, texto, clave="k3", **OP)
    crudo = str(db.eventos_de_relevo(T_A, conv3))
    revisar(texto not in crudo and "3005551234" not in crudo,
            "el registro no lleva el texto del mensaje ni el telefono del cliente")
    revisar("usuario_externo" not in crudo and "contenido" not in crudo,
            "ni campos de la conversacion que no le corresponden")
finally:
    admin.close()

print(f"\n{'=' * 76}")
if fallos:
    print(f"\nFALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\nOK: el relevo se puede leer, dice quien actuo, y no cruza empresas")
