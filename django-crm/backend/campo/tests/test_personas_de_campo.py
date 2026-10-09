# -*- coding: utf-8 -*-
"""
================================================================================
 UN AUXILIAR SIN CELULAR TAMBIEN INTEGRA LA CUADRILLA
================================================================================

Que cubre y por que
-------------------
`IntegranteDeJornada` apuntaba a `Profile`, que exige un `User` con correo y
credenciales: o sea que anotar a un auxiliar obligaba a inventarle una cuenta
que nadie iba a usar. Y el catalogo de roles ya ofrecia 'ayudante' y 'chofer'
(ver `AsignacionTrabajo.ROLES_CUADRILLA`) para gente que el modelo no permitia
registrar.

Lo que se verifica aqui es el EFECTO, no que el campo exista:

  - un auxiliar SIN cuenta queda anotado en la jornada y se lee quien estuvo
  - el reparto le asigna la orden SOLO a quien entra al sistema, porque una
    orden asignada a quien no tiene telefono no la ve nadie
  - una cuadrilla donde NADIE tiene cuenta no recibe trabajo, y se dice cual
  - la guarda de "una persona en dos cuadrillas el mismo dia" ahora alcanza a
    los auxiliares, que antes no podian estar anotados en ningun lado
  - enlazarle una cuenta a un auxiliar NO le parte el historial en dos
  - dar de baja no borra: sus jornadas siguen explicando quien estuvo

Corre contra PostgreSQL de verdad: el `UniqueConstraint` con condicion no se
comporta igual en SQLite, y esta suite ya escondio dos defectos asi el
04/10/2026.

    pytest campo/tests/test_personas_de_campo.py
================================================================================
"""

import pytest

from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla, PersonaDeCampo)

pytestmark = pytest.mark.django_db

PERSONAS = "/api/campo/personas-de-campo/"
JORNADA = "/api/campo/cuadrillas/jornada/"
REPARTO = "/api/campo/cuadrillas/reparto/"

LUNES = "2026-10-05"
MARTES = "2026-10-06"


@pytest.fixture
def version(org_a):
    from campo.models import WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )


@pytest.fixture
def cuadrilla(org_a, admin_profile):
    return Cuadrilla.objects.create(
        org=org_a, nombre="Cuadrilla 1", lider=admin_profile
    )


def _armar(client, cuadrilla, fecha, integrantes=(), labor="instalacion"):
    return client.post(
        JORNADA,
        {
            "cuadrilla": str(cuadrilla.id),
            "fecha": fecha,
            "labor": labor,
            "integrantes": list(integrantes),
        },
        format="json",
    )


# ---------------------------------------------------------------------------
# A · dar de alta a alguien que no tiene cuenta
# ---------------------------------------------------------------------------

def test_a_un_auxiliar_sin_cuenta_se_puede_dar_de_alta(admin_client):
    """Lo que antes era imposible: registrar a quien no entra al sistema."""
    r = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                          format="json")
    assert r.status_code == 201, r.content
    cuerpo = r.json()
    assert cuerpo["nombre"] == "Pedro Ayudante"
    assert cuerpo["profile"] is None
    # Y se DICE que no tiene cuenta: de eso depende si puede recibir trabajo
    # en un telefono, asi que la pantalla lo necesita antes de repartir.
    assert cuerpo["tiene_cuenta"] is False
    assert cuerpo["rol_habitual"] == "ayudante"


def test_b_sin_nombre_no_se_crea(admin_client):
    r = admin_client.post(PERSONAS, {"nombre": "   "}, format="json")
    assert r.status_code == 400
    assert PersonaDeCampo.objects.count() == 0


def test_c_un_rol_que_no_existe_se_rechaza_y_dice_cuales_son(admin_client):
    r = admin_client.post(
        PERSONAS, {"nombre": "Pedro", "rol_habitual": "capataz"},
        format="json")
    assert r.status_code == 400
    assert "ayudante" in r.json()["detail"]


