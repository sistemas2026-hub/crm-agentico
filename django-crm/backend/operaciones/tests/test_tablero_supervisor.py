# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE EL TABLERO PIDE Y LA API NO DABA
================================================================================

La pantalla del Supervisor tiene diez columnas, cuatro gráficos, un feed y un
mapa. El backend daba cuatro campos por propuesta y ningún feed.

Lo que se afirma aquí es el EFECTO sobre datos reales, y sobre todo **lo que el
backend hace cuando no sabe**: un caso sin ticket, una orden sin plan, una
organización sin actividad y un mapa sin coordenadas tienen que contestar algo
que la pantalla pueda pintar como "—" o "Sin registros", nunca un cero que
parezca medición ni un 404 que parezca avería.

LA REGLA QUE ATRAVIESA EL ARCHIVO
---------------------------------
Ningún valor por defecto disfrazado de dato. Si el backend no lo sabe, manda
None y el motivo.
================================================================================
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from cases.models import Case
from common.models import Activity, Profile, User
from common.serializer import OrgAwareRefreshToken
from conftest import rls_org
from operaciones import auditoria, indicadores, sla
from operaciones.contexto_operativo import (DEXTER, DEXTER_Y_WISPHUB, WISPHUB,
                                            contexto_de)
from operaciones.models import (ProgramacionOrden, ProgramacionSemanal,
                                PropuestaSupervisor)

pytestmark = pytest.mark.django_db

RUTA_ACTIVIDAD = "/api/operaciones/actividad-supervisor/"
RUTA_UBICACIONES = "/api/operaciones/ubicaciones/"


# ---------------------------------------------------------------------------
#  Datos
# ---------------------------------------------------------------------------
def _perfil(org, correo, rol="OPERACIONES"):
    u = User.objects.create_user(email=correo, password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=rol, is_active=True)


def _cliente(u, org, p):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org, p).access_token}"))
    return c


@pytest.fixture
def gestor(org_a):
    return _perfil(org_a, "jefe@tablero.test")


@pytest.fixture
def cliente(org_a, gestor):
    return _cliente(gestor[0], org_a, gestor[1])


def _caso(org, *, proveedor="", ticket="", nombre="Sin internet", **extra):
    return Case.objects.create(
        org=org, name=nombre, status="New", priority="Normal",
        provider=proveedor, external_ticket_id=ticket, **extra)


def _propuesta(org, *, origen_tipo="case", origen_id=None, tipo=None, **extra):
    datos = dict(
        org=org,
        tipo_senal=tipo or PropuestaSupervisor.CASO_ANTIGUO,
        origen_tipo=origen_tipo,
        origen_id=origen_id or str(uuid.uuid4()),
        accion_propuesta="Revisar el caso",
        motivo="Lleva mucho abierto",
        evidencia=[{"fuente": "case", "id": "c", "dato": "x",
                    "observado_en": timezone.now().isoformat()}],
        prioridad=40,
        huella_condicion="h-1",
        expira_en=timezone.now() + timedelta(days=7),
    )
    datos.update(extra)
    return PropuestaSupervisor.objects.create(**datos)


def _orden(org, numero=8100, estado=OrdenTrabajo.ASIGNADA):
    wt = WorkType.objects.create(org=org, codigo=f"tab{numero}", nombre="Tipo tablero")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema={"campos": [], "evidencias": []})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="Cliente tablero", cliente_direccion="Calle 1",
        estado_operativo=estado)


# =============================================================================
#  §1  Tickets por origen  --  el donut
# =============================================================================

def test_los_casos_se_cuentan_por_sistema_de_origen(org_a):
    _caso(org_a, proveedor="wisphub", ticket="WH-1")
    _caso(org_a, proveedor="wisphub", ticket="WH-2")
    _caso(org_a)                                   # nacido en el CRM

    por_origen = indicadores.indicadores_casos(org_a)["por_origen"]

    assert por_origen["wisphub"]["valor"] == 2
    #  Un caso sin proveedor NO es un dato faltante: es un caso del CRM.
    assert por_origen[DEXTER]["valor"] == 1


def test_una_organizacion_sin_casos_no_inventa_categorias(org_a):
    assert indicadores.indicadores_casos(org_a)["por_origen"] == {}


# =============================================================================
#  §2  Tendencias  --  reales donde se pueden calcular, ausentes donde no
# =============================================================================

