# -*- coding: utf-8 -*-
"""
================================================================================
 FLOTA DE SMARTOLT  --  la cadena get_olts -> get_outage_pons, medida
================================================================================

QUE SE AFIRMA
-------------
Que la lectura de flota encadena las dos llamadas, que DESCUBRE las OLTs en vez
de leerlas de una lista fija, que no inventa ningun id, y que cuando no puede
leer la flota ENTERA levanta en vez de devolver una parte.

Lo ultimo es la mitad del valor: una lectura parcial, aguas abajo, se leeria como
"en esa OLT no hay caidas", y esa es justo la afirmacion que no se puede hacer.

POR QUE NO HAY CREDENCIALES AQUI
--------------------------------
Esta prueba NO llama a SmartOLT. Sustituye 'requests.get' y afirma sobre QUE URLs
se pidieron y en que orden -- que es lo que define la cadena. Llamar al proveedor
de verdad exigiria su clave, y ninguna prueba de este repositorio la necesita
para comprobar el contrato.

Lo que queda SIN verificar y se dice: que la respuesta real de 'get_olts' de la
instancia de un cliente tenga la forma que '_olts_de' tolera. La skill de
smartolt-api la documenta verificada en vivo el 14/08/2026 ('{"olts": [...]}'),
y aqui se prueban las tres formas que el parser acepta.
================================================================================
"""

import os
import sys
import types
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from nucleo.herramientas import flota                           # noqa: E402


class _Respuesta:
    def __init__(self, cuerpo, status=200, revienta_json=False):
        self.status_code = status
        self._cuerpo = cuerpo
        self._revienta = revienta_json

    def json(self):
        if self._revienta:
            raise ValueError("no es json")
        return self._cuerpo


def _herramienta():
    """Lo minimo que 'flota' le pide a la herramienta del catalogo."""
    return types.SimpleNamespace(
        nombre="consultar_caidas_pon_flota", tipo="interno",
        detecta_caidas_flota=True, invocable_por_servicio=True,
        solo_lectura=True, base_url_ref="SMARTOLT_SUBDOMINIO",
        auth_ref="SMARTOLT_API_KEY", auth_esquema="", auth_header="X-Token")


def _pon(afectados, tipo="los"):
    return {"port": "3/1/4", "board": 3, "subscribers": 60,
            "affected": afectados, "type": tipo,
            "since": "2026-10-05 02:15:00"}


def _sobre_outage(pons):
    """La forma verificada de 'get_outage_pons'."""
    return {"response": {"sections": [
        {"key": "los", "groups": [{"subscribers": 60, "pons": pons}]}]}}


