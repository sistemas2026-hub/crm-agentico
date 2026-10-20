# -*- coding: utf-8 -*-
"""
================================================================================
 LAS PLANTILLAS DE TRABAJO, DESDE LA PLATAFORMA
================================================================================

    GET   /campo/plantillas/                  el catalogo de partida y las propias
    POST  /campo/plantillas/                  crear: desde el catalogo o desde cero
    GET   /campo/plantillas/<id>/             una, como la edita la pantalla
    PATCH /campo/plantillas/<id>/             activar o desactivar
    POST  /campo/plantillas/<id>/publicar/    publicar una version nueva

Lo que una plantilla PUEDE contener, y por que esa lista es cerrada, esta en
`campo/plantillas.py`. Aca solo hay permisos, forma de la respuesta y errores
con texto para quien edita.

QUIEN PUEDE
-----------
Leer: cualquiera de campo. Escribir: rol de gestion, el mismo que arma las
cuadrillas -- cambiar una plantilla cambia lo que cada tecnico tiene que hacer
en cada casa a partir de la proxima orden.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo import plantillas as P
from campo.cuadrillas import labores_de
from campo.cuadrillas_views import _exigir_gestion
from campo.models import OrdenTrabajo, WorkType
from campo.permissions import IsCampoAuthenticated
from campo.services.idempotencia import manejar_idempotencia


def _error(e: P.ErrorPlantilla, estado=status.HTTP_400_BAD_REQUEST):
    return Response({"error": e.codigo, "detalle": e.mensaje}, status=estado)


def _ordenes_vivas(tipo) -> int:
    """Cuantas ordenes abiertas usan alguna version de este tipo.

    Se muestra al publicar: esas NO cambian, conservan la version con la que
    nacieron. Decirlo evita que alguien crea que su cambio ya llego a la calle.
    """
    return (OrdenTrabajo.objects
            .filter(tipo_trabajo_version__work_type=tipo)
            .exclude(estado_operativo__in=[OrdenTrabajo.CERRADA,
                                           OrdenTrabajo.CANCELADA])
            .count())


def _resumen(tipo) -> dict:
    v = P.ultima_publicada(tipo)
    editable, motivos = True, []
    if v is not None:
        definicion, motivos = P.leer_definicion(v.esquema)
        editable = definicion is not None
    return {
        "id": str(tipo.id),
        "codigo": tipo.codigo,
        "nombre": tipo.nombre,
        "labor": tipo.labor,
        #  Con que asuntos del proveedor y en cuantos dias (19/10/2026): lo
        #  que Despacho usa para llenar el formulario solo.
        "asuntos": list(tipo.asuntos or []),
        "plazo_dias": tipo.plazo_dias,
        "activo": tipo.activo,
        "version": v.version if v else None,
        "publicada_en": v.publicada_en.isoformat() if v and v.publicada_en else None,
        "datos": len((v.esquema or {}).get("campos") or []) if v else 0,
        "fotos": len((v.esquema or {}).get("evidencias") or []) if v else 0,
        "editable": editable,
        "por_que_no": motivos,
        "de_catalogo": P.base_por_codigo(tipo.codigo) is not None,
    }


def _tipo_o_404(request, pk):
    return WorkType.objects.filter(org=request.profile.org, id=pk).first()


class PlantillasView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        propias = WorkType.objects.filter(org=org).order_by("-activo", "nombre")
        codigos = set(propias.values_list("codigo", flat=True))
        return Response({
            "propias": [_resumen(t) for t in propias],
            "catalogo": [
                {"codigo": b["codigo"], "nombre": b["nombre"],
                 "labor": b["labor"], "descripcion": b["descripcion"],
                 "visitas_medidas": b["visitas_medidas"],
                 "definicion": P.definicion_de_base(b),
                 #  Adoptada = la empresa ya tiene ese codigo. Se ofrece
                 #  igual de mirar, pero no de volver a crear.
                 "adoptada": b["codigo"] in codigos}
                for b in P.CATALOGO_BASE
            ],
            "tipos": [{"id": i, "texto": t, "ayuda": a} for i, t, a in P.TIPOS],
            #  Con el nombre que les da la empresa (20/10/2026).
            "labores": labores_de(org),
        })

    @manejar_idempotencia
    def post(self, request):
        _exigir_gestion(request)
        d = request.data or {}
        try:
            tipo, version = P.crear(
                request.profile.org,
                base=str(d.get("base") or "").strip(),
                nombre=str(d.get("nombre") or ""),
                labor=str(d.get("labor") or ""),
                definicion=d.get("definicion"),
            )
        except P.ErrorPlantilla as e:
            return _error(e, status.HTTP_409_CONFLICT
                          if e.codigo == "YA_EXISTE" else status.HTTP_400_BAD_REQUEST)
        return Response(_resumen(tipo), status=status.HTTP_201_CREATED)


class PlantillaView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        tipo = _tipo_o_404(request, pk)
        if tipo is None:
            return Response({"detail": "No existe."}, status=status.HTTP_404_NOT_FOUND)
        v = P.ultima_publicada(tipo)
        definicion, motivos = (P.leer_definicion(v.esquema) if v else
                               ({"campos": [], "evidencias": []}, []))
        return Response({
            **_resumen(tipo),
            "definicion": definicion,
            "ordenes_vivas": _ordenes_vivas(tipo),
            "versiones": [
                {"version": x.version, "estado": x.estado,
                 "publicada_en": x.publicada_en.isoformat() if x.publicada_en else None}
                for x in tipo.versions.order_by("-version")[:20]
            ],
        })

    def patch(self, request, pk):
        _exigir_gestion(request)
        tipo = _tipo_o_404(request, pk)
        if tipo is None:
            return Response({"detail": "No existe."}, status=status.HTTP_404_NOT_FOUND)
        activo = request.data.get("activo")
        if not isinstance(activo, bool):
            return Response({"error": "ACTIVO_INVALIDO",
                             "detalle": "'activo' tiene que ser true o false."},
                            status=status.HTTP_400_BAD_REQUEST)
        #  Desactivar solo la saca de Despacho. Las ordenes que ya la usan
        #  siguen como estaban: apagar una plantilla no cancela trabajo.
        tipo.activo = activo
        tipo.save(update_fields=["activo"])
        return Response(_resumen(tipo))


class PublicarPlantillaView(APIView):
    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        _exigir_gestion(request)
        tipo = _tipo_o_404(request, pk)
        if tipo is None:
            return Response({"detail": "No existe."}, status=status.HTTP_404_NOT_FOUND)

        actual = P.ultima_publicada(tipo)
        if actual is not None and P.leer_definicion(actual.esquema)[0] is None:
            #  Se arma a mano con algo que el editor no maneja. Publicar encima
            #  borraria eso sin que nadie lo decida.
            return Response(
                {"error": "NO_EDITABLE",
                 "detalle": "Esta plantilla tiene cosas que el editor no maneja "
                            "y se perderian al publicar.",
                 "por_que_no": P.leer_definicion(actual.esquema)[1]},
                status=status.HTTP_409_CONFLICT)

        d = request.data or {}
        try:
            version, cambio = P.publicar(
                tipo, d.get("definicion"),
                nombre=d.get("nombre") if "nombre" in d else None,
                labor=d.get("labor") if "labor" in d else None,
                asuntos=d.get("asuntos") if "asuntos" in d else None,
                plazo_dias=d.get("plazo_dias"),
                con_plazo="plazo_dias" in d,
            )
        except P.ErrorPlantilla as e:
            return _error(e)
        tipo.refresh_from_db()
        return Response({**_resumen(tipo), "cambio": cambio,
                         "ordenes_vivas": _ordenes_vivas(tipo)})
