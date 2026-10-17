# -*- coding: utf-8 -*-
"""
================================================================================
 CAPACIDAD OPERACIONAL  --  paso M03-G
================================================================================

Responde una sola pregunta, para un dia y una persona:

    cuanto tiempo operativo hay, cuanto esta comprometido, y si eso se pasa.

LA CAPACIDAD NO SE GUARDA. SE DERIVA.
-------------------------------------
No es una decision de este modulo: 'operaciones/models.py' ya lo habia
declarado al crear DisponibilidadTecnico --

    "Un numero de 'capacidad' depende de la disponibilidad, de la carga ya
     asignada, de la duracion estimada del tipo de trabajo, de la zona y de
     los bloqueos. Guardarlo es garantizar que quede viejo la proxima vez que
     cualquiera de esos cinco cambie."

-- asi que aqui no hay modelo, no hay tabla y no hay migracion. Se calcula
cuando se pregunta, con lo que haya en ese momento.

LO QUE NO HACE, Y NO ES UN OLVIDO
---------------------------------
No reprograma, no reasigna, no cancela, no retira a nadie y no llama a ningun
sistema externo. Produce un resultado legible; decidir que hacer con el es de
quien opera, y proponerlo sera de M09.

EL DATO QUE FALTA NO VALE CERO
------------------------------
Es la regla que gobierna todo el modulo. Una orden sin duracion conocida NO
aporta 0 minutos a la carga: aporta *desconocido*, y eso cambia lo que se
puede concluir. De ahi la asimetria del veredicto:

    con datos parciales SE PUEDE demostrar que hay sobrecarga
    (si lo ya conocido no cabe, agregar lo desconocido tampoco va a caber),

    pero NO SE PUEDE demostrar que no la hay.

Por eso "no hay sobrecarga" solo se afirma cuando se conocen todas las
duraciones. En cualquier otro caso el veredicto es INDETERMINADO, con la lista
de lo que falta. Un supervisor que lea "sin sobrecarga" sobre datos
incompletos toma una decision peor que uno que lea "no se sabe".

DE DONDE SALE CADA NUMERO
-------------------------
    jornada         business_hours.BusinessCalendar de la org, en SU zona
                    horaria declarada. No se reinterpreta: si el calendario
                    dice UTC, se usa UTC.
    duracion        1) ProgramacionOrden.hora_fin - hora_inicio, si ambas
                    2) WorkTypeVersion.esquema['duracion_estimada_minutos']
                    3) DESCONOCIDA. Nunca 0.
    disponibilidad  operaciones.DisponibilidadTecnico, por franjas
    cuadrilla       campo.AsignacionTrabajo (M03-F-B)

CUADRILLAS: SIN COEFICIENTES INVENTADOS
---------------------------------------
Una OT de 120 minutos con dos personas le cuesta 120 minutos a CADA una: las
dos estan ocupadas ese rato. Ni se divide entre dos --eso supondria que rinden
el doble-- ni se multiplica. No existe una regla empresarial de productividad
de cuadrillas, y no se inventa una aqui.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from datetime import time as _time

from business_hours.models import BusinessCalendar

from campo.models import AsignacionTrabajo
from common.models import Profile
from operaciones.models import DisponibilidadTecnico
from operaciones.programacion import lineas_de_jornada

#  Clave opcional dentro de WorkTypeVersion.esquema. El esquema es un JSONField
#  que ya existe, asi que declarar la duracion por tipo de trabajo NO necesita
#  migracion. No se siembra ningun valor: si no esta, la duracion es DESCONOCIDA.
CLAVE_DURACION = "duracion_estimada_minutos"

DIAS = ("monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday")

#  --- estados de los datos -----------------------------------------------
SUFICIENTES = "DATOS_SUFICIENTES"
PARCIALES = "DATOS_PARCIALES"
INSUFICIENTES = "DATOS_INSUFICIENTES"

#  --- veredicto ----------------------------------------------------------
SOBRECARGA = "SOBRECARGA"
SIN_SOBRECARGA = "SIN_SOBRECARGA"
INDETERMINADO = "INDETERMINADO"
NO_DETERMINABLE = "CAPACIDAD_NO_DETERMINABLE"

#  --- por que no hay jornada --------------------------------------------
SIN_CALENDARIO = "SIN_CALENDARIO"
FERIADO = "FERIADO"
CERRADA = "JORNADA_CERRADA"
INVALIDA = "JORNADA_INVALIDA"

#  --- estados de disponibilidad -----------------------------------------
DISPONIBLE = "DISPONIBLE"
AUSENTE = "AUSENTE"
PARCIAL = "DISPONIBILIDAD_PARCIAL"
SIN_REGISTRO = "SIN_REGISTRO"


def _minutos(t: _time) -> int:
    return t.hour * 60 + t.minute


def _union(tramos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Fusiona tramos solapados. Sin esto, dos franjas que se pisan contarian dos veces."""
    if not tramos:
        return []
    ordenados = sorted(tramos)
    salida = [ordenados[0]]
    for ini, fin in ordenados[1:]:
        ult_ini, ult_fin = salida[-1]
        if ini <= ult_fin:
            salida[-1] = (ult_ini, max(ult_fin, fin))
        else:
            salida.append((ini, fin))
    return salida


