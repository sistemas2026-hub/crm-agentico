# -*- coding: utf-8 -*-
"""Las visitas anteriores a este mismo servicio.

LA PREGUNTA QUE CONTESTA, Y CUANTO CUESTA HOY
---------------------------------------------
El tecnico toca el timbre y el cliente le dice «ya llame tres veces». Hoy no
tiene con que contestar: la ficha le da el numero de ticket y nada mas, y el
propio comentario del codigo admite que ese numero «es lo que permite buscar el
historial» -- buscarlo EN OTRO LADO, o sea llamar al NOC.

Esa es la llamada mas frecuente de la lista que armo el tecnico, y el dato ya
estaba en la base: son ordenes del mismo abonado. Nadie se lo mostraba.

COMO SE SABE QUE DOS ORDENES SON DEL MISMO SERVICIO
---------------------------------------------------
Por el **identificador del abonado en el sistema del ISP**
(`cliente_id_abonado`, o `contexto['servicio']` cuando el despacho lo dejo ahi).
Es lo unico estable: el nombre del cliente se escribe distinto cada vez
--«Beatriz Pinzon», «BEATRIZ PINZON», «B. Pinzon»--, la direccion tambien, y el
telefono cambia de dueño.

**Si no hay identificador, NO se adivina.** Agrupar por nombre o por direccion
devolveria visitas de otra persona, y el tecnico decidiria sobre eso: le diria al
cliente «ya le cambiamos la ONT dos veces» cuando fue al vecino. Una respuesta
equivocada es peor que ninguna, porque la otra la contesta el NOC.

POR QUE TRES Y NO TODAS
-----------------------
Tres entran en la pantalla sin hacer scroll y cubren lo que el tecnico necesita
saber: si esto ya paso, que se hizo, y si ya se cambio el equipo. Un historial
largo es una pantalla que nadie lee parado en una puerta.

LO QUE NO LLEVA
---------------
Ni nombre, ni direccion, ni telefono, ni documento. **Son del mismo servicio que
el tecnico ya tiene abierto en la ficha**: repetirlos no agrega nada y los
multiplica por tres en una pantalla que se sincroniza al telefono. Va lo que
permite ACTUAR: cuando, que tipo de trabajo, como termino, que material se uso y
si se cambio el equipo.
"""

from __future__ import annotations

CUANTAS = 3

#: Como se vio cada visita, en palabras de quien esta en la puerta. Un estado
#: interno (`completada_campo`, `cerrada`) no le dice nada al tecnico; lo que
#: quiere saber es si ese trabajo resolvio o volvio.
COMO_TERMINO = {
    "cerrada": "resuelto",
    "completada_campo": "resuelto",
    "cancelada": "cancelado",
    "bloqueada": "quedo trabado",
}


def id_de_servicio(orden) -> str:
    """El identificador del abonado en el ISP, o cadena vacia.

    Mismo criterio que `lazo_isp._id_servicio_de`, y a proposito: si dos partes
    del sistema decidieran distinto cual es el servicio de una orden, una de las
    dos estaria mostrando o escribiendo sobre el cliente equivocado.
    """
    if orden is None:
        return ""
    directo = (getattr(orden, "cliente_id_abonado", "") or "").strip()
    if directo:
        return directo
    contexto = getattr(orden, "contexto", None) or {}
    return str(contexto.get("servicio") or "").strip()


def visitas_anteriores(orden, cuantas: int = CUANTAS) -> list[dict]:
    """Las ultimas visitas al mismo servicio, sin incluir esta.

    Devuelve lista vacia --y no un error-- cuando no hay identificador o cuando
    es la primera visita. Las dos cosas son normales y la pantalla las dice
    distinto; aca no se inventa ninguna.
    """
    from campo.models import OrdenTrabajo

    servicio = id_de_servicio(orden)
    if not servicio:
        return []

    hermanas = (
        OrdenTrabajo.objects.filter(org=orden.org, cliente_id_abonado=servicio)
        .exclude(pk=orden.pk)
        # Las que todavia no pasaron no son historial: una orden programada para
        # el jueves no dice nada de lo que ya se hizo.
        .exclude(estado_operativo__in=[OrdenTrabajo.ASIGNADA, OrdenTrabajo.EN_CAMINO])
        .select_related("tipo_trabajo_version__work_type")
        .prefetch_related("asignaciones__profile__user", "movimientos_material__material")
        .order_by("-created_at")[:cuantas]
    )

    return [_resumen_de(o) for o in hermanas]


