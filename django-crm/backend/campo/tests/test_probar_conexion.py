# -*- coding: utf-8 -*-
"""
EL PING DEL TECNICO: LO QUE DICE, Y LO QUE SE CUIDA DE NO DECIR.

Estas pruebas no levantan el motor. Miden el borde que este backend controla:
que se le pide, que se hace con lo que contesta, y --sobre todo-- que "no se
pudo medir" nunca se confunda con "se midio y no respondio". Esa distincion es
el motivo entero del endpoint: la primera se reintenta, la segunda es un dato
sobre el equipo del cliente.

Se afirma sobre el EFECTO (lo que sale del servicio), nunca sobre que exista
la funcion. Una prueba que dice que un mecanismo existe no prueba que
funcione -- leccion cara de este repositorio, cometida el mismo dia tres
veces.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from campo.services import telemetria


class _Respuesta:
    def __init__(self, status_code, cuerpo=None, ilegible=False):
        self.status_code = status_code
        self._cuerpo = cuerpo
        self._ilegible = ilegible

    def json(self):
        if self._ilegible:
            raise ValueError("no es json")
        return self._cuerpo


class _Orden:
    def __init__(self, contexto):
        self.contexto = contexto


# Forma real de la respuesta de WispHub despues de la lista blanca del motor:
# una lista de objetos, con el conteo en texto. Medido en agosto de 2026 y
# documentado en motor.py::_buscar_campo -- buscar en el primer nivel no lo
# encuentra, y eso ya costo un bug.
PING_REAL = {
    "total": 4,
    "resultados": [
        {"ping-1": {"avg-rtt": "1ms401us", "packet-loss": "0"}},
        {"ping-2": {"avg-rtt": "1ms388us", "packet-loss": "0"}},
        {"ping-3": {"avg-rtt": "1ms502us", "packet-loss": "0"}},
        {"ping-exitoso": "3 de 3"},
    ],
}


class ProbarConexionTest(SimpleTestCase):

    def _orden(self, servicio="5832"):
        return _Orden({"contexto_disponible": True, "servicio": servicio})

    # -- lo que se manda --------------------------------------------------

    def test_el_id_del_servicio_sale_de_la_ficha_congelada(self):
        """No se vuelve a resolver: un cliente puede tener mas de un servicio,
        y el numero que importa es el que quedo atado a ESTE trabajo."""
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, {"resultado": PING_REAL})) as post:
            telemetria.probar_conexion(self._orden("7001"))

        self.assertEqual(post.call_args.kwargs["json"], {"id_servicio": "7001"})

    def test_sin_servicio_no_se_llama_a_nadie(self):
        """Sin identificador no hay a que equipo pingear. Se levanta antes de
        salir a la red, no se manda una consulta sin filtro."""
        with patch.object(telemetria.requests, "post") as post:
            with self.assertRaises(telemetria.SinServicioParaPing):
                telemetria.probar_conexion(self._orden(""))
        post.assert_not_called()

    # -- lo que se devuelve -----------------------------------------------

    def test_el_conteo_viaja_crudo_y_sin_veredicto(self):
        """'3 de 3' es texto y se queda en texto. Esta medido dos veces que el
        mismo equipo sano da 1, 2 y 3 de 3 en corridas seguidas: convertirlo a
        numero invita a compararlo, y un ping no es un veredicto."""
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, {"resultado": PING_REAL})):
            r = telemetria.probar_conexion(self._orden())

        self.assertTrue(r["ok"])
        self.assertEqual(r["respondieron"], "3 de 3")
        self.assertNotIn("veredicto", r)
        self.assertNotIn("exitoso", r)

    def test_las_tres_latencias_van_por_separado(self):
        """Promediarlas esconde lo que le importa a quien esta en la casa: si
        el enlace es intermitente o esta caido parejo."""
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, {"resultado": PING_REAL})):
            r = telemetria.probar_conexion(self._orden())

        self.assertEqual(r["latencias"], ["1ms401us", "1ms388us", "1ms502us"])

    def test_un_cero_de_tres_es_una_medicion_valida(self):
        """El caso que mas importa distinguir: el equipo NO respondio. Eso es
        un dato, no un fallo -- 'ok' sigue siendo True."""
        sin_respuesta = {"total": 1, "resultados": [{"ping-exitoso": "0 de 3"}]}
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, {"resultado": sin_respuesta})):
            r = telemetria.probar_conexion(self._orden())

        self.assertTrue(r["ok"])
        self.assertEqual(r["respondieron"], "0 de 3")

    def test_no_traslada_la_ip_ni_el_resto_del_crudo(self):
        """'ping-1' trae 'host', que es la IP del cliente. Ya se filtro una vez
        por reenviar el objeto entero; aca se arma lo que se muestra."""
        con_host = {
            "total": 2,
            "resultados": [
                {"ping-1": {"avg-rtt": "1ms", "host": "172.16.40.70"}},
                {"ping-exitoso": "1 de 3"},
            ],
        }
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, {"resultado": con_host})):
            r = telemetria.probar_conexion(self._orden())

        self.assertNotIn("172.16.40.70", str(r))

    # -- lo que NO se puede confundir con una medicion ---------------------

    def test_el_motor_caido_no_es_un_equipo_que_no_responde(self):
        with patch.object(telemetria.requests, "post",
                          side_effect=ConnectionError("sin ruta")):
            r = telemetria.probar_conexion(self._orden())

        self.assertFalse(r["ok"])
        self.assertEqual(r["motivo"], "motor_no_responde")
        self.assertNotIn("respondieron", r)

    def test_la_herramienta_no_habilitada_se_dice_por_su_nombre(self):
        """403 del motor = el tenant no declaro 'invocable_por_servicio'. Es un
        error de configuracion nuestro, no del equipo del cliente, y leerlo
        como 'no responde' mandaria a un tecnico a revisar una roseta sana."""
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(403)):
            r = telemetria.probar_conexion(self._orden())

        self.assertFalse(r["ok"])
        self.assertEqual(r["motivo"], "ping_no_habilitado")

    def test_una_respuesta_sin_conteo_no_se_inventa(self):
        """La llamada salio y no trajo el numero. No se rellena con '0 de 3':
        eso seria afirmar que el equipo no respondio cuando lo que pasa es que
        no se sabe."""
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, {"resultado": {"total": 0,
                                                                      "resultados": []}})):
            r = telemetria.probar_conexion(self._orden())

        self.assertFalse(r["ok"])
        self.assertEqual(r["motivo"], "sin_conteo")

    def test_json_ilegible_tampoco_se_interpreta(self):
        with patch.object(telemetria.requests, "post",
                          return_value=_Respuesta(200, ilegible=True)):
            r = telemetria.probar_conexion(self._orden())

        self.assertFalse(r["ok"])
        self.assertEqual(r["motivo"], "respuesta_ilegible")
