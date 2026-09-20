# -*- coding: utf-8 -*-
"""
================================================================================
 B5 -- APROBAR UNA ACCION  (contrato §3.4, §3.7, §9.3, T12, T13, X17, X23)
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=<base del ledger> \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_b5_acciones.py

Que protege, en orden de lo que costaria si se rompe:

  1. QUE NO SE EJECUTE LO QUE YA NO APLICA. Entre proponer y aprobar pasa
     tiempo: el ticket lo cerro otro tecnico, la factura se pago. Ejecutar la
     propuesta tal cual escribe sobre un mundo que ya no existe.

  2. LA ASIMETRIA DE LA REVALIDACION. Tres desenlaces, no dos:
         cumple      -> ejecuta
         no cumple   -> vencida       (se comprobo y no aplica)
         no se pudo  -> NO ejecuta, vuelve a pendiente
     Tratar "no se pudo comprobar" como "se cumple" ejecutaria a ciegas justo
     cuando la API externa esta en problemas: el peor momento posible.

  3. QUE DOS APROBACIONES NO PRODUZCAN DOS EFECTOS. La reserva condicionada es
     lo unico que lo impide, y se prueba con dos peticiones reales.

  4. QUE unknown != failed. Un timeout despues de mandar el pedido no prueba
     que no se hizo: queda 'desconocida' y NO se reintenta.

EL EJECUTOR SE INYECTA Y SE CUENTA. Ninguna asercion dice "la guarda existe":
todas miden cuantas veces se llamo al ejecutor real y que quedo en la base.
================================================================================
"""

from __future__ import annotations

import os
import sys
import threading
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
from nucleo.relevo import revalidacion                            # noqa: E402

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()
T_A = f"prueba-b5-{uuid.uuid4().hex[:8]}"
T_B = f"prueba-b5-{uuid.uuid4().hex[:8]}"
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


def conversacion(org, estado="abierta"):
    return admin.execute(
        "insert into asistente.conversations (organization_id, canal, usuario_externo, estado) "
        "values (%s, 'whatsapp', %s, %s) returning id",
        (str(org), f"57300{uuid.uuid4().int % 10**7:07d}", estado)).fetchone()["id"]


def proponer(tenant, conv, *, herramienta="crear_ticket", args=None,
             vigencia=60):
    accion_id, ya = db.guardar_accion_propuesta(
        tenant, herramienta, args or {"servicio": 6555, "asunto": "Sin internet"},
        "Crear ticket 'Sin internet' para el servicio 6555", "soporte", "ia",
        conversation_id=str(conv), vigencia_minutos=vigencia)
    return accion_id, ya


def fila(accion_id):
    return admin.execute(
        "select estado, conversation_id, vence_en, clave_equivalencia, "
        "revisado_por, codigo_error, resultado_ejecucion "
        "from asistente.acciones_propuestas where id = %s", (accion_id,)).fetchone()


def eventos(accion_id):
    return [f["tipo"] for f in admin.execute(
        "select tipo from asistente.acciones_eventos where accion_id = %s "
        "order by creado_en", (accion_id,)).fetchall()]


# --- El catalogo de mentira, con una herramienta aprobable y su lectura ------
class Herr:
    def __init__(self, nombre, **kw):
        self.nombre = nombre
        self.tipo = "http"
        self.solo_lectura = kw.get("solo_lectura", False)
        self.aprobacion_humana = kw.get("aprobacion_humana", False)
        self.aprobacion = kw.get("aprobacion")
        self.asincrona = False


class Cond:
    def __init__(self, campo, operador="igual_a", valor=None, valor_de_propuesta=None):
        self.campo, self.operador = campo, operador
        self.valor, self.valor_de_propuesta = valor, valor_de_propuesta


class Reval:
    def __init__(self, herramienta, argumentos=None, condiciones=()):
        self.herramienta = herramienta
        self.argumentos = argumentos or {}
        self.condiciones = list(condiciones)


class Aprob:
    def __init__(self, vigencia_minutos, revalidar):
        self.vigencia_minutos, self.revalidar = vigencia_minutos, revalidar


