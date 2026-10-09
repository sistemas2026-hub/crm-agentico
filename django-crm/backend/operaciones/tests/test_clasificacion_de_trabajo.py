# -*- coding: utf-8 -*-
"""
================================================================================
 DE QUE TIPO ES ESTE TRABAJO
================================================================================

Que cubre y por que
-------------------
Hasta ahora el tipo de trabajo lo elegia a mano quien despachaba. Esto lo
PROPONE, y lo que importa verificar no es que devuelva algo sino QUE SE APOYA
EN QUE:

  - la prueba le gana al texto, pero sobre una pregunta acotada
  - un equipo SANO no concluye «no hay trabajo»: concluye «no es falla de red»
  - sin energia NO manda cuadrilla -- el problema es el corte de luz del cliente
  - varios del mismo PON = UN trabajo de red, no N correctivos
  - lo que sale del texto queda marcado como NO verificado
  - lo que no se puede concluir no se concluye, y dice por que no

Son funciones puras sobre un dict: no tocan base, ni red, ni modelos. Por eso
corren en milisegundos y no necesitan Postgres.

    pytest operaciones/tests/test_clasificacion_de_trabajo.py
================================================================================
"""

import pytest

from operaciones import clasificacion_de_trabajo as clf


# ---------------------------------------------------------------------------
# A · la prueba
# ---------------------------------------------------------------------------

def test_a_caido_por_fibra_es_un_correctivo():
    r = clf.clasificar({"contexto_disponible": True, "equipo": {
        "estado": "caido", "causa_caida": "fibra"}})
    assert r["labor"] == clf.CORRECTIVO
    assert r["fuente"] == clf.POR_PRUEBA
    assert r["verificada"] is True
    assert "optica" in r["porque"]


def test_b_sin_energia_NO_manda_cuadrilla():
    """El problema es un corte de luz en la casa, no la red.

    Mandar un tecnico ahi es mandarlo a mirar como alguien espera que vuelva
    la luz.
    """
    r = clf.clasificar({"contexto_disponible": True, "equipo": {
        "estado": "caido", "causa_caida": "sin_energia"}})
    assert r["labor"] == clf.NO_REQUIERE_VISITA
    assert r["verificada"] is True
    #  Y NO es una labor: nadie puede tratarlo como un cuarto tipo de trabajo.
    assert r["labor"] not in (clf.INSTALACION, clf.CORRECTIVO, clf.TRABAJOS)


def test_c_senal_debil_es_correctivo_aunque_este_en_linea():
    r = clf.clasificar({"contexto_disponible": True, "equipo": {
        "estado": "en_linea", "senal": "debil", "senal_dbm": -27.4}})
    assert r["labor"] == clf.CORRECTIVO
    #  El numero viaja para que quien lee pueda comprobarlo por su cuenta.
    assert "-27.4" in r["porque"]


def test_d_caido_por_causa_desconocida_igual_es_correctivo_pero_no_afirma_la_causa():
    """Hay un cliente sin servicio: eso alcanza para ir. La causa, no."""
    r = clf.clasificar({"contexto_disponible": True, "equipo": {
        "estado": "caido", "causa_caida": "algo_que_nadie_mapeo"}})
    assert r["labor"] == clf.CORRECTIVO
    assert "no se afirma por que" in r["porque"]


def test_e_un_equipo_SANO_no_concluye_que_no_hay_trabajo():
    """Concluye que no es una falla de RED, que es otra cosa.

    Tratar «equipo sano» como «no hay nada que hacer» cerraria trabajos
    reales: el cliente puede estar pidiendo una reubicacion o un cambio de
    equipo.
    """
    r = clf.clasificar({"contexto_disponible": True, "equipo": {
        "estado": "en_linea", "senal": "buena", "senal_dbm": -21.8}})
    assert r["labor"] == clf.SIN_CONCLUIR
    assert "NO es una falla de red" in r["porque"]
    assert "quien despacha" in r["porque"]


def test_f_en_linea_sin_lectura_de_senal_no_concluye():
    r = clf.clasificar({"contexto_disponible": True,
                        "equipo": {"estado": "en_linea"}})
    assert r["labor"] == clf.SIN_CONCLUIR


