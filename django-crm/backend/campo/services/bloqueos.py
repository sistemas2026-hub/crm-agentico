# -*- coding: utf-8 -*-
"""Detener un trabajo, y volver a ponerlo en marcha.

LOS DOS HECHOS QUE NACEN DE UNA SOLA PANTALLA
---------------------------------------------
Cuando alguien aprieta "bloquear" pasan dos cosas distintas:

    1. una persona REPORTA que no puede seguir  ->  `bloqueo_campo` en la bitacora
    2. el sistema DETIENE el trabajo            ->  transicion a `bloqueada`

Se escriben juntas y en una sola transaccion, pero no son lo mismo, y el codigo
las mantiene separadas a proposito: un reporte humano no se convierte por si solo
en un estado de maquina. De hecho la segunda es OPCIONAL -- se puede anotar un
bloqueo sin detener nada, cuando algo demora pero el tecnico sigue haciendo lo que
puede, y entonces la ficha dice exactamente eso: "bloqueo reportado, el estado
operativo no cambio".

`bloqueada` Y `requiere_noc` NO SON LO MISMO
-------------------------------------------
    estado_operativo = "bloqueada"   ->  el trabajo esta detenido
    requiere_noc = True              ->  hace falta que alguien del NOC haga algo

Un trabajo detenido esperando al cliente, esperando material o porque llueve no lo
destraba el NOC. Si los dos conceptos fueran uno, esa bandeja mostraria trabajos
que nadie de esa mesa puede resolver, y a la semana la dejarian de mirar. Ver el
encabezado de `campo/bloqueos.py`.

EL RETORNO NO SE ADIVINA
------------------------
La fila del bloqueo guarda `estado_operativo_anterior` al abrirse. Resolver
PROPONE ese estado y la maquina de `transiciones.py` sigue siendo la que dice si
el retorno es legal. Nunca `orden.estado_operativo = lo_que_sea`.

Por eso tampoco hay un `bloqueada -> en_sitio` fijo: puede haber un bloqueo antes
de llegar --no hay acceso a la calle-- y volver a `en_sitio` inventaria que el
tecnico llego cuando no habia llegado.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from campo.bloqueos import BloqueoDeTrabajo
from campo.models import EventoTrabajo, OrdenTrabajo
from campo.services import seguimiento_campo as seguimiento
from campo.services.transiciones import (
    SE_PUEDE_BLOQUEAR_DESDE,
    TransicionInvalidaError,
    aplicar_transicion,
)


class BloqueoInvalido(Exception):
    """Lo que se niega antes de detener --o destrabar-- un trabajo."""

    def __init__(self, mensaje, errores=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.errores = errores or {}


#: El tipo con el que la resolucion queda en la bitacora. No es un momento de
#: seguimiento como los cuatro --nadie "reporta una resolucion" desde la calle--:
#: es un hecho del sistema, y por eso vive aca y no en `seguimiento_campo.TIPOS`.
BLOQUEO_RESUELTO = "bloqueo_resuelto"


def bloqueo_abierto_de(orden):
    """El bloqueo vivo de esta orden, o `None`. Hay a lo sumo uno (constraint)."""
    return (
        BloqueoDeTrabajo.objects.filter(
            org=orden.org, orden=orden, resuelto_en__isnull=True
        )
        .select_related("abierto_por__user")
        .first()
    )


@transaction.atomic
def bloquear(
    orden,
    *,
    profile,
    respuestas: dict | None = None,
    requiere_noc: bool = False,
    detener: bool = True,
    capturado_en_dispositivo=None,
):
    """Reporta un bloqueo y, si se pide, detiene el trabajo.

    Devuelve `(bloqueo, evento, se_detuvo)`.

    `requiere_noc` llega como argumento y NO se deduce de las respuestas: el
    campo del formulario lo nombra cada empresa como quiere, y un filtro que
    depende de ese nombre deja de funcionar con la segunda.
    """
    if bloqueo_abierto_de(orden) is not None:
        raise BloqueoInvalido(
            "Esta orden ya tiene un bloqueo abierto. Resolvelo antes de abrir otro: "
            "con dos bloqueos vivos no se sabría a qué estado volver."
        )

    estado_previo = orden.estado_operativo
    if detener and estado_previo not in SE_PUEDE_BLOQUEAR_DESDE:
        raise BloqueoInvalido(
            f"Un trabajo en '{estado_previo}' no se puede detener: ya pasó la etapa "
            "de ejecución. Si hay algo que reclamar, va por corrección o por un "
            "caso, no por un bloqueo."
        )

    # 1. EL REPORTE. Valida contra el esquema del tipo de trabajo y guarda su
    #    propio snapshot: es el hecho que dijo una persona.
    try:
        evento = seguimiento.registrar(
            orden,
            profile=profile,
            momento=seguimiento.BLOQUEO,
            respuestas=respuestas or {},
            capturado_en_dispositivo=capturado_en_dispositivo,
        )
    except seguimiento.SeguimientoInvalido as e:
        # Se traduce para que quien llama no tenga que conocer las dos
        # excepciones, y se conservan los errores POR CAMPO.
        raise BloqueoInvalido(e.mensaje, errores=e.errores) from e

    respuestas_limpias = (evento.datos or {}).get("respuestas") or {}

    bloqueo = BloqueoDeTrabajo.objects.create(
        org=orden.org,
        orden=orden,
        evento_reporte=evento,
        abierto_por=profile,
        abierto_en=timezone.now(),
        # Se guarda ACA, al abrir. No se deduce despues.
        estado_operativo_anterior=estado_previo,
        detuvo_el_trabajo=bool(detener),
        requiere_noc=bool(requiere_noc),
        categoria=str(respuestas_limpias.get("categoria") or "")[:64],
        motivo=str(respuestas_limpias.get("motivo") or ""),
        necesita=str(
            respuestas_limpias.get("necesita_de_noc")
            or respuestas_limpias.get("necesita")
            or ""
        ),
    )

    # 2. LA TRANSICION, si corresponde. Por la maquina, que es la que niega.
    se_detuvo = False
    if detener:
        aplicar_transicion(
            orden=orden,
            nuevo_estado=OrdenTrabajo.BLOQUEADA,
            tipo_evento="bloqueo_detuvo_el_trabajo",
            profile=profile,
            metadatos={
                "bloqueo_id": str(bloqueo.id),
                "requiere_noc": bool(requiere_noc),
                "estado_operativo_anterior": estado_previo,
            },
        )
        se_detuvo = True

    return bloqueo, evento, se_detuvo


@transaction.atomic
def resolver(
    bloqueo,
    *,
    profile,
    que_se_hizo: str,
    resuelto_por_rol: str = "",
    volver_a: str | None = None,
):
    """Destraba el trabajo y deja escrito quien, cuando y que hizo.

    Devuelve `(bloqueo, evento, volvio_a)`.

    `volver_a` por defecto es el estado que el bloqueo guardo al abrirse. Se puede
    pedir otro --el mundo cambio mientras estaba trabado-- y la maquina de
    transiciones lo valida igual: esta funcion PROPONE, no decide.
    """
    if bloqueo.resuelto_en is not None:
        raise BloqueoInvalido(
            "Este bloqueo ya estaba resuelto. Si el trabajo se volvió a trabar, se "
            "abre un bloqueo nuevo: así queda que fueron dos veces y no una."
        )

    que_se_hizo = (que_se_hizo or "").strip()
    if not que_se_hizo:
        raise BloqueoInvalido(
            "Decí qué se hizo para destrabarlo.",
            errores={"que_se_hizo": "Este campo es requerido."},
        )

    if resuelto_por_rol:
        validos = {q[0] for q in BloqueoDeTrabajo.QUIENES}
        if resuelto_por_rol not in validos:
            raise BloqueoInvalido(
                f"'{resuelto_por_rol}' no es un rol conocido. Los que hay: "
                + ", ".join(sorted(validos))
                + "."
            )

    orden = bloqueo.orden
    destino = volver_a or bloqueo.estado_operativo_anterior or OrdenTrabajo.ASIGNADA

    ahora = timezone.now()
    bloqueo.resuelto_en = ahora
    bloqueo.resuelto_por = profile
    bloqueo.resuelto_por_rol = resuelto_por_rol or ""
    bloqueo.que_se_hizo = que_se_hizo

    # La transicion PRIMERO, porque es la que puede negarse. Si el retorno no es
    # legal, no queremos un bloqueo marcado como resuelto y una orden que sigue
    # detenida: el rollback de la transaccion lo evita, pero el orden deja el
    # motivo del fallo en el lugar correcto.
    volvio_a = orden.estado_operativo
    if bloqueo.detuvo_el_trabajo and orden.estado_operativo == OrdenTrabajo.BLOQUEADA:
        try:
            aplicar_transicion(
                orden=orden,
                nuevo_estado=destino,
                tipo_evento="bloqueo_libero_el_trabajo",
                profile=profile,
                metadatos={"bloqueo_id": str(bloqueo.id), "volvio_a": destino},
            )
        except TransicionInvalidaError as e:
            raise BloqueoInvalido(
                f"No se puede devolver la orden a '{destino}': {e}"
            ) from e
        volvio_a = destino

    bloqueo.volvio_a = volvio_a
    bloqueo.save(
        update_fields=[
            "resuelto_en",
            "resuelto_por",
            "resuelto_por_rol",
            "que_se_hizo",
            "volvio_a",
            "updated_at",
        ]
    )

    # El hecho, en la bitacora. Con los minutos, que es lo que despues explica por
    # que la intervencion tardo -- sin que esos minutos se lean como "el tecnico no
    # reporto".
    evento = EventoTrabajo.objects.create(
        org=orden.org,
        orden=orden,
        tipo=BLOQUEO_RESUELTO,
        profile=profile,
        datos={
            "bloqueo_id": str(bloqueo.id),
            "que_se_hizo": que_se_hizo,
            "resuelto_por_rol": resuelto_por_rol or "",
            "requeria_noc": bool(bloqueo.requiere_noc),
            "volvio_a": volvio_a,
            "minutos_detenido": bloqueo.minutos_detenido,
            "abierto_en": bloqueo.abierto_en.isoformat(),
        },
    )
    return bloqueo, evento, volvio_a


def serializar(bloqueo) -> dict:
    """Un bloqueo, como lo leen la ficha y la bandeja."""
    return {
        "id": str(bloqueo.id),
        "orden_id": str(bloqueo.orden_id),
        "abierto": bloqueo.esta_abierto,
        "abierto_en": bloqueo.abierto_en.isoformat() if bloqueo.abierto_en else None,
        "abierto_por": _nombre(bloqueo.abierto_por),
        # Las dos cosas que no son lo mismo, cada una con su nombre.
        "detuvo_el_trabajo": bloqueo.detuvo_el_trabajo,
        "requiere_noc": bloqueo.requiere_noc,
        "estado_operativo_anterior": bloqueo.estado_operativo_anterior,
        "categoria": bloqueo.categoria,
        "motivo": bloqueo.motivo,
        "necesita": bloqueo.necesita,
        "minutos_detenido": bloqueo.minutos_detenido,
        "resuelto_en": bloqueo.resuelto_en.isoformat() if bloqueo.resuelto_en else None,
        "resuelto_por": _nombre(bloqueo.resuelto_por),
        "resuelto_por_rol": bloqueo.resuelto_por_rol,
        "que_se_hizo": bloqueo.que_se_hizo,
        "volvio_a": bloqueo.volvio_a,
    }


def abiertos_de(org, *, solo_noc: bool = False) -> list[dict]:
    """Los bloqueos vivos de la empresa. Para los filtros de la bandeja.

    `solo_noc` es lo que hace que «Bloqueados» y «Requiere NOC» puedan ser dos
    filtros distintos y los dos digan la verdad.
    """
    qs = BloqueoDeTrabajo.objects.filter(org=org, resuelto_en__isnull=True)
    if solo_noc:
        qs = qs.filter(requiere_noc=True)
    return [
        serializar(b)
        for b in qs.select_related("abierto_por__user", "orden").order_by("abierto_en")
    ]


def _nombre(profile) -> str | None:
    if profile is None:
        return None
    user = getattr(profile, "user", None)
    return (getattr(user, "name", "") or getattr(user, "email", "") or "").strip() or None
