# -*- coding: utf-8 -*-
"""
================================================================================
 UNA LECTURA CON EL GRUPO VACIO VUELVE A LA COLA, Y LA FASE LA ENCUENTRA
================================================================================

LOS DOS ESLABONES QUE ESTAS PRUEBAS FIJAN  --  15/10/2026
----------------------------------------------------------
Medido ese dia: 15 de 44 propuestas tenian 'grupo' en blanco. La causa no era
el texto --decian "No tiene internet, LOS en rojo"-- sino que el modelo, al no
poder leer el equipo ('onu_no_vinculada'), se callaba tambien el grupo.
Corregidas las instrucciones, releerlas devolvio grupo en 14 de 15.

Pero releerlas no ocurria, por dos razones encadenadas:

    1. 'le_falta_el_grupo' cortaba en la PRIMERA pieza que tuviera la clave
       'grupo', sin mirar su valor. Con la clave presente y vacia contestaba
       "no le falta nada".

    2. '_leer_tickets_abiertos' recorre 'for s in senales', asi que solo
       pregunta por los tickets que 'detectar' trajo en ESA vuelta. El ciclo
       del boton termino en 1,1 segundos con 'tickets leidos=None': las 35
       señales eran todas 'caso_abierto_antiguo' y ninguna tocaba a esas 15.

EL 2 ES LA CUARTA VEZ DE LA MISMA FORMA --la decision puesta en una rama a la
que los casos que importan no llegan-- y se cierra igual que la tercera: que la
fase CONSULTE las propuestas pendientes por su cuenta. Ver el encabezado de
'test_el_paso_es_su_propia_fase.py', que cuenta las tres anteriores.

LO QUE ESTAS PRUEBAS NO MIDEN: que el modelo devuelva el grupo. Eso es conducta
del modelo y no se fija con una unitaria -- lo sostiene la medicion de ese dia
(0 de 15 antes, 14 de 15 despues), repetible.
================================================================================
"""
import uuid

import pytest

from operaciones import diagnostico_de_ticket as dxt
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


def _caso(org, nombre="No tiene internet"):
    from cases.models import Case

    return Case.objects.create(
        org=org, name=nombre, status="New", priority="Normal", is_active=True,
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="3614",
        description="No Tiene Internet. No ping. LOS en rojo.")


def _propuesta(org, caso, *, grupo):
    """Una propuesta con su lectura guardada. 'grupo' puede venir vacio."""
    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.PROPUESTA,
        evidencia=[{
            "fuente": dxt.FUENTE,
            "dato": "se leyó el reclamo y no alcanza para una hipótesis",
            "observado_en": "2026-10-15T04:58:46Z",
            "grupo": grupo,
            "labor": "",
            "labor_porque": "no se pudo leer el equipo (onu_no_vinculada)",
            "labor_verificada": False,
            "confianza": "sin_hipotesis",
            "confianza_del_grupo": "",
        }])


# =============================================================================
#  §1  EL GRUPO VACIO VUELVE A LA COLA
# =============================================================================

def test_con_el_grupo_VACIO_le_falta_el_grupo(org_a):
    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")

    assert dxt.le_falta_el_grupo(p) is True, (
        "la clave está pero vino vacía: es una lectura incompleta, y el paso "
        "a Despacho no puede decidirla")


def test_con_el_grupo_PUESTO_no_se_relee(org_a):
    """La otra mitad: no gastar una consulta al modelo por una lectura sana."""
    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo=pytest.importorskip(
        "operaciones.paso_a_despacho").OBRA_DE_RED)

    assert dxt.le_falta_el_grupo(p) is False


def test_un_grupo_de_solo_espacios_cuenta_como_vacio(org_a):
    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="   ")
    assert dxt.le_falta_el_grupo(p) is True


def test_la_ULTIMA_lectura_manda_y_no_la_primera(org_a):
    """
    La evidencia se acumula. Una propuesta leída dos veces --vacía primero,
    con grupo después-- ya no necesita releerse, y al revés sí.
    """
    from operaciones import paso_a_despacho as pad

    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")
    p.evidencia.append({
        "fuente": dxt.FUENTE, "dato": "segunda lectura",
        "observado_en": "2026-10-15T23:42:00Z",
        "grupo": pad.OBRA_DE_RED, "labor": "",
        "labor_porque": "", "labor_verificada": False,
        "confianza": "media", "confianza_del_grupo": "alta",
    })
    p.save(update_fields=["evidencia"])

    assert dxt.le_falta_el_grupo(p) is False, (
        "la primera vino vacía y la segunda trajo grupo: releerla otra vez "
        "sería pagar una consulta al modelo por un dato que ya está")


