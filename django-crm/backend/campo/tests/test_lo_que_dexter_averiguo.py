# -*- coding: utf-8 -*-
"""
LO QUE EL ASISTENTE YA AVERIGUO LLEGA AL TECNICO, Y SIN SU CEDULA.

Dexter habla con el cliente antes de que exista la orden: verifica identidad,
mide el equipo, descarta causas y deja escrito QUE FALTA AVERIGUAR. Hasta el
25/09/2026 todo eso se quedaba en asistente.conversations -- el motor lo
devolvia en la MISMA respuesta que el contexto, y este backend lo tiraba. El
tecnico llegaba a la casa a preguntar lo que el cliente ya habia contestado
por WhatsApp.

Y el numero del ticket del ISP igual: la orden mostraba el UUID del caso, que
no le sirve a nadie. La oficina y el tecnico hablan de "el 93426".

LO QUE ESTAS PRUEBAS CUIDAN, y no es solo que el dato llegue:

  - que la CEDULA no baje a la orden. 'resumen' lo redacta el modelo y trae el
    documento cuando lo verifico ("Mario Sabanagrande, cedula 000021", visto
    en produccion). La ficha se congela en la orden y viaja al telefono.
  - que el SERIAL, la IP y el numero de ticket sobrevivan. Una redaccion que
    se lleva por delante el serial deja al tecnico sin la llave para buscar el
    equipo, y sirve de nada.

    python manage.py test campo.tests.test_lo_que_dexter_averiguo
"""
from django.test import SimpleTestCase

from campo.services.despacho import (
    _lo_que_el_asistente_averiguo,
    _sin_documentos,
    _ticket_del_proveedor,
)


class _Caso:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


#  Tal como llega de produccion (asistente.conversations).
CONVERSACION = {
    "caso_manual": "sin_senal_tv",
    "motivo_escalamiento": "solicitud_explicita",
    "etiqueta": "soporte_tecnico",
    "resumen": "El cliente (Mario Sabanagrande, cedula 000021) reporta que no "
               "tiene senal de TV. Se verifico identidad.",
    "escalada_siguiente_paso": "Confirmar con el cliente si el coaxial lo "
                               "instalo la empresa o lo modifico el.",
}


class LoQueDexterAveriguoTest(SimpleTestCase):

    # -- lo que llega -----------------------------------------------------

    def test_el_siguiente_paso_llega_literal(self):
        """Es el mas util de los tres y no es una etiqueta: es la frase que
        dice que falta averiguar."""
        d = _lo_que_el_asistente_averiguo(CONVERSACION)

        self.assertIn("coaxial", d["siguiente_paso"])
        self.assertIn("instalo la empresa", d["siguiente_paso"])

    def test_tambien_el_caso_y_el_motivo(self):
        d = _lo_que_el_asistente_averiguo(CONVERSACION)

        self.assertEqual(d["caso"], "sin_senal_tv")
        self.assertEqual(d["motivo_escalada"], "solicitud_explicita")

    def test_sin_conversacion_no_se_inventa_nada(self):
        """Un caso importado del ISP no tiene conversacion detras. Eso no es un
        error: es que nadie hablo con el cliente todavia."""
        self.assertEqual(_lo_que_el_asistente_averiguo({}), {})
        self.assertEqual(_lo_que_el_asistente_averiguo(None or {}), {})

    # -- lo que NO puede bajar a la orden ---------------------------------

    def test_la_cedula_no_baja_a_la_orden(self):
        """La ficha se congela en la orden de trabajo y viaja al telefono. El
        nombre si --ya esta en la orden--; el documento no."""
        d = _lo_que_el_asistente_averiguo(CONVERSACION)

        self.assertNotIn("000021", d["resumen"])
        self.assertIn("(documento)", d["resumen"])
        self.assertIn("Mario Sabanagrande", d["resumen"],
                      "el nombre si puede ir: el tecnico visita a esa persona")

    def test_el_serial_sobrevive_a_la_redaccion(self):
        """Una redaccion que se lleva el serial deja al tecnico sin la llave
        con la que se busca el equipo en SmartOLT."""
        self.assertEqual(_sin_documentos("La ONU HWTCA6FB5263 esta en linea"),
                         "La ONU HWTCA6FB5263 esta en linea")

    def test_la_ip_sobrevive(self):
        self.assertEqual(_sin_documentos("Su IP es 172.16.40.70"),
                         "Su IP es 172.16.40.70")

    def test_el_numero_de_ticket_sobrevive(self):
        """Un numero precedido de '#' no es un documento: es el ticket, y es
        el unico dato con el que la oficina y el tecnico se refieren al caso."""
        self.assertEqual(_sin_documentos("Importado de wisphub, ticket #93426"),
                         "Importado de wisphub, ticket #93426")

    # -- el ticket del proveedor ------------------------------------------

    def test_el_ticket_trae_numero_y_estado_del_isp(self):
        """'external_status' es el estado EN WISPHUB, que no tiene por que
        coincidir con el del CRM: alguien pudo cerrarlo del otro lado."""
        t = _ticket_del_proveedor(_Caso(
            external_ticket_id="93426", provider="wisphub",
            external_status="Nuevo", external_created_by="DANIELA OSPINO"))

        self.assertEqual(t["numero"], "93426")
        self.assertEqual(t["proveedor"], "wisphub")
        self.assertEqual(t["estado"], "Nuevo")
        self.assertEqual(t["abierto_por"], "DANIELA OSPINO")

    def test_un_caso_sin_ticket_externo_no_inventa_uno(self):
        """Una orden creada a mano desde el CRM no viene de ningun ticket."""
        self.assertEqual(_ticket_del_proveedor(_Caso(external_ticket_id=None)), {})
        self.assertEqual(_ticket_del_proveedor(None), {})