def test_g_un_estado_que_no_se_entiende_no_se_interpreta():
    r = clf.clasificar({"contexto_disponible": True,
                        "equipo": {"estado": "vaya_uno_a_saber"}})
    assert r["labor"] == clf.SIN_CONCLUIR


# ---------------------------------------------------------------------------
# B · la falla agrupada le gana al correctivo individual
# ---------------------------------------------------------------------------

def test_h_varios_del_mismo_PON_son_UN_trabajo_de_red():
    """Cinco ordenes mandarian cinco cuadrillas al mismo poste."""
    r = clf.clasificar(
        {"contexto_disponible": True,
         "equipo": {"estado": "caido", "causa_caida": "fibra"}},
        situacion={"afectados": 8, "etiqueta": "PON 1/3 · VINA DEL REY"},
    )
    assert r["labor"] == clf.TRABAJOS
    assert r["fuente"] == clf.POR_FALLA_AGRUPADA
    assert "8 clientes" in r["porque"]
    assert "VINA DEL REY" in r["porque"]


def test_i_un_solo_afectado_NO_es_una_falla_agrupada():
    """Con uno solo no hay nada que agrupar: sigue siendo su correctivo."""
    r = clf.clasificar(
        {"contexto_disponible": True,
         "equipo": {"estado": "caido", "causa_caida": "fibra"}},
        situacion={"afectados": 1, "etiqueta": "PON 1/3"},
    )
    assert r["labor"] == clf.CORRECTIVO
    assert r["fuente"] == clf.POR_PRUEBA


# ---------------------------------------------------------------------------
# C · la instalación, que no se prueba
# ---------------------------------------------------------------------------

def test_j_el_cliente_ficticio_del_proveedor_es_el_discriminador_fuerte():
    """Medido el 08/10/2026: 220 de 220, contra 23 de 220 por el asunto.

    Los tickets de instalación cuelgan de un cliente ficticio del proveedor
    («INSTALACIONES NUEVAS»). Gana incluso sobre un diagnóstico de fibra: una
    instalación no tiene ONT, así que lo que SmartOLT diga de ese id no habla
    de este trabajo.
    """
    r = clf.clasificar(
        {"contexto_disponible": True, "servicio": "3545",
         "equipo": {"estado": "caido", "causa_caida": "fibra"}},
        marcadores={"id_servicio_instalaciones": "3545"},
    )
    assert r["labor"] == clf.INSTALACION
    assert r["fuente"] == clf.POR_PROVEEDOR


def test_j2_el_id_del_cliente_ficticio_NO_esta_fijo_en_el_codigo():
    """Varía por empresa: vive en `WISPHUB_ID_SERVICIO_INSTALACIONES`.

    Con otro id, el MISMO caso deja de ser una instalación. Si el valor
    estuviera fijo acá, el segundo ISP clasificaría mal en silencio.
    """
    r = clf.clasificar(
        {"contexto_disponible": True, "servicio": "3545",
         "equipo": {"estado": "caido", "causa_caida": "fibra"}},
        marcadores={"id_servicio_instalaciones": "9999"},
    )
    assert r["labor"] == clf.CORRECTIVO


def test_j3_tambien_sirve_estar_en_el_padron_de_instalaciones():
    """La segunda vía medida: existe en `/api/instalaciones/` y no en clientes.

    Es una prueba POSITIVA —aparece en un lado y no en el otro—, a diferencia
    de «no aparece en SmartOLT», que no prueba nada.
    """
    r = clf.clasificar(
        {"contexto_disponible": True, "servicio": "7764"},
        marcadores={"en_padron_de_instalaciones": True,
                    "estado_instalacion": 1},
    )
    assert r["labor"] == clf.INSTALACION
    assert "padron de instalaciones" in r["porque"]
    assert "estado 1" in r["porque"]


def test_k_un_marcador_VACIO_no_es_que_no_sea_instalacion():
    """«No se pudo preguntar» y «no es» son cosas distintas.

    El atajo descartado con número: 1.299 de 4.163 clientes ACTIVOS tampoco
    tienen `sn_onu`, así que una ausencia no prueba nada. Lo mismo acá: un
    `None` es que la consulta no respondió, no que el cliente sea normal.
    """
    for vacio in ({}, {"en_padron_de_instalaciones": None},
                  {"id_servicio_instalaciones": ""},
                  {"en_padron_de_instalaciones": False}):
        r = clf.clasificar(
            {"contexto_disponible": True, "servicio": "7763",
             "equipo": {"estado": "caido", "causa_caida": "fibra"}},
            marcadores=vacio,
        )
        #  Sigue de largo hasta la prueba, en vez de afirmar que NO es
        #  instalación.
        assert r["labor"] == clf.CORRECTIVO, vacio


