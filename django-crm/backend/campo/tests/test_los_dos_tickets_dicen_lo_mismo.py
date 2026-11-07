# -*- coding: utf-8 -*-
"""
================================================================================
 LOS DOS TICKETS CUENTAN EL MISMO CIERRE  --  07/11/2026
================================================================================
El usuario cerro una orden desde Dexter y comparo lo que quedo escrito:

  WispHub -> «SE VALIDA TICKET / Revision: checklist ok; reporte ok;
              servicio ok; material ok; fotos sin datos»
  Dexter  -> «Campo: se tensiono cable · Tecnico: Mario Vasquez ·
              4 evidencias · OT #186»

El mismo acto, dos historias. Quien abriera el ticket en Dexter veia el
resumen del trabajo del tecnico y no se enteraba de que alguien habia
revisado, ni de que miro.

Y la linea que SI llegaba decia «fotos sin datos», que en el checklist se lee
bien y en fotos suena a que la foto no traia metadatos. Lo que paso es otra
cosa: la inspeccion no pudo concluir.

QUE AFIRMA ESTA GUARDA
----------------------
  · que la nota de Dexter diga QUE se valido, no solo que se cerro
  · que el texto salga de `texto_de_la_revision`, el mismo del ISP: una
    segunda redaccion aca es la forma de que vuelvan a divergir
  · que «sin datos» no vuelva
  · que una orden SIN revision no afirme que alguien reviso
  · que un fallo leyendo la revision no impida el cierre
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
#  EL TEXTO  --  sin base
# ---------------------------------------------------------------------------

def test_un_punto_sin_veredicto_dice_que_NO_SE_PUDO_VERIFICAR():
    """Lo que el usuario leyo en su propia validacion.

    `None` no es «no hay datos de la foto»: es «no se pudo concluir». La
    diferencia importa para quien lee el ticket meses despues y decide si ese
    punto quedo abierto.
    """
    from campo.services.nota_al_isp import texto_de_la_revision

    t = texto_de_la_revision({"puntos": [
        {"clave": "checklist", "ok": True},
        {"clave": "fotos", "ok": None},
    ]})

    assert "fotos no se pudo verificar" in t, t
    assert "sin datos" not in t, t


def test_los_tres_veredictos_se_leen_distinto():
    """ok / no cumple / no se pudo verificar son TRES estados, no dos.

    Si «no se pudo verificar» se leyera igual que «no cumple», una orden que
    nadie pudo medir pareceria una que fallo.
    """
    from campo.services.nota_al_isp import texto_de_la_revision

    t = texto_de_la_revision({"puntos": [
        {"clave": "a", "ok": True},
        {"clave": "b", "ok": False},
        {"clave": "c", "ok": None},
    ]})

    assert "a ok" in t and "b no cumple" in t and "c no se pudo verificar" in t, t


# ---------------------------------------------------------------------------
#  LA NOTA DE DEXTER
# ---------------------------------------------------------------------------

def _orden_con_caso(org_a, user_profile, numero=186):
    from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)
    from cases.models import Case

    caso = Case.objects.create(org=org_a, name="Internet Lento", status="New",
                               priority="Normal", is_active=True)
    wt = WorkType.objects.create(org=org_a, codigo=f"c{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": []})
    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.APROBADO,
        origen_sistema="crm", origen_ref=str(caso.pk), contexto={})
    AsignacionTrabajo.objects.create(orden=orden, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    return orden, caso


def _con_revision(orden, puntos, profile=None):
    from campo.models import EventoTrabajo
    from campo.revision_del_cierre import FOTO

    EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo=FOTO, profile=profile,
        datos={"veredicto": "aprobar", "texto": "", "puntos": puntos})


def test_la_nota_de_dexter_DICE_QUE_SE_VALIDO(org_a, user_profile):
    """EL HALLAZGO DEL USUARIO.

    Se afirma sobre el texto que queda en el ticket, no sobre que la funcion
    se llame: la nota ya existia y ya se escribia -- lo que faltaba era lo
    que decia.
    """
    from campo.devolver_al_ticket import _resumen

    orden, _caso = _orden_con_caso(org_a, user_profile)
    _con_revision(orden, [{"clave": "checklist", "ok": True},
                          {"clave": "fotos", "ok": None}])

    nota = _resumen(orden)

    assert "checklist ok" in nota, nota
    assert "fotos no se pudo verificar" in nota, nota
    #  Y lo de antes sigue: lo primero es lo que el tecnico hizo.
    assert nota.startswith("Campo:"), nota
    assert "OT #186" in nota, nota


def test_el_texto_es_EL_MISMO_que_va_al_ISP(org_a, user_profile):
    """ATA LAS DOS NOTAS.

    Sin esto, cada lado puede redactar lo suyo y volver a divergir -- que es
    exactamente el defecto que se esta arreglando. La unica diferencia
    permitida es «SE VALIDA TICKET», que en WispHub va sola en su renglon
    porque es la frase que ese equipo reconoce.
    """
    from campo.devolver_al_ticket import _resumen
    from campo.services.nota_al_isp import texto_de_la_revision

    puntos = [{"clave": "checklist", "ok": True},
              {"clave": "material", "ok": False},
              {"clave": "fotos", "ok": None}]
    orden, _caso = _orden_con_caso(org_a, user_profile, numero=187)
    _con_revision(orden, puntos)

    del_isp = texto_de_la_revision({"puntos": puntos})
    linea_del_isp = del_isp.split("\n", 1)[1].strip()

    assert linea_del_isp in _resumen(orden), (linea_del_isp, _resumen(orden))


def test_SIN_revision_la_nota_no_afirma_que_alguien_reviso(org_a,
                                                           user_profile):
    """Una orden cerrada sin pasar por la revision.

    Afirmar «Revision: ...» sobre una orden que nadie reviso es peor que no
    decir nada: el ticket quedaria mintiendo, y nadie podria distinguirlo de
    una revision real.
    """
    from campo.devolver_al_ticket import _resumen

    orden, _caso = _orden_con_caso(org_a, user_profile, numero=188)
    nota = _resumen(orden)      # sin EventoTrabajo de revision

    assert "Revision" not in nota, nota
    assert nota.startswith("Campo:"), nota


def test_cuando_la_revision_NO_ENTRA_se_pierde_ella_y_no_la_OT(org_a,
                                                               user_profile):
    """QUE SE SACRIFICA CUANDO NO ENTRA TODO.

    `Comment.comment` es un CharField(255) y la linea de la revision hizo
    crecer la nota. Sin el tope, la revision se agrega igual y el recorte
    final se come el FINAL del texto -- que es donde esta «OT #189», el unico
    dato que permite llegar a la orden desde el ticket.

    MEDIDO EL 07/11/2026: la primera version de esta guarda solo afirmaba
    `len(nota) <= MAX_NOTA`, y sobrevivio a la mutacion que quita el tope,
    porque el recorte final tambien deja 255. Afirmaba el sintoma equivocado.
    """
    from campo.devolver_al_ticket import MAX_NOTA, _resumen

    orden, _caso = _orden_con_caso(org_a, user_profile, numero=189)
    _con_revision(orden, [{"clave": "punto_con_nombre_larguisimo_%d" % i,
                           "ok": None} for i in range(30)])

    nota = _resumen(orden)

    assert len(nota) <= MAX_NOTA, len(nota)
    #  LA QUE MATA: la revision se deja afuera entera, no a medias.
    assert "OT #189" in nota, nota
    assert "Revision" not in nota, nota


def test_si_la_revision_NO_SE_PUEDE_LEER_la_nota_sale_igual(org_a,
                                                            user_profile):
    """La nota es un aviso; el cierre es el hecho.

    Un fallo leyendo la bitacora no puede dejar el ticket sin ninguna nota:
    se pierde la linea de la revision, no las otras.
    """
    from unittest import mock

    from campo.devolver_al_ticket import _resumen

    orden, _caso = _orden_con_caso(org_a, user_profile, numero=190)
    _con_revision(orden, [{"clave": "checklist", "ok": True}])

    with mock.patch("campo.services.nota_al_isp.texto_de_la_revision",
                    side_effect=RuntimeError("se cayo")):
        nota = _resumen(orden)

    assert nota.startswith("Campo:"), nota
    assert "OT #190" in nota, nota
