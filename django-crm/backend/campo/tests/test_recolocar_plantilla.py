# -*- coding: utf-8 -*-
"""
Mover una orden abierta a la plantilla que corresponde.

LO QUE DE VERDAD SE PRUEBA no es que mueva: es **qué no toca**. Este comando
cambia qué se le pide a un trabajo que ya salió a la calle, así que lo caro no
es que falle -- es que acierte de más:

  - una orden CERRADA reescrita es historia de un trabajo que alguien ya
    revisó y aprobó;
  - el ESQUEMA de una plantilla modificado rompe la única respuesta exacta a
    «qué se le pidió a esta orden»;
  - una orden movida SIN REGISTRO deja esa pregunta sin respuesta, que es
    casi lo mismo.
"""
import datetime as dt

import pytest

from django.core.management import CommandError, call_command

from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)

pytestmark = pytest.mark.django_db

COMANDO = "recolocar_plantilla"

#  La que exige la medición: el caso real del 06/11/2026.
FIBRA = [{"id": "medicion", "titulo": "Medición al llegar", "obligatorio": True},
         {"id": "dano", "titulo": "Daño encontrado", "obligatorio": False}]
#  La de TV: no la exige.
TV = [{"id": "trabajo", "titulo": "Trabajo terminado", "obligatorio": True}]


def _plantilla(org, codigo, evidencias, version=1):
    wt = WorkType.objects.get_or_create(
        org=org, codigo=codigo, defaults={"nombre": codigo.upper(),
                                          "labor": "correctivo"})[0]
    return WorkTypeVersion.objects.create(
        work_type=wt, version=version, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": evidencias})


def _orden(org, numero, version, *, estado=OrdenTrabajo.ASIGNADA, resumen=""):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        origen_sistema="crm", origen_ref=f"c-{numero}", resumen=resumen,
        estado_operativo=estado,
        programada_para=dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.timezone.utc))


def _correr(org, **extra):
    call_command(COMANDO, org=str(org.id), de="fibra", a="tv", **extra)


@pytest.fixture
def dos(org_a):
    return _plantilla(org_a, "fibra", FIBRA), _plantilla(org_a, "tv", TV)


class TestLoQueSiHace:
    def test_una_orden_abierta_pasa_a_la_plantilla_correcta(self, org_a, dos):
        vieja, nueva = dos
        o = _orden(org_a, 1, vieja)

        _correr(org_a, aplicar=True)

        o.refresh_from_db()
        assert o.tipo_trabajo_version_id == nueva.id

    def test_el_simulacro_NO_escribe(self, org_a, dos):
        vieja, _ = dos
        o = _orden(org_a, 2, vieja)

        _correr(org_a)

        o.refresh_from_db()
        assert o.tipo_trabajo_version_id == vieja.id

    def test_filtra_por_TEXTO_cuando_se_le_pide(self, org_a, dos):
        #  Sin esto habría que mover todas o ninguna, y el caso real es
        #  justamente que solo algunos asuntos están mal ruteados.
        vieja, nueva = dos
        tv = _orden(org_a, 3, vieja, resumen="Problema De Tv/Niveles Altos")
        fibra = _orden(org_a, 4, vieja, resumen="Internet Lento")

        _correr(org_a, texto="tv", aplicar=True)

        tv.refresh_from_db()
        fibra.refresh_from_db()
        assert tv.tipo_trabajo_version_id == nueva.id
        assert fibra.tipo_trabajo_version_id == vieja.id

    def test_toma_la_version_PUBLICADA_mas_alta(self, org_a, dos):
        #  Una borrador puede cambiar debajo del técnico: misma regla que
        #  aplica `crear_orden`.
        vieja, _ = dos
        v2 = _plantilla(org_a, "tv", TV, version=2)
        WorkTypeVersion.objects.create(
            work_type=v2.work_type, version=3,
            estado=WorkTypeVersion.BORRADOR,
            esquema={"campos": [], "evidencias": TV})
        o = _orden(org_a, 5, vieja)

        _correr(org_a, aplicar=True)

        o.refresh_from_db()
        assert o.tipo_trabajo_version_id == v2.id


