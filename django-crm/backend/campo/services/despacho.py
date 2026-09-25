# -*- coding: utf-8 -*-
"""
================================================================================
 DESPACHO  --  crear una orden de trabajo y ponerle una cuadrilla
================================================================================

Hasta hoy no habia forma de crear una OrdenTrabajo. 'OrdenTrabajo.objects
.create' aparecia en UN solo lugar de todo el repositorio: el comando de datos
de demostracion. Ni un endpoint, ni una señal, ni otra app. El modulo tenia un
motor de ejecucion completo -- la app del tecnico, con idempotencia,
concurrencia y checklist -- y ninguna puerta por donde entrara el trabajo.

Lo que se despachaba, se despachaba a mano desde el panel de Django, que exige
'is_staff': la bandera de superusuario. Un supervisor que solo tiene que
mandar una cuadrilla no deberia necesitar ver las facturas de la empresa para
hacerlo.
================================================================================
"""

from __future__ import annotations

import os
import re

from django.db import IntegrityError, transaction
from django.db.models import Max

from campo.models import AsignacionTrabajo, EventoTrabajo, OrdenTrabajo

# Cuantas veces se reintenta pedir un consecutivo. Con dos supervisores creando
# a la vez, uno pierde la carrera y vuelve a pedir el siguiente numero.
INTENTOS_CONSECUTIVO = 5


class ErrorDespacho(Exception):
    """Algo impide crear o asignar. El mensaje va al operador, no al log."""


def siguiente_numero(org) -> int:
    """
    El consecutivo por empresa.

    'max(numero) + 1' a secas es una carrera: dos supervisores creando al mismo
    tiempo leen el mismo maximo y el segundo choca contra
    UniqueConstraint(org, numero). Aca no se intenta evitar la carrera con un
    bloqueo -- en la primera orden de una empresa no hay ninguna fila que
    bloquear, asi que 'select_for_update' no protegeria nada -- sino que se
    deja chocar y se reintenta, que es lo unico que funciona en los dos casos.

    La restriccion de la base es la que decide; esto solo la respeta.
    """
    actual = OrdenTrabajo.objects.filter(org=org).aggregate(n=Max("numero"))["n"]
    return (actual or 0) + 1


