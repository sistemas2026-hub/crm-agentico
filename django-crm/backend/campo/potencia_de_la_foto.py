# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE DICE LA FOTO CONTRA LO QUE ESCRIBIO EL TECNICO  --  07/11/2026
================================================================================
El usuario, mirando la inspeccion de «Medicion al llegar» en la OT #187:

    «vamos desde aqui de medicion al llegar mira lo que respondio»

El modelo habia leido bien: «la pantalla se lee: 1310 nm, "Lo" y -70.00 dBm».
Ese numero es el dato mas importante de esa foto -- «Lo» es perdida de senal
-- y quedaba escrito en un parrafo y ahi moria.

Mientras tanto el tecnico escribe A MANO «Potencia al llegar: X dBm» en su
reporte. Nadie comparaba los dos. En la OT #186 escribio -21.0 dBm al llegar
Y al salir, identicos, que es justo el patron que conviene poder contrastar
contra lo que la foto muestra.

EL CODIGO CALCULA, EL MODELO SOLO DESCRIBE (CLAUDE.md §4). El modelo no juzga
si dos lecturas coinciden ni resta: escribe lo que ve, y de ese texto el
codigo saca el numero con una expresion regular y compara. Un juicio que
dependa de que el modelo reste no se puede auditar.

POR QUE NO SE REUSA `paso_a_despacho.niveles_reportados`
--------------------------------------------------------
Hace casi esto y se lo evaluo primero. Descarta todo lo que caiga fuera de
-45..-5 dBm, y con razon: lee tickets, donde el numero sale de una ONU y uno
de -70 seria un error de tipeo o un dato de otra cosa.

Aca la fuente es la pantalla de un medidor de mano, que SI baja de -45: la
foto que origino esto dice -70.00 dBm con el indicador «Lo». Reusar ese rango
habria descartado justo la lectura que importa.

LO QUE NO HACE
--------------
**No decide si el trabajo se cierra.** Devuelve un punto de la revision, como
los demas; quien decide es `revision_del_cierre`.

