# -*- coding: utf-8 -*-
"""
================================================================================
 DEL TICKET A LA CUADRILLA  --  el circuito entero, sin saltarse un eslabon
================================================================================

Por que existe
--------------
CLAUDE.md §6: «toda funcion nueva necesita al menos una prueba que atraviese la
cadena real». Cada pieza de este circuito tiene sus pruebas y todas estan en
verde, y aun asi eso NO prueba que el circuito funcione: ya se cobro dos veces
el mismo dia (29/09/2026) que el backend este bien y la capa de al lado deje
caer el dato en silencio.

Aca se recorre entero, en orden, con las funciones y los endpoints de verdad:

    1. hay un caso abierto con servicio en el proveedor
    2. el SUPERVISOR lo mira y propone que necesita visita
    3. una PERSONA acepta esa propuesta
    4. el caso aparece en DESPACHO
    5. se despacha: nace una ORDEN con su plantilla
    6. el CICLO DE LA MADRUGADA arma la jornada de la cuadrilla
    7. el REPARTO le propone esa orden a la cuadrilla que cubre su zona y labor
    8. una PERSONA publica
    9. el TECNICO ve el trabajo en su telefono

Si alguno de los nueve se corta, esto falla -- y falla nombrando cual.

Lo que NO cubre
---------------
Las llamadas reales a WispHub y SmartOLT. El contexto tecnico se sustituye,
porque lo que se prueba es que el dato ATRAVIESE las nueve capas, no que el
proveedor conteste. Eso ya lo cubren las skills y el verificador de API.

    pytest campo/tests/test_circuito_completo.py
================================================================================
"""

import datetime as dt

import pytest

from campo.cuadrillas import (Cuadrilla, IntegranteDeJornada,
                              JornadaDeCuadrilla, PersonaDeCampo)
from campo.models import (AsignacionTrabajo, OrdenTrabajo, WorkType,
                          WorkTypeVersion)
from campo.zonas import AliasDeZona, ZonaOperativa
from operaciones.models import PropuestaSupervisor

pytestmark = pytest.mark.django_db

HOY = dt.date(2026, 10, 9)
LOCALIDAD = "MARTHA GISELA"

CASOS = "/api/campo/casos-despachables/"
CREAR = "/api/campo/trabajos/crear/"
TRABAJOS = "/api/campo/trabajos/"


@pytest.fixture
def plantilla(org_a):
    """Un tipo de trabajo CLASIFICADO. Sin labor no se reparte."""
    tipo = WorkType.objects.create(org=org_a, codigo="ftth_correctivo",
                                   nombre="Correctivo FTTH",
                                   labor="correctivo")
    return WorkTypeVersion.objects.create(
        work_type=tipo, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": []},
    )


@pytest.fixture
def zona(org_a):
    z = ZonaOperativa.objects.create(org=org_a, nombre="Norte")
    AliasDeZona.objects.create(org=org_a, zona=z, localidad=LOCALIDAD)
    return z


@pytest.fixture
def contexto_del_equipo_caido(monkeypatch):
    """Lo que el motor devolveria: el equipo caido por fibra.

    Se sustituye el viaje al motor, no la decision: la clasificacion real
    corre sobre este snapshot.
    """
    snapshot = {
        "contexto_disponible": True,
        "capturado_en": "2026-10-09T03:00:00Z",
        "servicio": "6580",
        "cliente": {"nombre": "Alguien", "localidad": LOCALIDAD,
                    "telefono": "3242124123,3002687147",
                    "direccion": "Calle 5 # 12-34"},
        "equipo": {"estado": "caido", "causa_caida": "fibra"},
    }
    #  SE SUSTITUYE EN LOS DOS LUGARES DONDE SE USA, no solo en el modulo que
    #  lo define. `despacho_views` hace `from ... import contexto_del_caso`, o
    #  sea que tiene su PROPIA referencia: parchear solo el origen deja la
    #  vista llamando al original. Costo una falla que aparecia en la suite y
    #  no al correr el archivo solo.
    import campo.despacho_pantalla_views as pantalla   # noqa: F401
    import campo.despacho_views as vistas
    import campo.services.despacho as desp
    import operaciones.supervisor as sup               # noqa: F401

    monkeypatch.setattr(desp, "contexto_del_caso", lambda cid: snapshot)
    monkeypatch.setattr(vistas, "contexto_del_caso", lambda cid: snapshot)
    return snapshot


