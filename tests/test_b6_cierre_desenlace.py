# -*- coding: utf-8 -*-
"""
================================================================================
 B6 -- el cierre dice por que, y no lo adivina nadie
================================================================================

    DBHOST=localhost DBPORT=55435 DBNAME=b6_limpia \\
      DBUSER=motor DBPASSWORD=motor py -3.13 tests/test_b6_cierre_desenlace.py

Contra PostgreSQL real. Contrato §3.1, §3.5, T15a, T15b, T16, T17 y la tercera
decision de G8.

LO QUE SE AFIRMA
----------------
  1. el catalogo: doce base, extension por empresa, I16 fail-closed;
  2. el desenlace NO SE INFIERE por ninguno de los cinco caminos;
  3. el cierre es atomico: estado, desenlace, acciones canceladas y evento, o
     nada;
  4. cerrar la conversacion NO cierra el caso ni el ticket de afuera;
  5. concurrencia, idempotencia y aislamiento entre empresas;
  6. G8 'cerrar_con_desenlace' pasa por la transicion real, no por un atajo.
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

from nucleo.relevo import desenlaces                              # noqa: E402
from nucleo.relevo import transiciones as T                       # noqa: E402

DATOS = dict(host=os.environ["DBHOST"], port=os.environ["DBPORT"],
             dbname=os.environ["DBNAME"], user=os.environ["DBUSER"],
             password=os.environ["DBPASSWORD"])
admin = psycopg.connect(**DATOS, autocommit=True, row_factory=dict_row)
ORG = uuid.uuid4()
TEN = f"prueba-b6-{uuid.uuid4().hex[:8]}"
OP_ID = str(uuid.uuid4())
OP = "Ana Gomez"


def _columnas_obligatorias():
    return admin.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name='organization' "
        "and is_nullable='NO' and column_default is null").fetchall()


def sembrar_org(org_id, slug):
    valores = {"id": str(org_id), "name": slug, "api_key": f"k-{org_id}",
               "company_name": slug}
    for f in _columnas_obligatorias():
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
                  "values (%s, %s) on conflict do nothing", (str(org_id), slug))


def conversacion(org=None, **kw):
    campos = {"canal": "whatsapp", "estado": "abierta", "control": "ia",
              "control_motivo": None, "relevo_version": 1,
              "atendida_manual": False, "escalada_a_humano": False,
              "necesita_atencion_humana": False,
              "asignada_a_usuario_id": None, "asignada_a_nombre": None,
              "caso_id": None, "ticket_operativo": None, "tomada_por": None}
    campos.update(kw)
    cid = admin.execute(
        """insert into asistente.conversations
             (organization_id, canal, usuario_externo, estado, control,
              control_motivo, relevo_version, atendida_manual,
              escalada_a_humano, necesita_atencion_humana,
              asignada_a_usuario_id, asignada_a_nombre, caso_id,
              ticket_operativo, tomada_por)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        (str(org or ORG), campos["canal"], f"57300{uuid.uuid4().int % 10**7:07d}",
         campos["estado"], campos["control"], campos["control_motivo"],
         campos["relevo_version"], campos["atendida_manual"],
         campos["escalada_a_humano"], campos["necesita_atencion_humana"],
         campos["asignada_a_usuario_id"], campos["asignada_a_nombre"],
         campos["caso_id"], campos["ticket_operativo"],
         campos["tomada_por"])).fetchone()["id"]
    return str(cid)


def fila_de(cid):
    return admin.execute(
        """select estado, control, control_motivo, relevo_version,
                  atendida_manual, atendida_por, asignada_a_usuario_id,
                  asignada_a_nombre, cerrada_por_tipo, cerrada_por_usuario_id,
                  desenlace_codigo, desenlace_categoria_base, desenlace_nota
           from asistente.conversations where id = %s""", (cid,)).fetchone()


def eventos_de(cid):
    return admin.execute(
        """select tipo, actor_tipo, actor_nombre, actor_usuario_id, datos
           from asistente.relevo_eventos where conversation_id = %s
           order by creado_en, id""", (cid,)).fetchall()


def accion(cid, estado="pendiente", org=None):
    return str(admin.execute(
        """insert into asistente.acciones_propuestas
             (organization_id, conversation_id, herramienta, argumentos,
              resumen, propuesto_por, estado)
           values (%s, %s, 'crear_ticket', '{}'::jsonb, 'r', 'ia', %s)
           returning id""", (str(org or ORG), cid, estado)).fetchone()["id"])


def verificacion(cid, org=None):
    admin.execute(
        """insert into asistente.verificaciones_accion
             (organization_id, conversation_id, herramienta, espera_segundos,
              max_intentos, estado)
           values (%s, %s, 'reiniciar_ont', 60, 3, 'VERIFICACION_PENDIENTE')""",
        (str(org or ORG), cid))


sembrar_org(ORG, TEN)


# =============================================================================
titulo("1. el catalogo: plataforma primero, empresa despues")
# =============================================================================
base = desenlaces.catalogo(None)
revisar(len(base) == 12, f"sin config hay doce codigos de plataforma ({len(base)})",
        "§3.5: la base funciona SIN escribir config. Escribir tenant_config "
        "hoy partiria la medicion ON vs OFF (Q3).")
revisar(all(d["categoria_base"] == d["codigo"] for d in base),
        "cada codigo base es su propia categoria")
