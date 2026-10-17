# -*- coding: utf-8 -*-
"""
El catalogo de materiales: QUE COSAS maneja esta empresa.

DOS PREGUNTAS DISTINTAS, DOS LUGARES
------------------------------------
    Materiales   "¿que cosas maneja esta empresa?"   -- el maestro, esto
    Existencias  "¿cuanto tenemos y donde esta?"     -- el libro

Mezclarlas es lo que hace que un modulo de inventario se vuelva ilegible: la
segunda cambia todo el dia y la primera casi nunca.

POR QUE EXISTE ESTE ARCHIVO
---------------------------
Hasta el 29/09/2026 el catalogo se leia por API y no habia NINGUNA forma de dar
de alta un material: ni endpoint, ni admin, ni comando. Los tres que habia se
cargaron a mano en la base. Eso contradice la regla del proyecto -- un dato que
varia por empresa se administra desde la interfaz, no con un INSERT que solo sabe
hacer quien tiene acceso a la base.

LO QUE NO SE PUEDE CAMBIAR DESPUES DEL PRIMER MOVIMIENTO
--------------------------------------------------------
Tres campos dejan de ser editables en cuanto el material entra al libro:

    codigo   es lo que se escribe en las pantallas y lo que aparece en los
             registros viejos; cambiarlo los vuelve ilegibles
    clase    un consumible que pasa a serializado deja movimientos sin serie, y
             la existencia deja de significar lo mismo
    unidad   si "FIB-DROP" media metros y manaña mide unidades, TODO el libro
             historico cambia de significado sin que ningun movimiento se toque

El nombre y la categoria si se pueden corregir siempre: son descriptivos y no
cambian que dice un movimiento viejo.

Y ESTO SE VALIDA ACA, EN EL SERVIDOR. Deshabilitar el campo en la pantalla es una
ayuda para quien lo usa, no una garantia: cualquiera puede mandar un PATCH.
"""

from __future__ import annotations

from campo.models import MaterialCatalogo, MovimientoDeMaterial
from campo.services.storage import CampoStorage


class MaterialInvalido(Exception):
    """Lo que se niega antes de tocar el catalogo."""


#: Lo que se acepta como foto de un material. Solo imagenes: un PDF sirve como
#: evidencia de un trabajo, no para reconocer un conector en un estante.
MIME_IMAGEN = ("image/jpeg", "image/png", "image/webp")

#: Mas chico que el de una evidencia (25 MB) a proposito: una foto de catalogo se
#: mira en una tabla, no se periza como prueba, y cada fila la carga.
MAX_BYTES_IMAGEN = 5 * 1024 * 1024


#: Los tres que dejan de ser editables en cuanto hay movimientos, con el motivo
#: que la pantalla le muestra a quien lo intenta.
INMUTABLES = {
    "codigo": (
        "El codigo no se puede cambiar porque este material ya tiene movimientos "
        "registrados: es lo que aparece en las actas y en los registros viejos."
    ),
    "clase": (
        "La clase no se puede cambiar porque este material ya tiene movimientos "
        "registrados: un consumible que pasa a serializado dejaria movimientos "
        "sin numero de serie."
    ),
    "unidad": (
        "La unidad no se puede cambiar porque este material ya tiene movimientos "
        "registrados: si antes media metros y ahora midiera unidades, todo el "
        "historial cambiaria de significado sin que ningun movimiento se toque."
    ),
}


def normalizar_codigo(codigo) -> str:
    """Un codigo, siempre escrito igual.

    Sin espacios alrededor y en mayusculas: `con-sc-apc` y `CON-SC-APC ` son el
    mismo material, y dejarlos entrar como dos filas distintas es la forma mas
    facil de partir una existencia en dos.
    """
    return (codigo or "").strip().upper()


def tiene_movimientos(material) -> bool:
    """¿Este material ya entro al libro?

    Se mira el LIBRO y no el catalogo: lo que vuelve inmutable a un campo es que
    haya movimientos que se lean con el. Estar nombrado en una plantilla no
    cuenta -- una plantilla es un borrador y se puede reescribir.
    """
    return MovimientoDeMaterial.objects.filter(material=material).exists()


def tiene_imagen(material) -> bool:
    """¿Este material tiene foto?

    Se devuelve un SI/NO y no una URL a `/media/`, por dos razones medidas: ese
    prefijo solo lo sirve Django en modo desarrollo --en produccion nadie
    responde ahi-- y una foto del catalogo es un dato de la empresa, asi que pasa
    por la sesion como todo lo demas. El binario se pide a esta misma API y la
    pantalla lo muestra a traves de su propio proxy.
    """
    return bool(material.imagen_key)


def leer_imagen(material):
    """El archivo y su tipo, para servirlo. `None` si no hay o si se perdio."""
    if not material.imagen_key:
        return None
    ruta = CampoStorage.ruta_absoluta(material.imagen_key)
    if not ruta or not CampoStorage.verify_upload(material.imagen_key):
        return None
    import mimetypes
    tipo = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
    return ruta, tipo


