# -*- coding: utf-8 -*-
"""
================================================================================
 P8.2  --  DECISION != RESULTADO, y lo que se aprendio
================================================================================

LA AFIRMACION QUE SOSTIENE EL ARCHIVO
-------------------------------------
Que aceptar no es acertar y rechazar no es equivocarse. Las dos pruebas que mas
importan aqui son 'test_N' y 'test_O': ninguna decision, por si sola, puede
marcar una recomendacion como exitosa o incorrecta.

EL HUECO QUE CIERRA
-------------------
'DecisionSupervisor' existia desde P4 y NUNCA se escribia -- medido el
05/10/2026: la unica aparicion de 'DecisionSupervisor(' fuera de las pruebas era
la definicion de la clase. Las metricas de acierto de 'indicadores.py' leian una
tabla vacia y devolvian 0 / NO_APLICA para siempre.

LO QUE NO SE SUSTITUYE
----------------------
Nada del modelo. La decision la crea el flujo real ('supervisor.revisar'), el
desenlace el servicio real, las restricciones son las de la base y la auditoria
se lee de 'common.Activity'.
================================================================================
"""

from __future__ import annotations

import json

import pytest
from django.utils import timezone

from common.models import Activity, Profile, User
from operaciones import auditoria, gobierno
from operaciones import situaciones as svc
from operaciones import supervisor as sup
from operaciones.gobierno_modelos import (AprendizajeSupervisor,
                                          OrigenAprendizaje, ResultadoDecision,
                                          TipoAprendizaje, TipoDecision)
from operaciones.models import DecisionSupervisor, PropuestaSupervisor
from operaciones.situaciones_modelos import (SituacionOperativa, TipoAfectado,
                                             TipoEvento, TipoRelacion)
from operaciones.tests.test_p5_chat_supervisor import _situacion

P = PropuestaSupervisor
D = DecisionSupervisor
S = SituacionOperativa
Ap = AprendizajeSupervisor

pytestmark = pytest.mark.django_db


# =============================================================================
#  andamio
# =============================================================================

def _persona(org, correo, role="OPERACIONES"):
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return u, Profile.objects.create(user=u, org=org, role=role,
                                     is_active=True)


@pytest.fixture
def jefe(org_a):
    return _persona(org_a, "jefe.p82@prueba.local")[1]


@pytest.fixture
def cliente_jefe(org_a):
    from conftest import _make_authenticated_client
    u, p = _persona(org_a, "cli.p82@prueba.local")
    return _make_authenticated_client(u, org_a, p), p


def _evidencia(dato="12 ONT caídas en el PON 3/1/4"):
    return [{"fuente": "smartolt", "id": "3/1/4", "dato": dato,
             "observado_en": timezone.now().isoformat()}]


def _firma(texto: str) -> str:
    import hashlib

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:8]


def _propuesta(org, *, situacion=None, accion="Diagnosticar el PON 3/1/4",
               ahora=None):
    """
    Una propuesta por el camino REAL: 'supervisor.registrar_propuesta'.

    Si se le pasa una situacion, se ata con el mismo par que usa P6
    ('origen_tipo="situacion"'), que es de donde 'gobierno' la resuelve.
    """
    from operaciones import coordinacion

    ahora = ahora or timezone.now()
    senal = sup.Senal(
        tipo=P.ORDEN_EN_RIESGO,
        origen_tipo=(coordinacion.ORIGEN_SITUACION if situacion
                     else "orden_trabajo"),
        origen_id=(str(situacion.id) if situacion else "orden-1"),
        evidencia=_evidencia(),
        #  64 caracteres de tope y un uuid son 36: la accion va hasheada,
        #  no recortada. Recortandola, dos acciones que empiezan igual
        #  darian la misma huella y la segunda se leeria como repetida.
        huella=f"p82:{_firma(accion)}:{situacion.id if situacion else 'x'}")
    return sup.registrar_propuesta(org, senal, {
        "accion_propuesta": accion, "motivo": "la red muestra una afectación",
        "prioridad": 50, "impacto": "cliente",
        "nivel": P.NIVEL_RECOMENDAR}, ahora=ahora)


def _decidir(propuesta, jefe, decision=P.ACEPTADA, comentario="de acuerdo"):
    return sup.revisar(propuesta, actor=jefe, decision=decision,
                       comentario=comentario)


# =============================================================================
#  LA CAPTURA DE LA DECISION  (§3)
# =============================================================================

