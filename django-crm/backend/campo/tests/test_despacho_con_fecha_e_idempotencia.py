# -*- coding: utf-8 -*-
"""
EL DESPACHO CON FECHA NO SE PIERDE DESPUES DE CREAR LA ORDEN.

EL DEFECTO, reportado por el usuario y reproducido aca
------------------------------------------------------
«cuando despacho sale asi en rojo pero llega el ticket al tecnico y en
despacho aun sigue saliendo; toca actualizar la pagina para que se quite».

Las tres mitades del sintoma son el MISMO hecho:

  1. la orden SE CREA  -- la vista termino bien
  2. al tecnico LE LLEGA -- el aviso sale tras el commit de `asignar`
  3. el supervisor ve ROJO -- algo revienta DESPUES de los dos anteriores

Lo que revienta esta fuera de la vista: `manejar_idempotencia` guarda la
respuesta en `MutacionIdempotente.respuesta_json`, que es un JSONField SIN
`encoder=DjangoJSONEncoder`. `response.data` todavia trae objetos Python, y
`_compromiso` (serializers.py) devuelve SEIS datetime/date crudos --
`programada_para`, las dos ventanas, `sla_vence_en` y el orden del dia --
porque un SerializerMethodField no pasa por la conversion de DRF. El renderer
HTTP sabe convertirlos; `json.dumps` del JSONField no.

Y en la pantalla, un `fail` deja el caso en la lista: `use:enhance` sin
callback solo refresca con exito. Por eso hay que recargar.

POR QUE SOBREVIVIO
------------------
De las nueve pruebas que mandan 'Idempotency-Key', NINGUNA despachaba con
`programada_para` (medido el 06/11/2026). Sin fecha los seis campos son None
y `json.dumps` no se queja: el camino que el supervisor usa todos los dias
era justo el unico sin cubrir.

QUE SE AFIRMA
-------------
El EFECTO sobre quien despacha: que la respuesta llegue, que la orden quede
UNA sola, y que el reintento con la misma clave devuelva lo mismo en vez de
trabarse. No que la funcion "exista" ni que el encoder este puesto -- un
encoder puesto y una respuesta que igual revienta serian verde con el sintoma
vivo.
"""

import pytest
from common.models import Profile, User
from common.serializer import OrgAwareRefreshToken
from rest_framework.test import APIClient

from campo.models import MutacionIdempotente, OrdenTrabajo, WorkType, WorkTypeVersion

pytestmark = pytest.mark.django_db

#  Con fecha: es lo que manda Despacho cuando el supervisor elige el dia, y es
#  lo que llena `programada_para`. Sin ella el defecto no aparece.
CUANDO = "2026-11-20T14:00:00+00:00"

#  LOS CONTEOS VAN SCOPEADOS A LA ORG  --  06/11/2026, auditoria de frontera.
#  Contaban `OrdenTrabajo.objects.all()`: con `--reuse-db` --la receta del
#  proyecto-- una orden commiteada por otra suite daba `assert 2 == 1` y tres
#  rojos que no significaban nada. Un rojo que no senala un defecto ensena a
#  ignorar los rojos.


@pytest.fixture
def version_a(org_a):
    wt = WorkType.objects.create(org=org_a, codigo="correctivo", nombre="Correctivo")
    return WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [], "evidencias": []},
    )


@pytest.fixture
def supervisor(org_a):
    u = User.objects.create_user(email="super-fecha@test.com", password="x")
    p = Profile.objects.create(user=u, org=org_a, role="SUPERVISOR", is_active=True)
    c = APIClient()
    t = OrgAwareRefreshToken.for_user_and_org(u, org_a, p)
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {t.access_token}")
    return c, p


def despachar(cliente, version, clave, **extra):
    """Como lo manda la pantalla: el cuerpo y la clave que arma el servidor."""
    cuerpo = {"work_type_version_id": str(version.id), "cliente_nombre": "Mario S."}
    cuerpo.update(extra)
    return cliente.post("/api/campo/trabajos/crear/", cuerpo, format="json",
                        HTTP_IDEMPOTENCY_KEY=clave)


def test_despachar_con_fecha_responde_201(supervisor, version_a):
    """EL DEFECTO: 500 con la orden ya creada y el tecnico ya avisado."""
    cli, _ = supervisor
    r = despachar(cli, version_a, "despacho:caso-1:aaa", programada_para=CUANDO)
    assert r.status_code == 201, (
        f"respondio {r.status_code}: el supervisor ve rojo aunque la orden "
        f"se creo. {getattr(r, 'data', b'')}")


