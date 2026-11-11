# -*- coding: utf-8 -*-
"""
================================================================================
 REINTENTAR NO SERVIA DE NADA SI EL INTENTO VIEJO SIGUE CONTANDO  --  11/11/2026
================================================================================
MEDIDO EN LA OT #200, el dia despues de arreglar el reintento
--------------------------------------------------------------
    v1  medicion_al_salir  [recibido]  2 analisis
          ia 10/11 15:17:31  motivo=no se pudo hablar con el motor (ReadTimeout)
          ia 10/11 18:14:45  «Medidor Rouhan; pantalla legible: 1550 nm, -2.10 dBm...»

El reintento hizo su trabajo: la foto se volvio a mirar y la segunda vez se
leyo. Y el punto seguia diciendo:

    [None] fotos: Revisá las fotos: 1 no se pudieron mirar.

`punto_de_la_revision` tomaba TODAS las filas de analisis --la tabla es
append-only, cada intento suma una-- en vez de la ultima de cada foto. El
intento fallido pesaba para siempre y ninguna mirada posterior podia
limpiarlo. El arreglo del dia anterior no podia dar resultado.

EL SEGUNDO HALLAZGO DE LA MISMA SALIDA
---------------------------------------
    [True] potencia: La potencia que muestra la foto coincide con la que
           reporto el tecnico. La medición al salir no se pudo verificar...

El 10/11 se arreglo que el punto no dijera «coincide» cuando una foto no se
habia mirado (`sin_analizar`). El hermano quedo afuera sin que fuera una
decision: cuando la lectura SI llego pero se descarto por imposible
(`sin_mirar`), el punto seguia saliendo en verde con la nota pegada atras.
Para quien decide son la misma ausencia.

QUE AFIRMAN ESTAS GUARDAS
--------------------------
El EFECTO sobre los dos puntos que una persona lee en el panel.
================================================================================
"""
from __future__ import annotations

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


