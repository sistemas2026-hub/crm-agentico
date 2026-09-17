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
  9. D24, IA en vuelo contra Intervenir, por el camino real de WhatsApp: el
     modelo queda frenado, una persona interviene y hace commit, el modelo
     termina -> cero POST a Meta, cero respuesta de la IA guardada, nada en
     memoria. Y la intervencion entre la respuesta guardada y el POST: no se
     envia y la fila queda 'descartado', fuera del historial.
 10. Una clave de operacion ya usada por otro operador no le devuelve exito.
 11. D25, con el motor.responder REAL y el modelo guionado: el modelo queda
     frenado, una persona interviene, el modelo pide una herramienta que
     escribe -> cero llamadas al proveedor (control positivo: sin
     intervencion, una). Y el cierre por confirmacion no empieza si alguien
     intervino mientras corria el evaluador. La escalada PROPIA sigue
     sincronizando con el CRM (seccion 5).
  8. B3.3b en turnos reales: tras /intervenir el cliente escribe y el modelo NO
     corre, sin acuse de escalada ni banderas ni tasa; devolver reanuda; la
     memoria nunca decide contra la base (en las dos direcciones); reintento
     de la misma clave; dos operadores a la vez (uno gana, el otro 409); legado
     escalado no se puede intervenir.
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
    b = T.tomar(TENANT, c6, operador_id=ANA[0], operador_nombre=ANA[1], clave="op-1")
    comprobar(a.aplicada and not b.aplicada and b.motivo == "reintento" and b.version == a.version
              and estado(c6)[2] == "Ana Perez" and len(eventos(c6)) == 2,
              "misma clave dos veces: un cambio, un evento, la version del primero")
    b2 = T.tomar(TENANT, c6, operador_id=LUIS[0], operador_nombre=LUIS[1], clave="op-1")
    comprobar(not b2.aplicada and b2.motivo == "clave_ajena" and b2.evento_id is None
              and estado(c6)[2] == "Ana Perez" and len(eventos(c6)) == 2,
              f"la misma clave desde OTRO operador: clave_ajena, no un reintento a su nombre ({b2.motivo})")
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
        autorizado_propio = api._turno_sigue_autorizado(
            TENANT, "whatsapp-simulado", TEL, salida_turno.get("_autorizacion") or {}, exigir_ia=False)
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
    comprobar(autorizado_propio is True,
              "D24: la escalada que hizo ESTE turno no le frena su propio aviso al cliente")
    comprobar(bool(crm),
              "D25: la sincronizacion de la escalada PROPIA (el caso del CRM) corre aunque el control ya sea humano")
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

    # -----------------------------------------------------------------------
    print("\n== 8. B3.3b: intervenir, y la compuerta lee la base ==")
    modelo8 = []

    def responder8(config, rol, mensaje, historial, sesion, nota_continuidad=None):
        modelo8.append(mensaje)
        historial.append({"role": "assistant", "content": "respuesta de la IA"})
        return "respuesta de la IA", [], []
    base8 = {
        (api.motor, "responder"): responder8,
        (api.escalamiento, "evaluar"): lambda *a, **k: {},
        (api.escalamiento, "caso_sigue_abierto"): lambda *a, **k: True,
        (api, "_cerrar_el_traspaso"): lambda config, tenant, conversation_id, mensaje_id, respuesta, id_sesion, **k: respuesta,
        (api.consumo, "estado_del_gasto"): lambda *a, **k: {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0},
    }
    orig8 = {k: getattr(*k) for k in base8}
    for (m, n), f in base8.items():
        setattr(m, n, f)
    token8 = api._TOKEN_SERVICIO
    api._TOKEN_SERVICIO = None

    def turno(tel, texto):
        return api.atender_turno(CONFIG, TENANT, "cliente_final", tel, texto, "whatsapp-simulado")

    def conv_de(tel):
        return q("select id::text from asistente.conversations where usuario_externo = %s and estado = 'abierta'",
                 (tel,))[0][0]

    def intervenir_http(conv, operador, clave):
        return api.app.test_client().post(f"/conversaciones/{conv}/intervenir", json={
            "tenant": TENANT, "autor": operador[1], "autor_usuario_id": operador[0], "clave_operacion": clave})

    def escaladas():
        return db.tasa_escalamiento(TENANT, 30)
    try:
        api._sesiones.clear()
        tel = "573000000080"
        turno(tel, "hola, tengo una duda")
        cv = conv_de(tel)
        comprobar(len(modelo8) == 1, "turno normal: la IA responde")
        antes_tasa = escaladas()
        r = intervenir_http(cv, ANA, "int-ana")
        e = estado(cv)
        comprobar(r.status_code == 200 and e[:3] == ("humano", "intervencion", "Ana Perez"),
                  f"Ana interviene: 200, humano/intervencion, asignada a Ana ({r.status_code} {e[:3]})")
        comprobar(e[5] is False and e[6] is False,
                  "intervenir NO toca las banderas de escalada")
        salida = turno(tel, "hola? alguien?")
        comprobar(len(modelo8) == 1 and salida.get("respuesta") == "" and salida.get("pausada"),
                  f"mensaje del cliente con la conversacion intervenida: la IA NO corre y no hay acuse ({salida})")
        ult = q("""select rol, origen, contenido from asistente.messages where conversation_id = %s
                   order by creado_en desc limit 1""", (cv,))[0]
        comprobar(ult == ("user", "cliente", "hola? alguien?"), f"el mensaje del cliente queda guardado ({ult})")
        comprobar(escaladas() == antes_tasa, "la tasa de escalamiento no cambia: intervenir no es escalar")
        r_b = intervenir_http(cv, LUIS, "int-luis")
        comprobar(r_b.status_code == 409 and estado(cv)[2] == "Ana Perez",
                  f"Luis intenta intervenir despues: 409 y NO le roba la conversacion a Ana ({r_b.status_code})")
        v = estado(cv)[3]
        r_re = intervenir_http(cv, ANA, "int-ana")
        comprobar(r_re.status_code == 200 and r_re.get_json().get("reintento") and estado(cv)[3] == v
                  and [x[0] for x in eventos(cv)].count("intervencion") == 1,
                  "el mismo clic reintentado: 200 reintento, sin otra version ni otro evento")
        resp = api.app.test_client().post(f"/conversaciones/{cv}/mensajes", json={
            "tenant": TENANT, "mensaje": "Soy Ana, te ayudo yo", "autor": ANA[1], "autor_usuario_id": ANA[0]})
        comprobar(resp.status_code == 201, f"Ana responde: 201 ({resp.status_code})")
        T.devolver_a_ia(TENANT, cv, operador_id=ANA[0], operador_nombre=ANA[1])
        turno(tel, "gracias, otra pregunta")
        comprobar(len(modelo8) == 2, "devuelta a la IA: el siguiente mensaje vuelve a la IA")

        # La memoria no decide.
        api._sesiones[(TENANT, "whatsapp-simulado", tel)]["escalada"] = True
        turno(tel, "y otra cosa")
        comprobar(len(modelo8) == 3, "memoria dice pausa y la base dice IA: la IA responde (manda la base)")
        tel2 = "573000000081"
        turno(tel2, "hola")
        cv2 = conv_de(tel2)
        T.escalar(TENANT, cv2)                 # "otro proceso" escala; esta memoria no se entero
        n = len(modelo8)
        salida2 = turno(tel2, "sigo esperando")
        comprobar(len(modelo8) == n and salida2.get("pausada"),
                  "memoria sin pausa y la base dice humano (escalada en otro lado): la IA NO corre")

        # Dos operadores a la vez, con claves distintas.
        tel3 = "573000000082"
        turno(tel3, "hola")
        cv3 = conv_de(tel3)
        resultados = []
        barrera = threading.Barrier(2)

        def carrera(op, clave):
            barrera.wait()
            resultados.append((op[1], intervenir_http(cv3, op, clave).status_code))
        hilos = [threading.Thread(target=carrera, args=(ANA, "c-ana")),
                 threading.Thread(target=carrera, args=(LUIS, "c-luis"))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        codigos = sorted(c for _, c in resultados)
        ganador = [op for op, c in resultados if c == 200]
        comprobar(codigos == [200, 409] and ganador and estado(cv3)[2] == ganador[0]
                  and [x[0] for x in eventos(cv3)].count("intervencion") == 1,
                  f"dos operadores intervienen a la vez: uno gana, el otro 409, una sola intervencion ({resultados})")

        leg = str(q("""insert into asistente.conversations
                         (organization_id, canal, usuario_externo, escalada_a_humano, necesita_atencion_humana)
                       values (%s, 'whatsapp-simulado', '573000000083', true, true) returning id""", (org,))[0][0])
        r_leg = intervenir_http(leg, ANA, "int-leg")
        comprobar(r_leg.status_code == 409 and estado(leg)[3] == 0 and estado(leg)[0] == "ia",
                  "legado escalado (control efectivo humano): intervenir 409, no se le roba a la escalada")
    finally:
        for (m, n), f in orig8.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = token8
        api._sesiones.clear()

    # -----------------------------------------------------------------------
    print("\n== 9. D24: la IA en vuelo no sobrevive a una intervencion ==")
    posts = []
    empezo, liberar = threading.Event(), threading.Event()
    modo = {"frenar": False, "en_el_medio": None}

    def responder9(config, rol, mensaje, historial, sesion, nota_continuidad=None):
        historial.append({"role": "user", "content": mensaje})
        if modo["frenar"]:
            empezo.set()
            liberar.wait(60)
        historial.append({"role": "assistant", "content": "RESPUESTA-IA-D24"})
        return "RESPUESTA-IA-D24", [], []

    def adjunto9(config, tenant, entrante, conversacion_id, mensaje_id=None):
        if modo["en_el_medio"]:
            modo["en_el_medio"]()
    base9 = {
        (api.motor, "responder"): responder9,
        (api.escalamiento, "evaluar"): lambda *a, **k: {},
        (api.escalamiento, "caso_sigue_abierto"): lambda *a, **k: True,
        (api, "_cerrar_el_traspaso"): lambda config, tenant, conversation_id, mensaje_id, respuesta, id_sesion, **k: respuesta,
        (api.consumo, "estado_del_gasto"): lambda *a, **k: {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0},
        (api.whatsapp, "enviar_texto"): lambda config, tenant, para, texto: posts.append(texto) or "wamid.x",
        (api.whatsapp, "marcar_leido"): lambda *a, **k: None,
        (api, "_atendio_baja_o_alta"): lambda *a, **k: False,
        (api, "_guardar_adjunto"): adjunto9,
    }
    orig9 = {k: getattr(*k) for k in base9}
    for (m, n), f in base9.items():
        setattr(m, n, f)
    token9 = api._TOKEN_SERVICIO
    api._TOKEN_SERVICIO = None

    def whatsapp_turno(tel, texto):
        api._procesar_mensaje_whatsapp(CONFIG, TENANT, "cliente_final",
                                       {"de": tel, "telefono": tel, "texto": texto})

    def conv_wa(tel):
        return q("""select id::text from asistente.conversations
                    where usuario_externo = %s and canal = 'whatsapp' and estado = 'abierta'""", (tel,))[0][0]

    def filas_ia(conv):
        return q("""select contenido, estado_entrega from asistente.messages
                    where conversation_id = %s and rol = 'assistant' and origen = 'ia'
                    order by creado_en""", (conv,))
    try:
        api._sesiones.clear()
        tel = "573000000090"
        whatsapp_turno(tel, "hola")
        cv = conv_wa(tel)
        comprobar(posts == ["RESPUESTA-IA-D24"], f"turno sin intervencion: sale un POST ({len(posts)})")
        posts.clear()
        ia_antes = len(filas_ia(cv))
        v_antes = estado(cv)[3]
        descartes_antes = api.contadores_relevo["respuesta_ia_descartada_por_cambio_de_control"]

        # 9a. el modelo esta pensando cuando la persona interviene
        modo["frenar"] = True
        hilo = threading.Thread(target=whatsapp_turno, args=(tel, "me ayudas con la factura?"))
        hilo.start()
        comprobar(empezo.wait(30), "el modelo arranco (leyo control = ia)")
        r9 = intervenir_http(cv, ANA, "d24-ana")
        comprobar(r9.status_code == 200, f"la persona interviene mientras el modelo piensa: 200 ({r9.status_code})")
        liberar.set()
        hilo.join(60)
        modo["frenar"] = False
        e = estado(cv)
        comprobar(posts == [], f"cero POST a Meta con la respuesta calculada antes ({len(posts)})")
        comprobar(len(filas_ia(cv)) == ia_antes, "cero respuestas de la IA guardadas en ese turno")
        memoria = api._sesiones[(TENANT, "whatsapp", tel)]["historial"]
        comprobar(sum("RESPUESTA-IA-D24" in (m.get("content") or "") for m in memoria) == 1
                  and memoria[-1] == {"role": "user", "content": "me ayudas con la factura?"},
                  f"la memoria termina en el mensaje del cliente; solo queda la respuesta del turno "
                  f"anterior, que si salio ({memoria[-2:]})")
        ult = q("""select rol, origen, contenido from asistente.messages where conversation_id = %s
                   order by creado_en desc limit 1""", (cv,))[0]
        comprobar(ult == ("user", "cliente", "me ayudas con la factura?"),
                  f"el mensaje del cliente queda guardado para quien intervino ({ult})")
        comprobar(e[:3] == ("humano", "intervencion", "Ana Perez") and e[3] == v_antes + 1
                  and [x[0] for x in eventos(cv)].count("intervencion") == 1,
                  f"control humano, asignada a Ana, relevo_version +1, un evento ({e[:4]})")
        comprobar(api.contadores_relevo["respuesta_ia_descartada_por_cambio_de_control"] == descartes_antes + 1,
                  "queda contado como respuesta_ia_descartada_por_cambio_de_control")

        # 9b. la persona interviene despues de guardada la respuesta y antes del POST
        tel2 = "573000000091"
        whatsapp_turno(tel2, "hola")
        cv2 = conv_wa(tel2)
        posts.clear()
        modo["en_el_medio"] = lambda: intervenir_http(cv2, LUIS, "d24-luis")
        whatsapp_turno(tel2, "cuanto debo?")
        modo["en_el_medio"] = None
        filas = filas_ia(cv2)
        comprobar(posts == [], f"intervencion justo antes del envio: cero POST a Meta ({len(posts)})")
        comprobar(filas[-1] == ("RESPUESTA-IA-D24", "descartado"),
                  f"la respuesta guardada queda 'descartado' ({filas[-1]})")
        reconstruido = db.historial_para_el_modelo(TENANT, cv2)
        comprobar(sum("RESPUESTA-IA-D24" in (m.get("content") or "") for m in reconstruido) == 1,
                  "el historial reconstruido no la incluye (solo la del primer turno, que si salio)")
        memoria2 = api._sesiones[(TENANT, "whatsapp", tel2)]["historial"]
        comprobar(memoria2[-1] == {"role": "user", "content": "cuanto debo?"},
                  f"y sale de la memoria viva ({memoria2[-1]})")
        comprobar(estado(cv2)[:3] == ("humano", "intervencion", "Luis Rojas"), "control de Luis")

        # 10. la clave de otro operador
        tel3 = "573000000092"
        whatsapp_turno(tel3, "hola")
        cv3 = conv_wa(tel3)
        r_a = intervenir_http(cv3, ANA, "clave-compartida")
        r_b = intervenir_http(cv3, LUIS, "clave-compartida")
        comprobar(r_a.status_code == 200 and r_b.status_code == 409
                  and (r_b.get_json() or {}).get("codigo") == "clave_de_otra_operacion"
                  and estado(cv3)[2] == "Ana Perez",
                  f"== 10 == otro operador con la misma clave: 409, no aparece como quien intervino "
                  f"({r_a.status_code} {r_b.status_code})")
        r_tipo = T.devolver_a_ia(TENANT, cv3, operador_id=ANA[0], operador_nombre=ANA[1], clave="clave-compartida")
        comprobar(r_tipo.motivo == "clave_ajena" and estado(cv3)[0] == "humano",
                  f"la misma clave para OTRA operacion del mismo actor: clave_ajena, nada cambia ({r_tipo.motivo})")
    finally:
        liberar.set()
        for (m, n), f in orig9.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = token9
        api._sesiones.clear()

    # -----------------------------------------------------------------------
    print("\n== 11. D25: la IA no empieza efectos despues de una intervencion ==")
    from nucleo.modelo import cliente as cliente_modelo              # noqa: E402
    http11, posts11 = [], []
    empezo11, liberar11 = threading.Event(), threading.Event()
    guion = {"frenar": False, "herramienta": True, "al_evaluar": None, "veredicto": {}}
    ARGS = {"numero_documento": "1000000000", "nombre_confirmado": "CLIENTE DE PRUEBA",
            "motivo": "ya no la necesito"}

    def chat11(referencia_modelo, mensajes, tools=None, temperatura=0.1, timeout=None, **resto):
        # Pide la herramienta solo en la primera vuelta del turno (lo ultimo
        # es el mensaje del cliente); despues de ver su resultado, contesta.
        pide = tools is not None and guion["herramienta"] and mensajes[-1].get("role") == "user"
        if pide:
            if guion["frenar"]:
                empezo11.set()
                liberar11.wait(60)
            return cliente_modelo.Respuesta(contenido="", llamadas=[
                cliente_modelo.Llamada(nombre="cancelar_solicitud_servicio", argumentos=dict(ARGS))])
        return cliente_modelo.Respuesta(contenido="Listo.", llamadas=[])

    def http_11(herramienta, argumentos, tenant=None, *a, **k):
        http11.append(herramienta.nombre)
        return {"ok": True}

    def evaluar11(*a, **k):
        if guion["al_evaluar"]:
            guion["al_evaluar"]()
        return dict(guion["veredicto"])
    base11 = {
        (api.motor.cliente, "chat"): chat11,
        (api.motor.ejecutor_http, "ejecutar"): http_11,
        (api.motor.catalogo_habilidades, "indice_de"): lambda *a, **k: [],
        (api.escalamiento, "evaluar"): evaluar11,
        (api.escalamiento, "caso_sigue_abierto"): lambda *a, **k: True,
        (api.consumo, "estado_del_gasto"): lambda *a, **k: {"accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0},
        (api.whatsapp, "enviar_texto"): lambda config, tenant, para, texto: posts11.append(texto) or "wamid.y",
        (api.whatsapp, "marcar_leido"): lambda *a, **k: None,
        (api, "_atendio_baja_o_alta"): lambda *a, **k: False,
        (api, "_guardar_adjunto"): lambda *a, **k: None,
    }
    orig11 = {k: getattr(*k) for k in base11}
    for (m, n), f in base11.items():
        setattr(m, n, f)
    token11 = api._TOKEN_SERVICIO
    api._TOKEN_SERVICIO = None

    def turno11(tel, texto):
        api._procesar_mensaje_whatsapp(CONFIG, TENANT, "ventas", {"de": tel, "telefono": tel, "texto": texto})
    try:
        api._sesiones.clear()
        # control positivo: sin intervencion la escritura SI sale
        tel = "573000000110"
        guion["herramienta"] = False
        turno11(tel, "hola")
        cv = conv_wa(tel)
        guion["herramienta"] = True
        turno11(tel, "quiero cancelar mi solicitud")
        comprobar(http11.count("cancelar_solicitud_servicio") == 1,
                  f"control positivo: sin intervencion, la herramienta que escribe SI llega al proveedor ({http11})")

        # 11a. la carrera
        http11.clear()
        posts11.clear()
        v_antes = estado(cv)[3]
        canceladas = api.contadores_relevo["accion_ia_cancelada_por_cambio_de_control"]
        guion["frenar"] = True
        hilo = threading.Thread(target=turno11, args=(tel, "cancelala otra vez por favor"))
        hilo.start()
        comprobar(empezo11.wait(60), "el modelo arranco con control = ia y quedo frenado")
        r11 = intervenir_http(cv, ANA, "d25-ana")
        comprobar(r11.status_code == 200, f"una persona interviene y hace commit ({r11.status_code})")
        liberar11.set()
        hilo.join(90)
        guion["frenar"] = False
        comprobar(http11.count("cancelar_solicitud_servicio") == 0,
                  f"el modelo pidio la escritura DESPUES del commit: cero llamadas al proveedor ({http11})")
        comprobar(posts11 == [], "y cero POST a Meta")
        e = estado(cv)
        comprobar(e[:3] == ("humano", "intervencion", "Ana Perez") and e[3] == v_antes + 1
                  and [x[0] for x in eventos(cv)].count("intervencion") == 1,
                  f"control humano, asignada a Ana, version +1, un evento ({e[:4]})")
        comprobar(api.contadores_relevo["accion_ia_cancelada_por_cambio_de_control"] == canceladas + 1,
                  "queda contado como accion_ia_cancelada_por_cambio_de_control")

        # 11b. el cierre por confirmacion no empieza si alguien intervino mientras evaluaba
        tel2 = "573000000111"
        guion["herramienta"] = False
        turno11(tel2, "hola")
        cv2 = conv_wa(tel2)
        guion["veredicto"] = {"resuelta": True, "confirma_cierre": True}
        guion["al_evaluar"] = lambda: intervenir_http(cv2, LUIS, "d25-luis")
        turno11(tel2, "listo, ya quedo, gracias")
        guion["al_evaluar"], guion["veredicto"] = None, {}
        e2 = estado(cv2)
        comprobar(e2[4] == "abierta" and e2[:3] == ("humano", "intervencion", "Luis Rojas"),
                  f"intervencion durante el evaluador: la conversacion NO se cierra sola ({e2[:5]})")

        # 11c. la escalada que ya NO es de este turno no sincroniza nada
        import types                                                  # noqa: E402
        externos = []
        base11c = {
            (api.agendamiento, "ticket_para_escalar"): lambda *a, **k: types.SimpleNamespace(
                herramienta="crear_ticket_caso", area="soporte", asunto="Revision", prioridad="media"),
            (api.agendamiento, "agendar"): lambda *a, **k: externos.append("ticket") or "T-1",
            (api.escalamiento, "escalar"): lambda *a, **k: externos.append("crm") or True,
            (api.agendamiento, "perfil_del_area"): lambda *a, **k: "",
            (api, "con_las_manos_vacias"): lambda *a, **k: False,
            (api, "_cerrar_el_traspaso"): lambda config, tenant, conversation_id, mensaje_id, respuesta, id_sesion, **k: respuesta,
        }
        orig11c = {k: getattr(*k) for k in base11c}
        for (m, n), f in base11c.items():
            setattr(m, n, f)
        try:
            tel3 = "573000000112"
            turno11(tel3, "hola")
            cv3 = conv_wa(tel3)
            veredicto_escala = {"escalar": True, "necesita_humano": True, "motivo": "informacion_a_confirmar",
                                "etiqueta": "", "caso_manual": "caso_de_prueba_d25", "resumen": "cobertura sin catalogo"}
            # control positivo: sin intervencion, la escalada propia SI crea ticket y caso
            guion["veredicto"] = veredicto_escala
            turno11(tel3, "hay cobertura en Los Almendros?")
            comprobar(externos == ["ticket", "crm"],
                      f"control positivo: la escalada propia crea ticket y caso con control humano ({externos})")
            externos.clear()
            tel4 = "573000000113"
            guion["veredicto"] = {}
            turno11(tel4, "hola")
            cv4 = conv_wa(tel4)
            guion["veredicto"] = veredicto_escala
            guion["al_evaluar"] = lambda: intervenir_http(cv4, ANA, "d25-ana-esc")
            turno11(tel4, "hay cobertura en Los Almendros?")
            e4 = estado(cv4)
            comprobar(externos == [] and e4[:3] == ("humano", "intervencion", "Ana Perez")
                      and "escalada" not in [x[0] for x in eventos(cv4)],
                      f"intervencion antes de reservar: la escalada no es de este turno, ni ticket ni caso ({externos}, {e4[:3]})")
        finally:
            guion["al_evaluar"], guion["veredicto"] = None, {}
            for (m, n), f in orig11c.items():
                setattr(m, n, f)
    finally:
        liberar11.set()
        for (m, n), f in orig11.items():
            setattr(m, n, f)
        api._TOKEN_SERVICIO = token11
        api._sesiones.clear()
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
