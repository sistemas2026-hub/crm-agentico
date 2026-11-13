# -*- coding: utf-8 -*-
"""
================================================================================
 RELEER NO ARREGLA UN SESGO  --  11/11/2026, OT #201
================================================================================
LO QUE MIDIO LA PRUEBA EN VIVO
-------------------------------
El usuario cerro la OT #201 con la medicion al salir en -18.0 y la pantalla
marcando -21.0. La doble lectura --construida esa misma manana-- corrio: la
foto se miro CUATRO veces.

    v2  medicion_al_salir  [recibido]  4 analisis
          ia 12:23:36  «1550 nm, -2.10 dBm, 0.682 µW, 2kHz»
          ia 12:23:52  «1550 nm, -2.10 dBm, 0.682 µW, 2kHz»
          ia 12:24:04  «1550 nm, -2.10 dBm, 0.682 µW, 2kHz; punto decimal visible»
          ia 12:24:05  «1550 nm, -2.10 dBm, 0.682 µW, 2kHz»

Las cuatro iguales, y la tercera lo subraya: «punto decimal visible». El
modelo no duda -- esta seguro de su error.

LA DISTINCION QUE FALTABA, Y QUE COSTO UN ARREGLO ENTERO
---------------------------------------------------------
La doble lectura ataca VARIANZA: un modelo que se equivoca distinto cada vez
se delata al segundo intento. Esto es SESGO: lee igual de mal todas las
veces. Ninguna cantidad de relecturas puede arreglarlo, y cada una cuesta.

NO SE REEMPLAZAN. En la vuelta 1 de esa MISMA orden hubo varianza de verdad
--cuatro lecturas de la misma foto, dos de -21.0 y dos de -2.10-- y ahi la
doble lectura hace su trabajo. Las dos cosas conviven.

LO QUE SE HACE, Y LO QUE NO
----------------------------
Se le da al modelo la magnitud que tiene que esperar, ANTES de leer: el
rango que la empresa ya declaro en la plantilla (-60 a -8 en Rapilink), con
el pedido de verificar el punto decimal si lee algo afuera.

Y se le pide VERIFICAR, nunca ajustar. Un pie que diga «tiene que estar
entre X e Y» invita a inventar un numero que encaje, que es peor que leer
mal: un dato falso que pasa todos los filtros. Por el mismo motivo el codigo
NO corrige el punto decimal por su cuenta --seria inventar el dato-- y sigue
descartando lo que no puede salir de ese medidor. El prompt es guia; el
codigo es la garantia (PRD 7.4).

QUE AFIRMAN ESTAS GUARDAS
--------------------------
Que el rango llega al pie, que sale de la plantilla de ESA empresa y no de
una constante, que no se le cuelga a una foto que no es de medicion, y que
la relectura se detiene cuando el modelo ya se repitio.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

ESQUEMA = {
    "pasos": [],
    "campos": [
        {"id": "potencia_al_llegar", "tipo": "decimal",
         "titulo": "Medición al llegar", "reglas": {"min": -60, "max": -8}},
        {"id": "potencia_al_salir", "tipo": "decimal",
         "titulo": "Medición al salir", "reglas": {"min": -60, "max": -8}},
    ],
    "evidencias": [
        {"id": "medicion_al_llegar", "tipo": "foto",
         "titulo": "Foto del medidor al llegar", "obligatorio": True,
         "instrucciones": "Pantalla del medidor con la lectura en dBm."},
        {"id": "medicion_al_salir", "tipo": "foto",
         "titulo": "Foto del medidor al salir", "obligatorio": True,
         "instrucciones": "Pantalla del medidor con la lectura en dBm."},
        {"id": "dano_encontrado", "tipo": "foto",
         "titulo": "Foto del daño", "obligatorio": True,
         "instrucciones": "El elemento dañado."},
    ],
}


#  EL µW SE CALCULA DEL dBm (12/11/2026). Ver el mismo cambio en
#  `test_la_lectura_que_se_pide_dos_veces`: el «0.682 µW» fijo venia de una
#  foto promocional y hace imposible cualquier pantalla de prueba desde que
#  el codigo cruza las dos unidades.
def _texto(dbm: str) -> str:
    try:
        uw = 10 ** (float(str(dbm).replace(",", ".")) / 10.0) * 1000.0
        par = f"{dbm} dBm, {uw:.3f} µW"
    except ValueError:
        par = f"{dbm} dBm"
    return (f"Medidor óptico Rouhan; pantalla legible: 1550 nm, {par}, "
            f"2kHz. CATALOGO: no MUESTRA: si ATENCION: no")


def _orden(org, numero, *, esquema=None, escrito_al_salir="-18.0",
           lecturas_al_salir=("-2.10",)):
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"rg{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=esquema or ESQUEMA)
    respuestas = {"potencia_al_llegar": "-50.0",
                  "solucion": "se cambia conector APC",
                  "servicio_validado": "Hecho"}
    if escrito_al_salir is not None:
        respuestas["potencia_al_salir"] = escrito_al_salir
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "97996"},
        datos=dict(respuestas), vuelta=1)

    def _foto(requisito, lecturas):
        ev = EvidenciaTrabajo.objects.create(
            org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            sha256=f"{requisito}{numero}".ljust(64, "x")[:64],
            storage_key=f"k/{requisito}{numero}", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=1,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)
        for dbm in lecturas:
            AnalisisDeEvidencia.objects.create(
                org=org, evidencia=ev, vuelta=1,
                origen=AnalisisDeEvidencia.IA, texto=_texto(dbm))
        return ev

    _foto("medicion_al_llegar", ("-50.00",))
    salida = _foto("medicion_al_salir", lecturas_al_salir)
    dano = _foto("dano_encontrado", ())

    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden, salida, dano


# ---------------------------------------------------------------------------
#  1) EL RANGO LLEGA AL MODELO
# ---------------------------------------------------------------------------

def test_EL_PIE_DE_UNA_FOTO_DE_MEDIDOR_LLEVA_EL_RANGO(org_a):
    """La guarda del arreglo. Sin esto el modelo nunca sabe que magnitud
    esperar, y «-2.10» le parece tan valido como «-21.0»."""
    from campo.inspeccion_visual import que_tenia_que_mostrar

    _, salida, _ = _orden(org_a, 9971)
    pie = que_tenia_que_mostrar(salida)

    assert "-60.0" in pie and "-8.0" in pie, pie
    assert "punto decimal" in pie, pie


def test_SE_LE_PIDE_VERIFICAR_NO_AJUSTAR(org_a):
    """LA PARTE QUE NO SE PUEDE PERDER. Un pie que diga «tiene que estar
    entre X e Y» invita a inventar un numero que encaje -- un dato falso que
    pasa todos los filtros, que es peor que una lectura mal hecha y
    descartada."""
    from campo.inspeccion_visual import que_tenia_que_mostrar

    _, salida, _ = _orden(org_a, 9972)
    pie = que_tenia_que_mostrar(salida).lower()

    assert "no cambies el numero" in pie, pie
    assert "escribi lo que ves" in pie, pie


def test_EL_RANGO_SALE_DE_LA_PLANTILLA_DE_ESA_EMPRESA(org_a):
    """CLAUDE.md §3.3: lo que varia por empresa es configuracion. Otra
    empresa con otro instrumento declara otro rango y el pie cambia solo, sin
    tocar una linea de codigo. Si esta guarda se pone en rojo es porque
    alguien fijo los numeros de Rapilink en el codigo."""
    from campo.inspeccion_visual import que_tenia_que_mostrar

    otro = {k: v for k, v in ESQUEMA.items()}
    otro["campos"] = [
        {"id": "potencia_al_llegar", "tipo": "decimal",
         "titulo": "Medición al llegar", "reglas": {"min": -40, "max": -3}},
        {"id": "potencia_al_salir", "tipo": "decimal",
         "titulo": "Medición al salir", "reglas": {"min": -40, "max": -3}},
    ]
    _, salida, _ = _orden(org_a, 9973, esquema=otro)
    pie = que_tenia_que_mostrar(salida)

    assert "-40.0" in pie and "-3.0" in pie, pie
    assert "-60" not in pie, pie


def test_UNA_FOTO_QUE_NO_ES_DE_MEDIDOR_NO_LO_LLEVA(org_a):
    """La foto del daño no tiene ningun dBm que leer. Colgarle el rango
    gastaria contexto y podria hacerle buscar un numero donde no hay."""
    from campo.inspeccion_visual import que_tenia_que_mostrar

    _, _, dano = _orden(org_a, 9974)
    pie = que_tenia_que_mostrar(dano)

    assert "dBm" not in pie, pie
    assert "punto decimal" not in pie, pie


def test_SIN_LIMITES_DECLARADOS_NO_SE_INVENTA_NINGUNO(org_a):
    """Mismo criterio que `_lectura_creible`: una empresa que no declaro
    nada no recibe un rango sacado de otro lado."""
    from campo.inspeccion_visual import que_tenia_que_mostrar

    sin_reglas = {k: v for k, v in ESQUEMA.items()}
    sin_reglas["campos"] = [
        {"id": "potencia_al_salir", "tipo": "decimal",
         "titulo": "Medición al salir", "reglas": {"required": False}},
    ]
    _, salida, _ = _orden(org_a, 9975, esquema=sin_reglas)
    pie = que_tenia_que_mostrar(salida)

    assert "punto decimal" not in pie, pie
    #  Y el pie sigue existiendo: lo que se pedia de la foto no se perdio.
    assert "tenia que mostrar" in pie, pie


def test_EL_PIE_SIGUE_DICIENDO_LO_QUE_LA_PLANTILLA_PIDE(org_a):
    """El rango se SUMA, no reemplaza. Si esta guarda se pone en rojo, la
    instruccion que una persona escribio en `/supervisor-noc/plantillas`
    dejo de llegarle al modelo."""
    from campo.inspeccion_visual import que_tenia_que_mostrar

    _, salida, _ = _orden(org_a, 9976)
    pie = que_tenia_que_mostrar(salida)

    assert "Pantalla del medidor con la lectura en dBm." in pie, pie
    assert "Foto del medidor al salir" in pie, pie


# ---------------------------------------------------------------------------
#  2) NO SE RELEE A UN MODELO QUE YA SE REPITIO
# ---------------------------------------------------------------------------

def test_DOS_LECTURAS_IGUALES_CIERRAN_LA_PREGUNTA(org_a):
    """El caso de la #201: cuatro lecturas identicas de «-2.10». El tope de
    3 existe para un fallo transitorio de red; esto es un modelo consistente
    leyendo mal, y una lectura mas no va a decir algo distinto."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden, _, _ = _orden(org_a, 9977,
                         lecturas_al_salir=("-2.10", "-2.10"))

    assert mediciones_para_releer(orden) == []


