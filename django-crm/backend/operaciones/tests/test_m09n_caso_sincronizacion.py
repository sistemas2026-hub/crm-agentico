# -*- coding: utf-8 -*-
"""
================================================================================
 M09-N  --  un caso abierto hace mucho no es un caso desatendido
================================================================================

QUE ARREGLA, Y COMO SE MIDIO
----------------------------
El detector 'caso_abierto_antiguo' convertia en señal cualquier caso abierto en
el CRM con mas de 7 dias. El diagnostico del 22/09/2026 contra produccion (100%
lectura, sin ejecutar el ciclo) midio que eso, hoy, seria mayormente ruido:

    96  casos abiertos con mas de 7 dias
    78  de ellos CERRADOS en WispHub  ->  el trabajo ya termino afuera
     5  en curso afuera y CON respuestas registradas
    13  sin ninguna respuesta registrada

O sea: 78 de 96 propuestas habrian mandado a revisar clientes ya atendidos. La
causa no es operativa -- es que el cierre no se refleja en el CRM (la
reconciliacion T20 esta apagada en produccion, y 'sincronizaciones_externas'
tiene 0 filas). Este paso NO la enciende: solo corrige el razonamiento.

LO QUE ESTAS PRUEBAS FIJAN
--------------------------
No que el detector "exista": que ante cada estado externo produzca la señal que
corresponde y NINGUNA otra. Cada prueba mide el tipo emitido y el texto que
llegaria a la pantalla, porque el daño de este defecto no estaba en el conteo
sino en la palabra: "desatendido" sobre un caso atendido.

Y lo que ninguna prueba afirma: que el problema del cliente este resuelto. Eso
no lo dice ninguna columna.
================================================================================
"""
import itertools
from datetime import timedelta

import pytest
from django.utils import timezone

from cases.models import Case, RespuestaExterna
from operaciones import supervisor
from operaciones.models import ActividadOperativa, PropuestaSupervisor

pytestmark = pytest.mark.django_db


#  Las palabras con las que una propuesta ATRIBUIRIA culpa. Se buscan en la
#  accion y en el impacto -- donde una atribucion viviria -- y NO en el motivo:
#  ahi aparecen a proposito, negadas ("no se afirma incumplimiento de nadie"),
#  y un filtro ciego las confundiria con lo contrario de lo que dicen. Lo
#  aprendi de esta misma prueba: la primera version fallaba sobre el texto
#  correcto.
ABANDONO = ("abandon", "desatend", "incumpl", "atraso", "culpa")


_TICKET = itertools.count(9000)


@pytest.fixture
def actividad_bloqueada(org_a, user_profile):
    return ActividadOperativa.objects.create(
        org=org_a, titulo="Cambiar el ONT", responsable=user_profile,
        estado_operativo=ActividadOperativa.BLOQUEADA,
        motivo_bloqueo="falta material",
    )


def _caso(org, *, dias=9, externo="", respuestas=0, status="New"):
    """
    Un caso abierto con 'dias' de antiguedad y un estado externo dado.

    'provider' y 'external_ticket_id' van juntos o no van: la tabla lo exige
    con 'case_external_ref_complete', y es el mismo par que deja la
    importacion real.
    """
    externo_id = str(next(_TICKET)) if externo else ""
    caso = Case.objects.create(org=org, name="Sin internet", status=status,
                               priority="Normal", external_status=externo,
                               external_ticket_id=externo_id,
                               provider="wisphub" if externo else "")
    Case.objects.filter(pk=caso.pk).update(
        created_at=timezone.now() - timedelta(days=dias),
        external_fetched_at=timezone.now() if externo else None)
    for i in range(respuestas):
        RespuestaExterna.objects.create(
            org=org, case=caso, provider="wisphub", huella=f"h{caso.pk}-{i}",
            autor_nombre="tecnico", cuerpo="ya se atendio",
            creada_en_proveedor=timezone.now() - timedelta(days=1))
    caso.refresh_from_db()
    return caso


def _senales(org, origen_id=None):
    todas = supervisor.detectar(org)
    if origen_id is None:
        return todas
    return [s for s in todas if s.origen_id == str(origen_id)]


def _tipos(org):
    return sorted(s.tipo for s in supervisor.detectar(org))


# =============================================================================
#  A / F.  Cerrado afuera  ->  inconsistencia de sincronizacion, jamas abandono
# =============================================================================

def test_a_cerrado_en_el_proveedor_no_es_caso_antiguo(org_a):
    caso = _caso(org_a, dias=12, externo="Cerrado", respuestas=2)
    senales = _senales(org_a, caso.id)

    assert [s.tipo for s in senales] == [PropuestaSupervisor.CASO_DESINCRONIZADO]
    assert senales[0].huella == "cerrado_en_proveedor_abierto_en_crm"
    assert senales[0].datos["clasificacion"] == "OBSERVADO"


