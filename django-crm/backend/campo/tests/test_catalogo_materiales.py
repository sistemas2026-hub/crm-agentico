# -*- coding: utf-8 -*-
"""
El maestro del catalogo: dar de alta materiales y corregirlos sin romper el libro.

LO QUE ESTAS PRUEBAS DEFIENDEN
------------------------------
Que tres campos --codigo, clase y unidad-- dejan de ser editables en cuanto el
material entra al libro, Y QUE ESO SE VALIDA EN EL SERVIDOR. Deshabilitar el campo
en la pantalla es una ayuda para quien lo usa, no una garantia: estas pruebas
mandan el PATCH directo, que es lo que haria cualquiera con la consola abierta.

El de la unidad es el menos obvio de los tres y el que mas dano hace: si
"FIB-DROP" media metros y manaña midiera unidades, todo el libro historico cambia
de significado sin que ningun movimiento se toque.
"""

from decimal import Decimal

import pytest

from campo.inventario import UbicacionInventario
from campo.models import MaterialCatalogo
from campo.services import inventario as inv

pytestmark = pytest.mark.django_db

MATERIALES = "/api/campo/inventario/materiales/"
CATALOGO = "/api/campo/inventario/catalogo/"


@pytest.fixture
def bodega(org_a):
    return UbicacionInventario.objects.create(
        org=org_a, tipo=UbicacionInventario.BODEGA, nombre="Bodega Central"
    )


def _crear(client, **campos):
    cuerpo = {"codigo": "CON-SC-APC", "nombre": "Conector SC/APC",
              "clase": "consumible", "unidad": "unidades"}
    cuerpo.update(campos)
    return client.post(MATERIALES, cuerpo, format="json")


def _con_movimientos(org, material, bodega):
    """Le da historia: una entrada basta para que el material este en el libro."""
    inv.registrar_entrada(org=org, material=material, cantidad=10,
                          ubicacion_destino=bodega, origen_ref="ALTA")


# ---------------------------------------------------------------------------
# A · crear
# ---------------------------------------------------------------------------

def test_A_crear_material_aparece_en_el_catalogo_y_en_los_selectores(
    admin_client, org_a
):
    """Y en el mismo endpoint que alimenta los desplegables de las operaciones."""
    r = _crear(admin_client, codigo="con-sc-apc")
    assert r.status_code == 201, r.content
    # El codigo se normaliza: `con-sc-apc` y `CON-SC-APC ` son el mismo material.
    assert r.json()["codigo"] == "CON-SC-APC"

    maestro = admin_client.get(MATERIALES).json()["materiales"]
    assert [m["codigo"] for m in maestro] == ["CON-SC-APC"]
    assert maestro[0]["tiene_movimientos"] is False

    selectores = admin_client.get(CATALOGO).json()["materiales"]
    assert [m["codigo"] for m in selectores] == ["CON-SC-APC"]


# ---------------------------------------------------------------------------
# B y C · el codigo es unico POR EMPRESA, no entre empresas
# ---------------------------------------------------------------------------

def test_B_el_mismo_codigo_en_dos_empresas_se_permite(admin_client, org_b_client,
                                                       org_a, org_b):
    """Dos ISP pueden llamar CON-SC-APC a cosas distintas, y ninguno es dueño
    del nombre."""
    assert _crear(admin_client).status_code == 201
    assert _crear(org_b_client).status_code == 201

    assert MaterialCatalogo.objects.filter(codigo="CON-SC-APC").count() == 2


def test_C_el_mismo_codigo_dos_veces_en_la_misma_empresa_se_rechaza(admin_client,
                                                                     org_a):
    assert _crear(admin_client).status_code == 201
    r = _crear(admin_client, nombre="Otro conector")
    assert r.status_code == 409, r.content
    assert "CON-SC-APC" in r.json()["detail"]


# ---------------------------------------------------------------------------
# D, E y F · la inmutabilidad, medida contra el SERVIDOR
# ---------------------------------------------------------------------------

