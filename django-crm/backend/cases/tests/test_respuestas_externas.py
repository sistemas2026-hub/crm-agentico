# -*- coding: utf-8 -*-
"""
El endpoint que copia el hilo del proveedor: la unica puerta de escritura nueva.

    uv run pytest cases/tests/test_respuestas_externas.py --no-cov -v

POR QUE EXISTE ESTE ARCHIVO
---------------------------
Porque no existia. El endpoint entro a produccion con autenticacion,
aislamiento por organizacion, lista blanca de campos, tope de lote, upsert por
huella y escritura a la base -- y cero pruebas. Lo unico que lo respaldaba era
que en produccion habia escrito 170 filas sin duplicar, que demuestra el camino
feliz de un llamante amistoso y nada mas.

Lo que se prueba aca es el llamante HOSTIL y el DISTRAIDO: el que manda el caso
de otra empresa, el que repite el lote, el que manda mil respuestas, el que
manda 'org' en el payload, el que manda basura donde va una fecha.

EL INVARIANTE QUE NO SE NEGOCIA
-------------------------------
Este endpoint AGREGA filas a un hilo. No toca el Case: ni su estado, ni su
prioridad, ni su descripcion, ni a quien esta asignado. Si alguna de esas cosas
cambia despues de llamar aca, es un bug, y hay una prueba por cada una.
"""

import uuid

import pytest

from cases.models import Case, RespuestaExterna

pytestmark = pytest.mark.django_db


def _url(caso):
    return f"/api/importacion/casos/{caso.id}/respuestas/"


def _respuesta(**extra):
    base = {
        "huella": "a" * 64,
        "autor_nombre": "JULIO MORENO",
        "autor_usuario": "tecnico3@rapilink-sas",
        "cuerpo": "Se reviso la acometida.",
        "creada_en_proveedor": "2026-09-12T09:34:25-05:00",
        "archivos": 0,
    }
    base.update(extra)
    return base


@pytest.fixture
def importado(admin_user, org_a):
    """Un caso ya importado, que es el unico sobre el que esto puede escribir."""
    return Case.objects.create(
        name="No Tiene Internet", status="New", priority="Normal",
        org=org_a, created_by=admin_user,
        provider="wisphub", external_ticket_id="92321",
        external_service_id="2987", external_status="Nuevo",
        description="Reportado por telefono.",
    )


# =========================================================================
#  1. QUIEN PUEDE LLAMAR
# =========================================================================

def test_sin_autenticacion_no_entra(client, importado):
    r = client.post(_url(importado),
                    {"provider": "wisphub", "respuestas": []},
                    content_type="application/json")
    assert r.status_code in (401, 403), r.content
    assert RespuestaExterna.objects.count() == 0


def test_sin_contexto_de_organizacion_no_entra(importado, admin_user):
    """Un token valido SIN organizacion resuelta no puede escribir.

    'HasOrgContext' separa "este usuario existe" de "este usuario esta actuando
    dentro de una empresa". Sin eso 'org' seria None y la fila quedaria sin
    dueño, alcanzable desde cualquier organizacion.
    """
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    c = APIClient()
    token = RefreshToken.for_user(admin_user)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    r = c.post(_url(importado), {"provider": "wisphub", "respuestas": []},
               format="json")
    assert r.status_code in (400, 401, 403), r.content
    assert RespuestaExterna.objects.count() == 0


# =========================================================================
#  2. SOBRE QUE CASO
# =========================================================================

def test_el_caso_propio_recibe_el_hilo(admin_client, importado, org_a):
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": [_respuesta()]},
                          format="json")
    assert r.status_code == 200, r.content
    assert r.json() == {"nuevas": 1, "ya_estaban": 0, "total": 1}

    fila = RespuestaExterna.objects.get()
    assert fila.case_id == importado.id
    assert fila.org_id == org_a.id, "la fila tiene que quedar en la org del caso"
    assert fila.provider == "wisphub"