def test_f_la_propuesta_habla_de_sincronizacion_y_no_de_incumplimiento(org_a):
    caso = _caso(org_a, dias=12, externo="Cerrado")
    analisis = supervisor.analizar(_senales(org_a, caso.id)[0])

    visible = f"{analisis['accion_propuesta']} {analisis['impacto']}".lower()
    assert "sincroniza" in visible
    for palabra in ABANDONO:
        assert palabra not in visible, f"la propuesta insinua '{palabra}'"
    #  Y el motivo dice explicitamente que no afirma incumplimiento.
    motivo = analisis["motivo"].lower()
    assert "no se afirma incumplimiento de nadie" in motivo
    assert "inconsistencia entre los dos sistemas" in motivo
    #  No recomienda actuar sobre el caso: lo que hay que mirar es la
    #  sincronizacion, y eso no es una accion operativa sobre el cliente.
    assert analisis["nivel"] == PropuestaSupervisor.NIVEL_OBSERVAR


def test_f_cerrado_afuera_tambien_se_reconoce_con_otra_capitalizacion(org_a):
    caso = _caso(org_a, dias=12, externo="  CERRADO  ")
    assert [s.tipo for s in _senales(org_a, caso.id)] == [
        PropuestaSupervisor.CASO_DESINCRONIZADO]


# =============================================================================
#  B / C.  En curso afuera y con respuestas  ->  ninguna señal
# =============================================================================

@pytest.mark.parametrize("externo", ["Nuevo", "En Progreso"])
def test_bc_en_curso_con_respuestas_no_genera_señal(org_a, externo):
    caso = _caso(org_a, dias=20, externo=externo, respuestas=3)
    assert _senales(org_a, caso.id) == []


# =============================================================================
#  E.  En curso afuera y SIN respuestas  ->  se conserva la deteccion
# =============================================================================

def test_e_sin_respuestas_sigue_siendo_detectable(org_a):
    caso = _caso(org_a, dias=20, externo="Nuevo", respuestas=0)
    senales = _senales(org_a, caso.id)

    assert [s.tipo for s in senales] == [PropuestaSupervisor.CASO_ANTIGUO]
    assert senales[0].huella == "abierto_sin_respuesta_registrada"
    assert senales[0].datos["clasificacion"] == "OBSERVADO"
    evidencia = " ".join(e["dato"] for e in senales[0].evidencia)
    assert "sin ninguna respuesta registrada" in evidencia


def test_e_el_motivo_no_atribuye_incumplimiento_a_nadie(org_a):
    caso = _caso(org_a, dias=20, externo="Nuevo")
    motivo = supervisor.analizar(_senales(org_a, caso.id)[0])["motivo"].lower()

    for palabra in ABANDONO:
        assert palabra not in motivo, f"el motivo insinua '{palabra}'"


# =============================================================================
#  D.  Sin estado externo  ->  se mantiene la incertidumbre, no se inventa
# =============================================================================

def test_d_sin_estado_externo_no_se_inventa_ninguno(org_a):
    caso = _caso(org_a, dias=9, externo="")
    senales = _senales(org_a, caso.id)

    assert [s.tipo for s in senales] == [PropuestaSupervisor.CASO_ANTIGUO]
    assert senales[0].datos["clasificacion"] == "DATOS_FALTANTES"
    assert senales[0].huella == "abierto_sin_resolucion"
    evidencia = " ".join(e["dato"] for e in senales[0].evidencia).lower()
    assert "desconocido" in evidencia
    assert "cerrado" not in evidencia


def test_d_un_estado_externo_no_reconocido_tampoco_se_interpreta(org_a):
    caso = _caso(org_a, dias=9, externo="Pendiente de repuesto")
    senal = _senales(org_a, caso.id)[0]

    assert senal.tipo == PropuestaSupervisor.CASO_ANTIGUO
    assert senal.datos["clasificacion"] == "DATOS_FALTANTES"
    #  El valor crudo viaja en la evidencia: quien lo lea ve QUE decia.
    assert "Pendiente de repuesto" in " ".join(e["dato"] for e in senal.evidencia)


def test_d_el_motivo_dice_que_falta_el_dato(org_a):
    caso = _caso(org_a, dias=9, externo="")
    motivo = supervisor.analizar(_senales(org_a, caso.id)[0])["motivo"].lower()

    assert "no consta el estado" in motivo
    assert "falta el dato" in motivo


# =============================================================================
#  G.  Los demas detectores no cambian
# =============================================================================

def test_g_un_caso_reciente_sigue_sin_generar_nada(org_a):
    _caso(org_a, dias=2, externo="")
    assert _tipos(org_a) == []