def test_la_orden_queda_una_sola_y_con_su_fecha(supervisor, version_a, org_a):
    """No alcanza con no reventar: tiene que haber creado la visita."""
    cli, _ = supervisor
    despachar(cli, version_a, "despacho:caso-2:bbb", programada_para=CUANDO)
    ordenes = list(OrdenTrabajo.objects.filter(org=org_a))
    assert len(ordenes) == 1, f"quedaron {len(ordenes)} ordenes"
    assert ordenes[0].programada_para is not None


def test_el_reintento_con_la_misma_clave_no_se_traba(supervisor, version_a, org_a):
    """
    La consecuencia que mas duele: cuando el guardado revienta, la fila queda
    en PROCESANDO y el siguiente intento con la MISMA clave contesta 409
    «La operacion se esta procesando actualmente» -- para siempre, porque nadie
    la va a completar. El supervisor queda trabado sin forma de salir.
    """
    cli, _ = supervisor
    clave = "despacho:caso-3:ccc"
    primera = despachar(cli, version_a, clave, programada_para=CUANDO)
    segunda = despachar(cli, version_a, clave, programada_para=CUANDO)

    assert segunda.status_code == primera.status_code, (
        f"el reintento contesto {segunda.status_code} y el primero "
        f"{primera.status_code}: {getattr(segunda, 'data', b'')}")
    #  Y una sola orden: de eso se trata la clave.
    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1

    guardada = MutacionIdempotente.objects.get(idempotency_key=clave)
    assert guardada.estado == MutacionIdempotente.COMPLETADA, (
        f"quedo en '{guardada.estado}': toda clave repetida va a dar 409")


def test_la_respuesta_guardada_se_puede_releer(supervisor, version_a):
    """
    Lo que se guarda tiene que servir para contestar el reintento. Guardar
    `null` pasaria los de arriba y le devolveria una respuesta vacia a quien
    reintenta.
    """
    cli, _ = supervisor
    clave = "despacho:caso-4:ddd"
    despachar(cli, version_a, clave, programada_para=CUANDO)

    guardada = MutacionIdempotente.objects.get(idempotency_key=clave)
    assert guardada.respuesta_json, "se guardo vacia"
    #  La fecha sobrevive al viaje, y vuelve como texto legible.
    compromiso = guardada.respuesta_json["orden"]["compromiso"]
    assert compromiso["programada_para"], "la fecha se perdio al guardar"
    assert isinstance(compromiso["programada_para"], str)
    #  Y VUELVE EN ISO, no en `str(datetime)`.  Esta mutacion sobrevivia el
    #  06/11/2026: un encoder que mandara TODO por `str()` daba
    #  '2026-11-20 14:00:00+00:00' --con espacio-- y pasaba el isinstance de
    #  arriba, pero ningun cliente puede volver a leer eso como fecha.
    #  `fromisoformat` NO sirve para afirmarlo: desde Python 3.11 acepta
    #  cualquier separador de un caracter, asi que traga el espacio y la
    #  mutacion sobrevivia. La 'T' es lo que `new Date(...)` necesita en el
    #  navegador y en la app.
    assert "T" in compromiso["programada_para"], (
        f'no es ISO: {compromiso["programada_para"]!r}')
    from datetime import datetime
    revivida = datetime.fromisoformat(compromiso["programada_para"])
    assert revivida.year == 2026 and revivida.month == 11 and revivida.day == 20


def test_sin_fecha_sigue_andando(supervisor, version_a):
    """El control: este camino SI estaba cubierto y tiene que seguir verde."""
    cli, _ = supervisor
    r = despachar(cli, version_a, "despacho:caso-5:eee")
    assert r.status_code == 201, getattr(r, "data", b"")


