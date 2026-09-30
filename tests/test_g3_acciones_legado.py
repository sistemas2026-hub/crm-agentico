# -*- coding: utf-8 -*-
"""
================================================================================
 G3 -- EL LEGADO DE ACCIONES PROPUESTAS  (contrato §11.4, X24, I6, I12)
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_g3_acciones_legado.py

Por que existe
--------------
Hay 36 acciones en 'pendiente' que nadie propuso desde una conversacion viva
(A5). El endpoint de aprobar las ejecutaba: leia la fila, comprobaba que
estuviera 'pendiente', y llamaba a la API externa. Nada mas. Con 34 tickets
entre ellas, eso son 34 visitas tecnicas por problemas de hace mas de una
semana -- y con el gate Q2 en rojo, sin forma de detectar el duplicado ni de
deshacerlo.

Lo que estas pruebas protegen:

  1. QUE APROBAR NO EJECUTE. Y que no ejecute *antes* de cualquier otra cosa:
     el ejecutor se inyecta y se cuenta cuantas veces lo llamaron. Cero, o la
     prueba falla. No se afirma que la guarda exista: se mide su efecto.

  2. QUE 'cancelada' SEA DURABLE Y DIGA POR QUE. Estado, motivo, quien y
     cuando, mas su evento, en la MISMA transaccion (I12). Una cancelacion a
     medias --fila cambiada y evento perdido-- es peor que ninguna: deja 36
     filas sin explicacion para quien las mire el mes que viene.

  3. QUE UNA EMPRESA NO VEA NI TOQUE LAS DE OTRA.

El criterio de "legado" es UNO y no es una heuristica: la accion no tiene
`conversation_id`, asi que no hay contra que revalidarla (§3.7). No se mira la
edad ni el tipo -- una regla por edad se vuelve falsa sola el dia que alguien
cambie el plazo, y en silencio.
================================================================================
"""

from __future__ import annotations

import json
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
from psycopg.rows import dict_row                                 # noqa: E402

from nucleo.persistencia import db                                # noqa: E402
from nucleo.canales import api                                    # noqa: E402

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()
T_A = f"prueba-g3-{uuid.uuid4().hex[:8]}"
T_B = f"prueba-g3-{uuid.uuid4().hex[:8]}"
DATOS = dict(host=os.environ["DBHOST"], port=os.environ["DBPORT"],
             dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
             password=os.environ["DBPASSWORD"])
admin = psycopg.connect(**DATOS, autocommit=True, row_factory=dict_row)


def sembrar_org(org, slug):
    oblig = admin.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name='organization' "
        "and is_nullable='NO' and column_default is null").fetchall()
    valores = {"id": str(org), "name": slug, "api_key": f"clave-{org}", "company_name": slug}
    for f in oblig:
        campo, tipo = f["column_name"], f["data_type"]
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


def proponer(tenant, herramienta="crear_ticket", resumen="Ticket de hace dos semanas"):
    """Una accion de legado: como las 36, sin conversacion."""
    # Sin conversation_id, como las 36 de produccion. guardar_accion_propuesta
    # devuelve (id, ya_existia) desde B5: aca la segunda siempre es False
    # porque sin conversacion no hay clave de equivalencia que colisionar.
    accion_id, _ = db.guardar_accion_propuesta(
        tenant, herramienta,
        # Argumentos con datos reales, como los de produccion: sirven para
        # comprobar que NO salen en la lista.
        {"servicio": 6555, "telefono": "573001112233", "asunto": "Sin internet"},
        resumen, "soporte", "ia")
    return accion_id


def fila(accion_id):
    return admin.execute(
        "select estado, motivo_rechazo, revisado_por, revisado_en "
        "from asistente.acciones_propuestas where id = %s", (accion_id,)).fetchone()


def eventos(accion_id):
    return admin.execute(
        "select tipo, motivo, actor_tipo, actor_nombre from asistente.acciones_eventos "
        "where accion_id = %s order by creado_en", (accion_id,)).fetchall()


class EjecutorEspia:
    """Cuenta cuantas veces se llamo al ejecutor real. Tiene que ser cero."""

    def __init__(self):
        self.llamadas = []

    def __call__(self, config, accion):
        self.llamadas.append(accion)
        return {"id": 999}, None