def test_la_variacion_de_propuestas_se_calcula_contra_el_periodo_anterior(org_a):
    for _ in range(3):                              # periodo actual
        _propuesta(org_a)
    viejas = [_propuesta(org_a) for _ in range(2)]  # periodo anterior

    #  'ahora' se toma DESPUES de crear: la ventana es semiabierta [desde,
    #  hasta) y lo creado en el mismo instante que 'hasta' queda fuera, que es
    #  lo correcto -- pero hace que un test ingenuo cuente 0.
    ahora = timezone.now() + timedelta(seconds=1)
    desde, hasta = ahora - timedelta(days=7), ahora
    PropuestaSupervisor.objects.filter(
        id__in=[p.id for p in viejas]).update(created_at=ahora - timedelta(days=10))

    v = indicadores.indicadores_supervisor(
        org_a, desde=desde, hasta=hasta, ahora=ahora)["variaciones"]["propuestas"]

    assert v["disponible"] is True
    assert (v["actual"], v["anterior"]) == (3, 2)
    assert v["variacion"] == pytest.approx(0.5)


def test_sin_periodo_anterior_no_hay_porcentaje_sino_motivo(org_a):
    ahora = timezone.now()
    _propuesta(org_a)

    v = indicadores.indicadores_supervisor(
        org_a, desde=ahora - timedelta(days=7), hasta=ahora,
        ahora=ahora)["variaciones"]["propuestas"]

    #  0 -> 3 no es "+300%": es que antes no había nada. Se dice.
    assert v["disponible"] is False
    assert "anterior" in v["motivo"]


def test_los_hallazgos_vigentes_declaran_que_no_tienen_historico(org_a):
    """La detección es en vivo y no se persiste: no hay contra qué comparar."""
    v = indicadores.indicadores_supervisor(org_a)["variaciones"]["senales_vigentes"]

    assert v["disponible"] is False
    assert "no se persiste" in v["motivo"]
    assert "actual" in v


# =============================================================================
#  §3  Contexto operativo  --  las seis columnas que faltaban
# =============================================================================

def test_un_hallazgo_sobre_un_caso_trae_su_ticket_y_su_origen(org_a):
    caso = _caso(org_a, proveedor="wisphub", ticket="WH-91288")
    p = _propuesta(org_a, origen_id=str(caso.id))

    c = contexto_de(p)

    assert c["caso"]["ticket_externo"] == "WH-91288"
    assert c["caso"]["id_corto"] == str(caso.id)[:8]
    assert c["origen"] == WISPHUB
    #  Un caso no tiene zona en el CRM: None, no "" ni "Sin zona".
    assert c["zona"] is None


def test_un_caso_con_responsable_interno_se_marca_como_dexter_y_wisphub(org_a, gestor):
    caso = _caso(org_a, proveedor="wisphub", ticket="WH-2")
    caso.assigned_to.add(gestor[1])
    p = _propuesta(org_a, origen_id=str(caso.id))

    assert contexto_de(p)["origen"] == DEXTER_Y_WISPHUB


def test_un_caso_propio_del_crm_es_dexter(org_a):
    caso = _caso(org_a)
    assert contexto_de(_propuesta(org_a, origen_id=str(caso.id)))["origen"] == DEXTER


def test_un_hallazgo_sobre_una_orden_trae_tecnico_zona_y_plazo(org_a, gestor):
    orden = _orden(org_a)
    plan = ProgramacionSemanal.objects.create(
        org=org_a, semana_inicio=timezone.localdate(),
        estado=ProgramacionSemanal.BORRADOR)
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan, orden=orden,
        dia=timezone.localdate(), hora_inicio="09:00",
        zona="Soledad", estado=ProgramacionOrden.PLANIFICADA)
    p = _propuesta(org_a, origen_tipo="orden_trabajo", origen_id=str(orden.id),
                   tipo=PropuestaSupervisor.ORDEN_SIN_PROGRAMAR)

    c = contexto_de(p)

    assert c["orden"]["numero"] == orden.numero
    #  La zona sale de la LÍNEA DEL PLAN, que es donde vive de verdad.
    assert c["zona"] == "Soledad"
    #  El plazo lo calcula operaciones/sla.py, no este módulo.
    assert c["sla"] is not None and "estado" in c["sla"]


def test_una_orden_sin_plan_no_tiene_zona_y_eso_no_es_un_error(org_a):
    orden = _orden(org_a, numero=8101)
    c = contexto_de(_propuesta(org_a, origen_tipo="orden_trabajo",
                               origen_id=str(orden.id)))

    assert c["zona"] is None
    assert c["orden"]["numero"] == 8101


def test_un_origen_que_ya_no_existe_devuelve_contexto_vacio_sin_levantar(org_a):
    c = contexto_de(_propuesta(org_a, origen_id=str(uuid.uuid4())))

    assert c["caso"] is None and c["tecnico"] is None and c["sla"] is None


