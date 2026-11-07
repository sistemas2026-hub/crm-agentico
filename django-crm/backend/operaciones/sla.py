# -*- coding: utf-8 -*-
"""
================================================================================
 SLA OPERATIVO DE UNA ORDEN DE TRABAJO  --  paso M04-A
================================================================================

DERIVADO, NO ALMACENADO
-----------------------
Este modulo NO escribe nada. No agrega columnas, no crea un modelo y no guarda
un "estado SLA" en ninguna parte: lo calcula cada vez a partir de lo que ya
existe. Un estado guardado seria un dato que envejece solo -- una orden pasa de
'a tiempo' a 'vencida' sin que nadie la toque, y esa transicion no tiene evento
que la dispare. Guardarla obligaria a un proceso que la refresque, y ese
proceso seria el segundo motor de SLA que este bloque existe para no crear.

NO ES UN SEGUNDO MOTOR DE SLA
-----------------------------
El calendario laboral lo resuelve 'business_hours.calendar', el mismo que usa
'cases.Case' para sus deadlines. Aca no se reimplementa: se llama. Si algun dia
cambia la forma de contar horas habiles, cambia en un solo sitio y las dos
mitades del sistema siguen diciendo lo mismo.

DE DONDE SALE EL PLAZO
----------------------
Del 'TipoTrabajoVersion' vigente de la orden, campo
'duracion_estimada_minutos' del esquema -- la misma clave que M03-G ya usa para
calcular capacidad ('capacidad.CLAVE_DURACION'). No se inventa una duracion por
defecto: sin ese dato no hay plazo, y se dice.

EL ANCLA ES 'created_at', Y ES UNA DECISION, NO UN DESCUIDO
-----------------------------------------------------------
El plazo se cuenta desde que la orden existe, no desde 'programada_para'. Es lo
unico que hace ciertas dos reglas a la vez:

    reprogramar NO extiende el plazo
    cambiar el plan NO reinicia el plazo

Si el ancla fuera 'programada_para', mover una orden al martes le regalaria
plazo nuevo, y el indicador pasaria a medir la diligencia de quien reprograma
en vez del tiempo que el cliente lleva esperando. 'created_at' no se puede
mover: la orden se creo cuando se creo.

VENCIDA NO ES INCUMPLIMIENTO
----------------------------
Lo que este modulo contesta es una medida de tiempo, no un juicio. Una orden
vencida puede tener una causa registrada -- una ausencia, una falta de material,
un cliente que no abrio-- y eso lo dicen las novedades, no el reloj. Por eso
'estado' nunca vale "incumplida" ni "culpable": vale VENCIDA, que es un hecho
comprobable.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from operaciones.capacidad import CLAVE_DURACION

#  Estados del plazo. Son cinco, y los dos ultimos no son "errores": son
#  respuestas legitimas que significan cosas distintas entre si.
VENCIDA = "VENCIDA"
VENCE_PRONTO = "VENCE_PRONTO"
A_TIEMPO = "A_TIEMPO"
#  SIN_PLAZO: el tipo de trabajo existe y NO declara duracion. Nadie se
#  comprometio a un tiempo, asi que no hay plazo que medir. No es un cero.
SIN_PLAZO = "SIN_PLAZO"
#  NO_APLICA: la orden ya termino su recorrido. El plazo dejo de correr; decir
#  "vencida" de una orden cerrada hace tres semanas seria describir el pasado
#  como si fuera un pendiente.
NO_APLICA = "NO_APLICA"

#  Cuando ni siquiera se puede llegar al tipo de trabajo. Se distingue de
#  SIN_PLAZO a proposito: "no declara duracion" y "no se pudo leer" son
#  problemas distintos y se arreglan en lugares distintos.
DATOS_INSUFICIENTES = "DATOS_INSUFICIENTES"

#  Estados de la orden en los que el plazo ya no corre.
ESTADOS_TERMINADOS = ("cerrada", "cancelada")


#  VENTANA DE AVISO  --  proporcional al plazo, con tope
#
#  La primera version reutilizaba las 24 h que M09 usa para compromisos, y la
#  prueba de 'A_TIEMPO' lo delato: con un plazo de 2 horas, TODA orden nacia ya
#  en VENCE_PRONTO y el estado dejaba de discriminar. Un umbral fijo solo
#  funciona si todos los plazos son del mismo orden de magnitud, y no lo son:
#  aca conviven trabajos de 2 h con otros de varios dias.
#
#  20% del plazo, con tope de 24 h:
#      2 h  -> 24 min        24 h -> 4,8 h
#     10 h  ->  2 h          5 dias o mas -> 24 h (el tope manda)
TOPE_VENTANA_HORAS = 24
FRACCION_VENTANA = 0.20


def ventana_de_aviso(minutos_objetivo: int) -> float:
    """Horas de antelacion para VENCE_PRONTO: min(24 h, 20% del plazo)."""
    return min(TOPE_VENTANA_HORAS,
               (minutos_objetivo * FRACCION_VENTANA) / 60.0)


def _duracion_de(orden) -> int | None:
    """
    Los minutos que declara el tipo de trabajo vigente, o None.

    Se valida el TIPO ademas del valor: un esquema con
    'duracion_estimada_minutos': "90" (texto) o 0 no es una duracion utilizable,
    y tratarlo como 90 o como "sin plazo" seria inventar. Mismo criterio que
    'capacidad.py' aplica sobre la misma clave.
    """
    version = getattr(orden, "tipo_trabajo_version", None)
    if version is None:
        return None
    esquema = getattr(version, "esquema", None) or {}
    valor = esquema.get(CLAVE_DURACION)
    #  bool es subclase de int en Python y True valdria 1 minuto.
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        return None
    return valor


def _calendario_de(orden):
    """El calendario laboral de la organizacion, o None = 24/7."""
    from business_hours.calendar import get_default_calendar

    if not getattr(orden, "org_id", None):
        return None
    return get_default_calendar(orden.org_id)


def _faltantes(orden, version, minutos) -> list[dict]:
    """Lo que NO se sabe, nombrado. Medido sobre la fila, no deducido."""
    faltan = []
    if version is None:
        faltan.append({"entidad": "orden_trabajo", "campo": "tipo_trabajo_version",
                       "por_que": "la orden no tiene tipo de trabajo vigente"})
    elif minutos is None:
        faltan.append({"entidad": "tipo_trabajo", "campo": CLAVE_DURACION,
                       "por_que": "el tipo de trabajo no declara una duracion "
                                  "valida en minutos"})
    if getattr(orden, "created_at", None) is None:
        faltan.append({"entidad": "orden_trabajo", "campo": "created_at",
                       "por_que": "sin fecha de creacion no hay desde cuando contar"})
    return faltan


#  Centinela para distinguir "no me pasaron calendario" de "me pasaron None",
#  que significa 24/7 y es una respuesta legitima.
_SIN_CALENDARIO = object()


def plazo_de(orden, ahora=None, ventana_horas: int | None = None,
             calendario=_SIN_CALENDARIO) -> dict:
    """
    El plazo operativo de una orden. LEE y CALCULA; no escribe nada.

    'ahora' es inyectable a proposito: el resultado tiene que ser reproducible.
    Dos llamadas con el mismo 'ahora' y la misma fila devuelven lo mismo.

    'calendario' es inyectable por una razon distinta: 'get_default_calendar'
    no cachea, asi que calcular el plazo de un LOTE de ordenes de la misma
    organizacion lo consultaba una vez por orden. Quien tiene el lote lo busca
    una vez y lo pasa. Sin el argumento el comportamiento es identico al de
    antes -- se busca aqui dentro-- y pasar None significa 24/7, que es una
    respuesta valida y por eso el centinela no es None.

    Devuelve siempre las mismas claves, tambien cuando no hay plazo -- un dict
    con forma variable obliga a quien lo consume a adivinar cual recibio.
    """
    ahora = ahora or timezone.now()
    version = getattr(orden, "tipo_trabajo_version", None)
    minutos = _duracion_de(orden)
    faltantes = _faltantes(orden, version, minutos)

    base = {
        "estado": None,
        "minutos_objetivo": minutos,
        "ancla": None,
        "limite": None,
        "minutos_restantes": None,
        "minutos_atraso": None,
        "calendario": None,
        "ventana_horas": None,
        "ventana_fraccion": None,
        "datos_faltantes": faltantes,
        "ahora": ahora.isoformat(),
    }

    creada = getattr(orden, "created_at", None)
    if version is None or creada is None:
        #  No se pudo llegar al dato. Distinto de "no hay plazo declarado".
        base["estado"] = DATOS_INSUFICIENTES
        return base

    base["ancla"] = creada.isoformat()

    if minutos is None:
        base["estado"] = SIN_PLAZO
        return base

    #  Una orden terminada no tiene plazo corriendo. Se calcula igual el limite
    #  --sirve para mirar hacia atras-- pero el estado lo dice.
    terminada = getattr(orden, "estado_operativo", None) in ESTADOS_TERMINADOS

    if calendario is _SIN_CALENDARIO:
        calendario = _calendario_de(orden)
    base["calendario"] = getattr(calendario, "name", None) if calendario else None

    from business_hours.calendar import add_business_hours

    limite = add_business_hours(creada, minutos / 60.0, calendario)
    base["limite"] = limite.isoformat()

    if terminada:
        base["estado"] = NO_APLICA
        return base

    delta = int((limite - ahora).total_seconds() // 60)
    if delta < 0:
        base["estado"] = VENCIDA
        base["minutos_atraso"] = -delta
        base["minutos_restantes"] = 0
        return base

    base["minutos_restantes"] = delta
    base["minutos_atraso"] = 0
    horas = ventana_de_aviso(minutos) if ventana_horas is None else ventana_horas
    base["ventana_horas"] = horas
    base["ventana_fraccion"] = FRACCION_VENTANA if ventana_horas is None else None
    #  La ventana es tiempo de reloj, no horas habiles: quien mira la pantalla
    #  quiere saber si esto le explota hoy, no dentro de cuantas horas de
    #  oficina. El PLAZO si respeta el calendario; el aviso no.
    base["estado"] = VENCE_PRONTO if limite <= ahora + timedelta(hours=horas) else A_TIEMPO
    return base


def resumen(plazo: dict) -> str:
    """Una linea legible. Describe el hecho; no reparte responsabilidades."""
    e = plazo["estado"]
    if e == VENCIDA:
        return f"vencida hace {plazo['minutos_atraso']} minuto(s)"
    if e == VENCE_PRONTO:
        return f"vence en {plazo['minutos_restantes']} minuto(s)"
    if e == A_TIEMPO:
        return f"a tiempo, quedan {plazo['minutos_restantes']} minuto(s)"
    if e == SIN_PLAZO:
        return "sin plazo declarado por el tipo de trabajo"
    if e == NO_APLICA:
        return "la orden ya termino; el plazo no corre"
    return "no se pudo determinar el plazo"
