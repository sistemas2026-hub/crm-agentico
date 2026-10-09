# -*- coding: utf-8 -*-
"""
================================================================================
 SITUACIONES EN CARRERA  --  dos ciclos juntos no producen dos situaciones
================================================================================

POR QUE ESTA EN UN ARCHIVO APARTE
---------------------------------
Necesita 'transaction=True' --sin eso los hilos no ven lo que escribe el otro-- y
una prueba asi no convive con el resto en el mismo proceso de pytest: pytest-django
hace flush y reemite 'post_migrate' despues de cada una, y con varias en la misma
corrida el re-alta de permisos choca. Ya paso en el bloque anterior: una prueba de
este tipo dentro del archivo principal tumbo CUATRO pruebas ajenas que venian en
verde. La convencion '*_concurrencia_postgres.py' del repo existe por esto.

QUE SE MIDE, Y POR QUE NO ALCANZA CON 'BUSCAR ANTES DE INSERTAR'
---------------------------------------------------------------
Entre el 'select' que busca la situacion viva y el 'insert' que la crea hay una
ventana. Dos turnos del scheduler pueden caer justo ahi -- y entonces el patron
"busco y si no esta la creo" produce DOS situaciones para la misma anomalia, que
es exactamente el duplicado que el bloque prohibe.

Lo que lo impide de verdad es el indice unico PARCIAL de la base sobre
(org, huella) limitado a los estados vivos. Estas pruebas lo ejercitan con hilos
de verdad contra Postgres de verdad: no hay forma de medirlo con la base en
memoria ni con la transaccion de la prueba abierta.
================================================================================
"""

import threading

import pytest
from django.utils import timezone

from operaciones import correlacion, fuentes, situaciones as svc
from operaciones.fuentes_modelos import EstadoLectura, Fuente, FuenteEstado
from operaciones.situaciones_modelos import (Confianza, Riesgo,
                                             SituacionAfectado,
                                             SituacionOperativa, TipoAfectado)
from operaciones.deteccion import Senal

S = SituacionOperativa


def _senal(clave="3/1/4", afectados=12):
    return Senal(
        fuente=Fuente.SMARTOLT, tipo_situacion=S.AFECTACION_PON,
        dimension="pon", clave_dimension=clave,
        hecho=f"{afectados} ONT afectadas en el PON {clave}",
        relacion="mismo puerto", interpretacion="concentracion",
        riesgo=Riesgo.ALTO, hipotesis="posible falla optica",
        confianza=Confianza.MEDIA, recomendacion="verificar",
        afectados=[{"tipo": TipoAfectado.PON, "identificador": clave,
                    "datos": {"afectados": afectados}}],
        evidencia=[{"fuente": Fuente.SMARTOLT, "dato": f"{afectados} ONT",
                    "observado_en": timezone.now().isoformat()}],
        observada_en=timezone.now())


def _en_hilos(objetivo, cuantos=2, timeout=30):
    """Corre 'objetivo' en N hilos y devuelve los errores que levantaron."""
    errores = []

    def correr():
        from django.db import connection
        try:
            objetivo()
        except Exception as e:                                   # noqa: BLE001
            errores.append(f"{type(e).__name__}: {e}")
        finally:
            #  Cada hilo cierra SU conexion: dejarla abierta cuelga el teardown
            #  esperando el lock.
            connection.close()

    hilos = [threading.Thread(target=correr) for _ in range(cuantos)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=timeout)
    return errores


@pytest.mark.django_db(transaction=True)
def test_dos_ciclos_concurrentes_no_crean_dos_situaciones(org_a):
    #  LA CARRERA QUE IMPORTA. Los dos hilos ven que no hay situacion viva y los
    #  dos intentan crearla. El indice unico parcial deja pasar a uno; el otro
    #  recibe IntegrityError, vuelve a buscar y actualiza la que encontro.
    errores = _en_hilos(lambda: correlacion.agrupar(org_a, _senal()))

    assert errores == [], errores
    assert S.objects.filter(org=org_a).count() == 1, (
        "dos ciclos juntos tienen que producir UNA situacion")
    s = S.objects.get(org=org_a)
    #  Y el afectado tampoco se duplico.
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.PON).count() == 1


@pytest.mark.django_db(transaction=True)
def test_cuatro_ciclos_concurrentes_tampoco(org_a):
    #  Con cuatro la ventana se abre mas: si la garantia dependiera del 'select'
    #  previo, aqui apareceria mas de una.
    errores = _en_hilos(lambda: correlacion.agrupar(org_a, _senal()), cuantos=4)

    assert errores == [], errores
    assert S.objects.filter(org=org_a).count() == 1


