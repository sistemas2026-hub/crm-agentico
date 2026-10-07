# -*- coding: utf-8 -*-
"""El buscador de la cola encuentra por cliente y por numero de ticket.

POR QUE SE AMPLIO  --  07/10/2026
----------------------------------
La busqueda miraba solo ``name`` y ``description``. En una cola de tickets
IMPORTADOS eso no alcanza: medido en produccion ese dia, el asunto "No Tiene
Internet" se repite en **153** casos. Lo que identifica una fila es de quien
es y con que numero se la busca en el panel del proveedor.

``external_client_name`` ademas NO aparece en la descripcion -- el importador
guarda ahi la referencia y quien abrio el ticket del lado del ISP, no el
cliente -- asi que buscar por nombre devolvia cero y el buscador prometia algo
que no hacia.

QUE SE AFIRMA
-------------
Sobre el EFECTO: que la busqueda DEVUELVA el caso. Comprobar que el ``Q``
existe no prueba que encuentre nada, y menos cuando el campo que se busca ni
siquiera estaba en el texto donde se buscaba.
"""

import pytest
from rest_framework import status

from cases.models import Case

pytestmark = pytest.mark.django_db

RUTA = "/api/cases/"
REPETIDO = "No Tiene Internet"


def _caso(org, creador, **extra):
    datos = dict(
        name=REPETIDO, status="New", priority="Low", case_type="Question",
        description="Importado de wisphub, ticket #94553. Servicio 7746.",
        created_by=creador, org=org,
    )
    datos.update(extra)
    return Case.objects.create(**datos)


def _ids(respuesta):
    return {c["id"] for c in respuesta.json()["cases"]}


def test_encuentra_por_nombre_del_cliente(admin_client, admin_user, org_a):
    """LA REPRODUCCION: dos casos con el MISMO asunto, distinto cliente."""
    buscado = _caso(org_a, admin_user, external_client_name="JUAN DAVID BARRIOS")
    otro = _caso(org_a, admin_user, external_client_name="MARIA CABARCAS")

    r = admin_client.get(RUTA, {"search": "BARRIOS"})

    assert r.status_code == status.HTTP_200_OK
    ids = _ids(r)
    assert str(buscado.id) in ids, (
        "el nombre del cliente no esta en la descripcion: sin su propio "
        "termino de busqueda, esto devuelve cero")
    assert str(otro.id) not in ids, "trajo el del otro cliente"


def test_el_nombre_del_cliente_no_distingue_mayusculas(
        admin_client, admin_user, org_a):
    """Quien busca escribe como escribe; el proveedor guarda en mayusculas."""
    c = _caso(org_a, admin_user, external_client_name="JUAN DAVID BARRIOS")
    assert str(c.id) in _ids(admin_client.get(RUTA, {"search": "juan david"}))


def test_encuentra_por_numero_de_ticket(admin_client, admin_user, org_a):
    """El numero es con lo que se cruza la pantalla contra la del proveedor."""
    buscado = _caso(org_a, admin_user, provider="wisphub",
                    external_ticket_id="94553")
    otro = _caso(org_a, admin_user, provider="wisphub",
                 external_ticket_id="94800", description="otro ticket")

    ids = _ids(admin_client.get(RUTA, {"search": "94553"}))
    assert str(buscado.id) in ids
    assert str(otro.id) not in ids


def test_el_numero_es_exacto_y_no_un_fragmento(admin_client, admin_user, org_a):
    """Buscar '553' NO tiene por que traer el 94553.

    Con 'icontains' sobre el numero, cualquier fragmento arrastraria decenas
    de tickets sin relacion. Un identificador se busca entero.
    """
    c = _caso(org_a, admin_user, provider="wisphub", external_ticket_id="94553",
              description="sin referencias")
    assert str(c.id) not in _ids(admin_client.get(RUTA, {"search": "553"}))


def test_sigue_encontrando_por_asunto_y_descripcion(
        admin_client, admin_user, org_a):
    """Lo que ya funcionaba no se rompe: la busqueda SUMA terminos."""
    por_asunto = _caso(org_a, admin_user, name="Problemas De Tv")
    por_desc = _caso(org_a, admin_user, name="Otro",
                     description="cliente reporta corte en el sector norte")

    assert str(por_asunto.id) in _ids(admin_client.get(RUTA, {"search": "Tv"}))
    assert str(por_desc.id) in _ids(admin_client.get(RUTA, {"search": "sector norte"}))


def test_la_busqueda_no_cruza_organizaciones(
        admin_client, admin_user, org_a, org_b, user_b):
    """Un termino que coincide en otra empresa no la trae."""
    ajeno = Case.objects.create(
        name=REPETIDO, status="New", priority="Low", case_type="Question",
        description="x", created_by=user_b, org=org_b,
        external_client_name="JUAN DAVID BARRIOS")

    assert str(ajeno.id) not in _ids(admin_client.get(RUTA, {"search": "BARRIOS"}))


def test_sin_termino_devuelve_la_cola_entera(admin_client, admin_user, org_a):
    """Un 'search' vacio no filtra: la lista sigue siendo la lista."""
    _caso(org_a, admin_user, external_client_name="UNO")
    _caso(org_a, admin_user, external_client_name="DOS")

    assert len(_ids(admin_client.get(RUTA, {"search": ""}))) == 2
