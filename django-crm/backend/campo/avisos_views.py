# -*- coding: utf-8 -*-
"""La API que usa la pantalla de configuracion de avisos.

POR QUE HAY PANTALLA Y NO ALCANZA CON UNA FILA EN LA BASE
---------------------------------------------------------
La regla del proyecto no dice «configuracion por empresa»: dice **configuracion
editable desde la interfaz y persistida por tenant, nunca un valor fijo en
codigo NI en un archivo que solo un desarrollador sabe editar**. Una fila que
solo se carga por consola es la misma falla con otra cara -- la empresa numero
dos necesitaria una sesion de programacion para pegar una URL.

DOS COSAS QUE ESTA API HACE Y NO SON OBVIAS
-------------------------------------------
1. **El destino no vuelve.** En un webhook, esa URL ES la credencial: cualquiera
   con ella publica en el espacio. La pantalla recibe una pista --los ultimos
   caracteres-- que alcanza para distinguir «este es el del grupo norte» sin que
   el valor entero viaje al navegador cada vez que alguien abre la pagina. Mismo
   criterio que la pantalla de credenciales del asistente.

2. **Hay boton de probar, y recorre el mismo camino que un aviso de verdad.**
   Pegar una URL y no saber si sirve es como se pudren estas configuraciones:
   alguien la carga, nadie la prueba, y el dia que hay una devolucion el aviso no
   llega y nadie sabe desde cuando.
"""

from __future__ import annotations

from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.avisos import CanalDeAvisos, ConfiguracionDeAvisos
from campo.permissions import IsCampoAuthenticated, ROLES_GESTION
from campo.services import avisos as servicio


def _puede_configurar(request) -> bool:
    """Quien toca esto.

    No es cualquiera con sesion de campo: un webhook es una credencial y su
    destino decide a donde sale informacion de la empresa. Mismo criterio que el
    resto de la configuracion.
    """
    rol = (getattr(request.profile, "role", "") or "").upper()
    return rol == "ADMIN" or rol in ROLES_GESTION


def _como_se_ve(canal: CanalDeAvisos) -> dict:
    """Lo que la pantalla necesita. El destino NO va completo."""
    return {
        "id": str(canal.id),
        "tipo": canal.tipo,
        "tipo_nombre": canal.get_tipo_display(),
        "nombre": canal.nombre,
        # Nunca el valor entero: ver el encabezado.
        "pista": canal.pista,
        "activo": canal.activo,
        "probado_en": canal.probado_en.isoformat() if canal.probado_en else None,
        "ultimo_error": canal.ultimo_error,
    }


class CanalesDeAvisosView(APIView):
    """Listar, crear y configurar los canales de esta empresa."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        config = ConfiguracionDeAvisos.objects.filter(org=request.org).first()
        canales = CanalDeAvisos.objects.filter(org=request.org)
        return Response(
            {
                "canales": [_como_se_ve(c) for c in canales],
                "url_base_app": config.url_base_app if config else "",
                # Que tipos existen lo dice el BACKEND, no una lista escrita en
                # el frontend: el dia que se agregue Mattermost aparece solo.
                "tipos": [
                    {"valor": v, "nombre": n} for v, n in CanalDeAvisos.TIPOS
                ],
                "puede_configurar": _puede_configurar(request),
            }
        )

    def post(self, request):
        if not _puede_configurar(request):
            return Response(
                {"detail": "Solo gestión puede configurar los avisos."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tipo = (request.data.get("tipo") or "").strip()
        if tipo not in dict(CanalDeAvisos.TIPOS):
            return Response(
                {"detail": f"Tipo '{tipo}' desconocido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        destino = (request.data.get("destino") or "").strip()
        if not destino:
            return Response(
                {"detail": "Pegá la URL del webhook o la dirección de correo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Una validacion mínima, y con el motivo a la vista: un webhook que no
        # empieza con https se guardaria igual y fallaría recién el día de la
        # primera devolución.
        if tipo == CanalDeAvisos.CORREO:
            if "@" not in destino:
                return Response(
                    {"detail": "Eso no parece una dirección de correo."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif not destino.startswith("https://"):
            return Response(
                {"detail": "El webhook tiene que empezar con https://."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if CanalDeAvisos.objects.filter(org=request.org, destino=destino).exists():
            # 409 y no 400: el dato esta bien, el estado no lo permite. Avisar
            # dos veces al mismo lugar es como se logra que dejen de leerlos.
            return Response(
                {"detail": "Ese destino ya está cargado."},
                status=status.HTTP_409_CONFLICT,
            )

        canal = CanalDeAvisos.objects.create(
            org=request.org,
            tipo=tipo,
            nombre=(request.data.get("nombre") or "").strip()[:80],
            destino=destino,
            activo=True,
        )
        return Response(_como_se_ve(canal), status=status.HTTP_201_CREATED)

    def put(self, request):
        """El dominio de los enlaces, que es de la empresa y no de un canal."""
        if not _puede_configurar(request):
            return Response(
                {"detail": "Solo gestión puede configurar los avisos."},
                status=status.HTTP_403_FORBIDDEN,
            )

        url = (request.data.get("url_base_app") or "").strip()
        if url and not url.startswith("https://"):
            return Response(
                {"detail": "El dominio tiene que empezar con https://."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config, _ = ConfiguracionDeAvisos.objects.update_or_create(
            org=request.org, defaults={"url_base_app": url}
        )
        return Response({"url_base_app": config.url_base_app})


class CanalDeAvisosView(APIView):
    """Un canal: apagarlo, borrarlo o probarlo."""

    permission_classes = [IsCampoAuthenticated]

    def _canal(self, request, pk) -> CanalDeAvisos:
        canal = CanalDeAvisos.objects.filter(org=request.org, id=pk).first()
        if canal is None:
            # Se filtra por org SIEMPRE: con solo el id, una empresa podria
            # apagarle los avisos a otra.
            raise Http404("Ese canal no existe en esta empresa.")
        return canal

    def patch(self, request, pk):
        if not _puede_configurar(request):
            return Response(
                {"detail": "Solo gestión puede configurar los avisos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        canal = self._canal(request, pk)

        if "activo" in request.data:
            canal.activo = bool(request.data["activo"])
        if "nombre" in request.data:
            canal.nombre = (request.data.get("nombre") or "").strip()[:80]
        canal.save(update_fields=["activo", "nombre", "updated_at"])
        return Response(_como_se_ve(canal))

    def delete(self, request, pk):
        if not _puede_configurar(request):
            return Response(
                {"detail": "Solo gestión puede configurar los avisos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        self._canal(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProbarCanalView(APIView):
    """Manda un mensaje de prueba por ese canal, ahora.

    Es el boton que evita que esto se pudra: recorre el MISMO camino que un
    aviso de verdad, asi que si llega la prueba, llega el aviso.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        if not _puede_configurar(request):
            return Response(
                {"detail": "Solo gestión puede configurar los avisos."},
                status=status.HTTP_403_FORBIDDEN,
            )

        canal = CanalDeAvisos.objects.filter(org=request.org, id=pk).first()
        if canal is None:
            raise Http404("Ese canal no existe en esta empresa.")

        ok, error = servicio.probar(canal)
        # 200 aunque no haya llegado: la PRUEBA se ejecutó bien, y su resultado
        # es el cuerpo. Un 500 acá haría que la pantalla diga «falló la página»
        # cuando lo que falló fue el webhook de la empresa.
        return Response({"llego": ok, "error": error, **_como_se_ve(canal)})