@transaction.atomic
def crear_orden(
    *,
    org,
    profile,
    version,
    cliente: dict,
    origen_sistema: str = "manual",
    origen_tipo: str = "",
    origen_ref: str = "",
    programada_para=None,
    diagnostico_previo: dict | None = None,
    contexto: dict | None = None,
    despacho: dict | None = None,
) -> OrdenTrabajo:
    """
    Crea la orden y deja su nacimiento escrito en la bitacora.

    'org' y 'profile' salen de la sesion, NUNCA del cuerpo de la peticion: son
    los dos campos con los que se cruza un tenant si se aceptan de afuera.

    'version' es una WorkTypeVersion PUBLICADA. La plantilla se congela en la
    orden -- si manana alguien publica la v2, esta orden sigue exigiendo lo que
    exigia el dia que salio, que es lo que hace que una evidencia vieja se
    pueda auditar contra la regla que estaba vigente.

    'despacho' trae lo que decide la oficina y el tecnico no puede deducir:
    prioridad, zona, resumen, la franja prometida al cliente, cuando vence el
    compromiso, como se entra al inmueble y que requisitos de seguridad tiene
    el trabajo. Todo opcional: una orden sin nada de esto sigue siendo valida
    y se ve como se veia antes.
    """
    despacho = despacho or {}
    # La organizacion cuelga del WorkType, no de la version: la version es la
    # plantilla congelada, el tipo de trabajo es de quien la definio.
    if version.work_type.org_id != org.id:
        raise ErrorDespacho("Esa plantilla es de otra empresa.")
    from campo.models import WorkTypeVersion

    if version.estado != WorkTypeVersion.PUBLICADA:
        raise ErrorDespacho(
            f"La version {version.version} de '{version.work_type.nombre}' esta "
            f"en '{version.estado}'. Solo se despacha contra plantillas "
            f"publicadas: una borrador puede cambiar debajo del tecnico.")

    ultimo = None
    for _ in range(INTENTOS_CONSECUTIVO):
        try:
            with transaction.atomic():       # savepoint: ver el comentario abajo
                orden = OrdenTrabajo.objects.create(
                    org=org,
                    numero=siguiente_numero(org),
                    tipo_trabajo_version=version,
                    origen_sistema=origen_sistema,
                    origen_tipo=origen_tipo,
                    origen_ref=origen_ref,
                    cliente_nombre=cliente.get("nombre") or "",
                    cliente_telefono=cliente.get("telefono") or "",
                    cliente_direccion=cliente.get("direccion") or "",
                    gps_lat=cliente.get("gps_lat"),
                    gps_lng=cliente.get("gps_lng"),
                    programada_para=programada_para,
                    ventana_inicio=despacho.get("ventana_inicio"),
                    ventana_fin=despacho.get("ventana_fin"),
                    sla_vence_en=despacho.get("sla_vence_en"),
                    prioridad=despacho.get("prioridad") or OrdenTrabajo.PRIORIDAD_MEDIA,
                    zona=despacho.get("zona") or "",
                    resumen=despacho.get("resumen") or "",
                    cliente_detalle_acceso=cliente.get("detalle_acceso") or "",
                    cliente_id_abonado=cliente.get("id_abonado") or "",
                    requisitos_seguridad=despacho.get("requisitos_seguridad") or [],
                    diagnostico_previo=diagnostico_previo or {},
                    contexto=contexto or {},
                )
            break
        except IntegrityError as e:
            # SAVEPOINT anidado, no decorativo: en PostgreSQL un INSERT que
            # viola una constraint aborta la transaccion entera y toda consulta
            # posterior falla con InFailedSqlTransaction -- incluido el
            # 'siguiente_numero' del reintento. Es la misma leccion que ya
            # costo una vez en el registro de evidencias.
            ultimo = e
            if "unique_origen_externo_por_org" in str(e):
                raise ErrorDespacho(
                    "Ya existe una orden para ese origen externo. Las fuentes "
                    "automaticas admiten una sola.") from e
            continue
    else:
        raise ErrorDespacho(
            f"No se pudo asignar consecutivo despues de "
            f"{INTENTOS_CONSECUTIVO} intentos: {ultimo}")

    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="orden_creada", profile=profile,
        datos={
            "numero": orden.numero,
            "origen_sistema": origen_sistema,
            "origen_ref": origen_ref,
            "tipo_trabajo": version.work_type.codigo,
            "version_plantilla": version.version,
            "con_contexto": bool(contexto),
        },
    )
    return orden


@transaction.atomic
def asignar(orden: OrdenTrabajo, profile_tecnico, profile_actor,
            rol: str = "tecnico", motivo: str = "") -> AsignacionTrabajo:
    """
    Pone (o cambia) al responsable principal de una orden.

    El modelo ya impone un solo principal por orden
    (UniqueConstraint con condition=Q(es_principal=True)), asi que hay que
    bajar el anterior ANTES de subir el nuevo o la base rechaza el cambio. Las
    dos cosas van en la misma transaccion: una orden sin principal, aunque sea
    por un instante, es una orden que nadie ve como suya.

    Toda asignacion deja evento. Una hecha desde el panel de Django no lo
    dejaba, y entonces la bitacora tenia un hueco justo donde el trabajo
    cambiaba de manos.
    """
    if profile_tecnico.org_id != orden.org_id:
        raise ErrorDespacho("Esa persona es de otra empresa.")
    if orden.estado_operativo in (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA):
        raise ErrorDespacho(
            f"La orden esta '{orden.get_estado_operativo_display()}'. No se "
            f"reasigna un trabajo terminado.")

    anterior = orden.tecnico_principal
    if anterior is not None and anterior.id == profile_tecnico.id:
        return orden.asignaciones.get(profile=profile_tecnico)

    orden.asignaciones.filter(es_principal=True).update(es_principal=False)
    asignacion, creada = AsignacionTrabajo.objects.get_or_create(
        orden=orden, profile=profile_tecnico,
        defaults={"rol": rol, "es_principal": True},
    )
    if not creada:
        asignacion.es_principal = True
        asignacion.rol = rol
        asignacion.save(update_fields=["es_principal", "rol"])

    orden.revision += 1
    orden.save(update_fields=["revision", "updated_at"])

    EventoTrabajo.objects.create(
        org=orden.org, orden=orden,
        tipo="asignacion" if anterior is None else "reasignacion",
        profile=profile_actor,
        datos={
            "anterior": str(anterior.id) if anterior else None,
            "nuevo": str(profile_tecnico.id),
            "rol": rol,
            "motivo": motivo,
        },
    )
    return asignacion


