# -*- coding: utf-8 -*-
"""
UN ROL QUE NO VERIFICA NO SE QUEDA PIDIENDO LA CEDULA.

El caso, de produccion (22/09/2026)
-----------------------------------
'cliente_final' le pidio a un cliente el nombre y el "DNI" para darse de baja.
El cliente los mando. Volvio a pedirlos. Ocho horas dando vueltas y CERO
herramientas ejecutadas en toda la conversacion.

Su instruccion dice tres veces que no verifica y que derive a facturacion, y
la palabra "DNI" no aparece en ninguna parte de ella: el modelo se invento un
flujo. La config desplegada resulto identica al repo, byte a byte, asi que no
era un problema de configuracion.

Por que esto vive en codigo y no en otra frase del prompt: PRD 7.4 -- el
prompt es guia, nunca la garantia. Ya habia tres frases y no alcanzaron.

Que se afirma
-------------
Sobre la DECISION, no sobre el texto que produzca el modelo: las tres
condiciones que tienen que darse juntas, y sobre todo las que NO deben
disparar la guarda. Un falso positivo aca fuerza una derivacion que no
correspondia, y eso es peor que el problema original.

    py -3.13 tests/test_reencauzar_identidad.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.canales.api import debe_reencauzar_a_derivacion  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class Herr:
    def __init__(self, nombre, verifica_identidad=False, deriva_rol=None):
        self.nombre = nombre
        self.verifica_identidad = verifica_identidad
        self.deriva_rol = deriva_rol


class RolF:
    def __init__(self, puede_consultar):
        self.puede_consultar = puede_consultar


class ConfigF:
    def __init__(self, roles, herramientas):
        self.roles = roles
        self.herramientas = herramientas


DERIVAR = Herr("derivar_a_area", deriva_rol="facturacion_cliente")
VERIFICA = Herr("verificar_identidad_por_cedula", verifica_identidad=True)
LEER = Herr("consultar_facturas")

CONF = ConfigF(
    roles={"cliente_final": RolF(["derivar_a_area"]),
           "facturacion_cliente": RolF(["derivar_a_area",
                                        "verificar_identidad_por_cedula",
                                        "consultar_facturas"]),
           "sin_salida": RolF(["consultar_facturas"])},
    herramientas=[DERIVAR, VERIFICA, LEER])

PIDE = "Necesito tu nombre y el DNI del titular para validar la cuenta."

print("\n--- EL CASO QUE PASO ---")
afirmar(debe_reencauzar_a_derivacion(CONF, "cliente_final", PIDE, []),
        "el router pide identidad, no puede verificar y no derivo: se reencauza")
afirmar(debe_reencauzar_a_derivacion(
            CONF, "cliente_final",
            "Ese numero no me sirve. Necesito la cedula del titular.", []),
        "y tambien en la segunda vuelta, que es donde se quedo ocho horas")

print("\n--- LO QUE NO DEBE DISPARARLA (un falso positivo fuerza una derivacion "
      "que no correspondia) ---")
afirmar(not debe_reencauzar_a_derivacion(
            CONF, "facturacion_cliente", PIDE, []),
        "el AREA si puede verificar: pedir la cedula es su trabajo")
afirmar(not debe_reencauzar_a_derivacion(
            CONF, "cliente_final", PIDE,
            [{"herramienta": "derivar_a_area"}]),
        "si YA derivo, quien contesta es el area -- y el area debe pedirla. "
        "Esto se probo con casos dorados y prohibirlo marcaba como falla el "
        "comportamiento correcto")
afirmar(not debe_reencauzar_a_derivacion(
            CONF, "cliente_final",
            "Te paso con facturacion para que sigan con la baja.", []),
        "una respuesta que no pide identidad no se toca")
afirmar(not debe_reencauzar_a_derivacion(
            CONF, "sin_salida", PIDE, []),
        "sin herramienta para derivar, reencauzar solo daria otra vuelta igual")
afirmar(not debe_reencauzar_a_derivacion(CONF, "rol_que_no_existe", PIDE, []),
        "un rol desconocido no dispara nada: fail-open en observabilidad, no "
        "se inventa una derivacion")

print("\n--- reconoce como lo escribe un modelo, no como esta en el prompt ---")
# 'DNI' no aparece en la instruccion del rol: el modelo la trajo de su cabeza.
for frase in ("me confirmas tu numero de documento?",
              "necesito el DNI del titular",
              "pasame tu cédula por favor",
              "Necesito tu documento de identidad"):
    afirmar(debe_reencauzar_a_derivacion(CONF, "cliente_final", frase, []),
            f"reconoce {frase[:34]!r}")

print("\n--- no rompe con lo que falte ---")
afirmar(not debe_reencauzar_a_derivacion(CONF, "cliente_final", "", []),
        "respuesta vacia no dispara")
afirmar(not debe_reencauzar_a_derivacion(CONF, "cliente_final", None, None),
        "ni una respuesta nula con llamadas nulas")



# ===========================================================================
# SEGUNDA PARTE: EL CAMINO ENTERO, Y CONTRA LA CONFIG REAL
# ===========================================================================
#
# Lo de arriba prueba la DECISION con una config de juguete. Eso no dice dos
# cosas que importan mas:
#
#   1. que dispare con la config REAL de Rapilink -- si 'cliente_final'
#      tuviera una herramienta que declara verifica_identidad, la guarda
#      jamas se activaria y todo lo de arriba seguiria en verde.
#   2. que al cliente le llegue OTRA respuesta. Afirmar sobre el efecto,
#      nunca sobre la presencia del mecanismo: esta guarda podria estar
#      entera y devolver igual el pedido de cedula.
#
# Encontro un defecto real: la segunda vuelta se iba con un uuid nuevo al
# azar, sin marca, y las dos vueltas del mismo turno quedaban sin forma de
# juntarse en la traza.
from pathlib import Path  # noqa: E402

from nucleo.config import cargar_config  # noqa: E402

RAIZ = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")

# Lo que el bot dijo de verdad en produccion el 22/09/2026.
PIDE_CEDULA = ("Para poder ayudarte con la cancelacion necesito verificar tus "
               "datos. Me confirmas tu nombre completo y numero de DNI?")

print("\n--- con la config REAL de Rapilink, no con una de juguete ---")
afirmar(debe_reencauzar_a_derivacion(REAL, "cliente_final", PIDE_CEDULA, []),
        "'cliente_final' de Rapilink: no verifica, si deriva -- se reencauza")
afirmar(not debe_reencauzar_a_derivacion(REAL, "facturacion_cliente",
                                         PIDE_CEDULA, []),
        "'facturacion_cliente' de Rapilink si verifica: no se toca")

print("\n--- atender_turno() de verdad, base y modelo sustituidos ---")
from nucleo.canales import api  # noqa: E402

TEL = "573001112233"
YA_DERIVO = "Listo, un momento."
vueltas = []


def _modelo(config, rol, mensaje, historial, sesion,
            nota_continuidad=None, origen=None):
    vueltas.append({"nota": nota_continuidad, "origen": origen})
    if nota_continuidad is None:
        return (PIDE_CEDULA, [], [])                              # 1a: el bug
    return (YA_DERIVO, [{"herramienta": "derivar_a_area"}], [])   # 2a: derivo


def _turno(responder):
    """Mismo patron de sustitucion que tests/test_chat_canal.py."""
    p, esc, mot = api.persistencia, api.escalamiento, api.motor
    previo = {"escalada": False, "necesita_atencion_humana": False,
              "caso_id": None, "conversation_id": None, "motivo_escalada": None,
              "rol_efectivo": None, "id_cliente": None, "nombre_cliente": None,
              "datos_sesion": {}}
    postizos = {
        p: {"estado_de_conversacion_abierta": lambda *a, **k: previo,
            "control_de_conversacion_abierta": lambda *a, **k: {
                "conversation_id": "conv-1", "control_efectivo": "ia",
                "control_motivo": None, "relevo_version": 0},
            "atendida_por_humano": lambda *a, **k: False,
            "registrar_mensaje": lambda *a, **k: ("conv-1", "msg-1"),
            "conversacion_vencida": lambda *a, **k: None,
            "identificar_cliente": lambda *a, **k: None,
            "resumen_anterior": lambda *a, **k: None,
            "historial_para_el_modelo": lambda *a, **k: [],
            "registrar_turno": lambda *a, **k: None,
            "actualizar_contenido_mensaje": lambda *a, **k: None,
            "caso_de_conversacion": lambda *a, **k: None,
            "ticket_operativo_de": lambda *a, **k: None,
            "cerrar_conversacion": lambda *a, **k: None,
            "guardar_resumen": lambda *a, **k: None,
            "marcar_caso": lambda *a, **k: None,
            "completar_medicion": lambda *a, **k: None,
            "guardar_estado_routing": lambda *a, **k: None,
            "registrar_estado_escalada": lambda *a, **k: None,
            "registrar_marca_tv_desconocida": lambda *a, **k: None},
        esc: {"caso_sigue_abierto": lambda *a, **k: True,
              "evaluar": lambda *a, **k: {}},
        mot: {"responder": responder},
        api: {"_resolver_verificacion_pendiente": lambda *a, **k: None,
              "_hay_verificacion_pendiente": lambda *a, **k: False},
        api.consumo: {"estado_del_gasto": lambda *a, **k: {
            "accion": "seguir", "gastado": 0, "tope": 0, "porcentaje": 0.0}},
    }
    orig = {(m, n): getattr(m, n)
            for m, d in postizos.items() for n in d if hasattr(m, n)}
    for m, d in postizos.items():
        for n, f in d.items():
            if hasattr(m, n):
                setattr(m, n, f)
    try:
        return api.atender_turno(REAL, "rapilink", "cliente_final", TEL,
                                 "quiero cancelar el servicio", "whatsapp")
    finally:
        for (m, n), f in orig.items():
            setattr(m, n, f)


api._sesiones.clear()
dicho = (_turno(_modelo) or {}).get("respuesta", "")

afirmar(len(vueltas) == 2, "hubo una segunda vuelta al bucle del agente")
afirmar("DNI" not in dicho and "documento" not in dicho.lower(),
        "EL PEDIDO DE CEDULA NO LE LLEGA AL CLIENTE -- que es el efecto, y "
        "lo unico que el cliente nota")
afirmar(dicho == YA_DERIVO, "le llega la respuesta de la vuelta que SI derivo")
afirmar(vueltas and vueltas[-1]["nota"] == api.INSTRUCCION_REENCAUZAR,
        "la segunda vuelta recibe el aviso interno, no otro mensaje del cliente")
afirmar(len(vueltas) == 2
        and vueltas[1]["origen"] == f"{vueltas[0]['origen']}:reencauzado",
        "las dos vueltas comparten el origen, con sufijo: sin esto quedan sin "
        "forma de juntarse en la traza (defecto real que encontro esta prueba)")

print("\n--- si reincide, NO entra en bucle ---")
vueltas.clear()
api._sesiones.clear()


def _reincide(config, rol, mensaje, historial, sesion,
              nota_continuidad=None, origen=None):
    vueltas.append({"nota": nota_continuidad, "origen": origen})
    return (PIDE_CEDULA, [], [])


otra = (_turno(_reincide) or {}).get("respuesta", "")
afirmar(len(vueltas) == 2, "UNA sola vez, aunque la segunda tampoco derive")
afirmar(otra == PIDE_CEDULA,
        "y se manda lo que haya: el cliente esperando no tiene la culpa de "
        "que el modelo insista")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] Al cliente le llega la derivacion, no el pedido de cedula.")