def test_despues_de_TRES_lecturas_se_deja_como_esta(org_a):
    """
    EL TOPE, Y NO ES ADORNO. Un ticket cuyo texto de verdad no diga qué se
    pide va a volver vacío siempre; sin tope volvería a la cola en cada vuelta
    para siempre. Es el bucle de 43 lecturas sobre 11 propuestas del 14/10.
    """
    from operaciones.razonamiento_modelos import (FuenteRazonamiento,
                                                  RazonamientoSupervisor)

    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")
    assert dxt.le_falta_el_grupo(p) is True, "con cero lecturas, sí"

    from django.utils import timezone

    for _ in range(dxt.MAXIMAS_RELECTURAS):
        RazonamientoSupervisor.objects.create(
            org=org_a, propuesta=p, registrado_en=timezone.now(),
            fuente=FuenteRazonamiento.LECTURA_TICKET)

    assert dxt.le_falta_el_grupo(p) is False, (
        "pasado el tope se deja como está y la mira una persona, que es la "
        "respuesta correcta para un texto que no dice nada")


# =============================================================================
#  §2  LA FASE LA ENCUENTRA AUNQUE NO HAYA SEÑAL
# =============================================================================

def test_una_lectura_que_el_modelo_no_contesto_no_gasta_el_tope(org_a):
    """
    Medido el 16/10/2026: nueve propuestas con tres relecturas que 'validar'
    descarto enteras. El modelo nunca contesto; contarlas como lecturas las
    dejaba sin grupo para siempre. Con el doble del tope, si se deja.
    """
    from operaciones import cerebro, razonamiento
    from operaciones.razonamiento_modelos import FuenteRazonamiento

    #  Por el camino real: 'validar' produce el descarte y 'registrar' lo
    #  guarda con su saneo, como en la lectura. Si alla cambia el texto o el
    #  saneo, esta prueba tiene que enterarse (auditor independiente, 16/10).
    def _una_lectura_rota(p):
        v = cerebro.validar(cerebro._json_de("pidio otra herramienta"),
                            cerebro.Razonamiento())
        fila = razonamiento.registrar(
            org_a, v, fuente=FuenteRazonamiento.LECTURA_TICKET, propuesta=p)
        assert fila is not None, "no se pudo registrar la lectura de prueba"

    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")
    for _ in range(dxt.MAXIMAS_RELECTURAS):
        _una_lectura_rota(p)
    assert dxt.le_falta_el_grupo(p) is True, (
        "tres respuestas que no se pudieron leer no son tres lecturas")

    for _ in range(dxt.MAXIMAS_RELECTURAS):
        _una_lectura_rota(p)
    assert dxt.le_falta_el_grupo(p) is False, "con el doble, se deja como esta"


def test_una_lectura_con_otro_descarte_SI_cuenta(org_a):
    """
    Una lectura que contesto pero tuvo algo descartado --un hecho sin fuente,
    un campo fuera de lista-- es una lectura: cuenta para el tope. Si no
    contara, un ticket se leeria hasta seis veces (auditor independiente).
    """
    from django.utils import timezone

    from operaciones.razonamiento_modelos import (
        FuenteRazonamiento,
        RazonamientoSupervisor,
    )

    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")
    for _ in range(dxt.MAXIMAS_RELECTURAS):
        RazonamientoSupervisor.objects.create(
            org=org_a, propuesta=p, registrado_en=timezone.now(),
            fuente=FuenteRazonamiento.LECTURA_TICKET,
            descartes=["un hecho cita una herramienta que no se consulto"])

    assert dxt.le_falta_el_grupo(p) is False


def test_la_fase_recoge_la_que_NO_produjo_senal(org_a):
    """
    El síntoma medido: el ciclo del botón terminó en 1,1 s con
    'tickets leidos=None' porque ninguna señal tocaba a esas propuestas.
    """
    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo="")

    extra = sup._las_que_esperan_relectura(org_a, [])

    assert len(extra) == 1, (
        "sin señal que la traiga, la fase tiene que consultarla por su cuenta")
    assert str(extra[0].origen_id) == str(caso.id)
    assert extra[0].tipo == PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO


def test_la_fase_NO_duplica_lo_que_ya_vino_por_senal(org_a):
    """Duplicarla sería leer el mismo ticket dos veces en la misma vuelta."""
    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")

    ya_vino = sup._SinSenal(p)
    extra = sup._las_que_esperan_relectura(org_a, [ya_vino])

    assert extra == [], "ya venía por señal: traerla otra vez la lee dos veces"


def test_la_fase_NO_recoge_a_la_que_ya_tiene_grupo(org_a):
    from operaciones import paso_a_despacho as pad

    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo=pad.FALLA_DE_SERVICIO)

    assert sup._las_que_esperan_relectura(org_a, []) == [], (
        "una lectura sana no vuelve a la cola: cada relectura cuesta una "
        "consulta al modelo")


def test_la_fase_NO_recoge_a_una_YA_DECIDIDA(org_a):
    """Una persona ya resolvió: releerla gasta la vuelta y no cambia nada."""
    caso = _caso(org_a)
    p = _propuesta(org_a, caso, grupo="")
    p.estado = PropuestaSupervisor.ACEPTADA
    p.save(update_fields=["estado"])

    assert sup._las_que_esperan_relectura(org_a, []) == []


def test_la_fase_NO_cruza_empresas(org_a, org_b):
    """La propuesta de otra empresa no entra, aunque le falte el grupo."""
    caso = _caso(org_b)
    _propuesta(org_b, caso, grupo="")

    assert sup._las_que_esperan_relectura(org_a, []) == []


