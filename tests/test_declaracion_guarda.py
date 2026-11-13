# -*- coding: utf-8 -*-
"""
La guarda de 'exige_declaracion': lo que el cliente DIJO, validado en codigo.

Nace de algo medido, no de una hipotesis. El 22/09/2026, contra el motor real
y cuatro corridas del mismo caso dorado, 'reiniciar_ont' reinicio el equipo de
un cliente real ante una queja de LENTITUD en una de las cuatro. La regla que
lo prohibia vivia en la descripcion de la herramienta -- o sea, en el prompt.

Lo que se afirma aca es el EFECTO: que un valor ausente o fuera de la lista
NO ejecute. No que el campo exista.

Sin red y sin modelo: se prueban las dos funciones puras que deciden.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config.schema import Declaracion, Herramienta  # noqa: E402
from nucleo.modelo.motor import _declaracion_no_alcanza, _esquema_openai  # noqa: E402

fallos = []


def afirmar(condicion, que):
    if condicion:
        print(f"  [ok]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


DECL = Declaracion(
    param="sintoma",
    valores=["sin_servicio", "intermitente", "lento"],
    aceptados=["sin_servicio", "intermitente"],
    pregunta="Que reporto el cliente?",
    si_no_alcanza="Deriva en vez de reiniciar.",
)

CON_GUARDA = Herramienta(nombre="reiniciar_ont", tipo="http",
                         descripcion="x", endpoint="/x", metodo="POST", base_url="http://x",
                         roles_permitidos=["soporte"], requiere_confirmacion=True,
                         exige_declaracion=DECL)
SIN_GUARDA = Herramienta(nombre="consultar_algo", tipo="http",
                         descripcion="x", endpoint="/x", metodo="GET", base_url="http://x",
                         roles_permitidos=["soporte"], solo_lectura=True)

print("\n--- el rechazo ---")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {"sintoma": "lento"}) == "lento",
        "un sintoma que NO corresponde no ejecuta, y el motivo lo nombra")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {}) == "",
        "el argumento AUSENTE no ejecuta -- no se asume el valor que convendria")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {"sintoma": None}) == "",
        "un null tampoco ejecuta")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {"sintoma": "inventado"}) == "inventado",
        "un valor que el modelo invento fuera del enum no ejecuta")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {"sintoma": ""}) == "",
        "un valor vacio no ejecuta")

print("\n--- lo que SI pasa ---")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {"sintoma": "sin_servicio"}) is None,
        "un sintoma aceptado ejecuta")
afirmar(_declaracion_no_alcanza(CON_GUARDA, {"sintoma": " sin_servicio "}) is None,
        "los espacios alrededor no cambian la decision")
afirmar(_declaracion_no_alcanza(SIN_GUARDA, {}) is None,
        "una herramienta sin la guarda no se ve afectada")

print("\n--- lo que ve el modelo ---")
esq = _esquema_openai(CON_GUARDA)
props = esq["function"]["parameters"]["properties"]
req = esq["function"]["parameters"]["required"]
afirmar("sintoma" in props, "el argumento llega al esquema de una herramienta SIN filtros")
afirmar("sintoma" in req, "y llega como requerido")
afirmar(props["sintoma"]["enum"] == ["sin_servicio", "intermitente", "lento"],
        "se le ofrece la opcion honesta ('lento') aunque el codigo la rechace")
afirmar("lento" not in DECL.aceptados,
        "y 'lento' NO esta entre las aceptadas -- si lo estuviera, no rechazaria nada")

esq2 = _esquema_openai(SIN_GUARDA)
afirmar(esq2["function"]["parameters"]["properties"] == {},
        "una herramienta sin guarda sigue sin argumentos")

print("\n" + "=" * 62)
if fallos:
    print(f" {len(fallos)} falla(s).")
    raise SystemExit(1)
print(" Todo en orden.")