def _interseccion(a: list[tuple[int, int]],
                  b: list[tuple[int, int]]) -> list[tuple[int, int]]:
    salida = []
    for ai, af in a:
        for bi, bf in b:
            ini, fin = max(ai, bi), min(af, bf)
            if fin > ini:
                salida.append((ini, fin))
    return _union(salida)


def _restar(base: list[tuple[int, int]],
            quitar: list[tuple[int, int]]) -> list[tuple[int, int]]:
    salida = list(base)
    for qi, qf in _union(quitar):
        nuevo = []
        for bi, bf in salida:
            if qf <= bi or qi >= bf:
                nuevo.append((bi, bf))
                continue
            if bi < qi:
                nuevo.append((bi, qi))
            if qf < bf:
                nuevo.append((qf, bf))
        salida = nuevo
    return salida


def _total(tramos: list[tuple[int, int]]) -> int:
    return sum(f - i for i, f in tramos)


# ==============================================================================
#  JORNADA
# ==============================================================================

@dataclass
class Jornada:
    abierta: bool
    motivo: str = ""
    apertura: _time | None = None
    cierre: _time | None = None
    minutos: int = 0
    zona_horaria: str = ""
    tramos: list = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "abierta": self.abierta,
            "motivo": self.motivo,
            "apertura": str(self.apertura) if self.apertura else None,
            "cierre": str(self.cierre) if self.cierre else None,
            "minutos": self.minutos,
            "zona_horaria": self.zona_horaria,
        }


def jornada_de(org, dia: _date) -> Jornada:
    """
    La ventana operativa de la EMPRESA para ese dia.

    Se lee de BusinessCalendar y se respeta su campo 'timezone' TAL COMO ESTA.
    Reinterpretarlo seria cambiar la jornada en silencio, que es justo lo que
    este paso tiene prohibido: si el calendario declara una zona que no
    corresponde a la operacion real, eso se corrige EDITANDO EL CALENDARIO --
    es configuracion, no codigo.
    """
    cal = (BusinessCalendar.objects.filter(org=org, is_default=True).first()
           or BusinessCalendar.objects.filter(org=org).first())
    if cal is None:
        return Jornada(abierta=False, motivo=SIN_CALENDARIO)

    if cal.holidays.filter(date=dia).exists():
        return Jornada(abierta=False, motivo=FERIADO, zona_horaria=cal.timezone)

    nombre = DIAS[dia.weekday()]
    apertura = getattr(cal, f"{nombre}_open")
    cierre = getattr(cal, f"{nombre}_close")
    if apertura is None or cierre is None:
        return Jornada(abierta=False, motivo=CERRADA, zona_horaria=cal.timezone)

    ini, fin = _minutos(apertura), _minutos(cierre)
    if fin <= ini:
        #  Una jornada que cierra antes de abrir no se "arregla" suponiendo que
        #  cruza la medianoche: eso seria inventar una politica de turno noche.
        return Jornada(abierta=False, motivo=INVALIDA, apertura=apertura,
                       cierre=cierre, zona_horaria=cal.timezone)

    return Jornada(abierta=True, apertura=apertura, cierre=cierre,
                   minutos=fin - ini, zona_horaria=cal.timezone,
                   tramos=[(ini, fin)])