revisar(desenlaces.categoria_de("sin_respuesta_cliente") == "sin_respuesta_cliente",
        "y se resuelve sin config")
revisar(desenlaces.categoria_de("inventado") is None,
        "un codigo desconocido no resuelve a nada",
        "None NO es 'otro'. Tratarlo como 'otro' seria inventar una respuesta.")


class _D:
    def __init__(self, codigo, nombre, categoria_base):
        self.codigo, self.nombre = codigo, nombre
        self.categoria_base = categoria_base


class _Bloque:
    def __init__(self, propios=(), ocultos=()):
        self.propios, self.ocultos = list(propios), list(ocultos)


class _Config:
    def __init__(self, propios=(), ocultos=()):
        self.desenlaces = _Bloque(propios, ocultos)


c_propio = _Config([_D("fibra_poste_17", "Poste 17", "red_distribucion")])
revisar(desenlaces.categoria_de("fibra_poste_17", c_propio) == "red_distribucion",
        "un codigo propio resuelve a su categoria base (I16)",
        "Es lo unico que hace que las metricas sumen entre empresas que le "
        "ponen nombres distintos a la misma falla.")
revisar(len(desenlaces.catalogo(c_propio)) == 13,
        "y se suma al catalogo, sin reemplazar la base")

revisar(desenlaces.problemas([_D("x", "X", "")], []),
        "sin categoria_base la config no carga (I16)")
revisar(desenlaces.problemas([_D("x", "X", "no_existe")], []),
        "con una categoria que no es base tampoco")
revisar(desenlaces.problemas([_D("facturacion", "Otra cosa", "otro")], []),
        "y un propio NO puede redefinir un codigo base",
        "'facturacion' significa lo mismo en todas las empresas: dos "
        "definiciones lo vuelven ambiguo en cualquier metrica cruzada.")
revisar(desenlaces.problemas([_D("x", "X", "otro"), _D("x", "Y", "otro")], []),
        "ni declararse dos veces")
revisar(not desenlaces.problemas([_D("x", "X", "otro")], ["facturacion"]),
        "ocultar un codigo base es valido")
revisar(desenlaces.problemas([], ["fibra_poste_17"]),
        "ocultar algo que no es base, no")
revisar(desenlaces.problemas([], list(desenlaces.BASE)),
        "ocultar los doce sin agregar ninguno se rechaza al CARGAR",
        "Si no, el operador se entera de noche, con un cliente esperando: el "
        "boton de cerrar no tendria ni una opcion.")

oculto = _Config([], ["facturacion"])
revisar("facturacion" not in {d["codigo"] for d in desenlaces.catalogo(oculto)},
        "un codigo oculto sale de lo que se puede ELEGIR")
revisar(desenlaces.categoria_de("facturacion", oculto) == "facturacion",
        "pero lo ya cerrado con el conserva su categoria",
        "Ocultar no es borrar: el pasado no se reescribe.")
sin_plazo = _Config([], ["sin_respuesta_cliente"])
revisar(desenlaces.resolver_para_cerrar(desenlaces.POR_PLAZO, sin_plazo,
                                        por_persona=False)[0]
        == desenlaces.POR_PLAZO,
        "y el cierre por plazo sigue funcionando con el suyo oculto",
        "T16 no es una eleccion de nadie: ocultarlo de la lista no lo desactiva.")
try:
    desenlaces.resolver_para_cerrar(desenlaces.POR_PLAZO, sin_plazo)
    revisar(False, "pero una PERSONA no lo puede elegir si esta oculto")
except ValueError:
    revisar(True, "pero una PERSONA no lo puede elegir si esta oculto",
            "Quien escribe cambia la regla: la plataforma no elige, elige.")
try:
    desenlaces.resolver_para_cerrar("facturacion", oculto)
    revisar(False, "un operador NO puede cerrar con un codigo oculto")
except ValueError:
    revisar(True, "un operador NO puede cerrar con un codigo oculto",
            "Ocultar existe para que una empresa saque de la lista lo que no "
            "usa. Si igual se pudiera elegir, ocultar no significaria nada.")


# =============================================================================
titulo("2. la config falla cerrado")
# =============================================================================
from nucleo.config.schema import TenantConfig                     # noqa: E402
import inspect                                                    # noqa: E402

fuente_schema = inspect.getsource(TenantConfig)
revisar("_desenlaces_validos" in fuente_schema,
        "TenantConfig valida los desenlaces al cargar")
try:
    TenantConfig.model_validate({"desenlaces": {"propios": [
        {"codigo": "x", "nombre": "X", "categoria_base": "no_existe"}]}})
    revisar(False, "una categoria_base invalida rompe la carga entera")
except Exception as e:
    revisar("categoria base" in str(e) or "no_existe" in str(e),
            "una categoria_base invalida rompe la carga entera",
            "No se corrige 'cayendo a otro': eso llenaria las metricas de "
            "fallas de red mal declaradas y nadie lo notaria nunca.")


# =============================================================================
titulo("3. T17 -- una persona resuelve, y dice en que termino")
# =============================================================================
c1 = conversacion(control="humano", control_motivo="escalada",
                  asignada_a_usuario_id=OP_ID, asignada_a_nombre=OP,
                  atendida_manual=True)
