# -*- coding: utf-8 -*-
"""
===============================================================================
 AJUSTES DEL SUPERVISOR  --  delegar o quitar una tarea con un clic
===============================================================================

    GET   /api/operaciones/supervisor/ajustes/   el catalogo entero, cada tarea
                                                 con si esta delegada, quien,
                                                 cuando y por que, y lo que le
                                                 falta para actuar
    POST  /api/operaciones/supervisor/ajustes/   {clave, delegar, motivo}

POR QUE EXISTE  --  27/10/2026
------------------------------
Hasta hoy una tarea se delegaba solo hablandole al chat, y la pantalla del
alcance la mostraba en solo lectura. Eso dejaba fuera a quien no quiere (o no
sabe) pedirselo a una IA, y un Supervisor que va a publicar solo tiene que
poder apagarse con un clic: es la propuesta «Ajustes del Supervisor» de la
ficha de la jornada.

NO ES UN SEGUNDO CAMINO DE ESCRITURA. Escribe por 'td.delegar' y 'td.quitar',
las mismas funciones que usa el chat: las garantias (catalogo cerrado, persona
obligatoria, una fila por tarea que se enciende y se apaga) siguen viviendo en
un solo lugar. Lo que esta vista agrega es solo lo de HTTP, y dos reglas de
pantalla:

  EL MOTIVO ES OBLIGATORIO, en las dos direcciones. Mismo criterio que el
  freno de mano: una linea, no un informe. Con el clic solo quedaria quien y
  cuando, y el porque es lo que se pregunta meses despues.

  UNA PANTALLA VIEJA NO PISA UN REGISTRO. Se manda el estado que se quiere, no
  "invertir": si la tarea ya esta asi, 409 y no se escribe nada. Sin esto, dos
  personas con la pantalla abierta se pisarian el quien y el motivo.

QUE TAREA PUEDE ACTUAR NO SE CALCULA ACA: se reusa la lectura de la pantalla
del alcance ('AutonomiaSupervisorView._delegaciones'), que ya resuelve el nivel
efectivo y si algo la despierta. Una regla en dos lugares se separa el dia que
cambia una.

QUIEN SE MUESTRA CON NOMBRE, y no con el correo. 'td.delegadas' devuelve solo
el ID a proposito ("esto puede terminar en un log") y esa lectura la usa el
chat; esta es una pantalla de gestion, y "quien la delego" sin nombre no
contesta nada.
"""
from __future__ import annotations

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from operaciones.permissions import EsJefeDeOperaciones

logger = logging.getLogger(__name__)

MAX_MOTIVO = 500


class PuedeAjustarAlSupervisor(EsJefeDeOperaciones):
    """La misma puerta que el resto del Supervisor, con su propio texto: el
    del padre habla de revisar propuestas y mandaria a buscar en otro lado."""

    message = ("Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver "
               "y cambiar las tareas del Supervisor.")


def _nombre(profile) -> str:
    """El nombre de la persona, nunca el correo: si no tiene, se dice asi."""
    user = getattr(profile, "user", None)
    return (getattr(user, "name", "") or "").strip() or "una persona"


def _tareas(org) -> dict:
    """El catalogo entero, con el estado y lo que falta, para pintar la lista."""
    from operaciones import autonomia, tareas_delegadas as td
    from operaciones.tareas_modelos import TareaDelegada
    from operaciones.views import AutonomiaSupervisorView

    estado = autonomia.nivel_efectivo(org)
    filas = {f.clave: f for f in (TareaDelegada.objects
                                  .filter(org=org)
                                  .select_related("delegada_por__user",
                                                  "quitada_por__user"))}
    tareas = []
    for d in AutonomiaSupervisorView._delegaciones(org, estado, td):
        fila = filas.get(d["clave"])
        quitada = fila is not None and not fila.activa
        tareas.append({
            **d,
            #  'fila' puede faltar aunque 'delegada' diga que si: se leyeron
            #  en dos consultas, y entre las dos alguien pudo delegarla.
            "delegada_por": (_nombre(fila.delegada_por)
                             if d["delegada"] and fila is not None
                             and fila.delegada_por_id else ""),
            #  Lo de la ultima vez que se quito, solo mientras sigue quitada:
            #  con la tarea encendida, ese motivo ya no describe nada.
            "quitada_en": (fila.quitada_en.isoformat()
                           if quitada and fila.quitada_en else None),
            "quitada_por": (_nombre(fila.quitada_por)
                            if quitada and fila.quitada_por_id else ""),
            "motivo_al_quitar": fila.motivo_al_quitar if quitada else "",
            #  LA QUE SE APOYA EN OTRA (las correcciones sin el paso no hacen
            #  nada). El chat lo dice al delegar; la pantalla tiene que poder
            #  decirlo antes del clic.
            "requiere": [{"clave": r,
                          "nombre": td.CATALOGO.get(r, {}).get("nombre", r),
                          "delegada": td.esta_delegada(org, r)}
                         for r in td.CATALOGO[d["clave"]].get("requiere") or ()],
        })
    return {
        "nivel_efectivo": estado["efectivo"],
        "interruptor_permite": estado["interruptor_permite"],
        "motivo": estado["motivo"],
        "tareas": tareas,
    }


