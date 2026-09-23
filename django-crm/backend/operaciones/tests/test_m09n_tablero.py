# -*- coding: utf-8 -*-
"""
================================================================================
 M09-N  --  el tablero: contexto resuelto y feed de actividad
================================================================================

QUE SE AGREGO Y POR QUE HAY QUE VIGILARLO
-----------------------------------------
El tablero necesitaba mostrar la zona, el tecnico y el ticket del proveedor de
cada hallazgo. Los tres ya existian --en 'ProgramacionOrden', en
'campo.AsignacionTrabajo' y en 'cases.Case'-- y lo que faltaba era alcanzarlos.
'contexto_propuesta.contexto_de' los resuelve para el lote entero.

Ese modulo toca tres aplicaciones desde una cuarta, asi que tiene tres maneras
de salir mal que ninguna prueba anterior miraria:

  1. QUE DEVUELVA EL TECNICO EQUIVOCADO. 'responsable_sugerido' es a quien la
     IA propone. Ponerlo en la columna 'Tecnico' afirmaria que alguien ya tiene
     la orden. §1 lo afirma sobre el EFECTO: se crea una propuesta CON
     responsable sugerido y SIN asignacion, y el contexto tiene que salir
     vacio.

  2. QUE FILTRE COORDENADAS. 'campo.OrdenTrabajo' tiene gps_lat/gps_lng, y son
     PII: 'programacion-noc.js::leerOrden' las quita en el servidor a
     proposito. §2 afirma que no aparecen en ninguna clave del contexto, con
     una orden que SI las tiene pobladas -- una prueba con la orden en blanco
     pasaria sin probar nada.

  3. QUE CRUCE ORGANIZACIONES. 'origen_id' es texto libre: nada impide que
     apunte a una orden de otro tenant. §3 lo intenta a proposito.

Y el feed ('auditoria.recientes') tiene la suya: es la unica ruta nueva del
modulo, y el Shadow Mode vive de que ninguna ruta escriba. §4 lo afirma
contando filas antes y despues, no leyendo la vista.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from conftest import rls_org
from operaciones import auditoria, contexto_propuesta
from operaciones.models import PropuestaSupervisor

RUTA_FEED = "/api/operaciones/actividad-supervisor/"


# =============================================================================
#  utilidades
# =============================================================================

def _propuesta(org, **extra):
    """Una propuesta valida. La evidencia la exige una restriccion de la base."""
    datos = dict(
        org=org,
        tipo_senal=PropuestaSupervisor.ORDEN_SIN_PROGRAMAR,
        origen_tipo="orden_trabajo",
        origen_id=str(uuid.uuid4()),
        accion_propuesta="Programar la orden",
        motivo="Lleva 3 dias abierta sin fecha.",
        evidencia=[{
            "fuente": "campo.OrdenTrabajo",
            "id": "ot-1",
            "dato": "sin programada_para",
            "observado_en": timezone.now().isoformat(),
        }],
        prioridad=30,
        impacto="El cliente no tiene fecha",
        huella_condicion="huella-" + uuid.uuid4().hex[:8],
        expira_en=timezone.now() + timezone.timedelta(days=7),
    )
    datos.update(extra)
    return PropuestaSupervisor.objects.create(**datos)


def _orden(org, **extra):
    """
    Una orden de trabajo minima, con su tipo de trabajo.

    El codigo del WorkType lleva un sufijo unico: es unico por organizacion, y
    varias pruebas de este archivo crean mas de una orden.
    """
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    sufijo = uuid.uuid4().hex[:8]
    tipo = WorkType.objects.create(
        org=org, nombre=f"Instalacion {sufijo}", codigo=f"ins_{sufijo}")
    version = WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})
    datos = dict(
        org=org,
        numero=1842,
        tipo_trabajo_version=version,
        cliente_nombre="Cliente de prueba",
        cliente_direccion="Calle 1 #2-3",
    )
    datos.update(extra)
    return OrdenTrabajo.objects.create(**datos)


def _perfil(org, correo):
    from common.models import Profile, User
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org, role="OPERACIONES",
                                  is_active=True)


# =============================================================================
#  §1  EL TECNICO ES LA ASIGNACION REAL, NUNCA LA SUGERENCIA
# =============================================================================

def test_una_propuesta_con_responsable_sugerido_y_sin_asignacion_no_tiene_tecnico(org_a):
    """
    LA PRUEBA QUE IMPORTA DE TODO EL ARCHIVO.

    'responsable_sugerido' esta poblado, la orden existe, y NADIE la tiene
    asignada. Si el contexto devolviera ese nombre, la pantalla diria que Ana
    esta trabajando en algo que nadie le dio.

    Se afirma sobre el EFECTO -- el valor que sale -- y no sobre que el codigo
    no mencione 'responsable_sugerido': un 'or' de respaldo agregado despues
    pasaria esa segunda version sin que nadie se entere.
    """
    with rls_org(org_a):
        ana = _perfil(org_a, "ana@prueba.co")
        orden = _orden(org_a)
        propuesta = _propuesta(
            org_a, origen_id=str(orden.id), responsable_sugerido=ana)

        contexto = contexto_propuesta.contexto_de(org_a, [propuesta])

    assert propuesta.responsable_sugerido_id == ana.id, "el montaje debe tener sugerido"
    assert contexto[str(propuesta.id)]["tecnico"] == ""
    # Y el numero de la orden SI sale: lo que falta es el tecnico, no el enlace.
    assert contexto[str(propuesta.id)]["orden_numero"] == 1842


def test_el_tecnico_sale_cuando_hay_asignacion_principal(org_a):
    from campo.models import AsignacionTrabajo

    with rls_org(org_a):
        luis = _perfil(org_a, "luis@prueba.co")
        orden = _orden(org_a)
        AsignacionTrabajo.objects.create(
            orden=orden, profile=luis, es_principal=True)
        propuesta = _propuesta(org_a, origen_id=str(orden.id))

        contexto = contexto_propuesta.contexto_de(org_a, [propuesta])

    # 'name' cuando lo hay, el correo cuando no. 'create_user' deriva el name
    # del correo, asi que aqui sale 'luis'; lo que se afirma es que sale la
    # persona ASIGNADA y no una cadena vacia.
    assert contexto[str(propuesta.id)]["tecnico"] == luis.user.name


def test_una_cuadrilla_sin_principal_no_elige_a_uno_cualquiera(org_a):
    """
    Tres personas asignadas y ninguna marcada como principal. "Hay tres
    personas" no responde "quien responde por esto", asi que sale vacio en vez
    de la primera de la lista.
    """
    from campo.models import AsignacionTrabajo

    with rls_org(org_a):
        orden = _orden(org_a)
        for i in range(3):
            AsignacionTrabajo.objects.create(
                orden=orden, profile=_perfil(org_a, f"p{i}@prueba.co"),
                es_principal=False)
        propuesta = _propuesta(org_a, origen_id=str(orden.id))

        contexto = contexto_propuesta.contexto_de(org_a, [propuesta])

    assert contexto[str(propuesta.id)]["tecnico"] == ""


# =============================================================================
#  §2  LAS COORDENADAS NO SALEN
# =============================================================================

def test_el_contexto_no_devuelve_coordenadas_aunque_la_orden_las_tenga(org_a):
    """
    La orden tiene gps_lat/gps_lng POBLADOS. Con la orden en blanco esta
    prueba pasaria sin probar nada.

    No es una omision: 'programacion-noc.js::leerOrden' ya las quita en el
    servidor junto con el telefono. Mientras la decision de PII no se tome,
    ningun camino nuevo las expone.
    """
    with rls_org(org_a):
        orden = _orden(org_a, gps_lat=10.9878, gps_lng=-74.7889)
        propuesta = _propuesta(org_a, origen_id=str(orden.id))

        contexto = contexto_propuesta.contexto_de(org_a, [propuesta])

    fila = contexto[str(propuesta.id)]
    assert orden.gps_lat is not None, "el montaje debe tener coordenadas"
    plano = " ".join(str(v) for v in fila.values())
    for prohibido in ("10.98", "-74.78", "lat", "lng", "gps"):
        assert prohibido not in plano, f"se filtro {prohibido}"
    assert set(fila) == {
        "zona", "tecnico", "ticket_externo", "proveedor_externo", "orden_numero"}


# =============================================================================
#  §3  AISLAMIENTO ENTRE ORGANIZACIONES
# =============================================================================

def test_una_propuesta_que_apunta_a_una_orden_ajena_no_la_alcanza(org_a, org_b):
    """
    'origen_id' es un CharField: nada impide que apunte a una orden de otro
    tenant. El filtro por org va en la consulta, no en la confianza.
    """
    with rls_org(org_b):
        ajena = _orden(org_b, numero=9999)

    with rls_org(org_a):
        propuesta = _propuesta(org_a, origen_id=str(ajena.id))
        contexto = contexto_propuesta.contexto_de(org_a, [propuesta])

    assert contexto[str(propuesta.id)]["orden_numero"] is None


# =============================================================================
#  §4  EL CONTEXTO NO SE CAE NI INVENTA
# =============================================================================

def test_un_origen_que_no_es_un_uuid_no_tumba_el_lote(org_a):
    """
    'origen_id' es texto libre. Un valor raro no puede llevarse por delante la
    lista entera con un DataError -- las demas propuestas tienen que llegar.
    """
    with rls_org(org_a):
        orden = _orden(org_a)
        rota = _propuesta(org_a, origen_id="no-soy-un-uuid")
        sana = _propuesta(org_a, origen_id=str(orden.id))

        contexto = contexto_propuesta.contexto_de(org_a, [rota, sana])

    assert contexto[str(rota.id)]["orden_numero"] is None
    assert contexto[str(sana.id)]["orden_numero"] == 1842


def test_toda_propuesta_del_lote_tiene_entrada(org_a):
    """
    Incluso las que no alcanzan nada. Quien lee el dict no deberia tener que
    distinguir "no estaba" de "no tiene".
    """
    with rls_org(org_a):
        unas = [_propuesta(org_a, origen_tipo="actividad") for _ in range(3)]
        contexto = contexto_propuesta.contexto_de(org_a, unas)

    assert set(contexto) == {str(p.id) for p in unas}
    for fila in contexto.values():
        assert fila["tecnico"] == "" and fila["zona"] == ""


def test_un_lote_vacio_devuelve_un_dict_vacio_sin_consultar(org_a):
    assert contexto_propuesta.contexto_de(org_a, []) == {}


# =============================================================================
#  §5  EL FEED LEE Y NO ESCRIBE
# =============================================================================

def test_el_feed_no_escribe_ninguna_fila(org_a, admin_client, admin_profile):
    """
    La regla del Shadow Mode: ninguna ruta de este modulo produce trabajo. Se
    cuenta antes y despues -- no se lee la vista para concluir que no vio una
    escritura.
    """
    from common.models import Activity

    with rls_org(org_a):
        propuesta = _propuesta(org_a)
        auditoria.registrar(
            org=org_a, actor=None, accion="CREATED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id,
            nombre="Orden sin programar")
        antes_actividad = Activity.objects.count()
        antes_propuestas = PropuestaSupervisor.objects.count()

    r = admin_client.get(RUTA_FEED)
    assert r.status_code == 200

    with rls_org(org_a):
        assert Activity.objects.count() == antes_actividad
        assert PropuestaSupervisor.objects.count() == antes_propuestas


def test_el_feed_solo_trae_las_entidades_de_este_modulo(org_a, admin_client,
                                                        admin_profile):
    """
    'common.Activity' es la auditoria del CRM entero. Sin el filtro, el feed
    del Supervisor se llenaria de contactos editados: cierto, pero no es lo que
    esta pantalla pregunta.
    """
    from common.models import Activity

    with rls_org(org_a):
        propuesta = _propuesta(org_a)
        auditoria.registrar(
            org=org_a, actor=None, accion="CREATED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id,
            nombre="Orden sin programar")
        Activity.objects.create(
            org=org_a, user=None, action="UPDATED", entity_type="Contact",
            entity_id=uuid.uuid4(), entity_name="Un contacto cualquiera")

    r = admin_client.get(RUTA_FEED)
    entidades = {f["entidad"] for f in r.json()["resultados"]}

    assert "Contact" not in entidades
    assert entidades == {auditoria.ENTIDAD_PROPUESTA}


def test_el_feed_marca_como_ia_lo_que_no_tiene_usuario(org_a, admin_client,
                                                       admin_profile):
    """
    'user=None' es como se reconoce lo que escribio el Supervisor -- no por un
    usuario de sistema inventado que despues se confunda con una persona.
    """
    with rls_org(org_a):
        propuesta = _propuesta(org_a)
        auditoria.registrar(
            org=org_a, actor=None, accion="CREATED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id)
        auditoria.registrar(
            org=org_a, actor=admin_profile, accion="APPROVED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id)

    filas = admin_client.get(RUTA_FEED).json()["resultados"]
    por_accion = {f["accion"]: f for f in filas}

    assert por_accion["CREATED"]["es_ia"] is True
    assert por_accion["CREATED"]["quien"] == "Supervisor NOC IA"
    assert por_accion["APPROVED"]["es_ia"] is False


def test_el_feed_respeta_el_limite_y_no_acepta_uno_absurdo(org_a, admin_client,
                                                           admin_profile):
    with rls_org(org_a):
        propuesta = _propuesta(org_a)
        for _ in range(6):
            auditoria.registrar(
                org=org_a, actor=None, accion="CREATED",
                entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id)

    assert len(admin_client.get(RUTA_FEED + "?limite=3").json()["resultados"]) == 3
    # Un limite basura no revienta ni trae la tabla entera: cae al de por
    # defecto y sigue acotado.
    assert admin_client.get(RUTA_FEED + "?limite=abc").status_code == 200
    assert len(admin_client.get(RUTA_FEED + "?limite=99999").json()["resultados"]) <= 100


def test_el_feed_lo_mas_reciente_primero(org_a, admin_client, admin_profile):
    with rls_org(org_a):
        propuesta = _propuesta(org_a)
        for accion in ("CREATED", "STATUS_CHANGED", "APPROVED"):
            auditoria.registrar(
                org=org_a, actor=None, accion=accion,
                entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=propuesta.id)

    acciones = [f["accion"] for f in admin_client.get(RUTA_FEED).json()["resultados"]]
    assert acciones[0] == "APPROVED"


def test_el_feed_no_cruza_organizaciones(org_a, org_b, admin_client, admin_profile):
    with rls_org(org_b):
        ajena = _propuesta(org_b)
        auditoria.registrar(
            org=org_b, actor=None, accion="CREATED",
            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=ajena.id,
            nombre="De la otra empresa")

    filas = admin_client.get(RUTA_FEED).json()["resultados"]
    assert all(f["nombre"] != "De la otra empresa" for f in filas)


# =============================================================================
#  §6  LA LISTA DE PROPUESTAS SIGUE SIENDO LA MISMA, CON MAS CAMPOS
# =============================================================================

def test_la_lista_trae_el_contexto_resuelto(org_a, admin_client, admin_profile):
    from campo.models import AsignacionTrabajo

    with rls_org(org_a):
        luis = _perfil(org_a, "luis2@prueba.co")
        orden = _orden(org_a)
        AsignacionTrabajo.objects.create(
            orden=orden, profile=luis, es_principal=True)
        _propuesta(org_a, origen_id=str(orden.id))

    fila = admin_client.get("/api/operaciones/propuestas/").json()["resultados"][0]

    assert fila["tecnico"] == luis.user.name
    assert fila["tecnico"] != ""
    assert fila["orden_numero"] == 1842
    # Y lo que no hay sale vacio, no ausente: el frontend lee la clave siempre.
    assert fila["zona"] == ""
    assert fila["ticket_externo"] == ""


def test_la_lista_no_expone_responsable_sugerido_como_tecnico(org_a, admin_client,
                                                              admin_profile):
    """La §1, pero atravesando la API entera."""
    with rls_org(org_a):
        ana = _perfil(org_a, "ana2@prueba.co")
        orden = _orden(org_a)
        _propuesta(org_a, origen_id=str(orden.id), responsable_sugerido=ana)

    fila = admin_client.get("/api/operaciones/propuestas/").json()["resultados"][0]
    assert fila["tecnico"] == ""
    assert "ana2@prueba.co" not in str(fila)
