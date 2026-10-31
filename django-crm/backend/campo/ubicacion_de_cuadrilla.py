# -*- coding: utf-8 -*-
"""
================================================================================
 DONDE ESTA CADA CUADRILLA  --  31/10/2026
================================================================================
Pedido del usuario: *"queremos adicionarle un mapa donde uno pueda ver la
posicion actual de cada tecnico"*. Esto es el lado del servidor: donde se
guarda una posicion, quien puede escribirla y quien puede leerla.

LA DECISION QUE MANDA SOBRE EL MODELO: SOLO LA ULTIMA POSICION
---------------------------------------------------------------
Una fila por persona, que se pisa. **La tabla no guarda el recorrido.**

Dicho con el matiz que corresponde (revisor de PII, 31/10/2026): lo que se
afirma es sobre la tabla viva y sobre lo que la API puede entregar --nadie
puede pedir "por donde anduvo"--. Los respaldos de la base son otra cosa: si
tienen WAL o volcados diarios, la secuencia es recuperable dentro de su
ventana de retencion. Eso se resuelve en la politica de respaldo, no aca, pero
no se dice "no se guarda el recorrido" a secas.

No es una simplificacion para despues: es la decision. Un rastro permanente de
por donde anduvo un empleado es un dato mucho mas pesado --y mucho mas dificil
de justificar-- que saber donde esta ahora, y la operacion no necesita el
rastro: necesita saber a quien mandar al proximo caso. Si algun dia hace falta
el recorrido, se decide explicitamente y se mide por que.

LA GARANTIA VA EN CODIGO, NO EN LA APP (CLAUDE.md §4)
------------------------------------------------------
Se decidio que el tecnico comparte ubicacion **solo durante su jornada**. Si
esa regla viviera unicamente en el telefono, un error de la aplicacion --o una
version vieja-- seguiria mandando posiciones a las once de la noche y el
servidor las guardaria sin chistar.

Por eso `registrar()` **rechaza** dos cosas, y falla CERRADO en las dos:

  1. la posicion de quien no tiene `JornadaDeCuadrilla` de hoy;
  2. la que llega **fuera del horario de las cuadrillas** de la empresa
     (`operaciones.capacidad.jornada_de(..., solo_de_cuadrillas=True)`), con
     un margen declarado.

El punto 2 lo encontro el revisor de PII el 31/10/2026, y es la diferencia
entre lo que este archivo decia y lo que el codigo hacia: con solo mirar la
FECHA, el telefono de un tecnico con jornada de hoy seguia reportando a las
22:00 --su casa-- y el servidor lo guardaba y lo servia como `fresca`. Era
exactamente el contraejemplo que este encabezado pone como lo que no debe
pasar. Mirar la fecha no es mirar la jornada.

**Sin horario de cuadrillas cargado no se guarda nada** (`SIN_HORARIO`): la
empresa que no declaro cuando trabaja su gente no declaro cuando NO, y ante
eso se rechaza. Es la misma decision que ya tomo el Supervisor para armar y
despachar (21/10/2026): sin horario de cuadrillas, no corre.

La aplicacion tambien tiene que dejar de mandar, pero eso es comodidad; la
garantia es esta.

Y POR ESO LA LECTURA DICE LA EDAD
----------------------------------
*"Nunca mostrar una ubicacion antigua como si fuera actual"* (el pedido, punto
6). `de_las_cuadrillas()` devuelve los minutos desde que el telefono la midio,
y quien dibuja decide: lo viejo se muestra como viejo, no como ahora.

LO QUE ESTO NO PRUEBA
---------------------
Que el tecnico este ahi. Prueba que **su telefono** reporto esa coordenada. Un
telefono sin señal deja de reportar sin que pase nada raro, y eso no es una
acusacion: es ausencia de dato, y asi se nombra.
================================================================================
"""
from __future__ import annotations

import logging

from django.db import models
from django.utils import timezone

from common.models import BaseModel, Org, Profile

logger = logging.getLogger(__name__)

#: Mas vieja que esto, una posicion ya no se muestra en el mapa: a media hora
#: de distancia no dice donde esta la cuadrilla, dice donde estuvo.
MINUTOS_QUE_SIRVEN = 30

#: Precision peor que esto es el barrio, no la casa. Se guarda igual --saber
#: que esta en la zona sirve-- pero quien dibuja puede decirlo.
METROS_DE_PRECISION_POBRE = 100

#: Cuanto se acepta ANTES de abrir y DESPUES de cerrar. Un turno que se estira
#: es normal, y un tecnico que desaparece del mapa justo cuando se le hizo
#: tarde es peor que inutil. Una hora alcanza para eso y no alcanza para la
#: noche. Es constante y no configuracion a proposito: lo que varia por
#: empresa es el HORARIO (ya configurable), no cuanto se tolera pasarse; el
#: dia que una empresa necesite otro margen, se vuelve un campo del horario.
MINUTOS_DE_MARGEN = 60


