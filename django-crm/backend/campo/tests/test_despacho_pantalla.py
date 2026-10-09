# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE LA PANTALLA DE DESPACHO NECESITA PARA EXISTIR
================================================================================

Que cubre y por que
-------------------
`POST /campo/trabajos/crear/` existia desde siempre y **nadie lo llamaba**:
verificado el 09/10/2026 en frontend, app movil, motor y scripts, sin una sola
referencia. Las ordenes solo se podian crear por API directa, asi que el
circuito estaba cortado justo al principio -- el ciclo de la madrugada reparte
ordenes y la clasificacion propone su tipo, y nada de eso se ejercita si no hay
por donde decir «este caso va a campo».

Se afirma sobre el EFECTO:

  - solo se ofrecen plantillas PUBLICADAS: una borrador cambia debajo del
    tecnico, y `despachar()` ya la rechaza -- ofrecerla seria dejar elegir algo
    que va a fallar al enviar
  - UNA por tipo de trabajo, la version mas alta: dos versiones del mismo tipo
    son, para quien despacha, la misma cosa
  - las plantillas sin labor se CUENTAN, porque sus ordenes no entran al
    reparto automatico
  - un caso que ya tiene orden viva lo DICE, y no se bloquea: una segunda
    visita es legitima
  - la ficha se pide, no viene sola: es una llamada al motor POR CASO
  - nada de esto escribe

    pytest campo/tests/test_despacho_pantalla.py
