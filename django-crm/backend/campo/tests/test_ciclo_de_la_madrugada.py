# -*- coding: utf-8 -*-
"""
================================================================================
 EL CICLO DE LA MADRUGADA
================================================================================

Que cubre y por que
-------------------
El reparto automatico no existia por una razon declarada: «nadie deberia
programar a las 3 am algo que no vio funcionar a las 10». Lo que se construyo
entonces NO es publicar solo -- es dejar el dia armado y decir que hay que
mirar. El shadow mode queda intacto: una persona sigue publicando.

Se afirma sobre el EFECTO, no sobre la presencia del mecanismo:

  - la jornada del dia aparece sola, copiada del ultimo dia trabajado
  - correrlo dos veces deja lo mismo que correrlo una
  - una jornada armada a mano NO se pisa
  - quien esta de baja no se copia, y se dice cuantos quedaron afuera
  - una cuadrilla que nunca trabajo arranca con lo habitual
  - la hora es la LOCAL de cada empresa, no la del servidor
  - no corre dos veces el mismo dia
  - una empresa rota no deja sin jornada a las demas
  - el tope sale de la cuadrilla, y si no lo declara, de la empresa
  - lo que nadie empezo vuelve al reparto; lo empezado NO

Corre contra PostgreSQL de verdad.

    pytest campo/tests/test_ciclo_de_la_madrugada.py
================================================================================
"""

import datetime as dt

import pytest
from django.utils import timezone

from campo.cuadrillas import (ConfiguracionDeReparto, Cuadrilla,
                              IntegranteDeJornada, JornadaDeCuadrilla,
                              PersonaDeCampo)
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
MARTES = dt.date(2026, 10, 6)


@pytest.fixture
def norte(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    return z


@pytest.fixture
def cuadrilla(org_a, admin_profile):
    return Cuadrilla.objects.create(
        org=org_a, nombre="Cuadrilla 1", lider=admin_profile
    )


def _persona(org, nombre, activa=True):
    return PersonaDeCampo.objects.create(org=org, nombre=nombre, activa=activa)


def _jornada(org, cuadrilla, fecha, zonas=(), gente=()):
    j = JornadaDeCuadrilla.objects.create(
        org=org, cuadrilla=cuadrilla, fecha=fecha, labor="correctivo"
    )
    j.zonas.set(zonas)
    for persona, rol in gente:
        IntegranteDeJornada.objects.create(
            org=org, jornada=j, persona=persona, rol=rol
        )
    return j


# ---------------------------------------------------------------------------
# A · la jornada se arma sola
# ---------------------------------------------------------------------------

def test_a_la_jornada_del_dia_se_copia_del_ultimo_dia_trabajado(
    org_a, cuadrilla, norte
):
    """Sin esto el reparto automatico devuelve vacio todas las noches."""
    from campo import jornada_automatica

    pedro = _persona(org_a, "Pedro Ayudante")
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte], gente=[(pedro, "ayudante")])

    r = jornada_automatica.asegurar_jornadas(org_a, MARTES)

    assert [c["cuadrilla"] for c in r["copiadas"]] == ["Cuadrilla 1"]
    assert r["copiadas"][0]["desde"] == LUNES.isoformat()

    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=MARTES)
    assert nueva.labor == "correctivo"
    assert [z.nombre for z in nueva.zonas.all()] == ["Norte"]
    assert [(i.persona.nombre, i.rol) for i in nueva.integrantes.all()] == [
        ("Pedro Ayudante", "ayudante")
    ]


def test_b_correrlo_dos_veces_deja_lo_mismo_que_correrlo_una(
    org_a, cuadrilla, norte
):
    """Es la condicion para poder reintentarlo sin pensar."""
    from campo import jornada_automatica

    pedro = _persona(org_a, "Pedro")
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte], gente=[(pedro, "ayudante")])

    jornada_automatica.asegurar_jornadas(org_a, MARTES)
    segunda = jornada_automatica.asegurar_jornadas(org_a, MARTES)

    assert segunda["ya_estaban"] == ["Cuadrilla 1"]
    assert segunda["copiadas"] == []
    assert JornadaDeCuadrilla.objects.filter(fecha=MARTES).count() == 1
    assert IntegranteDeJornada.objects.filter(jornada__fecha=MARTES).count() == 1


