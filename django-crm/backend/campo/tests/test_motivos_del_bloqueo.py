# -*- coding: utf-8 -*-
"""El motivo del bloqueo en botones, medido donde el dato aterriza.

QUÉ AFIRMA ESTE ARCHIVO, Y POR QUÉ ASÍ  --  11/11/2026

El mismo día, un comando hermano (`permitir_otro`) publicó cuatro versiones a
producción con sus nueve guardas en verde y la función ROTA: todas afirmaban
que la bandera se escribía, ninguna que la opción llegara a la lista de la que
el técnico elige. El síntoma lo encontró la lectura del código de la app, no
la suite.

Así que acá la afirmación central no es «el esquema quedó declarado» sino
**`BloqueoDeTrabajo.categoria` trae lo que el técnico eligió**: el final del
camino, pasando por `formulario_de` --lo que la app dibuja-- y por
`bloqueos.bloquear` --lo que el servidor guarda--. Si algún eslabón se cae, la
columna queda vacía y estas pruebas lo dicen.
"""
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from campo.bloqueos import BloqueoDeTrabajo
from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from campo.services import bloqueos, seguimiento_campo

pytestmark = pytest.mark.django_db

ORG_SIN_IMPORTANCIA = "deberia dar lo mismo"


def _tipo(org, *, esquema=None, codigo="correctivo_fibra"):
    tipo = WorkType.objects.create(org=org, codigo=codigo, nombre="Correctivo",
                                   activo=True)
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema=esquema if esquema is not None else {
            "pasos": [{"id": "p1", "titulo": "Ejecución"}],
            "campos": [{"id": "que_encontro", "titulo": "Qué encontró",
                        "tipo": "texto", "reglas": {"required": True}}],
            "evidencias": [{"id": "foto", "titulo": "Foto", "obligatorio": True}],
        })
    return tipo


def _correr(org, tipo, aplicar=False, opciones=""):
    salida = io.StringIO()
    call_command("motivos_del_bloqueo", org=str(org.id), tipo=tipo.codigo,
                 opciones=opciones, aplicar=aplicar, stdout=salida)
    return salida.getvalue()


def _orden(org, profile, version):
    o = OrdenTrabajo.objects.create(
        org=org, numero=7701, tipo_trabajo_version=version,
        cliente_nombre="Cliente de prueba",
        estado_operativo=OrdenTrabajo.EN_SITIO)
    AsignacionTrabajo.objects.create(orden=o, profile=profile, rol="tecnico",
                                     es_principal=True)
    return o


def _vigente(tipo):
    return (WorkTypeVersion.objects.filter(work_type=tipo)
            .order_by("-version").first())


# --------------------------------------------------------------------------- #
# A. EL EFECTO: el dato llega a la columna
# --------------------------------------------------------------------------- #
def test_a1_LA_CATEGORIA_ATERRIZA_EN_SU_COLUMNA(org_a, user_profile):
    """La afirmación que importa, y la que hoy fallaría sin el comando.

    `BloqueoDeTrabajo.categoria` existe desde el principio y su comentario dice
    para qué: «lo que el tenant eligió en su formulario, copiado como texto
    para poder agrupar». `bloqueos.py` la lee de `respuestas["categoria"]`.
    Ninguna plantilla declaraba un campo con ese id, así que la columna estaba
    vacía en todos los bloqueos.
    """
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden = _orden(org_a, user_profile, _vigente(tipo))

    bloqueo, _evento, _detuvo = bloqueos.bloquear(
        orden, profile=user_profile,
        respuestas={"categoria": "Falta material",
                    "necesita_de_noc": "traer un drop de 80 metros"},
        requiere_noc=False, detener=True)

    bloqueo.refresh_from_db()
    assert bloqueo.categoria == "Falta material", (
        "la categoría no llegó a su columna: sin esto no se puede agrupar por "
        "qué se traban los trabajos, que es para lo que la columna existe")


def test_a2_el_minimo_generico_NO_LA_LLENA(org_a, user_profile):
    """El estado de hoy, medido. Es el control de la prueba anterior.

    Sin declarar el bloqueo, el mínimo pide dos TEXTOS y ninguno se llama
    `categoria`: mandarla sería un campo que no existe en la plantilla, y el
    validador la rechaza. Esta prueba afirma el AGUJERO, no una conducta
    deseada: cuando deje de pasar es porque el mínimo cambió.
    """
    tipo = _tipo(org_a)
    orden = _orden(org_a, user_profile, _vigente(tipo))

    bloqueo, _e, _d = bloqueos.bloquear(
        orden, profile=user_profile,
        respuestas={"motivo": "no hay quien abra",
                    "necesita_de_noc": "nada, es del cliente"},
        requiere_noc=False, detener=True)

    assert bloqueo.categoria == "", (
        "si esto trae algo, el mínimo genérico ya declara la categoría y este "
        "comando dejó de hacer falta")


