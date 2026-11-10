# -*- coding: utf-8 -*-
"""
================================================================================
 EL COMANDO QUE DICE POR QUE NO CERRO  --  09/11/2026
================================================================================
`campo/management/commands/por_que_no_cerro.py` existe para no volver a
diagnosticar «los siete puntos en verde y la orden sigue abierta» leyendo
codigo. Un comando de diagnostico que ESCRIBE es peor que no tenerlo: dejaria
la orden trabada una hora por haber preguntado (`_reclamar` escribe un evento)
o la cerraria sin que nadie lo pidiera.

Lo que estas guardas afirman es el EFECTO, no que el comando exista:

  1. nombra el paso que deja la orden afuera, no solo que no cerro
  2. la bitacora queda EXACTAMENTE igual: cero eventos nuevos
  3. el estado de la orden queda igual
  4. no imprime el nombre del cliente (CLAUDE.md §5)
================================================================================
"""
from __future__ import annotations

from io import StringIO

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _nada_espera_medicion(monkeypatch):
    from campo import revision_del_cierre as RC

    monkeypatch.setattr(RC, "pendientes_de_medir",
                        lambda org, ahora=None: set())


def _orden(org, numero, *, vuelta):
    """Terminada y con todo bien: la revision dice «Se puede cerrar»."""
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"pqnc{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": [
            {"id": "foto_ont", "tipo": "foto", "titulo": "Foto de la ONT",
             "obligatorio": True}]})
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={}, vuelta=vuelta)
    EvidenciaTrabajo.objects.create(
        org=org, orden_trabajo=orden, requisito_id="foto_ont", vuelta=vuelta,
        sha256=f"ont{numero}".ljust(64, "x")[:64],
        storage_key=f"k/ont{numero}", nombre_original="ont.jpg",
        mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": vuelta,
               "respuestas": {"solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"},
               "sin_material_confirmado": True})
    return orden


def _correr(org, **kw) -> str:
    from django.core.management import call_command

    salida = StringIO()
    call_command("por_que_no_cerro", org=str(org.id), stdout=salida, **kw)
    return salida.getvalue()


# ---------------------------------------------------------------------------
#  1) DICE DONDE SE CAE
# ---------------------------------------------------------------------------

def test_nombra_el_filtro_de_la_vuelta_cuando_es_ese(org_a):
    """Una orden en vuelta 2 que nadie devolvio: el filtro de la vuelta la
    deja afuera, y el comando lo DICE en vez de decir solo «no cerro»."""
    _orden(org_a, 9801, vuelta=2)

    texto = _correr(org_a, ot=[9801])

    assert "OT #9801" in texto
    assert "LA DEJA AFUERA" in texto
    assert "devuelta_por_el_supervisor=False" in texto


def test_la_devuelta_y_corregida_pasa_el_filtro(org_a):
    """La misma orden, con la devolucion del Supervisor en la bitacora, ya no
    se cae ahi -- es el arreglo del 09/11, visto desde el diagnostico."""
    from campo.cierre_por_el_supervisor import EVENTO_DEVUELTA
    from campo.models import EventoTrabajo

    orden = _orden(org_a, 9802, vuelta=2)
    EventoTrabajo.objects.create(org=org_a, orden=orden, tipo=EVENTO_DEVUELTA,
                                 datos={"requisitos": ["foto_ont"]})

    texto = _correr(org_a, ot=[9802])

    assert "LA DEJA AFUERA" not in texto
    assert "filtro de la vuelta: pasa" in texto


def test_nombra_el_reclamo_que_la_frena_una_hora(org_a):
    """Un intento reciente la frena 60 minutos, y ese es el paso 5. Sin esto,
    el sintoma --«no cerro y no hay nada escrito»-- no distingue este caso de
    los otros cinco."""
    from campo.cierre_por_el_supervisor import EVENTO_INTENTO
    from campo.models import EventoTrabajo

    orden = _orden(org_a, 9803, vuelta=1)
    EventoTrabajo.objects.create(org=org_a, orden=orden, tipo=EVENTO_INTENTO,
                                 datos={})

    texto = _correr(org_a, ot=[9803])

    assert "_reclamar: LA FRENA" in texto


# ---------------------------------------------------------------------------
#  2) NO ESCRIBE NADA
# ---------------------------------------------------------------------------

