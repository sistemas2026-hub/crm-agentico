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

import math
from datetime import timedelta

import requests

from nucleo.herramientas import http as ejecutor_http
from nucleo.herramientas import incidentes
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
        "senal_olt_dbm": None,
        "senal": "sin_dato",
        "estado_config": "",
        "puerto": "",
        "onus_en_los_a_la_vez": None,
        "motivo": motivo,
    }


#  LOS VECINOS DEL PUERTO  --  19/10/2026, caso 4 de las correcciones del
#  usuario: "varias ONU del mismo puerto en LOS a la vez es un corte de red: un
#  solo trabajo, no una visita por cliente". Lo decidio el usuario ese dia:
#  solo LOS (un "Power fail" es la luz de la casa, no la fibra).
#
#  COMO SE CUENTA, y de donde sale cada cosa:
#    - DONDE ESTA LA ONU: 'get_onu_details' trae 'olt_id', 'board' y 'port'.
#    - LAS DEL PUERTO EN LOS: 'get_all_onus_details' paginado y filtrado por
#      olt, placa, puerto y 'status=los' -- todo verificado el 19/10/2026 con el
#      metodo del valor imposible --, con 'fields=' para que vuelvan SOLO el
#      estado, la hora y el serial. Sin 'fields', cada fila trae nombre,
#      direccion y contacto del cliente.
#    - A LA VEZ: la ventana de 'incidentes' (20 minutos, medida el 21/08/2026)
#      alrededor de la caida de ESTE equipo, leida de su propia fila: el mismo
#      reloj que el de los vecinos. Un puerto acumula equipos caidos hace meses
#      --clientes que se fueron-- y esos no son el corte de hoy.
#
#  El serial solo se usa para encontrar la fila propia: no sale de aca, igual
#  que en el resto de este modulo. Lo que sale es la llave del puerto y un
#  numero. Y nunca levanta: sin poder contar, no hay corte que afirmar.
def _pieza_de_puerto(valor) -> str:
    """Una pieza de la llave del puerto: digitos, o "". El 0 vale --la placa 0
    y el puerto 0 existen--, asi que no se mira si es falso sino si es numero.
    Y solo digitos: la llave viaja al Supervisor y al modelo, y un texto del
    proveedor no puede colarse por aca (revisor de PII, 19/10/2026)."""
    texto = "" if valor is None else str(valor).strip()
    return texto if texto.isascii() and texto.isdigit() else ""


#:  Cuanto se espera a cada una de las dos consultas de los vecinos. CORTO a
#:  proposito (auditor independiente, 19/10/2026): el CRM le da 25 s al motor
#:  para TODO el diagnostico, y 'get_onu_full_status_info' ya se lleva unos 10.
#:  Sin esto, con SmartOLT lento la medicion entera vencia y se volvia a pedir
#:  cada hora. Si no contesta a tiempo, no hay corte que afirmar.
TIMEOUT_VECINOS_SEGUNDOS = 5

#:  Cuantas paginas del puerto se piden como mucho. Un puerto GPON tiene hasta
#:  128 equipos; si el proveedor recorta 'page_size', esto alcanza igual.
PAGINAS_DE_VECINOS = 3


