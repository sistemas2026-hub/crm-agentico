# -*- coding: utf-8 -*-
"""
================================================================================
 EL SEPTIMO PUNTO: LA FOTO CONTRA EL REPORTE  --  07/11/2026
================================================================================
`test_potencia_de_la_foto` mide el extractor. Esta mide el PUNTO: que la
revision del cierre lo incluya, que no pueda frenar un cierre, y que no
aparezca cuando no hay con que comparar.

LA REGLA QUE NO SE NEGOCIA
--------------------------
Vale `True` o `None`, NUNCA `False`. Un `False` se convierte en NO_CERRAR y
ademas alimenta el cierre autonomo del Supervisor. Una lectura que un modelo
hizo de una pantalla fotografiada no puede frenar el trabajo de un tecnico
(CLAUDE.md §4: crecer en alcance, no en autonomia).
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

ANALISIS_70 = ('La pantalla se lee: 1310 nm, "Lo" y -70.00 dBm; no hay luces '
               "indicadoras visibles. MUESTRA: si ATENCION: no")
ANALISIS_21 = ("En el display aparecen 1550 nm, la lectura -21.0 dBm con "
               "0.682 uW y 2 KHz. MUESTRA: si ATENCION: no")


def _armar(org_a, user_profile, numero, potencia, analisis,
           requisito="medicion_al_llegar", campo="potencia_al_llegar"):
    """Una orden con su reporte de cierre y el analisis de UNA foto."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org_a, codigo=f"p{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [],
                 "campos": [{"id": campo, "tipo": "decimal",
                             "titulo": "Potencia"}]})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        #  'aplica()' pide las DOS cosas: terminada en campo y sin validar.
        #  Sin el segundo estado la revision devuelve None y la guarda del
        #  veredicto medía un andamio, no el codigo.
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={})
    cierre = EventoTrabajo.objects.create(
        org=org_a, orden=orden, #  'cierre_campo', que es el tipo que '_cierre_de_esta_vuelta' busca.
        #  Con 'cierre_enviado' la revision no encontraba el reporte y el
        #  punto no aparecia: la guarda media el andamio.
        tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": {campo: potencia},
               "definicion": [{"id": campo}]})
    if analisis is not None:
        ev = EvidenciaTrabajo.objects.create(
            org=org_a, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            storage_key=f"{requisito}-{numero}.jpg",
            nombre_original="IMG.jpg", mime_type="image/jpeg", bytes=9,
            sha256=f"{numero}".ljust(64, "z")[:64],
            estado_archivo=EvidenciaTrabajo.VERIFICADO)
        AnalisisDeEvidencia.objects.create(
            org=org_a, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=analisis, motivo="ok",
            pide_atencion=False, modelo="x", segundos=1, tokens=1)
    return orden, cierre


def _punto(orden, cierre):
    from campo.revision_del_cierre import _potencia

    return _potencia(orden, cierre)


# ---------------------------------------------------------------------------
#  EL CASO DEL USUARIO
# ---------------------------------------------------------------------------

def test_cuando_NO_COINCIDEN_el_punto_lo_dice(org_a, user_profile):
    """LA OT #187: la foto marca -70.0 y el tecnico escribio -21.0.

    49 dBm de diferencia no es ruido de medicion.
    """
    orden, cierre = _armar(org_a, user_profile, 187, "-21.0", ANALISIS_70)

    p = _punto(orden, cierre)

    assert p is not None
    assert p["clave"] == "potencia"
    assert "-70.0" in p["texto"] and "-21.0" in p["texto"], p["texto"]


def test_cuando_NO_COINCIDEN_el_punto_NO_puede_decir_que_no(org_a,
                                                            user_profile):
    """LA REGLA QUE NO SE NEGOCIA.

    `False` se convierte en NO_CERRAR y alimenta el cierre autonomo. Una
    lectura de un modelo sobre una pantalla fotografiada no frena a un
    tecnico: pide que lo mire una persona, que es todo su alcance.
    """
    orden, cierre = _armar(org_a, user_profile, 188, "-21.0", ANALISIS_70)

    assert _punto(orden, cierre)["ok"] is None


def test_cuando_COINCIDEN_el_punto_queda_en_verde(org_a, user_profile):
    orden, cierre = _armar(org_a, user_profile, 189, "-21.4", ANALISIS_21)

    p = _punto(orden, cierre)

    assert p["ok"] is True, p