def test_si_el_guardado_falla_la_clave_no_queda_trabada(
        supervisor, version_a, org_a, monkeypatch):
    """
    LA DEFENSA DE ULTIMO METRO. Si el guardado de la copia falla por lo que
    sea --no solo por un tipo raro: la base puede rechazar la fila--, la
    operacion YA tuvo efecto y no se puede deshacer. Lo unico que queda por
    decidir es si la clave sirve para repetir o queda trabada.

    Antes del 06/11/2026 el TypeError subia: la fila quedaba en PROCESANDO y
    esa clave contestaba 409 «la operacion se esta procesando» para siempre,
    porque nadie la iba a terminar nunca. Y quien despachaba veia rojo sobre
    un trabajo que ya habia salido.

    Se fuerza devolviendo algo que el JSONField no puede escribir, que es la
    unica forma de llegar a ese `except` sin tocar la base.
    """
    from campo.services import idempotencia as mod

    monkeypatch.setattr(mod, "_para_guardar", lambda datos: {"x": object()})

    cli, _ = supervisor
    clave = "despacho:caso-6:fff"
    r = despachar(cli, version_a, clave, programada_para=CUANDO)

    assert r.status_code == 201, (
        f"un fallo al guardar la copia tumbo una orden ya creada: "
        f"{r.status_code}")
    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1

    #  Y la clave quedo utilizable: el reintento no re-ejecuta ni se traba.
    guardada = MutacionIdempotente.objects.get(idempotency_key=clave)
    assert guardada.estado == MutacionIdempotente.COMPLETADA, (
        f"quedo en '{guardada.estado}': esa clave da 409 para siempre")

    segunda = despachar(cli, version_a, clave, programada_para=CUANDO)
    assert segunda.status_code != 409, "la clave quedo trabada"
    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1, "el reintento duplico la visita"

    #  Y LA RESPUESTA DEL REINTENTO TIENE QUE SERVIR. Afirmar solo que «no da
    #  409» es afirmar que el MECANISMO no traba, no que la respuesta sea
    #  utilizable: el auditor midio que con `respuesta_json=None` esto pasaba
    #  en verde devolviendo CERO bytes, y el frontend --`await
    #  response.json()`-- lo convertia en el mismo 502 rojo de siempre.
    assert segunda.content, "el reintento devolvio un cuerpo vacio"
    cuerpo = segunda.json()
    assert isinstance(cuerpo, dict) and cuerpo, "el reintento no se puede leer"


def test_el_reintento_degradado_se_puede_leer(supervisor, version_a, org_a,
                                              monkeypatch):
    """
    Lo que recibe quien reintenta cuando la copia NO se pudo guardar.

    Medido por la auditoria el 06/11/2026: guardando `None`, DRF renderiza
    `Response(None, 201)` como cero bytes y sin Content-Type, y los dos
    clientes reales lo leen como servidor roto -- Despacho muestra 502, la
    app de campo reintenta para siempre algo ya aplicado. Tiene que llegar un
    cuerpo que se pueda parsear y que diga que paso.
    """
    from campo.services import idempotencia as mod

    monkeypatch.setattr(mod, "_para_guardar", lambda datos: {"x": object()})

    cli, _ = supervisor
    clave = "despacho:caso-7:ggg"
    despachar(cli, version_a, clave, programada_para=CUANDO)
    segunda = despachar(cli, version_a, clave, programada_para=CUANDO)

    assert segunda.content, "cero bytes: el cliente lo lee como servidor roto"
    cuerpo = segunda.json()
    assert cuerpo.get("idempotencia") == "RESPUESTA_NO_GUARDADA", cuerpo
    assert cuerpo.get("detalle"), "no dice que paso"
    #  Y sigue sin duplicar, que es de lo que se trata la clave.
    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1


def test_un_campo_raro_no_se_lleva_el_cuerpo_entero(supervisor, version_a):
    """
    `_para_guardar` degrada el CAMPO, no la respuesta.

    Con `DjangoJSONEncoder` a secas, un solo valor desconocido --bytes, un
    set, un objeto de dominio-- descartaba todo el cuerpo y se caia en el
    camino degradado de arriba. El numero de la orden, que es lo unico que la
    pantalla necesita, tiene que sobrevivir igual.
    """
    from campo.services import idempotencia as mod

    guardado = mod._para_guardar(
        {"orden": {"numero": 77, "raro": {1, 2}}, "server_time": "2026-11-06"})

    assert guardado is not None, "se descarto el cuerpo entero por un campo"
    assert guardado["orden"]["numero"] == 77
    assert guardado["orden"]["raro"], "el campo raro quedo vacio"


