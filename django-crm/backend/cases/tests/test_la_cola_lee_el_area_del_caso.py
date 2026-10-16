# -*- coding: utf-8 -*-
"""
================================================================================
 LA COLA DE TICKETS LEE EL AREA DEL CASO, NO LA DE QUIEN LO TIENE ASIGNADO
================================================================================

EL DEFECTO, MEDIDO EN LOCAL EL 16/10/2026
-----------------------------------------
La pantalla de Tickets deducia el area de cada caso de la PERSONA asignada::

    Case.area = soporte_tecnico       65
    pantalla "Soporte Técnico"        64
    pantalla "Sin área asignada"       6

El que faltaba --"Sin internet, LOS en rojo"-- tenia area 'soporte_tecnico'
y estaba asignado a alguien sin area en el motor, asi que la pantalla lo
mandaba a "Sin área asignada". Y la consecuencia grave es la inversa: un
ticket de ventas asignado a un tecnico aparecia como Soporte Tecnico -- el
mismo defecto que el Supervisor NOC ya no tiene desde cdaa9b27, vivo en esta
pantalla.

'Case.area' existe desde ese commit. Lo que faltaba era que la lista lo
expusiera y filtrara por el.

QUE SE AFIRMA, Y POR QUE ASI
----------------------------
Sobre el EFECTO, a traves del endpoint real: que ids llegan con '?area=...',
y que cuenta cada fila del desglose. Se afirma con el mismo par de mitades
del Supervisor, porque la asimetria ES el arreglo:

  * un caso CON area ajena no entra, aunque lo tenga un tecnico;
  * un caso SIN area entra con el criterio de ayer, su responsable, y solo si
    quien llama lo nombra en 'area_responsables'.

Cada prueba siembra el caso que tiene que quedar AFUERA junto al que tiene
que quedar ADENTRO: sin el de control, una cola vacia tambien seria verde.
================================================================================
"""
import pytest

from cases.models import Case
from common.models import Profile, User

pytestmark = pytest.mark.django_db

RUTA = "/api/cases/?limit=25&slim=true"


def _persona(org, correo):
    u = User.objects.create(email=correo, name=correo.split("@")[0])
    return Profile.objects.create(org=org, user=u, role="USER", is_active=True)


def _caso(org, creador, *, area, responsable=None, nombre="No tiene internet",
          estado="New", prioridad="Low"):
    caso = Case.objects.create(
        name=nombre, status=estado, priority=prioridad, case_type="Question",
        description="x", created_by=creador, org=org, area=area,
    )
    if responsable is not None:
        caso.assigned_to.add(responsable)
    return caso


def _ids(cuerpo):
    return {c["id"] for c in cuerpo["cases"]}


@pytest.fixture
def equipo(org_a):
    """Un tecnico, una persona de cartera y alguien sin area en el motor."""
    return {
        "tecnico": _persona(org_a, "tecnico@x.test"),
        "cartera": _persona(org_a, "cartera@x.test"),
        "sin_area": _persona(org_a, "nuevo@x.test"),
    }


def _cola_de_soporte(admin_client, *responsables):
    """Lo que la pantalla pide para la tarjeta de Soporte Tecnico."""
    extra = "".join(f"&area_responsables={p.id}" for p in responsables)
    return admin_client.get(f"{RUTA}&area=soporte_tecnico{extra}").json()


# =============================================================================
#  §1  EL AREA ESCRITA EN EL CASO MANDA
# =============================================================================

def test_el_caso_de_soporte_asignado_a_alguien_SIN_area_SI_esta_en_su_cola(
        admin_client, admin_user, org_a, equipo):
    """El ticket que faltaba: 'LOS en rojo', area soporte, responsable sin area."""
    los = _caso(org_a, admin_user, area="soporte_tecnico",
                responsable=equipo["sin_area"], nombre="Sin internet, LOS en rojo")
    control = _caso(org_a, admin_user, area="cartera",
                    responsable=equipo["sin_area"], nombre="Descuento programado")

    ids = _ids(_cola_de_soporte(admin_client, equipo["tecnico"]))

    assert str(los.id) in ids, (
        "un ticket de soporte no deja de serlo porque su responsable no "
        "tenga area configurada en el motor")
    assert str(control.id) not in ids


