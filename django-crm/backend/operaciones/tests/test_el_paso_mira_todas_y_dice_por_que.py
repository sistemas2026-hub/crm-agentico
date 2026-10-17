# -*- coding: utf-8 -*-
"""
================================================================================
 EL PASO A DESPACHO MIRA TODAS LAS PENDIENTES, Y DICE POR QUE SE QUEDA CADA UNA
================================================================================

LO QUE MIDIO PRODUCCION EL 16/10/2026
-------------------------------------
El Supervisor ya corria solo cada hora con las tres puertas abiertas, y en la
vuelta de las 11:07 paso CERO de 65 lecturas pendientes. Con las reglas
vigentes era la respuesta correcta --33 fallas que la lectura marcaba "con el
equipo en linea y sano", y el resto en grupos que van siempre a una persona--,
pero la medicion encontro dos defectos:

  1. EL TOPE TAPABA LAS NUEVAS. La fase miraba las 60 mas viejas y habia 65.
     Las que nunca califican ocupaban la ventana cada hora, asi que una falla
     NUEVA confirmada por la medicion --justo la que tiene que pasar sola--
     entraba ultima y no se evaluaba hasta que salieran otras: dias.

  2. EL MOTIVO NO QUEDABA ESCRITO. Por que se quedaba cada una salia solo
     sumado en el log del worker. En el panel, una propuesta revisada cada hora
     se veia igual que una que nadie miro.

QUE SE AFIRMA, Y POR QUE ASI
----------------------------
Sobre el EFECTO: el estado de la propuesta, quien la reviso, la fila de
auditoria con la tarea, la pieza de evidencia escrita y lo que devuelve la API
de detalle. Nunca sobre los contadores del informe: el 14/10 ocho pruebas
estuvieron en verde con el sintoma vivo por afirmar sobre un contador.

El tope se baja a 3 en las pruebas: lo que se prueba es la forma (mas
pendientes que el tope), no el numero 60.

LO QUE SE MIDIO DESPUES, EL MISMO DIA
-------------------------------------
"El equipo esta en linea y sano" no sale de una medicion: el clasificador lee
claves que el motor no manda, y la dice con cualquier dato del equipo (ver
test_f). Por eso el motivo no la copia, y por eso test_a prueba tambien lo que
HOY puede pasar en produccion: un trabajo pedido con confianza alta.

DESDE LA FASE 3 (16/10/2026)
----------------------------
Una falla se decide con la MEDICION de 'diagnosticar_servicio', y el caso
necesita una copia fresca de WispHub. En este archivo una falla "confirmada"
es un equipo en linea con la señal fuera de rango, y una "sana", uno en linea
con la señal en rango. Las afirmaciones sobre el tope y el motivo no cambian.
================================================================================
"""

import json
import logging
import re
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from common.models import Activity, Profile, User
from operaciones import clasificacion_de_trabajo as clf
from operaciones import diagnostico_de_ticket as dxt
from operaciones import medicion_de_fallas as mdf
from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

#  Datos que NO pueden aparecer en el motivo escrito: distintivos a proposito,
#  para que una asercion de ausencia no pase por casualidad. Van en el caso Y
#  en lo que escribe el modelo --la accion y el motivo de la propuesta, el dato
#  de la lectura--, que en produccion puede traer el nombre del cliente.
ASUNTO = "Sin internet desde el lunes, Zoraida"
DESCRIPCION = "La señora Zoraida Clientela dice que no tiene servicio. Tel 3113683499."
CLIENTE = "Zoraida Clientela"

CAIDO_POR_FIBRA = (
    "el equipo esta caido por perdida de señal optica (LOS/LOF): la falla es de la red."
)
SANO = (
    "el equipo esta en linea y sano, asi que esto NO es una falla de red. "
    "Que tipo de trabajo es lo decide quien despacha"
)
SIN_ONU = "no se pudo leer el equipo (onu_no_vinculada)"
SIN_FICHA = "no se pudo traer la ficha tecnica del caso, asi que no hubo nada que medir"

