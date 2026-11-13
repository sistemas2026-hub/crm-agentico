# -*- coding: utf-8 -*-
"""
================================================================================
 LA FIRMA QUE LA PANTALLA USA PARA ESCONDER EL ECO  --  07/11/2026
================================================================================
Cada avance del tecnico se escribe en los dos sistemas: una nota interna en
Dexter y una respuesta en WispHub. La pantalla del ticket junta las dos
fuentes, asi que el usuario veia cada aviso repetido:

    Rapilink SAS WISPHUB   Mario Vasquez (Dexter): va en camino a la OT #198.
    mario.vasquez...       Mario Vasquez: va en camino.

Se esconde la del proveedor y NO se deja de escribir -- el dia que WispHub
rechace el envio, la nota de Dexter es lo unico que queda. Decision del
usuario el 07/11/2026, con ese caso a la vista: ese mismo dia un 400 dejo el
reporte de la OT #198 solo en Dexter.

POR QUE ESTA GUARDA EXISTE
--------------------------
La pantalla reconoce lo nuestro POR LA FIRMA, y esa firma la emite el motor.
Una vive en JavaScript (`frontend/src/lib/server/v2/tickets.js::esNuestro`) y
la otra en Python: nada impide cambiar una sin la otra, y el sintoma no es un
error sino que la pantalla DEJA DE ESCONDER, en silencio, y el duplicado
vuelve sin que nadie lo note hasta que un usuario lo ve.

Esta guarda ata los dos lados: afirma que TODA firma que el motor puede
emitir sigue entrando en la regla que la pantalla aplica. Si alguien cambia
una firma, esto se pone rojo y dice exactamente por que.

LA REGLA, copiada de `esNuestro` a proposito: lo que esta antes del primer
':', si ese ':' aparece dentro de los primeros 80 caracteres, y termina en
'(Dexter)' o es exactamente 'Supervisor de Dexter'.

Se corre sola: `py -3.13 tests/test_la_firma_que_la_pantalla_esconde.py`
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.seguimiento import nota_en_el_ticket as N      # noqa: E402
from nucleo.seguimiento.operativo import _firmado          # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


def la_pantalla_lo_esconde(cuerpo: str) -> bool:
    """La misma regla que `esNuestro`, en Python. Si cambia alla, cambia aca
    -- y el commit que toque una sin la otra tiene que explicar por que."""
    texto = (cuerpo or "").lstrip()
    corte = texto.find(":")
    if corte < 0 or corte > 80:
        return False
    firma = texto[:corte]
    return firma.endswith("(Dexter)") or firma == "Supervisor de Dexter"


print("== 1. toda firma que el motor emite, la pantalla la reconoce ==")

#  TODOS los momentos declarados, con y sin actor: son los dos caminos de
#  `_firma_de`, y ninguno puede quedarse afuera.
for momento in sorted(N.MOMENTOS):
    for actor in ("MARIO VASQUEZ", ""):
        firma = N._firma_de(momento, actor)
        cuerpo = _firmado("va en camino a la OT #198.", firma)
        afirmar(la_pantalla_lo_esconde(cuerpo),
                f"{momento} con actor {'si' if actor else 'no'} -> «{firma}»")

#  Y el fallback, que es el que sale cuando el momento no esta en el mapa.
afirmar(la_pantalla_lo_esconde(_firmado("x", N._firma_de("inventado", ""))),
        "un momento que el mapa no tiene cae en la firma del Supervisor, y "
        "tambien se reconoce")


print()
print("== 2. lo que NO es nuestro se sigue viendo ==")

ajenos = [
    "Cliente: no tengo internet desde ayer",
    "Se realiza visita, se cambia conector. Niveles -21 dbm",
    "",
    "sin dos puntos en todo el texto",
    #  Un texto largo que menciona Dexter mucho despues: el tope de 80 existe
    #  para que una frase del cliente no se tome por una firma.
    ("una respuesta larguisima escrita a mano por alguien del equipo que "
     "sigue y sigue y recien aca menciona (Dexter): y despues dos puntos"),
]
for cuerpo in ajenos:
    afirmar(not la_pantalla_lo_esconde(cuerpo),
            f"se muestra: «{(cuerpo or '(vacio)')[:45]}»")


print()
print("== 3. las tres firmas siguen diciendo 'Dexter' ==")

#  Lo que la regla de la pantalla da por sentado, afirmado sobre las
#  constantes: si alguien saca 'Dexter' de una, arriba falla y aca se dice
#  cual fue.
afirmar(N.FIRMA_DE_CAMPO.endswith("(Dexter)"),
        f"FIRMA_DE_CAMPO = «{N.FIRMA_DE_CAMPO}»")
afirmar(N.FIRMA_DEL_SUPERVISOR == "Supervisor de Dexter",
        f"FIRMA_DEL_SUPERVISOR = «{N.FIRMA_DEL_SUPERVISOR}»")
afirmar(N._firma_de(N.REPORTE_DEL_TECNICO, "ANA").endswith("(Dexter)"),
        "la firma con nombre tambien")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    print("\nSi cambiaste una firma a proposito, hay que cambiar tambien "
          "`esNuestro` en frontend/src/lib/server/v2/tickets.js, o la "
          "pantalla deja de esconder el eco EN SILENCIO y el duplicado vuelve.")
    raise SystemExit(1)
print("[OK] La pantalla reconoce todo lo que el motor firma, y nada mas.")
