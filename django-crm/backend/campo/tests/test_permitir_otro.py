# -*- coding: utf-8 -*-
"""Habilitar «Otro» publica una versión nueva y no toca las viejas.

POR QUE ESTE ARCHIVO EXISTE  --  11/11/2026. El comando se escribió, se
verificó que parseaba, que importaba y que Django lo registraba, y se mandó a
producción. **Falló las dos primeras corridas**: una por leer las opciones de
una sola de las dos claves posibles, otra por llamar `opciones` a dos cosas
distintas en la misma función. Ninguno de los dos errores sobrevive a
ejecutarlo una vez; los dos sobrevivieron a «parsea e importa».

Es `PARSEA != IMPORTA != FUNCIONA` con los tres escalones medidos de a uno, y
el tercero cobrándoselo a quien estaba del otro lado de la terminal.
"""
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from campo.models import WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db


def _tipo(org, *, campo: dict, codigo: str = "prueba_otro"):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre="Prueba",
                                   activo=True)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [campo], "evidencias": []})
    return tipo


def _correr(org, tipo, campo, aplicar=False):
    salida = io.StringIO()
    call_command("permitir_otro", org=str(org.id), tipo=tipo.codigo,
                 campo=campo, aplicar=aplicar, stdout=salida)
    return salida.getvalue()


SELECCION_CON_REGLAS = {
    "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
    #  LA FORMA QUE ROMPIO LA PRIMERA CORRIDA: las opciones viven en
    #  `reglas.options`, no en `opciones`. Las dos existen en producción según
    #  cómo se creó la plantilla, y `plantillas.py` contempla las dos.
    "reglas": {"options": ["Conector sucio", "Fibra partida", "Roseta"]},
}


# --------------------------------------------------------------------------- #
# A. Lo que hace
# --------------------------------------------------------------------------- #
def test_a1_el_simulacro_no_publica_nada(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    salida = _correr(org_a, tipo, "que_encontro")

    assert "SIMULACRO" in salida
    assert "3 opciones" in salida, f"lee las opciones de `reglas`: {salida}"
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_a2_al_aplicar_publica_una_version_nueva(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    versiones = list(WorkTypeVersion.objects.filter(work_type=tipo)
                     .order_by("version"))
    assert [v.version for v in versiones] == [1, 2]
    nuevo = [c for c in versiones[-1].esquema["campos"]
             if c["id"] == "que_encontro"][0]
    assert nuevo.get("permite_otro") is True


def test_a3_LA_VIEJA_NO_SE_TOCA(org_a):
    #  Una orden congela su versión al nacer. Si la v1 cambiara, le estaríamos
    #  cambiando el formulario a órdenes que ya tienen respuestas escritas
    #  --incluso cerradas--. Es la razón entera de publicar en vez de editar.
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    v1 = WorkTypeVersion.objects.get(work_type=tipo, version=1)
    viejo = [c for c in v1.esquema["campos"] if c["id"] == "que_encontro"][0]
    assert not viejo.get("permite_otro"), "la v1 quedó como estaba"


def test_a4_correrlo_dos_veces_no_publica_una_tercera(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)
    salida = _correr(org_a, tipo, "que_encontro", aplicar=True)

    #  «v3» igual a «v2» solo ensuciaría la historia y haría creer que algo
    #  cambió.
    assert "YA lo tiene" in salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 2


def test_a6_NO_TOCA_LOS_OTROS_CAMPOS(org_a):
    #  Visto en produccion el 11/11/2026: la normalizacion de opciones
    #  recorria TODOS los campos y le agrego la clave a uno que nadie pidio
    #  tocar. Era inocuo --el lector mira las dos claves-- pero el comando
    #  promete que nada mas cambia.
    otro = {"id": "servicio_probado", "titulo": "Probado",
            "tipo": "seleccion", "reglas": {"options": ["Hecho", "No aplica"]}}
    tipo = WorkType.objects.create(org=org_a, codigo="dos_campos",
                                   nombre="Dos", activo=True)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [dict(SELECCION_CON_REGLAS), dict(otro)],
                 "evidencias": []})

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    nueva = WorkTypeVersion.objects.get(work_type=tipo, version=2)
    campos = {c["id"]: c for c in nueva.esquema["campos"]}
    assert campos["que_encontro"].get("permite_otro") is True
    #  EL OTRO, IDENTICO. Ni la bandera ni la clave de opciones.
    assert campos["servicio_probado"] == otro, (
        f"se toco un campo que nadie pidio: {campos['servicio_probado']}")


