# -*- coding: utf-8 -*-
"""
================================================================================
 DIAGNOSTICO: WISPHUB CERRADO vs DEXTER ABIERTO
================================================================================

QUE ES ESTE ARCHIVO, Y QUE NO ES
--------------------------------
Es el diagnostico de la deteccion que YA existe, escrito como pruebas para que
lo que se midio quede afirmado en vez de contado en un informe. NO implementa
ningun cierre: a la fecha de este archivo el cierre desde el Supervisor no
existe, y 'ejecutar_propuesta' levanta siempre.

LO QUE DOCUMENTA, Y ES LO QUE IMPORTA
-------------------------------------
La deteccion de desincronizacion NO es un detector propio: vive DENTRO de
'_casos_abiertos_antiguos', detras de su filtro de 7 dias. La consecuencia,
medida en produccion el 25/09/2026: de 112 casos cerrados en el proveedor y sin
resolver en el CRM, **109 se detectan y 3 no** -- los 3 que cerraron alla hace
menos de una semana. Y las 109 propuestas vivas de ese tipo coinciden exacto
con ese 109, lo que confirma que el umbral es el unico motivo.

Eso no es un bug de logica: la desincronizacion se descubrio mientras se
miraban casos antiguos, y quedo donde se encontro. Pero significa que un caso
cerrado afuera ayer no se ve hasta dentro de una semana, y esa espera no la
pide nada del dominio.

LOS OCHO ESCENARIOS
-------------------
Los que pidio el bloque de diagnostico, cada uno con lo que el sistema hace HOY
-- no con lo que deberia hacer. Donde hay un hueco, la prueba lo afirma como
hueco y lo dice: cambiarlo es una decision de producto, no un arreglo.
================================================================================
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from cases.models import Case, RespuestaExterna
from conftest import rls_org
from operaciones import supervisor
from operaciones.models import ActividadOperativa, PropuestaSupervisor

pytestmark = pytest.mark.django_db

TIPO = PropuestaSupervisor.CASO_DESINCRONIZADO
ANTIGUO = PropuestaSupervisor.CASO_ANTIGUO

_ticket = iter(range(90000, 99999))


# =============================================================================
#  andamio
# =============================================================================

def _caso(org, *, dias=9, externo="", status="New", respuestas=0,
          respuesta_posterior=False, cerrado_alla_hace=None, sin_lectura=False):
    """
    Un caso con la forma que deja la importacion real.

    'provider' y 'external_ticket_id' van juntos o no van -- lo exige la
    restriccion 'case_external_ref_complete' de la tabla.
    """
    ahora = timezone.now()
    ext_id = str(next(_ticket)) if externo else ""
    caso = Case.objects.create(
        org=org, name="Sin servicio de internet", status=status,
        priority="Normal", external_status=externo,
        external_ticket_id=ext_id, provider="wisphub" if externo else "")

    cerro_alla = None
    if externo and cerrado_alla_hace is not None:
        cerro_alla = ahora - timedelta(days=cerrado_alla_hace)

    Case.objects.filter(pk=caso.pk).update(
        created_at=ahora - timedelta(days=dias),
        external_status_at=cerro_alla,
        external_fetched_at=None if (sin_lectura or not externo) else ahora)

    for i in range(respuestas):
        cuando = ahora - timedelta(days=1)
        if respuesta_posterior and cerro_alla is not None:
            #  Una respuesta del proveedor POSTERIOR al cierre que el mismo
            #  proveedor reporto: los dos datos vienen de alla y se contradicen.
            cuando = cerro_alla + timedelta(hours=6)
        RespuestaExterna.objects.create(
            org=org, case=caso, provider="wisphub", huella=f"h{caso.pk}-{i}",
            autor_nombre="tecnico", cuerpo="se atendio",
            creada_en_proveedor=cuando)

    caso.refresh_from_db()
    return caso


def _senales_de(org, caso):
    return [s for s in supervisor.detectar(org) if s.origen_id == str(caso.id)]


def _tipos_de(org, caso):
    return sorted(s.tipo for s in _senales_de(org, caso))


def _propuesta_de(org, caso):
    """La propuesta que el ciclo emitiria por este caso."""
    senal = _senales_de(org, caso)[0]
    return supervisor.registrar_propuesta(org, senal, supervisor.analizar(senal))


# =============================================================================
#  §1  LOS OCHO ESCENARIOS
# =============================================================================

def test_1_wisphub_cerrado_y_dexter_abierto_se_detecta(org_a):
    """
    El caso que el bloque quiere resolver. Es la forma de 109 de produccion.

    Se detecta como inconsistencia de SINCRONIZACION y no como caso
    abandonado: son dos afirmaciones distintas y solo una es cierta.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado", respuestas=2,
                     cerrado_alla_hace=3)
        assert _tipos_de(org_a, caso) == [TIPO]
        assert ANTIGUO not in _tipos_de(org_a, caso)


def test_2_wisphub_abierto_y_dexter_abierto_no_es_desincronizacion(org_a):
    """Los dos sistemas coinciden: no hay nada que sincronizar."""
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Nuevo", respuestas=2)
        assert TIPO not in _tipos_de(org_a, caso)