def test_c_una_jornada_armada_a_mano_no_se_pisa(org_a, cuadrilla, norte):
    """La decision de una persona gana sobre un proceso de las 3 de la mañana."""
    from campo import jornada_automatica

    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])
    a_mano = _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    a_mano.labor = "trabajos"
    a_mano.save()

    jornada_automatica.asegurar_jornadas(org_a, MARTES)

    a_mano.refresh_from_db()
    assert a_mano.labor == "trabajos"


def test_d_quien_esta_de_baja_NO_se_copia_y_se_dice_cuantos(
    org_a, cuadrilla, norte
):
    """Copiar a alguien que ya no trabaja ahi lo pondria a recibir trabajo."""
    from campo import jornada_automatica

    activo = _persona(org_a, "Sigue Trabajando")
    de_baja = _persona(org_a, "Ya No Esta", activa=False)
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte],
             gente=[(activo, "tecnico"), (de_baja, "ayudante")])

    r = jornada_automatica.asegurar_jornadas(org_a, MARTES)

    assert r["copiadas"][0]["sin_gente"] == 1
    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=MARTES)
    assert [i.persona.nombre for i in nueva.integrantes.all()] == [
        "Sigue Trabajando"
    ]


def test_e_una_cuadrilla_que_nunca_trabajo_arranca_con_lo_habitual(
    org_a, cuadrilla, norte
):
    """El arranque en frio.

    Sin esto, una empresa recien dada de alta tendria que armar un dia entero
    a mano antes de que el ciclo sirviera para algo, y el sintoma seria «no se
    asigno nada» -- que no señala a la causa.
    """
    from campo import jornada_automatica

    cuadrilla.labor_habitual = "trabajos"
    cuadrilla.save()
    cuadrilla.zonas_habituales.set([norte])

    r = jornada_automatica.asegurar_jornadas(org_a, MARTES)

    assert r["estrenadas"] == ["Cuadrilla 1"]
    nueva = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=MARTES)
    assert nueva.labor == "trabajos"
    assert [z.nombre for z in nueva.zonas.all()] == ["Norte"]


def test_f_una_cuadrilla_sin_zona_queda_armada_pero_se_NOMBRA(
    org_a, cuadrilla
):
    """Vacio no es «cubre todas»: no va a recibir trabajo, y hay que saberlo."""
    from campo import jornada_automatica

    _jornada(org_a, cuadrilla, LUNES, zonas=[])

    r = jornada_automatica.asegurar_jornadas(org_a, MARTES)

    assert r["sin_zona"] == ["Cuadrilla 1"]
    assert JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


def test_g_una_cuadrilla_dada_de_baja_no_entra(org_a, cuadrilla, norte):
    from campo import jornada_automatica

    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])
    cuadrilla.activa = False
    cuadrilla.save()

    r = jornada_automatica.asegurar_jornadas(org_a, MARTES)

    assert r["copiadas"] == []
    assert not JornadaDeCuadrilla.objects.filter(fecha=MARTES).exists()


# ---------------------------------------------------------------------------
# B · la hora es la de cada empresa
# ---------------------------------------------------------------------------

def _config(org, **kw):
    datos = {"activo": True, "hora_local": 3, "tope_por_cuadrilla": 8}
    datos.update(kw)
    return ConfiguracionDeReparto.objects.create(org=org, **datos)


def test_h_apagado_de_fabrica(org_a):
    """Encender un proceso que corre todas las noches es de operacion.

    No puede pasar porque alguien desplego una version -- mismo criterio que
    `RELOJ_HABILITADO` en el motor.
    """
    from campo.cuadrillas import configuracion_de_reparto
    from campo.tasks import _le_toca

    config = configuracion_de_reparto(org_a)
    assert config.activo is False
    assert ConfiguracionDeReparto.objects.count() == 0, "leer no crea la fila"

    ahora = dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc)
    assert _le_toca(config, ahora) is False


def test_i_antes_de_su_hora_no_corre(org_a):
    from campo.tasks import _le_toca

    config = _config(org_a, hora_local=3)
    a_las_dos = dt.datetime(2026, 10, 6, 2, 59, tzinfo=dt.timezone.utc)
    assert _le_toca(config, a_las_dos) is False


def test_j_a_su_hora_corre(org_a):
    from campo.tasks import _le_toca

    config = _config(org_a, hora_local=3)
    a_las_tres = dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc)
    assert _le_toca(config, a_las_tres) is True


def test_k_una_corrida_perdida_se_recupera_a_la_hora_siguiente(org_a):
    """`>=` y no `==`.

    La tarea se dispara cada hora. Si el worker estaba caido a las 3, con `==`
    la empresa se saltearia el dia entero y nadie lo notaria hasta las siete.
    """
    from campo.tasks import _le_toca

    config = _config(org_a, hora_local=3)
    a_las_seis = dt.datetime(2026, 10, 6, 6, 5, tzinfo=dt.timezone.utc)
    assert _le_toca(config, a_las_seis) is True