def _resumen_de(orden) -> dict:
    """Una visita, en lo que le sirve a quien esta parado en la puerta."""
    return {
        "id": str(orden.id),
        "numero": orden.numero,
        "tipo": _nombre_del_tipo(orden),
        # La fecha en que SE HIZO, no en que se creo: el cliente cuenta las
        # visitas, no los tickets.
        "cuando": _cuando(orden),
        "como_termino": COMO_TERMINO.get(orden.estado_operativo, "en curso"),
        "quien": _quien(orden),
        "vuelta": orden.vuelta,
        "materiales": _materiales(orden),
        "cambio_equipo": _cambio_equipo(orden),
    }


def _nombre_del_tipo(orden) -> str:
    try:
        return orden.tipo_trabajo_version.work_type.nombre or ""
    except AttributeError:
        return ""


def _cuando(orden) -> str | None:
    fecha = orden.completada_campo_en or orden.iniciada_en or orden.created_at
    return fecha.isoformat() if fecha else None


def _quien(orden) -> str:
    """El nombre del tecnico principal.

    ES UN DATO DE UN COMPAÑERO, NO DEL CLIENTE, y por eso si va: el tecnico que
    llega necesita saber a quien preguntarle que hizo la vez pasada. Es
    exactamente lo que hoy resuelve escribiendo al grupo.
    """
    for a in orden.asignaciones.all():
        if a.es_principal and a.profile is not None:
            # El modelo de usuario de esta plataforma tiene `name`, no
            # `first_name`/`last_name`. Se comprobo contra el modelo real: la
            # version anterior leia dos campos que no existen y habria devuelto
            # el correo siempre, sin fallar.
            nombre = (getattr(a.profile.user, "name", "") or "").strip()
            if nombre:
                return nombre
            # El correo es lo ultimo: identifica a la persona para pedirle
            # contexto, que es para lo que esta.
            return getattr(a.profile.user, "email", "") or ""
    return ""


def _materiales(orden) -> list[dict]:
    """Que se consumio en esa visita.

    Solo CONSUMO: una devolucion no se gasto en la casa del cliente, y sumarla
    diria que se puso el doble de drop del que se puso.
    """
    from campo.models import MovimientoDeMaterial

    usados: dict[str, dict] = {}
    for m in orden.movimientos_material.all():
        if m.tipo != MovimientoDeMaterial.CONSUMO:
            continue
        nombre = getattr(m.material, "nombre", "") or ""
        if not nombre:
            continue
        fila = usados.setdefault(
            nombre,
            {"material": nombre, "cantidad": 0, "unidad": getattr(m.material, "unidad", "")},
        )
        # Decimal: la bobina se consume en metros con decimales. Se suma tal
        # cual y se formatea arriba; convertir a float aca perderia precision en
        # el unico lugar donde importa.
        fila["cantidad"] = fila["cantidad"] + m.cantidad
    return [
        {**f, "cantidad": _cantidad(f["cantidad"])}
        for f in sorted(usados.values(), key=lambda x: x["material"])
    ]


def _cantidad(valor) -> str:
    """El numero sin ceros de relleno.

    POR QUE NO ALCANZA CON `str()`
    ------------------------------
    PostgreSQL devuelve el `Decimal` con la escala de la columna: 43 metros
    salen como `43.000`. Y en Colombia el punto es separador de MILES, asi que
    «43.000 m» se lee como cuarenta y tres mil metros de drop. El tecnico que
    mira el historial para decidir cuanto llevar en la camioneta decide con ese
    numero.

    Se vio recien al correr contra PostgreSQL: en SQLite el mismo valor sale
    `43` y la diferencia no aparece. Es la razon por la que este proyecto exige
    probar persistencia contra la base real.

    `normalize()` solo lo haria mal al reves: convierte `100` en `1E+2`.
    """
    texto = str(valor)
    if "." not in texto:
        return texto
    return texto.rstrip("0").rstrip(".") or "0"


def _cambio_equipo(orden) -> bool:
    """Si en esa visita se instalo un equipo con serial.

    Es la pregunta que el tecnico hace distinto del resto: «¿ya le cambiaron la
    ONT?». Un consumo con serie es un equipo que quedo en la casa.
    """
    from campo.models import MovimientoDeMaterial

    for m in orden.movimientos_material.all():
        if m.tipo == MovimientoDeMaterial.CONSUMO and (m.serie or "").strip():
            return True
    return False