def test_d_un_homonimo_se_avisa_pero_no_se_bloquea(admin_client):
    """Dos personas se pueden llamar igual de verdad.

    Bloquear la segunda obligaria a deformarle el nombre para poder cargarla,
    asi que se avisa y decide quien carga.
    """
    admin_client.post(PERSONAS, {"nombre": "Juan Perez"}, format="json")
    r = admin_client.post(PERSONAS, {"nombre": "juan perez"}, format="json")
    assert r.status_code == 201
    assert r.json()["homonimos"] == 1
    assert PersonaDeCampo.objects.count() == 2


def test_e_la_misma_cuenta_no_se_da_de_alta_dos_veces(
    admin_client, admin_profile
):
    """Seria la misma persona dos veces, con el historial partido al medio."""
    r1 = admin_client.post(PERSONAS, {"profile": str(admin_profile.id)},
                           format="json")
    assert r1.status_code == 201
    assert r1.json()["tiene_cuenta"] is True

    r2 = admin_client.post(PERSONAS, {"profile": str(admin_profile.id)},
                           format="json")
    assert r2.status_code == 409
    assert PersonaDeCampo.objects.filter(profile=admin_profile).count() == 1


def test_f_las_cuentas_sin_persona_se_ofrecen_para_darlas_de_alta(
    admin_client, admin_profile, user_profile
):
    """Para que dar de alta al equipo que ya existe no sea cargarlo a mano."""
    antes = admin_client.get(PERSONAS).json()
    pendientes = {p["profile"] for p in antes["cuentas_sin_persona"]}
    assert str(admin_profile.id) in pendientes
    assert str(user_profile.id) in pendientes

    admin_client.post(PERSONAS, {"profile": str(admin_profile.id)},
                      format="json")
    despues = admin_client.get(PERSONAS).json()
    pendientes = {p["profile"] for p in despues["cuentas_sin_persona"]}
    # Ya dada de alta: deja de ofrecerse, o el alta chocaria con la unicidad.
    assert str(admin_profile.id) not in pendientes
    assert str(user_profile.id) in pendientes


def test_g_una_cuenta_dada_de_baja_no_vuelve_a_ofrecerse(
    admin_client, admin_profile
):
    """El filtro de pendientes mira TODAS las personas, no solo las activas.

    Si mirara solo las activas, la cuenta de alguien dado de baja volveria a
    la lista de pendientes y el alta fallaria por la unicidad -- con un error
    que no explica nada.
    """
    alta = admin_client.post(PERSONAS, {"profile": str(admin_profile.id)},
                             format="json").json()
    admin_client.patch(f"{PERSONAS}{alta['id']}/", {"activa": False},
                       format="json")

    cuerpo = admin_client.get(PERSONAS).json()
    pendientes = {p["profile"] for p in cuerpo["cuentas_sin_persona"]}
    assert str(admin_profile.id) not in pendientes


# ---------------------------------------------------------------------------
# B · armar el dia con un auxiliar
# ---------------------------------------------------------------------------

def test_h_el_auxiliar_queda_en_la_jornada_y_se_lee_quien_estuvo(
    admin_client, cuadrilla, admin_profile
):
    """La pregunta que no se podia contestar: que auxiliar estuvo que dia."""
    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()

    r = _armar(admin_client, cuadrilla, LUNES, [
        {"profile": str(admin_profile.id), "rol": "tecnico_lider"},
        {"persona": aux["id"], "rol": "ayudante"},
    ])
    assert r.status_code == 200, r.content

    gente = r.json()["integrantes"]
    assert len(gente) == 2
    por_nombre = {i["nombre"]: i for i in gente}
    assert por_nombre["Pedro Ayudante"]["rol"] == "ayudante"
    assert por_nombre["Pedro Ayudante"]["tiene_cuenta"] is False
    assert por_nombre["Pedro Ayudante"]["profile"] is None


def test_i_sin_rol_se_usa_el_habitual_de_la_persona(
    admin_client, cuadrilla
):
    """Para no retipear cada mañana lo que ya se sabe de esa persona."""
    chofer = admin_client.post(
        PERSONAS, {"nombre": "Luis Chofer", "rol_habitual": "chofer"},
        format="json").json()

    r = _armar(admin_client, cuadrilla, LUNES, [{"persona": chofer["id"]}])
    assert [i["rol"] for i in r.json()["integrantes"]] == ["chofer"]


