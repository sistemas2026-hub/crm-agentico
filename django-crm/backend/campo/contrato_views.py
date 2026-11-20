"""El contrato del cliente, desde la app y desde la plataforma (13/11/2026).

    GET  /api/campo/trabajos/<id>/contrato/   el borrador (o el ya firmado) y los servidores
    POST /api/campo/trabajos/<id>/contrato/   firmar: {cliente, plan, id_zona, gps, firma_png_base64}
    GET  /api/campo/contratos/<id>/pdf/       el PDF firmado
    GET  /api/campo/contrato/configuracion/   lo que la empresa pone en su contrato (gestion)
    PUT  /api/campo/contrato/configuracion/   {nit, servidores:[{id_zona,nombre}], texto_condiciones}

Ver `campo/contrato.py` para el porque de cada decision.

FIRMAR EXIGE SEÑAL, Y ES A PROPOSITO. La app NO encola el contrato: crear un
cliente es algo que no se puede mandar «despues» sin que nadie mire, y esto es
el primer paso de ese alta. Sin red, la app lo dice y deja el boton para cuando
vuelva.
"""
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.cuadrillas_views import _exigir_gestion
from campo.permissions import IsCampoAuthenticated

#: Cuantos servidores puede declarar una empresa. Son los del ISP, no miles.
MAXIMO_SERVIDORES = 20
MAXIMO_CONDICIONES = 20000


def _orden(request, pk):
    from campo.views import _obtener_orden_o_404

    return _obtener_orden_o_404(request, pk)


class ContratoDeLaOrdenView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.contrato import (ContratoDeServicio, borrador,
                                    configuracion_de)

        orden = _orden(request, pk)
        config = configuracion_de(orden.org)
        firmado = ContratoDeServicio.objects.filter(orden=orden).first()
        return Response({
            "contrato": firmado.como_dict() if firmado else None,
            "borrador": None if firmado else borrador(orden),
            "servidores": config["servidores"],
            "condiciones_cargadas": bool(config["texto_condiciones"].strip()),
            "empresa": getattr(orden.org, "name", "") or "",
        })

    def post(self, request, pk):
        from campo.contrato import ContratoInvalido, firmar

        orden = _orden(request, pk)
        try:
            contrato, creado = firmar(orden, request.profile, request.data or {})
        except ContratoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"contrato": contrato.como_dict()},
                        status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class PdfDelContratoView(APIView):
    """El PDF firmado. Lo abre quien puede abrir la orden: su tecnico, o gestion."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.contrato import ContratoDeServicio

        org = getattr(request, "org", None)
        contrato = (ContratoDeServicio.objects.filter(pk=pk, org=org)
                    .select_related("orden").first()) if org else None
        if contrato is None or not contrato.pdf:
            raise Http404
        _orden(request, contrato.orden_id)   # 404 si quien pide no ve la orden
        respuesta = FileResponse(contrato.pdf.open("rb"), content_type="application/pdf")
        respuesta["Content-Disposition"] = f'inline; filename="{contrato.numero}.pdf"'
        respuesta["X-Content-Type-Options"] = "nosniff"
        respuesta["Cache-Control"] = "private, no-store"
        return respuesta


def _servidores_validos(valor):
    """La lista tal como la guarda la base, o un texto de error."""
    if not isinstance(valor, list) or len(valor) > MAXIMO_SERVIDORES:
        return None, f"Los servidores son una lista de hasta {MAXIMO_SERVIDORES}."
    limpios, vistos = [], set()
    for s in valor:
        if not isinstance(s, dict):
            return None, "Cada servidor lleva su número de zona y su nombre."
        idz = s.get("id_zona")
        nombre = str(s.get("nombre") or "").strip()
        if isinstance(idz, bool) or not isinstance(idz, int) or idz <= 0:
            return None, "El número de zona de WispHub es un entero positivo."
        if not nombre or len(nombre) > 80:
            return None, "Cada servidor necesita un nombre de hasta 80 caracteres."
        if idz in vistos:
            return None, "Hay dos servidores con el mismo número de zona."
        vistos.add(idz)
        limpios.append({"id_zona": idz, "nombre": nombre})
    return limpios, ""


class ConfiguracionDeContratoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo.contrato import configuracion_de

        _exigir_gestion(request)
        return Response(configuracion_de(request.profile.org))

    def put(self, request):
        from campo.contrato import ConfiguracionDeContrato

        _exigir_gestion(request)
        datos = request.data or {}
        cambios = {}
        if "nit" in datos:
            nit = datos["nit"]
            if not isinstance(nit, str) or len(nit.strip()) > 80:
                return Response({"detail": "El NIT es un texto de hasta 80 caracteres."},
                                status=status.HTTP_400_BAD_REQUEST)
            cambios["nit"] = nit.strip()
        if "servidores" in datos:
            limpios, error = _servidores_validos(datos["servidores"])
            if error:
                return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
            cambios["servidores"] = limpios
        if "texto_condiciones" in datos:
            t = datos["texto_condiciones"]
            if not isinstance(t, str) or len(t) > MAXIMO_CONDICIONES:
                return Response({"detail": "Las condiciones son un texto de hasta "
                                           f"{MAXIMO_CONDICIONES} caracteres."},
                                status=status.HTTP_400_BAD_REQUEST)
            cambios["texto_condiciones"] = t.strip()

        fila, _ = ConfiguracionDeContrato.objects.get_or_create(org=request.profile.org)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        if cambios:
            fila.save(update_fields=list(cambios) + ["updated_at"])
        return Response(fila.como_dict())