# =============================================================================
#  §3  Y LA FASE DE VERDAD LA USA
# =============================================================================
#  ESTAS DOS EXISTEN PORQUE LAS DE ARRIBA NO ALCANZABAN  --  15/10/2026
#
#  Medido con una mutacion: borrando el enganche
#  'senales = senales + _las_que_esperan_relectura(org, senales)' de
#  '_leer_tickets_abiertos', las diez pruebas anteriores siguieron EN VERDE.
#
#  El motivo es que llaman a '_las_que_esperan_relectura' DIRECTO: afirman que
#  la funcion es correcta, no que alguien la llame. Es el mismo error que esta
#  sesion venia persiguiendo --el mecanismo en vez del efecto-- y lo cazo la
#  mutacion, no la lectura del codigo.
#
#  Estas dos corren la FASE y miran que el ticket llegue a leerse.

def _fase_con_lectura_espiada(org, monkeypatch):
    """Corre la fase con 'diagnosticar' espiado. Devuelve los origen_id leidos."""
    from django.utils import timezone

    vistos = []

    def _espia(org_, senales, *, ahora=None, tope=None, concluir=None,
               propuestas=None):
        vistos.extend(str(getattr(s, "origen_id", "")) for s in senales)
        return {}

    monkeypatch.setattr(dxt, "diagnosticar", _espia)
    sup._leer_tickets_abiertos(org, timezone.now())
    return vistos


def test_la_FASE_manda_a_leer_la_del_grupo_vacio(org_a, monkeypatch):
    """El efecto: el ticket llega a 'diagnosticar' aunque no haya señal."""
    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo="")

    vistos = _fase_con_lectura_espiada(org_a, monkeypatch)

    assert str(caso.id) in vistos, (
        "la fase no la mandó a leer: con 'for s in senales' sola, un ticket "
        "sin señal en esta vuelta no se relee nunca")


def test_la_FASE_no_manda_a_leer_la_que_ya_tiene_grupo(org_a, monkeypatch):
    """La otra mitad: no gastar una consulta al modelo por una lectura sana."""
    from operaciones import paso_a_despacho as pad

    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo=pad.OBRA_DE_RED)

    vistos = _fase_con_lectura_espiada(org_a, monkeypatch)

    assert str(caso.id) not in vistos


# =============================================================================
#  §4  LA CORRIDA DEL RELOJ LEE MAS QUE EL BOTON
# =============================================================================
#  POR QUE  --  16/10/2026. 'desatendido' se le pasaba solo a la fase de
#  cierres; la de lectura usaba siempre el tope corto. Medido en produccion esa
#  noche: 161 pendientes, ~50 esperando relectura, bajando de 50 a 44 por
#  vuelta. Cinco horas para drenar algo que no tiene a nadie esperando.
#
#  SE AFIRMA SOBRE EL TOPE QUE LLEGA A 'diagnosticar', no sobre la constante:
#  una prueba que comparara los dos numeros entre si seguiria en verde aunque
#  la fase no se los pasara -- que es exactamente como se descubrio esto.

def _tope_que_recibe(org, monkeypatch, *, desatendido):
    from django.utils import timezone

    visto = {}

    def _espia(org_, senales, *, ahora=None, tope=None, concluir=None,
               propuestas=None):
        visto["tope"] = tope
        return {}

    monkeypatch.setattr(dxt, "diagnosticar", _espia)
    sup._leer_tickets_abiertos(org, timezone.now(), desatendido=desatendido)
    return visto.get("tope", "NO SE LLAMO")


def test_la_corrida_del_reloj_lee_MAS(org_a, monkeypatch):
    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo="")

    tope = _tope_que_recibe(org_a, monkeypatch, desatendido=True)

    assert tope == sup.TOPE_TICKETS_DESATENDIDO
    assert tope > sup.TOPE_TICKETS_POR_CORRIDA, (
        "si no lee más que el botón, una cola grande tarda horas sin que "
        "nadie gane nada")


def test_el_boton_SIGUE_con_el_tope_corto(org_a, monkeypatch):
    """Ahí sí hay alguien mirando la pantalla, y una corrida larga se siente."""
    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo="")

    tope = _tope_que_recibe(org_a, monkeypatch, desatendido=False)

    assert tope is None, (
        "pasar None deja que 'diagnosticar' aplique TOPE_TICKETS_POR_CORRIDA, "
        "que es la fuente única de ese número")


def test_el_que_NO_se_declara_hereda_el_tope_corto(org_a, monkeypatch):
    """El defecto es el atendido: equivocarse por lento, no por caro."""
    from django.utils import timezone

    caso = _caso(org_a)
    _propuesta(org_a, caso, grupo="")

    visto = {}

    def _espia(org_, senales, *, ahora=None, tope=None, concluir=None,
               propuestas=None):
        visto["tope"] = tope
        return {}

    monkeypatch.setattr(dxt, "diagnosticar", _espia)
    #  SIN declarar 'desatendido', como lo haría un llamador nuevo.
    sup._leer_tickets_abiertos(org_a, timezone.now())

    assert visto.get("tope") is None
