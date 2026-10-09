# -*- coding: utf-8 -*-
"""
================================================================================
 CIERRE CONTROLADO: WISPHUB CERRADO -> DEXTER ABIERTO
================================================================================

LA REGLA
--------
Si el proveedor cerro el ticket y el CRM mantiene el caso abierto, el Supervisor
lo detecta y PROPONE cerrarlo. La deteccion es automatica; el cierre no ocurre
sin una decision humana y sin atravesar la frontera.

QUE CAMBIO EN M09-R
-------------------
1. Detector PROPIO ('_casos_cerrados_en_el_proveedor'), fuera de
   '_casos_abiertos_antiguos'. Antes heredaba su filtro de 7 dias: de 112 casos
   que cumplian la condicion en produccion se detectaban 109, y los 3 que
   faltaban eran los mas recientes -- los unicos donde actuar sirve de algo.
2. La propuesta pide CERRAR, no "revisar la sincronizacion". Nadie puede
   aceptar "revisar": no es una accion sobre nada.
3. Una ventana de frescura de la lectura (HORAS_LECTURA_FRESCA). Proponer un
   cierre es proponer un cambio de estado, y no se sostiene con una lectura de
   hace semanas: el ticket pudo reabrirse alla mientras tanto.

LO QUE ESTE ARCHIVO NO PRUEBA, PORQUE NO EXISTE
-----------------------------------------------
Que aceptar cierre el caso. No cierra, y las pruebas de §4 lo afirman sobre la
fila del caso releida. Faltan tres autorizaciones, todas medidas contra
produccion el 25/09/2026 y ninguna dable desde este codigo: AUTONOMIA_2_ACTIVA
apagada, B-7 abierto (el GUC del secreto de firma sigue en la base) y
'asistente.autorizacion_herramienta' vacia. Ver el docstring de
'ejecutar_propuesta'.
================================================================================
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from cases.models import Case
from conftest import rls_org
from operaciones import supervisor
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

TIPO = PropuestaSupervisor.CASO_DESINCRONIZADO
_ticket = iter(range(80000, 89999))


# =============================================================================
#  andamio
# =============================================================================

def _caso(org, *, externo="Cerrado", status="New", dias=12,
          cerro_hace_dias=3, leido_hace_horas=1, error_lectura="",
          sin_status_at=False, sin_fetched_at=False):
    """
    Un caso con la forma exacta que deja la importacion.

    Los valores por defecto son el caso que SI debe detectarse, para que cada
    prueba cambie una sola cosa y se vea cual.
    """
    ahora = timezone.now()
    ext_id = str(next(_ticket)) if externo else ""
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status=status,
        priority="Normal", external_status=externo,
        external_ticket_id=ext_id, provider="wisphub" if externo else "",
        external_fetch_error=error_lectura)

    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - timedelta(days=dias),
        external_status_at=None if sin_status_at
        else (ahora - timedelta(days=cerro_hace_dias) if externo else None),
        external_fetched_at=None if sin_fetched_at
        else (ahora - timedelta(hours=leido_hace_horas) if externo else None))
    caso.refresh_from_db()
    return caso


def _senales(org, caso):
    return [s for s in supervisor.detectar(org)
            if s.origen_id == str(caso.id) and s.tipo == TIPO]


def _detecta(org, caso) -> bool:
    return bool(_senales(org, caso))


def _propuesta(org, caso):
    senal = _senales(org, caso)[0]
    return supervisor.registrar_propuesta(org, senal, supervisor.analizar(senal))


def _estado_del_caso(caso):
    caso.refresh_from_db()
    return (caso.status, caso.resolved_at, caso.closed_on)


# =============================================================================
#  §1  CUANDO SI DETECTA
# =============================================================================

def test_1_wisphub_cerrado_y_dexter_new_detecta(org_a):
    """La forma de 100 casos de produccion."""
    with rls_org(org_a):
        assert _detecta(org_a, _caso(org_a, status="New"))


def test_2_wisphub_cerrado_y_dexter_assigned_detecta(org_a):
    """
    La forma de 12 casos de produccion.

    'Assigned' cuenta como abierto: lo unico que el CRM trata como resuelto es
    'Closed' (RESOLVED_STATUSES en cases/signals.py). Que alguien lo tenga
    asignado no lo resuelve.
    """
    with rls_org(org_a):
        assert _detecta(org_a, _caso(org_a, status="Assigned"))


def test_3_un_caso_recien_cerrado_afuera_tambien_se_detecta(org_a):
    """
    EL MOTIVO DE QUE ESTE DETECTOR EXISTA APARTE.

    Antes de M09-R este caso era invisible: el detector heredaba el corte de 7
    dias de '_casos_abiertos_antiguos'. Medido: 3 de 112 quedaban afuera, y eran
    los unicos donde cerrar a tiempo cambia algo.

    Se afirma sobre el EFECTO -- que se detecta -- y no sobre que el codigo no
    consulte 'created_at'.
    """
    with rls_org(org_a):
        ayer = _caso(org_a, dias=1, cerro_hace_dias=0)
        assert _detecta(org_a, ayer)
        #  Y NO sale ademas como caso antiguo: seria decir dos cosas del mismo
        #  caso, una de ellas falsa.
        tipos = [s.tipo for s in supervisor.detectar(org_a)
                 if s.origen_id == str(ayer.id)]
        assert tipos == [TIPO], tipos


@pytest.mark.parametrize("valor", ["Cerrado", "CERRADO", "cerrado", "  Cerrado  "])
def test_la_capitalizacion_del_proveedor_no_cambia_el_veredicto(org_a, valor):
    """
    Si dependiera de la capitalizacion exacta, un cambio de la API silenciaria
    la deteccion entera de golpe y sin ningun error.
    """
    with rls_org(org_a):
        assert _detecta(org_a, _caso(org_a, externo=valor))


# =============================================================================
#  §2  CUANDO NO DETECTA  --  las siete exclusiones
# =============================================================================

def test_4_dexter_ya_cerrado_no_detecta(org_a):
    """Si ya esta cerrado no hay nada que sincronizar."""
    with rls_org(org_a):
        caso = _caso(org_a, status="Closed")
        Case.objects.filter(pk=caso.pk).update(resolved_at=timezone.now())
        assert not _detecta(org_a, caso)


def test_5_wisphub_abierto_no_detecta(org_a):
    """Los dos sistemas coinciden."""
    with rls_org(org_a):
        for abierto in ("Nuevo", "En Progreso"):
            assert not _detecta(org_a, _caso(org_a, externo=abierto)), abierto


def test_6_estado_externo_vacio_no_detecta(org_a):
    """
    73 casos de produccion lo tienen vacio.

    La ausencia de dato no se convierte en dato: no se supone que el proveedor
    lo cerro porque el CRM no sepa nada.
    """
    with rls_org(org_a):
        assert not _detecta(org_a, _caso(org_a, externo=""))


def test_6b_un_estado_externo_desconocido_no_se_interpreta(org_a):
    """Un valor fuera de las dos listas no se lee como cerrado."""
    with rls_org(org_a):
        assert not _detecta(org_a, _caso(org_a, externo="Reabierto Por Cliente"))


def test_7_con_error_de_lectura_no_detecta(org_a):
    """
    Una lectura que dejo error anotado no sostiene nada, AUNQUE haya traido un
    estado: ese estado puede ser el de la lectura anterior.
    """
    with rls_org(org_a):
        assert not _detecta(org_a, _caso(
            org_a, error_lectura="HTTPError: 502 Bad Gateway"))


def test_8_sin_fecha_de_lectura_no_detecta(org_a):
    """Sin saber CUANDO se leyo, no se puede juzgar si el dato sirve."""
    with rls_org(org_a):
        assert not _detecta(org_a, _caso(org_a, sin_fetched_at=True))


def test_9_sin_fecha_de_cierre_del_proveedor_no_detecta(org_a):
    """
    Sin 'external_status_at' no se puede decir desde cuando estan desalineados,
    y esa cifra es parte de la evidencia con la que alguien decide.
    """
    with rls_org(org_a):
        assert not _detecta(org_a, _caso(org_a, sin_status_at=True))


def test_10_una_lectura_demasiado_antigua_no_detecta(org_a):
    """
    LA EXCLUSION QUE HOY APLICA A TODA LA PRODUCCION.

    Medido el 25/09/2026: la ultima 'external_fetched_at' era de 77,5 horas
    antes, porque las escrituras del reloj estan bloqueadas por Autonomia 2.
    Con este corte esos casos NO generan propuesta de cierre -- primero se
    arregla la sincronizacion, despues se decide sobre sus datos.

    Se afirma sobre el EFECTO y no sobre la constante: si alguien amplia la
    ventana, esta prueba falla y hay que decidir.
    """
    with rls_org(org_a):
        horas = supervisor.HORAS_LECTURA_FRESCA
        fresca = _caso(org_a, leido_hace_horas=horas - 1)
        vieja = _caso(org_a, leido_hace_horas=horas + 1)
        assert _detecta(org_a, fresca), f"ventana={horas}h"
        assert not _detecta(org_a, vieja), f"ventana={horas}h"


def test_11_un_caso_de_otra_organizacion_no_detecta(org_a, org_b):
    with rls_org(org_b):
        ajeno = _caso(org_b)
    with rls_org(org_a):
        assert not _detecta(org_a, ajeno)


# =============================================================================
#  §3  LA PROPUESTA
# =============================================================================

def test_la_propuesta_pide_cerrar_y_explica_por_que(org_a):
    """
    Los textos acordados. Se afirma el SENTIDO, no la frase exacta: lo que no
    puede pasar es que vuelva a pedir "revisar", que no es una accion sobre
    nada y nadie puede aceptar.
    """
    with rls_org(org_a):
        p = _propuesta(org_a, _caso(org_a))

    assert "cerrar el caso" in p.accion_propuesta.lower()
    assert "dexter" in p.accion_propuesta.lower() or "crm" in p.accion_propuesta.lower()
    assert "revisar la sincronizaci" not in p.accion_propuesta.lower()
    assert "wisphub reporta el ticket como cerrado" in p.motivo.lower()
    #  Y sigue sin afirmar lo que nadie puede saber.
    assert "el cliente" in p.motivo.lower()
    assert p.nivel_autonomia_requerido == PropuestaSupervisor.NIVEL_RECOMENDAR


def test_la_evidencia_trae_los_siete_datos_para_decidir(org_a):
    """
    Quien acepta esto cambia el estado de un caso: tiene que poder ver contra
    que. Se comprueba que cada dato ESTE, no como esta redactado.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)

    textos = " | ".join(e["dato"] for e in p.evidencia).lower()
    assert caso.external_ticket_id in textos          # ticket WispHub
    assert str(caso.id)[:8].lower() in textos         # caso Dexter
    assert "estado en el proveedor: cerrado" in textos
    assert f"estado en el crm: {caso.status}".lower() in textos
    assert "lo cerro el" in textos                    # external_status_at
    assert "leido el" in textos                       # external_fetched_at
    assert "condicion:" in textos                     # la regla que disparo
    assert "desalineados" in textos


