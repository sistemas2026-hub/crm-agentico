# -*- coding: utf-8 -*-
"""
================================================================================
 ALERTAS OPERATIVAS  --  mirar lo que ya se estaba midiendo
================================================================================

POR QUE EXISTE (05/10/2026)
---------------------------
Las dos senales ya estaban. Lo que faltaba era que alguien las mirara.

  'usage_daily.saldo_proveedor_usd' viene guardando la foto diaria del saldo
  desde hace semanas. El 05/10/2026 valia 0.72 USD -- unos tres dias al ritmo
  medido. Lo descubrio una auditoria a mano.

  'consumo.veredicto_conciliacion' viene calculando que el proveedor cobro
  2.86 veces lo que el sistema contaba. Tambien lo descubrio una persona que
  fue a mirar.

Un dato que solo aparece cuando alguien lo busca no es monitoreo. Este modulo
lo mira una vez por hora desde 'motor-reloj' y deja el hallazgo escrito en
'asistente.alertas_operativas'.

NO LLAMA AL MODELO Y NO LLAMA AL PROVEEDOR
-------------------------------------------
El saldo se lee de la foto que ya esta en la base. No se agrega ni una
peticion HTTP al proveedor ni un token de LLM: un barrido por hora que
consultara el saldo serian 24 llamadas diarias para un dato que se refresca
una vez al dia, y consumir credito para avisar que se esta acabando el
credito seria una forma elegante de empeorarlo.

Consecuencia que hay que tener presente: la foto la toma el motor al cerrar
un turno (consumo._quizas_fotografiar_saldo), asi que en un dia sin trafico
no hay foto nueva y se trabaja con la ultima. Eso puede producir un aviso
tardio --el saldo real bajo y la foto no lo refleja-- y, despues de una
recarga, un aviso de mas que dura hasta la foto siguiente. Las dos ventanas
son de horas y quedan anotadas en 'metadatos.edad_dias' de cada alerta, para
que quien la lea sepa de cuando es la cifra.

NO BLOQUEA NADA
---------------
No detiene a Dexter, no mueve el tope, no toca tarifas, no recarga. Escribe
una fila y un log. Una discrepancia contable no puede dejar sin atender a los
clientes de un ISP.

NO SE INVENTA UNA ALERTA, Y TAMPOCO SE INVENTA UN 'TODO BIEN'
--------------------------------------------------------------
Hay tres estados, no dos: se cumple, no se cumple, y NO SE SABE. El tercero
--sin foto de saldo, conciliacion que fallo, menos dias comparables de los
que hacen falta-- no crea una alerta y tampoco resuelve la que este abierta.
Resolver por falta de datos seria peor que no avisar: convertiria un silencio
en un alta medica.

LOS UMBRALES SON CONSTANTES DE MODULO, Y ESO ES UNA DEUDA DECLARADA
--------------------------------------------------------------------
Por 3.3 de CLAUDE.md, un numero que varia por empresa es configuracion. Estos
van a variar: 5 USD es poco para un ISP que gasta 200 por mes y es mucho para
uno que gasta 3. Hoy quedan aca porque el alcance aprobado de esta fase son
cuatro archivos y 'schema.py' no es uno -- y porque mover un default de
'TenantConfig' arrastra el problema conocido de 'editor._editar' (D7).

Para que esa mudanza sea una linea y no una refactorizacion, las funciones de
umbral los reciben como PARAMETROS y solo usan la constante como valor por
omision. El dia que vivan en la config, se pasan desde 'evaluar()'.
================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from nucleo.observabilidad import consumo
from nucleo.observabilidad.registro import registrar
from nucleo.persistencia.db import sesion

# -----------------------------------------------------------------------------
#  VOCABULARIO. Las mismas palabras que los 'check' de la tabla.
# -----------------------------------------------------------------------------
SALDO_BAJO = "saldo_bajo"
DIVERGENCIA = "divergencia_consumo"
TIPOS = (SALDO_BAJO, DIVERGENCIA)

WARNING = "warning"
CRITICAL = "critical"

SALDO_USD = "saldo_usd"
RATIO = "ratio"
DIFERENCIA_USD = "diferencia_usd"

#  Los tres estados de una lectura. 'sin_dato' no es un detalle: es el que
#  impide inventar tanto la alarma como el alta.
ALERTA = "alerta"
LIMPIO = "limpio"
SIN_DATO = "sin_dato"

# -----------------------------------------------------------------------------
#  UMBRALES  (ver la nota de deuda en el encabezado)
# -----------------------------------------------------------------------------
#  5 USD son ~3 semanas al ritmo medido el 05/10/2026 (6.78 USD en 23 dias);
#  2 USD son ~9 dias. El critico se eligio para que avise con mas de una
#  semana de margen: una recarga puede necesitar que alguien del lado del
#  cliente la autorice, y eso no se resuelve en una tarde.
SALDO_WARNING = 5.00
SALDO_CRITICAL = 2.00

#  La razon entre lo que cobro el proveedor y lo que calculamos. 1.5x es el
#  mismo numero que ya usa 'consumo.RATIO_DIVERGENCIA' y se importa de ahi
#  para que no haya dos verdades: el panel y la alerta tienen que coincidir.
RATIO_WARNING = consumo.RATIO_DIVERGENCIA
RATIO_CRITICAL = 3.0
#  En dolares, porque una razon alta sobre cifras chicas no significa nada:
#  0.02 calculado contra 0.10 real es 5x y son ocho centavos.
DIFERENCIA_CRITICAL = 5.00

#  POR QUE LA VENTANA ES DE 14 DIAS Y NO DE 3
#  -------------------------------------------
#  "Sostenido 3 dias" se implementa como "al menos 3 dias comparables dentro
#  de la ventana", y NO como 'veredicto_conciliacion(dias=3)'. Con dias=3 el
#  minimo es inalcanzable por aritmetica: 'conciliar' devuelve como mucho 3
#  filas, la primera nunca tiene con que compararse --el gasto de un dia es el
#  saldo del dia anterior menos el de hoy-- y los dias con recarga se
#  descartan. Son 2 comparables como techo, asi que un umbral de 3 nunca
#  dispararia y la alerta estaria muerta sin dar ningun sintoma.
#
#  La cota general es 'comparables <= dias - 1', y menos todavia si hay dias
#  sin foto o con recarga. El minimo viable para exigir 3 es 'dias = 4'.
#
#  14 dias es ademas la misma ventana que muestra 'GET /consumo', asi que la
#  alerta y el panel hablan del mismo numero.
#
#  QUE SIGNIFICA 'MINIMO_COMPARABLES', Y QUE NO
#  ---------------------------------------------
#  Es una condicion de SUFICIENCIA DE DATOS dentro de la ventana de 14 dias.
#  NO significa "tres dias consecutivos por encima de 1.5x", y conviene no
#  leerlo asi.
#
#  La persistencia la aporta otra cosa: 'veredicto_conciliacion' compara el
#  ACUMULADO de la ventana y no dia por dia, a proposito y con medicion detras
#  --el saldo se lee una vez al dia y los turnos siguen ocurriendo, asi que un
#  dia suelto siempre difiere--. Lo que esta regla afirma es "la ventana en
#  conjunto diverge, y hay al menos 3 dias usables para decirlo".
#
#  EL LIMITE, DECLARADO: sobre un acumulado de 14 dias, UN SOLO dia anomalo
#  con una divergencia grande puede cruzar el 1.5x por si mismo, aunque los
#  otros 13 esten limpios. Es mas debil que la lectura literal. Se acepta
#  porque la alternativa --razones diarias-- es justo la que la medicion
#  descarto, y porque la persistencia de verdad ya esta disponible gratis:
#  'alertas_operativas.creado_en' dice hace cuanto esta abierta la alerta. El
#  dia que haga falta escalar por duracion, ese es el dato, sin calcular nada.
DIAS_VENTANA = 14
MINIMO_COMPARABLES = 3


@dataclass(frozen=True)
class Condicion:
    """Una alerta que corresponde emitir, con la cifra que la justifica."""
    tipo: str
    gravedad: str
    metrica: str
    valor: float
    umbral: float
    metadatos: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Lectura:
    """Que se midio y que se concluyo. 'condicion' solo viene con ALERTA."""
    estado: str
    condicion: Condicion | None = None
    motivo: str = ""


# =============================================================================
#  LAS REGLAS  --  funciones puras, sin base y sin red
# =============================================================================
#  Separadas a proposito: son las que deciden, y una decision que necesita
#  PostgreSQL para probarse se prueba poco. Reciben lo ya medido y devuelven
#  que corresponde hacer.

def evaluar_saldo(saldo: float | None, *, dia_foto: date | None = None,
                  hoy: date | None = None,
                  warning: float = SALDO_WARNING,
                  critical: float = SALDO_CRITICAL) -> Lectura:
    """
    El saldo del proveedor contra los dos umbrales.

    Las comparaciones son ESTRICTAS ('<'), asi que un saldo exactamente igual
    al umbral no dispara. Es la lectura literal de "saldo bajo 5 USD" y evita
    que un aviso aparezca y desaparezca con una cifra que queda clavada justo
    en el borde.
    """
    if saldo is None:
        return Lectura(SIN_DATO, motivo="no hay foto del saldo del proveedor")

    saldo = float(saldo)
    edad = (hoy - dia_foto).days if (hoy and dia_foto) else None
    meta = {"edad_dias": edad,
            "dia_foto": dia_foto.isoformat() if dia_foto else None}

    if saldo < critical:
        return Lectura(ALERTA, Condicion(SALDO_BAJO, CRITICAL, SALDO_USD,
                                         round(saldo, 4), critical, meta))
    if saldo < warning:
        return Lectura(ALERTA, Condicion(SALDO_BAJO, WARNING, SALDO_USD,
                                         round(saldo, 4), warning, meta))
    return Lectura(LIMPIO, motivo="saldo por encima del umbral")


def evaluar_divergencia(veredicto: dict | None, *,
                        ratio_warning: float = RATIO_WARNING,
                        ratio_critical: float = RATIO_CRITICAL,
                        diferencia_critical: float = DIFERENCIA_CRITICAL,
                        minimo_comparables: int = MINIMO_COMPARABLES
                        ) -> Lectura:
    """
    Lo que cobro el proveedor contra lo que el sistema conto.

    DOS REGLAS INDEPENDIENTES, Y CADA UNA MIRA UNA DIRECCION DISTINTA
    -----------------------------------------------------------------
    La razon se mira SOLO hacia arriba (el proveedor cobro mas de lo que
    contamos): es la unica direccion donde hay plata que no se esta midiendo,
    que es lo que esta alerta existe para cazar.

    La diferencia en dolares se mira en VALOR ABSOLUTO. Contar de mas tambien
    es un problema contable --el panel le estaria cobrando al cliente un gasto
    que no ocurrio-- y a partir de cierto monto hay que saberlo. El signo
    queda en 'metadatos.direccion' para que se entienda de que lado cae.

    CON MENOS DE 'minimo_comparables' DIAS NO SE CONCLUYE NADA
    ----------------------------------------------------------
    Ni alerta ni alta. El saldo se fotografia una vez al dia y los turnos
    siguen ocurriendo: un dia suelto siempre difiere, y una alerta emitida con
    dos puntos se dispararia sola todo el tiempo. 'comparables' ya descuenta
    los dias con recarga, que son los que no se pueden comparar.
    """
    if not veredicto:
        return Lectura(SIN_DATO, motivo="no se pudo conciliar")

    comparables = int(veredicto.get("comparables") or 0)
    if comparables < minimo_comparables:
        return Lectura(SIN_DATO,
                       motivo=f"solo {comparables} dia(s) comparables, hacen "
                              f"falta {minimo_comparables}")

    ratio = veredicto.get("ratio")
    diferencia = float(veredicto.get("diferencia") or 0.0)
    meta = {"calculado": veredicto.get("calculado"),
            "real": veredicto.get("real"),
            "diferencia": round(diferencia, 4),
            "comparables": comparables,
            "dias_ventana": DIAS_VENTANA,
            "direccion": "cobro_de_mas" if diferencia > 0 else "contamos_de_mas"}

    #  El critico primero: una situacion que cumple las dos se reporta por la
    #  peor, no por la que se evaluo antes.
    if ratio is not None and float(ratio) > ratio_critical:
        return Lectura(ALERTA, Condicion(
            DIVERGENCIA, CRITICAL, RATIO, round(float(ratio), 4),
            ratio_critical, {**meta, "regla": "ratio"}))
    if abs(diferencia) > diferencia_critical:
        return Lectura(ALERTA, Condicion(
            DIVERGENCIA, CRITICAL, DIFERENCIA_USD, round(diferencia, 4),
            diferencia_critical, {**meta, "regla": "diferencia"}))
    if ratio is not None and float(ratio) > ratio_warning:
        return Lectura(ALERTA, Condicion(
            DIVERGENCIA, WARNING, RATIO, round(float(ratio), 4),
            ratio_warning, {**meta, "regla": "ratio"}))
    return Lectura(LIMPIO, motivo="el calculo sigue el saldo")


# =============================================================================
#  LA BASE
# =============================================================================

def ultimo_saldo(tenant: str) -> tuple[float | None, date | None]:
    """
    La foto de saldo mas reciente que exista, con su fecha.

    Se busca la ultima NO NULA y no la de hoy: el saldo solo se fotografia en
    dias con trafico, asi que exigir la de hoy dejaria la alerta ciega
    justamente los dias tranquilos. La fecha viaja para que quien lea la
    alerta sepa de cuando es la cifra.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select dia, saldo_proveedor_usd
                 from asistente.usage_daily
                where organization_id = %s and saldo_proveedor_usd is not null
                order by dia desc limit 1""", (org,))
        fila = cur.fetchone()
    if not fila or fila["saldo_proveedor_usd"] is None:
        return None, None
    return float(fila["saldo_proveedor_usd"]), fila["dia"]


def activas(tenant: str) -> dict[tuple[str, str], dict]:
    """Las alertas vigentes de esta empresa, por (tipo, proveedor)."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select id, tipo, gravedad, proveedor, metrica, valor, umbral,
                      creado_en
                 from asistente.alertas_operativas
                where organization_id = %s and resuelta_en is null""", (org,))
        filas = [dict(f) for f in cur.fetchall()]
    return {(f["tipo"], f["proveedor"]): f for f in filas}


def _crear(tenant: str, proveedor: str, c: Condicion) -> bool:
    """
    Abre una alerta. Devuelve si quedo escrita.

    'on conflict do nothing' contra el indice unico parcial, NO un 'select'
    previo: ahi vive la carrera. Un False no es un fallo -- quiere decir que
    ya habia una activa del mismo asunto, que es exactamente lo que se pedia.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """insert into asistente.alertas_operativas
                 (organization_id, tipo, gravedad, proveedor, metrica,
                  valor, umbral, metadatos)
               values (%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (organization_id, tipo, proveedor)
                 where resuelta_en is null
               do nothing
               returning id""",
            (org, c.tipo, c.gravedad, proveedor, c.metrica,
             round(c.valor, 4), round(c.umbral, 4),
             json.dumps(c.metadatos, ensure_ascii=False, default=str)))
        return cur.fetchone() is not None


