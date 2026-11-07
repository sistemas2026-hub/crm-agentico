# -*- coding: utf-8 -*-
"""
================================================================================
 LAS PLANTILLAS SE EDITAN DESDE LA PLATAFORMA, Y LO QUE SALE LA APP LO ENTIENDE
================================================================================

Hasta el 13/10/2026 una plantilla solo se creaba por el admin de Django,
escribiendo JSON. `campo/plantillas.py` la arma desde una definicion guiada.
Se afirma sobre el EFECTO:

  A  todo el catalogo de partida compone, y solo con lo que la app y el
     backend entienden IGUAL (la lista medida en campo/plantillas.py)
  B  crear desde el catalogo deja una version PUBLICADA, con hash, que
     DESPACHO ofrece y con la que se crea una ORDEN -- la cadena entera, por
     los endpoints de verdad
  C  publicar cambia lo que viene, NO lo que ya salio: la orden vieja conserva
     su version
  D  publicar lo mismo no crea otra version
  E  los ids sobreviven a un cambio de titulo: lo anotado ayer no queda huerfano
  F  lo que el editor no maneja no se pisa en silencio
  G  lo que se rechaza, se rechaza con texto para quien edita
  H  permisos y aislamiento entre empresas
  I  el backend acepta lo que el tecnico anota en cada tipo

    pytest campo/tests/test_plantillas_editables.py
================================================================================
"""

import pytest

from campo import plantillas as P
from campo.models import OrdenTrabajo, WorkType, WorkTypeVersion
from campo.services.validador import validar_campos_tecnicos

pytestmark = pytest.mark.django_db

LISTA = "/api/campo/plantillas/"
DESPACHO = "/api/campo/plantillas-de-trabajo/"
CREAR_ORDEN = "/api/campo/trabajos/crear/"


def _una(pk):
    return f"/api/campo/plantillas/{pk}/"


def _publicar(pk):
    return f"/api/campo/plantillas/{pk}/publicar/"


#: Lo que la app dibuja y valida igual que el backend. Ver la cabecera de
#: campo/plantillas.py: cualquier otra cosa deja ordenes cerradas en el
#: telefono y trabadas en el servidor.
TIPOS_SEGUROS = {"texto", "decimal", "seleccion"}


def _definicion_minima(**extra):
    return {"campos": [{"titulo": "Que se hizo", "tipo": "texto"}],
            "evidencias": [{"titulo": "Trabajo terminado"}], **extra}


# ---------------------------------------------------------------------------
# A · el catalogo de partida
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base", P.CATALOGO_BASE, ids=lambda b: b["codigo"])
def test_a_cada_plantilla_del_catalogo_compone_con_tipos_seguros(base):
    esquema = P.componer(P.definicion_de_base(base))

    for c in esquema["campos"]:
        assert c["tipo"] in TIPOS_SEGUROS, c
        assert "regex" not in c["reglas"], c
        if c["tipo"] == "texto":
            assert not {"min", "max"} & set(c["reglas"]), c
        if c["tipo"] == "seleccion":
            assert len(c["reglas"]["options"]) >= 2, c
    for e in esquema["evidencias"]:
        assert e["tipo"] == "foto", e
    assert base["labor"] in dict(WorkType.LABORES)
    #  Algo que registrar: una plantilla vacia se cierra con un toque.
    assert esquema["campos"] or esquema["evidencias"]


def test_a2_los_codigos_del_catalogo_no_se_repiten():
    codigos = [b["codigo"] for b in P.CATALOGO_BASE]
    assert len(codigos) == len(set(codigos))


def test_a3_el_checklist_viaja_como_seleccion_y_vuelve_como_checklist():
    """No como booleano: la app da por completo un booleano sin tocar."""
    esquema = P.componer({"campos": [{"titulo": "Probado", "tipo": "checklist"}]})
    c = esquema["campos"][0]
    assert c["tipo"] == "seleccion"
    assert c["reglas"]["options"] == P.OPCIONES_CHECKLIST
    assert c["reglas"]["required"] is True

    definicion, motivos = P.leer_definicion(esquema)
    assert motivos == []
    assert definicion["campos"][0]["tipo"] == "checklist"


