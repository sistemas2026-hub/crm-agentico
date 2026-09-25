# -*- coding: utf-8 -*-
"""
================================================================================
 EL NOMBRE DEL CLIENTE EN LA BANDEJA DEL SUPERVISOR
================================================================================

QUE GUARDA ESTE ARCHIVO
-----------------------
Que la columna «Cliente» de «Pendientes por revision» diga un nombre cuando
hay uno, y que diga que no lo hay cuando no lo hay -- sin inventarlo y sin
arrastrar nada mas de la persona.

DE DONDE SALE
-------------
Medido en produccion el 25/09/2026: la tabla 'accounts' esta VACIA -- no
desenlazada, vacia -- asi que los 237 casos no tenian ningun nombre que
mostrar y la pantalla decia «No disponible en la fuente» en las 121 propuestas.
El importador ya recibia el nombre del proveedor en la misma llamada que ya
hacia, y lo tiraba.

EL ORDEN, Y POR QUE ESE
-----------------------
1. 'account.name': el registro que la empresa mantiene. Si existe, manda.
2. 'external_client_name': lo que dijo el proveedor al importar. Puede estar
   viejo; nombrar al cliente con un dato de hace un mes es mejor que no
   nombrarlo.
3. Vacio.

LO QUE SE AFIRMA, Y LO QUE NO
-----------------------------
Se afirma sobre el VALOR que sale del contexto, no sobre que el codigo consulte
tal campo: un 'or' de respaldo agregado despues pasaria una prueba escrita al
reves. Y se afirma que la cedula, el telefono, la direccion y las coordenadas
NO salen -- no que no se consulten, que no salen.
================================================================================
"""

import uuid

import pytest
from django.utils import timezone

from conftest import rls_org
from operaciones import contexto_propuesta
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

NOMBRE_DEL_CRM = "Cuenta Del Crm"
NOMBRE_DEL_PROVEEDOR = "Nombre Del Proveedor"


# =============================================================================
#  utilidades
# =============================================================================

def _caso(org, **extra):
    """Un caso importado, con la forma que deja el importador."""
    from cases.models import Case

    datos = dict(
        org=org,
        name="Sin servicio de internet",
        status="New",
        priority="Normal",
        provider="wisphub",
        external_ticket_id=f"t{uuid.uuid4().hex[:8]}",
        external_service_id="6580",
    )
    datos.update(extra)
    return Case.objects.create(**datos)


def _cuenta(org, nombre=NOMBRE_DEL_CRM):
    from accounts.models import Account

    return Account.objects.create(org=org, name=nombre)


def _propuesta_de(org, caso, **extra):
    datos = dict(
        org=org,
        tipo_senal=PropuestaSupervisor.CASO_DESINCRONIZADO,
        origen_tipo="case",
        origen_id=str(caso.id),
        accion_propuesta="Revisar la sincronizacion",
        motivo="El proveedor lo reporta cerrado y aqui sigue abierto.",
        evidencia=[{
            "fuente": "cases.Case",
            "id": str(caso.id),
            "dato": "estado en el proveedor: Cerrado",
            "observado_en": timezone.now().isoformat(),
        }],
        prioridad=30,
        impacto="Infla la cola",
        huella_condicion="huella-" + uuid.uuid4().hex[:8],
        expira_en=timezone.now() + timezone.timedelta(days=7),
    )
    datos.update(extra)
    return PropuestaSupervisor.objects.create(**datos)


def _cliente_de(org, caso):
    propuesta = _propuesta_de(org, caso)
    contexto = contexto_propuesta.contexto_de(org, [propuesta])
    return contexto[str(propuesta.id)]["cliente"]


# =============================================================================
#  §1  EL ORDEN DE PRECEDENCIA
# =============================================================================

def test_con_cuenta_del_crm_usa_el_nombre_de_la_cuenta(org_a):
    """La cuenta del CRM manda: es el dato que alguien de la empresa mantiene."""
    with rls_org(org_a):
        caso = _caso(org_a, account=_cuenta(org_a),
                     external_client_name=NOMBRE_DEL_PROVEEDOR)
        assert _cliente_de(org_a, caso) == NOMBRE_DEL_CRM


