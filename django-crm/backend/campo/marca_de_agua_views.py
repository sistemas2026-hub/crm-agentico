"""Lo que la empresa decide sobre la marca de agua de sus fotos (12/11/2026).

    GET  /api/campo/marca-de-agua/configuracion/   como está
    PUT  /api/campo/marca-de-agua/configuracion/   {"activa": bool, ...}

Editable desde Programación (CLAUDE.md §3.3: lo que varía por empresa se edita
desde la interfaz, no en un YAML ni en código). Solo quien gestiona.

EL LOGO Y EL NOMBRE NO SE EDITAN ACÁ. Salen de `Org`, que ya tiene su pantalla
en `/settings/organization`. Esta vista los DEVUELVE en el GET --para que el
formulario pueda mostrar la vista previa y avisar si falta el logo-- pero no
los escribe: dos lugares para cargar el mismo logo es un logo que diverge.
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.cuadrillas_views import _exigir_gestion
from campo.marca_de_agua import CAMPOS_SI_NO, POSICIONES
from campo.permissions import IsCampoAuthenticated

CAMPOS_TEXTO = ("posicion", "texto_extra")
CAMPOS = CAMPOS_SI_NO + CAMPOS_TEXTO + ("opacidad",)

#: De 10 a 100. Por abajo de 10 la banda no se ve y la empresa creería que la
#: marca no funciona; por arriba de 100 no existe.
OPACIDAD_MIN, OPACIDAD_MAX = 10, 100


def _como_esta(org) -> dict:
    from campo.marca_de_agua import ConfiguracionDeMarcaDeAgua

    fila = ConfiguracionDeMarcaDeAgua.objects.filter(org=org).first()
    if fila is None:
        fila = ConfiguracionDeMarcaDeAgua(org=org)
    datos = {c: getattr(fila, c) for c in CAMPOS}

    #  LO QUE LA PANTALLA NECESITA PARA NO MENTIR. Si la empresa prende «el
    #  logo» y no cargó ninguno, la marca sale sin logo y nadie entiende por
    #  qué. El formulario lo puede decir antes, con esto.
    logo = getattr(org, "logo", None)
    datos["logo_cargado"] = bool(logo)
    datos["empresa"] = getattr(org, "name", "") or ""
    return datos


def _version_del_logo(org) -> str | None:
    """Una huella corta del logo, o None si la empresa no cargó ninguno.

    La app guarda el logo para trabajar sin señal y lo vuelve a bajar solo
    cuando esto cambia. Sale del nombre y el tamaño, no de leer los bytes: se
    pide cada vez que el técnico abre una orden, y leer hasta 2 MB por pedido
    para contestar «es el mismo» no tiene sentido. Subir otro logo cambia el
    nombre (el storage de Django no pisa archivos), así que la huella cambia.
    """
    import hashlib

    logo = getattr(org, "logo", None)
    if not logo:
        return None
    try:
        tamano = logo.size
    except Exception:                                            # noqa: BLE001
        tamano = 0
    return hashlib.sha256(f"{logo.name}:{tamano}".encode()).hexdigest()[:12]


class MarcaDeAguaParaLaAppView(APIView):
    """``GET /api/campo/marca-de-agua/`` — lo que el teléfono necesita para
    pintar la marca encima de la foto que el técnico acaba de tomar.

    POR QUÉ EXISTE  --  13/11/2026. Pedido del usuario: que la marca se vea en
    el teléfono al tomar la foto, no recién en la plataforma. El servidor
    sigue siendo el ÚNICO que estampa el archivo: si la app también lo hiciera,
    la foto saldría con dos bandas, y aceptar «ya viene marcada» le daría al
    teléfono la forma de apagar la marca que lo certifica (el mismo agujero que
    H3 cerró con el mime). La app solo DIBUJA ENCIMA, con esta misma
    configuración, para que el técnico vea lo que va a quedar.

    Cualquier persona de campo de la empresa la puede leer --no es gestión--:
    no trae nada que la propia foto no vaya a mostrar. `tecnico` es el nombre
    de quien pregunta, por la misma regla que usa el estampado
    (`nombre_para_la_marca`): nunca el correo.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        from campo.marca_de_agua import configuracion_de, nombre_para_la_marca

        org = request.profile.org
        return Response({
            "configuracion": configuracion_de(org),
            "empresa": getattr(org, "name", "") or "",
            "tecnico": nombre_para_la_marca(request.profile),
            "logo_version": _version_del_logo(org),
        })


class LogoParaLaMarcaView(APIView):
    """``GET /api/campo/marca-de-agua/logo/`` — los bytes del logo de la
    empresa de quien pregunta. 404 si no hay.

    Lee el `FileField` de la empresa del perfil, nunca una ruta que mande el
    cliente: no hay forma de pedir el logo de otra empresa, porque no hay nada
    que apuntar (la misma razón que `_logo_de`).
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        import mimetypes

        from django.http import Http404, HttpResponse

        from campo.marca_de_agua import _logo_de

        org = request.profile.org
        contenido = _logo_de(org)
        if not contenido:
            raise Http404
        tipo = mimetypes.guess_type(org.logo.name)[0] or "application/octet-stream"
        respuesta = HttpResponse(contenido, content_type=tipo)
        respuesta["X-Content-Type-Options"] = "nosniff"
        respuesta["Cache-Control"] = "private, max-age=0"
        return respuesta


class ConfiguracionDeMarcaDeAguaView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        _exigir_gestion(request)
        return Response(_como_esta(request.profile.org))

    def put(self, request):
        from campo.marca_de_agua import ConfiguracionDeMarcaDeAgua

        _exigir_gestion(request)
        datos = request.data or {}
        cambios = {c: datos[c] for c in CAMPOS if c in datos}

        for c in CAMPOS_SI_NO:
            if c in cambios and not isinstance(cambios[c], bool):
                return Response(
                    {"detail": "Cada casilla tiene que ser verdadera o falsa."},
                    status=status.HTTP_400_BAD_REQUEST)

        if "posicion" in cambios:
            validas = [v for v, _ in POSICIONES]
            if cambios["posicion"] not in validas:
                return Response(
                    {"detail": f"La posición tiene que ser una de {validas}."},
                    status=status.HTTP_400_BAD_REQUEST)

        if "opacidad" in cambios:
            v = cambios["opacidad"]
            #  `isinstance(True, int)` es True en Python: sin el primer
            #  chequeo, un `true` pasaría como opacidad 1.
            if (isinstance(v, bool) or not isinstance(v, int)
                    or not (OPACIDAD_MIN <= v <= OPACIDAD_MAX)):
                return Response(
                    {"detail": f"La opacidad va de {OPACIDAD_MIN} a "
                               f"{OPACIDAD_MAX}."},
                    status=status.HTTP_400_BAD_REQUEST)

        if "texto_extra" in cambios:
            v = cambios["texto_extra"]
            if not isinstance(v, str) or len(v) > 80:
                return Response(
                    {"detail": "El texto extra es una línea de hasta 80 "
                               "caracteres."},
                    status=status.HTTP_400_BAD_REQUEST)
            cambios["texto_extra"] = v.strip()

        org = request.profile.org
        fila, _ = ConfiguracionDeMarcaDeAgua.objects.get_or_create(org=org)
        for campo, valor in cambios.items():
            setattr(fila, campo, valor)
        if cambios:
            fila.save(update_fields=list(cambios) + ["updated_at"])
        return Response(_como_esta(org))
