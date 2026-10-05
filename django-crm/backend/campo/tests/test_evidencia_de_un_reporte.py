# -*- coding: utf-8 -*-
"""La foto que pertenece a un reporte de la bitacora, y no al checklist.

POR QUE SON DOS COSAS Y NO UNA
------------------------------
Hasta la Fase 4 una evidencia satisfacia un REQUISITO DE CIERRE: el checklist
pregunta "¿existe evidencia de 'foto_ont'?" para decidir si el trabajo se puede
dar por terminado. Esa pregunta no admite que cualquier foto cuente.

Una foto de un BLOQUEO contesta otra cosa: hace creible una frase. "La casa esta
cerrada" con la puerta fotografiada no es lo mismo que sin ella. No satisface
ningun requisito de cierre, y si se guardara como si lo hiciera, un trabajo
bloqueado quedaria dando por cumplido algo que nadie cumplio.

LO QUE ESTE ARCHIVO DEFIENDE
----------------------------
1. **La foto de un reporte se valida contra el SNAPSHOT de ese reporte**, no
   contra el esquema vigente. Es la misma regla que ya rige los campos: una
   version nueva del tipo de trabajo no puede volver invalida la foto que el
   tecnico saco siguiendo lo que la app le mostro ese dia.

2. **El deduplicado del checklist sigue intacto.** Agregar `evento` a la
   constraint original la habria apagado en silencio -- en PostgreSQL NULL no es
   igual a NULL -- y ninguna prueba vieja lo habria dicho. Se afirma en las dos
   direcciones: la misma foto del mismo requisito del checklist entra UNA vez; la
   misma foto en DOS reportes distintos entra DOS veces, porque son dos hechos.

3. **Un `evento_id` de otra orden se rechaza.** Con solo un id, una foto podria
   colgarse del reporte de otra empresa.

4. **La linea de tiempo no filtra la ruta del archivo ni el GPS del telefono.**
   La fila lleva `storage_key` y `metadatos_captura`; ninguna de las dos tiene
   nada que hacer en una pantalla.
"""

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIClient

from campo.models import (
    AsignacionTrabajo,
    EvidenciaTrabajo,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from campo.services import seguimiento_campo as seg
from common.models import Profile
from common.serializer import OrgAwareRefreshToken

pytestmark = pytest.mark.django_db


#: Un tipo de trabajo que pide UNA foto en el bloqueo y otra en el inicio. Los
#: nombres son de una empresa inventada: ninguno esta en el codigo del motor.
ESQUEMA = {
    "pasos": [],
    "campos": [],
    # El checklist de la orden, que es OTRA lista y vive en otro lado.
    "evidencias": [{"id": "foto_acta", "titulo": "Acta firmada", "tipo": "foto"}],
    "seguimiento": {
        "inicio": {
            "campos": [
                {
                    "id": "nota",
                    "titulo": "Qué se encontró",
                    "tipo": "texto",
                    "reglas": {"required": True},
                }
            ],
            "evidencias": [
                {"id": "foto_fachada", "titulo": "Foto de la fachada", "tipo": "foto"}
            ],
        },
        "bloqueo": {
            "campos": [
                {
                    "id": "motivo",
                    "titulo": "Por qué no se puede seguir",
                    "tipo": "texto",
                    "reglas": {"required": True},
                }
            ],
            "evidencias": [
                {
                    "id": "foto_del_obstaculo",
                    "titulo": "Foto de lo que impide seguir",
                    "tipo": "foto",
                }
            ],
        },
    },
}

#: El mismo tipo de trabajo, una version despues, SIN la foto del bloqueo. Sirve
#: para la prueba que importa: lo que ya se registro no cambia de reglas.
ESQUEMA_V2 = {
    "pasos": [],
    "campos": [],
    "evidencias": [],
    "seguimiento": {
        "bloqueo": {
            "campos": [
                {
                    "id": "motivo",
                    "titulo": "Por qué no se puede seguir",
                    "tipo": "texto",
                    "reglas": {"required": True},
                }
            ],
            "evidencias": [],
        }
    },
}


def _cliente(user, org, profile):
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(user, org, profile)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c


@pytest.fixture
def tecnico(org_a, django_user_model):
    user = django_user_model.objects.create_user(
        email="tecnico.evid@test.com", password="testpass123"
    )
    profile = Profile.objects.create(user=user, org=org_a, role="USER", is_active=True)
    return user, profile


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_evid", nombre="FTTH")
    return WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=ESQUEMA,
        schema_hash="hash-evid-v1",
    )


