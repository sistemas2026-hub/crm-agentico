# -*- coding: utf-8 -*-
"""
================================================================================
 P3  --  SITUACIONES OPERATIVAS: creer y saber son dos columnas distintas
================================================================================

LAS TRES PROPIEDADES QUE JUSTIFICAN EL BLOQUE
---------------------------------------------
  1. UNA anomalia es UNA situacion, aunque se vea diez veces. 12 ONT en el PON
     3/1/4 no son doce situaciones, y volver a verlas en el ciclo siguiente no
     crea otra.
  2. Una hipotesis NUNCA llega como hecho. Viaja en su campo, con su confianza
     al lado, y la base rechaza tener una sin la otra.
  3. Una señal que desaparece NO prueba que el problema se resolvio. Cerrar
     exige decir QUE se comprobo, y eso lo obliga un CheckConstraint.

COMO ESTA ORDENADO
------------------
    §1  crear, estados, transiciones invalidas
    §2  el timeline es append-only
    §3  afectados, insuficiencia, recuperacion
    §4  deteccion: hecho / relacion / interpretacion / riesgo / hipotesis
    §5  correlacion y agrupacion
    §6  deduplicacion
    §7  tickets: se asocian con evidencia, no por cercania
    §8  la señal que deja de verse, y la verificacion antes del cierre
    §9  fuente INCONCLUSA
    §10 multi-tenant
    §11 lo que NO hace
    §12 LA PRUEBA FUNCIONAL de cuatro ciclos

LO QUE SE SUSTITUYE
-------------------
Nada de la capa de situaciones. Se escriben capturas de fuente a mano --que es
lo que el sondeo dejaria-- y desde ahi todo es real: deteccion, correlacion,
modelos y Postgres.
================================================================================
"""

import json
from unittest import mock

import pytest
from django.db.utils import IntegrityError
from django.utils import timezone

from campo.models import OrdenTrabajo
from cases.models import Case
from common.models import Activity
from operaciones import correlacion, deteccion, fuentes, situaciones as svc
from operaciones.fuentes_modelos import EstadoLectura, Frescura, Fuente, FuenteEstado
from operaciones.models import ActividadOperativa, PropuestaSupervisor
from operaciones.situaciones_modelos import (Confianza, Riesgo,
                                             SituacionAfectado, SituacionEvento,
                                             SituacionOperativa,
                                             SituacionRelacion, TipoAfectado,
                                             TipoEvento, TipoRelacion)

S = SituacionOperativa
RUTA = "/api/operaciones/supervisor/sondeo/"


# =============================================================================
#  utilidades
# =============================================================================

def _captura(org, *, pons, ahora=None, estado=EstadoLectura.CON_DATOS,
             frescura=Frescura.FRESCA, dato_en=None):
    """
    Deja una captura de SmartOLT como la dejaria el sondeo.

    'pons' es {clave: {afectados, abonados, ...}} -- el mismo resumen que produce
    'fuentes_adaptadores._resumir_pons' a partir del sobre real del proveedor.
    """
    ahora = ahora or timezone.now()
    f, _ = FuenteEstado.objects.update_or_create(
        org=org, fuente=Fuente.SMARTOLT,
        defaults={"activa": True, "frecuencia_segundos": 300,
                  "antiguedad_maxima_segundos": 900,
                  "ventana_inconclusa_segundos": 0})
    lectura = fuentes.Lectura(
        estado, datos=pons, registros=len(pons),
        dato_en=dato_en if dato_en is not None else (ahora if pons else None),
        esquema="smartolt_pon_v1", tipo_consulta="outage_pons",
        error_tecnico="x" if estado == EstadoLectura.ERROR else "")
    snap = fuentes.registrar(f, lectura, inicio=ahora, ahora=ahora)
    if frescura != Frescura.FRESCA:
        #  La frescura se fuerza para poder probar el caso del dato viejo sin
        #  tener que esperar.
        snap.frescura = frescura
        snap.save(update_fields=["frescura"])
        f.frescura = frescura
        f.save(update_fields=["frescura"])
    return snap


def _pon(afectados, *, abonados=103, tipo="partial_los", porcentaje=None,
         caja="CTO 56"):
    fila = {"afectados": afectados, "abonados": abonados, "tipo": tipo,
            "caja": caja, "total_onus": abonados, "los": afectados}
    if porcentaje is not None:
        fila["porcentaje_afectado"] = porcentaje
    return fila


def _senal_pon(clave="3/1/4", afectados=12, **extra):
    """Una señal como la produce 'deteccion.desde_smartolt'."""
    datos = {clave: _pon(afectados, **extra)}
    snap = None
    return deteccion.Senal(
        fuente=Fuente.SMARTOLT,
        tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension=clave,
        hecho=f"{afectados} ONT afectadas en el PON {clave}",
        relacion=f"las {afectados} pertenecen al mismo puerto PON {clave}",
        interpretacion="hay concentracion topologica",
        riesgo=Riesgo.ALTO,
        hipotesis=f"posible falla optica en el PON {clave}",
        confianza=Confianza.MEDIA,
        recomendacion="verificar el PON",
        afectados=[{"tipo": TipoAfectado.PON, "identificador": clave,
                    "etiqueta": "CTO 56", "datos": {"afectados": afectados}},
                   {"tipo": TipoAfectado.OLT,
                    "identificador": clave.split("/")[0]}],
        evidencia=[{"fuente": Fuente.SMARTOLT, "dato": f"{afectados} ONT",
                    "observado_en": timezone.now().isoformat()}],
        observada_en=timezone.now())


def _situacion(org, **extra):
    ahora = timezone.now()
    datos = dict(org=org, codigo="S-900", tipo=S.AFECTACION_PON,
                 titulo="Posible afectación del PON 3/1/4",
                 descripcion="concentracion", estado=S.DETECTADA,
                 riesgo=Riesgo.MEDIO, huella="afectacion_pon|pon:3/1/4",
                 detectada_en=ahora, actualizada_en=ahora,
                 senal_vista_en=ahora, fuente_origen=Fuente.SMARTOLT)
    datos.update(extra)
    return S.objects.create(**datos)


