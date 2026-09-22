# -*- coding: utf-8 -*-
"""
================================================================================
 D-3  --  que el conocimiento exista, tenga fuente, y no invente nada
================================================================================

D-3 escribio cinco documentos de conocimiento en 'directivas/'. Estas pruebas
comprueban que:

  - los cinco archivos existen;
  - cada uno tiene ID, version, estado y fuentes;
  - las habilidades que citan EXISTEN;
  - las referencias de conocimiento apuntan a documentos que EXISTEN;
  - no hay versiones inventadas;
  - K-02 sigue sin escribirse y H-05 sigue bloqueada.

LO QUE NO HACEN
---------------
No comprueban que el conocimiento sea correcto -- eso lo decide una persona.
Comprueban que sea VERIFICABLE: que cada regla diga de donde sale y que nada
apunte al vacio.
================================================================================
"""

from pathlib import Path

import pytest

from operaciones import habilidades
from operaciones.models import PropuestaSupervisor


def _buscar_directivas() -> Path | None:
    """
    Sube por el arbol hasta encontrar 'directivas/'.

    No se usa un numero fijo de 'parents' porque la ruta cambia segun donde este
    montado el repositorio: en disco es
    'crm-agentico/django-crm/backend/operaciones/tests', pero en el contenedor
    de pruebas 'django-crm' se monta directo en '/proyecto' y la raiz queda
    fuera. Contar niveles funcionaba en un lado y fallaba en el otro -- medido.
    """
    for candidato in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        for base in (candidato, candidato / "repo"):
            if (base / "directivas").is_dir():
                return base / "directivas"
    #  El repositorio puede estar montado aparte (ver docker run -v .../repo).
    for extra in (Path("/repo"), Path("/proyecto").parent):
        if (extra / "directivas").is_dir():
            return extra / "directivas"
    return None


DIRECTIVAS = _buscar_directivas()

#  Si el repositorio no esta montado, estas pruebas no pueden decir nada: se
#  saltan en vez de fallar. Una prueba que falla por como se monto un volumen
#  entrena a ignorar fallos reales.
sin_repo = pytest.mark.skipif(
    DIRECTIVAS is None,
    reason="el repositorio no esta montado: no hay 'directivas/' que leer")

DOCUMENTOS = {
    "K-01": "K-01_criterio_antiguedad_caso.md",
    "K-02": "K-02_definicion_capacidad_operativa.md",
    "K-03": "K-03_estados_operativos_trabajo_iniciado.md",
    "K-04": "K-04_redaccion_sin_atribucion_de_culpa.md",
    "K-05": "K-05_first_response_at.md",
}


def _texto(id_doc: str) -> str:
    return (DIRECTIVAS / DOCUMENTOS[id_doc]).read_text(encoding="utf-8")


# =============================================================================
#  1-5.  LOS CINCO EXISTEN Y ESTAN IDENTIFICADOS
# =============================================================================

@sin_repo
def test_la_carpeta_de_directivas_existe():
    """No se creó una carpeta nueva: se usó la que ya existía."""
    assert DIRECTIVAS is not None and DIRECTIVAS.is_dir()


@pytest.mark.parametrize("id_doc", sorted(DOCUMENTOS))
@sin_repo
def test_el_documento_existe(id_doc):
    assert (DIRECTIVAS / DOCUMENTOS[id_doc]).is_file()


@pytest.mark.parametrize("id_doc", sorted(DOCUMENTOS))
@sin_repo
def test_el_documento_declara_su_id(id_doc):
    assert f"**ID** | {id_doc}" in _texto(id_doc)


@pytest.mark.parametrize("id_doc", sorted(DOCUMENTOS))
@sin_repo
def test_el_documento_declara_version_y_estado(id_doc):
    t = _texto(id_doc)
    assert "**Versión**" in t
    assert "**Estado**" in t


@pytest.mark.parametrize("id_doc", sorted(DOCUMENTOS))
@sin_repo
def test_el_documento_declara_fuentes(id_doc):
    """Cada regla debe poder rastrearse. Sin fuentes, es una opinión."""
    assert "## Fuentes" in _texto(id_doc) or "## Por qué" in _texto(id_doc)


@pytest.mark.parametrize("id_doc", ["K-01", "K-03", "K-04", "K-05"])
@sin_repo
def test_los_documentos_escritos_tienen_las_secciones_obligatorias(id_doc):
    t = _texto(id_doc)
    for seccion in ("## Propósito", "## Alcance", "## Fuera de alcance",
                    "## Fuentes", "## Reglas", "## Procedimiento",
                    "## Evidencia requerida", "## Limitaciones e incertidumbre",
                    "## Excepciones", "## Escalamiento", "## Prohibiciones",
                    "## Versionado"):
        assert seccion in t, f"{id_doc} no tiene '{seccion}'"


