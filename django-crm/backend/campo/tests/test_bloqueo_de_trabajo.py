# -*- coding: utf-8 -*-
"""Detener un trabajo, y volver a ponerlo en marcha.

LA PRUEBA QUE DA NOMBRE A ESTE ARCHIVO
--------------------------------------
`bloqueada` y `requiere_noc` **no son lo mismo**, y la mitad de estas pruebas
existen para que nadie los vuelva a juntar:

    estado_operativo = "bloqueada"   ->  el trabajo esta detenido
    requiere_noc = True              ->  hace falta que alguien del NOC haga algo

Un trabajo detenido esperando al cliente esta bloqueado y NO requiere NOC. Si
fueran un solo concepto, esa bandeja mostraria trabajos que nadie de esa mesa
puede destrabar, y a la semana la dejarian de mirar.

LO DEMAS QUE SE DEFIENDE
------------------------
  * el estado de retorno NO se adivina: lo guarda la fila del bloqueo al abrirse,
    y se prueba desde DOS estados distintos --porque puede haber un bloqueo antes
    de llegar al sitio, y volver siempre a `en_sitio` inventaria que el tecnico
    llego cuando no habia llegado--;
  * un trabajo ya terminado no se puede "bloquear";
  * la maquina de transiciones sigue negando lo que negaba: agregar un estado no
    abre los otros caminos;
  * reportar un bloqueo SIN detener el trabajo es valido y la ficha lo dice;
  * un solo bloqueo abierto por orden, garantizado en la base y no por un `select`
    previo -- ahi vive la carrera.
"""

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from campo.bloqueos import BloqueoDeTrabajo
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import bloqueos as serv
from campo.services import seguimiento_campo as seg
from campo.services.transiciones import (
    SE_PUEDE_BLOQUEAR_DESDE,
    TRANSICIONES_PERMITIDAS,
    TransicionInvalidaError,
    ejecutar_accion_operativa,
)
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db


ESQUEMA = {
    "pasos": [],
    "campos": [],
    "evidencias": [],
    "seguimiento": {
        "bloqueo": {
            "campos": [
                {"id": "categoria", "titulo": "Categoría", "tipo": "seleccion",
                 "reglas": {"required": True,
                            "options": ["material", "acceso", "cliente"]}},
                {"id": "motivo", "titulo": "Por qué no se puede seguir",
                 "tipo": "texto", "reglas": {"required": True}},
                {"id": "necesita_de_noc", "titulo": "Qué se necesita",
                 "tipo": "texto", "reglas": {"required": False}},
            ]
        }
    },
}

RESPUESTAS = {
    "categoria": "acceso",
    "motivo": "No hay acceso al poste",
    "necesita_de_noc": "Coordinar con el propietario",
}


def _cliente(user, org, profile):
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tec.bloq@test.com", password="testpass123"
    )
    return user, Profile.objects.create(
        user=user, org=org_a, role="USER", is_active=True
    )


@pytest.fixture
def jefe(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="noc.bloq@test.com", password="testpass123"
    )
    return user, Profile.objects.create(
        user=user, org=org_a, role="OPERACIONES", is_active=True
    )


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="bloq", nombre="Trabajo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA,
    )


def _orden(org, version, profile, numero, estado=OrdenTrabajo.EN_SITIO):
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzon", cliente_direccion="Calle 50",
        estado_operativo=estado, revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=profile, rol="tecnico", es_principal=True
    )
    return o


@pytest.fixture
def orden(org_a, version, tecnico):
    return _orden(org_a, version, tecnico[1], 4101)


# --------------------------------------------------------------------------- #
# A-D. bloqueada != requiere_noc
# --------------------------------------------------------------------------- #

def test_a_un_bloqueo_que_no_es_del_noc_detiene_igual(orden, tecnico):
    """Espera al cliente: el trabajo esta detenido y el NOC no tiene nada que hacer."""
    bloqueo, _evento, detuvo = serv.bloquear(
        orden, profile=tecnico[1],
        respuestas={"categoria": "cliente", "motivo": "El cliente no esta en la casa"},
        requiere_noc=False,
    )
    orden.refresh_from_db()
    assert detuvo is True
    assert orden.estado_operativo == OrdenTrabajo.BLOQUEADA
    assert bloqueo.requiere_noc is False