def test_el_caso_de_VENTAS_asignado_a_un_tecnico_NO_esta_en_la_de_soporte(
        admin_client, admin_user, org_a, equipo):
    """La consecuencia grave: el defecto del Supervisor, vivo en la pantalla."""
    ajeno = _caso(org_a, admin_user, area="ventas",
                  responsable=equipo["tecnico"], nombre="Cotización plan nuevo")
    propio = _caso(org_a, admin_user, area="soporte_tecnico",
                   responsable=equipo["tecnico"])

    ids = _ids(_cola_de_soporte(admin_client, equipo["tecnico"]))

    assert str(ajeno.id) not in ids, (
        "un ticket de ventas no es de soporte porque se lo hayan asignado a "
        "un técnico")
    assert str(propio.id) in ids


def test_el_area_del_caso_manda_sobre_la_de_la_persona(
        admin_client, admin_user, org_a, equipo):
    """Area propia, persona de otra area: entra, porque el trabajo es de soporte."""
    propio = _caso(org_a, admin_user, area="soporte_tecnico",
                   responsable=equipo["cartera"])

    assert str(propio.id) in _ids(_cola_de_soporte(admin_client, equipo["tecnico"]))


def test_un_caso_de_soporte_sin_responsable_tambien_entra(
        admin_client, admin_user, org_a, equipo):
    """La cola 'sin asignar' de un area es parte del area, no de 'Sin área'."""
    suelto = _caso(org_a, admin_user, area="soporte_tecnico", responsable=None)
    control = _caso(org_a, admin_user, area="", responsable=None)

    ids = _ids(_cola_de_soporte(admin_client, equipo["tecnico"]))

    assert str(suelto.id) in ids
    assert str(control.id) not in ids, "sin area y sin nadie no es de ningun area"


# =============================================================================
#  §2  LOS CASOS SIN AREA ESCRITA SIGUEN CON EL CRITERIO DE AYER
# =============================================================================

def test_un_caso_SIN_area_entra_por_su_responsable_solo_si_se_lo_nombra(
        admin_client, admin_user, org_a, equipo):
    """
    Los ~1.300 importados antes del campo, y los cargados a mano. Si dejaran
    de entrar, Soporte Tecnico se quedaria sin cola de un dia para el otro.
    """
    viejo = _caso(org_a, admin_user, area="", responsable=equipo["tecnico"])

    con_la_gente = _ids(_cola_de_soporte(admin_client, equipo["tecnico"]))
    sin_la_gente = _ids(_cola_de_soporte(admin_client))

    assert str(viejo.id) in con_la_gente
    assert str(viejo.id) not in sin_la_gente, (
        "sin 'area_responsables' no hay con que atribuir un caso sin area: "
        "atribuirlo igual seria adivinar")


def test_un_caso_SIN_area_de_alguien_de_otra_area_NO_entra(
        admin_client, admin_user, org_a, equipo):
    """La mitad vieja del filtro sigue siendo la de siempre."""
    viejo = _caso(org_a, admin_user, area="", responsable=equipo["cartera"])

    assert str(viejo.id) not in _ids(_cola_de_soporte(admin_client, equipo["tecnico"]))


def test_un_caso_SIN_area_con_DOS_responsables_del_area_sale_una_sola_vez(
        admin_client, admin_user, org_a, equipo):
    """
    LA AUDITORIA DEL 16/10 lo encontro quitando el '.distinct()': con la mitad
    vieja hecha con un join al M2M, un caso con dos responsables salia dos
    veces, 'cases_count' decia 2 y la paginacion se corria. Las once pruebas
    de entonces seguian verdes porque ninguna tenia un caso compartido y
    '_ids' es un set, que esconde el duplicado. Aca se mira la LISTA.
    """
    otro = _persona(org_a, "tecnico2@x.test")
    compartido = _caso(org_a, admin_user, area="", responsable=equipo["tecnico"])
    compartido.assigned_to.add(otro)

    cuerpo = _cola_de_soporte(admin_client, equipo["tecnico"], otro)

    assert [c["id"] for c in cuerpo["cases"]] == [str(compartido.id)]
    assert cuerpo["cases_count"] == 1
    assert cuerpo["open_count"] == 1


def test_se_honran_TODOS_los_responsables_del_area_no_solo_el_primero(
        admin_client, admin_user, org_a, equipo):
    """
    Soporte tiene varios tecnicos. La mutacion que solo mira el primer
    'area_responsables' dejaba verdes las pruebas de un solo responsable, y
    en produccion borraria de la cola los viejos de todos menos uno.
    """
    tecnicos = [equipo["tecnico"], _persona(org_a, "t2@x.test"), _persona(org_a, "t3@x.test")]
    viejos = [_caso(org_a, admin_user, area="", responsable=t) for t in tecnicos]

    cuerpo = _cola_de_soporte(admin_client, *tecnicos)

    assert _ids(cuerpo) == {str(c.id) for c in viejos}
    assert cuerpo["cases_count"] == 3