@pytest.mark.parametrize("id_doc", ["K-01", "K-03", "K-04", "K-05"])
@sin_repo
def test_cada_documento_escrito_declara_incertidumbre_explicita(id_doc):
    t = _texto(id_doc)
    assert "## Limitaciones e incertidumbre" in t
    assert "Cuándo abstenerse" in t


# =============================================================================
#  6-8.  NO APUNTAN AL VACIO
# =============================================================================

@pytest.mark.parametrize("id_doc", sorted(DOCUMENTOS))
@sin_repo
def test_las_habilidades_citadas_existen(id_doc):
    """Un documento no puede gobernar una habilidad que no existe."""
    import re
    t = _texto(id_doc)
    citadas = set(re.findall(r"\bH-(?:C?\d{1,2})\b", t))
    inexistentes = citadas - set(habilidades.IDS)
    assert not inexistentes, f"{id_doc} cita habilidades inexistentes: {inexistentes}"


@sin_repo
def test_el_mapa_de_conocimiento_solo_apunta_a_documentos_que_existen():
    for id_habilidad, docs in habilidades.CONOCIMIENTO.items():
        for id_doc, _version in docs:
            assert id_doc in DOCUMENTOS, \
                f"{id_habilidad} cita {id_doc}, que no existe"
            assert (DIRECTIVAS / DOCUMENTOS[id_doc]).is_file()


def test_el_mapa_de_conocimiento_solo_usa_habilidades_que_existen():
    for id_habilidad in habilidades.CONOCIMIENTO:
        assert id_habilidad in habilidades.HABILIDADES


def test_no_se_referencia_K02_porque_no_se_escribio():
    """
    K-02 existe como archivo, pero declara que NO se pudo construir.

    Referenciarlo desde una habilidad sería afirmar que hay conocimiento donde
    solo hay una constancia de que falta.
    """
    citados = {d for docs in habilidades.CONOCIMIENTO.values() for d, _ in docs}
    assert "K-02" not in citados


@sin_repo
def test_k02_declara_explicitamente_que_no_se_pudo_escribir():
    t = _texto("K-02")
    assert "PENDIENTE — INFORMACIÓN OPERATIVA INSUFICIENTE" in t
    assert "D-4" in t


# =============================================================================
#  9.  NINGUNA VERSION INVENTADA
# =============================================================================

def test_las_versiones_de_conocimiento_son_enteros_positivos():
    for docs in habilidades.CONOCIMIENTO.values():
        for _id, version in docs:
            assert isinstance(version, int) and version >= 1


@sin_repo
def test_la_version_citada_coincide_con_la_del_documento():
    """Si el mapa dice K-01@1, el documento tiene que decir v1."""
    for docs in habilidades.CONOCIMIENTO.values():
        for id_doc, version in docs:
            assert f"**Versión** | v{version}" in _texto(id_doc), \
                f"{id_doc}: el mapa dice v{version} y el documento no"


def test_conocimiento_de_devuelve_vacio_donde_no_hay_documento():
    """
    Doce de las dieciséis no tienen documento de conocimiento. El vacío es el
    dato, y no un pendiente: H-11 y H-12 (M04-A) tampoco lo tienen, porque D-3
    prohíbe inventarles uno para completar la tabla.
    """
    sin_documento = [i for i in habilidades.IDS
                     if i not in habilidades.CONOCIMIENTO]
    assert len(sin_documento) == 14
    for i in sin_documento:
        assert habilidades.conocimiento_de(i) == ""


# =============================================================================
#  10-12.  NO SE MODIFICO NADA DE LO PROHIBIDO
# =============================================================================

def test_las_catorce_habilidades_siguen_intactas():
    #  Eran 14 hasta M09-M. M04-A agrega H-11 y H-12 (plazo operativo de
    #  una orden) con autorizacion explicita. Las 14 originales NO se
    #  tocaron: lo verifica 'test_las_catorce_originales_no_cambiaron'.
    #  M04-A agrego H-11/H-12 y M05-A agrega H-13, las tres con autorizacion explicita.
    #  M09-M dejo 14. Despues se agregaron, con autorizacion explicita: H-11/H-12 (M04-A), H-13 (M05-A) y H-14 (M05-B).
    assert len(habilidades.HABILIDADES) == 18
    assert len(habilidades.IDS) == 18


