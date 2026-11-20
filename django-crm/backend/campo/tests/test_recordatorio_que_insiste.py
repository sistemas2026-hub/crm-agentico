# -*- coding: utf-8 -*-
"""
================================================================================
 EL RECORDATORIO AVISABA UNA VEZ Y SE CALLABA  --  11/11/2026
================================================================================
EL PEDIDO DEL USUARIO
----------------------
    «el supervisor notifica solo la primera vez que no han reportado pero si
    despues del reporte no mandan nada queda asi no vuelve a notificar. Hay
    que poner que notifique hasta recibir el reporte: ejemplo primer reporte
    a los 30 minutos y si no recibe reporte a los 15 y si no recibe asi hasta
    recibir»

POR QUE AVISABA UNA SOLA VEZ, Y NO ERA UN DESCUIDO
---------------------------------------------------
La clave de idempotencia era `sin_reporte|<orden>|<referencia>`, y la
REFERENCIA es el ultimo reporte. Mientras el tecnico no reporta, la
referencia no se mueve, la clave es la misma y el reclamo por clave primaria
la rechaza. Eso es exactamente lo que el encabezado del 30/10 buscaba --«uno
por atraso, no uno cada 5 minutos», porque la tarea mira cada 5-- y el
efecto no deseado venia pegado: el que no reporta nunca, nunca vuelve a
saber de nadie.

Ahora la clave lleva tambien CUAL recordatorio es, y ese numero sube con el
tiempo: `sin_reporte|<orden>|<referencia>|2`.

LA GRILLA ES FIJA, NO ENCADENADA  --  y conviene saberlo
---------------------------------------------------------
El recordatorio N sale en el minuto `ventana + (N-1) * cada` contado desde
EL ULTIMO REPORTE, no «15 minutos despues del aviso anterior». Con 30 y 15:
los minutos 30, 45, 60, 75...

Se eligio asi por dos motivos. Es idempotente sin consultar nada --el numero
sale de una resta, no de buscar cuando se mando el ultimo aviso-- y no
acumula deriva: encadenar hace que un ciclo que corrio tarde empuje todos
los avisos siguientes.

LO QUE CUESTA: si el primer aviso sale tarde --la tarea mira cada 5 minutos,
o el ciclo estuvo caido-- el segundo puede llegar antes de 15 minutos. Una
vez, y despues se acompasa con la grilla.

QUE AFIRMAN ESTAS GUARDAS
--------------------------
El EFECTO sobre lo que recibe el telefono del tecnico: que insista, que pare
cuando llega el reporte, y que la empresa pueda apagarlo sin tocar codigo.
================================================================================
"""
from __future__ import annotations

import datetime as dt
import zoneinfo
from unittest import mock

import pytest
from django.utils import timezone

from campo import recordatorio_de_reporte as RR
from campo.avisos import DispositivoDeTecnico
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.seguimiento import ConfiguracionDeSeguimiento
from campo.services import avisos, push_fcm

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")


@pytest.fixture
def org(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


@pytest.fixture
def mediodia():
    return timezone.now().astimezone(BOGOTA).replace(
        hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def fcm():
    enviados = []

    def mandar(token, titulo, texto, enlace, *, aviso_id="", verbo="",
               contenido=None):
        #  SE GUARDA TODO LO QUE SALE, NO SOLO EL CUERPO (12/11/2026). La
        #  primera version descartaba `titulo`, `enlace` y `aviso_id`, asi
        #  que `test_SIN_DATOS_DEL_CLIENTE_EN_NINGUNO` afirmaba sobre el
        #  cuerpo y el `data` nada mas: alguien podia ponerle el nombre del
        #  cliente al asunto y la guarda seguia en verde. Lo encontro el
        #  revisor de PII. Una guarda que no mira un campo no lo protege.
        enviados.append({"titulo": titulo, "texto": texto, "enlace": enlace,
                         "aviso_id": str(aviso_id),
                         "verbo": verbo, "contenido": contenido or {}})
        return push_fcm.ENTREGADO

    with mock.patch.object(push_fcm, "esta_configurado", return_value=True), \
            mock.patch.object(push_fcm, "mandar_a_un_telefono",
                              side_effect=mandar):
        yield enviados


@pytest.fixture
def orden(org, user_profile):
    wt = WorkType.objects.create(org=org, codigo="ins", nombre="Soporte")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []})
    o = OrdenTrabajo.objects.create(
        org=org, numero=7777, tipo_trabajo_version=v,
        estado_operativo=OrdenTrabajo.EN_SITIO,
        cliente_nombre="Beatriz Pinzón", cliente_direccion="Calle 50 # 10-20")
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    DispositivoDeTecnico.objects.create(org=org, profile=user_profile,
                                        token="tok-ins", plataforma="android",
                                        activo=True)
    return o


