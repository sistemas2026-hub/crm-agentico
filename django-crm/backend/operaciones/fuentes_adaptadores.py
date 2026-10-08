# -*- coding: utf-8 -*-
"""
================================================================================
 LOS ADAPTADORES  --  uno por fuente, todos devuelven la misma 'Lectura'
================================================================================

QUE ES UN ADAPTADOR
-------------------
Una funcion `(org, estado_fuente, ahora) -> Lectura`. Consulta SU fuente, arma
un resumen acotado y dice en que estado quedo. No escribe en la base, no decide
nada y no sabe de snapshots ni de frescura: eso es de 'fuentes.py'.

Tener una sola forma de salida es lo que permite tratar igual a SmartOLT --que
sale por HTTP hacia un tercero-- y a M03 --que es una consulta al ORM-- sin que
el orquestador tenga un 'if' por fuente.

LO QUE NINGUNO HACE
-------------------
Escribir afuera. Los seis son de LECTURA. Los dos que salen del proceso
(SmartOLT y WispHub) lo hacen por `GET`/`solo_lectura` a traves del motor, que
pone sus propias puertas. Ninguno crea situaciones, propuestas, casos ni
tickets, y ninguno toca el interruptor de autonomia.

EL RESUMEN NO LLEVA DATOS DE CLIENTE
------------------------------------
Lo que devuelve un adaptador termina en 'operaciones_fuente_snapshot' y, en
conteos, en el log del motor. Asi que son AGREGADOS: cuantos, por estado, por
PON. Ni un nombre, ni una cedula, ni una direccion, ni coordenadas. Importa en
particular para SmartOLT, cuya ficha de ONU trae 'name' con el nombre completo
del cliente, 'address' y lat/long (ver .claude/skills/smartolt-api), y para
WispHub, cuyo registro de cliente trae 54 campos con cuatro contrasenas.

QUE SE PUEDE Y QUE NO, HOY  --  medido el 02/10/2026
---------------------------------------------------
El unico camino por el que este backend puede llegar a un sistema externo es
`POST {MOTOR_URL}/interno/herramienta/<nombre>`, y el motor solo ejecuta ahi lo
que la config del tenant declara `invocable_por_servicio: true`. Se reviso la
config de Rapilink una por una:

  WispHub   SI se puede leer HOY. 'listar_tickets_recientes' ya esta declarada
            'solo_lectura: true' + 'invocable_por_servicio: true'. La barrera de
            Autonomia 2 que bloquea WispHub es de ESCRITURA (49.491 negaciones
            medidas, todas de acciones con efecto); leer nunca estuvo cerrado.
            No se toco ninguna politica para conseguir esto.

  SmartOLT  NO se puede todavia. NINGUNA herramienta de SmartOLT esta declarada
            'invocable_por_servicio', y ademas no existe en el catalogo ninguna
            de nivel FLOTA -- las seis que hay consultan un cliente a la vez por
            'sn_onu', y preguntar 5.061 veces cada 5 minutos no es una opcion.
            Lo que falta es declarar 'get_outage_pons' (contrato ya verificado
            en vivo contra una caida real, 18/08/2026, ver la skill). El
            adaptador de abajo esta completo y funciona el dia que esa
            declaracion se aplique; hasta entonces contesta NO_DISPONIBLE con el
            motivo exacto, nunca "0 caidas".

Esa diferencia es el motivo por el que el estado de una fuente es un dato y no
una constante: las dos estan implementadas, y la base dice cual puede contestar.
================================================================================
"""

from __future__ import annotations

import os

from django.db.models import Count, Q
from django.utils import timezone

from operaciones.fuentes import Lectura
from operaciones.fuentes_modelos import EstadoLectura, Fuente

#  El tope de cada consulta externa. No es prudencia abstracta: el proveedor de
#  SmartOLT pide explicitamente no usar sus endpoints pesados en polling, y el
#  de WispHub recorta por su cuenta cuando no se le pone ventana.
SEGUNDOS_TIMEOUT = 25

#  Cuanta ventana de tickets mira la sonda de WispHub. Corta a proposito: la
#  sonda corre seguido y lo que busca es el estado de AHORA, no el historico.
#  Ademas los rangos de fecha de esa API tienen tope (2 meses en tickets) y
#  pasarse devuelve HTTP 400.
WISPHUB_VENTANA_HORAS = 48
WISPHUB_TOPE_FILAS = 200

#  Los estados de ticket de WispHub son NUMERICOS, y una peticion por estado:
#  '?estado=1&estado=2' NO los une, se queda con el ultimo (verificado el
#  09/09/2026, ver la declaracion de 'listar_tickets_recientes'). Pedir la lista
#  de golpe habria traido un solo estado sin avisar.
WISPHUB_ESTADOS_ABIERTOS = {"nuevo": 1, "en_progreso": 2}

