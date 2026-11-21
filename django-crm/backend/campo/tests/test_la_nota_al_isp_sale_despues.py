"""La nota al ISP sale DESPUES de contestarle al tecnico  --  21/11/2026.

EL ERROR QUE LO ORIGINO
-----------------------
El usuario: «demoran en llegar los reportes del tecnico que manda por app», y
en el telefono «10 cambios necesitan que alguien los revise».

Marcar "en camino", "llegada" y mandar el reporte le escribian al ISP DENTRO
de la peticion del tecnico, y esa llamada espera hasta 45 s. La app espera 20.
Con el ISP lento la app se rendia, reintentaba con la misma clave, recibia 409
«en curso» y dejaba el cambio como conflicto, aunque estaba aplicado.

QUE SE AFIRMA ACA
-----------------
El EFECTO, no la presencia del mecanismo:

  - la peticion del tecnico contesta SIN haberle hablado a nadie de afuera;
  - la nota igual se escribe, por la tarea;
  - las notas de una misma orden salen EN ORDEN aunque las tareas arranquen
    desordenadas, y el cierre no le gana al reporte;
  - lo que llega tarde no se escribe, y queda dicho;
  - nada de esto puede dejar una nota esperando para siempre.
"""
from __future__ import annotations

import time
from unittest import mock

import pytest
from celery.exceptions import Retry
from django.core.cache import cache

from campo import tasks
from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services import nota_al_isp

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
#  Lo que hace falta para armar el caso
# ---------------------------------------------------------------------------

class _Respuesta:
    """Lo que el motor contesta cuando anota."""

    status_code = 200
    content = b"{}"

    def __init__(self, cuerpo=None):
        self._cuerpo = cuerpo or {"anotada": True, "codigo": "anotada"}

    def json(self):
        return self._cuerpo


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    """Una empresa con motor, y una cache limpia entre casos.

    La cache de pruebas es de proceso (LocMem) y vive entre casos: una marca
    que dejara un caso haria esperar al siguiente por un motivo que no es el
    suyo.
    """
    cache.clear()
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de",
                        lambda org_id: "tenant-de-prueba")
    monkeypatch.delenv(nota_al_isp.BANDERA, raising=False)
    monkeypatch.delenv(nota_al_isp.BANDERA_DEL_CIERRE, raising=False)
    yield
    cache.clear()


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="corr_nota",
                                 nombre="Correctivo", labor="correctivo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})


def _orden(org, version, profile, numero=901, *,
           estado=OrdenTrabajo.ASIGNADA, con_ticket=True):
    o = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE", estado_operativo=estado,
        contexto=({"ticket": {"numero": "97913", "proveedor": "wisphub"}}
                  if con_ticket else {}))
    AsignacionTrabajo.objects.create(orden=o, profile=profile,
                                     rol="tecnico", es_principal=True)
    return o


def _correr(orden, momento, profile=None, vuelta=1):
    """La tarea, como la correria el worker."""
    return tasks.anotar_en_el_isp(
        str(orden.org_id), str(orden.id), momento, vuelta,
        str(profile.pk) if profile is not None else "")


def _momentos_enviados(post) -> list:
    return [c.kwargs["json"]["momento"] for c in post.call_args_list]


def _eventos(orden, tipo) -> list:
    return [e.datos for e in EventoTrabajo.objects.filter(orden=orden,
                                                          tipo=tipo)]


# ---------------------------------------------------------------------------
#  1) LA PETICION DEL TECNICO NO ESPERA AL ISP
# ---------------------------------------------------------------------------