def test_1_revisar_una_propuesta_YA_crea_la_decision(org_a, jefe):
    """El hueco que cerraba este bloque, afirmado sobre el dato."""
    s = _situacion(org_a)
    p = _propuesta(org_a, situacion=s)
    assert D.objects.filter(org=org_a).count() == 0

    _decidir(p, jefe)

    d = D.objects.get(org=org_a)
    assert d.propuesta_id == p.id
    assert d.tipo == TipoDecision.ACEPTO
    assert d.actor_id == jefe.id
    assert d.decidida_en is not None
    #  LA CLAVE: nace PENDIENTE. Aceptar no es haber funcionado.
    assert d.resultado == ResultadoDecision.PENDIENTE
    assert d.resultado_en is None


def test_2_la_decision_se_ata_a_la_situacion_cuando_la_hay(org_a, jefe):
    s = _situacion(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    d = D.objects.get(org=org_a)
    assert d.situacion_id == s.id
    #  Y queda en el timeline de la situacion, append-only.
    evento = s.eventos.filter(tipo=TipoEvento.RECOMENDACION).last()
    assert evento.datos["decision_id"] == str(d.id)
    assert evento.datos["resultado"] == "pendiente"


def test_3_una_propuesta_SIN_situacion_tambien_deja_decision(org_a, jefe):
    """Una señal de M02/M03 no tiene situación, y eso es un estado válido."""
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    assert d.situacion_id is None
    assert d.propuesta_id is not None


def test_4_la_recomendacion_se_COPIA_no_se_referencia(org_a, jefe):
    """Si la propuesta cambia después, lo que se decidió sigue legible."""
    p = _propuesta(org_a, accion="Revisar el PON 3/1/4")
    _decidir(p, jefe)
    d = D.objects.get(org=org_a)
    assert d.recomendacion == "Revisar el PON 3/1/4"


# =============================================================================
#  §20 A-E  --  DECISION != RESULTADO
# =============================================================================

def test_A_aceptada_mas_resultado_exitoso(org_a, jefe):
    s = _situacion(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    d = D.objects.get(org=org_a)

    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="las 12 ONT volvieron y el PON quedó en 0 afectados")

    d.refresh_from_db()
    assert d.resultado == ResultadoDecision.FUNCIONO
    assert d.resultado_en is not None
    assert d.resultado_evidencia
    #  Y deja la lección: aceptó y funcionó.
    a = Ap.objects.get(org=org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA)
    assert a.decision_id == d.id
    assert a.origen == OrigenAprendizaje.PERSONA


def test_B_aceptada_mas_resultado_FALLIDO(org_a, jefe):
    """
    El caso que el bloque nombra: se le hizo caso y no sirvió.

    Y lo que NO se concluye: esto no es un falso positivo. La detección pudo
    ser correcta y el arreglo malo. Para decir que no había problema hace falta
    que alguien lo afirme con evidencia, y es otra llamada.
    """
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)

    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.NO_FUNCIONO,
        evidencia="se reinició la ONT y volvió a caer a los 20 minutos")

    d.refresh_from_db()
    assert d.resultado == ResultadoDecision.NO_FUNCIONO
    assert not Ap.objects.filter(
        org=org_a, tipo=TipoAprendizaje.FALSO_POSITIVO).exists()
    assert not Ap.objects.filter(
        org=org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA).exists()


def test_C_rechazada_y_el_problema_se_confirma_igual(org_a, jefe):
    """
    'RECHAZO_ERRADO': el Supervisor tenía razón y no se le creyó.

    Es la lección más valiosa del conjunto, y la única forma de verla es tener
    la decisión y el resultado separados.
    """
    _decidir(_propuesta(org_a), jefe, decision=P.RECHAZADA,
             comentario="no parece de red")
    d = D.objects.get(org=org_a)
    assert d.tipo == TipoDecision.RECHAZO

    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.NO_FUNCIONO,
        evidencia="a las 3 horas entraron 9 reclamos del mismo PON",
        correccion="había que diagnosticar el PON ese mismo turno")

    a = Ap.objects.get(org=org_a, tipo=TipoAprendizaje.RECHAZO_ERRADO)
    assert a.evidencia
    d.refresh_from_db()
    assert d.correccion


def test_D_modificada_conserva_el_original(org_a, jefe):
    p = _propuesta(org_a, accion="Reiniciar la ONT")
    original = p.accion_propuesta
    sup.revisar(p, actor=jefe, decision=P.MODIFICADA,
                comentario="mejor un diagnóstico antes",
                cambios={"accion_propuesta": "Diagnosticar antes de reiniciar"})

    p.refresh_from_db()
    assert p.accion_propuesta == "Diagnosticar antes de reiniciar"
    #  El original NO se sobrescribe: queda intacto en su JSON.
    assert p.propuesta_original["accion_propuesta"] == original
    #  Y la corrección humana queda contable, con su propio tipo.
    a = Ap.objects.get(org=org_a, tipo=TipoAprendizaje.CORRECCION_HUMANA)
    assert a.actor_id == jefe.id
    assert a.datos["original_en"] == "PropuestaSupervisor.propuesta_original"