#  Las herramientas de flota de SmartOLT, SEPARADAS POR COMA. Vacio por
#  defecto, y eso es el estado REAL: hoy no hay ninguna declarada.
#
#  LA HISTORIA, PORQUE EL PROXIMO LECTOR VA A PREGUNTAR (02/10/2026)
#  ----------------------------------------------------------------
#  La primera version de este bloque declaro dos herramientas
#  ('consultar_caidas_pon_1' y '_2') con el 'olt_id' saliendo de dos variables
#  de tenant. Se revirtio al descubrir que la forma estaba mal:
#
#    * 'cli/reporte_incidentes_red.py::_olts()' ya consulta
#      'GET /api/system/get_olts' y ENUMERA las OLTs de la empresa en vivo. No
#      hay que configurarlas: se descubren.
#    * 'nucleo/herramientas/incidentes.py' ya encadena
#      'get_onu_details(sn_onu) -> get_outage_pons(olt_id)' y filtra por
#      board+port. El mecanismo existe; lo que faltaba no era una herramienta
#      'http' mas sino la version de FLOTA de esa composicion.
#
#  Dos declaraciones con un 'olt_id' fijo cada una habrian quedado viejas el dia
#  que la empresa agregue una OLT, y ademas exigian cargar a mano un dato que la
#  API ya contesta.
#
#  LO QUE FALTA, Y NO SE HIZO AQUI: una herramienta 'tipo: interno' --
#  'get_olts' y despues 'get_outage_pons' por cada una-- declarada
#  'solo_lectura: true' + 'invocable_por_servicio: true'. Es el mismo patron de
#  'consultar_incidente_red'. Cuesta tres puntos de contacto en el motor (una
#  bandera en 'config/schema.py', un ejecutor en 'nucleo/herramientas/' y una
#  linea de despacho en 'modelo/motor.py'), y ese trabajo NO entraba en este
#  bloque.
#
#  MIENTRAS TANTO esta fuente contesta NO_DISPONIBLE con el motivo. Lo que NO
#  hace, y es lo unico que importa, es contestar "sin caidas".
VARIABLE_HERRAMIENTA_SMARTOLT = "SUPERVISOR_HERRAMIENTAS_CAIDAS_PON"
HERRAMIENTA_SMARTOLT_POR_DEFECTO = ""

#  ESTE BACKEND NO CONOCE LAS OLTs DE LA EMPRESA, Y ES A PROPOSITO. Cual OLT se
#  consulta es un dato que varia por empresa, asi que vive en 'variables_tenant'
#  del lado del motor y la herramienta lo inyecta con
#  'argumentos_desde_variables'. Por eso el adaptador de SmartOLT manda '{}' y no
#  un 'olt_id': si lo mandara, la lista de OLTs de un cliente estaria escrita en
#  el codigo de la plataforma.
VARIABLE_HERRAMIENTA_WISPHUB = "SUPERVISOR_HERRAMIENTA_TICKETS"
HERRAMIENTA_WISPHUB_POR_DEFECTO = "listar_tickets_recientes"


class MotorNoDisponible(Exception):
    """No se pudo preguntarle al motor. No es 'no hay datos'."""


def mover_interruptor_de_autonomia(*, detener: bool, actor: str,
                                   motivo: str) -> dict:
    """
    Tira o levanta el interruptor general, por el motor. Devuelve {estado}.

    El motor exige actor y motivo, y aqui no se rellenan: un freno sin dueño no
    se puede discutir despues, y poner "sistema" por defecto haria exactamente
    eso.

    'actor' es el ID del perfil, nunca su nombre ni su correo. Esto termina en
    una tabla de auditoria y en el log del motor, y el proyecto ya tiene escrito
    que a una persona se la nombra por referencia.
    """
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = (os.environ.get("MOTOR_TENANT", "") or "").strip()
    if not tenant:
        raise MotorNoDisponible(
            "falta MOTOR_TENANT: sin saber de que empresa es el interruptor no "
            "se puede mover, y suponerlo tocaria el de otra")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    camino = "detener" if detener else "reactivar"
    try:
        r = requests.post(f"{base}/autonomia/{camino}",
                          params={"tenant": tenant},
                          json={"actor": actor, "motivo": motivo},
                          headers=cabeceras, timeout=SEGUNDOS_TIMEOUT)
    except Exception as e:                                       # noqa: BLE001
        raise MotorNoDisponible(
            f"no se pudo mover el interruptor: {type(e).__name__}") from None

    try:
        cuerpo = r.json() or {}
    except ValueError:
        cuerpo = {}
    if r.status_code != 200:
        #  El 400 del motor trae un texto util --que falta el actor o el
        #  motivo-- y ese SI viaja: lo escribio para que lo lea una persona.
        raise MotorNoDisponible(
            str(cuerpo.get("error") or f"el motor contesto HTTP {r.status_code}"))
    return {"estado": str(cuerpo.get("estado") or "")}


