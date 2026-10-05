# -*- coding: utf-8 -*-
"""
================================================================================
 BLOQUE A  --  la fuente de flota, y la coordinacion al fin alcanzable
================================================================================

QUE CIERRA ESTE BLOQUE
----------------------
Dos huecos que la auditoria de P7-P13 midio y nombro:

  1. La fuente SmartOLT de FLOTA estaba construida y SIN herramienta: la
     variable 'SUPERVISOR_HERRAMIENTAS_CAIDAS_PON' venia vacia y el adaptador
     contestaba NO_DISPONIBLE -- correcto, pero el Supervisor no veia la red.

  2. 'operaciones/coordinacion.py' (P6) no tenia NINGUNA forma de ser
     alcanzado: ni endpoint ni trabajo del scheduler. Sus 42 pruebas pasaban y
     en produccion no existia. Es textual lo que CLAUDE.md §6 llama "codigo
     construido no es codigo que corre".

LO QUE SE SUSTITUYE, Y NADA MAS
-------------------------------
  * '_pedirle_al_motor': la llamada HTTP al motor. Se sustituye porque el motor
    es otro proceso y la credencial de SmartOLT vive alli. Lo que se le devuelve
    es el SOBRE REAL del proveedor ('response.sections[].groups[].pons[]'), asi
    que '_resumir_pons' --el parser de verdad-- corre entero.
  * '_interruptor_de': el interruptor del motor, que en la base de pruebas de
    Django no existe. Sin sustituirlo, el nivel 2 nunca seria efectivo y el
    camino permitido quedaria sin probar.

Todo lo demas es real: los adaptadores, los snapshots, la correlacion, las
situaciones, M02, la auditoria y la autonomia.
================================================================================
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.utils import timezone

from common.models import Activity, Profile, User
from operaciones import actividades as m02
from operaciones import auditoria
from operaciones import autonomia as gob
from operaciones import chat_herramientas, correlacion, coordinacion
from operaciones import fuentes, fuentes_adaptadores
from operaciones.fuentes_modelos import (EstadoLectura, Fuente, FuenteEstado,
                                         FuenteSnapshot)
from operaciones.models import (ActividadOperativa, ProgramacionOrden,
                                PropuestaSupervisor)
from operaciones.situaciones_modelos import (SituacionOperativa, TipoAfectado,
                                             TipoEvento)
from operaciones.tests.test_p5_chat_supervisor import _situacion

A = ActividadOperativa
P = PropuestaSupervisor
S = SituacionOperativa
RUTA = "/api/operaciones/supervisor/coordinar/"
HERRAMIENTA = "consultar_caidas_pon_flota"

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
    return _persona(org_a, "jefe.bloquea@prueba.local")[1]


@pytest.fixture
def cliente_jefe(org_a):
    from conftest import _make_authenticated_client
    u, p = _persona(org_a, "cli.bloquea@prueba.local")
    return _make_authenticated_client(u, org_a, p), p


def _sobre(pons, olt=3):
    """El sobre REAL de 'get_outage_pons', como lo devuelve la flota."""
    return {"response": {"sections": [
        {"key": "los", "olt_id": olt,
         "groups": [{"subscribers": 60, "pons": pons}]}]},
        "olts_consultadas": 1}


def _pon(afectados, port="3/1/4", olt=3, ahora=None):
    """
    Los nombres REALES del proveedor, no los que uno supondria.

    'affected_onus' y no 'affected'; 'subscribers' vive en el GRUPO y no aqui; y
    'olt_id' va DENTRO del pon, porque de ahi sale la clave
    'olt_id/board/port' del resumen. Supuse otros y las aserciones fallaron --
    es el motivo por el que esta prueba existe.

    LOS SELLOS VAN RELATIVOS A 'ahora', y tambien eso lo ensenaron las pruebas:
    con una fecha FIJA ('02:20') el dato quedaba viejo de horas, el seguimiento
    lo leia como senal ausente y movia la situacion a 'en_verificacion'. El
    sistema estaba haciendo lo correcto; el dato de la prueba estaba mal.
    """
    ahora = ahora or timezone.now()
    return {"olt_id": olt, "board": 3, "port": port,
            "affected_onus": afectados, "total_onus": 60,
            "affected_percent": round(afectados / 60 * 100, 1),
            "los_count": afectados,
            "partial_started_at": (ahora - timezone.timedelta(
                minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "partial_last_seen_at": ahora.strftime("%Y-%m-%d %H:%M:%S")}


def _con_herramienta(valor=HERRAMIENTA):
    import os
    return mock.patch.dict(
        os.environ,
        {fuentes_adaptadores.VARIABLE_HERRAMIENTA_SMARTOLT: valor,
         "MOTOR_TENANT": "rapilink"}, clear=False)


def _sin_herramienta():
    import os
    return mock.patch.dict(
        os.environ,
        {fuentes_adaptadores.VARIABLE_HERRAMIENTA_SMARTOLT: "",
         "MOTOR_TENANT": "rapilink"}, clear=False)


def _motor(respuesta):
    """Sustituye SOLO la llamada HTTP al motor. El parser corre de verdad."""
    if isinstance(respuesta, Exception):
        return mock.patch.object(fuentes_adaptadores, "_pedirle_al_motor",
                                 side_effect=respuesta)
    return mock.patch.object(fuentes_adaptadores, "_pedirle_al_motor",
                             return_value=respuesta)


def _permitir_ejecucion():
    return mock.patch("operaciones.autonomia._interruptor_de",
                      return_value=(True, ""))


def _detener_ejecucion(motivo="el interruptor del motor esta detenido"):
    return mock.patch("operaciones.autonomia._interruptor_de",
                      return_value=(False, motivo))


def _coordinable(org, actor):
    gob.cambiar(org, P.NIVEL_COORDINAR, actor=actor,
                motivo="piloto del bloque A",
                criterios="se revierte si aparece trabajo que nadie pidio")
    return _permitir_ejecucion()


def _fuente(org):
    f, _ = FuenteEstado.objects.update_or_create(
        org=org, fuente=Fuente.SMARTOLT,
        defaults={"activa": True, "frecuencia_segundos": 300,
                  "antiguedad_maxima_segundos": 900,
                  "ventana_inconclusa_segundos": 0})
    return f


def _cuerpo(codigo="S-001", **extra):
    d = {"situacion": codigo, "clase": "actividad",
         "tipo": A.TAREA, "titulo": "Diagnosticar el PON 3/1/4",
         "objetivo": "Confirmar si la afectación es óptica o de energía",
         "condicion_exito": "Reporte con la causa y la potencia medida",
         "area": "NOC"}
    d.update(extra)
    return d


# =============================================================================
#  §2/§4  --  LA FUENTE DE FLOTA
# =============================================================================

def test_A1_sin_herramienta_declarada_la_fuente_dice_NO_DISPONIBLE(org_a):
    """
    El estado de ayer, y la frase importa: NO se asume que la red este sana.
    """
    with _sin_herramienta():
        lectura = fuentes_adaptadores.smartolt(org_a, _fuente(org_a),
                                               timezone.now())
    assert lectura.estado == EstadoLectura.NO_DISPONIBLE
    assert fuentes_adaptadores.VARIABLE_HERRAMIENTA_SMARTOLT in \
        lectura.motivo_no_disponible
    #  Y lo dice con todas las letras, con el NO en mayuscula.
    assert "NO se conoce" in lectura.motivo_no_disponible
    assert lectura.datos in (None, {}, [])


def test_A2_con_la_herramienta_declarada_la_fuente_LEE(org_a):
    """La cadena completa: herramienta -> motor -> sobre real -> resumen."""
    with _con_herramienta(), _motor(_sobre([_pon(12)])):
        lectura = fuentes_adaptadores.smartolt(org_a, _fuente(org_a),
                                               timezone.now())

    assert lectura.estado == EstadoLectura.CON_DATOS
    assert lectura.registros == 1
    #  La clave es 'olt/board/port': sin el olt, dos OLTs se pisarian.
    clave = next(iter(lectura.datos))
    assert clave.endswith("3/1/4")
    assert lectura.datos[clave]["afectados"] == 12
    assert lectura.esquema == "smartolt_pon_v1"


def test_A3_vacio_es_SIN_REGISTROS_y_no_NO_DISPONIBLE(org_a):
    """
    Las tres cosas son distintas y no se colapsan:
      sin herramienta -> NO_DISPONIBLE  (no se sabe)
      sin caidas      -> SIN_REGISTROS  (se sabe, y no hay)
      error           -> ERROR          (no se pudo)
    """
    with _con_herramienta(), _motor(_sobre([])):
        lectura = fuentes_adaptadores.smartolt(org_a, _fuente(org_a),
                                               timezone.now())
    assert lectura.estado == EstadoLectura.SIN_REGISTROS
    assert lectura.registros == 0
    assert not lectura.motivo_no_disponible


def test_A4_un_error_del_proveedor_es_ERROR_de_fuente(org_a):
    with _con_herramienta(), _motor(
            fuentes_adaptadores.MotorNoDisponible("502 del proveedor")):
        lectura = fuentes_adaptadores.smartolt(org_a, _fuente(org_a),
                                               timezone.now())
    assert lectura.estado == EstadoLectura.ERROR
    assert lectura.error_tecnico
    #  NO devuelve datos parciales: no hay con que afirmar nada.
    assert not lectura.datos


def test_A5_la_herramienta_no_declarada_en_el_catalogo_es_NO_DISPONIBLE(org_a):
    """
    Nombrada en la variable pero ausente del catalogo del tenant: el motor la
    rechaza, y eso NO puede leerse como 'sin caidas'.
    """
    with _con_herramienta("no_existe_en_el_catalogo"), _motor(
            fuentes_adaptadores._NoDeclarada("no esta en el catalogo")):
        lectura = fuentes_adaptadores.smartolt(org_a, _fuente(org_a),
                                               timezone.now())
    assert lectura.estado == EstadoLectura.NO_DISPONIBLE
    assert "NO se conoce" in lectura.motivo_no_disponible


def test_A6_la_trazabilidad_queda_en_el_snapshot(org_a):
    """Timestamp de consulta, timestamp del dato y estado: los tres."""
    f = _fuente(org_a)
    inicio = timezone.now()
    with _con_herramienta(), _motor(_sobre([_pon(12)])):
        informe = fuentes.sondear(org_a, ahora=inicio,
                                  adaptadores={Fuente.SMARTOLT:
                                               fuentes_adaptadores.smartolt})

    assert informe["sondeadas"] >= 1
    f.refresh_from_db()
    assert f.ultima_consulta_fin is not None    # cuando se pregunto
    assert f.estado == EstadoLectura.CON_DATOS
    assert f.dato_en is not None               # de cuando es el dato
    assert f.registros == 1
    snap = FuenteSnapshot.objects.filter(org=org_a,
                                         fuente=Fuente.SMARTOLT).first()
    assert snap is not None
    assert snap.registros == 1
    assert snap.esquema == "smartolt_pon_v1"


def test_A7_sin_MOTOR_TENANT_no_se_consulta(org_a):
    """Fail-closed con el tenant: suponerlo leeria los datos de otra empresa."""
    import os
    with mock.patch.dict(os.environ, {"MOTOR_TENANT": ""}, clear=False):
        with pytest.raises(fuentes_adaptadores.MotorNoDisponible) as e:
            fuentes_adaptadores._pedirle_al_motor(HERRAMIENTA, {})
    assert "MOTOR_TENANT" in str(e.value)


def test_A8_dos_empresas_no_comparten_la_lectura(org_a, org_b):
    #  Se sondea POR A. El adaptador por si solo no persiste --eso es de
    #  'fuentes.registrar'--, asi que se pasa por 'sondear', que es el camino
    #  real. Mi primera version llamaba al adaptador suelto y esperaba un
    #  snapshot: no lo hay, y la asercion estaba mal.
    _fuente(org_a)
    _fuente(org_b)
    with _con_herramienta(), _motor(_sobre([_pon(12)])):
        fuentes.sondear(org_a, ahora=timezone.now(),
                        adaptadores={Fuente.SMARTOLT:
                                     fuentes_adaptadores.smartolt})
    assert FuenteSnapshot.objects.filter(org=org_a).count() == 1
    #  Y B no tiene nada: nadie sondeo por ella.
    assert not FuenteSnapshot.objects.filter(org=org_b).exists()


# =============================================================================
#  §5/§6  --  EL CALLER DE M02, Y SU PUERTA
# =============================================================================

def test_B1_con_autonomia_insuficiente_la_ruta_devuelve_409_y_no_escribe(
        org_a, cliente_jefe):
    cli, _ = cliente_jefe
    s = _situacion(org_a)
    antes = Activity.objects.filter(org=org_a).count()

    r = cli.post(RUTA, _cuerpo(), format="json")

    assert r.status_code == 409, r.content
    cuerpo = json.loads(r.content)
    assert cuerpo["error"] == "AUTONOMIA_INSUFICIENTE"
    #  El veredicto viaja: quien recibe el 409 puede decir POR QUE no.
    assert cuerpo["veredicto"]["puede"] is False
    assert cuerpo["veredicto"]["motivo"]
    #  Y NADA se escribio en M02 ni en el timeline.
    assert A.objects.filter(org=org_a).count() == 0
    assert s.eventos.filter(tipo=TipoEvento.COORDINACION).count() == 0
    #  El intento quedo AUDITADO.
    assert Activity.objects.filter(org=org_a).count() == antes + 1
    fila = Activity.objects.filter(org=org_a).order_by("-created_at").first()
    assert fila.action == "REJECTED"
    assert fila.entity_type == auditoria.ENTIDAD_SITUACION


def test_B2_con_autonomia_suficiente_la_ruta_CREA_la_actividad(org_a,
                                                               cliente_jefe):
    cli, perfil = cliente_jefe
    s = _situacion(org_a)
    with _coordinable(org_a, perfil):
        r = cli.post(RUTA, _cuerpo(), format="json")

    assert r.status_code == 201, r.content
    cuerpo = json.loads(r.content)
    assert cuerpo["repetida"] is False
    assert cuerpo["situacion"] == "S-001"
    assert cuerpo["nivel_efectivo"] == P.NIVEL_COORDINAR
    a = A.objects.get(org=org_a)
    assert a.origen_tipo == coordinacion.ORIGEN_SITUACION
    assert a.origen_id == str(s.id)
    assert cuerpo["actividad"]["id"] == str(a.id)
    #  Y el evento de coordinacion quedo en el timeline.
    assert s.eventos.filter(tipo=TipoEvento.COORDINACION).count() == 1


def test_B3_la_ruta_tambien_pide_evidencia(org_a, cliente_jefe):
    cli, perfil = cliente_jefe
    _situacion(org_a)
    with _coordinable(org_a, perfil):
        r = cli.post(RUTA, _cuerpo(
            clase="evidencia", clase_evidencia="medicion",
            detalle="potencia óptica en la ONT",
            condicion_exito="Valor en dBm registrado"), format="json")

    assert r.status_code == 201, r.content
    a = A.objects.get(org=org_a)
    assert a.tipo == A.SOLICITUD_INFORMACION
    assert "Medición" in a.titulo


def test_B4_pedir_dos_veces_lo_mismo_deja_UNA_actividad(org_a, cliente_jefe):
    cli, perfil = cliente_jefe
    _situacion(org_a)
    with _coordinable(org_a, perfil):
        uno = cli.post(RUTA, _cuerpo(), format="json")
        dos = cli.post(RUTA, _cuerpo(), format="json")

    assert uno.status_code == 201
    #  200 y 'repetida': que ya existiera NO es un error, es la idempotencia de
    #  dominio de M02. Quien llama puede distinguir "abri una" de "ya estaba".
    assert dos.status_code == 200, dos.content
    assert json.loads(dos.content)["repetida"] is True
    assert A.objects.filter(org=org_a).count() == 1


def test_B5_una_situacion_de_otra_empresa_da_404(org_a, org_b, cliente_jefe):
    cli, perfil = cliente_jefe
    _situacion(org_b, codigo="S-001")      # existe, pero es de B
    with _coordinable(org_a, perfil):
        r = cli.post(RUTA, _cuerpo(), format="json")
    #  404 y no 403: decir "existe pero no es tuya" ya confirmaria que existe.
    assert r.status_code == 404, r.content
    assert A.objects.filter(org=org_b).count() == 0


def test_B6_sin_sesion_y_sin_rol_no_se_coordina(org_a, unauthenticated_client):
    _situacion(org_a)
    assert unauthenticated_client.post(
        RUTA, _cuerpo(), format="json").status_code in (401, 403)

    from conftest import _make_authenticated_client
    u, p = _persona(org_a, "raso.bloquea@prueba.local", role="USER")
    cli = _make_authenticated_client(u, org_a, p)
    assert cli.post(RUTA, _cuerpo(), format="json").status_code == 403
    assert A.objects.filter(org=org_a).count() == 0


def test_B7_un_cuerpo_incompleto_se_rechaza_antes_de_mirar_la_autonomia(
        org_a, cliente_jefe):
    cli, perfil = cliente_jefe
    _situacion(org_a)
    with _coordinable(org_a, perfil):
        r = cli.post(RUTA, _cuerpo(titulo="", objetivo=""), format="json")
    assert r.status_code == 400, r.content
    assert json.loads(r.content)["error"] == "CUERPO_INVALIDO"


def test_B8_el_chat_sigue_sin_poder_coordinar(org_a):
    """§9: el chat consulta y explica. Ejecutar pasa por el caller protegido."""
    for inventada in ("solicitar_actividad", "solicitar_evidencia",
                      "coordinar", "coordinaciones_de_situacion_escribir"):
        assert inventada not in chat_herramientas.HERRAMIENTAS
    #  Y la de lectura que SI tiene no escribe nada.
    _situacion(org_a)
    salida = chat_herramientas.ejecutar(
        org_a, "coordinaciones_de_situacion", {"codigo": "S-001"})
    assert salida["cuantas"] == 0
    assert A.objects.filter(org=org_a).count() == 0


# =============================================================================
#  §10  --  LOS CINCO E2E
# =============================================================================

def test_E2E_1_de_la_senal_de_flota_a_la_situacion(org_a):
    """
    SmartOLT (flota) -> deteccion -> correlacion -> situacion.

    Pasa por el adaptador REAL y su parser: lo unico sustituido es la llamada
    HTTP al motor, que recibe el sobre del proveedor tal como es.
    """
    ahora = timezone.now()
    _fuente(org_a)
    with _con_herramienta(), _motor(_sobre([_pon(12, ahora=ahora)])):
        fuentes.sondear(org_a, ahora=ahora,
                        adaptadores={Fuente.SMARTOLT:
                                     fuentes_adaptadores.smartolt})
        informe = correlacion.correr(org_a, ahora=ahora)

    assert informe["creadas"] == 1
    s = S.objects.get(org=org_a)
    assert s.estado == S.DETECTADA
    assert "3/1/4" in s.titulo
    #  Y la situacion existe SIN un solo ticket: es el punto del Supervisor.
    assert s.afectados.filter(tipo=TipoAfectado.CASO).count() == 0
    #  El hecho dice 12; la hipotesis va aparte y con su confianza.
    assert "12" in s.eventos.get(tipo=TipoEvento.DETECTADA).resumen
    assert s.hipotesis


def test_E2E_2_recomendar_con_autonomia_baja_rechaza_audita_y_no_escribe(
        org_a, jefe):
    """Situacion -> coordinacion -> autonomia <2 -> rechazo -> auditoria."""
    s = _situacion(org_a)
    antes = {"act": A.objects.filter(org=org_a).count(),
             "eventos": s.eventos.count(),
             "aud": Activity.objects.filter(org=org_a).count()}

    with pytest.raises(coordinacion.CoordinacionNoPermitida):
        coordinacion.solicitar_actividad(
            s, actor=jefe, titulo="Diagnosticar", objetivo="x",
            condicion_exito="y", area="NOC")

    s.refresh_from_db()
    assert A.objects.filter(org=org_a).count() == antes["act"]
    assert s.eventos.count() == antes["eventos"]
    assert Activity.objects.filter(org=org_a).count() == antes["aud"] + 1
    #  Y RECOMENDAR si esta permitido: nivel 1 no necesita autonomia 2.
    p = coordinacion.recomendar_programacion(
        s, actor=jefe, accion="Programar diagnóstico", motivo="12 ONT caídas",
        evidencia=[{"fuente": "smartolt", "id": "3/1/4", "dato": "12 ONT",
                    "observado_en": timezone.now().isoformat()}])
    assert p.nivel_autonomia_requerido == P.NIVEL_RECOMENDAR


def test_E2E_3_coordinacion_con_autonomia_suficiente_y_su_traza(org_a, jefe):
    """Situacion -> coordinacion -> actividad -> vinculo -> trazabilidad."""
    s = _situacion(org_a)
    with _coordinable(org_a, jefe):
        salida = coordinacion.solicitar_evidencia(
            s, actor=jefe, clase="diagnostico",
            detalle="causa de la caída del PON 3/1/4",
            condicion_exito="Causa identificada y registrada", area="NOC")

    a = salida["actividad"]
    #  Traza en los DOS sentidos.
    assert a.origen_id == str(s.id)
    evento = s.eventos.get(tipo=TipoEvento.COORDINACION)
    assert evento.datos["actividad_id"] == str(a.id)
    assert evento.datos["condicion_exito"]
    #  Y la situacion NO se movio: crear una actividad no resuelve nada.
    s.refresh_from_db()
    assert s.estado in S.VIVAS
    assert s.verificacion == ""
    #  'ejecutada != validada', hasta el final.
    m02.iniciar_gestion(a, actor=jefe)
    m02.completar(a, actor=jefe, requiere_validacion=True)
    assert coordinacion.pendientes_de_la_situacion(s)[
        "completadas_sin_validar"] == 1


def test_E2E_4_el_interruptor_recorta_la_autonomia_aunque_este_configurada(
        org_a, jefe):
    """
    Configurada 2 y EFECTIVA 1 porque el interruptor del motor esta detenido.

    Es el caso que §6 pide explicitamente: no basta con leer la configuracion
    nominal. Sin esta prueba, 'autonomia >= 2' se podria haber implementado
    leyendo 'nivel_configurado' y nadie lo habria notado.
    """
    s = _situacion(org_a)
    gob.cambiar(org_a, P.NIVEL_COORDINAR, actor=jefe,
                motivo="configurada en 2", criterios="x")

    with _detener_ejecucion():
        estado = gob.nivel_efectivo(org_a)
        assert estado["configurado"] == P.NIVEL_COORDINAR
        assert estado["efectivo"] == P.NIVEL_RECOMENDAR
        assert estado["recortado"] is True

        with pytest.raises(coordinacion.CoordinacionNoPermitida) as e:
            coordinacion.solicitar_actividad(
                s, actor=jefe, titulo="Diagnosticar", objetivo="x",
                condicion_exito="y", area="NOC")

    assert e.value.veredicto["efectivo"] == P.NIVEL_RECOMENDAR
    assert A.objects.filter(org=org_a).count() == 0
    #  Auditado igual que cualquier otro rechazo.
    assert Activity.objects.filter(org=org_a, action="REJECTED").count() == 1


def test_E2E_5_M03_se_consulta_y_se_recomienda_pero_NO_se_escribe(org_a, jefe):
    """La consulta y la recomendacion pasan; la escritura no tiene camino."""
    import ast
    import inspect

    #  1. CONSULTAR: permitido, y sin autonomia ninguna.
    panorama = coordinacion.panorama_m03(org_a)
    assert "capacidad" in panorama
    assert panorama["lineas_programadas"] == 0
    assert "ordenes_sin_plazo_medible" in panorama

    #  2. RECOMENDAR: permitido en nivel 1.
    s = _situacion(org_a)
    p = coordinacion.recomendar_programacion(
        s, actor=jefe, accion="Programar la orden dentro de su plazo",
        motivo="sin programación y el plazo corre",
        evidencia=[{"fuente": "m03", "id": "x", "dato": "sin programada_para",
                    "observado_en": timezone.now().isoformat()}])
    assert p.estado == P.PROPUESTA

    #  3. ESCRIBIR: no hay camino. Afirmado sobre el AST del modulo.
    arbol = ast.parse(inspect.getsource(coordinacion))
    nombres = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    nombres |= {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    for escritura in ("reprogramar_orden", "actualizar_secuencia",
                      "secuenciar_jornada", "registrar_contingencia"):
        assert escritura not in nombres, escritura
    #  Y nada se movio en M03.
    assert ProgramacionOrden.objects.filter(org=org_a).count() == 0


def test_B9_un_error_de_M02_se_traduce_y_NO_revienta(org_a, cliente_jefe):
    """
    El camino que ninguna prueba tocaba, y que 'ruff' encontro antes que ellas.

    La primera version de la vista escribia 'except ErrorActividad' con el
    nombre suelto, y ese nombre NO esta importado en 'views.py' -- el resto del
    archivo lo nombra 'actividades.ErrorActividad'. Si M02 hubiera levantado su
    error de dominio, el 'except' habria dado 'NameError' y la respuesta un 500
    en vez del 400/409 que corresponde.

    Ninguna prueba lo cazo porque ningun cuerpo valido llega a ese 'except':
    las validaciones de 'coordinacion' muerden antes. Asi que se provoca el
    error en el borde justo, con lo que mide es el MAPEO de la vista.
    """
    cli, perfil = cliente_jefe
    _situacion(org_a)
    with _coordinable(org_a, perfil):
        with mock.patch.object(
                coordinacion, "solicitar_actividad",
                side_effect=m02.TransicionInvalida("no se puede")):
            r = cli.post(RUTA, _cuerpo(), format="json")

    #  409 y con su codigo, no un 500 ni un NameError.
    assert r.status_code == 409, r.content
    assert json.loads(r.content)["error"] == "TRANSICION_INVALIDA"
    assert A.objects.filter(org=org_a).count() == 0
