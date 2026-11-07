"""
================================================================================
 EL INFORME DE CRUCES CUENTA LO QUE PASÓ, Y NO DICE NADA DEL CLIENTE  --  27/10/2026
================================================================================
Antes de decidir si el reparto ordena por cercanía hace falta saber cuántos días
dos o más cuadrillas fueron al mismo barrio, y si las órdenes traen con qué
medir la distancia. Se afirma sobre los CONTEOS, con datos armados para que
cada uno tenga una sola respuesta posible, y sobre la salida: sin un solo dato
del cliente.
================================================================================
"""
import datetime as dt
import io
import zoneinfo

import pytest
from django.core.management import call_command

from campo.cuadrillas import Cuadrilla, JornadaDeCuadrilla
from campo.management.commands.informe_de_cruces import medir
from campo.models import AsignacionTrabajo, OrdenTrabajo, WorkType, WorkTypeVersion
from campo.zonas import normalizar_localidad
from common.models import Profile, User

pytestmark = pytest.mark.django_db

BOGOTA = zoneinfo.ZoneInfo("America/Bogota")
HASTA = dt.date(2026, 10, 10)
DIA = dt.date(2026, 10, 9)          # el día del único cruce
CANDELARIA = normalizar_localidad("CANDELARIA")


def _a_las(fecha, hora=12, minuto=0):
    return dt.datetime.combine(fecha, dt.time(hora, minuto), tzinfo=BOGOTA)


def _cuenta(org, correo):
    u = User.objects.create_user(email=correo, password="x12345678", name="Alguien")
    return Profile.objects.create(user=u, org=org, role="USER", is_active=True)


class Armado:
    """Dos cuadrillas con jornada los tres días; las órdenes se arman en cada prueba."""

    def __init__(self, org):
        org.timezone = "America/Bogota"
        org.save(update_fields=["timezone"])
        self.org = org
        wt = WorkType.objects.create(org=org, codigo="ftth", nombre="FTTH",
                                     labor=JornadaDeCuadrilla.INSTALACION)
        self.version = WorkTypeVersion.objects.create(
            work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
            esquema={"campos": []})
        sufijo = str(org.pk)[:8]
        self.lider_norte = _cuenta(org, f"norte-{sufijo}@cruces.test")
        self.lider_sur = _cuenta(org, f"sur-{sufijo}@cruces.test")
        self.sin_jornada = _cuenta(org, f"suelta-{sufijo}@cruces.test")
        norte = Cuadrilla.objects.create(org=org, nombre="Norte", lider=self.lider_norte)
        sur = Cuadrilla.objects.create(org=org, nombre="Sur", lider=self.lider_sur)
        for dias_antes in range(3):
            fecha = DIA - dt.timedelta(days=dias_antes)
            for c in (norte, sur):
                JornadaDeCuadrilla.objects.create(
                    org=org, cuadrilla=c, fecha=fecha,
                    labor=JornadaDeCuadrilla.INSTALACION)
        self.numero = 0

    def orden(self, de, barrio, *, programada=None, iniciada=None, asignada=None,
              estado=OrdenTrabajo.ASIGNADA, coordenadas=None):
        self.numero += 1
        lat, lng = coordenadas or (None, None)
        o = OrdenTrabajo.objects.create(
            org=self.org, numero=self.numero, tipo_trabajo_version=self.version,
            estado_operativo=estado, zona=barrio,
            prioridad=OrdenTrabajo.PRIORIDAD_MEDIA,
            cliente_nombre="Zoraida Pérez", cliente_telefono="3113683499",
            cliente_direccion="Calle 45 # 12-30", gps_lat=lat, gps_lng=lng,
            programada_para=programada, iniciada_en=iniciada)
        a = AsignacionTrabajo.objects.create(orden=o, profile=de, rol="tecnico",
                                             es_principal=True)
        if asignada is not None:
            AsignacionTrabajo.objects.filter(pk=a.pk).update(asignado_en=asignada)
        return o


