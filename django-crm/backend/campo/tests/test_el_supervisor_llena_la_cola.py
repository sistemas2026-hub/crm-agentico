# -*- coding: utf-8 -*-
"""
================================================================================
 EL EFECTO: EL CASO APARECE EN DESPACHO SIN QUE NADIE LO ACEPTE
================================================================================

POR QUE ESTA PRUEBA ES LA QUE CUENTA
------------------------------------
'operaciones/tests/test_las_cinco_reglas.py' afirma sobre la TABLA: dado un
grupo y una medicion, si la regla deja pasar. Eso corre sin base y sin red, y
es necesario -- pero es el mecanismo.

El efecto que el cliente pidio es otro: que el caso ESTE en la pantalla de
Despacho sin que una persona lo haya aceptado. Y eso se mira donde se mira,
que es la respuesta de 'GET /api/campo/casos-despachables/'.

La diferencia no es teorica. El 14/10/2026, en este mismo repositorio, ocho
pruebas estuvieron en verde con el sintoma vivo porque afirmaban sobre un
contador del informe en vez de sobre la fila. Esta prueba existe para que eso
no se repita en este camino.

LO QUE TAMBIEN FIJA, Y ES EL LIMITE DE ALCANCE
----------------------------------------------
Que el caso aparezca en la COLA y nada mas: sin orden de trabajo creada, sin
tecnico y sin fecha. Decidido por el cliente el 14/10/2026, y es lo que hace
reversible todo esto -- un caso mal pasado ensucia una cola y se saca; una
cuadrilla mal mandada son dos horas de alguien. Hay una prueba propia para eso.

EDITADO EL 16/10/2026 (FASE 3), CON AUTORIZACION DEL USUARIO
------------------------------------------------------------
Este archivo fijaba la regla 1 vieja: una falla pasaba con la labor
'verificada' que traia la señal. Desde la Fase 3 el paso decide SOLO con lo
guardado en la propuesta, una falla pasa solo con una MEDICION del equipo en
linea con la señal fuera de rango, y un caso sin una copia fresca de WispHub
no pasa. Se ajusto el andamio --lo que la señal decia queda escrito en la
propuesta, y el caso trae su copia de WispHub--. Las afirmaciones son las
mismas.
================================================================================
"""

import pytest
from django.utils import timezone

from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

CASOS = "/api/campo/casos-despachables/"


# =============================================================================
#  andamio
# =============================================================================

class _Senal:
    """Una señal de ticket leido, con lo que 'diagnosticar' deja en 'datos'."""

    def __init__(self, caso_id, *, grupo, labor, verificada, confianza,
                 porque="el equipo esta caido por perdida de señal optica"):
        self.tipo = PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO
        self.origen_tipo = "case"
        self.origen_id = str(caso_id)
        self.evidencia = []
        self.datos = {
            "diagnostico_leido": True,
            "grupo": grupo,
            "labor": labor,
            "labor_verificada": verificada,
            "labor_porque": porque,
            "diagnostico_confianza": confianza,
            #  LA QUE DECIDE desde el 14/10/2026: la del GRUPO. Se pone igual
            #  a la otra en este andamio porque lo que estas pruebas miden es
            #  el efecto, no la diferencia entre las dos -- esa tiene su propia
            #  guarda en 'test_las_cinco_reglas.py'.
            "confianza_del_grupo": confianza,
        }


_TICKET = iter(range(810000, 819999))


def _caso_con_ticket(org, nombre="No tiene internet"):
    """
    Un caso con su referencia externa COMPLETA.

    'case_external_ref_complete' exige 'provider' y 'external_ticket_id' las
    dos o ninguna -- un proveedor sin su numero de ticket no es una referencia,
    es media. La primera version de este andamio daba solo el proveedor y las
    nueve pruebas fallaron por eso, no por el codigo que miden.
    """
    from cases.models import Case

    return Case.objects.create(
        org=org, name=nombre, status="New", priority="Normal", is_active=True,
        provider="wisphub", external_ticket_id=str(next(_TICKET)),
        external_service_id="3614",
        #  La copia fresca y en curso de WispHub: sin ella, el caso no pasa.
        external_status="Nuevo", external_fetched_at=timezone.now(),
        description="El cliente dice que no tiene internet desde anoche.")


def _propuesta_sin_decidir(org, caso):
    """Como la deja el ciclo: PROPUESTA, esperando a que alguien la mire."""
    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        estado=PropuestaSupervisor.PROPUESTA,
        #  'propuesta_exige_evidencia' lo prohibe vacio, y con razon: una
        #  recomendacion que no se puede discutir no deberia existir.
        evidencia=[{"fuente": "diagnostico_del_ticket",
                    "dato": "lectura del reclamo: no tiene servicio",
                    "momento": "2026-10-14T18:00:00Z"}])