# =============================================================================
#  §1  CREAR, ESTADOS, TRANSICIONES
# =============================================================================

def test_1_una_senal_abre_una_situacion(org_a):
    s = svc.abrir(org_a, _senal_pon())

    assert s.codigo == "S-001"
    assert s.estado == S.DETECTADA
    assert s.tipo == S.AFECTACION_PON
    assert s.huella == "afectacion_pon|pon:3/1/4"
    assert s.titulo == "Posible afectación del PON 3/1/4"
    assert s.viva is True


def test_2_una_situacion_puede_existir_SIN_TICKETS(org_a):
    #  Es el punto entero del Supervisor: la red se ve caida antes de que alguien
    #  reclame. 'tickets: 0' es un estado valido, no un error.
    s = svc.abrir(org_a, _senal_pon())

    casos = SituacionAfectado.objects.filter(situacion=s,
                                             tipo=TipoAfectado.CASO).count()
    assert casos == 0
    assert s.afectados_contados >= 1
    assert Case.objects.filter(org=org_a).count() == 0


def test_3_el_codigo_es_consecutivo_por_organizacion(org_a, org_b):
    from conftest import rls_org

    a1 = svc.abrir(org_a, _senal_pon("3/1/4"))
    a2 = svc.abrir(org_a, _senal_pon("3/1/5"))
    with rls_org(org_b):
        b1 = svc.abrir(org_b, _senal_pon("3/1/4"))

    assert (a1.codigo, a2.codigo) == ("S-001", "S-002")
    #  El consecutivo de una empresa NO depende de cuantas tuvo otra.
    assert b1.codigo == "S-001"


@pytest.mark.parametrize("desde,hasta,permitida", [
    (S.DETECTADA, S.INVESTIGANDO, True),
    (S.DETECTADA, S.DESCARTADA, True),
    #  Saltar de detectada a resuelta seria afirmar que se resolvio algo que
    #  nadie comprobo.
    (S.DETECTADA, S.RESUELTA, False),
    (S.DETECTADA, S.CERRADA, False),
    (S.INVESTIGANDO, S.CONFIRMADA, True),
    (S.CONFIRMADA, S.EN_ATENCION, True),
    (S.CONFIRMADA, S.RESUELTA, False),
    (S.EN_VERIFICACION, S.RESUELTA, True),
    #  La vuelta desde verificacion: si la señal reaparece, no se resolvio.
    (S.EN_VERIFICACION, S.CONFIRMADA, True),
    (S.RESUELTA, S.CERRADA, True),
    (S.RESUELTA, S.CONFIRMADA, True),
    #  Las terminales no salen a ningun lado.
    (S.CERRADA, S.INVESTIGANDO, False),
    (S.DESCARTADA, S.CONFIRMADA, False),
])
def test_4_las_transiciones_son_lista_blanca(org_a, desde, hasta, permitida):
    #  Las situaciones que llegaron legitimamente a RESUELTA o CERRADA tienen su
    #  verificacion: es lo que la base exige para estar ahi. Montarlas sin ella
    #  haria fallar el CheckConstraint por un motivo que no es el que esta prueba
    #  mide -- y de hecho fallo asi la primera vez, lo que confirma que la
    #  restriccion muerde incluso por el camino de 'cambiar_estado'.
    con_verificacion = desde in (S.RESUELTA, S.CERRADA) or hasta == S.CERRADA
    s = _situacion(
        org_a, estado=desde,
        verificacion="se comprobo en campo" if con_verificacion else "",
        verificada_en=timezone.now() if con_verificacion else None)

    if permitida:
        svc.cambiar_estado(s, hasta, motivo="motivo de prueba")
        s.refresh_from_db()
        assert s.estado == hasta
    else:
        with pytest.raises(svc.TransicionInvalida):
            svc.cambiar_estado(s, hasta, motivo="motivo de prueba")


def test_5_descartar_exige_motivo(org_a):
    s = _situacion(org_a)

    with pytest.raises(svc.ErrorSituacion):
        svc.cambiar_estado(s, S.DESCARTADA, motivo="   ")

    svc.cambiar_estado(s, S.DESCARTADA, motivo="era una prueba del proveedor")
    s.refresh_from_db()
    assert s.estado == S.DESCARTADA
    #  Sin motivo seria indistinguible de un borrado silencioso.
    assert "prueba del proveedor" in s.descripcion


def test_6_la_base_rechaza_una_hipotesis_sin_confianza(org_a):
    with pytest.raises(IntegrityError):
        _situacion(org_a, hipotesis="posible falla del PON",
                   confianza=Confianza.SIN_HIPOTESIS)


def test_7_la_base_rechaza_una_confianza_sin_hipotesis(org_a):
    #  La forma simetrica del mismo error: las dos presentan una sospecha como
    #  un hecho.
    with pytest.raises(IntegrityError):
        _situacion(org_a, hipotesis="", confianza=Confianza.ALTA)


# =============================================================================
#  §2  EL TIMELINE ES APPEND-ONLY
# =============================================================================

def test_8_abrir_deja_el_timeline_de_la_deteccion(org_a):
    s = svc.abrir(org_a, _senal_pon())

    tipos = list(s.eventos.values_list("tipo", flat=True))
    assert TipoEvento.DETECTADA in tipos
    #  La hipotesis es SU PROPIO evento, con su confianza: asi el timeline deja
    #  ver cuando se empezo a creer algo, aparte de cuando se vio el hecho.
    assert TipoEvento.HIPOTESIS in tipos
    assert TipoEvento.RECOMENDACION in tipos


def test_9_un_evento_no_se_puede_reescribir(org_a):
    s = svc.abrir(org_a, _senal_pon())
    evento = s.eventos.first()

    evento.resumen = "otra cosa"
    with pytest.raises(SituacionEvento.NoSeReescribe):
        evento.save()

    evento.refresh_from_db()
    assert evento.resumen != "otra cosa"