#  Lo que deja guardado 'medicion_de_fallas' con una respuesta del motor.
_DEBIL = {"estado": "en_linea", "senal": "debil", "senal_dbm": -27.4,
          "causa_caida": "", "motivo": ""}
_EN_RANGO = {"estado": "en_linea", "senal": "buena", "senal_dbm": -21.0,
             "causa_caida": "", "motivo": ""}

TOPE = 3


def _caso(org):
    from cases.models import Case

    return Case.objects.create(
        org=org,
        name=ASUNTO,
        status="New",
        priority="Normal",
        is_active=True,
        provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614",
        #  La copia fresca y en curso de WispHub: sin ella no pasa (Fase 3).
        external_status="Nuevo",
        external_fetched_at=timezone.now(),
        description=DESCRIPCION,
        external_client_name=CLIENTE,
    )


def _lectura(
    *, grupo, verificada, labor_porque, confianza_del_grupo="alta", labor=clf.CORRECTIVO
):
    """Una pieza de lectura como la que deja 'diagnostico_de_ticket'."""
    return {
        "fuente": dxt.FUENTE,
        "id": "x",
        "dato": f"lectura del reclamo: {DESCRIPCION}",
        "observado_en": timezone.now().isoformat(),
        "grupo": grupo,
        "labor": labor if verificada else clf.SIN_CONCLUIR,
        "labor_verificada": verificada,
        "labor_porque": labor_porque,
        "confianza": "media",
        "confianza_del_grupo": confianza_del_grupo,
    }


def _pendiente(org, *, hace_min, medida=None, **lectura):
    """
    Una lectura pendiente, creada hace 'hace_min' minutos (manda el orden). Con
    'medida', ademas la medicion del equipo, guardada por el camino real.
    """
    p = P.objects.create(
        org=org,
        tipo_senal=P.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case",
        origen_id=str(_caso(org).id),
        estado=P.PROPUESTA,
        accion_propuesta=f"Llamar a {CLIENTE} al 3113683499",
        motivo=f"{CLIENTE} reporta que no tiene servicio",
        prioridad=30,
        evidencia=[_lectura(**lectura)],
    )
    P.objects.filter(pk=p.pk).update(
        created_at=timezone.now() - timedelta(minutes=hace_min)
    )
    if medida is not None:
        mdf.escribir(p, mdf.de_la_respuesta(medida), timezone.now())
    p.refresh_from_db()
    return p


def _confirmada(org, hace_min):
    return _pendiente(
        org,
        hace_min=hace_min,
        grupo=pad.FALLA_DE_SERVICIO,
        verificada=True,
        labor_porque=CAIDO_POR_FIBRA,
        medida=_DEBIL,
    )


def _sana(org, hace_min):
    return _pendiente(
        org,
        hace_min=hace_min,
        grupo=pad.FALLA_DE_SERVICIO,
        verificada=False,
        labor_porque=SANO,
        medida=_EN_RANGO,
    )


def _trabajo_pedido(org, hace_min):
    """Lo que HOY puede pasar en produccion: no depende de la medicion."""
    return _pendiente(
        org,
        hace_min=hace_min,
        grupo=pad.TRABAJO_PEDIDO,
        verificada=False,
        labor_porque=SANO,
        confianza_del_grupo="alta",
    )


def _estado(p):
    return P.objects.get(pk=p.pk).estado


def _el_panel_lo_pone_en_lo_que_falta(dato):
    """El criterio de 'esFaltante' (frontend/src/lib/v2/supervisor-noc-detalle.js)."""
    return bool(re.search(r"falta|no consta|no se pudo|sin registrar|no dice", dato, re.I))


def _sin_datos_del_cliente(pieza):
    """En NINGUNA clave de la pieza, no solo en 'dato' y 'porque'."""
    texto = json.dumps(pieza, ensure_ascii=False).lower()
    for dato in (ASUNTO, CLIENTE, "3113683499", "zoraida"):
        assert dato.lower() not in texto, f"el motivo escribio {dato!r}"


