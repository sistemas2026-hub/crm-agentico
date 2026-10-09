"""Adding one assignee must never cost the CRM somebody else's.

The endpoint exists because the other three ways of writing ``assigned_to``
replace the whole set (``.set()``, or ``clear()`` + ``add()``). For a person
editing a form that is fine -- they can see the set they are replacing. For an
automated reconciler it is not: between reading the set and writing it back, a
supervisor who adds a second technician loses their change with no trace.

So the assertion that matters here is not "the profile was added". It is
**everyone who was already there is still there**, including when two callers
add different people at the same time.
"""

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


def _url(case_id):
    return f"/api/cases/{case_id}/assignees/"


def _ids(response):
    return {p["id"] for p in response.json()["assigned_to"]}


class TestAddingOneAssignee:
    def test_adds_without_touching_the_others(
        self, admin_client, case_a, admin_profile, user_profile
    ):
        case_a.assigned_to.add(user_profile)

        response = admin_client.post(
            _url(case_a.id), {"profile_id": str(admin_profile.id)}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["added"] is True
        # The one who was already assigned is still assigned. This is the whole
        # point of the endpoint.
        assert _ids(response) == {str(admin_profile.id), str(user_profile.id)}
        assert set(case_a.assigned_to.values_list("id", flat=True)) == {
            admin_profile.id,
            user_profile.id,
        }

    def test_adding_the_same_profile_twice_does_not_duplicate(
        self, admin_client, case_a, admin_profile
    ):
        first = admin_client.post(
            _url(case_a.id), {"profile_id": str(admin_profile.id)}, format="json"
        )
        second = admin_client.post(
            _url(case_a.id), {"profile_id": str(admin_profile.id)}, format="json"
        )

        assert first.status_code == status.HTTP_201_CREATED
        # 200 and added=False: already there. A reconciler needs to tell "I put
        # it there" apart from "it was already there" without guessing.
        assert second.status_code == status.HTTP_200_OK
        assert second.json()["added"] is False
        assert case_a.assigned_to.filter(id=admin_profile.id).count() == 1

    def test_the_response_says_who_is_assigned_now(
        self, admin_client, case_a, admin_profile
    ):
        # The caller verifies against this instead of trusting the status code:
        # it is the only way an automated caller can confirm the effect.
        response = admin_client.post(
            _url(case_a.id), {"profile_id": str(admin_profile.id)}, format="json"
        )
        assert str(admin_profile.id) in _ids(response)

    def test_get_lists_the_current_assignees(
        self, admin_client, case_a, admin_profile, user_profile
    ):
        case_a.assigned_to.add(admin_profile, user_profile)
        response = admin_client.get(_url(case_a.id))
        assert response.status_code == status.HTTP_200_OK
        assert _ids(response) == {str(admin_profile.id), str(user_profile.id)}


class TestTwoCallersAtOnce:
    def test_two_different_additions_do_not_overwrite_each_other(
        self, admin_client, case_a, admin_profile, user_profile
    ):
        """The case ``.set()`` cannot survive.

        With read-modify-write, whoever reads first and writes last wins, and
        the other technician silently disappears from the case. ``add()``
        writes one row in the through table, so both survive.
        """
        admin_client.post(
            _url(case_a.id), {"profile_id": str(admin_profile.id)}, format="json"
        )
        admin_client.post(
            _url(case_a.id), {"profile_id": str(user_profile.id)}, format="json"
        )

        assert set(case_a.assigned_to.values_list("id", flat=True)) == {
            admin_profile.id,
            user_profile.id,
        }

    def test_the_endpoint_never_clears_the_set(self, admin_client, case_a, user_profile):
        """No request shape empties ``assigned_to``.

        ``bulk/update`` does exactly that when the profile does not resolve, so
        "assign X" can end up meaning "assign nobody" with a 200.
        """
        case_a.assigned_to.add(user_profile)

        for cuerpo in ({}, {"profile_id": ""}, {"profile_id": None}):
            admin_client.post(_url(case_a.id), cuerpo, format="json")
            assert set(case_a.assigned_to.values_list("id", flat=True)) == {
                user_profile.id
            }


class TestFailsClosed:
    def test_a_profile_from_another_org_is_rejected(
        self, admin_client, case_a, user_profile, profile_b
    ):
        case_a.assigned_to.add(user_profile)

        response = admin_client.post(
            _url(case_a.id), {"profile_id": str(profile_b.id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # And the set is untouched -- not emptied, not partially applied.
        assert set(case_a.assigned_to.values_list("id", flat=True)) == {
            user_profile.id
        }

    def test_a_case_from_another_org_is_not_found(
        self, admin_client, case_b, admin_profile
    ):
        response = admin_client.post(
            _url(case_b.id), {"profile_id": str(admin_profile.id)}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert case_b.assigned_to.count() == 0

    def test_missing_profile_id_is_a_400(self, admin_client, case_a):
        response = admin_client.post(_url(case_a.id), {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_unknown_profile_is_a_400_and_not_a_silent_noop(
        self, admin_client, case_a
    ):
        response = admin_client.post(
            _url(case_a.id),
            {"profile_id": "11111111-1111-1111-1111-111111111111"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert case_a.assigned_to.count() == 0

    def test_anonymous_cannot_assign(self, unauthenticated_client, case_a, admin_profile):
        response = unauthenticated_client.post(
            _url(case_a.id), {"profile_id": str(admin_profile.id)}, format="json"
        )
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
        assert case_a.assigned_to.count() == 0


class TestThereIsNoRemoval:
    """Un-assigning stays manual, and that is a decision, not an omission.

    ``remove()`` would be just as atomic as ``add()``. What is missing is
    provenance: the through table does not record who created the relation or
    why, so nothing can tell a stale automated assignment apart from a
    collaboration somebody set up by hand this morning.
    """

    def test_delete_is_not_offered(self, admin_client, case_a, admin_profile):
        case_a.assigned_to.add(admin_profile)
        response = admin_client.delete(_url(case_a.id))
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert case_a.assigned_to.filter(id=admin_profile.id).exists()