def test_a3_OTRO_con_texto_tambien_aterriza(org_a, user_profile):
    """Lo imprevisto no se pierde: es lo que hace que adivinar cueste poco."""
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden = _orden(org_a, user_profile, _vigente(tipo))

    bloqueo, evento, _d = bloqueos.bloquear(
        orden, profile=user_profile,
        respuestas={"categoria": "Otro",
                    "categoria_otro": "se robaron el poste anoche",
                    "necesita_de_noc": "que lo reporten a la electrificadora"},
        requiere_noc=True, detener=True)

    assert bloqueo.categoria == "Otro"
    guardadas = (evento.datos or {}).get("respuestas") or {}
    assert guardadas.get("categoria_otro") == "se robaron el poste anoche", (
        f"el texto de «Otro» se perdió: {guardadas}")


def test_a4_OTRO_SIN_TEXTO_se_rechaza(org_a, user_profile):
    """«Otro» vacío deja a la oficina con una respuesta que no dice nada."""
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden = _orden(org_a, user_profile, _vigente(tipo))

    with pytest.raises(bloqueos.BloqueoInvalido) as e:
        bloqueos.bloquear(
            orden, profile=user_profile,
            respuestas={"categoria": "Otro", "necesita_de_noc": "algo"},
            requiere_noc=False, detener=True)
    assert "categoria" in (e.value.errores or {}), e.value.errores


def test_a5_una_categoria_QUE_NO_ESTA_EN_LA_LISTA_se_rechaza(org_a, user_profile):
    """La lista es una lista: un valor inventado no entra."""
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden = _orden(org_a, user_profile, _vigente(tipo))

    with pytest.raises(bloqueos.BloqueoInvalido):
        bloqueos.bloquear(
            orden, profile=user_profile,
            respuestas={"categoria": "porque llueve",
                        "necesita_de_noc": "un paraguas"},
            requiere_noc=False, detener=True)


# --------------------------------------------------------------------------- #
# B. LO QUE LA APP VA A DIBUJAR
# --------------------------------------------------------------------------- #
def test_b1_la_app_recibe_la_categoria_como_SELECCION_con_la_opcion_adentro(org_a):
    """La lección de `permitir_otro`: la bandera sin la opción no dibuja nada."""
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden_falsa = type("O", (), {"tipo_trabajo_version": _vigente(tipo)})()

    formulario = seguimiento_campo.formulario_de(orden_falsa, "bloqueo")

    campos = {c["id"]: c for c in formulario["campos"]}
    assert "categoria" in campos, f"los ids que llegan: {list(campos)}"
    cat = campos["categoria"]
    assert cat["tipo"] == "seleccion"
    assert cat.get("permite_otro") is True
    #  LA MISMA PRECEDENCIA QUE `campo_del_formulario.dart:244`
    lista = (cat.get("reglas") or {}).get("options") or cat.get("opciones")
    assert lista[-1] == "Otro", f"«Otro» va última: {lista}"
    assert "Falta material" in lista
    assert formulario["declarado_por_el_tipo_de_trabajo"] is True


def test_b2_lo_obligatorio_PASA_DE_DOS_TEXTOS_A_UN_BOTON_Y_UN_TEXTO(org_a):
    """El pedido era «más fácil de llenar», y eso se puede contar."""
    tipo = _tipo(org_a)
    orden_falsa = type("O", (), {"tipo_trabajo_version": _vigente(tipo)})()
    antes = seguimiento_campo.formulario_de(orden_falsa, "bloqueo")["campos"]
    textos_antes = [c for c in antes
                    if c["tipo"] == "texto" and (c.get("reglas") or {}).get("required")]

    _correr(org_a, tipo, aplicar=True)
    orden_falsa2 = type("O", (), {"tipo_trabajo_version": _vigente(tipo)})()
    despues = seguimiento_campo.formulario_de(orden_falsa2, "bloqueo")["campos"]
    textos_despues = [c for c in despues
                      if c["tipo"] == "texto" and (c.get("reglas") or {}).get("required")]

    assert len(textos_antes) == 2, [c["id"] for c in textos_antes]
    assert len(textos_despues) == 1, [c["id"] for c in textos_despues]
    assert textos_despues[0]["id"] == "necesita_de_noc", (
        "el que queda obligatorio es el del NOC, que es la decisión que NO se "
        "reabrió")


