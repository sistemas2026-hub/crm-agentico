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

    #  EL LOCK  --  agregado en M03-F-B
    #  --------------------------------
    #  Sin el, dos asignaciones simultaneas sobre la misma OT se resolvian con
    #  un IntegrityError del indice unico parcial: la base salvaba el estado
    #  final, pero el segundo solicitante recibia un 500 en vez de un conflicto
    #  explicado. Se bloquea la OT, el mismo objeto que bloquea
    #  'programar_orden', asi que no se introduce un orden de locks nuevo.
    fresca = OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)
    if fresca.estado_operativo in (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA):
        raise ErrorDespacho(
            f"La orden esta '{fresca.get_estado_operativo_display()}'. No se "
            f"reasigna un trabajo terminado.")

    anterior = fresca.tecnico_principal
    if anterior is not None and anterior.id == profile_tecnico.id:
        return fresca.asignaciones.get(profile=profile_tecnico)

    fresca.asignaciones.filter(es_principal=True).update(es_principal=False)
    asignacion, creada = AsignacionTrabajo.objects.get_or_create(
        orden=fresca, profile=profile_tecnico,
        defaults={"rol": rol, "es_principal": True},
    )
    if not creada:
        asignacion.es_principal = True
        asignacion.rol = rol
        asignacion.save(update_fields=["es_principal", "rol"])

    fresca.revision += 1
    fresca.save(update_fields=["revision", "updated_at"])

    EventoTrabajo.objects.create(
        org=fresca.org, orden=fresca,
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
    caso = Case.objects.filter(pk=case_id).only("external_service_id").first()
    servicio = (caso.external_service_id or "").strip() if caso else ""
    if caso is not None and not servicio:
        return sin_contexto("caso_sin_servicio", motor_alcanzado=True)

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


# ==============================================================================
#  CUADRILLA AD-HOC POR OT  --  M03-F-B
# ==============================================================================
#
#  La cuadrilla NO es una entidad: es el conjunto de AsignacionTrabajo de una
#  OT, agrupado por 'orden_id'. Eso ya lo declaraba operaciones/models.py:19 y
#  M03-F-A.1 lo confirmo midiendo. Aqui no se crea ningun modelo nuevo.
#
#  LAS TRES REGLAS QUE MANDAN (contrato M03-F-A.2 / A.3)
#  ----------------------------------------------------
#  1. 0 integrantes es valido. Con >= 1 integrante hay EXACTAMENTE un principal.
#  2. 'es_principal' es la fuente de verdad. 'rol' es descriptivo y no decide
#     nada -- por eso ninguna de estas funciones lo toca para "ascender" a
#     nadie a 'tecnico_lider'.
#  3. Retirar al principal exige el sucesor EN EL MISMO ACTO. Nunca dos pasos:
#     M03-F-A.3 midio que el estado a medio camino es LEGAL y por tanto
#     invisible -- ninguna comprobacion existente puede distinguirlo de una
#     cuadrilla correcta. Lo que no se puede detectar, hay que hacerlo
#     imposible.
#
#  EL LOCK
#  -------
#  Todas bloquean la OT y solo la OT. El invariante "exactamente un principal"
#  es del CONJUNTO, no de una fila: bloquear filas sueltas no impide que llegue
#  una fila nueva. Es ademas el mismo objeto que bloquea 'programar_orden', asi
#  que no se introduce un orden de locks distinto al de M03 -- y como ninguna
#  de estas operaciones toca el plan, jamas se toma un segundo lock.


class RequiereSucesor(ErrorDespacho):
    """
    Se intento retirar al principal sin decir quien queda a cargo.

    No es un error de validacion: es un conflicto de estado. Va con 409, igual
    que el resto de conflictos reales del modulo.
    """


class ConflictoDeCuadrilla(ErrorDespacho):
    """La foto que traia el solicitante ya no corresponde a la realidad."""


ESTADOS_TERMINALES = (OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA)


def _exigir_operable(orden: OrdenTrabajo) -> None:
    if orden.estado_operativo in ESTADOS_TERMINALES:
        raise ErrorDespacho(
            f"La orden #{orden.numero} esta "
            f"'{orden.get_estado_operativo_display()}'. No se cambia la "
            f"cuadrilla de un trabajo terminado.")


def _bloquear(orden: OrdenTrabajo) -> OrdenTrabajo:
    """
    Relee la OT bajo lock. Lo que decide es la fila bloqueada, nunca la copia
    en memoria -- mismo criterio que 'programar_orden' (M03-B).
    """
    return OrdenTrabajo.objects.select_for_update().get(pk=orden.pk)


def _foto_cuadrilla(orden: OrdenTrabajo) -> list[dict]:
    """
    La composicion completa, para que el evento permita RECONSTRUIR la
    transicion y no solo enterarse de que hubo una.
    """
    return [
        {"profile": str(a.profile_id), "rol": a.rol,
         "es_principal": a.es_principal}
        for a in orden.asignaciones.all().order_by("asignado_en")
    ]


def _integrante(orden: OrdenTrabajo, profile) -> AsignacionTrabajo:
    fila = orden.asignaciones.filter(profile=profile).first()
    if fila is None:
        raise ErrorDespacho("Esa persona no esta asignada a esta orden.")
    return fila


def _misma_empresa(orden: OrdenTrabajo, profile) -> None:
    if profile.org_id != orden.org_id:
        raise ErrorDespacho("Esa persona es de otra empresa.")


def _evento(orden, tipo, actor, antes, **datos):
    return EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo=tipo, profile=actor,
        datos={"antes": antes, "despues": _foto_cuadrilla(orden), **datos},
    )


