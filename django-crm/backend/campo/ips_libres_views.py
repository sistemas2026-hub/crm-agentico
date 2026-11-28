# -*- coding: utf-8 -*-
"""Las IP que la app le ofrece al tecnico, en la pantalla del contrato.

    GET /api/campo/trabajos/<id>/ips-libres/?zona=<id_zona>[&cuantas=20]

POR QUE VIVE AL LADO DEL CONTRATO  --  14/11/2026
-------------------------------------------------
El flujo que el tecnico ya conoce del panel del proveedor, y que el usuario
describio ese dia: **primero elige la zona, despues salen las IP disponibles y
toma cualquiera** --«puede ser cualquiera»--. La pantalla del contrato ya le
pide la zona (`contrato_views`, `id_zona` en el POST), asi que esto es el paso
siguiente de esa misma pantalla.

Y encaja con la API del proveedor, que pide la zona en la URL del alta
(`agregar-cliente/{id_zona}`): la zona se decide antes de la IP, no al reves.

OFRECER Y NO PEDIR QUE TECLEE, que es el motivo de todo este trabajo. El
usuario reporto que al digitar los datos «hay muchos errores, mala escritura
del nombre, direcciones mal digitalizadas». Una IP mal tecleada no es un error
de ortografia: es un cliente sin servicio, o dos clientes con la misma IP.

ARCHIVO PROPIO Y NO DENTRO DE `contrato_views.py`: ese lo escribio otra sesion
el 13/11 y sigue trabajando ahi. Dos sesiones en el mismo archivo es un
conflicto que no hace falta tener.
"""
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated


class IpsLibresDeLaOrdenView(APIView):
    """Solo lectura. No reserva nada: dos tecnicos pueden ver la misma.

    NO HAY RESERVA, Y ES UNA DECISION. Reservar una direccion al mostrarla
    obligaria a liberarla cuando el tecnico cierra la app, se queda sin señal o
    se arrepiente, y una reserva que no se libera es peor que una colision: la
    direccion queda muerta y nadie sabe por que.

    La colision es improbable --hay cientos libres por pool y el usuario dijo
    que cualquiera sirve-- y cuando pase, el alta la va a rechazar. Lo que SI
    hace falta es que el alta lea el resultado de esa tarea, porque el
    proveedor contesta `202` y un `task_id`, no un `400`.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, pk):
        from campo.services import ips_libres
        from campo.views import _obtener_orden_o_404

        orden = _obtener_orden_o_404(request, pk)
        zona = request.query_params.get("zona")
        if not str(zona or "").strip():
            #  200 y lista vacia, no 400: la pantalla abre ANTES de que el
            #  tecnico elija la zona, y un error ahi se veria como una falla.
            return Response({
                "libres": [],
                "motivo": "elegí primero la zona",
                "advertencia": "", "actualizado_en": None,
                "zona_nombre": "", "prefijos": [],
            })

        datos = ips_libres.para_la_zona(
            orden.org, zona, request.query_params.get("cuantas")
            or ips_libres.CUANTAS_POR_DEFECTO)
        return Response(datos)
