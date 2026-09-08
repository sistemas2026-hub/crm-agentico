# -*- coding: utf-8 -*-
"""
================================================================================
 UN PASE QUE YA OCURRIO NO SE ANUNCIA
================================================================================

Por que existe
--------------
Cuando el modelo deriva, el area destino contesta EN ESE MISMO TURNO. Si esa
respuesta dice "te paso con ventas", el cliente se queda esperando a alguien
que ya hablo -- y como el turno termina ahi, para el es identico a que la
derivacion nunca hubiera ocurrido. Tiene que escribir de nuevo.

Medido tres veces el 08/09/2026 en el simulador, con la derivacion CONFIRMADA
en la traza (derivar_a_area + consultar_servicios_ofrecidos, las dos con
exito):

    "Dejame revisar que servicios ofrecemos para contarte bien."
    "...pero te paso con el equipo de ventas que te asesora."
    "...pero dejame pasarte con el area de ventas que te confirma."

La instruccion de no hacerlo YA existia en dos lugares -- el resultado de
derivar_a_area ("No le anuncies al cliente que lo derivaste") y persona
("NUNCA cierres un turno con una promesa")-- y se desobedecio igual, en 2 de 3
corridas. PRD 7.4: el prompt guia, el codigo garantiza.

Lo que se fija
--------------
1. LOS TRES CASOS MEDIDOS SE DETECTAN. Son el texto real, copiado de la base.

2. LA ESCALADA A UNA PERSONA NO SE TOCA. "Te paso con un compañero del equipo"
   es correcto y su propio prompt lo exige. Es el falso positivo que hace
   peligrosa esta guarda, y por eso tiene caso propio.

3. NO SE DETECTA POR LAS PALABRAS SOLAS. La señal es la TRAZA: si este turno
   llamo la herramienta de derivacion, quien redacta es el area destino y
   cualquier anuncio de pase es falso. Sin ese hecho no se evalua nada.

4. SE REHACE, NO SE BLOQUEA. Va como tercer motivo del bucle de reintento que
   ya existe en _redactar (junto a "vino vacia" y "es un valor crudo"), con su
   propia correccion: a una redaccion vacia hay que decirle que escriba; a esta,
   que el pase ya lo hizo ella.

Corre SIN BASE DE DATOS y sin red: el detector es una funcion pura.

Uso
---
    py -3.13 tests/test_pase_no_se_anuncia.py
================================================================================
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.config.schema import _sin_tildes                           # noqa: E402
from nucleo.modelo import motor                                        # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


# Como las arma el motor desde la config: nombres de rol mas la etiqueta de
# area de cada uno ('ventas', 'Ventas', 'soporte_tecnico_cliente', ...).
AREAS = {_sin_tildes(x) for x in
         ("ventas", "Ventas", "soporte_tecnico_cliente", "Soporte Tecnico",
          "facturacion_cliente", "Facturacion")}


print("== 1. los tres casos medidos el 08/09/2026 ==")

MEDIDOS = [
    ("Dejame revisar que servicios ofrecemos para contarte bien.",
     "promesa pura: el cliente no recibe NADA"),
    ("Te cuento que la telefonia fija no la ofrecemos por ahora, pero te paso "
     "con el equipo de ventas que te asesora con lo que necesitas.",
     "trae el dato, pero lo deja esperando un pase que ya ocurrio"),
    ("Hola! Te comento que la telefonia fija no la manejamos directamente, "
     "pero dejame pasarte con el area de ventas que te confirma que opciones "
     "hay disponibles.",
     "las dos cosas juntas: anuncia el pase y promete el dato"),
]
for texto, que in MEDIDOS:
    afirmar(motor._promete_en_vez_de_responder(texto, AREAS) is not None,
            f"se detecta -- {que}")


print("\n== 2. la escalada a una PERSONA no se toca ==")
# El falso positivo que hace peligrosa esta guarda. El prompt EXIGE avisarle al
# cliente cuando un humano toma el caso ("dile al cliente que un colaborador
# humano sigue el caso"), y ese aviso usa las mismas palabras.
for texto in (
    "Entiendo tu molestia. Te paso con un compañero del equipo que va a "
    "revisar tu caso ahora mismo.",
    "Eso lo tengo que confirmar con un compañero del equipo. Le paso tu caso "
    "y te responde por aca.",
    "Perdon, no estoy logrando resolverlo por aca. Te paso con un compañero "
    "del equipo que lo va a revisar con mas detalle.",
):
    afirmar(motor._promete_en_vez_de_responder(texto, AREAS) is None,
            f"pasa sin tocarse: '{texto[:48]}...'")

afirmar(motor._promete_en_vez_de_responder(
            "Te paso con un colaborador humano que sigue tu caso.", AREAS) is None,
        "y 'colaborador humano' tampoco -- ninguno nombra un AREA, que es lo "
        "que distingue un pase interno de un traspaso a una persona")


print("\n== 3. una respuesta que SI responde pasa ==")
for texto in (
    "Te cuento que ofrecemos internet residencial y television en los planes "
    "combo. En que barrio vives para verificar cobertura?",
    "Si, tenemos CNN en la parrilla de canales. Te interesa algun plan con TV?",
    "Ese canal no lo veo en la parrilla. Te referias a Win Sports?",
    "Tu plan es el PLAN HOGAR y cuesta 75.000 al mes.",
):
    afirmar(motor._promete_en_vez_de_responder(texto, AREAS) is None,
            f"pasa: '{texto[:52]}...'")


print("\n== 4. la señal es la TRAZA, no las palabras ==")
# El detector solo se consulta si el turno derivo de verdad. Se comprueba en la
# firma y en el cuerpo de _redactar, que es donde vive la condicion.
firma = inspect.signature(motor._redactar).parameters
afirmar("paso_a_otra_area" in firma and "nombres_area" in firma,
        "_redactar recibe el hecho de la traza, no lo deduce del texto")
afirmar(firma["paso_a_otra_area"].default is False,
        "y por defecto NO evalua nada: sin derivacion confirmada, esta guarda "
        "no existe -- asi la escalada a humano queda fuera de su alcance")

cuerpo = inspect.getsource(motor._redactar)
afirmar("paso_a_otra_area" in cuerpo and "_promete_en_vez_de_responder" in cuerpo,
        "el bucle lo usa de verdad")
afirmar("if intento == 0:" in cuerpo and "muerta" in cuerpo,
        "y tiene su propia correccion para el reintento, distinta de la de "
        "una redaccion vacia")

fuente_motor = inspect.getsource(motor)
afirmar("h.deriva_rol" in fuente_motor and "paso_a_otra_area=paso" in fuente_motor,
        "quien deriva se resuelve por el marcador 'deriva_rol' de la config, "
        "no por el nombre 'derivar_a_area' -- otro tenant puede llamarla "
        "distinto")


print("\n== 5. se REHACE, no se bloquea ==")
# Bloquear dejaria al cliente sin respuesta, que es el mismo mal que se
# persigue. El bucle pide otra redaccion, igual que hace con una vacia.
afirmar("intentos: int = 3" in cuerpo,
        "hay reintentos disponibles (los mismos que ya existian)")
afirmar("not muerta" in cuerpo,
        "una redaccion muerta NO se devuelve: se vuelve a pedir")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] Un pase que ya ocurrio no se anuncia, y avisar de una persona sigue intacto.")