def _revisiones(p):
    return [
        x
        for x in (P.objects.get(pk=p.pk).evidencia or [])
        if isinstance(x, dict) and x.get("fuente") == pad.FUENTE_REVISION
    ]


def _vuelta(org):
    return sup._pasar_a_despacho_los_que_las_reglas_habiliten(org, timezone.now())[
        "despacho"
    ]


@pytest.fixture
def puertas_abiertas(monkeypatch):
    """Tarea delegada y techo en 3; y el tope chico, que es lo que se prueba."""
    from operaciones import autonomia, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: True)
    monkeypatch.setattr(
        autonomia, "puede", lambda o, nivel: {"puede": True, "motivo": ""}
    )
    monkeypatch.setattr(sup, "TOPE_PASO_A_DESPACHO", TOPE)


# =============================================================================
#  §1  EL TOPE YA NO TAPA LAS NUEVAS
# =============================================================================


@pytest.mark.parametrize(
    "que_califica",
    [
        pytest.param(_confirmada, id="falla_confirmada"),
        pytest.param(_trabajo_pedido, id="trabajo_pedido_confianza_alta"),
    ],
)
def test_a_una_NUEVA_que_califica_pasa_aunque_haya_mas_viejas_que_el_tope(
    org_a, puertas_abiertas, que_califica
):
    """
    EL DEFECTO DEL 16/10. TOPE+5 pendientes viejas que no califican ocupan la
    ventana, y una nueva que califica entra ultima. Antes no se miraba; ahora
    pasa en la misma vuelta. Con las dos formas de calificar: la falla
    confirmada, y el trabajo pedido, que es la unica que hoy puede darse en
    produccion (ver test_f).
    """
    viejas = [_sana(org_a, hace_min=1000 + i) for i in range(TOPE + 5)]
    nueva = que_califica(org_a, hace_min=1)

    _vuelta(org_a)

    fila = P.objects.get(pk=nueva.pk)
    assert fila.estado == P.ACEPTADA, (
        "la falla nueva confirmada no paso: el tope la sigue tapando"
    )
    assert fila.revisado_por_id is None, "un pase automatico no lo firma nadie"
    assert Activity.objects.filter(
        entity_id=nueva.pk, metadata__tarea=pad.TAREA
    ).exists(), "la auditoria tiene que decir que fue un pase a Despacho"
    #  Y no copia al feed de toda la empresa lo que redacto el modelo: la
    #  'accion_propuesta' de esta prueba lleva el nombre y el telefono.
    actividad = Activity.objects.get(entity_id=nueva.pk, metadata__tarea=pad.TAREA)
    assert actividad.entity_name == pad.NOMBRE_DEL_PASE, actividad.entity_name
    #  Y el control: las viejas siguen esperando a una persona.
    assert all(_estado(p) == P.PROPUESTA for p in viejas)


def test_b_si_califican_mas_que_el_tope_pasan_el_tope_y_el_resto_la_vuelta_siguiente(
    org_a, puertas_abiertas
):
    """El tope acota el EFECTO de una vuelta: las mas viejas primero."""
    todas = [_confirmada(org_a, hace_min=100 - i) for i in range(TOPE + 2)]
    #  Y una que NO califica, la mas nueva: se mira despues del tope.
    queda = _sana(org_a, hace_min=1)

    _vuelta(org_a)

    aceptadas = [p for p in todas if _estado(p) == P.ACEPTADA]
    assert aceptadas == todas[:TOPE], "pasan como mucho el tope, las mas viejas"
    assert all(_estado(p) == P.PROPUESTA for p in todas[TOPE:])
    #  Las que esperan el tope no se quedaron con una persona: no se anotan.
    assert all(_revisiones(p) == [] for p in todas[TOPE:])
    #  La que no califica se anota aunque el tope ya se haya alcanzado.
    assert len(_revisiones(queda)) == 1, "pasado el tope, la que se queda no dice por que"

    _vuelta(org_a)

    assert all(_estado(p) == P.ACEPTADA for p in todas)