def test_j_un_auxiliar_en_dos_cuadrillas_el_mismo_dia_se_rechaza(
    admin_client, org_a, cuadrilla
):
    """La guarda ahora ALCANZA a los auxiliares.

    Antes no podia: un auxiliar no estaba anotado en ningun lado, asi que
    doblarlo entre dos cuadrillas no lo veia nadie y las dos contaban con el.
    """
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()

    assert _armar(admin_client, cuadrilla, LUNES,
                  [{"persona": aux["id"], "rol": "ayudante"}]).status_code == 200
    choque = _armar(admin_client, otra, LUNES,
                    [{"persona": aux["id"], "rol": "ayudante"}])
    assert choque.status_code == 409
    assert "Cuadrilla 1" in choque.json()["detail"]


def test_k_pero_el_dia_siguiente_SI_puede_estar_en_otra(
    admin_client, org_a, cuadrilla
):
    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()

    assert _armar(admin_client, cuadrilla, LUNES,
                  [{"persona": aux["id"]}]).status_code == 200
    assert _armar(admin_client, otra, MARTES,
                  [{"persona": aux["id"]}]).status_code == 200
    assert IntegranteDeJornada.objects.filter(persona_id=aux["id"]).count() == 2


def test_l_una_persona_de_otra_empresa_no_entra(
    admin_client, cuadrilla, org_b
):
    ajena = PersonaDeCampo.objects.create(org=org_b, nombre="De otra empresa")
    r = _armar(admin_client, cuadrilla, LUNES, [{"persona": str(ajena.id)}])
    assert r.status_code == 409
    assert "esta empresa" in r.json()["detail"]


# ---------------------------------------------------------------------------
# C · el historial, que es para lo que existe todo esto
# ---------------------------------------------------------------------------

def test_m_con_que_lider_estuvo_el_auxiliar_cada_dia(
    admin_client, org_a, cuadrilla, admin_profile, user_profile
):
    """La pregunta original: que auxiliar estuvo que dia con que lider."""
    otra = Cuadrilla.objects.create(
        org=org_a, nombre="Cuadrilla 2", lider=user_profile
    )
    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()

    _armar(admin_client, cuadrilla, LUNES, [{"persona": aux["id"]}])
    _armar(admin_client, otra, MARTES, [{"persona": aux["id"]}])

    r = admin_client.get(JORNADA, {"desde": LUNES, "hasta": MARTES,
                                   "persona": aux["id"]})
    jornadas = r.json()["jornadas"]
    assert [(j["fecha"], j["cuadrilla"]["nombre"]) for j in jornadas] == [
        (LUNES, "Cuadrilla 1"),
        (MARTES, "Cuadrilla 2"),
    ]