def test_NO_ESCRIBE_UN_SOLO_EVENTO(org_a):
    """Lo que hace peligroso a un diagnostico: `_reclamar` escribe. Si el
    comando lo llamara, preguntar por que no cerro trabaria la orden una hora.
    Se cuenta la bitacora antes y despues."""
    from campo.models import EventoTrabajo

    orden = _orden(org_a, 9804, vuelta=1)
    antes = EventoTrabajo.objects.filter(org=org_a, orden=orden).count()

    _correr(org_a, ot=[9804])

    assert EventoTrabajo.objects.filter(org=org_a, orden=orden).count() == antes


def test_NO_MUEVE_LA_ORDEN(org_a):
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 9805, vuelta=1)

    _correr(org_a, ot=[9805])

    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
    assert fresca.estado_validacion == OrdenTrabajo.PENDIENTE
    assert fresca.vuelta == 1


# ---------------------------------------------------------------------------
#  3) SIN DATOS DEL CLIENTE
# ---------------------------------------------------------------------------

def test_no_imprime_el_nombre_del_cliente(org_a):
    _orden(org_a, 9806, vuelta=1)

    texto = _correr(org_a, ot=[9806])

    assert "MARIO" not in texto.upper()


def test_el_texto_libre_de_un_evento_no_sale(org_a):
    """`observacion` lleva lo que escribio el tecnico. Sale la CLAVE, nunca su
    contenido."""
    from campo.models import EventoTrabajo

    orden = _orden(org_a, 9807, vuelta=1)
    EventoTrabajo.objects.create(
        org=org_a, orden=orden, tipo="correccion_requerida",
        datos={"observacion": "llamar al 3001234567 antes de ir",
               "requisitos_a_corregir": ["foto_ont"]})

    texto = _correr(org_a, ot=[9807])

    assert "3001234567" not in texto
    assert "observacion=<...>" in texto
    #  Lo que SI sirve para diagnosticar sigue saliendo entero.
    assert "foto_ont" in texto


# ---------------------------------------------------------------------------
#  4) LO QUE NO EXISTE SE DICE
# ---------------------------------------------------------------------------

def test_sin_ninguna_esperando_mira_LAS_DEVUELTAS(org_a):
    """La primera corrida en produccion dijo «No hay ordenes terminadas en
    campo esperando validacion» y se fue: la orden del usuario estaba DEVUELTA,
    y su bitacora --lo unico que podia explicar por que se devolvia otra vez--
    no se imprimio."""
    from campo.cierre_por_el_supervisor import EVENTO_DEVUELTA
    from campo.models import EventoTrabajo, OrdenTrabajo

    orden = _orden(org_a, 9808, vuelta=2)
    orden.estado_operativo = OrdenTrabajo.CORRECCION_REQUERIDA
    orden.estado_validacion = OrdenTrabajo.REQUIERE_CORRECCION
    orden.save(update_fields=["estado_operativo", "estado_validacion"])
    EventoTrabajo.objects.create(org=org_a, orden=orden, tipo=EVENTO_DEVUELTA,
                                 datos={"requisitos": ["foto_ont"]})

    texto = _correr(org_a)

    assert "OT #9808" in texto
    assert "Supervisor DEVOLVIO" in texto
    assert "BITACORA" in texto


def test_una_foto_SIN_ANALIZAR_se_nombra(org_a):
    """Una foto sin fila de analisis no aparece en el veredicto ni como «no se
    pudo mirar»: el punto entero se cae. Desde afuera eso se ve igual que todo
    bien, y es el bug del 09/11 por la manana."""
    _orden(org_a, 9809, vuelta=1)

    texto = _correr(org_a, ot=[9809])

    assert "FOTOS Y LO QUE EL MODELO VIO" in texto
    assert "SIN ANALISIS" in texto


def test_los_dos_numeros_de_la_potencia_salen_juntos(org_a):
    """Lo que devolvio la orden del usuario: el numero escrito contra el de la
    foto. Verlos en lineas separadas obliga a cruzarlos a mano."""
    _orden(org_a, 9810, vuelta=1)

    texto = _correr(org_a, ot=[9810])

    assert "POTENCIA: LA FOTO CONTRA LO ESCRITO" in texto
    assert "al salir: foto=" in texto


def test_una_orden_que_no_existe_se_nombra(org_a):
    texto = _correr(org_a, ot=[9999])

    assert "No existen en esta empresa" in texto