class Config:
    def __init__(self, tenant, herramientas):
        self.herramientas = herramientas
        self.variables_tenant = {}

        class Id:
            slug = tenant
        self.identidad = Id()


class Espia:
    """Cuenta las ejecuciones reales."""

    def __init__(self, resultado=None, codigo=None):
        self.llamadas = []
        self.resultado, self.codigo = resultado or {"id": 77}, codigo

    def __call__(self, config, accion):
        self.llamadas.append(accion)
        return self.resultado, self.codigo


REVAL_TICKET = Aprob(60, Reval("consultar_ticket", {"id": "{id_ticket}"},
                               [Cond("estado", "distinto_de", valor=4)]))
CATALOGO = [
    Herr("crear_ticket", aprobacion_humana=True, aprobacion=REVAL_TICKET),
    Herr("consultar_ticket", solo_lectura=True),
    Herr("sin_reval", aprobacion_humana=True),
]

try:
    sembrar_org(ORG_A, T_A)
    sembrar_org(ORG_B, T_B)
    api.app.config["TESTING"] = True
    cliente = api.app.test_client()

    original_exec = api.motor.ejecutar_accion_aprobada
    original_cfg = api._config_de
    api._config_de = lambda t: Config(t, CATALOGO)

    def aprobar(tenant, accion_id, quien="Ana Gomez"):
        return cliente.post(f"/acciones/propuestas/{accion_id}/aprobar",
                            json={"tenant": tenant, "revisado_por": quien})

    # =========================================================================
    titulo("1. toda accion nueva nace ligada, con plazo y clave")
    # =========================================================================
    conv = conversacion(ORG_A)
    accion, ya = proponer(T_A, conv)
    f = fila(accion)
    revisar(str(f["conversation_id"]) == str(conv),
            "la accion queda ligada a su conversacion")
    revisar(f["vence_en"] is not None, "y con su plazo de vigencia")
    revisar(f["clave_equivalencia"] is not None, "y con su clave de equivalencia")
    revisar(ya is False, "la primera propuesta no es duplicada")

    # T12: la equivalente viva no crea otra, devuelve la que hay.
    mismo, ya2 = proponer(T_A, conv)
    revisar(mismo == accion and ya2 is True,
            "proponer lo mismo devuelve la que ya existe, no crea otra",
            "Tres pedidos iguales dejarian tres tickets del mismo problema.")
    revisar("accion_propuesta_duplicada" in eventos(accion),
            "y queda el evento del duplicado")
    cuantas = admin.execute(
        "select count(*) as n from asistente.acciones_propuestas "
        "where conversation_id = %s", (conv,)).fetchone()["n"]
    revisar(cuantas == 1, f"sigue habiendo una sola fila (hay {cuantas})")

    # Distintos argumentos SI son otra accion.
    otra, _ = proponer(T_A, conv, args={"servicio": 999, "asunto": "Otro"})
    revisar(otra != accion, "argumentos distintos si crean otra accion")

    # Y la misma accion en OTRA conversacion tambien.
    conv2 = conversacion(ORG_A)
    tercera, ya3 = proponer(T_A, conv2)
    revisar(tercera != accion and ya3 is False,
            "el mismo pedido en otra conversacion es otra accion")

    # =========================================================================
    titulo("2. la revalidacion decide, y sus tres desenlaces")
    # =========================================================================
    herr = CATALOGO[0]
    base = {"argumentos": {"id_ticket": 90354, "servicio": 6555}}

    v = revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr, base,
                               leer=lambda h, a: {"id": 90354, "estado": 2})
    revisar(v.desenlace == revalidacion.CUMPLE,
            "ticket abierto (estado 2) -> cumple")

    v = revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr, base,
                               leer=lambda h, a: {"id": 90354, "estado": 4})
    revisar(v.desenlace == revalidacion.NO_CUMPLE,
            "ticket cerrado (estado 4) -> NO cumple")

    def cae(h, a):
        raise TimeoutError("la API no respondio")

    v = revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr, base, leer=cae)
    revisar(v.desenlace == revalidacion.NO_SE_PUDO,
            "la API caida -> NO SE PUDO, que no es 'cumple' ni 'no cumple'",
            "Tratarlo como 'cumple' ejecutaria a ciegas con la API en problemas.")

    v = revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr, base,
                               leer=lambda h, a: {"id": 90354})
    revisar(v.desenlace == revalidacion.NO_SE_PUDO,
            "el campo que no vino -> NO SE PUDO, no se asume que cumple")

    # La API contesta "4" y el catalogo declara 4: es el mismo estado.
    v = revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr, base,
                               leer=lambda h, a: {"estado": "4"})
    revisar(v.desenlace == revalidacion.NO_CUMPLE,
            "'4' y 4 son el mismo estado: no falla por el tipo",
            "Una condicion que falla por tipos bloquea una accion valida.")

    # Respuesta envuelta en 'results', como contestan estas APIs.
    v = revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr, base,
                               leer=lambda h, a: {"results": [{"estado": 2}]})
    revisar(v.desenlace == revalidacion.CUMPLE, "lee dentro de 'results'")

    # Comparar y cambiar (§3.7): el estado actual == el que se vio al proponer.
    herr_cc = Herr("actualizar_estado", aprobacion_humana=True,
                   aprobacion=Aprob(60, Reval(
                       "consultar_ticket", {"id": "{id_ticket}"},
                       [Cond("estado", "igual_a", valor_de_propuesta="estado_visto")])))
    cfg_cc = Config(T_A, CATALOGO + [herr_cc])
    accion_cc = {"argumentos": {"id_ticket": 1, "estado_visto": 2}}
    revisar(revalidacion.revalidar(cfg_cc, T_A, herr_cc, accion_cc,
                                   leer=lambda h, a: {"estado": 2}).desenlace
            == revalidacion.CUMPLE,
            "comparar y cambiar: el estado sigue siendo el que se vio")
    revisar(revalidacion.revalidar(cfg_cc, T_A, herr_cc, accion_cc,
                                   leer=lambda h, a: {"estado": 3}).desenlace
            == revalidacion.NO_CUMPLE,
            "y si otro lo movio, no se pisa el cambio ajeno")

    # Una lectura que no es de lectura no puede revalidar.
    herr_mala = Herr("mala", aprobacion_humana=True,
                     aprobacion=Aprob(60, Reval("crear_ticket", {}, [])))
    revisar(revalidacion.revalidar(Config(T_A, CATALOGO + [herr_mala]), T_A,
                                   herr_mala, base,
                                   leer=lambda h, a: {}).desenlace
            == revalidacion.NO_SE_PUDO,
            "revalidar con algo que ESCRIBE no corre",
            "Correria un efecto antes de decidir si se corre el efecto.")

    # Declarada y ausente del catalogo: tampoco se saltea (X17).
    herr_fant = Herr("fant", aprobacion_humana=True,
                     aprobacion=Aprob(60, Reval("no_existe", {}, [])))
    revisar(revalidacion.revalidar(Config(T_A, CATALOGO), T_A, herr_fant, base,
                                   leer=lambda h, a: {}).desenlace
            == revalidacion.NO_SE_PUDO,
            "una revalidacion declarada que no esta en el catalogo NO se saltea")

    # =========================================================================
    titulo("3. aprobar: los cuatro pasos, medidos por el ejecutor")
    # =========================================================================
    espia = Espia()
    api.motor.ejecutar_accion_aprobada = espia
    api.revalidacion.revalidar = lambda *a, **k: revalidacion.Veredicto(revalidacion.CUMPLE)

    conv3 = conversacion(ORG_A)
    ok_accion, _ = proponer(T_A, conv3)
    r = aprobar(T_A, ok_accion)
    revisar(r.status_code == 200 and r.get_json()["estado"] == "ejecutada_ok",
            f"la aprobacion normal ejecuta y queda ejecutada_ok (fue {r.status_code})")
    revisar(len(espia.llamadas) == 1, "el ejecutor se llamo exactamente una vez")
    f = fila(ok_accion)
    revisar(f["estado"] == "ejecutada_ok" and f["revisado_por"] == "Ana Gomez",
            "la fila guarda el desenlace y quien aprobo")
    revisar("accion_aprobada" in eventos(ok_accion), "con su evento durable")

    # Volver a aprobar no ejecuta otra vez.
    antes = len(espia.llamadas)
    r = aprobar(T_A, ok_accion)
    revisar(r.status_code in (400, 409) and len(espia.llamadas) == antes,
            "aprobar de nuevo no vuelve a ejecutar")

    # Sin responsable no se aprueba.
    otra3, _ = proponer(T_A, conv3, args={"servicio": 1, "asunto": "x"})
    antes = len(espia.llamadas)
    r = cliente.post(f"/acciones/propuestas/{otra3}/aprobar", json={"tenant": T_A})
    revisar(r.status_code == 400 and len(espia.llamadas) == antes,
            "sin 'revisado_por' no se ejecuta nada")

    # --- la revalidacion manda -------------------------------------------
    api.revalidacion.revalidar = lambda *a, **k: revalidacion.Veredicto(
        revalidacion.NO_CUMPLE, "estado:distinto_de", "El ticket ya esta cerrado.")
    nc, _ = proponer(T_A, conv3, args={"servicio": 2, "asunto": "y"})
    antes = len(espia.llamadas)
    r = aprobar(T_A, nc)
    revisar(r.status_code == 409 and len(espia.llamadas) == antes,
            "revalidacion que NO cumple -> no se ejecuta")
    revisar(fila(nc)["estado"] == "vencida", "y la accion queda 'vencida'")
    revisar("accion_vencida" in eventos(nc), "con su evento")

    api.revalidacion.revalidar = lambda *a, **k: revalidacion.Veredicto(
        revalidacion.NO_SE_PUDO, "lectura_fallida:TimeoutError")
    ns, _ = proponer(T_A, conv3, args={"servicio": 3, "asunto": "z"})
    antes = len(espia.llamadas)
    r = aprobar(T_A, ns)
    revisar(r.status_code == 503 and len(espia.llamadas) == antes,
            "revalidacion que no se PUDO correr -> no se ejecuta")
    revisar(fila(ns)["estado"] == "pendiente",
            "y la accion vuelve a 'pendiente': se puede reintentar",
            "No es 'vencida': la accion puede seguir siendo valida.")
    revisar(fila(ns)["revisado_por"] is None,
            "sin quedar marcada como revisada por nadie")

    api.revalidacion.revalidar = lambda *a, **k: revalidacion.Veredicto(revalidacion.CUMPLE)

    # =========================================================================
    titulo("4. el plazo (TTL)")
    # =========================================================================
    conv4 = conversacion(ORG_A)
    vieja, _ = proponer(T_A, conv4, args={"servicio": 4, "asunto": "vieja"})
    admin.execute("update asistente.acciones_propuestas set vence_en = now() - interval '1 minute' "
                  "where id = %s", (vieja,))
    antes = len(espia.llamadas)
    r = aprobar(T_A, vieja)
    revisar(r.status_code == 409 and len(espia.llamadas) == antes,
            "una accion vencida no se ejecuta")
    revisar(fila(vieja)["estado"] == "vencida", "y queda marcada 'vencida'")
    revisar("accion_vencida" in eventos(vieja), "con su evento")

    # =========================================================================
    titulo("5. la conversacion cerrada, y el legado")
    # =========================================================================
    cerrada = conversacion(ORG_A, estado="cerrada")
    en_cerrada, _ = proponer(T_A, cerrada, args={"servicio": 5, "asunto": "c"})
    antes = len(espia.llamadas)
    r = aprobar(T_A, en_cerrada)
    revisar(r.status_code == 409 and len(espia.llamadas) == antes,
            "no se aprueba una accion de conversacion cerrada")
    revisar(fila(en_cerrada)["estado"] == "pendiente",
            "y la accion no cambia de estado")

    legado, _ = db.guardar_accion_propuesta(
        T_A, "crear_ticket", {"servicio": 1}, "legado", "soporte", "ia")
    antes = len(espia.llamadas)
    r = aprobar(T_A, legado)
    revisar(r.status_code == 409 and r.get_json().get("codigo") == "accion_de_legado"
            and len(espia.llamadas) == antes,
            "el bloqueo del legado de G3 sigue en pie")

    # =========================================================================
    titulo("6. dos aprobaciones a la vez producen UN solo efecto")
    # =========================================================================
    conv6 = conversacion(ORG_A)
    carrera, _ = proponer(T_A, conv6, args={"servicio": 6, "asunto": "carrera"})
    espia_carrera = Espia()
    api.motor.ejecutar_accion_aprobada = espia_carrera
    codigos = []
    barrera = threading.Barrier(2)

    def intentar():
        barrera.wait()
        with api.app.test_client() as c:
            r = c.post(f"/acciones/propuestas/{carrera}/aprobar",
                       json={"tenant": T_A, "revisado_por": "Ana"})
            codigos.append(r.status_code)

    hilos = [threading.Thread(target=intentar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    revisar(len(espia_carrera.llamadas) == 1,
            f"el ejecutor corrio UNA vez (corrio {len(espia_carrera.llamadas)})",
            "Dos ejecuciones son dos tickets, y eso son dos visitas tecnicas.")
    revisar(sorted(codigos) == [200, 409],
            f"uno gana y el otro se entera (fueron {sorted(codigos)})")
    revisar(eventos(carrera).count("accion_aprobada") == 1,
            "y hay un solo evento de aprobacion")

    # =========================================================================
    titulo("7. unknown != failed")
    # =========================================================================
    conv7 = conversacion(ORG_A)
    incierta, _ = proponer(T_A, conv7, args={"servicio": 7, "asunto": "timeout"})
    api.motor.ejecutar_accion_aprobada = Espia(
        resultado={"error": "sin respuesta"}, codigo="ReadTimeout: la API no contesto")
    r = aprobar(T_A, incierta)
    revisar(fila(incierta)["estado"] == "desconocida",
            "un timeout despues de mandar el pedido queda 'desconocida'",
            "No prueba que no se hizo: el pedido pudo haber llegado.")
    revisar(r.get_json().get("estado") == "desconocida"
            and "NO se reintenta" in (r.get_json().get("mensaje") or ""),
            "y la respuesta dice que NO se reintenta")
    revisar("accion_desconocida" in eventos(incierta), "con su evento propio")

    fallida, _ = proponer(T_A, conv7, args={"servicio": 8, "asunto": "400"})
    api.motor.ejecutar_accion_aprobada = Espia(
        resultado={"error": "rechazado"}, codigo="ErrorHerramientaHttp: 400")
    r = aprobar(T_A, fallida)
    revisar(fila(fallida)["estado"] == "ejecutada_fallo",
            "un 400 SI prueba que no se hizo: 'ejecutada_fallo'")

    # =========================================================================
    titulo("8. una empresa no ve ni toca las de otra")
    # =========================================================================
    api.motor.ejecutar_accion_aprobada = Espia()
    conv_b = conversacion(ORG_B)
    de_b, _ = proponer(T_B, conv_b)
    espia_b = Espia()
    api.motor.ejecutar_accion_aprobada = espia_b
    r = aprobar(T_A, de_b)
    revisar(r.status_code == 404 and espia_b.llamadas == [],
            f"A no puede aprobar una de B (fue {r.status_code})")
    revisar(fila(de_b)["estado"] == "pendiente", "y la de B sigue intacta")

    revisar(db.acciones_de_conversacion(T_A, str(conv_b)) == [],
            "A no ve las acciones de una conversacion de B")

    # =========================================================================
    titulo("9. lo que la pantalla recibe")
    # =========================================================================
    vista = db.acciones_de_conversacion(T_A, str(conv3))
    revisar(vista and all("argumentos" not in v for v in vista),
            "la vista de la conversacion NO trae los argumentos crudos")
    revisar(all("resumen" in v and "estado" in v for v in vista),
            "pero si el resumen y el estado real")
    estados = {v["estado"] for v in vista}
    revisar("ejecutada_ok" in estados and "vencida" in estados,
            f"y los estados son los de verdad, no 'aprobada' para todo ({estados})")

finally:
    api.motor.ejecutar_accion_aprobada = original_exec
    api._config_de = original_cfg
    for org in (ORG_A, ORG_B):
        admin.execute("delete from public.organization where id = %s", (str(org),))
    admin.close()

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] Una accion se ejecuta solo si sigue aplicando, y una sola vez.")