def test_el_caso_ajeno_es_indistinguible_de_uno_inexistente(org_b_client, importado):
    """404 en los dos casos, y el MISMO 404.

    Si el caso ajeno diera 403 y el inexistente 404, la diferencia seria un
    oraculo: pidiendo UUIDs al azar se podrian enumerar los casos de las otras
    empresas.
    """
    ajeno = org_b_client.post(
        _url(importado), {"provider": "wisphub", "respuestas": [_respuesta()]},
        format="json")
    inexistente = org_b_client.post(
        f"/api/importacion/casos/{uuid.uuid4()}/respuestas/",
        {"provider": "wisphub", "respuestas": [_respuesta()]}, format="json")

    assert ajeno.status_code == 404, ajeno.content
    assert inexistente.status_code == 404, inexistente.content
    assert ajeno.json() == inexistente.json(), (
        "el cuerpo tiene que ser identico: si no, distingue existe de no existe")
    assert RespuestaExterna.objects.count() == 0


def test_un_caso_nativo_sin_proveedor_no_recibe_hilo(admin_client, admin_user, org_a):
    nativo = Case.objects.create(name="Nacido en Dexter", status="New",
                                 priority="Normal", org=org_a,
                                 created_by=admin_user)
    r = admin_client.post(_url(nativo),
                          {"provider": "wisphub", "respuestas": [_respuesta()]},
                          format="json")
    assert r.status_code == 400, r.content
    assert RespuestaExterna.objects.count() == 0


def test_el_hilo_de_otro_proveedor_se_rechaza(admin_client, importado):
    r = admin_client.post(_url(importado),
                          {"provider": "otro_isp", "respuestas": [_respuesta()]},
                          format="json")
    assert r.status_code == 400, r.content
    assert RespuestaExterna.objects.count() == 0


# =========================================================================
#  3. QUE SE ACEPTA EN EL CUERPO
# =========================================================================

def test_falta_provider(admin_client, importado):
    r = admin_client.post(_url(importado), {"respuestas": []}, format="json")
    assert r.status_code == 400


def test_respuestas_tiene_que_ser_lista(admin_client, importado):
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": {"a": 1}},
                          format="json")
    assert r.status_code == 400


def test_lista_vacia_es_valida_y_no_escribe_nada(admin_client, importado):
    """Un ticket sin respuestas es normal, no un error.

    La reconciliacion manda el hilo de cada caso que alcanza y la mayoria no
    tiene ninguna. Si esto fuera 400, cada pasada del reloj registraria decenas
    de fallos que no son fallos.
    """
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": []}, format="json")
    assert r.status_code == 200, r.content
    assert r.json() == {"nuevas": 0, "ya_estaban": 0, "total": 0}


def test_falta_la_huella(admin_client, importado):
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(huella="")]},
        format="json")
    assert r.status_code == 400


@pytest.mark.parametrize("extra", [
    {"org": "11111111-1111-1111-1111-111111111111"},
    {"case": "11111111-1111-1111-1111-111111111111"},
    {"created_by": "11111111-1111-1111-1111-111111111111"},
    {"updated_by": "11111111-1111-1111-1111-111111111111"},
    {"id": "11111111-1111-1111-1111-111111111111"},
    {"provider": "otro"},
    {"created_at": "2020-01-01T00:00:00Z"},
])
def test_no_se_acepta_nada_que_deba_salir_del_contexto(admin_client, importado, extra):
    """'org', 'case' y la auditoria se derivan de la sesion y de la URL.

    Aceptarlos del payload es como se cruza un tenant: el llamante diria de que
    empresa es la fila, en vez de decirlo quien lo autentico.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(**extra)]},
        format="json")
    assert r.status_code == 400, f"{extra} entro: {r.content}"
    assert RespuestaExterna.objects.count() == 0


def test_cada_respuesta_tiene_que_ser_un_objeto(admin_client, importado):
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": ["texto suelto"]},
                          format="json")
    assert r.status_code == 400


# =========================================================================
#  4. TAMAÑOS Y BASURA
# =========================================================================

def test_mas_de_doscientas_se_rechaza(admin_client, importado):
    filas = [_respuesta(huella=f"{i:064d}") for i in range(201)]
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": filas},
                          format="json")
    assert r.status_code == 400
    assert RespuestaExterna.objects.count() == 0, (
        "el tope se comprueba ANTES de escribir: si esto falla, el rechazo "
        "llega despues de haber metido doscientas filas")


def test_doscientas_justas_entran(admin_client, importado):
    filas = [_respuesta(huella=f"{i:064d}") for i in range(200)]
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": filas},
                          format="json")
    assert r.status_code == 200, r.content
    assert r.json()["nuevas"] == 200


def test_un_cuerpo_desmedido_no_se_guarda_entero(admin_client, importado):
    """Hay un tope de texto, y no es "lo que quepa en la base".

    El motor acota la descripcion a 800 caracteres, pero este endpoint es una
    puerta del CRM y no puede suponer que quien llama sea el motor. Sin tope,
    una respuesta de 50 MB entra y queda.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(cuerpo="x" * 100_000)]},
        format="json")
    if r.status_code == 200:
        fila = RespuestaExterna.objects.get()
        assert len(fila.cuerpo) <= 20_000, (
            f"se guardaron {len(fila.cuerpo)} caracteres sin tope alguno")
    else:
        assert r.status_code == 400