def test_b_la_bandeja_del_noc_no_ve_el_bloqueo_que_no_le_toca(org_a, version, tecnico):
    """LA prueba de la separación: dos filtros, y los dos dicen la verdad."""
    del_cliente = _orden(org_a, version, tecnico[1], 4102)
    del_noc = _orden(org_a, version, tecnico[1], 4103)

    serv.bloquear(
        del_cliente, profile=tecnico[1],
        respuestas={"categoria": "cliente", "motivo": "El cliente no esta"},
        requiere_noc=False,
    )
    serv.bloquear(
        del_noc, profile=tecnico[1],
        respuestas={"categoria": "acceso", "motivo": "Sin acceso al poste",
                    "necesita_de_noc": "Gestionar permiso"},
        requiere_noc=True,
    )

    todos = serv.abiertos_de(org_a)
    solo_noc = serv.abiertos_de(org_a, solo_noc=True)

    assert len(todos) == 2
    assert len(solo_noc) == 1
    assert solo_noc[0]["orden_id"] == str(del_noc.id)
    # Y las dos órdenes están bloqueadas: el filtro «Bloqueados» las ve a las dos.
    del_cliente.refresh_from_db()
    del_noc.refresh_from_db()
    assert del_cliente.estado_operativo == OrdenTrabajo.BLOQUEADA
    assert del_noc.estado_operativo == OrdenTrabajo.BLOQUEADA


def test_c_requiere_noc_no_se_deduce_del_formulario_del_isp(orden, tecnico):
    """Aunque el ISP llene «necesita_de_noc», el booleano lo decide quien llama.

    Si se dedujera de ese campo, la empresa que lo llame «pedido a mesa» rompería
    el filtro sin tocar una línea de código.
    """
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1],
        respuestas={"categoria": "material", "motivo": "Falta drop",
                    "necesita_de_noc": "texto que menciona al NOC"},
        requiere_noc=False,
    )
    assert bloqueo.requiere_noc is False
    # El texto igual se conserva: es lo que dijo la persona.
    assert "NOC" in bloqueo.necesita


def test_d_reportar_sin_detener_es_valido_y_se_distingue(orden, tecnico):
    """Algo demora pero el técnico sigue: el hecho queda y el estado no se mueve."""
    antes = orden.estado_operativo
    bloqueo, evento, detuvo = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS,
        requiere_noc=True, detener=False,
    )
    orden.refresh_from_db()
    assert detuvo is False
    assert orden.estado_operativo == antes
    assert bloqueo.detuvo_el_trabajo is False
    # El reporte existe igual, y aparece en la bandeja del NOC.
    assert evento.tipo == "bloqueo_campo"
    assert len(serv.abiertos_de(orden.org, solo_noc=True)) == 1
    # Y NO hay evento de transición.
    assert not EventoTrabajo.objects.filter(
        orden=orden, tipo="bloqueo_detuvo_el_trabajo"
    ).exists()


# --------------------------------------------------------------------------- #
# E-H. El retorno no se adivina
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "estado_inicial",
    [OrdenTrabajo.ASIGNADA, OrdenTrabajo.EN_CAMINO, OrdenTrabajo.EN_SITIO,
     OrdenTrabajo.CORRECCION_REQUERIDA],
)
def test_e_vuelve_al_estado_desde_el_que_se_bloqueo(
    org_a, version, tecnico, estado_inicial
):
    """Desde los cuatro, y a los cuatro. No hay un `bloqueada -> en_sitio` fijo.

    Puede haber un bloqueo ANTES de llegar al sitio --no hay acceso a la calle-- y
    volver siempre a `en_sitio` inventaría que el técnico llegó.
    """
    o = _orden(org_a, version, tecnico[1], 4200 + len(estado_inicial),
               estado=estado_inicial)
    bloqueo, _e, _d = serv.bloquear(
        o, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    o.refresh_from_db()
    assert o.estado_operativo == OrdenTrabajo.BLOQUEADA
    assert bloqueo.estado_operativo_anterior == estado_inicial

    bloqueo, _ev, volvio_a = serv.resolver(
        bloqueo, profile=tecnico[1], que_se_hizo="Se gestiono el acceso",
        resuelto_por_rol=BloqueoDeTrabajo.COORDINACION,
    )
    o.refresh_from_db()
    assert volvio_a == estado_inicial
    assert o.estado_operativo == estado_inicial
    assert bloqueo.volvio_a == estado_inicial


def test_f_se_puede_pedir_otro_destino_y_la_maquina_lo_valida(orden, tecnico):
    """El mundo cambió mientras estaba trabado: se puede volver a otro estado."""
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=False
    )
    bloqueo, _ev, volvio_a = serv.resolver(
        bloqueo, profile=tecnico[1], que_se_hizo="Se resolvio, pero hay que volver a salir",
        volver_a=OrdenTrabajo.EN_CAMINO,
    )
    orden.refresh_from_db()
    assert volvio_a == OrdenTrabajo.EN_CAMINO
    assert orden.estado_operativo == OrdenTrabajo.EN_CAMINO


