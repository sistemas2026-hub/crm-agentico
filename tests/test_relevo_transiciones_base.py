# -*- coding: utf-8 -*-
"""
================================================================================
 LAS TRANSICIONES DEL RELEVO  --  escritura en paralelo, contra PostgreSQL
================================================================================

    DBHOST=localhost DBPORT=55435 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_relevo_transiciones_base.py

B3.2 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md. Base efimera del ledger.

  1. Cada transicion sobre una conversacion gobernada: estado nuevo, legado,
     UN evento con la version resultante, version +1. Y lo que NO hace:
     soltar no devuelve a la IA, resolver no devuelve, tomar no marca
     atendida_manual, un cierre externo no le quita la conversacion a quien
     la tiene.
  2. Legado (version 0): tomar, soltar, resolver y devolver escriben solo las
     banderas de siempre; ni evento ni version.
  3. Idempotencia: la misma clave dos veces (y dos hilos a la vez) -> un
     cambio, un evento, una version.
  4. Rollback: si el evento falla, o algo falla despues de escribir y antes del
     commit, no queda ni estado ni evento.
  5. La escalada en un turno real de atender_turno(): cuando se llama al
     ticket operativo y al CRM, el control YA es humano en la base y NO hay
     ninguna transaccion abierta; si el CRM falla, el control no vuelve a la IA.
================================================================================
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
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
BASE = "b3_trans_" + uuid.uuid4().hex[:6]
TENANT = "rapilink"          # el slug de la config real: el turno de la seccion 5 la usa
ANA = ("7c9e6679-7425-40de-944b-e07fc1f90ae7", "Ana Perez")
LUIS = ("0f8fad5b-d9cb-469f-a165-70867728950e", "Luis Rojas")

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


def estado(conv):
    return q("""select control, control_motivo, asignada_a_nombre, relevo_version, estado,
                       escalada_a_humano, necesita_atencion_humana, tomada_por, atendida_manual, aviso_relevo
                from asistente.conversations where id = %s""", (conv,))[0]


def eventos(conv):
    return q("""select tipo, actor_tipo, actor_nombre, (datos->>'version')::int, datos
                from asistente.relevo_eventos where conversation_id = %s order by creado_en""", (conv,))


def nueva_conv(org, tel):
    return str(q("""insert into asistente.conversations (organization_id, canal, usuario_externo)
                    values (%s, 'whatsapp-simulado', %s) returning id""", (org, tel))[0][0])


print("=" * 74)
print(" LAS TRANSICIONES DEL RELEVO")
print("=" * 74)

try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO, "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    org = str(uuid.uuid4())
    fila_minima("organization", {"id": org, "name": "Org B3.2"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (org, TENANT))
    os.environ["DBNAME"] = BASE
    from nucleo.persistencia import db                              # noqa: E402
    from nucleo.relevo import transiciones as T                     # noqa: E402

    # -----------------------------------------------------------------------
    print("\n== 1. transiciones sobre una conversacion gobernada ==")
    c = nueva_conv(org, "573000000010")
    r1 = T.escalar(TENANT, c, motivo="solicitud_explicita")
    e = estado(c)
    comprobar(r1.aplicada and e[:4] == ("humano", "escalada", None, 1),
              f"escalar: humano/escalada, sin asignacion, version 1 ({e[:4]})")
    comprobar(e[5] is True and e[6] is True,
              "escalar escribe TAMBIEN las banderas de legado que deciden la pausa, en la misma transaccion")
    ev = eventos(c)
    comprobar(len(ev) == 1 and ev[0][:2] == ("escalada", "ia") and ev[0][3] == 1,
              f"un evento 'escalada' del actor ia con version 1 ({ev})")
    r1b = T.escalar(TENANT, c)
    comprobar(not r1b.aplicada and len(eventos(c)) == 1 and estado(c)[3] == 1,
              "escalar otra vez: no-op, sin evento ni version")

    r2 = T.tomar(TENANT, c, operador_id=ANA[0], operador_nombre=ANA[1])
    e = estado(c)
    comprobar(r2.aplicada and e[:4] == ("humano", "escalada", "Ana Perez", 2) and e[7] == "Ana Perez",
              f"tomar: asignada a Ana, control y motivo intactos, version 2, legado tomada_por ({e})")
    comprobar(e[8] is False, "tomar NO marca atendida_manual (no es resolver)")
    comprobar(not T.tomar(TENANT, c, operador_id=ANA[0], operador_nombre=ANA[1]).aplicada
              and estado(c)[3] == 2 and len(eventos(c)) == 2,
              "tomar de nuevo por la misma persona: no-op")

    r3 = T.soltar(TENANT, c, operador_id=ANA[0], operador_nombre=ANA[1])
    e = estado(c)
    comprobar(r3.aplicada and e[:4] == ("humano", "escalada", None, 3) and e[7] is None,
              f"soltar: sin asignacion y SIGUE humana (no es devolver) ({e})")
    ult = eventos(c)[-1]
    comprobar(ult[0] == "soltada" and ult[2] == "Ana Perez" and ult[4].get("anterior_nombre") == "Ana Perez",
              "evento 'soltada' con quien la tenia")

    T.tomar(TENANT, c, operador_id=LUIS[0], operador_nombre=LUIS[1])
    r4 = T.devolver_a_ia(TENANT, c, operador_id=LUIS[0], operador_nombre=LUIS[1])
    e = estado(c)
    comprobar(r4.aplicada and e[:4] == ("ia", None, None, 5) and e[5] is False and e[6] is False,
              f"devolver: control ia, sin motivo ni asignacion, legado sin pausa ({e})")
    comprobar(eventos(c)[-1][0] == "devuelta_a_ia", "evento 'devuelta_a_ia'")

    c2 = nueva_conv(org, "573000000011")
    T.escalar(TENANT, c2)
    T.tomar(TENANT, c2, operador_id=ANA[0], operador_nombre=ANA[1])
    r5 = T.resolver(TENANT, c2, operador_id=ANA[0], operador_nombre=ANA[1])
    e = estado(c2)
    comprobar(r5.aplicada and e[4] == "cerrada" and e[8] is True and e[2] is None,
              f"resolver: cerrada, atendida_manual, asignacion liberada ({e})")
    comprobar(e[0] == "humano", "resolver NO devuelve a la IA: el control queda como estaba")
    comprobar(eventos(c2)[-1][0] == "cerrada" and r5.datos.get("usuario_externo") == "573000000011",
              "evento 'cerrada' y devuelve usuario/canal para limpiar la sesion")

    c3 = nueva_conv(org, "573000000012")
    T.escalar(TENANT, c3)
    T.tomar(TENANT, c3, operador_id=ANA[0], operador_nombre=ANA[1])
    r6 = T.caso_externo_cerrado(TENANT, c3)
    e = estado(c3)
    comprobar(r6.aplicada and e[0] == "humano" and e[2] == "Ana Perez" and e[9] == "caso_externo_cerrado",
              f"caso cerrado afuera con Ana a cargo: aviso, control y asignacion intactos ({e})")
    comprobar(eventos(c3)[-1][4].get("aplicado") is False, "evento con aplicado=false")
    comprobar(not T.caso_externo_cerrado(TENANT, c3).aplicada, "el mismo aviso no se repite")
    c4 = nueva_conv(org, "573000000013")
    T.escalar(TENANT, c4)
    T.caso_externo_cerrado(TENANT, c4)
    e = estado(c4)
    comprobar(e[0] == "humano" and e[5] is True and e[9] == "caso_externo_cerrado"
              and eventos(c4)[-1][4].get("aplicado") is False,
              f"caso cerrado afuera SIN nadie a cargo: tampoco devuelve a la IA, solo aviso ({e})")
    comprobar([x[0] for x in eventos(c4)].count("devuelta_a_ia") == 0,
              "el unico camino de vuelta a la IA sigue siendo devolver_a_ia")

    c5 = nueva_conv(org, "573000000014")
    r7 = T.intervenir(TENANT, c5, operador_id=ANA[0], operador_nombre=ANA[1], motivo_texto="respuesta incorrecta")
    e = estado(c5)
    comprobar(r7.aplicada and e[:4] == ("humano", "intervencion", "Ana Perez", 1),
              f"intervenir: humano/intervencion y tomada por quien intervino ({e[:4]})")
    ev = eventos(c5)[-1]
    comprobar(ev[:3] == ("intervencion", "operador", "Ana Perez") and ev[4].get("tomada") is True,
              "evento 'intervencion' del operador")

    c9 = nueva_conv(org, "573000000015")
    db.cerrar_conversacion(TENANT, c9)
    comprobar(estado(c9)[4] == "cerrada" and estado(c9)[8] is False,
              "T15b: el cierre que hace la IA (cerrar_conversacion) NO marca atendida_manual")

    print("\n== 1b. control efectivo ==")
    leg_esc = str(q("""insert into asistente.conversations
                         (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana)
                       values (%s, 'whatsapp', '573000000016', true, true) returning id""", (org,))[0][0])
    leg_agenda = str(q("""insert into asistente.conversations
                            (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana)
                          values (%s, 'whatsapp', '573000000017', true, false) returning id""", (org,))[0][0])
    comprobar(db.control_efectivo_de(TENANT, leg_esc) == "humano",
              "legado escalado (version 0, control 'ia' por default): control efectivo HUMANO")
    comprobar(db.control_efectivo_de(TENANT, leg_agenda) == "ia",
              "legado agendado solo (no necesita persona): control efectivo ia")
    comprobar(db.control_efectivo_de(TENANT, nueva_conv(org, "573000000018")) == "ia",
              "conversacion nueva sin escalar: ia")
    comprobar(db.control_efectivo_de(TENANT, c) == "ia" and db.control_efectivo_de(TENANT, c3) == "humano",
              "gobernadas: manda la columna control (devuelta = ia, escalada = humano)")
    comprobar(db.control_efectivo_de(TENANT, str(uuid.uuid4())) is None, "inexistente: None")

    # -----------------------------------------------------------------------
    print("\n== 2. legado (version 0) ==")
    leg = str(q("""insert into asistente.conversations
                     (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana)
                   values (%s, 'whatsapp', '573000000020', true, true) returning id""", (org,))[0][0])
    rt = T.tomar(TENANT, leg, operador_id=ANA[0], operador_nombre=ANA[1])
    e = estado(leg)
    comprobar(not rt.gobernada and e[7] == "Ana Perez" and e[0] == "ia" and e[2] is None and e[3] == 0,
              f"tomar en legado: solo tomada_por, control y version intactos ({e})")
    T.soltar(TENANT, leg, operador_id=ANA[0], operador_nombre=ANA[1])
    comprobar(estado(leg)[7] is None, "soltar en legado: solo tomada_por")
    T.devolver_a_ia(TENANT, leg, operador_id=ANA[0], operador_nombre=ANA[1])
    e = estado(leg)
    comprobar(e[5] is False and e[6] is False and e[3] == 0, "devolver en legado: solo las banderas")
    T.resolver(TENANT, leg, operador_id=ANA[0], operador_nombre=ANA[1])
    e = estado(leg)
    comprobar(e[4] == "cerrada" and e[8] is True and e[3] == 0, "resolver en legado: como siempre")
    comprobar(eventos(leg) == [], "el legado no genera ningun evento")

    # -----------------------------------------------------------------------
    print("\n== 3. idempotencia ==")
    c6 = nueva_conv(org, "573000000030")
    T.escalar(TENANT, c6)
    a = T.tomar(TENANT, c6, operador_id=ANA[0], operador_nombre=ANA[1], clave="op-1")
    b = T.tomar(TENANT, c6, operador_id=LUIS[0], operador_nombre=LUIS[1], clave="op-1")
    comprobar(a.aplicada and not b.aplicada and b.motivo == "reintento" and b.version == a.version
              and estado(c6)[2] == "Ana Perez" and len(eventos(c6)) == 2,
              "misma clave dos veces: un cambio, un evento, la version del primero")
    c7 = nueva_conv(org, "573000000031")
    T.escalar(TENANT, c7)
    resultados = []
    barrera = threading.Barrier(2)

    def en_paralelo():
        barrera.wait()
        resultados.append(T.soltar(TENANT, c7, operador_id=ANA[0], operador_nombre=ANA[1], clave="op-par")
                          if False else T.tomar(TENANT, c7, operador_id=ANA[0], operador_nombre=ANA[1], clave="op-par"))
    hilos = [threading.Thread(target=en_paralelo) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    comprobar(sum(1 for x in resultados if x.aplicada) == 1 and estado(c7)[3] == 2
              and [x[0] for x in eventos(c7)].count("tomada") == 1,
              f"dos hilos con la misma clave a la vez: un cambio, una version, un evento "
              f"({[(x.aplicada, x.motivo) for x in resultados]})")

    # -----------------------------------------------------------------------
    print("\n== 4. rollback ==")
    c8 = nueva_conv(org, "573000000040")
    T.escalar(TENANT, c8)
    antes, ev_antes = estado(c8), eventos(c8)
    real_validar = T.validar_datos
    T.validar_datos = lambda tipo, datos: (_ for _ in ()).throw(ValueError("evento roto a proposito"))
    try:
        T.tomar(TENANT, c8, operador_id=ANA[0], operador_nombre=ANA[1])
        comprobar(False, "deberia fallar")
    except ValueError:
        pass
    finally:
        T.validar_datos = real_validar
    comprobar(estado(c8) == antes and eventos(c8) == ev_antes,
              "el evento falla DESPUES del UPDATE: ni asignacion, ni legado, ni version")
    T._gancho_antes_del_commit = lambda: (_ for _ in ()).throw(RuntimeError("falla antes del commit"))
    try:
        T.devolver_a_ia(TENANT, c8, operador_id=ANA[0], operador_nombre=ANA[1])
        comprobar(False, "deberia fallar")
    except RuntimeError:
        pass
    finally:
        T._gancho_antes_del_commit = None
    comprobar(estado(c8) == antes and eventos(c8) == ev_antes,
              "falla despues de estado + legado + evento y antes del commit: no queda nada")

    # -----------------------------------------------------------------------
    print("\n== 5. la escalada en un turno real ==")
    from nucleo.canales import api                                  # noqa: E402
    from nucleo.config import cargar_config                         # noqa: E402
    CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
    TEL = "573000000099"
    abiertas = threading.local()
    real_sesion = db.sesion

    @contextmanager
    def sesion_vigilada(tenant):
        abiertas.n = getattr(abiertas, "n", 0) + 1
        try:
            with real_sesion(tenant) as par:
                yield par
        finally:
            abiertas.n -= 1

    vistos = []

    def externo(nombre, devuelve):
        def f(*a, **k):
            conv_id = q("select id::text from asistente.conversations where usuario_externo = %s", (TEL,))
            ctrl = estado(conv_id[0][0])[0] if conv_id else None
            vistos.append((nombre, getattr(abiertas, "n", 0), ctrl))
            return devuelve
        return f

    reemplazos = {
        (db, "sesion"): sesion_vigilada,
        (api.motor, "responder"): lambda config, rol, mensaje, historial, sesion, nota_continuidad=None: (
            historial.append({"role": "assistant", "content": "Te paso con alguien del equipo."}),
            ("Te paso con alguien del equipo.", [], []))[1],
        (api.escalamiento, "evaluar"): lambda *a, **k: {"escalar": True, "necesita_humano": True,
                                                        "motivo": "informacion_a_confirmar", "etiqueta": "",
                                                        "resumen": "cobertura de un barrio sin catalogo"},
        (api.escalamiento, "escalar"): externo("crm", False),          # el CRM falla
        (api.agendamiento, "agendar"): externo("ticket", None),
        (api.agendamiento, "ticket_para_escalar"): lambda *a, **k: None,
        # Guarda real que pospone una escalada si el asistente no uso ninguna
        # herramienta todavia: no es lo que se mide aca.
        (api, "con_las_manos_vacias"): lambda *a, **k: False,
        (api.agendamiento, "perfil_del_area"): lambda *a, **k: "",
        (api, "_cerrar_el_traspaso"): lambda config, tenant, conversation_id, mensaje_id, respuesta, id_sesion, **k: respuesta,
        (api.consumo, "estado_del_gasto"): lambda *a, **k: {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0},
    }
    originales = {k: getattr(*k) for k in reemplazos}
    for (m, n), f in reemplazos.items():
        setattr(m, n, f)
    llamadas_modelo = []
    responder_real_stub = reemplazos[(api.motor, "responder")]

    def responder_contado(*a, **k):
        llamadas_modelo.append(1)
        return responder_real_stub(*a, **k)
    reemplazos[(api.motor, "responder")] = responder_contado
    setattr(api.motor, "responder", responder_contado)
    api._sesiones.clear()
    salida_turno = {}
    try:
        # 'informacion_a_confirmar' y no el motivo de "pide una persona": ese
        # tiene su propia guarda (se descarta si el cliente no lo pidio con
        # palabras), que no es lo que se mide aca.
        salida_turno = api.atender_turno(CONFIG, TENANT, "cliente_final", TEL,
                                         "hay cobertura en el barrio Los Almendros?", "whatsapp-simulado")
        memoria_pausada = api._sesiones[(TENANT, "whatsapp-simulado", TEL)]["escalada"]
        modelo_antes = len(llamadas_modelo)
        segunda = api.atender_turno(CONFIG, TENANT, "cliente_final", TEL, "hola? sigue ahi?",
                                    "whatsapp-simulado")
        # Mismo proceso reiniciado: la sesion se reconstruye desde la base.
        api._sesiones.clear()
        tercera = api.atender_turno(CONFIG, TENANT, "cliente_final", TEL, "alguien me atiende?",
                                    "whatsapp-simulado")
    except Exception as ex:                                          # noqa: BLE001
        comprobar(False, "el turno de escalada corre", f"{type(ex).__name__}: {ex}")
    finally:
        for (m, n), f in originales.items():
            setattr(m, n, f)
        api._sesiones.clear()
    crm = [v for v in vistos if v[0] == "crm"]
    comprobar(bool(crm) and crm[0][2] == "humano",
              f"cuando se llama al CRM, el control YA es humano en la base ({vistos})")
    comprobar(bool(vistos) and all(v[1] == 0 for v in vistos),
              f"ningun efecto externo corre con una transaccion abierta ({vistos})")
    conv_turno = q("select id::text from asistente.conversations where usuario_externo = %s", (TEL,))[0][0]
    e = estado(conv_turno)
    comprobar(e[0] == "humano" and e[5] is True and e[6] is True
              and [x[0] for x in eventos(conv_turno)] == ["escalada"],
              f"el CRM fallo: control humano Y legado pausado en la base; un solo evento ({e})")
    comprobar(memoria_pausada is True, "y la memoria del proceso tambien quedo en pausa (sin split-brain)")
    texto = (salida_turno or {}).get("respuesta") or ""
    comprobar("confirmar con un compañero" in texto and "de nuevo" not in texto.lower(),
              f"al cliente: el anuncio de atencion humana, NO 'escribime de nuevo' ({texto!r})")
    comprobar(len(llamadas_modelo) == modelo_antes and segunda.get("pausada") and tercera.get("pausada"),
              f"el mensaje siguiente, y despues de reconstruir la sesion, NO llega a la IA "
              f"(modelo llamado {len(llamadas_modelo) - modelo_antes} veces)")

    print("\n== 6. caso cerrado en el CRM durante la pausa ==")
    for tel, gobernada in (("573000000097", True), ("573000000096", False)):
        if gobernada:
            cid = nueva_conv(org, tel)
            T.escalar(TENANT, cid)
        else:
            cid = str(q("""insert into asistente.conversations
                             (organization_id, canal, usuario_externo, escalada_a_humano,
                              necesita_atencion_humana, caso_id)
                           values (%s, 'whatsapp-simulado', %s, true, true, gen_random_uuid()) returning id""",
                        (org, tel))[0][0])
        q("update asistente.conversations set caso_id = gen_random_uuid() where id = %s", (cid,))
        llamadas_modelo.clear()
        extra = dict(reemplazos)
        extra[(api.escalamiento, "caso_sigue_abierto")] = lambda *a, **k: False   # el CRM dice: cerrado
        extra[(api.escalamiento, "evaluar")] = lambda *a, **k: {}
        orig2 = {k: getattr(*k) for k in extra}
        for (m, n), f in extra.items():
            setattr(m, n, f)
        api._sesiones.clear()
        try:
            r6 = api.atender_turno(CONFIG, TENANT, "cliente_final", tel, "ya me resolvieron?", "whatsapp-simulado")
        finally:
            for (m, n), f in orig2.items():
                setattr(m, n, f)
            api._sesiones.clear()
        if gobernada:
            e = estado(cid)
            comprobar(r6.get("pausada") and not llamadas_modelo and e[0] == "humano"
                      and e[9] == "caso_externo_cerrado",
                      f"gobernada: el cierre externo deja aviso y la IA NO retoma ({e}, modelo={len(llamadas_modelo)})")
        else:
            comprobar(not r6.get("pausada") and llamadas_modelo,
                      "legado (version 0): se retoma como hasta hoy, hasta la reconciliacion de G8")

    # -----------------------------------------------------------------------
    print("\n== 7. B3.3: la guarda de control con la base real ==")
    envios = []
    orig_texto = api.whatsapp.enviar_texto
    api.whatsapp.enviar_texto = lambda *a, **k: envios.append(1) or "wamid.G"
    token = api._TOKEN_SERVICIO
    api._TOKEN_SERVICIO = None
    cliente = api.app.test_client()

    def responder(conv):
        antes = q("select count(*) from asistente.messages where conversation_id = %s", (conv,))[0][0]
        r = cliente.post(f"/conversaciones/{conv}/mensajes",
                         json={"tenant": TENANT, "mensaje": "hola, soy Ana", "autor": ANA[1],
                               "autor_usuario_id": ANA[0]})
        despues = q("select count(*) from asistente.messages where conversation_id = %s", (conv,))[0][0]
        return r.status_code, despues - antes
    try:
        agendada = str(q("""insert into asistente.conversations
                              (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana)
                            values (%s, 'whatsapp', '573000000070', true, false) returning id""", (org,))[0][0])
        comprobar(responder(agendada) == (409, 0) and not envios,
                  "legado agendado solo (la IA sigue atendiendo): 409, cero filas, cero envios a Meta")
        leg_h = str(q("""insert into asistente.conversations
                           (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana)
                         values (%s, 'whatsapp-simulado', '573000000071', true, true) returning id""", (org,))[0][0])
        comprobar(responder(leg_h) == (201, 1),
                  "legado escalado con control 'ia' por default: NO se bloquea (control efectivo humano)")
        gob = nueva_conv(org, "573000000072")
        T.escalar(TENANT, gob)
        comprobar(responder(gob) == (201, 1), "gobernada escalada: la persona responde")
        T.devolver_a_ia(TENANT, gob, operador_id=ANA[0], operador_nombre=ANA[1])
        comprobar(responder(gob) == (409, 0), "devuelta a la IA: 409, cero filas")
        T.intervenir(TENANT, gob, operador_id=ANA[0], operador_nombre=ANA[1])
        comprobar(responder(gob) == (201, 1), "despues de intervenir: la persona responde")
        nota = cliente.post(f"/conversaciones/{agendada}/nota",
                            json={"tenant": TENANT, "mensaje": "revisar", "autor": ANA[1], "autor_usuario_id": ANA[0]})
        comprobar(nota.status_code == 201, "la nota interna no se bloquea con la IA atendiendo")
    finally:
        api.whatsapp.enviar_texto = orig_texto
        api._TOKEN_SERVICIO = token
finally:
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname = %s and pid <> pg_backend_pid()", (BASE,))
            con.execute(f'drop database if exists "{BASE}"')
        print(f"\n       -> {BASE} borrada")
    except Exception as ex:
        print(f"\n  [aviso] no se pudo borrar {BASE}: {type(ex).__name__}: {ex}")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] Cada transicion escribe estado, legado y evento juntos, o nada.")
