# -*- coding: utf-8 -*-
"""
================================================================================
 LA CAPA DE FUENTES, EN CARRERA  --  contra Postgres real y con hilos de verdad
================================================================================

POR QUE ESTA EN UN ARCHIVO APARTE
---------------------------------
Porque necesita 'transaction=True' --sin eso los hilos no ven lo que escribe el
otro-- y una prueba asi no convive con el resto en el mismo proceso de pytest:
pytest-django hace un flush y vuelve a emitir 'post_migrate' despues de cada una,
y con varias en la misma corrida el re-alta de permisos choca
('auth_permission_content_type_id_codename ... already exists').

Esta no es una teoria: al meter esta prueba dentro de 'test_p2_fuentes.py' se
cayeron CUATRO pruebas de concurrencia ajenas que venian en verde
(test_m03e4_secuencia, test_m03e5_jornada, test_m03g_capacidad), y volvieron a
pasar al sacarla. El repositorio ya resuelve esto con archivos propios -- la
convencion '*_concurrencia_postgres.py' de 'campo/tests/' y 'cases/tests/' existe
por lo mismo.

QUE SE MIDE
-----------
Que dos sondeos simultaneos de la MISMA organizacion no produzcan trabajo
duplicado ni dejen la fila de estado incoherente. Es lo que hace segura la
frecuencia por fuente: si dos turnos del scheduler se cruzaran --algo que el
lease del scheduler ya evita, pero que no se quiere depender de una sola
barrera-- la capa tiene que aguantar igual.
================================================================================
"""

import threading

import pytest
from django.utils import timezone

from operaciones import fuentes
from operaciones.fuentes_modelos import Fuente, FuenteEstado, FuenteSnapshot


@pytest.mark.django_db(transaction=True)
def test_dos_sondeos_concurrentes_no_duplican_la_captura(org_a):
    FuenteEstado.objects.update_or_create(
        org=org_a, fuente=Fuente.M02,
        defaults={"activa": True, "frecuencia_segundos": 900})
    errores = []

    def correr():
        from django.db import connection
        try:
            fuentes.sondear(org_a)
        except Exception as e:                                   # noqa: BLE001
            errores.append(f"{type(e).__name__}: {e}")
        finally:
            #  Cada hilo cierra SU conexion: dejarla abierta hace que el
            #  teardown de la prueba se cuelgue esperando el lock.
            connection.close()

    hilos = [threading.Thread(target=correr) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert errores == [], errores
    #  A lo sumo una captura por pasada: mas de dos significaria que la carrera
    #  produjo trabajo que nadie pidio.
    assert FuenteSnapshot.objects.filter(
        org=org_a, fuente=Fuente.M02).count() <= 2
    f = FuenteEstado.objects.get(org=org_a, fuente=Fuente.M02)
    #  Y la fila queda coherente: consultada, con su proxima fecha puesta.
    assert f.proxima_consulta_en is not None
    assert f.ultima_consulta_fin is not None
    assert f.proxima_consulta_en > f.ultima_consulta_fin


@pytest.mark.django_db(transaction=True)
def test_la_poda_concurrente_no_borra_el_ultimo(org_a):
    #  'podar()' corre dentro de cada registro. Dos podas simultaneas no pueden
    #  dejar a la fuente SIN captura: sin la ultima, el ciclo siguiente no tiene
    #  contra que comparar y la diferencia se pierde en silencio.
    f, _ = FuenteEstado.objects.update_or_create(
        org=org_a, fuente=Fuente.M03,
        defaults={"activa": True, "frecuencia_segundos": 30})
    ahora = timezone.now()
    for i in range(fuentes.SNAPSHOTS_QUE_SE_CONSERVAN + 5):
        fuentes.registrar(
            f, fuentes.Lectura("sin_registros", registros=0,
                               esquema="m03_programacion_v1"),
            inicio=ahora, ahora=ahora + timezone.timedelta(seconds=i))

    errores = []

    def podar():
        from django.db import connection
        try:
            fuentes.podar(org_a.id, Fuente.M03)
        except Exception as e:                                   # noqa: BLE001
            errores.append(f"{type(e).__name__}: {e}")
        finally:
            connection.close()

    hilos = [threading.Thread(target=podar) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert errores == [], errores
    quedan = FuenteSnapshot.objects.filter(org=org_a, fuente=Fuente.M03).count()
    assert quedan >= 1, "la poda no puede dejar a la fuente sin captura"
    assert quedan <= fuentes.SNAPSHOTS_QUE_SE_CONSERVAN