# --------------------------------------------------------------------------- #
# B. Lo que se niega a hacer
# --------------------------------------------------------------------------- #
def test_b1_un_campo_sin_opciones_no_se_marca(org_a):
    #  «Otro» en un campo de texto no significa nada, y el validador lo
    #  rechazaría después — con una versión de más ya publicada.
    tipo = _tipo(org_a, campo={"id": "nota", "titulo": "Nota", "tipo": "texto"})

    with pytest.raises(CommandError, match="no tiene opciones"):
        _correr(org_a, tipo, "nota", aplicar=True)

    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_b2_un_campo_que_no_existe_lo_dice_y_lista_los_que_hay(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    with pytest.raises(CommandError) as e:
        _correr(org_a, tipo, "campo_inventado")

    #  Decir «no existe» y no cuál hay obliga a salir a buscar el esquema a
    #  mano, que es lo que el mensaje debería evitar.
    assert "que_encontro" in str(e.value)


def test_b3_una_plantilla_que_no_existe_no_revienta(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))
    tipo.codigo = "no_existe_este_codigo"

    with pytest.raises(CommandError, match="no existe"):
        _correr(org_a, tipo, "que_encontro")


def test_a5_una_plantilla_QUE_EL_EDITOR_NO_SABE_CREAR_tambien_se_publica(org_a):
    #  EL CASO REAL, y el que rompio en produccion el 11/11/2026. La v16 de
    #  `correctivo_fibra` tiene un campo de tipo `decimal`, que `componer`
    #  --el validador del EDITOR-- no acepta: esa plantilla no se hizo con el
    #  editor. El primer intento pasaba por `plantillas.publicar` y cortaba
    #  con «'decimal' no esta disponible», rechazando la plantilla ENTERA.
    #
    #  Un comando que habilita una opcion no puede exigir que el formulario
    #  sea reconstruible por otra herramienta.
    tipo = WorkType.objects.create(org=org_a, codigo='con_decimal',
                                   nombre='Con decimal', activo=True)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=16, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={'campos': [
            {'id': 'potencia_al_llegar', 'titulo': 'Potencia al llegar',
             'tipo': 'decimal'},
            dict(SELECCION_CON_REGLAS),
        ], 'evidencias': []})

    _correr(org_a, tipo, 'que_encontro', aplicar=True)

    vs = list(WorkTypeVersion.objects.filter(work_type=tipo).order_by('version'))
    assert [v.version for v in vs] == [16, 17], 'publica igual'
    campos = {c['id']: c for c in vs[-1].esquema['campos']}
    assert campos['que_encontro'].get('permite_otro') is True
    #  Y EL DECIMAL SIGUE SIENDO DECIMAL. El otro final malo de recomponer era
    #  que «arreglara» el tipo de un campo que hoy funciona.
    assert campos['potencia_al_llegar']['tipo'] == 'decimal'


# --------------------------------------------------------------------------- #
# C. La otra forma del dato
# --------------------------------------------------------------------------- #
def test_c1_tambien_lee_las_opciones_de_la_clave_vieja(org_a):
    #  La otra mitad de lo que rompió la primera corrida: hay plantillas con
    #  las opciones en `opciones` y otras en `reglas.options`.
    tipo = _tipo(org_a, campo={
        "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
        "opciones": ["Uno", "Dos"],
    })

    salida = _correr(org_a, tipo, "que_encontro")

    assert "2 opciones" in salida, salida
# --------------------------------------------------------------------------- #
# D. LO QUE LA APP LEE  --  la unica cosa que decide si «Otro» APARECE
#
#    POR QUE ESTA SECCION EXISTE, y es el tercer escalon del encabezado.
#
#    Las nueve pruebas de arriba estaban en verde y «Otro» NO FUNCIONABA en
#    produccion. Todas afirmaban sobre el MECANISMO --que la bandera se
#    escribiera, que la version se publicara, que nada mas cambiara-- y
#    ninguna sobre el EFECTO: que la opcion llegue a la lista de la que el
#    tecnico elige.
#
#    La app lee las opciones de `reglas.options` con prioridad y cae a
#    `opciones` solo si la primera no esta (`campo_del_formulario.dart:244`:
#    «las opciones viajan en `reglas.options`; `opciones` es la forma vieja»).
#    El comando copiaba `reglas.options` -> `opciones` y dejaba `reglas.options`
#    intacta, SIN «Otro». Resultado: `permite_otro: true` en el esquema, y la
#    opcion sin dibujar, porque la lista que la app lee no la tenia.
#
#    Quien agrega «Otro» a la lista es `componer` (`plantillas.py:519`), y este
#    comando no recompone a proposito --la v16 de `correctivo_fibra` no entra
#    por ahi--. Entonces tiene que hacerlo el: es lo que `componer` haria.
# --------------------------------------------------------------------------- #
def test_d1_la_opcion_OTRO_queda_en_LA_LISTA_QUE_LA_APP_LEE(org_a):
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    v2 = WorkTypeVersion.objects.get(work_type=tipo, version=2)
    campo = v2.esquema["campos"][0]
    #  LA MISMA PRECEDENCIA QUE LA APP, no una lista cualquiera: mirar
    #  `opciones` cuando la app mira `reglas.options` es justo el error que
    #  dejo pasar el defecto.
    lista = (campo.get("reglas") or {}).get("options") or campo.get("opciones")
    assert lista is not None, "la app no tendria de donde leer las opciones"
    assert "Otro" in lista, (
        f"la app lee esta lista y «Otro» no esta: {lista}. "
        "`permite_otro` sin la opcion en la lista no dibuja nada.")
    #  Y AL FINAL, como lo pone `componer`: el tecnico lee de arriba hacia
    #  abajo y «Otro» es la salida, no una opcion mas en el medio.
    assert lista[-1] == "Otro", f"«Otro» va ultima: {lista}"