def estado_de_autonomia() -> dict:
    """
    El interruptor general de autonomia, preguntado AL MOTOR por HTTP.

    Devuelve {permitido, estado, motivo}. Levanta MotorNoDisponible si no se
    pudo preguntar -- quien llama decide, y en este proyecto decide que no
    poder leer el control es lo mismo que no tenerlo.

    POR QUE POR HTTP Y NO LEYENDO LA TABLA (08/10/2026)
    ---------------------------------------------------
    Porque esa tabla es del MOTOR, y 'crm_user' no tiene acceso a su schema.
    Medido en produccion: 'information_schema.schemata' devuelve 0 filas para
    'asistente' con ese usuario, mientras la tabla existe. La lectura directa
    fallaba con ProgrammingError y el interruptor quedaba permanentemente
    ilegible -- o sea que el nivel efectivo de cualquier empresa era 0 pasara
    lo que pasara, y el cierre automatico no podia funcionar nunca.

    No se arregla con un GRANT, y no por pereza: la separacion de identidades
    de base es una decision tomada despues del incidente del 18/08/2026, y este
    mismo archivo ya documenta el sentido contrario -- el motor no lee ninguna
    tabla del CRM, y cuando necesita una la pide por HTTP. Esta es la misma
    frontera, cruzada en la otra direccion y de la misma forma.

    La ruta '/autonomia' del motor existe desde antes y esta hecha justo para
    esto: es de solo lectura y NO carga la configuracion del tenant, "porque el
    interruptor tiene que poder consultarse aunque la config este rota, que es
    justo uno de los momentos en que alguien querria tirarlo".
    """
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = (os.environ.get("MOTOR_TENANT", "") or "").strip()
    if not tenant:
        raise MotorNoDisponible(
            "falta MOTOR_TENANT: sin saber de que empresa es el interruptor no "
            "se puede consultar, y suponerlo leeria el de otra")

    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    try:
        r = requests.get(f"{base}/autonomia", params={"tenant": tenant},
                         headers=cabeceras, timeout=SEGUNDOS_TIMEOUT)
    except Exception as e:                                       # noqa: BLE001
        raise MotorNoDisponible(
            f"no se pudo preguntar: {type(e).__name__}") from None

    if r.status_code != 200:
        raise MotorNoDisponible(f"el motor contesto HTTP {r.status_code}")
    try:
        cuerpo = r.json() or {}
    except ValueError:
        raise MotorNoDisponible("el motor no devolvio JSON") from None

    #  'permitido' TIENE QUE VENIR, y no se asume. Un cuerpo sin esa clave es
    #  una respuesta que no entendemos, y entenderla de menos seria asumir que
    #  permite -- exactamente lo que el fail-closed existe para impedir.
    if "permitido" not in cuerpo:
        raise MotorNoDisponible("la respuesta no trae 'permitido'")

    return {"permitido": bool(cuerpo.get("permitido")),
            "estado": str(cuerpo.get("estado") or ""),
            "motivo": str(cuerpo.get("motivo") or "")}


# =============================================================================
#  EL CAMINO HACIA UN SISTEMA EXTERNO
# =============================================================================

def _pedirle_al_motor(herramienta: str, argumentos: dict, *,
                      rol: str = "") -> dict:
    """
    Ejecuta una herramienta de SOLO LECTURA del catalogo, por el motor.

    'rol' PIDE QUE EL MOTOR APLIQUE LA POLITICA DE CAMPOS DE ESE ROL
    ---------------------------------------------------------------
    Sin 'rol' la salida viene cruda, que es lo que necesita la capa de fuentes:
    lee topologia de red --PONs caidos, conteos-- y no datos de un abonado.
    CON 'rol', el motor aplica 'listas_blancas.filtrar_campos' ANTES de
    contestar, asi que el campo no autorizado no sale de alla.

    Lo usa el chat del Supervisor para las herramientas de WispHub, donde la
    ficha cruda trae 54 campos, cuatro contrasenas y el GPS del domicilio. El
    filtro vive en el motor y no aqui a proposito: es UNA implementacion de esa
    garantia, no dos que se desincronizan.

    POR QUE NO SE LLAMA DIRECTO AL PROVEEDOR
    ----------------------------------------
    Porque la credencial de SmartOLT y la de WispHub viven SOLO en el motor, y
    copiarlas aqui seria tener dos servicios con la misma clave: lo que despues
    se desincroniza sin que nadie sepa cual es la buena. El motor ademas pone la
    lista blanca ('invocable_por_servicio'), la resolucion de argumentos
    fail-closed y el filtro de campos.

    FAIL-CLOSED CON EL TENANT, Y NO ES ESTILO
    -----------------------------------------
    Sin 'MOTOR_TENANT' no se pregunta. Este parametro decide A QUE EMPRESA se le
    consulta; suponerlo leeria los datos de otra. 'campo/services/lazo_isp.py'
    tenia aqui un `or "rapilink"` y se corrigio por exactamente eso -- no se
    reintroduce.
    """
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = (os.environ.get("MOTOR_TENANT", "") or "").strip()
    if not tenant:
        raise MotorNoDisponible(
            "falta MOTOR_TENANT: sin saber de que empresa es este sondeo no se "
            "puede consultar, y suponerlo leeria los datos de otra")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    try:
        parametros = {"tenant": tenant}
        if rol:
            parametros["rol"] = rol
        r = requests.post(
            f"{base}/interno/herramienta/{herramienta}",
            params=parametros, json=argumentos,
            headers=cabeceras, timeout=SEGUNDOS_TIMEOUT)
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de una excepcion de red trae la URL, y la
        #  URL de una consulta a SmartOLT lleva el identificador del equipo de
        #  un cliente.
        raise MotorNoDisponible(
            f"no se pudo preguntar: {type(e).__name__}") from None

    try:
        cuerpo = r.json() or {}
    except ValueError:
        cuerpo = {}

    if r.status_code == 404:
        #  404 del motor = la herramienta NO esta en el catalogo de este tenant.
        #  Es una fuente no declarada, no una falla del proveedor, y la
        #  distincion decide a quien se llama para arreglarlo.
        raise _NoDeclarada(
            f"'{herramienta}' no esta en el catalogo de este tenant")
    if r.status_code == 403:
        raise _NoDeclarada(
            f"'{herramienta}' existe pero no esta declarada "
            f"'invocable_por_servicio: true'")
    if r.status_code == 400 and cuerpo.get("error") == "ROL_DESCONOCIDO":
        #  Se pidio una politica de campos que la config de esta empresa no
        #  tiene. NO es un fallo del proveedor y no se reintenta: falta cargar
        #  la config (la base manda, el YAML es semilla -- CLAUDE.md §3.2).
        raise _NoDeclarada(
            f"el rol '{rol}' no esta en la config de este tenant: la politica "
            f"de campos no se puede aplicar, asi que no se consulta")
    if r.status_code != 200:
        #  El cuerpo NO se incluye: un 500 puede traer una pagina entera y esto
        #  termina en una columna de la base.
        raise MotorNoDisponible(
            f"el motor contesto HTTP {r.status_code}"
            + (f" ({cuerpo.get('error')})" if cuerpo.get("error") else ""))

    return cuerpo.get("resultado") if isinstance(cuerpo, dict) else None


