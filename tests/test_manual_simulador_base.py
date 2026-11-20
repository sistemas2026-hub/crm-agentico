# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE EL EQUIPO MARCA PARA ENSEÑARLE A DEXTER, CONTRA POSTGRES REAL
================================================================================

    DBHOST=... DBPORT=... DBUSER=... DBPASSWORD=... \\
        py -3.13 tests/test_manual_simulador_base.py

Construye una base efimera desde cero (cli/base_desde_cero.py, el mismo ledger
que produccion), siembra una organizacion y corre el codigo de verdad con el
rol degradado y la RLS. Sin las variables se saltea con exit 0 -- y eso ya
escondio regresiones: correrla con base.

POR QUE EXISTE  (12/11/2026)
----------------------------
La auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md, grupo «Dexter»)
encontro que lo que el equipo marca para enseñar no llegaba a ningun lado, y
que el analista de habilidades contaba el simulador como evidencia real. Lo
que se fija aca:

  1. EL ANALISTA SOLO CUENTA CANALES REALES: cinco pruebas en el simulador no
     hacen un hueco de la operacion, y sus muestras van REDACTADAS al modelo.
  2. LOS USOS DE UNA HABILIDAD SE PUEDEN LEER: por la ruta del motor, con
     «escalo igual» y lo real separado de lo simulado.
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
sys.path.insert(0, str(RAIZ / "tests"))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
BASE = "manual_" + uuid.uuid4().hex[:6]
TENANT = "empresa_manual"

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def dsn(base: str) -> str:
    return (f"host={HOST} port={PUERTO} dbname={base} user={USUARIO} password={CLAVE} "
            f"sslmode=disable connect_timeout=15")


from base_local import exigir_base_local                           # noqa: E402
exigir_base_local(__file__)


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


print("=" * 74)
print(" LO QUE SE MARCA PARA ENSEÑAR, CONTRA POSTGRES REAL")
print("=" * 74)

ORG = str(uuid.uuid4())


def conv(canal="whatsapp", tel=None, rol="soporte_x", escalada=False,
         motivo=None, hace_min=60):
    return str(q("""insert into asistente.conversations
                      (organization_id, canal, usuario_externo, rol_efectivo,
                       escalada_a_humano, motivo_escalamiento, creado_en)
                    values (%s, %s, %s, %s, %s, %s, now() - make_interval(mins => %s))
                    returning id""",
                 (ORG, canal, tel or ("57" + uuid.uuid4().hex[:8]), rol,
                  escalada, motivo, hace_min))[0][0])


def msj(c, contenido, rol="user", hace_min=0, segs=0):
    origen = {"user": "cliente", "assistant": "ia"}.get(rol)
    return str(q("""insert into asistente.messages
                      (organization_id, conversation_id, rol, contenido, origen, creado_en)
                    values (%s, %s, %s, %s, %s,
                            now() - make_interval(mins => %s) + make_interval(secs => %s))
                    returning id""",
                 (ORG, c, rol, contenido, origen, hace_min, segs))[0][0])