def test_D_sin_movimientos_se_pueden_cambiar_codigo_clase_y_unidad(admin_client,
                                                                    org_a):
    """Todavia no hay historia que contradecir."""
    creado = _crear(admin_client).json()

    r = admin_client.patch(f"{MATERIALES}{creado['id']}/", {
        "codigo": "CON-NUEVO", "clase": "bobina", "unidad": "m",
    }, format="json")
    assert r.status_code == 200, r.content

    m = MaterialCatalogo.objects.get(id=creado["id"])
    assert (m.codigo, m.clase, m.unidad) == ("CON-NUEVO", "bobina", "m")


@pytest.mark.parametrize("campo,valor", [
    ("codigo", "CON-OTRO"),
    ("clase", "serializado"),
    ("unidad", "kg"),
])
def test_E_con_movimientos_NO_se_pueden_cambiar(admin_client, org_a, bodega,
                                                 campo, valor):
    """El PATCH va directo al servidor, sin pasar por la pantalla.

    Es la unica forma de probar que la regla vive en el backend: si solo estuviera
    en la interfaz, esta prueba pasaria igual con el campo deshabilitado y la
    proteccion seria de mentira.
    """
    creado = _crear(admin_client).json()
    material = MaterialCatalogo.objects.get(id=creado["id"])
    _con_movimientos(org_a, material, bodega)

    r = admin_client.patch(f"{MATERIALES}{creado['id']}/", {campo: valor},
                           format="json")
    assert r.status_code == 409, r.content
    # El mensaje explica POR QUE, que es lo que alguien necesita leer.
    assert "ya tiene movimientos" in r.json()["detail"]

    material.refresh_from_db()
    assert getattr(material, campo) != valor


def test_E2_la_unidad_es_la_que_mas_silenciosamente_rompe(admin_client, org_a,
                                                           bodega):
    """Cambiarla no toca ningun movimiento y sin embargo los cambia a todos.

    300 de "FIB-DROP" son 300 metros. Si la unidad pasa a "unidades", esos mismos
    300 pasan a ser 300 rollos sin que nada en el libro se haya movido.
    """
    creado = _crear(admin_client, codigo="FIB-DROP", nombre="Fibra drop",
                    clase="bobina", unidad="m").json()
    material = MaterialCatalogo.objects.get(id=creado["id"])
    inv.registrar_entrada(org=org_a, material=material, cantidad="300.5",
                          ubicacion_destino=bodega, origen_ref="BOBINA")

    r = admin_client.patch(f"{MATERIALES}{creado['id']}/", {"unidad": "unidades"},
                           format="json")

    assert r.status_code == 409, r.content
    material.refresh_from_db()
    assert material.unidad == "m"
    assert inv.existencia(bodega, material) == Decimal("300.5")


def test_F_el_nombre_y_la_categoria_se_corrigen_siempre(admin_client, org_a,
                                                         bodega):
    """Son descriptivos: no cambian lo que dice un movimiento viejo."""
    creado = _crear(admin_client).json()
    material = MaterialCatalogo.objects.get(id=creado["id"])
    _con_movimientos(org_a, material, bodega)

    r = admin_client.patch(f"{MATERIALES}{creado['id']}/", {
        "nombre": "Conector SC/APC monomodo", "categoria": "Conectividad",
    }, format="json")
    assert r.status_code == 200, r.content

    material.refresh_from_db()
    assert material.nombre == "Conector SC/APC monomodo"
    assert material.categoria == "Conectividad"


def test_mandar_el_mismo_codigo_que_ya_tenia_no_es_un_cambio(admin_client, org_a,
                                                              bodega):
    """La pantalla manda el formulario entero, incluido el codigo bloqueado.

    Rechazar eso seria negarse a guardar un cambio de nombre porque el formulario
    trae tambien los campos que no cambiaron.
    """
    creado = _crear(admin_client).json()
    material = MaterialCatalogo.objects.get(id=creado["id"])
    _con_movimientos(org_a, material, bodega)

    r = admin_client.patch(f"{MATERIALES}{creado['id']}/", {
        "codigo": "CON-SC-APC", "clase": "consumible", "unidad": "unidades",
        "nombre": "Conector corregido",
    }, format="json")
    assert r.status_code == 200, r.content
    material.refresh_from_db()
    assert material.nombre == "Conector corregido"


# ---------------------------------------------------------------------------
# G y H · dar de baja
# ---------------------------------------------------------------------------