def _guardar_lo_leido(p, s):
    """
    Lo que la señal trae, escrito en la propuesta: desde la Fase 3 el paso
    decide con lo guardado. Una falla 'verificada' lleva una MEDICION del
    equipo en linea con la señal fuera de rango (-27.4 dBm); una sin
    verificar, una medicion en rango, que contradice el reclamo.
    """
    from operaciones import medicion_de_fallas as mdf

    d = s.datos
    lectura = {"fuente": "diagnostico_del_ticket",
               "dato": "lectura del reclamo: no tiene servicio",
               "observado_en": timezone.now().isoformat(),
               "grupo": d["grupo"], "labor": d["labor"],
               "labor_verificada": d["labor_verificada"],
               "labor_porque": d["labor_porque"],
               "confianza": d["diagnostico_confianza"],
               "confianza_del_grupo": d["confianza_del_grupo"]}
    p.evidencia = [*(p.evidencia or []), lectura]
    p.save(update_fields=["evidencia"])
    if d["grupo"] == pad.FALLA_DE_SERVICIO:
        verificada = d["labor_verificada"]
        mdf.escribir(p, mdf.de_la_respuesta({
            "estado": "en_linea", "causa_caida": "", "motivo": "",
            "senal_dbm": -27.4 if verificada else -21.0,
            "senal": "debil" if verificada else "buena"}), timezone.now())
    p.refresh_from_db()


def _las_puertas_abiertas(monkeypatch):
    """
    La delegacion y el techo, que NO son lo que esta prueba mide: tienen sus
    propias guardas. Lo que se mide aca es el efecto cuando estan abiertas.
    """
    from operaciones import autonomia, tareas_delegadas

    monkeypatch.setattr(tareas_delegadas, "esta_delegada",
                        lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})


def _en_la_cola(cliente):
    return [c["nombre"] for c in cliente.get(CASOS).json()["casos"]]


# =============================================================================
#  §1  EL EFECTO
# =============================================================================

def test_una_falla_CONFIRMADA_entra_a_la_cola_sin_que_nadie_la_acepte(
        admin_client, org_a, monkeypatch):
    """
    LA PRUEBA CENTRAL. Mira la pantalla, no la propuesta.
    """
    from operaciones import clasificacion_de_trabajo as clf

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta")
    _guardar_lo_leido(p, s)
    _las_puertas_abiertas(monkeypatch)

    #  CONTROL: antes de pasar, la pantalla NO lo tiene. Sin esto, un "aparece"
    #  no distingue "el Supervisor lo paso" de "la pantalla lista todo".
    assert _en_la_cola(admin_client) == [], (
        "la pantalla ya listaba el caso antes de que nada lo aprobara")

    r = pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    assert r["paso"] is True, r["porque"]
    assert _en_la_cola(admin_client) == ["No tiene internet"], (
        "el Supervisor dijo que paso, y el caso NO esta en la cola de "
        "Despacho: el efecto no ocurrio")


def test_el_porque_queda_a_la_vista_de_quien_despacha(admin_client, org_a,
                                                      monkeypatch):
    """
    Un caso que aparece en la cola sin decir por que es peor que uno que no
    aparece: quien despacha no tiene con que discutirlo.
    """
    from operaciones import clasificacion_de_trabajo as clf

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta",
               porque="la señal de bajada es debil (-27.4 dBm)")
    _guardar_lo_leido(p, s)
    _las_puertas_abiertas(monkeypatch)

    pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    p.refresh_from_db()
    #  'resultado' es donde 'revisar' deja lo que se decidio y con que
    #  comentario -- no hay un 'comentario_revision'.
    escrito = f"{p.resultado or ''} {p.evidencia}"
    assert "-27.4 dBm" in escrito, (
        f"el numero contra el que se decidio no quedo escrito: {escrito[:300]}")


def test_un_trabajo_PEDIDO_entra_aunque_el_equipo_este_sano(admin_client,
                                                            org_a, monkeypatch):
    """
    Cambiar la clave del wifi igual necesita que alguien vaya. Es la regla 2.
    """
    from operaciones import clasificacion_de_trabajo as clf

    caso = _caso_con_ticket(org_a, "Cambio De Contrasena En Router Wifi")
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.TRABAJO_PEDIDO, labor=clf.TRABAJOS,
               verificada=False, confianza="alta")
    _guardar_lo_leido(p, s)
    _las_puertas_abiertas(monkeypatch)

    r = pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    assert r["paso"] is True, r["porque"]
    assert _en_la_cola(admin_client) == ["Cambio De Contrasena En Router Wifi"]


# =============================================================================
#  §2  LOS CONTRAFACTICOS: LO QUE NO TIENE QUE APARECER
# =============================================================================

def test_una_pagina_bloqueada_NO_entra_a_la_cola(admin_client, org_a,
                                                 monkeypatch):
    from operaciones import clasificacion_de_trabajo as clf

    caso = _caso_con_ticket(org_a, "Paginas Bloqueadas")
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.NADA_LO_MIDE, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta")
    _guardar_lo_leido(p, s)
    _las_puertas_abiertas(monkeypatch)

    r = pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    assert r["paso"] is False
    assert _en_la_cola(admin_client) == [], (
        "un reclamo que ninguna herramienta puede comprobar llego a la cola "
        "de Despacho")
    p.refresh_from_db()
    assert p.estado == PropuestaSupervisor.PROPUESTA, (
        "la propuesta se acepto sola: tenia que quedar esperando a una persona")


