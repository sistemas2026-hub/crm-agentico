# -*- coding: utf-8 -*-
"""Volver a medir la señal optica desde el terreno.

POR QUE EXISTE
--------------
La señal que trae la ficha es la del momento en que se armo la orden. Si eso
fue a las 08:10 y el tecnico llego a las 14:00, esa lectura tiene seis horas. Y
justo despues de limpiar un conector o cambiar una roseta, lo unico que contesta
«¿quedo bien?» es volver a medir. Hoy eso es una llamada al NOC.

LO QUE SE AFIRMA, Y QUE PASA SI SE ROMPE
----------------------------------------
1. **No pisa la lectura congelada.** `orden.contexto` es el registro de como
   estaba el servicio ANTES de la visita, y es lo unico que permite decir
   despues si la visita sirvio. Sobrescribirlo con la medicion de ahora borra
   esa evidencia -- y encima dejaria el «antes» igual al «despues» siempre, que
   es la forma mas limpia de no poder probar nada.

2. **Se mide el equipo de ESTA orden.** El serial sale de la ficha congelada y
   no de una consulta nueva: un cliente puede tener mas de un servicio, y
   resolverlo de nuevo mediria el equipo equivocado sin que nadie se entere.

3. **«No se pudo medir» no es «la señal esta mal».** La primera se reintenta; la
   segunda es un dato del equipo del cliente. Confundirlas manda al tecnico a
   buscar una falla de planta cuando lo que pasa es que el motor no contesto.

4. **Nunca se inventa un numero.** Si la respuesta llega sin niveles, se dice
   que no se pudo -- un cero seria afirmar que la señal esta en el piso.

5. **Fail-closed sobre lo que sale.** Lo que no esta en `CAMPOS_DE_SENAL` no
   sale, aunque el proveedor lo agregue mañana.
"""

from unittest import mock

import pytest

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services import telemetria

pytestmark = pytest.mark.django_db

SERIAL = "ZTEGC0A1B2C3"

#: La ficha tal como la congelo el despacho: con su lectura y su hora.
CONTEXTO_CONGELADO = {
    "contexto_disponible": True,
    "capturado_en": "2026-10-05T08:10:00+00:00",
    "servicio": "WH-1042",
    "sn_onu": SERIAL,
    "equipo": {
        "onu_status": "Online",
        "onu_signal_1490": -21.74,
        "onu_signal_1490_veredicto": "aceptable",
    },
}


@pytest.fixture
def orden(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="medir_test", nombre="Reparación")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )
    return OrdenTrabajo.objects.create(
        org=org_a, numero=7001, tipo_trabajo_version=version,
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
        contexto=dict(CONTEXTO_CONGELADO),
    )


class _Respuesta:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("sin cuerpo")
        return self._payload


def _motor_contesta(payload, status_code=200):
    return mock.patch.object(
        telemetria.requests, "post",
        return_value=_Respuesta(status_code, payload),
    )


LECTURA_NUEVA = {
    "resultado": {
        "onu_signal": "Very good",
        "onu_signal_1310": -23.10,
        "onu_signal_1490": -19.40,
        "onu_signal_1490_veredicto": "aceptable",
        "onu_status": "Online",
    }
}


# --------------------------------------------------------------------------- #
# A. Lo que devuelve
# --------------------------------------------------------------------------- #

def test_a1_devuelve_la_lectura_de_ahora_con_su_hora(orden):
    with _motor_contesta(LECTURA_NUEVA):
        r = telemetria.medir_senal(orden)

    assert r["ok"] is True
    assert r["lectura"]["onu_signal_1490"] == -19.40
    # La hora es parte de la medicion: sin ella, en cinco minutos vuelve a ser
    # una lectura vieja sin que nadie lo note.
    assert r["medido_en"]


def test_a2_le_pregunta_por_el_serial_de_ESTA_orden(orden):
    with _motor_contesta(LECTURA_NUEVA) as post:
        telemetria.medir_senal(orden)

    assert post.call_args.kwargs["json"] == {"sn_onu": SERIAL}
    assert "consultar_senal_ont" in post.call_args.args[0]


# --------------------------------------------------------------------------- #
# B. LA MAS IMPORTANTE: no pisa el registro de como estaba antes
# --------------------------------------------------------------------------- #

def test_b1_NO_toca_la_ficha_congelada(orden):
    """Si la pisara, el «antes» y el «despues» serian siempre iguales -- y nadie
    podria probar que la visita sirvio."""
    with _motor_contesta(LECTURA_NUEVA):
        telemetria.medir_senal(orden)

    orden.refresh_from_db()
    assert orden.contexto["equipo"]["onu_signal_1490"] == -21.74
    assert orden.contexto["capturado_en"] == "2026-10-05T08:10:00+00:00"


