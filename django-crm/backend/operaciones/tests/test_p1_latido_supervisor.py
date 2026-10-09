# -*- coding: utf-8 -*-
"""
================================================================================
 P1  --  la puerta por donde el scheduler despierta al Supervisor
================================================================================

QUE SE AGREGO
-------------
`GET /api/operaciones/supervisor/latido/`. El scheduler de
`nucleo/programador/` no es una persona y no puede entrar por la puerta de una,
asi que no reusa `POST supervisor/ciclo/` --que escribe propuestas y exige
`EsJefeDeOperaciones`--: tiene su propia ruta, de solo lectura.

LAS CUATRO MANERAS EN QUE ESTO SALDRIA MAL
------------------------------------------
  1. QUE ESCRIBA. Toda la justificacion del bloque es que el primer trabajo del
     scheduler no produce efectos. Se afirma contando filas antes y despues --en
     las tablas que un ciclo SI tocaria-- y no leyendo el codigo de la vista.

  2. QUE CRUCE ORGANIZACIONES. La ruta acepta `organization_id` porque el turno
     lo manda. Si ese parametro se usara para ELEGIR la organizacion, un token
     de una empresa leeria la de al lado. Se prueba con el id real de otra
     organizacion, no con uno inventado: un uuid que no existe daria 409 por el
     motivo equivocado y la prueba pasaria sin probar nada.

  3. QUE CONTESTE SIN CREDENCIAL. Es una lectura de panorama operativo
     --cuantos casos estan desalineados, cuantas ordenes en riesgo-- y eso no es
     publico.

  4. QUE DEVUELVA DATOS DE CLIENTE. Lo que contesta lo consume el scheduler:
     va al informe en memoria del tick y a la linea de log del motor. (NO a una
     tabla: `job_run` no tiene columna de salida -- medido el 02/10/2026 en
     `tests/test_latido_extremo_a_extremo.py`, despues de que esta misma suite
     afirmara lo contrario por suponerlo.) Se afirma sobre el JSON SERIALIZADO,
     no sobre las claves del primer nivel: una evidencia anidada no se veria
     mirando solo arriba.

Y una quinta que no es de seguridad sino de honestidad del dato: que devuelva
cero cuando hay senales. Por eso hay un caso con UNA senal real --un caso
abierto hace mas de `DIAS_CASO_ANTIGUO` dias-- y no solo el panorama vacio: una
vista que devolviera `0` siempre pasaria todas las pruebas de arriba.
================================================================================
"""

import json
import uuid

from django.utils import timezone

from rest_framework.test import APIClient, force_authenticate  # noqa: F401

from cases.models import Case
from common.models import Activity
from operaciones import supervisor
from operaciones.models import PropuestaSupervisor

RUTA = "/api/operaciones/supervisor/latido/"


def _caso_viejo(org, dias=None):
    """Un caso abierto hace tanto que '_casos_abiertos_antiguos' lo ve."""
    dias = dias if dias is not None else supervisor.DIAS_CASO_ANTIGUO + 3
    caso = Case.objects.create(org=org, name="Sin internet", status="New",
                               priority="Normal")
    #  'created_at' es auto_now_add: hay que correrlo con un update, igual que
    #  hacen las demas suites de este modulo.
    Case.objects.filter(pk=caso.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=dias))
    return caso


# =============================================================================
#  1. contesta, y contesta la verdad
# =============================================================================

def test_el_latido_contesta_los_conteos_que_ve_el_supervisor(org_a, admin_client,
                                                             admin_profile):
    _caso_viejo(org_a)

    r = admin_client.get(RUTA)

    assert r.status_code == 200, r.content
    cuerpo = r.json()
    #  El numero no se fija a mano: se compara contra la MISMA funcion que la
    #  vista dice usar. Afirmar '== 1' ataria la prueba a cuantos detectores hay
    #  hoy, y el dia que se agregue uno fallaria por lo que no importa.
    esperadas = supervisor.detectar(org_a)
    assert cuerpo["senales_vigentes"] == len(esperadas)
    assert cuerpo["senales_vigentes"] >= 1, (
        "el caso viejo tenia que producir al menos una senal; si esto es 0, la "
        "vista devuelve un cero que no significa 'no hay nada'")
    assert cuerpo["fuente"] == "operaciones.supervisor.detectar"
    assert cuerpo["organizacion"] == str(org_a.id)


