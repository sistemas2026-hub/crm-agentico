# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR RETIRA SOLO LO QUE NO ES SUYO
================================================================================

EL DEFECTO  --  16/10/2026
--------------------------
Desde cdaa9b27 el Supervisor NOC lee solo tickets de soporte técnico y
operativo. Pero las propuestas hechas ANTES de ese filtro --sobre cartera,
ventas, administrativo-- seguían en la pestaña Pendientes hasta que una persona
las revisara o expiraran a los 7 días. El 15/10 "Pendientes" decía 76 mientras
Soporte Técnico tenía 64 tickets. Y dos señales más seguían proponiendo
tickets ajenos cada hora: CASO_ANTIGUO y CASO_REQUIERE_VISITA.

LA REGLA, EN UN SOLO LUGAR
--------------------------
'areas_del_tenant.criterio_de_area' contesta tres cosas de un caso: PROPIO
(área escrita del Supervisor, o sin área y con alguien del área encima), AJENO
(área escrita de otra, o sin área y con gente cuya área el motor conoce y es
otra) o NO SE SABE. Las pruebas de acá fijan la asimetría: lo que se SABE
ajeno se cancela y deja de proponerse; lo que no se sabe NO se toca, porque
cancelar sin saber es inventarle un área.

Cada prueba siembra el caso que tiene que quedar AFUERA junto al que tiene que
quedar ADENTRO: sin el de control, "no retiró nada" y "retiró lo correcto" se
ven iguales.
================================================================================
"""

import io
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.utils import timezone

from cases.models import Case
from common.models import Activity, Profile, User
from operaciones import areas_del_tenant as areas
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db


#  Datos que NO pueden aparecer en ningún texto que este cambio escriba:
#  auditoría, salida del comando, logs. Cada uno es distintivo a propósito,
#  para que una aserción de ausencia no pase por casualidad.
NOMBRE_CLIENTE = "Zoraida Clientela"
TELEFONO_EN_DESCRIPCION = "3113683499"
NOMBRES_DE_PERSONA = {
    "tecnico@x.test": "Rigoberto Tecnicatura",
    "cartera@x.test": "Casimira Carterista",
    "nuevo@x.test": "Nepomuceno Novato",
}


def _persona(org, correo):
    u = User.objects.create(email=correo, name=NOMBRES_DE_PERSONA[correo])
    return Profile.objects.create(org=org, user=u, role="USER", is_active=True)


def _sin_datos_de_nadie(texto, *casos, personas=()):
    """Afirma que 'texto' no trae asunto, descripción, cliente, correo, nombre ni id de perfil."""
    prohibidos = [NOMBRE_CLIENTE, TELEFONO_EN_DESCRIPCION, "no tiene internet"]
    prohibidos += [c.name for c in casos]
    for p in personas:
        prohibidos += [p.user.email, p.user.name, str(p.id)]
    for dato in prohibidos:
        assert dato.lower() not in texto.lower(), f"se escribió {dato!r}"


def _caso(
    org,
    *,
    area,
    responsables=(),
    nombre="No tiene internet",
    external_service_id="",
    external_fetched_at=None,
    external_status="Nuevo",
    **extra,
):
    """
    Un caso que NINGUNA señal lee por defecto: sin lectura del proveedor, sin
    servicio, recién creado. Cada prueba enciende lo que necesita.
    """
    caso = Case.objects.create(
        org=org,
        name=nombre,
        status="New",
        priority="Normal",
        is_active=True,
        provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id=external_service_id,
        area=area,
        description=f"El cliente dice que no tiene internet. Tel {TELEFONO_EN_DESCRIPCION}.",
        external_client_name=NOMBRE_CLIENTE,
        external_status=external_status,
        external_fetched_at=external_fetched_at,
        **extra,
    )
    for r in responsables:
        caso.assigned_to.add(r)
    return caso


def _propuesta(org, caso, *, estado=P.PROPUESTA, tipo=P.TICKET_SIN_DIAGNOSTICO):
    return P.objects.create(
        org=org,
        tipo_senal=tipo,
        origen_tipo="case",
        origen_id=str(caso.id),
        estado=estado,
        #  Como la redactaría el modelo leyendo el ticket: con lo que el
        #  ticket traía. Es lo que el título de la cancelación NO debe repetir.
        accion_propuesta=f"Llamar a {NOMBRE_CLIENTE} al {TELEFONO_EN_DESCRIPCION}",
        motivo="x",
        prioridad=30,
        evidencia=[
            {
                "fuente": "caso",
                "id": str(caso.id),
                "dato": "z",
                "observado_en": timezone.now().isoformat(),
            }
        ],
    )


def _estado(propuesta):
    return P.objects.get(pk=propuesta.pk).estado


def _retirar(org):
    return sup.retirar_propuestas_fuera_de_area(org, timezone.now())


@pytest.fixture
def equipo(org_a, monkeypatch):
    """
    Un técnico de soporte, una persona de cartera y alguien que el motor no
    conoce. El mapa persona -> área se sirve entero, como lo hace el motor.
    """
    mapa = {}
    tecnico = _persona(org_a, "tecnico@x.test")
    cartera = _persona(org_a, "cartera@x.test")
    nuevo = _persona(org_a, "nuevo@x.test")
    mapa[str(tecnico.id)] = "soporte_tecnico"
    mapa[str(cartera.id)] = "cartera"
    monkeypatch.setattr(areas, "area_por_persona", lambda: dict(mapa))
    return SimpleNamespace(tecnico=tecnico, cartera=cartera, nuevo=nuevo, mapa=mapa)


# =============================================================================
#  §1  LO QUE SE SABE AJENO SE CANCELA; LO PROPIO SE QUEDA
# =============================================================================


def test_a_ventas_asignado_a_un_tecnico_se_cancela_con_motivo(org_a, equipo):
    """El defecto exacto: ventas con un técnico encima no es de soporte."""
    ajeno = _caso(
        org_a,
        area="ventas",
        responsables=[equipo.tecnico],
        nombre="Cotización plan nuevo",
    )
    propio = _caso(org_a, area="soporte_tecnico", responsables=[equipo.tecnico])
    p_ajeno = _propuesta(org_a, ajeno)
    p_propio = _propuesta(org_a, propio)

    assert _retirar(org_a) == 1
    assert _estado(p_ajeno) == P.CANCELADA
    assert _estado(p_propio) == P.PROPUESTA

    #  La fila de auditoría ENTERA --título, descripción y metadata-- lleva el
    #  área y el id del caso, y nada del ticket ni de nadie: esa fila la
    #  muestra el feed del panel y se pega en transcripciones. El título es
    #  fijo a propósito: la acción propuesta la redactó el modelo leyendo el
    #  ticket.
    renglon = Activity.objects.filter(description=sup.FUERA_DE_AREA).latest(
        "created_at"
    )
    motivo = (renglon.metadata or {}).get("motivo", "")
    assert "ventas" in motivo and str(ajeno.id) in motivo
    assert renglon.entity_name == sup.FUERA_DE_AREA
    assert renglon.user_id is None, "cancelar por área no es una decisión de nadie"
    todo = " ".join([renglon.description, renglon.entity_name, str(renglon.metadata)])
    _sin_datos_de_nadie(todo, ajeno, propio, personas=[equipo.tecnico])


def test_b_el_caso_de_soporte_sigue_pendiente(org_a, equipo):
    propio = _caso(org_a, area="soporte_tecnico", responsables=[equipo.cartera])
    p = _propuesta(org_a, propio)

    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA, (
        "el área escrita manda: soporte con alguien de cartera encima sigue "
        "siendo de soporte"
    )


def test_c_sin_area_escrita_y_con_alguien_de_cartera_se_cancela(org_a, equipo):
    """Los importados antes del campo: el criterio viejo, la persona."""
    viejo = _caso(org_a, area="", responsables=[equipo.cartera])
    control = _caso(org_a, area="", responsables=[equipo.tecnico])
    p_viejo = _propuesta(org_a, viejo)
    p_control = _propuesta(org_a, control)

    assert _retirar(org_a) == 1
    assert _estado(p_viejo) == P.CANCELADA
    assert _estado(p_control) == P.PROPUESTA


def test_d_sin_area_escrita_y_con_el_tecnico_se_queda(org_a, equipo):
    p = _propuesta(org_a, _caso(org_a, area="", responsables=[equipo.tecnico]))
    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA


# =============================================================================
#  §2  LO QUE NO SE SABE, NO SE TOCA
# =============================================================================


def test_e_sin_area_y_sin_nadie_no_se_cancela(org_a, equipo):
    p = _propuesta(org_a, _caso(org_a, area="", responsables=[]))
    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA, (
        "sin nadie encima no hay con qué decir que es ajeno"
    )


def test_f_sin_area_y_con_alguien_que_el_motor_no_conoce_no_se_cancela(org_a, equipo):
    p = _propuesta(org_a, _caso(org_a, area="", responsables=[equipo.nuevo]))
    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA


def test_m_con_dos_responsables_uno_de_soporte_no_es_ajeno(org_a, equipo):
    """Lo propio gana: soporte y cartera encima del mismo caso sin área."""
    p = _propuesta(
        org_a, _caso(org_a, area="", responsables=[equipo.tecnico, equipo.cartera])
    )
    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA


# =============================================================================
#  §3  FAIL-CLOSED Y LAS QUE YA DECIDIÓ UNA PERSONA
# =============================================================================


def test_g_sin_el_mapa_del_motor_no_se_cancela_nada(org_a, equipo, monkeypatch):
    """
    Un mapa vacío es "no se pudo saber", no "nadie es de soporte". Escribir un
    estado por una lectura que no llegó es peor que esperar la próxima vuelta.
    """
    p = _propuesta(org_a, _caso(org_a, area="ventas", responsables=[equipo.tecnico]))
    monkeypatch.setattr(areas, "area_por_persona", lambda: {})

    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA


@pytest.mark.parametrize("estado", [P.ACEPTADA, P.RECHAZADA, P.MODIFICADA])
def test_h_lo_que_una_persona_ya_decidio_queda_como_esta(org_a, equipo, estado):
    ajeno = _caso(org_a, area="ventas", responsables=[equipo.tecnico])
    p = _propuesta(org_a, ajeno, estado=estado)

    assert _retirar(org_a) == 0
    assert _estado(p) == estado


def test_cancelada_y_no_expirada(org_a, equipo):
    """Expirada significa que nadie la miró a tiempo, y eso sería falso."""
    p = _propuesta(org_a, _caso(org_a, area="cartera", responsables=[equipo.tecnico]))
    _retirar(org_a)
    assert _estado(p) == P.CANCELADA
    assert _estado(p) != P.EXPIRADA
    assert P.objects.get(pk=p.pk).revisado_por is None


# =============================================================================
#  §4  EL CICLO LO HACE SOLO, Y LO CUENTA
# =============================================================================


def test_i_correr_ciclo_retira_y_lo_cuenta(org_a, equipo):
    """
    Código construido no es código que corre: el retiro tiene que pasar por
    'correr_ciclo', que es lo que dispara el botón y la hora :07.
    """
    p_ajeno = _propuesta(
        org_a, _caso(org_a, area="ventas", responsables=[equipo.tecnico])
    )
    p_propio = _propuesta(
        org_a, _caso(org_a, area="soporte_tecnico", responsables=[equipo.tecnico])
    )

    resumen = sup.correr_ciclo(org_a)

    assert resumen["retiradas_por_area"] == 1
    assert _estado(p_ajeno) == P.CANCELADA
    assert _estado(p_propio) == P.PROPUESTA


# =============================================================================
#  §5  LAS SEÑALES DE RUIDO YA NO PROPONEN TICKETS AJENOS
# =============================================================================


def _ids(senales):
    return {s.origen_id for s in senales}


def test_j1_caso_antiguo_no_propone_un_ticket_de_ventas(org_a, equipo):
    ajeno = _caso(org_a, area="ventas", responsables=[equipo.tecnico])
    control = _caso(org_a, area="soporte_tecnico", responsables=[equipo.tecnico])
    dentro_de_ocho_dias = timezone.now() + timedelta(days=sup.DIAS_CASO_ANTIGUO + 1)

    ids = _ids(sup._casos_abiertos_antiguos(org_a, dentro_de_ocho_dias))

    assert str(control.id) in ids, (
        "sin el de control, una lista vacía también sería verde"
    )
    assert str(ajeno.id) not in ids


def test_j1b_sin_mapa_solo_entra_lo_que_no_depende_de_la_persona(
    org_a, equipo, monkeypatch
):
    """
    Sin el mapa del motor: un área escrita ajena se excluye igual (no
    necesita mapa), un área escrita propia entra, y un caso sin área y sin
    nadie entra. Lo que tiene gente encima ESPERA al mapa: proponerlo sin
    saber era proponer hoy lo que la vuelta siguiente cancela, y con el motor
    caído una vuelta eso oscilaba caso por caso (auditoría de frontera,
    16/10/2026).
    """
    escrito_ajeno = _caso(org_a, area="ventas", responsables=[equipo.tecnico])
    escrito_propio = _caso(org_a, area="soporte_tecnico", responsables=[equipo.cartera])
    sin_nadie = _caso(org_a, area="", responsables=[])
    con_alguien = _caso(org_a, area="", responsables=[equipo.cartera])
    monkeypatch.setattr(areas, "area_por_persona", lambda: {})
    dentro_de_ocho_dias = timezone.now() + timedelta(days=sup.DIAS_CASO_ANTIGUO + 1)

    ids = _ids(sup._casos_abiertos_antiguos(org_a, dentro_de_ocho_dias))

    assert str(escrito_propio.id) in ids
    assert str(sin_nadie.id) in ids
    assert str(escrito_ajeno.id) not in ids
    assert str(con_alguien.id) not in ids, (
        "sin mapa, lo que depende de la persona espera"
    )


def test_j2_requiere_visita_no_propone_un_ticket_de_ventas(org_a, equipo, monkeypatch):
    from operaciones import clasificacion_de_trabajo as clf

    ajeno = _caso(
        org_a, area="ventas", responsables=[equipo.tecnico], external_service_id="3614"
    )
    control = _caso(
        org_a,
        area="soporte_tecnico",
        responsables=[equipo.tecnico],
        external_service_id="3615",
    )
    consultados = []

    def _contexto(caso_id):
        consultados.append(caso_id)
        return {
            "contexto_disponible": True,
            "equipo": {"estado": "caido"},
            "capturado_en": timezone.now().isoformat(),
        }

    monkeypatch.setattr("campo.services.despacho.contexto_del_caso", _contexto)
    monkeypatch.setattr(
        clf,
        "clasificar",
        lambda contexto, marcadores=None: {
            "labor": clf.CORRECTIVO,
            "verificada": True,
            "porque": "equipo caído",
            "fuente": "prueba",
        },
    )

    ids = _ids(sup._casos_que_necesitan_visita(org_a, timezone.now()))

    assert str(control.id) in ids
    assert str(ajeno.id) not in ids
    #  Y ni siquiera le costó una llamada al motor.
    assert str(ajeno.id) not in consultados


def test_k_el_cierre_de_desincronizados_SIGUE_para_todas_las_areas(org_a, equipo):
    """
    Decisión del usuario, 16/10/2026: es la única señal que cierra en el CRM un
    ticket que WispHub ya cerró, y hoy nadie más lo hace. No se filtra.
    """
    ahora = timezone.now()
    de_cartera = _caso(
        org_a,
        area="cartera",
        responsables=[equipo.cartera],
        external_status="Cerrado",
        external_status_at=ahora - timedelta(days=1),
        external_fetched_at=ahora,
        external_fetch_error="",
    )

    ids = _ids(sup._casos_cerrados_en_el_proveedor(org_a, ahora))

    assert str(de_cartera.id) in ids


# =============================================================================
#  §6  EL COMANDO: MIDE SIN ESCRIBIR, Y RETIRA A DEMANDA
# =============================================================================


def test_l_el_comando_cuenta_sin_escribir_y_no_imprime_asuntos(org_a, equipo):
    ajeno = _caso(
        org_a,
        area="ventas",
        responsables=[equipo.tecnico],
        nombre="Cotización plan nuevo",
    )
    propio = _caso(org_a, area="soporte_tecnico", responsables=[equipo.tecnico])
    p_ajeno = _propuesta(org_a, ajeno)
    _propuesta(org_a, propio)

    salida = io.StringIO()
    call_command(
        "propuestas_fuera_de_area", "--org", str(org_a.id), "--contar", stdout=salida
    )
    texto = salida.getvalue()

    assert "pendientes sobre tickets: 2" in texto
    assert "fuera de área: 1" in texto
    assert str(ajeno.id) in texto and "ventas" in texto
    _sin_datos_de_nadie(texto, ajeno, propio, personas=[equipo.tecnico])
    assert _estado(p_ajeno) == P.PROPUESTA, "--contar no escribe"


def test_l2_el_comando_retira_a_demanda(org_a, equipo):
    p = _propuesta(org_a, _caso(org_a, area="ventas", responsables=[equipo.tecnico]))

    salida = io.StringIO()
    call_command("propuestas_fuera_de_area", "--org", str(org_a.id), stdout=salida)

    assert "retiradas: 1" in salida.getvalue()
    assert _estado(p) == P.CANCELADA


def test_l3_el_comando_sin_mapa_falla_en_vez_de_decir_cero(org_a, equipo, monkeypatch):
    from django.core.management.base import CommandError

    _propuesta(org_a, _caso(org_a, area="ventas", responsables=[equipo.tecnico]))
    monkeypatch.setattr(areas, "area_por_persona", lambda: {})

    with pytest.raises(CommandError):
        call_command(
            "propuestas_fuera_de_area",
            "--org",
            str(org_a.id),
            "--contar",
            stdout=io.StringIO(),
        )


def test_k2_una_propuesta_de_cierre_sobre_un_caso_de_cartera_NO_se_retira(
    org_a, equipo
):
    """
    La señal de cierre sigue para todas las áreas (decisión del 16/10), así
    que sus propuestas tampoco se retiran: cancelarlas sería deshacer cada
    hora lo que la señal permitida propone, y el cierre de un ticket de
    cartera nunca llegaría a una persona. La lectura con diagnóstico sobre
    el mismo caso sí se retira: esa señal es de soporte.
    """
    de_cartera = _caso(org_a, area="cartera", responsables=[equipo.cartera])
    cierre = _propuesta(org_a, de_cartera, tipo=P.CASO_DESINCRONIZADO)
    lectura = _propuesta(org_a, de_cartera, tipo=P.TICKET_SIN_DIAGNOSTICO)

    assert _retirar(org_a) == 1
    assert _estado(cierre) == P.PROPUESTA
    assert _estado(lectura) == P.CANCELADA


def test_l4_el_comando_dice_cuantos_cierres_ajenos_quedan_sin_retirar(org_a, equipo):
    """'fuera de área: 0' no significa 'Pendientes solo soporte': los cierres se quedan."""
    de_cartera = _caso(org_a, area="cartera", responsables=[equipo.cartera])
    _propuesta(org_a, de_cartera, tipo=P.CASO_DESINCRONIZADO)

    salida = io.StringIO()
    call_command(
        "propuestas_fuera_de_area", "--org", str(org_a.id), "--contar", stdout=salida
    )
    texto = salida.getvalue()

    assert "fuera de área: 0" in texto
    assert "pendientes de cierre sobre otras áreas: 1" in texto


# =============================================================================
#  §7  LO QUE ENCONTRO EL AUDITOR INDEPENDIENTE
# =============================================================================


@pytest.mark.parametrize(
    "grafia", ["Soporte_Tecnico", "soporte_tecnico ", "SOPORTE_TECNICO", " operativo"]
)
def test_n_una_grafia_distinta_del_area_propia_no_es_ajena(org_a, equipo, grafia):
    """
    'Case.area' se escribe tal cual viene de la configuración y el núcleo lo
    valida normalizado: 'Soporte_Tecnico' es la misma área. Compararla exacta
    cancelaba cada hora lo propio y lo sacaba de CASO_ANTIGUO.
    """
    caso = _caso(org_a, area=grafia, responsables=[equipo.tecnico])
    p = _propuesta(org_a, caso)
    dentro_de_ocho_dias = timezone.now() + timedelta(days=sup.DIAS_CASO_ANTIGUO + 1)

    assert _retirar(org_a) == 0
    assert _estado(p) == P.PROPUESTA
    assert str(caso.id) in _ids(
        sup._casos_abiertos_antiguos(org_a, dentro_de_ocho_dias)
    )


def test_l5_el_comando_cuenta_lo_que_no_se_sabe(org_a, equipo):
    """
    'fuera de área: 0' con la pestaña llena de casos sin área de gente que el
    motor no conoce: el comando lo dice aparte, no lo esconde en el cero.
    """
    _propuesta(org_a, _caso(org_a, area="", responsables=[equipo.nuevo]))
    _propuesta(org_a, _caso(org_a, area="", responsables=[]))
    _propuesta(
        org_a, _caso(org_a, area="soporte_tecnico", responsables=[equipo.tecnico])
    )

    salida = io.StringIO()
    call_command(
        "propuestas_fuera_de_area", "--org", str(org_a.id), "--contar", stdout=salida
    )
    texto = salida.getvalue()

    assert "fuera de área: 0" in texto
    assert "pendientes sobre casos cuya área no se sabe: 2" in texto


def test_l6_el_comando_fija_su_propio_contexto_rls(org_a, equipo):
    """
    Un comando no pasa por el middleware: sin 'app.current_org' las tablas con
    RLS devuelven 0 filas sin error. El fixture deja el contexto puesto, así
    que acá se limpia antes de llamar. Solo ve algo bajo un rol que RLS ate de
    verdad: con el superusuario de la receta de pruebas pasa igual.
    """
    from conftest import clear_rls_context, restore_rls_context

    _propuesta(org_a, _caso(org_a, area="ventas", responsables=[equipo.tecnico]))
    clear_rls_context()
    try:
        salida = io.StringIO()
        call_command(
            "propuestas_fuera_de_area",
            "--org",
            str(org_a.id),
            "--contar",
            stdout=salida,
        )
    finally:
        restore_rls_context()

    assert "fuera de área: 1" in salida.getvalue()