def _actualizar(tenant: str, alerta_id, c: Condicion) -> None:
    """
    La alerta abierta pasa a reflejar la cifra de ahora.

    POR QUE NO SE ABRE UNA SEGUNDA
    -------------------------------
    Un saldo que cruza de 4.80 a 1.90 es la MISMA situacion empeorando, no dos
    situaciones. Abrir otra fila duplicaria el aviso --que es justo lo que la
    antirrepeticion existe para evitar-- y el indice unico parcial ademas lo
    impide. Se sube la gravedad en el lugar y se registra el cambio: 'creado_en'
    sigue diciendo cuando empezo el problema, que es el dato que importa para
    saber hace cuanto que esta.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.alertas_operativas
                  set gravedad = %s, metrica = %s, valor = %s, umbral = %s,
                      metadatos = %s
                where id = %s and organization_id = %s
                  and resuelta_en is null""",
            (c.gravedad, c.metrica, round(c.valor, 4), round(c.umbral, 4),
             json.dumps(c.metadatos, ensure_ascii=False, default=str),
             alerta_id, org))


def _resolver(tenant: str, alerta_id) -> None:
    """Sella la alerta. No la borra: el historico es el dato."""
    with sesion(tenant) as (cur, org):
        cur.execute(
            """update asistente.alertas_operativas
                  set resuelta_en = now()
                where id = %s and organization_id = %s
                  and resuelta_en is null""", (alerta_id, org))


