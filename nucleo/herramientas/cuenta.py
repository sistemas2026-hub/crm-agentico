# -*- coding: utf-8 -*-
"""
================================================================================
 EL ESTADO DE CUENTA  --  cuanto debe quien esta en la conversacion
================================================================================

QUE PROBLEMA RESUELVE
---------------------
El agente de cobro al cliente solo veia la ficha del cliente, y la ficha trae un
'saldo' que NO es lo que debe: el 07/11/2026 un cliente con una factura
pendiente y el servicio suspendido aparecio con saldo 0.00, y el agente lo
repitio ("tu saldo es 0.00 y tienes una factura pendiente"). Se le pedia dar "el
saldo concreto que debe" sin darle con que obtenerlo.

El dato SI existe: las facturas pendientes, cada una con su total. Lo que no se
podia hacer era darle al modelo la herramienta de facturas tal cual, porque esa
herramienta filtra por un identificador que el modelo escribe. Con eso, una
inyeccion de prompt basta para pedir las facturas de otro cliente.

COMO SE RESUELVE
----------------
El modelo no pasa NADA. El 'id_servicio' sale de la sesion verificada
('inyectar_sesion'), y aqui adentro:

    id_servicio -> ficha -> usuario -> facturas pendientes de ESE usuario -> suma

    el modelo recibe:  cuantas, cuanto suman, la mas antigua, cuantas ya vencieron
    el modelo NUNCA recibe:  el usuario, ni el id de una factura, ni una lista

LA SUMA Y LA COMPARACION CON HOY SE HACEN AQUI, no en el prompt: el modelo
compone, el codigo calcula (PRD 12.5).

FALLA CERRADO, Y POR QUE ESTO ES LO DELICADO
--------------------------------------------
La documentacion de WispHub dice que 'servicio' e 'id_servicio' son filtros
validos de las facturas, y la API los IGNORA en silencio devolviendo el universo
entero con cara de exito (medido el 19/08/2026: 5.249 facturas para cualquier
cliente). Un filtro vacio funciona igual: no consulta "nadie", consulta TODOS.
Por eso aqui:

  - sin usuario en la ficha -> no se consulta, se dice que no se pudo;
  - la ficha se acepta solo si su id_servicio es EL de la sesion: si el
    proveedor ignorara ese filtro y devolviera varias, no se elige una;
  - si la lista de facturas trae mas pendientes de las que una sola persona
    puede deber, se toma como un filtro que no filtro y NO se suma: sumarle a
    un cliente la deuda de miles es peor que no dar el numero;
  - si una factura trae a nombre de quien esta y no es el usuario, igual.

'no se pudo calcular' y 'no debe nada' NO terminan en el mismo cajon: lo primero
es {"disponible": False, "motivo": ...} y lo segundo {"disponible": True,
"facturas_pendientes": 0}.

QUE SE SUMA, Y DE DONDE SALE (07/11/2026)
-----------------------------------------
Por factura se suma el 'total', SIEMPRE. En la factura de ejemplo de la
documentacion de WispHub el 'saldo' es el saldo pendiente de facturas ANTERIORES
y el 'total' (el gran total) YA LO INCLUYE: subtotal 300 + saldo 150 = total 450.
Tomar el 'saldo' como lo que se debe (lo que hacia la primera version) habria
dicho 150 donde se deben 450.

Por eso, si dos facturas pendientes de la misma persona traen saldo mayor que
cero, no se suma: la segunda podria estar arrastrando lo de la primera, y sumar
los dos totales contaria ese dinero dos veces. Sin cifra, y a una persona.
Con UNA sola, el total es exacto y se avisa que incluye saldo anterior.

LO QUE NO ESTA VERIFICADO CON DATOS REALES (y se dice): las 4.390 facturas de
Rapilink (904 pendientes, 3.479 pagadas, 7 canceladas) tienen 'saldo' en 0 sin
una sola excepcion, asi que esta lectura sale de la documentacion y no de una
factura real con saldo. Cuando aparezca la primera, hay que contrastarla.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from nucleo.herramientas import http as ejecutor_http
from nucleo.observabilidad.registro import registrar

#: Cuantas facturas pendientes puede deber UNA persona antes de que se tome como
#: un filtro que no filtro. Un cliente real debe unas pocas (el tope de rango de
#: fechas del proveedor es de tres meses; un atraso largo son meses). El universo
#: de la empresa son miles, asi que cualquier numero entre 24 y 500 separa las dos
#: cosas igual de bien: 60 deja margen a un caso extremo y sigue lejos del miedo.
MAXIMO_PENDIENTES_DE_UNA_PERSONA = 60

_FORMATOS_DE_FECHA = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y")


def _no_disponible(motivo: str) -> dict:
    """Una respuesta que dice QUE no se pudo. Nunca algo con forma de cifra."""
    return {"disponible": False, "motivo": motivo}


def _a_dinero(valor) -> Decimal | None:
    """Un monto como Decimal, o None. '' y None no son cero: son 'no hay dato'."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        n = Decimal(str(valor).strip())
    except (InvalidOperation, ValueError):
        return None
    return n if n.is_finite() else None


