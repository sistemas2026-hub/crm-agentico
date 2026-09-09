# -*- coding: utf-8 -*-
"""
================================================================================
 IMPORTACION DE TICKETS DEL SISTEMA OPERATIVO  --  del ISP hacia la bandeja
================================================================================

Hasta ahora los tickets viajaban en un solo sentido: una conversacion se
escalaba y abria un ticket alla. Lo que una persona abria del otro lado -- que
medido son 83 tickets por dia contra los 18 que Dexter registro en toda su
historia-- no existia de este lado.

Este modulo trae el otro sentido, y SOLO ese: cada llamada al proveedor es un
GET. Responder y cerrar ya viven en operativo.py y no se tocan desde aca.

DOS PROCESOS, NO UNO
--------------------
'descubrir' busca tickets que Dexter todavia no conoce, dentro de una ventana
por fecha de creacion. 'reconciliar' vuelve a mirar los que ya conoce, uno por
uno. Son distintos porque un ticket abierto hace tres semanas puede cambiar de
estado hoy y no aparecer en ninguna ventana de creacion -- con un solo proceso,
ese cambio no se ve nunca.

LO QUE ESTE MODULO NO DECIDE
----------------------------
No escribe. Devuelve veredictos y cambios propuestos; quien los aplica es otro.
Eso es lo que permite que el dry-run sea el MISMO codigo que la corrida real y
no una simulacion parecida que se desincroniza con el tiempo.

Tampoco toca 'Case.status'. El estado de Dexter es de Dexter; lo que el
proveedor diga vive en 'external_status'. Si divergen, la divergencia se
conserva y la mira una persona.

DEPENDENCIAS
------------
Deliberadamente pocas: pydantic para la config y 'reparto' para el desempate.
Todo lo que sale al mundo -- listar tickets, leer un cliente, saber que casos
existen -- entra como funcion. Asi las pruebas corren sin red y sin base, que
es la unica forma de probar de verdad los caminos de fallo.
================================================================================
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from nucleo.seguimiento import reparto

# --- resultados posibles de un ticket inspeccionado -------------------------
# Cada uno es un motivo DISTINTO por el que algo no entro, y estan separados
# porque llevan a acciones distintas: un asunto no permitido es una decision
# tomada, un area sin gente es un problema de plantilla, y un destino sin
# configurar es una regla que falta escribir. Un solo "descartado" los
# escondería a los tres detras del mismo numero.
CANDIDATO = "CANDIDATO"
YA_EXISTE = "YA_EXISTE"
DESCARTADO_POR_DEPARTAMENTO = "DESCARTADO_POR_DEPARTAMENTO"
DESCARTADO_POR_ASUNTO = "DESCARTADO_POR_ASUNTO"
DESCARTADO_POR_CREADOR = "DESCARTADO_POR_CREADOR"
SIN_DESTINO_CONFIGURADO = "SIN_DESTINO_CONFIGURADO"
AREA_DESTINO_INVALIDA = "AREA_DESTINO_INVALIDA"
SIN_RESPONSABLE_DISPONIBLE = "SIN_RESPONSABLE_DISPONIBLE"
SIN_SERVICIO = "SIN_SERVICIO"
DESCARTADO_POR_ESTADO = "DESCARTADO_POR_ESTADO"
ESTADO_SIN_MAPEO = "ESTADO_SIN_MAPEO"

# --- clasificacion de autoria ----------------------------------------------
DEXTER = "dexter"
HUMANO_VERIFICADO = "humano_verificado"
EXTERNO_DESCONOCIDO = "externo_desconocido"


def normalizar(texto) -> str:
    """
    Minusculas, sin acentos, espacios colapsados.

    Hace falta porque el filtro compara NOMBRES: 'GET /api/tickets/' devuelve
    'departamento' y 'asunto' como texto y no trae ningun id para ellos
    (verificado sobre 1.162 tickets, ninguna clave anidada). Sin normalizar,
    'Soporte Técnico' y 'SOPORTE TECNICO' serian dos departamentos distintos y
    la lista blanca fallaria por un acento.

    Es deuda conocida, no una eleccion. El dia que la API exponga ids, esto se
    borra.
    """
    crudo = "" if texto is None else str(texto)
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", crudo)
        if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())


def clave(departamento, asunto) -> str:
    """La clave de filtro y de mapeo: 'departamento|asunto', normalizada.

    Lleva el departamento adentro porque el mismo asunto existe en dos:
    'Cambio De Contraseña En Router Wifi' aparece 100 veces en Administrativo
    y 28 en Soporte Tecnico, y son trabajos distintos con destinos distintos.
    """
    return f"{normalizar(departamento)}|{normalizar(asunto)}"


def _comodin(departamento) -> str:
    return f"{normalizar(departamento)}|*"


@dataclass
class Veredicto:
    """Que se decidio sobre un ticket, y con que datos se decidio."""
    external_ticket_id: str
    external_service_id: str = ""
    departamento: str = ""
    asunto: str = ""
    external_status: str = ""
    external_created_by: str = ""
    external_created_by_type: str = ""
    cliente_identificado: bool = False
    identidad_es_placeholder: bool = False
    sn_onu: str = ""
    area: str = ""
    responsable: str = ""
    prioridad: str = ""
    resultado: str = ""
    detalle: str = ""

    @property
    def tiene_onu(self) -> bool:
        return bool(self.sn_onu)


@dataclass
class Cambio:
    """Lo que la reconciliacion actualizaria de un caso ya conocido."""
    caso_id: str
    external_ticket_id: str
    antes: dict = field(default_factory=dict)
    despues: dict = field(default_factory=dict)
    error: str = ""

    @property
    def hay_diferencia(self) -> bool:
        return any(self.antes.get(k) != v for k, v in self.despues.items())


# =============================================================================
#  DECISIONES  --  puras, sin red ni base
# =============================================================================

def pasa_la_lista(config_imp, departamento, asunto) -> tuple[bool, str]:
    """
    Si este ticket esta permitido, y si no, por cual de los dos filtros cayo.

    Lista vacia = NADA, nunca 'todo'. Es la unica lectura segura: un
    despliegue sin configurar no importa nada, mientras que la lectura
    contraria convertiria un olvido en 2.400 casos al mes.
    """
    permitidos = {normalizar(d) for d in config_imp.departamentos}
    if normalizar(departamento) not in permitidos:
        return False, DESCARTADO_POR_DEPARTAMENTO

    asuntos = {normalizar(a) for a in config_imp.asuntos}
    if clave(departamento, asunto) in asuntos or _comodin(departamento) in asuntos:
        return True, ""
    return False, DESCARTADO_POR_ASUNTO


def clasificar_creador(creado_por, external_ticket_id,
                       cuenta_api: str, registrados_por_dexter: set) -> str:
    """
    Quien abrio el ticket, dicho con el cuidado que los datos permiten.

    El proveedor SI informa autoria -- 'creado_por' viene poblado en el 100 %
    de los tickets, con cuentas nominales. Pero una de esas cuentas es la que
    firma la API key, y por ahi entra todo lo automatico: Dexter, cualquier
    otra integracion que comparta la clave, y una persona que inicie sesion
    con ella. Medido: 91 tickets en dos semanas entraron asi sin que Dexter
    los hubiera registrado, o sea que la clave esta compartida.

    De ahi las tres categorias. 'humano_verificado' solo cuando el proveedor
    nombro una cuenta individual; lo que llega por la cuenta compartida y no
    esta en nuestro registro es 'externo_desconocido' y no 'humano', que seria
    una afirmacion que los datos no sostienen.
    """
    autor = (creado_por or "").strip()
    if str(external_ticket_id) in registrados_por_dexter:
        return DEXTER
    if autor and normalizar(autor) != normalizar(cuenta_api):
        return HUMANO_VERIFICADO
    return EXTERNO_DESCONOCIDO


# Con que estado NACE un caso importado, segun el que tenga en el proveedor.
#
# El mapeo se aplica UNA sola vez, al crear. Despues el estado de Dexter es de
# Dexter y la reconciliacion no lo toca -- el del proveedor vive aparte, en
# 'external_status'.
#
# 'Cerrado' no esta, y no es un olvido: la decision de producto es no traer
# historia resuelta, y el filtro de descubrimiento ya lo excluye. Que tampoco
# tenga mapeo es la segunda capa: si alguien agregara 'Cerrado' a
# 'estados_descubrimiento', el ticket no se importaria igual en vez de entrar
# como caso cerrado que nadie va a mirar.
MAPEO_ESTADO_INICIAL = {
    "nuevo": "New",
    "en progreso": "Assigned",
}


def estado_inicial(external_status) -> str | None:
    """
    El 'Case.status' con el que nace un caso importado, o None si no hay mapeo.

    None significa NO IMPORTAR, no "usar el valor por defecto". La version
    anterior mandaba 'New' fijo, sin mirar el estado externo: los cuatro
    tickets 'En Progreso' de la primera importacion real nacieron como 'New' y
    quedaron un escalon antes del que les tocaba. Un valor por defecto habria
    repetido eso en silencio cada hora.
    """
    return MAPEO_ESTADO_INICIAL.get(normalizar(external_status))


def momento_del_estado(ticket: dict):
    """
    Cuando el proveedor movio el estado, o None si no se puede afirmar.

    AUDITADO EN VIVO (09/09/2026), dos veces y con dos hallazgos distintos.

    Primero: el proveedor NO entrega un sello de "ultimo cambio de estado". Lo
    unico que entrega es 'fecha_fin', y solo al cerrar -- medido sobre la
    ventana: poblada en 40 de 40 tickets 'Cerrado' y en 0 de 40 'Nuevo'. Asi
    que hay dos respuestas honestas: la fecha real del cierre, o nada. Poner
    'fecha_creacion' diria que el ticket cambio de estado cuando nacio, y poner
    el momento de nuestra lectura diria que cambio cuando miramos.

    Segundo, y por poco se escribe mal: las dos fechas del MISMO payload vienen
    en formatos distintos.

        fecha_creacion   2026-08-29T09:16:37.844072-05:00   ISO, con zona
        fecha_fin        09/05/2026 15:22:38                MM/DD/YYYY, sin zona

    Guardar 'fecha_fin' tal cual en una columna con zona la habria interpretado
    como UTC: un cierre de las 15:22 de Bogota archivado como las 15:22 de
    Londres, cinco horas antes de lo que paso. Y el formato ademas es ambiguo
    de leer -- '09/05' es 5 de septiembre solo porque el ticket nacio el 29 de
    agosto.

    La zona se toma de 'fecha_creacion' DEL MISMO TICKET, no de una constante:
    es el mismo sistema y el mismo reloj informando el mismo registro, asi que
    no hace falta suponer nada ni escribir el huso de una empresa en el nucleo.
    Sin esa referencia no se devuelve nada: un instante sin zona no es un
    instante.
    """
    if normalizar(ticket.get("estado")) != "cerrado":
        return None
    crudo = str(ticket.get("fecha_fin") or "").strip()
    if not crudo:
        return None
    try:
        cuando = datetime.strptime(crudo, "%m/%d/%Y %H:%M:%S")
    except ValueError:
        return None
    try:
        zona = datetime.fromisoformat(str(ticket.get("fecha_creacion"))).tzinfo
    except (ValueError, TypeError):
        return None
    if zona is None:
        return None
    return cuando.replace(tzinfo=zona).isoformat()


def clasificar_creador_persistente(creado_por, external_ticket_id, cuenta_api,
                                   registrados_por_dexter, tipo_guardado="") -> str:
    """
    La clasificacion de autoria para un caso QUE YA EXISTE.

    Igual que 'clasificar_creador' salvo por una regla: 'dexter' no se
    degrada. Si alguna vez supimos que ese ticket lo abrimos nosotros, eso no
    deja de ser cierto porque hoy el proveedor conteste con el nombre de la
    cuenta compartida -- que es lo que contesta SIEMPRE para todo lo que entra
    por API, incluido lo nuestro.

    Sin esto, la primera reconciliacion despues de importar convertiria cada
    caso 'dexter' en 'externo_desconocido', y la clasificacion empeoraria sola
    con el tiempo. La evidencia interna (nuestro propio registro) es mas
    especifica que una identidad que el proveedor comparte entre todos.
    """
    if tipo_guardado == DEXTER:
        return DEXTER
    return clasificar_creador(creado_por, external_ticket_id,
                              cuenta_api, registrados_por_dexter)


def destino_de(config_imp, departamento, asunto):
    """El destino declarado para este ticket, o None. Cae a 'departamento|*'."""
    normalizados = {normalizar(k): v for k, v in config_imp.destinos.items()}
    return (normalizados.get(clave(departamento, asunto))
            or normalizados.get(_comodin(departamento)))


def responsable_para(area: str, areas_por_persona: dict,
                     carga: dict | None = None) -> str | None:
    """
    A quien de esa area le toca. None si no hay nadie.

    Se resuelve ACA y no en la config a proposito: una persona se va de
    vacaciones, entra otra, cambia de equipo -- y con el profile_id escrito en
    el YAML, cada uno de esos dias normales obligaria a editar la integracion.
    El area es la regla de negocio; la persona es su consecuencia del dia.

    El desempate lo hace 'reparto', el mismo que ya reparte los tickets que
    salen: dos criterios distintos para lo mismo terminarian discrepando.
    """
    candidatos = [p for p, a in (areas_por_persona or {}).items()
                  if normalizar(a) == normalizar(area)]
    return reparto.elegir_menos_cargado(candidatos, carga)


# =============================================================================
#  DESCUBRIMIENTO
# =============================================================================

def debe_correr(config_imp, ultima: datetime | None = None,
                ahora: datetime | None = None) -> bool:
    """
    Si al barrido le toca. Con 'cada_horas' en 0 -- el valor por defecto -- NO.

    Es la compuerta que hace que desplegar este codigo no importe nada por su
    cuenta. Vive aca y no en el reloj del motor a proposito: el reloj sabe de
    tiempo, no de esta integracion, y la regla "0 significa apagado" tiene que
    poder probarse sin levantar un hilo.

    Se comprueba en cada pasada y no al arrancar: 'cada_horas' se cambia
    guardando la config, que es justo lo que un proceso ya arrancado no
    relee. Condicionarlo al arranque lo dejaria dormido hasta el proximo
    reinicio -- el mismo error que el reloj de vencimientos ya documenta.
    """
    if not config_imp.cada_horas or config_imp.cada_horas <= 0:
        return False
    if ultima is None:
        return True
    ahora = ahora or datetime.now(timezone.utc)
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    return (ahora - ultima) >= timedelta(hours=config_imp.cada_horas)


def ventana(config_imp, ahora: datetime | None = None) -> tuple[str, str]:
    """
    Desde cuando y hasta cuando mirar, en 'YYYY-MM-DD'.

    Una ventana MOVIL de 'ventana_dias', sin checkpoint persistido. Repetir lo
    ya visto no cuesta: un ticket que ya tiene caso se corta contra los
    conocidos antes de resolver ninguna identidad, y la unicidad la sostiene
    la base. A cambio, la ventana entera es la red de recuperacion -- un ciclo
    que falla no deja nada atras, porque no habia nada que avanzar.

    El tope de 55 dias no es prudencia: el proveedor responde HTTP 400 a
    cualquier ventana mayor a dos meses.
    """
    ahora = ahora or datetime.now(timezone.utc)
    dias = min(max(config_imp.ventana_dias, 1), 55)
    desde = ahora - timedelta(days=dias)
    return desde.date().isoformat(), ahora.date().isoformat()


def descubrir(config, tickets: list[dict], *,
              conocidos: set,
              registrados_por_dexter: set,
              areas_por_persona: dict,
              cuenta_api: str,
              servicio_placeholder: str = "",
              resolver_servicio=None,
              carga: dict | None = None) -> list[Veredicto]:
    """
    Un veredicto por ticket inspeccionado. No escribe nada, en ningun modo.

    'resolver_servicio' recibe una LISTA de id_servicio y devuelve
    {id_servicio: {...cliente...}}. Se llama UNA vez, con los servicios unicos
    de los tickets que pasaron el filtro: medido, 1.162 tickets son 607
    servicios distintos, asi que consultar por ticket seria casi el doble de
    llamadas para el mismo dato. Y solo despues del filtro, para no pagar
    ninguna consulta por un ticket que no iba a entrar.
    """
    conf = config.importacion_tickets
    areas_validas = {normalizar(a.nombre) for a in (config.areas or [])}

    # --- primera pasada: todo lo que se decide sin salir a la red ---------
    #
    # Cada ticket entra a 'veredictos' en el ORDEN EN QUE LLEGO, decida lo que
    # decida. 'pendientes' guarda referencias a los que todavia les falta la
    # identidad, y la segunda pasada los completa en su lugar: quien lee el
    # reporte tiene que poder seguirlo contra el listado del proveedor, y una
    # salida reordenada por resultado obliga a buscar cada ticket.
    veredictos: list[Veredicto] = []
    pendientes: list[Veredicto] = []
    for t in tickets:
        servicio = t.get("servicio") if isinstance(t.get("servicio"), dict) else {}
        v = Veredicto(
            external_ticket_id=str(t.get("id_ticket", "")),
            external_service_id=str(servicio.get("id_servicio") or ""),
            departamento=t.get("departamento") or "",
            asunto=t.get("asunto") or "",
            external_status=t.get("estado") or "",
            external_created_by=(t.get("creado_por") or "").strip(),
        )
        veredictos.append(v)
        v.external_created_by_type = clasificar_creador(
            v.external_created_by, v.external_ticket_id,
            cuenta_api, registrados_por_dexter)

        permitido, motivo = pasa_la_lista(conf, v.departamento, v.asunto)
        if not permitido:
            v.resultado = motivo
            continue

        # El estado se mira ACA: antes de resolver identidad, cliente y ONU.
        # Enriquecer un ticket que ya sabemos que se descarta es pagar una
        # llamada por un dato que nadie va a leer, y en el piloto eran 118 de
        # 139. Vacio no significa 'todos': significa que no entra ninguno.
        #
        # Solo gobierna el DESCUBRIMIENTO. Un ticket que se cierra despues de
        # importado lo sigue la reconciliacion, que no mira esta lista: el
        # caso ya existe y su estado externo tiene que poder cambiar.
        if v.external_status not in conf.estados_descubrimiento:
            v.resultado = DESCARTADO_POR_ESTADO
            continue

        # Que el estado este permitido no alcanza: tiene que saberse con que
        # estado propio nace el caso. Fail-closed -- sin mapeo no se importa.
        if estado_inicial(v.external_status) is None:
            v.resultado = ESTADO_SIN_MAPEO
            v.detalle = f"no hay estado inicial para '{v.external_status}'"
            continue

        if conf.tipos_de_creador and \
                v.external_created_by_type not in conf.tipos_de_creador:
            v.resultado = DESCARTADO_POR_CREADOR
            continue

        # Antes que cualquier resolucion de identidad: un ticket que ya tiene
        # caso no necesita ninguna consulta. Es tambien lo que hace que dos
        # pasadas seguidas no produzcan dos casos -- el solapamiento de la
        # ventana los vuelve a traer y aca se paran.
        if v.external_ticket_id in conocidos:
            v.resultado = YA_EXISTE
            continue

        if not v.external_service_id:
            v.resultado = SIN_SERVICIO
            continue

        destino = destino_de(conf, v.departamento, v.asunto)
        if destino is None:
            v.resultado = SIN_DESTINO_CONFIGURADO
            continue

        v.area = destino.area
        v.prioridad = destino.prioridad
        if normalizar(destino.area) not in areas_validas:
            v.resultado = AREA_DESTINO_INVALIDA
            v.detalle = f"'{destino.area}' no esta declarada en areas"
            continue

        elegido = responsable_para(destino.area, areas_por_persona, carga)
        if not elegido:
            # No se crea igual. Un caso sin responsable no tiene area -- el
            # area sale de la persona-- y terminaria invisible para todo el
            # equipo salvo quien administra. Peor que no crearlo.
            v.resultado = SIN_RESPONSABLE_DISPONIBLE
            v.detalle = f"nadie con area '{destino.area}'"
            continue

        v.responsable = elegido
        pendientes.append(v)

    # --- segunda pasada: la identidad, por SERVICIO unico ------------------
    if pendientes and resolver_servicio:
        # El cliente ficticio queda afuera de la consulta: no es una persona.
        unicos = sorted({v.external_service_id for v in pendientes
                         if v.external_service_id != str(servicio_placeholder)})
        fichas = resolver_servicio(unicos) if unicos else {}
        for v in pendientes:
            if v.external_service_id == str(servicio_placeholder):
                # Se conserva la referencia externa -- vino del proveedor y es
                # cierta-- pero no se le atribuye a nadie ni se le busca ONU:
                # es el registro que la empresa usa para poder abrir un ticket
                # de instalacion cuando el cliente todavia no existe.
                v.identidad_es_placeholder = True
                v.detalle = "servicio de instalaciones: prospecto sin identidad resuelta"
            else:
                ficha = fichas.get(v.external_service_id) or {}
                v.cliente_identificado = bool(ficha)
                v.sn_onu = str(ficha.get("sn_onu") or "")
            v.resultado = CANDIDATO
    else:
        for v in pendientes:
            v.resultado = CANDIDATO

    return veredictos


# =============================================================================
#  RECONCILIACION
# =============================================================================

def hay_que_reconciliar(config_imp, caso: dict,
                        ahora: datetime | None = None) -> bool:
    """
    Si vale la pena volver a preguntar por este caso.

    Se reconcilia lo que todavia se esta trabajando, mas una gracia despues de
    cerrar: el cierre de Dexter y el del proveedor no son el mismo momento, y
    esa divergencia de unos dias es justo la que se quiere poder mostrar.
    Fuera de eso no se pregunta: releer para siempre miles de casos cerrados
    es trafico permanente para enterarse de nada.
    """
    if caso.get("status") in config_imp.reconciliar_estados:
        return True
    cerrado = caso.get("closed_on")
    if not cerrado:
        return False
    ahora = ahora or datetime.now(timezone.utc)
    if isinstance(cerrado, str):
        try:
            cerrado = datetime.fromisoformat(cerrado)
        except ValueError:
            return False
    # 'Case.closed_on' es un DateField, asi que la base devuelve un 'date' y no
    # un 'datetime' -- y 'date.replace()' no acepta tzinfo. Reventaba con
    # TypeError sobre datos reales mientras las pruebas, que le pasaban cadenas
    # ISO, pasaban en verde: 'fromisoformat' de una cadena con hora si da un
    # datetime. Encontrado en el primer dry-run contra produccion.
    if isinstance(cerrado, date) and not isinstance(cerrado, datetime):
        cerrado = datetime(cerrado.year, cerrado.month, cerrado.day,
                           tzinfo=timezone.utc)
    if getattr(cerrado, "tzinfo", None) is None:
        cerrado = cerrado.replace(tzinfo=timezone.utc)
    return (ahora - cerrado) <= timedelta(days=config_imp.gracia_cierre_dias)


def reconciliar(config, casos: list[dict], *, leer_ticket,
                cuenta_api: str, registrados_por_dexter: set,
                ahora: datetime | None = None) -> list[Cambio]:
    """
    Que cambiaria de cada caso ya conocido. No escribe.

    Se consulta ticket por ticket ('GET /api/tickets/<id>/', que existe y
    responde) y no por ventana: un ticket abierto hace tres semanas puede
    cambiar hoy y no aparecer en ninguna ventana por fecha de creacion.

    'Case.status' NO esta entre lo que se toca, y no por olvido: el estado de
    Dexter es de Dexter. Lo que diga el proveedor vive en 'external_status', y
    si los dos discrepan la discrepancia se conserva para que la mire una
    persona.

    Un fallo en un ticket queda escrito en ESE caso y no corta el lote: que un
    ticket no responda no es motivo para no enterarse de los otros doscientos.
    """
    ahora = ahora or datetime.now(timezone.utc)
    cambios: list[Cambio] = []

    for caso in casos:
        if not hay_que_reconciliar(config.importacion_tickets, caso, ahora):
            continue
        tid = str(caso.get("external_ticket_id") or "")
        cambio = Cambio(
            caso_id=str(caso.get("id") or ""),
            external_ticket_id=tid,
            antes={
                "external_status": caso.get("external_status") or "",
                "external_created_by": caso.get("external_created_by") or "",
                "external_created_by_type": caso.get("external_created_by_type") or "",
                "external_fetch_error": caso.get("external_fetch_error") or "",
            },
        )
        try:
            t = leer_ticket(tid)
        except Exception as e:                              # noqa: BLE001
            cambio.error = f"{type(e).__name__}: {e}"
            # El fallo se escribe en la fila para que se vea en la plataforma,
            # y no toca el estado: un error de lectura no dice nada del caso.
            cambio.despues = {"external_fetch_error": cambio.error[:500]}
            cambios.append(cambio)
            continue

        # Se exige que la respuesta SEA ese ticket, no solo que sea un dict.
        # La guarda anterior pedia "dict no vacio", y un listado paginado
        # ({count, next, results}) lo es: con la herramienta equivocada la
        # reconciliacion daba 16/16 leidos y proponia vaciar el estado de los
        # 16. Comparar el id devuelto contra el pedido es lo unico que
        # distingue "me contestaron por este ticket" de "me contestaron algo".
        if not isinstance(t, dict) or str(t.get("id_ticket") or "") != str(tid):
            cambio.error = (f"la respuesta no corresponde al ticket {tid} "
                            f"(claves: {sorted(t)[:6] if isinstance(t, dict) else type(t).__name__})")
            cambio.despues = {"external_fetch_error": cambio.error[:500]}
            cambios.append(cambio)
            continue

        autor = (t.get("creado_por") or "").strip()
        cambio.despues = {
            "external_status": t.get("estado") or "",
            "external_status_at": momento_del_estado(t),
            "external_created_by": autor,
            # Persistente: un caso que ya sabemos que abrio Dexter no se
            # degrada a 'externo_desconocido' porque el proveedor conteste
            # con el nombre de la cuenta compartida.
            "external_created_by_type": clasificar_creador_persistente(
                autor, tid, cuenta_api, registrados_por_dexter,
                caso.get("external_created_by_type") or ""),
            # Una lectura correcta limpia el error anterior: dejarlo puesto
            # mostraria para siempre un fallo que ya se resolvio.
            "external_fetch_error": "",
            "external_fetched_at": ahora.isoformat(),
        }
        cambios.append(cambio)

    return cambios


def resumen(veredictos: list[Veredicto]) -> dict:
    """El conteo por resultado, mas lo que hay que mirar aunque no sea un conteo."""
    conteo: dict[str, int] = {}
    for v in veredictos:
        conteo[v.resultado] = conteo.get(v.resultado, 0) + 1
    candidatos = [v for v in veredictos if v.resultado == CANDIDATO]
    return {
        "inspeccionados": len(veredictos),
        "por_resultado": dict(sorted(conteo.items(), key=lambda x: -x[1])),
        "candidatos": len(candidatos),
        "con_cliente_real": sum(1 for v in candidatos if v.cliente_identificado),
        "placeholder_instalaciones": sum(
            1 for v in candidatos if v.identidad_es_placeholder),
        "con_onu": sum(1 for v in candidatos if v.tiene_onu),
        "sin_onu": sum(1 for v in candidatos if not v.tiene_onu),
        "por_tipo_de_creador": _contar(veredictos, "external_created_by_type"),
        "candidatos_por_tipo": _contar(candidatos, "external_created_by_type"),
        "candidatos_por_responsable": _contar(candidatos, "responsable"),
        "candidatos_por_area": _contar(candidatos, "area"),
    }


def _contar(items, atributo) -> dict:
    salida: dict[str, int] = {}
    for i in items:
        v = getattr(i, atributo) or "(vacio)"
        salida[v] = salida.get(v, 0) + 1
    return dict(sorted(salida.items(), key=lambda x: -x[1]))