def test_un_origen_id_que_no_es_uuid_no_tumba_la_lista(org_a):
    c = contexto_de(_propuesta(org_a, origen_id="no-es-un-uuid"))
    assert c["caso"] is None


def test_un_tipo_de_origen_desconocido_no_rompe(org_a):
    c = contexto_de(_propuesta(org_a, origen_tipo="programacion"))
    assert c["tipo"] == "programacion" and c["caso"] is None


def test_el_contexto_no_expone_datos_personales_del_cliente(org_a):
    caso = _caso(org_a, proveedor="wisphub", ticket="WH-3")
    c = contexto_de(_propuesta(org_a, origen_id=str(caso.id)))

    plano = str(c).lower()
    for prohibido in ("telefono", "direccion", "cedula", "gps", "coordenada",
                      "password", "latitud"):
        assert prohibido not in plano


def test_la_tabla_llega_por_http_con_las_columnas_nuevas(org_a, cliente):
    caso = _caso(org_a, proveedor="wisphub", ticket="WH-91300")
    _propuesta(org_a, origen_id=str(caso.id))

    fila = cliente.get("/api/operaciones/propuestas/").json()["resultados"][0]

    assert fila["contexto"]["caso"]["ticket_externo"] == "WH-91300"
    assert fila["huella_condicion"] == "h-1"


# =============================================================================
#  §4  El feed de actividad
# =============================================================================

def test_el_feed_devuelve_lo_que_el_supervisor_registro(org_a, cliente):
    p = _propuesta(org_a)
    auditoria.registrar(org=org_a, actor=None, accion="CREATE",
                        entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=p.id,
                        nombre=p.accion_propuesta, descripcion="detectó algo")

    r = cliente.get(RUTA_ACTIVIDAD)

    assert r.status_code == 200
    fila = r.json()["resultados"][0]
    #  Sin usuario = lo hizo la IA, y se dice con todas las letras.
    assert fila["es_ia"] is True
    assert fila["quien"] == "Supervisor NOC IA"
    assert fila["detalle"] == "detectó algo"


def test_una_revision_humana_aparece_con_su_autor(org_a, cliente, gestor):
    p = _propuesta(org_a)
    auditoria.registrar(org=org_a, actor=gestor[1], accion="APPROVED",
                        entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=p.id,
                        nombre="ok", descripcion="aceptada")

    fila = cliente.get(RUTA_ACTIVIDAD).json()["resultados"][0]

    assert fila["es_ia"] is False
    assert fila["quien"] == gestor[0].email


def test_el_feed_no_mezcla_la_actividad_del_resto_del_crm(org_a, cliente):
    Activity.objects.create(org=org_a, user=None, action="CREATE",
                            entity_type="Account", entity_id=uuid.uuid4(),
                            entity_name="Una cuenta", description="ajena")
    p = _propuesta(org_a)
    auditoria.registrar(org=org_a, actor=None, accion="CREATE",
                        entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=p.id,
                        nombre="propia", descripcion="del supervisor")

    tipos = {f["entidad"] for f in cliente.get(RUTA_ACTIVIDAD).json()["resultados"]}

    assert tipos == {auditoria.ENTIDAD_PROPUESTA}


def test_una_organizacion_sin_actividad_recibe_lista_vacia(org_a, cliente):
    r = cliente.get(RUTA_ACTIVIDAD)

    assert r.status_code == 200
    assert r.json() == {"count": 0, "resultados": []}


def test_el_feed_no_muestra_la_actividad_de_otra_empresa(org_a, org_b, cliente):
    with rls_org(org_b):
        ajena = Activity.objects.create(
            org=org_b, user=None, action="CREATE",
            entity_type=auditoria.ENTIDAD_PROPUESTA, entity_id=uuid.uuid4(),
            entity_name="de B", description="ajena")

    r = cliente.get(RUTA_ACTIVIDAD)

    assert r.json()["count"] == 0
    assert str(ajena.id) not in r.content.decode()


def test_el_feed_respeta_el_limite(org_a, cliente):
    p = _propuesta(org_a)
    for i in range(5):
        auditoria.registrar(org=org_a, actor=None, accion="CREATE",
                            entidad=auditoria.ENTIDAD_PROPUESTA, entidad_id=p.id,
                            nombre=f"e{i}", descripcion=f"evento {i}")

    r = cliente.get(RUTA_ACTIVIDAD, {"limite": 2})

    assert len(r.json()["resultados"]) == 2
    assert r.json()["count"] == 5


# =============================================================================
#  §5  El mapa
# =============================================================================