def test_10_un_evento_no_se_puede_borrar(org_a):
    s = svc.abrir(org_a, _senal_pon())
    evento = s.eventos.first()
    cuantos = s.eventos.count()

    with pytest.raises(SituacionEvento.NoSeReescribe):
        evento.delete()

    assert s.eventos.count() == cuantos


def test_11_el_timeline_distingue_cuando_paso_de_cuando_se_anoto(org_a):
    #  Un ciclo que procesa una captura de hace tres minutos no puede fechar el
    #  evento ahora: el timeline mentiria sobre el orden.
    hace_rato = timezone.now() - timezone.timedelta(minutes=3)
    s = _situacion(org_a)
    e = svc.anotar(s, TipoEvento.EVIDENCIA, "algo", ocurrido_en=hace_rato)

    assert e.ocurrido_en == hace_rato
    assert e.registrado_en > hace_rato


# =============================================================================
#  §3  AFECTADOS
# =============================================================================

def test_12_el_mismo_afectado_dos_veces_cuenta_UNA(org_a):
    s = _situacion(org_a)
    uno = [{"tipo": TipoAfectado.PON, "identificador": "3/1/4"}]

    svc.agregar_afectados(s, uno)
    r = svc.agregar_afectados(s, uno)

    assert r["nuevos"] == 0 and r["vistos"] == 1
    assert SituacionAfectado.objects.filter(situacion=s).count() == 1
    s.refresh_from_db()
    assert s.afectados_contados == 1


def test_12b_el_contador_se_RECALCULA_no_se_incrementa(org_a):
    """
    El contador sale de contar las filas vivas, nunca de sumarle al valor leido.

    POR QUE HACE FALTA ESTA PRUEBA APARTE (medido el 02/10/2026)
    ----------------------------------------------------------
    La mutacion que cambia el recalculo por 'contador + nuevos' SOBREVIVIO a
    test_12: con el mismo afectado dos veces, incrementar en 0 y recontar dan 1
    las dos veces. El caso que las separa es un afectado que se recupera y VUELVE:
    ahi 'nuevos' es 0 --la fila ya existia-- pero el total vivo subio de 0 a 1.
    Con el incremento el contador se queda en 0 y la situacion dice que no hay
    nadie afectado teniendo uno.
    """
    s = _situacion(org_a)
    uno = [{"tipo": TipoAfectado.PON, "identificador": "3/1/4"}]
    svc.agregar_afectados(s, uno)
    svc.marcar_recuperados(s, [], tipo=TipoAfectado.PON)
    s.refresh_from_db()
    assert s.afectados_contados == 0

    #  Vuelve a caer: la fila ya existe, asi que 'nuevos' es 0.
    r = svc.agregar_afectados(s, uno)
    s.refresh_from_db()

    assert r["nuevos"] == 0, "la fila ya existia"
    assert s.afectados_contados == 1, (
        "volver a verlo lo desmarca como recuperado, asi que vuelve a contar")


def test_13_la_base_impide_el_afectado_duplicado(org_a):
    s = _situacion(org_a)
    ahora = timezone.now()
    SituacionAfectado.objects.create(
        situacion=s, org=org_a, tipo=TipoAfectado.PON, identificador="3/1/4",
        detectado_en=ahora, visto_en=ahora)

    with pytest.raises(IntegrityError):
        SituacionAfectado.objects.create(
            situacion=s, org=org_a, tipo=TipoAfectado.PON,
            identificador="3/1/4", detectado_en=ahora, visto_en=ahora)


def test_14_un_afectado_sin_identificador_se_rechaza(org_a):
    s = _situacion(org_a)

    with pytest.raises(svc.ErrorSituacion):
        svc.agregar_afectados(s, [{"tipo": TipoAfectado.PON,
                                   "identificador": ""}])


def test_15_la_insuficiencia_se_REGISTRA_en_vez_de_inventarse(org_a):
    #  'get_outage_pons' agrupa y no devuelve los seriales de cada ONT. Se anota
    #  que hay 12 sin identificar, en vez de dejar la insuficiencia fuera -- una
    #  lista vacia se leeria como "nada afectado".
    snap = _captura(org_a, pons={"3/1/4": _pon(12)})
    senales = deteccion.desde_smartolt(snap, timezone.now())
    s = svc.abrir(org_a, senales[0])

    insuf = SituacionAfectado.objects.get(
        situacion=s, tipo=TipoAfectado.DATOS_INSUFICIENTES)
    assert insuf.datos["cuantas"] == 12
    assert "no devuelve los seriales" in insuf.datos["porque"]


def test_16_detectado_en_no_se_reescribe_en_cada_ciclo(org_a):
    s = _situacion(org_a)
    ayer = timezone.now() - timezone.timedelta(days=1)
    uno = [{"tipo": TipoAfectado.PON, "identificador": "3/1/4"}]
    svc.agregar_afectados(s, uno, ahora=ayer)

    svc.agregar_afectados(s, uno, ahora=timezone.now())

    fila = SituacionAfectado.objects.get(situacion=s, tipo=TipoAfectado.PON)
    #  Si cada ciclo reescribiera la deteccion, la situacion perderia desde
    #  cuando esta afectado ese recurso.
    assert fila.detectado_en == ayer
    assert fila.visto_en > ayer


def test_17_un_afectado_que_vuelve_se_marca_no_se_borra(org_a):
    s = _situacion(org_a)
    svc.agregar_afectados(s, [{"tipo": TipoAfectado.PON, "identificador": "3/1/4"},
                              {"tipo": TipoAfectado.PON, "identificador": "3/1/5"}])

    svc.marcar_recuperados(s, ["3/1/4"], tipo=TipoAfectado.PON)

    #  La fila sigue: borrarla perderia que estuvo caida, y con eso la evolucion.
    assert SituacionAfectado.objects.filter(situacion=s,
                                            tipo=TipoAfectado.PON).count() == 2
    recuperado = SituacionAfectado.objects.get(situacion=s, identificador="3/1/5")
    assert recuperado.recuperado_en is not None
    s.refresh_from_db()
    assert s.afectados_contados == 1


