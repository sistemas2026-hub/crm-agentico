"""Add one assignee to a case, without touching anyone else.

URL surface (mounted under /api/cases/):
    POST /<id>/assignees/   {"profile_id": "<uuid>"}   add one, idempotent
    GET  /<id>/assignees/                              who is assigned now

WHY THIS EXISTS, given that three endpoints already write ``assigned_to``
------------------------------------------------------------------------
All three of them *replace* the set:

    POST /api/cases/            ``.add()``, but only while creating the case
    PUT  /api/cases/<id>/       ``clear()`` then ``add()`` -- and it also
                                clears contacts, teams and tags
    POST /api/cases/bulk/update ``.set()``

So a caller that only wants to make sure somebody is assigned has to read the
current set, append, and send the whole thing back. Between that read and that
write, a supervisor who adds a second technician loses their change with no
trace. That is fine for a human editing a form -- they are looking at the set
they are replacing -- and wrong for an automated reconciler, which is what
Dexter is (D28: Dexter decides who is *handling* the conversation; the CRM set
is collaborators, not a single owner).

``ManyToMany.add()`` is not read-modify-write: it inserts into the through
table ignoring conflicts. Two callers adding different profiles at the same
time both succeed. That is the whole reason this endpoint can exist safely and
the other three cannot be made safe.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
There is no DELETE here. ``remove()`` would be just as atomic, but the through
table does not record *who* created the relation or why, so nothing can tell a
stale automated assignment apart from a collaboration somebody set up by hand
this morning. Removing on a guess deletes work that cannot be recovered.
Un-assigning stays manual until there is a way to know the difference.

AGREGAR EXIGE PODER ESCRIBIR (24/10/2026)
-----------------------------------------
Hasta ese dia el POST buscaba el caso con la regla de LECTURA y no miraba
mas: quien solo SEGUIA un ticket podia sumarle a cualquiera como
responsable. Ese mismo dia la lectura se abrio a los tickets sin asignar
del area de cada colaborador, y con ella se habria abierto asignarselos a
cualquiera. Ver no es repartir: ahora hace falta 'write'. Para asignarse a
uno mismo un ticket sin responsable esta 'tomar', abajo.

QUIEN LA LLAMA: el reconciliador D28 del motor ('asignar_caso_crm' en
tenants/<slug>.config.yaml -- por eso un grep en el codigo no la encuentra).
Sigue pudiendo: actua con la identidad que CREA los casos de escalamiento
('crear_caso_soporte', mismo token), y quien crea un caso lo escribe; la
misma identidad ya escribe casos con 'cerrar_caso_crm' (PATCH, que siempre
exigio 'write'). Lo unico que pierde este camino es quien solo SIGUE el
caso. Guarda: test_tomar_de_su_area.py::test_quien_creo_el_caso_suma_responsables.

TOMAR (24/10/2026)
------------------
    POST /<id>/tomar/        sin cuerpo: asigna a quien lo pide

Solo sobre un caso SIN responsable, y solo quien reparte, quien lo creo o
alguien del area escrita del caso (cases/access.py::puede_tomar). Dos que aprietan a
la vez: la fila se bloquea y la segunda recibe 409 YA_TIENE_RESPONSABLE, no
un segundo responsable. El area se lee ANTES de abrir la transaccion -- le
pregunta al motor, y ninguna transaccion espera a un servicio externo.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.access import (
    area_de,
    assert_case_write_access,
    get_case_or_404,
    is_org_admin,
    puede_tomar,
    reparte_tickets,
)
from cases.access import visible_cases_qs as _visible_cases_qs
from cases.models import Case
from common.models import Profile
from common.permissions import HasOrgContext
from common.serializer import ProfileSerializer


def _assigned_payload(case):
    """Who is assigned right now. The caller verifies against this instead of
    trusting the status code -- an automated caller has no other way to tell
    ``added`` from ``silently did nothing``."""
    return ProfileSerializer(case.assigned_to.all(), many=True).data


class CaseAssigneesView(APIView):
    """GET/POST /api/cases/<pk>/assignees/"""

    permission_classes = (IsAuthenticated, HasOrgContext)

    def get(self, request, pk, *args, **kwargs):
        case = get_object_or_404(_visible_cases_qs(request.profile), pk=pk)
        return Response({"assigned_to": _assigned_payload(case)})

    def post(self, request, pk, *args, **kwargs):
        case = get_object_or_404(_visible_cases_qs(request.profile), pk=pk)
        assert_case_write_access(request.profile, case)

        profile_id = (request.data or {}).get("profile_id")
        if not profile_id:
            return Response(
                {"error": True, "errors": "profile_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fail closed, and on purpose *not* the way bulk/update does it: there
        # a profile from another org is filtered out silently and the set ends
        # up emptied, so "assign X" can mean "assign nobody" with a 200. Here an
        # id that does not resolve inside this org is a 400 and the set is not
        # touched at all.
        profile = Profile.objects.filter(
            id=profile_id, org=request.profile.org, is_active=True
        ).first()
        if profile is None:
            return Response(
                {"error": True, "errors": "profile not found in this organisation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        already = case.assigned_to.filter(id=profile.id).exists()
        # Additive: nobody else in the set is read, replaced or removed.
        case.assigned_to.add(profile)

        return Response(
            {
                "error": False,
                "added": not already,
                "assigned_to": _assigned_payload(case),
            },
            status=status.HTTP_201_CREATED if not already else status.HTTP_200_OK,
        )


class CaseTomarView(APIView):
    """POST /api/cases/<pk>/tomar/ -- asignarse un caso sin responsable."""

    permission_classes = (IsAuthenticated, HasOrgContext)

    def post(self, request, pk, *args, **kwargs):
        yo = request.profile
        # 404 para un id de otra organizacion o mal formado, igual que el detalle.
        get_case_or_404(yo, pk)
        # Fuera de la transaccion: puede preguntarle al motor.
        area = "" if (is_org_admin(yo) or reparte_tickets(yo)) else area_de(yo)

        with transaction.atomic():
            case = Case.objects.select_for_update().get(pk=pk, org=yo.org)
            if case.assigned_to.exists():
                return Response(
                    {
                        "error": True,
                        "codigo": "YA_TIENE_RESPONSABLE",
                        "errors": "Otra persona ya tomo este ticket.",
                        "assigned_to": _assigned_payload(case),
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            if not puede_tomar(yo, case, area=area):
                return Response(
                    {
                        "error": True,
                        "codigo": "NO_ES_DE_TU_AREA",
                        "errors": "Este ticket no es de tu area.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            case.assigned_to.add(yo)

        return Response(
            {"error": False, "assigned_to": _assigned_payload(case)},
            status=status.HTTP_200_OK,
        )