def contexto_del_caso(case_id: str) -> dict:
    """
    Le pide al motor la ficha tecnica de un caso, para congelarla en la orden.

    Django NO habla con WispHub ni con SmartOLT -- no tiene las credenciales ni
    el catalogo de herramientas, y no deberia tenerlos. El motor si, y desde la
    Fase 3 sabe resolver el contexto de un caso importado sin necesitar
    conversacion. Se reusa ese camino en vez de abrir uno segundo.

    Es el mismo patron que 'solicitudes/entrega.py' ya usa para crear tickets.

    Nunca rompe la creacion: si el motor no responde, la orden nace sin
    snapshot y con la razon anotada. Un tecnico sin ficha puede trabajar; un
    supervisor que no puede despachar porque una API de terceros esta lenta,
    no.
    """
    import requests
    from django.utils import timezone

    # Un caso sin servicio asociado no se puede resolver ni con el motor
    # arriba: no hay contra que identificador preguntar. Se responde aca y no
    # se llama a nadie.
    #
    # Importa que sea su PROPIO motivo y no 'sin_identidad_resoluble'. Los dos
    # terminan sin ficha, pero para quien mira la orden son cosas distintas:
    # 'no se pudo consultar' se reintenta, 'no se pudo identificar' se resuelve
    # preguntandole a la persona, y este NO SE ARREGLA SOLO -- ese caso nacio
    # de una conversacion, no de un ticket, y nunca va a tener servicio.
    # Decirle al tecnico que reintente seria mandarlo a esperar algo que no va
    # a pasar. Medido: 4 de 100 casos reales estan asi (24/09/2026).
    from cases.models import Case
    caso = Case.objects.filter(pk=case_id).only(
        "external_service_id", "external_ticket_id", "provider",
        "external_status", "external_created_by").first()
    servicio = (caso.external_service_id or "").strip() if caso else ""
    if caso is not None and not servicio:
        # SIN SERVICIO NO HAY CONTEXTO TECNICO, PERO SI HAY EVALUACION.
        #
        # Un caso nacido de una conversacion no tiene servicio asociado y
        # nunca va a tenerlo. Hasta el 25/09/2026 eso cortaba aca y la orden
        # quedaba sin NADA -- y es justo el caso que SI tiene lo que el
        # asistente averiguo: son los dos lados de la misma moneda. Un caso
        # importado del ISP trae ticket y no trae conversacion; uno nacido de
        # un chat trae conversacion y no trae ticket.
        #
        # Se perdia lo mas util exactamente cuando existia.
        vacio = sin_contexto("caso_sin_servicio", motor_alcanzado=True)
        dexter = _lo_que_el_asistente_averiguo(_conversacion_del_caso(case_id))
        if dexter:
            vacio["dexter"] = dexter
        ticket = _ticket_del_proveedor(caso)
        if ticket:
            vacio["ticket"] = ticket
        return vacio

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    try:
        # 'servicio' es el identificador que el proveedor le puso al ticket, y
        # va SIEMPRE que el caso lo traiga. Sin el, un caso importado del ISP
        # --que no tiene conversacion detras-- nunca conseguia ficha: el motor
        # resolvia la identidad solo desde el chat, y ahi no hay ninguno.
        #
        # El motor ya lo contemplaba y nadie se lo mandaba. Su propio
        # 'identidad_del_contexto' lo dice: "un caso importado del sistema del
        # ISP trae su propio identificador de servicio y no tiene conversacion
        # detras; uno nacido de un chat tiene la conversacion y no el
        # identificador". Cuando estan los dos gana el del caso, y si no
        # coinciden lo informa como discrepancia en vez de elegir en silencio.
        parametros = {"tenant": tenant}
        if servicio:
            parametros["servicio"] = servicio
        r = requests.get(f"{base}/conversaciones/por-caso/{case_id}",
                         params=parametros, headers=cabeceras, timeout=30)
        r.raise_for_status()
        cuerpo = r.json() or {}
        crudo = cuerpo.get("contexto") or {}
        # La conversacion viene en la MISMA respuesta y hasta el 25/09/2026 se
        # tiraba. Ahi esta lo que el asistente ya averiguo.
        conversacion = cuerpo.get("conversacion") or {}
    except Exception as e:                                   # noqa: BLE001
        return sin_contexto(f"{type(e).__name__}", motor_alcanzado=False)

    if not crudo:
        # El motor contesto, pero no pudo resolver nada: caso sin servicio
        # asociado, o sin identidad. Es distinto de "no se pudo preguntar", y
        # la diferencia le importa a quien mire la orden despues.
        return sin_contexto("sin_identidad_resoluble", motor_alcanzado=True)

    return depurar_contexto(crudo, conversacion=conversacion, caso=caso)