try:
    sembrar_org(ORG_A, T_A)
    sembrar_org(ORG_B, T_B)
    api.app.config["TESTING"] = True
    cliente = api.app.test_client()

    # =========================================================================
    titulo("1. aprobar no ejecuta, y no cambia nada")
    # =========================================================================
    espia = EjecutorEspia()
    original = api.motor.ejecutar_accion_aprobada
    api.motor.ejecutar_accion_aprobada = espia

    accion = proponer(T_A)
    antes = fila(accion)

    r = cliente.post(f"/acciones/propuestas/{accion}/aprobar",
                     json={"tenant": T_A, "revisado_por": "Ana Gomez"})
    revisar(r.status_code == 409, f"aprobar responde 409 (fue {r.status_code})")
    revisar(r.get_json().get("codigo") == "accion_de_legado",
            "y dice por que, con un codigo que la pantalla puede leer")

    # LO QUE MAS IMPORTA: el ejecutor no se llamo NI UNA VEZ.
    revisar(espia.llamadas == [],
            "el ejecutor real no se llamo ni una vez",
            f"se llamo {len(espia.llamadas)} vez/veces -- esto son tickets reales")

    despues = fila(accion)
    revisar(despues["estado"] == "pendiente" == antes["estado"],
            "la accion sigue 'pendiente': un rechazo no cambia el estado")
    revisar(despues["revisado_por"] is None and despues["revisado_en"] is None,
            "y no queda marcada como revisada por nadie")

    # El intento queda registrado: un 409 se responde y se pierde.
    tipos = [e["tipo"] for e in eventos(accion)]
    revisar(tipos == ["accion_aprobacion_rechazada"],
            "el intento queda en el expediente", f"{tipos}")

    # Insistir tampoco ejecuta: no hay un segundo intento que pase.
    for _ in range(3):
        cliente.post(f"/acciones/propuestas/{accion}/aprobar", json={"tenant": T_A})
    revisar(espia.llamadas == [],
            "insistir cuatro veces sigue sin ejecutar nada")

    # Y una accion CON conversacion si pasaria la guarda: lo que se prohibe es
    # el legado, no aprobar. Se comprueba sobre la funcion, porque la columna
    # todavia no existe (llega en B5).
    revisar(db.es_accion_de_legado({"conversation_id": None}) is True,
            "sin conversacion -> es de legado")
    revisar(db.es_accion_de_legado({"conversation_id": str(uuid.uuid4())}) is False,
            "con conversacion -> NO es de legado, la guarda la dejaria pasar",
            "Si esto fuera True, B5 nacería con el camino cerrado para todo.")

    # La regla NO mira la edad ni el tipo.
    vieja_con_conv = {"conversation_id": str(uuid.uuid4()),
                      "creado_en": "2020-01-01", "herramienta": "crear_ticket"}
    revisar(db.es_accion_de_legado(vieja_con_conv) is False,
            "una accion vieja CON conversacion no es de legado: no se mira la edad")

    api.motor.ejecutar_accion_aprobada = original

    # =========================================================================
    titulo("2. cancelada: durable, con motivo y con evento")
    # =========================================================================
    accion = proponer(T_A)
    r = cliente.post(f"/acciones/propuestas/{accion}/cancelar",
                     json={"tenant": T_A, "motivo": "Obsoleta: el cliente ya reporto de nuevo",
                           "cancelada_por": "Ana Gomez"})
    revisar(r.status_code == 200, f"cancelar responde 200 (fue {r.status_code})")

    f = fila(accion)
    revisar(f["estado"] == "cancelada",
            "el estado queda 'cancelada', no 'rechazada'",
            "Rechazada es 'la evalue y dije que no'; cancelada es 'quedo obsoleta'.")
    revisar(f["motivo_rechazo"] == "Obsoleta: el cliente ya reporto de nuevo",
            "con su motivo guardado")
    revisar(f["revisado_por"] == "Ana Gomez" and f["revisado_en"] is not None,
            "y con quien la cancelo y cuando")

    evs = eventos(accion)
    revisar([e["tipo"] for e in evs] == ["accion_cancelada"],
            "deja su evento en el expediente", f"{[e['tipo'] for e in evs]}")
    revisar(evs[0]["motivo"] == "Obsoleta: el cliente ya reporto de nuevo",
            "el evento lleva el motivo, no solo la fila")
    revisar(evs[0]["actor_nombre"] == "Ana Gomez" and evs[0]["actor_tipo"] == "operador",
            "y dice quien fue: una cancelacion administrativa sin nombre no se audita")

    # El estado y el evento entran juntos (I12). Se comprueba contando: si el
    # evento se escribiera en otra transaccion, una caida entre las dos dejaria
    # la fila cancelada sin expediente.
    huerfanas = admin.execute(
        "select count(*) from asistente.acciones_propuestas a "
        "where a.estado = 'cancelada' and not exists ("
        "  select 1 from asistente.acciones_eventos e "
        "  where e.accion_id = a.id and e.tipo = 'accion_cancelada')").fetchone()["count"]
    revisar(huerfanas == 0, "ninguna cancelada quedo sin su evento (I12)")

    # Cancelar algo ya resuelto no reescribe historia.
    r = cliente.post(f"/acciones/propuestas/{accion}/cancelar",
                     json={"tenant": T_A, "motivo": "otra cosa", "cancelada_por": "Otro"})
    revisar(r.status_code == 409, f"cancelar dos veces responde 409 (fue {r.status_code})")
    revisar(fila(accion)["motivo_rechazo"] == "Obsoleta: el cliente ya reporto de nuevo",
            "y el motivo original no se pisa")
    revisar(len(eventos(accion)) == 1, "sin un segundo evento")

    # El motivo es obligatorio: 36 filas sin explicacion no sirven de nada.
    otra = proponer(T_A)
    r = cliente.post(f"/acciones/propuestas/{otra}/cancelar",
                     json={"tenant": T_A, "cancelada_por": "Ana"})
    revisar(r.status_code == 400 and fila(otra)["estado"] == "pendiente",
            "cancelar sin motivo se rechaza y no cambia nada")
    r = cliente.post(f"/acciones/propuestas/{otra}/cancelar",
                     json={"tenant": T_A, "motivo": "obsoleta"})
    revisar(r.status_code == 400 and fila(otra)["estado"] == "pendiente",
            "cancelar sin decir quien tampoco")

    # Y la base lo sostiene aunque alguien escriba por su cuenta.
    try:
        admin.execute(
            "insert into asistente.acciones_propuestas "
            "(organization_id, herramienta, resumen, propuesto_por, estado) "
            "values (%s, 'x', 'y', 'ia', 'inventado')", (str(ORG_A),))
        revisar(False, "la base rechaza un estado inventado")
    except psycopg.errors.CheckViolation:
        revisar(True, "la base rechaza un estado inventado")
    try:
        admin.execute(
            "insert into asistente.acciones_propuestas "
            "(organization_id, herramienta, resumen, propuesto_por, estado) "
            "values (%s, 'x', 'y', 'ia', 'cancelada')", (str(ORG_A),))
        revisar(False, "la base rechaza una cancelada sin motivo")
    except psycopg.errors.CheckViolation:
        revisar(True, "la base rechaza una cancelada sin motivo")

    # =========================================================================
    titulo("3. la lista: que se ve y que no")
    # =========================================================================
    r = cliente.get(f"/acciones/propuestas?tenant={T_A}&estado=pendiente")
    acciones = r.get_json()["acciones"]
    revisar(all(a["estado"] == "pendiente" for a in acciones),
            "filtra por estado")
    revisar(all(a["es_legado"] is True for a in acciones),
            "hoy todas son de legado, y la lista lo dice")

    crudo = json.dumps(acciones, ensure_ascii=False)
    revisar("argumentos" not in crudo,
            "la lista NO trae 'argumentos'",
            "Ahi estan los valores REALES sin enmascarar: telefono, cedula, direccion.")
    for dato in ("573001112233", "6555"):
        revisar(dato not in crudo, f"ni el dato '{dato}' por ningun otro camino")
    revisar(all("resumen" in a for a in acciones),
            "pero si el resumen, que es lo que hace falta para revisarla")

    # =========================================================================
    titulo("4. una empresa no ve ni toca las de otra")
    # =========================================================================
    de_b = proponer(T_B)
    r = cliente.get(f"/acciones/propuestas?tenant={T_A}")
    revisar(str(de_b) not in json.dumps(r.get_json()),
            "la lista de A no incluye las de B")

    r = cliente.post(f"/acciones/propuestas/{de_b}/cancelar",
                     json={"tenant": T_A, "motivo": "ajena", "cancelada_por": "Ana"})
    revisar(r.status_code == 404, f"A no puede cancelar una de B (fue {r.status_code})")
    revisar(fila(de_b)["estado"] == "pendiente",
            "y la de B sigue intacta")
    revisar(eventos(de_b) == [], "sin eventos escritos en el expediente ajeno")

    espia = EjecutorEspia()
    api.motor.ejecutar_accion_aprobada = espia
    r = cliente.post(f"/acciones/propuestas/{de_b}/aprobar", json={"tenant": T_A})
    revisar(r.status_code == 404 and espia.llamadas == [],
            "A tampoco puede aprobar una de B")
    api.motor.ejecutar_accion_aprobada = original

    # =========================================================================
    titulo("5. la reconciliacion de las 36")
    # =========================================================================
    # Ninguna se adopta sola: no hay codigo que cancele ni apruebe en lote.
    fuente = (RAIZ / "nucleo").rglob("*.py")
    automatico = []
    for archivo in fuente:
        texto = archivo.read_text(encoding="utf-8")
        for linea in texto.splitlines():
            if "cancelar_accion_propuesta" in linea and "def " not in linea:
                automatico.append(f"{archivo.name}: {linea.strip()[:60]}")
    revisar(all("api.py" in a for a in automatico),
            "solo el endpoint cancela: ningun proceso lo hace por su cuenta",
            f"{automatico}")

    reloj = (RAIZ / "nucleo" / "reloj.py").read_text(encoding="utf-8")
    revisar("acciones_propuestas" not in reloj and "cancelar_accion" not in reloj,
            "el reloj no vence ni cancela acciones (§11.4: nada de vencerlas)")

finally:
    for org in (ORG_A, ORG_B):
        admin.execute("delete from public.organization where id = %s", (str(org),))
    admin.close()

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El legado no se puede ejecutar, y se puede cancelar dejando rastro.")
