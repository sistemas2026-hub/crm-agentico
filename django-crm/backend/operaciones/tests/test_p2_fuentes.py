# -*- coding: utf-8 -*-
"""
================================================================================
 P2  --  LA CAPA DE FUENTES: que un cero tenga procedencia
================================================================================

LA PROPIEDAD QUE JUSTIFICA TODO EL BLOQUE
-----------------------------------------
Que "no hay nada" y "no se pudo preguntar" NO terminen en el mismo numero.

Ya paso, y esta medido: de los 15 detectores del Supervisor, solo 2 habian
disparado alguna vez en produccion. Los otros 13 leen tablas vacias y devuelven
[] -- indistinguible de "todo en orden". Un tablero sobre eso afirma que no hay
problemas porque no tiene con que verlos.

Asi que la mayoria de las pruebas de aqui no comprueban que algo funcione:
comprueban que un fallo NO se pueda confundir con un cero. Son las que importan.

COMO ESTA ORDENADO
------------------
    §1  el registro de fuentes y su alta
    §2  activa / inactiva, y cuando toca consultar
    §3  consulta exitosa, vacia, con error, con timeout
    §4  frescura: fresca, vieja, desconocida, sin dato
    §5  la ventana inconclusa  --  el vacio que no significa nada
    §6  snapshots y comparacion entre ciclos
    §7  multi-tenant
    §8  cada fuente: SmartOLT, WispHub, Dexter, SLA, M02, M03
    §9  lo que NO hace: efectos externos, situaciones, propuestas, autonomia
    §10 idempotencia y concurrencia

LO QUE SE SUSTITUYE, Y LO QUE NO
-------------------------------
Se sustituye 'requests.post' --la red hacia el motor-- y nada mas. La base es
Postgres de verdad, los modelos son los de produccion, y las cuatro fuentes
internas (Dexter, SLA, M02, M03) se consultan de verdad contra filas creadas
aqui. Un mock de la capa entera probaria el mock.
================================================================================
"""

import json
import threading
from unittest import mock

import pytest
from django.utils import timezone

from campo.models import OrdenTrabajo
from cases.models import Case
from common.models import Activity
from operaciones import fuentes, fuentes_adaptadores
from operaciones.fuentes_modelos import (EstadoLectura, Frescura, Fuente,
                                         FuenteEstado, FuenteSnapshot)
from operaciones.models import ActividadOperativa, PropuestaSupervisor

RUTA = "/api/operaciones/supervisor/sondeo/"

_n = [4200]


# =============================================================================
#  utilidades
# =============================================================================

def _fuente(org, nombre, **extra):
    """Una fila de fuente, ACTIVA salvo que se diga lo contrario."""
    datos = {"activa": True}
    datos.update(fuentes.SEMILLA.get(nombre, {}))
    datos.update(extra)
    f, _ = FuenteEstado.objects.update_or_create(
        org=org, fuente=nombre, defaults=datos)
    return f


class RespuestaFalsa:
    def __init__(self, status_code=200, cuerpo=None, revienta=False):
        self.status_code = status_code
        self._cuerpo = cuerpo if cuerpo is not None else {}
        self._revienta = revienta

    def json(self):
        if self._revienta:
            raise ValueError("no es JSON")
        return self._cuerpo


class Motor:
    """Sustituye la red hacia el motor y CUENTA lo que salio."""

    def __init__(self, respuesta=None, excepcion=None, por_herramienta=None):
        self.respuesta = respuesta if respuesta is not None else RespuestaFalsa()
        self.excepcion = excepcion
        self.por_herramienta = por_herramienta or {}
        self.llamadas = []

    def post(self, url, params=None, json=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "params": params or {},
                              "cuerpo": json or {}, "timeout": timeout})
        if self.excepcion is not None:
            raise self.excepcion
        for nombre, r in self.por_herramienta.items():
            if f"/interno/herramienta/{nombre}" in url:
                if isinstance(r, Exception):
                    raise r
                return r
        return self.respuesta


#  El sobre REAL de 'get_outage_pons', copiado de la verificacion en vivo del
#  18/08/2026 (8 ONUs caidas de verdad). No es un ejemplo inventado: es la forma
#  que la skill dejo registrada, con los nombres de campo tal cual.
SOBRE_SMARTOLT = {
    "resultado": {"response": {
        "total_pons": 1,
        "sections": [
            {"key": "partial_los", "group_by": "pon", "groups": [
                {"label": "1/3", "pon_count": 1, "subscribers": 8,
                 "pons": [{"alert_kind": "partial_los",
                           "partial_started_at": "2026-10-02 16:22:51",
                           "partial_last_seen_at": "2026-10-02 16:30:10",
                           "olt_id": "3", "board": "1", "port": "3",
                           "total_onus": "103", "los_count": "8",
                           "power_count": "4", "offline_count": "7",
                           "affected_onus": 8, "affected_percent": 7.8,
                           "odb_name": "CTO 56", "odb_count": 23}]}]},
            {"key": "los", "groups": []},
            {"key": "power", "groups": []},
            {"key": "offline", "groups": []},
        ],
        "stale": {"pon_count": 0, "subscribers": 0, "groups": []},
        "unreachable_olts": [],
    }}
}

SOBRE_SMARTOLT_LIMPIO = {
    "resultado": {"response": {
        "total_pons": 0,
        "sections": [{"key": "partial_los", "groups": []},
                     {"key": "los", "groups": []},
                     {"key": "power", "groups": []},
                     {"key": "offline", "groups": []}],
        "stale": {"pon_count": 0, "subscribers": 0, "groups": []},
        "unreachable_olts": [],
    }}
}


def _con_motor(motor, tenant="rapilink"):
    """Sustituye la red hacia el motor y el entorno que el adaptador necesita."""
    return _Contexto(motor, tenant)


class _Contexto:
    def __init__(self, motor, tenant):
        self.motor = motor
        self.tenant = tenant
        self._parches = []

    def __enter__(self):
        import os
        self._parches = [
            mock.patch("requests.post", self.motor.post),
            mock.patch.dict(os.environ, {
                "MOTOR_TENANT": self.tenant,
                "MOTOR_URL": "http://motor-de-prueba:5000",
                "SUPERVISOR_HERRAMIENTAS_CAIDAS_PON": "consultar_caidas_pon_1",
            }, clear=False),
        ]
        for p in self._parches:
            p.start()
        return self.motor

    def __exit__(self, *a):
        for p in reversed(self._parches):
            p.stop()
        return False


def _version(org, codigo):
    """Una version de tipo de trabajo. 'OrdenTrabajo' la exige (NOT NULL)."""
    from campo.models import WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org, codigo=codigo, nombre=codigo)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []})


def _orden(org, **extra):
    _n[0] += 1
    datos = dict(org=org, numero=_n[0], estado_operativo="pendiente",
                 tipo_trabajo_version=_version(org, f"p2_{_n[0]}"),
                 cliente_nombre=f"Cliente {_n[0]}",
                 cliente_direccion="Calle 1")
    datos.update(extra)
    return OrdenTrabajo.objects.create(**datos)