def test_PERO_CON_UNA_SOLA_TODAVIA_SE_RELEE(org_a):
    """La otra mitad: sin esto, el tope quedaria en 1 y la doble lectura --el
    arreglo de esta misma manana-- dejaria de existir."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden, _, _ = _orden(org_a, 9978, lecturas_al_salir=("-2.10",))

    assert mediciones_para_releer(orden) == ["medicion_al_salir"]


def test_Y_SI_LAS_DOS_LECTURAS_DIFIEREN_SE_SIGUE(org_a):
    """La vuelta 1 de la #201, donde SI habia varianza: dos lecturas de
    -21.0 y dos de -2.10 de la misma foto. Ahi una tercera opinion todavia
    puede desempatar, y pararse seria tirar el arreglo que funciona."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden, _, _ = _orden(org_a, 9979,
                         lecturas_al_salir=("-21.0", "-2.10"))

    assert mediciones_para_releer(orden) == ["medicion_al_salir"]


def test_NO_SE_PARA_POR_DOS_LECTURAS_BUENAS_SEPARADAS(org_a):
    """Se miran LAS DOS ULTIMAS, no «hay dos iguales en algun lado». Con
    lecturas -2.10, -21.0, -2.10 el modelo sigue cambiando de opinion y la
    pregunta sigue abierta."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden, _, _ = _orden(org_a, 9980,
                         lecturas_al_salir=("-2.10", "-21.0", "-2.10"))

    assert mediciones_para_releer(orden) == ["medicion_al_salir"]


def test_EL_CAMINO_QUE_MIRA_RESPETA_ESE_CORTE(org_a):
    """El efecto en la topologia que corre: con el modelo ya repetido,
    `mirar_las_que_faltan` no gasta otra llamada."""
    from campo.tasks import mirar_las_que_faltan

    orden, _, _ = _orden(org_a, 9981,
                         lecturas_al_salir=("-2.10", "-2.10"))

    with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
        r = mirar_las_que_faltan(orden)

    #  La del daño no tiene analisis, asi que esa SI se mira: lo que no se
    #  hace es releer la de salida.
    pedidas = [c.args[0].requisito_id for c in mirar.call_args_list]
    assert "medicion_al_salir" not in pedidas, pedidas
    assert r["relecturas"] == 0, r
