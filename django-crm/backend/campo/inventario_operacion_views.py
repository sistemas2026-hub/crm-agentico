# -*- coding: utf-8 -*-
"""
API de Fase 2 y 3: reservas, traslados, conteo, compras, valorizacion, reportes.

MISMO PERMISO QUE EL RESTO DEL INVENTARIO
-----------------------------------------
`ROLES_INVENTARIO` -- gestion o bodega. Un bodeguero reserva, traslada, cuenta y
recibe compras; sigue sin poder validar ordenes de trabajo. La lectura de reportes
la puede hacer cualquiera con sesion de campo: saber en que se fue el material no
mueve nada.

LOS CODIGOS DE ERROR DICEN QUE HACER
------------------------------------
    400  el dato esta mal escrito           -> corregilo
    409  el estado del inventario no lo permite -> mira el numero o el aparato
La distincion no es cosmetica: con 400 para las dos cosas, la pantalla tiene que
adivinar cual de las dos es y termina mostrando "no se pudo" para todo.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.inventario_operacion import (
    ConteoFisico,
    PlantillaDeKit,
    Proveedor,
    ReservaDeMaterial,
)
from campo.models import OrdenTrabajo
from campo.permissions import IsCampoAuthenticated
from campo.inventario_views import (
    ROLES_INVENTARIO,
    _decimal,
    _exigir_inventario,
    _material,
    _ubicacion,
)
from campo.services import inventario as inv
from campo.services import inventario_operacion as op


def _lineas(org, crudas):
    """Normaliza las lineas de un cuerpo. Un formato, en un lugar."""
    salida = []
    for c in (crudas or []):
        salida.append({
            "material": _material(org, c.get("material")),
            "cantidad": c.get("cantidad") or 0,
            "serie": (c.get("serie") or "").strip(),
            "costo_unitario": c.get("costo_unitario"),
        })
    return salida


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{valor}' no es una fecha ISO valida.")


# ---------------------------------------------------------------------------
# Reservas
# ---------------------------------------------------------------------------

class ReservasView(APIView):
    """``GET`` lo comprometido · ``POST`` comprometer."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        u = _ubicacion(org, request.query_params.get("ubicacion"))
        if u is None:
            return Response({"detail": "Hace falta la ubicacion."},
                            status=status.HTTP_400_BAD_REQUEST)
        todas = request.query_params.get("todas") == "1"
        return Response({
            "ubicacion": {"id": str(u.id), "nombre": u.nombre},
            "reservas": op.reservas_de(u, solo_activas=not todas),
        })

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        try:
            u = _ubicacion(org, request.data.get("ubicacion"))
            material = _material(org, request.data.get("material"))
            vence = _fecha(request.data.get("vence_en"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if u is None:
            return Response({"detail": "Hace falta la ubicacion."},
                            status=status.HTTP_400_BAD_REQUEST)

        # APARTAR PARA UNA ORDEN: POR NUMERO, NO SOLO POR UUID
        # ----------------------------------------------------
        # El id existia desde siempre y nadie lo mandaba. Quien aparta material
        # es la bodega, y lo que la bodega tiene en la mano es el NUMERO de la
        # OT -- el que esta impreso en la orden y el que dice el tecnico por
        # radio--, no un UUID de 36 caracteres. Pedirle el uuid es pedirle que
        # copie algo que no tiene.
        #
        # Se aceptan los dos. El uuid sigue sirviendo para quien lo tenga (otro
        # sistema, una integracion); el numero es el camino de la persona.
        orden = None
        if request.data.get("orden"):
            orden = OrdenTrabajo.objects.filter(
                org=org, id=request.data["orden"]
            ).first()
            if orden is None:
                raise Http404("Esa orden de trabajo no existe en esta empresa.")
        elif str(request.data.get("orden_numero") or "").strip():
            numero = str(request.data["orden_numero"]).strip()
            if not numero.isdigit():
                return Response(
                    {"detail": f"'{numero}' no es un numero de orden."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            orden = OrdenTrabajo.objects.filter(org=org, numero=int(numero)).first()
            if orden is None:
                raise Http404(
                    f"La orden #{numero} no existe en esta empresa."
                )
            # Apartar material para un trabajo terminado no tiene sentido y el
            # material quedaria bloqueado hasta que alguien lo note: la propia
            # transicion que lo soltaria ya ocurrio.
            if orden.estado_operativo in (
                OrdenTrabajo.CERRADA,
                OrdenTrabajo.CANCELADA,
            ):
                return Response(
                    {
                        "detail": (
                            f"La orden #{numero} esta "
                            f"'{orden.estado_operativo}': no se puede apartar "
                            "material para un trabajo que ya termino."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        try:
            r = op.reservar(
                org=org, ubicacion=u, material=material,
                cantidad=request.data.get("cantidad"),
                serie=(request.data.get("serie") or "").strip(),
                orden=orden, reservada_por=request.profile, vence_en=vence,
                motivo=(request.data.get("motivo") or "").strip(),
            )
        except op.ReservaInvalida as e:
            # 409: el dato esta bien, no alcanza el material.
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response({
            "id": str(r.id),
            "libre_ahora": str(op.libre(u, material)),
        }, status=status.HTTP_201_CREATED)


class LiberarReservaView(APIView):
    """``POST`` una reserva deja de bloquear material. La fila no se borra."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        _exigir_inventario(request)
        org = request.profile.org
        r = ReservaDeMaterial.objects.filter(org=org, id=pk).first()
        if r is None:
            raise Http404("Esa reserva no existe en esta empresa.")
        op.liberar(r, motivo=(request.data.get("motivo") or "").strip())
        return Response({
            "id": str(r.id),
            "desenlace": r.desenlace,
            "libre_ahora": str(op.libre(r.ubicacion, r.material)),
        })


class LibreView(APIView):
    """``GET`` existencia, reservado y libre de una ubicacion.

    Las tres juntas y no solo `libre`: "quedan 70" sin decir que hay 100 y 30
    comprometidos obliga a abrir otra pantalla para entender el numero.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        u = _ubicacion(org, request.query_params.get("ubicacion"))
        if u is None:
            return Response({"detail": "Hace falta la ubicacion."},
                            status=status.HTTP_400_BAD_REQUEST)

        filas = []
        for fila in inv.existencias_de(u):
            material = _material(org, fila["codigo"])
            filas.append({
                **fila,
                "reservado": str(op.reservado(u, material)),
                "libre": str(op.libre(u, material)),
            })
        return Response({
            "ubicacion": {"id": str(u.id), "nombre": u.nombre, "tipo": u.tipo},
            "materiales": filas,
        })


# ---------------------------------------------------------------------------
# Traslados
# ---------------------------------------------------------------------------

class TrasladosView(APIView):
    """``POST`` mover material entre ubicaciones internas."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        try:
            origen = _ubicacion(org, request.data.get("ubicacion_origen"))
            destino = _ubicacion(org, request.data.get("ubicacion_destino"))
            lineas = _lineas(org, request.data.get("lineas"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            movs = op.trasladar(
                org=org, ubicacion_origen=origen, ubicacion_destino=destino,
                lineas=lineas, profile=request.profile,
                motivo=(request.data.get("motivo") or "").strip(),
                # El numero de la hoja de ruta, si existe: es lo que hace que
                # reenviar el formulario no traslade dos veces. Sin el, el
                # traslado se registra igual y su clave queda marcada como no
                # protegida -- ver `_clave_de_hecho` en services/inventario.py.
                referencia=(request.data.get("referencia") or "").strip(),
            )
        except inv.DespachoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"movimientos": [str(m.id) for m in movs]},
                        status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Conteo fisico
# ---------------------------------------------------------------------------

class ConteosView(APIView):
    """``GET`` los conteos · ``POST`` abrir uno."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        filas = []
        for c in ConteoFisico.objects.filter(org=org).select_related("ubicacion"):
            filas.append({
                "id": str(c.id),
                "ubicacion": c.ubicacion.nombre,
                "estado": c.estado,
                "iniciado_en": c.iniciado_en.isoformat(),
                "cerrado_en": c.cerrado_en.isoformat() if c.cerrado_en else None,
                "lineas": c.lineas.count(),
            })
        return Response({"conteos": filas})

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        u = _ubicacion(org, request.data.get("ubicacion"))
        if u is None:
            return Response({"detail": "Hace falta la ubicacion."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            c = op.abrir_conteo(
                org=org, ubicacion=u, contado_por=request.profile,
                notas=(request.data.get("notas") or "").strip(),
            )
        except op.ConteoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"id": str(c.id), "estado": c.estado},
                        status=status.HTTP_201_CREATED)


class AnotarConteoView(APIView):
    """``POST`` lo que se conto de un material."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        _exigir_inventario(request)
        org = request.profile.org
        conteo = ConteoFisico.objects.filter(org=org, id=pk).first()
        if conteo is None:
            raise Http404("Ese conteo no existe en esta empresa.")
        try:
            material = _material(org, request.data.get("material"))
            cantidad = Decimal(str(request.data.get("cantidad") or 0))
        except (ValueError, InvalidOperation) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            op.anotar_conteo(
                conteo, material=material, cantidad=cantidad,
                motivo=(request.data.get("motivo") or "").strip(),
            )
        except op.ConteoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


class CerrarConteoView(APIView):
    """``POST`` congela las diferencias y escribe los ajustes."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request, pk):
        _exigir_inventario(request)
        org = request.profile.org
        conteo = ConteoFisico.objects.filter(org=org, id=pk).first()
        if conteo is None:
            raise Http404("Ese conteo no existe en esta empresa.")
        try:
            lineas, ajustes = op.cerrar_conteo(conteo, profile=request.profile)
        except op.ConteoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response({
            "conteo": str(conteo.id),
            # Las lineas que CUADRARON viajan tambien: un conteo que solo muestra
            # diferencias no deja ver cuanto se reviso.
            "lineas": [{
                "material": l.material.codigo,
                # Cuantizado a los 3 decimales del campo. Un Decimal que sale de
                # la base llega como "100" o "100.000" segun el motor, y la
                # pantalla no tendria que normalizar tres cifras del mismo
                # renglon. Mismo criterio que services/inventario.py::PRECISION.
                "contado": str(l.cantidad_contada.quantize(inv.PRECISION)),
                "segun_sistema": str(l.existencia_sistema.quantize(inv.PRECISION)),
                "diferencia": str(
                    (l.cantidad_contada - l.existencia_sistema)
                    .quantize(inv.PRECISION)
                ),
                "ajuste": str(l.ajuste_id) if l.ajuste_id else None,
                "motivo": l.motivo,
            } for l in lineas],
            "ajustes": len(ajustes),
        })


# ---------------------------------------------------------------------------
# FASE 3 -- proveedores, compras, valorizacion
# ---------------------------------------------------------------------------

class ProveedoresView(APIView):
    """``GET`` los proveedores · ``POST`` uno nuevo."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        return Response({"proveedores": [
            {"id": str(p.id), "nombre": p.nombre,
             "identificacion": p.identificacion, "contacto": p.contacto}
            for p in Proveedor.objects.filter(org=org, activo=True)
        ]})

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        nombre = (request.data.get("nombre") or "").strip()
        if not nombre:
            return Response({"detail": "Hace falta el nombre del proveedor."},
                            status=status.HTTP_400_BAD_REQUEST)
        p, creado = Proveedor.objects.get_or_create(
            org=org, nombre=nombre,
            defaults={
                "identificacion": (request.data.get("identificacion") or "").strip(),
                "contacto": (request.data.get("contacto") or "").strip(),
            },
        )
        return Response(
            {"id": str(p.id), "nombre": p.nombre, "creado": creado},
            status=status.HTTP_201_CREATED if creado else status.HTTP_200_OK)


class ComprasView(APIView):
    """``POST`` un lote que llego, con su costo."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        try:
            destino = _ubicacion(org, request.data.get("ubicacion_destino"))
            lineas = _lineas(org, request.data.get("lineas"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        proveedor = None
        if request.data.get("proveedor"):
            proveedor = Proveedor.objects.filter(
                org=org, id=request.data["proveedor"]
            ).first()
            if proveedor is None:
                raise Http404("Ese proveedor no existe en esta empresa.")

        # Se comprueba antes para poder DECIR que factura es. El constraint
        # sigue siendo la garantia --dos peticiones a la vez pasan las dos por
        # aca-- y su IntegrityError se atrapa abajo: el nombre del constraint no
        # aparece en el mensaje de SQLite, asi que se mira la tabla.
        referencia = (request.data.get("referencia") or "").strip()
        if proveedor is not None and referencia:
            from campo.inventario_operacion import Compra
            if Compra.objects.filter(
                org=org, proveedor=proveedor, referencia=referencia
            ).exists():
                return Response(
                    {"detail": f"La factura {referencia} ya se registró para "
                               f"{proveedor.nombre}."},
                    status=status.HTTP_409_CONFLICT)

        try:
            compra, movs = op.registrar_compra(
                org=org, ubicacion_destino=destino, proveedor=proveedor,
                referencia=referencia,
                moneda=(request.data.get("moneda") or "COP").strip(),
                recibida_por=request.profile, lineas=lineas,
                notas=(request.data.get("notas") or "").strip(),
            )
        except inv.DespachoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:  # noqa: BLE001
            # Una factura repetida del mismo proveedor llega aca como
            # IntegrityError. 409 y no 500: el dato esta bien, ya existe.
            texto = str(e)
            if ("unique_factura_por_proveedor" in texto
                    or "campo_compra" in texto):
                return Response(
                    {"detail": "Esa factura ya se registró para este proveedor."},
                    status=status.HTTP_409_CONFLICT)
            raise

        return Response({
            "compra": str(compra.id),
            "movimientos": [str(m.id) for m in movs],
        }, status=status.HTTP_201_CREATED)


class ValorizacionView(APIView):
    """``GET`` cuanto vale lo que hay, y de que no se sabe."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        u = _ubicacion(org, request.query_params.get("ubicacion"))
        if u is None:
            return Response({"detail": "Hace falta la ubicacion."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(op.valorizacion(u))


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

class ReportesView(APIView):
    """``GET /inventario/reportes/?de=consumo|tecnicos|descuadres``

    Leer un reporte no mueve nada, asi que no exige rol de inventario: cualquiera
    con sesion de campo puede saber en que se fue el material.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        cual = (request.query_params.get("de") or "consumo").strip()
        try:
            desde = _fecha(request.query_params.get("desde"))
            hasta = _fecha(request.query_params.get("hasta"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if cual == "consumo":
            return Response({"de": cual,
                             "filas": op.consumo_por_material(org, desde=desde,
                                                              hasta=hasta)})
        if cual == "tecnicos":
            return Response({"de": cual,
                             "filas": op.consumo_por_tecnico(org, desde=desde,
                                                             hasta=hasta)})
        if cual == "descuadres":
            return Response({"de": cual, "filas": op.descuadres_abiertos(org)})

        return Response(
            {"detail": f"No hay un reporte '{cual}'. Los que hay: consumo, "
                       f"tecnicos, descuadres."},
            status=status.HTTP_400_BAD_REQUEST)


class PlantillasView(APIView):
    """``GET`` las plantillas de kit · ``POST`` una nueva.

    LEER NO EXIGE ROL DE INVENTARIO; ESCRIBIR SI. Saber que lleva un kit no mueve
    nada y le sirve a cualquiera que planifique el dia; armarlo es decidir que se
    entrega, y eso es gestion o bodega.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        todas = request.query_params.get("todas") == "1"
        return Response({
            "plantillas": op.plantillas_de(org, solo_activas=not todas)
        })

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        try:
            lineas = _lineas_de_plantilla(org, request.data.get("lineas"))
            p = op.guardar_plantilla(
                org=org,
                nombre=request.data.get("nombre"),
                descripcion=request.data.get("descripcion") or "",
                lineas=lineas,
            )
        except op.ConteoInvalido as e:
            # 409 y no 400: el dato esta bien escrito, lo que no se puede es
            # tener dos plantillas con el mismo nombre o una sin materiales.
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": str(p.id), "nombre": p.nombre},
                        status=status.HTTP_201_CREATED)


class PlantillaView(APIView):
    """``PUT`` reescribe una plantilla · ``DELETE`` la desactiva."""

    permission_classes = [IsCampoAuthenticated]

    def _plantilla(self, request, pk):
        p = PlantillaDeKit.objects.filter(org=request.profile.org, id=pk).first()
        if p is None:
            raise Http404("Esa plantilla no existe en esta empresa.")
        return p

    def put(self, request, pk):
        _exigir_inventario(request)
        org = request.profile.org
        plantilla = self._plantilla(request, pk)
        try:
            lineas = _lineas_de_plantilla(org, request.data.get("lineas"))
            op.guardar_plantilla(
                org=org,
                nombre=request.data.get("nombre") or plantilla.nombre,
                descripcion=request.data.get("descripcion") or "",
                lineas=lineas,
                plantilla=plantilla,
            )
        except op.ConteoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": str(plantilla.id), "nombre": plantilla.nombre})

    def delete(self, request, pk):
        _exigir_inventario(request)
        plantilla = self._plantilla(request, pk)
        op.desactivar_plantilla(plantilla)
        # 200 y no 204: la plantilla sigue existiendo, solo dejo de ofrecerse.
        return Response({"id": str(plantilla.id), "activa": False})


def _lineas_de_plantilla(org, crudas) -> list[dict]:
    """Las lineas que llegan por JSON, con su material resuelto.

    Levanta `ValueError` con el nombre del campo que esta mal, en vez de un 500:
    quien arma una plantilla escribe codigos a mano y se equivoca.
    """
    salida = []
    for linea in (crudas or []):
        salida.append({
            "material": _material(org, linea.get("material")),
            "cantidad": _decimal(linea.get("cantidad"), "cantidad"),
        })
    return salida