r = T.resolver(TEN, c1, operador_id=OP_ID, operador_nombre=OP,
               desenlace="fibra_acometida", nota="empalme rehecho en el poste")
f = fila_de(c1)
revisar(r.aplicada and f["estado"] == "cerrada", "cierra la conversacion")
revisar(f["desenlace_codigo"] == "fibra_acometida"
        and f["desenlace_categoria_base"] == "fibra_acometida",
        f"guarda el codigo Y su categoria ({f['desenlace_codigo']}/"
        f"{f['desenlace_categoria_base']})",
        "La categoria se guarda al cerrar y no se recalcula al leer: la "
        "config de la empresa puede cambiar y el pasado no (§3.6).")
revisar(f["cerrada_por_tipo"] == "operador"
        and str(f["cerrada_por_usuario_id"]) == OP_ID,
        "deja quien la cerro, con su id")
revisar(f["desenlace_nota"] == "empalme rehecho en el poste", "y la nota")
revisar(f["atendida_manual"] and f["atendida_por"] == OP,
        "marca el hecho historico de que una persona actuo")
revisar(f["asignada_a_usuario_id"] is None and f["asignada_a_nombre"] is None,
        "libera la asignacion")
revisar(f["control"] == "humano",
        "y NO toca el control: cerrar no es devolver a la IA")

evs = eventos_de(c1)
revisar([e["tipo"] for e in evs] == ["cerrada"], "deja un evento 'cerrada'")
d = evs[0]["datos"]
revisar(d.get("por") == "operador" and d.get("desenlace") == "fibra_acometida"
        and d.get("categoria") == "fibra_acometida",
        f"con por, desenlace y categoria ({d})")
revisar(evs[0]["actor_nombre"] == OP and str(evs[0]["actor_usuario_id"]) == OP_ID,
        "y dice quien decidio")

# --- el desenlace es obligatorio y no se inventa ---------------------------
for caso, kw in (("sin codigo", {"desenlace": ""}),
                 ("con un codigo que no existe", {"desenlace": "inventado"}),
                 ("con una nota larguisima", {"desenlace": "otro",
                                              "nota": "x" * 501})):
    c = conversacion()
    antes = fila_de(c)
    try:
        T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, **kw)
        revisar(False, f"se rechaza cerrar a mano {caso}")
    except ValueError:
        revisar(True, f"se rechaza cerrar a mano {caso}")
    revisar(fila_de(c) == antes, f"y la conversacion no se toco ({caso})")
    revisar(eventos_de(c) == [], f"sin ningun evento ({caso})")


# =============================================================================
titulo("4. los cinco caminos: cada uno escribe lo suyo, ninguno adivina")
# =============================================================================
# T15a: el cliente confirma con una persona a cargo.
c = conversacion(atendida_manual=True, control="humano", control_motivo="escalada")
T.cerrar(TEN, c, por="cliente")
f = fila_de(c)
revisar(f["cerrada_por_tipo"] == "cliente",
        f"T15a: con 'atendida_manual' queda 'cliente' ({f['cerrada_por_tipo']})")
revisar(f["desenlace_codigo"] is None,
        "y el desenlace en NULL",
        "Que el cliente diga 'ya funciona' no dice si era la ONT, el WiFi o "
        "la fibra. Deducirlo del veredicto seria inventar el dato en la tabla "
        "que existe para aprender.")

# T15b: el mismo gesto, sin que nadie la haya atendido.
c = conversacion(atendida_manual=False)
T.cerrar(TEN, c, por="cliente")
revisar(fila_de(c)["cerrada_por_tipo"] == "ia_cliente",
        "T15b: sin 'atendida_manual' queda 'ia_cliente'",
        "La diferencia entre T15a y T15b es un hecho ya escrito, no una "
        "inferencia: se lee de la fila, con el lock puesto.")

# T16: el barrido por plazo.
c = conversacion(atendida_manual=True, control="humano", control_motivo="escalada")
r = T.cerrar(TEN, c, por="plazo")
f = fila_de(c)
revisar(f["cerrada_por_tipo"] == "plazo"
        and f["desenlace_codigo"] == "sin_respuesta_cliente",
        f"T16: plazo escribe 'sin_respuesta_cliente' ({f['desenlace_codigo']})")
revisar(eventos_de(c)[0]["actor_tipo"] == "sistema",
        "con actor 'sistema': no lo decidio ninguna persona")
revisar(f["cerrada_por_usuario_id"] is None,
        "y sin usuario: no hay a quien atribuirselo")

# T18: inactividad. La columna lo admite; el productor es de otra fase.
c = conversacion()
T.cerrar(TEN, c, por="inactividad")
revisar(fila_de(c)["cerrada_por_tipo"] == "inactividad",
        "T18: 'inactividad' se puede escribir, con desenlace NULL")

# Lo que NO se acepta.
for caso, kw in (("un desenlace por el camino del cliente",
                  {"por": "cliente", "desenlace": "facturacion"}),
                 ("un desenlace distinto por plazo",
                  {"por": "plazo", "desenlace": "facturacion"}),
                 ("una nota en un cierre automatico",
                  {"por": "plazo", "nota": "algo"}),
                 ("un operador en un cierre automatico",
                  {"por": "cliente", "operador_id": OP_ID, "operador_nombre": OP}),
                 ("un camino que no existe", {"por": "porque_si"})):
    c = conversacion()
    antes = fila_de(c)
    try:
        T.cerrar(TEN, c, **kw)
        revisar(False, f"se rechaza {caso}")
    except ValueError:
        revisar(True, f"se rechaza {caso}")
    revisar(fila_de(c) == antes, f"y nada cambia ({caso})")


