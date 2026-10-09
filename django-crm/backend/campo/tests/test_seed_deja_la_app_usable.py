# -*- coding: utf-8 -*-
"""
El comando de datos de prueba deja la aplicación usable de punta a punta.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
`seed_campo_demo` es lo que corre cualquiera que quiera ver la aplicación
andando contra un backend local. Si siembra una sola orden, la mitad de las
pantallas queda sin nada que mostrar y no se puede distinguir "está vacío"
de "está roto".

Esta prueba afirma sobre lo que la aplicación necesita para que cada pantalla
tenga sentido, y sobre todo sobre el caso que hasta ahora no se podía ver: una
orden devuelta, con su lista de qué rehacer.

QUÉ MODO DEL COMANDO SE MIDE ACÁ
--------------------------------
El modo `--completo`. Por defecto el comando siembra **una** orden, porque
sembrar tres de una hacía imposible afirmar cuántas dejaba una corrida —dos
corridas dejaban seis y ninguna prueba podía distinguir «sembró de más» de
«sembró dos veces»—. Esa cuenta es lo que `test_seguridad_seed_y_admin` necesita
para cerrar el incidente del 08/09/2026, y manda sobre esto.

Lo que no cambió es lo que se afirma: que haya con qué llenar cada pantalla.
"""

import pytest
from django.core.management import call_command
from django.test import override_settings

from campo.models import OrdenTrabajo, WorkTypeVersion
from campo.services.validador import devolucion_vigente

pytestmark = pytest.mark.django_db


@pytest.fixture
def sembrado(org_a):
    """Lo que siembra el comando en su modo COMPLETO.

    POR QUE `--completo`, Y POR QUE `--org`
    ---------------------------------------
    Hasta el 06/10/2026 esta fixture llamaba al comando sin argumentos, y eso
    la ponia en contradiccion directa con `test_seguridad_seed_y_admin`: esa
    exige que sin `--org` el comando NO corra --porque el 08/09/2026 corrio
    contra produccion y se invento una empresa-- y que una corrida deje UNA
    orden, contable.

    Manda la de seguridad, por origen: nacio de un incidente con datos reales.
    Lo que esta prueba afirma --que haya con que llenar cada pantalla-- no
    cambia: es el modo en el que esa riqueza existe el que ahora se declara.
    """
    # `DEBUG=True` explicito: `crm.test_settings` corre con DEBUG apagado, y el
    # comando se niega ahi -- como debe. Que esta prueba haya tenido que
    # declararlo es la mejor evidencia de que esa guarda no es decorativa:
    # bloqueo una llamada que no la esperaba.
    with override_settings(DEBUG=True):
        call_command("seed_campo_demo", "--org", str(org_a.id), "--completo",
                     verbosity=0)
    return OrdenTrabajo.objects.filter(org=org_a)


def test_1_siembra_mas_de_una_orden_y_mas_de_un_tipo(sembrado):
    """Una sola orden no alcanza para ver una lista ni para filtrar."""
    assert sembrado.count() >= 3
    tipos = {o.tipo_trabajo_version.work_type.codigo for o in sembrado}
    assert len(tipos) >= 2, "con un solo tipo no se ve que el formulario cambia"


def test_2_hay_una_orden_devuelta_con_su_lista_de_que_rehacer(sembrado):
    """El caso que la aplicación no podía mostrar hasta ahora."""
    devuelta = sembrado.get(estado_operativo=OrdenTrabajo.CORRECCION_REQUERIDA)
    devolucion = devolucion_vigente(devuelta)

    assert devolucion is not None, "una orden devuelta sin devolución no sirve de ejemplo"
    assert devolucion["requisitos"] == ["foto_potencia"]
    assert devolucion["observacion"] != ""
    assert devuelta.vuelta == 2


def test_3_las_ordenes_traen_el_contexto_tecnico_del_despacho(sembrado):
    """Sin contexto, el plan del cliente en la pantalla queda de ejemplo."""
    con_contexto = [o for o in sembrado if o.contexto.get("contexto_disponible")]

    assert con_contexto, "ninguna orden trae el snapshot del despacho"
    for orden in con_contexto:
        assert orden.contexto["cliente"]["plan"]
        assert orden.contexto["capturado_en"], "un snapshot sin fecha no se puede leer"


def test_4_las_plantillas_traen_sus_pasos_y_son_distintas(sembrado):
    """El protocolo de atención sale del tipo de trabajo, no de la aplicación."""
    versiones = {o.tipo_trabajo_version for o in sembrado}
    pasos_por_version = {
        v.work_type.codigo: [p["titulo"] for p in v.esquema.get("pasos", [])]
        for v in versiones
    }

    for codigo, pasos in pasos_por_version.items():
        assert pasos, f"la plantilla {codigo} no trae pasos"

    listas = list(pasos_por_version.values())
    assert listas[0] != listas[1], "los dos tipos tienen el mismo procedimiento"


def test_5_todas_las_plantillas_sembradas_pasan_la_validacion(sembrado):
    """
    El seed no puede sembrar una plantilla que la aplicación no entienda: sería
    enseñar el error en vez de prevenirlo.
    """
    for version in WorkTypeVersion.objects.all():
        assert version.estado == WorkTypeVersion.PUBLICADA
        # `clean` valida el vocabulario cuando está publicada.
        version.clean()


def test_6_el_tecnico_ve_todas_sus_ordenes_por_la_api(user_client, sembrado):
    """
    El seed usa su propio técnico, así que acá solo se comprueba que el
    endpoint responde y pagina bien con lo sembrado.
    """
    r = user_client.get("/api/campo/trabajos/")

    assert r.status_code == 200
    assert "results" in r.json()
    assert "next_cursor" in r.json()


def test_7_el_rol_de_la_asignacion_es_uno_de_los_del_modelo(sembrado):
    """
    El seed escribía `tecnico_lider`, que no existe en el modelo. Django no lo
    valida al guardar, así que viajaba tal cual a la aplicación.
    """
    roles_validos = {"tecnico", "ayudante", "chofer", "supervisor"}
    for orden in sembrado:
        for asignacion in orden.asignaciones.all():
            assert asignacion.rol in roles_validos, asignacion.rol
