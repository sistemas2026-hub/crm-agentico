# -*- coding: utf-8 -*-
"""
================================================================================
 CONSUMO  --  cuanto gasta cada empresa, y el tope que hasta ahora no podia
================================================================================

Lo que estaba roto
------------------
'asistente.usage_daily' existe desde el primer esquema, con columnas para
tokens y costo. NADIE escribia en ella. Y 'limites.max_costo_usd_mes' existe
en la configuracion desde entonces -- un tope de gasto que un ADMIN podia
poner, que se validaba, que se guardaba, y que NUNCA podia dispararse.

El propio codigo lo decia, en nucleo/canales/whatsapp.py:

    "limites.max_costo_usd_mes no tiene con que contar."

Un tope de seguridad que no cuenta nada es peor que no tenerlo: quien lo
configura cree que esta protegido. Este modulo es lo que le da con que contar.

Como cuenta, y por que asi
--------------------------
Un turno hace VARIAS llamadas al modelo -- el bucle de herramientas puede dar
varias vueltas, y la redaccion final es otra. Escribir a la base despues de
cada una serian tres o cuatro escrituras por turno, en el camino caliente,
para un dato que solo se lee agregado.

Se acumula en memoria durante el turno y se vuelca UNA vez al cerrar. El
acumulador vive en un ContextVar y no en una variable de modulo: el motor
atiende varios turnos a la vez en hilos distintos, y una variable compartida
mezclaria el consumo de dos empresas.

SIN CONTEXTO ABIERTO, ANOTAR NO HACE NADA. Es deliberado y es lo que mantiene
limpias las cifras: los corredores de casos dorados y los bancos de prueba
llaman al mismo motor y harian miles de llamadas al modelo. Si contaran, el
consumo del tenant seria mayormente pruebas, y el tope saltaria por trabajo
que nadie facturo. Solo el canal real abre el contexto.

Sobre las tarifas
-----------------
Vienen de la config del tenant (LLM.tarifas), no de este codigo. Un modelo sin
tarifa cargada cuenta sus tokens y deja el costo en CERO, marcado como sin
tarifa -- nunca se estima. Un numero inventado se veria igual de real en el
panel que uno correcto, y nadie sabria cual es cual.

Nunca rompe el turno
--------------------
Si la base falla al volcar, se anota y se sigue. Perder una fila de consumo es
molesto; perder la respuesta de un cliente por una estadistica, no se hace.
================================================================================
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from nucleo.persistencia.db import sesion

# El acumulador del turno en curso. None = no hay turno real abierto y anotar()
# no hace nada (ver el encabezado: es lo que deja las pruebas fuera de la
# facturacion).
_actual: ContextVar["Consumo | None"] = ContextVar("consumo_actual", default=None)

# Las tarifas se declaran por MILLON de tokens porque asi las publican los
# proveedores. Guardar el numero como viene evita la clase de error mas
# aburrida y mas cara: un factor de mil metido al cargarlo.
POR_MILLON = 1_000_000


@dataclass
class Consumo:
    tenant: str
    # La config viaja en la ficha para que anotar() sea de dos argumentos y se
    # pueda llamar desde cualquier punto del motor -- la redaccion final, por
    # ejemplo, no recibe config y no tiene por que empezar a recibirla solo
    # para esto.
    config: object = None
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    n_llamadas: int = 0
    # Referencias de modelo que se usaron sin tarifa cargada. Es el dato que
    # convierte "el costo dio 0" en "el costo dio 0 PORQUE falta cargar la
    # tarifa de este modelo", que son dos cosas muy distintas.
    sin_tarifa: set[str] = field(default_factory=set)


def _costo(config, referencia: str, entrada: int, salida: int) -> tuple[float, bool]:
    """(costo en USD, si habia tarifa). Sin tarifa: 0.0 y False, nunca un estimado."""
    tarifas = getattr(getattr(config, "llm", None), "tarifas", None) or {}
    t = tarifas.get(referencia)
    if not t:
        return 0.0, False
    return (entrada * float(t.get("entrada", 0.0))
            + salida * float(t.get("salida", 0.0))) / POR_MILLON, True


@contextmanager
def abrir(config):
    """Abre el acumulador de un turno real. Al salir, lo vuelca a la base.

    Lo abre SOLO el canal que atiende de verdad. Un corredor de pruebas que
    llame al mismo motor no lo abre, asi que su consumo no entra en la
    facturacion de nadie -- ver el encabezado.
    """
    ficha = Consumo(tenant=config.identidad.slug, config=config)
    testigo = _actual.set(ficha)
    try:
        yield ficha
    finally:
        _actual.reset(testigo)
        _volcar(ficha)


def anotar(referencia_modelo: str, respuesta) -> None:
    """Suma una llamada al modelo al turno en curso. Sin turno, no hace nada."""
    ficha = _actual.get()
    if ficha is None:
        return
    entrada = int(getattr(respuesta, "tokens_entrada", 0) or 0)
    salida = int(getattr(respuesta, "tokens_salida", 0) or 0)
    costo, hay_tarifa = _costo(ficha.config, referencia_modelo, entrada, salida)

    ficha.tokens_entrada += entrada
    ficha.tokens_salida += salida
    ficha.costo_usd += costo
    ficha.n_llamadas += 1
    if not hay_tarifa and (entrada or salida):
        ficha.sin_tarifa.add(referencia_modelo)


def _volcar(ficha: Consumo) -> None:
    """Una fila por dia y por empresa, sumando. Nunca rompe el turno."""
    if not ficha.n_llamadas:
        return
    if ficha.sin_tarifa:
        print(f"[consumo] {ficha.tenant}: sin tarifa cargada para "
              f"{sorted(ficha.sin_tarifa)} -- se cuentan tokens, el costo "
              f"queda en 0. Cargala en la configuracion del agente.")
    try:
        with sesion(ficha.tenant) as (cur, org):
            cur.execute(
                """insert into asistente.usage_daily
                       (organization_id, dia, n_mensajes, tokens_entrada,
                        tokens_salida, costo_usd)
                   values (%s, current_date, 1, %s, %s, %s)
                   on conflict (organization_id, dia) do update set
                       n_mensajes     = asistente.usage_daily.n_mensajes + 1,
                       tokens_entrada = asistente.usage_daily.tokens_entrada + excluded.tokens_entrada,
                       tokens_salida  = asistente.usage_daily.tokens_salida + excluded.tokens_salida,
                       costo_usd      = asistente.usage_daily.costo_usd + excluded.costo_usd""",
                (org, ficha.tokens_entrada, ficha.tokens_salida,
                 round(ficha.costo_usd, 6)))
    except Exception as fallo:      # noqa: BLE001 -- ver encabezado
        print(f"[consumo] no se pudo registrar el consumo de {ficha.tenant}: {fallo!r}")


def gasto_del_mes(tenant: str) -> float:
    """Lo gastado en el mes corriente. 0.0 si no se puede leer.

    Ante un fallo devuelve 0.0 y NO bloquea: un tope de gasto que no se puede
    consultar no debe dejar sin servicio a una empresa que quiza esta muy lejos
    de su limite. El riesgo de cobrar de mas un rato es menor que el de dejar
    de atender por una consulta fallida.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute("select asistente.gasto_del_mes(%s) as gasto", (org,))
            fila = cur.fetchone()
        return float((fila or {}).get("gasto") or 0.0)
    except Exception as fallo:      # noqa: BLE001
        print(f"[consumo] no se pudo leer el gasto de {tenant}: {fallo!r}")
        return 0.0


def tope_superado(config, tenant: str) -> tuple[bool, float, float]:
    """(se paso, gastado, tope). Sin tope configurado nunca se pasa.

    Devuelve las tres cosas y no solo el booleano: quien avisa necesita poder
    decir CUANTO, y un aviso de "alcanzaste el limite" sin la cifra obliga a ir
    a buscarla a otro lado justo cuando hay urgencia.
    """
    tope = getattr(getattr(config, "limites", None), "max_costo_usd_mes", None)
    if not tope:
        return False, 0.0, 0.0
    gastado = gasto_del_mes(tenant)
    return gastado >= float(tope), gastado, float(tope)
