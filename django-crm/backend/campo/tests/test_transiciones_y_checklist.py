# -*- coding: utf-8 -*-
"""Pruebas de la máquina de estados, transiciones y validación estricta de checklist/datos."""

import pytest
from campo.models import AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services.transiciones import (
    TransicionInvalidaError,
    completar_campo,
    ejecutar_accion_operativa,
)
from campo.services.validador import (
    validar_campos_tecnicos,
    verificar_checklist_completo,
)


@pytest.fixture
def work_type_ftth(org_a):
    return WorkType.objects.create(
        org=org_a,
        codigo="ftth_instalacion",
        nombre="Instalación Fibra Óptica",
    )


@pytest.fixture
def version_publicada(work_type_ftth):
    esquema = {
        "pasos": [{"id": "paso_1", "titulo": "Datos de Instalación"}],
        "campos": [
            {"id": "serial_ont", "tipo": "texto", "reglas": {"required": True, "min": 5}},
            {"id": "potencia_rx", "tipo": "decimal", "reglas": {"required": True, "min": -28.0, "max": -8.0}},
            {"id": "observaciones", "tipo": "texto", "reglas": {"required": False}},
        ],
        "evidencias": [
            {"id": "foto_ont", "titulo": "Foto ONT", "tipo": "foto", "obligatorio": True},
            {"id": "foto_speedtest", "titulo": "Test de Velocidad", "tipo": "foto", "obligatorio": False},
        ],
    }
    return WorkTypeVersion.objects.create(
        work_type=work_type_ftth,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=esquema,
    )


@pytest.fixture
def orden_asignada(org_a, user_profile, version_publicada):
    orden = OrdenTrabajo.objects.create(
        org=org_a,
        numero=2001,
        tipo_trabajo_version=version_publicada,
        cliente_nombre="Beatriz Pinzón",
        cliente_direccion="Calle 50 # 10-20",
        estado_operativo=OrdenTrabajo.ASIGNADA,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=orden,
        profile=user_profile,
        rol="tecnico_lider",
        es_principal=True,
    )
    return orden


def test_flujo_transiciones_exitoso(orden_asignada, user_profile):
    """Verifica el camino feliz: ASIGNADA -> EN_CAMINO -> EN_SITIO, con incremento de revisión y eventos."""
    assert orden_asignada.revision == 1
    assert orden_asignada.estado_operativo == OrdenTrabajo.ASIGNADA

    # 1. Iniciar desplazamiento
    ejecutar_accion_operativa(orden_asignada, "marcar_en_camino", profile=user_profile)
    orden_asignada.refresh_from_db()
    assert orden_asignada.estado_operativo == OrdenTrabajo.EN_CAMINO
    assert orden_asignada.revision == 2
    assert orden_asignada.eventos.filter(tipo="accion_marcar_en_camino").exists()

    # 2. Registrar llegada
    ejecutar_accion_operativa(
        orden_asignada, "marcar_llegada", profile=user_profile, metadatos={"lat": 4.60, "lng": -74.08}
    )
    orden_asignada.refresh_from_db()
    assert orden_asignada.estado_operativo == OrdenTrabajo.EN_SITIO
    assert orden_asignada.revision == 3
    evento_llegada = orden_asignada.eventos.filter(tipo="accion_marcar_llegada").first()
    assert evento_llegada is not None
    assert evento_llegada.datos.get("lat") == 4.60


def test_transiciones_invalidas(orden_asignada, user_profile):
    """No permite saltos ilegales (ej: intentar completar o llegar antes de iniciar camino)."""
    # Cancelar la orden
    ejecutar_accion_operativa(orden_asignada, "cancelar", profile=user_profile, metadatos={"motivo": "Cliente ausente"})
    orden_asignada.refresh_from_db()
    assert orden_asignada.estado_operativo == OrdenTrabajo.CANCELADA

    # Desde CANCELADA no se puede hacer ninguna transición
    with pytest.raises(TransicionInvalidaError):
        ejecutar_accion_operativa(orden_asignada, "marcar_en_camino", profile=user_profile)


def test_validador_datos_tecnicos(version_publicada):
    """Valida reglas requeridas, límites mín/máx y tipos."""
    # 1. Potencia fuera de rango
    datos_rango_invalido = {
        "serial_ont": "ALCL12345",
        "potencia_rx": -32.5,  # Menor al min permitido de -28.0
    }
    _, errores_rango = validar_campos_tecnicos(version_publicada.esquema, datos_rango_invalido)
    assert "potencia_rx" in errores_rango

    # 2. Datos correctos pasan sin errores
    datos_validos = {
        "serial_ont": "ALCL12345",
        "potencia_rx": -19.4,
        "observaciones": "Instalación en segundo piso",
    }
    valores_limpios, errores_validos = validar_campos_tecnicos(version_publicada.esquema, datos_validos)
    assert errores_validos == {}
    assert valores_limpios["serial_ont"] == "ALCL12345"
    assert valores_limpios["potencia_rx"] == -19.4


def test_completar_campo_requiere_evidencias_y_datos(orden_asignada, user_profile):
    """Verifica que verificar_checklist_completo bloquee si faltan evidencias obligatorias o datos requeridos."""
    # Llevar hasta EN_SITIO
    ejecutar_accion_operativa(orden_asignada, "marcar_en_camino", profile=user_profile)
    ejecutar_accion_operativa(orden_asignada, "marcar_llegada", profile=user_profile)
    orden_asignada.refresh_from_db()

    # 1. Checklist sin datos ni fotos -> arroja errores
    errores_iniciales = verificar_checklist_completo(orden_asignada)
    codigos_err = [e["codigo"] for e in errores_iniciales]
    assert "CAMPO_FALTANTE" in codigos_err
    assert "EVIDENCIA_FALTANTE" in codigos_err

    # 2. Guardar datos válidos pero sin foto obligatoria
    orden_asignada.datos = {
        "serial_ont": "ZTEG998877",
        "potencia_rx": -18.2,
    }
    orden_asignada.save()

    errores_con_datos = verificar_checklist_completo(orden_asignada)
    assert any(e["codigo"] == "EVIDENCIA_FALTANTE" for e in errores_con_datos)

    # 3. Adjuntar y confirmar foto_ont obligatoria
    EvidenciaTrabajo.objects.create(
        org=orden_asignada.org,
        orden_trabajo=orden_asignada,
        requisito_id="foto_ont",
        nombre_original="ont.jpg",
        mime_type="image/jpeg",
        bytes=1024,
        storage_key=f"evidencias/{orden_asignada.id}/ont.jpg",
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        estado_archivo="recibido",
    )

    # 4. Ahora el checklist está 100% completo
    errores_completos = verificar_checklist_completo(orden_asignada)
    assert errores_completos == []

    # 5. Completar campo exitoso
    completar_campo(orden_asignada, profile=user_profile)
    orden_asignada.refresh_from_db()
    assert orden_asignada.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
    assert orden_asignada.eventos.filter(tipo="trabajo_completado_campo").exists()