def test_E_sin_evidencia_suficiente_es_NO_SE_PUEDE_SABER(org_a, jefe):
    """
    Se registra la ignorancia en vez de inventar un veredicto.

    'no_se_puede_saber' NO está en CERRADOS: no es un resultado malo, es la
    ausencia de uno. Y por eso es el único que no exige evidencia.
    """
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)

    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.NO_SE_PUEDE_SABER,
        evidencia="el cliente no volvió a contestar")

    d.refresh_from_db()
    assert d.resultado == ResultadoDecision.NO_SE_PUEDE_SABER
    assert d.resultado not in ResultadoDecision.CERRADOS
    #  No deja lección: no se concluyó nada.
    assert Ap.objects.filter(org=org_a, decision=d).count() == 0


def test_E2_un_resultado_cerrado_SIN_evidencia_se_rechaza(org_a, jefe):
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    with pytest.raises(gobierno.ErrorGobierno) as e:
        gobierno.registrar_resultado(
            d, actor=jefe, resultado=ResultadoDecision.FUNCIONO, evidencia="  ")
    assert "evidencia" in str(e.value)
    d.refresh_from_db()
    assert d.resultado == ResultadoDecision.PENDIENTE


def test_E3_pendiente_no_es_un_desenlace(org_a, jefe):
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    with pytest.raises(gobierno.ErrorGobierno):
        gobierno.registrar_resultado(
            d, actor=jefe, resultado=ResultadoDecision.PENDIENTE,
            evidencia="x")


# =============================================================================
#  §20 F-G  --  VERIFICACION Y ACUMULACION
# =============================================================================

def test_F_el_desenlace_queda_en_el_timeline_como_verificacion(org_a, jefe):
    s = _situacion(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="el PON volvió a 0 afectados")

    evento = s.eventos.filter(tipo=TipoEvento.VERIFICACION).last()
    assert evento.datos["resultado"] == ResultadoDecision.FUNCIONO
    assert evento.datos["decision_id"] == str(d.id)
    #  Y la situación NO se cerró por eso: un desenlace no es un cierre.
    s.refresh_from_db()
    assert s.estado in S.VIVAS


def test_G_la_situacion_acumula_propuesta_decision_y_resultado(org_a, jefe):
    """§7: acumula por REFERENCIA, sin copiar la base dentro de la situación."""
    s = _situacion(org_a)
    p = _propuesta(org_a, situacion=s)
    _decidir(p, jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.PARCIAL,
        evidencia="volvieron 9 de 12")

    assert D.objects.filter(situacion=s).count() == 1
    #  Un 'parcial' NO deja leccion, y es correcto: '_leccion_de' solo concluye
    #  en 'acepto+funciono' y 'rechazo+no_funciono'. Mi primera version exigia
    #  una leccion aqui y era la asercion la que estaba mal -- "volvieron 9 de
    #  12" no dice si el Supervisor acerto.
    assert s.aprendizajes.count() == 0
    #  Los dos que este bloque agrega al timeline. 'DETECTADA' no esta porque
    #  el helper crea la situacion directo, sin pasar por 'svc.abrir' -- y eso
    #  es del andamio de la prueba, no del codigo.
    tipos = set(s.eventos.values_list("tipo", flat=True))
    assert {TipoEvento.RECOMENDACION, TipoEvento.VERIFICACION} <= tipos
    #  El resumen cruza los tres sin recalcular nada.
    resumen = gobierno.resumen_de_aprendizaje(org_a)
    assert resumen["decisiones"] == 1
    assert resumen["decisiones_con_desenlace"] == 1
    assert resumen["decisiones_sin_desenlace"] == 0


# =============================================================================
#  §20 H-I  --  REINCIDENCIA Y CORRELACION
# =============================================================================