def _vecinos_en_los(base_url: str, headers: dict, serial: str) -> dict:
    formas = {str(serial).strip().upper()}
    hexa = ejecutor_http._gpon_hex(serial)
    if hexa:
        formas.add(str(hexa).strip().upper())
    try:
        r = requests.get(f"{base_url}/api/onu/get_onu_details/{serial}",
                         headers=headers, timeout=TIMEOUT_VECINOS_SEGUNDOS)
        if not r.ok and hexa and hexa != serial:
            #  El mismo reintento que 'incidentes' y el ejecutor: 68 equipos
            #  de Rapilink solo responden con el serial en hexadecimal.
            r = requests.get(f"{base_url}/api/onu/get_onu_details/{hexa}",
                             headers=headers, timeout=TIMEOUT_VECINOS_SEGUNDOS)
        r.raise_for_status()
        detalles = (r.json() or {}).get("onu_details") or {}
        olt, placa, puerto = (_pieza_de_puerto(detalles.get(c))
                              for c in ("olt_id", "board", "port"))
        if not (olt and placa and puerto):
            registrar("diagnostico_servicio",
                      "no se pudo ubicar el equipo en su puerto")
            return {}
        filas, pagina, paginas = [], 1, 1
        while pagina <= min(paginas, PAGINAS_DE_VECINOS):
            r = requests.get(
                f"{base_url}/api/onu/get_all_onus_details", headers=headers,
                timeout=TIMEOUT_VECINOS_SEGUNDOS,
                params={"olt_id": olt, "board": placa, "port": puerto,
                        "status": "los",
                        "fields": "status,last_status_change,sn",
                        "page": pagina, "page_size": 200})
            r.raise_for_status()
            cuerpo = r.json() or {}
            filas.extend(cuerpo.get("onus") or [])
            total = cuerpo.get("total_pages")
            paginas = total if isinstance(total, int) and total > 0 else 1
            pagina += 1
        if paginas > PAGINAS_DE_VECINOS:
            registrar("diagnostico_servicio",
                      "el puerto tiene mas paginas en LOS de las que se piden: "
                      "el conteo puede quedar corto")
    except Exception as e:                                       # noqa: BLE001
        registrar("diagnostico_servicio",
                  "no se pudo contar los vecinos del puerto", error=e)
        return {}

    en_los = []
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        estado = str(fila.get("status") or "").strip().lower()
        if estado and estado != "los":
            continue
        en_los.append((str(fila.get("sn") or "").strip().upper(),
                       incidentes._a_fecha(fila.get("last_status_change"))))
    llave = f"{olt}/{placa}/{puerto}"
    if en_los and not any(sn for sn, _ in en_los):
        #  NO ES SILENCIOSO: si un dia el proveedor deja de devolver el serial
        #  con 'fields', ninguna caida se podria ubicar y el corte no se
        #  marcaria nunca. Queda dicho en el log, sin el serial.
        registrar("diagnostico_servicio",
                  "las filas del puerto no traen el serial: no se puede "
                  "ubicar la caida propia")
    propia = next((t for sn, t in en_los if sn in formas), None)
    if propia is None:
        #  ESTE equipo no figura en LOS en su puerto: no hay caida propia contra
        #  la cual comparar, y no se afirma ningun corte. Dicho en el log, sin
        #  el serial (auditor independiente, 19/10/2026: era un 0 mudo).
        registrar("diagnostico_servicio",
                  "la caida propia no figura en LOS en su puerto: no se "
                  "afirma un corte")
        return {"puerto": llave, "onus_en_los_a_la_vez": 0}
    ventana = timedelta(minutes=incidentes.VENTANA_MISMA_FALLA_MINUTOS)
    a_la_vez = sum(1 for _, t in en_los
                   if t is not None and abs(t - propia) <= ventana)
    return {"puerto": llave, "onus_en_los_a_la_vez": a_la_vez}


def _dbm(valor):
    """Un nivel en dBm como numero finito, o None. No se inventa ni se corrige:
    lo que no es un numero no es un nivel."""
    try:
        n = float(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


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

    if r.status_code == 404 or r.status_code == 400:
        #  400 EN ESTE ENDPOINT NO ES "la peticion esta mal", y decirlo asi
        #  mandaba a buscar el problema al lado equivocado.
        #
        #  La skill de SmartOLT lo tiene verificado con el metodo del valor
        #  imposible: un serial inexistente devuelve 400 "Invalid parameters".
        #  Medido ademas en produccion el 07/10/2026 sobre cinco servicios
        #  reales -- cuatro contestaron su estado optico y uno dio 400 con un
        #  serial de formato perfecto (12 caracteres, alfanumerico, sin
        #  guiones), asi que no era la forma del identificador: ese equipo no
        #  esta dado de alta en SmartOLT.
        #
        #  Esto lo lee una persona en una propuesta para decidir si cierra el
        #  caso de alguien. "contesto 400" la manda a revisar una integracion
        #  que esta bien; "no esta registrado" le dice que ese equipo no se
        #  puede diagnosticar, que es lo que de verdad pasa y lo que decide
        #  que hacer.
        return _sin_resolver(
            "el equipo de este servicio no esta registrado en SmartOLT, asi "
            "que no se puede diagnosticar su estado optico", id_servicio)

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
    #  EL NIVEL QUE RECIBE LA OLT  --  19/10/2026. Viene en la MISMA respuesta
    #  ('Optical status' trae 'OLT Rx ONT optical power(dBm)', verificado el
    #  14/08/2026 en la skill de SmartOLT) y se descartaba. El ISP lo escribe en
    #  el ticket junto al de la ONU ("-28.24 / -29.59 dBm"), y el doble
    #  diagnostico del Supervisor lo compara con lo que se mide. NO SE CLASIFICA:
    #  el rango de la guia es el de la bajada, y este numero solo informa.
    senal_olt = _dbm(optico.get("OLT Rx ONT optical power(dBm)"))
    #  Solo para una caida por perdida de señal optica: es la unica que un corte
    #  de la fibra del puerto explica, y asi las dos consultas de mas se pagan
    #  solo ahi.
    vecinos = (_vecinos_en_los(base_url, headers, serial)
               if not en_linea and causa == FIBRA else {})

    return {
        "id_servicio": id_servicio,
        "equipo_registrado": True,
        "estado": "en_linea" if en_linea else "caido",
        #  La causa solo se afirma si el equipo esta caido: la ultima causa de
        #  un equipo en linea es historia, y leerla como estado actual seria
        #  decir que esta caido cuando no lo esta.
        "causa_caida": causa if not en_linea else "",
        "senal_dbm": senal,
        "senal_olt_dbm": senal_olt,
        "puerto": vecinos.get("puerto", ""),
        "onus_en_los_a_la_vez": vecinos.get("onus_en_los_a_la_vez"),
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