def guardar_imagen(material, *, nombre, contenido, mime):
    """Pone (o reemplaza) la foto de un material.

    La anterior se borra: es ilustrativa y nadie va a querer la version vieja de
    una foto que alguien reemplazo porque salio mal. Es lo contrario de una
    evidencia, que no se borra nunca porque es la prueba de un trabajo.
    """
    mime = (mime or "").lower()
    if mime not in MIME_IMAGEN:
        raise MaterialInvalido(
            "La foto tiene que ser una imagen (JPG, PNG o WebP). Llego: "
            + (mime or "sin tipo") + "."
        )
    if not contenido:
        raise MaterialInvalido("El archivo llego vacio.")
    if len(contenido) > MAX_BYTES_IMAGEN:
        raise MaterialInvalido(
            f"La foto pesa {len(contenido) // 1024} KB y el maximo son "
            f"{MAX_BYTES_IMAGEN // 1024} KB. Sacale una mas liviana o reducila."
        )

    anterior = material.imagen_key
    key = CampoStorage.generar_key_catalogo(
        str(material.org_id), str(material.id), nombre or "foto.jpg"
    )
    if not CampoStorage.guardar(key, contenido):
        raise MaterialInvalido("No se pudo guardar la foto. Reintenta.")

    material.imagen_key = key
    material.save(update_fields=["imagen_key", "updated_at"])
    if anterior:
        CampoStorage.borrar(anterior)
    return material


def quitar_imagen(material):
    """Saca la foto. El material queda; lo que se va es la ilustracion."""
    anterior = material.imagen_key
    material.imagen_key = ""
    material.save(update_fields=["imagen_key", "updated_at"])
    if anterior:
        CampoStorage.borrar(anterior)
    return material


def materiales_de(org, *, solo_activos: bool = False) -> list[dict]:
    """El catalogo entero, con lo que la pantalla necesita para decidir.

    Incluye `tiene_movimientos` porque de eso depende que campos se pueden
    editar, y calcularlo en la pantalla obligaria a una consulta por fila.
    """
    qs = MaterialCatalogo.objects.filter(org=org)
    if solo_activos:
        qs = qs.filter(activo=True)

    usados = set(
        MovimientoDeMaterial.objects.filter(org=org)
        .values_list("material_id", flat=True)
        .distinct()
    )
    return [
        {
            "id": str(m.id),
            "codigo": m.codigo,
            "nombre": m.nombre,
            "categoria": m.categoria,
            "clase": m.clase,
            "unidad": m.unidad,
            "activo": m.activo,
            "es_serializado": m.es_serializado,
            "tiene_movimientos": m.id in usados,
            "tiene_imagen": bool(m.imagen_key),
        }
        for m in qs
    ]


def crear_material(*, org, codigo, nombre, clase="", unidad="", categoria=""):
    """Da de alta un material. Todo editable todavia: no tiene historia.

    Para un material serializado esto crea el TIPO --"ONT Huawei HG8145V5"--, no
    los aparatos: cada numero de serie nace cuando ese equipo entra al inventario.
    """
    codigo = normalizar_codigo(codigo)
    nombre = (nombre or "").strip()
    if not codigo:
        raise MaterialInvalido("Un material necesita un codigo para poder nombrarlo.")
    if not nombre:
        raise MaterialInvalido("Un material necesita un nombre.")

    clase = (clase or MaterialCatalogo.CONSUMIBLE).strip()
    _exigir_clase(clase)
    unidad = (unidad or "unidades").strip()

    if MaterialCatalogo.objects.filter(org=org, codigo=codigo).exists():
        raise MaterialInvalido(
            f"Ya hay un material con el codigo {codigo} en esta empresa."
        )

    return MaterialCatalogo.objects.create(
        org=org, codigo=codigo, nombre=nombre, clase=clase, unidad=unidad,
        categoria=(categoria or "").strip(),
    )


def editar_material(material, *, codigo=None, nombre=None, clase=None,
                    unidad=None, categoria=None, activo=None):
    """Corrige un material, respetando lo que ya no se puede tocar.

    Un campo que llega con el MISMO valor no cuenta como cambio: la pantalla
    manda el formulario entero, y rechazarla por enviar el codigo que ya tenia
    seria negarse a guardar un cambio de nombre.
    """
    con_historia = tiene_movimientos(material)
    cambios = {}

    if codigo is not None:
        nuevo = normalizar_codigo(codigo)
        if not nuevo:
            raise MaterialInvalido("El codigo no puede quedar vacio.")
        if nuevo != material.codigo:
            if con_historia:
                raise MaterialInvalido(INMUTABLES["codigo"])
            if MaterialCatalogo.objects.filter(
                org=material.org, codigo=nuevo
            ).exclude(pk=material.pk).exists():
                raise MaterialInvalido(
                    f"Ya hay otro material con el codigo {nuevo} en esta empresa."
                )
            cambios["codigo"] = nuevo

    if clase is not None:
        nueva = (clase or "").strip()
        _exigir_clase(nueva)
        if nueva != material.clase:
            if con_historia:
                raise MaterialInvalido(INMUTABLES["clase"])
            cambios["clase"] = nueva

    if unidad is not None:
        nueva = (unidad or "").strip()
        if not nueva:
            raise MaterialInvalido("La unidad no puede quedar vacia.")
        if nueva != material.unidad:
            if con_historia:
                raise MaterialInvalido(INMUTABLES["unidad"])
            cambios["unidad"] = nueva

    # Descriptivos: se corrigen siempre. Un nombre mal escrito no cambia lo que
    # dice un movimiento viejo.
    if nombre is not None:
        nuevo = (nombre or "").strip()
        if not nuevo:
            raise MaterialInvalido("El nombre no puede quedar vacio.")
        cambios["nombre"] = nuevo
    if categoria is not None:
        cambios["categoria"] = (categoria or "").strip()
    if activo is not None:
        cambios["activo"] = bool(activo)

    for campo, valor in cambios.items():
        setattr(material, campo, valor)
    if cambios:
        material.save(update_fields=[*cambios.keys(), "updated_at"])
    return material


def _exigir_clase(clase) -> None:
    validas = {c[0] for c in MaterialCatalogo.CLASES}
    if clase not in validas:
        raise MaterialInvalido(
            f"'{clase}' no es una clase de material. Las que hay: "
            + ", ".join(sorted(validas))
            + "."
        )
