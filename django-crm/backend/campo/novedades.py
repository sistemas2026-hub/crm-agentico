# -*- coding: utf-8 -*-
"""
================================================================================
 LA NOVEDAD DE LA CUADRILLA  --  30/10/2026
================================================================================

SPEC/objetivos/novedad-de-cuadrilla.md. El usuario: «¿cómo el técnico reporta
alguna novedad sin tener que escribir en el ticket, por ejemplo se pinchó la
llanta, y esas novedades?».

Lo que habia era BLOQUEAR una orden (`campo/bloqueos.py`), y un bloqueo es de
una orden. Una llanta pinchada es de la cuadrilla y del resto del dia: frena
todas sus ordenes, y la oficina no se enteraba hasta que se vencian.

QUE ES
------
El tecnico avisa QUE pasa (opciones de un toque, y un texto corto si quiere) y
CUANTO le afecta (30 minutos, 1 hora, el resto del dia). No se calcula ni se
adivina: lo dice el que esta en la calle.

QUE HACE
--------
  - Programacion la muestra en la tarjeta de la cuadrilla, y a quienes
    gestionan les llega un aviso (el despachador unico, `common.notifications`).
  - Mientras esta VIGENTE, la regla de los 30 minutos no acusa a sus ordenes
    (`services/salud_seguimiento.py`): igual que un bloqueo esperando al NOC.
  - «El resto del dia»: sus cuentas cuentan como FUERA HOY en la publicacion
    del Supervisor (`fuera_por_novedad`, sumado a las ausencias en
    `operaciones/publicacion_del_reparto.py`). Su jornada no recibe trabajo y
    sus ordenes SIN EMPEZAR pasan a otras cuadrillas. Lo empezado no se mueve.

VIGENTE: no resuelta y, si es corta, dentro de su tiempo. Las cortas vencen
solas; la del resto del dia, hasta que la cierra el tecnico («Ya seguí») o la
oficina.

EL TEXTO LIBRE no va a ningun log (CLAUDE.md §5): se guarda y se muestra a la
oficina de la empresa, nada mas.

NO ES `operaciones.NovedadOperativa`, y se miro antes de crear esta: aquella es
la CAUSA de una reprogramacion de una orden o actividad (Planes semanales), la
anota la oficina al reprogramar, tiene una lista de causas cerrada a proposito
(M05-A) y un ciclo de gestion. Esta la avisa el TECNICO, es de la CUADRILLA y
no de una orden, y vence sola.
================================================================================
"""

from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile

logger = logging.getLogger(__name__)

#: Que paso. Claves estables; el texto es de la pantalla.
LLANTA = "llanta"
VEHICULO = "vehiculo"
ACCIDENTE = "accidente"
CLIMA = "clima"
SIN_MATERIAL = "sin_material"
OTRA = "otra"
TIPOS = (
    (LLANTA, "Se pinchó una llanta"),
    (VEHICULO, "El vehículo se varó"),
    (ACCIDENTE, "Accidente"),
    (CLIMA, "Lluvia o clima"),
    (SIN_MATERIAL, "Se quedó sin material"),
    (OTRA, "Otra novedad"),
)

#: Cuanto afecta. Lo dice el tecnico.
MEDIA_HORA = "media_hora"
UNA_HORA = "una_hora"
RESTO_DEL_DIA = "resto_del_dia"
AFECTA = (
    (MEDIA_HORA, "30 minutos"),
    (UNA_HORA, "1 hora"),
    (RESTO_DEL_DIA, "El resto del día"),
)
DURACION = {MEDIA_HORA: dt.timedelta(minutes=30), UNA_HORA: dt.timedelta(hours=1)}

MAX_TEXTO = 280


