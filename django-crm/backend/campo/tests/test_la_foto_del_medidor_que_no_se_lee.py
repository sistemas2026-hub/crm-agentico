# -*- coding: utf-8 -*-
"""
================================================================================
 UNA FOTO DE MEDICION SIN NINGUN NUMERO NO SIRVE  --  10/11/2026
================================================================================
EL USUARIO
----------
    «pero y si sale borrosa o movida y si no se puede leer los datos, por que
     no la devolveria»

Y tenia razon, aunque la regla que lo impedia tambien la tenia.

LA DECISION DEL 06/11 QUE NO SE TOCA
-------------------------------------
«4 de 4 fotos piden una mirada» sobre fotos oscuras de un trabajo que estaba
bien hecho. Devolver por eso le haria rehacer al tecnico algo que no esta mal,
y mandarlo de vuelta a la casa del cliente por una OPINION de un modelo es
caro. Por eso solo `MUESTRA: no` devuelve: lo verificable mirando.

LA DISTINCION QUE FALTABA: PARA QUE ESTA ESA FOTO
--------------------------------------------------
  - La del daño encontrado, borrosa, igual muestra algo. Sirve de testimonio.
  - La del medidor tiene UN solo trabajo: que se lea un numero. Si no se lee,
    no sirve para nada.

Y esto no es una opinion del modelo: es que la expresion regular de
`potencia_de_la_foto` no encontro un dBm en lo que el modelo escribio. La
plantilla de la empresa ya declara el criterio: «Basta con que el numero se
lea».

DONDE MORIA ANTES
-----------------
    de_la_foto = PF.uno_solo(_texto_de_la_foto(orden, requisito))
    if escrito is None or de_la_foto is None:
        continue          <- aca, sin dejar rastro

Y si ninguna de las dos mediciones daba numero, `vistos == 0` y el punto no
aparecia: la orden cerraba como si estuviera todo bien.
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

#: Lo que el modelo escribe cuando no puede leer la pantalla.
NO_SE_LEE = ("Se ve un medidor óptico Rouhan de frente. La pantalla está "
             "movida y con reflejos: no se distingue ningún valor.\n"
             "CATALOGO: no\nMUESTRA: no se sabe\nATENCION: si")

SE_LEE = ("Medidor óptico Rouhan, pantalla legible: 1550 nm, -21.0 dBm.\n"
          "CATALOGO: no\nMUESTRA: si\nATENCION: no")

OTRO_VALOR = ("Medidor óptico Rouhan, pantalla legible: 1550 nm, -40.0 dBm.\n"
              "CATALOGO: no\nMUESTRA: si\nATENCION: no")


def _orden(org, numero, *, al_llegar=None, al_salir=None,
           foto_llegar=None, foto_salir=None, declara=("medicion_al_llegar",
                                                       "medicion_al_salir")):
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)

    reglas = {"min": -60, "max": -8}
    wt = WorkType.objects.create(org=org, codigo=f"ill{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [],
                 "campos": [{"id": "potencia_al_llegar", "tipo": "decimal",
                             "titulo": "Medición al llegar", "reglas": reglas},
                            {"id": "potencia_al_salir", "tipo": "decimal",
                             "titulo": "Medición al salir", "reglas": reglas}],
                 "evidencias": [{"id": r, "tipo": "foto", "titulo": r,
                                 "obligatorio": True} for r in declara]})
    respuestas = {"solucion": "se cambia conector APC",
                  "servicio_validado": "Hecho"}
    datos = {}
    for campo, valor in (("potencia_al_llegar", al_llegar),
                         ("potencia_al_salir", al_salir)):
        if valor is not None:
            respuestas[campo] = valor
            datos[campo] = valor
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": "98008"},
        datos=datos, vuelta=1)
    #  `None` = la foto no llego. `""` = llego y NADIE LA MIRO todavia, que
    #  es un estado distinto y el que separa este arreglo de devolver toda
    #  orden cuyo analisis no corrio.
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
        if not texto:
            continue
        AnalisisDeEvidencia.objects.create(
            org=org, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto=texto,
            pide_atencion="ATENCION: si" in texto)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": 1, "respuestas": respuestas,
               "sin_material_confirmado": True})
    return orden


def _revision(orden):
    from campo import revision_del_cierre as RC

    return RC.revisar(orden, pendientes=set())


def _punto(r):
    return next((p for p in r["puntos"] if p["clave"] == "potencia"), None)


# ---------------------------------------------------------------------------
#  1) SE DEVUELVE
# ---------------------------------------------------------------------------

def test_LA_FOTO_QUE_NO_DEJA_LEER_SE_PIDE_REHACER(org_a):
    orden = _orden(org_a, 9501, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=SE_LEE, foto_salir=NO_SE_LEE)

    r = _revision(orden)

    assert "medicion_al_salir" in r["sugeridas"], r["sugeridas"]
    assert "no deja leer" in _punto(r)["texto"], _punto(r)["texto"]


def test_Y_LA_ORDEN_VUELVE_DE_VERDAD(org_a):
    """EL EFECTO. Que `sugeridas` la nombre no prueba que la orden vuelva: ahi
    murio el caso del usuario del 09/11, en el `if not requisitos`."""
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 9502, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=SE_LEE, foto_salir=NO_SE_LEE)
    revision = _revision(orden)

    with mock.patch("campo.services.nota_al_isp._pedir") as pedir:
        pedir.return_value = {"anotada": True, "codigo": "anotada"}
        assert atender_la_que_no_cierra(orden, revision) == "devuelta"

    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA


def test_SI_NINGUNA_SE_LEE_EL_PUNTO_APARECE_IGUAL(org_a):
    """EL HUECO QUE ESTO CIERRA. Sin una sola comparacion, `vistos == 0` y el
    punto se iba en silencio: la orden cerraba como si estuviera todo bien."""
    orden = _orden(org_a, 9503, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=NO_SE_LEE, foto_salir=NO_SE_LEE)

    r = _revision(orden)
    p = _punto(r)

    assert p is not None, "el punto volvio a desaparecer"
    assert sorted(r["sugeridas"]) == ["medicion_al_llegar",
                                      "medicion_al_salir"], r["sugeridas"]


def test_SIN_NUMERO_ESCRITO_TAMBIEN_SE_PIDE(org_a):
    """Decision del usuario, 10/11: faltan las dos cosas y la foto sigue
    siendo obligatoria. Lo que NO se hace es acusar de una discrepancia que
    nadie midio -- para eso esta `test_no_dice_que_no_coinciden`."""
    orden = _orden(org_a, 9504, al_salir=None, foto_salir=NO_SE_LEE,
                   al_llegar="-21.0", foto_llegar=SE_LEE)

    r = _revision(orden)

    assert "medicion_al_salir" in r["sugeridas"], r["sugeridas"]


def test_no_dice_que_no_coinciden(org_a):
    """No se puede afirmar una discrepancia sobre un numero que no se leyo."""
    orden = _orden(org_a, 9505, al_llegar="-21.0", foto_llegar=NO_SE_LEE)

    texto = _punto(_revision(orden))["texto"]

    assert "no dicen lo mismo" not in texto, texto


def test_el_punto_SIGUE_SIN_PODER_DECIR_QUE_NO(org_a):
    """La regla del 31/10 no se toca: `None`, nunca `False`. Un `False` se
    convierte en NO_CERRAR y ademas alimenta el cierre autonomo."""
    orden = _orden(org_a, 9506, al_llegar="-21.0", foto_llegar=NO_SE_LEE)

    assert _punto(_revision(orden))["ok"] is None


# ---------------------------------------------------------------------------
#  2) LO QUE NO SE DEVUELVE
# ---------------------------------------------------------------------------

def test_una_foto_QUE_SI_SE_LEE_no_pide_nada(org_a):
    from campo import revision_del_cierre as RC

    orden = _orden(org_a, 9507, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=SE_LEE, foto_salir=SE_LEE)

    r = _revision(orden)

    assert r["sugeridas"] == [], r["sugeridas"]
    assert r["veredicto"] == RC.CERRAR, r["veredicto"]


def test_una_foto_QUE_NADIE_MIRO_TODAVIA_no_cuenta(org_a):
    """`_texto_de_la_foto` devuelve "" sin analisis, y eso es «todavia nadie
    la miro», nunca «no se lee». Confundirlos devolveria toda orden cuyo
    analisis no corrio -- justo lo que la mirada inmediata vino a evitar.

    La foto SI esta subida (`""`): si no estuviera, el checklist la pediria
    como faltante por otro camino y esta guarda pasaria en verde sin tocar lo
    que dice medir. Lo encontro ella misma, en rojo, la primera vez."""
    orden = _orden(org_a, 9508, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=SE_LEE, foto_salir="")

    r = _revision(orden)

    assert r["sugeridas"] == [], r["sugeridas"]


def test_una_que_la_PLANTILLA_NO_DECLARA_no_se_pide(org_a):
    """Mismo criterio que el rango, las de catalogo y la medicion: pedir
    rehacer algo que el formulario no tiene deja al tecnico sin poder
    cumplirlo."""
    orden = _orden(org_a, 9509, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=SE_LEE, foto_salir=NO_SE_LEE,
                   declara=("medicion_al_llegar",))

    r = _revision(orden)

    assert r["sugeridas"] == [], r["sugeridas"]


def test_una_LECTURA_IMPOSIBLE_no_es_lo_mismo_que_ilegible(org_a):
    """Dos cosas distintas que no se pueden confundir. «-2.10 dBm» SI trae un
    numero: el modelo leyo, leyo mal, y eso ya lo filtra `_lectura_creible`
    sin devolver la orden (OT #217). Ilegible es que no haya numero."""
    imposible = ("Pantalla del medidor: 1550 nm, -2.10 dBm, 0.682 µW.\n"
                 "CATALOGO: no\nMUESTRA: si\nATENCION: no")
    orden = _orden(org_a, 9510, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=SE_LEE, foto_salir=imposible)

    r = _revision(orden)
    texto = _punto(r)["texto"]

    assert r["sugeridas"] == [], r["sugeridas"]
    assert "no deja leer" not in texto, texto
    assert "no se pudo verificar" in texto, texto


def test_la_DISCREPANCIA_sigue_mandando(org_a):
    """Cuando una no cuadra y la otra no se lee, se dicen las dos cosas y se
    piden las dos. Una guarda que mire solo un motivo pasa en verde con la
    mitad implementada."""
    orden = _orden(org_a, 9511, al_llegar="-21.0", al_salir="-21.0",
                   foto_llegar=OTRO_VALOR, foto_salir=NO_SE_LEE)

    r = _revision(orden)
    texto = _punto(r)["texto"]

    assert "no dicen lo mismo" in texto, texto
    assert "no deja leer" in texto, texto
    assert sorted(r["sugeridas"]) == ["medicion_al_llegar",
                                      "medicion_al_salir"], r["sugeridas"]


def test_una_plantilla_SIN_MEDICIONES_no_cambia(org_a):
    """El punto no aparece donde no hay nada que medir, como siempre."""
    orden = _orden(org_a, 9512, declara=())

    assert _punto(_revision(orden)) is None
