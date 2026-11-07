# -*- coding: utf-8 -*-
"""
Partir el texto del ISP en dos numeros, o no partirlo.

LO QUE SE PRUEBA DE VERDAD no es un parseo: es que **un caso dudoso salga como
ausente y no como un punto**. Partir mal este campo no da error -- da una casa
equivocada, y el supervisor lee ese pin como un hecho sobre donde esta su
cuadrilla. El modo de falla es silencioso, asi que la guarda tiene que
apretar del lado del rechazo.

La forma buena es la UNICA medida contra la API real (05/11/2026,
`cli/medir_coordenadas.py rapilink 5832`): `DD.DDDDDD,-DD.DDDDDD`, coma sin
espacio, punto decimal, seis decimales, y el orden `lat,lng` probado por el
signo del segundo componente.
"""
import pytest

from campo import coordenadas_del_cliente as cc

#  El valor real tiene ESTA FORMA, con los digitos cambiados: no se pone una
#  coordenada de un cliente de verdad en un archivo del repositorio.
BUENA = "10.910800,-74.818600"


class TestLoQueSiEs:
    def test_la_forma_medida_se_lee_entera(self):
        assert cc.leer(BUENA) == (10.9108, -74.8186)

    def test_el_orden_es_lat_lng_y_no_al_reves(self):
        #  EL ERROR QUE MANDA AL TECNICO AL MAR. Si alguien invirtiera el
        #  parseo, esto seria (-74.8186, 10.9108) -- una latitud de -74 es la
        #  Antartida y una longitud de 10 es Argelia.
        lat, lng = cc.leer(BUENA)
        assert lat > 0, "la latitud de la costa colombiana es POSITIVA (~10.9 N)"
        assert lng < 0, "la longitud es NEGATIVA (~-74.8 W): el signo lo prueba"

    def test_los_seis_decimales_no_se_pierden(self):
        #  Redondear a tres decimales mueve el punto ~100 m: de la casa a la
        #  otra cuadra.
        lat, _ = cc.leer(BUENA)
        assert lat == 10.9108

    def test_tolera_el_espacio_despues_de_la_coma(self):
        #  No esta en lo medido, pero un espacio no cambia el significado de
        #  nada. Es el unico ablande que el modulo se permite.
        assert cc.leer("10.910800, -74.818600") == (10.9108, -74.8186)
        assert cc.leer("  10.910800,-74.818600  ") == (10.9108, -74.8186)

    def test_sin_decimales_tambien_es_una_coordenada(self):
        assert cc.leer("11,-75") == (11.0, -75.0)


class TestElCeroQueParecVacio:
    """`0,0` es el Golfo de Guinea: valido, y nadie vive ahi."""

    @pytest.mark.parametrize("texto", [
        "0,0", "0.0,0.0", "0, 0", "0.000000,0.000000", "0.0, 0.00",
    ])
    def test_el_cruce_del_ecuador_con_el_meridiano_no_es_un_domicilio(self, texto):
        #  SI ESTO SE ROMPE, el mapa dibuja un pin en el Atlantico con toda
        #  confianza, y la linea «sin ubicacion» --que es la verdad-- deja de
        #  aparecer. Una guarda que solo pregunte «esta vacio?» lo deja pasar.
        assert cc.leer(texto) == (None, None), f"{texto!r} no es una casa"

    def test_pero_un_cero_en_UN_componente_si_vale(self):
        #  El ecuador pasa por Ecuador, Colombia, Brasil, Kenia e Indonesia.
        #  Descartar latitud 0 borraria clientes reales del mapa.
        assert cc.leer("0,-74.818600") == (0.0, -74.8186)
        assert cc.leer("10.910800,0") == (10.9108, 0.0)


class TestLoQueNoSeInterpreta:
    @pytest.mark.parametrize("texto", [
        "", "   ", "None", "none", "NULL", "nan", "-", "n/a", "S/N",
    ])
    def test_los_vacios_del_proveedor(self, texto):
        assert cc.leer(texto) == (None, None)

    @pytest.mark.parametrize("texto", [
        "10,9108,-74,8186",                      # coma decimal: cuatro numeros
        "10.9108",                               # uno solo
        "10.9108,-74.8186,30",                   # tres
        "(10.9108, -74.8186)",                   # entre parentesis
        "lat 10.9108 lng -74.8186",              # con palabras
        "https://maps.google.com/?q=10.9,-74.8",  # un enlace pegado
        "10.9108;-74.8186",                      # punto y coma
        "10.9108 -74.8186",                      # solo espacio
    ])
    def test_una_forma_no_medida_sale_AUSENTE_y_no_adivinada(self, texto):
        #  LA REGLA DEL MODULO. Varias de estas se podrian "arreglar" con una
        #  linea mas, y es justo lo que no se hace: se midio UNA forma. El dia
        #  que aparezca otra se mide y se agrega con su fecha, porque aflojar
        #  el parseo "por si acaso" es como se cuela la casa equivocada.
        assert cc.leer(texto) == (None, None), f"{texto!r} no se adivina"

    @pytest.mark.parametrize("texto", [
        "91,-74.8", "-91,-74.8", "10.9,181", "10.9,-181", "999,999",
    ])
    def test_fuera_del_planeta(self, texto):
        #  No se valida «raro para Colombia»: esto es multi-empresa y el
        #  proximo ISP puede estar en otro pais. Se descarta lo IMPOSIBLE.
        assert cc.leer(texto) == (None, None)

    def test_los_limites_exactos_SI_entran(self):
        #  El otro borde: sin esto, poner el limite en 0 pasaria la prueba de
        #  arriba y borraria a todo el mundo del mapa.
        assert cc.leer("90,180") == (90.0, 180.0)
        assert cc.leer("-90,-180") == (-90.0, -180.0)

    @pytest.mark.parametrize("valor", [
        None, 0, 10.9108, [10.9, -74.8], {"lat": 10.9}, True,
    ])
    def test_lo_que_no_es_texto_no_se_interpreta(self, valor):
        #  Llega de una API ajena: puede venir cualquier cosa, y ninguna de
        #  estas es la forma medida.
        assert cc.leer(valor) == (None, None)


class TestNoFiltraElDomicilio:
    def test_una_forma_rara_se_registra_SIN_el_valor(self, caplog):
        #  Un log con la coordenada seria el domicilio de una persona en un
        #  archivo de texto. Se registra la silueta, que alcanza para notar
        #  que apareció un formato nuevo.
        import logging
        with caplog.at_level(logging.INFO):
            cc.leer("lat 10.910800 lng -74.818600")

        todo = caplog.text + "".join(
            str(getattr(r, "forma", "")) for r in caplog.records)
        assert "10.9108" not in todo, "la coordenada NO puede quedar en el log"
        assert "74.8186" not in todo
        #  Y sin embargo dice algo util.
        assert any(getattr(r, "forma", "") for r in caplog.records)