def test_g_los_demas_detectores_no_se_tocaron(org_a, actividad_bloqueada):
    #  Con un caso cerrado afuera Y una actividad bloqueada, la actividad sigue
    #  produciendo su señal de siempre: el cambio es del detector de casos.
    _caso(org_a, dias=12, externo="Cerrado")
    tipos = _tipos(org_a)

    assert PropuestaSupervisor.ACTIVIDAD_BLOQUEADA in tipos
    assert PropuestaSupervisor.CASO_DESINCRONIZADO in tipos
    assert PropuestaSupervisor.CASO_ANTIGUO not in tipos


# =============================================================================
#  H.  Deduplicacion: el mismo caso no se propone dos veces
# =============================================================================

def test_h_el_ciclo_no_duplica_la_inconsistencia(org_a):
    _caso(org_a, dias=12, externo="Cerrado")

    primero = supervisor.correr_ciclo(org_a)
    segundo = supervisor.correr_ciclo(org_a)

    assert primero["propuestas"] == 1
    assert segundo["propuestas"] == 0
    assert segundo["repetidas"] == 1
    assert PropuestaSupervisor.objects.filter(
        org=org_a, tipo_senal=PropuestaSupervisor.CASO_DESINCRONIZADO).count() == 1


def test_h_la_huella_no_lleva_la_magnitud(org_a):
    """Un dia mas no convierte la condicion en otra."""
    _caso(org_a, dias=12, externo="Cerrado")
    supervisor.correr_ciclo(org_a)

    despues = timezone.now() + timedelta(days=5)
    assert supervisor.correr_ciclo(org_a, ahora=despues)["propuestas"] == 0


# =============================================================================
#  I.  Aislamiento por organizacion
# =============================================================================

def test_i_una_organizacion_no_ve_los_casos_de_la_otra(org_a, org_b):
    _caso(org_a, dias=12, externo="Cerrado")
    _caso(org_b, dias=12, externo="Cerrado")

    señales_a = supervisor.detectar(org_a)
    ids_a = {s.origen_id for s in señales_a}

    assert len(señales_a) == 1
    assert {str(c.id) for c in Case.objects.filter(org=org_b)} & ids_a == set()


# =============================================================================
#  LA VALIDACION CON LOS NUMEROS DEL DIAGNOSTICO
# =============================================================================

def test_la_composicion_medida_en_produccion_se_reparte_como_se_espera(org_a):
    """
    Reproduce la COMPOSICION medida el 22/09/2026 (78 cerrados afuera, 5 en
    curso con respuestas, 13 sin respuesta) a escala, con datos sinteticos.

    Las proporciones son las reales; los numeros no: montar 96 casos no agrega
    nada que 3+2+2 no demuestre, y el diagnostico de produccion ya esta medido
    aparte. Lo que esta prueba fija es el REPARTO: ninguno de los cerrados
    afuera cae en la categoria de caso desatendido.
    """
    for _ in range(3):
        _caso(org_a, dias=12, externo="Cerrado", respuestas=1)     # los 78
    _caso(org_a, dias=12, externo="Nuevo", respuestas=2)           # los 5
    _caso(org_a, dias=12, externo="En Progreso", respuestas=1)
    _caso(org_a, dias=12, externo="Nuevo", respuestas=0)           # los 13
    _caso(org_a, dias=12, externo="", respuestas=0)

    por_tipo = {}
    for s in supervisor.detectar(org_a):
        por_tipo.setdefault(s.tipo, []).append(s)

    assert len(por_tipo[PropuestaSupervisor.CASO_DESINCRONIZADO]) == 3
    assert len(por_tipo[PropuestaSupervisor.CASO_ANTIGUO]) == 2
    #  Los dos "en curso con respuestas" no producen nada.
    assert sum(len(v) for v in por_tipo.values()) == 5

    clasificaciones = sorted(s.datos["clasificacion"]
                             for s in por_tipo[PropuestaSupervisor.CASO_ANTIGUO])
    assert clasificaciones == ["DATOS_FALTANTES", "OBSERVADO"]


def test_ningun_caso_cerrado_afuera_llega_a_la_pantalla_como_desatendido(org_a):
    """La prueba que mide el DAÑO del defecto, no su mecanismo."""
    for _ in range(3):
        _caso(org_a, dias=30, externo="Cerrado", respuestas=1)

    resumen = supervisor.correr_ciclo(org_a)
    propuestas = PropuestaSupervisor.objects.filter(org=org_a)

    assert resumen["propuestas"] == 3
    assert set(propuestas.values_list("tipo_senal", flat=True)) == {
        PropuestaSupervisor.CASO_DESINCRONIZADO}
    for p in propuestas:
        visible = f"{p.accion_propuesta} {p.impacto}".lower()
        for palabra in ABANDONO:
            assert palabra not in visible
        assert "no se afirma incumplimiento de nadie" in p.motivo.lower()