# =============================================================================
#  §1  EL REGISTRO DE FUENTES
# =============================================================================

def test_1_el_alta_crea_las_seis_fuentes(org_a):
    creadas = fuentes.asegurar_fuentes(org_a)

    assert sorted(creadas) == sorted(Fuente.TODAS)
    assert FuenteEstado.objects.filter(org=org_a).count() == 6


def test_2_las_seis_nacen_APAGADAS(org_a):
    #  Desplegar el codigo NO enciende seis consultas periodicas contra los
    #  sistemas de un cliente. Encenderlas es una decision de operacion.
    fuentes.asegurar_fuentes(org_a)

    assert FuenteEstado.objects.filter(org=org_a, activa=True).count() == 0


def test_3_el_alta_es_idempotente_y_no_pisa_la_configuracion(org_a):
    fuentes.asegurar_fuentes(org_a)
    FuenteEstado.objects.filter(org=org_a, fuente=Fuente.SMARTOLT).update(
        frecuencia_segundos=60, activa=True)

    creadas = fuentes.asegurar_fuentes(org_a)

    assert creadas == []
    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.SMARTOLT)
    #  Si una segunda llamada reescribiera los defaults, el ajuste que alguien
    #  hizo desde operacion se perderia en el proximo sondeo.
    assert f.frecuencia_segundos == 60
    assert f.activa is True


def test_4_una_fuente_sin_consultar_dice_que_no_se_sabe(org_a):
    fuentes.asegurar_fuentes(org_a)
    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.DEXTER)

    #  NO_CONSULTADA, no "sin registros": son cosas distintas y es la razon de
    #  ser de esta tabla.
    assert f.estado == EstadoLectura.NO_CONSULTADA
    assert f.registros is None, "NULL no es 0: 0 seria 'consultada y vacia'"
    assert f.concluyente is False


def test_5_la_base_impide_una_frecuencia_en_bucle(org_a):
    from django.db.utils import IntegrityError

    fuentes.asegurar_fuentes(org_a)
    with pytest.raises(IntegrityError):
        FuenteEstado.objects.filter(org=org_a, fuente=Fuente.M02).update(
            frecuencia_segundos=0)


def test_6_la_base_impide_un_error_sin_motivo(org_a):
    from django.db.utils import IntegrityError

    fuentes.asegurar_fuentes(org_a)
    with pytest.raises(IntegrityError):
        FuenteEstado.objects.filter(org=org_a, fuente=Fuente.M02).update(
            estado=EstadoLectura.ERROR, error_tecnico="")


def test_7_una_fuente_no_se_duplica_por_organizacion(org_a):
    from django.db.utils import IntegrityError

    fuentes.asegurar_fuentes(org_a)
    with pytest.raises(IntegrityError):
        FuenteEstado.objects.create(org=org_a, fuente=Fuente.M02)


# =============================================================================
#  §2  ACTIVA / INACTIVA, Y CUANDO TOCA
# =============================================================================

def test_8_una_fuente_inactiva_no_se_consulta(org_a):
    _fuente(org_a, Fuente.M02, activa=False)

    informe = fuentes.sondear(org_a)

    assert informe["sondeadas"] == 0
    assert FuenteSnapshot.objects.filter(org=org_a).count() == 0


def test_9_una_fuente_nunca_consultada_vence_ya(org_a):
    f = _fuente(org_a, Fuente.M02, proxima_consulta_en=None)

    assert f in fuentes.vencidas(org_a)


def test_10_una_fuente_que_no_vencio_no_se_consulta(org_a):
    ahora = timezone.now()
    _fuente(org_a, Fuente.M02,
            proxima_consulta_en=ahora + timezone.timedelta(minutes=10))

    assert fuentes.vencidas(org_a, ahora) == []
    assert fuentes.sondear(org_a, ahora=ahora)["sondeadas"] == 0


def test_11_consultar_corre_la_proxima_hacia_adelante(org_a):
    ahora = timezone.now()
    f = _fuente(org_a, Fuente.M02, frecuencia_segundos=900)

    fuentes.sondear(org_a, ahora=ahora)

    f.refresh_from_db()
    assert f.proxima_consulta_en is not None
    #  Desde AHORA y no desde el vencimiento viejo: encadenar desde el vencido
    #  dispararia una rafaga para "ponerse al dia" contra un tercero.
    assert abs((f.proxima_consulta_en - ahora).total_seconds() - 900) < 2


def test_12_una_fuente_caida_mucho_tiempo_no_genera_una_rafaga(org_a):
    #  La fuente vencio hace DOS HORAS. Tras un sondeo tiene que quedar a un
    #  intervalo de ahora, no acumular ocho consultas pendientes.
    ahora = timezone.now()
    f = _fuente(org_a, Fuente.M02, frecuencia_segundos=900,
                proxima_consulta_en=ahora - timezone.timedelta(hours=2))

    fuentes.sondear(org_a, ahora=ahora)

    f.refresh_from_db()
    assert f.proxima_consulta_en > ahora
    assert fuentes.vencidas(org_a, ahora) == []


# =============================================================================
#  §3  EXITOSA, VACIA, CON ERROR, CON TIMEOUT
# =============================================================================

def test_13_consulta_exitosa(org_a):
    _caso_abierto(org_a)
    f = _fuente(org_a, Fuente.DEXTER)

    fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.CON_DATOS
    assert f.registros == 1
    assert f.concluyente is True
    assert f.fallos_consecutivos == 0
    assert f.ultimo_exito_en is not None


def test_14_fuente_vacia_es_SIN_REGISTROS_y_no_un_error(org_a):
    #  M02 esta vacia en produccion de verdad (0 actividades medidas). La
    #  respuesta correcta es "consultada, sin registros", no un error ni un
    #  silencio.
    f = _fuente(org_a, Fuente.M02)

    fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.SIN_REGISTROS
    assert f.registros == 0, "0 aqui SI significa cero: se pudo preguntar"
    assert f.error_tecnico == ""
    #  Y se puede concluir: preguntamos y no hay nada.
    assert f.concluyente is True


def test_15_un_error_de_fuente_NO_es_cero(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT)
    motor = Motor(excepcion=RuntimeError("se cayo la red"))

    with _con_motor(motor):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.ERROR
    #  LO QUE IMPORTA: registros queda en None, NO en 0. Un 0 aqui diria "no hay
    #  caidas en la red" cuando la verdad es que no se pudo mirar.
    assert f.registros is None
    assert f.concluyente is False
    assert f.error_tecnico
    assert f.fallos_consecutivos == 1


def test_16_un_timeout_es_un_error_y_se_identifica_por_tipo(org_a):
    import requests

    f = _fuente(org_a, Fuente.SMARTOLT)
    motor = Motor(excepcion=requests.exceptions.Timeout(
        "http://motor-de-prueba:5000/interno/herramienta/x"))

    with _con_motor(motor):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.ERROR
    assert "Timeout" in f.error_tecnico
    #  La URL NO viaja al mensaje: una URL de SmartOLT lleva el identificador
    #  del equipo de un cliente.
    assert "motor-de-prueba" not in f.error_tecnico
    assert f.registros is None