# =============================================================================
titulo("5. las acciones vivas: la pendiente se cancela, la que ya salio no")
# =============================================================================
c = conversacion(control="humano", control_motivo="escalada")
a1 = accion(c, "pendiente")
a2 = accion(c, "pendiente")
a3 = accion(c, "ejecutando")

# Un cierre AUTOMATICO no procede con algo vivo (T15a/T15b/T16/T18).
antes = fila_de(c)
r = T.cerrar(TEN, c, por="cliente")
revisar(not r.aplicada and r.motivo == "accion_viva",
        f"un cierre automatico no procede con una accion viva ({r.motivo})")
revisar(fila_de(c) == antes, "y la conversacion sigue abierta")

# El manual SI: T17 dice "de inmediato".
r = T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro")
revisar(r.aplicada, "el cierre manual procede igual (T17: de inmediato)")
estados = {str(f["id"]): f["estado"] for f in admin.execute(
    "select id, estado from asistente.acciones_propuestas where conversation_id = %s",
    (c,)).fetchall()}
revisar(estados[a1] == "cancelada" and estados[a2] == "cancelada",
        "las pendientes quedan 'cancelada'")
revisar(estados[a3] == "ejecutando",
        "la que ya salio NO se toca",
        "Su desenlace lo escribe quien la ejecuta o el reconciliador (T20c). "
        "Pisarla con 'cancelada' registraria que no se hizo algo que quiza si "
        "se hizo -- justo lo que X21 prohibe.")
d = eventos_de(c)[0]["datos"]
revisar(d.get("acciones_canceladas") == 2 and d.get("acciones_en_vuelo") == 1,
        f"y el evento deja escrito lo uno y lo otro ({d})",
        "Es lo que despues explica una sincronizacion 'desconocida' en una "
        "conversacion que ya nadie mira.")
eventos_accion = admin.execute(
    "select tipo, actor_tipo from asistente.acciones_eventos where accion_id = %s",
    (a1,)).fetchall()
revisar([e["tipo"] for e in eventos_accion] == ["accion_cancelada"],
        "cada cancelacion deja su propio evento (I12)")

# La verificacion pendiente tambien frena los automaticos (D14).
c = conversacion()
verificacion(c)
r = T.cerrar(TEN, c, por="plazo")
revisar(not r.aplicada and r.motivo == "verificacion_pendiente",
        f"una verificacion sin resolver frena el cierre automatico ({r.motivo})")
revisar(T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP,
                   desenlace="otro").aplicada,
        "y no frena al operador")


# =============================================================================
titulo("6. el cierre ANOTA la intencion externa; no la ejecuta")
# =============================================================================
def sincronizaciones(cid):
    return admin.execute(
        """select tipo, estado, datos_intencion from asistente.sincronizaciones_externas
           where conversation_id = %s order by creado_en""", (cid,)).fetchall()


caso = str(uuid.uuid4())
c = conversacion(caso_id=caso, ticket_operativo="90354",
                 control="humano", control_motivo="escalada")
T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="red_central")
syncs = sincronizaciones(c)
revisar([s["tipo"] for s in syncs] == ["cerrar_caso"],
        f"encola SOLO 'cerrar_caso' ({[s['tipo'] for s in syncs]})",
        "El ticket de WispHub no: su unica via verificada de cierre publica un "
        "comentario en el mismo pedido, asi que cada reintento le deja al "
        "cliente otra copia del texto de cierre.")
revisar(syncs[0]["estado"] == "pendiente"
        and syncs[0]["datos_intencion"] == {"caso_id": caso},
        f"con la intencion minima y en 'pendiente' ({syncs[0]['datos_intencion']})",
        "Solo el id. Nunca payloads crudos ni datos del cliente (X19).")
revisar(fila_de(c)["estado"] == "cerrada",
        "y la conversacion se cierra igual: un fallo externo no la reabre (T17)")
revisar(eventos_de(c)[0]["datos"].get("ticket_pendiente") is True,
        "y el evento DICE que quedo un ticket abierto del otro lado",
        "Callarlo dejaria el ticket vivo sin que nadie se entere. Es menos de "
        "lo que el contrato pide y mas de lo que habia.")

# Sin caso no se encola nada: no hay nada que cerrar.
c = conversacion(control="humano", control_motivo="escalada")
T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro")
revisar(sincronizaciones(c) == [], "sin caso no encola nada")
revisar(eventos_de(c)[0]["datos"].get("ticket_pendiente") is None,
        "y sin ticket no avisa de ninguno")

# La misma transicion reintentada no encola dos veces.
c = conversacion(caso_id=str(uuid.uuid4()))
clave_sync = f"b6sync-{uuid.uuid4()}"
T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro",
           clave=clave_sync)
T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro",
           clave=clave_sync)
revisar(len(sincronizaciones(c)) == 1,
        f"un reintento de la misma transicion encola UNA vez ({len(sincronizaciones(c))})",
        "La clave sale del evento que la origino (§3.6).")

