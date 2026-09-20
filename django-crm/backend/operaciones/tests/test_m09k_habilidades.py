# -*- coding: utf-8 -*-
"""
================================================================================
 M09-K  --  que la ficha diga la verdad sobre el codigo, y no al reves
================================================================================

Estas pruebas no comprueban que las habilidades funcionen: eso ya lo hacen las
180 que existian antes. Comprueban que la FORMALIZACION es fiel:

  - que las 14 fichas existan y esten completas;
  - que cada ficha de dominio apunte a un detector que EXISTE en supervisor.py
    y a una señal que EXISTE en el modelo -- si alguien renombra una funcion, la
    ficha queda mintiendo, y esto lo caza;
  - que ninguna declare una herramienta de escritura;
  - que ninguna pida nivel > 1;
  - que la definicion literal sea reproducible;
  - que 'conocimiento_version' no reciba nada inventado.

LO QUE NO HACEN
---------------
No modifican ningun detector. Si una de estas pruebas fallara porque el codigo
cambio, lo correcto es corregir la FICHA -- el codigo es la fuente canonica
(decision D-1).
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from operaciones import habilidades, supervisor
from operaciones.models import PropuestaSupervisor


# =============================================================================
#  1-5.  LAS 14 ESTAN, Y ESTAN COMPLETAS
# =============================================================================

def test_hay_exactamente_catorce():
    assert len(habilidades.HABILIDADES) == 14
    assert len(habilidades.IDS) == 14
    assert len(set(habilidades.IDS)) == 14, "hay ids repetidos"


def test_diez_de_dominio_y_cuatro_transversales():
    dominio = [h for h in habilidades.HABILIDADES.values()
               if h.tipo == habilidades.DOMINIO]
    transversales = [h for h in habilidades.HABILIDADES.values()
                     if h.tipo == habilidades.TRANSVERSAL]
    assert len(dominio) == 10
    assert len(transversales) == 4


@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_cada_ficha_tiene_definicion_no_vacia(id_habilidad):
    h = habilidades.HABILIDADES[id_habilidad]
    for campo in ("id", "nombre", "tipo", "vigente_desde", "estado",
                  "proposito", "responsabilidad", "alcance"):
        valor = getattr(h, campo)
        assert isinstance(valor, str) and valor.strip(), \
            f"{id_habilidad}.{campo} vacio"


@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_cada_ficha_tiene_version(id_habilidad):
    h = habilidades.HABILIDADES[id_habilidad]
    assert isinstance(h.version, int) and h.version >= 1


@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_cada_ficha_declara_evidencia(id_habilidad):
    """Sin evidencia declarada no se sabe con qué se sostiene la afirmación."""
    h = habilidades.HABILIDADES[id_habilidad]
    assert h.evidencia, f"{id_habilidad} no declara evidencia"
    assert all(e.strip() for e in h.evidencia)


@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_cada_ficha_declara_incertidumbre(id_habilidad):
    """
    La sexta pregunta que M09-J encontró sin responder.

    Una habilidad que no sabe decir qué puede estar equivocado en su propio
    resultado se lee como si nunca se equivocara.
    """
    h = habilidades.HABILIDADES[id_habilidad]
    assert h.incertidumbre, f"{id_habilidad} no declara incertidumbre"
    assert all(i.strip() for i in h.incertidumbre)


@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_cada_ficha_declara_su_limite(id_habilidad):
    h = habilidades.HABILIDADES[id_habilidad]
    assert h.fuera_de_alcance, f"{id_habilidad} no declara qué NO hace"


# =============================================================================
#  6-7.  NI HERRAMIENTAS DE ESCRITURA, NI AUTONOMIA
# =============================================================================

@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_ninguna_declara_herramienta_de_escritura(id_habilidad):
    """
    La separación habilidad / herramienta / autorización / ejecución.

    Una habilidad puede decir qué datos consultar. No concede permisos. Si
    alguna declarara una herramienta de escritura, estaría documentando un
    permiso que la frontera nunca le dio.
    """
    h = habilidades.HABILIDADES[id_habilidad]
    assert h.herramientas_escritura == (), \
        f"{id_habilidad} declara escritura: {h.herramientas_escritura}"


@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_ninguna_pide_nivel_mayor_que_recomendar(id_habilidad):
    h = habilidades.HABILIDADES[id_habilidad]
    assert h.nivel in (PropuestaSupervisor.NIVEL_OBSERVAR,
                       PropuestaSupervisor.NIVEL_RECOMENDAR), \
        f"{id_habilidad} pide nivel {h.nivel}"


def test_las_transversales_son_nivel_cero():
    """No emiten señales: observan o calculan."""
    for h in habilidades.HABILIDADES.values():
        if h.tipo == habilidades.TRANSVERSAL:
            assert h.nivel == PropuestaSupervisor.NIVEL_OBSERVAR


def test_el_registro_esta_congelado():
    """
    No se puede agregar ni quitar una habilidad en caliente.

    Es la propiedad que hace que 'la definición' sea una sola cosa. Sin esto,
    cualquier módulo que importe el registro podría cambiarlo y la referencia
    guardada en una propuesta dejaría de significar algo.
    """
    with pytest.raises(TypeError):
        habilidades.HABILIDADES["H-99"] = None
    with pytest.raises(TypeError):
        del habilidades.HABILIDADES["H-01"]


def test_una_ficha_no_se_puede_editar():
    h = habilidades.HABILIDADES["H-01"]
    with pytest.raises(Exception):
        h.version = 99


# =============================================================================
#  LA FICHA CONTRA EL CODIGO  --  que no mienta
# =============================================================================

def test_cada_habilidad_de_dominio_apunta_a_un_detector_que_existe():
    """Si alguien renombra un detector, la ficha queda mintiendo. Esto lo caza."""
    for h in habilidades.HABILIDADES.values():
        if h.tipo != habilidades.DOMINIO:
            continue
        assert h.detector, f"{h.id} no nombra detector"
        assert hasattr(supervisor, h.detector), \
            f"{h.id} apunta a '{h.detector}', que no existe en supervisor.py"
        assert callable(getattr(supervisor, h.detector))


def test_cada_habilidad_de_dominio_apunta_a_una_senal_declarada():
    tipos = {v for v, _ in PropuestaSupervisor.TIPOS_SENAL}
    for h in habilidades.HABILIDADES.values():
        if h.tipo != habilidades.DOMINIO:
            continue
        assert h.senal in tipos, f"{h.id} declara señal '{h.senal}', no declarada"


def test_las_diez_senales_del_modelo_tienen_ficha():
    """Ninguna señal puede quedar sin habilidad que la explique."""
    tipos = {v for v, _ in PropuestaSupervisor.TIPOS_SENAL}
    cubiertas = set(habilidades.POR_SENAL)
    assert tipos == cubiertas, f"sin ficha: {tipos - cubiertas}"


def test_los_diez_detectores_del_ciclo_tienen_ficha():
    """Se lee la lista REAL de 'detectar()', no una copia."""
    import inspect
    fuente = inspect.getsource(supervisor.detectar)
    for h in habilidades.HABILIDADES.values():
        if h.tipo == habilidades.DOMINIO:
            assert h.detector in fuente, \
                f"{h.id}: '{h.detector}' no aparece en detectar()"


def test_las_transversales_no_apuntan_a_detector():
    for h in habilidades.HABILIDADES.values():
        if h.tipo == habilidades.TRANSVERSAL:
            assert h.detector == ""
            assert h.senal == ""


# =============================================================================
#  8-10.  DEFINICION LITERAL, REPRODUCIBLE Y ESTABLE
# =============================================================================

@pytest.mark.parametrize("id_habilidad", list(habilidades.IDS))
def test_la_huella_es_reproducible(id_habilidad):
    h = habilidades.HABILIDADES[id_habilidad]
    assert h.huella() == h.huella()
    assert len(h.huella()) == 64


def test_dos_fichas_distintas_tienen_huellas_distintas():
    huellas = {h.id: h.huella() for h in habilidades.HABILIDADES.values()}
    assert len(set(huellas.values())) == 14, "hay huellas repetidas"


def test_el_canonico_es_determinista_y_ordenado():
    """
    Se hashea una serialización explícita y ordenada, no el repr del objeto.

    Un hash sobre algo cuyo orden depende de la implementación deja de ser
    reproducible el día que cambia la versión de Python.
    """
    h = habilidades.HABILIDADES["H-01"]
    canonico = h.canonico()
    lineas = canonico.splitlines()
    claves = [l.split("=", 1)[0] for l in lineas]
    assert claves == sorted(claves), "el canónico no está ordenado por campo"
    assert h.canonico() == canonico


def test_una_version_nueva_no_altera_el_contenido_historico():
    """
    Cambiar la versión produce OTRA huella, y no toca la ficha original.

    Es lo que permite que una propuesta de hace seis meses siga significando lo
    mismo aunque la habilidad haya cambiado tres veces.
    """
    import dataclasses
    original = habilidades.HABILIDADES["H-01"]
    huella_original = original.huella()

    v2 = dataclasses.replace(original, version=2)

    assert v2.huella() != huella_original
    assert v2.referencia() == "habilidad:H-01@2"
    # La original no se movió:
    assert habilidades.HABILIDADES["H-01"].version == 1
    assert habilidades.HABILIDADES["H-01"].huella() == huella_original
    assert habilidades.HABILIDADES["H-01"].referencia() == "habilidad:H-01@1"


def test_la_referencia_tiene_forma_estable():
    for h in habilidades.HABILIDADES.values():
        assert h.referencia() == f"habilidad:{h.id}@{h.version}"
        assert len(h.referencia()) <= 128, "no entra en conocimiento_version"


# =============================================================================
#  11.  conocimiento_version NO RECIBE NADA INVENTADO
# =============================================================================

def test_una_senal_sin_ficha_no_inventa_referencia():
    """Preferible un campo vacío --el valor actual-- a una referencia falsa."""
    assert habilidades.referencia_de("senal_que_no_existe") == ""
    assert habilidades.referencia_de("") == ""


def test_la_referencia_declara_que_es_una_habilidad():
    """
    El campo se llama 'conocimiento_version' y lo que guarda es la versión de la
    HABILIDAD. Sin el prefijo, quien lea la fila dentro de un año creería que
    existe un conocimiento versionado que hoy no existe.
    """
    for senal in habilidades.POR_SENAL:
        assert habilidades.referencia_de(senal).startswith("habilidad:")


def test_ninguna_ficha_afirma_un_conocimiento_que_no_existe():
    """
    Una ficha solo puede citar conocimiento que EXISTE, o declararlo pendiente.

    No se compara contra una lista de cadenas: se resuelve la referencia contra
    el modelo real. Una lista de cadenas envejecería en silencio el día que el
    atributo citado se renombre, que es justo lo que hay que cazar.
    """
    from operaciones.models import NovedadOperativa

    def existe(cita: str) -> bool:
        if cita.startswith("PENDIENTE"):
            return True          # declara la ausencia en vez de inventarla
        if cita.startswith("NovedadOperativa.TIPOS"):
            return bool(getattr(NovedadOperativa, "TIPOS", None))
        return False

    for h in habilidades.HABILIDADES.values():
        for c in h.conocimiento:
            assert existe(c), f"{h.id} cita conocimiento no verificable: {c!r}"


def test_la_mayoria_de_las_fichas_declara_su_conocimiento_ausente():
    """
    Nueve de las catorce no tienen documento de conocimiento, y la ficha lo dice
    con una tupla vacía en vez de inventar una referencia.

    No es un defecto de la formalización: es el estado real, y es la razón por
    la que 'conocimiento_version' guarda solo la versión de la habilidad.
    """
    sin_conocimiento = [h.id for h in habilidades.HABILIDADES.values()
                        if not h.conocimiento]
    assert len(sin_conocimiento) >= 9, (
        "si esto baja, es porque se documentó conocimiento: actualizar D-3")


# =============================================================================
#  12.  TRAZABILIDAD EN LA PROPUESTA
# =============================================================================

def _senal(tipo, huella="h"):
    return supervisor.Senal(
        tipo=tipo, origen_tipo="case", origen_id=str(uuid.uuid4()),
        evidencia=[{"fuente": "case", "id": "x", "dato": "d",
                    "observado_en": timezone.now().isoformat()}],
        huella=huella)


def test_la_propuesta_guarda_que_habilidad_la_emitio(org_a):
    p = supervisor.registrar_propuesta(
        org_a, _senal(PropuestaSupervisor.CASO_ANTIGUO),
        {"accion_propuesta": "Revisar", "motivo": "m", "prioridad": 42,
         "componentes_prioridad": ["base 50"],
         "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR})
    p.refresh_from_db()
    #  D-3 extendio el formato: ahora tambien cita el conocimiento cuando existe.
    #  La primera mitad NO cambio -- esa es la garantia de estabilidad.
    assert p.conocimiento_version.startswith("habilidad:H-01@1")
    assert p.conocimiento_version == "habilidad:H-01@1 conocimiento:K-01@1,K-05@1"


@pytest.mark.parametrize("senal", list(habilidades.POR_SENAL))
def test_toda_senal_conocida_deja_referencia(org_a, senal):
    p = supervisor.registrar_propuesta(
        org_a, _senal(senal),
        {"accion_propuesta": "x", "motivo": "m", "prioridad": 50,
         "componentes_prioridad": ["base 50"],
         "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR})
    p.refresh_from_db()
    esperada = habilidades.referencia_de(senal)
    assert p.conocimiento_version == esperada
    assert esperada.startswith("habilidad:")


def test_la_referencia_permite_recuperar_la_ficha(org_a):
    """El punto de todo: poder responder 'qué definición produjo esto'."""
    p = supervisor.registrar_propuesta(
        org_a, _senal(PropuestaSupervisor.ORDEN_SIN_PROGRAMAR),
        {"accion_propuesta": "x", "motivo": "m", "prioridad": 30,
         "componentes_prioridad": ["base 30"],
         "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR})
    p.refresh_from_db()

    #  'habilidad:H-03@1 conocimiento:K-03@1'  ->  se lee la primera mitad
    parte_habilidad = p.conocimiento_version.split(" conocimiento:")[0]
    cuerpo = parte_habilidad.removeprefix("habilidad:")
    id_habilidad, version = cuerpo.split("@")
    ficha = habilidades.HABILIDADES[id_habilidad]

    assert ficha.id == "H-03"
    assert str(ficha.version) == version
    assert ficha.detector == "_ordenes_sin_programar"
    assert ficha.procedimiento          # se puede leer qué hizo


# =============================================================================
#  H-05 SIGUE BLOQUEADA
# =============================================================================

def test_h05_esta_bloqueada_y_lo_dice():
    h = habilidades.HABILIDADES["H-05"]
    assert h.estado == habilidades.BLOQUEADA
    assert any("D-4" in x for x in h.reglas)
    assert any("D-4" in x for x in h.conocimiento)


def test_solo_h05_esta_bloqueada():
    bloqueadas = [h.id for h in habilidades.HABILIDADES.values()
                  if h.estado == habilidades.BLOQUEADA]
    assert bloqueadas == ["H-05"]