def test_sin_cuenta_usa_el_nombre_que_dio_el_proveedor(org_a):
    """
    EL CASO QUE MOTIVO TODO EL BLOQUE.

    Es la forma de los 177 casos importados: sin cuenta, con servicio externo.
    """
    with rls_org(org_a):
        caso = _caso(org_a, external_client_name=NOMBRE_DEL_PROVEEDOR)
        assert _cliente_de(org_a, caso) == NOMBRE_DEL_PROVEEDOR


def test_sin_ninguno_de_los_dos_queda_vacio(org_a):
    """
    Vacio, no un nombre armado con lo que haya.

    La pantalla traduce el vacio a «No disponible en la fuente». Lo que NO
    puede pasar es que salga el numero de ticket, el asunto, o la cuenta del
    ISP que abrio el ticket ('external_created_by'), que no es el cliente.
    """
    with rls_org(org_a):
        caso = _caso(org_a, external_client_name="",
                     external_created_by="Soporte - api@rapilink-sas")
        assert _cliente_de(org_a, caso) == ""


def test_una_cuenta_con_nombre_en_blanco_cae_al_del_proveedor(org_a):
    """
    Una cuenta existe pero su nombre esta vacio.

    Sin esto el orden seria «si HAY cuenta, usa su nombre», y una cuenta con el
    nombre en blanco dejaria la celda vacia teniendo un nombre a mano.
    """
    with rls_org(org_a):
        caso = _caso(org_a, account=_cuenta(org_a, nombre="   "),
                     external_client_name=NOMBRE_DEL_PROVEEDOR)
        assert _cliente_de(org_a, caso) == NOMBRE_DEL_PROVEEDOR


def test_los_espacios_alrededor_no_viajan(org_a):
    with rls_org(org_a):
        caso = _caso(org_a, external_client_name="  Juan Perez  ")
        assert _cliente_de(org_a, caso) == "Juan Perez"


# =============================================================================
#  §2  LO QUE NO SALE
# =============================================================================

def test_el_contexto_no_trae_ningun_otro_dato_personal(org_a):
    """
    Solo el nombre.

    La misma fila del proveedor que trae el nombre trae la cedula, el telefono,
    la direccion, el GPS del domicilio y cuatro contrasenas. Ninguno de esos
    campos existe en 'Case', y esta prueba afirma que el contexto no gana
    claves nuevas: el dia que alguien agregue 'telefono' al diccionario, falla
    aqui y no en produccion.
    """
    with rls_org(org_a):
        caso = _caso(org_a, external_client_name=NOMBRE_DEL_PROVEEDOR)
        propuesta = _propuesta_de(org_a, caso)
        fila = contexto_propuesta.contexto_de(org_a, [propuesta])[str(propuesta.id)]

    assert set(fila) == set(contexto_propuesta.VACIO)
    prohibidos = ("cedula", "documento", "telefono", "celular", "direccion",
                  "gps", "lat", "lng", "coordenada", "password", "contrasena")
    for clave in fila:
        assert not any(p in clave.lower() for p in prohibidos), clave


def test_el_nombre_no_entra_en_la_evidencia_de_la_propuesta(org_a):
    """
    El nombre es para la PANTALLA, no para el expediente de la propuesta.

    La evidencia la escribe el detector y es lo que queda guardado y auditado;
    el contexto se resuelve al leer. Meter el nombre en la evidencia lo
    persistiria en otra tabla mas, sin que nadie lo haya decidido.
    """
    with rls_org(org_a):
        caso = _caso(org_a, external_client_name=NOMBRE_DEL_PROVEEDOR)
        propuesta = _propuesta_de(org_a, caso)
        contexto_propuesta.contexto_de(org_a, [propuesta])
        propuesta.refresh_from_db()

    assert NOMBRE_DEL_PROVEEDOR not in str(propuesta.evidencia)
    assert NOMBRE_DEL_PROVEEDOR not in (propuesta.motivo or "")
    assert NOMBRE_DEL_PROVEEDOR not in (propuesta.accion_propuesta or "")


# =============================================================================
#  §3  AISLAMIENTO Y COSTO
# =============================================================================