def _a_fecha(valor) -> date | None:
    """Una fecha, o None. Se mira solo el dia: la hora no decide un vencimiento."""
    texto = str(valor or "").strip()[:10]
    for formato in _FORMATOS_DE_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def monto_de(factura: dict, campo_total: str) -> Decimal | None:
    """
    Lo que se debe de UNA factura pendiente: su 'total', que ya incluye cualquier
    saldo anterior que arrastre. Sin total, None -- y entonces la cuenta entera no
    se afirma (ver 'calcular'): una factura sin monto no es una factura de cero.
    """
    return _a_dinero(factura.get(campo_total))


def arrastra_saldo(factura: dict, campo_saldo: str) -> bool:
    """Si la factura trae saldo anterior (mayor que cero). Un saldo ilegible NO
    cuenta como cero: se toma como que arrastra, que es el lado prudente."""
    valor = factura.get(campo_saldo)
    if valor is None or str(valor).strip() == "":
        return False
    saldo = _a_dinero(valor)
    return saldo is None or saldo > 0


def _filas(crudo) -> list[dict]:
    """La respuesta puede venir paginada ({'results': [...]}), como lista o suelta."""
    if isinstance(crudo, dict) and isinstance(crudo.get("results"), list):
        crudo = crudo["results"]
    if isinstance(crudo, dict):
        crudo = [crudo]
    return [f for f in (crudo or []) if isinstance(f, dict)] if isinstance(crudo, list) else []


def _dueno_de(factura: dict) -> str:
    """A nombre de quien dice la factura que esta, cuando lo dice. Vacio si no."""
    cliente = factura.get("cliente")
    if isinstance(cliente, dict):
        cliente = cliente.get("usuario") or cliente.get("id")
    return str(cliente or "").strip().lower()


def calcular(facturas: list[dict], *, usuario: str, cuenta: dict, hoy: date,
             hay_mas_paginas: bool = False) -> dict:
    """
    Las cuatro cifras del estado de cuenta, o 'no disponible' con el motivo.
    Pura: no llama a nadie, y por eso es lo que prueban las pruebas.
    """
    if len(facturas) > MAXIMO_PENDIENTES_DE_UNA_PERSONA:
        registrar("cuenta", "las facturas pendientes superan lo que una persona "
                            "puede deber: el filtro por cliente no filtro",
                  cantidad=len(facturas))
        return _no_disponible("el proveedor no filtro las facturas por cliente")

    esperado = (usuario or "").strip().lower()
    for f in facturas:
        dueno = _dueno_de(f)
        if dueno and dueno != esperado:
            registrar("cuenta", "una factura viene a nombre de otro cliente")
            return _no_disponible("el proveedor devolvio facturas de otro cliente")

    con_saldo = sum(1 for f in facturas if arrastra_saldo(f, cuenta["saldo"]))
    if con_saldo and len(facturas) > 1:
        # La segunda puede estar arrastrando lo de la primera: sumar los totales
        # contaria ese dinero dos veces. No se afirma ninguna cifra.
        registrar("cuenta", "varias facturas pendientes y alguna arrastra saldo: "
                            "no se suma para no contar dos veces",
                  facturas=len(facturas), con_saldo=con_saldo)
        return _no_disponible("hay saldo anterior arrastrado entre varias facturas")

    total = Decimal("0")
    vencimientos: list[date] = []
    for f in facturas:
        monto = monto_de(f, cuenta["total"])
        if monto is None:
            return _no_disponible("una factura pendiente no trae monto")
        total += monto
        vence = _a_fecha(f.get(cuenta["vencimiento"]))
        if vence is not None:
            vencimientos.append(vence)

    respuesta = {
        "disponible": True,
        "facturas_pendientes": len(facturas),
        "monto_pendiente": f"{total:.2f}",
        "vencimiento_mas_antiguo": (min(vencimientos).isoformat()
                                    if vencimientos else None),
    }
    # Solo se cuentan las que TRAEN fecha: una sin fecha no se declara vencida.
    vencidas = sum(1 for v in vencimientos if v < hoy)
    if vencidas:
        # SOLO SALE CUANDO HAY. Con 0 el campo no existe: un "0" que el modelo ve
        # es un "no tienes facturas vencidas" que el cliente escucha, y es ruido
        # (decision del dueno, 07/11/2026). Que el modelo no pueda mencionar lo que
        # no recibe es la garantia; pedirselo en el prompt seria solo una guia.
        respuesta["facturas_vencidas"] = vencidas
    if con_saldo:
        # Una sola factura, y su total ya incluye lo anterior: se dice.
        respuesta["incluye_saldo_anterior"] = True
    if hay_mas_paginas:
        # No se afirma el total completo: es lo que hay en la primera pagina.
        respuesta["completo"] = False
    return respuesta