def test_un_equipo_SANO_con_reclamo_de_falla_NO_entra(admin_client, org_a,
                                                      monkeypatch):
    """El reclamo y la medicion se contradicen: lo mira una persona."""
    from operaciones import clasificacion_de_trabajo as clf

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=False, confianza="alta")
    _guardar_lo_leido(p, s)
    _las_puertas_abiertas(monkeypatch)

    assert pad.pasar_si_corresponde(
        org_a, s, p, ahora=timezone.now())["paso"] is False
    assert _en_la_cola(admin_client) == []


def test_sin_la_tarea_delegada_NO_entra_aunque_la_regla_lo_habilite(
        admin_client, org_a, monkeypatch):
    """
    LA PUERTA QUE UNA PERSONA ABRE. Sin ella, las reglas por si solas no
    mueven nada -- y subir el techo de autonomia para otra cosa no puede
    encender esto en silencio.
    """
    from operaciones import autonomia, clasificacion_de_trabajo as clf
    from operaciones import tareas_delegadas

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta")
    _guardar_lo_leido(p, s)
    monkeypatch.setattr(tareas_delegadas, "esta_delegada",
                        lambda o, clave: False)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": True, "motivo": ""})

    r = pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    assert r["paso"] is False
    assert "nadie le delego" in r["porque"]
    assert _en_la_cola(admin_client) == []


def test_sin_el_techo_de_la_empresa_NO_entra(admin_client, org_a, monkeypatch):
    from operaciones import autonomia, clasificacion_de_trabajo as clf
    from operaciones import tareas_delegadas

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta")
    _guardar_lo_leido(p, s)
    monkeypatch.setattr(tareas_delegadas, "esta_delegada",
                        lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede",
                        lambda o, nivel: {"puede": False,
                                          "motivo": "nivel 1 configurado"})

    r = pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    assert r["paso"] is False
    assert "no lo autoriza" in r["porque"]
    assert _en_la_cola(admin_client) == []


def test_si_NO_SE_PUEDE_LEER_el_techo_tampoco_entra(admin_client, org_a,
                                                    monkeypatch):
    """
    No poder COMPROBAR el permiso es lo mismo que no tenerlo. Es la misma
    regla que el interruptor de autonomia del motor ya fija: esa ruta falla
    CERRADO a proposito.
    """
    from operaciones import autonomia, clasificacion_de_trabajo as clf
    from operaciones import tareas_delegadas

    def _se_cayo(o, nivel):
        raise RuntimeError("la base no contesta")

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta")
    _guardar_lo_leido(p, s)
    monkeypatch.setattr(tareas_delegadas, "esta_delegada",
                        lambda o, clave: True)
    monkeypatch.setattr(autonomia, "puede", _se_cayo)

    #  'pasar_si_corresponde' no consulta el techo si se lo pasan ya resuelto,
    #  asi que aca se lo deja preguntar -- que es el camino que puede fallar.
    with pytest.raises(RuntimeError):
        autonomia.puede(org_a, 3)
    r = pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now(),
                                 autorizacion={"puede": False,
                                               "motivo": "no se pudo leer"})

    assert r["paso"] is False
    assert _en_la_cola(admin_client) == []


# =============================================================================
#  §3  EL LIMITE DE ALCANCE
# =============================================================================

def test_pasar_a_la_cola_NO_crea_la_orden_ni_asigna_a_nadie(admin_client,
                                                            org_a, monkeypatch):
    """
    EL LIMITE QUE DECIDIO EL CLIENTE el 14/10/2026, y lo que mantiene esto
    reversible: el caso entra a la cola y el despachador reparte.

    Si algun dia esto crea ordenes, esta prueba se pone en rojo y esa
    conversacion vuelve a tenerse con una persona, que es el punto.
    """
    from campo.models import OrdenTrabajo
    from operaciones import clasificacion_de_trabajo as clf

    caso = _caso_con_ticket(org_a)
    p = _propuesta_sin_decidir(org_a, caso)
    s = _Senal(caso.id, grupo=pad.FALLA_DE_SERVICIO, labor=clf.CORRECTIVO,
               verificada=True, confianza="alta")
    _guardar_lo_leido(p, s)
    _las_puertas_abiertas(monkeypatch)
    antes = OrdenTrabajo.objects.count()

    pad.pasar_si_corresponde(org_a, s, p, ahora=timezone.now())

    assert OrdenTrabajo.objects.count() == antes, (
        "se creo una orden de trabajo: eso manda una cuadrilla, y el alcance "
        "decidido era dejar el caso en la cola para que una persona reparta")
