# -*- coding: utf-8 -*-
"""
================================================================================
 LO NO CRITICO NACE DELEGADO; LO CRITICO ESPERA A UNA PERSONA  --  12/11/2026
================================================================================

QUE AFIRMA
----------
La decision del dueno del producto del 02/11/2026 (PRD §1, §2, §8.18),
aplicada al Supervisor NOC por la auditoria del menu del 12/11/2026: sin
ninguna fila --ni de tarea ni de nivel--, una tarea NO critica actua sola y
una critica no. Hasta hoy las diez tareas nacian apagadas y la empresa en
OBSERVAR, asi que el Supervisor pedia permiso para todo.

POR QUE CON LAS PUERTAS DE VERDAD
---------------------------------
Las demas pruebas del paso a Despacho abren las puertas con un monkeypatch de
'esta_delegada' y 'autonomia.puede'. Aca NO: lo que se prueba es justamente el
defecto de esas dos funciones. Lo unico que se reemplaza es la lectura del
interruptor, que es una llamada HTTP al motor, y se reemplaza por los dos
valores que puede tomar.

Las tres preguntas del pedido, cada una con su prueba:
  (a) sin filas, la no critica actua y la critica queda como propuesta;
  (b) una fila que una persona apago la frena, y una fila de nivel bajo tambien;
  (c) la validacion en codigo antes del efecto sigue rechazando lo invalido
      en el camino autonomo.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import autonomia
from operaciones import paso_a_despacho as pad
from operaciones import supervisor as sup
from operaciones import tareas_delegadas as td
from operaciones.gobierno_modelos import NivelAutonomia
from operaciones.models import PropuestaSupervisor
from operaciones.tareas_modelos import TareaDelegada

pytestmark = pytest.mark.django_db
P = PropuestaSupervisor


# =============================================================================
#  ARMADO
# =============================================================================

def _caso(org):
    from cases.models import Case

    return Case.objects.create(
        org=org, name="No tiene internet", status="New", priority="Normal",
        is_active=True, provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614", external_status="Nuevo",
        external_fetched_at=timezone.now(),
        description="El cliente dice que no tiene internet.")


def _falla(org, *, medida=True):
    """Una propuesta leida como falla de servicio. Con 'medida' lleva la
    medicion del equipo fuera de rango, que es lo que la habilita a pasar."""
    from operaciones import clasificacion_de_trabajo as clf
    from operaciones import diagnostico_de_ticket as dxt
    from operaciones import medicion_de_fallas as mdf

    p = P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(_caso(org).id), estado=P.PROPUESTA,
        evidencia=[{
            "fuente": dxt.FUENTE, "dato": "lectura del reclamo: sin servicio",
            "observado_en": "2026-11-12T13:00:00Z",
            "grupo": pad.FALLA_DE_SERVICIO, "labor": clf.CORRECTIVO,
            "labor_verificada": medida, "labor_porque": "señal debil",
            "confianza": "media", "confianza_del_grupo": "alta"}])
    if medida:
        mdf.escribir(p, mdf.de_la_respuesta({
            "estado": "en_linea", "senal": "debil", "senal_dbm": -27.4,
            "causa_caida": "", "motivo": ""}), timezone.now())
        p.refresh_from_db()
    return p


@pytest.fixture
def interruptor(monkeypatch):
    """El interruptor del motor, sin HTTP. Arranca permitiendo."""
    from operaciones import cierre_de_caso, fuentes_adaptadores

    estado = {"permitido": True, "estado": "activo", "motivo": ""}
    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia",
                        lambda org: dict(estado))
    #  Ningun camino de esta prueba debe hablar con el motor.
    monkeypatch.setattr(
        cierre_de_caso, "_pedirle_al_motor",
        lambda *a, **k: pytest.fail("el paso a Despacho no le habla al motor"))
    return estado


def _pasar(org):
    return sup._pasar_a_despacho_los_que_las_reglas_habiliten(
        org, timezone.now())["despacho"]


# =============================================================================
#  (a) SIN FILAS
# =============================================================================

def test_a_sin_filas_la_no_critica_pasa_a_despacho_sola(org_a, interruptor):
    """EL EFECTO: la propuesta queda ACEPTADA, que es el caso en la cola de
    Despacho. Sin una sola fila de tarea ni de nivel."""
    assert not TareaDelegada.objects.filter(org=org_a).exists()
    assert not NivelAutonomia.objects.filter(org=org_a).exists()
    p = _falla(org_a)

    reporte = _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.ACEPTADA, reporte
    assert reporte["pasaron"] == 1, reporte


def test_a_sin_filas_una_critica_queda_como_propuesta(org_a, interruptor,
                                                      monkeypatch):
    """La MISMA tarea, declarada critica: sin filas no actua. Se declara asi en
    una copia de la ficha (el catalogo de hoy no tiene ninguna critica), y es
    la clasificacion --no otra cosa-- lo que cambia el desenlace."""
    ficha = dict(td.CATALOGO[td.PASAR_A_DESPACHO], critica=True,
                 exige_nivel=P.NIVEL_CRITICO)
    monkeypatch.setitem(td.CATALOGO, td.PASAR_A_DESPACHO, ficha)
    p = _falla(org_a)

    _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.PROPUESTA


def test_a_una_critica_no_se_puede_delegar(org_a, admin_profile, monkeypatch):
    """Delegar una critica dejaria una fila «delegada» que no hace nada (exige
    el 4, que nunca alcanza). Se rechaza antes de escribir."""
    ficha = dict(td.CATALOGO[td.ARMAR_LA_JORNADA], critica=True,
                 exige_nivel=P.NIVEL_CRITICO)
    monkeypatch.setitem(td.CATALOGO, td.ARMAR_LA_JORNADA, ficha)

    with pytest.raises(td.ErrorTarea, match="crítica"):
        td.delegar(org_a, td.ARMAR_LA_JORNADA, actor=admin_profile)
    assert not TareaDelegada.objects.filter(org=org_a).exists()


def test_a_el_nivel_sin_fila_es_3_y_dice_que_es_el_defecto(org_a, interruptor):
    estado = autonomia.nivel_efectivo(org_a)
    assert estado["configurado"] == P.NIVEL_EJECUTAR_REVERSIBLE
    assert estado["efectivo"] == P.NIVEL_EJECUTAR_REVERSIBLE
    assert estado["por_omision"] is True
    #  El 4 sigue siendo "siempre una persona".
    assert autonomia.puede(org_a, P.NIVEL_CRITICO)["puede"] is False


# =============================================================================
#  (b) LO QUE UNA PERSONA APAGO SE RESPETA
# =============================================================================

def test_b_una_fila_apagada_frena_la_no_critica(org_a, admin_profile,
                                                interruptor):
    td.quitar(org_a, td.PASAR_A_DESPACHO, actor=admin_profile,
              motivo="quiero mirarlos yo esta semana")
    p = _falla(org_a)

    _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.PROPUESTA
    fila = TareaDelegada.objects.get(org=org_a, clave=td.PASAR_A_DESPACHO)
    assert fila.activa is False
    assert fila.quitada_por_id == admin_profile.id
    assert fila.motivo_al_quitar == "quiero mirarlos yo esta semana"


def test_b_volver_a_delegarla_la_prende_otra_vez(org_a, admin_profile,
                                                 interruptor):
    td.quitar(org_a, td.PASAR_A_DESPACHO, actor=admin_profile, motivo="x")
    td.delegar(org_a, td.PASAR_A_DESPACHO, actor=admin_profile)
    assert td.esta_delegada(org_a, td.PASAR_A_DESPACHO) is True


def test_b_una_fila_de_nivel_que_una_persona_bajo_tambien_frena(
        org_a, admin_profile, interruptor):
    autonomia.cambiar(org_a, P.NIVEL_RECOMENDAR, actor=admin_profile,
                      motivo="semana de migracion de la OLT",
                      criterios="ninguno: es una pausa")
    p = _falla(org_a)

    _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.PROPUESTA


def test_b_el_interruptor_apagado_sigue_frenando_todo(org_a, interruptor):
    interruptor.update(permitido=False, estado="detenido",
                       motivo="freno de mano")
    p = _falla(org_a)

    _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.PROPUESTA


def test_b_el_interruptor_ilegible_falla_cerrado(org_a, monkeypatch):
    from operaciones import fuentes_adaptadores

    def _cae(org):
        raise ConnectionError("el motor no contesta")

    monkeypatch.setattr(fuentes_adaptadores, "estado_de_autonomia", _cae)
    p = _falla(org_a)

    _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.PROPUESTA


# =============================================================================
#  (c) LA GARANTIA EN CODIGO NO SE FUE CON LA PERSONA
# =============================================================================

def test_c_una_falla_sin_medicion_no_pasa_sola_aunque_este_delegada(
        org_a, interruptor):
    """Con todo abierto por defecto, la regla de las cinco sigue decidiendo:
    una falla que la medicion del equipo no confirma no pasa a Despacho."""
    assert td.esta_delegada(org_a, td.PASAR_A_DESPACHO) is True
    p = _falla(org_a, medida=False)

    reporte = _pasar(org_a)

    p.refresh_from_db()
    assert p.estado == P.PROPUESTA, reporte
    assert reporte["pasaron"] == 0


# =============================================================================
#  EL CATALOGO DECLARA, Y LO QUE NO DECLARA ES CRITICO
# =============================================================================

def test_cada_tarea_declara_critica_explicitamente():
    for clave, ficha in td.CATALOGO.items():
        assert isinstance(ficha.get("critica"), bool), (
            f"'{clave}' no declara 'critica': lo que no se declara se trata "
            f"como critico, y eso la apagaria en silencio")


def test_critica_va_con_el_nivel_4_y_no_critica_con_3_o_menos():
    for clave, ficha in td.CATALOGO.items():
        if ficha["critica"]:
            assert ficha["exige_nivel"] >= P.NIVEL_CRITICO, clave
        else:
            assert ficha["exige_nivel"] <= P.NIVEL_EJECUTAR_REVERSIBLE, clave


def test_la_clasificacion_de_hoy_segun_prd_2():
    """Las diez, tarea por tarea (PRD §2 y §8.18). Si alguna cambia de lado,
    esta prueba lo dice y obliga a escribir el porque en la ficha."""
    assert {c for c, f in td.CATALOGO.items() if not f["critica"]} == {
        td.CERRAR_DESINCRONIZADOS, td.CICLO_AUTOMATICO, td.PASAR_A_DESPACHO,
        td.ARMAR_LA_JORNADA, td.CREAR_LAS_ORDENES, td.PUBLICAR_EL_REPARTO,
        td.CARGAR_EL_MATERIAL, td.PASAR_CON_LAS_CORRECCIONES,
        td.UBICAR_LOS_ASUNTOS, td.CERRAR_LO_REVISADO}


def test_sin_el_campo_o_fuera_del_catalogo_cuenta_como_critica(monkeypatch):
    sin_campo = {k: v for k, v in td.CATALOGO[td.ARMAR_LA_JORNADA].items()
                 if k != "critica"}
    monkeypatch.setitem(td.CATALOGO, td.ARMAR_LA_JORNADA, sin_campo)
    assert td.es_critica(td.ARMAR_LA_JORNADA) is True
    assert td.es_critica("una_que_no_existe") is True


def test_lo_critico_espera_a_una_persona():
    """Lo que Ajustes muestra como «espera a una persona» lo frena de verdad la
    funcion que nombra: el aviso de caida no se aprueba sin una persona."""
    import importlib

    from operaciones import aviso_de_caida

    for c in td.LO_QUE_ESPERA_A_UNA_PERSONA:
        modulo, funcion = c["garantia"].rsplit(".", 1)
        assert callable(getattr(importlib.import_module(modulo), funcion))
    with pytest.raises(aviso_de_caida.NoAvisable, match="FALTA_QUIEN_APRUEBA"):
        aviso_de_caida.aprobar(object(), None)


# =============================================================================
#  QUITAR SIN FILA, Y LA LISTA DE LO DELEGADO
# =============================================================================

def test_quitar_sin_fila_deja_la_fila_apagada_con_quien(org_a, admin_profile):
    td.quitar(org_a, td.CARGAR_EL_MATERIAL, actor=admin_profile, motivo="m")
    assert td.esta_delegada(org_a, td.CARGAR_EL_MATERIAL) is False
    with pytest.raises(td.ErrorTarea, match="ya no estaba"):
        td.quitar(org_a, td.CARGAR_EL_MATERIAL, actor=admin_profile)


def test_delegadas_incluye_las_que_nacen_delegadas(org_a, admin_profile):
    td.quitar(org_a, td.CARGAR_EL_MATERIAL, actor=admin_profile, motivo="m")
    lista = {d["clave"]: d for d in td.delegadas(org_a)}
    assert td.CARGAR_EL_MATERIAL not in lista
    assert lista[td.PASAR_A_DESPACHO]["por_omision"] is True
    assert len(lista) == len(td.CATALOGO) - 1


# =============================================================================
#  EL CICLO HORARIO RECORRE A QUIEN NO LO APAGO
# =============================================================================

def test_el_ciclo_recorre_a_la_empresa_del_motor_sin_fila(org_a, org_b,
                                                         admin_profile,
                                                         monkeypatch):
    from common.models import Org

    from operaciones import areas_del_tenant
    from operaciones import tasks

    sin_tenant = Org.objects.create(name="Organizacion que no es un ISP")
    tenants = {org_a.id: "isp-a", org_b.id: "isp-b"}
    monkeypatch.setattr(areas_del_tenant, "tenant_de",
                        lambda org_id: tenants.get(org_id, ""))
    #  org_b apago el ciclo: no se la recorre aunque sea un ISP.
    TareaDelegada.objects.create(org=org_b, clave=td.CICLO_AUTOMATICO,
                                 activa=False)
    corridas = []
    monkeypatch.setattr(sup, "correr_ciclo",
                        lambda org, *a, **k: corridas.append(org.id) or {})

    tasks.ciclo_del_supervisor()

    assert corridas == [org_a.id]
    assert sin_tenant.id not in corridas
