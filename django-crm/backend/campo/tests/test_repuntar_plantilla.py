# -*- coding: utf-8 -*-
"""
================================================================================
 SOLO SE REPUNTA LO QUE NADIE EMPEZO  --  07/11/2026
================================================================================
Una orden congela su plantilla al nacer. El 07/11/2026 eso dejo 145 ordenes
abiertas colgando de una version del 21/10, anterior a las instrucciones de
foto corregidas y al rango bueno.

Repuntarlas es util y es peligroso: si la orden YA TIENE RESPUESTAS, cambiarle
el formulario debajo es exactamente lo que la inmutabilidad existe para
impedir.

QUE AFIRMA ESTA GUARDA
----------------------
  · que una orden sin empezar SI se mueva -- el efecto, no el mensaje
  · que una orden con CUALQUIER cosa escrita NO se mueva, por las tres vias:
    el estado, `datos`, y una evidencia subida
  · que sin `--aplicar` no se escriba una sola fila
  · que `revision` NO cambie (romperia la cola offline del tecnico)
  · que `updated_at` SI cambie (si no, la app no se entera y sigue con el
    formulario viejo en el equipo)
  · que la empresa de al lado no entre
  · y que el diff que se lee antes de aplicar diga lo que de verdad cambia
================================================================================
"""
from __future__ import annotations

from io import StringIO

import pytest

pytestmark = pytest.mark.django_db


def _tipo_con_dos_versiones(org, codigo="correctivo_fibra"):
    """Un tipo con v1 (vieja) y v2 (vigente), que difieren de verdad."""
    from campo.models import WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org, codigo=codigo, nombre="Soporte",
                                 labor="correctivo")
    vieja = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [],
                 "campos": [{"id": "potencia_al_salir", "tipo": "decimal",
                             "titulo": "Potencia al salir", "unidad": "dBm",
                             "reglas": {"min": -28.0, "max": -8.0}}]})
    vigente = WorkTypeVersion.objects.create(
        work_type=wt, version=2, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [],
                 "evidencias": [{"id": "dano_encontrado"}],
                 "campos": [{"id": "potencia_al_salir", "tipo": "decimal",
                             "titulo": "Potencia al salir", "unidad": "dBm",
                             "reglas": {"min": -60.0, "max": -8.0},
                             "bueno": {"min": -27.0, "max": -8.0}}]})
    return wt, vieja, vigente


def _orden(org, version, numero, **kw):
    from campo.models import OrdenTrabajo

    campos = dict(org=org, numero=numero, tipo_trabajo_version=version,
                  cliente_nombre="MARIO SABANAGRANDE",
                  estado_operativo=OrdenTrabajo.ASIGNADA,
                  origen_sistema="manual", contexto={}, datos={})
    campos.update(kw)
    return OrdenTrabajo.objects.create(**campos)


def _correr(org, aplicar=False, tipo=""):
    from django.core.management import call_command

    salida = StringIO()
    args = ["repuntar_plantilla", "--org", str(org.id)]
    if tipo:
        args += ["--tipo", tipo]
    if aplicar:
        args.append("--aplicar")
    call_command(*args, stdout=salida, stderr=salida)
    return salida.getvalue()


def _version_de(orden):
    orden.refresh_from_db()
    return orden.tipo_trabajo_version.version


# ---------------------------------------------------------------------------
#  LO QUE SI SE MUEVE
# ---------------------------------------------------------------------------

def test_una_orden_que_nadie_empezo_SE_MUEVE(org_a):
    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 401)

    _correr(org_a, aplicar=True)

    assert _version_de(orden) == 2


def test_SIN_aplicar_no_se_escribe_una_sola_fila(org_a):
    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 402)

    salida = _correr(org_a, aplicar=False)

    #  EL EFECTO, NO EL MENSAJE: que diga «SIMULACRO» no prueba que no
    #  escribio. Lo que lo prueba es la fila intacta.
    assert _version_de(orden) == 1
    assert "SIMULACRO" in salida


def test_una_orden_YA_en_la_vigente_no_se_cuenta(org_a):
    _, _, vigente = _tipo_con_dos_versiones(org_a)
    _orden(org_a, vigente, 403)

    salida = _correr(org_a, aplicar=False)

    assert "Nada que mover" in salida


# ---------------------------------------------------------------------------
#  LO QUE NO SE MUEVE  --  las tres vias
# ---------------------------------------------------------------------------

def test_una_orden_EN_SITIO_no_se_mueve(org_a):
    from campo.models import OrdenTrabajo

    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 404,
                   estado_operativo=OrdenTrabajo.EN_SITIO)

    _correr(org_a, aplicar=True)

    assert _version_de(orden) == 1


def test_una_orden_CON_RESPUESTAS_no_se_mueve(org_a):
    """El estado puede seguir en `asignada` y haber media hoja escrita."""
    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 405,
                   datos={"potencia_al_salir": "-21.0"})

    _correr(org_a, aplicar=True)

    assert _version_de(orden) == 1


def test_una_orden_CON_UNA_FOTO_SUBIDA_no_se_mueve(org_a):
    from campo.models import EvidenciaTrabajo

    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 406)
    EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=orden, requisito_id="dano_encontrado",
        vuelta=1, storage_key="k/406.jpg", nombre_original="IMG.jpg",
        mime_type="image/jpeg", bytes=12,
        sha256="406".ljust(64, "x")[:64],
        estado_archivo=EvidenciaTrabajo.VERIFICADO)

    _correr(org_a, aplicar=True)

    assert _version_de(orden) == 1


