# -*- coding: utf-8 -*-
"""
El ciclo de corrección: devolver un trabajo y que la devolución tenga dientes.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
`verificar_checklist_completo` preguntaba si EXISTÍA evidencia recibida del
requisito, sobre toda la orden. En una segunda vuelta la evidencia de la
primera sigue ahí y sigue en `recibido`, así que `/completar/` habría pasado de
inmediato sin que el técnico subiera nada: el supervisor devolvía el trabajo y
el sistema lo daba por corregido solo.

La prueba que más importa acá es la C. Es la única que falla si alguien vuelve
a la lógica anterior, y es la que convierte la devolución en algo real en vez
de un cambio de etiqueta.
"""

import pytest

from campo.models import (
    AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion,
)
from campo.services.transiciones import (
    TransicionInvalidaError, aprobar, completar_campo, ejecutar_accion_operativa,
    requerir_correccion,
)
from campo.services.validador import (
    requisitos_a_corregir, verificar_checklist_completo,
)

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------
#  Escenario: tres evidencias obligatorias. El supervisor devuelve UNA.
# --------------------------------------------------------------------------

@pytest.fixture
def version_tres_fotos(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_correctivo",
                                 nombre="Correctivo Fibra")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={
            "pasos": [{"id": "p1", "titulo": "Ejecución"}],
            "campos": [],
            "evidencias": [
                {"id": "foto_cto", "titulo": "Foto CTO", "obligatorio": True},
                {"id": "foto_potencia", "titulo": "Foto potencia", "obligatorio": True},
                {"id": "foto_router", "titulo": "Foto router", "obligatorio": True},
            ],
        },
    )


@pytest.fixture
def orden(org_a, user_profile, version_tres_fotos):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=3001, tipo_trabajo_version=version_tres_fotos,
        cliente_nombre="Cliente de prueba",
        estado_operativo=OrdenTrabajo.EN_SITIO,
    )
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return o


def subir(orden, requisito, vuelta, sha=None):
    """Una evidencia recibida, como la deja el flujo real de subida."""
    return EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=vuelta, sha256=sha or f"{requisito}-v{vuelta}",
        storage_key=f"k/{requisito}/{vuelta}", nombre_original=f"{requisito}.jpg",
        mime_type="image/jpeg", bytes=1024,
        estado_archivo=EvidenciaTrabajo.RECIBIDO,
    )


def completar(orden, profile):
    """Lo que hace el endpoint: checklist duro y recién después transición."""
    errores = verificar_checklist_completo(orden)
    if errores:
        raise AssertionError(f"checklist incompleto: {errores}")
    return completar_campo(orden, profile=profile)


# ============================== A ==========================================

def test_a_vuelta_uno_completa_deja_pendiente_de_validacion(orden, user_profile):
    """Completar engancha la validación. Antes quedaba en 'sin_evaluar' para siempre."""
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)

    assert verificar_checklist_completo(orden) == []
    completar(orden, user_profile)
    orden.refresh_from_db()

    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
    assert orden.estado_validacion == OrdenTrabajo.PENDIENTE
    assert orden.vuelta == 1
    assert orden.eventos.filter(tipo="presentado_a_validacion").exists()


# ============================== B ==========================================

def test_b_devolver_un_requisito_sube_la_vuelta(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)

    requerir_correccion(orden, requisitos=["foto_potencia"],
                        profile=user_profile, observacion="Medición inválida")
    orden.refresh_from_db()

    assert orden.vuelta == 2
    assert orden.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert orden.estado_validacion == OrdenTrabajo.REQUIERE_CORRECCION

    evento = orden.eventos.filter(tipo="correccion_requerida").first()
    assert evento is not None
    assert evento.datos["vuelta_anterior"] == 1
    assert evento.datos["vuelta_nueva"] == 2
    assert evento.datos["requisitos_a_corregir"] == ["foto_potencia"]
    assert evento.datos["observacion"] == "Medición inválida"
    assert requisitos_a_corregir(orden) == {"foto_potencia"}


# ============================== C ==========================================
#  La prueba que sostiene la decisión entera.