# ==========================================================================
#  LA VISTA REVIENTA A MEDIO CAMINO  --  F2 de la auditoría del 06/11/2026
#
#  El hermano del defecto de arriba, dos líneas más arriba en el mismo
#  decorador: el paso 2 BORRABA la fila ante cualquier excepción, y el
#  reintento con la misma clave creaba una SEGUNDA orden con un SEGUNDO aviso.
#  Medido por el auditor: `ordenes = 2`, `numeros = [2, 1]`, una sola clave.
#
#  Los dos pasos sostenían supuestos opuestos sobre el mismo hecho: el 3 dice
#  «ya hubo efecto, nunca relanzar»; el 2 decía «reventó, no pasó nada».
# ==========================================================================

def _revienta_al_responder(monkeypatch):
    """La orden ya está creada y el aviso ya salió; truena al armar la
    respuesta. Es exactamente dónde vivía el TypeError de los datetime."""
    from campo import despacho_views

    def bomba(*a, **k):
        raise RuntimeError("revento al armar la respuesta")

    monkeypatch.setattr(despacho_views, "OrdenTrabajoDetailSerializer", bomba)


def test_el_reintento_no_crea_una_segunda_visita(supervisor, version_a, org_a,
                                                 monkeypatch):
    """EL DEFECTO: dos órdenes y dos avisos con una sola Idempotency-Key."""
    cli, _ = supervisor
    clave = "despacho:caso-8:hhh"

    _revienta_al_responder(monkeypatch)
    with pytest.raises(RuntimeError):
        despachar(cli, version_a, clave, programada_para=CUANDO)
    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1

    #  La vista vuelve a andar: es el reintento de quien vio el error.
    monkeypatch.undo()
    segunda = despachar(cli, version_a, clave, programada_para=CUANDO)

    assert OrdenTrabajo.objects.filter(org=org_a).count() == 1, (
        "el reintento creó una SEGUNDA visita con la misma clave")


def test_el_reintento_dice_que_el_efecto_es_incierto(supervisor, version_a,
                                                     org_a, monkeypatch):
    """
    No alcanza con no duplicar: quien reintenta tiene que entender por qué no
    le llegó su orden. Un 409 mudo manda a crear una visita a mano -- que es
    el duplicado, por otra puerta.
    """
    cli, _ = supervisor
    clave = "despacho:caso-9:iii"

    _revienta_al_responder(monkeypatch)
    with pytest.raises(RuntimeError):
        despachar(cli, version_a, clave, programada_para=CUANDO)
    monkeypatch.undo()

    segunda = despachar(cli, version_a, clave, programada_para=CUANDO)
    assert segunda.status_code == 409, segunda.status_code
    assert segunda.content, "cero bytes: el cliente lo lee como servidor roto"
    assert segunda.json().get("error") == "EFECTO_INCIERTO", segunda.json()
    assert "Revisá" in segunda.json().get("detalle", ""), "no dice qué hacer"


def test_la_clave_no_queda_en_procesando(supervisor, version_a, monkeypatch):
    """
    Dejarla en PROCESANDO también evita el duplicado, pero con el 409 ambiguo
    de «se está procesando»: una operación en curso y una abandonada se leen
    igual, y nadie la va a terminar nunca.
    """
    cli, _ = supervisor
    clave = "despacho:caso-10:jjj"

    _revienta_al_responder(monkeypatch)
    with pytest.raises(RuntimeError):
        despachar(cli, version_a, clave, programada_para=CUANDO)

    fila = MutacionIdempotente.objects.get(idempotency_key=clave)
    assert fila.estado == MutacionIdempotente.COMPLETADA, fila.estado


def test_una_peticion_rechazada_deja_la_clave_libre(supervisor, org_a):
    """
    EL CONTROL, y es la mitad que no se puede romper al arreglar la otra.

    Un 404 --una plantilla que no existe-- sale de validar: no hubo efecto, y
    la clave tiene que quedar libre. La app de campo deriva sus claves de ids
    locales, no del cuerpo, así que reintenta con la MISMA clave; negarle ese
    reintento dejaría trabado un trabajo que nunca se hizo.
    """
    import uuid

    cli, _ = supervisor
    clave = "despacho:caso-11:kkk"

    class Falsa:
        id = uuid.uuid4()

    primera = despachar(cli, Falsa, clave, programada_para=CUANDO)
    assert primera.status_code == 404, primera.status_code
    assert not MutacionIdempotente.objects.filter(
        idempotency_key=clave).exists(), "la clave quedó tomada sin efecto"