class _NoDeclarada(Exception):
    """La herramienta no esta declarada para un servicio. No es un fallo."""


# =============================================================================
#  A. SMARTOLT  --  la fuente tecnica, y la unica que ve antes que un ticket
# =============================================================================

def smartolt(org, estado_fuente, ahora) -> Lectura:
    """
    Las caidas agrupadas por PON. La vista de FLOTA, no de un cliente.

    POR QUE 'get_outage_pons' Y NO RECORRER LAS ONUs
    -----------------------------------------------
    Porque ya resuelve la regla del splitter sin reconstruirla: devuelve, por
    puerto PON, cuantos abonados hay, cuantos estan afectados, de que tipo
    (partial_los / los / power / offline) y desde cuando. Verificado en vivo el
    18/08/2026 contra una caida real de 8 ONUs, y coincide exacto con el panel
    del proveedor -- no es un resumen con retraso, es la misma fuente.

    La alternativa era traer las ONUs y agrupar aqui. Se descarta por dos
    medidas: el filtro 'pon_port' del endpoint masivo se IGNORA en silencio
    (devuelve todos los puertos mezclados), y son 5.061 ONUs en Rapilink -- un
    recorrido cada 5 minutos contra un tercero que pide explicitamente no hacer
    polling masivo.

    EL RESUMEN ES LO QUE PERMITE COMPARAR CICLOS
    --------------------------------------------
    Una clave por PON ('olt/board/port') y, dentro, los conteos. Asi el ejemplo
    del bloque --un PON que pasa de 1 afectado a 12-- sale de restar dos
    capturas, sin haber guardado las 5.061 ONUs ni una sola vez.

    SIN DATOS DE CLIENTE: el endpoint agrupa, no nombra. 'odb_name' es el nombre
    de la CAJA en la calle (CTO 56), no de una persona.
    """
    herramientas = [h.strip() for h in
                    (os.environ.get(VARIABLE_HERRAMIENTA_SMARTOLT, "")
                     or HERRAMIENTA_SMARTOLT_POR_DEFECTO).split(",")
                    if h.strip()]
    if not herramientas:
        #  El estado real hoy. Se dice con todas las letras, y la frase importa:
        #  no se sabe como esta la red, NO se asume que esta sana.
        return Lectura(
            EstadoLectura.NO_DISPONIBLE,
            motivo_no_disponible=(
                "no hay ninguna herramienta de flota de SmartOLT declarada "
                f"(se nombran en {VARIABLE_HERRAMIENTA_SMARTOLT}). Falta una "
                "herramienta 'tipo: interno' que haga get_olts y despues "
                "get_outage_pons por cada OLT, como ya hace "
                "cli/reporte_incidentes_red.py. Hasta entonces el estado de la "
                "red NO se conoce -- no se asume que este sana."),
            tipo_consulta="outage_pons", esquema="smartolt_pon_v1")

    pons: dict = {}
    dato_en = None
    for herramienta in herramientas:
        try:
            crudo = _pedirle_al_motor(herramienta, {})
        except _NoDeclarada as e:
            #  Este es el estado REAL hoy, y se dice con todas las letras en vez
            #  de contestar "sin caidas", que seria una afirmacion falsa sobre la
            #  red de un cliente.
            return Lectura(
                EstadoLectura.NO_DISPONIBLE,
                motivo_no_disponible=(
                    f"{e}. SmartOLT no se puede consultar desde el backend "
                    f"hasta que la herramienta de flota este declarada en la "
                    f"config del tenant. Hasta entonces el estado de la red NO "
                    f"se conoce -- no se asume que este sana."),
                tipo_consulta="outage_pons", esquema="smartolt_pon_v1")
        except MotorNoDisponible as e:
            #  UNA OLT que no contesta invalida la lectura COMPLETA, y no se
            #  devuelve lo que trajeron las otras. Un resumen al que le falta una
            #  OLT se leeria como "en esa OLT no hay caidas", que es justo la
            #  afirmacion que no se puede hacer. Es mejor no saber de ninguna que
            #  creer saber de todas.
            return Lectura(EstadoLectura.ERROR, error_tecnico=str(e),
                           tipo_consulta="outage_pons",
                           esquema="smartolt_pon_v1")

        parcial, visto = _resumir_pons(crudo)
        #  Las claves son 'olt/board/port', asi que dos OLTs no se pisan. Si una
        #  clave se repitiera --misma OLT consultada dos veces por configuracion
        #  duplicada-- gana la ultima, que es el mismo dato.
        pons.update(parcial)
        if visto and (dato_en is None or visto > dato_en):
            dato_en = visto

    estado = (EstadoLectura.CON_DATOS if pons
              else EstadoLectura.SIN_REGISTROS)
    return Lectura(estado, datos=pons, registros=len(pons), dato_en=dato_en,
                   esquema="smartolt_pon_v1", tipo_consulta="outage_pons")


