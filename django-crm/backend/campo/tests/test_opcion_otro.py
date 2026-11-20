# -*- coding: utf-8 -*-
"""
================================================================================
 «OTRO» CON TEXTO EN UN CAMPO DE OPCIONES
================================================================================

Pedido del usuario (18/10/2026): en «Qué encontró» tiene que haber una opción
«Otro» que se pueda llenar, por si lo encontrado no está en la lista.

  A  la plantilla lo declara con una casilla; la opción la pone la plataforma,
     una vez y al final
  B  el texto se guarda al lado del campo, solo si el campo lo permite
  C  elegir «Otro» sin decir qué no deja cerrar la orden ni mandar un reporte
  D  la bitácora lo lee junto: «Otro: lo que escribió»

    pytest campo/tests/test_opcion_otro.py
================================================================================
"""

import pytest

from campo import plantillas as P
from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from campo.services import seguimiento_campo as seg
from campo.services.validador import (validar_campos_tecnicos,
                                      verificar_checklist_completo)
from common.models import Profile

pytestmark = pytest.mark.django_db

CAMPO = {"id": "que_encontro", "titulo": "Qué encontró", "tipo": "seleccion",
         "permite_otro": True,
         "reglas": {"required": True,
                    "options": ["Conector sucio", "Fibra cortada", "Otro"]}}


def _definicion(permite_otro=True, opciones=("Conector sucio", "Fibra cortada")):
    base = P.definicion_de_base(P.CATALOGO_BASE[0])
    base["campos"] = [{"titulo": "Qué encontró", "tipo": P.SELECCION,
                       "opciones": list(opciones), "permite_otro": permite_otro}]
    base["evidencias"] = []
    return base


def test_a_la_plantilla_agrega_otro_una_vez_y_al_final():
    esquema = P.componer(_definicion(opciones=("Otro", "Conector sucio", "Fibra cortada")))
    c = esquema["campos"][0]
    assert c["reglas"]["options"] == ["Conector sucio", "Fibra cortada", "Otro"]
    assert c["permite_otro"] is True
    # El editor no muestra «Otro» en la lista: lo maneja la casilla.
    definicion, motivos = P.leer_definicion(esquema)
    assert motivos == []
    fila = definicion["campos"][0]
    assert fila["permite_otro"] is True and fila["opciones"] == ["Conector sucio", "Fibra cortada"]
    # Y recomponer no lo duplica.
    assert P.componer(definicion)["campos"][0]["reglas"]["options"].count("Otro") == 1


def test_a2_sin_la_casilla_un_otro_escrito_a_mano_queda_como_opcion():
    c = P.componer(_definicion(permite_otro=False, opciones=("A", "Otro")))["campos"][0]
    assert c["reglas"]["options"] == ["A", "Otro"]
    assert "permite_otro" not in c


def test_b_el_texto_se_acepta_solo_si_el_campo_lo_permite():
    limpios, errores = validar_campos_tecnicos(
        {"campos": [CAMPO]}, {"que_encontro": "Otro", "que_encontro_otro": "Roseta quemada"})
    assert errores == {} and limpios["que_encontro_otro"] == "Roseta quemada"

    sin_permiso = dict(CAMPO, permite_otro=False)
    _, errores = validar_campos_tecnicos({"campos": [sin_permiso]},
                                         {"que_encontro_otro": "x"})
    assert "que_encontro_otro" in errores

    # Guardar «Otro» solo, como hace la app al tocarlo, se acepta: el texto se
    # exige al cerrar, no en el instante de elegir.
    _, errores = validar_campos_tecnicos({"campos": [CAMPO]}, {"que_encontro": "Otro"})
    assert errores == {}


@pytest.fixture
def orden(org_a, django_user_model):
    u = django_user_model.objects.create_user(email="t.otro@test.com", password="x")
    p = Profile.objects.create(user=u, org=org_a, role="USER", is_active=True)
    wt = WorkType.objects.create(org=org_a, codigo="corr_otro", nombre="Correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [CAMPO], "evidencias": [],
                 "seguimiento": {"avance": {"campos": [CAMPO], "evidencias": []}}})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=9501, tipo_trabajo_version=v, cliente_nombre="C",
        cliente_direccion="D", estado_operativo=OrdenTrabajo.EN_SITIO, revision=1)
    AsignacionTrabajo.objects.create(orden=o, profile=p, rol="tecnico_lider",
                                     es_principal=True)
    o._tecnico = p
    return o


def test_c_otro_sin_decir_que_no_deja_cerrar(orden):
    orden.datos = {"que_encontro": "Otro"}
    orden.save(update_fields=["datos"])
    errores = verificar_checklist_completo(orden)
    assert any(e["campo_id"] == "que_encontro" and "contá qué fue" in e["mensaje"]
               for e in errores)

    orden.datos = {"que_encontro": "Otro", "que_encontro_otro": "Roseta quemada"}
    orden.save(update_fields=["datos"])
    assert not [e for e in verificar_checklist_completo(orden)
                if e["campo_id"] == "que_encontro"]


def test_c2_un_reporte_con_otro_sin_texto_se_rechaza(orden):
    with pytest.raises(seg.SeguimientoInvalido) as e:
        seg.registrar(orden, profile=orden._tecnico, momento=seg.AVANCE,
                      respuestas={"que_encontro": "Otro"})
    assert "que_encontro" in e.value.errores


def test_d_la_bitacora_lo_lee_junto(orden):
    ev = seg.registrar(orden, profile=orden._tecnico, momento=seg.AVANCE,
                       respuestas={"que_encontro": "Otro",
                                   "que_encontro_otro": "Roseta quemada"})
    fila = next(e for e in seg.linea_de_tiempo(orden)["eventos"] if e["id"] == str(ev.id))
    valores = {d["id"]: d["valor"] for d in fila["detalle"]}
    assert valores == {"que_encontro": "Otro: Roseta quemada"}