# Y no hay HTTP dentro de la transaccion (X23).
fuente_t = (RAIZ / "nucleo" / "relevo" / "transiciones.py").read_text(encoding="utf-8")
cuerpo_cerrar = fuente_t[fuente_t.index("def cerrar("):fuente_t.index("def resolver(")]
codigo_cerrar = "\n".join(l for l in cuerpo_cerrar.splitlines()
                          if not l.strip().startswith("#"))
for prohibido in ("requests", "herramientas_http", "ejecutor_http",
                  "cerrar_ticket"):
    revisar(prohibido not in codigo_cerrar,
            f"y no hay ningun '{prohibido}' dentro de la transaccion",
            "Una TX abierta esperando una operacion externa deja la fila "
            "bloqueada y la sesion 'idle in transaction' tras el pooler (X23).")


# =============================================================================
titulo("7. atomico, idempotente y de una empresa sola")
# =============================================================================
c = conversacion()
antes = fila_de(c)
T._gancho_antes_del_commit = lambda: (_ for _ in ()).throw(RuntimeError("falla"))
try:
    T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro")
    revisar(False, "si algo falla antes del commit, el cierre entero se deshace")
except Exception:
    revisar(True, "si algo falla antes del commit, el cierre entero se deshace")
finally:
    T._gancho_antes_del_commit = None
revisar(fila_de(c) == antes, "la conversacion sigue exactamente como estaba",
        "Nunca una conversacion cerrada sin que se sepa por que.")
revisar(eventos_de(c) == [], "y no quedo ningun evento suelto")

c = conversacion()
a = accion(c, "pendiente")
T._gancho_antes_del_commit = lambda: (_ for _ in ()).throw(RuntimeError("falla"))
try:
    T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro")
except Exception:
    pass
finally:
    T._gancho_antes_del_commit = None
revisar(admin.execute("select estado from asistente.acciones_propuestas where id = %s",
                      (a,)).fetchone()["estado"] == "pendiente",
        "y la accion tampoco quedo cancelada por un cierre que no ocurrio")

# Misma clave, dos veces.
c = conversacion()
clave = f"b6-{uuid.uuid4()}"
r1 = T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP,
                desenlace="wifi_cliente", clave=clave)
r2 = T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP,
                desenlace="wifi_cliente", clave=clave)
revisar(r1.aplicada and not r2.aplicada, "la misma clave cierra UNA vez")
revisar(len(eventos_de(c)) == 1, f"un solo evento ({len(eventos_de(c))})")
revisar(fila_de(c)["relevo_version"] == 2, "y una sola version")

# Ya cerrada.
r3 = T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="otro")
revisar(not r3.aplicada and r3.motivo == "ya_cerrada",
        f"una ya cerrada responde 'ya_cerrada' ({r3.motivo})")
revisar(fila_de(c)["desenlace_codigo"] == "wifi_cliente",
        "y conserva el desenlace que se eligio la primera vez",
        "No se pisa la decision de otra persona.")

# Dos operadores a la vez.
c = conversacion()
resultados = []
barrera = threading.Barrier(2)


def cerrar_en_hilo(codigo):
    def _():
        barrera.wait()
        try:
            resultados.append(T.resolver(TEN, c, operador_id=str(uuid.uuid4()),
                                         operador_nombre=f"Op {codigo}",
                                         desenlace=codigo))
        except Exception as e:
            resultados.append(e)
    return _


hilos = [threading.Thread(target=cerrar_en_hilo("facturacion")),
         threading.Thread(target=cerrar_en_hilo("equipo_cliente"))]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
aplicadas = [x for x in resultados if not isinstance(x, Exception) and x.aplicada]
revisar(len(aplicadas) == 1,
        f"de dos operadores cerrando a la vez, gana UNO ({len(aplicadas)})")
revisar(len(eventos_de(c)) == 1, "con un solo evento")
f = fila_de(c)
revisar(f["desenlace_codigo"] in ("facturacion", "equipo_cliente")
        and f["relevo_version"] == 2,
        "y un solo desenlace, el del que gano")

# Otra empresa.
otra_org, otro_ten = uuid.uuid4(), f"prueba-b6b-{uuid.uuid4().hex[:8]}"
sembrar_org(otra_org, otro_ten)
try:
    c = conversacion()
    antes = fila_de(c)
    r = T.resolver(otro_ten, c, operador_id=OP_ID, operador_nombre=OP,
                   desenlace="otro")
    revisar(not r.aplicada, f"otra empresa no puede cerrar esta ({r.motivo})")
    revisar(fila_de(c) == antes, "y la conversacion no cambia")
finally:
    admin.execute("delete from public.organization where id = %s", (str(otra_org),))


# =============================================================================
titulo("8. legado: se cierra, pero no entra al modelo por la puerta de atras")
# =============================================================================
c = conversacion(relevo_version=0, escalada_a_humano=True,
                 necesita_atencion_humana=True, tomada_por="Luis Paz")
r = T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP,
               desenlace="resuelto_por_cliente")
f = fila_de(c)
revisar(r.aplicada and f["estado"] == "cerrada", "una de legado se cierra")
revisar(f["desenlace_codigo"] == "resuelto_por_cliente",
        "y el desenlace se guarda igual",
        "Es un dato de la conversacion, no del relevo: descartarlo seria "
        "tirar lo que la persona acaba de decir.")