def _resumir_pons(crudo) -> tuple[dict, object]:
    """
    Del sobre de SmartOLT a un resumen por PON. Tolerante y sin inventar.

    La forma verificada es
    {'response': {'sections': [{'key': ..., 'groups': [{'pons': [...]}]}]}}.
    Si llega otra cosa se devuelve vacio en vez de reventar: una forma distinta
    es un cambio del proveedor, y la respuesta correcta es no tener datos, no
    tener datos falsos. Lo que NUNCA se hace es rellenar con ceros.

    'dato_en' sale del 'partial_last_seen_at' mas reciente -- el proveedor
    confirmo que esos sellos son precisos al minuto, no estimaciones. Es lo que
    permite decir si la foto es de ahora o de hace media hora.
    """
    resumen: dict = {}
    mas_reciente = None

    cuerpo = crudo.get("response") if isinstance(crudo, dict) else None
    if not isinstance(cuerpo, dict):
        #  Algunos caminos del motor devuelven ya desenvuelto.
        cuerpo = crudo if isinstance(crudo, dict) else {}

    for seccion in (cuerpo.get("sections") or []):
        if not isinstance(seccion, dict):
            continue
        tipo = str(seccion.get("key") or "sin_tipo")
        for grupo in (seccion.get("groups") or []):
            if not isinstance(grupo, dict):
                continue
            #  'subscribers' vive en el GRUPO, no en cada 'pon' -- se verifico
            #  contra el sobre real y la primera version de este archivo lo
            #  leia del 'pon', donde no existe. Es el denominador de "cuantos
            #  de cuantos": sin el, un 8 no se puede interpretar.
            abonados_grupo = _entero(grupo.get("subscribers"))
            for pon in (grupo.get("pons") or []):
                if not isinstance(pon, dict):
                    continue
                clave = "/".join(str(pon.get(c) or "?")
                                 for c in ("olt_id", "board", "port"))
                fila = resumen.setdefault(clave, {})
                fila["tipo"] = tipo
                #  Los conteos de SmartOLT llegan como TEXTO en varios campos
                #  ('total_onus': '103'). Se convierten con cuidado: un int()
                #  crudo sobre un campo vacio reventaria la sonda entera.
                if abonados_grupo is not None:
                    fila["abonados"] = abonados_grupo
                for destino, origen in (("afectados", "affected_onus"),
                                        ("total_onus", "total_onus"),
                                        ("los", "los_count"),
                                        ("energia", "power_count"),
                                        ("offline", "offline_count")):
                    v = _entero(pon.get(origen))
                    if v is not None:
                        fila[destino] = v
                pct = pon.get("affected_percent")
                if isinstance(pct, (int, float)) and not isinstance(pct, bool):
                    fila["porcentaje_afectado"] = float(pct)
                #  'odb_name' es la CAJA en la calle, no una persona.
                if pon.get("odb_name"):
                    fila["caja"] = str(pon["odb_name"])[:64]
                desde = pon.get("partial_started_at")
                if desde:
                    fila["desde"] = str(desde)[:32]
                visto = _fecha(pon.get("partial_last_seen_at"))
                if visto and (mas_reciente is None or visto > mas_reciente):
                    mas_reciente = visto

    #  Una OLT que no se pudo alcanzar NO es una OLT sin caidas. Se conserva la
    #  insuficiencia en vez de dejarla fuera del resumen.
    inalcanzables = cuerpo.get("unreachable_olts")
    if inalcanzables:
        resumen["_olts_inalcanzables"] = {
            "cuantas": len(inalcanzables) if isinstance(inalcanzables, list)
            else 1}

    return resumen, mas_reciente


