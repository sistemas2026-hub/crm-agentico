# -*- coding: utf-8 -*-
"""
================================================================================
 LA REVISION NO SE RECALCULA SI NADA CAMBIO  --  21/11/2026
================================================================================
El usuario: «la pestaña de Supervisor cuando se recarga demora en salir».

Programacion recalculaba la revision del cierre de todas las ordenes terminadas
sin validar en cada pedido, cada 15 segundos por pestaña (339 consultas con 15
ordenes). `campo/revision_sin_repetir.py` saca una huella y no repite la cuenta
si nada cambio.

QUE AFIRMA ESTA GUARDA
----------------------
Dos cosas, y la segunda es la que importa:

  · que un pedido repetido NO vuelva a revisar (el ahorro);
  · que TODO lo que cambia una revision se vea en el pedido siguiente, sin
    esperar el minuto. Cada prueba de ese grupo cambia UNA cosa y mira el
    EFECTO en la tarjeta, no que «la huella sea distinta»: una huella que se
    mueve y una pantalla que no cambia tambien pasaria esa.

Y lo que pasa cuando algo se rompe: la cache caida, una huella que no sale o
una revision que revienta dejan la pantalla calculando como antes.

LA PRIMERA VERSION DE ESTE CODIGO NO AHORRABA NADA y todas las pruebas de
Programacion estaban en verde: la huella reventaba por un nombre de campo mal
escrito y el codigo caia, callado, a calcular siempre. Por eso la primera
prueba cuenta llamadas: «devuelve lo correcto» no distingue un atajo que
funciona de uno que nunca se toma.
================================================================================
"""
from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone

from campo import dia_publicado as D
from campo import revision_del_cierre as RC
from campo import revision_sin_repetir as RSR
from campo.analisis_de_evidencia import AnalisisDeEvidencia
from campo.cotejo_del_reporte import CUADRA, CotejoDelReporte
from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla, PersonaDeCampo)
from campo.models import (AsignacionTrabajo, EventoTrabajo, EvidenciaTrabajo,
                          MaterialCatalogo, MovimientoDeMaterial, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.zonas import AliasDeZona, ZonaOperativa

pytestmark = pytest.mark.django_db

LUNES = dt.date(2026, 10, 5)
_numero = iter(range(7000, 99999))


@pytest.fixture(autouse=True)
def cache_limpia():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def version(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="rsr", nombre="Soporte",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "medicion_al_salir", "titulo": "Medición al salir"}]})


@pytest.fixture
def cuadrilla(org_a, admin_profile):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad="MARTHA GISELA")
    c = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla #1")
    j = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=c, fecha=LUNES,
        labor=JornadaDeCuadrilla.INSTALACION)
    j.zonas.set([z])
    persona = PersonaDeCampo.objects.create(org=org_a, profile=admin_profile,
                                            nombre="Tecnico 0")
    IntegranteDeJornada.objects.create(org=org_a, jornada=j, persona=persona,
                                       rol="tecnico")
    return j


def _terminada(org, version, de, dia=LUNES, **extra):
    o = OrdenTrabajo.objects.create(
        org=org, numero=next(_numero), tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE, zona="MARTHA GISELA",
        cliente_nombre="MARIO SABANAGRANDE",
        completada_campo_en=timezone.make_aware(
            dt.datetime.combine(dia, dt.time(14, 0))), **extra)
    AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico",
                                     es_principal=True)
    return o


def _revision(org, orden, fecha=LUNES):
    """La revision de UNA orden tal como llega a la pantalla."""
    d = D.del_dia(org, fecha)
    filas = [f for c in d["cuadrillas"] for f in c["ordenes"]]
    filas += d["por_revisar"] + d["con_alguien_que_no_sale"]
    return next(f for f in filas if f["numero"] == orden.numero)["revision"]


def _punto(revision, clave):
    return next((p for p in revision["puntos"] if p["clave"] == clave), None)


class _Contador:
    """Cuenta las llamadas a `revisar()` sin cambiar lo que devuelve."""

    def __enter__(self):
        self.veces = 0
        real = RC.revisar

        def contada(orden, **kw):
            self.veces += 1
            return real(orden, **kw)

        self._parche = mock.patch.object(RC, "revisar", side_effect=contada)
        self._parche.start()
        return self

    def __exit__(self, *a):
        self._parche.stop()


