# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR NO DECIDE SOBRE UNA FOTO QUE NADIE MIRO  --  09/11/2026
================================================================================
El usuario, despues de ver que una foto equivocada esperaba hasta el ciclo de
la hora siguiente:

    «pero la orden no puede esperar cierto tiempo para devolverse. El proceso
     correcto es que apenas el tecnico mande el reporte el supervisor revisa y
     si encuentra algo malo devolver el ticket en ese mismo momento, para que
     el tecnico no se mueva hacia otro ticket y tenga que devolverse»

LA CAUSA: DOS TAREAS EN LA COLA, SIN ORDEN GARANTIZADO
------------------------------------------------------
Subir una foto encola `analizar_evidencia`, que le habla al modelo de vision.
Mandar el reporte encola `revisar_el_cierre_ya`, que revisa y devuelve. Las
dos salen a la cola y nadie promete cual corre primero.

Cuando el cierre le gana al analisis, `inspeccion_visual.punto_de_la_revision`
se encuentra sin ninguna fila y hace `if not analisis: return None`. La foto
NO aparece como «no se pudo mirar»: no aparece. El veredicto se calcula sin
ella.

Y eso tenia dos consecuencias, la segunda peor que la primera:

  · la foto equivocada no se nombraba, asi que la devolucion automatica no
    pasaba hasta el ciclo horario -- lo que el usuario vio;
  · el punto de la inspeccion quedaba FUERA del veredicto, de modo que una
    orden con el checklist y la medicion en orden daba CERRAR. Con el cierre
    autonomo encendido, se cerraba sola sin haber mirado ninguna foto.

Es el mismo fallo que esta tarea ya habia tenido con la medicion de la senal
el 06/11 --«la aceleracion llegaba a una pieza que nadie habia acelerado»-- y
se arregla igual: mirando lo que falte en el mismo worker, antes de revisar.

QUE AFIRMA ESTA GUARDA
----------------------
  · que al llegar el reporte se MIREN las fotos que no tienen analisis
  · que la orden VUELVA EN EL MOMENTO cuando una de esas fotos muestra otra
    cosa -- el caso del usuario, de punta a punta y contra la base
  · que sin esa mirada el veredicto daba CERRAR: el hueco, medido
  · que la mirada vaya ANTES del cierre, que es donde esta el bug
  · que una foto YA analizada no se vuelva a mirar, ni en una devolucion:
    pagarle de nuevo al modelo por una foto que no cambio
  · que un fallo --de una foto o de todas-- no tumbe el cierre
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

FOTOS = ("medicion_al_llegar", "dano_encontrado", "medicion_al_salir")

#: Lo que `inspeccion_visual.analizar` devuelve. La forma es la del contrato
#: real (`{"estado","texto","motivo","modelo","segundos","tokens"}`): si fuera
#: otra, lo que se mida aca no diria nada de produccion.
def _visto(texto, motivo=""):
    return {"estado": "mirada" if texto else "", "texto": texto,
            "motivo": motivo, "modelo": "prueba", "segundos": 1, "tokens": 10}


@pytest.fixture
def abierto(org_a, admin_profile, monkeypatch):
    """LAS PUERTAS DEL CIERRE AUTONOMO, abiertas por el camino real.

    Y NO ES ANDAMIAJE DE ADORNO: la devolucion automatica sale por
    `cerrar_esta_orden`, que arranca con `puertas(org)`. Una empresa que no
    le delego al Supervisor que cierre tampoco recibe la devolucion
    automatica -- queda en modo sombra, que escribe un log y nada mas. La
    primera version de esta guarda no las abria y afirmaba sobre una orden
    que ninguna rama habia tocado.
    """
    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    td.delegar(org_a, td.CERRAR_LO_REVISADO, actor=admin_profile,
               pedido_textual="aprobá y cerrá lo que des por bueno")
    autonomia.cambiar(org_a, 3, actor=admin_profile,
                      motivo="cerrar lo revisado",
                      criterios="la revision del cierre en codigo")
    monkeypatch.setattr("operaciones.autonomia._interruptor_de",
                        lambda org: (True, ""))
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion",
                        lambda org_id: "tenant-de-prueba")
    return org_a


