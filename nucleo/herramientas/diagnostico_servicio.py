# -*- coding: utf-8 -*-
"""
================================================================================
 DIAGNOSTICO DE UN SERVICIO  --  por id de servicio, sin que el serial salga
================================================================================

QUE PROBLEMA RESUELVE
---------------------
Las seis herramientas de ONU piden 'sn_onu' y lo exigen INYECTADO desde la
sesion verificada ('inyectados_obligatorios'), para que el modelo no pueda
elegir de que equipo pregunta. Esa garantia es correcta y no se toca.

Pero deja fuera a todo llamador que no tenga sesion: el Supervisor NOC entra por
'/interno/herramienta/', que pasa 'sesion=None' a proposito, asi que no puede
diagnosticar NINGUN equipo. Las seis estan autorizadas para su rol, con su lista
blanca de campos ya definida, y son inalcanzables.

La salida facil habria sido abrir 'sn_onu' a que lo mande el modelo y mostrarselo
en la ficha del cliente. Los dos cambios JUNTOS reconstruyen exactamente el
ataque que la inyeccion evita: ver seriales + poder pasarlos = consultar el
equipo de cualquiera.

LO QUE HACE ESTA HERRAMIENTA
----------------------------
Recibe 'id_servicio' --que SI es un argumento legitimo del modelo: esta
declarado en 'filtros_verificados', verificado contra la API, y el Supervisor lo
conoce de los afectados de una situacion-- y resuelve el equipo ADENTRO.

    el modelo pide:   diagnosticar_servicio(id_servicio=5832)
    aqui adentro:     id_servicio -> sn_onu -> estado optico de la ONU
    el modelo recibe: estado, señal, causa de caida.  NUNCA el serial.

EL SERIAL NO VIAJA EN LA RESPUESTA, y eso es la mitad del diseño. Si saliera,
bastaria una conversacion para cosechar seriales y la garantia se perderia por
otra puerta.

POR QUE EL SEGUNDO PROVEEDOR NO SE ESCRIBE AQUI
-----------------------------------------------
Resolver el serial exige preguntarle a WispHub; diagnosticar, a SmartOLT. Dos
proveedores, dos URLs, dos credenciales -- y 'nucleo/' no conoce a ninguno
(CLAUDE.md §3.1).

Asi que esta herramienta declara SU lado (el del diagnostico) como cualquier
otra, y para el otro nombra UNA HERRAMIENTA DEL MISMO CATALOGO
('resolver_equipo_con'). El ejecutor la busca por nombre y la corre con el
ejecutor de siempre, que ya sabe su base_url y su credencial. Si manana el ISP
cambia de proveedor de clientes, cambia el nombre en la configuracion y aqui no
se toca nada.

NO DECIDE SI CERRAR UN CASO, y es deliberado
--------------------------------------------
Devuelve HECHOS: si el equipo esta en linea, con que señal, y por que se cayo si
se cayo. La regla de negocio --que hacer con un caso desincronizado segun eso--
vive del lado del CRM, que es donde estan los casos. Un motor que decidiera
cerrar casos seria un motor que conoce la operacion de una empresa.
"""

from __future__ import annotations

import requests

from nucleo.herramientas import http as ejecutor_http
from nucleo.observabilidad.registro import registrar

TIMEOUT_SEGUNDOS = 25

#  Las causas de caida que SmartOLT reporta, agrupadas por lo que significan
#  PARA QUIEN DECIDE. Verificadas en vivo contra la instancia de Rapilink
#  (ver .claude/skills/smartolt-api/SKILL.md):
#
#    dying-gasp        el equipo aviso que se quedo sin energia justo antes de
#                      apagarse. Es la casa del cliente: corte de luz, o lo
#                      desenchufaron.
#    LOSi/LOBi/LOFi    perdio la señal optica. Es la fibra: corte o falla en la
#                      NAP. Eso es NUESTRO, y el cliente va a volver a llamar.
#
#  Juntarlas en "esta caida" borra justo la distincion que sirve para decidir.
SIN_ENERGIA = "sin_energia"
FIBRA = "fibra"
OTRA = "otra"

_CAUSAS = (
    ("dying-gasp", SIN_ENERGIA),
    ("losi", FIBRA),
    ("lobi", FIBRA),
    ("lofi", FIBRA),
)