def _conversacion_del_caso(case_id: str) -> dict:
    """
    Solo la conversacion que origino el caso, sin pedir contexto tecnico.

    Se usa cuando el caso NO tiene servicio: ahi no hay ficha del cliente que
    traer --el motor no sabe de quien hablar-- pero la conversacion existe y
    con ella lo que el asistente averiguo. Un fallo aca no es un error: se
    devuelve vacio y la orden queda como estaba.
    """
    # Importado ACA y no arriba, como el resto del modulo: asi se mantiene
    # importable sin la dependencia. Que el import faltara costo un rato --
    # el NameError caia en el 'except' de abajo y la funcion devolvia vacio
    # como si el motor no hubiera contestado.
    import requests

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    try:
        r = requests.get(f"{base}/conversaciones/por-caso/{case_id}",
                         params={"tenant": tenant}, headers=cabeceras,
                         timeout=30)
        r.raise_for_status()
        return (r.json() or {}).get("conversacion") or {}
    except Exception:                                        # noqa: BLE001
        return {}


def sin_contexto(motivo: str, *, motor_alcanzado: bool) -> dict:
    """
    La ausencia de ficha, dicha en voz alta.

    Un diccionario vacio es ambiguo: la app y el supervisor lo leerian como
    "cliente sin datos" en vez de "no se pudo averiguar". Son cosas
    distintas -- la primera es informacion sobre el cliente, la segunda es
    informacion sobre NOSOTROS -- y confundirlas manda a un tecnico al terreno
    creyendo que no hay nada que saber.

    'motivo' es una etiqueta corta y normalizada, no un traceback: lo que
    sirve del otro lado es poder distinguir "el motor no respondio" de "el
    caso no tiene servicio". El detalle vive en el log del proceso, que es
    donde se depura, y ademas un traceback puede arrastrar rutas o valores que
    no tienen por que quedar guardados en una orden de trabajo.
    """
    from django.utils import timezone

    return {
        "contexto_disponible": False,
        "capturado_en": timezone.now().isoformat(),
        "motivo": motivo,
        "fuente": "motor/contexto_tecnico" if motor_alcanzado else "",
        "motor_alcanzado": motor_alcanzado,
    }


# Lo que el tecnico necesita para trabajar, y nada mas.
#
# 'cedula' NO entra: es dato personal y no hace falta para cambiar una ONU. El
# nombre y la direccion si -- hay que saber a quien se visita y donde.
# Tampoco entra nada crudo del proveedor: la fila del cliente trae 54 campos,
# cuatro de ellos contraseñas y uno el GPS del domicilio.
#
# 'localidad' (24/09/2026): el motor ya la manda -- esta en su _CAMPOS_FICHA
# junto a 'ip' y 'direccion'-- y esta lista era el unico lugar donde se caia.
# No hizo falta migracion ni tocar el motor: el dato ya viajaba entero hasta
# aca. La direccion sola dice el numero de la casa; la localidad dice en que
# parte del pueblo queda, que es lo que decide si una visita entra en la ruta
# de hoy.
#
# 'direccion' y 'telefono' (24/09/2026): el comentario de arriba decia desde
# siempre que la direccion entra --"hay que saber a quien se visita y donde"--
# y NO estaba en la tupla. El codigo contradecia a su propio comentario, y se
# noto recien al mirar una orden real: el tecnico veia "Sin direccion" y "Sin
# telefono" con los dos datos cargados del otro lado.
#
# No alcanzaba con que vivan en la orden (cliente_direccion, cliente_telefono):
# esos los llena quien despacha desde el formulario, y un caso IMPORTADO del
# ISP no pasa por ningun formulario. Para esas ordenes, la ficha es la unica
# fuente -- y sin direccion el tecnico no sabe a donde ir.
CAMPOS_CLIENTE_SNAPSHOT = ("nombre", "estado", "plan", "ip", "localidad",
                           "direccion", "telefono")