def test_area_responsables_SIN_area_no_filtra_nada(
        admin_client, admin_user, org_a, equipo):
    """
    Solo tiene sentido como la mitad vieja de un area concreta. A solas no es
    un filtro: se ignora, y la cola es la de siempre.
    """
    de_cartera = _caso(org_a, admin_user, area="cartera", responsable=equipo["cartera"])
    viejo = _caso(org_a, admin_user, area="", responsable=equipo["tecnico"])

    ids = _ids(admin_client.get(
        f"{RUTA}&area_responsables={equipo['tecnico'].id}").json())

    assert {str(de_cartera.id), str(viejo.id)} <= ids


# =============================================================================
#  §3  EL AREA SE CRUZA CON LOS DEMAS FILTROS, NO LOS PISA
# =============================================================================

def test_el_responsable_elegido_en_la_barra_se_cruza_con_el_area(
        admin_client, admin_user, org_a, equipo):
    """
    Elegir a alguien dentro de un area muestra sus tickets DE ESA AREA: lo
    que el filtro visible dice. Antes el area se mandaba COMO 'assigned_to',
    y los dos filtros no podian convivir.
    """
    de_soporte = _caso(org_a, admin_user, area="soporte_tecnico",
                       responsable=equipo["cartera"])
    de_cartera = _caso(org_a, admin_user, area="cartera",
                       responsable=equipo["cartera"])
    de_otro = _caso(org_a, admin_user, area="soporte_tecnico",
                    responsable=equipo["tecnico"])

    ids = _ids(admin_client.get(
        f"{RUTA}&area=soporte_tecnico&assigned_to={equipo['cartera'].id}").json())

    assert ids == {str(de_soporte.id)}, (
        f"se esperaba solo el de soporte de cartera; "
        f"cartera={str(de_cartera.id) in ids} otro={str(de_otro.id) in ids}")


def test_la_pagina_que_llega_es_la_del_area_aunque_lo_reciente_sea_de_otra(
        admin_client, admin_user, org_a, equipo):
    """
    EL DEFECTO DEL 07/10, con el filtro nuevo: 138 abiertos, las 25 mas
    recientes todas de cartera, y Soporte Tecnico salia VACIO con la cabecera
    diciendo 91. El recorte tiene que pasar en el servidor.
    """
    de_soporte = [_caso(org_a, admin_user, area="soporte_tecnico",
                        responsable=equipo["tecnico"]) for _ in range(5)]
    for _ in range(30):     # mas recientes que los de soporte, y mas que una pagina
        _caso(org_a, admin_user, area="cartera", responsable=equipo["cartera"])

    cuerpo = _cola_de_soporte(admin_client, equipo["tecnico"])

    assert cuerpo["cases_count"] == 5
    assert _ids(cuerpo) == {str(c.id) for c in de_soporte}


# =============================================================================
#  §4  EL DESGLOSE Y CADA FILA DICEN SU AREA
# =============================================================================

def test_el_desglose_separa_por_area_a_la_misma_persona(
        admin_client, admin_user, org_a, equipo):
    """
    Un tecnico con 3 de soporte, 2 de ventas y 1 viejo sin area: tres filas,
    no una. Es lo que permite que la tarjeta de Ventas no sume como Soporte.
    """
    for _ in range(3):
        _caso(org_a, admin_user, area="soporte_tecnico", responsable=equipo["tecnico"])
    for _ in range(2):
        _caso(org_a, admin_user, area="ventas", responsable=equipo["tecnico"])
    _caso(org_a, admin_user, area="", responsable=equipo["tecnico"])

    cuerpo = admin_client.get(RUTA).json()
    del_tecnico = {f["area"]: f["total"] for f in cuerpo["open_by_assignee"]
                   if f["assigned_to"] == str(equipo["tecnico"].id)}

    assert del_tecnico == {"soporte_tecnico": 3, "ventas": 2, "": 1}
    assert sum(f["total"] for f in cuerpo["open_by_assignee"]) == cuerpo["open_count"] == 6


def test_cada_fila_de_la_cola_dice_su_area(admin_client, admin_user, org_a, equipo):
    """Sin esto la pantalla no tiene de donde leerla, y vuelve a deducirla."""
    _caso(org_a, admin_user, area="ventas", responsable=equipo["tecnico"])

    (fila,) = admin_client.get(RUTA).json()["cases"]

    assert fila["area"] == "ventas"