# ==============================================================================
#  DURACION
# ==============================================================================

def duracion_de_linea(linea) -> tuple[int | None, str]:
    """
    (minutos, fuente). 'minutos' en None significa DESCONOCIDA -- nunca 0.

    Se prefiere la franja de la propia linea sobre el valor del tipo de
    trabajo: si alguien reservo un horario concreto para ESTA orden, ese dato
    es mas especifico que el estimado generico.
    """
    hi, hf = linea.hora_inicio, linea.hora_fin
    if hi is not None and hf is not None:
        ini, fin = _minutos(hi), _minutos(hf)
        if fin > ini:
            return fin - ini, "franja_de_la_linea"

    version = getattr(linea.orden, "tipo_trabajo_version", None)
    esquema = getattr(version, "esquema", None) or {}
    valor = esquema.get(CLAVE_DURACION)
    #  'bool' es subclase de 'int' en Python: True pasaria como 1 minuto.
    if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0:
        return valor, "tipo_de_trabajo"

    return None, "desconocida"


# ==============================================================================
#  DISPONIBILIDAD
# ==============================================================================

def disponibilidad_de(org, profile, dia: _date, jornada: Jornada) -> dict:
    """
    Cuanto de la jornada tiene realmente esa persona.

    Cuatro estados, y el cuarto importa tanto como los otros tres: SIN_REGISTRO
    no es lo mismo que DISPONIBLE. Se asume la jornada completa porque es lo
    unico que permite calcular algo, pero el supuesto queda DECLARADO en la
    respuesta para que nadie lo confunda con un dato.
    """
    if not jornada.abierta:
        return {"estado": SIN_REGISTRO, "minutos": 0, "tramos": [],
                "supuesto": None, "franjas": 0}

    franjas = list(DisponibilidadTecnico.objects.filter(
        org=org, profile=profile, fecha=dia))
    if not franjas:
        return {
            "estado": SIN_REGISTRO,
            "minutos": jornada.minutos,
            "tramos": list(jornada.tramos),
            "franjas": 0,
            "supuesto": (
                "No hay ninguna franja registrada para esa persona ese dia. Se "
                "toma la jornada completa de la empresa; es un SUPUESTO, no un "
                "dato declarado."),
        }

    positivas = [(_minutos(f.hora_inicio), _minutos(f.hora_fin))
                 for f in franjas if f.disponible]
    negativas = [(_minutos(f.hora_inicio), _minutos(f.hora_fin))
                 for f in franjas if not f.disponible]

    base = _interseccion(jornada.tramos, _union(positivas)) if positivas \
        else list(jornada.tramos)
    tramos = _restar(base, negativas)
    minutos = _total(tramos)

    if minutos == 0:
        estado = AUSENTE
    elif minutos == jornada.minutos:
        estado = DISPONIBLE
    else:
        estado = PARCIAL

    return {"estado": estado, "minutos": minutos, "tramos": tramos,
            "franjas": len(franjas), "supuesto": None,
            "motivos": sorted({f.motivo for f in franjas
                               if not f.disponible and f.motivo})}


# ==============================================================================
#  CAPACIDAD DE UNA PERSONA EN UN DIA
# ==============================================================================