def test_g_un_destino_ilegal_se_niega_y_no_deja_nada_a_medias(orden, tecnico):
    """`completada_campo` no es un retorno legal desde `bloqueada`."""
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=False
    )
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.resolver(
            bloqueo, profile=tecnico[1], que_se_hizo="intento saltar el paso",
            volver_a=OrdenTrabajo.COMPLETADA_CAMPO,
        )
    assert "No se puede devolver" in str(e.value)

    # Nada quedó a medias: la orden sigue bloqueada y el bloqueo sigue abierto.
    orden.refresh_from_db()
    bloqueo.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.BLOQUEADA
    assert bloqueo.resuelto_en is None


def test_h_el_estado_anterior_no_se_deduce_del_ultimo_evento(orden, tecnico):
    """Se persiste al abrir. Aunque pasen otros eventos en el medio."""
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    # Ruido: más eventos después del bloqueo.
    for i in range(3):
        EventoTrabajo.objects.create(
            org=orden.org, orden=orden, tipo="contexto_refrescado",
            profile=tecnico[1], datos={"nuevo_estado": "cualquier_cosa"},
        )
    bloqueo.refresh_from_db()
    assert bloqueo.estado_operativo_anterior == OrdenTrabajo.EN_SITIO
    _b, _ev, volvio = serv.resolver(
        bloqueo, profile=tecnico[1], que_se_hizo="listo"
    )
    assert volvio == OrdenTrabajo.EN_SITIO


# --------------------------------------------------------------------------- #
# I-L. Lo que se niega
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "estado",
    [OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA, OrdenTrabajo.CANCELADA],
)
def test_i_un_trabajo_terminado_no_se_bloquea(org_a, version, tecnico, estado):
    o = _orden(org_a, version, tecnico[1], 4300 + len(estado), estado=estado)
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.bloquear(o, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)
    assert "no se puede detener" in str(e.value)
    o.refresh_from_db()
    assert o.estado_operativo == estado
    # Y no quedó ni el reporte: si no se puede detener, no se abre el hecho.
    assert not BloqueoDeTrabajo.objects.filter(orden=o).exists()


def test_j_el_mapa_declara_desde_donde_se_bloquea_y_coincide(org_a):
    """La guarda del mapa: los cuatro estados, y NADA MAS.

    Se afirma sobre el MAPA y no con `if` sueltos, que es lo que pidió quedar
    escrito. Si alguien agrega `completada_campo` acá, esta prueba lo dice.
    """
    assert SE_PUEDE_BLOQUEAR_DESDE == frozenset({
        OrdenTrabajo.ASIGNADA,
        OrdenTrabajo.EN_CAMINO,
        OrdenTrabajo.EN_SITIO,
        OrdenTrabajo.CORRECCION_REQUERIDA,
    })
    # Y el mapa de transiciones concuerda: los cuatro pueden ir a bloqueada.
    for estado in SE_PUEDE_BLOQUEAR_DESDE:
        assert OrdenTrabajo.BLOQUEADA in TRANSICIONES_PERMITIDAS[estado], estado
    # Los terminales no.
    for estado in (OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.CERRADA,
                   OrdenTrabajo.CANCELADA):
        assert OrdenTrabajo.BLOQUEADA not in TRANSICIONES_PERMITIDAS[estado], estado


def test_k_agregar_bloqueada_no_abrio_los_otros_caminos(orden, tecnico):
    """La máquina sigue negando lo que negaba antes de esta fase."""
    with pytest.raises(TransicionInvalidaError):
        # en_sitio -> en_camino seguía prohibido, y sigue.
        ejecutar_accion_operativa(orden, "marcar_en_camino", profile=tecnico[1])