def test_l_no_corre_dos_veces_el_mismo_dia(org_a):
    """Sin esto el supervisor recibiria el mismo aviso una vez por hora."""
    from campo.tasks import _le_toca

    config = _config(org_a, hora_local=3)
    config.ultima_corrida = dt.date(2026, 10, 6)
    config.save()

    a_las_cuatro = dt.datetime(2026, 10, 6, 4, 0, tzinfo=dt.timezone.utc)
    assert _le_toca(config, a_las_cuatro) is False

    # Pero al dia siguiente si.
    manana = dt.datetime(2026, 10, 7, 3, 5, tzinfo=dt.timezone.utc)
    assert _le_toca(config, manana) is True


def test_m_la_hora_es_la_LOCAL_de_la_empresa(org_a):
    """Beat corre en UTC y cada empresa lleva su `Org.timezone`.

    Las 3 de la mañana en Bogota son las 8 UTC. Una tarea fija a `hour=3` de
    beat correria a las 10 de la noche ANTERIOR alla.
    """
    from campo.tasks import _ahora_local

    org_a.timezone = "America/Bogota"
    org_a.save()

    local = _ahora_local(org_a)
    utc = timezone.now()
    assert local.utcoffset() == dt.timedelta(hours=-5)
    # El mismo instante, escrito en dos husos.
    assert abs((local - utc).total_seconds()) < 5


def test_n_una_zona_horaria_mal_escrita_no_deja_sin_ciclo(org_a):
    """Cae a UTC, que es visible. Saltearla seria un silencio."""
    from campo.tasks import _ahora_local

    org_a.timezone = "Marte/Olympus"
    org_a.save()
    assert _ahora_local(org_a).utcoffset() == dt.timedelta(0)


# ---------------------------------------------------------------------------
# C · el tope, configurable
# ---------------------------------------------------------------------------

def _orden(org, version, numero, localidad="MARTHA GISELA"):
    from campo.models import OrdenTrabajo

    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona=localidad,
    )


@pytest.fixture
def version(org_a):
    from campo.models import WorkType, WorkTypeVersion

    #  CON SU LABOR, y la misma que `_jornada` le pone a la cuadrilla: desde
    #  que el reparto filtra por labor, un tipo sin clasificar queda en
    #  `sin_clasificar` y no llega a ninguna cuadrilla. Una fixture sin labor
    #  haria fallar las pruebas del tope por un motivo que no es el tope.
    wt = WorkType.objects.create(org=org_a, codigo="ftth", nombre="FTTH",
                                 labor="correctivo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )


def test_o_el_tope_de_la_EMPRESA_acota_el_reparto(
    org_a, cuadrilla, norte, version
):
    from campo import reparto

    _config(org_a, tope_por_cuadrilla=2)
    _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    for n in range(1, 6):
        _orden(org_a, version, n)

    p = reparto.proponer(org_a, MARTES)
    assert len(p["asignaciones"][0]["ordenes"]) == 2
    assert len(p["sobrantes"]) == 3


def test_p_el_tope_de_la_CUADRILLA_le_gana_al_de_la_empresa(
    org_a, cuadrilla, norte, version
):
    """Una cuadrilla de dos no rinde lo mismo que una de cuatro.

    Un numero unico obliga a elegir entre sobrecargar a la chica o
    desaprovechar a la grande.
    """
    from campo import reparto

    _config(org_a, tope_por_cuadrilla=2)
    cuadrilla.tope_diario = 4
    cuadrilla.save()
    _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    for n in range(1, 6):
        _orden(org_a, version, n)

    p = reparto.proponer(org_a, MARTES)
    assert len(p["asignaciones"][0]["ordenes"]) == 4
    assert len(p["sobrantes"]) == 1


def test_q_sin_configuracion_vale_el_de_fabrica(
    org_a, cuadrilla, norte, version
):
    from campo import reparto

    _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    for n in range(1, 11):
        _orden(org_a, version, n)

    p = reparto.proponer(org_a, MARTES)
    assert len(p["asignaciones"][0]["ordenes"]) == ConfiguracionDeReparto.TOPE_DE_FABRICA


# ---------------------------------------------------------------------------
# D · quien empezo un trabajo lo termina
# ---------------------------------------------------------------------------

def test_r_lo_que_nadie_empezo_VUELVE_al_reparto(
    org_a, cuadrilla, norte, version, admin_profile
):
    """Antes se quedaba pegada a su cuadrilla aunque esa ya no cubriera su zona."""
    from campo.models import AsignacionTrabajo
    from campo import reparto

    _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    orden = _orden(org_a, version, 1)
    AsignacionTrabajo.objects.create(
        orden=orden, profile=admin_profile, rol="tecnico", es_principal=True
    )

    p = reparto.proponer(org_a, MARTES)
    assert [o.numero for o in p["asignaciones"][0]["ordenes"]] == [1]


def test_s_lo_que_YA_SE_EMPEZO_no_cambia_de_manos(
    org_a, cuadrilla, norte, version, admin_profile
):
    """Quien fue al sitio y hablo con el cliente sabe algo que el reparto no."""
    from campo.models import AsignacionTrabajo, EventoTrabajo
    from campo import reparto

    _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    orden = _orden(org_a, version, 1)
    AsignacionTrabajo.objects.create(
        orden=orden, profile=admin_profile, rol="tecnico", es_principal=True
    )
    EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo=reparto.EVENTO_INICIO
    )

    p = reparto.proponer(org_a, MARTES)
    assert p["asignaciones"][0]["ordenes"] == []