def capacidad_de_persona(org, profile, dia: _date, lineas=None) -> dict:
    """
    El calculo completo para una persona. Es una LECTURA: no escribe nada.
    """
    jornada = jornada_de(org, dia)

    if lineas is None:
        lineas = list(lineas_de_jornada(org, dia=dia))

    #  Las lineas de ESTA persona: esta en la cuadrilla de la orden (M03-F-B).
    #  Se mira la pertenencia, no la principalia -- un ayudante tambien esta
    #  ocupado esas horas.
    ids = set(AsignacionTrabajo.objects
              .filter(orden__in=[l.orden_id for l in lineas], profile=profile)
              .values_list("orden_id", flat=True))
    suyas = [l for l in lineas if l.orden_id in ids]

    detalle, conocidos, sin_duracion = [], 0, []
    for linea in suyas:
        minutos, fuente = duracion_de_linea(linea)
        detalle.append({
            "linea": str(linea.id),
            "orden": str(linea.orden_id),
            "numero": linea.orden.numero,
            "secuencia": linea.secuencia,
            "duracion_minutos": minutos,
            "fuente_duracion": fuente,
        })
        if minutos is None:
            sin_duracion.append(linea.orden.numero)
        else:
            conocidos += minutos

    faltantes = []
    if not jornada.abierta:
        faltantes.append(jornada.motivo)
    if sin_duracion:
        faltantes.append("DURACION_DESCONOCIDA")

    disp = disponibilidad_de(org, profile, dia, jornada)
    if disp["supuesto"]:
        faltantes.append("SIN_REGISTRO_DISPONIBILIDAD")

    #  ---- veredicto -----------------------------------------------------
    if not jornada.abierta:
        capacidad = None
        estado_datos = INSUFICIENTES
        riesgo = INDETERMINADO
        resultado = NO_DETERMINABLE
        disponible_restante = None
        exceso = None
    else:
        capacidad = disp["minutos"]
        resultado = "CALCULADA"
        disponible_restante = capacidad - conocidos
        exceso = max(0, conocidos - capacidad)
        if sin_duracion:
            estado_datos = PARCIALES
            #  Lo ya conocido no cabe: agregar lo que falta tampoco va a caber.
            #  Se puede AFIRMAR la sobrecarga aunque falten datos.
            riesgo = SOBRECARGA if conocidos > capacidad else INDETERMINADO
        else:
            estado_datos = SUFICIENTES
            riesgo = SOBRECARGA if conocidos > capacidad else SIN_SOBRECARGA

    return {
        "profile": {
            "id": str(profile.id),
            "nombre": (profile.user.name or profile.user.email)
            if getattr(profile, "user", None) else str(profile.id),
        },
        "dia": str(dia),
        "resultado": resultado,
        "estado_datos": estado_datos,
        "jornada": jornada.como_dict(),
        "disponibilidad": {k: v for k, v in disp.items() if k != "tramos"},
        "capacidad_minutos": capacidad,
        "carga": {
            "minutos_conocidos": conocidos,
            "ordenes": len(suyas),
            "ordenes_sin_duracion": len(sin_duracion),
            "numeros_sin_duracion": sorted(sin_duracion),
            "es_cota_inferior": bool(sin_duracion),
            "detalle": detalle,
        },
        "disponible_restante_minutos": disponible_restante,
        "exceso_minutos": exceso,
        "riesgo": riesgo,
        "faltantes": faltantes,
    }


def capacidad_de_jornada(org, dia: _date, profile=None) -> dict:
    """
    Todas las personas con trabajo programado ese dia, o una sola si se pide.

    Si se pregunta por alguien SIN trabajo ese dia se responde igual, con carga
    cero: "no tiene nada" es una respuesta util y distinta de "no se sabe".
    """
    lineas = list(lineas_de_jornada(org, dia=dia))

    if profile is not None:
        personas = [profile]
    else:
        ids = (AsignacionTrabajo.objects
               .filter(orden__in=[l.orden_id for l in lineas])
               .values_list("profile_id", flat=True).distinct())
        personas = list(Profile.objects.filter(id__in=list(ids), org=org)
                        .select_related("user").order_by("id"))

    resultados = [capacidad_de_persona(org, p, dia, lineas=lineas)
                  for p in personas]

    con_sobrecarga = [r for r in resultados if r["riesgo"] == SOBRECARGA]
    return {
        "dia": str(dia),
        "jornada": jornada_de(org, dia).como_dict(),
        "personas": len(resultados),
        "ordenes_programadas": len(lineas),
        "con_sobrecarga": len(con_sobrecarga),
        "con_datos_incompletos": len(
            [r for r in resultados if r["estado_datos"] != SUFICIENTES]),
        "resultados": resultados,
    }