def _orden(org, numero, *, vuelta=1, con_reporte=True):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"mir{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": [
            {"id": f, "tipo": "foto", "titulo": f, "obligatorio": True}
            for f in FOTOS]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        #  `aplica()` exige LOS DOS estados. Sin `estado_validacion`,
        #  `revisar` devuelve None y toda afirmacion sobre el veredicto mide
        #  el vacio -- la leccion de la guarda del 08/11.
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={}, vuelta=vuelta)
    if con_reporte:
        #  EL REPORTE DE CIERRE, o el veredicto sale NO_CERRAR por otro
        #  camino y la rama que importa no se ejecuta.
        EventoTrabajo.objects.create(
            org=org, orden=orden, tipo="cierre_campo",
            datos={"vuelta": vuelta,
                   "respuestas": {"solucion": "se cambia conector APC",
                                  "servicio_validado": "Hecho"},
                   "sin_material_confirmado": True})
    return orden


def _foto(orden, requisito, vuelta, *, texto=None,
          estado=None):
    """Una evidencia. `texto=None` deja la foto SIN ANALISIS, que es el caso."""
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=vuelta,
        sha256=f"{requisito}{vuelta}{orden.numero}".ljust(64, "x")[:64],
        storage_key=f"k/{requisito}-v{vuelta}",
        nombre_original=f"{requisito}.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=(estado if estado is not None
                        else EvidenciaTrabajo.RECIBIDO))
    if texto:
        AnalisisDeEvidencia.objects.create(
            org=orden.org, evidencia=ev, vuelta=vuelta, texto=texto)
    return ev


def _analisis_de(orden):
    from campo.models import AnalisisDeEvidencia

    return list(AnalisisDeEvidencia.objects.filter(
        org=orden.org, evidencia__orden_trabajo=orden))


# ---------------------------------------------------------------------------
#  1) EL EFECTO: llega el reporte -> se miran las fotos que faltan
# ---------------------------------------------------------------------------

def test_al_llegar_el_reporte_SE_MIRAN_las_fotos_sin_analisis(org_a):
    from campo import tasks as T

    orden = _orden(org_a, 980)
    for f in FOTOS:
        _foto(orden, f, 1)                      # las tres SIN analisis

    assert _analisis_de(orden) == [], "el andamiaje ya traia analisis"

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("todo bien. MUESTRA: si")), \
         mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    return_value={"resultado": ""}):
        T.revisar_el_cierre_ya(str(org_a.id), str(orden.id))

    assert len(_analisis_de(orden)) == 3, \
        "el reporte llego y las fotos siguen sin mirarse"


def test_LA_ORDEN_VUELVE_EN_EL_MOMENTO_por_una_foto_equivocada(abierto, org_a):
    """EL CASO DEL USUARIO, de punta a punta.

    Una foto que muestra otra cosa, sin analisis todavia --porque el tecnico
    la subio y mando el reporte seguido--. Hasta hoy esto se iba en silencio
    y la devolucion esperaba al ciclo horario, con el tecnico ya en otro
    ticket.

    SE ENTRA POR LA TAREA, no por `atender_la_que_no_cierra`: el defecto
    vivia justo arriba de ella, en que el dato no existia cuando se la
    llamaba. Una guarda que entre por debajo pasa en verde con el bug vivo.
    """
    from campo import tasks as T
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 981)
    for f in FOTOS:
        _foto(orden, f, 1)
    antes = orden.vuelta

    def _mira(evidencia, *a, **k):
        if evidencia.requisito_id == "dano_encontrado":
            return _visto("un teclado de laptop. MUESTRA: no")
        return _visto("se ve el conector. MUESTRA: si")

    with mock.patch("campo.inspeccion_visual.analizar", side_effect=_mira), \
         mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, json=lambda: {"ok": True})
        T.revisar_el_cierre_ya(str(org_a.id), str(orden.id))

    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA, \
        "la foto equivocada no devolvio la orden en el momento"
    assert fresca.vuelta == antes + 1


def test_SIN_LAS_PUERTAS_ABIERTAS_no_devuelve_nada(org_a):
    """LA DEVOLUCION AUTOMATICA NO ES UNA PUERTA NUEVA.

    Sale por `cerrar_esta_orden`, que arranca con `puertas(org)`: una empresa
    que no le delego al Supervisor que cierre lo que da por bueno tampoco
    recibe la devolucion sola. Queda en modo sombra -- un log, y la orden
    intacta para que la mire una persona.

    Que las fotos SI se miren igual es a proposito: mirar no es decidir, y
    quien abra la pantalla encuentra el analisis hecho.
    """
    from campo import tasks as T
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 979)
    for f in FOTOS:
        _foto(orden, f, 1)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("un teclado. MUESTRA: no")), \
         mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, json=lambda: {"ok": True})
        T.revisar_el_cierre_ya(str(org_a.id), str(orden.id))

    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO, \
        "devolvio sola sin que la empresa se lo haya delegado"
    assert fresca.vuelta == orden.vuelta
    assert len(_analisis_de(orden)) == 3, "en sombra tampoco se miraron"


