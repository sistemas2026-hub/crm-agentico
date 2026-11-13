# -*- coding: utf-8 -*-
"""
================================================================================
 UN ADJUNTO SE ABRE POR LA SESION, NO POR UNA URL PUBLICA  --  07/11/2026
================================================================================
El usuario, mirando el ticket del CRM con las fotos del tecnico ya listadas:

    «en dexter salen adjuntado los archivos pero no permiten ver»

Y al abrir una: `agent-api.rapilinksas.co/media/attachments/2026/11/
dano_encontrado-2.jpg` -> **Not Found**.

LA CAUSA, Y QUE NO ES DE LAS FOTOS. `crm/urls.py` sirve `/media/` SOLO cuando
`DEBUG` esta encendido. En produccion no lo esta, asi que Django contesta 404
a cualquier `/media/...`. No es un defecto de adjuntar fotos de campo: es que
NINGUN adjunto del CRM se podia abrir en produccion, desde siempre. Las fotos
solo lo hicieron visible, porque antes nadie abria los adjuntos.

ES EL MISMO DEFECTO QUE CAMPO YA ARREGLO el 15/10/2026 para las evidencias
(`campo/views.py::EvidenciaArchivoView`), con las mismas palabras en su
encabezado: «no habia forma de ver una foto en produccion». Aca se repite la
solucion, no el error.

POR QUE NO SE ENCIENDE `/media/` Y YA
--------------------------------------
Seria una linea. Y dejaria las fotos de la casa de un cliente --con su
direccion en el mismo ticket-- en una URL que no pide sesion: quien tuviera
el enlace la veria para siempre, y el nombre de archivo es adivinable
(`dano_encontrado-2.jpg`). CLAUDE.md §5 no lo permite y el precedente de
campo ya decidio lo contrario.

Aca cada pedido pasa por la sesion y por la empresa, y la respuesta no entra
en caches compartidas.

LA FRONTERA, Y POR QUE ES ESA
------------------------------
`IsAuthenticated + HasOrgContext` y filtro por `profile.org`: exactamente la
misma que usa la pantalla que lista el adjunto (`CaseDetailView`). Ni mas
floja --seria un agujero-- ni mas estricta, que rompería la pantalla sin que
nadie lo note hasta que un usuario legitimo vea un 404.
================================================================================
"""
from __future__ import annotations

import os

from django.http import FileResponse, Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.models import Attachments
from common.permissions import HasOrgContext

#:  Lo que se muestra EN LINEA. Todo lo demas se descarga.
#:
#:  Un `Content-Type` que el navegador ejecute (html, svg con script) servido
#:  desde el dominio de la API es XSS con la sesion del usuario adentro. La
#:  extension la eligio quien subio el archivo, asi que la decision no puede
#:  salir de ella: se parte de "se descarga" y solo esta lista levanta eso.
EN_LINEA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


class AttachmentArchivoView(APIView):
    """Devuelve el archivo de un adjunto de la empresa del que pide.

    404 --no 403-- cuando el adjunto es de otra empresa: responder "existe
    pero no podes" ya cuenta que existe.
    """

    #  REDUNDANTE CON EL MIDDLEWARE, Y SE DEJA A SABIENDAS. `RequireOrgContext`
    #  ya rechaza al anonimo antes de que esta vista corra, asi que la
    #  mutacion que borra esta linea sobrevive a las 13 guardas (medido el
    #  07/11/2026) -- no hay conducta que cambiar.
    #
    #  Se conserva porque un middleware se reordena o se saca sin que nadie
    #  mire esta vista, y lo que esta en juego son fotos de casas de clientes.
    #  CLAUDE.md §5: fail-closed, y cada capa acota sin eximir a la siguiente.
    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request, pk):
        adjunto = (Attachments.objects
                   .filter(pk=pk, org=request.profile.org)
                   .first())
        if adjunto is None or not adjunto.attachment:
            raise Http404

        try:
            ruta = adjunto.attachment.path
        except (NotImplementedError, ValueError):
            #  Un backend remoto (S3) no tiene `path`. Ahi la URL firmada del
            #  propio backend es la respuesta, y esta vista no corresponde.
            raise Http404
        if not ruta or not os.path.exists(ruta):
            raise Http404

        nombre = adjunto.file_name or os.path.basename(ruta)
        extension = os.path.splitext(nombre)[1].lower()
        tipo = EN_LINEA.get(extension)
        try:
            archivo = open(ruta, "rb")
        except OSError:
            raise Http404

        respuesta = FileResponse(
            archivo,
            content_type=tipo or "application/octet-stream",
            as_attachment=tipo is None,
            filename=nombre,
        )
        #  `private, no-store`: la foto de la casa de un cliente no queda en
        #  la cache de un proxy compartido. Mismo criterio que campo.
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