def _orden(org, version, profile, numero=7101):
    o = OrdenTrabajo.objects.create(
        org=org,
        numero=numero,
        tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzon",
        cliente_direccion="Calle 50 # 10-20",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        revision=1,
    )
    AsignacionTrabajo.objects.create(
        orden=o, profile=profile, rol="tecnico", es_principal=True
    )
    return o


@pytest.fixture
def orden(org_a, version, tecnico):
    return _orden(org_a, version, tecnico[1])


def _registrar_bloqueo(orden, profile, motivo="La casa está cerrada"):
    return seg.registrar(
        orden, profile=profile, momento=seg.BLOQUEO, respuestas={"motivo": motivo}
    )


def _subir(cliente, orden, *, requisito, sha, evento=None, nombre="foto.jpg"):
    cuerpo = {
        "requisito_id": requisito,
        "nombre": nombre,
        "mime_type": "image/jpeg",
        "bytes": 120_000,
        "sha256": sha,
    }
    if evento is not None:
        cuerpo["evento_id"] = str(evento.id)
    return cliente.post(
        f"/api/campo/trabajos/{orden.id}/evidencias/", cuerpo, format="json"
    )


# --------------------------------------------------------------------------- #
# A. El reporte guarda QUE foto se le pedia
# --------------------------------------------------------------------------- #

def test_a_el_reporte_congela_la_evidencia_que_se_le_pedia(orden, tecnico):
    evento = _registrar_bloqueo(orden, tecnico[1])

    declaradas = (evento.datos or {}).get("evidencias")
    assert [e["id"] for e in declaradas] == ["foto_del_obstaculo"]


def test_b_sin_declaracion_la_lista_queda_vacia_y_no_falta_la_clave(
    org_a, tecnico, version
):
    """Vacia no es ausente: quien lee tiene que poder distinguirlas."""
    wt = WorkType.objects.create(org=org_a, codigo="pelado", nombre="Pelado")
    v = WorkTypeVersion.objects.create(
        work_type=wt,
        version=1,
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )
    o = _orden(org_a, v, tecnico[1], numero=7102)

    evento = seg.registrar(
        o, profile=tecnico[1], momento=seg.AVANCE, respuestas={"nota": "sigo"}
    )

    assert (evento.datos or {}).get("evidencias") == []


# --------------------------------------------------------------------------- #
# B. La foto se valida contra el snapshot, no contra el esquema de hoy
# --------------------------------------------------------------------------- #

def test_c_una_version_nueva_no_invalida_la_foto_de_un_reporte_viejo(
    orden, tecnico, version
):
    """LA PRUEBA QUE SOSTIENE LA DECISION.

    Se registra el bloqueo con la version que SI pedia la foto, despues el tipo
    de trabajo pasa a una version que ya no la pide, y la foto tiene que seguir
    entrando. Si se validara contra el esquema vigente, el tecnico habria sacado
    una foto que el servidor rechaza por un cambio que nadie le aviso.
    """
    user, profile = tecnico
    evento = _registrar_bloqueo(orden, profile)

    v2 = WorkTypeVersion.objects.create(
        work_type=version.work_type,
        version=2,
        # `version=2` es la REVISION; el contrato sigue siendo el 1. Decia
        # `schema_version=2` y era la misma confusion que bloqueo una orden de
        # verdad: un contrato 2 no existe, y la app lo rechaza.
        schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=ESQUEMA_V2,
        schema_hash="hash-evid-v2",
    )
    orden.tipo_trabajo_version = v2
    orden.save(update_fields=["tipo_trabajo_version"])

    r = _subir(
        _cliente(user, orden.org, profile),
        orden,
        requisito="foto_del_obstaculo",
        sha="a" * 64,
        evento=evento,
    )

    assert r.status_code == 200, r.data
    assert EvidenciaTrabajo.objects.get(id=r.data["evidencia_id"]).evento_id == evento.id