@transaction.atomic
def agregar_integrante(orden: OrdenTrabajo, profile, actor,
                       rol: str = "tecnico",
                       motivo: str = "") -> AsignacionTrabajo:
    """
    Suma a alguien a la cuadrilla SIN tocar al principal.

    'es_principal=False' se fija AQUI y no es parametro: mover el principal es
    otra operacion, con otro nombre y otro evento. M03-F-A.1 midio que la unica
    via que existia hacia lo contrario -- agregar a un ayudante le robaba la
    principalia al lider -- y esa es la conducta que este modulo separa en dos
    actos distintos.

    Exige que YA haya alguien: una cuadrilla no empieza por el ayudante. La
    primera persona entra por 'asignar', que la deja como principal.
    """
    _misma_empresa(orden, profile)
    fresca = _bloquear(orden)
    _exigir_operable(fresca)

    if not fresca.asignaciones.exists():
        raise ErrorDespacho(
            f"La orden #{fresca.numero} no tiene a nadie asignado. La primera "
            f"persona se asigna con 'asignar', y queda como principal.")
    if fresca.asignaciones.filter(profile=profile).exists():
        raise ErrorDespacho("Esa persona ya esta en la cuadrilla.")

    antes = _foto_cuadrilla(fresca)
    asignacion = AsignacionTrabajo.objects.create(
        orden=fresca, profile=profile, rol=rol, es_principal=False)

    fresca.revision += 1
    fresca.save(update_fields=["revision", "updated_at"])

    _evento(fresca, "integrante_agregado", actor, antes,
            integrante=str(profile.id), rol=rol, motivo=motivo)
    return asignacion


@transaction.atomic
def cambiar_principal(orden: OrdenTrabajo, nuevo_principal, actor,
                      motivo: str = "") -> tuple[AsignacionTrabajo, bool]:
    """
    Traslada la responsabilidad entre DOS personas que ya estan en la cuadrilla.

    Devuelve (asignacion, cambio). 'cambio' en False significa que ya era el
    principal: es un no-op y responde 200 'sin_cambios', el mismo contrato que
    M03-B1 fijo para la secuenciacion. Un no-op no escribe, no audita y no
    exige motivo, porque no hay nada que justificar.

    NO toca 'rol'. 'principal' y 'tecnico_lider' no son sinonimos (F-3): quien
    pasa a responder por la OT no cambia de oficio por hacerlo.
    """
    _misma_empresa(orden, nuevo_principal)
    fresca = _bloquear(orden)
    _exigir_operable(fresca)

    entrante = _integrante(fresca, nuevo_principal)
    if entrante.es_principal:
        return entrante, False

    antes = _foto_cuadrilla(fresca)
    anterior = fresca.tecnico_principal

    #  Bajar ANTES de subir: el indice unico parcial no admite dos principales
    #  ni por un instante. Las dos escrituras van en la misma transaccion, asi
    #  que el hueco de cero principales no existe fuera de ella.
    fresca.asignaciones.filter(es_principal=True).update(es_principal=False)
    fresca.asignaciones.filter(profile=nuevo_principal).update(es_principal=True)

    fresca.revision += 1
    fresca.save(update_fields=["revision", "updated_at"])

    _evento(fresca, "cambio_principal", actor, antes,
            principal_anterior=str(anterior.id) if anterior else None,
            principal_nuevo=str(nuevo_principal.id), motivo=motivo)
    entrante.refresh_from_db()
    return entrante, True