@pytest.mark.django_db(transaction=True)
def test_dos_actualizaciones_concurrentes_no_pierden_afectados(org_a):
    #  LA ACTUALIZACION PERDIDA. Sin el 'select_for_update' de 'agrupar', los dos
    #  hilos leen el mismo conteo y el ultimo que escribe borra al otro. Cada uno
    #  trae un PON distinto, asi que al final tienen que estar los dos.
    svc.abrir(org_a, _senal("3/1/4"))
    s = S.objects.get(org=org_a)

    def agrega(clave):
        def _():
            svc.agregar_afectados(
                s, [{"tipo": TipoAfectado.PON, "identificador": clave}])
        return _

    errores = []
    hilos = []
    for clave in ("3/1/9", "3/1/10"):
        objetivo = agrega(clave)

        def correr(o=objetivo):
            from django.db import connection
            try:
                o()
            except Exception as e:                               # noqa: BLE001
                errores.append(f"{type(e).__name__}: {e}")
            finally:
                connection.close()

        hilos.append(threading.Thread(target=correr))
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert errores == [], errores
    #  El PON original mas los dos agregados.
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.PON).count() == 3
    s.refresh_from_db()
    #  El contador se RECALCULA de las filas, no se incrementa: por eso sobrevive
    #  a la carrera.
    assert s.afectados_contados == 3


@pytest.mark.django_db(transaction=True)
def test_dos_agrupaciones_concurrentes_sobre_la_MISMA_situacion(org_a):
    """
    Dos ciclos actualizando la situacion que ya existe. Los dos afectados quedan.

    QUE PROTEGE EL BLOQUEO, MEDIDO Y NO SUPUESTO (02/10/2026)
    --------------------------------------------------------
    La primera version de esta prueba daba a cada hilo un AFECTADO distinto y la
    mutacion que quita 'select_for_update' SOBREVIVIO. Tenia razon en sobrevivir:
    cada afectado es su propia FILA con su propia restriccion unica, y el contador
    se recalcula contando filas. Nada de eso necesita el bloqueo.

    Lo que SI lo necesita es 'situacion.evidencia': un campo JSON que
    'svc.actualizar' lee, le agrega y vuelve a escribir. Sin bloqueo los dos hilos
    leen la MISMA lista, cada uno le suma su observacion, y el ultimo que guarda
    borra la del otro -- la actualizacion perdida clasica, sobre el campo que
    justifica la situacion.

    Asi que esta prueba le da a cada hilo una EVIDENCIA distinta y exige las dos.
    """
    svc.abrir(org_a, _senal("3/1/4"))
    assert S.objects.filter(org=org_a).count() == 1

    #  Las dos señales son del MISMO PON --misma huella, misma situacion-- y cada
    #  una trae su propia evidencia y su propio afectado.
    def con(extra):
        s = _senal("3/1/4")
        s.afectados = list(s.afectados) + [
            {"tipo": TipoAfectado.ONT, "identificador": extra}]
        s.evidencia = [{"fuente": Fuente.SMARTOLT, "dato": f"observacion {extra}",
                        "observado_en": timezone.now().isoformat()}]
        return s

    errores = []
    hilos = []
    for extra in ("HWTC000000A1", "HWTC000000B2"):
        senal = con(extra)

        def correr(sn=senal):
            from django.db import connection
            try:
                correlacion.agrupar(org_a, sn)
            except Exception as e:                               # noqa: BLE001
                errores.append(f"{type(e).__name__}: {e}")
            finally:
                connection.close()

        hilos.append(threading.Thread(target=correr))
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert errores == [], errores
    assert S.objects.filter(org=org_a).count() == 1
    s = S.objects.get(org=org_a)
    onts = set(SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.ONT).values_list("identificador",
                                                        flat=True))
    #  LAS DOS. Si una se perdio, la actualizacion de un ciclo se fue al vacio.
    assert onts == {"HWTC000000A1", "HWTC000000B2"}, onts
    s.refresh_from_db()
    assert s.afectados_contados == SituacionAfectado.objects.filter(
        situacion=s, recuperado_en__isnull=True).count()

    #  Y LA EVIDENCIA DE LOS DOS, que es lo que el bloqueo protege de verdad.
    datos = {str(e.get("dato")) for e in (s.evidencia or [])}
    assert "observacion HWTC000000A1" in datos, datos
    assert "observacion HWTC000000B2" in datos, datos


@pytest.mark.django_db(transaction=True)
def test_el_ciclo_completo_dos_veces_a_la_vez_no_duplica(org_a):
    #  El caso real: el scheduler dispara dos turnos encimados y los dos corren
    #  la correlacion sobre la misma captura.
    ahora = timezone.now()
    f, _ = FuenteEstado.objects.update_or_create(
        org=org_a, fuente=Fuente.SMARTOLT,
        defaults={"activa": True, "frecuencia_segundos": 300,
                  "ventana_inconclusa_segundos": 0})
    fuentes.registrar(
        f, fuentes.Lectura(EstadoLectura.CON_DATOS, registros=1,
                           datos={"3/1/4": {"afectados": 12, "abonados": 103,
                                            "tipo": "partial_los"}},
                           dato_en=ahora, esquema="smartolt_pon_v1"),
        inicio=ahora, ahora=ahora)

    errores = _en_hilos(lambda: correlacion.correr(org_a, ahora=ahora))

    assert errores == [], errores
    assert S.objects.filter(org=org_a).count() == 1
    s = S.objects.get(org=org_a)
    assert SituacionAfectado.objects.filter(
        situacion=s, tipo=TipoAfectado.PON).count() == 1
