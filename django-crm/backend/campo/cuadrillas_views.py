# -*- coding: utf-8 -*-
"""
================================================================================
 LAS CUADRILLAS, DESDE LA PLATAFORMA
================================================================================

Quien reparte el trabajo necesita dos cosas distintas y por eso son dos rutas:

    /campo/cuadrillas/           quienes son  -- cambia casi nunca
    /campo/cuadrillas/jornada/   que hacen HOY -- cambia cada mañana

Mezclarlas en una sola haria que armar el dia pareciera editar la cuadrilla, y
es justo lo contrario: la cuadrilla sigue siendo la misma, lo que cambia es su
labor y quien la integra.

QUIEN PUEDE
-----------
Repartir trabajo es decidir el dia de otras personas, asi que pide rol de
gestion. No alcanza con ser tecnico de campo, aunque sea el lider: el lider
ejecuta la jornada, no la arma.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from campo.cuadrillas import Cuadrilla, IntegranteDeJornada, JornadaDeCuadrilla
from campo.inventario import UbicacionInventario
from campo.permissions import IsCampoAuthenticated, ROLES_GESTION
from common.models import Profile


#: Cuanto historial se puede pedir de una vez.
#:
#: Sin tope, pedir un año entero devuelve todo y la pantalla se cuelga sin que
#: nadie entienda por que. Tres meses cubren "el trimestre pasado", que es el
#: horizonte con el que se mira de verdad una cuadrilla.
MAX_DIAS_DE_HISTORIAL = 92


def _fecha_de(texto: str):
    """AAAA-MM-DD a fecha. Lanza ValueError si no lo es."""
    import datetime as _dt

    return _dt.date.fromisoformat(texto)


def _exigir_gestion(request):
    """403 si quien pide no puede repartir trabajo."""
    rol = (getattr(request.profile, "role", "") or "").upper()
    if rol in ROLES_GESTION or request.user.is_superuser:
        return
    from rest_framework.exceptions import PermissionDenied

    raise PermissionDenied(
        "Para armar cuadrillas hace falta un rol de gestion."
    )


def _nombre_de(profile) -> str:
    """Como se llama una persona, sin exponer el UUID.

    El nombre NO esta en `Profile` --no tiene campo `name`-- sino en
    `User.name`. Es la misma leccion que ya dejo escrita
    `services/inventario.py::nombre_de`: la primera version de aquella funcion
    probaba `profile.name`, caia al id, y la pantalla decia
    "Custodia de 47905efd-...". Para el compilador un UUID es un nombre
    perfectamente valido.
    """
    user = getattr(profile, "user", None)
    return (getattr(user, "name", "") or getattr(user, "email", "") or "").strip()


def _persona(profile) -> dict:
    return {"id": str(profile.id), "nombre": _nombre_de(profile)}


def _cuadrilla_json(c) -> dict:
    return {
        "id": str(c.id),
        "nombre": c.nombre,
        "activa": c.activa,
        "lider": _persona(c.lider) if c.lider else None,
        "vehiculo": (
            {"id": str(c.vehiculo_id), "nombre": c.vehiculo.nombre}
            if c.vehiculo_id else None
        ),
        "notas": c.notas,
    }


def _jornada_json(j) -> dict:
    return {
        "id": str(j.id),
        "fecha": j.fecha.isoformat(),
        "labor": j.labor,
        "labor_nombre": j.get_labor_display(),
        "cuadrilla": {"id": str(j.cuadrilla_id), "nombre": j.cuadrilla.nombre},
        # El lider del DIA, que puede no ser el de la cuadrilla: si esta de
        # vacaciones, alguien la lleva igual.
        "lider": _persona(j.lider) if j.lider else None,
        "integrantes": [
            {**_persona(i.profile), "rol": i.rol}
            for i in j.integrantes.select_related("profile__user")
        ],
        "notas": j.notas,
    }


class CuadrillasView(APIView):
    """``GET`` las cuadrillas de la empresa · ``POST`` una nueva."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        # Las dadas de baja entran solo si se piden: administrarlas es otra
        # pantalla que repartir el trabajo de mañana.
        qs = Cuadrilla.objects.filter(org=org)
        if request.query_params.get("todas") not in ("1", "true", "si"):
            qs = qs.filter(activa=True)
        qs = qs.select_related("lider__user", "vehiculo")
        return Response({"cuadrillas": [_cuadrilla_json(c) for c in qs]})

    def post(self, request):
        _exigir_gestion(request)
        org = request.profile.org
        nombre = (request.data.get("nombre") or "").strip()
        if not nombre:
            return Response({"detail": "Una cuadrilla necesita un nombre."},
                            status=status.HTTP_400_BAD_REQUEST)

        lider = _perfil_de(org, request.data.get("lider"))
        vehiculo = _vehiculo_de(org, request.data.get("vehiculo"))
        try:
            c = Cuadrilla.objects.create(
                org=org, nombre=nombre, lider=lider, vehiculo=vehiculo,
                notas=(request.data.get("notas") or "").strip(),
            )
        except IntegrityError:
            # 409 y no 400: el dato esta bien escrito; lo que no se puede es
            # tener dos cuadrillas con el mismo nombre, porque el nombre es lo
            # que la gente usa para hablar de ella.
            return Response(
                {"detail": f"Ya hay una cuadrilla llamada '{nombre}'."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_cuadrilla_json(c), status=status.HTTP_201_CREATED)


class CuadrillaView(APIView):
    """``PATCH`` el nombre, el lider, el vehiculo o la baja de una cuadrilla."""

    permission_classes = [IsCampoAuthenticated]

    def patch(self, request, pk):
        _exigir_gestion(request)
        org = request.profile.org
        c = Cuadrilla.objects.filter(org=org, id=pk).first()
        if c is None:
            return Response({"detail": "No existe esa cuadrilla."},
                            status=status.HTTP_404_NOT_FOUND)

        if "nombre" in request.data:
            nombre = (request.data.get("nombre") or "").strip()
            if not nombre:
                return Response({"detail": "El nombre no puede quedar vacio."},
                                status=status.HTTP_400_BAD_REQUEST)
            c.nombre = nombre
        if "lider" in request.data:
            c.lider = _perfil_de(org, request.data.get("lider"))
        if "vehiculo" in request.data:
            c.vehiculo = _vehiculo_de(org, request.data.get("vehiculo"))
        if "activa" in request.data:
            c.activa = bool(request.data.get("activa"))
        if "notas" in request.data:
            c.notas = (request.data.get("notas") or "").strip()

        try:
            c.save()
        except IntegrityError:
            return Response({"detail": "Ya hay otra cuadrilla con ese nombre."},
                            status=status.HTTP_409_CONFLICT)
        return Response(_cuadrilla_json(c))


class JornadaDeCuadrillaView(APIView):
    """``GET ?fecha=YYYY-MM-DD`` el dia armado · ``POST`` armar o reescribir uno.

    EL POST ES IDEMPOTENTE POR CUADRILLA Y DIA: vuelve a escribir la jornada
    entera con lo que llega. Armar el dia es una operacion que se corrige varias
    veces antes de que empiece, y obligar a borrar para rehacer dejaria ventanas
    donde la cuadrilla no existe para ese dia.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        """Un dia, o un RANGO.

        `?fecha=` sigue devolviendo un dia, que es con lo que se arma mañana.
        `?desde=&hasta=` devuelve el historial, que contesta otra pregunta:
        quien estuvo con quien, y que dia. El dato siempre estuvo completo --una
        fila por persona y por jornada-- y lo unico que faltaba era poder
        leerlo junto en vez de ir cambiando la fecha de a un dia.

        Se puede acotar por `cuadrilla` o por `profile`. La segunda es la que
        importa el dia que haya que responder "quien estaba en esa
        instalacion": sin ella hay que abrir cuadrilla por cuadrilla.
        """
        org = request.profile.org
        fecha = (request.query_params.get("fecha") or "").strip()
        desde = (request.query_params.get("desde") or "").strip()
        hasta = (request.query_params.get("hasta") or "").strip()

        if not fecha and not (desde and hasta):
            return Response(
                {"detail": "Hace falta 'fecha', o 'desde' y 'hasta'."},
                status=status.HTTP_400_BAD_REQUEST)

        qs = JornadaDeCuadrilla.objects.filter(org=org)
        if fecha:
            qs = qs.filter(fecha=fecha)
        else:
            # UN TOPE, Y DICHO. Sin el, pedir un año entero devuelve todo y la
            # pantalla se cuelga sin que nadie entienda por que. Tres meses
            # cubren "el trimestre pasado", que es lo que se mira de verdad.
            try:
                dias = (_fecha_de(hasta) - _fecha_de(desde)).days
            except ValueError:
                return Response({"detail": "Las fechas van en AAAA-MM-DD."},
                                status=status.HTTP_400_BAD_REQUEST)
            if dias < 0:
                return Response({"detail": "'hasta' es anterior a 'desde'."},
                                status=status.HTTP_400_BAD_REQUEST)
            if dias > MAX_DIAS_DE_HISTORIAL:
                return Response(
                    {"detail": f"El rango no puede pasar de "
                               f"{MAX_DIAS_DE_HISTORIAL} dias."},
                    status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(fecha__gte=desde, fecha__lte=hasta)

        cuadrilla = (request.query_params.get("cuadrilla") or "").strip()
        if cuadrilla:
            qs = qs.filter(cuadrilla_id=cuadrilla)

        # POR PERSONA: las jornadas donde ESA persona estuvo, con la cuadrilla
        # y el rol que tuvo cada dia. Es la vista que contesta "con quien
        # trabajo Pedro el martes".
        persona = (request.query_params.get("profile") or "").strip()
        if persona:
            qs = qs.filter(integrantes__profile_id=persona)

        qs = (
            qs.select_related("cuadrilla", "lider__user")
            .prefetch_related("integrantes__profile__user")
            .distinct()
            .order_by("fecha", "cuadrilla__nombre")
        )
        return Response({
            "fecha": fecha,
            "desde": desde,
            "hasta": hasta,
            "jornadas": [_jornada_json(j) for j in qs],
        })

    def post(self, request):
        _exigir_gestion(request)
        org = request.profile.org

        cuadrilla = Cuadrilla.objects.filter(
            org=org, id=request.data.get("cuadrilla")
        ).first() if request.data.get("cuadrilla") else None
        if cuadrilla is None:
            return Response({"detail": "Hace falta una cuadrilla de esta empresa."},
                            status=status.HTTP_400_BAD_REQUEST)

        fecha = (request.data.get("fecha") or "").strip()
        if not fecha:
            return Response({"detail": "Hace falta la fecha."},
                            status=status.HTTP_400_BAD_REQUEST)

        labor = (request.data.get("labor") or "").strip()
        if labor not in dict(JornadaDeCuadrilla.LABORES):
            return Response(
                {"detail": f"'{labor}' no es una labor. Son: "
                           f"{', '.join(dict(JornadaDeCuadrilla.LABORES))}."},
                status=status.HTTP_400_BAD_REQUEST)

        crudos = request.data.get("integrantes") or []
        if not isinstance(crudos, list):
            return Response({"detail": "'integrantes' tiene que ser una lista."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                jornada, _ = JornadaDeCuadrilla.objects.update_or_create(
                    cuadrilla=cuadrilla, fecha=fecha,
                    defaults={
                        "org": org,
                        "labor": labor,
                        "lider": _perfil_de(org, request.data.get("lider"))
                                 or cuadrilla.lider,
                        "notas": (request.data.get("notas") or "").strip(),
                    },
                )
                # Se reescribe la lista entera: es lo que hace que armar el dia
                # dos veces deje el mismo resultado que armarlo una.
                jornada.integrantes.all().delete()
                for crudo in crudos:
                    profile = _perfil_de(org, (crudo or {}).get("profile"))
                    if profile is None:
                        raise ValidationError(
                            "Hay un integrante que no es de esta empresa."
                        )
                    integrante = IntegranteDeJornada(
                        org=org, jornada=jornada, profile=profile,
                        rol=((crudo or {}).get("rol") or "tecnico").strip(),
                    )
                    # `full_clean` y no `save` a secas: ahi vive la guarda de
                    # "esta persona ya esta en otra cuadrilla hoy", que es la
                    # que evita repartirle el dia a alguien dos veces.
                    integrante.full_clean()
                    integrante.save()
        except ValidationError as e:
            return Response({"detail": "; ".join(e.messages)},
                            status=status.HTTP_409_CONFLICT)

        jornada = (
            JornadaDeCuadrilla.objects
            .select_related("cuadrilla", "lider__user")
            .prefetch_related("integrantes__profile__user")
            .get(pk=jornada.pk)
        )
        return Response(_jornada_json(jornada), status=status.HTTP_200_OK)


def _perfil_de(org, valor):
    if not valor:
        return None
    try:
        return Profile.objects.select_related("user").filter(
            org=org, id=valor, is_active=True
        ).first()
    except (ValueError, ValidationError):
        # Un id mal formado no es un 500: es "no existe".
        return None


def _vehiculo_de(org, valor):
    if not valor:
        return None
    try:
        return UbicacionInventario.objects.filter(
            org=org, id=valor, tipo=UbicacionInventario.VEHICULO
        ).first()
    except (ValueError, ValidationError):
        return None