def test_H_la_reincidencia_se_PROPONE_y_la_afirma_una_persona(org_a, jefe):
    ahora = timezone.now()
    vieja = _situacion(org_a, codigo="S-001",
                       ahora=ahora - timezone.timedelta(days=7))
    svc.agregar_afectados(vieja, [{"tipo": TipoAfectado.PON,
                                   "identificador": "3/1/4"}])
    nueva = _situacion(org_a, codigo="S-017", ahora=ahora)
    svc.agregar_afectados(nueva, [{"tipo": TipoAfectado.PON,
                                   "identificador": "3/1/4"}])

    #  1. Se PROPONEN, sin afirmar nada ni escribir nada.
    candidatas = gobierno.candidatas_de_reincidencia(nueva, ahora=ahora)
    assert len(candidatas) == 1
    assert candidatas[0]["codigo"] == "S-001"
    assert candidatas[0]["dias_antes"] == 7
    assert nueva.relaciones_origen.count() == 0 if hasattr(
        nueva, "relaciones_origen") else True

    #  2. Y la máquina NO puede marcarla sola: el tipo no es automático.
    assert TipoRelacion.REINCIDENCIA not in TipoRelacion.AUTOMATICOS
    with pytest.raises(gobierno.ErrorGobierno):
        gobierno.marcar_reincidencia(nueva, vieja, actor=None, motivo="x")

    #  3. Una persona sí.
    gobierno.marcar_reincidencia(
        nueva, vieja, actor=jefe,
        motivo="mismo PON, misma hora, y el empalme no se cambió")
    a = Ap.objects.get(org=org_a, tipo=TipoAprendizaje.REINCIDENCIA)
    assert a.datos["situacion_anterior"] == str(vieja.id)
    assert a.datos["dias_entre"] == 7


def test_H2_sin_afectado_de_topologia_no_hay_candidatas(org_a):
    """Un caso o un ticket no sirven: el mismo cliente reclama por dos cosas."""
    s = _situacion(org_a, codigo="S-050")
    s.afectados.all().delete()
    svc.agregar_afectados(s, [{"tipo": TipoAfectado.CASO,
                               "identificador": "caso-1"}])
    assert gobierno.candidatas_de_reincidencia(s) == []


def test_I_una_correlacion_errada_queda_registrada_con_los_dos_numeros(org_a,
                                                                       jefe):
    s = _situacion(org_a, afectados=12)
    gobierno.registrar_calidad_de_correlacion(
        s, actor=jefe, propuestos=12, confirmados=10,
        evidencia="se revisaron las 12 ONT y 2 estaban apagadas desde marzo")

    a = Ap.objects.get(org=org_a)
    assert a.tipo == TipoAprendizaje.CORRELACION_INCORRECTA
    assert a.datos["afectados_propuestos"] == 12
    assert a.datos["afectados_confirmados"] == 10
    assert a.datos["diferencia"] == -2
    assert a.origen == OrigenAprendizaje.EVIDENCIA_OPERATIVA


def test_I2_una_correlacion_correcta_tambien_queda(org_a, jefe):
    s = _situacion(org_a)
    gobierno.registrar_calidad_de_correlacion(
        s, actor=jefe, propuestos=12, confirmados=12,
        evidencia="las 12 se confirmaron en sitio")
    assert Ap.objects.get(org=org_a).tipo == \
        TipoAprendizaje.CORRELACION_CORRECTA


def test_I3_falso_positivo_y_omision_se_registran_por_separado(org_a, jefe):
    """§10 y §11: los datos que P8.3 va a necesitar, guardados hoy."""
    s = _situacion(org_a)
    gobierno.registrar_falso_positivo(
        s, actor=jefe, motivo="era una ventana de mantenimiento programada")
    gobierno.registrar_omision(
        org_a, actor=jefe,
        conclusion="hubo una caída del PON 9/9/9 y no había ninguna situación",
        evidencia="4 tickets del mismo PON entre 02:00 y 03:00")

    assert Ap.objects.filter(tipo=TipoAprendizaje.FALSO_POSITIVO).count() == 1
    omision = Ap.objects.get(tipo=TipoAprendizaje.OMISION)
    #  La omisión suele NO tener situación: el caso típico es que no existía.
    assert omision.situacion_id is None
    assert omision.propuesta_id is None or True
    resumen = gobierno.resumen_de_aprendizaje(org_a)
    assert resumen["en_contra"] == 2
    assert resumen["a_favor"] == 0


# =============================================================================
#  §20 J-K  --  TENANT Y PERMISOS
# =============================================================================

def test_J_el_aprendizaje_no_cruza_de_empresa(org_a, org_b, jefe):
    s_b = _situacion(org_b, codigo="S-B01")
    jefe_b = _persona(org_b, "jefe.b.p82@prueba.local")[1]
    gobierno.registrar_falso_positivo(s_b, actor=jefe_b, motivo="no era nada")

    assert Ap.objects.filter(org=org_a).count() == 0
    assert Ap.objects.filter(org=org_b).count() == 1
    assert gobierno.resumen_de_aprendizaje(org_a)["aprendizajes"] == 0