def parte_analista() -> None:
    from nucleo.habilidades import analista

    print("\n-- 1. el analista solo cuenta canales reales --")
    # Motivo A: 2 reales + 5 simuladas. Con el simulador contaba 7 y pasaba
    # el piso de 3; sin el, son 2 y no hay patron.
    for _ in range(2):
        c = conv("whatsapp", escalada=True, motivo="motivo_a")
        msj(c, "necesito cambiar el plan de mi servicio por favor", hace_min=59)
    for _ in range(5):
        c = conv("whatsapp-simulado", escalada=True, motivo="motivo_a")
        msj(c, "prueba del equipo ensayando el mismo caso", hace_min=59)
    # Motivo B: 3 reales -> patron, con UNA muestra que trae PII.
    ids_b = []
    for i in range(3):
        c = conv("whatsapp", escalada=True, motivo="motivo_b")
        ids_b.append(c)
        msj(c, ("mi cedula es 1098765432 y mi correo ana.perez@correo.com, "
                "no me llega la factura") if i == 0 else
            "no me llega la factura al correo desde hace meses", hace_min=59)
    for _ in range(2):
        conv("api", escalada=True, motivo="motivo_b")
    # Senal 2: el agente dijo no tener el procedimiento, SOLO en el simulador.
    for _ in range(4):
        c = conv("whatsapp-simulado", rol="ventas_x")
        msj(c, "Lo siento, no tengo el procedimiento para eso", rol="assistant", hace_min=58)
    # Senal 3: habilidad cargada y escalo igual, SOLO en el simulador.
    hab = str(q("""insert into asistente.habilidades
                     (organization_id, codigo, nombre, cuando_usarla, pasos,
                      roles_permitidos, estado)
                   values (%s, 'HAB-PRUEBA', 'Prueba', 'x', '1. x', %s, 'vigente')
                   returning id""", (ORG, ["otro_rol"]))[0][0])
    for _ in range(4):
        c = conv("whatsapp-simulado", escalada=True, motivo="motivo_c")
        q("""insert into asistente.habilidad_usos (organization_id, habilidad_id,
               conversation_id, rol) values (%s, %s, %s, 'soporte_x')""", (ORG, hab, c))

    patrones = analista.detectar(TENANT, dias=30, minimo=3)
    por_motivo = {p.motivo: p for p in patrones}
    comprobar("motivo_a" not in por_motivo,
              "EL EFECTO: 2 reales + 5 simuladas no son un hueco",
              str([(p.senal, p.motivo, p.n_casos) for p in patrones]))
    comprobar("motivo_b" in por_motivo and por_motivo["motivo_b"].n_casos == 3,
              "3 reales SI son un hueco, y cuenta 3 (no suma las del asistente interno)",
              str([(p.senal, p.motivo, p.n_casos) for p in patrones]))
    comprobar(not any(p.senal == "sin_procedimiento" for p in patrones),
              "«no tengo el procedimiento» dicho en el simulador no cuenta")
    comprobar(not any(p.senal == "habilidad_insuficiente" for p in patrones),
              "una habilidad cargada en el simulador que escalo no cuenta")
    if "motivo_b" in por_motivo:
        muestras = " | ".join(por_motivo["motivo_b"].muestras)
        comprobar("1098765432" not in muestras and "ana.perez@correo.com" not in muestras,
                  "las muestras que van al modelo salen sin cedula ni correo", muestras)
        comprobar("no me llega la factura" in muestras,
                  "y conservan lo que el cliente vino a pedir", muestras)
    comprobar("dato personal" in analista.PROMPT_REDACCION,
              "el prompt le pide no copiar datos personales a los pasos")


def parte_usos(http) -> None:
    print("\n-- 2. los usos de una habilidad, por la ruta --")
    hab = str(q("""insert into asistente.habilidades
                     (organization_id, codigo, nombre, cuando_usarla, pasos,
                      roles_permitidos, estado)
                   values (%s, 'HAB-USOS', 'Usos', 'x', '1. x', %s, 'vigente')
                   returning id""", (ORG, ["soporte_x"]))[0][0])
    escalo = conv("whatsapp", escalada=True, motivo="m")
    resolvio = conv("whatsapp")
    simulada = conv("whatsapp-simulado", escalada=True, motivo="m")
    for c in (escalo, resolvio, simulada):
        q("""insert into asistente.habilidad_usos (organization_id, habilidad_id,
               conversation_id, rol) values (%s, %s, %s, 'soporte_x')""", (ORG, hab, c))
    r = http.get(f"/habilidades/{hab}/usos?tenant={TENANT}")
    cuerpo = r.get_json() or {}
    comprobar(r.status_code == 200 and cuerpo.get("usos") == 3
              and cuerpo.get("usos_reales") == 2 and cuerpo.get("escalo_igual_reales") == 1,
              "3 usos, 2 con clientes, 1 escalo igual (la simulada no cuenta como real)",
              str(cuerpo))
    det = {d["conversation_id"]: d for d in cuerpo.get("detalle", [])}
    comprobar(det.get(escalo, {}).get("escalo") is True and det.get(escalo, {}).get("real") is True
              and det.get(resolvio, {}).get("escalo") is False
              and det.get(simulada, {}).get("real") is False,
              "cada uso dice su conversacion, si escalo y si fue real", str(det))
    comprobar(all("contenido" not in d for d in cuerpo.get("detalle", [])),
              "sin texto de la conversacion")
    r = http.get(f"/habilidades/{uuid.uuid4()}/usos?tenant={TENANT}")
    comprobar(r.status_code == 404, "una habilidad que no existe da 404")


CEDULA, TELEFONO = "1098765432", "3001234567"


def tool_call(c, herramienta, *, exito=True, bloqueo=False, error=None,
              parametros=None, hace_min=0, segs=0):
    q("""insert into asistente.tool_calls
           (organization_id, conversation_id, herramienta, parametros, exito,
            codigo_error, es_bloqueo, creado_en)
         values (%s, %s, %s, %s::jsonb, %s, %s, %s,
                 now() - make_interval(mins => %s) + make_interval(secs => %s))""",
      (ORG, c, herramienta, __import__("json").dumps(parametros or {}), exito,
       error, bloqueo, hace_min, segs))