def test_d2_el_servidor_ACEPTA_el_valor_Otro(org_a):
    """El otro extremo: que el reporte no se rechace al llegar.

    `_validar_reglas` corta con «Opcion invalida» cuando el valor no esta en
    `reglas.options`. Sin «Otro» en esa lista, un tecnico que la eligiera
    --si la viera-- quedaria con el trabajo trabado y sin saber por que.
    """
    from campo.services.validador import validar_campos_tecnicos

    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))
    _correr(org_a, tipo, "que_encontro", aplicar=True)
    campo = WorkTypeVersion.objects.get(work_type=tipo,
                                        version=2).esquema["campos"][0]

    limpios, errores = validar_campos_tecnicos(
        {"campos": [campo]},
        {"que_encontro": "Otro", "que_encontro_otro": "se robaron el poste"})

    assert errores == {}, f"el servidor rechaza «Otro»: {errores}"
    assert limpios["que_encontro"] == "Otro"
    assert limpios["que_encontro_otro"] == "se robaron el poste"


def test_d3_un_Otro_ESCRITO_A_MANO_no_queda_dos_veces(org_a):
    """Hay empresas que lo escribieron en la lista, sin texto libre.

    `componer` lo resuelve sacandolo y volviendolo a poner al final
    (`plantillas.py:519`). Si el comando solo agregara, la lista quedaria con
    dos «Otro» y el tecnico veria la misma palabra dos veces.
    """
    tipo = _tipo(org_a, campo={
        "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
        "reglas": {"options": ["Conector sucio", "Otro", "Roseta"]},
    })

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    campo = WorkTypeVersion.objects.get(work_type=tipo,
                                        version=2).esquema["campos"][0]
    lista = (campo.get("reglas") or {}).get("options")
    assert lista.count("Otro") == 1, f"«Otro» duplicada: {lista}"
    assert lista[-1] == "Otro", f"y al final: {lista}"


def test_d5_REPARA_una_plantilla_a_medio_hacer(org_a):
    """El estado que quedo en produccion el 11/11/2026, y como se sale de el.

    Cuatro plantillas quedaron con `permite_otro: true` y sin «Otro» en la
    lista. La pregunta vieja --¿tiene la bandera?-- contestaba «ya lo tiene» y
    el comando se iba sin hacer nada: el unico camino para arreglarlo habria
    sido editar la base a mano.

    Esta prueba es la que dice que la reparacion existe, y por eso arranca del
    esquema roto en vez de uno limpio.
    """
    tipo = _tipo(org_a, campo={
        "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
        #  LA BANDERA PUESTA...
        "permite_otro": True,
        #  ...Y LA OPCION AUSENTE DE LAS DOS LISTAS.
        "reglas": {"options": ["Conector sucio", "Fibra partida"]},
        "opciones": ["Conector sucio", "Fibra partida"],
    })

    salida = _correr(org_a, tipo, "que_encontro", aplicar=True)

    assert "A MEDIO HACER" in salida, salida
    assert "PUBLICADA la v2" in salida, salida
    campo = WorkTypeVersion.objects.get(work_type=tipo,
                                        version=2).esquema["campos"][0]
    lista = (campo.get("reglas") or {}).get("options")
    assert lista == ["Conector sucio", "Fibra partida", "Otro"], lista
    assert campo["opciones"][-1] == "Otro", campo["opciones"]


def test_d6_y_una_VEZ_REPARADA_no_publica_otra(org_a):
    """La idempotencia se mantiene: completo es completo."""
    tipo = _tipo(org_a, campo=dict(SELECCION_CON_REGLAS))
    _correr(org_a, tipo, "que_encontro", aplicar=True)

    salida = _correr(org_a, tipo, "que_encontro", aplicar=True)

    assert "YA lo tiene" in salida, salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 2


def test_d4_tambien_en_la_clave_vieja_cuando_es_la_unica(org_a):
    """Una plantilla con las opciones solo en `opciones` no se queda afuera."""
    tipo = _tipo(org_a, campo={
        "id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
        "opciones": ["Conector sucio", "Fibra partida"],
    })

    _correr(org_a, tipo, "que_encontro", aplicar=True)

    campo = WorkTypeVersion.objects.get(work_type=tipo,
                                        version=2).esquema["campos"][0]
    lista = (campo.get("reglas") or {}).get("options") or campo.get("opciones")
    assert "Otro" in lista, f"la app lee esta lista: {lista}"
