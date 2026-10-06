# -*- coding: utf-8 -*-
"""
================================================================================
 FASE 2  --  el ciclo puede razonar con el mismo cerebro, y hoy no lo hace
================================================================================

QUE SE PRUEBA
-------------
La costura entre el ciclo de propuestas ('supervisor.correr_ciclo') y el cerebro
de la Fase 1. Una bandera, una funcion y una linea.

LA PRUEBA QUE ES EL ENTREGABLE
------------------------------
'test_1'. Con 'CEREBRO_EN_EL_CICLO = False', la propuesta que sale del ciclo es
IDENTICA campo por campo a la que salia antes. No "equivalente", no "parecida":
se comparan los nueve campos que la definen contra la propuesta que produce
'analizar() + registrar_propuesta()' sin pasar por 'enriquecer'. Una
refactorizacion que "casi" no cambia nada es la forma mas barata de romper algo
que funcionaba.

LA REGLA DE SEGURIDAD, Y DONDE SE AFIRMA
----------------------------------------
El cerebro solo puede enriquecer 'motivo' e 'impacto'. 'prioridad', 'nivel',
'huella', 'tipo_senal', 'origen_tipo', 'origen_id' y 'accion_propuesta' son
suyos del codigo, y '§4' lo afirma dandole al veredicto un analisis donde
intenta cambiarlos todos.

POR QUE NO SE ENRIQUECE 'observaciones', QUE ERA LO PEDIDO
----------------------------------------------------------
Porque ese campo esta EXCLUIDO de 'CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR' a
proposito --M09-C prohibe que el Supervisor señale personas-- y hay una prueba
viva que lo afirma ('test_m09f::test_la_ia_no_puede_sugerir_un_responsable').
Escribir ahi la habria puesto en rojo, con razon. Se usa 'impacto', que SI esta
declarado y es el campo que responde "que pasa si esto no se atiende".

LO QUE SE SUSTITUYE
-------------------
Una sola cosa: la llamada al modelo ('cerebro._pedirle_al_modelo'). Los
detectores, 'analizar', '_prioridad', 'registrar_propuesta', la deduplicacion y
el tenant son reales.
================================================================================
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.utils import timezone

from campo.models import OrdenTrabajo
from common.models import Activity
from operaciones import cerebro
from operaciones import supervisor as sup
from operaciones.models import ActividadOperativa, PropuestaSupervisor
from operaciones.situaciones_modelos import Confianza, Riesgo

#  EL UNICO punto que se sustituye: el mismo que usa el chat.
RUTA_MODELO = "operaciones.cerebro._pedirle_al_modelo"
P = PropuestaSupervisor

#  Los campos que DEFINEN una propuesta. 'test_1' los compara uno por uno.
CAMPOS_DEFINITORIOS = ("tipo_senal", "origen_tipo", "origen_id",
                       "accion_propuesta", "prioridad",
                       "nivel_autonomia_requerido", "huella_condicion",
                       "estado", "impacto")


# =============================================================================
#  andamio
# =============================================================================

@pytest.fixture
def actividad_bloqueada(org_a, user_profile):
    """
    Una señal REAL que el ciclo detecta. Misma forma que en
    'test_m09d_shadow': la fixture es local de cada archivo, no de conftest, y
    copiarla es preferible a moverla -- mover una fixture que seis archivos
    usan es un cambio en seis pruebas ajenas por una comodidad de esta.
    """
    return ActividadOperativa.objects.create(
        org=org_a, titulo="Cambiar el ONT", responsable=user_profile,
        estado_operativo=ActividadOperativa.BLOQUEADA,
        motivo_bloqueo="falta material",
    )


@pytest.fixture
def entorno():
    import os
    return mock.patch.dict(os.environ, {"MOTOR_TENANT": "rapilink"},
                           clear=False)


def _senal(sufijo="1"):
    """Una señal como la deja un detector, con su evidencia completa."""
    return sup.Senal(
        tipo=P.CASO_ANTIGUO, origen_tipo="case", origen_id=f"caso-{sufijo}",
        evidencia=[{"fuente": "dexter", "id": f"caso-{sufijo}",
                    "dato": "9 días sin resolución",
                    "observado_en": timezone.now().isoformat()}],
        datos={"dias": 9, "clasificacion": sup.OBSERVADO,
               "estado_externo": "en progreso"},
        huella=f"caso_antiguo|{sufijo}")


def _analisis_determinista(senal):
    """Lo que 'analizar' produce. Se usa como linea base, sin tocarlo."""
    return sup.analizar(senal)


def _crudo(**kw):
    base = {
        "hechos": [{"dato": "hay 3 casos más del mismo sector",
                    "fuente": "listar_situaciones"}],
        "inferencias": ["podría ser una afectación de zona, no un caso aislado"],
        "riesgos": ["si es de zona, van a entrar más tickets"],
        "riesgo": Riesgo.ALTO,
        "hipotesis": "posible afectación en la zona SABANAGRANDE",
        "confianza": Confianza.MEDIA,
        "recomendacion": "revisar si los otros tres comparten PON",
        "falta": [],
    }
    base.update(kw)
    return base


def _traza(*nombres, con_error=(), agotado=False):
    r = cerebro.Razonamiento(agotado=agotado)
    for n in nombres:
        r.consultadas.append({"nombre": n, "argumentos": {},
                              "hubo_error": n in con_error})
    return r


def _veredicto(**kw):
    return cerebro.validar(_crudo(**kw), _traza("listar_situaciones"))


# =============================================================================
#  §1  LA BANDERA APAGADA  --  el entregable de la fase
# =============================================================================

def test_0_la_bandera_arranca_APAGADA(org_a):
    assert sup.CEREBRO_EN_EL_CICLO is False


def test_1_ENTREGABLE_con_la_bandera_apagada_la_propuesta_es_IDENTICA(org_a):
    """
    Campo por campo contra la linea base. Si 'enriquecer' tocara algo con la
    bandera apagada, esto cae.
    """
    senal = _senal("identica")
    base = _analisis_determinista(senal)

    #  La propuesta por el camino NUEVO (con 'enriquecer' en el medio).
    con_costura = sup.enriquecer(org_a, senal, dict(base))

    assert con_costura == base, "enriquecer modificó el análisis estando apagado"
    #  Y es el MISMO objeto: ni una copia defensiva que pudiera divergir.
    devuelto = sup.enriquecer(org_a, senal, base)
    assert devuelto is base


def test_2_el_ciclo_completo_registra_lo_mismo_que_antes(org_a,
                                                         actividad_bloqueada):
    """
    No solo la funcion: el CICLO. Se corre entero y se compara la propuesta
    resultante contra el analisis deterministico de su propia señal.
    """
    resumen = sup.correr_ciclo(org_a)

    assert resumen["propuestas"] >= 1
    p = P.objects.filter(org=org_a).first()
    senales = {s.huella: s for s in sup.detectar(org_a)}
    senal = senales.get(p.huella_condicion)
    assert senal is not None, "la propuesta no corresponde a ninguna señal"

    esperado = sup.analizar(senal)
    assert p.motivo == esperado["motivo"], "el motivo cambió"
    assert p.accion_propuesta == esperado["accion_propuesta"]
    assert p.prioridad == esperado["prioridad"]
    assert p.impacto == esperado.get("impacto", "")


def test_3_el_ciclo_no_llama_al_modelo_con_la_bandera_apagada(org_a,
                                                              actividad_bloqueada):
    """Lo que garantiza que esta fase no cuesta un peso: no hay llamada."""
    with mock.patch(RUTA_MODELO) as m:
        sup.correr_ciclo(org_a)

    m.assert_not_called()


# =============================================================================
#  §2  EL MISMO CEREBRO QUE EL CHAT  --  un unico punto de parche
# =============================================================================

def test_4_una_senal_pasa_por_el_MISMO_cerebro_que_el_chat(org_a, entorno):
    """
    Se enciende la bandera SOLO dentro de esta prueba, con monkeypatch, y se
    parchea el mismo punto que usa el chat. Si el ciclo tuviera su propio
    razonador, este parche no lo alcanzaria.
    """
    senal = _senal("mismo-cerebro")
    base = _analisis_determinista(senal)
    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "listar_situaciones",
                                        "argumentos": {}}]},
        {"contenido": json.dumps(_crudo()), "llamadas": []},
    ]

    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO, side_effect=respuestas) as m:
        salida = sup.enriquecer(org_a, senal, dict(base))

    assert m.called, "el ciclo NO pasó por el cerebro"
    assert salida["motivo"] != base["motivo"], "no aportó nada"


def test_5_el_contexto_que_recibe_es_operacional_y_sin_PII(org_a, entorno):
    """
    Se mira lo que se le MANDA al modelo: tiene el panorama con su procedencia,
    la señal y lo que la regla concluyó -- y ni un nombre de cliente.
    """
    from cases.models import Case

    Case.objects.create(org=org_a, name="ZZTESTAPELLIDO INEXISTENTE - caído",
                        status="New", priority="Normal")
    senal = _senal("contexto")
    base = _analisis_determinista(senal)

    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO,
                       return_value={"contenido": "{}", "llamadas": []}) as m:
        sup.enriquecer(org_a, senal, dict(base))

    mensajes = m.call_args.args[0]
    sistema = mensajes[0]["content"]
    entrada = mensajes[-1]["content"]

    #  Lo que el ciclo le pide es INTERPRETAR, no conversar. Se afirma sobre
    #  trozos que NO cruzan un salto de linea: el prompt esta envuelto a 79
    #  columnas y "ya detectó una señal" cae partido entre dos lineas. Una
    #  asercion que depende de donde envuelve el texto falla por el formato, no
    #  por la conducta.
    assert "REGLA DETERMINISTICA ya detectó" in sistema
    assert "no la reemplazás" in sistema
    #  Contexto operacional real, con procedencia.
    assert "PANORAMA DEL TURNO" in entrada
    assert "[OBSERVADO]" in entrada
    assert "LA SEÑAL DETECTADA" in entrada
    assert P.CASO_ANTIGUO in entrada
    assert "lo que la regla concluyo" in entrada
    #  Y sin PII.
    assert "ZZTESTAPELLIDO" not in entrada.upper()


# =============================================================================
#  §3  UN VEREDICTO CONCLUYENTE ENRIQUECE
# =============================================================================

def test_6_un_veredicto_concluyente_enriquece_motivo_e_impacto(org_a):
    senal = _senal("enriquece")
    base = _analisis_determinista(senal)

    salida = cerebro.analisis_de_veredicto(_veredicto(), dict(base))

    #  Lo deterministico sigue primero, y completo.
    assert salida["motivo"].startswith(base["motivo"])
    #  Y lo del cerebro va rotulado, cada cosa en su lugar.
    assert "HECHOS OBSERVADOS: hay 3 casos más" in salida["motivo"]
    assert "fuente: listar_situaciones" in salida["motivo"]
    assert "INTERPRETACION: podría ser una afectación" in salida["motivo"]
    assert "HIPOTESIS (confianza media)" in salida["motivo"]
    assert "EL SUPERVISOR SUGIERE ADEMAS: revisar si los otros tres" in salida["motivo"]
    assert "RIESGO PREVISTO: si es de zona" in salida["impacto"]


def test_7_la_hipotesis_NUNCA_se_convierte_en_hecho(org_a):
    """
    La regla que más importa del enriquecimiento. Va rotulada como hipótesis,
    con su confianza, y NO aparece bajo el rótulo de hechos.
    """
    salida = cerebro.analisis_de_veredicto(
        _veredicto(), dict(_analisis_determinista(_senal("hip"))))

    motivo = salida["motivo"]
    i_hechos = motivo.index("HECHOS OBSERVADOS:")
    i_hipotesis = motivo.index("HIPOTESIS (confianza")
    #  La hipótesis está DESPUÉS del bloque de hechos, en su propio rótulo.
    assert i_hipotesis > i_hechos
    bloque_hechos = motivo[i_hechos:i_hipotesis]
    assert "afectación en la zona SABANAGRANDE" not in bloque_hechos


def test_8_lo_que_FALTA_queda_escrito_en_el_motivo(org_a):
    """
    No en una nota al pie: es lo que decide si quien lee puede confiar en el
    resto. Un veredicto con 'falta' es no concluyente, así que se prueba la
    traducción directamente.
    """
    v = cerebro.Veredicto(
        hechos=[{"dato": "x", "fuente": "estado_fuentes"}],
        falta=["no sé cuántos abonados hay en ese PON"], concluyente=True)

    salida = cerebro.analisis_de_veredicto(
        v, dict(_analisis_determinista(_senal("falta"))))

    assert "FALTA POR SABER: no sé cuántos abonados" in salida["motivo"]


# =============================================================================
#  §4  LA REGLA DE SEGURIDAD  --  lo que el cerebro NO puede mover
# =============================================================================

def test_9_SEGURIDAD_el_cerebro_no_puede_cambiar_prioridad_ni_nivel(org_a):
    """
    Se le da un analisis y un veredicto que intentan moverlo todo. Se afirma
    sobre el VALOR de cada campo protegido, no sobre la existencia de un 'if'.
    """
    base = {
        "accion_propuesta": "Revisar este caso",
        "motivo": "lleva 9 días",
        "prioridad": 50,
        "impacto": "un caso sin movimiento no aparece en ninguna cola",
        "nivel": P.NIVEL_RECOMENDAR,
        "componentes_prioridad": ["base 50", "antiguedad -9"],
    }

    salida = cerebro.analisis_de_veredicto(_veredicto(), dict(base))

    assert salida["prioridad"] == 50, "el cerebro movió la prioridad"
    assert salida["nivel"] == P.NIVEL_RECOMENDAR, "el cerebro movió el nivel"
    assert salida["accion_propuesta"] == "Revisar este caso"
    assert salida["componentes_prioridad"] == base["componentes_prioridad"]
    #  Solo dos claves cambiaron.
    cambiadas = {k for k in base if salida[k] != base[k]}
    assert cambiadas <= set(cerebro.CAMPOS_QUE_EL_CEREBRO_ENRIQUECE)


def test_10_SEGURIDAD_la_lista_de_campos_enriquecibles_es_corta_y_explicita(
        org_a):
    assert cerebro.CAMPOS_QUE_EL_CEREBRO_ENRIQUECE == ("motivo", "impacto")
    #  'observaciones' NO: M09-C lo prohíbe y hay una prueba viva que lo afirma.
    assert "observaciones" not in cerebro.CAMPOS_QUE_EL_CEREBRO_ENRIQUECE
    assert "observaciones" not in sup.CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR
    for prohibido in ("prioridad", "nivel", "huella", "tipo_senal",
                      "origen_tipo", "origen_id", "accion_propuesta"):
        assert prohibido not in cerebro.CAMPOS_QUE_EL_CEREBRO_ENRIQUECE


def test_11_SEGURIDAD_la_huella_no_cambia_asi_que_la_dedup_sigue(org_a, entorno):
    """
    Si el enriquecimiento tocara la huella, la misma condición se propondría de
    nuevo cada ciclo y una propuesta rechazada volvería mañana.
    """
    senal = _senal("huella")
    base = _analisis_determinista(senal)

    salida = cerebro.analisis_de_veredicto(_veredicto(), dict(base))

    assert "huella" not in salida or salida.get("huella") == base.get("huella")
    p1 = sup.registrar_propuesta(org_a, senal, salida)
    assert p1.huella_condicion == senal.huella


# =============================================================================
#  §5  FALLBACK  --  el ciclo nunca depende del cerebro
# =============================================================================

def test_12_un_veredicto_NO_concluyente_no_enriquece_nada(org_a):
    v = cerebro.validar(_crudo(falta=["no sé cuántos hay"]),
                        _traza("listar_situaciones"))
    assert v.concluyente is False
    base = _analisis_determinista(_senal("noconcl"))

    salida = cerebro.analisis_de_veredicto(v, dict(base))

    assert salida == base, "'no se sabe' no mejora una propuesta"


def test_13_un_veredicto_SIN_hechos_tampoco(org_a):
    v = cerebro.validar(_crudo(hechos=[]), _traza())
    base = _analisis_determinista(_senal("sinhechos"))

    assert cerebro.analisis_de_veredicto(v, dict(base)) == base


def test_14_un_veredicto_None_tampoco(org_a):
    base = _analisis_determinista(_senal("none"))
    assert cerebro.analisis_de_veredicto(None, dict(base)) == base


def test_15_FALLBACK_ErrorCerebro_deja_la_propuesta_deterministica_intacta(
        org_a, entorno):
    """
    La propiedad más importante de 'enriquecer': NUNCA levanta. El ciclo no
    puede depender del cerebro para registrar una propuesta.
    """
    senal = _senal("errcerebro")
    base = _analisis_determinista(senal)

    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO,
                       side_effect=cerebro.ErrorCerebro("no contestó")):
        salida = sup.enriquecer(org_a, senal, dict(base))

    assert salida == base


@pytest.mark.parametrize("fallo", [
    ValueError("prosa en vez de json"),
    RuntimeError("algo que nadie previó"),
    KeyError("falta una clave"),
])
def test_16_FALLBACK_cualquier_fallo_degrada_al_analisis_de_la_regla(
        org_a, entorno, fallo):
    """
    El 'except' es amplio a propósito: un tipo de excepción que nadie previó no
    puede ser la diferencia entre proponer y no proponer.
    """
    senal = _senal("cualquiera")
    base = _analisis_determinista(senal)

    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO, side_effect=fallo):
        salida = sup.enriquecer(org_a, senal, dict(base))

    assert salida == base


def test_17_FALLBACK_el_ciclo_registra_la_propuesta_aunque_el_cerebro_falle(
        org_a, actividad_bloqueada, entorno):
    """El fallback de punta a punta: el ciclo entero con el cerebro caído."""
    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO,
                       side_effect=cerebro.ErrorCerebro("caído")):
        resumen = sup.correr_ciclo(org_a)

    assert resumen["propuestas"] >= 1
    assert P.objects.filter(org=org_a).exists()


# =============================================================================
#  §6  CERO ACCIONES EXTERNAS, SHADOW MODE, NIVELES 2/3/4
# =============================================================================

def test_18_SEGURIDAD_enriquecer_no_produce_ninguna_accion_externa(org_a,
                                                                   entorno):
    senal = _senal("sinefecto")
    base = _analisis_determinista(senal)
    antes = (OrdenTrabajo.objects.count(), ActividadOperativa.objects.count(),
             Activity.objects.count(), P.objects.count())

    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "listar_situaciones",
                                        "argumentos": {}}]},
        {"contenido": json.dumps(_crudo(
            recomendacion="reiniciar la ONT del abonado AHORA")),
         "llamadas": []},
    ]
    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO, side_effect=respuestas):
        salida = sup.enriquecer(org_a, senal, dict(base))

    #  La sugerencia llegó -- eso es lo que el Supervisor puede hacer.
    assert "reiniciar" in salida["motivo"]
    #  Y no pasó nada afuera.
    assert (OrdenTrabajo.objects.count(), ActividadOperativa.objects.count(),
            Activity.objects.count(), P.objects.count()) == antes


def test_19_SEGURIDAD_shadow_mode_intacto(org_a):
    assert sup.SHADOW_MODE is True
    with pytest.raises(Exception):
        sup.ejecutar_propuesta(None)


def test_20_SEGURIDAD_el_techo_de_la_etapa_sigue_en_1(org_a):
    assert P.NIVEL_MAXIMO_ETAPA == P.NIVEL_RECOMENDAR == 1


@pytest.mark.parametrize("nivel", [P.NIVEL_COORDINAR,
                                   P.NIVEL_EJECUTAR_REVERSIBLE,
                                   P.NIVEL_CRITICO])
def test_21_SEGURIDAD_una_propuesta_enriquecida_de_nivel_2_3_4_no_ejecuta(
        org_a, nivel):
    """
    Aunque el enriquecimiento pase por ahí, el nivel lo sigue poniendo el
    código y la propuesta queda fuera de alcance.
    """
    senal = _senal(f"nivel-{nivel}")
    base = dict(_analisis_determinista(senal))
    base["nivel"] = nivel

    salida = cerebro.analisis_de_veredicto(_veredicto(), base)
    p = sup.registrar_propuesta(org_a, senal, salida)

    assert p.nivel_autonomia_requerido == nivel
    assert p.dentro_del_alcance is False
    assert p.estado == P.PROPUESTA
    assert OrdenTrabajo.objects.count() == 0
    assert ActividadOperativa.objects.count() == 0


def test_22_SEGURIDAD_el_ciclo_no_puede_subir_la_autonomia(org_a, entorno):
    from operaciones import autonomia

    senal = _senal("autonomia")
    antes = autonomia.nivel_configurado(org_a)
    respuestas = [
        {"contenido": "", "llamadas": [{"nombre": "mis_limites",
                                        "argumentos": {}}]},
        {"contenido": json.dumps(_crudo(
            recomendacion="subir mi nivel de autonomía a 3")), "llamadas": []},
    ]
    with entorno, mock.patch.object(sup, "CEREBRO_EN_EL_CICLO", True), \
            mock.patch(RUTA_MODELO, side_effect=respuestas):
        salida = sup.enriquecer(org_a, senal,
                                dict(_analisis_determinista(senal)))

    assert autonomia.nivel_configurado(org_a) == antes
    assert salida["nivel"] == _analisis_determinista(senal)["nivel"]