def test_SIN_la_mirada_el_veredicto_daba_CERRAR(org_a):
    """EL HUECO, MEDIDO. Es la razon por la que este cambio no es cosmetico.

    Con la foto equivocada subida pero sin analisis, `punto_de_la_revision`
    devuelve None --no «cuidado», None-- y el punto no entra al veredicto.
    Todo lo demas esta en orden, asi que la revision dice CERRAR: con el
    cierre autonomo encendido, la orden se cerraba sola con una foto que
    mostraba otra cosa.

    Esta guarda NO pasa por la tarea a proposito: afirma el estado del que se
    partia. Si algun dia `revisar` dejara de dar CERRAR sin analisis, este
    caso falla y hay que volver a leer si la mirada previa sigue hacia falta.
    """
    from campo.revision_del_cierre import CERRAR, revisar

    orden = _orden(org_a, 982)
    for f in FOTOS:
        _foto(orden, f, 1)                      # subidas, ninguna mirada

    revision = revisar(orden)

    assert revision["veredicto"] == CERRAR, revision["puntos"]


def test_la_mirada_va_ANTES_del_cierre(org_a):
    """EL ORDEN ES EL BUG. Mirar despues de decidir no sirve de nada."""
    from campo import tasks as T

    orden = mock.Mock(org_id=str(org_a.id), id="x", org=org_a)
    quien = []
    with mock.patch("campo.models.OrdenTrabajo.objects") as objs, \
         mock.patch("common.tasks.set_rls_context"), \
         mock.patch("common.tasks.clear_rls_context"), \
         mock.patch("operaciones.verificacion_de_arreglos.medir_este_arreglo"), \
         mock.patch("campo.tasks.mirar_las_que_faltan",
                    side_effect=lambda *a, **k: quien.append("mirar")), \
         mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    side_effect=lambda *a, **k: quien.append("cerrar")):
        objs.get.return_value = orden
        T.revisar_el_cierre_ya(str(org_a.id), "x")

    assert quien == ["mirar", "cerrar"], quien


# ---------------------------------------------------------------------------
#  2) NO SE LE PAGA DOS VECES AL MODELO
# ---------------------------------------------------------------------------

def test_una_foto_que_YA_tiene_analisis_no_se_vuelve_a_mirar(org_a):
    from campo import tasks as T

    orden = _orden(org_a, 983)
    _foto(orden, "medicion_al_llegar", 1, texto="ya mirada. MUESTRA: si")
    _foto(orden, "dano_encontrado", 1)
    _foto(orden, "medicion_al_salir", 1)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("bien. MUESTRA: si")) as analizar:
        T.mirar_las_que_faltan(orden)

    assert analizar.call_count == 2, \
        "se volvio a mirar --y a pagar-- una foto que ya tenia analisis"


def test_la_foto_de_una_vuelta_ANTERIOR_con_analisis_tampoco(org_a):
    """El caso de la devolucion.

    En una orden devuelta el tecnico rehace SOLO lo que se le pidio; las
    demas fotos siguen en la vuelta anterior, con su analisis ya escrito.
    Filtrar por `vuelta=orden.vuelta` las mandaria al modelo de nuevo en
    cada devolucion -- y es exactamente el filtro que ya habia causado que
    una devolucion pareciera borrar las fotos (08/11/2026).
    """
    from campo import tasks as T

    orden = _orden(org_a, 984, vuelta=2)
    _foto(orden, "medicion_al_llegar", 1, texto="mirada en la vuelta 1. MUESTRA: si")
    _foto(orden, "dano_encontrado", 1, texto="mirada en la vuelta 1. MUESTRA: si")
    _foto(orden, "medicion_al_salir", 2)        # la unica rehecha

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("bien. MUESTRA: si")) as analizar:
        r = T.mirar_las_que_faltan(orden)

    assert analizar.call_count == 1, \
        "una devolucion volvio a mandar al modelo fotos que no cambiaron"
    assert r == {"miradas": 1, "faltaban": 1}, r


