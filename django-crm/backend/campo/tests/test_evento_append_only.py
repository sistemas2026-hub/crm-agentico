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

def test_una_orden_con_bitacora_NO_se_puede_borrar(orden, user_profile):
    """CERRADO: 'orden' paso de CASCADE a PROTECT.

    Antes, borrar una OrdenTrabajo se llevaba su bitacora: el colector de
    Django emite el DELETE al nivel de SQL, sin pasar por el modelo ni por el
    queryset, asi que ninguno de los guards de arriba lo veia.

    PROTECT es la unica de las tres salidas que preserva la historia Y su
    relacion con la orden. No obliga a inventar nada: 'CANCELADA' ya existia en
    la maquina de estados y es terminal, asi que dar de baja una orden ya era
    posible sin borrarla. Y no rompe nada: no hay un solo '.delete()' sobre
    OrdenTrabajo en el codigo de produccion.
    """
    from django.db.models import ProtectedError

    EventoTrabajo.objects.create(org=orden.org, orden=orden,
                                 tipo="orden_creada", profile=user_profile)

    with pytest.raises(ProtectedError):
        OrdenTrabajo.objects.filter(pk=orden.pk).delete()

    assert EventoTrabajo.objects.filter(orden=orden).count() == 1
    assert OrdenTrabajo.objects.filter(pk=orden.pk).exists()


def test_una_orden_SIN_bitacora_si_se_puede_borrar(org_a, version):
    """PROTECT no convierte la tabla en intocable: protege lo que tiene historia."""
    suelta = OrdenTrabajo.objects.create(
        org=org_a, numero=4099, tipo_trabajo_version=version,
        cliente_nombre="Sin bitacora")
    OrdenTrabajo.objects.filter(pk=suelta.pk).delete()
    assert not OrdenTrabajo.objects.filter(pk=suelta.pk).exists()


def test_cancelar_es_el_camino_para_dar_de_baja(orden, user_profile):
    """La alternativa a borrar ya existia y es terminal."""
    from campo.models import OrdenTrabajo as OT
    from campo.services.transiciones import TRANSICIONES_PERMITIDAS

    assert OT.CANCELADA in TRANSICIONES_PERMITIDAS[OT.EN_SITIO]
    assert TRANSICIONES_PERMITIDAS[OT.CANCELADA] == set(), (
        "'cancelada' tiene que ser terminal para servir de baja logica")


def test_LIMITE_borrar_la_ORGANIZACION_sigue_arrastrando_todo(orden, user_profile):
    """LIMITE CONOCIDO, MEDIDO, PENDIENTE DE DECISION.

    'EventoTrabajo.org' sigue en CASCADE. Con 'orden' en PROTECT, borrar una
    organizacion entera choca contra la proteccion en vez de arrastrar la
    bitacora -- que es un efecto util, pero no es una politica de retencion.

    Borrar una empresa toca derecho de supresion, retencion legal y purga de
    datos de prueba a la vez. Esa decision no se toma desde un 'on_delete', y
    por eso 'org' no se cambio. Esta prueba mide el camino tal como esta hoy:
    si algun dia se define la politica, falla y obliga a actualizarla.
    """
    from django.db.models import ProtectedError

    from common.models import Org

    EventoTrabajo.objects.create(org=orden.org, orden=orden,
                                 tipo="orden_creada", profile=user_profile)

    # Hoy esto NO borra en silencio: la proteccion de 'orden' lo detiene antes.
    with pytest.raises(ProtectedError):
        Org.objects.filter(pk=orden.org_id).delete()

    assert EventoTrabajo.objects.count() == 1


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


# --- los caminos que se saltean el queryset ---------------------------------
#
# La auditoria pidio distinguir tres cosas que no son la misma, y tiene razon:
#
#   inmutable por ORM          lo que hay hoy: update/delete/bulk_update y
#                              save() sobre una fila existente estan cerrados
#   protegido frente a cascada   NO lo esta: ver el test de la cascada
#   inmutable en PostgreSQL      NO lo esta: SQL crudo escribe igual
#
# Llamarlo "append-only real" seria mentir. Es "append-only por ORM".