def parte_caso_dorado(http, _api, config) -> None:
    import json
    import tempfile
    import yaml
    from nucleo.habilidades import casos_dorados

    print("\n-- 3. un ejemplo marcado da un caso dorado, desde la traza --")
    entrada = casos_dorados.rol_de_entrada(config)
    derivadora = next(h for h in config.herramientas if h.deriva_rol)
    destino = next(a for a in derivadora.areas_destino if a != entrada)
    otra = next(h.nombre for h in config.herramientas
                if not h.deriva_rol and h.nombre in config.roles[destino].puede_consultar)

    c = conv("whatsapp", rol=destino, hace_min=30)
    msj(c, f"hola, mi cedula es {CEDULA} y mi celular {TELEFONO}, no tengo internet",
        hace_min=30)
    msj(c, "Te paso con el area", rol="assistant", hace_min=30, segs=5)
    tool_call(c, derivadora.nombre, parametros={"area": destino}, hace_min=30, segs=6)
    tool_call(c, otra, hace_min=30, segs=7)
    tool_call(c, "una_bloqueada", exito=False, bloqueo=True,
              error="IDENTIDAD_NO_VERIFICADA", hace_min=30, segs=8)
    msj(c, "gracias", hace_min=29)
    marcada = msj(c, "De nada, ya quedo", rol="assistant", hace_min=29, segs=5)
    # Un turno POSTERIOR al marcado, con un error: no es parte del ejemplo.
    msj(c, "otra cosa mas", hace_min=28)
    tool_call(c, otra, exito=False, error="TIMEOUT", hace_min=28, segs=5)
    ejemplo = str(q("""insert into asistente.ejemplos_validados
                         (organization_id, conversation_id, mensaje_id, caso, marcado_por)
                       values (%s, %s, %s, 'otro', 'ana') returning id""",
                    (ORG, c, marcada))[0][0])

    r = http.get(f"/manual/ejemplos/{ejemplo}/caso-dorado?tenant={TENANT}")
    cuerpo = r.get_json() or {}
    texto = cuerpo.get("caso_dorado") or ""
    comprobar(r.status_code == 200 and texto, "la ruta devuelve el YAML del caso", str(cuerpo)[:300])
    caso = (yaml.safe_load("casos:\n" + texto) or {}).get("casos", [{}])[0]
    comprobar(CEDULA not in texto and TELEFONO not in texto,
              "EL EFECTO: ni la cedula ni el telefono del cliente llegan al YAML", texto)
    comprobar(caso.get("mensajes", [None])[0] and "no tengo internet" in caso["mensajes"][0]
              and caso["mensajes"][1:] == ["gracias"],
              "los mensajes son los del cliente hasta el turno marcado, en orden",
              str(caso.get("mensajes")))
    espera = caso.get("espera") or {}
    comprobar(espera.get("deriva_a") == destino and espera.get("usa") == [derivadora.nombre, otra],
              "afirma la traza: a donde derivo y que herramientas corrieron (la bloqueada no)",
              str(espera))
    comprobar(espera.get("sin_errores") is True,
              "el error del turno SIGUIENTE no es parte del ejemplo: afirma sin_errores", str(espera))
    comprobar(caso.get("rol") == entrada and caso.get("manual") is True
              and caso.get("origen") == f"ejemplo:{ejemplo}",
              "rol de entrada, nace manual y dice de donde salio", str(caso))

    print("\n-- 4. aprobar una revision tiene un efecto --")
    buena = str(q("""insert into asistente.revisiones_supervisor
                       (organization_id, conversation_id, es_buen_ejemplo, caso, justificacion)
                     values (%s, %s, true, 'otro', 'bien') returning id""", (ORG, c))[0][0])
    c_mala = conv("whatsapp", hace_min=20)
    msj(c_mala, "quiero cancelar", hace_min=20)
    mala = str(q("""insert into asistente.revisiones_supervisor
                      (organization_id, conversation_id, es_buen_ejemplo, justificacion)
                    values (%s, %s, false, 'invento un dato') returning id""",
                 (ORG, c_mala))[0][0])
    r = http.post(f"/manual/revisiones/{buena}/aprobar", json={"tenant": TENANT, "revisado_por": "x"})
    cuerpo = r.get_json() or {}
    comprobar(r.status_code == 200 and "caso_dorado" in cuerpo
              and f"revision:{buena}" in cuerpo["caso_dorado"],
              "aprobar una de buen ejemplo devuelve su caso dorado", str(cuerpo)[:300])
    rev = (yaml.safe_load("casos:\n" + cuerpo.get("caso_dorado", "")) or {}).get("casos", [{}])[0]
    comprobar("sin_errores" not in (rev.get("espera") or {})
              and any("errores" in a for a in cuerpo.get("avisos", [])),
              "la conversacion ENTERA tuvo un error: no afirma sin_errores, y lo avisa")
    r = http.post(f"/manual/revisiones/{mala}/aprobar", json={"tenant": TENANT})
    estado = q("select estado from asistente.revisiones_supervisor where id = %s", (mala,))[0][0]
    comprobar(r.status_code == 409 and estado == "pendiente",
              "una «con problemas» no se aprueba (409) y queda pendiente", f"{r.status_code} {estado}")
    r = http.post(f"/manual/revisiones/{mala}/descartar", json={"tenant": TENANT})
    comprobar(r.status_code == 200, "y se puede descartar")

    print("\n-- 5. el importador y cli/evaluar.py --")
    from nucleo.config import fuente
    fuente.desde_base = lambda t: (config, 1)
    sys.path.insert(0, str(RAIZ / "cli"))
    import importar_casos_dorados as imp
    tmp = Path(tempfile.mkdtemp())
    (tmp / "evaluacion").mkdir()
    archivo = tmp / "evaluacion" / f"{TENANT}.casos.yaml"
    archivo.write_text(
        "# comentario que no se puede perder\n"
        "sesion_por_defecto:\n  verificado: true\n  nivel: 1\n  identificador_canal: lab\n"
        "prohibido_a_cliente_final: []\n"
        "casos:\n"
        "  # un caso que ya estaba\n"
        f"  - nombre: ya estaba\n    rol: {entrada}\n    mensajes: [\"hola\"]\n"
        "    espera:\n      sin_errores: true\n", encoding="utf-8")
    imp.main([TENANT, "--archivo", str(archivo)])
    texto = archivo.read_text(encoding="utf-8")
    doc = yaml.safe_load(texto)
    origenes = [x.get("origen") for x in doc["casos"]]
    comprobar(origenes == [None, f"ejemplo:{ejemplo}", f"revision:{buena}"],
              "agrega el ejemplo y la revision aprobada (no la descartada), despues de lo que habia",
              str(origenes))
    comprobar(texto.startswith("# comentario que no se puede perder")
              and "# un caso que ya estaba" in texto,
              "sin tocar los comentarios del archivo")
    comprobar(CEDULA not in texto and TELEFONO not in texto, "tampoco el archivo trae la cedula")
    imp.main([TENANT, "--archivo", str(archivo)])
    comprobar(len(yaml.safe_load(archivo.read_text(encoding="utf-8"))["casos"]) == 3,
              "correrlo de nuevo no duplica (por 'origen')")

    # cli/evaluar.py con SU cargador y SU correr_caso: se le cambia la raiz
    # para que lea el archivo de arriba, la config, y el modelo por un doble
    # que repite la traza de la conversacion real.
    import evaluar
    evaluar.RAIZ = tmp
    evaluar.cargar_config = lambda _ruta: config

    def correr(fiel: bool) -> dict:
        def responder(_config, _rol, mensaje, historial, sesion):
            historial.append({"role": "user", "content": mensaje})
            if fiel and "no tengo internet" in mensaje:
                sesion.rol_siguiente = destino
                return "ok", [{"herramienta": derivadora.nombre},
                              {"herramienta": otra}], []
            return "ok", [], []
        evaluar.motor.responder = responder
        salida = tmp / "informe.json"
        sys.argv = ["evaluar.py", TENANT, "--caso", f"ejemplo {ejemplo[:8]}",
                    "--json", str(salida)]
        try:
            evaluar.main()
        except SystemExit:
            pass
        return json.loads(salida.read_text(encoding="utf-8"))[0]

    bien = correr(True)
    comprobar(bien["ok"], "cli/evaluar.py carga el caso y pasa contra la misma traza",
              str(bien["fallas"]))
    mal = correr(False)
    comprobar(not mal["ok"] and any("deriva_a" in f for f in mal["fallas"]),
              "y falla si el agente no deriva: el caso afirma algo", str(mal["fallas"]))