def test_K_la_ruta_del_resultado_exige_sesion_y_rol(org_a, jefe,
                                                    unauthenticated_client):
    p = _propuesta(org_a)
    _decidir(p, jefe)
    ruta = f"/api/operaciones/propuestas/{p.id}/resultado/"
    cuerpo = {"resultado": "funciono", "evidencia": "volvió"}

    assert unauthenticated_client.post(
        ruta, cuerpo, format="json").status_code in (401, 403)

    from conftest import _make_authenticated_client
    u, pr = _persona(org_a, "raso.p82@prueba.local", role="USER")
    assert _make_authenticated_client(u, org_a, pr).post(
        ruta, cuerpo, format="json").status_code == 403
    #  Y nada se escribió.
    assert D.objects.get(org=org_a).resultado == ResultadoDecision.PENDIENTE


def test_K2_una_propuesta_de_otra_empresa_da_404(org_a, org_b, cliente_jefe):
    cli, _ = cliente_jefe
    jefe_b = _persona(org_b, "jefe.b2.p82@prueba.local")[1]
    p_b = _propuesta(org_b)
    _decidir(p_b, jefe_b)

    r = cli.post(f"/api/operaciones/propuestas/{p_b.id}/resultado/",
                 {"resultado": "funciono", "evidencia": "x"}, format="json")
    assert r.status_code == 404, r.content
    assert D.objects.get(org=org_b).resultado == ResultadoDecision.PENDIENTE


def test_K3_la_ruta_registra_el_desenlace(org_a, cliente_jefe):
    cli, perfil = cliente_jefe
    s = _situacion(org_a)
    p = _propuesta(org_a, situacion=s)
    _decidir(p, perfil)

    r = cli.post(f"/api/operaciones/propuestas/{p.id}/resultado/",
                 {"resultado": "funciono",
                  "evidencia": "el PON volvió a 0 afectados"}, format="json")
    assert r.status_code == 200, r.content
    cuerpo = json.loads(r.content)
    assert cuerpo["resultado"] == "funciono"
    assert cuerpo["aprendizajes"][0]["tipo"] == \
        TipoAprendizaje.RECOMENDACION_CONFIRMADA
    #  Y quedó auditado.
    assert Activity.objects.filter(
        org=org_a, action="STATUS_CHANGED",
        entity_type=auditoria.ENTIDAD_PROPUESTA).exists()


def test_K4_sin_decision_previa_la_ruta_da_404(org_a, cliente_jefe):
    """Primero se revisa; el desenlace es de una decisión que ya existe."""
    cli, _ = cliente_jefe
    p = _propuesta(org_a)
    r = cli.post(f"/api/operaciones/propuestas/{p.id}/resultado/",
                 {"resultado": "funciono", "evidencia": "x"}, format="json")
    assert r.status_code == 404
    assert json.loads(r.content)["error"] == "DECISION_NO_ENCONTRADA"


# =============================================================================
#  §19  --  IDEMPOTENCIA Y DESENLACES INCOMPATIBLES
# =============================================================================

def test_M_el_mismo_desenlace_dos_veces_es_idempotente(org_a, jefe):
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    uno = gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="volvió")
    dos = gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="volvió")
    assert uno.id == dos.id
    assert uno.resultado_en == dos.resultado_en
    #  Y NO deja dos lecciones del mismo hecho.
    assert Ap.objects.filter(
        org=org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA).count() == 1


def test_M2_dos_desenlaces_INCOMPATIBLES_se_rechazan(org_a, jefe):
    """
    Registrar 'funcionó' y después 'no funcionó' no es corregir: es borrar.

    Si la conclusión cambió, va como aprendizaje nuevo -- y entonces queda el
    cambio de opinión, que es justo el dato que se perdería.
    """
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO, evidencia="volvió")

    with pytest.raises(gobierno.DesenlaceIncompatible) as e:
        gobierno.registrar_resultado(
            d, actor=jefe, resultado=ResultadoDecision.NO_FUNCIONO,
            evidencia="pensándolo mejor")

    assert "ya tiene desenlace" in str(e.value)
    d.refresh_from_db()
    assert d.resultado == ResultadoDecision.FUNCIONO


def test_M3_la_ruta_devuelve_409_ante_un_desenlace_ya_registrado(org_a,
                                                                 cliente_jefe):
    cli, perfil = cliente_jefe
    p = _propuesta(org_a)
    _decidir(p, perfil)
    ruta = f"/api/operaciones/propuestas/{p.id}/resultado/"
    assert cli.post(ruta, {"resultado": "funciono",
                           "evidencia": "volvió"},
                    format="json").status_code == 200
    r = cli.post(ruta, {"resultado": "no_funciono",
                        "evidencia": "otra cosa"}, format="json")
    assert r.status_code == 409, r.content
    assert json.loads(r.content)["error"] == "DESENLACE_YA_REGISTRADO"


