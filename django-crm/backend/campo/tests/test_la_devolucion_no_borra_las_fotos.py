# -*- coding: utf-8 -*-
"""
================================================================================
 UNA DEVOLUCION NO HACE DESAPARECER LAS FOTOS QUE NADIE PIDIO  --  08/11/2026
================================================================================
El usuario, probando «Devolver al tecnico»:

    «solo pedia dos fotos, el tecnico la corrige y despues salen dos que
    mandaron y esas el tecnico no las volvio a tomar porque no las pedian»

Y la revision las mostraba en rojo, «No llego», mientras arriba decia «El
checklist esta completo: datos y fotos». La misma tarjeta afirmando las dos
cosas.

LA CAUSA: TRES REGLAS PARA LA MISMA PREGUNTA. `services/validador.py` ya
tenia la buena --un requisito que NO se pidio rehacer se satisface con la
evidencia de CUALQUIER vuelta, y uno que SI se pidio exige una nueva-- y la
lista de fotos de la revision usaba otra: solo la vuelta que corre.

Ahora las dos dicen lo mismo. Mostrar la ultima de cada requisito no afloja
nada: al tecnico que no rehizo lo que le pidieron lo sigue frenando el
checklist, que es quien dice «hace falta evidencia nueva, de esta vuelta».

QUE AFIRMA ESTA GUARDA
----------------------
  · que la foto de la vuelta 1 que nadie pidio rehacer SIGA mostrandose
  · que la rehecha GANE sobre la vieja -- lo que el tecnico corrigio es lo
    que hay que mirar
  · que su analisis viaje con ella: una foto sin lo que la IA vio es media
    lista
  · y que el que NO rehizo lo pedido siga sin pasar -- por el checklist, no
    porque una foto desaparezca
================================================================================
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

FOTOS = ("medicion_al_llegar", "dano_encontrado", "medicion_al_salir")


def _orden_en_vuelta_2(org, numero=950):
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    wt = WorkType.objects.create(org=org, codigo=f"dev{numero}",
                                 nombre="Soporte", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "campos": [], "evidencias": [
            {"id": f, "tipo": "foto", "titulo": f, "obligatorio": True}
            for f in FOTOS]})
    return OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=version,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        origen_sistema="manual", contexto={}, vuelta=2)


def _foto(orden, requisito, vuelta, *, texto=None):
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo

    ev = EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito,
        vuelta=vuelta,
        sha256=f"{requisito}{vuelta}{orden.numero}".ljust(64, "x")[:64],
        storage_key=f"k/{requisito}-v{vuelta}",
        nombre_original=f"{requisito}.jpg", mime_type="image/jpeg", bytes=1,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)
    if texto:
        AnalisisDeEvidencia.objects.create(
            org=orden.org, evidencia=ev, vuelta=vuelta, texto=texto)
    return ev


def _lista(orden):
    from campo.revision_del_cierre import _evidencias_para_revisar

    esquema = orden.tipo_trabajo_version.esquema
    return {f["id"]: f for f in _evidencias_para_revisar(orden, esquema)}


# ---------------------------------------------------------------------------
#  EL CASO QUE EL USUARIO ENCONTRO
# ---------------------------------------------------------------------------

def test_la_foto_que_NADIE_PIDIO_REHACER_sigue_ahi(org_a):
    orden = _orden_en_vuelta_2(org_a, 950)
    #  Las tres llegaron en la vuelta 1; solo una se rehizo en la 2.
    for f in FOTOS:
        _foto(orden, f, 1)
    _foto(orden, "dano_encontrado", 2)

    fotos = _lista(orden)

    for f in FOTOS:
        assert fotos[f]["evidencia_id"], (
            f"«{f}» aparece como que no llego, y el tecnico la mando en la "
            f"vuelta 1 porque nadie le pidio rehacerla")


def test_la_REHECHA_gana_sobre_la_vieja(org_a):
    """Lo que el tecnico corrigio es lo que hay que mirar."""
    orden = _orden_en_vuelta_2(org_a, 951)
    vieja = _foto(orden, "dano_encontrado", 1)
    nueva = _foto(orden, "dano_encontrado", 2)

    fotos = _lista(orden)

    assert fotos["dano_encontrado"]["evidencia_id"] == str(nueva.id), (
        "se mostro la foto vieja: el tecnico la rehizo y esa es la que vale")
    assert fotos["dano_encontrado"]["evidencia_id"] != str(vieja.id)


def test_el_analisis_VIAJA_CON_la_foto_que_se_muestra(org_a):
    """Una foto sin lo que la IA vio es media lista: el supervisor compara
    contra el titulo y no puede decidir nada."""
    orden = _orden_en_vuelta_2(org_a, 952)
    _foto(orden, "medicion_al_salir", 1, texto="se lee -21.0 dBm")

    fotos = _lista(orden)

    assert "-21.0" in str(fotos["medicion_al_salir"].get("analisis") or ""), \
        fotos["medicion_al_salir"]


def test_la_potencia_de_una_foto_de_la_vuelta_ANTERIOR_se_compara(org_a):
    """`_texto_de_la_foto` tenia el mismo filtro: sin esto, la comparacion
    desaparecia en silencio justo donde habia mas para mirar."""
    from campo.revision_del_cierre import _texto_de_la_foto

    orden = _orden_en_vuelta_2(org_a, 953)
    _foto(orden, "medicion_al_salir", 1, texto="se lee 1550 nm y -21.0 dBm")

    assert "-21.0" in _texto_de_la_foto(orden, "medicion_al_salir")


# ---------------------------------------------------------------------------
#  Y NO AFLOJA NADA
# ---------------------------------------------------------------------------

def test_una_foto_que_NUNCA_llego_sigue_faltando(org_a):
    orden = _orden_en_vuelta_2(org_a, 954)
    _foto(orden, "dano_encontrado", 1)

    fotos = _lista(orden)

    assert fotos["medicion_al_salir"]["evidencia_id"] is None
    assert fotos["dano_encontrado"]["evidencia_id"]


def test_al_que_NO_REHIZO_lo_pedido_lo_frena_el_CHECKLIST(org_a):
    """El punto que hay que mirar no es la lista de fotos.

    Mostrar la de la vuelta anterior no deja pasar a quien ignoro la
    devolucion: `verificar_checklist_completo` exige evidencia NUEVA para los
    requisitos que el Supervisor nombro al devolver, y eso no cambio.
    """
    from campo.services.validador import verificar_checklist_completo

    orden = _orden_en_vuelta_2(org_a, 955)
    for f in FOTOS:
        _foto(orden, f, 1)
    #  EL SUPERVISOR PIDIO REHACER UNA, Y EL TECNICO NO LA REHIZO.
    #
    #  Lo que se devolvio sale de la BITACORA, no de una columna: un evento
    #  `correccion_requerida` con `vuelta_nueva` y `requisitos_a_corregir`
    #  (ver `validador.devolucion_vigente`). La primera version de esta
    #  guarda invento un campo `orden.correccion` que no existe y fallo al
    #  guardar -- otra vez un andamiaje con la forma que yo supuse en vez de
    #  la que el productor escribe.
    from campo.models import EventoTrabajo
    EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="correccion_requerida",
        datos={"vuelta_nueva": orden.vuelta,
               "requisitos_a_corregir": ["medicion_al_salir"],
               "observacion": "la pantalla no se lee"})

    errores = verificar_checklist_completo(orden)

    assert any("medicion_al_salir" == e.get("requisito_id") for e in errores), (
        "el checklist dio por buena una orden donde el tecnico no rehizo la "
        "foto que se le pidio: " + str(errores))


def test_una_foto_VIEJA_reintentada_NO_le_gana_a_la_rehecha(org_a):
    """EL CASO QUE ESTE ARREGLO CASI ROMPE.

    `test_revision_del_cierre.test_f8` lo cazo: la app ENCOLA las fotos y
    reintenta, asi que una de la vuelta 1 puede entrar al servidor DESPUES
    de la de la vuelta 2. Mostrar «la ultima por fecha» la elegiria a ella --
    y es justo la que el supervisor ya rechazo.

    Por eso el orden es `vuelta` primero y `recibida_en_servidor` despues:
    la rehecha gana aunque haya llegado antes, y la que nadie pidio rehacer
    sigue siendo la evidencia de su requisito. Las dos cosas a la vez.
    """
    import datetime as dt

    from campo.models import EvidenciaTrabajo

    orden = _orden_en_vuelta_2(org_a, 956)
    vieja = _foto(orden, "dano_encontrado", 1)
    nueva = _foto(orden, "dano_encontrado", 2)
    #  La vieja se reintento y entro CINCO MINUTOS DESPUES que la nueva.
    EvidenciaTrabajo.objects.filter(pk=vieja.pk).update(
        recibida_en_servidor=nueva.recibida_en_servidor
        + dt.timedelta(minutes=5))

    fotos = _lista(orden)

    assert fotos["dano_encontrado"]["evidencia_id"] == str(nueva.id), (
        "gano la foto que el supervisor ya habia rechazado, solo porque "
        "entro ultima al servidor")


def test_la_POTENCIA_tampoco_lee_la_foto_vieja_reintentada(org_a):
    """El mismo caso de arriba, en la otra consulta.

    `_texto_de_la_foto` tenia su propio orden, y sin la vuelta adelante leia
    el analisis de la foto REINTENTADA de la vuelta 1 -- la que el supervisor
    ya rechazo-- y comparaba la potencia contra ella. Medido el 08/11/2026:
    sin esta guarda la mutacion que quita `-vuelta` sobrevive.
    """
    import datetime as dt

    from campo.models import AnalisisDeEvidencia
    from campo.revision_del_cierre import _texto_de_la_foto

    orden = _orden_en_vuelta_2(org_a, 957)
    _foto(orden, "medicion_al_salir", 1, texto="la vieja dice -70.00 dBm")
    nueva = _foto(orden, "medicion_al_salir", 2,
                  texto="la rehecha dice -21.0 dBm")
    #  El analisis de la vieja se rehizo y quedo MAS NUEVO por fecha.
    de_la_nueva = AnalisisDeEvidencia.objects.get(evidencia=nueva)
    (AnalisisDeEvidencia.objects
     .filter(evidencia__vuelta=1, evidencia__orden_trabajo=orden)
     .update(created_at=de_la_nueva.created_at + dt.timedelta(minutes=5)))

    texto = _texto_de_la_foto(orden, "medicion_al_salir")

    assert "-21.0" in texto, (
        "se leyo el analisis de la foto que el supervisor ya habia "
        "rechazado: " + texto)
    assert "-70.00" not in texto, texto