class PosicionDeTecnico(BaseModel):
    """La ULTIMA posicion conocida del telefono de alguien. Una fila por
    persona: la anterior se pisa. Ver el encabezado."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="posiciones_de_tecnico")
    profile = models.OneToOneField(Profile, on_delete=models.CASCADE,
                                   related_name="posicion_de_tecnico")

    latitud = models.FloatField()
    longitud = models.FloatField()
    #: Radio de error en metros que informa el telefono. Nulo si no lo dijo.
    precision_m = models.IntegerField(null=True, blank=True)
    #: Bateria 0-100. Nulo si el telefono no lo entrego: un tecnico al 8% es un
    #: tecnico que va a dejar de reportar, y conviene saberlo antes.
    bateria = models.IntegerField(null=True, blank=True)

    #: Cuando el TELEFONO la midio (puede venir atrasada si no habia señal) y
    #: cuando llego al servidor. No son lo mismo y la diferencia importa.
    medida_en = models.DateTimeField()
    recibida_en = models.DateTimeField(default=timezone.now)

    #: Con que jornada la mando. Queda para saber de que dia es sin adivinar.
    jornada = models.ForeignKey("campo.JornadaDeCuadrilla",
                                on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="posiciones")

    class Meta:
        db_table = "campo_posicion_tecnico"
        indexes = [models.Index(fields=["org", "medida_en"], name="idx_posicion_org")]

    def __str__(self) -> str:                                    # pragma: no cover
        return f"{self.profile_id} @ {self.medida_en}"

    def minutos(self, ahora=None) -> int:
        return int(((ahora or timezone.now()) - self.medida_en).total_seconds() // 60)


class FueraDeLaJornada(Exception):
    """No se guarda su posicion. `motivo` dice cual de los tres casos es, para
    que la aplicacion pueda dejar de mandar sabiendo por que."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


#: No sale hoy.
SIN_JORNADA = "sin_jornada"
#: Sale hoy, pero esta llegando fuera del horario de las cuadrillas.
FUERA_DE_HORARIO = "fuera_de_horario"
#: La empresa no declaro cuando trabajan sus cuadrillas. Falla CERRADO.
SIN_HORARIO = "sin_horario"


def zona_operativa(org):
    """EL RELOJ CON QUE SE MIDE TODO ACA: el del horario de las cuadrillas si
    la empresa lo cargo; si no, el de la empresa.

    POR QUE NO ALCANZA `reparto._zona_de` (31/10/2026). `Org.timezone` trae
    `"UTC"` por omision, y con eso, a las 22:00 de Bogota el servidor ya esta
    en MAÑANA: el dia que se usa para buscar la jornada y el dia con que se
    mide el horario salian distintos, y la misma posicion se rechazaba por un
    motivo equivocado. El calendario de cuadrillas SI declara su zona, y es
    la que describe cuando trabaja la gente."""
    import datetime as dt
    from zoneinfo import ZoneInfo

    from campo import reparto as R
    from campo.horario_de_cuadrillas import calendario_de_cuadrillas

    cal = None
    try:
        cal = calendario_de_cuadrillas(org)
    except Exception:                                            # noqa: BLE001
        pass
    nombre = (getattr(cal, "timezone", "") or "").strip()
    if not nombre:
        return R._zona_de(org)
    try:
        return ZoneInfo(nombre)
    except Exception:                                            # noqa: BLE001
        return dt.timezone.utc


def dentro_del_horario(org, cuando) -> tuple[bool, str]:
    """`(si, motivo)`: si `cuando` cae en el horario de las cuadrillas de la
    empresa, con `MINUTOS_DE_MARGEN` de cada lado.

    La ventana sale de `operaciones.capacidad.jornada_de`, que ya lee el
    horario de las cuadrillas y **respeta la zona del calendario tal como
    esta** -- reinterpretarla cambiaria la jornada en silencio. No se duplica
    esa regla aca."""
    import datetime as dt

    from operaciones.capacidad import jornada_de

    zona = zona_operativa(org)
    local = cuando.astimezone(zona)
    j = jornada_de(org, local.date(), solo_de_cuadrillas=True)
    if not j.abierta:
        #  Cerrada hoy (feriado, domingo) o sin horario cargado: las dos
        #  terminan en lo mismo --no se guarda-- y se distinguen al reportar.
        from operaciones.capacidad import SIN_HORARIO_DE_CUADRILLAS
        return False, (SIN_HORARIO if j.motivo == SIN_HORARIO_DE_CUADRILLAS
                       else FUERA_DE_HORARIO)
    margen = dt.timedelta(minutes=MINUTOS_DE_MARGEN)
    abre = dt.datetime.combine(local.date(), j.apertura, tzinfo=zona) - margen
    cierra = dt.datetime.combine(local.date(), j.cierre, tzinfo=zona) + margen
    return (abre <= local <= cierra), FUERA_DE_HORARIO