def test_el_caso_de_otra_organizacion_no_presta_su_nombre(org_a, org_b):
    """
    'origen_id' es texto libre: podria apuntar a un caso de otra empresa.

    El filtro por org va igual, y el efecto que se afirma es que el nombre NO
    aparece -- no que la consulta lleve un WHERE.
    """
    with rls_org(org_b):
        ajeno = _caso(org_b, external_client_name="Cliente De La Otra Empresa")

    with rls_org(org_a):
        propuesta = _propuesta_de(org_a, ajeno, origen_id=str(ajeno.id))
        fila = contexto_propuesta.contexto_de(org_a, [propuesta])[str(propuesta.id)]

    assert fila["cliente"] == ""


def test_resolver_el_lote_no_cuesta_una_consulta_por_caso(org_a, django_assert_num_queries):
    """
    NINGUNA llamada al proveedor, y un numero de consultas que no crece con el
    lote.

    Es la razon por la que el nombre se persiste en vez de resolverse al
    pintar: hay 103 servicios distintos detras de las propuestas visibles, y
    preguntarle al proveedor por cada uno serian 103 llamadas HTTP por cada
    carga del tablero.

    Se mide con DIEZ casos y se exige el MISMO numero de consultas que con
    uno. Un N+1 introducido despues no pasa esta prueba.
    """
    with rls_org(org_a):
        uno = [_propuesta_de(org_a, _caso(org_a, external_client_name="A B"))]
        with django_assert_num_queries(1) as captura:
            contexto_propuesta.contexto_de(org_a, uno)
        consultas_con_uno = len(captura.captured_queries)

        diez = [_propuesta_de(org_a, _caso(org_a, external_client_name=f"N {i}"))
                for i in range(10)]
        with django_assert_num_queries(consultas_con_uno):
            resuelto = contexto_propuesta.contexto_de(org_a, diez)

    assert len(resuelto) == 10
    assert all(v["cliente"] for v in resuelto.values())


# =============================================================================
#  §4  LO QUE YA FUNCIONABA SIGUE FUNCIONANDO
# =============================================================================

def test_una_propuesta_de_orden_sigue_tomando_el_nombre_de_la_orden(org_a):
    """
    El camino de la orden de trabajo no se toco.

    'OrdenTrabajo.cliente_nombre' ya servia el nombre antes de este cambio, y
    es el precedente que lo justifica. Si se hubiera roto al mover la
    resolucion del caso a una funcion aparte, se veria aca.
    """
    from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion

    with rls_org(org_a):
        sufijo = uuid.uuid4().hex[:8]
        tipo = WorkType.objects.create(
            org=org_a, nombre=f"Instalacion {sufijo}", codigo=f"ins_{sufijo}")
        version = WorkTypeVersion.objects.create(
            work_type=tipo, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA,
            esquema={"campos": [], "evidencias": []})
        orden = OrdenTrabajo.objects.create(
            org=org_a, numero=9401, tipo_trabajo_version=version,
            cliente_nombre="Cliente De La Orden",
            cliente_direccion="Calle 1 #2-3")
        propuesta = PropuestaSupervisor.objects.create(
            org=org_a,
            tipo_senal=PropuestaSupervisor.ORDEN_SIN_PROGRAMAR,
            origen_tipo="orden_trabajo",
            origen_id=str(orden.id),
            accion_propuesta="Programar la orden",
            motivo="Lleva 3 dias sin fecha.",
            evidencia=[{"fuente": "campo.OrdenTrabajo", "id": "ot",
                        "dato": "sin programada_para",
                        "observado_en": timezone.now().isoformat()}],
            prioridad=30,
            impacto="El cliente no tiene fecha",
            huella_condicion="huella-" + uuid.uuid4().hex[:8],
            expira_en=timezone.now() + timezone.timedelta(days=7))
        fila = contexto_propuesta.contexto_de(org_a, [propuesta])[str(propuesta.id)]

    assert fila["cliente"] == "Cliente De La Orden"


def test_un_caso_sin_el_campo_poblado_no_rompe_nada(org_a):
    """
    La forma EXACTA de los 177 casos antes del backfill: el campo existe y esta
    vacio. No debe fallar ni ensuciar las otras columnas.
    """
    with rls_org(org_a):
        caso = _caso(org_a)
        propuesta = _propuesta_de(org_a, caso)
        fila = contexto_propuesta.contexto_de(org_a, [propuesta])[str(propuesta.id)]

    assert fila["cliente"] == ""
    assert fila["ticket_externo"] == caso.external_ticket_id
    assert fila["proveedor_externo"] == "wisphub"
    assert fila["asunto"] == "Sin servicio de internet"