def depurar_contexto(crudo: dict, *, conversacion: dict | None = None,
                     caso=None) -> dict:
    """
    Deja solo lo que se puede congelar, y le pone la hora.

    Al congelarse, una medicion deja de ser una medicion: pasa a ser un
    registro de lo que se veia en un momento. Sin la hora al lado es una
    afirmacion sobre el presente que nadie puede verificar -- la misma leccion
    que 'ACCION_CONFIRMADA' dejo escrita en el PRD.
    """
    from django.utils import timezone

    cliente = crudo.get("cliente") or {}
    equipo = crudo.get("equipo") or {}
    identidad = crudo.get("identidad") or {}

    snapshot = {
        "contexto_disponible": True,
        "capturado_en": timezone.now().isoformat(),
        "fuente": "motor/contexto_tecnico",
        "servicio": identidad.get("servicio") or "",
        "origen_identidad": identidad.get("origen") or "",
        "cliente": {k: v for k, v in cliente.items()
                    if k in CAMPOS_CLIENTE_SNAPSHOT and v},
    }
    if crudo.get("sn_onu"):
        snapshot["sn_onu"] = crudo["sn_onu"]
    if equipo:
        snapshot["equipo"] = {
            k: v for k, v in equipo.items()
            if isinstance(v, (str, int, float, bool)) and v != ""
        }
    if crudo.get("equipo_no_disponible"):
        snapshot["equipo_no_disponible"] = crudo["equipo_no_disponible"]
    if crudo.get("identidad_en_conflicto"):
        snapshot["identidad_en_conflicto"] = crudo["identidad_en_conflicto"]

    dexter = _lo_que_el_asistente_averiguo(conversacion or {})
    if dexter:
        snapshot["dexter"] = dexter
    ticket = _ticket_del_proveedor(caso)
    if ticket:
        snapshot["ticket"] = ticket
    return snapshot


#  Numeros que parecen un documento. No se baja la cedula a la orden de
#  trabajo: el tecnico necesita saber A QUIEN visita --y el nombre ya viaja en
#  la orden-- pero no su documento, y la ficha se congela y queda guardada.
#  Cuatro a doce digitos seguidos, que es la forma de una cedula colombiana y
#  tambien la de un NIT. Un numero precedido de '#' NO se toca: es un
#  ticket ('ticket #93426'), y recortarlo escondia el unico dato con
#  el que la oficina y el tecnico se refieren al caso.
_PARECE_DOCUMENTO = re.compile(r"(?<![#\d])\b\d{4,12}\b")


def _sin_documentos(texto: str) -> str:
    """El texto libre del asistente, sin numeros que parezcan un documento."""
    return _PARECE_DOCUMENTO.sub("(documento)", texto or "").strip()


def _lo_que_el_asistente_averiguo(conversacion: dict) -> dict:
    """
    Lo que Dexter ya hizo con este caso, para que no se vuelva a hacer.

    POR QUE IMPORTA. El asistente habla con el cliente antes de que exista la
    orden: verifica identidad, mide el equipo, descarta causas y deja escrito
    QUE FALTA AVERIGUAR. Todo eso vivia en asistente.conversations y no salia
    de ahi: el tecnico llegaba a la casa a preguntar lo mismo que el cliente ya
    habia contestado por WhatsApp.

    'siguiente_paso' es el mas util de los tres y es literal, no una etiqueta:
    "Confirmar con el cliente si el coaxial lo instalo la empresa o lo
    modifico el, y con eso cerrar el diagnostico de TV".

    SE LE QUITAN LOS DOCUMENTOS. 'resumen' es texto que redacta el modelo y
    trae la cedula cuando la verifico ("Mario Sabanagrande, cedula 000021",
    visto en produccion). El nombre si puede ir --ya esta en la orden--; el
    documento no: esto se congela en la orden de trabajo y viaja al telefono.
    """
    if not conversacion:
        return {}
    salida = {}
    for clave, origen in (("caso", "caso_manual"),
                          ("motivo_escalada", "motivo_escalamiento"),
                          ("etiqueta", "etiqueta")):
        valor = (conversacion.get(origen) or "").strip()
        if valor:
            salida[clave] = valor
    for clave, origen in (("resumen", "resumen"),
                          ("siguiente_paso", "escalada_siguiente_paso")):
        valor = _sin_documentos(conversacion.get(origen) or "")
        if valor:
            salida[clave] = valor
    return salida