def test_la_REHECHA_sin_analisis_se_mira_aunque_la_vieja_lo_tenga(org_a):
    """Lo inverso del caso anterior, que es el que importa de verdad: la foto
    nueva no puede quedar sin mirar porque la que reemplazo si estaba mirada.
    """
    from campo import tasks as T

    orden = _orden(org_a, 985, vuelta=2)
    _foto(orden, "dano_encontrado", 1, texto="la vieja, mirada. MUESTRA: no")
    rehecha = _foto(orden, "dano_encontrado", 2)
    _foto(orden, "medicion_al_llegar", 1, texto="mirada. MUESTRA: si")
    _foto(orden, "medicion_al_salir", 1, texto="mirada. MUESTRA: si")

    vistas = []
    with mock.patch("campo.inspeccion_visual.analizar",
                    side_effect=lambda ev, *a, **k: vistas.append(ev.id)
                    or _visto("ahora si. MUESTRA: si")):
        T.mirar_las_que_faltan(orden)

    assert vistas == [rehecha.id], vistas


def test_una_foto_VIEJA_reintentada_NO_tapa_a_la_rehecha(org_a):
    """LA VUELTA PESA PRIMERO, no la fecha de llegada.

    La app de campo encola las fotos y reintenta: una foto de la vuelta 1
    puede llegar al servidor DESPUES de la rehecha de la vuelta 2. Si el
    orden fuera por fecha, la vieja --que ya tiene analisis-- quedaria como
    «la ultima» y la rehecha se iria SIN MIRAR: justo la foto que el
    Supervisor ya habia rechazado una vez.

    Es la misma trampa que caza `test_f8` en la lista de evidencias, y por
    eso aca tambien se ordena por `vuelta` antes que por la llegada.
    """
    import datetime as dt

    from django.utils import timezone

    from campo import tasks as T
    from campo.models import EvidenciaTrabajo

    orden = _orden(org_a, 992, vuelta=2)
    rehecha = _foto(orden, "dano_encontrado", 2)
    vieja = _foto(orden, "dano_encontrado", 1, texto="la vieja, mirada. MUESTRA: no")
    #  LA VIEJA LLEGA DESPUES. Es un reintento de la app, no una foto nueva.
    EvidenciaTrabajo.objects.filter(pk=vieja.pk).update(
        recibida_en_servidor=timezone.now() + dt.timedelta(minutes=5))

    vistas = []
    with mock.patch("campo.inspeccion_visual.analizar",
                    side_effect=lambda ev, *a, **k: vistas.append(ev.id)
                    or _visto("ahora si. MUESTRA: si")):
        T.mirar_las_que_faltan(orden)

    assert vistas == [rehecha.id], \
        "un reintento de la foto vieja dejo la rehecha sin mirar"


def test_una_foto_que_NO_LLEGO_no_se_manda_al_modelo(org_a):
    """La app crea la fila antes de subir el archivo. Mandar al modelo una
    evidencia sin bytes es una llamada que solo puede fallar."""
    from campo import tasks as T
    from campo.models import EvidenciaTrabajo

    orden = _orden(org_a, 986)
    _foto(orden, "dano_encontrado", 1,
          estado=EvidenciaTrabajo.PENDIENTE)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("bien. MUESTRA: si")) as analizar:
        r = T.mirar_las_que_faltan(orden)

    assert analizar.call_count == 0, "se mando al modelo una foto que no llego"
    assert r == {"miradas": 0, "faltaban": 0}, r


# ---------------------------------------------------------------------------
#  3) FALLA CERRADO, Y NO TUMBA NADA
# ---------------------------------------------------------------------------

def test_si_UNA_foto_falla_las_demas_se_miran_igual(org_a):
    from campo import tasks as T

    orden = _orden(org_a, 987)
    for f in FOTOS:
        _foto(orden, f, 1)

    def _mira(evidencia, *a, **k):
        if evidencia.requisito_id == "dano_encontrado":
            raise RuntimeError("el proveedor no esta")
        return _visto("bien. MUESTRA: si")

    with mock.patch("campo.inspeccion_visual.analizar", side_effect=_mira):
        r = T.mirar_las_que_faltan(orden)

    assert r == {"miradas": 2, "faltaban": 3}, r
    assert len(_analisis_de(orden)) == 2


def test_si_la_mirada_FALLA_el_cierre_se_intenta_igual(org_a):
    """Mismo contrato que la medicion: es una aceleracion, no una puerta."""
    from campo import tasks as T

    orden = mock.Mock(org_id=str(org_a.id), id="x", org=org_a)
    with mock.patch("campo.models.OrdenTrabajo.objects") as objs, \
         mock.patch("common.tasks.set_rls_context"), \
         mock.patch("common.tasks.clear_rls_context"), \
         mock.patch("operaciones.verificacion_de_arreglos.medir_este_arreglo"), \
         mock.patch("campo.tasks.mirar_las_que_faltan",
                    side_effect=RuntimeError("se cayo todo")), \
         mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    return_value={"resultado": "cerrada"}) as cerrar:
        objs.get.return_value = orden
        r = T.revisar_el_cierre_ya(str(org_a.id), "x")

    assert cerrar.call_count == 1, "un fallo de la mirada tumbo el cierre"
    assert r["resultado"] == "cerrada"