def test_G_un_material_dado_de_baja_desaparece_de_las_operaciones_nuevas(
    admin_client, org_a
):
    creado = _crear(admin_client).json()

    r = admin_client.patch(f"{MATERIALES}{creado['id']}/", {"activo": False},
                           format="json")
    assert r.status_code == 200, r.content

    # El endpoint que alimenta los desplegables ya no lo ofrece...
    assert admin_client.get(CATALOGO).json()["materiales"] == []
    # ...y el maestro lo sigue mostrando, marcado.
    maestro = admin_client.get(MATERIALES).json()["materiales"]
    assert len(maestro) == 1 and maestro[0]["activo"] is False


def test_H_un_material_dado_de_baja_sigue_explicando_los_historicos(
    admin_client, org_a, bodega
):
    """Sus movimientos siguen ahi y su existencia se sigue pudiendo leer.

    Es la razon por la que se da de baja en vez de borrarse: los registros viejos
    lo referencian y son lo que explica una existencia.
    """
    creado = _crear(admin_client).json()
    material = MaterialCatalogo.objects.get(id=creado["id"])
    _con_movimientos(org_a, material, bodega)

    admin_client.patch(f"{MATERIALES}{creado['id']}/", {"activo": False},
                       format="json")

    assert inv.existencia(bodega, material) == Decimal("10")
    # Y sigue apareciendo en la pantalla de existencias de esa ubicacion.
    codigos = [f["codigo"] for f in inv.existencias_de(bodega)]
    assert "CON-SC-APC" in codigos


# ---------------------------------------------------------------------------
# I · aislamiento entre empresas
# ---------------------------------------------------------------------------

def test_I_una_empresa_no_ve_ni_toca_el_catalogo_de_otra(admin_client,
                                                          org_b_client, org_a):
    creado = _crear(admin_client).json()

    # No lo ve...
    assert org_b_client.get(MATERIALES).json()["materiales"] == []
    # ...y no lo puede editar: para la otra empresa ese material no existe.
    r = org_b_client.patch(f"{MATERIALES}{creado['id']}/", {"nombre": "Ajeno"},
                           format="json")
    assert r.status_code == 404, r.content

    assert MaterialCatalogo.objects.get(id=creado["id"]).nombre == "Conector SC/APC"


# ---------------------------------------------------------------------------
# J · no hay borrado fisico
# ---------------------------------------------------------------------------

def test_J_no_existe_ningun_camino_para_borrar_un_material(admin_client, org_a):
    """Ni por DELETE ni por ninguna otra ruta del modulo.

    Se afirma sobre el EFECTO --que el material sigue en la base-- y no sobre que
    la vista no declare el metodo: una ruta nueva podria agregarlo manaña.
    """
    creado = _crear(admin_client).json()

    r = admin_client.delete(f"{MATERIALES}{creado['id']}/")
    assert r.status_code in (404, 405), r.content
    assert MaterialCatalogo.objects.filter(id=creado["id"]).exists()


# ---------------------------------------------------------------------------
# Permisos
# ---------------------------------------------------------------------------

def test_un_tecnico_raso_puede_LEER_el_catalogo(user_client, org_a, admin_client):
    _crear(admin_client)
    r = user_client.get(MATERIALES)
    assert r.status_code == 200, r.content
    assert len(r.json()["materiales"]) == 1


def test_un_tecnico_raso_NO_puede_crear_ni_editar(user_client, admin_client, org_a):
    creado = _crear(admin_client).json()

    assert user_client.post(MATERIALES, {
        "codigo": "PROPIO", "nombre": "Inventado",
    }, format="json").status_code == 403

    assert user_client.patch(f"{MATERIALES}{creado['id']}/", {"nombre": "Otro"},
                             format="json").status_code == 403


def test_una_clase_que_no_existe_lo_dice_y_lista_las_que_hay(admin_client, org_a):
    r = _crear(admin_client, clase="liquido")
    assert r.status_code == 409, r.content
    assert "consumible" in r.json()["detail"]


# ---------------------------------------------------------------------------
# La foto del material
# ---------------------------------------------------------------------------

def _png():
    """Un PNG de 1x1 de verdad: el mas chico que un navegador acepta como imagen."""
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
        b"IQAAAABJRU5ErkJggg=="
    )


