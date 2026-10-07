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
from campo.zonas import AliasDeZona, ZonaOperativa, normalizar_localidad
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
        # VACIO NO ES "CUBRE TODAS": con zona dura, una cuadrilla sin zona no
        # recibe trabajo por zona, y eso tiene que notarse.
        "zonas": [{"id": str(z.id), "nombre": z.nombre}
                  for z in j.zonas.all()],
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
            .prefetch_related("integrantes__profile__user", "zonas")
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
                # Las zonas del dia, reescritas enteras por el mismo motivo
                # que los integrantes. Solo las de esta empresa: un id de otra
                # se ignora en silencio en vez de romper el armado, y lo que
                # queda escrito es lo que de verdad se pudo asignar.
                pedidas = request.data.get("zonas") or []
                if isinstance(pedidas, list):
                    jornada.zonas.set(
                        ZonaOperativa.objects.filter(org=org, id__in=[
                            x for x in pedidas if x
                        ])
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
            .prefetch_related("integrantes__profile__user", "zonas")
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


# ===========================================================================
#  ZONAS OPERATIVAS  --  como la empresa divide su territorio
# ===========================================================================

def _zona_json(z) -> dict:
    return {
        "id": str(z.id),
        "nombre": z.nombre,
        "activa": z.activa,
        "localidades": [a.localidad for a in z.alias.all()],
        "notas": z.notas,
    }


class ZonasView(APIView):
    """``GET`` las zonas con sus localidades · ``POST`` una nueva."""

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        qs = ZonaOperativa.objects.filter(org=org)
        if request.query_params.get("todas") not in ("1", "true", "si"):
            qs = qs.filter(activa=True)
        qs = qs.prefetch_related("alias")
        return Response({"zonas": [_zona_json(z) for z in qs]})

    def post(self, request):
        _exigir_gestion(request)
        org = request.profile.org
        nombre = (request.data.get("nombre") or "").strip()
        if not nombre:
            return Response({"detail": "Una zona necesita un nombre."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            z = ZonaOperativa.objects.create(
                org=org, nombre=nombre,
                notas=(request.data.get("notas") or "").strip(),
            )
        except IntegrityError:
            return Response({"detail": f"Ya hay una zona llamada '{nombre}'."},
                            status=status.HTTP_409_CONFLICT)
        return Response(_zona_json(z), status=status.HTTP_201_CREATED)


class ZonaView(APIView):
    """``PATCH`` el nombre o la baja de una zona."""

    permission_classes = [IsCampoAuthenticated]

    def patch(self, request, pk):
        _exigir_gestion(request)
        org = request.profile.org
        z = ZonaOperativa.objects.filter(org=org, id=pk).first()
        if z is None:
            return Response({"detail": "No existe esa zona."},
                            status=status.HTTP_404_NOT_FOUND)
        if "nombre" in request.data:
            nombre = (request.data.get("nombre") or "").strip()
            if not nombre:
                return Response({"detail": "El nombre no puede quedar vacio."},
                                status=status.HTTP_400_BAD_REQUEST)
            z.nombre = nombre
        if "activa" in request.data:
            z.activa = bool(request.data.get("activa"))
        if "notas" in request.data:
            z.notas = (request.data.get("notas") or "").strip()
        try:
            z.save()
        except IntegrityError:
            return Response({"detail": "Ya hay otra zona con ese nombre."},
                            status=status.HTTP_409_CONFLICT)
        return Response(_zona_json(z))


class LocalidadesDeZonaView(APIView):
    """``PUT`` reemplaza ENTERO el mapeo de localidades de una zona.

    Entero y no un delta: la pantalla tiene el estado completo, y mandar
    "agrega esta, saca aquella" obligaria a las dos puntas a estar de acuerdo
    sobre que habia antes. Mandarlo dos veces deja lo mismo que mandarlo una.

    UNA LOCALIDAD EN DOS ZONAS SE RECHAZA, y el mensaje dice en cual esta: si
    estuviera en las dos, una orden de ahi podria ir a cualquiera de las dos
    cuadrillas y el reparto dejaria de ser reproducible.
    """

    permission_classes = [IsCampoAuthenticated]

    def put(self, request, pk):
        _exigir_gestion(request)
        org = request.profile.org
        z = ZonaOperativa.objects.filter(org=org, id=pk).first()
        if z is None:
            return Response({"detail": "No existe esa zona."},
                            status=status.HTTP_404_NOT_FOUND)

        crudas = request.data.get("localidades")
        if not isinstance(crudas, list):
            return Response({"detail": "'localidades' tiene que ser una lista."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Se normalizan ANTES de comparar: el mismo barrio escrito de dos
        # formas no puede contarse dos veces ni chocar consigo mismo.
        nuevas = []
        vistas = set()
        for cruda in crudas:
            texto = normalizar_localidad(str(cruda or ""))
            if texto and texto not in vistas:
                vistas.add(texto)
                nuevas.append(texto)

        ajenas = (
            AliasDeZona.objects
            .filter(org=org, localidad__in=nuevas)
            .exclude(zona=z)
            .select_related("zona")
        )
        if ajenas.exists():
            a = ajenas.first()
            return Response(
                {"detail": f"'{a.localidad}' ya esta en la zona "
                           f"'{a.zona.nombre}'."},
                status=status.HTTP_409_CONFLICT)

        with transaction.atomic():
            z.alias.all().delete()
            AliasDeZona.objects.bulk_create([
                AliasDeZona(org=org, zona=z, localidad=x) for x in nuevas
            ])

        z = (
            ZonaOperativa.objects.prefetch_related("alias").get(pk=z.pk)
        )
        return Response(_zona_json(z))


# ===========================================================================
#  EL REPARTO  --  proponer es leer; publicar es escribir, y son dos rutas
# ===========================================================================

class RepartoView(APIView):
    """``GET ?fecha=`` la propuesta · ``POST`` publicarla.

    DOS VERBOS Y NO UNO CON BANDERA. Proponer no escribe nada y se puede
    repetir todas las veces que haga falta; publicar crea asignaciones de
    verdad. Un solo endpoint con `?simular=1` haria que olvidarse de la
    bandera publicara sin querer.

    EL POST NO RECALCULA: recibe las asignaciones que la pantalla mostro y
    escribe ESAS. Si recalculara, entre mirar y publicar podrian aparecer
    ordenes nuevas --a las 3 de la mañana entran tickets igual-- y se
    publicaria algo que nadie reviso. Se publica lo que se vio.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        fecha = (request.query_params.get("fecha") or "").strip()
        if not fecha:
            return Response({"detail": "Hace falta la fecha."},
                            status=status.HTTP_400_BAD_REQUEST)

        from campo import reparto as rep

        p = rep.proponer(org, fecha)
        return Response({
            "fecha": fecha,
            "asignaciones": [
                {
                    "jornada": str(a["jornada"].id),
                    "cuadrilla": {"id": str(a["cuadrilla"].id),
                                  "nombre": a["cuadrilla"].nombre},
                    "labor": a["jornada"].labor,
                    "zonas": [z.nombre for z in a["jornada"].zonas.all()],
                    "integrantes": a["jornada"].integrantes.count(),
                    "ordenes": [_orden_json(o) for o in a["ordenes"]],
                }
                for a in p["asignaciones"]
            ],
            # Tres motivos distintos, nombrados por separado: se arreglan
            # distinto y un solo "no se repartio" los volveria indistinguibles.
            "sin_zona": [_orden_json(o) for o in p["sin_zona"]],
            "sin_cuadrilla": [_orden_json(o) for o in p["sin_cuadrilla"]],
            "sobrantes": [_orden_json(o) for o in p["sobrantes"]],
        })

    def post(self, request):
        _exigir_gestion(request)
        org = request.profile.org

        crudas = request.data.get("asignaciones")
        if not isinstance(crudas, list) or not crudas:
            return Response({"detail": "No hay nada que publicar."},
                            status=status.HTTP_400_BAD_REQUEST)

        from campo.models import AsignacionTrabajo, OrdenTrabajo

        publicadas, ya_tenian = 0, []
        with transaction.atomic():
            for cruda in crudas:
                jornada = JornadaDeCuadrilla.objects.filter(
                    org=org, id=(cruda or {}).get("jornada")
                ).prefetch_related("integrantes__profile").first()
                if jornada is None:
                    continue

                integrantes = list(jornada.integrantes.all())
                if not integrantes:
                    # Una cuadrilla sin gente ese dia no puede recibir trabajo:
                    # la orden quedaria asignada a nadie.
                    continue

                lider_id = jornada.lider_id or jornada.cuadrilla.lider_id
                for oid in (cruda or {}).get("ordenes") or []:
                    orden = OrdenTrabajo.objects.filter(org=org, id=oid).first()
                    if orden is None:
                        continue
                    # NO SE PISA UNA ASIGNACION QUE YA EXISTE. Entre mirar y
                    # publicar alguien pudo asignarla a mano, y esa decision
                    # gana: la tomo una persona mirando el caso.
                    if orden.asignaciones.exists():
                        ya_tenian.append(orden.numero)
                        continue
                    for i in integrantes:
                        AsignacionTrabajo.objects.create(
                            orden=orden,
                            profile=i.profile,
                            rol=i.rol,
                            es_principal=(i.profile_id == lider_id),
                        )
                    publicadas += 1

        return Response({
            "publicadas": publicadas,
            # Se nombran: si no, la cuenta no cuadra con lo que se vio y nadie
            # sabe cuales quedaron afuera.
            "ya_tenian": ya_tenian,
        })


def _orden_json(o) -> dict:
    return {
        "id": str(o.id),
        "numero": o.numero,
        "cliente": o.cliente_nombre,
        "direccion": o.cliente_direccion,
        "zona": o.zona,
        "prioridad": o.prioridad,
    }
