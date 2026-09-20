# -*- coding: utf-8 -*-
"""
================================================================================
 M09  --  el Supervisor NOC IA en Shadow Mode
================================================================================

Lo que hay que demostrar acá no es que el Supervisor funcione: es que NO
ejecuta. Las dos cosas se prueban distinto --

  funciona     se le dan datos y se cuenta cuántas propuestas salen;
  no ejecuta   se afirma sobre el código: el único camino declarado hacia la
               ejecución levanta una excepción, el estado 'ejecutada' no existe
               entre los valores posibles, y el módulo no importa nada que
               hable con WispHub o SmartOLT.

La segunda mitad es la que importa, y es la que sobreviviría a que alguien
"mejore" el Supervisor.
================================================================================
"""

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from conftest import rls_org
from cases.models import Case
from operaciones import auditoria, supervisor
from operaciones.models import ActividadOperativa, PropuestaSupervisor


def _identificadores_del_codigo() -> set[str]:
    """
    Todo nombre que el CODIGO de supervisor.py usa: importaciones, variables,
    atributos y llamadas. SIN comentarios ni docstrings.

    La primera version de las dos pruebas que usan esto miraba el texto del
    archivo, y se encontraba a si misma: los comentarios que EXPLICAN por que
    el Supervisor no puede tocar WispHub mencionan WispHub. Documentar una
    prohibicion no puede hacer fallar la guarda que la vigila -- es el mismo
    tropiezo que ya habia pasado con la guarda del SET parametrizado en el
    motor.
    """
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(supervisor))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name):
            nombres.add(nodo.id.lower())
        elif isinstance(nodo, ast.Attribute):
            nombres.add(nodo.attr.lower())
        elif isinstance(nodo, ast.alias):
            nombres.update(p.lower() for p in nodo.name.split("."))
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.update(p.lower() for p in nodo.module.split("."))
    return nombres


@pytest.fixture
def actividad_vencida(org_a, user_profile):
    return ActividadOperativa.objects.create(
        org=org_a, titulo="Llamar al cliente para confirmar",
        responsable=user_profile,
        vence_en=timezone.now() - timedelta(hours=30),
    )


@pytest.fixture
def propuesta(org_a, actividad_vencida):
    senales = [s for s in supervisor.detectar(org_a)
               if s.tipo == PropuestaSupervisor.ACTIVIDAD_VENCIDA]
    assert senales, "la señal de actividad vencida tiene que dispararse"
    return supervisor.registrar_propuesta(
        org_a, senales[0], supervisor.analizar(senales[0]))


# --- 1. señal --------------------------------------------------------------
def test_una_actividad_vencida_produce_senal(org_a, actividad_vencida):
    senales = supervisor.detectar(org_a)
    vencidas = [s for s in senales if s.tipo == PropuestaSupervisor.ACTIVIDAD_VENCIDA]
    assert len(vencidas) == 1
    assert vencidas[0].origen_tipo == "actividad"
    assert vencidas[0].origen_id == str(actividad_vencida.id)


def test_la_deteccion_no_escribe_nada(org_a, actividad_vencida):
    """Detectar es leer. Si escribiera, no sería observación."""
    antes = PropuestaSupervisor.objects.count()
    supervisor.detectar(org_a)
    assert PropuestaSupervisor.objects.count() == antes


def test_una_actividad_bloqueada_usa_su_motivo_como_evidencia(org_a, user_profile):
    ActividadOperativa.objects.create(
        org=org_a, titulo="Cambiar el conector", responsable=user_profile,
        estado_operativo=ActividadOperativa.BLOQUEADA,
        motivo_bloqueo="No llegó el conector SC/APC",
    )
    senales = [s for s in supervisor.detectar(org_a)
               if s.tipo == PropuestaSupervisor.ACTIVIDAD_BLOQUEADA]
    assert len(senales) == 1
    assert "SC/APC" in senales[0].evidencia[0]["dato"]


