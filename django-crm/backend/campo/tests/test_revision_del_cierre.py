# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR REVISA EL CIERRE DEL TECNICO  --  30/10/2026
================================================================================
SPEC/objetivos/revision-del-cierre.md. Ver `campo/revision_del_cierre.py`.

  V1  todo bien: «Se puede cerrar», y cada punto dice por que.
  V2  un «no» manda: el tecnico dice que el servicio NO quedo, o la señal NO
      quedo en rango, o falta una foto (y la sugiere para devolver).
  V3  un «no se sabe» pide revisar: sin material ni confirmacion de que no uso.
  V4  el reporte de una vuelta YA DEVUELTA no cuenta.
  V5  lo que no aplica: una plantilla que no pregunta por el servicio, una
      orden sin medicion, una orden que no esta esperando validacion.
  V6  Programacion trae la revision en la orden terminada, y nada en las otras.
  V7  INDICA, NO DECIDE: revisar no aprueba, no cierra y no toca la orden.
  V8  la medicion de otra empresa no entra.

    pytest campo/tests/test_revision_del_cierre.py
================================================================================
"""
import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone

from campo import dia_publicado as D
from campo import revision_del_cierre as RC
from campo.cuadrillas import Cuadrilla, IntegranteDeJornada, JornadaDeCuadrilla, PersonaDeCampo
from campo.models import (
    AsignacionTrabajo,
    EventoTrabajo,
    EvidenciaTrabajo,
    MaterialCatalogo,
    MovimientoDeMaterial,
    OrdenTrabajo,
    WorkType,
    WorkTypeVersion,
)
from operaciones.models import PropuestaSupervisor
from operaciones.verificacion_de_arreglos import FUENTE

pytestmark = pytest.mark.django_db

PREGUNTAS = [{"id": "solucion", "tipo": "texto"}, {"id": "servicio_validado", "tipo": "booleano"}]


@pytest.fixture
def org(org_a):
    org_a.timezone = "America/Bogota"
    org_a.save(update_fields=["timezone"])
    return org_a


@pytest.fixture
def orden(org, user_profile):
    wt = WorkType.objects.create(org=org, codigo="sop", nombre="Soporte",
                                 labor=JornadaDeCuadrilla.CORRECTIVO)
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": [
            {"id": "foto_ont", "titulo": "Foto de la ONT", "tipo": "foto", "obligatorio": True}]})
    o = OrdenTrabajo.objects.create(
        org=org, numero=3, tipo_trabajo_version=v, zona="X",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE, completada_campo_en=timezone.now())
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile, rol="tecnico",
                                     es_principal=True)
    return o


def _foto(orden, requisito="foto_ont"):
    return EvidenciaTrabajo.objects.create(
        org=orden.org, orden_trabajo=orden, requisito_id=requisito, vuelta=orden.vuelta,
        sha256=f"{requisito}-{orden.vuelta}", storage_key=f"k/{requisito}",
        nombre_original=f"{requisito}.jpg", mime_type="image/jpeg", bytes=1024,
        estado_archivo=EvidenciaTrabajo.RECIBIDO)


def _cierre(orden, servicio=True, definicion=PREGUNTAS, **extra):
    return EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo="cierre_campo",
        datos={"definicion": definicion,
               "respuestas": {"solucion": "Cambié el conector", "servicio_validado": servicio},
               **extra})


def _consumo(orden, profile):
    m = MaterialCatalogo.objects.create(org=orden.org, codigo="CON", nombre="Conector",
                                        unidad="u")
    return MovimientoDeMaterial.objects.create(
        org=orden.org, material=m, orden=orden, tipo=MovimientoDeMaterial.CONSUMO,
        cantidad=Decimal("1"), profile=profile, idempotency_key=f"rc-{orden.id}")


def _medicion(orden, en_rango):
    return PropuestaSupervisor.objects.create(
        org=orden.org, origen_id="caso-1", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": FUENTE, "orden": str(orden.id), "quedo_en_rango": en_rango}])


def _claves(r):
    return {p["clave"]: p["ok"] for p in r["puntos"]}


# ---------------------------------------------------------------------------
# Las fotos, para que el supervisor pueda COMPARAR  --  06/11/2026
#
# El usuario: «el supervisor debe revisar si las fotos coinciden con lo
# pedido; si piden foto del router y manda el TV no debe pasar, y si pide la
# potencia y no manda la potencia no deberia pasar».
#
# El hueco era de INFORMACION, no de poder: el boton «Devolver al tecnico» ya
# existia, pero la revision mandaba solo `{id, titulo}` de cada evidencia --
# sin las instrucciones y sin la imagen--, asi que no habia con que comparar.
# Decir «el checklist esta completo» es contar fotos, no mirarlas.
# ---------------------------------------------------------------------------

def _con_instrucciones(orden, instrucciones="Pantalla del medidor con la lectura legible."):
    """La orden pasa a una version NUEVA que declara que tenia que mostrar.

    NO SE EDITA EL ESQUEMA PUBLICADO, y el primer intento de esta prueba lo
    hacia: `WorkTypeVersion.objects.filter(...).update(esquema=...)` fallo con
    «No se permite modificar el esquema de versiones PUBLICADAS». La guarda
    (`models.py:95-117`) hizo exactamente su trabajo, y vale dejarlo escrito:
    lo que se le pidio a una orden no puede cambiar despues, y por eso la
    respuesta a «que se le pidio» se lee de una fila que nadie pudo tocar.

    Asi que se crea otra version con su esquema propio y la orden apunta ahi,
    que es lo que pasaria en la realidad: la empresa publica v2 y las ordenes
    nuevas salen con esa.
    """
    v = orden.tipo_trabajo_version
    esquema = dict(v.esquema)
    esquema["evidencias"] = [
        {**e, "instrucciones": instrucciones} for e in esquema["evidencias"]]
    nueva = WorkTypeVersion.objects.create(
        work_type=v.work_type, version=v.version + 1,
        estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(tipo_trabajo_version=nueva)
    orden.refresh_from_db()
    return orden


def _lo_que_vio_la_ia(evidencia, texto, pide_atencion=False):
    from campo.models import AnalisisDeEvidencia

    return AnalisisDeEvidencia.objects.create(
        org=evidencia.org, evidencia=evidencia, vuelta=evidencia.vuelta,
        origen=AnalisisDeEvidencia.IA, texto=texto, pide_atencion=pide_atencion)


def _ev(r, requisito="foto_ont"):
    return next(e for e in r["evidencias"] if e["id"] == requisito)


def test_f1_cada_foto_dice_QUE_TENIA_QUE_MOSTRAR(orden, user_profile):
    #  La mitad de la comparacion que faltaba. Sin esto el supervisor compara
    #  contra un titulo de tres palabras.
    _con_instrucciones(orden)
    _foto(orden)
    _cierre(orden)

    e = _ev(RC.revisar(orden))

    assert e["instrucciones"] == "Pantalla del medidor con la lectura legible."
    assert e["titulo"] == "Foto de la ONT"


def test_f2_y_con_que_VER_la_que_llego(orden, user_profile):
    #  La otra mitad: el id con el que se pide la imagen. No se manda la
    #  imagen: una respuesta de revision no carga megabytes de fotos.
    foto = _foto(orden)
    _cierre(orden)

    e = _ev(RC.revisar(orden))

    assert e["evidencia_id"] == str(foto.id)


def test_f3_LA_QUE_FALTA_tambien_sale_y_se_distingue(orden, user_profile):
    #  EL SEGUNDO CASO DEL USUARIO: «si pide la potencia y no manda la
    #  potencia». Si desapareciera de la lista, el supervisor veria menos
    #  filas sin notar cual falta -- que es justo la que hay que mirar.
    _cierre(orden)                              # sin foto

    e = _ev(RC.revisar(orden))

    assert e["evidencia_id"] is None
    assert e["titulo"] == "Foto de la ONT"
    assert e["obligatoria"] is True


def test_f4_lo_que_la_IA_VIO_viaja_como_texto(orden, user_profile):
    #  EL PRIMER CASO DEL USUARIO: «si piden foto del router y manda el TV».
    #  La IA lo describe; QUIEN DECIDE ES EL SUPERVISOR, que para eso tiene
    #  «Devolver al tecnico». Ver el encabezado de `inspeccion_visual.py`:
    #  la IA puede pedir atencion, nunca negar un cierre (31/10/2026).
    _con_instrucciones(orden, "El router, con sus luces visibles.")
    foto = _foto(orden)
    _lo_que_vio_la_ia(foto, "Se ve un televisor encendido, no un router.",
                      pide_atencion=True)
    _cierre(orden)

    e = _ev(RC.revisar(orden))

    assert "televisor" in e["analisis"]
    assert e["pide_atencion"] is True
    #  Y lo pedido sigue al lado, que es lo que permite ver que no coincide.
    assert "router" in e["instrucciones"]


def test_f5_la_IA_NO_convierte_su_opinion_en_un_NO(orden, user_profile):
    #  LA GARANTIA QUE NO SE TOCA. Una foto que la IA marca sigue dejando el
    #  veredicto en manos de los OTROS puntos: aca el cierre no se puede dar
    #  por bueno solo (hay cosas sin verificar), pero la razon no es la IA.
    _con_instrucciones(orden)
    foto = _foto(orden)
    _lo_que_vio_la_ia(foto, "Se ve un televisor.", pide_atencion=True)
    _cierre(orden)

    r = RC.revisar(orden)

    assert r["veredicto"] != RC.NO_CERRAR, (
        "la IA pide atencion; NO niega un cierre")


def test_f6_sin_analisis_no_se_inventa_ninguno(orden, user_profile):
    #  La visión puede estar apagada, o la foto en un formato que no se mira.
    #  Silencio NO es aprobacion: se manda vacio, y la pantalla no puede
    #  mostrar un «lo revisó la IA» que no pasó.
    _foto(orden)
    _cierre(orden)

    e = _ev(RC.revisar(orden))

    assert e["analisis"] == ""
    assert e["pide_atencion"] is False


def test_f7_solo_la_vuelta_que_corre(orden, user_profile):
    #  Una orden devuelta y rehecha tiene fotos NUEVAS; la de la vuelta
    #  anterior no dice nada de esta. Si se colara, el supervisor aprobaria
    #  mirando la foto que ya habia rechazado.
    vieja = _foto(orden)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=2)
    orden.refresh_from_db()
    nueva = _foto(orden)
    _cierre(orden)

    e = _ev(RC.revisar(orden))

    assert e["evidencia_id"] == str(nueva.id)
    assert e["evidencia_id"] != str(vieja.id)


def test_f8_una_foto_VIEJA_que_llega_tarde_no_gana(orden, user_profile):
    """SE MIDIO QUE HACIA FALTA (06/11/2026).

    `test_f7` no mataba la mutacion que quita el filtro de vuelta: sin el, la
    consulta trae las dos vueltas, pero el "ultima gana" por
    `recibida_en_servidor` dejaba igual la nueva. La prueba afirmaba el
    resultado sin distinguir QUIEN lo logro.

    Este es el caso donde el orden por fecha NO alcanza, y es real: la app
    encola las fotos y reintenta. Una de la vuelta 1 que se reintento y llego
    DESPUES de la de la vuelta 2 queda ultima por fecha -- y es justo la que
    el supervisor ya habia rechazado. Sin el filtro, aprobaria mirandola.
    """
    vieja = _foto(orden)
    OrdenTrabajo.objects.filter(pk=orden.pk).update(vuelta=2)
    orden.refresh_from_db()
    nueva = _foto(orden)
    #  La vieja se reintento y entro al servidor DESPUES que la nueva.
    EvidenciaTrabajo.objects.filter(pk=vieja.pk).update(
        recibida_en_servidor=nueva.recibida_en_servidor + dt.timedelta(minutes=5))
    _cierre(orden)

    e = _ev(RC.revisar(orden))

    assert e["evidencia_id"] == str(nueva.id), (
        "manda la vuelta que corre, no la que entro ultima al servidor")


def test_v1_todo_bien_se_puede_cerrar_y_dice_por_que(orden, user_profile):
    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    _medicion(orden, True)

    r = RC.revisar(orden)

    assert (r["veredicto"], r["texto"]) == (RC.CERRAR, "Se puede cerrar")
    assert _claves(r) == {"checklist": True, "reporte": True, "servicio": True,
                          "medicion": True, "material": True}
    assert r["solucion"] == "Cambié el conector"
    #  06/11/2026: esta lista gano `instrucciones`, `evidencia_id`,
    #  `analisis` y `pide_atencion` para que el supervisor pueda COMPARAR lo
    #  pedido con lo que llego. Se afirma lo que esta prueba vino a cuidar
    #  --que el requisito este, con su titulo-- y no la forma entera, que
    #  volveria a romper con cada dato nuevo sin que eso signifique nada.
    assert [(e["id"], e["titulo"]) for e in r["evidencias"]] == [
        ("foto_ont", "Foto de la ONT")]
    assert r["sugeridas"] == []


def test_v2_un_no_manda(orden, user_profile):
    _foto(orden)
    _consumo(orden, user_profile)
    _cierre(orden, servicio=False)
    r = RC.revisar(orden)
    assert r["veredicto"] == RC.NO_CERRAR
    assert "El técnico dice que el servicio NO quedó funcionando." in [
        p["texto"] for p in r["puntos"] if p["ok"] is False]

    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").delete()
    _cierre(orden)
    _medicion(orden, False)
    assert RC.revisar(orden)["veredicto"] == RC.NO_CERRAR

    PropuestaSupervisor.objects.all().delete()
    EvidenciaTrabajo.objects.all().delete()
    r = RC.revisar(orden)
    assert (r["veredicto"], _claves(r)["checklist"], r["sugeridas"]) == (
        RC.NO_CERRAR, False, ["foto_ont"])


def test_v3_un_no_se_sabe_pide_revisar(orden, user_profile):
    _foto(orden)
    _cierre(orden)
    r = RC.revisar(orden)
    assert (r["veredicto"], _claves(r)["material"]) == (RC.REVISAR, None)

    EventoTrabajo.objects.filter(orden=orden, tipo="cierre_campo").delete()
    _cierre(orden, sin_material_confirmado=True)
    assert RC.revisar(orden)["veredicto"] == RC.CERRAR

    _medicion(orden, None)
    assert RC.revisar(orden)["veredicto"] == RC.REVISAR


def test_v4_el_reporte_de_una_vuelta_ya_devuelta_no_cuenta(orden, user_profile):
    _foto(orden)
    _consumo(orden, user_profile)
    viejo = _cierre(orden)
    EventoTrabajo.objects.filter(pk=viejo.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=2))
    EventoTrabajo.objects.create(org=orden.org, orden=orden, tipo="reapertura_correccion",
                                 datos={})

    r = RC.revisar(orden)
    assert (r["veredicto"], _claves(r)["reporte"]) == (RC.NO_CERRAR, False)
    assert "servicio" not in _claves(r), "sin el cierre de esta vuelta no hay que preguntar"


def test_v5_lo_que_no_aplica(orden, user_profile):
    _foto(orden)
    _consumo(orden, user_profile)
    _cierre(orden, definicion=[{"id": "solucion", "tipo": "texto"}])
    r = RC.revisar(orden)
    assert set(_claves(r)) == {"checklist", "reporte", "material"}
    assert r["veredicto"] == RC.CERRAR

    for estado, validacion in ((OrdenTrabajo.EN_SITIO, OrdenTrabajo.SIN_EVALUAR),
                               (OrdenTrabajo.COMPLETADA_CAMPO, OrdenTrabajo.APROBADO),
                               (OrdenTrabajo.CERRADA, OrdenTrabajo.APROBADO)):
        orden.estado_operativo, orden.estado_validacion = estado, validacion
        assert RC.revisar(orden) is None


def test_v6_programacion_trae_la_revision_en_la_terminada(org, orden, user_profile):
    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    import zoneinfo

    hoy = timezone.now().astimezone(zoneinfo.ZoneInfo("America/Bogota")).date()
    c = Cuadrilla.objects.create(org=org, nombre="Cuadrilla #5")
    j = JornadaDeCuadrilla.objects.create(org=org, cuadrilla=c, fecha=hoy,
                                          labor=JornadaDeCuadrilla.CORRECTIVO)
    persona = PersonaDeCampo.objects.create(org=org, profile=user_profile, nombre="T")
    IntegranteDeJornada.objects.create(org=org, jornada=j, persona=persona, rol="tecnico")
    otra = OrdenTrabajo.objects.create(
        org=org, numero=4, tipo_trabajo_version=orden.tipo_trabajo_version, zona="X",
        estado_operativo=OrdenTrabajo.EN_SITIO)
    AsignacionTrabajo.objects.create(orden=otra, profile=user_profile, rol="tecnico",
                                     es_principal=True)

    filas = {f["numero"]: f for f in D.del_dia(org, hoy)["cuadrillas"][0]["ordenes"]}

    assert filas[3]["revision"]["veredicto"] == RC.CERRAR
    assert filas[3]["vuelta"] == 1, "la clave de la decision de la persona"
    assert filas[4]["revision"] is None


def test_v7_indica_no_decide(orden, user_profile):
    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    antes = (orden.estado_operativo, orden.estado_validacion, orden.revision)
    eventos = EventoTrabajo.objects.filter(orden=orden).count()

    assert RC.revisar(orden)["veredicto"] == RC.CERRAR

    orden.refresh_from_db()
    assert (orden.estado_operativo, orden.estado_validacion, orden.revision) == antes
    assert EventoTrabajo.objects.filter(orden=orden).count() == eventos


def test_v8_la_medicion_de_otra_empresa_no_cuenta(org, orden, user_profile, org_b):
    """Aunque una propuesta de OTRA empresa nombrara esta orden, su medicion no
    entra en la revision. Se crea con el contexto de esa empresa (RLS), como la
    escribiria su propio ciclo.

    Mide RLS y el filtro `org=` JUNTOS: con RLS activo la mutacion que quita el
    filtro sobrevive (medido el 30/10/2026), porque la fila ya no se ve. El
    filtro queda para los roles que saltan RLS (CLAUDE.md §5)."""
    from conftest import set_rls_context

    _foto(orden)
    _cierre(orden)
    _consumo(orden, user_profile)
    set_rls_context(org_b)
    PropuestaSupervisor.objects.create(
        org=org_b, origen_id="caso-ajeno", estado=PropuestaSupervisor.ACEPTADA,
        evidencia=[{"fuente": FUENTE, "orden": str(orden.id), "quedo_en_rango": False}])
    #  La prueba no puede pasar porque la fila no exista: existe.
    assert PropuestaSupervisor.objects.filter(org=org_b).count() == 1
    set_rls_context(org)

    r = RC.revisar(orden)
    assert ("medicion" not in _claves(r), r["veredicto"]) == (True, RC.CERRAR)