def parte_simulador(http) -> None:
    print("\n-- 6. reproducir una conversacion en el simulador --")
    c = conv("whatsapp", hace_min=15)
    msj(c, f"mi numero es {TELEFONO}", hace_min=15)
    msj(c, "respuesta", rol="assistant", hace_min=15, segs=3)
    foto = msj(c, "descripcion de una foto que mando", hace_min=14)
    q("""insert into asistente.media (organization_id, conversation_id, mensaje_id,
           media_id, tipo, contenido, bytes) values (%s, %s, %s, 'm1', 'image', '\\x00', 1)""",
      (ORG, c, foto))
    msj(c, "sigue sin andar", hace_min=13)
    r = http.get(f"/simulador/reproduccion?tenant={TENANT}&conversacion_id={c}")
    mensajes = (r.get_json() or {}).get("mensajes")
    comprobar(r.status_code == 200 and len(mensajes or []) == 2
              and mensajes[1] == "sigue sin andar",
              "solo el texto del cliente, en orden, sin la foto", str(mensajes))
    comprobar(TELEFONO not in " ".join(mensajes or []), "y redactado")

    print("\n-- 7. la traza de un turno del simulador --")
    from nucleo.config import fuente
    config = fuente.desde_base(TENANT)[0]
    derivadora = next(h for h in config.herramientas if h.deriva_rol)
    s = conv("whatsapp-simulado", tel="sim-1", hace_min=10)
    u1 = msj(s, "no tengo internet", hace_min=10)
    tool_call(s, derivadora.nombre, parametros={"area": "area_x"}, hace_min=10, segs=4)
    tool_call(s, "consulta_que_fallo", exito=False, error="TIMEOUT", hace_min=10, segs=5)
    u2 = msj(s, "y ahora?", hace_min=9)
    tool_call(s, "otra_del_turno_2", hace_min=9, segs=4)
    r = http.get(f"/simulador/traza?tenant={TENANT}&conversacion_id={s}&desde_mensaje={u1}")
    t1 = r.get_json() or {}
    comprobar(r.status_code == 200
              and [h["herramienta"] for h in t1.get("herramientas", [])]
              == [derivadora.nombre, "consulta_que_fallo"],
              "el turno 1 trae SUS herramientas, no las del turno 2", str(t1))
    comprobar(t1.get("derivo_a") == "area_x" and len(t1.get("errores", [])) == 1
              and t1["errores"][0]["codigo_error"] == "TIMEOUT",
              "dice a donde derivo y que fallo")
    comprobar(t1.get("completa") is False, "sin el cierre de la ejecucion, 'completa' es false")
    q("""insert into asistente.ejecuciones (organization_id, agente, conversation_id,
           estado, terminada_en) values (%s, 'x', %s, 'terminada', now())""", (ORG, s))
    t2 = http.get(f"/simulador/traza?tenant={TENANT}&conversacion_id={s}&desde_mensaje={u2}").get_json()
    comprobar(t2.get("completa") is True
              and [h["herramienta"] for h in t2["herramientas"]] == ["otra_del_turno_2"],
              "con el cierre escrito, 'completa' es true", str(t2))
    r = http.get(f"/simulador/traza?tenant={TENANT}&conversacion_id={c}&desde_mensaje={foto}")
    comprobar(r.status_code == 403, "la traza de una conversacion REAL no sale por el simulador")


