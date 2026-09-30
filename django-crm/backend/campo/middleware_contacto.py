# -*- coding: utf-8 -*-
"""Anota que el telefono de alguien le hablo al servidor.

DONDE SE ENGANCHA Y POR QUE
---------------------------
En un middleware y solo para las rutas de `/api/campo/`, que son las que usa la
aplicacion de campo. Podria haber ido dentro del permiso `IsCampoAuthenticated`
--por ahi pasan todas-- pero un permiso que ESCRIBE es una sorpresa: quien lo lee
espera que conteste si o no, no que deje una fila.

LO QUE ESTE ARCHIVO NO AFIRMA
-----------------------------
Que el telefono tenga señal ahora. Solo que en tal momento pudo hablar. La
diferencia importa: la aplicacion no tiene latido --la cola se drena por eventos
de la interfaz, medido el 30/09/2026-- asi que la AUSENCIA de contacto no
distingue "sin señal" de "la app cerrada en el bolsillo". Ver
`campo/seguimiento.py`.

FALLA EN SILENCIO, Y ES A PROPOSITO
-----------------------------------
Si esto no puede escribir, la peticion sigue. Es telemetria: que el tecnico no
pueda cargar su jornada porque no se pudo anotar una marca de contacto seria
cambiar un dato de observabilidad por el trabajo de una persona.
"""

from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


class ContactoDeCampoMiddleware:
    """Marca el ultimo contacto del dispositivo, con freno."""

    #: Solo lo que usa la aplicacion de campo.
    PREFIJO = "/api/campo/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        try:
            self._anotar(request, respuesta)
        except Exception:
            # Ni el tipo ni el mensaje: esto es telemetria y no puede tumbar nada.
            logger.debug("contacto_de_campo_no_anotado", exc_info=False)
        return respuesta

    def _anotar(self, request, respuesta) -> None:
        if not str(getattr(request, "path", "")).startswith(self.PREFIJO):
            return
        # Una respuesta 401/403 no prueba que sea un dispositivo NUESTRO hablando.
        if getattr(respuesta, "status_code", 500) in (401, 403):
            return

        profile = getattr(request, "profile", None)
        org = getattr(request, "org", None)
        if profile is None or org is None:
            return

        # Import tardio: el middleware se instancia antes de que las apps esten
        # cargadas.
        from campo.seguimiento import ContactoDeDispositivo

        ahora = timezone.now()
        fila = ContactoDeDispositivo.objects.filter(profile=profile).first()
        if fila is None:
            ContactoDeDispositivo.objects.create(
                org=org, profile=profile, visto_en=ahora, ultima_ruta=request.path[:255]
            )
            return

        # EL FRENO. Una persona abriendo pantallas hace decenas de peticiones por
        # minuto y la pregunta que esta fila contesta no cambia por eso.
        if (ahora - fila.visto_en).total_seconds() < ContactoDeDispositivo.SEGUNDOS_DE_FRENO:
            return

        fila.visto_en = ahora
        fila.ultima_ruta = request.path[:255]
        fila.save(update_fields=["visto_en", "ultima_ruta", "updated_at"])