def test_sin_ordenes_el_mapa_responde_200_y_dice_por_que_esta_vacio(org_a, cliente):
    """
    Un 404 se leería como "falta la ruta". Lo que falta es el DATO, y el motivo
    viaja para que la pantalla lo diga en vez de quedarse en blanco.
    """
    r = cliente.get(RUTA_UBICACIONES)

    assert r.status_code == 200
    d = r.json()
    assert d["puntos"] == []
    assert d["disponible"] is False
    assert "órdenes" in d["motivo"].lower()


def test_una_orden_con_coordenadas_aparece_en_el_mapa(org_a, cliente):
    """El dato ya existía en la orden: lo que faltaba era que alguien lo pidiera."""
    orden = _orden(org_a, numero=8300)
    OrdenTrabajo.objects.filter(id=orden.id).update(gps_lat=10.9, gps_lng=-74.8)

    d = cliente.get(RUTA_UBICACIONES).json()

    assert d["disponible"] is True
    punto = d["puntos"][0]
    assert (punto["lat"], punto["lng"]) == (10.9, -74.8)
    assert punto["etiqueta"] == "OT-8300"
    assert punto["programada"] is False


def test_el_punto_no_lleva_ni_un_dato_del_cliente(org_a, cliente):
    """
    En el mapa se pinta dónde hay TRABAJO, no dónde vive una persona. Las
    coordenadas del domicilio que guarda el proveedor son PII (RNF-01) y no
    entran por aquí.
    """
    orden = _orden(org_a, numero=8301)
    OrdenTrabajo.objects.filter(id=orden.id).update(gps_lat=10.9, gps_lng=-74.8)

    plano = cliente.get(RUTA_UBICACIONES).content.decode().lower()

    assert "cliente tablero" not in plano
    for prohibido in ("telefono", "direccion", "calle", "cedula"):
        assert prohibido not in plano


def test_las_ordenes_sin_coordenadas_se_cuentan_en_vez_de_desaparecer(org_a, cliente):
    _orden(org_a, numero=8302)
    con = _orden(org_a, numero=8303)
    OrdenTrabajo.objects.filter(id=con.id).update(gps_lat=10.9, gps_lng=-74.8)

    d = cliente.get(RUTA_UBICACIONES).json()

    assert len(d["puntos"]) == 1
    assert d["ordenes_sin_posicion"] == 1


def test_la_leyenda_del_mapa_cuenta_ordenes_reales(org_a, cliente):
    sin_plan = _orden(org_a, numero=8200)
    con_plan = _orden(org_a, numero=8201)
    plan = ProgramacionSemanal.objects.create(
        org=org_a, semana_inicio=timezone.localdate())
    ProgramacionOrden.objects.create(
        org=org_a, programacion=plan, orden=con_plan,
        dia=timezone.localdate(), hora_inicio="08:00",
        estado=ProgramacionOrden.PLANIFICADA)

    leyenda = cliente.get(RUTA_UBICACIONES).json()["leyenda"]

    assert leyenda["total_abiertas"] == 2
    assert leyenda["programados"] == 1
    assert leyenda["sin_programar"] == 1
    assert str(sin_plan.id)


def test_sin_ordenes_la_leyenda_es_cero_y_no_falla(org_a, cliente):
    leyenda = cliente.get(RUTA_UBICACIONES).json()["leyenda"]

    assert leyenda == {"criticos": 0, "en_ejecucion": 0, "programados": 0,
                       "sin_programar": 0, "total_abiertas": 0}


# =============================================================================
#  §6  Permisos, aislamiento y cero efectos
# =============================================================================

@pytest.mark.parametrize("ruta", [RUTA_ACTIVIDAD, RUTA_UBICACIONES])
def test_un_rol_sin_gestion_no_entra(org_a, ruta):
    u, p = _perfil(org_a, f"raso{ruta.count('/')}@tablero.test", rol="USER")

    assert _cliente(u, org_a, p).get(ruta).status_code == 403


@pytest.mark.parametrize("ruta", [RUTA_ACTIVIDAD, RUTA_UBICACIONES])
def test_ninguna_de_las_dos_rutas_escribe(org_a, cliente, ruta):
    _propuesta(org_a)
    antes = (Activity.objects.count(), PropuestaSupervisor.objects.count(),
             OrdenTrabajo.objects.count())

    assert cliente.get(ruta).status_code == 200

    assert (Activity.objects.count(), PropuestaSupervisor.objects.count(),
            OrdenTrabajo.objects.count()) == antes