def test_una_foto_que_el_modelo_NO_PUDO_mirar_deja_la_fila_y_NO_cierra(org_a):
    """FALLA CERRADO. El analisis sin texto es `sin_mirar` para el punto de la
    inspeccion, que entonces deja el veredicto en «no se sabe» -- y el cierre
    autonomo exige CERRAR. Lo contrario --no escribir fila-- es lo que hacia
    que la foto no existiera, que es el bug de arriba."""
    from campo import tasks as T
    from campo.revision_del_cierre import CERRAR, revisar

    orden = _orden(org_a, 988)
    for f in FOTOS:
        _foto(orden, f, 1)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("", motivo="el proveedor no contesto")):
        T.mirar_las_que_faltan(orden)

    assert len(_analisis_de(orden)) == 3
    assert revisar(orden)["veredicto"] != CERRAR, \
        "una orden cuyas fotos no se pudieron mirar se iba a cerrar sola"


def test_el_APAGADO_no_deja_fila(org_a):
    """La empresa que no tiene la inspeccion encendida no cambia de conducta.

    Si se escribiera fila, el punto veria «ninguna se pudo mirar», el
    veredicto pasaria a REVISAR y la funcion APAGADA --que es el default--
    frenaria el cierre autonomo en toda orden con evidencia. Ya paso una vez
    (31/10/2026, H1 del revisor de PII).
    """
    from campo import inspeccion_visual as IV
    from campo import tasks as T

    orden = _orden(org_a, 989)
    for f in FOTOS:
        _foto(orden, f, 1)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("", motivo=IV.MOTIVO_APAGADO)):
        T.mirar_las_que_faltan(orden)

    assert _analisis_de(orden) == [], \
        "la inspeccion apagada dejo rastro y frenaria el cierre autonomo"


def test_el_TOPE_corta_y_no_deja_la_tarea_colgada(org_a):
    from campo import tasks as T

    orden = _orden(org_a, 990)
    #  Mas requisitos que el tope. La plantilla no los declara y da igual:
    #  `mirar_las_que_faltan` mira lo que LLEGO, no lo que se pidio.
    for i in range(T.MAX_FOTOS_EN_EL_MOMENTO + 3):
        _foto(orden, f"foto_{i}", 1)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("bien. MUESTRA: si")) as analizar:
        r = T.mirar_las_que_faltan(orden)

    assert analizar.call_count == T.MAX_FOTOS_EN_EL_MOMENTO, analizar.call_count
    assert r == {"miradas": T.MAX_FOTOS_EN_EL_MOMENTO,
                 "faltaban": T.MAX_FOTOS_EN_EL_MOMENTO + 3}, r


# ---------------------------------------------------------------------------
#  4) LA TAREA POR FOTO SIGUE SIENDO LA MISMA
# ---------------------------------------------------------------------------

def test_la_tarea_por_foto_escribe_LO_MISMO_que_la_mirada_inmediata(org_a):
    """Las dos pasan por `_mirar_y_anotar`, y eso no es un detalle de estilo:
    si escribieran distinto, el veredicto dependeria de QUIEN miro la foto.
    """
    from campo import tasks as T

    orden = _orden(org_a, 991)
    por_tarea = _foto(orden, "medicion_al_llegar", 1)
    inmediata = _foto(orden, "dano_encontrado", 1)

    with mock.patch("campo.inspeccion_visual.analizar",
                    return_value=_visto("un conector APC. MUESTRA: si")):
        T.analizar_evidencia(str(org_a.id), str(por_tarea.id))
        T._mirar_y_anotar(inmediata)

    from campo.models import AnalisisDeEvidencia
    filas = {a.evidencia_id: a for a in AnalisisDeEvidencia.objects.filter(
        org=org_a, evidencia__orden_trabajo=orden)}
    a, b = filas[por_tarea.id], filas[inmediata.id]
    for campo in ("texto", "motivo", "pide_atencion", "modelo", "vuelta",
                  "origen"):
        assert getattr(a, campo) == getattr(b, campo), campo
