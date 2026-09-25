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
import threading
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


    # =============================================================================
    titulo("6. registrar la decision humana (adopcion de G8)")
    # =============================================================================
    from nucleo.relevo import transiciones as T                       # noqa: E402

    admin.execute("insert into asistente.tenant_config (organization_id, slug) "
                  "values (%s, %s) on conflict do nothing", (str(ORG), TEN))

    OP_ID = str(uuid.uuid4())
    OP = "Ana Gomez"


    def fila_de(cid):
        return admin.execute(
            """select control, control_motivo, relevo_version, estado,
                      asignada_a_nombre, asignada_a_usuario_id, tomada_por,
                      escalada_a_humano, necesita_atencion_humana
               from asistente.conversations where id = %s""", (cid,)).fetchone()


    def eventos_de(cid):
        return admin.execute(
            """select tipo, actor_tipo, actor_nombre, actor_usuario_id, datos
               from asistente.relevo_eventos where conversation_id = %s
               order by creado_en, id""", (cid,)).fetchall()


    # --- seguir_humano --------------------------------------------------------
    c1 = conversacion(caso_id=str(uuid.uuid4()), tomada_por="Luis Paz")
    mensaje(c1, "user", "sin internet", 3)
    r = T.adoptar_de_legado(TEN, c1, decision="seguir_humano",
                            operador_id=OP_ID, operador_nombre=OP)
    f = fila_de(c1)
    revisar(r.aplicada and f["relevo_version"] == 1,
            f"seguir_humano adopta y sube la version a 1 ({f['relevo_version']})")
    revisar(f["control"] == "humano" and f["control_motivo"] == "escalada",
            "deja control humano con motivo escalada (§11.2)")
    revisar(f["asignada_a_nombre"] == "Luis Paz",
            "copia 'tomada_por' como NOMBRE")
    revisar(f["asignada_a_usuario_id"] is None,
            "y deja el id de usuario en NULL",
            "Un nombre no prueba identidad: inventar el id le atribuiria a una "
            "persona concreta una conversacion que quiza no es suya.")

    evs = eventos_de(c1)
    revisar([e["tipo"] for e in evs] == ["escalada"],
            f"deja un evento 'escalada' ({[e['tipo'] for e in evs]})")
    revisar(evs[0]["datos"].get("legado") is True
            and evs[0]["datos"].get("g8") == "seguir_humano",
            f"con datos.legado y datos.g8 ({evs[0]['datos']})",
            "Sin esas dos claves nadie podria distinguir una escalada real de una "
            "adopcion administrativa.")
    revisar(evs[0]["actor_nombre"] == OP and str(evs[0]["actor_usuario_id"]) == OP_ID,
            "y dice QUIEN decidio, con nombre e id")

    # --- volver_ia ------------------------------------------------------------
    c2 = conversacion(caso_id=str(uuid.uuid4()))
    mensaje(c2, "user", "ya se soluciono", 1)
    r = T.adoptar_de_legado(TEN, c2, decision="volver_ia",
                            operador_id=OP_ID, operador_nombre=OP)
    f = fila_de(c2)
    revisar(r.aplicada and f["control"] == "ia" and f["control_motivo"] is None,
            "volver_ia deja control ia sin motivo")
    revisar(not f["escalada_a_humano"] and not f["necesita_atencion_humana"],
            "y apaga las banderas de legado, en la misma escritura",
            "Si quedaran puestas, la reconstruccion seguiria pausandola y la "
            "decision no tendria efecto.")
    evs = eventos_de(c2)
    revisar(evs[0]["datos"].get("g8") == "volver_ia",
            "con su evento 'devuelta_a_ia' y datos.g8")

    # --- cerrar_con_desenlace: la desbloqueo B6 -------------------------------
    # Hasta B6 estaba en esta lista, rechazada porque no existia el catalogo de
    # desenlaces. Ahora cierra Y adopta, y sigue exigiendo el codigo: lo que se
    # levanto es la imposibilidad, no la regla. El detalle se prueba en
    # tests/test_b6_cierre_desenlace.py; aqui solo que la puerta de G8 la
    # acepta y la registra como decision de la revision.
    c_cierre = conversacion(caso_id=str(uuid.uuid4()))
    r = T.adoptar_de_legado(TEN, c_cierre, decision="cerrar_con_desenlace",
                            operador_id=OP_ID, operador_nombre=OP,
                            desenlace="otro")
    f = fila_de(c_cierre)
    revisar(r.aplicada and f["estado"] == "cerrada" and f["relevo_version"] == 1,
            "'cerrar_con_desenlace' cierra y adopta (B6)")
    evs = eventos_de(c_cierre)
    revisar([e["tipo"] for e in evs] == ["cerrada"]
            and evs[0]["datos"].get("g8") == "cerrar_con_desenlace",
            "con un evento 'cerrada' que dice que fue una decision de G8")

    c_sin = conversacion(caso_id=str(uuid.uuid4()))
    antes = fila_de(c_sin)
    try:
        T.adoptar_de_legado(TEN, c_sin, decision="cerrar_con_desenlace",
                            operador_id=OP_ID, operador_nombre=OP)
        revisar(False, "y sin codigo de desenlace sigue sin cerrar")
    except ValueError:
        revisar(True, "y sin codigo de desenlace sigue sin cerrar",
                "Que sea de legado no la hace menos de un cliente.")
    revisar(fila_de(c_sin) == antes, "sin tocar la conversacion")

    # --- la que TODAVIA no se puede registrar ---------------------------------
    for decision in ("resolver_estado_externo",):
        c = conversacion(caso_id=str(uuid.uuid4()))
        antes = fila_de(c)
        try:
            T.adoptar_de_legado(TEN, c, decision=decision,
                                operador_id=OP_ID, operador_nombre=OP)
            revisar(False, f"'{decision}' se rechaza con su motivo")
        except NotImplementedError as e:
            # Que el motivo ESTE, sea cual sea el texto: rechazar sin decirlo
            # dejaria a quien revisa sin saber si el error es suyo. Atarlo a
            # una frase concreta hace que reescribir el mensaje rompa la
            # prueba sin que nada real haya cambiado.
            revisar(decision in str(e) and len(str(e)) > 60,
                    f"'{decision}' se rechaza nombrandola y explicando por que")
        revisar(fila_de(c) == antes,
                f"y la conversacion no se toco ({decision})",
                "Hacer algo parecido seria peor: quien revisa creeria que decidio "
                "algo que el sistema no registro.")

    # Una decision inventada tampoco pasa.
    try:
        T.adoptar_de_legado(TEN, c1, decision="archivar",
                            operador_id=OP_ID, operador_nombre=OP)
        revisar(False, "una decision que no existe se rechaza")
    except ValueError:
        revisar(True, "una decision que no existe se rechaza")

    # --- el actor es obligatorio ----------------------------------------------
    c3 = conversacion(caso_id=str(uuid.uuid4()))
    for oid, onombre, caso in ((OP_ID, "", "sin nombre"),
                               ("", OP, "sin id"),
                               ("no-es-uuid", OP, "con un id que no es uuid")):
        antes = fila_de(c3)
        try:
            T.adoptar_de_legado(TEN, c3, decision="seguir_humano",
                                operador_id=oid, operador_nombre=onombre)
            revisar(False, f"se rechaza una adopcion {caso}")
        except Exception:
            revisar(True, f"se rechaza una adopcion {caso}")
        revisar(fila_de(c3) == antes, f"y no cambia nada ({caso})")

    # --- repetir no duplica ---------------------------------------------------
    c4 = conversacion(caso_id=str(uuid.uuid4()))
    clave = f"g8-{uuid.uuid4()}"
    r1 = T.adoptar_de_legado(TEN, c4, decision="seguir_humano", operador_id=OP_ID,
                             operador_nombre=OP, clave=clave)
    r2 = T.adoptar_de_legado(TEN, c4, decision="seguir_humano", operador_id=OP_ID,
                             operador_nombre=OP, clave=clave)
    revisar(r1.aplicada and not r2.aplicada,
            "la misma decision con la misma clave se aplica UNA vez")
    revisar(len(eventos_de(c4)) == 1,
            f"y deja un solo evento ({len(eventos_de(c4))})")
    revisar(fila_de(c4)["relevo_version"] == 1,
            "sin subir la version dos veces")

    # Sin clave, una ya adoptada no se vuelve a tocar.
    r3 = T.adoptar_de_legado(TEN, c4, decision="volver_ia", operador_id=OP_ID,
                             operador_nombre=OP)
    revisar(not r3.aplicada and r3.motivo == "ya_adoptada",
            f"una ya adoptada responde 'ya_adoptada' ({r3.motivo})")
    revisar(fila_de(c4)["control"] == "humano",
            "y conserva la decision anterior: no se pisa la de otra persona")
    revisar(len(eventos_de(c4)) == 1, "sin escribir un evento mas")

    # --- dos operadores a la vez ----------------------------------------------
    c5 = conversacion(caso_id=str(uuid.uuid4()))
    resultados = []
    barrera = threading.Barrier(2)


    def decidir(decision):
        def _():
            barrera.wait()
            try:
                resultados.append(T.adoptar_de_legado(
                    TEN, c5, decision=decision, operador_id=str(uuid.uuid4()),
                    operador_nombre=f"Op {decision}"))
            except Exception as e:
                resultados.append(e)
        return _


    hilos = [threading.Thread(target=decidir("seguir_humano")),
             threading.Thread(target=decidir("volver_ia"))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    aplicadas = [r for r in resultados
                 if not isinstance(r, Exception) and r.aplicada]
    revisar(len(aplicadas) == 1,
            f"de dos operadores decidiendo a la vez, gana UNO ({len(aplicadas)})",
            "La fila se bloquea con FOR UPDATE: el segundo la encuentra adoptada.")
    revisar(len(eventos_de(c5)) == 1,
            f"y queda un solo evento ({len(eventos_de(c5))})")
    revisar(fila_de(c5)["relevo_version"] == 1,
            "con la version en 1, no en 2")

    # --- rollback completo si falla el evento ---------------------------------
    c6 = conversacion(caso_id=str(uuid.uuid4()))
    antes = fila_de(c6)
    T._gancho_antes_del_commit = lambda: (_ for _ in ()).throw(
        RuntimeError("falla al escribir el evento"))
    try:
        T.adoptar_de_legado(TEN, c6, decision="seguir_humano",
                            operador_id=OP_ID, operador_nombre=OP)
        revisar(False, "si falla el evento, la adopcion entera se deshace")
    except Exception:
        revisar(True, "si falla el evento, la adopcion entera se deshace")
    finally:
        T._gancho_antes_del_commit = None
    revisar(fila_de(c6) == antes,
            "la conversacion sigue exactamente como estaba",
            "Nunca una adopcion sin quien ni por que.")
    revisar(eventos_de(c6) == [], "y no quedo ningun evento suelto")

    # --- aislamiento entre empresas -------------------------------------------
    otra_org = uuid.uuid4()
    otro_ten = f"prueba-g8b-{uuid.uuid4().hex[:8]}"
    oblig = admin.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name='organization' "
        "and is_nullable='NO' and column_default is null").fetchall()
    vals = {"id": str(otra_org), "name": otro_ten, "api_key": f"k-{otra_org}",
            "company_name": otro_ten}
    for fl in oblig:
        campo, tipo = fl["column_name"], fl["data_type"]
        if campo in vals:
            continue
        vals[campo] = ("now()" if "timestamp" in tipo or tipo == "date"
                       else True if tipo == "boolean"
                       else 0 if tipo in ("integer", "bigint", "smallint", "numeric")
                       else "{}" if tipo in ("json", "jsonb", "ARRAY") else "")
    cols = ", ".join('"' + k + '"' for k in vals)
    marcas = ", ".join("now()" if v == "now()" else "%s" for v in vals.values())
    admin.execute("insert into public.organization (" + cols + ") values (" + marcas + ")",
                  [v for v in vals.values() if v != "now()"])
    admin.execute("insert into asistente.tenant_config (organization_id, slug) "
                  "values (%s, %s)", (str(otra_org), otro_ten))
    try:
        c7 = conversacion(caso_id=str(uuid.uuid4()))
        antes = fila_de(c7)
        r = T.adoptar_de_legado(otro_ten, c7, decision="seguir_humano",
                                operador_id=OP_ID, operador_nombre=OP)
        revisar(not r.aplicada,
                f"otra empresa no puede adoptar esta conversacion ({r.motivo})")
        revisar(fila_de(c7) == antes, "y la conversacion no cambia")
        revisar(eventos_de(c7) == [], "sin eventos escritos en el expediente ajeno")
    finally:
        admin.execute("delete from public.organization where id = %s", (str(otra_org),))

    # --- ninguna ruta adopta sola ---------------------------------------------
    fuente_rev = (RAIZ / "cli" / "revision_g8.py").read_text(encoding="utf-8")
    revisar("adoptar_de_legado" not in fuente_rev,
            "la herramienta de revision NO puede adoptar: ni la nombra",
            "La clasificacion A/B/C no llega a ninguna escritura.")

    # Sobre el PARSER, no sobre el archivo: el docstring de decidir_g8.py
    # nombra '--todas' justamente para decir que no existe, asi que buscar la
    # cadena daba rojo por su propia explicacion. Es la quinta vez en esta fase
    # que ese error aparece, y por eso ahora se mide lo que el comando ACEPTA.
    _spec_d = importlib.util.spec_from_file_location(
        "dec", RAIZ / "cli" / "decidir_g8.py")
    dec = importlib.util.module_from_spec(_spec_d)
    _spec_d.loader.exec_module(dec)

    por_nombre = {o: a for a in dec.construir_parser()._actions
                  for o in a.option_strings}
    for masivo in ("--todas", "--desde-archivo", "--lote", "--archivo"):
        revisar(masivo not in por_nombre,
                f"el comando de decision no acepta '{masivo}'",
                "§11.2 dice UNA POR UNA: un comando en lote lo volveria un tramite.")
    revisar(por_nombre["--conversacion"].nargs is None,
            "y toma UNA conversacion, no una lista")
    for obligatorio in ("--conversacion", "--decision", "--operador-id", "--operador"):
        revisar(por_nombre[obligatorio].required is True,
                f"'{obligatorio}' es obligatorio")
    revisar(set(por_nombre["--decision"].choices) == set(T.DECISIONES_G8),
            "y las decisiones posibles salen del contrato, no de una lista aparte")

    # Ninguna otra parte del motor LLAMA a la adopcion.
    #
    # Se mide sobre el arbol de sintaxis y no buscando la cadena en el texto.
    # La version anterior contaba cualquier mencion, asi que se puso roja el
    # dia que un docstring de transiciones.py explico que cerrar una
    # conversacion de legado NO la adopta y que para eso esta esta funcion --
    # o sea, por una frase que dice exactamente lo que la prueba defiende.
    # Es el mismo error que ya aparecio varias veces en esta rama: afirmar
    # sobre la prosa en vez de sobre el efecto.
    import ast

    llamadores = []
    for archivo in (RAIZ / "nucleo").rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            nombre = (f.attr if isinstance(f, ast.Attribute)
                      else f.id if isinstance(f, ast.Name) else "")
            if nombre == "adoptar_de_legado":
                llamadores.append(f"{archivo.name}:{nodo.lineno}")
    revisar(not llamadores,
            f"ningun modulo del motor la llama por su cuenta ({llamadores})",
            "Solo el comando, que exige un operador en cada invocacion.")

finally:
    admin.execute("delete from public.organization where id = %s", (str(ORG),))
    admin.close()

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La revision selecciona lo correcto, no decide y no lee a nadie.")
