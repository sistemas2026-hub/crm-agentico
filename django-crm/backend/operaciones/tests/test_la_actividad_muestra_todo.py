# -*- coding: utf-8 -*-
"""
================================================================================
 EL PANEL DE ACTIVIDAD MUESTRA TODO LO QUE EL SUPERVISOR DEJA AUDITADO
================================================================================

EL AGUJERO QUE MOTIVA ESTO  --  medido el 15/10/2026
----------------------------------------------------
'auditoria.recientes' admitia CUATRO entidades y 'Case' no era una. Pero cuando
el Supervisor CIERRA un caso desincronizado, esa auditoria se escribe sobre el
CASO: 'cierre_de_caso.py' hace entity_type="Case", action="STATUS_CHANGED".

O sea que la accion con MAS EFECTO que el Supervisor hace hoy --veintiocho
casos cerrados solo el 14/10 en produccion-- era invisible en su propio panel de
actividad. Nadie lo noto porque el panel no estaba vacio: se llenaba de
propuestas generadas.

    PropuestaSupervisor CREATE    100   llegaba
    PropuestaSupervisor APPROVED   20   llegaba
    Case                CREATE     69   NO llegaba
    Case                ASSIGN     69   NO llegaba

Y UN ERROR DE AGRUPACION, que encontro el conteo
------------------------------------------------
La primera version agrupaba por ACCION sola, y dijo "propone: 169" cuando el
Supervisor habia generado 100 propuestas: los otros 69 eran 'Case CREATE' --
casos creados por otra via-- contados como si los hubiera propuesto el. Ahora
cada grupo es (entidad, accion), y hay una prueba abajo que lo fija.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from common.models import Activity
from operaciones import auditoria

pytestmark = pytest.mark.django_db


# =============================================================================
#  andamio
# =============================================================================

def _hecho(org, entidad, accion, nombre="algo", cuando=None):
    """Una fila de auditoria, como la escribe quien la escribe."""
    a = Activity.objects.create(
        org=org, user=None, action=accion, entity_type=entidad,
        entity_id=uuid.uuid4(), entity_name=nombre, description=nombre)
    if cuando is not None:
        Activity.objects.filter(pk=a.pk).update(created_at=cuando)
        a.refresh_from_db()
    return a


def _un_cierre_de_caso(org, nombre="Sin internet"):
    """
    Exactamente como lo escribe 'cierre_de_caso.py' cuando el Supervisor cierra.

    Se copian los dos valores de ahi --entity_type y action-- en vez de usar una
    constante propia: si ese modulo cambia alguno, esta prueba tiene que caerse,
    y con una constante compartida no se caeria.
    """
    return _hecho(org, "Case", "STATUS_CHANGED", nombre)


# =============================================================================
#  §1  EL AGUJERO: UN CIERRE TIENE QUE VERSE
# =============================================================================

def test_un_cierre_de_caso_SALE_en_el_panel(org_a):
    """
    LA PRUEBA QUE FALTABA. Antes del 15/10/2026 esto devolvia lista vacia.
    """
    cierre = _un_cierre_de_caso(org_a)

    ids = [a.id for a in auditoria.recientes(org_a, 20)]

    assert cierre.id in ids, (
        "el cierre de un caso no aparece en el feed: es la accion con mas "
        "efecto que hace el Supervisor y era invisible en su propio panel")


def test_y_tambien_filtrando_por_cierres(org_a):
    cierre = _un_cierre_de_caso(org_a)
    _hecho(org_a, "PropuestaSupervisor", "CREATE", "una propuesta")

    solo = list(auditoria.recientes(org_a, 20, grupo="cierra_caso"))

    assert [a.id for a in solo] == [cierre.id]


# =============================================================================
#  §2  EL FILTRO SEPARA, Y DICE CUANTOS HAY
# =============================================================================

def test_cada_grupo_trae_lo_suyo_y_nada_mas(org_a):
    paso = _hecho(org_a, "PropuestaSupervisor", "APPROVED", "pasa a despacho")
    propuso = _hecho(org_a, "PropuestaSupervisor", "CREATE", "propone")
    cerro = _un_cierre_de_caso(org_a)

    assert [a.id for a in auditoria.recientes(org_a, 20, grupo="pasa_a_despacho")] == [paso.id]
    assert [a.id for a in auditoria.recientes(org_a, 20, grupo="propone")] == [propuso.id]
    assert [a.id for a in auditoria.recientes(org_a, 20, grupo="cierra_caso")] == [cerro.id]


def test_el_conteo_dice_cuantos_hay_de_cada_uno(org_a):
    """
    Un selector que no dice cuantos hay obliga a probarlo para saber si sirve, y
    en un panel que se refresca solo eso significa apretarlo y no poder
    distinguir "no hay" de "todavia no llego".
    """
    for _ in range(3):
        _hecho(org_a, "PropuestaSupervisor", "APPROVED")
    for _ in range(5):
        _hecho(org_a, "PropuestaSupervisor", "CREATE")
    _un_cierre_de_caso(org_a)

    c = auditoria.cuantos_por_grupo(org_a)

    assert c["pasa_a_despacho"] == 3
    assert c["propone"] == 5
    assert c["cierra_caso"] == 1
    assert c["todo"] == 9


def test_el_conteo_NO_le_atribuye_al_supervisor_lo_que_no_hizo(org_a):
    """
    EL ERROR QUE ENCONTRO EL CONTEO, y por eso cada grupo es (entidad, accion).

    Un 'Case CREATE' es un caso creado --por la importacion, por una persona,
    por un script-- y NO una propuesta del Supervisor. Agrupando por accion sola
    se contaba ahi, y el panel decia que el Supervisor propuso cosas que no
    propuso.
    """
    _hecho(org_a, "PropuestaSupervisor", "CREATE", "esto si lo propuso el")
    for _ in range(4):
        _hecho(org_a, "Case", "CREATE", "esto no")

    c = auditoria.cuantos_por_grupo(org_a)

    assert c["propone"] == 1, (
        f"se le atribuyen al Supervisor casos que no propuso: {c}")
    assert c["otros"] == 4
    assert c["todo"] == 5


def test_lo_que_no_cae_en_ningun_grupo_va_a_OTROS_y_no_se_pierde(org_a):
    """
    Un hecho nuevo --una accion que hoy no existe-- tiene que aparecer en algun
    lado. Si cayera fuera de todos los grupos y de 'otros', desapareceria del
    panel sin que nadie lo note: la clase de falla que no da error.
    """
    raro = _hecho(org_a, "PropuestaSupervisor", "ACCION_QUE_NADIE_PREVIO")

    assert raro.id in [a.id for a in auditoria.recientes(org_a, 20, grupo="otros")]
    assert auditoria.cuantos_por_grupo(org_a)["otros"] == 1


# =============================================================================
#  §3  LOS CONTRAFACTICOS
# =============================================================================

def test_un_grupo_que_no_existe_devuelve_VACIO_y_no_todo(org_a):
    """
    Tratar lo que no se entiende como "sin filtro" mostraria MAS de lo que se
    pidio, y en un panel de auditoria esa es la peor direccion del error.
    """
    _hecho(org_a, "PropuestaSupervisor", "APPROVED")
    _un_cierre_de_caso(org_a)

    assert list(auditoria.recientes(org_a, 20, grupo="inventado")) == []


def test_la_actividad_de_OTRA_empresa_no_entra(org_a, org_b):
    _hecho(org_b, "PropuestaSupervisor", "APPROVED", "de la otra empresa")

    assert list(auditoria.recientes(org_a, 20)) == []
    assert auditoria.cuantos_por_grupo(org_a)["todo"] == 0


def test_lo_que_NO_es_de_este_modulo_sigue_sin_entrar(org_a):
    """
    El filtro por entidad no se afloja: su propio comentario dice que sin el, el
    feed se llenaria de "contactos editados y correos enviados, que es cierto
    pero no es lo que esta pantalla pregunta". Agregar 'Case' no abrio la puerta
    a todo.
    """
    _hecho(org_a, "Contact", "UPDATE", "un contacto editado")
    _hecho(org_a, "Invoice", "CREATE", "una factura")
    propio = _hecho(org_a, "PropuestaSupervisor", "APPROVED")

    assert [a.id for a in auditoria.recientes(org_a, 20)] == [propio.id]


# =============================================================================
#  §4  PAGINACION: MIRAR HACIA ATRAS SIN LIMITE
# =============================================================================

def test_la_pagina_siguiente_trae_hechos_MAS_VIEJOS(org_a):
    from datetime import timedelta

    ahora = timezone.now()
    #  Diez hechos, uno por minuto hacia atras.
    hechos = [_hecho(org_a, "PropuestaSupervisor", "CREATE", f"h{i}",
                     cuando=ahora - timedelta(minutes=i)) for i in range(10)]

    primera = list(auditoria.recientes(org_a, 4))
    segunda = list(auditoria.recientes(org_a, 4,
                                       antes_de=primera[-1].created_at))

    assert [a.entity_name for a in primera] == ["h0", "h1", "h2", "h3"]
    assert [a.entity_name for a in segunda] == ["h4", "h5", "h6", "h7"]


def test_la_paginacion_NO_repite_ni_saltea(org_a):
    """
    POR QUE POR FECHA Y NO POR 'offset': con filas entrando arriba todo el
    tiempo --el ciclo audita cada hora-- la pagina 2 por offset repetiria lo que
    la 1 mostro y saltearia otras. Un corte por 'created_at' no se mueve: lo que
    ya paso no cambia de lugar.
    """
    from datetime import timedelta

    ahora = timezone.now()
    for i in range(12):
        _hecho(org_a, "PropuestaSupervisor", "CREATE", f"h{i}",
               cuando=ahora - timedelta(minutes=i))

    vistos, corte = [], None
    for _ in range(4):
        pagina = list(auditoria.recientes(org_a, 3, antes_de=corte))
        if not pagina:
            break
        vistos += [a.entity_name for a in pagina]
        corte = pagina[-1].created_at

    assert vistos == [f"h{i}" for i in range(12)], (
        f"la paginacion repitio o salteo: {vistos}")
    assert len(vistos) == len(set(vistos)), "repitio alguno"


def test_paginar_respeta_el_filtro(org_a):
    """
    Si la pagina 2 trajera cosas de otro grupo, el filtro valdria solo para la
    primera -- y quien hojea hacia atras veria aparecer lo que habia filtrado.
    """
    from datetime import timedelta

    ahora = timezone.now()
    for i in range(6):
        _hecho(org_a, "PropuestaSupervisor", "APPROVED", f"paso{i}",
               cuando=ahora - timedelta(minutes=i * 2))
        _hecho(org_a, "PropuestaSupervisor", "CREATE", f"propuso{i}",
               cuando=ahora - timedelta(minutes=i * 2 + 1))

    p1 = list(auditoria.recientes(org_a, 3, grupo="pasa_a_despacho"))
    p2 = list(auditoria.recientes(org_a, 3, grupo="pasa_a_despacho",
                                  antes_de=p1[-1].created_at))

    assert [a.entity_name for a in p1] == ["paso0", "paso1", "paso2"]
    assert [a.entity_name for a in p2] == ["paso3", "paso4", "paso5"]


def test_cuando_no_queda_nada_mas_la_pagina_viene_vacia(org_a):
    """Y vacia significa "llegaste al final", no "fallo"."""
    from datetime import timedelta

    ahora = timezone.now()
    for i in range(3):
        _hecho(org_a, "PropuestaSupervisor", "CREATE", f"h{i}",
               cuando=ahora - timedelta(minutes=i))

    todos = list(auditoria.recientes(org_a, 10))
    assert list(auditoria.recientes(org_a, 10,
                                    antes_de=todos[-1].created_at)) == []


# =============================================================================
#  §5  EL CONTRATO HTTP, que es lo que el panel consume
# =============================================================================

#  La ruta REAL, de 'operaciones/urls.py'. La primera version de estas
#  pruebas la invento ("/api/operaciones/actividad/") y las cuatro fallaron
#  con "Content-Type es text/html": un 404 con pagina de error, no un JSON.
ACTIVIDAD = "/api/operaciones/actividad-supervisor/"


def test_la_vista_devuelve_los_conteos_y_con_que_seguir(admin_client, org_a):
    """
    Dos cosas que el frontend NO tiene que deducir: cuantos hay de cada grupo, y
    si queda mas hacia atras. Deducirlas contando la pagina da mal en el borde
    --una pagina llena puede ser la ultima-- y 'siguiente' lo dice sin ambiguedad.
    """
    _hecho(org_a, "PropuestaSupervisor", "APPROVED")
    _un_cierre_de_caso(org_a)

    cuerpo = admin_client.get(ACTIVIDAD).json()

    assert cuerpo["por_grupo"]["pasa_a_despacho"] == 1
    assert cuerpo["por_grupo"]["cierra_caso"] == 1
    assert cuerpo["por_grupo"]["todo"] == 2
    #  Dos filas con limite 20: no hay pagina siguiente, y se dice con null.
    assert cuerpo["siguiente"] is None


def test_la_vista_filtra_por_grupo(admin_client, org_a):
    _hecho(org_a, "PropuestaSupervisor", "CREATE", "una propuesta")
    cierre = _un_cierre_de_caso(org_a, "el cierre")

    cuerpo = admin_client.get(ACTIVIDAD, {"grupo": "cierra_caso"}).json()

    assert [r["id"] for r in cuerpo["resultados"]] == [str(cierre.id)]


def test_la_vista_pagina_hacia_atras(admin_client, org_a):
    from datetime import timedelta

    ahora = timezone.now()
    for i in range(5):
        _hecho(org_a, "PropuestaSupervisor", "CREATE", f"h{i}",
               cuando=ahora - timedelta(minutes=i))

    p1 = admin_client.get(ACTIVIDAD, {"limite": 2}).json()
    assert [r["nombre"] for r in p1["resultados"]] == ["h0", "h1"]
    assert p1["siguiente"] is not None

    p2 = admin_client.get(ACTIVIDAD,
                          {"limite": 2, "antes_de": p1["siguiente"]}).json()
    assert [r["nombre"] for r in p2["resultados"]] == ["h2", "h3"]


def test_una_fecha_ilegible_NO_se_ignora(admin_client, org_a):
    """
    Ignorarla devolveria la PRIMERA pagina otra vez, y quien hojea veria
    repetirse lo que ya leyo sin entender por que. Un 400 lo dice.
    """
    _hecho(org_a, "PropuestaSupervisor", "CREATE")

    r = admin_client.get(ACTIVIDAD, {"antes_de": "el martes pasado"})

    assert r.status_code == 400, r.json()