def _reporte(orden, cuando, tipo="accion_marcar_llegada"):
    ev = EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo=tipo,
                                      datos={})
    EventoTrabajo.objects.filter(pk=ev.pk).update(created_at=cuando)


def _a_los(org, orden, mediodia, minutos):
    """Corre la tarea cuando el atraso es de `minutos`. Devuelve si aviso."""
    return RR.recordar_para(
        org, ahora=mediodia + dt.timedelta(minutes=minutos))["avisadas"]


# ---------------------------------------------------------------------------
#  1) LA CUENTA, SIN BASE DE DATOS
# ---------------------------------------------------------------------------

def test_LA_CUENTA_CON_LOS_NUMEROS_DEL_USUARIO():
    """30 y 15, tal como los pidio. Es una funcion pura: si esta tabla
    cambia, cambio la cadencia que el usuario pidio."""
    assert RR.cual_recordatorio(30, 30, 15) == 1
    assert RR.cual_recordatorio(44, 30, 15) == 1
    assert RR.cual_recordatorio(45, 30, 15) == 2
    assert RR.cual_recordatorio(59, 30, 15) == 2
    assert RR.cual_recordatorio(60, 30, 15) == 3
    assert RR.cual_recordatorio(180, 30, 15) == 11


def test_EN_CERO_VUELVE_A_SER_UNO_SOLO():
    """La salida para la empresa que no quiera insistencia. Sin esto,
    apagarla seria un cambio de codigo."""
    assert RR.cual_recordatorio(30, 30, 0) == 1
    assert RR.cual_recordatorio(300, 30, 0) == 1


def test_ANTES_DE_LA_VENTANA_NO_HAY_NUMERO_NEGATIVO():
    """La regla no da por vencida una orden antes de la ventana, pero si
    alguna vez llamara con menos, la cuenta no puede devolver 0 ni -1: esa
    clave chocaria con la del primer aviso."""
    assert RR.cual_recordatorio(5, 30, 15) == 1
    assert RR.cual_recordatorio(0, 30, 15) == 1


# ---------------------------------------------------------------------------
#  2) EL EFECTO: EL TELEFONO DEL TECNICO
# ---------------------------------------------------------------------------

def test_LA_GUARDA_DEL_PEDIDO_insiste_hasta_que_reporta(org, orden, fcm,
                                                        mediodia):
    """Lo que el usuario pidio, entero. Si esto se pone en rojo, el que no
    reporta vuelve a no saber nada de nadie despues del primer aviso."""
    _reporte(orden, mediodia)

    assert _a_los(org, orden, mediodia, 31) == 1, "el primero, el que ya habia"
    assert _a_los(org, orden, mediodia, 36) == 0, "dentro del intervalo"
    assert _a_los(org, orden, mediodia, 46) == 1, "el segundo"
    assert _a_los(org, orden, mediodia, 51) == 0
    assert _a_los(org, orden, mediodia, 61) == 1, "el tercero"

    assert len(fcm) == 3, [m["texto"] for m in fcm]
    #  Y CADA UNO DICE SU PROPIO ATRASO: tres mensajes identicos en la
    #  campanita no se distinguen de un error del sistema.
    assert "31 min" in fcm[0]["texto"], fcm[0]
    assert "46 min" in fcm[1]["texto"], fcm[1]
    assert "61 min" in fcm[2]["texto"], fcm[2]