# =============================================================================
#  §4  DETECCION: creer y saber, separados
# =============================================================================

def test_18_la_senal_separa_hecho_de_hipotesis(org_a):
    snap = _captura(org_a, pons={"3/1/4": _pon(12, porcentaje=11.6)})

    senales = deteccion.desde_smartolt(snap, timezone.now())

    assert len(senales) == 1
    s = senales[0]
    #  HECHO: lo que la fuente dijo.
    assert "12 ONT afectadas en el PON 3/1/4" in s.hecho
    assert "103 abonados" in s.hecho
    #  RELACION: por que estan juntas.
    assert "mismo puerto PON 3/1/4" in s.relacion
    #  INTERPRETACION: que se lee de eso.
    assert "concentracion topologica" in s.interpretacion
    #  HIPOTESIS: lo que PODRIA ser, con su confianza, y en su propio campo.
    assert s.hipotesis.startswith("posible")
    assert s.confianza in (Confianza.BAJA, Confianza.MEDIA)
    #  Y el hecho NO contiene la hipotesis: si estuvieran en la misma frase nadie
    #  distinguiria cual se midio.
    assert "posible" not in s.hecho
    assert s.recomendacion


def test_19_un_solo_afectado_NO_produce_hipotesis(org_a):
    #  Decir "posible falla del PON" por una ONT caida convertiria una sospecha
    #  debil en una afirmacion.
    snap = _captura(org_a, pons={"3/1/4": _pon(1)})

    s = deteccion.desde_smartolt(snap, timezone.now())[0]

    assert s.hipotesis == ""
    assert s.confianza == Confianza.SIN_HIPOTESIS
    assert "no hay concentracion" in s.interpretacion


def test_20_la_hipotesis_depende_del_TIPO_de_alerta(org_a):
    #  'power' es un corte de energia y 'los' es perdida optica. Darles la misma
    #  hipotesis mandaria a revisar la fibra cuando se fue la luz.
    luz = deteccion.desde_smartolt(
        _captura(org_a, pons={"3/1/4": _pon(12, tipo="power")}),
        timezone.now())[0]
    fibra = deteccion.desde_smartolt(
        _captura(org_a, pons={"3/1/9": _pon(12, tipo="los")}),
        timezone.now())[0]

    assert "energia" in luz.hipotesis
    assert "optica" in fibra.hipotesis


def test_21_una_senal_no_puede_tener_hipotesis_sin_confianza():
    with pytest.raises(ValueError):
        deteccion.Senal(fuente=Fuente.SMARTOLT, tipo_situacion=S.OTRA,
                        dimension="pon", clave_dimension="x", hecho="h",
                        hipotesis="algo", confianza=Confianza.SIN_HIPOTESIS)
    with pytest.raises(ValueError):
        deteccion.Senal(fuente=Fuente.SMARTOLT, tipo_situacion=S.OTRA,
                        dimension="pon", clave_dimension="x", hecho="h",
                        hipotesis="", confianza=Confianza.ALTA)


def test_22_el_riesgo_sube_con_el_porcentaje(org_a):
    bajo = deteccion.desde_smartolt(
        _captura(org_a, pons={"3/1/4": _pon(3, abonados=100, porcentaje=3.0)}),
        timezone.now())[0]
    alto = deteccion.desde_smartolt(
        _captura(org_a, pons={"3/1/5": _pon(60, abonados=100, porcentaje=60.0)}),
        timezone.now())[0]

    assert Riesgo.ORDEN[alto.riesgo] > Riesgo.ORDEN[bajo.riesgo]
    assert alto.riesgo == Riesgo.CRITICO


def test_23_una_fuente_en_ERROR_no_produce_senales(org_a):
    #  Emitir una señal "sin afectados" afirmaria que la red esta sana justo
    #  cuando no se la pudo mirar.
    snap = _captura(org_a, pons={}, estado=EstadoLectura.ERROR)

    assert deteccion.desde_smartolt(snap, timezone.now()) == []


def test_23b_una_captura_en_ERROR_CON_DATOS_tampoco_se_interpreta(org_a):
    """
    El caso peligroso de verdad: la lectura fallo Y hay datos de antes.

    POR QUE ESTA PRUEBA EXISTE APARTE (medido el 02/10/2026)
    ------------------------------------------------------
    La mutacion que quita la guarda de ERROR en 'desde_smartolt' SOBREVIVIO a
    test_23: esa prueba usa una captura en ERROR con 'datos' vacios, asi que el
    bucle no encontraba nada que recorrer y devolvia [] por casualidad, no porque
    la guarda mordiera.

    Interpretar datos de una lectura que fallo es exactamente como un tablero
    termina mostrando una caida que ya se resolvio -- o peor, afirmando que la red
    esta sana con una foto que no se pudo tomar.
    """
    snap = _captura(org_a, pons={}, estado=EstadoLectura.ERROR)
    #  Se le ponen datos a mano: es lo que pasaria si un adaptador los dejara.
    snap.datos = {"3/1/4": _pon(12)}
    snap.save(update_fields=["datos"])

    assert deteccion.desde_smartolt(snap, timezone.now()) == [], (
        "una lectura que fallo no se interpreta, ni con datos al lado")


def test_23c_una_fuente_NO_DISPONIBLE_con_datos_tampoco(org_a):
    snap = _captura(org_a, pons={}, estado=EstadoLectura.ERROR)
    snap.estado = EstadoLectura.NO_DISPONIBLE
    snap.error_tecnico = ""
    snap.datos = {"3/1/4": _pon(12)}
    snap.save(update_fields=["estado", "error_tecnico", "datos"])

    assert deteccion.desde_smartolt(snap, timezone.now()) == []