# ---------------------------------------------------------------------------
#  A · EL AHORRO
# ---------------------------------------------------------------------------

def test_a_un_pedido_repetido_no_vuelve_a_revisar(org_a, version, cuadrilla,
                                                  admin_profile):
    """LA QUE DICE SI EL ATAJO SE TOMA. Sin contar llamadas, un atajo que
    nunca se usa y uno que funciona devuelven lo mismo."""
    de_hoy = _terminada(org_a, version, admin_profile)
    vieja = _terminada(org_a, version, admin_profile,
                       LUNES - dt.timedelta(days=3))

    with _Contador() as c:
        primera = D.del_dia(org_a, LUNES)
        assert c.veces == 2, "en frio se revisa cada orden"
        segunda = D.del_dia(org_a, LUNES)
        assert c.veces == 2, "el pedido repetido no vuelve a revisar ninguna"

    def revisiones(d):
        filas = [f for cu in d["cuadrillas"] for f in cu["ordenes"]]
        return {f["numero"]: f["revision"] for f in filas + d["por_revisar"]}

    assert revisiones(primera) == revisiones(segunda)
    assert revisiones(segunda)[de_hoy.numero]["veredicto"]
    assert revisiones(segunda)[vieja.numero]["veredicto"]


def test_a2_la_del_dia_se_revisa_UNA_vez_por_pedido(org_a, version, cuadrilla,
                                                    admin_profile, monkeypatch):
    """Antes eran dos: una para las cuentas y otra para la tarjeta de su
    cuadrilla. Con el atajo apagado, para medir solo eso."""
    monkeypatch.setenv(RSR.VARIABLE, "0")
    for _ in range(3):
        _terminada(org_a, version, admin_profile)

    with _Contador() as c:
        D.del_dia(org_a, LUNES)

    assert c.veces == 3


def test_a3_con_el_interruptor_apagado_se_calcula_siempre(
        org_a, version, cuadrilla, admin_profile, monkeypatch):
    monkeypatch.setenv(RSR.VARIABLE, "0")
    _terminada(org_a, version, admin_profile)

    with _Contador() as c:
        D.del_dia(org_a, LUNES)
        D.del_dia(org_a, LUNES)

    assert c.veces == 2


def test_a4_pasado_el_minuto_se_revisa_aunque_la_huella_no_se_mueva(
        org_a, version, cuadrilla, admin_profile, monkeypatch):
    """La red de atras: lo que la huella no ve (la configuracion de la
    empresa, un `.update()`, un despliegue) no queda viejo mas de `VIDA`."""
    assert RSR.VIDA_POR_DEFECTO <= 60, \
        "la red de atras tiene que seguir siendo corta"
    monkeypatch.setenv(RSR.VARIABLE, "1")
    _terminada(org_a, version, admin_profile)

    with _Contador() as c:
        D.del_dia(org_a, LUNES)
        time.sleep(1.3)
        D.del_dia(org_a, LUNES)

    assert c.veces == 2


@pytest.mark.parametrize("valor,segundos", [
    (None, 60),        # sin declarar: la de fabrica
    ("", 60),
    ("0", 0),          # apagado
    ("off", 0),
    ("-5", 0),
    ("120", 120),
    ("99999", 600),    # el tope: nada queda viejo mas de diez minutos
    ("mucho", 60),     # lo que no se entiende no apaga ni quita el tope
])
def test_a5_la_perilla_dice_cuantos_segundos_y_tiene_tope(monkeypatch, valor,
                                                          segundos):
    if valor is None:
        monkeypatch.delenv(RSR.VARIABLE, raising=False)
    else:
        monkeypatch.setenv(RSR.VARIABLE, valor)

    assert RSR.vida() == segundos
    assert RSR.encendido() is (segundos > 0)


#  Que la perilla LLEGUE al contenedor que la lee lo mide una guarda de la
#  raiz, `tests/test_perilla_de_la_revision_declarada.py`: desde aca adentro
#  el compose de produccion no se ve, y una prueba que se salta no cuida nada.


# ---------------------------------------------------------------------------
#  B · LO QUE CAMBIA LA REVISION SE VE EN EL PEDIDO SIGUIENTE
# ---------------------------------------------------------------------------