try:
    print(f"\n       -> construyendo {BASE}", flush=True)
    r = subprocess.run([sys.executable, str(RAIZ / "cli" / "base_desde_cero.py"), "--base", BASE,
                        "--host", HOST, "--puerto", PUERTO, "--usuario", USUARIO],
                       capture_output=True, text=True, timeout=1800,
                       env={**os.environ, "DBHOST": HOST, "DBPORT": PUERTO, "DBUSER": USUARIO,
                            "DBPASSWORD": CLAVE})
    if r.returncode != 0:
        comprobar(False, "base desde cero", (r.stdout + r.stderr)[-1500:])
        raise SystemExit(1)
    fila_minima("organization", {"id": ORG, "name": "Org manual"})
    q("insert into asistente.tenant_config (organization_id, slug) values (%s, %s)", (ORG, TENANT))
    os.environ["DBNAME"] = BASE

    parte_analista()

    from nucleo.canales import api                                  # noqa: E402
    api._TOKEN_SERVICIO = None
    http = api.app.test_client()
    parte_usos(http)

    # La config de una empresa real del repo: el caso se arma con lo que ELLA
    # declara (rol de entrada, que herramienta deriva), sin nombrarlo aca.
    from nucleo.config import cargar_config                         # noqa: E402
    CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
    api._config_de = lambda _t: CONFIG
    parte_caso_dorado(http, api, CONFIG)
    parte_simulador(http)
finally:
    try:
        from nucleo.persistencia import db as _db
        _db.cerrar_pools()
    except Exception:
        pass
    try:
        with psycopg.connect(dsn("postgres"), autocommit=True) as con:
            con.execute(f"drop database if exists {BASE} with (force)")
    except Exception as e:
        print(f"  (no se pudo borrar {BASE}: {type(e).__name__})")

print()
print("=" * 74)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" todo en verde")