# ---------------------------------------------------------------------------
# D · el texto, y su marca
# ---------------------------------------------------------------------------

MAPA = {
    "instalacion": clf.INSTALACION,
    "instalacion de camara": clf.TRABAJOS,
    "cambio de poste": clf.TRABAJOS,
}


def test_l_el_texto_solo_entra_cuando_nada_mas_concluyo():
    r = clf.clasificar(
        {"contexto_disponible": True,
         "equipo": {"estado": "en_linea", "senal": "buena"}},
        texto="Solicitud de cambio de poste en la esquina",
        mapa_de_texto=MAPA,
    )
    assert r["labor"] == clf.TRABAJOS
    assert r["fuente"] == clf.POR_TEXTO


def test_m_lo_que_sale_del_texto_queda_MARCADO_como_no_verificado():
    """El técnico tiene que poder saberlo antes de cargar el kit."""
    r = clf.clasificar(
        {"contexto_disponible": True},
        texto="cambio de poste", mapa_de_texto=MAPA,
    )
    assert r["verificada"] is False
    assert "NO esta verificado" in r["porque"]


def test_n_la_PRUEBA_le_gana_al_texto():
    """El ticket dice una cosa y el equipo dice otra: manda lo medido."""
    r = clf.clasificar(
        {"contexto_disponible": True,
         "equipo": {"estado": "caido", "causa_caida": "fibra"}},
        texto="instalacion", mapa_de_texto=MAPA,
    )
    assert r["labor"] == clf.CORRECTIVO
    assert r["fuente"] == clf.POR_PRUEBA


def test_o_entre_dos_patrones_gana_el_MAS_ESPECIFICO():
    """El orden de un dict no puede decidir esto.

    'instalacion' y 'instalacion de camara' mapean a labores distintas, y la
    específica tiene que ganarle a la genérica.
    """
    r = clf.clasificar({"contexto_disponible": True},
                       texto="INSTALACION DE CAMARA en el parque",
                       mapa_de_texto=MAPA)
    assert r["labor"] == clf.TRABAJOS

    r2 = clf.clasificar({"contexto_disponible": True},
                        texto="instalacion nueva cliente", mapa_de_texto=MAPA)
    assert r2["labor"] == clf.INSTALACION


def test_p_sin_mapa_declarado_el_texto_no_dice_nada():
    """Ningún texto dice por sí solo a qué labor corresponde.

    'soporte' en una empresa puede ser lo que en otra es 'mantenimiento'.
    """
    r = clf.clasificar({"contexto_disponible": True},
                       texto="cambio de poste", mapa_de_texto=None)
    assert r["labor"] == clf.SIN_CONCLUIR


# ---------------------------------------------------------------------------
# E · no concluir, diciendo por qué
# ---------------------------------------------------------------------------

def test_q_sin_ficha_tecnica_lo_dice_en_vez_de_callarse():
    r = clf.clasificar({"contexto_disponible": False,
                        "motivo": "motor_no_responde"})
    assert r["labor"] == clf.SIN_CONCLUIR
    assert "no se pudo traer la ficha" in r["porque"]


def test_r_equipo_no_disponible_es_distinto_de_equipo_sano():
    """«No se pudo medir» y «se midió y está bien» no son lo mismo."""
    r = clf.clasificar({"contexto_disponible": True,
                        "equipo_no_disponible": "sin sn_onu en el proveedor"})
    assert r["labor"] == clf.SIN_CONCLUIR
    assert "no se pudo leer el equipo" in r["porque"]
    assert "sin sn_onu" in r["porque"]


def test_s_siempre_devuelve_la_misma_forma():
    """Quien lo use no tiene que distinguir «sin respuesta» de «respuesta vacía»."""
    for entrada in ({}, None, {"contexto_disponible": True}, "no es un dict"):
        r = clf.clasificar(entrada)
        assert set(r) == {"labor", "porque", "fuente", "verificada"}
        assert isinstance(r["porque"], str) and r["porque"]


