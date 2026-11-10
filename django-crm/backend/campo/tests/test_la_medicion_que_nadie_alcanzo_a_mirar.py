# -*- coding: utf-8 -*-
"""
================================================================================
 «LA POTENCIA COINCIDE» CON UNA SOLA DE LAS DOS  --  10/11/2026, OT #200
================================================================================
LA PRUEBA EN VIVO QUE LO ENCONTRO
----------------------------------
El usuario cerro la OT #200 con todo bien MENOS la medicion al salir: escribio
-18.0 dBm y la pantalla del medidor marcaba -21.0. Esperaba una devolucion con
los dos numeros. El panel mostro, en la misma tarjeta:

    ? Revisá las fotos: 1 no se pudieron mirar.
    ✓ La potencia que muestra la foto coincide con la que reporto el tecnico.

La foto que «no se pudo mirar» era justamente la de salida: el Supervisor
reviso antes de que la cola la analizara. Nadie comparo -18.0 contra -21.0, y
el punto de potencia afirmo en verde una coincidencia que solo valia para la
medicion de llegada.

POR QUE SALIA ASI
------------------
`_potencia` sabia decir dos ausencias --`ilegibles` (se miro, no se lee) y
`sin_mirar` (se leyo algo imposible)-- y no la tercera: no hay analisis
todavia. Esa salia por el `continue` sin dejar rastro, y el texto hablaba de
«la potencia» como si las dos mediciones fueran una.

LO QUE CAMBIA Y LO QUE NO
--------------------------
NO se devuelve al tecnico: la foto esta subida y es obligatoria, y que la cola
no la haya mirado no es algo que el pueda rehacer. Cambia lo que se puede
SABER, y el veredicto del punto, que pasa a `None` --«miralo vos»--.

QUE AFIRMAN ESTAS GUARDAS
--------------------------
El EFECTO sobre el punto que la persona lee, no que exista una lista nueva. La
que mata el bug es `test_NO_DICE_QUE_COINCIDE_SI_SOLO_MIRO_UNA`.
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


def _orden(org, numero, *, al_salir_escrito="-18.0", texto_al_salir=None):
    """La OT #200 reducida.

    `texto_al_salir=None` es el caso del bug: la foto esta subida y NO tiene
    analisis. Un texto la pone analizada.
    """
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    wt = WorkType.objects.create(org=org, codigo=f"mn{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA)
    respuestas = {"potencia_al_llegar": "-50.0",
                  "solucion": "se cambia conector APC",
                  "servicio_validado": "Hecho"}
    if al_salir_escrito is not None:
        respuestas["potencia_al_salir"] = al_salir_escrito
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98010"},
        datos=dict(respuestas), vuelta=1)

    def _foto(requisito, texto):
        ev = EvidenciaTrabajo.objects.create(
            org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            sha256=f"{requisito}{numero}".ljust(64, "x")[:64],
            storage_key=f"k/{requisito}{numero}", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=1,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)
        if texto is not None:
            AnalisisDeEvidencia.objects.create(
                org=org, evidencia=ev, vuelta=1,
                origen=AnalisisDeEvidencia.IA, texto=texto)
        return ev

    _foto("medicion_al_llegar",
          "Medidor óptico Rouhan con pantalla legible: 1550 nm, -50.00 dBm, "
          "0.000 µW, 2kHz. CATALOGO: no MUESTRA: si ATENCION: no")
    #  LA DEL BUG: subida, sin analisis.
    _foto("medicion_al_salir", texto_al_salir)

    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden


def _potencia(orden):
    from campo import revision_del_cierre as RC

    revision = RC.revisar(orden, pendientes=set())
    punto = next((p for p in revision["puntos"] if p["clave"] == "potencia"),
                 None)
    return revision, punto


# ---------------------------------------------------------------------------
#  1) LA GUARDA DEL BUG
# ---------------------------------------------------------------------------

def test_NO_DICE_QUE_COINCIDE_SI_SOLO_MIRO_UNA(org_a):
    """Lo que el panel mostro en verde el 10/11. Si esta guarda vuelve a
    permitir ese texto, la OT #200 vuelve a pasar sin que nadie lo note."""
    _, punto = _potencia(_orden(org_a, 9921))

    assert punto is not None, "el punto desaparecio en vez de decir la verdad"
    assert punto["ok"] is None, punto
    assert "coincide" not in punto["texto"].lower(), punto["texto"]