def test_b_el_reporte_que_llega_se_ve_en_seguida(org_a, version, cuadrilla,
                                                 admin_profile):
    o = _terminada(org_a, version, admin_profile)
    assert _punto(_revision(org_a, o), "reporte")["ok"] is False

    EventoTrabajo.objects.create(
        org=org_a, orden=o, tipo="cierre_campo",
        datos={"definicion": [{"id": "servicio_validado"}],
               "respuestas": {"solucion": "Cambié el conector",
                              "servicio_validado": True}})

    r = _revision(org_a, o)
    assert _punto(r, "reporte")["ok"] is True
    assert r["solucion"] == "Cambié el conector"


def test_b2_el_material_que_llega_se_ve_en_seguida(org_a, version, cuadrilla,
                                                   admin_profile):
    o = _terminada(org_a, version, admin_profile)
    assert _punto(_revision(org_a, o), "material")["ok"] is None

    m = MaterialCatalogo.objects.create(org=org_a, codigo="CON",
                                        nombre="Conector", unidad="u")
    MovimientoDeMaterial.objects.create(
        org=org_a, material=m, orden=o, tipo=MovimientoDeMaterial.CONSUMO,
        cantidad=Decimal("1"), profile=admin_profile, idempotency_key="rsr-1")

    assert _punto(_revision(org_a, o), "material")["ok"] is True


def test_b3_LA_MEDICION_que_llega_se_ve_en_seguida(org_a, version, cuadrilla,
                                                   admin_profile):
    """EL MOTIVO POR EL QUE EL VEREDICTO NUNCA SE GUARDO
    (`revision_del_cierre.py`, «se calcula, no se guarda»): la medicion llega
    despues del cierre. Si esto fallara, la tarjeta diria «revisar» con la
    medicion ya hecha."""
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    o = _terminada(org_a, version, admin_profile)
    assert _punto(_revision(org_a, o), "medicion") is None

    PropuestaSupervisor.objects.create(
        org=org_a, origen_id="caso-rsr", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": FUENTE, "orden": str(o.id),
                    "quedo_en_rango": False}])

    r = _revision(org_a, o)
    assert _punto(r, "medicion")["ok"] is False
    assert r["veredicto"] == RC.NO_CERRAR


def test_b4_la_medicion_que_se_CORRIGE_tambien(org_a, version, cuadrilla,
                                               admin_profile):
    """La misma propuesta, reescrita: no cambia cuantas hay, cambia cuando se
    toco. Es como escribe `verificacion_de_arreglos` (`save` con
    `updated_at`)."""
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    o = _terminada(org_a, version, admin_profile)
    p = PropuestaSupervisor.objects.create(
        org=org_a, origen_id="caso-rsr2", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": FUENTE, "orden": str(o.id),
                    "quedo_en_rango": False}])
    assert _punto(_revision(org_a, o), "medicion")["ok"] is False

    p.evidencia = [{"fuente": FUENTE, "orden": str(o.id),
                    "quedo_en_rango": True}]
    p.save(update_fields=["evidencia", "updated_at"])

    assert _punto(_revision(org_a, o), "medicion")["ok"] is True


def test_b5_la_foto_y_su_analisis_se_ven_en_seguida(org_a, version, cuadrilla,
                                                    admin_profile):
    o = _terminada(org_a, version, admin_profile)
    antes = _revision(org_a, o)
    assert not any(e.get("analisis") for e in antes["evidencias"])

    ev = EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=o, requisito_id="medicion_al_salir",
        vuelta=o.vuelta, sha256="r".ljust(64, "x"), storage_key="k/rsr",
        nombre_original="m.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    con_foto = _revision(org_a, o)
    assert con_foto != antes, "la foto recien llegada cambia la tarjeta"

    AnalisisDeEvidencia.objects.create(
        org=org_a, evidencia=ev, vuelta=o.vuelta,
        origen=AnalisisDeEvidencia.IA,
        texto="Se ve el medidor con -19.8 dBm.")

    despues = _revision(org_a, o)
    assert any("-19.8" in str(e.get("analisis") or "")
               for e in despues["evidencias"]), despues["evidencias"]


def test_b6_el_cotejo_con_el_ticket_se_ve_en_seguida(org_a, version, cuadrilla,
                                                     admin_profile):
    o = _terminada(org_a, version, admin_profile)
    EventoTrabajo.objects.create(org=org_a, orden=o, tipo="cierre_campo",
                                 datos={"respuestas": {"solucion": "x"}})
    assert _punto(_revision(org_a, o), "cuadra") is None

    CotejoDelReporte.objects.create(org=org_a, orden=o, vuelta=o.vuelta,
                                    veredicto=CUADRA, motivo="")

    assert _punto(_revision(org_a, o), "cuadra")["ok"] is True


