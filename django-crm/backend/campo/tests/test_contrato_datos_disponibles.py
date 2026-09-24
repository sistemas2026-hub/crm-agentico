# -*- coding: utf-8 -*-
"""
Lo que el servidor ya sabía y la aplicación no recibía.

POR QUÉ EXISTE ESTE ARCHIVO
---------------------------
El inventario del 22/09/2026 encontró siete datos guardados en la base que
ningún serializador devolvía. El más caro: cuando un supervisor devuelve una
orden, la lista de qué hay que rehacer vivía solo en la bitácora del servidor
(`EventoTrabajo`), así que el técnico veía su trabajo en `correccion_requerida`
sin saber qué le devolvieron y lo averiguaba por teléfono.

Estas pruebas afirman sobre **la respuesta HTTP**, que es lo que el teléfono
recibe, no sobre el modelo. Si alguien vuelve a dejar un dato dentro del
servidor, acá falla.
"""

import pytest

from campo.models import (
    AsignacionTrabajo, EvidenciaTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion,
)
from campo.services.transiciones import completar_campo, requerir_correccion

pytestmark = pytest.mark.django_db


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="ftth_correctivo",
                                 nombre="Correctivo Fibra")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={
            "pasos": [
                {"id": "p1", "titulo": "Llegada al inmueble"},
                {"id": "p2", "titulo": "Medición óptica"},
                {"id": "p3", "titulo": "Cierre con el abonado"},
            ],
            "campos": [],
            "evidencias": [
                {"id": "foto_cto", "titulo": "Foto CTO", "obligatorio": True},
                {"id": "foto_potencia", "titulo": "Foto potencia", "obligatorio": True},
            ],
        },
    )


@pytest.fixture
def orden(org_a, user_profile, version):
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=7001, tipo_trabajo_version=version,
        cliente_nombre="Cliente de prueba",
        cliente_direccion="Calle 45 #12-88",
        estado_operativo=OrdenTrabajo.EN_SITIO,
        origen_sistema="wisphub",
        origen_tipo="ticket",
        origen_ref="WH-91288",
        contexto={
            "contexto_disponible": True,
            "capturado_en": "2026-09-22T07:00:00Z",
            "fuente": "motor",
            "cliente": {"nombre": "Cliente de prueba", "plan": "Fibra 500 Mbps"},
            "sn_onu": "48575443-A9B0C1",
        },
    )
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return o


def _subir(orden, requisito, vuelta):
    return EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=vuelta, sha256=f"{requisito}-v{vuelta}",
        storage_key=f"k/{requisito}/{vuelta}", nombre_original=f"{requisito}.jpg",
        mime_type="image/jpeg", bytes=1024,
        estado_archivo=EvidenciaTrabajo.RECIBIDO,
    )


# ======================= La devolución del supervisor =======================

def test_1_una_orden_devuelta_dice_que_hay_que_rehacer(user_client, orden, user_profile):
    """
    La prueba que más importa del archivo.

    Sin esto, el técnico recibe la orden devuelta y no sabe qué corregir.
    """
    for r in ("foto_cto", "foto_potencia"):
        _subir(orden, r, 1)
    completar_campo(orden, profile=user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"],
                        profile=user_profile,
                        observacion="La medición no coincide con la OLT")

    r = user_client.get(f"/api/campo/trabajos/{orden.id}/")
    assert r.status_code == 200

    correccion = r.json()["correccion"]
    assert correccion is not None, "la orden vino devuelta y la respuesta no lo dice"
    assert correccion["requisitos"] == ["foto_potencia"]
    assert correccion["observacion"] == "La medición no coincide con la OLT"
    assert correccion["vuelta"] == 2
    assert correccion["devuelta_en"] is not None


def test_2_sin_devolucion_el_campo_viene_vacio_no_inventado(user_client, orden):
    """Una orden que nadie devolvió no trae una corrección de relleno."""
    r = user_client.get(f"/api/campo/trabajos/{orden.id}/")

    assert r.status_code == 200
    assert r.json()["correccion"] is None
    assert r.json()["vuelta"] == 1


def test_3_la_devolucion_es_la_de_la_vuelta_que_corre(user_client, orden, user_profile):
    """
    Dos vueltas, dos devoluciones distintas. La aplicación tiene que recibir la
    vigente, no la primera ni una mezcla de las dos.
    """
    for r in ("foto_cto", "foto_potencia"):
        _subir(orden, r, 1)
    completar_campo(orden, profile=user_profile)
    requerir_correccion(orden, requisitos=["foto_potencia"],
                        profile=user_profile, observacion="Primera devolución")

    # Segunda vuelta: rehace y se la devuelven por otra cosa.
    _subir(orden, "foto_potencia", 2)
    orden.refresh_from_db()
    orden.estado_operativo = OrdenTrabajo.EN_SITIO
    orden.save(update_fields=["estado_operativo"])
    _subir(orden, "foto_cto", 2)
    completar_campo(orden, profile=user_profile)
    requerir_correccion(orden, requisitos=["foto_cto"],
                        profile=user_profile, observacion="Segunda devolución")

    correccion = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()["correccion"]
    assert correccion["vuelta"] == 3
    assert correccion["requisitos"] == ["foto_cto"]
    assert correccion["observacion"] == "Segunda devolución"


# ======================= Lo demás que ya estaba guardado ====================

def test_4_el_origen_de_la_orden_viaja_en_lista_y_en_detalle(user_client, orden):
    """De qué ticket nació la orden. Estaba en la base desde el primer día."""
    detalle = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()
    assert detalle["origen"] == {
        "sistema": "wisphub",
        "tipo": "ticket",
        "ref": "WH-91288",
    }

    fila = next(
        o for o in user_client.get("/api/campo/trabajos/").json()["results"]
        if o["numero"] == 7001
    )
    assert fila["origen"]["ref"] == "WH-91288"