# =============================================================================
#  §2  LA QUE SE QUEDA DICE POR QUE, Y DESDE CUANDO
# =============================================================================


def test_c_la_que_se_queda_lleva_el_motivo_y_la_api_lo_devuelve(
    org_a, puertas_abiertas
):
    from conftest import _make_authenticated_client

    queda = _sana(org_a, hace_min=10)
    pasa = _confirmada(org_a, hace_min=5)

    _vuelta(org_a)

    assert _estado(pasa) == P.ACEPTADA, (
        "sin el control, una vuelta vacia tambien seria verde"
    )
    (pieza,) = _revisiones(queda)
    assert "se contradicen" in pieza["porque"]
    assert pieza["grupo"] == pad.FALLA_DE_SERVICIO
    assert pieza["observado_en"], "tiene que decir desde cuando"
    _sin_datos_del_cliente(pieza)

    u = User.objects.create(email="jefa@x.test", name="Jefa")
    perfil = Profile.objects.create(
        org=org_a, user=u, role="OPERACIONES", is_active=True
    )
    r = _make_authenticated_client(u, org_a, perfil).get(
        f"/api/operaciones/propuestas/{queda.pk}/"
    )

    assert r.status_code == 200, r.data
    en_la_api = [
        x for x in r.data["evidencia"] if x.get("fuente") == pad.FUENTE_REVISION
    ]
    assert en_la_api and en_la_api[-1]["porque"] == pieza["porque"]


def test_d_con_el_mismo_motivo_la_vuelta_siguiente_no_escribe_nada(
    org_a, puertas_abiertas
):
    p = _sana(org_a, hace_min=10)
    _vuelta(org_a)
    evidencia = P.objects.get(pk=p.pk).evidencia
    actividad = Activity.objects.filter(entity_id=p.pk).count()

    _vuelta(org_a)

    assert P.objects.get(pk=p.pk).evidencia == evidencia, (
        "una vuelta con el mismo veredicto escribio otra vez"
    )
    assert Activity.objects.filter(entity_id=p.pk).count() == actividad


def test_d2_si_el_motivo_cambia_se_REEMPLAZA(org_a, puertas_abiertas):
    """
    La contracara de la anterior: el que cambia se anota, y reemplaza al
    viejo. El panel dibuja cada pieza sin su hora, y dos motivos juntos se
    leerian como dos cosas que pasan a la vez.
    """
    p = _sana(org_a, hace_min=10)
    _vuelta(org_a)
    fila = P.objects.get(pk=p.pk)
    fila.evidencia = [
        *fila.evidencia,
        _lectura(
            grupo=pad.NADA_LO_MIDE,
            verificada=False,
            labor_porque=SIN_ONU,
            confianza_del_grupo="media",
        ),
    ]
    fila.save(update_fields=["evidencia"])

    _vuelta(org_a)

    (vigente,) = _revisiones(p)
    assert "ninguna herramienta" in vigente["porque"]
    assert vigente["grupo"] == pad.NADA_LO_MIDE
    assert "se contradicen" not in vigente["porque"]


def test_una_decidida_por_una_persona_mientras_tanto_no_se_anota(org_a):
    """
    Entre que la fase lista las pendientes y escribe, una persona pudo
    decidirla. La fila se vuelve a mirar bloqueada: no gana una pieza que dice
    que se queda.
    """
    p = _sana(org_a, hace_min=10)
    P.objects.filter(pk=p.pk).update(estado=P.ACEPTADA)

    escribio = pad.anotar_por_que_se_queda(
        p,
        {"paso": False, "porque": "x", "grupo": "", "puerta": pad.PUERTA_REGLAS},
        timezone.now(),
    )

    assert escribio is False
    assert _revisiones(p) == []