def test_17_un_HTTP_no_200_tampoco_es_cero(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT)

    with _con_motor(Motor(RespuestaFalsa(500))):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.ERROR
    assert "500" in f.error_tecnico
    assert f.registros is None


def test_18_los_fallos_consecutivos_se_cuentan(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT, frecuencia_segundos=30)
    ahora = timezone.now()

    #  El tiempo AVANZA entre consultas. Sin esto la fuente no vuelve a vencer
    #  y el bucle corre una sola vez creyendo correr tres -- la primera version
    #  de esta prueba media 1 y afirmaba 3.
    for i in range(3):
        with _con_motor(Motor(RespuestaFalsa(500))):
            fuentes.sondear(org_a,
                            ahora=ahora + timezone.timedelta(minutes=10 * i))

    f.refresh_from_db()
    #  Una fuente que falla SIEMPRE es un problema distinto de una que fallo
    #  una vez, y el numero es lo que permite distinguirlos.
    assert f.fallos_consecutivos == 3


def test_19_un_exito_despues_de_fallos_reinicia_la_racha(org_a):
    _caso_abierto(org_a)
    f = _fuente(org_a, Fuente.DEXTER, fallos_consecutivos=5,
                estado=EstadoLectura.ERROR, error_tecnico="algo")

    fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.fallos_consecutivos == 0
    assert f.error_tecnico == ""


def test_20_una_excepcion_de_una_fuente_no_se_lleva_a_las_demas(org_a):
    _fuente(org_a, Fuente.M02)
    _fuente(org_a, Fuente.M03)

    def revienta(org, estado_fuente, ahora):
        raise RuntimeError("explotó")

    adaptadores = dict(fuentes_adaptadores.POR_FUENTE)
    adaptadores[Fuente.M02] = revienta

    informe = fuentes.sondear(org_a, adaptadores=adaptadores)

    assert informe["sondeadas"] == 2
    assert informe["por_fuente"][Fuente.M02]["estado"] == EstadoLectura.ERROR
    #  La otra se consulto igual. Al reves, cinco fuentes quedarian mudas por
    #  culpa de una y nada lo explicaria.
    assert informe["por_fuente"][Fuente.M03]["estado"] in (
        EstadoLectura.CON_DATOS, EstadoLectura.SIN_REGISTROS)


def test_21_una_fuente_sin_adaptador_es_NO_DISPONIBLE_con_motivo(org_a):
    _fuente(org_a, Fuente.M02)

    informe = fuentes.sondear(org_a, adaptadores={})

    detalle = informe["por_fuente"][Fuente.M02]
    assert detalle["estado"] == EstadoLectura.NO_DISPONIBLE
    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.M02)
    assert "adaptador" in f.motivo_no_disponible


# =============================================================================
#  §4  FRESCURA
# =============================================================================

def test_22_un_dato_reciente_es_fresco(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT, antiguedad_maxima_segundos=900)
    ahora = timezone.now()
    lectura = fuentes.Lectura(
        EstadoLectura.CON_DATOS, datos={"x": 1}, registros=1,
        dato_en=ahora - timezone.timedelta(minutes=2), esquema="e")

    assert fuentes.frescura_de(lectura, f, ahora) == Frescura.FRESCA


def test_23_un_dato_viejo_NO_se_presenta_como_estado_actual(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT, antiguedad_maxima_segundos=900)
    ahora = timezone.now()
    lectura = fuentes.Lectura(
        EstadoLectura.CON_DATOS, datos={"x": 1}, registros=1,
        dato_en=ahora - timezone.timedelta(hours=1), esquema="e")

    assert fuentes.frescura_de(lectura, f, ahora) == Frescura.VIEJA

    snap = fuentes.registrar(f, lectura, inicio=ahora, ahora=ahora)
    f.refresh_from_db()
    #  La consulta salio BIEN y el dato esta viejo: dos ejes distintos. Y no se
    #  puede concluir del dato viejo, aunque la lectura fuera un exito.
    assert snap.estado == EstadoLectura.CON_DATOS
    assert f.frescura == Frescura.VIEJA
    assert f.concluyente is False


def test_24_sin_fecha_la_frescura_es_DESCONOCIDA_y_no_fresca(org_a):
    f = _fuente(org_a, Fuente.WISPHUB)
    ahora = timezone.now()
    lectura = fuentes.Lectura(EstadoLectura.CON_DATOS, datos={"x": 1},
                              registros=1, dato_en=None, esquema="e")

    #  El atajo tentador --tomar 'ahora'-- volveria fresco cualquier dato por
    #  definicion.
    assert fuentes.frescura_de(lectura, f, ahora) == Frescura.DESCONOCIDA


def test_25_un_error_no_tiene_dato_que_fechar(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT)
    ahora = timezone.now()
    lectura = fuentes.Lectura(EstadoLectura.ERROR, error_tecnico="x")

    assert fuentes.frescura_de(lectura, f, ahora) == Frescura.SIN_DATO


def test_26_una_fecha_en_el_futuro_no_se_toma_como_fresca(org_a):
    #  Un reloj desfasado del proveedor. Presentarlo como fresco esconderia el
    #  problema; se dice que no se sabe, que es lo que de verdad se sabe.
    f = _fuente(org_a, Fuente.SMARTOLT)
    ahora = timezone.now()
    lectura = fuentes.Lectura(
        EstadoLectura.CON_DATOS, datos={"x": 1}, registros=1,
        dato_en=ahora + timezone.timedelta(hours=3), esquema="e")

    assert fuentes.frescura_de(lectura, f, ahora) == Frescura.DESCONOCIDA


def test_27_la_antiguedad_maxima_es_por_fuente(org_a):
    ahora = timezone.now()
    estricta = _fuente(org_a, Fuente.SMARTOLT, antiguedad_maxima_segundos=60)
    holgada = _fuente(org_a, Fuente.M03, antiguedad_maxima_segundos=7200)
    lectura = fuentes.Lectura(
        EstadoLectura.CON_DATOS, datos={"x": 1}, registros=1,
        dato_en=ahora - timezone.timedelta(minutes=30), esquema="e")

    assert fuentes.frescura_de(lectura, estricta, ahora) == Frescura.VIEJA
    assert fuentes.frescura_de(lectura, holgada, ahora) == Frescura.FRESCA


# =============================================================================
#  §5  LA VENTANA INCONCLUSA  --  el vacio que todavia no significa nada
# =============================================================================

def test_28_un_vacio_dentro_de_la_ventana_es_INCONCLUSO(org_a):
    #  Los desarrolladores de SmartOLT informaron que 'get_outage_pons' agrupa
    #  con 2 a 5 minutos de retraso. Un vacio en esa ventana NO prueba que no
    #  haya una caida de red: prueba que el proveedor no la agrupo todavia.
    ahora = timezone.now()
    f = _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=300,
                ultimo_exito_en=ahora - timezone.timedelta(minutes=1))

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT_LIMPIO))):
        fuentes.sondear(org_a, ahora=ahora)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.INCONCLUSA
    assert f.concluyente is False, (
        "una respuesta vacia dentro de la ventana no autoriza a decir que la "
        "red esta sana")


