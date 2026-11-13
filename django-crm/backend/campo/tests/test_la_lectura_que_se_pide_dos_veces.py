# -*- coding: utf-8 -*-
"""
================================================================================
 UNA LECTURA SOLA NO TIENE CON QUE VALIDARSE  --  11/11/2026
================================================================================
EL PEDIDO DEL USUARIO, Y POR QUE ESTO ES SU PRECONDICION
---------------------------------------------------------
    «o si mejor ese datos llene la app con la lectura que toma de la foto y
    ya se corrije ese eso de que haiga diferencia»

La app no puede llenar el campo con un numero en el que el sistema no confia,
y hoy no confia: el modelo le corre el punto decimal.

    OT #212, #198, #204 (08/11)   pantalla -21.0  ->  leyo -2.10
    OT #200  (10/11 18:14)        pantalla -21.0  ->  leyo -2.10
    medido el 10/11               3 de cada 7 lecturas

LO QUE ESO COSTO, MEDIDO EN LA OT #200
---------------------------------------
La orden cerro sola el 11/11 a las 11:09 con la medicion de salida SIN
VERIFICAR. El tecnico escribio -18.0, la pantalla marcaba -21.0 --el usuario
lo puso mal a proposito para ver la devolucion-- y nadie comparo esos dos
numeros nunca: la unica lectura que habia era imposible, se descarto con
razon, y descartar deja la medicion sin verificar. Los cinco arreglos de la
semana hicieron todos lo correcto y ninguno podia tapar este hueco.

EL ARREGLO, Y DONDE SE APARTA DE LO QUE SE PIDIO
-------------------------------------------------
Dos lecturas de la misma foto, y el numero vale si las dos lo dicen. Lo que
NO se hizo es pedir dos lecturas de TODA foto: se piden cuando la primera va
a tener consecuencia y no se sostiene sola --no se leyo nada, no es creible,
discordaron, o no coincide con lo escrito--. Cuando el numero creible
coincide con el del tecnico ya hay dos fuentes independientes de acuerdo, y
una tercera lectura no agrega nada. Eso deja el costo en ~0 llamadas en el
caso bueno, y en 2 como maximo cuando hace falta. Ver
`revision_del_cierre.mediciones_para_releer`.

QUE AFIRMAN ESTAS GUARDAS, Y CUALES MATAN QUE  --  medido el 11/11/2026
------------------------------------------------------------------------
No es una lista de intenciones: se mutaron las tres piezas del arreglo y se
corrio la suite. Murieron 5 de 15. Lo que cada mutacion mato:

    M1  `_numero_de_la_foto` ignora la discordancia (se queda con el primer
        creible)
        -> test_DOS_NUMEROS_CREIBLES_DISTINTOS_no_se_usan
    M2  `_lecturas_de_la_foto` vuelve a devolver UNA, la ultima (el
        comportamiento de ayer)
        -> test_LA_LECTURA_IMPOSIBLE_NO_ARRASTRA_A_LA_BUENA
    M3  la segunda pasada de `mirar_las_que_faltan` no corre
        -> test_LA_RELECTURA_LA_EJECUTA_EL_CAMINO_QUE_YA_MIRA
        -> test_LA_PRIMERA_PASADA_VA_ANTES_Y_LA_SEGUNDA_LA_VE
        -> test_EL_TOPE_TAMBIEN_FRENA_LA_RELECTURA

DOS QUE SOBREVIVIERON, Y SE DICE PORQUE ESTA ES LA PARTE QUE SE MIENTE SOLA:

  · `test_LA_OT_200_AHORA_SE_DEVUELVE` sobrevive a M2, y la primera version
    de este encabezado lo llamaba «la que mata el bug». Es falso: el caso
    tiene la lectura buena AL FINAL, asi que quedarse con la ultima acierta
    por casualidad. Sigue valiendo --es el caso de produccion tal como paso,
    y eso es lo que hay que poder leer el dia que vuelva-- pero lo que mata
    la mutacion es su hermana con las lecturas al reves. Ese par existe por
    esto: un solo orden de lecturas no distingue el arreglo del azar.

  · `test_Y_NO_LO_CUENTA_COMO_LECTURA_IMPOSIBLE` sobrevive a M1 por lo que
    afirma: una AUSENCIA en el texto. Con M1 el texto dice «coincide», que
    tampoco contiene la frase prohibida. Es una guarda de «no empeoro», no
    de efecto, y vale lo que vale.
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
         "titulo": "Foto del medidor al llegar", "obligatorio": True},
        {"id": "medicion_al_salir", "tipo": "foto",
         "titulo": "Foto del medidor al salir", "obligatorio": True},
    ],
}

#: Como queda un texto del analizador. El numero es lo unico que cambia.
#:
#: EL µW SE CALCULA DEL dBm  --  12/11/2026
#: Este helper ponia «0.682 µW» fijo, copiado de una foto real que resulto
#: ser la imagen promocional del fabricante: esos µW son -31.7 dBm y no
#: corresponden a ningun numero de estas guardas. Desde que el codigo cruza
#: las dos unidades, una pantalla imposible se descarta, y siete guardas de
#: este archivo se pusieron en rojo por su propio dato -- con razon.
#:
#: Las que prueban una lectura IMPOSIBLE (-2.10) siguen siendo imposibles
#: por el rango, que es lo que esas guardas miden; lo que cambia es que
#: ahora su pantalla es internamente coherente y el descarte ocurre por el
#: motivo que la guarda dice medir, no por un µW de adorno.
def _texto(dbm: str) -> str:
    #  Hay guardas que pasan algo que NO es un numero, a proposito: miden la
    #  foto que no deja leer nada. Ahi no hay µW que calcular.
    try:
        uw = 10 ** (float(str(dbm).replace(",", ".")) / 10.0) * 1000.0
        par = f"{dbm} dBm, {uw:.3f} µW"
    except ValueError:
        par = f"{dbm} dBm"
    return (f"Medidor de potencia óptico Rouhan; pantalla legible: 1550 nm, "
            f"{par}, 2kHz. "
            f"CATALOGO: no MUESTRA: si ATENCION: no")


def _orden(org, numero, *, escrito_al_salir="-18.0",
           lecturas_al_salir=("-2.10",), lecturas_al_llegar=("-50.00",),
           esquema=None):
    """La OT #200 reducida. Cada elemento de `lecturas_*` es UNA fila de
    analisis sobre esa foto, en el orden en que se escribieron; `None` es un
    intento que fallo (fila sin texto), como la que deja un ReadTimeout."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"dl{numero}",
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
        origen_sistema="manual", contexto={"ticket": "97997"},
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
                origen=AnalisisDeEvidencia.IA,
                texto="" if dbm is None else _texto(dbm),
                motivo=("no se pudo hablar con el motor (ReadTimeout)"
                        if dbm is None else ""))
        return ev

    _foto("medicion_al_llegar", lecturas_al_llegar)
    _foto("medicion_al_salir", lecturas_al_salir)

    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden


def _punto(orden):
    from campo import revision_del_cierre as RC

    revision = RC.revisar(orden, pendientes=set())
    return revision, next(p for p in revision["puntos"]
                          if p["clave"] == "potencia")


# ---------------------------------------------------------------------------
#  1) LA GUARDA DEL BUG
# ---------------------------------------------------------------------------

def test_LA_OT_200_AHORA_SE_DEVUELVE(org_a):
    """El caso entero, con la segunda lectura puesta: la primera leyo el
    «-2.10» imposible y la segunda leyo bien «-21.0». El tecnico escribio
    -18.0. Son 3.0 dBm de diferencia, mas que la tolerancia de 2.0, y eso es
    lo que el usuario queria ver el 10/11 y no vio.

    SI ESTA GUARDA SE PONE EN ROJO la #200 vuelve a cerrar sola con la
    medicion de salida sin verificar, que es como cerro de verdad.
    """
    orden = _orden(org_a, 9951, lecturas_al_salir=("-2.10", "-21.0"))
    revision, punto = _punto(orden)

    assert punto["ok"] is None, punto
    assert "no dicen lo mismo" in punto["texto"], punto["texto"]
    assert "-21" in punto["texto"] and "-18" in punto["texto"], punto["texto"]
    assert "medicion_al_salir" in revision["sugeridas"], revision["sugeridas"]
    #  Y YA NO SE HABLA DE UNA AUSENCIA: esa foto SI se pudo verificar.
    assert "no se pudo verificar" not in punto["texto"], punto["texto"]


def test_LA_LECTURA_IMPOSIBLE_NO_ARRASTRA_A_LA_BUENA(org_a):
    """El orden inverso --primero la buena, despues la imposible-- da lo
    mismo. Sin esto, quedarse con «la ultima» haria que el resultado dependa
    de en que pasada el modelo se equivoco."""
    orden = _orden(org_a, 9952, lecturas_al_salir=("-21.0", "-2.10"))
    _, punto = _punto(orden)

    assert "no dicen lo mismo" in punto["texto"], punto["texto"]
    assert "-21" in punto["texto"], punto["texto"]