def test_marcar_EN_CAMINO_contesta_sin_hablarle_al_isp(
        user_client, org_a, user_profile, version,
        django_capture_on_commit_callbacks):
    """El sintoma, medido en su origen.

    `requests.post` es por donde sale la nota. Si la vista lo llama, el
    tecnico esta esperando a WispHub: eso es exactamente lo que se quito.
    """
    orden = _orden(org_a, version, user_profile)

    with mock.patch("requests.post") as post, \
            mock.patch.object(tasks.anotar_en_el_isp, "delay") as encolar, \
            django_capture_on_commit_callbacks(execute=True):
        r = user_client.post(f"/api/campo/trabajos/{orden.id}/acciones/",
                             {"accion": "marcar_en_camino"}, format="json")

    assert r.status_code == 200, r.content
    assert post.call_count == 0, \
        "la peticion del tecnico le hablo al ISP antes de contestar"
    #  Y no es que la nota se haya perdido: quedo pedida, con lo que la
    #  tarea necesita para escribirla.
    encolar.assert_called_once_with(
        str(org_a.id), str(orden.id), nota_al_isp.EN_CAMINO, 1,
        str(user_profile.pk))


def test_mandar_el_REPORTE_contesta_sin_hablarle_al_isp(
        user_client, org_a, user_profile, version,
        django_capture_on_commit_callbacks):
    orden = _orden(org_a, version, user_profile, 902,
                   estado=OrdenTrabajo.EN_SITIO)

    with mock.patch("requests.post") as post, \
            mock.patch.object(tasks.anotar_en_el_isp, "delay") as encolar, \
            mock.patch.object(tasks.revisar_el_cierre_ya, "delay"), \
            django_capture_on_commit_callbacks(execute=True):
        r = user_client.post(f"/api/campo/trabajos/{orden.id}/completar/",
                             {}, format="json")

    assert r.status_code == 200, r.content
    assert post.call_count == 0, \
        "mandar el reporte le hablo al ISP antes de contestar"
    encolar.assert_called_once_with(
        str(org_a.id), str(orden.id), nota_al_isp.REPORTE_DEL_TECNICO, 1,
        str(user_profile.pk))


def test_el_reporte_se_pide_ANTES_que_la_revision(
        user_client, org_a, user_profile, version,
        django_capture_on_commit_callbacks):
    """El orden en la vista no es estetica.

    Pedir la nota deja la marca que la revision mira para no cerrar el ticket
    antes de que el reporte llegue. Si la revision se encolara primero,
    podria arrancar sin verla.
    """
    orden = _orden(org_a, version, user_profile, 903,
                   estado=OrdenTrabajo.EN_SITIO)
    llegaron = []

    with mock.patch("requests.post"), \
            mock.patch.object(
                tasks.anotar_en_el_isp, "delay",
                side_effect=lambda *a, **k: llegaron.append("nota")), \
            mock.patch.object(
                tasks.revisar_el_cierre_ya, "delay",
                side_effect=lambda *a, **k: llegaron.append("revision")), \
            django_capture_on_commit_callbacks(execute=True):
        r = user_client.post(f"/api/campo/trabajos/{orden.id}/completar/",
                             {}, format="json")

    assert r.status_code == 200, r.content
    assert llegaron == ["nota", "revision"], llegaron


# ---------------------------------------------------------------------------
#  2) LA NOTA IGUAL SE ESCRIBE
# ---------------------------------------------------------------------------

def test_la_tarea_ESCRIBE_la_nota_del_avance(org_a, user_profile, version):
    orden = _orden(org_a, version, user_profile, 910,
                   estado=OrdenTrabajo.EN_CAMINO)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        salida = _correr(orden, nota_al_isp.EN_CAMINO, user_profile)

    assert salida.get("anotada") is True, salida
    assert post.call_count == 1
    assert "anotar-en-el-ticket" in post.call_args.args[0]
    cuerpo = post.call_args.kwargs["json"]
    assert cuerpo["momento"] == nota_al_isp.EN_CAMINO
    assert cuerpo["ticket"] == "97913"
    assert cuerpo["vuelta"] == 1
    #  Y el rastro en la orden, que es lo que mira quien pregunta si el ISP
    #  se entero.
    assert [d["momento"] for d in _eventos(orden, nota_al_isp.EVENTO_ANOTADA)] \
        == [nota_al_isp.EN_CAMINO]


