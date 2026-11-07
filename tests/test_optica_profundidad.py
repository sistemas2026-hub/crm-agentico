# -*- coding: utf-8 -*-
"""
La lista blanca de la lectura profunda del equipo.

QUE PROTEGE, Y POR QUE HACE FALTA UNA PRUEBA
--------------------------------------------
`get_onu_full_status_info` devuelve 86 campos, y entre ellos
'ONU details.Description': el NOMBRE COMPLETO del cliente en el registro de la
ONU. La pantalla de Equipo muestra siete de esos campos y no puede mostrar el
resto -- ni hoy ni el dia que el proveedor agregue otros.

Las afirmaciones son sobre el EFECTO: que el nombre no salga, y que los siete
que si salen lleguen con su valor. No sobre que exista un filtro -- un filtro
puede existir y dejar pasar todo.

La forma de la respuesta se copio de una lectura REAL contra la instancia de
Rapilink (22/09/2026, serial de prueba), con los valores personales cambiados
por textos que se reconocen si se escapan.

    py -3.13 tests/test_optica_profundidad.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# El endpoint importa el motor entero; para esta prueba alcanza la funcion.
os.environ.setdefault("DBHOST", "localhost")
os.environ.setdefault("DBPORT", "5432")
os.environ.setdefault("DBNAME", "postgres")
os.environ.setdefault("DBUSER", "postgres")
os.environ.setdefault("DBPASSWORD", "x")

from nucleo.canales.api import _profundidad_de  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


# Lo que de verdad devuelve el proveedor, con la PII marcada para reconocerla.
NOMBRE = "NOMBRE COMPLETO DEL CLIENTE"
RESPUESTA = {
    "Optical status": {
        "Module type": "GPON",
        "Rx optical power(dBm)": "-21.13",
        "Tx optical power(dBm)": "1.31",
        "Temperature(C)": "44",
        "OLT Rx ONT optical power(dBm)": "-26.58",
        "CATV Rx optical power(dBm)": "N/A",
    },
    "ONU details": {
        "SN": "HWTC00000000",
        "Description": NOMBRE,
        "Last down cause": "dying-gasp",
        "ONT online duration": "0 day(s), 4 hour(s)",
        "Line profile name": "PLAN_100MB",
        "Service profile name": "SRV_100MB",
    },
    "History": {"01": {"Auth at": "x", "Offline at": "y", "Cause": "z"}},
    "ONU WAN Interfaces": {
        "1": {"MAC address": "AA:BB:CC:00:11:22", "IPv4 address": "172.16.0.9"},
        "2": {"MAC address": "AA:BB:CC:00:11:33"},
    },
    "MACs on OLT from this ONU": {
        "1": {"MAC address": "DE:AD:BE:EF:00:01"},
        "2": {"MAC address": "DE:AD:BE:EF:00:02"},
    },
}

print("\n--- los siete campos llegan ---")
r = _profundidad_de(RESPUESTA)
afirmar(r is not None, "una respuesta completa produce datos")
afirmar(r.get("temperatura") == "44", "la temperatura sale del modulo optico")
afirmar(r.get("tx") == "1.31", "la potencia de subida del equipo")
afirmar(r.get("olt_rx") == "-26.58", "lo que la OLT recibe del equipo")
afirmar(r.get("encendido") == "0 day(s), 4 hour(s)", "hace cuanto esta encendida")
afirmar(r.get("perfil") == "PLAN_100MB", "el perfil de linea")
afirmar(r.get("mac") == "AA:BB:CC:00:11:22",
        "la MAC de la PRIMERA interfaz WAN, no las dos concatenadas")
afirmar(r.get("dispositivos") == 2,
        "cuantos equipos se ven detras de la ONU: un numero")

print("\n--- y nada mas que esos siete ---")
afirmar(set(r) == {"temperatura", "tx", "olt_rx", "encendido", "perfil",
                   "mac", "dispositivos"},
        f"no sale ninguna clave de mas (salieron: {sorted(r)})")

print("\n--- el nombre del cliente no cruza ---")
afirmar(NOMBRE not in str(r),
        "'Description' trae el nombre del cliente y NO aparece en la salida")
afirmar("172.16.0.9" not in str(r),
        "la IP de la casa tampoco: no es lo que esta pantalla pregunta")
afirmar("DE:AD:BE:EF:00:01" not in str(r),
        "las MAC de los aparatos del cliente se cuentan, no se listan")

print("\n--- lo que el proveedor agregue manana se queda afuera ---")
manana = {k: dict(v) if isinstance(v, dict) else v for k, v in RESPUESTA.items()}
manana["ONU details"]["Subscriber address"] = "CALLE FALSA 123"
manana["Nueva seccion"] = {"Cedula": "1234567890"}
r2 = _profundidad_de(manana)
afirmar("CALLE FALSA 123" not in str(r2),
        "un campo nuevo en una seccion conocida no pasa")
afirmar("1234567890" not in str(r2), "una seccion nueva entera tampoco")
afirmar(set(r2) == set(r), "y la salida sigue siendo exactamente la misma")

print("\n--- respuestas incompletas no rompen ---")
afirmar(_profundidad_de({}) is None, "una respuesta vacia no produce datos")
afirmar(_profundidad_de({"Optical status": None}) is None,
        "una seccion nula tampoco -- el proveedor las manda asi cuando no mide")
afirmar(_profundidad_de({"Optical status": {"Temperature(C)": ""}}) is None,
        "un campo vacio no es un dato: mejor nada que un renglon en blanco")
solo_mac = _profundidad_de({"ONU WAN Interfaces": {"1": {"MAC address": "A"}}})
afirmar(solo_mac == {"mac": "A"}, "con un solo campo, sale ese solo campo")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] La lectura profunda muestra siete campos y no filtra nada mas.")