# ---------------------------------------------------------------------------
#  2) DOS LECTURAS EN PUGNA NO SON UNA LECTURA
# ---------------------------------------------------------------------------

def test_DOS_NUMEROS_CREIBLES_DISTINTOS_no_se_usan(org_a):
    """Las dos lecturas caen dentro de lo que la empresa declaro, y son
    numeros distintos: no hay con que decidir cual salio de esa pantalla.

    POR QUE NO SE PROMEDIA NI SE ELIGE UNA: promediar da un numero que
    ninguna pantalla mostro, y elegir la que convenga es inventar la mitad
    del juicio.
    """
    orden = _orden(org_a, 9953, lecturas_al_salir=("-21.0", "-19.0"))
    revision, punto = _punto(orden)

    assert "números distintos" in punto["texto"], punto["texto"]
    assert "al salir" in punto["texto"], punto["texto"]
    #  NO DEVUELVE LA ORDEN: el que leyo distinto dos veces es el modelo.
    assert "medicion_al_salir" not in (revision["sugeridas"] or []), \
        revision["sugeridas"]
    assert not (punto.get("rehacer") or []), punto


def test_Y_NO_LO_CUENTA_COMO_LECTURA_IMPOSIBLE(org_a):
    """Tres ausencias distintas, una frase cada una. Si la discordancia se
    contara como descarte, el texto diria «lo que se leyó en esa foto no
    puede salir de ese medidor» -- que de esas dos lecturas es falso."""
    orden = _orden(org_a, 9954, lecturas_al_salir=("-21.0", "-19.0"))
    _, punto = _punto(orden)

    assert "no puede salir de ese medidor" not in punto["texto"], punto["texto"]


def test_DOS_LECTURAS_IGUALES_si_se_usan(org_a):
    """La confirmacion, que es el caso que esto viene a habilitar: el mismo
    numero dos veces es una lectura confirmada, y se compara como siempre."""
    orden = _orden(org_a, 9955, escrito_al_salir="-21.0",
                   lecturas_al_salir=("-21.0", "-21.0"))
    _, punto = _punto(orden)

    assert punto["ok"] is True, punto
    assert "coincide" in punto["texto"].lower(), punto["texto"]


def test_UNA_SOLA_LECTURA_CREIBLE_SIGUE_VALIENDO(org_a):
    """LA COMPATIBILIDAD, y es deliberada. Toda orden ya cerrada tiene UNA
    lectura por foto. Si exigir dos fuera la regla, el panel de todas ellas
    pasaria a decir «no se pudo verificar» de un dia para otro -- y la
    prueba 1 del usuario (OT #215, que paso limpia) seria la primera.

    El tecnico ya escribio su propio numero: cuando los dos coinciden hay dos
    fuentes independientes de acuerdo, y eso es verificacion.
    """
    orden = _orden(org_a, 9956, escrito_al_salir="-21.0",
                   lecturas_al_salir=("-21.0",))
    _, punto = _punto(orden)

    assert punto["ok"] is True, punto
    assert "no se pudo verificar" not in punto["texto"], punto["texto"]


# ---------------------------------------------------------------------------
#  3) CUANDO SE GASTA UNA SEGUNDA LECTURA Y CUANDO NO
# ---------------------------------------------------------------------------

def test_SE_RELEE_LA_LECTURA_IMPOSIBLE(org_a):
    """El caso de la #200: la unica lectura no puede salir de ese medidor."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden = _orden(org_a, 9957, lecturas_al_salir=("-2.10",))

    assert mediciones_para_releer(orden) == ["medicion_al_salir"]


def test_SE_RELEE_LA_QUE_NO_COINCIDE(org_a):
    """Una discrepancia DEVUELVE la orden, y conviene estar seguro antes:
    mandar a un tecnico de vuelta por un error de lectura del modelo es el
    viaje mas caro que este sistema puede causar."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden = _orden(org_a, 9958, escrito_al_salir="-12.0",
                   lecturas_al_salir=("-21.0",))

    assert "medicion_al_salir" in mediciones_para_releer(orden)


