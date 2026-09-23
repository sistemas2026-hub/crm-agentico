# -*- coding: utf-8 -*-
"""
================================================================================
 BATERIA DE FLUJOS  --  20 conversaciones completas, y que AFIRMAN
================================================================================
    py -3.13 cli/bateria_flujos.py rapilink                 # solo los que corren desde aca
    py -3.13 cli/bateria_flujos.py rapilink --todos         # incluye los que necesitan el CRM
    py -3.13 cli/bateria_flujos.py rapilink --caso baja     # uno solo
    py -3.13 cli/bateria_flujos.py rapilink --json informe.json

De donde sale
-------------
De dos huecos que se tocan.

  cli/evaluar.py         llama a motor.responder() DIRECTO. No pasa por
                         atender_turno, asi que no ve nada de lo que vive
                         alrededor del modelo: el reencauzamiento, el control
                         de concurrencia, el embudo de identidad, la sesion
                         entre turnos. Todo eso se construyo a ciegas.
  cli/bateria_tv.py      SI entra por el canal --23 conversaciones completas,
                         y de ahi se copio el patron de abajo-- pero no afirma
                         nada: imprime y dice "la evidencia esta en la base".
                         Un humano tiene que leerla.

Esto es lo del medio: conversaciones de verdad, por el camino de verdad, y con
una afirmacion por caso sobre la TRAZA -- que herramientas corrieron, a que
area derivo, si escalo y con que motivo, que quedo en el embudo de identidad,
que accion quedo propuesta. Nunca sobre la redaccion: el modelo dice lo mismo
de diez formas.

POR QUE HAY CASOS QUE NO CORREN DESDE UNA MAQUINA DE DESARROLLO
---------------------------------------------------------------
17 herramientas del catalogo apuntan a 'http://backend:8000', que es el nombre
de red del compose. Desde afuera no resuelve. Eso incluye crear el caso del
CRM, y por lo tanto todo lo que escala. Medido el 10/09/2026 en bateria_tv: el
fallo NO queda contenido en el caso que escala -- el agente contesta "no pude
dejar registrado tu caso" a mitad de la conversacion y arruina la medicion.

Por eso cada caso declara 'necesita_crm'. Sin --todos se saltean, y se dice
cuantos: una bateria que corre 20 y mide 14 sin avisar miente.

    docker exec <contenedor-motor> python cli/bateria_flujos.py rapilink --todos

SE ENTRA EN EL PROCESO, NO POR HTTP
-----------------------------------
bateria_tv habla por /chat. Aca se llama a atender_turno() directo: es el mismo
camino desde la sesion en adelante --que es lo que hay que cubrir-- sin
necesitar el token de servicio ni un motor escuchando. Lo que NO cubre, y
queda dicho: la capa HTTP y el webhook de Meta.

LOS NUMEROS NO SE REUSAN
------------------------
Cada tanda usa un prefijo nuevo. Reusar un numero arrastra la conversacion
anterior --historial, identidad ya verificada, escalada abierta-- y el caso
mide otra cosa. Es la leccion de la conversacion de produccion del 22/09: con
27 mensajes encima, el mismo mensaje da otro resultado.

CANAL 'whatsapp-simulado' A PROPOSITO
-------------------------------------
Tiene clave de sesion propia (tests/test_chat_canal.py lo prueba), asi que no
toca ninguna conversacion de cliente, y el frontend lo separa por
'canal_operativo': no ensucia la bandeja real. Y a diferencia de 'api',
comparte con WhatsApp la semantica del remitente, que es lo que decide si el
canal cuenta como factor de posesion -- el corazon de los casos con BSUID.

QUE DEJA ATRAS
--------------
Conversaciones, mensajes, traza y --en los casos que las provocan-- acciones
propuestas en estado 'pendiente'. NINGUNA se aprueba: 'reiniciar_ont' corta el
servicio seis minutos y el equipo de laboratorio es uno solo. Si alguien
aprueba en lote lo que dejo una tanda, reinicia una ONT de verdad.
================================================================================
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                           # noqa: E402
from nucleo.config import fuente                                         # noqa: E402
from nucleo.persistencia.db import sesion                                # noqa: E402

CANAL = "whatsapp-simulado"
MAX_TURNOS = 12
CEDULA_OK = "000021"          # el cliente de laboratorio
CEDULA_FANTASMA = "1002003004"

# ── el cliente simulado ─────────────────────────────────────────────────────
#
# Contesta por PATRON lo que el agente pregunta, igual que bateria_tv. Las
# respuestas de identidad y las del checklist se dan SIEMPRE y no gastan una
# linea del guion: si el guion tuviera que preverlas, cada caso repetiria lo
# mismo y un cambio de protocolo los rompería todos a la vez.
IDENTIDAD = [
    (r"c[eé]dula|documento|n[uú]mero de identificaci|dni", "__CEDULA__"),
    (r"eres t[uú]|figura a nombre|confirmas que|sos vos|es correcto", "Si, soy yo."),
]
CHECKLIST = [
    (r"cu[aá]ntos televisores|cu[aá]ntos TV", "Uno solo."),
    (r"splitter", "No, es uno solo."),
    (r"cableado|qui[eé]n.*instal|lo puso", "Lo puso la empresa cuando instalaron."),
    (r"enroscad|ajustad|flojo|bien puesto", "Si, esta bien enroscado."),
    (r"luces|led", "El equipo tiene la luz verde encendida."),
    (r"reiniciaste|desconectaste|apagaste", "Si, ya lo desconecte y lo volvi a conectar."),
]


def entorno() -> tuple[str, str]:
    """
    (etiqueta, explicacion) de donde se esta corriendo. Se MIDE, no se declara.

    La diferencia no es cosmetica: desde una maquina de desarrollo las 17
    herramientas que apuntan a 'http://backend:8000' no resuelven, y ademas el
    interprete no tiene las dependencias de la imagen -- en la primera tanda
    salio 'ModuleNotFoundError: anthropic' (que SI esta en requirements.txt) y
    por un momento se leyo como un fallo de produccion. Un informe que no dice
    donde corrio invita a esa confusion cada vez.

    Se comprueba resolviendo el nombre de red del compose, que es exactamente
    lo que decide si los casos con CRM pueden correr.
    """
    import socket
    try:
        socket.getaddrinfo("backend", 8000)
        return ("CONTENEDOR", "'backend' resuelve: las herramientas del CRM funcionan")
    except OSError:
        return ("LOCAL", "'backend' no resuelve: las herramientas del CRM no salen, "
                         "y las dependencias son las de esta maquina, no las de la imagen")


def caso(num, nombre, apertura, reglas, espera, necesita_crm=False, cedula=CEDULA_OK):
    return dict(num=num, nombre=nombre, apertura=apertura, reglas=reglas,
                espera=espera, necesita_crm=necesita_crm, cedula=cedula)


# 'espera' afirma sobre la traza. Claves:
#   usa / no_usa       herramientas que tienen (o no) que haber corrido
#   deriva_a           rol al que debio pasar la conversacion
#   escala             True/False -- si tenia que terminar con una persona
#   escala_motivo      el motivo exacto, cuando el caso lo determina
#   caso               'caso_manual' con el que debe quedar clasificada
#   propone            herramienta que debe quedar en acciones_propuestas
#   identidad          etapas que deben aparecer en el embudo
CASOS = [
    # ── identidad y derivacion: el bug del 22/09 y su familia ──────────────
    caso("CO.9000000000000001", "baja desde un remitente sin telefono",
         "Buenas, quiero dar de baja el servicio",
         [(None, "Ya no lo necesito.")],
         {"usa": ["derivar_a_area"], "deriva_a": "facturacion_cliente",
          "caso": "baja_servicio"}),

    caso("CO.9000000000000002", "sin internet desde un remitente sin telefono",
         "No tengo internet desde ayer",
         [(None, "Sigue sin funcionar.")],
         {"usa": ["derivar_a_area"], "deriva_a": "soporte_tecnico_cliente"}),

    caso("CO.9000000000000003", "la cedula la pide el area, no el router",
         "quiero saber cuanto debo",
         [(None, "Gracias.")],
         {"usa": ["derivar_a_area", "verificar_identidad_por_cedula"],
          "deriva_a": "facturacion_cliente",
          "identidad": ["verificacion_ok"]}),

    caso("CO.9000000000000004", "el router NO tiene con que verificar",
         "necesito hablar de mi factura",
         [(None, "Si.")],
         {"no_usa_rol": {"cliente_final": ["verificar_identidad_por_cedula",
                                           "confirmar_identidad"]}}),

    caso("573900000005", "prospecto: ventas no pide cedula",
         "Hola, que planes de internet tienen?",
         [(None, "Gracias, lo voy a pensar.")],
         {"usa": ["derivar_a_area"], "deriva_a": "ventas",
          "no_usa": ["verificar_identidad_por_cedula"]}),

    caso("573900000006", "una cedula que no existe no entrega datos",
         "quiero ver mi saldo",
         [(None, "Mi cedula es 1002003004")],
         {"usa": ["verificar_identidad_por_cedula"],
          "no_usa": ["confirmar_identidad"],
          "identidad": ["verificacion_fallo"],
          "responde_sin": ["0.00", "SABANAGRANDE"]},
         cedula=CEDULA_FANTASMA),

    # ── diagnostico tecnico ────────────────────────────────────────────────
    caso("573900000007", "sin internet: mide antes de opinar",
         "no tengo internet",
         [(None, "Sigue igual.")],
         {"deriva_a": "soporte_tecnico_cliente",
          "usa": ["consultar_estado_ont"], "caso": "no_internet"}),

    caso("573900000008", "internet lento mira la estabilidad, no solo el ahora",
         "el internet me anda lentisimo desde hace dias",
         [(None, "Sobre todo en las noches.")],
         {"deriva_a": "soporte_tecnico_cliente", "caso": "internet_lento"}),

    caso("573900000009", "un reporte ambiguo no elige servicio por su cuenta",
         "no me funciona nada",
         [(None, "Eso.")],
         {"no_usa": ["reiniciar_ont"]}),

    caso("573900000010", "un numero suelto no dispara un diagnostico",
         "3001234567",
         [(None, "Nada mas.")],
         {"no_usa": ["ping_cliente", "consultar_estado_ont", "reiniciar_ont"]}),

    # LA REGLA ES TEMPORAL, NO ABSOLUTA, y la primera version de este caso la
    # escribio mal: afirmaba "un insulto nunca escala" y mandaba DOS mensajes.
    # El sistema escalo en el segundo -- que es lo correcto -- y la bateria lo
    # marco rojo. El defecto estaba en la expectativa, no en la conducta. Por
    # eso ahora son dos casos, cada uno afirmando una sola cosa.
    caso("573900000011", "un insulto NO escala en el primer mensaje",
         "esto es una porqueria",
         [],                                   # un solo mensaje, a proposito
         {"no_usa": ["ping_cliente", "consultar_estado_ont", "reiniciar_ont"],
          "escala": False}),

    caso("573900000011b", "y si insiste sin decir que falla, SI pasa a una persona",
         "esto es una porqueria",
         [(None, "Ya te dije, no sirve para nada."),
          (None, "Es una estafa.")],
         {"escala": True}),

    caso("573900000012", "sin senal de TV usa la guia, no improvisa",
         "no me aparecen los canales del televisor",
         [(r"marca|televisor", "Samsung."),
          (None, "El coaxial va directo al televisor."),
          (None, "Ya hice la busqueda y aparecieron.")],
         {"deriva_a": "soporte_tecnico_cliente", "caso": "sin_senal_tv"}),

    caso("573900000013", "cambio de clave del WiFi",
         "quiero cambiar la clave de mi wifi",
         [(None, "La nueva seria Rapilink2026."),
          (None, "Si, confirmo.")],
         {"deriva_a": "soporte_tecnico_cliente", "caso": "cambio_wifi"}),

    # ── ventas y catalogo ──────────────────────────────────────────────────
    caso("573900000014", "un canal se consulta en la parrilla, no se adivina",
         "tienen el canal ESPN?",
         [(None, "Gracias.")],
         {"deriva_a": "ventas"}),

    caso("573900000015", "un servicio que no se ofrece igual deriva a ventas",
         "quiero contratar telefonia fija",
         [(None, "Entiendo.")],
         {"usa": ["derivar_a_area"], "deriva_a": "ventas"}),

    # ── facturacion ────────────────────────────────────────────────────────
    caso("573900000016", "consulta de factura",
         "me pueden decir cuando vence mi factura?",
         [(None, "Gracias.")],
         {"deriva_a": "facturacion_cliente"}),

    caso("573900000017", "reconexion tras el pago",
         "ya pague, cuando me reconectan?",
         [(None, "Lo pague ayer.")],
         {"deriva_a": "facturacion_cliente"}),

    # ── conducta general ───────────────────────────────────────────────────
    caso("573900000018", "un mensaje de otro negocio no arranca un tramite",
         "hola, vendes repuestos de moto?",
         [(None, "Ah bueno, gracias.")],
         {"no_usa": ["derivar_a_area", "registrar_solicitud_servicio"]}),

    # ── los que necesitan el CRM ───────────────────────────────────────────
    caso("573900000019", "pedir una persona escala con su motivo",
         "quiero hablar con una persona",
         [(None, "Si, por favor.")],
         {"escala": True, "escala_motivo": "solicitud_explicita"},
         necesita_crm=True),

    caso("573900000020", "un traslado no lo resuelve el asistente",
         "me voy a mudar de casa y necesito llevarme el servicio",
         [(None, "A otro barrio, el mes que viene.")],
         {"escala": True},
         necesita_crm=True),
]


def _responde(c, usadas, texto):
    """Que contesta el cliente simulado a lo ultimo que dijo el agente."""
    t = texto or ""
    for patron, resp in IDENTIDAD:
        if re.search(patron, t, re.I):
            return c["cedula"] if resp == "__CEDULA__" else resp
    for patron, resp in CHECKLIST:
        if re.search(patron, t, re.I):
            return resp
    for i, (patron, resp) in enumerate(c["reglas"]):
        if i in usadas:
            continue
        if patron is None or re.search(patron, t, re.I):
            usadas.add(i)
            return resp
    return None


def _traza(tenant: str, conversacion_id: str) -> dict:
    """Lo que quedo en la base, que es lo unico sobre lo que se afirma."""
    if not conversacion_id:
        return {"herramientas": [], "identidad": [], "acciones": [], "conv": {}}
    with sesion(tenant) as (cur, _org):
        cur.execute("""select herramienta, rol_solicitante, exito, codigo_error, es_bloqueo
                       from asistente.tool_calls where conversation_id = %s
                       order by creado_en""", (conversacion_id,))
        herramientas = [dict(r) for r in cur.fetchall()]
        cur.execute("""select etapa, motivo, siguiente_paso from asistente.identidad_eventos
                       where conversation_id = %s order by creado_en""", (conversacion_id,))
        identidad = [dict(r) for r in cur.fetchall()]
        cur.execute("""select herramienta, estado from asistente.acciones_propuestas
                       where conversation_id = %s order by creado_en""", (conversacion_id,))
        acciones = [dict(r) for r in cur.fetchall()]
        cur.execute("""select escalada_a_humano, motivo_escalamiento, caso_manual,
                              etiqueta, estado_escalada
                       from asistente.conversations where id = %s""", (conversacion_id,))
        fila = cur.fetchone()
    return {"herramientas": herramientas, "identidad": identidad,
            "acciones": acciones, "conv": dict(fila) if fila else {}}


def _juzgar(c, traza, dicho: str) -> list[str]:
    """Las fallas de este caso. Lista vacia = paso."""
    e = c["espera"]
    fallas = []
    usadas = [h["herramienta"] for h in traza["herramientas"]]
    conv = traza["conv"]

    for herr in e.get("usa") or []:
        if herr not in usadas:
            fallas.append(f"usa: nunca llamo '{herr}' (corrieron: {usadas or 'ninguna'})")
    for herr in e.get("no_usa") or []:
        if herr in usadas:
            fallas.append(f"no_usa: llamo '{herr}' y no debia")
    for rol, prohibidas in (e.get("no_usa_rol") or {}).items():
        for h in traza["herramientas"]:
            if h["rol_solicitante"] == rol and h["herramienta"] in prohibidas:
                fallas.append(f"no_usa_rol: '{rol}' llamo '{h['herramienta']}'")

    if "deriva_a" in e:
        # Quien ATIENDE al final se ve en el rol que ejecuto las herramientas:
        # 'rol_siguiente' de la sesion se arrastra entre turnos a proposito
        # (nucleo/modelo/motor.py) y mentiria sobre este caso.
        roles = {h["rol_solicitante"] for h in traza["herramientas"]}
        if e["deriva_a"] not in roles:
            fallas.append(f"deriva_a: esperaba '{e['deriva_a']}', "
                          f"atendieron {sorted(roles) or 'nadie'}")

    if "escala" in e and bool(conv.get("escalada_a_humano")) != bool(e["escala"]):
        fallas.append(f"escala: esperaba {e['escala']} y fue "
                      f"{bool(conv.get('escalada_a_humano'))}")
    if e.get("escala_motivo") and conv.get("motivo_escalamiento") != e["escala_motivo"]:
        fallas.append(f"escala_motivo: esperaba '{e['escala_motivo']}' y fue "
                      f"'{conv.get('motivo_escalamiento')}'")
    if e.get("caso") and conv.get("caso_manual") != e["caso"]:
        fallas.append(f"caso: esperaba '{e['caso']}' y fue '{conv.get('caso_manual')}'")

    for etapa in e.get("identidad") or []:
        if etapa not in [x["etapa"] for x in traza["identidad"]]:
            fallas.append(f"identidad: falta la etapa '{etapa}' en el embudo")

    if e.get("propone"):
        propuestas = [a["herramienta"] for a in traza["acciones"]]
        if e["propone"] not in propuestas:
            fallas.append(f"propone: '{e['propone']}' no quedo propuesta")

    for prohibida in e.get("responde_sin") or []:
        if prohibida.lower() in (dicho or "").lower():
            fallas.append(f"responde_sin: la respuesta dice '{prohibida}'")

    # SIEMPRE, sin declararlo: ninguna accion con efecto puede quedar EJECUTADA.
    # El equipo de laboratorio es uno solo y un reinicio corta seis minutos.
    for a in traza["acciones"]:
        if a["estado"] not in ("pendiente", "rechazada", "cancelada", "vencida"):
            fallas.append(f"SEGURIDAD: '{a['herramienta']}' quedo '{a['estado']}', "
                          f"no 'pendiente'")
    return fallas


def correr(tenant: str, casos: list[dict], verboso: bool) -> list[dict]:
    cargada = fuente.desde_base(tenant)
    if not cargada:
        sys.exit(f"'{tenant}' no tiene configuracion cargada en la base.")
    config, version = cargada
    donde, por_que = entorno()
    print(f"Bateria de flujos -- {len(casos)} casos, tenant '{tenant}', config v{version}")
    print(f"ENTORNO: {donde}  ({por_que})")
    print(f"Canal '{CANAL}' (no toca la bandeja real). Cedula de laboratorio: {CEDULA_OK}\n")

    resultados = []
    for n, c in enumerate(casos, 1):
        # Numero nuevo por tanda: reusarlo arrastra la conversacion anterior.
        num = f"{c['num']}-{uuid.uuid4().hex[:6]}" if c["num"].startswith("57") else c["num"]
        if c["num"].startswith("CO."):
            num = f"CO.{uuid.uuid4().int % 10**16:016d}"
        api._sesiones.clear()

        usadas, mensaje, dicho = set(), c["apertura"], ""
        print(f"[{n:>2}/{len(casos)}] {c['nombre']}", flush=True)
        for _ in range(MAX_TURNOS):
            try:
                salida = api.atender_turno(config, tenant, "cliente_final", num,
                                           mensaje, CANAL)
            except Exception as ex:
                dicho = ""
                print(f"        ERROR: {type(ex).__name__}: {ex}", flush=True)
                break
            dicho = (salida or {}).get("respuesta", "") or ""
            if verboso:
                print(f"        [cli] {mensaje[:88]}")
                print(f"        [age] {dicho[:140]}")
            siguiente = _responde(c, usadas, dicho)
            if siguiente is None:
                break
            mensaje = siguiente

        estado = api._sesiones.get((tenant, CANAL, num)) or {}
        traza = _traza(tenant, estado.get("conversacion_id"))
        fallas = _juzgar(c, traza, dicho)
        marca = "[ok]  " if not fallas else "[FALLA]"
        print(f"        {marca} herramientas: "
              f"{[h['herramienta'] for h in traza['herramientas']] or 'ninguna'}", flush=True)
        for f in fallas:
            print(f"          -> {f}", flush=True)
        resultados.append({"nombre": c["nombre"], "ok": not fallas, "fallas": fallas,
                           "herramientas": [h["herramienta"] for h in traza["herramientas"]],
                           "identidad": [x["etapa"] for x in traza["identidad"]],
                           "acciones": traza["acciones"], "conv": traza["conv"]})
    return resultados


def main() -> int:
    ap = argparse.ArgumentParser(description="20 conversaciones completas, y que afirman")
    ap.add_argument("tenant")
    ap.add_argument("--todos", action="store_true",
                    help="incluye los casos que necesitan el CRM (solo dentro del contenedor)")
    ap.add_argument("--caso", help="solo los casos cuyo nombre contenga esto")
    ap.add_argument("--verboso", action="store_true", help="imprime cada turno")
    ap.add_argument("--json", help="guarda el informe completo")
    args = ap.parse_args()

    casos = CASOS
    if args.caso:
        casos = [c for c in casos if args.caso.lower() in c["nombre"].lower()]
    salteados = [c for c in casos if c["necesita_crm"]] if not args.todos else []
    if salteados:
        casos = [c for c in casos if not c["necesita_crm"]]

    resultados = correr(args.tenant, casos, args.verboso)

    ok = sum(1 for r in resultados if r["ok"])
    donde, _ = entorno()
    print("\n" + "=" * 70)
    print(f"  {ok}/{len(resultados)} casos OK        [entorno: {donde}]")
    if salteados:
        # Una bateria que corre 20 y mide 14 sin avisar miente.
        print(f"\n  {len(salteados)} caso(s) SALTEADOS: necesitan el CRM, que vive en")
        print("  'http://backend:8000' -- nombre de red del compose, no resuelve desde")
        print("  una maquina de desarrollo. Correr con --todos dentro del contenedor:")
        print("      docker exec <contenedor-motor> python cli/bateria_flujos.py "
              f"{args.tenant} --todos")
        for c in salteados:
            print(f"    - {c['nombre']}")
    pendientes = [a for r in resultados for a in r["acciones"] if a["estado"] == "pendiente"]
    if pendientes:
        print(f"\n  {len(pendientes)} accion(es) quedaron PENDIENTES de aprobacion. "
              f"NO aprobarlas en lote:")
        for a in pendientes:
            print(f"    - {a['herramienta']}")
        print("    'reiniciar_ont' corta el servicio seis minutos y el equipo de "
              "laboratorio es uno solo.")
    print("=" * 70)

    if args.json:
        Path(args.json).write_text(json.dumps(resultados, ensure_ascii=False,
                                              indent=2, default=str), encoding="utf-8")
        print(f"Informe: {args.json}")
    return 0 if ok == len(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