def test_5_los_pasos_del_procedimiento_salen_de_la_plantilla(user_client, orden):
    """
    El protocolo de atención no hay que inventarlo: viene con el tipo de
    trabajo y cambia con él.
    """
    tipo = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()["tipo"]

    assert [p["titulo"] for p in tipo["pasos"]] == [
        "Llegada al inmueble",
        "Medición óptica",
        "Cierre con el abonado",
    ]


def test_6_el_contexto_tecnico_congelado_llega_al_telefono(user_client, orden):
    """El plan del cliente y el serial de la ONU ya se guardaban al despachar."""
    contexto = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()["contexto"]

    assert contexto["cliente"]["plan"] == "Fibra 500 Mbps"
    assert contexto["sn_onu"] == "48575443-A9B0C1"
    # Y con su procedencia, para que nadie lo lea como una lectura de ahora.
    assert contexto["capturado_en"] == "2026-09-22T07:00:00Z"
    assert contexto["fuente"] == "motor"


def test_7_la_cuadrilla_incluye_a_quien_no_es_principal(user_client, orden, org_a,
                                                        admin_profile):
    """Un ayudante asignado existía en la base y la aplicación no lo veía."""
    AsignacionTrabajo.objects.create(orden=orden, profile=admin_profile,
                                     rol="ayudante", es_principal=False)

    cuadrilla = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()["cuadrilla"]

    assert len(cuadrilla) == 2
    assert cuadrilla[0]["es_principal"] is True, "el principal va primero"
    assert {c["rol"] for c in cuadrilla} == {"tecnico", "ayudante"}


def test_8_el_contrato_anterior_sigue_intacto(user_client, orden):
    """
    Todo lo de esta tanda es aditivo: la versión de la aplicación que está en
    la calle no puede romperse porque el servidor mande más campos.
    """
    detalle = user_client.get(f"/api/campo/trabajos/{orden.id}/").json()

    for campo in (
        "id", "numero", "revision", "tipo", "cliente", "tecnico_principal",
        "diagnostico_previo", "schema", "datos", "evidencias",
        "estado_operativo", "estado_validacion", "programada_para",
        "iniciada_en", "completada_campo_en", "created_at", "updated_at",
    ):
        assert campo in detalle, f"desapareció del contrato: {campo}"

    assert detalle["cliente"]["direccion"] == "Calle 45 #12-88"


# --- 24/09/2026 · la localidad se caía en el último filtro -------------------

def test_9_la_localidad_del_cliente_sobrevive_al_snapshot():
    """
    El motor ya mandaba la localidad y se perdía acá.

    Está en su `_CAMPOS_FICHA` junto a `ip` y `direccion`, viaja entera hasta
    `depurar_contexto()`, y esta lista blanca era el único lugar donde se
    caía. No hizo falta migración ni tocar el motor: el dato ya llegaba.

    La dirección sola dice el número de la casa; la localidad dice en qué
    parte del pueblo queda, que es lo que decide si una visita entra en la
    ruta de hoy.
    """
    from campo.services.despacho import depurar_contexto

    crudo = {
        "cliente": {
            "nombre": "Quien Sea",
            "estado": "Activo",
            "plan": "Fibra 300",
            "ip": "10.0.0.9",
            "localidad": "SAN JOSE",
            "cedula": "1044601347",
            "direccion": "Cl. 45 #12-88",
            "telefono": "3113683499",
        },
        "identidad": {"servicio": "7127", "origen": "wisphub"},
    }

    cliente = depurar_contexto(crudo)["cliente"]

    assert cliente["localidad"] == "SAN JOSE", "la localidad tiene que pasar"
    assert cliente["ip"] == "10.0.0.9", "y la ip seguir pasando"

    # 24/09/2026: el comentario de la lista decia desde siempre que la
    # direccion entra --"hay que saber a quien se visita y donde"-- y no
    # estaba. El codigo contradecia a su propio comentario, y se noto al mirar
    # una orden real: el tecnico veia "Sin direccion" con el dato cargado.
    #
    # No alcanza con que vivan en la orden: esos campos los llena quien
    # despacha desde el formulario, y un caso IMPORTADO del ISP no pasa por
    # ninguno. Para esas ordenes la ficha es la unica fuente.
    assert cliente["direccion"] == "Cl. 45 #12-88", "sin direccion no se llega"
    assert cliente["telefono"] == "3113683499", "sin telefono no se avisa"


def test_10_el_snapshot_sigue_dejando_afuera_el_dato_personal():
    """
    Abrir la lista blanca para la localidad no puede abrirla para todo.

    Afirma el EFECTO —qué claves quedan— y no la presencia de la constante:
    una prueba que solo mirara `CAMPOS_CLIENTE_SNAPSHOT` seguiría en verde si
    alguien cambiara la comprensión de lista que filtra de verdad.
    """
    from campo.services.despacho import depurar_contexto

    crudo = {
        "cliente": {
            "nombre": "Quien Sea",
            "localidad": "SAN JOSE",
            "cedula": "1044601347",
            "password_servicio": "no-deberia-estar",
            "gps": "6.24,-75.58",
            "direccion": "Cl. 45 #12-88",
        },
    }

    cliente = depurar_contexto(crudo)["cliente"]

    for prohibido in ("cedula", "password_servicio", "gps"):
        assert prohibido not in cliente, f"se coló al snapshot: {prohibido}"