def registrar(org, profile, *, latitud, longitud, medida_en,
              precision_m=None, bateria=None, ahora=None):
    """Guarda la ULTIMA posicion de `profile`, o levanta `FueraDeLaJornada`.

    Falla CERRADO a proposito: sin jornada de hoy no se escribe nada. Ver el
    encabezado.
    """
    from campo import reparto as R
    from campo.dia_publicado import jornada_de_la_persona

    ahora = ahora or timezone.now()
    #  EL MISMO RELOJ para el dia y para el horario: ver `zona_operativa`.
    hoy = ahora.astimezone(zona_operativa(org)).date()
    jornada = jornada_de_la_persona(org, profile, hoy)
    if jornada is None:
        raise FueraDeLaJornada(SIN_JORNADA)
    #  Y DENTRO DEL HORARIO, no solo del dia (revisor de PII, 31/10/2026).
    dentro, motivo = dentro_del_horario(org, ahora)
    if not dentro:
        raise FueraDeLaJornada(motivo)

    #  Una medicion del futuro es un reloj mal puesto: se recorta a ahora para
    #  que no quede una posicion que parece eterna (minutos negativos).
    if medida_en > ahora:
        medida_en = ahora

    fila, _ = PosicionDeTecnico.objects.update_or_create(
        profile=profile,
        defaults={"org": org, "latitud": latitud, "longitud": longitud,
                  "precision_m": precision_m, "bateria": bateria,
                  "medida_en": medida_en, "recibida_en": ahora,
                  "jornada": jornada},
    )
    return fila


#: Cuantos dias se conserva una posicion. Con la decision de guardar solo la
#: ultima, una posicion de ayer no le sirve a nadie --la pantalla ni siquiera
#: la muestra, porque `de_las_cuadrillas` pide la jornada de ESA fecha-- y
#: quedarse con ella es guardar donde estuvo un empleado sin ningun uso. Dos
#: dias por el huso y por una corrida que se saltee.
DIAS_QUE_SE_CONSERVA = 2


def purgar(org=None, *, ahora=None) -> int:
    """Borra las posiciones mas viejas que `DIAS_QUE_SE_CONSERVA`. Devuelve
    cuantas.

    POR QUE EXISTE (revisor de PII, 31/10/2026): no habia ningun borrado. La
    ultima posicion de quien renuncio en noviembre --con buena probabilidad su
    casa, al final del ultimo dia-- seguia en la tabla y en cada respaldo el
    año siguiente, y nadie la veia en el mapa, asi que nada iba a señalarla.
    `Profile.is_active = False` saca a la persona de la lectura; no borra la
    fila.

    La corre `campo.tasks.ciclo_de_la_madrugada`, que ya recorre las empresas.
    """
    import datetime as dt

    ahora = ahora or timezone.now()
    corte = ahora - dt.timedelta(days=DIAS_QUE_SE_CONSERVA)
    filas = PosicionDeTecnico.objects.filter(medida_en__lt=corte)
    if org is not None:
        filas = filas.filter(org=org)
    return filas.delete()[0]


def de_las_cuadrillas(org, fecha, *, ahora=None) -> dict:
    """`{profile_id: {...}}` con la ultima posicion de quienes salen `fecha`.

    Cada una trae `minutos` y `fresca`: quien dibuja NO tiene que calcular la
    edad ni decidir el umbral, y asi el mapa y la lista dicen lo mismo.
    """
    from campo.cuadrillas import JornadaDeCuadrilla, destinatarios

    ahora = ahora or timezone.now()
    perfiles = set()
    for j in (JornadaDeCuadrilla.objects.filter(org=org, fecha=fecha)
              .select_related("cuadrilla", "cuadrilla__lider", "lider")):
        perfiles |= {r["profile"].id for r in destinatarios(j)["reciben"]}
    if not perfiles:
        return {}

    #  SOLO LO DE ESE DIA (revisor de PII, 31/10/2026). Sin esto, pedir el
    #  mapa del 25 de octubre devolvia la posicion de ESTE minuto rotulada
    #  bajo aquella fecha: una vista que parece historial sin serlo, y la
    #  posicion en vivo servida por un camino que nadie leyo como "en vivo".
    #  Coherente con la decision de no guardar recorrido: una fecha pasada no
    #  muestra nada.
    salida = {}
    for p in PosicionDeTecnico.objects.filter(org=org, profile_id__in=perfiles,
                                              jornada__fecha=fecha):
        minutos = p.minutos(ahora)
        salida[str(p.profile_id)] = {
            "latitud": p.latitud,
            "longitud": p.longitud,
            "precision_m": p.precision_m,
            "bateria": p.bateria,
            "minutos": minutos,
            #  Lo viejo se muestra como viejo, nunca como ahora.
            "fresca": minutos <= MINUTOS_QUE_SIRVEN,
            "precision_pobre": (p.precision_m is not None
                                and p.precision_m > METROS_DE_PRECISION_POBRE),
            "medida_en": p.medida_en.isoformat(),
        }
    return salida