def test_la_tarea_ESCRIBE_el_reporte(org_a, user_profile, version):
    orden = _orden(org_a, version, user_profile, 911,
                   estado=OrdenTrabajo.COMPLETADA_CAMPO)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        salida = _correr(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile)

    assert salida.get("anotada") is True, salida
    cuerpo = post.call_args.kwargs["json"]
    assert cuerpo["momento"] == nota_al_isp.REPORTE_DEL_TECNICO
    assert "OT #911" in cuerpo["texto"]
    assert "fotos" in cuerpo, "el reporte dejo de llevar las fotos"


def test_no_se_pide_lo_que_NO_VA_A_SALIR(org_a, user_profile, version):
    """Una orden que no nacio de un ticket del ISP no encola nada."""
    orden = _orden(org_a, version, user_profile, 912, con_ticket=False)

    with mock.patch.object(tasks.anotar_en_el_isp, "delay") as encolar:
        pedida = tasks.pedir_nota_al_isp(orden, nota_al_isp.EN_CAMINO,
                                         user_profile)

    assert pedida is False
    assert encolar.call_count == 0
    assert tasks._notas_en_vuelo(orden.id) == [], \
        "quedo una marca de una nota que nadie va a escribir"


def test_con_la_nota_APAGADA_tampoco_se_pide(org_a, user_profile, version,
                                             monkeypatch):
    orden = _orden(org_a, version, user_profile, 913)
    monkeypatch.setenv(nota_al_isp.BANDERA, "0")

    with mock.patch.object(tasks.anotar_en_el_isp, "delay") as encolar:
        assert tasks.pedir_nota_al_isp(orden, nota_al_isp.EN_CAMINO) is False
    assert encolar.call_count == 0


# ---------------------------------------------------------------------------
#  3) EL ORDEN
# ---------------------------------------------------------------------------

def _pedir(orden, momento, profile, capturar):
    """Pide la nota como lo hace la vista, sin correr la tarea."""
    with mock.patch.object(tasks.anotar_en_el_isp, "delay"), \
            capturar(execute=True):
        assert tasks.pedir_nota_al_isp(orden, momento, profile) is True