def test_no_existe_ninguna_senal_de_incumplimiento_de_primera_respuesta():
    """
    'first_response_at' está poblado en 4 de 165 casos (15/09/2026), así que su
    ausencia no prueba nada: un caso sin ese dato puede haber sido atendido en
    diez minutos. Afirmar un incumplimiento sobre eso sería acusar a alguien de
    algo que el dato no sostiene.
    """
    tipos = {t for t, _ in PropuestaSupervisor.TIPOS_SENAL}
    assert not any("first_response" in t or "incumplimiento" in t for t in tipos)


# --- 2. propuesta ----------------------------------------------------------
def test_la_senal_se_convierte_en_propuesta_con_evidencia(org_a, propuesta):
    assert propuesta.estado == PropuestaSupervisor.PROPUESTA
    assert propuesta.accion_propuesta
    assert propuesta.motivo
    assert propuesta.evidencia, "sin evidencia no debería existir"
    assert propuesta.expira_en is not None


def test_cada_pieza_de_evidencia_dice_de_donde_salio(propuesta):
    for observacion in propuesta.evidencia:
        assert {"fuente", "id", "dato", "observado_en"} <= set(observacion)
        assert observacion["dato"], "una observación vacía no es evidencia"


def test_la_prioridad_se_puede_explicar(propuesta):
    """
    No es un score mágico: los componentes que la formaron viajan como
    evidencia, así que quien la lee puede reconstruir por qué quedó ahí.
    """
    calculos = [e for e in propuesta.evidencia if e["fuente"] == "calculo_prioridad"]
    assert len(calculos) == 1
    assert "base" in calculos[0]["dato"]


# --- 3 y 4. la evidencia es obligatoria ------------------------------------
def test_una_senal_sin_evidencia_no_produce_propuesta(org_a):
    vacia = supervisor.Senal(
        tipo=PropuestaSupervisor.ACTIVIDAD_VENCIDA,
        origen_tipo="actividad", origen_id=str(uuid.uuid4()), evidencia=[])
    with pytest.raises(ValueError, match="sin evidencia"):
        supervisor.registrar_propuesta(org_a, vacia, {"accion_propuesta": "x",
                                                      "motivo": "y", "prioridad": 50})


def test_la_base_tambien_rechaza_una_propuesta_sin_evidencia(org_a):
    """
    Dos capas, y las dos hacen falta: la validación de Python se puede saltear
    llamando por otro camino; la restricción de la base, no.
    """
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PropuestaSupervisor.objects.create(
                org=org_a, tipo_senal=PropuestaSupervisor.ACTIVIDAD_VENCIDA,
                origen_tipo="actividad", origen_id=str(uuid.uuid4()),
                accion_propuesta="Algo", motivo="Porque sí", evidencia=[],
            )


def test_una_evidencia_mal_formada_se_rechaza(org_a):
    p = PropuestaSupervisor(
        org=org_a, tipo_senal=PropuestaSupervisor.ACTIVIDAD_VENCIDA,
        origen_tipo="actividad", origen_id=str(uuid.uuid4()),
        accion_propuesta="Algo", motivo="Porque sí",
        evidencia=[{"fuente": "actividad"}],   # le faltan 'dato' y 'observado_en'
    )
    with pytest.raises(ValidationError):
        p.clean()


def test_una_senal_sin_analisis_declarado_no_inventa_recomendacion(org_a):
    """Antes que inventar una recomendación, no se hace ninguna."""
    desconocida = supervisor.Senal(
        tipo="senal_que_no_existe", origen_tipo="actividad",
        origen_id=str(uuid.uuid4()),
        evidencia=[{"fuente": "x", "id": "1", "dato": "algo", "observado_en": "hoy"}])
    assert supervisor.analizar(desconocida) == {}
    with pytest.raises(ValueError, match="sin análisis"):
        supervisor.registrar_propuesta(org_a, desconocida, {})


# --- 5, 6, 7, 8. revisión del Jefe de Operaciones --------------------------
def test_aceptar_queda_auditado_y_NO_ejecuta(org_a, propuesta, admin_profile):
    revisada = supervisor.revisar(
        propuesta, actor=admin_profile, decision=PropuestaSupervisor.ACEPTADA,
        comentario="De acuerdo, lo tomo yo")

    assert revisada.estado == "aceptada"
    assert revisada.revisado_por_id == admin_profile.id
    assert revisada.revisado_en is not None
    # Aceptar no crea ninguna referencia a la capa de ejecución.
    assert revisada.accion_propuesta_ref == ""

    filas = list(auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, propuesta.id))
    aprobaciones = [f for f in filas if f.action == "APPROVED"]
    assert len(aprobaciones) == 1
    assert aprobaciones[0].user_id == admin_profile.id
    assert aprobaciones[0].metadata["sin_ejecucion"] is True


