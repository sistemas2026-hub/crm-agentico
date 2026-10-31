# -*- coding: utf-8 -*-
"""Donde esta el telefono del tecnico (31/10/2026).

    POST /api/campo/ubicacion/   {latitud, longitud, medida_en, precision_m?, bateria?}

La manda la aplicacion de campo mientras hay jornada. **El servidor rechaza la
de quien no sale hoy** (`ubicacion_de_cuadrilla.registrar`): la regla de "solo
durante la jornada" no puede vivir solo en el telefono. Ver el encabezado de
`campo/ubicacion_de_cuadrilla.py`.

Una posicion rechazada devuelve 200 con `guardada: false`, no un error: para la
aplicacion no es una falla --dejo de haber jornada-- y un 4xx la haria
reintentar en un bucle que nadie necesita.

Lo que NO se registra en el log: la coordenada. Donde esta una persona es dato
de esa persona; el log dice que llego una, no donde.
"""
from __future__ import annotations

import logging

from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated

logger = logging.getLogger(__name__)

#: Fuera de esto no es la Tierra: es un error de la aplicacion o una prueba.
LIMITES = {"latitud": (-90.0, 90.0), "longitud": (-180.0, 180.0)}


def _coordenada(datos, nombre):
    """El valor como float, o `None` si falta o no es un numero del rango."""
    if nombre not in datos:
        return None
    try:
        v = float(datos[nombre])
    except (TypeError, ValueError):
        return None
    bajo, alto = LIMITES[nombre]
    return v if bajo <= v <= alto else None


def _entero(datos, nombre, bajo, alto):
    """Opcional: ausente o ilegible es `None`, nunca un 400. Que el telefono no
    sepa su bateria no puede costar la posicion."""
    if datos.get(nombre) is None:
        return None
    try:
        v = int(float(datos[nombre]))
    except (TypeError, ValueError):
        return None
    return v if bajo <= v <= alto else None


class UbicacionDelTecnicoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        from campo.ubicacion_de_cuadrilla import FueraDeLaJornada, registrar

        datos = request.data or {}
        latitud = _coordenada(datos, "latitud")
        longitud = _coordenada(datos, "longitud")
        if latitud is None or longitud is None:
            return Response(
                {"detail": "Hacen falta una latitud y una longitud válidas."},
                status=status.HTTP_400_BAD_REQUEST)

        #  `parse_datetime` LEVANTA ValueError con una fecha bien formada pero
        #  imposible ('2026-02-31T10:00:00'), medido el 31/10/2026. Sin esto
        #  subia a 500: la aplicacion reintentaba en bucle --justo lo que
        #  responder 200 quiso evitar-- y con DEBUG encendido la pagina de
        #  error de Django devolvia la coordenada en el cuerpo.
        try:
            medida_en = parse_datetime(str(datos.get("medida_en") or ""))
        except ValueError:
            medida_en = None
        if medida_en is None:
            medida_en = timezone.now()
        elif timezone.is_naive(medida_en):
            medida_en = timezone.make_aware(medida_en)

        try:
            registrar(
                request.profile.org, request.profile,
                latitud=latitud, longitud=longitud, medida_en=medida_en,
                precision_m=_entero(datos, "precision_m", 0, 100000),
                bateria=_entero(datos, "bateria", 0, 100),
            )
        except FueraDeLaJornada as e:
            #  Ni log con la coordenada ni 4xx: la aplicacion deja de mandar.
            #  El motivo distingue los tres casos (no sale hoy, fuera del
            #  horario, la empresa no cargo horario) para poder depurarlo sin
            #  tener que mirar donde estaba nadie.
            return Response({"guardada": False, "motivo": e.motivo})
        return Response({"guardada": True})
