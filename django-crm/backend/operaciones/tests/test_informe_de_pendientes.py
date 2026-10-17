# -*- coding: utf-8 -*-
"""
El informe de pendientes dice, por ticket, por qué se queda y qué pasaría con
cada cambio de regla, y no deja salir datos del cliente. Es lo que se pega
en una conversación para decidir las reglas con los tickets reales.
"""

import re
import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from operaciones import diagnostico_de_ticket as dxt
from operaciones import medicion_de_fallas as mdf
from operaciones import paso_a_despacho as pad
from operaciones.models import PropuestaSupervisor as P

pytestmark = pytest.mark.django_db

CLIENTE = "Zoraida Clientela"
TELEFONO = "3113683499"


def _caso(org, **campos):
    from cases.models import Case

    datos = dict(
        org=org, name=f"Sin internet, {CLIENTE}", status="New",
        priority="Normal", is_active=True, provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:6]}",
        external_service_id="3614", external_status="Nuevo",
        external_fetched_at=timezone.now(),
        external_client_name=CLIENTE,
        description=f"La señora {CLIENTE} dice que no tiene servicio. Tel {TELEFONO}.")
    datos.update(campos)
    return Case.objects.create(**datos)


def _pendiente(org, *, grupo, caso=None, confianza="alta", medida=None):
    caso = caso or _caso(org)
    p = P.objects.create(
        org=org, tipo_senal=P.TICKET_SIN_DIAGNOSTICO, origen_tipo="case",
        origen_id=str(caso.id), estado=P.PROPUESTA,
        accion_propuesta=f"Llamar a {CLIENTE}", motivo="x", prioridad=30,
        evidencia=[{
            "fuente": dxt.FUENTE, "id": "x",
            "dato": f"{dxt.ETIQUETA_LECTURA}sin servicio, el cliente deja el "
                    f"tel {TELEFONO} (confianza media)",
            "observado_en": timezone.now().isoformat(),
            "grupo": grupo, "labor": "", "labor_verificada": False,
            "labor_porque": "", "confianza": "media",
            "confianza_del_grupo": confianza}])
    if medida is not None:
        mdf.escribir(p, mdf.de_la_respuesta(medida), timezone.now())
    return caso.external_ticket_id


def _medida(estado, causa="", dbm=None):
    senal = "sin_dato" if dbm is None else ("buena" if -25 <= dbm <= -8 else "debil")
    return {"estado": estado, "causa_caida": causa, "senal": senal,
            "senal_dbm": dbm, "motivo": ""}


def _correr(org):
    out = StringIO()
    call_command("informe_de_pendientes", "--org", str(org.id), stdout=out)
    return out.getvalue()


def _fila(salida, ticket):
    linea = next(fila for fila in salida.splitlines() if fila.startswith(ticket))
    return re.split(r"\s{2,}", linea.strip())


def test_dice_por_ticket_que_pasaria_con_cada_regla(org_a):
    los = _pendiente(org_a, grupo=pad.FALLA_DE_SERVICIO,
                     medida=_medida("caido", causa="fibra"))
    en_rango = _pendiente(org_a, grupo=pad.FALLA_DE_SERVICIO,
                          medida=_medida("en_linea", dbm=-21.0))
    trabajo = _pendiente(org_a, grupo=pad.TRABAJO_PEDIDO, confianza="media")
    cerrado = _pendiente(org_a, grupo=pad.FALLA_DE_SERVICIO,
                         caso=_caso(org_a, status="Closed"),
                         medida=_medida("caido", causa="fibra"))
    sin_grupo = _pendiente(org_a, grupo="")

    salida = _correr(org_a)

    #  columnas: ticket edad grupo conf caso medicion por_que con_LOS con_media
    assert _fila(salida, los)[6:9] == ["LOS", "SI", "-"]
    assert _fila(salida, en_rango)[6:9] == ["en rango", "-", "-"]
    assert _fila(salida, trabajo)[6:9] == ["confianza", "-", "SI"]
    assert _fila(salida, cerrado)[4].startswith("cerrado Dexter")
    assert _fila(salida, cerrado)[6:9] == ["caso", "-", "-"]
    assert _fila(salida, sin_grupo)[6] == "sin grupo"
    assert ("pendientes=5 · pasan hoy=0 · pasarian con LOS=1 · "
            "pasarian con confianza media=1") in salida


def test_no_deja_salir_datos_del_cliente(org_a):
    _pendiente(org_a, grupo=pad.FALLA_DE_SERVICIO,
               medida=_medida("en_linea", dbm=-21.0))

    salida = _correr(org_a)

    assert "sin servicio" in salida, "la hipotesis tapada tiene que salir"
    for dato in (CLIENTE, "Zoraida", TELEFONO, "Llamar a"):
        assert dato not in salida, f"el informe escribio {dato!r}"


def test_dice_cuantas_veces_se_leyo_y_que_descarto_el_modelo(org_a):
    """
    La diferencia entre "el modelo no supo" y "lo dijo con otra forma": la
    segunda se arregla sin tocar las reglas, y solo se ve en los descartes.
    """
    from operaciones.razonamiento_modelos import (
        FuenteRazonamiento,
        RazonamientoSupervisor,
    )

    ticket = _pendiente(org_a, grupo="")
    p = P.objects.get(org=org_a)
    for _ in range(2):
        RazonamientoSupervisor.objects.create(
            org=org_a, propuesta=p, fuente=FuenteRazonamiento.LECTURA_TICKET,
            registrado_en=timezone.now(),
            descartes=["'grupo' con un valor que no esta declarado (dijo "
                       "'Obra_de_red'): se descarta, no se elige el mas parecido"])

    salida = _correr(org_a)

    assert _fila(salida, ticket)[9:11] == ["2", "grupo='Obra_de_red'"]


def test_una_que_ya_pasa_cuenta_en_las_tres(org_a):
    debil = _pendiente(org_a, grupo=pad.FALLA_DE_SERVICIO,
                       medida=_medida("en_linea", dbm=-27.0))

    salida = _correr(org_a)

    assert _fila(salida, debil)[6:9] == ["PASA", "SI", "SI"]
    assert "pasan hoy=1" in salida