class AjustesSupervisorView(APIView):
    """Delegar o quitar cada tarea del catalogo, con persona y motivo."""

    permission_classes = [PuedeAjustarAlSupervisor]

    def get(self, request):
        return Response(_tareas(request.org))

    def post(self, request):
        from operaciones import tareas_delegadas as td
        from operaciones.tareas_modelos import TareaDelegada

        actor = getattr(request, "profile", None)
        if actor is None:
            return Response(
                {"detail": "no se pudo determinar quién hace el cambio"},
                status=status.HTTP_400_BAD_REQUEST)

        clave = str(request.data.get("clave") or "").strip()
        if clave not in td.CATALOGO:
            return Response({"detail": "Esa tarea no está en el catálogo."},
                            status=status.HTTP_400_BAD_REQUEST)
        #  BOOLEANO DE VERDAD: la cadena "false" es verdadera para Python, y
        #  leerla como tal encenderia una tarea que alguien quiso apagar.
        delegar = request.data.get("delegar")
        if not isinstance(delegar, bool):
            return Response({"detail": "Falta decir si se delega o se quita."},
                            status=status.HTTP_400_BAD_REQUEST)
        motivo = " ".join(str(request.data.get("motivo") or "").split())
        if not motivo:
            return Response(
                {"detail": "Escribí el motivo: queda registrado con tu nombre."},
                status=status.HTTP_400_BAD_REQUEST)
        if len(motivo) > MAX_MOTIVO:
            return Response(
                {"detail": f"El motivo va hasta {MAX_MOTIVO} letras."},
                status=status.HTTP_400_BAD_REQUEST)

        #  La lectura del estado y la escritura van juntas, bajo el bloqueo de
        #  ESTA tarea ('td.bloquear', el mismo que toman 'td.delegar' y
        #  'td.quitar' cuando llegan por el chat): entre las dos no puede
        #  colarse otra persona, tampoco la primera vez, cuando todavia no hay
        #  fila que bloquear. Y nada de afuera adentro de esta transaccion.
        with transaction.atomic():
            td.bloquear(request.org, clave)
            fila = (TareaDelegada.objects
                    .filter(org=request.org, clave=clave).first())
            if bool(fila and fila.activa) == delegar:
                return Response(
                    {"detail": ("Esa tarea ya estaba "
                                + ("delegada" if delegar else "sin delegar")
                                + ": alguien la cambió mientras mirabas. "
                                  "Recargá la página.")},
                    status=status.HTTP_409_CONFLICT)
            try:
                if delegar:
                    td.delegar(request.org, clave, actor=actor,
                               pedido_textual=motivo)
                else:
                    td.quitar(request.org, clave, actor=actor, motivo=motivo)
            except td.ErrorTarea as e:
                return Response({"detail": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)

        #  UNA LINEA POR CAMBIO. La fila guarda el ultimo estado, no la
        #  secuencia; esto deja quien y cuando de cada clic (el id, nunca el
        #  nombre ni el motivo, que es texto libre).
        logger.info("Ajustes del Supervisor: tarea %s %s por %s", clave,
                    "delegada" if delegar else "quitada", actor.id)
        #  SOLO EL RESULTADO, no la lista: la lista lee el nivel en el motor, y
        #  si eso fallara despues de guardar, la persona veria un error de un
        #  cambio que si quedo (auditor independiente, 27/10/2026). La pantalla
        #  vuelve a pedir la lista con un GET.
        return Response({"clave": clave, "delegada": delegar})
