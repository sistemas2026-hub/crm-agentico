# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE CONSUMO  --  un tope que no cuenta nada es peor que no tenerlo
================================================================================

Lo que estaba roto
------------------
'asistente.usage_daily' existe desde el primer esquema, con columnas para
tokens y costo, y NADIE escribia en ella. 'limites.max_costo_usd_mes' existe
en la configuracion desde entonces: un ADMIN podia ponerlo, se validaba, se
guardaba, y no podia dispararse nunca. El propio codigo lo decia en
nucleo/canales/whatsapp.py: "no tiene con que contar".

Quien configura un tope cree que esta protegido. Esa es la falla, no la
ausencia de una metrica bonita.

Lo que se fija aca
------------------
1. SIN CONTEXTO ABIERTO NO SE CUENTA NADA. Es la propiedad que mantiene las
   cifras limpias: los casos dorados y los bancos de prueba llaman al MISMO
   motor y harian miles de llamadas al modelo. Si contaran, el consumo del
   tenant seria mayormente pruebas y el tope saltaria por trabajo que nadie
   facturo.

2. UN MODELO SIN TARIFA NO SE ESTIMA. Cuenta sus tokens y deja el costo en
   cero, marcado. Un numero inventado se ve igual de real que uno correcto en
   un panel, y despues nadie sabe cual es cual.

3. EL COSTO SE CALCULA POR MILLON DE TOKENS, como lo publican los proveedores.
   El error mas aburrido y mas caro de este dominio es un factor de mil.

4. SE CUENTAN LOS INTENTOS FALLIDOS. Un turno que gasta tres redacciones en
   blanco costo tres llamadas. Contar solo la que sirvio esconderia justo el
   caso caro -- y ese caso existe, medido el 03/09/2026.

5. SIN TOPE CONFIGURADO NUNCA SE BLOQUEA, y un fallo al leer el gasto tampoco
   bloquea. Un tope que no se puede consultar no debe dejar sin servicio a una
   empresa que quiza esta lejos de su limite.

Corre SIN BASE DE DATOS y sin red.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.observabilidad import consumo                          # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


class RespuestaFalsa:
    def __init__(self, entrada, salida):
        self.tokens_entrada, self.tokens_salida = entrada, salida


class ConfigFalsa:
    class identidad:
        slug = "tenant_de_prueba"

    class llm:
        # 1 USD por millon de entrada, 2 por millon de salida. Numeros redondos
        # a proposito: si el calculo mete un factor de mil, se ve a simple vista.
        tarifas = {"prov:modelo-con-tarifa": {"entrada": 1.0, "salida": 2.0}}

    class limites:
        max_costo_usd_mes = None


# Se sustituye la CONEXION, no _volcar(): asi la funcion real corre entera y
# se prueba tambien su corte por cero llamadas. Sustituir _volcar dejaba ese
# corte sin ejercitar y el test afirmaba algo que nunca se ejecutaba -- lo
# encontro esta misma guarda, fallando por su propio doble.
volcados: list = []


class _CursorFalso:
    def execute(self, *a, **k):
        volcados.append(a[1] if len(a) > 1 else None)


class _SesionFalsa:
    def __init__(self, tenant): pass
    def __enter__(self): return _CursorFalso(), "org-falsa"
    def __exit__(self, *a): return False


consumo.sesion = _SesionFalsa


print("\n== 1. sin contexto abierto no se cuenta nada ==")
consumo.anotar("prov:modelo-con-tarifa", RespuestaFalsa(1000, 1000))
afirmar(not volcados, "una llamada fuera de un turno real no genera consumo")


print("\n== 2-4. lo que se cuenta y como ==")
with consumo.abrir(ConfigFalsa()) as ficha:
    consumo.anotar("prov:modelo-con-tarifa", RespuestaFalsa(1_000_000, 500_000))

afirmar(len(volcados) == 1, "al cerrar el turno se escribe una vez, no por llamada")
tokens_in, tokens_out, costo = volcados[-1][1], volcados[-1][2], volcados[-1][3]


class _Escrito:
    def __init__(self, p):
        self.tokens_entrada, self.tokens_salida, self.costo_usd = p[1], p[2], p[3]