# ---------------------------------------------------------------------------
# B · la cadena: crear -> despacho -> orden -> lo que recibe la app
# ---------------------------------------------------------------------------

def test_b_crear_desde_el_catalogo_llega_a_despacho_y_a_una_orden(admin_client, org_a):
    r = admin_client.post(LISTA, {"base": "retiro_equipos"}, format="json")
    assert r.status_code == 201, r.content
    tipo_id = r.json()["id"]

    v = WorkTypeVersion.objects.get(work_type_id=tipo_id)
    assert v.estado == WorkTypeVersion.PUBLICADA
    assert v.version == 1 and v.schema_version == 1
    assert v.schema_hash and v.publicada_en

    ofrecidas = admin_client.get(DESPACHO).json()["plantillas"]
    mia = next(p for p in ofrecidas if p["codigo"] == "retiro_equipos")
    assert mia["labor"] == "trabajos"
    assert mia["id"] == str(v.id)

    r = admin_client.post(CREAR_ORDEN, {
        "work_type_version_id": mia["id"], "cliente_nombre": "Cliente prueba",
        "zona": "CENTRO"}, format="json")
    assert r.status_code in (200, 201), r.content
    orden = OrdenTrabajo.objects.get(org=org_a)
    assert orden.tipo_trabajo_version_id == v.id

    #  Y lo que la app recibe es el esquema que se compuso, no otro.
    detalle = admin_client.get(f"/api/campo/trabajos/{orden.id}/").json()
    assert detalle["schema"] == v.esquema


def test_b2_el_catalogo_dice_cual_ya_se_adopto(admin_client):
    admin_client.post(LISTA, {"base": "servicio_tv"}, format="json")
    cuerpo = admin_client.get(LISTA).json()
    adoptadas = {c["codigo"] for c in cuerpo["catalogo"] if c["adoptada"]}
    assert adoptadas == {"servicio_tv"}
    assert [p["codigo"] for p in cuerpo["propias"]] == ["servicio_tv"]


def test_b3_adoptar_dos_veces_es_409_y_no_crea_nada(admin_client, org_a):
    admin_client.post(LISTA, {"base": "servicio_tv"}, format="json")
    r = admin_client.post(LISTA, {"base": "servicio_tv"}, format="json")
    assert r.status_code == 409
    assert r.json()["error"] == "YA_EXISTE"
    assert WorkType.objects.filter(org=org_a).count() == 1


def test_b4_crear_desde_cero(admin_client):
    r = admin_client.post(LISTA, {"nombre": "Instalacion de camara",
                                  "labor": "trabajos",
                                  "definicion": _definicion_minima()},
                          format="json")
    assert r.status_code == 201, r.content
    assert r.json()["codigo"] == "instalacion_de_camara"


# ---------------------------------------------------------------------------
# C · publicar cambia lo que viene, no lo que ya salio
# ---------------------------------------------------------------------------

def test_c_la_orden_vieja_conserva_su_version(admin_client, org_a):
    tipo_id = admin_client.post(LISTA, {"base": "trabajo_general"},
                                format="json").json()["id"]
    v1 = WorkTypeVersion.objects.get(work_type_id=tipo_id)
    admin_client.post(CREAR_ORDEN, {"work_type_version_id": str(v1.id)},
                      format="json")

    definicion = admin_client.get(_una(tipo_id)).json()["definicion"]
    definicion["evidencias"].append({"titulo": "Fachada", "obligatorio": False})
    r = admin_client.post(_publicar(tipo_id), {"definicion": definicion},
                          format="json")
    assert r.status_code == 200, r.content
    assert r.json()["cambio"] is True
    assert r.json()["version"] == 2
    #  Se avisa cuantas ordenes NO cambian.
    assert r.json()["ordenes_vivas"] == 1

    orden = OrdenTrabajo.objects.get(org=org_a)
    assert orden.tipo_trabajo_version_id == v1.id
    ofrecida = next(p for p in admin_client.get(DESPACHO).json()["plantillas"]
                    if p["codigo"] == "trabajo_general")
    assert ofrecida["version"] == 2