#  EL RANGO DE SENAL QUE RECIBE LA ONT, y de donde sale.
#
#  La guia de operaciones de un ISP de fibra fija el aceptable entre -8 y -25
#  dBm para la senal de BAJADA, que es la que recibe el equipo del cliente. Un
#  caso sano medido en vivo contra Rapilink dio -21.74 y SmartOLT lo clasificaba
#  "Very good"; el que acaba de medirse dio -20.55.
#
#  LO QUE NO ESTA CONFIRMADO, y se dice: no se cruzo contra un caso de senal
#  MALA real. El umbral de abajo es el de la guia, no uno medido contra una
#  falla. Por eso 'debil' significa "fuera del rango declarado", no "esta roto",
#  y la decision de que hacer con eso sigue siendo del lado del CRM.
#
#  SE CLASIFICA EN CODIGO Y NO EN EL PROMPT porque el modelo no compara numeros:
#  es la regla del proyecto (el codigo calcula, el modelo redacta). Pedirle que
#  decida si -20.55 es bueno es pedirle una cuenta, y ahi se equivoca.
SENAL_MINIMA_DBM = -25.0
SENAL_MAXIMA_DBM = -8.0


def _clasificar_senal(dbm) -> str:
    """'buena', 'debil' o 'sin_dato'. Nunca adivina: sin numero, sin juicio."""
    if dbm is None:
        return "sin_dato"
    return "buena" if SENAL_MINIMA_DBM <= dbm <= SENAL_MAXIMA_DBM else "debil"


def _clasificar_causa(crudo: str) -> str:
    """De la cadena del proveedor al grupo que importa para decidir."""
    texto = (crudo or "").strip().lower()
    if not texto:
        return ""
    for patron, grupo in _CAUSAS:
        if patron in texto:
            return grupo
    return OTRA


def _sin_resolver(motivo: str, id_servicio) -> dict:
    """
    Una respuesta que dice QUE no se pudo y POR QUE.

    Nunca se devuelve algo con forma de diagnostico cuando no hubo diagnostico:
    'no se pudo preguntar' y 'esta sano' no pueden terminar en el mismo cajon,
    que es el error que este proyecto ya documento.
    """
    return {
        "id_servicio": id_servicio,
        "equipo_registrado": False,
        "estado": "desconocido",
        "causa_caida": "",
        "senal_dbm": None,
        "senal": "sin_dato",
        "estado_config": "",
        "motivo": motivo,
    }


