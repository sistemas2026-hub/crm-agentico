"""
================================================================================
 AUTORIZAR LA ONU DE UNA INSTALACION, DESDE LA APP DE CAMPO  --  26/11/2026
================================================================================
El usuario: «en el paso 3, instalacion, cuando se ponga el serial, como se
hace para que se active la ONU en SmartOLT enseguida». Decidio: un boton
«Activar ONU» despues del serial, construido APAGADO y probado una vez con su
permiso (es una escritura en un sistema externo que da servicio).

Lo medido antes de escribir esto (skill `smartolt-api`, 26/11/2026): la ONU
nueva aparece «esperando autorizacion» con su equipo central, placa, puerto y
tipo; la empresa no usa presets, asi que la autorizacion lleva cada dato; y la
VLAN y la zona las pone la empresa (la VLAN por el servidor del contrato, la
zona sugerida por el barrio y confirmada por el tecnico: decisiones del
usuario).

EL CAMINO, Y POR QUE ASI
------------------------
1. ¿Ya esta autorizada?  -> no se manda nada (YA_ESTABA).
2. ¿Esta ESPERANDO autorizacion?  -> SOLO se escribe si el proveedor la lista
   ahi. Es la defensa principal: el puerto, la placa y el equipo central salen
   de esa fila, nunca de lo que diga el telefono.
3. El interruptor de la empresa, sin cache, pegado a la escritura.
4. La autorizacion, por la puerta HUMANA (la pide un tecnico en la casa), con
   la clave fija del pedido y sin «reintentar» lo que fallo.
5. Confirmar LEYENDO la ONU autorizada. Si no aparece a tiempo, queda EN CURSO
   y `comprobar` vuelve a mirar: una autorizacion que tarda no es una que fallo.

El motor no sabe de SmartOLT: las cuatro herramientas se encuentran por su
marca y los nombres de los campos los declara la empresa (`ParametrosDeOnu`).
================================================================================
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field

from nucleo.observabilidad.registro import registrar

ACTIVADA = "activada"                    # se autorizo en esta pasada, y se leyo
YA_ESTABA = "ya_estaba"                  # ya estaba autorizada: no se mando nada
NO_ESPERA = "no_espera"                  # no aparece esperando autorizacion
EN_CURSO = "en_curso"                    # se pidio y todavia no se ve autorizada
FALLO = "fallo"                          # el proveedor dijo que no
DATOS_INVALIDOS = "datos_invalidos"
SIN_HERRAMIENTA = "sin_herramienta"
BLOQUEADO = "bloqueado"                  # el sistema decidio no escribir
NO_SE_PUDO_COMPROBAR = "no_se_pudo_comprobar"

#: «Tarda decenas de segundos», segun el proveedor.
ESPERA_S = 45
INTERVALO_S = 5

_SERIAL = re.compile(r"^[A-Z0-9:-]{6,32}$")
_LARGO_NOMBRE = 60


@dataclass
class ResultadoOnu:
    estado: str
    motivo: str = ""
    referencia: str = ""
    olt: str = ""
    placa: str = ""
    puerto: str = ""
    #: EL PEDIDO LLEGO HASTA EL REGISTRO DE OPERACIONES: desde ahi pudo salir.
    emitido: bool = False

    @property
    def activada(self) -> bool:
        return self.estado in (ACTIVADA, YA_ESTABA)

    def como_dict(self) -> dict:
        return {"estado": self.estado, "motivo": self.motivo,
                "referencia": self.referencia, "olt": self.olt,
                "placa": self.placa, "puerto": self.puerto,
                "emitido": self.emitido}


class _NoSePudoLeer(Exception):
    """Una lectura fallo o contesto algo que no se entiende. Lleva el TIPO."""


def _herramientas(config) -> dict:
    hs = list(config.herramientas or [])
    return {
        "buscar": next((h for h in hs if getattr(h, "busca_onu_sin_autorizar", False)), None),
        "autorizar": next((h for h in hs if getattr(h, "autoriza_onu", False)), None),
        "leer": next((h for h in hs if getattr(h, "lee_onu", False)), None),
        "zonas": next((h for h in hs if getattr(h, "lista_zonas_de_red", False)), None),
    }


def serial_de(valor) -> str:
    """El serial como lo guarda el proveedor: sin espacios y en mayusculas.
    Vacio si no tiene forma de serial (no se pregunta con basura)."""
    s = re.sub(r"\s+", "", str(valor or "")).upper()
    return s if _SERIAL.match(s) else ""


def nombre_para_la_red(valor) -> str:
    """El nombre del cliente como lo acepta el proveedor: letras, numeros,
    espacios, punto y guion. Sin tildes (una «Ñ» que el proveedor rechace
    deja la ONU sin autorizar por un nombre)."""
    t = unicodedata.normalize("NFKD", str(valor or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^A-Za-z0-9 .\-]", " ", t)
    return " ".join(t.upper().split())[:_LARGO_NOMBRE]


def _filas(crudo) -> list[dict]:
    """Estricto: una lista de objetos, o `_NoSePudoLeer`. Una respuesta que no
    se entiende NO es «no hay ninguna esperando»."""
    if isinstance(crudo, dict):
        listas = [v for v in crudo.values() if isinstance(v, list)]
        crudo = listas[0] if len(listas) == 1 else None
    if not isinstance(crudo, list) or not all(isinstance(f, dict) for f in crudo):
        raise _NoSePudoLeer("forma inesperada")
    return crudo


def _rechazo(e: BaseException) -> bool:
    """Si ese error es el proveedor DICIENDO QUE NO (un 4xx que no es 408)."""
    codigo = getattr(getattr(e, "response", None), "status_code", None)
    return isinstance(codigo, int) and 400 <= codigo < 500 and codigo != 408


def _ejecutar(herr, args: dict, config, tenant: str):
    from nucleo.herramientas import http as ejecutor_http

    return ejecutor_http.ejecutar(herr, {**dict(getattr(herr, "argumentos_fijos", None) or {}),
                                         **args},
                                  tenant, variables_tenant=config.variables_tenant)


def _esperando(h: dict, config, tenant: str, serial: str) -> dict | None:
    """La fila de la ONU que espera autorizacion con ESE serial, o None."""
    herr = h["buscar"]
    po = h["autorizar"].parametros_de_onu
    try:
        crudo = _ejecutar(herr, {po.fila["serial"]: serial}, config, tenant)
    except Exception as e:                                   # noqa: BLE001
        raise _NoSePudoLeer(type(e).__name__) from None
    #  El filtro del proveedor es «contiene»: se queda la que es IGUAL.
    iguales = [f for f in _filas(crudo) if serial_de(f.get(po.fila["serial"])) == serial]
    if len(iguales) > 1:
        raise _NoSePudoLeer("mas de una ONU esperando con ese serial")
    return iguales[0] if iguales else None


def _autorizada(h: dict, config, tenant: str, serial: str) -> bool:
    """Si la ONU ya esta autorizada. Un 4xx al leerla es «no existe»: no esta.
    Cualquier otra falla es `_NoSePudoLeer`, no un «no»."""
    herr = h["leer"]
    po = h["autorizar"].parametros_de_onu
    try:
        crudo = _ejecutar(herr, {po.serial_en_la_lectura: serial}, config, tenant)
    except Exception as e:                                   # noqa: BLE001
        if _rechazo(e):
            return False
        raise _NoSePudoLeer(type(e).__name__) from None
    if isinstance(crudo, dict):
        return serial_de(crudo.get(po.campo_serial_autorizada)) == serial
    raise _NoSePudoLeer("forma inesperada")


def zonas(config, tenant: str) -> list[str]:
    """Los nombres de las zonas de la red, para que el tecnico elija."""
    h = _herramientas(config)
    if h["zonas"] is None or h["autorizar"] is None:
        return []
    po = h["autorizar"].parametros_de_onu
    try:
        filas = _filas(_ejecutar(h["zonas"], {}, config, tenant))
    except Exception as e:                                   # noqa: BLE001
        registrar("activar_onu", "no se pudieron leer las zonas", error=e)
        return []
    return sorted({str(f.get(po.campo_nombre_de_zona) or "").strip()
                   for f in filas} - {""})


def buscar(config, tenant: str, serial) -> dict:
    """SOLO LEE: si la ONU esta esperando, ya autorizada o no aparece.

    Es lo que ve el tecnico antes de tocar «Activar»: en que puerto la ve el
    equipo central. No escribe nada, ni por error.
    """
    h = _herramientas(config)
    if None in (h["buscar"], h["autorizar"], h["leer"]):
        return {"estado": SIN_HERRAMIENTA}
    s = serial_de(serial)
    if not s:
        return {"estado": DATOS_INVALIDOS, "motivo": "ese serial no tiene forma de serial"}
    po = h["autorizar"].parametros_de_onu
    try:
        if _autorizada(h, config, tenant, s):
            return {"estado": YA_ESTABA}
        fila = _esperando(h, config, tenant, s)
    except _NoSePudoLeer as e:
        return {"estado": NO_SE_PUDO_COMPROBAR, "motivo": str(e)}
    if fila is None:
        return {"estado": NO_ESPERA}
    return {"estado": "esperando",
            "olt": str(fila.get(po.fila["olt"]) or ""),
            "placa": str(fila.get(po.fila["placa"]) or ""),
            "puerto": str(fila.get(po.fila["puerto"]) or ""),
            "tipo": str(fila.get(po.fila.get("tipo", "")) or "") if po.fila.get("tipo") else ""}


def activar(config, tenant: str, *, actor: str, origen: str, datos: dict,
            espera_s: float = ESPERA_S, intervalo_s: float = INTERVALO_S) -> ResultadoOnu:
    """Autoriza la ONU, una sola vez, y confirma leyendola.

    `datos`: `serial` (obligatorio), `zona`, `vlan`, `nombre`, `direccion`.
    `origen` identifica EL PEDIDO y es la base de la clave idempotente: lo
    arma la ruta, no quien llama.
    """
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguridad import frontera, idempotencia, interruptor

    h = _herramientas(config)
    if None in (h["buscar"], h["autorizar"], h["leer"]):
        return ResultadoOnu(SIN_HERRAMIENTA, "la empresa no declara como se autoriza una ONU",
                            referencia=origen)
    herr = h["autorizar"]
    po = herr.parametros_de_onu
    serial = serial_de((datos or {}).get("serial"))
    if not serial:
        return ResultadoOnu(DATOS_INVALIDOS, "ese serial no tiene forma de serial",
                            referencia=origen)
    vlan = (datos or {}).get("vlan")
    if vlan not in (None, ""):
        try:
            vlan = int(vlan)
        except (TypeError, ValueError):
            return ResultadoOnu(DATOS_INVALIDOS, "la VLAN no es un numero", referencia=origen)
        if not 1 <= vlan <= 4094:
            return ResultadoOnu(DATOS_INVALIDOS, "la VLAN va de 1 a 4094", referencia=origen)

    #  1 y 2. ¿Ya esta? ¿Esta esperando? Antes de cualquier escritura.
    try:
        if _autorizada(h, config, tenant, serial):
            return ResultadoOnu(YA_ESTABA, "la ONU ya estaba autorizada", referencia=origen)
        fila = _esperando(h, config, tenant, serial)
    except _NoSePudoLeer as e:
        return ResultadoOnu(NO_SE_PUDO_COMPROBAR, f"no se pudo leer la ONU ({e})",
                            referencia=origen)
    if fila is None:
        return ResultadoOnu(NO_ESPERA, "la ONU no aparece esperando autorizacion: revisa que "
                                       "este conectada y el serial bien escrito",
                            referencia=origen)
    lugar = {"olt": str(fila.get(po.fila["olt"]) or ""),
             "placa": str(fila.get(po.fila["placa"]) or ""),
             "puerto": str(fila.get(po.fila["puerto"]) or "")}

    #  3. EL INTERRUPTOR, sin cache y pegado a la escritura. Falla cerrado.
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("activar_onu", "no se pudo leer el interruptor: NO se autoriza", error=e)
        return ResultadoOnu(BLOQUEADO, "no se pudo comprobar el interruptor",
                            referencia=origen, **lugar)
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(tenant, actor=actor, recurso="activar_onu",
                                   motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoOnu(BLOQUEADO, "el interruptor de la empresa esta detenido",
                            referencia=origen, **lugar)

    #  4. EL PEDIDO: el lugar sale de la FILA del proveedor; la zona, la VLAN y
    #     el nombre, de quien llama. Un dato vacio no viaja.
    valores = {"olt": fila.get(po.fila["olt"]), "tipo_pon": fila.get(po.fila["tipo_pon"]),
               "serial": serial, "placa": fila.get(po.fila["placa"]),
               "puerto": fila.get(po.fila["puerto"]),
               "tipo": fila.get(po.fila["tipo"]) if po.fila.get("tipo") else None,
               "zona": " ".join(str((datos or {}).get("zona") or "").split()),
               "vlan": vlan,
               "nombre": nombre_para_la_red((datos or {}).get("nombre")),
               "direccion": nombre_para_la_red((datos or {}).get("direccion"))}
    args = {campo: valores[dato] for dato, campo in po.campos.items()
            if valores.get(dato) not in (None, "")}

    def _fin(estado: str, motivo: str = "") -> ResultadoOnu:
        return ResultadoOnu(estado, motivo, referencia=origen, emitido=True, **lugar)

    def _hacer():
        _ejecutar(herr, args, config, tenant)
        #  Un acuse, no la respuesta del proveedor (puede traer la ficha).
        return {"pedido": True}

    try:
        with frontera.humana(tenant, herr.nombre, actor=actor, evidencia=origen, origen=origen):
            #  CLAVE FIJA POR PEDIDO y SIN `reintentar_fallida`, como el alta.
            res = idempotencia.ejecutar(tenant, herr.nombre, args, origen, _hacer,
                                        clave=f"{origen}|{herr.nombre}")
    except ejecutor_http.ErrorHerramientaHttp as e:
        registrar("activar_onu", "el ejecutor no dejo salir la autorizacion", error=e)
        return _fin(BLOQUEADO, "la autorizacion no salio: el ejecutor la freno antes de "
                               "llegar al proveedor")
    except frontera.AccionExternaNoAutorizada as e:
        registrar("activar_onu", "la frontera no autorizo la ONU", error=e)
        return _fin(BLOQUEADO, "la frontera no autorizo la ONU")
    except Exception as e:                                   # noqa: BLE001
        registrar("activar_onu", "el pedido de autorizacion volvio con error", error=e)
        if _rechazo(e):
            return _fin(FALLO, "el proveedor rechazo la autorizacion")
        #  SALIO Y NO SE SABE SI LLEGO: se mira, como si hubiera contestado.
        res = None
    if res is not None and not res.ejecutada and res.decision not in (
            "repetida", "en_curso", "fallida"):
        return _fin(BLOQUEADO, "el registro de operaciones no dejo salir este pedido")

    #  5. CONFIRMAR LEYENDO, hasta `espera_s`.
    limite = time.monotonic() + max(0.0, float(espera_s))
    while True:
        try:
            if _autorizada(h, config, tenant, serial):
                registrar("activar_onu", "la ONU quedo autorizada")
                return _fin(ACTIVADA)
        except _NoSePudoLeer:
            pass
        if time.monotonic() >= limite:
            return _fin(EN_CURSO, "se pidio y la ONU todavia no aparece autorizada")
        time.sleep(max(0.0, float(intervalo_s)))


def comprobar(config, tenant: str, serial) -> ResultadoOnu:
    """Como quedo una autorizacion que ya se pidio. SOLO LEE."""
    h = _herramientas(config)
    if None in (h["leer"], h["autorizar"]):
        return ResultadoOnu(SIN_HERRAMIENTA, "la empresa no declara como se lee una ONU")
    s = serial_de(serial)
    if not s:
        return ResultadoOnu(DATOS_INVALIDOS, "ese serial no tiene forma de serial")
    try:
        return (ResultadoOnu(ACTIVADA) if _autorizada(h, config, tenant, s)
                else ResultadoOnu(EN_CURSO, "todavia no aparece autorizada"))
    except _NoSePudoLeer as e:
        return ResultadoOnu(NO_SE_PUDO_COMPROBAR, f"no se pudo leer la ONU ({e})")