def test_b7_la_aprobada_deja_de_traer_revision_en_seguida(
        org_a, version, cuadrilla, admin_profile):
    """Con `.update()`, que NO mueve `updated_at`. Esta no pasa por la huella:
    una orden aprobada ya no tiene nada que revisar y sale antes de mirar lo
    guardado. Lo que si depende de la huella esta en el grupo F."""
    o = _terminada(org_a, version, admin_profile)
    assert _revision(org_a, o) is not None

    OrdenTrabajo.objects.filter(pk=o.pk).update(
        estado_validacion=OrdenTrabajo.APROBADO)

    assert _revision(org_a, o) is None


def test_b8_el_bloqueo_del_cierre_solo_se_ve_en_seguida(
        org_a, version, cuadrilla, admin_profile):
    from campo.cierre_por_el_supervisor import EVENTO_BLOQUEADO

    o = _terminada(org_a, version, admin_profile)
    assert _revision(org_a, o)["supervisor_no_pudo"] is None

    EventoTrabajo.objects.create(org=org_a, orden=o, tipo=EVENTO_BLOQUEADO,
                                 datos={"detalle": "techo de autonomia"})

    assert _revision(org_a, o)["supervisor_no_pudo"]["detalle"] == \
        "techo de autonomia"


def test_b9_la_que_pasa_a_ESPERAR_la_medicion_se_ve_en_seguida(
        org_a, version, cuadrilla, admin_profile):
    """Nada de la orden cambia: cambia que ahora se sabe que es una falla de
    servicio y necesita la medicion. Eso lo dice `pendientes_de_medir`, y
    entra en la huella."""
    o = _terminada(org_a, version, admin_profile)
    with mock.patch.object(RC, "pendientes_de_medir", return_value=set()):
        assert _punto(_revision(org_a, o), "medicion") is None

    with mock.patch.object(RC, "pendientes_de_medir",
                           return_value={str(o.id)}):
        assert _punto(_revision(org_a, o), "medicion")["ok"] is None

    with mock.patch.object(RC, "pendientes_de_medir", return_value=None):
        assert "No se pudo saber" in _punto(_revision(org_a, o),
                                            "medicion")["texto"]


def test_b10_lo_que_cambia_MIENTRAS_se_revisa_no_queda_tapado(
        org_a, version, cuadrilla, admin_profile):
    """LA HUELLA SE SACA ANTES DE CALCULAR. Si se sacara despues, un dato que
    llega durante la cuenta quedaria bajo una huella que ya lo incluye, con
    una revision que no lo vio: viejo hasta que venza el minuto."""
    o = _terminada(org_a, version, admin_profile)
    m = MaterialCatalogo.objects.create(org=org_a, codigo="CON2",
                                        nombre="Conector", unidad="u")
    real = RC.revisar
    hecho = []

    def revisar_y_despues_llega_el_material(orden, **kw):
        r = real(orden, **kw)
        if not hecho:
            hecho.append(1)
            MovimientoDeMaterial.objects.create(
                org=org_a, material=m, orden=orden,
                tipo=MovimientoDeMaterial.CONSUMO, cantidad=Decimal("1"),
                profile=admin_profile, idempotency_key="rsr-carrera")
        return r

    with mock.patch.object(RC, "revisar",
                           side_effect=revisar_y_despues_llega_el_material):
        assert _punto(_revision(org_a, o), "material")["ok"] is None

    assert _punto(_revision(org_a, o), "material")["ok"] is True


# ---------------------------------------------------------------------------
#  C · CUANDO ALGO SE ROMPE, SE CALCULA
# ---------------------------------------------------------------------------

def test_c_una_revision_que_FALLO_no_se_guarda(org_a, version, cuadrilla,
                                               admin_profile):
    """La tarjeta de error se muestra, pero el pedido siguiente lo intenta de
    nuevo: un tropiezo de un instante no puede durar un minuto."""
    o = _terminada(org_a, version, admin_profile)

    with mock.patch.object(RC, "revisar", side_effect=RuntimeError("se cayo")):
        r = _revision(org_a, o)
    assert _punto(r, "error") is not None
    assert "se cayo" not in str(r), "el tipo, nunca el texto del error"

    r = _revision(org_a, o)
    assert _punto(r, "error") is None
    assert _punto(r, "reporte") is not None


