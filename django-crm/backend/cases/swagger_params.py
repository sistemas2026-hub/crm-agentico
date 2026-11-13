"""Schema-only parameter lists for drf-spectacular.

The ``org`` header parameter that used to lead every list here is gone; see
``common/swagger_params.py`` for why.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

organization_params = []

cases_list_get_params = [
    OpenApiParameter("name", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("priority", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("account", OpenApiTypes.STR, OpenApiParameter.QUERY),
    # El area del caso ('Case.area'). Con 'area_responsables' (repetible,
    # ids de perfil) entran ademas los casos SIN area escrita asignados a
    # esa gente: ver apply_case_list_filters en views.py.
    OpenApiParameter("area", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter(
        "area_responsables", OpenApiTypes.UUID, OpenApiParameter.QUERY, many=True
    ),
]