def test_29_pasada_la_ventana_el_mismo_vacio_SI_concluye(org_a):
    ahora = timezone.now()
    f = _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=300,
                ultimo_exito_en=ahora - timezone.timedelta(minutes=30))

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT_LIMPIO))):
        fuentes.sondear(org_a, ahora=ahora)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.SIN_REGISTROS
    assert f.concluyente is True


def test_30_la_primera_lectura_vacia_con_ventana_es_inconclusa(org_a):
    #  Sin un exito previo no hay desde cuando contar. El lado prudente es no
    #  concluir.
    f = _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=300,
                ultimo_exito_en=None)

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT_LIMPIO))):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.INCONCLUSA


def test_31_una_fuente_sin_ventana_no_tiene_estado_inconcluso(org_a):
    #  La ventana es de SmartOLT por una razon medida. M02 no la tiene, y su
    #  vacio significa exactamente lo que dice.
    f = _fuente(org_a, Fuente.M02, ventana_inconclusa_segundos=0)

    fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.SIN_REGISTROS


def test_32_una_lectura_con_datos_nunca_es_inconclusa(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=300,
                ultimo_exito_en=None)

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT))):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.CON_DATOS


# =============================================================================
#  §6  SNAPSHOTS Y COMPARACION ENTRE CICLOS
# =============================================================================

def test_33_cada_consulta_deja_una_captura(org_a):
    _fuente(org_a, Fuente.M02, frecuencia_segundos=30)

    fuentes.sondear(org_a)
    fuentes.sondear(org_a, ahora=timezone.now() + timezone.timedelta(hours=1))

    assert FuenteSnapshot.objects.filter(org=org_a,
                                         fuente=Fuente.M02).count() == 2


def test_34_la_comparacion_da_la_diferencia_que_pide_el_bloque(org_a):
    #  El ejemplo literal del bloque: un PON que pasa de 1 ONT caida a 12. La
    #  diferencia tiene que quedar disponible como +11.
    f = _fuente(org_a, Fuente.SMARTOLT)
    ahora = timezone.now()

    antes = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"3/1/4": {"afectados": 1, "abonados": 103}},
                           dato_en=ahora, esquema="smartolt_pon_v1"),
        inicio=ahora, ahora=ahora)
    luego = ahora + timezone.timedelta(minutes=5)
    despues = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"3/1/4": {"afectados": 12, "abonados": 103}},
                           dato_en=luego, esquema="smartolt_pon_v1"),
        inicio=luego, ahora=luego)

    diff = fuentes.comparar(antes, despues)

    assert diff["comparable"] is True
    assert diff["cambiaron"]["3/1/4"]["afectados"] == {
        "antes": 1, "ahora": 12, "delta": 11}
    #  'abonados' no cambio y por eso no aparece: el diff informa cambios, no
    #  repite el estado entero.
    assert "abonados" not in diff["cambiaron"]["3/1/4"]


def test_35_un_PON_nuevo_aparece_y_uno_que_se_recupero_desaparece(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT)
    ahora = timezone.now()
    antes = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"3/1/4": {"afectados": 2}},
                           dato_en=ahora, esquema="smartolt_pon_v1"),
        inicio=ahora, ahora=ahora)
    luego = ahora + timezone.timedelta(minutes=5)
    despues = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"3/2/7": {"afectados": 30}},
                           dato_en=luego, esquema="smartolt_pon_v1"),
        inicio=luego, ahora=luego)

    diff = fuentes.comparar(antes, despues)

    assert diff["aparecieron"] == ["3/2/7"]
    assert diff["desaparecieron"] == ["3/1/4"]


def test_36_sin_captura_anterior_no_hay_comparacion_y_se_dice(org_a):
    f = _fuente(org_a, Fuente.M02)
    ahora = timezone.now()
    snap = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.SIN_REGISTROS, registros=0,
                           esquema="m02_actividades_v1"),
        inicio=ahora, ahora=ahora)

    diff = fuentes.comparar(None, snap)

    assert diff["comparable"] is False
    assert "anterior" in diff["motivo"]


def test_37_no_se_comparan_esquemas_distintos(org_a):
    #  Si el adaptador cambio de forma, la diferencia seria del cambio de forma
    #  y no del mundo. Decirlo es un resultado honesto, no un fallo.
    f = _fuente(org_a, Fuente.SMARTOLT)
    ahora = timezone.now()
    a = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"x": {"n": 1}}, dato_en=ahora,
                           esquema="smartolt_pon_v1"),
        inicio=ahora, ahora=ahora)
    luego = ahora + timezone.timedelta(minutes=5)
    b = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"x": {"n": 9}}, dato_en=luego,
                           esquema="smartolt_pon_v2"),
        inicio=luego, ahora=luego)

    diff = fuentes.comparar(a, b)

    assert diff["comparable"] is False
    assert "esquemas distintos" in diff["motivo"]


def test_38_no_se_compara_contra_una_lectura_que_no_concluye(org_a):
    #  LA TRAMPA QUE ESTO EVITA: si SmartOLT fallo, su captura no tiene PONs. Un
    #  diff contra ella diria "desaparecieron 40 PONs, la red se recupero", que
    #  es exactamente lo contrario de lo que paso.
    f = _fuente(org_a, Fuente.SMARTOLT)
    ahora = timezone.now()
    bueno = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"3/1/4": {"afectados": 40}},
                           dato_en=ahora, esquema="smartolt_pon_v1"),
        inicio=ahora, ahora=ahora)
    luego = ahora + timezone.timedelta(minutes=5)
    malo = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.ERROR, error_tecnico="500",
                           esquema="smartolt_pon_v1"),
        inicio=luego, ahora=luego)

    diff = fuentes.comparar(bueno, malo)

    assert diff["comparable"] is False
    assert "no es concluyente" in diff["motivo"]


def test_39_los_snapshots_no_crecen_sin_techo(org_a):
    f = _fuente(org_a, Fuente.M02)
    ahora = timezone.now()
    for i in range(fuentes.SNAPSHOTS_QUE_SE_CONSERVAN + 7):
        fuentes.registrar(
            f, fuentes.Lectura(EstadoLectura.SIN_REGISTROS, registros=0,
                               esquema="m02_actividades_v1"),
            inicio=ahora, ahora=ahora + timezone.timedelta(minutes=i))

    assert (FuenteSnapshot.objects.filter(org=org_a, fuente=Fuente.M02).count()
            == fuentes.SNAPSHOTS_QUE_SE_CONSERVAN)