def test_el_desglose_por_tipo_suma_el_total(org_a, admin_client, admin_profile):
    _caso_viejo(org_a)
    _caso_viejo(org_a, dias=supervisor.DIAS_CASO_ANTIGUO + 40)

    cuerpo = admin_client.get(RUTA).json()

    assert sum(cuerpo["senales_por_tipo"].values()) == cuerpo["senales_vigentes"]
    assert all(isinstance(v, int) for v in cuerpo["senales_por_tipo"].values())


def test_sin_senales_contesta_cero_y_no_falla(org_a, admin_client, admin_profile):
    #  El panorama limpio tambien es una respuesta valida. Lo que NO puede pasar
    #  es que una organizacion sin datos haga reventar la ruta -- seria un fallo
    #  del turno indistinguible de un backend caido.
    r = admin_client.get(RUTA)

    assert r.status_code == 200
    assert r.json()["senales_vigentes"] == 0
    assert r.json()["senales_por_tipo"] == {}


# =============================================================================
#  2. no escribe NADA
# =============================================================================

def test_el_latido_no_escribe_ninguna_fila(org_a, admin_client, admin_profile):
    _caso_viejo(org_a)

    #  Las tres tablas que un CICLO del Supervisor si tocaria. Si el latido
    #  llamara a 'correr_ciclo' por error, aqui se veria.
    antes = (PropuestaSupervisor.objects.count(),
             Activity.objects.count(),
             Case.objects.count())

    assert admin_client.get(RUTA).status_code == 200
    #  Dos veces: una escritura idempotente se veria igual en la primera pasada.
    assert admin_client.get(RUTA).status_code == 200

    assert (PropuestaSupervisor.objects.count(),
            Activity.objects.count(),
            Case.objects.count()) == antes


def test_el_latido_declara_que_no_escribio(org_a, admin_client, admin_profile):
    #  El dato viaja en la respuesta para que quien lea el informe del tick --o
    #  la linea de log-- no tenga que ir al codigo a comprobar que fue una
    #  lectura.
    assert admin_client.get(RUTA).json()["escrituras"] == 0


# =============================================================================
#  3. el tenant se comprueba, no se elige
# =============================================================================

def test_el_organization_id_propio_se_acepta(org_a, admin_client, admin_profile):
    r = admin_client.get(RUTA, {"organization_id": str(org_a.id)})

    assert r.status_code == 200
    assert r.json()["organizacion"] == str(org_a.id)


def test_pedir_otra_organizacion_no_lee_nada(org_a, org_b, admin_client,
                                             admin_profile):
    #  El id REAL de otra organizacion, no uno inventado: con un uuid que no
    #  existe el 409 llegaria por el motivo equivocado.
    r = admin_client.get(RUTA, {"organization_id": str(org_b.id)})

    assert r.status_code == 409, r.content
    assert r.json()["error"] == "ORGANIZACION_DISTINTA"
    #  Y no se cuela el panorama de nadie en el cuerpo del rechazo.
    assert "senales_vigentes" not in r.json()


def test_un_organization_id_basura_tampoco_pasa(org_a, admin_client,
                                                admin_profile):
    for basura in (str(uuid.uuid4()), "no-es-un-uuid", "' or 1=1 --"):
        r = admin_client.get(RUTA, {"organization_id": basura})

        assert r.status_code == 409, f"{basura}: {r.content}"


def test_el_latido_no_cuenta_senales_de_otra_organizacion(org_a, org_b,
                                                          admin_client,
                                                          admin_profile):
    #  Toda la carga vieja esta en B; el token es de A.
    _caso_viejo(org_b)
    _caso_viejo(org_b)

    assert admin_client.get(RUTA).json()["senales_vigentes"] == 0


def test_cada_token_ve_su_propia_organizacion(org_a, org_b, admin_client,
                                              org_b_client, admin_profile,
                                              profile_b):
    _caso_viejo(org_b)

    assert admin_client.get(RUTA).json()["senales_vigentes"] == 0
    assert org_b_client.get(RUTA).json()["senales_vigentes"] >= 1


