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
) -> OrdenTrabajo:
    """
    Crea la orden y deja su nacimiento escrito en la bitacora.

    'org' y 'profile' salen de la sesion, NUNCA del cuerpo de la peticion: son
    los dos campos con los que se cruza un tenant si se aceptan de afuera.

    'version' es una WorkTypeVersion PUBLICADA. La plantilla se congela en la
    orden -- si manana alguien publica la v2, esta orden sigue exigiendo lo que
    exigia el dia que salio, que es lo que hace que una evidencia vieja se
    pueda auditar contra la regla que estaba vigente.
    """
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

    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    tenant = os.environ.get("MOTOR_TENANT", "") or "rapilink"
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    try:
        r = requests.get(f"{base}/conversaciones/por-caso/{case_id}",
                         params={"tenant": tenant}, headers=cabeceras, timeout=30)
        r.raise_for_status()
        crudo = (r.json() or {}).get("contexto") or {}
    except Exception as e:                                   # noqa: BLE001
        return sin_contexto(f"{type(e).__name__}", motor_alcanzado=False)

    if not crudo:
        # El motor contesto, pero no pudo resolver nada: caso sin servicio
        # asociado, o sin identidad. Es distinto de "no se pudo preguntar", y
        # la diferencia le importa a quien mire la orden despues.
        return sin_contexto("sin_identidad_resoluble", motor_alcanzado=True)

    return depurar_contexto(crudo)


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
CAMPOS_CLIENTE_SNAPSHOT = ("nombre", "estado", "plan", "ip")


def depurar_contexto(crudo: dict) -> dict:
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
    return snapshot
