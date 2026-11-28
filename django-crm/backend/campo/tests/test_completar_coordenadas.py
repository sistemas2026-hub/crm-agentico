# -*- coding: utf-8 -*-
"""
Rellenar el punto de las órdenes viejas sin pisar el de nadie.

LO QUE SE PRUEBA DE VERDAD no es que escriba: es **qué NO toca**. Un comando
de relleno que pisa un dato corregido a mano destruye trabajo de una persona
sin dejar rastro, y el síntoma aparece días después como «el pin está mal otra
vez» sin que nadie sepa por qué.

Las cuatro cosas que no puede hacer, y cada una tiene su prueba:
  - pisar una coordenada que ya está (la pudo corregir quien despacha)
  - tocar una orden cerrada o cancelada (es historia firmada)
  - inventar un punto cuando el ISP no lo tiene o lo tiene con otra forma
  - escribir en simulacro
"""
import datetime as dt
from unittest import mock

import pytest
from django.core.management import call_command

from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

#  Forma real medida contra la API (05/11/2026), con los dígitos cambiados.
CRUDO = "10.910800,-74.818600"
PUNTO = (10.9108, -74.8186)
COMANDO = "completar_coordenadas"


def _version(org):
    tipo = WorkType.objects.get_or_create(org=org, codigo="tc", defaults={
        "nombre": "TC", "labor": "correctivo"})[0]
    return WorkTypeVersion.objects.get_or_create(
        work_type=tipo, version=1, defaults={
            "estado": WorkTypeVersion.PUBLICADA,
            "esquema": {"campos": [{"id": "x", "tipo": "texto"}]}})[0]


def _orden(org, numero, *, estado=OrdenTrabajo.ASIGNADA, abonado="4986",
           lat=None, lng=None):
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=_version(org),
        origen_sistema="crm", origen_tipo="case", origen_ref=f"c-{numero}",
        cliente_nombre="Ana", cliente_id_abonado=abonado,
        estado_operativo=estado, gps_lat=lat, gps_lng=lng,
        programada_para=dt.datetime(2026, 11, 5, 12, 0,
                                    tzinfo=dt.timezone.utc))


def _responde(valor):
    """El motor contestando la ficha con ese valor en `coordenadas`."""
    return mock.patch(
        "operaciones.fuentes_adaptadores._pedirle_al_motor",
        return_value={"results": [{"nombre": "Ana", "coordenadas": valor}]})


def _correr(org, **extra):
    with _responde(extra.pop("valor", CRUDO)):
        call_command(COMANDO, org=str(org.id), **extra)


class TestLoQueSiHace:
    def test_una_orden_viva_sin_punto_lo_recibe(self, org_a):
        o = _orden(org_a, 9001)

        _correr(org_a, aplicar=True)

        o.refresh_from_db()
        assert (o.gps_lat, o.gps_lng) == PUNTO

    def test_el_simulacro_NO_escribe(self, org_a):
        #  Sin --aplicar no se toca la base. Si esto se rompe, un comando que
        #  alguien corre "para ver qué haría" cambia producción.
        o = _orden(org_a, 9002)

        _correr(org_a)

        o.refresh_from_db()
        assert o.gps_lat is None and o.gps_lng is None


class TestLoQueNoToca:
    def test_NO_pisa_un_punto_que_ya_esta(self, org_a):
        #  EL CASO QUE JUSTIFICA EL COMANDO ENTERO. Quien despacha pudo
        #  corregir a mano una coordenada mal cargada mirando el mapa. Este
        #  comando no puede distinguir esa corrección de un dato viejo, así
        #  que ante la duda no toca.
        o = _orden(org_a, 9003, lat=11.0, lng=-75.0)

        _correr(org_a, aplicar=True)

        o.refresh_from_db()
        assert (o.gps_lat, o.gps_lng) == (11.0, -75.0), (
            "una coordenada puesta a mano no se reemplaza por la del ISP")

    @pytest.mark.parametrize("estado", [
        OrdenTrabajo.CERRADA, OrdenTrabajo.COMPLETADA_CAMPO,
        OrdenTrabajo.CANCELADA,
    ])
    def test_NO_toca_lo_que_ya_termino(self, org_a, estado):
        #  Historia firmada. Rellenarla no le sirve a nadie --nadie va a ir--
        #  y cambia una orden que alguien ya cerró.
        o = _orden(org_a, 9004, estado=estado)

        _correr(org_a, aplicar=True)

        o.refresh_from_db()
        assert o.gps_lat is None, f"una orden {estado} no se toca"

    def test_sin_identificador_de_servicio_no_pregunta(self, org_a):
        #  Sin el id no hay a quién preguntarle, y adivinar por nombre
        #  devuelve OTRO cliente -- el error más caro posible acá.
        o = _orden(org_a, 9005, abonado="")

        with mock.patch(
                "operaciones.fuentes_adaptadores._pedirle_al_motor") as pedir:
            call_command(COMANDO, org=str(org_a.id), aplicar=True)

        assert not pedir.called, "sin id de servicio no se consulta nada"
        o.refresh_from_db()
        assert o.gps_lat is None

    def test_otra_empresa_no(self, org_a, org_b):
        ajena = _orden(org_b, 9006)

        _correr(org_a, aplicar=True)

        ajena.refresh_from_db()
        assert ajena.gps_lat is None, "no se tocan órdenes de otra empresa"


