# -*- coding: utf-8 -*-
"""
================================================================================
 FASE 1  --  el cerebro conectado: una sola implementacion, dos entradas
================================================================================

QUE SE PRUEBA
-------------
Que 'operaciones/cerebro.py' sea el UNICO razonador, y que el chat y el ciclo
sean dos entradas suyas. Mas las tres piezas que la fase agrego:
'contexto_para' (D2), 'senal_de_veredicto' (D3) y 'aprendizaje_relevante' (D4).

LA PRUEBA QUE DA SENTIDO A LA FASE
----------------------------------
'test_5' y 'test_6' parchean UN SOLO punto --'cerebro._pedirle_al_modelo'-- y
desde ahi atienden tanto una pregunta de chat como una entrada operacional. Si
hubiera dos cerebros, una de las dos no pasaria por ese parche. Es la forma de
afirmar "hay uno" sobre el EFECTO y no sobre la lectura de los imports.

EL CRITERIO DE EXITO DE LA FASE ES QUE EL CHAT NO CAMBIE
--------------------------------------------------------
§1 afirma lo que ya hacia: los mismos roles persistidos, el mismo tope de
vueltas, el mismo texto cuando se agotan, un fallo guardado como fallo, y la
traza sin el resultado de la herramienta. Una refactorizacion que "casi" no
cambia nada es la forma mas barata de romper algo que funcionaba.

LO QUE SE SUSTITUYE
-------------------
Una sola cosa: la llamada al modelo. El catalogo, el despachador, la lista
blanca de argumentos, la persistencia y el tenant son reales.
================================================================================
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.utils import timezone

from common.models import Activity, Profile, User
from operaciones import cerebro, chat
from operaciones.chat_modelos import RolMensaje
from operaciones.models import PropuestaSupervisor
from operaciones.situaciones_modelos import (Confianza, Riesgo,
                                             SituacionOperativa)

#  EL UNICO punto que se sustituye en todo el archivo.
RUTA_MODELO = "operaciones.cerebro._pedirle_al_modelo"
P = PropuestaSupervisor
S = SituacionOperativa


# =============================================================================
#  andamio
# =============================================================================

@pytest.fixture
def jefe(org_a):
    u = User.objects.create_user(email="jefe.f1@prueba.local",
                                 password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org_a, role="OPERACIONES",
                                  is_active=True)


@pytest.fixture
def entorno():
    import os
    return mock.patch.dict(os.environ, {"MOTOR_TENANT": "rapilink"},
                           clear=False)


def _contesta(texto="Hay una situación viva en el PON 3/1/4.", llamadas=None):
    return {"contenido": texto, "llamadas": llamadas or [],
            "modelo": "deepseek-v4-flash", "proveedor": "deepseek"}


def _veredicto_crudo(**kw):
    base = {
        "hechos": [{"dato": "12 ONT caídas en el PON 3/1/4",
                    "fuente": "listar_situaciones"}],
        "inferencias": ["la concentración sugiere un tramo óptico"],
        "riesgos": ["12 abonados siguen sin servicio"],
        "riesgo": Riesgo.ALTO,
        "hipotesis": "posible corte en la troncal",
        "confianza": Confianza.MEDIA,
        "recomendacion": "revisar el empalme de la caja",
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


def _situacion(org, **extra):
    ahora = timezone.now()
    datos = dict(org=org, codigo="S-700", tipo=S.AFECTACION_PON,
                 titulo="Posible afectación del PON 3/1/4",
                 descripcion="concentración", estado=S.DETECTADA,
                 riesgo=Riesgo.ALTO, huella="afectacion_pon|pon:3/1/4",
                 detectada_en=ahora, actualizada_en=ahora,
                 senal_vista_en=ahora, fuente_origen="smartolt",
                 afectados_contados=12)
    datos.update(extra)
    return S.objects.create(**datos)


# =============================================================================
#  §1  EL CHAT NO CAMBIO  --  el criterio de exito de la fase
# =============================================================================

def test_1_un_turno_sigue_guardando_pregunta_y_respuesta(org_a, admin_profile,
                                                         entorno):
    c = chat.abrir(org_a, admin_profile)

    with entorno, mock.patch(RUTA_MODELO, return_value=_contesta()):
        r = chat.responder(c, "¿Qué está pasando?")

    assert r.rol == RolMensaje.SUPERVISOR
    assert r.contenido.startswith("Hay una situación")
    roles = list(c.mensajes.order_by("escrito_en").values_list("rol",
                                                               flat=True))
    assert roles == [RolMensaje.HUMANO, RolMensaje.SUPERVISOR]
    assert r.modelo == "deepseek-v4-flash" and r.proveedor == "deepseek"


def test_2_un_fallo_se_sigue_guardando_como_fallo(org_a, admin_profile,
                                                  entorno):
    """
    Un hueco silencioso es indistinguible de un turno que nadie mandó. Y el
    error del cerebro se traduce al del chat para que quien lo atrapaba siga
    atrapándolo.
    """
    c = chat.abrir(org_a, admin_profile)

    with entorno, mock.patch(RUTA_MODELO,
                             side_effect=cerebro.ErrorCerebro("no contestó")):
        r = chat.responder(c, "¿y ahora?")

    assert r.rol == RolMensaje.ERROR
    assert r.error == "no contestó"
    assert r.contenido == "No pude responder en este momento."


def test_3_el_tope_de_vueltas_es_el_mismo_y_viene_de_UN_lugar(org_a,
                                                              admin_profile,
                                                              entorno):
    """
    Lo que lo hace valioso: 'chat.VUELTAS_MAXIMAS' no es una copia -- es el del
    cerebro. Un duplicado dejaría al chat diciendo tres y al cerebro dando
    cinco, y la prueba del gasto mediría otra cosa.
    """
    assert chat.VUELTAS_MAXIMAS == cerebro.VUELTAS_MAXIMAS == 3
    assert chat.VARIABLE_URL == cerebro.VARIABLE_URL
    assert chat.URL_POR_DEFECTO == cerebro.URL_POR_DEFECTO

    c = chat.abrir(org_a, admin_profile)
    pide = _contesta("", [{"nombre": "estado_fuentes", "argumentos": {}}])

    with entorno, mock.patch(RUTA_MODELO, return_value=pide) as m:
        r = chat.responder(c, "¿cómo están las fuentes?")

    assert m.call_count == chat.VUELTAS_MAXIMAS
    assert "no logré cerrar una respuesta" in r.contenido


def test_4_la_traza_no_guarda_el_resultado_de_la_herramienta(org_a,
                                                             admin_profile,
                                                             entorno):
    c = chat.abrir(org_a, admin_profile)
    respuestas = [
        _contesta("", [{"nombre": "listar_situaciones",
                        "argumentos": {"limite": 5}}]),
        _contesta("Listo."),
    ]

    with entorno, mock.patch(RUTA_MODELO, side_effect=respuestas):
        r = chat.responder(c, "¿qué situaciones hay?")

    assert len(r.herramientas) == 1
    assert set(r.herramientas[0]) == {"nombre", "argumentos", "hubo_error"}
    assert "resultado" not in r.herramientas[0]
    #  Y el contexto ahora dice cuántas vueltas dio, que antes no se sabía.
    assert r.contexto_usado["vueltas"] == 2
    assert r.contexto_usado["agotado"] is False


# =============================================================================
#  §2  HAY UN SOLO CEREBRO  --  las dos pruebas fundamentales
# =============================================================================

def test_5_FUNDAMENTAL_entrada_de_chat_pasa_por_el_cerebro(org_a,
                                                           admin_profile,
                                                           entorno):
    """
    PRUEBA FUNDAMENTAL 2: entrada de chat -> cerebro -> respuesta.

    Se parchea 'cerebro._pedirle_al_modelo'. Si el chat tuviera su propia
    implementación, este parche no lo alcanzaría y la prueba fallaría.
    """
    c = chat.abrir(org_a, admin_profile)

    with entorno, mock.patch(RUTA_MODELO, return_value=_contesta()) as m:
        r = chat.responder(c, "¿qué debería revisar primero?")

    assert m.called, "el chat NO pasó por el cerebro"
    assert r.rol == RolMensaje.SUPERVISOR


def test_6_FUNDAMENTAL_entrada_operacional_pasa_por_el_MISMO_cerebro(
        org_a, entorno):
    """
    PRUEBA FUNDAMENTAL 1: entrada operacional -> cerebro -> Veredicto -> Senal.

    El mismo parche que atendió al chat atiende esto. Eso es "un solo cerebro",
    afirmado sobre el efecto.
    """
    s = _situacion(org_a)
    respuestas = [
        _contesta("", [{"nombre": "listar_situaciones", "argumentos": {}}]),
        _contesta(json.dumps(_veredicto_crudo())),
    ]

    with entorno, mock.patch(RUTA_MODELO, side_effect=respuestas) as m:
        contexto = cerebro.contexto_para(org_a, situacion=s)
        v = cerebro.concluir(org_a, instrucciones="sos el supervisor",
                             entrada=contexto)
        senal = cerebro.senal_de_veredicto(
            v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
            dimension="pon", clave_dimension="3/1/4")

    assert m.called
    assert v.concluyente is True and len(v.hechos) == 1
    assert senal is not None
    assert senal.hipotesis == "posible corte en la troncal"
    assert senal.confianza == Confianza.MEDIA
    assert "listar_situaciones" in senal.hecho, "el hecho viaja con su fuente"


def test_7_las_dos_entradas_comparten_el_bucle_y_el_catalogo(org_a):
    """
    Se afirma sobre el código: 'chat.py' ya no tiene un bucle propio, y el
    catálogo que ve el cerebro es el mismo que veía el chat.
    """
    import ast
    import inspect

    from operaciones import chat_herramientas

    #  SE MIDE EL CODIGO, NO LA PROSA. La primera version buscaba la cadena
    #  "chat_herramientas.ejecutar" en el texto del modulo y fallaba por un
    #  DOCSTRING que la nombra para explicar quien pone el tenant. Una guarda
    #  que se cae por un comentario no mide lo que dice medir -- y arreglarla
    #  borrando el comentario habria sido peor.
    arbol_chat = ast.parse(inspect.getsource(chat))
    llamadas = set()
    for n in ast.walk(arbol_chat):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            duenio = getattr(n.func.value, "id", "")
            llamadas.add(f"{duenio}.{n.func.attr}" if duenio else n.func.attr)

    #  El bucle se fue: el chat ya no EJECUTA herramientas ni llama al modelo.
    assert "chat_herramientas.ejecutar" not in llamadas
    assert "cerebro.razonar" in llamadas
    #  Y no quedo un bucle de vueltas propio.
    assert not [n for n in ast.walk(arbol_chat)
                if isinstance(n, ast.For)
                and isinstance(n.target, ast.Name)
                and n.target.id == "_vuelta"]

    #  Y la implementación del modelo es UNA.
    arbol = ast.parse(inspect.getsource(cerebro))
    defs = [n.name for n in ast.walk(arbol)
            if isinstance(n, ast.FunctionDef)]
    assert defs.count("_pedirle_al_modelo") == 1
    assert len(chat_herramientas.HERRAMIENTAS) == 19


# =============================================================================
#  §3  D2 · EL ARMADOR DE CONTEXTO
# =============================================================================

def test_8_contexto_sin_origen_da_el_panorama(org_a):
    texto = cerebro.contexto_para(org_a)

    assert "PANORAMA DEL TURNO" in texto
    assert "APRENDIZAJE PREVIO" in texto
    #  La procedencia sobrevive a la traducción a texto: es lo que impide que
    #  el modelo lea un INFERIDO como una medición.
    assert "[OBSERVADO]" in texto and "[INFERIDO]" in texto


def test_9_contexto_de_una_situacion_la_incluye_con_su_confianza(org_a):
    s = _situacion(org_a, hipotesis="posible falla óptica",
                   confianza=Confianza.BAJA)

    texto = cerebro.contexto_para(org_a, situacion=s)

    assert "LA SITUACION" in texto
    assert "S-700" in texto
    assert "posible falla óptica" in texto
    assert "confianza: baja" in texto, "una hipótesis sin su confianza miente"


def test_10_contexto_de_un_EVENTO_se_marca_como_senal_no_diagnostico(org_a):
    texto = cerebro.contexto_para(
        org_a, evento={"tipo": "saldo_bajo", "umbral": 0.1})

    assert "EL EVENTO QUE DISPARO" in texto
    assert "es una senal, no un diagnostico" in texto
    assert "saldo_bajo" in texto


def test_11_contexto_de_una_PROPUESTA_no_lleva_datos_de_cliente(org_a, jefe):
    """
    La garantía de D2. 'contexto_propuesta.contexto_de' devuelve 'cliente' y
    'asunto' -- y WispHub guarda el asunto como "Asunto - Cliente". La lista es
    BLANCA: lo que no está declarado no viaja. Se afirma sobre el TEXTO.
    """
    from cases.models import Case
    from operaciones import supervisor as sup

    #  UN NOMBRE INVENTADO, a proposito. La primera version usaba el de un
    #  cliente REAL de Rapilink --un habito que viene de pruebas anteriores de
    #  este modulo-- y no hace falta: lo que esta prueba necesita es un nombre
    #  que NO pueda aparecer en la salida, y para eso sirve mejor uno que no
    #  exista. Escribir el de una persona real en una prueba que justamente
    #  verifica que los nombres no lleguen al prompt es la ironia barata que
    #  conviene no dejar en el repositorio.
    caso = Case.objects.create(
        org=org_a, name="ZZTESTAPELLIDO INEXISTENTE - sin internet",
        status="New", priority="Normal")
    senal = sup.Senal(tipo=P.CASO_ANTIGUO, origen_tipo="case",
                      origen_id=str(caso.id),
                      evidencia=[{"fuente": "dexter", "dato": "9 días",
                                  "observado_en": timezone.now().isoformat()}],
                      huella=f"f1:{caso.id}")
    p = sup.registrar_propuesta(org_a, senal, {
        "accion_propuesta": "Revisar este caso", "motivo": "lleva 9 días",
        "prioridad": 50, "impacto": "cliente",
        "nivel": P.NIVEL_RECOMENDAR})

    texto = cerebro.contexto_para(org_a, propuesta=p)

    assert "LA PROPUESTA" in texto
    assert "Revisar este caso" in texto
    assert "ZZTESTAPELLIDO" not in texto.upper(), (
        "el nombre del cliente llegó al prompt")
    assert "INEXISTENTE" not in texto.upper()
    assert cerebro.CAMPOS_QUE_NO_VIAJAN == ("cliente", "asunto")


def test_12_el_contexto_NO_escribe_una_fila(org_a):
    s = _situacion(org_a)
    antes = (Activity.objects.count(), S.objects.count(), P.objects.count())

    for _ in range(3):
        cerebro.contexto_para(org_a, situacion=s)

    assert (Activity.objects.count(), S.objects.count(),
            P.objects.count()) == antes


# =============================================================================
#  §4  D3 · VEREDICTO -> SENAL
# =============================================================================

def test_13_un_veredicto_NO_concluyente_no_produce_senal(org_a):
    """
    La regla que más importa de D3. Abrir una situación con una lectura que no
    cierra sería convertir "no se sabe" en "está pasando esto".
    """
    v = cerebro.validar(_veredicto_crudo(falta=["no sé cuántos abonados hay"]),
                        _traza("listar_situaciones"))
    assert v.concluyente is False

    assert cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="3/1/4") is None


def test_14_una_fuente_caida_tampoco_produce_senal(org_a):
    v = cerebro.validar(_veredicto_crudo(),
                        _traza("listar_situaciones", "estado_fuentes",
                               con_error=("estado_fuentes",)))

    assert cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="3/1/4") is None


def test_15_un_veredicto_sin_hechos_tampoco(org_a):
    v = cerebro.validar(_veredicto_crudo(hechos=[]), _traza())

    assert v.vacio is True
    assert cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="3/1/4") is None


def test_16_la_senal_separa_HECHO_de_INTERPRETACION(org_a):
    v = cerebro.validar(_veredicto_crudo(), _traza("listar_situaciones"))

    senal = cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="3/1/4")

    assert "12 ONT caídas" in senal.hecho
    assert "sugiere" not in senal.hecho, "una inferencia se colgó del hecho"
    assert "sugiere" in senal.interpretacion
    assert senal.datos["riesgos_previstos"] == ["12 abonados siguen sin servicio"]
    assert senal.datos["origen"] == "cerebro"


def test_17_la_evidencia_conserva_la_fuente_de_CADA_hecho(org_a):
    crudo = _veredicto_crudo(hechos=[
        {"dato": "12 ONT caídas", "fuente": "listar_situaciones"},
        {"dato": "la fuente SmartOLT está fresca", "fuente": "estado_fuentes"}])
    v = cerebro.validar(crudo, _traza("listar_situaciones", "estado_fuentes"))

    senal = cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="3/1/4")

    assert len(senal.evidencia) == 2
    assert {e["fuente"] for e in senal.evidencia} == {"listar_situaciones",
                                                      "estado_fuentes"}
    assert all(e["observado_en"] for e in senal.evidencia)


def test_18_el_par_hipotesis_confianza_SIEMPRE_es_uno_que_Senal_acepta(org_a):
    """
    'validar' lo garantiza y 'Senal.__init__' lo exige levantando ValueError.
    Son la MISMA regla en dos capas: por eso no pueden contradecirse. Se
    recorren los casos que podrían romperla y ninguno levanta.
    """
    for crudo in (_veredicto_crudo(),
                  _veredicto_crudo(confianza="muchísima"),
                  _veredicto_crudo(hipotesis=""),
                  _veredicto_crudo(hipotesis="", confianza="sin_hipotesis")):
        v = cerebro.validar(crudo, _traza("listar_situaciones"))
        senal = cerebro.senal_de_veredicto(
            v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
            dimension="pon", clave_dimension="3/1/4")
        if senal is not None:
            assert bool(senal.hipotesis) == (
                senal.confianza != Confianza.SIN_HIPOTESIS)


def test_19_la_senal_del_cerebro_la_consume_el_ciclo_SIN_cambios(org_a,
                                                                 entorno):
    """
    El cierre de D3: la señal que produce el cerebro entra por
    'correlacion.agrupar' --el camino que ya existía-- y abre una situación.
    """
    from operaciones import correlacion

    v = cerebro.validar(_veredicto_crudo(), _traza("listar_situaciones"))
    senal = cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="9/9/9")

    salida = correlacion.agrupar(org_a, senal)

    assert salida["creada"] is True
    s = S.objects.get(org=org_a, huella__contains="9/9/9")
    assert s.hipotesis == "posible corte en la troncal"
    assert s.confianza == Confianza.MEDIA


# =============================================================================
#  §5  D4 · APRENDIZAJE  --  historia, nunca el estado de hoy
# =============================================================================

def test_20_sin_aprendizaje_lo_dice_en_vez_de_callarse(org_a):
    texto = cerebro.aprendizaje_relevante(org_a)

    assert "no hay aprendizaje registrado" in texto
    assert "no es lo mismo que no haber tenido errores" in texto


def test_21_con_aprendizaje_lo_resume_y_avisa_que_es_HISTORIA(org_a, jefe):
    from operaciones import gobierno

    s = _situacion(org_a)
    gobierno.registrar_falso_positivo(s, actor=jefe, motivo="era mantenimiento")

    texto = cerebro.aprendizaje_relevante(org_a)

    assert "ESTO ES HISTORIA, NO EL ESTADO DE HOY" in texto
    assert "en contra: 1" in texto
    assert "consulta la herramienta" in texto


def test_22_el_aprendizaje_es_LECTURA(org_a, jefe):
    from operaciones.gobierno_modelos import AprendizajeSupervisor

    s = _situacion(org_a)
    from operaciones import gobierno
    gobierno.registrar_falso_positivo(s, actor=jefe, motivo="x")
    antes = (AprendizajeSupervisor.objects.count(), Activity.objects.count())

    for _ in range(3):
        cerebro.aprendizaje_relevante(org_a)

    assert (AprendizajeSupervisor.objects.count(),
            Activity.objects.count()) == antes


def test_23_el_aprendizaje_no_cruza_empresas(org_a, org_b, jefe):
    from operaciones import gobierno

    gobierno.registrar_falso_positivo(_situacion(org_a), actor=jefe,
                                      motivo="era mantenimiento en A")

    assert "en contra: 1" in cerebro.aprendizaje_relevante(org_a)
    assert "no hay aprendizaje registrado" in cerebro.aprendizaje_relevante(
        org_b)


# =============================================================================
#  §6  SEGURIDAD  --  recomendar no es ejecutar
# =============================================================================

def test_24_SEGURIDAD_un_veredicto_que_recomienda_una_accion_no_ejecuta_nada(
        org_a, entorno):
    """
    LA PRUEBA DE SEGURIDAD de la fase. El modelo recomienda reiniciar un
    equipo. Se afirma sobre el EFECTO: ni una orden, ni una actividad, ni una
    operación externa, y el único camino declarado a la ejecución levanta.
    """
    from campo.models import OrdenTrabajo
    from operaciones import supervisor as sup
    from operaciones.models import ActividadOperativa

    crudo = _veredicto_crudo(
        recomendacion="reiniciar la ONT del abonado 5832 AHORA")
    v = cerebro.validar(crudo, _traza("listar_situaciones"))
    senal = cerebro.senal_de_veredicto(
        v, fuente="smartolt", tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension="3/1/4")

    #  La recomendación llegó -- eso es lo que el Supervisor puede hacer.
    assert "reiniciar" in senal.recomendacion

    #  Y no pasó nada afuera.
    assert OrdenTrabajo.objects.count() == 0
    assert ActividadOperativa.objects.count() == 0
    with pytest.raises(Exception):
        sup.ejecutar_propuesta(None)
    assert sup.SHADOW_MODE is True


def test_25_SEGURIDAD_el_veredicto_no_tiene_por_donde_pedir_ejecucion(org_a):
    """
    No es que se ignore un campo de ejecución: no existe. Y el cerebro no
    importa nada que pueda mover la frontera.
    """
    import ast
    import inspect

    v = cerebro.Veredicto()
    for campo in ("ejecutar", "accion_externa", "nivel", "nivel_autonomia",
                  "autonomia", "aprobacion", "acierto", "resultado"):
        assert not hasattr(v, campo), campo

    nombres = {n.id for n in ast.walk(ast.parse(inspect.getsource(cerebro)))
               if isinstance(n, ast.Name)}
    for prohibido in ("frontera", "interruptor", "ejecutar_propuesta",
                      "registrar_propuesta", "autonomia"):
        assert prohibido not in nombres, prohibido


def test_26_SEGURIDAD_el_techo_de_la_etapa_sigue_en_RECOMENDAR(org_a):
    """La fase no lo toca, y una propuesta por encima queda fuera de alcance."""
    assert P.NIVEL_MAXIMO_ETAPA == P.NIVEL_RECOMENDAR == 1


@pytest.mark.parametrize("nivel", [P.NIVEL_COORDINAR,
                                   P.NIVEL_EJECUTAR_REVERSIBLE,
                                   P.NIVEL_CRITICO])
def test_27_SEGURIDAD_una_propuesta_de_nivel_2_3_o_4_NO_ejecuta(org_a, nivel):
    """
    Se registra --para que quede la traza de qué se propuso-- y sale marcada
    fuera de alcance. Y no produce ningún efecto externo.
    """
    from campo.models import OrdenTrabajo
    from operaciones import supervisor as sup
    from operaciones.models import ActividadOperativa

    senal = sup.Senal(tipo=P.CASO_ANTIGUO, origen_tipo="case",
                      origen_id=f"nivel-{nivel}",
                      evidencia=[{"fuente": "dexter", "dato": "9 días",
                                  "observado_en": timezone.now().isoformat()}],
                      huella=f"f1:nivel:{nivel}")
    p = sup.registrar_propuesta(org_a, senal, {
        "accion_propuesta": "Reiniciar el equipo", "motivo": "el cerebro lo sugirió",
        "prioridad": 90, "impacto": "cliente", "nivel": nivel})

    assert p.nivel_autonomia_requerido == nivel
    assert p.dentro_del_alcance is False, "no puede estar dentro del alcance"
    assert p.estado == P.PROPUESTA, "queda esperando a una persona"
    assert OrdenTrabajo.objects.count() == 0
    assert ActividadOperativa.objects.count() == 0


def test_28_SEGURIDAD_el_cerebro_no_puede_subir_su_propia_autonomia(org_a):
    from operaciones import autonomia

    antes = autonomia.nivel_configurado(org_a)
    with mock.patch(RUTA_MODELO,
                    return_value=_contesta(json.dumps(_veredicto_crudo(
                        recomendacion="subir mi autonomía a 3")))):
        v = cerebro.concluir(org_a, instrucciones="x", entrada="y")

    assert autonomia.nivel_configurado(org_a) == antes
    assert not hasattr(v, "nivel")