def test_40_la_poda_conserva_los_MAS_RECIENTES(org_a):
    f = _fuente(org_a, Fuente.M02)
    ahora = timezone.now()
    for i in range(fuentes.SNAPSHOTS_QUE_SE_CONSERVAN + 3):
        fuentes.registrar(
            f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=i,
                               datos={"n": {"i": i}}, dato_en=ahora,
                               esquema="m02_actividades_v1"),
            inicio=ahora, ahora=ahora + timezone.timedelta(minutes=i))

    ultimo = fuentes.ultimo_snapshot(org_a, Fuente.M02)
    assert ultimo.registros == fuentes.SNAPSHOTS_QUE_SE_CONSERVAN + 2


def test_41_un_resumen_desbordado_se_corta_y_lo_dice(org_a):
    f = _fuente(org_a, Fuente.M02)
    ahora = timezone.now()
    enorme = {f"k{i}": {"n": i}
              for i in range(fuentes.TOPE_CLAVES_DEL_RESUMEN + 50)}

    snap = fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1, datos=enorme,
                           dato_en=ahora, esquema="e"),
        inicio=ahora, ahora=ahora)

    #  Un recorte SILENCIOSO haria que el diff informara diferencias que son del
    #  recorte y no del mundo.
    assert "_truncado" in snap.datos
    assert len(snap.datos) == fuentes.TOPE_CLAVES_DEL_RESUMEN + 1


# =============================================================================
#  §7  MULTI-TENANT
# =============================================================================

def test_42_el_sondeo_de_una_organizacion_no_toca_la_otra(org_a, org_b):
    _fuente(org_a, Fuente.M02)
    _fuente(org_b, Fuente.M02)

    fuentes.sondear(org_a)

    assert FuenteSnapshot.objects.filter(org=org_a).count() == 1
    assert FuenteSnapshot.objects.filter(org=org_b).count() == 0
    assert (FuenteEstado.objects.get(org=org_b, fuente=Fuente.M02).estado
            == EstadoLectura.NO_CONSULTADA)


def test_43_los_datos_de_una_organizacion_no_entran_en_el_resumen_de_otra(
        org_a, org_b, rls_org_factory=None):
    #  Toda la carga esta en B; se sondea A. Si el adaptador olvidara el filtro
    #  de organizacion, A informaria los casos de B.
    from conftest import rls_org

    with rls_org(org_b):
        _caso_abierto(org_b)
        _caso_abierto(org_b)

    _fuente(org_a, Fuente.DEXTER)
    fuentes.sondear(org_a)

    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.DEXTER)
    assert f.registros == 0
    assert f.estado == EstadoLectura.SIN_REGISTROS


def test_44_la_comparacion_no_cruza_organizaciones(org_a, org_b):
    from conftest import rls_org

    ahora = timezone.now()
    fa = _fuente(org_a, Fuente.SMARTOLT)
    fuentes.registrar(
        fa, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                            datos={"3/1/4": {"afectados": 1}}, dato_en=ahora,
                            esquema="smartolt_pon_v1"),
        inicio=ahora, ahora=ahora)

    with rls_org(org_b):
        #  B no tiene ninguna captura: su comparacion no puede encontrar la de A.
        assert fuentes.ultimo_snapshot(org_b, Fuente.SMARTOLT) is None


# =============================================================================
#  §8  CADA FUENTE
# =============================================================================

def test_45_smartolt_resume_por_PON_con_el_sobre_real(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=0)

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT))) as motor:
        fuentes.sondear(org_a)

    assert len(motor.llamadas) == 1
    assert "/interno/herramienta/consultar_caidas_pon_1" in motor.llamadas[0]["url"]
    #  El tenant viaja: sin el, el motor no sabe de que empresa es la consulta.
    assert motor.llamadas[0]["params"]["tenant"] == "rapilink"

    snap = fuentes.ultimo_snapshot(org_a, Fuente.SMARTOLT)
    assert snap.estado == EstadoLectura.CON_DATOS
    assert "3/1/3" in snap.datos, snap.datos
    fila = snap.datos["3/1/3"]
    assert fila["afectados"] == 8
    assert fila["abonados"] == 8
    #  Los conteos de SmartOLT llegan como TEXTO ('total_onus': '103') y se
    #  convierten; un int() crudo sobre un campo vacio reventaria la sonda.
    assert fila["total_onus"] == 103
    assert fila["los"] == 8
    assert fila["tipo"] == "partial_los"
    assert fila["caja"] == "CTO 56"


def test_46_smartolt_fecha_el_dato_con_el_sello_del_proveedor(org_a):
    f = _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=0)

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT))):
        fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.SMARTOLT)
    #  'partial_last_seen_at' es preciso al minuto segun el proveedor, no una
    #  estimacion. Es lo que permite decir si la foto es de ahora.
    assert snap.dato_en is not None
    assert snap.dato_en.year == 2026


def test_47_smartolt_sin_la_herramienta_declarada_es_NO_DISPONIBLE(org_a):
    #  ES EL ESTADO REAL HOY: ninguna herramienta de SmartOLT esta declarada
    #  'invocable_por_servicio'. El motor contesta 404/403 y la fuente queda NO
    #  DISPONIBLE con el motivo -- nunca "sin caidas".
    f = _fuente(org_a, Fuente.SMARTOLT)

    with _con_motor(Motor(RespuestaFalsa(403, {"error": "no declarada"}))):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.NO_DISPONIBLE
    assert f.registros is None
    assert f.concluyente is False
    assert "invocable_por_servicio" in f.motivo_no_disponible


def test_48_smartolt_conserva_una_OLT_inalcanzable(org_a):
    #  Una OLT que no se pudo alcanzar NO es una OLT sin caidas.
    sobre = {"resultado": {"response": {
        "sections": [], "unreachable_olts": ["4"]}}}
    _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=0)

    with _con_motor(Motor(RespuestaFalsa(200, sobre))):
        fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.SMARTOLT)
    assert snap.datos["_olts_inalcanzables"]["cuantas"] == 1


def test_49_smartolt_con_dos_OLTs_pregunta_por_las_dos(org_a):
    import os

    _fuente(org_a, Fuente.SMARTOLT, ventana_inconclusa_segundos=0)
    motor = Motor(RespuestaFalsa(200, SOBRE_SMARTOLT_LIMPIO))

    with _con_motor(motor):
        with mock.patch.dict(os.environ, {
                "SUPERVISOR_HERRAMIENTAS_CAIDAS_PON":
                    "consultar_caidas_pon_1,consultar_caidas_pon_2"}):
            fuentes.sondear(org_a)

    assert len(motor.llamadas) == 2
    pedidas = [l["url"].rsplit("/", 1)[-1] for l in motor.llamadas]
    assert pedidas == ["consultar_caidas_pon_1", "consultar_caidas_pon_2"]


