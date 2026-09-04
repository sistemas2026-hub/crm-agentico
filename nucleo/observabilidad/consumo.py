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
from datetime import datetime, timezone
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
    tokens_entrada_cache: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0
    n_llamadas: int = 0
    # Referencias de modelo que se usaron sin tarifa cargada. Es el dato que
    # convierte "el costo dio 0" en "el costo dio 0 PORQUE falta cargar la
    # tarifa de este modelo", que son dos cosas muy distintas.
    sin_tarifa: set[str] = field(default_factory=set)


def _costo(config, referencia: str, entrada: int, salida: int,
           entrada_cache: int = 0, momento=None) -> tuple[float, bool]:
    """(costo en USD, si habia tarifa). Sin tarifa: 0.0 y False, nunca un estimado.

    'entrada' es el TOTAL de entrada y 'entrada_cache' la parte que venia
    cacheada -- asi los reporta DeepSeek, verificado en vivo. Se cobra la
    diferencia como entrada nueva.

    'momento' es CUANDO se hizo la llamada, en UTC, y decide si aplica la
    tarifa de pico o la de fuera de pico. Se calcula por llamada y no por dia:
    una conversacion de la madrugada y una del mediodia pueden caer en tramos
    distintos, y promediarlas seria inventar una tarifa que nadie cobra.

    Por defecto es ahora, que es cierto en el camino real -- se anota en el
    mismo instante. El parametro existe para poder probarlo con una hora fija.
    """
    tarifas = getattr(getattr(config, "llm", None), "tarifas", None) or {}
    t = tarifas.get(referencia)
    if not t:
        return 0.0, False
    p_nueva, p_cache, p_salida = t.por_millon(momento or datetime.now(timezone.utc))
    cacheados = max(0, min(int(entrada_cache or 0), entrada))
    nuevos = entrada - cacheados
    return (nuevos * p_nueva + cacheados * p_cache
            + salida * p_salida) / POR_MILLON, True


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
    cacheados = int(getattr(respuesta, "tokens_entrada_cache", 0) or 0)
    costo, hay_tarifa = _costo(ficha.config, referencia_modelo, entrada, salida,
                               cacheados)

    ficha.tokens_entrada += entrada
    ficha.tokens_entrada_cache += cacheados
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

    # Una vez al dia, y en un hilo: la foto del saldo es una llamada HTTP a un
    # tercero, y un cliente no tiene por que esperar por una consulta que no
    # tiene nada que ver con su pregunta.
    if ficha.config is not None:
        _quizas_fotografiar_saldo(ficha.config, ficha.tenant)


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


# A partir de que porcentaje del tope se avisa, sin bloquear todavia. Un tope
# que pasa de "todo normal" a "todo va a una persona" sin aviso previo es
# inoperable: quien lo administra se entera cuando ya no hay margen.
AVISO_DESDE = 0.8


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


def estado_del_gasto(config, tenant: str) -> dict:
    """
    En que punto del tope esta esta empresa, y que corresponde hacer.

    Devuelve 'accion': 'seguir' | 'avisar' | 'frenar'.

    'frenar' NO significa dejar al cliente sin respuesta. Significa que este
    turno no se le pide nada al modelo y la conversacion pasa a una persona --
    el tope existe para que no se dispare la factura, no para que alguien con
    el internet caido se quede hablando solo. Quien decide que hacer con eso es
    el canal (ver nucleo/canales/api.py); aca solo se informa.

    'avisar' se cruza una vez y despues sigue cruzandose en cada turno, asi que
    quien lo consuma tiene que decidir cada cuanto lo dice. No se guarda estado
    aca: este modulo cuenta y responde, no recuerda.
    """
    tope = getattr(getattr(config, "limites", None), "max_costo_usd_mes", None)
    if not tope:
        return {"accion": "seguir", "gastado": 0.0, "tope": 0.0, "porcentaje": 0.0}

    tope = float(tope)
    gastado = gasto_del_mes(tenant)
    porcentaje = (gastado / tope) if tope else 0.0
    if gastado >= tope:
        accion = "frenar"
    elif porcentaje >= AVISO_DESDE:
        accion = "avisar"
    else:
        accion = "seguir"
    return {"accion": accion, "gastado": round(gastado, 4),
            "tope": tope, "porcentaje": round(porcentaje, 3)}