def test_d_un_requisito_que_ese_reporte_no_pedia_se_rechaza(orden, tecnico):
    user, profile = tecnico
    evento = _registrar_bloqueo(orden, profile)

    # 'foto_fachada' existe, pero en el INICIO. No en este reporte.
    r = _subir(
        _cliente(user, orden.org, profile),
        orden,
        requisito="foto_fachada",
        sha="b" * 64,
        evento=evento,
    )

    assert r.status_code == 400
    assert r.data["error"] == "REQUISITO_INVALIDO"


def test_e_un_requisito_del_checklist_no_sirve_para_un_reporte(orden, tecnico):
    """Las dos listas no se mezclan, y por eso mismo no se cubren entre si."""
    user, profile = tecnico
    evento = _registrar_bloqueo(orden, profile)

    r = _subir(
        _cliente(user, orden.org, profile),
        orden,
        requisito="foto_acta",  # del checklist de la orden
        sha="c" * 64,
        evento=evento,
    )

    assert r.status_code == 400


def test_f_un_evento_de_otra_orden_se_rechaza(org_a, tecnico, version):
    """Con solo un id, una foto podria colgarse del reporte de otro trabajo."""
    user, profile = tecnico
    mia = _orden(org_a, version, profile, numero=7103)
    ajena = _orden(org_a, version, profile, numero=7104)
    evento_ajeno = _registrar_bloqueo(ajena, profile)

    r = _subir(
        _cliente(user, org_a, profile),
        mia,
        requisito="foto_del_obstaculo",
        sha="d" * 64,
        evento=evento_ajeno,
    )

    assert r.status_code == 400
    assert r.data["error"] == "EVENTO_INVALIDO"


# --------------------------------------------------------------------------- #
# C. El deduplicado: lo que NO se puede haber roto al agregar el vinculo
# --------------------------------------------------------------------------- #

def test_g_el_checklist_sigue_deduplicando_la_misma_foto(orden, tecnico):
    """LA GUARDA DE REGRESION.

    Agregar `evento` a la constraint original la habria apagado sin ruido: en
    PostgreSQL NULL no es igual a NULL, asi que dos filas con el evento vacio, el
    mismo requisito y el mismo sha habrian pasado como distintas. Esta es la
    garantia que existia antes de la Fase 4 y tiene que seguir en pie.
    """
    user, profile = tecnico
    c = _cliente(user, orden.org, profile)

    uno = _subir(c, orden, requisito="foto_acta", sha="e" * 64)
    dos = _subir(c, orden, requisito="foto_acta", sha="e" * 64)

    assert uno.status_code == 200 and dos.status_code == 200
    assert uno.data["evidencia_id"] == dos.data["evidencia_id"]
    assert (
        EvidenciaTrabajo.objects.filter(
            orden_trabajo=orden, requisito_id="foto_acta", evento__isnull=True
        ).count()
        == 1
    )


def test_h_la_misma_foto_en_dos_reportes_son_dos_hechos(orden, tecnico):
    """Y aca el deduplicado NO tiene que actuar.

    Dos bloqueos distintos con la misma fachada fotografiada son dos hechos
    distintos. Si se colapsaran en uno, el segundo reporte quedaria sin foto y
    nadie sabria por que.
    """
    user, profile = tecnico
    c = _cliente(user, orden.org, profile)
    primero = _registrar_bloqueo(orden, profile, motivo="Cerrada a las 8")
    segundo = _registrar_bloqueo(orden, profile, motivo="Cerrada otra vez a las 11")

    uno = _subir(c, orden, requisito="foto_del_obstaculo", sha="f" * 64, evento=primero)
    dos = _subir(c, orden, requisito="foto_del_obstaculo", sha="f" * 64, evento=segundo)

    assert uno.status_code == 200 and dos.status_code == 200
    assert uno.data["evidencia_id"] != dos.data["evidencia_id"]
    assert EvidenciaTrabajo.objects.filter(evento__isnull=False).count() == 2