def test_c2_con_la_cache_caida_la_pantalla_sale_igual(org_a, version, cuadrilla,
                                                      admin_profile):
    o = _terminada(org_a, version, admin_profile)

    with mock.patch.object(cache, "get_many",
                           side_effect=ConnectionError("redis")), \
            mock.patch.object(cache, "set_many",
                              side_effect=ConnectionError("redis")) as guardar:
        r = _revision(org_a, o)

    assert _punto(r, "reporte") is not None
    #  Y NO SE INSISTE: con Redis caido cada intento espera su tope. Leer y
    #  ademas guardar seria pagarlo dos veces por pedido.
    assert not guardar.called


def test_c2b_si_solo_falla_el_guardado_la_pantalla_sale_igual(
        org_a, version, cuadrilla, admin_profile):
    o = _terminada(org_a, version, admin_profile)

    with mock.patch.object(cache, "set_many",
                           side_effect=ConnectionError("redis")):
        r = _revision(org_a, o)

    assert _punto(r, "reporte") is not None


def test_c3_si_la_huella_no_sale_se_calcula_y_no_se_guarda(
        org_a, version, cuadrilla, admin_profile):
    o = _terminada(org_a, version, admin_profile)

    with mock.patch.object(RSR, "huellas", side_effect=RuntimeError("x")), \
            mock.patch.object(cache, "set_many") as guardar, \
            _Contador() as c:
        assert _punto(_revision(org_a, o), "reporte") is not None
        assert _punto(_revision(org_a, o), "reporte") is not None

    assert c.veces == 2
    assert not guardar.called


def test_c4_la_huella_es_de_seis_consultas_no_una_docena_por_orden(
        org_a, version, cuadrilla, admin_profile, django_assert_num_queries):
    """El atajo tiene que costar menos que lo que ahorra, y no crecer con la
    cantidad de ordenes."""
    ordenes = [_terminada(org_a, version, admin_profile) for _ in range(6)]

    with django_assert_num_queries(6):
        h = RSR.huellas(org_a, ordenes, set())

    assert len(set(h.values())) == 6, "cada orden con su huella"


# ---------------------------------------------------------------------------
#  D · CADA EMPRESA LA SUYA
# ---------------------------------------------------------------------------

def test_d_la_revision_de_otra_empresa_no_se_cruza(org_a, org_b, version,
                                                   cuadrilla, admin_profile):
    """La clave lleva la empresa y la orden; y lo que se guarda bajo una
    huella ajena no se devuelve."""
    o = _terminada(org_a, version, admin_profile)
    buena = _revision(org_a, o)

    #  Alguien dejo, bajo la clave de OTRA empresa, una revision para el
    #  mismo id de orden y con la huella correcta.
    #
    #  LA HUELLA SE COPIA DE LO QUE QUEDO GUARDADO, no se recalcula aca: al
    #  sumarle la zona y el codigo (22/11/2026), la que esta prueba armaba a
    #  mano dejo de coincidir con la real, la entrada plantada nunca valia, y
    #  la prueba pasaba tambien con la clave SIN la empresa. Se vio al repetir
    #  las mutaciones.
    guardado = cache.get(RSR._clave(org_a.id, o.id))
    assert guardado and guardado["revision"] == buena, \
        "sin algo guardado esta prueba no mide nada"
    h = guardado["huella"]
    cache.set(RSR._clave(org_b.id, o.id),
              {"huella": h, "revision": {"veredicto": "ajena"}}, 60)

    assert _revision(org_a, o) == buena

    #  Y una entrada con otra huella bajo la clave propia tampoco vale.
    cache.set(RSR._clave(org_a.id, o.id),
              {"huella": "otra", "revision": {"veredicto": "vieja",
                                              "puntos": []}}, 60)
    assert _revision(org_a, o) == buena


# ---------------------------------------------------------------------------
#  F · LO QUE LA REVISION LEE DE LA ORDEN Y DE SU PLANTILLA
#
#  La auditoria del 22/11/2026 reemplazo `_de_la_orden` por el id pelado y las
#  22 pruebas siguieron en verde: todo lo de arriba cambia OTRA tabla. Aca
#  cada cambio va con `.update()`, que no mueve `updated_at`: si pasaran solo
#  por la fecha de la fila, no medirian el valor.
# ---------------------------------------------------------------------------