# =============================================================================
#  CONCILIACION  --  lo que calculamos contra lo que el proveedor cobro
# =============================================================================
#  El conteo por tokens es un CALCULO nuestro: depende de que la tarifa cargada
#  sea la vigente, de que el desglose de cache sea correcto y de que las
#  ventanas de horario pico esten bien. Las tres pueden quedar viejas sin
#  aviso.
#
#  Paso el 17/08/2026: DeepSeek subio precios y nadie se entero. El nivel de
#  $0.28 por millon dejo de aplicarse y solo se vio semanas despues, mirando la
#  facturacion real.
#
#  El saldo del proveedor es la unica cifra que no discute nadie. Lo que baja
#  de un dia al otro ES lo que se gasto.
#
#  NO REEMPLAZA EL CONTEO: el saldo no dice por dia ni por tipo de token, y
#  llega tarde para frenar nada. Audita, no sustituye.

# Un proceso pregunta el saldo UNA vez por dia. Sin esto, cada turno miraria la
# base para ver si ya se guardo -- una consulta por turno para un dato que
# cambia una vez al dia.
_saldo_visto: dict[str, str] = {}


def _valor_en(datos, ruta: str):
    """El valor en 'a.b.0.c', tolerando listas. None si el camino no existe."""
    actual = datos
    for parte in (ruta or "").split("."):
        if isinstance(actual, list):
            try:
                actual = actual[int(parte)]
            except (ValueError, IndexError):
                return None
        elif isinstance(actual, dict):
            actual = actual.get(parte)
        else:
            return None
        if actual is None:
            return None
    return actual


def consultar_saldo(config) -> float | None:
    """El saldo que reporta el proveedor, o None si no se puede saber.

    Devuelve None ante cualquier problema -- sin endpoint declarado, sin
    credencial, timeout, respuesta con otra forma. Es informacion de auditoria:
    no saberla no puede afectar a nadie que este esperando una respuesta.
    """
    cfg = getattr(getattr(config, "llm", None), "saldo", None)
    if not cfg or not cfg.url or not cfg.campo:
        return None

    from nucleo.seguridad import secretos
    clave = secretos.obtener(config.identidad.slug, cfg.auth_ref) if cfg.auth_ref else None
    if cfg.auth_ref and not clave:
        print(f"[consumo] falta el secreto '{cfg.auth_ref}' para consultar el saldo.")
        return None

    try:
        import requests
        cabeceras = {}
        if clave:
            cabeceras[cfg.auth_header] = f"{cfg.auth_esquema} {clave}".strip()
        r = requests.get(cfg.url, headers=cabeceras, timeout=15)
        r.raise_for_status()
        crudo = _valor_en(r.json(), cfg.campo)
        return float(crudo) if crudo is not None else None
    except Exception as fallo:      # noqa: BLE001 -- ver docstring
        print(f"[consumo] no se pudo consultar el saldo del proveedor: {fallo!r}")
        return None