def test_SE_RELEE_LA_FOTO_SIN_NINGUN_NUMERO(org_a):
    """Una foto de medidor sin numero legible tambien devuelve la orden, y
    tampoco depende de que el tecnico haya escrito algo."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden = _orden(
        org_a, 9959, escrito_al_salir=None,
        lecturas_al_salir=("sin numero",))
    #  `_texto` siempre mete un dBm, asi que se escribe una lectura a mano.
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import EvidenciaTrabajo
    ev = EvidenciaTrabajo.objects.get(org=org_a, orden_trabajo=orden,
                                      requisito_id="medicion_al_salir")
    AnalisisDeEvidencia.objects.filter(org=org_a, evidencia=ev).delete()
    AnalisisDeEvidencia.objects.create(
        org=org_a, evidencia=ev, vuelta=1, origen=AnalisisDeEvidencia.IA,
        texto="Foto muy movida del medidor; la pantalla no se puede leer. "
              "CATALOGO: no MUESTRA: no ATENCION: si")

    assert "medicion_al_salir" in mediciones_para_releer(orden)


def test_NO_SE_RELEE_LA_QUE_YA_COINCIDE(org_a):
    """LA MITAD QUE CUIDA EL COSTO. Sin esto, cada pasada del ciclo horario
    le vuelve a pagar al modelo por las dos fotos de cada orden abierta."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden = _orden(org_a, 9960, escrito_al_salir="-21.0",
                   lecturas_al_salir=("-21.0",))

    assert mediciones_para_releer(orden) == []


def test_NO_SE_RELEE_LA_QUE_NADIE_MIRO_TODAVIA(org_a):
    """Esa la mira el camino de siempre. Releer no es lo que le falta, y
    contarla aca la haria mirar dos veces en la misma pasada."""
    from campo.revision_del_cierre import mediciones_para_releer

    orden = _orden(org_a, 9961, lecturas_al_salir=())

    assert "medicion_al_salir" not in mediciones_para_releer(orden)


# ---------------------------------------------------------------------------
#  4) QUE SE RELEA DE VERDAD, EN LA TOPOLOGIA QUE CORRE
# ---------------------------------------------------------------------------

def test_LA_RELECTURA_LA_EJECUTA_EL_CAMINO_QUE_YA_MIRA(org_a):
    """El efecto, no la presencia de la funcion: `mirar_las_que_faltan` --que
    es lo que corre en el camino acelerado Y en el ciclo horario-- vuelve a
    mirar esa foto.

    Si esto se pone en rojo, `mediciones_para_releer` existe y nadie la
    llama: codigo construido que no corre (CLAUDE.md §6).
    """
    from campo.tasks import mirar_las_que_faltan

    orden = _orden(org_a, 9962, lecturas_al_salir=("-2.10",))

    with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
        mirar.return_value = {"estado": "ok", "motivo": ""}
        r = mirar_las_que_faltan(orden)

    assert r["relecturas"] == 1, r
    #  Y ES ESA FOTO, no la de llegada, que coincide y no se toca.
    pedidas = [c.args[0].requisito_id for c in mirar.call_args_list]
    assert pedidas == ["medicion_al_salir"], pedidas


def test_LA_PRIMERA_PASADA_VA_ANTES_Y_LA_SEGUNDA_LA_VE(org_a):
    """POR QUE SON DOS PASADAS EN LA MISMA LLAMADA. En el camino acelerado la
    cola puede no haber mirado ninguna foto todavia --asi quedo atrapada la
    #200-- y para juzgar una lectura hay que tenerla escrita. Preguntando
    DESPUES de la primera pasada, la relectura sale en el mismo momento en
    que el tecnico manda el reporte, que es lo que el usuario pidio el 09/11.
    """
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import EvidenciaTrabajo
    from campo.tasks import mirar_las_que_faltan

    #  La foto de salida llega SIN ninguna fila: nadie la miro.
    orden = _orden(org_a, 9963, lecturas_al_salir=())

    def _escribe_lo_imposible(evidencia):
        AnalisisDeEvidencia.objects.create(
            org_id=evidencia.org_id, evidencia=evidencia, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=_texto("-2.10"))
        return {"estado": "ok", "motivo": ""}

    with mock.patch("campo.tasks._mirar_y_anotar",
                    side_effect=_escribe_lo_imposible) as mirar:
        r = mirar_las_que_faltan(orden)

    #  Una mirada (no habia analisis) y una relectura (lo que leyo no sirve).
    assert r["miradas"] == 1, r
    assert r["relecturas"] == 1, r
    assert mirar.call_count == 2, mirar.call_args_list
    ev = EvidenciaTrabajo.objects.get(org=org_a, orden_trabajo=orden,
                                      requisito_id="medicion_al_salir")
    assert AnalisisDeEvidencia.objects.filter(
        org=org_a, evidencia=ev).count() == 2


