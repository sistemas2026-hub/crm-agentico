"""Lo que el Supervisor hace solo con el seguimiento, por empresa (30/10/2026).

    GET  /api/campo/seguimiento/configuracion/   como esta
    PUT  /api/campo/seguimiento/configuracion/   {"recordar_al_tecnico": bool}

Editable desde Programacion (CLAUDE.md §3.3: lo que varia por empresa se
edita desde la interfaz). Solo quien gestiona.

Que el Supervisor CIERRE solo no se enciende aca: es una tarea que se le
delega desde su chat, con el nivel 3 y el interruptor de emergencia, como las
otras (auditoria de frontera, 30/10/2026: una casilla sin actor ni motivo no
puede habilitar una accion con efecto en el ISP)."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.cuadrillas_views import _exigir_gestion
from campo.permissions import IsCampoAuthenticated

CAMPOS = ("recordar_al_tecnico",)


def _como_esta(org) -> dict:
    from campo.seguimiento import ConfiguracionDeSeguimiento

    fila = ConfiguracionDeSeguimiento.objects.filter(org=org).first()
    if fila is None:
        fila = ConfiguracionDeSeguimiento(org=org)
    return {c: getattr(fila, c) for c in CAMPOS}


class ConfiguracionDeSeguimientoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        _exigir_gestion(request)
        return Response(_como_esta(request.profile.org))

    def put(self, request):
        from campo.seguimiento import ConfiguracionDeSeguimiento

        _exigir_gestion(request)
        datos = request.data or {}
        cambios = {c: datos[c] for c in CAMPOS if c in datos}
        if any(not isinstance(v, bool) for v in cambios.values()):
            return Response({"detail": "Cada valor tiene que ser verdadero o falso."},
                            status=status.HTTP_400_BAD_REQUEST)
        org = request.profile.org
        fila, _ = ConfiguracionDeSeguimiento.objects.get_or_create(org=org)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        if cambios:
            fila.save(update_fields=[*cambios, "updated_at"])
        return Response(_como_esta(org))