def _orden_200(org, numero, *, texto_al_salir, fallo_antes=True):
    """La OT #200 reducida, con su historia de dos intentos."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"if{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA)
    respuestas = {"potencia_al_llegar": "-50.0", "potencia_al_salir": "-18.0",
                  "solucion": "se cambia conector APC",
                  "servicio_validado": "Hecho"}
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "97997"},
        datos=dict(respuestas), vuelta=1)

    def _foto(requisito, texto, *, con_fallo_previo=False):
        ev = EvidenciaTrabajo.objects.create(
            org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            sha256=f"{requisito}{numero}".ljust(64, "x")[:64],
            storage_key=f"k/{requisito}{numero}", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=1,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)
        if con_fallo_previo:
            AnalisisDeEvidencia.objects.create(
                org=org, evidencia=ev, vuelta=1,
                origen=AnalisisDeEvidencia.IA, texto="",
                motivo="no se pudo hablar con el motor (ReadTimeout)")
        AnalisisDeEvidencia.objects.create(
            org=org, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=texto)
        return ev

    _foto("medicion_al_llegar",
          "Medidor Rouhan con pantalla legible: 1550 nm, -50.00 dBm. "
          "CATALOGO: no MUESTRA: si ATENCION: no")
    _foto("medicion_al_salir", texto_al_salir, con_fallo_previo=fallo_antes)

    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden


# ---------------------------------------------------------------------------
#  1) EL INTENTO FALLIDO DEJA DE PESAR CUANDO EL SIGUIENTE SI LEYO
# ---------------------------------------------------------------------------

def test_UNA_FOTO_RELEIDA_DEJA_DE_CONTAR_COMO_NO_MIRADA(org_a):
    """La guarda del bug. Sin esto el reintento no sirve para nada: el punto
    arrastra el intento fallido para siempre."""
    from campo.inspeccion_visual import punto_de_la_revision

    orden = _orden_200(
        org_a, 9941,
        texto_al_salir="Medidor Rouhan, pantalla legible: 1550 nm, -21.0 dBm. "
                       "CATALOGO: no MUESTRA: si ATENCION: no")

    punto = punto_de_la_revision(orden)

    assert punto is not None
    assert "no se pudieron mirar" not in punto["texto"], punto["texto"]
    assert punto["ok"] is True, punto


def test_PERO_SI_TODOS_LOS_INTENTOS_FALLARON_se_sigue_diciendo(org_a):
    """La otra mitad: una foto que solo tiene intentos fallidos sigue
    contando como no mirada. Sin esto, quedarse con la ultima fila taparia el
    fallo en vez de arreglarlo."""
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.inspeccion_visual import punto_de_la_revision
    from campo.models import EvidenciaTrabajo

    orden = _orden_200(
        org_a, 9942,
        texto_al_salir="Medidor Rouhan, pantalla legible: -21.0 dBm. "
                       "CATALOGO: no MUESTRA: si ATENCION: no")
    #  La de salida pasa a tener SOLO fallos.
    ev = EvidenciaTrabajo.objects.get(org=org_a, orden_trabajo=orden,
                                      requisito_id="medicion_al_salir")
    AnalisisDeEvidencia.objects.filter(org=org_a, evidencia=ev).delete()
    for _ in range(2):
        AnalisisDeEvidencia.objects.create(
            org=org_a, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto="",
            motivo="no se pudo hablar con el motor (ReadTimeout)")

    punto = punto_de_la_revision(orden)

    assert punto["ok"] is None, punto
    assert "no se pudieron mirar" in punto["texto"], punto["texto"]
    #  UNA foto, no dos: los dos intentos son de la misma.
    assert "1 no se pudieron mirar" in punto["texto"], punto["texto"]


# ---------------------------------------------------------------------------
#  2) EL PUNTO DE POTENCIA, CON LA LECTURA DESCARTADA
# ---------------------------------------------------------------------------

def test_UNA_LECTURA_DESCARTADA_NO_DEJA_DECIR_QUE_COINCIDE(org_a):
    """El caso tal cual: el modelo leyo «-2.10» donde la pantalla dice
    «-21.0», se descarto por imposible, y el punto decia «La potencia que
    muestra la foto coincide con la que reporto el tecnico» -- en singular,
    habiendo comparado una de dos.

    SE ARREGLA LA FRASE, NO EL VEREDICTO. La primera version de esta guarda
    pedia `ok is None` y puso en rojo a `test_LA_ORDEN_SIGUE_CERRANDO`
    (09/11), que tiene razon: con el modelo moviendo el punto decimal 3 de
    cada 7 veces, frenar por cada lectura descartada deja de cerrar casi
    todas las ordenes, y eso es peor que el problema. Ahora el punto nombra
    CUAL coincidio, que dice la verdad entera sin frenar nada.
    """
    from campo import revision_del_cierre as RC

    orden = _orden_200(
        org_a, 9943,
        texto_al_salir="Medidor Rouhan; pantalla legible: 1550 nm, -2.10 dBm, "
                       "0.682 µW. CATALOGO: no MUESTRA: si ATENCION: no")

    revision = RC.revisar(orden, pendientes=set())
    punto = next(p for p in revision["puntos"] if p["clave"] == "potencia")

    #  La frase que no puede volver.
    assert "la potencia que muestra la foto coincide" not in \
        punto["texto"].lower(), punto["texto"]
    #  Lo que si tiene que decir: cual se verifico y cual no.
    assert "al llegar" in punto["texto"], punto["texto"]
    assert "no se pudo verificar" in punto["texto"], punto["texto"]
    #  Y no frena: ese es el limite que la guarda del 09/11 protege.
    assert punto["ok"] is True, punto


def test_PERO_SIGUE_SIN_SER_UN_NO(org_a):
    """La regla del 31/10 no se toca: una lectura que un modelo hizo de una
    pantalla fotografiada no puede frenar a un tecnico. `None` pide que lo
    mire una persona; `False` seria frenarlo."""
    from campo import revision_del_cierre as RC

    orden = _orden_200(
        org_a, 9944,
        texto_al_salir="Medidor Rouhan; pantalla: -2.10 dBm. "
                       "CATALOGO: no MUESTRA: si ATENCION: no")

    revision = RC.revisar(orden, pendientes=set())
    punto = next(p for p in revision["puntos"] if p["clave"] == "potencia")

    assert punto["ok"] is not False, punto
    assert not (punto.get("rehacer") or []), punto
    assert "medicion_al_salir" not in (revision["sugeridas"] or []), \
        revision["sugeridas"]


def test_CON_LAS_DOS_BIEN_LEIDAS_sigue_diciendo_que_si(org_a):
    """Si esta guarda se pone en rojo, el cambio dejo de cerrar ordenes
    buenas -- que es el costo que hay que vigilar al apretar un criterio."""
    from campo import revision_del_cierre as RC
    from campo.models import OrdenTrabajo

    orden = _orden_200(
        org_a, 9945,
        texto_al_salir="Medidor Rouhan, pantalla legible: 1550 nm, -18.0 dBm. "
                       "CATALOGO: no MUESTRA: si ATENCION: no")
    OrdenTrabajo.objects.filter(pk=orden.pk).update(
        datos={"potencia_al_llegar": "-50.0", "potencia_al_salir": "-18.0",
               "solucion": "se cambia conector APC",
               "servicio_validado": "Hecho"})
    orden.refresh_from_db()

    revision = RC.revisar(orden, pendientes=set())
    punto = next(p for p in revision["puntos"] if p["clave"] == "potencia")

    assert punto["ok"] is True, punto
    assert "coincide" in punto["texto"].lower(), punto["texto"]
