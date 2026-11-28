# -*- coding: utf-8 -*-
"""Donde esta el telefono del tecnico (31/10/2026).

    POST /api/campo/ubicacion/   {latitud, longitud, medida_en, precision_m?, bateria?}

La manda la aplicacion de campo mientras hay jornada. **El servidor rechaza la
de quien no sale hoy** (`ubicacion_de_cuadrilla.registrar`): la regla de "solo
durante la jornada" no puede vivir solo en el telefono. Ver el encabezado de
`campo/ubicacion_de_cuadrilla.py`.

Una posicion rechazada devuelve 200 con `guardada: false`, no un error: para la
aplicacion no es una falla --dejo de haber jornada-- y un 4xx la haria
reintentar en un bucle que nadie necesita.

Lo que NO se registra en el log: la coordenada. Donde esta una persona es dato
de esa persona; el log dice que llego una, no donde.
"""
from __future__ import annotations

import logging

from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.permissions import IsCampoAuthenticated
from campo.services.idempotencia import manejar_idempotencia

logger = logging.getLogger(__name__)

#: Fuera de esto no es la Tierra: es un error de la aplicacion o una prueba.
LIMITES = {"latitud": (-90.0, 90.0), "longitud": (-180.0, 180.0)}

#: Lo mas corto que se acepta como motivo para pisar una ubicacion.
#:
#: No es un numero elegido por elegir: con menos de esto entra «mal», «no» o
#: un punto, y una justificacion que se satisface con tres letras no es una
#: justificacion -- es un boton con un paso de mas. Tampoco se pide un parrafo:
#: el tecnico escribe parado en la calle, con una mano.
_MINIMO_DEL_MOTIVO = 10


def _anotar(orden, profile, tipo: str, datos: dict) -> None:
    """Deja el rastro en la orden. Nunca levanta y no ensucia la transaccion.

    El `atomic` propio es un savepoint: sin el, un INSERT que falla rompe la
    transaccion de la vista y la respuesta se pierde DESPUES, por una
    bitacora. La ubicacion ya quedo escrita en el ISP; perder el rastro es
    aceptable, perder la respuesta no. Mismo criterio que
    `nota_al_isp._anotar_evento`.
    """
    from django.db import transaction

    try:
        from campo.models import EventoTrabajo

        with transaction.atomic():
            EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                         profile=profile, datos=datos or {})
    except Exception:                                           # noqa: BLE001
        logger.warning("ubicacion_del_cliente: no se pudo anotar %s", tipo)


def _coordenada(datos, nombre):
    """El valor como float, o `None` si falta o no es un numero del rango."""
    if nombre not in datos:
        return None
    try:
        v = float(datos[nombre])
    except (TypeError, ValueError):
        return None
    bajo, alto = LIMITES[nombre]
    return v if bajo <= v <= alto else None


def _entero(datos, nombre, bajo, alto):
    """Opcional: ausente o ilegible es `None`, nunca un 400. Que el telefono no
    sepa su bateria no puede costar la posicion."""
    if datos.get(nombre) is None:
        return None
    try:
        v = int(float(datos[nombre]))
    except (TypeError, ValueError):
        return None
    return v if bajo <= v <= alto else None