class TestLoQueNoToca:
    @pytest.mark.parametrize("estado", [
        OrdenTrabajo.CERRADA, OrdenTrabajo.COMPLETADA_CAMPO,
        OrdenTrabajo.CANCELADA,
    ])
    def test_NO_toca_lo_que_ya_termino(self, org_a, dos, estado):
        #  Nadie va a volver a esa casa, y cambiarle la plantilla reescribiría
        #  la historia de un trabajo que alguien ya revisó y aprobó.
        vieja, _ = dos
        o = _orden(org_a, 6, vieja, estado=estado)

        _correr(org_a, aplicar=True)

        o.refresh_from_db()
        assert o.tipo_trabajo_version_id == vieja.id

    def test_NO_modifica_el_esquema_de_ninguna_plantilla(self, org_a, dos):
        #  LA GARANTÍA QUE SOSTIENE TODO LO DEMÁS. Si el comando editara el
        #  esquema en vez de mover el puntero, «qué se le pidió a esta orden»
        #  dejaría de tener una respuesta exacta -- y la guarda de
        #  `models.py:95-117` existe justamente para impedirlo.
        vieja, nueva = dos
        antes_v, antes_n = dict(vieja.esquema), dict(nueva.esquema)
        _orden(org_a, 7, vieja)

        _correr(org_a, aplicar=True)

        vieja.refresh_from_db()
        nueva.refresh_from_db()
        assert vieja.esquema == antes_v
        assert nueva.esquema == antes_n

    def test_las_de_OTRA_empresa_no_se_tocan(self, org_a, org_b, dos):
        vieja, _ = dos
        ajena_v = _plantilla(org_b, "fibra", FIBRA)
        ajena = _orden(org_b, 8, ajena_v)

        _correr(org_a, aplicar=True)

        ajena.refresh_from_db()
        assert ajena.tipo_trabajo_version_id == ajena_v.id

    def test_NO_borra_las_fotos_que_quedan_sin_requisito(self, org_a, dos):
        #  Es trabajo que alguien hizo. Deja de pedirse, no deja de existir.
        vieja, _ = dos
        o = _orden(org_a, 9, vieja)
        ev = EvidenciaTrabajo.objects.create(
            org=org_a, orden_trabajo=o, requisito_id="medicion", vuelta=1,
            sha256="x", storage_key="k", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=10,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)

        _correr(org_a, aplicar=True)

        assert EvidenciaTrabajo.objects.filter(pk=ev.pk).exists()


class TestLosDosFiltrosSonDos:
    """Dos redes para «no tocar lo terminado», y hacen falta las dos.

    SE MIDIO QUE HACIA FALTA ESTA PRUEBA (06/11/2026):
    `test_NO_toca_lo_que_ya_termino` sobrevivia a quitar el filtro del
    queryset, porque el `update()` de adentro de la transaccion lo atrapaba
    igual. La prueba afirmaba el resultado sin distinguir quien lo logro.

    No son redundantes: el del QUERYSET evita gastar trabajo --y una consulta
    por orden-- en algo que no se va a mover; el del UPDATE cubre la carrera,
    que aca es muy real porque el comando puede tardar: el tecnico esta en la
    calle y puede completar la orden justo mientras corre.
    """

    def test_el_CONTEO_no_incluye_las_terminadas(self, org_a, dos, capsys):
        #  MATA la mutacion que quita el filtro del queryset. Sin el, la orden
        #  cerrada no se moveria --el `update` la atrapa-- pero el comando
        #  diria «se moverian 2» y la imprimiria en la lista. Quien corre un
        #  simulacro para decidir si aplicar leeria un numero que no es.
        vieja, _ = dos
        _orden(org_a, 23, vieja)
        _orden(org_a, 24, vieja, estado=OrdenTrabajo.CERRADA)

        _correr(org_a)

        salida = capsys.readouterr().out
        assert "se moverian: 1" in salida.lower().replace("í", "i")
        assert "#24" not in salida, "una orden cerrada no se nombra siquiera"

    def test_si_la_orden_se_COMPLETA_mientras_corre_no_se_mueve(self, org_a, dos):
        vieja, nueva = dos
        o = _orden(org_a, 20, vieja)
        otra = _orden(org_a, 21, vieja)

        #  La primera se completa mientras el comando trabaja en ella.
        import campo.management.commands.recolocar_plantilla as mod
        original = mod.transaction.atomic

        def _completar_y_seguir(*a, **k):
            if OrdenTrabajo.objects.filter(
                    pk=o.pk, estado_operativo=OrdenTrabajo.ASIGNADA).exists():
                OrdenTrabajo.objects.filter(pk=o.pk).update(
                    estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO)
            return original(*a, **k)

        mod.transaction.atomic = _completar_y_seguir
        try:
            _correr(org_a, aplicar=True)
        finally:
            mod.transaction.atomic = original

        o.refresh_from_db()
        otra.refresh_from_db()
        assert o.tipo_trabajo_version_id == vieja.id, (
            "la que se completo mientras corria no se mueve")
        assert otra.tipo_trabajo_version_id == nueva.id, (
            "pero las demas si: una no frena a las otras")

    def test_y_la_que_no_se_movio_NO_deja_evento(self, org_a, dos):
        #  Si dejara uno, la auditoria diria que se movio algo que no se movio.
        vieja, _ = dos
        o = _orden(org_a, 22, vieja)

        import campo.management.commands.recolocar_plantilla as mod
        original = mod.transaction.atomic

        def _completar_y_seguir(*a, **k):
            OrdenTrabajo.objects.filter(pk=o.pk).update(
                estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO)
            return original(*a, **k)

        mod.transaction.atomic = _completar_y_seguir
        try:
            _correr(org_a, aplicar=True)
        finally:
            mod.transaction.atomic = original

        assert not EventoTrabajo.objects.filter(
            orden=o, tipo="plantilla_recolocada").exists()


