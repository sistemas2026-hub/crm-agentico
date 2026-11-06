# -*- coding: utf-8 -*-
"""
================================================================================
 QUE LE DEVUELVE LA MIRADA AL TECNICO, EN EL SITIO  --  06/11/2026
================================================================================
MEDIDO ESE DIA, no supuesto. Una orden cerro con las cuatro fotos marcadas
"no es lo que se pidio", y la sospecha fue que el analisis se equivocaba.
Se comparo la misma foto con y sin degradar (`comparar_calidad_vision`):

    test_de_velocidad, como hoy     -> MUESTRA: no
    test_de_velocidad, sin degradar -> MUESTRA: no
    "la imagen es la pantalla de un sistema de gestion de tickets con un
     mapa, sin equipos ni instalacion de telecomunicaciones"

El analisis NO se equivocaba. El tecnico habia subido una captura de pantalla
del sistema de tickets en el lugar del test de velocidad. Las cuatro estaban
mal de verdad.

EL PROBLEMA ENTONCES NO ES LA MIRADA, ES CUANDO LLEGA
------------------------------------------------------
El analisis corre en el servidor cuando la foto ya subio. Para cuando alguien
lo lee, el tecnico se fue de la casa del cliente y la foto no se puede
rehacer: la orden se devuelve, el tecnico vuelve a la vivienda, el cliente
tiene que estar. Por una foto.

Si se lo dijera EN EL SITIO, la rehace en diez segundos.

QUE HACE ESTO
-------------
Una ruta que la app consulta despues de subir una foto. Devuelve lo que el
analisis concluyo, en la forma mas corta que sirve para decidir: si la foto
corresponde, y cuando no, la frase del modelo que lo explica.

LO QUE NO HACE, A PROPOSITO
---------------------------
**No bloquea nada.** Si no hay señal, si el analisis todavia no corrio, si la
empresa lo tiene apagado: contesta `listo: false` y el tecnico sigue
trabajando igual. Una foto que no se pudo mirar no puede frenar un cierre --
es la misma regla que `punto_de_la_revision`, que nunca devuelve `ok=False`
por no haber podido mirar.

**No decide por el tecnico.** Le dice lo que el modelo vio; rehacer la foto es
decision suya. Un modelo que se equivoca --y se equivoca-- no puede obligar a
nadie a repetir un trabajo bien hecho.

**No espera.** Contesta con lo que hay en ese instante. Quien pregunta decide
si vuelve a preguntar; mantener la conexion abierta mientras el modelo piensa
gastaria el dato del telefono de un tecnico en la calle.
================================================================================
"""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated

#: Cuanto del texto del modelo se le muestra. Lo util es la primera frase --el
#: modelo arranca por la conclusion-- y el resto es la descripcion larga, que
#: en la pantalla de un telefono bajo el sol no se lee.
MAX_RESUMEN = 220


def _resumen(texto: str) -> str:
    """La frase que le sirve al tecnico, sin las marcas del protocolo.

    `MUESTRA:` y `ATENCION:` son como el codigo habla consigo mismo. Mostrarlas
    en la app seria filtrar la plomeria a quien tiene que decidir si vuelve a
    sacar una foto.
    """
    lineas = []
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        bajo = limpia.lower()
        if bajo.startswith(("muestra:", "atencion:", "atención:")):
            continue
        lineas.append(limpia)
    junto = " ".join(lineas).strip()
    if len(junto) <= MAX_RESUMEN:
        return junto
    #  Se corta en el ultimo punto que entre, no a la mitad de una palabra.
    recorte = junto[:MAX_RESUMEN]
    corte = recorte.rfind(". ")
    return (recorte[:corte + 1] if corte > 60 else recorte.rstrip() + "…")


class AnalisisDeLaFotoView(APIView):
    """Lo que la mirada concluyo de UNA foto, para la app del tecnico.

    `GET /api/campo/evidencias/<pk>/analisis/`

    Siempre 200. Que la foto no se haya podido mirar no es un error de esta
    peticion: es una respuesta, y la app tiene que poder distinguirla de un
    fallo de red.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.analisis_de_evidencia import AnalisisDeEvidencia
        from campo.inspeccion_visual import que_tenia_que_mostrar
        from campo.models import EvidenciaTrabajo
        from campo.tasks import muestra_lo_pedido
        from campo.views import _debe_estar_asignado

        #  EL MISMO AISLAMIENTO QUE EL RESTO, no uno nuevo: la empresa sale de
        #  la sesion y, si no es gestion, la orden tiene que estar asignada a
        #  quien pregunta. Una ruta de lectura que se saltea eso deja ver el
        #  trabajo de otro.
        evidencias = EvidenciaTrabajo.objects.select_related(
            "orden_trabajo").filter(org=request.org, pk=pk)
        if _debe_estar_asignado(request):
            evidencias = evidencias.filter(
                orden_trabajo__asignaciones__profile=request.profile)
        evidencia = evidencias.first()
        if evidencia is None:
            #  404 y no 403: quien no tiene por que verla tampoco tiene por
            #  que saber que existe.
            return Response({"detail": "No encontrada."}, status=404)

        #  LA MAS RECIENTE, que puede ser la correccion de una persona. Si
        #  alguien ya dijo que la foto si corresponde, eso le gana al modelo.
        fila = (AnalisisDeEvidencia.objects
                .filter(org=request.org, evidencia=evidencia)
                .order_by("-created_at").first())

        if fila is None:
            return Response({
                "listo": False,
                "motivo": "todavia no se miro",
                "que_se_pidio": que_tenia_que_mostrar(evidencia),
            })

        corresponde = muestra_lo_pedido(fila.texto)
        return Response({
            "listo": True,
            #  TRES VALORES, no un booleano: `null` es "no se sabe", y es
            #  distinto de "no corresponde". Mostrar una duda como un rechazo
            #  mandaria al tecnico a rehacer una foto que esta bien.
            "corresponde": corresponde,
            "resumen": _resumen(fila.texto),
            "que_se_pidio": que_tenia_que_mostrar(evidencia),
            "pide_atencion": bool(fila.pide_atencion),
            #  Para que la app no vuelva a preguntar por algo que ya es final.
            "lo_dijo": fila.origen,
            "motivo": fila.motivo or "",
        })