def test_la_LLEGADA_espera_a_que_salga_el_EN_CAMINO(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    """El telefono que estuvo sin senal manda las dos en el mismo segundo.

    Un worker corre varias tareas a la vez, y la de la llegada puede arrancar
    primero. No escribe: se reprograma. Recien cuando la de "en camino"
    termino, sale.
    """
    orden = _orden(org_a, version, user_profile, 920,
                   estado=OrdenTrabajo.EN_SITIO)
    _pedir(orden, nota_al_isp.EN_CAMINO, user_profile,
           django_capture_on_commit_callbacks)
    _pedir(orden, nota_al_isp.EN_SITIO, user_profile,
           django_capture_on_commit_callbacks)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        #  La llegada arranca primero.
        with pytest.raises(Retry):
            _correr(orden, nota_al_isp.EN_SITIO, user_profile)
        assert post.call_count == 0, \
            "la llegada se escribio antes que el «en camino»"

        _correr(orden, nota_al_isp.EN_CAMINO, user_profile)
        _correr(orden, nota_al_isp.EN_SITIO, user_profile)

    assert _momentos_enviados(post) == [nota_al_isp.EN_CAMINO,
                                        nota_al_isp.EN_SITIO]


def test_el_REPORTE_espera_a_los_dos_avances(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    orden = _orden(org_a, version, user_profile, 921,
                   estado=OrdenTrabajo.COMPLETADA_CAMPO)
    for m in (nota_al_isp.EN_CAMINO, nota_al_isp.EN_SITIO,
              nota_al_isp.REPORTE_DEL_TECNICO):
        _pedir(orden, m, user_profile, django_capture_on_commit_callbacks)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        with pytest.raises(Retry):
            _correr(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile)
        _correr(orden, nota_al_isp.EN_CAMINO, user_profile)
        #  Falta la llegada: el reporte sigue esperando.
        with pytest.raises(Retry):
            _correr(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile)
        _correr(orden, nota_al_isp.EN_SITIO, user_profile)
        _correr(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile)

    assert _momentos_enviados(post) == [nota_al_isp.EN_CAMINO,
                                        nota_al_isp.EN_SITIO,
                                        nota_al_isp.REPORTE_DEL_TECNICO]


def test_el_EN_CAMINO_no_espera_a_nadie(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    """Lo de adelante no espera a lo de atras: si no, se trabarian entre si."""
    orden = _orden(org_a, version, user_profile, 922,
                   estado=OrdenTrabajo.EN_SITIO)
    _pedir(orden, nota_al_isp.EN_CAMINO, user_profile,
           django_capture_on_commit_callbacks)
    _pedir(orden, nota_al_isp.EN_SITIO, user_profile,
           django_capture_on_commit_callbacks)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        _correr(orden, nota_al_isp.EN_CAMINO, user_profile)

    assert _momentos_enviados(post) == [nota_al_isp.EN_CAMINO]


def test_las_notas_de_OTRA_orden_no_hacen_esperar(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    una = _orden(org_a, version, user_profile, 923,
                 estado=OrdenTrabajo.EN_SITIO)
    otra = _orden(org_a, version, user_profile, 924,
                  estado=OrdenTrabajo.EN_SITIO)
    _pedir(una, nota_al_isp.EN_CAMINO, user_profile,
           django_capture_on_commit_callbacks)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        _correr(otra, nota_al_isp.EN_SITIO, user_profile)

    assert post.call_count == 1


def test_el_CIERRE_no_le_gana_al_reporte(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    """Cada nota deja el ticket En Progreso.

    Si el Supervisor cerrara el ticket antes de que el reporte del tecnico
    llegue, el reporte lo reabriria. La revision se reprograma mientras haya
    una nota de esa orden en vuelo, y NO llega a cerrar.
    """
    orden = _orden(org_a, version, user_profile, 930,
                   estado=OrdenTrabajo.COMPLETADA_CAMPO)
    _pedir(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile,
           django_capture_on_commit_callbacks)

    with mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    return_value={"resultado": "cerrada"}) as cerrar, \
            mock.patch("operaciones.verificacion_de_arreglos."
                       "medir_este_arreglo"), \
            mock.patch("requests.post", return_value=_Respuesta()):
        with pytest.raises(Retry):
            tasks.revisar_el_cierre_ya(str(org_a.id), str(orden.id))
        assert cerrar.call_count == 0, \
            "el cierre corrio con el reporte todavia en vuelo"

        _correr(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile)
        tasks.revisar_el_cierre_ya(str(org_a.id), str(orden.id))

    assert cerrar.call_count == 1


# ---------------------------------------------------------------------------
#  4) NADA QUEDA ESPERANDO PARA SIEMPRE
# ---------------------------------------------------------------------------

def test_si_la_nota_FALLA_la_siguiente_no_queda_trabada(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    """El ISP caido no puede dejar la marca puesta."""
    orden = _orden(org_a, version, user_profile, 940,
                   estado=OrdenTrabajo.EN_SITIO)
    _pedir(orden, nota_al_isp.EN_CAMINO, user_profile,
           django_capture_on_commit_callbacks)
    _pedir(orden, nota_al_isp.EN_SITIO, user_profile,
           django_capture_on_commit_callbacks)

    with mock.patch("requests.post", side_effect=RuntimeError("caido")):
        salida = _correr(orden, nota_al_isp.EN_CAMINO, user_profile)
    assert not salida.get("anotada")

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        _correr(orden, nota_al_isp.EN_SITIO, user_profile)
    assert _momentos_enviados(post) == [nota_al_isp.EN_SITIO]


def test_si_la_tarea_REVIENTA_la_marca_se_suelta_igual(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    orden = _orden(org_a, version, user_profile, 941,
                   estado=OrdenTrabajo.EN_SITIO)
    _pedir(orden, nota_al_isp.EN_CAMINO, user_profile,
           django_capture_on_commit_callbacks)

    with mock.patch.object(nota_al_isp, "anotar_avance",
                           side_effect=RuntimeError("algo que nadie previo")):
        salida = _correr(orden, nota_al_isp.EN_CAMINO, user_profile)

    assert salida["codigo"] == "fallo", salida
    assert tasks._notas_en_vuelo(orden.id) == []


def test_la_marca_VENCE_SOLA(org_a, user_profile, version, monkeypatch,
                             django_capture_on_commit_callbacks):
    """Una tarea que se perdio no deja a las demas esperando para siempre."""
    orden = _orden(org_a, version, user_profile, 942,
                   estado=OrdenTrabajo.EN_SITIO)
    monkeypatch.setattr(tasks, "VIDA_DE_LA_MARCA", 1)
    _pedir(orden, nota_al_isp.EN_CAMINO, user_profile,
           django_capture_on_commit_callbacks)
    assert tasks._notas_en_vuelo(orden.id) == [nota_al_isp.EN_CAMINO]

    time.sleep(1.2)

    #  La tarea del "en camino" nunca corrio, y la llegada sale igual.
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        _correr(orden, nota_al_isp.EN_SITIO, user_profile)
    assert _momentos_enviados(post) == [nota_al_isp.EN_SITIO]


def test_despues_del_TOPE_sale_igual():
    """Aunque la marca siguiera viva, se espera un numero acotado de veces."""
    class _Tarea:
        class request:
            retries = 0

    cache.set(tasks._marca_de_nota("orden-x", nota_al_isp.EN_CAMINO), 1, 60)

    _Tarea.request.retries = tasks.TOPE_DE_ESPERAS - 1
    assert tasks._hay_que_esperar_a_las_notas(
        _Tarea, "orden-x", antes_de=nota_al_isp.EN_SITIO) is True
    _Tarea.request.retries = tasks.TOPE_DE_ESPERAS
    assert tasks._hay_que_esperar_a_las_notas(
        _Tarea, "orden-x", antes_de=nota_al_isp.EN_SITIO) is False


#  EN UN WORKER, NO EN UNA LLAMADA DIRECTA  --  auditoria del 21/11/2026
#
#  Los casos de arriba llaman la tarea como funcion, y ahi `self.retry`
#  levanta `Retry` sin mirar nada mas. Con eso estaban en verde mientras en un
#  worker real la tarea esperaba 9 s y MORIA: `self.retry(max_retries=None)`
#  no significa «sin tope», significa «usa el de la tarea», que es 3. El
#  auditor lo midio: corrio 4 veces y termino en MaxRetriesExceededError, sin
#  escribir la nota y sin rastro.
#
#  `.apply()` recorre el camino del worker: lleva la cuenta de reintentos,
#  aplica el tope de Celery y vuelve a correr la tarea. El tope propio se baja
#  a 6 --por encima del 3 de Celery, que es lo que hay que cruzar-- para no
#  anidar sesenta llamadas.

@pytest.fixture
def como_en_el_worker(monkeypatch):
    """Deja correr `.apply()` dentro de la transaccion de la prueba.

    `crm/celery.py` cierra las conexiones viejas antes y despues de cada
    tarea, que en un worker es lo correcto. Aca la conexion ES la transaccion
    de la prueba: cerrarla la corta, y la tarea fallaria por el arnes y no
    por lo que se mide.
    """
    monkeypatch.setattr("django.db.close_old_connections", lambda: None)
    monkeypatch.setattr(tasks, "TOPE_DE_ESPERAS", 6)


def test_en_un_worker_la_nota_TERMINA_SALIENDO_aunque_nadie_suelte_la_marca(
        org_a, user_profile, version, como_en_el_worker):
    """La tarea de adelante se perdio. La de atras espera su tope y escribe."""
    orden = _orden(org_a, version, user_profile, 945,
                   estado=OrdenTrabajo.EN_SITIO)
    cache.set(tasks._marca_de_nota(str(orden.id), nota_al_isp.EN_CAMINO), 1, 600)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        tasks.anotar_en_el_isp.apply(args=[
            str(org_a.id), str(orden.id), nota_al_isp.EN_SITIO, 1,
            str(user_profile.pk)])

    assert _momentos_enviados(post) == [nota_al_isp.EN_SITIO], \
        "la nota se quedo sin salir: la tarea murio esperando"


def test_en_un_worker_el_CIERRE_termina_corriendo_aunque_nadie_suelte_la_marca(
        org_a, user_profile, version, como_en_el_worker):
    """Lo mismo para la revision: esperar al reporte no puede matarla.

    Era una regresion de algo que funcionaba: el cierre inmediato existe
    desde el 31/10, y con el reporte tardando mas de 9 s en escribirse la
    tarea moria y la orden quedaba para el ciclo de cada hora.
    """
    orden = _orden(org_a, version, user_profile, 946,
                   estado=OrdenTrabajo.COMPLETADA_CAMPO)
    cache.set(tasks._marca_de_nota(str(orden.id),
                                   nota_al_isp.REPORTE_DEL_TECNICO), 1, 600)

    with mock.patch("campo.cierre_por_el_supervisor.cerrar_esta_orden",
                    return_value={"resultado": "cerrada"}) as cerrar, \
            mock.patch("operaciones.verificacion_de_arreglos."
                       "medir_este_arreglo"), \
            mock.patch("requests.post", return_value=_Respuesta()):
        tasks.revisar_el_cierre_ya.apply(args=[str(org_a.id), str(orden.id)])

    assert cerrar.call_count == 1, \
        "la revision nunca corrio: la tarea murio esperando al reporte"


def test_en_un_worker_ESPERA_las_veces_del_tope_y_no_menos(
        org_a, user_profile, version, como_en_el_worker, monkeypatch):
    """Y espera de verdad: no sale al primer intento con la marca viva."""
    orden = _orden(org_a, version, user_profile, 947,
                   estado=OrdenTrabajo.EN_SITIO)
    cache.set(tasks._marca_de_nota(str(orden.id), nota_al_isp.EN_CAMINO), 1, 600)
    preguntas = []
    real = tasks._notas_en_vuelo

    def _contar(*a, **k):
        preguntas.append(1)
        return real(*a, **k)

    monkeypatch.setattr(tasks, "_notas_en_vuelo", _contar)
    with mock.patch("requests.post", return_value=_Respuesta()):
        tasks.anotar_en_el_isp.apply(args=[
            str(org_a.id), str(orden.id), nota_al_isp.EN_SITIO, 1,
            str(user_profile.pk)])

    #  Intentos 0 a 5 preguntan y esperan; el 6 ya no pregunta: sale.
    assert len(preguntas) == 6, preguntas


def test_si_la_CACHE_no_contesta_la_nota_sale(org_a, user_profile, version):
    """No saber si hay algo en vuelo no puede dejar una nota sin salir."""
    orden = _orden(org_a, version, user_profile, 943,
                   estado=OrdenTrabajo.EN_SITIO)

    with mock.patch("django.core.cache.cache.get_many",
                    side_effect=RuntimeError("redis caido")), \
            mock.patch("django.core.cache.cache.set",
                       side_effect=RuntimeError("redis caido")), \
            mock.patch("django.core.cache.cache.delete",
                       side_effect=RuntimeError("redis caido")), \
            mock.patch("requests.post", return_value=_Respuesta()) as post:
        salida = _correr(orden, nota_al_isp.EN_SITIO, user_profile)

    assert salida.get("anotada") is True, salida
    assert post.call_count == 1


def test_SIN_COLA_no_revienta_y_queda_dicho(
        org_a, user_profile, version, django_capture_on_commit_callbacks):
    """Sin broker la nota no sale. Lo que no puede pasar es que no se sepa."""
    orden = _orden(org_a, version, user_profile, 944,
                   estado=OrdenTrabajo.EN_CAMINO)

    with mock.patch.object(tasks.anotar_en_el_isp, "delay",
                           side_effect=RuntimeError("sin broker")), \
            mock.patch("requests.post") as post, \
            django_capture_on_commit_callbacks(execute=True):
        tasks.pedir_nota_al_isp(orden, nota_al_isp.EN_CAMINO, user_profile)

    assert post.call_count == 0, \
        "sin cola se volvio a esperar al ISP dentro de la peticion"
    no = _eventos(orden, nota_al_isp.EVENTO_NO_ANOTADA)
    assert [d["codigo"] for d in no] == ["sin_cola"], no
    assert tasks._notas_en_vuelo(orden.id) == [], \
        "quedo la marca de una nota que nadie va a escribir"


# ---------------------------------------------------------------------------
#  5) LO QUE LLEGA TARDE NO SE ESCRIBE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("estado", [OrdenTrabajo.CERRADA,
                                    OrdenTrabajo.CANCELADA])
def test_una_nota_NO_reabre_un_ticket_que_ya_cerro(org_a, user_profile,
                                                   version, estado):
    orden = _orden(org_a, version, user_profile, 950, estado=estado)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        salida = _correr(orden, nota_al_isp.EN_CAMINO, user_profile)

    assert post.call_count == 0, \
        "se escribio una nota sobre una orden que ya termino"
    assert salida["codigo"] == "llego_tarde", salida
    no = _eventos(orden, nota_al_isp.EVENTO_NO_ANOTADA)
    assert [d["codigo"] for d in no] == ["llego_tarde"], no


def test_una_nota_de_OTRA_VUELTA_no_se_escribe(org_a, user_profile, version):
    """Se pidio en la vuelta 1; el Supervisor la devolvio y ya va por la 2."""
    orden = _orden(org_a, version, user_profile, 951,
                   estado=OrdenTrabajo.EN_SITIO)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=2)

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        salida = _correr(orden, nota_al_isp.EN_CAMINO, user_profile, vuelta=1)

    assert post.call_count == 0
    assert salida["codigo"] == "llego_tarde", salida


def test_una_nota_NO_reabre_un_ticket_cerrado_con_la_orden_TODAVIA_ABIERTA(
        org_a, user_profile, version):
    """El hueco que encontro la auditoria del 21/11/2026.

    Aprobar a mano cierra el ticket del ISP y deja la orden en
    `completada_campo` hasta el paso siguiente. Mirar solo el estado de la
    orden dejaba pasar la nota por ahi, y reabria el ticket. Lo que dice si
    el ticket cerro es su evento.
    """
    from campo.services import cierre_en_isp

    orden = _orden(org_a, version, user_profile, 953,
                   estado=OrdenTrabajo.COMPLETADA_CAMPO)
    EventoTrabajo.objects.create(org=org_a, orden=orden,
                                 tipo=cierre_en_isp.EVENTO_CERRADO,
                                 profile=user_profile, datos={})

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        salida = _correr(orden, nota_al_isp.REPORTE_DEL_TECNICO, user_profile)

    assert post.call_count == 0, "la nota reabrio un ticket que ya cerro"
    assert salida["codigo"] == "llego_tarde", salida
    no = _eventos(orden, nota_al_isp.EVENTO_NO_ANOTADA)
    assert [d["codigo"] for d in no] == ["llego_tarde"], no


def test_la_orden_que_YA_NO_ESTA_no_revienta(org_a, user_profile, version):
    orden = _orden(org_a, version, user_profile, 952)
    org_id, orden_id = str(orden.org_id), str(orden.id)
    AsignacionTrabajo.objects.filter(orden=orden).delete()
    orden.delete()

    with mock.patch("requests.post") as post:
        salida = tasks.anotar_en_el_isp(org_id, orden_id,
                                        nota_al_isp.EN_CAMINO, 1, "")

    assert post.call_count == 0
    assert salida["codigo"] == "sin_orden", salida
