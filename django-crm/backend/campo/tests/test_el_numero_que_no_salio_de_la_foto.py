# -*- coding: utf-8 -*-
"""
================================================================================
 UN NUMERO QUE NO SALIO DE ESA PANTALLA VUELVE AL TECNICO  --  09/11/2026
================================================================================
El usuario, probando con una orden nueva:

    «llene una orden nueva y no la devolvio; escribi unos niveles diferentes
     en la foto y vio el error pero no la devolvio»

Y tenia razon las dos veces. El punto `potencia` SI veia el error --lo dice
con los dos numeros en la mano, «la foto marca X y el reporte dice Y»-- pero
`_que_rehacer` no nombraba nada, asi que `atender_la_que_no_cierra` salia por
su `if not requisitos: return "nada"`.

Esa regla tiene su motivo medido (06/11): cuando el punto que falla es
«servicio», el tecnico puede necesitar material, un tercero o que alguien
decida, y mandarselo de vuelta es devolverle un problema que no es suyo. La
medicion no es ese caso: volver a medir y mandar la foto es algo que el
tecnico puede hacer, y es lo que se le pide.

LO QUE NO CAMBIA, Y ES LA MITAD DE LA DECISION DEL 31/10
---------------------------------------------------------
El punto sigue valiendo `True` o `None`, NUNCA `False`. Esa regla es sobre el
VEREDICTO --una lectura que un modelo hizo de una pantalla fotografiada no
puede, por si sola, decir «no se cierra»--. Nombrar algo concreto que rehacer
es otra cosa, y es el mismo camino que ya recorren las fotos con «MUESTRA:
no», cuyo punto tampoco puede decir que no.

QUE PROTEGE DE UNA MALA LECTURA DEL MODELO
-------------------------------------------
Dos cosas que ya existian, y por eso esto no necesita una tercera:
  · `_lectura_creible` descarta lo que el tecnico no habria podido escribir
    -- el «-2.10» que en realidad era «-21.0» sale por ahi;
  · `PF.comparar` perdona hasta TOLERANCIA_DBM (3.0).
Decision del usuario, preguntado entre 3 dBm, ~6 dBm o no devolver: 3 dBm.

QUE AFIRMA ESTA GUARDA
----------------------
  · que la orden VUELVA cuando el numero escrito no salio de la foto
  · que se pida rehacer LA MEDICION QUE NO CUADRA, no la otra
  · que una diferencia dentro de la tolerancia NO devuelva nada
  · que una lectura imposible siga sin devolver: el filtro de arriba manda
  · que no se pida una medicion que la plantilla no declara
  · que el veredicto NO pase a «no se cierra»: el punto sigue sin poder
    decir que no
================================================================================
"""
from __future__ import annotations

from unittest import mock

import pytest

pytestmark = pytest.mark.django_db

FOTOS = ("medicion_al_llegar", "medicion_al_salir")


def _orden(org, numero, *, al_llegar=None, al_salir=None,
           evidencias=FOTOS, vuelta=1):
    """Con el checklist completo: lo unico en juego es la potencia."""
    from campo.models import (EventoTrabajo, OrdenTrabajo, WorkType,
                              WorkTypeVersion)

    campos = [{"id": "potencia_al_llegar", "tipo": "decimal",
               "titulo": "Potencia al llegar",
               "reglas": {"min": -60, "max": -8}},
              {"id": "potencia_al_salir", "tipo": "decimal",
               "titulo": "Potencia al salir",
               "reglas": {"min": -60, "max": -8}}]
    wt = WorkType.objects.create(org=org, codigo=f"pot{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": campos, "evidencias": [
            {"id": f, "tipo": "foto", "titulo": f, "obligatorio": True}
            for f in evidencias]})
    datos = {}
    if al_llegar is not None:
        datos["potencia_al_llegar"] = al_llegar
    if al_salir is not None:
        datos["potencia_al_salir"] = al_salir
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={}, datos=datos, vuelta=vuelta)
    EventoTrabajo.objects.create(
        org=org, orden=orden, tipo="cierre_campo",
        datos={"vuelta": vuelta,
               "respuestas": {"solucion": "se cambia conector APC",
                              "servicio_validado": "Hecho"},
               "sin_material_confirmado": True})
    return orden


