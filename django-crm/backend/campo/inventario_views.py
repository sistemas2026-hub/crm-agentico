# -*- coding: utf-8 -*-
"""
La API del inventario: lo que hace la OFICINA, no el tecnico.

QUIEN PUEDE Y QUIEN NO
----------------------
Estas rutas son de gestion: despachar material, recibir una devolucion, dar de
alta una entrada. Ninguna la usa la app del tecnico --el tecnico consume y
devuelve desde `materiales_views.py`, con su propia sesion--.

Se agrega el rol BODEGA a los que pueden. No entra a ROLES_GESTION: un bodeguero
despacha y recibe, y NO valida ordenes de trabajo ni cierra casos. Dos permisos
distintos que se veian iguales porque no existia el primero.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.inventario import ActivoSerializado, UbicacionInventario
from campo.models import MaterialCatalogo
from campo.permissions import IsCampoAuthenticated, ROLES_GESTION
from campo.services import inventario as inv
from common.models import Profile

#: Quien puede mover inventario. Es ROLES_GESTION mas el bodeguero, y el orden
#: importa al leerlo: un bodeguero NO hereda lo que puede un supervisor.
ROLES_INVENTARIO = ROLES_GESTION | {"BODEGA"}


def _exigir_inventario(request):
    """403 si quien pide no puede mover inventario."""
    rol = (getattr(request.profile, "role", "") or "").upper()
    if rol in ROLES_INVENTARIO or request.user.is_superuser:
        return
    from rest_framework.exceptions import PermissionDenied
    raise PermissionDenied(
        "Para mover inventario hace falta un rol de gestion o de bodega."
    )


def _ubicacion(org, valor):
    if not valor:
        return None
    u = UbicacionInventario.objects.filter(org=org, id=valor).first()
    if u is None:
        raise Http404("Esa ubicacion no existe en esta empresa.")
    return u


def _material(org, valor):
    """Acepta el id o el CODIGO del material, y por eso el orden importa.

    Buscar por `id` primero parece natural y revienta: el campo es UUID y un
    codigo como 'CON-SC-APC' lanza ValidationError DENTRO del filter, antes de
    que el fallback por codigo pueda correr. Medido el 28/09/2026:

        ValueError: badly formed hexadecimal UUID string

    Asi que se prueba por codigo primero --que es como lo escribe una persona-- y
    el id se intenta solo si el valor tiene forma de UUID.
    """
    if not valor:
        raise Http404("Hace falta decir de que material se trata.")
    m = MaterialCatalogo.objects.filter(org=org, codigo=str(valor)).first()
    if m is None:
        try:
            UUID(str(valor))
        except (ValueError, AttributeError, TypeError):
            raise Http404(f"El material '{valor}' no esta en el catalogo.")
        m = MaterialCatalogo.objects.filter(org=org, id=valor).first()
    if m is None:
        raise Http404(f"El material '{valor}' no esta en el catalogo.")
    return m


def _decimal(valor, campo):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError):
        raise ValueError(f"'{campo}' tiene que ser un numero: llego '{valor}'.")


class PersonasView(APIView):
    """``GET`` a quien se le puede despachar.

    POR QUE ESTA RUTA EXISTE, si el CRM ya lista gente
    -------------------------------------------------
    `/users/get-teams-and-users/` devuelve 403 "Organization context is required"
    con el mismo JWT que estas rutas aceptan sin problema. Medido el 28/09/2026:
    la pantalla del inventario quedaba con el selector de personas vacio, o sea
    sin poder despachar, por un endpoint ajeno.

    Se expone lo minimo --id, nombre, rol-- y nada mas: un selector no necesita
    telefono ni email de nadie. Es la misma regla de las listas blancas del
    motor, aplicada a una pantalla interna.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        filas = [
            {"id": str(p.id), "nombre": inv.nombre_de(p), "rol": p.role or ""}
            for p in Profile.objects.filter(org=org, is_active=True)
                                    .select_related("user")
        ]
        return Response({"personas": sorted(filas, key=lambda f: f["nombre"])})


class UbicacionesView(APIView):
    """``GET`` las ubicaciones · ``POST`` una nueva bodega o vehiculo."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        filas = []
        for u in UbicacionInventario.objects.filter(org=org, activa=True):
            filas.append({
                "id": str(u.id),
                "tipo": u.tipo,
                "nombre": u.nombre,
                "profile": str(u.profile_id) if u.profile_id else None,
            })
        return Response({"ubicaciones": filas})

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        tipo = (request.data.get("tipo") or "").strip() or UbicacionInventario.BODEGA
        nombre = (request.data.get("nombre") or "").strip()
        if not nombre:
            return Response({"detail": "Hace falta el nombre."},
                            status=status.HTTP_400_BAD_REQUEST)
        if tipo == UbicacionInventario.TECNICO:
            # La custodia de una persona la crea el despacho, no un formulario:
            # asi no puede quedar una custodia sin dueño ni dos para el mismo.
            return Response(
                {"detail": "La custodia de un tecnico se crea al despacharle "
                           "material, no a mano."},
                status=status.HTTP_400_BAD_REQUEST)
        u = UbicacionInventario.objects.create(org=org, tipo=tipo, nombre=nombre)
        return Response({"id": str(u.id), "tipo": u.tipo, "nombre": u.nombre},
                        status=status.HTTP_201_CREATED)


class ExistenciasView(APIView):
    """``GET /api/campo/inventario/existencias/?ubicacion=<id>``

    Sin `ubicacion` devuelve TODAS las ubicaciones con sus existencias, que es lo
    que la pantalla necesita para pintar la vista general de un vistazo.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        pedida = request.query_params.get("ubicacion")
        if pedida:
            u = _ubicacion(org, pedida)
            return Response({
                "ubicacion": {"id": str(u.id), "nombre": u.nombre, "tipo": u.tipo},
                "materiales": inv.existencias_de(u),
            })

        bloques = []
        for u in UbicacionInventario.objects.filter(org=org, activa=True):
            bloques.append({
                "ubicacion": {"id": str(u.id), "nombre": u.nombre, "tipo": u.tipo},
                "materiales": inv.existencias_de(u),
            })
        return Response({"ubicaciones": bloques})


