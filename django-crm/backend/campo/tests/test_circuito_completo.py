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


def test_del_TEXTO_del_reclamo_a_la_cuadrilla(
    admin_client, org_a, admin_profile, plantilla, zona,
    contexto_del_equipo_caido, monkeypatch,
):
    """El OTRO camino a Despacho: el que sale de LEER el reclamo.

    POR QUE HACIA FALTA ESTA PRUEBA
    -------------------------------
    `CasosDespachablesView` acepta DOS tipos de senal, y lo dice con todas las
    letras (`despacho_pantalla_views.py:180-183`):

        CASO_REQUIERE_VISITA     lo sostiene una MEDICION del equipo
        TICKET_SIN_DIAGNOSTICO   sale de LEER el reclamo (13/10/2026)

    La prueba de arriba recorre el primero entero. **Del segundo no habia
    ninguna que llegara a Despacho** -- medido el 13/10/2026: buscar
    TICKET_SIN_DIAGNOSTICO en las pruebas de `campo/` daba cero. O sea que el
    camino que el cliente pidio --"que la clasificacion salga del resultado de
    esa prueba o del texto que tiene el ticket, ambas sirven"-- estaba
    construido y nadie habia comprobado que desembocara donde tiene que
    desembocar.

    Lo que se rompe sin esto, y no se nota: si `_tickets_abiertos_con_tecnico`
    guardara otro `origen_tipo`, o la propuesta naciera con otro `tipo_senal`,
    los tickets leidos NUNCA aparecerian en Despacho, y el sintoma --"la
    pantalla esta vacia"-- no senala ahi. Es la misma forma de fallar que ya se
    pago dos veces (CLAUDE.md §6).

    EL MODELO NO SE LLAMA. `diagnosticar` recibe `concluir` inyectado, a
    proposito: este eslabon prueba que el dato ATRAVIESE las capas, no que el
    modelo acierte.
    """
    from cases.models import Case
    from campo import jornada_automatica, reparto
    from operaciones import diagnostico_de_ticket, supervisor

    ahora = _ahora()

    # --- 1 - un ticket ABIERTO en el proveedor, con tecnico y con texto ----
    #  Las CINCO precondiciones de `_tickets_abiertos_con_tecnico`, puestas a
    #  proposito y no por casualidad: estado en curso alla, lectura fresca,
    #  alguien asignado, descripcion con texto, y el AREA.
    #
    #  EL AREA SE AGREGO EL 14/10/2026 y esta prueba la encontro al correrla
    #  contra produccion seis dias despues de escribirla: sin `area`, el caso
    #  es `indecidible_sin_mapa` y la señal no sale --"si no se puede saber, no
    #  se lee nada"--. No es un defecto: nacio de una medicion del cliente
    #  ("revise la lista de soporte tecnico y no salen los ticket de descuentos
    #  programados, esos son de cartera"), y una persona concentraba 563
    #  tickets de los cuales 509 eran de cartera.
    #
    #  'soporte_tecnico' es lo que la importacion escribe en `Case.area` desde
    #  `importacion_tickets.destinos` del tenant -- el mismo valor que produce
    #  el comodin 'soporte tecnico|*'. Ver `AREAS_DEL_SUPERVISOR`.
    caso = Case.objects.create(
        org=org_a, name="Internet intermitente", status="New",
        priority="Normal", is_active=True, area="soporte_tecnico",
        description="Dice que se le cae el internet cada rato desde el lunes.",
        external_service_id="6580", external_ticket_id="95048",
        provider="wisphub", external_status="En progreso",
        external_fetched_at=ahora - dt.timedelta(hours=1),
    )
    caso.assigned_to.add(admin_profile)

    #  Y UNO DE CARTERA, IDENTICO EN TODO LO DEMAS. Lo que el cliente pidio: la
    #  lista de soporte no trae los tickets de otra area. Se pone ACA y no en
    #  una prueba aparte porque es la MISMA consulta la que los separa, y
    #  afirmarlo con un solo caso presente no distingue "lo filtro" de "no
    #  habia ninguno".
    ajeno = Case.objects.create(
        org=org_a, name="Descuento programado", status="New",
        priority="Normal", is_active=True, area="cartera",
        description="Pregunta por el descuento que le prometieron.",
        external_service_id="6581", external_ticket_id="95050",
        provider="wisphub", external_status="En progreso",
        external_fetched_at=ahora - dt.timedelta(hours=1),
    )
    ajeno.assigned_to.add(admin_profile)

    # --- 2 - el Supervisor lo detecta --------------------------------------
    #  EL MAPA DE AREAS VIVE EN EL MOTOR, y sin el no se lee NADA.
    #
    #  `criterio_de_area()` pide `area_por_persona()`, que sale por HTTP al
    #  motor. En una prueba no hay motor, el mapa vuelve vacio, y
    #  `_tickets_abiertos_con_tecnico` devuelve `[]` ANTES de mirar un solo
    #  caso: «un mapa vacio es ambiguo --nadie tiene area, o el motor no
    #  contesto-- y se trata como "no se pudo"». Es fail-closed a proposito,
    #  porque leer un ticket cuesta una llamada al modelo.
    #
    #  Se sustituye la LECTURA, no la decision: el criterio real corre sobre
    #  este mapa. Y queda afirmado de paso que esta señal DEPENDE de que el
    #  motor conteste -- que es una dependencia del circuito y no un detalle
    #  del laboratorio.
    from operaciones import areas_del_tenant
    monkeypatch.setattr(areas_del_tenant, "area_por_persona",
                        lambda: {str(admin_profile.id): "soporte_tecnico"})

    senales = supervisor._tickets_abiertos_con_tecnico(org_a, ahora)
    assert [s.origen_id for s in senales] == [str(caso.id)], (
        f"el Supervisor tenia que detectar SOLO el de soporte. "
        f"detecto={[s.origen_id for s in senales]} "
        f"soporte={caso.id} cartera={ajeno.id}"
    )
    #  Las dos mitades de la misma afirmacion, por separado: que el de soporte
    #  SI entre, y que el de cartera NO.
    assert str(ajeno.id) not in [s.origen_id for s in senales], (
        "un ticket de cartera entro a la cola de soporte"
    )
    senal = senales[0]
    assert senal.tipo == PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO
    #  LA DESCRIPCION NO VIAJA EN LA SENAL, y es una decision de privacidad,
    #  no un olvido: 136 de cada 300 tickets traen una cedula escrita a mano,
    #  y una senal termina guardada en una propuesta.
    assert "description" not in senal.datos
    assert senal.datos["tiene_descripcion"] is True

    # --- 3 - se LEE el reclamo y queda la labor ----------------------------
    class _Veredicto:
        hipotesis = "Enlace optico degradado; intermitencia compatible."
        confianza = "media"
        riesgo = "bajo"
        falta = []

    informe = diagnostico_de_ticket.diagnosticar(
        org_a, senales, ahora=ahora,
        concluir=lambda org_, entrada: _Veredicto())
    assert informe["leidos"] == 1, informe
    assert informe["con_hipotesis"] == 1, informe
    assert senal.datos["diagnostico_leido"] is True
    #  La labor sale del clasificador REAL corriendo sobre el snapshot del
    #  equipo (fibra -> correctivo), y queda marcada como verificada porque la
    #  sostiene una medicion y no solo el texto.
    assert senal.datos["labor"] == "correctivo", senal.datos
    assert senal.datos["labor_verificada"] is True

    # --- 4 - una persona la acepta -----------------------------------------
    PropuestaSupervisor.objects.create(
        org=org_a, tipo_senal=senal.tipo, origen_tipo="case",
        origen_id=senal.origen_id, estado=PropuestaSupervisor.ACEPTADA,
        evidencia=senal.evidencia,
    )

    # --- 5 - aparece en Despacho -------------------------------------------
    cuerpo = admin_client.get(f"{CASOS}?ficha=1").json()
    assert [c["id"] for c in cuerpo["casos"]] == [str(caso.id)], (
        "un ticket LEIDO y aprobado no llego a Despacho: el camino del texto "
        "no desemboca donde tiene que desembocar"
    )
    assert cuerpo["sin_aprobados"] is False

    # --- 6 - se despacha ---------------------------------------------------
    r = admin_client.post(CREAR, {
        "work_type_version_id": str(plantilla.id),
        "case_id": str(caso.id),
        "zona": LOCALIDAD,
    }, format="json", HTTP_IDEMPOTENCY_KEY="circuito-texto-1")
    assert r.status_code == 201, r.content
    orden = OrdenTrabajo.objects.get(pk=r.data["orden"]["id"])
    assert (orden.zona or "").strip() == LOCALIDAD

    # --- 7 - el reparto se la da a la cuadrilla de ESA labor ---------------
    cuadrilla = Cuadrilla.objects.create(
        org=org_a, nombre="Cuadrilla 1", lider=admin_profile,
        labor_habitual="correctivo")
    cuadrilla.zonas_habituales.set([zona])
    jornada_automatica.asegurar_jornadas(org_a, HOY)
    jornada = JornadaDeCuadrilla.objects.get(cuadrilla=cuadrilla, fecha=HOY)
    IntegranteDeJornada.objects.create(
        org=org_a, jornada=jornada,
        persona=PersonaDeCampo.objects.create(
            org=org_a, nombre="La Lider", profile=admin_profile),
        rol="tecnico_lider")

    propuesta = reparto.proponer(org_a, HOY)
    asignadas = {a["cuadrilla"].nombre: [o.numero for o in a["ordenes"]]
                 for a in propuesta["asignaciones"]}
    assert asignadas.get("Cuadrilla 1") == [orden.numero], (
        f"el reparto no le dio la orden a la cuadrilla. "
        f"sin_zona={[o.numero for o in propuesta['sin_zona']]} "
        f"sin_cuadrilla={[o.numero for o in propuesta['sin_cuadrilla']]} "
        f"sin_clasificar={[o.numero for o in propuesta['sin_clasificar']]}"
    )

    # --- 8 - se publica y el tecnico lo ve ---------------------------------
    r = admin_client.post("/api/campo/cuadrillas/reparto/", {
        "asignaciones": [{"jornada": str(jornada.id),
                          "ordenes": [str(orden.id)]}],
    }, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["publicadas"] == 1
    suyos = admin_client.get(f"{TRABAJOS}?solo_mios=1").json()
    numeros = [t["numero"] for t in (suyos.get("results") or [])]
    assert orden.numero in numeros, (
        f"la orden publicada no aparece en los trabajos del tecnico: {suyos}"
    )


def test_un_ticket_RECHAZADO_no_llega_a_despacho(
    admin_client, org_a, admin_profile, plantilla, zona,
    contexto_del_equipo_caido,
):
    """Rechazar es decir que NO, y tiene que seguir significando eso.

    `ESTADOS_REVISADOS` agrupa aceptada/modificada/RECHAZADA para OTRA
    pregunta: "ya la miro alguien?". Si Despacho filtrara por ese conjunto
    traeria justo las que una persona decidio que no van, y nadie lo notaria:
    la pantalla se veria MAS llena, no vacia. Un falso verde con esa forma no
    lo caza ninguna prueba que solo mire el camino feliz.
    """
    from cases.models import Case

    caso = Case.objects.create(
        org=org_a, name="No tiene internet", status="New", priority="Normal",
        is_active=True, external_service_id="6580",
        external_ticket_id="95049", provider="wisphub",
    )
    #  LOS DOS TIPOS, rechazados. Con uno solo, esta prueba se tapa con la de
    #  arriba: si alguien saca `TICKET_SIN_DIAGNOSTICO` del filtro de TIPO, el
    #  caso desaparece por el tipo y no por el estado, y la mutacion del
    #  ESTADO pasaria sin que nada se ponga rojo. Medido el 13/10/2026,
    #  aplicando las dos mutaciones juntas: solo una se cazaba.
    for tipo in (PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO,
                 PropuestaSupervisor.CASO_REQUIERE_VISITA):
        PropuestaSupervisor.objects.create(
            org=org_a, tipo_senal=tipo,
            origen_tipo="case", origen_id=str(caso.id),
            estado=PropuestaSupervisor.RECHAZADA,
        #  La evidencia NO es decorativa: `propuesta_exige_evidencia` es una
        #  restriccion de la BASE, asi que una propuesta sin ella no se puede
        #  ni insertar. Es el diseno --una propuesta sin con que sostenerla no
        #  es una propuesta-- y por eso se respeta en vez de saltearla.
            evidencia=[{"fuente": "prueba", "entidad": str(caso.id),
                        "dato": "el cliente dijo que ya se arreglo solo",
                        "visto_en": "2026-10-13T20:00:00+00:00"}],
        )

    cuerpo = admin_client.get(CASOS).json()
    assert cuerpo["casos"] == []
    #  Y se distingue de un error: "todavia nadie aprobo ninguno" dice que
    #  hacer, "no se pudo leer" dice que algo esta roto.
    assert cuerpo["sin_aprobados"] is True


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
