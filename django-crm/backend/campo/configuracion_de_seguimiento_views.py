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

#: Los booleanos y los enteros se validan distinto, asi que se nombran
#: aparte. `CAMPOS` sigue siendo todo lo que la pantalla lee y escribe.
CAMPOS_SI_NO = ("recordar_al_tecnico",)
CAMPOS_MINUTOS = ("repetir_recordatorio_cada_minutos",)
CAMPOS = CAMPOS_SI_NO + CAMPOS_MINUTOS


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
        if any(not isinstance(cambios[c], bool)
               for c in CAMPOS_SI_NO if c in cambios):
            return Response({"detail": "Cada valor tiene que ser verdadero o falso."},
                            status=status.HTTP_400_BAD_REQUEST)
        #  UN TOPE DE ARRIBA, no solo que sea un entero: el campo es
        #  `PositiveSmallIntegerField` y un 70000 revienta en la base con un
        #  500 en vez de decir que el numero no sirve. 0 = un solo aviso.
        for c in CAMPOS_MINUTOS:
            if c not in cambios:
                continue
            v = cambios[c]
            if isinstance(v, bool) or not isinstance(v, int) or not (0 <= v <= 1440):
                return Response(
                    {"detail": "Los minutos tienen que ser un número entero "
                               "entre 0 y 1440 (0 = avisar una sola vez)."},
                    status=status.HTTP_400_BAD_REQUEST)
        org = request.profile.org
        fila, _ = ConfiguracionDeSeguimiento.objects.get_or_create(org=org)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        if cambios:
            fila.save(update_fields=[*cambios, "updated_at"])
        return Response(_como_esta(org))