@pytest.mark.parametrize("ruta", [RUTA_ACTIVIDAD, RUTA_UBICACIONES])
def test_ninguna_de_las_dos_acepta_escritura(org_a, cliente, ruta):
    assert cliente.post(ruta, {}, format="json").status_code == 405


# =============================================================================
#  §7  El SLA de la tabla es el del Supervisor, no uno propio
# =============================================================================

def test_los_estados_de_sla_son_los_del_modulo_que_usan_los_detectores(org_a):
    """
    Si la columna inventara sus propios estados, la tabla podría decir "a
    tiempo" de una orden que el detector acaba de marcar vencida.
    """
    orden = _orden(org_a, numero=8400)
    c = contexto_de(_propuesta(org_a, origen_tipo="orden_trabajo",
                               origen_id=str(orden.id)))

    assert c["sla"]["estado"] in (sla.VENCIDA, sla.VENCE_PRONTO, sla.A_TIEMPO,
                                  sla.SIN_PLAZO, sla.NO_APLICA,
                                  sla.DATOS_INSUFICIENTES)
    assert c["sla"]["fuente"] == "operaciones.sla"


def test_el_plazo_de_la_orden_coincide_con_el_que_calcula_el_detector(org_a):
    """El mismo veredicto, medido dos veces por los dos caminos."""
    orden = _orden(org_a, numero=8401)
    ahora = timezone.now()

    del_contexto = contexto_de(
        _propuesta(org_a, origen_tipo="orden_trabajo", origen_id=str(orden.id)),
        ahora=ahora)["sla"]["estado"]
    del_modulo = sla.plazo_de(orden, ahora=ahora)["estado"]

    assert del_contexto == del_modulo


def test_un_caso_vencido_se_dice_vencido_con_la_misma_palabra(org_a):
    caso = _caso(org_a)
    Case.objects.filter(id=caso.id).update(
        sla_resolution_hours=1, created_at=timezone.now() - timedelta(hours=10))
    caso.refresh_from_db()

    c = contexto_de(_propuesta(org_a, origen_id=str(caso.id)))

    assert c["sla"]["estado"] == sla.VENCIDA
    assert c["sla"]["minutos_atraso"] > 0


def test_un_caso_dentro_del_plazo_esta_a_tiempo(org_a):
    caso = _caso(org_a)
    Case.objects.filter(id=caso.id).update(sla_resolution_hours=72)
    caso.refresh_from_db()

    assert contexto_de(_propuesta(org_a, origen_id=str(caso.id)))["sla"]["estado"] == sla.A_TIEMPO


def test_el_umbral_de_riesgo_es_la_ventana_del_modulo_no_un_numero_propio(org_a):
    """
    'En riesgo' entra cuando falta menos del 20% del plazo (tope 24 h), que es
    la ventana que 'sla.ventana_de_aviso' aplica a las órdenes. Con un plazo de
    10 h, eso son 2 h: a 1 h del límite tiene que estar en riesgo.
    """
    caso = _caso(org_a)
    Case.objects.filter(id=caso.id).update(
        sla_resolution_hours=10, created_at=timezone.now() - timedelta(hours=9))
    caso.refresh_from_db()

    assert contexto_de(_propuesta(org_a, origen_id=str(caso.id)))["sla"]["estado"] == sla.VENCE_PRONTO


def test_un_caso_resuelto_no_dice_vencido_sino_que_no_aplica(org_a):
    """Decir "vencido" de algo cerrado describe el pasado como un pendiente."""
    caso = _caso(org_a)
    Case.objects.filter(id=caso.id).update(
        sla_resolution_hours=1, created_at=timezone.now() - timedelta(hours=10),
        resolved_at=timezone.now())
    caso.refresh_from_db()

    assert contexto_de(_propuesta(org_a, origen_id=str(caso.id)))["sla"]["estado"] == sla.NO_APLICA


def test_una_orden_sin_duracion_declarada_dice_sin_plazo(org_a):
    """
    SIN_PLAZO no es un error: el tipo de trabajo existe y no declara duración,
    así que nadie se comprometió a un tiempo y no hay plazo que medir. Es
    distinto de DATOS_INSUFICIENTES, que es "no se pudo leer".
    """
    orden = _orden(org_a, numero=8402)
    c = contexto_de(_propuesta(org_a, origen_tipo="orden_trabajo",
                               origen_id=str(orden.id)))

    assert c["sla"]["estado"] in (sla.SIN_PLAZO, sla.DATOS_INSUFICIENTES)
    #  Y cuando falta algo para poder calcularlo, se dice QUÉ falta.
    if c["sla"]["estado"] == sla.DATOS_INSUFICIENTES:
        assert c["sla"]["datos_faltantes"]
