# -*- coding: utf-8 -*-
"""
================================================================================
 M05-B  --  escalamiento con destinatario
================================================================================

'escalada' ya era un estado. Lo que faltaba es a QUIEN, CUANDO y CON QUE NIVEL.
Sin eso, el estado decia que alguien pidio ayuda y no decia a quien, asi que
nadie podia saber si la habia pedido bien.

LO QUE ESTA SUITE DEFIENDE
--------------------------
  * no hay destinatario por defecto: si no lo pones, se rechaza;
  * M09 NO elige destinatario -- dice que falta y se calla el nombre;
  * el nivel es RUTA de gestion, no gravedad ni culpa;
  * escalar una actividad no resuelve su incidencia, y al reves tampoco;
  * no se escala a alguien de otra empresa.

REESCALAMIENTO
--------------
No se inventa: 'TRANSICIONES[ESCALADA]' nunca se incluyo a si misma, asi que el
proyecto ya rechazaba reescalar de golpe. Se respeta y se prueba.
================================================================================
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from common.models import Activity, Profile, User
from operaciones import actividades as act
from operaciones import asistentes as A
from operaciones import auditoria, habilidades, novedades, supervisor
from operaciones.models import ActividadOperativa as ACT
from operaciones.models import NovedadOperativa as N
from operaciones.models import PropuestaSupervisor as P

_c = [0]


def _persona(org, role="USER"):
    _c[0] += 1
    u = User.objects.create_user(email=f"e{_c[0]}@x.test", password="x12345678")
    return u, Profile.objects.create(user=u, org=org, role=role, is_active=True)


@pytest.fixture
def actor(org_a):
    return _persona(org_a, "OPERACIONES")[1]


@pytest.fixture
def jefe(org_a):
    return _persona(org_a, "OPERACIONES")[1]


def _crear(org, actor, **kw):
    return act.crear(org=org, actor=actor, titulo=kw.pop("titulo", "una tarea"), **kw)


# ====================================== 1-5. modelo
@pytest.mark.django_db
def test_1_los_tres_campos_existen():
    campos = {f.name for f in ACT._meta.get_fields()}
    for c in ("escalado_a", "escalado_en", "nivel_escalamiento"):
        assert c in campos, f"falta '{c}'"
    assert ACT._meta.get_field("escalado_a").related_model is Profile


@pytest.mark.django_db
def test_2_3_4_los_campos_son_nullables_para_el_historico(org_a, actor):
    """
    Una actividad que ya existia no gana destinatario, fecha ni nivel
    retroactivos: no se inventa a quien se escalo algo antes de que el sistema
    lo registrara.
    """
    a = _crear(org_a, actor)
    assert a.escalado_a_id is None
    assert a.escalado_en is None
    assert a.nivel_escalamiento == ""
    assert ACT._meta.get_field("escalado_a").null is True
    assert ACT._meta.get_field("escalado_en").null is True


@pytest.mark.django_db
def test_5_el_nivel_no_es_el_impacto(org_a, actor, jefe):
    """
    Dos escalas distintas a proposito: el nivel describe la RUTA de gestion, el
    impacto describe la afectacion operacional. Una incidencia de impacto bajo
    puede necesitar nivel 3, y una critica resolverse en nivel 1.
    """
    niveles = set(dict(ACT.NIVELES_ESCALAMIENTO))
    impactos = set(dict(N.IMPACTOS))
    assert niveles.isdisjoint(impactos), "las dos escalas comparten valores"
    assert niveles == {"nivel_1", "nivel_2", "nivel_3"}


# ====================================== 6-16. escalar
@pytest.mark.django_db
def test_6_10_11_12_15_escalar_registra_todo(org_a, actor, jefe):
    antes = timezone.now()
    a = _crear(org_a, actor)
    a = act.escalar(a, actor=actor, motivo="supera lo que puedo autorizar",
                    escalado_a=jefe, nivel=ACT.NIVEL_2)
    a.refresh_from_db()

    assert a.estado_operativo == ACT.ESCALADA          # 15
    assert a.escalado_a_id == jefe.id                  # 11
    assert a.nivel_escalamiento == ACT.NIVEL_2         # 12
    assert a.escalado_en is not None                   # 10
    assert antes <= a.escalado_en <= timezone.now()


@pytest.mark.django_db
@pytest.mark.parametrize("kw,fragmento", [
    ({"motivo": ""}, "necesita su motivo"),
    ({"escalado_a": None}, "necesita destinatario"),
    ({"nivel": "nivel_9"}, "no es un nivel"),
    ({"nivel": ""}, "no es un nivel"),
])
def test_7_8_9_17_18_19_los_tres_datos_son_obligatorios(
        org_a, actor, jefe, kw, fragmento):
    """Falta uno de los tres -> rechazo, y la actividad no se mueve."""
    a = _crear(org_a, actor)
    base = {"motivo": "hace falta ayuda", "escalado_a": jefe, "nivel": ACT.NIVEL_1}
    base.update(kw)

    with pytest.raises(act.ErrorActividad) as e:
        act.escalar(a, actor=actor, **base)
    assert fragmento in str(e.value)

    a.refresh_from_db()
    assert a.estado_operativo != ACT.ESCALADA, "cambio de estado pese al rechazo"
    assert a.escalado_a_id is None
    assert a.escalado_en is None
    assert a.nivel_escalamiento == ""


@pytest.mark.django_db
def test_13_registra_auditoria_con_destinatario_y_nivel(org_a, actor, jefe):
    a = _crear(org_a, actor)
    act.escalar(a, actor=actor, motivo="no alcanzo el nivel 1",
                escalado_a=jefe, nivel=ACT.NIVEL_3)

    filas = Activity.objects.filter(org=org_a, entity_type=auditoria.ENTIDAD_ACTIVIDAD,
                                    entity_id=a.id, action="ESCALATED")
    assert filas.count() == 1
    m = filas.first().metadata
    assert m.get("estado_nuevo") == ACT.ESCALADA
    assert m.get("escalado_a") == str(jefe.id)
    assert m.get("nivel_escalamiento") == ACT.NIVEL_3
    assert "no alcanzo el nivel 1" in m.get("motivo", "")
    assert m.get("escalado_en")


@pytest.mark.django_db
def test_14_es_atomico(org_a, actor, jefe):
    """
    Si algo falla, no queda un estado 'escalada' a medias. Se prueba con el
    rechazo de tenant, que ocurre DESPUES de bloquear la fila.
    """
    _, ajeno = _persona(org_a)
    a = _crear(org_a, actor)
    ACT.objects.filter(pk=a.pk).update(estado_operativo=ACT.EN_GESTION)

    from common.models import Org
    otra = Org.objects.create(name="Otra empresa")
    _, de_otra = _persona(otra)

    with pytest.raises(act.ErrorActividad):
        act.escalar(a, actor=actor, motivo="x", escalado_a=de_otra,
                    nivel=ACT.NIVEL_1)

    a.refresh_from_db()
    assert a.estado_operativo == ACT.EN_GESTION
    assert a.escalado_a_id is None
    assert a.escalado_en is None
    assert a.nivel_escalamiento == ""


@pytest.mark.django_db
def test_16_no_destruye_el_estado_previo(org_a, actor, jefe):
    """Escalar desde bloqueada conserva el motivo del bloqueo."""
    a = _crear(org_a, actor)
    act.bloquear(a, actor=actor, motivo="falta material")
    a.refresh_from_db()

    a = act.escalar(a, actor=actor, motivo="bodega no responde",
                    escalado_a=jefe, nivel=ACT.NIVEL_2)
    a.refresh_from_db()
    assert a.estado_operativo == ACT.ESCALADA
    assert a.motivo_bloqueo == "falta material", "se perdio la causa del bloqueo"
    assert a.titulo and a.created_at


# ====================================== 20-22. tenant y reescalamiento
@pytest.mark.django_db
def test_20_no_se_escala_a_otra_organizacion(org_a, org_b, actor):
    """El trabajo de un cliente no se le pasa al personal de otro."""
    _, de_b = _persona(org_b)
    a = _crear(org_a, actor)
    with pytest.raises(act.ErrorActividad) as e:
        act.escalar(a, actor=actor, motivo="ayuda", escalado_a=de_b,
                    nivel=ACT.NIVEL_1)
    assert "otra organización" in str(e.value)
    a.refresh_from_db()
    assert a.escalado_a_id is None


@pytest.mark.django_db
def test_21_reescalar_se_rechaza_porque_el_proyecto_ya_lo_rechazaba(
        org_a, actor, jefe):
    """
    NO es una regla nueva: 'TRANSICIONES[ESCALADA]' nunca se incluyo a si
    misma. Se respeta tal cual, y lo importante es que el rechazo NO pisa los
    datos del primer escalamiento.
    """
    assert ACT.ESCALADA not in act.TRANSICIONES[ACT.ESCALADA]

    a = _crear(org_a, actor)
    a = act.escalar(a, actor=actor, motivo="primera", escalado_a=jefe,
                    nivel=ACT.NIVEL_1)
    primero = (a.escalado_a_id, a.escalado_en, a.nivel_escalamiento)

    _, otro = _persona(org_a)
    with pytest.raises(act.TransicionInvalida):
        act.escalar(a, actor=actor, motivo="segunda", escalado_a=otro,
                    nivel=ACT.NIVEL_3)

    a.refresh_from_db()
    assert (a.escalado_a_id, a.escalado_en, a.nivel_escalamiento) == primero, (
        "el reescalamiento rechazado piso la trazabilidad del primero")


@pytest.mark.django_db
def test_21b_el_camino_explicito_si_existe_y_deja_rastro(org_a, actor, jefe):
    """
    Para llevarla a otra instancia hay que devolverla a gestion primero. Ese
    camino queda escrito paso a paso en la auditoria, que es la diferencia con
    sobrescribir en silencio.
    """
    _, otro = _persona(org_a)
    a = _crear(org_a, actor)
    a = act.escalar(a, actor=actor, motivo="primera", escalado_a=jefe,
                    nivel=ACT.NIVEL_1)
    a = act.iniciar_gestion(a, actor=actor, motivo="vuelve a operaciones")
    a = act.escalar(a, actor=actor, motivo="ahora si, nivel 3",
                    escalado_a=otro, nivel=ACT.NIVEL_3)
    a.refresh_from_db()

    assert a.escalado_a_id == otro.id
    assert a.nivel_escalamiento == ACT.NIVEL_3
    #  los DOS escalamientos constan
    escalamientos = Activity.objects.filter(
        org=org_a, entity_id=a.id, action="ESCALATED").order_by("created_at")
    assert escalamientos.count() == 2
    assert escalamientos.first().metadata["escalado_a"] == str(jefe.id)
    assert escalamientos.last().metadata["escalado_a"] == str(otro.id)


@pytest.mark.django_db
def test_22_no_hay_escalamiento_silencioso(org_a, actor):
    """
    Ninguna otra operacion de M02 deja la actividad en 'escalada'. Se recorren
    las que cambian estado.
    """
    for mover in (lambda a: act.iniciar_gestion(a, actor=actor),
                  lambda a: act.poner_en_espera(a, actor=actor),
                  lambda a: act.bloquear(a, actor=actor, motivo="x"),
                  lambda a: act.completar(a, actor=actor)):
        a = _crear(org_a, actor)
        mover(a)
        a.refresh_from_db()
        assert a.estado_operativo != ACT.ESCALADA
        assert a.escalado_a_id is None and a.nivel_escalamiento == ""


# ====================================== 23-25. semántica
@pytest.mark.django_db
def test_23_escalar_una_actividad_no_resuelve_su_incidencia(org_a, actor, jefe):
    a = _crear(org_a, actor)
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, actividad=a,
                        descripcion="no hay material")
    antes = N.objects.get(pk=n.pk).updated_at

    act.escalar(a, actor=actor, motivo="bodega no responde", escalado_a=jefe,
                nivel=ACT.NIVEL_2)

    despues = N.objects.get(pk=n.pk)
    assert despues.estado == N.ABIERTA
    assert despues.resuelta_en is None
    assert despues.resolucion == ""
    assert despues.updated_at == antes, "escalar toco la incidencia"


@pytest.mark.django_db
def test_24_resolver_una_incidencia_no_escala_ni_desescala(org_a, actor, jefe):
    a = _crear(org_a, actor)
    a = act.escalar(a, actor=actor, motivo="ayuda", escalado_a=jefe,
                    nivel=ACT.NIVEL_1)
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.BLOQUEO, actividad=a)

    novedades.resolver(n, actor=actor, resolucion="llego el material")

    a.refresh_from_db()
    assert a.estado_operativo == ACT.ESCALADA, "resolver desescalo la actividad"
    assert a.escalado_a_id == jefe.id
    assert a.nivel_escalamiento == ACT.NIVEL_1


@pytest.mark.django_db
def test_25_los_dos_lifecycle_conviven_sin_mezclarse(org_a, actor, jefe):
    a = _crear(org_a, actor)
    a = act.escalar(a, actor=actor, motivo="ayuda", escalado_a=jefe,
                    nivel=ACT.NIVEL_2)
    n = novedades.abrir(org=org_a, actor=actor, tipo=N.DEPENDENCIA, actividad=a)
    novedades.iniciar_gestion(n, actor=actor)

    a.refresh_from_db()
    n.refresh_from_db()
    #  cuatro valores de tres ejes distintos, cada uno donde corresponde
    assert a.estado_operativo == ACT.ESCALADA        # actividad
    assert a.nivel_escalamiento == ACT.NIVEL_2       # ruta de escalamiento
    assert n.estado == N.EN_GESTION                  # incidencia
    assert n.impacto == ""                           # afectacion sin declarar


# ====================================== 26-30. M09
@pytest.mark.django_db
def test_26_29_detecta_la_falta_de_destinatario(org_a, actor):
    """
    Una actividad escalada antes de M05-B no tiene destinatario. Se simula
    poniendo el estado directo, que es como quedaron las historicas.
    """
    a = _crear(org_a, actor)
    ACT.objects.filter(pk=a.pk).update(estado_operativo=ACT.ESCALADA)

    s = [x for x in supervisor.detectar(org_a)
         if x.tipo == P.ESCALAMIENTO_SIN_DESTINATARIO and x.origen_id == str(a.id)]
    assert s, "no detecto el escalamiento sin destinatario"
    assert set(s[0].datos["faltan"]) == {"destinatario", "nivel"}

    texto = " ".join(x["dato"] for x in s[0].evidencia)
    assert "escalada" in texto
    assert "NO CONSTA" in texto
    assert a.titulo in texto


@pytest.mark.django_db
def test_27_m09_no_inventa_destinatario(org_a, actor):
    """
    LA REGLA. La propuesta dice que falta; NO nombra a nadie. Se comprueba
    contra los Profile reales de la organizacion.
    """
    _, p1 = _persona(org_a)
    _, p2 = _persona(org_a)
    a = _crear(org_a, actor)
    ACT.objects.filter(pk=a.pk).update(estado_operativo=ACT.ESCALADA)

    A.asistir(org_a, A.COMPROMISOS)
    props = P.objects.filter(org=org_a, tipo_senal=P.ESCALAMIENTO_SIN_DESTINATARIO)
    assert props.exists()
    for prop in props:
        texto = f"{prop.accion_propuesta} {prop.motivo} {prop.impacto}"
        for persona in (p1, p2, actor):
            assert str(persona.id) not in texto, "nombro a un destinatario"
        assert "no existe todavía una política" in prop.motivo


@pytest.mark.django_db
def test_28_deduplicacion(org_a, actor):
    a = _crear(org_a, actor)
    ACT.objects.filter(pk=a.pk).update(estado_operativo=ACT.ESCALADA)

    A.asistir(org_a, A.COMPROMISOS)
    n1 = P.objects.filter(org=org_a,
                          tipo_senal=P.ESCALAMIENTO_SIN_DESTINATARIO).count()
    assert n1 == 1
    segunda = A.asistir(org_a, A.COMPROMISOS)
    assert P.objects.filter(org=org_a,
                            tipo_senal=P.ESCALAMIENTO_SIN_DESTINATARIO).count() == n1
    assert any(r["resultado"] == A.REPETIDA for r in segunda["recomendaciones"]
               if r["senal_origen"] == P.ESCALAMIENTO_SIN_DESTINATARIO)


@pytest.mark.django_db
def test_28b_una_escalada_completa_no_produce_senal(org_a, actor, jefe):
    a = _crear(org_a, actor)
    act.escalar(a, actor=actor, motivo="ayuda", escalado_a=jefe, nivel=ACT.NIVEL_1)
    s = [x for x in supervisor.detectar(org_a)
         if x.tipo == P.ESCALAMIENTO_SIN_DESTINATARIO and x.origen_id == str(a.id)]
    assert not s, "propuso sobre un escalamiento que si tiene destinatario"


@pytest.mark.django_db
def test_30_a2_muestra_el_escalamiento_existente(org_a, actor, jefe):
    a = _crear(org_a, actor, vence_en=timezone.now() - timedelta(hours=3))
    act.escalar(a, actor=actor, motivo="supera mi nivel", escalado_a=jefe,
                nivel=ACT.NIVEL_2)

    salida = A.asistir(org_a, A.COMPROMISOS, registrar=False)
    filas = [r for r in salida["recomendaciones"] if r["origen_id"] == str(a.id)]
    assert filas
    esc = filas[0]["estado"]["escalamiento"]
    assert esc is not None
    assert esc["escalado_a"] == str(jefe.id)
    assert esc["nivel"] == ACT.NIVEL_2
    assert esc["escalado_en"]


@pytest.mark.django_db
def test_30b_una_actividad_sin_escalar_no_finge_tenerlo(org_a, actor):
    a = _crear(org_a, actor, vence_en=timezone.now() - timedelta(hours=3))
    salida = A.asistir(org_a, A.COMPROMISOS, registrar=False)
    filas = [r for r in salida["recomendaciones"] if r["origen_id"] == str(a.id)]
    assert filas
    assert filas[0]["estado"]["escalamiento"] is None


@pytest.mark.django_db
def test_m09_no_decide_que_algo_necesita_escalamiento(org_a, actor):
    """
    Una actividad vencida hace mucho NO produce una señal de escalamiento: no
    existe politica que diga que la antiguedad lo justifique, y el detector no
    la inventa.
    """
    a = _crear(org_a, actor, vence_en=timezone.now() - timedelta(days=60))
    s = [x for x in supervisor.detectar(org_a)
         if x.tipo == P.ESCALAMIENTO_SIN_DESTINATARIO and x.origen_id == str(a.id)]
    assert not s, "invento que una actividad vieja necesita escalamiento"


# ====================================== 31-35. seguridad
@pytest.mark.django_db
def test_31_h05_sigue_bloqueada_y_h14_es_nueva():
    assert habilidades.HABILIDADES["H-05"].estado == habilidades.BLOQUEADA
    assert habilidades.HABILIDADES["H-14"].estado == habilidades.VIGENTE
    assert habilidades.POR_SENAL[P.ESCALAMIENTO_SIN_DESTINATARIO] == "H-14"
    huellas = {i: habilidades.HABILIDADES[i].huella() for i in habilidades.IDS}
    assert len(set(huellas.values())) == len(huellas)


@pytest.mark.django_db
def test_32_33_34_35_m09_no_escala_ni_llama_a_nadie(org_a, actor):
    import ast
    import inspect

    nombres = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(
            supervisor._escalamientos_sin_destinatario))):
        if isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr)
        elif isinstance(nodo, ast.Name):
            nombres.add(nodo.id)
    assert nombres.isdisjoint({
        "escalar", "asignar_responsable", "save", "delete", "update",
        "requests", "httpx", "celery", "apply_async", "shared_task",
        "wisphub", "smartolt"})

    #  y el asistente entero tampoco importa el servicio de escalamiento
    usados = set()
    for nodo in ast.walk(ast.parse(inspect.getsource(A))):
        if isinstance(nodo, ast.Attribute):
            usados.add(nodo.attr)
        elif isinstance(nodo, ast.Name):
            usados.add(nodo.id)
    assert "escalar" not in usados

    #  una pasada no cambia ninguna actividad
    a = _crear(org_a, actor)
    ACT.objects.filter(pk=a.pk).update(estado_operativo=ACT.ESCALADA)
    foto = list(ACT.objects.filter(org=org_a).order_by("id").values())
    A.asistir(org_a, A.COMPROMISOS)
    assert list(ACT.objects.filter(org=org_a).order_by("id").values()) == foto

    for p in P.objects.filter(org=org_a,
                              tipo_senal=P.ESCALAMIENTO_SIN_DESTINATARIO):
        assert p.nivel_autonomia_requerido <= P.NIVEL_RECOMENDAR
        assert p.estado == P.PROPUESTA


# ====================================== 36-38. migración
@pytest.mark.django_db
def test_36_37_la_migracion_es_aditiva_y_sin_runpython():
    import ast
    import pathlib
    ruta = (pathlib.Path(__file__).resolve().parent.parent
            / "migrations" / "0008_m05b_escalamiento.py")
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    ops = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and getattr(nodo.targets[0], "id", "") == "operations":
            for op in nodo.value.elts:
                ops.append(op.func.attr if isinstance(op.func, ast.Attribute)
                           else getattr(op.func, "id", "?"))
    assert set(ops) == {"AddField", "AlterField"}, ops
    assert ops.count("AddField") == 3
    for destructiva in ("RunPython", "RunSQL", "RemoveField", "DeleteModel",
                        "RenameField", "AlterModelTable"):
        assert destructiva not in ops


@pytest.mark.django_db
def test_38_no_hay_modelos_nuevos():
    """No se creó 'Escalamiento' ni 'Destinatario'."""
    from django.apps import apps
    modelos = {m.__name__ for m in apps.get_app_config("operaciones").get_models()}
    assert modelos == {"ActividadOperativa", "DisponibilidadTecnico",
                       "ProgramacionSemanal", "ProgramacionOrden",
                       "NovedadOperativa", "PropuestaSupervisor"}, modelos


# ====================================== API
@pytest.mark.django_db
def test_la_api_exige_destinatario_y_nivel(org_a, actor, jefe):
    from rest_framework.test import APIClient

    from common.serializer import OrgAwareRefreshToken

    u, p = _persona(org_a, "OPERACIONES")
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        f"Bearer {OrgAwareRefreshToken.for_user_and_org(u, org_a, p).access_token}"))
    a = _crear(org_a, actor)
    ruta = f"/api/operaciones/actividades/{a.id}/transicion/"

    r = c.post(ruta, {"accion": "escalar", "motivo": "ayuda"}, format="json")
    assert r.status_code == 400 and r.data["error"] == "FALTA_DESTINATARIO"

    r = c.post(ruta, {"accion": "escalar", "motivo": "ayuda",
                      "escalado_a_id": str(jefe.id)}, format="json")
    assert r.status_code == 400 and r.data["error"] == "FALTA_NIVEL"

    r = c.post(ruta, {"accion": "escalar", "motivo": "ayuda",
                      "escalado_a_id": str(jefe.id),
                      "nivel_escalamiento": ACT.NIVEL_2}, format="json")
    assert r.status_code == 200, r.data
    a.refresh_from_db()
    assert a.escalado_a_id == jefe.id and a.nivel_escalamiento == ACT.NIVEL_2