def test_bulk_create_con_update_conflicts_no_reescribe(evento):
    """El upsert de Django: bulk_create(update_conflicts=True).

    Es el camino menos obvio para reescribir una fila y no pasa por save() ni
    por update(). Si algun dia alguien lo usa sobre esta tabla, esta prueba
    dice que paso.
    """
    gemelo = EventoTrabajo(org=evento.org, orden=evento.orden, tipo="reescrito",
                           profile=evento.profile, datos={"pisado": True})
    gemelo.pk = evento.pk

    with pytest.raises(ValidationError):
        EventoTrabajo.objects.bulk_create(
            [gemelo], update_conflicts=True,
            update_fields=["tipo", "datos"], unique_fields=["id"])

    evento.refresh_from_db()
    assert evento.tipo == "orden_creada", (
        "bulk_create(update_conflicts=True) reescribio un evento")
    assert evento.datos == {"numero": evento.orden.numero}


def test_update_or_create_sobre_una_fila_existente_se_rechaza(evento):
    """'update_or_create' termina llamando save() sobre la instancia hallada."""
    from django.core.exceptions import ValidationError as VE

    with pytest.raises((VE, Exception)):
        EventoTrabajo.objects.update_or_create(
            pk=evento.pk, defaults={"tipo": "reescrito"})

    evento.refresh_from_db()
    assert evento.tipo == "orden_creada"


def test_el_manager_por_defecto_es_el_protegido():
    """Si alguien agrega otro manager primero, este deja de proteger."""
    from campo.models import EventoTrabajoQuerySet

    assert isinstance(EventoTrabajo.objects.all(), EventoTrabajoQuerySet)
    assert isinstance(EventoTrabajo._default_manager.all(), EventoTrabajoQuerySet)


def test_LIMITE_el_base_manager_no_esta_protegido(evento):
    """LIMITE CONOCIDO, MEDIDO, NO CERRADO.

    Django usa '_base_manager' --un Manager plano-- para resolver relaciones y
    para el colector de borrado. Ese camino NO pasa por EventoTrabajoQuerySet.

    Esta prueba afirma el comportamiento ACTUAL. No es una aprobacion: es la
    diferencia entre "inmutable por ORM" y "inmutable de verdad", escrita donde
    se ve. Cerrarlo exige enforcement en PostgreSQL (un trigger), que es la
    misma decision de retencion que la cascada.
    """
    EventoTrabajo._base_manager.filter(pk=evento.pk).update(tipo="por_la_puerta_de_atras")
    evento.refresh_from_db()
    assert evento.tipo == "por_la_puerta_de_atras", (
        "el _base_manager ya esta protegido: se cerro el limite y hay que "
        "actualizar esta prueba y la documentacion del modelo")


def test_LIMITE_el_sql_crudo_escribe_igual(evento):
    """LIMITE CONOCIDO, MEDIDO, NO CERRADO.

    Ningun guard de Python puede impedir un UPDATE por SQL. Queda escrito para
    que nadie lea "append-only" y entienda una garantia que no existe.
    """
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("update campo_evento_trabajo set tipo = %s where id = %s",
                    ["por_sql", str(evento.pk)])

    evento.refresh_from_db()
    assert evento.tipo == "por_sql", (
        "el SQL crudo ya no puede: hay enforcement en la base y hay que "
        "actualizar esta prueba")


def test_crear_en_lote_sin_upsert_sigue_funcionando(orden, user_profile):
    """Bloquear el upsert no puede romper la creacion en lote."""
    nuevos = [EventoTrabajo(org=orden.org, orden=orden, tipo=f"evento_{i}",
                            profile=user_profile)
              for i in range(3)]
    EventoTrabajo.objects.bulk_create(nuevos)
    assert EventoTrabajo.objects.filter(orden=orden).count() == 3