revisar(f["relevo_version"] == 0 and eventos_de(c) == [],
        "pero NO sube de version ni deja evento",
        "Adoptar una conversacion de version 0 es una decision humana "
        "explicita (C5, I21): no puede pasar por el efecto lateral de un "
        "boton de cerrar. Para eso esta G8.")


# =============================================================================
titulo("9. G8: la tercera decision pasa por la transicion real")
# =============================================================================
revisar("cerrar_con_desenlace" in T.DECISIONES_G8_IMPLEMENTADAS,
        "'cerrar_con_desenlace' ya se puede registrar")

c = conversacion(relevo_version=0, escalada_a_humano=True,
                 necesita_atencion_humana=True, tomada_por="Luis Paz")
r = T.adoptar_de_legado(TEN, c, decision="cerrar_con_desenlace",
                        operador_id=OP_ID, operador_nombre=OP,
                        desenlace="falso_positivo_ia",
                        nota="no era una falla")
f = fila_de(c)
revisar(r.aplicada and f["relevo_version"] == 1,
        f"adopta y sube la version a 1 ({f['relevo_version']})")
revisar(f["estado"] == "cerrada" and f["cerrada_por_tipo"] == "operador"
        and str(f["cerrada_por_usuario_id"]) == OP_ID,
        "cierra como cierre manual, con su responsable")
revisar(f["desenlace_codigo"] == "falso_positivo_ia"
        and f["desenlace_categoria_base"] == "falso_positivo_ia"
        and f["desenlace_nota"] == "no era una falla",
        "con el codigo, su categoria y la nota")
evs = eventos_de(c)
d = evs[0]["datos"]
revisar([e["tipo"] for e in evs] == ["cerrada"], "deja un evento 'cerrada'")
revisar(d.get("legado") is True and d.get("g8") == "cerrar_con_desenlace"
        and d.get("desenlace") == "falso_positivo_ia",
        f"con legado, g8 y el desenlace ({d})",
        "Sin 'legado' y 'g8' nadie podria distinguir, dentro de un año, un "
        "cierre normal de una decision de la revision de G8.")

c = conversacion(relevo_version=0)
antes = fila_de(c)
try:
    T.adoptar_de_legado(TEN, c, decision="cerrar_con_desenlace",
                        operador_id=OP_ID, operador_nombre=OP)
    revisar(False, "sin codigo NO cierra, ni siquiera por G8")
except ValueError:
    revisar(True, "sin codigo NO cierra, ni siquiera por G8")
revisar(fila_de(c) == antes, "y la conversacion no se toco",
        "Que sea vieja no la hace menos de un cliente.")

try:
    T.adoptar_de_legado(TEN, c, decision="seguir_humano", operador_id=OP_ID,
                        operador_nombre=OP, desenlace="otro")
    revisar(False, "las otras decisiones NO aceptan desenlace")
except ValueError:
    revisar(True, "las otras decisiones NO aceptan desenlace")

try:
    T.adoptar_de_legado(TEN, conversacion(relevo_version=0),
                        decision="resolver_estado_externo",
                        operador_id=OP_ID, operador_nombre=OP)
    revisar(False, "'resolver_estado_externo' SIGUE bloqueada")
except NotImplementedError as e:
    revisar("efecto externo" in str(e) or "B4" in str(e),
            "'resolver_estado_externo' SIGUE bloqueada, con su motivo")


# =============================================================================
titulo("10. completar el desenlace despues del cierre (§3.5)")
# =============================================================================
# La frase del contrato que hasta hoy no tenia transicion: los cierres por el
# cliente y por inactividad dejan NULL "y se completan despues si una persona
# revisa".
c = conversacion(atendida_manual=True)
T.cerrar(TEN, c, por="cliente")
antes = fila_de(c)
revisar(antes["desenlace_codigo"] is None, "una cerrada por el cliente no tiene desenlace")

r = T.completar_desenlace(TEN, c, desenlace="equipo_cliente",
                          operador_id=OP_ID, operador_nombre=OP,
                          nota="era la ONT, se reemplazo")
f = fila_de(c)
revisar(r.aplicada and f["desenlace_codigo"] == "equipo_cliente"
        and f["desenlace_categoria_base"] == "equipo_cliente",
        "una persona se lo completa despues, con su categoria")
revisar(f["desenlace_nota"] == "era la ONT, se reemplazo", "y su nota")
revisar(f["estado"] == "cerrada", "NO reabre la conversacion")
revisar(f["cerrada_por_tipo"] == "cliente",
        f"y NO cambia quien la cerro ({f['cerrada_por_tipo']})",
        "La cerro el cliente. Completar el desenlace despues no convierte a "
        "quien revisa en el que cerro, y confundirlo rompe cualquier metrica "
        "de 'cuantas cerro el cliente solo'.")
revisar(f["cerrada_por_usuario_id"] is None,
        "ni le pone un usuario al cierre ajeno")
revisar(f["control"] == antes["control"]
        and f["asignada_a_usuario_id"] == antes["asignada_a_usuario_id"],
        "no toca el control ni la asignacion")
revisar(f["relevo_version"] == antes["relevo_version"] + 1,
        "la version sube: esto SI cambia algo durable")