def test_c_evidencia_vieja_no_satisface_la_correccion(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"], profile=user_profile)
    orden.refresh_from_db()

    # La foto de la vuelta 1 sigue existiendo y sigue 'recibido'. Con la lógica
    # anterior el checklist la habría dado por buena y la devolución no habría
    # exigido nada.
    assert orden.evidencias.filter(requisito_id="foto_potencia",
                                   vuelta=1).exists()

    errores = verificar_checklist_completo(orden)
    codigos = {e["codigo"] for e in errores}
    devueltos = {e.get("requisito_id") for e in errores}
    assert codigos == {"CORRECCION_PENDIENTE"}
    assert devueltos == {"foto_potencia"}


# ============================== D ==========================================

def test_d_evidencia_nueva_de_la_vuelta_actual_si_satisface(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"], profile=user_profile)
    orden.refresh_from_db()

    subir(orden, "foto_potencia", 2)
    assert verificar_checklist_completo(orden) == []

    # El tecnico vuelve al terreno antes de re-presentar: la maquina no deja
    # pasar de 'correccion_requerida' a 'completada_campo' de un salto.
    ejecutar_accion_operativa(orden, "marcar_llegada", profile=user_profile)
    orden.refresh_from_db()
    completar(orden, user_profile)
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
    assert orden.estado_validacion == OrdenTrabajo.PENDIENTE


# ============================== E ==========================================

def test_e_los_no_devueltos_no_se_repiten(orden, user_profile):
    """De ocho fotos, una mal: se repite una. Es la razón de haber elegido
    vuelta dirigida y no vuelta completa."""
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"], profile=user_profile)
    orden.refresh_from_db()

    subir(orden, "foto_potencia", 2)
    assert verificar_checklist_completo(orden) == []

    # foto_cto y foto_router siguen teniendo SOLO evidencia de la vuelta 1.
    for r in ("foto_cto", "foto_router"):
        vueltas = set(orden.evidencias.filter(requisito_id=r)
                      .values_list("vuelta", flat=True))
        assert vueltas == {1}


# ============================== F ==========================================

def test_f_segunda_devolucion_funciona_igual(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)

    requerir_correccion(orden, requisitos=["foto_potencia"], profile=user_profile)
    orden.refresh_from_db()
    subir(orden, "foto_potencia", 2)
    ejecutar_accion_operativa(orden, "marcar_llegada", profile=user_profile)
    orden.refresh_from_db()
    completar(orden, user_profile)
    orden.refresh_from_db()

    # Segunda devolución, y ahora de OTRO requisito.
    requerir_correccion(orden, requisitos=["foto_cto"], profile=user_profile)
    orden.refresh_from_db()
    assert orden.vuelta == 3
    assert requisitos_a_corregir(orden) == {"foto_cto"}

    # La foto_potencia de la vuelta 2 sigue valiendo: no fue devuelta esta vez.
    errores = verificar_checklist_completo(orden)
    assert {e.get("requisito_id") for e in errores} == {"foto_cto"}

    subir(orden, "foto_cto", 3)
    assert verificar_checklist_completo(orden) == []


# ============================== G ==========================================

def test_g_el_historial_queda_entero(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"], profile=user_profile)
    orden.refresh_from_db()
    subir(orden, "foto_potencia", 2)
    ejecutar_accion_operativa(orden, "marcar_llegada", profile=user_profile)
    orden.refresh_from_db()
    completar(orden, user_profile)
    orden.refresh_from_db()
    aprobar(orden, profile=user_profile)
    orden.refresh_from_db()

    # Nada se borró ni se sobrescribió: cuatro evidencias, dos de ellas del
    # mismo requisito en vueltas distintas.
    assert orden.evidencias.count() == 4
    potencia = sorted(orden.evidencias.filter(requisito_id="foto_potencia")
                      .values_list("vuelta", flat=True))
    assert potencia == [1, 2]

    tipos = list(orden.eventos.order_by("created_at").values_list("tipo", flat=True))
    for esperado in ("trabajo_completado_campo", "presentado_a_validacion",
                     "correccion_requerida", "reapertura_correccion",
                     "validacion_aprobada"):
        assert esperado in tipos, f"falta el evento {esperado}: {tipos}"

    # Y la métrica que motivó todo esto se puede calcular.
    assert orden.vuelta == 2          # no se aprobó a la primera
    assert orden.estado_validacion == OrdenTrabajo.APROBADO


# ============================== H ==========================================

def test_h_aprobado_es_terminal(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)
    aprobar(orden, profile=user_profile)
    orden.refresh_from_db()

    # Un trabajo aprobado no se devuelve. Si hay que volver, es otra orden --
    # que es justamente lo que permite tener varias por caso.
    with pytest.raises(TransicionInvalidaError):
        requerir_correccion(orden, requisitos=["foto_cto"], profile=user_profile)


# --------------------------------------------------------------------------
#  Guardas del propio mecanismo
# --------------------------------------------------------------------------

def test_no_se_devuelve_un_requisito_inexistente(orden, user_profile):
    """Devolver algo que la plantilla no declara dejaría el trabajo imposible
    de completar: el checklist esperaría para siempre una evidencia que nadie
    puede subir."""
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)

    with pytest.raises(TransicionInvalidaError):
        requerir_correccion(orden, requisitos=["foto_que_no_existe"],
                            profile=user_profile)


def test_no_se_devuelve_sin_decir_que(orden, user_profile):
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)

    with pytest.raises(TransicionInvalidaError):
        requerir_correccion(orden, requisitos=[], profile=user_profile)


def test_la_maquina_operativa_permite_volver_al_terreno(orden, user_profile):
    """CORRECCION_REQUERIDA -> EN_SITIO. Antes 'completada_campo' solo podía ir
    a 'cerrada' y no había ningún camino de vuelta."""
    for r in ("foto_cto", "foto_potencia", "foto_router"):
        subir(orden, r, 1)
    completar(orden, user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"], profile=user_profile)
    orden.refresh_from_db()

    ejecutar_accion_operativa(orden, "marcar_llegada", profile=user_profile)
    orden.refresh_from_db()
    assert orden.estado_operativo == OrdenTrabajo.EN_SITIO