@pytest.fixture
def con_campo(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="rsr-f", nombre="Soporte",
                                 labor=JornadaDeCuadrilla.INSTALACION)
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "serial", "titulo": "Serial",
                             "tipo": "texto", "obligatorio": True}],
                 "evidencias": []})


def test_f_lo_que_el_tecnico_lleno_en_el_formulario_se_ve_en_seguida(
        org_a, con_campo, cuadrilla, admin_profile):
    o = _terminada(org_a, con_campo, admin_profile)
    assert _punto(_revision(org_a, o), "checklist")["ok"] is False

    OrdenTrabajo.objects.filter(pk=o.pk).update(datos={"serial": "ZTE123"})

    assert _punto(_revision(org_a, o), "checklist")["ok"] is True


def test_f2_el_caso_del_ticket_se_ve_en_seguida(org_a, version, cuadrilla,
                                                admin_profile):
    o = _terminada(org_a, version, admin_profile, resumen="Sin internet")
    assert _revision(org_a, o)["el_ticket"]["caso"] == "Sin internet"

    OrdenTrabajo.objects.filter(pk=o.pk).update(resumen="Cambio de equipo")

    assert _revision(org_a, o)["el_ticket"]["caso"] == "Cambio de equipo"


def test_f3_la_orden_pasada_a_OTRA_plantilla_se_ve_en_seguida(
        org_a, version, con_campo, cuadrilla, admin_profile):
    """Lo que hacen `recolocar_plantilla` y `repuntar_plantilla`: un
    `.update(tipo_trabajo_version=...)`, sin evento y sin tocar la fecha."""
    #  Las dos plantillas se llaman igual, para que lo unico distinto sea
    #  CUAL es: sin esto la prueba pasaba por el nombre aunque la huella no
    #  mirara la plantilla.
    assert con_campo.work_type.nombre == version.work_type.nombre

    o = _terminada(org_a, version, admin_profile)
    antes = _revision(org_a, o)
    assert "Serial" not in _punto(antes, "checklist")["texto"]

    OrdenTrabajo.objects.filter(pk=o.pk).update(tipo_trabajo_version=con_campo)

    despues = _revision(org_a, o)
    assert "Serial" in _punto(despues, "checklist")["texto"], \
        "ahora se le exige el campo de la plantilla nueva"
    assert despues != antes


def test_f4_la_plantilla_RENOMBRADA_se_ve_en_seguida(org_a, version, cuadrilla,
                                                     admin_profile):
    """El nombre del tipo es el «asunto» de la tarjeta, y renombrarlo no
    mueve la fecha de la version que la orden tiene puesta."""
    o = _terminada(org_a, version, admin_profile)
    assert _revision(org_a, o)["el_ticket"]["asunto"] == "Soporte"

    WorkType.objects.filter(pk=version.work_type_id).update(
        nombre="Correctivo de red")

    assert _revision(org_a, o)["el_ticket"]["asunto"] == "Correctivo de red"


def test_f5_un_despliegue_que_cambia_el_codigo_no_devuelve_lo_de_antes(
        org_a, version, cuadrilla, admin_profile, monkeypatch):
    """Lo guardado vive en Redis y sobrevive al despliegue. Quien acaba de
    desplegar un arreglo mira la tarjeta en ese mismo minuto."""
    _terminada(org_a, version, admin_profile)

    with _Contador() as c:
        D.del_dia(org_a, LUNES)
        monkeypatch.setattr(RSR, "_VERSION", ["otro-despliegue"])
        D.del_dia(org_a, LUNES)

    assert c.veces == 2


def test_f6_la_version_del_codigo_sale_de_los_archivos_y_es_estable(
        monkeypatch, tmp_path):
    """Que se saque de verdad y no sea una constante: dos carpetas con codigo
    distinto dan dos versiones, y la misma carpeta da siempre la misma."""
    (tmp_path / "revision_sin_repetir.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_algo.py").write_text("y = 1\n")

    def version():
        monkeypatch.setattr(RSR, "_VERSION", [])
        monkeypatch.setattr(RSR, "__file__",
                            str(tmp_path / "revision_sin_repetir.py"))
        return RSR.version_del_codigo()

    primera = version()
    assert version() == primera
    (tmp_path / "tests" / "test_algo.py").write_text("y = 2\n")
    assert version() == primera, "una prueba que cambia no es otro criterio"
    (tmp_path / "revision_sin_repetir.py").write_text("x = 2\n")
    assert version() != primera