def test_50_si_UNA_OLT_falla_la_lectura_entera_es_un_error(org_a):
    #  Devolver lo que trajeron las otras haria leer "en esa OLT no hay caidas".
    #  Es mejor no saber de ninguna que creer saber de todas.
    import os

    f = _fuente(org_a, Fuente.SMARTOLT)
    motor = Motor(por_herramienta={
        "consultar_caidas_pon_1": RespuestaFalsa(200, SOBRE_SMARTOLT),
        "consultar_caidas_pon_2": RespuestaFalsa(500),
    })

    with _con_motor(motor):
        with mock.patch.dict(os.environ, {
                "SUPERVISOR_HERRAMIENTAS_CAIDAS_PON":
                    "consultar_caidas_pon_1,consultar_caidas_pon_2"}):
            fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.ERROR
    assert f.registros is None


def test_51_sin_MOTOR_TENANT_no_se_consulta_y_se_dice(org_a):
    import os

    f = _fuente(org_a, Fuente.SMARTOLT)
    motor = Motor(RespuestaFalsa(200, SOBRE_SMARTOLT))

    #  LA HERRAMIENTA SE DECLARA A PROPOSITO. Desde que se revirtio la config
    #  fija de SmartOLT (02/10/2026), sin herramientas declaradas el adaptador
    #  contesta NO_DISPONIBLE ANTES de intentar la llamada -- y entonces esta
    #  prueba no alcanzaria el camino que quiere medir, que es el fail-closed del
    #  tenant. El caso "sin herramientas" tiene su propia prueba abajo.
    with mock.patch("requests.post", motor.post):
        with mock.patch.dict(os.environ, {
                "MOTOR_TENANT": "",
                "SUPERVISOR_HERRAMIENTAS_CAIDAS_PON": "consultar_caidas_pon_1",
        }, clear=False):
            fuentes.sondear(org_a)

    f.refresh_from_db()
    #  Fail-closed: suponer el tenant leeria los datos de otra empresa.
    assert f.estado == EstadoLectura.ERROR
    assert "MOTOR_TENANT" in f.error_tecnico
    assert motor.llamadas == [], "no tenia que salir ninguna peticion"


def test_51b_sin_herramienta_declarada_es_NO_DISPONIBLE_nunca_sin_caidas(org_a):
    """
    EL ESTADO REAL DE SMARTOLT HOY: no hay herramienta de flota declarada.

    Se revirtio la config fija ('SMARTOLT_OLT_ID_1/_2' y las dos herramientas
    duplicadas) al descubrir que el repositorio ya descubre las OLTs con
    'get_olts' -- 'cli/reporte_incidentes_red.py::_olts()' lo hace, y
    'nucleo/herramientas/incidentes.py' ya encadena get_onu_details ->
    get_outage_pons. Configurar los ids a mano era la forma equivocada.

    Lo que esta prueba fija es lo unico que importa mientras eso no exista: que la
    fuente diga NO_DISPONIBLE con su motivo, y JAMAS "sin caidas". Un cero aqui
    afirmaria que la red esta sana sin haberla mirado.
    """
    import os

    f = _fuente(org_a, Fuente.SMARTOLT)
    motor = Motor(RespuestaFalsa(200, SOBRE_SMARTOLT))

    with mock.patch("requests.post", motor.post):
        with mock.patch.dict(os.environ, {
                "MOTOR_TENANT": "rapilink",
                "SUPERVISOR_HERRAMIENTAS_CAIDAS_PON": "",
        }, clear=False):
            fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.NO_DISPONIBLE
    assert f.registros is None, "NULL, no 0: no se pudo mirar"
    assert f.concluyente is False
    assert "get_olts" in f.motivo_no_disponible
    assert motor.llamadas == [], "no sale ninguna peticion sin herramienta"


def test_52_wisphub_pide_UN_ESTADO_POR_VEZ(org_a):
    #  '?estado=1&estado=2' NO los une: se queda con el ultimo (verificado el
    #  09/09/2026). Mandar la lista traeria un estado sin avisar y el resumen
    #  diria menos tickets de los que hay.
    _fuente(org_a, Fuente.WISPHUB)
    motor = Motor(RespuestaFalsa(200, {"resultado": {"count": 7}}))

    with _con_motor(motor):
        fuentes.sondear(org_a)

    assert len(motor.llamadas) == 2
    estados = sorted(l["cuerpo"]["estado"] for l in motor.llamadas)
    assert estados == [1, 2]
    #  Y la ventana de fechas es obligatoria: sin filtro esta API aplica un
    #  recorte propio que no sirve para comparar nada.
    for llamada in motor.llamadas:
        assert llamada["cuerpo"]["fecha_creacion_0"]
        assert llamada["cuerpo"]["fecha_creacion_1"]


def test_53_wisphub_suma_los_estados_y_no_inventa_frescura(org_a):
    _fuente(org_a, Fuente.WISPHUB)

    with _con_motor(Motor(RespuestaFalsa(200, {"resultado": {"count": 7}}))):
        fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.WISPHUB)
    assert snap.registros == 14
    assert snap.datos["ventana"]["tickets"] == 14
    #  La API no fecha la RESPUESTA, asi que 'dato_en' queda en None y la
    #  frescura es DESCONOCIDA. Decir 'ahora' afirmaria algo que nadie dijo.
    assert snap.dato_en is None
    assert snap.frescura == Frescura.DESCONOCIDA


def test_54_wisphub_con_un_estado_caido_NO_devuelve_un_resumen_parcial(org_a):
    f = _fuente(org_a, Fuente.WISPHUB)
    #  El primer estado contesta, el segundo no. Un resumen incompleto haria
    #  bajar el numero de tickets sin motivo y nadie lo notaria.
    respuestas = [RespuestaFalsa(200, {"resultado": {"count": 7}}),
                  RespuestaFalsa(502)]

    class Alternante(Motor):
        def post(self, *a, **k):
            super().post(*a, **k)
            return respuestas[min(len(self.llamadas) - 1,
                                  len(respuestas) - 1)]

    with _con_motor(Alternante()):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.ERROR
    assert f.registros is None


def test_55_wisphub_sin_conteo_reconocible_es_error_y_no_cero(org_a):
    f = _fuente(org_a, Fuente.WISPHUB)

    with _con_motor(Motor(RespuestaFalsa(200, {"resultado": {"raro": True}}))):
        fuentes.sondear(org_a)

    f.refresh_from_db()
    assert f.estado == EstadoLectura.ERROR
    assert f.registros is None


def test_56_dexter_cuenta_los_casos_abiertos_por_estado(org_a):
    _caso_abierto(org_a, status="New")
    _caso_abierto(org_a, status="Assigned")
    _caso_abierto(org_a, status="New")
    _fuente(org_a, Fuente.DEXTER)

    fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.DEXTER)
    assert snap.datos["estado_New"]["casos"] == 2
    assert snap.datos["estado_Assigned"]["casos"] == 1
    assert snap.datos["totales"]["abiertos"] == 3