def test_la_fuente_de_la_revision_no_se_confunde_con_una_lectura(org_a):
    """
    '_tickets_abiertos_con_tecnico' busca 'diagnostico_del_ticket' con
    'icontains' para saber que se leyo. Si esta fuente lo contuviera, una
    propuesta sin lectura con solo esta pieza dejaria de leerse.
    """
    assert dxt.FUENTE not in pad.FUENTE_REVISION
    p = P.objects.create(
        org=org_a,
        tipo_senal=P.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case",
        origen_id=str(_caso(org_a).id),
        estado=P.PROPUESTA,
        accion_propuesta="x",
        motivo="x",
        prioridad=30,
        evidencia=[sup._observacion("caso", "x", "caso en el CRM", timezone.now())],
    )
    pad.anotar_por_que_se_queda(
        p,
        {
            "paso": False,
            "porque": "la lectura guardada no trae el grupo",
            "grupo": "",
            "puerta": pad.PUERTA_REGLAS,
        },
        timezone.now(),
    )

    assert dxt.le_falta_lectura(P.objects.get(pk=p.pk)), (
        "una pieza de revision no es una lectura"
    )
    assert not P.objects.filter(pk=p.pk, evidencia__icontains=dxt.FUENTE).exists()


# =============================================================================
#  §3  LAS DECISIONES DEL 16/10 SIGUEN EN PIE
# =============================================================================


@pytest.mark.parametrize(
    "como",
    [
        pytest.param(
            dict(grupo=pad.FALLA_DE_SERVICIO, verificada=False, labor_porque=SANO),
            id="equipo_sano",
        ),
        pytest.param(
            dict(grupo=pad.NADA_LO_MIDE, verificada=True, labor_porque=CAIDO_POR_FIBRA),
            id="nada_lo_mide",
        ),
        pytest.param(
            dict(
                grupo=pad.NI_CLIENTE_NI_RED,
                verificada=True,
                labor_porque=CAIDO_POR_FIBRA,
            ),
            id="ni_cliente_ni_red",
        ),
    ],
)
def test_e_lo_que_las_reglas_mandan_a_una_persona_no_pasa(
    org_a, puertas_abiertas, como
):
    queda = _pendiente(org_a, hace_min=10, **como)
    control = _confirmada(org_a, hace_min=5)

    _vuelta(org_a)

    assert _estado(control) == P.ACEPTADA, (
        "sin el control, una vuelta vacia tambien seria verde"
    )
    assert _estado(queda) == P.PROPUESTA
    assert len(_revisiones(queda)) == 1


# =============================================================================
#  §4  EL MOTIVO DICE LO QUE UNA PERSONA NECESITA, Y NADA QUE NO DEBA
# =============================================================================


def _lo_que_leeria(contexto):
    """La lectura de una falla, con la labor que da el clasificador REAL."""
    v = clf.clasificar(contexto, texto=DESCRIPCION)
    return dict(
        grupo=pad.FALLA_DE_SERVICIO,
        verificada=bool(v.get("verificada")),
        labor_porque=v.get("porque") or "",
        labor=v.get("labor") or clf.SIN_CONCLUIR,
    )


def test_f_sin_medir_el_motivo_no_afirma_un_equipo_sano(org_a, puertas_abiertas):
    """
    Las lecturas salen del clasificador REAL con la forma REAL del endpoint
    liviano del motor (la de campo/tests/test_despacho_api.py): 'Online' u
    'Offline', sin causa. Con las dos el clasificador dice "el equipo esta en
    linea y sano" sin haber medido nada (H-1). Hasta la Fase 2 esta prueba
    usaba un 'LOS' inventado, que ese endpoint no devuelve.

    Desde la Fase 3 una falla se decide con la medicion de
    'diagnosticar_servicio', y mientras no la tenga el motivo dice que falta
    medirla. La frase de equipo sano no llega nunca a la propuesta, y el
    "onu_no_vinculada" de la lectura tampoco: el por que ahora lo dice la
    medicion misma.
    """
    en_linea = _pendiente(
        org_a,
        hace_min=30,
        **_lo_que_leeria(
            {
                "contexto_disponible": True,
                "equipo": {"onu_status": "Online", "onu_signal_1490": "-20.81 dBm"},
            }
        ),
    )
    offline = _pendiente(
        org_a,
        hace_min=20,
        **_lo_que_leeria(
            {"contexto_disponible": True, "equipo": {"onu_status": "Offline"}}
        ),
    )
    sin_onu = _pendiente(
        org_a,
        hace_min=10,
        **_lo_que_leeria(
            {"contexto_disponible": True, "equipo_no_disponible": "onu_no_vinculada"}
        ),
    )

    _vuelta(org_a)

    for p in (en_linea, offline, sin_onu):
        (pieza,) = _revisiones(p)
        assert "falta la medicion" in pieza["porque"], pieza["porque"]
        assert clf.EQUIPO_SANO not in json.dumps(pieza, ensure_ascii=False), (
            "el motivo afirma un equipo sano que nadie midio"
        )
        _sin_datos_del_cliente(pieza)
        assert _el_panel_lo_pone_en_lo_que_falta(pieza["dato"])