def test_i_un_reintento_del_mismo_reporte_devuelve_la_misma_fila(orden, tecnico):
    user, profile = tecnico
    c = _cliente(user, orden.org, profile)
    evento = _registrar_bloqueo(orden, profile)

    uno = _subir(c, orden, requisito="foto_del_obstaculo", sha="0" * 64, evento=evento)
    dos = _subir(c, orden, requisito="foto_del_obstaculo", sha="0" * 64, evento=evento)

    assert uno.data["evidencia_id"] == dos.data["evidencia_id"]


# --------------------------------------------------------------------------- #
# D. Lo que la linea de tiempo deja salir, y lo que no
# --------------------------------------------------------------------------- #

def test_j_la_linea_de_tiempo_trae_las_fotos_y_las_que_faltaban(orden, tecnico):
    user, profile = tecnico
    c = _cliente(user, orden.org, profile)
    evento = _registrar_bloqueo(orden, profile)
    _subir(c, orden, requisito="foto_del_obstaculo", sha="1" * 64, evento=evento)

    fila = [
        f
        for f in seg.linea_de_tiempo(orden)["eventos"]
        if f["tipo"] == "bloqueo_campo"
    ][0]

    assert [e["requisito_id"] for e in fila["evidencias"]] == ["foto_del_obstaculo"]
    # Las dos listas: sin la segunda, un bloqueo sin foto y un bloqueo al que
    # nunca se le pidio una se leen igual.
    assert [e["id"] for e in fila["evidencias_declaradas"]] == ["foto_del_obstaculo"]


def test_k_una_foto_registrada_pero_no_subida_no_se_declara_disponible(orden, tecnico):
    """Que exista la fila no es que la foto este en el servidor."""
    user, profile = tecnico
    c = _cliente(user, orden.org, profile)
    evento = _registrar_bloqueo(orden, profile)
    _subir(c, orden, requisito="foto_del_obstaculo", sha="2" * 64, evento=evento)

    fila = [
        f for f in seg.linea_de_tiempo(orden)["eventos"] if f["tipo"] == "bloqueo_campo"
    ][0]

    assert fila["evidencias"][0]["disponible"] is False
    assert fila["evidencias"][0]["estado_archivo"] == EvidenciaTrabajo.SUBIENDO


def test_l_ni_la_ruta_del_archivo_ni_el_gps_salen_a_la_pantalla(orden, tecnico):
    """La fila lleva las dos; ninguna tiene nada que hacer en una pantalla."""
    user, profile = tecnico
    c = _cliente(user, orden.org, profile)
    evento = _registrar_bloqueo(orden, profile)
    r = _subir(c, orden, requisito="foto_del_obstaculo", sha="3" * 64, evento=evento)

    ev = EvidenciaTrabajo.objects.get(id=r.data["evidencia_id"])
    ev.metadatos_captura = {"lat": 6.2451, "lng": -75.5812, "modelo": "Pixel"}
    ev.save(update_fields=["metadatos_captura"])

    fila = [
        f for f in seg.linea_de_tiempo(orden)["eventos"] if f["tipo"] == "bloqueo_campo"
    ][0]
    foto = fila["evidencias"][0]

    assert "storage_key" not in foto
    assert "metadatos_captura" not in foto
    assert "6.2451" not in str(fila)


def test_m_un_reporte_sin_fotos_trae_la_lista_vacia_no_la_clave_ausente(orden, tecnico):
    """Quien dibuja no tiene que preguntarse si la clave existe."""
    evento = _registrar_bloqueo(orden, tecnico[1])
    assert evento is not None

    fila = [
        f for f in seg.linea_de_tiempo(orden)["eventos"] if f["tipo"] == "bloqueo_campo"
    ][0]

    assert fila["evidencias"] == []