class _Entorno:
    """Sustituye base_url/headers y requests.get. Nada sale a la red."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.urls = []
        self._parches = []

    def __enter__(self):
        def get(url, headers=None, timeout=None):
            self.urls.append(url)
            for patron, r in self.respuestas:
                if patron in url:
                    if isinstance(r, Exception):
                        raise r
                    return r
            raise AssertionError(f"URL no prevista por la prueba: {url}")

        self._parches = [
            mock.patch.object(flota.requests, "get", side_effect=get),
            mock.patch.object(flota.ejecutor_http, "base_url_de",
                              return_value="https://ejemplo.smartolt.test"),
            mock.patch.object(flota.ejecutor_http, "headers_de",
                              return_value={"X-Token": "no-es-una-clave"}),
        ]
        for p in self._parches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self._parches):
            p.stop()
        return False


class CadenaDeFlota(unittest.TestCase):

    def test_1_encadena_get_olts_y_despues_get_outage_pons(self):
        """La afirmacion central: DOS llamadas, en ese orden, una por OLT."""
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"id": 3, "name": "OLT-A"},
                                              {"id": 7, "name": "OLT-B"}]})),
            ("get_outage_pons/3", _Respuesta(_sobre_outage([_pon(12)]))),
            ("get_outage_pons/7", _Respuesta(_sobre_outage([]))),
        ]) as e:
            salida = flota.caidas_por_pon(_herramienta(), {})

        self.assertTrue(e.urls[0].endswith("/api/system/get_olts"))
        self.assertIn("get_outage_pons/3", e.urls[1])
        self.assertIn("get_outage_pons/7", e.urls[2])
        self.assertEqual(len(e.urls), 3, "1 + N llamadas, ni una mas")
        self.assertEqual(salida["olts_consultadas"], 2)

    def test_2_las_OLTs_se_DESCUBREN_no_se_configuran(self):
        """
        Los ids consultados son los que devolvio 'get_olts', no una lista fija.

        Se afirma con ids que ninguna configuracion del repositorio menciona: si
        el codigo tuviera una lista quemada, pediria otros.
        """
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"id": 41}, {"id": 42}]})),
            ("get_outage_pons/41", _Respuesta(_sobre_outage([]))),
            ("get_outage_pons/42", _Respuesta(_sobre_outage([]))),
        ]) as e:
            flota.caidas_por_pon(_herramienta(), {})
        self.assertTrue(any("get_outage_pons/41" in u for u in e.urls))
        self.assertTrue(any("get_outage_pons/42" in u for u in e.urls))

    def test_3_el_olt_viaja_en_cada_seccion(self):
        """Sin el olt, dos OLTs con el mismo board/port se pisarian."""
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"id": 3, "name": "OLT-A"},
                                              {"id": 7, "name": "OLT-B"}]})),
            ("get_outage_pons/3", _Respuesta(_sobre_outage([_pon(12)]))),
            ("get_outage_pons/7", _Respuesta(_sobre_outage([_pon(5)]))),
        ]):
            salida = flota.caidas_por_pon(_herramienta(), {})

        secciones = salida["response"]["sections"]
        self.assertEqual(len(secciones), 2)
        self.assertEqual({s["olt_id"] for s in secciones}, {3, 7})
        self.assertEqual({s["olt_nombre"] for s in secciones},
                         {"OLT-A", "OLT-B"})
        #  Y DENTRO DE CADA PON, que es de donde el resumen de aguas abajo
        #  saca la clave 'olt_id/board/port'. Sin esto la clave sale con '?'
        #  en el lugar del olt y dos OLTs se pisan -- paso, y lo cazo la
        #  prueba de extremo a extremo.
        pons = [p for s in secciones
                for g in s.get("groups", []) for p in g.get("pons", [])]
        self.assertEqual(len(pons), 2)
        self.assertEqual({p["olt_id"] for p in pons}, {3, 7})

    def test_4_sin_caidas_devuelve_secciones_vacias_y_NO_un_error(self):
        """
        'Sin hallazgos' es un resultado valido y distinto de 'no se pudo leer'.

        Quien interpreta la diferencia es la capa de fuentes: secciones vacias ->
        SIN_REGISTROS; excepcion -> ERROR. Las dos cosas no se pueden colapsar.
        """
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"id": 3}]})),
            ("get_outage_pons/3", _Respuesta(_sobre_outage([]))),
        ]):
            salida = flota.caidas_por_pon(_herramienta(), {})
        #  La seccion EXISTE y viene sin PONs. Medido: 'get_outage_pons' devuelve
        #  su estructura igual cuando no hay nada, y eso es correcto -- quien
        #  resume aguas abajo cuenta cero PONs. Mi primera version de esta
        #  prueba exigia cero secciones y era la asercion la que estaba mal.
        secciones = salida["response"]["sections"]
        pons = [p for s in secciones
                for g in s.get("groups", []) for p in g.get("pons", [])]
        self.assertEqual(pons, [], "sin caidas = sin PONs, no sin secciones")
        self.assertEqual(salida["olts_consultadas"], 1)

    def test_5_una_OLT_que_no_contesta_invalida_la_lectura_COMPLETA(self):
        """
        El corazon del bloque: no se devuelve lo que trajeron las otras.

        Si devolviera la primera OLT, aguas abajo se leeria como "en la segunda
        no hay caidas" -- y nadie pregunto por la segunda.
        """
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"id": 3}, {"id": 7}]})),
            ("get_outage_pons/3", _Respuesta(_sobre_outage([_pon(12)]))),
            ("get_outage_pons/7", _Respuesta({}, status=503)),
        ]):
            with self.assertRaises(flota.FlotaNoLegible) as c:
                flota.caidas_por_pon(_herramienta(), {})
        self.assertIn("503", str(c.exception))

    def test_6_un_fallo_de_red_no_filtra_la_URL(self):
        """La URL lleva el subdominio de la empresa: va el TIPO, no el texto."""
        with _Entorno([
            ("get_olts", RuntimeError("https://ejemplo.smartolt.test/secreto")),
        ]):
            with self.assertRaises(flota.FlotaNoLegible) as c:
                flota.caidas_por_pon(_herramienta(), {})
        mensaje = str(c.exception)
        self.assertIn("RuntimeError", mensaje)
        self.assertNotIn("smartolt.test", mensaje)
        self.assertNotIn("secreto", mensaje)

    def test_7_cero_OLTs_NO_es_red_sana(self):
        with _Entorno([("get_olts", _Respuesta({"olts": []}))]):
            with self.assertRaises(flota.FlotaNoLegible) as c:
                flota.caidas_por_pon(_herramienta(), {})
        self.assertIn("no devolvio ninguna OLT", str(c.exception))

    def test_8_una_OLT_sin_id_NO_se_consulta_con_un_id_inventado(self):
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"name": "sin id"}]})),
        ]) as e:
            with self.assertRaises(flota.FlotaNoLegible) as c:
                flota.caidas_por_pon(_herramienta(), {})
        self.assertIn("sin identificador", str(c.exception))
        #  Y no se pidio ninguna caida: no hubo segunda llamada.
        self.assertEqual(len(e.urls), 1)

    def test_9_un_tope_de_OLTs_que_se_alcanza_LEVANTA(self):
        """Recortar dejaria una lectura incompleta con aspecto de completa."""
        muchas = [{"id": i} for i in range(flota.TOPE_OLTS + 1)]
        with _Entorno([("get_olts", _Respuesta({"olts": muchas}))]) as e:
            with self.assertRaises(flota.FlotaNoLegible) as c:
                flota.caidas_por_pon(_herramienta(), {})
        self.assertIn("tope", str(c.exception))
        self.assertEqual(len(e.urls), 1, "no se consulto ninguna OLT")

    def test_10_una_respuesta_que_no_es_json_es_ERROR_no_vacio(self):
        with _Entorno([
            ("get_olts", _Respuesta(None, revienta_json=True)),
        ]):
            with self.assertRaises(flota.FlotaNoLegible) as c:
                flota.caidas_por_pon(_herramienta(), {})
        self.assertIn("no es JSON", str(c.exception))

    def test_11_tolera_las_tres_formas_de_sobre_de_get_olts(self):
        """Cada endpoint de este proveedor trae su propio sobre."""
        for crudo in ({"olts": [{"id": 3}]},
                      {"response": [{"id": 3}]},
                      [{"id": 3}]):
            with _Entorno([
                ("get_olts", _Respuesta(crudo)),
                ("get_outage_pons/3", _Respuesta(_sobre_outage([]))),
            ]):
                salida = flota.caidas_por_pon(_herramienta(), {})
            self.assertEqual(salida["olts_consultadas"], 1, crudo)

    def test_12_los_argumentos_se_IGNORAN(self):
        """
        Un filtro por OLT la volveria una lectura parcial con aspecto de total.

        Se le pasa un 'olt_id' y se afirma que consulto LAS DOS igual.
        """
        with _Entorno([
            ("get_olts", _Respuesta({"olts": [{"id": 3}, {"id": 7}]})),
            ("get_outage_pons/3", _Respuesta(_sobre_outage([]))),
            ("get_outage_pons/7", _Respuesta(_sobre_outage([]))),
        ]) as e:
            flota.caidas_por_pon(_herramienta(), {"olt_id": 3})
        self.assertEqual(len([u for u in e.urls if "outage" in u]), 2)

    def test_13_NO_se_llama_a_ninguna_escritura(self):
        """Solo lectura, afirmado sobre el AST y sobre las URLs pedidas."""
        import ast
        import inspect

        arbol = ast.parse(inspect.getsource(flota))
        atributos = {n.attr for n in ast.walk(arbol)
                     if isinstance(n, ast.Attribute)}
        for escritura in ("post", "put", "patch", "delete"):
            self.assertNotIn(escritura, atributos, escritura)
        #  Y ningun endpoint de escritura de SmartOLT nombrado.
        fuente = inspect.getsource(flota).lower()
        for prohibido in ("reboot", "/onu/reboot", "authorize", "catv",
                          "update_onu", "move"):
            self.assertNotIn(prohibido, fuente, prohibido)


class LaDeclaracionDelCatalogo(unittest.TestCase):
    """La herramienta existe en la semilla, y con las banderas correctas."""

    @classmethod
    def setUpClass(cls):
        from nucleo.config.fuente import cargar_config
        cls.config = cargar_config(
            os.path.join(RAIZ, "tenants", "rapilink.config.yaml"))

    def _buscar(self, nombre):
        for h in self.config.herramientas:
            if h.nombre == nombre:
                return h
        return None

    def test_14_la_herramienta_de_flota_esta_declarada(self):
        h = self._buscar("consultar_caidas_pon_flota")
        self.assertIsNotNone(h, "no esta en la semilla del tenant")
        self.assertEqual(h.tipo, "interno")
        self.assertTrue(h.detecta_caidas_flota)
        #  El backend la llama por el servicio: sin esto, el motor la rechaza.
        self.assertTrue(h.invocable_por_servicio)
        self.assertTrue(h.solo_lectura)

    def test_15_NO_declara_una_lista_fija_de_OLTs(self):
        """Se intento una vez y se revirtio. No vuelve por la ventana."""
        crudo = open(os.path.join(RAIZ, "tenants", "rapilink.config.yaml"),
                     encoding="utf-8").read()
        for fijo in ("SMARTOLT_OLT_ID_1", "SMARTOLT_OLT_ID_2"):
            self.assertNotIn(fijo, crudo, fijo)

    def test_16_la_de_flota_y_la_de_un_cliente_son_DISTINTAS(self):
        """
        Las dos existen y no se pisan: una exige 'sn_onu', la otra no parte de
        nadie. Confundirlas fue el riesgo de este bloque.
        """
        flota_h = self._buscar("consultar_caidas_pon_flota")
        cliente_h = self._buscar("consultar_incidente_red")
        self.assertIsNotNone(cliente_h, "la de cliente tiene que seguir ahi")
        self.assertTrue(cliente_h.detecta_incidente)
        self.assertFalse(getattr(cliente_h, "detecta_caidas_flota", False))
        self.assertFalse(flota_h.detecta_incidente)
        #  Y la de cliente NO se volvio invocable por servicio de paso.
        self.assertFalse(cliente_h.invocable_por_servicio)

    def test_17_ninguna_herramienta_de_ESCRITURA_quedo_invocable(self):
        """
        El riesgo de tocar este catalogo: abrir una de escritura sin querer.

        Se afirma sobre TODAS, no solo sobre las que toque: quien tenga el token
        de servicio solo puede ejecutar lo que alguien declaro una por una.
        """
        abiertas = [h.nombre for h in self.config.herramientas
                    if h.invocable_por_servicio and not h.solo_lectura]
        #  Y la de flota quedo del lado correcto: abierta al servicio, y de
        #  LECTURA. Si alguien le quitara 'solo_lectura', aparece arriba.
        self.assertIn("consultar_caidas_pon_flota",
                      [h.nombre for h in self.config.herramientas
                       if h.invocable_por_servicio and h.solo_lectura])
        #  Las que ya estaban, nombradas: si aparece una mas, esto se pone rojo.
        #  El conjunto MEDIDO el 05/10/2026, no uno supuesto: la primera
        #  version de esta prueba lo adivino y nombraba 'registrar_pago', que
        #  NO esta abierta al servicio -- y de las seis que si lo estan, cuatro
        #  no las habia nombrado.
        self.assertEqual(
            sorted(abiertas),
            sorted(["actualizar_sn_onu", "cerrar_caso_crm",
                    "cerrar_ticket_operativo", "completar_ticket_instalacion",
                    "crear_ticket_instalacion",
                    "reasignar_ticket_instalacion"]),
            "cambio el conjunto de herramientas de ESCRITURA invocables por "
            "servicio: revisar una por una antes de aceptar")


if __name__ == "__main__":
    unittest.main(verbosity=2)