evs = eventos_de(c)
revisar([e["tipo"] for e in evs] == ["cerrada", "desenlace_completado"],
        f"deja un evento propio, no un segundo 'cerrada' ({[e['tipo'] for e in evs]})",
        "Dos eventos 'cerrada' en el mismo expediente se leerian como dos "
        "cierres, y esto no vuelve a cerrar nada.")
d = evs[1]["datos"]
revisar(d.get("desenlace") == "equipo_cliente" and d.get("categoria") == "equipo_cliente"
        and d.get("cerrada_por") == "cliente",
        f"con el codigo, la categoria y sobre que cierre se completo ({d})")
revisar(evs[1]["actor_nombre"] == OP and str(evs[1]["actor_usuario_id"]) == OP_ID,
        "y quien lo completo")

# --- una sola vez ---------------------------------------------------------
antes = fila_de(c)
r2 = T.completar_desenlace(TEN, c, desenlace="facturacion",
                           operador_id=str(uuid.uuid4()), operador_nombre="Otro")
revisar(not r2.aplicada and r2.motivo == "ya_completado",
        f"un segundo intento responde 'ya_completado' ({r2.motivo})")
revisar(fila_de(c)["desenlace_codigo"] == "equipo_cliente",
        "sin pisar el que ya estaba",
        "Pisar el de otra persona convertiria esto en una via silenciosa para "
        "reescribir el pasado, que es lo contrario de para que existe.")
revisar(len(eventos_de(c)) == 2, "y sin escribir otro evento")
revisar(fila_de(c)["relevo_version"] == antes["relevo_version"],
        "ni subir la version")

# Tampoco sobre una que se cerro CON desenlace.
c = conversacion()
T.resolver(TEN, c, operador_id=OP_ID, operador_nombre=OP, desenlace="red_central")
r = T.completar_desenlace(TEN, c, desenlace="otro", operador_id=OP_ID,
                          operador_nombre=OP)
revisar(not r.aplicada and r.motivo == "ya_completado",
        "un cierre manual ya trae desenlace: no se completa")
revisar(fila_de(c)["desenlace_codigo"] == "red_central", "y se conserva")

# Ni sobre el del plazo, que lo puso la plataforma.
c = conversacion()
T.cerrar(TEN, c, por="plazo")
T.completar_desenlace(TEN, c, desenlace="otro", operador_id=OP_ID,
                      operador_nombre=OP)
revisar(fila_de(c)["desenlace_codigo"] == "sin_respuesta_cliente",
        "el desenlace del plazo tampoco se pisa")

# --- una abierta se cierra, no se completa --------------------------------
c = conversacion()
antes = fila_de(c)
r = T.completar_desenlace(TEN, c, desenlace="otro", operador_id=OP_ID,
                          operador_nombre=OP)
revisar(not r.aplicada and r.motivo == "no_esta_cerrada",
        f"una conversacion ABIERTA no se completa ({r.motivo})")
revisar(fila_de(c) == antes, "y no se toca")

# --- el actor es obligatorio ----------------------------------------------
c = conversacion(atendida_manual=True)
T.cerrar(TEN, c, por="cliente")
for oid, onombre, caso in ((OP_ID, "", "sin nombre"), ("", OP, "sin id"),
                           ("no-es-uuid", OP, "con un id que no es uuid")):
    antes = fila_de(c)
    try:
        T.completar_desenlace(TEN, c, desenlace="otro", operador_id=oid,
                              operador_nombre=onombre)
        revisar(False, f"se rechaza completar {caso}")
    except Exception:
        revisar(True, f"se rechaza completar {caso}")
    revisar(fila_de(c) == antes, f"y no cambia nada ({caso})")

# --- el codigo tiene que estar VISIBLE ------------------------------------
for codigo, caso in (("inventado", "un codigo que no existe"),
                     ("", "sin codigo")):
    try:
        T.completar_desenlace(TEN, c, desenlace=codigo, operador_id=OP_ID,
                              operador_nombre=OP)
        revisar(False, f"se rechaza completar con {caso}")
    except ValueError:
        revisar(True, f"se rechaza completar con {caso}")
try:
    T.completar_desenlace(TEN, c, desenlace="facturacion", operador_id=OP_ID,
                          operador_nombre=OP, config=_Config([], ["facturacion"]))
    revisar(False, "se rechaza completar con un codigo que la empresa oculto")
except ValueError:
    revisar(True, "se rechaza completar con un codigo que la empresa oculto",
            "Lo elige una persona: tiene que estar en la lista que esa persona "
            "ve hoy.")
revisar(fila_de(c)["desenlace_codigo"] is None,
        "y despues de los cuatro rechazos sigue sin desenlace")

# --- rollback -------------------------------------------------------------
antes = fila_de(c)
T._gancho_antes_del_commit = lambda: (_ for _ in ()).throw(RuntimeError("falla"))
try:
    T.completar_desenlace(TEN, c, desenlace="otro", operador_id=OP_ID,
                          operador_nombre=OP)
    revisar(False, "si falla el evento, el desenlace no queda escrito")
except Exception:
    revisar(True, "si falla el evento, el desenlace no queda escrito")
finally:
    T._gancho_antes_del_commit = None
revisar(fila_de(c) == antes, "la conversacion sigue exactamente como estaba")

# --- dos revisores a la vez -----------------------------------------------
c = conversacion(atendida_manual=True)
T.cerrar(TEN, c, por="cliente")
resultados = []
barrera = threading.Barrier(2)