def _ticket_del_proveedor(caso) -> dict:
    """
    El ticket del sistema del ISP, con su numero y su estado ALLA.

    Un UUID de caso no le sirve a nadie: el tecnico y la oficina hablan de
    "el 93426". Y 'external_status' es el estado EN WISPHUB, que no tiene por
    que coincidir con el del CRM -- alguien pudo cerrarlo del otro lado.
    """
    if caso is None:
        return {}
    numero = str(getattr(caso, "external_ticket_id", "") or "").strip()
    if not numero:
        return {}
    ticket = {"numero": numero}
    for clave, atributo in (("proveedor", "provider"),
                            ("estado", "external_status"),
                            ("abierto_por", "external_created_by")):
        valor = str(getattr(caso, atributo, "") or "").strip()
        if valor:
            ticket[clave] = valor
    return ticket


# ============================================================================
#  REFRESCAR LA FICHA  --  volver a capturar lo que se congelo al despachar
# ============================================================================
#
# POR QUE HACE FALTA
# ------------------
# Al crear la orden, la ficha del cliente se congela. Eso es deliberado y no se
# discute: "al congelarse, una medicion deja de ser una medicion -- pasa a ser
# un registro de lo que se veia en un momento". Por eso lleva 'capturado_en'.
#
# El problema es que hasta hoy NO habia forma de volver a capturarla. Un ticket
# se importa apenas se abre y los datos del cliente se completan mas tarde: la
# orden quedaba con esa foto para siempre y el tecnico veia "Sin direccion"
# aunque alguien hubiera cargado la direccion despues. La unica salida era un
# script contra la base.
#
# LAS TRES DECISIONES, Y SU MOTIVO
# --------------------------------
# 1. NO TOCA LAS COLUMNAS de la orden (cliente_nombre, cliente_telefono,
#    cliente_direccion). Esas las escribe quien despacha, a mano, y dicen cosas
#    que el ISP no tiene y no puede tener: "Casa porton verde, timbre roto,
#    llamar al llegar". El ISP responde "Cl. 45 #12-88", que para llegar es
#    PEOR. Un refresco que las sobrescribiera destruiria trabajo humano en cada
#    llamada. La ficha rellena el hueco cuando la columna esta vacia, y eso ya
#    lo resuelve _cliente() en serializers.py, en un solo sentido.
#
# 2. SOLO LA ULTIMA FICHA vive en 'contexto'; la anterior COMPLETA queda dentro
#    del EventoTrabajo del refresco. La bitacora es append-only y ya existe:
#    responde "que se veia cuando el tecnico fue" sin inventar una tabla ni
#    engordar la orden con un historial que casi nadie lee.
#
# 3. MANUAL, nunca automatico al abrir. Cada refresco le pega al sistema del
#    ISP, que tiene limite de tasa (SmartOLT: 1.000 llamadas/hora, confirmado
#    por cabecera). Un refresco por apertura de orden lo gastaria en visitas
#    que no lo necesitan.
#
# LA PROPIEDAD QUE MAS IMPORTA
# ----------------------------
# Un refresco que falla NO destruye la ficha que habia. Por eso se captura
# PRIMERO, se comprueba que la ficha nueva exista de verdad, y recien entonces
# se escribe. 'contexto_del_caso' nunca lanza: devuelve el dict de
# 'sin_contexto' cuando no pudo. Si se guardara ese dict, un motor caido
# borraria los datos del cliente de una orden en curso -- que es exactamente lo
# que no puede pasar.
def refrescar_contexto(orden: OrdenTrabajo, *, profile) -> dict:
    """
    Vuelve a capturar la ficha del cliente de una orden ya despachada.

    Devuelve (ok, motivo, motor_alcanzado, capturado_en). No lanza cuando el
    motor falla -- eso no es un error del refresco, es una respuesta.

    Lanza ErrorDespacho solo cuando la orden no admite el refresco: esta
    cerrada o cancelada, o no nacio de un caso.
    """
    from django.utils import timezone

    # Una orden cerrada o cancelada no se refresca: su ficha es parte del acta.
    # Cambiarla despues seria reescribir lo que se veia cuando se trabajo.
    if orden.estado_operativo in (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA):
        raise ErrorDespacho(
            "Una orden cerrada o cancelada no se refresca: su ficha es parte "
            "del acta de lo que se vio cuando se trabajo.")

    # Sin caso detras no hay a quien preguntarle. Una orden manual no tiene
    # ficha que refrescar, y decir "no se pudo" seria confundir dos cosas.
    case_id = (orden.origen_ref or "").strip()
    if orden.origen_sistema != "crm" or not case_id:
        raise ErrorDespacho(
            "Esta orden no nacio de un caso del CRM: no hay contra que "
            "identificador preguntar.")

    # PRIMERO se captura. Nada se escribe hasta tener la ficha nueva en mano.
    fresco = contexto_del_caso(case_id)
    if fresco.get("contexto_disponible") is not True:
        # No se pudo, y la ficha tecnica anterior queda EXACTAMENTE como
        # estaba. Se devuelven los tres motivos distinguibles que la app ya
        # sabe leer.
        #
        # LO QUE SI SE GUARDA, Y NO ES UNA EXCEPCION A LA REGLA DE ARRIBA.
        # 'caso_sin_servicio' es el caso de un ticket nacido de una
        # conversacion: no hay cliente que resolver --y nunca lo va a haber--
        # pero SI esta lo que el asistente averiguo y el ticket del ISP. Son
        # los dos lados de la misma moneda: un caso importado trae ticket y no
        # trae conversacion; uno nacido de un chat trae conversacion y no trae
        # ticket. Hasta el 25/09/2026 se perdia lo mas util exactamente cuando
        # existia.
        #
        # Se AGREGAN al contexto que ya habia, no lo reemplazan: la ficha
        # tecnica sigue intacta, que es lo que esta funcion promete.
        extra = {k: fresco[k] for k in ("dexter", "ticket") if fresco.get(k)}
        if extra:
            with transaction.atomic():
                fila = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
                contexto = dict(fila.contexto or {})
                contexto.update(extra)
                fila.contexto = contexto
                fila.save(update_fields=["contexto"])
            orden.refresh_from_db(fields=["contexto"])
        return {
            "ok": False,
            "motivo": fresco.get("motivo") or "",
            "motor_alcanzado": fresco.get("motor_alcanzado", False),
        }

    anterior = dict(orden.contexto or {})

    with transaction.atomic():
        fresca = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
        # Se revalida el estado DENTRO de la transaccion: entre la captura y la
        # escritura pasaron los segundos que tarda el motor, y en ese rato
        # alguien pudo cerrar la orden.
        if fresca.estado_operativo in (OrdenTrabajo.CERRADA,
                                       OrdenTrabajo.CANCELADA):
            raise ErrorDespacho(
                "La orden se cerro mientras se consultaba la ficha: no se "
                "escribio nada.")

        fresca.contexto = fresco
        fresca.revision += 1
        fresca.save(update_fields=["contexto", "revision", "updated_at"])

        EventoTrabajo.objects.create(
            org=fresca.org,
            orden=fresca,
            tipo="contexto_refrescado",
            profile=profile,
            datos={
                # La ficha ANTERIOR entera. Es lo que responde "que se veia
                # cuando el tecnico fue" una vez que 'contexto' ya cambio.
                "anterior": anterior,
                "capturado_en": fresco.get("capturado_en") or "",
                "fuente": fresco.get("fuente") or "",
                "revision": fresca.revision,
                "refrescado_en": timezone.now().isoformat(),
            },
        )

    orden.contexto = fresco
    orden.revision = fresca.revision
    return {
        "ok": True,
        "capturado_en": fresco.get("capturado_en") or "",
        "revision": fresca.revision,
    }