def test_24_un_dato_VIEJO_produce_senal_no_concluyente(org_a):
    snap = _captura(org_a, pons={"3/1/4": _pon(12)}, frescura=Frescura.VIEJA)

    s = deteccion.desde_smartolt(snap, timezone.now())[0]

    #  La señal viaja para quedar registrada, pero marcada: una foto vieja
    #  describe el pasado.
    assert s.concluyente is False


# =============================================================================
#  §5 y §6  CORRELACION, AGRUPACION, DEDUPLICACION
# =============================================================================

def test_24b_una_senal_NO_concluyente_no_adelanta_la_ultima_vista(org_a):
    """
    Una captura VIEJA actualiza la situacion, pero NO dice que la vimos ahora.

    POR QUE IMPORTA, Y POR QUE NO HABIA PRUEBA (medido el 02/10/2026)
    ---------------------------------------------------------------
    'senal_vista_en' es lo que decide si una situacion pasa a verificacion por
    falta de señal. Si una captura vieja lo adelantara, una situacion cuya señal
    desaparecio hace una hora pareceria vigente para siempre -- y nadie iria a
    comprobar si se resolvio.

    La mutacion que cambia 'if senal.concluyente' por 'if True' SOBREVIVIO a todas
    las pruebas: la del camino inconcluso va por otra funcion, y no habia ninguna
    del camino de 'actualizar' con una captura vieja.
    """
    t0 = timezone.now() - timezone.timedelta(hours=1)
    s = _situacion(org_a, estado=S.CONFIRMADA, senal_vista_en=t0)
    vista_antes = s.senal_vista_en

    vieja = _senal_pon("3/1/4", 12)
    vieja.concluyente = False
    svc.actualizar(s, vieja, ahora=timezone.now())

    s.refresh_from_db()
    #  La situacion se actualizo --el afectado esta-- pero la ultima vez que se
    #  VIO la señal no se movio.
    assert s.senal_vista_en == vista_antes
    assert s.afectados_contados >= 1
    #  Y por eso sigue siendo candidata a verificacion.
    assert correlacion.revisar_sin_senal(org_a)["a_verificacion"] == 1


def test_25_doce_ONT_del_mismo_PON_son_UNA_situacion(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})

    informe = correlacion.correr(org_a)

    assert informe["creadas"] == 1
    assert S.objects.filter(org=org_a).count() == 1
    s = S.objects.get(org=org_a)
    assert s.tipo == S.AFECTACION_PON


def test_26_el_segundo_ciclo_ACTUALIZA_no_crea(org_a):
    ahora = timezone.now()
    _captura(org_a, pons={"3/1/4": _pon(12)}, ahora=ahora)
    correlacion.correr(org_a, ahora=ahora)

    luego = ahora + timezone.timedelta(minutes=5)
    _captura(org_a, pons={"3/1/4": _pon(15)}, ahora=luego)
    informe = correlacion.correr(org_a, ahora=luego)

    assert informe["creadas"] == 0
    assert informe["actualizadas"] == 1
    assert S.objects.filter(org=org_a).count() == 1


def test_27_dos_PONs_distintos_son_dos_situaciones(org_a):
    #  La agrupacion es por PON: dos puertos distintos son dos problemas hasta
    #  que algo demuestre lo contrario.
    _captura(org_a, pons={"3/1/4": _pon(12), "3/2/7": _pon(5)})

    informe = correlacion.correr(org_a)

    assert informe["creadas"] == 2


def test_28_dos_PONs_de_la_misma_OLT_se_RELACIONAN_no_se_funden(org_a):
    #  Fundirlos afirmaria que la OLT es la causa; dejarlos sueltos esconderia
    #  que estan juntos. Una relacion 'coincide' dice lo que se midio.
    _captura(org_a, pons={"3/1/4": _pon(12), "3/2/7": _pon(8)})

    informe = correlacion.correr(org_a)

    assert informe["creadas"] == 2
    assert informe["relaciones"] >= 1
    rel = SituacionRelacion.objects.filter(org=org_a).first()
    assert rel.tipo == TipoRelacion.COINCIDE
    assert "OLT 3" in rel.motivo


def test_29_la_correlacion_NO_puede_afirmar_causa(org_a):
    a = svc.abrir(org_a, _senal_pon("3/1/4"))
    b = svc.abrir(org_a, _senal_pon("3/2/7"))

    #  'explica' es una afirmacion de causalidad: la pone una persona.
    with pytest.raises(svc.ErrorSituacion):
        svc.relacionar(a, b, TipoRelacion.EXPLICA, "parecen relacionadas")


def test_30_una_relacion_necesita_motivo(org_a):
    a = svc.abrir(org_a, _senal_pon("3/1/4"))
    b = svc.abrir(org_a, _senal_pon("3/2/7"))

    with pytest.raises(svc.ErrorSituacion):
        svc.relacionar(a, b, TipoRelacion.COINCIDE, "  ")


def test_31_la_base_impide_dos_situaciones_VIVAS_con_la_misma_huella(org_a):
    _situacion(org_a, codigo="S-001", huella="afectacion_pon|pon:3/1/4")

    with pytest.raises(IntegrityError):
        _situacion(org_a, codigo="S-002", huella="afectacion_pon|pon:3/1/4")


def test_32_una_situacion_CERRADA_libera_la_huella(org_a):
    #  Cuando el PON se cae otra vez el mes que viene, eso es una situacion
    #  NUEVA. Un indice total lo impediria para siempre.
    vieja = _situacion(org_a, codigo="S-001")
    svc.verificar(vieja, "se reemplazo el splitter y volvieron las 12")
    svc.cambiar_estado(vieja, S.EN_VERIFICACION)
    svc.cerrar(vieja)

    nueva = _situacion(org_a, codigo="S-002")

    assert nueva.pk != vieja.pk
    assert S.objects.filter(org=org_a, huella=vieja.huella).count() == 2