================================================================================
"""

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

PLANTILLAS = "/api/campo/plantillas-de-trabajo/"
CASOS = "/api/campo/casos-despachables/"


def _tipo(org, codigo, labor="", activo=True):
    return WorkType.objects.create(org=org, codigo=codigo,
                                   nombre=codigo.upper(), labor=labor,
                                   activo=activo)


def _version(tipo, numero=1, estado=None):
    return WorkTypeVersion.objects.create(
        work_type=tipo, version=numero,
        estado=estado or WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "foto", "tipo": "foto"}]},
    )


# ---------------------------------------------------------------------------
# A · con qué se puede despachar
# ---------------------------------------------------------------------------

def test_a_solo_se_ofrecen_las_PUBLICADAS(admin_client, org_a):
    """Una borrador puede cambiar debajo del técnico y el backend la rechaza."""
    _version(_tipo(org_a, "ftth", "instalacion"))
    _version(_tipo(org_a, "borrador"), estado=WorkTypeVersion.BORRADOR)

    cuerpo = admin_client.get(PLANTILLAS).json()
    assert [p["codigo"] for p in cuerpo["plantillas"]] == ["ftth"]


def test_b_una_sola_version_por_tipo_la_mas_alta(admin_client, org_a):
    """Dos versiones del mismo tipo son, para quien despacha, la misma cosa."""
    tipo = _tipo(org_a, "ftth", "instalacion")
    _version(tipo, 1)
    _version(tipo, 2)

    cuerpo = admin_client.get(PLANTILLAS).json()
    assert len(cuerpo["plantillas"]) == 1
    assert cuerpo["plantillas"][0]["version"] == 2


def test_c_la_labor_viaja_con_cada_plantilla(admin_client, org_a):
    """Es lo que permite marcar cuál coincide con la sugerencia."""
    _version(_tipo(org_a, "soporte", "correctivo"))

    p = admin_client.get(PLANTILLAS).json()["plantillas"][0]
    assert p["labor"] == "correctivo"
    assert p["requisitos"] == 1


def test_d_las_SIN_LABOR_se_cuentan(admin_client, org_a):
    """Sus órdenes no entran al reparto automático, y eso hay que saberlo
    donde se despacha, no solo en la pantalla de configuración."""
    _version(_tipo(org_a, "ftth", "instalacion"))
    _version(_tipo(org_a, "retiro", ""))

    cuerpo = admin_client.get(PLANTILLAS).json()
    assert cuerpo["sin_clasificar"] == 1


def test_e_un_tipo_dado_de_baja_no_se_ofrece(admin_client, org_a):
    _version(_tipo(org_a, "viejo", "correctivo", activo=False))
    assert admin_client.get(PLANTILLAS).json()["plantillas"] == []


def test_f_las_plantillas_de_OTRA_empresa_no_entran(admin_client, org_b):
    _version(_tipo(org_b, "ajena", "correctivo"))
    assert admin_client.get(PLANTILLAS).json()["plantillas"] == []


# ---------------------------------------------------------------------------
# B · qué casos esperan
# ---------------------------------------------------------------------------

def _caso(org, nombre="Sin internet", **extra):
    from cases.models import Case

    campos = {"org": org, "name": nombre, "status": "New",
              "priority": "Normal", "is_active": True}
    campos.update(extra)
    return Case.objects.create(**campos)


def test_g_los_casos_abiertos_se_listan(admin_client, org_a):
    _caso(org_a, "Sin internet")
    cuerpo = admin_client.get(CASOS).json()
    assert [c["nombre"] for c in cuerpo["casos"]] == ["Sin internet"]


def test_h_un_caso_CERRADO_no_entra(admin_client, org_a):
    _caso(org_a, "Ya resuelto", status="Closed")
    assert admin_client.get(CASOS).json()["casos"] == []


def test_i_un_caso_de_EJEMPLO_no_entra(admin_client, org_a):
    """Los de muestra son del seed y despacharlos manda a nadie a ningún lado."""
    _caso(org_a, "De muestra", is_sample=True)
    assert admin_client.get(CASOS).json()["casos"] == []


def test_j_los_de_OTRA_empresa_no_entran(admin_client, org_b):
    """El aislamiento NO depende del filtro de esta vista: lo da el RLS.

    Medido: crear un caso de otra empresa desde esta sesion ni siquiera se
    puede --`new row violates row-level security policy`--, asi que la
    garantia esta una capa mas abajo que el `.filter(org=org)`. Se afirma eso
    y no "no aparece en la lista", que seria probar la capa mas debil de las
    dos.
    """
    from django.db.utils import ProgrammingError

    with pytest.raises(ProgrammingError, match="row-level security"):
        _caso(org_b, "Ajeno")


def test_k_un_caso_con_orden_VIVA_lo_dice_y_no_se_bloquea(
    admin_client, org_a
):
    """Una segunda visita al mismo caso es legítima.

    El técnico fue y faltó un material, o el cliente no estaba. Lo que evita el
    duplicado accidental es la `Idempotency-Key`; esto es para que quien
    despacha lo VEA antes, que es distinto de que el sistema decida por él.
    """
    caso = _caso(org_a, "Con orden")
    version = _version(_tipo(org_a, "ftth", "instalacion"))
    OrdenTrabajo.objects.create(
        org=org_a, numero=77, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA,
        origen_sistema="crm", origen_ref=str(caso.id),
    )

    fila = admin_client.get(CASOS).json()["casos"][0]
    assert fila["orden_activa"] == 77


def test_l_una_orden_CERRADA_ya_no_cuenta_como_viva(admin_client, org_a):
    caso = _caso(org_a, "Con orden cerrada")
    version = _version(_tipo(org_a, "ftth", "instalacion"))
    OrdenTrabajo.objects.create(
        org=org_a, numero=78, tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.CERRADA,
        origen_sistema="crm", origen_ref=str(caso.id),
    )

    assert admin_client.get(CASOS).json()["casos"][0]["orden_activa"] is None


def test_m_la_ficha_SE_PIDE_no_viene_sola(admin_client, org_a, monkeypatch):
    """Es una llamada al motor POR CASO, que a su vez habla con WispHub y
    SmartOLT. Abrir la lista no puede costar veinticinco viajes de red."""
    from campo import despacho_pantalla_views as vistas

    pedidas = []
    monkeypatch.setattr(
        vistas.CasosDespachablesView, "_sugerencia_de",
        lambda self, caso: pedidas.append(caso.id) or {"labor": "correctivo"},
    )
    _caso(org_a, "Sin internet")

    sin = admin_client.get(CASOS).json()["casos"][0]
    assert sin["sugerencia"] is None
    assert pedidas == []

    con = admin_client.get(f"{CASOS}?ficha=1").json()["casos"][0]
    assert con["sugerencia"]["labor"] == "correctivo"
    assert len(pedidas) == 1


def test_n_un_caso_que_no_se_pudo_evaluar_no_deja_sin_lista_a_los_otros(
    admin_client, org_a, monkeypatch
):
    from campo import despacho_pantalla_views as vistas

    def explota(self, caso):
        raise RuntimeError("el motor no responde")

    monkeypatch.setattr(vistas.CasosDespachablesView, "_sugerencia_de", explota)
    _caso(org_a, "Uno")
    _caso(org_a, "Dos")

    #  La excepcion se rompe A PROPOSITO desde fuera de `_sugerencia_de`, que
    #  es donde su propio try no llega: un import roto o un cambio de firma
    #  caen asi. La lista tiene que seguir saliendo.
    cuerpo = admin_client.get(f"{CASOS}?ficha=1").json()
    assert sorted(c["nombre"] for c in cuerpo["casos"]) == ["Dos", "Uno"]
    assert all(c["sugerencia"] is None for c in cuerpo["casos"])


def test_o_NADA_de_esto_escribe(admin_client, org_a):
    """Son dos lecturas. El despacho sigue siendo `trabajos/crear/`."""
    _version(_tipo(org_a, "ftth", "instalacion"))
    _caso(org_a, "Sin internet")

    antes = OrdenTrabajo.objects.count()
    admin_client.get(PLANTILLAS)
    admin_client.get(CASOS)
    assert OrdenTrabajo.objects.count() == antes