# ---------------------------------------------------------------------------
# D · publicar lo mismo no ensucia la historia
# ---------------------------------------------------------------------------

def test_d_publicar_sin_cambios_no_crea_version(admin_client):
    tipo_id = admin_client.post(LISTA, {"base": "trabajo_general"},
                                format="json").json()["id"]
    definicion = admin_client.get(_una(tipo_id)).json()["definicion"]

    r = admin_client.post(_publicar(tipo_id), {"definicion": definicion,
                                               "nombre": "Trabajo varios"},
                          format="json")
    assert r.json()["cambio"] is False
    assert r.json()["version"] == 1
    #  El nombre SI cambia: es del tipo, no de la version.
    assert r.json()["nombre"] == "Trabajo varios"
    assert WorkTypeVersion.objects.filter(work_type_id=tipo_id).count() == 1


def test_d2_tampoco_sobre_una_version_que_salio_de_publicar(admin_client):
    """La v1 la crea `crear()`; la v2, `publicar()`. Sin esta prueba, una v2
    sellada SIN hash pasaba: la comparacion nunca la reconocia como igual y
    cada «publicar» sin cambios creaba otra version (mutacion medida el
    13/10/2026, sobrevivia a todo lo demas)."""
    tipo_id = admin_client.post(LISTA, {"base": "trabajo_general"},
                                format="json").json()["id"]
    definicion = admin_client.get(_una(tipo_id)).json()["definicion"]
    definicion["evidencias"].append({"titulo": "Fachada", "obligatorio": False})

    assert admin_client.post(_publicar(tipo_id), {"definicion": definicion},
                             format="json").json()["version"] == 2
    r = admin_client.post(_publicar(tipo_id), {"definicion": definicion},
                          format="json").json()
    assert r["cambio"] is False
    assert r["version"] == 2
    assert WorkTypeVersion.objects.get(work_type_id=tipo_id, version=2).schema_hash


# ---------------------------------------------------------------------------
# E · ids estables
# ---------------------------------------------------------------------------

def test_e_renombrar_un_dato_conserva_su_id(admin_client):
    tipo_id = admin_client.post(LISTA, {"base": "trabajo_general"},
                                format="json").json()["id"]
    definicion = admin_client.get(_una(tipo_id)).json()["definicion"]
    id_antes = definicion["campos"][0]["id"]
    definicion["campos"][0]["titulo"] = "Que trabajo se hizo en la casa"

    admin_client.post(_publicar(tipo_id), {"definicion": definicion},
                      format="json")
    despues = admin_client.get(_una(tipo_id)).json()["definicion"]
    assert despues["campos"][0]["id"] == id_antes


def test_e2_dos_datos_con_el_mismo_titulo_no_comparten_id():
    esquema = P.componer({"campos": [{"titulo": "Serial"}, {"titulo": "Serial"}]})
    ids = [c["id"] for c in esquema["campos"]]
    assert len(set(ids)) == 2


# ---------------------------------------------------------------------------
# F · lo armado a mano no se pisa
# ---------------------------------------------------------------------------

def test_f_una_plantilla_con_booleano_no_se_edita_ni_se_pisa(admin_client, org_a):
    tipo = WorkType.objects.create(org=org_a, codigo="vieja", nombre="Vieja")
    WorkTypeVersion.objects.create(
        work_type=tipo, version=1, estado=WorkTypeVersion.PUBLICADA,
        esquema={"campos": [{"id": "ok", "titulo": "Quedo bien",
                             "tipo": "booleano", "reglas": {"required": True}}],
                 "evidencias": []})

    cuerpo = admin_client.get(_una(tipo.id)).json()
    assert cuerpo["editable"] is False
    assert cuerpo["definicion"] is None
    assert any("booleano" in m for m in cuerpo["por_que_no"])

    r = admin_client.post(_publicar(tipo.id),
                          {"definicion": _definicion_minima()}, format="json")
    assert r.status_code == 409
    assert WorkTypeVersion.objects.filter(work_type=tipo).count() == 1