def test_f7_la_zona_de_la_empresa_que_cambia_se_ve_en_seguida(
        org_a, version, cuadrilla, admin_profile):
    from campo.cierre_por_el_supervisor import EVENTO_BLOQUEADO

    o = _terminada(org_a, version, admin_profile)
    EventoTrabajo.objects.create(org=org_a, orden=o, tipo=EVENTO_BLOQUEADO,
                                 datos={"detalle": "x"})
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    en_bogota = _revision(org_a, o)["supervisor_no_pudo"]["hora"]

    org_a.timezone = "Asia/Tokyo"
    org_a.save(update_fields=["timezone"])

    assert _revision(org_a, o)["supervisor_no_pudo"]["hora"] != en_bogota


def test_f8_recalcular_la_atencion_de_las_fotos_se_ve_en_seguida(
        org_a, version, cuadrilla, admin_profile):
    """El comando escribia con `bulk_update`, que no mueve `updated_at`: quien
    lo corria miraba la tarjeta y veia lo de antes durante un minuto."""
    from django.core.management import call_command

    from common.tasks import set_rls_context

    o = _terminada(org_a, version, admin_profile)
    ev = EvidenciaTrabajo.objects.create(
        org=org_a, orden_trabajo=o, requisito_id="medicion_al_salir",
        vuelta=o.vuelta, sha256="q".ljust(64, "x"), storage_key="k/rsr8",
        nombre_original="m.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    a = AnalisisDeEvidencia.objects.create(
        org=org_a, evidencia=ev, vuelta=o.vuelta,
        origen=AnalisisDeEvidencia.IA,
        texto="La imagen es de un catalogo.\nATENCION: si",
        pide_atencion=False)

    with _Contador() as c:
        D.del_dia(org_a, LUNES)
        D.del_dia(org_a, LUNES)
        assert c.veces == 1

        call_command("recalcular_atencion_fotos", "--org", str(org_a.id),
                     "--aplicar", verbosity=0)
        set_rls_context(str(org_a.id))
        a.refresh_from_db()
        assert a.pide_atencion is True, "el comando tenia algo que cambiar"

        D.del_dia(org_a, LUNES)
        assert c.veces == 2, "y Programacion lo ve en el pedido siguiente"


# ---------------------------------------------------------------------------
#  G · EL MATERIAL DEL DIA NO REVISA NADA, Y SI FALLA TODO SE DICE
# ---------------------------------------------------------------------------

def test_g_el_material_del_dia_no_revisa_ningun_cierre(org_a, version,
                                                       cuadrilla,
                                                       admin_profile):
    """Al cargar Programacion se piden a la vez lo publicado y el material.
    El material armaba el dia publicado ENTERO para leer la prioridad de cada
    orden: en frio, todas las ordenes terminadas se revisaban dos veces en
    paralelo."""
    from campo import material_del_dia as MD

    for _ in range(3):
        _terminada(org_a, version, admin_profile)
    monkeypatch_env = mock.patch.dict("os.environ", {RSR.VARIABLE: "0"})

    with monkeypatch_env, _Contador() as c:
        m = MD.calcular(org_a, LUNES)

    assert c.veces == 0
    assert m is not None


def test_g2_sin_revision_las_filas_salen_igual_y_sin_ella(
        org_a, version, cuadrilla, admin_profile):
    o = _terminada(org_a, version, admin_profile)

    d = D.del_dia(org_a, LUNES, con_revision=False)

    fila = next(f for c in d["cuadrillas"] for f in c["ordenes"]
                if f["numero"] == o.numero)
    assert fila["revision"] is None
    assert fila["estado"] == OrdenTrabajo.COMPLETADA_CAMPO
    assert d["cuentas"]["publicadas"] == 1