#: El link de pago es un dato de la EMPRESA (varia de una a otra), no del codigo:
#: vive en una variable del tenant que la pantalla de Pagos edita, y la
#: configuracion de esta herramienta solo dice CUAL variable ('cuenta.link_de_pago').
LARGO_MAXIMO_DEL_LINK = 500


def link_de_pago(herramienta, variables_tenant) -> str | None:
    """
    El link para pagar, o None. Solo si la empresa lo cargo Y es una direccion
    https limpia: un valor mal escrito (sin esquema, con espacios, con usuario y
    clave incrustados) no se le da a un cliente. Fail-closed: ante la duda, nada.
    """
    nombre = ((herramienta.cuenta or {}).get("link_de_pago") or "").strip()
    if not nombre:
        return None
    valor = str((variables_tenant or {}).get(nombre) or "").strip()
    if not valor or len(valor) > LARGO_MAXIMO_DEL_LINK or any(c.isspace() for c in valor):
        return None
    from urllib.parse import urlsplit
    try:
        partes = urlsplit(valor)
    except ValueError:
        return None
    if partes.scheme != "https" or not partes.hostname or partes.username or partes.password:
        return None
    return valor


def _hoy(config) -> date:
    """El dia de hoy EN LA ZONA DE LA EMPRESA: a las 8 pm en Bogota ya es manana en UTC."""
    from datetime import timezone
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(config.identidad.zona_horaria)).date()
    except Exception:                                        # noqa: BLE001
        return datetime.now(timezone.utc).date()


def estado_de_cuenta(herramienta, argumentos, tenant, variables_tenant,
                     catalogo=None, hoy: date | None = None) -> dict:
    """Despacho: ficha -> usuario -> facturas pendientes de ese usuario -> cifras."""
    id_servicio = str((argumentos or {}).get("id_servicio") or "").strip()
    if not id_servicio:
        # Sin identidad no se consulta NADA: la ficha sin filtro es el universo.
        return _no_disponible("no hay un cliente verificado en la conversacion")

    config = None
    if catalogo is None or hoy is None:
        try:
            from nucleo.config import fuente as fuente_config
            config = fuente_config.cargar(tenant)
        except Exception as e:                               # noqa: BLE001
            registrar("cuenta", "no se pudo leer la configuracion del tenant", error=e)
            return _no_disponible("no se pudo leer la configuracion")
        catalogo = catalogo if catalogo is not None else config.herramientas
        hoy = hoy or _hoy(config)

    por_nombre = {h.nombre: h for h in (catalogo or [])}
    ficha_h = por_nombre.get(herramienta.resolver_cliente_con)
    facturas_h = por_nombre.get(herramienta.facturas_con)
    if ficha_h is None or facturas_h is None:
        return _no_disponible("la configuracion nombra una herramienta que no existe")
    cuenta = herramienta.cuenta

    pendiente = facturas_h.filtros_verificados.get("estado")
    valor_pendiente = ((getattr(pendiente, "valores", None) or {}).get("pendiente"))
    if valor_pendiente is None:
        return _no_disponible("la configuracion no dice como se pide 'pendiente'")

    try:
        crudo = ejecutor_http.ejecutar(
            ficha_h, {"id_servicio": id_servicio}, tenant=tenant,
            variables_tenant=variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("cuenta", "no se pudo leer la ficha del cliente", error=e)
        return _no_disponible("no se pudo consultar al cliente")

    # La ficha se acepta SOLO si es la de la sesion: si el proveedor ignorara el
    # filtro y devolviera varias, no se elige "la primera".
    propias = [f for f in _filas(crudo)
               if str(f.get("id_servicio") or "").strip() == id_servicio]
    if len(propias) != 1:
        return _no_disponible("no se pudo identificar la ficha del cliente")
    usuario = str(propias[0].get(cuenta["usuario"]) or "").strip()
    if not usuario:
        # Sin usuario el filtro iria vacio, y vacio es el universo entero.
        return _no_disponible("la ficha del cliente no trae con que buscar sus facturas")

    try:
        crudo_f = ejecutor_http.ejecutar(
            facturas_h, {cuenta["filtro"]: usuario, "estado": valor_pendiente},
            tenant=tenant, variables_tenant=variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("cuenta", "no se pudieron leer las facturas pendientes", error=e)
        return _no_disponible("no se pudieron consultar las facturas")

    hay_mas = isinstance(crudo_f, dict) and bool(crudo_f.get("next"))
    respuesta = calcular(_filas(crudo_f), usuario=usuario, cuenta=cuenta, hoy=hoy,
                         hay_mas_paginas=hay_mas)
    # El link SOLO viaja con una cuenta calculada Y con algo que pagar: a quien
    # no debe nada no se le da, y sin cifra tampoco (no hay "esta factura").
    if respuesta.get("disponible") and respuesta.get("facturas_pendientes"):
        enlace = link_de_pago(herramienta, variables_tenant)
        if enlace:
            respuesta["link_de_pago"] = enlace
    return respuesta