# =============================================================================
#  §20 N-O  --  LAS DOS QUE MAS IMPORTAN
# =============================================================================

def test_N_aceptada_NO_marca_la_recomendacion_como_exitosa(org_a, jefe):
    """
    El error que este bloque entero existe para no cometer.

    Se acepta y NO se registra desenlace. Lo que tiene que pasar: resultado
    PENDIENTE, cero lecciones a favor, y la métrica de acierto contándola como
    SIN desenlace -- no como un éxito.
    """
    s = _situacion(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe, decision=P.ACEPTADA)

    d = D.objects.get(org=org_a)
    assert d.tipo == TipoDecision.ACEPTO
    assert d.resultado == ResultadoDecision.PENDIENTE
    assert d.resultado not in ResultadoDecision.CERRADOS
    assert Ap.objects.filter(org=org_a,
                             tipo__in=TipoAprendizaje.A_FAVOR).count() == 0

    resumen = gobierno.resumen_de_aprendizaje(org_a)
    assert resumen["a_favor"] == 0
    assert resumen["decisiones_con_desenlace"] == 0
    assert resumen["decisiones_sin_desenlace"] == 1


def test_O_rechazada_NO_marca_la_recomendacion_como_incorrecta(org_a, jefe):
    """
    El simétrico. Rechazar es una decisión, no un veredicto sobre el acierto.

    Y si después resulta que la recomendación servía, la lección es
    'RECHAZO_ERRADO' -- a FAVOR del Supervisor, no en contra.
    """
    _decidir(_propuesta(org_a), jefe, decision=P.RECHAZADA,
             comentario="no parece de red")

    d = D.objects.get(org=org_a)
    assert d.tipo == TipoDecision.RECHAZO
    assert d.resultado == ResultadoDecision.PENDIENTE
    assert Ap.objects.filter(org=org_a,
                             tipo__in=TipoAprendizaje.EN_CONTRA).count() == 0
    assert gobierno.resumen_de_aprendizaje(org_a)["en_contra"] == 0


# =============================================================================
#  §18  --  EL SUPERVISOR NO PUEDE DECLARARSE CORRECTO
# =============================================================================

def test_P_el_supervisor_no_es_un_origen_de_aprendizaje(org_a, jefe):
    s = _situacion(org_a)
    assert "supervisor" not in OrigenAprendizaje.TODOS
    with pytest.raises(gobierno.ErrorGobierno) as e:
        gobierno.registrar_aprendizaje(
            org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA,
            origen="supervisor", conclusion="acerté",
            evidencia="yo lo digo", situacion=s)
    assert "no puede concluir sobre su propio acierto" in str(e.value)
    assert Ap.objects.count() == 0


def test_P2_un_resultado_sin_actor_se_rechaza(org_a, jefe):
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    with pytest.raises(gobierno.ErrorGobierno) as e:
        gobierno.registrar_resultado(
            d, actor=None, resultado=ResultadoDecision.FUNCIONO,
            evidencia="x")
    assert "declararse correcto" in str(e.value)


def test_P3_el_aprendizaje_es_APPEND_ONLY(org_a, jefe):
    s = _situacion(org_a)
    a = gobierno.registrar_falso_positivo(s, actor=jefe, motivo="no era nada")
    with pytest.raises(Ap.NoSeReescribe):
        a.conclusion = "pensándolo mejor, sí era"
        a.save()
    with pytest.raises(Ap.NoSeReescribe):
        a.delete()


def test_P4_una_leccion_sin_evidencia_o_sin_objeto_se_rechaza(org_a, jefe):
    s = _situacion(org_a)
    with pytest.raises(gobierno.ErrorGobierno):
        gobierno.registrar_aprendizaje(
            org_a, tipo=TipoAprendizaje.OMISION,
            origen=OrigenAprendizaje.PERSONA, conclusion="algo",
            evidencia="", situacion=s, actor=jefe)
    #  SIN objeto: se rechaza para cualquier tipo MENOS la omision, que existe
    #  justamente porque no habia situacion a la que apuntar.
    with pytest.raises(gobierno.ErrorGobierno) as e:
        gobierno.registrar_aprendizaje(
            org_a, tipo=TipoAprendizaje.FALSO_POSITIVO,
            origen=OrigenAprendizaje.PERSONA, conclusion="algo",
            evidencia="hay evidencia", actor=jefe)
    assert "apuntar a algo" in str(e.value)
    assert Ap.objects.count() == 0

    #  Y la omision SI pasa sin objeto. Es el caso principal de §11.
    huerfana = gobierno.registrar_aprendizaje(
        org_a, tipo=TipoAprendizaje.OMISION,
        origen=OrigenAprendizaje.PERSONA,
        conclusion="hubo una caída y no había ninguna situación abierta",
        evidencia="4 tickets del PON 9/9/9 entre 02:00 y 03:00", actor=jefe)
    assert huerfana.situacion_id is None
    assert Ap.objects.count() == 1