def test_una_huella_desmedida_no_rompe(admin_client, importado):
    """La huella es un sha256 de 64 caracteres; mas que eso es basura.

    La columna es CharField(64): sin validacion previa PostgreSQL lo rechaza
    con DataError, que NO es IntegrityError, asi que el except de la vista no
    lo atrapa y sale un 500.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(huella="z" * 500)]},
        format="json")
    assert r.status_code == 400, f"devolvio {r.status_code}: {r.content[:200]}"


@pytest.mark.parametrize("valor", ["no soy un numero", -1, 999999, [1, 2], 1.5])
def test_archivos_con_basura_no_revienta(admin_client, importado, valor):
    """'archivos' es un contador. Lo que llegue y no lo sea, se rechaza.

    'int("no soy un numero")' lanza ValueError, que nadie atrapa: 500. Un
    negativo o un numero enorme choca contra PositiveSmallIntegerField con
    DataError, que tampoco es IntegrityError.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(archivos=valor)]},
        format="json")
    assert r.status_code in (200, 400), (
        f"archivos={valor!r} devolvio {r.status_code}: {r.content[:200]}")
    if r.status_code == 200:
        assert RespuestaExterna.objects.get().archivos >= 0


@pytest.mark.parametrize("fecha", [
    "no es una fecha", "2026-13-45T99:99:99", 12345, {"a": 1},
])
def test_una_fecha_ilegible_no_revienta(admin_client, importado, fecha):
    """Una fecha que no se puede leer deja la fila sin fecha, no un 500."""
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(creada_en_proveedor=fecha)]},
        format="json")
    assert r.status_code in (200, 400), (
        f"fecha={fecha!r} devolvio {r.status_code}: {r.content[:200]}")