def test_g_una_puerta_cerrada_escribe_texto_fijo_y_no_el_motivo_libre(
    org_a, monkeypatch, caplog
):
    """
    El motivo de la puerta 3 arrastra lo que una persona escribio al mover el
    interruptor. Copiarlo a cada propuesta repartiria texto libre por la cola,
    y copiarlo al log lo dejaria donde no hay control de acceso.
    """
    from operaciones import autonomia, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: True)
    monkeypatch.setattr(
        autonomia,
        "puede",
        lambda o, nivel: {
            "puede": False,
            "motivo": "Lo apago Zoraida por la caida del lunes",
        },
    )
    p = _confirmada(org_a, hace_min=10)

    with caplog.at_level(logging.INFO, logger="operaciones.supervisor"):
        _vuelta(org_a)

    assert _estado(p) == P.PROPUESTA
    (pieza,) = _revisiones(p)
    _sin_datos_del_cliente(pieza)
    assert "las reglas lo dejan pasar" in pieza["porque"].lower()
    linea = next(
        (r.getMessage() for r in caplog.records if "paso a Despacho" in r.getMessage()),
        "",
    )
    assert "la empresa no tiene autorizado" in linea, "la fase no registro su linea"
    assert "zoraida" not in linea.lower(), "el log copio el motivo libre"


def test_g2_sin_la_tarea_delegada_tambien_lo_dice_con_texto_fijo(org_a, monkeypatch):
    from operaciones import autonomia, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: False)
    monkeypatch.setattr(
        autonomia, "puede", lambda o, nivel: {"puede": True, "motivo": ""}
    )
    p = _confirmada(org_a, hace_min=10)

    _vuelta(org_a)

    assert _estado(p) == P.PROPUESTA
    (pieza,) = _revisiones(p)
    assert "no esta delegado" in pieza["porque"]
    _sin_datos_del_cliente(pieza)


# =============================================================================
#  §5  LO QUE ENCONTRARON LOS AUDITORES EL 16/10
# =============================================================================


def test_h_si_anotar_o_quitar_fallan_la_vuelta_sigue_y_las_que_vienen_pasan(
    org_a, puertas_abiertas, monkeypatch
):
    """
    Anotar y quitar son informativos. Fuera de un try, una falla en cualquiera
    de los dos --un bloqueo, la conexion-- cortaba la fase, y las mas nuevas
    quedaban sin mirar: el mismo defecto que esta fase vino a cerrar.
    """

    def _falla(*a, **k):
        raise RuntimeError("bloqueo")

    monkeypatch.setattr(pad, "anotar_por_que_se_queda", _falla)
    monkeypatch.setattr(pad, "quitar_por_que_se_quedaba", _falla)
    vieja = _sana(org_a, hace_min=30)
    primera = _confirmada(org_a, hace_min=20)
    ultima = _confirmada(org_a, hace_min=1)

    _vuelta(org_a)

    assert _estado(ultima) == P.ACEPTADA, "una falla al anotar o al quitar tumbo la vuelta"
    assert _estado(primera) == P.ACEPTADA
    assert _estado(vieja) == P.PROPUESTA