**No afirma cuando no puede.** Sin numero en la foto, o sin numero escrito
por el tecnico, el punto queda en «no se sabe» -- nunca en «no cumple». Una
foto que el modelo no supo leer no es un tecnico que mintio.
================================================================================
"""
from __future__ import annotations

import math
import re

#:  UN NIVEL, tal como aparece escrito: "-70.00 dBm", "-21,0dBm", "-7 dBm".
#:  El signo es obligatorio -- una potencia optica recibida es negativa, y sin
#:  exigirlo "1310 nm" y "2 KHz" entrarian como lecturas.
_UN_NIVEL = r"-\s?\d{1,2}(?:[.,]\d{1,3})?"
_DBM = re.compile(_UN_NIVEL + r"\s*dbm", re.IGNORECASE)

#:  EL RANGO QUE UN MEDIDOR DE MANO PUEDE DAR. Mas ancho que el de
#:  `paso_a_despacho` (-45..-5) por el motivo de la cabecera: la foto que
#:  origino esto marca -70.00. El tope de abajo corta en -80 porque por
#:  debajo de eso ningun medidor del mercado lee: lo que venga mas abajo es
#:  un numero de otra cosa que quedo en la frase.
MINIMO = -80.0
MAXIMO = -1.0

#:  Cuanto pueden diferir las dos lecturas y seguir siendo "la misma".
#:
#:  POR QUE EXISTE UNA TOLERANCIA. Dos instrumentos distintos en el mismo
#:  punto no dan el mismo numero: el medidor de mano del tecnico y lo que el
#:  escribe redondean distinto, y la foto se saca en un momento y el dato se
#:  anota en otro. Sin margen, toda orden volveria por el ultimo decimal.
#:
#:  DE 3.0 A 2.0  --  decision del usuario, 10/11/2026, OT #200
#:  -----------------------------------------------------------
#:  El 09/11 se eligio 3.0 entre tres opciones (3 dBm, ~6 dBm, o no
#:  devolver), y esto la reabre con la medicion que faltaba: el usuario
#:  cerro la OT #200 escribiendo -18.0 con la pantalla marcando -21.0, A
#:  PROPOSITO, para ver la devolucion. No llego. Son exactamente 3.0 y la
#:  comparacion es `<=`, asi que para el sistema esos dos numeros eran el
#:  mismo. La diferencia que el usuario considera reportable caia justo del
#:  lado de adentro.
#:
#:  Elegido con el costo a la vista: en potencia optica 3 dB es la mitad de
#:  la senal, y 2.0 sigue perdonando el redondeo del tecnico y la lectura
#:  imprecisa del modelo. Si aparecen devoluciones por ruido de medicion,
#:  el numero a mirar es cuantas ordenes caen entre 2.0 y 3.0.
#:
#:  NO ES LO QUE ARREGLA LA MALA LECTURA DEL MODELO. Eso es otra cosa --el
#:  punto decimal corrido, medido 3 de 7 veces el 10/11-- y se ataca leyendo
#:  la foto dos veces, no moviendo este numero.
TOLERANCIA_DBM = 2.0


#:  LO QUE EL MEDIDOR MUESTRA EN LA OTRA UNIDAD. "0.682 µW", "0.000 uW",
#:  "7.94 microwatts". Sin signo: una potencia en µW es positiva.
_MICROWATTS = re.compile(
    r"(\d{1,6}(?:[.,]\d{1,4})?)\s*(?:µ|u|μ)\s*w\b"
    r"|(\d{1,6}(?:[.,]\d{1,4})?)\s*microwatts?\b",
    re.IGNORECASE)

#:  CUANTO PUEDEN DIFERIR LAS DOS UNIDADES Y SEGUIR SIENDO LA MISMA LECTURA.
#:
#:  El display redondea las dos a pocos decimales, asi que la conversion
#:  nunca da exacto. 1.0 dB es holgado a proposito: lo que esto busca no es
#:  un desajuste fino sino una lectura IMPOSIBLE, y las que importan fallan
#:  por decenas de dB. Medido el 12/11/2026 sobre la foto de la OT #214:
#:
#:      el modelo leyo   -2.10 dBm  y  0.682 µW
#:      -2.10 dBm serian          616.6 µW
#:      0.682 µW serian           -31.7 dBm
#:
#:  casi 30 dB de diferencia. Un umbral de 1.0 no deja pasar nada de eso y
#:  perdona cualquier redondeo real.
TOLERANCIA_CRUZADA_DB = 1.0

#:  Por debajo de esto el display esta en su piso ("0.000 µW") y no dice
#:  nada: es consistente con cualquier dBm muy bajo. No se verifica.
MICROWATTS_MINIMOS = 0.0005


def microwatts(texto: str) -> float | None:
    """Los µW que el medidor muestra, o None si no vienen o hay mas de uno.

    Con dos numeros no se verifica nada, por el mismo motivo que
    `uno_solo`: elegir uno seria inventar la mitad del juicio.
    """
    vistos = []
    for a, b in _MICROWATTS.findall(texto or ""):
        try:
            v = float((a or b).replace(",", "."))
        except ValueError:
            continue
        if v not in vistos:
            vistos.append(v)
    return vistos[0] if len(vistos) == 1 else None


def dbm_de_microwatts(uw: float) -> float | None:
    """La misma potencia, en dBm. `dBm = 10 * log10(mW)`, y 1 mW = 1000 µW."""
    try:
        if uw is None or uw <= 0:
            return None
        return 10.0 * math.log10(float(uw) / 1000.0)
    except (TypeError, ValueError):
        return None


def coherente_con_los_microwatts(texto: str) -> tuple[bool | None, str]:
    """¿El dBm y el µW de esta pantalla son el mismo valor?

    POR QUE ESTO EXISTE  --  12/11/2026
    ------------------------------------
    El modelo corre el punto decimal al leer un medidor: dice «-2.10» donde
    la pantalla muestra «-21.0». Se atacó de dos formas y ninguna alcanzó:

      * la DOBLE LECTURA (11/11) ataca la varianza, y esto resultó ser
        SESGO -- 4 de 4 lecturas de la misma foto dijeron -2.10, una de
        ellas agregando «punto decimal visible»;
      * el RANGO DE LA EMPRESA en el pie (11/11) sí llegó y el modelo sí lo
        usó --contestó «lectura legible, fuera del rango declarado»-- y
        reportó -2.10 igual. La instrucción le daba permiso explícito: «si
        después de mirarlo otra vez seguís leyendo lo mismo, escribí lo que
        ves». Obedeció.

    Esto es otra cosa: **no le pide al modelo que se corrija**. Un medidor
    óptico muestra la MISMA potencia en dBm y en µW, y son convertibles. Si
    los dos números que el modelo leyó de una sola pantalla no son el mismo
    valor, la lectura no sirve -- cualquiera sea cuál de los dos está mal.

    Es más fuerte que el rango por dos motivos: es física y no configuración
    (no depende de la planta de ninguna empresa), y no requiere que el
    modelo admita nada.

    DEVUELVE None CUANDO NO SE PUEDE SABER, y eso es la mitad del valor:
      * la lectura no trae µW, o trae más de uno
      * el µW está en el piso del display ("0.000"), consistente con
        cualquier dBm muy bajo -- es el caso de toda foto de «al llegar» con
        pérdida de señal
      * no hay un solo dBm que comparar

    Medido sobre las lecturas reales de producción del 11 y 12/11/2026: el
    µW viene en 10 de 10 textos no vacíos.
    """
    dbm = uno_solo(texto)
    if dbm is None:
        return None, "no hay un solo dBm que verificar"
    uw = microwatts(texto)
    if uw is None:
        return None, "la lectura no trae los µW"
    if uw < MICROWATTS_MINIMOS:
        return None, "los µW están en el piso del display: no dicen nada"
    equivalente = dbm_de_microwatts(uw)
    if equivalente is None:
        return None, "los µW no se pudieron convertir"
    diferencia = abs(dbm - equivalente)
    if diferencia <= TOLERANCIA_CRUZADA_DB:
        return True, (f"{dbm} dBm y {uw} µW son la misma potencia "
                      f"(±{diferencia:.1f} dB)")
    return False, (f"la pantalla no puede decir {dbm} dBm y {uw} µW a la vez: "
                   f"esos µW son {equivalente:.1f} dBm, "
                   f"{diferencia:.0f} dB de diferencia")


def niveles(texto: str) -> list[float]:
    """Los dBm que trae un texto, en orden y sin repetir el mismo dos veces.

    Del texto del analisis de la foto, o del que escribio el tecnico: los dos
    son texto libre y se leen igual.
    """
    salida = []
    for bruto in _DBM.findall(texto or ""):
        crudo = bruto.replace(" ", "").replace(",", ".")
        crudo = crudo[:-3] if crudo.lower().endswith("dbm") else crudo
        try:
            valor = float(crudo)
        except ValueError:
            continue
        if not (MINIMO <= valor <= MAXIMO):
            continue
        if valor not in salida:
            salida.append(valor)
    return salida


def uno_solo(texto: str) -> float | None:
    """El unico nivel del texto, o `None` si no hay o hay mas de uno.

    CON DOS NUMEROS NO SE COMPARA. Una foto donde el modelo leyo dos lecturas
    --la de la ONU y la de la OLT, o una pantalla con historial-- no dice cual
    es la que el tecnico anoto, y elegir una seria inventar la mitad del
    juicio. Se prefiere «no se sabe» a una coincidencia sacada a la suerte.
    """
    v = niveles(texto)
    return v[0] if len(v) == 1 else None


def comparar(de_la_foto: float | None,
             del_tecnico: float | None) -> tuple[bool | None, str]:
    """`(coinciden, por_que)`. `None` cuando falta alguno de los dos.

    `coinciden=False` es una afirmacion fuerte --el numero escrito no salio de
    esa pantalla-- y por eso solo se da con los dos numeros en la mano.
    """
    if de_la_foto is None or del_tecnico is None:
        return None, "no se pudo leer la potencia en los dos lados"
    diferencia = abs(de_la_foto - del_tecnico)
    if diferencia <= TOLERANCIA_DBM:
        return True, (f"la foto marca {de_la_foto:.1f} dBm y el reporte dice "
                      f"{del_tecnico:.1f} dBm")
    return False, (f"la foto marca {de_la_foto:.1f} dBm y el reporte dice "
                   f"{del_tecnico:.1f} dBm: {diferencia:.1f} dBm de "
                   f"diferencia")