class NovedadDeCuadrilla(BaseModel):
    """Una novedad que avisa un tecnico desde la calle. Ver el encabezado."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="novedades_de_cuadrilla")
    #: La jornada con que salia ese dia, si salia con alguna.
    jornada = models.ForeignKey("campo.JornadaDeCuadrilla", on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="novedades")
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT,
                                related_name="novedades_de_cuadrilla_avisadas")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    afecta = models.CharField(max_length=20, choices=AFECTA)
    texto = models.CharField(max_length=MAX_TEXTO, blank=True, default="")
    #: El dia de la EMPRESA en que se aviso: lo que se mira en Programacion.
    fecha = models.DateField()
    #: Cuando la aviso el telefono (puede llegar mas tarde, sin señal) y
    #: cuando la vio el servidor (`created_at`). Las cortas vencen contando
    #: desde la del telefono: es cuando paso.
    avisada_en = models.DateTimeField()
    resuelta_en = models.DateTimeField(null=True, blank=True)
    resuelta_por = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True,
                                     blank=True,
                                     related_name="novedades_de_cuadrilla_resueltas")
    #: La cabecera `Idempotency-Key` del telefono: un reintento sin señal no
    #: deja dos novedades donde hubo una.
    clave = models.CharField(max_length=100)

    class Meta:
        db_table = "campo_novedad_de_cuadrilla"
        ordering = ["-avisada_en"]
        constraints = [
            models.UniqueConstraint(fields=["org", "clave"],
                                    name="unique_novedad_por_clave"),
        ]
        indexes = [models.Index(fields=["org", "fecha"])]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.fecha}"

    def vigente(self, ahora=None) -> bool:
        """No resuelta y, si es corta, dentro de su tiempo."""
        if self.resuelta_en is not None:
            return False
        duracion = DURACION.get(self.afecta)
        if duracion is None:
            return True
        return (ahora or timezone.now()) < self.avisada_en + duracion

    def hasta(self):
        """Hasta cuando afecta, o None si es el resto del dia."""
        duracion = DURACION.get(self.afecta)
        return self.avisada_en + duracion if duracion else None


class NovedadInvalida(Exception):
    """Lo que el tecnico mando no es una novedad."""


def avisar(org, profile, *, tipo: str, afecta: str, texto: str = "",
           avisada_en=None, clave: str, ahora=None) -> tuple:
    """(novedad, creada). Idempotente por `clave`. Avisa a la oficina SOLO al
    crearla: un reintento no repite el aviso."""
    from campo import dia_publicado
    from campo import reparto as R

    if tipo not in dict(TIPOS):
        raise NovedadInvalida("No es una novedad que se conozca.")
    if afecta not in dict(AFECTA):
        raise NovedadInvalida("Falta cuánto te afecta: 30 minutos, 1 hora o el resto del día.")
    texto = " ".join(str(texto or "").split())
    if len(texto) > MAX_TEXTO:
        raise NovedadInvalida(f"El texto pasa de {MAX_TEXTO} letras.")
    clave = str(clave or "").strip()
    if not clave or len(clave) > 100:
        raise NovedadInvalida("Falta la clave del aviso (Idempotency-Key).")

    ahora = ahora or timezone.now()
    #  La hora del telefono, pero nunca en el futuro: un reloj adelantado
    #  alargaria la novedad.
    avisada_en = min(avisada_en or ahora, ahora)
    hoy = ahora.astimezone(R._zona_de(org)).date()

    ya = NovedadDeCuadrilla.objects.filter(org=org, clave=clave).first()
    if ya is not None:
        return ya, False
    #  La jornada con la MISMA regla que «Tu labor para hoy» (`mi-dia/`).
    jornada = dia_publicado.jornada_de_la_persona(org, profile, hoy)
    try:
        with transaction.atomic():
            n = NovedadDeCuadrilla.objects.create(
                org=org, jornada=jornada, profile=profile, tipo=tipo, afecta=afecta,
                texto=texto, fecha=hoy, avisada_en=avisada_en, clave=clave)
    except IntegrityError:
        #  Otro reintento la creo entre el filter y el create.
        return NovedadDeCuadrilla.objects.get(org=org, clave=clave), False
    _avisar_a_la_oficina(n)
    return n, True


def _avisar_a_la_oficina(n) -> None:
    """La campanita de quienes gestionan. Nunca rompe el aviso del tecnico."""
    from campo.permissions import ROLES_GESTION
    from common import notifications

    try:
        cuadrilla = n.jornada.cuadrilla.nombre if n.jornada_id else ""
        for p in (Profile.objects.filter(org=n.org, is_active=True)
                  .filter(role__in=ROLES_GESTION)):
            notifications.create(
                p, "novedad_de_cuadrilla", actor=n.profile, entity=n,
                entity_name=(cuadrilla or n.get_tipo_display())[:255],
                link="/supervisor-noc/programacion",
                data={"tipo": n.tipo, "afecta": n.afecta, "cuadrilla": cuadrilla})
    except Exception as e:                                       # noqa: BLE001
        #  POR TIPO, nunca el texto: lo escribio el tecnico.
        logger.warning("Novedad de cuadrilla: no se pudo avisar a la oficina (%s)",
                       type(e).__name__)


def resolver(org, novedad_id, profile, *, puede_cualquiera: bool, ahora=None):
    """La cierra: «Ya seguí». La cierra quien la aviso, o quien gestiona.
    Cerrar una ya cerrada no cambia nada."""
    n = NovedadDeCuadrilla.objects.filter(org=org, id=novedad_id).first()
    if n is None or (not puede_cualquiera and n.profile_id != profile.id):
        return None
    if n.resuelta_en is None:
        n.resuelta_en = ahora or timezone.now()
        n.resuelta_por = profile
        n.save(update_fields=["resuelta_en", "resuelta_por", "updated_at"])
    return n


def vigentes_de(org, fecha, ahora=None) -> list:
    """Las vigentes de ese dia de la empresa."""
    ahora = ahora or timezone.now()
    return [n for n in (NovedadDeCuadrilla.objects
                        .filter(org=org, fecha=fecha, resuelta_en__isnull=True)
                        .select_related("jornada__cuadrilla", "profile__user"))
            if n.vigente(ahora)]


def fuera_por_novedad(org, fecha, ahora=None) -> set:
    """Las cuentas que hoy cuentan como FUERA por una novedad del resto del
    dia: quien la aviso y quienes reciben las ordenes de su jornada. Se suma a
    las ausencias en la publicacion del Supervisor."""
    from campo.cuadrillas import destinatarios

    fuera = set()
    for n in vigentes_de(org, fecha, ahora):
        if n.afecta != RESTO_DEL_DIA:
            continue
        fuera.add(n.profile_id)
        if n.jornada is not None:
            fuera |= {r["profile"].id for r in destinatarios(n.jornada)["reciben"]}
    return fuera


def pausa_de(org, profile_ids, ahora=None):
    """La novedad vigente de alguna de esas cuentas, o None. La lee la regla de
    los 30 minutos: mientras dure, no acusa."""
    from campo import reparto as R
    from campo.cuadrillas import destinatarios

    ahora = ahora or timezone.now()
    hoy = ahora.astimezone(R._zona_de(org)).date()
    ids = set(profile_ids)
    if not ids:
        return None
    for n in vigentes_de(org, hoy, ahora):
        afectados = {n.profile_id}
        if n.jornada is not None:
            afectados |= {r["profile"].id for r in destinatarios(n.jornada)["reciben"]}
        if afectados & ids:
            return n
    return None


def a_json(n, ahora=None) -> dict:
    """Como la ven la app y Programacion. Sin datos de cliente: no los tiene.
    Las horas, en la de la EMPRESA: Programacion las lee como «10:12»."""
    from campo import reparto as R

    zona = R._zona_de(n.org)
    hasta = n.hasta()
    return {
        "id": str(n.id),
        "tipo": n.tipo,
        "tipo_texto": n.get_tipo_display(),
        "afecta": n.afecta,
        "afecta_texto": n.get_afecta_display(),
        "texto": n.texto,
        "avisada_en": n.avisada_en.astimezone(zona).isoformat(),
        "hasta": hasta.astimezone(zona).isoformat() if hasta else None,
        "vigente": n.vigente(ahora),
        "resuelta_en": (n.resuelta_en.astimezone(zona).isoformat()
                        if n.resuelta_en else None),
        "cuadrilla": (n.jornada.cuadrilla.nombre
                      if n.jornada_id and n.jornada is not None else ""),
        "quien": getattr(getattr(n.profile, "user", None), "name", "") or "",
    }
