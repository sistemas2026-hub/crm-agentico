# -*- coding: utf-8 -*-
"""La instalacion que valida una persona (26/11/2026). Ver campo/instalacion.py.

    GET  /api/campo/instalaciones/por-activar/          lo que espera a una persona
    POST /api/campo/trabajos/<pk>/aprobar-instalacion/  el encargado aprueba: se activa
    POST /api/campo/trabajos/<pk>/instalacion-entregada/ el tecnico entrego: se cierra
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated


def _gestion(request):
    from campo.cuadrillas_views import _exigir_gestion

    _exigir_gestion(request)


class InstalacionesPorActivarView(APIView):
    """Las instalaciones que esperan a una persona, y las aprobadas que el
    tecnico todavia no entrego. Con su contrato y la revision del cierre."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo.contrato import vigente_de
        from campo.instalacion import requiere_validacion_humana
        from campo.models import OrdenTrabajo
        from campo.revision_del_cierre import revisar

        _gestion(request)
        org = request.profile.org
        filas = []
        for orden in (OrdenTrabajo.objects
                      .filter(org=org, estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
                              contratos__isnull=False)
                      .distinct().order_by("completada_campo_en")[:100]):
            if not requiere_validacion_humana(orden):
                continue
            contrato = vigente_de(orden)
            try:
                revision = revisar(orden)
            except Exception:                                    # noqa: BLE001
                revision = None
            entregar = orden.estado_validacion == OrdenTrabajo.APROBADO
            #  EL CLIENTE DEL CONTRATO, no el de la orden (27/11/2026): en el ISP
            #  la instalacion se abre sobre un cliente DE PASO, y la tarjeta
            #  decia su nombre («MARIO SABANAGRANDE») en vez del de quien firmo.
            del_contrato = ((contrato.datos or {}).get("cliente") or {}) if contrato else {}
            nombre = " ".join(x for x in (str(del_contrato.get("nombre") or "").strip(),
                                         str(del_contrato.get("apellido") or "").strip()) if x)
            filas.append({
                "orden_id": str(orden.id), "numero": orden.numero, "vuelta": orden.vuelta,
                "cliente": nombre or orden.cliente_nombre or "",
                "finalizada_en": (orden.completada_campo_en.isoformat()
                                  if orden.completada_campo_en else None),
                "validacion": orden.estado_validacion,
                "espera": "entrega_del_tecnico" if entregar else "validacion",
                "contrato": contrato.como_dict() if contrato else None,
                "revision": revision,
            })
        return Response({"instalaciones": filas, "trabadas": _trabadas(org),
                         "server_time": timezone.now().isoformat()})


def _trabadas(org) -> list[dict]:
    """LAS INSTALACIONES QUE NO QUEDARON CREADAS EN EL PROVEEDOR (27/11/2026).

    El usuario, despues de la OT-502: «que reporte este error y el encargado
    revise, y con un boton permita volver a crear». Hasta hoy los botones
    vivian SOLO en la tarjeta de una solicitud, y un contrato que sale del
    ticket no tiene solicitud: trabado, no habia como destrabarlo sin un
    comando. Aca van TODOS los contratos firmados con el alta fallida o por
    revisar, tengan solicitud o no. Lo que se puede hacer lo dice el contrato
    (`alta.por_revisar`, `alta.se_puede_pedir`)."""
    from campo.contrato import ContratoDeServicio

    filas = []
    for c in (ContratoDeServicio.objects
              .filter(org=org, estado=ContratoDeServicio.FIRMADO,
                      alta_estado__in=(ContratoDeServicio.ALTA_POR_REVISAR,
                                       ContratoDeServicio.ALTA_FALLIDA))
              .select_related("orden").order_by("-alta_actualizada_en")[:100]):
        cliente = (c.datos or {}).get("cliente") or {}
        nombre = " ".join(x for x in (str(cliente.get("nombre") or "").strip(),
                                     str(cliente.get("apellido") or "").strip()) if x)
        filas.append({"orden_id": str(c.orden_id), "numero": c.orden.numero if c.orden_id else None,
                      "cliente": nombre or (c.orden.cliente_nombre if c.orden_id else "") or "",
                      "contrato": c.como_dict()})
    return filas


class AprobarInstalacionView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo.despacho_views import _orden_o_404
        from campo.instalacion import NoSePuedeActivar, pedir_activacion

        _gestion(request)
        orden = _orden_o_404(request, pk)
        try:
            contrato = pedir_activacion(orden, por=request.profile)
        except NoSePuedeActivar as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"contrato": contrato.como_dict()}, status=status.HTTP_202_ACCEPTED)


class InstalacionEntregadaView(APIView):
    """El tecnico valido el servicio y entrego al cliente: la orden se cierra
    y AHI se cierra el ticket del proveedor (el usuario: «y despues cierra el
    ticket»)."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        from campo.contrato import ContratoDeServicio, vigente_de
        from campo.instalacion import requiere_validacion_humana
        from campo.models import OrdenTrabajo
        from campo.serializers import OrdenTrabajoDetailSerializer
        from campo.services.cierre_en_isp import cerrar_ticket_al_validar
        from campo.services.transiciones import TransicionInvalidaError, cerrar_orden
        from campo.views import _obtener_orden_o_404

        orden = _obtener_orden_o_404(request, pk)
        contrato = vigente_de(orden)
        if not requiere_validacion_humana(orden) or contrato is None:
            return Response({"detail": "Esta orden no es una instalación que se entregue así."},
                            status=status.HTTP_409_CONFLICT)
        if orden.estado_operativo == OrdenTrabajo.CERRADA:
            return Response({"orden": OrdenTrabajoDetailSerializer(orden).data,
                             "ya_estaba": True})
        if (orden.estado_validacion != OrdenTrabajo.APROBADO
                or contrato.estado != ContratoDeServicio.EN_EL_ISP):
            return Response({"detail": "Todavía no está aprobada: espera el aviso de que "
                                       "quedó activada."},
                            status=status.HTTP_409_CONFLICT)
        try:
            orden = cerrar_orden(orden, profile=request.profile,
                                 metadatos={"entregada_al_cliente": True})
        except TransicionInvalidaError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        ticket_isp = cerrar_ticket_al_validar(
            orden, request.profile,
            extra="Instalación validada, activada y entregada al cliente.")
        orden.refresh_from_db()
        return Response({"orden": OrdenTrabajoDetailSerializer(orden).data,
                         "ticket_isp": ticket_isp, "server_time": timezone.now().isoformat()})