class UbicacionDelTecnicoView(APIView):
    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        from campo.ubicacion_de_cuadrilla import FueraDeLaJornada, registrar

        datos = request.data or {}
        latitud = _coordenada(datos, "latitud")
        longitud = _coordenada(datos, "longitud")
        if latitud is None or longitud is None:
            return Response(
                {"detail": "Hacen falta una latitud y una longitud válidas."},
                status=status.HTTP_400_BAD_REQUEST)

        #  `parse_datetime` LEVANTA ValueError con una fecha bien formada pero
        #  imposible ('2026-02-31T10:00:00'), medido el 31/10/2026. Sin esto
        #  subia a 500: la aplicacion reintentaba en bucle --justo lo que
        #  responder 200 quiso evitar-- y con DEBUG encendido la pagina de
        #  error de Django devolvia la coordenada en el cuerpo.
        try:
            medida_en = parse_datetime(str(datos.get("medida_en") or ""))
        except ValueError:
            medida_en = None
        if medida_en is None:
            medida_en = timezone.now()
        elif timezone.is_naive(medida_en):
            medida_en = timezone.make_aware(medida_en)

        try:
            registrar(
                request.profile.org, request.profile,
                latitud=latitud, longitud=longitud, medida_en=medida_en,
                precision_m=_entero(datos, "precision_m", 0, 100000),
                bateria=_entero(datos, "bateria", 0, 100),
            )
        except FueraDeLaJornada as e:
            #  Ni log con la coordenada ni 4xx: la aplicacion deja de mandar.
            #  El motivo distingue los tres casos (no sale hoy, fuera del
            #  horario, la empresa no cargo horario) para poder depurarlo sin
            #  tener que mirar donde estaba nadie.
            return Response({"guardada": False, "motivo": e.motivo})
        return Response({"guardada": True})