def test_g3_si_falla_TODA_la_revision_cada_tarjeta_lo_dice(
        org_a, version, cuadrilla, admin_profile):
    """Una tarjeta sin revision y sin botones se lee como «no hay nada que
    revisar». Y la orden que de verdad no tiene nada que revisar sigue sin
    tarjeta de error."""
    por_revisar = _terminada(org_a, version, admin_profile)
    en_curso = OrdenTrabajo.objects.create(
        org=org_a, numero=next(_numero), tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.EN_SITIO, zona="MARTHA GISELA")
    AsignacionTrabajo.objects.create(orden=en_curso, profile=admin_profile,
                                     rol="tecnico", es_principal=True)

    with mock.patch.object(RSR, "de_las_ordenes",
                           side_effect=RuntimeError("se cayo todo")):
        d = D.del_dia(org_a, LUNES)

    filas = {f["numero"]: f for c in d["cuadrillas"] for f in c["ordenes"]}
    r = filas[por_revisar.numero]["revision"]
    assert _punto(r, "error") is not None
    assert "RuntimeError" in _punto(r, "error")["texto"]
    assert "se cayo todo" not in str(r)
    assert filas[en_curso.numero]["revision"] is None


# ---------------------------------------------------------------------------
#  M · EL COMANDO QUE LO MIDE DONDE CORRE
# ---------------------------------------------------------------------------

def test_m_el_comando_mide_los_dos_caminos_y_no_nombra_a_nadie(
        org_a, version, cuadrilla, admin_profile):
    """`medir_programacion` se corre en produccion y su salida se pega en un
    chat: cuentas y milisegundos, nada de ningun cliente. Y deja el
    interruptor como lo encontro."""
    import io
    import os

    from django.core.management import call_command

    for _ in range(2):
        _terminada(org_a, version, admin_profile)
    antes = os.environ.get(RSR.VARIABLE)
    salida = io.StringIO()

    call_command("medir_programacion", "--org", str(org_a.id),
                 "--fecha", LUNES.isoformat(), stdout=salida)

    texto = salida.getvalue()
    def columnas(empieza):
        return next(r for r in texto.splitlines()
                    if r.strip().startswith(empieza)).split()

    #  Las columnas: ... <ms> ms <consultas> <revisadas> <ms> ms
    sin, repetido = columnas("sin el atajo"), columnas("con el atajo, repetido")
    assert int(sin[-3]) == 2, "sin el atajo se revisan las dos"
    assert int(repetido[-3]) == 0, "repetido no se revisa ninguna"
    assert int(repetido[-4]) < int(sin[-4]), "y hace menos consultas"
    assert "MARIO" not in texto and "SABANAGRANDE" not in texto
    assert "OJO" not in texto
    assert os.environ.get(RSR.VARIABLE) == antes


# ---------------------------------------------------------------------------
#  E · QUIEN LA ASIGNO, CON UNA DEVUELTA EN LA PANTALLA
# ---------------------------------------------------------------------------

def test_e_una_orden_devuelta_no_borra_quien_asigno_las_demas(
        org_a, version, cuadrilla, admin_profile):
    """El diccionario de la devolucion se llamaba igual que el de «quien la
    asigno» y lo pisaba: con UNA devuelta en la pantalla, todas las demas
    decian «sin registro» y la devuelta decia que la asigno quien la
    devolvio."""
    normal = OrdenTrabajo.objects.create(
        org=org_a, numero=next(_numero), tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona="MARTHA GISELA")
    devuelta = OrdenTrabajo.objects.create(
        org=org_a, numero=next(_numero), tipo_trabajo_version=version,
        estado_operativo=OrdenTrabajo.CORRECCION_REQUERIDA,
        estado_validacion=OrdenTrabajo.REQUIERE_CORRECCION,
        zona="MARTHA GISELA")
    for o in (normal, devuelta):
        AsignacionTrabajo.objects.create(orden=o, profile=admin_profile,
                                         rol="tecnico", es_principal=True)
        EventoTrabajo.objects.create(org=org_a, orden=o,
                                     tipo="asignada_por_el_supervisor")
    EventoTrabajo.objects.create(
        org=org_a, orden=devuelta, tipo="correccion_requerida",
        profile=admin_profile,
        datos={"requisitos_a_corregir": ["medicion_al_salir"],
               "observacion": "No se lee."})

    d = D.del_dia(org_a, LUNES)
    filas = {f["numero"]: f for c in d["cuadrillas"] for f in c["ordenes"]}

    assert filas[normal.numero]["asignada_por"] == D.SUPERVISOR
    assert filas[devuelta.numero]["asignada_por"] == D.SUPERVISOR
    assert filas[devuelta.numero]["devolucion"]["motivo"] == "No se lee."
    assert d["cuentas"]["por_el_supervisor"] == 2
    assert d["cuentas"]["sin_registro"] == 0