def test_l_no_hay_dos_bloqueos_abiertos_por_orden(orden, tecnico):
    serv.bloquear(orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.bloquear(orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)
    assert "ya tiene un bloqueo abierto" in str(e.value)


def test_m_la_base_tambien_lo_impide_no_solo_el_servicio(orden, tecnico):
    """El `select` previo del servicio es cortesía; la garantía está en la base.

    Ahí vive la carrera: dos pedidos a la vez pasan los dos por el `select` y los
    dos creen que pueden crear.
    """
    serv.bloquear(orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BloqueoDeTrabajo.objects.create(
                org=orden.org, orden=orden, abierto_por=tecnico[1],
                estado_operativo_anterior=OrdenTrabajo.EN_SITIO,
            )


def test_n_un_bloqueo_resuelto_no_se_resuelve_otra_vez(orden, tecnico):
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    serv.resolver(bloqueo, profile=tecnico[1], que_se_hizo="se gestiono")
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.resolver(bloqueo, profile=tecnico[1], que_se_hizo="otra vez")
    assert "ya estaba resuelto" in str(e.value)


def test_o_resolver_exige_decir_que_se_hizo(orden, tecnico):
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.resolver(bloqueo, profile=tecnico[1], que_se_hizo="   ")
    assert "que_se_hizo" in e.value.errores


def test_p_un_rol_inventado_se_rechaza(orden, tecnico):
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.resolver(
            bloqueo, profile=tecnico[1], que_se_hizo="algo",
            resuelto_por_rol="presidente",
        )
    assert "no es un rol conocido" in str(e.value)


def test_q_un_bloqueo_con_el_formulario_incompleto_no_abre_nada(orden, tecnico):
    """La validación del esquema sigue mandando, y el bloqueo no queda a medias."""
    with pytest.raises(serv.BloqueoInvalido) as e:
        serv.bloquear(
            orden, profile=tecnico[1],
            respuestas={"categoria": "acceso"},  # falta el motivo
            requiere_noc=True,
        )
    assert "motivo" in e.value.errores
    assert not BloqueoDeTrabajo.objects.filter(orden=orden).exists()
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.EN_SITIO


# --------------------------------------------------------------------------- #
# R-T. La línea de tiempo cuenta los minutos detenidos
# --------------------------------------------------------------------------- #

def test_r_la_linea_de_tiempo_cuenta_la_historia_completa(orden, tecnico, jefe):
    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    serv.resolver(
        bloqueo, profile=jefe[1], que_se_hizo="Coordinación gestionó el acceso",
        resuelto_por_rol=BloqueoDeTrabajo.COORDINACION,
    )
    seg.registrar(
        orden, profile=tecnico[1], momento=seg.AVANCE,
        respuestas={"nota": "sigo con el empalme"},
    )

    t = seg.linea_de_tiempo(orden)
    tipos = [e["tipo"] for e in t["eventos"]]
    assert tipos == [
        "bloqueo_campo",
        "bloqueo_detuvo_el_trabajo",
        "bloqueo_libero_el_trabajo",
        "bloqueo_resuelto",
        "avance_campo",
    ]
    por_tipo = {e["tipo"]: e for e in t["eventos"]}
    # El reporte humano trae su detalle leído con su esquema.
    assert por_tipo["bloqueo_campo"]["detalle"]
    # La transición trae el estado.
    assert por_tipo["bloqueo_detuvo_el_trabajo"]["estado_nuevo"] == "bloqueada"
    assert por_tipo["bloqueo_libero_el_trabajo"]["estado_nuevo"] == "en_sitio"
    # La resolución dice quién, qué y cuántos minutos.
    resuelto = por_tipo["bloqueo_resuelto"]
    assert resuelto["datos"]["que_se_hizo"].startswith("Coordinación")
    assert resuelto["datos"]["resuelto_por_rol"] == "coordinacion"
    assert resuelto["datos"]["minutos_detenido"] >= 0
    assert resuelto["etiqueta"] == "BLOQUEO RESUELTO"


def test_s_solo_se_exponen_las_claves_nombradas(orden, tecnico):
    """`datos` es un JSONField: volcarlo entero dejaría salir cualquier cosa."""
    EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="bloqueo_resuelto", profile=tecnico[1],
        datos={"que_se_hizo": "algo", "secreto_que_nadie_pidio": "no debe salir"},
    )
    t = seg.linea_de_tiempo(orden)
    ev = [e for e in t["eventos"] if e["tipo"] == "bloqueo_resuelto"][0]
    assert ev["datos"] == {"que_se_hizo": "algo"}
    assert "secreto_que_nadie_pidio" not in ev["datos"]


def test_t_los_minutos_detenidos_quedan_medidos(orden, tecnico):
    """Es lo que después explica por qué la intervención tardó."""
    from datetime import timedelta
    from django.utils import timezone

    bloqueo, _e, _d = serv.bloquear(
        orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True
    )
    # Se lo corre para atrás: 18 minutos detenido.
    bloqueo.abierto_en = timezone.now() - timedelta(minutes=18)
    bloqueo.save(update_fields=["abierto_en", "updated_at"])
    bloqueo, evento, _v = serv.resolver(
        bloqueo, profile=tecnico[1], que_se_hizo="se gestiono el acceso"
    )
    assert 17 <= bloqueo.minutos_detenido <= 19
    assert 17 <= evento.datos["minutos_detenido"] <= 19


# --------------------------------------------------------------------------- #
# U-Y. Por la API
# --------------------------------------------------------------------------- #

def test_u_el_bloqueo_por_la_ruta_de_seguimiento_abre_la_fila(orden, org_a, tecnico):
    """UN SOLO CAMINO: si esta ruta escribiera solo el evento, la bandeja del NOC
    se quedaría sin la fila."""
    user, prof = tecnico
    r = _cliente(user, org_a, prof).post(
        f"/api/campo/trabajos/{orden.id}/seguimiento/",
        {"momento": "bloqueo", "respuestas": RESPUESTAS, "requiere_noc": True},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert BloqueoDeTrabajo.objects.filter(orden=orden, requiere_noc=True).count() == 1
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.BLOQUEADA


def test_v_detener_false_por_la_api_no_mueve_el_estado(orden, org_a, tecnico):
    user, prof = tecnico
    r = _cliente(user, org_a, prof).post(
        f"/api/campo/trabajos/{orden.id}/seguimiento/",
        {"momento": "bloqueo", "respuestas": RESPUESTAS, "requiere_noc": False,
         "detener": False},
        format="json",
    )
    assert r.status_code == 201
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.EN_SITIO


def test_w_resolver_por_la_api(orden, org_a, tecnico, jefe):
    serv.bloquear(orden, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)
    user, prof = jefe
    r = _cliente(user, org_a, prof).post(
        f"/api/campo/trabajos/{orden.id}/bloqueo/resolver/",
        {"que_se_hizo": "Se gestiono el permiso", "resuelto_por_rol": "noc"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["volvio_a"] == OrdenTrabajo.EN_SITIO
    assert r.data["estado_operativo"] == OrdenTrabajo.EN_SITIO
    assert r.data["bloqueo"]["resuelto_por_rol"] == "noc"


def test_x_resolver_sin_bloqueo_abierto_da_409(orden, org_a, jefe):
    """409 y no 404: la orden existe, lo que no hay es un bloqueo."""
    user, prof = jefe
    r = _cliente(user, org_a, prof).post(
        f"/api/campo/trabajos/{orden.id}/bloqueo/resolver/",
        {"que_se_hizo": "algo"}, format="json",
    )
    assert r.status_code == 409


def test_y_la_bandeja_separa_los_dos_filtros_por_la_api(org_a, version, tecnico, jefe):
    del_cliente = _orden(org_a, version, tecnico[1], 4501)
    del_noc = _orden(org_a, version, tecnico[1], 4502)
    serv.bloquear(del_cliente, profile=tecnico[1],
                  respuestas={"categoria": "cliente", "motivo": "no esta"},
                  requiere_noc=False)
    serv.bloquear(del_noc, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)

    user, prof = jefe
    c = _cliente(user, org_a, prof)
    todos = c.get("/api/campo/bloqueos/")
    solo = c.get("/api/campo/bloqueos/?requiere_noc=1")
    assert todos.data["total"] == 2
    assert solo.data["total"] == 1
    assert solo.data["bloqueos"][0]["orden_id"] == str(del_noc.id)


def test_z_otra_empresa_no_ve_los_bloqueos(org_a, org_b, version, tecnico,
                                           django_user_model):
    """Cero filas, no «no aparece en la lista»."""
    o = _orden(org_a, version, tecnico[1], 4601)
    serv.bloquear(o, profile=tecnico[1], respuestas=RESPUESTAS, requiere_noc=True)

    user = django_user_model.objects.create_user(
        email="otra.bloq@empresa.com", password="testpass123"
    )
    prof_b = Profile.objects.create(user=user, org=org_b, role="ADMIN", is_active=True)
    r = _cliente(user, org_b, prof_b).get("/api/campo/bloqueos/")
    assert r.data["total"] == 0
    assert r.data["bloqueos"] == []
    # Y por el servicio, lo mismo.
    assert serv.abiertos_de(org_b) == []