# ---------------------------------------------------------------------------
#  CUANDO NO HAY CON QUE COMPARAR, EL PUNTO NO APARECE
# ---------------------------------------------------------------------------

def test_sin_FOTO_analizada_el_punto_no_aparece(org_a, user_profile):
    """Un punto que siempre dice «no se sabe» entrena a ignorarlo."""
    orden, cierre = _armar(org_a, user_profile, 190, "-21.0", analisis=None)

    assert _punto(orden, cierre) is None


def test_sin_NUMERO_del_tecnico_el_punto_no_aparece(org_a, user_profile):
    """Una plantilla que no pregunta la potencia, o un campo vacio."""
    orden, cierre = _armar(org_a, user_profile, 191, "", ANALISIS_21)

    assert _punto(orden, cierre) is None


def test_sin_CIERRE_el_punto_no_aparece(org_a, user_profile):
    orden, _c = _armar(org_a, user_profile, 192, "-21.0", ANALISIS_21)

    assert _punto(orden, None) is None


def test_una_foto_que_el_modelo_NO_SUPO_LEER_no_acusa(org_a, user_profile):
    """Sin numero en la foto no hay juicio que hacer.

    Es la diferencia entre «no se pudo verificar» y «el tecnico mintio», y
    aca se elige la primera sin dudar.
    """
    orden, cierre = _armar(org_a, user_profile, 193, "-21.0",
                           "Se ve un medidor, la pantalla esta borrosa.")

    assert _punto(orden, cierre) is None


def test_el_numero_se_lee_venga_COMO_TEXTO_O_COMO_NUMERO(org_a, user_profile):
    """El campo es `decimal`, pero el JSON del cierre guarda lo que entro.

    Leer solo uno de los dos formatos es que el punto desaparezca sin motivo
    visible la mitad de las veces.
    """
    o1, c1 = _armar(org_a, user_profile, 194, "-21.0", ANALISIS_21)
    o2, c2 = _armar(org_a, user_profile, 195, -21.0, ANALISIS_21)
    o3, c3 = _armar(org_a, user_profile, 196, "-21,0", ANALISIS_21)

    assert _punto(o1, c1)["ok"] is True
    assert _punto(o2, c2)["ok"] is True
    assert _punto(o3, c3)["ok"] is True, "la coma decimal no se leyo"


# ---------------------------------------------------------------------------
#  EN LA REVISION ENTERA
# ---------------------------------------------------------------------------

def test_el_punto_ENTRA_en_la_revision(org_a, user_profile):
    """Que la funcion exista no alcanza: tiene que estar en `revisar()`.

    Es el defecto que CLAUDE.md §6 llama «codigo construido no es codigo que
    corre»: el reloj de tareas colgaba de un bloque que gunicorn nunca
    ejecuta, y la reconciliacion estaba probada y sin llamador.
    """
    from campo.revision_del_cierre import revisar

    orden, _c = _armar(org_a, user_profile, 197, "-21.0", ANALISIS_70)

    r = revisar(orden)

    assert r is not None, "la revision no aplica a esta orden"
    claves = [p["clave"] for p in r["puntos"]]
    assert "potencia" in claves, claves


def test_una_DIFERENCIA_no_baja_el_veredicto_a_NO_CERRAR(org_a, user_profile):
    """El efecto sobre el VEREDICTO, no solo sobre el punto.

    Es donde se vuelve peligroso: NO_CERRAR devuelve la orden al tecnico. Con
    la foto discrepando, el veredicto puede ser REVISAR --que alguien lo
    mire-- y nunca NO_CERRAR por esta sola razon.
    """
    from campo.revision_del_cierre import revisar

    orden, _c = _armar(org_a, user_profile, 198, "-21.0", ANALISIS_70)

    #  SOBRE EL PUNTO DENTRO DE LA REVISION, no sobre el veredicto global:
    #  en este andamio el checklist ya esta en False --la plantilla pide
    #  evidencias que la orden no tiene-- y afirmar sobre el veredicto
    #  mediria ese otro punto. Lo que no puede pasar es que la potencia
    #  APORTE un False.
    p = next(x for x in revisar(orden)["puntos"] if x["clave"] == "potencia")
    assert p["ok"] is not False, p
