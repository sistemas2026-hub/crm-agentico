# -*- coding: utf-8 -*-
"""
================================================================================
 LOS ATASCOS DEL SUPERVISOR  --  29/10/2026
================================================================================
QUE ES
------
Lo que el ciclo no pudo decidir, anotado con su tipo. La pregunta del usuario:
«¿eso mejora al Supervisor en que rango de fallar?», y no habia un numero. Un
informe del 16/10 decia que de 27 tickets abiertos solo 6 eran atascos que mas
contexto podia destrabar --y en esos 6 la que fallo fue la IA--, pero era una
foto de un dia. Esto es la serie: que se traba, cuantos dias, cuantas cosas.

EL CATALOGO ES CERRADO. Cada tipo dice a que CLASE pertenece, y la clase es lo
que se va a decidir con el numero:
  no_decide      la regla no sabe elegir (un agente con mas contexto podria)
  no_alcanza     no hay lo que hace falta: material, cuadrillas, cupo
  falta_dato     falta configurar algo que una persona sabe
  ia             el modelo no contesto, contesto roto o sin hipotesis
  reglas         las reglas lo dejan con una persona, a proposito
  configuracion  una puerta de la empresa (tarea sin delegar, sin autorizar)
  fallo          algo se cayo
Un tipo que no esta en el catalogo no se anota: se avisa en el log. Asi el
informe nunca tiene una fila que nadie sabe clasificar.

NUNCA LEVANTA. Anotar es informativo: si la base falla, la fase sigue igual.
Es la regla de '_pasar_a_despacho_los_que_las_reglas_habiliten': anotar no
puede tumbar la vuelta.

SIN DATOS DEL CLIENTE: el sujeto es un id y el motivo un texto fijo (ver
'atascos_modelos').
================================================================================
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

FASE_MATERIAL = "material del dia"
FASE_REPARTO = "reparto del dia"
FASE_DESPACHO = "paso a Despacho"
FASE_LECTURA = "lectura de tickets"
FASE_CICLO = "ciclo"

NO_DECIDE = "no_decide"
NO_ALCANZA = "no_alcanza"
FALTA_DATO = "falta_dato"
IA = "ia"
REGLAS = "reglas"
CONFIGURACION = "configuracion"
FALLO = "fallo"

#: Lo que se le dice a una persona de cada clase, en el informe.
CLASES = {
    NO_DECIDE: "la regla no sabe decidir",
    NO_ALCANZA: "no alcanza lo que hay",
    FALTA_DATO: "falta un dato de configuración",
    IA: "la IA no contestó bien",
    REGLAS: "las reglas lo dejan con una persona",
    CONFIGURACION: "frenado por una puerta de la empresa",
    FALLO: "algo se cayó",
}

#: tipo -> (clase, que es). El texto es para el informe.
TIPOS = {
    # Material del dia (campo/material_del_dia.py, operaciones/carga_del_material.py)
    "kit_sin_elegir": (NO_DECIDE, "ningún kit se parece a la labor, o empatan"),
    "bodega_sin_elegir": (NO_DECIDE, "ninguna bodega se puede elegir para la cuadrilla"),
    "sin_lider": (FALTA_DATO, "la cuadrilla no tiene líder con cuenta activa"),
    "material_no_alcanza": (NO_ALCANZA, "la bodega no alcanza para completar el kit"),
    "sale_sin_equipo": (NO_ALCANZA, "la cuadrilla sale sin un equipo con serie de su kit"),
    "falta_en_bodega": (NO_ALCANZA, "a la bodega le falta un material para los kits del día"),
    "carga_fallo": (FALLO, "la carga de una cuadrilla se cayó"),
    # Reparto del dia (operaciones/publicacion_del_reparto.py)
    "orden_sin_labor": (NO_DECIDE, "la orden no tiene labor: no se sabe a qué cuadrilla va"),
    "orden_sin_zona": (NO_DECIDE, "el barrio de la orden no está en ninguna zona"),
    "orden_sin_cuadrilla": (NO_ALCANZA, "ninguna cuadrilla de hoy hace esa labor en esa zona"),
    "orden_sobrante": (NO_ALCANZA, "las cuadrillas que la pueden hacer llegaron a su tope"),
    "cuadrilla_sin_cuenta": (FALTA_DATO, "la cuadrilla no tiene a nadie con cuenta que reciba"),
    "cuadrilla_ausente": (NO_ALCANZA, "alguien de la cuadrilla declaró ausencia hoy"),
    # Paso a Despacho (operaciones/paso_a_despacho.py)
    "despacho_por_reglas": (REGLAS, "las reglas la dejan con una persona"),
    "despacho_sin_delegar": (CONFIGURACION, "la tarea del paso a Despacho no está delegada"),
    "despacho_sin_autorizar": (CONFIGURACION, "la empresa no autorizó el paso a Despacho"),
    "despacho_otra_puerta": (REGLAS, "otra puerta del paso (el caso, el registro)"),
    "despacho_fallo": (FALLO, "el paso a Despacho se cayó con esta propuesta"),
    "techo_ilegible": (FALLO, "no se pudo leer el techo de autonomía"),
    # Lectura de tickets (operaciones/diagnostico_de_ticket.py)
    "ia_error": (IA, "pedirle la lectura al modelo dio error"),
    "ia_respuesta_rota": (IA, "el modelo contestó una lectura rota"),
    "ia_sin_hipotesis": (IA, "el modelo leyó el ticket y no dio hipótesis"),
    # El ciclo
    "fase_caida": (FALLO, "una fase entera del ciclo se cayó"),
}


def _dia(org, ahora):
    from campo.reparto import _zona_de

    return ahora.astimezone(_zona_de(org)).date()


def _sumar(claves, motivo, ahora) -> int:
    from operaciones.models import AtascoDelSupervisor

    return (AtascoDelSupervisor.objects.filter(**claves)
            .update(veces=F("veces") + 1, ultima_vez=ahora, motivo=motivo,
                    updated_at=ahora))


def anotar(org, fase: str, tipo: str, sujeto, motivo: str = "", *, ahora=None) -> bool:
    """Anota UN atasco de hoy: la primera vez crea la fila, las demas suman
    una vuelta. Devuelve si quedo escrito. Nunca levanta."""
    from operaciones.models import AtascoDelSupervisor

    if tipo not in TIPOS:
        logger.warning("Supervisor: atasco de un tipo fuera del catalogo (%s): no se anota",
                       tipo)
        return False
    try:
        ahora = ahora or timezone.now()
        claves = {"org": org, "dia": _dia(org, ahora), "fase": fase[:48], "tipo": tipo,
                  "sujeto": str(sujeto)[:100]}
        motivo = " ".join(str(motivo or "").split())[:200]
        with transaction.atomic():
            if _sumar(claves, motivo, ahora):
                return True
            try:
                with transaction.atomic():
                    AtascoDelSupervisor.objects.create(
                        **claves, motivo=motivo, primera_vez=ahora, ultima_vez=ahora)
            except IntegrityError:
                #  Otra vuelta la creo entre el update y el create.
                _sumar(claves, motivo, ahora)
        return True
    except Exception as e:                                       # noqa: BLE001
        logger.warning("Supervisor: no se pudo anotar un atasco (%s)", type(e).__name__)
        return False


def informe(org, desde, hasta) -> dict:
    """Lo anotado entre dos dias (inclusive), agrupado. NO ESCRIBE.

        {"desde", "hasta", "dias_con_atascos",
         "por_clase": [{clase, que_es, dias, sujetos, veces}],
         "por_tipo": [{clase, fase, tipo, que_es, motivo, dias, sujetos, veces}]}
    """
    from operaciones.models import AtascoDelSupervisor

    filas = AtascoDelSupervisor.objects.filter(org=org, dia__gte=desde, dia__lte=hasta)

    por_tipo = []
    for r in (filas.values("fase", "tipo", "motivo")
              .annotate(dias=Count("dia", distinct=True),
                        sujetos=Count("sujeto", distinct=True), veces=Sum("veces"))):
        clase, que_es = TIPOS.get(r["tipo"], (FALLO, "tipo que ya no está en el catálogo"))
        por_tipo.append({"clase": clase, "fase": r["fase"], "tipo": r["tipo"],
                         "que_es": que_es, "motivo": r["motivo"], "dias": r["dias"],
                         "sujetos": r["sujetos"], "veces": r["veces"]})
    por_tipo.sort(key=lambda r: (list(CLASES).index(r["clase"]), -r["sujetos"], r["tipo"]))

    #  POR CLASE, contando de la base y no sumando las filas de arriba: un
    #  sujeto que se trabo dos dias es UN sujeto, y la suma lo contaria dos.
    tipos_de = {}
    for tipo, (clase, _) in TIPOS.items():
        tipos_de.setdefault(clase, []).append(tipo)
    por_clase = []
    for clase, que_es in CLASES.items():
        de_la_clase = filas.filter(tipo__in=tipos_de.get(clase, []))
        r = de_la_clase.aggregate(dias=Count("dia", distinct=True), veces=Sum("veces"))
        sujetos = de_la_clase.values("tipo", "sujeto").distinct().count()
        if sujetos:
            por_clase.append({"clase": clase, "que_es": que_es, "dias": r["dias"],
                              "sujetos": sujetos, "veces": r["veces"] or 0})

    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "dias_con_atascos": filas.values("dia").distinct().count(),
            "por_clase": por_clase, "por_tipo": por_tipo}