def test_n_enlazarle_una_cuenta_NO_le_parte_el_historial(
    admin_client, cuadrilla, user_profile
):
    """El auxiliar al que le asignan celular.

    Se le engancha la cuenta a la MISMA fila, asi que sus jornadas anteriores
    siguen siendo suyas. Si naciera una persona nueva, su historial empezaria
    de cero y el de antes quedaria colgado de un nombre sin dueño.
    """
    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()
    _armar(admin_client, cuadrilla, LUNES, [{"persona": aux["id"]}])

    r = admin_client.patch(f"{PERSONAS}{aux['id']}/",
                           {"profile": str(user_profile.id)}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["tiene_cuenta"] is True

    # LA MISMA FILA, y la jornada del lunes sigue apuntando a ella.
    assert PersonaDeCampo.objects.count() == 1
    assert IntegranteDeJornada.objects.filter(persona_id=aux["id"]).count() == 1
    # Y ahora se la encuentra tambien por su cuenta.
    jornadas = admin_client.get(
        JORNADA, {"desde": LUNES, "hasta": MARTES,
                  "profile": str(user_profile.id)}
    ).json()["jornadas"]
    assert [j["fecha"] for j in jornadas] == [LUNES]


def test_o_una_cuenta_que_ya_es_de_otra_persona_no_se_enlaza(
    admin_client, admin_profile
):
    uno = admin_client.post(PERSONAS, {"profile": str(admin_profile.id)},
                            format="json").json()
    otro = admin_client.post(PERSONAS, {"nombre": "Pedro"},
                             format="json").json()

    r = admin_client.patch(f"{PERSONAS}{otro['id']}/",
                           {"profile": str(admin_profile.id)}, format="json")
    assert r.status_code == 409
    assert PersonaDeCampo.objects.get(id=uno["id"]).profile_id == admin_profile.id


def test_p_dar_de_baja_no_borra_lo_que_ya_estuvo(
    admin_client, cuadrilla
):
    """Sus jornadas son las que explican quien estuvo cada dia."""
    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()
    _armar(admin_client, cuadrilla, LUNES, [{"persona": aux["id"]}])

    r = admin_client.patch(f"{PERSONAS}{aux['id']}/", {"activa": False},
                           format="json")
    assert r.status_code == 200
    assert r.json()["activa"] is False

    # La fila sigue, y la jornada del lunes sigue nombrandola.
    assert IntegranteDeJornada.objects.filter(persona_id=aux["id"]).count() == 1
    jornada = admin_client.get(JORNADA, {"fecha": LUNES}).json()["jornadas"][0]
    assert [i["nombre"] for i in jornada["integrantes"]] == ["Pedro Ayudante"]

    # Pero ya no se puede anotar en un dia nuevo: la baja fue una decision.
    assert _armar(admin_client, cuadrilla, MARTES,
                  [{"persona": aux["id"]}]).status_code == 409


def test_p2_una_persona_con_cuenta_dada_de_baja_tampoco_entra_POR_SU_CUENTA(
    admin_client, cuadrilla, user_profile
):
    """El camino por `profile`, que es otro que el camino por `persona`.

    La pantalla anterior enlazaba por cuenta y los historiales guardados usan
    ese id, asi que ese camino sigue vivo -- y la baja tiene que valer igual
    por los dos. Medido: la mutacion que borra este rechazo SOBREVIVIO a
    `test_p`, porque ahi se llega por el id de la persona y el primer filtro
    ya la excluye. Este caso es el que la caza.
    """
    alta = admin_client.post(PERSONAS, {"profile": str(user_profile.id)},
                             format="json").json()
    admin_client.patch(f"{PERSONAS}{alta['id']}/", {"activa": False},
                       format="json")

    r = _armar(admin_client, cuadrilla, LUNES,
               [{"profile": str(user_profile.id)}])
    assert r.status_code == 409
    assert IntegranteDeJornada.objects.count() == 0

# ---------------------------------------------------------------------------
# D · el reparto: a quien se le MANDA el trabajo
# ---------------------------------------------------------------------------

def _orden(org, version, numero=1):
    from campo.models import OrdenTrabajo

    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA,
    )