def test_33_el_mismo_ciclo_corrido_dos_veces_no_duplica(org_a):
    ahora = timezone.now()
    _captura(org_a, pons={"3/1/4": _pon(12)}, ahora=ahora)

    correlacion.correr(org_a, ahora=ahora)
    correlacion.correr(org_a, ahora=ahora)

    assert S.objects.filter(org=org_a).count() == 1
    s = S.objects.get(org=org_a)
    #  Y el conteo no se duplico: 12 vistos dos veces siguen siendo 12.
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.PON).count() == 1


# =============================================================================
#  §7  TICKETS
# =============================================================================

def _caso(org, *, pon=None, **extra):
    datos = dict(org=org, name="Sin internet", status="New", priority="Normal")
    datos.update(extra)
    caso = Case.objects.create(**datos)
    if pon is not None:
        Case.objects.filter(pk=caso.pk).update(custom_fields={"pon": pon})
        caso.refresh_from_db()
    return caso


def test_34_un_ticket_posterior_se_asocia_a_la_situacion(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)
    s = S.objects.get(org=org_a)

    _caso(org_a, pon="3/1/4")
    r = correlacion.asociar_tickets(org_a)

    assert r["asociados"] == 1
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.CASO).count() == 1
    #  Y NO se creo otra situacion.
    assert S.objects.filter(org=org_a).count() == 1


def test_35_un_ticket_de_otro_PON_NO_se_asocia(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)
    s = S.objects.get(org=org_a)

    _caso(org_a, pon="9/9/9")
    r = correlacion.asociar_tickets(org_a)

    assert r["asociados"] == 0
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.CASO).count() == 0


def test_36_un_ticket_SIN_el_dato_de_PON_no_se_asocia_por_cercania(org_a):
    #  LA DECISION MAS IMPORTANTE DE ESA FUNCION: un caso abierto a la misma hora
    #  puede ser una consulta de facturacion. Asociarlo porque coincide el reloj
    #  inflaria la situacion con casos ajenos.
    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)

    _caso(org_a)  # sin PON
    r = correlacion.asociar_tickets(org_a)

    assert r["asociados"] == 0
    assert r["sin_datos"] == 1


def test_37_asociar_un_ticket_NO_toca_el_caso(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)
    caso = _caso(org_a, pon="3/1/4")
    antes = (caso.status, caso.resolved_at, caso.updated_at)

    correlacion.asociar_tickets(org_a)

    caso.refresh_from_db()
    #  Ni el estado, ni la resolucion, ni 'updated_at': la unica escritura es una
    #  fila de afectado en la situacion.
    assert (caso.status, caso.resolved_at, caso.updated_at) == antes


def test_38_asociar_dos_veces_el_mismo_ticket_cuenta_una(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)
    _caso(org_a, pon="3/1/4")

    primero = correlacion.asociar_tickets(org_a)
    segundo = correlacion.asociar_tickets(org_a)

    assert primero["asociados"] == 1
    assert segundo["asociados"] == 0
    s = S.objects.get(org=org_a)
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.CASO).count() == 1


def test_39_el_afectado_de_tipo_caso_no_lleva_datos_de_cliente(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)
    _caso(org_a, pon="3/1/4", name="Sofia Munoz sin internet")

    correlacion.asociar_tickets(org_a)

    fila = SituacionAfectado.objects.get(situacion=S.objects.get(org=org_a),
                                         tipo=TipoAfectado.CASO)
    plano = json.dumps({"etiqueta": fila.etiqueta, "datos": fila.datos})
    assert "Sofia" not in plano


# =============================================================================
#  §8  LA SEÑAL QUE DEJA DE VERSE, Y LA VERIFICACION
# =============================================================================

def test_40_una_senal_ausente_pasa_a_VERIFICACION_no_a_cerrada(org_a):
    hace_mucho = timezone.now() - timezone.timedelta(hours=2)
    s = _situacion(org_a, estado=S.CONFIRMADA, senal_vista_en=hace_mucho)

    r = correlacion.revisar_sin_senal(org_a)

    s.refresh_from_db()
    assert r["a_verificacion"] == 1
    assert s.estado == S.EN_VERIFICACION
    assert s.estado != S.CERRADA
    tipos = list(s.eventos.values_list("tipo", flat=True))
    assert TipoEvento.SENAL_AUSENTE in tipos


def test_41_una_situacion_con_senal_reciente_no_se_toca(org_a):
    s = _situacion(org_a, estado=S.CONFIRMADA, senal_vista_en=timezone.now())

    r = correlacion.revisar_sin_senal(org_a)

    s.refresh_from_db()
    assert r["a_verificacion"] == 0
    assert s.estado == S.CONFIRMADA


def test_42_no_se_puede_cerrar_sin_verificacion(org_a):
    s = _situacion(org_a, estado=S.EN_VERIFICACION)

    with pytest.raises(svc.ErrorSituacion):
        svc.cerrar(s)

    s.refresh_from_db()
    assert s.estado == S.EN_VERIFICACION


def test_43_la_BASE_rechaza_una_cerrada_sin_verificacion(org_a):
    #  No depende de que el servicio se acuerde: el CheckConstraint lo impide
    #  aunque alguien escriba un camino nuevo.
    s = _situacion(org_a, estado=S.EN_VERIFICACION)

    with pytest.raises(IntegrityError):
        S.objects.filter(pk=s.pk).update(estado=S.CERRADA)


def test_44_verificar_exige_decir_QUE_se_comprobo(org_a):
    s = _situacion(org_a)

    with pytest.raises(svc.ErrorSituacion):
        svc.verificar(s, "   ")


def test_45_el_cierre_pasa_por_resuelta(org_a):
    s = _situacion(org_a, estado=S.EN_VERIFICACION)
    svc.verificar(s, "se midio el PON: las 12 ONT volvieron en linea")

    svc.cerrar(s)

    s.refresh_from_db()
    assert s.estado == S.CERRADA
    assert s.cerrada_en is not None
    estados = [e.datos.get("ahora") for e in s.eventos.filter(
        tipo=TipoEvento.CAMBIO_ESTADO)]
    #  El camino quedo escrito: verificacion -> resuelta -> cerrada.
    assert S.RESUELTA in estados and S.CERRADA in estados