class CatalogoView(APIView):
    """``GET`` el catalogo de materiales. Lo necesita el formulario de despacho."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        filas = [
            {"id": str(m.id), "codigo": m.codigo, "nombre": m.nombre,
             "categoria": m.categoria, "clase": m.clase, "unidad": m.unidad,
             "es_serializado": m.es_serializado}
            for m in MaterialCatalogo.objects.filter(org=org, activo=True)
        ]
        return Response({"materiales": filas})


class EntradasView(APIView):
    """``POST`` material que entra al sistema: una compra, o un equipo retirado."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org
        try:
            material = _material(org, request.data.get("material"))
            destino = _ubicacion(org, request.data.get("ubicacion_destino"))
            cantidad = _decimal(request.data.get("cantidad") or 0, "cantidad")
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mov = inv.registrar_entrada(
                org=org, material=material, cantidad=cantidad,
                ubicacion_destino=destino,
                serie=(request.data.get("serie") or "").strip(),
                origen_ref=(request.data.get("origen_ref") or "").strip(),
                profile=request.profile,
            )
        except inv.DespachoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "movimiento": str(mov.id),
            "existencia": str(inv.existencia(destino, material)
                              .quantize(inv.PRECISION)),
        }, status=status.HTTP_201_CREATED)


class DespachosView(APIView):
    """``POST`` el kit que sale de la bodega hacia un tecnico.

    El eslabon que faltaba: hasta ahora `KitView` solo tenia `get`, asi que nadie
    podia crear una entrega y el modulo entero colgaba de una tabla que nada
    llenaba.
    """

    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org

        destino_id = request.data.get("profile_destino")
        tecnico = Profile.objects.filter(org=org, id=destino_id).first()
        if tecnico is None:
            return Response({"detail": "Esa persona no esta en esta empresa."},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            origen = _ubicacion(org, request.data.get("ubicacion_origen"))
            lineas = []
            for cruda in (request.data.get("lineas") or []):
                lineas.append({
                    "material": _material(org, cruda.get("material")),
                    "cantidad": cruda.get("cantidad") or 0,
                    "serie": (cruda.get("serie") or "").strip(),
                })
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entrega, movs = inv.despachar(
                org=org, ubicacion_origen=origen, profile_destino=tecnico,
                lineas=lineas, despachado_por=request.profile,
                acta=(request.data.get("acta") or "").strip(),
                notas=(request.data.get("notas") or "").strip(),
            )
        except inv.DespachoInvalido as e:
            # 409 y no 400: no es un formulario mal llenado, es que el estado del
            # inventario no permite ese despacho AHORA. La distincion le dice a
            # la pantalla si corregir el dato o mirar donde esta el aparato.
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response({
            "entrega": str(entrega.id),
            "acta": entrega.acta,
            "movimientos": [str(m.id) for m in movs],
        }, status=status.HTTP_201_CREATED)


class DevolucionesView(APIView):
    """``POST`` lo que un tecnico devuelve a la bodega."""

    permission_classes = [IsCampoAuthenticated]

    def post(self, request):
        _exigir_inventario(request)
        org = request.profile.org

        tecnico = Profile.objects.filter(
            org=org, id=request.data.get("profile_origen")
        ).first()
        if tecnico is None:
            return Response({"detail": "Esa persona no esta en esta empresa."},
                            status=status.HTTP_404_NOT_FOUND)

        try:
            destino = _ubicacion(org, request.data.get("ubicacion_destino"))
            lineas = [
                {"material": _material(org, c.get("material")),
                 "cantidad": c.get("cantidad") or 0,
                 "serie": (c.get("serie") or "").strip()}
                for c in (request.data.get("lineas") or [])
            ]
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            movs = inv.recibir_devolucion(
                org=org, profile_origen=tecnico, ubicacion_destino=destino,
                lineas=lineas, recibida_por=request.profile,
                notas=(request.data.get("notas") or "").strip(),
            )
        except inv.DespachoInvalido as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        return Response({"movimientos": [str(m.id) for m in movs]},
                        status=status.HTTP_201_CREATED)


class HistoriaDeSerieView(APIView):
    """``GET /api/campo/inventario/serie/<serie>/``

    La pregunta que justifica el modulo entero: esta ONT, quien la tuvo, donde
    esta, cuando salio y por que. Con un solo libro es una consulta.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request, serie):
        org = request.profile.org
        activos = ActivoSerializado.objects.filter(org=org, serie=serie)
        if not activos.exists():
            raise Http404("No hay ningun aparato con esa serie en esta empresa.")

        salida = []
        for activo in activos.select_related("material"):
            pos = inv.posicion_de(activo)
            recalc, _ = inv.posicion_recalculada(activo)
            salida.append({
                "serie": activo.serie,
                "material": {"codigo": activo.material.codigo,
                             "nombre": activo.material.nombre},
                "donde_esta": pos.ubicacion.nombre if (pos and pos.ubicacion)
                              else "fuera de custodia",
                # Se expone a proposito: si el indice y el libro no coinciden, la
                # pantalla lo tiene que poder decir en vez de elegir uno.
                "cuadra_con_el_libro": (
                    (pos.ubicacion_id if pos else None)
                    == (recalc.id if recalc else None)
                ),
                "historia": inv.historia_de(org, activo.material, activo.serie),
            })
        return Response({"activos": salida})