def test_b2_la_lectura_nueva_viene_APARTE_de_la_vieja(orden):
    """No se devuelve mezclada con la ficha: son dos momentos distintos y el
    tecnico tiene que poder compararlos."""
    with _motor_contesta(LECTURA_NUEVA):
        r = telemetria.medir_senal(orden)

    assert set(r) == {"ok", "medido_en", "lectura"}
    assert "contexto" not in r


# --------------------------------------------------------------------------- #
# C. Cuando no se puede medir
# --------------------------------------------------------------------------- #

def test_c1_sin_serial_no_se_intenta_y_se_dice(orden):
    orden.contexto = {"servicio": "WH-1042"}
    orden.save(update_fields=["contexto"])

    with mock.patch.object(telemetria.requests, "post") as post:
        with pytest.raises(telemetria.SinEquipoParaMedir):
            telemetria.medir_senal(orden)

    post.assert_not_called()


def test_c2_el_motor_sin_responder_NO_es_una_señal_mala(orden):
    """Confundirlas manda al tecnico a buscar una falla de planta cuando lo que
    pasa es que el motor no contesto."""
    with mock.patch.object(
        telemetria.requests, "post", side_effect=OSError("sin red")
    ):
        r = telemetria.medir_senal(orden)

    assert r == {"ok": False, "motivo": "motor_no_responde", "detalle": "OSError"}


def test_c3_un_403_dice_que_es_configuracion_y_no_el_equipo(orden):
    with _motor_contesta({}, status_code=403):
        r = telemetria.medir_senal(orden)

    assert r["motivo"] == "medicion_no_habilitada"


def test_c4_una_respuesta_sin_niveles_NO_inventa_un_cero(orden):
    """Un cero seria afirmar que la señal esta en el piso. Lo que pasa es que no
    se sabe."""
    with _motor_contesta({"resultado": {"otra_cosa": "x"}}):
        r = telemetria.medir_senal(orden)

    assert r == {"ok": False, "motivo": "sin_lectura"}


def test_c5_una_respuesta_vacia_se_distingue_de_una_ilegible(orden):
    with _motor_contesta({"resultado": {}}):
        assert telemetria.medir_senal(orden)["motivo"] == "respuesta_vacia"

    with _motor_contesta(None):
        assert telemetria.medir_senal(orden)["motivo"] == "respuesta_ilegible"


# --------------------------------------------------------------------------- #
# D. Fail-closed sobre lo que sale
# --------------------------------------------------------------------------- #

def test_d1_un_campo_que_nadie_nombro_no_sale(orden):
    """La respuesta de señal hoy no trae datos personales. Esta lista es lo que
    impide que eso cambie en silencio."""
    with _motor_contesta({
        "resultado": {
            "onu_signal_1490": -19.40,
            "name": "Beatriz Pinzón",
            "address_or_comment": "Calle 50 # 10-20",
        }
    }):
        r = telemetria.medir_senal(orden)

    assert r["lectura"] == {"onu_signal_1490": -19.40}
    assert "Beatriz" not in str(r)


def test_d2_un_nivel_vacio_no_entra(orden):
    """Un `onu_signal_1490` vacio es «no se leyo», no «cero dBm»."""
    with _motor_contesta({
        "resultado": {"onu_signal_1490": "", "onu_status": "Online"}
    }):
        r = telemetria.medir_senal(orden)

    assert r["lectura"] == {"onu_status": "Online"}


# --------------------------------------------------------------------------- #
# E. Por HTTP
# --------------------------------------------------------------------------- #

def test_e1_sin_serial_responde_409_y_no_500(orden, user_client, user_profile):
    from campo.models import AsignacionTrabajo

    AsignacionTrabajo.objects.create(
        orden=orden, profile=user_profile, rol="tecnico", es_principal=True
    )
    orden.contexto = {"servicio": "WH-1042"}
    orden.save(update_fields=["contexto"])

    r = user_client.post(f"/api/campo/trabajos/{orden.id}/medir-senal/")

    assert r.status_code == 409


def test_e2_una_orden_de_otra_empresa_responde_404(org_b, user_client):
    wt = WorkType.objects.create(org=org_b, codigo="medir_b", nombre="Reparación")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []},
    )
    ajena = OrdenTrabajo.objects.create(
        org=org_b, numero=7100, tipo_trabajo_version=version,
        cliente_nombre="Otro", cliente_direccion="x",
        estado_operativo=OrdenTrabajo.EN_SITIO, revision=1,
        contexto=dict(CONTEXTO_CONGELADO),
    )

    r = user_client.post(f"/api/campo/trabajos/{ajena.id}/medir-senal/")

    assert r.status_code == 404