def test_57_dexter_no_infla_el_conteo_con_varios_asignados(org_a,
                                                           admin_profile,
                                                           user_profile):
    #  'Case.assigned_to' es un ManyToMany. Un Count con 'filter=' sobre un M2M
    #  cuenta FILAS DEL JOIN: un caso con dos personas asignadas se contaria DOS
    #  VECES y "con_asignado" superaria el total de abiertos.
    #
    #  HACEN FALTA DOS ASIGNADOS PARA QUE SE VEA, y la primera version de esta
    #  prueba ponia uno. Con uno, quitar 'distinct=True' no cambia nada y la
    #  mutacion SOBREVIVIA (medido el 02/10/2026): la prueba afirmaba la
    #  propiedad correcta sobre un caso que no podia violarla.
    caso = _caso_abierto(org_a)
    caso.assigned_to.add(admin_profile)
    caso.assigned_to.add(user_profile)
    #  Y uno SIN asignar, para que la resta tenga algo que restar.
    _caso_abierto(org_a)
    _fuente(org_a, Fuente.DEXTER)

    fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.DEXTER)
    totales = snap.datos["totales"]
    assert totales["abiertos"] == 2, "dos casos, no cuatro filas de join"
    assert totales["con_asignado"] == 1, (
        "UN caso con dos asignados es un caso, no dos")
    assert totales["sin_asignar"] == 1
    assert totales["con_asignado"] <= totales["abiertos"]
    #  Y el conteo por estado tampoco se infla.
    assert snap.datos["estado_New"]["casos"] == 2
    assert snap.registros == 2


def test_58_dexter_vacio_es_sin_registros(org_a):
    _fuente(org_a, Fuente.DEXTER)

    fuentes.sondear(org_a)

    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.DEXTER)
    assert f.estado == EstadoLectura.SIN_REGISTROS
    assert f.registros == 0


def test_59_sla_reutiliza_la_logica_existente_sin_recalcularla(org_a):
    from operaciones import sla as sla_modulo

    _orden(org_a)
    _fuente(org_a, Fuente.SLA)

    fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.SLA)
    #  Los seis estados salen de 'operaciones/sla.py' y no se reinterpretan.
    #  Cualquier clave que aparezca tiene que ser uno de los suyos.
    validos = {sla_modulo.VENCIDA, sla_modulo.VENCE_PRONTO, sla_modulo.A_TIEMPO,
               sla_modulo.SIN_PLAZO, sla_modulo.NO_APLICA,
               sla_modulo.DATOS_INSUFICIENTES}
    for clave in snap.datos:
        if clave.startswith("estado_"):
            assert clave[len("estado_"):] in validos, clave
    assert snap.datos["totales"]["ordenes_abiertas"] == 1


def test_60_sla_no_esconde_DATOS_INSUFICIENTES(org_a):
    #  Es la diferencia entre "va a tiempo" y "no se puede decir si va a
    #  tiempo". Juntarlas es lo que esta capa combate.
    from operaciones import sla as sla_modulo

    _orden(org_a)
    _fuente(org_a, Fuente.SLA)

    fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.SLA)
    con_estado = [k for k in snap.datos if k.startswith("estado_")]
    assert con_estado, "alguna orden tiene que haber quedado clasificada"
    #  La suma de los estados es el total: ninguna orden se perdio por el
    #  camino, incluidas las que no se pueden clasificar.
    suma = sum(snap.datos[k]["ordenes"] for k in con_estado)
    assert suma == snap.datos["totales"]["ordenes_abiertas"]


def test_61_m02_vacio_en_produccion_se_registra_como_tal(org_a):
    _fuente(org_a, Fuente.M02)

    fuentes.sondear(org_a)

    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.M02)
    assert f.estado == EstadoLectura.SIN_REGISTROS
    assert f.registros == 0
    #  Lo que NO se hizo: inventar una actividad para que el tablero se vea
    #  poblado. Un cero con procedencia vale; un numero inventado no.
    assert ActividadOperativa.objects.filter(org=org_a).count() == 0


def test_62_m02_con_datos_cuenta_vencidas_y_bloqueadas(org_a, admin_profile):
    ahora = timezone.now()
    ActividadOperativa.objects.create(
        org=org_a, titulo="vencida", vence_en=ahora - timezone.timedelta(days=1))
    ActividadOperativa.objects.create(
        org=org_a, titulo="bloqueada", estado_operativo="bloqueada",
        motivo_bloqueo="falta material")
    _fuente(org_a, Fuente.M02)

    fuentes.sondear(org_a, ahora=ahora)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.M02)
    assert snap.datos["totales"]["actividades"] == 2
    assert snap.datos["totales"]["vencidas"] == 1
    assert snap.datos["totales"]["bloqueadas"] == 1
    assert snap.datos["totales"]["sin_responsable"] == 2


def test_63_m03_cuenta_ordenes_y_programacion(org_a):
    _orden(org_a)
    _orden(org_a, programada_para=timezone.now())
    _fuente(org_a, Fuente.M03)

    fuentes.sondear(org_a)

    snap = fuentes.ultimo_snapshot(org_a, Fuente.M03)
    assert snap.datos["ordenes"]["total"] == 2
    assert snap.datos["ordenes"]["sin_programar"] == 1
    assert snap.datos["novedades"]["total"] == 0


def test_64_m03_sin_nada_es_sin_registros(org_a):
    _fuente(org_a, Fuente.M03)

    fuentes.sondear(org_a)

    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.M03)
    assert f.estado == EstadoLectura.SIN_REGISTROS


def test_65_ningun_resumen_lleva_datos_de_cliente(org_a):
    #  Se afirma sobre el JSON SERIALIZADO y no sobre las claves del primer
    #  nivel: una evidencia anidada no se veria mirando solo arriba. Y el caso
    #  esta poblado a proposito -- con el nombre en blanco esto pasaria sin medir
    #  nada.
    _caso_abierto(org_a, name="Sofia Munoz sin internet")
    for nombre in (Fuente.DEXTER, Fuente.SLA, Fuente.M02, Fuente.M03):
        _fuente(org_a, nombre)
    _orden(org_a)

    fuentes.sondear(org_a)

    for snap in FuenteSnapshot.objects.filter(org=org_a):
        plano = json.dumps(snap.datos)
        assert "Sofia" not in plano, snap.fuente
        for prohibido in ("cedula", "telefono", "direccion", "gps_lat",
                          "gps_lng", "coordenadas", "password", "email"):
            assert prohibido not in plano, f"{snap.fuente}: {prohibido}"


# =============================================================================
#  §9  LO QUE NO HACE
# =============================================================================

def test_66_el_sondeo_no_produce_NINGUN_efecto_externo(org_a):
    for nombre in Fuente.TODAS:
        _fuente(org_a, nombre)
    _caso_abierto(org_a)
    _orden(org_a)

    motor = Motor(RespuestaFalsa(200, SOBRE_SMARTOLT_LIMPIO))
    with _con_motor(motor):
        fuentes.sondear(org_a)

    #  Lo unico que salio del proceso son las consultas de SOLO LECTURA por el
    #  motor. Se afirma sobre el VERBO y la ruta, no sobre la intencion.
    for llamada in motor.llamadas:
        assert "/interno/herramienta/" in llamada["url"]
        assert "cerrar-caso" not in llamada["url"]


