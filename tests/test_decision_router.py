# -*- coding: utf-8 -*-
"""
POR QUE ESTE TURNO DERIVO, O POR QUE NO.

De donde sale
-------------
El 22/09/2026 'cliente_final' le pidio la cedula a un cliente que queria
darse de baja, en vez de derivar a facturacion -- algo que su propio contrato
le prohibe. Reconstruirlo costo dos horas y al final no se pudo decir POR QUE:
la traza guardaba lo que se ejecuto (nada) y el hilo lo que respondio. Faltaba
el medio.

Doce corridas contra el motor real no lo reprodujeron. Cuando algo pasa una
vez y no se repite, lo unico que queda es que la proxima vez deje rastro.

Por que esta prueba existe aparte de los casos dorados
------------------------------------------------------
Porque los casos dorados NO pueden verla. 'cli/evaluar.py' llama a
motor.responder() directo y no pasa por atender_turno: todo lo que se agregue
alrededor del modelo --este registro, el control de concurrencia-- queda
fuera de su alcance. Es una limitacion del arnes, no de la funcionalidad, y
por eso lo que se registra vive en una funcion pura que si se puede probar sin
base, sin modelo y sin red.

    py -3.13 tests/test_decision_router.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.canales.api import decision_del_router  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class SesionFalsa:
    def __init__(self, verificado=False, id_cliente_pendiente=None):
        self.verificado = verificado
        self.id_cliente_pendiente = id_cliente_pendiente


class RolFalso:
    def __init__(self, puede_consultar=None):
        self.puede_consultar = puede_consultar or []


ROUTER = RolFalso([])                       # cliente_final: no consulta nada
AREA = RolFalso(["verificar_identidad_por_cedula", "confirmar_identidad",
                 "consultar_facturas"])

print("\n--- el caso que fallo: el router resolvio por su cuenta ---")
d = decision_del_router("cliente_final", "cliente_final",
                        SesionFalsa(), ROUTER, [])
afirmar(d["rol"] == "cliente_final", "queda con que rol se evaluo")
afirmar(d["derivo_a"] == "",
        "y que NO derivo -- que es lo unico que distinguia este turno de uno "
        "sano, y no estaba guardado en ningun lado")
afirmar(d["herramientas_disponibles"] == 0,
        "con cero herramientas a mano: pidio un dato que no podia usar")
afirmar(d["herramientas_usadas"] == 0, "y no llamo a ninguna")

print("\n--- el turno sano: derivo ---")
d = decision_del_router("cliente_final", "facturacion_cliente",
                        SesionFalsa(), ROUTER, [{"herramienta": "derivar_a_area"}])
afirmar(d["derivo_a"] == "facturacion_cliente",
        "queda a que area paso, comparando contra el rol EVALUADO")
afirmar(d["herramientas_usadas"] == 1, "y cuantas herramientas corrieron")

print("\n--- los tres estados de identidad ---")
afirmar(decision_del_router("x", "x", SesionFalsa(), ROUTER, [])["identidad"]
        == "sin_verificar", "sin nada: sin_verificar")
afirmar(decision_del_router("x", "x", SesionFalsa(id_cliente_pendiente="5832"),
                            ROUTER, [])["identidad"] == "candidata",
        "LOCALIZADA PERO SIN CONFIRMAR: 'candidata', que es el estado que "
        "existe justo para poder auditar la diferencia entre localizar y "
        "verificar")
afirmar(decision_del_router("x", "x", SesionFalsa(verificado=True),
                            ROUTER, [])["identidad"] == "verificada",
        "confirmada: verificada")
afirmar(decision_del_router("x", "x", None, ROUTER, [])["identidad"]
        == "sin_verificar", "sin sesion no se afirma identidad")

print("\n--- verificada gana sobre candidata ---")
d = decision_del_router("x", "x", SesionFalsa(verificado=True,
                                              id_cliente_pendiente="5832"),
                        ROUTER, [])
afirmar(d["identidad"] == "verificada",
        "un pendiente que quedo sin limpiar no degrada una identidad ya "
        "confirmada")

print("\n--- NADA DE PII, que es la condicion para que esto pueda existir ---")
sucia = SesionFalsa(id_cliente_pendiente="5832")
sucia.telefono = "3001234567"
sucia.nombre = "MARIO SABANAGRANDE"
sucia.cedula = "000021"
d = decision_del_router("cliente_final", "facturacion_cliente", sucia, AREA,
                        [{"herramienta": "verificar_identidad_por_cedula"}])
texto = str(d)
for secreto in ("3001234567", "MARIO", "000021", "5832"):
    afirmar(secreto not in texto, f"'{secreto}' no aparece en lo que se registra")
afirmar(set(d) == {"rol", "identidad", "herramientas_disponibles",
                   "herramientas_usadas", "derivo_a"},
        f"y no sale ningun campo de mas (salieron: {sorted(d)})")

print("\n--- cuenta las herramientas del rol, no las del tenant ---")
d = decision_del_router("facturacion_cliente", "facturacion_cliente",
                        SesionFalsa(), AREA, [])
afirmar(d["herramientas_disponibles"] == 3,
        "el area tiene tres; el router tenia cero. Esa diferencia es la que "
        "explica por que uno puede resolver y el otro tiene que derivar")

print("\n--- no rompe con lo que falte ---")
afirmar(decision_del_router("x", "x", None, None, None)["herramientas_disponibles"] == 0,
        "sin rol configurado no levanta: es observabilidad, no funcionalidad")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] La decision del router queda registrada, y sin un solo dato del cliente.")
