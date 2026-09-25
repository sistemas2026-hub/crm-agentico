# -*- coding: utf-8 -*-
"""
================================================================================
 LOS DOS CAMINOS QUE CREABAN ORDENES SIN PASAR POR EL SERVICIO
================================================================================

El 08/09/2026 el comando 'seed_campo_demo' sembro en la base de PRODUCCION una
organizacion completa, un tecnico con contrasena publicada en el repositorio y
la orden 1842. Nadie se salto ningun control: el comando no tenia ninguno.

El segundo camino nunca llego a usarse pero estaba abierto: el alta de
'OrdenTrabajo' en el admin de Django, donde '/admin/' esta exento del
middleware de organizacion y el desplegable lista TODAS las empresas.

QUE SE AFIRMA AQUI
------------------
El EFECTO, no la presencia del candado:

  * con DEBUG=False el comando levanta Y no deja ni una fila -- se cuenta
    antes y despues, porque "levanto" y "no escribio" son dos cosas distintas
    y la segunda es la que importa;
  * sin '--org', o con un id que no existe, NO aparece ninguna organizacion
    nueva (que es exactamente lo que paso en produccion);
  * la contrasena que estuvo publicada YA NO SIRVE contra el usuario que el
    comando crea;
  * por HTTP, el formulario de alta del admin contesta 403 a un superusuario
    -- medido contra la ruta, no leyendo 'has_add_permission';
  * el listado del admin sigue respondiendo 200, porque cerrar el alta no
    puede costar la consulta.
================================================================================
"""

from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Org, Profile, User

pytestmark = pytest.mark.django_db

#  La que estuvo en el repositorio hasta este commit. Se nombra asi para que
#  nadie la copie creyendo que es una credencial en uso: la prueba existe para
#  afirmar que ya NO abre nada.
CLAVE_QUE_ESTUVO_PUBLICADA = "campo12345"
EMAIL_DEMO = "carlos.tecnico@demo.local"


def _conteos():
    return {
        "orgs": Org.objects.count(),
        "usuarios": User.objects.count(),
        "ordenes": OrdenTrabajo.objects.count(),
        "plantillas": WorkType.objects.count(),
    }


# =============================================================================
#  §1  El comando en produccion
# =============================================================================

@override_settings(DEBUG=False)
def test_con_debug_apagado_el_seed_se_niega_y_no_escribe_nada(org_a):
    antes = _conteos()

    with pytest.raises(CommandError) as e:
        call_command("seed_campo_demo", "--org", str(org_a.id))

    assert "DEBUG=False" in str(e.value)
    #  Lo que de verdad importa: que no quede rastro. Un comando que levanta
    #  DESPUES de escribir la mitad seria igual de malo que no levantar.
    assert _conteos() == antes


@override_settings(DEBUG=False)
def test_con_debug_apagado_se_niega_aunque_los_argumentos_sean_correctos(org_a):
    """El entorno se comprueba ANTES que nada: no hay combinacion que lo pase."""
    with pytest.raises(CommandError):
        call_command("seed_campo_demo", "--org", str(org_a.id),
                     "--email", "otro@demo.local", "--password", "x12345678")

    assert not User.objects.filter(email="otro@demo.local").exists()


# =============================================================================
#  §2  El comando en desarrollo
# =============================================================================

@override_settings(DEBUG=True)
def test_en_desarrollo_siembra_sobre_la_organizacion_indicada(org_a):
    orgs_antes = Org.objects.count()

    call_command("seed_campo_demo", "--org", str(org_a.id))

    # La siembra deja tres ordenes de dos tipos (lo exige
    # test_seed_deja_la_app_usable: con una sola no se ve una lista). Lo que
    # esta prueba mira es OTRA cosa -- que hayan caido en la organizacion
    # indicada-- asi que se afirma eso y no cuantas son.
    ordenes = list(OrdenTrabajo.objects.filter(org=org_a))
    assert ordenes, "no sembro ninguna orden en esa organizacion"
    assert any(o.estado_operativo == OrdenTrabajo.ASIGNADA for o in ordenes)
    assert WorkTypeVersion.objects.filter(
        work_type__org=org_a, estado=WorkTypeVersion.PUBLICADA).exists()
    assert Profile.objects.filter(org=org_a, user__email=EMAIL_DEMO).exists()
    #  Sembrar datos NO da de alta empresas, ni siquiera en desarrollo.
    assert Org.objects.count() == orgs_antes


