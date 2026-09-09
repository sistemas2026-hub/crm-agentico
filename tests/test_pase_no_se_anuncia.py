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


print("\n== 5b. el respaldo NO puede devolver lo que la guarda rechazo ==")
# Esta seccion existia el 09/09/2026 por la mañana y AFIRMABA LO CONTRARIO.
#
# El respaldo se agrego ese dia para un caso real: "buenas para una
# instalacion de telefonia" derivo bien, la redaccion se rechazo tres veces
# por prometer, y el cliente recibio "No pude terminar de redactar" -- o sea
# nada. El razonamiento fue "una promesa al menos dice algo".
#
# Es falso, y esa misma tarde se midio: con el numero 312 000 000, el cliente
# recibio "Dejame pasarte con el area de ventas" -- escrito POR ventas, un
# pase a si misma. Las dos formas dejan al cliente teniendo que escribir de
# nuevo, y la promesa es PEOR, porque parece que algo avanzo. La guarda habia
# quedado anulada por su propio respaldo.
#
# Y esta prueba no lo vio, porque afirmaba que la VARIABLE 'candidato'
# existiera -- no que se comportara de alguna forma. Sobrevivio intacta a una
# inversion completa de la conducta. Por eso ahora se afirma la CONDICION.
# La linea de guarda es la ANTERIOR a la asignacion. Se busca por indice y no
# por 'esta en el cuerpo', porque el mismo 'if' aparece dos veces en la
# funcion -- una para el candidato y otra para el retorno-- y buscar el texto
# suelto daria verde teniendo la condicion mal justo en la que importa.
_lineas = cuerpo.splitlines()
_i = next(i for i, l in enumerate(_lineas) if l.strip() == "candidato = limpio")
guarda = _lineas[_i - 1]
afirmar("not muerta" in guarda,
        "el texto que la guarda marco como promesa NO se guarda como "
        "candidato: si no, vuelve por la puerta de atras")
afirmar("if candidato:" in cuerpo,
        "el respaldo sigue existiendo -- para lo que si vino a resolver: una "
        "redaccion vacia o un valor crudo tras varios intentos")
afirmar(0 < cuerpo.find("if candidato:")
        < cuerpo.find("se agotaron los {intentos} intentos de redaccion"),
        "y va ANTES del aviso generico, que queda para cuando no hay "
        "absolutamente nada escrito")
afirmar("guardia_salida.verificar(candidato)" in cuerpo,
        "el respaldo pasa igual por la guardia de salida -- degradar la "
        "calidad de la respuesta no puede degradar lo que se filtra")


print("\n== 5c. el reintento va donde puede entrar informacion nueva ==")
# La leccion de fondo del 09/09/2026, y la razon de que esto se repitiera dos
# dias seguidos: la guarda solo sabe RECHAZAR texto. Cuando el area que entro
# por derivacion no consulto nada, no hay nada que redactar, y pedirle tres
# veces que reescriba devolvio las tres veces la MISMA frase, byte a byte.
#
# El reintento tiene que estar en el bucle del agente --la unica capa donde
# el modelo todavia puede llamar una herramienta-- y no en la redaccion final,
# que corre a proposito sin catalogo.
fuente_responder = fuente_motor
afirmar("registro_al_derivar" in fuente_responder,
        "se mide si el area que entro por derivacion consulto algo, o "
        "contesto sin mirar nada")
afirmar("reintentos_area_sin_consultar" in fuente_responder,
        "y en ese caso se le da otra vuelta del bucle, con su catalogo")
afirmar("reintentos_area_sin_consultar < 2" in fuente_responder,
        "con tope: un reintento sin limite gira solo y se come el turno. Dos "
        "y no una -- con una sola el area consulto en 2 de 3 corridas "
        "(09/09/2026); con dos, 5 de 5")
afirmar("_promete_en_vez_de_responder(limpio, nombres_area_conf)"
        in fuente_responder,
        "cuando contesto una promesa -- un area que contesta bien de una no "
        "paga nada")

# LOS DOS CAMINOS, y no solo el primero. El 09/09/2026 se arreglo unicamente
# "contesto una promesa", y esa misma tarde el humo cazo el otro: el area no
# contesto NADA, se fue directo a la redaccion final --que corre sin
# catalogo-- y los tres intentos produjeron la misma promesa.
#
# El sintoma en el log era la AUSENCIA de la linea de reintento: no fallaba,
# no se evaluaba. Por eso se afirma que el reintento se pide desde DOS sitios
# y con una sola funcion: dos copias se arreglan una sola vez.
afirmar(fuente_responder.count("_pedir_que_consulte(") >= 3,
        "el reintento se pide desde los DOS caminos (contesto una promesa, y "
        "no contesto nada), no solo del primero")
afirmar(fuente_responder.count("def _pedir_que_consulte") == 1,
        "y con UNA sola implementacion -- dos copias se arreglan una vez sola "
        "y la otra se queda vieja, que es justo lo que paso")


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