def test_del_ticket_a_la_cuadrilla(
    admin_client, org_a, admin_profile, plantilla, zona,
    contexto_del_equipo_caido,
):
    """Los nueve eslabones, en orden, sin saltarse ninguno."""
    from cases.models import Case
    from campo import jornada_automatica, reparto
    from operaciones import supervisor

    # --- 1 · un caso abierto, con servicio en el proveedor ----------------
    caso = Case.objects.create(
        org=org_a, name="No tiene internet", status="New", priority="Normal",
        is_active=True, external_service_id="6580",
        #  `case_external_ref_complete` exige las DOS o ninguna: un proveedor
        #  sin ticket no se puede cruzar, y un ticket sin proveedor no se
        #  puede resolver contra nada. Media referencia es un estado sin
        #  significado.
        external_ticket_id="95047", provider="wisphub",
    )

    # --- 2 · el Supervisor lo mira y propone ------------------------------
    senales = supervisor._casos_que_necesitan_visita(org_a, _ahora())
    assert len(senales) == 1, "el Supervisor no detecto que necesita visita"
    senal = senales[0]
    assert senal.tipo == PropuestaSupervisor.CASO_REQUIERE_VISITA
    assert senal.origen_id == str(caso.id)
    assert senal.datos["labor_sugerida"] == "correctivo"

    # --- 3 · una persona la acepta ----------------------------------------
    PropuestaSupervisor.objects.create(
        org=org_a, tipo_senal=senal.tipo, origen_tipo="case",
        origen_id=senal.origen_id, estado=PropuestaSupervisor.ACEPTADA,
        evidencia=senal.evidencia,
    )

    # --- 4 · aparece en Despacho ------------------------------------------
    cuerpo = admin_client.get(f"{CASOS}?ficha=1").json()
    assert [c["id"] for c in cuerpo["casos"]] == [str(caso.id)], \
        "el caso aprobado no llego a la pantalla de despacho"
    fila = cuerpo["casos"][0]
    assert fila["sugerencia"]["labor"] == "correctivo"
    assert fila["sugerencia"]["verificada"] is True

    # --- 5 · se despacha: nace la orden -----------------------------------
    r = admin_client.post(CREAR, {
        "work_type_version_id": str(plantilla.id),
        "case_id": str(caso.id),
        "cliente_nombre": "Alguien",
        "zona": LOCALIDAD,
    }, format="json", HTTP_IDEMPOTENCY_KEY="circuito-1")
    assert r.status_code == 201, r.content
    orden = OrdenTrabajo.objects.get(pk=r.data["orden"]["id"])
    #  La clasificacion queda CONGELADA en la orden: es la evidencia de que
    #  decia la medicion el dia que salio.
    assert orden.contexto["labor_sugerida"]["labor"] == "correctivo"

    #  LA ZONA LLEGO SOLA, Y ESO ES EL PUNTO. Hasta el 09/10/2026 la
    #  pantalla no la mandaba --el backend la aceptaba y nadie se la daba-- y
    #  la orden nacia sin barrio: el reparto la dejaba en `sin_zona` para
    #  siempre y el sintoma, "no se asigno", no señalaba ahi. Lo destapo esta
    #  misma prueba, que al principio tuvo que ponerla a mano.
    #  Y CON QUE LLAMAR Y A DONDE IR. Hasta el 09/10/2026 solo el nombre caia
    #  del contexto: el telefono y la direccion quedaban vacios aunque la
    #  ficha los trajera, y el tecnico llegaba sin poder llamar ni saber la
    #  direccion. La orden se creaba igual, sin error, asi que nadie lo veia.
    assert orden.cliente_telefono == "3242124123,3002687147", (
        "la orden nacio sin telefono: el tecnico no tiene a quien llamar"
    )
    assert orden.cliente_direccion == "Calle 5 # 12-34", (
        "la orden nacio sin direccion: el tecnico no sabe a donde ir"
    )

    assert (orden.zona or "").strip() == LOCALIDAD, (
        "la orden nacio SIN localidad: el reparto no va a poder darsela a "
        "ninguna cuadrilla"
    )

    # --- 6 · el ciclo de la madrugada arma la jornada ----------------------
    cuadrilla = Cuadrilla.objects.create(
        org=org_a, nombre="Cuadrilla 1", lider=admin_profile,
        labor_habitual="correctivo",
    )
    cuadrilla.zonas_habituales.set([zona])
    pedro = PersonaDeCampo.objects.create(
        org=org_a, nombre="Pedro Ayudante")           # sin cuenta, a proposito

    armado = jornada_automatica.asegurar_jornadas(org_a, HOY)
    assert armado["estrenadas"] == ["Cuadrilla 1"], armado
    jornada = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=HOY)
    assert jornada.labor == "correctivo"
    assert [z.nombre for z in jornada.zonas.all()] == ["Norte"]

    #  El lider entra como persona de campo con su cuenta; el auxiliar sin
    #  ella. Los dos integran la cuadrilla.
    lider = PersonaDeCampo.objects.create(
        org=org_a, nombre="La Lider", profile=admin_profile)
    IntegranteDeJornada.objects.create(
        org=org_a, jornada=jornada, persona=lider, rol="tecnico_lider")
    IntegranteDeJornada.objects.create(
        org=org_a, jornada=jornada, persona=pedro, rol="ayudante")

    # --- 7 · el reparto se la propone a esa cuadrilla ----------------------
    propuesta = reparto.proponer(org_a, HOY)
    asignadas = {a["cuadrilla"].nombre: [o.numero for o in a["ordenes"]]
                 for a in propuesta["asignaciones"]}
    assert asignadas.get("Cuadrilla 1") == [orden.numero], (
        f"el reparto no le dio la orden a la cuadrilla. "
        f"sin_zona={[o.numero for o in propuesta['sin_zona']]} "
        f"sin_cuadrilla={[o.numero for o in propuesta['sin_cuadrilla']]} "
        f"sin_clasificar={[o.numero for o in propuesta['sin_clasificar']]}"
    )

    # --- 8 · una persona publica -------------------------------------------
    r = admin_client.post("/api/campo/cuadrillas/reparto/", {
        "asignaciones": [{"jornada": str(jornada.id),
                          "ordenes": [str(orden.id)]}],
    }, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["publicadas"] == 1
    #  El auxiliar NO recibe asignacion --no entra al sistema-- y se dice.
    assert r.json()["auxiliares_sin_asignacion"] == 1

    # --- 9 · el tecnico lo ve en su telefono -------------------------------
    asignacion = AsignacionTrabajo.objects.get(orden=orden)
    assert asignacion.profile_id == admin_profile.id
    assert asignacion.es_principal is True

    suyos = admin_client.get(f"{TRABAJOS}?solo_mios=1").json()
    #  La clave es `results` --paginado con cursor--, no `resultados`. Se
    #  nombra la de verdad en vez de probar varias: una prueba que acepta tres
    #  formas posibles no dice cual es la que el cliente movil tiene que leer.
    numeros = [t["numero"] for t in (suyos.get("results") or [])]
    assert orden.numero in numeros, (
        f"la orden publicada no aparece en los trabajos del tecnico: {suyos}"
    )


def test_un_eslabon_cortado_se_nota(
    admin_client, org_a, admin_profile, plantilla, zona,
    contexto_del_equipo_caido,
):
    """Si el tipo de trabajo NO esta clasificado, el reparto lo deja afuera.

    Es el eslabon mas facil de olvidar --se clasifica una vez y nadie vuelve
    a mirarlo-- y su sintoma, «no se asigno nada», no señala la causa.
    """
    from campo import reparto

    plantilla.work_type.labor = ""
    plantilla.work_type.save(update_fields=["labor"])

    orden = OrdenTrabajo.objects.create(
        org=org_a, numero=1, tipo_trabajo_version=plantilla,
        estado_operativo=OrdenTrabajo.ASIGNADA, zona=LOCALIDAD,
    )
    cuadrilla = Cuadrilla.objects.create(org=org_a, nombre="Cuadrilla 1")
    jornada = JornadaDeCuadrilla.objects.create(
        org=org_a, cuadrilla=cuadrilla, fecha=HOY, labor="correctivo")
    jornada.zonas.set([zona])

    propuesta = reparto.proponer(org_a, HOY)
    assert propuesta["asignaciones"][0]["ordenes"] == []
    #  Y se NOMBRA donde quedo, con el tipo que hay que clasificar.
    assert [o.numero for o in propuesta["sin_clasificar"]] == [orden.numero]


def _ahora():
    from django.utils import timezone

    return timezone.now()