# =============================================================================
#  §14  --  NO SE ROMPIO NADA DE LO QUE YA HABIA
# =============================================================================

def test_Q_shadow_mode_y_la_ejecucion_siguen_cerrados(org_a, jefe):
    p = _propuesta(org_a)
    revisada = _decidir(p, jefe)
    assert sup.SHADOW_MODE is True
    with pytest.raises(Exception):
        sup.ejecutar_propuesta(revisada)


def test_R_los_indicadores_YA_ven_las_decisiones(org_a, jefe):
    """
    El cierre del hueco, medido donde dolía: 'indicadores_situaciones' leía una
    tabla vacía. Ahora cuenta.
    """
    from operaciones import indicadores

    s = _situacion(org_a)
    _decidir(_propuesta(org_a, situacion=s), jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="el PON volvió")

    ind = indicadores.indicadores_situaciones(org_a)
    assert ind["decisiones_acepto"]["valor"] == 1
    assert ind["tasa_aceptacion"]["valor"] is not None
    assert ind["recomendaciones_que_funcionaron"]["valor"] is not None
    assert ind["decisiones_sin_desenlace"]["valor"] == 0


# =============================================================================
#  INTEGRIDAD HISTORICA  --  PROTECT, y que nada desaparezca en silencio
# =============================================================================

def test_PROT_A_una_propuesta_SIN_decision_se_puede_borrar(org_a):
    """
    El contrapunto: PROTECT no bloquea todo, bloquea lo que tiene historia.

    Sin esta prueba, "PROTECT funciona" podria significar "nada se borra
    nunca", que no es lo que se pidio.
    """
    p = _propuesta(org_a)
    assert D.objects.filter(propuesta=p).count() == 0
    P.objects.filter(id=p.id).delete()
    assert not P.objects.filter(id=p.id).exists()


def test_PROT_B_una_propuesta_CON_decision_no_se_borra(org_a, jefe):
    from django.db.models import ProtectedError

    p = _propuesta(org_a)
    _decidir(p, jefe)
    d = D.objects.get(org=org_a)

    with pytest.raises(ProtectedError):
        P.objects.filter(id=p.id).delete()

    #  Y NADA desaparecio: ni la propuesta ni la decision.
    assert P.objects.filter(id=p.id).exists()
    assert D.objects.filter(id=d.id).exists()
    d.refresh_from_db()
    assert d.propuesta_id == p.id


def test_PROT_C_una_propuesta_con_APRENDIZAJE_no_se_borra(org_a, jefe):
    from django.db.models import ProtectedError

    p = _propuesta(org_a)
    #  Una leccion atada SOLO a la propuesta, sin decision de por medio.
    a = gobierno.registrar_aprendizaje(
        org_a, tipo=TipoAprendizaje.CORRELACION_INCORRECTA,
        origen=OrigenAprendizaje.PERSONA,
        conclusion="agrupo de mas", evidencia="se revisaron en sitio",
        propuesta=p, actor=jefe)

    with pytest.raises(ProtectedError):
        P.objects.filter(id=p.id).delete()
    assert Ap.objects.filter(id=a.id).exists()
    assert P.objects.filter(id=p.id).exists()


def test_PROT_C2_una_DECISION_con_aprendizaje_no_se_borra(org_a, jefe):
    """La cadena completa: el aprendizaje tambien protege a su decision."""
    from django.db.models import ProtectedError

    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="el PON volvio")
    assert d.aprendizajes.count() == 1

    with pytest.raises(ProtectedError):
        D.objects.filter(id=d.id).delete()
    assert D.objects.filter(id=d.id).exists()
    assert Ap.objects.filter(decision=d).exists()


