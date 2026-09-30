# -*- coding: utf-8 -*-
"""
================================================================================
 M05-A  --  ciclo de vida persistente de una incidencia
================================================================================

LA REGLA QUE ESTA SUITE EXISTE PARA DEFENDER
--------------------------------------------
    DESBLOQUEAR UNA ACTIVIDAD NO RESUELVE UNA INCIDENCIA.

Son dos hechos distintos:

    "la actividad ya no esta bloqueada"   <- estado del trabajo
    "la causa operacional ya se atendio"  <- estado de la incidencia

La primera version de este modulo los confundia: derivaba el estado de la
incidencia del estado de la actividad, y daba por cerrada una causa que nadie
habia atendido. Las pruebas de aquella version se eliminaron; estas afirman lo
contrario, y varias existen solo para que ese error no pueda volver.

El estado vive en 'NovedadOperativa.estado' y solo cambia por las operaciones
explicitas de 'operaciones/novedades.py'.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from business_hours.models import BusinessCalendar
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from common.models import Activity, Profile, User
from operaciones import actividades as m02
from operaciones import asistentes as A
from operaciones import auditoria, habilidades, incidencias, novedades, supervisor
from operaciones.capacidad import CLAVE_DURACION
from operaciones.models import ActividadOperativa, NovedadOperativa
from operaciones.models import PropuestaSupervisor as P

N = NovedadOperativa
_n = [9950]
_c = [0]
MARTES_9 = datetime(2026, 9, 15, 9, 0, tzinfo=ZoneInfo("UTC"))


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"v{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _calendario(org):
    cal = BusinessCalendar.objects.create(org=org, name="Default",
                                          timezone="UTC", is_default=True)
    for d in ("monday", "tuesday", "wednesday", "thursday", "friday",
              "saturday", "sunday"):
        setattr(cal, f"{d}_open", time(8, 0))
        setattr(cal, f"{d}_close", time(16, 0))
    cal.save()
    return cal


def _orden(org, duracion=120):
    _n[0] += 1
    wt = WorkType.objects.create(org=org, codigo=f"v_{_n[0]}", nombre="v")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [], CLAVE_DURACION: duracion})
    return OrdenTrabajo.objects.create(
        org=org, numero=_n[0], tipo_trabajo_version=v,
        cliente_nombre=f"C{_n[0]}", cliente_direccion="Calle 1",
        estado_operativo=OrdenTrabajo.ASIGNADA)


# ====================================== 1-5. el lifecycle existe y es persistente
@pytest.mark.django_db
def test_1_2_estado_e_impacto_son_columnas(org_a, actor):
    """Se leen del modelo real, no de un calculo."""
    campos = {f.name for f in N._meta.get_fields()}
    for c in ("estado", "impacto", "resuelta_en", "resolucion", "resuelta_por"):
        assert c in campos, f"falta la columna '{c}'"

    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO,
                        descripcion="sin ONT", impacto=N.ALTO)
    n.refresh_from_db()
    assert n.estado == N.ABIERTA
    assert n.impacto == N.ALTO
    #  y sobrevive a releer la fila: esta en la base, no en memoria
    assert N.objects.get(pk=n.pk).estado == N.ABIERTA


@pytest.mark.django_db
def test_3_4_resuelta_en_y_resolucion_son_nullables_al_abrir(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.FALTA_MATERIAL)
    assert n.resuelta_en is None
    assert n.resolucion == ""
    assert n.resuelta_por_id is None
    assert n.impacto == "", "no se inventa un impacto que nadie declaro"


@pytest.mark.django_db
def test_5_el_responsable_de_resolucion_es_un_profile_existente(org_a, actor):
    """Se reutiliza Profile; no hay entidad nueva de responsable."""
    campo = N._meta.get_field("resuelta_por")
    assert campo.related_model is Profile
    assert campo.null is True

    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.resolver(n, actor=actor, resolucion="llego el material")
    assert n.resuelta_por_id == actor.id


# ====================================== 6-8. transiciones válidas
@pytest.mark.django_db
def test_6_abierta_a_en_gestion(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.iniciar_gestion(n, actor=actor, motivo="lo toma bodega")
    assert n.estado == N.EN_GESTION
    assert n.resuelta_en is None, "iniciar gestion no resuelve"


@pytest.mark.django_db
def test_7_abierta_a_resuelta(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.resolver(n, actor=actor, resolucion="el cliente autorizo")
    assert n.estado == N.RESUELTA


@pytest.mark.django_db
def test_8_en_gestion_a_resuelta(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.iniciar_gestion(n, actor=actor)
    n = novedades.resolver(n, actor=actor, resolucion="se resolvio en bodega")
    assert n.estado == N.RESUELTA


# ====================================== 9-12. transiciones prohibidas
@pytest.mark.django_db
@pytest.mark.parametrize("resolucion", ["", "   ", "\n\t"])
def test_9_10_no_se_resuelve_sin_explicacion(org_a, actor, resolucion):
    """
    Sin 'resolucion' no se puede distinguir una causa atendida de una que
    alguien marco para sacarla de la lista.
    """
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    with pytest.raises(novedades.ErrorIncidencia) as e:
        novedades.resolver(n, actor=actor, resolucion=resolucion)
    assert "cómo se resolvió" in str(e.value)

    n.refresh_from_db()
    assert n.estado == N.ABIERTA
    assert n.resuelta_en is None, "quedo un timestamp de una resolucion que fallo"
    assert n.resolucion == ""


@pytest.mark.django_db
def test_11_no_se_inicia_gestion_desde_resuelta(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.resolver(n, actor=actor, resolucion="listo")
    with pytest.raises(novedades.ErrorIncidencia) as e:
        novedades.iniciar_gestion(n, actor=actor)
    assert "no puede pasar" in str(e.value)
    n.refresh_from_db()
    assert n.estado == N.RESUELTA


@pytest.mark.django_db
def test_12_una_resuelta_no_se_modifica_en_silencio(org_a, actor):
    """Tampoco se puede volver a resolver: no hay reapertura en este bloque."""
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.resolver(n, actor=actor, resolucion="primera")
    foto = {"estado": n.estado, "resuelta_en": n.resuelta_en,
            "resolucion": n.resolucion, "resuelta_por": n.resuelta_por_id}

    with pytest.raises(novedades.ErrorIncidencia):
        novedades.resolver(n, actor=actor, resolucion="segunda")

    n.refresh_from_db()
    assert n.resolucion == foto["resolucion"] == "primera"
    assert n.resuelta_en == foto["resuelta_en"]
    assert n.resuelta_por_id == foto["resuelta_por"]


# ====================================== 13-15. LA REGLA CRÍTICA
@pytest.mark.django_db
@pytest.mark.parametrize("estado_inicial", [N.ABIERTA, N.EN_GESTION])
def test_13_14_15_desbloquear_una_actividad_no_resuelve_la_incidencia(
        org_a, actor, estado_inicial):
    """
    EL CASO QUE MOTIVO LA CORRECCION.

    Un tecnico puede desbloquear para avanzar por otra via mientras la causa
    sigue sin atenderse. Si el sistema dedujera la resolucion del desbloqueo,
    daria por cerrada una causa que nadie toco.

    Recorre los dos estados vivos: ni ABIERTA ni EN_GESTION deben moverse.
    """
    a = m02.crear(org=org_a, actor=actor, titulo="con bloqueo")
    m02.bloquear(a, actor=actor, motivo="falta material en bodega")
    a.refresh_from_db()

    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO,
                        actividad=a, descripcion="no hay ONT", impacto=N.ALTO)
    if estado_inicial == N.EN_GESTION:
        n = novedades.iniciar_gestion(n, actor=actor)

    antes = N.objects.get(pk=n.pk)
    foto = (antes.estado, antes.resuelta_en, antes.resolucion,
            antes.resuelta_por_id, antes.updated_at)

    #  --- se desbloquea la actividad ---
    m02.desbloquear(a, actor=actor, motivo="seguimos por otra via")
    a.refresh_from_db()
    assert a.estado_operativo != ActividadOperativa.BLOQUEADA

    despues = N.objects.get(pk=n.pk)
    assert despues.estado == estado_inicial, "el desbloqueo movio el estado"
    assert despues.resuelta_en is None
    assert despues.resolucion == ""
    assert despues.resuelta_por_id is None
    #  y la fila no se toco en absoluto
    assert (despues.estado, despues.resuelta_en, despues.resolucion,
            despues.resuelta_por_id, despues.updated_at) == foto

    #  el analisis PUEDE observar que la actividad ya no esta bloqueada, pero
    #  eso viaja en 'contexto', nunca como el estado de la incidencia
    f = incidencias.ficha(despues)
    assert f["estado"] == estado_inicial
    assert f["sin_resolver"] is True
    assert f["contexto"]["observacion"] == incidencias.CONTEXTO_CESO
    assert "no significa que la causa se haya atendido" in f["contexto"]["por_que"]


@pytest.mark.django_db
def test_13b_tampoco_la_resuelve_completar_la_actividad(org_a, actor):
    """Mismo principio, otra puerta: cerrar el trabajo no cierra la causa."""
    a = m02.crear(org=org_a, actor=actor, titulo="x")
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, actividad=a)
    m02.completar(a, actor=actor)
    n.refresh_from_db()
    assert n.estado == N.ABIERTA
    assert n.resuelta_en is None


# ====================================== 16-19. resolver explícitamente
@pytest.mark.django_db
def test_16_17_18_resolver_registra_fecha_responsable_y_conserva_la_creacion(
        org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.FALTA_MATERIAL)
    creada = N.objects.get(pk=n.pk).created_at
    momento = MARTES_9 + timedelta(days=2)

    n = novedades.resolver(n, actor=actor,
                           resolucion="llegaron 4 ONT del proveedor",
                           ahora=momento)
    assert n.resuelta_en == momento
    assert n.resuelta_por_id == actor.id
    assert n.resolucion == "llegaron 4 ONT del proveedor"
    assert N.objects.get(pk=n.pk).created_at == creada, "se movio la fecha original"


@pytest.mark.django_db
def test_19_resolver_deja_auditoria_en_el_mecanismo_existente(org_a, actor):
    """Se escribe en common.Activity, la bitacora de todo el CRM."""
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    antes = Activity.objects.filter(
        org=org_a, entity_type=auditoria.ENTIDAD_NOVEDAD).count()

    novedades.resolver(n, actor=actor, resolucion="el cliente autorizo")

    filas = Activity.objects.filter(org=org_a,
                                    entity_type=auditoria.ENTIDAD_NOVEDAD,
                                    entity_id=n.id).order_by("created_at")
    assert filas.count() == antes + 1
    ultima = filas.last()
    assert ultima.metadata.get("estado_anterior") == N.ABIERTA
    assert ultima.metadata.get("estado_nuevo") == N.RESUELTA
    assert "el cliente autorizo" in ultima.metadata.get("motivo", "")
    assert ultima.user_id == actor.user_id or ultima.user_id is not None


@pytest.mark.django_db
def test_19b_el_entity_type_esta_declarado(org_a, actor):
    """
    Un entity_type sin declarar se guarda igual y diverge en silencio -- es la
    leccion que el propio common/models.py documenta.
    """
    declarados = {v for v, _ in Activity.ENTITY_TYPE_CHOICES}
    assert auditoria.ENTIDAD_NOVEDAD in declarados


# ====================================== 20-23. detector
@pytest.mark.django_db
@pytest.mark.parametrize("estado", [N.ABIERTA, N.EN_GESTION])
def test_20_21_el_detector_encuentra_las_vivas(org_a, actor, estado):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, impacto=N.ALTO)
    if estado == N.EN_GESTION:
        n = novedades.iniciar_gestion(n, actor=actor)

    s = [x for x in supervisor.detectar(org_a, MARTES_9)
         if x.tipo == P.INCIDENCIA_SIN_RESOLVER and x.origen_id == str(n.id)]
    assert s, f"el detector no vio una incidencia {estado}"
    assert s[0].datos["estado"] == estado
    assert s[0].huella == f"estado:{estado}"


@pytest.mark.django_db
def test_22_el_detector_ignora_las_resueltas(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    novedades.resolver(n, actor=actor, resolucion="listo")
    s = [x for x in supervisor.detectar(org_a, MARTES_9)
         if x.tipo == P.INCIDENCIA_SIN_RESOLVER and x.origen_id == str(n.id)]
    assert not s, "propuso sobre una incidencia ya resuelta"


@pytest.mark.django_db
def test_22b_la_evidencia_explica_la_incidencia(org_a, actor):
    a = m02.crear(org=org_a, actor=actor, titulo="la actividad")
    o = _orden(org_a)
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO,
                        descripcion="puerta cerrada", impacto=N.CRITICO,
                        orden=o, actividad=a)
    s = [x for x in supervisor.detectar(org_a, MARTES_9)
         if x.origen_id == str(n.id)][0]
    texto = " ".join(x["dato"] for x in s.evidencia)

    assert "Bloqueo" in texto and "Abierta" in texto      # tipo y estado
    assert "puerta cerrada" in texto                      # descripcion
    assert "Crítico" in texto                             # impacto
    assert "registrada el" in texto and "hace" in texto   # fecha y antiguedad
    assert f"#{o.numero}" in texto                        # OT relacionada
    assert "la actividad" in texto                        # actividad relacionada
    assert "registrada por" in texto                      # registrador
    assert str(n.id) in str(s.evidencia)                  # ID


@pytest.mark.django_db
def test_23_deduplicacion_estable(org_a, actor):
    """
    La huella lleva el ESTADO, no la antiguedad: pasar las horas no crea una
    propuesta nueva. Cambiar de ABIERTA a EN_GESTION si es otra situacion.
    """
    _calendario(org_a)
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)

    A.asistir(org_a, A.PROGRAMACION, MARTES_9)
    n1 = P.objects.filter(org=org_a, tipo_senal=P.INCIDENCIA_SIN_RESOLVER).count()
    assert n1 == 1

    A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(days=3))
    assert P.objects.filter(org=org_a,
                            tipo_senal=P.INCIDENCIA_SIN_RESOLVER).count() == n1

    novedades.iniciar_gestion(n, actor=actor)
    A.asistir(org_a, A.PROGRAMACION, MARTES_9 + timedelta(days=3))
    assert P.objects.filter(org=org_a,
                            tipo_senal=P.INCIDENCIA_SIN_RESOLVER).count() == n1 + 1


# ====================================== 24-26. A-1 / A-2
@pytest.mark.django_db
def test_24_a1_muestra_el_lifecycle(org_a, actor):
    _calendario(org_a)
    o = _orden(org_a)
    abierta = novedades.abrir(org=org_a, actor=actor, tipo=N.FALTA_MATERIAL,
                              orden=o, impacto=N.ALTO)
    resuelta = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, orden=o)
    novedades.resolver(resuelta, actor=actor, resolucion="ya esta")
    novedades.iniciar_gestion(
        novedades.abrir(org=org_a, actor=actor, tipo=N.DEPENDENCIA, orden=o),
        actor=actor)

    salida = A.asistir(org_a, A.PROGRAMACION, MARTES_9, registrar=False)
    filas = [r for r in salida["recomendaciones"]
             if r["origen_tipo"] == "orden_trabajo" and r["origen_id"] == str(o.id)]
    assert filas
    nov = filas[0]["contexto"]["novedades"]
    estados = {x["estado"] for x in nov}
    assert {N.ABIERTA, N.EN_GESTION, N.RESUELTA} <= estados

    r = salida["resumen"]["incidencias"]
    assert r["abiertas"] >= 1 and r["en_gestion"] >= 1 and r["resueltas"] >= 1
    assert r["sin_resolver"] >= 2
    assert r["por_impacto"].get(N.ALTO) >= 1
    assert r["sin_impacto_declarado"] >= 1
    #  la ficha de la abierta trae lo que pide el bloque
    f = [x for x in nov if x["id"] == str(abierta.id)][0]
    assert f["impacto"] == N.ALTO and f["antiguedad_horas"] is not None
    assert f["resolucion"] is None and f["resuelta_en"] is None


@pytest.mark.django_db
def test_25_a2_muestra_la_incidencia_de_la_actividad(org_a, actor):
    _calendario(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="bloqueada",
                  vence_en=MARTES_9 - timedelta(hours=2))
    m02.bloquear(a, actor=actor, motivo="el cliente no autoriza")
    a.refresh_from_db()
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, actividad=a,
                        impacto=N.MEDIO, descripcion="puerta cerrada")
    novedades.iniciar_gestion(n, actor=actor)

    salida = A.asistir(org_a, A.COMPROMISOS, MARTES_9 + timedelta(hours=5),
                       registrar=False)
    filas = [r for r in salida["recomendaciones"] if r["origen_id"] == str(a.id)]
    assert filas
    inc = filas[0]["incidencias"]
    assert inc
    f = inc[0]
    assert f["estado"] == N.EN_GESTION
    assert f["estado_etiqueta"] == "En gestión"
    assert f["impacto"] == N.MEDIO
    assert f["antiguedad_horas"] is not None
    assert f["resolucion"] is None
    assert f["sin_resolver"] is True


@pytest.mark.django_db
def test_26_sin_vinculo_no_se_inventa_incidencia(org_a, actor):
    _calendario(org_a)
    a = m02.crear(org=org_a, actor=actor, titulo="suelta",
                  vence_en=MARTES_9 - timedelta(hours=2))
    salida = A.asistir(org_a, A.COMPROMISOS, MARTES_9, registrar=False)
    filas = [r for r in salida["recomendaciones"] if r["origen_id"] == str(a.id)]
    assert filas
    assert filas[0]["incidencias"] == []


# ====================================== 27-28. invariantes
@pytest.mark.django_db
def test_27_h05_sigue_bloqueada_y_las_fichas_previas_no_cambiaron():
    assert habilidades.HABILIDADES["H-05"].estado == habilidades.BLOQUEADA
    assert habilidades.HABILIDADES["H-13"].estado == habilidades.VIGENTE
    assert habilidades.POR_SENAL[P.INCIDENCIA_SIN_RESOLVER] == "H-13"
    huellas = {i: habilidades.HABILIDADES[i].huella() for i in habilidades.IDS}
    assert len(set(huellas.values())) == len(huellas), "hay huellas repetidas"


@pytest.mark.django_db
def test_28_no_hay_ejecucion_externa_ni_modelos_nuevos(org_a, actor):
    import ast
    import inspect
    from django.apps import apps

    modelos = {m.__name__ for m in apps.get_app_config("operaciones").get_models()}
    assert modelos == {"ActividadOperativa", "DisponibilidadTecnico",
                       "ProgramacionSemanal", "ProgramacionOrden",
                       "NovedadOperativa", "PropuestaSupervisor"}, modelos

    #  el modulo de LECTURA no escribe
    nombres = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(incidencias))):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
    assert nombres.isdisjoint({"save", "delete", "create", "resolver",
                               "iniciar_gestion", "requests", "httpx",
                               "celery", "shared_task"})

    #  y M09 no resuelve, no cambia estado, no desbloquea
    nombres_sup = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(supervisor._incidencias_sin_resolver))):
        if isinstance(nodo, ast.Attribute):
            nombres_sup.add(nodo.attr)
    assert nombres_sup.isdisjoint({"resolver", "iniciar_gestion", "desbloquear",
                                   "save", "delete", "escalar"})

    #  las propuestas que crea siguen pidiendo revision humana
    _calendario(org_a)
    novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    A.asistir(org_a, A.PROGRAMACION, MARTES_9)
    for p in P.objects.filter(org=org_a, tipo_senal=P.INCIDENCIA_SIN_RESOLVER):
        assert p.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR
        assert p.estado == P.PROPUESTA
        assert p.revisado_por_id is None


# ====================================== límites
@pytest.mark.django_db
def test_no_determinable_nunca_sustituye_al_estado(org_a, actor):
    """
    'NO_DETERMINABLE' vive solo en el contexto observable. El estado siempre
    sale de la columna, tambien cuando no hay nada que observar.
    """
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.FALTA_MATERIAL)
    f = incidencias.ficha(n)
    assert f["contexto"]["observacion"] == incidencias.NO_DETERMINABLE
    assert f["estado"] == N.ABIERTA
    assert f["sin_resolver"] is True
    #  y tras resolverla, el contexto sigue sin poder observar nada pero el
    #  estado SI cambia
    novedades.resolver(n, actor=actor, resolucion="llego")
    n.refresh_from_db()
    f2 = incidencias.ficha(n)
    assert f2["contexto"]["observacion"] == incidencias.NO_DETERMINABLE
    assert f2["estado"] == N.RESUELTA
    assert f2["sin_resolver"] is False


@pytest.mark.django_db
def test_un_impacto_invalido_se_rechaza(org_a, actor):
    with pytest.raises(novedades.ErrorIncidencia):
        novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, impacto="altisimo")
    with pytest.raises(novedades.ErrorIncidencia):
        novedades.abrir(org=org_a, actor=actor, tipo="lo_que_sea")


@pytest.mark.django_db
def test_declarar_impacto_no_mueve_el_estado(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n = novedades.declarar_impacto(n, actor=actor, impacto=N.CRITICO)
    assert n.impacto == N.CRITICO
    assert n.estado == N.ABIERTA


@pytest.mark.django_db
def test_los_datos_faltantes_se_nombran(org_a, actor):
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.DEMORA_SIN_CAUSA)
    campos = {f["campo"] for f in incidencias.ficha(n)["datos_faltantes"]}
    assert "impacto" in campos
    assert "descripcion" in campos
    assert "orden/actividad" in campos


@pytest.mark.django_db
def test_el_aislamiento_por_organizacion_se_mantiene(org_a, org_b, actor):
    actor_b = _persona(org_b, "OPERACIONES")[1]
    novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO)
    n_b = novedades.abrir(org=org_b, actor=actor_b, tipo=N.BLOQUEO)

    ids = {s.origen_id for s in supervisor.detectar(org_a, MARTES_9)}
    assert str(n_b.id) not in ids