# ---------------------------------------------------------------------------
# E · el ciclo entero
# ---------------------------------------------------------------------------

def test_t_el_ciclo_deja_la_jornada_y_avisa(
    org_a, cuadrilla, norte, version, admin_profile
):
    from common.models import Notification
    from campo import tasks

    _config(org_a)
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])
    _orden(org_a, version, 1)

    ahora = dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc)
    r = tasks.correr_para(org_a, ahora_local=ahora)

    assert r["fecha"] == MARTES.isoformat()
    assert r["jornadas"]["copiadas"][0]["cuadrilla"] == "Cuadrilla 1"
    assert r["reparto"]["repartibles"] == 1

    avisos = Notification.objects.filter(org=org_a,
                                         verb="reparto_de_la_madrugada")
    assert avisos.count() == 1
    assert avisos.first().recipient_id == admin_profile.id
    # El aviso lleva el resumen, no solo un texto: la pantalla lo dibuja.
    assert avisos.first().data["reparto"]["repartibles"] == 1


def test_u_el_ciclo_NO_publica_ninguna_asignacion(
    org_a, cuadrilla, norte, version
):
    """El shadow mode queda intacto: una persona sigue publicando.

    `PropuestaSupervisor` no tiene estado `ejecutada`, y repartir el trabajo
    del dia sin que nadie mire cruzaria esa linea.
    """
    from campo.models import AsignacionTrabajo
    from campo import tasks

    _config(org_a)
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])
    _orden(org_a, version, 1)

    ahora = dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc)
    tasks.correr_para(org_a, ahora_local=ahora)

    assert AsignacionTrabajo.objects.count() == 0


def test_v_el_ciclo_marca_que_ya_corrio(org_a, cuadrilla, norte):
    from campo import tasks

    config = _config(org_a)
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])

    ahora = dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc)
    tasks.correr_para(org_a, ahora_local=ahora)

    config.refresh_from_db()
    assert config.ultima_corrida == MARTES


def test_w_una_empresa_rota_no_deja_sin_jornada_a_las_demas(
    org_a, org_b, cuadrilla, norte, monkeypatch
):
    """El mismo aislamiento que `nucleo/reloj.py` aprendio a tener.

    Alla una excepcion dejo un trabajo muerto un mes entero, sin log y sin
    sintoma.
    """
    from campo import tasks

    _config(org_a)
    _config(org_b)
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])

    original = tasks.correr_para

    def explota_para_b(org, **kw):
        if org.id == org_b.id:
            raise RuntimeError("config rota")
        return original(org, **kw)

    monkeypatch.setattr(tasks, "correr_para", explota_para_b)
    monkeypatch.setattr(
        tasks, "_ahora_local",
        lambda org: dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc),
    )

    r = tasks.ciclo_de_la_madrugada()

    assert [e["org"] for e in r["errores"]] == [str(org_b.id)]
    assert [c["org"] for c in r["corridas"]] == [str(org_a.id)]
    # Y la de la empresa sana quedo armada igual.
    assert JornadaDeCuadrilla.objects.filter(org=org_a, fecha=MARTES).exists()
    # El log lleva el TIPO, no el texto: un mensaje puede arrastrar datos de
    # cliente.
    assert r["errores"][0]["error"] == "RuntimeError"