def _guardar_saldo_del_dia(config, tenant: str) -> None:
    """Deja la foto del saldo de hoy, si todavia no esta. Una vez por dia."""
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """select saldo_proveedor_usd from asistente.usage_daily
                    where organization_id = %s and dia = current_date""", (org,))
            fila = cur.fetchone()
            if fila and fila["saldo_proveedor_usd"] is not None:
                return                      # ya esta
        saldo = consultar_saldo(config)
        if saldo is None:
            return
        with sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.usage_daily set saldo_proveedor_usd = %s
                    where organization_id = %s and dia = current_date""",
                (saldo, org))
    except Exception as fallo:      # noqa: BLE001
        print(f"[consumo] no se pudo guardar el saldo del dia: {fallo!r}")


def _quizas_fotografiar_saldo(config, tenant: str) -> None:
    """Dispara la foto en un hilo: nunca le agrega latencia al turno.

    El saldo es una llamada HTTP a un tercero. Hacerla dentro del turno
    significaria que un cliente espera por una consulta que no tiene nada que
    ver con su pregunta -- y que un proveedor lento le arruine la respuesta.
    """
    # Se descarta ANTES de tocar la base. Un proveedor sin endpoint de saldo no
    # participa de la conciliacion, y consultarle a la base todos los dias si
    # ya guardo un dato que nunca va a existir es trabajo puro.
    cfg = getattr(getattr(config, "llm", None), "saldo", None)
    if not cfg or not getattr(cfg, "url", "") or not getattr(cfg, "campo", ""):
        return
    hoy = str(__import__("datetime").date.today())
    if _saldo_visto.get(tenant) == hoy:
        return
    _saldo_visto[tenant] = hoy
    import threading
    threading.Thread(target=_guardar_saldo_del_dia, args=(config, tenant),
                     daemon=True).start()


def conciliar(tenant: str, dias: int = 14) -> list[dict]:
    """Por dia: lo que calculamos, lo que bajo el saldo, y si se separan.

    El gasto real de un dia es el saldo del dia ANTERIOR menos el de hoy. Hacen
    falta dos fotos consecutivas: el primer dia con saldo nunca tiene con que
    compararse, y se devuelve sin veredicto en vez de inventarle uno.

    Una recarga de saldo SUBE la cifra, asi que la resta da negativa. Ese dia
    no se puede conciliar -- se marca y se sigue, en vez de reportar un gasto
    negativo que no significa nada.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select dia, costo_usd, saldo_proveedor_usd
                 from asistente.usage_daily
                where organization_id = %s
                  and dia > current_date - make_interval(days => %s)
                order by dia""", (org, dias))
        filas = [dict(f) for f in cur.fetchall()]

    salida, saldo_previo = [], None
    for f in filas:
        saldo = f["saldo_proveedor_usd"]
        calculado = float(f["costo_usd"] or 0)
        real = None
        if saldo is not None and saldo_previo is not None:
            real = float(saldo_previo) - float(saldo)
        salida.append({
            "dia": f["dia"].isoformat(),
            "calculado": round(calculado, 4),
            "real": None if real is None else round(real, 4),
            # Negativo = hubo una recarga ese dia. No es un gasto negativo, es
            # que la resta no aplica.
            "hubo_recarga": real is not None and real < 0,
            "saldo": None if saldo is None else float(saldo),
        })
        if saldo is not None:
            saldo_previo = saldo
    return salida


def veredicto_conciliacion(config, tenant: str, dias: int = 14) -> dict:
    """Si el calculo se esta separando de la realidad, y por cuanto.

    Se compara el ACUMULADO y no dia por dia: el saldo se lee una vez al dia y
    los turnos siguen ocurriendo, asi que un dia suelto siempre difiere. Lo que
    importa es si la diferencia se sostiene.
    """
    filas = [f for f in conciliar(tenant, dias)
             if f["real"] is not None and not f["hubo_recarga"]]
    if not filas:
        return {"comparables": 0, "estado": "sin_datos"}

    calc = sum(f["calculado"] for f in filas)
    real = sum(f["real"] for f in filas)
    tolerancia = getattr(getattr(getattr(config, "llm", None), "saldo", None),
                         "tolerancia", 0.15)
    desvio = abs(calc - real) / real if real else 0.0
    return {
        "comparables": len(filas),
        "calculado": round(calc, 4),
        "real": round(real, 4),
        "desvio": round(desvio, 3),
        "estado": "ok" if desvio <= tolerancia else "desviado",
    }
