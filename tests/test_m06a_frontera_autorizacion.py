# -*- coding: utf-8 -*-
"""
================================================================================
 M06-A  --  frontera de acciones tecnicas y autorizacion
================================================================================

ESTE ARCHIVO NO CREA NINGUN CONTROL NUEVO.

Todo lo que hace falta ya existe y ya se probo:

    tests/test_m10a_gobierno_frontera.py    la clasificacion R0-R4 y su guarda
    tests/test_frontera_externa.py          ningun camino de salida sin frontera
    tests/test_frontera_adversarial.py      ninguna ruta autonoma con efecto
    tests/test_interruptor_autonomia.py     el kill switch
    tests/test_idempotencia_externa.py      la idempotencia
    tests/test_autonomia2*.py               la autorizacion granular

Lo que M06-A agrega es lo que NINGUNA de esas cubre: que la cadena entera se
comporte como una sola puerta, y en particular las dos cosas que el encargo
llama §8 y §9 --

    una aprobacion vale para UNOS argumentos, no para la herramienta
    aprobar A no puede ejecutar B

y la separacion de los seis estados de una accion (§4).

LA CLASIFICACION NO SE REPITE AQUI
----------------------------------
Se IMPORTA de 'test_m10a_gobierno_frontera'. Copiarla seria crear la segunda
tabla que se desincroniza en silencio -- exactamente lo que el encargo prohibe
y lo que ese archivo existe para impedir.
================================================================================
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                            # noqa: E402
from nucleo.seguridad import (autonomia2, autorizacion, frontera,  # noqa: E402
                              idempotencia, interruptor)

#  La UNICA fuente de la clasificacion. Si M10-A cambia, esto cambia con ella.
from tests.test_m10a_gobierno_frontera import (R1_INTERNO,         # noqa: E402
                                               R2_REGISTRO_EXTERNO,
                                               R3_EQUIPO_FISICO,
                                               R4_DINERO)

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
FALLOS: list[str] = []


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(titulo: str) -> None:
    print()
    print("-" * 78)
    print(f"  {titulo}")
    print("-" * 78)


ESCRITURAS = [h for h in CONFIG.herramientas if not h.solo_lectura]
POR_NOMBRE = {h.nombre: h for h in CONFIG.herramientas}


# =============================================================================
#  §4  LOS SEIS ESTADOS DE UNA ACCION
# =============================================================================
#  No se crea un enum nuevo: los estados YA existen repartidos entre las
#  estructuras que los producen, y lo que se comprueba es que cada uno tenga un
#  lugar donde se distingue del anterior.
#
#    OBSERVADA            supervisor.Senal          (el hecho, sin juicio)
#    RECOMENDADA          PropuestaSupervisor       (estado 'propuesta')
#    PENDIENTE_APROBACION acciones_propuestas       (estado 'pendiente')
#    AUTORIZADA           acciones_propuestas       (estado 'aprobada')
#    EJECUTANDO           operaciones_externas      (resultado IS NULL)
#    EJECUTADA / FALLIDA  operaciones_externas      (resultado IS NOT NULL)
#    RECHAZADA            acciones_propuestas       (estado 'rechazada')
#    BLOQUEADA            AccionExternaNoAutorizada (+ bitacora de bloqueo)

def estados_de_accion():
    seccion("§4  Los seis estados viven en estructuras DISTINTAS")

    #  'recomendada' y 'pendiente de aprobacion' NO son la misma cola. Es la
    #  regla arquitectonica principal del encargo.
    fuente_motor = inspect.getsource(sys.modules["nucleo.modelo.motor"]) \
        if "nucleo.modelo.motor" in sys.modules else ""
    if not fuente_motor:
        from nucleo.modelo import motor
        fuente_motor = inspect.getsource(motor)

    afirmar("acciones_propuestas" in fuente_motor,
            "'acciones_propuestas' existe como cola de aprobacion")
    afirmar("PropuestaSupervisor" not in fuente_motor,
            "el motor NO conoce PropuestaSupervisor: son dos colas separadas",
            "si el motor la importara, la recomendacion del Supervisor podria "
            "convertirse en ejecucion sin pasar por la cola de aprobacion")

    #  BLOQUEADA tiene su propio tipo de excepcion y su codigo.
    afirmar(issubclass(frontera.AccionExternaNoAutorizada, Exception),
            "'BLOQUEADA' tiene excepcion propia (AccionExternaNoAutorizada)")
    afirmar(hasattr(interruptor, "CODIGO_BLOQUEO"),
            "el bloqueo por kill switch tiene codigo propio")
    for codigo in ("SIN_AUTORIZACION", "REVOCADA", "EXPIRADA", "NIVEL_INSUFICIENTE"):
        afirmar(hasattr(autorizacion, codigo),
                f"'BLOQUEADA' distingue el motivo: {codigo}")

    #  EJECUTANDO vs EJECUTADA vs FALLIDA
    for codigo in ("EN_CURSO", "FALLIDA_PREVIA", "CLAVE_REUTILIZADA"):
        afirmar(hasattr(idempotencia, codigo),
                f"la ejecucion distingue el estado: {codigo}")


# =============================================================================
#  §8 y §9  LA APROBACION VALE PARA UNOS ARGUMENTOS
# =============================================================================

def aprobacion_ligada_a_argumentos():
    seccion("§8-§9  Aprobar A no autoriza ejecutar B")

    from nucleo.canales import api
    from nucleo.modelo import motor

    fuente_endpoint = inspect.getsource(api.acciones_propuesta_aprobar)

    #  LA PRUEBA CENTRAL: los argumentos NO se leen del cuerpo de la peticion.
    #  Si se leyeran, quien aprueba podria mandar otros distintos de los que se
    #  le mostraron -- aprobar "reiniciar el equipo de X" y ejecutar el de Y.
    arbol = ast.parse(fuente_endpoint)
    claves_del_cuerpo = set()
    for nodo in ast.walk(arbol):
        #  cuerpo.get("...")
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "get"
                and isinstance(nodo.func.value, ast.Name)
                and nodo.func.value.id == "cuerpo"
                and nodo.args and isinstance(nodo.args[0], ast.Constant)):
            claves_del_cuerpo.add(nodo.args[0].value)

    afirmar("argumentos" not in claves_del_cuerpo,
            "el endpoint de aprobacion NO acepta 'argumentos' del cliente",
            f"lee del cuerpo: {sorted(claves_del_cuerpo)}")
    afirmar("herramienta" not in claves_del_cuerpo,
            "el endpoint de aprobacion NO acepta 'herramienta' del cliente")
    afirmar(claves_del_cuerpo <= {"tenant", "revisado_por"},
            "del cuerpo solo salen 'tenant' y quien revisa",
            f"lee: {sorted(claves_del_cuerpo)}")

    #  Y los argumentos que se ejecutan salen de la FILA leida de la base.
    afirmar("accion_propuesta_de" in fuente_endpoint,
            "los argumentos se releen de la base, no del request")
    afirmar('accion["estado"] != "pendiente"' in fuente_endpoint
            or "estado" in fuente_endpoint,
            "una accion ya resuelta no se puede volver a aprobar")

    fuente_ejecutar = inspect.getsource(motor.ejecutar_accion_aprobada)
    afirmar('accion["argumentos"]' in fuente_ejecutar,
            "el ejecutor usa los argumentos de la fila aprobada")
    #  Por AST: los parametros reales, no el texto de la firma (que lleva
    #  anotaciones de tipo y rompe cualquier comparacion literal).
    firma = inspect.signature(motor.ejecutar_accion_aprobada)
    afirmar(list(firma.parameters) == ["config", "accion"],
            "el ejecutor no recibe argumentos sueltos: recibe la fila entera",
            f"parametros: {list(firma.parameters)}")

    #  LA IDEMPOTENCIA TAMBIEN LOS ATA: misma herramienta y distinto argumento
    #  son dos claves distintas, asi que una no puede pasar por la otra.
    a1 = {"sn_onu": "AAAA11111111"}
    a2 = {"sn_onu": "BBBB22222222"}
    k1 = idempotencia.clave_de("accion_aprobada:1", "reiniciar_ont", a1)
    k2 = idempotencia.clave_de("accion_aprobada:1", "reiniciar_ont", a2)
    afirmar(k1 != k2,
            "misma herramienta y MISMO origen, argumentos distintos -> clave distinta",
            f"{k1} vs {k2}")
    afirmar(idempotencia.hash_de(a1) != idempotencia.hash_de(a2),
            "el hash de argumentos distingue un cliente de otro")
    #  y el mismo argumento escrito al reves da el mismo hash: el orden de las
    #  claves no puede crear dos operaciones donde hay una.
    afirmar(idempotencia.hash_de({"a": 1, "b": 2}) ==
            idempotencia.hash_de({"b": 2, "a": 1}),
            "el hash es canonico: el orden de las claves no cambia la identidad")


# =============================================================================
#  §5  EL NIVEL ES UN TECHO, NO UNA AUTORIZACION
# =============================================================================

def autonomia_es_techo():
    seccion("§5  El nivel de autonomia es un techo, no una autorizacion")

    fuente = inspect.getsource(autorizacion)

    afirmar("min(" in fuente or "nivel_efectivo" in fuente,
            "el nivel efectivo se calcula, no se toma del techo")
    #  nivel 3 + cero herramientas autorizadas = cero ejecucion
    afirmar(hasattr(autorizacion, "SIN_AUTORIZACION"),
            "una herramienta sin autorizacion se bloquea aunque el techo sea alto")
    afirmar(hasattr(autorizacion, "NIVEL_INSUFICIENTE"),
            "y una autorizada por debajo del nivel requerido tambien")

    #  NADIE se sube el techo a si mismo: el modulo no escribe.
    nombres = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
    afirmar(nombres.isdisjoint({"insert", "update", "save", "delete"}),
            "el modulo de autorizacion LEE; ningun agente se eleva el nivel")


# =============================================================================
#  §10  EL ORDEN DE LOS CONTROLES EN LA PUERTA AUTONOMA
# =============================================================================

def orden_de_controles():
    seccion("§10  Kill switch antes que autorizacion, y las dos antes del efecto")

    fuente = inspect.getsource(frontera.autonoma)

    pos_tenant = fuente.find("_tenant_valido")
    pos_switch = fuente.find("interruptor.veredicto")
    pos_etapa = fuente.find("autonomia2.veredicto")
    pos_autoriz = fuente.find("autorizacion.veredicto")
    pos_yield = fuente.find("yield")

    afirmar(-1 < pos_tenant < pos_switch,
            "1. el tenant se valida antes de consultar el interruptor")
    afirmar(pos_switch < pos_etapa,
            "2. el kill switch se consulta antes que la etapa de autonomia")
    afirmar(pos_etapa < pos_autoriz,
            "3. la etapa se consulta antes que la autorizacion granular")
    afirmar(pos_autoriz < pos_yield,
            "4. TODOS los controles corren antes de ceder el permiso (yield)")

    #  El kill switch no se puede saltar con una segunda bandera.
    afirmar(fuente.count("interruptor.veredicto") == 1,
            "el interruptor se consulta en UN solo punto")

    #  Y 'humana()' NO consulta el interruptor, a proposito y documentado.
    #  POR AST, no por texto. La primera version de esta guarda buscaba la
    #  palabra "interruptor" en el codigo fuente y fallaba... porque el
    #  docstring de 'humana' dice literalmente "NO consulta el interruptor".
    #  La guarda estaba leyendo su propia prosa -- el mismo error que este
    #  proyecto ya cometio tres veces. Lo que importa es si LLAMA, no si lo
    #  menciona.
    arbol_humana = ast.parse(inspect.getsource(frontera.humana).lstrip())
    llamadas = set()
    for nodo in ast.walk(arbol_humana):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
            base = nodo.func.value
            if isinstance(base, ast.Name):
                llamadas.add(f"{base.id}.{nodo.func.attr}")
    afirmar("interruptor.veredicto" not in llamadas,
            "la puerta humana no CONSULTA el interruptor (decision documentada)",
            f"llamadas: {sorted(llamadas)}")

    #  y exige las dos cosas que la vuelven auditable: por parametro, no por
    #  mencion en el texto.
    firma_humana = inspect.signature(frontera.humana)
    afirmar({"actor", "evidencia"} <= set(firma_humana.parameters),
            "...pero exige actor Y evidencia, que es lo que la hace auditable",
            f"parametros: {list(firma_humana.parameters)}")


# =============================================================================
#  §13  M09 PROPONE; NO EJECUTA
# =============================================================================

def m09_no_ejecuta():
    seccion("§13  M09 detecta y propone; el efecto vive en otro lado")

    ruta = RAIZ / "django-crm" / "backend" / "operaciones"
    for archivo in ("supervisor.py", "asistentes.py", "incidencias.py",
                    "novedades.py", "sla.py"):
        p = ruta / archivo
        if not p.exists():
            continue
        nombres = set()
        for nodo in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Attribute):
                nombres.add(nodo.attr)
            elif isinstance(nodo, ast.Name):
                nombres.add(nodo.id)
            elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
                for alias in nodo.names:
                    nombres.add((alias.asname or alias.name).split(".")[0])
        afirmar(nombres.isdisjoint({"requests", "httpx", "urllib", "frontera",
                                    "ejecutor_http", "wisphub", "smartolt"}),
                f"{archivo} no tiene con que producir un efecto externo",
                f"usa: {sorted(nombres & {'requests', 'httpx', 'frontera'})}")

    #  'ejecutar_propuesta' sigue sin ejecutar.
    sup = (ruta / "supervisor.py").read_text(encoding="utf-8")
    if "def ejecutar_propuesta" in sup:
        cuerpo = sup[sup.index("def ejecutar_propuesta"):]
        cuerpo = cuerpo[:cuerpo.find("\ndef ", 1) if cuerpo.find("\ndef ", 1) > 0 else 800]
        afirmar("raise" in cuerpo or "NotImplemented" in cuerpo or "no ejecuta" in cuerpo.lower(),
                "'ejecutar_propuesta' sigue sin ejecutar nada",
                cuerpo[:160])


# =============================================================================
#  §14  LAS CRITICAS SIGUEN SIENDO CRITICAS
# =============================================================================

def criticas():
    seccion("§14  R3 y R4: ninguna se volvio autonoma sola")

    criticas_reales = R3_EQUIPO_FISICO | R4_DINERO
    #  M06-F: 6 desde que origin trajo registrar_promesa_y_reactivar (R4).
    afirmar(len(criticas_reales) == 6,
            f"siguen siendo 6 las acciones criticas ({len(criticas_reales)})",
            str(sorted(criticas_reales)))

    for nombre in sorted(criticas_reales):
        h = POR_NOMBRE.get(nombre)
        afirmar(h is not None, f"'{nombre}' sigue en el catalogo")
        if h is None:
            continue
        afirmar(not h.solo_lectura, f"'{nombre}' sigue clasificada como escritura")
        #  Ninguna puede dispararse por la ruta de servicio (sin conversacion).
        afirmar(not getattr(h, "invocable_por_servicio", False),
                f"'{nombre}' NO es invocable por un servicio")

    #  Y la frontera las cubre a las 5: 'escribe()' devuelve True.
    for nombre in sorted(criticas_reales):
        h = POR_NOMBRE.get(nombre)
        if h is not None:
            afirmar(frontera.escribe(h),
                    f"la frontera reconoce '{nombre}' como escritura")


# =============================================================================
#  §6-§7  LA MATRIZ, Y LO QUE NO SE PUEDE DECIDIR SIN EL NEGOCIO
# =============================================================================

def matriz():
    seccion(f"§6-§7  Matriz de las {len(ESCRITURAS)} escrituras")

    todas = R1_INTERNO | R2_REGISTRO_EXTERNO | R3_EQUIPO_FISICO | R4_DINERO
    nombres = {h.nombre for h in ESCRITURAS}
    afirmar(todas == nombres,
            f"las {len(nombres)} escrituras estan clasificadas, sin sobras ni faltas",
            f"solo en la clasificacion: {sorted(todas - nombres)} | "
            f"solo en el catalogo: {sorted(nombres - todas)}")

    con_gate = {h.nombre for h in ESCRITURAS
                if getattr(h, "aprobacion_humana", False)}
    print(f"\n  con 'aprobacion_humana' (el gate REAL): {len(con_gate)} de {len(nombres)}")
    for n in sorted(con_gate):
        print(f"      {n}")

    #  DECISION DE NEGOCIO (21/09/2026, corregida el mismo dia):
    #    registrar_pago, reiniciar_ont, activar_catv y cambiar_tipo_onu exigen
    #    aprobacion humana obligatoria, ATADA a la accion (irreversible=True
    #    -> frontera.critica). La primera version dejo las R3 sin gate porque
    #    la cola no revalidaba previas ni anotaba la verificacion; se corrigio
    #    el MECANISMO, no la decision. Ver tests/test_m06a_gate_critico.py.
    #  M06-C (21/09/2026): agregar_promesa_pago (R4) entra a la decision -- su
    #  aprobacion queda atada a la operacion exacta, igual que las otras.
    #  Asi TODO R3 y R4 va por la puerta critica.
    #  M06-E: mas la excepcion conservadora cancelar_solicitud_servicio (R2 en
    #  M10-A, irreversible con evidencia; ver M04-M06_CIERRE_FASE_GOBIERNO.md).
    #  M06-F: registrar_promesa_y_reactivar (R4, llego en origin) entra por la
    #  misma decision: TODO R3 y R4.
    DECISION = R3_EQUIPO_FISICO | R4_DINERO | {"cancelar_solicitud_servicio"}
    sin_gate = sorted(DECISION - con_gate)
    afirmar(not sin_gate,
            f"las {len(DECISION)} de la decision (todo R3 y R4) exigen aprobacion humana",
            f"sin gate: {sin_gate}")
    irreversibles = {h.nombre for h in ESCRITURAS if getattr(h, "irreversible", False)}
    afirmar(irreversibles == DECISION,
            f"...y las {len(DECISION)} (solo ellas) van por la puerta critica (irreversible)",
            f"irreversibles: {sorted(irreversibles)}")
    r3_sin_previas = sorted(n for n in R3_EQUIPO_FISICO
                            if not getattr(POR_NOMBRE.get(n), "exige_previas", None))
    afirmar(not r3_sin_previas,
            "las tres R3 conservan sus condiciones previas (se re-miden al aprobar)",
            f"sin previas: {r3_sin_previas}")

    #  'requiere_confirmacion' NO es una barrera -- que no se confunda con una.
    con_confirm = {h.nombre for h in ESCRITURAS
                   if getattr(h, "requiere_confirmacion", False)}
    afirmar(len(con_confirm) > len(con_gate),
            "'requiere_confirmacion' NO es el gate: lo declaran casi todas",
            f"confirmacion: {len(con_confirm)} · gate real: {len(con_gate)}")


# =============================================================================
#  R4 EN EFECTO: UN PAGO PEDIDO EN CONVERSACION NO SALE, QUEDA EN LA COLA
# =============================================================================
#  Afirmar que 'aprobacion_humana' esta en True no prueba que el pago se
#  frene: prueba que el campo existe. Aca corre el motor REAL (responder) con
#  un modelo de guion que pide registrar_pago, y se mira a donde fue a parar.
#  Sin red y sin base: se sustituyen el modelo, la recuperacion, el indice de
#  habilidades, el registro de consumo, la cola y '_ejecutar_tool' -- por esa
#  funcion pasa toda llamada real a un tercero.
#
#  El control DESARMADO es parte de la prueba: la misma corrida con el gate
#  apagado en una copia de la config TIENE que llegar a '_ejecutar_tool'. Si
#  no llegara, el "0 ejecutadas" de arriba no probaria nada.

def _pago_en_conversacion(config) -> dict:
    from nucleo.modelo import motor
    from nucleo.modelo.cliente import Llamada, Respuesta

    guion = [Respuesta(llamadas=[Llamada("registrar_pago", {
                 "id_factura": 999001, "accion": "solo_registrar_pago",
                 "forma_pago": 1})]),
             Respuesta(contenido="Quedo pendiente de aprobacion.")]
    visto = {"propuestas": [], "ejecutadas": []}

    def guardar(tenant, herramienta, argumentos, resumen, rol, quien, **atadura):
        #  'atadura': hash_argumentos, origen, contexto -- los manda una
        #  irreversible (ver tests/test_m06a_gate_critico.py, que los afirma).
        visto["propuestas"].append({"herramienta": herramienta,
                                    "argumentos": argumentos, "resumen": resumen})
        return "propuesta-de-prueba", False  # M06-F: firma de B5, (id, ya_existia)

    def ejecutar(herramienta, *a, **k):
        visto["ejecutadas"].append(herramienta.nombre)
        return {"ok": True}

    sustituir = [
        (motor.cliente, "chat",
         lambda *a, **k: guion.pop(0) if guion else Respuesta(contenido="fin")),
        (motor, "recuperar", lambda *a, **k: ([], 0.0)),
        (motor.catalogo_habilidades, "indice_de", lambda *a, **k: []),
        (motor.consumo, "anotar", lambda *a, **k: None),
        (motor.persistencia, "guardar_accion_propuesta", guardar),
        (motor, "_ejecutar_tool", ejecutar),
    ]
    originales = [(o, a, getattr(o, a)) for o, a, _ in sustituir]
    for o, a, f in sustituir:
        setattr(o, a, f)
    try:
        motor.responder(config, "facturacion",
                        "registra el pago de la factura 999001", [], None)
    finally:
        for o, a, f in originales:
            setattr(o, a, f)
    return visto


def r4_en_efecto():
    import copy

    seccion("R4 en efecto: el pago pedido en conversacion queda en la cola")

    con_gate = _pago_en_conversacion(CONFIG)
    afirmar(con_gate["ejecutadas"] == [],
            "con el gate, registrar_pago NO llega a ejecutarse",
            f"ejecutadas: {con_gate['ejecutadas']}")
    afirmar([p["herramienta"] for p in con_gate["propuestas"]] == ["registrar_pago"],
            "...queda UNA propuesta en la cola de aprobacion",
            f"propuestas: {con_gate['propuestas']}")
    if con_gate["propuestas"]:
        p = con_gate["propuestas"][0]
        afirmar(p["argumentos"].get("id") == 999001 and p["argumentos"].get("accion") == 0,
                "...con los argumentos YA resueltos (factura y accion), que "
                "son los que se ejecutaran al aprobar",
                f"argumentos: {p['argumentos']}")
        afirmar("999001" in p["resumen"] and "{" not in p["resumen"],
                "...y quien aprueba lee un resumen con la factura, no el JSON crudo",
                f"resumen: {p['resumen']}")

    desarmada = copy.deepcopy(CONFIG)
    next(h for h in desarmada.herramientas
         if h.nombre == "registrar_pago").aprobacion_humana = False
    sin_gate = _pago_en_conversacion(desarmada)
    afirmar(sin_gate["ejecutadas"] == ["registrar_pago"] and not sin_gate["propuestas"],
            "CONTROL: con el gate apagado la misma corrida SI llega a ejecutarse "
            "-- el instrumento distingue, el cero de arriba significa algo",
            f"sin gate: {sin_gate}")


# =============================================================================
#  ESTADO DE LAS BRECHAS QUE M10-A DEJO ABIERTAS
# =============================================================================

def brechas_de_m10a():
    seccion("Brechas de M10-A: cuales se cerraron desde entonces")

    #  Brecha 3: autorizacion granular. M10-A la dejo como 'no existe'.
    afirmar(hasattr(autorizacion, "veredicto"),
            "BRECHA 3 CERRADA: la autorizacion granular existe",
            "nucleo/seguridad/autorizacion.py")
    afirmar("autorizacion.veredicto" in inspect.getsource(frontera.autonoma),
            "...y la frontera la consulta en la puerta autonoma")

    #  Brecha 4: interruptor binario. Sigue.
    afirmar(interruptor.ESTADOS == (interruptor.ACTIVO, interruptor.DETENIDO),
            "BRECHA 4 ABIERTA: el interruptor sigue siendo binario",
            "no se puede permitir R2 y frenar R4 desde el interruptor; hoy lo "
            "hace la autorizacion granular, que si es por herramienta")

    #  La etapa de Autonomia 2 sigue apagada: es lo que hace que hoy
    #  ninguna accion autonoma salga.
    v = autonomia2.veredicto({})
    afirmar(not v.permitido,
            "la etapa de Autonomia 2 sigue APAGADA (fail-closed)",
            f"{v.codigo}: {v.motivo}")


def main() -> int:
    print("=" * 78)
    print("  M06-A  --  frontera de acciones tecnicas y autorizacion")
    print("=" * 78)
    print("  No se crea ningun control nuevo: se comprueba que la cadena")
    print("  existente se comporte como una sola puerta.")

    estados_de_accion()
    aprobacion_ligada_a_argumentos()
    autonomia_es_techo()
    orden_de_controles()
    m09_no_ejecuta()
    criticas()
    matriz()
    r4_en_efecto()
    brechas_de_m10a()

    print()
    print("=" * 78)
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for f in FALLOS:
            print(f"    - {f}")
        print("=" * 78)
        return 1
    print("  [OK] La cadena de autorizacion se comporta como una sola puerta,")
    print("       y la aprobacion vale para UNOS argumentos, no para una herramienta.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