def test_rechazar_queda_auditado_con_su_motivo(org_a, propuesta, admin_profile):
    supervisor.revisar(propuesta, actor=admin_profile,
                       decision=PropuestaSupervisor.RECHAZADA,
                       comentario="El cliente ya reprogramó por su cuenta")
    filas = [f for f in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, propuesta.id)
             if f.action == "REJECTED"]
    assert len(filas) == 1
    assert "reprogramó" in filas[0].metadata["motivo"]


def test_modificar_queda_auditado(org_a, propuesta, admin_profile):
    supervisor.revisar(propuesta, actor=admin_profile,
                       decision=PropuestaSupervisor.MODIFICADA,
                       comentario="Lo mismo pero para el jueves")
    propuesta.refresh_from_db()
    assert propuesta.estado == "modificada"
    assert propuesta.resultado == "Lo mismo pero para el jueves"


def test_una_revision_sin_revisor_no_es_una_revision(propuesta):
    with pytest.raises(ValueError, match="sin revisor"):
        supervisor.revisar(propuesta, actor=None,
                           decision=PropuestaSupervisor.ACEPTADA)


def test_una_propuesta_no_se_revisa_dos_veces(propuesta, admin_profile):
    supervisor.revisar(propuesta, actor=admin_profile,
                       decision=PropuestaSupervisor.ACEPTADA)
    with pytest.raises(ValueError, match="ya está"):
        supervisor.revisar(propuesta, actor=admin_profile,
                           decision=PropuestaSupervisor.RECHAZADA)


# --- 9. expiración ---------------------------------------------------------
def test_una_propuesta_vieja_expira_sola(org_a, propuesta):
    """
    Una recomendación de hace tres semanas sobre un caso ya cerrado es ruido.
    La cola que ya existe en el motor --36 pendientes, la más vieja del 19/08--
    es la demostración de a dónde lleva no tener esto.
    """
    propuesta.expira_en = timezone.now() - timedelta(days=1)
    propuesta.save(update_fields=["expira_en"])

    assert supervisor.expirar_vencidas(org_a) == 1
    propuesta.refresh_from_db()
    assert propuesta.estado == "expirada"

    filas = [f for f in auditoria.historial(org_a, auditoria.ENTIDAD_PROPUESTA, propuesta.id)
             if f.action == "STATUS_CHANGED"]
    assert filas and filas[0].metadata["estado_nuevo"] == "expirada"


# --- 10. aislamiento -------------------------------------------------------
def test_el_supervisor_de_una_empresa_no_ve_la_otra(org_a, org_b):
    with rls_org(org_a):
        ActividadOperativa.objects.create(
            org=org_a, titulo="De A", vence_en=timezone.now() - timedelta(hours=2))
    with rls_org(org_b):
        ActividadOperativa.objects.create(
            org=org_b, titulo="De B", vence_en=timezone.now() - timedelta(hours=2))

    with rls_org(org_a):
        resumen_a = supervisor.correr_ciclo(org_a)
        origenes_a = set(PropuestaSupervisor.objects.filter(org=org_a)
                         .values_list("origen_id", flat=True))
        ids_b = {str(x) for x in ActividadOperativa.objects.filter(org=org_b)
                 .values_list("id", flat=True)}

    assert resumen_a["propuestas"] >= 1
    assert not (origenes_a & ids_b), "una empresa no puede proponer sobre la otra"


# --- 11. SHADOW MODE: la parte que importa ---------------------------------
def test_ejecutada_no_es_un_estado_posible():
    """
    Aceptar significa "estoy de acuerdo", no "se hizo". Que el estado ni
    siquiera exista es lo que lo vuelve comprobable en vez de prometido.
    """
    estados = {e for e, _ in PropuestaSupervisor.ESTADOS}
    assert "ejecutada" not in estados
    assert estados == {"propuesta", "aceptada", "modificada", "rechazada",
                       "expirada", "cancelada"}