def _entero(v):
    """Un entero, o None. Nunca 0 por no haber podido convertir."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _fecha(v):
    """Una fecha con zona, o None. SmartOLT manda 'YYYY-MM-DD HH:MM:SS'."""
    if not v:
        return None
    from django.utils.dateparse import parse_datetime
    try:
        d = parse_datetime(str(v).strip().replace(" ", "T"))
    except (TypeError, ValueError):
        return None
    if d is None:
        return None
    if timezone.is_naive(d):
        #  Se asume la zona del despliegue y NO UTC: el proveedor manda hora
        #  local de la instancia. Suponer UTC desplazaria el dato 5 horas y
        #  haria ver vieja una foto de hace un minuto.
        d = timezone.make_aware(d, timezone.get_current_timezone())
    return d


# =============================================================================
#  B. WISPHUB  --  tickets abiertos del sistema del ISP
# =============================================================================

def wisphub(org, estado_fuente, ahora) -> Lectura:
    """
    Cuantos tickets abiertos hay en el sistema del proveedor, por estado.

    SE PUEDE HOY, Y SIN TOCAR NINGUNA BARRERA
    -----------------------------------------
    'listar_tickets_recientes' ya esta declarada 'solo_lectura: true' +
    'invocable_por_servicio: true'. Lo que esta bloqueado en WispHub son las
    ESCRITURAS -- Autonomia 2, 49.491 negaciones medidas, todas de acciones con
    efecto. Leer no estuvo cerrado nunca, asi que no hay nada que habilitar y no
    se modifico ninguna politica.

    UNA PETICION POR ESTADO, Y NO ES UN DESCUIDO
    -------------------------------------------
    Los estados son NUMERICOS y '?estado=1&estado=2' NO los une: se queda con el
    ultimo y devuelve solo ese (verificado el 09/09/2026). Mandar la lista
    habria traido un estado silenciosamente y el resumen diria menos tickets de
    los que hay. Por eso se pide 1 y 2 por separado.

    LA VENTANA ES OBLIGATORIA: sin filtro de fecha esta API aplica un recorte
    propio que no sirve para comparar nada (medido: sin filtro 2.635 tickets,
    pero solo julio 2.637 -- un subconjunto no puede superar al conjunto).

    Lo que se guarda son CONTEOS. La 'descripcion' de un ticket es texto libre
    de un operador y trae documentos embebidos -- 136 de 300 medidos-- asi que
    no entra al resumen ni recortada.
    """
    herramienta = (os.environ.get(VARIABLE_HERRAMIENTA_WISPHUB, "")
                   or HERRAMIENTA_WISPHUB_POR_DEFECTO)
    desde = ahora - timezone.timedelta(hours=WISPHUB_VENTANA_HORAS)
    resumen: dict = {}
    total = 0

    for etiqueta, codigo in sorted(WISPHUB_ESTADOS_ABIERTOS.items()):
        try:
            crudo = _pedirle_al_motor(herramienta, {
                "fecha_creacion_0": desde.date().isoformat(),
                "fecha_creacion_1": ahora.date().isoformat(),
                "estado": codigo,
                "limit": WISPHUB_TOPE_FILAS,
            })
        except _NoDeclarada as e:
            return Lectura(
                EstadoLectura.NO_DISPONIBLE, motivo_no_disponible=str(e),
                tipo_consulta="tickets_abiertos", esquema="wisphub_tickets_v1")
        except MotorNoDisponible as e:
            #  Un fallo PARCIAL --un estado si y el otro no-- tampoco se
            #  presenta como dato: el resumen quedaria incompleto sin decirlo,
            #  que es la forma mas facil de hacer bajar un numero sin motivo.
            return Lectura(
                EstadoLectura.ERROR,
                error_tecnico=f"estado '{etiqueta}': {e}",
                tipo_consulta="tickets_abiertos", esquema="wisphub_tickets_v1")

        cuantos = _contar(crudo)
        if cuantos is None:
            return Lectura(
                EstadoLectura.ERROR,
                error_tecnico=(f"estado '{etiqueta}': la respuesta no trae un "
                               f"conteo reconocible"),
                tipo_consulta="tickets_abiertos", esquema="wisphub_tickets_v1")
        resumen[f"estado_{etiqueta}"] = {"tickets": cuantos}
        total += cuantos

    resumen["ventana"] = {"horas": WISPHUB_VENTANA_HORAS, "tickets": total}
    estado = EstadoLectura.CON_DATOS if total else EstadoLectura.SIN_REGISTROS
    #  'dato_en' queda en None a proposito: la API no fecha la RESPUESTA, y los
    #  tickets que trae tienen cada uno su fecha. Decir 'ahora' afirmaria que el
    #  dato es de ahora sin que la fuente lo haya dicho.
    return Lectura(estado, datos=resumen, registros=total,
                   esquema="wisphub_tickets_v1",
                   tipo_consulta="tickets_abiertos")


def _contar(crudo):
    """Cuantos trajo. None si la forma no permite saberlo -- nunca 0."""
    if isinstance(crudo, dict):
        for clave in ("count", "total"):
            v = _entero(crudo.get(clave))
            if v is not None:
                return v
        for clave in ("results", "tickets", "items"):
            if isinstance(crudo.get(clave), list):
                return len(crudo[clave])
        return None
    if isinstance(crudo, list):
        return len(crudo)
    return None


# =============================================================================
#  C. DEXTER / CRM  --  los casos
# =============================================================================

def dexter(org, estado_fuente, ahora) -> Lectura:
    """
    Los casos abiertos de esta organizacion, por estado y por asignacion.

    Es la fuente que el Supervisor ya usaba sin saber su estado: dos de los 15
    detectores leen 'cases.Case'. Aqui no se cambia esa lectura -- se le pone
    frescura y snapshot para que un cero se pueda distinguir de un silencio.

    EL ALCANCE DEL BLOQUE, RESPETADO SIN CONVERTIRLO EN REGLA
    -------------------------------------------------------
    El Supervisor trabaja operacionalmente con casos que YA tienen tecnico
    asignado, y por eso 'sin_asignar' y 'con_asignado' se cuentan aparte. Pero
    los casos NO son la fuente primaria de deteccion: la red puede verlo antes y
    el ticket llegar despues como evidencia. Asi que esta fuente no filtra por
    asignacion -- cuenta las dos cosas y deja que el bloque siguiente decida.

    'external_status' se cuenta porque es la unica forma de ver un caso que el
    proveedor ya cerro y Dexter no.
    """
    from cases.models import Case

    por_estado = (Case.objects
                  .filter(org=org, resolved_at__isnull=True)
                  .values("status")
                  .annotate(n=Count("id", distinct=True))
                  .order_by("status"))

    resumen = {f"estado_{fila['status'] or 'sin_estado'}": {"casos": fila["n"]}
               for fila in por_estado}

    abiertos = Case.objects.filter(org=org, resolved_at__isnull=True)

    #  'Case.assigned_to' es un ManyToMany, no una clave ajena. Eso obliga a
    #  contar con 'distinct=True': un Count con 'filter=' sobre un M2M cuenta
    #  FILAS DEL JOIN, asi que un caso con dos personas asignadas se contaria
    #  dos veces y el total de "con asignado" podria superar el de abiertos.
    #  Se midio al escribir esto, no se supuso.
    agregados = abiertos.aggregate(
        total=Count("id", distinct=True),
        con_asignado=Count("id", distinct=True,
                           filter=Q(assigned_to__isnull=False)),
        cerrados_afuera=Count("id", distinct=True, filter=Q(
            external_status__in=("Cerrado", "Closed"))),
    )
    total = agregados["total"] or 0
    con_asignado = agregados["con_asignado"] or 0
    resumen["totales"] = {
        "abiertos": total,
        #  Por RESTA y no por otro Count: 'assigned_to__isnull=True' sobre un
        #  M2M depende del tipo de join y es facil que cuente lo contrario de
        #  lo que dice. La resta no puede equivocarse de lado.
        "sin_asignar": total - con_asignado,
        "con_asignado": con_asignado,
        "cerrados_en_el_proveedor": agregados["cerrados_afuera"] or 0,
    }

    #  'dato_en' es el ultimo cambio conocido: el dato es tan nuevo como la fila
    #  mas reciente, y eso SI se puede fechar sin suponer nada.
    ultimo = (abiertos.order_by("-updated_at")
              .values_list("updated_at", flat=True).first())

    estado = EstadoLectura.CON_DATOS if total else EstadoLectura.SIN_REGISTROS
    return Lectura(estado, datos=resumen, registros=total,
                   dato_en=ultimo if total else None,
                   esquema="dexter_casos_v1", tipo_consulta="casos_abiertos")


# =============================================================================
#  D. SLA  --  el riesgo temporal, con la MISMA logica que ya existe
# =============================================================================

def sla(org, estado_fuente, ahora) -> Lectura:
    """
    El estado de plazo de las ordenes abiertas. Cuenta; no recalcula.

    REUTILIZA 'operaciones/sla.py::plazo_de' TAL CUAL
    ------------------------------------------------
    Los seis estados --VENCIDA, VENCE_PRONTO, A_TIEMPO, SIN_PLAZO, NO_APLICA,
    DATOS_INSUFICIENTES-- salen de ahi y no se reinterpretan. Escribir una
    segunda logica de SLA habria dado dos respuestas distintas a la misma
    pregunta, y la peor parte es que las dos pareceriran correctas.

    'DATOS_INSUFICIENTES' se cuenta como cualquier otro estado y NO se esconde:
    es la diferencia entre "esta orden va a tiempo" y "de esta orden no se puede
    decir si va a tiempo", y juntarlas es exactamente lo que esta capa combate.

    El calendario se busca UNA vez para el lote: 'get_default_calendar' no
    cachea, y pasarlo es la razon por la que ese argumento existe.
    """
    from campo.models import OrdenTrabajo
    from operaciones import sla as sla_modulo

    abiertas = list(OrdenTrabajo.objects
                    .filter(org=org)
                    .exclude(estado_operativo__in=sla_modulo.ESTADOS_TERMINADOS)
                    .select_related("org"))

    calendario = None
    if abiertas:
        try:
            #  El modulo es 'business_hours.calendar' y el argumento es el ID,
            #  no la organizacion: es exactamente como lo llama
            #  'operaciones/sla.py'. Se verifico en el codigo antes de escribirlo
            #  porque la primera version de este archivo erraba las dos cosas.
            from business_hours.calendar import get_default_calendar
            calendario = get_default_calendar(org.id)
        except Exception:                                        # noqa: BLE001
            #  Sin calendario 'plazo_de' asume 24/7, que es una respuesta
            #  valida y declarada -- no un fallo de la fuente.
            calendario = None

    conteo: dict = {}
    for orden in abiertas:
        plazo = sla_modulo.plazo_de(orden, ahora=ahora, calendario=calendario)
        clave = str(plazo.get("estado") or sla_modulo.DATOS_INSUFICIENTES)
        fila = conteo.setdefault(f"estado_{clave}", {"ordenes": 0})
        fila["ordenes"] += 1

    total = len(abiertas)
    conteo["totales"] = {"ordenes_abiertas": total}
    estado = EstadoLectura.CON_DATOS if total else EstadoLectura.SIN_REGISTROS
    #  El dato se CALCULA en el momento, asi que su fecha es 'ahora' de verdad:
    #  no es una foto de un tercero, es una derivacion de filas propias.
    return Lectura(estado, datos=conteo, registros=total,
                   dato_en=ahora if total else None,
                   esquema="sla_ordenes_v1", tipo_consulta="plazos_abiertos")


# =============================================================================
#  E. M02  --  actividades, compromisos, bloqueos, dependencias
# =============================================================================

def m02(org, estado_fuente, ahora) -> Lectura:
    """
    Lo que falta hacer, por estado y por tipo.

    ESTA VACIA EN PRODUCCION, Y ESO SE REGISTRA ASI
    ----------------------------------------------
    Medido: 0 actividades. De los 15 detectores del Supervisor, 13 nunca
    dispararon porque leen tablas vacias como esta y devuelven [] --
    indistinguible de "todo en orden". Esta fuente va a contestar
    SIN_REGISTROS, que es la verdad: consultada, y no hay nada.

    No se inventa un dato para que el tablero se vea poblado. Un cero con su
    procedencia escrita vale; un numero inventado no vale nada.
    """
    from operaciones.models import ActividadOperativa

    base = ActividadOperativa.objects.filter(org=org)
    por_estado = (base.values("estado_operativo")
                  .annotate(n=Count("id")).order_by("estado_operativo"))
    resumen = {f"estado_{f['estado_operativo'] or 'sin_estado'}":
               {"actividades": f["n"]} for f in por_estado}

    agregados = base.aggregate(
        total=Count("id"),
        vencidas=Count("id", filter=Q(vence_en__lt=ahora)),
        sin_responsable=Count("id", filter=Q(responsable__isnull=True)),
        bloqueadas=Count("id", filter=Q(estado_operativo="bloqueada")),
    )
    total = agregados["total"] or 0
    resumen["totales"] = {
        "actividades": total,
        "vencidas": agregados["vencidas"] or 0,
        "sin_responsable": agregados["sin_responsable"] or 0,
        "bloqueadas": agregados["bloqueadas"] or 0,
    }

    ultimo = (base.order_by("-updated_at")
              .values_list("updated_at", flat=True).first())
    estado = EstadoLectura.CON_DATOS if total else EstadoLectura.SIN_REGISTROS
    return Lectura(estado, datos=resumen, registros=total,
                   dato_en=ultimo if total else None,
                   esquema="m02_actividades_v1", tipo_consulta="actividades")


# =============================================================================
#  F. M03  --  programacion, ordenes, asignaciones, disponibilidad
# =============================================================================

def m03(org, estado_fuente, ahora) -> Lectura:
    """
    El estado de la programacion y de las ordenes.

    Cuatro tablas en un resumen porque son UNA pregunta: que trabajo hay
    planeado, para quien, y que le falta. Separarlas en cuatro fuentes haria
    que una respuesta parcial se viera como cuatro respuestas completas.

    Tambien esta practicamente vacia en produccion (0 programaciones, 0
    novedades medidas). Mismo criterio que M02: se dice SIN_REGISTROS.
    """
    from campo.models import OrdenTrabajo
    from operaciones.models import (DisponibilidadTecnico, NovedadOperativa,
                                    ProgramacionOrden, ProgramacionSemanal)

    planes = ProgramacionSemanal.objects.filter(org=org)
    por_estado = (planes.values("estado").annotate(n=Count("id"))
                  .order_by("estado"))
    resumen = {f"plan_{f['estado'] or 'sin_estado'}": {"planes": f["n"]}
               for f in por_estado}

    lineas = ProgramacionOrden.objects.filter(org=org)
    ordenes = OrdenTrabajo.objects.filter(org=org)
    resumen["lineas"] = {"total": lineas.count()}
    resumen["ordenes"] = {
        "total": ordenes.count(),
        "sin_programar": ordenes.filter(programada_para__isnull=True).count(),
    }
    resumen["disponibilidad"] = {
        "registros": DisponibilidadTecnico.objects.filter(org=org).count()}
    resumen["novedades"] = {
        "total": NovedadOperativa.objects.filter(org=org).count()}

    total = (resumen["ordenes"]["total"] + resumen["lineas"]["total"]
             + planes.count())
    resumen["totales"] = {"registros": total}

    ultimo = (ordenes.order_by("-updated_at")
              .values_list("updated_at", flat=True).first())
    estado = EstadoLectura.CON_DATOS if total else EstadoLectura.SIN_REGISTROS
    return Lectura(estado, datos=resumen, registros=total,
                   dato_en=ultimo if total else None,
                   esquema="m03_programacion_v1",
                   tipo_consulta="programacion")


# =============================================================================
#  EL MAPA  --  literal y cerrado, como el registro de trabajos del scheduler
# =============================================================================

POR_FUENTE = {
    Fuente.SMARTOLT: smartolt,
    Fuente.WISPHUB: wisphub,
    Fuente.DEXTER: dexter,
    Fuente.SLA: sla,
    Fuente.M02: m02,
    Fuente.M03: m03,
}