def test_3_wisphub_cerrado_y_dexter_cerrado_no_genera_nada(org_a):
    """
    Coherentes. Es la forma de 3 casos de produccion.

    El detector filtra por 'resolved_at is null', asi que un caso resuelto no
    entra -- y se afirma sobre el EFECTO (no sale ninguna señal) y no sobre la
    columna que se consulta.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado", status="Closed")
        Case.objects.filter(pk=caso.pk).update(resolved_at=timezone.now())
        caso.refresh_from_db()
        assert _senales_de(org_a, caso) == []


def test_4_un_estado_externo_desconocido_no_se_interpreta(org_a):
    """
    Un valor que no esta en ninguna de las dos listas NO se asume cerrado.

    Se trata como caso antiguo -- que es lo que se sabe: lleva 12 dias sin
    resolver-- y no como desincronizado, que seria afirmar algo del proveedor
    que el proveedor no dijo.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Reabierto Por Cliente")
        tipos = _tipos_de(org_a, caso)
        assert TIPO not in tipos
        assert tipos == [ANTIGUO]


def test_4b_la_capitalizacion_del_proveedor_no_cambia_el_veredicto(org_a):
    """
    Producción devuelve 'Cerrado'; el detector normaliza antes de comparar.

    Si dependiera de la capitalizacion exacta, un cambio de la API silenciaria
    las 109 detecciones de golpe y sin error.
    """
    with rls_org(org_a):
        for valor in ("Cerrado", "CERRADO", "cerrado", "  Cerrado  "):
            caso = _caso(org_a, dias=12, externo=valor)
            assert _tipos_de(org_a, caso) == [TIPO], valor


def test_5_sin_estado_externo_no_se_concluye_nada_del_proveedor(org_a):
    """
    73 casos de produccion tienen 'external_status' vacio.

    La ausencia de dato no se convierte en dato: no es desincronizacion. Sale
    como caso antiguo marcado DATOS_FALTANTES, que es lo unico afirmable.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="")
        senales = _senales_de(org_a, caso)
        assert [s.tipo for s in senales] == [ANTIGUO]
        assert senales[0].datos.get("clasificacion") == supervisor.DATOS_FALTANTES


def test_5b_sin_fecha_de_lectura_lo_dice_en_la_evidencia(org_a):
    """
    Cuando no se sabe CUANDO se leyo el estado externo, la evidencia lo dice.

    Importa para el cierre futuro: un dato externo sin fecha de lectura no
    puede sostener una decision de cerrar. En produccion hoy los 115 casos
    cerrados-afuera tienen las dos marcas, pero la de abajo es la unica que
    garantiza que se vea cuando falten.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado", sin_lectura=True)
        senal = _senales_de(org_a, caso)[0]
        textos = " | ".join(e["dato"] for e in senal.evidencia)
        assert "no dice cuando se leyo" in textos


def test_6_un_caso_de_otra_organizacion_no_aparece(org_a, org_b):
    """El detector recibe la org y no mira mas alla. Dos capas, como siempre."""
    with rls_org(org_b):
        ajeno = _caso(org_b, dias=12, externo="Cerrado")
    with rls_org(org_a):
        assert _senales_de(org_a, ajeno) == []


def test_7_una_actividad_pendiente_no_cambia_la_deteccion_hoy(org_a, user_profile):
    """
    HUECO DOCUMENTADO, no comportamiento deseado.

    Una actividad operativa abierta sobre el caso NO impide la señal, y no
    aparece en su evidencia. Hoy eso no daña a nadie: medido en produccion, hay
    0 actividades y 0 ordenes con origen_tipo='case'. Pero si el cierre llega a
    existir, esta es la comprobacion que va a hacer falta -- y esta prueba es
    la que se va a tener que cambiar cuando se agregue, a proposito.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado")
        ActividadOperativa.objects.create(
            org=org_a, titulo="Revisar la sincronizacion",
            responsable=user_profile, origen_tipo="case",
            origen_id=str(caso.id))

        senal = _senales_de(org_a, caso)[0]
        assert senal.tipo == TIPO
        textos = " | ".join(e["dato"] for e in senal.evidencia)
        assert "actividad" not in textos.lower(), (
            "si la evidencia YA menciona la actividad, el hueco se cerro y "
            "esta prueba hay que reescribirla")


def test_8_una_respuesta_posterior_al_cierre_no_frena_la_senal_hoy(org_a):
    """
    HUECO DOCUMENTADO. El proveedor se contradice consigo mismo.

    Dice que cerro el ticket el dia X y registra una respuesta el dia X+6h. El
    detector emite la señal igual y la contradiccion no entra en la evidencia.
    Medido: en produccion hoy hay 0 casos asi, asi que el hueco es teorico --
    pero es exactamente el dato que impediria cerrar, y por eso queda afirmado.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado", respuestas=1,
                     cerrado_alla_hace=3, respuesta_posterior=True)
        senal = _senales_de(org_a, caso)[0]
        assert senal.tipo == TIPO
        textos = " | ".join(e["dato"] for e in senal.evidencia)
        for palabra in ("posterior", "contradic", "despues del cierre"):
            assert palabra not in textos.lower(), (
                f"'{palabra}' aparece: la contradiccion ya se detecta y esta "
                f"prueba hay que reescribirla")