def test_EL_REPORTE_LO_CALLA(org, orden, fcm, mediodia):
    """«hasta recibir el reporte». Si esta guarda se pone en rojo, el tecnico
    reporta y el telefono le sigue sonando -- que es peor que el problema que
    esto viene a arreglar."""
    _reporte(orden, mediodia)
    _a_los(org, orden, mediodia, 31)
    _a_los(org, orden, mediodia, 46)
    assert len(fcm) == 2

    #  Reporta al minuto 50. La referencia se mueve: empieza otra ventana.
    _reporte(orden, mediodia + dt.timedelta(minutes=50), tipo="avance_campo")

    assert _a_los(org, orden, mediodia, 61) == 0, "reporto hace 11 minutos"
    assert _a_los(org, orden, mediodia, 75) == 0, "todavia dentro de los 30"
    assert len(fcm) == 2

    #  Y si vuelve a pasar la ventana desde ESE reporte, arranca de nuevo.
    assert _a_los(org, orden, mediodia, 81) == 1
    assert "31 min" in fcm[2]["texto"], fcm[2]


def test_LA_EMPRESA_PUEDE_APAGAR_LA_INSISTENCIA(org, orden, fcm, mediodia):
    """En 0 vuelve el comportamiento de antes: un aviso por atraso. Lo que
    varia por empresa es configuracion (CLAUDE.md §3.3), y esto es una
    decision de procedimiento, no del motor."""
    ConfiguracionDeSeguimiento.objects.create(
        org=org, repetir_recordatorio_cada_minutos=0)
    _reporte(orden, mediodia)

    assert _a_los(org, orden, mediodia, 31) == 1
    assert _a_los(org, orden, mediodia, 46) == 0
    assert _a_los(org, orden, mediodia, 120) == 0
    assert len(fcm) == 1


def test_Y_PUEDE_ELEGIR_OTRA_CADENCIA(org, orden, fcm, mediodia):
    """Otra empresa con otro procedimiento pone otro numero y no hace falta
    tocar una linea. Si esta guarda se pone en rojo es porque los 15 minutos
    quedaron fijos en el codigo."""
    ConfiguracionDeSeguimiento.objects.create(
        org=org, repetir_recordatorio_cada_minutos=40)
    _reporte(orden, mediodia)

    assert _a_los(org, orden, mediodia, 31) == 1
    assert _a_los(org, orden, mediodia, 46) == 0, "con 40, todavia no toca"
    assert _a_los(org, orden, mediodia, 71) == 1
    assert len(fcm) == 2


def test_SUBIR_LA_CADENCIA_SIGUE_AVISANDO(org, orden, fcm, mediodia):
    """EL APAGON DEL 12/11/2026, encontrado por el auditor de frontera.

    La primera version puso en la clave solo el ORDINAL del recordatorio. El
    ordinal es `1 + (minutos - ventana) // cada`, asi que subir la cadencia
    lo hace BAJAR, de vuelta al rango que la cadencia vieja ya gasto: el
    reclamo por clave lo rechaza como repetido y no sale nada.

    Medido entonces: vencida desde las 7:00 con cadencia 15, 23 avisos al
    mediodia; el supervisor pone 60 esperando uno por hora y recibe CERO por
    el resto del dia. Al dia siguiente la referencia ya no es de hoy, asi que
    no vuelve nunca. Y la pantalla contestaba «Vuelve a avisarle cada 60
    minutos hasta que reporte» justo despues de apagarla.

    Las 17 guardas que habia estaban en verde con el sintoma vivo: ninguna
    cambiaba la configuracion con la orden YA contando. Esta lo hace.
    """
    fila = ConfiguracionDeSeguimiento.objects.create(
        org=org, repetir_recordatorio_cada_minutos=15)
    _reporte(orden, mediodia)

    #  Con 15: los avisos 1..5 (minutos 30, 45, 60, 75, 90).
    con_quince = sum(_a_los(org, orden, mediodia, m)
                     for m in (31, 46, 61, 76, 91))
    assert con_quince == 5, con_quince

    #  El supervisor sube a 60 esperando uno por hora.
    fila.repetir_recordatorio_cada_minutos = 60
    fila.save(update_fields=["repetir_recordatorio_cada_minutos"])

    #  LO QUE TIENE QUE PASAR: sigue avisando. Con 60 las ranuras caen en los
    #  minutos 30, 90, 150, 210... asi que de aca en adelante toca una por
    #  hora. Lo que NO puede pasar es cero.
    con_sesenta = sum(_a_los(org, orden, mediodia, m)
                      for m in (151, 211, 271))
    assert con_sesenta == 3, (
        f"la insistencia se apago al subir la cadencia: {con_sesenta} avisos")