def _resolver_serial(herramienta, argumentos, tenant, variables_tenant,
                     catalogo) -> tuple[str, str]:
    """
    El serial del equipo de ese servicio. Devuelve (serial, motivo_si_no_hay).

    Corre OTRA herramienta del catalogo --la que 'resolver_equipo_con' nombra--
    con el ejecutor de siempre, y le saca UN SOLO CAMPO. El resto de esa
    respuesta no se usa ni se devuelve: de la ficha de un cliente salen 54
    campos, cuatro de ellos contraseñas.
    """
    nombre = (herramienta.resolver_equipo_con or "").strip()
    if not nombre:
        return "", "la herramienta no declara con que resolver el equipo"

    #  El catalogo se INYECTA cuando se puede --las pruebas lo pasan-- y se
    #  carga cuando no. El despacho del motor no lo tiene, y agregarselo le
    #  cambiaria la firma a el y a sus llamadores por un ejecutor de nueve.
    if catalogo is None:
        try:
            from nucleo.config import fuente as fuente_config
            catalogo = fuente_config.cargar(tenant).herramientas
        except Exception as e:                               # noqa: BLE001
            registrar("diagnostico_servicio",
                      "no se pudo leer el catalogo del tenant", error=e)
            return "", "no se pudo leer la configuracion del tenant"

    fuente = next((h for h in (catalogo or []) if h.nombre == nombre), None)
    if fuente is None:
        return "", f"'{nombre}' no esta en el catalogo de este tenant"

    try:
        crudo = ejecutor_http.ejecutar(
            fuente, {"id_servicio": argumentos.get("id_servicio")},
            tenant=tenant, variables_tenant=variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("diagnostico_servicio",
                  "no se pudo resolver el equipo del servicio", error=e)
        return "", "no se pudo consultar el servicio en el proveedor"

    #  La respuesta puede venir como objeto suelto o paginada. Solo interesa un
    #  campo, asi que se lo busca en las dos formas y no se arrastra nada mas.
    fila = crudo
    if isinstance(crudo, dict) and isinstance(crudo.get("results"), list):
        fila = (crudo["results"] or [{}])[0]
    if not isinstance(fila, dict):
        return "", "la respuesta del proveedor no tiene la forma esperada"

    serial = str(fila.get("sn_onu") or "").strip()
    if not serial:
        #  Medido: 'sn_onu' esta vacio en 1.299 de 4.163 clientes activos. No es
        #  un fallo, es un dato que ese ISP no cargo -- y hay que decirlo asi.
        return "", "el servicio no tiene equipo registrado en el proveedor"
    return serial, ""


def diagnosticar(herramienta, argumentos: dict, tenant: str | None = None,
                 variables_tenant: dict | None = None,
                 catalogo=None) -> dict:
    """
    El estado optico del equipo de un servicio, sin devolver su serial.

    NUNCA LEVANTA: cualquier fallo sale como un diagnostico 'desconocido' con su
    motivo. Quien llama tiene que poder distinguir "esta sano" de "no se pudo
    averiguar", y una excepcion no deja decir ni una cosa ni la otra.
    """
    id_servicio = argumentos.get("id_servicio")
    if not id_servicio:
        return _sin_resolver("no se dijo de que servicio", id_servicio)

    serial, motivo = _resolver_serial(
        herramienta, argumentos, tenant, variables_tenant, catalogo)
    if not serial:
        return _sin_resolver(motivo, id_servicio)

    #  RESOLVER LA URL Y LA CREDENCIAL TAMBIEN PUEDE FALLAR, y estaba fuera del
    #  try. Esta funcion promete no levantar nunca, y 'base_url_de' levanta
    #  'ErrorHerramientaHttp' si la variable del tenant no esta cargada -- que
    #  es exactamente lo que paso en la primera prueba contra produccion, con
    #  un nombre de variable equivocado. La promesa valia para el proveedor y
    #  no para la configuracion, que es el error mas facil de cometer.
    try:
        base_url = ejecutor_http.base_url_de(
            herramienta, variables_tenant).rstrip("/")
        headers = ejecutor_http.headers_de(herramienta, tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("diagnostico_servicio",
                  "no se pudo resolver la URL o la credencial", error=e)
        return _sin_resolver(
            "falta configurar el acceso al proveedor optico para esta empresa",
            id_servicio)

    try:
        r = requests.get(
            f"{base_url}/api/onu/get_onu_full_status_info/{serial}",
            headers=headers, timeout=TIMEOUT_SEGUNDOS)
    except Exception as e:                                   # noqa: BLE001
        registrar("diagnostico_servicio",
                  "el proveedor optico no respondio", error=e)
        return _sin_resolver("el proveedor optico no respondio", id_servicio)

    if r.status_code != 200:
        return _sin_resolver(
            f"el proveedor optico contesto {r.status_code}", id_servicio)

    try:
        completo = (r.json() or {}).get("full_status_json") or {}
    except ValueError:
        return _sin_resolver("el proveedor optico no devolvio JSON", id_servicio)

    detalles = completo.get("ONU details") or {}
    optico = completo.get("Optical status") or {}

    corriendo = str(detalles.get("Run state") or "").strip().lower()
    en_linea = corriendo in ("online", "up", "en linea")
    causa = _clasificar_causa(str(detalles.get("Last down cause") or ""))

    #  La señal que importa es la que RECIBE la ONT (bajada). El campo del
    #  proveedor es 'Rx optical power(dBm)'. Si no viene, se dice que no vino --
    #  no se sustituye por la de subida, que mide otra cosa.
    try:
        senal = float(str(optico.get("Rx optical power(dBm)")).strip())
    except (TypeError, ValueError):
        senal = None

    return {
        "id_servicio": id_servicio,
        "equipo_registrado": True,
        "estado": "en_linea" if en_linea else "caido",
        #  La causa solo se afirma si el equipo esta caido: la ultima causa de
        #  un equipo en linea es historia, y leerla como estado actual seria
        #  decir que esta caido cuando no lo esta.
        "causa_caida": causa if not en_linea else "",
        "senal_dbm": senal,
        #  La clasificacion la hace el codigo, no el modelo. Ver el comentario
        #  de 'SENAL_MINIMA_DBM' para el rango y para lo que NO esta confirmado.
        "senal": _clasificar_senal(senal),
        #  'Match state' NO habla de la señal: dice si la configuracion del
        #  equipo coincide con su perfil en la OLT. Estuvo mapeado a un campo
        #  llamado 'senal_texto' y la primera corrida real devolvio 'mismatch'
        #  ahi -- con una señal de -20.55 dBm, que es BUENA. Un dato con el
        #  nombre equivocado se lee como un hecho, y ese hecho habria sido
        #  falso. Va con su nombre.
        "estado_config": str(detalles.get("Match state") or "").strip(),
        "ultima_caida": str(detalles.get("Last down time") or "").strip(),
        "ultima_conexion": str(detalles.get("Last up time") or "").strip(),
        "motivo": "",
    }