class TestLosDosFiltrosSonDos:
    """Dos redes para «no pisar un punto puesto a mano», y hacen falta las dos.

    SE MIDIO QUE HACIAN FALTA DOS PRUEBAS (05/11/2026). `test_NO_pisa_un_punto`
    sobrevivia a quitar CUALQUIERA de los dos filtros, porque el otro lo
    atrapaba: la prueba afirmaba el resultado sin distinguir quien lo logro.
    Dos mutaciones sobrevivieron por eso. Estas dos las matan.

    No son redundantes aunque protejan lo mismo:
      - el de la CONSULTA evita preguntarle a la API por una orden que ya
        tiene punto -- es trafico contra el proveedor que nadie necesita;
      - el de la ESCRITURA cubre la carrera: entre que se arma la lista y que
        se escribe, alguien pudo despachar de nuevo esa orden o corregirla a
        mano desde la pantalla.
    """

    def test_a_la_que_ya_tiene_punto_NI_SE_LE_PREGUNTA(self, org_a):
        #  MATA la mutacion que quita el filtro del queryset. Sin el, la orden
        #  igual no se pisaria --el update la filtra-- pero se habria gastado
        #  una llamada a la API del ISP por cada orden ya resuelta.
        _orden(org_a, 9020, lat=11.0, lng=-75.0)
        _orden(org_a, 9021)                      # esta si hay que preguntarla

        with mock.patch(
                "operaciones.fuentes_adaptadores._pedirle_al_motor",
                return_value={"results": [{"coordenadas": CRUDO}]}) as pedir:
            call_command(COMANDO, org=str(org_a.id), aplicar=True)

        assert pedir.call_count == 1, (
            "solo se pregunta por la que NO tiene punto: una orden ya resuelta "
            "no gasta una llamada al proveedor")

    def test_si_aparece_un_punto_MIENTRAS_corre_no_se_pisa(self, org_a):
        #  MATA la mutacion que quita el filtro del update. La carrera real:
        #  la orden se lista sin punto, y antes de escribirla alguien la
        #  corrige a mano desde la pantalla. Sin el filtro en el `update`, el
        #  comando pisa esa correccion sin dejar rastro.
        o = _orden(org_a, 9022)

        def _corrige_y_responde(*args, **kwargs):
            #  Entre listar y escribir: lo que haria la otra persona.
            OrdenTrabajo.objects.filter(pk=o.pk).update(gps_lat=11.0,
                                                        gps_lng=-75.0)
            return {"results": [{"coordenadas": CRUDO}]}

        with mock.patch("operaciones.fuentes_adaptadores._pedirle_al_motor",
                        side_effect=_corrige_y_responde):
            call_command(COMANDO, org=str(org_a.id), aplicar=True)

        o.refresh_from_db()
        assert (o.gps_lat, o.gps_lng) == (11.0, -75.0), (
            "el punto que entro durante la corrida gana: el comando no pisa "
            "lo que puso una persona")

    def test_y_lo_dice_en_vez_de_callarlo(self, org_a, capsys):
        #  Si el comando dijera «punto puesto» de una que no escribio, el
        #  conteo final mentiria y nadie podria auditar la corrida.
        o = _orden(org_a, 9023)

        def _corrige_y_responde(*args, **kwargs):
            OrdenTrabajo.objects.filter(pk=o.pk).update(gps_lat=11.0,
                                                        gps_lng=-75.0)
            return {"results": [{"coordenadas": CRUDO}]}

        with mock.patch("operaciones.fuentes_adaptadores._pedirle_al_motor",
                        side_effect=_corrige_y_responde):
            call_command(COMANDO, org=str(org_a.id), aplicar=True)

        salida = capsys.readouterr().out
        assert "no se pisa" in salida
        assert "PUESTAS: 0" in salida, "no se cuenta como puesta la que no se escribio"


class TestLoQueNoInventa:
    @pytest.mark.parametrize("valor", [
        "", None, "0,0", "lat 10.9 lng -74.8", "10,9108,-74,8186",
    ])
    def test_sin_dato_usable_la_orden_queda_SIN_punto(self, org_a, valor):
        #  Fail-closed. `0,0` entra acá porque es una coordenada válida --el
        #  Golfo de Guinea-- y es justo la que se cuela si la guarda solo
        #  pregunta «está vacío?».
        o = _orden(org_a, 9007)

        _correr(org_a, aplicar=True, valor=valor)

        o.refresh_from_db()
        assert o.gps_lat is None and o.gps_lng is None, (
            f"{valor!r} no se convierte en un punto")

    def test_si_el_motor_falla_la_orden_queda_igual_y_el_comando_sigue(self, org_a):
        #  Una consulta que falla no puede dejar sin rellenar a las otras
        #  veinticuatro, ni tumbar el comando a la mitad.
        o1, o2 = _orden(org_a, 9008), _orden(org_a, 9009)
        respuestas = [RuntimeError("timeout"),
                      {"results": [{"coordenadas": CRUDO}]}]

        with mock.patch("operaciones.fuentes_adaptadores._pedirle_al_motor",
                        side_effect=respuestas):
            call_command(COMANDO, org=str(org_a.id), aplicar=True)

        o1.refresh_from_db()
        o2.refresh_from_db()
        assert o1.gps_lat is None, "la que falló queda como estaba"
        assert (o2.gps_lat, o2.gps_lng) == PUNTO, "la siguiente igual se hace"


class TestNoFiltraElDomicilio:
    def test_la_salida_NO_trae_ninguna_coordenada(self, org_a, capsys):
        #  Esto se corre en una terminal cuya salida termina pegada en una
        #  conversación. El número de orden alcanza para saber qué pasó.
        _orden(org_a, 9010)

        _correr(org_a, aplicar=True)

        salida = capsys.readouterr().out
        assert "10.9108" not in salida
        assert "74.8186" not in salida
        assert "9010" in salida, "pero sí dice de qué orden habla"