# =============================================================================
#  EL BARRIDO
# =============================================================================

def proveedor_de(config) -> str:
    """
    De que proveedor es el saldo que se esta vigilando.

    Sale de 'llm.modelo_por_defecto', que es el que consume el endpoint
    declarado en 'llm.saldo'. No hay un nombre escrito en el codigo y no hay
    un 'if' por empresa: 'nucleo/' no conoce proveedores concretos (3.1).

    'llm.saldo' no tiene campo propio de nombre y no se le agrega en esta
    fase. El dia que haya mas de un proveedor con endpoint de saldo, ese campo
    es lo primero que hay que crear -- y entonces esta funcion recibe cual.
    """
    referencia = getattr(getattr(config, "llm", None), "modelo_por_defecto", "")
    proveedor, _ = consumo.partir_referencia(referencia or "")
    return proveedor or "desconocido"


def hay_endpoint_de_saldo(config) -> bool:
    """Si esta empresa declaro donde preguntar el saldo. Sin eso no hay que
    vigilar: un proveedor sin endpoint no participa de la conciliacion."""
    cfg = getattr(getattr(config, "llm", None), "saldo", None)
    return bool(cfg and getattr(cfg, "url", "") and getattr(cfg, "campo", ""))


def _aplicar(tenant: str, proveedor: str, lectura: Lectura, tipo: str,
             abiertas: dict, seco: bool) -> dict:
    """
    Lo que corresponde hacer con UNA lectura, y lo que se hizo.

    Cuatro caminos y ninguno depende del anterior:

      alerta  + sin abierta   -> crear
      alerta  + abierta       -> actualizar si cambio la gravedad; si no, nada
      limpio  + abierta       -> resolver
      sin_dato                -> NADA, ni crear ni resolver

    En seco se calcula exactamente lo mismo y no se escribe: el 'if seco' esta
    pegado a cada escritura y no antes de la decision, para que lo que el seco
    informa sea lo que el modo real haria y no una segunda version de la
    regla que puede discrepar.
    """
    abierta = abiertas.get((tipo, proveedor))
    paso = {"tipo": tipo, "proveedor": proveedor, "estado": lectura.estado,
            "accion": "nada"}
    if lectura.motivo:
        paso["motivo"] = lectura.motivo

    if lectura.estado == SIN_DATO:
        #  Ni alarma ni alta. Ver el encabezado: resolver por falta de datos
        #  convertiria un silencio en un "ya esta todo bien".
        paso["accion"] = "nada: sin dato confiable"
        return paso

    if lectura.estado == LIMPIO:
        if abierta:
            paso.update(accion="resolver", alerta=str(abierta["id"]),
                        gravedad_previa=abierta["gravedad"])
            if not seco:
                _resolver(tenant, abierta["id"])
                registrar("alertas", "alerta resuelta", tenant=tenant,
                          tipo=tipo, proveedor=proveedor,
                          gravedad=abierta["gravedad"])
        return paso

    c = lectura.condicion
    paso.update(gravedad=c.gravedad, metrica=c.metrica,
                valor=c.valor, umbral=c.umbral)

    if not abierta:
        paso["accion"] = "crear"
        if not seco:
            creada = _crear(tenant, proveedor, c)
            #  False = otra pasada la creo primero. No es un fallo: es la
            #  antirrepeticion funcionando.
            paso["accion"] = "crear" if creada else "ya existia"
            if creada:
                registrar("alertas", "alerta abierta", tenant=tenant,
                          tipo=tipo, proveedor=proveedor, gravedad=c.gravedad,
                          metrica=c.metrica, valor=c.valor, umbral=c.umbral)
        return paso

    if abierta["gravedad"] != c.gravedad:
        paso.update(accion="actualizar", alerta=str(abierta["id"]),
                    gravedad_previa=abierta["gravedad"])
        if not seco:
            _actualizar(tenant, abierta["id"], c)
            registrar("alertas", "alerta cambia de gravedad", tenant=tenant,
                      tipo=tipo, proveedor=proveedor,
                      gravedad_previa=abierta["gravedad"],
                      gravedad=c.gravedad, valor=c.valor, umbral=c.umbral)
        return paso

    paso.update(accion="nada: ya avisada", alerta=str(abierta["id"]))
    return paso