def test_b3_el_motivo_sigue_existiendo_y_ES_OPCIONAL(org_a):
    """No se pierde el detalle: baja de obligatorio a opcional."""
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden_falsa = type("O", (), {"tipo_trabajo_version": _vigente(tipo)})()

    campos = {c["id"]: c
              for c in seguimiento_campo.formulario_de(orden_falsa, "bloqueo")["campos"]}

    assert "motivo" in campos
    assert not (campos["motivo"].get("reglas") or {}).get("required")


def test_b4_la_categoria_va_PRIMERA(org_a):
    """«Motivo primero y como botones»: el orden es parte del pedido."""
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)
    orden_falsa = type("O", (), {"tipo_trabajo_version": _vigente(tipo)})()

    campos = seguimiento_campo.formulario_de(orden_falsa, "bloqueo")["campos"]

    assert campos[0]["id"] == "categoria", [c["id"] for c in campos]


# --------------------------------------------------------------------------- #
# C. LO QUE NO TOCA
# --------------------------------------------------------------------------- #
def test_c1_el_resto_del_esquema_queda_IGUAL(org_a):
    tipo = _tipo(org_a)
    antes = WorkTypeVersion.objects.get(work_type=tipo, version=1).esquema

    _correr(org_a, tipo, aplicar=True)

    despues = WorkTypeVersion.objects.get(work_type=tipo, version=2).esquema
    assert despues["campos"] == antes["campos"]
    assert despues["evidencias"] == antes["evidencias"]
    assert despues["pasos"] == antes["pasos"]


def test_c2_LA_VIEJA_NO_SE_TOCA(org_a):
    """Una orden congela su versión al nacer: editar la publicada le cambiaría
    el formulario a trabajos que ya tienen respuestas escritas."""
    tipo = _tipo(org_a)

    _correr(org_a, tipo, aplicar=True)

    v1 = WorkTypeVersion.objects.get(work_type=tipo, version=1)
    assert "seguimiento" not in (v1.esquema or {}), v1.esquema.get("seguimiento")


def test_c3_el_simulacro_no_publica_nada(org_a):
    tipo = _tipo(org_a)

    salida = _correr(org_a, tipo)

    assert "SIMULACRO" in salida
    assert "Falta material" in salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_c4_un_bloqueo_QUE_LA_EMPRESA_YA_DECLARO_no_se_pisa(org_a):
    """Esa lista es una decisión de alguien, no un hueco."""
    tipo = _tipo(org_a, esquema={
        "campos": [], "evidencias": [],
        "seguimiento": {"bloqueo": {"campos": [
            {"id": "lo_suyo", "titulo": "Lo que esta empresa pregunta",
             "tipo": "texto", "reglas": {"required": True}}]}},
    })

    salida = _correr(org_a, tipo, aplicar=True)

    assert "YA está declarado" in salida, salida
    assert "lo_suyo" in salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_c5_correrlo_dos_veces_no_publica_una_tercera(org_a):
    tipo = _tipo(org_a)
    _correr(org_a, tipo, aplicar=True)

    salida = _correr(org_a, tipo, aplicar=True)

    assert "YA está declarado" in salida, salida
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 2


# --------------------------------------------------------------------------- #
# D. LAS CATEGORIAS SON DE LA EMPRESA, NO DE LA PLATAFORMA
# --------------------------------------------------------------------------- #
def test_d1_otra_empresa_trae_las_suyas(org_a):
    """CLAUDE.md §3.3: lo que varía por empresa es configuración.

    Las tres del encargo son un default, no una lista de plataforma. El
    comentario de la columna lo dice: «no es una lista cerrada de plataforma:
    cada empresa tiene las suyas».
    """
    tipo = _tipo(org_a)

    _correr(org_a, tipo, aplicar=True,
            opciones="Sin energía en el poste; Permiso de alcaldía")

    orden_falsa = type("O", (), {"tipo_trabajo_version": _vigente(tipo)})()
    campos = {c["id"]: c
              for c in seguimiento_campo.formulario_de(orden_falsa, "bloqueo")["campos"]}
    lista = (campos["categoria"].get("reglas") or {}).get("options")
    assert lista == ["Sin energía en el poste", "Permiso de alcaldía", "Otro"], lista


def test_d2_una_plantilla_que_no_existe_no_revienta(org_a):
    tipo = _tipo(org_a)
    with pytest.raises(CommandError) as e:
        call_command("motivos_del_bloqueo", org=str(org_a.id),
                     tipo="no_existe", opciones="", aplicar=False,
                     stdout=io.StringIO())
    assert "no existe" in str(e.value)
    assert tipo.codigo  # no se tocó nada
