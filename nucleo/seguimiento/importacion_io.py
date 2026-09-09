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
#  EL CICLO COMPLETO  --  lo que corre el reloj, y tambien el CLI
# =============================================================================

def barrido(config, tenant: str, *, aplicar_cambios: bool = False) -> dict:
    """
    Una pasada entera: descubrir, y opcionalmente crear los casos.

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
    resumen = {"tenant": tenant, "ventana": [desde, hasta], "error_global": "",
               "inspeccionados": 0, "candidatos": 0,
               "creados": 0, "ya_estaban": 0, "fallidos": 0}

    try:
        areas = persistencia.areas_de_colaboradores(tenant)
        tickets = listar_tickets(config, tenant, desde, hasta)
        ids = [str(t.get("id_ticket")) for t in tickets if t.get("id_ticket")]
        conocidos, registro = tickets_conocidos(config, tenant, ids)
    except Exception as e:                                  # noqa: BLE001
        resumen["error_global"] = f"{type(e).__name__}: {e}"
        return resumen

    veredictos = imp.descubrir(
        config, tickets,
        conocidos=conocidos,
        registrados_por_dexter=registro,
        areas_por_persona=areas,
        cuenta_api=conf.cuenta_api,
        servicio_placeholder=(config.variables_tenant or {}).get(
            "WISPHUB_ID_SERVICIO_INSTALACIONES", ""),
        resolver_servicio=resolver_servicios(config, tenant))

    resumen["inspeccionados"] = len(veredictos)
    resumen["candidatos"] = sum(1 for v in veredictos if v.resultado == imp.CANDIDATO)

    if aplicar_cambios and resumen["candidatos"]:
        resumen.update(aplicar(config, tenant, veredictos))
        resumen.pop("ids", None)
    return resumen