def test_67_el_sondeo_no_crea_propuestas_ni_actividad(org_a):
    for nombre in Fuente.TODAS:
        _fuente(org_a, nombre)
    _caso_abierto(org_a)
    _orden(org_a)

    antes = (PropuestaSupervisor.objects.count(), Activity.objects.count(),
             Case.objects.count(), ActividadOperativa.objects.count(),
             OrdenTrabajo.objects.count())

    with _con_motor(Motor(RespuestaFalsa(200, SOBRE_SMARTOLT_LIMPIO))):
        fuentes.sondear(org_a)
        fuentes.sondear(org_a, ahora=timezone.now()
                        + timezone.timedelta(hours=2))

    assert (PropuestaSupervisor.objects.count(), Activity.objects.count(),
            Case.objects.count(), ActividadOperativa.objects.count(),
            OrdenTrabajo.objects.count()) == antes


def test_68_el_sondeo_no_corre_el_ciclo_del_supervisor(org_a):
    from operaciones import supervisor

    _fuente(org_a, Fuente.M02)
    with mock.patch.object(supervisor, "correr_ciclo") as ciclo:
        fuentes.sondear(org_a)

    #  Si alguien cambiara el sondeo por el ciclo, aqui se veria -- y con el
    #  conteo de propuestas de la prueba anterior tambien.
    ciclo.assert_not_called()


def test_69_el_sondeo_no_toca_el_interruptor_de_autonomia(org_a):
    #  Esta capa es de lectura y no eleva autonomia. No hay ninguna escritura a
    #  'asistente.interruptor_autonomia' en su camino, y se afirma sobre el
    #  CODIGO del modulo para que no dependa de que la prueba adivine el nombre
    #  de la tabla.
    import ast
    import inspect

    #  Se afirma sobre el AST --imports y llamadas-- y no sobre el texto: la
    #  palabra "interruptor" aparece en un comentario que dice justamente que no
    #  se toca, y una prueba que busca la palabra se pone en rojo por lo que no
    #  importa. Ya me paso con 'scheduler' en otra guarda el mismo dia.
    PROHIBIDOS = {"interruptor", "correr_ciclo", "registrar_propuesta",
                  "PropuestaSupervisor", "frontera", "idempotencia"}

    for modulo in (fuentes, fuentes_adaptadores):
        arbol = ast.parse(inspect.getsource(modulo))
        nombres = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    nombres.update(a.name.split("."))
            elif isinstance(nodo, ast.ImportFrom):
                nombres.update((nodo.module or "").split("."))
                nombres.update(a.name for a in nodo.names)
            elif isinstance(nodo, ast.Attribute):
                nombres.add(nodo.attr)
            elif isinstance(nodo, ast.Name):
                nombres.add(nodo.id)

        colados = nombres & PROHIBIDOS
        assert not colados, (modulo.__name__, sorted(colados))


def test_70_la_ruta_no_acepta_verbos_que_no_son_el_sondeo(org_a, admin_client,
                                                          admin_profile):
    for verbo in ("get", "put", "patch", "delete"):
        r = getattr(admin_client, verbo)(RUTA)
        assert r.status_code == 405, f"{verbo}: {r.status_code}"


# =============================================================================
#  §10  LA RUTA, IDEMPOTENCIA Y CONCURRENCIA
# =============================================================================

def test_71_la_ruta_sondea_y_devuelve_conteos(org_a, admin_client,
                                              admin_profile):
    FuenteEstado.objects.filter(org=org_a).delete()

    r = admin_client.post(RUTA)

    assert r.status_code == 200, r.content
    cuerpo = r.json()
    #  La primera llamada crea las seis filas, APAGADAS, asi que no sondea
    #  ninguna: crearlas no es encenderlas.
    assert cuerpo["fuentes_creadas"] == 6
    assert cuerpo["sondeadas"] == 0
    assert FuenteEstado.objects.filter(org=org_a, activa=True).count() == 0


def test_72_la_ruta_sondea_lo_que_este_activo(org_a, admin_client,
                                             admin_profile):
    _fuente(org_a, Fuente.M02)

    cuerpo = admin_client.post(RUTA).json()

    assert cuerpo["sondeadas"] == 1
    assert cuerpo["por_fuente"][Fuente.M02]["estado"] == (
        EstadoLectura.SIN_REGISTROS)


def test_73_la_ruta_sin_credencial_no_contesta(org_a, unauthenticated_client):
    r = unauthenticated_client.post(RUTA)

    assert r.status_code in (401, 403)
    assert b"por_fuente" not in r.content


def test_74_la_ruta_rechaza_otra_organizacion(org_a, org_b, admin_client,
                                              admin_profile):
    r = admin_client.post(f"{RUTA}?organization_id={org_b.id}")

    assert r.status_code == 409, r.content
    assert r.json()["error"] == "ORGANIZACION_DISTINTA"
    assert FuenteSnapshot.objects.filter(org=org_b).count() == 0


def test_75_dos_sondeos_seguidos_no_duplican_nada(org_a, admin_client,
                                                  admin_profile):
    #  No por una clave de idempotencia sino por el dato: al registrar se corre
    #  'proxima_consulta_en' hacia adelante, asi que el segundo no encuentra
    #  nada vencido. Se afirma contando snapshots.
    _fuente(org_a, Fuente.M02, frecuencia_segundos=900)

    primero = admin_client.post(RUTA).json()
    segundo = admin_client.post(RUTA).json()

    assert primero["sondeadas"] == 1
    assert segundo["sondeadas"] == 0
    assert FuenteSnapshot.objects.filter(org=org_a,
                                         fuente=Fuente.M02).count() == 1


def test_76_la_declaracion_de_permisos_de_la_ruta(org_a):
    #  DECLARACION, no efecto -- y la distincion esta medida: 'RequireOrgContext'
    #  rechaza antes de que DRF evalue permisos, asi que la prueba de arriba
    #  pasa igual si se le quitan. Esto impide un borrado silencioso.
    from rest_framework.permissions import IsAuthenticated

    from common.permissions import HasOrgContext
    from operaciones.views import SondeoFuentesView

    assert set(SondeoFuentesView.permission_classes) == {
        IsAuthenticated, HasOrgContext}


#  LA CONCURRENCIA VIVE EN SU PROPIO ARCHIVO, y no por estilo: necesita
#  'transaction=True', y pytest-django hace flush y reemite 'post_migrate'
#  despues de cada prueba asi. Con esta aqui se cayeron CUATRO pruebas de
#  concurrencia ajenas que venian en verde (test_m03e4_secuencia,
#  test_m03e5_jornada, test_m03g_capacidad) por un choque al re-dar de alta los
#  permisos. Esta en 'test_fuentes_concurrencia_postgres.py', siguiendo la
#  convencion que el repo ya tiene en 'campo/tests/' por el mismo motivo.
# =============================================================================
#  utilidad que usan varias
# =============================================================================

def _caso_abierto(org, **extra):
    datos = dict(org=org, name="Sin internet", status="New", priority="Normal")
    datos.update(extra)
    return Case.objects.create(**datos)