def test_i_cuando_pasa_se_quita_el_motivo_que_decia_que_se_quedaba(
    org_a, monkeypatch
):
    """
    El interruptor estuvo apagado y se anoto "se queda para una persona". En
    la vuelta siguiente paso: una ACEPTADA no puede seguir diciendo eso, y el
    panel la dibuja sin hora.
    """
    from operaciones import autonomia, tareas_delegadas

    techo = {"puede": False, "motivo": "apagado"}
    monkeypatch.setattr(tareas_delegadas, "esta_delegada", lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede", lambda o, nivel: dict(techo))
    p = _confirmada(org_a, hace_min=10)

    _vuelta(org_a)
    assert len(_revisiones(p)) == 1, "con la empresa cerrada se anota"

    techo["puede"] = True
    _vuelta(org_a)

    assert _estado(p) == P.ACEPTADA
    assert _revisiones(p) == [], "la aceptada sigue diciendo que se quedo"


def test_j_el_motivo_explica_la_decision_aunque_llegue_una_lectura(org_a):
    """
    Entre que la fase decide y escribe puede llegar una lectura nueva (dos
    ciclos solapados). El motivo explica la decision que se tomo con la copia
    que se tenia --sin lectura: "falta la lectura del reclamo"--, no lo que
    dice la fila recargada. Y la lectura que llego no se pierde: la vuelta que
    viene decide con ella.
    """
    p = P.objects.create(
        org=org_a,
        tipo_senal=P.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case",
        origen_id=str(_caso(org_a).id),
        estado=P.PROPUESTA,
        accion_propuesta="x",
        motivo="x",
        prioridad=30,
        evidencia=[sup._observacion("caso", "x", "caso en el CRM", timezone.now())],
    )
    decidida = P.objects.get(pk=p.pk)
    d = pad.de_la_propuesta(decidida)
    fila = P.objects.get(pk=p.pk)
    fila.evidencia = [
        *fila.evidencia,
        _lectura(grupo=pad.FALLA_DE_SERVICIO, verificada=False, labor_porque=SIN_FICHA),
    ]
    fila.save(update_fields=["evidencia"])

    escribio = pad.anotar_por_que_se_queda(
        decidida,
        {"paso": False, "porque": d.porque, "grupo": d.grupo, "puerta": pad.PUERTA_REGLAS},
        timezone.now(),
    )

    assert escribio
    (pieza,) = _revisiones(p)
    assert "falta la lectura del reclamo" in pieza["porque"], pieza["porque"]
    lecturas = [
        x for x in P.objects.get(pk=p.pk).evidencia if x.get("fuente") == dxt.FUENTE
    ]
    assert len(lecturas) == 1, "anotar perdio la lectura que llego en el medio"


# =============================================================================
#  §6  LO QUE ENCONTRO EL AUDITOR INDEPENDIENTE EL 16/10
# =============================================================================


def test_k_el_dia_que_el_clasificador_entienda_al_motor_esta_prueba_avisa():
    """
    NO describe lo que deberia pasar: es un aviso. El clasificador no entiende
    el equipo que manda el endpoint liviano del motor ('Online' u 'Offline',
    sin causa), y los otros llamadores de 'clasificar' --la pantalla de
    Despacho, la orden, CASO_REQUIERE_VISITA-- siguen recibiendo ese equipo
    (H-1). El paso a Despacho ya no depende de esto desde la Fase 3. El dia que
    el clasificador lea 'onu_status', esto falla: hay que revisar esos
    llamadores, porque desde entonces "sano" va a querer decir sano.
    """
    v = clf.clasificar({"contexto_disponible": True, "equipo": {"onu_status": "Offline"}})
    assert v["verificada"] is False, (
        "el clasificador ya confirma una caida con la forma del motor: revisar "
        "los otros llamadores de clasificar y la nota de EQUIPO_SANO"
    )


def test_l_quitar_el_motivo_no_toca_el_resto_de_la_evidencia(org_a):
    """
    Al pasar se quita SOLO la pieza del motivo, y de la fila bloqueada: una
    lectura que llego despues de cargar la copia sigue ahi. La pantalla de
    Despacho arma la hipotesis con la lectura; sin ella, quien despacha ve un
    caso vacio.
    """
    p = _confirmada(org_a, hace_min=10)
    pad.anotar_por_que_se_queda(
        p,
        {
            "paso": False,
            "porque": "x",
            "grupo": pad.FALLA_DE_SERVICIO,
            "puerta": pad.PUERTA_EMPRESA,
        },
        timezone.now(),
    )
    vieja = P.objects.get(pk=p.pk)
    assert len(_revisiones(p)) == 1
    otra = _lectura(
        grupo=pad.FALLA_DE_SERVICIO, verificada=True, labor_porque=CAIDO_POR_FIBRA
    )
    con_la_otra = [*vieja.evidencia, otra]
    P.objects.filter(pk=p.pk).update(estado=P.ACEPTADA, evidencia=con_la_otra)

    assert pad.quitar_por_que_se_quedaba(vieja) is True

    esperada = [x for x in con_la_otra if x.get("fuente") != pad.FUENTE_REVISION]
    assert P.objects.get(pk=p.pk).evidencia == esperada, (
        "quitar el motivo se llevo otra evidencia"
    )


def test_m_si_no_se_pudo_registrar_el_pase_no_se_escribe_que_se_queda(
    org_a, puertas_abiertas, monkeypatch
):
    """
    Un pase que fallo al registrarse no es una propuesta que se queda con una
    persona: la vuelta que viene lo reintenta. Escribir "se queda" seria
    falso.
    """

    def _falla(*a, **k):
        raise RuntimeError("base caida")

    monkeypatch.setattr(sup, "revisar", _falla)
    control = _sana(org_a, hace_min=20)
    p = _confirmada(org_a, hace_min=10)

    _vuelta(org_a)

    assert _estado(p) == P.PROPUESTA
    assert _revisiones(p) == [], "un pase que no se pudo registrar quedo como que se queda"
    assert len(_revisiones(control)) == 1, (
        "sin el control, una vuelta vacia tambien seria verde"
    )


def test_n_la_que_todavia_no_se_leyo_no_dice_que_hay_una_lectura(
    org_a, puertas_abiertas
):
    """
    El 'porque' de 'de_la_propuesta' supone una lectura guardada. En una
    propuesta que nunca se leyo eso es falso, y si el reclamo viene vacio
    quedaria escrito hasta que la propuesta venza.
    """
    p = P.objects.create(
        org=org_a,
        tipo_senal=P.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case",
        origen_id=str(_caso(org_a).id),
        estado=P.PROPUESTA,
        accion_propuesta="x",
        motivo="x",
        prioridad=30,
        evidencia=[sup._observacion("caso", "x", "caso en el CRM", timezone.now())],
    )

    _vuelta(org_a)

    (pieza,) = _revisiones(p)
    assert "la lectura guardada" not in pieza["porque"]
    assert "falta la lectura del reclamo" in pieza["porque"]
    assert dxt.le_falta_lectura(P.objects.get(pk=p.pk)), "la pieza no es una lectura"


def test_e2_obra_de_red_y_trabajo_pedido_pasan_con_confianza_media(
    org_a, puertas_abiertas
):
    """Decidido el 16/10/2026 (Fase 4): la confianza se escribe, no decide."""
    obra = _pendiente(
        org_a, hace_min=20, grupo=pad.OBRA_DE_RED, verificada=False,
        labor_porque=SIN_ONU, confianza_del_grupo="media",
    )
    trabajo = _pendiente(
        org_a, hace_min=10, grupo=pad.TRABAJO_PEDIDO, verificada=False,
        labor_porque=SANO, confianza_del_grupo="",
    )

    _vuelta(org_a)

    assert _estado(obra) == P.ACEPTADA and _estado(trabajo) == P.ACEPTADA
    assert "confianza media" in (P.objects.get(pk=obra.pk).resultado or "")