def evaluar(config, tenant: str, seco: bool = False) -> dict:
    """
    Una pasada de alertas para una empresa. Lo que encontro y lo que hizo.

    NO LEVANTA POR UNA PARTE ROTA. Las dos senales se evaluan por separado:
    que la conciliacion falle no puede dejar sin mirar el saldo, que es la mas
    urgente de las dos. El error queda en el resultado y en el log, y la
    pasada sigue.

    Lo que SI puede levantar es un fallo de la base al leer las alertas
    abiertas: sin esa lista no se puede decidir nada sin arriesgar duplicados.
    Eso lo atrapa el reloj, que ya tiene un try/except por trabajo y por
    tenant (ver nucleo/reloj.py::una_pasada).
    """
    if not hay_endpoint_de_saldo(config):
        return {"vigilado": False,
                "motivo": "el tenant no declara llm.saldo: no hay con que "
                          "comparar"}

    proveedor = proveedor_de(config)
    abiertas = activas(tenant)
    pasos = []

    # --- saldo ---------------------------------------------------------------
    try:
        saldo, dia_foto = ultimo_saldo(tenant)
        lectura = evaluar_saldo(saldo, dia_foto=dia_foto, hoy=date.today())
    except Exception as fallo:      # noqa: BLE001 -- ver docstring
        registrar("alertas", "no se pudo evaluar el saldo", tenant=tenant,
                  error=fallo)
        lectura = Lectura(SIN_DATO, motivo=f"{type(fallo).__name__}")
    pasos.append(_aplicar(tenant, proveedor, lectura, SALDO_BAJO, abiertas, seco))

    # --- divergencia ---------------------------------------------------------
    try:
        veredicto = consumo.veredicto_conciliacion(config, tenant, DIAS_VENTANA)
        lectura = evaluar_divergencia(veredicto)
    except Exception as fallo:      # noqa: BLE001
        registrar("alertas", "no se pudo conciliar el consumo", tenant=tenant,
                  error=fallo)
        lectura = Lectura(SIN_DATO, motivo=f"{type(fallo).__name__}")
    pasos.append(_aplicar(tenant, proveedor, lectura, DIVERGENCIA, abiertas, seco))

    return {
        "vigilado": True,
        "proveedor": proveedor,
        "seco": seco,
        "creadas": sum(1 for p in pasos if p["accion"] == "crear"),
        "actualizadas": sum(1 for p in pasos if p["accion"] == "actualizar"),
        "resueltas": sum(1 for p in pasos if p["accion"] == "resolver"),
        "sin_dato": sum(1 for p in pasos if p["estado"] == SIN_DATO),
        "pasos": pasos,
    }
