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

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] Se reencauza solo a quien pide lo que no puede usar.")