def test_f2_texto_con_minimo_tampoco_se_abre():
    """La app compara el numero; el backend, el largo."""
    _, motivos = P.leer_definicion({"campos": [
        {"id": "s", "titulo": "Serial", "tipo": "texto",
         "reglas": {"required": True, "min": 5}}]})
    assert motivos


# ---------------------------------------------------------------------------
# G · lo que se rechaza
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("definicion,codigo", [
    ({"campos": [{"titulo": "Ok", "tipo": "booleano"}]}, "TIPO_NO_PERMITIDO"),
    ({"campos": [{"titulo": "Cuando", "tipo": "fecha"}]}, "TIPO_NO_PERMITIDO"),
    ({"campos": [{"titulo": "Uno", "tipo": "seleccion", "opciones": ["Si"]}]},
     "FALTAN_OPCIONES"),
    ({"campos": [{"titulo": "Pot", "tipo": "numero", "min": 5, "max": 1}]},
     "RANGO_INVERTIDO"),
    ({"campos": [{"titulo": "", "tipo": "texto"}]}, "FALTA_TITULO"),
    ({"campos": [], "evidencias": []}, "PLANTILLA_VACIA"),
    ({"campos": [{"titulo": "x"}], "duracion_estimada_minutos": 0},
     "DURACION_INVALIDA"),
])
def test_g_lo_que_no_se_puede_publicar(admin_client, definicion, codigo):
    tipo_id = admin_client.post(LISTA, {"base": "trabajo_general"},
                                format="json").json()["id"]
    r = admin_client.post(_publicar(tipo_id), {"definicion": definicion},
                          format="json")
    assert r.status_code == 400
    assert r.json()["error"] == codigo
    assert r.json()["detalle"]
    assert WorkTypeVersion.objects.filter(work_type_id=tipo_id).count() == 1


# ---------------------------------------------------------------------------
# H · permisos y aislamiento
# ---------------------------------------------------------------------------

def test_h_sin_rol_de_gestion_se_lee_pero_no_se_escribe(user_client, org_a):
    assert user_client.get(LISTA).status_code == 200
    r = user_client.post(LISTA, {"base": "servicio_tv"}, format="json")
    assert r.status_code == 403
    assert not WorkType.objects.filter(org=org_a).exists()


def test_h2_otra_empresa_no_la_ve_ni_la_publica(admin_client, org_b_client):
    tipo_id = admin_client.post(LISTA, {"base": "servicio_tv"},
                                format="json").json()["id"]

    assert org_b_client.get(LISTA).json()["propias"] == []
    assert org_b_client.get(_una(tipo_id)).status_code == 404
    #  Ni con rol: org_b_client es USER, asi que tampoco pasaria la puerta de
    #  gestion; lo que se afirma aca es que no existe para ella.
    assert WorkTypeVersion.objects.filter(work_type_id=tipo_id).count() == 1


def test_h3_desactivar_la_saca_de_despacho(admin_client):
    tipo_id = admin_client.post(LISTA, {"base": "servicio_tv"},
                                format="json").json()["id"]
    r = admin_client.patch(_una(tipo_id), {"activo": False}, format="json")
    assert r.status_code == 200 and r.json()["activo"] is False
    codigos = [p["codigo"] for p in admin_client.get(DESPACHO).json()["plantillas"]]
    assert "servicio_tv" not in codigos


# ---------------------------------------------------------------------------
# I · el backend acepta lo que el tecnico anota
# ---------------------------------------------------------------------------

