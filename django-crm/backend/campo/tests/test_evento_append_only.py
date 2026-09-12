# -*- coding: utf-8 -*-
"""
EventoTrabajo es append-only, y ahora hay algo que lo impide.

    uv run pytest campo/tests/test_evento_append_only.py --no-cov -v

POR QUE EXISTE
--------------
El docstring del modelo decia "Bitácora append-only" desde el primer dia, y
nada lo impedia: 'update()', 'delete()' y 'save()' sobre una fila existente
funcionaban los tres. La auditoria lo encontro y lo puso primero en la lista de
riesgos, con razon.

No es un detalle de pulcritud. De esta bitacora salen dos cosas que deciden si
una orden se puede cerrar:

  - 'validador.verificar_checklist_completo' mira la evidencia de la vuelta
    actual, y la vuelta se cuenta con los eventos.
  - la devolucion dirigida guarda en 'datos' que requisitos hay que corregir.

Reescribir un evento cambia si un trabajo se da por bueno. Borrar uno borra la
prueba de que alguien lo devolvio.

LO QUE ESTA PRUEBA NO CUBRE
---------------------------
El borrado en cascada. 'orden' y 'org' son FK con on_delete=CASCADE y el
colector de Django emite el DELETE al nivel de SQL, sin pasar por el modelo ni
por el queryset. Borrar una OrdenTrabajo sigue llevandose sus eventos. Hay una
prueba abajo que lo DEJA ESCRITO en vez de disimularlo: si algun dia se cierra
ese camino, esa prueba falla y obliga a mirar.
"""

import pytest
from django.core.exceptions import ValidationError

from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_bitacora",
                                 nombre="Correctivo Fibra")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})


@pytest.fixture
def orden(org_a, user_profile, version):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=4001, tipo_trabajo_version=version,
        cliente_nombre="Cliente de prueba",
        estado_operativo=OrdenTrabajo.EN_SITIO)
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return o


@pytest.fixture
def evento(orden, user_profile):
    return EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="orden_creada", profile=user_profile,
        datos={"numero": orden.numero})


# --- lo que SI se puede -----------------------------------------------------

def test_crear_un_evento_funciona(orden, user_profile):
    e = EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="tecnico_asignado", profile=user_profile,
        datos={"a": 1})
    assert e.pk is not None
    assert EventoTrabajo.objects.filter(pk=e.pk).exists()


def test_se_pueden_agregar_varios(orden, user_profile):
    for tipo in ("orden_creada", "tecnico_asignado", "trabajo_iniciado"):
        EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                     profile=user_profile)
    assert EventoTrabajo.objects.filter(orden=orden).count() == 3


# --- lo que NO se puede -----------------------------------------------------

def test_guardar_encima_de_uno_existente_se_rechaza(evento):
    evento.tipo = "otra_cosa"
    with pytest.raises(ValidationError):
        evento.save()

    evento.refresh_from_db()
    assert evento.tipo == "orden_creada"


def test_cambiar_los_datos_se_rechaza(evento):
    """'datos' es donde vive que requisitos hay que corregir."""
    evento.datos = {"requisitos_a_corregir": []}
    with pytest.raises(ValidationError):
        evento.save()

    evento.refresh_from_db()
    assert evento.datos == {"numero": evento.orden.numero}


def test_borrar_una_instancia_se_rechaza(evento):
    with pytest.raises(ValidationError):
        evento.delete()
    assert EventoTrabajo.objects.filter(pk=evento.pk).exists()


def test_update_por_queryset_se_rechaza(evento):
    """El camino que se saltea 'save()' entero."""
    with pytest.raises(ValidationError):
        EventoTrabajo.objects.filter(pk=evento.pk).update(tipo="reescrito")

    evento.refresh_from_db()
    assert evento.tipo == "orden_creada"


def test_delete_por_queryset_se_rechaza(evento):
    with pytest.raises(ValidationError):
        EventoTrabajo.objects.filter(pk=evento.pk).delete()
    assert EventoTrabajo.objects.filter(pk=evento.pk).exists()


def test_borrado_masivo_de_toda_la_tabla_se_rechaza(evento):
    with pytest.raises(ValidationError):
        EventoTrabajo.objects.all().delete()
    assert EventoTrabajo.objects.count() == 1


def test_bulk_update_se_rechaza(evento):
    evento.tipo = "reescrito"
    with pytest.raises(ValidationError):
        EventoTrabajo.objects.bulk_update([evento], ["tipo"])

    evento.refresh_from_db()
    assert evento.tipo == "orden_creada"


def test_update_de_un_queryset_vacio_tambien_se_rechaza(orden):
    """No se permite "por si acaso no toca nada".

    Un update que hoy no encuentra filas es el mismo codigo que mañana, con
    otro filtro, si las encuentra. Lo que se prohibe es la operacion, no su
    resultado.
    """
    with pytest.raises(ValidationError):
        EventoTrabajo.objects.filter(tipo="no_existe_este_tipo").update(tipo="x")


# --- el limite conocido, escrito en vez de disimulado -----------------------

def test_la_cascada_SIGUE_llevandose_los_eventos(orden, user_profile):
    """LIMITE CONOCIDO, NO RESUELTO.

    'orden' es FK con on_delete=CASCADE. El colector de Django emite el DELETE
    al nivel de SQL, sin pasar por el modelo ni por el queryset, asi que borrar
    la orden borra su bitacora.

    Esta prueba afirma el comportamiento ACTUAL para que el limite quede
    medido. Cerrarlo exige decidir antes que significa una orden que no se
    puede borrar nunca --retencion legal, derecho de supresion, purga de datos
    de prueba-- y esa decision no se toma desde una linea de codigo.

    Si algun dia se cierra ese camino, esta prueba falla y obliga a mirar.
    """
    EventoTrabajo.objects.create(org=orden.org, orden=orden,
                                 tipo="orden_creada", profile=user_profile)
    assert EventoTrabajo.objects.filter(orden=orden).count() == 1

    OrdenTrabajo.objects.filter(pk=orden.pk).delete()

    assert EventoTrabajo.objects.count() == 0, (
        "la cascada ya no se lleva los eventos: el limite se cerro y hay que "
        "actualizar esta prueba y la documentacion del modelo")


# --- el admin -----------------------------------------------------------------

def test_el_admin_no_deja_tocar_la_bitacora():
    """La otra puerta: el panel de Django.

    Es la que mas importa en la practica, porque es la unica donde una persona
    ve la tabla y tiene un boton al lado.
    """
    from campo.admin import EventoTrabajoInline

    campos = set(EventoTrabajoInline.fields)
    solo_lectura = set(EventoTrabajoInline.readonly_fields)
    assert campos <= solo_lectura, (
        f"editables desde el admin: {sorted(campos - solo_lectura)}")
    assert EventoTrabajoInline.can_delete is False
    assert EventoTrabajoInline.has_add_permission(EventoTrabajoInline, None) is False