@transaction.atomic
def retirar_integrante(orden: OrdenTrabajo, profile, actor,
                       nuevo_principal=None, motivo: str = "") -> dict:
    """
    Saca a alguien de la cuadrilla. Si es el principal, el sucesor viaja en la
    MISMA llamada (decision A de M03-F-A.3).

    Por que no se permite en dos pasos: M03-F-A.3 midio el estado intermedio
    --cambiar el principal y no llegar a retirar-- y resulto ser LEGAL. Cumple
    el invariante, pasa 'revisar_coherencia' y no dispara H-05. O sea que un
    retiro a medias es indistinguible de una cuadrilla correcta, y nadie puede
    detectarlo despues. La unica defensa posible es que no pueda ocurrir.

    Sale el ULTIMO integrante: no hace falta sucesor. La OT queda en 0
    asignaciones, que es un estado valido y deliberado (F-2), no un accidente.
    """
    fresca = _bloquear(orden)
    _exigir_operable(fresca)

    saliente = _integrante(fresca, profile)
    quedan_otros = fresca.asignaciones.exclude(profile=profile).exists()
    principal_actual = fresca.tecnico_principal

    if not saliente.es_principal:
        #  Sale un auxiliar: el principal no se mueve. Un sucesor aqui solo se
        #  acepta si coincide con quien YA es principal -- si nombra a otro, la
        #  foto del solicitante quedo vieja y hay que decirselo, no adivinar.
        if (nuevo_principal is not None and principal_actual is not None
                and nuevo_principal.id != principal_actual.id):
            raise ConflictoDeCuadrilla(
                "Esa persona ya no es la principal de la orden. Vuelva a "
                "consultar la cuadrilla antes de retirar a alguien.")
        antes = _foto_cuadrilla(fresca)
        rol_que_tenia = saliente.rol
        saliente.delete()
        fresca.revision += 1
        fresca.save(update_fields=["revision", "updated_at"])
        _evento(fresca, "integrante_retirado", actor, antes,
                integrante_retirado=str(profile.id),
                rol_que_tenia=rol_que_tenia, motivo=motivo)
        return {"retirado": profile, "principal": principal_actual,
                "cambio_principal": False}

    #  ---------------- sale el PRINCIPAL ----------------
    if not quedan_otros:
        antes = _foto_cuadrilla(fresca)
        rol_que_tenia = saliente.rol
        saliente.delete()
        fresca.revision += 1
        fresca.save(update_fields=["revision", "updated_at"])
        _evento(fresca, "integrante_retirado", actor, antes,
                integrante_retirado=str(profile.id),
                rol_que_tenia=rol_que_tenia, era_principal=True,
                orden_queda_sin_asignar=True, motivo=motivo)
        return {"retirado": profile, "principal": None,
                "cambio_principal": False}

    if nuevo_principal is None:
        raise RequiereSucesor(
            f"Esa persona es la principal de la orden #{fresca.numero} y "
            f"quedan otros integrantes. Indique quien queda a cargo en esta "
            f"misma operacion.")

    _misma_empresa(fresca, nuevo_principal)
    if nuevo_principal.id == profile.id:
        raise ErrorDespacho(
            "El sucesor no puede ser la misma persona que se retira.")
    _integrante(fresca, nuevo_principal)      # tiene que estar en ESTA orden

    antes = _foto_cuadrilla(fresca)
    rol_que_tenia = saliente.rol

    #  Primero se va el principal, despues sube el sucesor: al reves habria dos
    #  principales a la vez y el indice unico parcial lo rechazaria.
    saliente.delete()
    fresca.asignaciones.filter(profile=nuevo_principal).update(es_principal=True)

    fresca.revision += 1
    fresca.save(update_fields=["revision", "updated_at"])

    _evento(fresca, "principal_retirado", actor, antes,
            integrante_retirado=str(profile.id), rol_que_tenia=rol_que_tenia,
            principal_anterior=str(profile.id),
            principal_nuevo=str(nuevo_principal.id), motivo=motivo)
    return {"retirado": profile, "principal": nuevo_principal,
            "cambio_principal": True}


@transaction.atomic
def desasignar(orden: OrdenTrabajo, actor, motivo: str = "") -> int:
    """
    Deja la OT sin nadie. 0 integrantes es un estado valido (F-2): una orden
    puede quedar esperando a que alguien la tome.

    NO es un atajo para sacar al principal conservando al resto -- eso es
    'retirar_integrante' con sucesor. Aqui se van TODOS, asi que no puede
    producir el estado "quedan integrantes y no hay principal".
    """
    fresca = _bloquear(orden)
    _exigir_operable(fresca)

    antes = _foto_cuadrilla(fresca)
    cuantos = fresca.asignaciones.count()
    if cuantos == 0:
        return 0

    fresca.asignaciones.all().delete()
    fresca.revision += 1
    fresca.save(update_fields=["revision", "updated_at"])
    _evento(fresca, "cuadrilla_desasignada", actor, antes,
            integrantes_retirados=cuantos, motivo=motivo)
    return cuantos
