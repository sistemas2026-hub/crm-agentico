# -*- coding: utf-8 -*-
"""
================================================================================
 LA MEDIDA AL SALIR CONTRA EL RANGO QUE LA EMPRESA FIJO  --  07/11/2026
================================================================================
El usuario: «hay que establecer que para que pueda diagnosticar si una medida
esta buena es entre este rango y cuando el note un rango fuera de lo indicado
ya diagnostica como malo».

Rapilink declaro -8 a -27 dBm, y se juzga SOLO AL SALIR: al llegar, una senal
mala es la falla que el tecnico vino a arreglar.

QUE AFIRMA ESTA GUARDA
----------------------
  · que una medida fuera de rango diga QUE NO -- este punto si puede, porque
    compara un numero que escribio una persona contra un rango que fijo la
    empresa, sin ninguna lectura de un modelo en el medio
  · que el rango NO este en el codigo: sin plantilla que lo declare, el punto
    no aparece
  · que SOBREVIVA a republicar la plantilla, que es lo que hace el boton
    «Guardar en la plantilla»
  · que `min`/`max` y el rango bueno sigan siendo cosas distintas: el tecnico
    tiene que poder REPORTAR una senal mala
  · y que la de LLEGADA no se juzgue
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

#:  Lo que Rapilink declaro el 07/11/2026.
PISO, TECHO = -27.0, -8.0


def _armar(org_a, numero, al_salir, bueno=(PISO, TECHO), al_llegar=None):
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    campo = {"id": "potencia_al_salir", "tipo": "decimal",
             "titulo": "Potencia al salir", "unidad": "dBm"}
    if bueno is not None:
        campo["bueno"] = {"min": bueno[0], "max": bueno[1]}
    campos = [campo]
    if al_llegar is not None:
        campos.insert(0, {"id": "potencia_al_llegar", "tipo": "decimal",
                          "titulo": "Potencia al llegar", "unidad": "dBm",
                          "bueno": {"min": PISO, "max": TECHO}})

    wt = WorkType.objects.create(org=org_a, codigo=f"r{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [], "campos": campos})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={})
    respuestas = {"potencia_al_salir": al_salir}
    if al_llegar is not None:
        respuestas["potencia_al_llegar"] = al_llegar
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "definicion": [{"id": k} for k in respuestas]})
    return orden, cierre


def _punto(orden, cierre):
    from campo.revision_del_cierre import _en_rango

    return _en_rango(orden, cierre)


# ---------------------------------------------------------------------------
#  EL DIAGNOSTICO
# ---------------------------------------------------------------------------

def test_dentro_del_rango_es_BUENO(org_a):
    orden, cierre = _armar(org_a, 300, "-21.0")

    p = _punto(orden, cierre)

    assert p["ok"] is True, p
    assert "-21" in p["texto"], p["texto"]


def test_fuera_del_rango_DICE_QUE_NO(org_a):
    """LO QUE EL USUARIO PIDIO, con todas las letras.

    Y este punto SI puede decir que no, a diferencia del de las fotos: lo que
    compara es un numero que escribio una persona contra un rango que fijo la
    empresa. No hay lectura de un modelo en el medio.
    """
    orden, cierre = _armar(org_a, 301, "-28.5")

    p = _punto(orden, cierre)

    assert p["ok"] is False, p
    assert "-28.5" in p["texto"] and "-27" in p["texto"], p["texto"]


def test_demasiada_senal_TAMBIEN_esta_fuera(org_a):
    """El rango tiene dos extremos.

    Por encima de -8 dBm el receptor satura, y el sintoma --intermitencias--
    se parece al de una senal debil. Un rango con un solo lado convertiria
    ese caso en «esta bien».
    """
    orden, cierre = _armar(org_a, 302, "-5.0")

    assert _punto(orden, cierre)["ok"] is False


@pytest.mark.parametrize("valor", [str(PISO), str(TECHO)])
def test_los_BORDES_estan_adentro(org_a, valor):
    """Exactamente -27.0 y -8.0 se consideran buenos.

    El borde se afirma porque es donde un cambio de criterio se nota, y donde
    un `<` en vez de un `<=` pasa inadvertido para siempre.
    """
    orden, cierre = _armar(org_a, 303 + int(float(valor)), valor)

    assert _punto(orden, cierre)["ok"] is True


def test_el_rango_se_lee_igual_ESCRITO_AL_REVES(org_a):
    """-8 como minimo y -27 como maximo describe el mismo rango.

    Quien configura no tiene por que adivinar la convencion de signos: en dBm
    el numero «mas chico» es el mas negativo, y eso confunde a cualquiera.
    """
    orden, cierre = _armar(org_a, 340, "-21.0", bueno=(TECHO, PISO))

    assert _punto(orden, cierre)["ok"] is True


# ---------------------------------------------------------------------------
#  EL RANGO NO VIVE EN EL CODIGO
# ---------------------------------------------------------------------------

def test_sin_rango_en_la_plantilla_el_punto_NO_APARECE(org_a):
    """CLAUDE.md §3.3: lo que varia por empresa es configuracion.

    Inventar un rango por omision es decidir por una empresa que no dijo
    nada -- y la que lo note va a ser la que reciba un «fuera de rango» que
    nadie configuro.
    """
    orden, cierre = _armar(org_a, 310, "-70.0", bueno=None)

    assert _punto(orden, cierre) is None


def test_con_UN_SOLO_extremo_tampoco_aparece(org_a):
    """Una plantilla a medio configurar parece configurada y no diagnostica.

    Mejor que el punto falte --se ve-- a que exista y nunca diga nada.

    SE ARMA LA VERSION CON EL HUECO, no se parchea una publicada: el modelo
    prohibe modificar el esquema de una version PUBLICADA por update(), y
    tiene razon -- una plantilla congelada que cambia debajo de una orden es
    justo lo que la inmutabilidad existe para impedir.
    """
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org_a, codigo='r311', nombre='Soporte',
                                 labor='correctivo')
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={'pasos': [], 'evidencias': [],
                 'campos': [{'id': 'potencia_al_salir', 'tipo': 'decimal',
                             'titulo': 'Al salir', 'unidad': 'dBm',
                             'bueno': {'min': PISO}}]})      # sin max
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=311, tipo_trabajo_version=version,
        cliente_nombre='MARIO SABANAGRANDE',
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema='manual', contexto={})
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo='cierre_campo',
        datos={'vuelta': 1, 'respuestas': {'potencia_al_salir': '-70.0'},
               'definicion': [{'id': 'potencia_al_salir'}]})

    assert _punto(orden, cierre) is None


def test_sin_MEDIDA_del_tecnico_el_punto_no_aparece(org_a):
    orden, cierre = _armar(org_a, 312, "")

    assert _punto(orden, cierre) is None


# ---------------------------------------------------------------------------
#  LA DE LLEGADA NO SE JUZGA
# ---------------------------------------------------------------------------

def test_la_potencia_AL_LLEGAR_no_se_juzga(org_a):
    """Decidido con el usuario el 07/11/2026.

    Al llegar, una senal mala ES la falla que el tecnico vino a arreglar.
    Marcarla pondria un punto en rojo en casi toda orden correctiva, que es
    la forma de que el rojo deje de significar algo.
    """
    orden, cierre = _armar(org_a, 320, "-21.0", al_llegar="-70.0")

    p = _punto(orden, cierre)

    assert p["ok"] is True, p
    assert "-70" not in p["texto"], p["texto"]


def test_el_rango_sale_DEL_CAMPO_DE_SALIR_y_no_de_otro(org_a):
    """QUE EL RANGO SALGA DEL CAMPO CORRECTO.

    Si el codigo tomara el primer campo decimal que encuentre, con una
    plantilla que declara rangos distintos para llegada y salida el
    diagnostico usaria el equivocado -- y nadie lo veria, porque el texto
    sigue diciendo numeros plausibles.

    MEDIDO EL 07/11/2026: la mutacion que toma el primer campo sobrevivio a
    las quince primeras guardas, porque todas le daban el MISMO rango a los
    dos campos. Aca son distintos a proposito.
    """
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    wt = WorkType.objects.create(org=org_a, codigo='r345', nombre='Soporte',
                                 labor='correctivo')
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={'pasos': [], 'evidencias': [], 'campos': [
            #  PRIMERO el de llegada, con un rango ANCHO que aceptaria todo.
            {'id': 'potencia_al_llegar', 'tipo': 'decimal',
             'titulo': 'Al llegar', 'unidad': 'dBm',
             'bueno': {'min': -79.0, 'max': -2.0}},
            #  Y el de salida, con el rango de verdad.
            {'id': 'potencia_al_salir', 'tipo': 'decimal',
             'titulo': 'Al salir', 'unidad': 'dBm',
             'bueno': {'min': PISO, 'max': TECHO}}]})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=345, tipo_trabajo_version=version,
        cliente_nombre='MARIO SABANAGRANDE',
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema='manual', contexto={})
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo='cierre_campo',
        datos={'vuelta': 1,
               'respuestas': {'potencia_al_llegar': '-70.0',
                              'potencia_al_salir': '-28.5'},
               'definicion': [{'id': 'potencia_al_salir'}]})

    p = _punto(orden, cierre)

    #  -28.5 esta DENTRO del rango ancho de llegada y FUERA del de salida.
    assert p['ok'] is False, p
    assert '-27' in p['texto'], p['texto']


# ---------------------------------------------------------------------------
#  LA PLANTILLA: ENTRA, SOBREVIVE, Y NO SE CONFUNDE CON min/max
# ---------------------------------------------------------------------------

def test_el_rango_SOBREVIVE_a_republicar_la_plantilla():
    """EL DEFECTO QUE ESTO EVITA.

    «Guardar en la plantilla», el boton con el que el supervisor afina las
    instrucciones de una foto, REPUBLICA el esquema entero pasando por
    `leer_definicion`. Si esa funcion no devolviera el rango, cada vez que
    alguien afinara una instruccion el diagnostico se apagaria en silencio.

    Es el mismo patron que CLAUDE.md anota como D7 sobre `editor._editar`.
    """
    from campo import plantillas as P

    definicion = {"pasos": [], "evidencias": [],
                  "campos": [{"id": "potencia_al_salir", "titulo": "Al salir",
                              "tipo": "numero", "unidad": "dBm",
                              "bueno_min": PISO, "bueno_max": TECHO}]}
    #  Ida: la definicion del editor -> el esquema que se guarda.
    esquema = P.componer(definicion)
    assert esquema["campos"][0]["bueno"] == {"min": PISO, "max": TECHO}

    #  Vuelta: el esquema -> la definicion que el editor republica.
    leida, motivos = P.leer_definicion(esquema)
    assert not motivos, motivos
    assert leida["campos"][0]["bueno_min"] == PISO
    assert leida["campos"][0]["bueno_max"] == TECHO

    #  Y otra ida, que es lo que pasa al guardar: nada se perdio.
    assert P.componer(leida)["campos"][0]["bueno"] == {
        "min": PISO, "max": TECHO}


def test_el_rango_bueno_NO_ES_min_max():
    """LA DISTINCION QUE SOSTIENE TODO.

    `min`/`max` dicen que PUEDE ESCRIBIR el tecnico -- el formulario rechaza
    lo de afuera. Si el rango bueno se expresara ahi, el tecnico no podria
    reportar la senal mala que vino a arreglar: la app no lo dejaria mandar
    el reporte.

    Son dos cosas distintas y tienen que poder convivir con valores
    distintos.
    """
    from campo import plantillas as P

    esquema = P.componer({
        "pasos": [], "evidencias": [],
        "campos": [{"id": "potencia_al_salir", "titulo": "Al salir",
                    "tipo": "numero", "min": -80, "max": -1,
                    "bueno_min": PISO, "bueno_max": TECHO}]})
    campo = esquema["campos"][0]

    assert campo["reglas"]["min"] == -80       # lo que se puede escribir
    assert campo["reglas"]["max"] == -1
    assert campo["bueno"] == {"min": PISO, "max": TECHO}   # lo que es sano


def test_un_rango_bueno_INVERTIDO_se_rechaza_al_publicar():
    """Mejor un error al configurar que un punto que nunca dice nada."""
    from campo import plantillas as P

    with pytest.raises(P.ErrorPlantilla) as e:
        P.componer({
            "pasos": [], "evidencias": [],
            "campos": [{"id": "x", "titulo": "Al salir", "tipo": "numero",
                        "bueno_min": 10, "bueno_max": -10}]})
    assert e.value.codigo == "RANGO_BUENO_INVERTIDO"


# ---------------------------------------------------------------------------
#  EN LA REVISION ENTERA
# ---------------------------------------------------------------------------

def test_el_punto_ENTRA_en_la_revision(org_a):
    """«Codigo construido no es codigo que corre» (CLAUDE.md §6)."""
    from campo.revision_del_cierre import revisar

    orden, _c = _armar(org_a, 330, "-28.5")

    claves = [p["clave"] for p in revisar(orden)["puntos"]]
    assert "rango" in claves, claves


def test_fuera_de_rango_BAJA_el_veredicto_a_NO_CERRAR(org_a):
    """EL EFECTO QUE EL USUARIO PIDIO.

    «cuando el note un rango fuera de lo indicado ya diagnostica como malo».
    Un punto en False lleva el veredicto a NO_CERRAR, que es lo que devuelve
    la orden al tecnico en vez de cerrarla.
    """
    from campo.revision_del_cierre import NO_CERRAR, revisar

    orden, _c = _armar(org_a, 331, "-28.5")

    assert revisar(orden)["veredicto"] == NO_CERRAR


# ---------------------------------------------------------------------------
#  LO QUE MANDA LA PANTALLA  --  07/11/2026
#
#  Hasta hoy el rango se cargaba con `manage.py fijar_rango_bueno`, un parche
#  declarado como tal. Ahora el editor de plantillas tiene «Bueno desde» y
#  «Bueno hasta», y manda `bueno_min` / `bueno_max` dentro de cada campo.
#
#  ESTA GUARDA VA DESDE LO QUE LA PANTALLA ENVIA, no desde una definicion
#  armada a mano con la forma que yo supongo. Es la leccion del mismo dia:
#  una prueba cuyo andamiaje inventa la forma del dato confirma la suposicion
#  de quien la escribio, no la realidad (ver test_el_dato_vive_en_la_orden).
# ---------------------------------------------------------------------------

def test_lo_que_manda_el_EDITOR_llega_al_esquema(org_a):
    from campo import plantillas as P
    from campo.models import WorkType

    #  Tal cual lo serializa `JSON.stringify(borrador)` en
    #  routes/(app)/supervisor-noc/plantillas/+page.svelte.
    de_la_pantalla = {
        "campos": [{"titulo": "Potencia al salir", "tipo": "numero",
                    "obligatorio": True, "paso": "", "unidad": "dBm",
                    "min": -60, "max": -8,
                    "bueno_min": -27, "bueno_max": -8}],
        "evidencias": [],
    }
    tipo = WorkType.objects.create(org=org_a, codigo="desde_pantalla",
                                   nombre="Soporte", labor="correctivo")

    version, _ = P.publicar(tipo, de_la_pantalla)

    campo = version.esquema["campos"][0]
    assert campo["bueno"] == {"min": -27.0, "max": -8.0}, campo
    #  Y lo otro no se pisa: el tecnico sigue pudiendo escribir -35.
    assert campo["reglas"]["min"] == -60.0, campo["reglas"]


def test_el_editor_lo_VUELVE_A_ABRIR_con_los_valores_puestos(org_a):
    """Sin esto la casilla abre vacia y el primer guardado borra el rango."""
    from campo import plantillas as P
    from campo.models import WorkType

    tipo = WorkType.objects.create(org=org_a, codigo="vuelve_a_abrir",
                                   nombre="Soporte", labor="correctivo")
    version, _ = P.publicar(tipo, {
        "campos": [{"titulo": "Potencia al salir", "tipo": "numero",
                    "obligatorio": True, "unidad": "dBm",
                    "bueno_min": -27, "bueno_max": -8}],
        "evidencias": []})

    definicion, motivos = P.leer_definicion(version.esquema)

    assert not motivos, motivos
    campo = definicion["campos"][0]
    assert campo["bueno_min"] == -27.0 and campo["bueno_max"] == -8.0, campo


def test_dejarlo_VACIO_desde_la_pantalla_no_pone_rango(org_a):
    """«Vacío: no juzga», que es lo que la pantalla promete."""
    from campo import plantillas as P
    from campo.models import WorkType

    tipo = WorkType.objects.create(org=org_a, codigo="sin_rango_pantalla",
                                   nombre="Soporte", labor="correctivo")

    version, _ = P.publicar(tipo, {
        "campos": [{"titulo": "Potencia al salir", "tipo": "numero",
                    "obligatorio": True, "unidad": "dBm",
                    "bueno_min": None, "bueno_max": None}],
        "evidencias": []})

    assert "bueno" not in version.esquema["campos"][0], version.esquema