def test_q_solo_quien_tiene_cuenta_recibe_la_asignacion(
    admin_client, org_a, cuadrilla, admin_profile, version
):
    """Una orden asignada a quien no entra al sistema no la ve nadie.

    El auxiliar igual queda en la JORNADA --ahi se lee quien estuvo-- pero no
    es a quien se le manda el trabajo.
    """
    from campo.models import AsignacionTrabajo

    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()
    _armar(admin_client, cuadrilla, LUNES, [
        {"profile": str(admin_profile.id), "rol": "tecnico_lider"},
        {"persona": aux["id"], "rol": "ayudante"},
    ])
    jornada = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=LUNES)
    orden = _orden(org_a, version)

    r = admin_client.post(REPARTO, {"asignaciones": [
        {"jornada": str(jornada.id), "ordenes": [str(orden.id)]},
    ]}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["publicadas"] == 1

    asignadas = list(AsignacionTrabajo.objects.filter(orden=orden))
    assert [a.profile_id for a in asignadas] == [admin_profile.id]
    # Se DICE cuantos auxiliares integran la cuadrilla sin recibir asignacion:
    # es lo esperado, pero un silencio se leeria como gente perdida.
    assert r.json()["auxiliares_sin_asignacion"] == 1
    # Y la jornada sigue diciendo que el auxiliar estuvo.
    assert jornada.integrantes.count() == 2


def test_r_una_cuadrilla_donde_NADIE_tiene_cuenta_no_recibe_trabajo(
    admin_client, org_a, cuadrilla, version
):
    """La orden quedaria sin una sola asignacion y nadie la veria.

    Publicar cero asignaciones e informar exito seria peor que no publicar:
    la orden parece repartida y no esta en ningun telefono.
    """
    from campo.models import AsignacionTrabajo

    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()
    _armar(admin_client, cuadrilla, LUNES, [{"persona": aux["id"]}])
    jornada = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=LUNES)
    orden = _orden(org_a, version)

    r = admin_client.post(REPARTO, {"asignaciones": [
        {"jornada": str(jornada.id), "ordenes": [str(orden.id)]},
    ]}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["publicadas"] == 0
    # Y se NOMBRA cual quedo afuera: la cuenta no cuadraria con lo que se vio.
    assert r.json()["sin_nadie_con_cuenta"] == ["Cuadrilla 1"]
    assert AsignacionTrabajo.objects.filter(orden=orden).count() == 0


def test_s_el_lider_queda_como_principal_aunque_haya_auxiliares(
    admin_client, org_a, cuadrilla, admin_profile, version
):
    from campo.models import AsignacionTrabajo

    aux = admin_client.post(PERSONAS, {"nombre": "Pedro Ayudante"},
                            format="json").json()
    _armar(admin_client, cuadrilla, LUNES, [
        {"persona": aux["id"], "rol": "ayudante"},
        {"profile": str(admin_profile.id), "rol": "tecnico_lider"},
    ])
    jornada = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=LUNES)
    orden = _orden(org_a, version)

    admin_client.post(REPARTO, {"asignaciones": [
        {"jornada": str(jornada.id), "ordenes": [str(orden.id)]},
    ]}, format="json")

    principales = AsignacionTrabajo.objects.filter(
        orden=orden, es_principal=True
    )
    assert [a.profile_id for a in principales] == [admin_profile.id]


def test_t_dos_cuadrillas_cuentan_sus_auxiliares_juntas(
    admin_client, org_a, cuadrilla, admin_profile, user_profile, version
):
    """El numero se acumula entre cuadrillas.

    Con una variable por ciclo solo se guardaria la ultima, y con dos
    cuadrillas el numero mentiria.
    """
    otra = Cuadrilla.objects.create(
        org=org_a, nombre="Cuadrilla 2", lider=user_profile
    )
    a1 = admin_client.post(PERSONAS, {"nombre": "Aux Uno"},
                           format="json").json()
    a2 = admin_client.post(PERSONAS, {"nombre": "Aux Dos"},
                           format="json").json()

    _armar(admin_client, cuadrilla, LUNES, [
        {"profile": str(admin_profile.id), "rol": "tecnico_lider"},
        {"persona": a1["id"], "rol": "ayudante"},
    ])
    _armar(admin_client, otra, LUNES, [
        {"profile": str(user_profile.id), "rol": "tecnico_lider"},
        {"persona": a2["id"], "rol": "ayudante"},
    ])
    j1 = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=LUNES)
    j2 = JornadaDeCuadrilla.objects.get(cuadrilla=otra, fecha=LUNES)
    o1, o2 = _orden(org_a, version, 1), _orden(org_a, version, 2)

    r = admin_client.post(REPARTO, {"asignaciones": [
        {"jornada": str(j1.id), "ordenes": [str(o1.id)]},
        {"jornada": str(j2.id), "ordenes": [str(o2.id)]},
    ]}, format="json")
    assert r.json()["publicadas"] == 2
    assert r.json()["auxiliares_sin_asignacion"] == 2
