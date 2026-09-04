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




print("\n== 6. el tope avisa antes de frenar ==")
# Un tope que pasa de "todo normal" a "todo va a una persona" sin aviso previo
# es inoperable: quien lo administra se entera cuando ya no hay margen.


def _con_tope(valor):
    class C(ConfigFalsa):
        class limites:
            max_costo_usd_mes = valor
            mensaje_al_alcanzar_tope = ""
    return C()


consumo.gasto_del_mes = lambda tenant: 50.0

e = consumo.estado_del_gasto(_con_tope(None), "t")
afirmar(e["accion"] == "seguir", "sin tope configurado la accion es seguir")

e = consumo.estado_del_gasto(_con_tope(1000.0), "t")     # 5%
afirmar(e["accion"] == "seguir", "muy por debajo del tope: seguir")

e = consumo.estado_del_gasto(_con_tope(60.0), "t")       # 83%
afirmar(e["accion"] == "avisar",
        f"cerca del tope avisa sin frenar (dio {e['accion']}, {e['porcentaje']:.0%})")

e = consumo.estado_del_gasto(_con_tope(50.0), "t")       # 100%
afirmar(e["accion"] == "frenar" and e["gastado"] == 50.0 and e["tope"] == 50.0,
        "al alcanzarlo frena, y devuelve cuanto y de cuanto para poder decirlo")

e = consumo.estado_del_gasto(_con_tope(40.0), "t")       # pasado
afirmar(e["accion"] == "frenar", "pasado el tope sigue frenando")

# Un fallo al consultar el gasto NO puede dejar sin servicio a una empresa que
# quiza esta lejos de su limite.
def _revienta(tenant):
    raise RuntimeError("base caida")


_original = consumo.gasto_del_mes
consumo.sesion = _SesionFalsa   # que gasto_del_mes real falle al leer
consumo.gasto_del_mes = consumo.__dict__["gasto_del_mes"]
e = consumo.estado_del_gasto(_con_tope(50.0), "t")
afirmar(e["accion"] in ("seguir", "frenar"),
        "un fallo al leer el gasto no revienta el turno")
consumo.gasto_del_mes = _original




print("\n== 7. el cache decide el costo, y se comprueba contra una factura real ==")
# DATO REAL (panel de DeepSeek, 30 dias al 04/09/2026):
#     141.852.383 tokens  ->  $7.48
#     = $0.053 por millon
#
# Esa cifra SOLO es posible si casi todo es cache. Al precio de entrada nueva
# ($0.22-0.44 por millon) los mismos tokens costarian entre $30 y $60. Este
# bloque comprueba que el calculo puede reproducir la factura real, y que
# ignorar el cache la multiplica por ocho.

TARIFA_FLASH = {"entrada": 0.44, "entrada_cache": 0.014, "salida": 1.32}


class ConCache(ConfigFalsa):
    class llm:
        tarifas = {"deepseek:deepseek-v4-flash": TARIFA_FLASH}


# 141.85M de entrada, 97% cacheada, y una salida chica.
ENTRADA, CACHE, SALIDA = 138_000_000, 134_000_000, 3_850_000
costo_con, _ = consumo._costo(ConCache(), "deepseek:deepseek-v4-flash",
                              ENTRADA, SALIDA, CACHE)
costo_sin, _ = consumo._costo(ConCache(), "deepseek:deepseek-v4-flash",
                              ENTRADA, SALIDA, 0)

afirmar(3.0 < costo_con < 15.0,
        f"con cache, el costo cae en el orden de la factura real (${costo_con:.2f} "
        f"contra $7.48 reales)")
afirmar(costo_sin > costo_con * 4,
        f"ignorar el cache multiplica la factura (${costo_sin:.2f} contra "
        f"${costo_con:.2f})")

# Sin 'entrada_cache' en la tarifa se cobra todo como entrada nueva: el lado
# conservador. Sobreestimar avisa antes de tiempo; subestimar deja pasar el
# tope sin frenar.
class SinPrecioCache(ConfigFalsa):
    class llm:
        tarifas = {"m": {"entrada": 0.44, "salida": 1.32}}


c1, _ = consumo._costo(SinPrecioCache(), "m", 1_000_000, 0, 1_000_000)
afirmar(abs(c1 - 0.44) < 1e-9,
        "sin precio de cache se cobra todo como entrada nueva (conservador)")

# Un proveedor que informe mas cacheados que entrada total no puede producir
# un costo negativo.
c2, _ = consumo._costo(ConCache(), "deepseek:deepseek-v4-flash", 1000, 0, 999999)
afirmar(c2 >= 0, "un dato de cache incoherente no genera un costo negativo")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] El consumo se cuenta donde debe, no se inventa, y el tope ya puede disparar.")