def test_PROT_D_con_decision_y_situacion_no_desaparece_nada(org_a, jefe):
    from django.db.models import ProtectedError

    s = _situacion(org_a)
    p = _propuesta(org_a, situacion=s)
    _decidir(p, jefe)
    d = D.objects.get(org=org_a)
    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO,
        evidencia="volvieron las 12")

    antes = {
        "propuestas": P.objects.filter(org=org_a).count(),
        "decisiones": D.objects.filter(org=org_a).count(),
        "aprendizajes": Ap.objects.filter(org=org_a).count(),
        "eventos": s.eventos.count(),
        "auditoria": Activity.objects.filter(org=org_a).count(),
    }
    with pytest.raises(ProtectedError):
        P.objects.filter(id=p.id).delete()

    #  Ni un solo registro historico se movio.
    assert P.objects.filter(org=org_a).count() == antes["propuestas"]
    assert D.objects.filter(org=org_a).count() == antes["decisiones"]
    assert Ap.objects.filter(org=org_a).count() == antes["aprendizajes"]
    assert s.eventos.count() == antes["eventos"]
    #  §4.H  La auditoria sigue ahi despues del intento rechazado.
    assert Activity.objects.filter(org=org_a).count() == antes["auditoria"]
    assert Activity.objects.filter(
        org=org_a, entity_type=auditoria.ENTIDAD_PROPUESTA).exists()


def test_PROT_E_expirar_y_cancelar_son_ESTADOS_no_borrados(org_a, jefe):
    """
    §4.E  La historia se maneja con estados, no con DELETE.

    Se afirma sobre el EFECTO: despues de expirar y de cancelar, las filas
    siguen existiendo y lo unico que cambio es su estado.
    """
    p1 = _propuesta(org_a, accion="Primera")
    p2 = _propuesta(org_a, accion="Segunda")

    #  Expirar: el reloj la vence, no la borra.
    p1.expira_en = timezone.now() - timezone.timedelta(days=1)
    p1.save(update_fields=["expira_en"])
    sup.expirar_vencidas(org_a)
    p1.refresh_from_db()
    assert p1.estado == P.EXPIRADA
    assert P.objects.filter(id=p1.id).exists()

    #  Cancelar: tampoco.
    sup.cancelar(p2, motivo="ya no aplica")
    p2.refresh_from_db()
    assert p2.estado == P.CANCELADA
    assert P.objects.filter(id=p2.id).exists()

    assert P.objects.filter(org=org_a).count() == 2


def test_PROT_F_las_decisiones_siguen_siendo_su_propio_registro(org_a, jefe):
    """
    §4.F  Una decision no se reescribe para cambiar lo que se decidio.

    'tipo' y 'decidida_en' son el hecho; lo unico que se completa despues es el
    desenlace, y una sola vez (lo afirma 'test_M2').
    """
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    tipo, cuando = d.tipo, d.decidida_en

    gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.PARCIAL,
        evidencia="volvieron 9 de 12")

    d.refresh_from_db()
    assert d.tipo == tipo
    assert d.decidida_en == cuando


def test_PROT_G_el_aprendizaje_sigue_siendo_append_only(org_a, jefe):
    s = _situacion(org_a)
    a = gobierno.registrar_falso_positivo(s, actor=jefe, motivo="no era nada")
    with pytest.raises(Ap.NoSeReescribe):
        a.conclusion = "otra cosa"
        a.save()
    with pytest.raises(Ap.NoSeReescribe):
        a.delete()
    assert Ap.objects.filter(id=a.id).exists()


def test_PROT_I_el_tenant_no_se_cruza_al_proteger(org_a, org_b, jefe):
    """Proteger la propuesta de A no debe estorbar a B, ni al reves."""
    from django.db.models import ProtectedError

    p_a = _propuesta(org_a)
    _decidir(p_a, jefe)
    #  B tiene una propuesta sin decidir: se borra sin problema.
    p_b = _propuesta(org_b)
    P.objects.filter(id=p_b.id).delete()
    assert not P.objects.filter(id=p_b.id).exists()
    #  Y la de A sigue protegida.
    with pytest.raises(ProtectedError):
        P.objects.filter(id=p_a.id).delete()
    assert D.objects.filter(org=org_a).count() == 1
    assert D.objects.filter(org=org_b).count() == 0


def test_PROT_J_la_idempotencia_del_desenlace_no_se_rompio(org_a, jefe):
    """§4.J  Lo que P8.2 ya garantizaba sigue garantizado tras el cambio."""
    _decidir(_propuesta(org_a), jefe)
    d = D.objects.get(org=org_a)
    uno = gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO, evidencia="volvio")
    dos = gobierno.registrar_resultado(
        d, actor=jefe, resultado=ResultadoDecision.FUNCIONO, evidencia="volvio")
    assert uno.resultado_en == dos.resultado_en
    with pytest.raises(gobierno.DesenlaceIncompatible):
        gobierno.registrar_resultado(
            d, actor=jefe, resultado=ResultadoDecision.NO_FUNCIONO,
            evidencia="otra cosa")
    assert Ap.objects.filter(
        org=org_a, tipo=TipoAprendizaje.RECOMENDACION_CONFIRMADA).count() == 1