def test_i_lo_que_anota_el_tecnico_pasa_el_validador_del_backend():
    esquema = P.componer({"campos": [
        {"titulo": "Nota", "tipo": "texto"},
        {"titulo": "Potencia", "tipo": "numero", "min": -28, "max": -8,
         "unidad": "dBm"},
        {"titulo": "Resultado", "tipo": "seleccion", "opciones": ["Bien", "Mal"]},
        {"titulo": "Probado", "tipo": "checklist"},
    ]})
    ids = [c["id"] for c in esquema["campos"]]

    #  Como lo manda la app: el numero llega como texto.
    limpios, errores = validar_campos_tecnicos(esquema, dict(zip(ids, [
        "cambio de conector", "-19.5", "Bien", "Hecho"])))
    assert errores == {}
    assert limpios[ids[1]] == -19.5

    _, errores = validar_campos_tecnicos(esquema, {ids[1]: "-40"})
    assert ids[1] in errores          # fuera de rango
    _, errores = validar_campos_tecnicos(esquema, {ids[3]: "Quizas"})
    assert ids[3] in errores          # fuera de las opciones del checklist


# ---------------------------------------------------------------------------
# I · asuntos y plazo  --  19/10/2026
# ---------------------------------------------------------------------------
# Lo que Despacho usa para llenar el formulario solo: el asunto del ticket
# elige la plantilla, y el plazo propone «para cuando». Son del TIPO, como la
# labor: se guardan aunque el formulario del tecnico no cambie.

def _nueva(admin_client, nombre):
    return admin_client.post(LISTA, {"nombre": nombre, "labor": "trabajos",
                                     "definicion": _definicion_minima()},
                             format="json").json()["id"]


def test_i_publicar_guarda_asuntos_y_plazo_sin_crear_version(admin_client):
    tipo_id = _nueva(admin_client, "Traslado")
    r = admin_client.post(_publicar(tipo_id), {
        "definicion": _definicion_minima(),
        "asuntos": ["Cambio De Domicilio", "  cambio de  domicilio ", "", "Traslado"],
        "plazo_dias": 3}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["cambio"] is False
    #  Repetidos (sin mayusculas ni espacios) y vacios se descartan.
    assert r.json()["asuntos"] == ["Cambio De Domicilio", "Traslado"]
    assert r.json()["plazo_dias"] == 3


def test_i2_no_mandarlos_no_los_borra_y_null_borra_el_plazo(admin_client):
    tipo_id = _nueva(admin_client, "Traslado")
    admin_client.post(_publicar(tipo_id), {"definicion": _definicion_minima(),
                                           "asuntos": ["Cambio De Domicilio"],
                                           "plazo_dias": 3}, format="json")
    r = admin_client.post(_publicar(tipo_id), {"definicion": _definicion_minima(),
                                               "nombre": "Traslado de servicio"},
                          format="json")
    assert r.json()["asuntos"] == ["Cambio De Domicilio"]
    assert r.json()["plazo_dias"] == 3
    r = admin_client.post(_publicar(tipo_id), {"definicion": _definicion_minima(),
                                               "plazo_dias": None}, format="json")
    assert r.json()["plazo_dias"] is None


def test_i3_un_asunto_va_en_una_sola_plantilla(admin_client):
    a = _nueva(admin_client, "Traslado")
    b = _nueva(admin_client, "Visita general")
    admin_client.post(_publicar(a), {"definicion": _definicion_minima(),
                                     "asuntos": ["Cambio De Domicilio"]},
                      format="json")
    r = admin_client.post(_publicar(b), {"definicion": _definicion_minima(),
                                         "asuntos": ["CAMBIO DE DOMICILIO"]},
                          format="json")
    assert r.status_code == 400, r.content
    assert "Traslado" in str(r.content.decode())
    assert WorkType.objects.get(pk=b).asuntos == []


@pytest.mark.parametrize("plazo", [-1, 61, "tres"])
def test_i4_un_plazo_fuera_de_rango_no_se_guarda(admin_client, plazo):
    tipo_id = _nueva(admin_client, "Traslado")
    r = admin_client.post(_publicar(tipo_id), {"definicion": _definicion_minima(),
                                               "plazo_dias": plazo}, format="json")
    assert r.status_code == 400, r.content
    assert WorkType.objects.get(pk=tipo_id).plazo_dias is None