def test_EL_TOPE_TAMBIEN_FRENA_LA_RELECTURA(org_a):
    """Una foto que el modelo lee mal tres veces deja de releerse y espera a
    una persona. Sin esto, una pantalla que el modelo nunca va a leer bien
    hace una llamada por foto en cada pasada del ciclo, para siempre.

    POR QUE LAS LECTURAS SON DISTINTAS ENTRE SI  --  11/11/2026, tarde
    ------------------------------------------------------------------
    Nacio con tres «-2.10» iguales y ese mismo dia se puso en rojo al
    agregarse el corte por repeticion (OT #201: dos lecturas iguales cierran
    la pregunta, ver `test_el_rango_que_el_modelo_no_sabia`). No era un
    defecto del corte: con lecturas iguales esta guarda ya no medía el TOPE,
    la frenaba el corte antes de llegar a él, y habría seguido en verde con
    el tope roto.

    Tres lecturas distintas y todas imposibles dejan el corte fuera de
    juego, que es lo que hace falta para que lo unico que frene sea el tope.
    """
    from campo.tasks import INTENTOS_POR_FOTO, mirar_las_que_faltan

    assert INTENTOS_POR_FOTO == 3
    distintas = ("-2.10", "-3.10", "-4.10")
    orden = _orden(org_a, 9964, lecturas_al_salir=distintas)

    with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
        r = mirar_las_que_faltan(orden)

    assert r["relecturas"] == 0, r
    assert mirar.call_count == 0, mirar.call_args_list

    #  Y UNO MENOS TODAVIA SE RELEE: sin esto un tope en 0 pasaria igual.
    orden2 = _orden(org_a, 9965, lecturas_al_salir=distintas[:2])
    with mock.patch("campo.tasks._mirar_y_anotar") as mirar2:
        mirar2.return_value = {"estado": "ok", "motivo": ""}
        assert mirar_las_que_faltan(orden2)["relecturas"] == 1
    assert mirar2.call_count == 1


def test_UN_FALLO_AL_DECIDIR_QUE_RELEER_NO_FRENA_NADA(org_a):
    """La relectura es una mejora sobre el dato, no una puerta. Si decidir
    que releer falla, lo que ya se miro se miro y la revision sigue."""
    from campo.tasks import mirar_las_que_faltan

    orden = _orden(org_a, 9966, lecturas_al_salir=("-2.10",))

    with mock.patch("campo.revision_del_cierre.mediciones_para_releer",
                    side_effect=RuntimeError("boom")):
        with mock.patch("campo.tasks._mirar_y_anotar") as mirar:
            mirar.return_value = {"estado": "ok", "motivo": ""}
            r = mirar_las_que_faltan(orden)

    assert r["relecturas"] == 0, r


def test_SIN_CAMPO_DE_POTENCIA_NO_SE_RELEE_NADA(org_a):
    """Lo encontro una guarda ajena  --  11/11/2026

    `test_las_fotos_se_miran_antes_de_decidir` arma su orden con
    `"campos": []`: declara las tres fotos y ningun campo. Sus siete casos se
    pusieron en rojo de golpe porque esta funcion pedia releer las dos fotos
    de medicion en cada pasada, y son guardas de COSTO -- «no se le paga dos
    veces al modelo».

    Y tenian razon: una segunda lectura solo sirve si hay con que
    contrastarla. Donde la plantilla no tiene el campo, el formulario nunca
    va a traer el numero del tecnico, y releer hasta agotar el tope no puede
    cambiar nada. Es gasto puro, en toda orden de esa plantilla y en cada
    pasada del ciclo.
    """
    from campo.revision_del_cierre import mediciones_para_releer

    #  LA MISMA ORDEN DOS VECES, lo unico distinto es la plantilla. Y la
    #  segunda nace con su esquema: `WorkTypeVersion.update()` sobre una
    #  version PUBLICADA esta prohibido --una guarda de `campo/models.py`,
    #  con razon-- asi que no se puede mutar la de la primera.
    con_campo = _orden(org_a, 9967, lecturas_al_salir=("-2.10",))
    assert mediciones_para_releer(con_campo) == ["medicion_al_salir"]

    sin_campo = _orden(org_a, 9968, lecturas_al_salir=("-2.10",),
                       esquema=dict(ESQUEMA, campos=[]))
    assert mediciones_para_releer(sin_campo) == []
