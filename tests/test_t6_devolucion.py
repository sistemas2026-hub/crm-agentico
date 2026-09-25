# -*- coding: utf-8 -*-
"""
================================================================================
 T6 -- RESPONDER Y DEVOLVER A LA IA
================================================================================

    py -3.13 tests/test_t6_devolucion.py                          (sin base)

Por que existe
--------------
T6 pone la conversacion de vuelta en manos de la IA. Si eso ocurre sin que la
respuesta del operador haya salido de verdad, el cliente queda esperando una
contestacion que nadie mando y la IA sigue la conversacion como si no hubiera
pasado nada. Por eso el invariante:

    NINGUN camino pone control = 'ia' por T6 sin que esten durablemente
    persistidos wamid + estado_entrega = 'enviado'.

El caso que obliga a todo lo demas es el corte a la mitad: Meta acepta el
mensaje y el proceso se cae ANTES de anotar el wamid. La fila queda
'pendiente', igual que si no hubiera salido nunca -- los dos casos son
indistinguibles mirando messages. El desempate vive en whatsapp_salidas, que se
reserva ANTES del POST. Un reintento que no lo consulte trata "pudo haber
salido" como "no salio", y eso es afirmar algo que Dexter no sabe.

  1. el invariante, leido del codigo: quien llama a devolver_a_ia y con que guarda
  2. el paso del rechazo no suelta control ni asignacion
  3. B1-B4 contra el endpoint real, con la base y el canal doblados
  4. idempotencia: la misma clave dos veces no produce dos efectos
================================================================================
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ.pop("MOTOR_SERVICE_TOKEN", None)

fallos: list[str] = []
TENANT = "rapilink"
CONV = "11111111-1111-4111-8111-111111111111"
AUTOR = {"autor": "Operador de prueba", "autor_usuario_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}


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


# =============================================================================
titulo("1. el invariante, leido del codigo")
# =============================================================================
fuente_api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
arbol_api = ast.parse(fuente_api)


def _guardas_de(nodo):
    """Las condiciones de los `if` que envuelven a este nodo, como texto."""
    pila, padres = [], {}
    for n in ast.walk(arbol_api):
        for hijo in ast.iter_child_nodes(n):
            padres[hijo] = n
    actual = nodo
    while actual in padres:
        padre = padres[actual]
        if isinstance(padre, ast.If) and actual not in padre.orelse:
            pila.append(ast.unparse(padre.test))
        actual = padre
    return pila


llamadas = [n for n in ast.walk(arbol_api)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "devolver_a_ia"]
revisar(len(llamadas) == 3,
        "devolver_a_ia se llama en exactamente 3 lugares",
        f"encontrados {len(llamadas)} en lineas {[n.lineno for n in llamadas]}")

sin_guarda = []
for n in llamadas:
    guardas = " ".join(_guardas_de(n))
    # O bien la guarda nombra la aceptacion, o bien es el canal que no entrega
    # por WhatsApp (simulador/API: no hay wamid posible y el contrato lo dice
    # devolviendo aceptado_por_meta = None).
    if not ("aceptado" in guardas or "!= 'whatsapp'" in guardas):
        sin_guarda.append(n.lineno)
revisar(not sin_guarda,
        "las 3 llamadas exigen aceptacion (o son de un canal sin entrega)",
        f"sin guarda de aceptacion: lineas {sin_guarda}")

revisar("_salida_previa(tenant, f'humano:{clave}')" in fuente_api.replace('"', "'"),
        "el reintento desempata por whatsapp_salidas y no solo por la fila",
        "sin esto, 'pudo haber salido' se trata como 'no salio'")

revisar("uuid" not in fuente_api.split("def conversaciones_responder_humano")[1][:6000],
        "la clave de salida de T6 no se inventa: viene del cliente",
        "un uuid nuevo por intento no es una clave idempotente")

# =============================================================================
titulo("2. el rechazo no suelta el control")
# =============================================================================
arbol_tr = ast.parse((RAIZ / "nucleo" / "relevo" / "transiciones.py").read_text(encoding="utf-8"))
fallida = next(n for n in ast.walk(arbol_tr)
               if isinstance(n, ast.FunctionDef) and n.name == "registrar_devolucion_fallida")
cuerpo_fallida = ast.unparse(fallida)
for prohibido, que in (("_subir_version", "no sube la version del relevo"),
                       ("control =", "no toca la columna control"),
                       ("asignada_a", "no toca la asignacion")):
    revisar(prohibido not in cuerpo_fallida,
            f"el paso 3 fallido {que}",
            f"aparece '{prohibido}' en registrar_devolucion_fallida")

solicitar = next(n for n in ast.walk(arbol_tr)
                 if isinstance(n, ast.FunctionDef) and n.name == "solicitar_devolucion")
cuerpo_solicitar = ast.unparse(solicitar)
revisar("control = 'ia'" not in cuerpo_solicitar,
        "el paso 1 guarda el mensaje y la intencion, pero NO devuelve el control",
        "T6 no puede soltar el control antes de que el mensaje salga")

# =============================================================================
titulo("3. B1-B4 contra el endpoint, con la base y el canal doblados")
# =============================================================================
from nucleo.canales import api                                    # noqa: E402
from nucleo.relevo.transiciones import Resultado                  # noqa: E402

api.app.config["TESTING"] = True
cliente = api.app.test_client()


class Espia:
    """Lo que la base 'contesto' y lo que el endpoint le pidio."""

    def __init__(self, estado_fila, estado_salida, wamid=None):
        self.estado_fila = estado_fila
        self.estado_salida = estado_salida
        self.wamid = wamid
        self.devuelta = False
        self.fallida = None
        self.envios = 0


def montar(espia, monkey):
    monkey.append((api, "_exigir_control_humano", api._exigir_control_humano))
    api._exigir_control_humano = lambda *a, **k: None

    def solicitar(tenant, conv, contenido, **kw):
        # Siempre el camino de reintento: la clave ya existia.
        return {"canal": "whatsapp", "usuario_externo": "573001112233",
                "ticket_operativo": None, "mensaje_id": "m-1",
                "existente": True, "estado_entrega": espia.estado_fila}

    def salida_whatsapp(tenant, clave):
        if espia.estado_salida is None:
            return None
        return {"estado": espia.estado_salida, "wamid": espia.wamid, "error": None}

    def devolver(tenant, conv, **kw):
        espia.devuelta = True
        return Resultado(True, True, 3, None)

    def fallida(tenant, conv, mensaje_id, *, resultado, **kw):
        espia.fallida = resultado
        return Resultado(True, True, 2, None)

    def entregar(*a, **k):
        espia.envios += 1
        return {"resultado": "aceptado", "aceptado_por_meta": True,
                "aceptacion_registrada": True}

    for obj, nombre, valor in ((api.transiciones, "solicitar_devolucion", solicitar),
                               (api.transiciones, "devolver_a_ia", devolver),
                               (api.transiciones, "registrar_devolucion_fallida", fallida),
                               (api.persistencia, "salida_whatsapp", salida_whatsapp),
                               (api, "_entregar_y_registrar", entregar)):
        monkey.append((obj, nombre, getattr(obj, nombre)))
        setattr(obj, nombre, valor)


def pedir(espia):
    monkey: list = []
    montar(espia, monkey)
    try:
        r = cliente.post(f"/conversaciones/{CONV}/mensajes", json={
            "tenant": TENANT, "mensaje": "Ya quedo resuelto, cualquier cosa avisame.",
            "devolver_al_asistente": True, "clave_idempotencia": "k-1", **AUTOR})
        return r.get_json() or {}
    finally:
        for obj, nombre, original in reversed(monkey):
            setattr(obj, nombre, original)


# B1: se reservo la salida y el proceso murio ANTES del POST.
b1 = Espia(estado_fila="pendiente", estado_salida="adquirido")
r = pedir(b1)
revisar(r.get("resultado") == "incierto" and not r.get("devuelto_al_asistente"),
        "B1 (crash antes del POST): no devuelve a la IA y lo llama incierto",
        f"{r}")
revisar(b1.envios == 0, "B1 no reenvia el mensaje", f"envios={b1.envios}")
revisar(b1.fallida == "incierto",
        "B1 deja evidencia del intento, marcada como incierta y no como fallo",
        f"evento={b1.fallida}")

# B2: Meta ACEPTO y el proceso murio antes de anotar el wamid. La fila es
# identica a la de B1 -- este es el caso que obliga a mirar whatsapp_salidas.
b2 = Espia(estado_fila="pendiente", estado_salida="adquirido")
r = pedir(b2)
revisar(not r.get("devuelto_al_asistente") and r.get("resultado") == "incierto",
        "B2 (Meta acepto, crash antes del wamid): tampoco devuelve",
        f"{r}")
revisar(b2.fallida == "incierto" and b2.fallida != "rechazado",
        "B2 NO se clasifica como rechazo: no consta que Meta lo haya rechazado",
        f"evento={b2.fallida}")

# B3: el wamid quedo guardado; lo unico que falto fue el paso 4.
b3 = Espia(estado_fila="enviado", estado_salida="aceptado", wamid="wamid-123")
r = pedir(b3)
revisar(r.get("devuelto_al_asistente") is True and r.get("resultado") == "aceptado",
        "B3 (wamid durable, crash antes del paso 4): el reintento lo completa",
        f"{r}")
revisar(b3.fallida is None, "B3 no registra un fallo", f"evento={b3.fallida}")

# B3b: la fila se quedo en 'pendiente' pero la salida SI sello la aceptacion.
b3b = Espia(estado_fila="pendiente", estado_salida="aceptado", wamid="wamid-456")
r = pedir(b3b)
revisar(r.get("devuelto_al_asistente") is True,
        "B3b: la aceptacion sellada en whatsapp_salidas tambien alcanza",
        f"{r}")

# B4 lo cubre transiciones: la misma clave replaya el evento en vez de repetirlo.
revisar("_replay(previo, tipo, actor_id)" in ast.unparse(
            next(n for n in ast.walk(arbol_tr)
                 if isinstance(n, ast.FunctionDef) and n.name == "_ejecutar")),
        "B4 (crash dentro del paso 4): la misma clave replaya, no repite")

# Rechazo confirmado: eso SI es un fallo, y se dice asi.
rech = Espia(estado_fila="pendiente", estado_salida="rechazado")
r = pedir(rech)
revisar(r.get("resultado") == "rechazado" and rech.fallida == "rechazado",
        "un rechazo confirmado se registra como rechazo, no como incierto",
        f"{r}")
revisar(not r.get("devuelto_al_asistente"), "un rechazo no devuelve a la IA")

# Sin rastro de la salida: tampoco se afirma nada.
nada = Espia(estado_fila="pendiente", estado_salida=None)
r = pedir(nada)
revisar(r.get("resultado") == "incierto",
        "sin fila en whatsapp_salidas el resultado es incierto, nunca rechazado",
        f"{r}")

# =============================================================================
titulo("4. idempotencia")
# =============================================================================
r = cliente.post(f"/conversaciones/{CONV}/mensajes", json={
    "tenant": TENANT, "mensaje": "hola", "devolver_al_asistente": True, **AUTOR})
revisar(r.status_code == 400 and (r.get_json() or {}).get("codigo") == "clave_requerida",
        "T6 sin clave de idempotencia se rechaza ANTES de escribir nada",
        f"{r.status_code} {r.get_json()}")

# =============================================================================
titulo("5. contra PostgreSQL real")
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print(f"  [saltado] la parte con base necesita {faltan} y una base construida "
          f"por el ledger (cli/base_desde_cero.py)")
else:
    import uuid                                                   # noqa: E402

    import psycopg                                                # noqa: E402

    from nucleo.persistencia import db                            # noqa: E402
    from nucleo.relevo import transiciones                        # noqa: E402

    ORG, OTRA = uuid.uuid4(), uuid.uuid4()
    T_A = f"prueba-t6-{uuid.uuid4().hex[:8]}"
    T_B = f"prueba-t6-{uuid.uuid4().hex[:8]}"
    OPERADOR = {"operador_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
                "operador_nombre": "Ana Perez"}
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

    def conversacion(org, *, control="humano"):
        return admin.execute(
            "insert into asistente.conversations (organization_id, canal, usuario_externo, "
            "estado, control, control_motivo, relevo_version, escalada_a_humano, "
            "necesita_atencion_humana) values (%s, 'whatsapp', %s, 'abierta', %s, 'escalada', "
            "1, true, true) returning id",
            (str(org), f"57300{uuid.uuid4().int % 10**7:07d}", control)).fetchone()[0]

    def fila_mensaje(mid):
        return admin.execute("select wamid, estado_entrega from asistente.messages where id = %s",
                             (mid,)).fetchone()

    def salida(org, clave):
        return admin.execute("select estado, wamid from asistente.whatsapp_salidas "
                             "where organization_id = %s and clave_idempotencia = %s",
                             (str(org), clave)).fetchone()

    def eventos(conv, tipo=None):
        sql = "select tipo, datos from asistente.relevo_eventos where conversation_id = %s"
        p = [conv]
        if tipo:
            sql += " and tipo = %s"
            p.append(tipo)
        return admin.execute(sql + " order by creado_en", p).fetchall()

    try:
        sembrar_org(ORG, T_A)
        sembrar_org(OTRA, T_B)

        # --- T6 completo: paso 1 + entrega + paso 4 ------------------------
        conv = conversacion(ORG)
        clave = f"k-{uuid.uuid4().hex[:8]}"
        d = transiciones.solicitar_devolucion(T_A, conv, "Ya quedo resuelto.",
                                              clave=clave, **OPERADOR)
        control = admin.execute("select control from asistente.conversations where id = %s",
                                (conv,)).fetchone()[0]
        revisar(d and not d["existente"] and control == "humano",
                "paso 1: guarda el mensaje y NO suelta el control todavia",
                f"control={control}")
        revisar(len(eventos(conv, "devolucion_solicitada")) == 1,
                "paso 1: queda el evento de la intencion")

        db.adquirir_salida_whatsapp(T_A, f"humano:{clave}", proposito="prueba",
                                    mensaje_id=d["mensaje_id"], conversation_id=conv)
        db.marcar_envio(T_A, d["mensaje_id"], "wamid.T6", clave_salida=f"humano:{clave}",
                        resultado="aceptado")
        r = transiciones.devolver_a_ia(T_A, conv, clave=f"devolver:{clave}", **OPERADOR)
        control = admin.execute("select control, asignada_a_usuario_id from "
                                "asistente.conversations where id = %s", (conv,)).fetchone()
        revisar(r.aplicada and control[0] == "ia" and control[1] is None,
                "paso 4: control vuelve a la IA y la asignacion se libera", f"{control}")

        # --- ATOMICIDAD de marcar_envio ------------------------------------
        conv2 = conversacion(ORG)
        c2 = f"k-{uuid.uuid4().hex[:8]}"
        d2 = transiciones.solicitar_devolucion(T_A, conv2, "texto", clave=c2, **OPERADOR)
        db.adquirir_salida_whatsapp(T_A, f"humano:{c2}", proposito="prueba",
                                    mensaje_id=d2["mensaje_id"], conversation_id=conv2)
        db.marcar_envio(T_A, d2["mensaje_id"], "wamid.ATOM", clave_salida=f"humano:{c2}",
                        resultado="aceptado")
        msg, sal = fila_mensaje(d2["mensaje_id"]), salida(ORG, f"humano:{c2}")
        revisar(msg == ("wamid.ATOM", "enviado") and sal == ("aceptado", "wamid.ATOM"),
                "marcar_envio deja messages y whatsapp_salidas coherentes", f"{msg} {sal}")

        # El caso que probaria la premisa falsa: la fila del mensaje NO se
        # puede tocar (es de otra empresa) pero la salida si. Si la salida
        # quedara 'aceptado' con la fila vacia, habria que reconciliar.
        conv_b = conversacion(OTRA)
        ajeno = admin.execute(
            "insert into asistente.messages (organization_id, conversation_id, rol, contenido, "
            "estado_entrega) values (%s, %s, 'assistant', 'x', 'pendiente') returning id",
            (str(OTRA), conv_b)).fetchone()[0]
        c3 = f"k-{uuid.uuid4().hex[:8]}"
        db.adquirir_salida_whatsapp(T_A, f"humano:{c3}", proposito="prueba")
        escrita = db.marcar_envio(T_A, ajeno, "wamid.AJENO", clave_salida=f"humano:{c3}",
                                  resultado="aceptado")
        msg_ajeno, sal3 = fila_mensaje(ajeno), salida(ORG, f"humano:{c3}")
        revisar(escrita is False and msg_ajeno == (None, "pendiente"),
                "una fila de otra empresa no se toca", f"{escrita} {msg_ajeno}")
        revisar(not (sal3 and sal3[0] == "aceptado" and msg_ajeno[0] is None)
                or escrita is False,
                "y si la salida quedo sellada sin la fila, marcar_envio lo DICE (False)",
                f"salida={sal3} fila={msg_ajeno}")

        # --- IDEMPOTENCIA real ---------------------------------------------
        c4 = f"k-{uuid.uuid4().hex[:8]}"
        primera = db.adquirir_salida_whatsapp(T_A, f"humano:{c4}", proposito="prueba")
        segunda = db.adquirir_salida_whatsapp(T_A, f"humano:{c4}", proposito="prueba")
        revisar(primera is True and segunda is False,
                "la misma clave se adquiere UNA sola vez", f"{primera} {segunda}")

        conv3 = conversacion(ORG)
        c5 = f"k-{uuid.uuid4().hex[:8]}"
        a = transiciones.solicitar_devolucion(T_A, conv3, "texto", clave=c5, **OPERADOR)
        b = transiciones.solicitar_devolucion(T_A, conv3, "texto", clave=c5, **OPERADOR)
        n = admin.execute("select count(*) from asistente.messages where conversation_id = %s",
                          (conv3,)).fetchone()[0]
        revisar(b["existente"] is True and str(a["mensaje_id"]) == str(b["mensaje_id"]) and n == 1,
                "el paso 1 con la misma clave no crea un segundo mensaje", f"{n} filas")

        r1 = transiciones.devolver_a_ia(T_A, conv3, clave=f"dev:{c5}", **OPERADOR)
        r2 = transiciones.devolver_a_ia(T_A, conv3, clave=f"dev:{c5}", **OPERADOR)
        revisar(r1.aplicada and r2.motivo == "reintento"
                and len(eventos(conv3, "devuelta_a_ia")) == 1,
                "B4 real: la misma clave replaya y deja UN solo evento",
                f"{r1.motivo} {r2.motivo} {len(eventos(conv3, 'devuelta_a_ia'))}")

        # --- CONCURRENCIA con dos conexiones reales -------------------------
        c6 = f"k-{uuid.uuid4().hex[:8]}"
        datos = dict(host=os.environ["DBHOST"], port=os.environ["DBPORT"],
                     dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
                     password=os.environ["DBPASSWORD"])
        ins = ("insert into asistente.whatsapp_salidas (organization_id, "
               "clave_idempotencia, proposito) values (%s, %s, 'carrera') "
               "on conflict (organization_id, clave_idempotencia) do nothing "
               "returning clave_idempotencia")
        with psycopg.connect(**datos) as ca, psycopg.connect(**datos) as cb:
            ga = ca.execute(ins, (str(ORG), c6)).fetchone()
            # B todavia NO puede saber si gana: la clave de A esta escrita y sin
            # confirmar. Que PostgreSQL lo BLOQUEE aca es la prueba de que el
            # indice unico serializa de verdad, y no solo la logica de Python.
            cb.execute("set local lock_timeout = '700ms'")
            try:
                cb.execute(ins, (str(ORG), c6)).fetchone()
                bloqueo = False
            except psycopg.errors.LockNotAvailable:
                bloqueo = True
            except psycopg.errors.QueryCanceled:
                bloqueo = True
            cb.rollback()
            revisar(bool(ga) and bloqueo,
                    "dos transacciones simultaneas: la segunda queda bloqueada por el indice",
                    f"a={ga} bloqueo={bloqueo}")
            ca.commit()
            gb = cb.execute(ins, (str(ORG), c6)).fetchone()
            cb.commit()
            revisar(not gb, "y al desbloquearse NO obtiene un segundo derecho a enviar", f"{gb}")

        # --- T6 contra un cambio de control concurrente ---------------------
        conv4 = conversacion(ORG)
        c7 = f"k-{uuid.uuid4().hex[:8]}"
        transiciones.solicitar_devolucion(T_A, conv4, "texto", clave=c7, **OPERADOR)
        # El esquema exige coherencia: control 'ia' no lleva motivo.
        admin.execute("update asistente.conversations set control = 'ia', "
                      "control_motivo = null where id = %s", (conv4,))
        r = transiciones.devolver_a_ia(T_A, conv4, clave=f"dev:{c7}", **OPERADOR)
        revisar(not r.aplicada and r.motivo == "no_es_humana",
                "si alguien solto el control en el medio, el paso 4 no aplica (fail closed)",
                f"{r.motivo}")

        # --- AISLAMIENTO entre empresas -------------------------------------
        c8 = f"k-{uuid.uuid4().hex[:8]}"
        db.adquirir_salida_whatsapp(T_A, c8, proposito="de A")
        gana_b = db.adquirir_salida_whatsapp(T_B, c8, proposito="de B")
        revisar(gana_b is True,
                "la misma clave en OTRA empresa es otra salida: no se pisan", f"{gana_b}")
        revisar(db.salida_whatsapp(T_B, c8)["estado"] == "adquirido"
                and salida(ORG, c8) is not None,
                "y cada una ve la suya")
        conv5 = conversacion(OTRA)
        antes = admin.execute("select count(*) from asistente.messages "
                              "where conversation_id = %s", (conv5,)).fetchone()[0]
        try:
            transiciones.solicitar_devolucion(T_A, conv5, "texto",
                                              clave=f"k-{uuid.uuid4().hex[:8]}", **OPERADOR)
        except Exception:
            pass   # que rechace es una forma valida de no cruzarse; lo que se
                   # mide es el EFECTO sobre la conversacion ajena, no la excepcion
        despues = admin.execute("select count(*) from asistente.messages "
                                "where conversation_id = %s", (conv5,)).fetchone()[0]
        revisar(despues == antes == 0,
                "el paso 1 de una empresa no escribe en la conversacion de otra",
                f"antes={antes} despues={despues}")
        revisar(admin.execute("select control, relevo_version from asistente.conversations "
                              "where id = %s", (conv5,)).fetchone() == ("humano", 1),
                "y la conversacion de la otra empresa no cambia de control ni de version")
    finally:
        admin.close()

# =============================================================================
print(f"\n{'=' * 76}")
if fallos:
    print(f"\nFALLAS ({len(fallos)}):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\nOK: T6 no devuelve a la IA sin aceptacion durable, y lo que no sabe no lo afirma")