def test_una_orden_CERRADA_no_se_mueve(org_a):
    from campo.models import OrdenTrabajo

    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 407,
                   estado_operativo=OrdenTrabajo.CERRADA)

    _correr(org_a, aplicar=True)

    assert _version_de(orden) == 1


# ---------------------------------------------------------------------------
#  LO QUE NO SE TOCA DE LA FILA
# ---------------------------------------------------------------------------

def test_revision_NO_cambia(org_a):
    """Subirla rechazaria por vieja la escritura pendiente del tecnico."""
    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 408)
    antes = orden.revision

    _correr(org_a, aplicar=True)

    orden.refresh_from_db()
    assert orden.revision == antes
    assert orden.tipo_trabajo_version.version == 2, "no se movio nada"


def test_updated_at_SI_cambia(org_a):
    """Sin esto la app no se entera y el tecnico llena el formulario viejo."""
    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 409)
    antes = orden.updated_at

    _correr(org_a, aplicar=True)

    orden.refresh_from_db()
    assert orden.updated_at > antes


# ---------------------------------------------------------------------------
#  LA FRONTERA
# ---------------------------------------------------------------------------

def test_la_empresa_de_al_lado_no_entra(org_a, org_b):
    _, vieja_a, _ = _tipo_con_dos_versiones(org_a)
    _, vieja_b, _ = _tipo_con_dos_versiones(org_b)
    mia = _orden(org_a, vieja_a, 410)
    ajena = _orden(org_b, vieja_b, 411)

    _correr(org_a, aplicar=True)

    assert _version_de(mia) == 2
    assert _version_de(ajena) == 1, "se movio una orden de otra empresa"


def test_tipo_limita_a_ese_tipo(org_a):
    _, vieja_uno, _ = _tipo_con_dos_versiones(org_a, "correctivo_fibra")
    _, vieja_dos, _ = _tipo_con_dos_versiones(org_a, "retiro_equipos")
    fibra = _orden(org_a, vieja_uno, 412)
    retiro = _orden(org_a, vieja_dos, 413)

    _correr(org_a, aplicar=True, tipo="correctivo_fibra")

    assert _version_de(fibra) == 2
    assert _version_de(retiro) == 1


def test_un_tipo_SIN_version_publicada_no_rompe(org_a):
    from campo.models import WorkType, WorkTypeVersion

    wt, vieja, vigente = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 414)
    otro = WorkType.objects.create(org=org_a, codigo="vacio",
                                   nombre="Sin plantilla", labor="correctivo")
    WorkTypeVersion.objects.create(
        work_type=otro, version=1, schema_version=1,
        estado=WorkTypeVersion.BORRADOR, esquema={"campos": []})

    _correr(org_a, aplicar=True)

    assert _version_de(orden) == 2, "un tipo sin publicar freno a los demas"


# ---------------------------------------------------------------------------
#  EL DIFF QUE SE LEE ANTES DE APLICAR
# ---------------------------------------------------------------------------

def test_el_simulacro_DICE_QUE_CAMBIA_en_el_formulario(org_a):
    """Sin esto se mueven 145 ordenes a ciegas."""
    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    _orden(org_a, vieja, 415)

    salida = _correr(org_a, aplicar=False)

    assert "potencia_al_salir.reglas" in salida, salida
    assert "-60" in salida, salida
    assert "potencia_al_salir.bueno" in salida, salida
    assert "dano_encontrado" in salida, salida


def test_el_diff_nombra_un_campo_que_DESAPARECE(org_a):
    from campo.management.commands.repuntar_plantilla import diferencias

    lineas = diferencias({"campos": [{"id": "viejo"}]},
                         {"campos": [{"id": "nuevo"}]})

    assert any("+ campo nuevo: nuevo" in x for x in lineas), lineas
    assert any("- campo que ya no esta: viejo" in x for x in lineas), lineas


def test_dos_esquemas_iguales_no_inventan_cambios(org_a):
    from campo.management.commands.repuntar_plantilla import diferencias

    uno = {"campos": [{"id": "a", "tipo": "decimal"}], "evidencias": []}

    assert diferencias(uno, dict(uno)) == []


# ---------------------------------------------------------------------------
#  `sin_empezar` DIRECTO
#
#  No es redundante con las de arriba, y la mutacion lo probo: `candidatas()`
#  YA filtra por `asignada`, asi que borrar el chequeo de estado dentro de
#  `sin_empezar` no cambiaba nada y la mutacion sobrevivia a las 15 guardas.
#
#  Pero `sin_empezar` se vuelve a llamar BAJO BLOQUEO, sobre una fila releida,
#  donde el filtro del queryset ya no esta: ahi es la unica defensa. Un tecnico
#  que entra a la orden entre el listado y la escritura cae justo ahi.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("estado,esperado", [
    ("asignada", True),
    ("en_camino", False),
    ("en_sitio", False),
    ("completada_campo", False),
    ("cerrada", False),
    ("cancelada", False),
])
def test_sin_empezar_SOLO_dice_que_si_en_asignada(org_a, estado, esperado):
    from campo.management.commands.repuntar_plantilla import sin_empezar

    _, vieja, _ = _tipo_con_dos_versiones(org_a)
    orden = _orden(org_a, vieja, 420, estado_operativo=estado)

    assert sin_empezar(orden) is esperado