# ---------------------------------------------------------------------------
# F · la labor: una cuadrilla de correctivo no recibe instalaciones
# ---------------------------------------------------------------------------

def _tipo(org, codigo, labor=""):
    from campo.models import WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo.upper(),
                                 labor=labor)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )


def test_x_una_cuadrilla_de_correctivo_NO_recibe_instalaciones(
    org_a, cuadrilla, norte
):
    """Hasta el 08/10/2026 la recibia: `labor` no se miraba en el reparto."""
    from campo import reparto

    j = _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    j.labor = "correctivo"
    j.save()

    instalacion = _tipo(org_a, "ftth", labor="instalacion")
    _orden(org_a, instalacion, 1)

    p = reparto.proponer(org_a, MARTES)
    assert p["asignaciones"][0]["ordenes"] == []
    # Y se NOMBRA: nadie cubre esa zona hoy CON esa labor.
    assert [o.numero for o in p["sin_cuadrilla"]] == [1]


def test_y_pero_SI_recibe_lo_de_su_labor(org_a, cuadrilla, norte):
    from campo import reparto

    j = _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    j.labor = "correctivo"
    j.save()

    soporte = _tipo(org_a, "soporte", labor="correctivo")
    _orden(org_a, soporte, 1)

    p = reparto.proponer(org_a, MARTES)
    assert [o.numero for o in p["asignaciones"][0]["ordenes"]] == [1]


def test_z_un_tipo_SIN_clasificar_no_se_reparte_y_se_dice_cual(
    org_a, cuadrilla, norte
):
    """Mismo criterio que la zona: lo que no se puede rutear bien no se rutea.

    Ningun codigo ('ftth', 'soporte', 'retiro') dice a que labor corresponde
    --cada empresa nombra los suyos-- asi que mandarlo a cualquier cuadrilla
    seria adivinar.
    """
    from campo import reparto

    _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    sin_clasificar = _tipo(org_a, "retiro", labor="")
    _orden(org_a, sin_clasificar, 1)

    p = reparto.proponer(org_a, MARTES)
    assert p["asignaciones"][0]["ordenes"] == []
    assert [o.numero for o in p["sin_clasificar"]] == [1]
    # NO cae en sin_zona: la zona estaba bien, lo que falta es la labor. Dos
    # problemas distintos se arreglan distinto.
    assert p["sin_zona"] == []


def test_z2_dos_cuadrillas_con_labores_distintas_reciben_lo_suyo(
    org_a, cuadrilla, norte
):
    """El caso real: una cuadrilla instala y otra atiende soporte."""
    from campo import reparto

    otra = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 2")
    j1 = _jornada(org_a, cuadrilla, MARTES, zonas=[norte])
    j1.labor = "instalacion"
    j1.save()
    j2 = _jornada(org_a, otra, MARTES, zonas=[norte])
    j2.labor = "correctivo"
    j2.save()

    instalacion = _tipo(org_a, "ftth", labor="instalacion")
    soporte = _tipo(org_a, "soporte", labor="correctivo")
    _orden(org_a, instalacion, 1)
    _orden(org_a, soporte, 2)

    p = reparto.proponer(org_a, MARTES)
    por_cuadrilla = {
        a["cuadrilla"].nombre: [o.numero for o in a["ordenes"]]
        for a in p["asignaciones"]
    }
    assert por_cuadrilla["Cuadrilla 1"] == [1]
    assert por_cuadrilla["Cuadrilla 2"] == [2]


def test_z3_el_aviso_nombra_los_TIPOS_sin_clasificar(org_a, cuadrilla, norte):
    """Se arregla una vez en el catalogo, no orden por orden.

    Por eso el aviso nombra el TIPO y no solo las ordenes: con treinta ordenes
    de un tipo sin clasificar, una lista de numeros no dice que hay que tocar
    un solo registro.
    """
    from campo import tasks

    _config(org_a)
    _jornada(org_a, cuadrilla, LUNES, zonas=[norte])
    retiro = _tipo(org_a, "retiro", labor="")
    _orden(org_a, retiro, 1)
    _orden(org_a, retiro, 2)

    ahora = dt.datetime(2026, 10, 6, 3, 5, tzinfo=dt.timezone.utc)
    r = tasks.correr_para(org_a, ahora_local=ahora)

    assert r["reparto"]["tipos_sin_clasificar"] == ["retiro"]
    assert sorted(r["reparto"]["sin_clasificar"]) == [1, 2]