@pytest.fixture
def armado(org_a):
    a = Armado(org_a)
    n, s = a.lider_norte, a.lider_sur
    #  EL DÍA DEL CRUCE: Norte y Sur en CANDELARIA.
    a.orden(n, "CANDELARIA", programada=_a_las(DIA), coordenadas=(10.9, -74.8))
    a.orden(n, "CANDELARIA", programada=_a_las(DIA), coordenadas=(0, 0))
    #  Programada TRES DÍAS ANTES y hecha el día del cruce: el reparto toma lo
    #  atrasado sin mover 'programada_para'. Cuenta el día en que se empezó
    #  (y ese día anterior Sur ni tenía jornada: contada ahí, no habría cruce).
    a.orden(s, "CANDELARIA", programada=_a_las(DIA - dt.timedelta(days=3)),
            iniciada=_a_las(DIA, 10), coordenadas=(10.9, -74.7))
    #  Ni programada ni iniciada: cuenta por cuándo se asignó.
    a.orden(n, "SOLEDAD", asignada=_a_las(DIA, 9))
    #  Sur en SOLEDAD, pero CANCELADA: no fue nadie, no hace cruce.
    a.orden(s, "SOLEDAD", programada=_a_las(DIA), estado=OrdenTrabajo.CANCELADA)
    #  Norte en SABANAGRANDE el día del cruce; Sur ahí la NOCHE ANTERIOR a las
    #  23:30 de Bogotá, que en UTC ya es el día del cruce. No es cruce.
    a.orden(n, "SABANAGRANDE", programada=_a_las(DIA))
    a.orden(s, "SABANAGRANDE", programada=_a_las(DIA - dt.timedelta(days=1), 23, 30))
    #  Sin barrio, y en CANDELARIA de alguien sin jornada: no entran al cruce.
    a.orden(n, "", programada=_a_las(DIA))
    a.orden(a.sin_jornada, "CANDELARIA", programada=_a_las(DIA))
    #  El día anterior, solo Norte en MALAMBO; dos días antes, Norte dos veces.
    a.orden(n, "MALAMBO", programada=_a_las(DIA - dt.timedelta(days=1)))
    a.orden(n, "MALAMBO", programada=_a_las(DIA - dt.timedelta(days=2)))
    a.orden(n, "MALAMBO", programada=_a_las(DIA - dt.timedelta(days=2), 15))
    #  Fuera del período (7 días hasta el 10/10 empiezan el 04/10).
    a.orden(s, "CANDELARIA", programada=_a_las(dt.date(2026, 10, 3)))
    return a


def test_cuenta_un_solo_cruce_y_el_dia_en_el_reloj_de_la_empresa(armado):
    m = medir(armado.org, dias=7, hasta=HASTA)
    assert m["cruces"] == [{"fecha": DIA, "barrio": CANDELARIA,
                            "cuadrillas": 2, "ordenes": 3}]
    assert m["dias_con_cruce"] == 1


def test_cuenta_las_ordenes_y_las_coordenadas(armado):
    m = medir(armado.org, dias=7, hasta=HASTA)
    #  11 en el período: de las 13 armadas, sin la cancelada ni la del 03/10.
    assert m["ordenes"] == 11
    #  Dos con coordenadas: la de (0, 0) no cuenta.
    assert m["con_coordenadas"] == 2
    assert m["sin_barrio"] == 1
    assert m["sin_cuadrilla"] == 1


def test_otra_empresa_no_entra(armado, org_b):
    otra = Armado(org_b)
    otra.orden(otra.lider_norte, "CANDELARIA", programada=_a_las(DIA))
    otra.orden(otra.lider_sur, "CANDELARIA", programada=_a_las(DIA))
    m = medir(armado.org, dias=7, hasta=HASTA)
    assert m["ordenes"] == 11
    assert m["cruces"][0]["cuadrillas"] == 2
    assert m["cruces"][0]["ordenes"] == 3


def test_la_salida_no_lleva_datos_del_cliente(armado, monkeypatch):
    from campo import tasks

    monkeypatch.setattr(tasks, "_ahora_local",
                        lambda org: _a_las(HASTA))
    salida = io.StringIO()
    call_command("informe_de_cruces", "--org", str(armado.org.id), "--dias", "7",
                 stdout=salida)
    texto = salida.getvalue()
    assert CANDELARIA in texto and "2026-10-09" in texto
    for dato in ("Zoraida", "3113683499", "Calle 45", "10.9", "-74.8",
                 "Norte", "Sur"):
        assert dato not in texto, dato
    #  El porcentaje: 2 de 11.
    assert "18,2 %" in texto


def test_una_empresa_que_no_existe_o_un_rango_imposible_se_niegan(org_a):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("informe_de_cruces", "--org", "no-es-un-uuid", "--dias", "7")
    with pytest.raises(CommandError):
        call_command("informe_de_cruces", "--org", str(org_a.id), "--dias", "0")
