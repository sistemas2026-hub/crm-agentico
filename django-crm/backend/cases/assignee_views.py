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
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.access import visible_cases_qs as _visible_cases_qs
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