def test_12_la_propuesta_no_se_duplica(org_a):
    """
    Dos ciclos sobre el mismo caso dejan UNA propuesta.

    La huella se conserva igual que la del camino anterior a proposito: si
    hubiera cambiado, el primer ciclo habria generado 109 duplicados de las que
    ya viven en produccion.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        senal = _senales(org_a, caso)[0]
        assert senal.huella == "cerrado_en_proveedor_abierto_en_crm"

        primera = supervisor.registrar_propuesta(
            org_a, senal, supervisor.analizar(senal))
        assert supervisor._ya_propuesta(org_a, senal) is True

        resumen = supervisor.correr_ciclo(org_a)
        vivas = PropuestaSupervisor.objects.filter(
            org=org_a, origen_id=str(caso.id), tipo_senal=TIPO).count()

    assert vivas == 1, "el ciclo volvio a proponer lo mismo"
    assert resumen.get("repetidas", 0) >= 1
    assert primera.id is not None


# =============================================================================
#  §4  EL CIERRE NO OCURRE  --  lo que la frontera todavia no autoriza
# =============================================================================

def test_13_la_deteccion_no_cierra_ningun_caso(org_a):
    """
    Detectar es leer. Se compara la fila ENTERA del caso antes y despues de un
    ciclo completo: ni un campo se mueve.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        antes = Case.objects.filter(id=caso.id).values().first()
        supervisor.correr_ciclo(org_a)
        despues = Case.objects.filter(id=caso.id).values().first()

    assert antes == despues