# =============================================================================
#  4. sin credencial no hay panorama
#
#  QUIEN RECHAZA, MEDIDO Y NO SUPUESTO (02/10/2026)
#  ------------------------------------------------
#  Las dos pruebas de abajo pasan, pero NO miden `permission_classes` de la
#  vista. Se comprobo por mutacion: poniendo `permission_classes = ()` en
#  `LatidoSupervisorView` las 15 pruebas siguen en verde. El rechazo lo produce
#  `common.middleware.rls_context.RequireOrgContext`, que devuelve 403 ANTES de
#  que DRF evalue los permisos de la vista, y el proyecto no declara
#  `DEFAULT_PERMISSION_CLASSES` (el default de DRF es `AllowAny`).
#
#  Lo que eso significa, dicho sin adornos: el efecto que un llamador real
#  experimenta ESTA garantizado --y es lo que miden estas dos-- pero la
#  declaracion de la vista es defensa en profundidad que por HTTP no se puede
#  distinguir. Esta ruta no esta exenta del middleware, asi que no hay forma de
#  llegar a `get()` sin organizacion para observar el permiso por separado.
#
#  Por eso hay ADEMAS una afirmacion sobre la DECLARACION, y esta etiquetada
#  como lo que es: no prueba un efecto, impide un borrado silencioso. Mentir
#  sobre cual de las dos cosas se midio es peor que no tener la segunda.
# =============================================================================

def test_sin_credencial_no_contesta(org_a, unauthenticated_client):
    r = unauthenticated_client.get(RUTA)

    assert r.status_code in (401, 403), r.content
    assert b"senales_vigentes" not in r.content


def test_autenticarse_sin_organizacion_no_alcanza(regular_user):
    #  'HasOrgContext' es la SEGUNDA mitad del permiso, y se mide aparte: un
    #  usuario valido cuyo token no lleva organizacion no tiene panorama que
    #  consultar, y la respuesta correcta es un rechazo, nunca un cero.
    #
    #  Se autentica sin pasar por 'OrgAwareRefreshToken' --que es justo lo que
    #  pone 'request.org'-- porque es la unica forma de llegar autenticado y sin
    #  organizacion por el mismo camino que lo haria un token mal emitido.
    cliente = APIClient()
    cliente.force_authenticate(user=regular_user)

    r = cliente.get(RUTA)

    assert r.status_code in (401, 403), r.content


def test_la_vista_declara_los_dos_permisos():
    """
    DECLARACION, no efecto -- y la distincion esta medida, no supuesta.

    Las dos pruebas de arriba siguen en verde aunque se le quiten los permisos a
    la vista (mutacion corrida el 02/10/2026), porque el middleware rechaza
    primero. Esta afirmacion no agrega una garantia nueva: hace que BORRAR la
    declaracion se vea, en vez de quedar tapado por el middleware que hoy la
    cubre y que manana puede eximir esta ruta.
    """
    from rest_framework.permissions import IsAuthenticated

    from common.permissions import HasOrgContext
    from operaciones.views import LatidoSupervisorView

    assert set(LatidoSupervisorView.permission_classes) == {
        IsAuthenticated, HasOrgContext}


# =============================================================================
#  5. lo que contesta termina en 'job_run': nada de datos de cliente
# =============================================================================

def test_la_respuesta_no_lleva_datos_de_cliente(org_a, admin_client,
                                                admin_profile):
    caso = _caso_viejo(org_a)

    plano = json.dumps(admin_client.get(RUTA).json())

    #  El nombre del caso es lo mas parecido a un dato de cliente que hay en
    #  esta cadena, y esta poblado a proposito: con el caso en blanco esto
    #  pasaria sin medir nada. Lo que sale de aqui lo lee el scheduler y acaba
    #  en el log del motor, que es razon suficiente.
    assert "Sin internet" not in plano
    assert str(caso.id) not in plano
    for prohibido in ("evidencia", "origen_id", "descripcion", "telefono",
                      "cedula", "direccion", "gps_lat", "gps_lng",
                      "coordenadas", "external_ticket_id"):
        assert prohibido not in plano, prohibido


def test_las_claves_de_la_respuesta_son_exactamente_estas(org_a, admin_client,
                                                          admin_profile):
    #  Conjunto FIJO, no 'contiene': asi un campo nuevo --un volcado de
    #  depuracion, la lista de senales entera-- rompe la prueba en vez de
    #  llegar callado al informe del tick y al log del motor.
    assert set(admin_client.get(RUTA).json()) == {
        "organizacion", "leido_en", "senales_vigentes", "senales_por_tipo",
        "escrituras", "fuente"}


# =============================================================================
#  6. es una LECTURA: los verbos que escriben no existen en esta ruta
# =============================================================================

def test_la_ruta_no_acepta_verbos_de_escritura(org_a, admin_client,
                                               admin_profile):
    for verbo in ("post", "put", "patch", "delete"):
        r = getattr(admin_client, verbo)(RUTA)

        assert r.status_code == 405, f"{verbo}: {r.status_code}"
