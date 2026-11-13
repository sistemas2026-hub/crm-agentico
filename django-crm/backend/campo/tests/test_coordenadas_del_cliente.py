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
    def test_los_vacios_del_proveedor(self, texto, caplog):
        #  QUE MIDE EL `caplog`, Y POR QUE HIZO FALTA (10/11/2026).
        #
        #  Esta prueba afirmaba solo `(None, None)`, que es el valor por
        #  DEFECTO de `leer`: una mutacion que borraba la lista `AUSENTES`
        #  entera la dejo en verde --ninguno de estos nueve textos matchea
        #  ningun regex, asi que caen igual al final--. Era la misma
        #  supervivencia que el modulo ya tenia escrita para "0,0" el
        #  05/11/2026, extendida a los nueve.
        #
        #  Lo que SOLO esta lista produce es el silencio: cortar antes de
        #  llegar al log. Sin ella, cada campo vacio del proveedor emite
        #  «coordenadas con forma no reconocida» -- y hay 2.982 clientes con
        #  el campo vacio, medido el 10/11/2026: 2.982 lineas por pasada
        #  avisando de un formato nuevo que no existe.
        with caplog.at_level("INFO"):
            assert cc.leer(texto) == (None, None)
        assert caplog.records == [], (
            "un vacio conocido no es un formato nuevo: no se registra")

    @pytest.mark.parametrize("texto", [
        "10,9108,-74,8186",                      # coma decimal: cuatro numeros
        "10.9108",                               # uno solo
        "10.9108,-74.8186,30",                   # tres
        "(10.9108, -74.8186)",                   # entre parentesis
        "lat 10.9108 lng -74.8186",              # con palabras
        "https://maps.google.com/?q=10.9,-74.8",  # un enlace pegado
        "10.9108;-74.8186",                      # punto y coma
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
    def test_lo_que_no_es_texto_no_se_interpreta(self, valor, caplog):
        #  Llega de una API ajena: puede venir cualquier cosa, y ninguna de
        #  estas es la forma medida.
        #
        #  El `caplog` por la misma razon que arriba (10/11/2026): afirmar solo
        #  `(None, None)` dejaba pasar una mutacion que cambiaba el `isinstance`
        #  por `crudo = str(crudo)`. `str(10.9108)` es "10.9108", un numero
        #  suelto que ningun regex reconoce, asi que el resultado era el mismo y
        #  la prueba no lo veia. Lo que cambia es el log: la version aflojada
        #  registra una silueta por cada valor que no es texto.
        with caplog.at_level("INFO"):
            assert cc.leer(valor) == (None, None)
        assert caplog.records == [], (
            "esto no es un formato nuevo del proveedor: es otro tipo de dato")


class TestLasFormasMedidasEl10De11:
    """TRES FORMAS MAS, Y POR QUE SE AGREGAN (10/11/2026).

    El modulo decia: «el dia que aparezca otra forma, el camino es MEDIRLA y
    agregarla aca con su fecha, no aflojar el parseo por si acaso». Aparecieron.

    Medido sobre los 4.644 clientes que sirve la API: 591 tenian el dato y el
    parser no lo leia, asi que la pantalla decia «sin ubicacion» teniendo la
    casa. Por forma:

        435  DD°DD'DD.D"a DD°DD'DD.D"a   grados-minutos-segundos
        134  DD.DDDD -DD.DDDD            separados por ESPACIO, no por coma
          4  DD.DDDDDD°a, DD.DDDDDD°a    decimal con el hemisferio en la letra
          4  aa. DDa # Da-DD             una direccion de calle: NO es coordenada
          4  --DD.DDDD                   doble signo: basura

    Se agregan las tres primeras --573 clientes-- y las dos ultimas siguen
    saliendo ausentes, que es la verdad: de una direccion de calle no se deduce
    un punto, y eso ya esta decidido en `dia_publicado.py` (no se geocodifica).
    """

    def test_grados_minutos_segundos_la_forma_de_435_clientes(self):
        #  Convertido a mano: 10 + 52/60 + 30.1/3600 = 10.875027...
        lat, lng = cc.leer("10°52\'30.1\"N 74°55\'20.2\"W")
        assert lat == pytest.approx(10.875028, abs=1e-6)
        #  El hemisferio W es el que pone el signo: el numero viene SIN signo.
        assert lng == pytest.approx(-74.922278, abs=1e-6)

    def test_el_hemisferio_decide_el_signo_y_no_el_orden(self):
        #  La letra dice cual es cual, asi que invertido tambien se lee bien.
        #  No es adivinar: el dato lo trae escrito.
        derecho = cc.leer("10°52\'30.1\"N 74°55\'20.2\"W")
        al_reves = cc.leer("74°55\'20.2\"W 10°52\'30.1\"N")
        assert al_reves == derecho
        #  Y EL VALOR, no solo la igualdad. Medido el 10/11/2026: desconectar
        #  la rama de DMS dejaba esta prueba en verde, porque
        #  `(None, None) == (None, None)` es verdadero y entonces decia que el
        #  hemisferio seguia decidiendo el signo cuando ya no decidia nada.
        assert al_reves == pytest.approx((10.875028, -74.922278), abs=1e-6)

    def test_dos_latitudes_juntas_no_se_adivinan(self):
        #  Sin una longitud no hay punto, y poner una al azar seria inventar
        #  media coordenada.
        assert cc.leer("10°52\'30.1\"N 11°55\'20.2\"S") == (None, None)

    def test_el_sur_y_el_oeste_son_negativos(self):
        lat, lng = cc.leer("10°00\'00\"S 74°00\'00\"E")
        assert lat == pytest.approx(-10.0)
        assert lng == pytest.approx(74.0)

    @pytest.mark.parametrize("texto", [
        "10°99\'00\"N 74°00\'00\"W",    # 99 minutos no existen
        "10°00\'99\"N 74°00\'00\"W",    # 99 segundos tampoco
    ])
    def test_minutos_o_segundos_imposibles_salen_ausentes(self, texto):
        #  60 minutos son un grado: pasar de ahi es un dato roto, y corregirlo
        #  por las nuestras moveria la casa sin que nadie se enterara.
        assert cc.leer(texto) == (None, None)

    def test_separados_por_espacio_la_forma_de_134_clientes(self):
        #  Hasta hoy esta estaba en la lista de «no se adivina», por no estar
        #  medida. Lo esta: 134 casos, y el signo del segundo componente lo
        #  trae el propio texto.
        assert cc.leer("10.9108 -74.8186") == (10.9108, -74.8186)

    def test_el_espacio_de_mas_tampoco_molesta(self):
        #  Dos de los casos medidos traen doble espacio.
        assert cc.leer("10.9108  -74.8186") == (10.9108, -74.8186)

    def test_el_doble_signo_sigue_siendo_basura(self):
        #  Cuatro casos medidos. `--74` no es -74 ni 74: es un dato que alguien
        #  escribio mal, y elegir uno de los dos es inventar.
        #
        #  CUAL ES LA RED, MEDIDO (10/11/2026). Esta prueba sobrevivio a
        #  aflojar el `-?` a `-*` en los dos patrones: con el regex abierto,
        #  `--74.8186` MATCHEA, y lo que lo ataja es el `float()` de `_partir`
        #  --su `ValueError`--. O sea que la red no era la que el comentario del
        #  modulo decia. Las dos juntas son cinturon y tirantes, y esta prueba
        #  ahora dice cual es cual.
        assert cc.leer("10.9108 --74.8186") == (None, None)
        assert cc.leer("10.9108,--74.8186") == (None, None)
        #  El tramo del regex, afirmado aparte: un solo signo y no dos.
        assert cc._PAR_ESPACIO.match("10.9108 --74.8186") is None
        assert cc._PAR.match("10.9108,--74.8186") is None
        #  Y la segunda red, la que de verdad trabajo cuando el regex aflojo.
        with pytest.raises(ValueError):
            float("--74.8186")

    def test_decimal_con_el_hemisferio_en_letra(self):
        #  Los dos numeros vienen POSITIVOS y la letra dice el signo. Leerlo
        #  ignorando la letra pondria la casa en el otro lado del planeta.
        assert cc.leer("10.910800°N, 74.818600°W") == (10.9108, -74.8186)
        assert cc.leer("10.910800°N,74.818600°W") == (10.9108, -74.8186)

    def test_un_signo_que_contradice_a_la_letra_sale_ausente(self):
        #  `-10.9°N` dice dos cosas opuestas. No se elige una.
        assert cc.leer("-10.910800°N, 74.818600°W") == (None, None)

    def test_la_direccion_de_calle_sigue_sin_ser_un_punto(self, caplog):
        #  Cuatro casos medidos. De una direccion no se deduce una coordenada,
        #  y geocodificarla es justo lo que el modulo decidio no hacer.
        #
        #  Y SE REGISTRA COMO FORMA DESCONOCIDA, que es la diferencia con los
        #  vacios de arriba: un vacio es normal y calla; una direccion en el
        #  campo de coordenadas es un dato mal cargado del que alguien tiene
        #  que enterarse. Sin esta parte la prueba era un marcador de
        #  intencion: ninguna de las 24 mutaciones de la pasada del 10/11/2026
        #  la mataba.
        with caplog.at_level("INFO"):
            assert cc.leer("Cl. 45c # 3D-21") == (None, None)
        siluetas = [getattr(r, "forma", "") for r in caplog.records]
        assert "aa. DDa # Da-DD" in siluetas, (
            "la forma se registra, para que alguien la vea; el valor no")
        assert not any("45c" in s for s in siluetas), "y sin el domicilio"

        assert cc.leer("Cra. 12b # 4-33") == (None, None)

    def test_las_formas_nuevas_tambien_pasan_por_los_limites_del_planeta(self):
        #  La validacion comun no se saltea por entrar por otra puerta.
        assert cc.leer("91°00\'00\"N 74°00\'00\"W") == (None, None)
        assert cc.leer("91.5 -74.8") == (None, None)

    def test_el_cero_exacto_tampoco_pasa_por_las_formas_nuevas(self):
        assert cc.leer("0°00\'00\"N 0°00\'00\"E") == (None, None)
        assert cc.leer("0.0 0.0") == (None, None)


class TestLaFormaSinSeparadorDel12De11:
    """La quinta forma: el menos de la longitud hace de separador.

    MEDIDA EL 12/11/2026 con `cli/medir_coordenadas.py rapilink 5345 5394`,
    que devolvio estas dos siluetas y ninguna coordenada:

        5345   DD.DDDDDD-DD.DDDDDD
        5394   DD.DDDDD-DD,DDDDDD

    Los digitos de aca abajo son otros: una coordenada de un cliente de verdad
    no va en un archivo del repositorio. Lo que se conserva es LA FORMA, que es
    lo unico que la guarda necesita.
    """

    #  Mismo punto escrito de las dos maneras. Que las dos den LO MISMO es la
    #  afirmacion: no alcanza con que cada una parsee, tienen que coincidir.
    PEGADA = "10.910800-74.818600"
    PEGADA_CON_COMA = "10.91080-74,818600"

    def test_sin_separador_se_lee(self):
        assert cc.leer(self.PEGADA) == (10.9108, -74.8186)

    def test_con_la_coma_como_decimal_tambien(self):
        #  EL CASO QUE MUERDE. Partir esto por la coma --que es lo que hace la
        #  forma buena-- da '10.91080-74' y '818600'. Antes de hoy salia
        #  ausente por accidente: lo atajaba el patron de la coma fallando.
        assert cc.leer(self.PEGADA_CON_COMA) == (10.9108, -74.8186)

    def test_las_dos_escrituras_dan_el_MISMO_punto(self):
        assert cc.leer(self.PEGADA) == cc.leer(self.PEGADA_CON_COMA)

    def test_el_orden_sigue_siendo_lat_lng(self):
        #  EL ERROR QUE MANDA AL TECNICO AL MAR, otra vez: con la latitud y la
        #  longitud al reves el pin cae en el Atlantico y se lee como un hecho.
        #  Barranquilla es ~10.9 N y ~-74.8 W.
        lat, lng = cc.leer(self.PEGADA)
        assert 0 < lat < 15, "la latitud es el PRIMER componente"
        assert -80 < lng < -70, "la longitud es el SEGUNDO, y es negativa"

    def test_la_longitud_POSITIVA_pegada_no_se_adivina(self):
        #  SIN EL MENOS NO HAY CORTE UNIVOCO: '10.9108074.818600' podria
        #  partirse en cualquier lado. Que salga ausente es el resultado
        #  correcto, no una limitacion -- es la diferencia entre leer y
        #  adivinar.
        assert cc.leer("10.9108074.818600") == (None, None)

    def test_el_doble_signo_sigue_sin_entrar_por_aca(self):
        #  La forma nueva admite un menos en el segundo componente. Dos no.
        assert cc.leer("10.910800--74.818600") == (None, None)

    def test_fuera_del_planeta_no_pasa_por_la_puerta_nueva(self):
        #  La validacion de planeta vive en `leer`, no en cada patron: una
        #  forma nueva NO puede traer su propia puerta de atras.
        assert cc.leer("91.500000-74.818600") == (None, None)
        assert cc.leer("10.910800-274.818600") == (None, None)

    def test_el_cero_tampoco(self):
        assert cc.leer("0.000000-0.000000") == (None, None)

    def test_la_forma_buena_sigue_leyendose_igual(self):
        #  EL CONTROL QUE IMPORTA: el patron nuevo se prueba ANTES que varios
        #  de los viejos, asi que podria robarles un caso. 1.071 clientes
        #  dependen de que este siga dando lo mismo.
        assert cc.leer(BUENA) == (10.9108, -74.8186)
        assert cc.leer("10.9108 -74.8186") == (10.9108, -74.8186)


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