def _foto(orden, requisito, texto):
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=orden.vuelta,
        sha256=f"{requisito}{orden.numero}".ljust(64, "x")[:64],
        storage_key=f"k/{requisito}-{orden.numero}",
        nombre_original=f"{requisito}.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    AnalisisDeEvidencia.objects.create(
        org=orden.org, evidencia=ev, vuelta=orden.vuelta, texto=texto)
    return ev


def _revision(orden):
    from campo.revision_del_cierre import revisar

    return revisar(orden)


def _pantalla(dbm):
    return f"la pantalla del medidor se lee: 1310 nm y {dbm} dBm. MUESTRA: si"


# ---------------------------------------------------------------------------
#  1) EL CASO DEL USUARIO
# ---------------------------------------------------------------------------

def test_el_NUMERO_INVENTADO_se_pide_rehacer(org_a):
    """La foto marca -30, el tecnico escribio -15: 15 dBm de diferencia."""
    orden = _orden(org_a, 300, al_llegar="-15.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    r = _revision(orden)

    assert "medicion_al_llegar" in r["sugeridas"], r["sugeridas"]
    assert "medicion_al_salir" not in r["sugeridas"], \
        "se pide rehacer la medicion que SI cuadraba"


def test_LA_ORDEN_VUELVE_DE_VERDAD(org_a):
    """EL EFECTO. Que `sugeridas` la nombre no prueba que la orden vuelva: el
    caso del usuario moria justo despues, en `if not requisitos`."""
    from campo.cierre_por_el_supervisor import atender_la_que_no_cierra
    from campo.models import OrdenTrabajo

    orden = _orden(org_a, 301, al_llegar="-15.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))
    revision = _revision(orden)

    with mock.patch("requests.post") as post:
        post.return_value = mock.Mock(status_code=200, content=b"{}",
                                      json=lambda: {"ok": True})
        resultado = atender_la_que_no_cierra(orden, revision)

    assert resultado == "devuelta", resultado
    fresca = OrdenTrabajo.objects.get(pk=orden.pk)
    assert fresca.estado_operativo == OrdenTrabajo.CORRECCION_REQUERIDA
    assert fresca.vuelta == 2


def test_la_de_SALIDA_tambien(org_a):
    """«La medicion que no cuadra» son dos campos, no uno. Una guarda que
    solo mire la de llegada pasa en verde con la mitad implementada."""
    orden = _orden(org_a, 302, al_llegar="-30.0", al_salir="-12.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-25.0"))

    r = _revision(orden)

    assert r["sugeridas"] == ["medicion_al_salir"], r["sugeridas"]


# ---------------------------------------------------------------------------
#  2) LO QUE NO DEVUELVE
# ---------------------------------------------------------------------------

def test_dentro_de_la_TOLERANCIA_no_se_pide_nada(org_a):
    """2 dBm de diferencia: por debajo de TOLERANCIA_DBM (3.0). Un medidor y
    una foto de su pantalla no tienen por que dar el mismo decimal."""
    orden = _orden(org_a, 303, al_llegar="-28.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    r = _revision(orden)

    assert r["sugeridas"] == [], r["sugeridas"]


def test_una_LECTURA_IMPOSIBLE_sigue_sin_devolver(org_a):
    """EL CASO QUE EL USUARIO YA VIO: el modelo leyo «-2.10» donde la
    pantalla decia «-21.0». Esta fuera de lo que la plantilla deja escribir
    (-60 a -8), asi que `_lectura_creible` la descarta ANTES de comparar --
    y sin ese filtro, esto devolveria una orden bien hecha."""
    orden = _orden(org_a, 304, al_llegar="-21.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-2.10"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    r = _revision(orden)

    assert r["sugeridas"] == [], r["sugeridas"]


def test_una_foto_SIN_NINGUN_NUMERO_no_devuelve_nada(org_a):
    """EL OTRO LADO DEL MISMO RIESGO.

    Si el modelo no pudo leer un numero, no hay nada que comparar, y «no se
    sabe» no puede valer lo mismo que «no cuadra»: eso devolveria una orden
    por una foto borrosa.

    POR QUE ESTA GUARDA EXISTE, dicho por una medicion: la mutacion que
    cambia `ok is False` por `ok is not True` SOBREVIVE sola, y no porque
    falte una guarda -- es equivalente, porque el `continue` de arriba hace
    que `PF.comparar` nunca devuelva None. Mutando las DOS a la vez, muere.
    Esta guarda sostiene el invariante desde el lado que importa: que una
    foto ilegible no mande a nadie a rehacer nada.
    """
    orden = _orden(org_a, 309, al_llegar="-21.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar",
          "la foto esta muy oscura y no se alcanza a leer la pantalla. "
          "MUESTRA: no se sabe")
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    r = _revision(orden)

    assert "medicion_al_llegar" not in r["sugeridas"], r["sugeridas"]


def test_no_se_pide_una_foto_que_la_PLANTILLA_NO_DECLARA(org_a):
    """Una devolucion que pide algo que el formulario no tiene deja al
    tecnico dando vueltas sin poder cumplirla."""
    orden = _orden(org_a, 305, al_llegar="-15.0",
                   evidencias=("medicion_al_salir",))
    #  La foto existe --llego por otro camino-- pero la plantilla no la pide.
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))

    r = _revision(orden)

    assert "medicion_al_llegar" not in r["sugeridas"], r["sugeridas"]


def test_cuando_COINCIDEN_no_pasa_nada(org_a):
    orden = _orden(org_a, 306, al_llegar="-30.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    r = _revision(orden)

    assert r["sugeridas"] == [], r["sugeridas"]
    punto = {p["clave"]: p for p in r["puntos"]}["potencia"]
    assert punto["ok"] is True, punto


# ---------------------------------------------------------------------------
#  3) LA MITAD QUE NO CAMBIA
# ---------------------------------------------------------------------------

def test_el_punto_SIGUE_SIN_PODER_decir_que_no(org_a):
    """La decision del 31/10, intacta.

    Nombrar algo que rehacer no convierte la opinion del modelo en un «no se
    cierra»: el punto queda en None --«miralo vos»-- y el veredicto es «hay
    dudas», no NO_CERRAR. Si algun dia esto pasara a False, el cierre
    autonomo empezaria a frenarse por una lectura no verificada.
    """
    from campo.revision_del_cierre import NO_CERRAR, REVISAR

    orden = _orden(org_a, 307, al_llegar="-15.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    r = _revision(orden)
    punto = {p["clave"]: p for p in r["puntos"]}["potencia"]

    assert punto["ok"] is None, punto
    assert r["veredicto"] == REVISAR, r["veredicto"]
    assert r["veredicto"] != NO_CERRAR


def test_el_texto_del_punto_SIGUE_DICIENDO_los_dos_numeros(org_a):
    """Es lo que le permite decidir a quien mira, y lo que hizo que el
    usuario notara el defecto: el Supervisor «vio el error»."""
    orden = _orden(org_a, 308, al_llegar="-15.0", al_salir="-20.0")
    _foto(orden, "medicion_al_llegar", _pantalla("-30.0"))
    _foto(orden, "medicion_al_salir", _pantalla("-20.0"))

    punto = {p["clave"]: p for p in _revision(orden)["puntos"]}["potencia"]

    assert "-30.0" in punto["texto"] and "-15.0" in punto["texto"], punto["texto"]