f = _Escrito(volcados[-1])
f.sin_tarifa = set()
# 1M entrada x 1 USD/M + 0.5M salida x 2 USD/M = 1.0 + 1.0 = 2.0
afirmar(abs(f.costo_usd - 2.0) < 1e-9,
        f"el costo se calcula por millon de tokens (dio {f.costo_usd})")
afirmar(f.tokens_entrada == 1_000_000 and f.tokens_salida == 500_000,
        "los tokens se acumulan tal cual")
afirmar(not f.sin_tarifa, "un modelo con tarifa no se marca como sin tarifa")

volcados.clear()
with consumo.abrir(ConfigFalsa()) as ficha:
    consumo.anotar("prov:modelo-SIN-tarifa", RespuestaFalsa(1_000_000, 1_000_000))
f = _Escrito(volcados[-1])
f.sin_tarifa = ficha.sin_tarifa
afirmar(f.costo_usd == 0.0, "un modelo sin tarifa NO se estima: el costo queda en 0")
afirmar(f.tokens_entrada == 1_000_000,
        "pero sus tokens si se cuentan -- el consumo existio")
afirmar("prov:modelo-SIN-tarifa" in f.sin_tarifa,
        "queda marcado cual modelo falta tarifar, para distinguir 0 de 'no se sabe'")

volcados.clear()
with consumo.abrir(ConfigFalsa()) as ficha:
    for _ in range(3):      # tres redacciones en blanco, como paso en vivo
        consumo.anotar("prov:modelo-con-tarifa", RespuestaFalsa(1_000_000, 0))
    n_llamadas = ficha.n_llamadas if (ficha := ficha) else 0
f = _Escrito(volcados[-1])
afirmar(n_llamadas == 3 and abs(f.costo_usd - 3.0) < 1e-9,
        "los intentos fallidos se cuentan: tres llamadas costaron tres")

volcados.clear()
with consumo.abrir(ConfigFalsa()):
    pass
afirmar(not volcados, "un turno sin ninguna llamada al modelo no escribe una fila vacia")


print("\n== 5. el tope no bloquea de mas ==")
consumo.gasto_del_mes = lambda tenant: 42.0

paso, gastado, tope = consumo.tope_superado(ConfigFalsa(), "tenant_de_prueba")
afirmar(paso is False, "sin tope configurado nunca se considera superado")


class ConTope(ConfigFalsa):
    class limites:
        max_costo_usd_mes = 50.0


paso, gastado, tope = consumo.tope_superado(ConTope(), "tenant_de_prueba")
afirmar(paso is False and gastado == 42.0 and tope == 50.0,
        "por debajo del tope no se bloquea, y devuelve cuanto y de cuanto")


class TopeBajo(ConfigFalsa):
    class limites:
        max_costo_usd_mes = 10.0


paso, gastado, tope = consumo.tope_superado(TopeBajo(), "tenant_de_prueba")
afirmar(paso is True and gastado == 42.0,
        "por encima del tope se marca, con la cifra para poder decirla")


print("\n== aislamiento entre turnos concurrentes ==")
# El acumulador vive en un ContextVar y no en una variable de modulo: el motor
# atiende varios turnos a la vez en hilos distintos, y una variable compartida
# mezclaria el consumo de dos empresas.
import threading                                                   # noqa: E402

volcados.clear()
resultados = {}


def turno(nombre, tokens):
    class Cfg(ConfigFalsa):
        class identidad:
            slug = nombre
    with consumo.abrir(Cfg()) as f:
        consumo.anotar("prov:modelo-con-tarifa", RespuestaFalsa(tokens, 0))
        resultados[nombre] = f.tokens_entrada


hilos = [threading.Thread(target=turno, args=(f"empresa_{i}", (i + 1) * 1000))
         for i in range(3)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()

afirmar(resultados == {"empresa_0": 1000, "empresa_1": 2000, "empresa_2": 3000},
        f"tres turnos a la vez no mezclan su consumo ({resultados})")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El consumo se cuenta donde debe, no se inventa, y el tope ya puede disparar.")
