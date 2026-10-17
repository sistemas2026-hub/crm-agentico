# -*- coding: utf-8 -*-
"""
================================================================================
 LA LECTURA TIENE QUE LLEGAR A LA PROPUESTA
================================================================================

DE DONDE SALE
-------------
Medido en produccion la madrugada del 14/10/2026, y es el agujero que costo la
noche entera:

    50   lecturas registradas (razonamientos de 'lectura_ticket')
     3   propuestas que efectivamente tenian esa lectura
     0   propuestas cuya accion cambio

Todo lo de arriba funcionaba -- el worker, la cola, el detector, el modelo que
devolvia hipotesis y recomendacion-- y el trabajo se perdia en el ULTIMO paso.
Se pagaba la consulta al modelo y no quedaba nada.

POR QUE NINGUNA GUARDA LO VIO
------------------------------
Habia pruebas de cada pieza por separado: que 'diagnosticar' anota, que
'guardar_en_propuesta' guarda, que 'analizar' juzga. Ninguna recorria el camino
ENTERO -- '_leer_tickets_abiertos' de punta a punta, que es donde las piezas se
conectan y donde se rompia.

Es exactamente lo que CLAUDE.md llama "PARSEA != IMPORTA != FUNCIONA", una
vuelta mas arriba: cada parte pasaba y el conjunto no.

LO QUE AFIRMA
-------------
Que despues de una vuelta de lectura, la propuesta QUEDA con su evidencia y con
la accion que el Supervisor propuso. Sobre el efecto en la fila, no sobre que
se haya llamado a tal funcion.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db


HIPOTESIS = ("El servicio fue suspendido por deuda y el cliente pide la "
             "reconexión; el ticket está frenado en la validación del pago.")
RECOMENDACION = ("Derivar a cartera: confirmar si el pago de la reconexión se "
                 "acreditó y, si está, reactivar el servicio.")


class _Razonamiento:
    herramientas_usadas = ["consultar_ticket", "diagnosticar_servicio"]
    vueltas = 2
    agotado = False
    modelo = "un-modelo"
    proveedor = "un-proveedor"
    duracion_ms = 1200


class _Veredicto:
    """Un veredicto como el que devuelve el cerebro cuando todo sale bien."""

    concluyente = True
    riesgo = "informativo"
    confianza = "media"
    hipotesis = HIPOTESIS
    recomendacion = RECOMENDACION
    inferencias = []
    riesgos = []
    falta = []
    descartes = []
    razonamiento = _Razonamiento()

    def __init__(self):
        self.hechos = [{"fuente": "diagnosticar_servicio",
                        "dato": "el equipo responde y la señal es buena"}]


def _perfil(org):
    from common.models import Profile, User

    u = User.objects.create(email=f"t{uuid.uuid4().hex[:6]}@isp.test",
                            name="Tecnico", is_active=True)
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


@pytest.fixture(autouse=True)
def _tecnicos_de_soporte(monkeypatch):
    """
    Todo perfil de estas pruebas es de SOPORTE TECNICO.

    Desde el 14/10/2026 el detector solo mira los tickets del area del
    Supervisor, y el area sale de la persona asignada. Sin esto, estas pruebas
    --que hablan del GUARDADO de la lectura, no de las areas-- quedarian en
    cero por una razon que no es la suya.
    """
    from common.models import Profile
    from operaciones import areas_del_tenant as areas

    monkeypatch.setattr(
        areas, "area_por_persona",
        lambda: {str(p.id): areas.AREA_DEL_SUPERVISOR
                 for p in Profile.objects.all()})


def _caso_con_tecnico(org):
    from cases.models import Case

    ahora = timezone.now()
    c = Case.objects.create(
        org=org, name="Reconexion", status="Assigned", priority="Normal",
        provider="wisphub", external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="1696", external_status="Nuevo",
        external_fetched_at=ahora,
        description="El cliente pide la reconexion, ya pago el costo indicado.")
    Case.objects.filter(pk=c.pk).update(
        created_at=ahora - timezone.timedelta(days=6))
    c.assigned_to.add(_perfil(org))
    c.refresh_from_db()
    return c


def _propuesta_sin_leer(org, caso):
    """Como la deja el ciclo ANTES de leer: con la frase generica."""
    ahora = timezone.now()
    return PropuestaSupervisor.objects.create(
        org=org, tipo_senal=PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
        origen_tipo="case", origen_id=str(caso.id),
        accion_propuesta="Decidir qué se hace con este ticket, que sigue abierto",
        motivo="El ticket sigue abierto en WispHub hace 6 días.",
        evidencia=[{"fuente": "cases.Case", "id": str(caso.id),
                    "dato": "abierto hace 6 dias",
                    "observado_en": ahora.isoformat()}],
        prioridad=40, impacto="Tiempo que corre sin decisión",
        huella_condicion="h-" + uuid.uuid4().hex[:8],
        expira_en=ahora + timezone.timedelta(days=7))


def test_despues_de_leer_la_propuesta_QUEDA_con_la_lectura(org_a, monkeypatch):
    """
    EL CAMINO COMPLETO, que es donde se rompia.

    Se corre '_leer_tickets_abiertos' tal cual lo llama el ciclo, con el modelo
    reemplazado -- lo unico que no puede ir a producción desde una prueba.
    """
    from operaciones import cerebro, diagnostico_de_ticket as dxt

    caso = _caso_con_tecnico(org_a)
    p = _propuesta_sin_leer(org_a, caso)
    monkeypatch.setattr(cerebro, "concluir",
                        lambda org, **kw: _Veredicto())

    informe = sup._leer_tickets_abiertos(org_a, timezone.now())

    p.refresh_from_db()
    lecturas = [x for x in (p.evidencia or [])
                if isinstance(x, dict) and x.get("fuente") == dxt.FUENTE]

    assert informe.get("tickets", {}).get("leidos", 0) >= 1, (
        f"no se leyo ningun ticket habiendo uno listo: {informe}")
    assert lecturas, (
        "se leyo el ticket y la propuesta quedo SIN la lectura: es el agujero "
        "medido el 14/10/2026 -- 50 lecturas, 3 propuestas con su pieza")
    assert HIPOTESIS[:30] in str(lecturas[0].get("dato")), (
        "la pieza guardada no trae lo que el Supervisor concluyo")


def test_y_la_accion_propuesta_pasa_a_ser_la_del_Supervisor(org_a, monkeypatch):
    """
    Lo que el cliente miro y dijo "para mi eso no es una propuesta".

    Si la lectura llega pero la accion no se actualiza, la pantalla sigue
    diciendo "Decidir qué se hace con este ticket" con el diagnostico completo
    tres bloques mas abajo.
    """
    from operaciones import cerebro

    caso = _caso_con_tecnico(org_a)
    p = _propuesta_sin_leer(org_a, caso)
    monkeypatch.setattr(cerebro, "concluir", lambda org, **kw: _Veredicto())

    sup._leer_tickets_abiertos(org_a, timezone.now())

    p.refresh_from_db()
    assert not p.accion_propuesta.startswith("Decidir qué se hace"), (
        f"la accion sigue siendo la generica: {p.accion_propuesta!r}")
    assert "cartera" in p.accion_propuesta.lower(), (
        f"no es lo que el Supervisor propuso: {p.accion_propuesta!r}")


def test_el_informe_dice_cuantas_se_guardaron(org_a, monkeypatch):
    """
    El numero que faltaba para no tener que deducir. Sin el, 'se leyo y no
    quedo' es invisible: el informe decia 'leidos: 10' y nadie podia saber que
    de esos diez no se guardo ninguno.
    """
    from operaciones import cerebro

    caso = _caso_con_tecnico(org_a)
    _propuesta_sin_leer(org_a, caso)
    monkeypatch.setattr(cerebro, "concluir", lambda org, **kw: _Veredicto())

    informe = sup._leer_tickets_abiertos(org_a, timezone.now())

    assert informe.get("guardadas", 0) >= 1, (
        f"el informe no cuenta las guardadas: {informe}")


def test_si_el_modelo_agota_sus_vueltas_la_lectura_igual_cierra(org_a,
                                                                monkeypatch):
    """
    EL CAMINO COMPLETO DEL 17/10/2026: el modelo pide herramientas en todas
    sus vueltas. Antes la lectura terminaba sin grupo -- 9 de 64 pendientes,
    tres relecturas cada una. Ahora se le pide el cierre sin herramientas, y
    lo que conteste llega a la propuesta.

    Se reemplaza SOLO el modelo: la lectura, 'concluir', el bucle y 'validar'
    corren de verdad. La herramienta pedida no existe en el catalogo, asi que
    no sale nada a la red.
    """
    import json

    from operaciones import cerebro
    from operaciones import paso_a_despacho as pad

    caso = _caso_con_tecnico(org_a)
    p = _propuesta_sin_leer(org_a, caso)
    cierre = {"contenido": json.dumps({
        "hechos": [], "inferencias": [], "riesgos": [], "falta": [],
        "riesgo": "informativo", "confianza": "media",
        "hipotesis": HIPOTESIS, "recomendacion": RECOMENDACION,
        "grupo": "trabajo_pedido", "confianza_del_grupo": "alta"})}
    llamadas = []

    def _modelo(mensajes, tools):
        llamadas.append(list(tools))
        if tools:
            return {"contenido": "", "llamadas": [{"nombre": "no_existe",
                                                   "argumentos": {}}]}
        return cierre

    monkeypatch.setattr(cerebro, "_pedirle_al_modelo", _modelo)

    sup._leer_tickets_abiertos(org_a, timezone.now())

    assert llamadas and llamadas[-1] == [], "no se pidio el cierre sin herramientas"
    p.refresh_from_db()
    #  El grupo se busca como lo busca el paso: la lectura deja varias piezas
    #  (la hipotesis, lo que falta) y el grupo no va necesariamente en la ultima.
    lectura = pad._ultima_lectura_con_grupo(p)
    assert lectura and lectura.get("grupo") == "trabajo_pedido", (
        "el modelo cerro con un grupo y la propuesta no lo tiene")
    assert HIPOTESIS[:30] in str(lectura.get("dato")), (
        "la hipotesis del cierre no llego a la propuesta")
