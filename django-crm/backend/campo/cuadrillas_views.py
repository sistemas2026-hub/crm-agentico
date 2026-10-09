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

from campo.models import AsignacionTrabajo, WorkType
from campo.cuadrillas import (ConfiguracionDeReparto, Cuadrilla,
                              IntegranteDeJornada, JornadaDeCuadrilla,
                              PersonaDeCampo, configuracion_de_reparto)
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
        # LO HABITUAL: de aqui sale la jornada cuando no hay ninguna anterior
        # que copiar -- el arranque en frio del ciclo de la madrugada.
        "labor_habitual": c.labor_habitual,
        "zonas_habituales": [{"id": str(z.id), "nombre": z.nombre}
                             for z in c.zonas_habituales.all()],
        # Vacio = el de la empresa. Una cuadrilla de dos no rinde lo mismo que
        # una de cuatro.
        "tope_diario": c.tope_diario,
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
        # SE DICE SI TIENE CUENTA, y no es un detalle de formato: una orden
        # asignada a quien no entra al sistema no la ve nadie en un telefono,
        # asi que quien arma el dia necesita verlo antes de repartir.
        "integrantes": [
            {"id": str(i.persona_id), "nombre": i.persona.nombre,
             "rol": i.rol, "tiene_cuenta": i.persona.tiene_cuenta,
             # La cuenta, cuando la hay: con esto la pantalla sigue pudiendo
             # enlazar a lo que ya mostraba por `Profile`.
             "profile": (str(i.persona.profile_id)
                         if i.persona.profile_id else None)}
            for i in j.integrantes.select_related("persona")
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
        if "labor_habitual" in request.data:
            labor = (request.data.get("labor_habitual") or "").strip()
            validas = dict(JornadaDeCuadrilla.LABORES)
            if labor not in validas:
                return Response(
                    {"detail": f"'{labor}' no es una labor. Son: "
                               f"{', '.join(validas)}."},
                    status=status.HTTP_400_BAD_REQUEST)
            c.labor_habitual = labor
        if "tope_diario" in request.data:
            # Vacio vuelve al tope de la empresa. Un cero NO es "sin tope":
            # seria una cuadrilla que no recibe nada, y eso se dice dandola de
            # baja, no poniendole cero.
            crudo = request.data.get("tope_diario")
            if crudo in (None, "", 0, "0"):
                c.tope_diario = None
            else:
                try:
                    c.tope_diario = max(1, int(crudo))
                except (TypeError, ValueError):
                    return Response({"detail": "El tope tiene que ser un numero."},
                                    status=status.HTTP_400_BAD_REQUEST)
        if "zonas_habituales" in request.data:
            # Se reemplaza la lista ENTERA, igual que las zonas del dia: la
            # pantalla manda el estado completo de los checkboxes y un merge
            # incremental haria que desmarcar no desmarcara.
            pedidas = request.data.get("zonas_habituales") or []
            if isinstance(pedidas, list):
                c.zonas_habituales.set(
                    ZonaOperativa.objects.filter(
                        org=org, id__in=[x for x in pedidas if x])
                )
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
        # Se acepta 'persona' (el id de PersonaDeCampo) y tambien el viejo
        # 'profile': la pantalla que ya existia enlazaba por cuenta, y romper
        # ese enlace dejaria los historiales guardados sin poder abrirse.
        persona = (request.query_params.get("persona") or "").strip()
        if persona:
            qs = qs.filter(integrantes__persona_id=persona)
        else:
            por_cuenta = (request.query_params.get("profile") or "").strip()
            if por_cuenta:
                qs = qs.filter(integrantes__persona__profile_id=por_cuenta)

        qs = (
            qs.select_related("cuadrilla", "lider__user")
            .prefetch_related("integrantes__persona", "zonas")
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
                    persona = _persona_de_campo(
                        org, (crudo or {}).get("persona")
                              or (crudo or {}).get("profile"))
                    if persona is None:
                        raise ValidationError(
                            "Hay un integrante que no es de esta empresa."
                        )
                    integrante = IntegranteDeJornada(
                        org=org, jornada=jornada, persona=persona,
                        rol=((crudo or {}).get("rol")
                             or persona.rol_habitual).strip(),
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
            .prefetch_related("integrantes__persona", "zonas")
            .get(pk=jornada.pk)
        )
        return Response(_jornada_json(jornada), status=status.HTTP_200_OK)


def _persona_de_campo(org, valor):
    """La persona de campo de esta empresa, o None.

    Acepta tambien el id de un `Profile`, porque la pantalla anterior enlazaba
    por cuenta y los historiales guardados usan ese id.

    CUANDO EL VALOR ES UNA CUENTA Y TODAVIA NO TIENE PERSONA, SE CREA. No es
    una comodidad: sin esto, el dia que esto se despliegue nadie podria armar
    una jornada hasta haber dado de alta a mano a todo el equipo que ya existe
    --y el sintoma seria "ese integrante no es de esta empresa", que señala a
    la causa equivocada.

    Es seguro porque la clave es la CUENTA, y `unique_persona_de_campo_por_cuenta`
    impide que dos filas la compartan. El riesgo de duplicados vive en los
    NOMBRES, no aca: por eso un alta por nombre sigue siendo explicita y avisa
    de los homonimos (ver `PersonasDeCampoView.post`).
    """
    if not valor:
        return None
    try:
        directa = PersonaDeCampo.objects.filter(
            org=org, id=valor, activa=True
        ).first()
        if directa is not None:
            return directa

        cuenta = Profile.objects.select_related("user").filter(
            org=org, id=valor, is_active=True
        ).first()
        if cuenta is None:
            return None
        persona, _ = PersonaDeCampo.objects.get_or_create(
            org=org, profile=cuenta,
            defaults={"nombre": _nombre_de(cuenta) or "Sin nombre"},
        )
        # Una persona dada de BAJA no vuelve sola por llegar por su cuenta:
        # darla de baja fue una decision, y reactivarla tiene su propio paso.
        return persona if persona.activa else None
    except (ValueError, ValidationError):
        # Un id mal formado no es un 500: es "no existe".
        return None


def _persona_json(p) -> dict:
    return {
        "id": str(p.id),
        "nombre": p.nombre,
        "rol_habitual": p.rol_habitual,
        "activa": p.activa,
        # Si entra al sistema. Decide si puede RECIBIR trabajo en un telefono,
        # asi que la pantalla lo necesita antes de repartir, no despues.
        "tiene_cuenta": p.tiene_cuenta,
        "profile": str(p.profile_id) if p.profile_id else None,
    }


class PersonasDeCampoView(APIView):
    """``GET`` quienes trabajan en campo · ``POST`` una persona nueva.

    POR QUE NO ALCANZABA LA LISTA DEL EQUIPO
    ----------------------------------------
    La pantalla ofrecia `Profile`, o sea gente con cuenta. Los auxiliares no
    tienen celular asignado y por lo tanto no tienen cuenta, asi que no habia
    forma de anotarlos -- y el catalogo de roles ofrecia 'ayudante' y 'chofer'
    para gente que el modelo no podia registrar. Ver el docstring de
    `campo.cuadrillas.PersonaDeCampo`.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        qs = PersonaDeCampo.objects.filter(org=org).select_related("profile")
        if (request.query_params.get("activas") or "1") == "1":
            qs = qs.filter(activa=True)
        personas = list(qs)

        # LAS CUENTAS QUE TODAVIA NO SON PERSONA DE CAMPO, para que dar de
        # alta al equipo que ya existe no sea cargarlo a mano uno por uno.
        # Se excluyen contra TODAS las personas, no solo las activas: una
        # cuenta de alguien dado de baja volveria a ofrecerse como pendiente y
        # al alta chocaria con la unicidad.
        ya = set(
            PersonaDeCampo.objects.filter(
                org=org, profile__isnull=False
            ).values_list("profile_id", flat=True)
        )
        pendientes = [
            {"profile": str(pr.id), "nombre": _nombre_de(pr)}
            for pr in Profile.objects.select_related("user").filter(
                org=org, is_active=True
            ).exclude(id__in=ya)
        ]
        return Response({
            "personas": [_persona_json(p) for p in personas],
            "cuentas_sin_persona": pendientes,
        })

    def post(self, request):
        org = request.profile.org
        _exigir_gestion(request)

        profile = _perfil_de(org, request.data.get("profile"))
        nombre = (request.data.get("nombre") or "").strip()
        if profile is not None and not nombre:
            # Se da de alta una cuenta del equipo: el nombre sale de ella.
            nombre = _nombre_de(profile)
        if not nombre:
            return Response({"detail": "Hace falta el nombre."},
                            status=status.HTTP_400_BAD_REQUEST)

        if profile is not None and PersonaDeCampo.objects.filter(
            org=org, profile=profile
        ).exists():
            # Dos filas con la misma cuenta serian la misma persona dos veces,
            # y su historial quedaria partido al medio.
            return Response(
                {"detail": "Esa cuenta ya esta dada de alta como persona de campo."},
                status=status.HTTP_409_CONFLICT)

        rol = (request.data.get("rol_habitual") or "").strip()
        validos = dict(AsignacionTrabajo.ROLES_CUADRILLA)
        if rol and rol not in validos:
            return Response(
                {"detail": f"'{rol}' no es un rol. Son: {', '.join(validos)}."},
                status=status.HTTP_400_BAD_REQUEST)

        persona = PersonaDeCampo.objects.create(
            org=org, nombre=nombre, profile=profile,
            rol_habitual=rol or AsignacionTrabajo.AYUDANTE,
        )
        return Response({
            **_persona_json(persona),
            # EL NOMBRE NO ES UNICO A PROPOSITO --dos personas se pueden
            # llamar igual de verdad-- asi que se avisa y decide quien carga,
            # en vez de bloquear y obligarlo a deformar un nombre.
            "homonimos": PersonaDeCampo.objects.filter(
                org=org, nombre__iexact=nombre
            ).exclude(id=persona.id).count(),
        }, status=status.HTTP_201_CREATED)


class PersonaDeCampoView(APIView):
    """``PATCH`` el nombre, el rol habitual, la cuenta o la baja."""

    permission_classes = [IsCampoAuthenticated]

    def patch(self, request, pk):
        org = request.profile.org
        _exigir_gestion(request)

        persona = PersonaDeCampo.objects.filter(org=org, id=pk).first()
        if persona is None:
            return Response({"detail": "No existe."},
                            status=status.HTTP_404_NOT_FOUND)

        if "nombre" in request.data:
            nombre = (request.data.get("nombre") or "").strip()
            if not nombre:
                return Response({"detail": "El nombre no puede quedar vacio."},
                                status=status.HTTP_400_BAD_REQUEST)
            persona.nombre = nombre

        if "rol_habitual" in request.data:
            rol = (request.data.get("rol_habitual") or "").strip()
            validos = dict(AsignacionTrabajo.ROLES_CUADRILLA)
            if rol not in validos:
                return Response(
                    {"detail": f"'{rol}' no es un rol. Son: {', '.join(validos)}."},
                    status=status.HTTP_400_BAD_REQUEST)
            persona.rol_habitual = rol

        if "profile" in request.data:
            # ENLAZAR UNA CUENTA A ALGUIEN QUE YA TRABAJABA es el caso del
            # auxiliar al que le asignan celular: se le engancha la cuenta a
            # ESTA fila y su historial sigue siendo uno, en vez de nacer una
            # persona nueva que empieza de cero.
            cuenta = _perfil_de(org, request.data.get("profile"))
            if request.data.get("profile") and cuenta is None:
                return Response({"detail": "Esa cuenta no es de esta empresa."},
                                status=status.HTTP_400_BAD_REQUEST)
            if cuenta is not None and PersonaDeCampo.objects.filter(
                org=org, profile=cuenta
            ).exclude(id=persona.id).exists():
                return Response(
                    {"detail": "Esa cuenta ya esta en otra persona de campo."},
                    status=status.HTTP_409_CONFLICT)
            persona.profile = cuenta

        if "activa" in request.data:
            # Se da de BAJA, no se borra: sus jornadas la referencian y son
            # las que explican quien estuvo cada dia.
            persona.activa = bool(request.data.get("activa"))

        persona.save()
        return Response(_persona_json(persona))


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

class TiposDeTrabajoView(APIView):
    """``GET`` los tipos de trabajo y su labor · ``PATCH`` clasificar uno.

    POR QUE EXISTE
    --------------
    `WorkType` no tenia ninguna pantalla: los tipos se crean por seed o por el
    admin de Django. Mientras la labor no se usaba para nada eso alcanzaba,
    pero desde que el reparto NO reparte lo que no esta clasificado, no tener
    donde clasificarlo dejaria todas las ordenes en `sin_clasificar` para
    siempre -- y el sintoma, «no se asigno nada», no señalaria aqui.

    SOLO SE TOCA LA LABOR. El codigo y el nombre de un tipo de trabajo son del
    catalogo de la empresa y los cambia quien lo administra; esto es la
    pregunta operativa de «¿que cuadrillas pueden tomarlo?», que es otra cosa
    y la contesta quien arma el dia.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        qs = WorkType.objects.filter(org=org, activo=True).order_by("codigo")
        return Response({
            "tipos": [
                {"id": str(t.id), "codigo": t.codigo, "nombre": t.nombre,
                 "labor": t.labor}
                for t in qs
            ],
            "labores": [{"id": v, "texto": n} for v, n in WorkType.LABORES],
            # Cuantos quedan sin clasificar: es el numero que explica por que
            # el reparto deja ordenes afuera, y tenerlo aqui evita cruzarlo a
            # mano contra la lista.
            "sin_clasificar": qs.filter(labor="").count(),
        })

    def patch(self, request, pk):
        org = request.profile.org
        _exigir_gestion(request)

        tipo = WorkType.objects.filter(org=org, id=pk).first()
        if tipo is None:
            return Response({"detail": "No existe."},
                            status=status.HTTP_404_NOT_FOUND)

        labor = (request.data.get("labor") or "").strip()
        validas = dict(WorkType.LABORES)
        # Vacio es valido: es «volver a sin clasificar», y hace falta para
        # poder deshacer una clasificacion equivocada sin tocar la base.
        if labor and labor not in validas:
            return Response(
                {"detail": f"'{labor}' no es una labor. Son: "
                           f"{', '.join(validas)}."},
                status=status.HTTP_400_BAD_REQUEST)

        tipo.labor = labor
        tipo.save(update_fields=["labor"])
        return Response({"id": str(tipo.id), "codigo": tipo.codigo,
                         "nombre": tipo.nombre, "labor": tipo.labor})


class ConfiguracionDeRepartoView(APIView):
    """``GET`` como reparte esta empresa · ``PUT`` cambiarlo.

    POR QUE ES CONFIGURACION Y NO CONSTANTES
    ----------------------------------------
    El tope por cuadrilla vivia fijo en `reparto.TOPE_POR_CUADRILLA = 8`, y la
    hora del ciclo habria vivido fija en la entrada de Celery beat. Las dos
    cosas varian por empresa --una operacion de cinco cuadrillas no reparte
    como una de veinte, y un ISP en otro huso no madruga a la misma hora UTC--
    asi que van donde se pueden cambiar sin una sesion de codigo.
    """

    permission_classes = [IsCampoAuthenticated]

    def get(self, request):
        org = request.profile.org
        c = configuracion_de_reparto(org)
        return Response({
            "activo": c.activo,
            "hora_local": c.hora_local,
            "tope_por_cuadrilla": c.tope_por_cuadrilla,
            "copia_la_jornada": c.copia_la_jornada,
            "ultima_corrida": (c.ultima_corrida.isoformat()
                               if c.ultima_corrida else None),
            # La zona de la empresa, para que la pantalla pueda decir «3 de la
            # mañana en Bogota» y no un numero suelto que no se sabe de donde
            # es.
            "zona_horaria": getattr(org, "timezone", "") or "UTC",
            # Que vale mientras nadie cree la fila. Sin esto la pantalla no
            # puede distinguir «esta en 8 porque alguien lo puso» de «esta en 8
            # porque nadie lo toco».
            "configurado": ConfiguracionDeReparto.objects.filter(org=org).exists(),
        })

    def put(self, request):
        org = request.profile.org
        _exigir_gestion(request)

        datos = request.data or {}
        hora = datos.get("hora_local", ConfiguracionDeReparto.HORA_DE_FABRICA)
        tope = datos.get("tope_por_cuadrilla",
                         ConfiguracionDeReparto.TOPE_DE_FABRICA)
        try:
            hora = int(hora)
            tope = int(tope)
        except (TypeError, ValueError):
            return Response({"detail": "La hora y el tope son numeros."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not 0 <= hora <= 23:
            return Response({"detail": "La hora va de 0 a 23."},
                            status=status.HTTP_400_BAD_REQUEST)
        if tope < 1:
            # Cero no es «sin tope»: seria un reparto que no reparte nada, y
            # el sintoma --cuadrillas vacias cada mañana-- no señalaria aqui.
            return Response({"detail": "El tope tiene que ser 1 o mas."},
                            status=status.HTTP_400_BAD_REQUEST)

        fila, _ = ConfiguracionDeReparto.objects.update_or_create(
            org=org,
            defaults={
                "activo": bool(datos.get("activo")),
                "hora_local": hora,
                "tope_por_cuadrilla": tope,
                "copia_la_jornada": bool(datos.get("copia_la_jornada", True)),
            },
        )
        return Response({
            "activo": fila.activo,
            "hora_local": fila.hora_local,
            "tope_por_cuadrilla": fila.tope_por_cuadrilla,
            "copia_la_jornada": fila.copia_la_jornada,
            "ultima_corrida": (fila.ultima_corrida.isoformat()
                               if fila.ultima_corrida else None),
            "configurado": True,
        })


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
            # Ni siquiera se pudieron evaluar: su tipo de trabajo no dice a
            # que labor pertenece. Se arregla clasificando el TIPO una vez.
            "sin_clasificar": [_orden_json(o) for o in p["sin_clasificar"]],
        })

    def post(self, request):
        _exigir_gestion(request)
        org = request.profile.org

        crudas = request.data.get("asignaciones")
        if not isinstance(crudas, list) or not crudas:
            return Response({"detail": "No hay nada que publicar."},
                            status=status.HTTP_400_BAD_REQUEST)

        from campo.models import AsignacionTrabajo, OrdenTrabajo

        publicadas, ya_tenian, sin_cuenta = 0, [], []
        #  Se acumula FUERA del ciclo: una variable por cuadrilla solo
        #  guardaria la ultima, y con dos cuadrillas el numero mentiria.
        auxiliares = 0
        with transaction.atomic():
            for cruda in crudas:
                jornada = JornadaDeCuadrilla.objects.filter(
                    org=org, id=(cruda or {}).get("jornada")
                ).prefetch_related("integrantes__persona").first()
                if jornada is None:
                    continue

                integrantes = list(jornada.integrantes.all())
                if not integrantes:
                    # Una cuadrilla sin gente ese dia no puede recibir trabajo:
                    # la orden quedaria asignada a nadie.
                    continue

                # SOLO QUIEN TIENE CUENTA RECIBE LA ASIGNACION, porque una
                # orden asignada a quien no entra al sistema no aparece en
                # ningun telefono. Los auxiliares sin celular integran la
                # cuadrilla --y por eso quedan en la jornada, que es donde se
                # lee quien estuvo-- pero no son a quien se le manda el
                # trabajo.
                con_cuenta = [i for i in integrantes if i.persona.tiene_cuenta]
                if not con_cuenta:
                    # Toda la cuadrilla sin cuenta: la orden quedaria sin una
                    # sola asignacion y nadie la veria. Se SALTEA y se dice --
                    # publicar cero asignaciones e informar exito seria peor
                    # que no publicar.
                    sin_cuenta.append(jornada.cuadrilla.nombre)
                    continue

                auxiliares += len(integrantes) - len(con_cuenta)
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
                    for i in con_cuenta:
                        AsignacionTrabajo.objects.create(
                            orden=orden,
                            profile=i.persona.profile,
                            rol=i.rol,
                            es_principal=(i.persona.profile_id == lider_id),
                        )
                    publicadas += 1

        return Response({
            "publicadas": publicadas,
            # Se nombran: si no, la cuenta no cuadra con lo que se vio y nadie
            # sabe cuales quedaron afuera.
            "ya_tenian": ya_tenian,
            # Las cuadrillas que no se pudieron publicar porque NADIE en ellas
            # entra al sistema. Un silencio aca haria creer que se repartio
            # todo.
            "sin_nadie_con_cuenta": sin_cuenta,
            # Cuantos auxiliares integran las cuadrillas publicadas sin recibir
            # asignacion: es lo esperado, no un error, pero se dice para que
            # nadie lo lea como gente perdida.
            "auxiliares_sin_asignacion": auxiliares,
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