def test_una_fecha_sin_zona_se_rechaza(admin_client, importado):
    """UN INSTANTE SIN ZONA NO ES UN INSTANTE, y esto costo cinco horas.

    WispHub manda '09/12/2026 09:34:25', hora local, sin zona. Guardarla tal
    cual en una columna con USE_TZ=True y TIME_ZONE='UTC' la interpreta como
    UTC: una respuesta escrita a las 09:34 de Bogota queda archivada como las
    09:34 de Londres.

    Medido en produccion el 12/09/2026 sobre dos barridos seguidos: el de las
    09:19 de Bogota dejo la respuesta mas nueva sellada a las 09:19 UTC, y el
    de las 10:20 a las 10:20 UTC. Dos coincidencias al segundo -- y una
    respuesta no puede haberse creado cinco horas antes del barrido que fue el
    primero en verla.

    La version anterior devolvia la fecha sin zona "para que quien la muestre
    decida". Nadie decidio: decidio el default de Django. Ahora se rechaza.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(creada_en_proveedor="2026-09-12T09:34:25")]},
        format="json")
    assert r.status_code == 400, r.content
    assert r.json()["error"] == "FECHA_SIN_ZONA", r.content
    assert RespuestaExterna.objects.count() == 0


def test_la_fecha_con_zona_se_guarda_en_el_instante_correcto(admin_client,
                                                              importado):
    """09:34 de Bogota son las 14:34 UTC, no las 09:34 UTC."""
    from datetime import timezone as tz, timedelta

    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(creada_en_proveedor="2026-09-12T09:34:25-05:00")]},
        format="json")
    assert r.status_code == 200, r.content

    fila = RespuestaExterna.objects.get()
    en_utc = fila.creada_en_proveedor.astimezone(tz.utc)
    assert (en_utc.hour, en_utc.minute) == (14, 34), (
        f"quedo en {en_utc:%H:%M} UTC; 09:34 de Bogota son las 14:34 UTC")
    bogota = fila.creada_en_proveedor.astimezone(tz(timedelta(hours=-5)))
    assert (bogota.hour, bogota.minute) == (9, 34)


def test_sin_fecha_la_fila_se_guarda_igual(admin_client, importado):
    """Mejor sin fecha que con una inventada.

    Hay tickets que no informan zona en 'fecha_creacion', y de esos el motor no
    puede deducir el huso de sus respuestas. La respuesta se guarda igual: el
    texto y el autor valen, y la fecha ausente se dice como ausente.
    """
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(creada_en_proveedor=None)]},
        format="json")
    assert r.status_code == 200, r.content
    assert RespuestaExterna.objects.get().creada_en_proveedor is None


# =========================================================================
#  5. REPETICION: LO QUE EL RELOJ HACE CADA HORA
# =========================================================================

def test_el_mismo_lote_dos_veces_no_duplica(admin_client, importado):
    cuerpo = {"provider": "wisphub",
              "respuestas": [_respuesta(huella=f"{i:064d}") for i in range(5)]}

    primero = admin_client.post(_url(importado), cuerpo, format="json")
    segundo = admin_client.post(_url(importado), cuerpo, format="json")

    assert primero.json() == {"nuevas": 5, "ya_estaban": 0, "total": 5}
    assert segundo.json() == {"nuevas": 0, "ya_estaban": 5, "total": 5}
    assert RespuestaExterna.objects.count() == 5


def test_el_lote_crece_y_solo_entra_lo_nuevo(admin_client, importado):
    """Lo que pasa de verdad cada hora: el hilo viejo mas una respuesta nueva."""
    viejas = [_respuesta(huella=f"{i:064d}") for i in range(5)]
    admin_client.post(_url(importado),
                      {"provider": "wisphub", "respuestas": viejas}, format="json")

    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": viejas + [_respuesta(huella="f" * 64)]},
        format="json")
    assert r.json() == {"nuevas": 1, "ya_estaban": 5, "total": 6}
    assert RespuestaExterna.objects.count() == 6


def test_huellas_repetidas_dentro_del_mismo_lote(admin_client, importado):
    """El proveedor manda la misma respuesta dos veces en la misma tanda."""
    una = _respuesta(huella="c" * 64)
    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": [una, una, una]},
                          format="json")
    assert r.status_code == 200, r.content
    assert r.json() == {"nuevas": 1, "ya_estaban": 2, "total": 3}
    assert RespuestaExterna.objects.count() == 1


def test_la_misma_huella_con_otro_contenido_no_pisa_lo_guardado(admin_client,
                                                                importado):
    """GANA EL PRIMERO, y es una decision, no un accidente.

    La huella es sha256 de fecha+autor+cuerpo: si el cuerpo cambia, cambia la
    huella y es otra fila. Que llegue la MISMA huella con otro contenido
    significa que el proveedor reescribio algo bajo el mismo sello, o que
    alguien esta probando si por ahi se edita historia ajena.

    Esto es un registro de lo que se dijo. No se reescribe.
    """
    admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(huella="d" * 64, cuerpo="lo que se dijo")]},
        format="json")

    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(huella="d" * 64,
                                   cuerpo="lo que alguien quiere que diga",
                                   autor_nombre="OTRO")]},
        format="json")
    assert r.status_code == 200
    assert r.json()["ya_estaban"] == 1

    fila = RespuestaExterna.objects.get()
    assert fila.cuerpo == "lo que se dijo", "se reescribio historia"
    assert fila.autor_nombre == "JULIO MORENO"


def test_el_mismo_hilo_en_dos_empresas_no_se_estorba(admin_client, org_b_client,
                                                      importado, user_b, org_b):
    """La misma huella sobre casos de empresas distintas son dos filas."""
    suyo = Case.objects.create(
        name="No Tiene Internet", status="New", priority="Normal",
        org=org_b, created_by=user_b, provider="wisphub",
        external_ticket_id="92321", external_service_id="2987")

    a = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": [_respuesta()]},
                          format="json")
    b = org_b_client.post(_url(suyo),
                          {"provider": "wisphub", "respuestas": [_respuesta()]},
                          format="json")
    assert a.json()["nuevas"] == 1
    assert b.json()["nuevas"] == 1, "la huella de otra empresa lo bloqueo"
    assert RespuestaExterna.objects.count() == 2


# =========================================================================
#  6. FALLO A MITAD DEL LOTE
# =========================================================================

def test_una_fila_invalida_no_deja_el_lote_a_medias(admin_client, importado):
    """El contrato es TODO O NADA.

    Sin esto, una fila mala en la posicion 5 de 8 devuelve 400 con las cuatro
    primeras YA escritas: el llamante lee "fallo" y reintenta, y lo que
    escribio queda. Peor, desde afuera no hay forma de saber cuantas pasaron.
    """
    filas = [_respuesta(huella=f"{i:064d}") for i in range(4)]
    filas.append(_respuesta(huella="e" * 64, campo_que_no_existe="x"))
    filas += [_respuesta(huella=f"{i:064d}") for i in range(5, 8)]

    r = admin_client.post(_url(importado),
                          {"provider": "wisphub", "respuestas": filas},
                          format="json")
    assert r.status_code == 400, r.content
    assert RespuestaExterna.objects.count() == 0, (
        f"quedaron {RespuestaExterna.objects.count()} filas de un lote rechazado")


# =========================================================================
#  7. EL CASE NO SE TOCA
# =========================================================================

def test_el_case_no_cambia_en_nada(admin_client, importado):
    """El invariante de la fase, campo por campo."""
    antes = {
        "status": importado.status,
        "priority": importado.priority,
        "name": importado.name,
        "description": importado.description,
        "external_status": importado.external_status,
        "closed_on": importado.closed_on,
        "asignados": list(importado.assigned_to.values_list("id", flat=True)),
    }

    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub",
         "respuestas": [_respuesta(huella=f"{i:064d}") for i in range(3)]},
        format="json")
    assert r.status_code == 200, r.content

    importado.refresh_from_db()
    assert importado.status == antes["status"]
    assert importado.priority == antes["priority"]
    assert importado.name == antes["name"]
    assert importado.description == antes["description"]
    assert importado.external_status == antes["external_status"]
    assert importado.closed_on == antes["closed_on"]
    assert (list(importado.assigned_to.values_list("id", flat=True))
            == antes["asignados"])


def test_el_cuerpo_se_guarda_tal_cual_sin_interpretarlo(admin_client, importado):
    """Lo que escribio el operador se guarda literal.

    Escapar al GUARDAR destruiria el dato y ademas no protege: quien lo lea por
    la API lo recibe igual. El escapado es de quien RENDERIZA. Esta prueba fija
    que aca no se hace nada raro con el texto.
    """
    hostil = "<script>alert(1)</script> <img src=x onerror=alert(2)>"
    r = admin_client.post(
        _url(importado),
        {"provider": "wisphub", "respuestas": [_respuesta(cuerpo=hostil)]},
        format="json")
    assert r.status_code == 200, r.content
    assert RespuestaExterna.objects.get().cuerpo == hostil
