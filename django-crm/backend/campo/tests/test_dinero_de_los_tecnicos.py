# -*- coding: utf-8 -*-
"""El dinero que recibe el tecnico (26/11/2026). Ver campo/dinero.py.

El usuario: «falta registrar el dinero que recibe el tecnico». Cobra la
instalacion y los equipos o el material extra, solo en efectivo, escribe cuanto
recibio, y la oficina ve cuanto debe entregar cada tecnico y marca recibido.

  A  LA PLANTILLA -- un numero con la marca `dinero`, que no se pierde al
     volver a publicar y no admite negativos.
  B  LO QUE VE LA OFICINA -- por tecnico, por orden y por concepto; sin
     ceros, sin canceladas, sin otra empresa.
  C  RECIBIR -- con la cifra que se vio; dos veces no; una cifra que cambio
     no; la orden de otro tecnico no.
  D  QUIEN -- solo gestion.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from campo import plantillas as P
from campo.dinero import EntregaDeDinero, campos_de_dinero, por_tecnico
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services.validador import validar_campos_tecnicos
from common.models import Profile

pytestmark = pytest.mark.django_db

URL = "/api/campo/dinero/"
URL_RECIBIR = "/api/campo/dinero/recibir/"

DEFINICION = {
    "campos": [
        {"titulo": "Serial de la ONU", "tipo": "texto"},
        {"titulo": "Valor de la instalación", "tipo": "numero", "dinero": True,
         "paso": "Configuración y entrega"},
        {"titulo": "Equipos o material extra", "tipo": "numero", "dinero": True,
         "obligatorio": False, "paso": "Configuración y entrega"},
        {"titulo": "Metros de fibra", "tipo": "numero"},
    ],
    "evidencias": [{"titulo": "ONU instalada"}],
}


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="instalacion_fibra",
                                 nombre="Instalación de fibra", labor="instalacion")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema=P.componer(DEFINICION))


@pytest.fixture
def otro_tecnico(org_a):
    u = get_user_model().objects.create_user(email="tecnico2@test.com", password="x")
    u.name = "Dilan Moreno"
    u.save()
    return Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)


def _ids(version):
    return {c["titulo"]: c["id"] for c in version.esquema["campos"]}


def _orden(org, version, tecnico, numero, instalacion=None, extra=None, **kw):
    ids = _ids(version)
    datos = {}
    if instalacion is not None:
        datos[ids["Valor de la instalación"]] = instalacion
    if extra is not None:
        datos[ids["Equipos o material extra"]] = extra
    datos[ids["Metros de fibra"]] = 120   # no es dinero: no suma
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre=f"CLIENTE {numero}", estado_operativo=kw.get("estado", OrdenTrabajo.ASIGNADA),
        revision=1, datos=datos)
    if tecnico is not None:
        AsignacionTrabajo.objects.create(orden=o, profile=tecnico, rol="tecnico_lider",
                                         es_principal=True)
    return o


def _recibir(cliente, tecnico, *pares):
    return cliente.post(URL_RECIBIR, {"tecnico_id": str(tecnico.id), "ordenes": [
        {"orden_id": str(o.id), "monto": m} for o, m in pares]}, format="json")


# =========================================================================== #
#  A. LA PLANTILLA
# =========================================================================== #
def test_a1_la_marca_DINERO_llega_al_esquema_con_minimo_cero():
    esquema = P.componer(DEFINICION)
    dinero = [c for c in esquema["campos"] if c.get("dinero")]
    assert [c["titulo"] for c in dinero] == ["Valor de la instalación", "Equipos o material extra"]
    assert all(c["reglas"]["min"] == 0 for c in dinero), "la plata no es negativa"
    assert [c["titulo"] for c in campos_de_dinero(esquema)] == [
        "Valor de la instalación", "Equipos o material extra"]


def test_a2_la_marca_NO_SE_PIERDE_al_abrir_y_volver_a_publicar():
    definicion, _ = P.leer_definicion(P.componer(DEFINICION))
    marcados = [c["titulo"] for c in definicion["campos"] if c.get("dinero")]
    assert marcados == ["Valor de la instalación", "Equipos o material extra"]
    assert campos_de_dinero(P.componer(definicion)) == campos_de_dinero(P.componer(DEFINICION))


def test_a3_un_monto_NEGATIVO_no_se_guarda(version):
    cid = _ids(version)["Valor de la instalación"]
    _, errores = validar_campos_tecnicos(version.esquema, {cid: -5000})
    assert cid in errores
    _, errores = validar_campos_tecnicos(version.esquema, {cid: 80000})
    assert not errores


# =========================================================================== #
#  B. LO QUE VE LA OFICINA
# =========================================================================== #
def test_b1_POR_TECNICO_por_orden_y_por_concepto(admin_client, version, user_profile,
                                                otro_tecnico, org_a):
    _orden(org_a, version, user_profile, 11, instalacion=80000, extra=25000)
    _orden(org_a, version, user_profile, 12, instalacion=50000)
    _orden(org_a, version, otro_tecnico, 13, instalacion=80000)
    r = admin_client.get(URL)
    assert r.status_code == 200, r.content
    d = r.json()
    assert d["configurado"] is True
    por_nombre = {t["tecnico"]["id"]: t for t in d["tecnicos"]}
    uno = por_nombre[str(user_profile.id)]
    assert uno["pendiente"] == 155000, "80.000 + 25.000 + 50.000"
    assert [o["numero"] for o in uno["ordenes"]] == [11, 12]
    assert uno["ordenes"][0]["conceptos"] == [
        {"titulo": "Valor de la instalación", "valor": 80000},
        {"titulo": "Equipos o material extra", "valor": 25000}]
    assert por_nombre[str(otro_tecnico.id)]["tecnico"]["nombre"] == "Dilan Moreno"
    assert d["tecnicos"][0]["tecnico"]["id"] == str(user_profile.id), "el que más debe, primero"


def test_b2_SIN_COBRO_canceladas_y_otra_empresa_no_salen(admin_client, version, user_profile,
                                                        org_a, org_b):
    _orden(org_a, version, user_profile, 21, instalacion=0)
    _orden(org_a, version, user_profile, 22)
    _orden(org_a, version, user_profile, 23, instalacion=80000, estado=OrdenTrabajo.CANCELADA)
    wt_b = WorkType.objects.create(org=org_b, codigo="instalacion_fibra", nombre="I", labor="instalacion")
    v_b = WorkTypeVersion.objects.create(work_type=wt_b, version=1, schema_version=1,
                                         estado=WorkTypeVersion.PUBLICADA,
                                         esquema=P.componer(DEFINICION))
    _orden(org_b, v_b, None, 24, instalacion=90000)
    assert admin_client.get(URL).json()["tecnicos"] == []


def test_b3_una_empresa_SIN_campos_de_dinero_lo_dice(admin_client):
    d = admin_client.get(URL).json()
    assert d == {"configurado": False, "tecnicos": [], "ultimas": []}


# =========================================================================== #
#  C. RECIBIR
# =========================================================================== #
def test_c1_RECIBIR_deja_la_entrega_escrita_y_el_pendiente_en_cero(
        admin_client, admin_profile, version, user_profile, org_a):
    a = _orden(org_a, version, user_profile, 31, instalacion=80000, extra=25000)
    b = _orden(org_a, version, user_profile, 32, instalacion=50000)
    r = _recibir(admin_client, user_profile, (a, 105000), (b, 50000))
    assert r.status_code == 200, r.content
    assert r.json()["recibidas"] == 2 and r.json()["tecnicos"] == []
    e = EntregaDeDinero.objects.get(orden=a)
    assert e.monto == Decimal("105000") and e.tecnico == user_profile
    assert e.recibido_por == admin_profile and e.recibido_en is not None
    ultima = r.json()["ultimas"][0]
    assert ultima["orden_numero"] in (31, 32) and ultima["monto"] in (105000, 50000)


def test_c2_DOS_VECES_no_se_recibe(admin_client, version, user_profile, org_a):
    a = _orden(org_a, version, user_profile, 41, instalacion=80000)
    assert _recibir(admin_client, user_profile, (a, 80000)).status_code == 200
    r = _recibir(admin_client, user_profile, (a, 80000))
    assert r.status_code == 409 and "ya no tiene dinero por entregar" in r.json()["detail"]
    assert EntregaDeDinero.objects.filter(orden=a).count() == 1


def test_c3_UNA_CIFRA_QUE_CAMBIO_no_se_recibe_y_no_queda_nada_a_medias(
        admin_client, version, user_profile, org_a):
    a = _orden(org_a, version, user_profile, 51, instalacion=80000)
    b = _orden(org_a, version, user_profile, 52, instalacion=50000)
    #  La pantalla mostraba 70.000 en la 52; el técnico la corrigió a 50.000.
    r = _recibir(admin_client, user_profile, (a, 80000), (b, 70000))
    assert r.status_code == 409 and "OT-52 cambió" in r.json()["detail"]
    assert "50.000" in r.json()["detail"]
    assert not EntregaDeDinero.objects.exists(), "todo o nada: la 51 tampoco"


def test_c4_si_el_tecnico_CORRIGE_DESPUES_de_entregar_aparece_la_diferencia(
        admin_client, version, user_profile, org_a):
    a = _orden(org_a, version, user_profile, 61, instalacion=80000)
    assert _recibir(admin_client, user_profile, (a, 80000)).status_code == 200
    cid = _ids(version)["Equipos o material extra"]
    OrdenTrabajo.objects.filter(pk=a.pk).update(datos={**a.datos, cid: 30000})
    t = admin_client.get(URL).json()["tecnicos"][0]
    assert t["pendiente"] == 30000
    o = t["ordenes"][0]
    assert (o["cobrado"], o["entregado"], o["pendiente"]) == (110000, 80000, 30000)


def test_c5_LA_ORDEN_DE_OTRO_TECNICO_no_se_recibe_a_nombre_de_este(
        admin_client, version, user_profile, otro_tecnico, org_a):
    a = _orden(org_a, version, otro_tecnico, 71, instalacion=80000)
    r = _recibir(admin_client, user_profile, (a, 80000))
    assert r.status_code == 400 and "no es de ese técnico" in r.json()["detail"]
    assert not EntregaDeDinero.objects.exists()


@pytest.mark.parametrize("cuerpo", [
    {}, {"tecnico_id": "x", "ordenes": []}, {"tecnico_id": "x", "ordenes": "todas"},
    {"tecnico_id": "x", "ordenes": [{"monto": 5}]},
    {"tecnico_id": "x", "ordenes": [{"orden_id": "y", "monto": True}]},
    {"tecnico_id": "x", "ordenes": [{"orden_id": "y", "monto": "mucho"}]},
])
def test_c6_un_pedido_mal_formado_se_rechaza_sin_romper(admin_client, cuerpo):
    assert admin_client.post(URL_RECIBIR, cuerpo, format="json").status_code == 400


def test_c7_la_orden_de_OTRA_EMPRESA_no_se_recibe(admin_client, version, user_profile,
                                                 org_b):
    wt_b = WorkType.objects.create(org=org_b, codigo="i", nombre="I", labor="instalacion")
    v_b = WorkTypeVersion.objects.create(work_type=wt_b, version=1, schema_version=1,
                                         estado=WorkTypeVersion.PUBLICADA,
                                         esquema=P.componer(DEFINICION))
    ajena = _orden(org_b, v_b, None, 81, instalacion=80000)
    r = _recibir(admin_client, user_profile, (ajena, 80000))
    assert r.status_code == 400 and "no es de tu empresa" in r.json()["detail"]


# =========================================================================== #
#  D. QUIEN
# =========================================================================== #
def test_d1_un_TECNICO_no_ve_ni_recibe(user_client, version, user_profile, org_a):
    a = _orden(org_a, version, user_profile, 91, instalacion=80000)
    assert user_client.get(URL).status_code == 403
    assert _recibir(user_client, user_profile, (a, 80000)).status_code == 403
    assert not EntregaDeDinero.objects.exists()


def test_d2_por_tecnico_no_mezcla_empresas(version, user_profile, org_a, org_b):
    _orden(org_a, version, user_profile, 92, instalacion=80000)
    assert por_tecnico(org_b) == {"configurado": False, "tecnicos": [], "ultimas": []}
