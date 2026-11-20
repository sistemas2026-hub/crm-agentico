# -*- coding: utf-8 -*-
"""
================================================================================
 UNA MEDICION QUE NO SE VERIFICO NO PUEDE PARECER VERIFICADA  --  09/11/2026
================================================================================
MEDIDO DOS VECES EN PRODUCCION (OT #212 y OT #217)
---------------------------------------------------
La pantalla del medidor marca `-21.0 dBm` --el usuario la abrio y lo
confirmo-- y el modelo escribe `-2.10 dBm`: le mueve el punto decimal. El
filtro de `_lectura_creible` hace lo correcto y descarta esa lectura, porque
-2.10 cae fuera de lo que el formulario de la empresa acepta (-60 a -8) y
"corregirla" seria inventar el dato.

EL HUECO: el punto salia diciendo «La potencia que muestra la foto coincide
con la que reporto el tecnico.» a secas. De las DOS mediciones solo se habia
mirado una --la de llegada-- y nada en la revision lo decia. La de salida
pasaba sin verificar, con un tilde verde al lado.

En la OT #217 eso se ve entero:

    al llegar: foto=-50.0  escrito=-50.0  creible=True   -> coinciden
    al salir:  foto=-2.1   escrito=-21.0  creible=False  -> DESCARTADA

LO QUE NO CAMBIA
----------------
El veredicto. Una foto mal leida por un modelo no puede frenar a un tecnico
(decision del 31/10), y menos todavia una que ya se descarto por imposible.
Lo que cambia es lo que se puede SABER leyendo la revision.

El arreglo de fondo --que el modelo no mueva el punto decimal-- va en la
regla 6b de `INSTRUCCION_EVIDENCIA`, y esa no se puede garantizar en codigo.
Estas guardas son la red de abajo: valen aunque el modelo siga leyendo mal.
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

#: Lo que el modelo escribio de verdad en la OT #217, al salir.
LEIDA_IMPOSIBLE = ("Se ve la pantalla de un medidor de potencia óptica Rouhan: "
                   "-2.10 dBm, 0.682 µW, 1550 nm, 2kHz. Lectura legible. "
                   "MUESTRA: si ATENCION: no")
LEIDA_BIEN = ("Medidor óptico Rouhan con pantalla legible: 1550nm, -50.00 dBm, "
              "0.000 µW, 2kHz. MUESTRA: si ATENCION: no")


def _orden(org, numero, *, al_llegar, al_salir, foto_llegar, foto_salir):
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    reglas = {"min": -60, "max": -8}
    wt = WorkType.objects.create(org=org, codigo=f"nad{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [],
                 "campos": [{"id": "potencia_al_llegar", "tipo": "decimal",
                             "titulo": "Medición al llegar", "reglas": reglas},
                            {"id": "potencia_al_salir", "tipo": "decimal",
                             "titulo": "Medición al salir", "reglas": reglas}],
                 "evidencias": [{"id": "medicion_al_llegar", "tipo": "foto",
                                 "titulo": "Medidor al llegar",
                                 "obligatorio": True},
                                {"id": "medicion_al_salir", "tipo": "foto",
                                 "titulo": "Medidor al salir",
                                 "obligatorio": True}]})
    respuestas = {"solucion": "se cambia conector APC",
                  "servicio_validado": "Hecho"}
    datos = {}
    if al_llegar is not None:
        respuestas["potencia_al_llegar"] = al_llegar
        datos["potencia_al_llegar"] = al_llegar
    if al_salir is not None:
        respuestas["potencia_al_salir"] = al_salir
        datos["potencia_al_salir"] = al_salir
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={}, datos=datos, vuelta=1)
    for requisito, texto in (("medicion_al_llegar", foto_llegar),
                             ("medicion_al_salir", foto_salir)):
        if texto is None:
            continue
        ev = EvidenciaTrabajo.objects.create(
            org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            sha256=f"{requisito}{numero}".ljust(64, "x")[:64],
            storage_key=f"k/{requisito}{numero}", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=1,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)
        AnalisisDeEvidencia.objects.create(
            org=org, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=texto)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden


def _potencia(orden):
    from campo import revision_del_cierre as RC

    r = RC.revisar(orden, pendientes=set())
    return next((p for p in r["puntos"] if p["clave"] == "potencia"), None), r


# ---------------------------------------------------------------------------
#  1) EL CASO MEDIDO
# ---------------------------------------------------------------------------

def test_EL_CASO_DE_LA_OT_217(org_a):
    """Una se verifica y la otra no. El texto tiene que decir cual."""
    orden = _orden(org_a, 9701, al_llegar="-50.0", al_salir="-21.0",
                   foto_llegar=LEIDA_BIEN, foto_salir=LEIDA_IMPOSIBLE)

    p, _ = _potencia(orden)

    assert p is not None
    assert p["ok"] is True, "una foto mal leida no puede frenar al tecnico"
    assert "al salir" in p["texto"], p["texto"]
    assert "no se pudo verificar" in p["texto"], p["texto"]


def test_LA_ORDEN_SIGUE_CERRANDO(org_a):
    """EL LIMITE DEL ARREGLO, y es deliberado: informa, no frena. Si esta
    guarda se pusiera en rojo, toda orden con una foto mal leida dejaria de
    cerrar sola -- que es peor que el problema que se arregla."""
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9702, al_llegar="-50.0", al_salir="-21.0",
                   foto_llegar=LEIDA_BIEN, foto_salir=LEIDA_IMPOSIBLE)

    _, r = _potencia(orden)

    assert r["veredicto"] == RC.CERRAR, r["veredicto"]


# ---------------------------------------------------------------------------
#  2) LO QUE NO SE TOCA
# ---------------------------------------------------------------------------

def test_cuando_LAS_DOS_se_leyeron_el_texto_no_agrega_nada(org_a):
    """Sin descartes, el punto dice lo de siempre. Una nota que apareciera
    siempre entrena a ignorarla, que es la regla de la cabecera de `_potencia`."""
    orden = _orden(org_a, 9703, al_llegar="-50.0", al_salir="-50.0",
                   foto_llegar=LEIDA_BIEN, foto_salir=LEIDA_BIEN)

    p, _ = _potencia(orden)

    assert p["ok"] is True
    assert "no se pudo verificar" not in p["texto"], p["texto"]


def test_una_DISCREPANCIA_DE_VERDAD_sigue_devolviendo(org_a):
    """La nota se suma al motivo, no lo reemplaza: la de llegada no coincide
    y la de salida no se pudo mirar, y las dos cosas quedan escritas."""
    orden = _orden(org_a, 9704, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=LEIDA_BIEN, foto_salir=LEIDA_IMPOSIBLE)

    p, _ = _potencia(orden)

    assert p["ok"] is None
    assert "no dicen lo mismo" in p["texto"], p["texto"]
    assert "no se pudo verificar" in p["texto"], p["texto"]
    assert p["rehacer"] == ["medicion_al_llegar"], p["rehacer"]


def test_SIN_NUMERO_ESCRITO_no_se_habla_de_esa_medicion(org_a):
    """La nota dice «no se pudo verificar», y verificar es comparar DOS
    numeros. Sin el escrito no habia nada que verificar y decirlo seria
    acusar al tecnico de algo que no hizo."""
    orden = _orden(org_a, 9705, al_llegar="-50.0", al_salir=None,
                   foto_llegar=LEIDA_BIEN, foto_salir=LEIDA_IMPOSIBLE)

    p, _ = _potencia(orden)

    assert p["ok"] is True
    assert "no se pudo verificar" not in p["texto"], p["texto"]


def test_SIN_FOTO_tampoco(org_a):
    """Ninguna lectura que descartar: la foto no llego."""
    orden = _orden(org_a, 9706, al_llegar="-50.0", al_salir="-21.0",
                   foto_llegar=LEIDA_BIEN, foto_salir=None)

    p, _ = _potencia(orden)

    assert "no se pudo verificar" not in p["texto"], p["texto"]


def test_si_NINGUNA_se_pudo_mirar_el_punto_sigue_sin_aparecer(org_a):
    """EL HUECO QUE QUEDA ABIERTO, escrito a proposito. Sin una sola
    comparacion el punto no aparece --regla de `_potencia`, para no entrenar a
    ignorarlo-- y entonces el descarte tampoco se cuenta. Hoy lo tapa que la
    de llegada casi siempre se lee bien; el dia que no, nadie se entera."""
    orden = _orden(org_a, 9707, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=LEIDA_IMPOSIBLE, foto_salir=LEIDA_IMPOSIBLE)

    p, _ = _potencia(orden)

    assert p is None