def test_t_nunca_devuelve_una_labor_sin_su_porque():
    """Una clasificación sin evidencia no se puede discutir."""
    casos = [
        ({"contexto_disponible": True,
          "equipo": {"estado": "caido", "causa_caida": "fibra"}}, {}),
        ({"contexto_disponible": True}, {"situacion": {"afectados": 3}}),
        ({"contexto_disponible": True},
         {"marcadores": {"en_padron_de_instalaciones": True}}),
        ({"contexto_disponible": True},
         {"texto": "cambio de poste", "mapa_de_texto": MAPA}),
    ]
    for contexto, extra in casos:
        r = clf.clasificar(contexto, **extra)
        assert r["labor"], (contexto, extra)
        assert len(r["porque"]) > 20, r
        assert r["fuente"], r


# ---------------------------------------------------------------------------
# F · el enganche: que esto CORRA al crear una orden, no solo que exista
# ---------------------------------------------------------------------------
#
# «Codigo construido no es codigo que corre» (CLAUDE.md §6). El reloj de
# tareas colgaba de un bloque que gunicorn nunca ejecuta y la reconciliacion
# estaba probada y sin llamador: ninguno dio error, log ni alerta. Estas dos
# pruebas verifican que la clasificacion queda ESCRITA en la orden por el
# camino real, no que la funcion devuelva algo cuando se la llama a mano.

def test_u_la_clasificacion_queda_escrita_en_el_contexto_de_la_orden():
    """Se congela con la orden, que es donde se puede leer despues."""
    from campo.services.despacho import depurar_contexto

    crudo = {
        "identidad": {"servicio": "6580", "origen": "caso"},
        "cliente": {"nombre": "Alguien", "localidad": "MARTHA GISELA"},
        "equipo": {"estado": "caido", "causa_caida": "fibra"},
    }
    snapshot = depurar_contexto(crudo)
    r = clf.clasificar(snapshot)

    assert r["labor"] == clf.CORRECTIVO
    assert r["verificada"] is True
    #  Y el snapshot lleva la hora: sin ella una medicion congelada pasa a ser
    #  una afirmacion sobre el presente que nadie puede verificar.
    assert snapshot["capturado_en"]


def test_v_el_marcador_de_instalaciones_SOBREVIVE_al_depurado():
    """El motor lo manda y el snapshot tiene que conservarlo.

    Si `depurar_contexto` lo tirara --como tiraba la conversacion hasta el
    25/09/2026-- la clasificacion nunca podria ver una instalacion, y el
    sintoma seria que todas caen en correctivo sin que nada avise.
    """
    from campo.services.despacho import depurar_contexto

    snapshot = depurar_contexto({
        "identidad": {"servicio": "3545", "origen": "caso"},
        "cliente": {"nombre": "Prospecto"},
        "id_servicio_instalaciones": "3545",
    })
    assert snapshot.get("id_servicio_instalaciones") == "3545"

    r = clf.clasificar(snapshot, marcadores={
        "id_servicio_instalaciones": snapshot["id_servicio_instalaciones"]})
    assert r["labor"] == clf.INSTALACION


def test_w_sin_ficha_NO_se_agrega_la_sugerencia():
    """Un contexto que ya dice «no se pudo traer la ficha» no lleva otra clave
    diciendo lo mismo.

    Se rompio al enganchar el clasificador: se agregaba `labor_sugerida` a
    TODA orden, y `test_la_ficha_no_rompe_la_creacion` --que exige que ese
    contexto tenga exactamente cinco claves-- lo cazo. La prueba tenia razon:
    sin ficha no hay nada que clasificar, y repetir la ausencia en otra clave
    es ruido en algo que se congela y queda guardado.
    """
    from campo.services.despacho import sin_contexto

    vacio = sin_contexto("ConnectTimeout", motor_alcanzado=False)
    #  La clasificacion sobre ese contexto NO concluye, y dice por que: eso
    #  esta bien. Lo que no debe pasar es que se guarde en la orden.
    r = clf.clasificar(vacio)
    assert r["labor"] == clf.SIN_CONCLUIR
    assert "no se pudo traer la ficha" in r["porque"]
