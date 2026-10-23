# -*- coding: utf-8 -*-
"""
================================================================================
 LA RUTA INTERNA DE SERVICIO PUEDE MANDAR LA IDENTIDAD, Y SIGUE SIENDO LA UNICA
================================================================================

Por que existe
--------------
Encontrado el 24/09/2026 construyendo el ping del tecnico. Una herramienta con
'inyectar_sesion' --o sea, cualquiera que pregunte por UN cliente-- no se podia
ejecutar por POST /interno/herramienta/<nombre>, nunca. El motivo estaba en el
orden de _resolver_argumentos:

  1. 'sobrescribir' pone lo que el CODIGO decidio (id_servicio=5832)
  2. el bucle de 'inyectar_sesion' lee la sesion, que en esa ruta es None a
     proposito, y hace argumentos.pop(...) -- borrando lo de arriba
  3. 'inyectados_obligatorios' encuentra el hueco y frena la llamada

El sintoma era enganoso: "necesita ['id_servicio'] de la sesion verificada",
hablando de una sesion que del otro lado no existe y nunca va a existir.

Lo que se fija aca
------------------
1. Con la sesion vacia, un valor puesto por 'sobrescribir' SOBREVIVE y la
   llamada sale.
2. Una sesion CON valor sigue ganandole al codigo. Esa precedencia es la que
   impide que una llamada salga con el id de otro cliente, y no se toca.
3. Lo que propuso el MODELO se sigue borrando cuando la sesion esta vacia.
   Ese pop es la guarda original y tiene que seguir cazando.
4. Una clave que el tenant NO declaro en 'argumentos_sobrescribibles' no entra
   por este camino, aunque el llamador la mande.

Se afirma sobre los argumentos RESUELTOS -- el efecto-- y no sobre que exista
la rama del if. Sin red, sin base y sin modelo:

    py -3.13 tests/test_ruta_de_servicio_identidad.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.config.schema import Herramienta            # noqa: E402
from nucleo.modelo import motor                          # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class _Sesion:
    def __init__(self, id_cliente=None):
        self.id_cliente = id_cliente


def herramienta(sobrescribibles=("id_servicio",)):
    return Herramienta(
        nombre="consulta_de_un_cliente",
        tipo="http",
        descripcion="Consulta acotada a un cliente.",
        solo_lectura=True,
        roles_permitidos=["soporte"],
        base_url="https://ejemplo.invalido",
        endpoint="/clientes/{id_servicio}/",
        metodo="GET",
        inyectar_sesion={"id_servicio": "id_cliente"},
        inyectados_obligatorios=["id_servicio"],
        invocable_por_servicio=True,
        argumentos_sobrescribibles=list(sobrescribibles),
    )


def resolver(h, sesion, del_modelo=None, sobrescribir=None):
    return motor._resolver_argumentos(h, sesion, del_modelo or {},
                                      sobrescribir=sobrescribir)


print("\n--- 1. sin sesion, el codigo puede decir de quien habla ---")
# El caso que estaba roto. Es la ruta interna: del otro lado no hay persona.
try:
    args = resolver(herramienta(), None, sobrescribir={"id_servicio": "5832"})
    afirmar(args.get("id_servicio") == "5832",
            f"la llamada sale con el id que puso el codigo ({args.get('id_servicio')!r})")
except motor.FaltaIdentidadEnSesion:
    afirmar(False, "la llamada se frena aunque el codigo dijo de quien habla "
                   "-- el ping del tecnico no salia por esto")

print("\n--- 2. una sesion CON valor le sigue ganando al codigo ---")
# La precedencia que protege al cliente equivocado. Si esto se invierte, una
# conversacion verificada podria terminar consultando otra cuenta.
args = resolver(herramienta(), _Sesion("7001"), sobrescribir={"id_servicio": "5832"})
afirmar(args.get("id_servicio") == "7001",
        f"gana la sesion verificada, no el argumento ({args.get('id_servicio')!r})")

print("\n--- 3. lo que propone el MODELO se sigue borrando ---")
# La guarda original, intacta: sin sesion, un id que el modelo invento no
# puede convertirse en una consulta. Es el agujero que motivo
# 'inyectados_obligatorios'.
try:
    resolver(herramienta(), None, del_modelo={"id_servicio": "9999"})
    afirmar(False, "un id propuesto por el modelo sobrevivio a la sesion vacia")
except motor.FaltaIdentidadEnSesion:
    afirmar(True, "un id propuesto por el modelo NO sobrevive: la llamada no sale")

print("\n--- 4. la lista blanca del tenant sigue mandando ---")
# Si el tenant no lo declaro sobrescribible, no entra -- aunque el llamador
# interno lo mande. Un servicio nuevo no gana permisos por existir.
try:
    resolver(herramienta(sobrescribibles=()), None,
             sobrescribir={"id_servicio": "5832"})
    afirmar(False, "entro una clave que el tenant no declaro sobrescribible")
except motor.FaltaIdentidadEnSesion:
    afirmar(True, "sin declararla en 'argumentos_sobrescribibles', no entra")

print("\n--- 5. una sesion vacia con '' se comporta igual que None ---")
args = resolver(herramienta(), _Sesion(""), sobrescribir={"id_servicio": "5832"})
afirmar(args.get("id_servicio") == "5832",
        "el motor ya convierte '' en ausente; el codigo puede completarlo igual")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] Un servicio puede decir de quien habla; el modelo no, y la sesion manda.")