def test_46_una_senal_que_vuelve_reabre_desde_verificacion(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, estado=S.EN_VERIFICACION, senal_vista_en=ahora,
                   huella="afectacion_pon|pon:3/1/4")
    _captura(org_a, pons={"3/1/4": _pon(12)}, ahora=ahora)

    informe = correlacion.correr(org_a, ahora=ahora)

    s.refresh_from_db()
    #  No se creo otra: la que estaba en verificacion se actualizo.
    assert informe["creadas"] == 0
    assert S.objects.filter(org=org_a).count() == 1
    assert s.estado == S.EN_VERIFICACION


# =============================================================================
#  §9  FUENTE INCONCLUSA
# =============================================================================

def test_47_una_fuente_inconclusa_NO_produce_red_sana(org_a):
    ahora = timezone.now()
    s = _situacion(org_a, estado=S.CONFIRMADA, senal_vista_en=ahora)
    vista_antes = s.senal_vista_en

    _captura(org_a, pons={}, estado=EstadoLectura.INCONCLUSA,
             ahora=ahora + timezone.timedelta(minutes=5))
    correlacion.correr(org_a, ahora=ahora + timezone.timedelta(minutes=5))

    s.refresh_from_db()
    #  Sigue viva, NO paso a verificacion, y su 'senal_vista_en' NO avanzo.
    assert s.estado == S.CONFIRMADA
    assert s.senal_vista_en == vista_antes
    tipos = list(s.eventos.values_list("tipo", flat=True))
    assert TipoEvento.INCONCLUSA in tipos


def test_48_una_inconclusa_no_abre_ninguna_situacion(org_a):
    _captura(org_a, pons={}, estado=EstadoLectura.INCONCLUSA)

    informe = correlacion.correr(org_a)

    assert informe["creadas"] == 0
    assert informe["inconclusas"] == 1
    assert S.objects.filter(org=org_a).count() == 0


# =============================================================================
#  §10  MULTI-TENANT
# =============================================================================

def test_49_una_situacion_de_A_no_se_ve_desde_B(org_a, org_b):
    from conftest import rls_org

    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)

    with rls_org(org_b):
        assert S.objects.filter(org=org_b).count() == 0
        correlacion.correr(org_b)
        assert S.objects.filter(org=org_b).count() == 0


def test_50_la_misma_huella_en_dos_organizaciones_son_dos_situaciones(org_a,
                                                                     org_b):
    from conftest import rls_org

    a = svc.abrir(org_a, _senal_pon("3/1/4"))
    with rls_org(org_b):
        b = svc.abrir(org_b, _senal_pon("3/1/4"))

    #  La unicidad es por organizacion: el PON 3/1/4 de una empresa no tiene
    #  nada que ver con el de otra.
    assert a.huella == b.huella
    assert a.pk != b.pk


def test_51_no_se_relacionan_situaciones_de_organizaciones_distintas(org_a,
                                                                    org_b):
    from conftest import rls_org

    a = svc.abrir(org_a, _senal_pon("3/1/4"))
    with rls_org(org_b):
        b = svc.abrir(org_b, _senal_pon("3/2/7"))

    with pytest.raises(svc.ErrorSituacion):
        svc.relacionar(a, b, TipoRelacion.COINCIDE, "misma OLT")


def test_52_un_ticket_de_B_no_se_asocia_a_una_situacion_de_A(org_a, org_b):
    from conftest import rls_org

    _captura(org_a, pons={"3/1/4": _pon(12)})
    correlacion.correr(org_a)
    with rls_org(org_b):
        _caso(org_b, pon="3/1/4")

    r = correlacion.asociar_tickets(org_a)

    assert r["asociados"] == 0


def test_53_el_timeline_y_los_afectados_llevan_su_organizacion(org_a):
    s = svc.abrir(org_a, _senal_pon())

    assert all(e.org_id == org_a.id for e in s.eventos.all())
    assert all(a.org_id == org_a.id for a in s.afectados.all())


# =============================================================================
#  §11  LO QUE NO HACE
# =============================================================================

def test_54_el_ciclo_no_crea_propuestas_ni_actividad(org_a):
    _captura(org_a, pons={"3/1/4": _pon(12)})
    _caso(org_a, pon="3/1/4")
    antes = (PropuestaSupervisor.objects.count(), Activity.objects.count(),
             ActividadOperativa.objects.count(), OrdenTrabajo.objects.count(),
             Case.objects.count())

    correlacion.correr(org_a)
    correlacion.correr(org_a)

    assert (PropuestaSupervisor.objects.count(), Activity.objects.count(),
            ActividadOperativa.objects.count(), OrdenTrabajo.objects.count(),
            Case.objects.count()) == antes


def test_55_una_situacion_es_independiente_de_PropuestaSupervisor(org_a):
    #  Son dos entidades y las dos siguen existiendo. Una propuesta no reemplaza
    #  ni cierra una situacion.
    s = svc.abrir(org_a, _senal_pon())

    assert PropuestaSupervisor.objects.filter(org=org_a).count() == 0
    assert s.viva is True
    #  Y nada en el modelo de situacion apunta a una propuesta.
    campos = {f.name for f in S._meta.get_fields()}
    assert not any("propuesta" in c for c in campos)


def test_56_los_modulos_no_ejecutan_nada_externo(org_a):
    import ast
    import inspect

    #  Se afirma sobre el AST --no sobre el texto-- porque los comentarios de
    #  estos modulos explican justamente que NO ejecutan nada, y una busqueda por
    #  palabra se pondria en rojo por la explicacion.
    PROHIBIDOS = {"interruptor", "frontera", "requests", "post", "put", "patch",
                  "delete", "correr_ciclo", "registrar_propuesta"}
    for modulo in (svc, deteccion, correlacion):
        arbol = ast.parse(inspect.getsource(modulo))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol)
                    if isinstance(n, ast.Attribute)}
        colados = nombres & PROHIBIDOS
        assert not colados, (modulo.__name__, sorted(colados))