@override_settings(DEBUG=True)
def test_la_orden_sembrada_se_declara_demo_y_no_finge_venir_de_wisphub(org_a):
    """
    Las tres de produccion dicen 'wisphub' y por eso costo rastrearlas: parecian
    tickets reales. Una orden de prueba tiene que decir que lo es.
    """
    call_command("seed_campo_demo", "--org", str(org_a.id))

    # Se afirma sobre TODAS y no sobre una: la semilla siembra tres ordenes de
    # dos tipos distintos (lo exige test_seed_deja_la_app_usable, porque con
    # una sola no se ve una lista ni se ve que el formulario cambia). Un
    # .get() aqui no probaba una propiedad mas fuerte -- probaba que hubiera
    # exactamente una, que es otra cosa y ya no es cierta.
    ordenes = list(OrdenTrabajo.objects.filter(org=org_a))
    assert ordenes, "la siembra no dejo ninguna orden"
    for orden in ordenes:
        assert orden.origen_sistema == "demo", orden.numero
        assert orden.origen_sistema != "wisphub", orden.numero

    # El texto de demostracion se exige en la que lo tiene: no todas llevan
    # diagnostico previo, y obligarlas a tenerlo seria inventar un dato.
    con_diagnostico = [o for o in ordenes if (o.diagnostico_previo or {}).get("resumen")]
    assert con_diagnostico, "ninguna orden trae diagnostico previo"
    assert any("DEMOSTRACION" in o.diagnostico_previo["resumen"].upper()
               for o in con_diagnostico)


@override_settings(DEBUG=True)
def test_dos_corridas_no_chocan_con_el_consecutivo(org_a):
    """El numero sale del consecutivo de la organizacion, no de un 1842 fijo."""
    call_command("seed_campo_demo", "--org", str(org_a.id))
    call_command("seed_campo_demo", "--org", str(org_a.id))

    # Lo que importa es que NINGUN numero se repita, no cuantos hay: la
    # siembra dejo de ser de una sola orden y contar aqui ataba esta prueba a
    # un detalle que no es el suyo.
    numeros = list(OrdenTrabajo.objects.filter(org=org_a)
                   .values_list("numero", flat=True))
    assert len(numeros) == len(set(numeros)), f"consecutivo repetido: {numeros}"
    assert len(numeros) >= 2, "dos corridas tienen que dejar mas de una orden"


# =============================================================================
#  §3  La organizacion: se recibe, no se inventa
# =============================================================================

@override_settings(DEBUG=True)
def test_sin_org_el_comando_no_corre(org_a):
    antes = _conteos()

    with pytest.raises(CommandError):
        call_command("seed_campo_demo")

    assert _conteos() == antes


@override_settings(DEBUG=True)
def test_con_una_organizacion_inexistente_no_la_crea(org_a):
    """El defecto exacto que ensucio produccion: 'get_or_create' por nombre."""
    inexistente = uuid.uuid4()
    orgs_antes = Org.objects.count()

    with pytest.raises(CommandError) as e:
        call_command("seed_campo_demo", "--org", str(inexistente))

    assert "NO crea organizaciones" in str(e.value)
    assert Org.objects.count() == orgs_antes
    assert not Org.objects.filter(name__icontains="Telecomunicaciones").exists()


@override_settings(DEBUG=True)
def test_un_org_que_no_es_uuid_no_pasa(org_a):
    with pytest.raises(CommandError):
        call_command("seed_campo_demo", "--org", "Rapilink Telecomunicaciones")


# =============================================================================
#  §4  La contrasena
# =============================================================================

@override_settings(DEBUG=True)
def test_la_clave_publicada_ya_no_abre_la_cuenta_que_siembra_el_comando(org_a):
    call_command("seed_campo_demo", "--org", str(org_a.id))

    user = User.objects.get(email=EMAIL_DEMO)
    assert not user.check_password(CLAVE_QUE_ESTUVO_PUBLICADA)


