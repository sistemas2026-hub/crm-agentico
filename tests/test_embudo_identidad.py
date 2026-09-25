# -*- coding: utf-8 -*-
"""
EL EMBUDO DE IDENTIDAD SE CLASIFICA BIEN, Y SIN UN SOLO DATO DEL CLIENTE.

Fase 1 de "completar el ciclo de identidad" (23/09/2026). El motor ya frena
en codigo lo que necesita saber quien es el cliente; lo que pasa despues lo
decide el modelo, y ahi se pierde un tercio de las conversaciones (16 de 49
en 45 dias). Para arreglarlo primero hay que verlo, y la traza no alcanza:
la fila de la herramienta que verifica dice exito=true tanto si encontro al
cliente como si no.

Lo que se afirma aqui es la CLASIFICACION (motor.evento_identidad), que es
una funcion pura, y el paso al registro del turno (api.eventos_identidad_de).
Afirmar que se INSERTA en la base es cosa de la migracion y de
cli/embudo_identidad.py contra una base real.

Y lo mas importante: que por ese camino no pase ni la cedula, ni el nombre,
ni el telefono. Es la condicion para que la tabla pueda existir.

    py -3.13 tests/test_embudo_identidad.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.modelo.motor import evento_identidad, CODIGOS_DE_IDENTIDAD, CODIGOS_DE_BLOQUEO  # noqa: E402
from nucleo.canales.api import eventos_identidad_de  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class Herr:
    def __init__(self, nombre, verifica=False, confirma=False):
        self.nombre = nombre
        self.verifica_identidad = verifica
        self.confirma_identidad = confirma


class Ses:
    def __init__(self, pendiente=None, intentos=0):
        self.id_cliente_pendiente = pendiente
        self.intentos_verificacion_fallidos = intentos
        # PII a proposito: nada de esto puede salir en el evento.
        self.telefono = "3001234567"
        self.nombre = "MARIO SABANAGRANDE"
        self.cedula = "000021"
        self.nombre_pendiente = "MARIO SABANAGRANDE"


VERIFICA = Herr("verificar_identidad_por_cedula", verifica=True)
CONFIRMA = Herr("confirmar_identidad", confirma=True)
CONSULTA = Herr("consultar_mi_servicio")

print("\n--- los codigos de identidad son un subconjunto de los de bloqueo ---")
afirmar(CODIGOS_DE_IDENTIDAD <= CODIGOS_DE_BLOQUEO,
        "ninguno se invento aqui: todos los produce un gate del motor")

print("\n--- el bloqueo, y lo que el motor espera despues ---")
e = evento_identidad(CONSULTA, {"error": "IDENTIDAD_NO_VERIFICADA"},
                     "IDENTIDAD_NO_VERIFICADA", Ses())
afirmar(e and e["etapa"] == "bloqueo" and e["motivo"] == "IDENTIDAD_NO_VERIFICADA",
        "un bloqueo por identidad queda como bloqueo, con su codigo")
afirmar(e and e["siguiente_paso"] == "espera_cedula",
        "sin candidato pendiente, lo que sigue es la cedula")
e = evento_identidad(CONSULTA, {}, "IDENTIDAD_NO_VERIFICADA", Ses(pendiente="5832"))
afirmar(e and e["siguiente_paso"] == "espera_nombre",
        "con candidato pendiente, lo que sigue es confirmar el nombre")
e = evento_identidad(CONSULTA, {}, "IDENTIDAD_NO_RESUELTA", None)
afirmar(e and e["etapa"] == "bloqueo" and e["siguiente_paso"] == "espera_cedula",
        "IDENTIDAD_NO_RESUELTA tambien cuenta, y sin sesion no rompe")
e = evento_identidad(CONSULTA, {}, "DATO_DEL_EQUIPO_NO_CARGADO", Ses())
afirmar(e and e["siguiente_paso"] == "ninguno",
        "DATO_DEL_EQUIPO_NO_CARGADO: ya sabemos quien es, no se espera nada del cliente")
afirmar(evento_identidad(CONSULTA, {}, "PRECONDICION_NO_CUMPLIDA", Ses()) is None,
        "un bloqueo que NO es de identidad no entra al embudo")

print("\n--- la verificacion: encontrado, no encontrado, ambiguo ---")
e = evento_identidad(VERIFICA, {"verificado": False, "nombre_a_confirmar": "MARIO S."},
                     None, Ses(pendiente="5832"))
afirmar(e and e["etapa"] == "verificacion_ok" and e["siguiente_paso"] == "espera_nombre",
        "encontrado: verificacion_ok y lo que sigue es el nombre")
e = evento_identidad(VERIFICA, {"verificado": False, "motivo": "no encontrado"},
                     None, Ses(intentos=1))
afirmar(e and e["etapa"] == "verificacion_fallo" and e["motivo"] == "no encontrado"
        and e["intentos"] == 1,
        "no encontrado: verificacion_fallo, con el intento contado -- esto es lo "
        "que la traza NO distingue (exito=true en ambos)")
e = evento_identidad(VERIFICA, {"verificado": False, "motivo": "ambiguo"}, None, Ses())
afirmar(e and e["etapa"] == "verificacion_ambigua", "ambiguo tiene su propia etapa")

print("\n--- la confirmacion ---")
e = evento_identidad(CONFIRMA, {"verificado": True}, None, Ses())
afirmar(e and e["etapa"] == "confirmacion_ok" and e["siguiente_paso"] == "ninguno",
        "confirmado: el ciclo se cerro")
e = evento_identidad(CONFIRMA, {"verificado": False, "motivo": "el cliente no confirmo el nombre"},
                     None, Ses())
afirmar(e and e["etapa"] == "confirmacion_fallo" and e["siguiente_paso"] == "espera_cedula",
        "no confirmo: se vuelve a empezar por la cedula")

print("\n--- lo que no tiene que ver, no entra ---")
afirmar(evento_identidad(CONSULTA, [{"plan": "x"}], None, Ses()) is None,
        "una consulta normal que salio bien: None")
afirmar(evento_identidad(None, {"x": 1}, None, Ses()) is None,
        "sin herramienta conocida y sin codigo de identidad: None")
afirmar(evento_identidad(VERIFICA, "texto raro", None, Ses()) is None,
        "una salida que no es dict no rompe: None")

print("\n--- NADA DE PII, que es la condicion para que la tabla exista ---")
for salida in ({"verificado": False, "nombre_a_confirmar": "MARIO SABANAGRANDE"},
               {"verificado": False, "motivo": "no encontrado"},
               {"error": "IDENTIDAD_NO_VERIFICADA"}):
    for herr, codigo in ((VERIFICA, None), (CONFIRMA, None), (CONSULTA, "IDENTIDAD_NO_VERIFICADA")):
        e = evento_identidad(herr, salida, codigo, Ses(pendiente="5832", intentos=2))
        texto = str(e)
        for secreto in ("3001234567", "MARIO", "000021", "5832"):
            afirmar(secreto not in texto, f"'{secreto}' no sale en {e['etapa'] if e else None}")
        if e:
            afirmar(set(e) == {"etapa", "motivo", "siguiente_paso", "intentos"},
                    f"y no sale ningun campo de mas en {e['etapa']}")

print("\n--- el paso al registro del turno ---")
llamadas = [
    {"herramienta": "consultar_mi_servicio", "identidad": None},
    {"herramienta": "consultar_mi_servicio",
     "identidad": {"etapa": "bloqueo", "motivo": "IDENTIDAD_NO_VERIFICADA",
                   "siguiente_paso": "espera_cedula", "intentos": 0}},
    {"herramienta": "verificar_identidad_por_cedula",
     "identidad": {"etapa": "verificacion_ok", "motivo": None,
                   "siguiente_paso": "espera_nombre", "intentos": 0}},
    {"herramienta": "derivar_a_area"},
    None,
]
ev = eventos_identidad_de(llamadas)
afirmar(len(ev) == 2, f"solo pasan las llamadas con evento (pasaron {len(ev)})")
afirmar([x["herramienta"] for x in ev] == ["consultar_mi_servicio", "verificar_identidad_por_cedula"],
        "cada evento lleva la herramienta que lo produjo")
afirmar(ev[0]["etapa"] == "bloqueo" and ev[1]["etapa"] == "verificacion_ok",
        "y conserva la clasificacion tal cual")
afirmar(eventos_identidad_de(None) == [] and eventos_identidad_de([]) == [],
        "sin llamadas, sin eventos, sin excepcion")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] El embudo de identidad se clasifica bien, y sin un solo dato del cliente.")