def test_57_la_ruta_del_sondeo_devuelve_el_informe_de_situaciones(
        org_a, admin_client, admin_profile):
    _captura(org_a, pons={"3/1/4": _pon(12)})

    cuerpo = admin_client.post(RUTA).json()

    assert "situaciones" in cuerpo
    assert cuerpo["situaciones"]["vivas"] >= 1


# =============================================================================
#  §12  LA PRUEBA FUNCIONAL  --  los cuatro ciclos del bloque
# =============================================================================

def test_58_funcional_12_ONT_una_situacion_15_ONT_cuatro_tickets(org_a):
    """
    El escenario literal del bloque, ciclo por ciclo.

        02:15  12 ONT en el PON 3/1/4   -> 1 situacion, 0 tickets
        02:20  15 ONT                   -> la MISMA, 15 afectados
        02:25  4 tickets relacionados   -> asociados, SIN crear otra situacion
        03:30  la anomalia baja a 0     -> EN_VERIFICACION, NO cerrada
    """
    t0 = timezone.now().replace(microsecond=0)

    # ----- CICLO 1 --------------------------------------------------------
    _captura(org_a, pons={"3/1/4": _pon(12, porcentaje=11.6)}, ahora=t0)
    c1 = correlacion.correr(org_a, ahora=t0)

    assert c1["creadas"] == 1, "12 ONT del mismo PON son UNA situacion"
    s = S.objects.get(org=org_a)
    assert s.codigo == "S-001"
    assert s.estado == S.DETECTADA
    assert "PON 3/1/4" in s.titulo
    assert s.afectados_contados >= 1
    #  Tickets: 0, y es un estado valido.
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.CASO).count() == 0
    #  El HECHO dice 12; la hipotesis va aparte.
    detectada = s.eventos.get(tipo=TipoEvento.DETECTADA)
    assert "12 ONT" in detectada.resumen
    assert s.hipotesis and s.confianza != Confianza.SIN_HIPOTESIS

    # ----- CICLO 2:  15 ONT, la MISMA situacion ---------------------------
    t1 = t0 + timezone.timedelta(minutes=5)
    _captura(org_a, pons={"3/1/4": _pon(15, porcentaje=14.5)}, ahora=t1)
    c2 = correlacion.correr(org_a, ahora=t1)

    assert c2["creadas"] == 0, "no se crea otra situacion"
    assert c2["actualizadas"] == 1
    assert S.objects.filter(org=org_a).count() == 1
    s.refresh_from_db()
    #  La señal se repitio: pasa de detectada a investigando.
    assert s.estado == S.INVESTIGANDO
    afectado_pon = SituacionAfectado.objects.get(situacion=s,
                                                 tipo=TipoAfectado.PON)
    assert afectado_pon.datos["afectados"] == 15
    insuf = SituacionAfectado.objects.get(
        situacion=s, tipo=TipoAfectado.DATOS_INSUFICIENTES)
    assert insuf.datos["cuantas"] == 15
    assert s.eventos.filter(tipo=TipoEvento.ACTUALIZADA).exists()

    # ----- CICLO 3:  aparecen 4 tickets -----------------------------------
    t2 = t1 + timezone.timedelta(minutes=5)
    for _ in range(4):
        _caso(org_a, pon="3/1/4")
    #  Y uno que NO tiene nada que ver, para que la asociacion no sea por reloj.
    _caso(org_a, pon="9/9/9")
    _captura(org_a, pons={"3/1/4": _pon(15, porcentaje=14.5)}, ahora=t2)
    c3 = correlacion.correr(org_a, ahora=t2)

    assert c3["creadas"] == 0, "los tickets NO crean una situacion nueva"
    assert S.objects.filter(org=org_a).count() == 1
    assert c3["tickets"]["asociados"] == 4
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.CASO).count() == 4
    assert s.eventos.filter(tipo=TipoEvento.TICKET_ASOCIADO).count() == 4

    # ----- CICLO 4:  la anomalia desaparece -------------------------------
    #  Mas de 'MINUTOS_SIN_SENAL_PARA_VERIFICAR' despues: la señal no se ve.
    t3 = t2 + timezone.timedelta(
        minutes=correlacion.MINUTOS_SIN_SENAL_PARA_VERIFICAR + 10)
    _captura(org_a, pons={}, ahora=t3)
    c4 = correlacion.correr(org_a, ahora=t3)

    s.refresh_from_db()
    assert c4["a_verificacion"] == 1
    assert s.estado == S.EN_VERIFICACION, "a verificacion, NO a cerrada"
    assert s.estado != S.CERRADA
    assert s.cerrada_en is None
    #  Y cerrarla todavia exige que alguien diga QUE comprobo.
    with pytest.raises(svc.ErrorSituacion):
        svc.cerrar(s)

    # ----- el cierre, con verificacion ------------------------------------
    svc.verificar(s, "se midio el PON 3/1/4: las 15 ONT volvieron en linea")
    svc.cerrar(s)
    s.refresh_from_db()
    assert s.estado == S.CERRADA

    #  Y el timeline completo quedo, sin un solo evento reescrito.
    tipos = list(s.eventos.order_by("ocurrido_en", "registrado_en")
                 .values_list("tipo", flat=True))
    for esperado in (TipoEvento.DETECTADA, TipoEvento.HIPOTESIS,
                     TipoEvento.ACTUALIZADA, TipoEvento.TICKET_ASOCIADO,
                     TipoEvento.SENAL_AUSENTE, TipoEvento.CAMBIO_ESTADO,
                     TipoEvento.VERIFICACION, TipoEvento.CIERRE):
        assert esperado in tipos, esperado
