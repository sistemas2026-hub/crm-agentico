# -*- coding: utf-8 -*-
"""
================================================================================
 EL COTEJO NO PUEDE EQUIVOCARSE HACIA EL «SI»  --  12/11/2026
================================================================================
`nucleo/canales/cotejo.py` compara lo que se pidio contra lo que el tecnico
reporto. El usuario: «no puede haber una respuesta correcta en un asunto que
ni por ahi iba al caso».

LA ASIMETRIA QUE ESTAS GUARDAS PROTEGEN
----------------------------------------
Los dos errores no cuestan lo mismo:

  decir «no cuadra» cuando cuadraba  -> alguien mira una orden de mas
  decir «cuadra» cuando no cuadraba  -> un cliente sin servicio, un ticket
                                        cerrado, y nadie se entero

Por eso TODO lo que sale mal --el proveedor caido, una respuesta fuera de
formato, un lado vacio-- tiene que dar `no_se_sabe`, jamas `si`. La mitad de
este archivo mide exactamente eso, porque es el unico error que no se ve
desde afuera: una orden que cerro sola y no debia se ve igual que una que
cerro bien.

DOS DEFENSAS, Y CADA UNA TIENE SU GUARDA -- MEDIDO
---------------------------------------------------
El fail-closed no es un `if`: son dos capas, y se rompieron por separado
para comprobar que las dos estan medidas.

  mutacion                                        muere
  ---------------------------------------------   ---------------------------
  `_normalizar` devuelve CUADRA por defecto        «deja el veredicto en
  (la palabra no reconocida pasa como si)           blanco»
  `leer` interpreta el texto crudo cuando falta    «contesta en prosa»
  la linea marca (lo lee «a ojo»)

Cada mutacion mata UNA sola guarda, y son guardas distintas. Si alguna de
las dos lineas de esa tabla deja de tener su caso, esa capa queda sin medir
y el archivo entero sigue en verde.

NO SE LLAMA AL MODELO EN NINGUNA DE ESTAS PRUEBAS. El cliente se sustituye:
lo que se mide es la decision del codigo, no la conducta del proveedor --que
tiene varianza y no corre en CI (CLAUDE.md §6).

Se corre sola:  py -3.13 tests/test_cotejo_reporte_contra_ticket.py
================================================================================
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nucleo.canales import cotejo as C  # noqa: E402

FALLAS: list[str] = []


def afirmar(condicion, mensaje: str) -> None:
    if condicion:
        print(f"  [ok] {mensaje}")
    else:
        print(f"  [FALLA] {mensaje}")
        FALLAS.append(mensaje)


class _Respuesta:
    def __init__(self, contenido):
        self.contenido = contenido
        self.tokens_entrada = 120
        self.tokens_salida = 30


def _contesta(texto):
    """Sustituye al cliente del modelo por uno que contesta eso."""
    def chat(modelo, mensajes, **kw):
        _contesta.ultimos = mensajes
        return _Respuesta(texto)
    C.cliente_modelo.chat = chat


def _revienta(excepcion):
    def chat(modelo, mensajes, **kw):
        raise excepcion
    C.cliente_modelo.chat = chat


#  EL CASO REAL DEL 12/11/2026, pegado de la pantalla de produccion.
SE_PIDIO = ("Segun el Supervisor: El cliente pide el cambio de router wifi "
            "como gestion comercial/tecnica, no por una falla: el equipo "
            "esta en linea y con senal buena.")
QUE_HIZO = ("Potencia al llegar: -50.0 dBm. Que encontro: fibra partida "
            "antes del conector. Que hizo: se prepara nuevamente el conector "
            "y se restablece el servicio. Potencia al salir: -21.0 dBm.")

print(__doc__)

# ---------------------------------------------------------------------------
#  1) LOS TRES VEREDICTOS LLEGAN ENTEROS
# ---------------------------------------------------------------------------
print("\n1) el veredicto del modelo llega sin cambiarse")

_contesta("CUADRA: no\nPOR QUE: el ticket dice que el equipo estaba en linea "
          "y el reporte describe una fibra partida")
r = C.cotejar(SE_PIDIO, QUE_HIZO, "x/y")
afirmar(r.veredicto == C.NO_CUADRA, f"el caso real da 'no' (dio {r.veredicto})")
afirmar(r.contradice, "y `contradice` lo dice sin que nadie compare cadenas")
afirmar("fibra partida" in r.motivo,
        "el motivo cita lo concreto de cada lado, no «no coinciden»")

_contesta("CUADRA: si\nPOR QUE: el conector sucio explica el sintoma")
afirmar(C.cotejar(SE_PIDIO, QUE_HIZO, "x/y").veredicto == C.CUADRA,
        "un 'si' llega como 'si'")

_contesta("CUADRA: no se sabe\nPOR QUE: el reporte no dice que encontro")
afirmar(C.cotejar(SE_PIDIO, QUE_HIZO, "x/y").veredicto == C.NO_SE_SABE,
        "y un 'no se sabe' tambien")

# ---------------------------------------------------------------------------
#  2) TODO LO QUE SALE MAL CAE AL «NO SE SABE», NUNCA AL «SI»
# ---------------------------------------------------------------------------
print("\n2) ningun error puede producir un «cuadra»")

for texto, como in (
    ("Si, cuadra perfectamente con lo que se pidio.", "contesta en prosa"),
    ("La verdad es que no sabria decirte.", "divaga"),
    ("", "contesta vacio"),
    ("CUADRA:\nPOR QUE: algo", "deja el veredicto en blanco"),
    ("cuadra si", "escribe la marca sin los dos puntos"),
    ("POR QUE: hay una contradiccion", "manda el motivo sin el veredicto"),
):
    _contesta(texto)
    v = C.cotejar(SE_PIDIO, QUE_HIZO, "x/y").veredicto
    afirmar(v == C.NO_SE_SABE,
            f"si el modelo {como}, es 'no se sabe' (dio '{v}')")

_revienta(TimeoutError("el proveedor no contesto"))
r = C.cotejar(SE_PIDIO, QUE_HIZO, "x/y")
afirmar(r.veredicto == C.NO_SE_SABE,
        f"si el proveedor se cae, es 'no se sabe' (dio '{r.veredicto}')")
afirmar(r.error == "TimeoutError",
        f"y queda el TIPO del error, para poder contarlo (dio '{r.error}')")

_revienta(RuntimeError("clave invalida: sk-abc123"))
r = C.cotejar(SE_PIDIO, QUE_HIZO, "x/y")
afirmar("sk-abc123" not in (r.error + r.motivo),
        "el mensaje del proveedor NO se propaga: puede traer de vuelta lo "
        "que se le mando, o una credencial")

# ---------------------------------------------------------------------------
#  3) SIN UNO DE LOS DOS LADOS NO SE LE PREGUNTA A NADIE
# ---------------------------------------------------------------------------
print("\n3) un lado vacio no se consulta: se contesta gratis")

llamo = {"si": False}


def _marca(modelo, mensajes, **kw):
    llamo["si"] = True
    return _Respuesta("CUADRA: si\nPOR QUE: lo que sea")


C.cliente_modelo.chat = _marca

r = C.cotejar("", QUE_HIZO, "x/y")
afirmar(r.veredicto == C.NO_SE_SABE and not llamo["si"],
        "sin lo que se pidio: 'no se sabe' y NO se llamo al proveedor")
afirmar("falta lo que se pidio" in r.motivo,
        "y dice cual de los dos lados falta")

llamo["si"] = False
r = C.cotejar(SE_PIDIO, "   ", "x/y")
afirmar(r.veredicto == C.NO_SE_SABE and not llamo["si"],
        "sin el reporte del tecnico: igual, y sin pagar")
afirmar("no escribio" in r.motivo, "y lo dice con esas palabras")

# ---------------------------------------------------------------------------
#  4) LO QUE VIAJA AL PROVEEDOR, Y LO QUE VUELVE
# ---------------------------------------------------------------------------
print("\n4) lo que sale y lo que entra")

_contesta("CUADRA: no\nPOR QUE: algo")
C.cotejar(SE_PIDIO, QUE_HIZO, "x/y")
mensajes = _contesta.ultimos
afirmar(len(mensajes) == 2 and mensajes[0]["role"] == "system",
        "van dos mensajes: la instruccion y los dos textos")
afirmar("no puede estar en linea" not in mensajes[0]["content"].lower()
        and "NO ACUSES A NADIE" in mensajes[0]["content"],
        "la instruccion le prohibe acusar, que es como contesta sin eso")
afirmar("LO QUE SE PIDIO" in mensajes[1]["content"]
        and "LO QUE EL TECNICO REPORTO" in mensajes[1]["content"],
        "los dos lados van rotulados: sin rotulo el modelo no sabe cual es cual")

largo = "palabra " * 900
C.cotejar(largo, QUE_HIZO, "x/y")
afirmar(len(_contesta.ultimos[1]["content"]) < 2 * C.TOPE_POR_LADO + 200,
        f"un texto enorme se recorta a {C.TOPE_POR_LADO} por lado")

#  LA REDACCION A LA SALIDA. El motivo lo escribe el modelo citando los dos
#  textos, y esos textos son de personas.
_contesta("CUADRA: no\nPOR QUE: el reporte menciona la cedula 1098765432 "
          "del cliente y el ticket no")
r = C.cotejar(SE_PIDIO, QUE_HIZO, "x/y")
afirmar("1098765432" not in r.motivo,
        f"una cedula en el motivo se tapa antes de devolverlo (dio: {r.motivo})")

# ---------------------------------------------------------------------------
#  5) EL TIMEOUT ES EL CORTO, PORQUE NADIE ESPERA ESTO
# ---------------------------------------------------------------------------
print("\n5) el trabajo secundario usa el tope corto")

visto = {}


def _mira_timeout(modelo, mensajes, **kw):
    visto.update(kw)
    return _Respuesta("CUADRA: si\nPOR QUE: x")


C.cliente_modelo.chat = _mira_timeout
C.cotejar(SE_PIDIO, QUE_HIZO, "x/y")
afirmar(visto.get("timeout") == C.cliente_modelo.TIMEOUT_SECUNDARIO,
        f"pasa TIMEOUT_SECUNDARIO ({C.cliente_modelo.TIMEOUT_SECUNDARIO}s), "
        f"no el de la respuesta que un cliente espera (dio {visto.get('timeout')})")
afirmar(visto.get("temperatura") == 0.0,
        "y temperatura 0: esto es un juicio, no una redaccion")

print()
if FALLAS:
    print(f"FALLARON {len(FALLAS)}:")
    for f in FALLAS:
        print(f"  - {f}")
    sys.exit(1)
print("[OK] El cotejo nunca dice «cuadra» por un error, y sin los dos lados "
      "no le pregunta a nadie.")