def test_el_unico_camino_a_la_ejecucion_levanta(propuesta):
    """
    Es la diferencia entre "no encontramos ninguna llamada externa" --una
    afirmación sobre lo que alguien no vio-- y "el camino declarado levanta",
    que es una afirmación sobre lo que el código hace.
    """
    with pytest.raises(supervisor.EjecucionNoPermitida):
        supervisor.ejecutar_propuesta(propuesta)


def test_el_modulo_no_habla_con_ningun_sistema_externo():
    """
    Shadow Mode no puede reiniciar una ONT, activar CATV ni crear un ticket. Se
    comprueba sobre el FUENTE del módulo: si alguien agrega esa llamada, esto
    se pone rojo aunque la llamada nunca se ejecute en una prueba.
    """
    prohibidos = {"wisphub", "smartolt", "requests", "httpx", "urllib",
                  "reiniciar_ont", "activar_catv", "cambiar_tipo_onu"}
    encontrados = prohibidos & _identificadores_del_codigo()
    assert not encontrados, (
        f"el Supervisor no puede tocar sistemas externos, y su CODIGO menciona: "
        f"{sorted(encontrados)}"
    )


def test_el_ciclo_completo_no_ejecuta_nada(org_a, actividad_vencida):
    """De punta a punta: datos reales, señal, propuesta, y cero ejecuciones."""
    resumen = supervisor.correr_ciclo(org_a)
    assert resumen["propuestas"] >= 1
    assert supervisor.SHADOW_MODE is True

    for p in PropuestaSupervisor.objects.filter(org=org_a):
        assert p.estado == "propuesta"
        assert p.accion_propuesta_ref == ""


def test_una_pasada_repetida_no_duplica_la_cola(org_a, actividad_vencida):
    """
    Sin esto, cada pasada agregaría una propuesta más sobre el mismo caso y la
    cola se volvería ruido -- exactamente lo que le pasó a la del motor.
    """
    primera = supervisor.correr_ciclo(org_a)
    segunda = supervisor.correr_ciclo(org_a)
    assert primera["propuestas"] >= 1
    assert segunda["propuestas"] == 0
    assert segunda["repetidas"] >= 1


# --- 12. niveles de autonomía ----------------------------------------------
def test_el_supervisor_nace_en_nivel_0_1(org_a, actividad_vencida):
    """No se habilita nivel 2, 3 ni 4: todo lo que emite es 'recomendar'."""
    supervisor.correr_ciclo(org_a)
    niveles = set(PropuestaSupervisor.objects.filter(org=org_a)
                  .values_list("nivel_autonomia_requerido", flat=True))
    assert niveles <= {PropuestaSupervisor.NIVEL_OBSERVAR,
                       PropuestaSupervisor.NIVEL_RECOMENDAR}
    assert PropuestaSupervisor.NIVEL_MAXIMO_ETAPA == 1


def test_una_propuesta_de_nivel_alto_queda_marcada_fuera_de_alcance(org_a, propuesta):
    propuesta.nivel_autonomia_requerido = PropuestaSupervisor.NIVEL_COORDINAR
    assert propuesta.dentro_del_alcance is False
    propuesta.nivel_autonomia_requerido = PropuestaSupervisor.NIVEL_RECOMENDAR
    assert propuesta.dentro_del_alcance is True


def test_el_supervisor_no_puede_tocar_permisos_ni_autonomia():
    """
    Ningún agente eleva su propio nivel. Se comprueba sobre el fuente: el
    módulo no menciona Profile.role, ni el interruptor, ni tenant_config.
    """
    prohibidos = {"interruptor", "tenant_config", "is_organization_admin",
                  "role", "permissions", "user_permissions"}
    encontrados = prohibidos & _identificadores_del_codigo()
    assert not encontrados, (
        f"el Supervisor no puede modificar sus propios permisos, y su CODIGO "
        f"menciona: {sorted(encontrados)}"
    )