@override_settings(DEBUG=True)
def test_a_un_usuario_que_ya_existe_no_se_le_cambia_la_clave(org_a):
    """
    Sembrar datos no es una operacion de seguridad. Antes, cada corrida
    reescribia la contrasena del tecnico.
    """
    existente = User.objects.create_user(email=EMAIL_DEMO, password="mia-y-solo-mia-1")

    call_command("seed_campo_demo", "--org", str(org_a.id),
                 "--password", "intento-de-pisarla-1")

    existente.refresh_from_db()
    assert existente.check_password("mia-y-solo-mia-1")
    assert not existente.check_password("intento-de-pisarla-1")


@override_settings(DEBUG=True)
def test_con_password_explicita_la_usa_para_el_usuario_nuevo(org_a):
    call_command("seed_campo_demo", "--org", str(org_a.id),
                 "--email", "nuevo@demo.local", "--password", "elegida-local-1")

    assert User.objects.get(email="nuevo@demo.local").check_password("elegida-local-1")


# =============================================================================
#  §5  El admin: se consulta, no se crea
# =============================================================================

@pytest.fixture
def superusuario():
    u = User.objects.create_superuser(email="root@prueba.local", password="root-12345678")
    u.is_staff = True
    u.save()
    return u


@pytest.fixture
def cliente_admin(superusuario):
    c = Client()
    c.force_login(superusuario)
    return c


def test_el_admin_no_ofrece_crear_una_orden(cliente_admin):
    """Medido contra la RUTA: es lo que contesta el servidor, no la clase."""
    r = cliente_admin.get("/admin/campo/ordentrabajo/add/")

    assert r.status_code == 403


def test_por_http_no_se_puede_crear_una_orden_cruzando_organizacion(
        cliente_admin, org_a, org_b):
    """
    El escenario completo: un superusuario manda el formulario con la org de
    OTRA empresa. Antes, '/admin/' no tiene contexto de organizacion y el
    desplegable las lista todas.
    """
    wt = WorkType.objects.create(org=org_a, codigo="seg", nombre="Tipo seguridad")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})
    antes = OrdenTrabajo.objects.count()

    r = cliente_admin.post("/admin/campo/ordentrabajo/add/", {
        "org": str(org_b.id),
        "numero": 9999,
        "tipo_trabajo_version": str(version.id),
        "cliente_nombre": "Intento cruzado",
        "cliente_direccion": "Calle 1",
        "estado_validacion": "sin_evaluar",
        "vuelta": 1,
    })

    assert r.status_code == 403
    assert OrdenTrabajo.objects.count() == antes
    assert not OrdenTrabajo.objects.filter(org=org_b).exists()


def test_el_listado_del_admin_sigue_funcionando(cliente_admin, org_a):
    """Cerrar el alta no puede costar la consulta."""
    wt = WorkType.objects.create(org=org_a, codigo="seg2", nombre="Tipo seguridad 2")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=7777, tipo_trabajo_version=version,
        cliente_nombre="Visible", cliente_direccion="Calle 2",
        estado_operativo=OrdenTrabajo.ASIGNADA)

    lista = cliente_admin.get("/admin/campo/ordentrabajo/")
    detalle = cliente_admin.get(f"/admin/campo/ordentrabajo/{orden.id}/change/")

    assert lista.status_code == 200
    assert detalle.status_code == 200
    assert "Visible" in lista.content.decode()


def test_la_organizacion_no_es_editable_en_el_detalle(cliente_admin, org_a, org_b):
    """
    Mover una orden entre empresas desde un desplegable no es una correccion.
    Se afirma sobre el EFECTO: se manda el POST y la orden sigue donde estaba.
    """
    wt = WorkType.objects.create(org=org_a, codigo="seg3", nombre="Tipo seguridad 3")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=7778, tipo_trabajo_version=version,
        cliente_nombre="No se muda", cliente_direccion="Calle 3",
        estado_operativo=OrdenTrabajo.ASIGNADA)

    cliente_admin.post(f"/admin/campo/ordentrabajo/{orden.id}/change/", {
        "org": str(org_b.id),
        "tipo_trabajo_version": str(version.id),
        "cliente_nombre": "No se muda",
        "cliente_direccion": "Calle 3",
        "estado_validacion": "sin_evaluar",
        "vuelta": 1,
        "_continue": "Guardar y continuar editando",
    })

    orden.refresh_from_db()
    assert orden.org_id == org_a.id