def _subir(client, material_id, contenido=None, nombre="foto.png",
           tipo="image/png"):
    from django.core.files.uploadedfile import SimpleUploadedFile
    archivo = SimpleUploadedFile(nombre, contenido if contenido is not None else _png(),
                                 content_type=tipo)
    return client.post(f"{MATERIALES}{material_id}/imagen/", {"imagen": archivo},
                       format="multipart")


def test_se_le_puede_poner_una_foto_al_material(admin_client, org_a):
    creado = _crear(admin_client).json()

    r = _subir(admin_client, creado["id"])
    assert r.status_code == 200, r.content
    assert r.json()["tiene_imagen"] is True

    # El catalogo dice que HAY foto; la pantalla la pide aparte.
    fila = admin_client.get(MATERIALES).json()["materiales"][0]
    assert fila["tiene_imagen"] is True

    # Y el binario se sirve por la API, con sesion -- no por /media, que solo
    # existe en desarrollo.
    foto = admin_client.get(f"{MATERIALES}{creado['id']}/imagen/")
    assert foto.status_code == 200, foto.content
    assert foto["Content-Type"].startswith("image/")
    assert b"".join(foto.streaming_content) == _png()


def test_la_foto_se_reemplaza_y_la_anterior_se_borra(admin_client, org_a):
    """Nadie quiere la version vieja de una foto que salio mal.

    Es lo contrario de una evidencia, que no se borra nunca porque es la prueba
    de un trabajo.
    """
    from campo.services.storage import CampoStorage
    creado = _crear(admin_client).json()

    _subir(admin_client, creado["id"])
    key_vieja = MaterialCatalogo.objects.get(id=creado["id"]).imagen_key
    assert CampoStorage.verify_upload(key_vieja)

    _subir(admin_client, creado["id"], nombre="mejor.png")
    key_nueva = MaterialCatalogo.objects.get(id=creado["id"]).imagen_key

    assert key_nueva != key_vieja
    assert not CampoStorage.verify_upload(key_vieja), "quedo la foto anterior"
    assert CampoStorage.verify_upload(key_nueva)


def test_quitar_la_foto_no_borra_el_material(admin_client, org_a):
    creado = _crear(admin_client).json()
    _subir(admin_client, creado["id"])

    r = admin_client.delete(f"{MATERIALES}{creado['id']}/imagen/")
    assert r.status_code == 200, r.content
    assert r.json()["tiene_imagen"] is False
    # Y pedirla devuelve 404, que la pantalla lee como "no tiene foto".
    assert admin_client.get(f"{MATERIALES}{creado['id']}/imagen/").status_code == 404
    # El material sigue, que es lo que no se borra nunca.
    assert MaterialCatalogo.objects.filter(id=creado["id"]).exists()


def test_un_archivo_que_no_es_imagen_se_rechaza(admin_client, org_a):
    """Un PDF sirve como evidencia de un trabajo, no para reconocer un conector."""
    creado = _crear(admin_client).json()

    r = _subir(admin_client, creado["id"], contenido=b"%PDF-1.4 no soy una foto",
               nombre="ficha.pdf", tipo="application/pdf")

    assert r.status_code == 409, r.content
    assert "tiene que ser una imagen" in r.json()["detail"]
    assert MaterialCatalogo.objects.get(id=creado["id"]).imagen_key == ""


def test_una_foto_demasiado_pesada_lo_dice_con_los_dos_numeros(admin_client, org_a):
    creado = _crear(admin_client).json()

    r = _subir(admin_client, creado["id"], contenido=b"x" * (6 * 1024 * 1024))

    assert r.status_code == 409, r.content
    detalle = r.json()["detail"]
    assert "5120 KB" in detalle and "6144 KB" in detalle


def test_la_foto_de_otra_empresa_no_se_puede_tocar(admin_client, org_b_client, org_a):
    creado = _crear(admin_client).json()
    r = _subir(org_b_client, creado["id"])
    assert r.status_code == 404, r.content


def test_un_tecnico_raso_no_puede_cambiar_la_foto(user_client, admin_client, org_a):
    creado = _crear(admin_client).json()
    assert _subir(user_client, creado["id"]).status_code == 403