def test_Y_VOLVER_A_LA_CADENCIA_ANTERIOR_TAMPOCO_LA_APAGA(org, orden, fcm,
                                                          mediodia):
    """El caso real: se baja a 5 para probar y se vuelve a 15. Si el espacio
    de claves fuera solo el ordinal, los numeros de 15 ya estarian todos
    gastados por la corrida de 5 --toda ranura de 15 es tambien ranura de
    5-- y el silencio seria total."""
    fila = ConfiguracionDeSeguimiento.objects.create(
        org=org, repetir_recordatorio_cada_minutos=5)
    _reporte(orden, mediodia)

    de_a_cinco = sum(_a_los(org, orden, mediodia, m)
                     for m in (31, 36, 41, 46, 51, 56, 61))
    assert de_a_cinco == 7, de_a_cinco

    fila.repetir_recordatorio_cada_minutos = 15
    fila.save(update_fields=["repetir_recordatorio_cada_minutos"])

    de_a_quince = sum(_a_los(org, orden, mediodia, m) for m in (76, 91, 106))
    assert de_a_quince == 3, (
        f"volver a la cadencia anterior la apago: {de_a_quince} avisos")


def test_APAGADO_DEL_TODO_SIGUE_APAGADO(org, orden, fcm, mediodia):
    """`recordar_al_tecnico` manda sobre todo lo demas: la insistencia no
    puede resucitar un aviso que la empresa apago."""
    ConfiguracionDeSeguimiento.objects.create(org=org,
                                              recordar_al_tecnico=False)
    _reporte(orden, mediodia)

    assert _a_los(org, orden, mediodia, 31) == 0
    assert _a_los(org, orden, mediodia, 61) == 0
    assert len(fcm) == 0


def test_SIN_DATOS_DEL_CLIENTE_EN_NINGUNO(org, orden, fcm, mediodia):
    """La regla del 30/10 vale para todos los avisos, no solo el primero:
    el numero de la orden y los minutos, nada mas."""
    import json

    _reporte(orden, mediodia)
    _a_los(org, orden, mediodia, 31)
    _a_los(org, orden, mediodia, 46)
    _a_los(org, orden, mediodia, 61)

    #  El `json.dumps` del fixture completo: titulo, texto, enlace, aviso_id,
    #  verbo y contenido. Si manana alguien le agrega un dato del cliente a
    #  CUALQUIERA de esos, esto se pone rojo.
    crudo = json.dumps(fcm, ensure_ascii=False)
    assert "Beatriz" not in crudo and "Calle 50" not in crudo, crudo
    #  Y el titulo se mira aparte, porque es el campo que la version vieja
    #  del fixture descartaba: que exista en el json no prueba que se haya
    #  armado, podria ser la cadena vacia.
    assert all(f"OT #{orden.numero}" in e["titulo"] for e in fcm),         [e["titulo"] for e in fcm]


def test_EL_PRIMERO_CONSERVA_SU_CLAVE_VIEJA(org, orden, fcm, mediodia):
    """EL DIA DEL DEPLOY. Hay ordenes vencidas que ya recibieron su aviso con
    la clave sin sufijo; si el primer recordatorio pasara a llevar `|1`, cada
    una volveria a sonar en el telefono de su tecnico el mismo minuto, por
    una migracion."""
    from campo.avisos import AvisoEnviado

    _reporte(orden, mediodia)
    #  La fila que ya existia antes del cambio, con la clave de entonces.
    s = avisos.CLAVE_SIN_REPORTE
    referencia = EventoTrabajo.objects.filter(
        org=org, orden=orden).first().created_at.isoformat()
    AvisoEnviado.objects.create(
        org=org, clave=f"{s}|{orden.id}|{referencia}"[:200])

    assert _a_los(org, orden, mediodia, 31) == 0, "no vuelve a mandar el 1"
    assert len(fcm) == 0
    #  Pero el segundo sale igual: la clave vieja no lo tapa.
    assert _a_los(org, orden, mediodia, 46) == 1
