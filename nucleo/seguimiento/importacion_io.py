# -*- coding: utf-8 -*-
"""
================================================================================
 IMPORTACION -- LOS EFECTOS  (lo unico de esta funcion que sale del proceso)
================================================================================

'importacion.py' decide y no toca nada. Este modulo hace: habla con el sistema
del ISP, escribe casos en el CRM, y aplica lo que aquel decidio.

La separacion no es estetica. Las decisiones -- que entra, a quien le toca,
como se clasifica la autoria-- son las que hay que poder probar en todos sus
caminos de fallo, y probarlas es barato solo mientras no haya red ni base de
por medio. Del otro lado quedan las llamadas, que se prueban distinto y se
rompen por otros motivos.

QUIEN CONSUME ESTO
------------------
'cli/importar_tickets.py' (una persona, a mano) y el reloj del motor (cada
hora, cuando se encienda). Los dos llaman a las MISMAS funciones: un camino
manual que se parece al automatico es un camino manual que miente el dia que
hay que usarlo.

NADA DE ESTO ESCRIBE EN WISPHUB
-------------------------------
Contra el proveedor, solo GET. Responder y cerrar viven en operativo.py y esta
fase no los toca.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timezone

from nucleo.herramientas import http as ejecutor_http
from nucleo.persistencia import db as persistencia
from nucleo.seguimiento import importacion as imp

# El nombre de la herramienta de listado SI puede vivir aca: es del catalogo
# generico, no de una empresa. El proveedor y la cuenta con la que firma no --
# esos salen de 'config.importacion_tickets' (ver ARQUITECTURA.md: el nucleo no
# conoce a ningun cliente, y tests/test_nucleo_sin_tenants.py lo comprueba).
HERRAMIENTA_LISTADO = "listar_tickets_recientes"

# TODAS las herramientas del catalogo que este modulo busca por nombre.
#
# Existe para que el reloj pueda decir ANTES de correr si el tenant tiene lo
# que hace falta -- las herramientas en el catalogo y sus credenciales
# resolubles -- sin repetir la lista en otro archivo. Guarda contra la deriva:
# tests/test_reloj.py relee este mismo modulo, junta cada nombre que se le pide
# a _herramienta, y exige que todos esten declarados aca abajo.
HERRAMIENTAS = frozenset({
    HERRAMIENTA_LISTADO,
    "consultar_ticket_por_id",
    "consultar_tickets_conocidos",
    "consultar_casos_externos",
    "importar_caso_externo",
    "reconciliar_caso_externo",
    "sincronizar_respuestas_externas",
})


def _herramienta(config, nombre):
    return next((h for h in config.herramientas if h.nombre == nombre), None)


# Los codigos de estado son del proveedor y viven en la config del tenant, no
# aca -- salvo esta tabla, que es la traduccion entre la etiqueta que el
# proveedor DEVUELVE y el codigo que ACEPTA como filtro. Son dos vocabularios
# distintos para el mismo campo: '?estado=Nuevo' devuelve cero sin error.
# Verificado el 09/09/2026: 1=Nuevo (102), 2=En Progreso (9), 4=Cerrado (936),
# y 102+9+936 = 1.047 = el total sin filtro.
CODIGO_DE_ESTADO = {"nuevo": 1, "en progreso": 2, "cerrado": 4}


def listar_tickets(config, tenant, desde, hasta, tope=5000) -> list[dict]:
    """
    Los tickets de la ventana. Si hay estados permitidos, UNA PETICION POR
    ESTADO y el filtro va en el servidor.

    Una peticion por estado y no una sola con los dos valores: probado el
    09/09/2026, '?estado=1&estado=2' NO los une -- se queda con el ultimo y
    devuelve 9 en vez de 111. Mandar la lista habria importado un solo estado
    en silencio, que es la peor forma de fallar.

    Filtrar en el servidor no es una optimizacion menor: en el piloto son 111
    tickets traidos en vez de 1.047, y los 936 cerrados no viajan siquiera.
    """
    herr = _herramienta(config, HERRAMIENTA_LISTADO)
    if herr is None:
        raise SystemExit(
            f"Falta la herramienta '{HERRAMIENTA_LISTADO}' en la config de "
            f"'{tenant}'. Esta en tenants/{tenant}.config.yaml -- si la config "
            f"vigente sale de la base, cargala con cli/cargar_config.py o corre "
            f"esto con --config-yaml.")

    estados = config.importacion_tickets.estados_descubrimiento
    codigos = [CODIGO_DE_ESTADO.get(imp.normalizar(e)) for e in estados]
    sin_traducir = [e for e, c in zip(estados, codigos) if c is None]
    if sin_traducir:
        # Fail-closed: un estado que no se sabe traducir no se pide "por las
        # dudas sin filtro" -- eso traeria los 936 cerrados.
        raise SystemExit(
            f"No se como pedirle al proveedor los estados {sin_traducir}. "
            f"Conocidos: {sorted(CODIGO_DE_ESTADO)}.")
    # Sin estados configurados no se pide nada: no hay ningun ticket que pueda
    # pasar el filtro, asi que traerlos seria trafico para descartarlo entero.
    if not codigos:
        return []

    filas = []
    for codigo in codigos:
        offset = 0
        while len(filas) < tope:
            datos = ejecutor_http.ejecutar(
                herr, {"fecha_creacion_0": desde, "fecha_creacion_1": hasta,
                       "estado": codigo, "limit": 100, "offset": offset},
                tenant, variables_tenant=config.variables_tenant)
            pagina = datos.get("results") if isinstance(datos, dict) else None
            if not pagina:
                break
            filas.extend(pagina)
            if not (isinstance(datos, dict) and datos.get("next")):
                break
            offset += 100
    return filas


def leer_ticket(config, tenant, id_ticket) -> dict:
    """
    Un ticket suelto, para reconciliar uno que salio de la ventana.

    Va contra 'consultar_ticket_por_id' y NO contra 'consultar_ticket', que se
    le parece y no sirve: esa apunta a '/api/tickets/' sin marcador, asi que
    devuelve el listado entero. Como el listado tambien es un dict no vacio, la
    reconciliacion lo daba por leido y proponia vaciar 'external_status'.
    """
    herr = _herramienta(config, "consultar_ticket_por_id")
    if herr is None:
        raise RuntimeError(
            "falta 'consultar_ticket_por_id' en el catalogo: sin ella no se "
            "puede leer un ticket por su numero")
    return ejecutor_http.ejecutar(
        herr, {"id_ticket": str(id_ticket)}, tenant,
        variables_tenant=config.variables_tenant)


def resolver_servicios(config, tenant):
    """
    {id_servicio: ficha} para una lista de servicios UNICOS.

    Reusa la misma eleccion de herramienta que la pantalla del ticket
    (_ficha_cliente en api.py): la que declara el filtro por 'id_servicio'.
    Elegir "la primera que apunte a /api/clientes/" devolveria el primer
    cliente de la empresa con aspecto de respuesta correcta.
    """
    herr = next((h for h in config.herramientas
                 if h.tipo == "http" and "id_servicio" in (h.filtros_verificados or {})),
                None)

    def resolver(ids):
        salida = {}
        if herr is None:
            return salida
        for sid in ids:
            try:
                datos = ejecutor_http.ejecutar(
                    herr, {"id_servicio": str(sid)}, tenant,
                    variables_tenant=config.variables_tenant)
                fila = (datos.get("results") or [None])[0] \
                    if isinstance(datos, dict) else None
                if isinstance(fila, dict):
                    # Solo lo que el importador necesita. La fila cruda trae 54
                    # campos, incluidas cuatro contraseñas y el GPS del
                    # domicilio: nada de eso tiene por que salir de aca.
                    salida[str(sid)] = {"sn_onu": fila.get("sn_onu") or "",
                                        "usuario": fila.get("usuario") or "",
                                        "estado": fila.get("estado") or ""}
            except Exception as e:                          # noqa: BLE001
                print(f"    [aviso] servicio {sid}: {type(e).__name__}: {e}")
        return salida

    return resolver


def casos_de_este_proveedor(config, tenant: str) -> list[dict]:
    """Los casos con referencia externa, para reconciliar. Por la API, no por SQL."""
    herr = _herramienta(config, "consultar_casos_externos")
    if herr is None:
        raise SystemExit("falta 'consultar_casos_externos' en el catalogo")
    casos, desde = [], 0
    while True:
        r = ejecutor_http.ejecutar(
            herr, {"provider": config.importacion_tickets.proveedor,
                   "limit": 200, "offset": desde},
            tenant, variables_tenant=config.variables_tenant)
        if not isinstance(r, dict):
            break
        casos.extend(r.get("casos") or [])
        desde = r.get("next_offset")
        if not desde:
            break
    return casos


def tickets_conocidos(config, tenant: str, ids: list[str]) -> tuple[set, set]:
    """
    De estos tickets: cuales ya tienen caso, y cuales los abrio Dexter.

    Le pregunta al CRM en vez de leer sus tablas. No es una vuelta larga: el
    motor NO PUEDE leerlas -- corre con su propio usuario de base desde el
    incidente del 18/08/2026, en que compartia credencial con Django. El
    primer dry-run en produccion lo encontro asi:

        psycopg.errors.InsufficientPrivilege:
        permission denied for table solicitudes_solicitudservicio

    La salida no era un GRANT. Habria deshecho esa separacion de credenciales
    y habria atado 'nucleo/' al esquema interno de otra app: el dia que
    'solicitudes' renombre una columna, se rompe el importador y nadie sabe por
    que. Ahora Django contesta pertenencia y por dentro cambia lo que quiera.

    Devuelve (con_caso, registrados_por_dexter). La segunda UNE lo que dice el
    CRM con 'conversations.ticket_operativo', que si es del dominio del motor.
    Las dos fuentes hacen falta: mirar una sola es el error que ya se cometio
    en la auditoria, y clasifico como externos dos tickets nuestros.
    """
    con_caso: set = set()
    del_crm: set = set()

    herr = _herramienta(config, "consultar_tickets_conocidos")
    if herr is not None and ids:
        # En tandas: el endpoint acepta hasta 500 ids por consulta y la URL no
        # puede crecer sin limite.
        # Tandas de 150 contra un tope de servidor de 200: el margen deja
        # lugar por si algun dia los ids del proveedor son mas largos.
        for arranque in range(0, len(ids), 150):
            tanda = ids[arranque:arranque + 150]
            try:
                r = ejecutor_http.ejecutar(
                    herr, {"provider": config.importacion_tickets.proveedor,
                           "ids": ",".join(tanda)},
                    tenant, variables_tenant=config.variables_tenant)
                if isinstance(r, dict):
                    con_caso |= {str(x) for x in (r.get("con_caso") or [])}
                    del_crm |= {str(x) for x in (r.get("creados_por_dexter") or [])}
            except Exception as e:                          # noqa: BLE001
                # Es un fallo GLOBAL, no de un ticket: sin saber que ya existe
                # se crearia de nuevo todo. Que reviente aca es lo correcto.
                raise RuntimeError(
                    f"no se pudo consultar los tickets conocidos: "
                    f"{type(e).__name__}: {e}") from e

    # La otra fuente de autoria, esta si del dominio del motor.
    from nucleo.persistencia.conexion import dsn
    import psycopg

    with psycopg.connect(dsn()) as cx:
        conv = {str(f[0]).strip() for f in cx.execute(
            "select trim(ticket_operativo) from asistente.conversations "
            "where coalesce(trim(ticket_operativo),'') <> ''").fetchall()}

    print(f"[registro] tickets de Dexter: {len(conv)} en conversaciones + "
          f"{len(del_crm)} en solicitudes | con caso: {len(con_caso)}")
    return con_caso, conv | del_crm


# =============================================================================
#  APLICAR  --  la unica parte que escribe, y solo con --aplicar
# =============================================================================

def _cuerpo_de(v, config) -> dict:
    """
    Lo que se le manda al CRM por un candidato. Ni un campo mas.

    'name' lleva el asunto del proveedor tal cual: es lo que quien atiende
    reconoce en la cola, y traducirlo lo desalinearia de WispHub. La
    descripcion NO copia la del ticket -- ese campo es texto libre de un
    operador y ya se sabe que trae PII embebida (PRD 7.4); lo que se guarda es
    la referencia para ir a buscarla.
    """
    proveedor = config.importacion_tickets.proveedor
    partes = [f"Importado de {proveedor}, ticket #{v.external_ticket_id}.",
              f"Servicio {v.external_service_id}." if v.external_service_id else "",
              f"Abierto por {v.external_created_by}." if v.external_created_by else ""]
    if v.identidad_es_placeholder:
        partes.append("Cuelga del registro de instalaciones: el cliente todavia "
                      "no existe como tal.")
    # La prioridad que le puso el proveedor va COMO TEXTO, no como prioridad del
    # caso. El ticket que destapo esto decia 'Alta' y el caso nacio 'Normal':
    # el dato estaba y lo ignorabamos. Ponerlo a la vista evita que alguien lea
    # ese 'Normal' como un juicio de Dexter -- hoy no lo es, es una constante de
    # configuracion. Cuando Dexter calcule prioridad de verdad, esta linea
    # servira ademas para comparar los dos criterios.
    if v.prioridad_proveedor:
        partes.append(f"Prioridad en {proveedor}: {v.prioridad_proveedor}.")

    # Lo que escribio quien abrio el ticket, al final y separado de la
    # referencia: arriba queda lo que este sistema sabe con certeza, abajo el
    # texto libre del otro lado.
    referencia = " ".join(x for x in partes if x)
    descripcion = f"{referencia}\n\n{v.descripcion}".strip() if v.descripcion \
        else referencia

    return {
        "provider": proveedor,
        "external_ticket_id": v.external_ticket_id,
        "external_service_id": v.external_service_id,
        "external_status": v.external_status,
        "external_status_at": None,
        "external_created_by": v.external_created_by,
        "external_created_by_type": v.external_created_by_type,
        "external_fetched_at": datetime.now(timezone.utc).isoformat(),
        "assigned_to": v.responsable,
        "priority": v.prioridad or "Normal",
        # El estado que le corresponde por el que tiene alla, no un fijo.
        "status": imp.estado_inicial(v.external_status),
        "name": (v.asunto or "Ticket importado")[:64],
        "description": descripcion,
    }


def aplicar(config, tenant, veredictos) -> dict:
    """
    Crea los casos de los candidatos. Un fallo por ticket no corta el lote.

    La idempotencia NO la pone este bucle: la pone
    UNIQUE(org, provider, external_ticket_id) del otro lado. Aca se puede
    reintentar sin miedo porque el writer devuelve 'created=false' y el caso
    que ya estaba, sin tocarle nada.
    """
    herr = _herramienta(config, "importar_caso_externo")
    if herr is None:
        raise SystemExit("falta 'importar_caso_externo' en el catalogo")

    resumen = {"creados": 0, "ya_estaban": 0, "fallidos": 0, "ids": []}
    for v in veredictos:
        if v.resultado != imp.CANDIDATO:
            continue
        try:
            r = ejecutor_http.ejecutar(herr, _cuerpo_de(v, config), tenant,
                                       variables_tenant=config.variables_tenant)
            if isinstance(r, dict) and r.get("created"):
                resumen["creados"] += 1
            else:
                resumen["ya_estaban"] += 1
            resumen["ids"].append(v.external_ticket_id)
        except Exception as e:                              # noqa: BLE001
            resumen["fallidos"] += 1
            print(f"    [fallo] ticket {v.external_ticket_id}: "
                  f"{type(e).__name__}: {e}")
    return resumen


def aplicar_reconciliacion(config, tenant, cambios) -> dict:
    """Persiste los external_* de los casos ya conocidos. Nunca el estado."""
    herr = _herramienta(config, "reconciliar_caso_externo")
    if herr is None:
        raise SystemExit("falta 'reconciliar_caso_externo' en el catalogo")

    # 'sin_cambios' es, en la practica, siempre 0: toda fila que se escribe
    # refresca 'external_fetched_at', asi que el endpoint la cuenta como
    # actualizada aunque el proveedor haya contestado exactamente lo mismo.
    # Se conserva porque distingue "el endpoint dijo que no toco nada" de un
    # fallo, pero el numero que informa cuantos casos cambiaron ALGO es
    # 'con_diferencia' (ver Cambio.hay_diferencia), no este.
    resumen = {"actualizados": 0, "sin_cambios": 0, "fallidos": 0}
    for c in cambios:
        cuerpo = {k: v for k, v in c.despues.items() if v is not None}
        cuerpo["id_caso"] = c.caso_id
        try:
            r = ejecutor_http.ejecutar(herr, cuerpo, tenant,
                                       variables_tenant=config.variables_tenant)
            if isinstance(r, dict) and r.get("actualizados"):
                resumen["actualizados"] += 1
            else:
                resumen["sin_cambios"] += 1
        except Exception as e:                              # noqa: BLE001
            resumen["fallidos"] += 1
            print(f"    [fallo] caso {c.caso_id}: {type(e).__name__}: {e}")
    return resumen

# =============================================================================
#  EL CICLO COMPLETO  --  lo que corre el reloj, y tambien el CLI
# =============================================================================

def sincronizar_respuestas(config, tenant, cambios) -> dict:
    """
    Manda el hilo de cada ticket al caso que le corresponde.

    Ni una llamada al proveedor: las respuestas ya vinieron en el mismo payload
    que 'reconciliar' leyo para saber el estado. Lo unico que sale de aca son
    escrituras al CRM, y solo por los casos que TIENEN hilo.

    El endpoint hace upsert por huella, asi que repetir la misma pasada cada
    hora no duplica nada y aca no hace falta llevar la cuenta de que se mando
    antes. Un fallo por caso no corta el lote: el hilo del siguiente no tiene
    por que perderse porque uno no se pudo escribir.
    """
    herr = _herramienta(config, "sincronizar_respuestas_externas")
    resumen = {"hilos": 0, "respuestas": 0, "nuevas": 0, "fallidos": 0}
    if herr is None:
        # Sin la herramienta en el catalogo no se sincroniza, y se dice. No es
        # un error del barrido: es una config a la que le falta una pieza.
        resumen["error"] = "falta 'sincronizar_respuestas_externas' en el catalogo"
        return resumen

    proveedor = config.importacion_tickets.proveedor
    for c in cambios:
        if not c.respuestas or not c.caso_id:
            continue
        resumen["hilos"] += 1
        resumen["respuestas"] += len(c.respuestas)
        try:
            r = ejecutor_http.ejecutar(
                herr, {"id_caso": c.caso_id, "provider": proveedor,
                       "respuestas": c.respuestas},
                tenant, variables_tenant=config.variables_tenant)
            if isinstance(r, dict):
                resumen["nuevas"] += int(r.get("nuevas") or 0)
        except Exception as e:                              # noqa: BLE001
            resumen["fallidos"] += 1
            print(f"    [hilo] caso {c.caso_id}: {type(e).__name__}: {e}")
    return resumen


def barrido(config, tenant: str, *, aplicar_cambios: bool = False) -> dict:
    """
    Una pasada entera del subsistema de importacion:

        B. descubrir tickets nuevos y crear sus casos
        C. reconciliar los casos que ya existen

    (La A -- cerrar conversaciones vencidas -- no es de aca: la corre el reloj
    antes de llamar a esto, y es de otro dominio.)

    UNA SOLA COMPUERTA PARA LAS DOS
    -------------------------------
    Quien decide si esto corre es 'imp.debe_correr(cada_horas)', del lado del
    reloj. O sea que 'cada_horas = 0' apaga el subsistema ENTERO: ni se importa
    ni se reconcilia. Es deliberado y es la unica semantica que se puede
    explicar en una frase -- "cada_horas manda sobre importacion_tickets".
    Separarlo en dos frecuencias daria un estado raro de sostener ("no importa
    nada pero sigue hablando con el proveedor todas las horas") y un segundo
    interruptor que alguien tendria que recordar. Si algun dia hace falta
    refrescar sin importar, eso es una clave nueva y explicita en la config, no
    una excepcion escondida aca.

    SIN CHECKPOINT, a proposito. La ventana movil es la red de recuperacion:
    cada pasada mira los ultimos 'ventana_dias' completos, asi que lo que no se
    pudo hacer en un ciclo se vuelve a intentar en el siguiente sin que nadie
    tenga que acordarse de donde quedo. Un ciclo que falla entero no deja nada
    desincronizado porque no habia nada que avanzar.

    DOS CLASES DE FALLO, Y SE TRATAN DISTINTO
    -----------------------------------------
    Global -- no se pudo listar, la credencial no sirve, la config es
    invalida: no hay lote que procesar, se devuelve el error y se sale. No es
    grave: dentro de una hora se vuelve a mirar la misma ventana.

    Por ticket -- un caso que no se pudo persistir: se anota y se sigue con
    los demas. Que uno falle no es motivo para no importar los otros veinte, y
    el que fallo reaparece en la proxima pasada mientras los ya creados se
    cortan solos contra la unicidad.
    """
    conf = config.importacion_tickets
    if not conf.proveedor:
        return {"tenant": tenant, "error_global":
                "'proveedor' no esta declarado en importacion_tickets"}
    desde, hasta = imp.ventana(conf)
    # Contadores SEPARADOS. Importar y reconciliar son dos trabajos distintos
    # sobre datos distintos -- uno crea casos que no existian, el otro refresca
    # los que ya estan -- y sumarlos en un solo 'fallidos' hace ilegible el
    # unico numero que alguien mira cuando algo anda mal.
    resumen = {
        "tenant": tenant, "ventana": [desde, hasta], "error_global": "",
        "importacion": {"inspeccionados": 0, "candidatos": 0,
                        "creados": 0, "ya_estaban": 0, "fallidos": 0},
        "reconciliacion": {"alcanzados": 0, "con_diferencia": 0,
                           "actualizados": 0, "sin_cambios": 0,
                           "fallidos": 0, "errores_lectura": 0,
                           "respuestas": {}},
    }

    # -----------------------------------------------------------------------
    #  B. DESCUBRIMIENTO E IMPORTACION  --  entera dentro de un try
    # -----------------------------------------------------------------------
    # Todo el paso B va aislado, no solo el listado. Antes 'aplicar' quedaba
    # fuera del try y una excepcion suya salia de esta funcion: la
    # reconciliacion no llegaba a correr. Que no se pueda importar no es
    # motivo para dejar de refrescar los casos que YA existen -- son dos
    # trabajos sobre datos distintos.
    registro: set = set()
    try:
        areas = persistencia.areas_de_colaboradores(tenant)
        tickets = listar_tickets(config, tenant, desde, hasta)
        ids = [str(t.get("id_ticket")) for t in tickets if t.get("id_ticket")]
        conocidos, registro = tickets_conocidos(config, tenant, ids)
        _importar(config, tenant, tickets, conocidos, registro, areas, conf,
                  resumen, aplicar_cambios)
    except Exception as e:                                  # noqa: BLE001
        resumen["error_global"] = f"{type(e).__name__}: {e}"
        print(f"[importacion] el descubrimiento de '{tenant}' fallo: "
              f"{type(e).__name__}: {e}")

    _reconciliar(config, tenant, conf, registro, resumen, aplicar_cambios)
    return resumen


def _importar(config, tenant, tickets, conocidos, registro, areas, conf,
              resumen, aplicar_cambios) -> None:
    """El paso B. Escribe sus numeros en resumen['importacion']."""
    veredictos = imp.descubrir(
        config, tickets,
        conocidos=conocidos,
        registrados_por_dexter=registro,
        areas_por_persona=areas,
        cuenta_api=conf.cuenta_api,
        servicio_placeholder=(config.variables_tenant or {}).get(
            "WISPHUB_ID_SERVICIO_INSTALACIONES", ""),
        resolver_servicio=resolver_servicios(config, tenant))

    resumen["importacion"]["inspeccionados"] = len(veredictos)
    resumen["importacion"]["candidatos"] = sum(
        1 for v in veredictos if v.resultado == imp.CANDIDATO)

    if aplicar_cambios and resumen["importacion"]["candidatos"]:
        creado = aplicar(config, tenant, veredictos)
        creado.pop("ids", None)
        resumen["importacion"].update(creado)


def _reconciliar(config, tenant, conf, registro, resumen, aplicar_cambios) -> None:
    """
    El paso C: refrescar lo que el proveedor dice de los casos que ya existen.

    Va DESPUES de importar y en su propio try/except, y las dos cosas importan:

      despues   los casos recien creados SI entran a esta misma
                reconciliacion: 'casos_de_este_proveedor' se consulta despues
                de importar, asi que los ve. Medido el 10/09/2026 -- 34
                alcanzados antes de importar dos, 36 despues. Cuesta un GET
                por caso nuevo y a cambio estrenan 'external_status_at' sin
                esperar una hora. (Este comentario decia lo contrario y era
                falso: el orden de las llamadas manda, no la intencion.)

      aislada   que la reconciliacion falle NO puede deshacer ni ensuciar lo ya
                importado. Los casos creados estan creados; esto solo refresca
                columnas 'external_*'. El fallo se anota y la proxima pasada
                vuelve a intentar -- no hay checkpoint que quede a medias.

    'Case.status' no aparece en ningun lado de este camino: lo que el
    proveedor dice vive en 'external_status'. La ausencia es el invariante
    entero de la fase, y ademas el endpoint la impone (CAMPOS_RECONCILIACION
    en cases/importacion_views.py) por si alguien la olvidara aca.
    """
    try:
        casos = casos_de_este_proveedor(config, tenant)
        cambios = imp.reconciliar(
            config, casos,
            leer_ticket=lambda t: leer_ticket(config, tenant, t),
            cuenta_api=conf.cuenta_api,
            # Del mismo 'tickets_conocidos' que uso el descubrimiento. Alcanza
            # porque 'clasificar_creador_persistente' no degrada un caso que
            # YA tiene 'dexter' guardado: la evidencia vive en la fila, no en
            # esta lista.
            registrados_por_dexter=registro)
        rec = resumen["reconciliacion"]
        rec["alcanzados"] = len(cambios)
        rec["errores_lectura"] = sum(1 for c in cambios if c.error)
        rec["con_diferencia"] = sum(1 for c in cambios if c.hay_diferencia)
        if aplicar_cambios and cambios:
            rec.update(aplicar_reconciliacion(config, tenant, cambios))
            rec["respuestas"] = sincronizar_respuestas(config, tenant, cambios)
        else:
            rec["respuestas"] = {
                "hilos": sum(1 for c in cambios if c.respuestas),
                "respuestas": sum(len(c.respuestas) for c in cambios),
                "nuevas": 0, "seco": True}
    except Exception as e:                                  # noqa: BLE001
        resumen["reconciliacion"]["error"] = f"{type(e).__name__}: {e}"
        print(f"[importacion] la reconciliacion de '{tenant}' fallo: "
              f"{type(e).__name__}: {e}")