class TestQueQuedeEscrito:
    def test_cada_movimiento_deja_su_EVENTO(self, org_a, dos):
        #  Sin esto, «por qué esta orden cambió de plantilla» no tiene
        #  respuesta -- que es casi tan malo como no poder contestar «qué se
        #  le pidió».
        vieja, nueva = dos
        o = _orden(org_a, 10, vieja)

        _correr(org_a, aplicar=True)

        e = EventoTrabajo.objects.get(orden=o, tipo="plantilla_recolocada")
        assert e.datos["de"] == "fibra"
        assert e.datos["a"] == "tv"
        assert e.datos["a_version"] == nueva.version

    def test_el_evento_NOMBRA_las_fotos_que_quedan_huerfanas(self, org_a, dos):
        vieja, _ = dos
        o = _orden(org_a, 11, vieja)
        EvidenciaTrabajo.objects.create(
            org=org_a, orden_trabajo=o, requisito_id="medicion", vuelta=1,
            sha256="y", storage_key="k", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=10,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)

        _correr(org_a, aplicar=True)

        e = EventoTrabajo.objects.get(orden=o, tipo="plantilla_recolocada")
        assert e.datos["evidencias_huerfanas"] == ["medicion"]

    def test_el_simulacro_NO_deja_eventos(self, org_a, dos):
        vieja, _ = dos
        o = _orden(org_a, 12, vieja)

        _correr(org_a)

        assert not EventoTrabajo.objects.filter(
            orden=o, tipo="plantilla_recolocada").exists()


class TestCuandoNoSePuede:
    def test_una_plantilla_que_no_existe_se_dice_con_su_nombre(self, org_a, dos):
        with pytest.raises(CommandError, match="no_existe"):
            call_command(COMANDO, org=str(org_a.id), de="fibra", a="no_existe")

    def test_una_plantilla_SIN_version_publicada_no_sirve_de_destino(
            self, org_a, dos):
        #  Una borrador puede cambiar debajo del técnico.
        wt = WorkType.objects.create(org=org_a, codigo="borrador",
                                     nombre="B", labor="correctivo")
        WorkTypeVersion.objects.create(
            work_type=wt, version=1, estado=WorkTypeVersion.BORRADOR,
            esquema={"campos": [], "evidencias": []})

        with pytest.raises(CommandError, match="PUBLICADA"):
            call_command(COMANDO, org=str(org_a.id), de="fibra", a="borrador")

    def test_una_organizacion_inventada_no_escupe_una_traza(self, org_a):
        with pytest.raises(CommandError, match="válida"):
            call_command(COMANDO, org="no-soy-un-uuid", de="a", a="b")