def test_14_aceptar_la_propuesta_no_cierra_el_caso(org_a, user_profile):
    """
    ACEPTAR REGISTRA UN ACUERDO. El caso sigue exactamente como estaba.

    No es la conducta deseada a futuro: es la conducta REAL hoy, y esta prueba
    es la que va a fallar -- a proposito -- el dia que la ejecucion se autorice.
    Cuando eso pase, hay que reescribirla afirmando el cierre, no borrarla.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        antes = _estado_del_caso(caso)

        supervisor.revisar(p, actor=user_profile,
                           decision=PropuestaSupervisor.ACEPTADA,
                           comentario="de acuerdo, cerrar")
        p.refresh_from_db()

    assert p.estado == PropuestaSupervisor.ACEPTADA
    assert _estado_del_caso(caso) == antes, (
        "el caso se movio al aceptar: si la ejecucion ya esta autorizada, esta "
        "prueba hay que reescribirla afirmando el cierre")


def test_15_rechazar_no_modifica_dexter(org_a, user_profile):
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        antes = _estado_del_caso(caso)

        supervisor.revisar(p, actor=user_profile,
                           decision=PropuestaSupervisor.RECHAZADA,
                           comentario="el cliente volvio a reportar")
        p.refresh_from_db()

    assert p.estado == PropuestaSupervisor.RECHAZADA
    assert _estado_del_caso(caso) == antes


def test_16_una_propuesta_pendiente_no_modifica_dexter(org_a):
    """Emitida y sin revisar: no pasa nada, que es lo correcto."""
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        antes = _estado_del_caso(caso)

    assert p.estado == PropuestaSupervisor.PROPUESTA
    assert _estado_del_caso(caso) == antes


def test_17_el_unico_camino_declarado_a_la_ejecucion_levanta(org_a):
    """
    Es la diferencia entre "no encontramos ninguna ejecucion" -- una afirmacion
    sobre lo que alguien no vio -- y "el camino declarado no ejecuta".
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)

        with pytest.raises(supervisor.EjecucionNoPermitida):
            supervisor.ejecutar_propuesta(p)

    assert _estado_del_caso(caso)[0] == "New"