# --------------------------------------------------------------------------- #
# E. La foto no retiene el reporte
# --------------------------------------------------------------------------- #

def test_n_un_reporte_con_foto_declarada_se_guarda_igual_sin_ella(orden, tecnico):
    """DECISION DE PRODUCTO, afirmada donde se puede romper.

    El texto es lo que destraba al NOC; la foto lo respalda. Si una foto
    obligatoria retuviera el reporte, un tecnico sin espacio en el telefono --o
    con la camara rota-- dejaria al NOC sin saber que el trabajo esta detenido.
    Se guarda primero y se entrega despues, como todo lo demas del modulo.
    """
    evento = _registrar_bloqueo(orden, tecnico[1])

    assert evento.pk is not None
    assert evento.evidencias.count() == 0
    # Y queda escrito que se pedia, para que la falta se pueda ver.
    assert [e["id"] for e in evento.datos["evidencias"]] == ["foto_del_obstaculo"]


# --------------------------------------------------------------------------- #
# F. La restriccion de la base, medida sin pasar por la vista
# --------------------------------------------------------------------------- #
#
# POR QUE ESTA SECCION EXISTE
# ---------------------------
# `test_g` pasa por la relectura con select_for_update que la vista hace ANTES de
# insertar: pasaria igual aunque en la base no hubiera ninguna constraint. Es
# justo el caso que el metodo llama "una prueba en verde con el sintoma vivo" --
# afirma el efecto por el camino feliz y no toca la garantia.
#
# Lo que de verdad protege el dato es el indice unico. Aca se inserta a mano,
# sorteando la vista, y se exige que la base se niegue.


def _guardar(orden, *, requisito, sha, evento=None):
    return EvidenciaTrabajo.objects.create(
        org=orden.org,
        orden_trabajo=orden,
        evento=evento,
        requisito_id=requisito,
        sha256=sha,
        nombre_original="x.jpg",
        mime_type="image/jpeg",
        bytes=10,
        estado_archivo=EvidenciaTrabajo.SUBIENDO,
    )


@pytest.mark.postgres_only
def test_o_la_base_rechaza_la_misma_foto_del_checklist_dos_veces(orden, tecnico):
    """La garantia que existia ANTES de la Fase 4, medida en la base.

    En SQLite y en PostgreSQL NULL no es igual a NULL: si la constraint hubiera
    quedado sobre (orden, requisito, sha, evento) sin condicion, estas dos filas
    -- con `evento` vacio -- habrian entrado las dos y nadie se habria enterado.
    """
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real: se mide el indice unico parcial.")

    _guardar(orden, requisito="foto_acta", sha="9" * 64)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _guardar(orden, requisito="foto_acta", sha="9" * 64)


@pytest.mark.postgres_only
def test_p_la_base_rechaza_la_misma_foto_dos_veces_en_el_mismo_reporte(orden, tecnico):
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real: se mide el indice unico parcial.")

    evento = _registrar_bloqueo(orden, tecnico[1])
    _guardar(orden, requisito="foto_del_obstaculo", sha="8" * 64, evento=evento)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _guardar(orden, requisito="foto_del_obstaculo", sha="8" * 64, evento=evento)


@pytest.mark.postgres_only
def test_q_la_base_si_acepta_la_misma_foto_en_dos_reportes(orden, tecnico):
    """La otra direccion. Una sola de las dos se cumpliria por accidente con una
    constraint que rechace todo, o con ninguna."""
    if connection.vendor != "postgresql":
        pytest.skip("Exige PostgreSQL real: se mide el indice unico parcial.")

    uno = _registrar_bloqueo(orden, tecnico[1], motivo="a las 8")
    dos = _registrar_bloqueo(orden, tecnico[1], motivo="a las 11")

    _guardar(orden, requisito="foto_del_obstaculo", sha="7" * 64, evento=uno)
    _guardar(orden, requisito="foto_del_obstaculo", sha="7" * 64, evento=dos)

    assert EvidenciaTrabajo.objects.filter(sha256="7" * 64).count() == 2