def test_ninguna_habilidad_gano_herramienta_de_escritura():
    for h in habilidades.HABILIDADES.values():
        assert h.herramientas_escritura == ()


def test_ninguna_habilidad_cambio_de_nivel():
    for h in habilidades.HABILIDADES.values():
        assert h.nivel in (PropuestaSupervisor.NIVEL_OBSERVAR,
                           PropuestaSupervisor.NIVEL_RECOMENDAR)


def test_las_huellas_de_m09k_no_cambiaron():
    """
    D-3 agregó un mapa APARTE, no un campo a la ficha.

    Si alguien moviera la referencia de conocimiento dentro de 'Habilidad', las
    14 huellas registradas en M09-K dejarían de ser válidas y una propuesta
    vieja ya no podría demostrar con qué definición se emitió.
    """
    esperadas = {
        "H-01": "c687c991fea79985b3dadaf78b751c4c31abe2335d30de08998c2259f37eda27",
        "H-03": "6c4015d1921b6e316864fd5f3de95414c3626aac1c91fa153ac02ce43b62c926",
        "H-05": "f1cf879ab7d5598a3bc8f9f188415a140dbba484cdbc912fac722a7cc9edc94c",
        "H-C4": "625f2faf089791ab8e1c40f48f2d43012416f1ffd7463f8badbda9f95634aea5",
    }
    for id_habilidad, huella in esperadas.items():
        assert habilidades.HABILIDADES[id_habilidad].huella() == huella, \
            f"{id_habilidad} cambió de contenido: la huella de M09-K ya no vale"


# =============================================================================
#  13.  H-05 SIGUE BLOQUEADA
# =============================================================================

def test_h05_sigue_bloqueada():
    h = habilidades.HABILIDADES["H-05"]
    assert h.estado == habilidades.BLOQUEADA
    assert "H-05" not in habilidades.CONOCIMIENTO


# =============================================================================
#  14.  LA REFERENCIA EXTENDIDA
# =============================================================================

def test_el_formato_extendido_conserva_la_primera_mitad():
    """
    Estabilidad hacia atrás: la parte 'habilidad:' no cambió.

    Una propuesta emitida antes de D-3 guarda 'habilidad:H-01@1'; una de después
    guarda 'habilidad:H-01@1 conocimiento:...'. Las dos siguen diciendo lo mismo
    sobre la habilidad.
    """
    r = habilidades.referencia_de(PropuestaSupervisor.CASO_ANTIGUO)
    assert r.startswith("habilidad:H-01@1")
    assert " conocimiento:K-01@1,K-05@1" in r


def test_una_senal_sin_conocimiento_no_menciona_la_palabra():
    """
    Diez de las diez señales... menos las que tienen documento.

    Donde no hay documento, la referencia NO dice 'conocimiento:'. Decirlo con
    una lista vacía sugeriría que hay algo que consultar.
    """
    r = habilidades.referencia_de(PropuestaSupervisor.ACTIVIDAD_VENCIDA)
    assert r == "habilidad:H-06@1"
    assert "conocimiento" not in r


def test_una_senal_desconocida_sigue_devolviendo_vacio():
    assert habilidades.referencia_de("no_existe") == ""


@pytest.mark.parametrize("senal", list(habilidades.POR_SENAL))
def test_toda_referencia_entra_en_el_campo(senal):
    """conocimiento_version es CharField(128). Sin migración, hay que caber."""
    assert len(habilidades.referencia_de(senal)) <= 128


def test_la_propuesta_guarda_habilidad_y_conocimiento(org_a):
    import uuid as _uuid
    from django.utils import timezone
    from operaciones import supervisor

    senal = supervisor.Senal(
        tipo=PropuestaSupervisor.CASO_ANTIGUO, origen_tipo="case",
        origen_id=str(_uuid.uuid4()),
        evidencia=[{"fuente": "case", "id": "x", "dato": "d",
                    "observado_en": timezone.now().isoformat()}],
        huella="h")
    p = supervisor.registrar_propuesta(
        org_a, senal,
        {"accion_propuesta": "x", "motivo": "m", "prioridad": 42,
         "componentes_prioridad": ["base 50"],
         "nivel": PropuestaSupervisor.NIVEL_RECOMENDAR})
    p.refresh_from_db()
    assert p.conocimiento_version == "habilidad:H-01@1 conocimiento:K-01@1,K-05@1"