def test_18_dos_revisiones_a_la_vez_dejan_una_sola_decision(org_a, user_profile):
    """
    CONCURRENCIA. Dos personas aceptan la misma propuesta.

    La segunda no puede volver a decidir: 'revisar' bloquea la fila y mira el
    estado sobre la fila releida, no sobre la copia en memoria. Y lo que se
    afirma aqui ademas es el efecto que importa para este bloque: el caso no se
    toca ninguna de las dos veces, asi que no hay dos cierres.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        antes = _estado_del_caso(caso)

        supervisor.revisar(p, actor=user_profile,
                           decision=PropuestaSupervisor.ACEPTADA,
                           comentario="primera")

        #  Una segunda copia del objeto, como la que traeria otra peticion HTTP.
        otra = PropuestaSupervisor.objects.get(pk=p.pk)
        with pytest.raises(Exception):
            supervisor.revisar(otra, actor=user_profile,
                               decision=PropuestaSupervisor.RECHAZADA,
                               comentario="segunda")

        p.refresh_from_db()
        decisiones = PropuestaSupervisor.objects.filter(
            pk=p.pk, estado=PropuestaSupervisor.ACEPTADA).count()

    assert decisiones == 1
    assert p.estado == PropuestaSupervisor.ACEPTADA
    assert _estado_del_caso(caso) == antes


def test_19_la_revision_queda_auditada_con_quien_decidio(org_a, user_profile):
    """
    Trazabilidad: quien, cuando, y sobre que propuesta. En la bitacora que ya
    existe, no en una tabla nueva.
    """
    from common.models import Activity

    with rls_org(org_a):
        caso = _caso(org_a)
        p = _propuesta(org_a, caso)
        supervisor.revisar(p, actor=user_profile,
                           decision=PropuestaSupervisor.ACEPTADA,
                           comentario="de acuerdo")

        filas = Activity.objects.filter(
            entity_type="PropuestaSupervisor", entity_id=p.id)
        assert filas.exists(), "la decision no quedo auditada"
        fila = filas.first()
        assert fila.user_id == user_profile.id
        assert fila.org_id == org_a.id
        assert fila.created_at is not None


# =============================================================================
#  §5  DOS HUECOS QUE SIGUEN ABIERTOS, Y AHORA IMPORTAN MAS
# =============================================================================
#  Vienen del diagnostico de M09-Q, que este archivo reemplaza. Se conservan
#  porque siguen siendo ciertos, y porque dejaron de ser teoricos: mientras la
#  propuesta decia "revisar la sincronizacion" no comprobar estas dos cosas era
#  inofensivo. Ahora propone CERRAR un caso, y cualquiera de las dos deberia
#  impedirlo.
#
#  Ninguno se corrige aqui: hacerlo es una decision de producto sobre que
#  bloquea un cierre, y este bloque no la toma. Lo que si se hace es dejarlos
#  afirmados, para que el dia que se cierren estas pruebas fallen y avisen.

def test_20_una_actividad_pendiente_no_frena_la_propuesta_todavia(org_a, user_profile):
    """
    HUECO DOCUMENTADO, no conducta deseada.

    Una actividad operativa abierta sobre el caso no impide la señal ni aparece
    en su evidencia. Hoy no daña a nadie: medido el 25/09/2026, hay 0
    actividades y 0 ordenes de trabajo con origen_tipo='case' en produccion.
    Pero es una de las condiciones que deberian bloquear un cierre.
    """
    from operaciones.models import ActividadOperativa

    with rls_org(org_a):
        caso = _caso(org_a)
        ActividadOperativa.objects.create(
            org=org_a, titulo="Revisar con el cliente",
            responsable=user_profile, origen_tipo="case",
            origen_id=str(caso.id))

        senal = _senales(org_a, caso)[0]

    textos = " | ".join(e["dato"] for e in senal.evidencia).lower()
    assert "actividad" not in textos, (
        "la evidencia ya menciona la actividad: el hueco se cerro y esta "
        "prueba hay que reescribirla como condicion que bloquea")


def test_21_una_respuesta_posterior_al_cierre_no_frena_la_propuesta_todavia(org_a):
    """
    HUECO DOCUMENTADO. El proveedor se contradice consigo mismo: dice que cerro
    el ticket y registra una respuesta despues.

    Medido: 0 casos asi en produccion hoy. Es el dato mas claro de "informacion
    contradictoria reciente", y no se comprueba.
    """
    from cases.models import RespuestaExterna

    with rls_org(org_a):
        caso = _caso(org_a, cerro_hace_dias=3)
        RespuestaExterna.objects.create(
            org=org_a, case=caso, provider="wisphub", huella=f"h{caso.pk}",
            autor_nombre="tecnico", cuerpo="el cliente volvio a llamar",
            creada_en_proveedor=caso.external_status_at + timedelta(hours=6))

        senal = _senales(org_a, caso)[0]

    textos = " | ".join(e["dato"] for e in senal.evidencia).lower()
    for palabra in ("posterior", "contradic", "despues del cierre"):
        assert palabra not in textos, (
            f"'{palabra}' aparece: la contradiccion ya se detecta y esta prueba "
            f"hay que reescribirla como condicion que bloquea")


def test_22_lo_que_el_detector_NO_comprueba_esta_dicho(org_a):
    """
    La lista de condiciones que un cierre deberia exigir y que hoy no se miran.

    No es documentacion suelta: si alguien agrega una de estas comprobaciones,
    esta prueba falla y obliga a actualizar la lista -- que es como se evita que
    el informe y el codigo se separen.
    """
    fuente = supervisor._casos_cerrados_en_el_proveedor.__doc__ or ""
    #  Lo que SI exige, dicho en su propio docstring.
    for exigido in ("external_status_at", "external_fetched_at",
                    "external_fetch_error"):
        assert exigido in fuente, exigido

    #  Y lo que no: ninguna de estas tres palabras aparece, porque ninguna se
    #  comprueba. El dia que se comprueben, esto falla.
    import inspect
    codigo = inspect.getsource(supervisor._casos_cerrados_en_el_proveedor)
    for no_comprobado in ("ActividadOperativa", "OrdenTrabajo",
                          "RespuestaExterna", "NovedadOperativa"):
        assert no_comprobado not in codigo, (
            f"{no_comprobado} ya se consulta: el detector gano una condicion y "
            f"esta prueba hay que actualizarla")