# =============================================================================
#  §2  EL UMBRAL DE 7 DIAS  --  el hallazgo principal del diagnostico
# =============================================================================

def test_el_umbral_de_7_dias_esconde_las_desincronizaciones_recientes(org_a):
    """
    LA PRUEBA QUE VALE POR TODO EL DIAGNOSTICO.

    La desincronizacion NO tiene detector propio: cuelga de
    '_casos_abiertos_antiguos', detras de su filtro de DIAS_CASO_ANTIGUO. Un
    caso cerrado en el proveedor hace dos dias es tan desincronizado como uno
    de hace dos meses -- el CRM esta igual de equivocado en los dos-- y el de
    dos dias no se ve.

    Medido en produccion el 25/09/2026: 112 casos cumplen la condicion cruda,
    109 se detectan, 3 no. Los 3 son exactamente los de menos de 7 dias.

    Se afirma sobre el EFECTO, no sobre la constante: si alguien baja el umbral
    a 1 dia, esta prueba falla y hay que decidir -- que es lo correcto, porque
    el numero es una decision, no un detalle.
    """
    with rls_org(org_a):
        viejo = _caso(org_a, dias=supervisor.DIAS_CASO_ANTIGUO + 2,
                      externo="Cerrado")
        reciente = _caso(org_a, dias=2, externo="Cerrado")

        assert _tipos_de(org_a, viejo) == [TIPO]
        assert _senales_de(org_a, reciente) == [], (
            "el caso reciente ya se detecta: el umbral dejo de esconderlo y "
            "este diagnostico quedo viejo")


def test_en_el_borde_del_umbral_entra(org_a):
    """Justo por encima entra; justo por debajo no. El corte es el que dice."""
    with rls_org(org_a):
        corte = supervisor.DIAS_CASO_ANTIGUO
        dentro = _caso(org_a, dias=corte + 1, externo="Cerrado")
        fuera = _caso(org_a, dias=corte - 1, externo="Cerrado")
        assert _tipos_de(org_a, dentro) == [TIPO], f"corte={corte}"
        assert _senales_de(org_a, fuera) == [], f"corte={corte}"


# =============================================================================
#  §3  ACEPTAR NO CIERRA NADA  --  lo que el bloque pidio no asumir
# =============================================================================

def test_aceptar_una_propuesta_no_cierra_el_caso(org_a, user_profile):
    """
    'ACEPTADA' registra un acuerdo. El caso sigue exactamente como estaba.

    Se afirma sobre la fila del CASO -- estado, resolved_at y closed_on
    releidos-- y no sobre la ausencia de una llamada: "no encontramos ninguna
    ejecucion" es una afirmacion sobre lo que alguien no vio.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado")
        propuesta = _propuesta_de(org_a, caso)
        antes = (caso.status, caso.resolved_at, caso.closed_on)

        #  'revisar' exige un revisor: "Una revisión sin revisor no es una
        #  revisión". Se le da uno real, porque lo que se prueba es que ACEPTAR
        #  no mueve el caso -- no que la funcion valide su actor.
        supervisor.revisar(propuesta, actor=user_profile,
                           decision=PropuestaSupervisor.ACEPTADA,
                           comentario="de acuerdo")

        propuesta.refresh_from_db()
        caso.refresh_from_db()

    assert propuesta.estado == PropuestaSupervisor.ACEPTADA
    assert (caso.status, caso.resolved_at, caso.closed_on) == antes


def test_el_unico_camino_declarado_a_la_ejecucion_levanta(org_a):
    """
    No es decorativo: es la diferencia entre "no vimos ejecucion" y "el camino
    declarado no ejecuta".
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado")
        propuesta = _propuesta_de(org_a, caso)

        with pytest.raises(supervisor.EjecucionNoPermitida):
            supervisor.ejecutar_propuesta(propuesta)

        caso.refresh_from_db()
        assert caso.status == "New"
        assert caso.resolved_at is None


def test_la_propuesta_no_promete_un_cierre(org_a):
    """
    El nivel es OBSERVAR y la accion habla de REVISAR la sincronizacion.

    Si alguien cambiara el texto a "cerrar el caso", la pantalla prometeria un
    efecto que el sistema no produce -- y ese es el malentendido mas caro de
    todo el tablero.
    """
    with rls_org(org_a):
        caso = _caso(org_a, dias=12, externo="Cerrado")
        propuesta = _propuesta_de(org_a, caso)

    assert propuesta.nivel_autonomia_requerido == PropuestaSupervisor.NIVEL_OBSERVAR
    assert "revisar" in propuesta.accion_propuesta.lower()
    assert "sincroniz" in propuesta.accion_propuesta.lower()