def test_Y_DICE_CUAL_FALTO(org_a):
    """«Solo una» sin decir cual deja a quien mira buscando en cuatro fotos."""
    _, punto = _potencia(_orden(org_a, 9922))

    assert "al salir" in punto["texto"], punto["texto"]
    assert "no se ha revisado" in punto["texto"], punto["texto"]


def test_NO_SE_LE_DEVUELVE_AL_TECNICO(org_a):
    """La foto esta subida. Que la cola no la haya mirado es del sistema, no
    algo que el pueda rehacer: mandarselo de vuelta seria hacerlo viajar."""
    revision, punto = _potencia(_orden(org_a, 9923))

    assert "medicion_al_salir" not in (revision["sugeridas"] or []), \
        revision["sugeridas"]
    assert not (punto.get("rehacer") or []), punto


# ---------------------------------------------------------------------------
#  2) QUE NO SE ROMPIO LO QUE YA ANDABA
# ---------------------------------------------------------------------------

def test_CUANDO_LA_FOTO_SI_SE_MIRO_la_discrepancia_aparece(org_a):
    """La misma orden, con la foto de salida ya analizada: ahi SI se comparan
    los dos numeros y se pide rehacer.

    POR QUE NO USA EL -18.0 DE LA OT #200  --  medido al escribir esto
    ------------------------------------------------------------------
    Esta guarda nacio con el caso tal cual --foto -21.0, escrito -18.0-- y
    salio en rojo: `TOLERANCIA_DBM` vale 3.0 y la comparacion es `<=`, asi
    que esos dos numeros COINCIDEN para el sistema. La diferencia del usuario
    caia exactamente en el borde.

    Son dos cosas distintas y conviene no confundirlas: que la foto no se
    haya mirado es el bug que este archivo cierra; que 3.0 dBm sea mucho o
    poco es una decision de la empresa, con la tolerancia a la vista. Si
    alguna vez baja, esta guarda sigue valiendo -- mide 9 dBm de diferencia,
    no el borde.
    """
    orden = _orden(org_a, 9924, al_salir_escrito="-12.0",
                   texto_al_salir="Medidor óptico Rouhan, pantalla legible: "
                                  "1550 nm, -21.0 dBm, 2kHz. "
                                  "CATALOGO: no MUESTRA: si ATENCION: no")
    revision, punto = _potencia(orden)

    assert punto["ok"] is None, punto
    assert "no dicen lo mismo" in punto["texto"], punto["texto"]
    assert "-21" in punto["texto"] and "-12" in punto["texto"], punto["texto"]
    assert "medicion_al_salir" in revision["sugeridas"], revision["sugeridas"]
    #  Y la ausencia ya no se menciona: esa foto se miro.
    assert "no se ha revisado" not in punto["texto"], punto["texto"]


def test_LAS_DOS_MIRADAS_Y_COINCIDIENDO_sigue_diciendo_que_si(org_a):
    """La prueba 1 del usuario (OT #215, paso sin errores). Si esta guarda se
    pone en rojo, el cambio dejo de cerrar ordenes buenas."""
    orden = _orden(org_a, 9925, al_salir_escrito="-21.0",
                   texto_al_salir="Medidor Rouhan, pantalla legible: 1550 nm, "
                                  "-21.0 dBm. CATALOGO: no MUESTRA: si "
                                  "ATENCION: no")
    _, punto = _potencia(orden)

    assert punto["ok"] is True, punto
    assert "coincide" in punto["texto"].lower(), punto["texto"]


def test_SIN_NUMERO_ESCRITO_no_cuenta_como_ausencia(org_a):
    """Sin numero no hay nada que verificar, y el checklist ya reclama la
    foto por su cuenta. Contarlo aca ensuciaria el punto en toda orden a la
    que le falte un campo."""
    orden = _orden(org_a, 9926, al_salir_escrito=None)
    _, punto = _potencia(orden)

    assert punto is not None
    assert "no se ha revisado" not in punto["texto"], punto["texto"]
    assert punto["ok"] is True, punto