class UbicacionDelClienteView(APIView):
    """Deja escrita, en los sistemas del ISP, la ubicacion de la casa.

        POST /api/campo/trabajos/<id>/ubicacion-del-cliente/  {latitud, longitud}

    NO ES LA DE ARRIBA, y la diferencia importa. La de arriba es donde esta el
    TECNICO: una fila por persona, la ultima, que se pisa cada 90 segundos y no
    sale de Dexter. Esta es donde vive el CLIENTE: se escribe en los sistemas
    del ISP, queda, y la usa cualquiera que despues busque esa casa.

    POR QUE EXISTE (10/11/2026). Medido contra la instancia real: de 5.186
    equipos, **10** tienen coordenada --0,19 %--. El dato lo tiene el tecnico,
    parado en la puerta, y no habia forma de que lo dejara escrito.

    EL BOTON SOLO SE OFRECE CUANDO NO HAY UNA COORDENADA UTILIZABLE, decision
    del usuario: el campo vacio, o uno que el parser no puede leer. Esa regla
    vive en la aplicacion --es ella la que decide si dibuja el boton-- pero el
    servidor NO la hace cumplir, y eso se dice en vez de callarlo: esta vista
    escribe lo que le manden. Si alguna vez hay que impedir que se pise una
    coordenada buena, la regla tiene que bajar aca.

    PIDE CONEXION: no se encola para despues. Una escritura en un sistema de
    un tercero no se puede prometer offline --nadie sabe si va a seguir siendo
    valida en una hora-- y dejarla en la cola la convertiria en lo que se
    arreglo hoy del otro lado: algo que espera sin que nadie sepa por que.
    """

    permission_classes = [IsCampoAuthenticated]

    @manejar_idempotencia
    def post(self, request, pk):
        from campo.services import ubicacion_al_isp
        from campo.views import _obtener_orden_o_404

        orden = _obtener_orden_o_404(request, pk)
        lat = _coordenada(request.data, "latitud")
        lng = _coordenada(request.data, "longitud")
        if lat is None or lng is None:
            #  400 Y NO 200: aca si es un error de quien llama, y reintentarlo
            #  tal cual no va a cambiar nada.
            return Response(
                {"guardada": False, "codigo": "coordenada_invalida",
                 "detalle": "falta la latitud o la longitud, o no estan en el "
                            "planeta"},
                status=status.HTTP_400_BAD_REQUEST)

        #  CORREGIR NO ES LLENAR, Y LA DIFERENCIA LA HACE CUMPLIR EL SERVIDOR
        #  (11/11/2026, pedido del usuario: «cuando el tecnico le presione
        #  para corregir si esta mala, en este caso si tiene que pedir
        #  justificacion en texto»).
        #
        #  Si la orden YA tiene un punto, lo que llega lo PISA: alguien
        #  decidio que el que estaba era peor que este. Esa decision tiene que
        #  quedar con su motivo, y tiene que ser obligatoria ACA y no solo en
        #  la pantalla -- si la regla vive en el telefono, en tres meses van a
        #  existir correcciones sin motivo y nadie va a saber por que se movio
        #  una casa.
        #
        #  Llenar un vacio no pide nada: no hay decision que justificar, no se
        #  pierde nada, y pedir un texto ahi solo enseña a escribir «ok» para
        #  destrabar el boton -- que es como una justificacion obligatoria
        #  deja de significar algo.
        corrige = orden.gps_lat is not None and orden.gps_lng is not None
        motivo = str(request.data.get("motivo") or "").strip()
        if corrige and len(motivo) < _MINIMO_DEL_MOTIVO:
            return Response(
                {"guardada": False, "codigo": "motivo_requerido",
                 "detalle": "esta orden ya tiene una ubicación: para "
                            "cambiarla hay que decir por qué"},
                status=status.HTTP_400_BAD_REQUEST)

        resultado = ubicacion_al_isp.guardar_ubicacion(
            orden, latitud=lat, longitud=lng,
            profile=getattr(request, "profile", None))

        #  QUE CODIGO LLEVA CADA CASO, Y POR QUE:
        #    200  quedo escrita (entera o a medias -- el cuerpo lo dice, y una
        #         parcial se completa volviendo a llamar);
        #    400  lo que mandaron no sirve y reintentarlo tampoco serviria;
        #    409  el sistema decidio no escribir (el interruptor);
        #    502  el ISP fallo de verdad, y reintentar tiene sentido.
        if resultado.get("guardada"):
            #  Y LA ORDEN TAMBIEN, o el mapa sigue diciendo «sin ubicacion»
            #  (11/11/2026, visto en la primera prueba de campo: la coordenada
            #  quedo escrita en el ISP y la pantalla no cambio).
            #
            #  La orden congela la ficha del cliente al despachar, asi que no
            #  se entera sola de nada que pase despues. Hasta la proxima
            #  bajada el tecnico veia el punto escrito del otro lado y su
            #  propia pantalla sin ubicar.
            #
            #  Se escribe DESPUES del ISP y no antes: si el ISP rechaza, la
            #  orden no puede quedar afirmando un punto que no se guardo en
            #  ningun lado.
            try:
                orden.gps_lat = lat
                orden.gps_lng = lng
                orden.save(update_fields=["gps_lat", "gps_lng"])
                #  EL RASTRO, Y SIN LA COORDENADA. Que se corrigio, quien y
                #  por que: eso es lo que alguien va a buscar dentro de seis
                #  meses. Donde quedo la casa ya esta en la orden y en el
                #  ISP; repetirlo aca solo agrega un lugar mas con el
                #  domicilio de una persona.
                _anotar(orden, getattr(request, "profile", None),
                        "ubicacion_corregida" if corrige
                        else "ubicacion_registrada",
                        {"motivo": motivo} if corrige else {})
            except Exception as e:                       # noqa: BLE001
                #  Lo que importaba --que el ISP la tenga-- ya paso. Que la
                #  copia local no se actualice es molesto, no grave: se
                #  recupera en la proxima bajada o con
                #  `completar_coordenadas`. No se le devuelve un error al
                #  tecnico por esto.
                logger.warning(
                    "ubicacion_del_cliente: el ISP la tiene pero la orden no "
                    "se pudo actualizar (%s)", type(e).__name__)
            return Response(resultado, status=status.HTTP_200_OK)
        codigo = resultado.get("codigo") or ""
        de_quien_llama = {"coordenada_invalida", "sin_identificador",
                          "sin_actor", "sin_empresa"}
        if codigo in de_quien_llama:
            http = status.HTTP_400_BAD_REQUEST
        elif codigo in {"bloqueado_por_interruptor", "sin_herramienta"}:
            http = status.HTTP_409_CONFLICT
        else:
            http = status.HTTP_502_BAD_GATEWAY
        return Response(resultado, status=http)