def completar_en_hilo(codigo):
    def _():
        barrera.wait()
        try:
            resultados.append(T.completar_desenlace(
                TEN, c, desenlace=codigo, operador_id=str(uuid.uuid4()),
                operador_nombre=f"Rev {codigo}"))
        except Exception as e:
            resultados.append(e)
    return _


hilos = [threading.Thread(target=completar_en_hilo("wifi_cliente")),
         threading.Thread(target=completar_en_hilo("configuracion"))]
for h in hilos:
    h.start()
for h in hilos:
    h.join()
aplicadas = [x for x in resultados if not isinstance(x, Exception) and x.aplicada]
revisar(len(aplicadas) == 1,
        f"de dos revisores a la vez, gana UNO ({len(aplicadas)})",
        "El candado esta en el UPDATE ('and desenlace_codigo is null'), no en "
        "una lectura previa.")
revisar([e["tipo"] for e in eventos_de(c)].count("desenlace_completado") == 1,
        "con un solo evento")

# --- otra empresa ---------------------------------------------------------
otra_org, otro_ten = uuid.uuid4(), f"prueba-b6c-{uuid.uuid4().hex[:8]}"
sembrar_org(otra_org, otro_ten)
try:
    c = conversacion(atendida_manual=True)
    T.cerrar(TEN, c, por="cliente")
    antes = fila_de(c)
    r = T.completar_desenlace(otro_ten, c, desenlace="otro", operador_id=OP_ID,
                              operador_nombre=OP)
    revisar(not r.aplicada, f"otra empresa no puede completarla ({r.motivo})")
    revisar(fila_de(c) == antes, "y la conversacion no cambia")
finally:
    admin.execute("delete from public.organization where id = %s", (str(otra_org),))

# --- legado ---------------------------------------------------------------
c = conversacion(relevo_version=0, atendida_manual=True)
T.cerrar(TEN, c, por="cliente")
r = T.completar_desenlace(TEN, c, desenlace="otro", operador_id=OP_ID,
                          operador_nombre=OP)
f = fila_de(c)
revisar(r.aplicada and f["desenlace_codigo"] == "otro",
        "una de legado tambien se puede completar")
revisar(f["relevo_version"] == 0 and eventos_de(c) == [],
        "pero NO sube de version ni deja evento",
        "Subirla meteria al modelo una conversacion de version 0 por la puerta "
        "de atras, y esa puerta es G8 y ninguna otra (C5, I21).")

# --- no toca nada de afuera -----------------------------------------------
# La cuenta se toma sobre ESTA conversacion y alrededor de la completada
# sola: el cierre previo si encola 'cerrar_caso', y medir sobre la empresa
# entera haria que este numero hablara del cierre y no de lo que se prueba.
c = conversacion(atendida_manual=True, caso_id=str(uuid.uuid4()),
                 ticket_operativo="90355")
T.cerrar(TEN, c, por="cliente")
antes_sync = sincronizaciones(c)
T.completar_desenlace(TEN, c, desenlace="facturacion", operador_id=OP_ID,
                      operador_nombre=OP)
revisar(sincronizaciones(c) == antes_sync,
        f"completar no encola ningun efecto externo ({len(antes_sync)} antes y despues)",
        "Escribir un codigo en una fila no cambia nada en el CRM ni en "
        "WispHub. Hacerlo de paso seria mover sistemas de afuera desde una "
        "pantalla de estadistica.")

cuerpo_completar = fuente_t[fuente_t.index("def completar_desenlace("):]
codigo_completar = "\n".join(l for l in cuerpo_completar.splitlines()
                             if not l.strip().startswith("#"))
for prohibido in ("encolar_sincronizacion", "estado = 'abierta'",
                  "cerrada_por_tipo ="):
    revisar(prohibido not in codigo_completar,
            f"y no hay ningun '{prohibido}' escondido")


# =============================================================================
titulo("11. la base tambien lo sostiene")
# =============================================================================
c = conversacion()
try:
    admin.execute("update asistente.conversations set desenlace_codigo = 'otro' "
                  "where id = %s", (c,))
    revisar(False, "una conversacion ABIERTA no puede tener desenlace")
except psycopg.errors.CheckViolation:
    revisar(True, "una conversacion ABIERTA no puede tener desenlace",
            "Una abierta con desenlace no significa nada y no deberia poder "
            "existir.")

for sql, que in (
    ("update asistente.conversations set estado='cerrada', "
     "desenlace_codigo='otro' where id = %s",
     "un codigo sin categoria se rechaza"),
    ("update asistente.conversations set estado='cerrada', "
     "cerrada_por_tipo='inventado' where id = %s",
     "un 'cerrada_por_tipo' fuera de los cinco se rechaza"),
    ("update asistente.conversations set estado='cerrada', "
     "cerrada_por_tipo='plazo', cerrada_por_usuario_id=gen_random_uuid() "
     "where id = %s",
     "un usuario en un cierre que no es de operador se rechaza"),
):
    c = conversacion()
    try:
        admin.execute(sql, (c,))
        revisar(False, que)
    except psycopg.errors.CheckViolation:
        revisar(True, que)


admin.execute("delete from public.organization where id = %s", (str(ORG),))
print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  todo en verde.")
